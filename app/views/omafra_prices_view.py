"""View extracted from streamlit_app.py — Phase 3 Architecture Refactoring."""
import io
from typing import Mapping
import math
import re

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from app.analytics import AnalyticsOptions, compute_linear_trend, compute_moving_average, compute_yoy_change, flag_outliers
from app.cpi_utils import apply_cpi_adjustment, detect_dollar_series, load_cpi_deflators
from dataset_descriptions import DATASET_DESCRIPTIONS
from app.unit_utils import get_unit_label, supports_inflation_adjustment
from app.utils import (

    apply_index_to_base_if_needed,
    DatasetLoadError,
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
)

from scripts import config_loader
TABLE_CONFIG = config_loader.load_tables(active_only=True)



def render_omafra_commodity_prices_view(
    table_cfg: Mapping | None,
    analytics_options: AnalyticsOptions,
    params: Mapping[str, str] | None = None,
) -> dict:
    """Render the OMAFRA commodity prices view for the selected dataset."""

    if not isinstance(table_cfg, Mapping):
        st.info("No OMAFRA commodity price data is available yet.")
        return {}

    try:
        df = safe_load_dataset(dict(table_cfg))
    except Exception:
        st.info("No OMAFRA commodity price data is available yet.")
        return {}

    if df is None or df.empty:
        st.info("No OMAFRA commodity price data is available yet.")
        return {}

    params = params or {}
    dataset_label = table_cfg.get("name") if isinstance(table_cfg, Mapping) else None
    dataset_label = dataset_label or "Commodity prices (OMAFRA)"

    plot_df = ensure_year_column(df.copy())
    if "YEAR" not in plot_df.columns and "DATE" in plot_df.columns:
        plot_df["YEAR"] = pd.to_datetime(plot_df["DATE"], errors="coerce").dt.year
    if "YEAR" not in plot_df.columns or "VALUE" not in plot_df.columns:
        st.info("No OMAFRA commodity price data is available yet.")
        return {}

    plot_df = plot_df.dropna(subset=["YEAR"]).copy()
    plot_df["YEAR"] = pd.to_numeric(plot_df["YEAR"], errors="coerce")
    plot_df = plot_df.dropna(subset=["YEAR"]).copy()
    plot_df["YEAR"] = plot_df["YEAR"].astype(int)
    plot_df["VALUE"] = pd.to_numeric(plot_df["VALUE"], errors="coerce")
    plot_df = plot_df.dropna(subset=["VALUE"]).copy()

    if plot_df.empty:
        st.info("No OMAFRA commodity price data is available yet.")
        return {}

    geo_col = "GEO" if "GEO" in plot_df.columns else None
    series_col = "SERIES" if "SERIES" in plot_df.columns else None

    available_geos_for_cpi: list[str] = []
    if geo_col and geo_col in df.columns:
        available_geos_for_cpi = df[geo_col].dropna().astype(str).unique().tolist()

    selected_geos: list[str] = []
    if geo_col:
        geos_all = sorted(plot_df[geo_col].dropna().unique().tolist())
        geos_param = _get_param(params, "geos", None)
        url_geos = [g for g in (geos_param.split(",") if geos_param else []) if g in geos_all]
        default_geos = geos_all[:3] if len(geos_all) > 3 else geos_all
        selected_geos = multiselect_with_pins(
            "Geography",
            geos_all,
            key=f"{table_cfg.get('id', 'omafra')}_geos" if isinstance(table_cfg, Mapping) else "omafra_geos",
            pinned_options=[g for g in geos_all if g in ["Canada", "Ontario"]],
            url_values=url_geos,
            default_values=default_geos,
        )
        if not selected_geos:
            st.info("Select at least one geography to display the data.")
            return {}
        plot_df = plot_df[plot_df[geo_col].isin(selected_geos)].copy()

    selected_series_list: list[str] = []
    if series_col:
        series_all = sorted(plot_df[series_col].dropna().unique().tolist())
        series_param = _get_param(params, "series", None)
        url_series = [s for s in (series_param.split(",") if series_param else []) if s in series_all]
        default_series = series_all
        selected_series_list = st.multiselect(
            "Series",
            series_all,
            default=url_series or default_series,
            help="Select one or more commodity series to display.",
        )
        if selected_series_list:
            plot_df = plot_df[plot_df[series_col].isin(selected_series_list)].copy()
        else:
            selected_series_list = default_series

    yrs = plot_df["YEAR"].dropna().astype(int)
    if yrs.empty:
        st.info("No OMAFRA commodity price data is available yet.")
        return {}

    yr_min, yr_max = int(yrs.min()), int(yrs.max())
    param_start = _get_int_param(params, "start_year")
    param_end = _get_int_param(params, "end_year")

    start_default = param_start if param_start is not None else yr_min
    end_default = param_end if param_end is not None else yr_max
    start_default = max(yr_min, min(yr_max, start_default))
    end_default = max(yr_min, min(yr_max, end_default))
    if start_default > end_default:
        start_default, end_default = end_default, start_default

    if yr_min == yr_max:
        yr_from = yr_to = yr_min
    else:
        yr_from, yr_to = st.slider(
            "Year range",
            min_value=yr_min,
            max_value=yr_max,
            value=(start_default, end_default),
        )

    plot_df = plot_df[plot_df["YEAR"].between(yr_from, yr_to)].copy()
    if plot_df.empty:
        st.info("No OMAFRA commodity price data is available yet.")
        return {}

    df_metrics = plot_df.copy()
    if "YEAR" not in df_metrics.columns and "DATE" in df_metrics.columns:
        df_metrics["YEAR"] = pd.to_datetime(df_metrics["DATE"], errors="coerce").dt.year

    group_cols = ["YEAR"]
    if "GEO" in df_metrics.columns:
        group_cols.append("GEO")
    if "SERIES" in df_metrics.columns:
        group_cols.append("SERIES")

    annual_df = (
        df_metrics.groupby(group_cols, as_index=False)["VALUE"]
        .mean()
        .sort_values(["YEAR"])
    )

    plot_df = annual_df.copy()

    label_col = "OMAFRA_LABEL"
    if geo_col and series_col:
        plot_df[label_col] = plot_df[geo_col].astype(str) + " – " + plot_df[series_col].astype(str)
    elif series_col:
        plot_df[label_col] = plot_df[series_col].astype(str)
    elif geo_col:
        plot_df[label_col] = plot_df[geo_col].astype(str)
    else:
        plot_df[label_col] = dataset_label

    unit_lbl = None
    if "UNIT" in plot_df.columns:
        unit_vals = plot_df["UNIT"].dropna().unique()
        if len(unit_vals):
            unit_lbl = str(unit_vals[0])
    unit_lbl = unit_lbl or get_unit_label(plot_df)

    value_col_for_chart = "VALUE"
    value_title = unit_lbl or "Value"
    inflation_note: str | None = None
    time_col = "YEAR"
    cpi_geo_preference = "Canada"
    if any("ontario" in g.lower() for g in available_geos_for_cpi):
        cpi_geo_preference = "Ontario"
    chart_df = plot_df.copy()
    (
        chart_df,
        value_col_for_chart,
        inflation_applied,
        inflation_checked,
        base_year,
        inflation_note,
        is_dollar_series,
    ) = apply_cpi_adjustment(
        chart_df=chart_df,
        params_obj=params,
        dataset_label=dataset_label,
        unit_lbl=unit_lbl,
        checkbox_key=f"{table_cfg.get('id', 'omafra_prices')}_inflation",
        value_col=value_col_for_chart,
        time_col=time_col,
        table_cfg=table_cfg if isinstance(table_cfg, Mapping) else None,
        table_id=table_cfg.get("id") if isinstance(table_cfg, Mapping) else None,
        cpi_geo=cpi_geo_preference,
        inflation_label="Inflation-adjust (real $)",
        inflation_help=(
            "Uses CPI all-items, annual average (StatCan table 18-10-0005-01). "
            "Ontario CPI is used when available; falls back to Canada. Adjusts by calendar year."
        ),
        warn_on_cpi_failure=True,
        table_config=TABLE_CONFIG,
        _load_table_fn=load_table,
    )

    index_base_year: int | None = None
    indexed = False

    chart_df, value_col_for_chart, index_base_year, indexed = apply_index_to_base_if_needed(
        chart_df,
        value_col=value_col_for_chart,
        year_col="YEAR",
        base_year=yr_from,
        group_cols=[label_col],
        analytics_options=analytics_options,
    )

    table_id = table_cfg.get("id") if isinstance(table_cfg, Mapping) else None

    analytics_level = None
    analytics_yoy = None

    try:
        analytics_level = compute_time_series_analytics(
            chart_df,
            value_col=value_col_for_chart,
            time_col="YEAR",
            table_cfg=table_cfg if isinstance(table_cfg, Mapping) else None,
            table_id=table_id,
        )
    except Exception:
        analytics_level = None

    try:
        analytics_yoy = compute_yoy_analytics(
            chart_df, value_col=value_col_for_chart, time_col="YEAR"
        )
    except Exception:
        analytics_yoy = None

    st.caption(dataset_label)
    render_dataset_notes(table_cfg if isinstance(table_cfg, Mapping) else None)
    render_source_caption(table_cfg if isinstance(table_cfg, Mapping) else None)
    _desc = DATASET_DESCRIPTIONS.get(table_id)
    if _desc:
        st.info(f"\U0001f4ca **What this data shows:** {_desc}")

    dataset_title_for_summary = dataset_label
    if selected_series_list:
        dataset_title_for_summary = f"{dataset_label} — {', '.join(selected_series_list)}"

    narrative = build_narrative_summary(
        dataset_title_for_summary,
        analytics_level,
        analytics_yoy,
        analytics_options,
        last_year=yr_to,
        unit_label=unit_lbl,
        table_cfg=table_cfg if isinstance(table_cfg, Mapping) else None,
        table_id=table_id,
        df=chart_df,
        label_col=label_col,
        value_col=value_col_for_chart,
    )
    if narrative:
        st.subheader("Summary")
        st.markdown(narrative)

    present_labels = sorted(chart_df[label_col].dropna().unique().tolist())
    y_title = f"{dataset_label}{(' (' + unit_lbl + ')') if unit_lbl else ''}"
    if indexed:
        if index_base_year is not None:
            y_title = f"{dataset_label} — Index (base year = {index_base_year}, 100 = base)"
        else:
            y_title = f"{dataset_label} — Index (first non-zero year in selected range = 100)"
    elif inflation_applied and base_year is not None:
        real_label = f"Real ({base_year} $)"
        y_title = f"{dataset_label} — {real_label}"
        value_title = real_label

    if yr_min == yr_max:
        chart = (
            alt.Chart(chart_df)
            .mark_bar()
            .encode(
                x=alt.X(f"{label_col}:N", title="Geography / series"),
                y=alt.Y(f"{value_col_for_chart}:Q", title=y_title, axis=alt.Axis(format="~s")),
                tooltip=[
                    alt.Tooltip(f"{label_col}:N", title="Geography / series"),
                    alt.Tooltip(f"{value_col_for_chart}:Q", title=value_title, format=","),
                ],
                color=alt.Color(
                    f"{label_col}:N",
                    title="Geography / series",
                    scale=altair_colour_scale(present_labels),
                ),
            )
            .properties(height=420)
        )
    else:
        long_df = chart_df[["YEAR", label_col, value_col_for_chart]].copy()
        long_df["YEAR"] = long_df["YEAR"].astype(int)
        chart = make_line_chart(
            long_df,
            y_title,
            present_labels,
            value_col=value_col_for_chart,
            color_col=label_col,
            color_title="Geography / series",
            tooltip_fields=[(label_col, "Geography / series")],
            analytics_options=analytics_options,
            value_title=value_title,
        )

    st.altair_chart(chart, use_container_width=True)

    if inflation_note:
        st.caption(inflation_note)
    if unit_lbl:
        st.caption(f"ℹ️ Values shown in: {unit_lbl}")

    selected_series_label = ",".join(selected_series_list) if selected_series_list else None
    return {
        "selected_dataset_id": table_cfg.get("id"),
        "selected_geos_for_params": selected_geos,
        "selected_series_for_params": selected_series_label,
        "year_range_for_params": (yr_from, yr_to),
        "inflation_adjusted_for_params": inflation_checked,
    }


