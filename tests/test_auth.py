"""Real cookie authentication and authorization boundaries, without an auth bypass."""
import hashlib
import time
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from backend.app.api.auth import router, require_user
from backend.app.core.security import LocalSecurityMiddleware
from backend.app.core.passwords import verify_password
from backend.app.db.session import Database
from backend.app.services.auth import AuthService
from backend.app.services.workspace import DomainError
from fastapi import Depends

PASSWORD = "Une phrase de passe fictive 42!"
NEW_PASSWORD = "Une autre phrase de passe 84!"


def auth_app(path: Path) -> FastAPI:
    """Exercise the real adapter/service/database while the root composes other routes."""
    app = FastAPI()
    app.state.auth = AuthService(Database(path))
    app.add_middleware(LocalSecurityMiddleware)

    @app.exception_handler(DomainError)
    async def domain_error(_request, error):
        return JSONResponse({"error": error.message}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, _error):
        return JSONResponse({"error": "Données invalides."}, status_code=422)

    app.include_router(router)

    @app.patch("/api/protected")
    def protected(user=Depends(require_user)):
        return user

    return app


@pytest.fixture
def auth(tmp_path):
    app = auth_app(tmp_path / "auth.sqlite")
    with TestClient(app, base_url="http://127.0.0.1:4310") as client:
        yield client, app.state.auth


def register(client, email="alice@epita.fr", username="Alice", password=PASSWORD):
    response = client.post("/api/auth/register", json={"email": email, "username": username, "password": password})
    assert response.status_code == 201, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrfToken"]
    return response


def test_registration_hash_cookie_and_persisted_session(auth):
    client, service = auth
    response = register(client, " Alice@EPITA.FR ")
    assert set(response.json()) == {"user", "csrfToken"}
    assert response.json()["user"] == {"id": 1, "email": "alice@epita.fr", "username": "Alice"}
    assert "password" not in response.text and "token_hash" not in response.text
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    token = client.cookies.get("circular_session")
    with service.database.connect() as db:
        user = dict(db.execute("SELECT * FROM users").fetchone())
        session = dict(db.execute("SELECT * FROM user_sessions").fetchone())
    assert user["password_hash"].startswith("$argon2id$")
    assert verify_password(user["password_hash"], PASSWORD)
    assert session["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(session)
    reopened = AuthService(Database(service.database.path))
    assert reopened.authenticate(token) == response.json()


@pytest.mark.parametrize("email", ["alice@example.com", "alice@epita.fr.example.com", "alice@sub.epita.fr", "alice@@epita.fr", "a..b@epita.fr", ".alice@epita.fr"])
def test_registration_rejects_other_domains(auth, email):
    client, _ = auth
    assert client.post("/api/auth/register", json={"email": email, "username": "Alice", "password": PASSWORD}).status_code == 422


@pytest.mark.parametrize("payload", [
    {"password": "short"}, {"password": "x" * 129}, {"username": " "}, {"username": "x" * 41},
    {"username": "alias@epita.fr"}, {"username": "bad\nname"}, {"role": "admin"},
])
def test_registration_invalid_fields_never_create_user(auth, payload):
    client, service = auth
    response = client.post("/api/auth/register", json={"email": "alice@epita.fr", "username": "Alice", "password": PASSWORD, **payload})
    assert response.status_code == 422
    with service.database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_case_insensitive_uniqueness_and_login_with_pseudo_or_email(auth):
    client, _ = auth
    register(client)
    duplicate = client.post("/api/auth/register", json={"email": "ALICE@epita.fr", "username": "Other", "password": PASSWORD})
    assert duplicate.status_code == 409
    duplicate_name = client.post("/api/auth/register", json={"email": "other@epita.fr", "username": "aLiCe", "password": PASSWORD})
    assert duplicate_name.status_code == 409
    for identifier in (" ALICE ", "ALICE@EPITA.FR"):
        result = client.post("/api/auth/login", json={"identifier": identifier, "password": PASSWORD})
        assert result.status_code == 200
        assert result.json()["user"]["email"] == "alice@epita.fr"


def test_unknown_and_wrong_password_have_same_failure(auth):
    client, _ = auth
    register(client)
    wrong = client.post("/api/auth/login", json={"identifier": "Alice", "password": "incorrect"})
    unknown = client.post("/api/auth/login", json={"identifier": "unknown", "password": "incorrect"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_csrf_is_required_and_logout_revokes_cookie(auth):
    client, service = auth
    session = register(client).json()
    token = client.cookies.get("circular_session")
    del client.headers["X-CSRF-Token"]
    assert client.patch("/api/protected", json={}).status_code == 403
    assert client.post("/api/auth/logout", json={}).status_code == 403
    client.headers["X-CSRF-Token"] = "wrong"
    assert client.patch("/api/protected", json={}).status_code == 403
    client.headers["X-CSRF-Token"] = session["csrfToken"]
    assert client.patch("/api/protected", json={}).status_code == 200
    assert client.post("/api/auth/logout", json={}).status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    with pytest.raises(DomainError) as error:
        service.authenticate(token)
    assert error.value.status == 401


def test_login_rotates_and_invalidates_prior_session(auth):
    client, service = auth
    old = register(client).json()
    old_cookie = client.cookies.get("circular_session")
    new = client.post("/api/auth/login", json={"identifier": "Alice", "password": PASSWORD}).json()
    assert client.cookies.get("circular_session") != old_cookie
    assert new["csrfToken"] != old["csrfToken"]
    with pytest.raises(DomainError):
        service.authenticate(old_cookie)


def test_password_change_revokes_every_session(auth):
    client, service = auth
    register(client)
    _, second_cookie = service.login("Alice", PASSWORD, "second-peer")
    assert client.post("/api/auth/password", json={"currentPassword": "incorrect", "newPassword": NEW_PASSWORD}).status_code == 400
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/password", json={"currentPassword": PASSWORD, "newPassword": NEW_PASSWORD}).status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    with pytest.raises(DomainError):
        service.authenticate(second_cookie)
    assert client.post("/api/auth/login", json={"identifier": "Alice", "password": PASSWORD}).status_code == 401
    assert client.post("/api/auth/login", json={"identifier": "Alice", "password": NEW_PASSWORD}).status_code == 200


@pytest.mark.parametrize("field", ["expires_at", "last_seen_at"])
def test_session_absolute_and_idle_expiry(auth, field):
    client, service = auth
    register(client)
    value = int(time.time()) - (service.idle_timeout + 1 if field == "last_seen_at" else 1)
    with service.database.connect(write=True) as db:
        db.execute(f"UPDATE user_sessions SET {field} = ?", (value,))
    assert client.get("/api/auth/me").status_code == 401
    with service.database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM user_sessions").fetchone()[0] == 0


def test_rate_limit_is_shared_between_service_instances(auth):
    _, service = auth
    service2 = AuthService(Database(service.database.path))
    for attempt in range(11):
        with pytest.raises(DomainError) as failure:
            (service if attempt % 2 else service2).login("absent", "incorrect", "same-peer")
        assert failure.value.status == (401 if attempt < 10 else 429)


def test_forged_cookie_and_disabled_user_cannot_authenticate(auth):
    client, service = auth
    client.cookies.set("circular_session", "forged")
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.clear()
    register(client)
    with service.database.connect(write=True) as db:
        db.execute("UPDATE users SET active = 0")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"identifier": "Alice", "password": PASSWORD}).status_code == 401


def test_operator_reset_revokes_sessions_without_public_endpoint(auth):
    client, service = auth
    register(client)
    service.reset_password("alice@epita.fr", NEW_PASSWORD)
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"identifier": "Alice", "password": NEW_PASSWORD}).status_code == 200
    assert client.post("/api/auth/reset-password", json={"email": "alice@epita.fr"}).status_code == 404


