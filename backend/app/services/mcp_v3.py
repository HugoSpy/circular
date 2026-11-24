"""MCP adapters for the V3 capabilities."""
import sqlite3
from base64 import b64decode, b64encode
from binascii import Error as Base64Error
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Annotated, Literal
from uuid import UUID, uuid4

from anyio import to_thread
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, StringConstraints

from backend.app.db.session import Database
from backend.app.repositories.workspace import WorkspaceRepository
from backend.app.repositories.preferences import PreferencesRepository
from backend.app.repositories.sharing import SharingRepository
from backend.app.schemas.responses import Activity, Comment, Issue, Label, Project
from backend.app.schemas.docs import CommentInput, PageFromTemplate, PagePlacement, PageSave
from backend.app.schemas.records import RecordChange
from backend.app.schemas.workspace import CommentCreate, IssueCreate, IssueUpdate, LabelCreate, LabelIds, LabelUpdate, PositiveId, Priority, ProjectCreate, ProjectUpdate, Status, Title
from backend.app.services.docs import DocsService, require as require_document
from backend.app.services.document_shares import DocumentShares
from backend.app.services.github_reviews import GithubReviews, PullAction, PullFiles, RepositoryName
from backend.app.services.mcp_confirmations import ApprovalRequest, Confirmations
from backend.app.services.mcp_operation import lock_target_project, principal, transact
from backend.app.services.mcp_policy import scope_string, tool_scopes
from backend.app.services.mcp_tools import ADDITIVE, READ_ONLY, Cursor, Limit, Page, TicketSummary, WriteKey, oauth_metadata, ticket_url
from backend.app.services.records import Record, RecordPage, RecordsService
from backend.app.services.scope import scoped_connection
from backend.app.services.ticket_planning import Relation, TicketPlanning, check_assignee, lock_tickets, ticket_info, update_planning, update_relation
from backend.app.services.ticket_shares import TicketShares
from backend.app.services.workspace import DomainError

TicketReference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Revision = Annotated[str, StringConstraints(min_length=1, max_length=40)]
PlanningKind = Literal["initiative", "milestone", "cycle", "update", "triage"]
CustomerKind = Literal["customer", "request"]
ReleaseKind = Literal["pipeline", "release", "release_note", "review_criterion", "pull_link"]
ContextKind = Literal["instruction", "learning", "friction"]
RecordQuery = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
RecordCursor = Annotated[str, StringConstraints(max_length=36)]

MUTATION = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)


class TicketContext(BaseModel):
    ticket: Issue
    comments: list[Comment]
    activity: list[Activity]
    planning: TicketPlanning | None = None


class UpdatedTicket(BaseModel):
    ticket: Issue
    url: str


class TicketUpdate(IssueUpdate):
    nullable_fields = {"dueDate", "assigneeId", "estimate"}
    assigneeId: PositiveId | None = None
    estimate: int | None = Field(default=None, ge=0, le=1000)


class TicketRelationResult(BaseModel):
    changed: bool
    planning: TicketPlanning


class ProjectPeople(BaseModel):
    items: list[dict]


class WorkspaceIdentity(BaseModel):
    id: int
    name: str
    slug: str
    userId: int


class SharedTickets(BaseModel):
    items: list[dict]
    nextCursor: int | None


class DocumentSummary(BaseModel):
    id: str
    title: str


class DocumentResult(DocumentSummary):
    revision: int


class DocumentDetail(DocumentResult):
    markdown: str
    parentId: str | None = None
    collectionId: str | None = None


class DocumentSearch(BaseModel):
    items: list[DocumentSummary]


class DocumentItems(BaseModel):
    items: list[dict]
    nextCursor: str | None = None


class WorkspaceMatches(BaseModel):
    tickets: list[TicketSummary]
    projects: list[Project]
    documents: list[DocumentSummary]


class DocumentPatch(BaseModel):
    revision: PositiveId
    oldText: Annotated[str, StringConstraints(min_length=1, max_length=10000)]
    newText: Annotated[str, StringConstraints(max_length=10000)]


class DocumentUpload(BaseModel):
    revision: PositiveId
    name: Annotated[str, StringConstraints(min_length=1, max_length=240)]
    contentBase64: Annotated[str, StringConstraints(min_length=4, max_length=87384)]
    image: bool = False


class DocumentAttachment(BaseModel):
    id: str
    name: str
    mediaType: str
    size: int
    contentBase64: str | None = None


class NotificationChange(BaseModel):
    action: Literal["read", "snooze", "unsnooze"]
    hours: int | None = Field(default=None, ge=1, le=168)


class NotificationResult(BaseModel):
    id: str
    snoozedUntil: str | None = None


class AttachedDocument(DocumentResult):
    assetId: str


class ApprovalStatus(BaseModel):
    state: str
    result: dict | None


class DocumentComment(BaseModel):
    id: str
    pageId: str


