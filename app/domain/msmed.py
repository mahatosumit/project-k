"""MSMED Act interest and recovery-stage modelling.

Facts used here (see research/01-problems-and-competitors.md and DECISIONS.md):

* MSMED Act, 2006 s.15: a buyer must pay a registered micro/small enterprise
  within **45 days** of acceptance (where there is no agreed period, the
  statutory ceiling applies).
* s.16: on default, the buyer pays **compound interest at three times the
  bank rate notified by the RBI**.

The exact notified bank rate is *configuration*, never hard-coded here, because
it changes: set ``RBI_BANK_RATE_PERCENT`` and re-verify against the RBI before
quoting a figure to a customer. If it is unset, we return the statutory
multiplier and mark the output as unverified rather than inventing a rate.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.money import add_months

STATUTORY_PAYMENT_DAYS = 45
INTEREST_MULTIPLIER = Decimal("3")


@dataclass(frozen=True)
class InterestResult:
    principal_paise: int
    days_overdue: int
    monthly_rate_percent: Decimal | None
    annual_rate_percent: Decimal | None
    compound_interest_paise: int
    total_payable_paise: int
    verified: bool
    note: str
    assumptions: list[str] = field(default_factory=list)


def statutory_due_date(acceptance_date: dt.date, agreed_days: int | None = None) -> dt.date:
    """s.15: 45 days where no period is agreed, otherwise the agreed period."""
    days = STATUTORY_PAYMENT_DAYS if agreed_days is None else max(0, int(agreed_days))
    return acceptance_date + dt.timedelta(days=days)


def compound_interest(
    *,
    principal_paise: int,
    due_date: dt.date,
    as_of: dt.date,
    rbi_bank_rate_percent: float | Decimal | None,
) -> InterestResult:
    """Compound interest under MSMED s.16, compounded monthly.

    The Act says "compound interest ... at three times the bank rate". It does
    not prescribe a compounding interval in the statute text we could verify, so
    we compound monthly, state that plainly, and mark the whole result as
    unverified until the rate is set and the basis confirmed by a professional.
    """
    if principal_paise < 0:
        raise ValueError("principal must not be negative")

    days = max(0, (as_of - due_date).days)
    if rbi_bank_rate_percent is None or Decimal(str(rbi_bank_rate_percent)) <= 0:
        return InterestResult(
            principal_paise=principal_paise,
            days_overdue=days,
            monthly_rate_percent=None,
            annual_rate_percent=None,
            compound_interest_paise=0,
            total_payable_paise=principal_paise,
            verified=False,
            note=(
                "RBI notified bank rate not configured, so no interest figure is shown. "
                "MSMED s.16 provides compound interest at 3x the RBI bank rate — set "
                "RBI_BANK_RATE_PERCENT after verifying the current rate on rbi.org.in."
            ),
            assumptions=["No interest computed. Rate unknown."],
        )

    bank_rate = Decimal(str(rbi_bank_rate_percent))
    annual = bank_rate * INTEREST_MULTIPLIER
    monthly = annual / Decimal(12)
    months = Decimal(days) / Decimal("30.4375")

    interest = (Decimal(principal_paise) * ((Decimal(1) + monthly / Decimal(100)) ** months)) - Decimal(
        principal_paise
    )
    interest_paise = int(interest.to_integral_value(rounding="ROUND_HALF_UP"))

    return InterestResult(
        principal_paise=principal_paise,
        days_overdue=days,
        monthly_rate_percent=monthly.quantize(Decimal("0.001")),
        annual_rate_percent=annual.quantize(Decimal("0.01")),
        compound_interest_paise=interest_paise,
        total_payable_paise=principal_paise + interest_paise,
        verified=True,
        note=(
            f"Compound interest at 3 x {bank_rate}% = {annual}% p.a., compounded monthly "
            f"over {days} days. Confirm the rate and the compounding basis with a professional."
        ),
        assumptions=[
            "Interest compounded monthly.",
            "Day count approximated as days/30.4375 months.",
            "Statutory 45-day payment window applied where no period was agreed.",
        ],
    )


# --- Recovery stage model --------------------------------------------------

STAGES: tuple[str, ...] = (
    "upcoming",       # not yet due
    "due_soon",       # due within the reminder window
    "due_today",
    "overdue",        # 1-30 days
    "escalated",      # 31-60 days
    "statutory",      # past the MSMED 45-day threshold and above escalation
    "final",          # final demand issued
    "legal_candidate",  # ready for MSME Samadhaan / MSEFC, human decides
    "paid",
    "written_off",
)


def stage_for(
    *,
    status: str,
    due_date: dt.date,
    total_paise: int,
    outstanding_paise: int,
    as_of: dt.date,
    escalation_enabled: bool = True,
    reminder_days_before: int = 3,
) -> str:
    """Map an invoice to a recovery stage. Paid/void/draft always win."""
    if status == "draft":
        # Nothing has been sent and no ladder is running, so no chasing stage
        # applies yet however old the due date is.
        return "upcoming"
    if status in {"paid", "cancelled"}:
        return "paid" if status == "paid" else "written_off"
    if status == "written_off":
        return "written_off"
    if outstanding_paise <= 0 < total_paise:
        return "paid"

    days = (as_of - due_date).days
    if days < 0:
        return "due_soon" if -days <= reminder_days_before else "upcoming"
    if days == 0:
        return "due_today"
    if not escalation_enabled:
        return "overdue"
    if days <= 30:
        return "overdue"
    if days <= 60:
        return "escalated"
    if days <= 90:
        return "statutory"
    if days <= 120:
        return "final"
    return "legal_candidate"


def stage_label(stage: str, locale: str = "en") -> str:
    en = {
        "upcoming": "Not yet due",
        "due_soon": "Due soon",
        "due_today": "Due today",
        "overdue": "Overdue",
        "escalated": "Escalated",
        "statutory": "Past MSMED 45-day limit",
        "final": "Final demand",
        "legal_candidate": "Recovery route available",
        "paid": "Paid",
        "written_off": "Written off",
    }
    hi = {
        "upcoming": "अभी देय नहीं",
        "due_soon": "जल्द देय",
        "due_today": "आज देय",
        "overdue": "बकाया",
        "escalated": "सख्ती से माँगा गया",
        "statutory": "MSMED 45-दिन की सीमा पार",
        "final": "अंतिम मांग",
        "legal_candidate": "वसूली मार्ग उपलब्ध",
        "paid": "भुगतान हो गया",
        "written_off": "बट्टे खाते",
    }
    return (hi if locale == "hi" else en).get(stage, stage)


def escalation_checklist(*, msme_registered: bool, days_overdue: int, locale: str = "en") -> list[dict[str, str]]:
    """An evidence pack checklist. This is *not* legal advice; it is a reminder
    of the documents a buyer typically challenges, plus where to file."""
    if locale == "hi":
        items = [
            {"id": "invoice", "text": "कर चालान की प्रति (नंबर, दिनांक, राशि)", "required": "yes"},
            {"id": "proof", "text": "परियोजना/सेवा पूरी होने का प्रमाण (ईमेल, शिकायत रहित स्वीकृति)", "required": "yes"},
            {"id": "ledger", "text": "खाता विवरण (सभी भुगतान और शेष)", "required": "yes"},
            {"id": "demand", "text": "लिखित मांग पत्र की प्रति और भेजने का प्रमाण", "required": "yes"},
            {"id": "udhyam", "text": "उद्यम/Udyam पंजीकरण प्रमाण", "required": "yes" if msme_registered else "recommended"},
            {"id": "msme", "text": "MSME Samadhaan पोर्टल पर शिकायत (45 दिन पार)", "required": "yes" if days_overdue > 45 else "later"},
        ]
    else:
        items = [
            {"id": "invoice", "text": "Copy of the tax invoice (number, date, amount)", "required": "yes"},
            {"id": "proof", "text": "Proof of delivery/acceptance (email, complaint-free sign-off)", "required": "yes"},
            {"id": "ledger", "text": "Statement of account showing all payments and the balance", "required": "yes"},
            {"id": "demand", "text": "Copy of the written demand and proof it was sent", "required": "yes"},
            {"id": "udhyam", "text": "Udyam / MSME registration proof", "required": "yes" if msme_registered else "recommended"},
            {"id": "msme", "text": "MSME Samadhaan complaint (available past 45 days)", "required": "yes" if days_overdue > 45 else "later"},
        ]
    return items


def ageing_buckets(as_of: dt.date, rows: list[tuple[dt.date, int]]) -> dict[str, int]:
    """Standard receivables ageing. ``rows`` is (due_date, outstanding_paise)."""
    buckets = {"current": 0, "1-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    for due, amount in rows:
        if amount <= 0:
            continue
        days = (as_of - due).days
        if days <= 0:
            buckets["current"] += amount
        elif days <= 30:
            buckets["1-30"] += amount
        elif days <= 60:
            buckets["31-60"] += amount
        elif days <= 90:
            buckets["61-90"] += amount
        else:
            buckets["90+"] += amount
    return buckets


__all__ = [
    "INTEREST_MULTIPLIER",
    "STAGES",
    "STATUTORY_PAYMENT_DAYS",
    "InterestResult",
    "add_months",
    "ageing_buckets",
    "compound_interest",
    "escalation_checklist",
    "stage_for",
    "stage_label",
    "statutory_due_date",
]
