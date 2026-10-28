"""Application factory, error translation, middleware and local frontend."""
from pathlib import Path
import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from backend.app.api.routes import router
from backend.app.api.preferences import router as preferences_router
from backend.app.api.auth import router as auth_router
from backend.app.api.sharing import router as sharing_router
from backend.app.api.spaces import router as spaces_router
from backend.app.api.frontend import mount_frontend
from backend.app.core.config import ROOT, database_target, public_url
from backend.app.core.security import LocalSecurityMiddleware
from backend.app.db.session import Database
from backend.app.services.workspace import DomainError, WorkspaceService
from backend.app.services.preferences import PreferencesService
from backend.app.services.auth import AuthService


def create_app(db_path: Path | str | None = None, dist_path: Path | str | None = None) -> FastAPI:
    app = FastAPI(title="Circular", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    public_url()
    app.state.database = Database(db_path or database_target())
    app.state.auth = AuthService(app.state.database)
    app.state.workspace = WorkspaceService(app.state.database)
    app.state.preferences = PreferencesService(app.state.database)
    app.add_middleware(LocalSecurityMiddleware)

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, error: DomainError):
        if error.status == 403:
            logging.getLogger("circular.security").warning("authorization_denied method=%s", _request.method)
        return JSONResponse({"error": error.message}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError):
        return JSONResponse({"error": "Données invalides. Vérifiez les champs renseignés."}, status_code=422)

    app.include_router(router)
    app.include_router(preferences_router)
    app.include_router(auth_router)
    app.include_router(sharing_router)
    app.include_router(spaces_router)
    mount_frontend(app, Path(dist_path) if dist_path is not None else ROOT / "dist")
    return app
