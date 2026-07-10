import pandas as pd
from pathlib import Path

# Paths to the raw files downloaded by fetch_all_raw.py
FILES = [
    Path("data/latest/3610059401.csv"), # National Multipliers
    Path("data/latest/3610059501.csv")  # Provincial Multipliers
]

def inspect():
    print("--- INSPECTING RAW MULTIPLIER HEADERS ---\n")
    for p in FILES:
        print(f"📄 Checking: {p.name}")
        if not p.exists():
            print("   ❌ File not found. Did you run fetch_all_raw.py?")
            continue

        try:
            # Read just the first few rows to get headers
            df = pd.read_csv(p, nrows=2)
            cols = df.columns.tolist()
            
            print("   ✅ Columns found:")
            print(f"   {cols}")
            
            # Check for the tricky ones
            candidates = ["Variables", "Characteristics", "Multiplier", "Input-output multipliers"]
            found = [c for c in candidates if c in cols]
            print(f"   🎯 Target Columns found: {found}")
            print("-" * 30)

        except Exception as e:
            print(f"   ❌ Error reading file: {e}")

if __name__ == "__main__":
    inspect()