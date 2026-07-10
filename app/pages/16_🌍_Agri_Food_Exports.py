"""
Page 16 — 🌍 Agri-Food Exports
Tracks Canadian agricultural and agri-food exports by commodity, destination, and province.
Data source: StatCan Table 12-10-0175-01 (CIMT) filtered to agri-food HS sections.
"""
import datetime
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

# -----------------------------------------------------------------------------
# 1. PAGE CONFIG
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Agri-Food Exports", page_icon="🌍", layout="wide")

from app.utils import inject_standalone_mode, show_data_freshness
inject_standalone_mode()
show_data_freshness(
    table_ids=["12-10-0175-01", "12-10-0163-01"],
    source_labels={
        "12-10-0175-01": "Trade by Province",
        "12-10-0163-01": "Trade by Commodity",
    },
)


st.markdown("""
<style>
    .export-up { color: #10b981; font-weight: 700; }
    .export-down { color: #ef4444; font-weight: 700; }
    .kpi-card {
        background: var(--secondary-background-color);
        border-radius: 12px; padding: 16px; margin: 4px;
    }
    .source-badge {
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 0.75rem; background: var(--secondary-background-color); color: var(--primary-color);
    }
</style>
""", unsafe_allow_html=True)

# Colour palette
COLOURS = {
    "primary": "#1565c0",
    "secondary": "#2e7d32",
    "accent": "#d84315",
    "usa": "#1565c0",
    "china": "#d84315",
    "japan": "#6a1b9a",
    "eu": "#2e7d32",
    "mexico": "#f9a825",
    "india": "#00838f",
    "other": "#78909c",
}

PARTNER_COLOURS = {
    "United States": COLOURS["usa"],
    "China": COLOURS["china"],
    "Japan": COLOURS["japan"],
    "European Union": COLOURS["eu"],
    "Mexico": COLOURS["mexico"],
    "India": COLOURS["india"],
}

CHART_COLOURS = [
    "#1565c0", "#2e7d32", "#d84315", "#6a1b9a", "#f9a825",
    "#00838f", "#ad1457", "#4e342e", "#37474f", "#558b2f",
    "#e65100", "#283593", "#00695c", "#bf360c", "#4a148c",
]

# Province ordering for charts
PROVINCE_ORDER = [
    "Canada", "Ontario", "Quebec", "Alberta", "Saskatchewan",
    "British Columbia", "Manitoba", "New Brunswick",
    "Nova Scotia", "Prince Edward Island",
    "Newfoundland and Labrador", "Northwest Territories",
    "Yukon", "Nunavut",
]

# ISO-3 country codes for choropleth map
_ISO3_MAP = {
    "Algeria": "DZA", "Australia": "AUS", "Belgium": "BEL",
    "Brazil": "BRA", "China": "CHN", "France": "FRA",
    "Germany": "DEU", "Hong Kong": "HKG", "India": "IND",
    "Indonesia": "IDN", "Iraq": "IRQ", "Italy": "ITA",
    "Japan": "JPN", "Mexico": "MEX", "Netherlands": "NLD",
    "Norway": "NOR", "Peru": "PER", "Russian Federation": "RUS",
    "Saudi Arabia": "SAU", "Singapore": "SGP", "South Korea": "KOR",
    "Spain": "ESP", "Switzerland": "CHE", "Taiwan": "TWN",
    "Türkiye": "TUR", "Turkey": "TUR",
    "United Kingdom": "GBR", "United States": "USA",
    # Common alternate spellings
    "U.S.": "USA", "USA": "USA", "UK": "GBR",
    "Republic of Korea": "KOR", "Korea, South": "KOR",
    "People's Republic of China": "CHN",
}

# -----------------------------------------------------------------------------
# 2. LOAD DATA
# -----------------------------------------------------------------------------
@st.cache_data(max_entries=3, show_spinner="Loading agri-food export data…")
def load_export_data():
    """Load the processed agri-food exports dataset (12-10-0175-01)."""
    data_path = Path("data/latest/agrifood_exports.csv")
    try:
        df = smart_read(data_path)
    except FileNotFoundError:
        return None

    if df.empty:
        return None

    # Ensure types
    if "YEAR" in df.columns:
        df["YEAR"] = pd.to_numeric(df["YEAR"], errors="coerce").astype("Int64")
    if "VALUE" in df.columns:
        df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")

    return df


@st.cache_data(max_entries=3, show_spinner="Loading detailed commodity data…")
def load_detailed_commodities():
    """Load the detailed NAPCS commodity dataset (12-10-0163-01)."""
    path = Path("data/latest/agrifood_exports_detailed.parquet")
    if not path.exists():
        # Fall back to CSV
        path = Path("data/latest/agrifood_exports_detailed.csv")
        if not path.exists():
            return None
    try:
        if str(path).endswith(".parquet"):
            df = pd.read_parquet(path)
        else:
            df = smart_read(path)
    except Exception:
        return None
    if df.empty:
        return None
    if "YEAR" in df.columns:
        df["YEAR"] = pd.to_numeric(df["YEAR"], errors="coerce").astype("Int64")
    if "VALUE" in df.columns:
        df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")
    return df


@st.cache_data(max_entries=3, show_spinner=False)
def _detect_incomplete_years():
    """Detect years with fewer than 12 months of source data.

    Returns a dict  {year: n_months}  for every incomplete year found.
    The current calendar year is ALWAYS treated as incomplete, even
    before the raw ZIP can be inspected (defensive default).
    """
    import zipfile

    current_year = datetime.date.today().year
    incomplete: dict[int, int] = {}

    zip_path = Path("data/latest/12100175-eng.zip")
    if zip_path.exists():
        try:
            with zipfile.ZipFile(zip_path) as z:
                data_csv = None
                for name in z.namelist():
                    if name.lower().endswith(".csv") and "metadata" not in name.lower():
                        data_csv = name
                        break
                if data_csv:
                    with z.open(data_csv) as f:
                        # Only read the REF_DATE column for speed
                        ref_dates = pd.read_csv(
                            f, usecols=["REF_DATE"],
                        )
                        ref_dates["_year"] = (
                            ref_dates["REF_DATE"].astype(str).str[:4]
                            .pipe(pd.to_numeric, errors="coerce")
                        )
                        ref_dates["_month"] = (
                            ref_dates["REF_DATE"].astype(str).str[5:7]
                            .pipe(pd.to_numeric, errors="coerce")
                        )
                        months_per_year = (
                            ref_dates.dropna(subset=["_year", "_month"])
                            .groupby("_year")["_month"]
                            .nunique()
                        )
                        for yr, n in months_per_year.items():
                            if n < 12:
                                incomplete[int(yr)] = int(n)
        except Exception:
            pass  # Fall back to calendar-year heuristic below

    # Safety net: if the current year isn't already flagged, add it
    if current_year not in incomplete:
        incomplete[current_year] = datetime.date.today().month - 1 or 1

    return incomplete


INCOMPLETE_YEARS = _detect_incomplete_years()


df_all = load_export_data()
df_detailed = load_detailed_commodities()

if df_all is None or df_all.empty:
    st.error(
        "⚠️ Agri-food export data not found. Please run:\n\n"
        "```\npython scripts/process_agrifood_exports.py\n```\n\n"
        "This will download and process StatCan Tables 12-10-0175-01 and 12-10-0163-01."
    )
    st.stop()

# -----------------------------------------------------------------------------
# 3. DETECT COLUMNS
# -----------------------------------------------------------------------------
def find_col(df, keywords):
    """Find a column by keyword matching."""
    for col in df.columns:
        for kw in keywords:
            if kw.lower() in col.lower():
                return col
    return None

