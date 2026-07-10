import pandas as pd
import requests, zipfile, io
from pathlib import Path
import re

# Config
DETAIL_TABLE_ID = "36100478"
URL = f"https://www150.statcan.gc.ca/n1/tbl/csv/{DETAIL_TABLE_ID}-eng.zip"
RAW_DIR = Path("data/latest")
OUT_FILE = RAW_DIR / "io_supply_use_subset.csv"

def parse_bracket_code(text):
    if not isinstance(text, str): return "", str(text)
    match = re.search(r"\[(.*?)\]", text)
    if match: return match.group(1), text.replace(f"[{match.group(1)}]", "").strip()
    return "", text.strip()

def normalize_code(code: str) -> str:
    s = str(code).upper().strip()
    for prefix in ["BS", "GS", "NP"]:
        s = s.replace(prefix, "")
    return s.rstrip("0")

def scalar_to_float(s):
    s = str(s).lower()
    if "million" in s: return 1_000_000.0
    if "thousand" in s: return 1_000.0
    return 1.0

def run():
    print(f"🚀 Downloading Detailed Supply-Use Table ({DETAIL_TABLE_ID})...")
    try:
        r = requests.get(URL)
        r.raise_for_status()
        
        print("📦 Extracting...")
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            csv_name = f"{DETAIL_TABLE_ID}.csv"
            with z.open(csv_name) as f:
                print("📖 Reading CSV (this may take a moment)...")
                df = pd.read_csv(f, low_memory=False)
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return

    print(f"✅ Loaded {len(df):,} rows.")
    print("⚙️ Processing...")
    
    # 1. Clean Cols
    df.rename(columns={
        "REF_DATE": "YEAR", 
        "GEO": "GEO", 
        "Supply and use": "supply_use", 
        "Valuation": "valuation", 
        "VALUE": "value", 
        "SCALAR_FACTOR": "scalar",
        "Industry": "Industry_Raw",
        "Product": "Product_Raw"
    }, inplace=True)
    
    # 2. Filter: Supply + Basic Price + TOTAL PRODUCTS ONLY
    # This effectively grabs the 'Footer' of the receipt, ensuring 100% accuracy with no double counting.
    mask = (
        df["supply_use"].isin(["Supply", "Output", "Production", "Total supply"]) & 
        (df["valuation"].astype(str).str.startswith("Basic price")) &
        (df["Product_Raw"].astype(str).str.contains("Total products", case=False, na=False))
    )
    df = df[mask].copy()
    print(f"   Filtered to {len(df):,} Industry Total rows.")

    # 3. Parse Industry Codes
    parsed = df["Industry_Raw"].apply(parse_bracket_code)
    df["io_code"] = parsed.apply(lambda x: x[0])
    df["io_name"] = parsed.apply(lambda x: x[1])
    
    # 4. Create Join Code
    df["join_code"] = df["io_code"].apply(normalize_code)
    
    # 5. Convert to Dollars
    df["mult"] = df["scalar"].apply(scalar_to_float)
    df["value_dollars"] = df["value"] * df["mult"]
    
    # 6. Aggregate
    # (Should be redundant now as we filtered to Unique Totals, but good for safety)
    agg = df.groupby(["YEAR", "GEO", "io_code", "join_code", "io_name"], as_index=False)["value_dollars"].sum()
    
    # Save
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    agg.to_csv(OUT_FILE, index=False)
    print(f"🎉 Saved {OUT_FILE} with {len(agg):,} records.")

if __name__ == "__main__":
    run()