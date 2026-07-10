import sys
import pandas as pd
from pathlib import Path

# Add project root to path to allow imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.io_multipliers_engine import industries_for_basket, load_supply_use_subset

def run_diagnostic():
    print("--- BASKET HISTORY DIAGNOSTIC (2021) ---")
    
    # 1. Get Dashboard Configured Codes
    basket_df = industries_for_basket("primary_agriculture")
    if basket_df.empty:
        print("CRITICAL: Dashboard returns empty basket.")
        return
        
    dashboard_codes = set(basket_df['join_code'].astype(str))
    print(f"Dashboard Configured Codes: {sorted(list(dashboard_codes))}")
    
    # 2. Get Actual Data for 2021
    df = load_supply_use_subset()
    # Filter: Canada, 2021, and broad Agriculture definition (111*, 112*, 115*)
    mask_2021 = (df['YEAR'] == 2021) & (df['GEO'] == 'Canada')
    df_2021 = df[mask_2021].copy()
    
    # Regex for "All Agriculture"
    ag_data = df_2021[df_2021['join_code'].astype(str).str.match(r'^(111|112|115)')].sort_values('VALUE', ascending=False)
    
    print("\n--- GAP ANALYSIS: 2021 DATA VS CONFIG ---")
    print(f"{'Code':<10} | {'Status':<12} | {'Value ($)':<15} | {'Industry Name'}")
    print("-" * 80)
    
    missing_sum = 0
    
    for _, row in ag_data.iterrows():
        code = str(row['join_code'])
        val = row['VALUE']
        name = row['io_name']
        
        if code in dashboard_codes:
            status = "✅ INCLUDED"
        else:
            status = "❌ MISSING"
            missing_sum += val
            
        print(f"{code:<10} | {status:<12} | ${val:,.0f} | {name}")
        
    print("-" * 80)
    print(f"TOTAL MISSING FROM DASHBOARD (2021): ${missing_sum:,.0f}")

if __name__ == "__main__":
    import sys
    # Redirect stdout to a file with UTF-8 encoding
    with open("debug_basket_gap_utf8.txt", "w", encoding="utf-8") as f:
        original_stdout = sys.stdout
        sys.stdout = f
        try:
            run_diagnostic()
        finally:
            sys.stdout = original_stdout
            
    print("Diagnostic complete. Results saved to debug_basket_gap_utf8.txt")
