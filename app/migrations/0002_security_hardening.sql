-- Migration 0002 — hardening fixes from the independent security review.
--
-- (1) A gateway payment id must be unique per provider. Without this, two
--     deliveries of the same payment (different event ids) could both pass the
--     existence check in ledger.record_payment and insert twice, double-crediting
--     an invoice. SQLite's writer serialisation hides this in development;
--     PostgreSQL READ COMMITTED does not.
-- (2) PaymentEvent and BreachEvent had no org_id, so the ops dashboard could not
--     scope them and every tenant could read every tenant's webhook payloads.

-- (1) Unique gateway payment id. Partial index: rows with no gateway id (manual
-- entries) must not collide with each other.
CREATE UNIQUE INDEX ux_payments_gateway_payment
    ON payments (gateway_provider, gateway_payment_id)
    WHERE gateway_provider IS NOT NULL AND gateway_payment_id IS NOT NULL;

-- (2) Scope payment events and incidents to an organisation.
ALTER TABLE payment_events ADD COLUMN org_id VARCHAR(32);

ALTER TABLE breach_events ADD COLUMN org_id VARCHAR(32);

CREATE INDEX ix_payment_events_org ON payment_events (org_id, received_at);

CREATE INDEX ix_breach_events_org ON breach_events (org_id, detected_at);

-- Backfill what can be inferred: a payment event's org is the org of the order or
-- payment it references. Anything still NULL is a global/platform-level event and
-- is therefore only visible to platform operators, not to a tenant.
UPDATE payment_events
SET org_id = (
    SELECT go.org_id FROM gateway_orders go
    WHERE go.provider = payment_events.provider
      AND payment_events.payload LIKE '%' || go.provider_order_id || '%'
    LIMIT 1
)
WHERE org_id IS NULL;

-- Index to make the reconciliation sweep's "paid but uncredited" query cheap.
CREATE INDEX ix_orders_status_created ON gateway_orders (status, created_at);
