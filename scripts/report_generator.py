"""
Report Generator for Economic Impact Multipliers — v2.0
========================================================
World-class consulting-grade deliverables:
  1. Full report (Word, 12-15 pages) — replaces $50K consulting engagement
  2. Slide deck (PowerPoint, native charts) — board-ready presentation
  3. One-pager (PDF) — stakeholder leave-behind

All outputs returned as BytesIO buffers for Streamlit download buttons.
"""
from __future__ import annotations
import re as _re_mod

import io
import textwrap
from datetime import date
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import OxmlElement
from docx.oxml import parse_xml

from pptx import Presentation
from pptx.util import Inches as PptInches, Pt as PptPt, Emu as PptEmu
from pptx.dml.color import RGBColor as PptRGB
from pptx.enum.text import PP_ALIGN
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE



# ─────────────────────────────────────────────────────────────────────────────
# BRAND CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
_NAVY = RGBColor(0x1B, 0x2A, 0x4A)
_EMERALD = RGBColor(0x05, 0x96, 0x69)
_DARK_GREY = RGBColor(0x33, 0x33, 0x33)
_MID_GREY = RGBColor(0x66, 0x66, 0x66)
_LIGHT_GREY = RGBColor(0x99, 0x99, 0x99)
_WHITE = RGBColor(0xFF, 0xFF, 0xFF)

_NAVY_HEX = "#1B2A4A"
_EMERALD_HEX = "#059669"
_CHART_COLORS = {
    "gdp": "#059669", "imports": "#dc2626", "exports": "#2563eb",
    "direct": "#0d9488", "indirect": "#f59e0b", "induced": "#ef4444",
    "tax": "#7c3aed", "subsidy": "#f97316",
}
_SECTOR_COLORS = [
    "#059669", "#2563eb", "#f59e0b", "#ef4444", "#8b5cf6",
    "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#6366f1",
]


# ─────────────────────────────────────────────────────────────────────────────
# FORMATTING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_EMOJI_RE = _re_mod.compile(
    "[\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U0000FE00-\U0000FE0F"
    "\U0001F900-\U0001F9FF"
    "\U00002600-\U000026FF"
    "\U0000200D"
    "\U00002B50"
    "\U0000231A-\U0000231B"
    "\U000023E9-\U000023F3"
    "\U000023F8-\U000023FA"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "]+",
    flags=_re_mod.UNICODE,
)


def _strip_emojis(text: str) -> str:
    """Remove emoji characters from text for professional documents."""
    if not text:
        return text
    return _EMOJI_RE.sub("", text).strip()


def _fmt(val: float) -> str:
    """Format a dollar value compactly: $1.2 billion, $149 billion."""
    if pd.isna(val):
        return "N/A"
    if val == 0:
        return "$0"
    
    def _clean(num):
        s = f"{num:,.1f}"
        return s[:-2] if s.endswith(".0") else s

    if abs(val) >= 1e9:
        return f"${_clean(val/1e9)} billion"
    if abs(val) >= 1e6:
        return f"${_clean(val/1e6)} million"
    if abs(val) >= 1e3:
        return f"${_clean(val/1e3)} thousand"
    return f"${val:,.0f}"

def _fmt_short(val: float) -> str:
    """Format a dollar value very compactly for chart axes (e.g., $1.2B)."""
    if pd.isna(val):
        return "N/A"
    if val == 0:
        return "$0"
    def _clean(num):
        s = f"{num:,.1f}"
        return s[:-2] if s.endswith(".0") else s
    if abs(val) >= 1e9:
        return f"${_clean(val/1e9)}B"
    if abs(val) >= 1e6:
        return f"${_clean(val/1e6)}M"
    if abs(val) >= 1e3:
        return f"${_clean(val/1e3)}K"
    return f"${val:,.0f}"


def _fmt_full(val: float) -> str:
    """Full-precision dollar format: $1,234,567, or compact for very large numbers."""
    if pd.isna(val):
        return "N/A"
    if val == 0:
        return "$0"
        
    def _clean(num):
        s = f"{num:,.1f}"
        return s[:-2] if s.endswith(".0") else s

    if abs(val) >= 1e9:
        return f"${_clean(val/1e9)} billion"
    if abs(val) >= 1e6:
        return f"${_clean(val/1e6)} million"
    
    return f"${val:,.0f}"


def _pct(val: float) -> str:
    return f"{val:.1f}%"


def _get_metric(df: pd.DataFrame, pattern: str) -> float:
    """Sum impact_dollars for rows matching a pattern in metric column."""
    if df is None or df.empty:
        return 0.0
    if pattern.lower() == "gross domestic":
        pattern = "Gross domestic.*basic prices"
    elif pattern.lower() == "gdp":
        pattern = "GDP.*basic prices"
    mask = df["metric"].str.contains(pattern, case=False, na=False)
    col = "impact_dollars" if "impact_dollars" in df.columns else "impact"
    return float(df.loc[mask, col].sum())


def _get_bd_metric(bd_df: pd.DataFrame, pattern: str, impact_type: str) -> float:
    """Get breakdown metric for a specific type (Direct/Indirect/Induced)."""
    if bd_df is None or bd_df.empty:
        return 0.0
    if pattern.lower() == "gross domestic":
        pattern = "Gross domestic.*basic prices"
    elif pattern.lower() == "gdp":
        pattern = "GDP.*basic prices"
    mask = (
        bd_df["metric"].str.contains(pattern, case=False, na=False) &
        (bd_df["Type"] == impact_type)
    )
    col = "impact_dollars" if "impact_dollars" in bd_df.columns else "impact"
    return float(bd_df.loc[mask, col].sum())


# ─────────────────────────────────────────────────────────────────────────────
# FISCAL METRICS CALCULATOR (Finding 1)
# ─────────────────────────────────────────────────────────────────────────────


def _allowed_types(scope_label: str) -> list[str]:
    """Determine which impact types (Direct/Indirect/Induced) are allowed by scope."""
    sl = scope_label.lower()
    if "induced" in sl:
        return ["Direct", "Indirect", "Induced"]
    if "indirect" in sl:
        return ["Direct", "Indirect"]
    return ["Direct"]


def _filter_bd_by_scope(bd_df: pd.DataFrame, scope_label: str) -> pd.DataFrame:
    """Filter breakdown dataframe to only include types allowed by scope."""
    if bd_df is None or bd_df.empty:
        return bd_df
    allowed = _allowed_types(scope_label)
    return bd_df[bd_df["Type"].isin(allowed)].copy()



def _scope_model_name(scope_label: str) -> str:
    """Map scope label to IO model terminology."""
    sl = scope_label.lower()
    if "induced" in sl:
        return "Closed Model"
    if "indirect" in sl:
        return "Open Model"
    return "Direct Only"

def _compute_fiscal(sum_df: pd.DataFrame) -> dict:
    """Compute the fiscal contribution metrics — the Lobbyist's Arsenal."""
    taxes_products = _get_metric(sum_df, "Taxes on products")
    taxes_production = _get_metric(sum_df, "Taxes on production")
    subsidies_raw = _get_metric(sum_df, "Subsidies")
    # StatCan reports subsidies as NEGATIVE values; use absolute value
    subsidies = abs(subsidies_raw)
    total_tax = taxes_products + taxes_production
    net_fiscal = total_tax - subsidies
    tax_roi = (total_tax / subsidies) if subsidies > 0 else 0
    return {
        "taxes_products": taxes_products,
        "taxes_production": taxes_production,
        "total_tax": total_tax,
        "subsidies": subsidies,
        "net_fiscal": net_fiscal,
        "tax_roi": tax_roi,
    }


# ─────────────────────────────────────────────────────────────────────────────
# INCOME DISTRIBUTION CALCULATOR (Finding 7)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_income_distribution(sum_df: pd.DataFrame) -> dict:
    """Break out labour income into wages vs self-employment."""
    wages = _get_metric(sum_df, "Wages and salaries")
    labour_income = _get_metric(sum_df, "Labour income$")
    uninc = _get_metric(sum_df, "unincorporated")
    social = _get_metric(sum_df, "social contributions")
    total_comp = wages + uninc + social
    uninc_pct = (uninc / total_comp * 100) if total_comp > 0 else 0
    wages_pct = (wages / total_comp * 100) if total_comp > 0 else 0
    return {
        "wages": wages,
        "unincorporated": uninc,
        "social_contributions": social,
        "total_compensation": total_comp,
        "uninc_pct": uninc_pct,
        "wages_pct": wages_pct,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CHART RENDERING (matplotlib → 300 DPI PNG for Word)
# ─────────────────────────────────────────────────────────────────────────────

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Calibri", "Arial", "Helvetica"],
    "font.size": 10,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.spines.top": False,
    "axes.spines.right": False,
})






def _render_trend_chart(trend_df: pd.DataFrame, geo: str, basket_name: str,
                         scope_label: str) -> io.BytesIO:
    """Dual-axis line chart: GDP ($) and Jobs (#) over time.
    trend_df must have columns: Year, GDP, Jobs."""
    if trend_df is None or trend_df.empty or len(trend_df) < 2:
        return io.BytesIO()

    fig, ax1 = plt.subplots(figsize=(7, 6.0))
    fig.patch.set_facecolor("white")

    years = trend_df["Year"].values
    gdp = trend_df["GDP"].values
    jobs = trend_df["Jobs"].values

    # GDP line (left axis)
    color_gdp = "#059669"
    ax1.plot(years, gdp / 1e9, color=color_gdp, marker="o", markersize=5,
             linewidth=2.2, label="GDP ($ Billions)", zorder=3)
    ax1.fill_between(years, 0, gdp / 1e9, alpha=0.08, color=color_gdp)
    ax1.set_xlabel("Year", fontsize=10)
    ax1.set_ylabel("GDP ($ Billions)", fontsize=10, color=color_gdp)
    ax1.tick_params(axis="y", labelcolor=color_gdp)
    ax1.set_xlim(years[0] - 0.3, years[-1] + 0.3)
    ax1.set_xticks(years)
    ax1.set_xticklabels([str(y) for y in years], rotation=45, ha="right", fontsize=8)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.1f}B"))

    # Jobs line (right axis)
    ax2 = ax1.twinx()
    color_jobs = "#1B2A4A"
    ax2.plot(years, jobs / 1000, color=color_jobs, marker="s", markersize=5,
             linewidth=2.2, linestyle="--", label="Jobs (Thousands)", zorder=3)
    ax2.set_ylabel("Jobs (Thousands)", fontsize=10, color=color_jobs)
    ax2.tick_params(axis="y", labelcolor=color_jobs)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}K"))

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2,
               loc="upper left", fontsize=8, framealpha=0.9, edgecolor="#ccc")

    ax1.set_title(f"Historical Trend: {basket_name} Economic Impact ({scope_label})",
                  pad=12, fontsize=11, fontweight="bold")
    ax1.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.text(0.99, 0.01, "Source: Statistics Canada (IO Multipliers)", ha='right', va='bottom', fontsize=7, color='#666666', style='italic')
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig); buf.seek(0); return buf

def _render_employment_chart(bd_df, scope_label: str, jobs: float) -> io.BytesIO:
    """Horizontal bar chart showing employment breakdown by Direct / Indirect / Induced."""
    if bd_df is None or bd_df.empty:
        return io.BytesIO()
    fig, ax = plt.subplots(figsize=(6, 6.0))
    fig.patch.set_facecolor("white")

    types = _allowed_types(scope_label)
    job_vals = []
    labels = []
    colors = []
    color_map = {"Direct": _CHART_COLORS["direct"],
                 "Indirect": _CHART_COLORS["indirect"],
                 "Induced": _CHART_COLORS["induced"]}
    for t in types:
        v = _get_bd_metric(bd_df, "Jobs", t)
        if v > 0:
            job_vals.append(v)
            labels.append(t)
            colors.append(color_map.get(t, "#666"))

    if not job_vals:
        plt.close(fig)
        return io.BytesIO()

    y = np.arange(len(labels))
    bars = ax.barh(y, job_vals, height=0.5, color=colors, edgecolor="white", linewidth=0.8)
    for bar, val in zip(bars, job_vals):
        ax.text(bar.get_width() + max(job_vals)*0.02, bar.get_y()+bar.get_height()/2,
                f"{val:,.0f}", va="center", ha="left", fontsize=10, fontweight="bold", color="#333")
    ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=11)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1000:.0f}K" if x >= 1000 else f"{x:.0f}"))
    ax.set_xlim(0, max(job_vals)*1.3)
    ax.set_title("Direct Employment" if scope_label == "Direct" else "Employment by Impact Type", pad=10)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.text(0.99, 0.01, "Source: Statistics Canada (IO Multipliers)", ha='right', va='bottom', fontsize=7, color='#666666', style='italic')
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig); buf.seek(0); return buf

def _render_value_retention_chart(gdp, imports_val, exports_val=0) -> io.BytesIO:
    """Horizontal bar: GDP vs Imports vs Exports."""
    fig, ax = plt.subplots(figsize=(7, 6.0))
    fig.patch.set_facecolor("white")

    cats, vals, cols = [], [], []
    if gdp > 0:
        cats.append("Value Added\n(GDP)"); vals.append(gdp); cols.append(_CHART_COLORS["gdp"])
    if imports_val > 0:
        cats.append("Import\nLeakage"); vals.append(imports_val); cols.append(_CHART_COLORS["imports"])
    if exports_val > 0:
        cats.append("International\nExports"); vals.append(exports_val); cols.append(_CHART_COLORS["exports"])
    if not vals:
        plt.close(fig); return io.BytesIO()

    y = np.arange(len(cats))
    bars = ax.barh(y, vals, color=cols, height=0.45, edgecolor="white", linewidth=0.8)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_width() + max(vals)*0.02, bar.get_y()+bar.get_height()/2,
                _fmt(v), va="center", ha="left", fontsize=10, fontweight="bold", color="#333")
    ax.set_yticks(y); ax.set_yticklabels(cats, fontsize=10)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_short(x)))
    ax.set_xlim(0, max(vals)*1.35)
    ax.set_title("Value Retention Analysis", pad=12)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.text(0.99, 0.01, "Source: Statistics Canada (IO Multipliers)", ha='right', va='bottom', fontsize=7, color='#666666', style='italic')
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig); buf.seek(0); return buf


def _render_ripple_chart(bd_df, scope_label: str = "Direct + Indirect + Induced") -> io.BytesIO:
    """Stacked horizontal bar: Direct / Indirect / Induced."""
    if bd_df is None or bd_df.empty:
        return io.BytesIO()
    fig, ax = plt.subplots(figsize=(7, 6.0))
    fig.patch.set_facecolor("white")

    def _clean(x):
        xl = str(x).lower()
        if "gross domestic" in xl and "basic prices" in xl: return "GDP"
        if xl.strip() == "output": return "Output"
        return None

    df = bd_df.copy()
    df["short"] = df["metric"].apply(_clean)
    df = df.dropna(subset=["short"])
    df = df.groupby(["short", "Type"], as_index=False)["impact"].sum()

    metrics = [m for m in ["Output", "GDP"] if m in df["short"].unique()]
    if not metrics:
        plt.close(fig); return io.BytesIO()

    types = _allowed_types(scope_label)
    y = np.arange(len(metrics))
    left = np.zeros(len(metrics))

    for t_idx, t in enumerate(types):
        vals = np.array([df[(df["short"]==m)&(df["Type"]==t)]["impact"].sum() for m in metrics])
        color = [_CHART_COLORS["direct"], _CHART_COLORS["indirect"], _CHART_COLORS["induced"]][t_idx]
        ax.barh(y, vals, left=left, height=0.45, label=t, color=color, edgecolor="white", linewidth=0.8)
        left += vals

    for i, total in enumerate(left):
        ax.text(total + max(left)*0.02, y[i], _fmt(total),
                va="center", ha="left", fontsize=10, fontweight="bold", color="#333")
    ax.set_yticks(y); ax.set_yticklabels(metrics, fontsize=11)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_short(x)))
    ax.set_xlim(0, max(left)*1.3)
    ax.legend(loc="upper right", fontsize=9, framealpha=0.9, edgecolor="#ccc")
    scope_parts = " → ".join(_allowed_types(scope_label))
    ax.set_title(f"The Ripple Effect: {scope_parts}", pad=12)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.text(0.99, 0.01, "Source: Statistics Canada (IO Multipliers)", ha='right', va='bottom', fontsize=7, color='#666666', style='italic')
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig); buf.seek(0); return buf


def _render_sector_donut(res_df, get_sector_label_fn=None) -> io.BytesIO:
    """Donut chart showing output contribution by sector."""
    if res_df is None or res_df.empty:
        return io.BytesIO()
    df = res_df[res_df["metric"] == "Output"].copy()
    if df.empty:
        return io.BytesIO()
    if get_sector_label_fn:
        df["Sector"] = df.apply(get_sector_label_fn, axis=1)
    else:
        df["Sector"] = df["industry_name"].str[:30]
    sa = df.groupby("Sector", as_index=False)["impact"].sum()
    sa = sa[sa["impact"] > 0]  # Bug 7: exclude zero-value sectors
    sa = sa.sort_values("impact", ascending=False)
    if len(sa) > 8:
        top = sa.head(8)
        other = pd.DataFrame([{"Sector": "Other", "impact": sa.iloc[8:]["impact"].sum()}])
        sa = pd.concat([top, other], ignore_index=True)
    total = sa["impact"].sum()
    if total <= 0: return io.BytesIO()
    fig, ax = plt.subplots(figsize=(5, 6.0)); fig.patch.set_facecolor("white")
    colors = _SECTOR_COLORS[:len(sa)]
    wedges, _, autotexts = ax.pie(
        sa["impact"], labels=None, autopct=lambda p: f"{p:.0f}%" if p > 4 else "",
        colors=colors, startangle=90, pctdistance=0.78,
        wedgeprops={"width": 0.45, "edgecolor": "white", "linewidth": 2})
    for t in autotexts: t.set_fontsize(8); t.set_fontweight("bold")
    ax.legend(wedges, [f"{r['Sector']} ({_fmt(r['impact'])})" for _, r in sa.iterrows()],
              loc="center left", bbox_to_anchor=(1, 0.5), fontsize=8, frameon=False)
    ax.set_title("Output Contribution by Sector", pad=12)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.text(0.99, 0.01, "Source: Statistics Canada (IO Multipliers)", ha='right', va='bottom', fontsize=7, color='#666666', style='italic')
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig); buf.seek(0); return buf


