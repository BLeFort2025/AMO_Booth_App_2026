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

import altair as alt
import pandas as pd
import requests
import streamlit as st

from app.smart_read import smart_read

from app.analytics import (
    AnalyticsOptions,
    compute_linear_trend,
    compute_moving_average,
    compute_yoy_change,
    flag_outliers,
)
from app.cpi_utils import apply_cpi_adjustment, load_cpi_deflators
from app.unit_utils import get_unit_label
from scripts import config_loader

# Constants
DATA_LATEST = Path("data/latest")
PIPELINE_STATUS_FP = Path("data/pipeline_status.json")

# Consistent colours for Canada + provinces
GEO_COLOURS = {
    "Canada": "#D00000",
    "British Columbia": "#FF9800",
    "Alberta": "#0D3692",
    "Saskatchewan": "#8BB800",
    "Manitoba": "#A07F37",
    "Ontario": "#007A30",
    "Quebec": "#001F97",
    "New Brunswick": "#F4C600",
    "Nova Scotia": "#00AFEF",
    "Prince Edward Island": "#00968C",
    "Newfoundland and Labrador": "#C2185B",
    "Yukon": "#7E57C2",
    "Northwest Territories": "#006064",
    "Nunavut": "#FF7043",
}

DEFAULT_SERIES_LABELS: dict[str, str] = {
    "32-10-0045-01": "Total farm cash receipts",
    "18-10-0004-01": "Food",
    "18-10-0004-03": "Food",
}

# Metadata columns from StatCan tables that should not be exposed as breakdowns
STATCAN_METADATA_COLUMNS: set[str] = {
    "DGUID",
    "VECTOR",
    "COORDINATE",
    "SCALAR_ID",
    "SCALAR_FACTOR",
    "STATUS",
    "SYMBOL",
    "TERMINATED",
    "DECIMALS",
    "UOM_ID",
    "UOM",
}

class DatasetLoadError(Exception):
    """
    Raised when the dashboard cannot load a dataset from local CSV
    or from a live StatCan download.
    """

    def __init__(self, table_id: str, kind: str, message: str):
        super().__init__(message)
        self.table_id = table_id
        self.kind = kind


def altair_colour_scale(present_geos: list[str]) -> alt.Scale:
    """Colour scale mapping geos to fixed colours."""
    domain: list[str] = []
    rng: list[str] = []

    for g in present_geos:
        if g in GEO_COLOURS:
            domain.append(g)
            rng.append(GEO_COLOURS[g])

    for g in present_geos:
        if g not in domain:
            domain.append(g)

    if rng:
        return alt.Scale(domain=domain, range=rng)
    return alt.Scale(domain=domain, scheme="tableau10")


@st.cache_data(max_entries=5, show_spinner=False, ttl=1800)
def load_pipeline_status():
    """Return a small dict from data/pipeline_status.json, or None if missing/invalid."""
    if not PIPELINE_STATUS_FP.exists():
        return None
    try:
        return json.loads(PIPELINE_STATUS_FP.read_text())
    except Exception:
        return None


@st.cache_resource(max_entries=5, show_spinner=False)
def load_tables_cfg_for_health():
    """Lightweight loader for tables.yml used only by the sidebar health panel."""
    try:
        return config_loader.load_tables_config()
    except Exception:
        return {"tables": []}


@st.cache_data(max_entries=5, show_spinner=False, ttl=1800)
def compute_data_health():
    """
    Compute a tiny "health" summary for the sidebar.

    Returns a dict with:
      - last_run (str | None): ISO timestamp or date of last pipeline run
      - active_count (int): number of active tables configured
      - csv_count (int): number of CSV files currently in data/latest
      - failed_tables (list[str]): tables that failed in the last pipeline run
    """
    cfg = load_tables_cfg_for_health()
    tables = cfg.get("tables", []) or []
    active_tables = [t for t in tables if t.get("active", True)]

    status = load_pipeline_status() or {}
    last_run = status.get("last_run_local")

    csv_count = 0
    if DATA_LATEST.exists():
        csv_count = sum(1 for _ in DATA_LATEST.glob("*.csv"))

    failed_tables = status.get("failed_tables") or []

    return {
        "last_run": last_run,
        "active_count": len(active_tables),
        "csv_count": csv_count,
        "failed_tables": failed_tables,
    }


def build_share_url(
    base_url,
    view_key,
    dataset_id,
    series_slug,
    selected_geos,
    start_year,
    end_year,
    adjust_for_inflation,
    analytics_options: AnalyticsOptions | None = None,
) -> str:
    """
    Build a sharable URL that encodes the current filters as query parameters.
    """
    opts = analytics_options or AnalyticsOptions()
    params = {
        "view": view_key,
        "dataset": dataset_id,
        "series": series_slug,
        "geos": ",".join(selected_geos),
        "start_year": int(start_year),
        "end_year": int(end_year),
        "inflation": "real" if adjust_for_inflation else "nominal",
        "chart_mode": "yoy" if opts.chart_mode == "yoy" else "level",
        "ma": str(opts.moving_average_window or 0),
        "trend": "1" if opts.show_trendline else "0",
        "index": "1" if opts.index_to_base else "0",
        "outliers": "1" if opts.highlight_outliers else "0",
    }
    try:
        st.query_params = params
    except Exception:
        pass
    return f"{base_url}/?{urlencode(params)}"


@st.cache_data(max_entries=3, show_spinner="Fetching from StatCan...", ttl=1800)
def _fetch_live_statcan(table_id: str) -> pd.DataFrame:
    from scripts.fetch_statcan import fetch_table
    df, _content_hash = fetch_table(table_id)
    return df


def load_dataset(table_cfg: dict) -> pd.DataFrame:
    """
    Load a dataset for the given table configuration.

    Priority:
      1. data/latest/{csv} if present
      2. Live StatCan download for StatCan-backed tables
    """
    table_id = table_cfg["id"]
    csv_name = table_cfg.get("csv") or f"{table_id}.csv"
    csv_path = Path(csv_name)
    latest_path = DATA_LATEST / csv_name

    # 1) Try configured CSV path first (supports custom directories)
    if csv_path.exists() or csv_path.with_suffix('.parquet').exists():
        return smart_read(csv_path)

    # 2) Try local CSV under data/latest
    if latest_path.exists() or latest_path.with_suffix('.parquet').exists():
        return smart_read(latest_path)

    # Determine whether this is a StatCan-backed table
    is_statcan = bool(table_cfg.get("statscan_url"))

    # 3) If not a StatCan table, we cannot fetch on demand
    if not is_statcan:
        raise DatasetLoadError(
            table_id=table_id,
            kind="local_missing",
            message=f"Local CSV {latest_path} for custom dataset {table_id} is missing.",
        )

    # 3) Live fallback: fetch from StatCan
    try:
        return _fetch_live_statcan(table_id)
    except requests.exceptions.RequestException as e:
        # Network / HTTP issues talking to StatCan
        raise DatasetLoadError(
            table_id=table_id,
            kind="statcan_unavailable",
            message=f"Statistics Canada request failed for {table_id}: {e}",
        ) from e
    except Exception as e:
        # Any other unexpected error
        raise DatasetLoadError(
            table_id=table_id,
            kind="generic",
            message=f"Unexpected error loading {table_id}: {e}",
        ) from e


def safe_load_dataset(table_cfg: dict) -> pd.DataFrame:
    """
    Wrapper around load_dataset that turns DatasetLoadError into friendly UI messages,
    including a retry button for transient StatCan issues.
    """
    try:
        return load_dataset(table_cfg)
    except DatasetLoadError as err:
        if err.kind == "statcan_unavailable":
            st.warning(
                f"Statistics Canada is not responding for this table ({err.table_id}). "
                "Please try again later."
            )
            if st.button("Retry loading this dataset", key="retry_load_dataset"):
                st.rerun()
            st.stop()
        elif err.kind == "local_missing":
            st.error(
                "This dataset depends on a local CSV file that is not available in this deployment. "
                "Please run the data pipeline and redeploy, or contact the OFA dashboard maintainer."
            )
            st.caption(str(err))
            st.stop()
        else:
            st.error("Something went wrong while loading this dataset.")
            st.caption(str(err))
            st.stop()