def test_another_sessions_csrf_token_is_rejected(auth):
    client, service = auth
    first = register(client).json()
    second, _ = service.register("bob@epita.fr", "Bob", PASSWORD, "another-peer")
    client.headers["X-CSRF-Token"] = second["csrfToken"]
    assert client.patch("/api/protected", json={}).status_code == 403
    assert client.get("/api/auth/me").json()["user"] == first["user"]


def test_non_ascii_csrf_header_is_rejected_without_server_error(auth):
    client, _ = auth
    register(client)
    del client.headers["X-CSRF-Token"]
    assert client.patch("/api/protected", json={}, headers={b"x-csrf-token": b"\xff"}).status_code == 403


def test_production_cookie_origin_and_hsts(tmp_path, monkeypatch):
    monkeypatch.setenv("CIRCULAR_ENV", "production")
    monkeypatch.setenv("CIRCULAR_PUBLIC_URL", "https://circular.epita.fr")
    with TestClient(auth_app(tmp_path / "production-auth.sqlite"), base_url="https://circular.epita.fr") as client:
        blocked = client.post("/api/auth/register", json={"email": "alice@epita.fr", "username": "Alice", "password": PASSWORD}, headers={"origin": "https://untrusted.example"})
        assert blocked.status_code == 403
        response = register(client)
        assert "Secure" in response.headers["set-cookie"]
        assert "HttpOnly" in response.headers["set-cookie"]
        assert response.headers["strict-transport-security"] == "max-age=31536000"
        assert client.get("/api/auth/me").status_code == 200
        assert client.get("/api/auth/me", headers={"host": "untrusted.example"}).status_code == 403


def test_password_whitespace_is_preserved_through_all_forms(auth):
    client, _ = auth
    password = "  Une phrase avec espaces 42!  "
    replacement = "  Une autre phrase avec espaces 84!  "
    register(client, password=password)
    assert client.post("/api/auth/login", json={"identifier": "Alice", "password": password.strip()}).status_code == 401
    login = client.post("/api/auth/login", json={"identifier": "Alice", "password": password})
    assert login.status_code == 200
    client.headers["X-CSRF-Token"] = login.json()["csrfToken"]
    assert client.post("/api/auth/password", json={"currentPassword": password.strip(), "newPassword": replacement}).status_code == 400
    assert client.post("/api/auth/password", json={"currentPassword": password, "newPassword": replacement}).status_code == 204
    assert client.post("/api/auth/login", json={"identifier": "Alice", "password": replacement.strip()}).status_code == 401
    assert client.post("/api/auth/login", json={"identifier": "Alice", "password": replacement}).status_code == 200
