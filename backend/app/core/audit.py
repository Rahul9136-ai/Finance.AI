"""Audit middleware — records every mutating request with actor + outcome."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.security import decode_token
from app.db.session import SessionLocal
from app.models.audit import AuditLog

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
SKIP_PATHS = ("/api/auth/login", "/api/auth/refresh")


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.method not in MUTATING or request.url.path in SKIP_PATHS:
            return response

        actor_email, user_id, org_id = "", None, None
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            payload = decode_token(auth[7:])
            if payload:
                user_id = int(payload.get("sub")) if payload.get("sub") else None
                org_id = payload.get("org_id")

        try:
            db = SessionLocal()
            db.add(AuditLog(
                org_id=org_id, user_id=user_id, actor_email=actor_email,
                action=f"{request.method} {request.url.path}",
                method=request.method, path=request.url.path,
                status_code=response.status_code,
            ))
            db.commit()
            db.close()
        except Exception:
            pass  # auditing must never break the request path
        return response
