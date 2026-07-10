"""
Comprehensive update of the Word document to reflect 500-acre PURE CORN scenario.
Scans every paragraph and table cell, updates all Scenario 1 references.
"""

import json
import re
from docx import Document

DOC_PATH = (
    r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture"
    r"\Desktop\Ben Desktop Files\Farm Business Confidence Survey"
    r"\2025\Specififc Issue spekaing notes"
    r"\Energy and Fertilizer Shock Memo and Speaking Notes.docx"
)

# Load the model results
with open("data/farm_cost_impact_results.json", "r") as f:
    results = json.load(f)

g = results["grain_farm_500ac"]

# New correct values
NEW = {
    "total_2025": 165740,
    "total_2026_cons": int(g["total_2026_range"][0]),
    "total_2026_mid": int(g["total_2026_range"][1]),
    "total_2026_worst": int(g["total_2026_range"][2]),
    "inc_cons": int(g["increase_range"][0]),
    "inc_mid": int(g["increase_range"][1]),
    "inc_worst": int(g["increase_range"][2]),
    "pac_cons": int(g["per_acre_increase"][0]),
    "pac_mid": int(g["per_acre_increase"][1]),
    "pac_worst": int(g["per_acre_increase"][2]),
    "pct_mid": round((g["total_2026_range"][1] / g["total_2025"] - 1) * 100),
    "fert_2025": int(g["details"]["fertilizer"]["2025"]),
    "fert_2026_mid": int(g["details"]["fertilizer"]["2026_mid"]),
    "fuel_2025": int(g["details"]["fuel"]["2025"]),
    "fuel_2026_mid": int(g["details"]["fuel"]["2026_mid"]),
    "dry_2025": int(g["details"]["drying"]["2025"]),
    "dry_2026_mid": int(g["details"]["drying"]["2026_mid"]),
}

print("NEW VALUES:")
for k, v in NEW.items():
    print(f"  {k}: {v:,}")

# ============================================================
# Define all text replacements
# ============================================================
# Each tuple: (old_text_fragment, new_text_fragment, description)
# We match on unique substrings to find the right paragraph

PARAGRAPH_REPLACEMENTS = [
    # KEY FINDING paragraph
    {
        "match": "KEY FINDING",
        "old_fragments": ["$30,000 to $48,000", "+40% at midpoint"],
        "new_text": (
            "KEY FINDING: A 500-acre corn farm faces an estimated cost increase of "
            "$54,000 to $85,000 (+42% at midpoint) in combined fertilizer, fuel, and grain "
            "drying costs. A 200-acre vegetable operation faces a $10,000 to $12,000 increase "
            "(+48%) in nitrogen fertilizer costs alone. This analysis excludes crop protection, "
            "seed, and machinery parts, which represent additional inflationary pressures not "
            "quantified here."
        ),
        "desc": "KEY FINDING box"
    },

    # Top-line message
    {
        "match": "The war in Iran",
        "old_fragments": ["40 to 50 percent", "$30,000 to $50,000"],
        "new_text": (
            '"The war in Iran and the closure of the Strait of Hormuz have sent energy and '
            "fertilizer costs soaring for Ontario farmers. We're looking at cost increases of "
            "over 40 percent on the inputs farmers need for spring planting \u2014 fertilizer, "
            "diesel fuel, and grain drying. For a 500-acre corn farm, that's an "
            "additional $54,000 to $85,000 this year. For vegetable growers, nitrogen costs "
            "alone are up nearly 50 percent. These are real, immediate costs that farmers "
            'cannot pass on to the consumer."'
        ),
        "desc": "Top-line message"
    },

    # Grain farm talking point 1
    {
        "match": "500-acre corn, soybean, and wheat farm",
        "old_fragments": ["$98,000", "$128,000 to $146,000", "$30,000"],
        "new_text": (
            "A 500-acre corn farm in Ontario spent about "
            "$166,000 on fertilizer, fuel, and grain drying last year. This spring, "
            "that same package of inputs costs $220,000 to $251,000 \u2014 a $54,000 to "
            "$85,000 increase."
        ),
        "desc": "Grain talking point 1"
    },

    # Grain farm talking point 2 - per acre
    {
        "match": "midpoint of our estimates",
        "old_fragments": ["$78 per acre"],
        "new_text": (
            "At the midpoint of our estimates, that's a 42 percent increase, or an "
            "additional $138 per acre. That's money that goes straight off the bottom line."
        ),
        "desc": "Grain talking point 2 (per acre)"
    },

    # Assumptions line
    {
        "match": "Assumptions:",
        "old_fragments": ["Corn-soybean-wheat rotation"],
        "new_text": (
            "Assumptions: 500 acres grain corn, minimum-till, "
            "typical nutrient application rates per OMAFRA guidelines (150 lbs N/ac, "
            "50 lbs P\u2082O\u2085/ac, 80 lbs K\u2082O/ac). Corn dried from 25% to 15% moisture."
        ),
        "desc": "Assumptions line"
    },
]

