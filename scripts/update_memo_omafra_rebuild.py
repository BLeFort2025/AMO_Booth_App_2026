"""
Comprehensive Word document update — OMAFRA Pub 60 rebuild.
Updates ALL paragraphs and table cells with the new OMAFRA-based numbers.
"""
import json
from docx import Document

DOC_PATH = (
    r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture"
    r"\Desktop\Ben Desktop Files\Farm Business Confidence Survey"
    r"\2025\Specififc Issue spekaing notes"
    r"\Energy and Fertilizer Shock Memo and Speaking Notes.docx"
)

with open("data/farm_cost_impact_results.json") as f:
    r = json.load(f)

g = r["grain_farm_500ac"]
d = g["details"]

# Exact model values
grand_2025 = g["total_2025"]
grand_cons = g["total_2026_range"][0]
grand_mid = g["total_2026_range"][1]
grand_worst = g["total_2026_range"][2]
inc_cons = g["increase_range"][0]
inc_mid = g["increase_range"][1]
inc_worst = g["increase_range"][2]
pac_cons = g["per_acre_increase"][0]
pac_mid = g["per_acre_increase"][1]
pac_worst = g["per_acre_increase"][2]
pct_cons = g["pct_increase"][0]
pct_mid = g["pct_increase"][1]
pct_worst = g["pct_increase"][2]

fert_2025 = d["fertilizer"]["2025"]
fert_mid = d["fertilizer"]["2026_mid"]
fuel_2025 = d["fuel"]["2025"]
fuel_mid = d["fuel"]["2026_mid"]
dry_2025 = d["drying"]["2025"]
dry_mid = d["drying"]["2026_mid"]

# Rounded toplines for speaking notes
r_2025 = round(grand_2025 / 1000) * 1000
r_cons = round(grand_cons / 1000) * 1000
r_worst = round(grand_worst / 1000) * 1000
r_inc_low = round(inc_cons / 1000) * 1000
r_inc_high = round(inc_worst / 1000) * 1000

print("=== NEW VALUES ===")
print(f"2025: ${grand_2025:,}  ({r_2025:,})")
print(f"2026: ${grand_cons:,} / ${grand_mid:,} / ${grand_worst:,}")
print(f"Inc:  ${inc_cons:,} / ${inc_mid:,} / ${inc_worst:,}")
print(f"PAC:  ${pac_cons} / ${pac_mid} / ${pac_worst}")
print(f"PCT:  {pct_cons}% / {pct_mid}% / {pct_worst}%")
print(f"Fert: ${fert_2025:,} -> ${fert_mid:,}")
print(f"Fuel: ${fuel_2025:,} -> ${fuel_mid:,}")
print(f"Dry:  ${dry_2025:,} -> ${dry_mid:,}")
print(f"Topline: ~${r_2025:,} -> ~${r_cons:,}-${r_worst:,}, inc ~${r_inc_low:,}-${r_inc_high:,}")

# ============================================================
# REBUILD PER-ACRE / PER-CATEGORY VALUES FOR TABLES
# ============================================================
# From the model: OMAFRA per-acre costs × escalation
# We need individual category values for all 3 scenarios

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from farm_cost_impact_model import OMAFRA_2025, ESCALATION

o = OMAFRA_2025
acres = 500

cat_data = {
    "N Fertilizer": {
        "base": o["n_fertilizer_per_acre"] * acres,
        "esc": ESCALATION["nitrogen"]
    },
    "P2O5 Fertilizer": {
        "base": o["p2o5_fertilizer_per_acre"] * acres,
        "esc": ESCALATION["phosphate"]
    },
    "K2O Fertilizer": {
        "base": o["k2o_fertilizer_per_acre"] * acres,
        "esc": ESCALATION["potash"]
    },
    "Fuel + Lubricant": {
        "base": o["fuel_and_lube_per_acre"] * acres,
        "esc": ESCALATION["fuel"]
    },
    "Drying": {
        "base": o["drying_per_acre"] * acres,
        "esc": ESCALATION["drying"]
    },
}

# Calculate subtotals for the Word table groupings
# Table groups: Fertilizer (N+P+K), Fuel, Drying
fert_cats = ["N Fertilizer", "P2O5 Fertilizer", "K2O Fertilizer"]
fc = {s: sum(cat_data[c]["base"] * (1 + cat_data[c]["esc"][s]) for c in fert_cats)
      for s in ["conservative", "mid", "worst"]}
