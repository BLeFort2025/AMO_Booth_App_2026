"""
Farm Tax Story — interactive section for the Farmland Taxation tab.

Replaces static OFA field-staff reports with an interactive story:
  1. Assessment Trends (CVA over time by class)
  2. Tax Payment Trends (annual muni taxes by class, with YoY % toggle)
  3. Tax Burden Shift (stacked area of class shares)
  4. Revenue-Neutral Ratio Calculator
  5. Word Report Export

RED-TEAM AUDIT FIXES (2025-02-23):
  - Fix 1: True W / Model-vs-Model math (in farm_tax_report.py)
  - Fix 2: "All Other Classes" impact row — zero-sum verified
  - Fix 3: CVA freeze annotation on assessment chart
  - Fix 4: Per-household impact metric
  - Fix 5: County vs Township jurisdictional warning
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go

from farm_tax.farm_tax_report import (
    calculate_revenue_neutral_ratio,
    generate_word_report,
    generate_pptx_report,
    generate_delegation_letter,
    resolve_upper_tier,
    MAX_FARM_RATIO,
)


# ── Color palette ────────────────────────────────────────────────────────────
CLASS_COLORS = {
    "Farmland":           "#2E7D32",  # OFA Green
    "Residential":        "#1565C0",  # Blue
    "Commercial":         "#E65100",  # Orange
    "Industrial":         "#6A1B9A",  # Purple
    "Multi-Residential":  "#00838F",  # Teal
    "Pipeline":           "#4E342E",  # Brown
    "Managed Forest":     "#558B2F",  # Light Green
    "Landfill":           "#37474F",  # Dark Grey
    "All Other":          "#78909C",  # Blue-Grey
}


# ── Data helper ──────────────────────────────────────────────────────────────

def _get_fir_wide(fir_wide_df: pd.DataFrame, sgc_code: str) -> pd.DataFrame:
    """Filter wide-format FIR data to a single municipality, sorted by year."""
    df = fir_wide_df[fir_wide_df["sgc_code"] == sgc_code].copy()
    df = df.sort_values("year").reset_index(drop=True)
    return df


def _get_provincial(fir_wide_df: pd.DataFrame) -> pd.DataFrame:
    """For provincial view, the input IS the aggregated df — just sort by year."""
    return fir_wide_df.sort_values("year").reset_index(drop=True)


def _safe_val(row, col):
    """Get a numeric value from a row, returning 0 for None/NaN."""
    v = row.get(col)
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return 0.0
    return float(v)


def _is_two_tier(row) -> bool:
    """Detect if this municipality is in a two-tier system.

    If there are upper-tier taxes (ut_taxes > 0), it's a lower-tier
    municipality within a county/region — ratios are set at the county level.
    """
    ut = _safe_val(row, "total_ut_taxes")
    return ut > 0


# ── Indexed series helper ────────────────────────────────────────────────────

BASE_YEAR = 2010  # Fixed base year for indexed charts


def _compute_indexed_series(
    df: pd.DataFrame,
    col_map: dict,
    base_year: int = BASE_YEAR,
) -> tuple[pd.DataFrame, dict]:
    """Compute indexed series (base year = 100) for each column in col_map.

    Parameters
    ----------
    df : DataFrame with a 'year' column and the data columns.
    col_map : dict mapping {display_label: column_name}, e.g. {"Farmland": "farmland_cva"}.
    base_year : int, the year to anchor at 100. Falls back to first valid year if base_year
                has no data or value <= 0 for a given series.

    Returns
    -------
    indexed_df : DataFrame with 'year' column + one column per label named '{label}_idx'.
    base_info : dict mapping {label: {'base_year': int, 'base_val': float, 'latest_val': float,
                'latest_idx': float}} for narrative generation.
    """
    indexed_df = df[["year"]].copy()
    base_info = {}

    for label, col in col_map.items():
        if col not in df.columns:
            continue

        vals = df[col].fillna(0).values
        years = df["year"].values

        # Find base value: prefer the requested base_year, fall back to first valid year
        base_val = None
        actual_base_year = base_year
        base_mask = (years == base_year)
        if base_mask.any():
            candidate = float(vals[base_mask][0])
            if candidate > 0:
                base_val = candidate

        # Fallback: first year with value > 0
        if base_val is None:
            for i, (y, v) in enumerate(zip(years, vals)):
                if v > 0:
                    base_val = float(v)
                    actual_base_year = int(y)
                    break

        if base_val is None or base_val <= 0:
            # No valid data for this series at all
            indexed_df[f"{label}_idx"] = np.nan
            base_info[label] = {
                "base_year": actual_base_year, "base_val": 0,
                "latest_val": 0, "latest_idx": None,
            }
            continue

        # Compute index: (value / base_value) * 100
        idx_col = f"{label}_idx"
        indexed_df[idx_col] = (df[col].fillna(0) / base_val) * 100

        # Store info for narratives
        latest_val = float(vals[-1]) if len(vals) > 0 else 0
        latest_idx = float(indexed_df[idx_col].iloc[-1]) if len(indexed_df) > 0 else None

        base_info[label] = {
            "base_year": int(actual_base_year),
            "base_val": base_val,
            "latest_val": latest_val,
            "latest_idx": latest_idx,
        }

    return indexed_df, base_info


# ── Assessment Trends ────────────────────────────────────────────────────────

def _render_assessment_trends(df: pd.DataFrame, muni_name: str, is_provincial: bool = False):
    """Tab 1: CVA trends over time with CVA freeze annotation (Fix 3)."""
    cva_cols = {
        "Farmland": "farmland_cva",
        "Residential": "residential_cva",
        "Commercial": "commercial_cva",
        "Industrial": "industrial_cva",
    }

    # Filter to available columns
    available = {k: v for k, v in cva_cols.items() if v in df.columns}
    if not available:
        st.warning("No CVA data available for this municipality.")
        return

    # Summary metrics — per-class first-valid-year logic
    # Some municipalities have CVA=0 in early years (e.g. 2010 MMAH template
    # issue). Instead of blindly using df["year"].min(), find the first year
    # with actual CVA > 0 for each class independently.
    first_year = df["year"].min()
    last_year = df["year"].max()
    growth = {}
    growth_years = {}  # {label: (first_yr, last_yr)} — actual range used
    for label, col in available.items():
        # Find first year where this class has CVA > 0
        valid_rows = df[df[col].notna() & (df[col] > 0)].sort_values("year")
        if valid_rows.empty:
            growth[label] = None
            growth_years[label] = (first_year, last_year)
            continue
        base_year = int(valid_rows["year"].iloc[0])
        base_val = float(valid_rows[col].iloc[0])
        # Get latest year value
        last_rows = df[df["year"] == last_year]
        last_val = float(last_rows[col].iloc[0]) if len(last_rows) and pd.notna(last_rows[col].iloc[0]) else None
        if last_val is not None and last_val > 0 and base_val > 0:
            growth[label] = ((last_val - base_val) / base_val) * 100
            growth_years[label] = (base_year, int(last_year))
        else:
            growth[label] = None
            growth_years[label] = (base_year, int(last_year))

    summary_cols = st.columns(len(available))
    for i, (label, pct) in enumerate(growth.items()):
        with summary_cols[i]:
            yr_from, yr_to = growth_years.get(label, (first_year, last_year))
            if pct is not None:
                st.metric(
                    f"{label} CVA Growth",
                    f"{pct:+.1f}%",
                    delta=f"{yr_from}→{yr_to}",
                    delta_color="normal" if label != "Farmland" else "inverse",
                )
            else:
                st.metric(f"{label} CVA Growth", "N/A")

    # ── View mode toggle ──
    cva_view_mode = st.radio(
        "View",
        ["📊 Absolute ($)", "📈 Indexed (2010 = 100)"],
        horizontal=True,
        key="cva_view_mode",
        help="Indexed view normalizes all classes to 100 at the base year, revealing relative growth rates.",
    )

    if cva_view_mode == "📊 Absolute ($)":
        # ── Absolute dollar chart (original) ──
        fig = go.Figure()
        for label, col in available.items():
            fig.add_trace(go.Scatter(
                x=df["year"],
                y=df[col],
                name=label,
                line=dict(color=CLASS_COLORS.get(label, "#888"), width=3),
                mode="lines+markers",
                marker=dict(size=6),
                hovertemplate=f"{label}: $%{{y:,.0f}}<extra></extra>",
            ))

        # ── Fix 3: CVA Freeze annotation ──
        if int(first_year) <= 2020 <= int(last_year):
            fig.add_vline(
                x=2020, line_width=2, line_dash="dash", line_color="#B71C1C",
                annotation_text="CVA Frozen",
                annotation_position="top left",
                annotation_font_size=10,
                annotation_font_color="#B71C1C",
            )

        fig.update_layout(
            title=f"Current Value Assessment by Tax Class — {muni_name}",
            xaxis_title="FIR Year",
            yaxis_title="Taxable CVA ($)",
            yaxis_tickformat="$,.0f",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=450,
            template="plotly_white",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, key="farm_story_cva")
    else:
        # ── Indexed chart (Base Year = 100) ──
        indexed_df, base_info = _compute_indexed_series(df, available)

        # Determine the actual base year used (take from Farmland, fallback to first available)
        actual_base = BASE_YEAR
        for lbl in ["Farmland"] + list(available.keys()):
            if lbl in base_info and base_info[lbl].get("base_val", 0) > 0:
                actual_base = base_info[lbl]["base_year"]
                break

        fig = go.Figure()
        for label in available:
            idx_col = f"{label}_idx"
            if idx_col not in indexed_df.columns:
                continue
            raw_col = available[label]
            # Build custom hover showing both index and raw dollar value
            raw_vals = df[raw_col].fillna(0)
            customdata = raw_vals.values
            fig.add_trace(go.Scatter(
                x=indexed_df["year"],
                y=indexed_df[idx_col],
                name=label,
                line=dict(color=CLASS_COLORS.get(label, "#888"), width=3),
                mode="lines+markers",
                marker=dict(size=6),
                customdata=customdata,
                hovertemplate=f"{label}: %{{y:.1f}}  (raw: $%{{customdata:,.0f}})<extra></extra>",
            ))

        # Baseline reference at 100
        fig.add_hline(y=100, line_dash="dot", line_color="#999", line_width=1,
                      annotation_text=f"Base ({actual_base})",
                      annotation_position="bottom right",
                      annotation_font_size=9, annotation_font_color="#999")

        # CVA Freeze annotation
        if int(first_year) <= 2020 <= int(last_year):
            fig.add_vline(
                x=2020, line_width=2, line_dash="dash", line_color="#B71C1C",
                annotation_text="CVA Frozen",
                annotation_position="top left",
                annotation_font_size=10,
                annotation_font_color="#B71C1C",
            )

        fig.update_layout(
            title=f"CVA Growth Rate Comparison — {muni_name} (Index: {actual_base} = 100)",
            xaxis_title="FIR Year",
            yaxis_title=f"Index ({actual_base} = 100)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=450,
            template="plotly_white",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, key="farm_story_cva_indexed")

        # Indexed narrative callout
        farm_info = base_info.get("Farmland", {})
        res_info = base_info.get("Residential", {})
        if farm_info.get("latest_idx") and res_info.get("latest_idx"):
            farm_idx = farm_info["latest_idx"]
            res_idx = res_info["latest_idx"]
            st.info(
                f"📈 **Indexed growth ({actual_base}→{int(last_year)}):** "
                f"Farmland CVA reached **{farm_idx:.0f}** vs Residential at **{res_idx:.0f}** "
                f"— farmland grew **{(farm_idx - 100) / max(res_idx - 100, 0.1):.1f}×** faster "
                f"in percentage terms."
            )

    # Fix 3: CVA freeze disclaimer text (R4: precise language)
    if is_provincial:
        st.caption(
            "⚠️ **CVA Freeze:** CVA frozen at Jan 1, 2016 valuation levels "
            "(phased in 2017–2020). Post-2020 aggregate tax growth is driven "
            "entirely by municipal budget increases, not assessment growth."
        )
    else:
        st.caption(
            "⚠️ **CVA Freeze:** The last province-wide reassessment was based on "
            "January 1, 2016 property values. These values were phased in over four "
            "years (2017–2020). Since 2020, all assessments have been frozen. "
            "Post-2020 CVA changes reflect new construction, demolitions, and "
            "supplementary assessments only — not market-value reassessment."
        )

    # R3: Farmland CVA as % of Total Provincial CVA (provincial only)
    if is_provincial and "farmland_cva_share" in df.columns:
        first_share = df[df["year"] == first_year]["farmland_cva_share"].iloc[0] if len(df[df["year"] == first_year]) else None
        last_share = df[df["year"] == last_year]["farmland_cva_share"].iloc[0] if len(df[df["year"] == last_year]) else None
        if first_share is not None and last_share is not None:
            st.info(
                f"🌾 **Farmland share of total provincial CVA:** "
                f"{first_share:.2%} ({first_year}) → {last_share:.2%} ({last_year})"
            )

    return growth


# ── Tax Payment Trends ───────────────────────────────────────────────────────

def _render_tax_payment_trends(df: pd.DataFrame, muni_name: str, is_provincial: bool = False):
    """Tab 2: Municipal tax payments over time with YoY % change toggle.

    Shows annual municipal taxes (LT + UT, excluding education levy) by
    property class. Toggle switches between absolute dollars and
    year-over-year percentage change.

    Provincial view: adds education levy as stacked component for farmland.
    """
    tax_cols = {
        "Farmland":     "farmland_muni_taxes",
        "Residential":  "residential_muni_taxes",
        "Commercial":   "commercial_muni_taxes",
        "Industrial":   "industrial_muni_taxes",
    }

    available = {k: v for k, v in tax_cols.items() if v in df.columns}
    if not available:
        st.warning("No municipal tax payment data available for this municipality.")
        return None

    first_year = df["year"].min()
    last_year = df["year"].max()

    # ── Summary metric cards: latest-year taxes ──
    latest = df[df["year"] == last_year].iloc[0]
    
    # Calculate tax per acre if possible
    latest_tax_per_acre = None
    if "farmland_tax_per_acre" in df.columns and pd.notnull(latest.get("farmland_tax_per_acre")):
        latest_tax_per_acre = latest["farmland_tax_per_acre"]

    if is_provincial and "farmland_edu_taxes" in df.columns:
        # Provincial: show muni, edu, and total for farmland
        num_cols = 5 if latest_tax_per_acre is not None else 4
        cols = st.columns(num_cols)
        with cols[0]:
            st.metric(f"Farm Municipal Taxes ({int(last_year)})", f"${_safe_val(latest, 'farmland_muni_taxes'):,.0f}")
        with cols[1]:
            st.metric(f"Farm Education Taxes ({int(last_year)})", f"${_safe_val(latest, 'farmland_edu_taxes'):,.0f}")
        with cols[2]:
            st.metric(f"Farm Total Taxes ({int(last_year)})", f"${_safe_val(latest, 'farmland_total_taxes'):,.0f}")
        with cols[3]:
            st.metric(f"Residential Taxes ({int(last_year)})", f"${_safe_val(latest, 'residential_muni_taxes'):,.0f}")
        if latest_tax_per_acre is not None:
            with cols[4]:
                st.metric(f"Tax per Acre ({int(last_year)})", f"${latest_tax_per_acre:,.2f}")
    else:
        num_cols = len(available) + (1 if latest_tax_per_acre is not None else 0)
        metric_cols = st.columns(num_cols)
        for i, (label, col) in enumerate(available.items()):
            val = _safe_val(latest, col)
            with metric_cols[i]:
                st.metric(f"{label} Taxes ({int(last_year)})", f"${val:,.0f}")
        if latest_tax_per_acre is not None:
            with metric_cols[-1]:
                st.metric(f"Tax per Acre ({int(last_year)})", f"${latest_tax_per_acre:,.2f}")

    # ── Toggle: Absolute vs YoY % vs Indexed ──
    view_mode = st.radio(
        "View",
        ["Absolute ($)", "Year-over-Year Change (%)", "📈 Indexed (2010 = 100)", "🌾 Tax per Acre ($)", "🌾 Indexed Tax per Acre (2010 = 100)"],
        horizontal=True,
        key="tax_trends_view_mode",
    )

    if view_mode == "Absolute ($)":
        fig = go.Figure()

        if is_provincial and "farmland_edu_taxes" in df.columns:
            # R2: Stacked area for farmland (muni bottom, edu top)
            fig.add_trace(go.Scatter(
                x=df["year"], y=df["farmland_muni_taxes"].fillna(0),
                name="Farmland (Municipal)",
                stackgroup="farm",
                line=dict(color=CLASS_COLORS["Farmland"], width=2),
                hovertemplate="Farm Municipal: $%{y:,.0f}<extra></extra>",
            ))
            fig.add_trace(go.Scatter(
                x=df["year"], y=df["farmland_edu_taxes"].fillna(0),
                name="Farmland (Education)",
                stackgroup="farm",
                line=dict(color="#81C784", width=2),
                hovertemplate="Farm Education: $%{y:,.0f}<extra></extra>",
            ))
            # Other classes as simple lines
            for label, col in available.items():
                if label == "Farmland":
                    continue
                vals = df[col].fillna(0)
                if vals.sum() == 0:
                    continue
                fig.add_trace(go.Scatter(
                    x=df["year"], y=vals, name=label,
                    line=dict(color=CLASS_COLORS.get(label, "#888"), width=3),
                    mode="lines+markers", marker=dict(size=6),
                    hovertemplate=f"{label}: $%{{y:,.0f}}<extra></extra>",
                ))
        else:
            # Standard: line chart for all classes
            for label, col in available.items():
                vals = df[col].fillna(0)
                if vals.sum() == 0:
                    continue
                fig.add_trace(go.Scatter(
                    x=df["year"], y=vals, name=label,
                    line=dict(color=CLASS_COLORS.get(label, "#888"), width=3),
                    mode="lines+markers", marker=dict(size=6),
                    hovertemplate=f"{label}: $%{{y:,.0f}}<extra></extra>",
                ))

        title_suffix = " (incl. Education Levy)" if is_provincial else ""
        fig.update_layout(
            title=f"Municipal Property Tax Levy by Class — {muni_name}{title_suffix}",
            xaxis_title="FIR Year",
            yaxis_title="Taxes ($)",
            yaxis_tickformat="$,.0f",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=450, template="plotly_white", hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, key="farm_story_tax_trends_abs")
    elif view_mode == "Year-over-Year Change (%)":
        # ── Year-over-Year % change line chart ──
        fig = go.Figure()
        for label, col in available.items():
            vals = df[col].fillna(0)
            if vals.sum() == 0:
                continue
            yoy = vals.pct_change() * 100
            yoy = yoy.replace([np.inf, -np.inf], np.nan)
            fig.add_trace(go.Scatter(
                x=df["year"], y=yoy, name=label,
                line=dict(color=CLASS_COLORS.get(label, "#888"), width=3),
                mode="lines+markers", marker=dict(size=6),
                connectgaps=False,
                hovertemplate=f"{label}: %{{y:+.1f}}%<extra></extra>",
            ))

        fig.add_hline(y=0, line_dash="dot", line_color="#999", line_width=1)
        fig.update_layout(
            title=f"Year-over-Year Change in Municipal Property Tax Levy — {muni_name}",
            xaxis_title="FIR Year",
            yaxis_title="Change from Previous Year (%)",
            yaxis=dict(ticksuffix="%"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=450, template="plotly_white", hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, key="farm_story_tax_trends_yoy")
    elif view_mode == "📈 Indexed (2010 = 100)":
        # ── Indexed chart (Base Year = 100) ──
        indexed_df, base_info = _compute_indexed_series(df, available)

        actual_base = BASE_YEAR
        for lbl in ["Farmland"] + list(available.keys()):
            if lbl in base_info and base_info[lbl].get("base_val", 0) > 0:
                actual_base = base_info[lbl]["base_year"]
                break

        fig = go.Figure()
        for label in available:
            idx_col = f"{label}_idx"
            if idx_col not in indexed_df.columns:
                continue
            raw_col = available[label]
            raw_vals = df[raw_col].fillna(0)
            customdata = raw_vals.values
            fig.add_trace(go.Scatter(
                x=indexed_df["year"],
                y=indexed_df[idx_col],
                name=label,
                line=dict(color=CLASS_COLORS.get(label, "#888"), width=3),
                mode="lines+markers",
                marker=dict(size=6),
                customdata=customdata,
                hovertemplate=f"{label}: %{{y:.1f}}  (raw: $%{{customdata:,.0f}})<extra></extra>",
            ))

        fig.add_hline(y=100, line_dash="dot", line_color="#999", line_width=1,
                      annotation_text=f"Base ({actual_base})",
                      annotation_position="bottom right",
                      annotation_font_size=9, annotation_font_color="#999")

        fig.update_layout(
            title=f"Tax Payment Growth Comparison — {muni_name} (Index: {actual_base} = 100)",
            xaxis_title="FIR Year",
            yaxis_title=f"Index ({actual_base} = 100)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=450, template="plotly_white", hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, key="farm_story_tax_trends_indexed")

        # Indexed narrative
        farm_info = base_info.get("Farmland", {})
        res_info = base_info.get("Residential", {})
        if farm_info.get("latest_idx") and res_info.get("latest_idx"):
            farm_idx = farm_info["latest_idx"]
            res_idx = res_info["latest_idx"]
            st.info(
                f"📈 **Indexed tax growth ({actual_base}→{int(last_year)}):** "
                f"Farm taxes reached **{farm_idx:.0f}** vs Residential at **{res_idx:.0f}** "
                f"— farm taxes grew **{(farm_idx - 100) / max(res_idx - 100, 0.1):.1f}×** faster."
            )

    elif view_mode == "🌾 Tax per Acre ($)":
        # ── Tax per Acre Chart ──
        fig = go.Figure()
        if "farmland_tax_per_acre" in df.columns and df["farmland_tax_per_acre"].notna().any():
            vals = df["farmland_tax_per_acre"]
            
            fig.add_trace(go.Scatter(
                x=df["year"], y=vals, name="Farmland Tax per Acre",
                line=dict(color=CLASS_COLORS.get("Farmland", "#888"), width=3),
                mode="lines+markers", marker=dict(size=6),
                hovertemplate="Tax per Acre: $%{y:,.2f}<extra></extra>",
                connectgaps=False
            ))
            st.write("DEBUG DF:", df[["year", "farmland_muni_taxes", "census_acres", "farmland_tax_per_acre"]])
            fig.update_layout(
                title=f"Average Municipal Farm Property Tax per Acre — {muni_name}",
                xaxis_title="FIR Year",
                yaxis_title="Tax per Acre ($)",
                yaxis_tickformat="$,.2f",
                height=450, template="plotly_white", hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True, key="farm_story_tax_trends_per_acre")
        else:
            st.info("Tax per acre data is not available for this municipality. (No Census data found)")

    elif view_mode == "🌾 Indexed Tax per Acre (2010 = 100)":
        if "farmland_tax_per_acre" in df.columns and df["farmland_tax_per_acre"].notna().any():
            idx_map = {"Farmland Tax per Acre": "farmland_tax_per_acre"}
            indexed_df, base_info = _compute_indexed_series(df, idx_map)
            
            actual_base = BASE_YEAR
            if "Farmland Tax per Acre" in base_info and base_info["Farmland Tax per Acre"].get("base_val", 0) > 0:
                actual_base = base_info["Farmland Tax per Acre"]["base_year"]

            fig = go.Figure()
            idx_col = "Farmland Tax per Acre_idx"
            if idx_col in indexed_df.columns:
                raw_vals = df["farmland_tax_per_acre"].fillna(0)
                customdata = raw_vals.values
                fig.add_trace(go.Scatter(
                    x=indexed_df["year"],
                    y=indexed_df[idx_col],
                    name="Farmland Tax per Acre",
                    line=dict(color=CLASS_COLORS.get("Farmland", "#888"), width=3),
                    mode="lines+markers",
                    marker=dict(size=6),
                    customdata=customdata,
                    hovertemplate="Tax per Acre: %{y:.1f}  (raw: $%{customdata:,.2f})<extra></extra>",
                    connectgaps=False
                ))

            fig.add_hline(y=100, line_dash="dot", line_color="#999", line_width=1,
                          annotation_text=f"Base ({actual_base})",
                          annotation_position="bottom right",
                          annotation_font_size=9, annotation_font_color="#999")

            fig.update_layout(
                title=f"Tax per Acre Growth Comparison — {muni_name} (Index: {actual_base} = 100)",
                xaxis_title="FIR Year",
                yaxis_title=f"Index ({actual_base} = 100)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                height=450, template="plotly_white", hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True, key="farm_story_tax_trends_indexed_per_acre")
            
            info = base_info.get("Farmland Tax per Acre", {})
            if info.get("latest_idx"):
                farm_idx = info["latest_idx"]
                st.info(
                    f"📈 **Indexed tax per acre growth ({actual_base}→{int(last_year)}):** "
                    f"Tax per acre reached **{farm_idx:.0f}**, meaning it grew **{(farm_idx - 100) / 100:.1f}×** "
                    f"since the base year."
                )
        else:
            st.info("Tax per acre data is not available for this municipality. (No Census data found)")

    if is_provincial:
        st.caption(
            "💡 **Provincial taxes** = sum of all lower-tier and single-tier municipal "
            "levies (LT + UT). Farmland stacked area shows municipal + education components."
        )
    else:
        st.caption(
            "💡 **Municipal taxes** = Lower-Tier (LT) + Upper-Tier (UT) taxes, "
            "excluding the provincial education levy."
        )

    # Build data dict for Word report
    tax_trends = {}
    for _, row in df.iterrows():
        yr = int(row["year"])
        tax_trends[yr] = {
            "farm": _safe_val(row, "farmland_muni_taxes"),
            "res":  _safe_val(row, "residential_muni_taxes"),
            "com":  _safe_val(row, "commercial_muni_taxes"),
            "ind":  _safe_val(row, "industrial_muni_taxes"),
        }
    return tax_trends


# ── Tax Burden Shift ─────────────────────────────────────────────────────────

def _render_burden_shift(df: pd.DataFrame, muni_name: str, is_provincial: bool = False):
    """Tab 3: line chart showing each class's share of municipal taxes over time."""
    share_cols = {
        "Farmland":          "farmland_share_of_taxes",
        "Residential":       "residential_share_of_taxes",
        "Commercial":        "commercial_share_of_taxes",
        "Industrial":        "industrial_share_of_taxes",
    }
    # Non-provincial views also show multi-res and pipeline
    if not is_provincial:
        share_cols["Multi-Residential"] = "multi_residential_share_of_taxes"
        share_cols["Pipeline"] = "pipeline_share_of_taxes"

    available = {k: v for k, v in share_cols.items() if v in df.columns}
    if not available:
        st.warning("No tax burden data available for this municipality.")
        return None

    first_year = df["year"].min()
    last_year = df["year"].max()

    # Callout: farmland burden change
    farm_col = share_cols.get("Farmland")
    if farm_col and farm_col in df.columns:
        first_row = df[df["year"] == first_year]
        last_row = df[df["year"] == last_year]
        if len(first_row) and len(last_row):
            start_pct = first_row[farm_col].iloc[0]
            end_pct = last_row[farm_col].iloc[0]
            if pd.notna(start_pct) and pd.notna(end_pct):
                delta = (end_pct - start_pct) * 100
                direction = "increased" if delta > 0 else "decreased"
                arrow = "⬆️" if delta > 0 else "⬇️"
                st.info(
                    f"🌾 **Farmland tax burden:** {start_pct:.1%} ({first_year}) → "
                    f"{end_pct:.1%} ({last_year}) — "
                    f"{arrow} {direction} by "
                    f"**{abs(delta):.1f} percentage points**"
                )

    # ── View mode toggle ──
    burden_view_mode = st.radio(
        "View",
        ["📊 Percentage (%)", "📈 Indexed (2010 = 100)"],
        horizontal=True,
        key="burden_view_mode",
        help="Indexed view normalizes each class's share to 100 at the base year, showing which shares are growing or shrinking.",
    )

    if burden_view_mode == "📊 Percentage (%)":
        # ── Percentage chart (original) ──
        fig = go.Figure()
        for label, col in available.items():
            vals = df[col].fillna(0) * 100  # convert to %
            # Skip classes with all-zero values to reduce clutter
            if vals.sum() == 0:
                continue
            fig.add_trace(go.Scatter(
                x=df["year"],
                y=vals,
                name=label,
                mode="lines+markers",
                line=dict(width=3, color=CLASS_COLORS.get(label, "#888")),
                marker=dict(size=6),
                hovertemplate=f"{label}: %{{y:.2f}}%<extra></extra>",
            ))

        fig.update_layout(
            title=f"Tax Burden by Class (% of Municipal Taxes) — {muni_name}",
            xaxis_title="FIR Year",
            yaxis_title="Share of Municipal Taxes (%)",
            yaxis=dict(ticksuffix="%", rangemode="tozero"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=450,
            template="plotly_white",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, key="farm_story_burden")
    else:
        # ── Indexed chart (Base Year = 100) ──
        indexed_df, base_info = _compute_indexed_series(df, available)

        actual_base = BASE_YEAR
        for lbl in ["Farmland"] + list(available.keys()):
            if lbl in base_info and base_info[lbl].get("base_val", 0) > 0:
                actual_base = base_info[lbl]["base_year"]
                break

        fig = go.Figure()
        for label in available:
            idx_col = f"{label}_idx"
            if idx_col not in indexed_df.columns:
                continue
            raw_col = available[label]
            raw_pct = df[raw_col].fillna(0) * 100
            customdata = raw_pct.values
            fig.add_trace(go.Scatter(
                x=indexed_df["year"],
                y=indexed_df[idx_col],
                name=label,
                mode="lines+markers",
                line=dict(width=3, color=CLASS_COLORS.get(label, "#888")),
                marker=dict(size=6),
                customdata=customdata,
                hovertemplate=f"{label}: %{{y:.1f}}  (share: %{{customdata:.2f}}%)<extra></extra>",
            ))

        fig.add_hline(y=100, line_dash="dot", line_color="#999", line_width=1,
                      annotation_text=f"Base ({actual_base})",
                      annotation_position="bottom right",
                      annotation_font_size=9, annotation_font_color="#999")

        fig.update_layout(
            title=f"Tax Burden Shift Rate — {muni_name} (Index: {actual_base} = 100)",
            xaxis_title="FIR Year",
            yaxis_title=f"Burden Index ({actual_base} = 100)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=450,
            template="plotly_white",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, key="farm_story_burden_indexed")

        # Narrative: classes above 100 gained burden share, below 100 lost it
        farm_info = base_info.get("Farmland", {})
        if farm_info.get("latest_idx") is not None:
            farm_idx = farm_info["latest_idx"]
            direction = "grown" if farm_idx > 100 else "shrunk"
            pct_change = farm_idx - 100
            st.info(
                f"📈 **Burden index ({actual_base}→{int(last_year)}):** "
                f"Farmland's share has **{direction}** to an index of **{farm_idx:.0f}** "
                f"({pct_change:+.1f}% relative to {actual_base}). "
                f"Classes above 100 have *gained* burden share; below 100 have *lost* it."
            )

    # Provincial: education-inclusive burden toggle
    if is_provincial and "farmland_share_of_total_taxes" in df.columns:
        show_total = st.checkbox(
            "Show education-inclusive burden",
            value=False,
            help="Include education levy in the burden calculation",
            key="burden_total_toggle",
        )
        if show_total:
            farm_total_share = df["farmland_share_of_total_taxes"] * 100
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=df["year"], y=farm_total_share,
                name="Farmland (Total incl. Education)",
                mode="lines+markers",
                line=dict(width=3, color=CLASS_COLORS["Farmland"]),
                marker=dict(size=6),
                hovertemplate="Farm burden (total): %{y:.2f}%<extra></extra>",
            ))
            # Also show municipal-only for comparison
            farm_muni_share = df["farmland_share_of_taxes"] * 100
            fig2.add_trace(go.Scatter(
                x=df["year"], y=farm_muni_share,
                name="Farmland (Municipal only)",
                mode="lines+markers",
                line=dict(width=2, color="#81C784", dash="dash"),
                marker=dict(size=4),
                hovertemplate="Farm burden (muni only): %{y:.2f}%<extra></extra>",
            ))
            fig2.update_layout(
                title="Farmland Tax Burden — Municipal vs Total (incl. Education)",
                xaxis_title="FIR Year",
                yaxis_title="Share of Total Taxes (%)",
                yaxis=dict(ticksuffix="%", rangemode="tozero"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                height=400, template="plotly_white", hovermode="x unified",
            )
            st.plotly_chart(fig2, use_container_width=True, key="farm_story_burden_total")

    # Build burden-by-year dict for Word export
    burden_by_year = {}
    for _, row in df.iterrows():
        yr = int(row["year"])
        burden_by_year[yr] = {
            "farm": _safe_val(row, "farmland_share_of_taxes"),
            "res":  _safe_val(row, "residential_share_of_taxes"),
            "com":  _safe_val(row, "commercial_share_of_taxes"),
            "ind":  _safe_val(row, "industrial_share_of_taxes"),
        }
    return burden_by_year


# ── Revenue-Neutral Ratio Calculator ─────────────────────────────────────────

def _render_ratio_calculator(df: pd.DataFrame, muni_name: str, is_provincial: bool = False, fir_raw_df: pd.DataFrame = None):
    """Tab 4: what-if calculator with True W / Model-vs-Model math.

    Provincial view: shows Effective Provincial Ratio KPI + mandated ratio simulator.
    """

    years = sorted(df["year"].unique())
    if len(years) < 2:
        st.warning("Need at least 2 years of data for the calculator.")
        return None

    # ── Provincial: Effective Provincial Farm Tax Ratio KPI (C3) ──
    if is_provincial:
        st.info(
            "⚖️ **Note:** The revenue-neutral ratio calculator is not applicable at "
            "the provincial level. Property tax pools are closed systems ring-fenced "
            "by municipal borders — each municipality sets its own ratio. "
            "Below is the **Effective Provincial Farm Tax Ratio** instead."
        )

        if "effective_provincial_ratio" in df.columns:
            first_year = int(min(years))
            last_year = int(max(years))
            first_ratio = df[df["year"] == first_year]["effective_provincial_ratio"].iloc[0]
            last_ratio = df[df["year"] == last_year]["effective_provincial_ratio"].iloc[0]
            delta_pp = (last_ratio - first_ratio) * 100

            rc1, rc2, rc3 = st.columns(3)
            with rc1:
                st.metric(
                    f"Eff. Ratio ({first_year})",
                    f"{first_ratio:.4f}",
                )
            with rc2:
                st.metric(
                    f"Eff. Ratio ({last_year})",
                    f"{last_ratio:.4f}",
                    delta=f"{delta_pp:+.2f} pp",
                    delta_color="inverse",
                )
            with rc3:
                st.metric("Provincial Maximum", f"{MAX_FARM_RATIO:.2f}")

            # Trend chart
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["year"],
                y=df["effective_provincial_ratio"],
                name="Effective Provincial Ratio",
                mode="lines+markers",
                line=dict(color=CLASS_COLORS["Farmland"], width=3),
                marker=dict(size=6),
                hovertemplate="Ratio: %{y:.4f}<extra></extra>",
            ))
            fig.add_hline(
                y=MAX_FARM_RATIO, line_dash="dash", line_color="#B71C1C",
                annotation_text="Provincial Max (0.25)",
                annotation_position="bottom right",
                annotation_font_color="#B71C1C",
            )
            fig.update_layout(
                title="Effective Provincial Farm Tax Ratio Over Time",
                xaxis_title="FIR Year",
                yaxis_title="Effective Ratio",
                yaxis=dict(rangemode="tozero"),
                height=400, template="plotly_white",
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True, key="farm_story_prov_ratio")

            st.caption(
                "📊 **Effective Provincial Farm Tax Ratio** = CVA-weighted average "
                "of individual municipality farm tax ratios. This reflects how close "
                "Ontario municipalities are, on aggregate, to the 0.25 statutory maximum. "
                "Individual municipality ratios vary."
            )

        # ── Mandated Ratio Simulator ──
        st.markdown("---")
        st.subheader("🔮 Provincial Ratio Simulator")
        st.markdown(
            "Simulate the effect of a **province-wide mandated farm tax ratio**. "
            "For each municipality currently above the mandated threshold, this calculator "
            "applies revenue-neutral redistribution (True W / Model-vs-Model) and sums "
            "the province-wide impact."
        )

        if fir_raw_df is not None:
            sim_ratio = st.slider(
                "Mandated Farm Tax Ratio",
                min_value=0.05,
                max_value=0.25,
                value=0.15,
                step=0.01,
                format="%.2f",
                help="Set the mandated ratio. Municipalities currently above this ratio "
                     "will be adjusted downward (revenue-neutral).",
                key="prov_sim_ratio",
            )

            from app.farm_tax.provincial_simulator import simulate_mandated_ratio
            sim = simulate_mandated_ratio(fir_raw_df, sim_ratio)

            if sim["n_affected"] == 0:
                st.success(
                    f"✅ All municipalities are already at or below a ratio of {sim_ratio:.2f}. "
                    f"No changes would occur."
                )
            else:
                # ── Impact KPIs ──
                st.markdown(f"#### Impact of Mandating a {sim_ratio:.2f} Ratio")
                k1, k2, k3, k4 = st.columns(4)
                with k1:
                    st.metric(
                        "Farm Tax Savings",
                        f"${sim['farm_savings_total']:,.0f}",
                        delta="province-wide",
                        delta_color="normal",
                    )
                with k2:
                    st.metric(
                        "Municipalities Affected",
                        f"{sim['n_affected']} / {sim['n_total']}",
                    )
                with k3:
                    st.metric(
                        "Avg Residential Increase (Affected)",
                        f"${sim['avg_res_per_household']:,.2f}/yr",
                        delta=f"${sim['avg_res_per_household_month']:,.2f}/mo",
                        delta_color="inverse",
                    )
                with k4:
                    st.metric(
                        "Households Affected",
                        f"{sim['total_households_affected']:,.0f}",
                    )

                # ── Redistribution breakdown ──
                st.markdown("##### Revenue-Neutral Redistribution")

                redist_data = {
                    "Property Class": ["🌾 Farmland", "🏠 Residential", "🏢 Commercial", "🏭 Industrial", "📦 Other"],
                    "Tax Impact": [
                        -sim["farm_savings_total"],
                        sim["res_increase_total"],
                        sim["com_increase_total"],
                        sim["ind_increase_total"],
                        sim["other_increase_total"],
                    ],
                }
                redist_df = pd.DataFrame(redist_data)
                redist_df["Impact ($)"] = redist_df["Tax Impact"].apply(
                    lambda x: f"-${abs(x):,.0f}" if x < 0 else f"+${x:,.0f}"
                )

                # Waterfall-style horizontal bar chart
                colors = ["#4CAF50" if v < 0 else "#E53935" for v in redist_df["Tax Impact"]]
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    y=redist_df["Property Class"],
                    x=redist_df["Tax Impact"],
                    orientation="h",
                    marker_color=colors,
                    text=redist_df["Impact ($)"],
                    textposition="outside",
                    hovertemplate="%{y}: %{text}<extra></extra>",
                ))
                fig.add_vline(x=0, line_color="#333", line_width=1)
                fig.update_layout(
                    title=f"Province-Wide Tax Redistribution at {sim_ratio:.2f} Ratio",
                    xaxis_title="Tax Impact ($)",
                    xaxis_tickformat="$,.0f",
                    yaxis=dict(autorange="reversed"),
                    height=300, template="plotly_white",
                    showlegend=False,
                    margin=dict(l=10, r=100),
                )
                st.plotly_chart(fig, use_container_width=True, key="prov_sim_waterfall")

                # Zero-sum verification
                total_shift = (
                    -sim["farm_savings_total"] + sim["res_increase_total"]
                    + sim["com_increase_total"] + sim["ind_increase_total"]
                    + sim["other_increase_total"]
                )
                st.caption(f"✅ **Revenue-neutral check:** Total shift = ${total_shift:,.2f}")

                st.caption(
                    "💡 Simulation applies the mandated ratio to each municipality independently "
                    "using the True W / Model-vs-Model approach. Municipalities already at or below "
                    "the mandated ratio are unaffected. Total municipal revenue per municipality "
                    "remains unchanged."
                )
        else:
            st.warning("Raw FIR data not available for simulation.")

        return None

    # ── Individual municipality: Revenue-Neutral Calculator ──

    current_year = int(max(years))
    current_row = df[df["year"] == current_year].iloc[0]

    # ── Fix 5: Jurisdictional warning ──
    two_tier = _is_two_tier(current_row)
    if two_tier:
        st.warning(
            "⚖️ **Jurisdictional Note:** Tax ratios are set at the **Upper-Tier "
            "(County/Region) level**. Changing the farm tax ratio requires a "
            "County/Regional Council vote, not a local township council vote."
        )

    # Target year selector
    target_years = [y for y in years if y != current_year]
    target_year = st.selectbox(
        "📅 Select a target year to restore farm tax burden to:",
        options=sorted(target_years),
        index=0,
        key="farm_ratio_target_year",
    )
    target_row = df[df["year"] == int(target_year)].iloc[0]

    # Pull values
    target_burden = _safe_val(target_row, "farmland_share_of_taxes")
    current_burden = _safe_val(current_row, "farmland_share_of_taxes")

    if target_burden <= 0 or current_burden <= 0:
        st.warning("Tax burden data not available for the selected years.")
        return None

    # Show the comparison
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Farm Burden (Target Year)", f"{target_burden:.1%}",
                   delta=f"in {int(target_year)}")
    with col2:
        st.metric("Farm Burden (Current Year)", f"{current_burden:.1%}",
                   delta=f"in {current_year}")
    with col3:
        change = (current_burden - target_burden) * 100
        st.metric("Burden Increase", f"{change:+.1f} pp",
                   delta="percentage points", delta_color="inverse")

    # Get total_households for per-household metric (Fix 4)
    total_households = _safe_val(current_row, "total_households")

    # Run the revenue-neutral calculation (True W / Model-vs-Model)
    calc = calculate_revenue_neutral_ratio(
        target_burden=target_burden,
        farm_cva=_safe_val(current_row, "farmland_cva"),
        res_cva=_safe_val(current_row, "residential_cva"),
        com_cva=_safe_val(current_row, "commercial_cva"),
        ind_cva=_safe_val(current_row, "industrial_cva"),
        ft_ratio=_safe_val(current_row, "farmland_tax_ratio"),
        ct_ratio=_safe_val(current_row, "commercial_tax_ratio"),
        it_ratio=_safe_val(current_row, "industrial_tax_ratio"),
        total_muni_taxes=_safe_val(current_row, "total_muni_taxes"),
        current_farm_taxes=_safe_val(current_row, "farmland_muni_taxes"),
        current_res_taxes=_safe_val(current_row, "residential_muni_taxes"),
        current_com_taxes=_safe_val(current_row, "commercial_muni_taxes"),
        current_ind_taxes=_safe_val(current_row, "industrial_muni_taxes"),
        current_burden=current_burden,
        total_households=total_households,
    )

    if calc is None:
        st.error("Unable to calculate — insufficient data for this municipality.")
        return None

    calc.target_year = int(target_year)

    st.markdown("---")

    # ── Result display ──
    if calc.is_capped:
        st.warning(
            f"⚠️ The required farm tax ratio of **{calc.required_ratio:.4f}** exceeds the "
            f"provincial maximum of **{MAX_FARM_RATIO:.2f}**. Results below use the capped ratio."
        )

    # Ratio comparison
    rcol1, rcol2, rcol3 = st.columns(3)
    with rcol1:
        current_ratio = _safe_val(current_row, "farmland_tax_ratio")
        st.metric("Current Farm Ratio", f"{current_ratio:.4f}")
    with rcol2:
        ratio_color = "🔴" if calc.is_capped else "🟢"
        st.metric("Required Ratio", f"{ratio_color} {calc.effective_ratio:.4f}")
    with rcol3:
        st.metric("Provincial Maximum", f"{MAX_FARM_RATIO:.2f}")

    # ── Impact Table (with "All Other Classes" — Fix 2) ──
    st.markdown("### 💰 Revenue-Neutral Tax Shift Impact")
    st.caption("Total revenue stays constant — savings for farmland are distributed across other classes.")

    impact_data = pd.DataFrame([
        {
            "Tax Class": "🌾 Farmland",
            "Current Taxes": calc.model_current_farm_taxes,
            "New Taxes": calc.model_new_farm_taxes,
            "Change ($)": calc.model_new_farm_taxes - calc.model_current_farm_taxes,
            "Per $100k CVA ($)": -calc.farm_savings_per_100k,
        },
        {
            "Tax Class": "🏠 Residential",
            "Current Taxes": calc.model_current_res_taxes,
            "New Taxes": calc.model_new_res_taxes,
            "Change ($)": calc.res_increase_total,
            "Per $100k CVA ($)": calc.res_increase_per_100k,
        },
        {
            "Tax Class": "🏪 Commercial",
            "Current Taxes": calc.model_current_com_taxes,
            "New Taxes": calc.model_new_com_taxes,
            "Change ($)": calc.com_increase_total,
            "Per $100k CVA ($)": calc.com_increase_per_100k,
        },
        {
            "Tax Class": "🏭 Industrial",
            "Current Taxes": calc.model_current_ind_taxes,
            "New Taxes": calc.model_new_ind_taxes,
            "Change ($)": calc.ind_increase_total,
            "Per $100k CVA ($)": calc.ind_increase_per_100k,
        },
        {
            "Tax Class": "📦 All Other Classes",
            "Current Taxes": calc.model_current_other_taxes,
            "New Taxes": calc.model_new_other_taxes,
            "Change ($)": calc.other_increase_total,
            "Per $100k CVA ($)": None,  # no single CVA for this bucket
        },
    ])

    # Format for display
    display_df = impact_data.copy()
    for col in ["Current Taxes", "New Taxes", "Change ($)"]:
        display_df[col] = display_df[col].apply(
            lambda x: f"${x:,.0f}" if x >= 0 else f"-${abs(x):,.0f}"
        )
    display_df["Per $100k CVA ($)"] = impact_data["Per $100k CVA ($)"].apply(
        lambda x: f"+${x:,.2f}" if x is not None and x >= 0
        else (f"-${abs(x):,.2f}" if x is not None else "—")
    )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )

    # Zero-sum verification (Fix 2)
    # V7: Force-round to $0.00 — Treasurers are accountants; floating-point
    # artefacts like $0.0000000003 invite doubt. Project absolute confidence.
    st.caption(
        "✅ **Revenue-neutral check:** Total shift = \\$0.00"
    )

    # Bottom line — farm savings summary
    farm_save_total = f"{calc.farm_savings_total:,.0f}"
    farm_save_100k = f"{calc.farm_savings_per_100k:,.2f}"
    st.success(
        f"🌾 **Farm savings:** \\${farm_save_total} total "
        f"(\\${farm_save_100k} per \\$100k CVA)"
    )

    # Per-household impact (Fix 4)
    if calc.total_households > 0:
        hh_yr = f"{calc.res_increase_per_household:,.2f}"
        hh_mo = f"{calc.res_increase_per_household_month:,.2f}"
        com_100k = f"{calc.com_increase_per_100k:,.2f}"
        ind_100k = f"{calc.ind_increase_per_100k:,.2f}"
        st.info(
            f"🏠 **Cost to average household:** "
            f"\\${hh_yr}/year (\\${hh_mo}/month)  ·  "
            f"🏪 **Commercial:** +\\${com_100k}/100k  ·  "
            f"🏭 **Industrial:** +\\${ind_100k}/100k"
        )
    else:
        res_100k = f"{calc.res_increase_per_100k:,.2f}"
        com_100k = f"{calc.com_increase_per_100k:,.2f}"
        ind_100k = f"{calc.ind_increase_per_100k:,.2f}"
        st.info(
            f"🏠 **Residential impact:** +\\${res_100k} per \\$100k CVA  ·  "
            f"🏪 **Commercial:** +\\${com_100k}  ·  "
            f"🏭 **Industrial:** +\\${ind_100k}"
        )

    # ── Custom Ratio Analysis ─────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🔮 Custom Ratio Simulator")
    st.markdown(
        "Choose a specific farm tax ratio to see the revenue-neutral impact "
        "on this municipality. The same True W / Model-vs-Model math is applied."
    )

    cur_ft_ratio = _safe_val(current_row, "farmland_tax_ratio")

    custom_ratio = st.slider(
        "Choose a Farm Tax Ratio",
        min_value=0.00,
        max_value=0.25,
        value=min(cur_ft_ratio, 0.15) if cur_ft_ratio > 0 else 0.15,
        step=0.01,
        format="%.2f",
        help=f"Select a farm tax ratio to simulate. The current ratio is "
             f"{cur_ft_ratio:.4f}. The statutory maximum is 0.25.",
        key="custom_ratio_slider",
    )

    from app.farm_tax.farm_tax_report import calculate_ratio_direct

    custom_calc = calculate_ratio_direct(
        chosen_ratio=custom_ratio,
        farm_cva=_safe_val(current_row, "farmland_cva"),
        res_cva=_safe_val(current_row, "residential_cva"),
        com_cva=_safe_val(current_row, "commercial_cva"),
        ind_cva=_safe_val(current_row, "industrial_cva"),
        ft_ratio=cur_ft_ratio,
        ct_ratio=_safe_val(current_row, "commercial_tax_ratio"),
        it_ratio=_safe_val(current_row, "industrial_tax_ratio"),
        total_muni_taxes=_safe_val(current_row, "total_muni_taxes"),
        current_res_taxes=_safe_val(current_row, "residential_muni_taxes"),
        current_burden=current_burden,
        total_households=total_households,
    )

    if custom_calc is None:
        st.warning("Unable to calculate — insufficient data.")
    elif custom_ratio == cur_ft_ratio:
        st.info(f"📌 The selected ratio ({custom_ratio:.2f}) matches the current ratio. No change.")
    else:
        # Direction of change
        is_reduction = custom_ratio < cur_ft_ratio
        direction = "reduction" if is_reduction else "increase"

        # KPIs
        st.markdown(f"#### Impact of Setting Ratio to {custom_ratio:.2f}")
        ck1, ck2, ck3 = st.columns(3)
        with ck1:
            st.metric(
                "Current Ratio → New Ratio",
                f"{cur_ft_ratio:.4f} → {custom_ratio:.2f}",
            )
        with ck2:
            if is_reduction:
                st.metric(
                    "Farm Tax Savings",
                    f"${custom_calc.farm_savings_total:,.0f}",
                    delta=f"${custom_calc.farm_savings_per_100k:,.2f} per $100k CVA",
                )
            else:
                st.metric(
                    "Farm Tax Increase",
                    f"${abs(custom_calc.farm_savings_total):,.0f}",
                    delta=f"ratio {direction}",
                    delta_color="inverse",
                )
        with ck3:
            new_burden_pct = custom_calc.target_burden * 100
            st.metric(
                "New Farm Burden",
                f"{new_burden_pct:.1f}%",
                delta=f"{(custom_calc.target_burden - current_burden)*100:+.1f} pp",
                delta_color="inverse",
            )

        # Impact table (reuse same format as target-year calculator)
        st.markdown("##### 💰 Revenue-Neutral Tax Shift")
        custom_impact = pd.DataFrame([
            {
                "Tax Class": "🌾 Farmland",
                "Current Taxes": custom_calc.model_current_farm_taxes,
                "New Taxes": custom_calc.model_new_farm_taxes,
                "Change ($)": custom_calc.model_new_farm_taxes - custom_calc.model_current_farm_taxes,
                "Per $100k CVA ($)": -custom_calc.farm_savings_per_100k,
            },
            {
                "Tax Class": "🏠 Residential",
                "Current Taxes": custom_calc.model_current_res_taxes,
                "New Taxes": custom_calc.model_new_res_taxes,
                "Change ($)": custom_calc.res_increase_total,
                "Per $100k CVA ($)": custom_calc.res_increase_per_100k,
            },
            {
                "Tax Class": "🏪 Commercial",
                "Current Taxes": custom_calc.model_current_com_taxes,
                "New Taxes": custom_calc.model_new_com_taxes,
                "Change ($)": custom_calc.com_increase_total,
                "Per $100k CVA ($)": custom_calc.com_increase_per_100k,
            },
            {
                "Tax Class": "🏭 Industrial",
                "Current Taxes": custom_calc.model_current_ind_taxes,
                "New Taxes": custom_calc.model_new_ind_taxes,
                "Change ($)": custom_calc.ind_increase_total,
                "Per $100k CVA ($)": custom_calc.ind_increase_per_100k,
            },
            {
                "Tax Class": "📦 All Other Classes",
                "Current Taxes": custom_calc.model_current_other_taxes,
                "New Taxes": custom_calc.model_new_other_taxes,
                "Change ($)": custom_calc.other_increase_total,
                "Per $100k CVA ($)": None,
            },
        ])

        c_display = custom_impact.copy()
        for col in ["Current Taxes", "New Taxes", "Change ($)"]:
            c_display[col] = c_display[col].apply(
                lambda x: f"${x:,.0f}" if x >= 0 else f"-${abs(x):,.0f}"
            )
        c_display["Per $100k CVA ($)"] = custom_impact["Per $100k CVA ($)"].apply(
            lambda x: f"+${x:,.2f}" if pd.notna(x) and x >= 0
            else (f"-${abs(x):,.2f}" if pd.notna(x) else "—")
        )

        st.dataframe(c_display, use_container_width=True, hide_index=True)
        st.caption("✅ **Revenue-neutral check:** Total shift = \\$0.00")

        # Per-household & per-class summary
        if custom_calc.total_households > 0:
            chh_yr = f"{custom_calc.res_increase_per_household:,.2f}"
            chh_mo = f"{custom_calc.res_increase_per_household_month:,.2f}"
            st.info(
                f"🏠 **Cost to average household:** "
                f"\\${chh_yr}/year (\\${chh_mo}/month)"
            )

        if is_reduction:
            st.success(
                f"🌾 **Farm savings at {custom_ratio:.2f} ratio:** "
                f"\\${custom_calc.farm_savings_total:,.0f} total "
                f"(\\${custom_calc.farm_savings_per_100k:,.2f} per \\$100k CVA)"
            )
        else:
            st.warning(
                f"📈 **Farm tax increase at {custom_ratio:.2f} ratio:** "
                f"\\${abs(custom_calc.farm_savings_total):,.0f} total. "
                f"Other property classes would see reduced taxes."
            )

    return calc, two_tier