# TABLE CELL REPLACEMENTS (exact value matches)
TABLE_REPLACEMENTS = {
    # Table 1: Scenario 1 cost summary — old -> new
    # Fertilizer row
    "$65,182": f"${NEW['fert_2025']:,}",
    "$69,750": f"${NEW['total_2026_cons'] - NEW['fuel_2026_mid'] - NEW['dry_2026_mid'] + (NEW['fuel_2025'] - NEW['fuel_2025']) + 4000:,}",  # approximate
    "$84,420": f"${NEW['fert_2026_mid']:,}",
    # Fuel row stays same if it was for 200ac corn... but now it's 500ac
    "$12,760": f"${NEW['fuel_2025']:,}",
    # Drying row
    "$19,621": f"${NEW['dry_2025']:,}",
    # Totals
    "$97,563": f"${NEW['total_2025']:,}",
    "$127,993": f"${NEW['total_2026_cons']:,}",
    "$136,685": f"${NEW['total_2026_mid']:,}",
    "$145,692": f"${NEW['total_2026_worst']:,}",
    # Increase table
    "$30,430": f"${NEW['inc_cons']:,}",
    "$39,121": f"${NEW['inc_mid']:,}",
    "$48,128": f"${NEW['inc_worst']:,}",
    "+31%": f"+{round((NEW['total_2026_cons']/NEW['total_2025']-1)*100)}%",
    "$61/ac": f"${NEW['pac_cons']:,}/ac",
    "$78/ac": f"${NEW['pac_mid']:,}/ac",
    "$96/ac": f"${NEW['pac_worst']:,}/ac",
}

# Let me recalculate the cons/worst fertilizer and fuel/drying values properly
# by loading the full JSON
fert_cons = NEW["total_2026_cons"] - (12500 * 2.04) - (68130 * 0.95)
fert_worst = NEW["total_2026_worst"] - (12500 * 2.22) - (68130 * 1.15)

doc = Document(DOC_PATH)
changes = []

# ============================================================
# PARAGRAPH REPLACEMENTS
# ============================================================
for i, para in enumerate(doc.paragraphs):
    text = para.text.strip()
    if not text:
        continue

    for repl in PARAGRAPH_REPLACEMENTS:
        if repl["match"] in text and all(f in text for f in repl["old_fragments"]):
            # Preserve formatting from first run
            if para.runs:
                for run in para.runs:
                    run.text = ""
                para.runs[0].text = repl["new_text"]
            else:
                para.text = repl["new_text"]
            changes.append(f"PARA {i}: {repl['desc']}")
            break

# ============================================================
# TABLE CELL REPLACEMENTS
# ============================================================
# We need to be smarter — get exact values from JSON rather than approximate
# Load the full results to get all individual cost components

# Recalculate individual table values from the model
with open("data/farm_cost_impact_data.json", "r") as f:
    DATA = json.load(f)

# Exact values from the model run
fert_base = DATA["baseline_2025"]["fertilizer"]
fert_est = DATA["estimated_april_2026_ontario"]["fertilizer"]
fuel_base = DATA["baseline_2025"]["fuel"]
fuel_est = DATA["estimated_april_2026_ontario"]["fuel"]
rates = DATA["application_rates"]
conv = rates["conversions"]

# 500 acres corn
acres = 500
n_rate = 150
p_rate = 50
k_rate = 80

total_n = acres * n_rate  # 75000
total_p = acres * p_rate  # 25000
total_k = acres * k_rate  # 40000

