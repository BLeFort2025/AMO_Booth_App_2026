# Revenue-Neutral Farm Tax Ratio Calculator & Word Report Generator
# Used by the Farmland Taxation tab in the Rural Community Data page.
#
# RED-TEAM AUDIT FIX (2025-02-23):
#   - Replaced manual W_other sum with True W reverse-engineered from res_rate
#   - Switched to Model-vs-Model baseline (NOT observed-vs-model)
#   - Added "All Other Classes" impact row for perfect $0 zero-sum
#   - Added per-household impact metric

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Revenue-Neutral Math  (True W / Model-vs-Model)
# ---------------------------------------------------------------------------
# Ontario's property tax system: each class rate = class_ratio × res_rate
# Revenue-neutral means: total_muni_taxes is CONSTANT.
#
# KEY INSIGHT (from expert audit):
#   The residential class has ratio = 1.0 and NO capping/phase-in noise.
#   Therefore:  actual_res_rate = residential_muni_taxes / residential_cva
#   And:        true_total_W = total_muni_taxes / actual_res_rate
#
#   This elegantly captures ALL classes (pipeline, multi-res, managed
#   forest, landfill, PILs) without needing their individual ratios.
#
# Impact comparison uses MODEL-predicted taxes for both baseline and
# scenario, guaranteeing sum(savings) == sum(increases) to the penny.
# ---------------------------------------------------------------------------

MAX_FARM_RATIO = 0.25  # Provincial ceiling


@dataclass
class RatioResult:
    """Result of a revenue-neutral farm tax ratio calculation."""
    target_year: int
    target_burden: float       # e.g. 0.15 means 15%
    current_burden: float      # current year burden
    required_ratio: float      # uncapped
    effective_ratio: float     # capped at 0.25
    is_capped: bool
    total_muni_taxes: float

    # Residential base rates
    current_res_rate: float
    new_res_rate: float

    # True Weighted Assessment
    true_total_W: float
    w_other: float

    # Per-class impact  (model-current vs model-new)
    farm_savings_total: float
    farm_savings_per_100k: float
    res_increase_total: float
    res_increase_per_100k: float
    com_increase_total: float
    com_increase_per_100k: float
    ind_increase_total: float
    ind_increase_per_100k: float
    other_increase_total: float     # multi-res + pipeline + managed forest + landfill

    # Model-predicted taxes (current and new)
    model_current_farm_taxes: float
    model_new_farm_taxes: float
    model_current_res_taxes: float
    model_new_res_taxes: float
    model_current_com_taxes: float
    model_new_com_taxes: float
    model_current_ind_taxes: float
    model_new_ind_taxes: float
    model_current_other_taxes: float
    model_new_other_taxes: float

    # Per-household impact (Fix 4)
    total_households: float
    res_increase_per_household: float       # $/year
    res_increase_per_household_month: float  # $/month

    # Current farm ratio (for report text)
    current_farm_ratio: float

    # Zero-sum verification
    zero_sum_check: float  # should be 0.00


