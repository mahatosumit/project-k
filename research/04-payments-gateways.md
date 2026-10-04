# 04 — Indian Payment Gateways: Razorpay & Cashfree
Verified as of 2026-10-04. Sources: official docs/pricing (razorpay.com, cashfree.com, rbi.org.in, npci.org.in) unless marked SECONDARY.

Given (verified earlier in project, not re-derived): Razorpay webhook header X-Razorpay-Signature (HMAC-SHA256 of raw body, webhook secret; idempotency x-razorpay-event-id; test-mode admin OTP 754081; blacklisted callback hosts ngrok.io/webhook.site; localhost unsupported). Cashfree webhook x-webhook-signature + x-webhook-timestamp, Base64(HMAC_SHA256(ts + "." + payload, merchantSecretKey)); helper PGVerifyWebhookSignature; idempotency x-idempotency-header; 3 retries at 2/10/30 min. SDKs: razorpay 2.0.1, cashfree-pg 6.0.1. RBI e-mandate framework 2026 (21 Apr 2026): AFA first txn; >=24h pre-debit notification; <=Rs 15,000 recurring without AFA; Rs 1,00,000 no-AFA only insurance/MF/credit-card bills.

## 1. Onboarding (documents, website requirements, timelines)
UNVERIFIED — pending.

## 2. Pricing (published MDR, fees)

### Razorpay (primary source: razorpay.com/blog/razorpay-payment-gateway-pricing-explained, accessed 2026-10-04; cross-checked razorpay.com/pricing and razorpay.com/blog/payment-gateway-transparent-pricing-explained)
- Standard domestic platform fee: **2% + 18% GST** on successful transactions (cards, netbanking, wallets, UPI). GST applies only to the fee, not transaction value; 2% becomes **2.36% all-in**.
- UPI: 0% MDR by regulation, but Razorpay charges its platform fee of 2% + GST for gateway infrastructure (stated explicitly in their pricing blog).
- Credit Card on UPI (RuPay): 2.15% + GST. EMI/Cardless EMI, Corporate/Business cards, Amex/Diners, Pay Later: 3% + GST. International cards: 3% + GST (optional chargeback protection +1%). International bank transfers: 1% + GST. International wallets/local methods: 3.5% + GST.
- Setup fee: ₹0. AMC: ₹0. No mandatory minimums. **Refund processing fee: ₹0 ("zero refund processing fee")** — per transparent-pricing blog.
- One-time KYC processing fee: **₹199 + applicable taxes** (from pricing blog, new-merchant offer conditions).
- **Promo (current, auto-applied): 0% platform fee for merchants who complete KYC/activate on or after 1 July 2026 — up to ₹5,00,000 cumulative GMV or 90 days from activation, whichever is first.** Covers UPI, debit cards, credit cards, netbanking, wallets. Excludes prepaid cards, corporate cards, Amex, Diners, EMI, international. GST (18%) still applies on the standard 2% and the ₹199 KYC fee still applies. Fair usage: credit-card volume must stay under 90% of total.
- Subscription product: additional 0.99% per transaction on top of payment method fee (not needed for one-off invoice collection).

### Cashfree (primary source: cashfree.com/docs/help/account/pricing "accurate as of 10 August 2026"; cross-checked cashfree.com/blog/payment-gateway-charges-india-free-payment-gateway, both accessed 2026-10-04)
- Standard domestic TDR: **1.95%** for UPI (Intent/Collect/Credit Line/PPI), domestic credit & debit cards, net banking, digital wallets, prepaid cards. **UPI on RuPay credit cards: 2.15%.**
- **Festive offer: 0% platform fee for new merchants who sign up on or after 21 July 2026 (12:00 PM IST), up to cumulative GMV ₹20,00,000 (one-time cap), valid through 31 March 2027.** Applied automatically post-KYC. Excludes AMEX/Diners, corporate cards, EMI, prepaid, Pay Later, subscriptions/e-mandate, international (IPG). GST 18% still charged on the standard 1.95% even when the fee is waived. Fair usage: after 5+ txn & ₹5L GMV, if credit-card share ≥60% of GMV the offer may be withdrawn. One per PAN/bank account; partner-referred merchants not eligible.
- EMI/Pay Later: CC EMI from 1.90% + 0.25%; DC EMI (HDFC) 1.50%; Cardless EMI 1.90%; Pay Later 2.20%. International: Visa/MC 2.99%, AMEX 2.95%. Virtual bank accounts (IMPS/NEFT/RTGS): flat from ₹20/txn.
- **Setup fee ₹0; AMC ₹0.** No published per-refund fee on this page; pricing page footnote warns "* Platform charges may apply for reporting, settlements, refunds, risk and dispute management."
- Offer on cashfree.com/pricing FAQ states UPI "1.90% per transaction" — conflicts with the 1.95% standard in the docs FAQ (dated 10 Aug 2026). Treat **1.95%** as the operative standard rate; 1.90% likely stale copy. Flagged in Must-verify.
- Payouts/Cashgram/Secure ID: no published rate card (contact sales). Enterprise custom pricing available.
- Blog states offer eligibility as "sign up before 31 July 2026" while the docs FAQ states "on or after 21 July 2026"; the docs FAQ (dated) controls. Flagged in Must-verify.

