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


def render_environment_land_view(params, analytics_options):
    """Render the Environment & Land Use view. Returns footer-state dict."""
    st.subheader("Environment & Land Use")

    dataset_options = {
        "Land use (Census of Agriculture 2021)": "32-10-0249-01.csv",
        "Land use (Census of Agriculture 2011 & 2016)": "32-10-0406-01.csv",
        "Irrigation volume by province": "38-10-0239-01.csv",
        "Irrigation volume by crop type": "38-10-0240-01.csv",
        "Irrigated area by crop type": "38-10-0241-01.csv",
        "Farms by irrigation status": "38-10-0242-01.csv",
        "Irrigation water sources": "38-10-0246-01.csv",
        "Water & energy conservation practices": "38-10-0249-01.csv",
        "Agriculture greenhouse gas emissions": "38-10-0097-01.csv",
        "Fertilizers, herbicides & pesticide use (Census)": "32-10-0408-01.csv",
    }

    dataset_labels = list(dataset_options.keys())
    default_dataset_label = dataset_labels[0]
    dataset_from_url = _get_param(
        params, "dataset", dataset_options[default_dataset_label].replace(".csv", "")
    )
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

    df = ensure_year_column(df)
    if "YEAR" in df.columns:
        df = df.dropna(subset=["YEAR"]).copy()
        df["YEAR"] = df["YEAR"].astype(int)
    if "VALUE" in df.columns:
        df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")

    series_col = find_series_column(table_id, df)
    additional_dim = None

    if table_id in {"32-10-0249-01", "32-10-0406-01"}:
        series_col = find_column_fuzzy(df, ["Land use", "Land use category", "Type of land use"]) or series_col
    elif table_id == "38-10-0239-01":
        province_col = find_column_fuzzy(df, ["Geography", "Province", "Geography (drainage region)"])
        drainage_col = find_column_fuzzy(df, ["Drainage region"])
        series_col = drainage_col or province_col or series_col
        additional_dim = province_col if series_col == drainage_col else drainage_col
    elif table_id in {"38-10-0240-01", "38-10-0241-01"}:
        crop_col = find_column_fuzzy(df, ["Crop", "Crop type", "Type of crop"])
        irrigation_method_col = find_column_fuzzy(df, ["Irrigation method", "Irrigation system"])
        series_col = crop_col or series_col
        additional_dim = irrigation_method_col if irrigation_method_col and irrigation_method_col != series_col else additional_dim
    elif table_id == "38-10-0242-01":
        status_col = find_column_fuzzy(df, ["Irrigation status", "Irrigation"])
        series_col = status_col or series_col
    elif table_id == "38-10-0246-01":
        source_col = find_column_fuzzy(df, ["Source of water", "Water source", "Source of irrigation water"])
        measure_col = find_column_fuzzy(df, ["Type of measure", "Measure", "Statistics"])
        series_col = source_col or series_col
        additional_dim = measure_col if measure_col and measure_col != series_col else additional_dim
    elif table_id == "38-10-0249-01":
        practice_col = find_column_fuzzy(df, ["Conservation practice", "Practice", "Type of practice"])
        series_col = practice_col or series_col
    elif table_id == "38-10-0097-01":
        industry_col = find_column_fuzzy(df, ["Industry"])
        gas_col = find_column_fuzzy(df, ["Gas"])
        if industry_col:
            df = df[df[industry_col].str.contains("agric", case=False, na=False)].copy()
        series_col = gas_col or industry_col or series_col
        additional_dim = industry_col if series_col == gas_col else gas_col

    selected_series = None
    if series_col and series_col in df.columns:
        series_options = sorted(df[series_col].dropna().unique().tolist())
        default_series = next((s for s in series_options if str(s).lower().startswith("total")), series_options[0])
        selected_series = st.sidebar.selectbox(
            "Series", series_options, index=series_options.index(default_series)
        )
        df = df[df[series_col] == selected_series].copy()
    else:
        st.info("This dataset has no separate series dimension; using geography comparison instead.")

    metadata_cols = STATCAN_METADATA_COLUMNS.union({"REF_DATE", "YEAR", "GEO", "VALUE"})
    extra_cols = [
        c
        for c in df.columns
        if c
        not in metadata_cols
        and c not in {series_col, additional_dim}
        and df[c].dropna().nunique() > 1
    ]

    breakdown_cols = [additional_dim] if additional_dim else []
    breakdown_cols += extra_cols

    if breakdown_cols:
        with st.sidebar.expander("Additional breakdowns"):
            for col in breakdown_cols:
                opts = sorted(df[col].dropna().unique().tolist(), key=lambda x: str(x))
                all_label = f"All {col.lower()}"
                default_val = pick_default_breakdown_option(df, col)
                options_with_all = [all_label] + opts
                default_idx = options_with_all.index(default_val) if default_val in opts else (1 if opts else 0)
                choice = st.selectbox(
                    col, options_with_all, key=f"{table_id}_{col}", index=default_idx
                )
                if choice != all_label:
                    df = df[df[col] == choice].copy()

    geo_col = "GEO"

    if geo_col not in df.columns:
        st.error("Expected column 'GEO' not found in this dataset.")
        st.stop()

    geos_all = sorted(df[geo_col].dropna().unique().tolist())
    default_geos = get_default_geos(geos_all)
    if not default_geos and geos_all:
        default_geos = geos_all[:3]
    geos_param = _get_param(params, "geos", None)
    url_geos = [g for g in (geos_param.split(",") if geos_param else []) if g in geos_all]
    geo_pins = [g for g in geos_all if g in ["Canada", "Ontario"]]
    with st.sidebar:
        selected_geos = multiselect_with_pins(
            "Geography",
            geos_all,
            key=f"{table_id}_geos",
            pinned_options=geo_pins,
            url_values=url_geos,
            default_values=default_geos,
        )

    if not selected_geos:
        st.info("Select at least one geography to display the data.")
        st.stop()

    yrs = df[df[geo_col].isin(selected_geos)]["YEAR"].dropna().astype(int)
    if yrs.empty:
        st.info("No data for selected filters.")
        st.stop()

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
        yr_from, yr_to = st.sidebar.slider(
            "Year range",
            min_value=yr_min,
            max_value=yr_max,
            value=(start_default, end_default),
        )

    f = df[(df[geo_col].isin(selected_geos)) & (df["YEAR"].between(yr_from, yr_to))].copy()
    if f.empty:
        st.info("No data for selected filters.")
        st.stop()

    plot_df = ensure_year_column(f)
    group_cols = ["YEAR", geo_col]
    if series_col:
        group_cols.append(series_col)

    plot_df = plot_df.groupby(group_cols, as_index=False)["VALUE"].sum()

    if plot_df.empty:
        st.info("No data for selected filters.")
        st.stop()

    unit_lbl = get_unit_label(plot_df)
    value_col_for_chart = "VALUE"
    inflation_checked = False
    inflation_applied = False
    base_year: int | None = None

    aggregated = plot_df.groupby("YEAR", as_index=False)[value_col_for_chart].sum()
    analytics_level = compute_time_series_analytics(
        aggregated, value_col=value_col_for_chart, time_col="YEAR"
    )
    analytics_yoy = compute_yoy_analytics(
        aggregated, value_col=value_col_for_chart, time_col="YEAR"
    )

    latest_slice = aggregated[aggregated["YEAR"] == yr_to]
    prev_slice = aggregated[aggregated["YEAR"] < yr_to]
    total_latest = latest_slice[value_col_for_chart].sum()

    metric_label = f"{dataset_label} in {yr_to}"
    if selected_series:
        metric_label = f"{metric_label} — {selected_series}"

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
        st.metric(metric_label, f"{total_latest:,.0f}")

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

    series_piece = f" — {selected_series}" if selected_series else ""
    caption_text = f"{dataset_label}{series_piece}"
    st.caption(caption_text)
    render_dataset_notes(table_cfg)

    last_period = compute_last_updated_period(plot_df)
    if last_period is not None:
        st.caption(f"Last available period in dataset: {format_last_period(last_period)}")

    present_geos = sorted(plot_df[geo_col].unique().tolist())
    y_title = f"{dataset_label}{(' (' + unit_lbl + ')') if unit_lbl else ''}"

    dl_name = build_download_name(dataset_label, selected_series, yr_from, yr_to, present_geos)
    alt.renderers.set_embed_options(
        actions={"export": True, "source": False, "compiled": False, "editor": False},
        downloadFileName=dl_name,
    )

    if yr_min == yr_max:
        chart = (
            alt.Chart(plot_df)
            .mark_bar()
            .encode(
                x=alt.X("GEO:N", title="Geography"),
                y=alt.Y(f"{value_col_for_chart}:Q", title=y_title, axis=alt.Axis(format="~s")),
                tooltip=[
                    alt.Tooltip("GEO:N", title="Geography"),
                    alt.Tooltip(f"{value_col_for_chart}:Q", title="Value", format=","),
                ],
                color=alt.Color("GEO:N", title="Geography", scale=altair_colour_scale(present_geos)),
            )
            .properties(height=420)
        )
    else:
        long_df = plot_df[["YEAR", geo_col, value_col_for_chart]].copy()
        long_df["YEAR"] = long_df["YEAR"].astype(int)
        chart = make_line_chart(
            long_df,
            y_title,
            present_geos,
            value_col=value_col_for_chart,
            tooltip_fields=[(geo_col, "Geography")],
            analytics_options=analytics_options,
        )

    chart_tab, data_tab = st.tabs(["Chart", "Data"])

    with chart_tab:
        st.altair_chart(chart, width="stretch")

        file_stem_parts = [table_cfg["id"].replace(" ", "_")]
        if selected_series:
            file_stem_parts.append(str(selected_series).replace(" ", "_"))
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
        if not plot_df.empty:
            st.dataframe(plot_df.head(500))
        else:
            st.info("No data available for the selected filters.")
    if not plot_df.empty:
        csv_buffer = io.StringIO()
        plot_df.to_csv(csv_buffer, index=False)
        geo_piece = safe_slug("-".join(present_geos))
        series_piece_slug = safe_slug(selected_series)
        file_parts = [safe_slug(table_id), series_piece_slug, geo_piece, f"{yr_from}_{yr_to}"]
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
    selected_series_for_params = selected_series
    selected_geos_for_params = present_geos
    year_range_for_params = (yr_from, yr_to)
    inflation_adjusted_for_params = inflation_checked

# ============================================================
# PRODUCTION & YIELDS VIEW
# ============================================================

    # Return footer state for URL sharing
    return {
        "selected_dataset_id": locals().get("selected_dataset_id"),
        "selected_series_for_params": locals().get("selected_series_for_params"),
        "selected_geos_for_params": locals().get("selected_geos_for_params", []),
        "year_range_for_params": locals().get("year_range_for_params"),
        "inflation_adjusted_for_params": locals().get("inflation_adjusted_for_params", False),
    }
