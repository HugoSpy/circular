"""Strict local-account input and public session response contracts."""
import re
import unicodedata
from typing import Annotated
from pydantic import BaseModel, Field, StringConstraints, field_validator
from backend.app.schemas.workspace import Input

EMAIL_PATTERN = re.compile(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@epita\.fr", re.ASCII)
Password = Annotated[str, StringConstraints(strip_whitespace=False, min_length=12, max_length=128)]
ExistingPassword = Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=128)]


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Une adresse @epita.fr est requise.")
    local = email.split("@", 1)[0]
    if local.startswith(".") or local.endswith(".") or ".." in local:
        raise ValueError("Adresse électronique invalide.")
    return email


class Register(Input):
    email: str = Field(max_length=254)
    username: str = Field(min_length=2, max_length=40)
    password: Password

    @field_validator("email")
    @classmethod
    def email_domain(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        value = unicodedata.normalize("NFC", value.strip())
        if not 2 <= len(value) <= 40 or "@" in value or any(unicodedata.category(char).startswith("C") for char in value):
            raise ValueError("Pseudo invalide.")
        return value


class Login(Input):
    identifier: str = Field(min_length=1, max_length=254)
    password: ExistingPassword


class ChangePassword(Input):
    currentPassword: ExistingPassword
    newPassword: Password


class ProfileUpdate(Input):
    displayName: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ""


class PublicUser(BaseModel):
    id: int
    email: str
    username: str
    displayName: str
    title: str
    profileCompleted: bool


class SessionResponse(BaseModel):
    user: PublicUser
    csrfToken: str
