"""Print missing FIR municipalities by year from audit JSON."""
import json

with open("data/fir_audit.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for year_str, items in data["missing"].items():
    print(f"\n=== Missing from {year_str}: {len(items)} municipalities ===")
    for item in items:
        present = ", ".join(str(y) for y in item["present_in"])
        print(f"  {item['code']} {item['name']} [present in: {present}]")
