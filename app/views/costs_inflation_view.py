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



def render_costs_inflation_view(params, analytics_options):
    """Render the Costs & Inflation view. Returns footer-state dict."""
    st.subheader("Costs & Inflation (Price Indices & CPI)")

    dataset_options = {
        # Farm input & machinery price indices
        "Farm input price index (FIPI, quarterly)": "18-10-0258-01.csv",
        "Farm product prices – crops & livestock (monthly)": "32-10-0077-01.csv",
        "Farm product price index (FPPI, monthly)": "32-10-0098-01.csv",
        "Machinery & equipment price index (MEPI, quarterly)": "18-10-0270-01.csv",

        # Consumer fuel prices
        "Gasoline CPI (retail price index)": "18-10-0001-01.csv",
        "Diesel fuel CPI (retail price index)": "18-10-0002-01.csv",

        # Food CPI relative importance
        "Food CPI – relative importance": "18-10-0004-01.csv",

        # Freight service price indices
        "For-hire motor carrier freight services price index": "18-10-0281-01.csv",
        "Freight Rail Services Price Index": "18-10-0212-01.csv",

        # Food CPI (downstream price signal)
        "Food CPI (index – 2002=100)": "18-10-0004-03.csv",

        # Farm input price index (percentage change)
        "Farm input price index – % change": "18-10-0258-02.csv",

        # Food manufacturing
        "Manufacturing sales by subsector (food mfg)": "16-10-0048-01.csv",
    }

    dataset_labels = list(dataset_options.keys())
    default_dataset_label = dataset_labels[0]
    dataset_id_lookup = {
        label: dataset_options[label].replace(".csv", "") for label in dataset_labels
    }
    dataset_from_url = _get_param(params, "dataset", dataset_id_lookup[default_dataset_label])
    if dataset_from_url.endswith(".csv"):
        dataset_from_url = dataset_from_url.replace(".csv", "")
    initial_dataset_label = next(
        (label for label, ds_id in dataset_id_lookup.items() if ds_id == dataset_from_url),
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

    # For MEPI, keep only "Total domestic and imported" and clarify Canada-only
    if table_id == "18-10-0270-01":
        if "Machinery and equipment, domestic and imported" in df.columns:
            df = df[
                df["Machinery and equipment, domestic and imported"]
                == "Total domestic and imported"
            ].copy()
        st.info(
            "MEPI is available at the **Canada** level only "
            "in Statistics Canada Table 18-10-0270-01."
        )

    # Clean YEAR + VALUE and drop rows without YEAR
    df = ensure_year_column(df)

    if "YEAR" in df.columns:
        df = df.dropna(subset=["YEAR"]).copy()
    else:
        # Proceed without dropping on YEAR; some auxiliary tables may not need it.
        df = df.copy()

    df["YEAR"] = df["YEAR"].astype(int)
    if "VALUE" in df.columns:
        df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")

    # SERIES DIMENSION
    dim_col = find_series_column(table_id, df)

    ignored_cols = {
        "REF_DATE",
        "YEAR",
        "GEO",
        "VALUE",
        "UOM",
        "Unit of measure",
    }.union(STATCAN_METADATA_COLUMNS)

    extra_dim_cols: list[str] = []
    for col in df.columns:
        if col in ignored_cols or col == dim_col:
            continue
        if df[col].dropna().nunique() <= 1:
            continue
        if df[col].dtype == object or any(
            kw in col.lower()
            for kw in [
                "index",
                "product",
                "group",
                "component",
                "type",
                "class",
                "category",
                "series",
                "estimate",
                "commodity",
                "input",
            ]
        ):
            extra_dim_cols.append(col)

    if extra_dim_cols:
        with st.sidebar.expander("Additional breakdowns"):
            for col in extra_dim_cols:
                options = sorted(df[col].dropna().unique().tolist(), key=lambda x: str(x))
                all_label = f"All {col.lower()}"
                selected = st.selectbox(
                    col, [all_label] + options, key=f"{table_id}_{col}"
                )
                if selected != all_label:
                    df = df[df[col] == selected].copy()

    # Compare mode: geographies vs series
    compare_mode = st.sidebar.radio(
        "Compare by",
        ["Geographies", "Series"],
        index=0,
        help="Geographies: one series, multiple geographies. Series: one geography, multiple series.",
    )

    # SERIES SELECTOR(S)
    selected_series: str | None = None
    selected_series_list: list[str] | None = None

    if table_id == "32-10-0213-01" and dataset_label == "Farm family income by source":
        income_col = find_income_source_column(df)
        if income_col:
            dim_col = income_col

    selected_series_label: str | None = None

    if dim_col:
        all_series = sorted(df[dim_col].dropna().unique().tolist())
        series_filter = st.sidebar.text_input("Filter series (optional)", "").strip().lower()
        series_options = (
            [s for s in all_series if series_filter in str(s).lower()]
            if series_filter
            else all_series
        )
        if not series_options:
            st.info("No series match your filter.")
            st.stop()

        series_param = _get_param(params, "series", None)
        url_series = [
            s for s in (series_param.split(",") if series_param else []) if s in series_options
        ]

        if compare_mode == "Geographies":
            dataset_id_for_defaults = table_cfg.get("id", table_id)
            default_series = get_default_series(dataset_id_for_defaults, series_options)
            pinned_series = [s for s in series_options if str(s).lower().startswith("total") or str(s).lower() in ("food", "all-items")]

            with st.sidebar:
                selected_series_list = multiselect_with_pins(
                    "Series",
                    series_options,
                    key=f"{table_id}_series",
                    pinned_options=pinned_series,
                    url_values=url_series,
                    default_values=default_series,
                    help="Select one or more series.",
                )
            if not selected_series_list:
                st.info("Select at least one series.")
                st.stop()
            selected_series = selected_series_list[0]
            selected_series_label = selected_series
            df = df[df[dim_col].isin(selected_series_list)].copy()
        else:
            # Series comparison: one geography, multiple series
            default_series_list = get_default_series(
                table_cfg.get("id", table_id), series_options
            )
            if series_param:
                parsed = [s.strip() for s in series_param.split(",") if s.strip()]
                parsed = [s for s in parsed if s in series_options]
                if parsed:
                    default_series_list = parsed

            pinned_series = [s for s in series_options if str(s).lower().startswith("total") or str(s).lower() in ("food", "all-items")]

            selected_series_list = multiselect_with_pins(
                "Series (multiple allowed)",
                series_options,
                key=f"{table_id}_series",
                pinned_options=pinned_series,
                url_values=url_series,
                default_values=default_series_list,
                help="Select one or more series.",
            )
            if not selected_series_list:
                st.info("Select at least one series.")
                st.stop()
            selected_series_label = ", ".join(map(str, selected_series_list))
            df = df[df[dim_col].isin(selected_series_list)].copy()
    else:
        if compare_mode == "Series":
            st.info("This dataset has no separate series dimension; using geography comparison instead.")
            compare_mode = "Geographies"

    geo_col = "GEO"

    # GEOGRAPHY SELECTORS
    if geo_col not in df.columns or "VALUE" not in df.columns:
        st.error("Expected columns 'GEO' and 'VALUE' not found in this dataset.")
        st.stop()

    geos_all = sorted(df[geo_col].dropna().unique().tolist())

    if compare_mode == "Geographies":
        if table_id in {"18-10-0270-01", "18-10-0281-01", "18-10-0212-01"} and geos_all == ["Canada"]:
            pick = ["Canada"]
        else:
            geos_param = _get_param(params, "geos", None)
            url_geos = [g for g in (geos_param.split(",") if geos_param else []) if g in geos_all]
            default_geos = get_default_geos(geos_all)
            if not default_geos and geos_all:
                default_geos = [geos_all[0]]
            pinned_geos = [g for g in geos_all if g in ["Canada", "Ontario"]]
            with st.sidebar:
                pick = multiselect_with_pins(
                    label="Geography",
                    options=geos_all,
                    key=f"{table_id}_geos",
                    pinned_options=pinned_geos,
                    url_values=url_geos,
                    default_values=default_geos,
                    help="Select one or more geographies.",
                )
        geo_sel = None
    else:
        geos_param = _get_param(params, "geos", None)
        url_geos = [g for g in (geos_param.split(",") if geos_param else []) if g in geos_all]
        default_geos = get_default_geos(geos_all)
        if not default_geos and geos_all:
            default_geos = [geos_all[0]]
        pinned_geos = [g for g in geos_all if g in ["Canada", "Ontario"]]
        with st.sidebar:
            selected_geos = multiselect_with_pins(
                label="Geography",
                options=geos_all,
                key=f"{table_id}_geos",
                pinned_options=pinned_geos,
                url_values=url_geos,
                default_values=default_geos,
                help="Select one geography for series comparison.",
        )
        if not selected_geos:
            st.info("Select at least one geography to display the data.")
            st.stop()
        geo_sel = selected_geos[0]
        pick = [geo_sel]

    if not pick:
        st.info("Select at least one geography to display the data.")
        st.stop()

    # YEAR RANGE
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
        )

    if compare_mode == "Geographies":
        f = df[(df["GEO"].isin(pick)) & (df["YEAR"].between(yr_from, yr_to))].copy()
    else:
        f = df[(df["GEO"] == geo_sel) & (df["YEAR"].between(yr_from, yr_to))].copy()

    if f.empty:
        st.info("No data for selected filters.")
        st.stop()

    # Build DATE column for quarterly/monthly time series
    if "REF_DATE" in f.columns:
        if any("Q" in str(x) for x in f["REF_DATE"].unique()):
            def quarter_to_date(qstr: str) -> str:
                text = str(qstr)
                year = int(text[:4])
                q = text[-1]
                qm = {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}.get(q, "12-31")
                return f"{year}-{qm}"

            f["DATE"] = pd.to_datetime(
                f["REF_DATE"].astype(str).apply(quarter_to_date), errors="coerce"
            )
        else:
            f["DATE"] = pd.to_datetime(
                f["REF_DATE"].astype(str).str.slice(0, 7) + "-01", errors="coerce"
            )

    inflation_note: str | None = None
    base_year: int | None = None

    date_col = "DATE" if "DATE" in f.columns and f["DATE"].notna().any() else "YEAR"
    chart_df = f.copy()

    unit_lbl = get_unit_label(chart_df)
    is_dollar_series = False
    for col in ["UOM", "Unit of measure", "UNIT"]:
        if col in chart_df.columns:
            if chart_df[col].astype(str).str.contains("dollar|\$", case=False, regex=True).any():
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

    try:
        cpi = (
            load_cpi_deflators(table_config=TABLE_CONFIG, _load_table_fn=load_table)
            if is_dollar_series
            else None
        )
    except Exception:
        cpi = None

    if date_col == "DATE" and pd.api.types.is_datetime64_any_dtype(chart_df[date_col]):
        year_key = chart_df[date_col].dt.year
    else:
        year_key = pd.to_numeric(chart_df[date_col], errors="coerce")

    year_key_int = pd.to_numeric(year_key, errors="coerce").astype("Int64")
    series_years = year_key_int.dropna().astype(int)
    if series_years.empty:
        base_year = None
    else:
        base_year = int(series_years.max())

    if cpi is not None and base_year is not None and base_year in cpi["YEAR"].values:
        base_cpi = float(cpi.loc[cpi["YEAR"] == base_year, "cpi"].iloc[0])
        cpi = cpi.assign(deflator=base_cpi / cpi["cpi"])
        cpi_for_merge = cpi.rename(columns={"YEAR": "CPI_YEAR"})
        cpi_for_merge = (
            cpi_for_merge.groupby("CPI_YEAR", as_index=False)[["deflator"]]
            .mean()
        )
        chart_df = chart_df.merge(
            cpi_for_merge[["CPI_YEAR", "deflator"]],
            left_on=year_key_int,
            right_on="CPI_YEAR",
            how="left",
        ).drop(columns=["CPI_YEAR"], errors="ignore")

    value_col_for_chart = "VALUE"
    inflation_applied = False
    if (
        inflation_checked
        and "deflator" in chart_df.columns
        and chart_df["deflator"].notna().any()
    ):
        chart_df["VALUE_REAL"] = chart_df["VALUE"] * chart_df["deflator"]
        value_col_for_chart = "VALUE_REAL"
        inflation_applied = True

    inflation_suffix = (
        f" (constant {base_year} dollars)" if inflation_applied and base_year is not None else ""
    )

    if inflation_applied and base_year is not None:
        inflation_note = (
            "Values adjusted for inflation using CPI all-items, Canada, annual average "
            "(StatCan table 18-10-0005-01); "
            f"constant {base_year} dollars."
        )

    group_cols: list[str] = []
    if "REF_DATE" in chart_df.columns:
        group_cols.append("REF_DATE")
    if date_col == "DATE" and "DATE" in chart_df.columns:
        group_cols.append("DATE")
    elif "YEAR" in chart_df.columns:
        group_cols.append("YEAR")
    if "GEO" in chart_df.columns:
        group_cols.append("GEO")
    if dim_col:
        group_cols.append(dim_col)

    if group_cols:
        chart_df = chart_df.groupby(group_cols, as_index=False)[value_col_for_chart].sum()

    f = chart_df

    # Auto-rebase index series to the first selected period
    if unit_lbl and not is_dollar_series:
        lowered_unit = unit_lbl.lower()
        if "index" in lowered_unit or "=" in lowered_unit:
            time_c = "DATE" if ("DATE" in f.columns and not f["DATE"].isna().all()) else "YEAR"
            rebase_group_cols = [c for c in ["GEO", dim_col] if c and c in f.columns]
            
            sorted_f = f.sort_values(time_c)
            if not sorted_f.empty:
                if rebase_group_cols:
                    base_values = sorted_f.groupby(rebase_group_cols, as_index=False).first()
                    base_values = base_values[rebase_group_cols + [value_col_for_chart]].rename(columns={value_col_for_chart: "BASE_VALUE"})
                    f = f.merge(base_values, on=rebase_group_cols, how="left")
                else:
                    f["BASE_VALUE"] = sorted_f[value_col_for_chart].iloc[0]
                    
                mask = (f["BASE_VALUE"].notna()) & (f["BASE_VALUE"] != 0)
                f.loc[mask, value_col_for_chart] = (f.loc[mask, value_col_for_chart] / f.loc[mask, "BASE_VALUE"]) * 100.0
                f = f.drop(columns=["BASE_VALUE"])
                
                base_yr_display = int(sorted_f["YEAR"].iloc[0]) if "YEAR" in sorted_f.columns else yr_from
                unit_lbl = f"Index ({base_yr_display}=100)"
    label_col = "GEO" if compare_mode == "Geographies" else dim_col or "GEO"

    time_col_for_analytics = "DATE" if date_col == "DATE" else "YEAR"
    analytics_level = compute_time_series_analytics(
        f, value_col=value_col_for_chart, time_col=time_col_for_analytics
    )
    analytics_yoy = compute_yoy_analytics(
        f, value_col=value_col_for_chart, time_col=time_col_for_analytics
    )

    # KPI construction
    kpi_rows: list[tuple[str, object, float, float | None]] = []
    metric_title_suffix = ""
    if compare_mode == "Geographies":
        if "DATE" in f.columns and not f["DATE"].isna().all():
            f2 = f.dropna(subset=["DATE", value_col_for_chart]).copy()
            f2 = f2.sort_values(["GEO", "DATE"])
            f2["PREV_VALUE"] = f2.groupby("GEO")[value_col_for_chart].shift(1)
            latest_date = f2["DATE"].max()
            last_rows = f2[f2["DATE"] == latest_date].copy()
            for _, row in last_rows.iterrows():
                geo = row["GEO"]
                val = row[value_col_for_chart]
                prev = row["PREV_VALUE"]
                change = (val - prev) / prev * 100 if pd.notnull(prev) and prev else None
                kpi_rows.append((geo, latest_date.date(), float(val), change))
            metric_title_suffix = f"on {latest_date.date()}"
        else:
            f2 = f.sort_values(["GEO", "YEAR"])
            f2["PREV_VALUE"] = f2.groupby("GEO")[value_col_for_chart].shift(1)
            latest_year = int(f2["YEAR"].max())
            last_rows = f2[f2["YEAR"] == latest_year].copy()
            for _, row in last_rows.iterrows():
                geo = row["GEO"]
                val = row[value_col_for_chart]
                prev = row["PREV_VALUE"]
                change = (val - prev) / prev * 100 if pd.notnull(prev) and prev else None
                kpi_rows.append((geo, latest_year, float(val), change))
            metric_title_suffix = f"in {latest_year}"
    else:
        if dim_col is None:
            st.error("Series comparison requires a series dimension.")
            st.stop()

        if "DATE" in f.columns and not f["DATE"].isna().all():
            f2 = f.dropna(subset=["DATE", value_col_for_chart]).copy()
            f2 = f2.sort_values([dim_col, "DATE"])
            f2["PREV_VALUE"] = f2.groupby(dim_col)[value_col_for_chart].shift(1)
            latest_date = f2["DATE"].max()
            last_rows = f2[f2["DATE"] == latest_date].copy()
            for _, row in last_rows.iterrows():
                s_name = row[dim_col]
                val = row[value_col_for_chart]
                prev = row["PREV_VALUE"]
                change = (val - prev) / prev * 100 if pd.notnull(prev) and prev else None
                kpi_rows.append((str(s_name), latest_date.date(), float(val), change))
            metric_title_suffix = f"on {latest_date.date()}"
        else:
            f2 = f.sort_values([dim_col, "YEAR"])
            f2["PREV_VALUE"] = f2.groupby(dim_col)[value_col_for_chart].shift(1)
            latest_year = int(f2["YEAR"].max())
            last_rows = f2[f2["YEAR"] == latest_year].copy()
            for _, row in last_rows.iterrows():
                s_name = row[dim_col]
                val = row[value_col_for_chart]
                prev = row["PREV_VALUE"]
                change = (val - prev) / prev * 100 if pd.notnull(prev) and prev else None
                kpi_rows.append((str(s_name), latest_year, float(val), change))
            metric_title_suffix = f"in {latest_year}"

    if metric_title_suffix and inflation_suffix:
        metric_title_suffix = f"{metric_title_suffix}{inflation_suffix}"

    if kpi_rows:
        n = min(len(kpi_rows), 6)
        cols = st.columns(n)
        for i, (label_item, period, val, change) in enumerate(kpi_rows[:n]):
            with cols[i]:
                label = f"{dataset_label} — {label_item} {metric_title_suffix}"
                delta_txt = (
                    f"{change:+.1f}% vs previous period" if change is not None else ""
                )
                st.metric(label, f"{val:,.1f}", delta_txt)

    if compare_mode == "Geographies":
        dataset_title_for_summary = (
            f"{dataset_label} — {selected_series_label}"
            if selected_series_label
            else dataset_label
        )
    else:
        dataset_title_for_summary = f"{dataset_label} — {geo_sel}" if geo_sel else dataset_label

    if date_col == "DATE" and "DATE" in f.columns and pd.api.types.is_datetime64_any_dtype(f["DATE"]):
        last_year = int(f["DATE"].dt.year.max())
    else:
        last_year = yr_to

    narrative = build_narrative_summary(
        dataset_title=dataset_title_for_summary,
        analytics_level=analytics_level,
        analytics_yoy=analytics_yoy,
        analytics_options=analytics_options,
        last_year=last_year,
        unit_label=unit_lbl,
        df=f,
        label_col=label_col,
        value_col=value_col_for_chart,
    )

    if narrative:
        st.subheader("Summary")
        st.markdown(narrative)

    last_period = compute_last_updated_period(f)
    if last_period is not None:
        st.caption(f"Last available period in dataset: {format_last_period(last_period)}")

    unit_lbl = get_unit_label(f)

    if inflation_applied and base_year is not None and unit_lbl and (
        "dollar" in unit_lbl.lower() or "$" in unit_lbl
    ):
        y_title_base = f"{dataset_label} — constant {base_year} dollars"
    else:
        y_title_base = f"{dataset_label}{(' (' + unit_lbl + ')') if unit_lbl else ''}"

    if compare_mode == "Geographies":
        if "DATE" in f.columns and not f["DATE"].isna().all():
            long_df = f[["DATE", "GEO", value_col_for_chart]].copy()
            present_geos = sorted(long_df["GEO"].unique().tolist())
            y_title = y_title_base

            dl_series_label = selected_series
            dl_name = build_download_name(
                dataset_label, dl_series_label, yr_from, yr_to, present_geos
            )
            alt.renderers.set_embed_options(
                actions={"export": True, "source": False, "compiled": False, "editor": False},
                downloadFileName=dl_name,
            )

            chart = (
                alt.Chart(long_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("DATE:T", title="Date"),
                    y=alt.Y(
                        f"{value_col_for_chart}:Q",
                        title=y_title,
                        axis=alt.Axis(format="~s"),
                    ),
                    color=alt.Color(
                        "GEO:N",
                        title="Geography",
                        scale=altair_colour_scale(present_geos),
                    ),
                    tooltip=[
                        alt.Tooltip("DATE:T", title="Date"),
                        alt.Tooltip("GEO:N", title="Geography"),
                        alt.Tooltip(f"{value_col_for_chart}:Q", title="Value", format=","),
                    ],
                )
                .properties(height=420)
                .interactive()
            )
        else:
            long_df = f[["YEAR", "GEO", value_col_for_chart]].copy()
            present_geos = sorted(long_df["GEO"].unique().tolist())
            y_title = y_title_base

            dl_series_label = selected_series
            dl_name = build_download_name(
                dataset_label, dl_series_label, yr_from, yr_to, present_geos
            )
            alt.renderers.set_embed_options(
                actions={"export": True, "source": False, "compiled": False, "editor": False},
                downloadFileName=dl_name,
            )

            chart = make_line_chart(
                long_df,
                y_title,
                present_geos,
                value_col=value_col_for_chart,
                analytics_options=analytics_options,
            )
    else:
        if dim_col is None:
            st.error("Series comparison requires a series dimension.")
            st.stop()

        if "DATE" in f.columns and not f["DATE"].isna().all():
            long_df = f[["DATE", dim_col, value_col_for_chart]].copy()
            present_geos = [geo_sel] if geo_sel else []
            y_title = y_title_base

            if selected_series_list:
                if len(selected_series_list) == 1:
                    dl_series_label = selected_series_list[0]
                else:
                    dl_series_label = f"{len(selected_series_list)} series"
            else:
                dl_series_label = None

            dl_name = build_download_name(
                dataset_label, dl_series_label, yr_from, yr_to, present_geos
            )
            alt.renderers.set_embed_options(
                actions={"export": True, "source": False, "compiled": False, "editor": False},
                downloadFileName=dl_name,
            )

            chart = (
                alt.Chart(long_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("DATE:T", title="Date"),
                    y=alt.Y(
                        f"{value_col_for_chart}:Q",
                        title=y_title,
                        axis=alt.Axis(format="~s"),
                    ),
                    color=alt.Color(
                        f"{dim_col}:N",
                        title="Series",
                        scale=alt.Scale(scheme="tableau10"),
                    ),
                    tooltip=[
                        alt.Tooltip("DATE:T", title="Date"),
                        alt.Tooltip(f"{dim_col}:N", title="Series"),
                        alt.Tooltip(f"{value_col_for_chart}:Q", title="Value", format=","),
                    ],
                )
                .properties(height=420)
                .interactive()
            )
        else:
            long_df = f[["YEAR", dim_col, value_col_for_chart]].copy()
            long_df["YEAR"] = long_df["YEAR"].astype(int).astype(str)
            present_geos = [geo_sel] if geo_sel else []
            y_title = y_title_base

            if selected_series_list:
                if len(selected_series_list) == 1:
                    dl_series_label = selected_series_list[0]
                else:
                    dl_series_label = f"{len(selected_series_list)} series"
            else:
                dl_series_label = None

            dl_name = build_download_name(
                dataset_label, dl_series_label, yr_from, yr_to, present_geos
            )
            alt.renderers.set_embed_options(
                actions={"export": True, "source": False, "compiled": False, "editor": False},
                downloadFileName=dl_name,
            )

            chart = (
                alt.Chart(long_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("YEAR:O", title="Year", axis=alt.Axis(format="d")),
                    y=alt.Y(
                        f"{value_col_for_chart}:Q",
                        title=y_title,
                        axis=alt.Axis(format="~s"),
                    ),
                    color=alt.Color(
                        f"{dim_col}:N",
                        title="Series",
                        scale=alt.Scale(scheme="tableau10"),
                    ),
                    tooltip=[
                        alt.Tooltip("YEAR:O", title="Year", format="d"),
                        alt.Tooltip(f"{dim_col}:N", title="Series"),
                        alt.Tooltip(f"{value_col_for_chart}:Q", title="Value", format=","),
                    ],
                )
                .properties(height=420)
                .interactive()
            )

    chart_tab, data_tab = st.tabs(["Chart", "Data"])

    with chart_tab:
        st.altair_chart(chart, width="stretch")

        file_stem_parts = [table_cfg["id"].replace(" ", "_")]
        selected_series_label = None
        if selected_series:
            selected_series_label = selected_series
        elif selected_series_list:
            selected_series_label = ",".join(map(str, selected_series_list))
        if selected_series_label:
            file_stem_parts.append(str(selected_series_label).replace(" ", "_"))
        if pick:
            file_stem_parts.append("_".join(g.replace(" ", "_") for g in pick))
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
        series_piece = None
        if selected_series:
            series_piece = safe_slug(selected_series)
        elif selected_series_list:
            series_piece = safe_slug("-".join(map(str, selected_series_list)))
        geo_piece = safe_slug("-".join(pick)) if compare_mode == "Geographies" else safe_slug(geo_sel)
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

    if inflation_note:
        st.caption(inflation_note)

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
    selected_series_for_params = selected_series
    selected_geos_for_params = pick
    year_range_for_params = (yr_from, yr_to)
    inflation_adjusted_for_params = inflation_checked

# ============================================================
# FARM LABOUR & HOUSEHOLDS (ONTARIO) VIEW
# ============================================================

    # Return footer state for URL sharing
    return {
        "selected_dataset_id": locals().get("selected_dataset_id"),
        "selected_series_for_params": locals().get("selected_series_for_params"),
        "selected_geos_for_params": locals().get("selected_geos_for_params", []),
        "year_range_for_params": locals().get("year_range_for_params"),
        "inflation_adjusted_for_params": locals().get("inflation_adjusted_for_params", False),
    }