def _get_or_zero(val):
    """Coalesce None/NaN to 0."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0.0
    return float(val)


def calculate_revenue_neutral_ratio(
    target_burden: float,
    farm_cva: float,
    res_cva: float,
    com_cva: float,
    ind_cva: float,
    ft_ratio: float,
    ct_ratio: float,
    it_ratio: float,
    total_muni_taxes: float,
    current_farm_taxes: float,    # observed — used only for burden calc
    current_res_taxes: float,     # observed — used for res_rate derivation
    current_com_taxes: float,     # observed — NOT used in impact
    current_ind_taxes: float,     # observed — NOT used in impact
    current_burden: float,
    total_households: float = 0,
) -> Optional[RatioResult]:
    """Calculate the revenue-neutral farm tax ratio to achieve a target burden.

    Uses the expert-recommended True W approach:
      1. Derive actual_res_rate from observed residential taxes / CVA
      2. Derive true_total_W = total_muni_taxes / actual_res_rate
      3. All impacts are MODEL vs MODEL (not observed vs model)

    Returns None if inputs are insufficient.
    """
    farm_cva = _get_or_zero(farm_cva)
    res_cva = _get_or_zero(res_cva)
    com_cva = _get_or_zero(com_cva)
    ind_cva = _get_or_zero(ind_cva)
    ft_ratio = _get_or_zero(ft_ratio)
    ct_ratio = _get_or_zero(ct_ratio)
    it_ratio = _get_or_zero(it_ratio)
    total_muni_taxes = _get_or_zero(total_muni_taxes)
    current_res_taxes = _get_or_zero(current_res_taxes)
    total_households = _get_or_zero(total_households)

    if farm_cva <= 0 or res_cva <= 0 or total_muni_taxes <= 0:
        return None
    if target_burden <= 0 or target_burden >= 1:
        return None
    if current_res_taxes <= 0:
        return None  # can't derive res_rate

    # ── Step 1: Derive actual residential base rate ──
    # Residential ratio = 1.0 and has no capping noise → perfect proxy
    actual_res_rate = current_res_taxes / res_cva

    # ── Step 2: Derive True Total Weighted Assessment ──
    # Captures ALL classes (pipeline, multi-res, managed forest, PILs, etc.)
    true_total_W = total_muni_taxes / actual_res_rate

    # ── Step 3: W_other = everything EXCEPT farmland ──
    current_farm_W = farm_cva * ft_ratio
    w_other = true_total_W - current_farm_W

    # ── Step 4: Required farm ratio for target burden ──
    required_ratio = target_burden * w_other / (farm_cva * (1 - target_burden))
    effective_ratio = min(required_ratio, MAX_FARM_RATIO)
    is_capped = required_ratio > MAX_FARM_RATIO

    # ── Step 5: New residential rate ──
    new_total_W = w_other + effective_ratio * farm_cva
    new_res_rate = total_muni_taxes / new_total_W

    # ── Step 6: Model-vs-Model impact (guarantees zero-sum) ──
    # Current (model-predicted)
    model_current_farm_taxes = farm_cva * ft_ratio * actual_res_rate
    model_current_res_taxes = res_cva * 1.0 * actual_res_rate
    model_current_com_taxes = com_cva * ct_ratio * actual_res_rate
    model_current_ind_taxes = ind_cva * it_ratio * actual_res_rate
    model_current_other_taxes = (
        total_muni_taxes
        - model_current_farm_taxes
        - model_current_res_taxes
        - model_current_com_taxes
        - model_current_ind_taxes
    )

    # New (model-predicted with adjusted farm ratio)
    model_new_farm_taxes = farm_cva * effective_ratio * new_res_rate
    model_new_res_taxes = res_cva * 1.0 * new_res_rate
    model_new_com_taxes = com_cva * ct_ratio * new_res_rate
    model_new_ind_taxes = ind_cva * it_ratio * new_res_rate
    model_new_other_taxes = (
        total_muni_taxes
        - model_new_farm_taxes
        - model_new_res_taxes
        - model_new_com_taxes
        - model_new_ind_taxes
    )

    # ── Step 7: Compute deltas ──
    farm_savings_total = model_current_farm_taxes - model_new_farm_taxes
    res_increase_total = model_new_res_taxes - model_current_res_taxes
    com_increase_total = model_new_com_taxes - model_current_com_taxes
    ind_increase_total = model_new_ind_taxes - model_current_ind_taxes
    other_increase_total = model_new_other_taxes - model_current_other_taxes

    # Zero-sum verification (should be 0.00)
    zero_sum = (
        -farm_savings_total
        + res_increase_total
        + com_increase_total
        + ind_increase_total
        + other_increase_total
    )

    # Per $100k CVA
    farm_savings_per_100k = (farm_savings_total / farm_cva) * 100_000 if farm_cva > 0 else 0
    res_increase_per_100k = (res_increase_total / res_cva) * 100_000 if res_cva > 0 else 0
    com_increase_per_100k = (com_increase_total / com_cva) * 100_000 if com_cva > 0 else 0
    ind_increase_per_100k = (ind_increase_total / ind_cva) * 100_000 if ind_cva > 0 else 0

    # Per-household impact (Fix 4)
    if total_households > 0:
        res_increase_per_household = res_increase_total / total_households
        res_increase_per_household_month = res_increase_per_household / 12
    else:
        res_increase_per_household = 0
        res_increase_per_household_month = 0

    return RatioResult(
        target_year=0,  # set by caller
        target_burden=target_burden,
        current_burden=current_burden,
        required_ratio=required_ratio,
        effective_ratio=effective_ratio,
        is_capped=is_capped,
        total_muni_taxes=total_muni_taxes,
        current_res_rate=actual_res_rate,
        new_res_rate=new_res_rate,
        true_total_W=true_total_W,
        w_other=w_other,
        farm_savings_total=farm_savings_total,
        farm_savings_per_100k=farm_savings_per_100k,
        res_increase_total=res_increase_total,
        res_increase_per_100k=res_increase_per_100k,
        com_increase_total=com_increase_total,
        com_increase_per_100k=com_increase_per_100k,
        ind_increase_total=ind_increase_total,
        ind_increase_per_100k=ind_increase_per_100k,
        other_increase_total=other_increase_total,
        model_current_farm_taxes=model_current_farm_taxes,
        model_new_farm_taxes=model_new_farm_taxes,
        model_current_res_taxes=model_current_res_taxes,
        model_new_res_taxes=model_new_res_taxes,
        model_current_com_taxes=model_current_com_taxes,
        model_new_com_taxes=model_new_com_taxes,
        model_current_ind_taxes=model_current_ind_taxes,
        model_new_ind_taxes=model_new_ind_taxes,
        model_current_other_taxes=model_current_other_taxes,
        model_new_other_taxes=model_new_other_taxes,
        total_households=total_households,
        res_increase_per_household=res_increase_per_household,
        res_increase_per_household_month=res_increase_per_household_month,
        current_farm_ratio=ft_ratio,
        zero_sum_check=zero_sum,
    )


def calculate_ratio_direct(
    chosen_ratio: float,
    farm_cva: float,
    res_cva: float,
    com_cva: float,
    ind_cva: float,
    ft_ratio: float,
    ct_ratio: float,
    it_ratio: float,
    total_muni_taxes: float,
    current_res_taxes: float,
    current_burden: float,
    total_households: float = 0,
) -> Optional[RatioResult]:
    """Calculate the revenue-neutral impact of a directly chosen farm tax ratio.

    Same True W / Model-vs-Model math as calculate_revenue_neutral_ratio,
    but the user specifies the ratio directly instead of deriving it from
    a target year's burden share.

    Returns None if inputs are insufficient.
    """
    farm_cva = _get_or_zero(farm_cva)
    res_cva = _get_or_zero(res_cva)
    com_cva = _get_or_zero(com_cva)
    ind_cva = _get_or_zero(ind_cva)
    ft_ratio = _get_or_zero(ft_ratio)
    ct_ratio = _get_or_zero(ct_ratio)
    it_ratio = _get_or_zero(it_ratio)
    total_muni_taxes = _get_or_zero(total_muni_taxes)
    current_res_taxes = _get_or_zero(current_res_taxes)
    total_households = _get_or_zero(total_households)

    if farm_cva <= 0 or res_cva <= 0 or total_muni_taxes <= 0:
        return None
    if chosen_ratio < 0 or chosen_ratio > MAX_FARM_RATIO:
        return None
    if current_res_taxes <= 0:
        return None

    # ── Step 1: Derive actual residential base rate ──
    actual_res_rate = current_res_taxes / res_cva

    # ── Step 2: True Total W ──
    true_total_W = total_muni_taxes / actual_res_rate

    # ── Step 3: W_other = everything EXCEPT farmland ──
    current_farm_W = farm_cva * ft_ratio
    w_other = true_total_W - current_farm_W

    # ── Step 4: Use the chosen ratio directly (no derivation) ──
    effective_ratio = chosen_ratio
    is_capped = False  # user chose it directly

    # ── Step 5: New residential rate ──
    new_total_W = w_other + effective_ratio * farm_cva
    new_res_rate = total_muni_taxes / new_total_W

    # ── Step 6: Model-vs-Model impact ──
    model_current_farm_taxes = farm_cva * ft_ratio * actual_res_rate
    model_current_res_taxes = res_cva * 1.0 * actual_res_rate
    model_current_com_taxes = com_cva * ct_ratio * actual_res_rate
    model_current_ind_taxes = ind_cva * it_ratio * actual_res_rate
    model_current_other_taxes = (
        total_muni_taxes
        - model_current_farm_taxes
        - model_current_res_taxes
        - model_current_com_taxes
        - model_current_ind_taxes
    )

    model_new_farm_taxes = farm_cva * effective_ratio * new_res_rate
    model_new_res_taxes = res_cva * 1.0 * new_res_rate
    model_new_com_taxes = com_cva * ct_ratio * new_res_rate
    model_new_ind_taxes = ind_cva * it_ratio * new_res_rate
    model_new_other_taxes = (
        total_muni_taxes
        - model_new_farm_taxes
        - model_new_res_taxes
        - model_new_com_taxes
        - model_new_ind_taxes
    )

    # ── Step 7: Compute deltas ──
    farm_savings_total = model_current_farm_taxes - model_new_farm_taxes
    res_increase_total = model_new_res_taxes - model_current_res_taxes
    com_increase_total = model_new_com_taxes - model_current_com_taxes
    ind_increase_total = model_new_ind_taxes - model_current_ind_taxes
    other_increase_total = model_new_other_taxes - model_current_other_taxes

    zero_sum = (
        -farm_savings_total
        + res_increase_total
        + com_increase_total
        + ind_increase_total
        + other_increase_total
    )

    # Per $100k CVA
    farm_savings_per_100k = (farm_savings_total / farm_cva) * 100_000 if farm_cva > 0 else 0
    res_increase_per_100k = (res_increase_total / res_cva) * 100_000 if res_cva > 0 else 0
    com_increase_per_100k = (com_increase_total / com_cva) * 100_000 if com_cva > 0 else 0
    ind_increase_per_100k = (ind_increase_total / ind_cva) * 100_000 if ind_cva > 0 else 0

    # Per-household impact
    if total_households > 0:
        res_increase_per_household = res_increase_total / total_households
        res_increase_per_household_month = res_increase_per_household / 12
    else:
        res_increase_per_household = 0
        res_increase_per_household_month = 0

    # Derive the burden that this ratio produces
    new_burden = model_new_farm_taxes / total_muni_taxes if total_muni_taxes > 0 else 0

    return RatioResult(
        target_year=0,
        target_burden=new_burden,
        current_burden=current_burden,
        required_ratio=chosen_ratio,
        effective_ratio=effective_ratio,
        is_capped=is_capped,
        total_muni_taxes=total_muni_taxes,
        current_res_rate=actual_res_rate,
        new_res_rate=new_res_rate,
        true_total_W=true_total_W,
        w_other=w_other,
        farm_savings_total=farm_savings_total,
        farm_savings_per_100k=farm_savings_per_100k,
        res_increase_total=res_increase_total,
        res_increase_per_100k=res_increase_per_100k,
        com_increase_total=com_increase_total,
        com_increase_per_100k=com_increase_per_100k,
        ind_increase_total=ind_increase_total,
        ind_increase_per_100k=ind_increase_per_100k,
        other_increase_total=other_increase_total,
        model_current_farm_taxes=model_current_farm_taxes,
        model_new_farm_taxes=model_new_farm_taxes,
        model_current_res_taxes=model_current_res_taxes,
        model_new_res_taxes=model_new_res_taxes,
        model_current_com_taxes=model_current_com_taxes,
        model_new_com_taxes=model_new_com_taxes,
        model_current_ind_taxes=model_current_ind_taxes,
        model_new_ind_taxes=model_new_ind_taxes,
        model_current_other_taxes=model_current_other_taxes,
        model_new_other_taxes=model_new_other_taxes,
        total_households=total_households,
        res_increase_per_household=res_increase_per_household,
        res_increase_per_household_month=res_increase_per_household_month,
        current_farm_ratio=ft_ratio,
        zero_sum_check=zero_sum,
    )


# ---------------------------------------------------------------------------
# Word Report Generation
# ---------------------------------------------------------------------------

def generate_word_report(
    muni_name: str,
    year_range: str,
    current_year: int,
    target_year: int,
    burden_by_year: dict,     # {year: {'farm': pct, 'res': pct, 'com': pct, 'ind': pct}}
    calc: RatioResult,
    cva_growth: dict,         # {'farm': pct, 'res': pct, 'com': pct, 'ind': pct}
    is_two_tier: bool = False,
    is_upper_tier: bool = False,
    chart_images: dict = None,  # {'assessment': bytes, 'burden': bytes}
    tax_trends_by_year: dict = None,  # {year: {'farm': $, 'res': $, 'com': $, 'ind': $}}
    logo_bytes: bytes = None,
) -> io.BytesIO:
    """Generate a 1-2 page Farm Tax Report as a Word document.

    Returns a BytesIO buffer containing the .docx file.
    """
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT

    doc = Document()

    # Adjust default style
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(10)
    style.paragraph_format.space_after = Pt(4)

    # ── Logo (if provided) ──
    if logo_bytes:
        logo_para = doc.add_paragraph()
        logo_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        logo_para.add_run().add_picture(io.BytesIO(logo_bytes), width=Inches(1.5))

    # ── Title ──
    title = doc.add_heading(f"Farm Tax Burden Report — {muni_name}", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        run.font.color.rgb = RGBColor(0x2E, 0x7D, 0x32)  # OFA green

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run(f"FIR Data: {year_range}  |  Generated from OFA's farm and rural database")
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x75, 0x75, 0x75)

    # ── Jurisdictional note (Fix 5) ──
    if is_two_tier:
        note = doc.add_paragraph()
        run = note.add_run(
            "Note: Tax ratios are set at the Upper-Tier (County/Region) level. "
            "Changing the farm tax ratio requires a County/Regional Council vote."
        )
        run.font.italic = True
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0xB7, 0x1C, 0x1C)

    # ── V45: Upper-tier levy disclaimer ──
    if is_upper_tier:
        note = doc.add_paragraph()
        run = note.add_run(
            "Note: This report analyzes the Upper-Tier (County/Regional) property tax "
            "levy only. It does not include local lower-tier township taxes or the "
            "provincial education levy."
        )
        run.font.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0x1B, 0x5E, 0x20)  # OFA dark green

    # ── Assessment Growth ──
    doc.add_heading("Assessment Trends (CVA)", level=2)
    doc.add_paragraph(
        f"Over the reporting period, farmland Current Value Assessment (CVA) "
        f"grew by {cva_growth.get('Farmland', 0):+.1f}%, compared to residential at "
        f"{cva_growth.get('Residential', 0):+.1f}%, commercial at {cva_growth.get('Commercial', 0):+.1f}%, "
        f"and industrial at {cva_growth.get('Industrial', 0):+.1f}%."
    )
    doc.add_paragraph(
        "Note: The last province-wide reassessment was based on January 1, 2016 "
        "property values, phased in over four years (2017–2020). Since 2020, all "
        "assessments have been frozen. Post-2020 CVA changes reflect new "
        "construction, demolitions, and supplementary assessments only — not "
        "market-value reassessment."
    ).runs[0].font.italic = True

    if chart_images and chart_images.get("assessment"):
        doc.add_picture(io.BytesIO(chart_images["assessment"]), width=Inches(6))

    # ── Indexed CVA Growth Chart ──
    try:
        indexed_cva_img = _build_indexed_cva_chart(cva_growth, tax_trends_by_year, year_range)
        if indexed_cva_img:
            doc.add_heading("CVA Growth Rate Comparison (Indexed)", level=3)
            farm_g = cva_growth.get('Farmland', 0)
            res_g = cva_growth.get('Residential', 0)
            if farm_g and res_g and res_g > 0:
                doc.add_paragraph(
                    f"When normalized to a common starting point of 100, farmland CVA "
                    f"reached {100 + farm_g:.0f} while residential reached {100 + res_g:.0f} — "
                    f"farmland grew {farm_g / max(res_g, 0.1):.1f}\u00d7 faster in percentage terms. "
                    f"This indexed view eliminates the scale difference and isolates the "
                    f"rate of change that drives the tax burden shift."
                )
            doc.add_picture(indexed_cva_img, width=Inches(6))
    except Exception:
        pass  # Don't break the report if chart generation fails

    # ── Tax Payment Trends Table ──
    if tax_trends_by_year:
        doc.add_heading("Municipal Tax Payment Trends", level=2)
        trend_years = sorted(tax_trends_by_year.keys())
        if len(trend_years) >= 2:
            first_yr, last_yr = trend_years[0], trend_years[-1]
            first_farm = tax_trends_by_year[first_yr].get("farm", 0)
            last_farm = tax_trends_by_year[last_yr].get("farm", 0)
            if first_farm > 0:
                cum_pct = ((last_farm - first_farm) / first_farm) * 100
                # V27: Include residential comparison for advocacy context
                first_res = tax_trends_by_year[first_yr].get("res", 0)
                last_res = tax_trends_by_year[last_yr].get("res", 0)
                res_pct = ((last_res - first_res) / first_res) * 100 if first_res > 0 else 0
                narrative = (
                    f"Farmland municipal taxes grew by {cum_pct:+.1f}% over the "
                    f"reporting period ({first_yr}\u2013{last_yr}), from "
                    f"${first_farm:,.0f} to ${last_farm:,.0f}."
                )
                if first_res > 0:
                    narrative += (
                        f" For comparison, residential taxes grew by "
                        f"{res_pct:+.1f}% over the same period."
                    )
                doc.add_paragraph(narrative)
            else:
                doc.add_paragraph(
                    f"Farmland municipal taxes over the reporting period "
                    f"({first_yr}\u2013{last_yr})."
                )

        # Table: Year x Class
        # +1 for header, +len for data rows, +1 for cumulative row
        tt_table = doc.add_table(
            rows=1 + len(trend_years) + 1, cols=5, style='Light List Accent 1'
        )
        tt_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        tt_headers = ["Year", "Farmland", "Residential", "Commercial", "Industrial"]
        for i, h in enumerate(tt_headers):
            tt_table.rows[0].cells[i].text = h
        for row_idx, yr in enumerate(trend_years, 1):
            d = tax_trends_by_year[yr]
            tt_table.rows[row_idx].cells[0].text = str(yr)
            tt_table.rows[row_idx].cells[1].text = f"${d.get('farm', 0):,.0f}"
            tt_table.rows[row_idx].cells[2].text = f"${d.get('res', 0):,.0f}"
            tt_table.rows[row_idx].cells[3].text = f"${d.get('com', 0):,.0f}"
            tt_table.rows[row_idx].cells[4].text = f"${d.get('ind', 0):,.0f}"

        # Cumulative increase ($) row
        cum_row_idx = 1 + len(trend_years)
        first_d = tax_trends_by_year[trend_years[0]]
        last_d = tax_trends_by_year[trend_years[-1]]
        tt_table.rows[cum_row_idx].cells[0].text = f"Cumulative Change ({trend_years[0]}\u2013{trend_years[-1]})"
        for ci, key in enumerate(["farm", "res", "com", "ind"], 1):
            diff = last_d.get(key, 0) - first_d.get(key, 0)
            sign = "+" if diff >= 0 else ""
            tt_table.rows[cum_row_idx].cells[ci].text = f"{sign}${diff:,.0f}"
        # Bold the cumulative row
        for ci in range(5):
            for paragraph in tt_table.rows[cum_row_idx].cells[ci].paragraphs:
                for run in paragraph.runs:
                    run.bold = True

        doc.add_paragraph(
            "Municipal taxes = Lower-Tier (LT) + Upper-Tier (UT) taxes, "
            "excluding the provincial education levy."
        ).runs[0].font.italic = True

        # ── Annual & Cumulative % Increase Table ──
        doc.add_heading("Tax Increase (%) by Property Class", level=3)
        doc.add_paragraph(
            f"Annual year-over-year and cumulative percentage change in "
            f"municipal property taxes by class ({trend_years[0]}\u2013{trend_years[-1]})."
        )

        # Build the % table: header + one row per year (skip first year for YoY)
        pct_years = trend_years[1:]  # YoY starts from 2nd year
        # Rows: header + annual rows + cumulative row
        pct_table = doc.add_table(
            rows=1 + len(pct_years) + 1, cols=5, style='Light List Accent 1'
        )
        pct_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        pct_headers = ["Year", "Farmland", "Residential", "Commercial", "Industrial"]
        for i, h in enumerate(pct_headers):
            pct_table.rows[0].cells[i].text = h

        for row_idx, yr in enumerate(pct_years, 1):
            prev_yr = trend_years[trend_years.index(yr) - 1]
            prev_d = tax_trends_by_year[prev_yr]
            cur_d = tax_trends_by_year[yr]
            pct_table.rows[row_idx].cells[0].text = str(yr)
            for ci, key in enumerate(["farm", "res", "com", "ind"], 1):
                prev_val = prev_d.get(key, 0)
                cur_val = cur_d.get(key, 0)
                if prev_val > 0:
                    yoy_pct = ((cur_val - prev_val) / prev_val) * 100
                    pct_table.rows[row_idx].cells[ci].text = f"{yoy_pct:+.1f}%"
                else:
                    pct_table.rows[row_idx].cells[ci].text = "N/A"

        # Cumulative % row
        cum_pct_row = 1 + len(pct_years)
        pct_table.rows[cum_pct_row].cells[0].text = f"Cumulative ({trend_years[0]}\u2013{trend_years[-1]})"
        for ci, key in enumerate(["farm", "res", "com", "ind"], 1):
            first_val = first_d.get(key, 0)
            last_val = last_d.get(key, 0)
            if first_val > 0:
                cum_pct = ((last_val - first_val) / first_val) * 100
                pct_table.rows[cum_pct_row].cells[ci].text = f"{cum_pct:+.1f}%"
            else:
                pct_table.rows[cum_pct_row].cells[ci].text = "N/A"
        # Bold the cumulative row
        for ci in range(5):
            for paragraph in pct_table.rows[cum_pct_row].cells[ci].paragraphs:
                for run in paragraph.runs:
                    run.bold = True

        # ── Indexed Tax Payment Growth Chart ──
        try:
            indexed_tax_img = _build_indexed_tax_chart(tax_trends_by_year)
            if indexed_tax_img:
                doc.add_heading("Tax Payment Growth Rate Comparison (Indexed)", level=3)
                first_yr, last_yr = trend_years[0], trend_years[-1]
                first_d = tax_trends_by_year[first_yr]
                last_d = tax_trends_by_year[last_yr]
                farm_base = first_d.get('farm', 0)
                res_base = first_d.get('res', 0)
                if farm_base > 0 and res_base > 0:
                    farm_idx = (last_d.get('farm', 0) / farm_base) * 100
                    res_idx = (last_d.get('res', 0) / res_base) * 100
                    doc.add_paragraph(
                        f"Indexed to 100 in {first_yr}, farmland taxes reached {farm_idx:.0f} "
                        f"by {last_yr} while residential taxes reached {res_idx:.0f}. "
                        f"This confirms that farm property taxes have grown at a "
                        f"disproportionately faster rate."
                    )
                doc.add_picture(indexed_tax_img, width=Inches(6))
        except Exception:
            pass  # Don't break the report if chart generation fails

    # ── Tax Burden Shift Table ──
    doc.add_heading("Tax Burden Shift (% of Municipal Taxes)", level=2)
    years = sorted(burden_by_year.keys())
    table = doc.add_table(rows=1 + len(years), cols=5, style='Light List Accent 1')
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Year", "Farmland", "Residential", "Commercial", "Industrial"]
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h
    for row_idx, yr in enumerate(years, 1):
        d = burden_by_year[yr]
        table.rows[row_idx].cells[0].text = str(yr)
        table.rows[row_idx].cells[1].text = f"{d.get('farm', 0):.2%}"
        table.rows[row_idx].cells[2].text = f"{d.get('res', 0):.2%}"
        table.rows[row_idx].cells[3].text = f"{d.get('com', 0):.2%}"
        table.rows[row_idx].cells[4].text = f"{d.get('ind', 0):.2%}"

    if chart_images and chart_images.get("burden"):
        doc.add_picture(io.BytesIO(chart_images["burden"]), width=Inches(6))

    # ── Ratio Calculator Result ──
    doc.add_heading("Revenue-Neutral Ratio Analysis", level=2)

    if calc.is_capped:
        doc.add_paragraph(
            f"To return farmland's tax burden to the {target_year} level of "
            f"{calc.target_burden:.2%}, a farm tax ratio of {calc.required_ratio:.4f} "
            f"would be required — this exceeds the provincial maximum of {MAX_FARM_RATIO:.2f}. "
            f"The analysis below uses the capped ratio of {calc.effective_ratio:.4f}."
        )
    else:
        doc.add_paragraph(
            f"To return farmland's tax burden to the {target_year} level of "
            f"{calc.target_burden:.2%}, the farm tax ratio would need to move from "
            f"{calc.current_burden:.2%}-burden (current ratio {calc.current_farm_ratio:.4f}) "
            f"to {calc.effective_ratio:.4f}, "
            f"within the provincial maximum of {MAX_FARM_RATIO:.2f}."
        )

    # Impact table (with "All Other Classes" row — Fix 2)
    doc.add_heading("Tax Shift Impact (Revenue-Neutral)", level=3)
    impact_table = doc.add_table(rows=7, cols=4, style='Light List Accent 1')
    impact_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    impact_headers = ["Tax Class", "Current Taxes", "New Taxes", "Change"]
    for i, h in enumerate(impact_headers):
        impact_table.rows[0].cells[i].text = h
    impacts = [
        ("🌾 Farmland", calc.model_current_farm_taxes, calc.model_new_farm_taxes),
        ("🏠 Residential", calc.model_current_res_taxes, calc.model_new_res_taxes),
        ("🏪 Commercial", calc.model_current_com_taxes, calc.model_new_com_taxes),
        ("🏭 Industrial", calc.model_current_ind_taxes, calc.model_new_ind_taxes),
        ("📦 All Other Classes", calc.model_current_other_taxes, calc.model_new_other_taxes),
    ]
    for row_idx, (name, cur, new) in enumerate(impacts, 1):
        chg = new - cur
        impact_table.rows[row_idx].cells[0].text = name
        impact_table.rows[row_idx].cells[1].text = f"${cur:,.0f}"
        impact_table.rows[row_idx].cells[2].text = f"${new:,.0f}"
        sign = "+" if chg >= 0 else ""
        impact_table.rows[row_idx].cells[3].text = f"{sign}${chg:,.0f}"
    # Total row
    impact_table.rows[6].cells[0].text = "TOTAL"
    impact_table.rows[6].cells[1].text = f"${calc.total_muni_taxes:,.0f}"
    impact_table.rows[6].cells[2].text = f"${calc.total_muni_taxes:,.0f}"
    impact_table.rows[6].cells[3].text = "$0"

    # Per $100k CVA table
    doc.add_heading("Impact Per $100,000 of Assessment", level=3)
    per100k_table = doc.add_table(rows=5, cols=2, style='Light List Accent 1')
    per100k_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    per100k_table.rows[0].cells[0].text = "Tax Class"
    per100k_table.rows[0].cells[1].text = "Change Per $100k CVA"
    per100k_data = [
        ("🌾 Farmland", -calc.farm_savings_per_100k),
        ("🏠 Residential", calc.res_increase_per_100k),
        ("🏪 Commercial", calc.com_increase_per_100k),
        ("🏭 Industrial", calc.ind_increase_per_100k),
    ]
    for row_idx, (name, val) in enumerate(per100k_data, 1):
        per100k_table.rows[row_idx].cells[0].text = name
        sign = "+" if val >= 0 else ""
        per100k_table.rows[row_idx].cells[1].text = f"{sign}${val:,.2f}"

    # ── Summary with per-household impact (Fix 4) ──
    doc.add_heading("Key Takeaway", level=2)
    takeaway = (
        f"If the farm tax ratio were adjusted revenue-neutrally to "
        f"{calc.effective_ratio:.4f}, farmland owners would save a total of "
        f"${calc.farm_savings_total:,.0f} (${calc.farm_savings_per_100k:,.2f} per $100k CVA). "
        f"This cost would be distributed across residential (+${calc.res_increase_per_100k:,.2f} "
        f"per $100k), commercial (+${calc.com_increase_per_100k:,.2f} per $100k), "
        f"industrial (+${calc.ind_increase_per_100k:,.2f} per $100k), and all other "
        f"property classes."
    )
    if calc.total_households > 0:
        takeaway += (
            f"\n\nThis would cost the average residential household "
            f"${calc.res_increase_per_household:,.2f} per year "
            f"(${calc.res_increase_per_household_month:,.2f} per month)."
        )
    doc.add_paragraph(takeaway)

    # Methodology footnote (V14: expanded per expert recommendation)
    footnote = doc.add_paragraph()
    footnote.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = footnote.add_run(
        "Methodology: This analysis uses a revenue-neutral model where the total "
        "municipal levy is held constant. All property class ratios except farmland "
        "are frozen at their current values, and the residential base rate floats "
        "to absorb the tax shift. The model uses Current Value Assessment (CVA) and "
        "tax ratios as reported in Schedule 26A and Schedule 22A of the Financial "
        "Information Return (FIR). Municipal taxes are calculated as LT + UT "
        "(excluding the provincial education levy). Actual bylaw levies may vary "
        "slightly due to municipal decimal rounding and rate-setting conventions."
    )
    run.font.size = Pt(8)
    run.font.italic = True
    run.font.color.rgb = RGBColor(0x75, 0x75, 0x75)

    # ── Footer ──
    footer_p = doc.add_paragraph()
    footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer_p.add_run("Source: Ontario Financial Information Return (FIR) | Generated using OFA's farm and rural database")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    # Write to buffer
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Upper-Tier Resolution
# ---------------------------------------------------------------------------

def resolve_upper_tier(
    sgc_code: str,
    fir_df: pd.DataFrame,
) -> dict:
    """Resolve a lower-tier municipality to its upper-tier county/region.

    SGC codes follow the pattern 35CCXXX where CC = census division.
    Upper-tier entries always end in '000'. For single-tier municipalities
    (total_ut_taxes = 0), the municipality IS the taxing authority.

    Returns dict with:
        upper_tier_code: str (the upper-tier SGC code)
        upper_tier_name: str (display name)
        is_single_tier: bool (True if municipality is its own authority)
        is_lower_tier: bool (True if a lower-tier within a county/region)
    """
    latest = fir_df.sort_values("year").drop_duplicates("sgc_code", keep="last")

    muni_row = latest[latest["sgc_code"] == sgc_code]
    if muni_row.empty:
        return {
            "upper_tier_code": sgc_code,
            "upper_tier_name": sgc_code,
            "is_single_tier": True,
            "is_lower_tier": False,
        }

    muni_row = muni_row.iloc[0]
    tier = muni_row.get("tier", "")
    ut_taxes = _get_or_zero(muni_row.get("total_ut_taxes"))

    # If upper-tier taxes == 0, this is a single-tier municipality
    if ut_taxes <= 0 or tier == "upper":
        import re
        name = str(muni_row.get("municipality_name", sgc_code))
        # Normalize abbreviations for display
        name = re.sub(r'\bUCo$', 'United Counties', name)
        name = re.sub(r'\bCo$', 'County', name)
        name = re.sub(r'\bR$', 'Region', name)
        name = re.sub(r'\bD$', 'District', name)
        name = re.sub(r'\bTp$', 'Township', name)
        name = re.sub(r'\bT$', 'Town', name)
        name = re.sub(r'\bC$', 'City', name)
        return {
            "upper_tier_code": sgc_code,
            "upper_tier_name": name,
            "is_single_tier": True,
            "is_lower_tier": False,
        }

    # Lower-tier: derive upper-tier code by replacing last 3 digits with 000
    upper_code = sgc_code[:4] + "000"

    upper_row = latest[latest["sgc_code"] == upper_code]
    if not upper_row.empty:
        import re
        raw_name = str(upper_row.iloc[0].get("municipality_name", upper_code))
        # Normalize abbreviations
        raw_name = re.sub(r'\bUCo$', 'United Counties', raw_name)
        raw_name = re.sub(r'\bCo$', 'County', raw_name)
        raw_name = re.sub(r'\bR$', 'Region', raw_name)
        raw_name = re.sub(r'\bD$', 'District', raw_name)
        upper_name = raw_name
    else:
        upper_name = f"Census Division {sgc_code[:4]}"

    return {
        "upper_tier_code": upper_code,
        "upper_tier_name": upper_name,
        "is_single_tier": False,
        "is_lower_tier": True,
    }


# ---------------------------------------------------------------------------
# PowerPoint Report Generation
# ---------------------------------------------------------------------------

def _make_chart_image(fig) -> io.BytesIO:
    """Render a matplotlib figure to a BytesIO PNG buffer."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    import matplotlib.pyplot as plt
    plt.close(fig)
    return buf


