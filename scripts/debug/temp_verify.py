import json
p = json.load(open("data/derived/farm_expense_profiles.json"))
d = p.get("Ontario|Crop production [111]", {})
ir = d.get("intermediate_ratios", {})
r = d.get("ratios", {})
print("=== Ontario | Crop production [111] ===")
print(f"Total expenses: ${d.get('total_expenses_raw', 0) / 1e6:,.0f}M")
print(f"Labor $:        ${d.get('labor_dollars', 0) / 1e6:,.0f}M")
print(f"Interest $:     ${d.get('interest_dollars', 0) / 1e6:,.0f}M")
print(f"Depreciation $: ${d.get('depreciation_dollars', 0) / 1e6:,.0f}M")
print()
print("Gross ratios (display):")
for k, v in r.items():
    print(f"  {k}: {v:.1%}")
print()
print("Intermediate ratios (sim):")
for k, v in ir.items():
    print(f"  {k}: {v:.1%}")
print(f"  SUM: {sum(ir.values()):.1%}")

# Economist trace: IO expense_bill ~$5.80B, 10% fert shock
expense_bill = 5_800_000_000
fert_ir = ir.get("fertilizer", 0)
shock = expense_bill * fert_ir * 0.10
print(f"\n=== Economist Trace ===")
print(f"expense_bill * intermediate_fert_ratio * 10%")
print(f"= $5.80B * {fert_ir:.1%} * 10%")
print(f"= ${shock / 1e6:,.0f}M")
print(f"Economist expected: ~$138M")
