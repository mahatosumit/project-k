"""Customer portal link construction.

Kept in the service layer (not in a route module) because three places need it:
the pay routes, the merchant's invoice screen, and the reminder messages. Each
invoice gets its own unguessable token derived from the customer's portal token,
so a link cannot be edited into another invoice's link.
"""

from __future__ import annotations

import hashlib
import hmac

from app.config import get_settings
from app.models import Customer, Invoice


def public_token(portal_link_key: str, invoice_id: str) -> str:
    """Per-invoice token: HMAC of (customer token, invoice id) under the app key."""
    settings = get_settings()
    return hmac.new(
        (settings.secret_key or "dev").encode(),
        f"{portal_link_key}:{invoice_id}".encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def portal_path(invoice: Invoice, customer: Customer) -> str:
    return f"/pay/{invoice.id}/{public_token(customer.portal_link_key, invoice.id)}"


def portal_link(invoice: Invoice, customer: Customer) -> str:
    settings = get_settings()
    return f"{settings.base_url}{portal_path(invoice, customer)}"


def plan_link(invoice: Invoice, customer: Customer) -> str:
    return f"{portal_link(invoice, customer)}/plan"
