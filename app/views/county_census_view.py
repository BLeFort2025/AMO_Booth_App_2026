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



def render_county_census_view(params, analytics_options):
    """Render the County Level Census Stats (ON) view. Returns footer-state dict."""
    st.subheader("County Level Census Stats (Ontario only)")
    st.caption(
        "Ontario-only county / census division data from custom Census of Agriculture dataset."
    )
    dataset_options = {
        "Census of Agriculture (CEAG) – county indicators": "ceag",
        "Farm cash receipts by county & commodity (OMAFRA)": "omafra_fcr",
        "Agri-food GDP & jobs by county (OMAFRA)": "omafra_attr",
    }

    selected_dataset_label = st.sidebar.selectbox(
        "Dataset",
        list(dataset_options.keys()),
        index=0,
    )
    selected_dataset_key = dataset_options[selected_dataset_label]

    if selected_dataset_key == "ceag":
        table_cfg = get_table_metadata("ontario_county_ceag") or {
            "id": "ontario_county_ceag",
            "csv": "ontario_county_ceag.csv",
        }
        render_dataset_notes(table_cfg)

        with st.spinner("Fetching data from Statistics Canada or local dataset…"):
            df = safe_load_dataset(table_cfg)

        # Ensure YEAR exists before we drop NA on it
        df = ensure_year_column(df)

        if "YEAR" in df.columns:
            df = df.dropna(subset=["YEAR"]).copy()
        else:
            # Proceed without dropping on YEAR; some auxiliary tables may not need it.
            df = df.copy()

        if "YEAR" not in df.columns or "GEO" not in df.columns:
            st.error("Ontario county dataset must contain YEAR and GEO columns.")
            st.stop()

        df["YEAR"] = df["YEAR"].astype(int)
        df["GEO"] = df["GEO"].astype(str)

        counties = sorted(df["GEO"].unique().tolist())
        default_counties = counties[:3] if len(counties) > 3 else counties
        geos_param = _get_param(params, "geos", None)
        initial_counties = (
            geos_param.split(",") if geos_param else default_counties
        )
        initial_counties = [c for c in initial_counties if c in counties] or default_counties
        county_pick = st.sidebar.multiselect(
            "County / Census division (Ontario only)", counties, default=initial_counties
        )
        if not county_pick:
            st.info("Select at least one county.")
            st.stop()

        yrs = df[df["GEO"].isin(county_pick)]["YEAR"].dropna().astype(int)
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
            )

        f = df[(df["GEO"].isin(county_pick)) & (df["YEAR"].between(yr_from, yr_to))].copy()
        if f.empty:
            st.info("No data for selected filters.")
            st.stop()

        exclude_cols = {
            "GEO",
            "YEAR",
            "REF_DATE",
            "DGUID",
            "UOM",
            "UOM_ID",
            "SCALAR_FACTOR",
            "SCALAR_ID",
            "VECTOR",
            "COORDINATE",
            "STATUS",
            "SYMBOL",
            "TERMINATED",
            "DECIMALS",
        }
        numeric_cols = [
            c
            for c in f.columns
            if c not in exclude_cols and pd.api.types.is_numeric_dtype(f[c])
        ]
        if not numeric_cols:
            st.error("No numeric metric columns found in Ontario county dataset.")
            st.stop()

        metric_default = numeric_cols[0]
        metric_param = _get_param(params, "series", metric_default)
        if metric_param not in numeric_cols:
            metric_param = metric_default
        metric = st.sidebar.selectbox(
            "Metric", numeric_cols, index=numeric_cols.index(metric_param)
        )

        latest_year = f["YEAR"].max()
        latest_slice = f[f["YEAR"] == latest_year]
        prev_slice = f[f["YEAR"] < latest_year]

        total_latest = latest_slice[metric].sum()
        if not prev_slice.empty:
            prev_year = prev_slice["YEAR"].max()
            prev_total = prev_slice[prev_slice["YEAR"] == prev_year][metric].sum()
            change = (total_latest - prev_total) / prev_total * 100 if prev_total else 0.0
            metric_col, delta_col = st.columns([2, 1])
            with metric_col:
                st.metric(f"{metric} in {latest_year}", f"{total_latest:,.0f}")
            with delta_col:
                st.metric("Change vs prior census", f"{change:+.1f}% vs {int(prev_year)}")
        else:
            st.metric(f"{metric} in {latest_year}", f"{total_latest:,.0f}", "")
            st.caption("No earlier census year in selection for comparison.")

        st.caption(f"Ontario counties — {metric}")

        last_period = compute_last_updated_period(f)
        if last_period is not None:
            st.caption(f"Last available period in dataset: {format_last_period(last_period)}")

        chart_df = f[["YEAR", "GEO", metric]].rename(columns={metric: "VALUE"})
        present_geos = sorted(chart_df["GEO"].unique().tolist())
        y_title = metric
        inflation_note: str | None = None

        dl_name = build_download_name(
            "Ontario county CEAG", metric, yr_from, yr_to, present_geos
        )
        alt.renderers.set_embed_options(
            actions={"export": True, "source": False, "compiled": False, "editor": False},
            downloadFileName=dl_name,
        )

        chart = make_line_chart(chart_df, y_title, present_geos, analytics_options=analytics_options)
        chart_tab, data_tab = st.tabs(["Chart", "Data"])

        with chart_tab:
            st.altair_chart(chart, width="stretch")

            file_stem_parts = [table_cfg["id"].replace(" ", "_")]
            selected_series_label = metric
            if selected_series_label:
                file_stem_parts.append(str(selected_series_label).replace(" ", "_"))
            if county_pick:
                file_stem_parts.append("_".join(g.replace(" ", "_") for g in county_pick))
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

            if inflation_note:
                st.caption(inflation_note)

        with data_tab:
            if not chart_df.empty:
                st.dataframe(chart_df.head(500))
            else:
                st.info("No data available for the selected filters.")

        if not f.empty:
            csv_buffer = io.StringIO()
            f.to_csv(csv_buffer, index=False)
            file_name = "ontario_county_ceag_" + "_".join(
                filter(None, [safe_slug(metric), safe_slug("-".join(county_pick))])
            )
            file_name = (file_name or "ontario_county_ceag").strip("_") + ".csv"
            st.download_button(
                label="Download data as CSV",
                data=csv_buffer.getvalue(),
                file_name=file_name,
                mime="text/csv",
                help="Download the data used in this chart for further analysis.",
            )

        st.caption("Source: Custom Ontario county Census of Agriculture dataset")

        selected_dataset_id = table_cfg.get("id") or "ontario_county_ceag"
        selected_series_for_params = metric
        selected_geos_for_params = county_pick
        year_range_for_params = (yr_from, yr_to)

    elif selected_dataset_key == "omafra_fcr":
        try:
            df = load_omafra_fcr_by_county()
        except Exception as e:
            st.error("Could not load OMAFRA farm cash receipts dataset.")
            st.caption(str(e))
            st.stop()

        df = df.dropna(subset=["YEAR", "GEO", "VALUE"]).copy()
        df["YEAR"] = df["YEAR"].astype(int)
        df["GEO"] = df["GEO"].astype(str)

        counties = sorted(df["GEO"].unique().tolist())
        if not counties:
            st.error("No geography values found in OMAFRA farm cash receipts dataset.")
            st.stop()

        provincial_geos = [
            g for g in counties
            if g.strip().lower() in {"ontario", "ontario total", "province of ontario"}
        ]
        if provincial_geos:
            default_counties = provincial_geos
        else:
            default_counties = counties[:3] if len(counties) > 3 else counties

        geos_param = _get_param(params, "geos", None)
        initial_counties = (
            geos_param.split(",") if geos_param else default_counties
        )
        initial_counties = [c for c in initial_counties if c in counties] or default_counties

        selected_geos = st.sidebar.multiselect(
            "County / region (OMAFRA)",
            counties,
            default=initial_counties,
        )
        if not selected_geos:
            st.info("Select at least one county / region.")
            st.stop()

        year_series = df[df["GEO"].isin(selected_geos)]["YEAR"].dropna().astype(int)
        if year_series.empty:
            st.info("No data for selected filters.")
            st.stop()

        yr_min, yr_max = int(year_series.min()), int(year_series.max())

        if yr_min == yr_max:
            yr_from = yr_to = yr_min
        else:
            yr_from, yr_to = st.sidebar.slider(
                "Year range",
                min_value=yr_min,
                max_value=yr_max,
                value=(yr_min, yr_max),
                step=1,
            )

        filtered = df[
            (df["GEO"].isin(selected_geos))
            & (df["YEAR"] >= yr_from)
            & (df["YEAR"] <= yr_to)
        ].copy()

        if filtered.empty:
            st.info("No data for the selected counties and year range.")
            st.stop()

        commodities = sorted(filtered["COMMODITY"].dropna().unique().tolist())
        if not commodities:
            st.error("No commodity information found in OMAFRA farm cash receipts dataset.")
            st.stop()

        default_commodity = next(
            (c for c in commodities if str(c).lower().startswith("total farm cash receipts")),
            commodities[0],
        )

        selected_commodity = st.sidebar.selectbox(
            "Commodity",
            commodities,
            index=commodities.index(default_commodity),
        )

        filtered = filtered[filtered["COMMODITY"] == selected_commodity].copy()
        if filtered.empty:
            st.info("No data after filtering for the selected commodity.")
            st.stop()

        # Build base chart data
        chart_base = filtered[["YEAR", "GEO", "VALUE"]].copy()
        chart_base["YEAR"] = chart_base["YEAR"].astype(int)

        # Inflation adjustment (CPI, Canada)
        inflation_label = "Adjust for inflation (CPI, Canada)"
        inflation_help = (
            "Uses CPI all-items, Canada, annual average (StatCan table 18-10-0005-01) "
            "to express values in constant-dollar terms, using the last year in the series as the base year."
        )
        inflation_param = _get_param(params, "inflation", "nominal")
        inflation_checked = st.sidebar.checkbox(
            inflation_label,
            value=inflation_param == "real",
            help=inflation_help,
            key="omafra_fcr_inflation",
        )

        value_col_for_chart = "VALUE"
        inflation_applied = False
        base_year = None
        inflation_note = None

        try:
            cpi = load_cpi_deflators(
                table_config=TABLE_CONFIG,
                _load_table_fn=load_table,
            )
        except Exception:
            cpi = None

        series_years_full = pd.to_numeric(chart_base["YEAR"], errors="coerce")
        series_years = series_years_full.dropna().astype(int)
        if not series_years.empty:
            base_year = int(series_years.max())

        chart_with_cpi = chart_base.copy()
        if cpi is not None and base_year is not None and base_year in cpi["YEAR"].values:
            base_cpi = float(cpi.loc[cpi["YEAR"] == base_year, "cpi"].iloc[0])
            cpi = cpi.assign(deflator=base_cpi / cpi["cpi"])
            cpi_for_merge = cpi.rename(columns={"YEAR": "CPI_YEAR"})
            cpi_for_merge = (
                cpi_for_merge.groupby("CPI_YEAR", as_index=False)[["deflator"]]
                .mean()
            )
            chart_with_cpi = chart_with_cpi.merge(
                cpi_for_merge[["CPI_YEAR", "deflator"]],
                left_on=series_years_full.astype("Int64"),
                right_on="CPI_YEAR",
                how="left",
            ).drop(columns=["CPI_YEAR"], errors="ignore")

        if (
            inflation_checked
            and "deflator" in chart_with_cpi.columns
            and chart_with_cpi["deflator"].notna().any()
        ):
            chart_with_cpi["VALUE_REAL"] = chart_with_cpi["VALUE"] * chart_with_cpi["deflator"]
            value_col_for_chart = "VALUE_REAL"
            inflation_applied = True

        # Final chart data: YEAR, GEO, VALUE (nominal or real)
        chart_data = chart_with_cpi[["YEAR", "GEO"]].copy()
        chart_data["VALUE"] = chart_with_cpi[value_col_for_chart].values

        if inflation_applied and base_year is not None:
            inflation_note = (
                "Values adjusted for inflation using CPI all-items, Canada, annual average "
                "(StatCan table 18-10-0005-01); "
                f"constant {base_year} dollars."
            )

        latest_year = int(chart_data["YEAR"].max())
        latest_slice = chart_data[chart_data["YEAR"] == latest_year]
        prev_slice = chart_data[chart_data["YEAR"] < latest_year]

        latest_total = float(latest_slice["VALUE"].sum())
        col1, col2 = st.columns(2)

        if not prev_slice.empty:
            prev_year = int(prev_slice["YEAR"].max())
            prev_total = float(
                prev_slice[prev_slice["YEAR"] == prev_year]["VALUE"].sum()
            )
            if prev_total:
                pct_change = 100.0 * (latest_total - prev_total) / prev_total
            else:
                pct_change = 0.0

            metric_label = f"{selected_commodity} receipts in {latest_year}"
            if inflation_applied and base_year is not None:
                metric_label += f" (constant {base_year} dollars)"

            col1.metric(
                metric_label,
                f"{latest_total:,.0f}",
            )
            col2.metric(
                "Change vs prior year",
                f"{pct_change:+.1f}%",
                help=f"Vs {prev_year}",
            )
        else:
            metric_label = f"{selected_commodity} receipts in {latest_year}"
            if inflation_applied and base_year is not None:
                metric_label += f" (constant {base_year} dollars)"
            col1.metric(
                metric_label,
                f"{latest_total:,.0f}",
            )
            col2.caption("No earlier year in selection for comparison.")

        y_title = "Farm cash receipts (dollars)"
        if inflation_applied and base_year is not None:
            y_title = f"Farm cash receipts (constant {base_year} dollars)"

        chart = make_line_chart(
            chart_data,
            y_title,
            sorted(chart_data["GEO"].unique()),
            analytics_options=analytics_options,
        )

        chart_tab, data_tab = st.tabs(["Chart", "Data"])

        with chart_tab:
            st.altair_chart(chart, use_container_width=True)

            file_stem_parts = ["omafra_fcr_by_county"]
            if selected_commodity:
                file_stem_parts.append(safe_slug(selected_commodity))
            if selected_geos:
                file_stem_parts.append("_".join(g.replace(" ", "_") for g in selected_geos))
            file_stem = "_".join(filter(None, file_stem_parts))

            png_bytes = get_chart_png_bytes(chart, file_stem=file_stem)

            if png_bytes is not None:
                st.download_button(
                    label="Download chart as PNG",
                    data=png_bytes,
                    file_name=f"{file_stem}.png",
                    mime="image/png",
                    key="download_chart_svg_omafra_fcr",
                )
            else:
                st.caption("Chart image download not available in this environment.")

            if inflation_note:
                st.caption(inflation_note)

        with data_tab:
            st.dataframe(
                chart_data.sort_values(["GEO", "YEAR"]).reset_index(drop=True)
            )
            csv_buffer = io.StringIO()
            chart_data.to_csv(csv_buffer, index=False)
            st.download_button(
                label="Download data as CSV",
                data=csv_buffer.getvalue(),
                file_name=f"omafra_fcr_by_county_{yr_from}_{yr_to}.csv",
                mime="text/csv",
                help="Download the data behind this chart.",
            )

        st.caption(
            "Source: Ontario Ministry of Agriculture, Food and Agribusiness (OMAFRA), "
            "Ontario farm cash receipts by county and crop (Ontario Data Catalogue)."
        )

        selected_dataset_id = "omafra_fcr"
        selected_series_for_params = selected_commodity
        selected_geos_for_params = selected_geos
        year_range_for_params = (yr_from, yr_to)
        inflation_adjusted_for_params = inflation_checked

    elif selected_dataset_key == "omafra_attr":
        try:
            df = load_omafra_attribution_county()
        except Exception as e:
            st.error("Could not load OMAFRA agri-food GDP & employment dataset.")
            st.caption(str(e))
            st.stop()

        df = df.dropna(subset=["YEAR", "GEO", "VALUE"]).copy()
        df["YEAR"] = df["YEAR"].astype(int)
        df["GEO"] = df["GEO"].astype(str)

        counties = sorted(df["GEO"].unique().tolist())
        if not counties:
            st.error("No geography values found in OMAFRA agri-food dataset.")
            st.stop()

        provincial_geos = [
            g for g in counties
            if g.strip().lower() in {"ontario", "ontario total", "province of ontario"}
        ]
        if provincial_geos:
            default_counties = provincial_geos
        else:
            default_counties = counties[:3] if len(counties) > 3 else counties
        geos_param = _get_param(params, "geos", None)
        initial_counties = (
            geos_param.split(",") if geos_param else default_counties
        )
        initial_counties = [c for c in initial_counties if c in counties] or default_counties

        selected_geos = st.sidebar.multiselect(
            "County / region (OMAFRA)",
            counties,
            default=initial_counties,
        )
        if not selected_geos:
            st.info("Select at least one county / region.")
            st.stop()

        year_series = df[df["GEO"].isin(selected_geos)]["YEAR"].dropna().astype(int)
        if year_series.empty:
            st.info("No data for selected filters.")
            st.stop()

        yr_min, yr_max = int(year_series.min()), int(year_series.max())
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

        measure_labels = {
            "GDP_chained2017_millions": "GDP (chained 2017$, millions)",
            "Employment_thousands": "Employment (thousands of jobs)",
        }

        measure_options = list(measure_labels.values())
        default_measure_code = "GDP_chained2017_millions"
        default_measure_label = measure_labels[default_measure_code]

        selected_measure_label = st.sidebar.selectbox(
            "Measure",
            measure_options,
            index=measure_options.index(default_measure_label),
        )

        reverse_measure_map = {v: k for k, v in measure_labels.items()}
        selected_measure_code = reverse_measure_map[selected_measure_label]

        filtered = df[
            (df["GEO"].isin(selected_geos))
            & (df["YEAR"] >= yr_from)
            & (df["YEAR"] <= yr_to)
            & (df["MEASURE"] == selected_measure_code)
        ].copy()

        if filtered.empty:
            st.info("No data for the selected counties, measure, and year range.")
            st.stop()

        latest_year = int(filtered["YEAR"].max())
        latest_slice = filtered[filtered["YEAR"] == latest_year]
        prev_slice = filtered[filtered["YEAR"] < latest_year]

        latest_total = float(latest_slice["VALUE"].sum())
        col1, col2 = st.columns(2)

        measure_label = (
            "millions of chained 2017 dollars"
            if selected_measure_code == "GDP_chained2017_millions"
            else "thousands of jobs"
        )

        if not prev_slice.empty:
            prev_year = int(prev_slice["YEAR"].max())
            prev_total = float(
                prev_slice[prev_slice["YEAR"] == prev_year]["VALUE"].sum()
            )
            if prev_total:
                pct_change = 100.0 * (latest_total - prev_total) / prev_total
            else:
                pct_change = 0.0

            col1.metric(
                f"{selected_measure_label} in {latest_year}",
                f"{latest_total:,.1f}",
            )
            col2.metric(
                "Change vs prior year",
                f"{pct_change:+.1f}%",
                help=f"Vs {prev_year}",
            )
        else:
            col1.metric(
                f"{selected_measure_label} in {latest_year}",
                f"{latest_total:,.1f}",
            )
            col2.caption("No earlier year in selection for comparison.")

        chart_df = filtered[["YEAR", "GEO", "VALUE"]].copy()
        y_title = (
            "GDP (chained 2017$, millions)"
            if selected_measure_code == "GDP_chained2017_millions"
            else "Employment (thousands of jobs)"
        )

        chart = make_line_chart(
            chart_df,
            y_title,
            sorted(chart_df["GEO"].unique()),
            analytics_options=analytics_options,
        )
        chart_tab, data_tab = st.tabs(["Chart", "Data"])

        with chart_tab:
            st.altair_chart(chart, use_container_width=True)

            file_stem_parts = ["omafra_agri_food_value_chain"]
            if selected_measure_code:
                file_stem_parts.append(safe_slug(selected_measure_code))
            if selected_geos:
                file_stem_parts.append("_".join(g.replace(" ", "_") for g in selected_geos))
            file_stem = "_".join(filter(None, file_stem_parts))

            png_bytes = get_chart_png_bytes(chart, file_stem=file_stem)

            if png_bytes is not None:
                st.download_button(
                    label="Download chart as PNG",
                    data=png_bytes,
                    file_name=f"{file_stem}.png",
                    mime="image/png",
                    key="download_chart_svg_omafra_attr",
                )
            else:
                st.caption("Chart image download not available in this environment.")

        with data_tab:
            st.dataframe(
                filtered.sort_values(["GEO", "YEAR"]).reset_index(drop=True)
            )
            csv_buffer = io.StringIO()
            filtered.to_csv(csv_buffer, index=False)
            st.download_button(
                label="Download data as CSV",
                data=csv_buffer.getvalue(),
                file_name=f"omafra_agri_food_value_chain_{yr_from}_{yr_to}.csv",
                mime="text/csv",
            )

        st.caption(
            "Source: Ontario Ministry of Agriculture, Food and Agribusiness (OMAFRA), "
            "Ontario agri-food value chain by county (Ontario Data Catalogue)."
        )

        selected_dataset_id = "omafra_attr"
        selected_series_for_params = selected_measure_code
        selected_geos_for_params = selected_geos
        year_range_for_params = (yr_from, yr_to)

# ============================================================
# OMAFRA COMMODITY PRICES VIEW
# ============================================================

    # Return footer state for URL sharing
    return {
        "selected_dataset_id": locals().get("selected_dataset_id"),
        "selected_series_for_params": locals().get("selected_series_for_params"),
        "selected_geos_for_params": locals().get("selected_geos_for_params", []),
        "year_range_for_params": locals().get("year_range_for_params"),
        "inflation_adjusted_for_params": locals().get("inflation_adjusted_for_params", False),
    }
