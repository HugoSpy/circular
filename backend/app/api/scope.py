"""Resolve an explicit browser workspace; legacy clients retain permissioned scope."""
from fastapi import Request
from backend.app.services.spaces import SpacesService
from backend.app.services.workspace import DomainError
from backend.app.schemas.workspace import MAX_ID


def selected_workspace(request: Request, user_id: int) -> int | None:
    values = request.headers.getlist("x-workspace-id")
    if not values:
        return None
    if len(values) != 1 or not values[0].isascii() or not values[0].isdigit() or not 0 < int(values[0]) <= MAX_ID:
        raise DomainError(422, "Espace sélectionné invalide.")
    workspace_id = int(values[0])
    SpacesService(request.app.state.database, user_id).workspace(workspace_id)
    return workspace_id
