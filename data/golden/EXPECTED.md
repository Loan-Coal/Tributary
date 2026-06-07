# EXPECTED.md — Golden Scenario Ground Truth

**Document purpose:** This file contains the hand-computed expected values for the Meridian Group
golden scenario. Every obligation, threshold check, and deadline that the deterministic engine will
compute must match these figures exactly. If the engine disagrees with any value here, the engine
has a bug — not this file.

**Scenario:** The Meridian Group — four entities, four jurisdictions of tax exposure, one planted
PE Triangle conflict designed to exercise double-taxation detection, treaty credit computation, and
multi-jurisdiction CIT attribution.

**Produced:** 2026-06-06 (hand-computed; no AI arithmetic used)

---

## 1. Assumptions

### 1.1 FX Reference Rates

| Pair | Rate | Source |
|------|------|--------|
| EUR/HKD | 8.50 | Golden scenario reference rate (as_of_date: 2025-01-01) |
| USD/HKD | 7.78 | Golden scenario reference rate (as_of_date: 2025-01-01) |

All amounts in this file are denominated in **HKD** unless otherwise stated.

### 1.2 Fiscal Periods

| Entity | Fiscal Year | Period |
|--------|-------------|--------|
| MERID-HK | HK Profits Tax year | 1 April 2025 – 31 March 2026 |
| MERID-DE | German CIT year | 1 January 2025 – 31 December 2025 |
| MERID-FR | French CIT year | 1 January 2025 – 31 December 2025 |
| MERID-US | US federal CIT year | 1 January 2025 – 31 December 2025 |

### 1.3 Rule As-of Dates (DEC-004)

All rule applications must surface the `as_of_date` of the rule pack used. Demo packs use
simplified rules — this is an honest, disclosed limitation.

| Jurisdiction | Rule Pack | as_of_date | source_citation |
|---|---|---|---|
| HK | hk_profits_tax | 2023-04-01 | HK IRO Cap.112 (as amended 2023) |
| DE | de_cit | 2024-01-01 | KStG 2024 (Körperschaftsteuergesetz) |
| DE | de_trade_tax | 2024-01-01 | GewStG 2024 (Gewerbesteuergesetz) |
| DE | de_wht | 2024-01-01 | EStG §43; HK-DE DTA (BGBl 2010 II) |
| DE-FR | de_fr_dta | 2017-01-01 | DE-FR DTA Art.5, Art.23 (OECD 2017 service PE) |
| FR | fr_cit | 2024-01-01 | CGI Art.206 (Code général des impôts) |
| FR | fr_vat | 2024-01-01 | CGI Art.293B (VAT threshold) |
| FR | fr_wht | 2024-01-01 | CGI Art.119bis; EU PSD 2011/96/EU |

### 1.4 Simplifications Made (needs_review flags)

The following items are modeled with simplifying assumptions for the demo. They are flagged
`needs_review: true` in engine output and brief output.

| Item | Simplification | Deferred to |
|------|---------------|-------------|
| HK source-rule (T001) | Royalty treated as HK-sourced under IRO s.15(1)(b). Actual sourcing depends on where IP is used — further analysis needed. | ISSUE-001 |
| HK interest income (T006) | T006 interest received by MERID-HK excluded from HK taxable income (not a money-lending business). Flag as needs_review. | ISSUE-002 |
| T007 management fee arm's-length | Assumed arm's-length. Transfer pricing analysis deferred. | ISSUE-003 |
| FR VAT arithmetic | VAT filing obligation is flagged; net VAT payable not computed in v1. | ISSUE-004 |
| Zinsschranke deduction model | T006 interest (HKD 320,000) is included as a deductible expense in DE net income. This simplified model does not apply thin-cap adjustments. Zinsschranke barrier check is performed and not breached. | In-scope check below |
| PE attribution percentage | 35% used as stated in DEC-007. Actual arm's-length attribution requires functional analysis. | ISSUE-005 |

---

## 2. Transaction Reference

| tx_id | From | To | Type | Amount (HKD) | Note |
|-------|------|----|------|-------------|------|
| T001 | MERID-DE | MERID-HK | Royalty (IC) | 2,400,000 | DE pays HK; HK records as royalty income |
| T002 | MERID-DE | MERID-FR | Royalty (IC) | 600,000 | DE sub-licences to FR; FR records as royalty income received |
| T003 | MERID-DE | — | Presence marker | 0 | 185 days in France → PE trigger |
| T004 | MERID-FR | MERID-DE | Dividend (IC) | 900,000 | FR pays DE; §8b KStG applies |
| T005 | MERID-DE | MERID-HK | Dividend (IC) | 1,500,000 | DE pays HK; WHT applies |
| T006 | MERID-DE | MERID-HK | Interest (IC) | 320,000 | DE pays HK; 0% WHT under DTA |
| T007 | MERID-FR | MERID-HK | Management fee (IC) | 300,000 | FR pays HK; 12.8% WHT |
| T008 | 3rd party | MERID-DE | Revenue | 6,200,000 | Third-party; DE records as revenue |
| T009 | 3rd party | MERID-FR | Revenue | 2,800,000 | Third-party; FR records as revenue |
| T010 | 3rd party | MERID-US | Revenue | 3,890,000 | USD 500,000 × 7.78; US records as revenue |
| T011 | MERID-US | MERID-HK | Dividend (IC) | 389,000 | USD 50,000 × 7.78; 30% US WHT (no HK-US DTA) |

---

## 3. MERID-HK — Profits Tax (FY 1 April 2025 – 31 March 2026)

### 3.1 Applicable Rules

- Rule: HK Profits Tax
- Rate: **16.5%**
- Scope: Territorial — only HK-sourced profits taxable
- Exemptions: Dividends received from foreign companies are not taxable (territorial exclusion)
- Rule as_of_date: 2023-04-01 | source: HK IRO Cap.112 s.14

### 3.2 Income Classification

| Transaction | Amount (HKD) | Treatment | Taxable? |
|------------|-------------|-----------|----------|
| T001 royalty received from MERID-DE | 2,400,000 | HK-sourced royalty income — included (needs_review: true; see IRO s.15(1)(b)) | YES |
| T007 management fee received from MERID-FR | 300,000 | HK-sourced management services provided from HK | YES |
| T005 dividend received from MERID-DE | 1,500,000 | Foreign-source dividend — territorial exclusion | NO |
| T006 interest received from MERID-DE | 320,000 | Not a money-lending business; excluded (needs_review: true) | NO |

### 3.3 Taxable Income Computation

```
Taxable income:
  T001 royalty received          HKD 2,400,000
  T007 management fee received   HKD   300,000
                                 ─────────────
  Total taxable income           HKD 2,700,000

HK Profits Tax:
  2,700,000 × 16.5%  =          HKD   445,500
```

**MERID-HK Profits Tax: HKD 445,500**

### 3.4 WHT Obligations (MERID-HK as payer)

MERID-HK makes no outbound payments to non-HK entities in this scenario. No WHT from MERID-HK.

### 3.5 Filing Deadline

- **April 30, 2026** (Profits Tax Return due within one month after end of assessment year)
- Rule as_of_date: 2023-04-01 | source: HK IRO Cap.112 s.51

---

## 4. MERID-DE — German CIT, Trade Tax, WHT (FY 1 January 2025 – 31 December 2025)

### 4.1 Applicable Rules

| Rule | Rate | as_of_date | source |
|------|------|-----------|--------|
| CIT | 15% | 2024-01-01 | KStG §23 |
| Solidarity surcharge | 5.5% on CIT | 2024-01-01 | SolZG §3 |
| CIT effective rate | 15% × 1.055 = **15.825%** | 2024-01-01 | Combined KStG + SolZG |
| Trade Tax (Gewerbesteuer) | 14% (average municipality) | 2024-01-01 | GewStG §11 |
| §8b KStG participation exemption | 95% exempt, 5% deemed expense | 2024-01-01 | KStG §8b |
| Mindestbesteuerung (loss cap) | Full offset ≤ €1M; 60% above | 2024-01-01 | KStG §10d |
| WHT on dividends (domestic) | 25% | 2024-01-01 | EStG §43(1) |
| WHT on interest (domestic) | 25% | 2024-01-01 | EStG §43(1) |
| HK-DE DTA dividend | 5% (beneficial owner ≥10% for ≥12 months) | 2010-04-13 | HK-DE DTA Art.10 |
| HK-DE DTA interest | 0% | 2010-04-13 | HK-DE DTA Art.11 |

### 4.2 Revenue and IC Receipts

```
T008 third-party revenue received:      HKD 6,200,000
T004 dividend from MERID-FR (gross):    HKD   900,000
  §8b KStG exemption (95%):            (HKD   855,000)
  §8b KStG taxable portion (5%):        HKD    45,000
                                        ─────────────
  Gross income before deductions:       HKD 6,245,000
```

### 4.3 Deductible Expenses

```
T001 royalty paid to MERID-HK:          HKD 2,400,000  (deductible)
T002 royalty paid to MERID-FR:          HKD   600,000  (deductible)
T006 interest paid to MERID-HK:         HKD   320,000  (deductible — see Zinsschranke check below)
T005 dividend paid to MERID-HK:         HKD 1,500,000  (NOT deductible — distribution, not expense)
```

### 4.4 Zinsschranke Check (Interest Barrier — T006)

Rule as_of_date: 2024-01-01 | source: EStG §4h

```
Net interest expense (T006):            HKD   320,000

EBITDA proxy (operating income before interest):
  Third-party revenue:                  HKD 6,200,000
  §8b taxable dividend income:          HKD    45,000
  Less royalty deductions:             (HKD 3,000,000)   [T001 + T002]
  EBITDA proxy:                         HKD 3,245,000

30% EBITDA cap:
  3,245,000 × 30%:                      HKD   973,500

Actual net interest:                    HKD   320,000
Cap:                                    HKD   973,500
Comparison:   320,000 < 973,500  →  Zinsschranke NOT BREACHED
```

**Result: T006 interest (HKD 320,000) is fully deductible.**

### 4.5 Net Income Before PE Deduction

```
Third-party revenue:                    HKD 6,200,000
§8b taxable dividend income:            HKD    45,000
Less: T001 royalty paid:               (HKD 2,400,000)
Less: T002 royalty paid:               (HKD   600,000)
Less: T006 interest paid:              (HKD   320,000)
                                        ─────────────
Net income before PE deduction:         HKD 2,925,000
```

### 4.6 PE Attribution (T003 — Service PE in France)

Rule as_of_date: 2017-01-01 | source: DE-FR DTA Art.5 (OECD 2017 service PE provision)

```
Presence days:                          185 days
PE threshold:                           183 days
Comparison:  185 > 183  →  PE TRIGGERED

Attribution percentage:                 35%
  (DEC-007: service delivery attribution based on proportion of DE activities in France)

PE-attributed income:
  2,925,000 × 35%:                      HKD 1,023,750

DE taxable base after PE deduction:
  2,925,000 − 1,023,750:                HKD 1,901,250
```

**PE trigger: CONFIRMED. Attributed income: HKD 1,023,750 (taxed in France as PE income).**

### 4.7 Loss Carryforward — Mindestbesteuerung (DEC-008)

Rule as_of_date: 2024-01-01 | source: KStG §10d (Mindestbesteuerung)

```
Prior-period loss (FY2024):             HKD 1,600,000
DE taxable base (post PE):              HKD 1,901,250

Mindestbesteuerung threshold:
  €1,000,000 × 8.50 EUR/HKD:           HKD 8,500,000

Comparison: 1,901,250 < 8,500,000  →  FULL LOSS OFFSET ALLOWED (no 60% cap)

Allowable offset:
  min(1,600,000, 1,901,250):            HKD 1,600,000  (full prior loss consumed)

Post-loss taxable base:
  1,901,250 − 1,600,000:                HKD   301,250

Remaining loss carryforward:            HKD         0
```

### 4.8 CIT Computation

```
Taxable base:                           HKD   301,250
CIT rate (15% + 5.5% soli surcharge):  15.825%

CIT:
  301,250 × 0.15825:                    HKD    47,672.81
  Rounded to nearest HKD:               HKD    47,673
```

**MERID-DE CIT: HKD 47,673**

### 4.9 Trade Tax Computation

Rule as_of_date: 2024-01-01 | source: GewStG §11(2)

```
Taxable base (same as CIT base):        HKD   301,250
Trade Tax rate (average municipality):  14%

Trade Tax:
  301,250 × 0.14:                       HKD    42,175.00
  Rounded to nearest HKD:               HKD    42,175
```

**MERID-DE Trade Tax: HKD 42,175**

### 4.10 WHT on Outbound Payments from MERID-DE

#### T005 — Dividend to MERID-HK (HKD 1,500,000)

Rule as_of_date: 2024-01-01 (domestic) / 2010-04-13 (DTA) | source: EStG §43; HK-DE DTA Art.10

```
Gross dividend:                         HKD 1,500,000

Domestic German WHT rate:               25%
Domestic WHT:  1,500,000 × 25%:        HKD   375,000

Treaty condition check (HK-DE DTA Art.10):
  Beneficial owner holds ≥10%?          YES (MERID-HK holds 100% of MERID-DE)
  Holding period ≥12 months?            YES (held since 2020; >5 years by 2025)
  Treaty rate:                          5%

Treaty WHT:  1,500,000 × 5%:           HKD    75,000
Treaty relief (domestic less treaty):   HKD   300,000
```

**T005 WHT payable: HKD 75,000 (treaty rate 5% applies)**

#### T006 — Interest to MERID-HK (HKD 320,000)

Rule as_of_date: 2010-04-13 | source: HK-DE DTA Art.11

```
Gross interest:                         HKD   320,000

Domestic German WHT rate:               25%
Domestic WHT:  320,000 × 25%:          HKD    80,000

Treaty rate (HK-DE DTA Art.11):         0%
Treaty WHT:                             HKD         0
Treaty relief:                          HKD    80,000
```

**T006 WHT payable: HKD 0 (0% treaty rate applies)**

### 4.11 Filing Deadline

- **July 31, 2026** (German CIT and Trade Tax return for FY2025)
- Rule as_of_date: 2024-01-01 | source: AO §149(2) (Abgabenordnung)

---

## 5. MERID-FR — French CIT, VAT Obligation, WHT (FY 1 January 2025 – 31 December 2025)

### 5.1 Applicable Rules

| Rule | Rate | as_of_date | source |
|------|------|-----------|--------|
| CIT | 25% flat | 2024-01-01 | CGI Art.219 |
| VAT threshold (services) | EUR 85,800 | 2024-01-01 | CGI Art.293B |
| WHT on non-EU payments | 12.8% | 2024-01-01 | CGI Art.119bis |
| EU Parent-Subsidiary Directive (dividend WHT) | 0% if ≥25% held ≥2 years | 2011-11-30 | EU Directive 2011/96/EU |

### 5.2 Income Classification

| Transaction | Amount (HKD) | Treatment |
|------------|-------------|-----------|
| T009 third-party revenue | 2,800,000 | French-source revenue — included |
| T002 royalty received from MERID-DE | 600,000 | French-source royalty income — included |
| PE-attributed income from MERID-DE (T003) | 1,023,750 | PE-attributed; taxable in France as PE state |
| T004 dividend paid to MERID-DE | 900,000 | Outbound distribution — NOT income for FR |

### 5.3 Deductible Expenses

```
T007 management fee paid to MERID-HK:   HKD   300,000
  (deductible if arm's length — assumed arm's length; needs_review: true — see ISSUE-003)
```

### 5.4 CIT Base Computation

```
T009 third-party revenue:               HKD 2,800,000
T002 royalty income received:           HKD   600,000
PE-attributed income:                   HKD 1,023,750
Less: T007 management fee paid:        (HKD   300,000)
                                        ─────────────
FR CIT base:                            HKD 4,123,750

Loss carryforward:                      HKD         0  (no prior losses for MERID-FR)

Taxable base:                           HKD 4,123,750
```

### 5.5 CIT Computation

```
Taxable base:                           HKD 4,123,750
CIT rate:                               25%

FR CIT:
  4,123,750 × 0.25:                     HKD 1,030,937.50
  Rounded to nearest HKD:               HKD 1,030,938
```

**MERID-FR CIT: HKD 1,030,938**

Of which, CIT attributable to PE-attributed income:
```
  PE-attributed income:                 HKD 1,023,750
  FR CIT on PE portion:
    1,023,750 × 25%:                    HKD   255,937.50
    Rounded:                            HKD   255,938
```