def get_chart_png_bytes(chart: alt.Chart, file_stem: str = "chart"):
    """Render an Altair chart to PNG bytes using a temporary file.

    Returns None if rendering fails.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            png_path = tmpdir_path / f"{file_stem}.png"
            # Save chart to a real file on disk
            chart.save(str(png_path), format="png")
            # Read bytes back
            png_bytes = png_path.read_bytes()
        return png_bytes
    except Exception:
        return None


def load_table(table_cfg: dict) -> pd.DataFrame:
    return safe_load_dataset(table_cfg)


def ensure_year_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure the DataFrame has a YEAR column.

    Tries, in order:
      - If YEAR already exists, just return df.
      - If 'Year' exists, rename it to YEAR.
      - If 'REF_DATE' exists, parse it into a year.
    If none of these are present, returns df unchanged.
    """
    if "YEAR" in df.columns:
        return df

    # Common alternate spelling
    if "Year" in df.columns:
        df = df.rename(columns={"Year": "YEAR"})
        return df

    # StatCan raw tables usually have REF_DATE; handle numeric and string cases
    if "REF_DATE" in df.columns:
        ref = df["REF_DATE"]
        if pd.api.types.is_numeric_dtype(ref):
            # REF_DATE already stores the year as a number
            year_vals = pd.to_numeric(ref, errors="coerce")
        else:
            # REF_DATE is a date-like string; parse and extract year
            year_vals = pd.to_datetime(ref.astype(str), errors="coerce").dt.year
        df = df.assign(YEAR=year_vals)
        return df

    return df


def pick_default_breakdown_option(df: pd.DataFrame, col: str, geo_col: str = "GEO"):
    """Choose a sensible default breakdown value.

    Preference order:
    1) First non-null value for the most recent Canada row (if GEO present)
    2) First non-null value in the column
    """

    if col not in df.columns:
        return None

    if geo_col in df.columns and "YEAR" in df.columns:
        canada_rows = df[df[geo_col].astype(str).str.contains("canada", case=False, na=False)]
        if not canada_rows.empty:
            latest_year = canada_rows["YEAR"].dropna().max()
            if pd.notna(latest_year):
                latest_rows = canada_rows[canada_rows["YEAR"] == latest_year]
                candidates = latest_rows[col].dropna()
                if not candidates.empty:
                    return candidates.iloc[0]

    non_null = df[col].dropna()
    if not non_null.empty:
        return non_null.iloc[0]

    return None


def compute_last_updated_period(df: pd.DataFrame) -> Optional[object]:
    """Safely compute the last available period from common date columns."""

    try:
        if "REF_DATE" in df.columns:
            ref_date = pd.to_datetime(df["REF_DATE"], errors="coerce")
            if ref_date.notna().any():
                return ref_date.max()
            numeric_ref = pd.to_numeric(df["REF_DATE"], errors="coerce")
            if numeric_ref.notna().any():
                return numeric_ref.max()

        for col in ["Year", "year", "YEAR"]:
            if col in df.columns:
                numeric_year = pd.to_numeric(df[col], errors="coerce")
                if numeric_year.notna().any():
                    return numeric_year.max()
    except Exception:
        return None

    return None


def _extract_year(value) -> Optional[int]:
    """
    Given a time value from the time column, return an integer year if possible.

    Handles:
      - ints / floats / year-like strings ("2020")
      - pandas.Timestamp
      - datetime.date / datetime.datetime
      - numpy.datetime64

    Returns None if the year cannot be determined.
    """
    if value is None:
        return None

    # pandas / python datetime objects
    if isinstance(value, (pd.Timestamp, datetime.date, datetime.datetime)):
        return int(value.year)

    # numpy datetime64
    if isinstance(value, np.datetime64):
        try:
            return int(pd.to_datetime(value).year)
        except Exception:
            return None

    # Already numeric or numeric-like string
    try:
        return int(value)
    except Exception:
        try:
            return int(float(str(value)))
        except Exception:
            return None


def format_last_period(last_period: object) -> str:
    """Format the last period for display with sensible date handling."""

    try:
        if isinstance(last_period, (pd.Timestamp, datetime.date, datetime.datetime)):
            month = getattr(last_period, "month", None)
            day = getattr(last_period, "day", None)

            if month == 1 and day == 1:
                return last_period.strftime("%Y")

            return last_period.strftime("%Y-%m")

        if isinstance(last_period, (int, float)):
            if isinstance(last_period, float) and not last_period.is_integer():
                return str(last_period)
            return str(int(last_period))

    except Exception:
        return str(last_period)

    return str(last_period)


def get_table_metadata(table_id: str) -> dict:
    """Fetch table metadata from configuration if available."""

    # TABLE_CONFIG is loaded in streamlit_app.py usually, we might need to load it here or pass it?
    # To avoid circular import or reloading, we can load it fresh here as it is cached by config_loader
    try:
        full_cfg = config_loader.load_tables(active_only=True)
    except Exception:
        return {}
    
    if isinstance(full_cfg, list):
        for t in full_cfg:
            if str(t.get("id")) == str(table_id):
                return t
    elif isinstance(full_cfg, dict):
        if str(full_cfg.get("id")) == str(table_id):
            return full_cfg
    return {}


def safe_slug(text: str | None) -> str:
    if not text:
        return ""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", str(text).strip().lower())
    return slug.strip("_")


def render_source_caption(table_cfg: Mapping | None) -> None:
    """Render a standardized source caption for the selected dataset."""

    if not isinstance(table_cfg, Mapping):
        st.caption("Source: Statistics Canada. Data may be subject to revision.")
        return

    source = table_cfg.get("source", "statcan")
    if source == "omafra":
        st.caption(
            "Source: Ontario Ministry of Agriculture, Food and Rural Affairs "
            "(OMAFRA). Data may be subject to revision."
        )
        return

    table_id = str(table_cfg.get("id", "")).strip()
    statscan_url = table_cfg.get("statscan_url")
    if not statscan_url and table_id:
        pid = table_id.replace("-", "")
        statscan_url = f"https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid={pid}"

    if statscan_url and table_id:
        st.markdown(
            f"Source: Statistics Canada table [**{table_id}**]({statscan_url}). "
            "Data may be subject to revision."
        )
    else:
        st.caption("Source: Statistics Canada. Data may be subject to revision.")


def render_dataset_notes(table_cfg: dict | None) -> None:
    if not isinstance(table_cfg, dict):
        return

    notes = table_cfg.get("notes")
    if not notes:
        return

    with st.expander("Dataset notes & definitions"):
        if isinstance(notes, (list, tuple)):
            for line in notes:
                st.markdown(f"- {line}")
        elif isinstance(notes, dict):
            for key, value in notes.items():
                st.markdown(f"**{key}:** {value}")
        else:
            st.write(notes)


def clean_year_labels(year_vals) -> list[str]:
    """Extract numeric year labels and adjust duplicated terminal year."""

    years: list[int] = []
    for val in year_vals:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        if isinstance(val, (int, float)):
            years.append(int(val))
            continue
        match = re.search(r"(\d{4})", str(val))
        if match:
            years.append(int(match.group(1)))

    if len(years) >= 2 and years[-1] == max(years) and years[-2] == years[-1]:
        years[-1] = years[-1] + 1

    return [str(y) for y in years]


def build_download_name(
    dataset_label: str,
    series_label: str | None,
    yr_min: int | None,
    yr_max: int | None,
    geos: list[str],
) -> str:
    """Create a friendly download filename for chart export."""
    parts: list[str] = [dataset_label]
    if series_label:
        parts.append(series_label)
    if yr_min is not None and yr_max is not None:
        parts.append(f"{yr_min}-{yr_max}")
    if geos:
        parts.append(", ".join(geos[:3]) + ("" if len(geos) <= 3 else ", …"))

    name = " — ".join(parts)
    name = re.sub(r"[\\/:*?\"<>|]+", "-", name)  # illegal path chars
    name = re.sub(r"\s+", " ", name).strip()
    return name


