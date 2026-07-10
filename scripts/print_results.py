"""Quick summary of model results."""
import json

with open("data/farm_cost_impact_results.json") as f:
    r = json.load(f)

g = r["grain_farm_500ac"]
v = r["vegetable_farm_200ac"]

print(f"=== SCENARIO 1: {g['acres']}-ACRE GRAIN CORN FARM ===")
print(f"Source:          {g['source']}")
print(f"Yield:           {g['yield_bu_per_acre']} bu/ac")
print(f"2025 Total:      ${g['total_2025']:,}")
print(f"2026 Range:      ${g['total_2026_range'][0]:,} (cons) / ${g['total_2026_range'][1]:,} (mid) / ${g['total_2026_range'][2]:,} (worst)")
print(f"Increase ($):    ${g['increase_range'][0]:,} / ${g['increase_range'][1]:,} / ${g['increase_range'][2]:,}")
print(f"Per Acre Inc:    ${g['per_acre_increase'][0]}/ac / ${g['per_acre_increase'][1]}/ac / ${g['per_acre_increase'][2]}/ac")
print(f"Mid % Increase:  {g['pct_increase'][1]}%")
d = g["details"]
print(f"\nBreakdown (midpoint):")
print(f"  fertilizer      ${d['fertilizer']['2025']:>10,} -> ${d['fertilizer']['2026_mid']:>10,}  (+{round((d['fertilizer']['2026_mid']/d['fertilizer']['2025']-1)*100)}%)")
print(f"  fuel            ${d['fuel']['2025']:>10,} -> ${d['fuel']['2026_mid']:>10,}  (+{round((d['fuel']['2026_mid']/d['fuel']['2025']-1)*100)}%)")
print(f"  drying          ${d['drying']['2025']:>10,} -> ${d['drying']['2026_mid']:>10,}  (+{round((d['drying']['2026_mid']/d['drying']['2025']-1)*100)}%)")

print(f"\n=== SCENARIO 2: 200-ACRE VEGETABLE FARM ===")
print(f"N demand:        {v['total_n_lbs']:,} lbs")
print(f"Urea needed:     {v['urea_tonnes']} tonnes")
print(f"2025 Cost:       ${v['cost_2025']:,}")
print(f"2026 Range:      ${v['cost_2026_range'][0]:,} (cons) / ${v['cost_2026_range'][1]:,} (mid) / ${v['cost_2026_range'][2]:,} (worst)")
print(f"Increase ($):    ${v['increase_range'][0]:,} / ${v['increase_range'][1]:,} / ${v['increase_range'][2]:,}")
print(f"Per acre 2025:   ${v['per_acre_cost_2025']}/ac")
print(f"Per acre 2026:   ${v['per_acre_cost_2026_mid']}/ac")
