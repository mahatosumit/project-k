-- Vasool initial schema (migration 0001)
-- Portable across SQLite (local/test) and PostgreSQL (production).
-- Money is stored as INTEGER paise (1 rupee = 100 paise). Never floats.
-- Primary keys are TEXT UUID-hex: portable, no sequence/autoincrement dialect gap.

CREATE TABLE organizations (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    legal_name VARCHAR(200),
    gstin VARCHAR(15),
    pan VARCHAR(10),
    state_code VARCHAR(2) NOT NULL DEFAULT '27',
    address_line1 VARCHAR(200),
    address_line2 VARCHAR(200),
    city VARCHAR(100),
    state VARCHAR(100),
    pincode VARCHAR(6),
    country VARCHAR(2) NOT NULL DEFAULT 'IN',
    phone_e164 VARCHAR(16),
    billing_email VARCHAR(254),
    locale VARCHAR(5) NOT NULL DEFAULT 'en',
    invoice_prefix VARCHAR(10) NOT NULL DEFAULT 'INV',
    sac_code VARCHAR(6) NOT NULL DEFAULT '998314',
    gst_registered BOOLEAN NOT NULL DEFAULT FALSE,
    place_of_supply_state_code VARCHAR(2),
    reminder_days_before INTEGER NOT NULL DEFAULT 3,
    reminder_escalation_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    grace_days_before_final INTEGER NOT NULL DEFAULT 7,
    complaint_officer_name VARCHAR(200),
    complaint_officer_email VARCHAR(254),
    complaint_officer_phone VARCHAR(16),
    gateway_provider VARCHAR(20),
    gateway_key_id VARCHAR(120),
    gateway_key_secret_enc TEXT,
    gateway_webhook_secret_enc TEXT,
    gateway_status VARCHAR(20) NOT NULL DEFAULT 'not_connected',
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE users (
    id VARCHAR(32) PRIMARY KEY,
    org_id VARCHAR(32) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email VARCHAR(254) NOT NULL,
    phone_e164 VARCHAR(16),
    name VARCHAR(200) NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'owner',
    locale VARCHAR(5) NOT NULL DEFAULT 'en',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMP,
    last_login_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE UNIQUE INDEX ux_users_email_lower ON users (email);

CREATE TABLE customers (
    id VARCHAR(32) PRIMARY KEY,
    org_id VARCHAR(32) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    contact_name VARCHAR(200),
    phone_e164 VARCHAR(16),
    email VARCHAR(254),
    gstin VARCHAR(15),
    state_code VARCHAR(2),
    address VARCHAR(400),
    notes TEXT,
    whatsapp_opt_in BOOLEAN NOT NULL DEFAULT FALSE,
    opt_in_at TIMESTAMP,
    opt_in_source VARCHAR(60),
    portal_link_key VARCHAR(64) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE UNIQUE INDEX ux_customers_portal_link_key ON customers (portal_link_key);

CREATE INDEX ix_customers_org ON customers (org_id, name);

CREATE INDEX ix_customers_phone ON customers (org_id, phone_e164);

CREATE TABLE invoices (
    id VARCHAR(32) PRIMARY KEY,
    org_id VARCHAR(32) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    customer_id VARCHAR(32) NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    invoice_number VARCHAR(16) NOT NULL,
    series_fy VARCHAR(7) NOT NULL,
    issue_date DATE NOT NULL,
    due_date DATE NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'INR',
    sac_code VARCHAR(6) NOT NULL DEFAULT '998314',
    description VARCHAR(400),
    place_of_supply_state_code VARCHAR(2),
    is_interstate BOOLEAN NOT NULL DEFAULT FALSE,
    taxable_value_paise BIGINT NOT NULL DEFAULT 0,
    discount_paise BIGINT NOT NULL DEFAULT 0,
    gst_rate_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
    cgst_paise BIGINT NOT NULL DEFAULT 0,
    sgst_paise BIGINT NOT NULL DEFAULT 0,
    igst_paise BIGINT NOT NULL DEFAULT 0,
    total_paise BIGINT NOT NULL DEFAULT 0,
    paid_paise BIGINT NOT NULL DEFAULT 0,
    credited_paise BIGINT NOT NULL DEFAULT 0,
    written_off_paise BIGINT NOT NULL DEFAULT 0,
    reverse_charge BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    notes TEXT,
    issued_at TIMESTAMP,
    paid_at TIMESTAMP,
    created_by VARCHAR(32),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE UNIQUE INDEX ux_invoices_number ON invoices (org_id, series_fy, invoice_number);

CREATE INDEX ix_invoices_org_due ON invoices (org_id, due_date);

CREATE INDEX ix_invoices_customer ON invoices (customer_id, status);

CREATE TABLE invoice_items (
    id VARCHAR(32) PRIMARY KEY,
    invoice_id VARCHAR(32) NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL DEFAULT 1,
    description VARCHAR(400) NOT NULL,
    hsn_sac VARCHAR(8),
    quantity NUMERIC(12,3) NOT NULL DEFAULT 1,
    unit VARCHAR(20) NOT NULL DEFAULT 'NOS',
    unit_price_paise BIGINT NOT NULL DEFAULT 0,
    line_total_paise BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX ix_invoice_items_invoice ON invoice_items (invoice_id, seq);

CREATE TABLE payments (
    id VARCHAR(32) PRIMARY KEY,
    org_id VARCHAR(32) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    invoice_id VARCHAR(32) REFERENCES invoices(id) ON DELETE SET NULL,
    customer_id VARCHAR(32) REFERENCES customers(id) ON DELETE SET NULL,
    amount_paise BIGINT NOT NULL,
    method VARCHAR(20) NOT NULL DEFAULT 'manual',
    status VARCHAR(20) NOT NULL DEFAULT 'succeeded',
    reference VARCHAR(120),
    utr VARCHAR(40),
    received_at TIMESTAMP NOT NULL,
    gateway_provider VARCHAR(20),
    gateway_order_id VARCHAR(120),
    gateway_payment_id VARCHAR(120),
    gateway_signature VARCHAR(255),
    notes TEXT,
    recorded_by VARCHAR(32),
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_payments_invoice ON payments (invoice_id, received_at);

CREATE INDEX ix_payments_gateway ON payments (gateway_provider, gateway_payment_id);

-- Webhook events: the idempotency + replay defence. event_key is unique.
CREATE TABLE payment_events (
    id VARCHAR(32) PRIMARY KEY,
    provider VARCHAR(20) NOT NULL,
    event_key VARCHAR(200) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    signature_valid BOOLEAN NOT NULL DEFAULT FALSE,
    payload TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'received',
    detail TEXT,
    received_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP
);

CREATE UNIQUE INDEX ux_payment_events_key ON payment_events (provider, event_key);

CREATE INDEX ix_payment_events_received ON payment_events (received_at);

CREATE TABLE reminders (
    id VARCHAR(32) PRIMARY KEY,
    org_id VARCHAR(32) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    invoice_id VARCHAR(32) NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    customer_id VARCHAR(32) NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    step_index INTEGER NOT NULL,
    stage VARCHAR(20) NOT NULL,
    channel VARCHAR(20) NOT NULL DEFAULT 'whatsapp',
    tone VARCHAR(20) NOT NULL DEFAULT 'friendly',
    scheduled_for TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
    message_body TEXT,
    provider_message_id VARCHAR(120),
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    sent_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE UNIQUE INDEX ux_reminders_step ON reminders (invoice_id, step_index, channel);

CREATE INDEX ix_reminders_queue ON reminders (status, scheduled_for);

CREATE TABLE disputes (
    id VARCHAR(32) PRIMARY KEY,
    org_id VARCHAR(32) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    invoice_id VARCHAR(32) NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    customer_id VARCHAR(32) NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    public_token VARCHAR(64) NOT NULL,
    kind VARCHAR(30) NOT NULL,
    reason_code VARCHAR(40),
    message TEXT,
    promised_date DATE,
    claimed_amount_paise BIGINT,
    claimed_utr VARCHAR(40),
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    resolution_note TEXT,
    created_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE UNIQUE INDEX ux_disputes_token ON disputes (public_token);

CREATE INDEX ix_disputes_invoice ON disputes (invoice_id, status);

CREATE TABLE installment_plans (
    id VARCHAR(32) PRIMARY KEY,
    org_id VARCHAR(32) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    invoice_id VARCHAR(32) NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    dispute_id VARCHAR(32) REFERENCES disputes(id) ON DELETE SET NULL,
    total_paise BIGINT NOT NULL,
    count INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'offered',
    created_by VARCHAR(32),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_plans_invoice ON installment_plans (invoice_id, status);

CREATE TABLE installments (
    id VARCHAR(32) PRIMARY KEY,
    plan_id VARCHAR(32) NOT NULL REFERENCES installment_plans(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    due_date DATE NOT NULL,
    amount_paise BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    paid_at TIMESTAMP,
    payment_id VARCHAR(32) REFERENCES payments(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX ux_installments_seq ON installments (plan_id, seq);

CREATE TABLE consents (
    id VARCHAR(32) PRIMARY KEY,
    org_id VARCHAR(32) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    subject_type VARCHAR(20) NOT NULL DEFAULT 'customer',
    subject_id VARCHAR(32) NOT NULL,
    purpose VARCHAR(60) NOT NULL,
    notice_version VARCHAR(20) NOT NULL,
    granted BOOLEAN NOT NULL DEFAULT FALSE,
    source VARCHAR(60),
    evidence VARCHAR(255),
    granted_at TIMESTAMP,
    withdrawn_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_consents_subject ON consents (subject_type, subject_id, purpose);

CREATE TABLE notification_log (
    id VARCHAR(32) PRIMARY KEY,
    org_id VARCHAR(32) REFERENCES organizations(id) ON DELETE CASCADE,
    channel VARCHAR(20) NOT NULL,
    to_address VARCHAR(254) NOT NULL,
    template VARCHAR(60),
    body TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    provider_message_id VARCHAR(120),
    error TEXT,
    related_type VARCHAR(30),
    related_id VARCHAR(32),
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_notifications_created ON notification_log (org_id, created_at);

CREATE TABLE otp_codes (
    id VARCHAR(32) PRIMARY KEY,
    scope VARCHAR(30) NOT NULL,
    phone_e164 VARCHAR(16) NOT NULL,
    code_hash VARCHAR(128) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    consumed_at TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    request_ip VARCHAR(45),
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_otp_lookup ON otp_codes (scope, phone_e164, created_at);

CREATE TABLE rate_counters (
    bucket VARCHAR(60) NOT NULL,
    key VARCHAR(120) NOT NULL,
    window_start TIMESTAMP NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bucket, key, window_start)
);

CREATE TABLE support_requests (
    id VARCHAR(32) PRIMARY KEY,
    org_id VARCHAR(32) REFERENCES organizations(id) ON DELETE CASCADE,
    subject_type VARCHAR(20) NOT NULL DEFAULT 'customer',
    subject_id VARCHAR(32),
    channel VARCHAR(20) NOT NULL DEFAULT 'portal',
    category VARCHAR(40) NOT NULL DEFAULT 'general',
    message TEXT NOT NULL,
    contact VARCHAR(254),
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    sla_due_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP,
    resolution_note TEXT,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_support_status ON support_requests (status, sla_due_at);

CREATE TABLE data_requests (
    id VARCHAR(32) PRIMARY KEY,
    org_id VARCHAR(32) REFERENCES organizations(id) ON DELETE CASCADE,
    subject_type VARCHAR(20) NOT NULL DEFAULT 'customer',
    subject_id VARCHAR(32) NOT NULL,
    kind VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'received',
    note TEXT,
    requested_at TIMESTAMP NOT NULL,
    due_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP
);

CREATE INDEX ix_data_requests_status ON data_requests (status, due_at);

CREATE TABLE breach_events (
    id VARCHAR(32) PRIMARY KEY,
    severity VARCHAR(20) NOT NULL DEFAULT 'medium',
    summary TEXT NOT NULL,
    detected_at TIMESTAMP NOT NULL,
    reported_to_cert_in_at TIMESTAMP,
    report_due_at TIMESTAMP NOT NULL,
    affected_subjects INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    notes TEXT,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE subscriptions (
    id VARCHAR(32) PRIMARY KEY,
    org_id VARCHAR(32) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    plan_code VARCHAR(30) NOT NULL,
    price_paise BIGINT NOT NULL,
    billing_cycle VARCHAR(20) NOT NULL DEFAULT 'monthly',
    status VARCHAR(20) NOT NULL DEFAULT 'trialing',
    started_at TIMESTAMP NOT NULL,
    current_period_end TIMESTAMP,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    cancelled_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_subs_org ON subscriptions (org_id, status);

CREATE TABLE gateway_orders (
    id VARCHAR(32) PRIMARY KEY,
    org_id VARCHAR(32) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    subscription_id VARCHAR(32) REFERENCES subscriptions(id) ON DELETE SET NULL,
    purpose VARCHAR(30) NOT NULL DEFAULT 'subscription',
    provider VARCHAR(20) NOT NULL,
    mode VARCHAR(10) NOT NULL DEFAULT 'sandbox',
    provider_order_id VARCHAR(120) NOT NULL,
    amount_paise BIGINT NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'INR',
    status VARCHAR(20) NOT NULL DEFAULT 'created',
    paid_at TIMESTAMP,
    idempotency_key VARCHAR(120),
    notes TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE UNIQUE INDEX ux_orders_provider_id ON gateway_orders (provider, provider_order_id);

CREATE TABLE audit_log (
    id VARCHAR(32) PRIMARY KEY,
    org_id VARCHAR(32),
    actor_type VARCHAR(20) NOT NULL DEFAULT 'system',
    actor_id VARCHAR(32),
    action VARCHAR(60) NOT NULL,
    entity_type VARCHAR(40),
    entity_id VARCHAR(32),
    ip VARCHAR(45),
    user_agent VARCHAR(255),
    detail TEXT,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_audit_created ON audit_log (created_at);

CREATE INDEX ix_audit_org_action ON audit_log (org_id, action, created_at);

CREATE TABLE counters (
    name VARCHAR(60) PRIMARY KEY,
    value BIGINT NOT NULL DEFAULT 0
);
