"""
Pure-ASGI middleware (no BaseHTTPMiddleware: it would buffer and break streaming/WebSocket behaviour).

  RequestContextMiddleware     X-Request-ID on every response + a contextvar for log correlation
  BodySizeLimitMiddleware      413 for request bodies over MAX_REQUEST_BYTES (declared or streamed)
  SecurityHeadersMiddleware    hardening headers on every HTTP response
"""

import re
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def _header(scope: Scope, name: bytes) -> str | None:
    for k, v in scope.get("headers", []):
        if k == name:
            return v.decode("latin-1")
    return None


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = _header(scope, b"x-request-id")
        rid = incoming if incoming and _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        scope["request_id"] = rid  # survives past this middleware: the 500 handler runs OUTSIDE it
        token = request_id_var.set(rid)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-request-id", rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id_var.reset(token)


class _TooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = settings.MAX_REQUEST_BYTES
        declared = _header(scope, b"content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            await self._reject(send)
            return
        seen = 0
        overflow = False
        answered = False

        async def counting_receive() -> Message:
            nonlocal seen, overflow
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    overflow = True
                    raise _TooLarge()
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal answered
            if overflow:  # the app failed while reading an over-limit body: its answer (400/500) is replaced by a 413
                if not answered:
                    answered = True
                    await self._reject(send)
                return
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _TooLarge:
            if not answered:
                await self._reject(send)

    @staticmethod
    async def _reject(send: Send) -> None:
        body = b'{"detail":"Request body too large"}'
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware:
    """The API only serves JSON, so the CSP forbids everything; the interactive docs (dev only) are exempt."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_doc = scope.get("path", "").startswith(_DOC_PATHS)

        async def send_secure(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                existing = {k.lower() for k, _ in headers}
                extra = {
                    b"x-content-type-options": b"nosniff",
                    b"referrer-policy": b"no-referrer",
                    b"x-frame-options": b"DENY",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
                    b"cross-origin-resource-policy": b"same-site",
                }
                if not is_doc:
                    extra[b"content-security-policy"] = b"default-src 'none'; frame-ancestors 'none'"
                    extra[b"cache-control"] = b"no-store"  # API responses are per-user: never cached
                if settings.is_production and settings.COOKIE_SECURE:  # HTTPS is enforced: pin it
                    extra[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
                headers.extend((k, v) for k, v in extra.items() if k not in existing)
            await send(message)

        await self.app(scope, receive, send_secure)
