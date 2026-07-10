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


def render_demographics_view(params, analytics_options):
    """Render the Demographics, Labour & Technology view. Returns footer-state dict."""
    st.subheader("Demographics, Labour & Technology")

    dataset_options = {
        "Farm operators by age & sex (2021)": "32-10-0381-01.csv",
        "Farm operators by age (1991–2016)": "32-10-0230-01.csv",
        "Employees in agriculture (by province)": "32-10-0216-01.csv",
        "Employees in agriculture (by revenue class)": "32-10-0217-01.csv",
        "TFWs in agriculture & agri-food (by industry)": "32-10-0218-01.csv",
        "TFWs in agriculture (by revenue class)": "32-10-0220-01.csv",
        "Technologies used on farm operations": "32-10-0379-01.csv",
        # Farm structure & demographics
        "Fertilizer shipments by product type": "32-10-0036-01.csv",
        "Farms by total farm area (historical Census)": "32-10-0156-01.csv",
        "Employees in agriculture (by industry group)": "32-10-0215-01.csv",
        "TFWs by country of citizenship": "32-10-0221-01.csv",
        "Farms by operating arrangement (Census 2021)": "32-10-0235-01.csv",
        "Paid labour (Census 2021)": "32-10-0243-01.csv",
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
    additional_dims: list[str] = []

    if table_id == "32-10-0381-01":
        characteristics_col = find_column_fuzzy(df, ["Characteristics", "Characteristic"]) or series_col
        age_col = find_column_fuzzy(df, ["Age group", "Age group of farm operators"])
        number_ops_col = find_column_fuzzy(
            df, ["Farms according to number of operators", "Number of farm operators", "Number of operators"]
        )
        series_col = characteristics_col or age_col or series_col
        for candidate in [age_col, number_ops_col]:
            if candidate and candidate != series_col:
                additional_dims.append(candidate)
    elif table_id == "32-10-0230-01":
        series_col = find_column_fuzzy(df, ["Age group", "Age group of farm operators"]) or series_col
    elif table_id == "32-10-0216-01":
        series_col = find_column_fuzzy(df, ["Type of employee", "Characteristic", "Employee type"]) or series_col
    elif table_id == "32-10-0217-01":
        series_col = find_column_fuzzy(df, ["Revenue class", "Farm revenue class", "Revenue category"]) or series_col
        stats_col = find_column_fuzzy(
            df, ["Characteristic", "Statistics", "Type of employee", "Employee type"]
        )
        if stats_col and stats_col != series_col:
            additional_dims.append(stats_col)
    elif table_id == "32-10-0218-01":
        series_col = find_column_fuzzy(
            df,
            [
                "North American Industry Classification System (NAICS)",
                "Industry group",
                "Industry",
            ],
        ) or series_col
        measure_col = find_column_fuzzy(
            df,
            ["Characteristic", "Statistics", "Type of worker", "Type of job"],
        )
        if measure_col and measure_col != series_col:
            additional_dims.append(measure_col)
    elif table_id == "32-10-0220-01":
        series_col = find_column_fuzzy(df, ["Revenue class", "Farm revenue class", "Revenue category"]) or series_col
        measure_col = find_column_fuzzy(
            df,
            ["Characteristic", "Statistics", "Type of worker", "Type of job"],
        )
        if measure_col and measure_col != series_col:
            additional_dims.append(measure_col)
    elif table_id == "32-10-0379-01":
        series_col = find_column_fuzzy(df, ["Technology", "Technology type"]) or series_col
        farm_type_col = find_column_fuzzy(df, ["Farm type", "Type of farm"])
        if farm_type_col:
            additional_dims.append(farm_type_col)
    elif table_id == "32-10-0036-01":
        series_col = find_column_fuzzy(df, ["Fertilizer product type", "Age group", "Sex"]) or series_col
        period_col = find_column_fuzzy(df, ["Period"])
        if period_col and period_col != series_col:
            additional_dims.append(period_col)
    elif table_id == "32-10-0156-01":
        series_col = find_column_fuzzy(df, ["Total farm area distribution", "Farm type"]) or series_col
    elif table_id == "32-10-0215-01":
        series_col = find_column_fuzzy(df, ["Industry", "Industry group"]) or series_col
        stats_col = find_column_fuzzy(df, ["Statistics", "Characteristic"])
        if stats_col and stats_col != series_col:
            additional_dims.append(stats_col)
    elif table_id == "32-10-0221-01":
        series_col = find_column_fuzzy(df, ["Country of citizenship"]) or series_col
        stats_col = find_column_fuzzy(df, ["Statistics", "Characteristic"])
        if stats_col and stats_col != series_col:
            additional_dims.append(stats_col)
    elif table_id == "32-10-0235-01":
        series_col = find_column_fuzzy(df, ["Operating arrangement"]) or series_col
    elif table_id == "32-10-0243-01":
        series_col = find_column_fuzzy(df, ["Paid agricultural workers"]) or series_col

    selected_series_list: list[str] = []
    if series_col and series_col in df.columns:
        series_options = sorted(df[series_col].dropna().unique().tolist())
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
            )
        if not selected_series_list:
            st.info("Select at least one series to display the data.")
            st.stop()
        df = df[df[series_col].isin(selected_series_list)].copy()
    else:
        st.info("This dataset has no separate series dimension; using geography comparison instead.")

    selected_series_label = (
        ", ".join(map(str, selected_series_list)) if selected_series_list else None
    )

    metadata_cols = STATCAN_METADATA_COLUMNS.union({"REF_DATE", "YEAR", "GEO", "VALUE"})
    extra_cols = [
        c
        for c in df.columns
        if c
        not in metadata_cols
        and c != series_col
        and c not in additional_dims
        and df[c].dropna().nunique() > 1
    ]

    breakdown_cols = [c for c in additional_dims if c] + extra_cols

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

    label_col = "GEO_SERIES_LABEL"
    if series_col:
        plot_df[label_col] = plot_df[geo_col].astype(str) + " – " + plot_df[series_col].astype(str)
    else:
        plot_df[label_col] = plot_df[geo_col].astype(str)

    unit_lbl = get_unit_label(plot_df)
    value_col_for_chart = "VALUE"
    inflation_checked = False
    inflation_applied = False
    base_year: int | None = None

    time_col_for_analytics = "YEAR"
    if "DATE" in plot_df.columns:
        try:
            plot_df["DATE"] = pd.to_datetime(plot_df["DATE"], errors="coerce")
            if pd.api.types.is_datetime64_any_dtype(plot_df["DATE"]) and plot_df["DATE"].notna().any():
                time_col_for_analytics = "DATE"
        except Exception:
            time_col_for_analytics = "YEAR"

    if not plot_df.empty:
        try:
            last_time = plot_df[time_col_for_analytics].max()
            last_year = _extract_year(last_time)
        except Exception:
            last_year = None
    else:
        last_year = None

    aggregated_year = plot_df.groupby("YEAR", as_index=False)[value_col_for_chart].sum()
    aggregated_for_analytics = plot_df.groupby(
        time_col_for_analytics, as_index=False
    )[value_col_for_chart].sum()

    analytics_level = None
    analytics_yoy = None
    if time_col_for_analytics in aggregated_for_analytics.columns:
        analytics_level = compute_time_series_analytics(
            aggregated_for_analytics,
            value_col=value_col_for_chart,
            time_col=time_col_for_analytics,
        )
        analytics_yoy = compute_yoy_analytics(
            aggregated_for_analytics,
            value_col=value_col_for_chart,
            time_col=time_col_for_analytics,
        )

    latest_slice = aggregated_year[aggregated_year["YEAR"] == yr_to]
    prev_slice = aggregated_year[aggregated_year["YEAR"] < yr_to]
    total_latest = latest_slice[value_col_for_chart].sum()

    metric_label = f"{dataset_label} in {yr_to}"
    if selected_series_label:
        metric_label = f"{metric_label} — {selected_series_label}"

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

    dataset_title_for_summary = (
        f"{dataset_label} — {selected_series_label}" if selected_series_label else dataset_label
    )
    narrative = build_narrative_summary(
        dataset_title=dataset_title_for_summary,
        analytics_level=analytics_level,
        analytics_yoy=analytics_yoy,
        analytics_options=analytics_options,
        last_year=last_year,
        unit_label=unit_lbl,
        df=plot_df,
        label_col=label_col,
        value_col=value_col_for_chart,
    )

    if narrative:
        st.subheader("Summary")
        st.markdown(narrative)

    series_piece = f" — {selected_series_label}" if selected_series_label else ""
    caption_text = f"{dataset_label}{series_piece}"
    st.caption(caption_text)
    render_dataset_notes(table_cfg)

    last_period = compute_last_updated_period(plot_df)
    if last_period is not None:
        st.caption(f"Last available period in dataset: {format_last_period(last_period)}")

    present_labels = sorted(plot_df[label_col].unique().tolist())
    y_title = f"{dataset_label}{(' (' + unit_lbl + ')') if unit_lbl else ''}"

    dl_name = build_download_name(
        dataset_label, selected_series_label, yr_from, yr_to, present_labels
    )
    alt.renderers.set_embed_options(
        actions={"export": True, "source": False, "compiled": False, "editor": False},
        downloadFileName=dl_name,
    )

    if yr_min == yr_max:
        chart = (
            alt.Chart(plot_df)
            .mark_bar()
            .encode(
                x=alt.X(f"{label_col}:N", title="Geography / series"),
                y=alt.Y(f"{value_col_for_chart}:Q", title=y_title, axis=alt.Axis(format="~s")),
                tooltip=[
                    alt.Tooltip(f"{label_col}:N", title="Geography / series"),
                    alt.Tooltip(f"{value_col_for_chart}:Q", title="Value", format=","),
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
        long_df = plot_df[["YEAR", label_col, value_col_for_chart]].copy()
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
        if not plot_df.empty:
            st.dataframe(plot_df.head(500))
        else:
            st.info("No data available for the selected filters.")
    if not plot_df.empty:
        csv_buffer = io.StringIO()
        plot_df.to_csv(csv_buffer, index=False)
        geo_piece = safe_slug("-".join(present_labels))
        series_piece_slug = safe_slug(selected_series_label)
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
    selected_series_for_params = selected_series_label
    selected_geos_for_params = selected_geos
    year_range_for_params = (yr_from, yr_to)
    inflation_adjusted_for_params = inflation_checked

# ============================================================
# TRADE & SUPPLY CHAINS (AGRI-FOOD) VIEW
# ============================================================

    # Return footer state for URL sharing
    return {
        "selected_dataset_id": locals().get("selected_dataset_id"),
        "selected_series_for_params": locals().get("selected_series_for_params"),
        "selected_geos_for_params": locals().get("selected_geos_for_params", []),
        "year_range_for_params": locals().get("year_range_for_params"),
        "inflation_adjusted_for_params": locals().get("inflation_adjusted_for_params", False),
    }
