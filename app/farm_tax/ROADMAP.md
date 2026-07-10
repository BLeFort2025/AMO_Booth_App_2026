# Farm Tax Calculator — Development Roadmap

> **Location:** `app/farm_tax/ROADMAP.md`
> This file lives inside the `farm_tax` module so it is always discovered
> when auditing files related to the Farm Tax Calculator (Page 11).

---

## Priority 1: Local Agricultural Economic Data in Reports

### Goal
Enrich the auto-generated Word reports and PowerPoint decks with **municipality-specific agricultural economic statistics**, so that OFA field staff can walk into a council meeting with a complete fiscal + economic picture.

### Data to Integrate
Pull from existing dashboard data sources (IO engine, Census, OMAFRA) for each municipality:

- **Farm cash receipts** — total and top commodities (from Census of Agriculture / OMAFRA county profiles)
- **Number of farms and farm operators** — Census 2021 data
- **Agri-food sector GDP contribution** — from the IO multiplier engine (direct + indirect + induced)
- **Employment multiplier** — jobs supported per $1M in farm cash receipts
- **Upstream/downstream supply chain activity** — input suppliers, processors, equipment dealers
- **Tax ROI framing** — farmland pays $X in taxes, supports $Y in economic activity (multiplier ratio)

### Implementation Notes
- The data sources already exist in the dashboard (`census_indicators.csv`, IO engine outputs)
- Add a new section to `generate_word_report()` in `farm_tax_report.py` after the revenue-neutral analysis
- Add 1–2 slides to `generate_pptx_report()` with key economic stats
- Consider a `load_local_ag_stats(sgc_code)` utility function that pulls and formats the relevant data

### Files to Modify
- `app/farm_tax/farm_tax_report.py` — add economic data sections to Word/PPTX generators
- `app/farm_tax/farm_tax_story.py` — optionally display economic context in the story UI
- May need a new utility: `app/farm_tax/local_ag_stats.py`

---

## Priority 2: Delegation FAQ Document

### Goal
Create a **downloadable FAQ document** (Word/PDF) that helps county federations prepare for common questions councillors might ask during a property tax delegation. This is a practical advocacy tool that pairs with the existing "Letter to Council" export.

### Placement
- Add a new download button **below the existing Letter to Council button** in the Export Report tab
- Label: "📋 Download Delegation FAQ & Talking Points"

### FAQ Content to Include

#### Q1: "Farmers only pay 25% of the residential tax rate — why should they pay even less?"
**Key rebuttal points:**
- The 0.25 ratio applies to the **tax rate**, not the total tax bill. Farm properties have large CVAs, so even at 25% of the rate, the absolute dollar amount is substantial.
- **Farms more than pay their own way.** Research shows that farm properties generate a net fiscal surplus for municipalities — they consume far less in municipal services (roads, water, sewer, transit, recreation) per dollar of taxes paid compared to residential properties.
- The classic **Cost of Community Services (COCS) studies** consistently show:
  - Residential properties: require $1.05–$1.16 in services for every $1.00 in taxes paid
  - Farm/forest properties: require only $0.33–$0.50 in services for every $1.00 in taxes paid
  - Commercial/industrial: $0.25–$0.45 per $1.00
- Farmland is assessed at **market value** (what it would sell for), NOT at its **productive value** (what income it generates). Speculative demand from non-farm buyers inflates CVA beyond what the land earns.
- The 0.25 ratio is a **provincial maximum**, not a subsidy — it partially corrects a structural over-assessment.
- Reference: OFA research, American Farmland Trust COCS methodology, Ben LePort's farm property tax analysis

#### Q2: "Why can't farmers just absorb a small tax increase?"
- Operating margins in agriculture are thin (typically 2–5% net margin)
- Property tax is a **fixed cost** — it must be paid regardless of crop prices, weather, or yields
- Unlike residential owners, farmers cannot pass tax increases to tenants
- A $500/year increase × 500 acres = $250,000 annual impact on a typical cash crop operation
- Use the dashboard's **per-hectare** and **per-$100K CVA** metrics to illustrate

