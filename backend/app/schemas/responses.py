"""Public response contract exposed by the local OpenAPI document."""
from pydantic import BaseModel, ConfigDict
from typing import Literal
from backend.app.schemas.workspace import Status, Priority, ProjectStatus


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Project(Output):
    id: int
    workspaceId: int | None
    visibility: Literal["private", "workspace"]
    name: str
    key: str
    description: str
    color: str
    issueCount: int
    doneCount: int
    createdAt: str
    status: ProjectStatus
    dueDate: str | None
    role: Literal["owner", "member"]


class Label(Output):
    id: int
    name: str
    color: str
    description: str
    canEdit: bool


class Issue(Output):
    id: int
    identifier: str
    title: str
    description: str
    projectId: int
    status: Status
    priority: Priority
    labels: list[Label]
    createdAt: str
    updatedAt: str
    dueDate: str | None
    isFavorite: bool


class Person(Output):
    id: int
    username: str
    displayName: str


class Comment(Output):
    id: int
    issueId: int
    body: str
    createdAt: str
    author: Person | None
    canEdit: bool
    canDelete: bool


class Error(Output):
    error: str


class Activity(Output):
    id: int
    issueId: int
    kind: str
    body: str
    createdAt: str
    actor: Person | None
