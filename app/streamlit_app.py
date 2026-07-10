import datetime
import io
import json
import os
import tempfile
import re
import math
import numpy as np
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import urlencode, quote_plus
import sys  # NEW

import altair as alt
import pandas as pd
import requests
import streamlit as st
import streamlit.runtime as st_runtime

# Ensure the project root (parent of the app/ directory) is on sys.path so that
# we can import the top-level scripts package on Streamlit Cloud as well as locally.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from app.analytics import (
    AnalyticsOptions,
    compute_linear_trend,
    compute_moving_average,
    compute_yoy_change,
    flag_outliers,
)
from app.cpi_utils import apply_cpi_adjustment, detect_dollar_series, load_cpi_deflators
from dataset_descriptions import DATASET_DESCRIPTIONS
from app.unit_utils import get_unit_label, supports_inflation_adjustment
from app.utils import (
    apply_index_to_base_if_needed,
    DatasetLoadError,
    load_pipeline_status,
    load_tables_cfg_for_health,
    compute_data_health,
    build_share_url,
    load_dataset,
    safe_load_dataset,
    get_chart_png_bytes,
    load_table,
    ensure_year_column,
    pick_default_breakdown_option,
    compute_last_updated_period,
    _extract_year,
    format_last_period,
    get_table_metadata,
    safe_slug,
    render_source_caption,
    render_dataset_notes,
    clean_year_labels,
    load_omafra_fcr_by_county,
    load_omafra_attribution_county,
    build_download_name,
    altair_colour_scale,
    make_line_chart,
    compute_time_series_analytics,
    compute_yoy_analytics,
    _format_quantity_for_narrative,
    format_unit_for_narrative,
    _normalize_percent_value,
    build_narrative_summary,
    find_column_fuzzy,
    find_series_column,
    _get_param,
    _get_int_param,
    _get_bool_param,
    get_default_geos,
    get_default_series,
    multiselect_with_pins,
    STATCAN_METADATA_COLUMNS,
    show_data_freshness,
)
from app.farm_finance_view import render_farm_finance_view

# ── Extracted view renderers (Phase 3) ──
from app.views.county_census_view import render_county_census_view
from app.views.omafra_prices_view import render_omafra_prices_view
from app.views.farm_household_view import render_farm_household_view
from app.views.costs_inflation_view import render_costs_inflation_view
from app.views.farm_labour_view import render_farm_labour_view
from app.views.farm_finance_detail_view import render_farm_finance_detail_view
from app.views.demographics_view import render_demographics_view
from app.views.trade_supply_view import render_trade_supply_view
from app.views.environment_land_view import render_environment_land_view
from app.views.production_yields_view import render_production_yields_view
from app.views.transport_exports_view import render_transport_exports_view
from app.views.dairy_poultry_view import render_dairy_poultry_view
from app.views.aquaculture_view import render_aquaculture_view




from scripts import config_loader

# -------------------------
# Page + constants
# -------------------------
st.set_page_config(page_title="OFA Canada Farm Statistics Dashboard", layout="wide")

from app.utils import inject_standalone_mode
inject_standalone_mode()

st.title("OFA Canada Farm Statistics Dashboard")
st.caption(
    "Source: Statistics Canada and custom OFA datasets. Data may be subject to revision."
)

# ── Data Freshness Badge ──────────────────────────────────────────────────────
try:
    _health = compute_data_health()
    _last = _health.get("last_run")
    _active = _health.get("active_count", 0)
    _csvs = _health.get("csv_count", 0)
    _fails = _health.get("failed_tables", [])
    if _last:
        _badge = f"🟢 Data refreshed **{_last}** · {_active} tables · {_csvs} CSVs"
    else:
        _badge = f"📊 {_active} tables configured · {_csvs} CSVs loaded"
    if _fails:
        _badge += f" · ⚠️ {len(_fails)} table(s) failed"
    st.caption(_badge)
except Exception:
    pass  # Graceful fallback if health check fails

