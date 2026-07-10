from __future__ import annotations

import pandas as pd


def get_unit_label(df: pd.DataFrame) -> str:
    """
    Build a compact unit label from UOM/SCALAR_FACTOR or a UNIT column.

    Examples:
      - UOM='Dollars', SCALAR_FACTOR='thousands' -> 'Dollars (× 1,000)'
      - UOM='Dollars', SCALAR_FACTOR='millions'  -> 'Dollars (× 1,000,000)'
      - UOM='Index, 2016=100', SCALAR_FACTOR='units' -> 'Index, 2016=100'
      - UNIT='$/bu' -> '$/bu'
    """
    uom = None
    scalar = None

    column_lookup = {col.lower(): col for col in df.columns}

    def _mode_for_col(col_name: str) -> str | None:
        series = df[col_name]
        if series.notna().any():
            return series.dropna().astype(str).mode().iloc[0]
        return None

    for possible in ["uom", "unit of measure"]:
        if possible in column_lookup:
            uom = _mode_for_col(column_lookup[possible])
            if uom:
                break

    if "scalar_factor" in column_lookup:
        scalar = _mode_for_col(column_lookup["scalar_factor"])

    if uom or scalar:
        if scalar:
            scalar_lower = scalar.lower()
            scale_map = {
                "thousands": "× 1,000",
                "millions": "× 1,000,000",
                "billions": "× 1,000,000,000",
            }
            if scalar_lower == "units":
                return uom or ""

            if uom and scalar_lower in scale_map:
                return f"{uom} ({scale_map[scalar_lower]})"

            if uom:
                return f"{uom}, {scalar}"

            return scalar

        return uom or ""

    if "unit" in column_lookup:
        unit_value = _mode_for_col(column_lookup["unit"])
        if unit_value:
            return unit_value

    return ""


def supports_inflation_adjustment(df: pd.DataFrame, table_cfg: dict | None = None) -> bool:
    """
    Determine whether a dataset supports CPI deflation based on dollar-denominated UOMs.

    Returns True if any unit of measure in the data appears to be dollar-based
    (e.g., contains "dollar" or "$"), ignoring index, percent, or count-style units.
    """

    def _is_dollar_uom(uom: str) -> bool:
        text = str(uom).lower()
        if not text.strip():
            return False
        if any(term in text for term in ["index", "%", "percent", "percentage", "ratio", "count", "number"]):
            return False
        return "dollar" in text or "$" in text

    uom_values: list[str] = []
    for col in ["UOM", "Unit of measure", "UNIT"]:
        if col in df.columns:
            uom_values.extend(df[col].dropna().astype(str).unique().tolist())

    unit_label = get_unit_label(df)
    if unit_label:
        uom_values.append(unit_label)

    return any(_is_dollar_uom(uom) for uom in uom_values)
