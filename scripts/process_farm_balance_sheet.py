"""
process_farm_balance_sheet.py
─────────────────────────────
Phase 2 integration: Derives farm financial health metrics from StatCan data
for use by the Growth & Risk Simulator (page 8).

Sources:
  - 32-10-0051-01  Farm debt outstanding (by lender, by province)
  - 32-10-0052-01  Net farm income, by components (by province)
  - 32-10-0056-01  Balance sheet of the agricultural sector (by province)

Output:
  data/derived/farm_financial_health.csv

Columns produced (per geography):
  geo               — Province or "Canada"
  data_year         — Reference year of the data
  total_assets_M    — Total assets ($ millions)
  total_liabilities_M — Total liabilities ($ millions)
  total_debt_M      — Farm debt outstanding ($ millions)
  equity_M          — Equity ($ millions)
  debt_to_asset     — Debt-to-asset ratio (solvency)
  net_cash_income_M — Net cash income ($ millions)
  depreciation_M    — Depreciation charges ($ millions)
  realized_net_income_M — Realized net income ($ millions)
  current_liabilities_M — Current liabilities ($ millions)
  interest_coverage — Interest coverage ratio (from StatCan)
  amortization_rate — Implied annual principal repayment rate
                      = Current Liabilities / Total Debt
                      (share of debt due within 1 year)
  depreciation_rate — Data-driven capital depreciation rate (δ)
                      = depreciation_M / (CapEx_M / δ_base)
                      Uses CapEx-implied capital stock; clamped to [5%, 20%]
  implied_dscr      — Debt Service Coverage Ratio estimate
                      = Net Cash Income / (Total Debt × (implied_rate + amortization_rate))
"""

import pandas as pd
from pathlib import Path
import sys

# Add project root to path if needed
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import config_loader

# Constants
TABLE_DEBT     = "32-10-0051-01"
TABLE_INCOME   = "32-10-0052-01"
TABLE_BALANCE  = "32-10-0056-01"
CAPEX_FILE     = Path("data/derived/basket_capex.csv")
OUTPUT_FILE    = Path("data/derived/farm_financial_health.csv")

# Depreciation rate constants
DELTA_BASE     = 0.12   # Baseline δ used to estimate K₀ from CapEx (K = CapEx/δ)
DELTA_MIN      = 0.05   # Floor: prevents unrealistically slow depreciation
DELTA_MAX      = 0.20   # Cap: prevents noisy estimates from tiny provinces


def _load_table(table_id):
    """Load a raw StatCan CSV, return DataFrame or None."""
    raw_dir = config_loader.get_raw_data_dir()
    raw_path = raw_dir / f"{table_id}.csv"
    if not raw_path.exists():
        print(f"  [WARNING] Raw data for {table_id} not found at {raw_path}")
        return None
    return pd.read_csv(raw_path, low_memory=False)


def _filter_latest(df, geo_col="GEO"):
    """Keep only the latest reference year."""
    latest = df["REF_DATE"].max()
    return df[df["REF_DATE"] == latest].copy(), latest


