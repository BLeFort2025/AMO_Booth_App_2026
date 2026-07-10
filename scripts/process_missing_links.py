import pandas as pd
import yaml
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- IMPORT THE SOURCE OF TRUTH ---
# We use the same engine as Page 6 to guarantee the numbers match.
from scripts.io_multipliers_engine import get_actual_output, industries_for_basket, available_years

# --- CONFIG ---
OUTPUT_FILE = Path("data/derived/basket_output.csv")
CONFIG_FILE = PROJECT_ROOT / "config" / "io_baskets.yml"

def load_shares():
    if not CONFIG_FILE.exists(): return {}
    with open(CONFIG_FILE, "r") as f:
        conf = yaml.safe_load(f)
    shares = {}
    for key, data in conf.get('baskets', {}).items():
        shares[key] = float(data.get('calculated_share', 1.0))
    return shares

def run():
    print("--- 🔄 Synchronizing Page 8 Baseline with Page 6 Engine ---")
    
    # 1. Get Shares from YAML
    shares = load_shares()
    
    # 2. Determine Target Year (Match Page 6 Default)
    # We check what years the engine has available for Canada
    years = available_years("Canada")
    target_year = 2022
    if years and 2022 in years:
        target_year = 2022
    elif years:
        target_year = max(years) # Fallback to latest
        
    print(f"   📅 Target Year: {target_year}")

    new_rows = []
    grand_total = 0.0
    core_sum = 0.0
    
    # 3. Iterate Baskets from Config
    with open(CONFIG_FILE, "r") as f:
        conf = yaml.safe_load(f)
        basket_keys = list(conf.get('baskets', {}).keys())

    for basket in basket_keys:
        # A. Get the Codes via Engine (Handles matching logic)
        ind_df = industries_for_basket(basket)
        
        if ind_df.empty:
            print(f"   ⚠️ Basket '{basket}' returned no industries.")
            continue
            
        codes = ind_df['join_code'].tolist()
        
        # B. Get Raw Output via Engine (The Source of Truth)
        # This sums the standardized IO table values
        raw_val = get_actual_output("Canada", target_year, codes)
        
        # C. Apply Share Coefficient
        share = shares.get(basket, 1.0)
        final_val = raw_val * share
        
        print(f"   > {basket}: ${final_val/1e9:.1f}B (Share: {share:.1%})")
        
        # D. Store Result
        new_rows.append({
            "basket_key": basket,
            "verified_output": final_val,
            "data_year": target_year
        })
        
        # E. Classify for Headline Total
        if basket == "cfa_food_system":
            core_sum = final_val
        elif basket not in ["primary_agriculture", "food_beverage_manufacturing"]:
            # Satellites (Transport, Inputs, Wholesale)
            # We exclude primary/mfg here because they are inside the Core sum
            grand_total += final_val

    # Grand Total = Core + Satellites
    grand_total += core_sum

    # 4. Save to CSV for Page 8
    df_final = pd.DataFrame(new_rows)
    # Add Total Row
    df_final = pd.concat([df_final, pd.DataFrame([{
        "basket_key": "cfa_total_footprint",
        "verified_output": grand_total,
        "data_year": target_year
    }])], ignore_index=True)
    
    df_final.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✅ Synchronization Complete.")
    print(f"   > 🇨🇦 CORE ENGINE (Page 6 Match): ${core_sum/1e9:.1f} B")
    print(f"   > 🇨🇦 TOTAL FOOTPRINT:            ${grand_total/1e9:.1f} B")

if __name__ == "__main__":
    run()