trade_col = find_col(df_all, ["Trade"])
commodity_col = find_col(df_all, ["Harmonized", "HS", "Commodity", "NAPCS"])
partner_col = find_col(df_all, ["Principal trading partner", "Trading partner", "partner"])
geo_col = "GEO" if "GEO" in df_all.columns else None

# -----------------------------------------------------------------------------
# 4. SIDEBAR
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Export Data Controls")

    # ── Incomplete-year toggle ──────────────────────────────────────
    if INCOMPLETE_YEARS:
        _inc_labels = ", ".join(
            f"{yr} ({mo}/12 mo)" for yr, mo in sorted(INCOMPLETE_YEARS.items())
        )
        exclude_incomplete = st.checkbox(
            "Exclude incomplete years",
            value=True,
            help=(
                f"The following years have fewer than 12 months of data and "
                f"would appear misleadingly low on charts: **{_inc_labels}**."
            ),
        )
    else:
        exclude_incomplete = False

    st.divider()

    # Year range
    if "YEAR" in df_all.columns:
        years = sorted(df_all["YEAR"].dropna().unique())
        if exclude_incomplete:
            years = [y for y in years if int(y) not in INCOMPLETE_YEARS]
        yr_min, yr_max = int(min(years)), int(max(years))
        year_range = st.slider(
            "Year Range",
            min_value=yr_min, max_value=yr_max,
            value=(max(yr_min, 2015), yr_max),
        )
    else:
        year_range = (2015, 2025)

    st.divider()

    # Trade flow
    trade_options = ["Exports", "Imports", "Both"]
    trade_flow = st.radio("Trade Flow", trade_options, index=0)

    st.divider()

    # Province filter
    if geo_col:
        all_geos = sorted(df_all[geo_col].dropna().unique().tolist())
        # Remove StatCan indirect-allocation entries (e.g. "... including indirect allocations")
        all_geos = [g for g in all_geos if "including" not in g.lower()]
        # Smart ordering
        ordered_geos = [g for g in PROVINCE_ORDER if g in all_geos]
        ordered_geos += [g for g in all_geos if g not in ordered_geos]

        selected_provinces = st.multiselect(
            "Province(s)",
            ordered_geos,
            default=[g for g in ["Canada"] if g in ordered_geos] or ordered_geos[:1],
        )
    else:
        selected_provinces = []

    st.divider()

    # Data scope toggle
    _has_detailed = df_detailed is not None and not df_detailed.empty
    data_scope = st.radio(
        "Data Scope",
        ["Full Agri-Food", "Primary Agriculture"],
        index=0 if _has_detailed else 1,
        disabled=not _has_detailed,
        help=(
            "**Full Agri-Food** includes all agricultural, food & beverage exports "
            "(NAPCS C11 + C221) from Table 12-10-0163-01 — available at the national "
            "level only. **Primary Agriculture** covers raw & intermediate farm "
            "products (C11) from Table 12-10-0175-01 — available by province and "
            "trading partner."
        ),
    )
    use_full_scope = data_scope == "Full Agri-Food" and _has_detailed

    st.divider()
    st.caption("📊 Data: StatCan Tables 12-10-0175-01 & 12-10-0163-01")
    st.caption("🌍 CIMT (Customs Basis)")

# -----------------------------------------------------------------------------
# 5. FILTER DATA
# -----------------------------------------------------------------------------
df = df_all.copy()

# Year filter
if "YEAR" in df.columns:
    df = df[(df["YEAR"] >= year_range[0]) & (df["YEAR"] <= year_range[1])]

# Exclude incomplete years
if exclude_incomplete and INCOMPLETE_YEARS:
    df = df[~df["YEAR"].isin(list(INCOMPLETE_YEARS.keys()))]

# Trade flow filter
if trade_col:
    if trade_flow == "Exports":
        df = df[df[trade_col].str.contains("export", case=False, na=False)]
    elif trade_flow == "Imports":
        df = df[df[trade_col].str.contains("import", case=False, na=False)]

# Keep a national-scope copy before province filtering (for KPIs & Provincial tab)
df_national = df.copy()

# Province filter
if geo_col and selected_provinces:
    df = df[df[geo_col].isin(selected_provinces)]

if df.empty:
    st.warning("No data available for the selected filters. Try adjusting the sidebar controls.")
    st.stop()

# -----------------------------------------------------------------------------
# 6. HEADER
# -----------------------------------------------------------------------------
flow_label = trade_flow if trade_flow != "Both" else "Exports & Imports"
province_label = ", ".join(selected_provinces) if selected_provinces else "All Provinces"
# Short label for chart titles — truncate if multiple provinces
if selected_provinces and len(selected_provinces) == 1:
    geo_label = selected_provinces[0]
elif selected_provinces and len(selected_provinces) <= 3:
    geo_label = ", ".join(selected_provinces)
else:
    geo_label = f"{len(selected_provinces)} Provinces"
st.title(f"🌍 Agri-Food {flow_label}: {geo_label}")
st.markdown(f"### StatCan CIMT (Table 12-10-0175-01) • {year_range[0]}–{year_range[1]}")
st.markdown("---")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def fmt_value(val, unit="$"):
    """Format a value in thousands to human-readable."""
    if pd.isna(val) or val == 0:
        return "N/A"
    # StatCan trade values are in thousands of dollars (x 1,000)
    val_dollars = val * 1000
    if abs(val_dollars) >= 1e9:
        return f"{unit}{val_dollars / 1e9:.1f}B"
    if abs(val_dollars) >= 1e6:
        return f"{unit}{val_dollars / 1e6:.1f}M"
    return f"{unit}{val_dollars:,.0f}"


def _format_dollar_axis(fig, axis="y"):
    """Replace Plotly's default SI-prefix formatting (G for giga) with
    financial-style labels: $10B, $500M, etc.

    Call this AFTER all traces are added so we can inspect the data range.
    """
    import math

    # Collect all values from traces for the target axis
    vals = []
    for trace in fig.data:
        data = trace.y if axis == "y" else trace.x
        if data is not None:
            try:
                vals.extend([v for v in data if v is not None and not (isinstance(v, float) and math.isnan(v))])
            except TypeError:
                pass

    if not vals:
        return fig

    max_val = max(abs(v) for v in vals) if vals else 0

    if max_val >= 1e9:
        divisor, suffix = 1e9, "B"
    elif max_val >= 1e6:
        divisor, suffix = 1e6, "M"
    elif max_val >= 1e3:
        divisor, suffix = 1e3, "K"
    else:
        return fig  # no special formatting needed

    # Generate nice round tick values
    nice_max = max_val / divisor
    # Pick a step that gives ~5-8 ticks
    raw_step = nice_max / 6
    magnitude = 10 ** math.floor(math.log10(raw_step)) if raw_step > 0 else 1
    nice_step = math.ceil(raw_step / magnitude) * magnitude
    if nice_step == 0:
        nice_step = 1

    tick_vals = []
    tick_text = []
    v = 0
    while v <= max_val * 1.05:
        tick_vals.append(v)
        label_num = v / divisor
        if label_num == int(label_num):
            tick_text.append(f"${int(label_num)}{suffix}")
        else:
            tick_text.append(f"${label_num:.1f}{suffix}")
        v += nice_step * divisor

    axis_update = dict(tickvals=tick_vals, ticktext=tick_text)
    if axis == "y":
        fig.update_yaxes(**axis_update)
    else:
        fig.update_xaxes(**axis_update)

    return fig


def get_latest_year(df):
    """Get the latest year with data."""
    if "YEAR" in df.columns:
        return int(df["YEAR"].max())
    return None


