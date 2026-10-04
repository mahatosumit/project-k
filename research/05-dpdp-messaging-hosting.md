# 05 — DPDP, Security-Incident, Messaging & Hosting Rules/Costs (India)

Status: SKELETON — sections being verified against primary sources as of Oct 2026. Write-after-every-section discipline in effect.

## 1. DPDP Act 2023 + DPDP Rules 2025 — status, live vs phased obligations

**Bottom line: The Rules are FINAL and notified — not draft. However, as of 4 Oct 2026 the substantive data-fiduciary obligations are NOT yet in force; most commence ~13 May 2027 (18 months after publication). Only institutional/Board provisions are live today.**

### 1.1 Instruments and dates
- **Act**: Digital Personal Data Protection Act, 2023 (Act 22 of 2023) — enacted August 2023. Substantive provisions took effect only via commencement notification (below).
- **Draft rules**: G.S.R. 02(E), 3 Jan 2025, MeitY — 45-day public consultation. [Evidence tier: secondary-analyst + MeitY site index; high confidence]
- **Final Rules**: **Digital Personal Data Protection Rules, 2025 — G.S.R. 846(E), dated 13 November 2025** (MeitY), Gazette of India, Extraordinary, Pt. II, Sec. 3(i). One source (Taxmann) notes: "GSR 846(E) is dated 13 November 2025; however, it was published in the Official Gazette on 14 November 2025" — the 13 vs 14 Nov publication-date discrepancy is **UNRESOLVED** and matters for exact phase dates. [Secondary-analyst tier (DSCI summary of MeitY notification; taxmannpublic.com); MeitY-hosted copies not directly fetchable during this run — see Must-verify]
- **Commencement notification**: **G.S.R. 843(E), dated 13 November 2025** (MeitY) — brings different Act sections into force in tranches. [Secondary-analyst tier, corroborated by ≥5 independent sources (DSCI, linkinglaws, munotes, hrengage, iplink-asia)]

### 1.2 Phase-in schedule (as reported from the two gazette notifications)
| In force from | Act sections | Rules |
|---|---|---|
| 13 Nov 2025 (day of publication) | 1(2), 2, 18–26, 35, 38–43, 44(1), 44(3) — institutional: Board constitution, appointments, Govt directions | 1, 2, 17–21 — Board functioning |
| 13 Nov 2026 (1 year) | 6(9), 27(1)(d) — consent-manager registration machinery | Rule 4 — Consent Manager registration/obligations |
| ~13 May 2027 (18 months) | 3–5 (notice/consent), 6(1)–(8), 6(10), 7–10 (legitimate uses, general obligations incl. security & breach, children, SDF), 11–17 (data-principal rights, cross-border, exemptions), 27 (except 27(1)(d)), 28–34 (Board powers, penalties), 36, 37, 44(2) | 3 (notice), 5–16 (security, breach, retention, children, SDF, rights), 22, 23 |

Source for table: DSCI summary of the DPDP Rules (dsci.in/files/content/documents/2025/Digital-Personal-Data-Protection-Rules-2025.pdf), cross-checked against: courtroomexchange.com ("Rule 1, Rule 2 and Rule 17 to 21 ... from 13th November, 2025; Rule 4 ... 13th November 2025 [sic — +1 year]; Rule 3, 5–16, 22 and 23 ... 18 months ... Around 13th May 2027") and grc3.io ("core obligations and the penalty provisions under sections 28 to 34 are scheduled to commence on 13th May, 2027").

**DISCREPANCY (flagged):** The DSCI summary table prints "13th March 2027" for the third tranche, which contradicts 18-month arithmetic from 13 Nov 2025 (= 13 May 2027) and contradicts four other sources. Treat 13 May 2027 as the working date; 13 vs 14 May depends on gazette publication date. **Exact tranche dates must be confirmed from the gazette text by a human** (see Must-verify).

### 1.3 What is live NOW for a small B2B SaaS (as of 4 Oct 2026)
- Only the institutional provisions (Data Protection Board of India setup, appointments, Govt powers to call for information) are in force today. **No notice/consent/security/breach/rights obligation is enforceable against a Data Fiduciary yet.**
- Rule 4 (Consent Manager registration) becomes operative 13 Nov 2026 — not yet as of today; irrelevant unless the startup wants to register as a Consent Manager (it does not).
- Practical meaning: no DPDP penalty exposure today; but **plan for 13 May 2027 compliance now** because consent capture architecture (esp. WhatsApp opt-in records — different from TRAI DLT consent) takes time to build.