## 3. Settlement cycles & fees
UNVERIFIED — pending.

## 4. Refunds
UNVERIFIED — pending.

## 5. Chargebacks / disputes
UNVERIFIED — pending.

## 6. Sandbox & test mode

### Razorpay (verified: razorpay.com/docs/payments/payments/test-card-details/ and /test-upi-details/, accessed 2026-10-04)
- Test mode has a mock bank page with **Success and Failure buttons**; no real money. Test cards only work in test mode; using them in live mode returns `card issuer is invalid` or `invalid card input`.
- Card flow: select Card → any random CVV → any future expiry → Pay → enter random OTP (4–10 digits = success; under 4 digits = failure).
- **Test UPI success: `success@razorpay`. Test UPI failure: `failure@razorpay`.** In test mode, payment cancellation results in a successful payment (a documented quirk — test cancellation in live mode instead).
- Test cards (numbers partially rendered by fetch; standard published set includes 4111 1111 1111 1111 and 5105 1051 0510 5100 for Mastercard international flow) — see "# Must-verify-by-human" to re-pull from the doc page table.
- Test-mode admin OTP 754081 (given, already verified).
- Base URLs: test API `https://api.razorpay.com/v1` with `rzp_test_*` keys; live `https://api.razorpay.com/v1` with `rzp_live_*` keys (same host, key prefix distinguishes mode — verify on first integration).

## 7. UPI specifics (MDR, limits, collect flows)

### UPI MDR — effective 15 October 2026 (CONFIRMED)
- **0.4% MDR on P2M UPI transactions above ₹2,000, effective 15 October 2026.** For transactions of ₹75,000 and above, **MDR is capped at ₹300 per transaction**. P2P stays free; P2M ≤ ₹2,000 stays free (gazette notification dated 14 September 2026; Payment and Settlement Systems Act 2007 s.10A amended).
- Circular: **NPCI/UPI/OC No. 237/2026-27, dated 15 September 2026** ("Merchant Discount Rate (MDR) for UPI P2M transactions above ₹2,000"). Sources: NPCI UPI circulars index lists "UPI | OC No. 237 | FY 2026-27" (npci.org.in/circulars/upi, accessed 2026-10-04); circular number also reported by businessupturn.com and madhyabharatparidrishya.com [SECONDARY for number; PRIMARY for existence of OC 237 in NPCI index]. TOI (15 Sep 2026) confirms 0.4%, ₹300 cap at ≥₹75,000, effective 15 Oct 2026 [SECONDARY/report].
- **Caveat:** the NPCI index entry for OC No. 237 says "Please get in touch with your bank" and the PDF link was not retrievable (fetch failed / index hides PDF URL). The 0.4%/₹300/15-Oct parameters are therefore cross-verified from multiple secondary reports + NPCI index presence, not from the circular PDF itself. Marked in "# Must-verify-by-human".
- **What this means for the two gateways:** both currently charge their own platform fee on UPI anyway (Razorpay 2%+GST; Cashfree 1.95% standard / 0% offer). The MDR sits behind the PA/bank layer; the merchant-visible effect is an increase in underlying UPI cost for PAs on >₹2,000 P2M, which may feed into future platform pricing. If MDR applies to a specific transaction, gateway economics could shift after 15 Oct 2026 — re-check published pricing then.
- NPCI FAQ (reported by multiple outlets, incl. Instagram/news posts): MDR is merchant-side; consumers stay free. Whether specific MCC/merchant-size exemptions exist (small merchants) — Reuters noted "small merchants exempt" but I could not open the Reuters article (blocked) or the circular PDF. Carved-out categories and exemptions = NOT yet verified; see Must-verify.

## 8. Payment data storage & tokenisation
UNVERIFIED — pending.

## 9. Go-live (sandbox to live, approvals, blockers)
UNVERIFIED — pending.

# Fee model worksheet
UNVERIFIED — pending.

# Sandbox test recipes
UNVERIFIED — pending.

# Must-verify-by-human
- (populated at end)