def _dedup_totals(frame: pd.DataFrame) -> pd.DataFrame:
    """Return rows suitable for computing aggregate totals.

    The CIMT dataset contains aggregate partner rows ('All countries')
    alongside individual country rows. Summing all rows double-counts.
    This helper keeps ONLY the 'All countries' partner row so the VALUE
    column can be safely summed for totals and trend charts.
    """
    if partner_col and partner_col in frame.columns:
        agg = frame[frame[partner_col].str.contains("All countries", case=False, na=False)]
        if not agg.empty:
            return agg
    return frame


# =============================================================================
# TABS
# =============================================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Export Overview",
    "🌾 Top Commodities",
    "🗺️ Destination Markets",
    "🏗️ Provincial Breakdown",
    "📖 Methodology & Sources",
])


# =============================================================================
# TAB 1: EXPORT OVERVIEW
# =============================================================================
with tab1:
    latest_year = get_latest_year(df)

    # --- KPI CARDS ---
    if latest_year:
        # Use Canada-only data for KPIs to avoid double-counting when multiple provinces selected
        _df_kpi = df_national[df_national[geo_col].str.contains("^Canada$", case=False, regex=True)] if geo_col else df_national
        if _df_kpi.empty:
            _df_kpi = df_national  # Fallback if Canada not in data
        df_latest = _dedup_totals(_df_kpi[_df_kpi["YEAR"] == latest_year])
        df_prev = _dedup_totals(_df_kpi[_df_kpi["YEAR"] == latest_year - 1])

        # Primary ag exports from 12-10-0175 (C11 only)
        if trade_col:
            exports_latest = df_latest[df_latest[trade_col].str.contains("export", case=False, na=False)]["VALUE"].sum()
            exports_prev = df_prev[df_prev[trade_col].str.contains("export", case=False, na=False)]["VALUE"].sum() if not df_prev.empty else 0
            imports_latest = df_latest[df_latest[trade_col].str.contains("import", case=False, na=False)]["VALUE"].sum()
            imports_prev = df_prev[df_prev[trade_col].str.contains("import", case=False, na=False)]["VALUE"].sum() if not df_prev.empty else 0
        else:
            exports_latest = df_latest["VALUE"].sum()
            exports_prev = df_prev["VALUE"].sum() if not df_prev.empty else 0
            imports_latest = 0
            imports_prev = 0

        trade_balance = exports_latest - imports_latest

        # Full agri-food exports from 12-10-0163 (C11 + C221)
        full_export_val = None
        full_export_prev = None
        if df_detailed is not None and not df_detailed.empty:
            _det_trade_col = None
            for c in df_detailed.columns:
                if c.lower() == "trade":
                    _det_trade_col = c
                    break
            # Find the latest year available in the detailed data
            det_years = sorted(df_detailed["YEAR"].dropna().unique())
            # Exclude incomplete years from detailed data too
            if exclude_incomplete and INCOMPLETE_YEARS:
                det_years = [y for y in det_years if int(y) not in INCOMPLETE_YEARS]
            if det_years:
                det_latest = int(max(det_years))
                df_det_yr = df_detailed[df_detailed["YEAR"] == det_latest]
                df_det_prev = df_detailed[df_detailed["YEAR"] == det_latest - 1]
                if _det_trade_col:
                    full_export_val = df_det_yr[
                        df_det_yr[_det_trade_col].str.contains("export", case=False, na=False)
                    ]["VALUE"].sum()
                    full_export_prev = df_det_prev[
                        df_det_prev[_det_trade_col].str.contains("export", case=False, na=False)
                    ]["VALUE"].sum() if not df_det_prev.empty else 0
                else:
                    full_export_val = df_det_yr["VALUE"].sum()
                    full_export_prev = df_det_prev["VALUE"].sum() if not df_det_prev.empty else 0

        cols = st.columns(4)
        with cols[0]:
            # Show full agri-food total if available, else primary only
            if full_export_val is not None and full_export_val > 0:
                delta_full = ((full_export_val - full_export_prev) / full_export_prev * 100) if full_export_prev and full_export_prev > 0 else None
                st.metric(
                    f"Full Agri-Food Exports ({latest_year})",
                    fmt_value(full_export_val),
                    delta=f"{delta_full:+.1f}% YoY" if delta_full is not None else None,
                )
            else:
                delta = ((exports_latest - exports_prev) / exports_prev * 100) if exports_prev > 0 else None
                st.metric(
                    f"Total {flow_label} ({latest_year})",
                    fmt_value(exports_latest),
                    delta=f"{delta:+.1f}% YoY" if delta is not None else None,
                )
        with cols[1]:
            delta_primary = ((exports_latest - exports_prev) / exports_prev * 100) if exports_prev > 0 else None
            st.metric(
                f"Primary Ag Exports ({latest_year})",
                fmt_value(exports_latest),
                delta=f"{delta_primary:+.1f}% YoY" if delta_primary is not None else None,
            )
        with cols[2]:
            if imports_latest > 0:
                st.metric(f"Trade Balance ({latest_year})", fmt_value(trade_balance))
            else:
                st.metric("Period Covered", f"{year_range[0]}–{year_range[1]}")
        with cols[3]:
            if partner_col:
                # Count individual partners (exclude aggregates)
                partners_yr = df[df["YEAR"] == latest_year][partner_col].unique()
                n_partners = len([
                    p for p in partners_yr
                    if not any(kw in str(p).lower() for kw in ["all countries", "other countries", "total"])
                ])
                st.metric("Trading Partners", f"{n_partners}")
            else:
                if geo_col:
                    n_provinces = df[geo_col].nunique()
                    st.metric("Provinces", f"{n_provinces}")

        # Source labels for KPIs
        kpi_notes = []
        if full_export_val is not None and full_export_val > 0:
            kpi_notes.append(
                "**Full Agri-Food Exports** = C11 + C221 from Table 12-10-0163-01 (Canada only)."
            )
        kpi_notes.append(
            "**Primary Ag Exports** = C11 from Table 12-10-0175-01 (by province & partner)."
        )
        st.caption(
            f"Values in Canadian dollars (×1,000 from StatCan). "
            f"Latest year: **{latest_year}**. "
            + " ".join(kpi_notes)
        )

    # --- Data scope explanation ---
    if use_full_scope:
        st.info(
            "📊 **Showing: Full Agri-Food** (C11 + C221) — includes all agricultural, "
            "food, and beverage exports (meat, dairy, packaged food, beverages, etc.). "
            "Source: Table 12-10-0163-01 (national level). Use the sidebar toggle to "
            "switch to **Primary Agriculture** for province/partner breakdowns."
        )
    else:
        st.info(
            "📊 **Showing: Primary Agriculture** (C11) — raw and intermediate farm "
            "products only. This is the dataset available by province and trading "
            "partner. The KPI above also shows the **Full Agri-Food** total "
            "(C11 + C221) for national context. Use the sidebar toggle to view the "
            "full agri-food trend."
        )

    st.markdown("---")

    # --- TREND CHART ---
    _scope_label = "Full Agri-Food" if use_full_scope else "Primary Ag"
    st.subheader(f"📈 {geo_label} — {_scope_label} {flow_label} Trend")

    multi_geo = geo_col and selected_provinces and len(selected_provinces) > 1

    if trade_col:
        # Use deduplicated data for trend (only "All countries" partner rows)
        df_trend = _dedup_totals(df)

        fig_trend = go.Figure()

        # When Full Agri-Food scope is selected, use df_detailed for the trend
        _use_detailed_trend = (
            use_full_scope
            and df_detailed is not None
            and not multi_geo  # detailed data has no province dimension
        )

        if _use_detailed_trend:
            # --- FULL AGRI-FOOD TREND from 12-10-0163-01 ---
            _det = df_detailed.copy()
            if exclude_incomplete and INCOMPLETE_YEARS:
                _det = _det[~_det["YEAR"].isin(list(INCOMPLETE_YEARS.keys()))]
            _det = _det[(_det["YEAR"] >= year_range[0]) & (_det["YEAR"] <= year_range[1])]
            _det_trade_col = None
            for c in _det.columns:
                if c.lower() == "trade":
                    _det_trade_col = c
                    break
            if _det_trade_col:
                if trade_flow == "Exports":
                    _det = _det[_det[_det_trade_col].str.contains("export", case=False, na=False)]
                elif trade_flow == "Imports":
                    _det = _det[_det[_det_trade_col].str.contains("import", case=False, na=False)]

            annual_full = _det.groupby("YEAR", as_index=False)["VALUE"].sum().sort_values("YEAR")
            fig_trend.add_trace(go.Scatter(
                x=annual_full["YEAR"],
                y=annual_full["VALUE"] * 1000,
                mode="lines+markers",
                name="Full Agri-Food (C11+C221)",
                line=dict(color=COLOURS["primary"], width=3),
                marker=dict(size=6),
                hovertemplate=(
                    "<b>Full Agri-Food</b><br>"
                    "Year: %{x}<br>"
                    "Value: $%{y:,.0f}<extra></extra>"
                ),
            ))
            # Also show Primary Ag as a secondary line for comparison
            df_prim_trend = _dedup_totals(df)
            if trade_flow == "Exports" and trade_col:
                df_prim_trend = df_prim_trend[df_prim_trend[trade_col].str.contains("export", case=False, na=False)]
            elif trade_flow == "Imports" and trade_col:
                df_prim_trend = df_prim_trend[df_prim_trend[trade_col].str.contains("import", case=False, na=False)]
            annual_prim = df_prim_trend.groupby("YEAR", as_index=False)["VALUE"].sum().sort_values("YEAR")
            fig_trend.add_trace(go.Scatter(
                x=annual_prim["YEAR"],
                y=annual_prim["VALUE"] * 1000,
                mode="lines+markers",
                name="Primary Ag Only (C11)",
                line=dict(color=COLOURS["accent"], width=2, dash="dot"),
                marker=dict(size=4),
                hovertemplate=(
                    "<b>Primary Ag Only</b><br>"
                    "Year: %{x}<br>"
                    "Value: $%{y:,.0f}<extra></extra>"
                ),
            ))
            st.caption(
                "Solid line = Full Agri-Food (C11 + C221, national). "
                "Dotted line = Primary Agriculture (C11 only) for comparison."
            )

        elif multi_geo:
            # --- MULTI-GEOGRAPHY COMPARISON: one line per province ---
            for i, geo in enumerate(selected_provinces):
                geo_data = df_trend[df_trend[geo_col] == geo]
                annual_geo = geo_data.groupby("YEAR", as_index=False)["VALUE"].sum().sort_values("YEAR")
                fig_trend.add_trace(go.Scatter(
                    x=annual_geo["YEAR"],
                    y=annual_geo["VALUE"] * 1000,
                    mode="lines+markers",
                    name=geo,
                    line=dict(color=CHART_COLOURS[i % len(CHART_COLOURS)], width=3),
                    marker=dict(size=6),
                    hovertemplate=(
                        f"<b>{geo}</b><br>"
                        "Year: %{x}<br>"
                        "Value: $%{y:,.0f}<extra></extra>"
                    ),
                ))
        else:
            # --- SINGLE GEOGRAPHY: one line per trade type ---
            annual = df_trend.groupby(["YEAR", trade_col], as_index=False)["VALUE"].sum()
            for trade_type in sorted(annual[trade_col].unique()):
                subset = annual[annual[trade_col] == trade_type].sort_values("YEAR")
                is_export = "export" in str(trade_type).lower()
                fig_trend.add_trace(go.Scatter(
                    x=subset["YEAR"],
                    y=subset["VALUE"] * 1000,
                    mode="lines+markers",
                    name=str(trade_type),
                    line=dict(
                        color=COLOURS["primary"] if is_export else COLOURS["accent"],
                        width=3 if is_export else 2,
                    ),
                    marker=dict(size=6 if is_export else 4),
                    hovertemplate=(
                        f"<b>{trade_type}</b><br>"
                        "Year: %{x}<br>"
                        "Value: $%{y:,.0f}<extra></extra>"
                    ),
                ))

        fig_trend.update_layout(
            template="plotly_white",
            hovermode="x unified",
            height=500,
            legend=dict(orientation="h", y=-0.15),
            yaxis_title="Value (CAD)",
            xaxis_title="",
            yaxis=dict(tickformat="~s"),
        )
        _format_dollar_axis(fig_trend, "y")
        st.plotly_chart(fig_trend, use_container_width=True)

        if multi_geo and not _use_detailed_trend:
            st.caption("Showing one line per selected province for comparison.")
    else:
        # Simple total trend
        df_trend = _dedup_totals(df)
        annual = df_trend.groupby("YEAR", as_index=False)["VALUE"].sum().sort_values("YEAR")
        fig_trend = px.line(
            annual, x="YEAR", y="VALUE",
            title=f"Total {_scope_label} {flow_label} — {geo_label}",
            labels={"VALUE": "Value (×1,000 CAD)", "YEAR": "Year"},
        )
        fig_trend.update_layout(template="plotly_white", height=450)
        st.plotly_chart(fig_trend, use_container_width=True)

    # --- COMPOSITION BY COMMODITY GROUP ---
    if commodity_col:
        st.markdown("---")
        st.subheader(f"📊 {geo_label} — Export Composition by Commodity Group")

        # Use deduplicated data for composition chart too
        df_comp = _dedup_totals(df)
        comp = df_comp.groupby(["YEAR", commodity_col], as_index=False)["VALUE"].sum()
        top_commodities = (
            comp.groupby(commodity_col)["VALUE"].sum()
            .sort_values(ascending=False)
            .head(8)
            .index.tolist()
        )

        comp_top = comp[comp[commodity_col].isin(top_commodities)]

        fig_comp = go.Figure()
        for i, comm in enumerate(top_commodities):
            subset = comp_top[comp_top[commodity_col] == comm].sort_values("YEAR")
            # Truncate long labels
            label = str(comm)[:50] + "…" if len(str(comm)) > 50 else str(comm)
            fig_comp.add_trace(go.Bar(
                x=subset["YEAR"],
                y=subset["VALUE"] * 1000,
                name=label,
                marker_color=CHART_COLOURS[i % len(CHART_COLOURS)],
                hovertemplate=(
                    f"<b>{label}</b><br>"
                    "Year: %{x}<br>"
                    "Value: $%{y:,.0f}<extra></extra>"
                ),
            ))

        fig_comp.update_layout(
            barmode="stack",
            template="plotly_white",
            height=500,
            legend=dict(orientation="h", y=-0.25, font=dict(size=10)),
            yaxis_title="Value (CAD)",
            yaxis=dict(tickformat="~s"),
            xaxis_title="",
        )
        _format_dollar_axis(fig_comp, "y")
        st.plotly_chart(fig_comp, use_container_width=True)


