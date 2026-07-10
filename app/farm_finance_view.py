import datetime
import io
import sys
import pandas as pd
import streamlit as st
import streamlit.runtime as st_runtime
import altair as alt
from typing import Mapping

from dataset_descriptions import DATASET_DESCRIPTIONS
from app.analytics import (
    AnalyticsOptions,
)
from app.cpi_utils import load_cpi_deflators
from app.unit_utils import get_unit_label, supports_inflation_adjustment
from scripts import config_loader

from app.utils import (
    _get_param,
    _get_int_param,
    get_table_metadata,
    safe_load_dataset,
    ensure_year_column,
    STATCAN_METADATA_COLUMNS,
    find_column_fuzzy,
    find_series_column,
    get_default_series,
    multiselect_with_pins,
    pick_default_breakdown_option,
    get_default_geos,
    compute_last_updated_period,
    format_last_period,
    load_table,
    make_line_chart,
    get_chart_png_bytes,
    apply_index_to_base_if_needed,
    build_narrative_summary,
    _format_quantity_for_narrative,
    render_dataset_notes,
    render_source_caption,
    build_download_name,
    safe_slug,
    DATA_LATEST,
    DEFAULT_SERIES_LABELS, # If needed, though used in utils
    compute_time_series_analytics,
    compute_yoy_analytics,
)

# Load table metadata locally as needed
TABLE_CONFIG = config_loader.load_tables(active_only=True)


