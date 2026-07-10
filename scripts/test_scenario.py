"""Test Phases 3-4: Infrastructure + Economy for Guelph."""
import sys
sys.path.insert(0, "scripts")
from scenario_engine import run_scenario, calculate_housing_metrics, calculate_infrastructure_metrics, calculate_economic_metrics

r = run_scenario("3523008", "Wellington", migration_factor=1.0, aging_factor=1.0, end_year=2041, use_mof_controls=True)
h = calculate_housing_metrics(r, vacancy_rate=0.03, provincial_target=0)
i = calculate_infrastructure_metrics(r, h)
e = calculate_economic_metrics(r, h)

print("=== INFRASTRUCTURE (Guelph, 2021 vs 2041) ===")
il = i["infrastructure_load"]
base, end = il.iloc[0], il.iloc[-1]
for col in ["water_demand_m3d", "ww_demand_m3d", "total_students", "total_er_visits", "family_docs_needed", "est_vehicles"]:
    print(f"  {col}: {base[col]:,.1f} → {end[col]:,.1f}")

print(f"\n=== DEVELOPMENT CHARGES ===")
dc = i["development_charges"]
print(f"  New units: {dc['new_units']:,}")
print(f"  Per unit: ${dc['total_per_unit']:,}")
print(f"  Total DC: ${dc['total_aggregate']:,.0f}")

print(f"\n=== ECONOMIC IMPACT (Guelph, 2021 vs 2041) ===")
ep = e["economic_projection"]
base_e, end_e = ep.iloc[0], ep.iloc[-1]
for col in ["total_tax_rev", "service_cost_total", "fiscal_balance", "fiscal_per_capita", "labour_force", "employed", "construction_value", "construction_jobs"]:
    print(f"  {col}: {base_e[col]:,.0f} → {end_e[col]:,.0f}")