# =============================================================================
# TAB 2: TOP COMMODITIES
# =============================================================================
with tab2:
    # Prefer detailed NAPCS data from 12-10-0163 when available
    _use_detailed = df_detailed is not None and not df_detailed.empty

    if _use_detailed:
        st.subheader(f"🌾 Top Export Commodities — Detailed Breakdown ({latest_year or 'Latest'})")
        st.info(
            "🇨🇦 **National data — All agri-food products.** This tab shows "
            "Canada’s total agri-food exports broken down by commodity, including "
            "both primary farm products (grains, oilseeds, livestock) **and** "
            "finished food & beverages (meat, dairy, packaged food, alcohol). "
            "Source: StatCan Table 12-10-0163-01 (Canada only, no provincial detail)."
        )

        # Determine trade column
        _det_trade_col = None
        for c in df_detailed.columns:
            if c.lower() == "trade":
                _det_trade_col = c
                break

        # Filter to exports and year range
        df_det_filtered = df_detailed.copy()
        if _det_trade_col:
            df_det_filtered = df_det_filtered[
                df_det_filtered[_det_trade_col].str.contains("export", case=False, na=False)
            ]
        if "YEAR" in df_det_filtered.columns:
            df_det_filtered = df_det_filtered[
                (df_det_filtered["YEAR"] >= year_range[0]) & (df_det_filtered["YEAR"] <= year_range[1])
            ]
            if exclude_incomplete and INCOMPLETE_YEARS:
                df_det_filtered = df_det_filtered[
                    ~df_det_filtered["YEAR"].isin(list(INCOMPLETE_YEARS.keys()))
                ]

        # Use NAPCS_LABEL for display grouping
        label_col = "NAPCS_LABEL" if "NAPCS_LABEL" in df_det_filtered.columns else "NAPCS_CODE"

        if not df_det_filtered.empty and label_col in df_det_filtered.columns:
            # Latest year snapshot
            det_latest = int(df_det_filtered["YEAR"].max()) if "YEAR" in df_det_filtered.columns else None
            if det_latest:
                df_det_yr = df_det_filtered[df_det_filtered["YEAR"] == det_latest]
            else:
                df_det_yr = df_det_filtered

            comm_totals = (
                df_det_yr.groupby(label_col, as_index=False)["VALUE"]
                .sum()
                .sort_values("VALUE", ascending=False)
            )

            if not comm_totals.empty:
                total_val = comm_totals["VALUE"].sum()
                comm_totals["Share (%)"] = (comm_totals["VALUE"] / total_val * 100).round(1)
                comm_totals["Formatted Value"] = comm_totals["VALUE"].apply(fmt_value)

                # --- Horizontal bar chart ---
                top_n = comm_totals.head(15).copy()

                fig_bar = go.Figure(go.Bar(
                    y=top_n[label_col],
                    x=top_n["VALUE"] * 1000,
                    orientation="h",
                    marker_color=CHART_COLOURS[:len(top_n)],
                    text=top_n.apply(
                        lambda r: f"{fmt_value(r['VALUE'])} ({r['Share (%)']:.1f}%)", axis=1
                    ),
                    textposition="outside",
                    hovertemplate="<b>%{y}</b><br>Value: $%{x:,.0f}<extra></extra>",
                ))
                fig_bar.update_layout(
                    template="plotly_white",
                    height=max(450, len(top_n) * 45),
                    yaxis=dict(autorange="reversed"),
                    xaxis_title="Value (CAD)",
                    xaxis=dict(tickformat="~s"),
                    showlegend=False,
                    margin=dict(l=300),
                    title=f"Top Export Commodities ({det_latest or 'Latest Year'})",
                )
                _format_dollar_axis(fig_bar, "x")
                st.plotly_chart(fig_bar, use_container_width=True)

                st.markdown("---")

                # --- Treemap ---
                st.subheader("🗺️ Commodity Share Treemap")
                top_tree = comm_totals.head(18).copy()
                top_tree["VALUE_CAD"] = top_tree["VALUE"] * 1000

                fig_tree = px.treemap(
                    top_tree,
                    path=[label_col],
                    values="VALUE_CAD",
                    color="VALUE_CAD",
                    color_continuous_scale="Greens",
                    labels={"VALUE_CAD": "Value (CAD)"},
                )
                fig_tree.update_layout(height=500, margin=dict(t=30, l=0, r=0, b=0))
                fig_tree.update_traces(
                    texttemplate="<b>%{label}</b><br>%{percentRoot:.1%}",
                    hovertemplate="<b>%{label}</b><br>Value: $%{value:,.0f}<extra></extra>",
                )
                st.plotly_chart(fig_tree, use_container_width=True)

                st.markdown("---")

                # --- Trend lines by commodity ---
                st.subheader("📈 Commodity Export Trends Over Time")
                top_5_labels = comm_totals.head(6)[label_col].tolist()
                trend_data = (
                    df_det_filtered[df_det_filtered[label_col].isin(top_5_labels)]
                    .groupby(["YEAR", label_col], as_index=False)["VALUE"].sum()
                    .sort_values("YEAR")
                )

                fig_trend_comm = go.Figure()
                for i, lbl in enumerate(top_5_labels):
                    subset = trend_data[trend_data[label_col] == lbl]
                    fig_trend_comm.add_trace(go.Scatter(
                        x=subset["YEAR"],
                        y=subset["VALUE"] * 1000,
                        mode="lines+markers",
                        name=lbl,
                        line=dict(color=CHART_COLOURS[i % len(CHART_COLOURS)], width=2.5),
                        marker=dict(size=5),
                        hovertemplate=(
                            f"<b>{lbl}</b><br>"
                            "Year: %{x}<br>"
                            "Value: $%{y:,.0f}<extra></extra>"
                        ),
                    ))

                fig_trend_comm.update_layout(
                    template="plotly_white",
                    hovermode="x unified",
                    height=500,
                    legend=dict(orientation="h", y=-0.2, font=dict(size=10)),
                    yaxis_title="Value (CAD)",
                    yaxis=dict(tickformat="~s"),
                    xaxis_title="",
                    title="Top Commodity Export Trends",
                )
                _format_dollar_axis(fig_trend_comm, "y")
                st.plotly_chart(fig_trend_comm, use_container_width=True)

                st.markdown("---")

                # --- Full table ---
                st.subheader("📋 Full Commodity Breakdown")
                display_df = comm_totals[[label_col, "Formatted Value", "Share (%)"]].rename(
                    columns={label_col: "Commodity"}
                )
                st.dataframe(display_df, hide_index=True, use_container_width=True)

                st.info(
                    "ℹ️ This tab shows **Canada-level** commodity detail from Table 12-10-0163-01. "
                    "For provincial and trading partner breakdowns, see the Destinations and "
                    "Provincial tabs (powered by Table 12-10-0175-01)."
                )
        else:
            st.warning("Detailed commodity data has no matching rows for the selected filters.")

    elif commodity_col:
        # Fallback: use section-level data from 12-10-0175
        st.subheader(f"🌾 Top Export Commodities ({latest_year or 'Latest'})")
        st.caption(
            "📊 Source: StatCan Table 12-10-0175-01 (section-level NAPCS). "
            "Run `python scripts/process_agrifood_exports.py` to unlock detailed commodity data."
        )

        df_comm_base = _dedup_totals(df)
        if latest_year:
            df_comm = df_comm_base[df_comm_base["YEAR"] == latest_year]
        else:
            df_comm = df_comm_base

        comm_totals = (
            df_comm.groupby(commodity_col, as_index=False)["VALUE"]
            .sum()
            .sort_values("VALUE", ascending=False)
        )

        if not comm_totals.empty:
            total_val = comm_totals["VALUE"].sum()
            comm_totals["Share (%)"] = (comm_totals["VALUE"] / total_val * 100).round(1)
            comm_totals["Formatted Value"] = comm_totals["VALUE"].apply(fmt_value)

            top_10 = comm_totals.head(10).copy()
            top_10["Label"] = top_10[commodity_col].apply(
                lambda x: str(x)[:45] + "…" if len(str(x)) > 45 else str(x)
            )

            fig_bar = go.Figure(go.Bar(
                y=top_10["Label"],
                x=top_10["VALUE"] * 1000,
                orientation="h",
                marker_color=CHART_COLOURS[:len(top_10)],
                text=top_10.apply(
                    lambda r: f"{fmt_value(r['VALUE'])} ({r['Share (%)']:.1f}%)", axis=1
                ),
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>Value: $%{x:,.0f}<extra></extra>",
            ))
            fig_bar.update_layout(
                template="plotly_white",
                height=max(400, len(top_10) * 50),
                yaxis=dict(autorange="reversed"),
                xaxis_title="Value (CAD)",
                xaxis=dict(tickformat="~s"),
                showlegend=False,
                margin=dict(l=250),
            )
            _format_dollar_axis(fig_bar, "x")
            st.plotly_chart(fig_bar, use_container_width=True)

            st.markdown("---")

            st.subheader("📋 Full Commodity Breakdown")
            display_df = comm_totals[[commodity_col, "Formatted Value", "Share (%)"]].rename(
                columns={commodity_col: "Commodity Group"}
            )
            st.dataframe(display_df, hide_index=True, use_container_width=True)
    else:
        st.info("Commodity dimension not available in the data.")