def _build_tax_trends_chart(tax_trends_by_year: dict, muni_name: str) -> io.BytesIO:
    """Line chart of tax payment trends by property class."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker

    years = sorted(tax_trends_by_year.keys())
    farm = [tax_trends_by_year[y].get("farm", 0) for y in years]
    res = [tax_trends_by_year[y].get("res", 0) for y in years]
    com = [tax_trends_by_year[y].get("com", 0) for y in years]
    ind = [tax_trends_by_year[y].get("ind", 0) for y in years]

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    ax.plot(years, farm, "o-", color="#2E7D32", linewidth=2.5, markersize=5, label="Farmland")
    ax.plot(years, res, "s-", color="#1565C0", linewidth=2, markersize=4, label="Residential")
    ax.plot(years, com, "^-", color="#E65100", linewidth=1.5, markersize=4, label="Commercial")
    ax.plot(years, ind, "D-", color="#6A1B9A", linewidth=1.5, markersize=4, label="Industrial")

    ax.set_title(f"Municipal Tax Payments by Property Class", fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Year", fontsize=11)
    ax.set_ylabel("Annual Tax Payment ($)", fontsize=11)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.legend(loc="upper left", framealpha=0.9)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    return _make_chart_image(fig)


def _build_burden_chart(burden_by_year: dict, muni_name: str) -> io.BytesIO:
    """Stacked area chart of tax burden share."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    years = sorted(burden_by_year.keys())
    farm = [burden_by_year[y].get("farm", 0) * 100 for y in years]
    res = [burden_by_year[y].get("res", 0) * 100 for y in years]
    com = [burden_by_year[y].get("com", 0) * 100 for y in years]
    ind = [burden_by_year[y].get("ind", 0) * 100 for y in years]

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    ax.stackplot(years, farm, res, com, ind,
                 labels=["Farmland", "Residential", "Commercial", "Industrial"],
                 colors=["#2E7D32", "#1565C0", "#E65100", "#6A1B9A"], alpha=0.85)

    ax.set_title("Tax Burden Share by Property Class (%)", fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Year", fontsize=11)
    ax.set_ylabel("Share of Municipal Taxes (%)", fontsize=11)
    ax.set_ylim(0, 100)
    ax.legend(loc="center right", framealpha=0.9)
    ax.grid(True, alpha=0.3, axis="y")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    return _make_chart_image(fig)


def _build_cva_bar_chart(cva_growth: dict) -> io.BytesIO:
    """Horizontal bar chart of CVA growth by class."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    classes = ["Farmland", "Residential", "Commercial", "Industrial"]
    values = [cva_growth.get(c, 0) for c in classes]
    colors = ["#2E7D32", "#1565C0", "#E65100", "#6A1B9A"]

    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    bars = ax.barh(classes, values, color=colors, height=0.6, edgecolor="white", linewidth=0.5)

    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + 2, bar.get_y() + bar.get_height() / 2,
                f"{val:+.1f}%", va="center", fontsize=11, fontweight="bold")

    ax.set_title("Cumulative CVA Growth by Property Class", fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Growth (%)", fontsize=11)
    ax.grid(True, alpha=0.3, axis="x")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    return _make_chart_image(fig)


def _build_impact_chart(calc: 'RatioResult') -> io.BytesIO:
    """Horizontal bar chart of revenue-neutral tax impact by class."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    classes = ["Farmland", "Residential", "Commercial", "Industrial", "Other"]
    impacts = [
        -calc.farm_savings_total,
        calc.res_increase_total,
        calc.com_increase_total,
        calc.ind_increase_total,
        calc.other_increase_total,
    ]
    colors = ["#2E7D32" if v < 0 else "#B71C1C" for v in impacts]

    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    bars = ax.barh(classes, impacts, color=colors, height=0.6, edgecolor="white", linewidth=0.5)

    # Place labels outside the bars — always to the right of bar end
    for bar, val in zip(bars, impacts):
        label = f"-${abs(val):,.0f}" if val < 0 else f"+${val:,.0f}"
        # For negative bars, label goes to the left of the bar end
        if val < 0:
            ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2,
                    f" {label} ", va="center", ha="right", fontsize=10, fontweight="bold")
        else:
            ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2,
                    f" {label} ", va="center", ha="left", fontsize=10, fontweight="bold")

    ax.set_title("Revenue-Neutral Tax Impact by Class", fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Change in Taxes ($)", fontsize=11)
    ax.axvline(x=0, color="black", linewidth=0.8)
    ax.grid(True, alpha=0.3, axis="x")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    import matplotlib.ticker as mticker
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # Ensure enough left margin so labels/ticks don't clip
    x_min = min(impacts) * 1.25
    x_max = max(impacts) * 1.25
    ax.set_xlim(x_min, x_max)

    fig.tight_layout()

    return _make_chart_image(fig)


def _build_indexed_cva_chart(cva_growth: dict, tax_trends_by_year: dict = None,
                              year_range: str = "") -> io.BytesIO:
    """Line chart showing CVA growth indexed to 100 at the base year.

    Uses cva_growth dict {class: cumulative_pct} and tax_trends_by_year
    (for consistent year axis) to build the indexed chart.
    Fallback: derives approximate indexed values from cumulative growth %.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    classes = ["Farmland", "Residential", "Commercial", "Industrial"]
    colors = ["#2E7D32", "#1565C0", "#E65100", "#6A1B9A"]
    markers = ["o", "s", "^", "D"]

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    # We have cumulative growth %, so latest index = 100 + growth%
    latest_idx = {}
    for cls in classes:
        g = cva_growth.get(cls)
        if g is not None:
            latest_idx[cls] = 100 + g
        else:
            latest_idx[cls] = None

    # Simple 2-point chart: base year = 100, latest year = indexed value
    # Extract year range
    yr_parts = year_range.replace("–", "-").replace("\u2013", "-").split("-")
    base_yr = int(yr_parts[0]) if yr_parts else 2010
    last_yr = int(yr_parts[-1]) if len(yr_parts) > 1 else 2024

    for cls, color, marker in zip(classes, colors, markers):
        idx_val = latest_idx.get(cls)
        if idx_val is not None:
            ax.plot([base_yr, last_yr], [100, idx_val],
                    marker=marker, color=color, linewidth=2.5, markersize=8,
                    label=f"{cls} ({idx_val:.0f})")

    ax.axhline(y=100, color="#999", linewidth=1, linestyle="--", alpha=0.7)
    ax.set_title(f"CVA Growth Rate Comparison (Index: {base_yr} = 100)",
                 fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Year", fontsize=11)
    ax.set_ylabel(f"Index ({base_yr} = 100)", fontsize=11)
    ax.legend(loc="upper left", framealpha=0.9, fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    return _make_chart_image(fig)


def _build_indexed_tax_chart(tax_trends_by_year: dict) -> io.BytesIO:
    """Line chart showing tax payment growth indexed to 100 at base year."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    years = sorted(tax_trends_by_year.keys())
    if len(years) < 2:
        return None

    keys = {"Farmland": "farm", "Residential": "res",
            "Commercial": "com", "Industrial": "ind"}
    colors = {"Farmland": "#2E7D32", "Residential": "#1565C0",
              "Commercial": "#E65100", "Industrial": "#6A1B9A"}
    markers = {"Farmland": "o", "Residential": "s",
               "Commercial": "^", "Industrial": "D"}

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    base_yr = years[0]

    for cls, key in keys.items():
        base_val = tax_trends_by_year[base_yr].get(key, 0)
        if base_val <= 0:
            continue
        vals = [(tax_trends_by_year[y].get(key, 0) / base_val) * 100 for y in years]
        latest_idx = vals[-1]
        ax.plot(years, vals, marker=markers[cls], color=colors[cls],
                linewidth=2.5, markersize=5,
                label=f"{cls} ({latest_idx:.0f})")

    ax.axhline(y=100, color="#999", linewidth=1, linestyle="--", alpha=0.7)
    ax.set_title(f"Tax Payment Growth Comparison (Index: {base_yr} = 100)",
                 fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Year", fontsize=11)
    ax.set_ylabel(f"Index ({base_yr} = 100)", fontsize=11)
    ax.legend(loc="upper left", framealpha=0.9, fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    return _make_chart_image(fig)


def generate_pptx_report(
    muni_name: str,
    year_range: str,
    current_year: int,
    target_year: int,
    burden_by_year: dict,
    calc: RatioResult,
    cva_growth: dict,
    is_two_tier: bool = False,
    is_upper_tier: bool = False,
    tax_trends_by_year: dict = None,
    logo_bytes: bytes = None,
    fir_raw_df: 'pd.DataFrame | None' = None,
) -> io.BytesIO:
    """Generate a 12-slide Farm Tax delegation presentation as a PowerPoint file.

    Slide structure:
      1. Title
      2. How Property Taxes Work (educational)
      3. MPAC & Assessment (educational)
      4. The Issue: Rising Farm Tax Burden (data)
      5. Why Farm Values Rose Faster (data — CVA chart)
      6. Tax Payment Trends (data — line chart + table)
      7. Revenue Neutrality Explained (educational)
      8. The Logic of Our Ask (educational)
      9. Municipalities Leading the Way (data — peer table)
     10. Revenue-Neutral Impact (data — chart + table)
     11. Key Takeaway & The Ask (data)
     12. Thank You / Questions (closing)

    Returns a BytesIO buffer containing the .pptx file.
    """
    import re
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor as PptxRGB
    from pptx.enum.text import PP_ALIGN

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    OFA_GREEN = PptxRGB(0x1B, 0x5E, 0x20)
    OFA_GREEN_LIGHT = PptxRGB(0x2E, 0x7D, 0x32)
    WHITE = PptxRGB(0xFF, 0xFF, 0xFF)
    DARK = PptxRGB(0x33, 0x33, 0x33)
    GREY = PptxRGB(0x75, 0x75, 0x75)
    TOTAL_SLIDES = 13

    def _normalize_name(name: str) -> str:
        """Expand common FIR abbreviations for presentation display."""
        name = re.sub(r'\bUCo$', 'United Counties', name)
        name = re.sub(r'\bCo$', 'County', name)
        name = re.sub(r'\bR$', 'Region', name)
        name = re.sub(r'\bD$', 'District', name)
        name = re.sub(r'\bTp$', 'Township', name)
        name = re.sub(r'\bT$', 'Town', name)
        name = re.sub(r'\bC$', 'City', name)
        name = re.sub(r'\bV$', 'Village', name)
        name = re.sub(r'\bM$', 'Municipality', name)
        name = re.sub(r'\(([A-Z][a-zA-Z\s-]+)\)$',
                      lambda m: f'(County of {m.group(1)})' if 'County' not in m.group(1) and 'Region' not in m.group(1) and 'District' not in m.group(1) else f'({m.group(1)})',
                      name)
        return name

    display_name = _normalize_name(muni_name)

    def _add_logo(slide, title_slide=False):
        """Place logo without overlapping content."""
        if not logo_bytes:
            return
        if title_slide:
            slide.shapes.add_picture(
                io.BytesIO(logo_bytes),
                Inches(10.8), Inches(0.3),
                height=Inches(1.0),
            )
        else:
            slide.shapes.add_picture(
                io.BytesIO(logo_bytes),
                Inches(12.0), Inches(0.15),
                height=Inches(0.7),
            )

    def _add_green_header(slide, title_text, subtitle_text=None):
        """Add a green header bar at the top of a content slide."""
        bg = slide.shapes.add_shape(
            1, Inches(0), Inches(0), Inches(13.333), Inches(1.1),
        )
        bg.fill.solid()
        bg.fill.fore_color.rgb = OFA_GREEN
        bg.line.fill.background()

        txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.12), Inches(11), Inches(0.55))
        tf = txBox.text_frame
        p = tf.paragraphs[0]
        p.text = title_text
        p.font.size = Pt(26)
        p.font.bold = True
        p.font.color.rgb = WHITE

        if subtitle_text:
            txBox2 = slide.shapes.add_textbox(Inches(0.5), Inches(0.6), Inches(11), Inches(0.35))
            tf2 = txBox2.text_frame
            p2 = tf2.paragraphs[0]
            p2.text = subtitle_text
            p2.font.size = Pt(13)
            p2.font.color.rgb = PptxRGB(0xC8, 0xE6, 0xC9)

    def _add_footer(slide, text=None, slide_number=None):
        """Add a subtle footer at the bottom with optional slide number."""
        ft = text or "Source: Ontario Financial Information Return (FIR) | Generated using OFA\u2019s farm and rural database"
        txBox = slide.shapes.add_textbox(Inches(0.5), Inches(7.05), Inches(10.5), Inches(0.35))
        tf = txBox.text_frame
        p = tf.paragraphs[0]
        p.text = ft
        p.font.size = Pt(9)
        p.font.color.rgb = GREY
        p.alignment = PP_ALIGN.CENTER
        if slide_number is not None:
            sn_box = slide.shapes.add_textbox(Inches(11.5), Inches(7.05), Inches(1.5), Inches(0.35))
            sn_tf = sn_box.text_frame
            sn_p = sn_tf.paragraphs[0]
            sn_p.text = f"{slide_number} / {TOTAL_SLIDES}"
            sn_p.font.size = Pt(9)
            sn_p.font.color.rgb = GREY
            sn_p.alignment = PP_ALIGN.RIGHT

    def _add_compact_table(slide, headers, rows, left, top, width, row_height=Inches(0.35)):
        """Add a compact formatted table."""
        n_rows = len(rows) + 1
        n_cols = len(headers)
        table_shape = slide.shapes.add_table(n_rows, n_cols, left, top, width, row_height * n_rows)
        table = table_shape.table

        for i, h in enumerate(headers):
            cell = table.cell(0, i)
            cell.text = h
            cell.fill.solid()
            cell.fill.fore_color.rgb = OFA_GREEN
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(10)
                p.font.bold = True
                p.font.color.rgb = WHITE
                p.alignment = PP_ALIGN.CENTER

        for ri, row in enumerate(rows):
            for ci, val in enumerate(row):
                cell = table.cell(ri + 1, ci)
                cell.text = str(val)
                for p in cell.text_frame.paragraphs:
                    p.font.size = Pt(10)
                    p.alignment = PP_ALIGN.CENTER

        return table

    def _add_bullet_content(slide, bullets, left=0.8, top=1.4, width=11.5, height=5.2, font_size=18, spacing=12):
        """Add bullet-point text content to a slide."""
        txBox = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        tf = txBox.text_frame
        tf.word_wrap = True
        for i, bullet in enumerate(bullets):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            if isinstance(bullet, tuple):
                # (text, is_bold, font_size_override, color_override)
                text, bold, fs, color = bullet
                p.text = text
                p.font.bold = bold
                p.font.size = Pt(fs)
                p.font.color.rgb = color
            else:
                p.text = bullet
                p.font.size = Pt(font_size)
                p.font.color.rgb = DARK
                p.font.bold = False
            p.space_after = Pt(spacing)
        return txBox

    # ══════════════════════════════════════════════════════════════════
    # SLIDE 1: Title
    # ══════════════════════════════════════════════════════════════════
    slide1 = prs.slides.add_slide(prs.slide_layouts[6])
    bg_shape = slide1.shapes.add_shape(
        1, Inches(0), Inches(0), Inches(13.333), Inches(7.5),
    )
    bg_shape.fill.solid()
    bg_shape.fill.fore_color.rgb = OFA_GREEN
    bg_shape.line.fill.background()

    txBox = slide1.shapes.add_textbox(Inches(1), Inches(2), Inches(11), Inches(1.5))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = f"Farm Property Tax Analysis \u2014 {current_year}"
    p.font.size = Pt(44)
    p.font.bold = True
    p.font.color.rgb = WHITE
    p.alignment = PP_ALIGN.CENTER

    txBox2 = slide1.shapes.add_textbox(Inches(1), Inches(3.5), Inches(11), Inches(1))
    tf2 = txBox2.text_frame
    p2 = tf2.paragraphs[0]
    p2.text = display_name
    p2.font.size = Pt(32)
    p2.font.color.rgb = PptxRGB(0xC8, 0xE6, 0xC9)
    p2.alignment = PP_ALIGN.CENTER

    txBox3 = slide1.shapes.add_textbox(Inches(1), Inches(5), Inches(11), Inches(0.8))
    tf3 = txBox3.text_frame
    p3 = tf3.paragraphs[0]
    p3.text = f"FIR Data: {year_range}  |  Generated from OFA\u2019s farm and rural database"
    p3.font.size = Pt(16)
    p3.font.color.rgb = PptxRGB(0xA5, 0xD6, 0xA7)
    p3.alignment = PP_ALIGN.CENTER

    _add_logo(slide1, title_slide=True)

    # ══════════════════════════════════════════════════════════════════
    # SLIDE 2: How Property Taxes Work
    # ══════════════════════════════════════════════════════════════════
    slide2 = prs.slides.add_slide(prs.slide_layouts[6])
    _add_green_header(slide2, "How Property Taxes Work")

    bullets_s2 = [
        ("Two factors determine every property tax bill:", True, 20, DARK),
        "\u2460  Assessed Value \u2014 determined by MPAC (Municipal Property Assessment Corporation), not the municipality",
        "\u2461  Tax Rate \u2014 set annually by your municipal council through the budget process",
        ("Tax Bill  =  Assessed Value  \u00d7  Tax Rate", True, 24, OFA_GREEN_LIGHT),
        "The municipality controls the tax rate. MPAC determines the assessed value.",
        "Different property classes (residential, farm, commercial, industrial) can have different tax rates, expressed as a ratio of the residential rate.",
        ("Ontario\u2019s farm tax ratio can be set between 0 and 0.25 (i.e., farms pay a maximum of 25% of the residential rate).", True, 16, GREY),
    ]
    _add_bullet_content(slide2, bullets_s2, font_size=17, spacing=14)
    _add_logo(slide2)
    _add_footer(slide2, slide_number=2)

    # ══════════════════════════════════════════════════════════════════
    # SLIDE 3: MPAC & Assessment
    # ══════════════════════════════════════════════════════════════════
    slide3 = prs.slides.add_slide(prs.slide_layouts[6])
    _add_green_header(slide3, "MPAC & the Assessment Process")

    bullets_s3 = [
        ("How MPAC Values Properties:", True, 20, DARK),
        "MPAC assesses every property in Ontario using a Current Value Assessment (CVA) approach \u2014 based on what the property would sell for on the open market.",
        "For farmland, MPAC uses comparable sales of agricultural properties in the area.",
        ("Assessment Cycle:", True, 20, DARK),
        "Historically, MPAC reassessed properties on a 4-year cycle. The most recent province-wide reassessment used January 1, 2016 values, phased in over 2017\u20132020.",
        ("\u26a0  In 2020, the Province froze all assessments at 2016 levels. No reassessment has occurred since.", True, 18, PptxRGB(0xB7, 0x1C, 0x1C)),
        "This means the large increases in farmland values that occurred before 2016 are still embedded in today\u2019s tax calculations.",
    ]
    _add_bullet_content(slide3, bullets_s3, font_size=17, spacing=12)
    _add_logo(slide3)
    _add_footer(slide3, slide_number=3)

    # ══════════════════════════════════════════════════════════════════
    # SLIDE 4: The Issue — Rising Farm Tax Burden
    # ══════════════════════════════════════════════════════════════════
    slide4 = prs.slides.add_slide(prs.slide_layouts[6])
    _add_green_header(slide4, "The Issue: Rising Farm Tax Burden",
                      "Farm\u2019s share of the total municipal tax bill has been increasing")

    if burden_by_year:
        try:
            burden_chart = _build_burden_chart(burden_by_year, muni_name)
            slide4.shapes.add_picture(burden_chart, Inches(0.3), Inches(1.2), width=Inches(8.0))
        except Exception:
            pass

        burden_years = sorted(burden_by_year.keys())
        if len(burden_years) >= 2:
            first_farm = burden_by_year[burden_years[0]].get("farm", 0)
            last_farm = burden_by_year[burden_years[-1]].get("farm", 0)
            delta = (last_farm - first_farm) * 100
            direction = "increased" if delta > 0 else "decreased"

            # Callout on the right
            txBox = slide4.shapes.add_textbox(Inches(8.5), Inches(1.5), Inches(4.5), Inches(2.5))
            tf = txBox.text_frame
            tf.word_wrap = True

            p = tf.add_paragraph()
            p.text = "Farmland Tax Burden"
            p.font.size = Pt(18)
            p.font.bold = True
            p.font.color.rgb = OFA_GREEN_LIGHT
            p.space_after = Pt(8)

            p2 = tf.add_paragraph()
            p2.text = f"{first_farm:.1%} ({burden_years[0]})"
            p2.font.size = Pt(16)
            p2.font.color.rgb = DARK
            p2.space_after = Pt(4)

            p3 = tf.add_paragraph()
            p3.text = f"{last_farm:.1%} ({burden_years[-1]})"
            p3.font.size = Pt(16)
            p3.font.color.rgb = DARK
            p3.space_after = Pt(12)

            p4 = tf.add_paragraph()
            p4.text = f"{direction.title()} by {abs(delta):.1f} pp"
            p4.font.size = Pt(20)
            p4.font.bold = True
            p4.font.color.rgb = PptxRGB(0xB7, 0x1C, 0x1C) if delta > 0 else OFA_GREEN_LIGHT

            # Condensed burden summary table
            burden_headers = ["Year", "Farm", "Res", "Com", "Ind"]
            first_yr_b = burden_years[0]
            last_yr_b = burden_years[-1]
            burden_tbl_rows = []
            for yr_b in [first_yr_b, last_yr_b]:
                d = burden_by_year[yr_b]
                burden_tbl_rows.append([
                    str(yr_b),
                    f"{d.get('farm', 0):.1%}",
                    f"{d.get('res', 0):.1%}",
                    f"{d.get('com', 0):.1%}",
                    f"{d.get('ind', 0):.1%}",
                ])
            first_b = burden_by_year[first_yr_b]
            last_b = burden_by_year[last_yr_b]
            change_row = ["\u0394 (pp)"]
            for key in ["farm", "res", "com", "ind"]:
                diff = (last_b.get(key, 0) - first_b.get(key, 0)) * 100
                change_row.append(f"{diff:+.1f}")
            burden_tbl_rows.append(change_row)
            _add_compact_table(
                slide4, burden_headers, burden_tbl_rows,
                Inches(8.5), Inches(4.2), Inches(4.5), row_height=Inches(0.30)
            )

        # Two drivers explanation
        txBox_d = slide4.shapes.add_textbox(Inches(0.3), Inches(5.8), Inches(8.0), Inches(1.0))
        tf_d = txBox_d.text_frame
        tf_d.word_wrap = True
        p_d = tf_d.paragraphs[0]
        p_d.text = (
            "Two factors drive farm tax burden: \u2460 Farm values rising faster than "
            "other property types (determined by MPAC), and \u2461 The tax ratio applied "
            "to farmland (set by Council)."
        )
        p_d.font.size = Pt(13)
        p_d.font.bold = True
        p_d.font.color.rgb = OFA_GREEN_LIGHT

    _add_logo(slide4)
    _add_footer(slide4, slide_number=4)

    # ══════════════════════════════════════════════════════════════════
    # SLIDE 5: Why Farm Values Rose Faster (CVA chart)
    # ══════════════════════════════════════════════════════════════════
    slide5 = prs.slides.add_slide(prs.slide_layouts[6])
    _add_green_header(slide5, "Why Farm Values Rose Faster",
                      "Farmland assessments grew much more than other property types")

    try:
        cva_chart = _build_cva_bar_chart(cva_growth)
        slide5.shapes.add_picture(cva_chart, Inches(0.5), Inches(1.3), width=Inches(7.5))
    except Exception:
        pass

    # Key stats with period header
    txBox = slide5.shapes.add_textbox(Inches(8.5), Inches(1.3), Inches(4.5), Inches(4))
    tf = txBox.text_frame
    tf.word_wrap = True
    p_hdr = tf.paragraphs[0]
    p_hdr.text = f"Cumulative CVA Growth ({year_range})"
    p_hdr.font.size = Pt(14)
    p_hdr.font.bold = True
    p_hdr.font.color.rgb = OFA_GREEN_LIGHT
    p_hdr.space_after = Pt(12)
    stat_lines = [
        f"Farmland: {cva_growth.get('Farmland', 0):+.1f}%",
        f"Residential: {cva_growth.get('Residential', 0):+.1f}%",
        f"Commercial: {cva_growth.get('Commercial', 0):+.1f}%",
        f"Industrial: {cva_growth.get('Industrial', 0):+.1f}%",
    ]
    for item in stat_lines:
        p = tf.add_paragraph()
        p.text = item
        p.font.size = Pt(18)
        p.font.color.rgb = DARK
        p.space_after = Pt(10)

    # Context note
    farm_g = cva_growth.get('Farmland', 0)
    res_g = cva_growth.get('Residential', 0)
    if farm_g > res_g and res_g > 0:
        ratio_text = f"{farm_g / res_g:.1f}x"
        context_note = (
            f"Farmland assessments grew {ratio_text} faster than residential "
            f"values \u2014 this is the root cause of the tax burden shift."
        )
    else:
        context_note = (
            "Assessment growth differences drive the tax burden shift."
        )
    txBox_ctx = slide5.shapes.add_textbox(Inches(0.5), Inches(5.8), Inches(12), Inches(0.5))
    tf_ctx = txBox_ctx.text_frame
    tf_ctx.word_wrap = True
    p_ctx = tf_ctx.paragraphs[0]
    p_ctx.text = context_note
    p_ctx.font.size = Pt(14)
    p_ctx.font.bold = True
    p_ctx.font.color.rgb = OFA_GREEN_LIGHT

    # CVA freeze note
    txBox_note = slide5.shapes.add_textbox(Inches(0.5), Inches(6.3), Inches(12), Inches(0.6))
    tf_note = txBox_note.text_frame
    tf_note.word_wrap = True
    p_note = tf_note.paragraphs[0]
    p_note.text = (
        "Note: CVA frozen at Jan 1, 2016 valuation levels (phased in 2017\u20132020). "
        "Post-2020 changes reflect new construction/demolitions only."
    )
    p_note.font.size = Pt(11)
    p_note.font.italic = True
    p_note.font.color.rgb = GREY

    _add_logo(slide5)
    _add_footer(slide5, slide_number=5)

    # ══════════════════════════════════════════════════════════════════
    # SLIDE 6 (NEW): Indexed Growth Rate Comparison
    # ══════════════════════════════════════════════════════════════════
    slide6_idx = prs.slides.add_slide(prs.slide_layouts[6])
    _add_green_header(slide6_idx, "Growth Rate Comparison (Indexed)",
                      f"All classes normalized to 100 at base year — rate of change revealed")

    # Left: Indexed CVA chart
    try:
        idx_cva_chart = _build_indexed_cva_chart(cva_growth, tax_trends_by_year, year_range)
        if idx_cva_chart:
            slide6_idx.shapes.add_picture(idx_cva_chart, Inches(0.3), Inches(1.2), width=Inches(6.0))
    except Exception:
        pass

    # Right: Indexed tax chart
    if tax_trends_by_year:
        try:
            idx_tax_chart = _build_indexed_tax_chart(tax_trends_by_year)
            if idx_tax_chart:
                slide6_idx.shapes.add_picture(idx_tax_chart, Inches(6.5), Inches(1.2), width=Inches(6.0))
        except Exception:
            pass

    # Summary table at bottom
    farm_g = cva_growth.get("Farmland", 0)
    res_g = cva_growth.get("Residential", 0)
    com_g = cva_growth.get("Commercial", 0)
    ind_g = cva_growth.get("Industrial", 0)

    idx_headers = ["", "Farmland", "Residential", "Commercial", "Industrial"]
    idx_rows = [
        ["CVA Index", f"{100 + farm_g:.0f}", f"{100 + res_g:.0f}", f"{100 + com_g:.0f}", f"{100 + ind_g:.0f}"],
    ]

    # Add tax index row if we have the data
    if tax_trends_by_year:
        trend_years = sorted(tax_trends_by_year.keys())
        if len(trend_years) >= 2:
            base_d = tax_trends_by_year[trend_years[0]]
            last_d = tax_trends_by_year[trend_years[-1]]
            tax_idx_row = ["Tax Index"]
            for key in ["farm", "res", "com", "ind"]:
                bv = base_d.get(key, 0)
                lv = last_d.get(key, 0)
                if bv > 0:
                    tax_idx_row.append(f"{(lv / bv) * 100:.0f}")
                else:
                    tax_idx_row.append("n/a")
            idx_rows.append(tax_idx_row)

    _add_compact_table(slide6_idx, idx_headers, idx_rows,
                       Inches(1.5), Inches(5.5), Inches(10), row_height=Inches(0.32))

    # Narrative callout
    if farm_g > res_g and res_g > 0:
        ratio_text = f"{farm_g / res_g:.1f}x"
        narrative = (
            f"When normalized to a common starting point, farmland values grew {ratio_text} faster "
            f"than residential — this growth rate disparity is the root cause of the tax burden shift."
        )
    else:
        narrative = (
            "Indexed comparison allows direct rate-of-change comparison across classes of very different sizes."
        )
    txBox_idx_narr = slide6_idx.shapes.add_textbox(Inches(0.5), Inches(6.5), Inches(12), Inches(0.5))
    tf_idx_narr = txBox_idx_narr.text_frame
    tf_idx_narr.word_wrap = True
    p_idx_narr = tf_idx_narr.paragraphs[0]
    p_idx_narr.text = narrative
    p_idx_narr.font.size = Pt(13)
    p_idx_narr.font.bold = True
    p_idx_narr.font.color.rgb = OFA_GREEN_LIGHT

    _add_logo(slide6_idx)
    _add_footer(slide6_idx, slide_number=6)

    # ══════════════════════════════════════════════════════════════════
    # SLIDE 6: Tax Payment Trends (line chart + table)
    # ══════════════════════════════════════════════════════════════════
    slide6 = prs.slides.add_slide(prs.slide_layouts[6])
    _add_green_header(slide6, "Municipal Tax Payment Trends",
                      f"How assessment growth translated into tax dollar growth ({year_range})")

    if tax_trends_by_year:
        try:
            trends_chart = _build_tax_trends_chart(tax_trends_by_year, muni_name)
            slide6.shapes.add_picture(trends_chart, Inches(0.3), Inches(1.2), width=Inches(8.0))
        except Exception:
            pass

        trend_years = sorted(tax_trends_by_year.keys())
        if len(trend_years) >= 2:
            first_yr, last_yr = trend_years[0], trend_years[-1]
            first_d = tax_trends_by_year[first_yr]
            last_d = tax_trends_by_year[last_yr]

            # Build year-over-year % change rows
            headers = ["Year", "Farm %", "Res %", "Com %", "Ind %"]
            all_yoy_rows = []
            for i in range(1, len(trend_years)):
                yr = trend_years[i]
                prev_yr = trend_years[i - 1]
                d = tax_trends_by_year[yr]
                prev_d = tax_trends_by_year[prev_yr]
                row = [str(yr)]
                for key in ["farm", "res", "com", "ind"]:
                    prev_val = prev_d.get(key, 0)
                    curr_val = d.get(key, 0)
                    if prev_val > 0:
                        pct = ((curr_val - prev_val) / prev_val) * 100
                        row.append(f"{pct:+.1f}%")
                    else:
                        row.append("n/a")
                all_yoy_rows.append(row)

            # Smart-truncate for long periods (>10 years): show first 3, last 3
            if len(all_yoy_rows) > 10:
                ellipsis_row = ["...", "...", "...", "...", "..."]
                rows = all_yoy_rows[:3] + [ellipsis_row] + all_yoy_rows[-3:]
            else:
                rows = all_yoy_rows

            # Total cumulative % change row
            total_row = [f"{first_yr}\u2013{last_yr}"]
            cum_pcts = {}
            for key in ["farm", "res", "com", "ind"]:
                fv = first_d.get(key, 0)
                lv = last_d.get(key, 0)
                if fv > 0:
                    total_pct = ((lv - fv) / fv) * 100
                    total_row.append(f"{total_pct:+.1f}%")
                    cum_pcts[key] = total_pct
                else:
                    total_row.append("n/a")
                    cum_pcts[key] = None
            rows.append(total_row)

            table = _add_compact_table(slide6, headers, rows, Inches(8.5), Inches(1.2), Inches(4.5), row_height=Inches(0.30))

            # Highlight cumulative total row
            last_ri = len(rows)
            farm_cell = table.cell(last_ri, 1)
            farm_cell.fill.solid()
            farm_cell.fill.fore_color.rgb = PptxRGB(0x2E, 0x7D, 0x32)
            for p in farm_cell.text_frame.paragraphs:
                p.font.bold = True
                p.font.color.rgb = PptxRGB(0xFF, 0xFF, 0xFF)
            label_cell = table.cell(last_ri, 0)
            label_cell.fill.solid()
            label_cell.fill.fore_color.rgb = PptxRGB(0x33, 0x33, 0x33)
            for p in label_cell.text_frame.paragraphs:
                p.font.bold = True
                p.font.color.rgb = PptxRGB(0xFF, 0xFF, 0xFF)

            # Narrative callout
            farm_cum = cum_pcts.get("farm")
            res_cum = cum_pcts.get("res")
            if farm_cum is not None and res_cum is not None:
                if farm_cum > res_cum and res_cum > 0:
                    ratio_text = f"{farm_cum / res_cum:.1f}x"
                    narrative = (
                        f"Farm property taxes grew {farm_cum:+.0f}% from "
                        f"{first_yr}\u2013{last_yr}, {ratio_text} the "
                        f"{res_cum:+.0f}% growth in residential taxes."
                    )
                else:
                    narrative = (
                        f"Farm property taxes grew {farm_cum:+.0f}% from "
                        f"{first_yr}\u2013{last_yr}, compared to "
                        f"{res_cum:+.0f}% for residential."
                    )
                txBox_narr = slide6.shapes.add_textbox(
                    Inches(0.3), Inches(5.6), Inches(8.0), Inches(0.5)
                )
                tf_narr = txBox_narr.text_frame
                tf_narr.word_wrap = True
                p_narr = tf_narr.paragraphs[0]
                p_narr.text = narrative
                p_narr.font.size = Pt(13)
                p_narr.font.bold = True
                p_narr.font.color.rgb = OFA_GREEN_LIGHT

    _add_logo(slide6)
    _add_footer(slide6, slide_number=7)


    # ══════════════════════════════════════════════════════════════════
    # SLIDE 7: Revenue Neutrality Explained
    # ══════════════════════════════════════════════════════════════════
    slide7 = prs.slides.add_slide(prs.slide_layouts[6])
    _add_green_header(slide7, "What Does Revenue-Neutral Mean?",
                      "Changing the tax ratio does NOT change total taxes collected")

    bullets_s7 = [
        ("Key Principle:", True, 22, OFA_GREEN_LIGHT),
        "Adjusting the farm tax ratio does not reduce or increase the total amount of property taxes a municipality collects.",
        ("Total municipal revenue stays exactly the same.", True, 20, OFA_GREEN),
        "What changes is how the tax burden is distributed among property classes \u2014 the relative share paid by each class (farm, residential, commercial, industrial).",
        "Lowering the farm ratio means a small portion of the tax burden shifts from farmland to all other property classes.",
        ("The municipality does not lose any revenue. The tax pool is simply redistributed more equitably.", True, 17, DARK),
        ("Think of it as slicing the same pie differently \u2014 the pie doesn\u2019t get smaller.", False, 16, GREY),
    ]
    _add_bullet_content(slide7, bullets_s7, font_size=17, spacing=14)
    _add_logo(slide7)
    _add_footer(slide7, slide_number=8)

    # ══════════════════════════════════════════════════════════════════
    # SLIDE 8: The Logic of Our Ask
    # ══════════════════════════════════════════════════════════════════
    slide8 = prs.slides.add_slide(prs.slide_layouts[6])
    _add_green_header(slide8, "The Logic of Our Ask",
                      "Why a lower farm tax ratio is the appropriate response")

    bullets_s8 = [
        ("The Problem:", True, 20, PptxRGB(0xB7, 0x1C, 0x1C)),
        "Farmland values across much of Ontario increased at a much faster rate than other property types before the province froze assessments in 2020.",
        "Because assessments are frozen, the disproportionate increase in farm values is permanently embedded in the tax base \u2014 there is no market correction coming.",
        ("The Solution:", True, 20, OFA_GREEN_LIGHT),
        "Since the assessment side of the equation is locked by the Province, the only tool available to address the burden shift is on the rate side.",
        "A lower farm property tax ratio relative to other property classes directly offsets the disproportionate assessment increase.",
        ("A lower ratio = a fairer share of the tax burden for farmers.", True, 18, OFA_GREEN),
        ("This is not a tax cut \u2014 it is a rebalancing of the tax load using the only tool available.", False, 16, GREY),
    ]
    _add_bullet_content(slide8, bullets_s8, font_size=17, spacing=12)
    _add_logo(slide8)
    _add_footer(slide8, slide_number=9)

    # ══════════════════════════════════════════════════════════════════
    # SLIDE 9: Municipalities Leading the Way
    # ══════════════════════════════════════════════════════════════════
    slide9 = prs.slides.add_slide(prs.slide_layouts[6])
    _add_green_header(slide9, "Municipalities Leading the Way",
                      "Upper-tier and single-tier municipalities that have already lowered their farm tax ratio")

    # Build peer list from FIR data
    peer_rows = []
    if fir_raw_df is not None:
        try:
            latest_yr = fir_raw_df["year"].max()
            latest = fir_raw_df[fir_raw_df["year"] == latest_yr].copy()
            latest["sgc_code"] = latest["sgc_code"].astype(str).str.zfill(7)

            # Upper-tier (ends in 000) + single-tier (no UT taxes)
            upper = latest[latest["sgc_code"].str.endswith("000")]
            single = latest[(latest["total_ut_taxes"].fillna(0) <= 0) &
                            (~latest["sgc_code"].str.endswith("000"))]
            combined = pd.concat([upper, single])
            combined = combined[combined["farmland_tax_ratio"].notna() &
                                (combined["farmland_tax_ratio"] > 0)]
            below_25 = combined[combined["farmland_tax_ratio"] < 0.25].sort_values("farmland_tax_ratio")

            for _, row in below_25.iterrows():
                name = _normalize_name(str(row.get("municipality_name", "")))
                ratio = float(row["farmland_tax_ratio"])
                peer_rows.append([name, f"{ratio:.4f}", f"{ratio * 100:.2f}%"])
        except Exception:
            pass

    if peer_rows:
        # Split into two columns if many municipalities
        peer_headers = ["Municipality", "Ratio", "% of Res Rate"]
        n_peers = len(peer_rows)

        if n_peers <= 12:
            # Single table
            _add_compact_table(slide9, peer_headers, peer_rows,
                               Inches(1.5), Inches(1.3), Inches(10), row_height=Inches(0.32))
        else:
            # Two-column layout
            mid = (n_peers + 1) // 2
            _add_compact_table(slide9, peer_headers, peer_rows[:mid],
                               Inches(0.5), Inches(1.3), Inches(6), row_height=Inches(0.32))
            _add_compact_table(slide9, peer_headers, peer_rows[mid:],
                               Inches(7.0), Inches(1.3), Inches(6), row_height=Inches(0.32))

        # Count callout
        txBox_count = slide9.shapes.add_textbox(Inches(0.5), Inches(6.3), Inches(12), Inches(0.5))
        tf_c = txBox_count.text_frame
        tf_c.word_wrap = True
        p_c = tf_c.paragraphs[0]
        p_c.text = (
            f"{n_peers} municipalities have already set their farm tax ratio "
            f"below the provincial maximum of 0.25 (FIR {int(latest_yr)} data)."
        )
        p_c.font.size = Pt(14)
        p_c.font.bold = True
        p_c.font.color.rgb = OFA_GREEN_LIGHT
        p_c.alignment = PP_ALIGN.CENTER
    else:
        txBox_na = slide9.shapes.add_textbox(Inches(1), Inches(3), Inches(11), Inches(1))
        tf_na = txBox_na.text_frame
        p_na = tf_na.paragraphs[0]
        p_na.text = "Peer municipality data not available."
        p_na.font.size = Pt(18)
        p_na.font.color.rgb = GREY
        p_na.alignment = PP_ALIGN.CENTER

    _add_logo(slide9)
    _add_footer(slide9, slide_number=10)

    # ══════════════════════════════════════════════════════════════════
    # SLIDE 10: Revenue-Neutral Impact (chart + table)
    # ══════════════════════════════════════════════════════════════════
    slide10 = prs.slides.add_slide(prs.slide_layouts[6])
    capped_note = " (capped at 0.25)" if calc.is_capped else ""
    _add_green_header(
        slide10,
        "Revenue-Neutral Impact Analysis",
        f"Current ratio: {calc.current_farm_ratio:.4f}  \u2192  Target: {calc.effective_ratio:.4f}{capped_note}",
    )

    try:
        impact_chart = _build_impact_chart(calc)
        slide10.shapes.add_picture(impact_chart, Inches(0.3), Inches(1.2), width=Inches(7.0))
    except Exception:
        pass

    # Impact summary table with "Other" row
    impact_headers = ["Class", "Current", "New", "Change"]
    other_change = calc.other_increase_total
    other_sign = "+" if other_change >= 0 else ""
    impact_rows = [
        ["Farmland", f"${calc.model_current_farm_taxes:,.0f}",
         f"${calc.model_new_farm_taxes:,.0f}", f"-${calc.farm_savings_total:,.0f}"],
        ["Residential", f"${calc.model_current_res_taxes:,.0f}",
         f"${calc.model_new_res_taxes:,.0f}", f"+${calc.res_increase_total:,.0f}"],
        ["Commercial", f"${calc.model_current_com_taxes:,.0f}",
         f"${calc.model_new_com_taxes:,.0f}", f"+${calc.com_increase_total:,.0f}"],
        ["Industrial", f"${calc.model_current_ind_taxes:,.0f}",
         f"${calc.model_new_ind_taxes:,.0f}", f"+${calc.ind_increase_total:,.0f}"],
        ["Other", f"${calc.model_current_other_taxes:,.0f}",
         f"${calc.model_new_other_taxes:,.0f}", f"{other_sign}${other_change:,.0f}"],
        ["TOTAL", f"${calc.total_muni_taxes:,.0f}",
         f"${calc.total_muni_taxes:,.0f}", "$0"],
    ]
    _add_compact_table(slide10, impact_headers, impact_rows, Inches(7.5), Inches(1.3), Inches(5.5))

    # Per-household callout
    if calc.total_households > 0:
        txBox_hh = slide10.shapes.add_textbox(Inches(7.5), Inches(4.5), Inches(5.5), Inches(0.5))
        tf_hh = txBox_hh.text_frame
        tf_hh.word_wrap = True
        p_hh = tf_hh.paragraphs[0]
        p_hh.text = f"Residential impact: ~${calc.res_increase_per_household_month:,.2f}/month per household"
        p_hh.font.size = Pt(12)
        p_hh.font.bold = True
        p_hh.font.color.rgb = OFA_GREEN_LIGHT
        p_hh.alignment = PP_ALIGN.CENTER

    _add_logo(slide10)
    _add_footer(slide10, slide_number=11)

    # ══════════════════════════════════════════════════════════════════
    # SLIDE 11: Key Takeaway & The Ask
    # ══════════════════════════════════════════════════════════════════
    slide11 = prs.slides.add_slide(prs.slide_layouts[6])
    _add_green_header(slide11, "Key Takeaway")

    # Left column: Farm savings
    txBox_left = slide11.shapes.add_textbox(Inches(0.8), Inches(1.5), Inches(5.5), Inches(3.5))
    tf_l = txBox_left.text_frame
    tf_l.word_wrap = True

    p = tf_l.add_paragraph()
    p.text = "Farm Tax Savings"
    p.font.size = Pt(22)
    p.font.bold = True
    p.font.color.rgb = OFA_GREEN_LIGHT
    p.space_after = Pt(16)

    stats_left = [
        f"Total savings: ${calc.farm_savings_total:,.0f}",
        f"Per $100k CVA: ${calc.farm_savings_per_100k:,.2f}",
    ]
    for line in stats_left:
        p = tf_l.add_paragraph()
        p.text = line
        p.font.size = Pt(18)
        p.font.color.rgb = DARK
        p.space_after = Pt(8)

    # Right column: Impact on others
    txBox_right = slide11.shapes.add_textbox(Inches(7.0), Inches(1.5), Inches(5.5), Inches(3.5))
    tf_r = txBox_right.text_frame
    tf_r.word_wrap = True

    p = tf_r.add_paragraph()
    p.text = "Impact on Other Classes"
    p.font.size = Pt(22)
    p.font.bold = True
    p.font.color.rgb = PptxRGB(0x42, 0x42, 0x42)
    p.space_after = Pt(16)

    stats_right = [
        f"Residential: +${calc.res_increase_per_100k:,.2f} per $100k",
        f"Commercial: +${calc.com_increase_per_100k:,.2f} per $100k",
        f"Industrial: +${calc.ind_increase_per_100k:,.2f} per $100k",
    ]
    for line in stats_right:
        p = tf_r.add_paragraph()
        p.text = line
        p.font.size = Pt(16)
        p.font.color.rgb = DARK
        p.space_after = Pt(8)

    if calc.total_households > 0:
        txBox_hh = slide11.shapes.add_textbox(Inches(1), Inches(5.0), Inches(11), Inches(0.8))
        tf_hh = txBox_hh.text_frame
        p_hh = tf_hh.paragraphs[0]
        p_hh.text = (
            f"Cost to average household: ${calc.res_increase_per_household:,.2f}/year "
            f"(${calc.res_increase_per_household_month:,.2f}/month)"
        )
        p_hh.font.size = Pt(20)
        p_hh.font.bold = True
        p_hh.font.color.rgb = OFA_GREEN
        p_hh.alignment = PP_ALIGN.CENTER

    # Advocacy "ask" closing statement
    ask_y = 5.3 if calc.total_households <= 0 else 5.9
    txBox_ask = slide11.shapes.add_textbox(Inches(0.8), Inches(ask_y), Inches(11.5), Inches(0.6))
    tf_ask = txBox_ask.text_frame
    tf_ask.word_wrap = True
    p_ask = tf_ask.paragraphs[0]
    hh_clause = ""
    if calc.total_households > 0:
        hh_clause = f" while costing the average household just ${calc.res_increase_per_household_month:,.2f}/month"
    p_ask.text = (
        f"We respectfully request that Council consider reducing the farm property "
        f"tax ratio to {calc.effective_ratio:.4f}, saving farmland owners "
        f"${calc.farm_savings_total:,.0f}{hh_clause}."
    )
    p_ask.font.size = Pt(14)
    p_ask.font.italic = True
    p_ask.font.color.rgb = OFA_GREEN
    p_ask.alignment = PP_ALIGN.CENTER

    # Jurisdictional note
    if is_two_tier:
        jur_y = ask_y + 0.65
        txBox_jur = slide11.shapes.add_textbox(Inches(1), Inches(jur_y), Inches(11), Inches(0.4))
        tf_j = txBox_jur.text_frame
        p_j = tf_j.paragraphs[0]
        p_j.text = "Note: Tax ratios are set at the Upper-Tier (County/Region) level."
        p_j.font.size = Pt(11)
        p_j.font.italic = True
        p_j.font.color.rgb = PptxRGB(0xB7, 0x1C, 0x1C)

    _add_logo(slide11)
    _add_footer(slide11, slide_number=12)

    # ══════════════════════════════════════════════════════════════════
    # SLIDE 12: Thank You / Questions
    # ══════════════════════════════════════════════════════════════════
    slide12 = prs.slides.add_slide(prs.slide_layouts[6])
    bg12 = slide12.shapes.add_shape(
        1, Inches(0), Inches(0), Inches(13.333), Inches(7.5),
    )
    bg12.fill.solid()
    bg12.fill.fore_color.rgb = OFA_GREEN
    bg12.line.fill.background()

    txBox_ty = slide12.shapes.add_textbox(Inches(1), Inches(2.2), Inches(11), Inches(1.5))
    tf_ty = txBox_ty.text_frame
    p_ty = tf_ty.paragraphs[0]
    p_ty.text = "Thank You"
    p_ty.font.size = Pt(48)
    p_ty.font.bold = True
    p_ty.font.color.rgb = WHITE
    p_ty.alignment = PP_ALIGN.CENTER

    txBox_q = slide12.shapes.add_textbox(Inches(1), Inches(3.8), Inches(11), Inches(1))
    tf_q = txBox_q.text_frame
    p_q = tf_q.paragraphs[0]
    p_q.text = "Questions & Discussion"
    p_q.font.size = Pt(28)
    p_q.font.color.rgb = PptxRGB(0xC8, 0xE6, 0xC9)
    p_q.alignment = PP_ALIGN.CENTER

    txBox_src = slide12.shapes.add_textbox(Inches(1), Inches(5.5), Inches(11), Inches(0.8))
    tf_src = txBox_src.text_frame
    p_src = tf_src.paragraphs[0]
    p_src.text = (
        f"Data: Ontario Financial Information Return (FIR), {year_range}\n"
        f"Generated from OFA\u2019s farm and rural database"
    )
    p_src.font.size = Pt(14)
    p_src.font.color.rgb = PptxRGB(0xA5, 0xD6, 0xA7)
    p_src.alignment = PP_ALIGN.CENTER

    _add_logo(slide12, title_slide=True)

    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf









# ---------------------------------------------------------------------------
# Template Delegation Letter Generation
# ---------------------------------------------------------------------------

def _add_highlighted_placeholder(paragraph, text):
    """Add a yellow-highlighted, bold ALL CAPS placeholder to a paragraph."""
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_COLOR_INDEX
    r = paragraph.add_run(text)
    r.font.highlight_color = WD_COLOR_INDEX.YELLOW
    r.font.bold = True
    r.font.size = Pt(12)
    return r


def generate_delegation_letter(
    muni_name: str,
    upper_tier_name: str,
    is_lower_tier: bool,
    current_year: int,
    calc: RatioResult,
    burden_by_year: dict = None,
    tax_trends_by_year: dict = None,
    logo_bytes: bytes = None,
) -> io.BytesIO:
    """Generate a template delegation letter to the upper-tier/single-tier council.

    The letter requests a delegation to discuss the farm property tax ratio
    and is pre-populated with local data from the FIR analysis.

    All user-editable fields are highlighted in yellow ALL CAPS for easy
    identification (e.g., INSERT DATE, INSERT WARDEN'S NAME).

    Returns a BytesIO buffer containing the .docx file.
    """
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX

    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(12)
    style.paragraph_format.space_after = Pt(6)
    style.paragraph_format.line_spacing = 1.15

    # ── Logo (if provided, right-aligned at top) ──
    if logo_bytes:
        logo_para = doc.add_paragraph()
        logo_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        logo_para.add_run().add_picture(io.BytesIO(logo_bytes), width=Inches(1.5))

    # ── Jurisdictional note (for internal reference, not part of the letter) ──
    if is_lower_tier:
        note_para = doc.add_paragraph()
        r = note_para.add_run(
            f"\u26a0 INTERNAL NOTE: This letter is addressed to {upper_tier_name} because "
            f"farm property tax ratios are set at the upper-tier (county/region) level "
            f"in Ontario\u2019s two-tier municipal system. {muni_name} does not have the "
            f"authority to change the farm tax ratio. Delete this note before sending."
        )
        r.font.size = Pt(9)
        r.font.italic = True
        r.font.color.rgb = RGBColor(0xB7, 0x1C, 0x1C)
        r.font.highlight_color = WD_COLOR_INDEX.YELLOW
        doc.add_paragraph()

    # ── Date ──
    p_date = doc.add_paragraph()
    _add_highlighted_placeholder(p_date, "INSERT DATE")

    doc.add_paragraph()

    # ── Address block ──
    # Warden/Mayor line
    p_to = doc.add_paragraph()
    if is_lower_tier:
        # Two-tier: letter goes to the County/Region → addressed to Warden
        p_to.add_run("Warden ").bold = True
        _add_highlighted_placeholder(p_to, "INSERT WARDEN'S NAME")
        p_to.add_run("\n")
        p_to.add_run("and Members of Council\n").bold = True
        p_to.add_run(f"{upper_tier_name}\n")
        _add_highlighted_placeholder(p_to, "INSERT MUNICIPAL ADDRESS")
    else:
        # Single-tier: addressed to Mayor
        p_to.add_run("Mayor ").bold = True
        _add_highlighted_placeholder(p_to, "INSERT MAYOR'S NAME")
        p_to.add_run("\n")
        p_to.add_run("and Members of Council\n").bold = True
        p_to.add_run(f"{upper_tier_name}\n")
        _add_highlighted_placeholder(p_to, "INSERT MUNICIPAL ADDRESS")

    doc.add_paragraph()

    # ── Subject line ──
    p_subj = doc.add_paragraph()
    r = p_subj.add_run(
        f"Re: Request for Delegation \u2014 Farm Property Tax Ratio in {upper_tier_name}"
    )
    r.bold = True
    r.font.size = Pt(13)
    r.underline = True

    doc.add_paragraph()

    # ── Salutation ──
    p_sal = doc.add_paragraph()
    if is_lower_tier:
        p_sal.add_run("Dear Warden ")
        _add_highlighted_placeholder(p_sal, "INSERT WARDEN'S NAME")
        p_sal.add_run(" and Members of Council,")
    else:
        p_sal.add_run("Dear Mayor ")
        _add_highlighted_placeholder(p_sal, "INSERT MAYOR'S NAME")
        p_sal.add_run(" and Members of Council,")

    # ── Body ──

    # Paragraph 1: Introduction
    p1 = doc.add_paragraph()
    p1.add_run("On behalf of the ")
    _add_highlighted_placeholder(p1, "INSERT LOCAL OFA FEDERATION NAME")
    p1.add_run(
        f", I am writing to request the opportunity to appear as a delegation "
        f"before {upper_tier_name} Council to discuss the farm property tax ratio "
        f"and its impact on the agricultural community."
    )

    # Paragraph 2: Context on farm tax ratios
    doc.add_paragraph(
        "As you may know, Ontario municipalities have the authority to set the "
        "farm property tax ratio, which determines how farm properties are taxed "
        "relative to the residential rate. The provincial maximum ratio is 0.25, "
        "meaning farms can be taxed at a maximum of 25% of the residential rate. "
        "Many municipalities across Ontario have recognized the value of reducing "
        "this ratio to support local agriculture, reduce the cost of doing business "
        "for farmers, and help ensure the long-term viability of the agricultural "
        "sector in their communities."
    )

    # Paragraph 3: Local data — current situation
    ratio_pct = f"{calc.current_farm_ratio * 100:.2f}%"
    burden_text = f"{calc.current_burden:.1%}"

    local_para = (
        f"In {upper_tier_name}, the current farm property tax ratio is "
        f"{calc.current_farm_ratio:.4f} ({ratio_pct} of the residential rate), "
        f"and farmland currently accounts for {burden_text} of the total "
        f"municipal property tax levy."
    )

    # Add burden trend if available
    if burden_by_year:
        years = sorted(burden_by_year.keys())
        if len(years) >= 2:
            first_farm = burden_by_year[years[0]].get("farm", 0)
            last_farm = burden_by_year[years[-1]].get("farm", 0)
            delta = (last_farm - first_farm) * 100
            if delta > 0:
                local_para += (
                    f" Over the period {years[0]}\u2013{years[-1]}, the farm "
                    f"tax burden has increased by {delta:.1f} percentage points, "
                    f"meaning farmers are bearing a growing share of the municipal "
                    f"tax bill."
                )
    doc.add_paragraph(local_para)

    # Paragraph 4: Tax growth comparison
    if tax_trends_by_year:
        trend_years = sorted(tax_trends_by_year.keys())
        if len(trend_years) >= 2:
            first_d = tax_trends_by_year[trend_years[0]]
            last_d = tax_trends_by_year[trend_years[-1]]
            farm_first = first_d.get("farm", 0)
            farm_last = last_d.get("farm", 0)
            res_first = first_d.get("res", 0)
            res_last = last_d.get("res", 0)
            if farm_first > 0 and res_first > 0:
                farm_pct = ((farm_last - farm_first) / farm_first) * 100
                res_pct = ((res_last - res_first) / res_first) * 100
                doc.add_paragraph(
                    f"To put this in context, between {trend_years[0]} and "
                    f"{trend_years[-1]}, total farm property taxes in "
                    f"{upper_tier_name} grew by {farm_pct:+.1f}% (from "
                    f"${farm_first:,.0f} to ${farm_last:,.0f}), compared to "
                    f"{res_pct:+.1f}% growth for the residential class. "
                    f"This disproportionate increase places a significant "
                    f"financial burden on farm operations."
                )

    # Paragraph 5: Revenue-neutral framing — THE KEY ARGUMENT
    doc.add_paragraph(
        f"Importantly, a reduction in the farm tax ratio is entirely "
        f"revenue-neutral for the municipality \u2014 the total tax levy does not "
        f"change. Our analysis, based on Financial Information Return (FIR) data, "
        f"shows that adjusting the ratio to {calc.effective_ratio:.4f} would save "
        f"the farm sector ${calc.farm_savings_total:,.0f} in total, with the cost "
        f"distributed proportionally across all other property classes."
    )

    if calc.total_households > 0:
        doc.add_paragraph(
            f"For the average residential household in {upper_tier_name}, "
            f"this adjustment would cost approximately "
            f"${calc.res_increase_per_household:,.2f} per year \u2014 that is just "
            f"${calc.res_increase_per_household_month:,.2f} per month. We believe "
            f"this is a modest and manageable investment in the long-term health "
            f"of local agriculture."
        )

    # Paragraph 6: Why it matters
    doc.add_paragraph(
        "Agriculture is one of Ontario\u2019s most important economic sectors. "
        "Reducing the farm tax ratio sends a clear signal that this municipality "
        "values its farming community and recognizes the unique nature of "
        "farmland \u2014 which generates limited property tax revenue relative to its "
        "assessment value, yet provides essential food, environmental, and "
        "economic benefits to the broader community."
    )

    # Paragraph 7: The ask
    doc.add_paragraph(
        "We respectfully request the opportunity to present this analysis to "
        "Council in person. We would be happy to share a detailed, data-driven "
        "presentation on the local farm tax situation, answer any questions, and "
        "discuss how other Ontario municipalities have successfully implemented "
        "farm tax ratio reductions."
    )

    # Paragraph 8: Closing
    doc.add_paragraph(
        "We look forward to your response and are pleased to work with your "
        "office to schedule a convenient time for this delegation. Please do not "
        "hesitate to contact me if you require any additional information."
    )

    doc.add_paragraph()

    # ── Signature block ──
    doc.add_paragraph("Respectfully,")
    doc.add_paragraph()

    p_name = doc.add_paragraph()
    _add_highlighted_placeholder(p_name, "INSERT YOUR NAME")

    p_title = doc.add_paragraph()
    _add_highlighted_placeholder(p_title, "INSERT YOUR TITLE / POSITION")

    p_org = doc.add_paragraph()
    _add_highlighted_placeholder(p_org, "INSERT LOCAL OFA FEDERATION NAME")

    p_contact = doc.add_paragraph()
    _add_highlighted_placeholder(p_contact, "INSERT PHONE NUMBER AND EMAIL")

    # ── cc: line (if lower-tier, cc the local township clerk) ──
    if is_lower_tier:
        doc.add_paragraph()
        p_cc = doc.add_paragraph()
        p_cc.add_run("cc: ").bold = True
        p_cc.add_run("Clerk, ")
        p_cc.add_run(f"{muni_name}")

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf

