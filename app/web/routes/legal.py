"""Legal pages: privacy policy, terms, refund policy, grievance officer.

Written to match what the product actually does — a policy that describes a
different product is worse than none. Data-protection specifics are tracked in
``research/05-dpdp-messaging-hosting.md``; anything a lawyer must confirm is in
docs/HUMAN_TODO.md rather than asserted here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.web.deps import db_session, ensure_csrf
from app.web.templating import render

router = APIRouter(prefix="/legal")


def _common() -> dict[str, str]:
    settings = get_settings()
    return {
        "entity_line": "Operated by the business named on this site's contact page.",
        "version": "2026-10-01",
        "support_email": settings.smtp_from,
        "log_retention_days": str(settings.log_retention_days),
        "cert_in_hours": str(settings.cert_in_report_hours),
        "complaint_window_hours": str(settings.complaint_window_hours),
    }


@router.get("/privacy")
async def privacy(request: Request, session: Session = Depends(db_session)):
    ensure_csrf(request)
    return render(request, "legal_privacy.html", _common())


@router.get("/terms")
async def terms(request: Request, session: Session = Depends(db_session)):
    ensure_csrf(request)
    return render(request, "legal_terms.html", _common())


@router.get("/refund")
async def refund(request: Request, session: Session = Depends(db_session)):
    ensure_csrf(request)
    return render(request, "legal_refund.html", _common())


@router.get("/grievance")
async def grievance(request: Request, session: Session = Depends(db_session)):
    ensure_csrf(request)
    return render(request, "legal_grievance.html", _common())
