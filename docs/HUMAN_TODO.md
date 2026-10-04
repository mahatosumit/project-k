# HUMAN_TODO — everything only a person can do

Ordered by what blocks the most. Time estimates are realistic for someone doing
this alongside other work, and include waiting on other people. Nothing here can be
done by the software, which is why the software was finished first.

---

## 1. Entity and bank account — **blocks everything else** (2–4 weeks)

**Why:** a payment gateway will not activate a merchant without a registered entity
and a bank account in that entity's name, and GST registration decisions depend on
the structure you choose.

- [ ] Choose the structure: proprietorship (fastest, simplest, personal liability),
      LLP, or private limited (cleanest for a gateway and for hiring, most
      compliance).
- [ ] Register: proprietorship via Udyam + a current account, or a company via
      MCA/SPICe+ (7–15 working days plus DSC/DIN lead time).
- [ ] Open a **current account** in the entity's name. Officers: PAN, address
      proof, incorporation or Udyam certificate.
- [ ] Obtain a **Udyam (MSME) registration** if eligible — it is free, fast, and it
      is the document that makes the MSMED interest and MSME Samadhaan route
      legally available to *you* as a supplier, and it is checked in the product's
      evidence checklist.
- **Official links:** `udyamregistration.gov.in`, `mca.gov.in`,
  `onlineservices.nsdl.com` (PAN), the bank's own account-opening page.

## 2. Payment gateway merchant KYC — **blocks live payments** (1–3 weeks)

**Why:** no live keys, no live money. Everything else can proceed in parallel.

- [ ] Sign up with **Razorpay** (`razorpay.com`) and/or **Cashfree**
      (`cashfree.com`) and complete merchant KYC. **The exact document list per
      entity type could not be verified during this build** — ask their onboarding
      team for the current list in writing and keep the reply.
- [ ] Expect to be asked for a **live website with working Terms, Privacy, Refund
      and Contact pages**. All four exist in this product (`/legal/terms`,
      `/legal/privacy`, `/legal/refund`, `/legal/grievance`) but require a domain
      and a deployment before they are reachable.
- [ ] Ask explicitly: **is a live website with policy pages required before
      activation, and what is the KYC turnaround for this entity type?**
- [ ] Once activated: capture the key id, key secret and webhook signing key, set
      `PAYMENT_MODE=live` and the provider, register
      `{BASE_URL}/webhooks/{provider}` at the gateway, and take a real ₹1 payment
      end to end (see `docs/OPERATIONS.md` §1).
- [ ] Confirm the **current MDR for UPI** accounting for the 0.4% P2M change
      effective 15 October 2026, and whether a small merchant is exempt.

## 3. GST decisions and registration — **blocks compliant invoicing** (1 week + CA time)

**Why:** the product charges GST correctly, but whether *you* must register is a
tax decision, not a software one.

- [ ] Engage a **CA** and get written answers to the questions collected in
      `research/03-gst-and-tax.md` (the "Must-ask-a-CA" section). The most
      important is whether the **inter-state exemption for service suppliers**
      (Notification No. 10/2017–Integrated Tax, dated 13.10.2017) still applies to
      your exact service — this was flagged UNVERIFIED and getting it wrong in
      either direction is expensive.
- [ ] Register for GST if your CA advises it, or if you want to sell to customers
      who need an input-tax-credit invoice. Many Indian business buyers will not
      accept a "bill of supply", which is a commercial reason to register earlier
      than the ₹20 lakh turnover threshold.
- [ ] Confirm the **SAC code** for your service (the product defaults to 998314 and
      it is editable).
- [ ] Confirm the invoice format against Rule 46 for your specific case, and the
      GSTR filing cadence and due dates you will be on.
- [ ] If you sell to buyers who deduct TDS, confirm the current section, rate and
      threshold under the **Income-tax Act, 2025** (the old 194C/194J numbering was
      consolidated into Section 393 from 1 April 2026) — sources disagreed on
      thresholds during this build.
- **Official links:** `gst.gov.in`, `cbic.gov.in`, `incometaxindia.gov.in`.

## 4. Domain, hosting and HTTPS — **blocks the gateway and any real use** (2–3 days)

- [ ] Buy a domain. `.in` or `.com`; avoid anything that looks like a
      payment-collection brand (no "pay", "collect", "recover" in the name) so it
      is not mistaken for a lender.
- [ ] Deploy to an **India region** for latency and data-residency comfort. Note
      the CERT-In direction requires logs to be retained **within Indian
      jurisdiction** for 180 days; the deployment must be consistent with that.
- [ ] Point DNS at the host, put the Caddy config from `deploy/Caddyfile` in place
      with the real domain, and confirm automatic HTTPS works.
- [ ] Run the app with `--no-server-header` and `--proxy-headers`, and confirm the
      proxy strips incoming `X-Forwarded-For`.
- [ ] Complete `/legal/grievance` and `/legal/privacy` with the operator's real
      name, address and grievance contact, then set the same details per merchant
      in the app.
