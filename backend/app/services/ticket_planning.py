"""Ticket assignments, estimates and relationships in the selected workspace."""
from typing import Literal

from pydantic import BaseModel

from backend.app.db.session import timestamp
from backend.app.repositories.workspace import WorkspaceRepository
from backend.app.services.mcp_operation import lock_target_project
from backend.app.services.scope import scoped_connection
from backend.app.services.workspace import DomainError, WorkspaceService

Relation = Literal["parent", "blocks", "related", "duplicate"]


class TicketRelation(BaseModel):
    kind: Relation
    direction: Literal["outgoing", "incoming"]
    ticketId: int
    identifier: str
    title: str


class TicketPlanning(BaseModel):
    assigneeId: int | None = None
    assigneeName: str | None = None
    estimate: int | None = None
    archivedAt: str | None = None
    relations: list[TicketRelation]


def ticket_info(repo: WorkspaceRepository, ticket_id: int) -> TicketPlanning:
    values = repo.connection.execute("SELECT assignee_id AS assigneeId, estimate, archived_at AS archivedAt FROM issues WHERE id = ?",
                                     (ticket_id,)).fetchone()
    access, parameters = repo.access_clause()
    relations = repo.connection.execute(f"""SELECT i.id AS ticketId, i.identifier, i.title, r.kind,
        CASE WHEN r.issue_id = ? THEN 'outgoing' ELSE 'incoming' END AS direction
        FROM issue_relations r JOIN issues i ON i.id = CASE WHEN r.issue_id = ? THEN r.target_id ELSE r.issue_id END
        JOIN projects p ON p.id = i.project_id
        WHERE (r.issue_id = ? OR r.target_id = ?) AND {access} ORDER BY i.id, r.kind""",
        [ticket_id, ticket_id, ticket_id, ticket_id, *parameters]).fetchall()
    assignee = repo.person(values["assigneeId"])
    return TicketPlanning(**dict(values), assigneeName=assignee["displayName"] if assignee else None,
                          relations=[TicketRelation.model_validate(dict(row)) for row in relations])


def get_ticket_planning(service: WorkspaceService, ticket_id: int) -> TicketPlanning:
    with scoped_connection(service.database, service.user_id, service.workspace_id) as connection:
        repo = WorkspaceRepository(connection, service.user_id, service.workspace_id)
        service.require(repo.issue(ticket_id), "Ticket introuvable.")
        return ticket_info(repo, ticket_id)


def check_assignee(repo: WorkspaceRepository, user_id: int | None, project_id: int) -> None:
    if user_id is None:
        return
    people = WorkspaceRepository(repo.connection, user_id, repo.workspace_id)
    lock = " FOR KEY SHARE" if getattr(repo.connection, "dialect", "sqlite") == "postgresql" else ""
    membership = repo.connection.execute("SELECT user_id FROM workspace_members WHERE workspace_id = ? AND user_id = ?" + lock,
                                         (repo.workspace_id, user_id)).fetchone()
    if lock:
        repo.connection.execute("SELECT user_id FROM project_members WHERE project_id = ? AND user_id = ?" + lock,
                                (project_id, user_id)).fetchone()
    if not membership or not people.project(project_id):
        raise DomainError(422, "Cette personne doit avoir accès au projet.")


def update_planning(repo: WorkspaceRepository, issue_id: int, changes: dict) -> None:
    if not changes:
        return
    current = ticket_info(repo, issue_id)
    assignee = changes.get("assigneeId", current.assigneeId)
    estimate = changes.get("estimate", current.estimate)
    if (assignee, estimate) == (current.assigneeId, current.estimate):
        return
    repo.connection.execute("UPDATE issues SET assignee_id = ?, estimate = ?, updated_at = ? WHERE id = ?",
                            (assignee, estimate, timestamp(), issue_id))
    repo.add_activity(issue_id, "updated", "Responsable ou estimation du ticket modifiés.")


def lock_tickets(repo: WorkspaceRepository, ids: set[int]) -> dict[int, dict]:
    tickets = {}
    for issue_id in sorted(ids):
        repo.lock_issue(issue_id)
        tickets[issue_id] = WorkspaceService.require(repo.issue(issue_id), "Ticket introuvable.")
    for project_id in sorted({ticket["projectId"] for ticket in tickets.values()}):
        lock_target_project(repo, project_id)
    return tickets


def update_relation(repo, issue_id: int, target_id: int, kind: Relation, remove: bool) -> bool:
    if issue_id == target_id:
        raise DomainError(409, "Un ticket ne peut pas être relié à lui-même.")
    if kind == "related":
        issue_id, target_id = sorted((issue_id, target_id))
    if remove:
        changed = repo.connection.execute("DELETE FROM issue_relations WHERE issue_id = ? AND target_id = ? AND kind = ?",
                                          (issue_id, target_id, kind)).rowcount
    else:
        loop = kind != "related" and repo.connection.execute("""WITH RECURSIVE chain(id) AS (
            SELECT CAST(? AS BIGINT)
            UNION
            SELECT r.target_id FROM issue_relations r JOIN chain c ON c.id = r.issue_id WHERE r.kind = ?
        ) SELECT 1 FROM chain WHERE id = ?""", (target_id, kind, issue_id)).fetchone()
        if loop:
            raise DomainError(409, "Cette relation crée une boucle entre les tickets.")
        if kind in {"parent", "duplicate"}:
            repo.connection.execute("DELETE FROM issue_relations WHERE issue_id = ? AND kind = ? AND target_id <> ?",
                                    (issue_id, kind, target_id))
        changed = repo.connection.execute("""INSERT INTO issue_relations (issue_id, target_id, kind)
            VALUES (?, ?, ?) ON CONFLICT (issue_id, target_id, kind) DO NOTHING""", (issue_id, target_id, kind)).rowcount
    if changed:
        repo.add_activity(issue_id, "updated", "Relation de ticket modifiée.")
    return bool(changed)
