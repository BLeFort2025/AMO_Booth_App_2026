"""
Page 17 — 🍎 Tree Fruit Deep Dive
Standalone commodity analysis for Ontario's tree fruit and tender fruit sectors.
Replicates and updates key analyses from JRG Consulting's 2019 Economic Impact Study
using verified public StatCan data.

Data sources (all in Source Data folder):
  - StatCan 32-10-0364: Ontario tree fruit production, area, FGV
  - StatCan 32-10-0054: Per capita food availability (consumption)
  - IO multipliers:      StatCan 36-10-0594 (via standardized CSV)
"""
import sys
import os
from pathlib import Path

# --- PROJECT SETUP ---
current_file = Path(__file__).resolve()
project_root = current_file.parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import altair as alt

from app.smart_read import smart_read
from app.utils import build_share_url, render_source_caption, inject_standalone_mode, show_data_freshness
from app.cpi_utils import apply_cpi_adjustment

# Import the same IO engine used by Page 6 (Economic Impact Multipliers)
from scripts.io_multipliers_engine import (
    compute_impacts,
    compute_breakdown,
    compute_hlrf_breakdown,
    compute_subsidy_impact,
    load_oag_config,
    industries_for_basket,
    available_years as engine_available_years,
    Scope,
)

# ─────────────────────────────────────────────────────────────
# 1. PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Tree Fruit Deep Dive", page_icon="🍎", layout="wide")

from app.utils import inject_standalone_mode, show_data_freshness
inject_standalone_mode()
show_data_freshness()


st.markdown("""
<style>
    .fruit-up { color: #10b981; font-weight: 700; }
    .fruit-down { color: #ef4444; font-weight: 700; }
    .kpi-card {
        background: var(--secondary-background-color);
        border-radius: 12px; padding: 16px; margin: 4px;
    }
    .source-badge {
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 0.75rem; background: var(--secondary-background-color); color: var(--primary-color);
    }
    .jrg-badge {
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 0.75rem; background: var(--secondary-background-color); color: var(--primary-color);
    }
</style>
""", unsafe_allow_html=True)

# Colour palette — warm, fruit-themed
COLOURS = {
    "apple_red": "#c62828",
    "apple_green": "#2e7d32",
    "peach": "#ff8f00",
    "pear": "#9e9d24",
    "plum": "#6a1b9a",
    "cherry": "#ad1457",
    "grape": "#4527a0",
    "nectarine": "#ef6c00",
    "primary": "#2e7d32",
    "secondary": "#1565c0",
    "accent": "#d84315",
    "neutral": "#546e7a",
}

COMMODITY_COLOURS = {
    "Fresh apples": COLOURS["apple_red"],
    "Fresh peaches": COLOURS["peach"],
    "Fresh pears": COLOURS["pear"],
    "Fresh plums and prune plums": COLOURS["plum"],
    "Fresh nectarines": COLOURS["nectarine"],
    "Fresh apricots": COLOURS["cherry"],
    "Fresh grapes": COLOURS["grape"],
    "Fresh Labrusca grapes": COLOURS["grape"],
    "Fresh vinifera, fresh French hybrid grapes": "#7e57c2",
}

CHART_COLOURS = [
    "#c62828", "#2e7d32", "#ff8f00", "#6a1b9a", "#1565c0",
    "#ad1457", "#ef6c00", "#00838f", "#4527a0", "#9e9d24",
]

# ─────────────────────────────────────────────────────────────
# 2. CONSTANTS & DATA
# ─────────────────────────────────────────────────────────────
# Original StatCan data source URLs
SOURCE_URLS = {
    "production": "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3210036401",
    "consumption": "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3210005401",
    "io_multipliers": "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3610059401",
}

SRC = Path(r"C:\Projects\Farm Finance Stats Dashboard\Reports and supplemental information"
           r"\Economic Impact Multipliers\Reports Generates Using our tool\Ontario"
           r"\Commodity Specific\Apple\Source Data")


@st.cache_data(max_entries=3, show_spinner="Loading production data…")
def load_production():
    fp = SRC / "ontario_tree_fruit_production_2010_2023.csv"
    if not fp.exists():
        return None
    df = smart_read(fp)
    # Clean commodity names
    df["Commodity_Clean"] = df["Commodity"].str.replace(r"\s*\[.*?\]", "", regex=True).str.strip()
    return df


@st.cache_data(max_entries=3, show_spinner="Loading consumption data…")
def load_consumption():
    fp = SRC / "fruit_consumption_per_capita_2004_2023.csv"
    if not fp.exists():
        return None
    return smart_read(fp)


@st.cache_data(max_entries=3, show_spinner="Loading national share data…")
def load_share():
    fp = SRC / "ontario_share_national_production.csv"
    if not fp.exists():
        return None
    df = smart_read(fp)
    df["Commodity_Clean"] = df["Commodity"].str.replace(r"\s*\[.*?\]", "", regex=True).str.strip()
    return df


@st.cache_data(max_entries=3, show_spinner="Loading economic impact data…")
def load_impact():
    fp = SRC / "apple_growing_impact_trend.csv"
    if not fp.exists():
        return None
    return smart_read(fp)


df_prod = load_production()
df_cons = load_consumption()
df_share = load_share()
df_impact = load_impact()
oag_cfg = load_oag_config()

if df_prod is None:
    st.error(
        "⚠️ Tree fruit data not found. Expected CSV files in:\n\n"
        f"`{SRC}`\n\n"
        "Please run the data processing scripts first."
    )
    st.stop()

# ─────────────────────────────────────────────────────────────
# 3. SIDEBAR
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Deep Dive Controls")

    # Commodity selector
    all_commodities = sorted(df_prod["Commodity_Clean"].unique())
    selected_commodity = st.selectbox(
        "Commodity",
        ["All Tree Fruits"] + all_commodities,
        index=0,
    )

    st.divider()

    # Year range
    all_years = sorted(df_prod["Year"].dropna().unique())
    yr_min, yr_max = int(min(all_years)), int(max(all_years))
    year_range = st.slider(
        "Year Range",
        min_value=yr_min, max_value=yr_max,
        value=(max(yr_min, 2012), yr_max),
    )

    st.divider()
    st.markdown("### 📊 Data Sources")
    st.markdown(
        f"- [Production (32-10-0364)]({SOURCE_URLS['production']})\n"
        f"- [Consumption (32-10-0054)]({SOURCE_URLS['consumption']})\n"
        f"- [IO Multipliers (36-10-0594)]({SOURCE_URLS['io_multipliers']})"
    )
    st.caption("🍎 Based on JRG Consulting 2019 Study Framework")

# Filter production data
df_p = df_prod[
    (df_prod["Year"] >= year_range[0]) &
    (df_prod["Year"] <= year_range[1])
].copy()

if selected_commodity != "All Tree Fruits":
    df_p = df_p[df_p["Commodity_Clean"] == selected_commodity]

# ─────────────────────────────────────────────────────────────
# 4. HEADER
# ─────────────────────────────────────────────────────────────
st.title(f"🍎 Ontario Tree Fruit Deep Dive")
st.markdown(f"### {selected_commodity} • {year_range[0]}–{year_range[1]}")
st.markdown("---")

# ─────────────────────────────────────────────────────────────
# 5. TABS
# ─────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Production Overview",
    "🍽️ Consumption Trends",
    "💰 Economic Impact",
    "🍑 Tender Fruit Profile",
    "📖 Methodology & Sources",
])