- [ ] Re-run `python scripts/live_walk.py https://your-domain` and the restore
      drill against the new host.

## 5. TRAI DLT registration for SMS — **blocks SMS reminders** (3–10 days)

**Why:** unregistered commercial SMS is dropped at the operator level. The product
refuses to send without all five DLT values, which is the correct behaviour and
also means SMS does not work until this is done.

- [ ] Register as a **Principal Entity** on any one DLT portal (Jio `trueconnect.jio.com`,
      Airtel `dltconnect.airtel.in`, Vi `vilpower.in`, BSNL, Tata). One registration
      is enough; the ledger is shared. Officers: GST certificate, PAN, incorporation
      or Udyam certificate, authorised-signatory ID, and the portal fee.
- [ ] Register a **sender header** (6 characters) and submit **message templates**
      for the reminder steps you intend to send.
- [ ] Set `SMS_DLT_ENTITY_ID`, `SMS_SENDER_ID`, `SMS_DLT_TEMPLATE_ID`, `SMS_API_URL`
      and `SMS_API_KEY`.
- [ ] Send one test SMS to your own number and confirm it arrives.
- **Note:** SMS is the *secondary* channel in the ladder. WhatsApp carries most of
  it, so this is not on the critical path to a first paying customer.

## 6. WhatsApp Business Platform — **blocks WhatsApp reminders** (3–10 days)

**Why:** this is the ladder's primary channel and therefore the product's main
value delivery.

- [ ] Create a **Meta Business account** and add a phone number not already on
      WhatsApp (`business.facebook.com`).
- [ ] Choose the onboarding path: **Cloud API directly** (cheapest, more setup) or a
      **Business Solution Provider** (faster, a per-message markup). For a solo
      operator starting out, the Cloud API direct is worth the extra day.
- [ ] Submit **utility templates** for each reminder stage in both English and
      Hindi. Utility, not marketing: these are transactional messages about a real
      invoice.
- [ ] Set `MESSAGING_PROVIDER=whatsapp`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`.
- [ ] Send one real message to your own number and confirm it arrives and that the
      per-message cost matches your expectation.
- [ ] **Confirm the current India rate card** for utility messages — it was not
      verifiable during this build and it drives the product's unit economics.
- [ ] Understand the quality-rating and messaging-limit rules for a new number;
      send slowly at first.

## 7. Legal review — **required before the first paying customer** (1–2 weeks)

- [ ] A lawyer reviews the **privacy policy, terms of service, refund policy and
      grievance page** against the Digital Personal Data Protection Act 2023 and
      its Rules, the IT Act, and the CERT-In directions. They were written to match
      what the software actually does, but **no lawyer has read them**.
- [ ] A lawyer or CA reviews the **MSMED interest presentation** and the recovery
      evidence checklist, confirming that showing a calculation with its rate and
      assumptions — and showing nothing when the rate is unset — is the defensible
      approach.
- [ ] Confirm the **DPDP Rules phase-in dates**. Sources read during this build
      disagreed (13 May vs 13 March 2027), so no obligation timing is asserted in
      the product.
- [ ] Confirm the **current RBI notified bank rate** for MSMED s.16 and set
      `RBI_BANK_RATE_PERCENT`. Until this is set the product deliberately shows no
      interest figure at all.

## 8. Pre-launch verification only a person can do (1 day)

- [ ] Walk the product on a **real low-end Android phone over throttled 3G**. The
      automated visual and throttled-network verification could not run in the
      build environment, so responsiveness has not been seen on a real device.
- [ ] Read every reminder message as a customer would: would you be annoyed, or
      would you pay? Fix the wording here, not after a customer complains.
- [ ] Log in as a customer via a portal link on a phone and complete the payment
      flow with a real (small) amount once live keys exist.
- [ ] Delete a test customer and confirm the exported data and the audit trail
      behave as the privacy policy describes.

## 9. Deferred product work (not blockers; do them only if the pilot asks)

- [ ] **PWA manifest and service worker** for installation on Android. Deliberately
      deferred: it does not change whether a merchant gets paid.
- [ ] **TOTP two-factor for merchant accounts.** Phone OTP exists; TOTP would raise
      support cost more than perceived safety at ₹299/month.
- [ ] **Automated refunds** via the gateway API, once live keys exist to test
      against. Until then refunds are a recorded human action.
- [ ] **A second gateway adapter** if merchants ask; the adapter interface is
      already in place.
- [ ] **A second locale** (Marathi or Tamil) — a new JSON file plus one entry, no
      code change.

## 10. A CA or lawyer must sign off on these specific statements

Because they are money or law, and the product repeats them to customers:

1. Whether the inter-state service exemption still applies to your service.
2. The SAC code you will use on invoices.
3. The MSMED interest rate and compounding basis you will quote.
4. Whether your buyers must deduct TDS, and under which section.
5. Whether GST registration is required for you at your expected turnover.
6. That the privacy notice and consent wording comply with the DPDP Act as it
   stands.