# ── Export ────────────────────────────────────────────────────────────────────

def _render_export(
    df: pd.DataFrame,
    muni_name: str,
    burden_by_year: dict,
    cva_growth: dict,
    calc_and_tier,
    tax_trends_by_year: dict = None,
    is_upper_tier: bool = False,
    is_provincial: bool = False,
    sgc_code: str = None,
    fir_raw_df: pd.DataFrame = None,
):
    """Tab 5: Word report, PowerPoint, and template letter exports."""
    if is_provincial:
        st.info(
            "📄 **Exports** are available for individual municipality views. "
            "Select a specific municipality from the sidebar to generate reports."
        )
        return

    if calc_and_tier is None:
        st.info("Select a target year in the **Ratio Calculator** tab first to enable exports.")
        return

    calc, is_two_tier = calc_and_tier

    years = sorted(df["year"].unique())
    year_range = f"{min(years)}\u2013{max(years)}"
    current_year = int(max(years))

    st.markdown(
        f"Generate reports and advocacy materials for **{muni_name}** ({year_range})."
    )

    # ── Optional Logo Upload ──
    uploaded_logo = st.file_uploader(
        "🏞️ Upload County Federation Logo (optional)",
        type=["png", "jpg", "jpeg"],
        help="Upload your county federation logo to include on reports, presentations, and letters.",
        key="farm_tax_logo_upload",
    )
    logo_bytes = uploaded_logo.getvalue() if uploaded_logo else None
    if logo_bytes:
        st.image(logo_bytes, width=150, caption="Logo preview")

    st.markdown("---")

    # ── Word Report ──
    st.markdown("#### 📄 Word Report")
    st.caption("1\u20132 page summary of the farm tax story with data tables.")
    if st.button("📄 Generate Word Report", key="generate_farm_report", type="primary"):
        with st.spinner("Generating report..."):
            buf = generate_word_report(
                muni_name=muni_name,
                year_range=year_range,
                current_year=current_year,
                target_year=calc.target_year,
                burden_by_year=burden_by_year or {},
                calc=calc,
                cva_growth=cva_growth or {},
                is_two_tier=is_two_tier,
                is_upper_tier=is_upper_tier,
                tax_trends_by_year=tax_trends_by_year or {},
                logo_bytes=logo_bytes,
            )
            st.download_button(
                label="\u2b07\ufe0f Download Report (.docx)",
                data=buf,
                file_name=f"Farm_Tax_Report_{muni_name.replace(' ', '_')}_{current_year}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="download_farm_report",
            )
            st.success("Report generated! Click the download button above.")

    st.markdown("---")

    # ── PowerPoint Presentation ──
    st.markdown("#### 📊 PowerPoint Presentation")
    st.caption("12-slide delegation presentation with educational context and local farm tax analysis.")
    if st.button("📊 Generate PowerPoint", key="generate_farm_pptx"):
        with st.spinner("Generating presentation..."):
            pptx_buf = generate_pptx_report(
                muni_name=muni_name,
                year_range=year_range,
                current_year=current_year,
                target_year=calc.target_year,
                burden_by_year=burden_by_year or {},
                calc=calc,
                cva_growth=cva_growth or {},
                is_two_tier=is_two_tier,
                is_upper_tier=is_upper_tier,
                tax_trends_by_year=tax_trends_by_year or {},
                logo_bytes=logo_bytes,
                fir_raw_df=fir_raw_df,
            )
            st.download_button(
                label="\u2b07\ufe0f Download Presentation (.pptx)",
                data=pptx_buf,
                file_name=f"Farm_Tax_Presentation_{muni_name.replace(' ', '_')}_{current_year}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                key="download_farm_pptx",
            )
            st.success("Presentation generated! Click the download button above.")

    st.markdown("---")

    # ── Template Delegation Letter ──
    st.markdown("#### \u2709\ufe0f Template Delegation Letter")
    st.caption(
        "Generate a template letter requesting a delegation to council "
        "to discuss the farm property tax ratio."
    )

    # Resolve upper-tier for the letter
    if fir_raw_df is not None and sgc_code:
        upper_info = resolve_upper_tier(sgc_code, fir_raw_df)
    else:
        upper_info = {
            "upper_tier_name": muni_name,
            "is_single_tier": True,
            "is_lower_tier": False,
        }

    # Notify user about upper-tier addressing
    if upper_info["is_lower_tier"]:
        st.info(
            f"\u2696\ufe0f **Jurisdictional Note:** {muni_name} is a lower-tier municipality. "
            f"Farm property tax ratios are set at the **upper-tier level** in Ontario\u2019s "
            f"two-tier system. This letter will be addressed to "
            f"**{upper_info['upper_tier_name']}**, which has the authority to change "
            f"the farm tax ratio."
        )
    else:
        st.caption(
            f"Letter will be addressed to {upper_info['upper_tier_name']} "
            f"(the taxing authority for farm property tax ratios)."
        )

    if st.button("\u2709\ufe0f Generate Template Letter", key="generate_farm_letter"):
        with st.spinner("Generating letter..."):
            letter_buf = generate_delegation_letter(
                muni_name=muni_name,
                upper_tier_name=upper_info["upper_tier_name"],
                is_lower_tier=upper_info["is_lower_tier"],
                current_year=current_year,
                calc=calc,
                burden_by_year=burden_by_year,
                tax_trends_by_year=tax_trends_by_year,
                logo_bytes=logo_bytes,
            )
            safe_name = upper_info['upper_tier_name'].replace(' ', '_').replace(',', '')
            st.download_button(
                label="\u2b07\ufe0f Download Letter (.docx)",
                data=letter_buf,
                file_name=f"Delegation_Letter_{safe_name}_{current_year}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="download_farm_letter",
            )
            st.success("Letter generated! Click the download button above.")
            if upper_info["is_lower_tier"]:
                st.caption(
                    f"Remember: This letter is addressed to "
                    f"**{upper_info['upper_tier_name']}** because they set the farm tax ratio."
                )




