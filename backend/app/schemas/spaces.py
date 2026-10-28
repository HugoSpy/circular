"""Workspace administration and onboarding request contracts."""
from typing import Annotated
from pydantic import Field, StringConstraints, field_validator
from backend.app.schemas.workspace import Input, Name, Patch
from backend.app.schemas.auth import normalize_email

Slug = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]


class SpaceCreate(Input):
    name: Name
    slug: Slug
    includeWelcomeIssues: bool = True


class SpaceUpdate(Patch):
    name: Name | None = None
    slug: Slug | None = None


class SpaceInvitation(Input):
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def normalize(cls, value: str) -> str:
        return normalize_email(value)


class InviteToken(Input):
    token: str = Field(min_length=40, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
