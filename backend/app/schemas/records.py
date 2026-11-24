"""Contracts shared by the planning, customer, release and assistant tools."""
from datetime import date
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, UUID4, field_validator, model_validator

from backend.app.schemas.workspace import Input, PositiveId, Title, validate_date

RecordKind = Literal["initiative", "milestone", "cycle", "update", "triage", "customer", "request", "pipeline",
                     "release", "release_note", "review_criterion", "pull_link", "instruction", "learning", "friction"]
RecordState = Literal["planned", "active", "review", "done", "canceled"]
RecordId = Annotated[UUID4, Field(strict=False)]


class RecordDraft(Input):
    nullable_fields = {"projectId", "ticketId", "parentId", "sourceUrl", "startsOn", "endsOn"}
    title: Title
    body: str = Field(default="", max_length=20000)
    state: RecordState = "planned"
    projectId: PositiveId | None = None
    ticketId: PositiveId | None = None
    parentId: RecordId | None = None
    sourceUrl: str | None = Field(default=None, max_length=2048)
    startsOn: str | None = None
    endsOn: str | None = None

    @field_validator("startsOn", "endsOn")
    @classmethod
    def valid_date(cls, value):
        return validate_date(value)

    @field_validator("sourceUrl")
    @classmethod
    def https_source(cls, value):
        if value is not None:
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Adresse source HTTPS invalide.")
        return value

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.startsOn and self.endsOn and date.fromisoformat(self.startsOn) > date.fromisoformat(self.endsOn):
            raise ValueError("La date de fin doit suivre la date de début.")
        return self


class RecordChange(Input):
    nullable_fields = {"id", "revision"}
    id: RecordId | None = None
    revision: PositiveId | None = None
    record: RecordDraft

    @model_validator(mode="after")
    def matched_revision(self):
        if (self.id is None) != (self.revision is None):
            raise ValueError("Fournissez ensemble l’identifiant et la révision.")
        return self