def render_omafra_prices_view(params, analytics_options):
    """Render the Commodity prices (OMAFRA) view. Returns footer-state dict."""
    st.subheader("Commodity prices (OMAFRA)")

    omafra_price_tables = [
        t
        for t in TABLE_CONFIG
        if t.get("theme") == "Commodity prices (OMAFRA)" and t.get("active", True)
    ]
    omafra_price_tables = sorted(omafra_price_tables, key=lambda t: t.get("name", ""))

    if not omafra_price_tables:
        st.info("No OMAFRA commodity price datasets are active.")
    else:
        omafra_dataset_options = {t["name"]: t["id"] for t in omafra_price_tables}

        dataset_labels = list(omafra_dataset_options.keys())
        default_label = dataset_labels[0]
        dataset_from_url = _get_param(params, "dataset", omafra_dataset_options[default_label])
        initial_label = next(
            (
                label
                for label, table_id in omafra_dataset_options.items()
                if str(table_id) == str(dataset_from_url)
            ),
            default_label,
        )

        selected_dataset_label = st.sidebar.selectbox(
            "Dataset",
            dataset_labels,
            index=dataset_labels.index(initial_label),
        )
        selected_dataset_id = omafra_dataset_options[selected_dataset_label]
        table_cfg = next(
            t for t in omafra_price_tables if str(t.get("id")) == str(selected_dataset_id)
        )

        with st.spinner("Loading OMAFRA commodity prices…"):
            view_state = render_omafra_commodity_prices_view(
                table_cfg=table_cfg,
                analytics_options=analytics_options,
                params=params,
            )

        if view_state:
            selected_dataset_id = view_state.get("selected_dataset_id")
            selected_series_for_params = view_state.get("selected_series_for_params")
            selected_geos_for_params = view_state.get("selected_geos_for_params", [])
            year_range_for_params = view_state.get("year_range_for_params")
            inflation_adjusted_for_params = view_state.get(
                "inflation_adjusted_for_params", False
            )

# ============================================================
# HOUSEHOLD INCOME & BALANCE SHEET VIEW
# ============================================================

    # Return footer state for URL sharing
    return {
        "selected_dataset_id": locals().get("selected_dataset_id"),
        "selected_series_for_params": locals().get("selected_series_for_params"),
        "selected_geos_for_params": locals().get("selected_geos_for_params", []),
        "year_range_for_params": locals().get("year_range_for_params"),
        "inflation_adjusted_for_params": locals().get("inflation_adjusted_for_params", False),
    }