### 1.4 What the obligations will require (when in force)
- **Consent notice** (Act s.5; Rule 3): notice must be clear, understandable **without relying on other information**, standalone, itemised (specific personal data collected, purposes, goods/services to be provided), include link to withdraw consent as easily as given, how to exercise data-principal rights, and how to complain to the Board. [DSCI summary; courtroomexchange article]
- **Purpose limitation / legitimate uses**: processing only per consent or the s.7 legitimate uses; state processing under s.7 (subsidy/benefit/service by State) follows Second Schedule standards.
- **Data-principal rights** (ss.11–14; Rules 9, 14): access, correction, erasure, grievance redressal, nomination. Fiduciary must publish on its website/app a business contact (DPO if appointed or other authorised person) to answer processing questions, publish how to submit rights requests (with required identifiers for verification), and operate a grievance system that responds "within a reasonable time, no more than 90 days" (per DSCI summary of Rules 9/14). [Secondary tier]
- **Breach notification** (Act s.8(6); Rule 7): (a) intimation to the Data Protection Board **without delay** on becoming aware; (b) **detailed report within 72 hours** (Board may allow longer on written request); (c) **prompt notice in clear/plain language to every affected Data Principal** via their registered channel/user account, stating what happened, likely impact, mitigation steps, what the individual should do, and a contact point. [dpdpaedu.org Rule 7 guide (secondary-analyst); DSCI summary ("notify the Board immediately ... and, within 72 hours ... share detailed information")] Penalty ceiling for breach-notification failure: **₹200 crore**.
- **Retention/erasure** (Act s.8(7); Rule 8 + Third Schedule): erase when the purpose the data was collected for is no longer served (unless law requires retention); **at least 48 hours' prior notice** to the Data Principal before deletion, giving them a chance to log in/contact to continue the purpose; Third Schedule sets shorter/longer deemed-purposes for listed classes (e.g., e-commerce, gaming, banks). A small B2B SaaS not in the listed classes follows the general erasure rule. **UNVERIFIED**: whether a generic SaaS falls in any Third Schedule class — human check.
- **Security safeguards** (Act s.8(4)–(5); Rule 6): reasonable security safeguards including (at minimum, per DSCI summary of Rule 6) encryption, masking, tokenisation, access controls, monitoring/logging, backups. Note: the *obligation* is on the Data Fiduciary legally from 13 May 2027; the *practice* is recommended now anyway (see CERT-In §3, which IS live now).
- **Children's data** (Act s.9; Rules 10–12; Fourth Schedule): verifiable parental consent before processing a child's data; no tracking/behavioural monitoring/targeted ads directed at children. Exemptions exist for healthcare providers/educational institutions (Fourth Schedule conditions). Low relevance to a B2B payment-reminder tool, but if self-serve sign-ups are not age-gated, note this. [DSCI summary; storyboard18]
- **Significant Data Fiduciary (SDF)**: no automatic threshold; designation is by Central Government notification considering volume/sensitivity of data, risk to data principals, impact on sovereignty/security/electoral democracy/public order (Act s.10; Rule 13). Obligations: **annual DPIA + data audit** (12-month cycle), algorithmic-risk due diligence, and restriction on transfer outside India for certain notified data classes. Penalty up to **₹150 crore** per instance. A small B2B SaaS is **unlikely** to be designated; verify any future SDF notification list. [DSCI summary of Rule 13]
- **Penalty exposure** (Act Schedule; ss.28–34 commence 13 May 2027): up to ₹250 crore (security-safeguards failure, s.8(4)); up to ₹200 crore (breach notification); up to ₹50 crore (other contraventions, incl. notice/consent/rights obligations); data-principal false-report duty capped at ₹10,000. **No MSME/small-business carve-out found in the Rules** — the mitigant is that no penalty can be levied before the penalty provisions commence, and the Board must weigh factors such as nature, gravity and repetition when imposing. [UNVERIFIED detail — see Must-verify re: any proportionality carve-out in the gazette.]
- **Cross-border transfer** (Act s.16; Rule 15): transfers outside India permitted **unless** the Central Government notifies restrictions — i.e., a blacklist model, not a whitelist. So hosting outside India is legally permitted today and under the Rules as notified; watch for notified restrictions. [DSCI summary of Rule 15]

## 2. IT Act 2000 / SPDI Rules 2011 — still relevant?

