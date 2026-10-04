"""GST calculation for an India-only B2B SaaS.

Rules applied (see research/03-gst-and-tax.md for the cited sources):

* A supplier who is **not registered** must not charge GST — the invoice is a
  plain invoice with no tax lines.
* Once registered, an **intra-state** supply (supplier state == place of supply)
  splits the tax equally into CGST + SGST; an **inter-state** supply attracts
  IGST (IGST Act 2017, ss.7-8 with s.12(2)(a) place-of-supply for B2B).
* SAC for this service: 998314 (IT design & development services), 18%.
* Rounding: each tax component is rounded half-up to the paise; the invoice
  total is the sum of the rounded components, so the invoice always foots.

This module computes; it does not advise. Rates and thresholds must be
re-verified against CBIC before filing (see docs/DECISIONS.md).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.domain.money import financial_year

DEFAULT_SAC = "998314"
DEFAULT_GST_RATE = Decimal("18")

# State codes used for the place-of-supply comparison. Kept minimal on purpose:
# we only ever need equality against the supplier's own state code.
STATE_CODES: dict[str, str] = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana", "07": "Delhi",
    "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala",
    "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman and Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}


def state_name(code: str | None) -> str:
    if not code:
        return ""
    return STATE_CODES.get(str(code).zfill(2), "")


def _round_paise(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class TaxBreakdown:
    taxable_value_paise: int
    discount_paise: int
    gst_rate_percent: Decimal
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    total_paise: int
    is_interstate: bool
    reverse_charge: bool
    gst_registered: bool

    @property
    def total_tax_paise(self) -> int:
        return self.cgst_paise + self.sgst_paise + self.igst_paise


def compute_tax(
    *,
    subtotal_paise: int,
    discount_paise: int = 0,
    supplier_state_code: str | None,
    place_of_supply_state_code: str | None,
    gst_registered: bool,
    gst_rate_percent: Decimal | float | str | None = None,
    reverse_charge: bool = False,
) -> TaxBreakdown:
    """Compute the tax lines and total for one invoice."""
    if subtotal_paise < 0:
        raise ValueError("subtotal must not be negative")
    if discount_paise < 0:
        raise ValueError("discount must not be negative")
    if discount_paise > subtotal_paise:
        raise ValueError("discount cannot exceed the subtotal")

    rate = Decimal(str(gst_rate_percent)) if gst_rate_percent is not None else DEFAULT_GST_RATE
    if rate < 0 or rate > 100:
        raise ValueError("gst rate out of range")

    taxable = subtotal_paise - discount_paise
    supplier = str(supplier_state_code).zfill(2) if supplier_state_code else None
    pos = str(place_of_supply_state_code).zfill(2) if place_of_supply_state_code else None

    # Interstate is only meaningful when registered and both states are known.
    interstate = bool(gst_registered and supplier and pos and supplier != pos)

    if not gst_registered:
        return TaxBreakdown(
            taxable_value_paise=taxable,
            discount_paise=discount_paise,
            gst_rate_percent=Decimal("0"),
            cgst_paise=0,
            sgst_paise=0,
            igst_paise=0,
            total_paise=taxable,
            is_interstate=False,
            reverse_charge=reverse_charge,
            gst_registered=False,
        )

    if interstate:
        igst = _round_paise(Decimal(taxable) * rate / Decimal(100))
        cgst = sgst = 0
    else:
        # Split the rate in half, then round each half independently.
        half = rate / Decimal(2)
        cgst = _round_paise(Decimal(taxable) * half / Decimal(100))
        sgst = _round_paise(Decimal(taxable) * half / Decimal(100))
        igst = 0

    total = taxable + cgst + sgst + igst
    return TaxBreakdown(
        taxable_value_paise=taxable,
        discount_paise=discount_paise,
        gst_rate_percent=rate,
        cgst_paise=cgst,
        sgst_paise=sgst,
        igst_paise=igst,
        total_paise=total,
        is_interstate=interstate,
        reverse_charge=reverse_charge,
        gst_registered=True,
    )


def gstin_is_wellformed(gstin: str | None) -> bool:
    """Structural check only: 2 digits + 10 char PAN + entity + Z + checksum.

    This validates the documented format; it does not prove the GSTIN exists.
    """
    if not gstin:
        return False
    g = gstin.strip().upper()
    if len(g) != 15:
        return False
    if not g[:2].isdigit():
        return False
    if not g[2:12].isalnum():
        return False
    if not g[12].isalnum():
        return False
    if g[13] != "Z":
        return False
    if not g[14].isalnum():
        return False
    return g[:2] in STATE_CODES


def pan_is_wellformed(pan: str | None) -> bool:
    if not pan:
        return False
    p = pan.strip().upper()
    return len(p) == 10 and p[:5].isalpha() and p[5:9].isdigit() and p[9].isalpha()


def next_invoice_number(prefix: str, sequence: int) -> str:
    """Consecutive, <=16 chars, unique per financial year (Rule 46(b))."""
    number = f"{prefix}{sequence:04d}"
    return number[:16]


def series_for(issue_date: dt.date, prefix: str | None = None) -> str:
    fy = financial_year(issue_date)
    return f"{prefix or 'INV'}-{fy}"[:16]


def invoice_number_for(prefix: str, fy_label: str, sequence: int) -> str:
    return f"{prefix}/{fy_label.split('-')[-1]}/{sequence:04d}"[:16]


def invoice_due_date(issue_date: dt.date, days: int = 15) -> dt.date:
    return issue_date + dt.timedelta(days=max(0, int(days)))
