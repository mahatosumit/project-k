"""Public routes: landing page, health, status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.web.deps import db_session, ensure_csrf
from app.web.templating import render

router = APIRouter()


@router.get("/")
async def landing(request: Request):
    ensure_csrf(request)
    return render(request, "landing.html")


@router.get("/healthz")
async def healthz(session: Session = Depends(db_session)):
    """Liveness + readiness: must touch the database to be meaningful."""
    try:
        session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    settings = get_settings()
    body = {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "environment": settings.environment,
        "payment_provider": settings.payment_provider,
    }
    return JSONResponse(body, status_code=200 if db_ok else 503)


@router.get("/readyz")
async def readyz(session: Session = Depends(db_session)):
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"ready": False}, status_code=503)
    return JSONResponse({"ready": True})


@router.get("/pricing")
async def pricing(request: Request):
    ensure_csrf(request)
    return render(request, "pricing.html")
