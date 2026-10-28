"""Strict request schemas shared by HTTP routes and seed data."""
from datetime import date
from typing import Annotated, Literal, ClassVar
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationInfo, field_validator, model_validator

Status = Literal["backlog", "todo", "in_progress", "in_review", "done"]
Priority = Literal["none", "low", "medium", "high", "urgent"]
ProjectStatus = Literal["backlog", "planned", "in_progress", "completed", "canceled"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]
Color = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
ProjectKey = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Z][A-Z0-9]{1,9}$")]
MAX_ID = 9223372036854775807
PositiveId = Annotated[int, Field(strict=True, gt=0, le=MAX_ID)]
LabelIds = Annotated[list[PositiveId], Field(max_length=20)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    nullable_fields: ClassVar[set[str]] = set()

    @field_validator("*", mode="before")
    @classmethod
    def forbid_null(cls, value, info: ValidationInfo):
        if value is None and info.field_name not in cls.nullable_fields:
            raise ValueError("La valeur ne peut pas être nulle.")
        return value


class ProjectCreate(Input):
    nullable_fields = {"dueDate"}
    name: Name
    key: ProjectKey
    description: str = Field(default="", max_length=5000)
    color: Color = "#e6c65c"
    status: ProjectStatus = "planned"
    dueDate: str | None = None

    @field_validator("dueDate")
    @classmethod
    def valid_due_date(cls, value):
        return validate_date(value)


class Patch(Input):
    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set:
            raise ValueError("Aucune modification fournie.")
        return self


class ProjectUpdate(Patch):
    nullable_fields = {"dueDate"}
    name: Name | None = None
    description: str | None = Field(default=None, max_length=5000)
    color: Color | None = None
    status: ProjectStatus | None = None
    dueDate: str | None = None

    @field_validator("dueDate")
    @classmethod
    def valid_due_date(cls, value):
        return validate_date(value)


class IssueCreate(Input):
    nullable_fields = {"dueDate"}
    title: Title
    description: str = Field(default="", max_length=20000)
    projectId: PositiveId
    status: Status = "backlog"
    priority: Priority = "none"
    labelIds: LabelIds = Field(default_factory=list)
    dueDate: str | None = None
    isFavorite: bool = False

    @field_validator("dueDate")
    @classmethod
    def valid_due_date(cls, value):
        return validate_date(value)

    @field_validator("labelIds")
    @classmethod
    def unique_labels(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Une étiquette ne peut pas être ajoutée deux fois.")
        return value


class IssueUpdate(Patch):
    nullable_fields = {"dueDate"}
    title: Title | None = None
    description: str | None = Field(default=None, max_length=20000)
    projectId: PositiveId | None = None
    status: Status | None = None
    priority: Priority | None = None
    labelIds: LabelIds | None = None
    dueDate: str | None = None
    isFavorite: bool | None = None

    @field_validator("dueDate")
    @classmethod
    def valid_due_date(cls, value):
        return validate_date(value)

    @field_validator("labelIds")
    @classmethod
    def unique_labels(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Une étiquette ne peut pas être ajoutée deux fois.")
        return value


class LabelCreate(Input):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    color: Color = "#9da5af"
    description: str = Field(default="", max_length=1000)


class LabelUpdate(Patch):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)] | None = None
    color: Color | None = None
    description: str | None = Field(default=None, max_length=1000)


class CommentCreate(Input):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]


def validate_date(value: str | None) -> str | None:
    if value is not None:
        if len(value) != 10 or date.fromisoformat(value).isoformat() != value:
            raise ValueError("La date doit être au format AAAA-MM-JJ.")
    return value
