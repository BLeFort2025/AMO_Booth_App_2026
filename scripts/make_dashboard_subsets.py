from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_LATEST = ROOT / "data" / "latest"


def load_raw(table_id: str) -> pd.DataFrame:
    """
    Load the full raw StatCan CSV for a given table id from data/latest.
    This expects a file named {table_id}.csv that was written by the main pipeline.
    """
    path = DATA_LATEST / f"{table_id}.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def save_dashboard(df: pd.DataFrame, table_id: str) -> None:
    """
    Save a trimmed, dashboard-friendly CSV under data/latest/{table_id}_dashboard.csv.
    """
    out = DATA_LATEST / (f"{table_id}_dashboard.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Saved {out} with {len(df):,} rows")


def make_32_10_0136_dashboard():
    """
    32-10-0136-01 – Farm operating revenues and expenses.
    Keep:
      - Canada + provinces (GEO)
      - REF_DATE >= 1990
      - All farm types, all revenue classes (if those dimensions exist)
    """
    table_id = "32-10-0136-01"
    df = load_raw(table_id)

    # Filter geography (if GEO exists)
    if "GEO" in df.columns:
        keep_geos = [
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
        ]
        df = df[df["GEO"].isin(keep_geos)].copy()

    # Filter years via REF_DATE if present
    if "REF_DATE" in df.columns:
        # REF_DATE is usually a string like "1990" or "1990-01"
        years = pd.to_numeric(df["REF_DATE"].astype(str).str[:4], errors="coerce")
        df = df[years >= 1990].copy()

    # Dimension filters – only apply if the columns are present
    if "Farm type" in df.columns:
        df = df[df["Farm type"] == "All farm types"].copy()
    if "Revenue class" in df.columns:
        df = df[df["Revenue class"] == "All revenue classes"].copy()

    save_dashboard(df, table_id)


def make_32_10_0213_dashboard():
    """
    32-10-0213-01 – Total income of farm families by source.
    Keep:
      - Canada + provinces
      - REF_DATE >= 1990
      - All revenue classes (if that dimension exists)
    """
    table_id = "32-10-0213-01"
    df = load_raw(table_id)

    if "GEO" in df.columns:
        keep_geos = [
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
        ]
        df = df[df["GEO"].isin(keep_geos)].copy()

    if "REF_DATE" in df.columns:
        years = pd.to_numeric(df["REF_DATE"].astype(str).str[:4], errors="coerce")
        df = df[years >= 1990].copy()

    if "Revenue class" in df.columns:
        df = df[df["Revenue class"] == "All revenue classes"].copy()

    save_dashboard(df, table_id)


def make_12_10_0177_dashboard():
    """
    12-10-0177-01 – Merchandise trade by mode of transport.
    Keep:
      - Canada (if GEO exists)
      - REF_DATE >= 2000
      - A small set of modes of transport
      - Agricultural/food NAPCS codes
      - A curated list of key trading partners to keep file size under 50MB
    """
    import re
    table_id = "12-10-0177-01"
    df = load_raw(table_id)

    if "GEO" in df.columns:
        df = df[df["GEO"] == "Canada"].copy()

    if "REF_DATE" in df.columns:
        years = pd.to_numeric(df["REF_DATE"].astype(str).str[:4], errors="coerce")
        df = df[years >= 2000].copy()

    mode_col = next((c for c in df.columns if c.lower() == "mode of transport"), None)
    if mode_col:
        keep_modes = [
            "Road",
            "Rail",
            "Water",
            "Air",
        ]
        df = df[df[mode_col].isin(keep_modes)].copy()

    napcs_col = next((c for c in df.columns if "napcs" in c.lower() or "product classification" in c.lower()), None)
    if napcs_col:
        allowed_napcs = {
            "C11", "111", "112", "113", "114", "115", "116", "121",
            "171", "172", "173", "181", "182", "183", "191", "192", "193",
            "211", "212"
        }
        def is_agrifood(val):
            if not isinstance(val, str):
                return False
            match = re.search(r'\[([A-Z0-9]+)\]', val)
            if not match:
                return False
            return match.group(1) in allowed_napcs
        df = df[df[napcs_col].apply(is_agrifood)].copy()

    partner_col = next((c for c in df.columns if "trading partner" in c.lower()), None)
    if partner_col:
        keep_partners = [
            "All countries",
            "United States",
            "China",
            "Mexico",
            "United Kingdom",
            "Japan",
            "Other countries"
        ]
        df = df[df[partner_col].isin(keep_partners)].copy()

    save_dashboard(df, table_id)



def make_18_10_0004_dashboard():
    """
    18-10-0004-01 – CPI, monthly, not seasonally adjusted.
    Keep:
      - Canada + provinces
      - REF_DATE >= 1990
      - A curated list of product groups
    """
    table_id = "18-10-0004-01"
    df = load_raw(table_id)

    if "GEO" in df.columns:
        keep_geos = [
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
        ]
        df = df[df["GEO"].isin(keep_geos)].copy()

    if "REF_DATE" in df.columns:
        years = pd.to_numeric(df["REF_DATE"].astype(str).str[:4], errors="coerce")
        df = df[years >= 1990].copy()

    # Product group column name may vary; check the common CPI header name.
    product_col_candidates = [
        "Products and product groups",
        "Products and product groups (CPI)",
        "Product group",
    ]
    product_col = None
    for col in product_col_candidates:
        if col in df.columns:
            product_col = col
            break

    if product_col:
        keep_groups = [
            "All-items",
            "Food",
            "Shelter",
            "Transportation",
            "Energy",
        ]
        df = df[df[product_col].isin(keep_groups)].copy()

    save_dashboard(df, table_id)


def make_36_10_0489_dashboard():
    """
    36-10-0489-01 – Labour statistics by job category and industry (SNA).
    Keep:
      - Canada + provinces
      - REF_DATE >= 1990
      - Industry = 'Agriculture, forestry, fishing and hunting' (if present)
    """
    table_id = "36-10-0489-01"
    df = load_raw(table_id)

    if "GEO" in df.columns:
        keep_geos = [
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
        ]
        df = df[df["GEO"].isin(keep_geos)].copy()

    if "REF_DATE" in df.columns:
        years = pd.to_numeric(df["REF_DATE"].astype(str).str[:4], errors="coerce")
        df = df[years >= 1990].copy()

    # Filter industry (e.g. "North American Industry Classification System (NAICS)")
    ind_col = next((c for c in df.columns if "industry" in c.lower() or "naics" in c.lower()), None)
    if ind_col:
        df = df[df[ind_col].astype(str).str.startswith("Agriculture, forestry, fishing and hunting")].copy()

    save_dashboard(df, table_id)


def main():
    make_32_10_0136_dashboard()
    make_32_10_0213_dashboard()
    make_12_10_0177_dashboard()
    make_18_10_0004_dashboard()
    make_36_10_0489_dashboard()


if __name__ == "__main__":
    main()
