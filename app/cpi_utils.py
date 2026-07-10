from __future__ import annotations

from typing import Any, Mapping
from pathlib import Path

import pandas as pd
import streamlit as st

from app.smart_read import smart_read
from app.analytics import AnalyticsOptions
from scripts import config_loader


def ensure_year_column(df: pd.DataFrame) -> pd.DataFrame:
    if "YEAR" in df.columns:
        return df

    if "Year" in df.columns:
        return df.rename(columns={"Year": "YEAR"})

    if "REF_DATE" in df.columns:
        ref = df["REF_DATE"]
        if pd.api.types.is_numeric_dtype(ref):
            year_vals = pd.to_numeric(ref, errors="coerce")
        else:
            year_vals = pd.to_datetime(ref.astype(str), errors="coerce").dt.year
        return df.assign(YEAR=year_vals)

    return df


def _get_param_local(params_obj, key: str, default=None):
    if not params_obj:
        return default

    try:
        value = params_obj[key]
    except Exception:
        value = params_obj.get(key, None)

    if value is None:
        return default

    if isinstance(value, str):
        return value

    if isinstance(value, (list, tuple)):
        if not value:
            return default
        return value[0]

    return str(value)


def detect_dollar_series(chart_df: pd.DataFrame, unit_lbl: str | None) -> bool:
    is_dollar_series = False
    for col in ["UOM", "Unit of measure", "UNIT"]:
        if col in chart_df.columns:
            if chart_df[col].astype(str).str.contains(r"dollar|\$", case=False, regex=True).any():
                is_dollar_series = True
                break
    if not is_dollar_series and unit_lbl:
        lowered_unit = str(unit_lbl).lower()
        if "dollar" in lowered_unit or "$" in lowered_unit:
            is_dollar_series = True
    return is_dollar_series


@st.cache_data(max_entries=5, show_spinner=False)
def load_cpi_deflators(
    geo: str | None = "Canada",
    return_geo: bool = False,
    *,
    table_config: Mapping[str, Any] | list[Mapping[str, Any]] | None = None,
    _load_table_fn=None,
):
    """
    Fetch and cache the Annual CPI table.
    """
    # Safety return object to prevent KeyErrors downstream
    EMPTY_RET = pd.DataFrame(columns=["YEAR", "cpi", "GEO"])

    # Fallback to local import if function not passed
    if _load_table_fn is None:
        try:
            from scripts.fetch_statcan import fetch_table
            _load_table_fn = fetch_table
        except ImportError:
            return EMPTY_RET

    try:
        cfg = table_config or config_loader.load_tables(active_only=True)
        tables = cfg["tables"] if isinstance(cfg, dict) and "tables" in cfg else cfg
        
        # Robust config lookup
        cpi_cfg = next((t for t in tables if t.get("id") == "18-10-0005-01"), None)
        if not cpi_cfg:
            cpi_cfg = {"id": "18-10-0005-01"}

        cpi_table_id = cpi_cfg["id"]

        # --- Robust loader: handles multiple _load_table_fn signatures ---
        cpi_df = None

        def _try_load(fn, arg):
            """Call fn(arg), handle both tuple (df, hash) and plain df returns."""
            result = fn(arg)
            if isinstance(result, tuple):
                return result[0]
            return result

        if _load_table_fn is not None:
            # Try passing the table ID string directly (matches fetch_table signature)
            try:
                cpi_df = _try_load(_load_table_fn, cpi_table_id)
            except Exception:
                pass

        # Try 3: fallback — load directly from local CSV or live fetch
        if cpi_df is None or (hasattr(cpi_df, 'empty') and cpi_df.empty):
            local_path = Path("data/latest") / f"{cpi_table_id}.csv"
            if local_path.exists():
                cpi_df = smart_read(local_path)
            else:
                try:
                    from scripts.fetch_statcan import fetch_table as _fetch_live
                    cpi_df, _ = _fetch_live(cpi_table_id)
                except Exception:
                    return EMPTY_RET

        if cpi_df is None or cpi_df.empty:
            return EMPTY_RET

        normalized = cpi_df.copy()
        if "SERIES" not in normalized.columns and "Products and product groups" in normalized.columns:
            normalized = normalized.rename(columns={"Products and product groups": "SERIES"})

        normalized = ensure_year_column(normalized)

        # Filter Series
        series_col = "SERIES" if "SERIES" in normalized.columns else None
        if series_col:
            all_items_mask = normalized[series_col].astype(str).str.contains(
                "all-items", case=False, na=False
            )
            if all_items_mask.any():
                normalized = normalized[all_items_mask]

        # Filter Geo
        used_geo: str | None = geo
        if "GEO" in normalized.columns and geo:
            geo_lower = str(geo).lower()
            geo_matches = normalized[normalized["GEO"].astype(str).str.lower() == geo_lower]
            if geo_matches.empty and geo_lower != "canada":
                canada_matches = normalized[
                    normalized["GEO"].astype(str).str.lower() == "canada"
                ]
                if not canada_matches.empty:
                    geo_matches = canada_matches
                    used_geo = "Canada"
            if not geo_matches.empty:
                normalized = geo_matches

        if "VALUE" in normalized.columns:
            normalized["VALUE"] = pd.to_numeric(normalized["VALUE"], errors="coerce")

        normalized = normalized.dropna(subset=["YEAR", "VALUE"]).copy()
        normalized["YEAR"] = pd.to_numeric(normalized["YEAR"], errors="coerce")
        normalized = normalized.dropna(subset=["YEAR", "VALUE"]).copy()
        normalized["YEAR"] = normalized["YEAR"].astype(int)
        normalized["cpi"] = pd.to_numeric(normalized["VALUE"], errors="coerce")

        if "GEO" in normalized.columns:
            tidy_cols = normalized[["YEAR", "cpi", "GEO"]].drop_duplicates().sort_values("YEAR")
        else:
            tidy_cols = normalized[["YEAR", "cpi"]].drop_duplicates().sort_values("YEAR")
            if used_geo:
                tidy_cols["GEO"] = used_geo

        if return_geo:
            return tidy_cols, used_geo
        return tidy_cols

    except Exception:
        # On any failure (including signature mismatch), return empty safe DF
        return EMPTY_RET


