"""Workspace records with checked references and optimistic revisions."""
from uuid import uuid4
from urllib.parse import urlsplit
import re

from pydantic import BaseModel

from backend.app.db.session import timestamp
from backend.app.repositories.workspace import WorkspaceRepository
from backend.app.schemas.records import RecordChange, RecordKind, RecordState
from backend.app.services.scope import scoped_connection
from backend.app.services.workspace import DomainError, WorkspaceService

RECORD_FAMILY = {
    "initiative": "projects", "milestone": "projects", "cycle": "projects", "update": "projects", "triage": "projects",
    "customer": "customers", "request": "customers",
    "pipeline": "releases", "release": "releases", "release_note": "releases", "review_criterion": "releases", "pull_link": "releases",
    "instruction": "agents", "learning": "agents", "friction": "agents",
}
PARENT_KINDS = {
    "initiative": {"initiative"}, "update": {"initiative", "milestone"}, "request": {"customer"},
    "release": {"pipeline"}, "release_note": {"pipeline", "release"},
}
PROJECT_KINDS = {"initiative", "milestone", "cycle", "update", "triage", "request", "pipeline", "release", "release_note", "review_criterion", "pull_link", "friction"}
TICKET_KINDS = {"request", "release", "pull_link", "friction"}
PROJECT_REQUIRED = {"milestone", "pull_link"}
PARENT_REQUIRED = {"release", "release_note"}
COLUMNS = """r.id, r.kind, r.project_id AS projectId, r.ticket_id AS ticketId, r.parent_id AS parentId,
    r.title, r.body, r.state, r.source_url AS sourceUrl, r.starts_on AS startsOn, r.ends_on AS endsOn,
    r.created_by AS createdBy, r.updated_by AS updatedBy, r.updated_at AS updatedAt, r.revision, r.archived_at AS archivedAt,
    (SELECT COUNT(*) FROM learning_reactions lr WHERE lr.record_id = r.id) AS helpfulCount"""


class Record(BaseModel):
    id: str
    kind: RecordKind
    projectId: int | None
    ticketId: int | None
    parentId: str | None
    title: str
    body: str
    state: RecordState
    sourceUrl: str | None
    startsOn: str | None
    endsOn: str | None
    createdBy: int
    updatedBy: int
    updatedAt: str
    revision: int
    archivedAt: str | None
    helpfulCount: int


class RecordPage(BaseModel):
    items: list[Record]
    nextCursor: str | None


