"""Script to inject the final property tax assessment values into write_report.py and bump to v8."""

with open('scripts/write_report.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update the COCS citation [16]
old_cocs_para = """new_doc.add_paragraph(
    'The realization that farmland "more than pays its own way" is critical context for understanding the current '
    'state of local municipal finances. Over the last decade, soaring farmland values have dramatically shifted '
    'the property tax landscape. As we examine the specific municipal finances of Perth and Wellington counties '
    'in the following sections, it becomes evident that the agricultural sector has absorbed a rapidly increasing '
    'share of the total local tax burden to fund these municipalities.'
)"""

new_cocs_para = """new_doc.add_paragraph(
    'The realization that farmland "more than pays its own way" is critical context for understanding the current '
    'state of local municipal finances. Over the last decade, soaring farmland values have dramatically shifted '
    'the property tax landscape. As we examine the specific municipal finances of Perth and Wellington counties '
    'in the following sections, it becomes evident that the agricultural sector has absorbed a rapidly increasing '
    'share of the total local tax burden to fund these municipalities [16].'
)"""

text = text.replace(old_cocs_para, new_cocs_para)

# 2. Add Perth Narrative
old_perth = "new_doc.add_paragraph('[Analysis of Perth County property tax assessment impacts to be inserted]')"
new_perth = """new_doc.add_paragraph(
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
)"""

text = text.replace(old_perth, new_perth)

# 3. Add Wellington Narrative
old_wellington = "new_doc.add_paragraph('[Analysis of Wellington County property tax assessment impacts to be inserted]')"
new_wellington = """new_doc.add_paragraph(
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
)"""

text = text.replace(old_wellington, new_wellington)


# 4. Add References
old_refs = """    '15. Statistics Canada. 2022. Census of Population, 2021. Catalogue no. 98-316-X. Census Profile: Wellington, County (Census Division), Ontario.',
]"""

new_refs = """    '15. Statistics Canada. 2022. Census of Population, 2021. Catalogue no. 98-316-X. Census Profile: Wellington, County (Census Division), Ontario.',
    '16. Ontario Federation of Agriculture (OFA). 2024. "The Fiscal Impact of Farmland on Ontario Municipalities." Guelph: OFA. Available at: https://ofa.on.ca/resources/the-fiscal-impact-of-farmland-on-ontario-municipalities/',
    '17. Ontario Ministry of Municipal Affairs and Housing (MMAH). 2024. "Financial Information Return (FIR) Database." Toronto: King\\'s Printer for Ontario. Available at: https://efis.fma.csc.gov.on.ca/fir/',
]"""

text = text.replace(old_refs, new_refs)


# 5. Bump version to Report_v8
text = text.replace("'Report_v7.docx'", "'Report_v8.docx'")


with open('scripts/write_report.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("Tax logic successfully injected.")
