"""Persistent display preferences, saved views and reusable creation templates."""
from typing import Annotated, Literal
from pydantic import Field, StringConstraints, field_validator
from backend.app.schemas.workspace import Input, Patch, Name, PositiveId, LabelIds, Status, Priority, MAX_ID

SortBy = Literal["createdAt", "updatedAt", "title", "priority", "dueDate"]
Direction = Literal["asc", "desc"]
Property = Literal["identifier", "status", "priority", "project", "labels", "createdAt", "updatedAt", "dueDate"]


class Display(Input):
    view: Literal["list", "board"] = "list"
    grouping: Literal["status", "project", "priority", "none"] = "status"
    sortBy: SortBy = "createdAt"
    direction: Direction = "desc"
    properties: list[Property] = Field(default_factory=lambda: ["identifier", "status", "priority", "project", "labels"], max_length=8)
    showEmptyGroups: bool = False
    collapsedGroups: list[Annotated[str, StringConstraints(max_length=120)]] = Field(default_factory=list, max_length=500)
    hiddenStatuses: list[Status] = Field(default_factory=list, max_length=5)

    @field_validator("properties", "collapsedGroups", "hiddenStatuses")
    @classmethod
    def unique_values(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Valeurs répétées.")
        return value


class Filters(Input):
    q: str = Field(default="", max_length=200)
    projectId: Annotated[str, StringConstraints(pattern=r"^(?:[1-9][0-9]*)?$", max_length=19)] = ""
    status: Literal["", "backlog", "todo", "in_progress", "in_review", "done"] = ""
    priority: Literal["", "none", "low", "medium", "high", "urgent"] = ""
    labelIds: LabelIds = Field(default_factory=list)
    statuses: list[Status] = Field(default_factory=list, max_length=5)
    priorities: list[Priority] = Field(default_factory=list, max_length=5)
    favoritesOnly: bool = False

    @field_validator("projectId")
    @classmethod
    def valid_project_id(cls, value):
        if value and int(value) > MAX_ID:
            raise ValueError("Identifiant de projet invalide.")
        return value

    @field_validator("labelIds", "statuses", "priorities")
    @classmethod
    def unique_values(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Valeurs répétées.")
        return value


class Settings(Input):
    homeView: Literal["resume", "list", "board", "projects"] = "resume"
    fontSize: Literal["small", "default", "large"] = "default"
    density: Literal["compact", "comfortable"] = "compact"
    reduceMotion: bool = False
    commentSubmit: Literal["ctrl_enter", "enter"] = "ctrl_enter"
    display: Display = Field(default_factory=Display)
    filters: Filters = Field(default_factory=Filters)


class SettingsUpdate(Patch):
    homeView: Literal["resume", "list", "board", "projects"] | None = None
    fontSize: Literal["small", "default", "large"] | None = None
    density: Literal["compact", "comfortable"] | None = None
    reduceMotion: bool | None = None
    commentSubmit: Literal["ctrl_enter", "enter"] | None = None
    display: Display | None = None
    filters: Filters | None = None


class ViewCreate(Input):
    name: Name
    filters: Filters = Field(default_factory=Filters)
    display: Display = Field(default_factory=Display)


class ViewUpdate(Patch):
    name: Name | None = None
    filters: Filters | None = None
    display: Display | None = None


class SavedView(ViewCreate):
    id: int


class TemplateCreate(Input):
    nullable_fields = {"projectId"}
    name: Name
    title: str = Field(default="", max_length=240)
    description: str = Field(default="", max_length=20000)
    projectId: PositiveId | None = None
    status: Status = "backlog"
    priority: Priority = "none"
    labelIds: LabelIds = Field(default_factory=list)

    @field_validator("labelIds")
    @classmethod
    def unique_values(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Valeurs répétées.")
        return value


class TemplateUpdate(Patch):
    nullable_fields = {"projectId"}
    name: Name | None = None
    title: str | None = Field(default=None, max_length=240)
    description: str | None = Field(default=None, max_length=20000)
    projectId: PositiveId | None = None
    status: Status | None = None
    priority: Priority | None = None
    labelIds: LabelIds | None = None

    @field_validator("labelIds")
    @classmethod
    def unique_values(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Valeurs répétées.")
        return value


class Template(TemplateCreate):
    id: int
