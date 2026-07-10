import pandas as pd
from pathlib import Path
import sys

# --- PATH SETUP ---
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "latest" / "io_multipliers_standardized.csv.gz"

print(f"📂 Loading data from: {DATA_PATH}")

if not DATA_PATH.exists():
    print(f"❌ CRITICAL ERROR: File not found at {DATA_PATH}")
    sys.exit(1)

# Load data
try:
    df = pd.read_csv(DATA_PATH)
except Exception as e:
    alt_path = DATA_PATH.with_suffix("") 
    if alt_path.exists():
        print(f"⚠️ .gz not found, trying .csv: {alt_path}")
        df = pd.read_csv(alt_path)
    else:
        raise e

# --- THE FIX: IGNORE ZEROS ---
# We only care about overlaps if they have ECONOMIC VALUE.
# If a row is 0.0 or NaN, it's just a placeholder and doesn't count as a "Double Count."
df = df[df['value'].fillna(0) != 0]

# Filter for the suspicious codes
suspects = ["1114", "111400", "BS111400", "1114A", "1114A0", "BS1114A0"]
mask = df['join_code'].astype(str).isin(suspects)
df_sus = df[mask].copy()

if df_sus.empty:
    print("ℹ️ No non-zero Greenhouse codes found in the file.")
    sys.exit(0)

# Group by Year and count how many unique codes exist per year
overlap_check = df_sus.groupby('YEAR')['join_code'].nunique()

print("\n--- 🕵️ GREENHOUSE CODE AUDIT (Ignoring Zeros) ---")
print(overlap_check)

if overlap_check.max() > 1:
    print("\n⚠️ WARNING: REAL OVERLAP DETECTED! We have both codes with $$$ in the same year.")
    print(df_sus[df_sus['YEAR'] == overlap_check.idxmax()][['YEAR', 'join_code', 'value']].head())
else:
    print("\n✅ CERTIFIED CLEAN: No conflicting non-zero values found.")