def make_line_chart(
    long_df: pd.DataFrame,
    y_title: str,
    present_geos: list[str],
    value_col: str = "VALUE",
    color_col: str = "GEO",
    color_title: str = "Geography",
    tooltip_fields: list[tuple[str, str]] | None = None,
    analytics_options: AnalyticsOptions | None = None,
    value_title: str | None = None,
) -> alt.Chart:
    """Altair line chart (YEAR, GEO, VALUE) for annual data."""

    chart_df = long_df.copy()
    analytics = analytics_options or AnalyticsOptions()

    if "YEAR" not in chart_df.columns:
        chart_df["YEAR"] = chart_df.index

    # Ensure numeric year for calculations
    chart_df["YEAR"] = pd.to_numeric(chart_df["YEAR"], errors="coerce")
    chart_df = chart_df.dropna(subset=["YEAR", value_col]).copy()

    group_cols = [color_col] if color_col in chart_df.columns else None
    time_col = "YEAR" if "YEAR" in chart_df.columns else ("DATE" if "DATE" in chart_df.columns else None)
    plot_value_col = value_col
    y_axis_title = y_title

    if analytics.chart_mode == "yoy":
        chart_df = compute_yoy_change(chart_df, value_col, group_cols=group_cols)
        plot_value_col = f"{value_col}_yoy_pct"
        chart_df = chart_df.dropna(subset=[plot_value_col]).copy()
        y_axis_title = f"{y_title} — YoY % change"

    ma_col = None
    if analytics.moving_average_window:
        chart_df = compute_moving_average(
            chart_df,
            plot_value_col,
            window=analytics.moving_average_window,
            group_cols=group_cols,
        )
        ma_col = f"{plot_value_col}_ma_{analytics.moving_average_window}"

    trend_col = None
    if analytics.show_trendline:
        chart_df = compute_linear_trend(
            chart_df, plot_value_col, group_cols=group_cols
        )
        trend_col = f"{plot_value_col}_trend"

    if analytics.highlight_outliers and time_col is not None:
        outlier_group_cols = group_cols or []
        chart_df = flag_outliers(
            chart_df,
            value_col=plot_value_col,
            group_cols=outlier_group_cols,
            time_col=time_col,
        )
    else:
        chart_df = chart_df.copy()
        chart_df["is_outlier"] = False

    chart_df["YEAR_DISPLAY"] = chart_df["YEAR"].astype(int).astype(str)
    scale = altair_colour_scale(present_geos)

    tooltip_value_title = value_title or "Value"
    base_tooltip = [
        alt.Tooltip("YEAR_DISPLAY:O", title="Year", format="d"),
        alt.Tooltip(f"{color_col}:N", title=color_title),
        alt.Tooltip(f"{plot_value_col}:Q", title=tooltip_value_title, format=","),
    ]

    if tooltip_fields:
        for field, title in tooltip_fields:
            if field == color_col:
                continue
            base_tooltip.append(alt.Tooltip(f"{field}:N", title=title))

    base_chart = alt.Chart(chart_df)
    if analytics.chart_mode == "yoy":
        base_mark = base_chart.mark_bar()
    else:
        base_mark = base_chart.mark_line(point=True)

    chart = (
        base_mark.encode(
            x=alt.X("YEAR_DISPLAY:O", title="Year", axis=alt.Axis(format="d")),
            y=alt.Y(f"{plot_value_col}:Q", title=y_axis_title, axis=alt.Axis(format="~s")),
            color=alt.Color(f"{color_col}:N", title=color_title, scale=scale),
            tooltip=base_tooltip,
        )
        .properties(height=420)
        .interactive()
    )

    layers = [chart]

    if ma_col:
        ma_layer = (
            alt.Chart(chart_df)
            .mark_line(strokeDash=[4, 4], strokeWidth=1.5)
            .encode(
                x=alt.X("YEAR_DISPLAY:O", title="Year", axis=alt.Axis(format="d")),
                y=alt.Y(f"{ma_col}:Q", title=y_axis_title, axis=alt.Axis(format="~s")),
                color=alt.Color(f"{color_col}:N", title=color_title, scale=scale),
                tooltip=base_tooltip
            )
        )
        layers.append(ma_layer)

    if trend_col:
        trend_layer = (
            alt.Chart(chart_df)
            .mark_line(strokeDash=[2, 1], strokeWidth=1.5)
            .encode(
                x=alt.X("YEAR_DISPLAY:O", title="Year", axis=alt.Axis(format="d")),
                y=alt.Y(f"{trend_col}:Q", title=y_axis_title, axis=alt.Axis(format="~s")),
                color=alt.Color(f"{color_col}:N", title=color_title, scale=scale),
                tooltip=base_tooltip,
            )
        )
        layers.append(trend_layer)

    outliers_df = chart_df[chart_df.get("is_outlier", False)].copy()
    if not outliers_df.empty:
        x_field = "YEAR_DISPLAY" if "YEAR_DISPLAY" in outliers_df.columns else (time_col or "YEAR")
        tooltip = [
            alt.Tooltip(f"{x_field}:O", title="Year", format="d"),
            alt.Tooltip(f"{color_col}:N", title=color_title)
            if color_col in outliers_df.columns
            else None,
            alt.Tooltip(f"{plot_value_col}:Q", title="Value", format=","),
        ]
        tooltip = [t for t in tooltip if t is not None]
        color_encoding = (
            alt.Color(f"{color_col}:N", title=color_title, scale=scale)
            if color_col in outliers_df.columns
            else alt.value("Outlier")
        )
        outlier_layer = (
            alt.Chart(outliers_df)
            .mark_point(size=80, shape="triangle-up", color="red")
            .encode(
                x=alt.X(f"{x_field}:O", title="Year", axis=alt.Axis(format="d")),
                y=alt.Y(f"{plot_value_col}:Q", title=y_axis_title, axis=alt.Axis(format="~s")),
                color=color_encoding,
                tooltip=tooltip,
            )
        )
        layers.append(outlier_layer)

    return alt.layer(*layers).resolve_scale(color="shared")


def compute_time_series_analytics(
    df: pd.DataFrame,
    value_col: str,
    time_col: str = "YEAR",
    table_cfg: Mapping | None = None,
    table_id: str | None = None,
) -> dict:
    """
    Compute basic analytics for a time series aggregated by year.

    Returns a dict with keys:
      - cagr_5y (float | None): annualized growth rate over the last ~5 years,
                                if there are at least 6 years of data and both
                                endpoints are positive.
      - min_year (int | None)
      - min_value (float | None)
      - max_year (int | None)
      - max_value (float | None)
      - growth_volatility (float | None): std dev of YoY percentage changes (0–100 scale).
      - latest_value (float | None): latest aggregated value in the selection.
    """
    if df.empty or value_col not in df.columns or time_col not in df.columns:
        return {
            "cagr_5y": None,
            "min_year": None,
            "min_value": None,
            "max_year": None,
            "max_value": None,
            "growth_volatility": None,
            "latest_value": None,
        }

    # Include a few useful extra columns (if present) but avoid duplicating the time/value columns.
    extra_cols = [
        col
        for col in ["YEAR", "GEO", "SERIES"]
        if col in df.columns and col not in {time_col, value_col}
    ]
    cols = [time_col, value_col] + extra_cols

    tmp = (
        df[cols]
        .dropna(subset=[time_col, value_col])
        .copy()
    )
    if tmp.empty:
        return {
            "cagr_5y": None,
            "min_year": None,
            "min_value": None,
            "max_year": None,
            "max_value": None,
            "growth_volatility": None,
            "latest_value": None,
        }

    # Aggregate across geographies: total per year
    agg = (
        tmp.groupby(time_col, as_index=False)[value_col]
        .sum()
        .sort_values(time_col)
    )
    if len(agg) < 2:
        return {
            "cagr_5y": None,
            "min_year": None,
            "min_value": None,
            "max_year": None,
            "max_value": None,
            "growth_volatility": None,
            "latest_value": None,
        }

    # Min / max
    min_idx = agg[value_col].idxmin()
    max_idx = agg[value_col].idxmax()
    min_row = agg.loc[min_idx]
    max_row = agg.loc[max_idx]

    min_year = _extract_year(min_row[time_col])
    min_value = float(min_row[value_col])

    max_year = _extract_year(max_row[time_col])
    max_value = float(max_row[value_col])
    latest_value = float(agg[value_col].iloc[-1])

    start_year = _extract_year(agg[time_col].iloc[0])
    end_year = _extract_year(agg[time_col].iloc[-1])
    if start_year is not None and end_year is not None:
        years_span = end_year - start_year
    else:
        years_span = 0
    if (
        years_span >= 5
        and agg[value_col].iloc[0] > 0
        and agg[value_col].iloc[-1] > 0
    ):
        cagr_5y = (agg[value_col].iloc[-1] / agg[value_col].iloc[0]) ** (
            5 / years_span
        ) - 1
    else:
        cagr_5y = None

    # Volatility of YoY growth rates
    growth_volatility = None
    try:
        agg = agg.sort_values(time_col).copy()
        agg["prev"] = agg[value_col].shift(1)
        valid = agg[(agg["prev"].notna()) & (agg["prev"] != 0)]
        if not valid.empty:
            growth_rates = (valid[value_col] - valid["prev"]) / valid["prev"]
            if not growth_rates.empty:
                growth_volatility = float(growth_rates.std()) * 100.0
    except Exception:
        growth_volatility = None

    return {
        "cagr_5y": cagr_5y,
        "min_year": min_year,
        "min_value": min_value,
        "max_year": max_year,
        "max_value": max_value,
        "growth_volatility": growth_volatility,
        "latest_value": latest_value,
    }


