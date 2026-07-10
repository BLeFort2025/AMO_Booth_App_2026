"""
Derive Master Farmland Valuations Dataset
=========================================
Merges ONFVRVS rental and buyer datasets, strips geographic suffixes for
mapping compatibility, and calculates the Income Capitalization Approach
agricultural value.

Output: data/surveys/onfvrvs_master_valuation.csv
"""

import pandas as pd
from pathlib import Path
import re

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data" / "surveys"

def clean_geo_name(region):
    """Clean region string by stripping everything after the first parenthesis"""
    return str(region).split('(')[0].strip()

def main():
    print("=" * 70)
    print("Deriving Master Farmland Valuation Dataset")
    print("=" * 70)
    
    rental_path = DATA_DIR / "onfvrvs_rental_rates_and_values.csv"
    buyer_path = DATA_DIR / "onfvrvs_buyer_perceptions.csv"
    
    if not rental_path.exists() or not buyer_path.exists():
        print("ERROR: Source CSV datasets not found.")
        return
        
    df_rent = pd.read_csv(rental_path)
    df_buyer = pd.read_csv(buyer_path)
    
    # 1. Clean the region names to prepare for merge and mapping
    df_rent['geo_name'] = df_rent['region'].apply(clean_geo_name)
    df_buyer['geo_name'] = df_buyer['region'].apply(clean_geo_name)
    
    # Standardize specific naming inconsistencies to match dim_geography.csv
    # e.g., "Stormont, Dundas and Glengarry" is standard in both
    map_fixes = {
        'Haldimand-Norfolk': 'Haldimand-Norfolk', # Might need mapping if boundaries are split
    }
    
    # 2. Merge the datasets
    # We use left join on rent as the primary foundation
    df_master = pd.merge(
        df_rent,
        df_buyer[['year', 'geo_name', 'pct_sales_to_farmers']],
        on=['year', 'geo_name'],
        how='left'
    )
    
    # 3. Calculate Income Capitalization (Agricultural Value) using Exogenous Cap Rate
    
    # Historical Bank of Canada 10-Year Bond Yields (V122487)
    BOC_10YR_YIELDS = {}
    import urllib.request
    import json
    
    try:
        url = 'https://www.bankofcanada.ca/valet/observations/V122487/json'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        yearly_accums = {}
        for obs in data.get('observations', []):
            year = int(obs.get('d', '')[:4])
            if year >= 2016:
                val_str = obs.get('V122487', {}).get('v')
                if val_str:
                    yearly_accums.setdefault(year, []).append(float(val_str))
                    
        for y, vals in yearly_accums.items():
            BOC_10YR_YIELDS[y] = sum(vals) / len(vals)
            
        print("✓ BoC Valet API: Yields fetched dynamically.")
    except Exception as e:
        print(f"⚠ BoC API Fetch Failed: {e}. Falling back to hardcoded history.")
        BOC_10YR_YIELDS = {
            2016: 1.8042, 2017: 2.1808, 2018: 2.3250, 2019: 1.7258,
            2020: 1.0758, 2021: 1.7983, 2022: 2.8600, 2023: 3.3092,
            2024: 3.3625, 2025: 3.5175
        }

    df_master['boc_10yr_yield'] = df_master['year'].map(BOC_10YR_YIELDS)
    AGRICULTURAL_RISK_PREMIUM_PCT = 4.0
    EXPECTED_ANNUAL_GROWTH_PCT = 2.5  # Expected annual growth in cash rents/NOI, not capital appreciation
    NOI_DEDUCTION_FACTOR = 0.85  # Deduct 15% from gross cash rents for property taxes and maintenance
    CAP_RATE_FLOOR_PCT = 2.0  # Minimum credible farmland cap rate (prevents model instability in low-rate environments)
    
    def calc_ag_value(row):
        rent = row['median_cash_rent_per_acre']
        boc_yield = row.get('boc_10yr_yield')
        
        if pd.isna(rent) or pd.isna(boc_yield):
            return None
            
        noi = rent * NOI_DEDUCTION_FACTOR
        cap_rate_pct = boc_yield + AGRICULTURAL_RISK_PREMIUM_PCT - EXPECTED_ANNUAL_GROWTH_PCT
        # Floor the cap rate to prevent model instability in low-rate environments
        cap_rate_pct = max(CAP_RATE_FLOOR_PCT, cap_rate_pct)
        
        return noi / (cap_rate_pct / 100.0)

    df_master['agricultural_value_per_acre'] = df_master.apply(calc_ag_value, axis=1)
    
    # Add the exogenous cap rate to the dataset for transparency
    df_master['exogenous_cap_rate_pct'] = df_master['boc_10yr_yield'] + AGRICULTURAL_RISK_PREMIUM_PCT - EXPECTED_ANNUAL_GROWTH_PCT
    df_master['exogenous_cap_rate_pct'] = df_master['exogenous_cap_rate_pct'].clip(lower=CAP_RATE_FLOOR_PCT)
    
    # Rename market value for clarity
    df_master = df_master.rename(columns={
        'median_land_price_per_acre': 'market_value_per_acre'
    })
    
    # Calculate the valuation premium (Market Value - Agricultural Value)
    df_master['market_premium_pct'] = (
        (df_master['market_value_per_acre'] - df_master['agricultural_value_per_acre']) 
        / df_master['agricultural_value_per_acre']
    ) * 100
    
    # 4. Sort and export
    df_master = df_master.sort_values(['year', 'geo_name'])
    
    out_path = DATA_DIR / "onfvrvs_master_valuation.csv"
    df_master.to_csv(out_path, index=False)
    
    print(f"✓ Master dataset generated: {len(df_master)} records")
    print(f"✓ Saved to: {out_path.name}")
    
    # Print sample of the value gap
    print("\nSample comparing Agricultural Value vs Market Value (2024):")
    sample = df_master[df_master['year'] == 2024][['geo_name', 'median_cash_rent_per_acre', 'agricultural_value_per_acre', 'market_value_per_acre']].head(10)
    for _, r in sample.iterrows():
        ag = f"${r['agricultural_value_per_acre']:,.0f}" if pd.notnull(r['agricultural_value_per_acre']) else "N/A"
        mkt = f"${r['market_value_per_acre']:,.0f}" if pd.notnull(r['market_value_per_acre']) else "N/A"
        print(f"  {r['geo_name']:20s} Rent: ${r['median_cash_rent_per_acre']:,.0f} | Ag Val: {ag:>10s} | Mkt Val: {mkt:>10s}")

if __name__ == "__main__":
    main()
