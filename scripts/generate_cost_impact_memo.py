"""
Generate OFA Memo & Speaking Notes: Iran War Impact on Ontario Farm Input Costs
===============================================================================
Produces a professional Word document with:
  1. Internal Memo (data-driven, with tables)
  2. Speaking Notes (narrative, quote-ready)
"""

import json
import os
from datetime import datetime

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT


def set_cell_shading(cell, color_hex):
    """Set cell background color."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), color_hex)
    shading.set(qn("w:val"), "clear")
    cell._tc.get_or_add_tcPr().append(shading)


def add_formatted_table(doc, headers, rows, col_widths=None, header_color="1B5E20"):
    """Add a professional formatted table."""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header row
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = header
        for paragraph in cell.paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in paragraph.runs:
                run.bold = True
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        set_cell_shading(cell, header_color)

    # Data rows
    for r_idx, row_data in enumerate(rows):
        for c_idx, val in enumerate(row_data):
            cell = table.rows[r_idx + 1].cells[c_idx]
            cell.text = str(val)
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(9)
                # Right-align numeric columns (all but first)
                if c_idx > 0:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            # Alternate row shading
            if r_idx % 2 == 1:
                set_cell_shading(cell, "F5F5F5")

    # Bold the last row if it looks like a total
    if rows and any("total" in str(v).lower() for v in rows[-1]):
        for cell in table.rows[-1].cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.bold = True

    return table


def build_document():
    """Build the complete Word document."""

    # Load results
    results_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", "farm_cost_impact_results.json"
    )
    with open(results_path, "r") as f:
        results = json.load(f)

    g = results["grain_farm_500ac"]
    v = results["vegetable_farm_200ac"]

    doc = Document()

    # ========================================
    # PAGE SETUP
    # ========================================
    for section in doc.sections:
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    # Default font
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Calibri"
    font.size = Pt(11)

    # ========================================
    # HEADER / TITLE
    # ========================================
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("ONTARIO FEDERATION OF AGRICULTURE")
    run.bold = True
    run.font.size = Pt(14)
    run.font.color.rgb = RGBColor(0x1B, 0x5E, 0x20)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run("INTERNAL MEMO & SPEAKING NOTES")
    run.bold = True
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    # Divider
    divider = doc.add_paragraph()
    divider.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = divider.add_run("_" * 70)
    run.font.color.rgb = RGBColor(0x1B, 0x5E, 0x20)

    # ========================================
    # MEMO HEADER BLOCK
    # ========================================
    memo_table = doc.add_table(rows=5, cols=2)
    memo_table.columns[0].width = Inches(1.2)
    memo_table.columns[1].width = Inches(5.3)

    memo_fields = [
        ("TO:", "OFA Board of Directors / Policy Team"),
        ("FROM:", "Research & Policy Division"),
        ("DATE:", datetime.now().strftime("%B %d, %Y")),
        ("RE:", "Impact of Iran Conflict on Ontario Farm Energy & Fertilizer Costs"),
        ("STATUS:", "DRAFT — Pending Ridgetown Spring 2026 Survey & StatsCan FIPI Q4 2025"),
    ]

    for i, (label, value) in enumerate(memo_fields):
        cell_label = memo_table.rows[i].cells[0]
        cell_label.text = label
        for p in cell_label.paragraphs:
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(10)
        cell_value = memo_table.rows[i].cells[1]
        cell_value.text = value
        for p in cell_value.paragraphs:
            for r in p.runs:
                r.font.size = Pt(10)

    doc.add_paragraph()  # spacer

    # ========================================
    # PART 1: INTERNAL MEMO
    # ========================================
    h1 = doc.add_heading("PART 1: INTERNAL MEMO — Cost Impact Analysis", level=1)
    for run in h1.runs:
        run.font.color.rgb = RGBColor(0x1B, 0x5E, 0x20)

    # Executive Summary
    doc.add_heading("Executive Summary", level=2)
    doc.add_paragraph(
        "The ongoing conflict in Iran and the near-total closure of the Strait of Hormuz have "
        "triggered severe disruptions to global energy and fertilizer supply chains. As of April 2026, "
        "Ontario farmers are facing dramatic year-over-year increases in their two largest variable "
        "input costs: fertilizer and fuel."
    )
    doc.add_paragraph(
        "This memo quantifies the impact on two representative Ontario farm operations using "
        "validated data from the Ridgetown Farm Input Monitoring Project (2025 baseline), the "
        "World Bank Commodity Markets group (March 2026 price indices), and the DTN Retail "
        "Fertilizer Index (March 2026). All estimates are presented as ranges across three "
        "scenarios (conservative, midpoint, worst-case) to reflect the inherent uncertainty in "
        "current market conditions."
    )

    # Key findings box
    p = doc.add_paragraph()
    run = p.add_run("KEY FINDING: ")
    run.bold = True
    run.font.color.rgb = RGBColor(0xC6, 0x28, 0x28)
    run = p.add_run(
        f"A typical 500-acre grain farm faces an estimated cost increase of "
        f"$30,000 to $48,000 (+40% at midpoint) in combined fertilizer, fuel, and grain "
        f"drying costs. A 200-acre vegetable operation faces a $10,000 to $12,000 increase "
        f"(+48%) in nitrogen fertilizer costs alone. This analysis excludes crop protection, "
        f"seed, and machinery parts, which represent additional inflationary pressures not "
        f"quantified here."
    )

    # Geopolitical Context
    doc.add_heading("Geopolitical Context", level=2)
    doc.add_paragraph(
        "In late February 2026, military operations involving Iran led to the near-total "
        "closure of the Strait of Hormuz — the chokepoint through which approximately 20-30% "
        "of global oil and one-third of global fertilizer trade transits. The consequences "
        "are being felt across multiple channels:"
    )

    bullets = [
        "Brent crude oil has surged to ~$110/barrel (April 7, 2026)",
        "The World Bank Fertilizer Price Index jumped 26.2% in March 2026 alone",
        "Global urea prices spiked 53.7% in a single month (March 2026)",
        "European natural gas prices rose 59.4% in March, driving up nitrogen fertilizer production costs",
        "Ontario retail diesel has reached ~$2.37/litre (vs. $1.35/L one year ago)",
        "Many Ontario producers entered spring 2026 with low on-farm fertilizer inventory, "
        "leaving them exposed to spot-market pricing",
    ]
    for bullet in bullets:
        doc.add_paragraph(bullet, style="List Bullet")

    # Ontario's Vulnerability
    doc.add_heading("Ontario's Specific Vulnerability", level=2)
    doc.add_paragraph(
        "While Canada is a net exporter of fertilizer overall (driven by Saskatchewan potash "
        "and Alberta nitrogen production), Ontario is effectively import-dependent for the "
        "nutrients it uses most:"
    )

    add_formatted_table(doc,
        ["Nutrient", "Canada Position", "Ontario Exposure"],
        [
            ["Potash (K)", "World's largest producer", "LOW — domestic supply secure"],
            ["Nitrogen (Urea/UAN)", "Net exporter overall", "HIGH — Eastern Canada is net importer"],
            ["Phosphate (DAP/MAP)", "Limited domestic production", "HIGH — almost entirely imported"],
        ]
    )

    doc.add_paragraph()
    doc.add_paragraph(
        "The Canada-wide 35% tariff on Russian fertilizer imports remains in effect, adding "
        "an estimated ~$100/tonne cost premium relative to U.S. farmers. Combined with the "
        "current Hormuz disruption, Ontario producers face a compounding cost disadvantage."
    )

    # ========================================
    # SCENARIO 1
    # ========================================
    doc.add_heading("Scenario 1: 500-Acre Grain Farm", level=2)
    doc.add_paragraph(
        "Assumptions: Corn-soybean-wheat rotation (200/175/125 acres), minimum-till, "
        "typical nutrient application rates per OMAFRA guidelines."
    )

    doc.add_heading("Cost Summary", level=3)

    add_formatted_table(doc,
        ["Category", "2025", "2026 (Cons.)", "2026 (Mid)", "2026 (Worst)"],
        [
            ["Fertilizer", "$65,182", "$69,750", "$84,420", "$99,497"],
            ["Field Fuel (Diesel)", "$12,760", "$22,440", "$23,650", "$24,420"],
            ["Grain Drying (Propane)", "$19,621", "$25,803", "$28,615", "$31,247"],
            ["TOTAL", "$97,563", "$127,993", "$136,685", "$145,692"],
        ]
    )

    doc.add_paragraph()

    add_formatted_table(doc,
        ["Metric", "Conservative", "Midpoint", "Worst-Case"],
        [
            ["Total Increase ($)", "$30,430", "$39,121", "$48,128"],
            ["Increase (%)", "+31%", "+40%", "+49%"],
            ["Per Acre Increase", "$61/ac", "$78/ac", "$96/ac"],
        ],
        header_color="B71C1C"
    )

    doc.add_paragraph()
    doc.add_heading("Key Price Drivers", level=3)

    add_formatted_table(doc,
        ["Input", "April 2025", "April 2026 (Est.)", "YoY Change"],
        [
            ["Urea (46-0-0)", "$819/tonne", "$1,190–$1,259/tonne", "+45% to +54%"],
            ["MAP (11-52-0)", "$1,164/tonne", "$1,236–$1,469/tonne", "+6% to +26%"],
            ["Potash (0-0-60)", "$678/tonne", "$705–$855/tonne", "+4% to +26%"],
            ["Farm Diesel (coloured)", "$1.16/litre", "$2.04–$2.22/litre", "+76% to +91%"],
            ["Propane (drying)", "~$0.72/litre", "~$0.95–$1.15/litre", "+32% to +60%"],
        ]
    )
    doc.add_paragraph()
    p = doc.add_paragraph()
    run = p.add_run("Source: ")
    run.italic = True
    run.font.size = Pt(9)
    run = p.add_run(
        "2025 baselines from Ridgetown Farm Input Monitoring Project (April 16, 2025). "
        "2026 estimates triangulated from World Bank Pink Sheet (March 2026), "
        "DTN Retail Fertilizer Index (March 2026), and news reports. "
        "Farm diesel estimated using validated 14% farm-bulk discount on retail prices."
    )
    run.italic = True
    run.font.size = Pt(9)

    # ========================================
    # SCENARIO 2
    # ========================================
    doc.add_heading("Scenario 2: 200-Acre Vegetable Farm", level=2)
    doc.add_paragraph(
        "Assumptions: Mixed vegetable operation (sweet corn, potatoes, processing tomatoes, "
        "peppers, leafy greens). This scenario focuses specifically on nitrogen/urea costs "
        "to illustrate the impact on farms that did not pre-purchase fertilizer."
    )

    add_formatted_table(doc,
        ["Crop", "Acres", "N Rate (lbs/ac)", "Total N (lbs)"],
        [
            ["Sweet Corn", "60", "135", "8,100"],
            ["Potatoes", "50", "175", "8,750"],
            ["Processing Tomatoes", "40", "120", "4,800"],
            ["Peppers", "25", "115", "2,875"],
            ["Leafy Greens", "25", "100", "2,500"],
            ["TOTAL", "200", "", "27,025"],
        ]
    )

    doc.add_paragraph()
    doc.add_paragraph(
        f"Total nitrogen demand: 27,025 lbs = 26.6 tonnes of urea (46-0-0)"
    )

    add_formatted_table(doc,
        ["Metric", "2025", "2026 (Range)"],
        [
            ["Urea Price", "$819/tonne", "$1,188–$1,259/tonne"],
            ["Total Urea Cost", "$21,825", "$31,659–$33,551"],
            ["Cost Per Acre", "$109/ac", "$158–$168/ac"],
            ["Increase", "—", "+$9,833 to +$11,725"],
            ["Increase (%)", "—", "+45% to +54%"],
        ],
        header_color="B71C1C"
    )

    # ========================================
    # METHODOLOGY NOTE
    # ========================================
    doc.add_heading("Methodology & Data Quality Notes", level=2)

    notes = [
        "The Ridgetown Campus spring 2026 survey has not yet been published. Our 2026 "
        "price estimates use a three-way triangulation methodology: (A) World Bank commodity "
        "index escalation applied to the 2025 Ontario baseline — representing current spot "
        "and replacement cost, (B) DTN U.S. retail prices converted to CAD and adjusted "
        "for the observed Ontario-vs-U.S. price relationship, and (C) validation against "
        "news and market reports. Method A represents the upper range; blended retail "
        "prices at local co-ops may be somewhat lower where dealers have pre-existing "
        "inventory purchased at earlier prices.",

        "The Ontario-vs-U.S. fertilizer price relationship was empirically validated using "
        "Ridgetown's own cross-border survey data. In April 2025, Ontario prices were actually "
        "6-12% cheaper than comparable U.S. prices on a currency-adjusted basis, driven "
        "by the weak Canadian dollar.",

        "Farm bulk diesel pricing was validated at a ~14% discount to retail pump prices, "
        "driven by the provincial fuel tax exemption (9¢/L) and bulk delivery margin savings. "
        "Note: all federal carbon fuel charge rates under the Greenhouse Gas Pollution Pricing "
        "Act were set to $0.00 effective April 1, 2025 — this applies to all consumers, not "
        "only agriculture.",

        "Statistics Canada's Farm Input Price Index (FIPI) for Q4 2025 releases on April 10, "
        "2026, and will provide additional official validation. These estimates should be "
        "updated when the Ridgetown spring 2026 survey is published.",

        "This analysis isolates fertilizer, fuel, and grain drying costs only. Crop "
        "protection products, seed, machinery parts, and labour represent additional "
        "inflationary pressures not quantified in this memo.",
    ]
    for note in notes:
        doc.add_paragraph(note, style="List Bullet")

    # ========================================
    # PAGE BREAK — SPEAKING NOTES
    # ========================================
    doc.add_page_break()

    h1 = doc.add_heading("PART 2: SPEAKING NOTES", level=1)
    for run in h1.runs:
        run.font.color.rgb = RGBColor(0x1B, 0x5E, 0x20)

    doc.add_paragraph(
        "The following sections provide ready-to-use language for media interviews, "
        "policy briefs, government delegations, and member communications."
    )

    # Top-line message
    doc.add_heading("Top-Line Message", level=2)
    p = doc.add_paragraph()
    run = p.add_run(
        '"The war in Iran and the closure of the Strait of Hormuz have sent energy and '
        "fertilizer costs soaring for Ontario farmers. We're looking at cost increases of "
        "40 to 50 percent on the inputs farmers need for spring planting — fertilizer, "
        "diesel fuel, and grain drying. For a typical 500-acre grain farm, that's an "
        "additional $30,000 to $50,000 this year. For vegetable growers, nitrogen costs "
        "alone are up nearly 50 percent. These are real, immediate costs that farmers "
        'cannot pass on to the consumer."'
    )
    run.italic = True

    # Grain farm talking points
    doc.add_heading("Talking Points: Grain Farm Costs", level=2)
    grain_points = [
        "A typical 500-acre corn, soybean, and wheat farm in Ontario spent about "
        "$98,000 on fertilizer, fuel, and grain drying last year. This spring, "
        "that same package of inputs costs $128,000 to $146,000 — a $30,000 to "
        "$48,000 increase.",

        "At the midpoint of our estimates, that's a 40 percent increase, or an "
        "additional $78 per acre. That's money that goes straight off the bottom line.",

        "Diesel fuel — which farmers use to run tractors, combines, and grain trucks — "
        "has nearly doubled. Farm diesel was $1.16 per litre last April. Today it's "
        "over $2.10. That is an 85 percent increase.",

        "Urea fertilizer, the primary source of nitrogen for corn and wheat, has "
        "gone from $819 per tonne to approximately $1,200 per tonne. That's a "
        "45 to 54 percent increase driven directly by the energy crisis in the "
        "Middle East.",

        "Farmers have no ability to pass these costs on. The price of corn and "
        "wheat is set by global commodity markets. When input costs go up and "
        "crop prices don't, the farmer absorbs the loss.",
    ]
    for point in grain_points:
        doc.add_paragraph(point, style="List Bullet")

    # Vegetable farm talking points
    doc.add_heading("Talking Points: Vegetable Farm Costs", level=2)
    veg_points = [
        "A typical 200-acre vegetable operation in Ontario needs about 27,000 pounds "
        "of nitrogen to grow sweet corn, potatoes, tomatoes, peppers, and leafy greens. "
        "Sourced as urea fertilizer, that's approximately 27 tonnes.",

        "Last year, that urea cost about $21,800. This spring, at current spot-market "
        "prices, that same fertilizer costs $31,700 to $33,600 — an increase of nearly "
        "$10,000 to $12,000, or 45 to 54 percent.",

        "The critical factor is timing. Farms that pre-purchased and locked in their "
        "fertilizer last fall are protected. But many Ontario vegetable growers purchase "
        "closer to planting — and they are now fully exposed to a market that has been "
        "dramatically disrupted by the Strait of Hormuz closure.",

        "Ontario is particularly vulnerable because Eastern Canada is a net importer "
        "of nitrogen and phosphate fertilizers. While Western Canada produces potash "
        "and nitrogen from natural gas, Ontario's supply depends on imports that must "
        "now navigate disrupted global shipping routes.",
    ]
    for point in veg_points:
        doc.add_paragraph(point, style="List Bullet")

    # Pre-purchase angle
    doc.add_heading("Talking Points: Pre-Purchase & Lock-In", level=2)
    prepurch_points = [
        "Many Ontario farmers in this increasingly volatile cost environment simply cannot afford "
        "to prepurchase and lock in inputs months in advance. That requires significant "
        "upfront capital that many operations — especially smaller family farms — do not "
        "have readily available.",

        "The farms that are hit hardest are the ones buying fertilizer at today's spot "
        "prices. Those are disproportionately smaller operations, new entrants, and farms "
        "with tighter cash flow — exactly the operations we can least afford to lose.",

        "This highlights the need for risk management tools and government programs "
        "that help farmers manage input cost volatility, not just production risk.",
    ]
    for point in prepurch_points:
        doc.add_paragraph(point, style="List Bullet")

    # Q&A
    doc.add_heading("Anticipated Questions & Responses", level=2)

    qas = [
        (
            "Q: Can't farmers just use less fertilizer?",
            "A: To some extent, yes — and some will. But reducing nitrogen on corn, for "
            "example, directly reduces yield. At current corn prices, the Most Economical "
            "Rate of Nitrogen calculated by OMAFRA's corn nitrogen calculator already "
            "accounts for the cost-benefit tradeoff. Cutting below that rate means "
            "losing more in yield value than you save in fertilizer."
        ),
        (
            "Q: Won't farmers just switch to soybeans instead of corn?",
            "A: Soybeans fix their own nitrogen, so they avoid the urea cost hit. Some "
            "farmers will shift acreage. But Ontario needs corn for the livestock sector, "
            "ethanol production, and food manufacturing. A widespread shift away from corn "
            "creates supply chain problems downstream."
        ),
        (
            "Q: Are these estimates conservative or aggressive?",
            "A: We present three scenarios. Our conservative estimate uses the lowest "
            "available price data; our worst-case uses the highest. Our midpoint is the "
            "average of three independent estimation methods. All are based on publicly "
            "available data from the World Bank, the University of Guelph, and the DTN "
            "agricultural market service. When Statistics Canada releases its Farm Input "
            "Price Index for Q4 2025 on April 10, we will incorporate that as additional "
            "validation."
        ),
        (
            "Q: How does this compare to the 2022 fertilizer crisis?",
            "A: The 2022 situation (Russia-Ukraine) primarily affected potash and natural "
            "gas markets. This crisis is broader — it's simultaneously disrupting oil, "
            "LNG, and fertilizer trade through a single chokepoint. The speed of the "
            "price increase is also more severe: urea jumped 54% in a single month."
        ),
    ]

    for q, a in qas:
        p = doc.add_paragraph()
        run = p.add_run(q)
        run.bold = True
        run.font.size = Pt(10)
        p = doc.add_paragraph()
        run = p.add_run(a)
        run.font.size = Pt(10)
        doc.add_paragraph()  # spacer

    # Footer
    doc.add_paragraph()
    divider = doc.add_paragraph()
    divider.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = divider.add_run("_" * 70)
    run.font.color.rgb = RGBColor(0x1B, 0x5E, 0x20)

    footer_text = doc.add_paragraph()
    footer_text.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer_text.add_run(
        "Prepared by OFA Research & Policy Division | "
        f"{datetime.now().strftime('%B %d, %Y')} | DRAFT — FOR INTERNAL USE"
    )
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
    run.italic = True

    return doc


def main():
    doc = build_document()

    output_dir = (
        r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture"
        r"\Desktop\Ben Desktop Files\Farm Business Confidence Survey"
        r"\2025\Specififc Issue spekaing notes"
    )

    filename = "Iran War Farm Input Cost Impact - Memo and Speaking Notes.docx"
    output_path = os.path.join(output_dir, filename)

    doc.save(output_path)
    print(f"Document saved to: {output_path}")


if __name__ == "__main__":
    main()
