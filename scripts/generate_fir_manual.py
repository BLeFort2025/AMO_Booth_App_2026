"""Generate FIR Developer Manual as Word document."""
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
import os

doc = Document()

# ── Style tweaks ──
style = doc.styles['Normal']
style.font.name = 'Calibri'
style.font.size = Pt(11)

# Title
title = doc.add_heading('FIR Municipal Finance Data\nDeveloper Manual', level=0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER

doc.add_paragraph(
    'Rural Community Data & Scenario Planner — Farm Finance Stats Dashboard\n'
    'Data Engineering Documentation\n'
    'Last Updated: February 20, 2026',
    style='Subtitle'
).alignment = WD_ALIGN_PARAGRAPH.CENTER

# ═══════════════════════════════════════════════════════════════════════
# SECTION 1: OVERVIEW
# ═══════════════════════════════════════════════════════════════════════
doc.add_heading('1. Overview', level=1)
doc.add_paragraph(
    'This manual documents the Financial Information Return (FIR) data extraction '
    'pipeline used in the Rural Community Data page of the Farm Finance Stats Dashboard. '
    'The FIR is an annual financial disclosure filed by all Ontario municipalities with '
    'the Ministry of Municipal Affairs and Housing (MMAH). Our pipeline extracts 15 years '
    'of data (2010–2024) from individual municipality ZIP files, each containing Excel '
    'workbooks with standardized schedule sheets.'
)

doc.add_heading('1.1 Data Source', level=2)
doc.add_paragraph(
    'Source: Ontario Ministry of Municipal Affairs and Housing (MMAH)\n'
    'URL: https://efis.fma.csc.gov.on.ca/fir/\n'
    'Format: ZIP files containing XLSX workbooks (one per municipality per year)\n'
    'Coverage: 444 municipalities × 15 years = 6,571 files\n'
    'Local path: data/FIR/ (organized by year subdirectories)'
)

doc.add_heading('1.2 Pipeline Architecture', level=2)
doc.add_paragraph(
    'The ETL pipeline consists of three layers:'
)
t = doc.add_table(rows=4, cols=3)
t.style = 'Light Grid Accent 1'
t.alignment = WD_TABLE_ALIGNMENT.CENTER
for i, (layer, file, desc) in enumerate([
    ('Layer', 'File', 'Description'),
    ('Configuration', 'config/fir_indicators.yaml', 'Declarative extraction rules — edit here to add/remove indicators without code changes'),
    ('ETL Engine', 'scripts/process_fir.py', 'Reads YAML config, opens each ZIP, extracts values from schedule sheets, computes derived indicators, writes CSV'),
    ('Output', 'data/derived/fir_indicators.csv', 'Wide-format CSV: one row per municipality-year, columns for all raw + computed indicators'),
]):
    for j, val in enumerate((layer, file, desc)):
        cell = t.rows[i].cells[j]
        cell.text = val
        if i == 0:
            cell.paragraphs[0].runs[0].bold = True

doc.add_heading('1.3 SGC Crosswalk', level=2)
doc.add_paragraph(
    'FIR data uses MMAH municipality IDs; Census data uses Statistics Canada SGC codes. '
    'The crosswalk file (config/fir_sgc_crosswalk.csv) maps between them, enabling linkage '
    'on the dashboard. The crosswalk was built by scripts/build_fir_sgc_crosswalk.py using '
    'fuzzy name matching with manual overrides for ambiguous cases.'
)

# ═══════════════════════════════════════════════════════════════════════
# SECTION 2: EXTRACTION SCHEDULES
# ═══════════════════════════════════════════════════════════════════════
doc.add_heading('2. FIR Schedule Extraction Configuration', level=1)
doc.add_paragraph(
    'All extraction rules are defined in config/fir_indicators.yaml. The pipeline supports '
    'two matching modes (line-code matching and RTC string matching) and two column addressing '
    'modes (FIR column headers and direct Excel column positions).'
)

# ── Schedule 26A ──
doc.add_heading('2.1 Schedule 26A: Taxation & Assessment', level=2)
doc.add_paragraph(
    'The cornerstone schedule for property tax analysis. Provides Current Value Assessment (CVA), '
    'tax levies, and their breakdown by Lower-Tier (LT), Upper-Tier (UT), and Education components '
    'for each Realty Tax Class (RTC).'
)
doc.add_paragraph('Match type: Line code matching')
doc.add_paragraph('Column addressing: FIR column headers (auto-detected)')

t = doc.add_table(rows=1, cols=5)
t.style = 'Light Grid Accent 1'
for j, h in enumerate(['Indicator', 'Line', 'Col', 'RTC', 'Description']):
    t.rows[0].cells[j].text = h
    t.rows[0].cells[j].paragraphs[0].runs[0].bold = True

s26a_indicators = [
    ('residential_cva', '0010', '16', 'RT', 'Residential Taxable CVA'),
    ('residential_total_taxes', '0010', '3', 'RT', 'Residential Total Taxes (LT+UT+Edu)'),
    ('residential_lt_taxes', '0010', '4', 'RT', 'Residential Lower-Tier Muni Taxes'),
    ('residential_ut_taxes', '0010', '5', 'RT', 'Residential Upper-Tier Muni Taxes'),
    ('residential_edu_taxes', '0010', '6', 'RT', 'Residential Education Taxes'),
    ('multi_residential_cva', '0050', '16', 'MT', 'Multi-Residential Taxable CVA'),
    ('multi_residential_taxes', '0050', '3', 'MT', 'Multi-Residential Total Taxes'),
    ('multi_residential_lt_taxes', '0050', '4', 'MT', 'Multi-Residential Lower-Tier Muni Taxes'),
    ('multi_residential_ut_taxes', '0050', '5', 'MT', 'Multi-Residential Upper-Tier Muni Taxes'),
    ('farmland_cva', '0110', '16', 'FT', 'Farmland Taxable CVA'),
    ('farmland_total_taxes', '0110', '3', 'FT', 'Farmland Total Taxes (LT+UT+Edu)'),
    ('farmland_lt_taxes', '0110', '4', 'FT', 'Farmland Lower-Tier Muni Taxes'),
    ('farmland_ut_taxes', '0110', '5', 'FT', 'Farmland Upper-Tier Muni Taxes'),
    ('farmland_edu_taxes', '0110', '6', 'FT', 'Farmland Education Taxes'),
    ('commercial_cva', '9120', '16', 'CT (subtotal)', 'Commercial Taxable CVA — subtotal of all CT, CU, CX subclasses'),
    ('commercial_total_taxes', '9120', '3', 'CT (subtotal)', 'Commercial Total Taxes (subtotal)'),
    ('commercial_lt_taxes', '9120', '4', 'CT (subtotal)', 'Commercial Lower-Tier Muni Taxes (subtotal)'),
    ('commercial_ut_taxes', '9120', '5', 'CT (subtotal)', 'Commercial Upper-Tier Muni Taxes (subtotal)'),
    ('industrial_cva', '9130', '16', 'IT (subtotal)', 'Industrial Taxable CVA — subtotal of all IT, IU, IX subclasses'),
    ('industrial_total_taxes', '9130', '3', 'IT (subtotal)', 'Industrial Total Taxes (subtotal)'),
    ('industrial_lt_taxes', '9130', '4', 'IT (subtotal)', 'Industrial Lower-Tier Muni Taxes (subtotal)'),
    ('industrial_ut_taxes', '9130', '5', 'IT (subtotal)', 'Industrial Upper-Tier Muni Taxes (subtotal)'),
    ('pipeline_cva', '0810', '16', 'PT', 'Pipeline Taxable CVA'),
    ('pipeline_total_taxes', '0810', '3', 'PT', 'Pipeline Total Taxes'),
    ('pipeline_lt_taxes', '0810', '4', 'PT', 'Pipeline Lower-Tier Muni Taxes'),
    ('pipeline_ut_taxes', '0810', '5', 'PT', 'Pipeline Upper-Tier Muni Taxes'),
    ('total_taxable_cva', '9199', '16', 'All', 'Total Taxable Assessment (CVA) — excludes PILs'),
    ('total_taxes', '9199', '3', 'All', 'Total Taxes Levied (all classes)'),
    ('total_lt_taxes', '9199', '4', 'All', 'Total Lower-Tier Muni Taxes'),
    ('total_ut_taxes', '9199', '5', 'All', 'Total Upper-Tier Muni Taxes'),
]
for row_data in s26a_indicators:
    row = t.add_row()
    for j, val in enumerate(row_data):
        row.cells[j].text = val

doc.add_paragraph()
p = doc.add_paragraph()
p.add_run('Important Design Decisions (Expert-Validated):').bold = True
doc.add_paragraph(
    'Commercial uses subtotal line 9120 (not base line 0210) to capture all subclasses '
    '(CT, CU/Excess Land, CX/Vacant Land, Office Buildings, Shopping Centres).', style='List Bullet'
)
doc.add_paragraph(
    'Industrial uses subtotal line 9130 (not base line 0510) for the same reason.', style='List Bullet'
)
doc.add_paragraph(
    'Line 9199 is "Total Taxable Assessment Before Adjustments" — strictly excludes '
    'Payment-in-Lieu (PIL) rows (1xxx series). This is the correct denominator for '
    'ratepayer share calculations.', style='List Bullet'
)
doc.add_paragraph(
    'Pipeline (L0810) is the hidden driver of rural Ontario municipal finance. '
    'Townships crossed by Enbridge/TC Energy pipelines can have 4–8% of their total tax base from pipelines.', style='List Bullet'
)

# ── Schedule 22A ──
doc.add_heading('2.2 Schedule 22A: Tax Rates & Ratios', level=2)
doc.add_paragraph(
    'Provides legislated tax ratios and tax rates by Realty Tax Class. Uses RTC string matching '
    '(exact match on the Realty Tax Class column) instead of line codes.'
)
doc.add_paragraph('Match type: RTC string matching (exact match)')
doc.add_paragraph('Column addressing: FIR column headers')

t = doc.add_table(rows=1, cols=4)
t.style = 'Light Grid Accent 1'
for j, h in enumerate(['Indicator', 'RTC', 'Col', 'Description']):
    t.rows[0].cells[j].text = h
    t.rows[0].cells[j].paragraphs[0].runs[0].bold = True

s22a_indicators = [
    ('residential_tax_ratio', 'RT', '5', 'Residential Tax Ratio (always 1.0)'),
    ('residential_lt_rate', 'RT', '8', 'Residential Lower-Tier Tax Rate'),
    ('residential_ut_rate', 'RT', '9', 'Residential Upper-Tier Tax Rate'),
    ('farmland_tax_ratio', 'FT', '5', 'Farmland Tax Ratio (max 0.25 by law)'),
    ('farmland_lt_rate', 'FT', '8', 'Farmland Lower-Tier Tax Rate'),
    ('farmland_ut_rate', 'FT', '9', 'Farmland Upper-Tier Tax Rate'),
    ('commercial_tax_ratio', 'CT', '5', 'Commercial Tax Ratio'),
    ('commercial_lt_rate', 'CT', '8', 'Commercial Lower-Tier Tax Rate'),
    ('industrial_tax_ratio', 'IT', '5', 'Industrial Tax Ratio'),
    ('industrial_lt_rate', 'IT', '8', 'Industrial Lower-Tier Tax Rate'),
    ('multi_res_tax_ratio', 'MT', '5', 'Multi-Residential Tax Ratio'),
]
for row_data in s22a_indicators:
    row = t.add_row()
    for j, val in enumerate(row_data):
        row.cells[j].text = val

doc.add_paragraph()
p = doc.add_paragraph()
p.add_run('Design Notes:').bold = True
doc.add_paragraph(
    'Single-tier municipalities put their unified rate in Col 08 (LT) and leave Col 09 (UT) blank/zero. '
    'The LT + UT formulas safely handle this.', style='List Bullet'
)
doc.add_paragraph(
    'Subclass rates (CU, CX) may differ from the base CT rate due to provincial discounts, '
    'but the base rate represents the core municipal policy lever.', style='List Bullet'
)

# ── Schedule 10 ──
doc.add_heading('2.3 Schedule 10: Revenue', level=2)
doc.add_paragraph('Municipal revenue breakdown. Single value column; uses FIR Col 1.')

t = doc.add_table(rows=1, cols=4)
t.style = 'Light Grid Accent 1'
for j, h in enumerate(['Indicator', 'Line', 'Col', 'Description']):
    t.rows[0].cells[j].text = h
    t.rows[0].cells[j].paragraphs[0].runs[0].bold = True

s10_indicators = [
    ('own_purpose_tax_rev', '0299', '1', 'Taxation — Own Purposes'),
    ('pil_rev', '0499', '1', 'Payments-In-Lieu of Taxation'),
    ('ompf_grant', '0620', '1', 'Ontario Municipal Partnership Fund (OMPF)'),
    ('ont_grants_unconditional', '0699', '1', 'Ontario Grants (Unconditional)'),
    ('ont_grants_conditional', '0899', '1', 'Ontario Grants (Conditional)'),
    ('total_revenue', '9910', '1', 'Total Revenue'),
]
for row_data in s10_indicators:
    row = t.add_row()
    for j, val in enumerate(row_data):
        row.cells[j].text = val

# ── Schedule 40 ──
doc.add_heading('2.4 Schedule 40: Expenses', level=2)
doc.add_paragraph(
    'Municipal expense breakdown by functional category. Col 11 = Total Expenses; '
    'Col 02 = Long-Term Debt Interest.'
)

t = doc.add_table(rows=1, cols=4)
t.style = 'Light Grid Accent 1'
for j, h in enumerate(['Indicator', 'Line', 'Col', 'Description']):
    t.rows[0].cells[j].text = h
    t.rows[0].cells[j].paragraphs[0].runs[0].bold = True

s40_indicators = [
    ('general_govt', '0299', '11', 'General Government'),
    ('protection', '0499', '11', 'Protection Services'),
    ('transportation', '0699', '11', 'Transportation Services'),
    ('environmental', '0899', '11', 'Environmental Services'),
    ('health', '1099', '11', 'Health Services'),
    ('social_family', '1299', '11', 'Social & Family Services'),
    ('recreation_culture', '1499', '11', 'Recreation & Cultural'),
    ('planning_development', '1699', '11', 'Planning & Development'),
    ('total_expenses', '9910', '11', 'Total Expenses'),
    ('debt_interest', '9910', '2', 'Total Long-Term Debt Interest'),
]
for row_data in s40_indicators:
    row = t.add_row()
    for j, val in enumerate(row_data):
        row.cells[j].text = val

# ── Schedule 70 ──
doc.add_heading('2.5 Schedule 70: Balance Sheet', level=2)
doc.add_paragraph('Municipal balance sheet. Single value column; FIR Col 1.')

t = doc.add_table(rows=1, cols=4)
t.style = 'Light Grid Accent 1'
for j, h in enumerate(['Indicator', 'Line', 'Col', 'Description']):
    t.rows[0].cells[j].text = h
    t.rows[0].cells[j].paragraphs[0].runs[0].bold = True

s70_indicators = [
    ('cash', '0299', '1', 'Cash and Cash Equivalents'),
    ('taxes_receivable', '0699', '1', 'Taxes Receivable'),
    ('total_financial_assets', '9930', '1', 'Total Financial Assets'),
    ('total_liabilities', '9940', '1', 'Total Liabilities'),
    ('net_financial_assets', '9945', '1', 'Net Financial Assets / (Debt)'),
    ('accumulated_surplus', '9971', '1', 'Accumulated Surplus / (Deficit) — modern PSAB'),
    ('_accumulated_surplus_9950', '9950', '1', 'Fallback for pre-2022 (historic line)'),
]
for row_data in s70_indicators:
    row = t.add_row()
    for j, val in enumerate(row_data):
        row.cells[j].text = val

doc.add_paragraph()
p = doc.add_paragraph()
p.add_run('PSAB Fallback Logic:').bold = True
doc.add_paragraph(
    'Line 9971 is the modern PSAB PS1201 "Accumulated Surplus" line (post-2022). '
    'Line 9950 is the legacy total. The pipeline uses a coalesce: if 9971 is null, '
    'it falls back to 9950. This provides 100% coverage across all 15 years.', style='List Bullet'
)

# ── Schedule 80D ──
doc.add_heading('2.6 Schedule 80D: Infrastructure & Planning Stats', level=2)
doc.add_paragraph(
    'Physical infrastructure statistics. Multi-section sheet with varying headers — uses '
    'direct Excel column positions (1-based) instead of FIR column headers.'
)
doc.add_paragraph('Column addressing: Direct Excel column positions (col_type: excel)')

t = doc.add_table(rows=1, cols=4)
t.style = 'Light Grid Accent 1'
for j, h in enumerate(['Indicator', 'Line', 'Excel Col', 'Description']):
    t.rows[0].cells[j].text = h
    t.rows[0].cells[j].paragraphs[0].runs[0].bold = True

s80d_indicators = [
    ('ag_land_hectares', '1370', '9', 'Hectares designated for agriculture'),
    ('paved_road_km', '1710', '9', 'Total Paved Lane KM'),
    ('unpaved_road_km', '1730', '9', 'Total Unpaved Lane KM'),
    ('winter_road_km', '1740', '9', 'Winter-Maintained Lane KM'),
    ('wastewater_km', '1815', '9', 'Total KM of Wastewater Mains'),
    ('wastewater_ml_treated', '1820', '9', 'Megalitres of Wastewater Treated'),
    ('water_ml_treated', '1845', '9', 'Megalitres of Drinking Water Treated'),
    ('water_km', '1855', '9', 'KM of Water Distribution Pipe'),
    ('solid_waste_tonnes', '1860', '9', 'Total Tonnes Collected (all classes)'),
    ('waste_diverted_tonnes', '1870', '9', 'Total Tonnes Diverted'),
]
for row_data in s80d_indicators:
    row = t.add_row()
    for j, val in enumerate(row_data):
        row.cells[j].text = val

doc.add_paragraph()
p = doc.add_paragraph()
p.add_run('Coverage Note:').bold = True
doc.add_paragraph(
    'ag_land_hectares has ~74% null rate. This is expected — many municipalities do not '
    'report this optional field. Use farmland_cva and farmland_tax_per_100k_cva as primary '
    'analytical drivers instead.', style='List Bullet'
)

# ── Schedule 80A ──
doc.add_heading('2.7 Schedule 80A: Building Permits', level=2)
doc.add_paragraph(
    'Building permit statistics. Schedule 80 is split into 80A/80B/80C/80D. Permits are on 80A. '
    'Uses direct Excel column positions (same layout as 80D).'
)
doc.add_paragraph('Column addressing: Direct Excel column positions (col_type: excel)')

t = doc.add_table(rows=1, cols=4)
t.style = 'Light Grid Accent 1'
for j, h in enumerate(['Indicator', 'Line', 'Excel Col', 'Description']):
    t.rows[0].cells[j].text = h
    t.rows[0].cells[j].paragraphs[0].runs[0].bold = True

s80a_indicators = [
    ('res_building_permits_count', '1210', '9', 'Residential Building Permits (#)'),
    ('res_building_permits_value', '1210', '10', 'Residential Building Permits ($)'),
    ('total_building_permits_count', '1299', '9', 'Total All Building Permits (#)'),
    ('total_building_permits_value', '1299', '10', 'Total All Building Permits ($)'),
]
for row_data in s80a_indicators:
    row = t.add_row()
    for j, val in enumerate(row_data):
        row.cells[j].text = val

doc.add_paragraph()
p = doc.add_paragraph()
p.add_run('Coverage Notes:').bold = True
doc.add_paragraph(
    'Residential permits: 58.1% count coverage, 47.1% value coverage.', style='List Bullet'
)
doc.add_paragraph(
    'Total permits: 66.2% count coverage, 54.0% value coverage — captures ag sheds, barns, '
    'and commercial builds in addition to residential.', style='List Bullet'
)
doc.add_paragraph(
    'Null rates are expected: in two-tier systems the county often issues permits, so '
    'lower-tier clerks leave this blank. S80A is also unaudited and frequently skipped.', style='List Bullet'
)

# ═══════════════════════════════════════════════════════════════════════
# SECTION 3: COMPUTED INDICATORS
# ═══════════════════════════════════════════════════════════════════════
doc.add_heading('3. Computed Indicators', level=1)
doc.add_paragraph(
    'These indicators are calculated from the raw extracted values by the _compute_derived() '
    'function in scripts/process_fir.py. All formulas are also documented in config/fir_indicators.yaml '
    'under the "computed:" section.'
)

doc.add_heading('3.1 Municipal Tax Totals', level=2)
doc.add_paragraph(
    'Municipal taxes exclude Education taxes (set uniformly by the Province) to isolate '
    'local policy decisions. Formula: LT + UT for each tax class.'
)

t = doc.add_table(rows=1, cols=3)
t.style = 'Light Grid Accent 1'
for j, h in enumerate(['Indicator', 'Formula', 'Description']):
    t.rows[0].cells[j].text = h
    t.rows[0].cells[j].paragraphs[0].runs[0].bold = True

muni_tax_indicators = [
    ('farmland_muni_taxes', 'farmland_lt_taxes + farmland_ut_taxes', 'Farmland Total Municipal Taxes (LT+UT)'),
    ('residential_muni_taxes', 'residential_lt_taxes + residential_ut_taxes', 'Residential Total Municipal Taxes (LT+UT)'),
    ('commercial_muni_taxes', 'commercial_lt_taxes + commercial_ut_taxes', 'Commercial Total Municipal Taxes (LT+UT)'),
    ('industrial_muni_taxes', 'industrial_lt_taxes + industrial_ut_taxes', 'Industrial Total Municipal Taxes (LT+UT)'),
    ('multi_residential_muni_taxes', 'multi_residential_lt_taxes + multi_residential_ut_taxes', 'Multi-Residential Total Municipal Taxes (LT+UT)'),
    ('pipeline_muni_taxes', 'pipeline_lt_taxes + pipeline_ut_taxes', 'Pipeline Total Municipal Taxes (LT+UT)'),
    ('total_muni_taxes', 'total_lt_taxes + total_ut_taxes', 'Total Municipal Taxes (LT+UT, all classes)'),
]
for row_data in muni_tax_indicators:
    row = t.add_row()
    for j, val in enumerate(row_data):
        row.cells[j].text = val

doc.add_heading('3.2 Tax Class Shares of Municipal Taxes', level=2)
doc.add_paragraph(
    'Each class\'s share of total municipal-only taxes (LT+UT). Education taxes are excluded because '
    'they are set provincially and do not reflect local policy. The denominator is total_muni_taxes '
    '(line 9199 LT+UT), which strictly excludes PILs.'
)

t = doc.add_table(rows=1, cols=3)
t.style = 'Light Grid Accent 1'
for j, h in enumerate(['Indicator', 'Formula', 'Description']):
    t.rows[0].cells[j].text = h
    t.rows[0].cells[j].paragraphs[0].runs[0].bold = True

share_indicators = [
    ('farmland_share_of_taxes', 'farmland_muni_taxes / total_muni_taxes', 'Farmland % of Municipal Taxes'),
    ('residential_share_of_taxes', 'residential_muni_taxes / total_muni_taxes', 'Residential % of Municipal Taxes'),
    ('commercial_share_of_taxes', 'commercial_muni_taxes / total_muni_taxes', 'Commercial % of Municipal Taxes'),
    ('industrial_share_of_taxes', 'industrial_muni_taxes / total_muni_taxes', 'Industrial % of Municipal Taxes'),
    ('multi_residential_share_of_taxes', 'multi_residential_muni_taxes / total_muni_taxes', 'Multi-Residential % of Municipal Taxes'),
    ('pipeline_share_of_taxes', 'pipeline_muni_taxes / total_muni_taxes', 'Pipeline % of Municipal Taxes'),
]
for row_data in share_indicators:
    row = t.add_row()
    for j, val in enumerate(row_data):
        row.cells[j].text = val

doc.add_paragraph()
p = doc.add_paragraph()
p.add_run('Six-Class Coverage:').bold = True
doc.add_paragraph(
    'Mean 6-class share sum: 93.6% (median: 97.1%). The remaining ~6% is from '
    'Managed Forest (TT), Landfills (HF), and other minor RTC classes. Consistent across '
    'all 15 years (92.4% to 94.3%).', style='List Bullet'
)

doc.add_heading('3.3 Infrastructure Aggregates', level=2)
t = doc.add_table(rows=1, cols=3)
t.style = 'Light Grid Accent 1'
for j, h in enumerate(['Indicator', 'Formula', 'Description']):
    t.rows[0].cells[j].text = h
    t.rows[0].cells[j].paragraphs[0].runs[0].bold = True

infra_indicators = [
    ('total_road_km', 'paved_road_km + unpaved_road_km', 'Total Road KM (paved + unpaved)'),
    ('waste_diversion_rate', 'waste_diverted_tonnes / (solid_waste_tonnes + waste_diverted_tonnes)', 'Waste Diversion Rate (%)'),
]
for row_data in infra_indicators:
    row = t.add_row()
    for j, val in enumerate(row_data):
        row.cells[j].text = val

doc.add_heading('3.4 Financial Health Indicators', level=2)
t = doc.add_table(rows=1, cols=3)
t.style = 'Light Grid Accent 1'
for j, h in enumerate(['Indicator', 'Formula', 'Description']):
    t.rows[0].cells[j].text = h
    t.rows[0].cells[j].paragraphs[0].runs[0].bold = True

fin_indicators = [
    ('ompf_dependency', 'ompf_grant / total_revenue', 'OMPF Grant Dependency Ratio'),
    ('tax_arrears_ratio', 'taxes_receivable / total_taxes', 'Tax Arrears Ratio (receivable / levied)'),
    ('operating_surplus', 'total_revenue - total_expenses', 'Accounting Surplus / (Deficit) — accrual basis, not cash budget'),
    ('ompf_relief_factor', 'ompf_grant / total_lt_taxes', 'OMPF Relief Factor (grant / local tax base)'),
]
for row_data in fin_indicators:
    row = t.add_row()
    for j, val in enumerate(row_data):
        row.cells[j].text = val

doc.add_paragraph()
p = doc.add_paragraph()
p.add_run('Important:').bold = True
doc.add_paragraph(
    'operating_surplus is an ACCOUNTING surplus (accrual-based per PSAB standards), '
    'not a cash budget surplus. Municipalities may report an "accounting surplus" while '
    'still running a tight cash-basis budget.', style='List Bullet'
)

doc.add_heading('3.5 Farmland-Specific Indicators', level=2)
t = doc.add_table(rows=1, cols=3)
t.style = 'Light Grid Accent 1'
for j, h in enumerate(['Indicator', 'Formula', 'Description']):
    t.rows[0].cells[j].text = h
    t.rows[0].cells[j].paragraphs[0].runs[0].bold = True

farm_indicators = [
    ('farmland_tax_per_hectare', 'farmland_total_taxes / ag_land_hectares', 'Farmland Tax Per Hectare ($)'),
    ('farmland_share_of_cva', 'farmland_cva / total_taxable_cva', 'Farmland Share of Total Assessment (%)'),
    ('farmland_tax_per_100k_cva', '(farmland_muni_taxes / farmland_cva) × 100,000', 'Farmland Municipal Tax Per $100k CVA ($) — expert-recommended'),
    ('farmland_burden_gap', '(farmland_cva / total_taxable_cva) - (farmland_muni_taxes / total_muni_taxes)', 'Assessment-vs-Burden Gap (% shielded by ratio). Positive = farmland pays less tax share than CVA share.'),
]
for row_data in farm_indicators:
    row = t.add_row()
    for j, val in enumerate(row_data):
        row.cells[j].text = val

# ═══════════════════════════════════════════════════════════════════════
# SECTION 4: DATA QUALITY
# ═══════════════════════════════════════════════════════════════════════
doc.add_heading('4. Data Quality & Known Limitations', level=1)

doc.add_heading('4.1 Record Counts', level=2)
doc.add_paragraph(
    'Total records: 6,556 (from 6,571 files — 15 legacy .xls files fail due to unreadable format). '
    'This represents ~99.8% extraction success rate.'
)

doc.add_heading('4.2 Known Failures', level=2)
doc.add_paragraph(
    '15 legacy .xls files fail consistently due to format issues with python-calamine. '
    'These are historical files from Champlain Tp, Espanola T, Brockton M, Hearst T, and others. '
    'This is a graceful failure — the pipeline logs warnings and continues.'
)

doc.add_heading('4.3 CVA Assessment Freeze (2021–2024)', level=2)
doc.add_paragraph(
    'CRITICAL: The Province of Ontario froze all Current Value Assessments (CVA) in 2020 due to '
    'COVID-19, and they remain frozen through 2024. Users looking at 2021–2024 data must understand '
    'that flat CVA values are a legislative artifact, not a stagnant real estate market. '
    'A footnote explaining this is displayed on the dashboard.'
)

doc.add_heading('4.4 Column-Level Null Rates', level=2)
doc.add_paragraph('Indicators with significant null rates (>30%):')
t = doc.add_table(rows=1, cols=3)
t.style = 'Light Grid Accent 1'
for j, h in enumerate(['Indicator', 'Null %', 'Explanation']):
    t.rows[0].cells[j].text = h
    t.rows[0].cells[j].paragraphs[0].runs[0].bold = True

null_indicators = [
    ('ag_land_hectares', '74.1%', 'Optional field; many municipalities do not report'),
    ('waste_diversion_rate', '72.3%', 'Depends on solid waste reporting'),
    ('wastewater/water indicators', '64–69%', 'Only municipalities operating own utilities report'),
    ('res_building_permits_value', '52.9%', 'Upper-tier may issue permits; unaudited schedule'),
    ('unpaved/paved roads', '49–51%', 'Mainly urban single-tiers leave blank'),
    ('total_building_permits_count', '33.8%', 'Better coverage than residential-only'),
    ('farmland_ut_rate', '35.3%', 'Single-tier municipalities have no UT rate'),
]
for row_data in null_indicators:
    row = t.add_row()
    for j, val in enumerate(row_data):
        row.cells[j].text = val

# ═══════════════════════════════════════════════════════════════════════
# SECTION 5: EXPERT VALIDATION HISTORY
# ═══════════════════════════════════════════════════════════════════════
doc.add_heading('5. Expert Validation History', level=1)
doc.add_paragraph(
    'The extraction configuration underwent three rounds of validation with a FIR domain expert '
    '(February 2026). Key corrections made:'
)

doc.add_heading('5.1 Round 1: Initial Setup', level=2)
doc.add_paragraph('Established baseline extraction from all 7 schedules (26A, 22A, 10, 40, 70, 80D, 80A).', style='List Bullet')
doc.add_paragraph('Identified line code corrections (Multi-Res was on wrong line).', style='List Bullet')
doc.add_paragraph('Added OMPF Relief Factor, Farmland Tax Per $100k CVA, and Assessment-vs-Burden Gap as expert-recommended indicators.', style='List Bullet')

doc.add_heading('5.2 Round 2: CT/IT Subtotals & UT Taxes', level=2)
doc.add_paragraph('Moved Commercial from line 0210 (base CT only) to line 9120 (subtotal all CT subclasses).', style='List Bullet')
doc.add_paragraph('Moved Industrial from line 0510 (base IT only) to line 9130 (subtotal all IT subclasses).', style='List Bullet')
doc.add_paragraph('Added Upper-Tier (UT) tax extraction for CT and IT classes.', style='List Bullet')
doc.add_paragraph('Corrected share formulas to use municipal taxes (LT+UT) as denominator, excluding Education.', style='List Bullet')
doc.add_paragraph('Moved Building Permits from S80D to S80A with correct Excel column positions.', style='List Bullet')

doc.add_heading('5.3 Round 3: Pipeline & Multi-Res Completion', level=2)
doc.add_paragraph('Added Pipeline extraction (L0810) to capture the "hidden driver" of rural municipal finance.', style='List Bullet')
doc.add_paragraph('Added Multi-Residential LT/UT taxes for share calculation.', style='List Bullet')
doc.add_paragraph('Added Total Building Permits (L1299) to capture agricultural and commercial permits.', style='List Bullet')
doc.add_paragraph('Closed 6-class share gap from ~91% to 93.6% mean / 97.1% median.', style='List Bullet')
doc.add_paragraph('Expert verdict: FULLY APPROVED FOR PRODUCTION.', style='List Bullet')

# ═══════════════════════════════════════════════════════════════════════
# SECTION 6: MAINTENANCE GUIDE
# ═══════════════════════════════════════════════════════════════════════
doc.add_heading('6. Maintenance Guide', level=1)

doc.add_heading('6.1 Adding a New Year of Data', level=2)
doc.add_paragraph('1. Download the FIR ZIP files for the new year from the MMAH website.')
doc.add_paragraph('2. Place them in data/FIR/{year}/ directory.')
doc.add_paragraph('3. Update YEARS constant in scripts/process_fir.py to include the new year.')
doc.add_paragraph('4. Run: python scripts/process_fir.py')
doc.add_paragraph('5. Verify output with: python scripts/verify_r3.py')

doc.add_heading('6.2 Adding a New Indicator', level=2)
doc.add_paragraph('1. Add the indicator to config/fir_indicators.yaml under the appropriate schedule.')
doc.add_paragraph('2. If it requires computation, add both a raw extraction entry and a computed entry.')
doc.add_paragraph('3. Add computation logic to _compute_derived() in scripts/process_fir.py.')
doc.add_paragraph('4. Add the indicator to FIR_INDICATOR_COLS and INDICATOR_META in the dashboard page.')
doc.add_paragraph('5. Re-run python scripts/process_fir.py.')

doc.add_heading('6.3 Key Files Reference', level=2)
t = doc.add_table(rows=1, cols=2)
t.style = 'Light Grid Accent 1'
t.rows[0].cells[0].text = 'File'
t.rows[0].cells[1].text = 'Purpose'
t.rows[0].cells[0].paragraphs[0].runs[0].bold = True
t.rows[0].cells[1].paragraphs[0].runs[0].bold = True

files = [
    ('config/fir_indicators.yaml', 'Declarative extraction configuration — the single source of truth for all indicators'),
    ('config/fir_sgc_crosswalk.csv', 'Maps MMAH municipality IDs to Statistics Canada SGC codes for Census linkage'),
    ('scripts/process_fir.py', 'ETL engine: reads ZIP files, extracts values, computes derived indicators, writes CSV'),
    ('scripts/build_fir_sgc_crosswalk.py', 'One-time script to build the SGC crosswalk from fuzzy name matching'),
    ('data/derived/fir_indicators.csv', 'Output: wide-format CSV read by the Streamlit dashboard'),
    ('app/pages/9_🏘️_Rural_Community_Data.py', 'Dashboard page: FIR_INDICATOR_COLS and INDICATOR_META lists'),
]
for file, purpose in files:
    row = t.add_row()
    row.cells[0].text = file
    row.cells[1].text = purpose

# ── Save ──
out_dir = r"C:\Projects\Farm Finance Stats Dashboard\Reports and supplemental information\Municipal Rural Data and Municipal Scenario Planner"
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "FIR Data Developer Manual.docx")
doc.save(out_path)
print(f"Saved: {out_path}")
