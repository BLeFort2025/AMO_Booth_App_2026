import sys
from pathlib import Path

# Ensure project root is on sys.path (needed for Streamlit Cloud page loading)
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import json
import re
import io
try:
    from docx import Document
except ImportError:
    Document = None
from app.smart_read import smart_read

# --- PAGE CONFIG ---
st.set_page_config(page_title="Growth & Risk Simulator", page_icon="🔮", layout="wide")

from app.utils import inject_standalone_mode, show_data_freshness
inject_standalone_mode()
show_data_freshness()


st.markdown("""
<style>
    .metric-card { background-color: var(--secondary-background-color); padding: 15px; border-radius: 8px; border-left: 4px solid #2e7d32; }
    .stMetric { text-align: center; }
</style>
""", unsafe_allow_html=True)

# --- 0. SESSION STATE INITIALIZATION ---
default_shocks = {
    "shock_revenue": 0,
    "shock_fert": 0,
    "shock_energy": 0,
    "shock_labor": 0,
    "shock_feed": 0,
    "shock_crop": 0,
    "shock_interest": 0,
    "proj_capex_shock": 0,
    "proj_tfw_reduction": 0,
    "tariff_pct": 0,
    "tariff_active": False,
    "tariff_country": "US",
    "tariff_commodity": "All Primary Agriculture"
}
for key, val in default_shocks.items():
    if key not in st.session_state:
        st.session_state[key] = val

def apply_preset(preset):
    # Reset all first
    for k in default_shocks:
        st.session_state[k] = default_shocks[k]
        
    if preset == "Trade War":
        st.session_state["tariff_active"] = True
        st.session_state["tariff_pct"] = 25
        st.session_state["tariff_country"] = "US"
        st.session_state["tariff_commodity"] = "All Primary Agriculture"
        st.toast("✅ US Trade War Scenario Applied (25% Tariff)", icon="🚨")
    elif preset == "Stagflation":
        st.session_state["shock_fert"] = 20
        st.session_state["shock_energy"] = 15
        st.session_state["shock_interest"] = 3
        st.session_state["proj_capex_shock"] = -10
        st.toast("✅ Stagflation Scenario Applied", icon="🚨")
    elif preset == "Labor Crisis":
        st.session_state["shock_labor"] = 20
        st.session_state["proj_tfw_reduction"] = 25
        st.toast("✅ Labor Crisis Scenario Applied", icon="🚨")
    elif preset == "Reset":
        st.toast("✅ Scenarios Reset", icon="🔄")