class RecordsService:
    def __init__(self, database, user_id: int, workspace_id: int):
        self.database = database
        self.user_id = user_id
        self.workspace_id = workspace_id

    def visible(self, repo):
        access, values = repo.access_clause()
        project = f"SELECT p.id FROM projects p WHERE {access}"
        ticket = f"SELECT i.id FROM issues i JOIN projects p ON p.id = i.project_id WHERE {access}"
        clause = f"""r.workspace_id = ? AND
            (r.project_id IS NULL OR r.project_id IN ({project})) AND
            (r.ticket_id IS NULL OR r.ticket_id IN ({ticket}))"""
        return clause, [self.workspace_id, *values, *values]

    @staticmethod
    def membership(repo):
        if repo.container_role() not in {"owner", "member"}:
            raise DomainError(403, "Cette rubrique est réservée aux membres de l’espace.")

    def list(self, kind, query="", cursor="", limit=30, archived=False):
        with scoped_connection(self.database, self.user_id, self.workspace_id) as connection:
            repo = WorkspaceRepository(connection, self.user_id, self.workspace_id)
            self.membership(repo)
            where, values = self.visible(repo)
            matches = connection.execute(f"""SELECT {COLUMNS} FROM workspace_records r
                WHERE {where} AND r.kind = ? AND r.id > ? AND (? = 1 OR r.archived_at IS NULL)
                AND (lower(r.title) LIKE ? ESCAPE '\\' OR lower(r.body) LIKE ? ESCAPE '\\')
                ORDER BY r.id LIMIT ?""",
                [*values, kind, cursor, int(archived), self.pattern(query), self.pattern(query), limit + 1]).fetchall()
            return RecordPage(items=[Record.model_validate(dict(row)) for row in matches[:limit]],
                              nextCursor=matches[limit - 1]["id"] if len(matches) > limit else None)

    @staticmethod
    def pattern(query):
        return "%" + query.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"

    def get(self, kind, record_id):
        with scoped_connection(self.database, self.user_id, self.workspace_id) as connection:
            return self.get_in(WorkspaceRepository(connection, self.user_id, self.workspace_id), kind, record_id)

    def get_in(self, repo, kind, record_id, *, lock=False):
        self.membership(repo)
        where, values = self.visible(repo)
        locking = " FOR UPDATE OF r" if lock and self.database.dialect == "postgresql" else ""
        row = repo.connection.execute(f"""SELECT {COLUMNS} FROM workspace_records r
            WHERE {where} AND r.kind = ? AND r.id = ?""" + locking, [*values, kind, record_id]).fetchone()
        return Record.model_validate(dict(WorkspaceService.require(row, "Élément introuvable.")))

    def save(self, kind, data: RecordChange):
        with scoped_connection(self.database, self.user_id, self.workspace_id, write=True, lock_workspace=True) as connection:
            repo = WorkspaceRepository(connection, self.user_id, self.workspace_id)
            existing = self.target(repo, kind, data)
            return self.save_in(repo, kind, data, existing)

    def target(self, repo, kind, data):
        self.membership(repo)
        existing = self.get_in(repo, kind, str(data.id), lock=True) if data.id else None
        if existing and existing.archivedAt:
            raise DomainError(409, "Cet élément est archivé.")
        if existing and existing.createdBy != self.user_id and repo.container_role() != "owner":
            raise DomainError(403, "Seul l’auteur ou un propriétaire peut modifier cet élément.")
        self.check_references(repo, kind, data.record, existing)
        return existing

    def archive_target(self, repo, kind, record_id):
        record = self.get_in(repo, kind, record_id, lock=True)
        if record.createdBy != self.user_id and repo.container_role() != "owner":
            raise DomainError(403, "Seul l’auteur ou un propriétaire peut archiver cet élément.")
        if record.projectId:
            from backend.app.services.mcp_operation import lock_target_project
            lock_target_project(repo, record.projectId)
        return record

    def archive_in(self, repo, record, revision):
        if record.revision != revision or record.archivedAt:
            raise DomainError(409, "L’élément a changé. Relisez-le avant de l’archiver.")
        child = repo.connection.execute("""SELECT 1 FROM workspace_records
            WHERE workspace_id = ? AND parent_id = ? AND archived_at IS NULL LIMIT 1""", (self.workspace_id, record.id)).fetchone()
        if child:
            raise DomainError(409, "Archivez d’abord les éléments rattachés.")
        now = timestamp()
        repo.connection.execute("""UPDATE workspace_records SET archived_at = ?, updated_at = ?,
            updated_by = ?, revision = revision + 1 WHERE workspace_id = ? AND id = ?""",
            (now, now, self.user_id, self.workspace_id, record.id))
        return self.get_in(repo, record.kind, record.id)

    def archive(self, kind, record_id, revision):
        with scoped_connection(self.database, self.user_id, self.workspace_id, write=True, lock_workspace=True) as connection:
            repo = WorkspaceRepository(connection, self.user_id, self.workspace_id)
            return self.archive_in(repo, self.archive_target(repo, kind, record_id), revision)

    def check_references(self, repo, kind, draft, existing):
        from backend.app.services.mcp_operation import lock_target_project

        if (draft.projectId and kind not in PROJECT_KINDS) or (draft.ticketId and kind not in TICKET_KINDS):
            raise DomainError(422, "Ce type d’élément ne permet pas cette association.")
        if kind in PROJECT_REQUIRED and not draft.projectId or kind in PARENT_REQUIRED and not draft.parentId:
            raise DomainError(422, "Renseignez le projet ou l’élément parent.")
        if kind == "pull_link":
            source = urlsplit(draft.sourceUrl or "")
            if (not draft.ticketId or source.netloc != "github.com" or source.query or source.fragment
                    or not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[1-9][0-9]*", source.path)):
                raise DomainError(422, "Fournissez un ticket et le lien HTTPS d’une pull request GitHub.")
        if draft.ticketId:
            repo.lock_issue(draft.ticketId)
            ticket = WorkspaceService.require(repo.issue(draft.ticketId), "Ticket introuvable.")
            if ticket["projectId"] != draft.projectId:
                raise DomainError(422, "Le ticket et l’élément doivent appartenir au même projet.")
        if draft.projectId:
            lock_target_project(repo, draft.projectId)
        if existing and existing.projectId != draft.projectId:
            raise DomainError(422, "Le projet d’un élément existant est fixe.")
        if draft.parentId:
            model = repo.connection.execute("SELECT kind FROM workspace_records WHERE id = ? AND workspace_id = ?",
                                            (str(draft.parentId), self.workspace_id)).fetchone()
            if not model or model["kind"] not in PARENT_KINDS.get(kind, ()):
                raise DomainError(404, "Élément parent introuvable.")
            parent = self.get_in(repo, model["kind"], str(draft.parentId))
            if parent.archivedAt or (parent.projectId is not None and parent.projectId != draft.projectId):
                raise DomainError(422, "Le parent ne peut pas être utilisé dans ce projet.")
            if existing and existing.kind == "initiative" and existing.parentId != parent.id:
                self.check_initiative_cycle(repo, existing.id, parent)

    def check_initiative_cycle(self, repo, record_id, parent):
        seen = {record_id}
        while parent:
            if parent.id in seen:
                raise DomainError(409, "Cette relation crée une boucle d’initiatives.")
            seen.add(parent.id)
            parent = self.get_in(repo, "initiative", parent.parentId) if parent.parentId else None

    def save_in(self, repo, kind, data, existing):
        draft = data.record
        parent_id = str(draft.parentId) if draft.parentId else None
        now = timestamp()
        content = (draft.title, draft.body, draft.state, draft.projectId, draft.ticketId, parent_id, draft.sourceUrl, draft.startsOn, draft.endsOn)
        if existing:
            if existing.revision != data.revision:
                raise DomainError(409, "L’élément a changé. Relisez-le avant de le modifier.")
            record_id = existing.id
            repo.connection.execute("""UPDATE workspace_records SET title = ?, body = ?, state = ?, project_id = ?, ticket_id = ?,
                parent_id = ?, source_url = ?, starts_on = ?, ends_on = ?, updated_by = ?, updated_at = ?, revision = revision + 1
                WHERE workspace_id = ? AND id = ?""", (*content, self.user_id, now, self.workspace_id, record_id))
        else:
            record_id = str(uuid4())
            repo.connection.execute("""INSERT INTO workspace_records
                (title, body, state, project_id, ticket_id, parent_id, source_url, starts_on, ends_on, updated_by, updated_at,
                 workspace_id, id, kind, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (*content, self.user_id, now, self.workspace_id, record_id, kind, self.user_id))
        return self.get_in(repo, kind, record_id)

    def mark_helpful(self, repo, learning):
        if learning.archivedAt:
            raise DomainError(409, "Cette note est archivée.")
        repo.connection.execute("""INSERT INTO learning_reactions(record_id, user_id) VALUES (?, ?)
            ON CONFLICT (record_id, user_id) DO NOTHING""", (learning.id, self.user_id))
        return self.get_in(repo, "learning", learning.id)