DATA_LATEST = Path("data/latest")
PIPELINE_STATUS_FP = Path("data/pipeline_status.json")
MANIFEST_FP = Path("data/manifest.json")

# ── At a Glance — Headline KPIs ──────────────────────────────────────────────
@st.cache_data(max_entries=5, show_spinner=False, ttl=3600)
def _load_headline_kpis():
    """Load and compute headline KPI values from Farm Cash Receipts & Net Income."""

    def _find_series(df, known_names):
        """Find the series/breakdown column by checking known StatCan names first."""
        for name in known_names:
            if name in df.columns:
                return name
        return find_series_column(df)

    kpis = {}
    try:
        # Farm Cash Receipts (32-10-0045-01)
        _fcr_cfg = get_table_metadata("32-10-0045-01") or {"id": "32-10-0045-01", "csv": "32-10-0045-01.csv"}
        _fcr = safe_load_dataset(_fcr_cfg)
        if _fcr is not None and not _fcr.empty:
            _fcr = ensure_year_column(_fcr)
            _geo_col = "GEO" if "GEO" in _fcr.columns else None
            _series_col = _find_series(_fcr, [
                "Type of cash receipts", "Farm cash receipts", "SERIES",
            ])
            if _geo_col:
                _fcr = _fcr[_fcr[_geo_col].str.contains("Canada", case=False, na=False)]
            if "VALUE" in _fcr.columns:
                _fcr["VALUE"] = pd.to_numeric(_fcr["VALUE"], errors="coerce")
            if "YEAR" in _fcr.columns:
                _fcr["YEAR"] = pd.to_numeric(_fcr["YEAR"], errors="coerce")
                _fcr = _fcr.dropna(subset=["YEAR", "VALUE"])
                _latest_year = int(_fcr["YEAR"].max())
                kpis["latest_year"] = _latest_year
                _fcr_latest = _fcr[_fcr["YEAR"] == _latest_year]
                _fcr_prev = _fcr[_fcr["YEAR"] == _latest_year - 1]

                if _series_col:
                    # Total Farm Cash Receipts
                    _total_mask = _fcr_latest[_series_col].str.contains("Total farm cash receipts", case=False, na=False)
                    _total_vals = _fcr_latest.loc[_total_mask, "VALUE"]
                    if not _total_vals.empty:
                        kpis["total_fcr"] = float(_total_vals.iloc[0])
                    # Crop receipts
                    _crop_mask = _fcr_latest[_series_col].str.contains("Total crop receipts", case=False, na=False)
                    _crop_vals = _fcr_latest.loc[_crop_mask, "VALUE"]
                    if not _crop_vals.empty:
                        kpis["crop_receipts"] = float(_crop_vals.iloc[0])
                    # Livestock receipts
                    _live_mask = _fcr_latest[_series_col].str.contains("Total livestock", case=False, na=False)
                    _live_vals = _fcr_latest.loc[_live_mask, "VALUE"]
                    if not _live_vals.empty:
                        kpis["livestock_receipts"] = float(_live_vals.iloc[0])
                    # YoY change
                    if not _fcr_prev.empty:
                        _prev_total_mask = _fcr_prev[_series_col].str.contains("Total farm cash receipts", case=False, na=False)
                        _prev_vals = _fcr_prev.loc[_prev_total_mask, "VALUE"]
                        if not _prev_vals.empty and kpis.get("total_fcr"):
                            _prev = float(_prev_vals.iloc[0])
                            if _prev > 0:
                                kpis["fcr_yoy_pct"] = ((kpis["total_fcr"] - _prev) / _prev) * 100

        # Net Farm Income (32-10-0052-01)
        _nfi_cfg = get_table_metadata("32-10-0052-01") or {"id": "32-10-0052-01", "csv": "32-10-0052-01.csv"}
        _nfi = safe_load_dataset(_nfi_cfg)
        if _nfi is not None and not _nfi.empty:
            _nfi = ensure_year_column(_nfi)
            _geo_col_n = "GEO" if "GEO" in _nfi.columns else None
            _series_col_n = _find_series(_nfi, [
                "Income components", "Farm income components", "SERIES",
            ])
            if _geo_col_n:
                _nfi = _nfi[_nfi[_geo_col_n].str.contains("Canada", case=False, na=False)]
            if "VALUE" in _nfi.columns:
                _nfi["VALUE"] = pd.to_numeric(_nfi["VALUE"], errors="coerce")
            if "YEAR" in _nfi.columns:
                _nfi["YEAR"] = pd.to_numeric(_nfi["YEAR"], errors="coerce")
                _nfi = _nfi.dropna(subset=["YEAR", "VALUE"])
                _nfi_year = int(_nfi["YEAR"].max())
                _nfi_latest = _nfi[_nfi["YEAR"] == _nfi_year]
                if _series_col_n:
                    # Realized net income
                    _ni_mask = _nfi_latest[_series_col_n].str.contains("Realized net income", case=False, na=False)
                    _ni_vals = _nfi_latest.loc[_ni_mask, "VALUE"]
                    if not _ni_vals.empty:
                        kpis["net_income"] = float(_ni_vals.iloc[0])
                    # Operating expenses
                    _exp_mask = _nfi_latest[_series_col_n].str.contains("Operating expenses after rebates", case=False, na=False)
                    _exp_vals = _nfi_latest.loc[_exp_mask, "VALUE"]
                    if not _exp_vals.empty:
                        kpis["total_expenses"] = float(_exp_vals.iloc[0])
    except Exception:
        pass
    return kpis



