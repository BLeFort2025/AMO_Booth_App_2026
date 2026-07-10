from __future__ import annotations
import sys
from pathlib import Path
import re
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))
from scripts.fetch_statcan import ensure_year_column

DATA_LATEST = Path("data/latest")
TBL_MULT_NATIONAL = "36-10-0594-01"
TBL_MULT_PROV_TERR = "36-10-0595-01"
TBL_SUT_DETAIL = "36-10-0478-01"
OUT_MULT_STD = DATA_LATEST / "io_multipliers_standardized.csv.gz"
OUT_INDUSTRY_LOOKUP = DATA_LATEST / "io_industry_lookup.csv"
OUT_SUT_SUBSET = DATA_LATEST / "io_supply_use_subset.csv"
KEEP_MULTIPLIER_TYPES = {"Direct multiplier", "Simple multiplier", "Total multiplier"}

def normalize_code(code: str) -> str:
    if pd.isna(code) or code == "": return ""
    s = str(code).upper().strip()
    for prefix in ["BS", "GS", "NP"]: s = s.replace(prefix, "")
    return s.rstrip("0")

def parse_bracket_code(text: str) -> tuple[str, str]:
    if not isinstance(text, str): return "", str(text)
    match = re.search(r"\[(.*?)\]", text)
    if match:
        code = match.group(1)
        name = text.replace(f"[{code}]", "").strip()
        return code, name
    return "", text.strip()

def process_multipliers(df_nat: pd.DataFrame, df_pt: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    # (Standard multiplier logic - unchanged)
    df_nat = ensure_year_column(df_nat)
    df_pt = ensure_year_column(df_pt)
    col_map = {
        "Geography": "GEO", 
        "Multiplier type": "multiplier_type", 
        "Multiplier": "multiplier_type",
        "Variable": "variable",      # <-- ADDED
        "Variables": "variable",     # <-- ADDED
        "Value": "value", 
        "VALUE": "value", 
        "SCALAR_FACTOR": "scalar"
    }
    for df in [df_nat, df_pt]:
        df.rename(columns={k:v for k,v in col_map.items() if k in df.columns}, inplace=True)
        if "Geography" in df.columns and "GEO" not in df.columns: df["GEO"] = df["Geography"]
    if "GEO" in df_pt.columns: df_pt = df_pt[df_pt["GEO"] != "Canada"]
    df = pd.concat([df_nat, df_pt], ignore_index=True)
    
    ind_col = "Industry" if "Industry" in df.columns else "Input-output industry classification (IOIC)"
    if ind_col in df.columns:
        parsed = df[ind_col].apply(parse_bracket_code)
        df["industry_code"] = parsed.apply(lambda x: x[0])
        df["industry_name"] = parsed.apply(lambda x: x[1])
        df["join_code"] = df["industry_code"].apply(normalize_code)
    
    name_map = {}
    if "industry_name" in df.columns and "industry_code" in df.columns:
        subset = df[["industry_name", "industry_code"]].drop_duplicates()
        name_map = dict(zip(subset["industry_name"], subset["industry_code"]))
        
    cols = ["YEAR", "GEO", "industry_code", "join_code", "industry_name", "multiplier_type", "variable", "value"]

    # --- NEW: THE PERMANENT GHOSTBUSTER FIX ---
    # Drop rows where 'value' is NaN/Empty before saving to disk.
    df_clean = df[[c for c in cols if c in df.columns]].copy()
    initial_len = len(df_clean)
    df_clean = df_clean.dropna(subset=["value"])
    print(f"   > Removed {initial_len - len(df_clean)} ghost rows (NaN values).")

    return df_clean, name_map

def process_supply_use(df: pd.DataFrame, industry_name_map: dict) -> pd.DataFrame:
    print("   > Filtering Supply Use Table (Matrix Logic)...")
    df = ensure_year_column(df)
    
    # Standardize Columns
    col_map = {
        "Supply and use": "supply_use", "Valuation": "valuation", "VALUE": "value",
        "SCALAR_FACTOR": "scalar", "Industry": "Industry_Raw", 
        "Product": "Product_Raw", "Geography": "GEO"
    }
    df.rename(columns={k:v for k,v in col_map.items() if k in df.columns}, inplace=True)
    if "Geography" in df.columns and "GEO" not in df.columns: df["GEO"] = df["Geography"]

    # --- THE FIX: MATRIX COORDINATE MATCHING ---
    # We want: Supply AND Basic Price AND Total Products
    mask_output = (
        (df["supply_use"] == "Supply") &
        (df["valuation"] == "Basic price") &
        (df["Product_Raw"].str.contains("Total products", na=False))
    )
    
    # Just in case, keep GDP if we stumble on it (usually in Use table, but rare in this specific file structure)
    mask_gdp = df["Industry_Raw"].str.contains("Gross domestic product", case=False, na=False)
    
    df_filtered = df[mask_output | mask_gdp].copy()
    print(f"   > Rows matching Output Criteria: {len(df_filtered)}")

    # Assign Variable Name
    df_filtered["variable"] = "Output" # Default
    df_filtered.loc[mask_gdp, "variable"] = "GDP"

    # Parse Industry Codes (BS Codes)
    def get_code(row):
        raw_text = row.get("Industry_Raw", "")
        c, n = parse_bracket_code(raw_text)
        if c: return c, n
        stripped = raw_text.strip()
        return (industry_name_map.get(stripped, ""), stripped)

    parsed = df_filtered.apply(get_code, axis=1)
    df_filtered["io_code"] = parsed.apply(lambda x: x[0])
    df_filtered["io_name"] = parsed.apply(lambda x: x[1])
    
    # Normalize
    df_filtered = df_filtered[df_filtered["io_code"] != ""]
    df_filtered["join_code"] = df_filtered["io_code"].apply(normalize_code)
    
    # Calculate Value
    def scalar_to_float(s):
        s = str(s).lower()
        if "million" in s: return 1_000_000.0
        if "thousand" in s: return 1_000.0
        return 1.0
    
    df_filtered["VALUE"] = df_filtered["value"] * df_filtered["scalar"].apply(scalar_to_float)
    
    # Keep relevant columns
    cols = ["YEAR", "GEO", "join_code", "variable", "VALUE"]
    return df_filtered[cols]

def run():
    print("--- Starting IO Multipliers Transform (Matrix Fix) ---")
    try:
        p_nat = DATA_LATEST / f"{TBL_MULT_NATIONAL.replace('-','')}.csv"
        p_pt = DATA_LATEST / f"{TBL_MULT_PROV_TERR.replace('-','')}.csv"
        
        ind_map = {}
        if p_nat.exists():
            print("Processing Multipliers...")
            df_nat = pd.read_csv(p_nat, low_memory=False)
            df_pt = pd.read_csv(p_pt, low_memory=False) if p_pt.exists() else pd.DataFrame()
            mult_std, ind_map = process_multipliers(df_nat, df_pt)
            mult_std.to_csv(OUT_MULT_STD, index=False, compression='gzip')

        # Load SUT
        p_sut = DATA_LATEST / f"{TBL_SUT_DETAIL.replace('-','')}.csv"
        if p_sut.exists():
            print("Processing Supply Use Table...")
            df_sut = pd.read_csv(p_sut, low_memory=False)
            sut_subset = process_supply_use(df_sut, ind_map)
            sut_subset.to_csv(OUT_SUT_SUBSET, index=False)
            print(f"[OK] Saved {OUT_SUT_SUBSET} ({len(sut_subset)} rows)")
        else:
            print(f"[ERROR] Supply Use File not found: {p_sut}")
            
    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")

if __name__ == "__main__":
    run()