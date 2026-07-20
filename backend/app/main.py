from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.audit import AuditMiddleware
from app.core.config import settings
from app.api.routers import (
    accounts, ai, auth, bills, dashboard, gl, invoices, journal, parties,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0-phase1",
        description="AI-powered ERP Accounts & Finance — the AI Finance Assistant.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AuditMiddleware)

    for module in (auth, accounts, journal, gl, parties, invoices, bills, dashboard, ai):
        app.include_router(module.router)

    @app.get("/health", tags=["ops"])
    def health():
        return {"status": "ok", "app": settings.app_name, "env": settings.env}

    return app


app = create_app()