fc["base"] = sum(cat_data[c]["base"] for c in fert_cats)

fu = cat_data["Fuel + Lubricant"]
fu_vals = {"base": fu["base"]}
for s in ["conservative", "mid", "worst"]:
    fu_vals[s] = fu["base"] * (1 + fu["esc"][s])

dr = cat_data["Drying"]
dr_vals = {"base": dr["base"]}
for s in ["conservative", "mid", "worst"]:
    dr_vals[s] = dr["base"] * (1 + dr["esc"][s])

print(f"\n=== TABLE VALUES ===")
print(f"Fert:  ${fc['base']:,.0f}  ${fc['conservative']:,.0f}  ${fc['mid']:,.0f}  ${fc['worst']:,.0f}")
print(f"Fuel:  ${fu_vals['base']:,.0f}  ${fu_vals['conservative']:,.0f}  ${fu_vals['mid']:,.0f}  ${fu_vals['worst']:,.0f}")
print(f"Dry:   ${dr_vals['base']:,.0f}  ${dr_vals['conservative']:,.0f}  ${dr_vals['mid']:,.0f}  ${dr_vals['worst']:,.0f}")

# ============================================================
# LOAD AND UPDATE THE DOCUMENT
# ============================================================
doc = Document(DOC_PATH)
changes = []

# First, dump current state for debugging
print(f"\n=== CURRENT PARAGRAPH SCAN ===")
for i, para in enumerate(doc.paragraphs):
    text = para.text.strip()
    if text and ("$" in text or "percent" in text.lower()):
        print(f"  [{i}] {text[:160]}")

# PARAGRAPH UPDATES
for i, para in enumerate(doc.paragraphs):
    text = para.text.strip()
    if not text or not para.runs:
        continue

    updated = None

    # KEY FINDING
    if "KEY FINDING" in text and ("$54,000" in text or "$30,000" in text):
        updated = (
            f"KEY FINDING: A 500-acre corn farm faces an estimated cost increase of "
            f"${r_inc_low:,} to ${r_inc_high:,} (+{pct_mid}% at midpoint) in combined fertilizer, fuel, and grain "
            f"drying costs. A 200-acre vegetable operation faces a $10,000 to $12,000 increase "
            f"(+48%) in nitrogen fertilizer costs alone. This analysis excludes crop protection, "
            f"seed, and machinery parts, which represent additional inflationary pressures not "
            f"quantified here."
        )
        changes.append(f"PARA {i}: KEY FINDING")

    # Top-line message
    elif "The war in Iran" in text and ("$54,000" in text or "$30,000" in text or "40 percent" in text):
        updated = (
            '"The war in Iran and the closure of the Strait of Hormuz have sent energy and '
            "fertilizer costs soaring for Ontario farmers. We're looking at cost increases of "
            f"over {pct_mid} percent on the inputs farmers need for spring planting \u2014 fertilizer, "
            f"diesel fuel, and grain drying. For a 500-acre corn farm, that's an "
            f"additional ${r_inc_low:,} to ${r_inc_high:,} this year. For vegetable growers, nitrogen costs "
            f"alone are up nearly 50 percent. These are real, immediate costs that farmers "
            f'cannot pass on to the consumer."'
        )
        changes.append(f"PARA {i}: Top-line message")

    # Grain talking point 1 — topline cost
    elif "500-acre corn farm" in text and ("$166,000" in text or "$165,000" in text or "$188,000" in text):
        updated = (
            f"A 500-acre corn farm in Ontario spent about "
            f"${r_2025:,} on fertilizer, fuel, and grain drying last year. This spring, "
            f"that same package of inputs costs ${r_cons:,} to ${r_worst:,} \u2014 a ${r_inc_low:,} to "
            f"${r_inc_high:,} increase."
        )
        changes.append(f"PARA {i}: Grain talking point 1")

    # Grain talking point 2 — per-acre
    elif "midpoint of our estimates" in text and ("per acre" in text or "percent increase" in text):
        updated = (
            f"At the midpoint of our estimates, that's a {pct_mid} percent increase, or an "
            f"additional ${pac_mid} per acre. That's money that goes straight off the bottom line."
        )
        changes.append(f"PARA {i}: Grain talking point 2")

    # Assumptions line
    elif "Assumptions:" in text and ("500 acres" in text or "corn" in text.lower()):
        updated = (
            "Assumptions: 500 acres grain corn, no-till, per OMAFRA Publication 60 "
            "(2025 Field Crop Budgets, p.12). Yield: 193 bu/ac. Fertility: 171 kg/ha N "
            "(as UAN 28-0-0), 89 kg/ha P\u2082O\u2085, 60 kg/ha K\u2082O. "
            "Diesel: 16 L/ac (no-till). Drying: $20.85/tonne, 8 points."
        )
        changes.append(f"PARA {i}: Assumptions")

    if updated:
        for run in para.runs:
            run.text = ""
        para.runs[0].text = updated

