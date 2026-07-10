"""Script to completely reconstruct the end of the report generator."""

import re

with open('scripts/write_report.py', 'r', encoding='utf-8') as f:
    text = f.read()

# I will systematically cut off the file right before the 
# # =========================================================================
# # FISCAL IMPACT ON MUNICIPALITIES
# section, or if it's missing, right before the property tax sections or the References section.

# The safest point is after the Economic Impact comparison section.
# Let's search for "COMBINED ECONOMIC COMPARISON"
base_match = re.search(r'(.*?# =========================================================================\s*# COMBINED ECONOMIC COMPARISON.*?new_doc\.add_paragraph\(\s*\'Together, Perth and Wellington.*?11\.0% of Ontario\\\'s entire.*?\)[\r\n]+)', text, re.DOTALL)

if not base_match:
    print("Could not find base match.")
    raise SystemExit()
    
base_text = base_match.group(1)

# Now I'll append the final code exactly as it should be.
end_code = """
# =========================================================================
# FISCAL IMPACT ON MUNICIPALITIES
# =========================================================================
new_doc.add_page_break()
new_doc.add_heading('The Fiscal Impact of Agriculture on Ontario Municipalities', level=2)

new_doc.add_paragraph(
    'While the economic footprint of agriculture is widely recognized, its specific impact on municipal '
    'budgets is equally profound. A recent econometric study by the Ontario Federation of Agriculture (OFA) '
    'established that farmland acts as a significant net fiscal positive for rural municipalities. By analyzing '
    'upper-tier municipal financial data across Ontario, the research confirmed that farmland properties contribute '
    'substantially more in property tax revenue than they demand in municipal services. The data reveals a stark '
    'reality: for every 1% of a county\\'s land mass that is removed from agricultural production, its municipal '
    'operating surplus demonstrably decreases by over $240,000 annually.'
)

new_doc.add_paragraph(
    'This positive fiscal balance is driven by the unique nature of agricultural land use. Farmland provides '
    'a stable, highly assessed property tax base while requiring minimal support from expensive municipal services '
    'such as social housing, protection services, or extensive recreational facilities. The OFA study found the '
    'only significant municipal expenditure directly correlated with an agricultural land base is the maintenance '
    'of rural transportation infrastructure. Furthermore, a thriving agricultural sector indirectly benefits '
    'municipalities by attracting lucrative commercial and industrial assessments — such as equipment dealerships, '
    'feed mills, and processing plants — which further fortify municipal revenues without heavy service burdens.'
)

new_doc.add_paragraph(
    'The realization that farmland "more than pays its own way" is critical context for understanding the current '
    'state of local municipal finances. Over the last decade, soaring farmland values have dramatically shifted '
    'the property tax landscape. As we examine the specific municipal finances of Perth and Wellington counties '
    'in the following sections, it becomes evident that the agricultural sector has absorbed a rapidly increasing '
    'share of the total local tax burden to fund these municipalities [16].'
)

new_doc.add_heading('Property Tax Shift to Farm Properties in Perth County (2010–2024)', level=2)
new_doc.add_paragraph(
    'Between 2010 and the most recent FIR reporting cycle, Perth County experienced a massive surge in agricultural '
    'property values. The total assessed value (CVA) of farmland skyrocketed from $2.44 billion in 2010 to '
    '$7.57 billion — a 209.6% increase. Because property taxes are inherently tied to assessment values, this created '
    'a substantial shift in the municipal tax burden toward the agricultural sector.'
)
new_doc.add_paragraph(
    'In 2010, the agricultural sector contributed $1.69 million in municipal property taxes, accounting for 17.5% '
    'of the county\\'s total upper-tier tax levy. Driven by soaring assessments rather than an increase in service '
    'demands, the total municipal tax paid by farm properties has since soared by 224.8% to over $5.50 million. '
    'Today, despite requiring minimal municipal services, the agricultural sector shoulders 27.1% of Perth '
    'County\\'s entire upper-tier municipal tax burden [17].'
)

new_doc.add_heading('Property Tax Shift to Farm Properties in Wellington County (2010–2024)', level=2)
new_doc.add_paragraph(
    'Wellington County has seen a similarly staggering appreciation in agricultural land values. The total assessed '
    'value (CVA) of farmland across the county grew from $1.88 billion in 2010 to $5.16 billion — a 173.8% '
    'increase over the cycle. As land values spiked out of sync with other property classes, farmers absorbed a '
    'disproportionate share of the local tax burden.'
)
new_doc.add_paragraph(
    'In 2010, farm properties contributed $2.99 million in municipal property taxes, representing 4.1% of '
    'Wellington County\\'s upper-tier tax levy. By the latest reporting cycle, the total municipal tax paid by the '
    'agricultural sector surged by 197.8%, reaching $8.89 million. As a result of this disproportionate assessment '
    'growth, the agricultural sector\\'s share of the total upper-tier tax burden expanded significantly to 6.5% [17].'
)

# =========================================================================
# REFERENCES
# =========================================================================
new_doc.add_page_break()
new_doc.add_heading('References', level=2)

references = [
    '1. Statistics Canada. 2022. Census of Agriculture, 2021. Statistics Canada Catalogue no. 95-640-X. Ottawa: Statistics Canada. Table 32-10-0236-01 to 32-10-0249-01. Available at: https://www.statcan.gc.ca/en/subjects-start/agriculture_and_food',
    '2. Statistics Canada. 2017. Census of Agriculture, 2016. Statistics Canada Catalogue no. 95-640-X. Ottawa: Statistics Canada.',
    '3. Statistics Canada. 2012. Census of Agriculture, 2011. Statistics Canada Catalogue no. 95-640-X. Ottawa: Statistics Canada.',
    '4. Statistics Canada. 2007. Census of Agriculture, 2006. Statistics Canada Catalogue no. 95-629-X. Ottawa: Statistics Canada.',
    '5. Ontario Ministry of Agriculture, Food and Agribusiness (OMAFA). 2025. "Ontario Farm Cash Receipts by County and Commodity, 2011–2024." Ontario Data Catalogue. Toronto: King\\'s Printer for Ontario. Available at: https://data.ontario.ca/dataset/farm-cash-receipts-by-county',
    '6. Statistics Canada. Table 32-10-0236-01: Value of farm capital, Census of Agriculture, 2021. DOI: https://doi.org/10.25318/3210023601-eng',
    '7. Statistics Canada. Table 32-10-0240-01: Total gross farm receipts, Census of Agriculture, 2021.',
    '8. Statistics Canada. Table 32-10-0241-01: Total farm business operating expenses, Census of Agriculture, 2021.',
    '9. Statistics Canada. Table 32-10-0243-01: Number of farm operators by paid work characteristics, Census of Agriculture, 2021.',
    '10. Statistics Canada. Table 32-10-0249-01: Crops, Census of Agriculture, 2021.',
    '11. Ontario Pork. 2024. "County-Level Hog Marketing Statistics." Guelph: Ontario Pork. Available at: https://www.ontariopork.on.ca',
    '12. Dairy Farmers of Ontario / Lactanet. 2024. Provincial dairy herd statistics by county. Available at: https://www.lactanet.ca',
    '13. Ontario Ministry of Agriculture, Food and Agribusiness (OMAFA). 2025. Ontario Agri-Food Value Chain by County: Gross Domestic Product and Employment, 2012-2024. Ontario Data Catalogue. Available at: https://data.ontario.ca/dataset/ontario-agri-food-value-chain-by-county',
    '14. Statistics Canada. 2022. Census of Population, 2021. Catalogue no. 98-316-X. Census Profile: Perth, County (Census Division), Ontario. Labour force by industry (NAICS 2017). Available at: https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/index.cfm',
    '15. Statistics Canada. 2022. Census of Population, 2021. Catalogue no. 98-316-X. Census Profile: Wellington, County (Census Division), Ontario.',
    '16. Ontario Federation of Agriculture (OFA). 2024. "The Fiscal Impact of Farmland on Ontario Municipalities." Guelph: OFA. Available at: https://ofa.on.ca/resources/the-fiscal-impact-of-farmland-on-ontario-municipalities/',
    '17. Ontario Ministry of Municipal Affairs and Housing (MMAH). 2024. "Financial Information Return (FIR) Database." Toronto: King\\'s Printer for Ontario. Available at: https://efis.fma.csc.gov.on.ca/fir/',
]

for ref in references:
    p = new_doc.add_paragraph(ref)
    for run in p.runs:
        run.font.size = Pt(9)

new_doc.add_paragraph()  # spacer

# Notes section
new_doc.add_heading('Notes on Data Sources', level=3)
notes = [
    'Census of Agriculture data (farm counts, acreage, livestock inventories, operator demographics, '
    'business structure, technology adoption, and employment) is sourced from Statistics Canada\\'s Census '
    'of Agriculture, conducted every five years in conjunction with the national Census of Population. '
    'The most recent Census of Agriculture was conducted in 2021. Statistics Canada introduced a revised '
    'definition of "census farm" in 2021, requiring that farms report revenues or expenses to the Canada '
    'Revenue Agency. Caution should be exercised when comparing 2021 data directly with previous Census years.',
    
    'Farm Cash Receipts (FCR) data is sourced from the Ontario Ministry of Agriculture, Food and Agribusiness '
    '(formerly OMAFRA). FCR measures the total revenue received by farmers from the sale of agricultural '
    'products, including crops, livestock, dairy, poultry, and other commodities. The county-level FCR estimates '
    'are derived by applying county commodity share factors to provincial totals, based on Census of Agriculture '
    'production data and industry allocation models. FCR figures presented in this report are nominal '
    '(not adjusted for inflation).',
    
    'Provincial livestock rankings (e.g., "second-largest hog-producing county") are based on the authors\\' '
    'analysis of the 2021 Census of Agriculture data across all Ontario census divisions. Rankings may '
    'differ from those reported by commodity organizations (e.g., Ontario Pork) that use annual marketing '
    'data rather than Census inventory snapshots.',
    
    'All dollar figures are in Canadian dollars. Census financial data (farm capital, gross receipts, operating '
    'expenses) refers to the calendar year or fiscal year preceding the Census reference date. Farm cash '
    'receipts for 2024 are preliminary estimates and may be subject to revision.',
    
    'Agri-Food Value Chain data (GDP and Employment) is sourced from OMAFA. It measures the combined '
    'economic impact of primary agriculture, food and beverage manufacturing, and food retail. GDP figures '
    'are expressed in millions of chained 2017 dollars, adjusting for inflation to reflect real economic '
    'growth.',
]

for note in notes:
    p = new_doc.add_paragraph(note)
    for run in p.runs:
        run.font.size = Pt(9)
    p.paragraph_format.space_after = Pt(6)

# Save
output_path = os.path.join(os.path.dirname(REPORT_PATH), 'Report_v8.docx')
new_doc.save(output_path)
print(f"\\nReport saved to: {output_path}")
print("DONE")
"""

with open('scripts/write_report.py', 'w', encoding='utf-8') as f:
    f.write(base_text + end_code)

print("Report layout completely rebuilt safely.")
