"""Indian money and date helpers.

Everything is integer paise. Formatting uses Indian digit grouping (lakh/crore),
and amounts are delivered in words as an Indian invoice requires
(``Rupees ... and Paise ... Only``).
"""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

PAISE = 100

_UNITS = [
    "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def rupees_to_paise(value: str | float | int | Decimal) -> int:
    """Parse a rupee amount (from a form) into paise, round-half-up.

    Accepts '1,23,456.78', '₹1234', '1234.5'. Raises ValueError on junk.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value * PAISE
    if isinstance(value, Decimal):
        dec = value
    else:
        raw = str(value).strip()
        if not raw:
            raise ValueError("amount is empty")
        # Accept the prefixes people actually type: Rs, Rs., INR, ₹, and spaces
        # used as Indian digit grouping.
        raw = raw.replace(",", "").replace("\u20b9", "").strip()
        for prefix in ("INR", "Rs.", "Rs", "Rupees", "rupees"):
            if raw.startswith(prefix):
                raw = raw[len(prefix):].strip()
                break
        if raw.startswith("+"):
            raw = raw[1:]
        if not raw:
            raise ValueError("amount is empty")
        try:
            dec = Decimal(raw)
        except Exception as exc:
            raise ValueError(f"invalid amount: {value!r}") from exc
    if dec.is_nan() or dec.is_infinite():
        raise ValueError("invalid amount")
    if dec < 0:
        raise ValueError("amount must not be negative")
    return int((dec * PAISE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def paise_to_decimal(paise: int) -> Decimal:
    return (Decimal(paise) / PAISE).quantize(Decimal("0.01"))


def format_paise(paise: int, symbol: bool = True, decimals: bool = True) -> str:
    """Format paise with Indian digit grouping: 12345678 paise -> '₹1,23,456.78'."""
    negative = paise < 0
    paise = abs(int(paise))
    whole, frac = divmod(paise, PAISE)
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts: list[str] = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    out = f"{s}.{frac:02d}" if decimals else s
    if symbol:
        out = "\u20b9" + out
    return ("-" + out) if negative else out


def format_paise_plain(paise: int) -> str:
    """Format without the rupee symbol — safest for SMS/WhatsApp ASCII paths."""
    return format_paise(paise, symbol=False)


def _two_digits(n: int) -> str:
    if n < 20:
        return _UNITS[n]
    tens, unit = divmod(n, 10)
    return _TENS[tens] + (f" {_UNITS[unit]}" if unit else "")


def _three_digits(n: int) -> str:
    if n < 100:
        return _two_digits(n)
    hundreds, rest = divmod(n, 100)
    return f"{_UNITS[hundreds]} Hundred" + (f" {_two_digits(rest)}" if rest else "")


def amount_in_words(paise: int) -> str:
    """Indian numbering: crore / lakh / thousand. e.g. 12345678 paise.

    12345678 paise = 123456.78 rupees -> 'Rupees One Lakh Twenty Three Thousand
    Four Hundred Fifty Six and Paise Seventy Eight Only'
    """
    negative = paise < 0
    paise = abs(int(paise))
    whole, frac = divmod(paise, PAISE)
    if whole == 0 and frac == 0:
        return "Rupees Zero Only"

    crore, rest = divmod(whole, 10_000_000)
    lakh, rest = divmod(rest, 100_000)
    thousand, rest = divmod(rest, 1000)
    hundred = rest

    parts: list[str] = []
    if crore:
        parts.append(f"{_three_digits(crore)} Crore" if crore > 99 else f"{_two_digits(crore)} Crore")
    if lakh:
        parts.append(f"{_two_digits(lakh)} Lakh")
    if thousand:
        parts.append(f"{_two_digits(thousand)} Thousand")
    if hundred:
        parts.append(_three_digits(hundred))

    words = "Rupees " + (" ".join(parts) if parts else "Zero")
    if frac:
        words += f" and Paise {_two_digits(frac)}"
    if negative:
        words = "Minus " + words
    return words + " Only"


def financial_year(d: dt.date, start_month: int = 4) -> str:
    """Indian FY label: 2026-04-01 -> '2026-27'; 2027-02-01 -> '2026-27'."""
    year = d.year if d.month >= start_month else d.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


def add_months(d: dt.date, months: int) -> dt.date:
    """Add months, clamping the day (31 Jan + 1 month -> 28/29 Feb)."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = d.day
    while day > 1:
        try:
            return dt.date(year, month, day)
        except ValueError:
            day -= 1
    return dt.date(year, month, 1)


def days_between(a: dt.date, b: dt.date) -> int:
    return (b - a).days


def today_ist() -> dt.date:
    """Current date in IST (UTC+05:30) — no external tz database needed."""
    return (dt.datetime.now(dt.UTC) + dt.timedelta(hours=5, minutes=30)).date()


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)
