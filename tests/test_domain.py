"""Domain unit tests: money formatting, GST maths, MSMED interest, the ladder."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from app.domain import ledger
from app.domain import reminders as ladder
from app.domain.gst import (
    compute_tax,
    gstin_is_wellformed,
    next_invoice_number,
    pan_is_wellformed,
    series_for,
)
from app.domain.money import (
    add_months,
    amount_in_words,
    financial_year,
    format_paise,
    paise_to_decimal,
    rupees_to_paise,
)
from app.domain.msmed import ageing_buckets, compound_interest, stage_for, statutory_due_date

# --- Money -----------------------------------------------------------------

def test_indian_digit_grouping():
    assert format_paise(12345678) == "\u20b91,23,456.78"
    assert format_paise(50000000) == "\u20b95,00,000.00"
    assert format_paise(100) == "\u20b91.00"
    assert format_paise(0) == "\u20b90.00"
    # Above one crore the first group is the crores (Indian numbering).
    assert format_paise(1234567890) == "\u20b91,23,45,678.90"
    assert format_paise(10000000000) == "\u20b910,00,00,000.00"
    assert format_paise(123456789012) == "\u20b91,23,45,67,890.12"
    assert format_paise(-50000000) == "-\u20b95,00,000.00"


def test_rupee_parsing_accepts_indian_forms():
    assert rupees_to_paise("1,23,456.78") == 12345678
    assert rupees_to_paise("Rs 1234.5") == 123450
    assert rupees_to_paise("\u20b924000") == 2400000
    assert rupees_to_paise("INR 500") == 50000
    assert rupees_to_paise(24000) == 2400000


def test_rupee_parsing_rejects_junk():
    for bad in ["", "abc", "12.3.4", "-5", None]:
        with pytest.raises(ValueError):
            rupees_to_paise(bad)  # type: ignore[arg-type]


def test_amount_in_words_indian_numbering():
    assert amount_in_words(50000000) == "Rupees Five Lakh Only"
    assert "Lakh Twenty Three Thousand" in amount_in_words(12345678)
    assert amount_in_words(0) == "Rupees Zero Only"
    assert amount_in_words(150) == "Rupees One and Paise Fifty Only"
    assert amount_in_words(1000000000) == "Rupees One Crore Only"


def test_paise_round_trip():
    assert paise_to_decimal(12345678) == Decimal("123456.78")


def test_financial_year_boundary():
    assert financial_year(dt.date(2026, 4, 1)) == "2026-27"
    assert financial_year(dt.date(2027, 3, 31)) == "2026-27"
    assert financial_year(dt.date(2027, 2, 1)) == "2026-27"
    assert financial_year(dt.date(2026, 3, 31)) == "2025-26"


def test_add_months_clamps_day():
    assert add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)
    assert add_months(dt.date(2026, 12, 15), 1) == dt.date(2027, 1, 15)


# --- GST -------------------------------------------------------------------

def test_intra_state_splits_cgst_sgst_equally():
    tax = compute_tax(
        subtotal_paise=10000000,
        supplier_state_code="27",
        place_of_supply_state_code="27",
        gst_registered=True,
    )
    assert tax.cgst_paise == 900000
    assert tax.sgst_paise == 900000
    assert tax.igst_paise == 0
    assert tax.total_paise == 11800000
    assert tax.is_interstate is False


def test_inter_state_charges_igst():
    tax = compute_tax(
        subtotal_paise=2400000,
        supplier_state_code="27",
        place_of_supply_state_code="29",
        gst_registered=True,
    )
    assert tax.igst_paise == 432000
    assert tax.cgst_paise == 0
    assert tax.total_paise == 2832000
    assert tax.is_interstate is True


def test_unregistered_supplier_charges_no_tax():
    tax = compute_tax(
        subtotal_paise=10000000,
        supplier_state_code="27",
        place_of_supply_state_code="29",
        gst_registered=False,
    )
    assert tax.total_tax_paise == 0
    assert tax.total_paise == 10000000
    assert tax.is_interstate is False


def test_discount_reduces_taxable_value():
    tax = compute_tax(
        subtotal_paise=10000000,
        discount_paise=1000000,
        supplier_state_code="27",
        place_of_supply_state_code="27",
        gst_registered=True,
    )
    assert tax.taxable_value_paise == 9000000
    assert tax.cgst_paise == 810000
    assert tax.total_paise == 10620000


def test_discount_cannot_exceed_subtotal():
    with pytest.raises(ValueError):
        compute_tax(
            subtotal_paise=100,
            discount_paise=200,
            supplier_state_code="27",
            place_of_supply_state_code="27",
            gst_registered=True,
        )


def test_invoice_total_always_foots():
    """Tax components are rounded independently, so check the total is their sum."""
    for amount in range(1, 400):
        tax = compute_tax(
            subtotal_paise=amount,
            supplier_state_code="27",
            place_of_supply_state_code="27",
            gst_registered=True,
        )
        assert tax.total_paise == tax.taxable_value_paise + tax.cgst_paise + tax.sgst_paise


def test_gstin_and_pan_validation():
    assert gstin_is_wellformed("27AAPFU0939F1ZV") is True
    assert gstin_is_wellformed("27aapfu0939f1zv") is True
    assert gstin_is_wellformed("99AAPFU0939F1ZV") is False  # unknown state code
    assert gstin_is_wellformed("27AAPFU0939F1Z") is False  # 14 chars
    assert gstin_is_wellformed("") is False
    assert pan_is_wellformed("AAPFU0939F") is True
    assert pan_is_wellformed("AA9FU0939F") is False


def test_invoice_number_fits_rule_46_limit():
    number = next_invoice_number("INV", 1)
    assert len(number) <= 16
    assert number == "INV0001"
    assert series_for(dt.date(2026, 5, 1), "SDW").endswith("2026-27")


# --- MSMED -----------------------------------------------------------------

def test_statutory_due_date_is_45_days():
    assert statutory_due_date(dt.date(2026, 1, 1)) == dt.date(2026, 2, 15)
    assert statutory_due_date(dt.date(2026, 1, 1), agreed_days=30) == dt.date(2026, 1, 31)


def test_interest_not_invented_when_rate_unknown():
    result = compound_interest(
        principal_paise=10000000,
        due_date=dt.date(2026, 1, 1),
        as_of=dt.date(2026, 10, 1),
        rbi_bank_rate_percent=None,
    )
    assert result.verified is False
    assert result.compound_interest_paise == 0
    assert result.total_payable_paise == 10000000
    assert "not configured" in result.note


def test_interest_computed_at_three_times_bank_rate():
    result = compound_interest(
        principal_paise=10000000,
        due_date=dt.date(2026, 1, 1),
        as_of=dt.date(2026, 10, 1),
        rbi_bank_rate_percent=Decimal("5.5"),
    )
    assert result.verified is True
    assert result.annual_rate_percent == Decimal("16.50")
    assert result.compound_interest_paise > 0
    assert result.total_payable_paise == 10000000 + result.compound_interest_paise


def test_interest_is_zero_when_not_overdue():
    result = compound_interest(
        principal_paise=10000000,
        due_date=dt.date(2026, 12, 1),
        as_of=dt.date(2026, 10, 1),
        rbi_bank_rate_percent=Decimal("5.5"),
    )
    assert result.days_overdue == 0
    assert result.compound_interest_paise == 0


@pytest.mark.parametrize(
    "days,expected",
    [
        (-30, "upcoming"),
        (-1, "due_soon"),
        (0, "due_today"),
        (10, "overdue"),
        (45, "escalated"),
        (75, "statutory"),
        (100, "final"),
        (200, "legal_candidate"),
    ],
)
def test_stage_progression(days, expected):
    due = dt.date(2026, 1, 1)
    stage = stage_for(
        status="issued",
        due_date=due,
        total_paise=100,
        outstanding_paise=100,
        as_of=due + dt.timedelta(days=days),
    )
    assert stage == expected


def test_stage_respects_settled_and_draft():
    # A settled invoice reports paid, whatever the dates say.
    assert (
        stage_for(status="paid", due_date=dt.date(2020, 1, 1), total_paise=1, outstanding_paise=0, as_of=dt.date(2026, 1, 1))
        == "paid"
    )
    # A draft has never been sent, so it is not in a chasing stage yet.
    assert (
        stage_for(status="draft", due_date=dt.date(2020, 1, 1), total_paise=1, outstanding_paise=1, as_of=dt.date(2026, 1, 1))
        == "upcoming"
    )
    # Once issued and overdue, the stage escalates.
    assert (
        stage_for(status="issued", due_date=dt.date(2020, 1, 1), total_paise=1, outstanding_paise=1, as_of=dt.date(2026, 1, 1))
        == "legal_candidate"
    )


def test_ageing_buckets():
    as_of = dt.date(2026, 6, 30)
    rows = [
        (dt.date(2026, 7, 10), 100),   # current
        (dt.date(2026, 6, 20), 200),   # 1-30
        (dt.date(2026, 5, 20), 300),   # 31-60
        (dt.date(2026, 4, 20), 400),   # 61-90
        (dt.date(2026, 1, 1), 500),    # 90+
        (dt.date(2026, 1, 1), 0),      # ignored
    ]
    buckets = ageing_buckets(as_of, rows)
    assert buckets == {"current": 100, "1-30": 200, "31-60": 300, "61-90": 400, "90+": 500}


# --- Reminder ladder -------------------------------------------------------

def test_ladder_has_nine_steps_ending_in_final_notice():
    steps = ladder.steps_for()
    assert len(steps) == 9
    assert steps[0].stage == "pre_due"
    assert steps[-1].stage == "overdue_60"
    assert steps[-1].requires_human is True
    # Only the final notice needs a person; everything before it is automatic.
    assert sum(1 for s in steps if s.requires_human) == 1


def test_ladder_is_ordered_by_offset():
    offsets = [s.offset_days for s in ladder.steps_for()]
    assert offsets == sorted(offsets)


def test_escalation_off_truncates_the_ladder():
    steps = ladder.steps_for(escalation_enabled=False)
    assert all(s.index <= 3 for s in steps)
    assert len(steps) < 9


def test_mixed_script_rendering_has_no_unsubstituted_placeholders():
    ctx = {
        "contact": "\u0930\u092e\u0947\u0936",
        "customer_name": "Verma Traders",
        "invoice_no": "SDW/26/0001",
        "amount": format_paise(2832000),
        "amount_plain": "28320.00",
        "outstanding": format_paise(2832000),
        "outstanding_plain": "28320.00",
        "due_date": "04 Oct 2026",
        "issue_date": "19 Sep 2026",
        "days_overdue": "7",
        "description_line": "\nDetails: website\n",
        "pay_link": "https://example.in/pay/abc",
        "plan_link": "https://example.in/pay/abc/plan",
        "org_name": "Sharma Digital Works",
        "org_contact": "+919000000000",
    }
    for locale in ("en", "hi"):
        for template in ladder.TEMPLATES["en"]:
            body = ladder.render(template, locale=locale, context=ctx)
            assert body, f"{template}/{locale} rendered empty"
            assert "{" not in body, f"{template}/{locale} left a placeholder"
            assert "}" not in body, f"{template}/{locale} left a placeholder"


def test_every_stage_maps_to_a_template():
    for step in ladder.LADDER:
        assert ladder.template_for_stage(step.stage) in ladder.TEMPLATES["en"]


def test_schedule_datetime_is_10am_ist():
    # 10:00 IST is 04:30 UTC.
    when = ladder.schedule_datetime(dt.date(2026, 10, 1), 0)
    assert when.hour == 4 and when.minute == 30
    assert when.date() == dt.date(2026, 10, 1)


# --- Ledger ----------------------------------------------------------------

def test_ledger_outstanding_never_negative():
    class Fake:
        total_paise = 100
        paid_paise = 500
        credited_paise = 0
        written_off_paise = 0

    assert ledger.ledger_of(Fake()).outstanding_paise == 0


def test_status_transitions():
    assert ledger.can_transition("draft", "issued")
    assert ledger.can_transition("issued", "paid")
    assert not ledger.can_transition("paid", "issued")
    assert not ledger.can_transition("draft", "paid")