# TABLE CELL REPLACEMENTS
# Build old -> new mapping for table cells
# We need to find what's currently in the tables and replace
# Current values from the previous pure-corn model:
OLD_TABLE = {
    # Table 1: Cost summary
    # Fertilizer row
    "$102,186": f"${fc['base']:,.0f}",
    "$129,938": f"${fc['conservative']:,.0f}",
    "$136,454": f"${fc['mid']:,.0f}",
    "$144,465": f"${fc['worst']:,.0f}",
    # Fuel row
    "$14,500": f"${fu_vals['base']:,.0f}",
    "$13,282": f"${fu_vals['base']:,.0f}",
    "$25,500": f"${fu_vals['conservative']:,.0f}",
    "$23,362": f"${fu_vals['conservative']:,.0f}",
    "$26,875": f"${fu_vals['mid']:,.0f}",
    "$24,618": f"${fu_vals['mid']:,.0f}",
    "$27,750": f"${fu_vals['worst']:,.0f}",
    "$25,406": f"${fu_vals['worst']:,.0f}",
    # Drying row
    "$49,054": f"${dr_vals['base']:,.0f}",
    "$64,724": f"${dr_vals['conservative']:,.0f}",
    "$71,536": f"${dr_vals['mid']:,.0f}",
    "$78,350": f"${dr_vals['worst']:,.0f}",
    # Totals row
    "$165,740": f"${grand_2025:,}",
    "$164,522": f"${grand_2025:,}",
    "$220,162": f"${grand_cons:,}",
    "$218,020": f"${grand_cons:,}",
    "$234,865": f"${grand_mid:,}",
    "$232,608": f"${grand_mid:,}",
    "$250,565": f"${grand_worst:,}",
    "$248,234": f"${grand_worst:,}",
    # Table 2: Increase metrics
    "$54,422": f"${inc_cons:,}",
    "$53,498": f"${inc_cons:,}",
    "$69,125": f"${inc_mid:,}",
    "$68,086": f"${inc_mid:,}",
    "$84,825": f"${inc_worst:,}",
    "$83,712": f"${inc_worst:,}",
    "+33%": f"+{pct_cons}%",
    "+42%": f"+{pct_mid}%",
    "+51%": f"+{pct_worst}%",
    "$109/ac": f"${pac_cons}/ac",
    "$107/ac": f"${pac_cons}/ac",
    "$138/ac": f"${pac_mid}/ac",
    "$136/ac": f"${pac_mid}/ac",
    "$170/ac": f"${pac_worst}/ac",
    "$167/ac": f"${pac_worst}/ac",
}

for t_idx, table in enumerate(doc.tables):
    for r_idx, row in enumerate(table.rows):
        for c_idx, cell in enumerate(row.cells):
            text = cell.text.strip()
            if text in OLD_TABLE:
                new_val = OLD_TABLE[text]
                if text != new_val:
                    if cell.paragraphs and cell.paragraphs[0].runs:
                        for run in cell.paragraphs[0].runs:
                            run.text = ""
                        cell.paragraphs[0].runs[0].text = new_val
                    else:
                        cell.paragraphs[0].text = new_val
                    changes.append(f"TABLE {t_idx} R{r_idx} C{c_idx}: {text} -> {new_val}")

doc.save(DOC_PATH)

print(f"\n=== CHANGES APPLIED ({len(changes)}) ===")
for c in changes:
    print(f"  {c}")
print(f"\nDocument saved: {DOC_PATH}")
