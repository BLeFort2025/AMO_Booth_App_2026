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



def render_transport_exports_view(params, analytics_options):
    """Render the Transportation & Exports view. Returns footer-state dict."""
    st.subheader("Transportation & Exports (Farm logistics & trade flows)")

    # All active Transportation & Exports tables from config,
    # excluding 32-10-0049-01 (farm operating expenses).
    transport_tables = [
        t
        for t in TABLE_CONFIG
        if t.get("theme") == "Transportation & Exports"
        and t.get("active", True)
        and t.get("id") != "32-10-0049-01"
    ]
    if not transport_tables:
        st.info("No transportation & exports tables are configured in tables.yml yet.")
        st.stop()

    dataset_labels = [t["name"] for t in transport_tables]
    default_dataset_label = dataset_labels[0]
    dataset_from_url = _get_param(params, "dataset", transport_tables[0]["id"])
    if dataset_from_url.endswith(".csv"):
        dataset_from_url = dataset_from_url.replace(".csv", "")
    initial_dataset_label = next(
        (t["name"] for t in transport_tables if t["id"] == dataset_from_url),
        default_dataset_label,
    )
    dataset_label = st.sidebar.selectbox(
        "Dataset", dataset_labels, index=dataset_labels.index(initial_dataset_label)
    )
    tbl = next(t for t in transport_tables if t["name"] == dataset_label)
    table_id = tbl["id"]
    filename = f"{table_id}.csv"
    table_cfg = tbl

    with st.spinner("Fetching data from Statistics Canada or local dataset…"):
        df = safe_load_dataset(table_cfg)

    st.caption(dataset_label)
    render_dataset_notes(table_cfg)

    if "VALUE" not in df.columns:
        st.error("Expected column 'VALUE' not found in this dataset.")
        st.stop()
    df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")

    geo_choice = None
    geo_options: list[str] = []
    if "GEO" in df.columns and df["GEO"].notna().any():
        geo_options = sorted(df["GEO"].dropna().unique().tolist())

    # Table-specific extra filters
    commodity_col = None
    measure_col = None
    trade_col = None
    partner_col = None
    napcs_col = None
    mode_col = None

    # Trucking financial statistics – NAICS industry group
    if table_id == "23-10-0291-01":
        naics_col = find_column_fuzzy(df, ["North American Industry Classification System"])
        if naics_col:
            naics_vals = sorted(df[naics_col].dropna().unique().tolist())
            default_naics = next(
                (v for v in naics_vals if "Total, truck transportation" in str(v)),
                naics_vals[0],
            )
            naics_choice = st.sidebar.selectbox(
                "Industry group (NAICS)", naics_vals, index=naics_vals.index(default_naics)
            )
            df = df[df[naics_col] == naics_choice].copy()

    # For-hire motor carrier freight SPI – expose NAICS series directly
    if table_id == "18-10-0281-01":
        naics_col = find_column_fuzzy(
            df, ["North American Industry Classification System (NAICS)"]
        )
        if naics_col:
            df = df.copy()
            df.rename(columns={naics_col: "North American Industry Classification System (NAICS)"}, inplace=True)

    # Railway carloadings – measure and commodity group filters
    if table_id == "23-10-0216-02":
        measure_col = find_column_fuzzy(df, ["Estimates"])
        if measure_col:
            measures = sorted(df[measure_col].dropna().unique().tolist())
            default_meas = next(
                (m for m in measures if "tonnes" in str(m).lower()),
                measures[0],
            )
            meas_choice = st.sidebar.selectbox(
                "Measure", measures, index=measures.index(default_meas)
            )
            df = df[df[measure_col] == meas_choice].copy()

        commodity_col = find_column_fuzzy(df, ["Commodity group"])
        if commodity_col:
            commodities = sorted(df[commodity_col].dropna().unique().tolist())
            default_comm = next(
                (c for c in commodities if "agricultural products" in str(c).lower()),
                None,
            )
            if default_comm is None:
                default_comm = next(
                    (c for c in commodities if "total" in str(c).lower()),
                    commodities[0],
                )
            comm_choice = st.sidebar.selectbox(
                "Commodity group", commodities, index=commodities.index(default_comm)
            )
            df = df[df[commodity_col] == comm_choice].copy()

    # CFAF – characteristics and commodity group
    if table_id == "23-10-0142-01":
        char_col = find_column_fuzzy(df, ["Characteristics"])
        if char_col:
            chars = sorted(df[char_col].dropna().unique().tolist())
            default_char = next(
                (c for c in chars if "value" in str(c).lower()),
                chars[0],
            )
            char_choice = st.sidebar.selectbox(
                "Characteristic", chars, index=chars.index(default_char)
            )
            df = df[df[char_col] == char_choice].copy()

        commodity_col = find_column_fuzzy(df, ["Commodity group"])
        if commodity_col:
            comms = sorted(df[commodity_col].dropna().unique().tolist())
            default_comm = next(
                (c for c in comms if "agricultural products" in str(c).lower()),
                None,
            )
            if default_comm is None:
                default_comm = next(
                    (c for c in comms if "total" in str(c).lower()),
                    comms[0],
                )
            comm_choice = st.sidebar.selectbox(
                "Commodity group", comms, index=comms.index(default_comm)
            )
            df = df[df[commodity_col] == comm_choice].copy()

    # CIMT by mode – trading partner, NAPCS, and trade-flow selector
    if table_id == "12-10-0177-01":
        partner_col = find_column_fuzzy(df, ["Principal trading partner"])
        if partner_col:
            partners = sorted(df[partner_col].dropna().unique().tolist())
            default_partner = next(
                (p for p in partners if "all countries" in str(p).lower()),
                partners[0],
            )
            partner_choice = st.sidebar.selectbox(
                "Principal trading partner", partners, index=partners.index(default_partner)
            )
            df = df[df[partner_col] == partner_choice].copy()

        napcs_col = find_column_fuzzy(
            df, ["North American Product Classification System", "NAPCS"]
        )
        if napcs_col:
            napcs_vals = sorted(df[napcs_col].dropna().unique().tolist())
            default_napcs = next(
                (v for v in napcs_vals if "fresh fruit, nuts and vegetables" in str(v).lower()),
                None,
            )
            if default_napcs is None:
                default_napcs = next(
                    (
                        v
                        for v in napcs_vals
                        if "farm, fishing and intermediate food products" in str(v).lower()
                    ),
                    None,
                )
            if default_napcs is None:
                default_napcs = next(
                    (v for v in napcs_vals if "total" in str(v).lower()),
                    napcs_vals[0],
                )
            napcs_choice = st.sidebar.selectbox(
                "Commodity (NAPCS)", napcs_vals, index=napcs_vals.index(default_napcs)
            )
            df = df[df[napcs_col] == napcs_choice].copy()

        trade_col = find_column_fuzzy(df, ["Trade"])
        if trade_col:
            trade_vals = sorted(df[trade_col].dropna().unique().tolist())
            default_flows = [v for v in trade_vals if "export" in str(v).lower()]
            if not default_flows:
                default_flows = trade_vals
            flow_pick = st.sidebar.multiselect(
                "Trade flow (Exports / Imports)", trade_vals, default=default_flows
            )
            if not flow_pick:
                st.info("Select at least one trade flow.")
                st.stop()
            df = df[df[trade_col].isin(flow_pick)].copy()

        mode_col = find_column_fuzzy(df, ["Mode of transport"])

    # Activity indicators and supply chain performance – expose mode filters when present
    if table_id in {"23-10-0269-01", "23-10-0271-01"}:
        mode_col = find_column_fuzzy(df, ["Mode of transport", "Mode of transportation"])
        if mode_col and df[mode_col].dropna().nunique() > 1:
            modes = sorted(df[mode_col].dropna().unique().tolist())
            default_mode = next(
                (m for m in modes if "total" in str(m).lower()),
                modes[0],
            )
            mode_choice = st.sidebar.selectbox(
                "Mode of transport", modes, index=modes.index(default_mode)
            )
            df = df[df[mode_col] == mode_choice].copy()

    # Determine primary series dimension
    dim_col = find_series_column(table_id, df)

    # For CIMT, treat each Mode × Trade-flow combo as its own series
    if table_id == "12-10-0177-01":
        if trade_col and dim_col:
            df["Series"] = df[trade_col].astype(str) + " – " + df[dim_col].astype(str)
            dim_col = "Series"

    # Override series dimension for carloadings to focus on components
    if table_id == "23-10-0216-02":
        component_col = find_column_fuzzy(df, ["Railway carloadings components"])
        if component_col:
            dim_col = component_col

    selected_series_list: list[str] | None = None
    series_label_for_filename: str | None = None

    # Additional breakdown filters (excluding the main series dimension and GEO)
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
        extra_dim_cols.append(col)

    if extra_dim_cols:
        with st.sidebar.expander("Additional breakdowns"):
            for col in extra_dim_cols:
                options = sorted(df[col].dropna().unique().tolist())
                all_label = f"All {col}" if len(options) > 1 else options[0]
                selected = st.selectbox(
                    col, [all_label] + options, key=f"transport_{table_id}_{col}"
                )
                if selected != all_label:
                    df = df[df[col] == selected].copy()

    # Compare mode: geographies vs series (when both dimensions exist)
    compare_mode = "Series"
    if geo_options and dim_col:
        compare_mode = st.sidebar.radio(
            "Compare by",
            ["Geographies", "Series"],
            index=1,
            help="Geographies: one series, multiple geographies. Series: one geography, multiple series.",
        )

    # SERIES SELECTOR(S)
    selected_series: str | None = None
    selected_geos: list[str] = []
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

        if compare_mode == "Geographies" and geo_options:
            default_series = series_options[0]

            if table_id == "12-10-0177-01":
                pref = [
                    s
                    for s in series_options
                    if any(
                        kw in str(s).lower()
                        for kw in ["road", "rail", "water", "air", "other"]
                    )
                ]
                if pref:
                    default_series = pref[0]
            elif table_id == "23-10-0216-02":
                pref = [
                    s
                    for s in series_options
                    if any(
                        kw in str(s).lower()
                        for kw in [
                            "total traffic carried",
                            "total non-intermodal traffic loaded",
                            "wheat",
                            "canola",
                        ]
                    )
                ]
                if pref:
                    default_series = pref[0]
            elif table_id == "18-10-0281-01":
                pref = [
                    s
                    for s in series_options
                    if "truck transportation" in str(s).lower()
                ]
                if pref:
                    default_series = pref[0]

            series_param = _get_param(params, "series", default_series)
            if series_param in series_options:
                default_series = series_param

            selected_series = st.sidebar.selectbox(
                "Series", series_options, index=series_options.index(default_series)
            )
            df = df[df[dim_col] == selected_series].copy()
            series_label_for_filename = selected_series
        else:
            default_series_list = series_options[:5] if len(series_options) > 5 else series_options

            if table_id == "12-10-0177-01":
                pref = [
                    s
                    for s in series_options
                    if any(
                        kw in str(s).lower()
                        for kw in ["road", "rail", "water", "air", "other"]
                    )
                ]
                if pref:
                    default_series_list = pref
            elif table_id == "23-10-0216-02":
                pref = [
                    s
                    for s in series_options
                    if any(
                        kw in str(s).lower()
                        for kw in [
                            "total traffic carried",
                            "total non-intermodal traffic loaded",
                            "wheat",
                            "canola",
                        ]
                    )
                ]
                if pref:
                    default_series_list = pref
            elif table_id == "18-10-0281-01":
                pref = [
                    s
                    for s in series_options
                    if "truck transportation" in str(s).lower()
                ]
                if pref:
                    default_series_list = pref

            series_param = _get_param(params, "series", None)
            if series_param:
                parsed = [s.strip() for s in series_param.split(",") if s.strip()]
                parsed = [s for s in parsed if s in series_options]
                if parsed:
                    default_series_list = parsed

            selected_series_list = st.sidebar.multiselect(
                "Series (multiple allowed)", series_options, default=default_series_list
            )
            if not selected_series_list:
                st.info("Select at least one series.")
                st.stop()
            df = df[df[dim_col].isin(selected_series_list)].copy()

            if len(selected_series_list) == 1:
                series_label_for_filename = str(selected_series_list[0])
            else:
                series_label_for_filename = f"{len(selected_series_list)} series"

    # Geography selection after series filtering
    if geo_options:
        if compare_mode == "Geographies" and dim_col:
            default_geos = [g for g in geo_options if "Canada" in str(g)]
            if not default_geos:
                default_geos = geo_options[:5] if len(geo_options) > 5 else geo_options
            geos_param = _get_param(params, "geos", None)
            if geos_param:
                parsed = [g for g in geos_param.split(",") if g in geo_options]
                if parsed:
                    default_geos = parsed
            selected_geos = st.sidebar.multiselect(
                "Geographies", geo_options, default=default_geos
            )
            if not selected_geos:
                st.info("Select at least one geography.")
                st.stop()
            df = df[df["GEO"].isin(selected_geos)].copy()
            geo_choice = None
        elif not dim_col:
            default_geos = [g for g in geo_options if "Canada" in str(g)]
            if not default_geos:
                default_geos = geo_options[:5] if len(geo_options) > 5 else geo_options
            geos_param = _get_param(params, "geos", None)
            if geos_param:
                parsed = [g for g in geos_param.split(",") if g in geo_options]
                if parsed:
                    default_geos = parsed
            selected_geos = st.sidebar.multiselect(
                "Geographies", geo_options, default=default_geos
            )
            if not selected_geos:
                st.info("Select at least one geography.")
                st.stop()
            df = df[df["GEO"].isin(selected_geos)].copy()
            geo_choice = selected_geos[0] if len(selected_geos) == 1 else None
        else:
            default_geo = "Canada" if "Canada" in geo_options else geo_options[0]
            geos_param = _get_param(params, "geos", None)
            if geos_param:
                geo_candidate = geos_param.split(",")[0]
                if geo_candidate in geo_options:
                    default_geo = geo_candidate
            geo_choice = st.sidebar.selectbox(
                "Geography", geo_options, index=geo_options.index(default_geo)
            )
            df = df[df["GEO"] == geo_choice].copy()
            selected_geos = [geo_choice]
    else:
        selected_geos = []

    chart_dim_col = dim_col
    if compare_mode == "Geographies" and geo_options and dim_col:
        chart_dim_col = "GEO"

    # Build DATE column from REF_DATE or YEAR
    if "REF_DATE" in df.columns:
        if any("Q" in str(x) for x in df["REF_DATE"].unique()):
            def quarter_to_date(qstr: str) -> str:
                text = str(qstr)
                year = int(text[:4])
                q = text[-1]
                qm = {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}.get(q, "12-31")
                return f"{year}-{qm}"

            df["DATE"] = pd.to_datetime(
                df["REF_DATE"].astype(str).apply(quarter_to_date), errors="coerce"
            )
        else:
            df["DATE"] = pd.to_datetime(
                df["REF_DATE"].astype(str).str.slice(0, 7) + "-01", errors="coerce"
            )
    elif "YEAR" in df.columns:
        df["DATE"] = pd.to_datetime(
            df["YEAR"].astype(int).astype(str) + "-01-01", errors="coerce"
        )
    else:
        df["DATE"] = pd.NaT

    if df["DATE"].notna().any():
        df = df.dropna(subset=["DATE"]).copy()
        df["YEAR"] = df["DATE"].dt.year
    elif "YEAR" in df.columns:
        df = df.dropna(subset=["YEAR"]).copy()
        df["YEAR"] = df["YEAR"].astype(int)
    else:
        st.error("Could not determine a time dimension for this dataset.")
        st.stop()

    yrs = df["YEAR"].dropna().astype(int)
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
    df = df[df["YEAR"].between(yr_from, yr_to)].copy()
    if df.empty:
        st.info("No data for selected filters.")
        st.stop()

    # If no explicit series dimension but multiple geographies remain, use GEO as series
    if chart_dim_col is None and "GEO" in df.columns and df["GEO"].dropna().nunique() > 1:
        chart_dim_col = "GEO"

    # Capture units BEFORE aggregation
    unit_lbl = get_unit_label(df)

    # Aggregate across remaining dimensions to avoid vertical spikes
    has_date = "DATE" in df.columns and df["DATE"].notna().any()
    group_cols = ["DATE" if has_date else "YEAR"]
    if chart_dim_col:
        group_cols.append(chart_dim_col)
    if "GEO" in df.columns and df["GEO"].notna().any() and "GEO" not in group_cols:
        group_cols.append("GEO")

    df = df.groupby(group_cols, as_index=False)["VALUE"].sum()
    if has_date:
        df["YEAR"] = df["DATE"].dt.year

    # KPI metrics
    kpi_rows: list[tuple[str, object, float, float | None]] = []
    time_col = "DATE" if has_date else "YEAR"
    latest_period = df[time_col].max()
    if chart_dim_col:
        grouped = df.sort_values(time_col).groupby(chart_dim_col)
        for series_name, sdf in grouped:
            sdf = sdf.dropna(subset=["VALUE"])
            if sdf.empty:
                continue
            last = sdf.iloc[-1]
            val = float(last["VALUE"])
            if len(sdf) > 1:
                prev = sdf.iloc[-2]["VALUE"]
                change = (val - prev) / prev * 100 if prev else None
            else:
                change = None
            period = last[time_col]
            kpi_rows.append((str(series_name), period, val, change))
    else:
        sdf = df.sort_values(time_col).dropna(subset=["VALUE"])
        if not sdf.empty:
            last = sdf.iloc[-1]
            val = float(last["VALUE"])
            if len(sdf) > 1:
                prev = sdf.iloc[-2]["VALUE"]
                change = (val - prev) / prev * 100 if prev else None
            else:
                change = None
            label = dataset_label if geo_choice is None else f"{dataset_label} — {geo_choice}"
            period = last[time_col]
            kpi_rows.append((label, period, val, change))

    def _period_label(p):
        if isinstance(p, pd.Timestamp):
            return p.date().isoformat()
        try:
            return str(int(p))
        except Exception:
            return str(p)

    if kpi_rows:
        n = min(len(kpi_rows), 6)
        cols = st.columns(n)
        for i, (label, period, val, change) in enumerate(kpi_rows[:n]):
            with cols[i]:
                delta_txt = (
                    f"{change:+.1f}% vs previous period" if change is not None else ""
                )
                cols[i].metric(f"{label} on {_period_label(period)}", f"{val:,.1f}", delta_txt)

    last_period = compute_last_updated_period(df)
    if last_period is not None:
        st.caption(f"Last available period in dataset: {format_last_period(last_period)}")

    # Chart
    y_title = f"{dataset_label}{(' (' + unit_lbl + ')') if unit_lbl else ''}"
    present_labels: list[str] = []
    if chart_dim_col:
        present_labels = sorted(df[chart_dim_col].dropna().unique().tolist())
    elif selected_geos:
        present_labels = selected_geos

    dl_name = build_download_name(
        dataset_label, series_label_for_filename, yr_from, yr_to, present_labels
    )
    alt.renderers.set_embed_options(
        actions={"export": True, "source": False, "compiled": False, "editor": False},
        downloadFileName=dl_name,
    )

    n_periods = df[time_col].nunique()
    one_period_cross_section = chart_dim_col is not None and n_periods == 1

    if one_period_cross_section and chart_dim_col:
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                x=alt.X(f"{chart_dim_col}:N", title="Series"),
                y=alt.Y("VALUE:Q", title=y_title, axis=alt.Axis(format="~s")),
                tooltip=[
                    alt.Tooltip(f"{chart_dim_col}:N", title="Series"),
                    alt.Tooltip("VALUE:Q", title="Value", format=","),
                ],
            )
            .properties(height=420)
            )
    else:
        x_enc = (
            alt.X("DATE:T", title="Date")
            if has_date
            else alt.X("YEAR:O", title="Year", axis=alt.Axis(format="d"))
        )
        tooltip_time = alt.Tooltip(
            "DATE:T", title="Date"
        ) if has_date else alt.Tooltip("YEAR:O", title="Year", format="d")
        if chart_dim_col:
            chart = (
                alt.Chart(df)
                .mark_line(point=True)
                .encode(
                    x=x_enc,
                    y=alt.Y(
                        "VALUE:Q",
                        title=y_title,
                        axis=alt.Axis(format="~s"),
                    ),
                    color=alt.Color(
                        f"{chart_dim_col}:N",
                        title="Series",
                        scale=alt.Scale(scheme="tableau10"),
                    ),
                    tooltip=[
                        tooltip_time,
                        alt.Tooltip(f"{chart_dim_col}:N", title="Series"),
                        alt.Tooltip("VALUE:Q", title="Value", format=","),
                    ],
                )
                .properties(height=420)
                .interactive()
            )
        else:
            tooltip_fields = [
                tooltip_time,
                alt.Tooltip("VALUE:Q", title="Value", format=","),
            ]
            if "GEO" in df.columns:
                tooltip_fields.insert(1, alt.Tooltip("GEO:N", title="Geography"))
            chart = (
                alt.Chart(df)
                .mark_line(point=True)
                .encode(
                    x=x_enc,
                    y=alt.Y(
                        "VALUE:Q",
                        title=y_title,
                        axis=alt.Axis(format="~s"),
                    ),
                    tooltip=tooltip_fields,
                )
                .properties(height=420)
                .interactive()
            )

    chart_tab, data_tab = st.tabs(["Chart", "Data"])

    with chart_tab:
        st.altair_chart(chart, width="stretch")

        file_stem_parts = [table_cfg["id"].replace(" ", "_")]
        selected_series_label = series_label_for_filename
        if selected_series_label:
            file_stem_parts.append(str(selected_series_label).replace(" ", "_"))
        if selected_geos:
            file_stem_parts.append("_".join(g.replace(" ", "_") for g in selected_geos))
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
        if not df.empty:
            st.dataframe(df.head(500))
        else:
            st.info("No data available for the selected filters.")
    if not df.empty:
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        series_piece = safe_slug(series_label_for_filename)
        geo_piece = safe_slug(geo_choice)
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

    st.caption(f"Unit: {unit_lbl if unit_lbl else '—'}")
    render_source_caption(table_cfg)
    _desc = DATASET_DESCRIPTIONS.get(table_id)
    if _desc:
        st.info(f"\U0001f4ca **What this data shows:** {_desc}")

    selected_dataset_id = table_cfg.get("id", table_id)
    if selected_series_list:
        selected_series_for_params = ",".join(map(str, selected_series_list))
    else:
        selected_series_for_params = series_label_for_filename
    selected_geos_for_params = selected_geos
    year_range_for_params = (yr_from, yr_to)

# ============================================================
# DAIRY, POULTRY & EGGS VIEW
# ============================================================

    # Return footer state for URL sharing
    return {
        "selected_dataset_id": locals().get("selected_dataset_id"),
        "selected_series_for_params": locals().get("selected_series_for_params"),
        "selected_geos_for_params": locals().get("selected_geos_for_params", []),
        "year_range_for_params": locals().get("year_range_for_params"),
        "inflation_adjusted_for_params": locals().get("inflation_adjusted_for_params", False),
    }