def compute_yoy_analytics(
    df: pd.DataFrame,
    value_col: str,
    time_col: str = "YEAR",
) -> dict:
    """
    Compute analytics on year-over-year % changes for an aggregated time series.

    Returns a dict with keys:
      - latest_yoy (float | None)
      - mean_yoy (float | None)
      - min_yoy (float | None)
      - min_yoy_year (int | None)
      - max_yoy (float | None)
      - max_yoy_year (int | None)
      - volatility_yoy (float | None): std dev of YoY % changes in percent points.
    """
    if df.empty or value_col not in df.columns or time_col not in df.columns:
        return {
            "latest_yoy": None,
            "mean_yoy": None,
            "min_yoy": None,
            "min_yoy_year": None,
            "max_yoy": None,
            "max_yoy_year": None,
            "volatility_yoy": None,
        }

    agg = (
        df[[time_col, value_col]]
        .dropna(subset=[time_col, value_col])
        .groupby(time_col, as_index=False)[value_col]
        .sum()
        .sort_values(time_col)
    )

    agg["prev"] = agg[value_col].shift(1)
    valid = agg[(agg["prev"].notna()) & (agg["prev"] != 0)]
    if len(valid) < 2:
        return {
            "latest_yoy": None,
            "mean_yoy": None,
            "min_yoy": None,
            "min_yoy_year": None,
            "max_yoy": None,
            "max_yoy_year": None,
            "volatility_yoy": None,
        }

    yoy = (valid[value_col] - valid["prev"]) / valid["prev"] * 100.0

    if len(yoy) < 1:
        return {
            "latest_yoy": None,
            "mean_yoy": None,
            "min_yoy": None,
            "min_yoy_year": None,
            "max_yoy": None,
            "max_yoy_year": None,
            "volatility_yoy": None,
        }

    latest_time = valid[time_col].max()
    latest_row = valid[valid[time_col] == latest_time].iloc[-1]
    latest_yoy = float(yoy.loc[latest_row.name]) if not yoy.empty else None

    min_idx = yoy.idxmin()
    max_idx = yoy.idxmax()

    volatility = yoy.std()
    if pd.isna(volatility):
        volatility = None

    return {
        "latest_yoy": latest_yoy,
        "mean_yoy": float(yoy.mean()) if not yoy.empty else None,
        "min_yoy": float(yoy.loc[min_idx]) if pd.notnull(min_idx) else None,
        "min_yoy_year": _extract_year(valid.loc[min_idx, time_col]) if pd.notnull(min_idx) else None,
        "max_yoy": float(yoy.loc[max_idx]) if pd.notnull(max_idx) else None,
        "max_yoy_year": _extract_year(valid.loc[max_idx, time_col]) if pd.notnull(max_idx) else None,
        "volatility_yoy": float(volatility) if volatility is not None else None,
    }

def _normalize_percent_value(value: float | None) -> float | None:
    """
    Normalize a value that may be stored either as a fraction (0.058)
    or already as a percent (5.8).

    If abs(value) < 1, treat it as a fraction and convert to percent.
    Otherwise, return as-is.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v):
        return None
    if abs(v) < 1.0:
        return v * 100.0
    return v

def _extract_scalar_from_unit_label(unit_label: str | None) -> tuple[float, str]:
    """
    Extract the scalar multiplier and base unit from a unit label.

    Examples:
        'Dollars (× 1,000)'     -> (1000.0,  'Dollars')
        'Dollars (× 1,000,000)' -> (1e6,     'Dollars')
        'Index, 2016=100'       -> (1.0,     'Index, 2016=100')
        None                    -> (1.0,     '')
    """
    if not unit_label:
        return 1.0, ""

    import re
    # Match patterns like "(× 1,000)" or "(x 1,000,000)"
    m = re.search(r'\(\s*[×x]\s*([\d,]+)\s*\)', unit_label)
    if m:
        scalar_str = m.group(1).replace(',', '')
        try:
            scalar = float(scalar_str)
        except ValueError:
            scalar = 1.0
        base_unit = unit_label[:m.start()].strip()
        return scalar, base_unit

    return 1.0, unit_label


def _format_quantity_for_narrative(value: float | None, unit_label: str | None) -> str:
    """
    Format a numeric value for use in narrative text.

    - Applies the scalar multiplier embedded in the unit label (e.g. "× 1,000").
    - Uses thousands/millions/billions with one decimal place.
    - Uses "$" prefix for dollar-denominated units.
    - Returns an empty string if value is None or NaN.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""

    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""

    # Apply scalar multiplier from the unit label
    scalar, base_unit = _extract_scalar_from_unit_label(unit_label)
    v = v * scalar

    # Determine if this is a dollar unit
    is_dollar = base_unit.lower().startswith('dollar') or '$' in (base_unit or '')

    abs_v = abs(v)
    if abs_v >= 1e9:
        magnitude = f"{v / 1e9:.1f} billion"
    elif abs_v >= 1e6:
        magnitude = f"{v / 1e6:.1f} million"
    elif abs_v >= 1e3:
        magnitude = f"{v / 1e3:.1f} thousand"
    else:
        magnitude = f"{v:,.0f}"

    if is_dollar:
        return f"${magnitude}"
    if base_unit:
        return f"{magnitude} {base_unit}"
    return magnitude


def format_unit_for_narrative(
    unit_lbl: str | None,
    *,
    source: str | None = None,
    theme: str | None = None,
    table_id: str | None = None,
) -> str | None:
    """Return a cleaned unit label for narrative text, with OMAFRA tweaks.

    The scalar suffix (e.g. '(× 1,000)') is preserved so that
    _format_quantity_for_narrative can extract and apply it.
    """

    unit = (unit_lbl or "").strip()
    if source == "omafra" or theme == "Commodity prices (OMAFRA)" or table_id == "omafra-average-weekly-corn-prices":
        normalized = unit.replace(" ", "").lower()
        if normalized == "$/bushel":
            return "dollars per bushel"
    return unit_lbl