def run():
    print("--- Processing Farm Balance Sheet Data ---")

    # ── 1. Load Balance Sheet (32-10-0056) ──────────────────────────────
    df_bs = _load_table(TABLE_BALANCE)
    if df_bs is None:
        return
    df_bs, bs_year = _filter_latest(df_bs)
    print(f"  Balance Sheet: using {bs_year} data ({len(df_bs)} rows)")

    # Extract key items per geography
    dim_col = "Commodities"
    items_dollars = [
        "Total assets", "Total liabilities", "Equity",
        "Current assets", "Current liabilities",
        "Long-term liabilities", "Machinery", "Farm real estate",
    ]
    items_ratios = [
        "Solvency ratio: debt",
        "Efficiency ratio: interest coverage",
    ]

    bs_data = {}
    for geo in df_bs["GEO"].unique():
        geo_df = df_bs[df_bs["GEO"] == geo]
        record = {"geo": geo}

        # Dollar items (in thousands → convert to millions)
        for item in items_dollars:
            row = geo_df[geo_df[dim_col] == item]
            if not row.empty:
                val = row.iloc[0]["VALUE"]
                key = item.lower().replace(" ", "_").replace(",", "")
                record[f"{key}_M"] = val / 1_000 if pd.notna(val) else None

        # Ratio items (already unit-less)
        for item in items_ratios:
            row = geo_df[geo_df[dim_col] == item]
            if not row.empty:
                val = row.iloc[0]["VALUE"]
                key = item.lower().replace(" ", "_").replace(":", "").replace(" ", "_")
                record[key] = val if pd.notna(val) else None

        bs_data[geo] = record

    # ── 2. Load Farm Debt (32-10-0051) ──────────────────────────────────
    df_debt = _load_table(TABLE_DEBT)
    if df_debt is None:
        return
    df_debt, debt_year = _filter_latest(df_debt)
    print(f"  Farm Debt: using {debt_year} data ({len(df_debt)} rows)")

    # Get total debt per geography (in thousands → millions)
    dim_debt = "Type of lender"
    for geo in df_debt["GEO"].unique():
        total_row = df_debt[
            (df_debt["GEO"] == geo) &
            (df_debt[dim_debt] == "Farm debt outstanding, total")
        ]
        if not total_row.empty and geo in bs_data:
            val = total_row.iloc[0]["VALUE"]
            bs_data[geo]["total_debt_M"] = val / 1_000 if pd.notna(val) else None

    # ── 3. Load Income Components (32-10-0052) ──────────────────────────
    df_inc = _load_table(TABLE_INCOME)
    if df_inc is None:
        return
    df_inc, inc_year = _filter_latest(df_inc)
    print(f"  Farm Income: using {inc_year} data ({len(df_inc)} rows)")

    dim_inc = "Income components"
    income_items = {
        "Net cash income": "net_cash_income_M",
        "Depreciation charges": "depreciation_M",
        "Realized net income": "realized_net_income_M",
        "Cash receipts, total": "cash_receipts_M",
        "Operating expenses after rebates": "operating_expenses_M",
    }

    for geo in df_inc["GEO"].unique():
        geo_df = df_inc[df_inc["GEO"] == geo]
        if geo not in bs_data:
            bs_data[geo] = {"geo": geo}
        for item_name, col_name in income_items.items():
            row = geo_df[geo_df[dim_inc] == item_name]
            if not row.empty:
                val = row.iloc[0]["VALUE"]
                bs_data[geo][col_name] = val / 1_000 if pd.notna(val) else None

    # ── 4. Compute Derived Metrics ──────────────────────────────────────
    # ── 5. Load CapEx data for depreciation rate derivation ────────────
    capex_by_geo = {}
    if CAPEX_FILE.exists():
        df_capex = pd.read_csv(CAPEX_FILE)
        for _, cr in df_capex[df_capex["basket_key"] == "primary_agriculture"].iterrows():
            capex_by_geo[cr["geo"]] = cr["total_capex_M"]
        print(f"  CapEx data loaded: {len(capex_by_geo)} geographies")
    else:
        print(f"  [WARNING] CapEx file not found at {CAPEX_FILE} — δ will use defaults")

    results = []
    for geo, rec in bs_data.items():
        total_assets = rec.get("total_assets_M")
        total_liab = rec.get("total_liabilities_M")
        total_debt = rec.get("total_debt_M")
        current_liab = rec.get("current_liabilities_M")
        nci = rec.get("net_cash_income_M")
        depr = rec.get("depreciation_M")

        # Debt-to-asset ratio (computed, cross-check with StatCan ratio)
        debt_to_asset = None
        if total_liab and total_assets and total_assets > 0:
            debt_to_asset = total_liab / total_assets

        # Amortization rate: Current Liabilities / Total Debt
        # = share of debt due within 1 year (natural proxy for annual repayment)
        amortization_rate = None
        if current_liab and total_debt and total_debt > 0:
            amortization_rate = current_liab / total_debt

        # Depreciation rate (δ): depreciation / capital_stock
        # Capital stock estimated from CapEx: K = CapEx / δ_base
        # Then δ_actual = depreciation / K = depreciation / (CapEx / δ_base)
        # Clamped to [DELTA_MIN, DELTA_MAX] to avoid outliers from tiny provinces
        depreciation_rate = None
        capex_val = capex_by_geo.get(geo, 0)
        if depr and depr > 0 and capex_val > 0:
            K_estimated = capex_val / DELTA_BASE
            depreciation_rate = depr / K_estimated
            depreciation_rate = max(DELTA_MIN, min(DELTA_MAX, depreciation_rate))

        # Implied DSCR: NCI / (Debt × (interest_rate + amortization_rate))
        # Uses data-derived amortization rate instead of hardcoded 10%
        implied_dscr = None
        if nci and total_debt and total_debt > 0:
            amort = amortization_rate if amortization_rate else 0.10
            annual_debt_service = total_debt * (0.05 + amort)
            implied_dscr = nci / annual_debt_service

        results.append({
            "geo": geo,
            "data_year": max(bs_year, debt_year, inc_year),
            "total_assets_M": rec.get("total_assets_M"),
            "total_liabilities_M": total_liab,
            "total_debt_M": total_debt,
            "equity_M": rec.get("equity_M"),
            "debt_to_asset": round(debt_to_asset, 4) if debt_to_asset else None,
            "current_liabilities_M": current_liab,
            "net_cash_income_M": nci,
            "depreciation_M": depr,
            "realized_net_income_M": rec.get("realized_net_income_M"),
            "cash_receipts_M": rec.get("cash_receipts_M"),
            "operating_expenses_M": rec.get("operating_expenses_M"),
            "interest_coverage": rec.get("efficiency_ratio_interest_coverage"),
            "amortization_rate": round(amortization_rate, 4) if amortization_rate else None,
            "depreciation_rate": round(depreciation_rate, 4) if depreciation_rate else None,
            "implied_dscr": round(implied_dscr, 3) if implied_dscr else None,
        })

    # Sort: Canada first, then alphabetical
    results.sort(key=lambda r: ("" if r["geo"] == "Canada" else r["geo"]))

    out_df = pd.DataFrame(results)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(OUTPUT_FILE, index=False)

    # ── Print Summary ───────────────────────────────────────────────────
    print(f"\n  Saved {len(results)} records to {OUTPUT_FILE}")
    canada = next((r for r in results if r["geo"] == "Canada"), None)
    if canada:
        print(f"  Canada Summary ({canada['data_year']}):")
        print(f"    Total Assets:      ${canada['total_assets_M']:,.0f}M")
        print(f"    Total Liabilities: ${canada['total_liabilities_M']:,.0f}M")
        print(f"    Total Debt:        ${canada['total_debt_M']:,.0f}M")
        print(f"    Debt-to-Asset:     {canada['debt_to_asset']:.1%}")
        print(f"    Net Cash Income:   ${canada['net_cash_income_M']:,.0f}M")
        print(f"    Interest Coverage: {canada['interest_coverage']:.2f}x")
        print(f"    Implied DSCR:      {canada['implied_dscr']:.2f}x")
    print("--- Done ---")


if __name__ == "__main__":
    run()
