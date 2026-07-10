"""
Canadian Government Finance Dashboard
======================================
Page 18 — Comprehensive view of federal, provincial, municipal, and
consolidated government finances powered by StatCan IO tables and
Bank of Canada benchmark bond yields.
"""
import sys
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ── Path setup ───────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.gov_finance_loader import (
    get_gov_finance_data,
    get_annual_yields,
    fetch_gdp_data,
    extract_kpi,
    extract_time_series,
    extract_breakdown,
    get_available_geos,
    get_available_years,
    REVENUE_PATTERNS,
    EXPENDITURE_PATTERNS,
    SURPLUS_PATTERNS,
    GROSS_DEBT_PATTERNS,
    NET_DEBT_PATTERNS,
    DEBT_CHARGES_PATTERNS,
    REVENUE_BREAKDOWN_PATTERNS,
    EXPENDITURE_BREAKDOWN_PATTERNS,
)

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Government Finance | Agri-Food Dashboard",
    page_icon="🏛️",
    layout="wide",
)

from app.utils import inject_standalone_mode, show_data_freshness
inject_standalone_mode()
show_data_freshness(
    table_ids=["10-10-0020-01", "10-10-0147-01", "10-10-0148-01", "10-10-0149-01", "36-10-0222-01"],
    source_labels={
        "10-10-0020-01": "Public Sector Emp",
        "10-10-0147-01": "Gov Expense",
        "10-10-0148-01": "Gov Debt",
        "10-10-0149-01": "Gov Revenue",
        "36-10-0222-01": "Provincial GDP",
    },
)