_headline_kpis = _load_headline_kpis()

if _headline_kpis:
    with st.expander("📊 At a Glance — Canada Agricultural Sector", expanded=True):
        _yr = _headline_kpis.get("latest_year", "")
        if _yr:
            st.caption(f"Latest available data: **{_yr}** · All values in thousands of dollars unless noted")

        _k1, _k2, _k3 = st.columns(3)

        def _fmt_kpi(val):
            """Format a KPI value (in $000s from StatCan) to human-readable."""
            if val is None:
                return "N/A"
            val_dollars = val * 1000  # StatCan reports in $000s
            if abs(val_dollars) >= 1e9:
                return f"${val_dollars / 1e9:.1f}B"
            if abs(val_dollars) >= 1e6:
                return f"${val_dollars / 1e6:.1f}M"
            return f"${val_dollars:,.0f}"

        with _k1:
            _fcr = _headline_kpis.get("total_fcr")
            _yoy = _headline_kpis.get("fcr_yoy_pct")
            st.metric(
                "Total Farm Cash Receipts",
                _fmt_kpi(_fcr),
                delta=f"{_yoy:+.1f}%" if _yoy is not None else None,
            )
        with _k2:
            st.metric("Crop Receipts", _fmt_kpi(_headline_kpis.get("crop_receipts")))
        with _k3:
            st.metric("Livestock Receipts", _fmt_kpi(_headline_kpis.get("livestock_receipts")))

        _k4, _k5, _k6 = st.columns(3)
        with _k4:
            st.metric("Realized Net Income", _fmt_kpi(_headline_kpis.get("net_income")))
        with _k5:
            st.metric("Operating Expenses", _fmt_kpi(_headline_kpis.get("total_expenses")))
        with _k6:
            _exp = _headline_kpis.get("total_expenses")
            _rev = _headline_kpis.get("total_fcr")
            if _exp and _rev and _rev > 0:
                _ratio = (_exp / _rev) * 100
                st.metric("Expense-to-Revenue Ratio", f"{_ratio:.1f}%")
            else:
                st.metric("Expense-to-Revenue Ratio", "N/A")
TABLES_YML = Path("config/tables.yml")

APP_BASE_URL = os.environ.get(
    "FARM_FINANCE_DASHBOARD_BASE_URL",
    "https://farmfinancedatabase-qdaadnipzfsrzqfh5yvwaz.streamlit.app",
)

# Load query params
params = st.query_params