map_lbs = total_p / conv["map_p2o5_content"]
map_tonnes = map_lbs / conv["lbs_per_tonne"]
n_from_map = map_lbs * conv["map_n_content"]
remaining_n = total_n - n_from_map
urea_lbs = remaining_n / conv["urea_n_content"]
urea_tonnes = urea_lbs / conv["lbs_per_tonne"]
mop_lbs = total_k / conv["mop_k2o_content"]
mop_tonnes = mop_lbs / conv["lbs_per_tonne"]

# Individual fertilizer costs
def fc(tonnes, base_key, est_key, scenario):
    bp = fert_base[base_key]["price_per_tonne"]
    ep = fert_est[est_key]
    if scenario == "2025":
        return round(tonnes * bp)
    elif scenario == "cons":
        return round(tonnes * ep["working_range"]["low"])
    elif scenario == "mid":
        return round(tonnes * ep["midpoint"])
    elif scenario == "worst":
        return round(tonnes * ep["working_range"]["high"])

urea_2025 = fc(urea_tonnes, "urea_46_0_0", "urea_46_0_0", "2025")
urea_cons = fc(urea_tonnes, "urea_46_0_0", "urea_46_0_0", "cons")
urea_mid = fc(urea_tonnes, "urea_46_0_0", "urea_46_0_0", "mid")
urea_worst = fc(urea_tonnes, "urea_46_0_0", "urea_46_0_0", "worst")

map_2025 = fc(map_tonnes, "map_11_52_0", "map_11_52_0", "2025")
map_cons = fc(map_tonnes, "map_11_52_0", "map_11_52_0", "cons")
map_mid = fc(map_tonnes, "map_11_52_0", "map_11_52_0", "mid")
map_worst = fc(map_tonnes, "map_11_52_0", "map_11_52_0", "worst")

mop_2025 = fc(mop_tonnes, "potash_mop_0_0_60", "potash_mop_0_0_60", "2025")
mop_cons = fc(mop_tonnes, "potash_mop_0_0_60", "potash_mop_0_0_60", "cons")
mop_mid = fc(mop_tonnes, "potash_mop_0_0_60", "potash_mop_0_0_60", "mid")
mop_worst = fc(mop_tonnes, "potash_mop_0_0_60", "potash_mop_0_0_60", "worst")

fert_2025 = urea_2025 + map_2025 + mop_2025
fert_cons = urea_cons + map_cons + mop_cons
fert_mid = urea_mid + map_mid + mop_mid
fert_worst = urea_worst + map_worst + mop_worst

# Fuel
diesel_litres = acres * 25
fuel_2025 = round(diesel_litres * fuel_base["diesel_coloured_farm"]["price_per_litre"])
fuel_cons = round(diesel_litres * fuel_est["diesel_coloured_farm"]["working_range"]["low"])
fuel_mid = round(diesel_litres * fuel_est["diesel_coloured_farm"]["midpoint"])
fuel_worst = round(diesel_litres * fuel_est["diesel_coloured_farm"]["working_range"]["high"])

# Drying
corn_yield = rates["grain_crops"]["corn"]["yield_bu_per_acre"]["typical"]
bushels = acres * corn_yield
pts = rates["grain_crops"]["corn"]["drying_moisture_removal_points"]
ppb = rates["grain_crops"]["corn"]["propane_gal_per_point_per_bu"]
propane_gal = bushels * pts * ppb
propane_litres = propane_gal * conv["litres_per_us_gallon"]

prop_2025_data = DATA["fuel_april_2026"]["propane"]["lock_in_2025"]
prop_2026_data = DATA["fuel_april_2026"]["propane"]["spot_2026_estimated"]
prop_2025_avg = (prop_2025_data["low"] + prop_2025_data["high"]) / 2
prop_2026_low = prop_2026_data["low"]
prop_2026_mid = (prop_2026_data["low"] + prop_2026_data["high"]) / 2
prop_2026_high = prop_2026_data["high"]

dry_2025 = round(propane_litres * prop_2025_avg)
dry_cons = round(propane_litres * prop_2026_low)
dry_mid = round(propane_litres * prop_2026_mid)
dry_worst = round(propane_litres * prop_2026_high)

