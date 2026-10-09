"""
ROMA 2027 Conference Briefing & PDF Report Generator
====================================================
Generates an executive, OFA-branded 2-page PDF briefing for any Ontario
municipality selected at the ROMA 2027 conference booth.

Includes:
- Fair Farm Tax redistribution analysis (0.15 target)
- OMPF $1B Restoration & OFA 3-Gate Rural model comparison
- Net Fiscal Position bottom line
- Historical FIR tax & grant metrics
- Lead capture logging & SMTP/mailto delivery
"""

from __future__ import annotations

import csv
import datetime
import email
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import io
import os
from pathlib import Path
import smtplib
import urllib.parse
from typing import Optional, Dict, Any, Tuple

from fpdf import FPDF
import pandas as pd


# Brand Palette
OFA_DARK_GREEN = (27, 94, 32)      # #1b5e20 - Primary header
OFA_MID_GREEN  = (46, 125, 50)     # #2e7d32 - Accents, borders
OFA_LIGHT_BG   = (241, 248, 241)   # #f1f8f1 - Soft card backgrounds
OFA_GOLD       = (230, 81, 0)      # #e65100 - Highlights
TEXT_DARK      = (33, 33, 33)      # Charcoal
TEXT_MUTED     = (117, 117, 117)   # Muted grey
LINE_GREY      = (220, 224, 220)   # Borders
ROW_ALT_GREY   = (248, 249, 250)   # Alternating row bg
BADGE_GREEN    = (46, 125, 50)
BADGE_RED      = (198, 40, 40)