def build_narrative_summary(
    dataset_title: str,
    analytics_level: dict | None,
    analytics_yoy: dict | None,
    analytics_options: AnalyticsOptions,
    last_year: int | None,
    unit_label: str | None,
    table_cfg: Mapping | None = None,
    table_id: str | None = None,
    df: pd.DataFrame | None = None,
    label_col: str | None = None,
    value_col: str | None = None,
    max_groups: int = 3,
) -> str:
    """
    Build a short narrative summary for the current chart selection.
    """
    main_sentences: list[str] = []
    series_sentences: list[str] = []

    table_source = table_cfg.get("source") if isinstance(table_cfg, Mapping) else None
    table_theme = table_cfg.get("theme") if isinstance(table_cfg, Mapping) else None
    table_identifier = table_id or (table_cfg.get("id") if isinstance(table_cfg, Mapping) else None)

    narrative_unit_label = format_unit_for_narrative(
        unit_label,
        source=table_source,
        theme=table_theme,
        table_id=table_identifier,
    )

    highlight_values = not (
        table_source == "omafra"
        or table_theme == "Commodity prices (OMAFRA)"
        or table_identifier == "omafra-average-weekly-corn-prices"
    )

    def _emphasize(text: str | None) -> str:
        if not text:
            return ""
        return f"**{text}**" if highlight_values else text

    # Derive a shorter metric name for narrative
    # If the title contains an em dash, use the part after it; otherwise use the full title.
    metric_name = dataset_title
    if "—" in dataset_title:
        metric_name = dataset_title.split("—", 1)[1].strip()

    if analytics_options.chart_mode == "level" and analytics_level is not None:
        latest_value = analytics_level.get("latest_value")
        cagr_5y = analytics_level.get("cagr_5y")
        min_value = analytics_level.get("min_value")
        min_year = analytics_level.get("min_year")
        max_value = analytics_level.get("max_value")
        max_year = analytics_level.get("max_year")
        growth_volatility = analytics_level.get("growth_volatility")

        cagr_pct = _normalize_percent_value(cagr_5y)
        volatility_pct = _normalize_percent_value(growth_volatility)

        latest_str = _format_quantity_for_narrative(latest_value, narrative_unit_label)
        min_str = _format_quantity_for_narrative(min_value, narrative_unit_label)
        max_str = _format_quantity_for_narrative(max_value, narrative_unit_label)

        latest_display = _emphasize(latest_str)
        cagr_display = _emphasize(f"{cagr_pct:.1f}%" if cagr_pct is not None else "")
        min_display = _emphasize(min_str)
        max_display = _emphasize(max_str)
        volatility_display = _emphasize(
            f"{volatility_pct:.1f}%" if volatility_pct is not None else ""
        )

        if last_year is not None and latest_str:
            main_sentences.append(
                f"In {last_year}, **{metric_name}** across the selected geographies was approximately {latest_display}."
            )

        if cagr_pct is not None:
            if cagr_pct > 0.5:
                direction = f"growing at roughly {_emphasize(f'{abs(cagr_pct):.1f}%')} per year"
            elif cagr_pct < -0.5:
                direction = f"declining at roughly {_emphasize(f'{abs(cagr_pct):.1f}%')} per year"
            else:
                direction = f"roughly stable (about {_emphasize(f'{abs(cagr_pct):.1f}%')} annual change)"
            main_sentences.append(
                f"Over the past five years, values have been {direction}."
            )

        if min_str and min_year is not None and max_str and max_year is not None:
            range_sentence = f"Over the selected period, values ranged from a low of {min_display} in {min_year} to a high of {max_display} in {max_year}."
            if volatility_pct is not None:
                if volatility_pct > 10:
                    range_sentence += f" Year-to-year swings have been large ({volatility_display})."
                elif volatility_pct > 5:
                    range_sentence += f" Year-to-year variability has been moderate ({volatility_display})."
                else:
                    range_sentence += f" Values have been relatively stable year to year ({volatility_display})."
            main_sentences.append(range_sentence)

    if analytics_options.chart_mode == "yoy" and analytics_yoy is not None:
        latest_yoy = _normalize_percent_value(analytics_yoy.get("latest_yoy"))
        mean_yoy = _normalize_percent_value(analytics_yoy.get("mean_yoy"))
        min_yoy = _normalize_percent_value(analytics_yoy.get("min_yoy"))
        min_yoy_year = analytics_yoy.get("min_yoy_year")
        max_yoy = _normalize_percent_value(analytics_yoy.get("max_yoy"))
        max_yoy_year = analytics_yoy.get("max_yoy_year")
        volatility_yoy = _normalize_percent_value(analytics_yoy.get("volatility_yoy"))

        if last_year is not None and latest_yoy is not None:
            latest_yoy_display = _emphasize(f"{latest_yoy:.1f}%")
            main_sentences.append(
                f"In {last_year}, the year-over-year change in **{metric_name}** across the selected geographies was {latest_yoy_display}."
            )

        if mean_yoy is not None and volatility_yoy is not None:
            mean_yoy_display = _emphasize(f"{mean_yoy:.1f}%")
            vol_yoy_display = _emphasize(f"{volatility_yoy:.1f}")
            main_sentences.append(
                f"On average, values changed by about {mean_yoy_display} per year, with year-to-year fluctuations of roughly {vol_yoy_display} percentage points."
            )

        if (
            min_yoy is not None
            and min_yoy_year is not None
            and max_yoy is not None
            and max_yoy_year is not None
        ):
            min_yoy_display = _emphasize(f"{min_yoy:.1f}%")
            max_yoy_display = _emphasize(f"{max_yoy:.1f}%")
            main_sentences.append(
                f"Annual changes ranged from {min_yoy_display} in {min_yoy_year} to {max_yoy_display} in {max_yoy_year}."
            )

    if (
        df is not None
        and label_col is not None
        and value_col is not None
        and label_col in df.columns
        and value_col in df.columns
        and df[label_col].nunique() > 1
    ):
        labels = sorted(df[label_col].dropna().unique().tolist())
        labels = labels[:max_groups]

        for label in labels:
            sub = df[df[label_col] == label].copy()
            if sub.empty:
                continue

            last_year_series = (
                int(sub["YEAR"].max())
                if "YEAR" in sub.columns and not sub["YEAR"].empty
                else None
            )

            analytics_series_level = None
            analytics_series_yoy = None

            try:
                analytics_series_level = compute_time_series_analytics(
                    sub,
                    value_col=value_col,
                    time_col="YEAR",
                    table_cfg=table_cfg,
                    table_id=table_identifier,
                )
            except Exception:
                analytics_series_level = None

            try:
                analytics_series_yoy = compute_yoy_analytics(
                    sub, value_col=value_col, time_col="YEAR"
                )
            except Exception:
                analytics_series_yoy = None

            if analytics_options.chart_mode == "level" and analytics_series_level is not None:
                s_latest = _format_quantity_for_narrative(
                    analytics_series_level.get("latest_value"), narrative_unit_label
                )
                s_min = _format_quantity_for_narrative(
                    analytics_series_level.get("min_value"), narrative_unit_label
                )
                s_max = _format_quantity_for_narrative(
                    analytics_series_level.get("max_value"), narrative_unit_label
                )
                s_min_year = analytics_series_level.get("min_year")
                s_max_year = analytics_series_level.get("max_year")
                s_vol = _normalize_percent_value(analytics_series_level.get("growth_volatility"))

                parts: list[str] = []
                if last_year_series is not None and s_latest:
                    parts.append(f"latest value in {last_year_series} was about {s_latest}")
                if s_min and s_min_year is not None and s_max and s_max_year is not None:
                    parts.append(f"ranged from {s_min} in {s_min_year} to {s_max} in {s_max_year}")
                if s_vol is not None:
                    parts.append(f"with annual growth volatility around {s_vol:.1f}%")

                if parts:
                    series_sentences.append(
                        f"For {label}, the " + "; ".join(parts) + "."
                    )

            if analytics_options.chart_mode == "yoy" and analytics_series_yoy is not None:
                s_latest_yoy = _normalize_percent_value(analytics_series_yoy.get("latest_yoy"))
                s_mean_yoy = _normalize_percent_value(analytics_series_yoy.get("mean_yoy"))
                s_vol_yoy = _normalize_percent_value(analytics_series_yoy.get("volatility_yoy"))

                parts = []
                if last_year_series is not None and s_latest_yoy is not None:
                    parts.append(
                        f"latest year-over-year change in {last_year_series} was {s_latest_yoy:.1f}%"
                    )
                if s_mean_yoy is not None:
                    parts.append(f"averaged about {s_mean_yoy:.1f}% per year")
                if s_vol_yoy is not None:
                    parts.append(
                        f"with volatility near {s_vol_yoy:.1f} percentage points"
                    )

                if parts:
                    series_sentences.append(
                        f"For {label}, the " + "; ".join(parts) + "."
                    )

    paragraphs: list[str] = []

    if main_sentences:
        paragraphs.append(" ".join(main_sentences))

    if series_sentences:
        bullet_lines = "\n".join(f"- {s}" for s in series_sentences)
        paragraphs.append("By geography / series:\n" + bullet_lines)

    if not paragraphs:
        return ""

    return "\n\n".join(paragraphs).strip()


def find_column_fuzzy(df: pd.DataFrame, search_terms: list[str]) -> str | None:
    """Return first column whose name contains any of the given search terms (case-insensitive)."""
    cols = list(df.columns)
    lower_cols = [c.lower() for c in cols]
    for term in search_terms:
        t = term.lower()
        for col, col_lower in zip(cols, lower_cols):
            if t in col_lower:
                return col
    return None