# Load table metadata once
TABLE_CONFIG = config_loader.load_tables(active_only=True)
OMAFRA_PRICE_TABLES = [
    t
    for t in TABLE_CONFIG
    if t.get("active", True) and t.get("theme") == "Commodity prices (OMAFRA)"
]




VIEW_OPTIONS = [
    ("Farm finance statistics", "farm_finance"),
    ("County Level Census Stats (ON)", "county_census"),
    ("Costs & Inflation", "costs_inflation"),
    ("Transportation & Exports", "transport_exports"),
    ("Production & Yields", "production_yields"),
    ("Environment & Land Use", "environment_land"),
    ("Trade & Supply Chains (Agri-food)", "trade_supply"),
    ("Demographics, Labour & Technology", "demographics_labour_tech"),
    ("Dairy, Poultry & Eggs", "dairy_poultry"),
    ("Aquaculture & Fisheries", "aquaculture"),
]

if OMAFRA_PRICE_TABLES:
    VIEW_OPTIONS.append(("Commodity prices (OMAFRA)", "omafra_prices"))

view_labels = [label for label, _ in VIEW_OPTIONS]
view_lookup = {key: label for label, key in VIEW_OPTIONS}
default_view_key = VIEW_OPTIONS[0][1]
initial_view_key = _get_param(params, "view", default_view_key)
initial_view_label = view_lookup.get(initial_view_key, view_labels[0])

st.sidebar.header("Filters")
level = st.sidebar.radio(
    "Geography / View",
    view_labels,
    index=view_labels.index(initial_view_label),
    horizontal=False,
)
current_view_key = level
view_key = next(key for label, key in VIEW_OPTIONS if label == level)

with st.sidebar.expander("Analytics options", expanded=False):
    chart_mode_param = _get_param(params, "chart_mode", "level")
    ma_param = _get_int_param(params, "ma", 0) or 0
    trend_param = _get_bool_param(params, "trend", False)
    index_param = _get_bool_param(params, "index", False)
    outliers_param = _get_bool_param(params, "outliers", False)

    chart_mode_default_index = 1 if chart_mode_param == "yoy" else 0

    ma_options = ["None", "3-year", "10-year"]
    ma_default_label = {0: "None", 3: "3-year", 10: "10-year"}.get(ma_param, "None")
    ma_default_index = ma_options.index(ma_default_label)

    moving_average_label = st.selectbox(
        "Moving average",
        ma_options,
        index=ma_default_index,
        help="Overlay a simple rolling mean over the selected values.",
    )
    moving_average_window = {"None": None, "3-year": 3, "10-year": 10}[moving_average_label]

    show_trendline = st.checkbox(
        "Show linear trendline",
        value=trend_param,
        help="Overlay a linear regression trendline (requires at least 3 data points).",
    )

    chart_mode = st.radio(
        "Chart mode",
        ["Level (original values)", "Year-over-year % change"],
        index=chart_mode_default_index,
        help="Switch between raw levels and YoY percentage changes.",
    )

    index_checked = st.checkbox(
        "Normalize to index (base year = 100)",
        value=index_param,
        help="Re-express each series so the first year in the selected range equals 100.",
        key="index_to_base",
    )

    chart_mode_value = "yoy" if chart_mode == "Year-over-year % change" else "level"
    if chart_mode_value != "level":
        index_checked = False

    highlight_outliers = st.checkbox(
        "Highlight outliers (±2σ)",
        value=outliers_param,
        help="Visually flag points that deviate from the selected baseline.",
    )

analytics_options = AnalyticsOptions(
    moving_average_window=moving_average_window,
    show_trendline=show_trendline,
    chart_mode=chart_mode_value,
    highlight_outliers=highlight_outliers,
    index_to_base=index_checked,
)

selected_dataset_id: Optional[str] = None
selected_series_for_params: Optional[str] = None
selected_geos_for_params: list[str] = []
year_range_for_params: Optional[tuple[int, int]] = None
inflation_adjusted_for_params = False

# ============================================================
# VIEW DISPATCH — each view is now an extracted module
# ============================================================
_view_state = {}

