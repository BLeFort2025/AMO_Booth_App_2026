import json

d = json.load(open("data/farm_cost_impact_data.json"))
est = d["estimated_april_2026_ontario"]["fertilizer"]
base = d["baseline_2025"]["fertilizer"]
fuel_b = d["baseline_2025"]["fuel"]
fuel_e = d["estimated_april_2026_ontario"]["fuel"]

print("=== FERTILIZER PRICE COMPARISON ===")
for key in ["urea_46_0_0", "map_11_52_0", "potash_mop_0_0_60"]:
    b = base[key]["price_per_tonne"]
    e = est[key]
    mid = e["midpoint"]
    lo = e["working_range"]["low"]
    hi = e["working_range"]["high"]
    pct = round((mid / b - 1) * 100, 1)
    name = key.split("_")[0].upper()
    print(f"  {name}: 2025=${b}/t -> 2026 ${lo}-${hi}/t (mid=${mid}/t, YoY={pct:+.1f}%)")

print("\n=== FUEL PRICE COMPARISON ===")
db = fuel_b["diesel_coloured_farm"]["price_per_litre"]
de = fuel_e["diesel_coloured_farm"]
dm = de["midpoint"]
dpct = round((dm / db - 1) * 100, 1)
print(f"  Diesel (farm bulk): 2025=${db}/L -> 2026 ${de['working_range']['low']}-${de['working_range']['high']}/L (mid=${dm}/L, YoY={dpct:+.1f}%)")

print("\n=== WORLD BANK RAW DATA ===")
wb = d["world_bank"]["raw_data"]
if "monthly_prices" in wb:
    for k, v in wb["monthly_prices"].items():
        if v:
            recent = {p: pr for p, pr in v.items() if "2026" in p or "2025M04" in p}
            if recent:
                print(f"  {k}: {recent}")
    print()
    if "monthly_indices" in wb:
        for k, v in wb["monthly_indices"].items():
            if v:
                recent = {p: pr for p, pr in v.items() if "2026" in p or "2025M04" in p}
                if recent:
                    print(f"  INDEX {k}: {recent}")
else:
    print(f"  Keys: {list(wb.keys())}")
