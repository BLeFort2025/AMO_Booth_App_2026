"""View extracted from streamlit_app.py — Phase 3 Architecture Refactoring."""
import io
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


def render_farm_labour_view(params, analytics_options):
    """Render the Farm Labour & Households (Ontario) view. Returns footer-state dict."""
    st.subheader("Farm labour & households (Ontario)")

    dataset_options = {
        "Employment in Ontario agriculture": "32-10-0234-01.csv",
        "Labour costs in Ontario agriculture": "32-10-0236-01.csv",
        "Farm households and families in Ontario": "32-10-0422-01.csv",
    }

    dataset_labels = list(dataset_options.keys())
    default_dataset_label = dataset_labels[0]
    dataset_from_url = _get_param(params, "dataset", dataset_options[default_dataset_label].replace(".csv", ""))
    if dataset_from_url.endswith(".csv"):
        dataset_from_url = dataset_from_url.replace(".csv", "")
    initial_dataset_label = next(
        (
            label
            for label, fname in dataset_options.items()
            if fname.replace(".csv", "") == dataset_from_url
        ),
        default_dataset_label,
    )

    dataset_label = st.sidebar.selectbox(
        "Dataset", dataset_labels, index=dataset_labels.index(initial_dataset_label)
    )
    filename = dataset_options[dataset_label]
    table_id = filename.replace(".csv", "")
    table_cfg = get_table_metadata(table_id) or {"id": table_id, "csv": filename}

    with st.spinner("Fetching data from Statistics Canada or local dataset…"):
        df = safe_load_dataset(table_cfg)

    st.caption(dataset_label)
    render_dataset_notes(table_cfg)

    df = ensure_year_column(df)

    if "YEAR" in df.columns:
        df = df.dropna(subset=["YEAR"]).copy()
    else:
        df = df.copy()

    df["YEAR"] = df["YEAR"].astype(int)
    if "VALUE" not in df.columns:
        st.error("Expected column 'VALUE' not found.")
        st.stop()
    df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")

    dim_col = find_series_column(table_id, df)
    selected_series_list: list[str] = []

    if dim_col:
        series_options = sorted(df[dim_col].dropna().unique().tolist())
        dataset_id_for_defaults = table_cfg.get("id", table_id)
        default_series = get_default_series(dataset_id_for_defaults, series_options)
        series_param = _get_param(params, "series", None)
        url_series = [
            s for s in (series_param.split(",") if series_param else []) if s in series_options
        ]
        pinned_series = [s for s in series_options if str(s).lower().startswith("total")]

        with st.sidebar:
            selected_series_list = multiselect_with_pins(
                "Series (multiple allowed)",
                series_options,
                key=f"{table_id}_series",
                pinned_options=pinned_series,
                url_values=url_series,
                default_values=default_series,
                help="Select one or more series.",
            )
        if not selected_series_list:
            st.info("Select at least one series to display the data.")
            st.stop()
        df = df[df[dim_col].isin(selected_series_list)].copy()

    selected_series_label = (
        ", ".join(map(str, selected_series_list)) if selected_series_list else None
    )

    if "GEO" not in df.columns:
        st.error("Expected 'GEO' column not found.")
        st.stop()

    geos = sorted(df["GEO"].dropna().unique().tolist())
    default_geos = get_default_geos(geos)
    if not default_geos and geos:
        default_geos = geos[:1]
    geos_param = _get_param(params, "geos", None)
    url_geos = [g for g in (geos_param.split(",") if geos_param else []) if g in geos]
    pinned_geos = [g for g in geos if g in ["Canada", "Ontario"]]

    with st.sidebar:
        selected_geos = multiselect_with_pins(
            "Geography",
            geos,
            key=f"{table_id}_geos",
            pinned_options=pinned_geos,
            url_values=url_geos,
            default_values=default_geos,
            help="Select one or more geographies.",
        )

    if not selected_geos:
        st.info("Select at least one geography to display the data.")
        st.stop()

    yrs = df[df["GEO"].isin(selected_geos)]["YEAR"].dropna().astype(int)
    if yrs.empty:
        st.info("No data for selected filters.")
        st.stop()

    yr_min, yr_max = int(yrs.min()), int(yrs.max())
    start_default, end_default = yr_min, yr_max

    param_start = _get_int_param(params, "start_year")
    param_end = _get_int_param(params, "end_year")

    if param_start is not None:
        start_default = max(yr_min, min(yr_max, param_start))
    if param_end is not None:
        end_default = max(yr_min, min(yr_max, param_end))

    if start_default > end_default:
        start_default, end_default = end_default, start_default

    if yr_min == yr_max:
        yr_from = yr_to = yr_min
    else:
        yr_from, yr_to = st.sidebar.slider(
            "Year range",
            min_value=yr_min,
            max_value=yr_max,
            value=(start_default, end_default),
            step=1,
        )

    f = df[(df["GEO"].isin(selected_geos)) & (df["YEAR"].between(yr_from, yr_to))].copy()
    if f.empty:
        st.info("No data for selected filters.")
        st.stop()

    label_col = "GEO_SERIES_LABEL"
    plot_df = f.copy()
    if dim_col:
        plot_df[label_col] = plot_df["GEO"].astype(str) + " – " + plot_df[dim_col].astype(str)
    else:
        plot_df[label_col] = plot_df["GEO"].astype(str)

    chart_df = plot_df.copy()
    value_col_for_chart = "VALUE"
    base_year: int | None = None

    unit_lbl = get_unit_label(chart_df)

    series_years_full = pd.to_numeric(chart_df["YEAR"], errors="coerce")
    series_years = series_years_full.dropna().astype(int)
    if series_years.empty:
        base_year = None
    else:
        base_year = int(series_years.max())

    latest_slice = f[f["YEAR"] == yr_to]
    prev_slice = f[f["YEAR"] < yr_to]
    total_latest = latest_slice[value_col_for_chart].sum()

    metric_label = f"{dataset_label} in {yr_to}"

    if not prev_slice.empty:
        prev_year = int(prev_slice["YEAR"].max())
        prev_total = prev_slice[prev_slice["YEAR"] == prev_year][value_col_for_chart].sum()
        change = (total_latest - prev_total) / prev_total * 100 if prev_total else 0.0
        metric_col, delta_col = st.columns([2, 1])
        with metric_col:
            st.metric(metric_label, f"{total_latest:,.0f}")
        with delta_col:
            st.metric("Change vs prior year", f"{change:+.1f}%")
    else:
        st.metric(metric_label, f"{total_latest:,.0f}", "")

    analytics_level = compute_time_series_analytics(
        f,
        value_col=value_col_for_chart,
        time_col="YEAR",
    )
    analytics_yoy = compute_yoy_analytics(
        f,
        value_col=value_col_for_chart,
        time_col="YEAR",
    )

    tiles = []
    if analytics_options.chart_mode == "yoy":
        if analytics_yoy.get("latest_yoy") is not None:
            tiles.append(
                (
                    "Latest annual change",
                    f"{analytics_yoy['latest_yoy']:.1f}%",
                    "vs previous year",
                )
            )
        if analytics_yoy.get("mean_yoy") is not None:
            tiles.append(
                (
                    "Average annual change",
                    f"{analytics_yoy['mean_yoy']:.1f}%",
                    "over selected window",
                )
            )
        if analytics_yoy.get("min_yoy") is not None and analytics_yoy.get("min_yoy_year") is not None:
            tiles.append(
                (
                    "Biggest annual drop",
                    f"{analytics_yoy['min_yoy']:.1f}%",
                    f"in {int(analytics_yoy['min_yoy_year'])}",
                )
            )
        if analytics_yoy.get("max_yoy") is not None and analytics_yoy.get("max_yoy_year") is not None:
            tiles.append(
                (
                    "Biggest annual increase",
                    f"{analytics_yoy['max_yoy']:.1f}%",
                    f"in {int(analytics_yoy['max_yoy_year'])}",
                )
            )
        if analytics_yoy.get("volatility_yoy") is not None:
            tiles.append(
                (
                    "Year-to-year variability",
                    f"{analytics_yoy['volatility_yoy']:.1f}%",
                    "How much annual change fluctuates",
                )
            )
    else:
        if analytics_level.get("cagr_5y") is not None:
            tiles.append(
                (
                    "Avg. annual growth",
                    f"{analytics_level['cagr_5y'] * 100:.1f}%",
                    "How fast values grew or shrank each year on average",
                )
            )
        if analytics_level.get("min_value") is not None and analytics_level.get("min_year") is not None:
            tiles.append(
                (
                    "Lowest point",
                    f"{analytics_level['min_value']:,.0f}",
                    f"in {int(analytics_level['min_year'])}",
                )
            )
        if analytics_level.get("max_value") is not None and analytics_level.get("max_year") is not None:
            tiles.append(
                (
                    "Highest point",
                    f"{analytics_level['max_value']:,.0f}",
                    f"in {int(analytics_level['max_year'])}",
                )
            )
        if analytics_level.get("growth_volatility") is not None:
            tiles.append(
                (
                    "Year-to-year variability",
                    f"{analytics_level['growth_volatility']:.1f}%",
                    "How much annual change fluctuates",
                )
            )

    if tiles:
        cols = st.columns(len(tiles))
        for col, (label, value, delta) in zip(cols, tiles):
            with col:
                st.metric(label, value, delta)

    dataset_title_for_summary = (
        f"{dataset_label} — {selected_series_label}" if selected_series_label else dataset_label
    )
    narrative = build_narrative_summary(
        dataset_title=dataset_title_for_summary,
        analytics_level=analytics_level,
        analytics_yoy=analytics_yoy,
        analytics_options=analytics_options,
        last_year=yr_to,
        unit_label=unit_lbl,
        df=chart_df,
        label_col=label_col,
        value_col=value_col_for_chart,
    )

    if narrative:
        st.subheader("Summary")
        st.markdown(narrative)

    caption_text = dataset_title_for_summary
    st.caption(caption_text)

    render_dataset_notes(table_cfg)

    last_period = compute_last_updated_period(f)
    if last_period is not None:
        st.caption(f"Last available period in dataset: {format_last_period(last_period)}")

    long_df = chart_df[["YEAR", "GEO", label_col, value_col_for_chart]].copy()
    present_labels = sorted(long_df[label_col].dropna().unique().tolist())
    tooltip_fields = [("GEO", "Geography")]
    if dim_col:
        tooltip_fields.append((dim_col, "Series"))
    series_piece = f" — {selected_series_label}" if selected_series_label else ""
    unit_lbl = get_unit_label(f)
    y_title = f"{dataset_label}{series_piece}{(' (' + unit_lbl + ')') if unit_lbl else ''}"

    dl_name = build_download_name(
        dataset_label, selected_series_label, yr_from, yr_to, present_labels
    )
    alt.renderers.set_embed_options(
        actions={"export": True, "source": False, "compiled": False, "editor": False},
        downloadFileName=dl_name,
    )

    chart = make_line_chart(
        long_df,
        y_title,
        present_labels,
        value_col=value_col_for_chart,
        color_col=label_col,
        color_title="Geography / series" if dim_col else "Geography",
        tooltip_fields=tooltip_fields,
        analytics_options=analytics_options,
    )
    chart_tab, data_tab = st.tabs(["Chart", "Data"])

    with chart_tab:
        st.altair_chart(chart, width="stretch")

        file_stem_parts = [table_cfg["id"].replace(" ", "_")]
        if selected_series_label:
            file_stem_parts.append(str(selected_series_label).replace(" ", "_"))
        if present_labels:
            file_stem_parts.append("_".join(g.replace(" ", "_") for g in present_labels))
        file_stem = "_".join(file_stem_parts)

        png_bytes = get_chart_png_bytes(chart, file_stem=file_stem)

        if png_bytes is not None:
            st.download_button(
                label="Download chart as PNG",
                data=png_bytes,
                file_name=f"{file_stem}.png",
                mime="image/png",
                key=f"download_chart_svg_{table_cfg['id']}",
            )
        else:
            st.caption("Chart image download not available in this environment.")

    with data_tab:
        if not f.empty:
            st.dataframe(f.head(500))
        else:
            st.info("No data available for the selected filters.")

    if not f.empty:
        csv_buffer = io.StringIO()
        f.to_csv(csv_buffer, index=False)
        geo_piece = safe_slug("-".join(present_labels))
        series_piece = safe_slug(selected_series_label)
        file_parts = [safe_slug(table_id), series_piece, geo_piece, f"{yr_from}_{yr_to}"]
        file_name = "_".join([p for p in file_parts if p]) or "dataset"
        file_name = file_name + ".csv"
        st.download_button(
            label="Download data as CSV",
            data=csv_buffer.getvalue(),
            file_name=file_name,
            mime="text/csv",
            help="Download the data used in this chart for further analysis.",
        )

    unit_caption = f"Unit: {unit_lbl if unit_lbl else '—'}"
    st.caption(unit_caption)
    render_source_caption(table_cfg)
    _desc = DATASET_DESCRIPTIONS.get(table_id)
    if _desc:
        st.info(f"\U0001f4ca **What this data shows:** {_desc}")

    selected_dataset_id = table_cfg.get("id", table_id)
    selected_series_for_params = selected_series_label
    selected_geos_for_params = selected_geos
    year_range_for_params = (yr_from, yr_to)
    inflation_adjusted_for_params = False

# ============================================================
# FARM FINANCE – ADDITIONAL DETAIL VIEW
# ============================================================

    # Return footer state for URL sharing
    return {
        "selected_dataset_id": locals().get("selected_dataset_id"),
        "selected_series_for_params": locals().get("selected_series_for_params"),
        "selected_geos_for_params": locals().get("selected_geos_for_params", []),
        "year_range_for_params": locals().get("year_range_for_params"),
        "inflation_adjusted_for_params": locals().get("inflation_adjusted_for_params", False),
    }
