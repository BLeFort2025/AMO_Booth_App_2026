"""Quick verification: test engine with custom sidebar parameters."""
import sys
sys.path.insert(0, "scripts")
from scenario_engine import (
    run_scenario, calculate_housing_metrics,
    calculate_infrastructure_metrics, calculate_economic_metrics,
)

# Run baseline scenario for Centre Wellington
r = run_scenario("3523008", "Wellington")
if "error" in r:
    print("FAIL - Engine error:", r["error"])
    sys.exit(1)

h = calculate_housing_metrics(r, vacancy_rate=0.03)

# Test 1: Infrastructure with user-provided capacity
i = calculate_infrastructure_metrics(r, h, user_water_capacity=8000, user_ww_capacity=10000)
il = i["infrastructure_load"]
water_util = il.iloc[-1]["water_util_pct"]
ww_util = il.iloc[-1]["ww_util_pct"]
print(f"PASS - Water util: {water_util:.1f}%, WW util: {ww_util:.1f}%")
assert water_util > 0, "Water utilization should be > 0 when capacity provided"
assert ww_util > 0, "WW utilization should be > 0 when capacity provided"

# Test 2: Infrastructure with 0 capacity (default / no utilization)
i_default = calculate_infrastructure_metrics(r, h, user_water_capacity=0, user_ww_capacity=0)
assert i_default["infrastructure_load"].iloc[-1]["water_util_pct"] == 0, "Default should be 0"
print("PASS - Default capacity (0) shows 0% utilization")

# Test 3: Economy with custom mill rate and assessment
e = calculate_economic_metrics(r, h, local_mill_rate=0.0105, local_assessment=425000)
ep = e["economic_projection"]
tax_custom = ep.iloc[-1]["total_tax_rev"]
print(f"PASS - Tax revenue (custom): ${tax_custom:,.0f}")

# Test 4: Economy with defaults (should use benchmarks)
e_default = calculate_economic_metrics(r, h)
tax_default = e_default["economic_projection"].iloc[-1]["total_tax_rev"]
print(f"PASS - Tax revenue (default): ${tax_default:,.0f}")
assert tax_custom != tax_default, "Custom values should differ from defaults"

print("\nALL TESTS PASSED")
