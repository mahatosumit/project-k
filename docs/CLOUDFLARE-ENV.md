# Cloudflare Workers Environment & Secrets Reference — Vasool

This document details all configuration variables and production secrets required to run Vasool on **Cloudflare Python Workers**.

---

## 1. Normal Environment Variables (`vars` in `wrangler.jsonc` or Dashboard)

These values are public or non-sensitive configuration settings that can be checked into `wrangler.jsonc` or set as plain text environment variables in the Cloudflare Dashboard.

| Variable Name | Example Value | Description |
|---|---|---|
| `APP_ENV` | `staging` or `prod` | Application environment. Anything other than `dev` enables strict startup verification. |
| `APP_NAME` | `Vasool` | Branding name displayed across navigation, invoices, and emails. |
| `BASE_URL` | `https://vasool.example.in` | Fully qualified public HTTPS domain without trailing slash. Used for portal and payment links. |
| `PAYMENT_PROVIDER` | `razorpay` | Primary platform payment provider (`razorpay`, `cashfree`, or `mock` for staging). |
| `PAYMENT_MODE` | `sandbox` or `live` | Gateway mode (`sandbox` for testing, `live` for real production payments). |
| `MESSAGING_PROVIDER` | `whatsapp` | Outbound messaging provider (`whatsapp`, `sms_dlt`, `email`, or `console` for staging). |
| `SAC_CODE_DEFAULT` | `998314` | Default Services Accounting Code (SAC) printed on tax invoices (Rule 46). |
| `ENABLE_HSTS` | `1` | Enforces HTTP Strict Transport Security header when running on HTTPS. |
| `RBI_BANK_RATE_PERCENT` | `0` | RBI-notified bank rate for MSMED s.16 interest calculations (leave 0 if unverified). |
| `CERT_IN_REPORT_HOURS` | `6` | CERT-In compliance incident reporting window (hours). |
| `LOG_RETENTION_DAYS` | `180` | Audit trail retention period in days. |
| `OTP_MAX_PER_PHONE_PER_HOUR` | `5` | Abuse limit for OTP requests to a single phone number. |
| `OTP_MAX_PER_IP_PER_HOUR` | `20` | Abuse limit for OTP requests from a single client IP. |
| `OTP_TTL_SECONDS` | `300` | Expiration lifetime of a one-time login code (5 minutes). |
| `OTP_MAX_VERIFY_ATTEMPTS` | `5` | Maximum incorrect OTP attempts before code invalidation. |
| `LOGIN_MAX_PER_IP_PER_HOUR` | `30` | Maximum login attempts per IP address per hour. |
| `GLOBAL_RATE_LIMIT_PER_MINUTE`| `240` | Global per-IP rate limit ceiling across all endpoints. |

---

## 2. Production Secrets (`wrangler secret put` or Encrypted Secrets)

**NEVER commit these values to version control.** Set them using `npx wrangler secret put <NAME>` or via Cloudflare Dashboard under **Workers & Pages > Settings > Variables and Secrets**.

| Secret Name | How to Generate / Source | Required In |
|---|---|---|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` | **All environments** (signs session cookies and CSRF tokens) |
| `FIELD_ENCRYPTION_KEY` | `python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` | **All environments** (encrypts merchant gateway keys at rest) |
| `DATABASE_URL` | PostgreSQL connection URI or Hyperdrive connection string | **Production & Staging** |
| `RAZORPAY_KEY_ID` | Razorpay Dashboard (`rzp_live_...` or `rzp_test_...`) | When `PAYMENT_PROVIDER=razorpay` |
| `RAZORPAY_KEY_SECRET` | Razorpay Dashboard secret key | When `PAYMENT_PROVIDER=razorpay` |
| `RAZORPAY_WEBHOOK_SECRET` | Webhook secret configured in Razorpay Dashboard | When `PAYMENT_PROVIDER=razorpay` |
| `CASHFREE_APP_ID` | Cashfree Dashboard App ID | When `PAYMENT_PROVIDER=cashfree` |
| `CASHFREE_SECRET_KEY` | Cashfree Dashboard Secret Key | When `PAYMENT_PROVIDER=cashfree` |
| `CASHFREE_WEBHOOK_SECRET` | Cashfree Dashboard Webhook Secret | When `PAYMENT_PROVIDER=cashfree` |
| `WHATSAPP_TOKEN` | Meta Graph API User/System Token | When `MESSAGING_PROVIDER=whatsapp` |
| `WHATSAPP_PHONE_NUMBER_ID` | Meta Business Manager WhatsApp Phone Number ID | When `MESSAGING_PROVIDER=whatsapp` |
| `SMS_API_KEY` | Indian SMS Gateway API Key | When `MESSAGING_PROVIDER=sms_dlt` |
| `SMS_API_URL` | Indian SMS Gateway endpoint | When `MESSAGING_PROVIDER=sms_dlt` |
| `SMS_SENDER_ID` | 6-character registered DLT Sender ID | When `MESSAGING_PROVIDER=sms_dlt` |
| `SMS_DLT_ENTITY_ID` | Principal Entity ID from Telecom DLT Portal | When `MESSAGING_PROVIDER=sms_dlt` |
| `SMS_DLT_TEMPLATE_ID` | Approved DLT Content Template ID | When `MESSAGING_PROVIDER=sms_dlt` |
| `SMTP_PASSWORD` | SMTP password for outbound emails | When `MESSAGING_PROVIDER=email` |

---

## 3. How to Set Secrets via Wrangler CLI

```bash
# Core application secrets
npx wrangler secret put SECRET_KEY
npx wrangler secret put FIELD_ENCRYPTION_KEY
npx wrangler secret put DATABASE_URL

# Gateway secrets (if using Razorpay)
npx wrangler secret put RAZORPAY_KEY_ID
npx wrangler secret put RAZORPAY_KEY_SECRET
npx wrangler secret put RAZORPAY_WEBHOOK_SECRET
```