def apply_cpi_adjustment(
    chart_df: pd.DataFrame,
    params_obj: Mapping[str, str],
    dataset_label: str,
    unit_lbl: str | None,
    checkbox_key: str,
    value_col: str = "VALUE",
    time_col: str = "YEAR",
    table_cfg: Mapping[str, Any] | None = None,
    table_id: str | None = None,
    cpi_geo: str | None = "Canada",
    inflation_label: str | None = None,
    inflation_help: str | None = None,
    warn_on_cpi_failure: bool = False,
    *,
    table_config: Mapping[str, Any] | list[Mapping[str, Any]] | None = None,
    _load_table_fn=None,
) -> tuple[pd.DataFrame, str, bool, bool, int | None, str | None, bool]:
    is_dollar_series = detect_dollar_series(chart_df, unit_lbl)

    table_id_from_cfg = None
    if isinstance(table_cfg, Mapping):
        table_id_from_cfg = table_cfg.get("id") or table_cfg.get("table_id")
    table_id = table_id or table_id_from_cfg or _get_param_local(params_obj, "table_id", None)

    inflation_param = _get_param_local(params_obj, "inflation", "nominal")
    inflation_checked = False

    dollar_like_units = unit_lbl.lower() if unit_lbl else ""
    is_ratio_or_index = any(term in dollar_like_units for term in ["%", "percent", "ratio", "index"])

    omafra_price_table_ids = {
        "omafra-average-weekly-corn-prices",
        "omafra-average-weekly-soybean-prices",
        "omafra-average-weekly-wheat-prices",
        "omafra-average-weekly-hog-prices",
        "omafra-average-weekly-cattle-prices",
    }

    supports_inflation = is_dollar_series and not is_ratio_or_index
    if table_id:
        if str(table_id) == "18-10-0005-01":
            supports_inflation = False
        elif str(table_id) in omafra_price_table_ids:
            supports_inflation = supports_inflation or is_dollar_series
    value_col_for_chart = value_col
    inflation_applied = False
    base_year: int | None = None
    inflation_note: str | None = None

    series_years_full = pd.to_numeric(chart_df[time_col], errors="coerce")
    series_years = series_years_full.dropna().astype(int)
    if not series_years.empty:
        base_year = int(series_years.max())

    # FORCE Canada for robust inflation adjustment
    inflation_label = inflation_label or "Adjust for inflation (CPI, Canada)"
    help_base_year = base_year if base_year is not None else "the latest year in the data"
    inflation_help = inflation_help or (
        "Uses CPI all-items, Canada, annual average (StatCan table 18-10-0005-01). "
        f"Adjusts by calendar year; base year = {help_base_year}."
    )

    cpi = None
    cpi_geo_used = "Canada" # Force Canada
    cpi_available = False
    cpi_error: str | None = None
    if is_dollar_series:
        try:
            # FORCE GEO="Canada" here to prevent missing provincial data issues
            cpi_result = load_cpi_deflators(
                geo="Canada",
                return_geo=True,
                table_config=table_config,
                _load_table_fn=_load_table_fn,
            )
            if isinstance(cpi_result, tuple):
                cpi, _ = cpi_result
            else:
                cpi = cpi_result
        except Exception as exc:
            cpi = None
            cpi_error = str(exc)

    if cpi is not None and base_year is not None:
        if not cpi.empty:
            # FALLBACK: If base_year (e.g. 2024) is missing in CPI (ends 2023), use max available
            if base_year not in cpi["YEAR"].values:
                max_cpi = int(cpi["YEAR"].max())
                if max_cpi > 0: 
                    base_year = max_cpi
            
            if base_year in cpi["YEAR"].values:
                cpi_available = True
            elif cpi_error is None:
                cpi_error = f"CPI data missing base year {base_year}."
        elif cpi_error is None:
             cpi_error = "CPI data is empty."

    elif cpi is None and cpi_error is None and is_dollar_series:
        cpi_error = "CPI data unavailable for inflation adjustment."

    if supports_inflation:
        inflation_checked = st.sidebar.checkbox(
            inflation_label,
            value=inflation_param == "real",
            help=inflation_help,
            key=checkbox_key,
            disabled=not cpi_available,
        )

    if not cpi_available:
        inflation_checked = False

    if warn_on_cpi_failure and supports_inflation and not cpi_available and cpi_error:
        st.sidebar.warning(cpi_error)

    if cpi_available and cpi is not None:
        base_val_series = cpi.loc[cpi["YEAR"] == base_year, "cpi"]
        if not base_val_series.empty:
            base_cpi = float(base_val_series.iloc[0])
            cpi = cpi.assign(deflator=base_cpi / cpi["cpi"])
            cpi_for_merge = cpi.rename(columns={"YEAR": "CPI_YEAR"})
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

    if inflation_applied and base_year is not None:
        geo_label = "Canada"
        inflation_note = (
            "Values adjusted for inflation using CPI all-items, "
            f"{geo_label}, annual average (StatCan table 18-10-0005-01); "
            f"constant {base_year} dollars."
        )

    return (
        chart_df,
        value_col_for_chart,
        inflation_applied,
        inflation_checked,
        base_year,
        inflation_note,
        is_dollar_series,
    )