# =============================================================================
# TAB 3: DESTINATION MARKETS
# =============================================================================
with tab3:
    if partner_col:
        st.subheader(f"🗺️ {geo_label} — Export Destination Markets ({latest_year or 'Latest'})")
        if use_full_scope:
            st.warning(
                "⚠️ **Data scope note:** You have **Full Agri-Food** selected, but "
                "partner-country breakdowns are only available for **Primary Agriculture** "
                "(C11). The data below shows Primary Ag destinations only."
            )
        st.info(
            "🌎 **Destination data — Primary agricultural products only.** These "
            "partner-country breakdowns cover raw and intermediate farm products (NAPCS C11). "
            "Processed food exports are **not** included, which is why the US share (~49%) is "
            "lower than AAFC's figure (~62%). The US buys a larger share of Canada's "
            "processed food than of its primary farm exports."
        )

        if latest_year:
            df_dest = df[df["YEAR"] == latest_year]
        else:
            df_dest = df

        dest_totals = (
            df_dest.groupby(partner_col, as_index=False)["VALUE"]
            .sum()
            .sort_values("VALUE", ascending=False)
        )

        if not dest_totals.empty:
            # Use the "All countries" aggregate row as the denominator —
            # individual country rows should NOT be summed (that double-counts).
            _AGG_PAT = "All countries|Total"
            agg_rows = dest_totals[dest_totals[partner_col].str.contains(_AGG_PAT, case=False, na=False)]
            total_val = float(agg_rows["VALUE"].sum()) if not agg_rows.empty else dest_totals["VALUE"].sum()
            dest_totals["Share (%)"] = (dest_totals["VALUE"] / total_val * 100).round(1)

            # Rows excluding aggregates (for charts & partner counts)
            _EXCLUDE_PAT = "All countries|Other countries|Total"
            dest_individual = dest_totals[
                ~dest_totals[partner_col].str.contains(_EXCLUDE_PAT, case=False, na=False)
            ]

            # KPI cards for top destinations
            us_row = dest_totals[dest_totals[partner_col].str.contains("United States|USA|U.S.", case=False, na=False)]

            kpi_cols = st.columns(3)
            with kpi_cols[0]:
                if not us_row.empty:
                    us_share = float(us_row["Share (%)"].iloc[0])
                    st.metric(f"🇺🇸 {geo_label}'s US Share", f"{us_share:.1f}%")
                else:
                    top_share = dest_individual["Share (%)"].iloc[0] if not dest_individual.empty else 0
                    st.metric("Top Partner Share", f"{top_share:.1f}%")
            with kpi_cols[1]:
                non_us = dest_individual[~dest_individual[partner_col].str.contains("United States|USA|U.S.", case=False, na=False)]
                if not non_us.empty:
                    st.metric("Top Non-US Partner", str(non_us.iloc[0][partner_col])[:25])
            with kpi_cols[2]:
                n_partners = len(dest_individual)
                st.metric("Active Trade Partners", f"{n_partners}")

            st.markdown("---")

            # ── Choropleth World Map ─────────────────────────────
            map_data = dest_individual.copy()
            map_data["iso_alpha"] = map_data[partner_col].map(_ISO3_MAP)
            map_data = map_data.dropna(subset=["iso_alpha"])

            if not map_data.empty:
                map_data["Value_CAD"] = map_data["VALUE"] * 1000
                map_data["Formatted"] = map_data["VALUE"].apply(fmt_value)

                fig_map = px.choropleth(
                    map_data,
                    locations="iso_alpha",
                    color="Value_CAD",
                    hover_name=partner_col,
                    hover_data={"Formatted": True, "Share (%)": True, "iso_alpha": False, "Value_CAD": False},
                    color_continuous_scale=[
                        [0, "#e8f5e9"],
                        [0.15, "#81c784"],
                        [0.4, "#43a047"],
                        [0.7, "#2e7d32"],
                        [1.0, "#1b5e20"],
                    ],
                    labels={"Value_CAD": "Export Value (CAD)", "Formatted": "Value"},
                    title=f"Primary Ag Export Destinations — {geo_label} ({latest_year or 'Latest'})",
                )
                fig_map.update_geos(
                    showcoastlines=True, coastlinecolor="#bdbdbd",
                    showland=True, landcolor="#f5f5f5",
                    showocean=True, oceancolor="#e3f2fd",
                    showlakes=False,
                    showcountries=True, countrycolor="#e0e0e0",
                    projection_type="natural earth",
                    lataxis_range=[-55, 80],
                )
                fig_map.update_layout(
                    height=500,
                    margin=dict(l=0, r=0, t=40, b=0),
                    coloraxis_colorbar=dict(
                        title="Export Value",
                        tickvals=[0, 5e9, 10e9, 15e9, 20e9, 25e9, 30e9],
                        ticktext=["$0", "$5B", "$10B", "$15B", "$20B", "$25B", "$30B"],
                        len=0.6,
                    ),
                    geo=dict(bgcolor="rgba(0,0,0,0)"),
                )
                st.plotly_chart(fig_map, use_container_width=True)

            st.markdown("---")

            # Destination bar chart — individual countries only
            dest_viz = dest_individual.head(10)

            if not dest_viz.empty:
                colours = [
                    PARTNER_COLOURS.get(str(p), COLOURS["other"])
                    for p in dest_viz[partner_col]
                ]

                fig_dest = go.Figure(go.Bar(
                    y=dest_viz[partner_col],
                    x=dest_viz["VALUE"] * 1000,
                    orientation="h",
                    marker_color=colours,
                    text=dest_viz.apply(
                        lambda r: f"{fmt_value(r['VALUE'])} ({r['Share (%)']:.1f}%)", axis=1
                    ),
                    textposition="outside",
                    hovertemplate="<b>%{y}</b><br>Value: $%{x:,.0f}<extra></extra>",
                ))
                fig_dest.update_layout(
                    template="plotly_white",
                    height=max(400, len(dest_viz) * 50),
                    yaxis=dict(autorange="reversed"),
                    xaxis_title="Value (CAD)",
                    xaxis=dict(tickformat="~s"),
                    showlegend=False,
                    title=f"Top Export Destinations — {geo_label} ({latest_year or 'Latest Year'})",
                )
                _format_dollar_axis(fig_dest, "x")
                st.plotly_chart(fig_dest, use_container_width=True)

            st.markdown("---")

            # US vs Others trend over time
            st.subheader(f"🇺🇸 {geo_label} — US vs. Non-US Export Trend")

            if partner_col and "YEAR" in df.columns:
                df_partners = df.copy()
                df_partners["Partner_Group"] = df_partners[partner_col].apply(
                    lambda x: "United States" if "united states" in str(x).lower() or "usa" in str(x).lower()
                    else ("Aggregate" if any(kw in str(x).lower() for kw in ["all countries", "other countries", "total"])
                          else "Other Partners")
                )

                # Exclude aggregate rows
                df_partners = df_partners[df_partners["Partner_Group"] != "Aggregate"]

                trend_data = (
                    df_partners.groupby(["YEAR", "Partner_Group"], as_index=False)["VALUE"]
                    .sum()
                    .sort_values("YEAR")
                )

                fig_us = go.Figure()
                for group in ["United States", "Other Partners"]:
                    subset = trend_data[trend_data["Partner_Group"] == group]
                    colour = COLOURS["usa"] if group == "United States" else COLOURS["other"]
                    fig_us.add_trace(go.Scatter(
                        x=subset["YEAR"],
                        y=subset["VALUE"] * 1000,
                        mode="lines+markers",
                        name=group,
                        line=dict(color=colour, width=3),
                        marker=dict(size=6),
                        fill="tozeroy" if group == "Other Partners" else None,
                        hovertemplate=f"<b>{group}</b><br>Year: %{{x}}<br>Value: $%{{y:,.0f}}<extra></extra>",
                    ))

                fig_us.update_layout(
                    template="plotly_white",
                    hovermode="x unified",
                    height=450,
                    legend=dict(orientation="h", y=-0.15),
                    yaxis_title="Value (CAD)",
                    yaxis=dict(tickformat="~s"),
                    xaxis_title="",
                    title=f"{geo_label} — US vs. Non-US Primary Ag Exports",
                )
                _format_dollar_axis(fig_us, "y")
                st.plotly_chart(fig_us, use_container_width=True)
                st.caption(
                    "The AAFC notes that the US accounted for 61.9% of Canadian agri-food "
                    "exports in 2024, up from 53.3% in 2015."
                )

            # Full destination table
            st.markdown("---")
            st.subheader(f"📋 {geo_label} — Full Destination Breakdown")
            dest_display = dest_totals[[partner_col, "VALUE", "Share (%)"]].copy()
            dest_display["Formatted Value"] = dest_display["VALUE"].apply(fmt_value)
            st.dataframe(
                dest_display[[partner_col, "Formatted Value", "Share (%)"]].rename(
                    columns={partner_col: "Trading Partner"}
                ),
                hide_index=True, use_container_width=True,
            )
    else:
        st.info(
            "Trading partner dimension not available in the data. "
            "This may mean the downloaded data was filtered before partners were captured."
        )