def _clean_str(text: Any) -> str:
    """Sanitize strings for FPDF Helvetica (Latin-1 safe, no unhandled unicode)."""
    if text is None:
        return ""
    s = str(text)
    # Replace common unicode typographic characters
    replacements = {
        "—": "-",
        "–": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "•": "*",
        "·": "-",
        "≥": ">=",
        "≤": "<=",
        "±": "+/-",
        "…": "...",
        "\u202f": " ",
        "\xa0": " ",
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    # Filter to latin-1 encodable characters
    clean = []
    for char in s:
        try:
            char.encode("latin-1")
            clean.append(char)
        except UnicodeEncodeError:
            clean.append(" ")
    return "".join(clean)


class ROMABriefingPDF(FPDF):
    """Custom 2-page OFA ROMA 2027 briefing PDF."""

    def __init__(self, muni_name: str, county: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.muni_name = _clean_str(muni_name)
        self.county = _clean_str(county)
        self.set_auto_page_break(auto=True, margin=14)
        self.set_margins(12, 12, 12)

    def header(self):
        # Top banner on each page
        self.set_fill_color(*OFA_DARK_GREEN)
        self.rect(0, 0, 210, 8, "F")
        self.set_font("Helvetica", "B", 7)
        self.set_text_color(255, 255, 255)
        self.set_xy(12, 1.5)
        self.cell(90, 5, "ONTARIO FEDERATION OF AGRICULTURE  |  ROMA 2027 CONFERENCE BRIEFING")
        self.set_xy(108, 1.5)
        self.cell(90, 5, "FAIR FARM TAXES & FULLY FUNDED MUNICIPALITIES", align="R")
        self.set_y(12)

    def footer(self):
        self.set_y(-10)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*TEXT_MUTED)
        self.cell(
            0,
            6,
            f"Page {self.page_no()}/{{nb}}  |  OFA Farm Finance & Policy Research  |  Data Source: MMAH FIR 2010-2024 & MOF OMPF Guidelines",
            align="C",
        )

    def draw_badge(self, x: float, y: float, w: float, h: float, text: str, is_pass: bool):
        """Draw an executive colored pill badge."""
        fill = BADGE_GREEN if is_pass else BADGE_RED
        self.set_fill_color(*fill)
        self.rect(x, y, w, h, "F")
        self.set_font("Helvetica", "B", 7)
        self.set_text_color(255, 255, 255)
        self.set_xy(x, y + 0.5)
        self.cell(w, h - 1, text, align="C")

    def draw_kpi_card(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        title: str,
        main_value: str,
        subtitle: str,
        caption: str = "",
        accent_color: tuple = OFA_MID_GREEN,
    ):
        """Draw a structured KPI scorecard container."""
        # Background card
        self.set_fill_color(255, 255, 255)
        self.set_draw_color(*LINE_GREY)
        self.set_line_width(0.3)
        self.rect(x, y, w, h, "DF")

        # Top accent stripe
        self.set_fill_color(*accent_color)
        self.rect(x, y, w, 2.5, "F")

        # Title
        self.set_font("Helvetica", "B", 7.5)
        self.set_text_color(*TEXT_MUTED)
        self.set_xy(x + 2, y + 4)
        self.cell(w - 4, 4, _clean_str(title.upper()), align="L")

        # Main Value
        self.set_font("Helvetica", "B", 12.5)
        self.set_text_color(*OFA_DARK_GREEN)
        self.set_xy(x + 2, y + 8.5)
        self.cell(w - 4, 6.5, _clean_str(main_value), align="L")

        # Subtitle
        self.set_font("Helvetica", "B", 7.2)
        self.set_text_color(*TEXT_DARK)
        self.set_xy(x + 2, y + 15.5)
        self.cell(w - 4, 4, _clean_str(subtitle), align="L")

        # Caption (if any)
        if caption:
            self.set_font("Helvetica", "", 6.5)
            self.set_text_color(*TEXT_MUTED)
            self.set_xy(x + 2, y + 19.5)
            self.cell(w - 4, 3.5, _clean_str(caption), align="L")


def generate_roma_pdf(data: Dict[str, Any]) -> bytes:
    """
    Generate an executive 2-page PDF report for the given municipality data dictionary.
    Returns the PDF as raw bytes.
    """
    muni_name = _clean_str(data.get("municipality_name", "Municipality"))
    county = _clean_str(data.get("county", ""))
    type_desc = _clean_str(data.get("type_desc", "Rural Municipality"))
    sgc_code = _clean_str(data.get("sgc_code", ""))
    fir_code = _clean_str(data.get("fir_code", ""))
    latest_year = data.get("latest_year", 2024)

    pdf = ROMABriefingPDF(muni_name=muni_name, county=county)
    pdf.alias_nb_pages()

    # =========================================================================
    # PAGE 1: EXECUTIVE BRIEFING & KEY METRICS
    # =========================================================================
    pdf.add_page()

    # Header branding logo (if available)
    logo_path = Path(__file__).resolve().parent / "data" / "OFA_logo.png"
    if not logo_path.exists():
        # Fallback search path in project root
        root_logo = Path(__file__).resolve().parent.parent / "app" / "data" / "OFA_logo.png"
        if root_logo.exists():
            logo_path = root_logo

    if logo_path.exists():
        try:
            pdf.image(str(logo_path), x=12, y=11, w=32)
        except Exception:
            pass

    # Title block
    pdf.set_xy(48, 11)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*OFA_DARK_GREEN)
    pdf.cell(150, 6, "Fair Farm Taxes & Fully Funded Municipalities", new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(48)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*TEXT_DARK)
    pdf.cell(150, 5, f"Fiscal Briefing for {muni_name}", new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(48)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(*TEXT_MUTED)
    meta_txt = f"{type_desc}  |  County: {county or 'N/A'}  |  SGC: {sgc_code}  |  FIR: {fir_code}  |  Year: {latest_year}"
    pdf.cell(150, 4.5, _clean_str(meta_txt), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)

    # -------------------------------------------------------------------------
    # Executive Callout Card (Bottom Line)
    # -------------------------------------------------------------------------
    pdf.set_fill_color(*OFA_LIGHT_BG)
    pdf.set_draw_color(*OFA_MID_GREEN)
    pdf.set_line_width(0.5)
    callout_y = pdf.get_y()
    pdf.rect(12, callout_y, 186, 17, "DF")

    pdf.set_xy(15, callout_y + 2)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*OFA_DARK_GREEN)
    pdf.cell(180, 4, "EXECUTIVE SUMMARY - FISCAL BOTTOM LINE FOR COUNCIL", new_x="LMARGIN", new_y="NEXT")

    net_pos = data.get("net_position", 0.0)
    add_gated = data.get("additional_ompf_gated", 0.0)
    redist = data.get("redistribution_amount", 0.0)
    muni_eligible = data.get("muni_eligible", True)
    is_below = data.get("is_below_or_equal", False)

    if muni_eligible and is_below:
        summary_body = (
            f"{muni_name} already meets OFA's farm tax target (ratio <= 0.15). Under the proposed "
            f"$1B Rural-Targeted OMPF model, your municipality receives ${add_gated:,.0f}/year in NEW provincial "
            f"funding with zero required local tax shift, directly strengthening your local budget."
        )
    elif muni_eligible and net_pos >= 0:
        summary_body = (
            f"Under OFA's proposed $1B Rural-Targeted OMPF reform, {muni_name} gains ${add_gated:,.0f} in new annual "
            f"provincial funding. This fully covers the ${redist:,.0f} farm tax equity adjustment, delivering a "
            f"NET FISCAL SURPLUS OF +${net_pos:,.0f} ANNUALLY to support municipal infrastructure."
        )
    elif muni_eligible:
        cov_pct = (add_gated / redist * 100) if redist > 0 else 0
        gap = abs(net_pos)
        summary_body = (
            f"{muni_name} qualifies for rural OMPF funding (+${add_gated:,.0f}/yr), covering {cov_pct:.0f}% of "
            f"the proposed ${redist:,.0f} farm tax equity adjustment (remaining balance: ${gap:,.0f}/yr)."
        )
    else:
        summary_body = (
            f"{muni_name} is currently classified under urban metrics for core OMPF gating. "
            f"Farm tax relief modeled at ${redist:,.0f} under a 0.15 target ratio."
        )

    pdf.set_x(15)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(*TEXT_DARK)
    pdf.multi_cell(180, 4.2, _clean_str(summary_body))

    pdf.set_y(callout_y + 19)

    # -------------------------------------------------------------------------
    # 3-Column KPI Scorecard
    # -------------------------------------------------------------------------
    cur_ratio = data.get("current_ratio", 0.0)
    hh_month = data.get("res_increase_month", 0.0)
    unfettered_add = data.get("additional_ompf_unfettered", 0.0)
    bonus = data.get("bonus_gated", 0.0)

    card_y = pdf.get_y()
    card_w = 60
    card_h = 24

    # Card 1: Farm Tax Relief
    val_c1 = f"${redist:,.0f}" if redist > 0 else "Target Met"
    sub_c1 = f"Home Impact: ${hh_month:,.2f}/mo" if (redist > 0 and hh_month > 0) else f"Current Ratio: {cur_ratio:.4f}"
    cap_c1 = f"Target Ratio: 0.1500 (OFA ceiling)"
    pdf.draw_kpi_card(
        12, card_y, card_w, card_h,
        "1. Fair Farm Taxes",
        val_c1, sub_c1, cap_c1,
        OFA_MID_GREEN
    )

    # Card 2: Restored OMPF ($1B Status Quo)
    val_c2 = f"+${unfettered_add:,.0f}"
    sub_c2 = f"Current Grant: ${data.get('ompf_grant', 0.0):,.0f}"
    cap_c2 = "Proportional $1B scale-up"
    pdf.draw_kpi_card(
        75, card_y, card_w, card_h,
        "2. Restored OMPF ($1B)",
        val_c2, sub_c2, cap_c2,
        (21, 101, 192)  # Blue
    )

    # Card 3: Rural-Targeted Model (Gated)
    val_c3 = f"+${add_gated:,.0f}" if muni_eligible else "$0 (Filtered)"
    sub_c3 = f"Rural Bonus: +${bonus:,.0f}" if muni_eligible else "Urban Leakage Reform"
    cap_c3 = "Redirects $100M+ from urban"
    pdf.draw_kpi_card(
        138, card_y, card_w, card_h,
        "3. Rural-Gated Model",
        val_c3, sub_c3, cap_c3,
        OFA_GOLD
    )

    pdf.set_y(card_y + card_h + 3)

    # -------------------------------------------------------------------------
    # Section: Rural OMPF 3-Gate Eligibility
    # -------------------------------------------------------------------------
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*OFA_DARK_GREEN)
    pdf.cell(0, 5, "RURAL OMPF 3-GATE ELIGIBILITY ASSESSMENT", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 7.2)
    pdf.set_text_color(*TEXT_MUTED)
    pdf.cell(
        0,
        3.5,
        "OFA proposes restricting core OMPF grants to rural and northern communities, ending the transfer of rural tax dollars to large urban centres.",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(1)

    # Eligibility Table
    rscm = data.get("muni_rscm", 0.0)
    fam = data.get("muni_fam", 0.0)
    region = data.get("muni_region", "")
    is_northern = region in ["Northeast", "Northwest"]
    pass_rscm = rscm >= 0.25
    pass_fam = fam > 0.05

    tbl_y = pdf.get_y()
    col_w = [48, 48, 55, 35]

    # Header
    pdf.set_fill_color(*OFA_DARK_GREEN)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 7)
    headers = ["Eligibility Gate", "Threshold", f"{muni_name} Value", "Result"]
    for w, h in zip(col_w, headers):
        pdf.cell(w, 5, h, border=1, fill=True, align="C")
    pdf.ln()

    rows = [
        ("Northern Ontario", "Northeast or Northwest District", region or "Southern Ontario", "PASS" if is_northern else "NOT MET", is_northern),
        ("Rural & Small Community (RSCM)", "RSCM >= 25.0%", f"{rscm:.1%}", "PASS" if pass_rscm else "NOT MET", pass_rscm),
        ("Farm Area Measure (FAM)", "FAM > 5.0%", f"{fam:.1%}", "PASS" if pass_fam else "NOT MET", pass_fam),
    ]

    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*TEXT_DARK)
    for i, (g_name, thresh, val, res_txt, is_p) in enumerate(rows):
        pdf.set_fill_color(*(ROW_ALT_GREY if i % 2 == 1 else (255, 255, 255)))
        pdf.cell(col_w[0], 5, _clean_str(g_name), border=1, fill=True, align="L")
        pdf.cell(col_w[1], 5, _clean_str(thresh), border=1, fill=True, align="C")
        pdf.cell(col_w[2], 5, _clean_str(val), border=1, fill=True, align="C")

        # Result badge cell
        cx = pdf.get_x()
        cy = pdf.get_y()
        pdf.cell(col_w[3], 5, "", border=1, fill=True)
        pdf.draw_badge(cx + 6, cy + 0.8, col_w[3] - 12, 3.4, res_txt, is_p)
        pdf.set_xy(cx + col_w[3], cy)
        pdf.ln()

    pdf.ln(3)

    # -------------------------------------------------------------------------
    # Section: Revenue-Neutral Farm Tax Redistribution Table
    # -------------------------------------------------------------------------
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*OFA_DARK_GREEN)
    pdf.cell(0, 5, "REVENUE-NEUTRAL TAX SHIFT BREAKDOWN (TARGET RATIO = 0.15)", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 7.2)
    pdf.set_text_color(*TEXT_MUTED)
    pdf.cell(
        0,
        3.5,
        "Municipal tax levy remains 100% constant. Lowering the farm ratio modestly redistributes levy across all classes:",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(1)

    cb = data.get("class_breakdown", {})
    res_imp = cb.get("Residential", 0.0)
    com_imp = cb.get("Commercial", 0.0)
    ind_imp = cb.get("Industrial", 0.0)
    oth_imp = cb.get("Other", 0.0)

    t2_cols = [50, 45, 50, 41]
    pdf.set_fill_color(*OFA_DARK_GREEN)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 7)
    for w, h in zip(t2_cols, ["Property Class", "Annual Levy Impact", "Context / Household Impact", "Share of Shift"]):
        pdf.cell(w, 5, h, border=1, fill=True, align="C")
    pdf.ln()

    shift_rows = [
        ("Residential", f"+${res_imp:,.0f}", f"+${hh_month:,.2f}/month per home" if hh_month > 0 else "Minimal", f"{(res_imp/redist*100):.1f}%" if redist > 0 else "0%"),
        ("Commercial", f"+${com_imp:,.0f}", "Commercial rate adjustment", f"{(com_imp/redist*100):.1f}%" if redist > 0 else "0%"),
        ("Industrial", f"+${ind_imp:,.0f}", "Industrial rate adjustment", f"{(ind_imp/redist*100):.1f}%" if redist > 0 else "0%"),
        ("All Other Classes", f"+${oth_imp:,.0f}", "Pipelines, managed forest, etc.", f"{(oth_imp/redist*100):.1f}%" if redist > 0 else "0%"),
        ("Farmland Class (Relief)", f"-${redist:,.0f}", f"Ratio drops from {cur_ratio:.4f} to 0.1500", "100.0% Farm Relief"),
    ]

    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*TEXT_DARK)
    for i, (c_name, imp_txt, ctx_txt, pct_txt) in enumerate(shift_rows):
        is_total = (i == len(shift_rows) - 1)
        bg = (232, 245, 233) if is_total else (ROW_ALT_GREY if i % 2 == 1 else (255, 255, 255))
        pdf.set_fill_color(*bg)
        f_style = "B" if is_total else ""
        pdf.set_font("Helvetica", f_style, 7)
        pdf.cell(t2_cols[0], 4.8, _clean_str(c_name), border=1, fill=True, align="L")
        pdf.cell(t2_cols[1], 4.8, _clean_str(imp_txt), border=1, fill=True, align="R")
        pdf.cell(t2_cols[2], 4.8, _clean_str(ctx_txt), border=1, fill=True, align="C")
        pdf.cell(t2_cols[3], 4.8, _clean_str(pct_txt), border=1, fill=True, align="C")
        pdf.ln()

    # =========================================================================
    # PAGE 2: OMPF SCENARIOS, HISTORICAL TRENDS & ACTION PLAN
    # =========================================================================
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*OFA_DARK_GREEN)
    pdf.cell(0, 6, "PROVINCIAL OMPF SCENARIO COMPARISON", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(*TEXT_MUTED)
    pdf.cell(
        0,
        4,
        "Evaluating municipal grant allocations under three provincial funding models:",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(1)

    cur_ompf = data.get("ompf_grant", 0.0)
    unfet_grant = data.get("scenario_grant_unfettered", 0.0)
    gated_grant = data.get("scenario_grant_gated", 0.0)
    leakage = data.get("urban_leakage", 0.0)

    p2_cols = [52, 42, 46, 46]
    pdf.set_fill_color(*OFA_DARK_GREEN)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 7)
    for w, h in zip(p2_cols, ["Funding Model Scenario", "Province-Wide Pool", f"{muni_name} Grant", "Net Change vs Current"]):
        pdf.cell(w, 5, h, border=1, fill=True, align="C")
    pdf.ln()

    scen_rows = [
        ("Current Allocation (Status Quo)", "$497 Million", f"${cur_ompf:,.0f}", "$0 (Baseline)"),
        ("Scenario A: $1B Restored (Current Formula)", "$1.0 Billion", f"${unfet_grant:,.0f}", f"+${unfettered_add:,.0f}/year"),
        ("Scenario B: $1B Restored (Rural-Only Gate)", "$1.0 Billion (Rural-Gated)", f"${gated_grant:,.0f}", f"+${add_gated:,.0f}/year"),
    ]

    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*TEXT_DARK)
    for i, (s_name, pool_txt, m_txt, chg_txt) in enumerate(scen_rows):
        is_highlight = (i == 2)
        bg = (232, 245, 233) if is_highlight else (ROW_ALT_GREY if i % 2 == 1 else (255, 255, 255))
        pdf.set_fill_color(*bg)
        f_style = "B" if is_highlight else ""
        pdf.set_font("Helvetica", f_style, 7)
        pdf.cell(p2_cols[0], 5, _clean_str(s_name), border=1, fill=True, align="L")
        pdf.cell(p2_cols[1], 5, _clean_str(pool_txt), border=1, fill=True, align="C")
        pdf.cell(p2_cols[2], 5, _clean_str(m_txt), border=1, fill=True, align="R")
        pdf.cell(p2_cols[3], 5, _clean_str(chg_txt), border=1, fill=True, align="R")
        pdf.ln()

    pdf.set_font("Helvetica", "I", 6.8)
    pdf.set_text_color(*TEXT_MUTED)
    pdf.cell(
        0,
        4.5,
        f"*Rural-Only Gate redirects approx. ${leakage:,.0f} from 73 urban centres into rural and northern municipal grants.",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    # -------------------------------------------------------------------------
    # Section: Historical Assessment & Revenue Trends (Table)
    # -------------------------------------------------------------------------
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*OFA_DARK_GREEN)
    pdf.cell(0, 5, f"HISTORICAL ASSESSMENT & REVENUE PROFILE ({muni_name})", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 7.2)
    pdf.set_text_color(*TEXT_MUTED)
    pdf.cell(
        0,
        3.5,
        "Longitudinal data from Ontario Financial Information Returns (MMAH FIR Schedules 10 & 22):",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(1)

    hist_data = data.get("historical_trends", [])
    h_cols = [20, 34, 34, 26, 26, 26, 20]
    pdf.set_fill_color(*OFA_DARK_GREEN)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 6.8)
    h_headers = ["Year", "Farmland CVA", "Residential CVA", "Farm Ratio", "Farm Levy %", "OMPF Grant", "OMPF % Rev"]
    for w, h in zip(h_cols, h_headers):
        pdf.cell(w, 5, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 6.8)
    pdf.set_text_color(*TEXT_DARK)
    if hist_data:
        for idx, row in enumerate(hist_data[-8:]):  # up to 8 years
            bg = ROW_ALT_GREY if idx % 2 == 1 else (255, 255, 255)
            pdf.set_fill_color(*bg)
            pdf.cell(h_cols[0], 4.5, str(row.get("year", "")), border=1, fill=True, align="C")
            pdf.cell(h_cols[1], 4.5, f"${row.get('farmland_cva', 0):,.0f}", border=1, fill=True, align="R")
            pdf.cell(h_cols[2], 4.5, f"${row.get('residential_cva', 0):,.0f}", border=1, fill=True, align="R")
            pdf.cell(h_cols[3], 4.5, f"{row.get('farmland_tax_ratio', 0):.4f}", border=1, fill=True, align="C")
            pdf.cell(h_cols[4], 4.5, f"{row.get('farmland_share_of_taxes', 0)*100:.1f}%", border=1, fill=True, align="C")
            pdf.cell(h_cols[5], 4.5, f"${row.get('ompf_grant', 0):,.0f}", border=1, fill=True, align="R")
            dep = row.get("ompf_dependency", 0)
            pdf.cell(h_cols[6], 4.5, f"{dep*100:.1f}%" if dep else "N/A", border=1, fill=True, align="C")
            pdf.ln()
    else:
        pdf.cell(186, 6, "No longitudinal historical FIR data recorded for this SGC code.", border=1, align="C")
        pdf.ln()

    pdf.ln(3)

    # -------------------------------------------------------------------------
    # Section: Strategic Policy Briefing for ROMA 2027
    # -------------------------------------------------------------------------
    pdf.set_fill_color(255, 255, 255)
    pdf.set_draw_color(*LINE_GREY)
    pdf.rect(12, pdf.get_y(), 186, 42, "DF")

    box_y = pdf.get_y()
    pdf.set_xy(15, box_y + 2)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*OFA_DARK_GREEN)
    pdf.cell(180, 4, "POLICY ADVOCACY TAKEAWAYS FOR MUNICIPAL COUNCILS", new_x="LMARGIN", new_y="NEXT")

    points = [
        (
            "1. Protect Agricultural Competitiveness:",
            "Since the 2016 MPAC assessment freeze, farmland assessments have risen substantially faster than other property classes without consuming municipal services. Reducing the farm tax ratio to 0.15 levels the playing field for local farm businesses."
        ),
        (
            "2. Restore & Protect the OMPF:",
            "The Ontario Municipal Partnership Fund has lost significant purchasing power over the past decade. Restoring the fund to $1.0 Billion indexed to municipal inflation is essential for small, rural municipalities with extensive road networks."
        ),
        (
            "3. The Win-Win Policy Synergy:",
            "By pairing farm tax fairness with provincial OMPF restoration, rural councils do not have to choose between supporting local agriculture and maintaining municipal infrastructure. Provincial grant recovery more than covers the local farm tax shift."
        )
    ]

    for title, desc in points:
        pdf.set_x(15)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*OFA_MID_GREEN)
        pdf.cell(50, 3.8, _clean_str(title), align="L")
        pdf.set_font("Helvetica", "", 6.8)
        pdf.set_text_color(*TEXT_DARK)
        pdf.multi_cell(130, 3.8, _clean_str(desc))
        pdf.ln(0.5)

    pdf.set_y(box_y + 45)

    # Contact Block
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*OFA_DARK_GREEN)
    pdf.cell(0, 4, "ONTARIO FEDERATION OF AGRICULTURE (OFA)", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 6.8)
    pdf.set_text_color(*TEXT_MUTED)
    pdf.cell(
        0,
        3.5,
        "Contact: Ben Le Fort, Senior Policy & Farm Finance Analyst  |  Email: policy@ofa.on.ca  |  Web: ofa.on.ca  |  ROMA 2027 Booth",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    return bytes(pdf.output())


# =============================================================================
# LEAD CAPTURE & EMAIL DISPATCH SERVICES
# =============================================================================

LEADS_FILE = Path(__file__).resolve().parent.parent / "data" / "roma_2027_booth_leads.csv"


def save_booth_lead(
    municipality_name: str,
    sgc_code: str,
    recipient_name: str,
    recipient_email: str,
    recipient_role: str,
    net_position: float,
    status: str = "Queued",
    notes: str = ""
) -> bool:
    """Save captured conference lead details to persistent CSV."""
    LEADS_FILE.parent.mkdir(parents=True, exist_ok=True)
    is_new = not LEADS_FILE.exists()

    try:
        with open(LEADS_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow([
                    "Timestamp", "Municipality", "SGC_Code", "Name", "Email",
                    "Role", "Net_Fiscal_Position", "Status", "Notes"
                ])
            writer.writerow([
                datetime.datetime.now().isoformat(timespec="seconds"),
                municipality_name,
                sgc_code,
                recipient_name,
                recipient_email,
                recipient_role,
                f"${net_position:,.0f}",
                status,
                notes
            ])
        return True
    except Exception as e:
        print(f"Error saving lead: {e}")
        return False


def get_booth_leads_df() -> pd.DataFrame:
    """Read back all captured leads for the admin/export drawer."""
    if LEADS_FILE.exists():
        try:
            return pd.read_csv(LEADS_FILE)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def send_roma_report_email(
    to_email: str,
    recipient_name: str,
    municipality_name: str,
    pdf_bytes: bytes,
    net_position: float,
    smtp_config: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str]:
    """
    Send the PDF report to the specified email address via SMTP.
    If smtp_config is not provided, attempts to read from environment variables:
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
    """
    cfg = smtp_config or {}
    host = cfg.get("host") or os.environ.get("SMTP_HOST")
    port = cfg.get("port") or os.environ.get("SMTP_PORT", 587)
    user = cfg.get("user") or os.environ.get("SMTP_USER")
    password = cfg.get("password") or os.environ.get("SMTP_PASS")
    sender = cfg.get("sender") or os.environ.get("SMTP_FROM", user or "policy@ofa.on.ca")

    if not host or not user or not password:
        return (
            False,
            "SMTP server credentials not configured. Lead recorded in booth log and available for instant download."
        )

    try:
        port = int(port)
        msg = MIMEMultipart()
        display_name = recipient_name.strip() if recipient_name else "Councilor / Municipal Colleague"
        msg["From"] = f"Ontario Federation of Agriculture <{sender}>"
        msg["To"] = to_email
        msg["Subject"] = f"OFA ROMA 2027 Briefing — Fair Farm Taxes & OMPF for {municipality_name}"

        # HTML Body
        net_str = f"+${net_position:,.0f}" if net_position >= 0 else f"-${abs(net_position):,.0f}"
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #222;">
            <div style="background-color: #1b5e20; padding: 16px; border-radius: 4px; color: white;">
                <h2 style="margin: 0;">Ontario Federation of Agriculture</h2>
                <p style="margin: 4px 0 0 0; font-size: 14px;">ROMA 2027 Conference — Municipal Fiscal Briefing</p>
            </div>
            
            <p>Dear {display_name},</p>
            
            <p>Thank you for stopping by the <strong>Ontario Federation of Agriculture (OFA)</strong> booth at the <strong>ROMA 2027 Conference</strong>.</p>
            
            <p>Attached is your customized 2-page briefing document analyzing <strong>{municipality_name}</strong>'s fiscal profile, including:</p>
            <ul>
                <li><strong>Farm Tax Fairness:</strong> Local impacts of a 0.15 farmland tax ratio target and minimal household impacts.</li>
                <li><strong>Restored Provincial OMPF ($1 Billion):</strong> Grant recovery under OFA's 3-Gate Rural model.</li>
                <li><strong>Net Fiscal Bottom Line:</strong> Modeled annual net position: <strong>{net_str}/year</strong>.</li>
            </ul>
            
            <p>We look forward to continuing the conversation on how municipal leaders and agricultural producers can work together for strong rural communities.</p>
            
            <p style="margin-top: 24px;">Sincerely,</p>
            <p><strong>Ben Le Fort</strong><br>
            Senior Farm Policy & Financial Analyst<br>
            Ontario Federation of Agriculture (OFA)<br>
            <a href="mailto:policy@ofa.on.ca">policy@ofa.on.ca</a> | <a href="https://ofa.on.ca">ofa.on.ca</a></p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body_html, "html"))

        # Attach PDF
        clean_name = "".join(c for c in municipality_name if c.isalnum() or c in (" ", "_")).strip().replace(" ", "_")
        attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=f"OFA_ROMA2027_Briefing_{clean_name}.pdf"
        )
        msg.attach(attachment)

        # Send via SMTP
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)

        return (True, f"Briefing email successfully delivered to {to_email}!")

    except Exception as e:
        return (False, f"SMTP Error sending email: {str(e)}")


def generate_mailto_url(
    to_email: str,
    recipient_name: str,
    municipality_name: str,
    net_position: float
) -> str:
    """Generate a pre-filled mailto URL for local desktop email clients (Outlook, etc.)."""
    display_name = recipient_name.strip() if recipient_name else "Councilor / Staff"
    net_str = f"+${net_position:,.0f}" if net_position >= 0 else f"-${abs(net_position):,.0f}"
    
    subject = f"OFA ROMA 2027 Briefing — Fair Farm Taxes & OMPF for {municipality_name}"
    body = (
        f"Dear {display_name},\n\n"
        f"Thank you for stopping by the Ontario Federation of Agriculture (OFA) booth at ROMA 2027.\n\n"
        f"Attached is your customized briefing on Fair Farm Taxes & Restored OMPF for {municipality_name}.\n"
        f"Modeled Annual Net Fiscal Position: {net_str}/year.\n\n"
        f"Sincerely,\n"
        f"Ben Le Fort\n"
        f"Ontario Federation of Agriculture (OFA)\n"
        f"policy@ofa.on.ca\n"
    )
    
    params = {
        "subject": subject,
        "body": body
    }
    return f"mailto:{to_email}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"