#### Q3: "Other property classes pay higher ratios — isn't this already fair?"
- Commercial and industrial properties can **deduct** property tax as a business expense (reducing income tax)
- Farmers on the cash basis often cannot fully realize this deduction due to volatile income
- Commercial properties typically have higher revenue-per-square-foot than farmland
- The ratio system was designed to reflect **ability to pay**, not just assessment value

#### Q4: "What would happen if we lowered the farm ratio below 0.25?"
- Use the dashboard's **Revenue-Neutral Calculator** to show the exact dollar shift
- Emphasize the **zero-sum** nature: the total tax levy doesn't change, just the distribution
- Show the **per-household impact** — typically pennies per household, but significant for farm operations

#### Q5: "Our municipality has a large farm tax base — doesn't lowering the ratio hurt our budget?"
- Revenue-neutral means the **total levy is unchanged** — the municipality collects the same amount
- Only the **distribution** across classes shifts
- Upper-tier municipalities set the ratio; lower-tier municipalities follow
- Historical trend: most municipalities have been at 0.25 (the max) for years

### Data-Driven Customization
- Auto-populate with the selected municipality's actual numbers from the FIR data
- Include the revenue-neutral calculation results showing the exact dollar impact
- Pull local agricultural economic stats (see Priority 1) to strengthen the "farms pay their way" argument

### Implementation Notes
- Create a new function `generate_delegation_faq()` in `farm_tax_report.py`
- Use `python-docx` (already a dependency) to generate a polished Word document
- Template with OFA branding (header, footer, colours)
- Include a "Prepared for [Municipality Name]" header with the date

### Files to Modify
- `app/farm_tax/farm_tax_report.py` — add `generate_delegation_faq()` function
- `app/farm_tax/farm_tax_story.py` — add download button in Export Report tab

---

## ~~Priority 3: Indexed (Base-100) Chart View for CVA & Tax Trends~~ ✅ COMPLETED

> **Completed 2026-04-02.** See Completed Items below for full details.

### Files Modified
- `app/farm_tax/farm_tax_story.py` — added `_compute_indexed_series()` helper, toggles in 3 chart tabs
- `app/farm_tax/farm_tax_report.py` — added indexed chart builders, Word indexed sections, PPTX Slide 6 (13 slides total)

---

## Completed Items

### ✅ Indexed (Base-100) Chart Views (2026-04-02)
- **Scope:** Added indexed toggle to all 3 trend chart tabs + Word/PPTX reports
- **Base Year:** Fixed at 2010 with automatic fallback to first valid year
- **Features:** `_compute_indexed_series()` helper, `st.radio()` toggles, hover tooltips (index + raw), narrative callouts, works in provincial view
- **Reports:** `_build_indexed_cva_chart()`, `_build_indexed_tax_chart()` in Word; new Slide 6 in PPTX (13 slides)
- **Tests:** Zero-sum verified, Word + PPTX generation tested, all 13 slides confirmed

### ✅ CVA Growth N/A Fix (2026-04-01)
- **Problem:** 92/444 municipalities showed "N/A" for CVA growth due to 2010 MMAH template producing CVA=0
- **Fix:** Per-class first-valid-year logic in `_render_assessment_trends()`
- **Verification:** 55/55 spot-check fields matched raw Excel at 100%; 389/389 zero-sum verified
- **Commit:** `1ecd4db` — pushed to Streamlit Cloud

---

## Related Files
For a complete inventory, see the Farm Tax Tool audit:
- Main page: `app/pages/11_🌾_Farm_Tax_Calculator.py`
- Module: `app/farm_tax/` (this directory)
- ETL: `scripts/process_fir.py`
- Config: `config/fir_indicators.yaml`
- Data: `data/derived/fir_indicators.csv`
- Tests: `tests/test_farm_tax_story.py`, `tests/test_process_fir.py`
- Accuracy scan: `scripts/verify_farm_tax_accuracy.py`
- Extraction verification: `scripts/verify_fir_extraction.py`