def find_series_column(table_id: str, df: pd.DataFrame) -> Optional[str]:
    """Figure out which column should be treated as the 'series' selector."""

    # ---------- Farm finance core tables ----------

    # Farm cash receipts
    if table_id == "32-10-0045-01" and "Type of cash receipts" in df.columns:
        return "Type of cash receipts"

    # Farm operating revenues & expenses (ATDP)
    if table_id == "32-10-0136-01":
        if "Estimates" in df.columns:
            return "Estimates"
        if "Revenues and expenses" in df.columns:
            return "Revenues and expenses"

    if table_id == "32-10-0078-01":
        for c in ["Farm type", "Type of farm", "Type of farm operation"]:
            if c in df.columns:
                return c

    # Farm operating expenses & depreciation charges
    if table_id == "32-10-0049-01" and "Expenses and rebates" in df.columns:
        return "Expenses and rebates"

    # Farm capital (value of assets)
    if table_id == "32-10-0050-01" and "Farm items" in df.columns:
        return "Farm items"

    # Farm debt outstanding
    if table_id == "32-10-0051-01" and "Type of lender" in df.columns:
        return "Type of lender"

    # Balance sheet of the agricultural sector
    if table_id == "32-10-0056-01":
        if "Balance sheet item" in df.columns:
            return "Balance sheet item"
        if "Commodities" in df.columns:
            return "Commodities"

    # Net farm income, by components
    if table_id == "32-10-0052-01":
        for c in ["Income components", "Net farm income components", "Component"]:
            if c in df.columns:
                return c

    # Direct program payments to producers
    if table_id == "32-10-0106-01":
        for c in [
            "Direct payments and rebates",
            "Direct program payments",
            "Program",
            "Program type",
        ]:
            if c in df.columns:
                return c

    # Agriculture value added account
    if table_id == "32-10-0048-01":
        for c in ["Value added account", "Value added component"]:
            if c in df.columns:
                return c

    # Farm income in kind
    if table_id == "32-10-0055-01":
        for c in [
            "Type of farm items",
            "Farm income in kind items",
            "Farm income in kind, by item",
            "Farm income in kind",
        ]:
            if c in df.columns:
                return c

    if table_id == "32-10-0213-01":
        for c in [
            "Type of farm family",
            "Farm family type",
            "Type of family",
            "Family type",
            "Income concept",
        ]:
            if c in df.columns:
                return c
        for c in [
            "Income source",
            "Income sources",
            "Source of income",
        ]:
            if c in df.columns:
                return c

    if table_id == "32-10-0214-01":
        for c in ["Income quartile", "Income quartile group", "Quartile"]:
            if c in df.columns:
                return c

    if table_id == "32-10-0054-01":
        for c in [
            "Commodity",
            "Products",
            "Food category",
        ]:
            if c in df.columns:
                return c

    if table_id == "32-10-0101-01":
        for c in [
            "Farm financial item",
            "Balance sheet item",
            "Assets and liabilities",
        ]:
            if c in df.columns:
                return c

    if table_id in {"32-10-0102-01", "32-10-0103-01"}:
        for c in [
            "Farm financial item",
            "Balance sheet item",
            "Assets and liabilities",
        ]:
            if c in df.columns:
                return c

    if table_id == "32-10-0104-01":
        for c in [
            "Capital item",
            "Capital purchases and sales item",
            "Farm financial item",
        ]:
            if c in df.columns:
                return c

    if table_id in {
        "32-10-0126-01",
        "32-10-0200-01",
        "32-10-0212-01",
        "32-10-0364-01",
        "32-10-0365-01",
        "32-10-0456-01",
    }:
        col = find_column_fuzzy(
            df,
            [
                "Fruit",
                "Vegetable",
                "Product",
                "Crop",
                "Horticultural product",
                "Greenhouse product",
                "Livestock",
                "Animal",
                "Component",
                "Supply and disposition",
            ],
        )
        if col:
            return col

    # ---------- Costs & Inflation tables ----------

    # Farm input price index (FIPI)
    if table_id == "18-10-0258-01":
        for c in ["Price index", "Farm input category", "Inputs"]:
            if c in df.columns:
                return c

    # Machinery & equipment price index (MEPI)
    if table_id == "18-10-0270-01" and "Industry of purchase" in df.columns:
        return "Industry of purchase"

    if table_id == "32-10-0098-01":
        for c in ["Farm product group", "Farm product groups", "Commodity group"]:
            if c in df.columns:
                return c

    if table_id == "32-10-0077-01" and "Farm products" in df.columns:
        return "Farm products"

    # Food CPI and related CPI tables
    if table_id.startswith("18-10-0004") or table_id in {"18-10-0001-01", "18-10-0002-01"}:
        if "Products and product groups" in df.columns:
            return "Products and product groups"

    # For-hire motor carrier freight SPI
    if table_id == "18-10-0281-01" and "North American Industry Classification System (NAICS)" in df.columns:
        return "North American Industry Classification System (NAICS)"

    # Freight Rail Services Price Index
    if table_id == "18-10-0212-01" and "Commodity group" in df.columns:
        return "Commodity group"

    # ---------- Census 2021 / farm structure ----------

    if table_id == "32-10-0237-01" and "Farm capital" in df.columns:
        return "Farm capital"

    if table_id == "32-10-0238-01" and "Farm machinery and equipment" in df.columns:
        return "Farm machinery and equipment"

    if table_id == "32-10-0239-01" and "Total farm revenues distribution" in df.columns:
        return "Total farm revenues distribution"

    if table_id == "32-10-0240-01":
        for c in ["Total operating revenues, excluding forest products", "Operating revenues"]:
            if c in df.columns:
                return c

    if table_id == "32-10-0241-01":
        for c in ["Total farm operating expenses", "Operating expenses"]:
            if c in df.columns:
                return c

    if table_id == "32-10-0242-01" and "Direct sales" in df.columns:
        return "Direct sales"

    if table_id == "32-10-0243-01" and "Paid agricultural workers" in df.columns:
        return "Paid agricultural workers"

    if table_id == "32-10-0235-01" and "Operating arrangement" in df.columns:
        return "Operating arrangement"

    if table_id == "32-10-0157-01":
        for c in ["Farms classified by gross farm receipts", "Revenue class"]:
            if c in df.columns:
                return c

    if table_id == "32-10-0163-01" and "Selected machinery" in df.columns:
        return "Selected machinery"

    if table_id == "32-10-0166-01" and "North American Industry Classification System (NAICS)" in df.columns:
        return "North American Industry Classification System (NAICS)"

    # ---------- Demographics & labour ----------

    if table_id == "32-10-0036-01" and "Fertilizer product type" in df.columns:
        return "Fertilizer product type"

    if table_id == "32-10-0156-01" and "Total farm area distribution" in df.columns:
        return "Total farm area distribution"

    if table_id == "32-10-0215-01" and "Industry" in df.columns:
        return "Industry"

    if table_id == "32-10-0221-01" and "Country of citizenship" in df.columns:
        return "Country of citizenship"

    # Farm input price index – percentage change
    if table_id == "18-10-0258-02":
        for c in ["Price index", "Farm input category", "Inputs"]:
            if c in df.columns:
                return c

    # On-farm storage capacity
    if table_id == "32-10-0003-01" and "On-farm storage capacity" in df.columns:
        return "On-farm storage capacity"

    # ---------- Generic fallback ----------

    candidates = [
        "Type of cash receipts",
        "Farm items",
        "Expenses and rebates",
        "Commodities",
        "Balance sheet item",
        "Component",
        "Program",
        "Program type",
        "Farm type",
        "Revenues and expenses",
        "Estimates",
        "Price index",
        "Products and product groups",
        "Industry of purchase",
        "Value added account",
        "Farm income in kind items",
        "Mode of transport",
        "Mode of transportation",
        "North American Product Classification System (NAPCS)",
        "North American Industry Classification System (NAICS)",
        "Commodity group",
        "Financial statistics",
        "Activity indicators",
        "Performance indicators",
    ]
    for c in candidates:
        if c in df.columns:
            return c

    return None

def _get_param(params_obj, key: str, default=None):
    """
    Safely read a single query parameter.
    """
    if not params_obj:
        return default

    # Try new-style access first
    try:
        value = params_obj[key]
    except Exception:
        value = params_obj.get(key, None)

    if value is None:
        return default

    # New API: value is already a string
    if isinstance(value, str):
        return value

    # Old API: list/tuple of strings
    if isinstance(value, (list, tuple)):
        if not value:
            return default
        return value[0]

    # Fallback
    return str(value)


def _get_int_param(params_obj, key: str, default=None):
    """
    Read an integer query parameter, falling back to default on any error.
    """
    raw = _get_param(params_obj, key, None)
    if raw is None:
        return default
    try:
        return int(float(raw))
    except Exception:
        return default
    
def _get_bool_param(params_obj, key: str, default=False):
    """
    Read a boolean query parameter represented as 1/0 or true/false strings.
    """
    raw = _get_param(params_obj, key, None)
    if raw is None:
        return default
    if isinstance(raw, str):
        return raw.lower() in {"1", "true", "t", "yes"}
    try:
        return bool(int(raw))
    except Exception:
        return default


def get_default_geos(options: list[str]) -> list[str]:
    """Return preferred default geographies when no user overrides are present."""

    if "Canada" in options and "Ontario" in options:
        return ["Canada", "Ontario"]
    if "Ontario" in options:
        return ["Ontario"]
    return []


def get_default_series(dataset_id: str, series_options: list[str]) -> list[str]:
    """Return the preferred default series for a dataset, or the first option."""

    label = DEFAULT_SERIES_LABELS.get(dataset_id)
    if label and label in series_options:
        return [label]
    return series_options[:1] if series_options else []

