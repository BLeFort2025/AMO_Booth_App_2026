"""
Government Finance Data Loader
===============================
Fetches and processes Canadian government finance data from:
  - StatCan Tables 10-10-0147, 10-10-0148, 10-10-0149, 10-10-0020
  - Bank of Canada Valet API (benchmark bond yields)

All functions are designed to be wrapped with @st.cache_data in the page.
"""
from __future__ import annotations

import io
import zipfile
from typing import Optional

import pandas as pd
import requests

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

STATCAN_TABLES = {
    "federal":      "10-10-0149-01",
    "provincial":   "10-10-0148-01",
    "municipal":    "10-10-0020-01",
    "consolidated": "10-10-0147-01",
}

# Bank of Canada benchmark bond yield series IDs
BOC_YIELD_SERIES = {
    "2-Year":  "BD.CDN.2YR.DQ.YLD",
    "5-Year":  "BD.CDN.5YR.DQ.YLD",
    "10-Year": "BD.CDN.10YR.DQ.YLD",
    "Long-Term": "BD.CDN.LONG.DQ.YLD",
}

# Key line-item patterns for KPI extraction
# StatCan CGFS tables use bracket-coded line items, e.g. "Revenue [1]"
# These patterns use case-insensitive substring matching via str.contains
REVENUE_PATTERNS = [
    r"^Revenue \[1\]$",
]
EXPENDITURE_PATTERNS = [
    r"^Expense \[2\]$",
]
SURPLUS_PATTERNS = [
    "net operating balance",
    "net lending",
]
GROSS_DEBT_PATTERNS = [
    r"^Liabilities \[63\]$",
]
NET_DEBT_PATTERNS = [
    "net debt",
    "net worth",
]
DEBT_CHARGES_PATTERNS = [
    r"^Interest expense \[24\]$",
]

# Revenue breakdown categories (using substring matching)
REVENUE_BREAKDOWN_PATTERNS = {
    "Income Taxes": ["Taxes on income, profits"],
    "Goods & Services Taxes": ["Taxes on goods and services"],
    "Property Taxes": ["Taxes on property"],
    "Social Contributions": ["Social contributions"],
    "Payroll & Other Taxes": ["Taxes on payroll"],
    "Grants Revenue": ["Grants, revenue"],
    "Other Revenue": ["Other revenue"],
}

# Expenditure breakdown categories (using substring matching)
EXPENDITURE_BREAKDOWN_PATTERNS = {
    "Compensation": ["Compensation of employees"],
    "Goods & Services": ["Use of goods and services"],
    "Interest Charges": ["Interest expense"],
    "Subsidies": ["Subsidies"],
    "Grants": ["Grants, expense"],
    "Social Benefits": ["Social benefits"],
    "Other Expense": ["Other expense"],
}


# ─────────────────────────────────────────────────────────────────────────────
# STATCAN DATA FETCHER
# ─────────────────────────────────────────────────────────────────────────────

def _csv_zip_url(table_id: str) -> str:
    """Build the StatCan CSV-zip download URL from a table ID."""
    pid = table_id.replace("-", "")
    file_id = pid[:8]
    return f"https://www150.statcan.gc.ca/n1/tbl/csv/{file_id}-eng.zip"


def fetch_statcan_table(table_id: str) -> pd.DataFrame:
    """Download and parse a StatCan table from the CSV-zip endpoint.
    
    Uses streaming download for large government finance tables.
    Returns a cleaned DataFrame with standardized columns.
    """
    url = _csv_zip_url(table_id)
    try:
        r = requests.get(url, timeout=300, verify=False, stream=True)
        r.raise_for_status()
        # Stream into memory for large files
        content = b""
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            content += chunk
    except requests.RequestException as e:
        raise ConnectionError(
            f"Failed to download StatCan table {table_id}: {e}\n"
            f"URL: {url}"
        )

    z = zipfile.ZipFile(io.BytesIO(content))
    csv_names = [n for n in z.namelist() if n.lower().endswith(".csv") and "metadata" not in n.lower()]
    if not csv_names:
        raise ValueError(f"No data CSV found in ZIP for table {table_id}")

    chosen = sorted(csv_names)[0]
    with z.open(chosen) as f:
        df = pd.read_csv(f, low_memory=False)

    return _clean_statcan_df(df)


def _clean_statcan_df(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize StatCan column names and extract year."""
    # Extract year from REF_DATE
    if "REF_DATE" in df.columns:
        df["year"] = pd.to_numeric(
            df["REF_DATE"].astype(str).str[:4], errors="coerce"
        ).astype("Int64")
    elif "Reference period" in df.columns:
        df["year"] = pd.to_numeric(
            df["Reference period"].astype(str).str[:4], errors="coerce"
        ).astype("Int64")

    # Standardize geography
    if "GEO" in df.columns:
        df["geo"] = df["GEO"].str.strip()

    # Standardize the line-item / statement description column
    # StatCan government finance tables use various column names
    line_item_col = None
    for candidate in [
        "Statement of operations and balance sheet",
        "Government finance statistics, statement of operations and balance sheet",
        "Statement of government operations and balance sheet",
        "Government finance statistics",
        "Financial indicator",
    ]:
        if candidate in df.columns:
            line_item_col = candidate
            break

    if line_item_col is None:
        # Fallback: pick the object column with the MOST unique values
        # (avoids grabbing a 2-value sector column over a 139-value line-item column)
        standard = {"REF_DATE", "GEO", "DGUID", "UOM", "UOM_ID", "SCALAR_FACTOR",
                     "SCALAR_ID", "VECTOR", "COORDINATE", "STATUS", "SYMBOL",
                     "TERMINATED", "DECIMALS", "VALUE", "year", "geo",
                     "Reference period"}
        remaining = [c for c in df.columns if c not in standard and df[c].dtype == "object"]
        if remaining:
            line_item_col = max(remaining, key=lambda c: df[c].nunique())

    if line_item_col:
        df["line_item"] = df[line_item_col].astype(str).str.strip()

    # Standardize value column
    if "VALUE" in df.columns:
        df["value"] = pd.to_numeric(df["VALUE"], errors="coerce")
    elif "Value" in df.columns:
        df["value"] = pd.to_numeric(df["Value"], errors="coerce")

    # Keep scalar factor info for unit awareness
    if "SCALAR_FACTOR" in df.columns:
        df["scalar"] = df["SCALAR_FACTOR"].astype(str).str.strip().str.lower()

    return df


def get_gov_finance_data(level: str) -> pd.DataFrame:
    """Fetch government finance data for a specific level.
    
    Args:
        level: One of 'federal', 'provincial', 'municipal', 'consolidated'
    
    Returns:
        Cleaned DataFrame with columns: year, geo, line_item, value, scalar
    """
    table_id = STATCAN_TABLES.get(level.lower())
    if not table_id:
        raise ValueError(f"Unknown government level: {level}. "
                         f"Use one of: {list(STATCAN_TABLES.keys())}")
    return fetch_statcan_table(table_id)


# ─────────────────────────────────────────────────────────────────────────────
# BANK OF CANADA BOND YIELDS
# ─────────────────────────────────────────────────────────────────────────────

BOC_VALET_BASE = "https://www.bankofcanada.ca/valet/observations"


def fetch_boc_yields(start_date: str = "2000-01-01") -> pd.DataFrame:
    """Fetch benchmark Government of Canada bond yields from Bank of Canada.
    
    Returns DataFrame with columns: date, series, yield_pct
    """
    all_rows = []

    for label, series_id in BOC_YIELD_SERIES.items():
        url = f"{BOC_VALET_BASE}/{series_id}/json"
        params = {"start_date": start_date}
        try:
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
        except Exception:
            continue

        observations = data.get("observations", [])
        for obs in observations:
            val = obs.get(series_id, {}).get("v")
            if val is not None:
                try:
                    all_rows.append({
                        "date": pd.to_datetime(obs["d"]),
                        "series": label,
                        "yield_pct": float(val),
                    })
                except (ValueError, KeyError):
                    continue

    if not all_rows:
        return pd.DataFrame(columns=["date", "series", "yield_pct"])

    df = pd.DataFrame(all_rows)
    df["year"] = df["date"].dt.year
    return df


def get_annual_yields(start_date: str = "2000-01-01") -> pd.DataFrame:
    """Get annual average bond yields by series.
    
    Returns DataFrame with columns: year, series, yield_pct
    """
    daily = fetch_boc_yields(start_date)
    if daily.empty:
        return pd.DataFrame(columns=["year", "series", "yield_pct"])

    annual = daily.groupby(["year", "series"], as_index=False)["yield_pct"].mean()
    annual["yield_pct"] = annual["yield_pct"].round(2)
    return annual


# ─────────────────────────────────────────────────────────────────────────────
# GDP DATA (for debt-to-GDP and deficit-to-GDP ratios)
# ─────────────────────────────────────────────────────────────────────────────

GDP_TABLE_ID = "36-10-0222-01"


def fetch_gdp_data() -> pd.DataFrame:
    """Fetch nominal GDP at market prices by province from StatCan.
    
    Uses table 36-10-0222-01 (GDP, expenditure-based).
    Returns DataFrame with columns: year, geo, gdp (in dollars, not millions)
    """
    df = fetch_statcan_table(GDP_TABLE_ID)

    # Filter to current prices and GDP at market prices
    prices_col = "Prices" if "Prices" in df.columns else None
    estimates_col = "Estimates" if "Estimates" in df.columns else None

    if prices_col:
        df = df[df[prices_col].str.contains("Current prices", case=False, na=False)]
    if estimates_col:
        df = df[df[estimates_col].str.contains("Gross domestic product at market prices", case=False, na=False)]

    if df.empty:
        return pd.DataFrame(columns=["year", "geo", "gdp"])

    result = df[["year", "geo", "value", "scalar"]].dropna(subset=["value"]).copy()

    # Apply scalar (values are in millions)
    def _apply_scalar(row):
        v = row["value"]
        s = str(row.get("scalar", "")).lower()
        if "million" in s:
            return v * 1_000_000
        if "thousand" in s:
            return v * 1_000
        if "billion" in s:
            return v * 1_000_000_000
        return v

    result["gdp"] = result.apply(_apply_scalar, axis=1)
    result = result.groupby(["year", "geo"], as_index=False)["gdp"].sum()
    return result.sort_values(["geo", "year"])



# KPI EXTRACTION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _match_line_item(df: pd.DataFrame, patterns: list[str]) -> pd.DataFrame:
    """Filter DataFrame rows where line_item matches any of the patterns.
    Supports both regex patterns (starting with ^) and plain substring matching.
    """
    if df.empty or "line_item" not in df.columns:
        return pd.DataFrame()

    mask = pd.Series(False, index=df.index)
    for pat in patterns:
        if pat.startswith("^"):
            # Regex match
            mask |= df["line_item"].str.match(pat, case=False, na=False)
        else:
            # Substring match
            mask |= df["line_item"].str.contains(pat, case=False, na=False, regex=False)
    return df[mask]


def extract_kpi(df: pd.DataFrame, patterns: list[str],
                geo: Optional[str] = None,
                year: Optional[int] = None) -> float:
    """Extract a single KPI value from the DataFrame.
    
    Filters by line_item patterns, geo, and year. Returns the first
    matching value (preferring the most specific line item).
    """
    filtered = df.copy()

    if geo and "geo" in filtered.columns:
        filtered = filtered[filtered["geo"] == geo]

    if year and "year" in filtered.columns:
        filtered = filtered[filtered["year"] == year]

    matched = _match_line_item(filtered, patterns)
    if matched.empty or "value" not in matched.columns:
        return 0.0

    # Drop NaN values
    matched = matched.dropna(subset=["value"])
    if matched.empty:
        return 0.0

    # Prefer the most specific match (shortest line_item name often = top-level)
    matched = matched.sort_values("line_item", key=lambda s: s.str.len())
    val = matched.iloc[0]["value"]

    # Apply scalar factor (StatCan reports in millions)
    scalar = matched.iloc[0].get("scalar", "")
    if "million" in str(scalar).lower():
        val *= 1_000_000
    elif "thousand" in str(scalar).lower():
        val *= 1_000
    elif "billion" in str(scalar).lower():
        val *= 1_000_000_000

    return float(val)


def extract_time_series(df: pd.DataFrame, patterns: list[str],
                        geo: Optional[str] = None) -> pd.DataFrame:
    """Extract a time series for a set of line-item patterns.
    
    Returns DataFrame with columns: year, value
    """
    filtered = df.copy()
    if geo and "geo" in filtered.columns:
        filtered = filtered[filtered["geo"] == geo]

    matched = _match_line_item(filtered, patterns)
    if matched.empty:
        return pd.DataFrame(columns=["year", "value"])

    # Pick the most common/shortest line item name for consistency
    top_item = matched["line_item"].value_counts().idxmax()
    series = matched[matched["line_item"] == top_item].copy()

    # Apply scalar
    def _apply_scalar(row):
        v = row["value"]
        s = str(row.get("scalar", "")).lower()
        if "million" in s:
            return v * 1_000_000
        if "thousand" in s:
            return v * 1_000
        if "billion" in s:
            return v * 1_000_000_000
        return v

    series["value"] = series.apply(_apply_scalar, axis=1)
    result = series.groupby("year", as_index=False)["value"].sum()
    return result.sort_values("year")


def extract_breakdown(df: pd.DataFrame, category_patterns: dict,
                      geo: Optional[str] = None,
                      year: Optional[int] = None) -> pd.DataFrame:
    """Extract a breakdown of values by category for stacked charts.
    
    Args:
        category_patterns: Dict mapping category labels to lists of patterns
    
    Returns DataFrame with columns: year, category, value
    """
    filtered = df.copy()
    if geo and "geo" in filtered.columns:
        filtered = filtered[filtered["geo"] == geo]
    if year and "year" in filtered.columns:
        filtered = filtered[filtered["year"] == year]

    rows = []
    for category, patterns in category_patterns.items():
        matched = _match_line_item(filtered, patterns)
        if matched.empty:
            continue

        # Apply scalar and sum by year
        def _apply_scalar(row):
            v = row["value"]
            s = str(row.get("scalar", "")).lower()
            if "million" in s:
                return v * 1_000_000
            if "thousand" in s:
                return v * 1_000
            if "billion" in s:
                return v * 1_000_000_000
            return v

        matched = matched.dropna(subset=["value"]).copy()
        if matched.empty:
            continue

        matched["value"] = matched.apply(_apply_scalar, axis=1)

        for yr, grp in matched.groupby("year"):
            rows.append({
                "year": yr,
                "category": category,
                "value": grp["value"].sum(),
            })

    if not rows:
        return pd.DataFrame(columns=["year", "category", "value"])

    return pd.DataFrame(rows).sort_values(["year", "category"])


# ─────────────────────────────────────────────────────────────────────────────
# GEOGRAPHY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

PROVINCES = [
    "Canada",
    "Newfoundland and Labrador",
    "Prince Edward Island",
    "Nova Scotia",
    "New Brunswick",
    "Quebec",
    "Ontario",
    "Manitoba",
    "Saskatchewan",
    "Alberta",
    "British Columbia",
    "Yukon",
    "Northwest Territories",
    "Nunavut",
]


def get_available_geos(df: pd.DataFrame) -> list[str]:
    """Get list of available geographies from the data."""
    if "geo" not in df.columns:
        return ["Canada"]
    geos = df["geo"].dropna().unique().tolist()
    # Sort with Canada first, then alphabetical
    ordered = []
    for p in PROVINCES:
        matches = [g for g in geos if p.lower() in g.lower()]
        ordered.extend(matches)
    # Add any remaining
    remaining = [g for g in geos if g not in ordered]
    return ordered + sorted(remaining)


def get_available_years(df: pd.DataFrame) -> tuple[int, int]:
    """Get min and max available years."""
    if "year" not in df.columns or df["year"].isna().all():
        return 2000, 2023
    valid = df["year"].dropna()
    return int(valid.min()), int(valid.max())