def generate_word_report(
    headline_text, scenario_desc, baseline_gdp, gap_m, final_dscr,
    horizon, region, name, fig=None, takeaways=None,
    # ── New parameters for executive briefing ──
    sim=None, projection=None, baseline_proj=None, mc_results=None,
    report_markdown=None, sector_params=None, proj_debt_ratio=None,
    proj_tfp_growth=None, baseline_tfp=None, active_shocks_list=None,
    is_pulse=False, tariff_active=False, tariff_detail="",
    tariff_commodity_breakdown=None, cost_commodity_breakdown=None,
):
    """Generate a professional executive briefing Word document."""
    if not Document: return None
    from docx.shared import Inches, Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.section import WD_ORIENT
    from datetime import datetime
    import os

    doc = Document()

    # ── Professional Document Formatting ──────────────────────────────
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)
    style.paragraph_format.space_after = Pt(6)
    style.paragraph_format.space_before = Pt(0)

    # Configure heading styles
    for level in range(1, 4):
        heading_style = doc.styles[f'Heading {level}']
        heading_style.font.name = 'Calibri'
        heading_style.font.color.rgb = RGBColor(0x1B, 0x5E, 0x20)  # Dark green

    # Set margins
    for section in doc.sections:
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.54)
        section.right_margin = Cm(2.54)

    # ── Helper: Convert markdown text to Word runs ────────────────────
    def add_markdown_paragraph(doc_or_cell, text, style_name=None):
        """Parse markdown bold/italic and convert to Word formatting."""
        import re
        # Clean escaped dollar signs (from rfmt)
        text = text.replace("\\$", "$")
        p = doc_or_cell.add_paragraph(style=style_name)
        # Split on **bold** markers
        parts = re.split(r'\*\*(.*?)\*\*', text)
        for i, part in enumerate(parts):
            if not part:
                continue
            run = p.add_run(part)
            if i % 2 == 1:  # Odd indices are the bold parts
                run.bold = True
        return p

    def add_bullet(doc_obj, text):
        """Add a bullet point with markdown bold support."""
        return add_markdown_paragraph(doc_obj, text, style_name='List Bullet')

    def fmt_doc(val):
        """Format monetary values for document."""
        if abs(val) >= 1_000_000_000:
            return f"${val/1_000_000_000:.2f}B"
        elif abs(val) >= 1_000_000:
            return f"${val/1_000_000:.1f}M"
        else:
            return f"${val:,.0f}"

    # ── OFA Logo & Header ─────────────────────────────────────────────
    logo_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'OFA_logo.png')
    if os.path.exists(logo_path):
        try:
            doc.add_picture(logo_path, width=Inches(1.8))
            # Left-align the logo
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.LEFT
        except Exception:
            pass

    # ── Title Block ───────────────────────────────────────────────────
    title = doc.add_heading(f"Farm Sector Shock Assessment — {region}", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Subtitle with date and classification
    date_str = datetime.now().strftime("%B %d, %Y")
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run_date = subtitle.add_run(f"Prepared: {date_str}  |  Ontario Federation of Agriculture")
    run_date.font.size = Pt(10)
    run_date.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    # Classification line
    classification = doc.add_paragraph()
    classification.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run_class = classification.add_run("FOR INTERNAL USE — Scenario Analysis, Not a Forecast")
    run_class.font.size = Pt(9)
    run_class.font.italic = True
    run_class.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    doc.add_paragraph()  # Spacer

    # ── Executive Summary ─────────────────────────────────────────────
    doc.add_heading("Executive Summary", level=1)
    clean_headline = headline_text.replace("**", "")
    p = doc.add_paragraph()
    r = p.add_run(clean_headline)
    r.bold = True
    r.font.size = Pt(12)

    # ── KPI Summary Table ─────────────────────────────────────────────
    doc.add_paragraph()  # Spacer
    kpi_data = []
    if sim:
        kpi_data.append(("Baseline Sector GDP", fmt_doc(sim.get('base_gdp', 0))))
        kpi_data.append(("Industry Revenue", fmt_doc(sim.get('base_output', 0))))

    # Cumulative GDP Impact
    abs_gap = abs(gap_m)
    if abs_gap >= 1000:
        formatted_gap = f"${abs_gap / 1000:,.2f}B"
    else:
        formatted_gap = f"${abs_gap:,.0f}M"
    sign = "−" if gap_m < 0 else "+"
    kpi_data.append((f"Farm Sector GDP Impact ({horizon}-Year Cumulative)", f"{sign}{formatted_gap}"))

    if sim and sim.get('macro_gdp', 0) != 0:
        macro_label = "Supply Chain Ripple Effects (Total GDP Impact)"
        sign_macro = "−" if sim['macro_gdp'] < 0 else "+"
        kpi_data.append((macro_label, f"{sign_macro}{fmt_doc(abs(sim['macro_gdp']))}"))

    if sim and sim.get('macro_jobs', 0) != 0:
        jobs_label = "Supply Chain Ripple Effects (Jobs at Risk)" if sim['macro_jobs'] < 0 else "Supply Chain Ripple Effects (Jobs Supported)"
        kpi_data.append((jobs_label, f"{abs(int(sim['macro_jobs'])):,}"))

    kpi_data.append(("Projection Horizon", f"{horizon} years"))
    kpi_data.append(("Representative Farm", name))

    if kpi_data:
        table = doc.add_table(rows=len(kpi_data), cols=2, style='Light Shading Accent 3')
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, (label, value) in enumerate(kpi_data):
            row = table.rows[i]
            row.cells[0].text = label
            row.cells[1].text = str(value)
            # Bold the value column
            for paragraph in row.cells[1].paragraphs:
                for run in paragraph.runs:
                    run.bold = True

    doc.add_paragraph()  # Spacer

    # ── Chart ─────────────────────────────────────────────────────────
    if fig:
        try:
            doc.add_picture(fig, width=Inches(6.0))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception:
            pass

    # ── Scenario Overview ─────────────────────────────────────────────
    doc.add_heading("Scenario Overview", level=1)

    region_adj = "national" if region == "Canada" else "provincial"
    if sim:
        add_markdown_paragraph(doc,
            f"This analysis examines {name} in {region} over a "
            f"{horizon}-year projection horizon. The sector currently generates "
            f"approximately {fmt_doc(sim.get('base_output', 0))} in annual output, contributing "
            f"{fmt_doc(sim.get('base_gdp', 0))} to {region_adj} GDP "
            f"(a value-added share of {sim.get('margin_pct', 0):.1%})."
        )

    if scenario_desc:
        add_markdown_paragraph(doc, "Scenario conditions tested:")
        for shock in scenario_desc:
            # Strip markdown for clean Word formatting
            clean_shock = shock.replace("**", "")
            doc.add_paragraph(clean_shock, style='List Bullet')

        if tariff_active and tariff_detail:
            p = doc.add_paragraph()
            r = p.add_run(f"Trade shock: {tariff_detail.replace('**', '')}")
            r.italic = True
            r.font.size = Pt(10)

            doc.add_heading("Who actually pays a tariff?", level=2)
            _buyer_str = f"{tariff_country} buyers" if tariff_country else "Foreign buyers"
            add_markdown_paragraph(doc,
                f"History shows that {_buyer_str} and Canadian sellers split the cost. "
                f"Based on empirical trade data, the model assumes Canadian farmers are forced to "
                f"'absorb' a specific percentage of the tariff cost, rather than the naive assumption of 100%."
            )
            doc.add_paragraph("Amiti, Redding & Weinstein (2019, JEP) and Fajgelbaum et al. (2020, QJE) established that importing consumers typically bear the vast majority of tariff costs.", style='List Bullet')
            doc.add_paragraph("Vyn & Rude (2020, CJAE) confirmed that during the 2019 China canola ban, the Canadian exporter absorption was similarly muted.", style='List Bullet')
            add_markdown_paragraph(doc,
                "Based on these peer-reviewed benchmarks and rigorous empirical literature, the model applies commodity-specific "
                "absorption (pass-through) rates ranging from 5% (for supply-managed sectors) up to 90% (for highly rigid global commodities like Barley). "
                "This ensures the tariff impact is historically calibrated, highly realistic, and defensible."
            )

            doc.add_heading("Export Exposure Methodology", level=2)
            add_markdown_paragraph(doc,
                f"Furthermore, the simulator mathematically isolates the specific volume of product at risk. "
                f"A {st.session_state.tariff_pct}% tariff does not automatically apply to a farmer's total gross revenue; "
                f"it only applies to the specific fraction of production exposed to the tariff—either through direct exports or domestic market contagion."
            )
            doc.add_paragraph("Export Intensity: The fraction of total production that is actually exported globally (e.g., ~90% for Canola, ~50% for Cattle).", style='List Bullet')
            doc.add_paragraph(f"Market Share: The exact percentage of those exports destined for the country imposing the tariff (e.g., 75% of cattle exports go to the US, but 40% of Dry Peas go to China).", style='List Bullet')
            doc.add_paragraph("The Domino Effect: For highly integrated continental markets, a closed border causes surplus product to back up into the Canadian market, crashing local prices even for goods sold domestically.", style='List Bullet')
            add_markdown_paragraph(doc,
                "By combining Export Intensity, Market Share, and The Domino Effect, the simulator calculates a realistic 'Exposure Percentage'. This prevents the model from generating artificially catastrophic numbers by only penalizing the share of revenue actually at risk."
            )
            
            if tariff_commodity_breakdown:
                doc.add_heading("Commodity-Level Tariff Exposure", level=2)
                add_markdown_paragraph(doc,
                    "The national-level farm cash receipts data reveals uneven exposure across agricultural commodities. "
                    "The table below isolates the specific dollar impact for each major commodity group after accounting for export intensity, market share, and absorption rates."
                )
                
                doc.add_heading("Winners & Losers", level=3)
                p = add_markdown_paragraph(doc,
                    "Livestock sectors (Cattle and Hogs) bear almost half the financial damage due to their deep integration with the US market and the threat of domestic price crashes. "
                    "Conversely, major crops like Wheat and Canola Seed are globally priced and largely insulated from a US-specific tariff. "
                    "Supply-managed sectors (Dairy, Poultry) see virtually zero impact due to their domestic focus and Tariff-Rate Quota (TRQ) protections."
                )
                p.style = 'Intense Quote'

                
                _sorted = sorted(tariff_commodity_breakdown, key=lambda x: abs(x['dollar_impact']), reverse=True)
                table = doc.add_table(rows=1, cols=4)
                table.style = 'Light Shading Accent 1'
                hdr_cells = table.rows[0].cells
                hdr_cells[0].text = 'Commodity'
                hdr_cells[1].text = 'Production Revenue'
                hdr_cells[2].text = 'Total Exposure'
                hdr_cells[3].text = 'Est. $ Impact'
                
                for _item in _sorted:
                    row_cells = table.add_row().cells
                    _sm_tag = " (SM)" if _item['sm_shielded'] and "(SM)" not in _item['commodity'] else ""
                    row_cells[0].text = _item['commodity'] + _sm_tag
                    row_cells[1].text = f"${_item['fcr_revenue']/1e9:,.1f}B"
                    row_cells[2].text = f"{_item['total_exposure']:.1%}"
                    row_cells[3].text = f"${_item['dollar_impact']/1e6:,.1f}M"
                    
                doc.add_paragraph()
                p = doc.add_paragraph("Note: (SM) denotes Supply-Managed sectors which are largely shielded by Tariff-Rate Quotas.")
                p.style = 'Intense Quote'
                
                doc.add_heading("Note on Revenue Calculation", level=3)
                p = add_markdown_paragraph(doc,
                    "Why do the commodity losses differ from the total industry impact? "
                    "The commodity total represents the direct hit to the sale of physical crops and livestock. "
                    "The larger industry figure includes the broader ripple effect on secondary farm revenues, "
                    "such as custom work, land rent, and inter-farm sales, which decline in tandem with commodity prices."
                )
                p.style = 'Intense Quote'

            if cost_commodity_breakdown:
                doc.add_heading("Cost Shock Exposure by Commodity", level=2)
                add_markdown_paragraph(doc,
                    "How input cost spikes distribute across Canada's agricultural sectors based on Census expense structures."
                )
                
                doc.add_heading("Winners & Losers", level=3)
                p = add_markdown_paragraph(doc,
                    "Different farm types have vastly different cost structures. Greenhouses face disproportionate exposure to energy and labor shocks, "
                    "while grain farms are heavily penalized by fertilizer spikes. The table below isolates the dollar impact across all major commodity groups."
                )
                p.style = 'Intense Quote'
                
                _sorted_costs = sorted(cost_commodity_breakdown, key=lambda x: abs(x['dollar_impact']), reverse=True)
                table = doc.add_table(rows=1, cols=3)
                table.style = 'Light Shading Accent 1'
                hdr_cells = table.rows[0].cells
                hdr_cells[0].text = 'Commodity'
                hdr_cells[1].text = 'Total Expenses Base'
                hdr_cells[2].text = 'Est. Cost Increase'
                
                for _item in _sorted_costs:
                    row_cells = table.add_row().cells
                    row_cells[0].text = _item['commodity']
                    row_cells[1].text = f"${_item['total_expenses']/1e9:,.1f}B"
                    row_cells[2].text = f"${_item['dollar_impact']/1e6:,.1f}M"


    if proj_debt_ratio is not None:
        add_markdown_paragraph(doc,
            f"The analysis assumes a debt-to-asset ratio of {proj_debt_ratio:.0%} "
            f"(Regional average: ~18-22%)."
        )

    # Shock duration note
    if scenario_desc:
        if is_pulse:
            add_markdown_paragraph(doc,
                "Shock Duration: One-Time (Pulse). Cost and investment shocks "
                "apply only in Year 1, then revert to baseline. This models transient "
                "events like a single-season drought or temporary supply disruption."
            )
        else:
            add_markdown_paragraph(doc,
                "Shock Duration: Persistent (Structural). All shocks continue "
                "every year of the projection. This models permanent changes like a "
                "new tariff regime, carbon tax, or structural shift in input costs."
            )
    elif not scenario_desc:
        baseline_tfp_val = baseline_tfp if baseline_tfp else 1.0
        add_markdown_paragraph(doc,
            f"No shocks applied — this report shows the baseline growth trajectory "
            f"at {baseline_tfp_val:.1f}% annual productivity growth."
        )

    # ── Immediate Impact (Year 1) ─────────────────────────────────────
    doc.add_heading("Immediate Impact (Year 1)", level=1)

    if sim:
        total_shock_val = sum(sim.get('hits', {}).values())
        shock_revenue_val = sim.get('final_output', 0) - sim.get('base_output', 0)

        if abs(shock_revenue_val) > 0:
            rev_word = "boost" if shock_revenue_val > 0 else "reduction"
            add_markdown_paragraph(doc,
                f"The market price change produces a {fmt_doc(abs(shock_revenue_val))} "
                f"revenue {rev_word}."
            )

        if total_shock_val > 0:
            biggest_cost = max(sim['hits'].items(), key=lambda x: x[1])
            add_markdown_paragraph(doc,
                f"Operating costs increase by {fmt_doc(total_shock_val)}, "
                f"driven primarily by {biggest_cost[0]} ({fmt_doc(biggest_cost[1])})."
            )

        gdp_y0_change = sim.get('final_gdp', 0) - sim.get('base_gdp', 0)
        if gdp_y0_change < 0:
            add_markdown_paragraph(doc,
                f"After accounting for all shocks, sector GDP falls by "
                f"{fmt_doc(abs(gdp_y0_change))} ({gdp_y0_change/sim.get('base_gdp', 1):.1%}), "
                f"leaving the sector with {fmt_doc(sim.get('final_gdp', 0))} in value added."
            )
        elif gdp_y0_change > 0:
            add_markdown_paragraph(doc,
                f"Net sector GDP increases by {fmt_doc(gdp_y0_change)} "
                f"({gdp_y0_change/sim.get('base_gdp', 1):+.1%})."
            )

        if sim.get('profit_squeeze', 0) > 0:
            add_markdown_paragraph(doc,
                f"Additionally, {fmt_doc(sim['profit_squeeze'])} in sector profits "
                f"is redistributed to labor and lenders through wage and interest increases. "
                f"While this does not reduce GDP, it squeezes farm profitability and cash flow."
            )

    # ── Multi-Year Outlook ────────────────────────────────────────────
    doc.add_heading(f"{horizon}-Year Outlook", level=1)

    if projection and baseline_proj:
        final_yr = projection[-1]
        bl_final = baseline_proj[-1]
        final_gdp_gap = final_yr["gdp"] - bl_final["gdp"]
        gap_pct = (final_yr["gdp"] / bl_final["gdp"] - 1) * 100 if bl_final["gdp"] > 0 else 0
        cumulative_gap = sum(p["gdp"] - baseline_proj[i]["gdp"] for i, p in enumerate(projection))

        if abs(final_gdp_gap) < 1_000_000:
            add_markdown_paragraph(doc,
                f"Over {horizon} years, the scenario trajectory closely tracks the baseline. "
                f"The sector's productive capacity remains stable."
            )
        elif final_gdp_gap > 0:
            add_markdown_paragraph(doc,
                f"Over {horizon} years, the scenario produces {fmt_doc(abs(final_gdp_gap))} "
                f"more Direct Farm GDP annually by Year {horizon} compared to the baseline "
                f"({gap_pct:+.1f}%). Cumulatively, the sector gains an additional "
                f"{fmt_doc(abs(cumulative_gap))} in Direct Farm GDP over the full period."
            )
        else:
            p = add_markdown_paragraph(doc,
                f"Over {horizon} years, the shock erodes Direct Farm GDP by "
                f"{fmt_doc(abs(final_gdp_gap))} annually by Year {horizon} "
                f"({gap_pct:+.1f}% vs baseline). The cumulative Direct Farm GDP loss over the "
                f"full period is {fmt_doc(abs(cumulative_gap))}."
            )
            # Add context for Trade Diversion if gap shrinks relative to Year 1
            y1_gap = projection[1]["gdp"] - baseline_proj[1]["gdp"] if len(projection) > 1 else 0
            if tariff_active and y1_gap < 0 and final_gdp_gap > y1_gap:
                add_markdown_paragraph(doc,
                    f"Note that the annual GDP gap is smaller in Year {horizon} "
                    f"({fmt_doc(abs(final_gdp_gap))}) than in Year 1 ({fmt_doc(abs(y1_gap))}). "
                    f"This reflects trade diversion: as Canadian agriculture loses access to "
                    f"the {tariff_country} market due to tariffs, the model assumes exporters gradually find "
                    f"alternative global markets over time, absorbing some of the lost volume."
                )

        # Capital dynamics
        cap_change_pct = (final_yr['capital_stock'] / projection[0]['capital_stock'] - 1) * 100
        if abs(cap_change_pct) > 0.5:
            cap_word = "growth" if cap_change_pct > 0 else "erosion"
            msg = (
                f"The sector's capital stock (land, machinery, buildings) shows "
                f"{cap_change_pct:+.1f}% net {cap_word} over the period. "
            )
            if cap_change_pct < -2:
                msg += (
                    "Declining capital stock means farms are not replacing depreciated equipment "
                    "and infrastructure — a warning sign for long-term productive capacity."
                )
            elif cap_change_pct > 2:
                msg += (
                    "This reflects healthy reinvestment in farm infrastructure, "
                    "supporting future output growth."
                )
            else:
                msg += "Capital is roughly maintained at replacement levels."
            add_markdown_paragraph(doc, msg)

    # ── Year-by-Year Trajectory Table ─────────────────────────────────
    if projection and baseline_proj:
        doc.add_heading("Year-by-Year Detail", level=2)
        tbl_headers = ["Year", "Output ($B)", "GDP ($B)", "GDP Impact ($M)"]
        table = doc.add_table(rows=len(projection) + 1, cols=len(tbl_headers), style='Light Shading Accent 3')
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        # Header row
        for j, header in enumerate(tbl_headers):
            cell = table.rows[0].cells[j]
            cell.text = header
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.bold = True
                    run.font.size = Pt(9)

        # Data rows
        for i, p in enumerate(projection):
            bl = baseline_proj[i]
            gap_val = (p['gdp'] - bl['gdp']) / 1e6

            row_data = [
                f"Year {p['year']}",
                f"{p['output']/1e9:.2f}",
                f"{p['gdp']/1e9:.2f}",
                f"{gap_val:+,.0f}",
            ]
            for j, val in enumerate(row_data):
                cell = table.rows[i + 1].cells[j]
                cell.text = val
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(9)
                        # Color the gap column
                        if j == 3 and gap_val < -0.5:
                            run.font.color.rgb = RGBColor(0xC6, 0x28, 0x28)
                        elif j == 3 and gap_val > 0.5:
                            run.font.color.rgb = RGBColor(0x2E, 0x7D, 0x32)

    # ── Uncertainty Analysis ──────────────────────────────────────────
    if mc_results:
        doc.add_heading("Uncertainty Analysis", level=1)

        mc_spread_gdp = mc_results.get("final_gdp_p90", 0) - mc_results.get("final_gdp_p10", 0)
        mc_mid_gdp = (mc_results.get("final_gdp_p90", 0) + mc_results.get("final_gdp_p10", 0)) / 2
        mc_spread_pct = (mc_spread_gdp / mc_mid_gdp * 100) if mc_mid_gdp > 0 else 0

        add_markdown_paragraph(doc,
            f"The uncertainty bands represent the range of outcomes that could realistically occur. "
            f"{mc_results.get('n_runs', 200)} simulations were run, each with slightly different "
            f"assumptions about productivity growth, input costs, interest rates, and investment levels."
        )

        add_markdown_paragraph(doc,
            f"By Year {horizon}, there is an 80% probability that sector GDP lands between "
            f"{fmt_doc(mc_results.get('final_gdp_p10', 0))} and {fmt_doc(mc_results.get('final_gdp_p90', 0))} "
            f"— a spread of {fmt_doc(mc_spread_gdp)} ({mc_spread_pct:.1f}% of the midpoint)."
        )

        if mc_spread_pct < 3:
            add_markdown_paragraph(doc,
                "This is a narrow range, suggesting the projection is relatively robust "
                "to parameter uncertainty."
            )
        elif mc_spread_pct < 8:
            add_markdown_paragraph(doc,
                "This is a moderate range, typical for multi-year agricultural projections. "
                "The directional conclusions are reliable, but precise dollar values should "
                "be interpreted as estimates."
            )
        else:
            add_markdown_paragraph(doc,
                "This is a wide range, indicating high sensitivity to underlying assumptions. "
                "Decisions should consider the full range of outcomes rather than relying "
                "on any single point estimate."
            )

    # ── Key Takeaways ─────────────────────────────────────────────────
    if takeaways:
        doc.add_heading("Key Takeaways", level=1)
        for t in takeaways:
            clean_t = t.replace("**", "").replace("\\$", "$").replace("\\", "")
            doc.add_paragraph(clean_t, style='List Bullet')

    # ── Methodology Note ──────────────────────────────────────────────
    doc.add_heading("Technical Appendix", level=1)
    add_markdown_paragraph(doc,
        "This analysis uses Statistics Canada Input-Output multiplier data (Supply-Use Tables) "
        "to estimate the economic impact of user-defined shocks on Canadian agriculture. "
        "Farm cost structures are derived from the Census of Agriculture. "
        "The multi-year projection uses a Cobb-Douglas production function with "
        "sector-specific capital elasticity and depreciation parameters calibrated from "
        "AAFC, FCC, and CAHRC research."
    )
    add_markdown_paragraph(doc,
        f"Uncertainty bands are generated from {mc_results.get('n_runs', 200) if mc_results else 200} "
        f"Monte Carlo simulations with correlated macroeconomic shocks "
        f"(Cholesky decomposition covariance matrix). The analysis uses conservative "
        f"Type I multipliers (direct + indirect) to calculate supply chain impacts, "
        f"intentionally excluding induced household effects to ensure maximum methodological defensibility."
    )

    # ── Assumptions & Limitations ─────────────────────────────────────
    doc.add_heading("Assumptions & Limitations", level=1)
    assumptions = [
        f"Representative farm: {name}; Sector archetype: {sector_params.get('label', 'Mixed') if sector_params else 'Mixed'}",
        f"Debt-to-asset ratio: {proj_debt_ratio:.0%}" if proj_debt_ratio else "Debt-to-asset ratio: ~22% (Canadian average)",
        f"TFP growth: {proj_tfp_growth:.1f}%/yr" if proj_tfp_growth is not None else "TFP growth: 1.0%/yr",
        "The model assumes standard economic rules where farmers cannot instantly change their operations — actual impacts may be lower if producers substitute away from expensive inputs",
        "This is a simulation, not a forecast. Results depend on the accuracy of assumed coefficients and the persistence of modeled shocks",
        "Balance sheet data: StatCan Tables 32-10-0051, 32-10-0052, 32-10-0056",
        "Not modeled: capacity utilization weighting and cross-sector feed loops (e.g., cheap grain benefiting livestock margins)",
    ]
    for a in assumptions:
        p = doc.add_paragraph(a, style='List Bullet')
        for run in p.runs:
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    # ── Footer / Page Numbers ─────────────────────────────────────────
    for section in doc.sections:
        footer = section.footer
        footer.is_linked_to_previous = False
        p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("Ontario Federation of Agriculture  |  Farm Finance Dashboard  |  Scenario Analysis Tool")
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# --- 1. DATA LOADERS ---
@st.cache_data(max_entries=3, ttl=1800)
def load_expense_profiles():
    path = Path("data/derived/farm_expense_profiles.json")
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {}

expense_profiles = load_expense_profiles()

@st.cache_data(max_entries=3, ttl=1800)
def load_capex_baseline(geo="Canada"):
    """Load CapEx baseline from derived data, filtered by geography.
    Falls back to Canada if the selected geo is not available."""
    path = Path("data/derived/basket_capex.csv")
    if path.exists():
        df = smart_read(path)
        row = df[(df["basket_key"] == "primary_agriculture") & (df["geo"] == geo)]
        if row.empty:
            row = df[(df["basket_key"] == "primary_agriculture") & (df["geo"] == "Canada")]
        if not row.empty:
            return {
                "total_capex_M": row.iloc[0]["total_capex_M"],  # millions
                "construction_share": row.iloc[0]["construction_share"],
                "machinery_share": row.iloc[0]["machinery_share"],
                "data_year": int(row.iloc[0]["data_year"]),
                "geo": row.iloc[0]["geo"],
            }
    return None  # fallback to estimation

@st.cache_data(max_entries=3, ttl=1800)
def load_financial_health():
    """Load farm financial health metrics (Phase 2 integration)."""
    path = Path("data/derived/farm_financial_health.csv")
    if path.exists():
        return smart_read(path)
    return None

@st.cache_data(max_entries=3, ttl=1800)
def load_labor_metrics():
    """Load province-specific labor metrics (TFW dependency, vacancy rates)."""
    path = Path("data/derived/labor_metrics.csv")
    if path.exists():
        return smart_read(path)
    return None

financial_health_df = load_financial_health()
labor_metrics_df = load_labor_metrics()

@st.cache_data(max_entries=3, ttl=1800)
def load_national_fcr():
    """Load national Farm Cash Receipts for commodity-level tariff impact."""
    path = Path("data/latest/32-10-0045-01.csv")
    if path.exists():
        return smart_read(path)
    return None

national_fcr_df = load_national_fcr()

# Exact mapping from TARIFF_CONFIG keys to StatCan 32-10-0045 receipt types
TARIFF_FCR_MAP = {
    "Live Cattle": ["Cattle [1111111]", "Calves [1111112]"],
    "Hogs / Pork": ["Hogs [111121]"],
    "Wheat": ["Wheat (except durum wheat) [1121111]", "Durum wheat [112111211]"],
    "Canola (Seed)": ["Canola (including rapeseed) [113111]"],
    "Dairy (SM)": ["Unprocessed milk from bovine [11612111]"],
    "Poultry (SM)": ["Chickens for meat [11113131]", "Turkeys for meat [111132211]", "Eggs in shell [116111]"],
    "Dry Peas": ["Dry peas [114314]"],
    "Lentils": ["Lentils [114312]"],
    "Chickpeas": ["Chickpeas [114311]"],
    "Soybeans": ["Soybeans [1151211]"],
    "Barley": ["Barley [1151141]"],
    "Oats": ["Oats [115113111]"],
    "Corn (Grain)": ["Corn for grain [1151111]"],
    "Flaxseed": ["Flaxseed [115122111]"],
    "Dry Beans": ["Dry beans [114313]"],
    "Potatoes (Fresh)": ["Fresh potatoes [114211]"],
}

# Import IO Engine
try:
    from scripts.io_multipliers_engine import (
        get_actual_output, 
        available_years, 
        industries_for_basket,
        load_multipliers
    )
    ENGINE_AVAILABLE = True
except ImportError:
    ENGINE_AVAILABLE = False

# --- 2. THE PROXY BRIDGE ---
# Maps Census NAICS codes to IO join_codes for multiplier lookups.
# IMPORTANT: Values must be the NORMALIZED join_codes as they appear in the
# multiplier data (no "BS" prefix). See normalize_code_simple() in the engine.
PROXY_MAP = {
    # Parent-level
    "111":    "111A",     # Crop production -> Crops
    "112":    "112A",     # Animal production -> Animals
    # Standard 4-digit
    "1111":   "111A",     # Oilseed & Grain -> Crops
    "1112":   "111A",     # Veg & Melon -> Crops
    "1113":   "111A",     # Fruit -> Crops
    "1119":   "111A",     # Other Crops -> Crops
    "1114":   "1114",     # Greenhouse -> Greenhouse
    "1121":   "112A",     # Beef & Dairy -> Animals
    "1122":   "112A",     # Hogs -> Animals
    "1123":   "112A",     # Poultry -> Animals
    "1124":   "112A",     # Sheep -> Animals
    "1129":   "112A",     # Other Animals -> Animals
    # Granular 5/6-digit Census codes
    "112110": "112A",     # Beef cattle -> Animals
    "112120": "112A",     # Dairy cattle -> Animals
    "111211": "111A",     # Potato farming -> Crops
    "111219": "111A",     # Other veg/melon -> Crops
    "112A":   "112A",     # Other animal production -> Animals
}


def _resolve_proxy(naics_code: str) -> str | None:
    """Try exact match, then progressively shorter prefixes."""
    if naics_code in PROXY_MAP:
        return PROXY_MAP[naics_code]
    for length in (4, 3):
        prefix = naics_code[:length]
        if prefix in PROXY_MAP:
            return PROXY_MAP[prefix]
    return None

# --- 3. SIDEBAR: SCOPE & CONTEXT ---
st.sidebar.header("⚙️ Simulation Scope")
regions = ["Canada", "Ontario", "Saskatchewan", "Alberta", "Manitoba", "Quebec", "British Columbia", "Atlantic provinces"]
region = st.sidebar.selectbox("Region", regions, index=1)

st.sidebar.info("🔒 Simulator locked to 'Primary Agriculture' for granular cost modeling.")
st.sidebar.subheader("🚜 Farm Type Context")

avail_types_map = {} 
if expense_profiles:
    prefix = f"{region}|"
    for k in expense_profiles.keys():
        if k.startswith(prefix):
            raw_name = k.split("|")[1]
            clean_name = raw_name.split(" [")[0]
            avail_types_map[clean_name] = k
            
sorted_names = sorted(list(avail_types_map.keys()))

default_idx = 0
if "All farm types" in sorted_names:
    default_idx = sorted_names.index("All farm types")

target_codes = None 
naics_code = None          # Raw NAICS for specific-commodity path
current_profile = {} 
sector_total_expenses = 0 
proxy_label = "None"

if sorted_names:
    selected_name = st.sidebar.selectbox("Representative Farm", sorted_names, index=default_idx)
    full_key = avail_types_map[selected_name]
    
    profile_data = expense_profiles.get(full_key, {})
    current_profile = profile_data.get("ratios", {})
    intermediate_profile = profile_data.get("intermediate_ratios", current_profile)
    sector_total_expenses = profile_data.get("total_expenses_raw", 0)
    
    if "All farm types" in selected_name:
        target_codes = "BASKET:primary_agriculture" 
        proxy_label = "Basket: Primary Ag"
    else:
        match = re.search(r"\[(\w+)\]", full_key)
        if match:
            raw_code = match.group(1)
            naics_code = raw_code          # e.g. "1111" or "112110"
            resolved_proxy = _resolve_proxy(raw_code)
            if resolved_proxy:
                proxy_label = f"Proxy: {resolved_proxy}"
            else:
                proxy_label = f"Code: {raw_code}"
            target_codes = "SPECIFIC"      # sentinel; actual codes resolved inside sim
        else:
            target_codes = None
            proxy_label = "Unknown"
else:
    st.sidebar.warning(f"No profiles found for {region}.")
    selected_name = "Generic Farm"
    target_codes = None
    current_profile = {"fertilizer": 0.15, "energy": 0.10, "labor": 0.15, "interest": 0.05, "feed": 0.10, "crop_inputs": 0.05}
    intermediate_profile = {"fertilizer": 0.22, "energy": 0.15, "feed": 0.15, "crop_inputs": 0.07, "other": 0.41}
    profile_data = {"ratios": current_profile, "intermediate_ratios": intermediate_profile}

with st.sidebar.expander("View Cost Structure", expanded=True):
    cols = st.columns(2)
    with cols[0]:
        st.write(f"**Fertilizer:** {current_profile.get('fertilizer',0):.1%}")
        st.write(f"**Energy:** {current_profile.get('energy',0):.1%}")
        st.write(f"**Labor:** {current_profile.get('labor',0):.1%}")
    with cols[1]:
        st.write(f"**Feed:** {current_profile.get('feed',0):.1%}")
        st.write(f"**Seed/Pest:** {current_profile.get('crop_inputs',0):.1%}")
        st.write(f"**Interest:** {current_profile.get('interest',0):.1%}")
    st.caption(f"Structure: Census 2024 | IO Proxy: {proxy_label}")
    if "Proxy" in proxy_label:
        st.caption("⚠️ **Warning:** Proxy uses a Margin Calibration Factor to adjust for profit margin heterogeneity across sub-sectors. Baseline revenue estimates may be approximate.")

# --- 4. SHOCK INPUTS ---
st.sidebar.markdown("---")
st.sidebar.header("🕹️ Shock Scenarios")

st.sidebar.markdown("#### 📖 Quick Scenarios")
sc1, sc2 = st.sidebar.columns(2)
with sc1:
    sc1.button("US Trade War", on_click=apply_preset, args=("Trade War",), use_container_width=True)
    sc1.button("Stagflation", on_click=apply_preset, args=("Stagflation",), use_container_width=True)
with sc2:
    sc2.button("Labor Crisis", on_click=apply_preset, args=("Labor Crisis",), use_container_width=True)
    sc2.button("Reset (Zero)", on_click=apply_preset, args=("Reset",), use_container_width=True)

st.sidebar.subheader("📉 Revenue Shocks")
shock_revenue = st.sidebar.slider("Market Price / Yield Change (%)", -50, 50, key="shock_revenue", help="Adjusts base revenue.")

# ── C5: Tariff Exposure Module (Literature-Calibrated, April 2026 v3.1) ──
TARIFF_CONFIG = {
    "Canola (Seed)": {"markets": {"China": 0.40, "Japan": 0.15, "Mexico": 0.15, "US": 0.05, "Other": 0.25},
                      "pass_through": 0.30, "export_intensity": 0.90, "us_lop_spillover": 0.0,
                      "eps_sr": 0.30, "eps_lr": 1.10, "lam": 0.4,
                      "fx_buffer": 0.15, "diversion_rate": 0.35, "sm_shielded": False},
    "Canola (Oil/Meal)": {"markets": {"US": 0.85, "China": 0.05, "Other": 0.10},
                          "pass_through": 0.35, "export_intensity": 0.85, "us_lop_spillover": 0.10,
                          "eps_sr": 0.28, "eps_lr": 1.05, "lam": 0.4,
                          "fx_buffer": 0.10, "diversion_rate": 0.10, "sm_shielded": False},
    "Wheat":       {"markets": {"China": 0.23, "US": 0.11, "Japan": 0.08, "Other": 0.58},
                    "pass_through": 0.15, "export_intensity": 0.70, "us_lop_spillover": 0.0,
                    "eps_sr": 0.40, "eps_lr": 1.10, "lam": 0.4,
                    "fx_buffer": 0.20, "diversion_rate": 0.40, "sm_shielded": False},
    "Live Cattle": {"markets": {"US": 0.75, "Japan": 0.09, "Mexico": 0.06, "Other": 0.10},
                    "pass_through": 0.25, "export_intensity": 0.50, "us_lop_spillover": 0.425,
                    "eps_sr": 0.12, "eps_lr": 0.85, "lam": 0.8,
                    "fx_buffer": 0.05, "diversion_rate": 0.10, "sm_shielded": False},
    "Hogs / Pork": {"markets": {"US": 0.65, "Japan": 0.12, "China": 0.08, "Other": 0.15},
                    "pass_through": 0.30, "export_intensity": 0.70, "us_lop_spillover": 0.30,
                    "eps_sr": 0.15, "eps_lr": 0.90, "lam": 0.6,
                    "fx_buffer": 0.10, "diversion_rate": 0.20, "sm_shielded": False},
    "Dairy (SM)": {"markets": {"US": 0.05, "Other": 0.95},
                   "pass_through": 0.05, "export_intensity": 0.05, "us_lop_spillover": 0.0,
                   "eps_sr": 0.05, "eps_lr": 0.10, "lam": 0.1,
                   "fx_buffer": 0.0, "diversion_rate": 0.0, "sm_shielded": True},
    "Poultry (SM)": {"markets": {"US": 0.05, "Other": 0.95},
                     "pass_through": 0.05, "export_intensity": 0.05, "us_lop_spillover": 0.0,
                     "eps_sr": 0.05, "eps_lr": 0.10, "lam": 0.1,
                     "fx_buffer": 0.0, "diversion_rate": 0.0, "sm_shielded": True},
    "Dry Peas": {
        "markets": {"China": 0.40, "India": 0.20, "US": 0.10, "Japan": 0.01, "Bangladesh": 0.10, "EU": 0.05, "Other": 0.14},
        "export_intensity": 0.75, "pass_through": 0.65, "us_lop_spillover": 0.0,
        "eps_sr": 0.25, "eps_lr": 0.75, "lam": 0.67, "fx_buffer": 0.10, "diversion_rate": 0.20, "sm_shielded": False
    },
    "Lentils": {
        "markets": {"China": 0.00, "India": 0.33, "US": 0.04, "Japan": 0.00, "Bangladesh": 0.00, "EU": 0.08, "Other": 0.55},
        "export_intensity": 0.85, "pass_through": 0.60, "us_lop_spillover": 0.0,
        "eps_sr": 0.30, "eps_lr": 0.80, "lam": 0.62, "fx_buffer": 0.10, "diversion_rate": 0.25, "sm_shielded": False
    },
    # Corn: eps_sr > eps_lr (0.40 > 0.29) reflects agronomic reality — producers max out
    # viable corn acreage quickly when prices spike but yield drag and pest pressure prevent
    # sustained expansion. lam = 0.38 governs convergence speed from SR to LR.
    "Corn (Grain)": {
        "markets": {"China": 0.00, "India": 0.00, "US": 0.22, "Japan": 0.00, "Bangladesh": 0.00, "EU": 0.50, "Other": 0.28},
        "export_intensity": 0.15, "pass_through": 0.85, "us_lop_spillover": 0.40,
        "eps_sr": 0.40, "eps_lr": 0.29, "lam": 0.38, "fx_buffer": 0.10, "diversion_rate": 0.20, "sm_shielded": False
    },
    "Chickpeas": {
        "markets": {"China": 0.00, "India": 0.03, "US": 0.19, "Japan": 0.00, "Bangladesh": 0.00, "EU": 0.19, "Other": 0.59},
        "export_intensity": 0.91, "pass_through": 0.65, "us_lop_spillover": 0.0,
        "eps_sr": 0.25, "eps_lr": 0.80, "lam": 0.69, "fx_buffer": 0.10, "diversion_rate": 0.30, "sm_shielded": False
    },
    "Soybeans": {
        "markets": {"China": 0.20, "India": 0.00, "US": 0.05, "Japan": 0.12, "Bangladesh": 0.00, "EU": 0.20, "Other": 0.43},
        "export_intensity": 0.70, "pass_through": 0.75, "us_lop_spillover": 0.10,
        "eps_sr": 0.21, "eps_lr": 0.63, "lam": 0.67, "fx_buffer": 0.10, "diversion_rate": 0.35, "sm_shielded": False
    },
    "Barley": {
        "markets": {"China": 0.71, "India": 0.00, "US": 0.09, "Japan": 0.20, "Bangladesh": 0.00, "EU": 0.00, "Other": 0.00},
        "export_intensity": 0.35, "pass_through": 0.90, "us_lop_spillover": 0.15,
        "eps_sr": 0.15, "eps_lr": 0.45, "lam": 0.67, "fx_buffer": 0.10, "diversion_rate": 0.15, "sm_shielded": False
    },
    "Oats": {
        "markets": {"China": 0.01, "India": 0.00, "US": 0.95, "Japan": 0.01, "Bangladesh": 0.00, "EU": 0.00, "Other": 0.03},
        "export_intensity": 0.50, "pass_through": 0.85, "us_lop_spillover": 0.30,
        "eps_sr": 0.20, "eps_lr": 0.60, "lam": 0.67, "fx_buffer": 0.10, "diversion_rate": 0.05, "sm_shielded": False
    },
    "Corn (Grain)": {
        "markets": {"China": 0.00, "India": 0.00, "US": 0.22, "Japan": 0.00, "Bangladesh": 0.00, "EU": 0.50, "Other": 0.28},
        "export_intensity": 0.15, "pass_through": 0.85, "us_lop_spillover": 0.40,
        "eps_sr": 0.40, "eps_lr": 0.29, "lam": -0.38, "fx_buffer": 0.10, "diversion_rate": 0.20, "sm_shielded": False
    },
    "Flaxseed": {
        "markets": {"China": 0.20, "India": 0.00, "US": 0.65, "Japan": 0.02, "Bangladesh": 0.00, "EU": 0.04, "Other": 0.09},
        "export_intensity": 0.81, "pass_through": 0.60, "us_lop_spillover": 0.10,
        "eps_sr": 0.25, "eps_lr": 0.70, "lam": 0.64, "fx_buffer": 0.10, "diversion_rate": 0.25, "sm_shielded": False
    },
    "Dry Beans": {
        "markets": {"China": 0.01, "India": 0.00, "US": 0.10, "Japan": 0.05, "Bangladesh": 0.00, "EU": 0.20, "Other": 0.64},
        "export_intensity": 0.88, "pass_through": 0.75, "us_lop_spillover": 0.0,
        "eps_sr": 0.30, "eps_lr": 0.85, "lam": 0.65, "fx_buffer": 0.10, "diversion_rate": 0.30, "sm_shielded": False
    },
    "Potatoes (Fresh)": {
        "markets": {"China": 0.00, "India": 0.00, "US": 0.93, "Japan": 0.00, "Bangladesh": 0.00, "EU": 0.00, "Other": 0.07},
        "export_intensity": 0.10, "pass_through": 0.80, "us_lop_spillover": 0.20,
        "eps_sr": 0.15, "eps_lr": 0.50, "lam": 0.70, "fx_buffer": 0.10, "diversion_rate": 0.05, "sm_shielded": False
    }
}
_AGG_REVENUE_WEIGHTS = {
    "Live Cattle": 0.154,
    "Hogs / Pork": 0.119,
    "Wheat": 0.101,
    "Canola (Seed)": 0.035,
    "Canola (Oil/Meal)": 0.023,
    "Dairy (SM)": 0.005,
    "Poultry (SM)": 0.005,
    "Dry Peas": 0.015,
    "Lentils": 0.015,
    "Chickpeas": 0.002,
    "Soybeans": 0.030,
    "Barley": 0.010,
    "Oats": 0.005,
    "Corn (Grain)": 0.010,
    "Flaxseed": 0.005,
    "Dry Beans": 0.002,
    "Potatoes (Fresh)": 0.005,
    "_other": 0.459,
}
_OTHER_AG_CONFIG = {
    "pass_through": 0.25,
    "export_intensity": 0.50,
    "us_lop_spillover": 0.10,
    "fx_buffer": 0.10,
}
tariff_active = False
tariff_detail = ""
tariff_effective_tariff = 0.0
tariff_tcfg = None
tariff_revenue_exposure = 0.0
tariff_commodity_breakdown = None
with st.sidebar.expander("🌐 Trade Shock Scenario", expanded=False):
    _tariff_options = ["All Primary Agriculture"] + list(TARIFF_CONFIG.keys())
    tariff_commodity = st.selectbox("Commodity", _tariff_options, key="tariff_commodity")

    if tariff_commodity == "All Primary Agriculture":
        _all_countries = set()
        for _cfg in TARIFF_CONFIG.values():
            _all_countries.update(_cfg["markets"].keys())
        _all_countries.discard("Other")
        _country_list = sorted(_all_countries)
    else:
        tcfg = TARIFF_CONFIG[tariff_commodity]
        _country_list = list(tcfg["markets"].keys())

        if tcfg.get("sm_shielded"):
            st.info(
                "🛡️ **Supply-managed sector**: Insulated by tariff-rate quotas (TRQ). "
                "Over-quota tariffs are already prohibitively high. External tariffs "
                "have minimal impact on domestic output or margins."
            )

    tariff_country = st.selectbox("Tariff Source Country", _country_list, key="tariff_country")
    if "tariff_pct" not in st.session_state: st.session_state.tariff_pct = 0
    tariff_pct = st.sidebar.slider("Tariff Increase (%)", 0, 1000, key="tariff_pct")
    include_processing = st.sidebar.checkbox("Include downstream processing impact", value=False, help="Models the supply-chain ripple through processing (NAICS 3112 for grains/pulses)")
    if tariff_pct > 0:
        if tariff_commodity == "All Primary Agriculture":
            _agg_impact = 0.0
            _agg_exposure = 0.0
            _component_lines = []
            _total_weight = 0.0
            tariff_commodity_breakdown = []

            _fcr_rev_cache = {}
            if national_fcr_df is not None:
                if 'YEAR' in national_fcr_df.columns:
                    latest_yr = int(national_fcr_df['YEAR'].max())
                    can_df = national_fcr_df[(national_fcr_df['GEO'] == 'Canada') & (national_fcr_df['YEAR'] == latest_yr)]
                else:
                    latest_yr = int(pd.to_numeric(national_fcr_df['REF_DATE'].astype(str).str[:4]).max())
                    can_df = national_fcr_df[(national_fcr_df['GEO'] == 'Canada') & (national_fcr_df['REF_DATE'].astype(str).str.startswith(str(latest_yr)))]
                
                _mapped_fcr_total = 0.0
                for _c_name, _fcr_keys in TARIFF_FCR_MAP.items():
                    _c_total = 0.0
                    for _key in _fcr_keys:
                        _matches = can_df[can_df['Type of cash receipts'].str.contains(_key, case=False, na=False, regex=False)]
                        for _, _r in _matches.iterrows():
                            _val = _r['VALUE']
                            _label_str = str(_r['Type of cash receipts'])
                            if pd.notna(_val) and _val > 0:
                                if _key.lower() in _label_str.lower()[:len(_key)+10]:
                                    _c_total += _val * 1000.0
                                    break
                    _fcr_rev_cache[_c_name] = _c_total
                    _mapped_fcr_total += _c_total
                
                _total_fcr_row = can_df[can_df['Type of cash receipts'] == 'Total farm cash receipts']
                if not _total_fcr_row.empty:
                    _total_fcr = _total_fcr_row.iloc[0]['VALUE'] * 1000.0
                    _other_fcr = _total_fcr - _mapped_fcr_total
                    _payments_row = can_df[can_df['Type of cash receipts'] == 'Total direct payments']
                    if not _payments_row.empty:
                        _other_fcr -= _payments_row.iloc[0]['VALUE'] * 1000.0
                    _fcr_rev_cache["_other"] = max(0.0, _other_fcr)

            for _comm, _weight in _AGG_REVENUE_WEIGHTS.items():
                if _comm == "_other":
                    _cfg = _OTHER_AG_CONFIG
                    _ms = 0.49 if tariff_country == "US" else 0.15
                else:
                    _cfg = TARIFF_CONFIG[_comm]
                    _ms = _cfg["markets"].get(tariff_country, 0.0)

                _ei = _cfg.get("export_intensity", 0.50)
                _pt = _cfg.get("pass_through", 0.25)
                _fx = _cfg.get("fx_buffer", 0.10)
                _direct = _ei * _ms
                _spill = _cfg.get("us_lop_spillover", 0.0) if tariff_country == "US" else 0.0
                _exp = min(_direct + _spill, 1.0)
                _border_drop = (tariff_pct / 100.0) * _pt * (1 - _fx)
                _imp = -(_border_drop * _exp) * 100.0

                _weighted_imp = _imp * _weight
                _agg_impact += _weighted_imp
                _agg_exposure += _exp * _weight
                _total_weight += _weight

                _label = _comm if _comm != "_other" else "Other Ag (generic)"
                if abs(_weighted_imp) > 0.01:
                    _component_lines.append(f"{_label}: {_imp:+.1f}% × {_weight:.0%} = {_weighted_imp:+.2f}pp")

                _fcr_rev = _fcr_rev_cache.get(_comm, 0.0)
                _dollar_impact = _fcr_rev * _exp * _pt * (1 - _fx) * (tariff_pct / 100.0) * -1.0
                
                tariff_commodity_breakdown.append({
                    "commodity": _label if _comm != "_other" else "Other Ag",
                    "fcr_revenue": _fcr_rev,
                    "weight": _weight,
                    "export_intensity": _ei,
                    "market_share": _ms,
                    "direct_exposure": _direct,
                    "spillover": _spill,
                    "total_exposure": _exp,
                    "pass_through": _pt,
                    "fx_buffer": _fx,
                    "revenue_impact_pct": _imp,
                    "dollar_impact": _dollar_impact,
                    "sm_shielded": _cfg.get("sm_shielded", False)
                })

            price_impact = round(_agg_impact, 1)
            total_revenue_exposure = _agg_exposure / _total_weight if _total_weight > 0 else 0

            st.caption(f"📊 **Aggregate sector impact: {price_impact:+.1f}%** (trade-weighted revenue-share sum)")
            st.caption(
                f"Weighted avg revenue exposure: **{total_revenue_exposure:.0%}** · "
                f"Tariff: **{tariff_pct}%** from **{tariff_country}**"
            )
            with st.expander("Component breakdown", expanded=False):
                for _line in _component_lines:
                    st.caption(_line)

            _avg_pt = sum(
                TARIFF_CONFIG[c].get("pass_through", 0.25) * w
                for c, w in _AGG_REVENUE_WEIGHTS.items() if c != "_other"
            ) + _OTHER_AG_CONFIG["pass_through"] * _AGG_REVENUE_WEIGHTS["_other"]
            tcfg = {
                "pass_through": _avg_pt,
                "export_intensity": 0.50,
                "us_lop_spillover": 0.15 if tariff_country == "US" else 0.0,
                "eps_sr": 0.25, "eps_lr": 0.95, "lam": 0.5,
                "fx_buffer": 0.12, "diversion_rate": 0.25, "sm_shielded": False,
            }
            direct_exposure = _agg_exposure
            spillover_exposure = 0.0

        else:
            tcfg = TARIFF_CONFIG[tariff_commodity]
            market_share = tcfg["markets"][tariff_country]
            fx_buf = tcfg.get("fx_buffer", 0.0)
            export_intensity = tcfg.get("export_intensity", 1.0)
            direct_exposure = export_intensity * market_share
            spillover_exposure = tcfg.get("us_lop_spillover", 0.0) if tariff_country == "US" else 0.0
            total_revenue_exposure = direct_exposure + spillover_exposure
            price_drop_at_border = (tariff_pct / 100.0) * tcfg["pass_through"] * (1 - fx_buf)
            # 5. Final revenue impact
            price_impact = -(price_drop_at_border * total_revenue_exposure) * 100.0

            st.caption(
                f"Export share ({tariff_country}): **{market_share:.0%}** · "
                f"Export intensity: **{export_intensity:.0%}** → "
                f"Direct exposure: **{direct_exposure:.0%}**"
            )
            if spillover_exposure > 0:
                st.caption(
                    f"🔗 US LOP spillover: **+{spillover_exposure:.0%}** → "
                    f"Total revenue exposure: **{total_revenue_exposure:.0%}**"
                )
            else:
                st.caption(f"Total revenue exposure: **{total_revenue_exposure:.0%}**")
            st.caption(
                f"Producer absorption: **{tcfg['pass_through']:.0%}** "
                f"(FX buffer: {fx_buf:.0%}) → "
                f"Farm revenue impact: **{price_impact:+.1f}%**"
            )

        div_rate = tcfg.get("diversion_rate", 0.0)
        if div_rate > 0:
            st.caption(
                f"📈 Trade diversion rate: **{div_rate:.0%}** — "
                f"impact diminishes over 3 years as alternative markets absorb volume."
            )

        # ── Downstream Processing (Analysis-by-Parts) ──
        _processing_commodities = [
            "Dry Peas", "Lentils", "Soybeans", "Canola (Seed)", "Canola (Oil/Meal)",
            "Wheat", "Barley", "Oats", "Corn (Grain)", "Flaxseed"
        ]
        if include_processing and tariff_commodity in _processing_commodities:
            st.markdown("---")
            st.markdown("##### 🏭 Downstream Processing (Analysis-by-Parts)")
            st.caption(
                "Modeling tariff incidence on processed export value "
                "(e.g. Pea Starch, Canola Oil, Flour, Malt)."
            )
            # Farm commodity represents ~60% of processed product value;
            # processor margin captures the remaining 40%.
            _farm_share = 0.60
            _processor_margin = 0.40
            # Type II GDP multipliers (StatCan Symmetric IO Tables)
            _naics_3112_mult = 2.15  # NAICS 3112: Grain and Oilseed Milling
            _naics_111_mult = 1.85   # NAICS 111: Crop Production
            # Farm-only macro drag vs. combined supply chain drag
            _base_macro_drag = 1.0 * _naics_111_mult
            _total_macro_drag = (
                1.0 * _naics_111_mult
                + (_processor_margin / _farm_share) * _naics_3112_mult
            )
            _amplification = _total_macro_drag / _base_macro_drag
            st.info(
                f"**Macro Amplification:** The combined supply chain loss "
                f"(Farm + Processing Margin) generates a GDP drag "
                f"**{_amplification:.1f}×** larger than the farm-only shock."
            )

        st.caption(
            "⚠️ Does not model retaliatory tariff offsets. Canada is a net ag exporter "
            "to the US ($13.5B surplus, 2024 CIMT); retaliation provides partial but "
            "incomplete offset."
        )
        # Override the generic revenue slider with precise tariff impact
        # Scale the impact if viewing the entire sector, otherwise apply directly
        if tariff_commodity != "All Primary Agriculture" and selected_name == "All farm types":
            _weight = _AGG_REVENUE_WEIGHTS.get(tariff_commodity, 1.0)
            shock_revenue = round(price_impact * _weight, 2)
        else:
            shock_revenue = round(price_impact, 1)
        tariff_active = True
        tariff_effective_tariff = tariff_pct / 100.0  # raw tariff rate
        tariff_tcfg = tcfg
        tariff_revenue_exposure = total_revenue_exposure
        tariff_detail = (
            f"{tariff_pct}% tariff on {tariff_commodity} from {tariff_country} "
            f"(exposure {total_revenue_exposure:.0%}, absorption {tcfg['pass_through']:.0%}, "
            f"impact {price_impact:+.1f}%)"
        )

with st.sidebar.expander("🔥 Cost Shocks", expanded=True):
    c1, c2 = st.columns(2)
    with c1:
        shock_fert = st.slider("Fertilizer (%)", 0, 100, key="shock_fert")
        shock_energy = st.slider("Energy/Fuel (%)", 0, 100, key="shock_energy")
        shock_labor = st.slider("Wages (%)", 0, 50, key="shock_labor")
    with c2:
        shock_feed = st.slider("Feed (%)", 0, 100, key="shock_feed")
        shock_crop = st.slider("Seed/Pest (%)", 0, 100, key="shock_crop")
        shock_interest = st.slider("Interest (%)", 0, 100, key="shock_interest")

# ── Cost Shock Commodity Breakdown ──
cost_commodity_breakdown = None
if selected_name == "All farm types" and (shock_fert > 0 or shock_energy > 0 or shock_labor > 0 or shock_feed > 0 or shock_crop > 0 or shock_interest > 0):
    cost_commodity_breakdown = []
    _prefix = f"{region}|"
    for k, v in expense_profiles.items():
        if k.startswith(_prefix) and "All farm types" not in k:
            _raw_name = k.split("|")[1]
            _clean_name = _raw_name.split(" [")[0]
            
            _ir = v.get("intermediate_ratios", v.get("ratios", {}))
            _exp = v.get("total_expenses_raw", 0)
            
            _fert_hit = _exp * _ir.get('fertilizer', 0) * (shock_fert / 100.0)
            _eng_hit  = _exp * _ir.get('energy', 0)     * (shock_energy / 100.0)
            _feed_hit = _exp * _ir.get('feed', 0)       * (shock_feed / 100.0)
            _crop_hit = _exp * _ir.get('crop_inputs', 0)* (shock_crop / 100.0)
            
            _lab_hit = v.get("labor_dollars", 0) * (shock_labor / 100.0)
            _int_hit = v.get("interest_dollars", 0) * (shock_interest / 100.0)
            
            _total_hit = _fert_hit + _eng_hit + _feed_hit + _crop_hit + _lab_hit + _int_hit
            
            if _total_hit > 0:
                cost_commodity_breakdown.append({
                    "commodity": _clean_name,
                    "total_expenses": _exp,
                    "dollar_impact": _total_hit
                })

# ── C4: Shock Duration Toggle ──
shock_persistence = st.sidebar.radio(
    "Shock Duration",
    ["Persistent (structural)", "One-Time (pulse)"],
    index=0,
    help="Persistent: shock continues every year (e.g., permanent tariff). "
         "One-Time: shock hits Year 1 only, then reverts (e.g., drought)."
)

# --- 4b. MULTI-YEAR PROJECTION CONTROLS ---
with st.sidebar.expander("📈 Multi-Year Projection Parameters", expanded=False):
    proj_horizon = st.slider("Projection Horizon (years)", 1, 10, 3, 1)
    # Get province-specific defaults from balance sheet data
    _fin_default_dta = 0.22  # fallback
    _fin_default_src = "Canadian average"
    if financial_health_df is not None:
        _fh_row = financial_health_df[financial_health_df["geo"] == region]
        if _fh_row.empty:
            _fh_row = financial_health_df[financial_health_df["geo"] == "Canada"]
        if not _fh_row.empty:
            _fh = _fh_row.iloc[0]
            _fin_default_dta = round(_fh["debt_to_asset"], 2)
            _fin_default_src = f"StatCan {int(_fh['data_year'])}"

    proj_debt_ratio = st.slider(
        "Debt-to-Asset Ratio", 0.05, 0.50, _fin_default_dta, 0.01,
        help=f"Default: {_fin_default_dta:.0%} ({_fin_default_src}). Higher leverage = more sensitive to interest shocks."
    )
    base_tfp_growth = st.slider(
        "Baseline TFP Growth (% / yr)", 0.0, 3.0, 1.0, 0.1,
        help="The 'business-as-usual' productivity growth rate to compare against."
    )
    proj_tfp_growth = st.slider(
        "Target TFP Growth (% / yr)", 0.0, 3.0, 1.0, 0.1,
        help="The new scenario productivity growth rate. Gap = Target - Baseline."
    )
    proj_capex_shock = st.slider(
        "Capital Investment Change (%)", -50, 50, key="proj_capex_shock",
        help="% change in annual capital investment. Positive = more spending on machinery/infrastructure. Negative = disinvestment."
    )

    # TFW Policy Shock — province-specific labor vulnerability
    _labor_row = None
    if labor_metrics_df is not None:
        _lr = labor_metrics_df[labor_metrics_df["geo"] == region]
        if _lr.empty:
            _lr = labor_metrics_df[labor_metrics_df["geo"] == "Canada"]
        if not _lr.empty:
            _labor_row = _lr.iloc[0]

    _tfw_dep_display = f" (TFW dependency: {_labor_row['tfw_dependency']:.0%})" if _labor_row is not None else ""
    proj_tfw_reduction = st.slider(
        "TFW Access Reduction (%)", 0, 100, key="proj_tfw_reduction",
        help=f"Simulate curtailment of Temporary Foreign Worker programs{_tfw_dep_display}. "
             f"Higher TFW-dependent provinces (e.g. Ontario ~40%) are hit harder."
    )

# --- 5. SIMULATION ENGINE ---

# ── Helper: extract GDP & Jobs coefficients from a pre-filtered multiplier DF ──
def _coefficients_for_code(df_mult: pd.DataFrame, code: str):
    """Return (gdp_coeff, jobs_coeff) for a single join_code."""
    m_gdp, m_jobs = 0.0, 0.0
    if df_mult.empty:
        return m_gdp, m_jobs
    df_c = df_mult[df_mult["join_code"] == str(code)]
    row_gdp = df_c[
        df_c["variable"].str.contains("Gross domestic", case=False) &
        df_c["variable"].str.contains("basic prices", case=False)
    ]
    row_jobs = df_c[df_c["variable"].str.contains("Jobs", case=False)]
    if not row_gdp.empty:
        m_gdp = float(row_gdp["value"].iloc[0])
    if not row_jobs.empty:
        m_jobs = float(row_jobs["value"].iloc[0])
    return m_gdp, m_jobs


# ── Named Constants ───────────────────────────────────────────────────────
# Employment-output elasticity: ILO/World Bank reports ag output-labor
# elasticity ~0.3 for mechanized agriculture; meta-analyses of farm labor
# demand wage elasticities center -0.4 to -0.7 (AJAE 1973, AJAE 1969).
# 0.4 reflects OECD high-income ag: sticky labor, seasonal employment.
EMPLOYMENT_ELASTICITY = 0.4

# ── Sector Classifier (Research Brief §4.2 coefficients) ──────────────────
# Note: α values are for REPRODUCIBLE capital only (machinery + buildings),
# not total capital including land. The CapEx Impact doc (§4.1) reports total
# capital elasticities of 0.35-0.45 which include land's income share.
SECTOR_COEFFICIENTS = {
    "field_crops":   {"alpha": 0.18, "delta": 0.17, "phi": 0.10, "lag": 1, "tfw_multiplier": 0.5, "label": "Field Crops"},
    "horticulture":  {"alpha": 0.12, "delta": 0.12, "phi": 1.50, "lag": 2, "tfw_multiplier": 1.5, "label": "Horticulture"},
    "livestock":     {"alpha": 0.25, "delta": 0.05, "phi": 0.50, "lag": 3, "tfw_multiplier": 0.2, "label": "Livestock"},
    "mixed":         {"alpha": 0.18, "delta": 0.12, "phi": 0.30, "lag": 2, "tfw_multiplier": 1.0, "label": "Mixed / All"},
}

def _classify_sector(naics_code_or_name: str) -> dict:
    """Map NAICS code or farm type name to research-brief archetype."""
    code = str(naics_code_or_name or "").strip()
    name_lower = code.lower()
    # Horticulture: Greenhouse (1114), Fruit (1113), Veg (1112)
    if code.startswith("1114") or code.startswith("1113") or code.startswith("1112"):
        return SECTOR_COEFFICIENTS["horticulture"]
    if any(kw in name_lower for kw in ["greenhouse", "fruit", "vegetable", "nursery"]):
        return SECTOR_COEFFICIENTS["horticulture"]
    # Livestock: 112x
    if code.startswith("112"):
        return SECTOR_COEFFICIENTS["livestock"]
    if any(kw in name_lower for kw in ["cattle", "hog", "pig", "poultry", "dairy", "sheep", "animal"]):
        return SECTOR_COEFFICIENTS["livestock"]
    # Field Crops: 111x (excluding horticulture already caught above)
    if code.startswith("111"):
        return SECTOR_COEFFICIENTS["field_crops"]
    if any(kw in name_lower for kw in ["crop", "grain", "oilseed", "wheat", "canola"]):
        return SECTOR_COEFFICIENTS["field_crops"]
    # Default: mixed
    return SECTOR_COEFFICIENTS["mixed"]


def run_dynamic_projection(sim_y0: dict, horizon: int, debt_ratio: float,
                           tfp_growth_pct: float, interest_shock_pct: float,
                           wage_shock_pct: float, sector_params: dict,
                           annual_cost_shock: float = 0.0,
                           capex_shock_pct: float = 0.0,
                           base_vacancy_override: float = None,
                           tfw_reduction_pct: float = 0.0,
                           tfw_dependency: float = 0.0,
                           is_pulse: bool = False,
                           tariff_params: dict = None,
                           mc_draws: dict = None) -> list:
    """
    Recursive multi-year projection engine (Research Brief §5.1).

    Takes the Year 0 static simulation results and projects forward using:
      - Financial Stress Factor (FSF)  → investment throttle
      - Capital Accumulation K_{t+1}   → output capacity
      - Labor Realization Factor (LRF) → output penalty

    Returns a list of dicts, one per year (including Year 0).
    """
    alpha = sector_params["alpha"]          # Output elasticity of capital
    delta = sector_params["delta"]          # Depreciation rate (sector default)
    phi   = sector_params["phi"]            # Labor shortage penalty
    lag   = sector_params["lag"]            # Investment-to-output lag (years)
    tfp_g = tfp_growth_pct / 100.0         # TFP annual growth rate

    # ── Override δ with data-driven depreciation rate if available ──
    fin_health = sim_y0.get("financial_health")
    if fin_health is not None:
        data_delta = fin_health.get("depreciation_rate")
        if data_delta and data_delta == data_delta:  # not None and not NaN
            delta = float(data_delta)

    # ── Year 0 baseline values ──
    base_output = sim_y0["base_output"]
    base_gdp    = sim_y0["base_gdp"]
    gdp_coeff   = sim_y0["margin_pct"]
    type1_mult  = sim_y0.get("type1_mult", 1.35)

    # ── Initial capital stock & investment from StatCan CapEx data ──
    if sim_y0.get("capex_data"):
        capex = sim_y0["capex_data"]
        # Annual CapEx in dollars (CSV is in millions)
        base_investment = capex["total_capex_M"] * 1_000_000
        # Steady-state: K = CapEx / δ (at equilibrium, investment replaces depreciation)
        K = base_investment / delta if delta > 0 else base_output
        k0_source = f"StatCan CapEx ({capex.get('data_year', '?')}, {capex.get('geo', '?')})"
    else:
        # Fallback: estimate from output (Phase 1 behavior)
        K = base_output
        base_investment = K * delta * 1.02
        k0_source = "Estimated from output"

    K_0 = K  # Store initial capital for Cobb-Douglas normalization

    # ── C2 Validation: flag anomalous K₀ ──
    k0_warning = None
    if base_output > 0:
        k_ratio = K / base_output
        if k_ratio < 0.5 or k_ratio > 5.0:
            k0_warning = (f"K₀/Output ratio = {k_ratio:.1f}× "
                          f"(expected 1-4×). Source: {k0_source}")

    # Interest rate and debt: use real data if available
    fin_health = sim_y0.get("financial_health")
    if fin_health is not None:
        # Real total debt from StatCan (millions → dollars)
        real_total_debt = fin_health["total_debt_M"] * 1_000_000
        
        # Implied interest rate from real debt and income data
        nci = fin_health["net_cash_income_M"] * 1_000_000
        coverage = fin_health.get("interest_coverage", 2.0)
        if coverage and coverage > 0 and real_total_debt > 0:
            interest_expense = nci / coverage if coverage > 0 else real_total_debt * 0.05
            implied_rate = interest_expense / real_total_debt if real_total_debt > 0 else 0.05
            implied_rate = max(0.02, min(implied_rate, 0.10))  # clamp to 2-10%
        else:
            implied_rate = 0.05
            
        # NOW assign projection debt based on user slider
        total_assets = fin_health.get("total_assets_M", 0) * 1_000_000
        if total_assets > 0:
            total_debt = total_assets * debt_ratio
        else:
            total_debt = real_total_debt

        # Data-driven amortization rate (current liabilities / total debt)
        amort_rate = fin_health.get("amortization_rate")
        if amort_rate is None or amort_rate != amort_rate:  # None or NaN
            # Fallback 0.07: conservative vs FCC blended ~0.09 (farmland 20-25yr
            # amort = 4-5%, equipment 5-10yr = 10-20%, weighted ~0.09)
            amort_rate = 0.07
    else:
        # Fallback: hardcoded estimates (Phase 1 behavior)
        implied_rate = 0.05
        total_debt = base_output * debt_ratio
        amort_rate = 0.07  # default amortization

    shocked_rate = implied_rate * (1 + interest_shock_pct / 100.0)

    # Vacancy rate: derive from wage shock + TFW policy shock
    # Base vacancy is province-specific (from labor_metrics.csv) or CAHRC default
    base_vacancy = base_vacancy_override if base_vacancy_override is not None else 0.074
    # Wage hikes reduce vacancies slightly but don't eliminate structural gap
    wage_adjustment = (wage_shock_pct / 100.0) * 0.15
    # TFW reduction creates additional vacancies proportional to province's TFW dependency
    # If 40% of workforce is TFW and 50% reduction → 20% of jobs become vacant
    tfw_vacancy_shock = tfw_dependency * (tfw_reduction_pct / 100.0)
    vacancy_rate = max(0, base_vacancy - wage_adjustment + tfw_vacancy_shock)

    # ── Build Year 0 record ──
    output_t = sim_y0["final_output"]  # Year 0 shocked output
    gdp_t    = sim_y0["final_gdp"]
    A_t      = 1.0  # Normalized TFP
    investment_history = [base_investment] * (lag + 1)  # historical pipeline
    
    # M-1 Fix: Track the Year 0 shock to anchor the recursive loop permanently
    price_scalar = sim_y0["final_output"] / base_output if base_output > 0 else 1.0

    # Extract static variables for loop
    va_labor_hit = sim_y0.get("va_labor_hit", 0.0)
    base_expense = base_output * (1.0 - gdp_coeff)

    # Compute Year 0 DSCR from data
    # E-1 Fix: Strip wages from EBITDA calculation
    ebitda_y0 = output_t * gdp_coeff - annual_cost_shock - va_labor_hit
    debt_service_y0 = (total_debt * shocked_rate) + (total_debt * amort_rate)
    dscr_y0 = 0.0 if ebitda_y0 < 0 else (ebitda_y0 / debt_service_y0 if debt_service_y0 > 0 else 9.99)

    trajectory = [{
        "year": 0,
        "output": output_t,
        "gdp": gdp_t,
        "capital_stock": K,
        "investment": base_investment,
        "fsf": 1.0,
        "lrf": 1.0,
        "dscr": dscr_y0,
        "macro_gdp": sim_y0["macro_gdp"],
        "macro_jobs": sim_y0["macro_jobs"],
        "k0_source": k0_source,
        "k0_warning": k0_warning,
    }]

    for t in range(1, horizon + 1):
        # Apply stochastic draws if present
        tfp_g_t = (tfp_growth_pct + (mc_draws["tfp"][t] if mc_draws else 0.0)) / 100.0
        cost_draw_t = mc_draws["cost"][t] if mc_draws else 0.0
        int_draw_t = mc_draws["interest"][t] if mc_draws else 0.0
        capex_draw_t = mc_draws["capex"][t] if mc_draws else 0.0

        # ── Step 1: Financial Health (DSCR) ──
        # I-1 Fix: Pulse mode must also revert interest rate and tariff
        current_interest_shock = interest_shock_pct if (not is_pulse or t == 1) else 0.0
        shocked_rate_t = implied_rate * (1 + (current_interest_shock + int_draw_t) / 100.0)
        
        tariff_active_t = False
        if tariff_params and tariff_params.get("active"):
            tariff_active_t = True if (not is_pulse or t == 1) else False

        # E-2 / M-3 Fix: Derive physical volume ratio (excluding margin/price drops)
        expected_output_val = base_output * price_scalar
        vol_ratio_prev = output_t / expected_output_val if expected_output_val > 0 else 1.0
        
        # Base input cost hit dynamically scales with physical planted harvest. Apply stochastic variance.
        user_cost_shock = annual_cost_shock if (not is_pulse or t == 1) else 0.0
        cost_shock_t = (user_cost_shock + base_expense * cost_draw_t) * vol_ratio_prev
        
        # E-1 Fix: Wages bypass EBITDA, dynamically scaled to shrinking volumes
        va_labor_hit_t = va_labor_hit * vol_ratio_prev
        ebitda = output_t * gdp_coeff - cost_shock_t - va_labor_hit_t
        
        # O-1 Fix: Inject AgriStability (BRM) trigger if EBITDA falls >30% below baseline 
        base_ebitda = base_output * gdp_coeff
        if ebitda < 0.70 * base_ebitda:
            brm_decay_factor = max(0.0, 1.0 - 0.33 * max(0, t - 2)) 
            brm_payout = 0.70 * (0.70 * base_ebitda - ebitda) * brm_decay_factor
            ebitda += brm_payout

        # I-3 Fix: Explicitly force DSCR=0 if EBITDA is strictly negative
        annual_principal = total_debt * amort_rate
        debt_service = (total_debt * shocked_rate_t) + annual_principal
        if ebitda < 0:
            dscr = 0.0
        else:
            dscr = ebitda / debt_service if debt_service > 0 else 9.99

        # ── Step 2: Financial Stress Factor (FSF) — Research Brief §2.3 ──
        if dscr > 1.25:
            fsf = 1.0
        elif dscr > 1.0:
            beta_stress = 0.20
            fsf = 1.0 - beta_stress * (1.25 - dscr)
        else:
            beta_crisis = 0.80
            p_liquidation = 0.05
            fsf = max(0.0, 1.0 - beta_crisis * (1.0 - dscr) - p_liquidation)

        # ── Step 3: Investment → Capital Accumulation (§4.3, Rule 4) ──
        # C4: In pulse mode, CapEx shock applies only in Year 1
        current_capex_shock = capex_shock_pct if (not is_pulse or t == 1) else 0.0
        capex_mult_t = (1.0 + (current_capex_shock + capex_draw_t) / 100.0) 
        investment_t = base_investment * fsf * capex_mult_t
        investment_history.append(investment_t)

        # Lagged investment enters capital stock
        lagged_investment = investment_history[max(0, len(investment_history) - 1 - lag)]
        K = K * (1 - delta) + lagged_investment

        # ── Step 4: TFP trend ──
        # I-2 Fix: Inject stochastic volatility into TFP
        A_t *= (1 + tfp_g_t)

        # ── Step 5: Potential output from capital (Cobb-Douglas) ──
        # M-1 Fix: Incorporate Year 0 price shock scalar into baseline capacity
        potential_output = base_output * price_scalar * A_t * (K / K_0) ** alpha

        # ── Step 6: Labor Realization Factor (§3.3, Rule 3) ──
        # LRF is RELATIVE to structural vacancy: current output already
        # reflects the 7.4% base vacancy. Only penalize for CHANGES.
        delta_vacancy = max(0, vacancy_rate - base_vacancy)
        lrf = max(0.0, 1.0 - phi * delta_vacancy)

        # ── Step 7: Realized output ──
        output_t = potential_output * lrf

        # ── C3: Livestock Liquidation J-Curve (Research Brief §2.3, Rule 2) ──
        absolute_rate_change = shocked_rate_t - implied_rate
        if sector_params.get("label") == "Livestock" and absolute_rate_change > 0.0001:
            liquidation_coeff = 0.03  # 3% herd contraction per 100bps
            # M-2 Fix: Extract absolute basis point change for contraction math
            delta_rate_points = absolute_rate_change * 100.0

            if t == 1:
                # Year 1: liquidation spike — forced sales INCREASE short-term output
                output_t *= (1.0 + liquidation_coeff * delta_rate_points)
            else:
                # Year 2+: smaller breeding herd → output contracts
                cumulative_herd_loss = liquidation_coeff * delta_rate_points * min(t, 5)
                output_t *= max(0.85, 1.0 - cumulative_herd_loss)

        # ── Step 7b: Tariff Time-Varying Elasticity & Trade Diversion ──
        if tariff_active_t:
            tcfg_p = tariff_params["config"]
            tariff_rate = tariff_params["tariff_pct"]  # raw tariff rate (e.g. 0.35)
            revenue_exposure = tariff_params["revenue_exposure"]  # pre-computed in UI
            eps_sr = tcfg_p.get("eps_sr", 0.3)
            eps_lr = tcfg_p.get("eps_lr", 1.0)
            div_rate = tcfg_p.get("diversion_rate", 0.0)
            fx_buffer = tcfg_p.get("fx_buffer", 0.0)
            pass_through = tcfg_p.get("pass_through", 1.0)
            tariff_weight = tariff_params.get("weight", 1.0)
            
            # Price drop at border: tariff × producer absorption × FX buffer
            # Revenue exposure: pre-computed (direct + spillover), destination-aware
            # tariff_weight scales the impact down if simulating a single crop but viewing the national aggregate
            domestic_price_drop_pct = tariff_rate * pass_through * (1.0 - fx_buffer) * revenue_exposure * tariff_weight
            
            lam = tcfg_p.get("lam", 0.4)
            t_90 = min(np.log(0.1) / np.log(max(lam, 0.01)), 10.0)  # cap at 10yr
            progress = min(t / t_90, 1.0)
            eps_t = eps_sr + progress * (eps_lr - eps_sr)
            diversion_factor = 1.0 - div_rate * min(t / 3.0, 1.0)
            
            tariff_output_drag = base_output * domestic_price_drop_pct * eps_t * diversion_factor
            output_t = max(output_t * 0.5, output_t - tariff_output_drag)  # floor at 50%

        # GDP = Value Added minus cost burden
        gdp_t = output_t * gdp_coeff - cost_shock_t

        # ── Step 8: Macro impacts (same multipliers as Year 0) ──
        delta_gdp = gdp_t - base_gdp
        macro_gdp = delta_gdp * type1_mult
        macro_indirect_gdp = macro_gdp - delta_gdp
        
        # E-2 Fix: Tie jobs purely to physical output volume, stripping out margin drops
        vol_ratio_curr = output_t / base_output if base_output > 0 else 1.0
        pct_change_vol = vol_ratio_curr - 1.0
        direct_jobs = sim_y0.get("base_jobs", 0) * pct_change_vol * EMPLOYMENT_ELASTICITY
        type1_jobs_mult = sim_y0.get("type1_jobs_mult", 1.35)
        macro_jobs = direct_jobs * type1_jobs_mult
        macro_indirect_jobs = macro_jobs - direct_jobs

        trajectory.append({
            "year": t,
            "output": output_t,
            "gdp": gdp_t,
            "capital_stock": K,
            "investment": investment_t,
            "fsf": fsf,
            "lrf": lrf,
            "dscr": dscr,
            "macro_gdp": macro_gdp,
            "macro_jobs": macro_jobs,
        })

    return trajectory


def run_monte_carlo_projections(sim_y0: dict, horizon: int, debt_ratio: float,
                                tfp_growth_pct: float, interest_shock_pct: float,
                                wage_shock_pct: float, sector_params: dict,
                                annual_cost_shock: float = 0.0,
                                capex_shock_pct: float = 0.0,
                                base_vacancy_override: float = None,
                                tfw_reduction_pct: float = 0.0,
                                tfw_dependency: float = 0.0,
                                is_pulse: bool = False,
                                tariff_params: dict = None,
                                n_runs: int = 200, seed: int = 42) -> dict:
    """
    Monte Carlo uncertainty analysis.

    Runs n_runs iterations of run_dynamic_projection with randomly perturbed
    parameters, then returns percentile bands (P10, P25, P50, P75, P90).

    Red Team Fix: Implementation of Correlated Multivariate Shocks.
    Following standard macroeconomic agricultural modeling (e.g., Richardson et al., 2000
    SIMETAR models; USDA ERS stochastic baselines), variables are not independent.
    We use a Cholesky Decomposition covariance matrix to model compounding tail-risk:
    - High inflation (cost) strongly correlates with Central Bank rate hikes (interest).
    - High interest rates strongly inverse-correlate with Capital Expenditures.
    """
    rng = np.random.default_rng(seed)

    # Storage: rows = runs, cols = years (0..horizon)
    gdp_matrix = np.zeros((n_runs, horizon + 1))
    dscr_matrix = np.zeros((n_runs, horizon + 1))

    # --- CHOLESKY DECOMPOSITION COVARIANCE MATRIX ---
    # Variables: [TFP, Cost, Interest, CapEx]
    stds = np.array([0.3, 0.05, 0.5, 5.0])
    
    # Correlation Matrix (Literature-backed approximations)
    corr = np.array([
        [ 1.0, -0.2, -0.1,  0.4], # TFP
        [-0.2,  1.0,  0.6, -0.5], # Cost (highly correlated with interest)
        [-0.1,  0.6,  1.0, -0.6], # Interest (inversely correlated with capex)
        [ 0.4, -0.5, -0.6,  1.0]  # CapEx
    ])
    
    # Covariance matrix: diag(stds) * corr * diag(stds)
    cov = np.diag(stds) @ corr @ np.diag(stds)
    L = np.linalg.cholesky(cov)

    for i in range(n_runs):
        # Draw independent standard normals: shape (4, horizon+1)
        Z = rng.standard_normal((4, horizon + 1))
        # Apply Cholesky matrix to get correlated draws: shape (4, horizon+1)
        correlated_draws = L @ Z
        
        mc_draws = {
            "tfp": correlated_draws[0],      
            "cost": correlated_draws[1],    
            "interest": correlated_draws[2], 
            "capex": correlated_draws[3],    
        }

        # Perturb labor penalty coefficient (φ) — relevant for TFW scenarios
        # σ=0.20 reflects literature range: horticulture φ spans 1.0-2.0, livestock 0.3-0.7
        mc_sector_params = dict(sector_params)
        mc_sector_params["phi"] = max(0.05, sector_params["phi"] + rng.normal(0, 0.20))

        # Perturb tariff parameters if active (literature-backed uncertainty)
        mc_tariff_params = None
        if tariff_params and tariff_params.get("active"):
            mc_tcfg = dict(tariff_params["config"])
            mc_tcfg["pass_through"] = max(0.05, mc_tcfg["pass_through"] + rng.normal(0, 0.05))
            mc_tcfg["diversion_rate"] = max(0.0, min(0.8, mc_tcfg.get("diversion_rate", 0) + rng.normal(0, 0.10)))
            mc_tcfg["fx_buffer"] = max(0.0, min(0.5, mc_tcfg.get("fx_buffer", 0) + rng.normal(0, 0.05)))
            # Perturb revenue exposure slightly (±5pp) for uncertainty in LOP spillover
            mc_revenue_exposure = max(0.01, tariff_params["revenue_exposure"] + rng.normal(0, 0.05))
            mc_tariff_params = {
                "active": True,
                "tariff_pct": tariff_params["tariff_pct"],
                "revenue_exposure": mc_revenue_exposure,
                "config": mc_tcfg,
            }

        traj = run_dynamic_projection(
            sim_y0=sim_y0,
            horizon=horizon,
            debt_ratio=debt_ratio,
            tfp_growth_pct=tfp_growth_pct,
            interest_shock_pct=interest_shock_pct,
            wage_shock_pct=wage_shock_pct,
            sector_params=mc_sector_params,
            annual_cost_shock=annual_cost_shock,
            capex_shock_pct=capex_shock_pct,
            base_vacancy_override=base_vacancy_override,
            tfw_reduction_pct=tfw_reduction_pct,
            tfw_dependency=tfw_dependency,
            is_pulse=is_pulse,
            tariff_params=mc_tariff_params if mc_tariff_params else tariff_params,
            mc_draws=mc_draws,
        )

        for t, rec in enumerate(traj):
            gdp_matrix[i, t] = rec["gdp"]
            dscr_matrix[i, t] = rec["dscr"]

    # Compute percentiles
    percentiles = [10, 25, 50, 75, 90]
    result = {
        "years": list(range(horizon + 1)),
        "n_runs": n_runs,
        "gdp": {},
        "dscr": {},
    }
    for p in percentiles:
        result["gdp"][f"p{p}"] = np.percentile(gdp_matrix, p, axis=0).tolist()
        result["dscr"][f"p{p}"] = np.percentile(dscr_matrix, p, axis=0).tolist()

    # Final-year spread for reporting
    result["final_gdp_p10"] = result["gdp"]["p10"][-1]
    result["final_gdp_p90"] = result["gdp"]["p90"][-1]
    result["final_gdp_p25"] = result["gdp"]["p25"][-1]
    result["final_gdp_p75"] = result["gdp"]["p75"][-1]
    result["final_dscr_p10"] = result["dscr"]["p10"][-1]
    result["final_dscr_p90"] = result["dscr"]["p90"][-1]

    return result


def run_margin_simulation():
    base_output = 0.0
    gdp_coeff = 0.30        # safe default
    jobs_coeff = 4.0        # safe default
    source_tag = "Estimate"
    df_mult = pd.DataFrame() # safe default for dynamic multiplier lookup

    if not ENGINE_AVAILABLE or not target_codes:
        # Nothing to resolve – fall through to ultimate fallback below
        pass

    elif target_codes == "BASKET:primary_agriculture":
        # ── PATH A: Basket Aggregation ("All farm types") ──────────────
        # This path is already validated – it sums all granular IO codes.
        basket_df = industries_for_basket("primary_agriculture")
        if not basket_df.empty:
            search_codes = basket_df["join_code"].unique().tolist()

            years = available_years(region)
            target_year = max(years) if years else 2022

            # Pre-fetch & filter multipliers: Region + Year (all types)
            try:
                df_mult = load_multipliers()
                mask = (df_mult["GEO"] == region)
                if "YEAR" in df_mult.columns:
                    mask = mask & (df_mult["YEAR"] == target_year)
                df_mult = df_mult[mask]
            except Exception:
                pass
            df_direct = df_mult[df_mult["multiplier_type"].str.contains("Direct", case=False)] if not df_mult.empty else df_mult

            total_real_output = 0.0
            weighted_gdp_accum = 0.0
            weighted_jobs_accum = 0.0
            found_codes_count = 0

            for c in search_codes:
                val = get_actual_output(region, target_year, [c])
                if val > 0:
                    total_real_output += val
                    found_codes_count += 1
                    m_gdp, m_jobs = _coefficients_for_code(df_direct, c)
                    weighted_gdp_accum += val * m_gdp
                    weighted_jobs_accum += val * m_jobs

            if total_real_output > 0:
                base_output = total_real_output
                gdp_coeff = weighted_gdp_accum / total_real_output
                jobs_coeff = weighted_jobs_accum / total_real_output
                if found_codes_count > 1:
                    source_tag = f"StatCan IO ({target_year}) [Basket Agg]"
                else:
                    source_tag = f"StatCan IO ({target_year})"

    elif target_codes == "SPECIFIC" and naics_code:
        # ── PATH B: Specific Commodity – Hybrid Logic ─────────────────
        years = available_years(region)
        target_year = max(years) if years else 2022

        # Pre-fetch & filter multipliers: Region + Year (all types)
        try:
            df_mult = load_multipliers()
            mask = (df_mult["GEO"] == region)
            if "YEAR" in df_mult.columns:
                mask = mask & (df_mult["YEAR"] == target_year)
            df_mult = df_mult[mask]
        except Exception:
            pass
        df_direct = df_mult[df_mult["multiplier_type"].str.contains("Direct", case=False)] if not df_mult.empty else df_mult

        # ── Step 1: Gold Standard – direct IO output for this code ──
        granular_output = get_actual_output(region, target_year, [naics_code])

        if granular_output > 0:
            # Perfect match: use IO output AND IO multipliers
            base_output = granular_output
            gdp_coeff, jobs_coeff = _coefficients_for_code(df_direct, naics_code)
            source_tag = f"StatCan IO ({target_year})"

        else:
            # ── Step 2: Share-Based Apportionment ──────────────────
            # Census expenses are on a different scale than IO output
            # (Census ≈ $44B for Ontario vs IO ≈ $21B), so we CANNOT
            # use: Revenue = Census_Expenses / (1 - GDP%).
            #
            # Instead:
            #   1. Get IO basket total (same as "All farm types")
            #   2. Census share = sub_expenses / all_farm_expenses
            #   3. Revenue = IO_total × share
            #
            # This guarantees sub-sector revenue ≤ total.

            proxy_code = _resolve_proxy(naics_code)

            # Get proxy multiplier coefficients (efficiency)
            proxy_gdp, proxy_jobs = 0.0, 0.0
            if proxy_code and not df_direct.empty:
                proxy_gdp, proxy_jobs = _coefficients_for_code(df_direct, proxy_code)

            # Compute the IO basket total for all primary agriculture
            io_basket_total = 0.0
            basket_df = industries_for_basket("primary_agriculture")
            if not basket_df.empty:
                for c in basket_df["join_code"].unique().tolist():
                    io_basket_total += get_actual_output(region, target_year, [c])

            # Compute Census expense share for this sub-sector
            all_farm_key = f"{region}|All farm types"
            all_farm_data = expense_profiles.get(all_farm_key, {})
            all_farm_expenses = all_farm_data.get("total_expenses_raw", 0)

            if io_basket_total > 0 and all_farm_expenses > 0 and sector_total_expenses > 0:
                census_share = sector_total_expenses / all_farm_expenses
                
                # Red Team Fix: Margin Calibration Factor
                # True Revenue Share = Expense Share * ((1 - avg_margin) / (1 - sector_margin))
                avg_gdp_margin = 0.30 # Approximate provincial average for primary agriculture
                margin_calibration = 1.0
                if proxy_gdp > 0 and proxy_gdp < 1.0:
                    margin_calibration = (1.0 - avg_gdp_margin) / (1.0 - proxy_gdp)
                    margin_calibration = max(0.5, min(2.0, margin_calibration)) # Bounded for safety
                
                calibrated_share = census_share * margin_calibration
                base_output = io_basket_total * calibrated_share
                
                # Use proxy coefficients for margin/jobs if available
                if proxy_gdp > 0:
                    gdp_coeff = proxy_gdp
                    jobs_coeff = proxy_jobs
                source_tag = f"IO Calibrated Share ({calibrated_share:.1%}) + IO Margin ({target_year})"
            # else: base_output stays 0 → ultimate fallback below

    # ── Ultimate Fallback ──────────────────────────────────────────────
    if base_output == 0:
        if sector_total_expenses > 0:
            base_output = sector_total_expenses / (1.0 - gdp_coeff)
            source_tag = "Census Estimate (Expense Derived)"
        else:
            # Model Provincial Industry-Wide impact as requested
            try:
                # Target year might not be initialized if we fast-tracked to the fallback
                _years = available_years(region) if ENGINE_AVAILABLE else []
                _safe_year = max(_years) if _years else 2022
                
                # Fetch multipliers defensively for coefficient weighting
                try:
                    _df_m = load_multipliers()
                    _mask = (_df_m["GEO"] == region)
                    if "YEAR" in _df_m.columns:
                        _mask = _mask & (_df_m["YEAR"] == _safe_year)
                    _df_m = _df_m[_mask]
                    _df_d = _df_m[_df_m["multiplier_type"].str.contains("Direct", case=False)] if not _df_m.empty else _df_m
                except Exception:
                    _df_d = pd.DataFrame()
                
                proxy_macro_total = 0.0
                _weighted_gdp = 0.0
                _weighted_jobs = 0.0
                basket_macro_df = industries_for_basket("primary_agriculture")
                
                if not basket_macro_df.empty:
                    for c in basket_macro_df["join_code"].unique().tolist():
                        _val = get_actual_output(region, _safe_year, [c])
                        if _val > 0:
                            proxy_macro_total += _val
                            _m_gdp, _m_jobs = _coefficients_for_code(_df_d, c)
                            _weighted_gdp += _val * _m_gdp
                            _weighted_jobs += _val * _m_jobs
            except Exception:
                proxy_macro_total = 0.0
                
            if proxy_macro_total > 0:
                base_output = proxy_macro_total
                gdp_coeff = _weighted_gdp / proxy_macro_total
                jobs_coeff = _weighted_jobs / proxy_macro_total
                source_tag = "Provincial Industry-Wide Aggregate"
            else:
                base_output = 100_000_000
                source_tag = "Generic $100M Baseline (Proxy Failed)"

    # ── Downstream Calculations (Economist Remediation) ───────────────
    base_gdp = base_output * gdp_coeff
    base_jobs = (base_output / 1_000_000) * jobs_coeff

    delta_revenue_shock = base_output * (shock_revenue / 100.0)
    new_revenue = base_output + delta_revenue_shock

    expense_bill = base_output * (1.0 - gdp_coeff)

    # ── FIX #1: Use INTERMEDIATE ratios (normalized denominator) ──────
    # These ratios exclude Labor/Interest/Depreciation from the
    # denominator, so they map correctly to the IO expense_bill.
    hits = {
        "Fertilizer":  expense_bill * intermediate_profile.get('fertilizer', 0)  * (shock_fert / 100.0),
        "Energy":      expense_bill * intermediate_profile.get('energy', 0)      * (shock_energy / 100.0),
        "Feed":        expense_bill * intermediate_profile.get('feed', 0)        * (shock_feed / 100.0),
        "Crop Inputs": expense_bill * intermediate_profile.get('crop_inputs', 0) * (shock_crop / 100.0),
    }

    total_cost_shock = sum(hits.values())
    delta_gdp = delta_revenue_shock - total_cost_shock
    final_gdp = base_gdp + delta_gdp

    # ── FIX #2: Value-Added shocks (GDP-preserving) ───────────────────
    # Wages and Interest are PART of GDP (Income Approach). A wage hike
    # transfers money from Profits to Labor within the sector — GDP is
    # unchanged. We compute the dollar impact for informational display.
    labor_dollars_census   = profile_data.get("labor_dollars", 0)
    interest_dollars_census = profile_data.get("interest_dollars", 0)
    # Scale Census dollars to IO-based revenue
    census_rev_est = sector_total_expenses / (1.0 - gdp_coeff) if (gdp_coeff < 1 and sector_total_expenses > 0) else 0
    io_scale = base_output / census_rev_est if census_rev_est > 0 else 1.0
    va_labor_hit    = labor_dollars_census   * io_scale * (shock_labor / 100.0)
    va_interest_hit = interest_dollars_census * io_scale * (shock_interest / 100.0)
    profit_squeeze  = va_labor_hit + va_interest_hit

    # ── FIX #3: Dynamic Type I (Supply Chain) multiplier ────────────────────────────
    # Replaces Type II total multiplier with Type I simple multiplier for defensibility.
    type1_gdp_mult = 1.35  # conservative fallback
    type1_jobs_mult = 1.35 # conservative fallback
    try:
        if not df_mult.empty:
            proxy_lookup = _resolve_proxy(naics_code) if naics_code else None
            lookup_codes = [proxy_lookup] if proxy_lookup else search_codes if 'search_codes' in dir() else []
            for lc in lookup_codes:
                # GDP Multiplier
                row_t1 = df_mult[
                    (df_mult["join_code"] == str(lc)) &
                    (df_mult["multiplier_type"].str.contains("Simple", case=False)) &
                    (df_mult["variable"].str.contains("Gross domestic", case=False))
                ]
                if not row_t1.empty:
                    simple_gdp_coeff = float(row_t1["value"].iloc[0])
                    # Type I ratio = Simple / Direct 
                    if gdp_coeff > 0:
                        type1_gdp_mult = simple_gdp_coeff / gdp_coeff
                        
                # Jobs Multiplier (Type I)
                row_jobs_t1 = df_mult[
                    (df_mult["join_code"] == str(lc)) &
                    (df_mult["multiplier_type"].str.contains("Type I", case=False)) &
                    (df_mult["variable"].str.contains("Jobs", case=False))
                ]
                if not row_jobs_t1.empty:
                    type1_jobs_mult = float(row_jobs_t1["value"].iloc[0])
                    
                if not row_t1.empty:
                    break
    except Exception:
        pass  # keep fallbacks

    macro_gdp_impact = delta_gdp * type1_gdp_mult
    macro_indirect_gdp = macro_gdp_impact - delta_gdp

    # E-2 Fix: Jobs depend on physical volume (revenue shocks simulate price drops or volume
    # loss, but cost inflation only hits margin). Revenue shock proxy stands in for volume here.
    pct_change_vol = shock_revenue / 100.0
    direct_jobs_impact = base_jobs * pct_change_vol * EMPLOYMENT_ELASTICITY
    macro_jobs_impact = direct_jobs_impact * type1_jobs_mult
    macro_indirect_jobs = macro_jobs_impact - direct_jobs_impact

    return {
        "base_output": base_output,
        "base_gdp": base_gdp,
        "base_jobs": base_jobs,
        "final_output": new_revenue,
        "final_gdp": final_gdp,
        "hits": hits,
        "macro_gdp": macro_gdp_impact,
        "macro_indirect_gdp": macro_indirect_gdp,
        "macro_jobs": macro_jobs_impact,
        "direct_jobs_impact": direct_jobs_impact,
        "macro_indirect_jobs": macro_indirect_jobs,
        "source": source_tag,
        "margin_pct": gdp_coeff,
        "profit_squeeze": profit_squeeze,
        "va_labor_hit": va_labor_hit,
        "va_interest_hit": va_interest_hit,
        "type1_mult": type1_gdp_mult,
        "type1_jobs_mult": type1_jobs_mult
    }

sim = run_margin_simulation()

# --- 6. DASHBOARD ---
region_adj = "national" if region == "Canada" else "provincial"
region_noun = "country" if region == "Canada" else "province"

st.title(f"🔮 {region} Farm Shock Simulator")
headline_container = st.container()
st.caption(f"Context: {selected_name} | Baseline: StatCan IO (2021) | Basket App: Value-Added Share (GDP): {sim['margin_pct']:.1%}", 
    help="This is NOT Net Profit. It is the sector's contribution to GDP (Value Added), which includes Wages, Rent, Interest, Depreciation, and Taxes."
)

def fmt(val):
    if abs(val) >= 1_000_000_000: return f"${val/1_000_000_000:.2f}B"
    return f"${val/1_000_000:.1f}M"

# Report-safe format: escapes $ for Streamlit markdown (prevents LaTeX rendering)
def rfmt(val):
    if abs(val) >= 1_000_000_000: return f"\\${val/1_000_000_000:.2f}B"
    return f"\\${val/1_000_000:.1f}M"

col1, col2, col3 = st.columns(3)
col1.metric("Industry Revenue", 
            fmt(sim['final_output']), 
            delta=f"{(sim['final_output'] - sim['base_output'])/sim['base_output']:.1%}")

col2.metric("Total Cost Shock", 
            fmt(sum(sim['hits'].values())), 
            delta="Sector Expenses", delta_color="inverse")

gdp_delta = (sim['final_gdp'] - sim['base_gdp']) / sim['base_gdp']
col3.metric("Net Sector Income (GDP)", 
            fmt(sim['final_gdp']), 
            delta=f"{gdp_delta:.1%}")

st.markdown("---")

# ── Financial Health Benchmarks (Phase 4A) ────────────────────────────
if financial_health_df is not None and not financial_health_df.empty:
    with st.expander("📊 Farm Financial Health Benchmarks by Province", expanded=False):
        _fh_display = financial_health_df.copy()
        _fh_year = int(_fh_display["data_year"].iloc[0]) if "data_year" in _fh_display.columns else "N/A"

        _fh_cols = {
            "geo": "Province",
            "debt_to_asset": "Debt/Asset",
            "interest_coverage": "Interest Coverage",
            "implied_dscr": "Implied DSCR",
            "equity_M": "Equity ($M)",
            "amortization_rate": "Amort. Rate",
            "total_assets_M": "Total Assets ($M)",
        }
        _fh_avail = {k: v for k, v in _fh_cols.items() if k in _fh_display.columns}
        _fh_table = _fh_display[list(_fh_avail.keys())].rename(columns=_fh_avail)

        def _highlight_selected(row):
            if row["Province"] == region:
                return ["background-color: #e8f5e9; font-weight: bold"] * len(row)
            return [""] * len(row)

        st.dataframe(
            _fh_table.style
            .apply(_highlight_selected, axis=1)
            .format({
                "Debt/Asset": "{:.1%}",
                "Interest Coverage": "{:.2f}",
                "Implied DSCR": "{:.2f}",
                "Equity ($M)": "${:,.0f}",
                "Amort. Rate": "{:.1%}",
                "Total Assets ($M)": "${:,.0f}",
            }),
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            f"Source: Statistics Canada — Farm Balance Sheet & Financial Health ({_fh_year}). "
            f"Selected province ({region}) highlighted in green. "
            "These benchmarks inform the Debt-to-Asset Ratio and DSCR calculations in the projection engine."
        )

col_L, col_R = st.columns([2, 1])

with col_L:
    st.subheader("📉 Sector Margin Analysis")
    measure = ["relative", "relative"] 
    x = ["Baseline GDP", "Rev Change"]
    y = [sim['base_gdp'], (sim['final_output'] - sim['base_output'])]
    
    for k, v in sim['hits'].items():
        if v > 0:
            measure.append("relative")
            x.append(k)
            y.append(-v)
            
    measure.append("total")
    x.append("Final GDP")
    y.append(sim['final_gdp'])

    fig = go.Figure(go.Waterfall(
        name = "20", orientation = "v",
        measure = measure, x = x, y = y,
        textposition = "outside",
        connector = {"line":{"color":"rgb(63, 63, 63)"}},
        decreasing = {"marker":{"color":"#c62828"}},
        increasing = {"marker":{"color":"#2e7d32"}},
        totals = {"marker":{"color":"#1565c0"}}
    ))
    fig.update_layout(height=450, title=f"Aggregate Impact on {region_adj.capitalize()} Sector GDP")
    st.plotly_chart(fig, use_container_width=True)

    # ── Value-Added Info Card (Profit Squeeze) ────────────────────────
    if sim['profit_squeeze'] > 0:
        va_parts = []
        if sim['va_labor_hit'] > 0:
            va_parts.append(f"{fmt(sim['va_labor_hit'])} from wages")
        if sim['va_interest_hit'] > 0:
            va_parts.append(f"{fmt(sim['va_interest_hit'])} from interest")
        va_detail = " and ".join(va_parts)
        st.info(
            f"💰 **Profit Redistribution**: {va_detail} would shift from sector profits "
            f"to labor & lenders ({fmt(sim['profit_squeeze'])} total). "
            f"GDP is unaffected — this is an internal transfer within Value Added."
        )

with col_R:
    st.subheader("🏛️ Policy Impact")
    st.info(f"Aggregate supply chain fallout for the {region_noun} (Type I multiplier: **{sim.get('type1_mult', 1.35):.2f}×**).")
    
    is_positive = sim['macro_gdp'] > 0
    lbl_gdp = "Supply Chain Ripple Effects"
    lbl_jobs = "Jobs Created" if is_positive else "Jobs at Risk"
    
    pct_gdp = sim['macro_gdp'] / sim['base_gdp'] * 100 if sim['base_gdp'] > 0 else 0
    
    st.metric(lbl_gdp, 
              fmt(sim['macro_gdp']),
              delta=f"{pct_gdp:+.1f}% {region_adj.capitalize()} GDP", delta_color="normal")
              
    cA, cB = st.columns(2)
    with cA:
        lbl_dir = "Direct Farm Impact"
        st.metric(lbl_dir, fmt(sim['final_gdp'] - sim['base_gdp']))
    with cB:
        lbl_ind = "Indirect Impact"
        st.metric(lbl_ind, fmt(sim.get('macro_indirect_gdp', 0)))
              
    lbl_jobs = "Supply Chain Jobs Created" if is_positive else "Total Supply Chain Jobs at Risk"
    st.metric(lbl_jobs, 
              f"{int(sim['macro_jobs']):,}",
              delta=f"Type I Multiplier: {sim.get('type1_jobs_mult', 1.35):.2f}×", delta_color="off")
              
    cC, cD = st.columns(2)
    with cC:
        st.metric("Direct Farm Jobs", f"{int(sim.get('direct_jobs_impact', 0)):,}")
    with cD:
        st.metric("Indirect Jobs", f"{int(sim.get('macro_indirect_jobs', 0)):,}")

# ── FIX #4: Leontief Assumption Footnote ──────────────────────────────
st.caption(
    "⚠️ Estimates assume standard economic rules where farmers cannot instantly change their operations. "
    "Actual costs may be lower if producers substitute away from expensive inputs."
)

# ═══════════════════════════════════════════════════════════════════════
# ── 7. MULTI-YEAR DYNAMIC PROJECTION ──────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════

BASELINE_TFP = base_tfp_growth  # Reference TFP growth rate (%/yr) for baseline comparison

# ── COMMODITY IMPACT BREAKDOWN (Tariff Scenarios) ──
if tariff_active and tariff_commodity == "All Primary Agriculture" and tariff_commodity_breakdown:
    st.markdown("---")
    st.subheader("🌾 Tariff Impact by Commodity")
    st.caption(f"How the **{tariff_pct}% {tariff_country}** tariff distributes across Canada's agricultural sectors (national-level analysis)")
    
    # Sort breakdown by absolute dollar impact (descending)
    _sorted_breakdown = sorted(tariff_commodity_breakdown, key=lambda x: abs(x['dollar_impact']), reverse=True)
    
    # Prepare Plotly chart
    import plotly.graph_objects as go
    _plot_df = pd.DataFrame(_sorted_breakdown)
    fig_comm = go.Figure()
    
    colors = ['#cbd5e1' if sm else '#ef4444' for sm in _plot_df['sm_shielded']]
    
    fig_comm.add_trace(go.Bar(
        x=_plot_df['dollar_impact'] / 1e6, # in millions
        y=_plot_df['commodity'],
        orientation='h',
        marker_color=colors,
        text=[f"{imp:+.1f}% (Exp: {exp:.0%})" for imp, exp in zip(_plot_df['revenue_impact_pct'], _plot_df['total_exposure'])],
        textposition='outside'
    ))
    
    fig_comm.update_layout(
        title="Estimated Revenue Impact ($M)",
        yaxis={'autorange': 'reversed'},
        margin=dict(l=0, r=0, t=30, b=0),
        height=350,
        xaxis_title="$ Millions"
    )
    st.plotly_chart(fig_comm, use_container_width=True)
    
    # Summary Table
    _table_data = []
    _total_impact_pct = 0.0
    _total_dollar_impact = 0.0
    _total_fcr = 0.0
    for _item in _sorted_breakdown:
        _table_data.append({
            "Commodity": _item['commodity'] + (" (SM)" if _item['sm_shielded'] and "(SM)" not in _item['commodity'] else ""),
            "Production Revenue": f"${_item['fcr_revenue']/1e9:,.1f}B",
            "Export Exposure": f"{_item['direct_exposure']:.1%}",
            "Total Exposure": f"{_item['total_exposure']:.1%}",
            "Absorption": f"{_item['pass_through']:.0%}",
            "Revenue Impact": f"{_item['revenue_impact_pct']:+.1f}%",
            "Est. $ Impact": f"${_item['dollar_impact']/1e6:,.1f}M"
        })
        _total_impact_pct += _item['revenue_impact_pct'] * _item['weight']
        _total_dollar_impact += _item['dollar_impact']
        _total_fcr += _item['fcr_revenue']
        
    _table_data.append({
        "Commodity": "Weighted Total",
        "Production Revenue": f"${_total_fcr/1e9:,.1f}B",
        "Export Exposure": "",
        "Total Exposure": "",
        "Absorption": "",
        "Revenue Impact": f"{_total_impact_pct:+.1f}%",
        "Est. $ Impact": f"${_total_dollar_impact/1e6:,.1f}M"
    })
    
    st.dataframe(pd.DataFrame(_table_data), use_container_width=True, hide_index=True)
    st.caption("*Production revenue base: StatCan Farm Cash Receipts (32-10-0045). Muted bars denote Supply-Managed (SM) sectors.*")

# ── COMMODITY IMPACT BREAKDOWN (Cost Shocks) ──
if cost_commodity_breakdown:
    st.markdown("---")
    st.subheader("⛽ Cost Shock Exposure by Commodity")
    st.caption("How input cost spikes distribute across Canada's agricultural sectors based on Census expense structures.")
    
    _sorted_costs = sorted(cost_commodity_breakdown, key=lambda x: abs(x['dollar_impact']), reverse=True)
    
    # Narrative
    st.markdown("#### Winners & Losers")
    st.markdown(
        "> Different farm types have vastly different cost structures. Greenhouses face disproportionate exposure to energy and labor shocks, "
        "while grain farms are heavily penalized by fertilizer spikes. The table below isolates the dollar impact across all major commodity groups."
    )
    
    import plotly.graph_objects as go
    _cplot_df = pd.DataFrame(_sorted_costs)
    fig_costs = go.Figure()
    
    fig_costs.add_trace(go.Bar(
        x=_cplot_df['dollar_impact'] / 1e6, # in millions
        y=_cplot_df['commodity'],
        orientation='h',
        marker_color='#f59e0b',
        text=[f"${imp/1e6:,.1f}M" for imp in _cplot_df['dollar_impact']],
        textposition='outside'
    ))
    
    fig_costs.update_layout(
        title="Estimated Cost Increase ($M)",
        yaxis={'autorange': 'reversed'},
        margin=dict(l=0, r=0, t=30, b=0),
        height=350,
        xaxis_title="$ Millions"
    )
    st.plotly_chart(fig_costs, use_container_width=True)
    
    _ctable_data = []
    for _item in _sorted_costs:
        _ctable_data.append({
            "Commodity": _item['commodity'],
            "Total Expenses Base": f"${_item['total_expenses']/1e9:,.1f}B",
            "Est. Cost Increase": f"${_item['dollar_impact']/1e6:,.1f}M"
        })
    st.dataframe(pd.DataFrame(_ctable_data), use_container_width=True, hide_index=True)


st.markdown("---")
st.subheader("📈 Multi-Year Dynamic Projection")

# Classify sector for coefficients
sector_key = naics_code or selected_name
sector_params = _classify_sector(sector_key)

# Attach CapEx baseline data to sim dict for projection engine (region-specific)
capex_baseline = load_capex_baseline(region)
sim["capex_data"] = capex_baseline  # None if CSV not available → fallback estimation

# Attach financial health data (Phase 2: real debt, income, interest rates)
if financial_health_df is not None:
    _fh_proj = financial_health_df[financial_health_df["geo"] == region]
    if _fh_proj.empty:
        _fh_proj = financial_health_df[financial_health_df["geo"] == "Canada"]
    sim["financial_health"] = _fh_proj.iloc[0].to_dict() if not _fh_proj.empty else None
else:
    sim["financial_health"] = None

capex_geo = capex_baseline.get('geo', region) if capex_baseline else None
capex_source = f"StatCan CapEx ({capex_baseline['data_year']}, {capex_geo})" if capex_baseline else "Estimated from output"

# Determine actual δ being used (data-driven or sector default)
_actual_delta = sector_params['delta']
_delta_source = ""
if sim.get("financial_health"):
    _fh_delta = sim["financial_health"].get("depreciation_rate")
    if _fh_delta and _fh_delta == _fh_delta:  # not None or NaN
        _actual_delta = float(_fh_delta)
        _delta_source = " (data)"

# Compute labor metrics for this region
_tfw_dep = 0.0
_base_vacancy = 0.074  # CAHRC default
_vacancy_source = ""
if _labor_row is not None:
    _tfw_dep = float(_labor_row['tfw_dependency'])
    _base_vacancy = float(_labor_row['base_vacancy_rate'])
    _vacancy_source = " (data)"

# Apply sector archetype scaling
_tfw_multiplier = sector_params.get("tfw_multiplier", 1.0)
_adjusted_tfw_dep = min(_tfw_dep * _tfw_multiplier, 0.95)

st.caption(
    f"Sector archetype: **{sector_params['label']}** "
    f"(α={sector_params['alpha']}, δ={_actual_delta:.0%}{_delta_source}, "
    f"φ={sector_params['phi']}, lag={sector_params['lag']}yr) | "
    f"TFP: **{proj_tfp_growth:.1f}%/yr** vs baseline {BASELINE_TFP:.1f}%/yr | "
    f"K₀ source: {capex_source} | "
    f"Vacancy: {_base_vacancy:.1%}{_vacancy_source}, Sector-Adjusted TFW dep: {_adjusted_tfw_dep:.0%} (Base: {_tfw_dep:.0%})"
)

# Build tariff params dict for dynamic projection
_tariff_proj_params = None
if tariff_active and tariff_tcfg:
    _tariff_weight = 1.0
    if tariff_commodity != "All Primary Agriculture" and selected_name == "All farm types":
        _tariff_weight = _AGG_REVENUE_WEIGHTS.get(tariff_commodity, 1.0)

    _tariff_proj_params = {
        "active": True,
        "tariff_pct": tariff_effective_tariff,  # raw tariff rate (e.g. 0.35)
        "revenue_exposure": tariff_revenue_exposure,  # pre-computed: direct + spillover
        "config": tariff_tcfg,
        "weight": _tariff_weight,
    }

# Run projection — shock persistence determined by user toggle
_is_pulse = (shock_persistence == "One-Time (pulse)")
annual_cost_shock = sum(sim['hits'].values())  # total annual cost burden
projection = run_dynamic_projection(
    sim_y0=sim,
    horizon=proj_horizon,
    debt_ratio=proj_debt_ratio,
    tfp_growth_pct=proj_tfp_growth,
    interest_shock_pct=shock_interest,
    wage_shock_pct=shock_labor,
    sector_params=sector_params,
    annual_cost_shock=annual_cost_shock,
    capex_shock_pct=proj_capex_shock,
    base_vacancy_override=_base_vacancy,
    tfw_reduction_pct=proj_tfw_reduction,
    tfw_dependency=_adjusted_tfw_dep,
    is_pulse=_is_pulse,
    tariff_params=_tariff_proj_params,
)

# ── Monte Carlo uncertainty analysis ──
mc_results = run_monte_carlo_projections(
    sim_y0=sim,
    horizon=proj_horizon,
    debt_ratio=proj_debt_ratio,
    tfp_growth_pct=proj_tfp_growth,
    interest_shock_pct=shock_interest,
    wage_shock_pct=shock_labor,
    sector_params=sector_params,
    annual_cost_shock=annual_cost_shock,
    capex_shock_pct=proj_capex_shock,
    base_vacancy_override=_base_vacancy,
    tfw_reduction_pct=proj_tfw_reduction,
    tfw_dependency=_adjusted_tfw_dep,
    is_pulse=_is_pulse,
    tariff_params=_tariff_proj_params,
)

# ── Baseline trajectory (no shock, reference TFP=1.5%) ──
baseline_sim = {**sim, "final_output": sim["base_output"], "final_gdp": sim["base_gdp"],
                "macro_gdp": 0, "macro_jobs": 0}
no_shock_params = {**sector_params}
baseline_proj = run_dynamic_projection(
    sim_y0=baseline_sim,
    horizon=proj_horizon,
    debt_ratio=proj_debt_ratio,
    tfp_growth_pct=BASELINE_TFP,
    interest_shock_pct=0,
    wage_shock_pct=0,
    sector_params=no_shock_params,
    annual_cost_shock=0.0,
    capex_shock_pct=0,
    base_vacancy_override=_base_vacancy,
    tfw_reduction_pct=0,  # no TFW shock in baseline
    tfw_dependency=_adjusted_tfw_dep,
)

proj_col1, proj_col2 = st.columns([3, 2])

with proj_col1:
    # ── GDP Trajectory Chart ──
    years = [f"Year {p['year']}" for p in projection]
    shocked_gdp = [p["gdp"] / 1e9 for p in projection]
    baseline_gdp = [p["gdp"] / 1e9 for p in baseline_proj]

    # Monte Carlo bands (GDP)
    mc_gdp_p10 = [v / 1e9 for v in mc_results["gdp"]["p10"]]
    mc_gdp_p25 = [v / 1e9 for v in mc_results["gdp"]["p25"]]
    mc_gdp_p75 = [v / 1e9 for v in mc_results["gdp"]["p75"]]
    mc_gdp_p90 = [v / 1e9 for v in mc_results["gdp"]["p90"]]

    fig_proj = go.Figure()

    # P10-P90 band (80% confidence — light)
    fig_proj.add_trace(go.Scatter(
        x=years + years[::-1],
        y=mc_gdp_p90 + mc_gdp_p10[::-1],
        fill="toself", fillcolor="rgba(229,57,53,0.08)",
        line=dict(color="rgba(0,0,0,0)"),
        name="80% confidence",
        showlegend=True, hoverinfo="skip",
    ))
    # P25-P75 band (50% confidence — darker)
    fig_proj.add_trace(go.Scatter(
        x=years + years[::-1],
        y=mc_gdp_p75 + mc_gdp_p25[::-1],
        fill="toself", fillcolor="rgba(229,57,53,0.18)",
        line=dict(color="rgba(0,0,0,0)"),
        name="50% confidence",
        showlegend=True, hoverinfo="skip",
    ))

    fig_proj.add_trace(go.Scatter(
        x=years, y=baseline_gdp, mode="lines+markers",
        name=f"Baseline (TFP {BASELINE_TFP}%, No Shocks)",
        line=dict(color="#43a047", width=2, dash="dash"),
        marker=dict(size=6),
    ))
    fig_proj.add_trace(go.Scatter(
        x=years, y=shocked_gdp, mode="lines+markers",
        name=f"Scenario (TFP {proj_tfp_growth}%)",
        line=dict(color="#e53935", width=3),
        marker=dict(size=8),
    ))
    fig_proj.update_layout(
        title="Sector GDP Trajectory ($B) — with Uncertainty Bands",
        yaxis_title="GDP ($B)",
        xaxis_title="",
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    st.plotly_chart(fig_proj, use_container_width=True)

    # ── Capital Stock Chart ──
    shocked_k = [p["capital_stock"] / 1e9 for p in projection]
    baseline_k = [p["capital_stock"] / 1e9 for p in baseline_proj]

    fig_k = go.Figure()
    fig_k.add_trace(go.Scatter(
        x=years, y=baseline_k, mode="lines+markers",
        name="Baseline Capital",
        line=dict(color="#43a047", width=2, dash="dash"),
        marker=dict(size=6),
    ))
    fig_k.add_trace(go.Scatter(
        x=years, y=shocked_k, mode="lines+markers",
        name="Scenario Capital",
        line=dict(color="#ff9800", width=3),
        marker=dict(size=8),
        fill="tonexty", fillcolor="rgba(255,152,0,0.10)",
    ))
    fig_k.update_layout(
        title="Capital Stock Trajectory ($B)",
        yaxis_title="Capital Stock ($B)",
        xaxis_title="",
        height=350,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    st.plotly_chart(fig_k, use_container_width=True)
    # Note when capital lines overlap (no FSF difference)
    k_diff = abs(shocked_k[-1] - baseline_k[-1])
    if k_diff < 0.01:
        st.caption("ℹ️ Scenario and Baseline capital lines overlap — no difference in investment behavior under current settings.")

with proj_col2:
    # ── Summary Metrics ──
    final_yr = projection[-1]
    yr0 = projection[0]
    cumulative_gdp_loss = sum(p["gdp"] - baseline_proj[i]["gdp"]
                              for i, p in enumerate(projection))

    st.markdown("#### 📊 Cumulative Impact")
    mc1, mc2 = st.columns(2)

    with mc1:
        st.metric("GDP vs Baseline (Final)",
                  fmt(final_yr['gdp'] - baseline_proj[-1]['gdp']),
                  delta=f"{(final_yr['gdp']/baseline_proj[-1]['gdp'] - 1)*100:+.1f}% vs baseline",
                  delta_color="normal")
        capital_change = (final_yr['capital_stock'] / yr0['capital_stock'] - 1) * 100
        st.metric("Capital Stock Change",
                  f"{capital_change:+.1f}%",
                  delta=f"Year {proj_horizon} vs Year 0",
                  delta_color="normal" if capital_change >= 0 else "inverse")

    with mc2:
        st.metric(f"Cumulative GDP ({proj_horizon}yr)",
                  fmt(cumulative_gdp_loss),
                  delta=f"{proj_horizon}-year total",
                  delta_color="inverse" if cumulative_gdp_loss < 0 else "normal")
    st.markdown("---")

    # ── Year-by-Year Table ──
    st.markdown("#### 📋 Year-by-Year Detail")
    table_data = []
    for i, p in enumerate(projection):
        bl = baseline_proj[i]
        # Gap needs to be a float for the styler to work properly, we'll format it inside the styler or keep it simple
        table_data.append({
            "Year": f"Yr {p['year']}",
            "Output ($B)": f"{p['output']/1e9:.2f}",
            "GDP ($B)": f"{p['gdp']/1e9:.2f}",
            "GDP Impact ($M)": (p['gdp'] - bl['gdp'])/1e6,
        })
        
    df_table = pd.DataFrame(table_data).set_index("Year")
    
    def color_gap(val):
        if pd.isna(val): return ''
        if val < -0.01: return 'color: #d32f2f; font-weight: bold'
        elif val > 0.01: return 'color: #388e3c; font-weight: bold'
        return ''
        
    # Format the float back to a string with a + sign in the pandas styler
    styled_df = df_table.style.format({"GDP Impact ($M)": "{:+.0f}"}).map(color_gap, subset=['GDP Impact ($M)'])

    st.dataframe(
        styled_df,
        use_container_width=True,
        height=min(250, 35 * (proj_horizon + 2)),
    )

# ── Dynamic Model Footnote ──
st.caption(
    f"📐 Dynamic model: K(t+1) = K(t)·(1−δ) + I(t−{sector_params['lag']}). "
    f"Output = A·K^α · LRF. Coefficients from AAFC/FCC/CAHRC research. "
    f"Shock mode: {'Pulse (Year 1 only)' if _is_pulse else 'Persistent'}."
)
# C2: K₀ anomaly warning
_k0_warn = projection[0].get("k0_warning")
if _k0_warn:
    st.warning(f"⚠️ Capital Stock Warning: {_k0_warn}")

# ═══════════════════════════════════════════════════════════════════════
# ── 8. AUTO-GENERATED SCENARIO REPORT ─────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════

st.markdown("---")
st.subheader("📄 Scenario Report")

# ── Gather all scenario inputs ──
active_shocks = []
# Only list the basic revenue shock if it wasn't overwritten by the tariff engine
if shock_revenue != 0 and not tariff_active:
    direction = "increase" if shock_revenue > 0 else "decrease"
    active_shocks.append(f"a **{abs(shock_revenue)}% {direction}** in market prices/yields")
if shock_fert > 0:
    active_shocks.append(f"a **{shock_fert}%** rise in fertilizer costs")
if shock_energy > 0:
    active_shocks.append(f"a **{shock_energy}%** rise in energy/fuel costs")
if shock_labor > 0:
    active_shocks.append(f"a **{shock_labor}%** increase in wages")
if shock_feed > 0:
    active_shocks.append(f"a **{shock_feed}%** increase in feed costs")
if shock_crop > 0:
    active_shocks.append(f"a **{shock_crop}%** increase in seed/pesticide costs")
if shock_interest > 0:
    active_shocks.append(f"a **{shock_interest}%** increase in interest rates")
if proj_capex_shock != 0:
    direction = "increase" if proj_capex_shock > 0 else "decrease"
    active_shocks.append(f"a **{abs(proj_capex_shock)}%** {direction} in capital investment")
if proj_tfw_reduction > 0:
    active_shocks.append(f"a **{proj_tfw_reduction}%** reduction in TFW program access")
if tariff_active and tariff_detail:
    active_shocks.append(f"a trade shock: {tariff_detail}")

tfp_changed = abs(proj_tfp_growth - BASELINE_TFP) > 0.01
if tfp_changed:
    direction = "increase" if proj_tfp_growth > BASELINE_TFP else "decrease"
    active_shocks.append(f"a productivity (TFP) {direction} from {BASELINE_TFP:.1f}% to {proj_tfp_growth:.1f}% per year")

# ── Final-year results ──
final = projection[-1]
bl_final = baseline_proj[-1]
yr0 = projection[0]
cumulative_gap = sum(p["gdp"] - baseline_proj[i]["gdp"] for i, p in enumerate(projection))
cap_change_pct = (final["capital_stock"] / yr0["capital_stock"] - 1) * 100
final_dscr = final["dscr"]

# ── Dynamic Executive Headline ──
if active_shocks or tfp_changed:
    # Determine primary driver for narrative
    if tariff_active and not (shock_fert > 0 or shock_energy > 0 or shock_labor > 0):
        shock_str = f"A **{tariff_pct}% {tariff_country} tariff shock**"
    elif not tariff_active and (shock_fert > 0 or shock_energy > 0):
        shock_str = "An **input cost shock**"
    elif tariff_active and (shock_fert > 0 or shock_energy > 0):
        shock_str = f"A **{tariff_pct}% {tariff_country} tariff** combined with **rising input costs**"
    elif proj_tfw_reduction > 0 and shock_labor > 0:
        shock_str = "A **severe labor shortage and wage spike**"
    else:
        shock_str = "A **combined economic shock**"
        
    if cumulative_gap < -1_000_000:
        headline = (f"{shock_str} is projected to drain **{fmt(abs(cumulative_gap))} in cumulative Farm Sector GDP** over {proj_horizon} years. "
                    f"When accounting for broader supply chain ripples, the **Year 1 shock poses {fmt(abs(sim['macro_gdp']))} in risk to the {region_adj} economy**.")
        headline_container.error(headline, icon="📉")
    elif cumulative_gap > 1_000_000:
        headline = (f"{shock_str} is projected to add **{fmt(cumulative_gap)} in cumulative Farm Sector GDP** over {proj_horizon} years. "
                    f"When accounting for broader supply chain ripples, the **Year 1 shock poses a {fmt(sim['macro_gdp'])} boost to the {region_adj} economy**.")
        headline_container.success(headline, icon="📈")
    else:
        headline = f"The scenario generates a marginal impact on Farm Sector GDP (**{fmt(cumulative_gap)}** over {proj_horizon} years)."
        headline_container.warning(headline, icon="⚠️")
else:
    headline = f"Under baseline conditions ({BASELINE_TFP}% TFP growth, no shocks), the sector remains stable over the projection horizon."
    headline_container.info(headline, icon="ℹ️")

# ── Section 1: Scenario Overview ──
report_parts = []
report_parts.append(f"### 🏷️ Scenario Overview\n")
report_parts.append(
    f"This analysis examines **{selected_name}** in **{region}** over a "
    f"**{proj_horizon}-year** projection horizon. The sector currently generates "
    f"approximately **{rfmt(sim['base_output'])}** in annual output, contributing "
    f"**{rfmt(sim['base_gdp'])}** to {region_adj} GDP "
    f"(a value-added share of **{sim['margin_pct']:.1%}**).\n"
)

# Scenario description
if active_shocks or tfp_changed:
    report_parts.append("**Scenario conditions tested:**\n")
    for s in active_shocks:
        report_parts.append(f"- {s}\n")
    if tfp_changed:
        direction = "higher" if proj_tfp_growth > BASELINE_TFP else "lower"
        report_parts.append(
            f"- Productivity growth (TFP) set to **{proj_tfp_growth:.1f}%/yr** "
            f"({direction} than the {BASELINE_TFP:.1f}% historical baseline)\n"
        )
    report_parts.append(
        f"\nThe analysis assumes a debt-to-asset ratio of **{proj_debt_ratio:.0%}** "
        f"(Regional average: ~18-22%).\n"
    )
    # Shock duration note
    if _is_pulse:
        report_parts.append(
            "\n⚡ **Shock Duration: One-Time (Pulse).** Cost and investment shocks "
            "apply only in Year 1, then revert to baseline. This models transient "
            "events like a single-season drought or temporary supply disruption.\n"
        )
    else:
        report_parts.append(
            "\n🔄 **Shock Duration: Persistent (Structural).** All shocks continue "
            "every year of the projection. This models permanent changes like a "
            "new tariff regime, carbon tax, or structural shift in input costs.\n"
        )
    # TFW labor context
    if proj_tfw_reduction > 0 and _adjusted_tfw_dep > 0:
        tfw_implied_vacancy = _adjusted_tfw_dep * (proj_tfw_reduction / 100.0)
        effective_lrf = max(0.0, 1.0 - sector_params['phi'] * tfw_implied_vacancy)
        output_loss_pct = (1 - effective_lrf) * 100
        report_parts.append(
            f"\n👷 **Labor Impact**: The **{sector_params['label']}** sector in {region} has a Sector-Adjusted TFW dependency of "
            f"**{_adjusted_tfw_dep:.0%}** (derived from the provincial average of {_tfw_dep:.0%} applying a {_tfw_multiplier}x sector multiplier). "
            f"A **{proj_tfw_reduction}%** reduction in TFW access creates "
            f"**{tfw_implied_vacancy:.1%}** additional vacancies, reducing the "
            f"Labor Realization Factor to **{effective_lrf:.2f}** "
            f"(a **{output_loss_pct:.0f}%** output penalty).\n\n"
        )
        report_parts.append(
            f"**How to read these results:** The Immediate Impact section (Year 0) "
            f"reflects only input cost shocks and does **not** capture labor shortages. "
            f"The TFW labor penalty activates in **Year 1 onward** of the Multi-Year "
            f"Projection, reflecting the reality that program changes take at least one "
            f"growing season to affect harvesting, planting, and processing capacity. "
            f"In the Year-by-Year table, watch the **LRF column** — when it drops "
            f"below 1.0, the sector is losing potential output to unfilled positions. "
            f"At LRF = {effective_lrf:.2f}, the sector can only realize "
            f"**{effective_lrf:.0%}** of its productive capacity.\n"
        )
else:
    report_parts.append(
        "*No shocks or TFP changes applied — this report shows the baseline growth trajectory "
        f"at {BASELINE_TFP:.1f}% annual productivity growth.*\n"
    )

# ── Section 2: Immediate Impact (Year 0) ──
report_parts.append(f"\n### ⚡ Immediate Impact (Year 1)\n")

total_shock_val = sum(sim['hits'].values())
if total_shock_val > 0 or shock_revenue != 0:
    if shock_revenue != 0:
        rev_word = "boost" if shock_revenue > 0 else "reduction"
        report_parts.append(
            f"The market price change produces a **{rfmt(abs(sim['final_output'] - sim['base_output']))}** "
            f"revenue {rev_word}. "
        )
    if total_shock_val > 0:
        # Find the biggest cost driver
        biggest_cost = max(sim['hits'].items(), key=lambda x: x[1])
        report_parts.append(
            f"Operating costs increase by **{rfmt(total_shock_val)}**, "
            f"driven primarily by **{biggest_cost[0]}** ({rfmt(biggest_cost[1])}). "
        )
    gdp_y0_change = sim['final_gdp'] - sim['base_gdp']
    if gdp_y0_change < 0:
        report_parts.append(
            f"After accounting for all shocks, sector GDP falls by "
            f"**{rfmt(abs(gdp_y0_change))}** ({gdp_y0_change/sim['base_gdp']:.1%}), "
            f"leaving the sector with **{rfmt(sim['final_gdp'])}** in value added.\n"
        )
    else:
        report_parts.append(
            f"Net sector GDP changes by **{rfmt(gdp_y0_change)}** "
            f"({gdp_y0_change/sim['base_gdp']:+.1%}).\n"
        )

    if sim['profit_squeeze'] > 0:
        report_parts.append(
            f"\nAdditionally, **{rfmt(sim['profit_squeeze'])}** in sector profits "
            f"is redistributed to labor and lenders through wage and interest increases. "
            f"While this does not reduce GDP (it stays within the economy), it squeezes "
            f"farm profitability and cash flow.\n"
        )
        
    if tariff_active and tariff_commodity == "All Primary Agriculture" and tariff_commodity_breakdown:
        report_parts.append(f"\n#### 🌾 Tariff Impact by Commodity\n")
        report_parts.append(f"The {tariff_pct}% {tariff_country} tariff does not affect all sectors equally. The breakdown based on national Farm Cash Receipts is as follows:\n\n")
        
        report_parts.append("> **Winners & Losers**\n")
        report_parts.append("> Livestock sectors (Cattle and Hogs) bear almost half the financial damage due to their deep integration with the US market and the threat of domestic price crashes. ")
        report_parts.append("> Conversely, major crops like Wheat and Canola Seed are globally priced and largely insulated from a US-specific tariff. ")
        report_parts.append("> Supply-managed sectors (Dairy, Poultry) see virtually zero impact due to their domestic focus and Tariff-Rate Quota (TRQ) protections.\n\n")

        report_parts.append("| Commodity | Prod. Revenue | Total Exposure | Est. $ Impact |\n")
        report_parts.append("|---|---|---|---|\n")
        _sorted = sorted(tariff_commodity_breakdown, key=lambda x: abs(x['dollar_impact']), reverse=True)
        for _item in _sorted:
            _sm_tag = " (SM)" if _item['sm_shielded'] and "(SM)" not in _item['commodity'] else ""
            report_parts.append(f"| {_item['commodity']}{_sm_tag} | ${_item['fcr_revenue']/1e9:,.1f}B | {_item['total_exposure']:.1%} | ${_item['dollar_impact']/1e6:,.1f}M |\n")
        report_parts.append("\n*Note: (SM) denotes Supply-Managed sectors which are generally shielded by TRQs.*\n")
        
        report_parts.append("\n> **Note on Revenue Calculation**\n")
        report_parts.append("> Why do the commodity losses differ from the total industry impact? ")
        report_parts.append("> The commodity total represents the direct hit to the sale of physical crops and livestock. ")
        report_parts.append("> The larger industry figure includes the broader ripple effect on secondary farm revenues, such as custom work, land rent, and inter-farm sales, which decline in tandem with commodity prices.\n")
else:
    report_parts.append(
        "With no cost or revenue shocks applied, the sector enters the projection period "
        "at its current baseline level.\n"
    )

# ── Section 3: Multi-Year Outlook ──
report_parts.append(f"\n### 📈 {proj_horizon}-Year Outlook\n")

final_gdp_gap = final["gdp"] - bl_final["gdp"]
gap_pct = (final["gdp"] / bl_final["gdp"] - 1) * 100

if abs(final_gdp_gap) < 1_000_000:
    # No meaningful gap
    report_parts.append(
        f"Over {proj_horizon} years, the scenario trajectory closely tracks the baseline. "
        f"The sector's productive capacity remains stable.\n"
    )
elif final_gdp_gap > 0:
    report_parts.append(
        f"Over {proj_horizon} years, the scenario produces **{rfmt(abs(final_gdp_gap))}** "
        f"more GDP annually by Year {proj_horizon} compared to the baseline "
        f"(**{gap_pct:+.1f}%**). Cumulatively, the economy gains an additional "
        f"**{rfmt(abs(cumulative_gap))}** in sector GDP over the full period.\n"
    )
    if tfp_changed and proj_tfp_growth > BASELINE_TFP:
        report_parts.append(
            f"\nThis growth is primarily driven by higher productivity "
            f"({proj_tfp_growth:.1f}% vs {BASELINE_TFP:.1f}% baseline). "
            f"Each percentage point of TFP growth compounds over time — "
            f"the gap widens every year as technology builds on itself. This illustrates "
            f"the long-term economic value of investing in agricultural R&D, precision "
            f"agriculture, and innovation.\n"
        )
else:
    report_parts.append(
        f"Over {proj_horizon} years, the shock erodes sector GDP by "
        f"**{rfmt(abs(final_gdp_gap))}** annually by Year {proj_horizon} "
        f"(**{gap_pct:+.1f}%** vs baseline). The cumulative GDP loss over the "
        f"full period is **{rfmt(abs(cumulative_gap))}**.\n"
    )
    
    # Add context for Trade Diversion if gap shrinks relative to Year 1
    y1_gap = projection[1]["gdp"] - baseline_proj[1]["gdp"] if len(projection) > 1 else 0
    if tariff_active and y1_gap < 0 and final_gdp_gap > y1_gap:
        report_parts.append(
            f"\n> 📉 **Trade Diversion**: Note that the annual GDP gap is smaller in Year {proj_horizon} "
            f"({rfmt(abs(final_gdp_gap))}) than in Year 1 ({rfmt(abs(y1_gap))}). "
            f"As Canadian agriculture loses access to the {tariff_country} market due to tariffs, the model assumes "
            f"exporters gradually find alternative global markets over time, absorbing some of the lost volume.\n"
        )

# C3: Livestock J-Curve callout
if sector_params.get("label") == "Livestock" and shock_interest > 0:
    report_parts.append(
        f"\n🐂 **Livestock Liquidation Effect**: Interest rate shocks on livestock "
        f"trigger a characteristic J-curve. In Year 1, financial stress forces herd "
        f"liquidation (sell-off), temporarily **increasing** output as animals enter "
        f"the market. From Year 2 onward, the depleted breeding stock means fewer "
        f"calves/piglets, and output **contracts** progressively. Watch the Output column "
        f"in the Year-by-Year table for this pattern.\n"
    )

# Capital dynamics
if abs(cap_change_pct) > 0.5:
    cap_word = "growth" if cap_change_pct > 0 else "erosion"
    report_parts.append(
        f"\nThe sector's capital stock (land, machinery, buildings) shows "
        f"**{cap_change_pct:+.1f}%** net {cap_word} over the period. "
    )
    if cap_change_pct < -2:
        report_parts.append(
            "Declining capital stock means farms are not replacing depreciated equipment "
            "and infrastructure — a warning sign for long-term productive capacity.\n"
        )
    elif cap_change_pct > 2:
        report_parts.append(
            "This reflects healthy reinvestment in farm infrastructure, "
            "supporting future output growth.\n"
        )
    else:
        report_parts.append("Capital is roughly maintained at replacement levels.\n")

# CapEx explanation when slider is active
if proj_capex_shock != 0:
    direction = "more" if proj_capex_shock > 0 else "less"
    abs_pct = abs(proj_capex_shock)
    report_parts.append(
        f"\n> **Note on Capital Investment:** The {abs_pct}% investment change is applied "
        f"**every year** of the projection, not as a one-time event. This models a "
        f"sustained shift — for example, a {abs_pct}% {'increase due to a CapEx incentive program or tax credit' if proj_capex_shock > 0 else 'reduction due to economic uncertainty or credit tightening'}. "
        f"Each year's {'additional' if proj_capex_shock > 0 else 'reduced'} investment compounds through "
        f"the capital stock, producing {'progressively larger output gains' if proj_capex_shock > 0 else 'accelerating output losses'} "
        f"as {'new' if proj_capex_shock > 0 else 'aging'} machinery and infrastructure "
        f"{'enters' if proj_capex_shock > 0 else 'exits'} production.\n"
    )

# Financial health
report_parts.append(f"\n### 🏦 Financial Health\n")
if final_dscr > 1.25:
    report_parts.append(
        f"The sector maintains a **healthy** financial position throughout the projection "
        f"(Debt Service Coverage Ratio: **{final_dscr:.1f}×** in Year {proj_horizon}). "
        f"This ratio (Earnings / Debt Payments) indicates that farm earnings are growing faster than debt obligations, "
        f"meaning farm incomes comfortably cover both interest and principal payments, supporting continued investment.\n"
    )
elif final_dscr > 1.0:
    report_parts.append(
        f"The sector enters **financial stress** territory by Year {proj_horizon} "
        f"(DSCR: **{final_dscr:.2f}×**). While farms can still meet debt obligations, "
        f"the margin of safety is thin. Investment slows as lenders tighten credit, "
        f"and some operations may defer capital expenditures.\n"
    )
else:
    report_parts.append(
        f"The sector enters **crisis territory** by Year {proj_horizon} "
        f"(DSCR: **{final_dscr:.2f}×**). Farm incomes no longer cover debt service, "
        f"triggering asset sales, herd liquidation, and potential defaults. "
        f"This creates a self-reinforcing downward spiral as forced sales depress "
        f"asset values across the sector.\n"
    )

# ── Section 3b: Uncertainty Analysis ──
report_parts.append(f"\n### 🎲 Uncertainty Analysis\n")
report_parts.append(f"The model runs {mc_results.get('n_runs', 200)} random simulations to account for real-world uncertainty like weather and input prices.\n")

# Plain-language description
mc_spread_gdp = mc_results["final_gdp_p90"] - mc_results["final_gdp_p10"]
mc_mid_gdp = (mc_results["final_gdp_p90"] + mc_results["final_gdp_p10"]) / 2
mc_spread_pct = (mc_spread_gdp / mc_mid_gdp * 100) if mc_mid_gdp > 0 else 0

report_parts.append(
    f"The shaded bands on the GDP chart above represent **uncertainty** — "
    f"the range of outcomes that could realistically occur given that no economic "
    f"model can perfectly predict the future. We ran **{mc_results['n_runs']} simulations**, "
    f"each with slightly different assumptions about productivity growth, input costs, "
    f"interest rates, and investment levels.\n\n"
)
report_parts.append(
    f"**What the bands mean:**\n\n"
    f"- The **dark shaded area** shows where GDP is most likely to land "
    f"(50% of simulations fell within this range)\n"
    f"- The **light shaded area** shows the broader range of plausible outcomes "
    f"(80% of simulations fell within this range)\n"
    f"- The **red line** is the central scenario based on your chosen settings\n\n"
)
report_parts.append(
    f"By Year {proj_horizon}, there is an **80% chance** that sector GDP lands between "
    f"**{rfmt(mc_results['final_gdp_p10'])}** and **{rfmt(mc_results['final_gdp_p90'])}** "
    f"— a spread of **{rfmt(mc_spread_gdp)}** ({mc_spread_pct:.1f}% of the midpoint). "
)

if mc_spread_pct < 3:
    report_parts.append(
        "This is a **narrow range**, suggesting the projection is relatively robust "
        "to parameter uncertainty. The key conclusions hold across most scenarios.\n"
    )
elif mc_spread_pct < 8:
    report_parts.append(
        "This is a **moderate range**, typical for multi-year agricultural projections. "
        "The directional conclusions are reliable, but the precise dollar values should "
        "be interpreted as estimates rather than exact predictions.\n"
    )
else:
    report_parts.append(
        "This is a **wide range**, indicating high sensitivity to underlying assumptions. "
        "Policy decisions should consider the full range of outcomes rather than relying "
        "on any single point estimate.\n"
    )

# DSCR uncertainty
report_parts.append(
    f"\nThe DSCR (financial health) ranges from **{mc_results['final_dscr_p10']:.2f}×** "
    f"to **{mc_results['final_dscr_p90']:.2f}×** across the 80% confidence interval. "
)
if mc_results["final_dscr_p10"] < 1.0:
    report_parts.append(
        "⚠️ In pessimistic scenarios, the sector enters **crisis territory** "
        "(DSCR below 1.0), where farms cannot cover debt obligations.\n"
    )
elif mc_results["final_dscr_p10"] < 1.25:
    report_parts.append(
        "⚠️ In pessimistic scenarios, the sector enters **financial stress** "
        "(DSCR below 1.25), where investment may slow due to lender caution.\n"
    )
else:
    report_parts.append(
        "Even in pessimistic scenarios, the sector maintains **healthy** debt coverage.\n"
    )

# ── Section 4: Key Takeaways ──
report_parts.append(f"\n### 💡 Key Takeaways\n")

# Build bullet points based on what's most relevant
takeaways = []

if sim['macro_gdp'] != 0:
    macro_word = "at risk" if sim['macro_gdp'] < 0 else "in potential gains"
    delta_gdp_abs = abs(sim['final_gdp'] - sim['base_gdp'])
    indirect_abs = abs(sim.get('macro_indirect_gdp', 0))
    takeaways.append(
        f"**Supply Chain Ripple Effects**: The {region_adj} economy faces **{rfmt(abs(sim['macro_gdp']))}** {macro_word}. "
        f"Every dollar lost on the farm means less money spent at local equipment dealers, feed mills, and trucking companies. "
        f"This captures **{rfmt(delta_gdp_abs)}** in direct farm-level impacts and **{rfmt(indirect_abs)}** in indirect ripple effects "
        f"(multiplier: **{sim.get('type1_mult', 1.35):.2f}×**)."
    )

if abs(cumulative_gap) > 1_000_000:
    if cumulative_gap > 0:
        takeaways.append(
            f"Over {proj_horizon} years, the scenario generates **{rfmt(cumulative_gap)}** "
            f"in cumulative Direct Farm GDP gains versus business-as-usual."
        )
    else:
        takeaways.append(
            f"Over {proj_horizon} years, the shock compounds to produce **{rfmt(abs(cumulative_gap))}** "
            f"in cumulative Direct Farm GDP losses — significantly more than the Year 1 impact alone."
        )

if tfp_changed and proj_tfp_growth > BASELINE_TFP:
    annual_tfp_value = abs(final_gdp_gap) if final_gdp_gap > 0 else 0
    if annual_tfp_value > 0:
        takeaways.append(
            f"Each additional percentage point of productivity growth is worth approximately "
            f"**{rfmt(annual_tfp_value / (proj_tfp_growth - BASELINE_TFP))}/yr** "
            f"to the sector by Year {proj_horizon}."
        )

if shock_interest > 0 and final_dscr < 1.25:
    takeaways.append(
        "Rising interest rates are the most dangerous shock for leveraged operations. "
        "Unlike input costs, debt service cannot be reduced through substitution."
    )

if not takeaways:
    takeaways.append(
        "Under current settings, the sector shows stable performance with no material divergence "
        "from the baseline trajectory."
    )

for t in takeaways:
    report_parts.append(f"- {t}\n")

# Determine data sources for assumptions text
_dta_source = _fin_default_src if financial_health_df is not None else "assumed"
_rate_source = "derived from StatCan income/debt data" if sim.get("financial_health") else "assumed ~5%"

# Render the main report
full_report = "".join(report_parts)
st.markdown(full_report)

with st.expander("🔬 Technical Appendix (Assumptions & Limitations)", expanded=False):
    st.markdown(
        f"- Sector archetype: **{sector_params['label']}** "
        f"(capital elasticity α={sector_params['alpha']}, "
        f"depreciation δ={_actual_delta:.0%}/yr{_delta_source}, "
        f"investment lag={sector_params['lag']} yr)\n"
        f"- Debt-to-asset ratio: **{proj_debt_ratio:.0%}** "
        f"({_dta_source}; assumes no new borrowing or repayment)\n"
        f"- Capital investment change: **{proj_capex_shock:+d}%** from baseline\n"
        f"- TFP growth: **{proj_tfp_growth:.1f}%/yr** "
        f"(baseline reference: {BASELINE_TFP:.1f}%/yr)\n"
        f"- Interest rate: {_rate_source} + applied shock\n"
        f"- Capital stock: {capex_source}\n"
        f"- The model assumes standard economic rules where farmers cannot instantly change their operations — "
        f"actual impacts may be lower if producers substitute away from expensive inputs\n"
        f"- Multiplier data: StatCan Supply-Use Tables, latest available year\n"
        f"- Balance sheet data: StatCan Tables 32-10-0051, 32-10-0052, 32-10-0056\n"
        f"- Labor data: StatCan Tables 32-10-0216 (employees), 32-10-0218 (TFW); "
        f"base vacancy {_base_vacancy:.1%}{_vacancy_source}, TFW dependency {_tfw_dep:.0%}\n"
        f"- Uncertainty bands: {mc_results['n_runs']} Monte Carlo simulations; "
        f"TFP σ=±0.3pp, cost σ=±10%, interest σ=±0.5pp, CapEx σ=±5pp (seed=42)\n"
        f"- This is a simulation, not a forecast. "
        f"Results depend on the accuracy of assumed coefficients and the "
        f"persistence of modeled shocks.\n"
        f"- **Not modeled (future scope):** Capacity utilization weighting "
        f"(CapEx→output response varies with utilization rate), and cross-sector "
        f"feed loops (e.g., cheap grain benefiting livestock margins).\n"
    )

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# Generate enhanced matplotlib figure for word doc export
fig_mpl, ax = plt.subplots(figsize=(9, 4.5))

years_chart = list(range(proj_horizon + 1))
year_labels = [f"Year {y}" for y in years_chart]
base_gdp_vals = [p['gdp'] / 1e9 for p in baseline_proj]
scen_gdp_vals = [p['gdp'] / 1e9 for p in projection]

# Monte Carlo bands
mc_gdp_p10_chart = [v / 1e9 for v in mc_results["gdp"]["p10"]]
mc_gdp_p25_chart = [v / 1e9 for v in mc_results["gdp"]["p25"]]
mc_gdp_p75_chart = [v / 1e9 for v in mc_results["gdp"]["p75"]]
mc_gdp_p90_chart = [v / 1e9 for v in mc_results["gdp"]["p90"]]

# P10-P90 band (80% confidence)
ax.fill_between(years_chart, mc_gdp_p10_chart, mc_gdp_p90_chart,
                alpha=0.10, color='#e53935', label='80% confidence')
# P25-P75 band (50% confidence)
ax.fill_between(years_chart, mc_gdp_p25_chart, mc_gdp_p75_chart,
                alpha=0.20, color='#e53935', label='50% confidence')

ax.plot(years_chart, base_gdp_vals, label=f"Baseline (TFP {BASELINE_TFP}%, No Shocks)",
        color="#43a047", linestyle="--", linewidth=2, marker="s", markersize=5)
ax.plot(years_chart, scen_gdp_vals, label=f"Scenario (TFP {proj_tfp_growth}%)",
        color="#e53935", linewidth=2.5, marker="o", markersize=6)

# Annotate the final-year gap
if proj_horizon >= 1 and abs(scen_gdp_vals[-1] - base_gdp_vals[-1]) > 0.01:
    gap_val = scen_gdp_vals[-1] - base_gdp_vals[-1]
    mid_y = (scen_gdp_vals[-1] + base_gdp_vals[-1]) / 2
    # Format the cumulative gap
    cum_gap_b = cumulative_gap / 1e9
    sign = "+" if cum_gap_b > 0 else "−"
    ax.annotate(
        f"Cumulative: {sign}${abs(cum_gap_b):.2f}B",
        xy=(proj_horizon, scen_gdp_vals[-1]),
        xytext=(proj_horizon - 0.6, scen_gdp_vals[-1] + (gap_val * 0.3 if gap_val < 0 else -gap_val * 0.3)),
        fontsize=8, fontweight='bold', color='#c62828',
        arrowprops=dict(arrowstyle='->', color='#c62828', lw=1.2),
        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#c62828', alpha=0.9),
    )

ax.set_title(f"{region} Sector GDP Trajectory ($B) — with Uncertainty Bands",
             fontsize=12, fontweight='bold', pad=12)
ax.set_xlabel("")
ax.set_ylabel("GDP ($B)", fontsize=10)
ax.set_xticks(years_chart)
ax.set_xticklabels(year_labels, fontsize=9)
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.08), ncol=2, fontsize=8, framealpha=0.9)
ax.grid(True, alpha=0.25, linestyle='-')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
fig_mpl.tight_layout()

chart_buffer = io.BytesIO()
fig_mpl.savefig(chart_buffer, format='png', dpi=200, bbox_inches='tight')
plt.close(fig_mpl)
chart_buffer.seek(0)

# Add Download Button for Word Report — now passes full data for executive briefing
if Document:
    doc_buffer = generate_word_report(
        headline_text=headline,
        scenario_desc=active_shocks,
        baseline_gdp=sim['base_gdp'],
        gap_m=cumulative_gap / 1e6,
        final_dscr=final_dscr,
        horizon=proj_horizon,
        region=region,
        name=selected_name,
        fig=chart_buffer,
        takeaways=takeaways,
        # ── New executive briefing data ──
        sim=sim,
        projection=projection,
        baseline_proj=baseline_proj,
        mc_results=mc_results,
        sector_params=sector_params,
        proj_debt_ratio=proj_debt_ratio,
        proj_tfp_growth=proj_tfp_growth,
        baseline_tfp=BASELINE_TFP,
        active_shocks_list=active_shocks,
        is_pulse=_is_pulse,
        tariff_active=tariff_active,
        tariff_detail=tariff_detail,
        tariff_commodity_breakdown=tariff_commodity_breakdown if tariff_commodity == "All Primary Agriculture" else None,
        cost_commodity_breakdown=cost_commodity_breakdown,
    )
    if doc_buffer:
        headline_container.download_button(
            label="📥 Download Executive Briefing (.docx)",
            data=doc_buffer,
            file_name=f"Farm_Sector_Shock_Assessment_{region}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

from app.utils import global_footer
global_footer()