**FR CIT on PE portion: HKD 255,938** (used in treaty credit computation — Section 6)

### 5.6 VAT Filing Obligation

Rule as_of_date: 2024-01-01 | source: CGI Art.293B

```
T009 revenue (EUR equivalent):
  2,800,000 ÷ 8.50:                     EUR   329,412
FR VAT threshold:                        EUR    85,800

Comparison:  329,412 > 85,800  →  VAT FILING OBLIGATION TRIGGERED

Filing frequency:                        Quarterly VAT returns
VAT arithmetic:                          Out of scope for v1 — obligation flag only
```

**VAT obligation: TRIGGERED. Quarterly returns required.**

### 5.7 WHT on Outbound Payments from MERID-FR

#### T007 — Management Fee to MERID-HK (HKD 300,000)

Rule as_of_date: 2024-01-01 | source: CGI Art.119bis

```
Gross management fee:                   HKD   300,000

Applicable rate:  12.8% (non-EU recipient; no HK-FR DTA in effect for this scenario)

WHT:  300,000 × 0.128:                  HKD    38,400
```

**T007 WHT payable: HKD 38,400**

#### T004 — Dividend to MERID-DE (HKD 900,000)

Rule as_of_date: 2011-11-30 | source: EU Directive 2011/96/EU (Parent-Subsidiary Directive)

```
Gross dividend:                         HKD   900,000

EU PSD condition check:
  Parent entity (MERID-DE) in EU?       YES (Germany)
  Holding percentage?                   100% (MERID-DE holds 100% of MERID-FR)
  Threshold met (≥25%)?                 YES
  Holding period (≥2 years)?            YES (since 2021-03-15; >4 years by 2025-12-31)

EU PSD rate:                            0%
WHT:                                    HKD         0
```

**T004 WHT payable: HKD 0 (EU Parent-Subsidiary Directive exemption applies)**

### 5.8 Filing Deadline

- **May 31, 2026** (French CIT return for FY2025)
- Rule as_of_date: 2024-01-01 | source: CGI Art.223 (filing deadlines)

---

## 9. MERID-US — Federal CIT and WHT (FY 1 January 2025 – 31 December 2025)

### 9.1 Applicable Rules

| Rule | Rate | as_of_date | source |
|------|------|-----------|--------|
| Federal CIT | 21% | 2024-01-01 | IRC §11 (TCJA 2017) |
| WHT on dividends (domestic) | 30% | 2024-01-01 | IRC §881 (non-treaty recipient) |

**Note:** There is no Hong Kong–United States tax treaty. The domestic 30% withholding rate applies
in full to T011. FDII (§250) and GILTI (§951A) regime computations are out of scope for v1 — these
require qualified business asset investment (QBAI) data not captured in the golden scenario.
A professional reviewer must assess FDII/GILTI before filing.

### 9.2 Income Classification

| Transaction | Amount (HKD) | Treatment |
|------------|-------------|-----------|
| T010 third-party US revenue | 3,890,000 | US-source revenue — taxable |
| T011 dividend to MERID-HK | 389,000 | Outbound distribution — not income |

### 9.3 CIT Computation

```
Taxable base (T010):                    HKD 3,890,000
Federal CIT rate:                       21%

CIT:
  3,890,000 × 0.21:                     HKD   816,900
  (exact, no rounding required)
```

**MERID-US Federal CIT: HKD 816,900**

### 9.4 WHT on Outbound Payments from MERID-US

#### T011 — Dividend to MERID-HK (HKD 389,000)

Rule as_of_date: 2024-01-01 | source: IRC §881

```
Gross dividend:                         HKD   389,000

Domestic US WHT rate:                   30%  (no HK-US DTA)
WHT:  389,000 × 0.30:                  HKD   116,700
Treaty relief:                          HKD         0  (no applicable treaty)
```

**T011 WHT payable: HKD 116,700 (full domestic rate; no treaty)**

MERID-HK receives T011: territorial exclusion applies (foreign-source dividend, HK IRO s.14).

### 9.5 Filing Deadline

- **April 15, 2026** (US Form 1120 due 15th day of 4th month after year-end)
- Rule as_of_date: 2024-01-01 | source: IRC §6072(b)

