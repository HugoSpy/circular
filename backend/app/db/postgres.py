"""Small DB-API bridge for the repository's parameterized, portable SQL.

Only driver conventions are adapted here: qmark parameters, result names and
generated IDs. Domain SQL and authorization stay in their repository layers.
"""
from collections.abc import Iterable, Iterator, Mapping, Sequence
import re
import sqlite3
from typing import Any


# Inserts into these tables use the common generated-ID contract. Association
# tables, counters and settings must never receive an implicit RETURNING id.
IDENTITY_TABLES = frozenset({
    "projects", "issues", "labels", "comments", "saved_views", "issue_templates",
    "issue_activity", "users", "project_invitations",
})


def compile_sql(sql: str, *, parameters: bool = True) -> str:
    """Convert qmark placeholders without treating SQL literals as placeholders.

    PostgreSQL folds unquoted aliases to lowercase. Quote mixed-case aliases so
    both drivers expose the same HTTP-facing dictionary keys.
    """
    def alias(match: re.Match[str]) -> str:
        name = match[2]
        return f'AS "{name}"' if name and any(char.isupper() for char in name) and any(char.islower() for char in name) else match[0]

    sql = re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*|/\*[\s\S]*?\*/|(\bAS\s+([A-Za-z_][A-Za-z_0-9]*))", alias, sql, flags=re.IGNORECASE)
    result: list[str] = []
    index = 0
    quote: str | None = None
    line_comment = False
    block_comment = False
    while index < len(sql):
        char = sql[index]
        following = sql[index:index + 2]
        if line_comment:
            if char == "\n":
                line_comment = False
        elif block_comment:
            if following == "*/":
                result.append("*/")
                block_comment = False
                index += 2
                continue
        elif quote:
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    result.append(quote * 2)
                    index += 2
                    continue
                quote = None
        elif following == "--":
            line_comment = True
        elif following == "/*":
            block_comment = True
        elif char in {"'", '"'}:
            quote = char
        elif char == "?":
            result.append("%s")
            index += 1
            continue
        result.append("%%" if char == "%" and parameters else char)
        index += 1
    return "".join(result)


class Record(Mapping[str, Any]):
    """Dictionary-compatible row that also supports sqlite's numeric indexing."""
    def __init__(self, row: Mapping[str, Any]):
        self._row = row
        self._values = tuple(row.values())

    def __getitem__(self, key: str | int) -> Any:
        return self._values[key] if isinstance(key, int) else self._row[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._row)

    def __len__(self) -> int:
        return len(self._row)


class Cursor:
    def __init__(self, cursor: Any, *, generated_id: bool = False):
        self._cursor = cursor
        self.lastrowid: int | None = None
        if generated_id:
            row = cursor.fetchone()
            self.lastrowid = row["id"] if row else None

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def fetchone(self) -> Record | None:
        row = self._cursor.fetchone()
        return Record(row) if row is not None else None

    def fetchall(self) -> list[Record]:
        return [Record(row) for row in self._cursor.fetchall()]

    def __iter__(self) -> Iterator[Record]:
        for row in self._cursor:
            yield Record(row)


class PostgresConnection:
    dialect = "postgresql"

    def __init__(self, connection: Any):
        self.raw = connection

    def execute(self, sql: str, values: Sequence[Any] = ()) -> Cursor:
        import psycopg

        statement = sql.strip().rstrip(";")
        inserted = re.match(r"INSERT\s+INTO\s+([a-z_][a-z_0-9]*)\b", statement, re.IGNORECASE)
        generated_id = bool(inserted and inserted[1].lower() in IDENTITY_TABLES and not re.search(r"\bRETURNING\b", statement, re.IGNORECASE))
        if generated_id:
            statement += " RETURNING id"
        try:
            # Passing None prevents psycopg interpreting percent signs in DDL.
            cursor = self.raw.execute(compile_sql(statement, parameters=bool(values)), tuple(values) if values else None)
            return Cursor(cursor, generated_id=generated_id)
        except psycopg.IntegrityError as error:
            # Preserve the service layer's existing driver-independent behavior
            # while exposing no PostgreSQL diagnostics or values in HTTP errors.
            raise sqlite3.IntegrityError("Database integrity constraint violated.") from error

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> Cursor:
        import psycopg

        cursor = self.raw.cursor()
        try:
            cursor.executemany(compile_sql(sql), rows)
            return Cursor(cursor)
        except psycopg.IntegrityError as error:
            raise sqlite3.IntegrityError("Database integrity constraint violated.") from error

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()