# Grand totals
grand_2025 = fert_2025 + fuel_2025 + dry_2025
grand_cons = fert_cons + fuel_cons + dry_cons
grand_mid = fert_mid + fuel_mid + dry_mid
grand_worst = fert_worst + fuel_worst + dry_worst

inc_cons = grand_cons - grand_2025
inc_mid = grand_mid - grand_2025
inc_worst = grand_worst - grand_2025

pac_cons = round(inc_cons / acres)
pac_mid = round(inc_mid / acres)
pac_worst = round(inc_worst / acres)

pct_cons = round((grand_cons / grand_2025 - 1) * 100)
pct_mid = round((grand_mid / grand_2025 - 1) * 100)
pct_worst = round((grand_worst / grand_2025 - 1) * 100)

print(f"\n=== EXACT TABLE VALUES ===")
print(f"Fert:   2025=${fert_2025:,}  cons=${fert_cons:,}  mid=${fert_mid:,}  worst=${fert_worst:,}")
print(f"Fuel:   2025=${fuel_2025:,}  cons=${fuel_cons:,}  mid=${fuel_mid:,}  worst=${fuel_worst:,}")
print(f"Dry:    2025=${dry_2025:,}  cons=${dry_cons:,}  mid=${dry_mid:,}  worst=${dry_worst:,}")
print(f"TOTAL:  2025=${grand_2025:,}  cons=${grand_cons:,}  mid=${grand_mid:,}  worst=${grand_worst:,}")
print(f"INC:    cons=${inc_cons:,}  mid=${inc_mid:,}  worst=${inc_worst:,}")
print(f"PAC:    cons=${pac_cons:,}  mid=${pac_mid:,}  worst=${pac_worst:,}")
print(f"PCT:    cons={pct_cons}%  mid={pct_mid}%  worst={pct_worst}%")

# Build exact cell-level replacement map: old_value -> new_value
CELL_MAP = {
    # Table 1: Cost summary (Fertilizer row)
    "$65,182": f"${fert_2025:,}",
    "$69,750": f"${fert_cons:,}",
    "$84,420": f"${fert_mid:,}",
    "$99,497": f"${fert_worst:,}",
    # Fuel row
    "$12,760": f"${fuel_2025:,}",
    "$22,440": f"${fuel_cons:,}",
    "$23,650": f"${fuel_mid:,}",
    "$24,420": f"${fuel_worst:,}",
    # Drying row
    "$19,621": f"${dry_2025:,}",
    "$25,803": f"${dry_cons:,}",
    "$28,615": f"${dry_mid:,}",
    "$31,247": f"${dry_worst:,}",
    # Total row
    "$97,563": f"${grand_2025:,}",
    "$127,993": f"${grand_cons:,}",
    "$136,685": f"${grand_mid:,}",
    "$145,692": f"${grand_worst:,}",
    # Table 2: Increase metrics
    "$30,430": f"${inc_cons:,}",
    "$39,121": f"${inc_mid:,}",
    "$48,128": f"${inc_worst:,}",
    "+31%": f"+{pct_cons}%",
    "+40%": f"+{pct_mid}%",
    "+49%": f"+{pct_worst}%",
    "$61/ac": f"${pac_cons}/ac",
    "$78/ac": f"${pac_mid}/ac",
    "$96/ac": f"${pac_worst}/ac",
}

print(f"\n=== CELL REPLACEMENTS ===")
for old, new in CELL_MAP.items():
    if old != new:
        print(f"  {old} -> {new}")

# Apply table cell replacements
for t_idx, table in enumerate(doc.tables):
    for r_idx, row in enumerate(table.rows):
        for c_idx, cell in enumerate(row.cells):
            text = cell.text.strip()
            if text in CELL_MAP:
                new_val = CELL_MAP[text]
                if text != new_val:
                    if cell.paragraphs and cell.paragraphs[0].runs:
                        for run in cell.paragraphs[0].runs:
                            run.text = ""
                        cell.paragraphs[0].runs[0].text = new_val
                    else:
                        cell.paragraphs[0].text = new_val
                    changes.append(f"TABLE {t_idx} R{r_idx} C{c_idx}: {text} -> {new_val}")

# Save
doc.save(DOC_PATH)

print(f"\n=== CHANGES APPLIED ({len(changes)}) ===")
for c in changes:
    print(f"  {c}")

print(f"\nDocument saved to: {DOC_PATH}")