---

## 6. PE Triangle Conflict — Detection, Attribution, and Treaty Resolution

### 6.1 Conflict Identification

**Trigger transaction:** T003
**Trigger condition:** 185 cumulative days in France > 183-day service PE threshold
**Rule triggered:** DE-FR DTA Art.5 (OECD 2017 service PE provision)
**Rule as_of_date:** 2017-01-01 | source: DE-FR DTA Art.5(3)(b)

**Entities involved:**
- MERID-DE (residence state: Germany — worldwide CIT basis)
- MERID-FR (PE state: France — taxes PE-attributed profits)

**Nature of conflict:** Same income base (MERID-DE PE-attributed profits, HKD 1,023,750) is:
1. Subject to French CIT as PE income (France is the PE state)
2. Subject to German CIT on worldwide basis (Germany is the residence state)

### 6.2 Attribution

```
PE-attributed income (35% of MERID-DE net income):
  MERID-DE net income before PE deduction:  HKD 2,925,000
  Attribution percentage (DEC-007):         35%
  PE-attributed to France:                  HKD 1,023,750

Source of 35% percentage: DEC-007 — service delivery functional analysis (demo assumption)
```

### 6.3 Competing Claims (before treaty relief)

| State | Claim basis | Base (HKD) | Rate | Tax if it taxed (HKD) |
|-------|-------------|-----------|------|----------|
| France (PE state) | PE-attributed business profits | 1,023,750 | 25% | 255,938 |
| Germany (residence state) | Worldwide basis (pre-relief) | 1,023,750 | 15.825% | 162,008 |

Both states have a *prima facie* claim on the same HKD 1,023,750. This is the conflict the
engine must detect. Whether it produces actual double tax depends on the treaty's elimination
method (§6.4).

### 6.4 Treaty Resolution — DE-FR DTA Art.23 (Exemption Method)

Rule as_of_date: 2017-01-01 | source: DE-FR DTA Art.23 (Freistellungsmethode for PE business profits)

Under the DE-FR treaty, Germany (the residence state) eliminates double taxation on French
**permanent-establishment business profits** by the **exemption method** — it removes the
PE-attributed profits from the German tax base entirely (it does *not* tax them and then grant a
credit). This is exactly what Section 4.6 does: the HKD 1,023,750 was deducted from the German
base before computing German CIT.

```
PE-attributed income (taxed in France only):   HKD 1,023,750
  France (PE state) taxes it:  1,023,750 × 25%  = HKD 255,938
  Germany exempts it:          taxed in DE       = HKD       0
                                                   ─────────────
Residual double taxation:                          HKD       0
```

**Resolution: exemption. The income is taxed once, in France (HKD 255,938). Germany exempts it;
there is no residual double tax and no credit is taken.**

Informational only — credit-method comparison (NOT applied under this treaty): had the treaty
used the credit method, Germany would have taxed the slice at 15.825% (HKD 162,008) and granted a
credit for French tax capped at that German amount, leaving HKD 93,930 of French tax
unrelieved. The DE-FR treaty uses exemption for PE profits, so this figure is illustrative only.

### 6.5 Conflict flag output

```json
{
  "conflict_id": "PE-TRIANGLE-2025",
  "conflict_type": "service_pe_double_tax",
  "trigger_flow_ids": ["PRES-DE-FR-2025"],
  "entities": ["MERID-DE", "MERID-FR"],
  "jurisdictions": ["DE", "FR"],
  "attributed_base_hkd": 1023750,
  "residence_jurisdiction": "DE",
  "pe_jurisdiction": "FR",
  "pe_tax_hkd": 255938,
  "residence_tax_before_relief_hkd": 162008,
  "relief_mechanism": "exemption",
  "relieved_amount_hkd": 162008,
  "residual_double_tax_hkd": 0,
  "treaty_rule_id": "DEFR-DTA-ELIMINATION",
  "treaty_as_of_date": "2017-01-01",
  "treaty_source_citation": "DE-FR DTA Art.23 (Freistellungsmethode)",
  "credit_method_note": "Credit method (not applied) would cap relief at HKD 162,008, leaving HKD 93,930 unrelieved."
}
```

---

## 7. Summary Table