if level == "County Level Census Stats (ON)":
    _view_state = render_county_census_view(params, analytics_options) or {}

elif level == "Commodity prices (OMAFRA)":
    _view_state = render_omafra_prices_view(params, analytics_options) or {}

elif level == "Farm finance statistics":
    _view_state = render_farm_finance_view(params=params, analytics_options=analytics_options) or {}

elif level == "Costs & Inflation":
    _view_state = render_costs_inflation_view(params, analytics_options) or {}

elif level == "Transportation & Exports":
    _view_state = render_transport_exports_view(params, analytics_options) or {}

elif level == "Production & Yields":
    _view_state = render_production_yields_view(params, analytics_options) or {}

elif level == "Environment & Land Use":
    _view_state = render_environment_land_view(params, analytics_options) or {}

elif level == "Trade & Supply Chains (Agri-food)":
    _view_state = render_trade_supply_view(params, analytics_options) or {}

elif level == "Demographics, Labour & Technology":
    _view_state = render_demographics_view(params, analytics_options) or {}

elif level == "Dairy, Poultry & Eggs":
    _view_state = render_dairy_poultry_view(params, analytics_options) or {}

elif level == "Aquaculture & Fisheries":
    _view_state = render_aquaculture_view(params, analytics_options) or {}

# Unpack view state for footer
if _view_state:
    selected_dataset_id = _view_state.get("selected_dataset_id")
    selected_series_for_params = _view_state.get("selected_series_for_params")
    selected_geos_for_params = _view_state.get("selected_geos_for_params", [])
    year_range_for_params = _view_state.get("year_range_for_params")
    inflation_adjusted_for_params = _view_state.get("inflation_adjusted_for_params", False)

adjust_for_inflation = inflation_adjusted_for_params

# --- Bridge variables for the footer ---
current_dataset_id = locals().get("selected_dataset_id")
selected_series_slug = locals().get("selected_series_for_params")
selected_geos = locals().get("selected_geos_for_params", [])
# Unpack year range if available, otherwise safe defaults
if locals().get("year_range_for_params"):
    start_year, end_year = year_range_for_params
else:
    start_year, end_year = 2010, 2023

# Ensure view key uses the slug, not the label
if "view_key" in locals():
    current_view_key = view_key

with st.sidebar:
    share_url = build_share_url(
        APP_BASE_URL,
        current_view_key,
        current_dataset_id,
        selected_series_slug,
        selected_geos,
        int(start_year),
        int(end_year),
        adjust_for_inflation,
        analytics_options,
    )

    st.markdown("---")
    with st.popover("Share this view", use_container_width=True):
        st.caption("Copy this link or share directly to social media.")
        st.code(share_url, language=None)
        st.link_button(
            "Share on X (Twitter)",
            f"https://twitter.com/intent/tweet?url={quote_plus(share_url)}",
        )
        st.link_button(
            "Share on LinkedIn",
            f"https://www.linkedin.com/sharing/share-offsite/?url={quote_plus(share_url)}",
        )

    health = compute_data_health()

    st.markdown("---")
    with st.expander("Data health", expanded=False):
        if health["last_run"]:
            st.caption(f"Last pipeline run: {health['last_run']}")
        else:
            st.caption("Last pipeline run: not available on this deployment.")

        st.caption(
            f"Local CSV files in data/latest: {health['csv_count']} "
            f"(out of {health['active_count']} active tables in tables.yml)."
        )

        if health["csv_count"] < health["active_count"]:
            st.caption(
                "Any missing tables will be fetched live from Statistics Canada "
                "the first time you view them."
            )

        failed = health["failed_tables"]
        if failed:
            st.caption("Tables that failed in the last pipeline run:")
            for tid in failed:
                st.text(f"• {tid}")
        else:
            st.caption("No failed tables reported in the last pipeline run.")

    # ── Sidebar: Data Freshness Indicator ──
    show_data_freshness()

from app.utils import global_footer
global_footer()
