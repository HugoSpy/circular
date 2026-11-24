"""Present sensitive MCP actions to the account holder before performing them."""
import json
import time
from uuid import uuid4

from pydantic import BaseModel

from backend.app.db.session import timestamp
from backend.app.repositories.workspace import WorkspaceRepository
from backend.app.services.auth import verifier
from backend.app.services.docs import DocsService, require as require_document
from backend.app.services.document_shares import DocumentShares
from backend.app.services.github_reviews import GithubReviews, PullAction
from backend.app.services.mcp_policy import row_scopes, tool_scopes
from backend.app.services.records import RECORD_FAMILY, RecordsService
from backend.app.services.ticket_planning import lock_tickets, ticket_info
from backend.app.services.ticket_shares import TicketShares
from backend.app.services.workspace import DomainError, WorkspaceService


class ApprovalRequest(BaseModel):
    id: str
    url: str
    expiresAt: int


GITHUB_ACTIONS = {
    "comment": "Publier un commentaire de revue",
    "request_changes": "Demander des changements",
    "approve": "Approuver la revue",
    "merge": "Fusionner la pull request",
}


class Confirmations:
    def __init__(self, database, origin):
        self.database = database
        self.origin = origin

    def prepare(self, repo, token, action, payload):
        grant = repo.connection.execute("SELECT id FROM mcp_connections WHERE access_hash = ?", (verifier(token.token),)).fetchone()
        grant = WorkspaceService.require(grant, "Autorisation introuvable.")
        identifier, expires = str(uuid4()), int(time.time()) + 600
        repo.connection.execute("""INSERT INTO mcp_confirmations
            (id, connection_id, action, payload, state, expires_at, created_at) VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
            (identifier, grant["id"], action, json.dumps(payload), expires, timestamp()))
        return ApprovalRequest(id=identifier, url=f"{self.origin}/#mcp-action={identifier}", expiresAt=expires)

    def lookup(self, connection, identifier, user_id, *, lock=False):
        grant = connection.execute("""SELECT g.id, g.user_id, g.workspace_id, g.scope, g.family_scopes, g.refresh_expires_at,
                g.access_hash, w.name AS workspace
            FROM mcp_confirmations c JOIN mcp_connections g ON g.id = c.connection_id
            JOIN workspaces w ON w.id = g.workspace_id
            WHERE c.id = ? AND g.user_id = ? AND g.resource = ?""" +
            (" FOR UPDATE OF g" if lock and self.database.dialect == "postgresql" else ""),
            (identifier, user_id, f"{self.origin}/mcp")).fetchone()
        if not grant or grant["refresh_expires_at"] <= int(time.time()):
            raise DomainError(404, "Demande introuvable ou révoquée.")
        row = connection.execute("SELECT * FROM mcp_confirmations WHERE id = ? AND connection_id = ?",
                                 (identifier, grant["id"])).fetchone()
        row = WorkspaceService.require(row, "Demande introuvable ou révoquée.")
        family = {"github": "releases", "share_document": "docs",
                  "archive_record": RECORD_FAMILY.get(json.loads(row["payload"]).get("kind"))}.get(row["action"], "tickets")
        if family is None:
            raise DomainError(404, "Demande introuvable ou révoquée.")
        required = tool_scopes(family, write=True)
        if not required.issubset(row_scopes(grant)):
            raise DomainError(404, "Demande introuvable ou révoquée.")
        return row, grant

    def describe(self, row, grant):
        payload = json.loads(row["payload"])
        if row["action"] == "github":
            name = GITHUB_ACTIONS[payload["action"]]
            target = f'{payload["repository"]} · PR #{payload["number"]}'
            details = [f'Branche cible : {payload["base"]}', f'Révision : {payload["sha"]}']
            if payload["body"]:
                details.append(payload["body"])
        elif row["action"] == "share_ticket":
            name = "Retirer l’accès au ticket" if payload["remove"] else "Partager le ticket"
            target = payload["identifier"] + " · " + payload["title"]
            details = [f'Personne concernée : {payload["recipient"]}', "Ce partage porte sur la lecture de ce ticket et de sa discussion."]
        elif row["action"] == "share_document":
            name = "Retirer l’accès au document" if payload["remove"] else "Partager le document"
            target = payload["title"]
            details = [f'Personne concernée : {payload["recipient"]}', "Le partage porte sur ce document et ses pièces jointes."]
        elif row["action"] == "delete_comment":
            name = "Supprimer le commentaire"
            target = payload["identifier"] + " · " + payload["title"]
            details = [payload["comment"]]
        elif row["action"] == "archive_record":
            name = "Archiver l’élément"
            target = payload["title"]
            details = ["L’élément sera retiré des listes actives."]
        else:
            name = "Archiver le ticket"
            target = payload["identifier"] + " · " + payload["title"]
            details = ["Le ticket sera retiré des listes actives. Son historique reste consultable."]
        state = row["state"]
        if state == "pending" and row["expires_at"] <= int(time.time()):
            state = "expired"
        return {"id": row["id"], "workspace": grant["workspace"], "title": name,
                "target": target, "details": details, "state": state,
                "result": json.loads(row["result"]) if row["result"] else None}

    def get(self, identifier, user_id, token=None):
        with self.database.connect() as connection:
            row, grant = self.lookup(connection, identifier, user_id)
            if token and grant["access_hash"] != verifier(token.token):
                raise DomainError(404, "Demande introuvable ou révoquée.")
            payload = json.loads(row["payload"])
            if row["action"] == "archive_record":
                repo = WorkspaceRepository(connection, user_id, grant["workspace_id"])
                RecordsService(self.database, user_id, grant["workspace_id"]).get_in(repo, payload["kind"], payload["record_id"])
            elif row["action"] == "share_document":
                docs = DocsService(self.database, grant["workspace_id"], user_id)
                require_document(docs.repository_on(connection, "owner").page(payload["page_id"]))
            elif row["action"] != "github":
                repo = WorkspaceRepository(connection, user_id, grant["workspace_id"])
                WorkspaceService.require(repo.issue(payload["ticket_id"]), "Ticket introuvable.")
            else:
                GithubReviews(user_id, grant["workspace_id"]).configured_token(payload["repository"])
            return self.describe(row, grant)

    def decide(self, identifier, user_id, approved):
        remote = None
        with self.database.connect(write=True) as connection:
            if self.database.dialect == "postgresql":
                candidate, authorization = self.lookup(connection, identifier, user_id)
                if candidate["action"] in {"archive_record", "share_document"}:
                    connection.execute("SELECT id FROM workspaces WHERE id = ? FOR NO KEY UPDATE", (authorization["workspace_id"],)).fetchone()
            row, grant = self.lookup(connection, identifier, user_id, lock=True)
            if row["state"] != "pending" or row["expires_at"] <= int(time.time()):
                raise DomainError(409, "Cette demande a expiré ou a déjà été traitée.")
            if not approved:
                self.set_state(connection, identifier, "refused")
            elif row["action"] == "archive_record":
                payload = json.loads(row["payload"])
                repo = WorkspaceRepository(connection, user_id, grant["workspace_id"])
                records = RecordsService(self.database, user_id, grant["workspace_id"])
                target = records.archive_target(repo, payload["kind"], payload["record_id"])
                records.archive_in(repo, target, payload["revision"])
                self.set_state(connection, identifier, "done", {"message": "Élément archivé."})
            elif row["action"] == "share_document":
                payload = json.loads(row["payload"])
                docs = DocsService(self.database, grant["workspace_id"], user_id)
                repo = docs.repository_on(connection, "owner")
                page = require_document(repo.page(payload["page_id"]))
                docs._check_revision(page, payload["revision"])
                DocumentShares(self.database, user_id, grant["workspace_id"]).apply(repo, payload["page_id"], payload["recipient_id"], payload["remove"])
                message = "Accès au document retiré." if payload["remove"] else "Document partagé en lecture."
                self.set_state(connection, identifier, "done", {"message": message})
            elif row["action"] != "github":
                # PostgreSQL orders locks by workspace membership, grant, ticket and project in MCP writes.
                # This transaction already owns the grant. A direct grant lookup does not lock membership.
                repo = WorkspaceRepository(connection, user_id, grant["workspace_id"])
                payload = json.loads(row["payload"])
                ticket = lock_tickets(repo, {payload["ticket_id"]})[payload["ticket_id"]]
                if ticket["updatedAt"] != payload["revision"] or ticket_info(repo, ticket["id"]).archivedAt:
                    raise DomainError(409, "Ce ticket a changé. Demandez une nouvelle confirmation.")
                if row["action"] == "share_ticket":
                    TicketShares(self.database, user_id, grant["workspace_id"]).apply(repo, ticket, payload["recipient_id"], payload["remove"])
                    message = "Accès au ticket retiré." if payload["remove"] else "Ticket partagé en lecture."
                elif row["action"] == "delete_comment":
                    comment = WorkspaceService.require(repo.comment(ticket["id"], payload["comment_id"]), "Commentaire introuvable.")
                    if not comment["canDelete"]:
                        raise DomainError(403, "Vous ne pouvez pas supprimer ce commentaire.")
                    repo.delete_comment(ticket["id"], payload["comment_id"])
                    message = "Commentaire supprimé."
                else:
                    now = timestamp()
                    connection.execute("UPDATE issues SET archived_at = ?, updated_at = ? WHERE id = ?", (now, now, ticket["id"]))
                    repo.add_activity(ticket["id"], "updated", "Ticket archivé après confirmation dans Circular.")
                    message = "Ticket archivé."
                self.set_state(connection, identifier, "done", {"message": message, "url": payload["url"]})
            else:
                remote = (GithubReviews(user_id, grant["workspace_id"]), json.loads(row["payload"]))
                self.set_state(connection, identifier, "running")
        if remote:
            github, payload = remote
            payload.pop("base")
            try:
                state, result = "done", github.submit(PullAction.model_validate(payload))
            except DomainError as error:
                state = "uncertain" if error.status >= 500 else "failed"
                result = {"message": error.message}
            with self.database.connect(write=True) as connection:
                self.set_state(connection, identifier, state, result)
        return self.get(identifier, user_id)

    @staticmethod
    def set_state(connection, identifier, state, result=None):
        connection.execute("UPDATE mcp_confirmations SET state = ?, result = ? WHERE id = ?",
                           (state, json.dumps(result) if result else None, identifier))
