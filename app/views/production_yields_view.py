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



def render_production_yields_view(params, analytics_options):
    """Render the Production & Yields view. Returns footer-state dict."""
    st.subheader("Production & Yields")

    dataset_options = {
        "Field crop production & yields": "32-10-0359-01.csv",
        "Cattle inventories": "32-10-0130-01.csv",
        "Hog inventories": "32-10-0160-01.csv",
        "Fruit production & farm gate value": "32-10-0364-01.csv",
        "Vegetable production & farm gate value": "32-10-0365-01.csv",
        "Greenhouse vegetables & fruits": "32-10-0456-01.csv",
        "Organic fruit & vegetable production": "32-10-0212-01.csv",
        "Hogs, sheep & lambs – farm and meat production": "32-10-0126-01.csv",
        "Hog supply & disposition": "32-10-0200-01.csv",
        "Sheep & lamb inventories": "32-10-0129-01.csv",
        "Cattle & calves – farm and meat production": "32-10-0125-01.csv",
        "Cattle supply & disposition": "32-10-0139-01.csv",
        "Sheep & lambs – supply & disposition": "32-10-0141-01.csv",
        "Frozen & chilled meat stocks": "32-10-0137-01.csv",
        "Pre-harvest crop estimates (area, yield, production)": "32-10-0002-01.csv",
        "Cattle farms & average herd size": "32-10-0151-01.csv",
        "Hog farms & average herd size": "32-10-0202-01.csv",
        # Census snapshots (2021)
        "Field crops & hay (Census 2021)": "32-10-0309-01.csv",
        "Fruits (Census 2021)": "32-10-0315-01.csv",
        "Field vegetables (Census 2021)": "32-10-0355-01.csv",
        "Greenhouse products (Census 2021)": "32-10-0360-01.csv",
        "Sheep inventory (Census 2021)": "32-10-0371-01.csv",
        # Infrastructure
        "Storage capacity of grain and oilseeds": "32-10-0003-01.csv",
        # Productivity (RBC Capital Gains dataset)
        "Multifactor productivity — agriculture": "36-10-0217-01.csv",
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
    statistic_col = None

    if table_id == "32-10-0359-01":
        series_col = find_column_fuzzy(df, ["Crop", "Field crop", "Type of crop"]) or series_col
        statistic_col = find_column_fuzzy(
            df,
            ["Statistic", "Prices", "Farm value", "Type of crop statistic", "Measure"],
        )
    elif table_id == "32-10-0130-01":
        series_col = find_column_fuzzy(df, ["Class of cattle", "Cattle class", "Type of cattle"]) or series_col
    elif table_id == "32-10-0160-01":
        series_col = find_column_fuzzy(df, ["Type of hog", "Hog class", "Category"]) or series_col
    elif table_id in {"32-10-0364-01", "32-10-0365-01", "32-10-0456-01", "32-10-0212-01"}:
        series_col = find_column_fuzzy(
            df,
            [
                "Fruit",
                "Vegetable",
                "Product",
                "Crop",
                "Horticultural product",
                "Greenhouse product",
            ],
        ) or series_col
        statistic_col = find_column_fuzzy(
            df,
            [
                "Type of measure",
                "Measure",
                "Statistic",
                "Type of production",
                "Type of product measure",
            ],
        )
    elif table_id == "32-10-0126-01":
        series_col = find_column_fuzzy(
            df,
            [
                "Livestock",
                "Product",
                "Animal",
                "Commodity",
                "Type of production",
            ],
        ) or series_col
        statistic_col = find_column_fuzzy(
            df,
            [
                "Type of production",
                "Production type",
                "Type of farm production",
                "Type of meat production",
            ],
        )
    elif table_id == "32-10-0200-01":
        series_col = find_column_fuzzy(
            df,
            [
                "Supply and disposition",
                "Supply",
                "Disposition",
                "Component",
                "Type of supply",
                "Type of disposition",
            ],
        ) or series_col
        statistic_col = find_column_fuzzy(
            df,
            [
                "Type of farm",
                "Type of operation",
                "Classification",
            ],
        )
    elif table_id == "32-10-0125-01":
        series_col = find_column_fuzzy(
            df, ["Livestock", "Cattle", "Animal", "Type of animal", "Commodity"]
        ) or series_col
        statistic_col = find_column_fuzzy(
            df, ["Type of production", "Production type", "Statistic"]
        )
    elif table_id in {"32-10-0139-01", "32-10-0141-01"}:
        series_col = find_column_fuzzy(
            df, ["Supply and disposition", "Supply", "Component", "Disposition"]
        ) or series_col
    elif table_id == "32-10-0137-01":
        series_col = find_column_fuzzy(
            df, ["Product", "Commodity", "Meat product", "Type of meat"]
        ) or series_col
    elif table_id == "32-10-0002-01":
        series_col = find_column_fuzzy(
            df, ["Type of crop", "Crop", "Principal field crop", "Commodity"]
        ) or series_col
        statistic_col = find_column_fuzzy(
            df, ["Estimate", "Type of estimate", "Statistic", "Area, yield or production"]
        )
    elif table_id in {"32-10-0151-01", "32-10-0202-01"}:
        series_col = find_column_fuzzy(
            df, ["Number of cattle", "Number of hogs", "Statistic", "Type of statistic", "Farms or animals"]
        ) or series_col

    metadata_exclusions = {c.lower() for c in STATCAN_METADATA_COLUMNS}
    dim_cols = [
        c
        for c in df.columns
        if c
        not in {"YEAR", "GEO", "VALUE", "deflator"}
        and not pd.api.types.is_numeric_dtype(df[c])
        and c.lower() not in metadata_exclusions
    ]

    selected_series_list: list[str] = []
    if series_col:
        all_series_vals = sorted(df[series_col].dropna().unique().tolist())

        dataset_id_for_defaults = table_cfg.get("id", table_id)
        preferred_order = [
            "all farm types",
            "all farms",
            "total",
            "all",
        ]
        heuristic_default = next(
            (s for s in all_series_vals if any(pref in str(s).lower() for pref in preferred_order)),
            None,
        )
        series_default = (
            [heuristic_default]
            if heuristic_default
            else get_default_series(dataset_id_for_defaults, all_series_vals)
        )
        series_pinned = [s for s in all_series_vals if str(s).lower().startswith("total")]
        series_param = _get_param(params, "series", None)
        url_series = (
            [s for s in (series_param.split(",") if series_param else []) if s in all_series_vals]
        )

        with st.sidebar:
            selected_series_list = multiselect_with_pins(
                "Series (multiple allowed)",
                all_series_vals,
                key=f"{table_id}_series",
                pinned_options=series_pinned,
                url_values=url_series,
                default_values=series_default,
            )
        if selected_series_list:
            df = df[df[series_col].isin(selected_series_list)].copy()
    else:
        st.info("This dataset has no separate series dimension; using geography comparison instead.")

    selected_series_label = (
        ", ".join(map(str, selected_series_list)) if selected_series_list else None
    )

    remaining_dims = [c for c in dim_cols if c != series_col]
    if statistic_col and statistic_col not in remaining_dims and statistic_col != series_col:
        remaining_dims.insert(0, statistic_col)

    if remaining_dims:
        with st.sidebar.expander("Additional breakdowns"):
            for col in remaining_dims:
                options = sorted(df[col].dropna().unique().tolist(), key=lambda x: str(x))
                if not options:
                    continue
                default_option = pick_default_breakdown_option(df, col) or options[0]

                selected_opt = st.selectbox(
                    col,
                    options,
                    index=options.index(default_option) if default_option in options else 0,
                    key=f"{table_id}_{col}",
                )
                df = df[df[col] == selected_opt].copy()

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
    is_dollar_series = False
    for col in ["UOM", "Unit of measure", "UNIT"]:
        if col in plot_df.columns:
            if plot_df[col].astype(str).str.contains("dollar|\$", case=False, regex=True).any():
                is_dollar_series = True
                break
    if not is_dollar_series and unit_lbl:
        lowered_unit = unit_lbl.lower()
        if "dollar" in lowered_unit or "$" in lowered_unit:
            is_dollar_series = True

    inflation_label = "Adjust for inflation (CPI, Canada)"
    inflation_help = (
        "Uses CPI all-items, Canada, annual average (StatCan table 18-10-0005-01) "
        "to express values in constant-dollar terms, using the last year in the series as the base year."
    )
    inflation_param = _get_param(params, "inflation", "nominal")
    inflation_checked = False
    if is_dollar_series:
        inflation_checked = st.sidebar.checkbox(
            inflation_label,
            value=inflation_param == "real",
            help=inflation_help,
            key=f"{table_id}_inflation",
        )

    value_col_for_chart = "VALUE"
    inflation_applied = False
    base_year: int | None = None
    index_base_year: int | None = None
    indexed = False

    if is_dollar_series and inflation_checked:
        try:
            cpi = load_cpi_deflators(
                table_config=TABLE_CONFIG,
                _load_table_fn=load_table,
            )
        except Exception:
            cpi = None
        series_years = pd.to_numeric(plot_df["YEAR"], errors="coerce").dropna().astype(int)
        if not series_years.empty:
            base_year = int(series_years.max())
        if cpi is not None and base_year is not None and base_year in cpi["YEAR"].values:
            base_cpi = float(cpi.loc[cpi["YEAR"] == base_year, "cpi"].iloc[0])
            cpi = cpi.assign(deflator=base_cpi / cpi["cpi"])
            cpi_for_merge = cpi.rename(columns={"YEAR": "CPI_YEAR"})
            cpi_for_merge = (
                cpi_for_merge.groupby("CPI_YEAR", as_index=False)[["deflator"]]
                .mean()
            )
            plot_df = plot_df.merge(
                cpi_for_merge[["CPI_YEAR", "deflator"]],
                left_on="YEAR",
                right_on="CPI_YEAR",
                how="left",
            ).drop(columns=["CPI_YEAR"], errors="ignore")
            if "deflator" in plot_df.columns and plot_df["deflator"].notna().any():
                plot_df["VALUE_REAL"] = plot_df[value_col_for_chart] * plot_df["deflator"]
                value_col_for_chart = "VALUE_REAL"
                inflation_applied = True

    base_year_for_index = yr_from
    group_cols_for_index = [label_col]

    plot_df, value_col_for_chart, index_base_year, indexed = apply_index_to_base_if_needed(
        plot_df,
        value_col=value_col_for_chart,
        year_col="YEAR",
        base_year=base_year_for_index,
        group_cols=group_cols_for_index,
        analytics_options=analytics_options,
    )

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
    if selected_series_label:
        metric_label = f"{metric_label} — {selected_series_label}"
    if inflation_applied and base_year is not None:
        metric_label = f"{metric_label} (constant {base_year} dollars)"

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
        last_year=yr_to,
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
    if inflation_applied and base_year is not None:
        caption_text = f"{caption_text} (constant {base_year} dollars)"
    st.caption(caption_text)
    render_dataset_notes(table_cfg)

    last_period = compute_last_updated_period(plot_df)
    if last_period is not None:
        st.caption(f"Last available period in dataset: {format_last_period(last_period)}")

    present_labels = sorted(plot_df[label_col].unique().tolist())
    if indexed:
        if index_base_year is not None:
            y_title = f"{dataset_label} — Index (base year = {index_base_year}, 100 = base)"
        else:
            y_title = (
                f"{dataset_label} — Index (first non-zero year in selected range = 100)"
            )
    else:
        y_title = f"{dataset_label}{(' (' + unit_lbl + ')') if unit_lbl else ''}"
        if inflation_applied and base_year is not None and unit_lbl and (
            "dollar" in unit_lbl.lower() or "$" in unit_lbl
        ):
            y_title = f"{dataset_label}{series_piece} — constant {base_year} dollars"

    dl_name = build_download_name(
        dataset_label, selected_series_label, yr_from, yr_to, present_labels
    )
    alt.renderers.set_embed_options(
        actions={"export": True, "source": False, "compiled": False, "editor": False},
        downloadFileName=dl_name,
    )

    if yr_min == yr_max:
        tooltip_fields = [alt.Tooltip("GEO:N", title="Geography")]
        if series_col:
            tooltip_fields.append(alt.Tooltip(f"{series_col}:N", title="Series"))
        tooltip_fields.append(alt.Tooltip(f"{value_col_for_chart}:Q", title="Value", format=","))

        chart = (
            alt.Chart(plot_df)
            .mark_bar()
            .encode(
                x=alt.X(f"{label_col}:N", title="Geography / series"),
                y=alt.Y(f"{value_col_for_chart}:Q", title=y_title, axis=alt.Axis(format="~s")),
                tooltip=tooltip_fields,
                color=alt.Color(
                    f"{label_col}:N",
                    title="Geography / series",
                    scale=altair_colour_scale(present_labels),
                ),
            )
            .properties(height=420)
        )
    else:
        line_cols = ["YEAR", geo_col, value_col_for_chart, label_col]
        if series_col:
            line_cols.append(series_col)
        long_df = plot_df[line_cols].copy()
        long_df["YEAR"] = long_df["YEAR"].astype(int)
        tooltip_fields = [(geo_col, "Geography")]
        if series_col:
            tooltip_fields.append((series_col, "Series"))
        chart = make_line_chart(
            long_df,
            y_title,
            present_labels,
            value_col=value_col_for_chart,
            color_col=label_col,
            color_title="Geography / series",
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
    selected_series_for_params = selected_series_label
    selected_geos_for_params = present_labels
    year_range_for_params = (yr_from, yr_to)
    inflation_adjusted_for_params = inflation_checked

# ============================================================
# TRANSPORTATION & EXPORTS VIEW
# ============================================================

    # Return footer state for URL sharing
    return {
        "selected_dataset_id": locals().get("selected_dataset_id"),
        "selected_series_for_params": locals().get("selected_series_for_params"),
        "selected_geos_for_params": locals().get("selected_geos_for_params", []),
        "year_range_for_params": locals().get("year_range_for_params"),
        "inflation_adjusted_for_params": locals().get("inflation_adjusted_for_params", False),
    }
