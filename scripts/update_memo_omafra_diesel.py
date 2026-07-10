"""
Update Word doc for OMAFRA diesel rate change (22.90 L/ac no-till).
Only the fuel-affected values need updating — fertilizer and drying unchanged.
"""
import json
from docx import Document

DOC_PATH = (
    r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture"
    r"\Desktop\Ben Desktop Files\Farm Business Confidence Survey"
    r"\2025\Specififc Issue spekaing notes"
    r"\Energy and Fertilizer Shock Memo and Speaking Notes.docx"
)

with open("data/farm_cost_impact_results.json", "r") as f:
    r = json.load(f)
with open("data/farm_cost_impact_data.json", "r") as f:
    DATA = json.load(f)

g = r["grain_farm_500ac"]

# Recalculate exact fuel values
acres = 500
diesel_l_per_ac = 22.9  # OMAFRA no-till
diesel_litres = acres * diesel_l_per_ac
fuel_base = DATA["baseline_2025"]["fuel"]["diesel_coloured_farm"]["price_per_litre"]
fuel_est = DATA["estimated_april_2026_ontario"]["fuel"]["diesel_coloured_farm"]

fuel_2025 = round(diesel_litres * fuel_base)
fuel_cons = round(diesel_litres * fuel_est["working_range"]["low"])
fuel_mid = round(diesel_litres * fuel_est["midpoint"])
fuel_worst = round(diesel_litres * fuel_est["working_range"]["high"])

# Fert and drying unchanged
fert_2025 = 102186
fert_cons = 129938
fert_mid = 136454
fert_worst = 144465
dry_2025 = 49054
dry_cons = 64724
dry_mid = 71536
dry_worst = 78350

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

print(f"Diesel: {diesel_litres} L x ${fuel_base} = ${fuel_2025:,}")
print(f"Total 2025: ${grand_2025:,}  Mid 2026: ${grand_mid:,}  Inc: ${inc_mid:,} ({pct_mid}%)")
print(f"Per acre: ${pac_mid}/ac")

# Cell replacements: old corn values -> new OMAFRA values
CELL_MAP = {
    # Fuel row only
    "$14,500": f"${fuel_2025:,}",
    "$25,500": f"${fuel_cons:,}",
    "$26,875": f"${fuel_mid:,}",
    "$27,750": f"${fuel_worst:,}",
    # Totals
    "$165,740": f"${grand_2025:,}",
    "$220,162": f"${grand_cons:,}",
    "$234,865": f"${grand_mid:,}",
    "$250,565": f"${grand_worst:,}",
    # Increase table
    "$54,422": f"${inc_cons:,}",
    "$69,125": f"${inc_mid:,}",
    "$84,825": f"${inc_worst:,}",
    f"+33%": f"+{pct_cons}%",
    f"+42%": f"+{pct_mid}%",
    f"+51%": f"+{pct_worst}%",
    "$109/ac": f"${pac_cons}/ac",
    "$138/ac": f"${pac_mid}/ac",
    "$170/ac": f"${pac_worst}/ac",
}

# Round the topline numbers for speaking notes
topline_2025 = round(grand_2025 / 1000) * 1000  # $165,000
topline_cons = round(grand_cons / 1000) * 1000
topline_worst = round(grand_worst / 1000) * 1000
topline_inc_low = round(inc_cons / 1000) * 1000
topline_inc_high = round(inc_worst / 1000) * 1000

print(f"\nTopline: ${topline_2025:,} -> ${topline_cons:,}-${topline_worst:,}")
print(f"Topline inc: ${topline_inc_low:,} - ${topline_inc_high:,}")

doc = Document(DOC_PATH)
changes = []

# PARAGRAPH REPLACEMENTS
for i, para in enumerate(doc.paragraphs):
    text = para.text.strip()
    if not text:
        continue

    # KEY FINDING
    if "KEY FINDING" in text and "$54,000 to $85,000" in text:
        new_text = (
            f"KEY FINDING: A 500-acre corn farm faces an estimated cost increase of "
            f"${topline_inc_low:,} to ${topline_inc_high:,} (+{pct_mid}% at midpoint) in combined fertilizer, fuel, and grain "
            f"drying costs. A 200-acre vegetable operation faces a $10,000 to $12,000 increase "
            f"(+48%) in nitrogen fertilizer costs alone. This analysis excludes crop protection, "
            f"seed, and machinery parts, which represent additional inflationary pressures not "
            f"quantified here."
        )
        for run in para.runs:
            run.text = ""
        para.runs[0].text = new_text
        changes.append(f"PARA {i}: KEY FINDING")

    # Top-line message
    if "The war in Iran" in text and "$54,000 to $85,000" in text:
        new_text = (
            '"The war in Iran and the closure of the Strait of Hormuz have sent energy and '
            "fertilizer costs soaring for Ontario farmers. We're looking at cost increases of "
            f"over 40 percent on the inputs farmers need for spring planting \u2014 fertilizer, "
            f"diesel fuel, and grain drying. For a 500-acre corn farm, that's an "
            f"additional ${topline_inc_low:,} to ${topline_inc_high:,} this year. For vegetable growers, nitrogen costs "
            f"alone are up nearly 50 percent. These are real, immediate costs that farmers "
            f'cannot pass on to the consumer."'
        )
        for run in para.runs:
            run.text = ""
        para.runs[0].text = new_text
        changes.append(f"PARA {i}: Top-line message")

    # Grain talking point 1
    if "500-acre corn farm" in text and "$166,000" in text:
        new_text = (
            f"A 500-acre corn farm in Ontario spent about "
            f"${topline_2025:,} on fertilizer, fuel, and grain drying last year. This spring, "
            f"that same package of inputs costs ${topline_cons:,} to ${topline_worst:,} \u2014 a ${topline_inc_low:,} to "
            f"${topline_inc_high:,} increase."
        )
        for run in para.runs:
            run.text = ""
        para.runs[0].text = new_text
        changes.append(f"PARA {i}: Grain talking point 1")

    # Grain talking point 2
    if "midpoint of our estimates" in text and "$138 per acre" in text:
        new_text = (
            f"At the midpoint of our estimates, that's a {pct_mid} percent increase, or an "
            f"additional ${pac_mid} per acre. That's money that goes straight off the bottom line."
        )
        for run in para.runs:
            run.text = ""
        para.runs[0].text = new_text
        changes.append(f"PARA {i}: Grain talking point 2")

    # Assumptions line
    if "Assumptions:" in text and "500 acres grain corn" in text:
        new_text = (
            "Assumptions: 500 acres grain corn, no-till, "
            "typical nutrient application rates per OMAFRA guidelines (150 lbs N/ac, "
            "50 lbs P\u2082O\u2085/ac, 80 lbs K\u2082O/ac). Diesel: 22.90 L/ac per OMAFRA 2025 "
            "Field Crop Budget. Corn dried from 25% to 15% moisture."
        )
        for run in para.runs:
            run.text = ""
        para.runs[0].text = new_text
        changes.append(f"PARA {i}: Assumptions")

# TABLE CELL REPLACEMENTS
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

doc.save(DOC_PATH)

print(f"\n=== CHANGES APPLIED ({len(changes)}) ===")
for c in changes:
    print(f"  {c}")
print(f"\nSaved: {DOC_PATH}")
