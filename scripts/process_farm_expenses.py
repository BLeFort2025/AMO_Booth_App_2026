import pandas as pd
import json
from pathlib import Path
import sys

# --- CONFIGURATION ---
POSSIBLE_PATHS = [
    Path("data/latest/32-10-0136-01.csv"),
    Path("data/raw/32-10-0136-01.csv"),
    Path("data/32-10-0136-01.csv"),
    Path("32-10-0136-01.csv")
]

OUTPUT_FILE = Path("data/derived/farm_expense_profiles.json")

def run():
    print("🚜 Starting Farm Expense Processor (Aggressive Interest Search)...")
    
    # 1. Locate File
    target_file = None
    for p in POSSIBLE_PATHS:
        if p.exists():
            target_file = p
            break
            
    if not target_file:
        print(f"❌ Error: Input file not found.")
        return

    # 2. Load Data
    print(f"   Loading {target_file}...")
    try:
        df_raw = pd.read_csv(target_file, low_memory=False)
        if "Year" in df_raw.columns and "REF_DATE" not in df_raw.columns:
            df_raw.rename(columns={"Year": "REF_DATE"}, inplace=True)
        max_year = df_raw["REF_DATE"].max()
        print(f"   Filtering for latest data year: {max_year}")
        df = df_raw[df_raw["REF_DATE"] == max_year].copy()
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        return

    # 3. Dynamic Column Identification
    # Instead of hardcoded maps, we search the actual values in "Estimates"
    unique_estimates = df["Estimates"].unique()
    
    # Helper to find best match
    def find_match(keywords):
        for val in unique_estimates:
            if all(k.lower() in str(val).lower() for k in keywords):
                return val
        return None

    # Map our logic buckets to the ACTUAL strings found in the file
    key_map = {
        "total": find_match(["Total", "operating", "expenses"]),
        "fertilizer": find_match(["Fertilizer"]),
        "labor": find_match(["Salaries", "wages"]),
        "feed": find_match(["Feed", "supplements"]),
        "seed": find_match(["Seeds", "plants"]),
        "pesticide": find_match(["Pesticides"]),
        "interest": find_match(["Interest"]),  # <--- Catches ANY interest line
        "depreciation": find_match(["Capital cost"]),  # CCA and amortization
        # Energy Components
        "fuel_machinery": find_match(["fuel", "machinery"]),
        "fuel_heating": find_match(["Heating", "fuel"]),
        "electricity": find_match(["Electricity"])
    }
    
    # Print what we found to verify
    print("\n   🔎 Mapping Verification:")
    for k, v in key_map.items():
        print(f"      - {k.upper()}: {v}")

    # 4. Filter and Pivot
    # Only keep rows that match our identified keys
    valid_estimates = [v for v in key_map.values() if v is not None]
    df_subset = df[df["Estimates"].isin(valid_estimates)].copy()

    # CRITICAL: The raw CSV has rows for EACH revenue bracket ($10K-$24K,
    # $25K-$49K, etc.) plus an "All revenue classes" aggregate, AND for
    # each Estimate type ("Total estimate", "Average per farm", etc.).
    # We MUST filter to only the aggregate total to avoid double-counting.
    if "Revenue class" in df_subset.columns:
        df_subset = df_subset[
            df_subset["Revenue class"].str.contains("All revenue", case=False, na=False)
        ]
    if "Estimate type" in df_subset.columns:
        df_subset = df_subset[
            df_subset["Estimate type"].str.contains("Total estimate", case=False, na=False)
        ]

    pivot = df_subset.pivot_table(index=["GEO", "Farm type"], columns="Estimates", values="VALUE", aggfunc="sum").reset_index()
    
    profiles = {}
    
    for _, row in pivot.iterrows():
        geo = row["GEO"]
        ftype = row["Farm type"]
        
        # Helper to get value using the dynamic map
        def get_val(key):
            col_name = key_map.get(key)
            return row[col_name] if col_name and col_name in row else 0.0

        total_exp = get_val("total")
        if total_exp == 0: continue
            
        # Sum Components
        fert = get_val("fertilizer")
        labor = get_val("labor")
        feed = get_val("feed")
        crop_inputs = get_val("seed") + get_val("pesticide")
        interest = get_val("interest")
        depreciation = get_val("depreciation")
        energy = get_val("fuel_machinery") + get_val("fuel_heating") + get_val("electricity")
        
        # Calculate Other
        captured = fert + labor + feed + crop_inputs + interest + depreciation + energy
        other = max(0, total_exp - captured)
        
        # --- INTERMEDIATE-ONLY DENOMINATOR (Economist Fix #1) ---
        # IO expense_bill = Revenue * (1 - GDP_coeff) excludes Wages, Interest,
        # and Depreciation.  Census ratios must use the SAME denominator so
        # that  expense_bill * ratio * shock%  yields the correct dollar value.
        intermediate_sum = max(1, total_exp - labor - interest - depreciation)
        # "other" intermediate = everything not captured minus value-added
        other_intermediate = max(0, intermediate_sum - fert - energy - feed - crop_inputs)
        
        profile = {
            "total_expenses_raw": total_exp,
            # Gross ratios (for sidebar display — shows share of TOTAL expenses)
            "ratios": {
                "fertilizer": round(fert / total_exp, 4),
                "energy": round(energy / total_exp, 4),
                "labor": round(labor / total_exp, 4),
                "feed": round(feed / total_exp, 4),
                "crop_inputs": round(crop_inputs / total_exp, 4),
                "interest": round(interest / total_exp, 4),
                "other": round(other / total_exp, 4)
            },
            # Intermediate-only ratios (for simulation math — denominates
            # against the IO expense bill, which excludes value-added)
            "intermediate_ratios": {
                "fertilizer": round(fert / intermediate_sum, 4),
                "energy": round(energy / intermediate_sum, 4),
                "feed": round(feed / intermediate_sum, 4),
                "crop_inputs": round(crop_inputs / intermediate_sum, 4),
                "other": round(other_intermediate / intermediate_sum, 4)
            },
            # Raw dollar values for value-added info card
            "labor_dollars": labor,
            "interest_dollars": interest,
            "depreciation_dollars": depreciation
        }
        profiles[f"{geo}|{ftype}"] = profile

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(profiles, f, indent=2)
        
    print(f"\n✅ Success! Generated {len(profiles)} profiles in {OUTPUT_FILE}")

if __name__ == "__main__":
    run()