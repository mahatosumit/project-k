# GST & Tax Rules for a Small Indian SaaS Business (B2B, India-only)

> Status: IN PROGRESS — sections marked DRAFT are being verified.
> Research date: 2026-10-04. GST law changes via CBIC notifications; re-verify before filing.
> **Nothing here is tax advice.** Facts are stated with sources; decisions are marked for a CA.

Scope: Indian SaaS/software business selling to Indian *business* customers.
Out of scope (owned by other researchers): payment gateway fees/NPCI/MDR; DPDP/CERT-In/hosting.

---

## 1. GST registration thresholds (goods vs services; interstate supply)

**Thresholds (confirmed current as of 2026-10-04):**
- **Services: ₹20 lakh** aggregate turnover in a financial year — general threshold, **Section 22(1) CGST Act, 2017**.
- **Goods: ₹40 lakh** — raised from ₹20 lakh by **Notification No. 10/2019–Central Tax dated 07.03.2019**, effective **01.04.2019**.
- **Special category states: ₹10 lakh** (services); ₹20 lakh (goods).
- *Unchanged since 01.04.2019* — coraa.ai (Jul 2026): "The base limits are ₹20 lakh for normal states and ₹10 lakh for special category states. These limits are unchanged since 1 April 2019."
- **Proposals to raise them have been discussed** (companiesinn, Jul 2025) but **no change was in force** at research date.
- Evidence tier: **SECONDARY but strongly corroborated across 2026-dated sources.** CBIC's legacy PDF paths 404; the precise figure should be re-confirmed on gst.gov.in before reliance.

**Does interstate supply force registration regardless of turnover? — Not for services.**
- **Section 24(i), CGST Act 2017** does list "persons making any inter-State taxable supply" as requiring registration **irrespective of turnover**. This bites hard on **goods**.
- **But for services it was relaxed:** **Notification No. 10/2017–Integrated Tax, dated 13.10.2017** exempted persons making inter-State supplies of taxable **services** from registration, subject to a value limit.
- Both notifications exist: **No. 10/2017–Integrated Tax dated 28.06.2017** (a *rate* notification — different instrument) and **No. 10/2017–Integrated Tax dated 13.10.2017** (the *registration* exemption). Do not conflate them.
- Sources: taxtmi (17.10.2017) — "Notification No. 10/2017-Integrated tax, dated 13.10.2017 the Government exempted the persons making **inter-State supplies of taxable services**"; caclubindia — "Notification No. 10/2017–Integrated Tax, dated 13.10.2017 · supply [Exemption: Inter-State supplies of taxable services…]"; cajatinminocha (Handbook on Registration under GST) — "exempted from obtaining registration under the said Act subject to certain conditions. 6. Notification No. 10/2017-Integrated Tax, dated 13-10-2017 as amended."
- Evidence tier: **SECONDARY (3 independent sources agreeing on number, date and subject).** The exact monetary limit and conditions in the notification were **not verified at primary source** — flagged for a CA.
- **Practical upshot:** an interstate *software service* supplier is generally **not** forced to register below ₹20 lakh. Getting this wrong in either direction is costly, so confirm it.

## 2. Does SaaS to Indian businesses need registration from rupee one?

**No — not from rupee one, by turnover alone.** Two independent tests:
1. **Turnover test** (Section 22): registration only when aggregate turnover **exceeds ₹20 lakh** in a FY (₹10 lakh in special category states).
2. **Interstate test** (Section 24(i)): generally does **not** force a *services* supplier to register below ₹20 lakh because of Notification No. 10/2017–IT(R) (see §1).

**But it is not purely turnover that decides.** Registration is triggered from rupee one if any Section 24 condition applies regardless of turnover — e.g.:
- **Reverse charge** liability (Section 24(iii)),
- **Input Service Distributor**, **casual taxable person**, **non-resident taxable person**,
- supplying through an **e-commerce operator** required to collect TCS (Section 24(ix)),
- or where the **customer is liable to pay under RCM** and the supplier is otherwise unregistered.

**The practical SaaS trap:** many Indian SaaS buyers are large corporates who **cannot take input tax credit (ITC) and will not accept a "bill of supply"**; they demand a tax invoice with a GSTIN. Commercially you may need to register well before ₹20 lakh. This is a **business** reason, not a legal one.
- Evidence tier: HIGH CONFIDENCE on the mechanism; the specific exception notification needs CA-level confirmation.

