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

from scripts import config_loader
TABLE_CONFIG = config_loader.load_tables(active_only=True)



def render_farm_household_view(params, analytics_options):
    """Render the Farm Household Income & Balance Sheet view. Returns footer-state dict."""
    st.subheader("Farm household income & balance sheet – Canada & Provinces")

    dataset_options = {
        "Farm family income by source": "32-10-0213-01.csv",
        "Total income of farm families": "32-10-0213-01.csv",
        "Balance sheet: assets, liabilities and net worth": "32-10-0101-01.csv",
        "Balance sheet: assets detail": "32-10-0101-01.csv",
        "Balance sheet: liabilities detail": "32-10-0101-01.csv",
        "Financial structure by farm type (average per farm)": "32-10-0102-01.csv",
        "Financial structure by revenue class (average per farm)": "32-10-0103-01.csv",
        "Capital purchases and sales by farms (average per farm)": "32-10-0104-01.csv",
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
    if table_id == "32-10-0213-01" and dataset_label == "Farm family income by source":
        income_source_col = find_column_fuzzy(
            df, ["source of income", "Income source", "Source of income"]
        )
        if income_source_col:
            dim_col = income_source_col
    selected_series_label: str | None = None
    selected_series_list: list[str] | None = None

    if table_id == "32-10-0213-01" and dataset_label == "Farm family income by source":
        income_col = find_income_source_column(df)
        if income_col:
            dim_col = income_col

    if dim_col:
        series_options = sorted(df[dim_col].dropna().unique().tolist())
        max_defaults = 5 if dataset_label == "Farm family income by source" else 3
        default_series_list = infer_default_series_selection(
            series_options, max_items=max_defaults
        )

        series_param = _get_param(params, "series", None)
        if series_param:
            parsed = [s for s in series_param.split(",") if s in series_options]
            if parsed:
                default_series_list = parsed

        if len(series_options) == 1:
            selected_series_list = series_options
        else:
            selected_series_list = st.sidebar.multiselect(
                "Series", series_options, default=default_series_list
            )
            if not selected_series_list:
                selected_series_list = default_series_list or series_options[:1]

        selected_series_label = ", ".join(map(str, selected_series_list)) if selected_series_list else None
        df = df[df[dim_col].isin(selected_series_list)].copy()

    if "GEO" not in df.columns or "VALUE" not in df.columns:
        st.error("Expected 'GEO' and 'VALUE' columns not found.")
        st.stop()

    geos = sorted(df["GEO"].dropna().unique().tolist())
    default_geos: list[str] = []
    if "Canada" in geos:
        default_geos.append("Canada")
    if "Ontario" in geos:
        default_geos.append("Ontario")
    if not default_geos and geos:
        default_geos = [geos[0]]
    geos_param = _get_param(params, "geos", None)
    if geos_param:
        parsed_geos = [g for g in geos_param.split(",") if g in geos]
        if parsed_geos:
            default_geos = parsed_geos

    pick = st.sidebar.multiselect("Geography", geos, default=default_geos)

    yrs = df[df["GEO"].isin(pick)]["YEAR"].dropna().astype(int)
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

    f = df[(df["GEO"].isin(pick)) & (df["YEAR"].between(yr_from, yr_to))].copy()
    if f.empty:
        st.info("No data for selected filters.")
        st.stop()

    if table_id in {
        "32-10-0213-01",
        "32-10-0101-01",
        "32-10-0102-01",
        "32-10-0103-01",
        "32-10-0104-01",
        "32-10-0078-01",
        "32-10-0214-01",
    }:
        id_cols = ["YEAR", "GEO"]
        if dim_col is not None:
            id_cols.append(dim_col)

        value_col = "VALUE"

        f = (
            f.groupby(id_cols, as_index=False)[value_col]
            .sum()
        )

    chart_df = f.copy()
    value_col_for_chart = "VALUE"
    time_col = "YEAR"
    unit_lbl = get_unit_label(df)  # Use original df (pre-groupby) so SCALAR_FACTOR/UOM are available
    (
        chart_df,
        value_col_for_chart,
        inflation_applied,
        inflation_checked,
        base_year,
        inflation_note,
        is_dollar_series,
    ) = apply_cpi_adjustment(
        chart_df,
        params,
        dataset_label,
        unit_lbl,
        checkbox_key=f"{table_id}_inflation",
        value_col=value_col_for_chart,
        time_col=time_col,
        table_cfg=table_cfg if isinstance(table_cfg, Mapping) else None,
        table_id=table_id,
        table_config=TABLE_CONFIG,
        _load_table_fn=load_table,
    )

    f = chart_df

    series_descriptor = selected_series_label
    if dataset_label == "Farm family income by source" and series_descriptor:
        series_descriptor = f"Income source: {series_descriptor}"
    elif dim_col and series_descriptor:
        series_descriptor = f"{dim_col}: {series_descriptor}"

    # KPI header: scope to primary geography to avoid cross-geo double-counting
    primary_geo = next((g for g in pick if g == "Canada"), pick[0]) if pick else None
    kpi_df = f[f["GEO"] == primary_geo] if primary_geo else f

    latest_slice = kpi_df[kpi_df["YEAR"] == yr_to]
    prev_slice = kpi_df[kpi_df["YEAR"] < yr_to]
    total_latest = latest_slice[value_col_for_chart].sum()

    metric_label = dataset_label
    if series_descriptor:
        metric_label = f"{metric_label} — {series_descriptor}"
    if primary_geo and len(pick) > 1:
        metric_label = f"{metric_label} ({primary_geo}) in {yr_to}"
    else:
        metric_label = f"{metric_label} in {yr_to}"
    if inflation_applied and base_year is not None:
        metric_label = f"{metric_label} (constant {base_year} dollars)"

    if not prev_slice.empty:
        prev_year = int(prev_slice["YEAR"].max())
        prev_total = prev_slice[prev_slice["YEAR"] == prev_year][value_col_for_chart].sum()
        change = (total_latest - prev_total) / prev_total * 100 if prev_total else 0.0
        scaled_latest = _format_quantity_for_narrative(total_latest, unit_lbl)
        metric_col, delta_col = st.columns([2, 1])
        with metric_col:
            st.metric(metric_label, scaled_latest or f"{total_latest:,.0f}")
        with delta_col:
            st.metric("Change vs prior year", f"{change:+.1f}%")
    else:
        scaled_latest = _format_quantity_for_narrative(total_latest, unit_lbl)
        st.metric(metric_label, scaled_latest or f"{total_latest:,.0f}", "")

    analytics_level = compute_time_series_analytics(
        kpi_df,
        value_col=value_col_for_chart,
        time_col="YEAR",
    )
    analytics_yoy = compute_yoy_analytics(
        kpi_df,
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
            min_display = _format_quantity_for_narrative(analytics_level['min_value'], unit_lbl)
            tiles.append(
                (
                    "Lowest point",
                    min_display or f"{analytics_level['min_value']:,.0f}",
                    f"in {int(analytics_level['min_year'])}",
                )
            )
        if analytics_level.get("max_value") is not None and analytics_level.get("max_year") is not None:
            max_display = _format_quantity_for_narrative(analytics_level['max_value'], unit_lbl)
            tiles.append(
                (
                    "Highest point",
                    max_display or f"{analytics_level['max_value']:,.0f}",
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

    caption_text = dataset_label
    if series_descriptor:
        caption_text = f"{caption_text} — {series_descriptor}"
    if inflation_applied and base_year is not None:
        caption_text = f"{caption_text} (constant {base_year} dollars)"
    st.caption(caption_text)

    render_dataset_notes(table_cfg)

    last_period = compute_last_updated_period(f)
    if last_period is not None:
        st.caption(f"Last available period in dataset: {format_last_period(last_period)}")

    long_df = f[["YEAR", "GEO", value_col_for_chart]].copy()
    if dim_col and dim_col in f.columns:
        long_df["SERIES_DIM"] = f[dim_col]
    else:
        long_df["SERIES_DIM"] = dataset_label
    long_df["LINE_LABEL"] = long_df.apply(
        lambda row: f"{row['GEO']} — {row['SERIES_DIM']}" if dim_col else row["GEO"],
        axis=1,
    )

    present_geos = sorted(long_df["GEO"].unique().tolist())
    present_lines = sorted(long_df["LINE_LABEL"].unique().tolist())
    unit_lbl = get_unit_label(f)
    series_piece = f" — {series_descriptor}" if series_descriptor else ""
    if inflation_applied and base_year is not None and unit_lbl and (
        "dollar" in unit_lbl.lower() or "$" in unit_lbl
    ):
        y_title = f"{dataset_label}{series_piece} — constant {base_year} dollars"
    else:
        y_title = f"{dataset_label}{series_piece}{(' (' + unit_lbl + ')') if unit_lbl else ''}"

    dl_name = build_download_name(
        dataset_label, selected_series_label, yr_from, yr_to, present_geos
    )
    alt.renderers.set_embed_options(
        actions={"export": True, "source": False, "compiled": False, "editor": False},
        downloadFileName=dl_name,
    )

    chart = make_line_chart(
        long_df,
        y_title,
        present_lines,
        value_col=value_col_for_chart,
        color_col="LINE_LABEL",
        color_title="Geography / series" if dim_col else "Geography",
        tooltip_fields=[("GEO", "Geography"), ("SERIES_DIM", dim_col or "Series")],
        analytics_options=analytics_options,
    )
    chart_tab, data_tab = st.tabs(["Chart", "Data"])

    with chart_tab:
        st.altair_chart(chart, width="stretch")

        file_stem_parts = [table_cfg["id"].replace(" ", "_")]
        if selected_series_label:
            file_stem_parts.append(str(selected_series_label).replace(" ", "_"))
        if present_geos:
            file_stem_parts.append("_".join(g.replace(" ", "_") for g in present_geos))
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
        geo_piece = safe_slug("-".join(present_geos))
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

    selected_dataset_id = table_cfg.get("id", table_id)
    selected_geos_for_params = pick
    selected_series_for_params = None
    if selected_series_list:
        selected_series_for_params = ",".join(map(str, selected_series_list))
    elif selected_series_label:
        selected_series_for_params = selected_series_label
    year_range_for_params = (yr_from, yr_to)
    inflation_adjusted_for_params = inflation_checked

    if indexed:
        if index_base_year is not None:
            unit_caption = f"Unit: Index (base year = {index_base_year}, 100 = base)."
        else:
            unit_caption = "Unit: Index (first non-zero year in selected range = 100)."
    else:
        unit_caption = f"Unit: {unit_lbl if unit_lbl else '—'}"
        if inflation_applied and base_year is not None and unit_lbl and (
            "dollar" in unit_lbl.lower() or "$" in unit_lbl
        ):
            unit_caption += (
                f" — constant {base_year} dollars (CPI all-items, Canada, annual average; "
                "StatCan table 18-10-0005-01)."
            )
    st.caption(unit_caption)
    render_source_caption(table_cfg)
    _desc = DATASET_DESCRIPTIONS.get(table_id)
    if _desc:
        st.info(f"\U0001f4ca **What this data shows:** {_desc}")

    selected_dataset_id = table_cfg.get("id", table_id)
    if selected_series_list:
        selected_series_for_params = ",".join(map(str, selected_series_list))
    else:
        selected_series_for_params = selected_series_label
    selected_geos_for_params = present_geos
    year_range_for_params = (yr_from, yr_to)
    inflation_adjusted_for_params = inflation_checked

# ============================================================
# COSTS & INFLATION VIEW
# ============================================================

    # Return footer state for URL sharing
    return {
        "selected_dataset_id": locals().get("selected_dataset_id"),
        "selected_series_for_params": locals().get("selected_series_for_params"),
        "selected_geos_for_params": locals().get("selected_geos_for_params", []),
        "year_range_for_params": locals().get("year_range_for_params"),
        "inflation_adjusted_for_params": locals().get("inflation_adjusted_for_params", False),
    }
