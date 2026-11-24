"""Capabilities agreed by the user and required by each MCP tool."""
from typing import Iterable

READ_SCOPE = "circular:read"
WRITE_SCOPE = "circular:write"
WRITE_SCOPES = f"{READ_SCOPE} {WRITE_SCOPE}"

FAMILIES = {
    "tickets": "Tickets et triage",
    "projects": "Projets et feuille de route",
    "docs": "Documents et collaboration",
    "customers": "Clients et demandes",
    "releases": "Releases et revues",
    "agents": "Contexte des assistants",
}


def family_scope(family: str, mode: str) -> str:
    return f"circular:{family}:{mode}"


FAMILY_SCOPES = frozenset(family_scope(family, mode) for family in FAMILIES for mode in ("read", "write"))
ALL_SCOPES = sorted({READ_SCOPE, WRITE_SCOPE, *FAMILY_SCOPES})


def scope_string(scopes: Iterable[str]) -> str:
    return " ".join(sorted(set(scopes)))


def valid_scopes(scopes: set[str]) -> bool:
    return (
        READ_SCOPE in scopes
        and scopes <= set(ALL_SCOPES)
        and all(family_scope(family, "write") not in scopes or family_scope(family, "read") in scopes for family in FAMILIES)
    )


def scope_columns(scopes: Iterable[str]) -> tuple[str, str]:
    values = set(scopes)
    return scope_string(values - FAMILY_SCOPES), scope_string(values & FAMILY_SCOPES)


def row_scopes(row) -> list[str]:
    return scope_string([*row["scope"].split(), *row["family_scopes"].split()]).split()


def scope_options(scopes: Iterable[str]) -> list[dict]:
    available = set(scopes)
    groups = []
    for family, label in FAMILIES.items():
        read = family_scope(family, "read")
        write = family_scope(family, "write")
        if read in available:
            groups.append({"id": family, "label": label, "read": read, "write": write if write in available else None})
    return groups


def tool_scopes(family: str, *, write: bool = False) -> set[str]:
    scopes = {READ_SCOPE, family_scope(family, "read")}
    if write:
        scopes.add(family_scope(family, "write"))
    return scopes