## 3. Composition scheme for services

**The standard composition scheme (Section 10(1)/(2)) does not apply to services** — it is for **goods** suppliers and, under the restaurant provision, restaurant service providers.

**For services there is a separate scheme — Section 10(2A) CGST Act, 2017:**
- **Rate: 6%** of turnover (**3% CGST + 3% SGST**).
- **Ceiling: ₹50 lakh** aggregate turnover in the preceding financial year.
- **Ineligible if:** making **inter-State supplies**, supplying through an e-commerce operator required to collect TCS, a non-resident taxable person, a casual taxable person, or supplying goods (scheme is services-only).
- No **input tax credit (ITC)**; must issue a **bill of supply**, not a tax invoice; files **CMP-08** quarterly + **GSTR-4** annually.
- Sources: taxscan (03.06.2025) — "50 lakh / 6% (3% + 3%) / On total turnover (Section 10(2A))"; taxguru (15.06.2026) — "The Rs. 50 lakh service-provider limit under Section 10(2A) is the same across the country"; studocu summary — "Person should be engaged in supply of services or mixed supply… Aggregate turnover should not exceed 50 lakhs in the preceding financial".
- Evidence tier: SECONDARY, consistent.
- **Verdict for a SaaS:** the **inter-State supply prohibition generally rules it out** for anyone selling across state lines, and the **no-ITC** rule is a serious problem because your own vendors charge you GST you could otherwise offset. Treat as a corner case for a purely single-state, B2C-only business — **CA decision**.

## 4. SAC codes realistically used for SaaS / software services

Services are classified under the CBIC **"Scheme of Classification of Services"**, built on UNCPC. All entries below carry **18% GST** (the standard service rate).

| SAC | Official description | Realistic use |
|---|---|---|
| **998314** | Information technology (IT) **design and development services** | Custom software / product development, and the common conservative choice for SaaS delivery work |
| **998313** | Information technology (IT) **consulting and support services** | Consulting, implementation, helpdesk |
| **998315** | IT **infrastructure provisioning** services | Managed hosting where the vendor provides infrastructure |
| **998434** | **Licensing services for the right to use computer software and databases** | Software *licences*; often argued to be the wrong code for SaaS delivered purely as a service |
| **998439** | **Other on-line contents** nowhere else classified | Downloadable / online content |
| **998431** | On-line **information and data base retrieval** services | Data / database subscription access |

- Sources: itrsaral SAC lookup — "What SAC code do freelance web developers use? **998314 (IT design and development services) at 18%**. IT consulting is 998313"; incorpx — "9983 14 Information technology (IT) design and development services 18%… 9983 13 Information technology (IT) consulting and support services 18%"; invocreto — "**998439**, All Services, Other on-line contents nowhere else classified"; piceapp shows **998434** described as "Licensing services for the right to use computer software and databases" in a live GSTIN record. **998315** appears as "IT infrastructure provisioning" in the 9983 group listing.
- Evidence tier: SECONDARY — **multiple independent sources agree verbatim on 998314, 998313, 998434 and 998439**; the official CBIC classification PDF could not be fetched (domain blocked the fetch).

**Recommended code for a SaaS subscription delivered as a service: 998314.** Rationale: the subscription is a *service* the vendor operates, not a transfer of a right to use software as such — and 998314 is the description vendors and customers most routinely accept for software development/delivery services.
**However:** the 998314-vs-998434 choice is genuinely fact-dependent and CBIC has issued classification guidance on software. **This is a CA decision (§Must-ask-a-CA).**
**Trap to avoid:** pre-GST law sometimes deemed the right to use software a *deemed sale of goods*. **Under GST a SaaS supply is a service** — do not invoice it as goods.

## 5. Invoice rules (Rule 46 CGST Rules) — VERIFIED AT PRIMARY SOURCE

Source: **CBIC, taxinformation.cbic.gov.in — "Rule 46. Tax invoice" (current rule text)**, fetched 2026-10-04. All clause letters below are the rule's own.

**Which document:** a registered person making a **taxable** supply issues a **tax invoice**; a supplier of exempt supply or a composition dealer issues a **bill of supply** instead (Rule 49). A SaaS making taxable supplies issues a **tax invoice**.

**Mandatory particulars — Rule 46, verbatim clause list:**

