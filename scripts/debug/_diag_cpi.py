"""Quick diagnostic: verify CPI deflators and the narrative number."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

# 1. Check farm cash receipts 2023-2024 values
df = pd.read_csv("data/latest/32-10-0045-01.csv", low_memory=False)
receipts = df[
    (df["GEO"] == "Canada")
    & (df.iloc[:, 3] == "Total farm cash receipts")
    & (df["YEAR"].isin([2022, 2023, 2024]))
][["YEAR", "VALUE", "SCALAR_FACTOR", "UOM"]]
print("=== Farm Cash Receipts (Canada) ===")
print(receipts.to_string(index=False))
print()

# 2. Check if CPI table exists locally
cpi_path = "data/latest/18-10-0005-01.csv"
if os.path.exists(cpi_path):
    print("CPI file exists locally")
    cpi = pd.read_csv(cpi_path, low_memory=False)
    print(f"CPI rows: {len(cpi)}, columns: {cpi.columns.tolist()[:8]}")
else:
    print("CPI file does NOT exist locally - will be fetched live")
    # Try loading via the app's loader
    try:
        from app.cpi_utils import load_cpi_deflators
        result = load_cpi_deflators(
            table_config=[{"id": "18-10-0005-01"}],
            _load_table_fn=lambda tid: pd.DataFrame(),  # dummy
        )
        if isinstance(result, tuple):
            cpi_df, geo = result
        else:
            cpi_df = result
        print(f"load_cpi_deflators returned: {type(cpi_df)}, shape={getattr(cpi_df, 'shape', 'N/A')}")
        if hasattr(cpi_df, 'empty') and not cpi_df.empty:
            print(cpi_df[cpi_df["YEAR"].isin([2022, 2023, 2024])].to_string(index=False))
    except Exception as e:
        print(f"Error loading CPI: {e}")
        import traceback; traceback.print_exc()

# 3. Show what the narrative formatter would produce
val_2024 = 514573720
val_2024_actual = val_2024 * 1000  # because SCALAR_FACTOR=thousands
print(f"\n=== Narrative Formatting ===")
print(f"Raw VALUE: {val_2024:,}")
print(f"Actual dollars (x1000): ${val_2024_actual:,.0f}")
print(f"Raw -> narrative:  {val_2024/1e6:.1f} million (WRONG - what the code does)")
print(f"Actual -> narrative: {val_2024_actual/1e9:.1f} billion (CORRECT)")
