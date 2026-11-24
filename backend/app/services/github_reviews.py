"""GitHub pull request access for a configured Circular workspace and GitHub user."""
import json
import os
import re
from pathlib import Path
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, Field, StringConstraints, model_validator

from backend.app.schemas.workspace import Input, PositiveId
from backend.app.services.workspace import DomainError

RepositoryName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=200)]
Commit = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
GITHUB_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


class PullAction(Input):
    repository: RepositoryName
    number: PositiveId
    sha: Commit
    action: Literal["comment", "request_changes", "approve", "merge"]
    body: str = Field(default="", max_length=12000)

    @model_validator(mode="after")
    def required_body(self):
        if self.action in {"comment", "request_changes"} and not self.body.strip():
            raise ValueError("Un texte est requis.")
        return self


class PullRequest(BaseModel):
    repository: str
    number: int
    title: str
    body: str
    sha: str
    base: str
    state: str
    url: str
    merged: bool


class PullFiles(BaseModel):
    pull: PullRequest
    files: list[dict]
    nextPage: int | None


class GithubReviews:
    def __init__(self, user_id: int, workspace_id: int):
        self.user_id = user_id
        self.workspace_id = workspace_id

    def configured_token(self, repository: str) -> str:
        filename = os.environ.get("CIRCULAR_GITHUB_CONNECTIONS_FILE")
        if not filename:
            raise DomainError(503, "La connexion GitHub n’est pas configurée dans Circular.")
        try:
            settings = json.loads(Path(filename).read_text(encoding="utf-8"))
            if not isinstance(settings, list):
                raise ValueError
        except (OSError, ValueError) as error:
            raise DomainError(503, "La configuration GitHub est indisponible.") from error
        for entry in settings:
            if (isinstance(entry, dict) and entry.get("workspaceId") == self.workspace_id and entry.get("userId") == self.user_id
                    and isinstance(entry.get("repository"), str) and entry["repository"].casefold() == repository.casefold()
                    and isinstance(entry.get("token"), str) and re.fullmatch(r"[A-Za-z0-9_]+", entry["token"])):
                return entry["token"]
        raise DomainError(404, "Dépôt GitHub introuvable pour cette connexion.")

    def request(self, repository: str, path: str, *, method: str = "GET", data: dict | None = None) -> tuple[object, bool]:
        if not GITHUB_REPOSITORY.fullmatch(repository) or {".", ".."}.intersection(repository.split("/")):
            raise DomainError(404, "Dépôt GitHub introuvable.")
        auth = self.configured_token(repository)
        try:
            response = httpx.request(method, f"https://api.github.com/repos/{repository}/{path}", json=data,
                                     headers={"Authorization": f"Bearer {auth}", "Accept": "application/vnd.github+json",
                                              "X-GitHub-Api-Version": "2022-11-28"},
                                     follow_redirects=False, trust_env=False, timeout=10)
        except httpx.RequestError as error:
            raise DomainError(502, "GitHub ne répond pas. Vérifiez l’état de la PR avant toute relance.") from error
        if not response.is_success:
            if response.status_code in {401, 403, 404}:
                raise DomainError(403, "GitHub a refusé l’accès ou cette action.")
            if response.status_code in {405, 409, 422}:
                raise DomainError(409, "La PR a changé ou les conditions GitHub ne sont pas réunies.")
            raise DomainError(502, "GitHub n’a pas confirmé l’opération.")
        try:
            return response.json(), 'rel="next"' in response.headers.get("Link", "")
        except ValueError as error:
            raise DomainError(502, "GitHub a renvoyé une réponse illisible.") from error

    def pull(self, repository: str, number: int) -> PullRequest:
        data, _ = self.request(repository, f"pulls/{number}")
        try:
            return PullRequest(repository=repository, number=number, title=data["title"], body=(data["body"] or "")[:12000],
                               sha=data["head"]["sha"], base=data["base"]["ref"], state=data["state"], merged=data["merged"],
                               url=f"https://github.com/{repository}/pull/{number}")
        except (KeyError, TypeError, ValueError) as error:
            raise DomainError(502, "GitHub a renvoyé une PR illisible.") from error

    def files(self, repository: str, number: int, page: int) -> PullFiles:
        pull = self.pull(repository, number)
        data, more = self.request(repository, f"pulls/{number}/files?per_page=15&page={page}")
        if not isinstance(data, list):
            raise DomainError(502, "GitHub a renvoyé une liste de fichiers illisible.")
        files = [{"path": item.get("filename"), "status": item.get("status"),
                  "patch": (item.get("patch") or "")[:8000]} for item in data if isinstance(item, dict)]
        return PullFiles(pull=pull, files=files, nextPage=page + 1 if more else None)

    def submit(self, data: PullAction) -> dict:
        pull = self.pull(data.repository, data.number)
        if pull.sha != data.sha or pull.state != "open":
            raise DomainError(409, "La PR a changé depuis la demande. Ouvrez une nouvelle demande pour cette révision.")
        path = f"pulls/{data.number}"
        if data.action == "merge":
            result, _ = self.request(data.repository, path + "/merge", method="PUT", data={"sha": data.sha})
            if not isinstance(result, dict) or not result.get("merged"):
                raise DomainError(409, "GitHub n’a pas fusionné la PR.")
            return {"url": pull.url, "message": "Pull request fusionnée."}
        events = {"approve": "APPROVE", "comment": "COMMENT", "request_changes": "REQUEST_CHANGES"}
        self.request(data.repository, path + "/reviews", method="POST",
                     data={"commit_id": data.sha, "body": data.body, "event": events[data.action]})
        return {"url": pull.url, "message": "Revue transmise à GitHub."}
