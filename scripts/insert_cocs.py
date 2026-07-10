"""Script to insert the fiscal impact summary narrative before the document saves."""

with open('scripts/write_report.py', 'r', encoding='utf-8') as f:
    text = f.read()

# I will replace the # Save comment with the new narrative code, followed by the # Save comment again.
cocs_code = """
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
    'share of the total local tax burden to fund these municipalities.'
)

new_doc.add_heading('Property Tax Shift to Farm Properties in Perth County (2010–2024)', level=2)
new_doc.add_paragraph('[Analysis of Perth County property tax assessment impacts to be inserted]')

new_doc.add_heading('Property Tax Shift to Farm Properties in Wellington County (2010–2024)', level=2)
new_doc.add_paragraph('[Analysis of Wellington County property tax assessment impacts to be inserted]')

# Save"""

if "# Save" in text:
    text = text.replace("# Save", cocs_code)
    
# Bump the version
text = text.replace("'Report_v6.docx'", "'Report_v7.docx'")

with open('scripts/write_report.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("COCS summary successfully inserted.")
