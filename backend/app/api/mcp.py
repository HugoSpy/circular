"""Streamable HTTP transport and the authenticated Circular consent API."""
import os
from contextlib import asynccontextmanager
from typing import Annotated
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field, StringConstraints
from starlette.routing import Route

from backend.app.api.auth import User
from backend.app.core.security import BODY_LIMIT
from backend.app.schemas.workspace import PositiveId
from backend.app.services.mcp_auth import CircularMcpAuth
from backend.app.services.mcp_tools import READ_SCOPE, register_read_tools

RequestId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{43}$")]


class ConsentRequest(BaseModel):
    requestId: RequestId


class ConsentDecision(ConsentRequest):
    workspaceId: PositiveId | None = Field(...)


def mount_mcp(app: FastAPI, origin: str) -> None:
    router = APIRouter(prefix="/api/mcp")

    @router.get("/connections")
    def list_connections(user: User):
        return {"url": auth.resource if auth else None, "connections": auth.connections(user["id"]) if auth else []}

    if not origin:
        auth = None
        app.include_router(router)
        return

    redirects = {uri.strip() for uri in os.environ.get("CIRCULAR_MCP_REDIRECT_URIS", "").split(",") if uri.strip()}
    auth = CircularMcpAuth(app.state.database, origin, redirects)

    @router.post("/consent")
    def pending(data: ConsentRequest, user: User):
        return auth.pending(data.requestId, user["id"])

    @router.post("/consent/decision")
    def decide(data: ConsentDecision, user: User):
        return {"redirectUrl": auth.decide(data.requestId, user["id"], data.workspaceId)}

    @router.delete("/connections/{connection_id}", status_code=204)
    def revoke(connection_id: UUID, user: User):
        auth.revoke_connection(user["id"], str(connection_id))
        return Response(status_code=204)

    app.include_router(router)

    def build_transport():
        server = FastMCP(
            "Circular", instructions="Consultez les projets et tickets accessibles dans l’espace autorisé.",
            stateless_http=True, json_response=True, max_request_body_size=BODY_LIMIT,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
            auth_server_provider=auth,
            auth=AuthSettings(issuer_url=origin, resource_server_url=auth.resource, validate_token_resource=True,
                              required_scopes=[READ_SCOPE], revocation_options=RevocationOptions(enabled=True),
                              client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=[READ_SCOPE],
                                                                                    default_scopes=[READ_SCOPE])),
        )
        register_read_tools(server, app.state.database)
        return server.streamable_http_app()

    transport = build_transport()

    # Keep the SDK routes exact. The application's frontend remains the fallback for other paths.
    class Transport:
        async def __call__(self, scope, receive, send):
            if scope["path"] == "/token":
                request = Request(scope, receive)
                body = await request.body()
                params = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
                if "resource" in params and params["resource"] != [auth.resource]:
                    response = JSONResponse({"error": "invalid_target"}, status_code=400)
                    return await response(scope, receive, send)
                delivered = False

                async def replay():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    return await receive()

                return await app.state.mcp_transport(scope, replay, send)
            await app.state.mcp_transport(scope, receive, send)

    endpoint = Transport()
    for route in transport.routes:
        if isinstance(route, Route):
            methods = ["GET", "POST", "DELETE"] if route.path == "/mcp" else route.methods
            if route.path == "/authorize":
                methods = ["GET"]
            app.router.routes.append(Route(route.path, endpoint, methods=methods))

    base_lifespan = app.router.lifespan_context

    # SDK session managers are single-use. Create one per application lifespan.
    @asynccontextmanager
    async def lifespan(application):
        application.state.mcp_transport = build_transport()
        async with base_lifespan(application), application.state.mcp_transport.router.lifespan_context(application.state.mcp_transport):
            yield

    app.router.lifespan_context = lifespan