# =============================================================================
# TAB 4: PROVINCIAL BREAKDOWN
# =============================================================================
with tab4:
    # Provincial tab always uses full national data (not filtered by sidebar province selection)
    _df_prov_src = df_national if geo_col else df
    if geo_col and _df_prov_src[geo_col].nunique() > 1:
        st.subheader(f"🏗️ Exports by Province ({latest_year or 'Latest'})")
        if use_full_scope:
            st.warning(
                "⚠️ **Data scope note:** You have **Full Agri-Food** selected, but "
                "provincial breakdowns are only available for **Primary Agriculture** "
                "(C11). The data below shows Primary Ag by province only."
            )
        st.info(
            "🇨🇦 **Provincial data — Primary agricultural products only.** These "
            "figures cover raw and intermediate farm products (grains, oilseeds, livestock, "
            "fish, flour, oils) but do **not** include finished food products like meat, dairy, "
            "or packaged food. That’s because provincial-level trade data is only available for "
            "primary agriculture (NAPCS C11). For the full agri-food total including processed "
            "foods, see the **Export Overview** or **Top Commodities** tabs."
        )

        # Use deduplicated data (Partner='All countries') for province totals
        df_prov_base = _dedup_totals(_df_prov_src)

        if latest_year:
            df_prov = df_prov_base[df_prov_base["YEAR"] == latest_year]
        else:
            df_prov = df_prov_base

        prov_totals = (
            df_prov.groupby(geo_col, as_index=False)["VALUE"]
            .sum()
            .sort_values("VALUE", ascending=False)
        )

        if not prov_totals.empty:
            # Use 'Canada' as the denominator for share calculations
            canada_total = prov_totals[prov_totals[geo_col].str.contains("^Canada$", case=False, regex=True)]["VALUE"].sum()
            if canada_total > 0:
                prov_totals["Share (%)"] = (prov_totals["VALUE"] / canada_total * 100).round(1)
            else:
                total_val = prov_totals["VALUE"].sum()
                prov_totals["Share (%)"] = (prov_totals["VALUE"] / total_val * 100).round(1)

            # Exclude Canada aggregate for province-level chart
            prov_viz = prov_totals[
                ~prov_totals[geo_col].str.contains("^Canada$", case=False, na=False, regex=True)
            ]

            if not prov_viz.empty:
                fig_prov = go.Figure(go.Bar(
                    y=prov_viz[geo_col],
                    x=prov_viz["VALUE"] * 1000,
                    orientation="h",
                    marker_color=CHART_COLOURS[:len(prov_viz)],
                    text=prov_viz.apply(
                        lambda r: f"{fmt_value(r['VALUE'])} ({r['Share (%)']:.1f}%)", axis=1
                    ),
                    textposition="outside",
                    hovertemplate="<b>%{y}</b><br>Value: $%{x:,.0f}<extra></extra>",
                ))
                fig_prov.update_layout(
                    template="plotly_white",
                    height=max(400, len(prov_viz) * 45),
                    yaxis=dict(autorange="reversed"),
                    xaxis_title="Value (CAD)",
                    xaxis=dict(tickformat="~s"),
                    showlegend=False,
                    title=f"Primary Ag Exports by Province ({latest_year})",
                )
                _format_dollar_axis(fig_prov, "x")
                st.plotly_chart(fig_prov, use_container_width=True)

            st.markdown("---")

            # Provincial trends over time — also deduplicated
            st.subheader("📈 Provincial Export Trends")

            prov_trend = df_prov_base.groupby(["YEAR", geo_col], as_index=False)["VALUE"].sum()

            # Get top 5 provinces by latest year value (excluding Canada)
            top_provs = (
                prov_totals[~prov_totals[geo_col].str.contains("^Canada$", case=False, na=False, regex=True)]
                .head(5)[geo_col].tolist()
            )

            prov_trend_top = prov_trend[prov_trend[geo_col].isin(top_provs)].sort_values("YEAR")

            fig_prov_trend = go.Figure()
            for i, prov in enumerate(top_provs):
                subset = prov_trend_top[prov_trend_top[geo_col] == prov]
                fig_prov_trend.add_trace(go.Scatter(
                    x=subset["YEAR"],
                    y=subset["VALUE"] * 1000,
                    mode="lines+markers",
                    name=prov,
                    line=dict(color=CHART_COLOURS[i % len(CHART_COLOURS)], width=2.5),
                    marker=dict(size=5),
                    hovertemplate=f"<b>{prov}</b><br>Year: %{{x}}<br>Value: $%{{y:,.0f}}<extra></extra>",
                ))

            fig_prov_trend.update_layout(
                template="plotly_white",
                hovermode="x unified",
                height=500,
                legend=dict(orientation="h", y=-0.15),
                yaxis_title="Value (CAD)",
                yaxis=dict(tickformat="~s"),
                xaxis_title="",
                title="Top 5 Provinces — Primary Ag Export Trends",
            )
            _format_dollar_axis(fig_prov_trend, "y")
            st.plotly_chart(fig_prov_trend, use_container_width=True)

            st.markdown("---")

            # Full table with YoY change
            st.subheader("📋 Full Provincial Breakdown")
            prov_display = prov_totals[[geo_col, "VALUE", "Share (%)"]].copy()
            prov_display["Formatted Value"] = prov_display["VALUE"].apply(fmt_value)

            # Compute YoY change
            _show_yoy = latest_year and (latest_year - 1) >= year_range[0]
            if _show_yoy:
                _df_prov_prev = df_prov_base[df_prov_base["YEAR"] == latest_year - 1]
                _prov_prev = _df_prov_prev.groupby(geo_col, as_index=False)["VALUE"].sum()
                prov_display = prov_display.merge(
                    _prov_prev[[geo_col, "VALUE"]].rename(columns={"VALUE": "_PREV"}),
                    on=geo_col, how="left",
                )
                prov_display["YoY (%)"] = (
                    (prov_display["VALUE"] - prov_display["_PREV"])
                    / prov_display["_PREV"] * 100
                ).round(1)
                _prov_cols = [geo_col, "Formatted Value", "Share (%)", "YoY (%)"]
            else:
                _prov_cols = [geo_col, "Formatted Value", "Share (%)"]

            st.dataframe(
                prov_display[_prov_cols].rename(
                    columns={geo_col: "Province"}
                ),
                hide_index=True, use_container_width=True,
            )
    else:
        st.info(
            "Provincial breakdown requires province-level data. "
            "Ensure the dataset includes multiple geographies."
        )

