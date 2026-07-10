"""
process_labor_metrics.py
────────────────────────
Derives province-specific labor vulnerability metrics from StatCan data
for use by the Growth & Risk Simulator (page 8).

Sources:
  - 32-10-0218-01  TFW in agriculture & agri-food, by industry & province
  - 32-10-0216-01  Employees in the agriculture sector, by province

Output:
  data/derived/labor_metrics.csv

Columns produced (per geography):
  geo                — Province or "Canada"
  data_year_emp      — Reference year for employment data
  data_year_tfw      — Reference year for TFW data
  total_employees    — Total agricultural employees
  full_time          — Full-time employees
  seasonal           — Seasonal employees
  seasonal_share     — Seasonal / Total (labor volatility indicator)
  tfw_ag             — TFW workers in agriculture
  tfw_dependency     — TFW / Total employees (labor vulnerability ratio)
  base_vacancy_rate  — Calibrated structural vacancy rate
                       = CAHRC_baseline × (1 + relative_tfw_excess)
                       Provinces with above-average TFW dependency get
                       higher structural vacancy (more exposed to labor shocks)
"""

import pandas as pd
from pathlib import Path
import sys

# Add project root to path if needed
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Constants
TABLE_TFW = "32-10-0218-01"
TABLE_EMP = "32-10-0216-01"
OUTPUT_FILE = Path("data/derived/labor_metrics.csv")
CAHRC_VACANCY = 0.074  # CAHRC 2022 national baseline vacancy rate


def run():
    print("--- Processing Labor Metrics ---")

    # ── 1. Load Employment Data (32-10-0216) ─────────────────────────────
    emp_path = Path("data/latest") / f"{TABLE_EMP}.csv"
    if not emp_path.exists():
        print(f"  [WARNING] Employment data not found at {emp_path}")
        return
    df_emp = pd.read_csv(emp_path, low_memory=False)
    emp_year = df_emp["REF_DATE"].max()
    df_emp = df_emp[df_emp["REF_DATE"] == emp_year].copy()
    print(f"  Employment: using {emp_year} data ({len(df_emp)} rows)")

    # Extract per province
    emp_data = {}
    for geo in df_emp["GEO"].unique():
        geo_df = df_emp[df_emp["GEO"] == geo]
        record = {"geo": geo}
        for _, row in geo_df.iterrows():
            stat = row["Statistics"]
            val = row["VALUE"]
            if stat == "Total number of employees":
                record["total_employees"] = int(val) if pd.notna(val) else 0
            elif stat == "Full-time employees":
                record["full_time"] = int(val) if pd.notna(val) else 0
            elif stat == "Seasonal employees":
                record["seasonal"] = int(val) if pd.notna(val) else 0
        emp_data[geo] = record

    # ── 2. Load TFW Data (32-10-0218) ────────────────────────────────────
    tfw_path = Path("data/latest") / f"{TABLE_TFW}.csv"
    if not tfw_path.exists():
        print(f"  [WARNING] TFW data not found at {tfw_path}")
        return
    df_tfw = pd.read_csv(tfw_path, low_memory=False)
    tfw_year = df_tfw["REF_DATE"].max()
    df_tfw_latest = df_tfw[df_tfw["REF_DATE"] == tfw_year].copy()
    print(f"  TFW: using {tfw_year} data ({len(df_tfw_latest)} rows)")

    # Get total ag TFW per province (filter: "Agricultural industries, total" +
    # "Temporary foreign workers" statistic)
    tfw_ag = df_tfw_latest[
        (df_tfw_latest["Industry"] == "Agricultural industries, total") &
        (df_tfw_latest["Statistics"] == "Temporary foreign workers")
    ]

    for _, row in tfw_ag.iterrows():
        geo = row["GEO"]
        if geo in emp_data:
            emp_data[geo]["tfw_ag"] = int(row["VALUE"]) if pd.notna(row["VALUE"]) else 0

    # ── 3. Compute Derived Metrics ───────────────────────────────────────
    # National TFW dependency for calibration reference
    canada = emp_data.get("Canada", {})
    national_tfw_dep = 0.0
    if canada.get("total_employees", 0) > 0 and canada.get("tfw_ag", 0) > 0:
        national_tfw_dep = canada["tfw_ag"] / canada["total_employees"]
    print(f"  National TFW dependency: {national_tfw_dep:.1%}")

    results = []
    for geo, rec in emp_data.items():
        total_emp = rec.get("total_employees", 0)
        seasonal = rec.get("seasonal", 0)
        tfw = rec.get("tfw_ag", 0)

        # TFW dependency ratio
        tfw_dependency = tfw / total_emp if total_emp > 0 else 0.0

        # Seasonal share (labor volatility)
        seasonal_share = seasonal / total_emp if total_emp > 0 else 0.0

        # Calibrated base vacancy rate:
        # Provinces with higher TFW dependency face higher structural vacancy
        # because their labor market is more fragile (more reliant on program access).
        # Formula: vacancy = CAHRC_baseline × (1 + excess_tfw_reliance)
        # where excess = (provincial_tfw_dep - national_avg) / national_avg
        # Clamped to [3%, 15%] to prevent outliers.
        if national_tfw_dep > 0:
            relative_excess = (tfw_dependency - national_tfw_dep) / national_tfw_dep
            base_vacancy = CAHRC_VACANCY * (1 + relative_excess * 0.5)  # damped
        else:
            base_vacancy = CAHRC_VACANCY
        base_vacancy = max(0.03, min(0.15, base_vacancy))

        results.append({
            "geo": geo,
            "data_year_emp": emp_year,
            "data_year_tfw": tfw_year,
            "total_employees": total_emp,
            "full_time": rec.get("full_time", 0),
            "seasonal": seasonal,
            "seasonal_share": round(seasonal_share, 4),
            "tfw_ag": tfw,
            "tfw_dependency": round(tfw_dependency, 4),
            "base_vacancy_rate": round(base_vacancy, 4),
        })

    # Sort: Canada first, then alphabetical
    results.sort(key=lambda r: ("" if r["geo"] == "Canada" else r["geo"]))

    out_df = pd.DataFrame(results)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(OUTPUT_FILE, index=False)

    # ── Print Summary ────────────────────────────────────────────────────
    print(f"\n  Saved {len(results)} records to {OUTPUT_FILE}")
    print(f"\n  {'Geo':<30} {'Employees':>10} {'TFW':>8} {'TFW Dep':>8} {'Vacancy':>8}")
    print("  " + "-" * 68)
    for r in results:
        print(f"  {r['geo']:<30} {r['total_employees']:>10,} {r['tfw_ag']:>8,} "
              f"{r['tfw_dependency']:>7.1%} {r['base_vacancy_rate']:>7.1%}")
    print("--- Done ---")


if __name__ == "__main__":
    run()