def render_farm_finance_view(analytics_options: AnalyticsOptions, params: dict):
    dataset_options = {
        # Core revenue / expense accounts
        "Farm cash receipts (annual)": "32-10-0045-01.csv",
        "Operating revenues & expenses (ATDP)": "32-10-0136-01.csv",
        "Operating revenues & expenses (avg by farm type)": "32-10-0078-01.csv",
        "Farm operating expenses & depreciation charges": "32-10-0049-01.csv",
        "Net farm income": "32-10-0052-01.csv",
        "Direct program payments to producers": "32-10-0106-01.csv",
        "Agriculture value added account": "32-10-0048-01.csv",
        "Farm income in kind in Canada": "32-10-0055-01.csv",

        # Balance sheet / stock accounts
        "Farm capital (value of assets)": "32-10-0050-01.csv",
        "Value per acre of farm land and buildings (July 1)": "32-10-0047-01.csv",
        "Farm debt outstanding": "32-10-0051-01.csv",
        "Balance sheet of farm sector": "32-10-0056-01.csv",

        # Additional household & detailed balance sheet tables
        "Farm family income by source": "32-10-0213-01.csv",
        "Total income of farm families": "32-10-0213-01.csv",
        "Farm financial statistics – balance sheet": "32-10-0101-01.csv",
        "Farm financial statistics – assets": "32-10-0101-01.csv",
        "Farm financial statistics – liabilities": "32-10-0101-01.csv",
        "Financial structure by farm type (average per farm)": "32-10-0102-01.csv",
        "Financial structure by revenue class (average per farm)": "32-10-0103-01.csv",
        "Capital purchases and sales by farms (average per farm)": "32-10-0104-01.csv",
        "Income of farm families by income quartile": "32-10-0214-01.csv",

        # Census 2021 snapshots
        "Farm capital (Census 2021)": "32-10-0237-01.csv",
        "Farm machinery & equipment value (Census 2021)": "32-10-0238-01.csv",
        "Farms by total operating revenues (Census 2021)": "32-10-0239-01.csv",
        "Operating revenues (Census 2021)": "32-10-0240-01.csv",
        "Operating expenses (Census 2021)": "32-10-0241-01.csv",
        "Direct sales to consumers (Census 2021)": "32-10-0242-01.csv",

        # Farm structure & land rents
        "Farms by gross farm receipts (historical Census)": "32-10-0157-01.csv",
        "Farm machinery (historical Census)": "32-10-0163-01.csv",
        "Number of farms by NAICS industry": "32-10-0166-01.csv",

        # Capital investment & GDP (RBC Capital Gains datasets)
        "Capital formation — agriculture & food manufacturing": "36-10-0096-01.csv",
        "Agriculture GDP by industry": "36-10-0434-03.csv",
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

    st.subheader("Farm finance statistics – Canada & Provinces")
    render_source_caption(table_cfg)

    _desc = DATASET_DESCRIPTIONS.get(table_id)
    if _desc:
        st.info(f"📊 **What this data shows:** {_desc}")

    with st.spinner("Fetching data from Statistics Canada or local dataset…"):
        df = safe_load_dataset(table_cfg)

    if df is None or not isinstance(df, pd.DataFrame):
        st.info("No data is available for this dataset in the current environment.")
        df = pd.DataFrame(columns=["YEAR", "GEO", "VALUE"])

    date_col = "YEAR"
    geo_col = "GEO"
    value_col = "VALUE" if "VALUE" in df.columns else None

    df = ensure_year_column(df)

    if date_col in df.columns:
        df = df.dropna(subset=[date_col]).copy()
        df[date_col] = df[date_col].astype(int)
    else:
        df = df.copy()

    if value_col is None:
        st.error("Expected 'VALUE' column not found in dataset.")
        st.stop()
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")

    metadata_exclusions = {c.lower() for c in STATCAN_METADATA_COLUMNS}
    dim_cols = [
        c
        for c in df.columns
        if c not in {date_col, geo_col, value_col, "deflator"}
        and not pd.api.types.is_numeric_dtype(df[c])
        and c.lower() not in metadata_exclusions
    ]

    if table_id == "32-10-0101-01":
        item_col = find_column_fuzzy(df, ["Balance sheet item", "Farm financial item"])
        if item_col:
            lower_label = dataset_label.lower()
            if "asset" in lower_label:
                df = df[df[item_col].str.contains("asset", case=False, na=False)].copy()
            elif "liabilit" in lower_label:
                df = df[
                    df[item_col]
                    .str.contains("liabilit", case=False, na=False)
                ].copy()

    series_col = find_series_column(table_id, df)
    if table_id == "32-10-0047-01":
        series_col = None
    if table_id == "32-10-0213-01" and dataset_label == "Farm family income by source":
        income_source_col = find_column_fuzzy(
            df,
            [
                "Source of income",
                "source of income",
                "Income source",
                "Source of income of farm families",
            ],
        )
        if income_source_col:
            series_col = income_source_col

    # Census 2021 tables
    if table_id == "32-10-0237-01":
        series_col = find_column_fuzzy(df, ["Farm capital"]) or series_col
    elif table_id == "32-10-0238-01":
        series_col = find_column_fuzzy(df, ["Farm machinery and equipment"]) or series_col
    elif table_id == "32-10-0239-01":
        series_col = find_column_fuzzy(df, ["Total farm revenues distribution"]) or series_col
    elif table_id == "32-10-0240-01":
        series_col = find_column_fuzzy(df, ["Total operating revenues, excluding forest products", "Operating revenues"]) or series_col
    elif table_id == "32-10-0241-01":
        series_col = find_column_fuzzy(df, ["Total farm operating expenses", "Operating expenses"]) or series_col
    elif table_id == "32-10-0242-01":
        series_col = find_column_fuzzy(df, ["Direct sales"]) or series_col
    # Farm structure & rents
    elif table_id == "32-10-0157-01":
        series_col = find_column_fuzzy(df, ["Farms classified by gross farm receipts", "Revenue class"]) or series_col
    elif table_id == "32-10-0163-01":
        series_col = find_column_fuzzy(df, ["Selected machinery", "Farm size"]) or series_col
    elif table_id == "32-10-0166-01":
        series_col = find_column_fuzzy(df, ["North American Industry Classification System (NAICS)", "NAICS"]) or series_col
    # Capital investment & GDP tables — default to agriculture, not "Total"
    elif table_id in ("36-10-0096-01", "36-10-0434-03"):
        series_col = find_column_fuzzy(df, ["Industry"]) or series_col

    # Table-specific preferred defaults that override the generic "total" heuristic
    _TABLE_PREFERRED_DEFAULTS: dict[str, list[str]] = {
        "36-10-0096-01": ["agriculture, forestry, fishing and hunting", "crop production"],
        "36-10-0434-03": ["agriculture, forestry, fishing and hunting", "crop and animal production"],
    }

    selected_series_list: list[str] = []
    if series_col:
        all_series_vals = sorted(df[series_col].dropna().unique().tolist())

        dataset_id_for_defaults = table_cfg.get("id", table_id)

        # Check table-specific preferred defaults first
        table_prefs = _TABLE_PREFERRED_DEFAULTS.get(table_id, [])
        heuristic_default = None
        if table_prefs:
            heuristic_default = next(
                (s for s in all_series_vals if str(s).lower() in table_prefs),
                None,
            )

        # Fall back to the generic heuristic
        if heuristic_default is None:
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
        series_param = _get_param(params, "series", None)
        url_series = (
            [s for s in (series_param.split(",") if series_param else []) if s in all_series_vals]
        )

        selected_series_list = multiselect_with_pins(
            "Series (multiple allowed)",
            all_series_vals,
            key=f"{table_id}_series",
            url_values=url_series,
            default_values=series_default,
        )
        if not selected_series_list and series_default:
            selected_series_list = series_default
        if selected_series_list:
            df = df[df[series_col].isin(selected_series_list)].copy()

    remaining_dims = [c for c in dim_cols if c != series_col]

    if remaining_dims:
        with st.sidebar.expander("Additional breakdowns"):
            for col in remaining_dims:
                options = sorted(df[col].dropna().unique().tolist(), key=lambda x: str(x))
                if not options:
                    continue
                default_option = None
                if table_id == "32-10-0078-01":
                    for preferred in [
                        "net operating income",
                        "net farm income",
                        "net operating return to family",
                        "net operating return to unpaid labour",
                    ]:
                        default_option = next(
                            (opt for opt in options if preferred in str(opt).lower()), None
                        )
                        if default_option:
                            break
                if default_option is None:
                    for opt in options:
                        opt_str = str(opt).lower()
                        if "total" in opt_str or opt_str.startswith("all "):
                            default_option = opt
                            break
                if default_option is None:
                    default_option = pick_default_breakdown_option(df, col) or options[0]

                selected_opt = st.selectbox(
                    col,
                    options,
                    index=options.index(default_option) if default_option in options else 0,
                    key=f"{table_id}_{col}",
                )
                df = df[df[col] == selected_opt].copy()

    supports_inflation = supports_inflation_adjustment(df, table_cfg)

    if geo_col not in df.columns or value_col not in df.columns:
        st.error("Expected 'GEO' and 'VALUE' columns not found.")
        st.stop()

    geos = sorted(df[geo_col].dropna().unique().tolist())
    default_geos = get_default_geos(geos)
    if not default_geos and geos:
        default_geos = [geos[0]]
    geos_param = _get_param(params, "geos", None)
    url_geos = [g for g in (geos_param.split(",") if geos_param else []) if g in geos]

    geo_pinned = [g for g in geos if g in ["Canada", "Ontario"]]
    with st.sidebar:
        pick = multiselect_with_pins(
            "Geography",
            geos,
            key=f"{table_id}_geos",
            pinned_options=geo_pinned,
            url_values=url_geos,
            default_values=default_geos,
        )

    yrs = df[df[geo_col].isin(pick)][date_col].dropna().astype(int)
    if yrs.empty:
        st.info("No data for selected filters.")
        if st_runtime.exists():
            st.stop()
        else:
            sys.exit(0)

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

    f = df[(df[geo_col].isin(pick)) & (df[date_col].between(yr_from, yr_to))].copy()
    if f.empty:
        st.info("No data for selected filters.")
        st.stop()

    group_cols = [date_col, geo_col]
    if series_col:
        group_cols.append(series_col)

    plot_df = (
        f.dropna(subset=[date_col])
        .assign(**{date_col: f[date_col].astype(int)})
        .groupby(group_cols, as_index=False)[value_col]
        .sum()
    )

    if plot_df.empty:
        st.info("No data for selected filters.")
        st.stop()

    label_col = "GEO_SERIES_LABEL"
    if series_col:
        plot_df[label_col] = (
            plot_df[geo_col].astype(str) + " – " + plot_df[series_col].astype(str)
        )
    else:
        plot_df[label_col] = plot_df[geo_col].astype(str)

    chart_df = plot_df.copy()
    value_col_for_chart = value_col
    time_col = date_col
    inflation_note: str | None = None
    base_year: int | None = None
    inflation_applied = False
    index_base_year: int | None = None
    indexed = False

    unit_lbl = get_unit_label(df)  # Use original df (pre-groupby) so SCALAR_FACTOR/UOM are available
    is_dollar_series = supports_inflation

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

    series_years_full = pd.to_numeric(chart_df[time_col], errors="coerce")
    series_years = series_years_full.dropna().astype(int)
    if series_years.empty:
        base_year = None
    else:
        base_year = int(series_years.max())

    if cpi is not None and base_year is not None and base_year in cpi["YEAR"].values:
        base_cpi = float(cpi.loc[cpi["YEAR"] == base_year, "cpi"].iloc[0])
        cpi = cpi.assign(deflator=base_cpi / cpi["cpi"])
        cpi_for_merge = cpi.rename(columns={"YEAR": "CPI_YEAR"})
        # Deduplicate: keep one deflator per year to prevent row multiplication
        cpi_for_merge = (
            cpi_for_merge.groupby("CPI_YEAR", as_index=False)[["deflator"]]
            .mean()
        )
        chart_df = chart_df.merge(
            cpi_for_merge[["CPI_YEAR", "deflator"]],
            left_on=series_years_full.astype("Int64"),
            right_on="CPI_YEAR",
            how="left",
        ).drop(columns=["CPI_YEAR"], errors="ignore")

    if (
        inflation_checked
        and "deflator" in chart_df.columns
        and chart_df["deflator"].notna().any()
    ):
        chart_df["VALUE_REAL"] = chart_df[value_col_for_chart] * chart_df["deflator"]
        value_col_for_chart = "VALUE_REAL"
        inflation_applied = True

    f = chart_df

    f, value_col_for_chart, index_base_year, indexed = apply_index_to_base_if_needed(
        f,
        value_col=value_col_for_chart,
        year_col=time_col,
        base_year=int(yr_from),
        group_cols=[label_col],
        analytics_options=analytics_options,
    )

    # Keep chart_df in sync so KPI section can find the (possibly new) value column
    chart_df = f

    if inflation_applied and base_year is not None:
        inflation_note = (
            "Values adjusted for inflation using CPI all-items, Canada, annual average "
            "(StatCan table 18-10-0005-01); "
            f"constant {base_year} dollars."
        )

    # KPI header: scope to primary geography to avoid cross-geo double-counting
    # (StatCan's "Canada" row already includes all provincial data)
    primary_geo = next((g for g in pick if g == "Canada"), pick[0]) if pick else None
    kpi_df = chart_df[chart_df[geo_col] == primary_geo] if primary_geo else chart_df

    latest_slice = kpi_df[kpi_df[date_col] == yr_to]
    prev_slice = kpi_df[kpi_df[date_col] < yr_to]
    total_latest = latest_slice[value_col_for_chart].sum()

    metric_label = f"{dataset_label} in {yr_to}"
    if primary_geo and len(pick) > 1:
        metric_label = f"{dataset_label} ({primary_geo}) in {yr_to}"
    if inflation_applied and base_year is not None:
        metric_label = f"{metric_label} (constant {base_year} dollars)"

    if not prev_slice.empty:
        prev_year = int(prev_slice[date_col].max())
        prev_total = prev_slice[prev_slice[date_col] == prev_year][value_col_for_chart].sum()
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
        time_col=date_col,
    )
    analytics_yoy = compute_yoy_analytics(
        kpi_df,
        value_col=value_col_for_chart,
        time_col=date_col,
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
            _cagr_val = analytics_level['cagr_5y'] * 100
            _cagr_hint = "Strong growth" if _cagr_val > 2 else ("Stable" if _cagr_val >= 0 else "Declining")
            tiles.append(
                (
                    "Avg. annual growth",
                    f"{_cagr_val:.1f}%",
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
            _vol = analytics_level['growth_volatility']
            _vol_hint = "Volatile — values swing widely" if _vol > 10 else ("Moderate variability" if _vol > 5 else "Stable")
            tiles.append(
                (
                    "Year-to-year variability",
                    f"{_vol:.1f}%",
                    "How much annual change fluctuates",
                )
            )

    if tiles:
        cols = st.columns(len(tiles))
        for col, (label, value, delta) in zip(cols, tiles):
            with col:
                st.metric(label, value, delta)

    selected_series_label = ", ".join(selected_series_list) if selected_series_list else None
    caption_text = (
        f"{dataset_label} — {selected_series_label}"
        if selected_series_label
        else dataset_label
    )
    if inflation_applied and base_year is not None:
        caption_text = f"{caption_text} (constant {base_year} dollars)"

    last_year_in_selection = int(f[date_col].max()) if not f.empty else None
    dataset_title_for_summary = dataset_label
    if selected_series_label:
        dataset_title_for_summary = f"{dataset_label} — {selected_series_label}"
    narrative = build_narrative_summary(
        dataset_title=dataset_title_for_summary,
        analytics_level=analytics_level,
        analytics_yoy=analytics_yoy,
        analytics_options=analytics_options,
        last_year=last_year_in_selection,
        unit_label=unit_lbl,
        df=chart_df,
        label_col=label_col,
        value_col=value_col_for_chart,
    )

    if narrative:
        st.markdown("#### Summary")
        st.markdown(narrative.replace('$', '\\$'))
    st.caption(caption_text)

    render_dataset_notes(table_cfg)

    last_period = compute_last_updated_period(f)
    if last_period is not None:
        st.caption(f"Last available period in dataset: {format_last_period(last_period)}")

    long_df = f[[date_col, geo_col, value_col_for_chart]].copy()
    long_df[label_col] = chart_df[label_col]
    present_geos = sorted(long_df[label_col].unique().tolist())
    unit_lbl = get_unit_label(df)  # Use original df so SCALAR_FACTOR/UOM are available
    if indexed:
        if index_base_year is not None:
            y_title = (
                f"{dataset_label} — index (base year = {index_base_year}, 100 = base)"
            )
        else:
            y_title = (
                f"{dataset_label} — index (first non-zero year in selected range = 100)"
            )
    elif inflation_applied and base_year is not None and unit_lbl and (
        "dollar" in unit_lbl.lower() or "$" in unit_lbl
    ):
        y_title = f"{dataset_label} — constant {base_year} dollars"
    else:
        y_title = f"{dataset_label}{(' (' + unit_lbl + ')') if unit_lbl else ''}"

    dl_name = build_download_name(
        dataset_label, selected_series_label, yr_from, yr_to, present_geos
    )
    alt.renderers.set_embed_options(
        actions={"export": True, "source": False, "compiled": False, "editor": False},
        downloadFileName=dl_name,
    )

    tooltip_fields = []
    if geo_col in long_df.columns:
        tooltip_fields.append((geo_col, "Geography"))
    if series_col:
        tooltip_fields.append((series_col, "Series"))

    chart = make_line_chart(
        long_df,
        y_title,
        present_geos,
        value_col=value_col_for_chart,
        color_col=label_col,
        color_title="Geography / series",
        tooltip_fields=tooltip_fields,
        analytics_options=analytics_options,
    )
    chart_tab, data_tab = st.tabs(["Chart", "Data"])

    with chart_tab:
        st.altair_chart(chart, width="stretch")
        if unit_lbl:
            st.caption(f"ℹ️ Values shown in: {unit_lbl}")

        file_stem_parts = [table_cfg["id"].replace(" ", "_")]
        selected_series_label_for_file = selected_series_label
        if selected_series_label_for_file:
            file_stem_parts.append(str(selected_series_label_for_file).replace(" ", "_"))
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

    # Return key parameters needed for URL sharing
    selected_series_for_params = None
    if selected_series_list:
        selected_series_for_params = ",".join(map(str, selected_series_list))
    elif selected_series_label:
        selected_series_for_params = selected_series_label

    return {
        "selected_dataset_id": table_cfg.get("id", table_id),
        "selected_series_for_params": selected_series_for_params,
        "selected_geos_for_params": pick,
        "year_range_for_params": (yr_from, yr_to),
        "inflation_adjusted_for_params": inflation_checked,
    }