def multiselect_with_pins(
    label: str,
    options: list[str],
    key: str,
    pinned_options: list[str] | None = None,
    url_values: list[str] | None = None,
    default_values: list[str] | None = None,
    help: str | None = None,
) -> list[str]:
    """
    Wrapper around st.multiselect that:
    - Moves `pinned` options (if present) to the top.
    - Adds "All" and "Clear" buttons next to the multiselect.
    Returns the selected list of options.
    """

    pinned_present = [o for o in (pinned_options or []) if o in options]
    other_options = [o for o in options if o not in pinned_present]
    ordered_options = pinned_present + other_options

    state_key = key

    base_selection: list[str]
    incoming_url_values = url_values or []
    incoming_default_values = default_values or []

    if incoming_url_values:
        base_selection = [v for v in incoming_url_values if v in ordered_options]
    elif state_key in st.session_state:
        existing = st.session_state.get(state_key)
        if existing is None:
            base_selection = []
        elif isinstance(existing, (list, tuple)):
            base_selection = [v for v in existing if v in ordered_options]
        else:
            base_selection = [existing] if existing in ordered_options else []
    else:
        base_selection = [v for v in incoming_default_values if v in ordered_options]

    cols = st.columns([4, 1, 1])
    with cols[1]:
        all_clicked = st.button("All", key=f"{state_key}_all")
    with cols[2]:
        clear_clicked = st.button("Clear", key=f"{state_key}_clear")

    if all_clicked:
        base_selection = list(ordered_options)
    elif clear_clicked:
        base_selection = []

    if (state_key not in st.session_state) or all_clicked or clear_clicked:
        st.session_state[state_key] = base_selection

    with cols[0]:
        selected = st.multiselect(
            label,
            ordered_options,
            key=state_key,
            help=help,
        )

    return selected

def apply_index_to_base_if_needed(
    df: pd.DataFrame,
    value_col: str,
    year_col: str,
    base_year: int,
    group_cols: list[str],
    analytics_options: AnalyticsOptions,
) -> tuple[pd.DataFrame, str, int | None, bool]:
    """
    If analytics_options.index_to_base is True and chart mode is 'level', compute an index so
    that each group's first non-zero value at or after base_year equals 100.

    Returns the potentially transformed dataframe, the column name to use for charting, the
    base year applied when common across series (or None), and a flag indicating whether
    indexing was applied.
    """

    if not (analytics_options.index_to_base and analytics_options.chart_mode == "level"):
        return df, value_col, None, False

    if df.empty or df[year_col].nunique() < 2:
        return df, value_col, None, False

    valid = df.copy()
    valid = valid[
        (valid[year_col] >= base_year) & valid[value_col].notna() & (valid[value_col] != 0)
    ]

    if valid.empty:
        return df, value_col, None, False

    valid_sorted = valid.sort_values(year_col)
    base_rows = (
        valid_sorted.groupby(group_cols, as_index=False).first()[group_cols + [year_col, value_col]]
    )
    base_rows = base_rows.rename(columns={year_col: "BASE_YEAR", value_col: "BASE_VALUE"})

    df_out = df.merge(base_rows, on=group_cols, how="left")
    df_out["INDEX_VALUE"] = df_out[value_col] / df_out["BASE_VALUE"] * 100.0

    if df_out["INDEX_VALUE"].isna().all():
        return df, value_col, None, False

    base_years = base_rows["BASE_YEAR"].dropna().unique()
    if len(base_years) == 1:
        base_year_for_caption: int | None = int(base_years[0])
    else:
        base_year_for_caption = None

    return df_out, "INDEX_VALUE", base_year_for_caption, True


OMAFRA_FCR_XLSX_URL = (
    "https://data.ontario.ca/dataset/ontario-farm-cash-receipts-by-county-and-crop/resource/"
    "c4cffe14-d1a0-40e8-b2b6-393a7631ec24/download"
)

OMAFRA_ATTRIBUTION_XLSX_URL = (
    "https://data.ontario.ca/dataset/ontario-agri-food-value-chain-by-county/resource/"
    "c0cc0162-7b39-4e1b-bab9-5b84ea6f739f/download"
)