| Clause | Particular (rule's own wording, abbreviated) |
|---|---|
| **(a)** | "name, address and **Goods and Services Tax Identification Number of the supplier**" |
| **(b)** | "a **consecutive serial number not exceeding sixteen characters**, in one or multiple series, containing alphabets or numerals or special characters - hyphen or dash and slash symbolised as \"-'' and \"/\" respectively, and any combination thereof, **unique for a financial year**" |
| **(c)** | "date of its issue" |
| **(d)** | "name, address and **GSTIN or Unique Identity Number, if registered, of the recipient**" |
| **(e)** | name, address of recipient + **address of delivery**, with **State name and code**, if recipient is **unregistered** and taxable supply ≥ **₹50,000** |
| **(f)** | same as (e) where value < ₹50,000 **and the recipient requests** it be recorded |
| **(g)** | "**Harmonised System of Nomenclature code** for goods or services" (i.e. HSN/SAC) |
| **(h)** | "description of goods or services" |
| **(i)** | "quantity in case of goods and unit or Unique Quantity Code thereof" |
| **(j)** | "**total value of supply** of goods or services or both" |
| **(k)** | "**taxable value** of the supply… taking into account discount or abatement, if any" |
| **(l)** | "**rate of tax** (central tax, State tax, integrated tax, Union territory tax or cess)" |
| **(m)** | "**amount of tax charged** in respect of taxable goods or services (central tax, State tax, integrated tax, Union territory tax or cess)" |
| **(n)** | "**place of supply along with the name of the State**, in the case of a supply in the course of **inter-State trade or commerce**" |
| **(o)** | "address of delivery where the same is different from the place of supply" |
| **(p)** | "whether the tax is **payable on reverse charge basis**" |
| **(q)** | "**signature or digital signature** of the supplier or his authorised representative" |
| **(r)** | QR code with embedded **IRN**, **in case invoice has been issued in the manner prescribed under sub-rule (4) of rule 48** (i.e. where e-invoicing applies) |
| **(s)** | a **declaration** that the invoice is not required to be issued under rule 48(4), for taxpayers whose turnover exceeded the e-invoicing threshold but who are not required to so prepare — verbatim: *"I/We hereby declare that though our aggregate turnover in any preceding financial year from 2017-18 onwards is more than the aggregate turnover notified under sub-rule (4) of rule 48, we are not required to prepare an invoice in terms of the provisions of the said sub-rule."* |

**Special proviso caught on the same page — important for an online service:**
> "*Provided 10[in cases involving supply of online money gaming or in cases] that where any taxable service is supplied by or through an electronic commerce operator or by a supplier of **online information and database access or retrieval services** to a recipient who is **un-registered**, irrespective of the value of such supply, a tax invoice issued by the registered person shall contain the **name of the state of the recipient** and the same shall be deemed to be the address on record of the recipient*"

That proviso speaks directly to **OIDAR** supplies to unregistered recipients — it is a place-of-supply/address rule, and OIDAR has its own registration regime. Flag to a CA if the SaaS sells to unregistered consumers.

**Signature — resolved at primary source:** Rule 46(q) requires "signature or digital signature". **A separate proviso expressly exempts it:** "*Provided also that the **signature or digital signature of the supplier or his authorised representative shall not be required** in the case of issuance of an **electronic invoice** in accordance with the provisions of the **Information Technology Act, 2000***." → An electronically issued invoice does **not** need a physical signature.

**Serial-number rules:** consecutive, **≤16 characters**, one or multiple series, alphabets/numerals/- and / allowed, **unique for a financial year** [Rule 46(b), verbatim above].

**Is a PDF e-invoice acceptable?** For a business **below** the e-invoicing threshold: yes — a normal PDF invoice carrying all Rule 46 particulars is valid, and the signature proviso means electronic issuance is contemplated. It becomes an *e-invoice* in the technical sense only when reported to the IRP for an IRN (§6).

**Time limit to issue an invoice for services — Rule 47:** **within 30 days from the date of supply of service**; **45 days** for banking/financial institutions/NBFCs/telecom. Continuous supply of services is governed by **Section 31(5)**.
- Source: **taxinformation.cbic.gov.in, "Rule 47 of the CGST Rules"** — verbatim: "*Rule 47. Time limit for issuing tax invoice.-* shall be issued within a period of thirty days from the date of the supply of service:" [PRIMARY — CBIC-hosted]

## 6. E-invoicing (IRN / QR / IRP)

**Current turnover threshold: ₹5 crore** aggregate turnover in any FY (from 01.08.2023).
- Changed from ₹10 crore to **₹5 crore** by **Notification No. 10/2023–Central Tax dated 10.05.2023**, effective **01.08.2023**. This inserted/replaced "ten crore rupees" with "five crore rupees" in the relevant e-invoicing notification.
- Historical ladder: ₹500 cr → ₹100 cr (01.01.2020) → ₹50 cr → ₹20 cr (01.04.2021) → ₹10 cr (01.10.2022) → **₹5 cr (01.08.2023)**.
- **Yes, it applies to B2B services** — the rule is turnover-based against *aggregate turnover*, and B2B service suppliers above the threshold are covered. Document type matters (B2B invoice, export invoice, credit/debit notes, RCM invoices), not goods-vs-services.
- **What is required:** report the invoice to the **Invoice Registration Portal (IRP)** and obtain an **IRN (Invoice Reference Number)** plus a **signed QR code**; the tax invoice must carry the **IRN and QR code**. Reportable window for entities ≥₹10 cr: within 30 days of invoice date (and for turnover below that, up to the time of filing of the return — verify current wording).
- **For a small SaaS (below ₹5 crore): e-invoicing does NOT apply.** Self-generated invoice numbering remains fine.
- Evidence tier: SECONDARY but strongly corroborated (ET Government 11.05.2023; TaxScan on Notification 10/2023; NYCA 01.08.2023).

## 7. Place of supply (B2B vs B2C, IGST vs CGST+SGST)

**Governing law:** Sections 12 and 13, **IGST Act, 2017**. Section 12 = general rule for supplies where **supplier and recipient are both in India**; Section 13 = default rule for cross-border (not needed for an India-only SaaS).

**B2B (recipient is a registered person) — Section 12(2)(a):** the **place of supply is the location of the recipient** (specifically, where the recipient has taken registration / the location in the recipient's registration). The invoice must carry the recipient's GSTIN.
- Source: taxguru.in — "For general services, place of supply will be the place of for which recipient obtained GSTIN and if GSTIN not obtained then definition of…"; corroborated by a compiled Sec 12(2) table: "[Sec 12(2)] Recipient Status: Registered → Condition: — → Place of Supply: Location of recipient". [SECONDARY, consistent]

**B2C (recipient unregistered) — Section 12(2)(b):** place of supply is the **address of the recipient recorded on record** (or the address of the recipient available at the time of supply); where no such address is available — **the location of the supplier**.
- Evidence tier: SECONDARY, consistent across sources. Legal text should be confirmed on cbic.gov.in.

**IGST vs CGST+SGST — the decisive test for a services supplier:**
- **Supplier and place of supply in the SAME State** → **CGST + SGST** (intra-State), charged at half the rate each (e.g. 9% + 9% = 18%).
- **Supplier and place of supply in DIFFERENT States** → **IGST** at the full rate (e.g. 18%).
- For a **registered B2B customer**, since place of supply = **customer's location**, a supplier in State A billing a registered customer in State B charges **IGST**. This is the common case for a SaaS selling across India.
- Evidence tier: HIGH CONFIDENCE (standard GST mechanism; Section 12(2) + Section 7/8 IGST Act).

**Note the interaction with registration (§1/§2):** while *below* the threshold you may not be registered and cannot charge tax; but the moment you register, supplying interstate services means **IGST on those invoices** — and you then also need to file returns (§9).

## 8. TDS on software/SaaS payments (194C vs 194J vs 194Q)

> ⚠️ **MAJOR CHANGE — the section numbers below are the OLD Act's.** As of **01.04.2026**, the **Income-tax Act, 2025** replaced the Income-tax Act, 1961 and **consolidated the TDS sections**. Today is **October 2026**, so the **new numbering is the live numbering**. Do not quote the old sections on invoices or correspondence after FY 2026-27 begins.

**In plain terms:**
- A **corporate customer paying a small SaaS** is very likely a **deductor**. When they pay you for services, they may **deduct TDS** and deposit it against **your PAN**, and you claim credit for it.
- Historically the two candidate sections for software/SaaS were:
  - **194C** — TDS on payments to **contractors** (typically **2%** for non-individual contractors / 1% for individuals & HUF), thresholds **₹30,000 per contract** / **₹1,00,000 aggregate per year**.
  - **194J** — TDS on **professional or technical fees** (**10%**; **2%** for certain technical services), threshold **₹30,000** (some representations for ₹50,000 — verify).
  - **194Q** — TDS on **purchase of goods** (0.1% above ₹50 lakh) — **not** the operative section for a pure service supply.
- **The core substantive question — is a software/SaaS payment "royalty" (10%) or a contract/professional payment (2%/10%)?** The Supreme Court in **Engineering Analysis Centre of Excellence Pvt. Ltd. v. CIT (2021)** held that payments for **shrink-wrap / off-the-shelf software** do not amount to use of the **underlying copyright**, so they are **not royalty**. The IBA summarised: "Court found the amounts paid are akin to simpliciter purchase of goods and, therefore, do not give rise to a liability to deduct any taxes at…". Khaitan & Co (22.03.2021) and akmglobal confirm the same holding.
  - **Caveat:** that case concerned *imported* software and the *royalty* characterisation (withholding on payments to non-residents, Section 195). Applying it to **domestic 194J-vs-194C** classification for an Indian SaaS is **not a straight-line inference**. For a genuinely *hosted, ongoing SaaS service*, the more common characterisation is **technical/professional services** rather than a goods purchase. **This is exactly a CA question — the rate differs (2% vs 10%).**
- **New numbering (from 01.04.2026):** the old section-wise TDS structure was **consolidated into Section 393** of the **Income-tax Act, 2025**. Sources:
  - **incometax.gov.in** (primary, current) — "A circular clarifying the term 'work' under section 194C of the old Act will continue to apply to **section 393** of the ITA 2025, where the intent…".
  - **taxaj.com** section-mapping — "**Section 194J → Section 393.** Professional and technical fees are also included in the consolidated TDS…" and "**No. 6(i), rather than old Section 194C**".
  - **eirc-icai.org**, "Overview of key provisions of Income Tax Act, 2025" (01.04.2026) — includes a mapping table "Sec 194 … Sec 194C … Sec 194J … (section – sec 393)".
  - wraptax.com — "Income-tax Act, 2025 removes the earlier section-wise TDS structure (like 194C, 194J, 194H etc.) and consolidates all deduction provisions".
  - batchwise.ai (29.05.2026) — "Section 194J is consolidated under Section 393 of the Income-tax Act, 2025. **Transactions on or after 1 April 2026 must quote Section 393.**"
- **Rate under the new Act:** the **10% professional/technical** and **2% contractor** rates are reported to continue within the consolidated Section 393 structure. **Thresholds reported inconsistently across secondary sources (₹30,000 vs ₹50,000; and one source quoting a ₹2.5 lakh/₹3 lakh shift)** — **UNVERIFIED**. Confirm the exact rate + threshold for your service characterisation with a CA against the current Act text/Finance Act.

**What a small SaaS must practically do:**
1. Put your **PAN** on your invoice — that is what the customer uses to deduct.
2. Expect the customer to **deduct TDS on the pre-GST amount** and pay you the balance.
3. **Reconcile** the deducted TDS against **Form 26AS** and the **Annual Information Statement (AIS)** on the income-tax portal; TDS credit appears against your PAN.
4. **Match** what customers actually deducted against your invoice register; chase missing TDS credits from the customer with the invoice number.
5. File your **income-tax return** claiming the TDS credit — an unclaimed TDS deduction is a cash loss.
6. **Do not decide 2% vs 10% yourself.** Ask the CA in writing so your invoice wording (and possibly the customer's deduction) is consistent.
- Evidence tier: Primary for the **existence of the renumbering** (incometax.gov.in) and for the **Supreme Court holding** (multiple law-firm notes on Engineering Analysis Centre, 2021). SECONDARY/UNVERIFIED for the **exact rate and thresholds** under Section 393.

## 9. GSTR filing cadence (GSTR-1, GSTR-3B, QRMP)

**Returns a small B2B SaaS supplier files once registered:**

| Return | What it reports | Frequency | Due date |
|---|---|---|---|
| **GSTR-1** | Outward supplies (your sales) | **Monthly** if turnover > ₹5 cr; **Quarterly** if in QRMP | **11th** of the following month (monthly); **13th** of the month following the quarter (quarterly, QRMP) |
| **IFF** (Invoice Furnishing Facility) | Optional month-by-month upload of B2B invoices in months 1 & 2 of a QRMP quarter | Monthly (optional) | **13th** of the following month |
| **GSTR-3B** | Summary return + tax payment | **Monthly**, or **quarterly** under QRMP | **20th** of the following month (monthly). Quarterly QRMP filers: **22nd or 24th** depending on state group |

**QRMP (Quarterly Return, Monthly Payment) scheme:**
- **Eligibility: aggregate turnover up to ₹5 crore** in the preceding financial year.
- **How it works:** you file the **return quarterly** but **pay tax monthly** (the monthly payment is made via a challan, PMT-06, by the **25th** of each month in the quarter).
- **State-group staggering:** for quarterly GSTR-3B, states are split into **Group A (due 22nd)** and **Group B (due 24th)** of the month following the quarter.
- **Practical for a small SaaS:** at well under ₹5 crore, QRMP is usually available and reduces filing to 4 GSTR-1s + 4 GSTR-3Bs a year — but the **IFF** (13th monthly) is worth using so that your B2B customers see their input tax credit on time. Customers complain loudly when ITC is delayed.
- Evidence tier: SECONDARY but strongly consistent (tallysolutions.com — "GSTR-1 (Monthly): 11th of the following month; GSTR-1 (Quarterly – QRMP): 13th of the month following the quarter"; taxced.com — "The due date for GSTR-3B is usually the 20th of the following month. For quarterly filers under the QRMP scheme, it is filed on the 22nd or 24th…"; iicpa.in — "File GSTR-1 by 11th of next month / File GSTR-3B by 20th of next month"). **Due dates are frequently extended by notification around year-end — check the CBIC portal each quarter.**

## 10. Threshold relief, LUT/exports notes, 2025–2026 changes

**GST 2.0 rate rationalisation (effective 22.09.2025):** the four-slab structure (5/12/18/28) was collapsed to a **two-slab structure of 5% and 18%**, with a **40% slab for sin/luxury goods**. Implemented via CBIC rate notifications of **September 2025** (e.g. Notification No. 09/2025–Central Tax (Rate) line of notifications; a corrigenda was issued 18.09.2025).
- **Consequence for SaaS:** 18% continues to apply to IT/software services. **Verify the current rate for your exact SAC entry before invoicing** — the September 2025 notifications renumbered and re-lettered schedules.
- Evidence tier: SECONDARY (several sources; ET/Moneycontrol 22.09.2025 effective date). **Re-verify the software-services entry in the current rate notification.**

---

# Invoice field checklist

Concrete list of what the software must put on a tax invoice (from **Rule 46, verified verbatim at CBIC**, §5). Clause letters in brackets.

**Header / supplier (mandatory)**
- [ ] Supplier **name** and **address** [46(a)]
- [ ] Supplier **GSTIN** [46(a)]
- [ ] **Invoice serial number** — consecutive, **≤16 characters**, unique for the financial year [46(b)]
- [ ] **Date of issue** [46(c)]
- [ ] Document title containing the words **"Tax Invoice"**

**Recipient (mandatory)**
- [ ] Recipient **name** and **address** [46(d)]
- [ ] Recipient **GSTIN** — required when the recipient is registered (this is the normal B2B SaaS case) [46(d)]
- [ ] For an **unregistered** recipient with taxable value **≥ ₹50,000**: recipient name + address, **address of delivery**, plus **State name and State code** [46(e)]
- [ ] For an unregistered recipient **< ₹50,000**: only if the recipient asks [46(f)]

**Line items**
- [ ] **SAC code** (HSN for goods) [46(g)] — use the SAC chosen per §4
- [ ] **Description of services** [46(h)]
- [ ] Quantity/unit — only for goods; N/A for SaaS [46(i)]

**Money**
- [ ] **Total value** of supply [46(j)]
- [ ] **Taxable value** (after discount/abatement if any) [46(k)]
- [ ] **Rate of tax**, shown separately as **CGST / SGST / UTGST / IGST / cess** [46(l)] — 18% for these services (§4, §10)
- [ ] **Amount of tax charged**, split the same way [46(m)]

**Place of supply**
- [ ] **Place of supply with State name** — required in inter-State supply [46(n)]
- [ ] **Address of delivery** if different from place of supply [46(o)]

**Compliance flags**
- [ ] "**Tax payable on reverse charge**" indicator (Yes/No) [46(p)]
- [ ] **Signature or digital signature** of supplier/authorised rep — *not required if the invoice is issued electronically under the IT Act, 2000* (proviso) [46(q)]

**Only when e-invoicing applies (turnover above the notified threshold, §6)**
- [ ] **QR code embedding the IRN** [46(r)]
- [ ] The **turnover declaration** text where the taxpayer is above the e-invoicing turnover threshold but not required to prepare under rule 48(4) [46(s)]

**Software must also be able to**
- [ ] Number invoices **consecutively** and keep the series **unique per financial year**; never reuse a number
- [ ] Issue within **30 days of supply** for services (Rule 47)
- [ ] Emit **IGST** when the place of supply is a different State; **CGST+SGST** when within the same State (§7)
- [ ] Carry the customer's **PAN** (for TDS, §8) as a commercial, not GST, requirement
- [ ] Store an **audit trail** (invoice → customer → return filed → TDS credit reconciled)
- [ ] Support **credit notes / debit notes** for corrections (Rule 53)

---

# Must-ask-a-CA

1. **Interstate registration exemption.** Confirm that **Notification No. 10/2017–Integrated Tax (Rate)** still exempts an unregistered **service** supplier from the Section 24(i) compulsory-registration trigger below the threshold — and that your exact service falls inside it. (I could not verify this at primary source.)
2. **SAC code.** Choose between **998314** (IT design & development services) and **998434** (licensing services for the right to use computer software) for your product. The correct code affects the invoice and possibly the rate entry.
3. **Rate entry under GST 2.0.** Confirm the current entry and rate for your chosen SAC in the **September 2025 rate notifications** (the schedules were renumbered/corrected — a corrigenda issued 18.09.2025).
4. **TDS characterisation.** Is your SaaS payment **2% (contractor) or 10% (professional/technical)** under the **consolidated Section 393 of the Income-tax Act, 2025**? Get this in writing, because it decides how much cash your customers withhold.
5. **TDS rate and threshold under the new Act.** My sources disagreed on thresholds; get the current figures confirmed.
6. **OIDAR.** If you ever sell to **unregistered consumers** (B2C) — especially outside India — OIDAR rules change the registration and place-of-supply analysis entirely (see the Rule 46 proviso on online information/database access or retrieval services).
7. **Composition (Section 10(2A)).** Confirm whether it is worth it at all: no ITC, no interstate supply allowed — usually fatal for a SaaS with out-of-state customers.
8. **HSN/SAC digit count.** Confirm how many digits your turnover band requires on the invoice (the rule's proviso lets the Board specify digits by class of person).
9. **Export / LUT.** If you ever bill customers outside India: zero-rated supply + **LUT in Form GST RFD-11** to avoid paying IGST up front. Get this set up *before* the first export invoice.
10. **Due dates.** Return due dates get extended by notification near year-end; have the CA confirm each quarter rather than trusting this document.

---

# Sources

- Notification No. 10/2019–Central Tax, dated 07.03.2019 (goods threshold ₹40 lakh; services stay ₹20 lakh). [SECONDARY — CBIC PDF fetch 404; mirrored in EY/TaxGuru alerts of 07.03.2019]
- Section 22(1) and Section 24(i)/(iii)/(ix), CGST Act, 2017. [PRIMARY-ish — well-reported statutory text; verify on cbic.gov.in]
- Notification No. 10/2017–Integrated Tax (Rate), dated 13.10.2017 (exemption from registration for inter-State supply of services up to threshold). [SECONDARY]
- Section 10(2A), CGST Act, 2017 (services composition scheme, 6%, ₹50 lakh). [SECONDARY]
- CBIC Scheme of Classification of Services — SAC 998314 / 998313 / 998434 / 998439. [SECONDARY, multiple agreeing sources]
- Notification No. 10/2023–Central Tax, dated 10.05.2023 (e-invoicing threshold ₹10 cr → ₹5 cr, w.e.f. 01.08.2023). [SECONDARY, strongly corroborated]
- CBIC rate notifications, September 2025 (GST 2.0 two-slab 5%/18% + 40%, effective 22.09.2025). [SECONDARY]
- cbic-gst.gov.in (CBIC GST portal, live as of research date — homepage reachable, legacy PDF paths 404).
