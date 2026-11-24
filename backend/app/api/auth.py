"""Cookie-session HTTP adapter. Authentication and CSRF are dependencies, not UI checks."""
import os
import secrets
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Response
from backend.app.schemas.auth import ChangePassword, Login, Register, SessionResponse, ProfileUpdate, PublicUser, VerificationRequest, VerificationToken, RegistrationAccepted
from backend.app.services.auth import AuthService
from backend.app.services.workspace import DomainError

COOKIE_NAME = "circular_session"
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def service(request: Request) -> AuthService:
    return request.app.state.auth


def peer(request: Request) -> str:
    # Reverse-proxy forwarding is controlled by the server's explicit trusted-proxy list.
    return request.client.host if request.client else "unknown"


def session(request: Request) -> dict:
    if not hasattr(request.state, "authenticated_session"):
        request.state.authenticated_session = service(request).authenticate(request.cookies.get(COOKIE_NAME))
    return request.state.authenticated_session


def require_user(request: Request) -> dict:
    current = session(request)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not secrets.compare_digest(supplied.encode("utf-8"), current["csrfToken"].encode("ascii")):
            raise DomainError(403, "La session ne permet pas cette requête. Actualisez la page et réessayez.")
    return current["user"]


User = Annotated[dict, Depends(require_user)]


def set_cookie(response: Response, token: str, ttl: int) -> None:
    response.set_cookie(COOKIE_NAME, token, max_age=ttl, httponly=True, secure=os.environ.get("CIRCULAR_ENV") == "production", samesite="lax", path="/")


def clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, httponly=True, secure=os.environ.get("CIRCULAR_ENV") == "production", samesite="lax", path="/")


@router.get("/me", response_model=SessionResponse)
def me(request: Request):
    return session(request)


@router.post("/register", status_code=202, response_model=RegistrationAccepted)
def register(data: Register, request: Request):
    return service(request).register(data.email, data.username, data.password, peer(request))


@router.post("/verification/resend", status_code=202, response_model=RegistrationAccepted)
def resend_verification(data: VerificationRequest, request: Request):
    return service(request).request_verification(data.email, peer(request))


@router.post("/verification/resend-current", status_code=202, response_model=RegistrationAccepted)
def resend_current_verification(request: Request, user: User):
    return service(request).request_current_verification(user["id"], peer(request))


@router.post("/verification/confirm", response_model=SessionResponse)
def confirm_verification(data: VerificationToken, request: Request, response: Response):
    auth = service(request)
    result, token = auth.verify_email(data.token, peer(request))
    if previous := request.cookies.get(COOKIE_NAME):
        auth.logout(previous)
    set_cookie(response, token, auth.session_ttl)
    return result


@router.post("/login", response_model=SessionResponse)
def login(data: Login, request: Request, response: Response):
    auth = service(request)
    result, token = auth.login(data.identifier, data.password, peer(request))
    if previous := request.cookies.get(COOKIE_NAME):
        auth.logout(previous)
    set_cookie(response, token, auth.session_ttl)
    return result


@router.post("/logout", status_code=204)
def logout(request: Request, user: User):
    service(request).logout(request.cookies[COOKIE_NAME])
    response = Response(status_code=204)
    clear_cookie(response)
    return response


@router.post("/password", status_code=204)
def change_password(data: ChangePassword, request: Request, user: User):
    service(request).change_password(user["id"], data.currentPassword, data.newPassword, peer(request))
    response = Response(status_code=204)
    clear_cookie(response)
    return response


@router.patch("/profile", response_model=PublicUser)
def update_profile(data: ProfileUpdate, request: Request, user: User):
    return service(request).update_profile(user["id"], data.model_dump())