def _render_fiscal_chart(fiscal: dict) -> io.BytesIO:
    """Bar chart showing Tax Revenue vs Subsidies with Net callout."""
    fig, ax = plt.subplots(figsize=(5, 6.0))
    fig.patch.set_facecolor("white")
    tax_val = fiscal["total_tax"]
    sub_val = fiscal["subsidies"]  # already abs from _compute_fiscal
    net_val = fiscal["net_fiscal"]
    cats = ["Tax Revenue\nGenerated", "Government\nSubsidies", "Net Fiscal\nContribution"]
    vals = [tax_val, sub_val, net_val]
    cols = [_CHART_COLORS["tax"], _CHART_COLORS["subsidy"], _CHART_COLORS["gdp"]]
    y = np.arange(len(cats))
    bars = ax.barh(y, vals, color=cols, height=0.45, edgecolor="white")
    max_val = max(abs(v) for v in vals) if vals else 1
    for bar, v in zip(bars, vals):
        x_pos = bar.get_width() + max_val * 0.03
        ax.text(x_pos, bar.get_y() + bar.get_height() / 2,
                _fmt(abs(v)), va="center", ha="left", fontsize=10, fontweight="bold", color="#333")
    ax.set_yticks(y); ax.set_yticklabels(cats, fontsize=10)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt(abs(x))))
    ax.set_xlim(0, max_val * 1.4)
    ax.set_title("Fiscal Contribution", pad=12)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.text(0.99, 0.01, "Source: Statistics Canada (IO Multipliers)", ha='right', va='bottom', fontsize=7, color='#666666', style='italic')
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig); buf.seek(0); return buf


# ─────────────────────────────────────────────────────────────────────────────
# PRIMARY AGRICULTURE COMMODITY BREAKDOWN
# ─────────────────────────────────────────────────────────────────────────────

_AG_COMMODITY_GROUPS = [
    ("Field Crops",             ["111A", "BS111A", "BS111A00"]),
    ("Livestock",               ["112A", "BS112A", "BS112"]),
    ("Greenhouse & Nursery",    ["1114A", "1114", "BS1114A0", "BS111400", "BS1114A"]),
    ("Aquaculture",             ["1125", "BS1125", "BS112500"]),
    ("Ag Support Services",     ["115A", "BS115A", "BS115A00"]),
    ("Cannabis",                ["111CL", "BS111CL", "BS111CL0", "111CU"]),
]


def _compute_primary_ag_breakdown(res_df: pd.DataFrame) -> pd.DataFrame:
    """Break down primary agriculture results into commodity groups."""
    if res_df is None or res_df.empty:
        return pd.DataFrame()
    rows = []
    for group_name, code_prefixes in _AG_COMMODITY_GROUPS:
        mask = res_df["industry_code"].astype(str).apply(
            lambda c: any(
                c == pfx or c.startswith(pfx)
                for pfx in code_prefixes
            )
        )
        subset = res_df[mask]
        if subset.empty:
            continue
        output = subset[subset["metric"] == "Output"]["impact"].sum()
        gdp_mask = subset["metric"].str.contains("Gross domestic.*basic prices", case=False, na=False)
        gdp = subset[gdp_mask]["impact"].sum()
        jobs = subset[subset["metric"].str.contains("^Jobs$", case=False, na=False)]["impact"].sum()
        if output > 0 or gdp > 0 or jobs > 0:
            rows.append({"Commodity": group_name, "Output": output, "GDP": gdp, "Jobs": jobs})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("Output", ascending=False)
    total = df["Output"].sum()
    if total > 0:
        df["Share"] = df["Output"] / total * 100
    else:
        df["Share"] = 0.0
    return df


def _render_commodity_chart(commodity_df: pd.DataFrame) -> io.BytesIO:
    """Horizontal bar chart of primary agriculture output by commodity."""
    if commodity_df is None or commodity_df.empty:
        return io.BytesIO()
    fig, ax = plt.subplots(figsize=(6, 6.0))
    fig.patch.set_facecolor("white")
    df = commodity_df.sort_values("Output", ascending=True)
    colors = _SECTOR_COLORS[:len(df)]
    colors.reverse()
    y = np.arange(len(df))
    bars = ax.barh(y, df["Output"].values, color=colors, height=0.55,
                   edgecolor="white", linewidth=0.8)
    max_val = df["Output"].max()
    for bar, val in zip(bars, df["Output"].values):
        ax.text(bar.get_width() + max_val * 0.02, bar.get_y() + bar.get_height()/2,
                _fmt(val), va="center", ha="left", fontsize=9, fontweight="bold", color="#333")
    ax.set_yticks(y)
    ax.set_yticklabels(df["Commodity"].values, fontsize=10)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_short(x)))
    ax.set_xlim(0, max_val * 1.35)
    ax.set_title("Primary Agriculture Output by Commodity", pad=12)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.text(0.99, 0.01, "Source: Statistics Canada (IO Multipliers)", ha='right', va='bottom', fontsize=7, color='#666666', style='italic')
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig); buf.seek(0); return buf


def _render_commodity_metric_chart(commodity_df: pd.DataFrame, metric: str = "GDP") -> io.BytesIO:
    """Horizontal bar chart of primary agriculture breakdown by a specific metric (GDP or Jobs)."""
    if commodity_df is None or commodity_df.empty or metric not in commodity_df.columns:
        return io.BytesIO()
    fig, ax = plt.subplots(figsize=(6, 6.0))
    fig.patch.set_facecolor("white")
    df = commodity_df.sort_values(metric, ascending=True)
    colors = _SECTOR_COLORS[:len(df)]
    colors.reverse()
    y = np.arange(len(df))
    vals = df[metric].values
    bars = ax.barh(y, vals, color=colors, height=0.55,
                   edgecolor="white", linewidth=0.8)
    max_val = max(vals) if len(vals) > 0 else 1
    for bar, val in zip(bars, vals):
        label = _fmt(val) if metric == "GDP" else f"{val:,.0f}"
        ax.text(bar.get_width() + max_val * 0.02, bar.get_y() + bar.get_height()/2,
                label, va="center", ha="left", fontsize=9, fontweight="bold", color="#333")
    ax.set_yticks(y)
    ax.set_yticklabels(df["Commodity"].values, fontsize=10)
    if metric == "Jobs":
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{x/1000:.0f}K" if x >= 1000 else f"{x:.0f}"))
        title = "Primary Agriculture: Employment by Commodity"
    else:
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_short(x)))
        title = "Primary Agriculture: GDP Contribution by Commodity"
    ax.set_xlim(0, max_val * 1.35)
    ax.set_title(title, pad=12)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.text(0.99, 0.01, "Source: Statistics Canada (IO Multipliers)", ha='right', va='bottom', fontsize=7, color='#666666', style='italic')
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig); buf.seek(0); return buf


# ─────────────────────────────────────────────────────────────────────────────
# FOOD SYSTEM SUB-COMPONENT AGGREGATION
# ─────────────────────────────────────────────────────────────────────────────

_FOOD_SYSTEM_COMPONENTS = [
    ("Primary Agriculture",
     ["111A", "BS111A", "112", "BS112", "1114", "BS1114", "BS111400",
      "BS1114A0", "115A", "BS115A", "BS115A00", "111CL", "BS111CL0"]),
    ("Food & Beverage Manufacturing",
     ["311", "BS311", "312", "BS312", "BS3121", "BS312100", "BS3122",
      "BS312200", "BS312A00"]),
    ("Wholesale & Retail (Food)",
     ["411", "BS411", "4111", "BS4111", "445", "BS445", "413", "BS413"]),
    ("Foodservice",
     ["722", "BS722"]),
    ("Agri-Inputs (Fertilizer & Chemicals)",
     ["3253", "BS3253"]),
    ("Agri-Inputs (Machinery)",
     ["3331", "BS3331"]),
    ("Transportation (Rail & Truck)",
     ["482", "BS482", "484", "BS484"]),
]


