import sys
from pathlib import Path

# --- PROJECT SETUP ---
current_file = Path(__file__).resolve()
project_root = current_file.parents[2]          # app/pages/ → app/ → project root
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.smart_read import smart_read
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

try:
    from scripts.input_cost_engine import (
        InputCostEngine,
        CATEGORY_GROUPS,
        HEADLINE_CATEGORIES,
        VALID_GEOS,
        LIVE_MARKET_TICKERS,
    )
except ImportError:
    st.error("⚠️ Engine not found. Please ensure 'scripts/input_cost_engine.py' exists.")
    st.stop()

# -----------------------------------------------------------------------------
# 1. PAGE CONFIG
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Farm Input Cost Tracker", page_icon="📈", layout="wide")

from app.utils import inject_standalone_mode, show_data_freshness
inject_standalone_mode()
show_data_freshness(
    table_ids=["18-10-0258-01"],
    source_labels={"18-10-0258-01": "Farm Input Price Index"},
)


st.markdown("""
<style>
    .kpi-up { color: #ef4444; font-weight: 700; }
    .kpi-down { color: #10b981; font-weight: 700; }
    .kpi-flat { color: var(--text-color); font-weight: 700; }
    .source-badge {
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 0.75rem; background: var(--secondary-background-color); color: var(--primary-color);
    }
</style>
""", unsafe_allow_html=True)

# Colour palette for chart lines
CHART_COLOURS = [
    "#2e7d32", "#1565c0", "#d84315", "#6a1b9a", "#f9a825",
    "#00838f", "#ad1457", "#4e342e", "#37474f", "#558b2f",
]

# -----------------------------------------------------------------------------
# 2. LOAD ENGINE (cached)
# -----------------------------------------------------------------------------
@st.cache_resource(ttl=3600, show_spinner="Loading Farm Input Price Index data…")
def load_engine():
    return InputCostEngine()


try:
    engine = load_engine()
except Exception as e:
    st.error(f"⚠️ Failed to load FIPI data: {e}")
    st.stop()

# -----------------------------------------------------------------------------
# 3. SIDEBAR
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Input Cost Controls")

    selected_geo = st.selectbox(
        "Select Region",
        [g for g in VALID_GEOS if g in engine.available_geos],
        index=([g for g in VALID_GEOS if g in engine.available_geos].index("Ontario")
               if "Ontario" in engine.available_geos else 0),
    )

    st.divider()

    # Category selection with group-based defaults
    st.subheader("📂 Category Selection")
    group_choice = st.selectbox(
        "Quick Select Group",
        ["Custom"] + list(CATEGORY_GROUPS.keys()),
        index=0,
    )

    if group_choice != "Custom":
        default_cats = CATEGORY_GROUPS[group_choice]
    else:
        default_cats = ["Fertilizer", "Machinery fuel", "Pesticides", "Commercial seed and plant"]

    # Filter to only categories available in data
    available_cats = engine.available_categories
    default_cats = [c for c in default_cats if c in available_cats]

    selected_categories = st.multiselect(
        "Input Categories",
        available_cats,
        default=default_cats,
    )

    st.divider()

    # Date range
    st.subheader("📅 Date Range")
    year_range = st.slider(
        "Year Range",
        min_value=2002,
        max_value=2026,
        value=(2015, 2026),
    )

    st.divider()
    st.caption("📊 Data: StatCan FIPI (18-10-0258)")
    st.caption("🌍 World Bank fertilizer benchmarks")
    st.caption("⚡ Live commodity futures via Yahoo Finance")

# -----------------------------------------------------------------------------
# 4. HEADER
# -----------------------------------------------------------------------------
st.title(f"📈 Farm Input Cost Tracker: {selected_geo}")
st.markdown("### StatCan Farm Input Price Index (FIPI) • Quarterly • Base 2021 = 100")
st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab1, tab6, tab2, tab5, tab3, tab4 = st.tabs([
    "📊 Input Cost Dashboard",
    "⚡ Live Market Signals",
    "⛽ Fuel Focus",
    "🌍 Global Fertilizer Benchmarks",
    "📈 Year-over-Year Analysis",
    "📖 Methodology & Sources",
])