@st.cache_data(max_entries=3, show_spinner=False, ttl=1800)
def load_omafra_fcr_by_county() -> pd.DataFrame:
    """Load OMAFRA farm cash receipts by county and commodity."""

    try:
        resp = requests.get(OMAFRA_FCR_XLSX_URL, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Failed to download OMAFRA farm cash receipts workbook: {e}")

    xls = pd.ExcelFile(io.BytesIO(resp.content))
    frames: list[pd.DataFrame] = []

    for sheet_name in xls.sheet_names:
        if not re.search(r"FCR(\d{4})", sheet_name):
            continue
        year_match = re.search(r"FCR(\d{4})", sheet_name)
        if not year_match:
            continue
        year_val = int(year_match.group(1))

        sheet_df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        if sheet_df.empty:
            continue

        header_candidates = sheet_df.index[
            sheet_df.iloc[:, 0].astype(str).str.strip().str.lower() == "county"
        ]
        if header_candidates.empty:
            continue
        header_row = header_candidates[0]
        headers = sheet_df.iloc[header_row].tolist()
        data = sheet_df.iloc[header_row + 1 :].copy()
        headers = headers[: data.shape[1]]
        data = data.iloc[:, : len(headers)]
        data.columns = headers

        county_col = headers[0]
        long_df = data.melt(id_vars=[county_col], var_name="COMMODITY", value_name="VALUE")
        long_df[county_col] = long_df[county_col].astype(str).str.strip()
        long_df = long_df.assign(YEAR=year_val)

        long_df["VALUE"] = pd.to_numeric(long_df["VALUE"], errors="coerce")

        geo_series = long_df[county_col].astype(str).str.strip()
        is_footnote = (
            geo_series.str.startswith("*")
            | geo_series.str.match(r"\d{4}-\d{2}-\d{2}")
            | geo_series.str.match(r"[A-Za-z]{3,9} \d{1,2} \d{4}")
            | geo_series.str.contains("Date of update", case=False, na=False)
            | geo_series.str.startswith("Reference:")
        )
        long_df = long_df[~is_footnote].copy()
        long_df = long_df.rename(columns={county_col: "GEO"})

        frames.append(long_df[["GEO", "YEAR", "COMMODITY", "VALUE"]])

    if not frames:
        return pd.DataFrame(columns=["GEO", "YEAR", "COMMODITY", "VALUE"])

    return pd.concat(frames, ignore_index=True)


@st.cache_data(max_entries=3, show_spinner=False, ttl=1800)
def load_omafra_attribution_county() -> pd.DataFrame:
    """Load OMAFRA agri-food GDP and employment by county."""

    try:
        resp = requests.get(OMAFRA_ATTRIBUTION_XLSX_URL, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(
            f"Failed to download OMAFRA agri-food value chain workbook: {e}"
        )

    xls = pd.ExcelFile(io.BytesIO(resp.content))
    df_raw = pd.read_excel(xls, sheet_name="county_En", header=None)

    gdp_title_mask = df_raw[0].astype(str).str.contains("Gross Domestic Product", case=False, na=False)
    gdp_title_indices = df_raw[gdp_title_mask & pd.to_numeric(df_raw[1], errors="coerce").notna()].index
    if gdp_title_indices.empty:
        return pd.DataFrame(columns=["GEO", "YEAR", "MEASURE", "VALUE"])
    gdp_title_row = gdp_title_indices[0]

    employment_title_indices = df_raw[df_raw[0].astype(str).str.startswith("Employment", na=False)].index
    if employment_title_indices.empty:
        return pd.DataFrame(columns=["GEO", "YEAR", "MEASURE", "VALUE"])
    employment_title_row = employment_title_indices[0]

    gdp_years = clean_year_labels(df_raw.iloc[gdp_title_row, 1:].tolist())
    gdp_cols = ["County"] + gdp_years
    gdp_data = df_raw.iloc[gdp_title_row + 1 : employment_title_row, : len(gdp_cols)].copy()
    gdp_data.columns = gdp_cols
    gdp_long = gdp_data.melt(id_vars=["County"], var_name="YEAR", value_name="VALUE")
    gdp_long = gdp_long.assign(MEASURE="GDP_chained2017_millions")

    employment_years = clean_year_labels(df_raw.iloc[employment_title_row, 1:].tolist())
    employment_cols = ["County"] + employment_years
    last_row = df_raw.dropna(how="all").index.max()
    employment_data = df_raw.iloc[employment_title_row + 1 : last_row + 1, : len(employment_cols)].copy()
    employment_data.columns = employment_cols
    employment_long = employment_data.melt(
        id_vars=["County"], var_name="YEAR", value_name="VALUE"
    )
    employment_long = employment_long.assign(MEASURE="Employment_thousands")

    combined = pd.concat([gdp_long, employment_long], ignore_index=True)
    combined["County"] = combined["County"].astype(str).str.strip()

    combined = combined[~combined["County"].str.startswith("Source:", na=False)]
    combined = combined[~combined["County"].str.startswith("Note:", na=False)]
    combined = combined[~combined["County"].str.match(r"\d{4}-\d{2}-\d{2}", na=False)]

    combined = combined.rename(columns={"County": "GEO"})
    combined["YEAR"] = pd.to_numeric(combined["YEAR"], errors="coerce")
    combined["VALUE"] = pd.to_numeric(combined["VALUE"], errors="coerce")

    combined = combined.dropna(subset=["YEAR", "GEO", "VALUE"])
    combined["YEAR"] = combined["YEAR"].astype(int)

    return combined[["GEO", "YEAR", "MEASURE", "VALUE"]]


def inject_theme_css():
    """
    Injects global CSS to ensure that hardcoded light-mode colors (e.g. #1a1a2e, #555) 
    are overridden when Streamlit's dark mode is active. This uses @media queries and 
    Streamlit's internal theme selectors.
    """
    import streamlit as st
    st.markdown("""
    <style>
        /* CSS Variables Global Native Bindings */
        /* General Text Colors */
        div[data-testid="stMetricValue"], 
        div[data-testid="stMetricLabel"],
        .kpi-label, .section-title, .preset-desc, 
        .method-note, .source-note, .source-badge {
            color: var(--text-color) !important;
        }
        
        .kpi-value {
            color: var(--text-color) !important;
        }

        /* Explicit inline text overrides for #555, #666, #888, #1a1a2e */
        span[style*="color: #555"], span[style*="color:#555"],
        span[style*="color: #666"], span[style*="color:#666"],
        span[style*="color: #888"], span[style*="color:#888"],
        span[style*="color: #1a1a2e"], span[style*="color:#1a1a2e"],
        div[style*="color: #555"], div[style*="color:#555"],
        div[style*="color: #666"], div[style*="color:#666"],
        div[style*="color: #888"], div[style*="color:#888"],
        div[style*="color: #1a1a2e"], div[style*="color:#1a1a2e"],
        td[style*="color: #555"], td[style*="color:#555"],
        p[style*="color: #555"], p[style*="color:#555"],
        p[style*="color: #888"], p[style*="color:#888"] {
            color: var(--text-color) !important;
        }

        /* Specific Information Badges/Text */
        span[style*="color: #006064"], span[style*="color:#006064"] {
            color: var(--primary-color) !important;
        }

        /* Background Overrides */
        .kpi-section, .narrative-box, .section-header, 
        .metric-card, .kpi-card, .housing-card,
        .context-banner, .context-badge, .jrg-badge, .ccr-badge {
            background: var(--secondary-background-color) !important;
            border-color: rgba(128, 128, 128, 0.2) !important;
            color: var(--text-color) !important;
        }

        /* Gap / Up / Down specific colors relying on Streamlit's red/green mapping or distinct RGBA combos */
        .gap-positive, .kpi-up, .export-up, .fruit-up {
            color: #16a34a !important; /* Tailwind green-600, visible on dark/light */
            background: rgba(22, 163, 74, 0.1) !important;
        }
        
        .gap-negative, .kpi-down, .export-down, .fruit-down {
            color: #dc2626 !important; /* Tailwind red-600 */
            background: rgba(220, 38, 38, 0.1) !important;
        }
        
        .kpi-flat {
            color: var(--text-color) !important;
            background: var(--secondary-background-color) !important;
        }
    </style>
    """, unsafe_allow_html=True)
    
def global_footer():
    """Renders a standard footer at the bottom of the page."""
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.divider()
    st.caption(
        "For inquiries on how to use this dashboard please contact "
        "OFA's Senior Economist Ben LeFort at [ben.lefort@ofa.on.ca](mailto:ben.lefort@ofa.on.ca)"
    )


def inject_standalone_mode():
    """
    Injects a client-side JavaScript component to hide Streamlit's sidebar navigation 
    and top header when ?standalone=true is passed in the URL.
    Also injects theme CSS to fix dark mode.
    """
    inject_theme_css()
    import streamlit.components.v1 as components
    components.html(
        """
        <script>
            const urlParams = new URLSearchParams(window.parent.location.search);
            if (urlParams.get('standalone') === 'true') {
                const style = window.parent.document.createElement('style');
                style.innerHTML = `
                    /* Broadly hide the page navigation list */
                    [data-testid="stSidebarNav"] { display: none !important; }
                    div[data-testid="stSidebarNav"] { display: none !important; }
                    /* Hide header */
                    header[data-testid="stHeader"] { display: none !important; }
                    .block-container { padding-top: 2rem !important; }
                `;
                window.parent.document.head.appendChild(style);
            }
        </script>
        """,
        height=0,
        width=0,
    )


# ════════════════════════════════════════════════════════
#  Data Freshness Indicator
# ════════════════════════════════════════════════════════

_PROJ_ROOT = Path(__file__).resolve().parents[1]  # app/utils.py → app/ → project root

def _load_manifest() -> dict:
    """Load data/manifest.json (cached for the session)."""
    import streamlit as st

    @st.cache_data(max_entries=5, ttl=300)  # refresh every 5 minutes
    def _read():
        fp = _PROJ_ROOT / "data" / "manifest.json"
        if fp.exists():
            return json.loads(fp.read_text())
        return {"tables": {}}

    return _read()


def _load_pipeline_status() -> dict:
    """Load data/pipeline_status.json (cached for the session)."""
    import streamlit as st

    @st.cache_data(max_entries=5, ttl=300)
    def _read():
        fp = _PROJ_ROOT / "data" / "pipeline_status.json"
        if fp.exists():
            return json.loads(fp.read_text())
        return {}

    return _read()


def get_table_last_updated(table_id: str) -> str | None:
    """Return the last_updated_local date string for a specific table, or None."""
    manifest = _load_manifest()
    entry = manifest.get("tables", {}).get(table_id, {})
    return entry.get("last_updated_local")


def get_pipeline_last_run() -> str | None:
    """Return the last pipeline run timestamp, or None."""
    status = _load_pipeline_status()
    return status.get("last_run_local")


def show_data_freshness(table_ids: list[str] | None = None,
                        source_labels: dict[str, str] | None = None,
                        show_pipeline_run: bool = True):
    """Render a compact data freshness indicator in the Streamlit sidebar.

    Args:
        table_ids: List of StatCan table IDs used by this page.
                   If None, shows only the pipeline-level last run.
        source_labels: Optional dict mapping table_id → friendly label.
                       e.g. {"32-10-0045-01": "Farm Cash Receipts"}
        show_pipeline_run: Whether to show the overall pipeline last run date.

    Usage in a page:
        from app.utils import show_data_freshness
        show_data_freshness(
            table_ids=["32-10-0045-01", "32-10-0046-01"],
            source_labels={"32-10-0045-01": "Cash Receipts", "32-10-0046-01": "Net Income"},
        )
    """
    import streamlit as st

    manifest = _load_manifest()
    status = _load_pipeline_status()

    with st.sidebar:
        st.divider()
        st.markdown(
            "<p style='font-size:0.75rem; color:#888; margin-bottom:0.25rem;'>"
            "📅 <b>Data Freshness</b></p>",
            unsafe_allow_html=True,
        )

        # Overall pipeline run
        if show_pipeline_run:
            last_run = status.get("last_run_local", "")
            if last_run:
                # Format: "2026-01-23T12:38:54" → "Jan 23, 2026"
                try:
                    dt = datetime.datetime.fromisoformat(last_run)
                    friendly = dt.strftime("%b %d, %Y")
                except (ValueError, TypeError):
                    friendly = last_run[:10]
                st.caption(f"Last pipeline run: **{friendly}**")

                # Show failed count if any
                failed = status.get("failed_tables", [])
                if failed:
                    st.caption(f"⚠️ {len(failed)} table(s) failed last run")
            else:
                st.caption("Pipeline has not run yet.")

        # Per-table freshness
        if table_ids:
            labels = source_labels or {}
            lines = []
            for tid in table_ids:
                entry = manifest.get("tables", {}).get(tid, {})
                date_str = entry.get("last_updated_local", "")
                label = labels.get(tid, tid)
                if date_str:
                    try:
                        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                        age_days = (datetime.datetime.now() - dt).days
                        friendly = dt.strftime("%b %d, %Y")
                        if age_days > 90:
                            lines.append(f"⚠️ {label}: {friendly} ({age_days}d ago)")
                        else:
                            lines.append(f"✅ {label}: {friendly}")
                    except (ValueError, TypeError):
                        lines.append(f"✅ {label}: {date_str}")
                else:
                    lines.append(f"🔄 {label}: *on-demand*")

            for line in lines:
                st.caption(line)