def document_id(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as error:
        raise DomainError(404, "Document introuvable.") from error


def ticket_reference(reference: str, origin: str) -> str:
    from urllib.parse import parse_qs, urlsplit

    if reference.startswith(("http://", "https://")):
        try:
            url = urlsplit(reference)
        except ValueError as error:
            raise DomainError(404, "Ticket introuvable.") from error
        if f"{url.scheme}://{url.netloc}" != origin or url.path != "/":
            raise DomainError(404, "Ticket introuvable.")
        params = parse_qs(url.query)
        values = params.get("issue", [])
        reference = values[0] if len(values) == 1 else ""
    return reference


def resolve_ticket(repo: WorkspaceRepository, reference: str) -> dict | None:
    if reference.isascii() and reference.isdigit() and 0 < int(reference) <= 9223372036854775807:
        return repo.issue(int(reference))
    access, values = repo.access_clause()
    row = repo.connection.execute(f"""SELECT i.id FROM issues i JOIN projects p ON p.id = i.project_id
        WHERE i.identifier = ? AND {access}""", [reference.upper(), *values]).fetchone()
    return repo.issue(row["id"]) if row else None


def register_v3(server: FastMCP, database: Database, origin: str, requirements: dict[str, set[str]]) -> None:
    approvals = Confirmations(database, origin)
    def register(family: str, title: str, *, annotations=READ_ONLY):
        required = tool_scopes(family, write=not annotations.readOnlyHint)

        def attach(handler):
            requirements[handler.__name__] = required

            @wraps(handler)
            async def invoke(*args, **kwargs):
                def execute():
                    principal(database, required)
                    return handler(*args, **kwargs)
                try:
                    return await to_thread.run_sync(execute)
                except DomainError as error:
                    raise ToolError(error.message) from error

            server.tool(title=title, annotations=annotations, meta=oauth_metadata(scope_string(required)))(invoke)
            return invoke

        return attach

    def workspace(family: str):
        return principal(database, tool_scopes(family))[1]

    def records(family: str):
        service = workspace(family)
        return RecordsService(database, service.user_id, service.workspace_id)

    def save_record(family, kind, change, request_key):
        service = records(family)
        return transact(database, tool_scopes(family, write=True), "save_workspace_record",
                        {"kind": kind, "data": change.model_dump(mode="json")}, request_key, Record,
                        lambda _service, repo: service.target(repo, kind, change),
                        lambda _service, repo, existing, _slug: service.save_in(repo, kind, change, existing), lock_workspace=True)

    def archive_record(family, kind, record_id, revision, request_key):
        required = tool_scopes(family, write=True)
        token, _service = principal(database, required)
        service = records(family)
        identifier = document_id(record_id)

        def write(_service, repo, record, _slug):
            if record.revision != revision or record.archivedAt:
                raise DomainError(409, "L’élément a changé ou est déjà archivé.")
            return approvals.prepare(repo, token, "archive_record", {"record_id": identifier, "revision": revision,
                                      "kind": kind, "title": record.title})

        return transact(database, required, "prepare_record_archive", {"kind": kind, "id": identifier, "revision": revision},
                        request_key, ApprovalRequest, lambda _service, repo: service.archive_target(repo, kind, identifier), write,
                        lock_workspace=True)

    def docs_service():
        service = workspace("docs")
        return DocsService(database, service.workspace_id, service.user_id)

    def document_shares():
        service = workspace("docs")
        return DocumentShares(database, service.user_id, service.workspace_id)

    def write_document(action, data, key, operation, page_id=None, result_type=DocumentResult, permission="editor"):
        docs = docs_service()

        def validate(_service, repo):
            document_repo = docs.repository_on(repo.connection, permission)
            if page_id:
                require_document(document_repo.page(page_id))
            return document_repo

        def write(_service, _repo, document_repo, _slug):
            return result_type.model_validate(operation(docs, document_repo))

        return transact(database, tool_scopes("docs", write=True), action,
                        {"id": page_id, "data": data.model_dump(mode="json")}, key,
                        result_type, validate, write, lock_workspace=True)

    @register("tickets", "Lire la discussion et l’historique d’un ticket")
    def get_ticket_context(reference: TicketReference) -> TicketContext:
        """Retrouve un ticket accessible par identifiant, numéro ou lien Circular."""
        service = workspace("tickets")
        with scoped_connection(database, service.user_id, service.workspace_id) as connection:
            repo = WorkspaceRepository(connection, service.user_id, service.workspace_id)
            reference = ticket_reference(reference, origin)
            ticket = resolve_ticket(repo, reference)
            if not ticket:
                shared = TicketShares(database, service.user_id, service.workspace_id).shared(repo, reference)
                return TicketContext.model_validate(service.require(shared, "Ticket introuvable."))
            issue_id = ticket["id"]
            return TicketContext(ticket=ticket, comments=repo.comments(issue_id), activity=repo.activity(issue_id), planning=ticket_info(repo, issue_id))

    @register("tickets", "Filtrer les tickets de l’espace")
    def filter_tickets(query: RecordQuery = "", project_id: PositiveId | None = None, assignee_id: PositiveId | None = None,
                       label_ids: LabelIds | None = None, status: Status | None = None, priority: Priority | None = None,
                       include_archived: bool = False, limit: Limit = 20, cursor: Cursor = 0) -> Page[TicketSummary]:
        """Combine une recherche, un projet, un responsable, des étiquettes, un statut et une priorité."""
        service = workspace("tickets")
        filters = {"q": query, "projectId": project_id, "assigneeId": assignee_id, "labelIds": label_ids,
                   "status": status, "priority": priority, "includeArchived": include_archived}
        rows = service.issues(filters, limit=limit + 1, after_id=cursor)
        return Page[TicketSummary](items=rows[:limit], nextCursor=rows[limit - 1]["id"] if len(rows) > limit else None)

    @register("tickets", "Lister les tickets partagés avec vous")
    def list_shared_tickets(cursor: Cursor = 0, limit: Limit = 20) -> SharedTickets:
        service = workspace("tickets")
        return SharedTickets.model_validate(TicketShares(database, service.user_id, service.workspace_id).list(cursor, limit))

    @register("tickets", "Mettre à jour un ticket", annotations=MUTATION)
    def update_ticket(ticket_id: PositiveId, expected_updated_at: Revision, changes: TicketUpdate, request_key: WriteKey) -> UpdatedTicket:
        """Modifie uniquement les champs fournis. Transmets la date de modification obtenue à la lecture et garde la même clé en cas de relance."""
        data = changes.model_dump(exclude_unset=True)
        if "isFavorite" in data:
            raise DomainError(422, "Les favoris se gèrent dans Circular.")

        def validate(service, repo):
            repo.lock_issue(ticket_id)
            ticket = service.require(repo.issue(ticket_id), "Ticket introuvable.")
            for project_id in sorted({ticket["projectId"], data.get("projectId", ticket["projectId"])}):
                lock_target_project(repo, project_id)
            return ticket

        def write(service, repo, ticket, slug):
            if ticket["updatedAt"] != expected_updated_at:
                raise DomainError(409, "Le ticket a changé. Relisez-le avant de le modifier.")
            core = {key: value for key, value in data.items() if key not in {"assigneeId", "estimate"}}
            planning = {key: value for key, value in data.items() if key in {"assigneeId", "estimate"}}
            if "assigneeId" in planning or "projectId" in core:
                assignee = planning.get("assigneeId", ticket_info(repo, ticket_id).assigneeId)
                check_assignee(repo, assignee, core.get("projectId", ticket["projectId"]))
            if core:
                service.update_issue_in(repo, ticket, core)
            update_planning(repo, ticket_id, planning)
            return UpdatedTicket(ticket=repo.issue(ticket_id), url=ticket_url(origin, slug, ticket_id))

        arguments = {"ticket_id": ticket_id, "expected_updated_at": expected_updated_at, "changes": data}
        return transact(database, tool_scopes("tickets", write=True), "update_ticket",
                        arguments, request_key, UpdatedTicket, validate, write)

    @register("tickets", "Relier deux tickets", annotations=MUTATION)
    def relate_tickets(ticket_id: PositiveId, target_id: PositiveId, relation: Relation, request_key: WriteKey,
                       remove: bool = False) -> TicketRelationResult:
        """Ajoute ou retire un parent, une dépendance bloquante, un lien ou un doublon."""
        def write(_service, repo, _targets, _slug):
            changed = update_relation(repo, ticket_id, target_id, relation, remove)
            return TicketRelationResult(changed=changed, planning=ticket_info(repo, ticket_id))

        return transact(database, tool_scopes("tickets", write=True), "relate_tickets",
                        {"ticket": ticket_id, "target": target_id, "relation": relation, "remove": remove}, request_key,
                        TicketRelationResult, lambda _service, repo: lock_tickets(repo, {ticket_id, target_id}), write, lock_workspace=True)

    @register("tickets", "Dupliquer un ticket", annotations=ADDITIVE)
    def duplicate_ticket(ticket_id: PositiveId, request_key: WriteKey) -> UpdatedTicket:
        def write(service, repo, original, slug):
            copied = service.duplicate_issue_in(repo, original)
            return UpdatedTicket(ticket=copied, url=ticket_url(origin, slug, copied["id"]))

        return transact(database, tool_scopes("tickets", write=True), "duplicate_ticket", {"ticket_id": ticket_id}, request_key,
                        UpdatedTicket, lambda _service, repo: lock_tickets(repo, {ticket_id})[ticket_id], write)

    @register("tickets", "Consulter les modèles de tickets")
    def list_ticket_templates() -> ProjectPeople:
        service = workspace("tickets")
        with scoped_connection(database, service.user_id, service.workspace_id) as connection:
            return ProjectPeople(items=PreferencesRepository(connection, service.user_id, service.workspace_id).templates())

    @register("tickets", "Créer un ticket depuis un modèle", annotations=ADDITIVE)
    def create_ticket_from_template(template_id: PositiveId, project_id: PositiveId, request_key: WriteKey,
                                    title: Title | None = None) -> UpdatedTicket:
        def validate(service, repo):
            lock_target_project(repo, project_id)
            template = PreferencesRepository(repo.connection, service.user_id, service.workspace_id).template(template_id)
            return service.require(template, "Modèle introuvable.")

        def write(service, repo, template, slug):
            data = IssueCreate(projectId=project_id, title=title or template["title"], description=template["description"],
                               status=template["status"], priority=template["priority"], labelIds=template["labelIds"])
            created = service.create_issue_in(repo, data.model_dump())
            return UpdatedTicket(ticket=created, url=ticket_url(origin, slug, created["id"]))

        return transact(database, tool_scopes("tickets", write=True), "create_ticket_from_template",
                        {"template": template_id, "project": project_id, "title": title}, request_key, UpdatedTicket, validate, write)

    @register("tickets", "Créer un sous-ticket", annotations=ADDITIVE)
    def create_subticket(parent_id: PositiveId, title: Title, request_key: WriteKey) -> UpdatedTicket:
        def write(service, repo, parent, slug):
            created = service.create_issue_in(repo, IssueCreate(projectId=parent["projectId"], title=title).model_dump())
            update_relation(repo, created["id"], parent_id, "parent", False)
            return UpdatedTicket(ticket=created, url=ticket_url(origin, slug, created["id"]))

        return transact(database, tool_scopes("tickets", write=True), "create_subticket", {"parent": parent_id, "title": title},
                        request_key, UpdatedTicket, lambda _service, repo: lock_tickets(repo, {parent_id})[parent_id], write, lock_workspace=True)

    @register("tickets", "Modifier un commentaire de ticket", annotations=MUTATION)
    def update_ticket_comment(ticket_id: PositiveId, comment_id: PositiveId, expected_updated_at: Revision,
                              comment: CommentCreate, request_key: WriteKey) -> Comment:
        def validate(service, repo):
            ticket = lock_tickets(repo, {ticket_id})[ticket_id]
            current = service.require(repo.comment(ticket_id, comment_id), "Commentaire introuvable.")
            if not current["canEdit"]:
                raise DomainError(403, "Seul l’auteur peut modifier ce commentaire.")
            return ticket

        def write(_service, repo, ticket, _slug):
            if ticket["updatedAt"] != expected_updated_at:
                raise DomainError(409, "Le ticket a changé. Relisez la discussion.")
            return Comment.model_validate(repo.update_comment(ticket_id, comment_id, comment.body))

        return transact(database, tool_scopes("tickets", write=True), "update_ticket_comment",
                        {"ticket": ticket_id, "comment": comment_id, "revision": expected_updated_at, "body": comment.body},
                        request_key, Comment, validate, write)

    @register("tickets", "Demander confirmation pour archiver un ticket", annotations=MUTATION)
    def prepare_ticket_archive(ticket_id: PositiveId, expected_updated_at: Revision, request_key: WriteKey) -> ApprovalRequest:
        """Transmets le lien de confirmation à l’utilisateur. Le ticket est archivé après confirmation dans Circular."""
        required = tool_scopes("tickets", write=True)
        token, _service = principal(database, required)

        def write(_service, repo, ticket, slug):
            if ticket["updatedAt"] != expected_updated_at or ticket_info(repo, ticket_id).archivedAt:
                raise DomainError(409, "Le ticket a changé ou est déjà archivé.")
            return approvals.prepare(repo, token, "archive_ticket", {"ticket_id": ticket_id, "revision": expected_updated_at,
                "title": ticket["title"], "identifier": ticket["identifier"], "url": ticket_url(origin, slug, ticket_id)})

        return transact(database, required, "prepare_ticket_archive", {"id": ticket_id, "revision": expected_updated_at},
                        request_key, ApprovalRequest, lambda _service, repo: lock_tickets(repo, {ticket_id})[ticket_id], write)

    @register("tickets", "Demander confirmation pour partager un ticket", annotations=MUTATION)
    def prepare_ticket_share(ticket_id: PositiveId, recipient_id: PositiveId, expected_updated_at: Revision,
                             request_key: WriteKey, remove: bool = False) -> ApprovalRequest:
        """Donne ou retire un accès en lecture après confirmation par le propriétaire dans Circular."""
        required = tool_scopes("tickets", write=True)
        token, _service = principal(database, required)

        def validate(service, repo):
            ticket = lock_tickets(repo, {ticket_id})[ticket_id]
            service.owner(repo.project(ticket["projectId"]))
            recipient = TicketShares.recipient(repo, recipient_id)
            return ticket, recipient["name"]

        def write(_service, repo, target, slug):
            ticket, recipient = target
            if ticket["updatedAt"] != expected_updated_at or ticket_info(repo, ticket_id).archivedAt:
                raise DomainError(409, "Le ticket a changé ou est archivé.")
            return approvals.prepare(repo, token, "share_ticket", {"ticket_id": ticket_id, "revision": expected_updated_at,
                "title": ticket["title"], "identifier": ticket["identifier"], "url": ticket_url(origin, slug, ticket_id),
                "recipient": recipient, "recipient_id": recipient_id, "remove": remove})

        return transact(database, required, "prepare_ticket_share", {"id": ticket_id, "revision": expected_updated_at,
                        "recipient": recipient_id, "remove": remove}, request_key, ApprovalRequest, validate, write)

    @register("tickets", "Demander confirmation pour supprimer un commentaire", annotations=MUTATION)
    def prepare_comment_deletion(ticket_id: PositiveId, comment_id: PositiveId, expected_updated_at: Revision,
                                 request_key: WriteKey) -> ApprovalRequest:
        required = tool_scopes("tickets", write=True)
        token, _service = principal(database, required)

        def validate(service, repo):
            ticket = lock_tickets(repo, {ticket_id})[ticket_id]
            comment = service.require(repo.comment(ticket_id, comment_id), "Commentaire introuvable.")
            if not comment["canDelete"]:
                raise DomainError(403, "Vous ne pouvez pas supprimer ce commentaire.")
            return ticket, comment

        def write(_service, repo, values, slug):
            ticket, comment = values
            if ticket["updatedAt"] != expected_updated_at:
                raise DomainError(409, "Le ticket a changé. Relisez la discussion.")
            return approvals.prepare(repo, token, "delete_comment", {"ticket_id": ticket_id, "revision": expected_updated_at,
                "title": ticket["title"], "identifier": ticket["identifier"], "url": ticket_url(origin, slug, ticket_id),
                "comment_id": comment_id, "comment": comment["body"]})

        return transact(database, required, "prepare_comment_deletion", {"ticket": ticket_id, "comment": comment_id,
                        "revision": expected_updated_at}, request_key, ApprovalRequest, validate, write)

    @register("tickets", "Consulter l’état d’une confirmation de ticket")
    def get_ticket_action_status(action_id: str) -> ApprovalStatus:
        token, service = principal(database, tool_scopes("tickets"))
        return ApprovalStatus.model_validate(approvals.get(document_id(action_id), service.user_id, token))

    @register("projects", "Consulter un projet")
    def get_project(project_id: PositiveId) -> Project:
        service = workspace("projects")
        with scoped_connection(database, service.user_id, service.workspace_id) as connection:
            repo = WorkspaceRepository(connection, service.user_id, service.workspace_id)
            return Project.model_validate(service.require(repo.project(project_id), "Projet introuvable."))

    @register("projects", "Consulter les membres d’un projet")
    def list_project_members(project_id: PositiveId) -> ProjectPeople:
        service = workspace("projects")
        with scoped_connection(database, service.user_id, service.workspace_id) as connection:
            repo = WorkspaceRepository(connection, service.user_id, service.workspace_id)
            service.require(repo.project(project_id), "Projet introuvable.")
            return ProjectPeople(items=[{key: row[key] for key in ("id", "username", "role")} for row in SharingRepository(connection).members(project_id)])

    @register("projects", "Consulter les vues enregistrées")
    def list_saved_views() -> ProjectPeople:
        service = workspace("projects")
        with scoped_connection(database, service.user_id, service.workspace_id) as connection:
            return ProjectPeople(items=PreferencesRepository(connection, service.user_id, service.workspace_id).views())

    @register("projects", "Consulter les étiquettes")
    def list_labels() -> ProjectPeople:
        return ProjectPeople(items=workspace("projects").labels())

    @register("projects", "Créer une étiquette", annotations=ADDITIVE)
    def create_label(label: LabelCreate, request_key: WriteKey) -> Label:
        data = label.model_dump()

        def write(_service, repo, _target, _slug):
            if repo.label_by_name(data["name"]):
                raise DomainError(409, "Une étiquette porte déjà ce nom.")
            return Label.model_validate(repo.create_label(data))

        return transact(database, tool_scopes("projects", write=True), "create_label", data, request_key, Label,
                        lambda _service, _repo: None, write, lock_workspace=True)

    @register("projects", "Mettre à jour une étiquette", annotations=MUTATION)
    def update_label(label_id: PositiveId, changes: LabelUpdate, request_key: WriteKey) -> Label:
        data = changes.model_dump(exclude_unset=True)

        def validate(service, repo):
            label = service.require(repo.label(label_id), "Étiquette introuvable.")
            if not label["canEdit"]:
                raise DomainError(403, "Seul le créateur peut modifier cette étiquette.")
            return label

        def write(_service, repo, label, _slug):
            if "name" in data:
                same_name = repo.label_by_name(data["name"])
                if same_name and same_name["id"] != label_id:
                    raise DomainError(409, "Une étiquette porte déjà ce nom.")
            return Label.model_validate(repo.update_label(label_id, {**label, **data}))

        return transact(database, tool_scopes("projects", write=True), "update_label", {"id": label_id, "changes": data},
                        request_key, Label, validate, write, lock_workspace=True)

    @register("projects", "Créer un projet", annotations=ADDITIVE)
    def create_project(project: ProjectCreate, request_key: WriteKey) -> Project:
        """Crée un projet dans l’espace autorisé. Utilise une clé distincte pour chaque création."""
        data = project.model_dump()

        def validate(_service, repo):
            if repo.container_role() not in {"owner", "member"}:
                raise DomainError(403, "Les invités ne peuvent pas créer de projet.")

        try:
            return transact(database, tool_scopes("projects", write=True), "create_project", data, request_key, Project,
                            validate, lambda service, repo, _target, _slug: Project.model_validate(service.create_project_in(repo, data)))
        except sqlite3.IntegrityError as error:
            raise DomainError(409, "Ce préfixe de projet existe déjà.") from error

    @register("projects", "Mettre à jour un projet", annotations=MUTATION)
    def update_project(project_id: PositiveId, changes: ProjectUpdate, request_key: WriteKey) -> Project:
        data = changes.model_dump(exclude_unset=True)

        def validate(service, repo):
            project = lock_target_project(repo, project_id, shared=False)
            service.owner(project)
            return project

        def write(_service, repo, project, _slug):
            return Project.model_validate(repo.update_project(project_id, {**project, **data}))

        return transact(database, tool_scopes("projects", write=True), "update_project",
                        {"project_id": project_id, "changes": data}, request_key, Project, validate, write)

    @register("docs", "Rechercher des documents")
    def search_documents(query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]) -> DocumentSearch:
        return DocumentSearch(items=docs_service().search(query))

    @register("docs", "Rechercher dans les tickets, projets et documents")
    def search_workspace(query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)],
                         limit: Limit = 10) -> WorkspaceMatches:
        service = workspace("docs")
        permitted_docs = docs_service().search(query)[:limit]
        with scoped_connection(database, service.user_id, service.workspace_id) as connection:
            repo = WorkspaceRepository(connection, service.user_id, service.workspace_id)
            return WorkspaceMatches(tickets=repo.issues({"q": query}, limit=limit),
                                    projects=repo.projects(limit=limit, query_text=query), documents=permitted_docs)

    @register("docs", "Consulter un document")
    def get_document(page_id: str) -> DocumentDetail:
        identifier = document_id(page_id)
        try:
            return DocumentDetail.model_validate(docs_service().page(identifier))
        except DomainError as error:
            if error.status != 404:
                raise
        return DocumentDetail.model_validate(document_shares().get(identifier))

    @register("docs", "Lister les documents partagés avec vous")
    def list_shared_documents(cursor: RecordCursor = "") -> DocumentItems:
        result = document_shares().list(cursor)
        return DocumentItems(items=result["items"], nextCursor=result["nextCursor"])

    @register("docs", "Créer un document", annotations=ADDITIVE)
    def create_document(page: PageFromTemplate, request_key: WriteKey) -> DocumentResult:
        return write_document("create_document", page, request_key, lambda docs, repo: docs.create_page_in(repo, page))

    @register("docs", "Modifier le Markdown d’un document", annotations=MUTATION)
    def update_document(page_id: str, change: PageSave, request_key: WriteKey) -> DocumentResult:
        """Enregistre le Markdown à partir de la révision consultée. Conserve les parties du document que tu ne dois pas modifier."""
        identifier = document_id(page_id)
        return write_document("update_document", change, request_key,
                              lambda docs, repo: docs.save_page_in(repo, identifier, change), identifier)

    @register("docs", "Corriger un passage d’un document", annotations=MUTATION)
    def patch_document(page_id: str, change: DocumentPatch, request_key: WriteKey) -> DocumentResult:
        """Remplace un passage qui apparaît une seule fois dans la révision consultée."""
        identifier = document_id(page_id)

        def patch(docs, repo):
            current = require_document(repo.page(identifier))
            docs._check_revision(current, change.revision)
            if current["markdown"].count(change.oldText) != 1:
                raise DomainError(409, "Le passage doit être présent une seule fois dans le document.")
            markdown = current["markdown"].replace(change.oldText, change.newText, 1)
            return docs.save_page_in(repo, identifier, PageSave(revision=change.revision, markdown=markdown))

        return write_document("patch_document", change, request_key, patch, identifier)

    @register("docs", "Déplacer ou renommer un document", annotations=MUTATION)
    def move_document(page_id: str, change: PagePlacement, request_key: WriteKey) -> DocumentResult:
        identifier = document_id(page_id)
        if change.revision is None:
            raise DomainError(422, "La révision du document est requise.")
        return write_document("move_document", change, request_key,
                              lambda docs, repo: docs.place_page_in(repo, identifier, change), identifier)

    @register("docs", "Consulter les commentaires d’un document")
    def list_document_comments(page_id: str) -> DocumentItems:
        return DocumentItems(items=docs_service().comments(document_id(page_id))["items"])

    @register("docs", "Commenter un document", annotations=ADDITIVE)
    def comment_document(page_id: str, comment: CommentInput, request_key: WriteKey) -> DocumentComment:
        identifier = document_id(page_id)

        def create(docs, repo):
            comment_id = str(uuid4())
            docs.write_comment_in(repo, identifier, comment_id, comment, create=True)
            return {"id": comment_id, "pageId": identifier}

        return write_document("comment_document", comment, request_key, create, identifier, DocumentComment)

    @register("docs", "Ajouter un fichier à un document", annotations=ADDITIVE)
    def attach_document_file(page_id: str, file: DocumentUpload, request_key: WriteKey) -> AttachedDocument:
        """Ajoute un fichier PDF ou une image de 64 Kio maximum au document."""
        identifier = document_id(page_id)
        try:
            content = b64decode(file.contentBase64, validate=True)
        except (ValueError, Base64Error) as error:
            raise DomainError(422, "Contenu Base64 invalide.") from error
        if len(content) > 65536:
            raise DomainError(413, "Ce fichier dépasse la limite de 64 Kio du connecteur MCP.")

        def attach(docs, repo):
            current = require_document(repo.page(identifier))
            docs._check_revision(current, file.revision)
            asset_id = str(uuid4())
            docs.upload_asset_in(repo, identifier, asset_id, file.name, content, file.image)
            link = f"[Pièce jointe](/attachments/{asset_id})"
            markdown = current["markdown"].rstrip() + "\n\n" + ("!" if file.image else "") + link
            if len(markdown) > 100000:
                raise DomainError(413, "Le document dépasse la limite de taille.")
            saved = docs.save_page_in(repo, identifier, PageSave(revision=file.revision, markdown=markdown))
            return {**saved, "assetId": asset_id}

        return write_document("attach_document_file", file, request_key, attach, identifier, AttachedDocument)

    @register("docs", "Consulter une pièce jointe d’un document")
    def get_document_file(asset_id: str, include_content: bool = False) -> DocumentAttachment:
        identifier = document_id(asset_id)
        try:
            asset = docs_service().asset(identifier)
        except DomainError as error:
            if error.status != 404:
                raise
            asset = document_shares().asset(identifier)
        if include_content and asset["size_bytes"] > 65536:
            raise DomainError(413, "Le fichier dépasse la limite de lecture de 64 Kio du connecteur MCP.")
        content = b64encode(bytes(asset["content"])).decode("ascii") if include_content else None
        return DocumentAttachment(id=asset["id"], name=asset["name"], mediaType=asset["media_type"], size=asset["size_bytes"], contentBase64=content)

    @register("docs", "Consulter les notifications Docs")
    def list_document_notifications() -> DocumentItems:
        return DocumentItems(items=docs_service().notifications()[:50])

    @register("docs", "Marquer ou reporter une notification Docs", annotations=MUTATION)
    def update_document_notification(comment_id: str, change: NotificationChange, request_key: WriteKey) -> NotificationResult:
        identifier = document_id(comment_id)
        if (change.action == "snooze") != (change.hours is not None):
            raise DomainError(422, "Indiquez une durée seulement pour reporter une notification.")

        def update(docs, repo):
            until = None
            if change.hours:
                until = (datetime.now(timezone.utc) + timedelta(hours=change.hours)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            docs.update_notification_in(repo, identifier, read=change.action == "read", snooze=until)
            return {"id": identifier, "snoozedUntil": until}

        return write_document("notification:" + identifier, change, request_key, update,
                              result_type=NotificationResult, permission="reader")

    @register("docs", "Demander confirmation pour partager un document", annotations=MUTATION)
    def prepare_document_share(page_id: str, recipient_id: PositiveId, revision: PositiveId,
                               request_key: WriteKey, remove: bool = False) -> ApprovalRequest:
        """Donne ou retire un accès en lecture au document après confirmation dans Circular."""
        required = tool_scopes("docs", write=True)
        token, _service = principal(database, required)
        docs = docs_service()
        identifier = document_id(page_id)

        def validate(_service, repo):
            docs_repo = docs.repository_on(repo.connection, "owner")
            page = require_document(docs_repo.page(identifier))
            recipient = TicketShares.recipient(repo, recipient_id)
            return page, recipient["name"]

        def write(_service, repo, values, _slug):
            page, recipient = values
            docs._check_revision(page, revision)
            return approvals.prepare(repo, token, "share_document", {"page_id": identifier, "title": page["title"],
                "revision": revision, "recipient": recipient, "recipient_id": recipient_id, "remove": remove})

        return transact(database, required, "prepare_document_share", {"page": identifier, "recipient": recipient_id,
                        "revision": revision, "remove": remove}, request_key, ApprovalRequest, validate, write, lock_workspace=True)

    @register("projects", "Rechercher des éléments de feuille de route")
    def list_planning(kind: PlanningKind, query: RecordQuery = "", cursor: RecordCursor = "") -> RecordPage:
        """Liste les initiatives, jalons, cycles, bilans ou permanences de triage. Poursuis avec nextCursor."""
        return records("projects").list(kind, query, cursor)

    @register("projects", "Enregistrer un élément de feuille de route", annotations=MUTATION)
    def save_planning(kind: PlanningKind, change: RecordChange, request_key: WriteKey) -> Record:
        """Crée un élément ou le met à jour avec son identifiant et sa révision. Un jalon exige un projet."""
        return save_record("projects", kind, change, request_key)

    @register("projects", "Demander confirmation pour archiver un élément de feuille de route", annotations=MUTATION)
    def prepare_planning_archive(kind: PlanningKind, record_id: str, revision: PositiveId, request_key: WriteKey) -> ApprovalRequest:
        return archive_record("projects", kind, record_id, revision, request_key)

    @register("customers", "Rechercher des clients ou des demandes")
    def list_customer_records(kind: CustomerKind, query: RecordQuery = "", cursor: RecordCursor = "") -> RecordPage:
        """Liste les clients ou leurs demandes. Poursuis avec nextCursor."""
        return records("customers").list(kind, query, cursor)

    @register("customers", "Enregistrer un client ou une demande", annotations=MUTATION)
    def save_customer_record(kind: CustomerKind, change: RecordChange, request_key: WriteKey) -> Record:
        """Crée une fiche ou une demande. Pour rattacher une demande à un client, fournis son identifiant comme parentId."""
        return save_record("customers", kind, change, request_key)

    @register("customers", "Demander confirmation pour archiver une fiche client ou une demande", annotations=MUTATION)
    def prepare_customer_archive(kind: CustomerKind, record_id: str, revision: PositiveId, request_key: WriteKey) -> ApprovalRequest:
        return archive_record("customers", kind, record_id, revision, request_key)

    @register("releases", "Rechercher des releases, pipelines ou critères")
    def list_release_records(kind: ReleaseKind, query: RecordQuery = "", cursor: RecordCursor = "") -> RecordPage:
        """Liste les pipelines, releases, notes et critères de revue accessibles. Poursuis avec nextCursor."""
        return records("releases").list(kind, query, cursor)

    @register("releases", "Enregistrer une release, une note ou un critère", annotations=MUTATION)
    def save_release_record(kind: ReleaseKind, change: RecordChange, request_key: WriteKey) -> Record:
        """Enregistre un élément de release. Les releases sont rattachées à un pipeline."""
        return save_record("releases", kind, change, request_key)

    @register("releases", "Demander confirmation pour archiver un élément de release", annotations=MUTATION)
    def prepare_release_archive(kind: ReleaseKind, record_id: str, revision: PositiveId, request_key: WriteKey) -> ApprovalRequest:
        return archive_record("releases", kind, record_id, revision, request_key)

    @register("releases", "Consulter une pull request GitHub et ses modifications")
    def get_github_pull(repository: RepositoryName, number: PositiveId, page: Annotated[int, Field(ge=1, le=100)] = 1) -> PullFiles:
        service = workspace("releases")
        return GithubReviews(service.user_id, service.workspace_id).files(repository, number, page)

    @register("releases", "Demander confirmation pour une action de revue GitHub", annotations=MUTATION)
    def prepare_github_review(review: PullAction, request_key: WriteKey) -> ApprovalRequest:
        """Prépare un commentaire, une demande de changements, une approbation ou une fusion. Fournis le lien à l’utilisateur."""
        required = tool_scopes("releases", write=True)
        token, service = principal(database, required)
        github = GithubReviews(service.user_id, service.workspace_id)

        def write(_service, repo, _target, _slug):
            pull = github.pull(review.repository, review.number)
            if pull.state != "open" or pull.sha != review.sha:
                raise DomainError(409, "La PR a changé. Relisez-la avant de préparer une action.")
            return approvals.prepare(repo, token, "github", {**review.model_dump(), "base": pull.base})

        return transact(database, required, "prepare_github_review", review.model_dump(), request_key, ApprovalRequest,
                        lambda _service, _repo: github.configured_token(review.repository), write)

    @register("releases", "Consulter l’état d’une confirmation de revue GitHub")
    def get_github_review_status(action_id: str) -> ApprovalStatus:
        token, service = principal(database, tool_scopes("releases"))
        return ApprovalStatus.model_validate(approvals.get(document_id(action_id), service.user_id, token))

    @register("agents", "Rechercher des consignes, notes et blocages")
    def list_assistant_context(kind: ContextKind, query: RecordQuery = "", cursor: RecordCursor = "") -> RecordPage:
        """Recherche dans le contexte partagé avec les membres de l’espace. Poursuis avec nextCursor."""
        return records("agents").list(kind, query, cursor)

    @register("agents", "Identifier l’espace de cette connexion")
    def get_connected_workspace() -> WorkspaceIdentity:
        service = workspace("agents")
        with scoped_connection(database, service.user_id, service.workspace_id) as connection:
            row = connection.execute("SELECT id, name, slug FROM workspaces WHERE id = ?", (service.workspace_id,)).fetchone()
            return WorkspaceIdentity(**dict(service.require(row, "Espace introuvable.")), userId=service.user_id)

    @register("agents", "Enregistrer une consigne, une note ou un blocage", annotations=MUTATION)
    def save_assistant_context(kind: ContextKind, change: RecordChange, request_key: WriteKey) -> Record:
        """Enregistre du contexte partagé. Indique la source pour un apprentissage vérifié et exclue les secrets."""
        return save_record("agents", kind, change, request_key)

    @register("agents", "Demander confirmation pour archiver un élément de contexte", annotations=MUTATION)
    def prepare_context_archive(kind: ContextKind, record_id: str, revision: PositiveId, request_key: WriteKey) -> ApprovalRequest:
        return archive_record("agents", kind, record_id, revision, request_key)

    @register("agents", "Indiquer qu’une note a été utile", annotations=ADDITIVE)
    def mark_learning_helpful(record_id: str, request_key: WriteKey) -> Record:
        store = records("agents")
        identifier = document_id(record_id)
        return transact(database, tool_scopes("agents", write=True), "mark_learning_helpful", {"id": identifier},
                        request_key, Record, lambda _service, repo: store.get_in(repo, "learning", identifier, lock=True),
                        lambda _service, repo, note, _slug: store.mark_helpful(repo, note))