# =============================================================================
# TAB 1: INPUT COST DASHBOARD
# =============================================================================
with tab1:
    # ── KPI Cards ───────────────────────────────────────────────────────
    kpis = engine.get_headline_kpis(geo=selected_geo)

    if kpis:
        cols = st.columns(len(kpis))
        for col, kpi in zip(cols, kpis):
            with col:
                # Friendly label
                label = kpi["category"]
                if label == "Farm input total":
                    label = "All Inputs"
                elif label == "Commercial seed and plant":
                    label = "Seed & Plant"
                elif label == "Machinery fuel":
                    label = "Fuel"

                delta_str = None
                delta_color = "off"
                if kpi["yoy_change"] is not None:
                    delta_str = f"{kpi['yoy_change']:+.1f}% YoY"
                    # For costs: rising = bad (inverse)
                    delta_color = "inverse"

                st.metric(
                    label=f"{label} ({kpi['quarter_label']})",
                    value=f"{kpi['value']:.1f}",
                    delta=delta_str,
                    delta_color=delta_color,
                )

        st.caption("Index values (2021 = 100). ▲ Rising costs shown in red, ▼ falling costs in green.")
    else:
        st.info("No headline data available for the selected region.")

    st.markdown("---")

    # ── Main Trend Chart ────────────────────────────────────────────────
    if selected_categories:
        st.subheader("📈 Input Cost Trends")

        trend_data = engine.get_multi_category_comparison(
            selected_categories, geo=selected_geo
        )

        # Filter by year range
        trend_data = trend_data[
            (trend_data["date"].dt.year >= year_range[0])
            & (trend_data["date"].dt.year <= year_range[1])
        ]

        if not trend_data.empty:
            fig = go.Figure()

            for i, cat in enumerate(selected_categories):
                cat_df = trend_data[trend_data["category"] == cat]
                colour = CHART_COLOURS[i % len(CHART_COLOURS)]

                fig.add_trace(go.Scatter(
                    x=cat_df["date"],
                    y=cat_df["value"],
                    mode="lines+markers",
                    name=cat,
                    line=dict(color=colour, width=2.5),
                    marker=dict(size=4),
                    hovertemplate=(
                        f"<b>{cat}</b><br>"
                        "Quarter: %{customdata}<br>"
                        "Index: %{y:.1f}<extra></extra>"
                    ),
                    customdata=cat_df["quarter_label"],
                ))

            # Reference line at 100 (base year)
            fig.add_hline(
                y=100, line_dash="dot", line_color="grey",
                annotation_text="Base Year (2021 = 100)",
                annotation_position="bottom right",
            )

            fig.update_layout(
                template="plotly_white",
                hovermode="x unified",
                height=500,
                legend=dict(orientation="h", y=-0.15),
                yaxis_title="Price Index (2021 = 100)",
                xaxis_title="",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No data available for the selected date range.")
    else:
        st.info("Select one or more input categories in the sidebar to display trends.")

    # ── Latest Values Table ─────────────────────────────────────────────
    if selected_categories:
        st.subheader("📋 Latest Index Values")
        try:
            snapshot = engine.get_latest_snapshot(geo=selected_geo)
            display_snap = snapshot[snapshot["category"].isin(selected_categories)]
            if not display_snap.empty:
                st.dataframe(
                    display_snap.style.format({"value": "{:.1f}"}),
                    hide_index=True,
                    use_container_width=True,
                )
        except Exception as e:
            st.warning(f"Could not load snapshot: {e}")


# =============================================================================
# TAB 2: FUEL FOCUS
# =============================================================================
with tab2:
    st.subheader(f"⛽ Fuel & Energy Cost Analysis — {selected_geo}")
    st.markdown("Detailed view of fuel-related input costs from the FIPI index.")

    fuel_cats = ["Machinery fuel"]
    # Also show related comparisons
    fuel_context_cats = [
        "Machinery fuel",
        "Fertilizer",
        "Farm input total",
    ]

    # ── Fuel Trend ──────────────────────────────────────────────────────
    try:
        fuel_trend = engine.get_multi_category_comparison(
            fuel_context_cats, geo=selected_geo
        )
        fuel_trend = fuel_trend[
            (fuel_trend["date"].dt.year >= year_range[0])
            & (fuel_trend["date"].dt.year <= year_range[1])
        ]

        if not fuel_trend.empty:
            fig_fuel = go.Figure()

            fuel_colours = {"Machinery fuel": "#d84315", "Fertilizer": "#1565c0", "Farm input total": "#636363"}
            for cat in fuel_context_cats:
                cat_df = fuel_trend[fuel_trend["category"] == cat]
                fig_fuel.add_trace(go.Scatter(
                    x=cat_df["date"],
                    y=cat_df["value"],
                    mode="lines+markers",
                    name=cat,
                    line=dict(
                        color=fuel_colours.get(cat, "#999"),
                        width=3 if cat == "Machinery fuel" else 1.5,
                        dash="solid" if cat == "Machinery fuel" else "dot",
                    ),
                    marker=dict(size=5 if cat == "Machinery fuel" else 3),
                ))

            fig_fuel.add_hline(y=100, line_dash="dot", line_color="grey")
            fig_fuel.update_layout(
                template="plotly_white",
                hovermode="x unified",
                height=450,
                title="Machinery Fuel vs. Other Input Costs",
                legend=dict(orientation="h", y=-0.15),
                yaxis_title="Price Index (2021 = 100)",
            )
            st.plotly_chart(fig_fuel, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not load fuel trend data: {e}")

    st.markdown("---")

    # ── Ontario Fuel Weekly (if available) ──────────────────────────────
    st.subheader("🏷️ Ontario Weekly Retail Fuel Prices")
    try:
        fuel_csv = Path("data/latest/ontario_fuel_weekly.csv")
        fuel_weekly = smart_read(fuel_csv)
        if not fuel_weekly.empty:
            st.dataframe(fuel_weekly.tail(20), use_container_width=True)
            st.caption("Source: Ontario Data Catalogue — Fuels Price Survey")
        else:
            st.info("Ontario fuel data file is empty.")
    except FileNotFoundError:
        st.info(
            "🔄 Ontario weekly fuel data not yet available. "
            "Run `python scripts/fetch_ontario_fuel.py` to fetch it."
        )
    except Exception as e:
        st.info(f"Ontario fuel data unavailable: {e}")


# =============================================================================
# TAB 5: GLOBAL FERTILIZER BENCHMARKS
# =============================================================================
with tab5:
    st.subheader(f"🌍 Global Fertilizer Benchmark Prices")
    st.markdown(
        "Monthly wholesale prices from the **World Bank Commodity Price Pink Sheet** "
        "(USD/metric tonne). These global benchmarks drive Canadian retail fertilizer costs."
    )

    # ── KPI Cards ───────────────────────────────────────────────────────
    fert_kpis = engine.get_fertilizer_kpis()

    if fert_kpis:
        fert_cols = st.columns(len(fert_kpis))
        for col, kpi in zip(fert_cols, fert_kpis):
            with col:
                delta_str = None
                delta_color = "off"
                if kpi["mom_change"] is not None:
                    delta_str = f"{kpi['mom_change']:+.1f}% MoM"
                    delta_color = "inverse"  # rising cost = bad

                st.metric(
                    label=f"{kpi['commodity'].split('(')[0].strip()} ({kpi['date_label']})",
                    value=f"${kpi['price']:,.0f}" if kpi["price"] else "N/A",
                    delta=delta_str,
                    delta_color=delta_color,
                )

        st.caption("Prices in USD/metric tonne. ▲ Rising costs shown in red.")
    else:
        st.info(
            "🔄 Fertilizer benchmark data not yet available. "
            "Run `python scripts/fetch_fertilizer_benchmarks.py` to fetch it."
        )

    st.markdown("---")

    # ── Main Benchmark Trend Chart ──────────────────────────────────────
    benchmarks = engine.get_fertilizer_benchmarks(start_year=year_range[0])

    if benchmarks is not None and not benchmarks.empty:
        # Filter to year range
        benchmarks = benchmarks[
            (benchmarks["date"].dt.year >= year_range[0])
            & (benchmarks["date"].dt.year <= year_range[1])
        ]

        # CAD conversion toggle
        show_cad = st.checkbox("Show prices in CAD", value=False)
        cad_rate = 1.0
        if show_cad:
            try:
                signals = smart_read(Path("data/latest/market_signals.csv")).set_index("ticker")
                if "CAD=X" in signals.index:
                    cad_rate = float(signals.loc["CAD=X", "current_price"])
                    st.caption(f"Using USD/CAD rate: {cad_rate:.4f}")
                else:
                    st.caption("USD/CAD rate not available — showing USD.")
                    show_cad = False
            except Exception:
                st.caption("Market signals not available — showing USD.")
                show_cad = False

        currency_label = "CAD" if show_cad else "USD"

        # Build chart
        from scripts.fetch_fertilizer_benchmarks import FERTILIZER_LABELS

        price_cols = [c for c in benchmarks.columns if c.endswith("_usd")]
        fert_chart_colours = {
            "urea_usd": "#1565c0",
            "dap_usd": "#d84315",
            "tsp_usd": "#6a1b9a",
            "potash_usd": "#2e7d32",
            "phosphate_rock_usd": "#f9a825",
        }

        fig_bench = go.Figure()
        for col in price_cols:
            label = FERTILIZER_LABELS.get(col, col)
            if show_cad:
                label = label.replace("USD", "CAD")

            y_vals = benchmarks[col] * cad_rate if show_cad else benchmarks[col]

            fig_bench.add_trace(go.Scatter(
                x=benchmarks["date"],
                y=y_vals,
                mode="lines",
                name=label,
                line=dict(
                    color=fert_chart_colours.get(col, "#999"),
                    width=2.5,
                ),
            ))

        fig_bench.update_layout(
            template="plotly_white",
            hovermode="x unified",
            height=500,
            title=f"Global Fertilizer Benchmark Prices ({currency_label}/metric tonne)",
            legend=dict(orientation="h", y=-0.15),
            yaxis_title=f"Price ({currency_label}/t)",
            xaxis_title="",
        )
        st.plotly_chart(fig_bench, use_container_width=True)

        st.markdown("---")

        # ── Correlation: Global vs FIPI ─────────────────────────────────
        st.subheader(f"🔗 Global Benchmarks vs. Canadian FIPI — {selected_geo}")
        st.markdown(
            "How do global wholesale fertilizer prices relate to the StatCan "
            "Farm Input Price Index (Fertilizer) for Canadian farmers?"
        )

        merged = engine.get_fertilizer_vs_fipi(
            geo=selected_geo, start_year=year_range[0]
        )

        if merged is not None and not merged.empty:
            fig_corr = go.Figure()

            # Primary Y-axis: Urea (as representative benchmark)
            fig_corr.add_trace(go.Scatter(
                x=merged["date"],
                y=merged["urea_usd"],
                mode="lines",
                name="Urea (USD/t)",
                line=dict(color="#1565c0", width=2.5),
                yaxis="y",
            ))

            # Secondary Y-axis: FIPI Fertilizer index
            fig_corr.add_trace(go.Scatter(
                x=merged["date"],
                y=merged["fipi_fertilizer"],
                mode="lines",
                name=f"FIPI Fertilizer ({selected_geo})",
                line=dict(color="#d84315", width=2.5, dash="dot"),
                yaxis="y2",
            ))

            fig_corr.update_layout(
                template="plotly_white",
                hovermode="x unified",
                height=450,
                title="Global Urea Price vs. Canadian FIPI Fertilizer Index",
                legend=dict(orientation="h", y=-0.15),
                yaxis=dict(title="Urea (USD/t)", side="left"),
                yaxis2=dict(
                    title="FIPI Index (2021=100)",
                    side="right",
                    overlaying="y",
                ),
            )
            st.plotly_chart(fig_corr, use_container_width=True)
            st.caption(
                "The FIPI Fertilizer index (red, dotted) tracks the Canadian "
                "farm-gate cost, while Urea (blue) shows the global wholesale "
                "benchmark. Divergences indicate transport, currency, or "
                "local supply factors."
            )
        else:
            st.info("Correlation data not available for this region.")

    elif fert_kpis is None:
        pass  # Already showed the info message above
    else:
        st.info("No benchmark data available for the selected date range.")


# =============================================================================
# TAB 3: YEAR-OVER-YEAR ANALYSIS
# =============================================================================
with tab3:
    st.subheader(f"📈 Year-over-Year Input Cost Changes — {selected_geo}")

    try:
        yoy = engine.get_yoy_changes(geo=selected_geo)

        if not yoy.empty:
            quarter_label = yoy["quarter_label"].iloc[0]
            st.markdown(f"**Comparing {quarter_label} to the same quarter one year prior.**")

            # ── Horizontal Bar Chart ────────────────────────────────────
            # Colour: red for cost increases, green for decreases
            yoy["colour"] = yoy["yoy_pct"].apply(
                lambda x: "#d62728" if x > 0 else "#2ca02c"
            )

            fig_yoy = go.Figure()
            fig_yoy.add_trace(go.Bar(
                y=yoy["category"],
                x=yoy["yoy_pct"],
                orientation="h",
                marker_color=yoy["colour"],
                text=yoy["yoy_pct"].apply(lambda x: f"{x:+.1f}%"),
                textposition="outside",
            ))

            fig_yoy.update_layout(
                template="plotly_white",
                height=max(400, len(yoy) * 28),
                title=f"Year-over-Year Change by Input Category ({quarter_label})",
                xaxis_title="Change (%)",
                yaxis=dict(autorange="reversed"),
                showlegend=False,
            )
            fig_yoy.add_vline(x=0, line_color="black", line_width=1)
            st.plotly_chart(fig_yoy, use_container_width=True)

            st.markdown("---")

            # ── Summary Metrics ─────────────────────────────────────────
            rising = yoy[yoy["yoy_pct"] > 0]
            falling = yoy[yoy["yoy_pct"] < 0]

            col_r, col_f, col_max = st.columns(3)
            with col_r:
                st.metric("Categories Rising", f"{len(rising)} of {len(yoy)}")
            with col_f:
                st.metric("Categories Falling", f"{len(falling)} of {len(yoy)}")
            with col_max:
                if not yoy.empty:
                    biggest = yoy.iloc[0]
                    st.metric(
                        f"Largest Increase",
                        f"{biggest['yoy_pct']:+.1f}%",
                        delta=biggest["category"],
                        delta_color="off",
                    )

            st.markdown("---")

            # ── Full table ──────────────────────────────────────────────
            st.subheader("📋 Full Year-over-Year Breakdown")
            display_yoy = yoy[["category", "current", "prior", "yoy_pct"]].rename(
                columns={
                    "category": "Input Category",
                    "current": f"Current ({quarter_label})",
                    "prior": "Prior Year",
                    "yoy_pct": "YoY Change (%)",
                }
            )
            st.dataframe(
                display_yoy.style.format({
                    f"Current ({quarter_label})": "{:.1f}",
                    "Prior Year": "{:.1f}",
                    "YoY Change (%)": "{:+.1f}%",
                }),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No year-over-year data available for this region.")

    except Exception as e:
        st.warning(f"Could not compute year-over-year changes: {e}")


# =============================================================================
# TAB 4: METHODOLOGY & SOURCES
# =============================================================================
with tab4:
    st.subheader("📖 Methodology & Data Sources")

    with st.expander("📊 Farm Input Price Index (FIPI)", expanded=True):
        st.markdown("""
### What is the FIPI?

The **Farm Input Price Index** (FIPI) is a quarterly indicator published by
Statistics Canada (table [18-10-0258-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810025801))
that measures changes in the prices of goods and services purchased by farmers
for use in agricultural production.

### Key Properties
| Property | Value |
|----------|-------|
| **Base Year** | 2021 = 100 |
| **Frequency** | Quarterly |
| **Geographic Coverage** | Canada, provinces, Eastern/Western regions |
| **Time Span** | Q1 2002 – present |
| **Categories** | 31 individual input types |

### How to Read the Index
- **100** = Same price level as the 2021 base year
- **120** = Prices are 20% higher than 2021
- **85** = Prices are 15% lower than 2021

### Pass-Through to Farm Budgets
The FIPI tracks **wholesale/aggregate input prices**, not individual farm invoices.
Actual farm-gate prices vary based on:
- Volume discounts and negotiated rebates
- Freight and transportation costs
- Seasonal timing of purchases
- Currency exchange rates (for imported inputs)
        """)

    with st.expander("📂 Input Categories Covered"):
        st.markdown("The FIPI tracks **31 input categories** organized into these groups:")

        for group_name, cats in CATEGORY_GROUPS.items():
            st.markdown(f"**{group_name}**")
            for cat in cats:
                st.markdown(f"- {cat}")

    with st.expander("⛽ Ontario Fuel Price Data"):
        st.markdown("""
### Ontario Fuels Price Survey

Retail fuel prices are published weekly by the Ontario Ministry of Energy, based on
the Fuels Price Survey covering **10 Ontario markets**:

Burlington, Cornwall, Hamilton, Kingston, London, Ottawa, Peterborough,
St. Catharines, Sudbury, Thunder Bay, Toronto, Windsor.

**Fuel types**: Regular gasoline, mid-grade, premium, diesel, auto propane, CNG.

**Source**: [Ontario Data Catalogue — Fuels Price Survey](https://data.ontario.ca/dataset/fuels-price-survey)

> **Note**: This data supplements the FIPI's quarterly "Machinery fuel" index with
> more granular, weekly pricing for Ontario-specific analysis.
        """)

    with st.expander("🌍 World Bank Fertilizer Benchmarks"):
        st.markdown("""
### World Bank Commodity Price "Pink Sheet"

The [World Bank Commodity Markets](https://www.worldbank.org/en/research/commodity-markets)
publishes monthly nominal USD prices for major commodities, including five fertilizer
benchmarks used in this dashboard:

| Commodity | Specification |
|-----------|---------------|
| **Urea** | Eastern Europe, bulk, f.o.b. |
| **DAP** | Di-ammonium Phosphate, US Gulf, f.o.b. |
| **TSP** | Triple Super Phosphate, North Africa, f.o.b. |
| **Potash (KCl)** | Muriate of Potash, standard grade, f.o.b. Vancouver |
| **Phosphate Rock** | Morocco, 70% BPL, contract, f.a.s. Casablanca |

**License**: Creative Commons Attribution 4.0 (CC-BY 4.0)

**Coverage**: Monthly from 1960 to present

> These are **global wholesale benchmarks**, not Ontario retail prices. Canadian
> farm-gate fertilizer costs are influenced by these benchmarks plus transportation,
> currency (USD→CAD), and local dealer margins.
        """)

    with st.expander("🔄 Data Freshness & Update Schedule"):
        st.markdown("""
| Dataset | Update Frequency | Typical Lag |
|---------|-----------------|-------------|
| FIPI (StatCan 18-10-0258) | Quarterly | ~2 months after quarter end |
| Fertilizer Benchmarks (World Bank) | Monthly | ~1 month |
| Ontario Fuel Survey | Weekly (Mondays) | Same week |
| Market Signals (Yahoo Finance) | On-demand | Real-time |

Data is fetched by running:
- `python scripts/fetch_statcan.py` (FIPI)
- `python scripts/fetch_fertilizer_benchmarks.py` (World Bank fertilizer)
- `python scripts/fetch_ontario_fuel.py` (Ontario fuel)
        """)

    with st.expander("📎 Related Dashboard Pages"):
        st.markdown("""
- **Page 7 — Farm Income Forecaster**: Uses oil/gas shock parameters that
  correspond to the same cost pressures tracked here.
- **Page 8 — Growth & Risk Simulator**: Models multi-year impacts of sustained
  input cost changes on farm financial sustainability.
- **Page 14 — AI Research Assistant**: Can query the FIPI data via natural
  language (e.g., "Show me Ontario fertilizer cost trends since 2020").
        """)

    with st.expander("⚡ Live Market Signals"):
        st.markdown("""
### Real-Time Commodity Futures

The **Live Market Signals** tab fetches real-time commodity futures from
Yahoo Finance every 5 minutes. These are the same instruments traded on
CBOT (Chicago Board of Trade) and NYMEX (New York Mercantile Exchange).

| Ticker | Commodity | Why It Matters |
|--------|-----------|---------------|
| `NG=F` | Natural Gas | #1 cost driver for nitrogen fertilizer |
| `CL=F` | Crude Oil (WTI) | Drives diesel/gasoline prices |
| `BZ=F` | Brent Crude | International oil benchmark |
| `ZC=F` | Corn | Key livestock feed input |
| `ZS=F` | Soybeans | Protein feed ingredient |
| `ZW=F` | Wheat | Feed wheat benchmark |
| `CAD=X` | USD/CAD Rate | Currency impact on all imports |

> **Note**: These are futures contract prices, not spot prices.
> They represent market expectations and are leading indicators
> of future farm input costs.
        """)


# =============================================================================
# TAB 6: LIVE MARKET SIGNALS
# =============================================================================
import yfinance as yf

@st.cache_data(max_entries=3, ttl=300, show_spinner="Fetching live commodity data…")
def _fetch_live_signals():
    """Fetch 90-day history for all live market tickers."""
    results = {}
    all_tickers = list(LIVE_MARKET_TICKERS.keys())

    for ticker in all_tickers:
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="3mo")
            if not hist.empty:
                results[ticker] = hist
        except Exception:
            pass

    return results


def _compute_signal_metrics(hist: pd.DataFrame) -> dict:
    """Compute price metrics from yfinance history."""
    if hist.empty:
        return {}

    current = float(hist["Close"].iloc[-1])

    # Daily change
    if len(hist) >= 2:
        prev_close = float(hist["Close"].iloc[-2])
        daily_chg = ((current - prev_close) / prev_close) * 100
    else:
        daily_chg = 0.0

    # 7-day change
    if len(hist) >= 6:
        week_ago = float(hist["Close"].iloc[-6])
        week_chg = ((current - week_ago) / week_ago) * 100
    else:
        week_chg = None

    # 30-day change
    if len(hist) >= 22:
        month_ago = float(hist["Close"].iloc[-22])
        month_chg = ((current - month_ago) / month_ago) * 100
    else:
        month_chg = None

    # 30-day high/low
    recent_30 = hist["Close"].tail(22)
    high_30 = float(recent_30.max())
    low_30 = float(recent_30.min())

    return {
        "current": current,
        "daily_chg": daily_chg,
        "week_chg": week_chg,
        "month_chg": month_chg,
        "high_30": high_30,
        "low_30": low_30,
        "last_date": hist.index[-1].strftime("%b %d, %Y"),
    }


with tab6:
    st.subheader("⚡ Live Commodity Market Signals")
    st.markdown(
        "Real-time futures prices that drive Ontario farm input costs. "
        "Data refreshes every 5 minutes via Yahoo Finance."
    )

    # Fetch data
    live_data = _fetch_live_signals()

    if not live_data:
        st.error(
            "⚠️ Could not fetch live market data. "
            "Please check your internet connection and try again."
        )
    else:
        # ── Timestamp ───────────────────────────────────────────────────
        any_ticker = next(iter(live_data.values()))
        last_ts = any_ticker.index[-1]
        st.caption(f"📡 Last market data: {last_ts.strftime('%B %d, %Y')} • Refreshes every 5 min")

        st.markdown("---")

        # ── KPI Cards by Group ──────────────────────────────────────────
        for group_name in ["Energy", "Grain", "Currency"]:
            group_tickers = {
                t: info for t, info in LIVE_MARKET_TICKERS.items()
                if info["group"] == group_name
            }

            if group_name == "Energy":
                st.markdown("### 🛢️ Energy")
            elif group_name == "Grain":
                st.markdown("### 🌾 Grain Futures")
            elif group_name == "Currency":
                st.markdown("### 💱 Currency")

            cols = st.columns(len(group_tickers))
            for col, (ticker, info) in zip(cols, group_tickers.items()):
                with col:
                    if ticker in live_data:
                        metrics = _compute_signal_metrics(live_data[ticker])
                        if metrics:
                            delta_str = f"{metrics['daily_chg']:+.2f}% today"
                            st.metric(
                                label=info["name"],
                                value=f"${metrics['current']:.2f}",
                                delta=delta_str,
                                delta_color="inverse",
                            )

                            # 30-day context
                            if metrics["month_chg"] is not None:
                                direction = "📈" if metrics["month_chg"] > 0 else "📉"
                                st.caption(
                                    f"{direction} 30-day: {metrics['month_chg']:+.1f}% "
                                    f"| Range: ${metrics['low_30']:.2f}–${metrics['high_30']:.2f}"
                                )

                            # Source link
                            exchange = info.get("exchange", "")
                            source_url = info.get("source_url", "")
                            if source_url:
                                st.caption(
                                    f"[{exchange} via Yahoo Finance ↗]({source_url})"
                                )
                        else:
                            st.metric(label=info["name"], value="N/A")
                    else:
                        st.metric(label=info["name"], value="N/A")
                        st.caption("Data unavailable")

        st.markdown("---")

        # ── 30-Day Sparklines ───────────────────────────────────────────
        st.subheader("📈 30-Day Price Trends")

        sparkline_colours = {
            "Energy": "#d84315",
            "Grain": "#2e7d32",
            "Currency": "#1565c0",
        }

        # Two rows: Energy + Currency, then Grains
        for group_name in ["Energy", "Grain", "Currency"]:
            group_tickers = {
                t: info for t, info in LIVE_MARKET_TICKERS.items()
                if info["group"] == group_name and t in live_data
            }
            if not group_tickers:
                continue

            cols = st.columns(len(group_tickers))
            for col, (ticker, info) in zip(cols, group_tickers.items()):
                with col:
                    hist = live_data[ticker].tail(30)
                    if not hist.empty:
                        fig_spark = go.Figure()
                        fig_spark.add_trace(go.Scatter(
                            x=hist.index,
                            y=hist["Close"],
                            mode="lines",
                            line=dict(
                                color=sparkline_colours.get(group_name, "#999"),
                                width=2,
                            ),
                            fill="tozeroy",
                            fillcolor=sparkline_colours.get(group_name, "#999").replace(")", ",0.1)").replace("rgb", "rgba") if "rgb" in sparkline_colours.get(group_name, "#999") else None,
                            showlegend=False,
                            hovertemplate="%{x|%b %d}: $%{y:.2f}<extra></extra>",
                        ))
                        fig_spark.update_layout(
                            height=150,
                            margin=dict(l=0, r=0, t=25, b=0),
                            title=dict(text=info["name"], font=dict(size=12)),
                            xaxis=dict(showticklabels=False, showgrid=False),
                            yaxis=dict(showticklabels=True, showgrid=False, tickformat="$.2f"),
                            template="plotly_white",
                        )
                        st.plotly_chart(fig_spark, use_container_width=True)

        st.markdown("---")

        # ── Input Cost Pressure Radar ───────────────────────────────────
        st.subheader("🎯 Input Cost Pressure Indicators")
        st.markdown(
            "Based on recent 30-day commodity price trends, here's where "
            "Ontario farmers should expect cost pressure:"
        )

        pressure_data = []
        for ticker, info in LIVE_MARKET_TICKERS.items():
            if ticker in live_data:
                metrics = _compute_signal_metrics(live_data[ticker])
                if metrics and metrics.get("month_chg") is not None:
                    pressure_data.append({
                        "commodity": info["name"],
                        "impact_area": info["impact"],
                        "change_30d": metrics["month_chg"],
                        "description": info["description"],
                    })

        if pressure_data:
            pdf = pd.DataFrame(pressure_data).sort_values("change_30d", ascending=False)

            # Colour-coded summary
            for _, row in pdf.iterrows():
                chg = row["change_30d"]
                if chg > 5:
                    icon = "🔴"
                    severity = "**Upward pressure**"
                elif chg > 2:
                    icon = "🟡"
                    severity = "Mild upward pressure"
                elif chg < -5:
                    icon = "🟢"
                    severity = "**Downward pressure**"
                elif chg < -2:
                    icon = "🟢"
                    severity = "Mild downward pressure"
                else:
                    icon = "⚪"
                    severity = "Stable"

                with st.expander(
                    f"{icon} {row['commodity']} → {row['impact_area']} "
                    f"({chg:+.1f}% in 30 days) — {severity}",
                    expanded=(abs(chg) > 5),
                ):
                    st.markdown(row["description"])

                    # Show current price
                    ticker_match = [
                        t for t, i in LIVE_MARKET_TICKERS.items()
                        if i["name"] == row["commodity"]
                    ]
                    if ticker_match and ticker_match[0] in live_data:
                        m = _compute_signal_metrics(live_data[ticker_match[0]])
                        if m:
                            c1, c2, c3 = st.columns(3)
                            with c1:
                                st.metric("Current", f"${m['current']:.2f}")
                            with c2:
                                st.metric("30-Day High", f"${m['high_30']:.2f}")
                            with c3:
                                st.metric("30-Day Low", f"${m['low_30']:.2f}")
        else:
            st.info("Could not compute pressure indicators.")

        st.markdown("---")

        # ── Source Attribution Footer ───────────────────────────────────
        st.markdown("### 📎 Data Sources")
        st.markdown("""
| Data | Source | Link |
|------|--------|------|
| Commodity Futures | Yahoo Finance (NYMEX / CBOT / ICE) | [finance.yahoo.com](https://finance.yahoo.com/markets/commodities/) |
| Farm Input Price Index | Statistics Canada Table 18-10-0258-01 | [statcan.gc.ca](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810025801) |
| Fertilizer Benchmarks | World Bank Commodity Price Pink Sheet | [worldbank.org](https://www.worldbank.org/en/research/commodity-markets) |
| Ontario Fuel Prices | Ontario Data Catalogue | [data.ontario.ca](https://data.ontario.ca/dataset/fuels-price-survey) |
| Exchange Rate | Yahoo Finance (FOREX) | [CAD=X](https://finance.yahoo.com/quote/CAD%3DX/) |

> **Disclaimer**: Futures prices are delayed ~15 minutes from exchange close.
> These are market indicators for directional insight — not real-time trading data.
> All historical index data sourced from Statistics Canada and the World Bank
> is official and verified against source publications.
        """)

from app.utils import global_footer
global_footer()