**Bottom line: YES — both still live today, and they bind a small SaaS NOW (unlike DPDP's fiduciary duties). The SPDI Rules' parent section (IT Act s.43A) is omitted by DPDP s.44(2)(a) with commencement fixed at 13 May 2027; until then the SPDI Rules run alongside the DPDP regime.**

### 2.1 The instruments
- IT Act, 2000 (21 of 2000); s.43A inserted by the IT (Amendment) Act, 2008 w.e.f. 27 Oct 2009. SPDI Rules: **IT (Reasonable security practices and procedures and sensitive personal data or information) Rules, 2011 — G.S.R. 313(E), 11 April 2011**, Ministry of Communications and IT (DIT). [Primary — Gazette text via dataguidance.com/in098en.pdf]
- Sunset: **DPDP Act 2023 s.44(2)(a) omits s.43A IT Act; commencement fixed at 13 May 2027** by the phased-commencement notifications of 13 Nov 2025 (G.S.R. 843(E), 844(E), 845(E)). [veritect.ai explainer (28 Jul 2026) citing primary notifications; legal500.com ("From 13 May 2027, Section 44(2) of the DPDP Act will omit Section 43A of the IT Act and also omit the related rule-making power under Section 87...")] Pending adjudications under IT Act s.46 are preserved by General Clauses Act s.6.

### 2.2 What the SPDI Rules require (verbatim points; primary)
- **Applicability**: "Body corporate" per explanation to s.43A — reaches "a company, firm, sole proprietorship or other association engaged in commercial or professional activities" (veritect.ai's reading of the clause; primary s.43A text aligns). **A one/two-person startup is inside the perimeter.** [secondary-analysis + primary]
- **SPDI definition (Rule 3)**: password; financial information such as bank account / credit card / debit card or other **payment instrument details**; health condition; sexual orientation; medical records/history; biometrics. **For a payment-reminder SaaS, customer payment-instrument references would count as SPDI.** [Primary]
- **Rule 4**: publish a privacy policy on the website stating practices, data types collected, purpose, disclosure, security practices.
- **Rule 5**: **prior consent** before collection; purpose limitation; no retention beyond purpose; option to withdraw consent; correction/amendment on request; **designated Grievance Officer published on the website, redress within one month** (Rule 5(9)).
- **Rule 6**: disclosure to third parties needs prior permission unless contractually agreed or legally required.
- **Rule 7**: transfer of SPDI (anywhere in or outside India) only to entities ensuring **the same level of data protection**, and only where necessary for a lawful contract or with consent.
- **Rule 8(2)**: **IS/ISO/IEC 27001** expressly named as a qualifying "reasonable security practices" standard — a named statutory safe harbour.
- **Rule 8(4)**: "the body corporate ... shall get its security practices audited, at least once per year, by an independent auditor approved by the Central Government or the industry associations..." — i.e., **annual security audit obligation, live now**. [veritect's rendering; the Gazette PDF fetch cut off mid-Rule 8(3); the audit duty is corroborated by veritect.ai and industry commentary. Mark exact sub-rule wording as **partially UNVERIFIED from primary text** — human should pull pp. of G.S.R. 313(E) Rule 8(4).]
- **Breach reporting**: the SPDI Rules contain **none** — veritect: "The SPDI Rules have none; your only pre-DPDP breach clocks are the CERT-In six-hour rule and your sectoral regulator."
- **Safe-harbour mismatch**: ISO 27001 is named under SPDI Rule 8(2) but **not** under DPDP Rule 6 (2025) — plan a re-baseline before 13 May 2027. [secondary-analysis]

### 2.3 Bottom line for the sibling's SaaS
- Between now and 13 May 2027 the startup runs **both** regimes: SPDI (live now: privacy policy, consent, grievance officer ≤1 month, annual audit if using ISO27001 path, transfer controls) + DPDP (coming 2027).
- Practically, a privacy policy + consent receipts + a named grievance contact satisfy overlapping obligations cheaply now.

## 3. CERT-In Directions (2022) — reporting, logs, scope

**Bottom line: Live NOW (effective since ~27 June 2022). "Any entity whatsoever" in scope — including a small SaaS company. Report listed cyber incidents to CERT-In within 6 hours; keep ICT logs for a rolling 180 days and keep them within Indian jurisdiction.**

### 3.1 The instrument (primary source)
- **Title/Number**: "Directions under sub-section (6) of section 70B of the Information Technology Act, 2000 relating to information security practices, procedure, prevention, response and reporting of cyber incidents for Safe & Trusted Internet." — **No. 20(3)/2022-CERT-In**, dated **28 April 2022**, issued by CERT-In, MeitY. [Primary — official PDF, retrieved via web.archive.org copy of cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf; cert-in.org.in itself was not fetchable from this environment]
- Legal basis quote: CERT-In is "empowered and competent to call for information and give directions to the service providers, intermediaries, data centres, body corporate and any other person" (p.2).
- Effective date: **"This direction will become effective after 60 days from the date on which it is issued"** (p.4) → ~27 June 2022.

### 3.2 What must be reported, and within what time (verbatim)
- "**Any service provider, intermediary, data centre, body corporate and Government organisation shall mandatorily report cyber incidents as mentioned in Annexure I to CERT-In within 6 hours of noticing such incidents or being brought to notice about such incidents.**" (p.2, clause (ii))
- Reporting channels: email incident@cert-in.org.in, phone 1800-11-4949, fax 1800-11-6969 (p.2 and p.6).
- **Annexure I list includes** (p.5–6, 20 categories): targeted scanning/probing; compromise of critical systems; **unauthorised access of IT systems/data; data breach; data leak**; malicious code (ransomware, cryptominers); server attacks (DB/mail/DNS); identity theft/spoofing/phishing; DoS/DDoS; attacks on applications such as **e-Commerce**; **attacks or malicious activities affecting cloud systems/servers/applications**; malicious/fake mobile apps; unauthorised access to social media accounts; attacks affecting **AI and ML systems**; etc.
- The direction also derives its incident list from Rule 12(1)(a) of the IT (CERT-In) Rules, 2013 (Annexure I header).

### 3.3 Log retention and where logs must reside (verbatim)
- "All service providers, intermediaries, data centres, body corporate and Government organisations **shall mandatorily enable logs of all their ICT systems and maintain them securely for a rolling period of 180 days and the same shall be maintained within the Indian jurisdiction.** These should be provided to CERT-In along with reporting of any incident or when ordered / directed by CERT-In." (p.3, clause (iv))
- **This is a live in-India log-residency requirement affecting hosting choice** (see §7): application/server logs need to be retained in India for 180 days even if compute runs abroad. [Primary]
- Related, for hosting-provider roles (not the SaaS's own): data centres, VPS, cloud and VPN providers must maintain subscriber/customer registration records for 5 years (clause (v)); VASPs/Custodian wallets KYC+transaction records 5 years (clause (vi)). More explicitly: if the startup only *buys* hosting it isn't a "data centre/VPS provider"; if it *resells* infra this could bite.

### 3.4 Does it apply to a small company? Any MSME relief?
- The direction's scope is deliberately broad — "service providers, intermediaries, data centres, body corporate and Government organisations", plus "any other person" per the empowering provision. **"Body corporate" has no size threshold in the direction text; a small private limited company is within scope.** Analyst corroboration: "It has been clarified that the Directions are applicable to 'any entity whatsoever', in the matter of cyber incidents" (mondaq.com, "Decoding The New Cert-In Directions", 23 May 2022). [Primary + secondary-analysis]
- **No MSME exemption or small-business carve-out found in the direction text.** The sibling should note: a one-person dev shop incorporated as a company is within the literal scope of clause (ii) and (iv).
- **2025–2026 changes / MSME relief: NONE FOUND.** Searches for MSME relief or amended CERT-In directions through Oct 2026 surfaced only compliance-vendor guidance restating the 2022 rules (e.g., corridalegal.com Feb 2026; writerinformation.com Sep 2026: "The CERT-In Directions require ICT system logs to be retained for 180 days within India"). No superseding direction was found. **Status: no change detected as of 4 Oct 2026; a human should re-check cert-in.org.in/Directions.jsp.**
- Penalty for non-compliance: punitive action under s.70B(7) IT Act (the direction invokes it) — i.e., not the DPDP penalty scale.

### 3.5 Practical consequence for this SaaS
- Any of: unauthorized access to its systems, data breach/leak, attack affecting its cloud/hosting, e-commerce/app attacks → report within 6 hours, not 72 hours. Pair this with DPDP Rule 7 (72 h detailed report to the DPB, coming 2027) — two separate clocks, two different regulators (CERT-In vs DPB).
- Keep 180 days of ICT logs *in India*; if app servers sit in a Singapore/EU region, ship logs to an India-resident log store.

## 4. TRAI DLT for SMS

**Bottom line: YES — DLT registration is mandatory before sending ANY commercial SMS (transactional or promotional) to Indian numbers, including OTPs. A small startup must register its entity (PE), a sender ID/header and every message template on a TRAI-approved DLT portal; SMS is blocked at operator level without it. One-time operator fee ₹5,900 incl. GST.**

### 4.1 Legal basis
- Framework: **Telecom Commercial Communications Customer Preference Regulations, 2018 (TCCCPR 2018)** issued by TRAI; mandates DLT registration of entities, headers and templates for commercial SMS. The Blockchain/DLT framework became effectively compulsory from ~Jan–Mar 2022 with operator enforcement (first Mar 2021 deadlines, extended). [TRAI regulation name from provider/industry sources (kaleyra, smsgatewayhub); **TRAI's own PDF (trai.gov.in/sites/default/files/Regulation_31072018_0.pdf) was not fetchable from this environment — mark cited regulation number as high-confidence but not primary-verified in-run**]
- Enforcement reality: "Without registration, SMS is blocked at the operator level — including OTP, order confirmations and bank alerts." (smsgatewayhub.com/dlt-registration, STPL, 2026) [Provider-tier, but consistent across every provider checked]

### 4.2 What must be registered (4 steps)
1. **Entity registration (Principal Entity)** — company KYC: GST certificate, PAN, CIN/incorporation certificate (or Udyam/trade licence for proprietorship), authorised signatory ID; pay the DLT operator fee. Produces a unique **PE ID** used in API calls. Approval: typically 1–3 working days (some portals <24 h).
2. **Sender ID (Header) registration** — a **6-character sender ID** per traffic category; separate headers for promotional vs transactional; new TRAI mandate (May 2025) requires category suffix on all A2P headers: **-P (promotional), -T (transactional), -S (service), -G (government)**. Approval: 1–2 working days.
3. **Content template registration** — every message format pre-approved; fixed text must match exactly at send time; variables in `{#var#}` placeholders; every template gets a **Template ID**. Approval: 24–48 h. **URL whitelisting mandate (Oct 2024): any URL inside an SMS template must be pre-whitelisted on the DLT portal or the message is auto-blocked.**
4. **PE–TM chain binding** — bind your PE ID to your SMS provider's Telemarketer ID; **without this binding all SMS are blocked even after steps 1–3.**
[Source: smsgatewayhub.com/dlt-registration (STPL) — provider-tier but detailed and consistent with other providers; treat specific latencies as typical, not guaranteed]

### 4.3 Where to register and cost
- One registration on **any ONE** operator portal suffices — shared blockchain ledger syncs to all operators: **Jio trueconnect.jio.com, Airtel dltconnect.airtel.in, SmartPing (Videocon) smartping.live, Vi vilpower.in, BSNL ucc-bsnl.co.in, TATA telemarketer.tatateleservices.com**.
- **Fee: ₹5,900 incl. 18% GST, one-time, paid to the chosen DLT operator** (₹5,000 + GST), same across operators. Corroborated by ≥4 providers (smscountry: "The registration costs INR 5,900. It is the same for all DLT operators"; msg24x7; fonada; 2factor). [Provider-tier, high consistency]
- **Templates must** include the brand name, keep 70% fixed content (2factor.in), exact-match at send time (or error code 5101 blocks).

### 4.4 Does the startup need this BEFORE any SMS? 
- **Yes for SMS.** "Yes. DLT registration is mandatory for all businesses sending commercial SMS in India in 2026. This covers promotional, transactional, OTP, service implicit and service explicit SMS. Unregistered SMS is blocked at the operator level. There are no exceptions." (smsgatewayhub.com FAQ, 2026) [Provider-tier]
- For WhatsApp: DLT is **not** required (different channel, Meta's own opt-in framework) — but note that some Indian banks run WhatsApp + SMS fallback, and the SMS leg needs DLT.
- Timeline to plan: allow **~3–7 working days** worst case (entity 1–3 d + header 1–2 d + template 24–48 h), plus PE-TM chain.
- **Practical order for the founder: (a) incorporate/GST (sibling's scope), (b) DLT entity+header+template+PE-TM chain, (c) SMS provider wallet; WhatsApp can proceed in parallel without DLT.**

## 5. WhatsApp Business Platform
_(pending verification)_

## 6. OTP / SMS-pumping fraud guidance
_(pending verification)_

## 7. Hosting — India regions and entry pricing
_(pending verification)_

# Messaging cost comparison
_(pending verification)_

# Compliance checklist for a solo founder
_(pending)_

# Must-verify-by-human
_(pending)_