def _compute_food_system_subcomponents(res_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate res_df into food system sub-components for exec summary."""
    if res_df is None or res_df.empty:
        return pd.DataFrame()
    rows = []
    for comp_name, code_prefixes in _FOOD_SYSTEM_COMPONENTS:
        mask = res_df["industry_code"].astype(str).apply(
            lambda c: any(
                c == pfx or c.startswith(pfx)
                for pfx in code_prefixes
            )
        )
        subset = res_df[mask]
        if subset.empty:
            continue
        output = subset[subset["metric"] == "Output"]["impact"].sum()
        gdp_mask = subset["metric"].str.contains("Gross domestic.*basic prices", case=False, na=False)
        gdp = subset[gdp_mask]["impact"].sum()
        jobs = subset[subset["metric"].str.contains("^Jobs$", case=False, na=False)]["impact"].sum()
        if output > 0 or gdp > 0 or jobs > 0:
            rows.append({"Component": comp_name, "Output": output, "GDP": gdp, "Jobs": jobs})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("GDP", ascending=False)
    total_gdp = df["GDP"].sum()
    if total_gdp > 0:
        df["GDP_Share"] = df["GDP"] / total_gdp * 100
    else:
        df["GDP_Share"] = 0.0
    return df


# ─────────────────────────────────────────────────────────────────────────────
# FOOD & BEVERAGE MANUFACTURING INTERNAL NAICS BREAKDOWN
# ─────────────────────────────────────────────────────────────────────────────

_FB_MFG_SUB_INDUSTRIES = [
    ("Meat Product Mfg",         ["3116", "BS3116", "BS311600"]),
    ("Dairy Product Mfg",        ["3115", "BS3115", "BS311500"]),
    ("Fruit & Veg Preserving",   ["3114", "BS3114", "BS311400"]),
    ("Grain & Oilseed Milling",  ["3112", "BS3112", "BS311200"]),
    ("Animal Food Mfg",          ["3111", "BS3111", "BS311100"]),
    ("Bakeries & Tortilla Mfg",  ["3118", "BS3118", "BS311800"]),
    ("Sugar & Confectionery",    ["3113", "BS3113", "BS311300"]),
    ("Seafood Product Mfg",      ["3117", "BS3117", "BS311700"]),
    ("Other Food Mfg",           ["3119", "BS3119", "BS311900"]),
    ("Beverage Mfg",             ["3121", "BS3121", "312A", "BS312A", "BS312100", "BS312A00"]),
    ("Tobacco Mfg",              ["3122", "BS3122", "BS312200"]),
]


def _compute_fb_mfg_breakdown(res_df: pd.DataFrame) -> pd.DataFrame:
    """Break down Food & Beverage Manufacturing results into NAICS sub-industries."""
    if res_df is None or res_df.empty:
        return pd.DataFrame()
    rows = []
    for sub_name, code_prefixes in _FB_MFG_SUB_INDUSTRIES:
        mask = res_df["industry_code"].astype(str).apply(
            lambda c: any(
                c == pfx or c.startswith(pfx)
                for pfx in code_prefixes
            )
        )
        subset = res_df[mask]
        if subset.empty:
            continue
        output = subset[subset["metric"] == "Output"]["impact"].sum()
        gdp_mask = subset["metric"].str.contains("Gross domestic.*basic prices", case=False, na=False)
        gdp = subset[gdp_mask]["impact"].sum()
        jobs = subset[subset["metric"].str.contains("^Jobs$", case=False, na=False)]["impact"].sum()
        if output > 0 or gdp > 0 or jobs > 0:
            rows.append({"Sub-Industry": sub_name, "Output": output, "GDP": gdp, "Jobs": jobs})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("GDP", ascending=False)
    total_gdp = df["GDP"].sum()
    if total_gdp > 0:
        df["GDP_Share"] = df["GDP"] / total_gdp * 100
    else:
        df["GDP_Share"] = 0.0
    return df


def _render_fb_mfg_breakdown_chart(fb_df: pd.DataFrame, metric: str = "GDP") -> io.BytesIO:
    """Horizontal bar chart of F&B Manufacturing sub-industry breakdown."""
    if fb_df is None or fb_df.empty or metric not in fb_df.columns:
        return io.BytesIO()
    fig, ax = plt.subplots(figsize=(7, 6.0))
    fig.patch.set_facecolor("white")
    df = fb_df.sort_values(metric, ascending=True)
    colors = _SECTOR_COLORS[:len(df)]
    colors.reverse()
    y = np.arange(len(df))
    vals = df[metric].values
    bars = ax.barh(y, vals, color=colors, height=0.55,
                   edgecolor="white", linewidth=0.8)
    max_val = max(vals) if len(vals) > 0 else 1
    for bar, val in zip(bars, vals):
        label = _fmt(val) if metric == "GDP" else f"{val:,.0f}"
        ax.text(bar.get_width() + max_val * 0.02, bar.get_y() + bar.get_height()/2,
                label, va="center", ha="left", fontsize=8, fontweight="bold", color="#333")
    ax.set_yticks(y)
    ax.set_yticklabels(df["Sub-Industry"].values, fontsize=9)
    if metric == "Jobs":
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{x/1000:.0f}K" if x >= 1000 else f"{x:.0f}"))
        title = "Food & Beverage Manufacturing: Employment by Sub-Industry"
    else:
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_short(x)))
        title = "Food & Beverage Manufacturing: GDP by Sub-Industry"
    ax.set_xlim(0, max_val * 1.35)
    ax.set_title(title, pad=12)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.text(0.99, 0.01, "Source: Statistics Canada (IO Multipliers)", ha='right', va='bottom', fontsize=7, color='#666666', style='italic')
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig); buf.seek(0); return buf


# ─────────────────────────────────────────────────────────────────────────────
# DOWNSTREAM SECTOR DATA EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

_DOWNSTREAM_SECTORS = [
    ("Food Stores (Grocery, Specialty, Convenience)",
     ["445", "BS445", "4450", "BS4450", "BS445000"]),
    ("Food & Beverage Wholesalers",
     ["413", "BS413", "4130", "BS4130", "BS413000"]),
    ("Farm Product Wholesalers",
     ["411", "BS411", "4111", "BS4111", "BS411100", "BS411000"]),
    ("Foodservice (Restaurants, Caterers, Institutions)",
     ["722", "BS722", "7220", "BS7220", "BS722000"]),
]


def _compute_downstream_breakdown(res_df: pd.DataFrame) -> pd.DataFrame:
    """Extract GDP and Jobs data for downstream food system sectors."""
    if res_df is None or res_df.empty:
        return pd.DataFrame()
    rows = []
    for sector_name, code_prefixes in _DOWNSTREAM_SECTORS:
        mask = res_df["industry_code"].astype(str).apply(
            lambda c: any(
                c == pfx or c.startswith(pfx)
                for pfx in code_prefixes
            )
        )
        subset = res_df[mask]
        if subset.empty:
            continue
        output = subset[subset["metric"] == "Output"]["impact"].sum()
        gdp_mask = subset["metric"].str.contains("Gross domestic.*basic prices", case=False, na=False)
        gdp = subset[gdp_mask]["impact"].sum()
        jobs = subset[subset["metric"].str.contains("^Jobs$", case=False, na=False)]["impact"].sum()
        if output > 0 or gdp > 0 or jobs > 0:
            rows.append({"Sector": sector_name, "Output": output, "GDP": gdp, "Jobs": jobs})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("GDP", ascending=False)


def _render_downstream_chart(downstream_df: pd.DataFrame, metric: str = "GDP") -> io.BytesIO:
    """Horizontal bar chart for downstream food system sectors."""
    if downstream_df is None or downstream_df.empty or metric not in downstream_df.columns:
        return io.BytesIO()
    fig, ax = plt.subplots(figsize=(7, 6.0))
    fig.patch.set_facecolor("white")
    df = downstream_df.sort_values(metric, ascending=True)
    colors = ["#059669", "#2563eb", "#f59e0b", "#ef4444"][:len(df)]
    colors.reverse()
    y = np.arange(len(df))
    vals = df[metric].values
    bars = ax.barh(y, vals, color=colors, height=0.55,
                   edgecolor="white", linewidth=0.8)
    max_val = max(vals) if len(vals) > 0 else 1
    for bar, val in zip(bars, vals):
        label = _fmt(val) if metric == "GDP" else f"{val:,.0f}"
        ax.text(bar.get_width() + max_val * 0.02, bar.get_y() + bar.get_height()/2,
                label, va="center", ha="left", fontsize=9, fontweight="bold", color="#333")
    ax.set_yticks(y)
    ax.set_yticklabels(df["Sector"].values, fontsize=9)
    if metric == "Jobs":
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{x/1000:.0f}K" if x >= 1000 else f"{x:.0f}"))
        title = "Downstream Food System: Employment by Sector"
    else:
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_short(x)))
        title = "Downstream Food System: GDP by Sector"
    ax.set_xlim(0, max_val * 1.35)
    ax.set_title(title, pad=12)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.text(0.99, 0.01, "Source: Statistics Canada (IO Multipliers)", ha='right', va='bottom', fontsize=7, color='#666666', style='italic')
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig); buf.seek(0); return buf


# ─────────────────────────────────────────────────────────────────────────────
# PER-SECTOR LEAKAGE RATE SCAN
# ─────────────────────────────────────────────────────────────────────────────

def _compute_leakage_by_subcomponent(res_df: pd.DataFrame) -> pd.DataFrame:
    """Compute import leakage rates for each food system sub-component."""
    if res_df is None or res_df.empty:
        return pd.DataFrame()
    rows = []
    for comp_name, code_prefixes in _FOOD_SYSTEM_COMPONENTS:
        mask = res_df["industry_code"].astype(str).apply(
            lambda c: any(
                c == pfx or c.startswith(pfx)
                for pfx in code_prefixes
            )
        )
        subset = res_df[mask]
        if subset.empty:
            continue
        output = subset[subset["metric"] == "Output"]["impact"].sum()
        imports_mask = subset["metric"].str.contains("International imports", case=False, na=False)
        imports_val = subset[imports_mask]["impact"].sum()
        if output > 0:
            leak = imports_val / output * 100
            rows.append({
                "Component": comp_name,
                "Output": output,
                "Imports": imports_val,
                "Leakage Rate": leak,
                "Domestic Retention": 100 - leak,
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("Leakage Rate", ascending=True)




_TRANSPORT_INDUSTRY_MAP = [
    ("Rail Transportation",     "482",  0.334,
     ["4820", "BS4820", "BS482000", "482"]),
    ("Truck Transportation",    "484",  0.245,
     ["4840", "BS4840", "BS484000", "484"]),
    ("Machinery Manufacturing", "3331", 0.468,
     ["3331", "BS3331", "BS333100"]),
]


def _compute_transport_impacts(res_df: pd.DataFrame) -> pd.DataFrame:
    """Extract transport/machinery ag-share impacts from per-industry results."""
    if res_df is None or res_df.empty:
        return pd.DataFrame()
    rows = []
    for label, naics, ag_share, code_variants in _TRANSPORT_INDUSTRY_MAP:
        mask = res_df["industry_code"].astype(str).apply(
            lambda c: any(
                c == v or c.startswith(v)
                for v in code_variants
            )
        )
        subset = res_df[mask]
        if subset.empty:
            continue
        output = subset[subset["metric"] == "Output"]["impact"].sum()
        gdp_mask = subset["metric"].str.contains("Gross domestic.*basic prices", case=False, na=False)
        gdp = subset[gdp_mask]["impact"].sum()
        jobs = subset[subset["metric"].str.contains("^Jobs$", case=False, na=False)]["impact"].sum()
        li_mask = subset["metric"].str.contains("^Labour income$", case=False, na=False)
        labour_income = subset[li_mask]["impact"].sum()
        if output > 0 or gdp > 0 or jobs > 0:
            rows.append({
                "Industry": label,
                "NAICS": naics,
                "Ag-Share": f"{ag_share * 100:.1f}%",
                "Output": output,
                "GDP": gdp,
                "Jobs": jobs,
                "Labour Income": labour_income,
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _render_transport_impact_chart(transport_df: pd.DataFrame) -> io.BytesIO:
    """Grouped horizontal bar chart of transport/machinery impacts."""
    if transport_df is None or transport_df.empty:
        return io.BytesIO()
    fig, ax = plt.subplots(figsize=(7, 6.0))
    fig.patch.set_facecolor("white")
    df = transport_df.sort_values("GDP", ascending=True).copy()
    y = np.arange(len(df))
    bar_height = 0.35
    bars_gdp = ax.barh(y + bar_height/2, df["GDP"].values, height=bar_height,
                       color="#059669", label="GDP", edgecolor="white")
    bars_out = ax.barh(y - bar_height/2, df["Output"].values, height=bar_height,
                       color="#94a3b8", label="Output", edgecolor="white")
    max_val = max(df["Output"].max(), df["GDP"].max())
    for bar, val in zip(bars_gdp, df["GDP"].values):
        ax.text(bar.get_width() + max_val * 0.02, bar.get_y() + bar.get_height()/2,
                _fmt(val), va="center", ha="left", fontsize=8, fontweight="bold", color="#059669")
    for bar, val in zip(bars_out, df["Output"].values):
        ax.text(bar.get_width() + max_val * 0.02, bar.get_y() + bar.get_height()/2,
                _fmt(val), va="center", ha="left", fontsize=8, color="#666")
    ax.set_yticks(y)
    ax.set_yticklabels(df["Industry"].values, fontsize=10)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_short(x)))
    ax.set_xlim(0, max_val * 1.4)
    ax.set_title("Agricultural Share: Transport & Machinery Contributions", pad=12)
    ax.legend(loc="lower right", fontsize=8)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.text(0.99, 0.01, "Source: Statistics Canada (IO Multipliers)", ha='right', va='bottom', fontsize=7, color='#666666', style='italic')
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig); buf.seek(0); return buf



# ─────────────────────────────────────────────────────────────────────────────
# FOOD MANUFACTURING vs OTHER MANUFACTURING COMPARISON
# ─────────────────────────────────────────────────────────────────────────────

_MFG_SECTOR_GROUPS = [
    ("Food & Beverage",
     ["3111", "3112", "3113", "3114", "3115", "3116", "3117", "3118", "3119",
      "31211", "31212", "3121A", "312A"]),
    ("Transportation Manufacturing",
     ["33611", "33612", "3362", "3363", "33631", "33632", "33633", "33634",
      "33635", "33636", "33637", "33639", "3364", "3365", "3366", "3369"]),
    ("Chemicals & Pharma",
     ["3251", "3252", "3253", "3254", "3255", "3256", "3259"]),
    ("Primary Metals",
     ["3311", "3312", "3313", "3314", "3315"]),
    ("Machinery",
     ["3331", "3332", "3333", "3334", "3335", "3336", "3339"]),
    ("Wood & Paper",
     ["3211", "3212", "3219", "3221", "3222", "323"]),
    ("Petroleum & Coal",
     ["32411", "3241A"]),
]


def _compute_manufacturing_comparison(
    geo: str, year: int, scope_label: str, geo_scope: str = "all_provinces"
) -> pd.DataFrame:
    """Compute GDP and Jobs for major manufacturing sectors for comparison."""
    from scripts.io_multipliers_engine import (
        compute_impacts, get_actual_output, load_multipliers,
    )
    scope_map = {
        "direct": "direct",
        "direct only": "direct",
        "direct + indirect": "direct_indirect",
        "direct + indirect + induced": "direct_indirect_induced",
    }
    scope = scope_map.get(scope_label.lower(), "direct_indirect")

    # Get all available codes from the multiplier data
    mult_df = load_multipliers()
    if mult_df is None or mult_df.empty:
        return pd.DataFrame()
    avail_codes = set(
        mult_df[(mult_df["GEO"] == geo)]["join_code"].unique()
    )

    rows = []
    for sector_name, code_list in _MFG_SECTOR_GROUPS:
        # Find which codes are available in our data
        matched_codes = []
        for code in code_list:
            # Check exact match, with and without BS/GS prefix
            for variant in [code, f"BS{code}", f"GS{code}", f"BS{code}00", f"BS{code}0"]:
                if variant in avail_codes and variant not in matched_codes:
                    matched_codes.append(variant)
        if not matched_codes:
            continue

        # Get output and compute impacts
        shock_dict = {}
        for c in matched_codes:
            out = get_actual_output(geo, year, [c])
            if out > 0:
                shock_dict[c] = out
        if not shock_dict:
            continue

        total_output = sum(shock_dict.values())
        try:
            _, sum_df = compute_impacts(
                shock_dict, geo, year, scope, matched_codes, geo_scope=geo_scope
            )
            if sum_df is None or sum_df.empty:
                continue
            gdp = sum_df[
                sum_df["metric"].str.contains("Gross domestic.*basic prices",
                                               case=False, na=False)
            ]["impact_dollars"].sum()
            jobs = sum_df[
                sum_df["metric"].str.contains("^Jobs$", case=False, na=False)
            ]["impact_dollars"].sum()
            rows.append({
                "Sector": sector_name,
                "Output": total_output,
                "GDP": gdp,
                "Jobs": jobs,
                "Codes": len(matched_codes),
            })
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("GDP", ascending=False)


def _render_mfg_comparison_chart(mfg_df: pd.DataFrame,
                                  metric: str = "GDP") -> io.BytesIO:
    """Horizontal bar chart comparing manufacturing sectors."""
    if mfg_df is None or mfg_df.empty:
        return io.BytesIO()
    fig, ax = plt.subplots(figsize=(7, 6.0))
    fig.patch.set_facecolor("white")
    df = mfg_df.sort_values(metric, ascending=True).copy()
    y = np.arange(len(df))
    colors = []
    for _, row in df.iterrows():
        if row["Sector"] == "Food & Beverage":
            colors.append("#059669")  # Emerald highlight
        else:
            colors.append("#94a3b8")  # Subtle grey
    bars = ax.barh(y, df[metric].values, color=colors, height=0.55,
                   edgecolor="white", linewidth=0.8)
    max_val = df[metric].max()
    for bar, val in zip(bars, df[metric].values):
        if metric == "Jobs":
            label = f"{val:,.0f}"
        else:
            label = _fmt(val)
        ax.text(bar.get_width() + max_val * 0.02, bar.get_y() + bar.get_height()/2,
                label, va="center", ha="left", fontsize=9, fontweight="bold", color="#333")
    ax.set_yticks(y)
    ax.set_yticklabels(df["Sector"].values, fontsize=10)
    if metric == "Jobs":
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{x/1000:.0f}K" if x >= 1000 else f"{x:.0f}"))
        title = "Employment by Manufacturing Sector"
    else:
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_short(x)))
        title = "GDP Contribution by Manufacturing Sector"
    ax.set_xlim(0, max_val * 1.35)
    ax.set_title(title, pad=12)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.text(0.99, 0.01, "Source: Statistics Canada (IO Multipliers)", ha='right', va='bottom', fontsize=7, color='#666666', style='italic')
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig); buf.seek(0); return buf


# ─────────────────────────────────────────────────────────────────────────────
# NARRATIVE GENERATION (Finding 5: enhanced talking points)
# ─────────────────────────────────────────────────────────────────────────────




def _compute_multi_year_trends(geo: str, scope_label: str,
                                basket_codes: list,
                                geo_scope: str = "all_provinces") -> pd.DataFrame:
    """Compute GDP and Jobs for all available years (2010-2022).
    Returns DataFrame with columns: Year, GDP, Jobs."""
    from scripts.io_multipliers_engine import (
        compute_impacts, get_actual_output, load_multipliers, SCOPE_TO_MULT_TYPE
    )
    # Determine available years from output data
    years = list(range(2010, 2023))  # 2010-2022
    scope_map = {
        "direct": "direct",
        "direct + indirect": "direct_indirect",
        "direct + indirect + induced": "direct_indirect_induced",
    }
    scope = scope_map.get(scope_label.lower(), "direct_indirect")

    results = []
    for yr in years:
        # Check if we have output data for this year
        total_output = sum(get_actual_output(geo, yr, [c]) for c in basket_codes)
        if total_output <= 0:
            continue
        # Build shock dict with actual output per code
        shock = {}
        for code in basket_codes:
            out = get_actual_output(geo, yr, [code])
            if out > 0:
                shock[code] = out
        if not shock:
            continue
        # Compute impacts
        try:
            _, sum_df = compute_impacts(shock, geo, yr, scope,
                                        basket_codes, geo_scope=geo_scope)
            if sum_df.empty:
                continue
            gdp = sum_df[sum_df["metric"].str.contains("Gross domestic.*basic prices",
                         case=False, na=False)]["impact_dollars"].sum()
            jobs = sum_df[sum_df["metric"].str.contains("^Jobs$",
                         case=False, na=False)]["impact_dollars"].sum()
            results.append({"Year": yr, "GDP": gdp, "Jobs": jobs})
        except Exception:
            continue
    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)

def _build_industry_list(basket_codes, basket_name: str,
                          get_sector_label_fn=None, is_basket: bool = True) -> str:
    """Build a readable description of the industries in the selected basket/industry."""
    if not basket_codes:
        return ""
    # Defensive: ensure basket_codes is a list
    if isinstance(basket_codes, str):
        basket_codes = [basket_codes]
    try:
        if get_sector_label_fn:
            names = [str(get_sector_label_fn(code)) for code in basket_codes]
        else:
            names = [str(code) for code in basket_codes]

        if not is_basket or len(basket_codes) == 1:
            return (f"This analysis focuses on the {names[0]} industry "
                    f"(NAICS {basket_codes[0]}).")

        # For sector groupings, build a readable list
        intro = (f"The {basket_name} sector encompasses {len(basket_codes)} "
                 f"NAICS industries spanning the following activities:\n")
        items = []
        for code, name in zip(basket_codes, names):
            items.append(f"  - {name} ({code})")
        return intro + "\n".join(items)
    except Exception:
        return ""

def _build_talking_points(geo, basket_name, year, total_output, total_gdp,
                          jobs, avg_wage, leak_pct, scope_label,
                          fiscal=None, income=None) -> list[str]:
    """Generate 5-6 consultant-grade talking points."""
    geo_scope = "nation" if geo == "Canada" else "province"
    points = []
    if total_output > 0:
        points.append(
            f"The {basket_name} sector in {geo} generates {_fmt(total_output)} "
            f"in total economic output ({year}), supporting {jobs:,.0f} jobs "
            f"across the {geo_scope}.")
    if total_gdp > 0 and total_output > 0:
        ratio = total_gdp / total_output * 100
        points.append(
            f"For every dollar of output produced, {ratio:.0f} cents remain in the "
            f"economy as value added (GDP) - demonstrating strong domestic retention.")
    if fiscal and fiscal.get("total_tax", 0) > 0:
        points.append(
            f"The sector generates {_fmt(fiscal['total_tax'])} in government tax revenue, "
            f"flowing to federal, provincial, and municipal treasuries.")
    if fiscal and fiscal.get("total_tax", 0) > 0 and fiscal.get("subsidies", 0) > 0:
        points.append(
            f"While the sector requires government support to manage production risk (receiving {_fmt(fiscal['subsidies'])} "
            f"in subsidies), it simultaneously anchors a supply chain that generates {_fmt(fiscal['total_tax'])} in "
            f"downstream transactional and production tax revenue.")
    if "Ontario" in geo:
        points.append(
            f"The sector is a critical pillar of provincial food security, feeding millions of "
            f"Ontarians while anchoring employment in rural communities outside the GTA.")
    if income and income.get("uninc_pct", 0) > 5:
        points.append(
            f"Approximately {income['uninc_pct']:.0f}% of sector income flows to "
            f"independent, family-owned businesses — anchoring rural entrepreneurship.")
    if avg_wage > 0:
        points.append(
            f"Workers across the sector earn an average of {_fmt(avg_wage)} annually, "
            f"supporting household spending and community vitality.")
    if leak_pct > 0:
        retention = 100 - leak_pct
        points.append(
            f"Approximately {retention:.0f}% of sector spending is retained domestically, "
            f"with only {leak_pct:.1f}% flowing to international imports.")
    return points[:6]


def _build_action_title(template: str, **kwargs) -> str:
    """Build McKinsey-style action title from data."""
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return template


# ─────────────────────────────────────────────────────────────────────────────
# WORD STYLING HELPERS (Finding 3: Tufte-style professional formatting)
# ─────────────────────────────────────────────────────────────────────────────

def _set_cell_shading(cell, color_hex: str):
    """Set cell background color."""
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shading)


def _style_tufte_table(table, header_bg="#1B2A4A", header_fg=_WHITE,
                       alt_row_bg="#F8FAFB"):
    """Apply Tufte-inspired table styling: heavy top/bottom borders, clean interior."""
    table.style = None  # Remove default style
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else parse_xml(f'<w:tblPr {nsdecls("w")}/>')

    # Style header row
    for cell in table.rows[0].cells:
        _set_cell_shading(cell, header_bg)
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.font.color.rgb = header_fg
                run.font.bold = True
                run.font.size = Pt(9)
                run.font.name = "Calibri"

    # Style data rows with alternating shading
    for row_idx in range(1, len(table.rows)):
        for cell in table.rows[row_idx].cells:
            if row_idx % 2 == 0:
                _set_cell_shading(cell, alt_row_bg)
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9)
                    run.font.name = "Calibri"
                    run.font.color.rgb = _DARK_GREY


def _add_styled_heading(doc, text, level=1):
    """Add a heading with navy color and Calibri Light font."""
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.color.rgb = _NAVY
        run.font.name = "Calibri Light"
    return h


def _add_body_text(doc, text):
    """Add body paragraph with consistent styling."""
    p = doc.add_paragraph(text)
    for run in p.runs:
        run.font.size = Pt(10.5)
        run.font.name = "Calibri"
        run.font.color.rgb = _DARK_GREY
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.15
    return p


# ─────────────────────────────────────────────────────────────────────────────
# 1. FULL CONSULTANT REPORT (Word, 12-15 pages)
# ─────────────────────────────────────────────────────────────────────────────

def generate_full_report(
    geo: str, basket_name: str, year: int, scope_label: str,
    prov_scope_label: str,
    sum_df: pd.DataFrame, bd_df: pd.DataFrame, res_df: pd.DataFrame,
    raw_mult_df: pd.DataFrame = None,
    jobs: float = 0, avg_wage: float = 0,
    get_sector_label_fn=None,
    basket_codes: list = None,
    is_basket: bool = True,
    shock_source: str = "Historical StatCan Output",
    basket_config: dict = None,
) -> io.BytesIO:
    """Generate a world-class economic impact report (Word, 12-15 pages)."""
    basket_name = _strip_emojis(basket_name)
    sl_lower = str(scope_label).lower()
    if "induced" in sl_lower:
        scope_label = "Direct + Indirect + Induced"
    elif "indirect" in sl_lower:
        scope_label = "Direct + Indirect"
    else:
        scope_label = "Direct"

    if basket_config is None:
        basket_config = {}
    doc = Document()
    for section in doc.sections:
        section.top_margin = Cm(2.2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    # Pre-compute
    total_output = _get_metric(sum_df, "Output")
    total_gdp = _get_metric(sum_df, "Gross domestic")
    imports_val = _get_metric(sum_df, "International imports")
    exports_val = _get_metric(sum_df, "International exports")
    leak_pct = (imports_val / total_output * 100) if total_output > 0 else 0
    fiscal = _compute_fiscal(sum_df)
    income = _compute_income_distribution(sum_df)

    # Bug 1: Filter breakdown data to match the user's selected scope
    bd_df = _filter_bd_by_scope(bd_df, scope_label)

    # ══ COVER ══
    import os
    logo_path = os.path.join(os.path.dirname(__file__), "..", "app", "data", "OFA_logo.png")
    if os.path.exists(logo_path):
        p_logo = doc.add_paragraph()
        p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_logo.add_run().add_picture(logo_path, width=Inches(2.5))
        for _ in range(2):
            doc.add_paragraph("")
    else:
        for _ in range(5):
            doc.add_paragraph("")
            
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("Economic Impact Assessment")
    run.font.size = Pt(32); run.font.color.rgb = _NAVY; run.font.bold = True; run.font.name = "Calibri Light"
    doc.add_paragraph("")
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = sub.add_run(basket_name)
    run.font.size = Pt(20); run.font.color.rgb = _EMERALD; run.font.bold = True; run.font.name = "Calibri Light"
    geo_p = doc.add_paragraph()
    geo_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = geo_p.add_run(f"{geo}  -  {year}")
    run.font.size = Pt(16); run.font.color.rgb = _MID_GREY; run.font.name = "Calibri Light"
    geo_p.paragraph_format.space_after = Pt(48)
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = meta.add_run(
        f"Prepared by the Ontario Federation of Agriculture\n\n"
        f"Impact Scope: {scope_label}\nMultiplier Scope: {prov_scope_label}\n"
        f"Shock Source: {shock_source}\n\nGenerated: {date.today().strftime('%B %d, %Y')}")
    run.font.size = Pt(10); run.font.color.rgb = _MID_GREY; run.font.name = "Calibri"
    src = doc.add_paragraph()
    src.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = src.add_run(f"\nData Source: Statistics Canada Input-Output Tables\nTable {'36-10-0594' if geo == 'Canada' else '36-10-0595'}")
    run.font.size = Pt(9); run.font.italic = True; run.font.color.rgb = _LIGHT_GREY; run.font.name = "Calibri"
    doc.add_page_break()

    # ══ HEADERS & FOOTERS ══
    for section in doc.sections:
        # Header
        header = section.header
        hp = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
        hp.text = f"{basket_name} - Economic Impact Assessment"
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for r in hp.runs:
            r.font.size = Pt(9)
            r.font.name = "Calibri"
            r.font.color.rgb = _MID_GREY
            r.font.italic = True
        
        # Footer
        footer = section.footer
        fp = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        fp.text = "Ontario Federation of Agriculture | ofa.on.ca | Page "
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for r in fp.runs:
            r.font.size = Pt(9)
            r.font.name = "Calibri"
            r.font.color.rgb = _MID_GREY
        
        # Page numbers
        r_pg = fp.add_run()
        for r in fp.runs:
            r.font.size = Pt(9)
            r.font.name = "Calibri"
            r.font.color.rgb = _MID_GREY

        f1 = OxmlElement('w:fldChar')
        f1.set(qn('w:fldCharType'), 'begin')
        r_pg._r.append(f1)
        i1 = OxmlElement('w:instrText')
        i1.set(qn('xml:space'), 'preserve')
        i1.text = 'PAGE'
        r_pg._r.append(i1)
        f2 = OxmlElement('w:fldChar')
        f2.set(qn('w:fldCharType'), 'separate')
        r_pg._r.append(f2)
        f3 = OxmlElement('w:fldChar')
        f3.set(qn('w:fldCharType'), 'end')
        r_pg._r.append(f3)

    # Disable header/footer on cover page
    doc.sections[0].different_first_page_header_footer = True



    # ══ 1. EXECUTIVE SUMMARY ══
    _add_styled_heading(doc, "1. Executive Summary", level=1)
    model_name = _scope_model_name(scope_label)
    _add_body_text(doc,
        f"This report quantifies the economic impact of the {basket_name} sector "
        f"in {geo} for {year}, using Statistics Canada's symmetric Input-Output "
        f"multipliers under the {model_name} ({scope_label.lower()} scope). "
        f"The sector generates {_fmt(total_output)} in total economic output, contributes "
        f"{_fmt(total_gdp)} to GDP, and supports {jobs:,.0f} jobs across the province.")

    # Industry composition explanation
    ind_text = _build_industry_list(basket_codes, basket_name,
                                     get_sector_label_fn, is_basket)
    if ind_text:
        _add_body_text(doc, ind_text)
    
    if "food system" in basket_name.lower():
        _add_body_text(doc, 
            "The 'Food System' represents the complete farm-to-fork value chain. This includes Primary Agriculture (the raw commodities), "
            "Food & Beverage Manufacturing (processing of those commodities), and the downstream Logistics, Wholesale, and Retail sectors "
            "that deliver finished products to consumers. By capturing this entire ecosystem, we can quantify its total significance to the provincial economy.")
    doc.add_paragraph("")

    if fiscal["total_tax"] > 0:
        _add_body_text(doc,
            f"The sector generates {_fmt(fiscal['total_tax'])} in government tax revenue, "
            f"supporting public services and infrastructure across {geo}. "
            f"This fiscal contribution is vital for sustaining community investments, "
            f"healthcare, education, and regional development initiatives. A strong and resilient "
            f"agricultural and food processing base ensures a reliable tax base that benefits all "
            f"residents, bridging the economic gap between rural production hubs and urban consumer centers.")
            
    if "food system" in basket_name.lower():
        _add_body_text(doc,
            "Within this broader system, the downstream components—particularly Food Retail and Foodservice—"
            "play a dominant role in employment generation. These sectors serve as the critical final link "
            "to consumers and require a massive workforce to operate efficiently. This extensive "
            "downstream footprint demonstrates how agricultural production cascades through the economy to "
            "support hundreds of thousands of front-line jobs.")
            
    _add_body_text(doc,
        f"Furthermore, the sector exhibits exceptional domestic value retention. Only {leak_pct:.1f}% of total "
        f"spending leaks out of the domestic economy through international imports, meaning approximately "
        f"{100-leak_pct:.0f}% of the economic activity remains within Canada. This strong domestic "
        f"retention ensures that the wages, taxes, and indirect supply chain spending generated by the sector "
        f"continue to circulate locally, amplifying its overall economic impact.")
            
    _add_body_text(doc,
        f"Beyond the top-line numbers, the economic activity detailed in this report highlights the "
        f"interconnected nature of the {geo} economy. The sector serves as a foundational pillar "
        f"that not only provides essential goods but also sustains a vast network of suppliers, "
        f"logistics providers, and ancillary services. From specialized equipment manufacturers "
        f"to local transportation networks, the ongoing vitality of the {basket_name} sector is "
        f"integral to the broader economic resilience of the region.")
    doc.add_paragraph("")

    if "Ontario" in geo:
        # StatCan exact historical data for Ontario
        ont_jobs_by_year = {
            2018: 7343300, 2019: 7458700, 2020: 7088300, 
            2021: 7455700, 2022: 7732100, 2023: 7915300
        }
        ont_households_by_year = {
            # Based on 2021 Census (5,491,200) and historical growth rates
            2018: 5290000, 2019: 5370000, 2020: 5430000,
            2021: 5491200, 2022: 5580000, 2023: 5670000
        }
        ontario_jobs = ont_jobs_by_year.get(year, 7732100)
        ontario_households = ont_households_by_year.get(year, 5580000)
        job_ratio = ontario_jobs / jobs if jobs > 0 else 0
        
        auto_gdp = 11600000000  # $11.6B
        auto_jobs = 104000
        gdp_comp = "surpasses" if total_gdp > auto_gdp else ("rivals" if total_gdp > auto_gdp * 0.5 else "is a fraction of")
        job_comp = "eclipsing" if jobs > auto_jobs else ("comparable to" if jobs > auto_jobs * 0.5 else "fewer than")
        
        _add_styled_heading(doc, f"The {geo} Context", level=3)
        _add_body_text(doc, 
            f"Ontario's agri-food system is one of the province's largest economic engines, "
            f"with a geographic reach that anchors rural communities from Windsor to Ottawa. "
            f"For context, Ontario's renowned automotive manufacturing sector (including both vehicle assembly and auto parts manufacturing) contributed $11.6 billion to GDP "
            f"and directly employed roughly 104,000 people in 2022. By contrast, the {basket_name} sector "
            f"{gdp_comp} the auto sector with a {_fmt(total_gdp)} GDP contribution, while {job_comp} "
            f"it by supporting {jobs:,.0f} jobs (approximately 1 in {job_ratio:.0f} Ontario jobs).")
        doc.add_paragraph("")

    # Sub-component breakdown for food system reports
    if "food system" in basket_name.lower() and res_df is not None and not res_df.empty:
        subcomp_df = _compute_food_system_subcomponents(res_df)
        if not subcomp_df.empty:
            _add_styled_heading(doc, "Food System Breakdown by Segment", level=3)
            _add_body_text(doc,
                "The following table summarises the relative contribution of each segment of the food system "
                "to total GDP and employment, illustrating the breadth and diversity of the sector.")
            sc_table = doc.add_table(rows=1 + len(subcomp_df), cols=4)
            for i, h in enumerate(["Segment", "GDP Contribution", "Jobs Supported", "Share of GDP"]):
                sc_table.rows[0].cells[i].text = h
            for ri, (_, row) in enumerate(subcomp_df.iterrows()):
                sc_table.rows[ri+1].cells[0].text = str(row["Component"])
                sc_table.rows[ri+1].cells[1].text = _fmt(row["GDP"])
                sc_table.rows[ri+1].cells[2].text = f"{row['Jobs']:,.0f}"
                sc_table.rows[ri+1].cells[3].text = f"{row['GDP_Share']:.1f}%"
                for ci in range(1, 4):
                    for p in sc_table.rows[ri+1].cells[ci].paragraphs:
                        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            _style_tufte_table(sc_table)
            doc.add_paragraph("")

    _add_styled_heading(doc, "Key Highlights At a Glance", level=3)
    # KPI tables (full-precision values for executive credibility)
    for kpi_set in [
        [("Total Output", _fmt_full(total_output)), ("GDP Contribution", _fmt_full(total_gdp)), ("Jobs Supported", f"{jobs:,.0f}")],
        [("Average Wage", _fmt_full(avg_wage)), ("Tax Revenue", _fmt_full(fiscal['total_tax'])), ("Spending Retained in Canada", f"{100-leak_pct:.0f}%")]
    ]:
        t = doc.add_table(rows=2, cols=3)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, (h, v) in enumerate(kpi_set):
            t.rows[0].cells[i].text = h
            t.rows[1].cells[i].text = v
        _style_tufte_table(t, header_bg="1B2A4A")
        for cell in t.rows[1].cells:
            for p in cell.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:
                    r.font.size = Pt(16); r.font.bold = True; r.font.color.rgb = _EMERALD
        doc.add_paragraph("")

    # ══ 2. METHODOLOGY ══
    _add_styled_heading(doc, "2. Methodology", level=1)
    model_name = _scope_model_name(scope_label)
    _add_body_text(doc,
        "This analysis employs Statistics Canada's symmetric Input-Output (IO) "
        "multipliers to quantify the economic impact of the " + basket_name + " sector in "
        + geo + ". The IO model, based on data collected by Statistics Canada, maps out the "
        "relationships between different industries and sectors within the economy. It shows "
        "how the production from one industry is used as an input in other industries, "
        "allowing us to trace the flow of goods and services and measure the total economic impact.")
    if scope_label == "Direct":
        _add_styled_heading(doc, "Direct Economic Footprint", level=2)
        _add_body_text(doc, 
            "This analysis strictly employs the Direct scope. For highly integrated economic sectors "
            f"like the {basket_name} sector, which spans multiple layers of the supply chain "
            "(e.g., primary agriculture, food processing, and retail), utilizing a Direct-only scope "
            "prevents the double-counting of economic activity. For example, if we included indirect "
            "impacts, the value of wheat sold by a farmer would be counted once at the farm gate, and "
            "then counted again as an 'indirect' supply-chain input when analyzing the flour mill. "
            "By measuring only the direct value-added and employment generated within each specific sub-sector, "
            "this approach provides the most accurate, defensible estimate of the true economic footprint of the entire system.")
    else:
        _add_body_text(doc,
            "The IO model captures economic activity through up to three impact layers:")
        for term, defn in [
            ("Direct Effects",
             "The initial economic activities within the sector itself, such as the production and sale of goods."),
            ("Indirect Effects",
             "The additional economic activities generated in the supply chain. When the sector purchases "
             "inputs such as seeds, fuel, machinery, and services, the businesses supplying these inputs "
             "generate their own economic activity, employment, and tax revenue."),
            ("Induced Effects",
             "The further economic activities stimulated by the spending of incomes earned in the sector. "
             "When sector workers spend their wages on goods and services within the province, such as "
             "groceries, housing, and services, this spending supports other local businesses and creates "
             "additional economic activity.")]:
            p = doc.add_paragraph()
            r = p.add_run(term + ": "); r.font.bold = True; r.font.size = Pt(10.5)
            r.font.name = "Calibri"; r.font.color.rgb = _NAVY
            r = p.add_run(defn); r.font.size = Pt(10.5); r.font.name = "Calibri"; r.font.color.rgb = _DARK_GREY
            p.paragraph_format.space_after = Pt(4)
        # Open vs Closed Model explanation
        _add_styled_heading(doc, "Open and Closed Model Framework", level=2)
        _add_body_text(doc,
            "In IO analysis, the Open Model captures only direct and indirect effects -- "
            "providing a conservative estimate that reflects the immediate financial transactions "
            "and supply chain impacts. The Closed Model takes a broader view by also including "
            "induced effects: the additional rounds of spending that occur when employees spend "
            "their earnings in the local economy.")
        _add_body_text(doc,
            f"This analysis uses the {model_name} ({scope_label}), meaning the results "
            + ("capture the full ripple effect through supply chains and household re-spending." if "Induced" in scope_label
               else "capture direct production activity and its supply chain impacts, but do not include household re-spending effects. "
                    "This provides a conservative, defensible estimate of economic impact."))
    # Caveats
    _add_body_text(doc,
        "While IO models provide valuable insights, results should be interpreted "
        "with appropriate caution. IO models assume fixed input-output ratios, do not account "
        "for price changes or supply constraints, and represent a static snapshot of the economic "
        "structure for the reference year." + 
        (" The induced effects in particular may overstate actual impacts due to assumptions about local spending rates." if "Induced" in _allowed_types(scope_label) else ""))
    _add_body_text(doc,
        "Because IO models do not account for price effects, recent spikes in energy and fertilizer "
        "costs may inflate total output values without a corresponding increase in physical production or "
        "employment. These output spikes are mechanically translated by the model into job and GDP growth, "
        "which can overstate the true economic expansion during inflationary periods.")
    doc.add_paragraph("")
    # Parameters table
    _add_styled_heading(doc, "Analysis Parameters", level=2)
    pt = doc.add_table(rows=7, cols=2); pt.alignment = WD_TABLE_ALIGNMENT.LEFT
    for i, (k, v) in enumerate([("Parameter", "Value"), ("Geography", geo),
        ("Industry / Economic Sector", basket_name), ("Reference Year", str(year)),
        ("Impact Scope", f"{scope_label} ({model_name})"),
        ("Multiplier Scope", prov_scope_label if geo != "Canada" else "National"),
        ("Data Source", f"Statistics Canada Table {'36-10-0594' if geo == 'Canada' else '36-10-0595'}")]):
        pt.rows[i].cells[0].text = k; pt.rows[i].cells[1].text = v
    _style_tufte_table(pt)
    doc.add_paragraph("")

    if scope_label == "Direct":
        _add_body_text(doc,
            "As this analysis focuses exclusively on the Direct scope, it measures the immediate "
            "output generated by the sector itself. Since no supply chain multiplier effects are calculated, "
            "the geographic multiplier scope (Within Province vs. All Provinces) does not apply.")
        doc.add_paragraph("")
    elif "All Provinces" in prov_scope_label:
        _add_body_text(doc,
            "The 'All Provinces' multiplier scope means that the analysis captures economic "
            "spillovers that occur when inputs are sourced from other Canadian provinces. "
            "This approach was selected to provide a comprehensive view of the sector's true "
            "national economic footprint, preventing artificial 'leakage' when an Ontario "
            "farm or processor purchases inputs (like fertilizer or specialized machinery) "
            "from neighboring provinces like Quebec or Manitoba.")
        doc.add_paragraph("")

    # ══ 3. ECONOMIC IMPACT ANALYSIS ══
    _add_styled_heading(doc, "3. Economic Impact Analysis", level=1)

    # 3.1 GDP
    _add_styled_heading(doc, "3.1  GDP Contribution", level=2)
    allowed = _allowed_types(scope_label)
    gd = _get_bd_metric(bd_df, "Gross domestic.*basic prices", "Direct")
    gi = _get_bd_metric(bd_df, "Gross domestic.*basic prices", "Indirect") if "Indirect" in allowed else 0
    gind = _get_bd_metric(bd_df, "Gross domestic.*basic prices", "Induced") if "Induced" in allowed else 0
    gdp_sum = gd + gi + gind

    # Educational block: What is GDP at Basic Prices?
    _add_body_text(doc,
        "GDP at Basic Prices represents the total market value of all goods and services "
        "produced by the sector, adjusted to isolate the true economic contribution. Specifically, "
        "it subtracts the cost of intermediate inputs (such as seeds, fuel, and raw materials), "
        "removes the effect of indirect taxes (which could artificially inflate output), and adds "
        "back any subsidies (including government program payments and agricultural subsidies for primary agriculture).")
    _add_body_text(doc,
        "This adjustment is critical because it strips away external factors, allowing us to "
        "see the intrinsic economic output -- what the sector itself produces without distortions "
        "from fluctuating input costs or fiscal policy changes. GDP at basic prices is the standard "
        "measure used by Statistics Canada for inter-industry economic analysis.")
    _add_body_text(doc,
        "For example, in primary agriculture, GDP at basic prices roughly equates to "
        "total farm cash receipts minus the cost of intermediate inputs like seed, feed, "
        "and fertilizer. In food processing, it represents the wholesale value of the "
        "manufactured food products minus the cost of raw ingredients, packaging, and energy.")

    if total_gdp > 0:
        # Direct GDP narrative
        _add_body_text(doc,
            f"The direct GDP of the {basket_name} sector is {_fmt(gd)}. This represents "
            f"the immediate value added through the sector's own production activities.")

        # Indirect narrative
        if "Indirect" in allowed and gi > 0:
            _add_body_text(doc,
                f"When including the indirect effects -- the GDP generated by businesses that "
                f"supply inputs to the {basket_name.lower()} sector -- the contribution grows to "
                f"{_fmt(gd + gi)}. The indirect GDP of {_fmt(gi)} represents the "
                f"economic value created by supply chain partners whose sales depend on the sector's "
                f"demand for inputs.")

        # Induced narrative
        if "Induced" in allowed and gind > 0:
            _add_body_text(doc,
                f"The closed model incorporates induced effects: when sector workers spend their "
                f"earnings in the local economy, they generate an additional {_fmt(gind)} in GDP. "
                f"The total GDP contribution in the closed model is {_fmt(gdp_sum)}.")

        # Effective multiplier
        if gd > 0 and scope_label != "Direct":
            eff_mult = gdp_sum / gd
            _add_body_text(doc,
                f"The effective GDP multiplier is {eff_mult:.2f} -- meaning that for every dollar "
                f"of GDP generated directly by {basket_name.lower()} production, a total of "
                f"${eff_mult:.2f} in GDP is created across the {geo} economy.")

        # Build scope-aware table with full precision
        cols_data = [("Direct GDP", gd)]
        if "Indirect" in allowed: cols_data.append(("Indirect GDP", gi))
        if "Induced" in allowed: cols_data.append(("Induced GDP", gind))
        if scope_label != "Direct":
            cols_data.append(("Total GDP", total_gdp))
            if gd > 0:
                eff_mult = gdp_sum / gd
                cols_data.append(("Effective Multiplier", eff_mult))
        gt = doc.add_table(rows=3, cols=len(cols_data))
        hdrs = [c[0] for c in cols_data]
        for i, h in enumerate(hdrs):
            gt.rows[0].cells[i].text = h
        for i, (_, v) in enumerate(cols_data):
            if "Multiplier" in cols_data[i][0]:
                gt.rows[1].cells[i].text = f"{v:.2f}"
            else:
                gt.rows[1].cells[i].text = _fmt_full(v)
            for p in gt.rows[1].cells[i].paragraphs: p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        # Add description row
        descs = ["Value added directly by sector production"]
        if "Indirect" in allowed: descs.append("GDP generated by input suppliers")
        if "Induced" in allowed: descs.append("GDP from worker spending")
        if scope_label != "Direct":
            descs.append("Sum of all effects")
            if gd > 0: descs.append("Total / Direct")
        for i, d in enumerate(descs):
            gt.rows[2].cells[i].text = d
            for p in gt.rows[2].cells[i].paragraphs:
                for r in p.runs: r.font.size = Pt(8); r.font.italic = True; r.font.color.rgb = _MID_GREY
        _style_tufte_table(gt)
    doc.add_paragraph("")

    # 3.2 Employment & Income Distribution
    _add_styled_heading(doc, "3.2  Employment & Income Distribution", level=2)

    # Employment narrative
    jd = _get_bd_metric(bd_df, "Jobs", "Direct")
    ji = _get_bd_metric(bd_df, "Jobs", "Indirect") if "Indirect" in allowed else 0
    jind = _get_bd_metric(bd_df, "Jobs", "Induced") if "Induced" in allowed else 0

    if scope_label == "Direct":
        _add_body_text(doc,
            f"The {basket_name} sector directly supports {jobs:,.0f} jobs across "
            f"{geo}. These positions represent direct employment within the sector's "
            f"own operations, encompassing all employment types including full-time, "
            f"part-time, seasonal, and self-employed positions.")
    else:
        _add_body_text(doc,
            f"The {basket_name} sector supports a total of {jobs:,.0f} jobs across "
            f"{geo}. These jobs encompass all employment types sustained by sector output, "
            f"including positions directly within the sector and those supported through "
            f"supply chain and consumer spending linkages.")

    # Educational block: What does "Jobs" measure?
    _add_styled_heading(doc, "Understanding the Jobs Metric", level=3)
    _add_body_text(doc,
        "The 'Jobs' variable in Statistics Canada's IO multiplier tables represents "
        "a headcount of all positions supported by sector output. This includes "
        "full-time employees, part-time workers, seasonal and temporary positions, "
        "self-employed individuals (including owner-operators of unincorporated "
        "businesses), and unpaid family workers contributing to family-run enterprises. "
        "Each position is counted as one job regardless of the number of hours worked.")
    _add_body_text(doc,
        "It is important to note that the published IO multiplier tables do not "
        "separately identify Full-Time Equivalent (FTE) positions versus non-FTE "
        "or part-time employment. Nor does the model distinguish between hired "
        "labour (employees on payroll) and owner-operators or unpaid family workers "
        "who are common in agriculture and small-scale food processing.")


    if jd > 0:
        if scope_label == "Direct":
            # In Direct mode, total == direct, so skip the redundant breakdown
            pass
        else:
            _add_body_text(doc,
                f"Of the total {jobs:,.0f} jobs, the sector directly supports {jd:,.0f} "
                f"positions within its own operations."
                + (f" An additional {ji:,.0f} jobs are supported in supply chain industries "
                   f"that provide inputs to the sector." if ji > 0 else "")
                + (f" A further {jind:,.0f} jobs are sustained through the induced spending "
                   f"of sector workers in the local economy." if jind > 0 else ""))
            job_mult = jobs / jd
            _add_body_text(doc,
                f"The effective employment multiplier is {job_mult:.2f} -- meaning that "
                f"each job within the sector supports a total of {job_mult:.2f} jobs across the "
                f"broader {geo} economy.")

    # Employment breakdown chart
    emp_chart = _render_employment_chart(bd_df, scope_label, jobs)
    if emp_chart.getbuffer().nbytes > 0:
        doc.add_picture(emp_chart, width=Inches(4.5))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")

    # Labour income narrative
    _add_styled_heading(doc, "Labour Income", level=3)
    _add_body_text(doc,
        f"Labour income reflects the total earnings received by employees supported by "
        f"the sector, including wages, salaries, and employer social contributions. "
        f"Total labour compensation amounts to {_fmt(income['total_compensation'])}.")

    # Labour income effective multiplier
    lid = _get_bd_metric(bd_df, "Labour income$", "Direct")
    if lid > 0 and income["total_compensation"] > 0 and scope_label != "Direct":
        li_mult = income["total_compensation"] / lid
        _add_body_text(doc,
            f"The effective labour income multiplier is {li_mult:.2f} -- meaning that "
            f"for every dollar of labour income paid directly within the sector, a total "
            f"of ${li_mult:.2f} in labour income is generated across the {geo} economy.")

    wage_desc = "workers in direct, indirect, and induced employment" if scope_label != "Direct" else "workers within the sector"
    _add_body_text(doc,
        f"The average wage across the sector is {_fmt(avg_wage)}, reflecting the "
        f"weighted average of wages paid to {wage_desc}. Note that this average wage may appear lower than standard full-time equivalencies, as it incorporates seasonal, part-time, and transient labour typical in agriculture and food services.")

    # Income distribution
    if income["uninc_pct"] > 0:
        _add_body_text(doc,
            f"A distinguishing characteristic of this sector is the role of self-employment "
            f"income. {income['uninc_pct']:.1f}% of sector income ({_fmt(income['unincorporated'])}) "
            f"flows to the unincorporated sector -- independent owner-operators and family businesses. "
            f"This contrasts with industries dominated by corporate payrolls, where nearly "
            f"all labour income takes the form of wages and salaries. The presence of substantial "
            f"self-employment income underscores the entrepreneurial nature of the sector and its "
            f"role in sustaining independent business ownership. Specifically within primary agriculture, the vast majority of farms (including legally incorporated entities) are family-owned and operated.")

    # Table with full precision
    it = doc.add_table(rows=3, cols=4)
    for i, (l, v, desc) in enumerate([
        ("Wages & Salaries", income["wages"],
         "Earnings paid to employees"),
        ("Self-Employment Income", income["unincorporated"],
         "Income to independent owner-operators and family businesses"),
        ("Employer Contributions", income["social_contributions"],
         "CPP, EI, benefits"),
        ("Total Compensation", income["total_compensation"],
         "Sum of all labour income")]):
        it.rows[0].cells[i].text = l
        it.rows[1].cells[i].text = _fmt_full(v)
        for p in it.rows[1].cells[i].paragraphs: p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        it.rows[2].cells[i].text = desc
        for p in it.rows[2].cells[i].paragraphs:
            for r in p.runs: r.font.size = Pt(8); r.font.italic = True; r.font.color.rgb = _MID_GREY
    _style_tufte_table(it)
    doc.add_paragraph("")

    # 3.3 Fiscal Contribution
    _add_styled_heading(doc, "3.3  Tax Revenue", level=2)

    # Tax breakdown educational block
    _add_body_text(doc,
        "The Input-Output model traces the tax revenue generated at each stage of "
        "production as sector activity ripples through the economy. Two categories "
        "of tax are captured in the IO framework:")
    for term, defn in [
        ("Taxes on Products",
         "Taxes applied to the sale and consumption of goods and services, collected at various "
         "stages of the production and distribution process. These include sales taxes (GST/HST), "
         "excise taxes, and customs duties."),
        ("Taxes on Production",
         "Levies imposed on the assets and activities required to produce goods and services. "
         "These include property taxes on land and buildings, business taxes, and production-related "
         "permits and licence fees.")]:
        p = doc.add_paragraph()
        r = p.add_run(term + ": "); r.font.bold = True; r.font.size = Pt(10.5)
        r.font.name = "Calibri"; r.font.color.rgb = _NAVY
        r = p.add_run(defn); r.font.size = Pt(10.5); r.font.name = "Calibri"; r.font.color.rgb = _DARK_GREY
        p.paragraph_format.space_after = Pt(4)

    _add_body_text(doc,
        f"The {basket_name} sector generates {_fmt(fiscal['total_tax'])} in total "
        f"government tax revenue across all levels of government. This comprises "
        f"{_fmt(fiscal['taxes_products'])} in taxes on products and "
        f"{_fmt(fiscal['taxes_production'])} in taxes on production. These revenues "
        f"flow to federal, provincial, and municipal treasuries, supporting public services "
        f"and infrastructure across {geo}. Note that these estimates do not include personal or corporate income taxes, meaning the total fiscal contribution of the sector is likely understated.")
        
    _add_body_text(doc,
        "Additionally, the IO model uses sector averages and may not perfectly reflect ag-specific tax "
        "policies, such as the provincial fuel tax exemptions for primary producers. As a result, the "
        "taxes on production for primary agriculture may be moderately overstated.")

    # Tax revenue table
    tt = doc.add_table(rows=3, cols=3)
    for i, (l, v, desc) in enumerate([
        ("Taxes on Products", fiscal["taxes_products"], "GST/HST, excise, customs"),
        ("Taxes on Production", fiscal["taxes_production"], "Property tax, business licences"),
        ("Total Tax Revenue", fiscal["total_tax"], "Sum of all tax categories")]):
        tt.rows[0].cells[i].text = l
        tt.rows[1].cells[i].text = _fmt_full(v)
        for p in tt.rows[1].cells[i].paragraphs: p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        tt.rows[2].cells[i].text = desc
        for p in tt.rows[2].cells[i].paragraphs:
            for r in p.runs: r.font.size = Pt(8); r.font.italic = True; r.font.color.rgb = _MID_GREY
    _style_tufte_table(tt)
    doc.add_paragraph("")

    # 3.4 Trade
    _add_styled_heading(doc, "3.4  Supply Chain Import Reliance", level=2)
    _add_body_text(doc,
        "When the IO model traces how a sector's output ripples through the economy, "
        "not all of that spending stays within the domestic economy. A portion of "
        "the goods and services purchased as inputs must be sourced from abroad -- "
        "this outflow is known as import leakage. Import leakage directly affects "
        "the GDP contribution of a sector, because GDP measures only the value "
        "added within a country's borders. Dollars spent on imported inputs do not "
        "generate additional domestic GDP, and they do not support domestic wages or tax revenue.")
    _add_body_text(doc,
        f"For the {basket_name} sector, international imports account for "
        f"{_fmt(imports_val)}, representing a leakage rate of {leak_pct:.1f}%. "
        f"This means that {100-leak_pct:.0f}% of the sector's total output value "
        f"is retained within {geo}'s domestic economy. The retained share flows "
        f"to Canadian workers (as wages), Canadian businesses (as intermediate input "
        f"purchases from domestic suppliers), and Canadian governments (as tax revenue).")
    _add_body_text(doc,
        "A lower leakage rate is generally favourable from a domestic policy "
        "perspective, as it indicates that a greater share of sector activity "
        "is generating local economic benefit. Sectors with high domestic input "
        "requirements -- such as agriculture, which relies heavily on domestic "
        "land, labour, and locally sourced supplies -- tend to exhibit stronger "
        "value retention than import-dependent industries such as electronics "
        "or petroleum refining.")
    cb = _render_value_retention_chart(total_gdp, imports_val, exports_val)
    if cb.getbuffer().nbytes > 0:
        doc.add_picture(cb, width=Inches(5.5))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")

    # Sub-component leakage variation scan (Comment 16)
    if "food system" in (basket_name or "").lower() and res_df is not None:
        leak_df = _compute_leakage_by_subcomponent(res_df)
        if not leak_df.empty and len(leak_df) >= 2:
            _add_styled_heading(doc, "Import Leakage by Food System Segment", level=3)
            _add_body_text(doc,
                "Import leakage rates vary significantly across the food system's sub-components, "
                "reflecting differences in domestic sourcing patterns and reliance on imported inputs. "
                "The following table ranks each segment from lowest to highest leakage:")
            lt = doc.add_table(rows=1 + len(leak_df), cols=4)
            for i, h in enumerate(["Segment", "Output", "Import Leakage", "Domestic Retention"]):
                lt.rows[0].cells[i].text = h
            for ri, (_, row) in enumerate(leak_df.iterrows()):
                lt.rows[ri+1].cells[0].text = str(row["Component"])
                lt.rows[ri+1].cells[1].text = _fmt(row["Output"])
                lt.rows[ri+1].cells[2].text = f"{row['Leakage Rate']:.1f}%"
                lt.rows[ri+1].cells[3].text = f"{row['Domestic Retention']:.0f}%"
                for ci in range(1, 4):
                    for p in lt.rows[ri+1].cells[ci].paragraphs:
                        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            _style_tufte_table(lt)
            doc.add_paragraph("")
            # Narrative summary
            lowest = leak_df.iloc[0]
            highest = leak_df.iloc[-1]
            _add_body_text(doc,
                f"{lowest['Component']} exhibits the lowest leakage rate at {lowest['Leakage Rate']:.1f}%, "
                f"retaining {lowest['Domestic Retention']:.0f}% of its output value domestically. By contrast, "
                f"{highest['Component']} has the highest leakage at {highest['Leakage Rate']:.1f}%, "
                f"reflecting its greater reliance on imported raw materials and intermediate inputs.")
            doc.add_paragraph("")

    # ══ 3.5 HISTORICAL TREND ══
    if basket_codes and isinstance(basket_codes, (list, tuple)) and len(basket_codes) > 0:
        try:
            # Determine geo_scope from prov_scope_label
            gs = "within_province" if "within" in prov_scope_label.lower() else "all_provinces"
            trend_df = _compute_multi_year_trends(geo, scope_label, list(basket_codes), gs)
            if trend_df is not None and not trend_df.empty and len(trend_df) >= 2:
                _add_styled_heading(doc, "3.5  Historical Trend", level=2)
                _add_body_text(doc,
                    f"The following chart traces the GDP contribution and employment impact of "
                    f"the {basket_name} sector between {int(trend_df['Year'].min())} and {int(trend_df['Year'].max())}. Each year's "
                    f"impact is computed using historical output volumes from Statistics Canada's "
                    f"supply-use tables (Table 36-10-0402), multiplied by the IO multiplier "
                    f"coefficients for that year. This provides a view of how the sector's economic "
                    f"footprint has evolved over time.")
                _add_body_text(doc,
                    f"All values reflect the {scope_label} scope, consistent with the "
                    f"analysis throughout this report.")
                cb = _render_trend_chart(trend_df, geo, basket_name, scope_label)
                if cb.getbuffer().nbytes > 0:
                    doc.add_picture(cb, width=Inches(5.5))
                    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                # Add a summary of the trend
                first = trend_df.iloc[0]
                last = trend_df.iloc[-1]
                if first["GDP"] > 0 and first["Jobs"] > 0:
                    gdp_change = (last["GDP"] - first["GDP"]) / first["GDP"] * 100
                    jobs_change = (last["Jobs"] - first["Jobs"]) / first["Jobs"] * 100
                    _add_body_text(doc,
                        f"Between {int(first['Year'])} and {int(last['Year'])}, the sector's "
                        f"GDP contribution {'grew' if gdp_change > 0 else 'declined'} by "
                        f"{abs(gdp_change):.1f}% (from {_fmt(first['GDP'])} to {_fmt(last['GDP'])}), "
                        f"while employment {'increased' if jobs_change > 0 else 'decreased'} by "
                        f"{abs(jobs_change):.1f}% (from {first['Jobs']:,.0f} to {last['Jobs']:,.0f} jobs).")
        except Exception:
            pass  # Silently skip if trend computation fails
    doc.add_paragraph("")

    # ══ 4. RIPPLE EFFECT ══
    if scope_label != "Direct":
        _add_styled_heading(doc, "4. Ripple Effect Decomposition", level=1)
        _add_body_text(doc,
            f"The economic impact of the {basket_name} sector extends far beyond the sector's "
            f"own direct output. The revenue generated by the sector is used to purchase inputs "
            f"from suppliers -- equipment, fuel, professional services, and raw materials. Those "
            f"suppliers, in turn, generate their own economic activity, sustaining their employees "
            f"and their own supply chains.")
        _add_body_text(doc,
            "The following chart decomposes the total economic impact into its constituent "
            "layers, illustrating how direct activity cascades through supply chains "
            + ("and household spending." if "Induced" in scope_label
               else "to input-supplying industries."))
        cb = _render_ripple_chart(bd_df, scope_label)
        if cb.getbuffer().nbytes > 0:
            doc.add_picture(cb, width=Inches(5.5))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        direct_out = _get_bd_metric(bd_df, "Output", "Direct")
        if direct_out > 0 and total_output > 0:
            mult = total_output / direct_out
            if mult > 1:
                _add_body_text(doc,
                    f"The total output multiplier of {mult:.2f} indicates that every dollar "
                    f"of direct activity generates an additional ${mult-1:.2f} in supply chain "
                    f"and household impacts.")
        doc.add_paragraph("")

    # ══ 5. SECTOR COMPOSITION ══
    next_sec_num = 4 if scope_label == "Direct" else 5
    if is_basket and res_df is not None and not res_df.empty:
        _add_styled_heading(doc, f"{next_sec_num}. Sector Composition", level=1)
        _add_body_text(doc,
            f"The {basket_name} sector comprises {len(basket_codes or [])} NAICS industries, "
            f"each weighted by actual economic output.")
        cb = _render_sector_donut(res_df, get_sector_label_fn)
        if cb.getbuffer().nbytes > 0:
            doc.add_picture(cb, width=Inches(5))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph("")

        # ── 5.1 PRIMARY AGRICULTURE COMMODITY BREAKDOWN ──
        commodity_df = _compute_primary_ag_breakdown(res_df)
        if not commodity_df.empty:
            _add_styled_heading(doc, f"{next_sec_num}.1  Primary Agriculture: Commodity Breakdown", level=2)
            _add_body_text(doc,
                "The primary agriculture sector encompasses a diverse range of commodity groups, "
                "each contributing different economic profiles. The following breakdown isolates the "
                "direct economic contribution of each major commodity category within the primary "
                "agriculture component of this analysis.")

            # GDP by commodity chart
            _add_styled_heading(doc, "Primary Agriculture GDP Contribution by Commodity", level=3)
            gdp_comm_chart = _render_commodity_metric_chart(commodity_df, "GDP")
            if gdp_comm_chart.getbuffer().nbytes > 0:
                doc.add_picture(gdp_comm_chart, width=Inches(5.5))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            doc.add_paragraph("")

            # Jobs by commodity chart
            _add_styled_heading(doc, "Primary Agriculture Employment by Commodity", level=3)
            jobs_comm_chart = _render_commodity_metric_chart(commodity_df, "Jobs")
            if jobs_comm_chart.getbuffer().nbytes > 0:
                doc.add_picture(jobs_comm_chart, width=Inches(5.5))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            doc.add_paragraph("")

            # Commodity detail table
            ct = doc.add_table(rows=1 + len(commodity_df), cols=5)
            for i, h in enumerate(["Commodity", "Output", "GDP", "Jobs", "Share (%)"]):
                ct.rows[0].cells[i].text = h
            for ri, (_, row) in enumerate(commodity_df.iterrows()):
                ct.rows[ri+1].cells[0].text = str(row["Commodity"])
                ct.rows[ri+1].cells[1].text = _fmt_full(row["Output"])
                ct.rows[ri+1].cells[2].text = _fmt_full(row["GDP"])
                ct.rows[ri+1].cells[3].text = f"{row['Jobs']:,.0f}"
                ct.rows[ri+1].cells[4].text = f"{row['Share']:.1f}%"
                for ci in range(1, 5):
                    for p in ct.rows[ri+1].cells[ci].paragraphs:
                        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            _style_tufte_table(ct)
            doc.add_paragraph("")

            # Summary output chart at end of subsection
            comm_chart = _render_commodity_chart(commodity_df)
            if comm_chart.getbuffer().nbytes > 0:
                doc.add_picture(comm_chart, width=Inches(5.5))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            doc.add_paragraph("")

            # Narrative highlights
            if len(commodity_df) >= 2:
                top = commodity_df.iloc[0]
                second = commodity_df.iloc[1]
                _add_body_text(doc,
                    f"{top['Commodity']} is the largest component of primary agriculture, accounting for "
                    f"{top['Share']:.1f}% of sector output ({_fmt(top['Output'])}), followed by "
                    f"{second['Commodity']} at {second['Share']:.1f}% ({_fmt(second['Output'])}). "
                    f"Together, these two commodity groups account for "
                    f"{top['Share'] + second['Share']:.0f}% of primary agricultural output.")
                if top["Jobs"] > 0:
                    _add_body_text(doc,
                        f"{top['Commodity']} supports {top['Jobs']:,.0f} jobs, while "
                        f"{second['Commodity']} supports {second['Jobs']:,.0f} jobs.")

        # ── 5.2 FOOD MANUFACTURING IN CONTEXT ──
        _has_food_mfg = any(
            str(c).replace("BS", "").replace("GS", "").startswith("311") or
            str(c).replace("BS", "").replace("GS", "").startswith("312")
            for c in (basket_codes or [])
        )
        if _has_food_mfg:
            try:
                gs = "within_province" if "within" in prov_scope_label.lower() else "all_provinces"
                mfg_comp_df = _compute_manufacturing_comparison(geo, year, scope_label, gs)
                if not mfg_comp_df.empty and len(mfg_comp_df) >= 2:
                    _add_styled_heading(doc, f"{next_sec_num}.2  Food & Beverage Manufacturing in Context", level=2)
                    _add_body_text(doc,
                        f"To place the food and beverage manufacturing sector in context, the following "
                        f"comparison measures its economic contribution against other major manufacturing "
                        f"sectors in {geo}. All sectors are evaluated using the same Statistics Canada IO "
                        f"multipliers and historical output data for {year}, ensuring a consistent and "
                        f"defensible comparison.")

                    # GDP comparison chart
                    gdp_chart = _render_mfg_comparison_chart(mfg_comp_df, "GDP")
                    if gdp_chart.getbuffer().nbytes > 0:
                        doc.add_picture(gdp_chart, width=Inches(5.5))
                        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                    doc.add_paragraph("")

                    # Jobs comparison chart
                    jobs_chart = _render_mfg_comparison_chart(mfg_comp_df, "Jobs")
                    if jobs_chart.getbuffer().nbytes > 0:
                        doc.add_picture(jobs_chart, width=Inches(5.5))
                        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                    doc.add_paragraph("")

                    # Comparison table
                    mt = doc.add_table(rows=1 + len(mfg_comp_df), cols=4)
                    for i, h in enumerate(["Manufacturing Sector", "GDP Contribution", "Jobs Supported", "Output"]):
                        mt.rows[0].cells[i].text = h
                    for ri, (_, row) in enumerate(mfg_comp_df.iterrows()):
                        mt.rows[ri+1].cells[0].text = str(row["Sector"])
                        mt.rows[ri+1].cells[1].text = _fmt_full(row["GDP"])
                        mt.rows[ri+1].cells[2].text = f"{row['Jobs']:,.0f}"
                        mt.rows[ri+1].cells[3].text = _fmt_full(row["Output"])
                        for ci in range(1, 4):
                            for p in mt.rows[ri+1].cells[ci].paragraphs:
                                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    _style_tufte_table(mt)
                    doc.add_paragraph("")

                    # Narrative
                    fb_row = mfg_comp_df[mfg_comp_df["Sector"] == "Food & Beverage"]
                    if not fb_row.empty:
                        fb = fb_row.iloc[0]
                        rank_gdp = list(mfg_comp_df["Sector"]).index("Food & Beverage") + 1
                        total_mfg_gdp = mfg_comp_df["GDP"].sum()
                        fb_share = (fb["GDP"] / total_mfg_gdp * 100) if total_mfg_gdp > 0 else 0
                        rank_suffix = {1: "st", 2: "nd", 3: "rd"}.get(rank_gdp, "th")
                        _add_body_text(doc,
                            f"Food and beverage manufacturing ranks {rank_gdp}{rank_suffix} among "
                            f"major manufacturing sectors in {geo} by GDP contribution, generating "
                            f"{_fmt(fb['GDP'])} in value added and supporting {fb['Jobs']:,.0f} jobs. "
                            f"This represents {fb_share:.1f}% of the total GDP generated across the "
                            f"{len(mfg_comp_df)} manufacturing sectors analyzed.")
                        # Find the top sector for comparison
                        top_mfg = mfg_comp_df.iloc[0]
                        if top_mfg["Sector"] != "Food & Beverage":
                            _add_body_text(doc,
                                f"While {top_mfg['Sector']} leads in GDP contribution "
                                f"({_fmt(top_mfg['GDP'])}), food and beverage manufacturing "
                                f"is a critical anchor of the manufacturing base due to its "
                                f"steady demand profile and deep linkages to primary agriculture.")
            except Exception:
                pass  # Silently skip if manufacturing comparison fails

            # ── F&B Manufacturing Internal NAICS Breakdown (Comment 19) ──
            try:
                fb_internal_df = _compute_fb_mfg_breakdown(res_df)
                if not fb_internal_df.empty and len(fb_internal_df) >= 2:
                    _add_styled_heading(doc, "Food & Beverage Manufacturing: Internal Diversification", level=3)
                    _add_body_text(doc,
                        "The food and beverage manufacturing sector itself is highly diversified, encompassing "
                        "a range of NAICS sub-industries from meat processing and dairy production to bakeries, "
                        "beverages, and specialty food products. The following charts and table detail the GDP "
                        "contribution and employment of each sub-industry within the sector.")

                    # GDP by sub-industry chart
                    fb_gdp_chart = _render_fb_mfg_breakdown_chart(fb_internal_df, "GDP")
                    if fb_gdp_chart.getbuffer().nbytes > 0:
                        doc.add_picture(fb_gdp_chart, width=Inches(5.5))
                        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                    doc.add_paragraph("")

                    # Jobs by sub-industry chart
                    fb_jobs_chart = _render_fb_mfg_breakdown_chart(fb_internal_df, "Jobs")
                    if fb_jobs_chart.getbuffer().nbytes > 0:
                        doc.add_picture(fb_jobs_chart, width=Inches(5.5))
                        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                    doc.add_paragraph("")

                    # Detail table
                    fbt = doc.add_table(rows=1 + len(fb_internal_df), cols=5)
                    for i, h in enumerate(["Sub-Industry", "Output", "GDP", "Jobs", "GDP Share"]):
                        fbt.rows[0].cells[i].text = h
                    for ri, (_, row) in enumerate(fb_internal_df.iterrows()):
                        fbt.rows[ri+1].cells[0].text = str(row["Sub-Industry"])
                        fbt.rows[ri+1].cells[1].text = _fmt_full(row["Output"])
                        fbt.rows[ri+1].cells[2].text = _fmt_full(row["GDP"])
                        fbt.rows[ri+1].cells[3].text = f"{row['Jobs']:,.0f}"
                        fbt.rows[ri+1].cells[4].text = f"{row['GDP_Share']:.1f}%"
                        for ci in range(1, 5):
                            for p in fbt.rows[ri+1].cells[ci].paragraphs:
                                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    _style_tufte_table(fbt)
                    doc.add_paragraph("")

                    # Narrative highlights
                    fb_top = fb_internal_df.iloc[0]
                    fb_second = fb_internal_df.iloc[1]
                    total_fb_jobs = fb_internal_df["Jobs"].sum()
                    _add_body_text(doc,
                        f"{fb_top['Sub-Industry']} is the largest sub-industry by GDP contribution, "
                        f"generating {_fmt(fb_top['GDP'])} ({fb_top['GDP_Share']:.1f}% of sector GDP) "
                        f"and supporting {fb_top['Jobs']:,.0f} jobs. {fb_second['Sub-Industry']} follows "
                        f"with {_fmt(fb_second['GDP'])} in GDP and {fb_second['Jobs']:,.0f} jobs. "
                        f"Together, the {len(fb_internal_df)} sub-industries support a combined "
                        f"{total_fb_jobs:,.0f} manufacturing jobs across {geo}.")
            except Exception:
                pass

        # ── 5.3 DOWNSTREAM: WHOLESALE, RETAIL & FOODSERVICE ──
        if "food system" in (basket_name or "").lower():
            _add_styled_heading(doc, f"{next_sec_num}.3  Wholesale, Retail & Foodservice", level=2)
            _add_body_text(doc,
                "While primary agriculture and food manufacturing represent the upstream components of the food system, "
                "the wholesale, retail, and foodservice sectors form the critical downstream link that delivers food "
                "products to consumers. Together, these downstream sectors are among the largest private-sector employers "
                "in the province and represent the final economic transactions that underpin demand for all upstream "
                "agricultural and manufacturing activity.")

            # Describe what each sector includes
            for name, desc in [
                ("Food Stores", "Grocery chains (e.g., Loblaw, Metro, Sobeys), specialty food retailers, "
                 "convenience stores, and independent grocers that sell food directly to consumers."),
                ("Food & Beverage Wholesalers", "Distributors that purchase food and beverages from manufacturers "
                 "and sell to retailers, restaurants, and institutions — managing the complex logistics of "
                 "cold chain distribution, warehousing, and delivery."),
                ("Farm Product Wholesalers", "Intermediaries that purchase raw agricultural commodities from "
                 "farms and sell to processors, exporters, and other buyers — including grain elevators, "
                 "livestock auction markets, and produce brokers."),
                ("Foodservice", "Full-service and limited-service restaurants, caterers, drinking places, "
                 "institutional cafeterias (hospitals, schools, prisons), and contract food service operators."),
            ]:
                p = doc.add_paragraph()
                r = p.add_run(f"{name}: "); r.font.bold = True; r.font.size = Pt(10.5)
                r.font.name = "Calibri"; r.font.color.rgb = _NAVY
                r = p.add_run(desc); r.font.size = Pt(10.5); r.font.name = "Calibri"; r.font.color.rgb = _DARK_GREY
                p.paragraph_format.space_after = Pt(4)

            # Data-backed breakdown from res_df
            downstream_df = _compute_downstream_breakdown(res_df)
            if not downstream_df.empty:
                doc.add_paragraph("")

                # GDP chart
                ds_gdp_chart = _render_downstream_chart(downstream_df, "GDP")
                if ds_gdp_chart.getbuffer().nbytes > 0:
                    doc.add_picture(ds_gdp_chart, width=Inches(5.5))
                    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                doc.add_paragraph("")

                # Jobs chart
                ds_jobs_chart = _render_downstream_chart(downstream_df, "Jobs")
                if ds_jobs_chart.getbuffer().nbytes > 0:
                    doc.add_picture(ds_jobs_chart, width=Inches(5.5))
                    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                doc.add_paragraph("")

                # Summary table
                ds_table = doc.add_table(rows=1 + len(downstream_df), cols=4)
                for i, h in enumerate(["Sector", "GDP Contribution", "Jobs Supported", "Output"]):
                    ds_table.rows[0].cells[i].text = h
                for ri, (_, row) in enumerate(downstream_df.iterrows()):
                    ds_table.rows[ri+1].cells[0].text = str(row["Sector"])
                    ds_table.rows[ri+1].cells[1].text = _fmt_full(row["GDP"])
                    ds_table.rows[ri+1].cells[2].text = f"{row['Jobs']:,.0f}"
                    ds_table.rows[ri+1].cells[3].text = _fmt_full(row["Output"])
                    for ci in range(1, 4):
                        for p in ds_table.rows[ri+1].cells[ci].paragraphs:
                            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                _style_tufte_table(ds_table)
                doc.add_paragraph("")

                # Narrative
                total_ds_gdp = downstream_df["GDP"].sum()
                total_ds_jobs = downstream_df["Jobs"].sum()
                if total_gdp > 0 and total_ds_gdp > 0:
                    ds_share = total_ds_gdp / total_gdp * 100
                    _add_body_text(doc,
                        f"The downstream wholesale, retail, and foodservice sectors collectively contribute "
                        f"{_fmt(total_ds_gdp)} in GDP and support {total_ds_jobs:,.0f} jobs, representing "
                        f"{ds_share:.0f}% of the total food system GDP. These sectors are critical for "
                        f"translating upstream agricultural production into accessible consumer products "
                        f"and services.")
            else:
                _add_body_text(doc,
                    "While detailed IO multiplier data for some downstream sectors may be aggregated "
                    "at broader NAICS levels, it is important to recognise that food retail and foodservice "
                    "are among the largest private-sector employers in the province.")
            doc.add_paragraph("")

        # ── 5.3 TRANSPORT & MACHINERY AG-SHARE CONTRIBUTIONS ──
        _has_transport_codes = any(
            k in (basket_config.get("components", []))
            for k in ["agri_transport_rail", "agri_transport_truck", "agri_inputs_machinery"]
        )
        if _has_transport_codes:
            transport_df = _compute_transport_impacts(res_df)
            if not transport_df.empty:
                _add_styled_heading(doc, f"{next_sec_num}.4  Transportation & Machinery: Agricultural Share Contributions", level=2)
                _add_body_text(doc,
                    f"The {basket_name} sector extends beyond the traditional AAFC food system "
                    f"definition by including the agricultural share of three critical support "
                    f"industries. Rather than attributing 100% of these industries to the agri-food "
                    f"sector, this analysis applies empirically derived Ag-Intensity Coefficients "
                    f"to isolate only the portion of each industry's economic activity that is "
                    f"directly driven by the production, processing, and distribution of "
                    f"agricultural goods.")

                # Transport impact chart
                tc = _render_transport_impact_chart(transport_df)
                if tc.getbuffer().nbytes > 0:
                    doc.add_picture(tc, width=Inches(5.5))
                    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                doc.add_paragraph("")

                # Impact summary table
                tt = doc.add_table(rows=1 + len(transport_df), cols=6)
                for i, h in enumerate(["Industry", "NAICS", "Ag-Share",
                                        "Output (Ag-Share)", "GDP (Ag-Share)", "Jobs (Ag-Share)"]):
                    tt.rows[0].cells[i].text = h
                for ri, (_, row) in enumerate(transport_df.iterrows()):
                    tt.rows[ri+1].cells[0].text = str(row["Industry"])
                    tt.rows[ri+1].cells[1].text = str(row["NAICS"])
                    tt.rows[ri+1].cells[2].text = str(row["Ag-Share"])
                    tt.rows[ri+1].cells[3].text = _fmt_full(row["Output"])
                    tt.rows[ri+1].cells[4].text = _fmt_full(row["GDP"])
                    tt.rows[ri+1].cells[5].text = f"{row['Jobs']:,.0f}"
                    for ci in range(3, 6):
                        for p in tt.rows[ri+1].cells[ci].paragraphs:
                            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                _style_tufte_table(tt)
                doc.add_paragraph("")

                # Totals
                total_t_output = transport_df["Output"].sum()
                total_t_gdp = transport_df["GDP"].sum()
                total_t_jobs = transport_df["Jobs"].sum()
                total_t_li = transport_df["Labour Income"].sum()

                _add_body_text(doc,
                    f"Together, the agricultural share of these three support industries "
                    f"contributes {_fmt(total_t_output)} in output, {_fmt(total_t_gdp)} in GDP, "
                    f"and supports {total_t_jobs:,.0f} jobs across {geo}. This represents the "
                    f"economic activity within the transportation and machinery sectors that would "
                    f"not exist without the agricultural sector's demand for freight, logistics, "
                    f"and equipment.")

                if total_output > 0 and total_t_output > 0:
                    t_share = total_t_output / total_output * 100
                    _add_body_text(doc,
                        f"The transport and machinery components account for {t_share:.1f}% of the "
                        f"total {basket_name} sector output. The remaining {100-t_share:.0f}% is "
                        f"attributed to the core AAFC food system segments (primary agriculture, "
                        f"food manufacturing, wholesale/retail, and foodservice).")

                # Per-industry methodology detail
                _add_styled_heading(doc, "Methodology: Ag-Intensity Coefficients", level=3)
                _add_body_text(doc,
                    "Each coefficient represents the share of the industry's total economic "
                    "activity that is directly attributable to agricultural demand. These were "
                    "derived from a comprehensive sector-impact analysis covering the 2021-2024 "
                    "period, using Statistics Canada data, carrier financial reports, and "
                    "industry benchmarks. The coefficients are applied as multipliers on each "
                    "industry's total output before computing impacts through the IO model.")

                for label, naics, ag_share, _ in _TRANSPORT_INDUSTRY_MAP:
                    p = doc.add_paragraph()
                    r = p.add_run(f"{label} (NAICS {naics}) - {ag_share*100:.1f}% Ag-Share: ")
                    r.font.bold = True; r.font.size = Pt(10); r.font.name = "Calibri"
                    r.font.color.rgb = _NAVY
                    if naics == "482":
                        detail = (
                            "Derived from grain and fertilizer freight revenue as a share of "
                            "total rail freight revenue (CN and CPKC annual reports, 2023). "
                            "Grain alone accounts for 19-20% of top-line freight revenue; adding "
                            "fertilizers (potash) and processed food intermodal brings the total "
                            "to 33.4%. The coefficient is corroborated by tonnage analysis "
                            "(agricultural commodities represent 20-22% of physical freight) and "
                            "Maximum Revenue Entitlement (MRE) data showing $2.1B in regulated "
                            "grain revenue. Range: 30-36% depending on crop year."
                        )
                    elif naics == "484":
                        detail = (
                            "Calculated using a weighted average of transborder trade intensity "
                            "(17% of total truck trade value is agricultural) and domestic food "
                            "distribution activity (28% intensity, driven by the food and beverage "
                            "sector being Canada's largest manufacturing sector by shipments). "
                            "Weighting assumes a 40/60 split between international and domestic "
                            "trucking activity. Range: 22-28%."
                        )
                    else:  # 3331
                        detail = (
                            "Based on Agricultural Implement Manufacturing (NAICS 33311) shipments "
                            "of $6.5 billion as a share of total NAICS 3331 shipments of $13.9 billion, "
                            "per Statistics Canada manufacturing data for 2023. Agricultural implements "
                            "dominate over Construction Machinery ($3.3B, 23.7%) and Mining/Oil & Gas "
                            "Machinery ($4.1B, 29.5%). Range: 44-49%."
                        )
                    r = p.add_run(detail)
                    r.font.size = Pt(9.5); r.font.name = "Calibri"; r.font.color.rgb = _DARK_GREY
                    p.paragraph_format.space_after = Pt(6)

                # Assumptions
                _add_styled_heading(doc, "Key Assumptions", level=3)
                for assumption in [
                    "Ag-Intensity Coefficients are applied as static multipliers on industry output. "
                    "In reality, the agricultural share fluctuates with crop yields, commodity prices, "
                    "and trade patterns (e.g., drought years depress rail intensity to ~28%).",
                    "The analysis is scope-locked to Direct impacts to prevent double-counting. "
                    "Since the basket already spans agriculture, manufacturing, transport, and "
                    "wholesale, using indirect or induced scope would count inter-sector "
                    "transactions multiple times.",
                    "Coefficients are based on 2023 reference data. Structural shifts in "
                    "transportation patterns (e.g., modal shift from rail to truck) or machinery "
                    "demand cycles may cause the actual ag-share to deviate.",
                ]:
                    p = doc.add_paragraph(assumption, style="List Bullet")
                    for r in p.runs:
                        r.font.size = Pt(9); r.font.name = "Calibri"
                        r.font.color.rgb = _MID_GREY
                doc.add_paragraph("")

    # ══ KEY FINDINGS SUMMARY ══
    imp = next_sec_num + (1 if is_basket else 0)
    _add_styled_heading(doc, f"{imp}. Key Findings Summary", level=1)
    pts = _build_talking_points(geo, basket_name, year, total_output, total_gdp,
                                jobs, avg_wage, leak_pct, scope_label, fiscal, income)
    _add_body_text(doc,
        f"The following points summarize the headline findings from this {year} "
        f"economic impact analysis of the {basket_name} sector in {geo}:")
    for pt in pts:
        p = doc.add_paragraph(pt, style="List Bullet")
        for r in p.runs:
            r.font.size = Pt(10.5); r.font.name = "Calibri"; r.font.color.rgb = _DARK_GREY
    doc.add_paragraph("")

    # ══ APPENDIX A: RAW MULTIPLIERS ══
    if raw_mult_df is not None and not raw_mult_df.empty:
        doc.add_page_break()
        _add_styled_heading(doc, "Appendix A: Raw Multiplier Values", level=1)
        _add_body_text(doc, "The actual Statistics Canada multiplier coefficients used in this analysis:")
        # Bug 6: Map to correct columns — find the numeric value column
        possible_val_cols = ["value", "VALUE", "Value", "multiplier_value"]
        val_col = None
        for vc in possible_val_cols:
            if vc in raw_mult_df.columns:
                # Verify it contains numbers, not strings like "Direct multiplier"
                sample = raw_mult_df[vc].dropna().head(5)
                if len(sample) > 0 and pd.api.types.is_numeric_dtype(sample):
                    val_col = vc
                    break
        # If no numeric value column found, try to find any numeric column
        if val_col is None:
            for col_name in raw_mult_df.columns:
                if pd.api.types.is_numeric_dtype(raw_mult_df[col_name]) and col_name not in ["YEAR", "Year"]:
                    sample = raw_mult_df[col_name].dropna()
                    if len(sample) > 0 and sample.mean() < 100:  # multipliers are typically < 10
                        val_col = col_name
                        break
        display_cols = []
        for candidate in ["join_code", "industry_name", "variable", "multiplier_type"]:
            if candidate in raw_mult_df.columns:
                display_cols.append(candidate)
        if val_col and val_col not in display_cols:
            display_cols.append(val_col)
        if len(display_cols) >= 2:
            disp = raw_mult_df[display_cols].drop_duplicates().head(40)
            hdrs = []
            for dc in display_cols:
                if dc == "join_code": hdrs.append("NAICS")
                elif dc == "industry_name": hdrs.append("Industry")
                elif dc == "variable": hdrs.append("Metric")
                elif dc == "multiplier_type": hdrs.append("Type")
                elif dc == val_col: hdrs.append("Value")
                else: hdrs.append(dc)
            tbl = doc.add_table(rows=1+len(disp), cols=len(hdrs))
            for i, h in enumerate(hdrs): tbl.rows[0].cells[i].text = h
            for ri, (_, row) in enumerate(disp.iterrows()):
                for ci, dc in enumerate(display_cols):
                    cell_val = row[dc]
                    if dc == val_col and pd.notna(cell_val):
                        tbl.rows[ri+1].cells[ci].text = f"{float(cell_val):.4f}"
                    else:
                        tbl.rows[ri+1].cells[ci].text = str(cell_val) if pd.notna(cell_val) else ""
            _style_tufte_table(tbl)
    doc.add_page_break()

    # ══ APPENDIX B: METHODOLOGY & LIMITATIONS ══
    _add_styled_heading(doc, "Appendix B: Methodology & Limitations", level=1)
    _add_styled_heading(doc, "The Input-Output Framework", level=2)
    _add_body_text(doc,
        "Input-Output analysis, pioneered by Nobel laureate Wassily Leontief, models "
        "the economy as interconnected industries. The IO multipliers quantify the total "
        "economic effect of a one-dollar change in final demand for a specific industry.")
    _add_styled_heading(doc, "Key Definitions", level=2)
    for term, defn in [
        ("Output", "The total value of goods and services produced, also referred to as "
         "business revenue. This includes both the cost of intermediate inputs purchased from "
         "other industries and the value added by the sector's own production activities."),
        ("GDP at Basic Prices", "The value added by the sector after subtracting the cost of "
         "intermediate inputs and adjusting for indirect taxes and subsidies. This isolates the "
         "sector's true economic contribution, free from external distortions such as fluctuating "
         "input costs or fiscal policy changes."),
        ("Labour Income", "Total earnings received by employees, including wages, salaries, and "
         "employer social contributions (such as CPP and EI premiums). Also includes the labour "
         "income of unincorporated businesses (self-employed individuals)."),
        ("Jobs", "Total employment supported by sector output, including all positions sustained "
         "through direct, indirect, and induced effects."),
        ("Direct Impact", "Economic activity occurring within the industry itself -- the immediate "
         "production, employment, and income generated by sector operations."),
        ("Indirect Impact", "Activity generated in upstream supply chain industries when the sector "
         "purchases inputs such as feed, fuel, equipment, and professional services."),
        ("Induced Impact", "Additional economic activity stimulated when workers in direct and "
         "indirect industries spend their earnings in the local economy on housing, groceries, "
         "services, and other consumer goods."),
        ("Taxes on Products", "Taxes on goods and services collected at various stages of production "
         "and distribution, including GST/HST, excise taxes, and customs duties."),
        ("Taxes on Production", "Levies on the assets and activities involved in production, including "
         "property taxes, business licences, and production-related fees."),
        ("Subsidies on Products", "Government payments made per unit of a good or service produced "
         "or imported. These directly reduce the purchaser's price, including crop insurance "
         "payments, price stabilization, and supply management programs."),
        ("Subsidies on Production", "Government payments received by enterprises for engaging in "
         "production, not tied to specific product quantities. Includes environmental stewardship "
         "programs, disaster recovery assistance, and agricultural partnership programs."),
        ("Fiscal ROI", "The ratio of total tax revenue generated by the sector to government subsidies "
         "received. A ratio greater than 1.0 indicates the sector is a net contributor to public finances.")]:
        p = doc.add_paragraph()
        r = p.add_run(f"{term}: "); r.font.bold = True; r.font.size = Pt(10); r.font.name = "Calibri"; r.font.color.rgb = _NAVY
        r = p.add_run(defn); r.font.size = Pt(10); r.font.name = "Calibri"; r.font.color.rgb = _DARK_GREY
        p.paragraph_format.space_after = Pt(3)
    _add_styled_heading(doc, "Limitations of the Static IO Model", level=2)
    for lim in [
        "Fixed Proportions: IO multipliers assume constant input-output ratios regardless of scale.",
        "No Supply Constraints: All industries can expand without bottlenecks or capacity limits.",
        "No Price Effects: Demand changes do not affect prices in the IO framework.",
        "Static Snapshot: Multipliers reflect a single reference year's economic structure.",
        "No Substitution: Industries cannot substitute between inputs."]:
        p = doc.add_paragraph(lim, style="List Bullet")
        for r in p.runs: r.font.size = Pt(9.5); r.font.name = "Calibri"; r.font.color.rgb = _MID_GREY
    doc.add_paragraph("")
    _add_body_text(doc,
        f"- Multipliers: Statistics Canada Table {'36-10-0594' if geo=='Canada' else '36-10-0595'}\n"
        f"- Historical output: Table 36-10-0402\n"
        f"- Report generated {date.today().strftime('%B %d, %Y')} by the Agri-Food Economic Dashboard")

    # ══ APPENDIX C: TRANSPORTATION & MACHINERY INCLUSION ══
    _is_composite = basket_config.get("weight_type") == "composite"
    _has_transport = any(
        k in (basket_config.get("components", []))
        for k in ["agri_transport_rail", "agri_transport_truck", "agri_inputs_machinery"]
    )
    if _is_composite and _has_transport:
        doc.add_page_break()
        _add_styled_heading(doc, "Appendix C: Transportation & Machinery Industry Inclusion", level=1)
        _add_body_text(doc,
            f"The {basket_name} sector extends beyond the traditional AAFC food system definition "
            f"by including the agricultural share of three support industries: Rail Transportation, "
            f"Truck Transportation, and Agricultural Machinery Manufacturing. These industries are "
            f"not entirely agricultural, but a substantial and defensible share of their economic "
            f"activity is directly attributable to the production, processing, and distribution of "
            f"agricultural goods.")
        _add_body_text(doc,
            "Rather than including 100% of these sectors (which would overstate agriculture's "
            "footprint), this analysis applies Ag-Intensity Coefficients to isolate only the "
            "agricultural share of each industry's economic activity. These coefficients were "
            "derived from a comprehensive sector-impact analysis using Statistics Canada data, "
            "carrier financial reports, and industry benchmarks.")

        # Ag-Share table
        _add_styled_heading(doc, "Agricultural Intensity Coefficients", level=2)
        at = doc.add_table(rows=4, cols=4)
        for i, h in enumerate(["Industry", "NAICS Code", "Ag-Share (%)", "Primary Methodology"]):
            at.rows[0].cells[i].text = h
        _ag_rows = [
            ("Rail Transportation", "482", "33.4%",
             "Grain & fertilizer freight revenue share (CN, CPKC annual reports) "
             "combined with regulated grain tonnage data (Maximum Revenue Entitlement). "
             "Range: 30-36% depending on crop year."),
            ("Truck Transportation", "484", "24.5%",
             "Transborder agricultural trade value share (17%) weighted with domestic "
             "food processing freight activity (28%). Food & beverage processing is "
             "Canada's largest manufacturing sector by shipments. Range: 22-28%."),
            ("Machinery Manufacturing", "3331", "46.8%",
             "Agricultural implement manufacturing shipments ($6.5B) as share of total "
             "NAICS 3331 shipments ($13.9B), per Statistics Canada manufacturing data. "
             "Range: 44-49%."),
        ]
        for ri, (name, code, share, method) in enumerate(_ag_rows):
            at.rows[ri+1].cells[0].text = name
            at.rows[ri+1].cells[1].text = code
            at.rows[ri+1].cells[2].text = share
            at.rows[ri+1].cells[3].text = method
            for p in at.rows[ri+1].cells[3].paragraphs:
                for r in p.runs:
                    r.font.size = Pt(8.5)
        _style_tufte_table(at)
        doc.add_paragraph("")

        _add_styled_heading(doc, "Scope Lock: Preventing Double-Counting", level=2)
        _add_body_text(doc,
            "When the Entire Food System basket is selected, the analysis is scope-locked "
            "to Direct impacts only. This is a deliberate methodological choice: because "
            "the basket already spans multiple sectors (agriculture, manufacturing, transport, "
            "wholesale, foodservice), including indirect or induced effects would count "
            "the same inter-sector transactions multiple times. The Direct scope provides "
            "a conservative, defensible estimate of the full food system's economic footprint.")

        _add_styled_heading(doc, "Data Sources for Coefficients", level=2)
        for src in [
            "CN Rail 2023 Annual Report - Grain & Fertilizer revenue segment (19% of freight revenue)",
            "CPKC 2023 Annual Report - Grain revenue (20% of freight), Bulk segment (35%)",
            "Statistics Canada Railway Carloadings (Table 23-10-0063): Wheat +30.2%, Canola +22.1% in 2023",
            "Maximum Revenue Entitlement (2023-2024 crop year): CN $1.21B, CPKC $872M regulated grain",
            "Statistics Canada Manufacturing Shipments: NAICS 33311 ($6.5B), 33312 ($3.3B), 33313 ($4.1B)",
            "Transport Canada Annual Report 2023: trucking = 52.2% of import trade value",
            "AAFC Market Overview: $59.5B in agri-food exports to the U.S. (2023)",
        ]:
            p = doc.add_paragraph(src, style="List Bullet")
            for r in p.runs:
                r.font.size = Pt(8.5); r.font.name = "Calibri"; r.font.color.rgb = _MID_GREY

    buf = io.BytesIO(); doc.save(buf); buf.seek(0); return buf

# ─────────────────────────────────────────────────────────────────────────────
# 2. SLIDE DECK (PowerPoint — native charts, action titles, speaker notes)
# ─────────────────────────────────────────────────────────────────────────────

def _add_slide(prs, layout_idx=6):
    """Add a blank slide."""
    return prs.slides.add_slide(prs.slide_layouts[layout_idx])


def _add_text_box(slide, left, top, width, height, text, font_size=14,
                  bold=False, color=None, alignment=PP_ALIGN.LEFT):
    """Add a text box to a slide."""
    txBox = slide.shapes.add_textbox(PptInches(left), PptInches(top),
                                      PptInches(width), PptInches(height))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = PptPt(font_size)
    p.font.bold = bold
    p.alignment = alignment
    if color:
        p.font.color.rgb = PptRGB(*color)
    return tf


def _add_speaker_notes(slide, notes_text):
    """Add speaker notes to a slide."""
    notes_slide = slide.notes_slide
    notes_slide.notes_text_frame.text = notes_text


def _add_native_stacked_bar(slide, categories, series_data, left, top, width, height):
    """Add a native editable stacked bar chart."""
    chart_data = CategoryChartData()
    chart_data.categories = categories
    for name, values in series_data:
        chart_data.add_series(name, values)
    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_STACKED, PptInches(left), PptInches(top),
        PptInches(width), PptInches(height), chart_data
    ).chart
    # Style
    chart.has_legend = True
    chart.legend.include_in_layout = False
    chart.legend.position = 2  # Bottom
    plot = chart.plots[0]
    plot.gap_width = 80
    # Color the series
    colors = [PptRGB(0x0d,0x94,0x88), PptRGB(0xf5,0x9e,0x0b), PptRGB(0xef,0x44,0x44)]
    for i, series in enumerate(plot.series):
        if i < len(colors):
            series.format.fill.solid()
            series.format.fill.fore_color.rgb = colors[i]
    return chart


def _add_native_bar(slide, categories, values, colors_list, left, top, width, height):
    """Add a native editable clustered bar chart."""
    chart_data = CategoryChartData()
    chart_data.categories = categories
    chart_data.add_series("Value", values)
    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.BAR_CLUSTERED, PptInches(left), PptInches(top),
        PptInches(width), PptInches(height), chart_data
    ).chart
    chart.has_legend = False
    plot = chart.plots[0]
    plot.gap_width = 100
    series = plot.series[0]
    for i, color in enumerate(colors_list):
        pt = series.points[i]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = color
    return chart


def generate_slide_deck(
    geo: str, basket_name: str, year: int, scope_label: str,
    prov_scope_label: str,
    sum_df: pd.DataFrame, bd_df: pd.DataFrame, res_df: pd.DataFrame,
    jobs: float = 0, avg_wage: float = 0,
    get_sector_label_fn=None,
    shock_source: str = "Historical StatCan Output",
) -> io.BytesIO:
    """Generate a PowerPoint slide deck with native charts and action titles."""
    basket_name = _strip_emojis(basket_name)
    prs = Presentation()
    prs.slide_width = PptInches(13.333)
    prs.slide_height = PptInches(7.5)

    total_output = _get_metric(sum_df, "Output")
    total_gdp = _get_metric(sum_df, "Gross domestic")
    imports_val = _get_metric(sum_df, "International imports")
    exports_val = _get_metric(sum_df, "International exports")
    leak_pct = (imports_val / total_output * 100) if total_output > 0 else 0
    fiscal = _compute_fiscal(sum_df)
    income = _compute_income_distribution(sum_df)

    # Bug 1: Filter breakdown data by scope
    bd_df = _filter_bd_by_scope(bd_df, scope_label)

    # ── SLIDE 1: TITLE ──
    slide = _add_slide(prs)
    shape = slide.shapes.add_shape(1, PptInches(0), PptInches(0), prs.slide_width, prs.slide_height)
    shape.fill.solid(); shape.fill.fore_color.rgb = PptRGB(0x1B, 0x2A, 0x4A)
    shape.line.fill.background()
    _add_text_box(slide, 1, 1.5, 11, 1.5, "Economic Impact Assessment",
                  font_size=36, bold=True, color=(0xFF,0xFF,0xFF), alignment=PP_ALIGN.CENTER)
    _add_text_box(slide, 1, 3.2, 11, 1, f"{basket_name}  -  {geo}  -  {year}",
                  font_size=20, color=(0x05,0x96,0x69), alignment=PP_ALIGN.CENTER)
    _add_text_box(slide, 1, 4.5, 11, 0.8,
                  f"Scope: {scope_label}  |  {prov_scope_label}  |  {shock_source}",
                  font_size=12, color=(0xAA,0xAA,0xAA), alignment=PP_ALIGN.CENTER)
    _add_text_box(slide, 1, 6, 11, 0.5,
                  f"Data Source: Statistics Canada IO Tables  |  {date.today().strftime('%B %Y')}",
                  font_size=10, color=(0x88,0x88,0x88), alignment=PP_ALIGN.CENTER)

    # ── SLIDE 2: KEY METRICS (Action Title) ──
    slide = _add_slide(prs)
    action_title = _build_action_title(
        "{geo}'s {sector} Sector Anchors {jobs:,.0f} Jobs and {gdp} in GDP",
        geo=geo, sector=basket_name, jobs=jobs, gdp=_fmt(total_gdp))
    _add_text_box(slide, 0.5, 0.3, 12, 1, action_title,
                  font_size=22, bold=True, color=(0x1B,0x2A,0x4A))

    kpis = [("Total Output", _fmt(total_output)),
            ("GDP Contribution", _fmt(total_gdp)),
            ("Jobs Supported", f"{jobs:,.0f}"),
            ("Average Wage", _fmt(avg_wage))]
    for i, (label, value) in enumerate(kpis):
        left = 0.8 + (i * 3.1)
        box = slide.shapes.add_shape(1, PptInches(left), PptInches(1.8), PptInches(2.8), PptInches(2))
        box.fill.solid(); box.fill.fore_color.rgb = PptRGB(0xF0,0xF7,0xF4)
        box.line.color.rgb = PptRGB(0xD1,0xE7,0xDD)
        _add_text_box(slide, left+0.2, 2.0, 2.4, 0.5, label,
                      font_size=11, bold=True, color=(0x66,0x66,0x66))
        _add_text_box(slide, left+0.2, 2.5, 2.4, 1, value,
                      font_size=26, bold=True, color=(0x05,0x96,0x69))

    # Tax Revenue callout
    if fiscal["total_tax"] > 0:
        _add_text_box(slide, 0.8, 4.3, 11, 1,
                      f"\U0001f4b0 Tax Revenue: The sector generates {_fmt(fiscal['total_tax'])} in government tax revenue.",
                      font_size=14, bold=True, color=(0x7c,0x3a,0xed))

    _add_text_box(slide, 0.8, 5.5, 11, 0.8,
                  f"\U0001f4c9 Import Leakage: {leak_pct:.1f}%  |  Domestic Retention: {100-leak_pct:.0f}%",
                  font_size=12, color=(0x66,0x66,0x66))

    _add_speaker_notes(slide, "\n".join(_build_talking_points(
        geo, basket_name, year, total_output, total_gdp, jobs, avg_wage,
        leak_pct, scope_label, fiscal, income)))

    # ── SLIDE 3: VALUE RETENTION (Native chart) ──
    slide = _add_slide(prs)
    retention_pct = (total_gdp/total_output*100) if total_output > 0 else 0
    _add_text_box(slide, 0.5, 0.3, 12, 1,
                  _build_action_title("For Every $1 of Output, {pct:.0f}\u00a2 is Retained as GDP in {geo}",
                                      pct=retention_pct, geo=geo),
                  font_size=22, bold=True, color=(0x1B,0x2A,0x4A))

    cats_vr, vals_vr, cols_vr = [], [], []
    if total_gdp > 0:
        cats_vr.append("Value Added (GDP)"); vals_vr.append(total_gdp/1e6)
        cols_vr.append(PptRGB(0x05,0x96,0x69))
    if imports_val > 0:
        cats_vr.append("Import Leakage"); vals_vr.append(imports_val/1e6)
        cols_vr.append(PptRGB(0xdc,0x26,0x26))
    if exports_val > 0:
        cats_vr.append("International Exports"); vals_vr.append(exports_val/1e6)
        cols_vr.append(PptRGB(0x25,0x63,0xeb))
    if cats_vr:
        _add_native_bar(slide, cats_vr, tuple(vals_vr), cols_vr, 1.5, 1.5, 10, 5)

    _add_speaker_notes(slide,
        f"Value Retention: {retention_pct:.0f}% of output retained as GDP.\n"
        f"Imports: {_fmt(imports_val)} ({leak_pct:.1f}% leakage)")

    # ── SLIDE 4: RIPPLE EFFECT (Native stacked bar) ──
    slide = _add_slide(prs)
    direct_out = _get_bd_metric(bd_df, "Output", "Direct")
    mult_val = total_output / direct_out if direct_out > 0 else 0
    _add_text_box(slide, 0.5, 0.3, 12, 1,
                  _build_action_title(f"Every Dollar of Farm Output Cascades ${mult:.2f} Through {geo}'s Economy",
                                      mult=mult_val, geo=geo) if mult_val > 1 else "The Ripple Effect",
                  font_size=22, bold=True, color=(0x1B,0x2A,0x4A))

    allowed = _allowed_types(scope_label)
    ripple_cats = []
    ripple_series = {t: [] for t in allowed}
    for metric_pattern, label in [("Output", "Output"), ("Gross domestic.*basic prices", "GDP")]:
        total = 0
        for t in allowed:
            v = _get_bd_metric(bd_df, metric_pattern, t)
            ripple_series[t].append(v / 1e6)
            total += v
        if total > 0:
            ripple_cats.append(label)
        else:
            for t in allowed:
                ripple_series[t].pop()
    if ripple_cats:
        series_data = [(t, tuple(ripple_series[t])) for t in allowed]
        _add_native_stacked_bar(slide, ripple_cats, series_data, 1.5, 1.5, 10, 5)

    _add_speaker_notes(slide,
        "Direct: activity within the sector.\n"
        "Indirect: supply chain spending.\n"
        "Induced: household re-spending of labour income.")

    # ── SLIDE 5: SECTOR MIX (if basket) ──
    if res_df is not None and not res_df.empty:
        slide = _add_slide(prs)
        _add_text_box(slide, 0.5, 0.3, 12, 0.8, "Sector Composition",
                      font_size=28, bold=True, color=(0x1B,0x2A,0x4A))
        cb = _render_sector_donut(res_df, get_sector_label_fn)
        if cb.getbuffer().nbytes > 0:
            slide.shapes.add_picture(cb, PptInches(3), PptInches(1.3), PptInches(7), PptInches(5.5))

    # ── SLIDE 6: KEY TAKEAWAYS ──
    slide = _add_slide(prs)
    _add_text_box(slide, 0.5, 0.3, 12, 0.8, "Key Takeaways & Policy Implications",
                  font_size=28, bold=True, color=(0x1B,0x2A,0x4A))
    pts = _build_talking_points(geo, basket_name, year, total_output, total_gdp,
                                jobs, avg_wage, leak_pct, scope_label, fiscal, income)
    for i, pt in enumerate(pts):
        _add_text_box(slide, 1, 1.5 + (i * 1.0), 11, 0.9,
                      f"-  {pt}", font_size=15, color=(0x33,0x33,0x33))

    buf = io.BytesIO(); prs.save(buf); buf.seek(0); return buf


# ─────────────────────────────────────────────────────────────────────────────
# 3. ONE-PAGER (PDF via fpdf2 — pixel-perfect, locked layout)
# ─────────────────────────────────────────────────────────────────────────────


def _sanitize_pdf(text: str) -> str:
    """Replace Unicode chars not supported by fpdf2 Helvetica."""
    replacements = {
        '\u2014': ' -- ',
        '\u2013': ' - ',
        '\u2019': "'",
        '\u2018': "'",
        '\u201c': '"',
        '\u201d': '"',
        '\u2022': '-',
        '\u2500': '-',
        '\u00a0': ' ',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode('latin-1', errors='replace').decode('latin-1')

def _set_cell_shading(cell, color_hex: str):
    """Set cell background color using proper XML."""
    shading_elm = parse_xml(
        '<w:shd {} w:fill="{}"/>'.format(nsdecls("w"), color_hex))
    cell._tc.get_or_add_tcPr().append(shading_elm)


def _set_table_borders(table, color="auto", sz="4", val="single"):
    """Set borders on entire table using proper XML."""
    tbl = table._tbl
    tblPr = tbl.tblPr
    if tblPr is None:
        tblPr = parse_xml('<w:tblPr {}/>'.format(nsdecls("w")))
        tbl.append(tblPr)
    borders_xml = (
        '<w:tblBorders {ns}>'
        '<w:top w:val="{v}" w:sz="{s}" w:color="{c}"/>'
        '<w:left w:val="{v}" w:sz="{s}" w:color="{c}"/>'
        '<w:bottom w:val="{v}" w:sz="{s}" w:color="{c}"/>'
        '<w:right w:val="{v}" w:sz="{s}" w:color="{c}"/>'
        '<w:insideH w:val="{v}" w:sz="{s}" w:color="{c}"/>'
        '<w:insideV w:val="{v}" w:sz="{s}" w:color="{c}"/>'
        '</w:tblBorders>'
    ).format(ns=nsdecls("w"), v=val, s=sz, c=color)
    tblPr.append(parse_xml(borders_xml))


def _hide_table_borders(table):
    """Remove all borders from a table."""
    _set_table_borders(table, val="none", sz="0", color="auto")


def generate_one_pager(
    geo: str, basket_name: str, year: int, scope_label: str,
    prov_scope_label: str,
    sum_df: pd.DataFrame, bd_df: pd.DataFrame,
    jobs: float = 0, avg_wage: float = 0,
    shock_source: str = "Historical StatCan Output",
) -> io.BytesIO:
    """Generate a 1-page stakeholder leave-behind (Word .docx)."""
    basket_name = _strip_emojis(basket_name)
    total_output = _get_metric(sum_df, "Output")
    total_gdp = _get_metric(sum_df, "Gross domestic")
    imports_val = _get_metric(sum_df, "International imports")
    leak_pct = (imports_val / total_output * 100) if total_output > 0 else 0
    fiscal = _compute_fiscal(sum_df)
    income = _compute_income_distribution(sum_df)

    doc = Document()

    # Page setup: Letter, narrow margins for one-page density
    for section in doc.sections:
        section.page_width = Inches(8.5)
        section.page_height = Inches(11)
        section.top_margin = Inches(0.3)
        section.bottom_margin = Inches(0.3)
        section.left_margin = Inches(0.5)
        section.right_margin = Inches(0.5)

    # ── HEADER ──
    ht = doc.add_table(rows=2, cols=1)
    ht.alignment = WD_TABLE_ALIGNMENT.CENTER
    _hide_table_borders(ht)
    for row in ht.rows:
        _set_cell_shading(row.cells[0], "1B2A4A")
    # Title
    p = ht.rows[0].cells[0].paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"Economic Impact: {basket_name}")
    r.font.size = Pt(20); r.font.bold = True
    r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF); r.font.name = "Calibri"
    p.paragraph_format.space_before = Pt(8); p.paragraph_format.space_after = Pt(0)
    # Subtitle
    p = ht.rows[1].cells[0].paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"{geo}  |  {year}  |  {scope_label}  |  {prov_scope_label}")
    r.font.size = Pt(9); r.font.color.rgb = RGBColor(0xB4, 0xC8, 0xDC)
    r.font.name = "Calibri"
    p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(6)

    doc.add_paragraph("").paragraph_format.space_after = Pt(4)

    # ── KPI BOXES ──
    kpis = [
        ("Total Output", _fmt(total_output)),
        ("GDP", _fmt(total_gdp)),
        ("Jobs", f"{jobs:,.0f}"),
        ("Avg Wage", _fmt(avg_wage)),
    ]
    if fiscal["total_tax"] > 0:
        kpis.append(("Tax Revenue", _fmt(fiscal['total_tax'])))

    kt = doc.add_table(rows=2, cols=len(kpis))
    kt.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(kt, color="D1E7DD", sz="4", val="single")
    for i, (label, value) in enumerate(kpis):
        for row_idx in range(2):
            _set_cell_shading(kt.rows[row_idx].cells[i], "F0F7F4")
        # Label
        p = kt.rows[0].cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(label)
        r.font.size = Pt(7); r.font.bold = True; r.font.name = "Calibri"
        r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        p.paragraph_format.space_before = Pt(4); p.paragraph_format.space_after = Pt(0)
        # Value
        p = kt.rows[1].cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(value)
        r.font.size = Pt(16); r.font.bold = True; r.font.name = "Calibri"
        r.font.color.rgb = RGBColor(0x05, 0x96, 0x69)
        p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(4)

    doc.add_paragraph("").paragraph_format.space_after = Pt(4)

    # ── RIPPLE EFFECT CHART ──
    bd_df = _filter_bd_by_scope(bd_df, scope_label)
    chart_buf = _render_ripple_chart(bd_df, scope_label)
    if chart_buf.getbuffer().nbytes > 0:
        doc.add_picture(chart_buf, width=Inches(5.5))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph("").paragraph_format.space_after = Pt(2)

    # ── TAX REVENUE CALLOUT ──
    if fiscal["total_tax"] > 0:
        ft = doc.add_table(rows=1, cols=1)
        ft.alignment = WD_TABLE_ALIGNMENT.CENTER
        _hide_table_borders(ft)
        _set_cell_shading(ft.rows[0].cells[0], "7C3AED")
        p = ft.rows[0].cells[0].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        tax_text = (
            f"TAX REVENUE: The sector generates "
            f"{_fmt(fiscal['total_tax'])} in government tax revenue across "
            f"all levels of government")
        r = p.add_run(tax_text)
        r.font.size = Pt(10); r.font.bold = True; r.font.name = "Calibri"
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p.paragraph_format.space_before = Pt(4); p.paragraph_format.space_after = Pt(4)

    doc.add_paragraph("").paragraph_format.space_after = Pt(2)

    # ── KEY TALKING POINTS ──
    p = doc.add_paragraph()
    r = p.add_run("Key Talking Points")
    r.font.size = Pt(11); r.font.bold = True; r.font.name = "Calibri"
    r.font.color.rgb = _NAVY
    p.paragraph_format.space_after = Pt(2)

    pts = _build_talking_points(geo, basket_name, year, total_output, total_gdp,
                                jobs, avg_wage, leak_pct, scope_label, fiscal, income)
    for pt in pts[:4]:
        p = doc.add_paragraph(pt, style="List Bullet")
        for r in p.runs:
            r.font.size = Pt(8.5); r.font.name = "Calibri"
            r.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        p.paragraph_format.space_after = Pt(1)

    doc.add_paragraph("").paragraph_format.space_after = Pt(6)

    # ── POLICY ASK BOX (editable!) ──
    pa = doc.add_table(rows=1, cols=1)
    pa.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(pa, color="C8C8C8", sz="4", val="single")
    _set_cell_shading(pa.rows[0].cells[0], "FCFCFC")
    cell = pa.rows[0].cells[0]
    p = cell.paragraphs[0]
    r = p.add_run("Our Policy Ask:  ")
    r.font.size = Pt(10); r.font.italic = True; r.font.name = "Calibri"
    r.font.color.rgb = RGBColor(0x96, 0x96, 0x96)
    r = p.add_run("[Enter your specific ask here before printing]")
    r.font.size = Pt(10); r.font.italic = True; r.font.name = "Calibri"
    r.font.color.rgb = RGBColor(0xBB, 0xBB, 0xBB)
    for _ in range(3):
        cell.add_paragraph("").paragraph_format.space_after = Pt(8)

    # ── FOOTER ──
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_text = (
        f"Source: Statistics Canada IO Tables  |  {shock_source}  |  "
        f"Generated {date.today().strftime('%B %d, %Y')}  |  "
        f"Agri-Food Economic Dashboard")
    r = p.add_run(footer_text)
    r.font.size = Pt(6); r.font.italic = True; r.font.name = "Calibri"
    r.font.color.rgb = RGBColor(0xAA, 0xAA, 0xAA)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf
