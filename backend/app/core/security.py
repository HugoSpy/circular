"""Loopback-only browser access and bounded JSON request bodies."""
import re
from starlette.datastructures import Headers
from starlette.responses import JSONResponse, Response
from urllib.parse import urlsplit
from backend.app.core.config import production, public_url

BODY_LIMIT = 131072
HOST_PATTERN = re.compile(r"^(localhost|127\.0\.0\.1)(?::([0-9]{1,5}))?$", re.IGNORECASE)
CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"


class LocalSecurityMiddleware:
    def __init__(self, app):
        self.app = app
        self.production = production()
        self.public_url = public_url()
        self.public_host = urlsplit(self.public_url).netloc.lower() if self.public_url else None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        host = headers.get("host", "")
        match = HOST_PATTERN.fullmatch(host)
        origin = headers.get("origin")
        allowed_origin = origin == self.public_url if self.production else origin in {f"http://{host.lower()}", "http://127.0.0.1:5173", self.public_url}

        async def secure_send(message):
            if message["type"] == "http.response.start":
                extra = [(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
                         (b"referrer-policy", b"no-referrer"), (b"content-security-policy", CSP.encode()),
                         (b"cache-control", b"no-store")]
                if self.production:
                    extra.append((b"strict-transport-security", b"max-age=31536000"))
                if origin and allowed_origin:
                    extra.extend([(b"access-control-allow-origin", origin.encode()), (b"vary", b"Origin")])
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        async def reject(status, message):
            await JSONResponse({"error": message}, status_code=status)(scope, receive, secure_send)

        local_valid = bool(match and (not match.group(2) or 1 <= int(match.group(2)) <= 65535))
        # Loopback health probes are permitted without broadening the public API host allowlist.
        probe = scope["path"] in {"/api/health", "/api/ready"} and local_valid
        host_valid = host.lower() == self.public_host if self.production else local_valid
        if len(headers.getlist("host")) != 1 or not (host_valid or probe):
            return await reject(403, "Hôte non autorisé.")
        if origin and not allowed_origin:
            return await reject(403, "Origine non autorisée.")
        if headers.get("sec-fetch-site") == "cross-site" and not allowed_origin:
            return await reject(403, "Requête intersite non autorisée.")
        if scope["method"] == "OPTIONS":
            return await Response(status_code=204, headers={"Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS", "Access-Control-Allow-Headers": "Content-Type, X-CSRF-Token"})(scope, receive, secure_send)
        if scope["method"] in {"POST", "PATCH", "PUT"}:
            if headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                return await reject(415, "Le contenu doit être au format application/json.")
            try:
                if int(headers.get("content-length", "0")) > BODY_LIMIT:
                    return await reject(413, "La requête dépasse la limite de 128 Ko.")
            except ValueError:
                return await reject(400, "Taille de requête invalide.")
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > BODY_LIMIT:
                    return await reject(413, "La requête dépasse la limite de 128 Ko.")
                if not message.get("more_body", False):
                    break
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            return await self.app(scope, replay, secure_send)
        await self.app(scope, receive, secure_send)