# =============================================================================
# TAB 1: PRODUCTION OVERVIEW
# =============================================================================
with tab1:
    # --- KPI CARDS ---
    latest_yr = int(df_p["Year"].max())
    prev_yr = latest_yr - 1

    df_latest = df_p[df_p["Year"] == latest_yr]
    df_prev = df_p[df_p["Year"] == prev_yr]

    total_fgv_latest = df_latest["Farm_Gate_Value_CAD"].sum()
    total_fgv_prev = df_prev["Farm_Gate_Value_CAD"].sum() if not df_prev.empty else 0
    total_prod_latest = df_latest["Production_Marketed_Tonnes"].sum()
    total_prod_prev = df_prev["Production_Marketed_Tonnes"].sum() if not df_prev.empty else 0

    cols = st.columns(4)
    with cols[0]:
        fgv_delta = (
            ((total_fgv_latest - total_fgv_prev) / total_fgv_prev * 100)
            if total_fgv_prev > 0 else None
        )
        st.metric(
            f"Farm Gate Value ({latest_yr})",
            f"${total_fgv_latest / 1000:.1f}M" if total_fgv_latest > 0 else "N/A",
            delta=f"{fgv_delta:+.1f}% YoY" if fgv_delta is not None else None,
        )
    with cols[1]:
        prod_delta = (
            ((total_prod_latest - total_prod_prev) / total_prod_prev * 100)
            if total_prod_prev > 0 else None
        )
        st.metric(
            f"Production ({latest_yr})",
            f"{total_prod_latest:,.0f} MT" if total_prod_latest > 0 else "N/A",
            delta=f"{prod_delta:+.1f}% YoY" if prod_delta is not None else None,
        )
    with cols[2]:
        # Earliest year for growth comparison
        earliest_yr = int(df_p["Year"].min())
        df_earliest = df_p[df_p["Year"] == earliest_yr]
        fgv_earliest = df_earliest["Farm_Gate_Value_CAD"].sum()
        if fgv_earliest > 0 and total_fgv_latest > 0:
            growth = ((total_fgv_latest / fgv_earliest) - 1) * 100
            st.metric(
                f"FGV Growth ({earliest_yr}→{latest_yr})",
                f"{growth:+.0f}%",
            )
        else:
            st.metric("Period Covered", f"{year_range[0]}–{year_range[1]}")
    with cols[3]:
        n_commodities = df_p["Commodity_Clean"].nunique()
        st.metric("Commodities Tracked", f"{n_commodities}")

    st.caption(
        f'<span class="source-badge"><a href="{SOURCE_URLS["production"]}" target="_blank">StatCan 32-10-0364</a></span> '
        f"Values in $000 CAD. Production in metric tonnes. Latest data: **{latest_yr}**.",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # --- PRODUCTION TREND CHART ---
    st.subheader("📈 Farm Gate Value Trend")

    if selected_commodity == "All Tree Fruits":
        # Stacked area by commodity
        fgv_by_comm = df_p.groupby(["Year", "Commodity_Clean"], as_index=False)[
            "Farm_Gate_Value_CAD"
        ].sum()
        fgv_by_comm["FGV_M"] = fgv_by_comm["Farm_Gate_Value_CAD"] / 1000

        # Order by total FGV
        comm_order = (
            fgv_by_comm.groupby("Commodity_Clean")["FGV_M"].sum()
            .sort_values(ascending=False).index.tolist()
        )

        fig_fgv = go.Figure()
        for i, comm in enumerate(comm_order):
            subset = fgv_by_comm[fgv_by_comm["Commodity_Clean"] == comm].sort_values("Year")
            colour = COMMODITY_COLOURS.get(comm, CHART_COLOURS[i % len(CHART_COLOURS)])
            fig_fgv.add_trace(go.Scatter(
                x=subset["Year"], y=subset["FGV_M"],
                mode="lines", name=comm, stackgroup="one",
                line=dict(width=0.5, color=colour),
                fillcolor=colour.replace(")", ", 0.6)").replace("rgb", "rgba") if "rgb" in colour else colour,
                hovertemplate=f"<b>{comm}</b><br>Year: %{{x}}<br>FGV: $%{{y:.1f}}M<extra></extra>",
            ))

        fig_fgv.update_layout(
            template="plotly_white", height=500,
            yaxis_title="Farm Gate Value ($M)",
            legend=dict(orientation="h", y=-0.2, font=dict(size=10)),
            hovermode="x unified",
        )
    else:
        # Single commodity line chart
        comm_data = df_p.groupby("Year", as_index=False)["Farm_Gate_Value_CAD"].sum()
        comm_data["FGV_M"] = comm_data["Farm_Gate_Value_CAD"] / 1000

        fig_fgv = go.Figure()
        fig_fgv.add_trace(go.Scatter(
            x=comm_data["Year"], y=comm_data["FGV_M"],
            mode="lines+markers",
            name=selected_commodity,
            line=dict(color=COLOURS["primary"], width=3),
            marker=dict(size=8),
            fill="tozeroy",
            fillcolor="rgba(46, 125, 50, 0.1)",
            hovertemplate="Year: %{x}<br>FGV: $%{y:.1f}M<extra></extra>",
        ))

        fig_fgv.update_layout(
            template="plotly_white", height=450,
            yaxis_title="Farm Gate Value ($M)",
        )

    st.plotly_chart(fig_fgv, width="stretch")

    st.markdown("---")

    # --- PRODUCTION VOLUME ---
    st.subheader("🏗️ Production Volume (Marketed Tonnes)")

    prod_trend = df_p.dropna(subset=["Production_Marketed_Tonnes"])
    if not prod_trend.empty:
        if selected_commodity == "All Tree Fruits":
            prod_agg = prod_trend.groupby(["Year", "Commodity_Clean"], as_index=False)[
                "Production_Marketed_Tonnes"
            ].sum()

            fig_prod = go.Figure()
            comm_order_prod = (
                prod_agg.groupby("Commodity_Clean")["Production_Marketed_Tonnes"].sum()
                .sort_values(ascending=False).index.tolist()
            )
            for i, comm in enumerate(comm_order_prod):
                subset = prod_agg[prod_agg["Commodity_Clean"] == comm].sort_values("Year")
                colour = COMMODITY_COLOURS.get(comm, CHART_COLOURS[i % len(CHART_COLOURS)])
                fig_prod.add_trace(go.Bar(
                    x=subset["Year"], y=subset["Production_Marketed_Tonnes"],
                    name=comm, marker_color=colour,
                    hovertemplate=f"<b>{comm}</b><br>%{{y:,.0f}} MT<extra></extra>",
                ))
            fig_prod.update_layout(
                barmode="stack", template="plotly_white", height=450,
                yaxis_title="Marketed Production (Tonnes)",
                legend=dict(orientation="h", y=-0.2, font=dict(size=10)),
            )
        else:
            prod_single = prod_trend.groupby("Year", as_index=False)["Production_Marketed_Tonnes"].sum()
            fig_prod = go.Figure()
            fig_prod.add_trace(go.Bar(
                x=prod_single["Year"], y=prod_single["Production_Marketed_Tonnes"],
                marker_color=COLOURS["primary"],
                hovertemplate="Year: %{x}<br>Production: %{y:,.0f} MT<extra></extra>",
            ))
            fig_prod.update_layout(
                template="plotly_white", height=400,
                yaxis_title="Marketed Production (Tonnes)",
            )

        st.plotly_chart(fig_prod, width="stretch")

    st.markdown("---")

    # --- ONTARIO SHARE OF NATIONAL PRODUCTION ---
    st.subheader("🇨🇦 Ontario's Share of National Production")

    if df_share is not None:
        df_s = df_share[
            (df_share["Year"] >= year_range[0]) &
            (df_share["Year"] <= year_range[1])
        ]
        if selected_commodity != "All Tree Fruits":
            df_s = df_s[df_s["Commodity_Clean"] == selected_commodity]

        if not df_s.empty:
            if selected_commodity == "All Tree Fruits":
                # Latest year comparison bar chart
                latest_share = df_s[df_s["Year"] == df_s["Year"].max()]
                latest_share = latest_share.sort_values("Ontario_Share_Pct", ascending=True)

                fig_share = go.Figure()
                colours_share = []
                for _, r in latest_share.iterrows():
                    c = COMMODITY_COLOURS.get(r["Commodity_Clean"], COLOURS["neutral"])
                    colours_share.append(c)

                fig_share.add_trace(go.Bar(
                    y=latest_share["Commodity_Clean"],
                    x=latest_share["Ontario_Share_Pct"],
                    orientation="h",
                    marker_color=colours_share,
                    text=[f"{v:.0f}%" for v in latest_share["Ontario_Share_Pct"]],
                    textposition="outside",
                    hovertemplate="<b>%{y}</b><br>Ontario Share: %{x:.1f}%<extra></extra>",
                ))
                fig_share.update_layout(
                    template="plotly_white", height=350,
                    xaxis_title="Ontario Share of Canadian Production (%)",
                    xaxis=dict(range=[0, 105]),
                    title=f"Latest Year: {int(df_s['Year'].max())}",
                )
                st.plotly_chart(fig_share, width="stretch")
            else:
                # Single commodity trend
                share_trend = df_s.groupby("Year", as_index=False)["Ontario_Share_Pct"].mean()
                fig_share = go.Figure()
                fig_share.add_trace(go.Scatter(
                    x=share_trend["Year"], y=share_trend["Ontario_Share_Pct"],
                    mode="lines+markers",
                    line=dict(color=COLOURS["primary"], width=3),
                    marker=dict(size=8),
                    hovertemplate="Year: %{x}<br>Ontario Share: %{y:.1f}%<extra></extra>",
                ))
                fig_share.update_layout(
                    template="plotly_white", height=400,
                    yaxis_title="Ontario Share (%)",
                    yaxis=dict(range=[0, 100]),
                )
                st.plotly_chart(fig_share, width="stretch")


# =============================================================================
# TAB 2: CONSUMPTION TRENDS
# =============================================================================
with tab2:
    if df_cons is not None:
        st.subheader("🍽️ Per Capita Food Availability Trends")
        st.caption(
            f'Source: <a href="{SOURCE_URLS["consumption"]}" target="_blank">StatCan 32-10-0054</a> '
            '— Food Available (adjusted for retail, household, and cooking losses) · **Canada-level data** '
            '(no provincial breakdown available)',
            unsafe_allow_html=True,
        )
        st.info(
            "⚠️ **Data note**: These figures represent *food availability* (supply-side disappearance data), "
            "not actual dietary consumption. StatCan's food availability tables estimate how much food enters "
            "the Canadian food system per person after adjusting for losses — they are an upper-bound proxy. "
            "No commodity-level consumption survey exists at the provincial level; the Canadian Community "
            "Health Survey (CCHS) measures only frequency of fruit intake, not quantities."
        )

        # Define fruit categories for filtering
        apple_forms = ["Apples fresh", "Apple juice", "Apple sauce",
                       "Apple pie filling", "Apples canned", "Apples dried", "Apples frozen"]
        tender_forms = ["Peaches fresh", "Pears fresh", "Plums total fresh",
                        "Nectarines fresh", "Apricots fresh", "Peaches canned",
                        "Pears canned", "Apricots canned"]
        grape_forms = ["Grapes fresh", "Grape juice"]

        # Filter by selected commodity
        if selected_commodity == "All Tree Fruits":
            cons_filter = apple_forms + tender_forms + grape_forms
            cons_title = "All Tree Fruit"
        elif "apple" in selected_commodity.lower():
            cons_filter = apple_forms
            cons_title = "Apple"
        elif "peach" in selected_commodity.lower():
            cons_filter = [f for f in tender_forms if "peach" in f.lower()]
            cons_title = "Peach"
        elif "pear" in selected_commodity.lower():
            cons_filter = [f for f in tender_forms if "pear" in f.lower()]
            cons_title = "Pear"
        elif "plum" in selected_commodity.lower():
            cons_filter = [f for f in tender_forms if "plum" in f.lower()]
            cons_title = "Plum"
        elif "nectarine" in selected_commodity.lower():
            cons_filter = [f for f in tender_forms if "nectarine" in f.lower()]
            cons_title = "Nectarine"
        elif "apricot" in selected_commodity.lower():
            cons_filter = [f for f in tender_forms if "apricot" in f.lower()]
            cons_title = "Apricot"
        elif "grape" in selected_commodity.lower():
            cons_filter = grape_forms
            cons_title = "Grape"
        else:
            cons_filter = apple_forms + tender_forms + grape_forms
            cons_title = "All Fruit"

        cons_data = df_cons[
            (df_cons["Commodity"].isin(cons_filter)) &
            (df_cons["Year"] >= 2004)
        ].copy()

        if not cons_data.empty:
            # --- Main trend: Fresh fruit consumption ---
            fresh_items = [c for c in cons_filter if "fresh" in c.lower()]
            fresh_data = cons_data[cons_data["Commodity"].isin(fresh_items)]

            if not fresh_data.empty:
                fig_cons = go.Figure()
                for i, comm in enumerate(sorted(fresh_data["Commodity"].unique())):
                    subset = fresh_data[fresh_data["Commodity"] == comm].sort_values("Year")
                    fig_cons.add_trace(go.Scatter(
                        x=subset["Year"], y=subset["Per_Capita_Kg_or_L"],
                        mode="lines+markers",
                        name=comm,
                        line=dict(width=2.5, color=CHART_COLOURS[i % len(CHART_COLOURS)]),
                        marker=dict(size=5),
                        hovertemplate=f"<b>{comm}</b><br>Year: %{{x}}<br>%{{y:.2f}} kg/person<extra></extra>",
                    ))

                fig_cons.update_layout(
                    template="plotly_white", height=500,
                    yaxis_title="Per Capita Food Availability (kg or L / person / year)",
                    legend=dict(orientation="h", y=-0.2),
                    hovermode="x unified",
                    title=f"Fresh {cons_title} — Per Capita Food Availability Trend",
                )
                st.plotly_chart(fig_cons, width="stretch")

                # Change summary
                for comm in sorted(fresh_data["Commodity"].unique()):
                    sub = fresh_data[fresh_data["Commodity"] == comm].sort_values("Year")
                    if len(sub) >= 5:
                        first_val = sub.iloc[0]["Per_Capita_Kg_or_L"]
                        last_val = sub.iloc[-1]["Per_Capita_Kg_or_L"]
                        change = ((last_val / first_val) - 1) * 100 if first_val > 0 else 0
                        arrow = "📉" if change < 0 else "📈"
                        st.markdown(
                            f"{arrow} **{comm}**: {first_val:.2f} → {last_val:.2f} "
                            f"({change:+.1f}% since {int(sub.iloc[0]['Year'])})"
                        )

            st.markdown("---")

            # --- Consumption by form (latest year) ---
            st.subheader(f"📊 {cons_title} Consumption by Form (Latest Year)")

            latest_cons_yr = int(cons_data["Year"].max())
            latest_cons = cons_data[cons_data["Year"] == latest_cons_yr].sort_values(
                "Per_Capita_Kg_or_L", ascending=False
            )

            if not latest_cons.empty:
                fig_form = go.Figure()
                fig_form.add_trace(go.Bar(
                    x=latest_cons["Commodity"],
                    y=latest_cons["Per_Capita_Kg_or_L"],
                    marker_color=[CHART_COLOURS[i % len(CHART_COLOURS)] for i in range(len(latest_cons))],
                    text=[f"{v:.2f}" for v in latest_cons["Per_Capita_Kg_or_L"]],
                    textposition="outside",
                    hovertemplate="<b>%{x}</b><br>%{y:.2f} per person/year<extra></extra>",
                ))
                fig_form.update_layout(
                    template="plotly_white", height=400,
                    yaxis_title="Per Capita (kg or L / person / year)",
                    title=f"Year: {latest_cons_yr}",
                    xaxis_tickangle=-30,
                )
                st.plotly_chart(fig_form, width="stretch")
    else:
        st.warning("Consumption data not available.")


# =============================================================================
# TAB 3: ECONOMIC IMPACT  (uses same engine as Page 6)
# =============================================================================
with tab3:
    st.subheader("💰 Tree Fruit Economic Impact — IO Engine Analysis")
    st.caption(
        f'Uses the **same IO engine** as the Economic Impact Multipliers page (Page 6). '
        f'Source: <a href="{SOURCE_URLS["production"]}" target="_blank">FGV (32-10-0364)</a> × '
        f'<a href="{SOURCE_URLS["io_multipliers"]}" target="_blank">StatCan Multipliers (36-10-0594)</a>',
        unsafe_allow_html=True,
    )

    # --- Engine Configuration ---
    GEO = "Ontario"
    SCOPE: Scope = "direct_indirect_induced"
    # Red Team Fix: Default to within-province scope for Ontario advocacy KPIs
    GEO_SCOPE = "within_province"

    # Determine which basket to use based on commodity selection
    if selected_commodity == "All Tree Fruits" or "apple" in selected_commodity.lower():
        basket_key = "apple_growing"
        impact_label = "Apple Growing"
    elif any(f in selected_commodity.lower() for f in ["peach", "pear", "plum", "nectarine", "apricot"]):
        basket_key = "tender_fruit_growing"
        impact_label = "Tender Fruit Growing"
    else:
        basket_key = "apple_growing"
        impact_label = "Apple Growing"

    # Get the NAICS codes for this basket (engine handles anti-double-counting)
    basket_industries = industries_for_basket(basket_key)
    if not basket_industries.empty:
        join_codes = basket_industries["join_code"].tolist()
    else:
        join_codes = ["111A"]  # Fallback: Crop Production

    st.info(
        f"🔧 **Engine Config**: Basket = `{basket_key}` · "
        f"NAICS codes = {join_codes} · Scope = Total (D+I+I) · "
        f"Geo scope = Within Ontario · "
        f"Anti-double-counting: engine parent-dominance filter active"
    )

    # --- Get FGV data for each year to use as shock values ---
    apple_fgv_data = df_prod[
        (df_prod["Commodity_Clean"].str.contains("apples", case=False, na=False)) &
        (df_prod["Year"] >= year_range[0]) &
        (df_prod["Year"] <= year_range[1]) &
        (df_prod["Farm_Gate_Value_CAD"].notna())
    ].sort_values("Year")

    if apple_fgv_data.empty:
        st.warning("No production data available for the selected filters.")
    else:
        # --- Compute impacts for each year using the engine ---
        engine_years = engine_available_years(GEO)
        impact_records = []

        for _, row in apple_fgv_data.iterrows():
            yr = int(row["Year"])
            fgv_dollars = row["Farm_Gate_Value_CAD"] * 1000  # CSV is in $000 → convert to $

            # Use the closest available multiplier year
            mult_year = yr if yr in engine_years else max([y for y in engine_years if y <= yr], default=max(engine_years))

            # Call the SAME engine function as Page 6
            per_ind, summ = compute_impacts(
                shock=fgv_dollars,
                geo=GEO,
                year=mult_year,
                scope=SCOPE,
                join_codes=join_codes,
                geo_scope=GEO_SCOPE,  # Red Team Fix: within-province for Ontario KPIs
            )

            if summ.empty:
                continue

            record = {"Year": yr, "Multiplier_Year": mult_year, "FGV_M": fgv_dollars / 1e6}
            for _, s in summ.iterrows():
                metric = s["metric"]
                val = s["impact_dollars"]
                if "Output" in metric:
                    record["Economic_Activity_M"] = val / 1e6
                elif "domestic product" in metric.lower() and "market" in metric.lower():
                    record["GDP_M"] = val / 1e6  # Market prices (consistent with Page 6)
                elif "Jobs" in metric:
                    record["Jobs"] = val  # engine already returns FTE count
                elif "wages" in metric.lower() and "salaries" in metric.lower():
                    record["Wages_M"] = val / 1e6

            impact_records.append(record)

        if impact_records:
            impact = pd.DataFrame(impact_records).sort_values("Year")

            # --- KPI CARDS (Red Team: GDP elevated as primary metric) ---
            latest_imp = impact.iloc[-1]

            cols = st.columns(4)
            with cols[0]:
                gdp_val = latest_imp.get("GDP_M", 0)
                st.metric(
                    f"🏆 GDP Value Added ({int(latest_imp['Year'])})",
                    f"${gdp_val:.0f}M" if gdp_val else "N/A",
                )
            with cols[1]:
                econ_val = latest_imp.get("Economic_Activity_M", 0)
                st.metric(
                    f"Gross Output ({int(latest_imp['Year'])})",
                    f"${econ_val:.0f}M" if econ_val else "N/A",
                    help="Gross output includes supply-chain pass-throughs. GDP (value added) is the primary metric.",
                )
            with cols[2]:
                wages_val = latest_imp.get("Wages_M", 0)
                st.metric(
                    f"Wages & Salaries ({int(latest_imp['Year'])})",
                    f"${wages_val:.0f}M" if wages_val else "N/A",
                )
            with cols[3]:
                jobs_val = latest_imp.get("Jobs", 0)
                st.metric(
                    f"Jobs ({int(latest_imp['Year'])})",
                    f"~{int(jobs_val):,}" if jobs_val else "N/A",
                )

            st.markdown("---")

            # --- Value Added (GDP) Trend — Primary Chart ---
            st.subheader("📈 GDP (Value Added) Trend")
            fig_econ = go.Figure()

            if "GDP_M" in impact.columns:
                fig_econ.add_trace(go.Scatter(
                    x=impact["Year"], y=impact["GDP_M"],
                    mode="lines+markers", name="GDP (Value Added)",
                    line=dict(color=COLOURS["primary"], width=3),
                    marker=dict(size=8),
                    fill="tozeroy", fillcolor="rgba(46, 125, 50, 0.08)",
                    hovertemplate="Year: %{x}<br>$%{y:.1f}M<extra></extra>",
                ))
            if "Wages_M" in impact.columns:
                fig_econ.add_trace(go.Scatter(
                    x=impact["Year"], y=impact["Wages_M"],
                    mode="lines+markers", name="Wages & Salaries",
                    line=dict(color=COLOURS["accent"], width=2.5),
                    marker=dict(size=6),
                    hovertemplate="Year: %{x}<br>$%{y:.1f}M<extra></extra>",
                ))
            if "Economic_Activity_M" in impact.columns:
                fig_econ.add_trace(go.Scatter(
                    x=impact["Year"], y=impact["Economic_Activity_M"],
                    mode="lines+markers", name="Gross Output (secondary)",
                    line=dict(color=COLOURS["neutral"], width=1.5, dash="dash"),
                    marker=dict(size=4),
                    hovertemplate="Year: %{x}<br>$%{y:.1f}M<extra></extra>",
                ))

            fig_econ.update_layout(
                template="plotly_white", height=500,
                yaxis_title="$M (Millions CAD)",
                legend=dict(orientation="h", y=-0.15),
                hovermode="x unified",
            )
            st.plotly_chart(fig_econ, width="stretch")

            # --- Jobs Trend ---
            st.subheader("👷 Employment Impact Trend")

            if basket_key == "apple_growing" and "oag_employment_2024" in oag_cfg:
                st.success(
                    "✅ **OAG Calibrated Data**: Employment figures for the latest year have been "
                    "calibrated using ground-truth headcount and wage data provided by the "
                    "Ontario Apple Growers (OAG). Historical years use standard IO estimates."
                )

            if "Jobs" in impact.columns:
                fig_jobs = go.Figure()
                fig_jobs.add_trace(go.Bar(
                    x=impact["Year"], y=impact["Jobs"],
                    marker_color=COLOURS["neutral"],
                    text=[f"~{j:,.0f}" for j in impact["Jobs"]],
                    textposition="outside",
                    hovertemplate="Year: %{x}<br>Jobs (est.): ~%{y:,.0f} FTE<extra></extra>",
                ))
                fig_jobs.update_layout(
                    template="plotly_white", height=400,
                    yaxis_title="Estimated FTE Jobs",
                )
                st.plotly_chart(fig_jobs, width="stretch")

            st.markdown("---")

            # --- Direct / Indirect / Induced Breakdown (latest year) ---
            st.subheader("📊 Impact Breakdown: Direct / Indirect / Induced")

            latest_yr_impact = int(impact.iloc[-1]["Year"])
            latest_fgv_dollars = impact.iloc[-1]["FGV_M"] * 1e6
            latest_mult_yr = int(impact.iloc[-1]["Multiplier_Year"])

            breakdown = None
            
            # Use HLRF calibration if OAG data is available for this basket
            hlrf_overrides = {}
            if basket_key == "apple_growing" and "oag_employment_2024" in oag_cfg:
                if "growing" in oag_cfg["oag_employment_2024"]:
                    grw = oag_cfg["oag_employment_2024"]["growing"]
                    hlrf_overrides = {
                        "Jobs": grw["ftes"],
                        "Wages and salaries": grw["wages_M"] * 1e6
                    }
                    
            if hlrf_overrides:
                breakdown = compute_hlrf_breakdown(
                    shock=latest_fgv_dollars,
                    geo=GEO,
                    year=latest_mult_yr,
                    join_codes=join_codes,
                    hlrf_overrides=hlrf_overrides,
                )
            else:
                breakdown = compute_breakdown(
                    shock=latest_fgv_dollars,
                    geo=GEO,
                    year=latest_mult_yr,
                    join_codes=join_codes,
                )

            if not breakdown.empty:
                # Pivot for display
                bd_pivot = breakdown.groupby(["metric", "Type"], as_index=False)["impact"].sum()

                # Filter to key metrics
                key_metrics = [
                    m for m in bd_pivot["metric"].unique()
                    if any(kw in m for kw in ["Output", "domestic product", "Jobs", "Wages"])
                ]
                bd_filtered = bd_pivot[bd_pivot["metric"].isin(key_metrics)]

                if not bd_filtered.empty:
                    # Nicer metric labels
                    def shorten_metric(m):
                        if "Output" in m:
                            return "Economic Activity"
                        elif "domestic product" in m.lower():
                            return "GDP"
                        elif "Jobs" in m:
                            return "Jobs"
                        elif "wages" in m.lower() or "salaries" in m.lower():
                            return "Wages & Salaries"
                        return m

                    bd_filtered = bd_filtered.copy()
                    bd_filtered["Metric_Short"] = bd_filtered["metric"].apply(shorten_metric)

                    # Format values for display
                    def fmt_bd(row):
                        if row["Metric_Short"] == "Jobs":
                            return row["impact"]  # Already FTE
                        else:
                            return row["impact"] / 1e6  # Convert to $M

                    bd_filtered["Value"] = bd_filtered.apply(fmt_bd, axis=1)

                    breakdown_colours = {
                        "Direct": "#2e7d32",
                        "Indirect": "#1565c0",
                        "Induced": "#d84315",
                    }

                    fig_bd = go.Figure()
                    for btype in ["Direct", "Indirect", "Induced"]:
                        sub = bd_filtered[bd_filtered["Type"] == btype]
                        if sub.empty:
                            continue
                        fig_bd.add_trace(go.Bar(
                            x=sub["Metric_Short"],
                            y=sub["Value"],
                            name=btype,
                            marker_color=breakdown_colours.get(btype, "#999"),
                            hovertemplate=f"<b>{btype}</b><br>%{{x}}: %{{y:,.1f}}<extra></extra>",
                        ))

                    fig_bd.update_layout(
                        barmode="stack",
                        template="plotly_white",
                        height=450,
                        yaxis_title="$M (or FTE for Jobs)",
                        legend=dict(orientation="h", y=-0.15),
                        title=f"{impact_label} Impact Breakdown ({latest_yr_impact}, mult. year {latest_mult_yr})",
                    )
                    st.plotly_chart(fig_bd, width="stretch")

                    st.caption(
                        "**Direct** = within the farm sector · "
                        "**Indirect** = supply chain (inputs, services) · "
                        "**Induced** = household spending from wages\n\n"
                        "*⚠️ Induced impacts may overstate local spending effects. A significant "
                        "portion of the Ontario orchard workforce consists of Seasonal Agricultural "
                        "Worker Program (SAWP) participants who remit earnings internationally, "
                        "reducing the domestic induced multiplier effect.*"
                    )

            st.markdown("---")

            # --- Government Transfers Addendum ---
            st.subheader("🏛️ Government Transfers Addendum")
            
            if "government_transfers_2024" in oag_cfg:
                gov_cfg = oag_cfg["government_transfers_2024"]
                
                # Select the right transfer data block
                if basket_key == "apple_growing" and "apples" in gov_cfg:
                    tf_data = gov_cfg["apples"]
                elif basket_key == "tender_fruit_growing" and "tender_fruit" in gov_cfg:
                    tf_data = gov_cfg["tender_fruit"]
                else:
                    tf_data = None
                    
                if tf_data:
                    total_transfers = tf_data.get("total_govt_transfers_M", 0) * 1e6
                    pi_M = tf_data.get("production_insurance_M", 0)
                    sdrm_M = tf_data.get("sdrm_M", 0)
                    
                    if total_transfers > 0:
                        st.markdown(
                            f"In addition to market revenue (FGV), the sector received **${total_transfers/1e6:.2f}M** "
                            f"in government transfers (Production Insurance: ${pi_M:.2f}M, SDRM: ${sdrm_M:.2f}M). "
                            f"These payments do not generate supply-chain (Indirect) impacts, but they do generate "
                            f"**Induced impacts** when farmers spend this income in their local communities."
                        )
                        
                        subsidy_bd = compute_subsidy_impact(
                            subsidy_dollars=total_transfers,
                            geo=GEO,
                            year=latest_mult_yr,
                            join_codes=join_codes,
                        )
                        
                        if not subsidy_bd.empty:
                            sub_gdp = subsidy_bd[subsidy_bd["metric"].str.contains("domestic product", case=False, na=False)]["impact"].sum()
                            sub_jobs = subsidy_bd[subsidy_bd["metric"].str.contains("Jobs", case=False, na=False)]["impact"].sum()
                            
                            cols = st.columns(2)
                            with cols[0]:
                                st.metric("Additional GDP (Induced)", f"${sub_gdp/1e6:.1f}M")
                            with cols[1]:
                                st.metric("Additional Jobs (Induced)", f"~{int(sub_jobs)} FTE")
                                
                        with st.expander("📝 Methodology Disclosure: SDRM Allocation"):
                            st.markdown(oag_cfg.get("report_disclosure", "Methodology disclosure not found."))
            else:
                st.info("Government transfer data is not yet configured for this commodity.")

            st.markdown("---")

            # --- JRG Comparison ---
            st.subheader("📋 Comparison vs JRG 2019 Study (2017/18 Baseline)")

            our_1718 = impact[(impact["Year"] >= 2017) & (impact["Year"] <= 2018)]
            our_latest = impact.iloc[-1]

            if not our_1718.empty:
                comp_data = {
                    "Metric": ["GDP ($M)", "Economic Activity ($M)", "Jobs (FTE)†", "Wages ($M)†"],
                    "JRG 2017/18": [163.7, 267.2, 3266, 130.1],
                    f"Our 2017/18 Avg": [
                        our_1718["GDP_M"].mean() if "GDP_M" in our_1718 else 0,
                        our_1718["Economic_Activity_M"].mean() if "Economic_Activity_M" in our_1718 else 0,
                        our_1718["Jobs"].mean() if "Jobs" in our_1718 else 0,
                        our_1718["Wages_M"].mean() if "Wages_M" in our_1718 else 0,
                    ],
                    f"Our {int(our_latest['Year'])}": [
                        our_latest.get("GDP_M", 0),
                        our_latest.get("Economic_Activity_M", 0),
                        our_latest.get("Jobs", 0),
                        our_latest.get("Wages_M", 0),
                    ],
                }
                comp_df = pd.DataFrame(comp_data)

                st.dataframe(
                    comp_df.style.format({
                        "JRG 2017/18": "{:.1f}",
                        f"Our 2017/18 Avg": "{:.1f}",
                        f"Our {int(our_latest['Year'])}": "{:.1f}",
                    }),
                    width="stretch",
                    hide_index=True,
                )

                st.caption(
                    "**†Jobs and Wages are preliminary** — based on NAICS 111A (all crops) multiplier, "
                    "pending calibration with OAG actual headcount data.\n\n"
                    "**Key methodological differences**: "
                    "JRG used an expenditure-based shock ($131.3M incl. government transfers) with "
                    "a proprietary ERL model featuring a custom horticultural labor vector. "
                    "We use an output-based shock (FGV from public StatCan data) with published "
                    "StatCan multipliers. The 33% shock gap reflects excluded government transfers "
                    "(AgriStability, crop insurance). The jobs gap reflects both the shock difference "
                    "and the ERL model's higher labor intensity vs. the diluted 111A average. "
                    "See Methodology tab for full explanation."
                )

            st.markdown("---")

            # =================================================================
            # IMPORT SUBSTITUTION SCENARIO (Pre-built — uses existing public data)
            # =================================================================
            st.subheader("🔄 Import Substitution Scenario: What If Ontario Grew More?")

            # Load consumption data for fresh apples (already loaded as df_cons)
            try:
                if df_cons is not None:
                    apple_fresh_cons = df_cons[
                        df_cons["Commodity"] == "Apples fresh"
                    ].sort_values("Year")
                else:
                    apple_fresh_cons = pd.DataFrame()

                if not apple_fresh_cons.empty:
                    latest_cons = apple_fresh_cons.iloc[-1]
                    latest_cons_yr = int(latest_cons["Year"])
                    per_capita_kg = latest_cons["Per_Capita_Kg_or_L"]

                    # --- CORRECTED: Use Ontario population, not Canada ---
                    ONT_POP_2023 = 15_801_768  # StatCan Q4 2023

                    # Ontario fresh apple consumption (MT)
                    ont_fresh_consumption_mt = per_capita_kg * ONT_POP_2023 / 1000

                    # Ontario production (latest) from df_prod
                    apple_prod = df_prod[
                        df_prod["Commodity_Clean"] == "Fresh apples"
                    ].sort_values("Year")

                    if not apple_prod.empty:
                        latest_prod_row = apple_prod.iloc[-1]
                        ontario_total_prod_mt = latest_prod_row.get("Production_Marketed_Tonnes", 0)
                        if pd.isna(ontario_total_prod_mt) or ontario_total_prod_mt == 0:
                            ontario_total_prod_mt = 148_000  # Fallback avg

                        # --- CORRECTED: Apply fresh pack-out ratio ---
                        # ~70% of Ontario apples go to fresh market (JRG 2019 baseline)
                        FRESH_PACKOUT_PCT = 0.70
                        ontario_fresh_prod_mt = ontario_total_prod_mt * FRESH_PACKOUT_PCT

                        # Ontario self-sufficiency ratio
                        self_sufficiency_pct = (
                            ontario_fresh_prod_mt / ont_fresh_consumption_mt * 100
                        ) if ont_fresh_consumption_mt > 0 else 0

                        # Ontario fresh import gap (properly scoped)
                        import_gap_mt = max(0, ont_fresh_consumption_mt - ontario_fresh_prod_mt)

                        # FGV price per MT (Farm_Gate_Value_CAD is in $000s)
                        latest_fgv_000 = latest_prod_row.get("Farm_Gate_Value_CAD", 0)
                        if pd.isna(latest_fgv_000) or latest_fgv_000 == 0:
                            latest_fgv_000 = 128_000  # Fallback
                        latest_fgv_dollars = latest_fgv_000 * 1000  # $000 → $
                        # Price per MT for fresh apples (higher than processing)
                        price_per_mt = latest_fgv_dollars / ontario_total_prod_mt if ontario_total_prod_mt > 0 else 800

                        # Scenario slider
                        capture_pct = st.slider(
                            "What % of Ontario's fresh apple import gap could local growers capture?",
                            min_value=0, max_value=100, value=25, step=5,
                            key="import_sub_slider",
                            help=(
                                "Slide to model different import substitution scenarios. "
                                "Assumes available agronomic capacity (land, labor, capital) "
                                "to scale production without displacing other crops."
                            ),
                        )

                        additional_mt = import_gap_mt * capture_pct / 100
                        additional_fgv = additional_mt * price_per_mt  # Ontario FGV prices

                        # Run through engine
                        if additional_fgv > 0:
                            _, scenario_summ = compute_impacts(
                                shock=additional_fgv,
                                geo=GEO,
                                year=int(impact.iloc[-1]["Multiplier_Year"]),
                                scope=SCOPE,
                                join_codes=join_codes,
                                geo_scope=GEO_SCOPE,
                            )

                            if not scenario_summ.empty:
                                scenario_results = {}
                                for _, s in scenario_summ.iterrows():
                                    metric = s["metric"]
                                    val = s["impact_dollars"]
                                    if "domestic product" in metric.lower() and "market" in metric.lower():
                                        scenario_results["GDP_M"] = val / 1e6
                                    elif "Output" in metric:
                                        scenario_results["Econ_M"] = val / 1e6
                                    elif "Jobs" in metric:
                                        scenario_results["Jobs"] = val

                                cols_s = st.columns(4)
                                with cols_s[0]:
                                    st.metric(
                                        "Additional Production",
                                        f"{additional_mt:,.0f} MT",
                                        help="Tonnes of additional Ontario fresh apple production to replace imports",
                                    )
                                with cols_s[1]:
                                    st.metric(
                                        "Additional FGV",
                                        f"${additional_fgv/1e6:.1f}M",
                                        help="Valued at Ontario farm-gate prices (not import wholesale prices)",
                                    )
                                with cols_s[2]:
                                    st.metric(
                                        "GDP Prize",
                                        f"${scenario_results.get('GDP_M', 0):.1f}M",
                                    )
                                with cols_s[3]:
                                    st.metric(
                                        "Additional Jobs†",
                                        f"~{int(scenario_results.get('Jobs', 0)):,}",
                                        help="Preliminary (NAICS 111A estimate)",
                                    )

                        st.caption(
                            f"**Ontario Fresh Apple Balance** ({latest_cons_yr}): "
                            f"Estimated Ontario fresh apple demand: ~{ont_fresh_consumption_mt:,.0f} MT "
                            f"(national per-capita food availability of {per_capita_kg:.1f} kg/person × "
                            f"{ONT_POP_2023:,} Ontario population). "
                            f"Ontario growers produce ~{ontario_total_prod_mt:,.0f} MT total, of which "
                            f"~{ontario_fresh_prod_mt:,.0f} MT ({FRESH_PACKOUT_PCT:.0%}) goes to the fresh market. "
                            f"Self-sufficiency: **{self_sufficiency_pct:.0f}%**. "
                            f"Provincial fresh import gap: **{import_gap_mt:,.0f} MT**.\n\n"
                            f"*Ontario demand estimated from national food availability data "
                            f"(StatCan 32-10-0054, adjusted for losses) — no provincial consumption "
                            f"survey exists. Scenario uses Ontario FGV prices (${price_per_mt:,.0f}/MT). "
                            f"Assumes agronomic capacity to scale and static prices "
                            f"(no price elasticity adjustment).*"
                        )
                    else:
                        st.info("Apple production data not available for scenario calculation.")
                else:
                    st.info("Consumption data not available for import substitution scenario.")
            except Exception:
                st.info("Could not load data for import substitution scenario.")

            st.markdown("---")

            # =================================================================
            # FULL VALUE CHAIN IMPACT (Growing + Packing + Processing + Subsidies)
            # =================================================================
            st.subheader("📦 Full Value Chain Economic Impact (2024)")
            
            latest_yr = int(impact.iloc[-1]["Year"])
            value_chain_cfg = oag_cfg.get("value_chain_2024", {})
            packing_margin_M = value_chain_cfg.get("packing_margin_M", 110.8)
            processing_margin_M = value_chain_cfg.get("processing_margin_M", 125.6)
            
            # --- 1. Compute Packing Impact (NAICS 4111) ---
            packing_impact, _ = compute_impacts(
                shock=packing_margin_M * 1_000_000,
                geo="Ontario",
                year=latest_yr,
                scope="Total",
                join_codes=["4111"],
                geo_scope="within_province"
            )
            
            # --- 2. Compute Processing Impact (NAICS 3114) ---
            processing_impact, _ = compute_impacts(
                shock=processing_margin_M * 1_000_000,
                geo="Ontario",
                year=latest_yr,
                scope="Total",
                join_codes=["3114"],
                geo_scope="within_province"
            )
            
            if not packing_impact.empty and not processing_impact.empty:
                pack_gdp = packing_impact[packing_impact["metric"].str.contains("domestic product", case=False, na=False)]["impact"].sum()
                pack_jobs = packing_impact[packing_impact["metric"].str.contains("Jobs", case=False, na=False)]["impact"].sum()
                pack_wages = packing_impact[packing_impact["metric"].str.contains("Wages", case=False, na=False)]["impact"].sum()
                
                proc_gdp = processing_impact[processing_impact["metric"].str.contains("domestic product", case=False, na=False)]["impact"].sum()
                proc_jobs = processing_impact[processing_impact["metric"].str.contains("Jobs", case=False, na=False)]["impact"].sum()
                proc_wages = processing_impact[processing_impact["metric"].str.contains("Wages", case=False, na=False)]["impact"].sum()

                # Calculate Total Industry
                total_gdp = our_latest.get("GDP_M", 0) * 1e6 + pack_gdp + proc_gdp + (sub_gdp if 'sub_gdp' in locals() else 0)
                total_jobs = our_latest.get("Jobs", 0) + pack_jobs + proc_jobs + (sub_jobs if 'sub_jobs' in locals() else 0)
                total_wages = our_latest.get("Wages_M", 0) * 1e6 + pack_wages + proc_wages
                
                # Render Individual Segment Breakdown
                st.markdown("#### Segment Breakdown (Total Impacts: Direct + Indirect + Induced)")
                b_cols = st.columns(3)
                with b_cols[0]:
                    st.info(f"**🍎 Growing (Calibrated)**\n\nGDP: ${our_latest.get('GDP_M', 0):.1f}M\n\nJobs: {int(our_latest.get('Jobs', 0)):,} FTE\n\nWages: ${our_latest.get('Wages_M', 0):.1f}M")
                with b_cols[1]:
                    st.info(f"**📦 Packing (NAICS 4111)**\n\nGDP: ${pack_gdp/1e6:.1f}M\n\nJobs: {int(pack_jobs):,} FTE\n\nWages: ${pack_wages/1e6:.1f}M")
                with b_cols[2]:
                    st.info(f"**🥫 Processing (NAICS 3114)**\n\nGDP: ${proc_gdp/1e6:.1f}M\n\nJobs: {int(proc_jobs):,} FTE\n\nWages: ${proc_wages/1e6:.1f}M")

                st.markdown("---")
                
                # Render Total Industry Summary
                st.success("### 🏆 Total Ontario Apple Industry Footprint (2024)")
                t_cols = st.columns(3)
                with t_cols[0]:
                    st.metric("Total Industry GDP", f"${total_gdp/1e6:.1f}M")
                with t_cols[1]:
                    st.metric("Total Industry Jobs", f"{int(total_jobs):,} FTE")
                with t_cols[2]:
                    st.metric("Total Industry Wages", f"${total_wages/1e6:.1f}M")
                    
                st.caption(
                    "*Methodology: The full value chain impact aggregates the HLRF-calibrated Growing segment (NAICS 111A) "
                    "with the Net Margin shocks for Packing (NAICS 4111) and Processing (NAICS 3114). "
                    "Government subsidy impacts (if configured) are modeled strictly via induced-only multiplier channels to prevent double-counting. "
                    "Values may not sum perfectly due to rounding.*"
                )
            else:
                st.warning("Could not compute packing or processing impacts.")

            st.warning("Could not compute impacts. Check that multiplier data is available.")


# =============================================================================
# TAB 4: TENDER FRUIT PROFILE
# =============================================================================
with tab4:
    st.subheader("🍑 Ontario Tender Fruit Industry Profile")
    st.caption("Peaches, Nectarines, Pears, Plums, Cherries, Apricots")

    tender_commodities = [
        "Fresh peaches", "Fresh nectarines", "Fresh pears",
        "Fresh plums and prune plums", "Fresh apricots",
    ]

    df_tender = df_prod[
        (df_prod["Commodity_Clean"].isin(tender_commodities)) &
        (df_prod["Year"] >= year_range[0]) &
        (df_prod["Year"] <= year_range[1])
    ].copy()

    if not df_tender.empty:
        # --- KPI: Total tender fruit FGV ---
        latest_tf_yr = int(df_tender["Year"].max())
        tf_latest = df_tender[df_tender["Year"] == latest_tf_yr]
        total_tf_fgv = tf_latest["Farm_Gate_Value_CAD"].sum()

        cols = st.columns(4)
        with cols[0]:
            st.metric(
                f"Total Tender Fruit FGV ({latest_tf_yr})",
                f"${total_tf_fgv / 1000:.1f}M" if total_tf_fgv > 0 else "N/A",
            )
        with cols[1]:
            total_tf_prod = tf_latest["Production_Marketed_Tonnes"].sum()
            st.metric(
                f"Total Production ({latest_tf_yr})",
                f"{total_tf_prod:,.0f} MT" if total_tf_prod > 0 else "N/A",
            )
        with cols[2]:
            n_tf = tf_latest["Commodity_Clean"].nunique()
            st.metric("Commodities", f"{n_tf}")
        with cols[3]:
            # Peach dominance
            peach_fgv = tf_latest[
                tf_latest["Commodity_Clean"].str.contains("peach", case=False)
            ]["Farm_Gate_Value_CAD"].sum()
            if total_tf_fgv > 0:
                st.metric("Peach Share of FGV", f"{peach_fgv / total_tf_fgv * 100:.0f}%")

        st.markdown("---")

        # --- FGV by commodity ---
        st.subheader("💰 Farm Gate Value by Commodity")

        tf_fgv = df_tender.groupby(["Year", "Commodity_Clean"], as_index=False)[
            "Farm_Gate_Value_CAD"
        ].sum()
        tf_fgv["FGV_M"] = tf_fgv["Farm_Gate_Value_CAD"] / 1000

        fig_tf = go.Figure()
        for i, comm in enumerate(tender_commodities):
            subset = tf_fgv[tf_fgv["Commodity_Clean"] == comm].sort_values("Year")
            if subset.empty:
                continue
            colour = COMMODITY_COLOURS.get(comm, CHART_COLOURS[i % len(CHART_COLOURS)])
            fig_tf.add_trace(go.Bar(
                x=subset["Year"], y=subset["FGV_M"],
                name=comm.replace("Fresh ", ""),
                marker_color=colour,
                hovertemplate=f"<b>{comm}</b><br>${{y:.1f}}M<extra></extra>",
            ))

        fig_tf.update_layout(
            barmode="stack", template="plotly_white", height=450,
            yaxis_title="Farm Gate Value ($M)",
            legend=dict(orientation="h", y=-0.2),
        )
        st.plotly_chart(fig_tf, width="stretch")

        st.markdown("---")

        # --- National share for each tender fruit ---
        st.subheader("🇨🇦 Ontario's Dominance in National Tender Fruit Production")

        if df_share is not None:
            tf_share = df_share[
                (df_share["Commodity_Clean"].isin(tender_commodities)) &
                (df_share["Year"] == df_share["Year"].max())
            ].sort_values("Ontario_Share_Pct", ascending=True)

            if not tf_share.empty:
                fig_tf_share = go.Figure()
                for i, (_, r) in enumerate(tf_share.iterrows()):
                    colour = COMMODITY_COLOURS.get(r["Commodity_Clean"], CHART_COLOURS[i])
                    fig_tf_share.add_trace(go.Bar(
                        y=[r["Commodity_Clean"].replace("Fresh ", "")],
                        x=[r["Ontario_Share_Pct"]],
                        orientation="h",
                        marker_color=colour,
                        text=f"{r['Ontario_Share_Pct']:.0f}%",
                        textposition="outside",
                        showlegend=False,
                        hovertemplate=f"<b>{r['Commodity_Clean']}</b><br>"
                                      f"Ontario: {r['Ontario_Production']:,.0f} MT<br>"
                                      f"Canada: {r['Canada_Production']:,.0f} MT<br>"
                                      f"Share: {r['Ontario_Share_Pct']:.1f}%<extra></extra>",
                    ))
                fig_tf_share.update_layout(
                    template="plotly_white", height=300,
                    xaxis_title="Ontario Share of Canadian Production (%)",
                    xaxis=dict(range=[0, 105]),
                    title=f"Year: {int(df_share['Year'].max())}",
                )
                st.plotly_chart(fig_tf_share, width="stretch")

                st.success(
                    "🏆 Ontario produces the vast majority of Canada's tender fruits, "
                    "particularly peaches (78%) and plums (77%). This dominant position "
                    "means Ontario policies directly affect the national supply."
                )
    else:
        st.warning("No tender fruit data available for the selected year range.")


# =============================================================================
# TAB 5: METHODOLOGY & SOURCES
# =============================================================================
with tab5:
    st.subheader("📖 Methodology & Data Sources")

    st.markdown(f"""
    ### Data Sources

    | Source | StatCan Table | Content | Coverage |
    |---|---|---|---|
    | **Production** | [32-10-0364]({SOURCE_URLS['production']}) | Area, production, FGV, prices | 1926–2025 |
    | **Consumption** | [32-10-0054]({SOURCE_URLS['consumption']}) | Per capita food availability | 1960–2023 |
    | **IO Multipliers** | [36-10-0594]({SOURCE_URLS['io_multipliers']}) | Economic impact multipliers | 2010–2022 |

    > All data is publicly available from Statistics Canada. Click table numbers above to access original data.

    ### Economic Impact Methodology

    **Our Approach (Output-Based, Growing Segment):**
    - Shock input = Farm Gate Value (marketed output) from [32-10-0364]({SOURCE_URLS['production']})
    - Multiplied by StatCan published Total multipliers (D+I+I) from [36-10-0594]({SOURCE_URLS['io_multipliers']})
    - NAICS 111A (Crop Production) for the growing segment
    - Geo scope: **Within Ontario** (provincial impacts only)
    - Primary metric: **GDP (Value Added)** — not Gross Output

    **JRG Consulting (Expenditure-Based):**
    - Shock input = Total industry expenditure ($131.3M, includes $32.8M in government transfers)
    - Multiplied by ERL proprietary regional multipliers with custom horticultural labor vector
    - Custom model calibrated for Ontario

    ### Key Differences from JRG Study

    | Factor | Impact on Results |
    |---|---|
    | **Shock methodology** | JRG uses 33% larger input ($131.3M vs ~$98.5M FGV) |
    | **Government transfers** | JRG includes AgriStability/crop insurance; ours excluded |
    | **Multiplier model** | ERL custom horticultural labor vector vs. StatCan 111A avg |
    | **GDP / Gross Output** | Within 5–10% when same inputs are used |
    | **Jobs & Wages** | Our 111A estimates are preliminary — pending OAG calibration |

    ### Known Limitations & Planned Fixes

    | Item | Current Status | Planned Resolution |
    |---|---|---|
    | **111A aggregation bias** | NAICS 111A averages all crops; dilutes orchard labor intensity | **HLRF**: Direct Jobs = OAG actual headcount; Indirect = engine (unchanged); Induced = wage-ratio-scaled |
    | **Jobs multiplier decline** | Partly a nominal denominator effect (price inflation ÷ $M), not purely mechanization | Document inflation effect; use HLRF for calibrated employment |
    | **Government transfers** | Excluded from FGV-based shock ($32.8M gap vs JRG) | Model as separate addendum "Induced-only" shock |
    | **SAWP remittances** | Standard Induced multiplier assumes local spending | Caveat that Induced upper bound due to international remittances ✅ |
    | **Processing shock math** | Currently uses NET expenditure for 3114 | Analysis-by-Parts: gross shock minus upstream apple overlap (Red Team approved ✅) |
    | **Value chain scope-lock** | Composite baskets locked to Direct-only | Remove lock once Analysis-by-Parts is implemented |
    | **Import substitution** | Planned scenario toggle | Must use Ontario FGV prices, not wholesale import prices, to avoid overstating the "prize" |

    ### Double-Counting Avoidance

    For the growing segment (current page), no double-counting risk exists — single
    NAICS code, single shock.

    For the **full value chain** (Growing + Packing + Processing, pending OAG data),
    the planned approach is **Analysis-by-Parts**:
    1. Run Processing at **gross output** through 3114 multiplier → Total footprint (A)
    2. Run the raw apple purchase value through 111A → Total footprint (B)
    3. Processing's unique contribution = A − B

    This avoids the error of applying a NET (margin) shock to a gross-based
    manufacturing multiplier, which would undercount supply chain impacts.

    ### Interpreting the Data

    - **GDP (Value Added)** is the primary footprint metric — it measures new wealth created
    - **Gross Output** is shown as secondary; it includes supply-chain pass-throughs
    - **FGV is in $000 CAD** (divide by 1,000 for millions). Scalar: thousands. UOM: Dollars.
    - **Production is in marketed metric tonnes** (what left the farm; NOT short tons)
    - **Consumption is per capita** (kg or litres per person per year), adjusted for losses
    - **IO impacts use within-province Ontario multipliers** (inter-provincial spillovers excluded)
    - **IO multipliers use 2022 vintage** for years beyond 2022 (latest available from StatCan)
    - **2024-2025 production** data is preliminary/forecast from StatCan
    - **⚠️ Jobs and wages are preliminary** — based on NAICS 111A (all crops), not calibrated for horticulture
    """)

    with st.expander("📋 Full Data File Inventory"):
        st.markdown(f"""
        All source files are located in:
        `{SRC}`

        | File | Rows | Description |
        |---|---|---|
        | `32100364.csv` | ~47K | Raw StatCan production data |
        | `32100054.csv` | ~34K | Raw StatCan consumption data |
        | `ontario_tree_fruit_production_2010_2023.csv` | 569 | Processed production summary |
        | `fruit_consumption_per_capita_2004_2023.csv` | 1,465 | Processed consumption by fruit form |
        | `ontario_share_national_production.csv` | 342 | Ontario vs Canada production share |
        | `apple_growing_impact_trend.csv` | 14 | IO impact analysis (2012-2025) |
        """)

from app.utils import global_footer
global_footer()