# ── Custom Styling ───────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Header styling */
    .gov-header {
        background: var(--primary-color);
        padding: 1.8rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .gov-header h1 {
        margin: 0; font-size: 1.8rem; font-weight: 700; color: white;
    }
    .gov-header p {
        margin: 0.3rem 0 0 0; opacity: 0.85; font-size: 0.95rem; color: white;
    }

    /* KPI card styling */
    .kpi-card {
        background: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .kpi-label {
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: var(--text-color);
        opacity: 0.8;
        margin-bottom: 0.3rem;
    }
    .kpi-value {
        font-size: 1.6rem;
        font-weight: 800;
        color: var(--text-color);
    }
    .kpi-value.positive { color: #10b981; }
    .kpi-value.negative { color: #ef4444; }

    /* Context badge */
    .context-badge {
        display: inline-block;
        background: var(--secondary-background-color);
        color: var(--primary-color);
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-right: 0.5rem;
    }

    /* Section headers */
    .section-title {
        font-size: 1.15rem;
        font-weight: 700;
        color: var(--text-color);
        margin-top: 1.5rem;
        padding-bottom: 0.4rem;
        border-bottom: 2px solid rgba(128, 128, 128, 0.2);
    }
</style>
""", unsafe_allow_html=True)

# ── Plotly template ──────────────────────────────────────────────────────────
PLOTLY_TEMPLATE = "plotly_white"
COLORS = {
    "revenue": "#059669",
    "expenditure": "#dc2626",
    "surplus": "#2563eb",
    "debt": "#7c3aed",
    "interest": "#f59e0b",
}
BREAKDOWN_COLORS = px.colors.qualitative.Set2


# ── Formatting helpers ───────────────────────────────────────────────────────
def fmt_compact(val: float) -> str:
    """Format dollar value compactly."""
    if val == 0:
        return "$0"
    neg = val < 0
    val = abs(val)
    if val >= 1e12:
        s = f"${val/1e12:,.1f}T"
    elif val >= 1e9:
        s = f"${val/1e9:,.1f}B"
    elif val >= 1e6:
        s = f"${val/1e6:,.1f}M"
    elif val >= 1e3:
        s = f"${val/1e3:,.1f}K"
    else:
        s = f"${val:,.0f}"
    return f"-{s}" if neg else s


def fmt_pct(val: float) -> str:
    return f"{val:.2f}%"


# ── Cached data loading ─────────────────────────────────────────────────────
@st.cache_data(max_entries=3, ttl=3600, show_spinner="Fetching government finance data...")
def load_gov_data(level: str) -> pd.DataFrame:
    """Load and cache government finance data for a specific level."""
    return get_gov_finance_data(level)


@st.cache_data(max_entries=3, ttl=3600, show_spinner="Fetching Bank of Canada bond yields...")
def load_boc_yields() -> pd.DataFrame:
    """Load and cache Bank of Canada benchmark bond yields."""
    return get_annual_yields(start_date="1990-01-01")


@st.cache_data(max_entries=3, ttl=3600, show_spinner="Fetching GDP data...")
def load_gdp_data() -> pd.DataFrame:
    """Load and cache nominal GDP data by province."""
    return fetch_gdp_data()


# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="gov-header">
    <h1>🏛️ Canadian Government Finance Dashboard</h1>
    <p>Revenue, expenditure, debt, and interest rate analysis across all levels of government</p>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🏛️ Government Finance")
    st.markdown("---")

    # Level of government
    gov_level = st.selectbox(
        "📊 Level of Government",
        options=["Federal", "Provincial", "Municipal", "Consolidated"],
        index=0,
        help=(
            "**Federal:** Government of Canada finances\n\n"
            "**Provincial:** Provincial/territorial governments\n\n"
            "**Municipal:** Local/municipal governments\n\n"
            "**Consolidated:** All levels combined (avoids double-counting inter-government transfers)"
        ),
    )

    st.markdown("---")

# ── Load data ────────────────────────────────────────────────────────────────
try:
    with st.spinner(f"Loading {gov_level} government data..."):
        df = load_gov_data(gov_level.lower())
except Exception as e:
    st.error(
        f"⚠️ Failed to load {gov_level} government data.\n\n"
        f"This may be due to a Statistics Canada API timeout. "
        f"Please try refreshing the page.\n\n"
        f"Error: {e}"
    )
    st.stop()

if df.empty:
    st.warning("No data returned from Statistics Canada. Please try again later.")
    st.stop()

# ── Dynamic sidebar filters (after data loads) ──────────────────────────────
with st.sidebar:
    # Province filter (only for provincial/municipal)
    available_geos = get_available_geos(df)

    if gov_level.lower() in ("provincial", "municipal") and len(available_geos) > 1:
        selected_geo = st.selectbox(
            "📍 Province / Territory",
            options=available_geos,
            index=0,
        )
    else:
        selected_geo = available_geos[0] if available_geos else "Canada"

    # Year range
    min_yr, max_yr = get_available_years(df)
    year_range = st.slider(
        "📅 Year Range",
        min_value=min_yr, max_value=max_yr,
        value=(max(min_yr, max_yr - 15), max_yr),
    )

    st.markdown("---")
    st.caption(
        f"**Data Source:** Statistics Canada CGFS Tables\n\n"
        f"**Bond Yields:** Bank of Canada Valet API\n\n"
        f"**Scope:** {gov_level} Government"
    )

# ── Filter data by year range ───────────────────────────────────────────────
year_min, year_max = year_range
df_filtered = df[(df["year"] >= year_min) & (df["year"] <= year_max)].copy()

# ── Context banner ───────────────────────────────────────────────────────────
st.markdown(
    f'<div style="margin-bottom:1rem;">'
    f'<span class="context-badge">🏛️ {gov_level}</span>'
    f'<span class="context-badge">📍 {selected_geo}</span>'
    f'<span class="context-badge">📅 {year_min}–{year_max}</span>'
    f'</div>',
    unsafe_allow_html=True
)

# ── KPI Cards ────────────────────────────────────────────────────────────────
latest_year = int(df_filtered["year"].max()) if not df_filtered.empty else max_yr

revenue = extract_kpi(df_filtered, REVENUE_PATTERNS, geo=selected_geo, year=latest_year)
expenditure = extract_kpi(df_filtered, EXPENDITURE_PATTERNS, geo=selected_geo, year=latest_year)
surplus = revenue - expenditure if (revenue > 0 and expenditure > 0) else extract_kpi(df_filtered, SURPLUS_PATTERNS, geo=selected_geo, year=latest_year)
gross_debt = extract_kpi(df_filtered, GROSS_DEBT_PATTERNS, geo=selected_geo, year=latest_year)
net_debt = extract_kpi(df_filtered, NET_DEBT_PATTERNS, geo=selected_geo, year=latest_year)
debt_charges = extract_kpi(df_filtered, DEBT_CHARGES_PATTERNS, geo=selected_geo, year=latest_year)
eff_rate = (debt_charges / gross_debt * 100) if gross_debt > 0 else 0.0

# ── Load GDP data for ratios ─────────────────────────────────────────────────
try:
    gdp_df = load_gdp_data()
except Exception:
    gdp_df = pd.DataFrame()

# Calculate debt-to-GDP and deficit-to-GDP
latest_gdp = 0.0
if not gdp_df.empty:
    gdp_match = gdp_df[(gdp_df["geo"] == selected_geo) & (gdp_df["year"] == latest_year)]
    if gdp_match.empty and selected_geo != "Canada":
        gdp_match = gdp_df[(gdp_df["geo"].str.contains(selected_geo, case=False, na=False)) & (gdp_df["year"] == latest_year)]
    if not gdp_match.empty:
        latest_gdp = float(gdp_match["gdp"].iloc[0])

debt_to_gdp = (gross_debt / latest_gdp * 100) if latest_gdp > 0 else 0.0
deficit_to_gdp = (abs(surplus) / latest_gdp * 100) if latest_gdp > 0 else 0.0
if surplus >= 0:
    deficit_to_gdp = -deficit_to_gdp  # surplus is a negative deficit

st.markdown(f'<p class="section-title">📊 Key Metrics — {latest_year}</p>', unsafe_allow_html=True)

kpi_cols = st.columns(6)
kpis = [
    ("Total Revenue", fmt_compact(revenue), ""),
    ("Total Expenditures", fmt_compact(expenditure), ""),
    ("Surplus / Deficit", fmt_compact(surplus), "positive" if surplus >= 0 else "negative"),
    ("Gross Debt", fmt_compact(gross_debt), ""),
    ("Net Debt", fmt_compact(net_debt), ""),
    ("Eff. Interest Rate", fmt_pct(eff_rate) if eff_rate > 0 else "N/A", ""),
]

for col, (label, value, css_class) in zip(kpi_cols, kpis):
    with col:
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-value {css_class}">{value}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

# ── GDP Ratio KPI Cards (row 2) ──────────────────────────────────────────────
ratio_cols = st.columns(4)
ratio_kpis = [
    ("Debt-to-GDP", fmt_pct(debt_to_gdp) if latest_gdp > 0 else "N/A",
     "negative" if debt_to_gdp > 60 else ""),
    ("Deficit-to-GDP", fmt_pct(deficit_to_gdp) if latest_gdp > 0 else "N/A",
     "negative" if deficit_to_gdp > 0 else "positive"),
    ("GDP (Nominal)", fmt_compact(latest_gdp) if latest_gdp > 0 else "N/A", ""),
    ("Debt Charges / GDP", fmt_pct(debt_charges / latest_gdp * 100) if latest_gdp > 0 else "N/A", ""),
]

for col, (label, value, css_class) in zip(ratio_cols, ratio_kpis):
    with col:
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-value {css_class}">{value}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

# ── Visualizations ───────────────────────────────────────────────────────────
st.markdown("---")

tab_trend, tab_rev, tab_exp, tab_rates, tab_gdp = st.tabs([
    "📈 Revenue vs Expenditures",
    "💰 Revenue Breakdown",
    "📋 Expenditure Breakdown",
    "🏦 Interest Rate Comparison",
    "📊 Debt & Deficit to GDP",
])

# ── Tab 1: Revenue vs Expenditures time series ──────────────────────────────
with tab_trend:
    st.markdown(f'<p class="section-title">Revenue vs Expenditures Over Time</p>', unsafe_allow_html=True)

    rev_ts = extract_time_series(df_filtered, REVENUE_PATTERNS, geo=selected_geo)
    exp_ts = extract_time_series(df_filtered, EXPENDITURE_PATTERNS, geo=selected_geo)

    if not rev_ts.empty or not exp_ts.empty:
        fig = go.Figure()

        if not rev_ts.empty:
            fig.add_trace(go.Scatter(
                x=rev_ts["year"], y=rev_ts["value"],
                name="Revenue",
                line=dict(color=COLORS["revenue"], width=3),
                mode="lines+markers",
                marker=dict(size=6),
                hovertemplate="Year: %{x}<br>Revenue: $%{y:,.0f}<extra></extra>",
            ))

        if not exp_ts.empty:
            fig.add_trace(go.Scatter(
                x=exp_ts["year"], y=exp_ts["value"],
                name="Expenditures",
                line=dict(color=COLORS["expenditure"], width=3),
                mode="lines+markers",
                marker=dict(size=6),
                hovertemplate="Year: %{x}<br>Expenditures: $%{y:,.0f}<extra></extra>",
            ))

        # Add surplus/deficit shading
        if not rev_ts.empty and not exp_ts.empty:
            merged = rev_ts.merge(exp_ts, on="year", suffixes=("_rev", "_exp"))
            if not merged.empty:
                merged["surplus"] = merged["value_rev"] - merged["value_exp"]
                fig.add_trace(go.Scatter(
                    x=merged["year"], y=merged["surplus"],
                    name="Surplus/Deficit",
                    fill="tozeroy",
                    line=dict(color=COLORS["surplus"], width=1, dash="dot"),
                    fillcolor="rgba(37, 99, 235, 0.1)",
                    hovertemplate="Year: %{x}<br>Surplus/Deficit: $%{y:,.0f}<extra></extra>",
                ))

        fig.update_layout(
            template=PLOTLY_TEMPLATE,
            height=450,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            yaxis_title="Amount ($)",
            xaxis_title="Year",
            hovermode="x unified",
            margin=dict(t=40, b=40, l=60, r=20),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No revenue/expenditure time-series data available for this selection.")

# ── Tab 2: Revenue Breakdown ────────────────────────────────────────────────
with tab_rev:
    st.markdown(f'<p class="section-title">Revenue Sources Breakdown</p>', unsafe_allow_html=True)

    rev_bd = extract_breakdown(df_filtered, REVENUE_BREAKDOWN_PATTERNS, geo=selected_geo)

    if not rev_bd.empty:
        # Filter to years in range
        rev_bd = rev_bd[(rev_bd["year"] >= year_min) & (rev_bd["year"] <= year_max)]

        if not rev_bd.empty:
            fig_rev = px.bar(
                rev_bd,
                x="year", y="value", color="category",
                barmode="stack",
                color_discrete_sequence=BREAKDOWN_COLORS,
                labels={"value": "Amount ($)", "year": "Year", "category": "Source"},
                hover_data={"value": ":$,.0f"},
            )
            fig_rev.update_layout(
                template=PLOTLY_TEMPLATE,
                height=450,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                margin=dict(t=40, b=40, l=60, r=20),
            )
            st.plotly_chart(fig_rev, use_container_width=True)
        else:
            st.info("No revenue breakdown data available for this selection.")
    else:
        st.info("No revenue breakdown data available for this selection.")

# ── Tab 3: Expenditure Breakdown ────────────────────────────────────────────
with tab_exp:
    st.markdown(f'<p class="section-title">Expenditure Line Items</p>', unsafe_allow_html=True)

    exp_bd = extract_breakdown(df_filtered, EXPENDITURE_BREAKDOWN_PATTERNS, geo=selected_geo)

    if not exp_bd.empty:
        exp_bd = exp_bd[(exp_bd["year"] >= year_min) & (exp_bd["year"] <= year_max)]

        if not exp_bd.empty:
            fig_exp = px.bar(
                exp_bd,
                x="year", y="value", color="category",
                barmode="stack",
                color_discrete_sequence=BREAKDOWN_COLORS,
                labels={"value": "Amount ($)", "year": "Year", "category": "Category"},
                hover_data={"value": ":$,.0f"},
            )
            fig_exp.update_layout(
                template=PLOTLY_TEMPLATE,
                height=450,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                margin=dict(t=40, b=40, l=60, r=20),
            )
            st.plotly_chart(fig_exp, use_container_width=True)
        else:
            st.info("No expenditure breakdown data available for this selection.")
    else:
        st.info("No expenditure breakdown data available for this selection.")

# ── Tab 4: Interest Rate Comparison ─────────────────────────────────────────
with tab_rates:
    st.markdown(f'<p class="section-title">Effective Interest Rate vs Benchmark Bond Yields</p>', unsafe_allow_html=True)

    # Calculate effective interest rate time series
    debt_ts = extract_time_series(df_filtered, GROSS_DEBT_PATTERNS, geo=selected_geo)
    charges_ts = extract_time_series(df_filtered, DEBT_CHARGES_PATTERNS, geo=selected_geo)

    eff_rate_ts = pd.DataFrame()
    if not debt_ts.empty and not charges_ts.empty:
        rate_merged = charges_ts.merge(debt_ts, on="year", suffixes=("_charges", "_debt"))
        rate_merged = rate_merged[rate_merged["value_debt"] > 0]
        if not rate_merged.empty:
            rate_merged["eff_rate"] = rate_merged["value_charges"] / rate_merged["value_debt"] * 100
            eff_rate_ts = rate_merged[["year", "eff_rate"]]

    # Load BoC yields
    try:
        boc_yields = load_boc_yields()
    except Exception:
        boc_yields = pd.DataFrame()

    if not eff_rate_ts.empty or not boc_yields.empty:
        fig_rates = go.Figure()

        # Effective rate
        if not eff_rate_ts.empty:
            fig_rates.add_trace(go.Scatter(
                x=eff_rate_ts["year"], y=eff_rate_ts["eff_rate"],
                name=f"Effective Rate ({gov_level})",
                line=dict(color=COLORS["interest"], width=3),
                mode="lines+markers",
                marker=dict(size=7, symbol="diamond"),
                hovertemplate="Year: %{x}<br>Effective Rate: %{y:.2f}%<extra></extra>",
            ))

        # BoC benchmark yields
        if not boc_yields.empty:
            boc_filtered = boc_yields[
                (boc_yields["year"] >= year_min) & (boc_yields["year"] <= year_max)
            ]
            boc_colors = {"2-Year": "#06b6d4", "5-Year": "#8b5cf6",
                          "10-Year": "#ec4899", "Long-Term": "#64748b"}
            for series_name in boc_filtered["series"].unique():
                s = boc_filtered[boc_filtered["series"] == series_name]
                fig_rates.add_trace(go.Scatter(
                    x=s["year"], y=s["yield_pct"],
                    name=f"BoC {series_name}",
                    line=dict(color=boc_colors.get(series_name, "#999"), width=2, dash="dash"),
                    mode="lines",
                    hovertemplate=f"Year: %{{x}}<br>{series_name} Yield: %{{y:.2f}}%<extra></extra>",
                ))

        fig_rates.update_layout(
            template=PLOTLY_TEMPLATE,
            height=450,
            yaxis_title="Interest Rate (%)",
            xaxis_title="Year",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            hovermode="x unified",
            margin=dict(t=40, b=40, l=60, r=20),
        )
        st.plotly_chart(fig_rates, use_container_width=True)

        st.caption(
            "**Effective Interest Rate** = Debt Servicing Costs ÷ Total Interest-Bearing Debt. "
            "**Benchmark Yields** are annual averages from the Bank of Canada. "
            "When the effective rate exceeds benchmark yields, it suggests the government "
            "is carrying older, higher-rate debt."
        )
    else:
        st.info("No interest rate data available for this selection.")

# ── Tab 5: Debt & Deficit to GDP ─────────────────────────────────────────────
with tab_gdp:
    st.markdown(f'<p class="section-title">Debt & Deficit as % of GDP</p>', unsafe_allow_html=True)

    if not gdp_df.empty:
        # Build time-series of debt-to-GDP and deficit-to-GDP
        debt_ts = extract_time_series(df_filtered, GROSS_DEBT_PATTERNS, geo=selected_geo)
        rev_ts_gdp = extract_time_series(df_filtered, REVENUE_PATTERNS, geo=selected_geo)
        exp_ts_gdp = extract_time_series(df_filtered, EXPENDITURE_PATTERNS, geo=selected_geo)

        # Get GDP for matching geography
        gdp_geo = gdp_df.copy()
        if selected_geo != "Canada":
            geo_match = gdp_geo[gdp_geo["geo"].str.contains(selected_geo, case=False, na=False)]
            if not geo_match.empty:
                gdp_geo = geo_match
            else:
                gdp_geo = gdp_geo[gdp_geo["geo"] == selected_geo]
        else:
            gdp_geo = gdp_geo[gdp_geo["geo"] == "Canada"]

        has_data = False
        fig_gdp = go.Figure()

        # Debt-to-GDP
        if not debt_ts.empty and not gdp_geo.empty:
            debt_gdp_merged = debt_ts.merge(
                gdp_geo[["year", "gdp"]], on="year", how="inner"
            )
            debt_gdp_merged = debt_gdp_merged[debt_gdp_merged["gdp"] > 0]
            if not debt_gdp_merged.empty:
                debt_gdp_merged["ratio"] = debt_gdp_merged["value"] / debt_gdp_merged["gdp"] * 100
                fig_gdp.add_trace(go.Scatter(
                    x=debt_gdp_merged["year"], y=debt_gdp_merged["ratio"],
                    name="Debt-to-GDP",
                    line=dict(color=COLORS["debt"], width=3),
                    mode="lines+markers",
                    marker=dict(size=7),
                    hovertemplate="Year: %{x}<br>Debt-to-GDP: %{y:.1f}%<extra></extra>",
                ))
                has_data = True

        # Deficit-to-GDP
        if not rev_ts_gdp.empty and not exp_ts_gdp.empty and not gdp_geo.empty:
            surplus_ts = rev_ts_gdp.merge(exp_ts_gdp, on="year", suffixes=("_rev", "_exp"))
            surplus_ts["deficit"] = surplus_ts["value_exp"] - surplus_ts["value_rev"]  # positive = deficit
            deficit_gdp_merged = surplus_ts.merge(
                gdp_geo[["year", "gdp"]], on="year", how="inner"
            )
            deficit_gdp_merged = deficit_gdp_merged[deficit_gdp_merged["gdp"] > 0]
            if not deficit_gdp_merged.empty:
                deficit_gdp_merged["ratio"] = deficit_gdp_merged["deficit"] / deficit_gdp_merged["gdp"] * 100
                fig_gdp.add_trace(go.Scatter(
                    x=deficit_gdp_merged["year"], y=deficit_gdp_merged["ratio"],
                    name="Deficit-to-GDP",
                    fill="tozeroy",
                    line=dict(color=COLORS["expenditure"], width=2),
                    fillcolor="rgba(220, 38, 38, 0.1)",
                    hovertemplate="Year: %{x}<br>Deficit-to-GDP: %{y:.1f}%<extra></extra>",
                ))
                has_data = True

        # Debt charges / GDP
        charges_ts_gdp = extract_time_series(df_filtered, DEBT_CHARGES_PATTERNS, geo=selected_geo)
        if not charges_ts_gdp.empty and not gdp_geo.empty:
            charges_merged = charges_ts_gdp.merge(
                gdp_geo[["year", "gdp"]], on="year", how="inner"
            )
            charges_merged = charges_merged[charges_merged["gdp"] > 0]
            if not charges_merged.empty:
                charges_merged["ratio"] = charges_merged["value"] / charges_merged["gdp"] * 100
                fig_gdp.add_trace(go.Scatter(
                    x=charges_merged["year"], y=charges_merged["ratio"],
                    name="Debt Charges / GDP",
                    line=dict(color=COLORS["interest"], width=2, dash="dash"),
                    mode="lines",
                    hovertemplate="Year: %{x}<br>Debt Charges/GDP: %{y:.1f}%<extra></extra>",
                ))
                has_data = True

        if has_data:
            # Add reference line at 60% (common debt sustainability threshold)
            fig_gdp.add_hline(
                y=60, line_dash="dot", line_color="#94a3b8",
                annotation_text="60% (Maastricht threshold)",
                annotation_position="top right",
                annotation_font_size=10,
                annotation_font_color="#64748b",
            )

            fig_gdp.update_layout(
                template=PLOTLY_TEMPLATE,
                height=450,
                yaxis_title="% of GDP",
                xaxis_title="Year",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                hovermode="x unified",
                margin=dict(t=40, b=40, l=60, r=20),
            )
            st.plotly_chart(fig_gdp, use_container_width=True)

            st.caption(
                "**Debt-to-GDP** = Total Liabilities ÷ Nominal GDP. "
                "**Deficit-to-GDP** = (Expenditures − Revenue) ÷ Nominal GDP. Positive values indicate a deficit. "
                "**Debt Charges / GDP** shows the fiscal burden of servicing government debt. "
                "The 60% line represents the Maastricht Treaty threshold used by the EU as a benchmark "
                "for sustainable public debt."
            )
        else:
            st.info("Could not compute GDP ratios. GDP data may not be available for this geography.")
    else:
        st.info("GDP data could not be loaded. Cannot compute debt and deficit ratios.")

# ── Methodology ──────────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("📖 Methodology & Data Sources", expanded=False):
    st.markdown(f"""
### Data Sources

| Source | Table | Description |
|--------|-------|-------------|
| Statistics Canada | 10-10-0149-01 | Federal government — CGFS statement of operations and balance sheet |
| Statistics Canada | 10-10-0148-01 | Provincial/territorial governments |
| Statistics Canada | 10-10-0020-01 | Municipal/local governments |
| Statistics Canada | 10-10-0147-01 | Consolidated government (avoids inter-government transfer double-counting) |
| Statistics Canada | 36-10-0222-01 | GDP, expenditure-based (nominal, for debt/deficit-to-GDP ratios) |
| Bank of Canada | Valet API | Government of Canada benchmark bond yields (2yr, 5yr, 10yr, long-term) |

### Key Metrics

- **Total Revenue / Expenditures:** Drawn from the CGFS statement of operations
- **Surplus/Deficit:** Revenue minus Expenditures
- **Gross Debt:** Total liabilities from the balance sheet
- **Net Debt:** Net financial worth (assets minus liabilities)
- **Effective Interest Rate:** Calculated as debt servicing costs (interest expense) divided by total interest-bearing debt (gross debt). This metric shows the average cost of government borrowing
- **Debt-to-GDP:** Total liabilities as a percentage of nominal GDP. The 60% Maastricht threshold is shown for reference
- **Deficit-to-GDP:** Annual deficit (expenditures minus revenue) as a percentage of nominal GDP
- **Debt Charges / GDP:** Interest expense as a percentage of nominal GDP, measuring the fiscal burden of debt

### Classification System

Government finance statistics follow the **Canadian Government Finance Statistics (CGFS)** framework,
which is aligned with the internationally recognized Government Finance Statistics Manual (GFSM 2014)
published by the International Monetary Fund. This framework provides a standardized classification
of government revenues, expenditures, assets, and liabilities across all levels of government.

### Important Notes

- All dollar values are in **millions of Canadian dollars** as reported by Statistics Canada
- The **consolidated** view eliminates inter-government transfers to avoid double-counting
- Bond yield data from the Bank of Canada represents **market yields** on benchmark securities,
  not the government's cost of new borrowing
- Data availability varies by government level and may lag by 1-2 years
""")

st.caption(
    "📌 Data: Statistics Canada CGFS Tables & Bank of Canada Valet API  |  "
    "Agri-Food Economic Dashboard"
)

from app.utils import global_footer
global_footer()