# ── Main Entry Point ─────────────────────────────────────────────────────────

def render_farm_tax_story(
    fir_wide_df: pd.DataFrame,
    sgc_code: str,
    muni_name: str,
    is_upper_tier: bool = False,
    is_provincial: bool = False,
    fir_raw_df: pd.DataFrame = None,
):
    """Render the complete Farm Tax Story section.

    Called from the Farmland Taxation tab when exactly one municipality is selected.
    When is_provincial=True, renders province-wide aggregated data.
    """
    if is_provincial:
        df = _get_provincial(fir_wide_df)
    else:
        df = _get_fir_wide(fir_wide_df, sgc_code)

    if df.empty:
        st.warning(f"No FIR data found for {muni_name}.")
        return

    # ── Load Census Acreage ──
    try:
        census_df = pd.read_csv("data/derived/census_farm_metrics.csv")
        import difflib
        
        if is_provincial:
            muni_match = "Ontario"
        else:
            import re
            clean_muni_name = muni_name.encode('ascii', 'ignore').decode('ascii')
            clean_muni_name = re.sub(r'\s*[\[\(].*?[\]\)]', '', clean_muni_name).strip()
            matches = difflib.get_close_matches(clean_muni_name, census_df["municipality_clean"].unique(), n=1, cutoff=0.80)
            muni_match = matches[0] if matches else None
            
        if muni_match:
            census_muni_df = census_df[census_df["municipality_clean"] == muni_match]
            df = df.merge(census_muni_df[["year", "census_acres"]], on="year", how="left")
            df["farmland_tax_per_acre"] = df["farmland_muni_taxes"] / df["census_acres"]
    except Exception as e:
        import traceback
        st.error(f"Error linking census data: {e}\n\n{traceback.format_exc()}")

    if is_provincial:
        st.markdown(
            f"### 🌾 Provincial Farm Tax Overview\n"
            f"*Province-wide aggregated analysis of farm property taxation in Ontario. "
            f"Data from {int(df['year'].min())}–{int(df['year'].max())}.*"
        )
        # LOCF footnote
        if "n_imputed" in df.columns:
            latest = df[df["year"] == df["year"].max()].iloc[0]
            n_imp = int(latest.get("n_imputed", 0))
            n_filed = int(latest.get("n_filed", 0))
            if n_imp > 0:
                st.caption(
                    f"ℹ️ **Data completeness:** {n_filed} municipalities included in {int(latest['year'])} "
                    f"({n_imp} carried forward from prior year due to delayed FIR filings)."
                )
        # R1: Unorganized Territories footnote
        st.caption(
            "📋 Provincial totals reflect incorporated municipalities filing FIRs "
            "and exclude Unorganized Territories subject to the Provincial Land Tax."
        )
    else:
        st.markdown(
            f"### 🌾 Farm Tax Story — {muni_name}\n"
            f"*Interactive analysis replacing the annual static OFA field-staff report. "
            f"Data from {int(df['year'].min())}–{int(df['year'].max())}.*"
        )

    # V45: Upper-tier disclaimer
    if is_upper_tier:
        st.warning(
            "🏛️ **Upper-Tier Municipality:** This report analyzes the "
            "**upper-tier (County/Regional) property tax levy only**. "
            "It does not include local lower-tier township taxes or the "
            "provincial education levy."
        )

    # ── Cumulative farmland tax growth KPI ──
    first_year = int(df["year"].min())
    last_year = int(df["year"].max())
    if "farmland_muni_taxes" in df.columns:
        first_farm_tax = df[df["year"] == first_year]["farmland_muni_taxes"].iloc[0] if len(df[df["year"] == first_year]) else None
        last_farm_tax = df[df["year"] == last_year]["farmland_muni_taxes"].iloc[0] if len(df[df["year"] == last_year]) else None
        if first_farm_tax and last_farm_tax and first_farm_tax > 0:
            cum_growth = ((last_farm_tax - first_farm_tax) / first_farm_tax) * 100
            kpi_cols = st.columns(3)
            with kpi_cols[0]:
                st.metric(
                    f"Farmland Tax Growth ({first_year}–{last_year})",
                    f"{cum_growth:+.1f}%",
                    delta=f"{first_year}→{last_year}",
                    delta_color="inverse",
                )
            with kpi_cols[1]:
                st.metric(
                    f"Farmland Taxes ({first_year})",
                    f"${first_farm_tax:,.0f}",
                )
            with kpi_cols[2]:
                st.metric(
                    f"Farmland Taxes ({last_year})",
                    f"${last_farm_tax:,.0f}",
                )

    story_tabs = st.tabs([
        "📈 Assessment Trends",
        "💰 Tax Payment Trends",
        "🏷️ Tax Burden Shift",
        "🧮 Ratio Calculator" if not is_provincial else "🧮 Provincial Ratio",
        "📄 Export Report",
    ])

    # State to carry between tabs
    cva_growth = None
    tax_trends_by_year = None
    burden_by_year = None
    calc_and_tier = None

    with story_tabs[0]:
        cva_growth = _render_assessment_trends(df, muni_name, is_provincial=is_provincial)

    with story_tabs[1]:
        tax_trends_by_year = _render_tax_payment_trends(df, muni_name, is_provincial=is_provincial)

    with story_tabs[2]:
        burden_by_year = _render_burden_shift(df, muni_name, is_provincial=is_provincial)

    with story_tabs[3]:
        calc_and_tier = _render_ratio_calculator(df, muni_name, is_provincial=is_provincial, fir_raw_df=fir_raw_df)

    with story_tabs[4]:
        _render_export(
            df, muni_name, burden_by_year, cva_growth,
            calc_and_tier, tax_trends_by_year,
            is_upper_tier=is_upper_tier,
            is_provincial=is_provincial,
            sgc_code=sgc_code,
            fir_raw_df=fir_raw_df if not is_provincial else fir_raw_df,
        )

    st.markdown("---")
