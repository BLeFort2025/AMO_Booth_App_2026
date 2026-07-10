import pandas as pd
from pathlib import Path

# Paths
MULT_FILE = Path("data/latest/io_multipliers_standardized.csv")
HIST_FILE = Path("data/latest/io_supply_use_subset.csv")

def verify():
    print("--- 🔍 DATA INTEGRITY AUDIT ---\n")

    # 1. Load Files
    if not MULT_FILE.exists() or not HIST_FILE.exists():
        print("❌ CRITICAL: One or both data files are missing.")
        return

    df_mult = pd.read_csv(MULT_FILE)
    df_hist = pd.read_csv(HIST_FILE)

    print(f"✅ Loaded Multipliers: {len(df_mult):,} rows")
    print(f"✅ Loaded History:     {len(df_hist):,} rows")

    # 2. Check for join_code
    if "join_code" not in df_mult.columns:
        print("❌ FAIL: 'join_code' missing from Multipliers.")
    if "join_code" not in df_hist.columns:
        print("❌ FAIL: 'join_code' missing from History.")
    
    if "join_code" not in df_mult.columns or "join_code" not in df_hist.columns:
        return

    # 3. Analyze Codes
    mult_codes = set(df_mult["join_code"].dropna().astype(str).unique())
    hist_codes = set(df_hist["join_code"].dropna().astype(str).unique())

    print(f"\n📊 Unique Industry Codes found:")
    print(f"   - Multipliers: {len(mult_codes)}")
    print(f"   - History:     {len(hist_codes)}")

    # 4. Check Overlap (The Moment of Truth)
    overlap = mult_codes.intersection(hist_codes)
    print(f"   - 🔗 MATCHING CODES: {len(overlap)}")

    # 5. Spot Check Specific Targets
    targets = ["111", "111A", "311", "3111", "311A"]
    print("\n🎯 Target Spot Check:")
    for t in targets:
        in_m = "✅" if t in mult_codes else "❌"
        in_h = "✅" if t in hist_codes else "❌"
        status = "READY" if (t in mult_codes and t in hist_codes) else "BROKEN"
        print(f"   Code '{t}': Mult[{in_m}]  Hist[{in_h}] -> {status}")

    # 6. Sample Data
    print("\n📝 Sample History Data (for '111A' or similar):")
    sample = df_hist[df_hist["join_code"].isin(targets)]
    if not sample.empty:
        print(sample[["YEAR", "GEO", "join_code", "value_dollars"]].head())
    else:
        print("   (No data found for targets in history)")

if __name__ == "__main__":
    verify()