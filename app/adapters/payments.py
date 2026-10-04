"""Payment adapters.

Every gateway sits behind :class:`PaymentAdapter`, so adding a provider (or a
second country's gateway) means writing an adapter, not changing the product.
The same interface serves our own subscription billing.

Security rules enforced here:
* Card data never touches our servers: we only create a hosted order and hand
  the customer a checkout URL/parameters.
* Webhook signatures are verified with keyed HMAC over the **raw** body, and
  webhook handling is idempotent (see ``app/services/payments.py``).
* We trust the gateway's server-to-server lookup over any browser redirect.

Credential material is only ever passed in from configuration at call time.
Razorpay and Cashfree are integrated through their **official Python SDKs**;
neither module builds auth headers or signs requests by hand.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class PaymentError(Exception):
    """Raised for adapter/transport failures. Never carries credential values."""


@dataclass
class OrderRequest:
    amount_paise: int
    currency: str = "INR"
    receipt: str = ""
    notes: dict[str, str] = field(default_factory=dict)
    idempotency_key: str | None = None
    return_url: str = ""
    customer_id: str = ""
    customer_name: str = ""
    customer_email: str = ""
    customer_phone: str = ""


@dataclass
class OrderResult:
    provider_order_id: str
    amount_paise: int
    currency: str
    status: str
    checkout: dict[str, Any] = field(default_factory=dict)


@dataclass
class LookupResult:
    status: str          # created | paid | failed | refunded
    amount_paise: int
    payment_id: str | None = None
    method: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class WebhookResult:
    event_key: str
    event_type: str
    order_id: str | None
    payment_id: str | None
    amount_paise: int | None
    status: str          # succeeded | failed | ignored
    signature_valid: bool
    detail: str = ""


class PaymentAdapter(Protocol):
    name: str
    mode: str

    def create_order(self, req: OrderRequest) -> OrderResult: ...

    def fetch_order(self, provider_order_id: str) -> LookupResult: ...

    def verify_webhook(self, *, headers: dict[str, str], raw_body: bytes) -> WebhookResult: ...


def _headers_lower(headers: dict[str, str]) -> dict[str, str]:
    return {str(k).lower(): v for k, v in (headers or {}).items()}


def paise_to_gateway_amount(paise: int) -> int:
    """Razorpay takes INR amounts in paise; Cashfree takes rupees."""
    if paise <= 0:
        raise PaymentError("amount must be positive")
    return int(paise)


def paise_to_rupees(paise: int) -> float:
    if paise <= 0:
        raise PaymentError("amount must be positive")
    return round(paise / 100, 2)


def gateway_amount_to_paise(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _hmac_b64(key: str, message: bytes) -> str:
    return base64.b64encode(hmac.new(key.encode(), message, hashlib.sha256).digest()).decode()


def _hmac_hex(key: str, message: bytes) -> str:
    return hmac.new(key.encode(), message, hashlib.sha256).hexdigest()


# --------------------------------------------------------------------------
# Mock adapter — default in development and the deterministic test double.
# --------------------------------------------------------------------------

class MockAdapter:
    """Deterministic in-process gateway.

    Exercises the whole critical path (order -> signed webhook -> verified
    payment -> reconciliation) with no network call and no real rupee.
    """

    name = "mock"
    mode = "sandbox"

    def __init__(self, settings: Settings | None = None, verify_key: str | None = None) -> None:
        self.settings = settings
        # No literal credential here: the caller supplies a verify key, else we
        # derive one from the configured signing material so development and
        # production exercise exactly the same code path.
        self.verify_key = verify_key or get_settings().secret_key[:32]
        self._orders: dict[str, OrderResult] = {}
        self._counter = 0
        self._lock = threading.Lock()

    def create_order(self, req: OrderRequest) -> OrderResult:
        # The counter and the id are process-global so concurrent callers cannot
        # collide on an order id, which the database treats as unique.
        with self._lock:
            self._counter += 1
            oid = f"order_mock{secrets.token_hex(8)}{self._counter:04d}"
        result = OrderResult(
            provider_order_id=oid,
            amount_paise=req.amount_paise,
            currency=req.currency,
            status="created",
            checkout={
                "provider": self.name,
                "key_id": "mock_key",
                "order_id": oid,
                "amount": req.amount_paise,
                "currency": req.currency,
                "name": "Sandbox checkout",
            },
        )
        self._orders[oid] = result
        return result

    def fetch_order(self, provider_order_id: str) -> LookupResult:
        order = self._orders.get(provider_order_id)
        if order is None:
            return LookupResult(status="failed", amount_paise=0, raw={"mock": True, "reason": "unknown order"})
        resolved = "paid" if order.status == "paid" else "created"
        return LookupResult(status=resolved, amount_paise=order.amount_paise, raw={"mock": True})

    def mark_paid(self, provider_order_id: str) -> None:
        """Test helper: simulate the gateway capturing the order."""
        order = self._orders.get(provider_order_id)
        if order is not None:
            order.status = "paid"

    def sign(self, payload: bytes) -> str:
        return _hmac_hex(self.verify_key, payload)

    def build_webhook(
        self, *, order_id: str, event_key: str, failed: bool = False
    ) -> tuple[bytes, dict[str, str]]:
        """Test helper: produce a correctly signed callback body and headers.

        The payment id is derived from the order id (and the event), so it stays
        unique per order — a gateway never reuses a payment id across orders.
        """
        order = self._orders.get(order_id)
        amount = order.amount_paise if order else 0
        payment_ref = hashlib.sha256(f"{order_id}:{event_key}".encode()).hexdigest()[:16]
        body = json.dumps(
            {
                "event": "payment.failed" if failed else "payment.captured",
                "event_id": event_key,
                "payload": {
                    "payment": {
                        "entity": {
                            "id": f"pay_mock_{payment_ref}",
                            "order_id": order_id,
                            "amount": amount,
                            "currency": "INR",
                            "status": "failed" if failed else "captured",
                            "method": "upi",
                        }
                    }
                },
            },
            separators=(",", ":"),
        ).encode()
        return body, {"X-Razorpay-Signature": self.sign(body)}

    def verify_webhook(self, *, headers: dict[str, str], raw_body: bytes) -> WebhookResult:
        h = _headers_lower(headers)
        provided = h.get("x-razorpay-signature") or h.get("x-webhook-signature") or ""
        expected = self.sign(raw_body)
        valid = bool(provided) and hmac.compare_digest(provided, expected)
        return _parse_simple(body=raw_body, valid=valid)


def _parse_simple(*, body: bytes, valid: bool) -> WebhookResult:
    try:
        data = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return WebhookResult("", "", None, None, None, "failed", valid, "unparseable body")
    event_type = str(data.get("event") or data.get("type") or "")
    event_key = str(data.get("event_id") or data.get("id") or "")
    entity = ((data.get("payload") or {}).get("payment") or {}).get("entity") or data.get("data") or {}
    status = str(entity.get("status") or "")
    return WebhookResult(
        event_key=event_key,
        event_type=event_type,
        order_id=entity.get("order_id"),
        payment_id=entity.get("id"),
        amount_paise=gateway_amount_to_paise(entity.get("amount")),
        status="succeeded" if status in {"captured", "paid", "success", "SUCCESS"} else "failed",
        signature_valid=valid,
    )


# --------------------------------------------------------------------------
# Razorpay — official `razorpay` SDK
# --------------------------------------------------------------------------

class RazorpayAdapter:
    """Razorpay, via the official ``razorpay`` Python SDK.

    Webhook contract (verified; see research/04-payments-gateways.md): header
    ``X-Razorpay-Signature`` is HMAC-SHA256 of the **raw** request body keyed
    with the webhook signing material, and ``x-razorpay-event-id`` is the
    idempotency key. Event ordering is not guaranteed, so processing re-reads
    gateway state rather than trusting the order events arrive in.
    """

    name = "razorpay"

    def __init__(self, key_id: str, key_material: str, webhook_key: str, mode: str = "sandbox") -> None:
        if not key_id or not key_material:
            raise PaymentError("razorpay credentials are not configured")
        self.key_id = key_id
        self._key_material = key_material
        self._webhook_key = webhook_key or ""
        self.mode = mode if mode in {"sandbox", "live"} else "sandbox"
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import razorpay  # official SDK, pinned in requirements

            self._client = razorpay.Client(auth=(self.key_id, self._key_material))
            self._client.set_app_details({"title": "Vasool", "version": "1.0.0"})
        return self._client

    def create_order(self, req: OrderRequest) -> OrderResult:
        notes = dict(req.notes or {})
        if req.return_url:
            notes["return_url"] = req.return_url
        try:
            order = self.client.order.create(
                {
                    "amount": paise_to_gateway_amount(req.amount_paise),
                    "currency": req.currency,
                    "receipt": (req.receipt or "")[:40],
                    "notes": notes,
                    "payment_capture": 1,
                }
            )
        except Exception as exc:
            raise PaymentError(f"razorpay order create failed: {type(exc).__name__}") from exc
        return OrderResult(
            provider_order_id=str(order.get("id")),
            amount_paise=order.get("amount") or req.amount_paise,
            currency=str(order.get("currency") or "INR"),
            status=str(order.get("status") or "created"),
            checkout={
                "provider": self.name,
                "mode": self.mode,
                "key_id": self.key_id,
                "order_id": str(order.get("id")),
                "amount": order.get("amount") or req.amount_paise,
                "currency": "INR",
                "return_url": req.return_url,
            },
        )

    def fetch_order(self, provider_order_id: str) -> LookupResult:
        """Authoritative server-side check — never trust the browser redirect."""
        try:
            order = self.client.order.fetch(provider_order_id)
        except Exception as exc:
            raise PaymentError(f"razorpay order fetch failed: {type(exc).__name__}") from exc

        status = str(order.get("status") or "created")
        amount = int(order.get("amount") or 0)
        payment_id = None
        method = None
        mapped = {"paid": "paid", "attempted": "created", "created": "created"}.get(status, "failed")
        if mapped == "paid":
            try:
                payments = self.client.order.payments(provider_order_id)
                items = payments.get("items") or []
                captured = [p for p in items if str(p.get("status")) in {"captured", "authorized"}]
                chosen = captured[0] if captured else (items[0] if items else None)
                if chosen:
                    payment_id = str(chosen.get("id"))
                    method = str(chosen.get("method") or "")
                    amount = chosen.get("amount") or amount
            except Exception:
                logger.warning("razorpay payment lookup failed for %s", provider_order_id)
        return LookupResult(
            status=mapped, amount_paise=amount, payment_id=payment_id, method=method, raw={"status": status}
        )

    def verify_webhook(self, *, headers: dict[str, str], raw_body: bytes) -> WebhookResult:
        h = _headers_lower(headers)
        provided = h.get("x-razorpay-signature", "")
        valid = False
        if self._webhook_key and provided:
            valid = hmac.compare_digest(_hmac_hex(self._webhook_key, raw_body), provided)
        if not valid:
            return WebhookResult("", "", None, None, None, "failed", False, "signature invalid")

        try:
            data = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return WebhookResult("", "", None, None, None, "failed", True, "unparseable body")

        event_type = str(data.get("event") or "")
        event_key = str(data.get("id") or h.get("x-razorpay-event-id") or "")
        if not event_key:
            event_key = hashlib.sha256(raw_body).hexdigest()

        entity = ((data.get("payload") or {}).get("payment") or {}).get("entity") or {}
        status_raw = str(entity.get("status") or "")
        if event_type in {"payment.captured", "payment.authorized"} or status_raw in {"captured", "authorized"}:
            status = "succeeded"
        elif event_type in {"payment.failed", "payment.dispute.created"} or status_raw == "failed":
            status = "failed"
        else:
            status = "ignored"

        return WebhookResult(
            event_key=event_key,
            event_type=event_type,
            order_id=(str(entity["order_id"]) if entity.get("order_id") else None),
            payment_id=(str(entity["id"]) if entity.get("id") else None),
            amount_paise=gateway_amount_to_paise(entity.get("amount")),
            status=status,
            signature_valid=True,
        )


# --------------------------------------------------------------------------
# Cashfree — official `cashfree-pg` SDK
# --------------------------------------------------------------------------

class CashfreeAdapter:
    """Cashfree Payments via the official ``cashfree-pg`` SDK.

    Webhook signature: Cashfree documents
    ``Base64(HMAC_SHA256(timestamp + "." + raw_payload, key))`` from the
    ``x-webhook-signature`` and ``x-webhook-timestamp`` headers, but the
    official SDK's own ``PGVerifyWebhookSignature`` hashes
    ``timestamp + raw_payload`` with **no** separator. Both are keyed HMACs over
    the same untrusted input, so we accept either and record which one matched —
    no security is lost, and we are not blind to a gateway-side change. This
    discrepancy is logged in docs/DECISIONS.md.
    """

    name = "cashfree"
    SANDBOX = "SANDBOX"
    PRODUCTION = "PRODUCTION"

    def __init__(
        self,
        app_id: str,
        key_material: str,
        mode: str = "sandbox",
        webhook_key: str | None = None,
    ) -> None:
        if not app_id or not key_material:
            raise PaymentError("cashfree credentials are not configured")
        self.app_id = app_id
        self._key_material = key_material
        self.mode = mode if mode in {"sandbox", "live"} else "sandbox"
        self._webhook_key = webhook_key or key_material
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from cashfree_pg.api_client import Cashfree  # official SDK, pinned

            env = Cashfree.SANDBOX if self.mode == "sandbox" else Cashfree.PRODUCTION
            self._client = Cashfree(env, self.app_id, self._key_material)
        return self._client

    @staticmethod
    def _unwrap(response: Any) -> dict[str, Any]:
        """The SDK returns either a model, a dict, or an ApiResponse wrapper."""
        if response is None:
            return {}
        data = getattr(response, "data", response)
        if hasattr(data, "model_dump"):
            return data.model_dump()
        if isinstance(data, dict):
            return data
        if hasattr(data, "to_dict"):
            return data.to_dict()
        return {}

    def create_order(self, req: OrderRequest) -> OrderResult:
        from cashfree_pg.models.create_order_request import CreateOrderRequest
        from cashfree_pg.models.customer_details import CustomerDetails
        from cashfree_pg.models.order_meta import OrderMeta

        order_id = (req.receipt or "")[:45]
        customer = CustomerDetails(
            customer_id=(req.customer_id or order_id)[:50],
            customer_name=(req.customer_name or "Customer")[:100],
            customer_email=(req.customer_email or None),
            customer_phone=(req.customer_phone or None),
        )
        meta = OrderMeta(return_url=req.return_url) if req.return_url else None
        body = CreateOrderRequest(
            order_id=order_id,
            order_amount=paise_to_rupees(req.amount_paise),
            order_currency=req.currency,
            customer_details=customer,
            order_meta=meta,
            order_note=", ".join(f"{k}={v}" for k, v in (req.notes or {}).items())[:200] or None,
        )
        try:
            raw = self.client.PGCreateOrder(body, x_idempotency_key=req.idempotency_key)
        except Exception as exc:
            raise PaymentError(f"cashfree order create failed: {type(exc).__name__}") from exc
        data = self._unwrap(raw)
        amount = data.get("order_amount")
        return OrderResult(
            provider_order_id=str(data.get("order_id") or order_id),
            amount_paise=round(float(amount * 100)) if amount is not None else req.amount_paise,
            currency=str(data.get("order_currency") or "INR"),
            status=str(data.get("order_status") or "created"),
            checkout={
                "provider": self.name,
                "mode": self.mode,
                "payment_session_id": data.get("payment_session_id"),
                "order_id": str(data.get("order_id") or order_id),
                "amount": req.amount_paise,
                "currency": "INR",
                "return_url": req.return_url,
            },
        )

    def fetch_order(self, provider_order_id: str) -> LookupResult:
        try:
            raw = self.client.PGFetchOrder(provider_order_id)
        except Exception as exc:
            raise PaymentError(f"cashfree order fetch failed: {type(exc).__name__}") from exc
        data = self._unwrap(raw)
        raw_status = str(data.get("order_status") or "").upper()
        mapped = {"PAID": "paid", "ACTIVE": "created", "EXPIRED": "failed"}.get(raw_status, "failed")
        amount = data.get("order_amount")
        return LookupResult(
            status=mapped,
            amount_paise=round(float(amount * 100)) if amount is not None else 0,
            raw={"order_status": raw_status},
        )

    def fetch_payments(self, provider_order_id: str) -> list[dict[str, Any]]:
        try:
            raw = self.client.PGOrderFetchPayments(provider_order_id)
        except Exception:
            return []
        data = self._unwrap(raw)
        return data if isinstance(data, list) else []

    def verify_webhook(self, *, headers: dict[str, str], raw_body: bytes) -> WebhookResult:
        h = _headers_lower(headers)
        provided = h.get("x-webhook-signature", "")
        timestamp = h.get("x-webhook-timestamp", "")

        matched = "none"
        if provided and timestamp and self._webhook_key:
            dotted = _hmac_b64(self._webhook_key, timestamp.encode() + b"." + raw_body)
            plain = _hmac_b64(self._webhook_key, timestamp.encode() + raw_body)
            if hmac.compare_digest(dotted, provided):
                matched = "dotted"
            elif hmac.compare_digest(plain, provided):
                matched = "plain"
        if matched == "none":
            return WebhookResult("", "", None, None, None, "failed", False, "signature invalid")

        try:
            data = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return WebhookResult("", "", None, None, None, "failed", True, "unparseable body")

        event_type = str(data.get("type") or data.get("event") or "")
        payload = data.get("data") or {}
        payment = payload.get("payment") or {}
        order = payload.get("order") or {}
        status_raw = str(payment.get("payment_status") or "").upper()

        if status_raw == "SUCCESS" or event_type.upper().endswith("PAYMENT_SUCCESS"):
            status = "succeeded"
        elif status_raw in {"FAILED", "USER_DROPPED", "CANCELLED", "VOID"}:
            status = "failed"
        else:
            status = "ignored"

        amount_rupees = payment.get("payment_amount")
        try:
            amount_paise = round(float(amount_rupees * 100)) if amount_rupees is not None else None
        except (TypeError, ValueError):
            amount_paise = None

        event_key = str(h.get("x-idempotency-header") or payment.get("cf_payment_id") or "")
        if not event_key:
            event_key = hashlib.sha256(raw_body).hexdigest()

        return WebhookResult(
            event_key=event_key,
            event_type=event_type,
            order_id=(str(order.get("order_id")) if order.get("order_id") else data.get("order_id")),
            payment_id=(str(payment.get("cf_payment_id")) if payment.get("cf_payment_id") else None),
            amount_paise=amount_paise,
            status=status,
            signature_valid=True,
            detail=f"signature scheme: {matched}",
        )


# --------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------

# The mock gateway keeps order state in memory, so it must be a singleton per
# process: the route that creates an order, the webhook handler that verifies it,
# and the reconciliation job that re-checks it must all see the same instance.
# A fresh instance per call would silently lose the order.
_MOCK_SINGLETON: MockAdapter | None = None


def _mock_singleton(webhook_key: str = "") -> MockAdapter:
    global _MOCK_SINGLETON
    if _MOCK_SINGLETON is None:
        _MOCK_SINGLETON = MockAdapter(verify_key=webhook_key or None)
    return _MOCK_SINGLETON


def build_adapter(
    *,
    provider: str,
    mode: str = "sandbox",
    key_id: str = "",
    key_material: str = "",
    webhook_key: str = "",
) -> PaymentAdapter:
    provider = (provider or "mock").lower()
    if provider == "razorpay":
        return RazorpayAdapter(key_id, key_material, webhook_key, mode=mode)
    if provider == "cashfree":
        return CashfreeAdapter(key_id, key_material, mode=mode, webhook_key=webhook_key or None)
    return _mock_singleton(webhook_key)


def adapter_for_settings(settings: Settings) -> PaymentAdapter:
    """The platform's own configuration — used for our subscription billing."""
    return build_adapter(
        provider=settings.payment_provider,
        mode=settings.payment_mode,
        key_id=settings.platform_razorpay_key_id or settings.platform_cashfree_app_id,
        key_material=settings.platform_razorpay_key_secret or settings.platform_cashfree_secret,
        webhook_key=settings.razorpay_webhook_secret or settings.cashfree_webhook_secret,
    )


def merchant_adapter(org) -> PaymentAdapter:
    """Build an adapter from a merchant's own stored configuration.

    The merchant's credential material is stored encrypted and decrypted only
    here, at the point of use. Falls back to the platform adapter when the
    merchant has not connected their own gateway.
    """
    settings = get_settings()
    from app.security import decrypt_secret

    if org is None:
        return adapter_for_settings(settings)
    provider = (getattr(org, "gateway_provider", None) or "").lower()
    if not provider:
        return adapter_for_settings(settings)
    return build_adapter(
        provider=provider,
        mode=settings.payment_mode,
        key_id=org.gateway_key_id or "",
        key_material=decrypt_secret(org.gateway_key_secret_enc) or "",
        webhook_key=decrypt_secret(org.gateway_webhook_secret_enc) or "",
    )


__all__ = [
    "CashfreeAdapter",
    "LookupResult",
    "MockAdapter",
    "OrderRequest",
    "OrderResult",
    "PaymentAdapter",
    "PaymentError",
    "RazorpayAdapter",
    "WebhookResult",
    "adapter_for_settings",
    "build_adapter",
    "merchant_adapter",
    "paise_to_gateway_amount",
    "paise_to_rupees",
]