# =============================================================================
# TAB 5: METHODOLOGY & SOURCES
# =============================================================================
with tab5:
    st.subheader("📖 Understanding This Data")

    st.markdown("""
This page tracks Canadian agricultural and agri-food **exports and imports**
using publicly available data from Statistics Canada. We combine data from
**two StatCan tables** to provide both broad coverage and granular commodity
detail.
    """)

    st.markdown("---")

    # ── Section 1: What data we use ──────────────────────────────────
    st.markdown("### 1. Where does this data come from?")
    st.markdown("""
This page draws from **two** Statistics Canada tables in the **Canadian
International Merchandise Trade (CIMT)** program:

| | **Table 12-10-0175-01** | **Table 12-10-0163-01** |
|---|---|---|
| **Title** | Trade by province, commodity & partner | Trade by commodity, monthly |
| **Link** | [View →](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1210017501) | [View →](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1210016301) |
| **Commodity detail** | Section level | Group level (3-digit NAPCS) |
| **Geography** | Canada + all provinces | Canada only |
| **Trading partners** | 29 countries + aggregates | None |
| **Used for** | Overview, destinations, provincial tabs | Top commodities tab, headline total |

Both tables track physical goods crossing Canada's borders based on
**customs declarations**. They are published **monthly** (with about a
two-month lag). We aggregate the monthly figures into **annual totals**.

Values are reported in **thousands of Canadian dollars** (×1,000).
    """)

    st.markdown("---")

    # ── Section 2: How we filter the data ────────────────────────────
    st.markdown("### 2. How do we filter to agri-food?")
    st.markdown("""
Both tables classify goods using the **North American Product Classification
System (NAPCS)**.

#### Table 12-10-0175-01 (province & partner data)

We filter to **C11 — Farm, fishing and intermediate food products**, which
covers live animals, grains & oilseeds, crops, fish & seafood, and
intermediate food products (flour, oils, meal).

#### Table 12-10-0163-01 (commodity detail)

This table provides 3-digit NAPCS codes, letting us capture **both**
primary agricultural products and processed food:

| Section | NAPCS Codes | Products |
|---------|------------|----------|
| **C11** (Primary) | 111–121, 181–182 | Live animals, wheat, canola, fruit & vegetables, fish, animal feed, intermediate food |
| **C221** (Processed) | 171–173, 183, 191–193, 211–212 | Meat, dairy, packaged food, coffee & tea, juices, beverages, alcohol, tobacco |

By combining both sections, our **Full Agri-Food Exports** headline now
captures the complete agri-food value chain — matching much closer to
AAFC's reported figures.
    """)

    st.markdown("---")

    # ── Section 3: How our numbers compare to AAFC ───────────────────
    st.markdown("### 3. How do our numbers compare to AAFC's?")
    st.markdown("""
Agriculture and Agri-Food Canada (AAFC) reports Canada's agri-food and
seafood exports at roughly **$100 billion** for 2024, using the commercial
Global Trade Tracker (GTT) with its own custom classification.

| Metric | Our Dashboard | AAFC |
|--------|:---:|:---:|
| **Full agri-food total** | ~$92–100B (from 12-10-0163) | ~$100B (from GTT) |
| **Primary ag only (C11)** | ~$59B (from 12-10-0175) | Not reported separately |
| **Data source** | Free, public StatCan tables | Commercial GTT subscription |

Our **Full Agri-Food Exports** figure now closely tracks AAFC's headline
number. Any remaining gap is due to differences in how AAFC and StatCan
classify certain borderline products (e.g., some industrial food
ingredients).

#### Why the US share differs

The **US export share** shown on the Destinations tab comes from Table
12-10-0175-01, which covers C11 (primary agriculture) only. For primary
products like grain and oilseeds, exports are more globally diversified
(China, Japan, etc.), so the US share appears lower (~49%) than AAFC's
figure (~62%). AAFC's higher US share reflects the fact that the US is
the dominant buyer of Canada's **processed food** exports.
    """)

    st.markdown("---")

    # ── Section 4: Trade types ───────────────────────────────────────
    st.markdown("### 4. Understanding the trade types")
    st.markdown("""
The data includes three trade flow categories:

- **Domestic export** — Goods produced or significantly transformed in
  Canada, then shipped to another country. This is the main export figure.
- **Re-export** — Goods imported into Canada and then shipped back out
  without significant transformation.
- **Import** — Goods brought into Canada from another country.

When this page says "Total Exports," it includes both domestic exports
and re-exports, which matches Statistics Canada's reporting convention.
    """)

    st.markdown("---")

    # ── Section 5: Data freshness ────────────────────────────────────
    st.markdown("### 5. How fresh is the data?")

    st.markdown("""
| Item | Detail |
|------|--------|
| **Source tables** | [12-10-0175-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1210017501) (province/partner) and [12-10-0163-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1210016301) (commodity detail) |
| **Release frequency** | Monthly (usually ~2 months behind) |
| **Dashboard aggregation** | Monthly → Annual totals |
| **Incomplete years** | Automatically detected and excluded by default |
| **Update command** | `python scripts/process_agrifood_exports.py` |

The "Exclude incomplete years" checkbox in the sidebar removes any year
where Statistics Canada has not yet published all 12 months of data. This
prevents partial years from showing misleadingly low values on charts.
    """)

    st.markdown("---")

    # ── Section 6: Related pages ─────────────────────────────────────
    st.markdown("### 6. Related dashboard pages")
    st.markdown("""
- **Trade & Supply Chains** — Grain exports by destination, supply and
  disposition balances for major crops
- **Transportation & Exports** — Railway carloadings, trucking costs,
  and export logistics
- **Economic Impact Multipliers** — GDP and employment multipliers for
  agri-food industries
- **AI Research Assistant** — Ask natural-language questions about any
  dataset in this dashboard
    """)

from app.utils import global_footer
global_footer()