### 7.1 Tax Obligations

| Entity | Obligation | Taxable Base (HKD) | Rate | Amount (HKD) |
|--------|-----------|---------------------|------|--------------|
| MERID-HK | Profits Tax | 2,700,000 | 16.5% | **445,500** |
| MERID-DE | CIT (incl. soli surcharge; post loss offset) | 301,250 | 15.825% | **47,673** |
| MERID-DE | Trade Tax | 301,250 | 14% | **42,175** |
| MERID-FR | CIT | 4,123,750 | 25% | **1,030,938** |
| MERID-US | Federal CIT | 3,890,000 | 21% | **816,900** |

### 7.2 WHT Obligations

| Payer | Payee | Transaction | Gross (HKD) | WHT Rate | WHT (HKD) | Treaty/Directive |
|-------|-------|------------|------------|---------|----------|-----------------|
| MERID-DE | MERID-HK | T005 dividend | 1,500,000 | 5% (treaty) | **75,000** | HK-DE DTA Art.10 |
| MERID-DE | MERID-HK | T006 interest | 320,000 | 0% (treaty) | **0** | HK-DE DTA Art.11 |
| MERID-FR | MERID-HK | T007 management fee | 300,000 | 12.8% | **38,400** | No DTA (non-EU) |
| MERID-FR | MERID-DE | T004 dividend | 900,000 | 0% (EU PSD) | **0** | EU Directive 2011/96/EU |
| MERID-US | MERID-HK | T011 dividend | 389,000 | 30% | **116,700** | No HK-US DTA |

### 7.3 Filing Obligations

| Entity | Obligation | Deadline |
|--------|-----------|---------|
| MERID-HK | Profits Tax return | April 30, 2026 |
| MERID-DE | CIT + Trade Tax return | July 31, 2026 |
| MERID-FR | CIT return | May 31, 2026 |
| MERID-FR | VAT filing (quarterly) | TRIGGERED — quarterly returns |
| MERID-US | Federal CIT (Form 1120) | April 15, 2026 |

### 7.4 Threshold Checks

| Check | Entity | Result |
|-------|--------|--------|
| PE service days (183-day threshold) | MERID-DE → France | **BREACHED** (185 days) |
| Zinsschranke (30% EBITDA cap) | MERID-DE T006 | **NOT BREACHED** (320,000 < 973,500) |
| FR VAT threshold (EUR 85,800) | MERID-FR | **EXCEEDED** (EUR 329,412) |
| Mindestbesteuerung (€1M cap) | MERID-DE | **BELOW THRESHOLD** — full loss offset |

### 7.5 PE Triangle — Key Figures (exemption method)

| Item | Value (HKD) |
|------|------------|
| PE-attributed income | 1,023,750 |
| FR CIT on PE portion (taxed once, in France) | 255,938 |
| German tax on PE income (exempted) | 0 |
| Residual double taxation | 0 |
| Relief mechanism | Exemption (DE-FR DTA Art.23) |
| Informational: credit-method cap (NOT applied) | 162,008 |

---

## 8. Simplifications and Deferred Items

The following items were not fully modeled in v1 and are tracked in `project-harness/ISSUES.md`.

| Issue | Item | What's deferred |
|-------|------|----------------|
| ISSUE-001 | HK royalty source rule (T001) | IRO s.15(1)(b) analysis; royalty included in HK taxable income as conservative treatment pending sourcing determination |
| ISSUE-002 | HK interest income (T006) | Excluded from HK taxable income on the assumption MERID-HK is not a money-lending business; full s.15(1)(f) analysis deferred |
| ISSUE-003 | T007 management fee arm's-length | Transfer pricing analysis required to confirm 5% arm's-length rate; treated as deductible for FR CIT |
| ISSUE-004 | FR VAT arithmetic | VAT filing obligation flag is computed; net VAT payable, input VAT recovery, and quarterly return amounts are out of scope for v1 |
| ISSUE-005 | PE attribution percentage | 35% is a stated assumption (DEC-007); arm's-length attribution requires functional and factual analysis beyond demo scope |

---

*End of EXPECTED.md — hand-computed ground truth for Meridian Group golden scenario.*
*Any engine output that diverges from the values in Section 7 is a bug in the engine.*
