"""Write the agricultural profile sections into the Report.docx template."""
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml
import os

REPORT_PATH = r'C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Ben Desktop Files\Economic Analyst Position\Economic Impact Studies\County Level\Perth and Wellington\Report.docx'

# Don't read the template (may be locked by Word) - we build from scratch
# doc = Document(REPORT_PATH)

# =========================================================================
# Helper functions
# =========================================================================
def set_cell_shading(cell, color):
    """Set background shading on a table cell."""
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color}"/>')
    cell._tc.get_or_add_tcPr().append(shading)

def add_styled_table(doc, headers, rows, col_widths=None):
    """Add a professionally formatted table."""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = 'Table Grid'
    
    # Header row
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = header
        for paragraph in cell.paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in paragraph.runs:
                run.bold = True
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(255, 255, 255)
        set_cell_shading(cell, "2E7D32")  # Dark green header
    
    # Data rows
    for row_idx, row_data in enumerate(rows):
        for col_idx, value in enumerate(row_data):
            cell = table.rows[row_idx + 1].cells[col_idx]
            cell.text = str(value)
            for paragraph in cell.paragraphs:
                if col_idx == 0:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                else:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in paragraph.runs:
                    run.font.size = Pt(9)
            # Alternate row shading
            if row_idx % 2 == 0:
                set_cell_shading(cell, "E8F5E9")  # Light green
    
    return table

def add_heading3(doc, text):
    p = doc.add_heading(text, level=3)
    return p

# =========================================================================
# Build the document from scratch
# =========================================================================
new_doc = Document()

# Copy styles from original (we'll use the template's formatting)
# For simplicity, recreate with clean formatting

# ---- TITLE ----
title = new_doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run('The Economic and Fiscal Impacts of Farming in Perth & Wellington')
run.bold = True
run.font.size = Pt(22)
run.font.color.rgb = RGBColor(0x2E, 0x7D, 0x32)

new_doc.add_paragraph()  # spacer

# =========================================================================
# PERTH COUNTY PROFILE
# =========================================================================
h2 = new_doc.add_heading('Agricultural Profile of Perth County', level=2)

# Introduction
new_doc.add_paragraph(
    'Perth County, located in the heart of southwestern Ontario, is one of the province\'s most '
    'productive agricultural regions. With a history rooted in mixed farming that dates back to the '
    'mid-1800s, Perth County has evolved into a modern agricultural powerhouse that punches well above '
    'its weight on the provincial stage. In 2024, Perth County\'s farms generated an estimated $1.51 billion '
    'in farm cash receipts — accounting for 6.7% of all farm revenue produced in Ontario, making it one '
    'of the top five agricultural counties in the province.'
)

# Overview
new_doc.add_heading('Size and Scale', level=3)
new_doc.add_paragraph(
    'According to the 2021 Census of Agriculture, Perth County is home to 2,420 farms spread across '
    '533,244 acres of farmland — an area roughly the size of 400,000 football fields. Of that total, '
    '468,573 acres (88%) is actively used for crop production, reflecting the county\'s intensive '
    'agricultural character. The remaining acreage includes pastureland, woodlots, and farmsteads.'
)
new_doc.add_paragraph(
    'These 2,420 farms are operated by 3,430 farm operators — individuals who are directly involved in '
    'making management decisions for their farm businesses. Together, these operations hold $12.7 billion '
    'in total farm capital, including land, buildings, machinery, and livestock.'
)

# Historical trend table - Perth
new_doc.add_heading('How Perth County Farming Has Changed Over Time', level=3)
new_doc.add_paragraph(
    'The following table tracks key indicators from the Census of Agriculture, conducted every five years '
    'by Statistics Canada. These figures reveal how the structure and scale of Perth County\'s agricultural '
    'sector has evolved over a 15-year period.'
)

add_styled_table(new_doc,
    ['Indicator', '2006', '2011', '2016', '2021', 'Change 2006–2021'],
    [
        ['Number of farms', '2,438', '2,252', '2,231', '2,420', '-0.7%'],
        ['Total farm area (acres)', '498,161', '506,291', '518,023', '533,244', '+7.0%'],
        ['Cropland (acres)', '427,832', '442,972', '453,605', '468,573', '+9.5%'],
        ['Total farm operators', '3,600', '3,365', '3,235', '3,430', '-4.7%'],
        ['Average operator age', '49.4', '51.0', '53.0', '54.1', '+4.7 years'],
        ['Total farm capital', '$3.76B', '$5.34B', '$9.24B', '$12.71B', '+238%'],
        ['Gross farm receipts', '$703M', '$748M', '$966M', '$1.29B', '+84%'],
    ]
)

new_doc.add_paragraph(
    'Several trends stand out. While the total number of farms has remained relatively stable — declining '
    'slightly from 2,438 in 2006 to 2,420 in 2021 — the total area being farmed has actually increased by '
    '7%. This reflects a broader trend in Canadian agriculture: farms are getting larger as smaller operations '
    'consolidate. The most dramatic change has been in farm capital values, which have more than tripled from '
    '$3.76 billion to $12.71 billion, driven primarily by soaring farmland values. Gross farm receipts have '
    'also grown significantly, rising 84% over the period — well above the rate of inflation.'
)

# Commodity mix
new_doc.add_heading('What Perth County Farms Produce', level=3)
new_doc.add_paragraph(
    'Perth County\'s agricultural economy is anchored by two dominant sectors: dairy farming and hog '
    'production. Together, dairy products and hogs account for over 44% of all farm cash receipts in the '
    'county. This makes Perth County one of Ontario\'s most important centres for both milk production and '
    'pork production.'
)

add_styled_table(new_doc,
    ['Commodity', '2024 Farm Cash Receipts', 'Share of County Total'],
    [
        ['Dairy Products', '$339.5M', '22.4%'],
        ['Hogs', '$329.0M', '21.8%'],
        ['Steers & Slaughter Heifers', '$148.3M', '9.8%'],
        ['Corn', '$132.4M', '8.8%'],
        ['Chickens', '$124.4M', '8.2%'],
        ['Soybeans', '$95.0M', '6.3%'],
        ['Wheat', '$49.1M', '3.2%'],
        ['Eggs', '$45.0M', '3.0%'],
        ['Dry Beans', '$24.7M', '1.6%'],
        ['All Other', '$225.0M', '14.9%'],
        ['Total', '$1,512.3M', '100.0%'],
    ]
)

new_doc.add_paragraph(
    'Perth County\'s hog sector is particularly notable. With 661,067 pigs recorded in the 2021 Census, '
    'Perth is the second-largest hog-producing county in Ontario, behind only Huron County. The county\'s '
    '230 hog operations range from smaller farrow-to-finish farms to large-scale commercial operations that '
    'supply major packing plants. The dairy sector is equally substantial, with 37,621 dairy cows across '
    '321 dairy farms — the second-highest dairy cow count in any Ontario county, behind only Oxford County.'
)
new_doc.add_paragraph(
    'Field crops play a vital supporting role. Corn is planted on 158,149 acres — more than any other crop '
    '— much of which is used as feed grain for the county\'s large livestock population. Soybeans (122,612 '
    'acres) and wheat (89,749 acres) round out a classic southwestern Ontario crop rotation. Perth County '
    'is also a significant producer of dry beans, a specialty crop grown on over 25,000 acres.'
)

# Livestock
new_doc.add_heading('Livestock Inventory', level=3)
new_doc.add_paragraph(
    'Perth County\'s livestock sector is large and diverse. The table below tracks how animal populations '
    'have changed over four Census periods.'
)

add_styled_table(new_doc,
    ['Livestock Type', '2006', '2011', '2016', '2021'],
    [
        ['Total cattle & calves', '115,250', '110,896', '104,289', '123,605'],
        ['Dairy cows', '30,904', '33,464', '33,789', '37,621'],
        ['Beef cows', '8,402', '5,731', '5,087', '6,250'],
        ['Pigs', '664,508', '455,726', '569,442', '661,067'],
        ['Hens & chickens', '3,732,504', '3,715,097', '4,622,352', '5,043,758'],
        ['Sheep & lambs', '7,745', '14,973', '11,012', '11,010'],
        ['Turkeys', '79,297', '32,591', '261,706', '209,820'],
    ]
)

new_doc.add_paragraph(
    'The dairy herd has grown steadily, reflecting strong demand for Ontario-produced milk and the '
    'modernization of dairy operations. The hog sector experienced a significant dip following the 2008-2009 '
    'financial crisis and low commodity prices but has recovered to near 2006 levels. Poultry numbers have '
    'grown by 35% over the period, indicating expansion in the supply-managed chicken and egg sectors.'
)

# Demographics
new_doc.add_heading('The People Behind the Farms', level=3)
new_doc.add_paragraph(
    'Like much of rural Ontario, Perth County\'s farming community is aging. The average farm operator was '
    '54.1 years old in 2021, up from 49.4 in 2006. Only 10.2% of operators are under 35 years old (350 '
    'individuals), down from 12.6% in 2006. Meanwhile, the share of operators aged 55 and over has risen '
    'from 32.8% to 54.2% — meaning more than half of all farm operators in Perth County are now 55 or older.'
)
new_doc.add_paragraph(
    'Roughly one-third of farm operators (31.6%) are women, a share that has remained relatively stable '
    'over the past 15 years. About 49% of all farm operators report earning some income from off-farm '
    'employment, reflecting the economic reality that many farm families supplement their agricultural income '
    'with non-farm work.'
)

# Farm business structure
new_doc.add_heading('How Farms Are Organized', level=3)
new_doc.add_paragraph(
    'Perth County\'s farms are increasingly structured as formal business entities rather than traditional '
    'sole proprietorships. While sole proprietorships still represent the largest single category (887 farms '
    'in 2021), family corporations have been growing steadily — from 492 in 2006 to 680 in 2021, a 38% '
    'increase. This shift toward incorporation reflects the growing capital requirements and business '
    'complexity of modern farming, as well as tax planning and succession considerations.'
)

add_styled_table(new_doc,
    ['Business Structure', '2006', '2021', 'Change'],
    [
        ['Sole proprietorship', '1,085', '887', '-18%'],
        ['Partnership', '844', '797', '-6%'],
        ['Family corporation', '492', '680', '+38%'],
        ['Non-family corporation', '—', '56', '—'],
    ]
)

# Revenue distribution
new_doc.add_heading('Farm Revenue Distribution', level=3)
new_doc.add_paragraph(
    'Perth County\'s farms span a wide range of sizes, from small hobby operations to multi-million dollar '
    'enterprises. In 2021, 135 farms (5.6%) reported gross receipts of $2 million or more, while 189 farms '
    '(7.8%) were in the $1 million to $2 million range. At the other end of the spectrum, 396 farms (16.4%) '
    'reported receipts under $25,000. This distribution reflects the co-existence of commercial-scale '
    'operations — particularly in dairy, hogs, and grain — alongside smaller lifestyle and part-time '
    'farming operations.'
)

add_styled_table(new_doc,
    ['Revenue Class', 'Number of Farms', 'Share'],
    [
        ['$2,000,000 and over', '135', '5.6%'],
        ['$1,000,000 to $1,999,999', '189', '7.8%'],
        ['$500,000 to $999,999', '290', '12.0%'],
        ['$250,000 to $499,999', '301', '12.4%'],
        ['$100,000 to $249,999', '405', '16.7%'],
        ['$50,000 to $99,999', '395', '16.3%'],
        ['$25,000 to $49,999', '309', '12.8%'],
        ['Under $25,000', '396', '16.4%'],
    ]
)

# Employment
new_doc.add_heading('Farm Employment', level=3)
new_doc.add_paragraph(
    'Beyond the 3,430 farm operators themselves, Perth County\'s farms directly employed 2,234 paid workers '
    'in 2021. Of these, 1,164 were full-time year-round employees (working 30 or more hours per week), '
    '819 were part-time year-round, and 251 were seasonal or temporary workers. These employment figures '
    'represent only direct on-farm labour and do not include the thousands of additional jobs in agricultural '
    'supply, processing, and service industries that depend on the county\'s farm sector — impacts that are '
    'explored in detail in the economic impact section of this report.'
)

# Growth
new_doc.add_heading('Farm Cash Receipts Growth, 2011–2024', level=3)
new_doc.add_paragraph(
    'Farm cash receipts — the total revenue received by farmers from the sale of agricultural products — '
    'have grown substantially in Perth County over the past decade. From $740 million in 2011 to $1.51 '
    'billion in 2024, total receipts have more than doubled, representing a compound annual growth rate '
    'of 5.6%. While some of this growth reflects commodity price inflation, it also reflects real expansion '
    'in production volume, particularly in dairy and poultry.'
)

new_doc.add_paragraph()  # spacer

# =========================================================================
# WELLINGTON COUNTY PROFILE
# =========================================================================
h2 = new_doc.add_heading('Agricultural Profile of Wellington County', level=2)

new_doc.add_paragraph(
    'Wellington County, stretching from the city of Guelph northward through some of Ontario\'s most '
    'fertile farmland, is a cornerstone of the province\'s agricultural economy. Known for its rolling '
    'landscapes, prosperous farming communities, and a uniquely diverse mix of farm types — from Old Order '
    'Mennonite operations to state-of-the-art robotic dairy barns — Wellington County generated an estimated '
    '$1.36 billion in farm cash receipts in 2024, representing 6.0% of Ontario\'s total agricultural output.'
)

new_doc.add_heading('Size and Scale', level=3)
new_doc.add_paragraph(
    'The 2021 Census of Agriculture counted 2,617 farms operating across 523,903 acres in Wellington County. '
    'Roughly 436,390 acres (83%) is actively cropped, with the remainder including pastureland, woodlots, '
    'sugar bushes, and farmsteads. The county\'s 3,800 farm operators collectively manage $10.6 billion in '
    'total farm capital.'
)
new_doc.add_paragraph(
    'Compared to Perth County, Wellington has slightly more farms (2,617 vs. 2,420) but slightly less total '
    'farmland (523,903 vs. 533,244 acres). Wellington also has a somewhat lower proportion of cropland (83% '
    'vs. 88%), reflecting the county\'s hillier terrain in the northern townships and a greater emphasis on '
    'pasture-based livestock production.'
)

# Historical trends
new_doc.add_heading('How Wellington County Farming Has Changed Over Time', level=3)
new_doc.add_paragraph(
    'The table below tracks how the fundamental structure of Wellington County farming has evolved across '
    'the four most recent Census of Agriculture cycles.'
)

add_styled_table(new_doc,
    ['Indicator', '2006', '2011', '2016', '2021', 'Change 2006–2021'],
    [
        ['Number of farms', '2,588', '2,511', '2,348', '2,617', '+1.1%'],
        ['Total farm area (acres)', '485,862', '499,176', '466,400', '523,903', '+7.8%'],
        ['Cropland (acres)', '386,414', '402,894', '380,733', '436,390', '+12.9%'],
        ['Total farm operators', '3,770', '3,655', '3,455', '3,800', '+0.8%'],
        ['Average operator age', '49.6', '51.0', '51.0', '52.7', '+3.1 years'],
        ['Total farm capital', '$3.28B', '$4.54B', '$6.51B', '$10.64B', '+224%'],
        ['Gross farm receipts', '$491M', '$654M', '$943M', '$1.17B', '+139%'],
    ]
)

new_doc.add_paragraph(
    'Wellington County is notable for its resilience. Unlike many parts of rural Ontario where farm numbers '
    'have declined steadily for decades, Wellington has actually seen its farm count increase slightly from '
    '2,588 in 2006 to 2,617 in 2021. This is due in part to the county\'s large Old Order Mennonite '
    'community in the northern townships, which tends to maintain smaller, family-scale operations that '
    'resist the consolidation trend. Total farm area has also grown by nearly 8%, and cropland has expanded '
    'by almost 13%. Farm capital has more than tripled, and gross farm receipts have surged 139% — the '
    'fastest receipts growth rate between the two counties.'
)

# Commodity mix
new_doc.add_heading('What Wellington County Farms Produce', level=3)
new_doc.add_paragraph(
    'Wellington County\'s agricultural economy is distinctly more diversified than Perth\'s. Rather than '
    'being dominated by one or two commodities, revenue is spread more evenly across beef cattle, dairy, '
    'poultry, hogs, and field crops. This diversification provides a degree of economic resilience — when '
    'prices fall in one sector, other sectors can help buffer the impact.'
)

add_styled_table(new_doc,
    ['Commodity', '2024 Farm Cash Receipts', 'Share of County Total'],
    [
        ['Steers & Slaughter Heifers', '$315.5M', '23.1%'],
        ['Dairy Products', '$274.5M', '20.1%'],
        ['Chickens', '$213.0M', '15.6%'],
        ['Hogs', '$112.4M', '8.2%'],
        ['Soybeans', '$76.8M', '5.6%'],
        ['Corn', '$58.4M', '4.3%'],
        ['Wheat', '$44.2M', '3.2%'],
        ['Eggs', '$40.3M', '3.0%'],
        ['Sheep & Lambs', '$9.5M', '0.7%'],
        ['All Other', '$219.8M', '16.1%'],
        ['Total', '$1,364.4M', '100.0%'],
    ]
)

new_doc.add_paragraph(
    'The beef sector leads Wellington County\'s commodity mix, with steers and slaughter heifers generating '
    '$315.5 million — nearly 23% of all farm revenue. Wellington is home to 150,093 cattle and calves '
    '(2021 Census) — the highest total cattle inventory of any county in Ontario — including both cow-calf '
    'operations in the hillier northern townships and finishing feedlots in the more level southern areas. '
    'The county is also Ontario\'s largest poultry producer: with nearly 7 million hens and chickens — more '
    'than any other county in the province — Wellington generates $213 million from broiler chickens and '
    '$40 million from eggs annually.'
)
new_doc.add_paragraph(
    'Field crops — corn (121,818 acres), soybeans (116,923 acres), wheat (86,371 acres), and alfalfa '
    '(67,775 acres) — provide both direct revenue and essential feed inputs for the county\'s large '
    'livestock sector. The higher alfalfa acreage compared to Perth (67,775 vs. 51,038 acres) reflects '
    'Wellington\'s greater emphasis on cattle and dairy operations that rely on hay and silage.'
)

# Livestock
new_doc.add_heading('Livestock Inventory', level=3)

add_styled_table(new_doc,
    ['Livestock Type', '2006', '2011', '2016', '2021'],
    [
        ['Total cattle & calves', '135,619', '142,197', '131,038', '150,093'],
        ['Dairy cows', '23,819', '25,779', '26,610', '30,716'],
        ['Beef cows', '13,782', '10,350', '7,900', '9,398'],
        ['Pigs', '298,627', '236,144', '232,527', '255,297'],
        ['Hens & chickens', '4,366,519', '5,706,394', '6,816,729', '6,953,181'],
        ['Sheep & lambs', '12,193', '27,548', '19,361', '28,879'],
        ['Turkeys', '207,467', '248,811', '175,336', '176,261'],
    ]
)

new_doc.add_paragraph(
    'Wellington County\'s cattle herd has grown by 10.7% since 2006 — a strong performance at a time when '
    'cattle numbers have been declining across much of Ontario. The dairy herd has seen particularly robust '
    'growth, rising 29% from 23,819 to 30,716 cows. The sheep and lamb sector has also seen notable growth, '
    'more than doubling from 12,193 to 28,879. Poultry numbers have increased by 59%, from 4.4 million to '
    'nearly 7 million birds, reflecting strong consumer demand for chicken products.'
)

# Demographics
new_doc.add_heading('The People Behind the Farms', level=3)
new_doc.add_paragraph(
    'Wellington County\'s farming population is younger than Perth\'s. The average farm operator in Wellington '
    'was 52.7 years old in 2021, compared to 54.1 in Perth. More significantly, 14.6% of Wellington\'s '
    'operators are under 35 (555 individuals), compared to just 10.2% in Perth. This younger demographic '
    'profile is partly attributable to the county\'s Mennonite farming communities, where multi-generational '
    'farming and earlier farm succession are common.'
)
new_doc.add_paragraph(
    'Women make up 32.9% of Wellington\'s farm operators (1,250 individuals), a slightly higher share than '
    'Perth\'s 31.6%. About half of all operators (50.1%) report earning some off-farm income.'
)

# Business structure
new_doc.add_heading('How Farms Are Organized', level=3)

add_styled_table(new_doc,
    ['Business Structure', '2006', '2021', 'Change'],
    [
        ['Sole proprietorship', '1,274', '1,014', '-20%'],
        ['Partnership', '945', '1,096', '+16%'],
        ['Family corporation', '337', '462', '+37%'],
        ['Non-family corporation', '—', '41', '—'],
    ]
)

new_doc.add_paragraph(
    'Wellington has seen a distinctive shift toward partnerships, which grew 16% from 945 to 1,096 — the '
    'single largest category of business arrangement in the county by 2021. This is unusual; in most Ontario '
    'counties, sole proprietorships remain the dominant form. The growth in partnerships may reflect the '
    'Mennonite community\'s tradition of family-based farming arrangements, as well as pragmatic succession '
    'strategies where parents and adult children farm together under a shared business entity.'
)

# Revenue distribution
new_doc.add_heading('Farm Revenue Distribution', level=3)

add_styled_table(new_doc,
    ['Revenue Class', 'Number of Farms', 'Share'],
    [
        ['$2,000,000 and over', '88', '3.4%'],
        ['$1,000,000 to $1,999,999', '177', '6.8%'],
        ['$500,000 to $999,999', '370', '14.1%'],
        ['$250,000 to $499,999', '351', '13.4%'],
        ['$100,000 to $249,999', '358', '13.7%'],
        ['$50,000 to $99,999', '290', '11.1%'],
        ['$25,000 to $49,999', '295', '11.3%'],
        ['Under $25,000', '688', '26.3%'],
    ]
)

new_doc.add_paragraph(
    'Wellington County has a larger tail of smaller farms than Perth: 26.3% of farms report receipts under '
    '$25,000, compared to 16.4% in Perth. Conversely, Perth has a higher concentration of very large farms '
    '(5.6% over $2 million vs. 3.4% in Wellington). This pattern is consistent with Wellington\'s more '
    'diversified farm structure, which includes many smaller Mennonite family operations alongside large '
    'commercial grain, dairy, and poultry enterprises.'
)

# Employment
new_doc.add_heading('Farm Employment', level=3)
new_doc.add_paragraph(
    'Wellington County\'s farms employed 1,567 paid workers in 2021, including 718 full-time year-round '
    'employees, 468 part-time year-round, and 381 seasonal or temporary workers. This is fewer paid workers '
    'than Perth (2,234), which likely reflects Wellington\'s higher proportion of family-operated farms where '
    'unpaid family labour substitutes for hired employees — a common arrangement in Mennonite farming '
    'communities. These figures also do not include the operators themselves, who number 3,800.'
)

# Technology
new_doc.add_heading('Technology Adoption', level=3)
new_doc.add_paragraph(
    'Both counties are active adopters of precision agriculture and farm technology. The 2021 Census '
    'captured adoption rates for several key technologies:'
)

add_styled_table(new_doc,
    ['Technology', 'Perth County', 'Wellington County'],
    [
        ['Automated steering (auto-steer)', '828 farms (34%)', '680 farms (26%)'],
        ['Soil sample testing', '1,129 farms (47%)', '1,001 farms (38%)'],
        ['GIS mapping', '570 farms (24%)', '421 farms (16%)'],
        ['Variable-rate input application', '504 farms (21%)', '432 farms (17%)'],
        ['Drones', '104 farms (4%)', '82 farms (3%)'],
        ['Robotic milking', '64 farms (3%)', '73 farms (3%)'],
        ['Renewable energy systems', '494 farms (20%)', '491 farms (19%)'],
    ]
)

new_doc.add_paragraph(
    'Perth County generally shows higher adoption rates for precision agriculture technologies like '
    'auto-steer, GIS mapping, and variable-rate application. This is consistent with Perth\'s larger '
    'average farm size and higher proportion of large-scale grain and oilseed operations, which tend '
    'to be early adopters of GPS-guided and data-driven farming tools. Wellington County, meanwhile, matches '
    'Perth on robotic milking — with 73 robotic dairy farms — reflecting the rapid modernization of its '
    'dairy sector.'
)

# Growth
new_doc.add_heading('Farm Cash Receipts Growth, 2011–2024', level=3)
new_doc.add_paragraph(
    'Wellington County\'s farm cash receipts have doubled over 13 years, rising from $681 million in 2011 '
    'to $1.36 billion in 2024 — a compound annual growth rate of 5.5%. This growth mirrors Perth\'s '
    'trajectory (5.6% CAGR) and reflects both commodity price appreciation and expanding production in '
    'the county\'s dairy, poultry, and beef sectors.'
)

# =========================================================================
# COMPARISON SUMMARY
# =========================================================================
new_doc.add_heading('Perth and Wellington: Side-by-Side Comparison', level=2)

new_doc.add_paragraph(
    'While Perth and Wellington counties share many similarities — neighbouring geographies, strong mixed '
    'farming traditions, and comparable total output — they have distinct agricultural personalities. The '
    'table below highlights the key similarities and differences.'
)

add_styled_table(new_doc,
    ['Metric', 'Perth County', 'Wellington County'],
    [
        ['Total farms (2021)', '2,420', '2,617'],
        ['Total farm area', '533,244 acres', '523,903 acres'],
        ['Cropland', '468,573 acres (88%)', '436,390 acres (83%)'],
        ['Total farm capital', '$12.71 billion', '$10.64 billion'],
        ['Farm Cash Receipts (2024)', '$1.51 billion', '$1.36 billion'],
        ['Provincial FCR share', '6.7%', '6.0%'],
        ['No. 1 commodity', 'Dairy ($340M)', 'Beef ($316M)'],
        ['No. 2 commodity', 'Hogs ($329M)', 'Dairy ($275M)'],
        ['Pig inventory', '661,067', '255,297'],
        ['Dairy cows', '37,621', '30,716'],
        ['Cattle & calves', '123,605', '150,093'],
        ['Hens & chickens', '5,043,758', '6,953,181'],
        ['Average operator age', '54.1 years', '52.7 years'],
        ['Operators under 35', '350 (10.2%)', '555 (14.6%)'],
        ['Paid employees', '2,234', '1,567'],
        ['Farms over $2M revenue', '135 (5.6%)', '88 (3.4%)'],
        ['FCR CAGR (2011–2024)', '5.6%', '5.5%'],
    ]
)

new_doc.add_paragraph(
    'In summary, Perth County is somewhat more concentrated and commercially intensive — home to Ontario\'s '
    'second-largest hog sector, second-largest dairy herd, and a higher share of very large farms. '
    'Wellington County is more diversified and has a younger farming population, the province\'s largest '
    'total cattle herd, and the largest county-level poultry flock. Together, they contributed a combined '
    '$2.88 billion in farm cash receipts in 2024 — approximately 12.7% of all farm revenue generated in '
    'Ontario — making this two-county region one of the most agriculturally significant in the country.'
)

# =========================================================================
# ECONOMIC IMPACT - PERTH COUNTY
# =========================================================================
new_doc.add_page_break()
new_doc.add_heading('Economic Impact of the Agri-Food Sector in Perth County', level=2)

new_doc.add_paragraph(
    'The agricultural profile in the previous section describes what happens on Perth County\'s farms — the '
    'crops, livestock, and people that make up the primary production sector. But the ultimate economic footprint of '
    'this agriculture extends far beyond the farm gate. When a dairy farmer ships milk to a processing plant, '
    'or when a grain elevator handles locally grown corn, each of these activities generates economic value '
    'and employment further down the supply chain.'
)

new_doc.add_heading('What is the Agri-Food Value Chain Attribution Model?', level=3)
new_doc.add_paragraph(
    'To capture this full picture, the Ontario Ministry of Agriculture, Food and Agribusiness (OMAFA) utilizes '
    'an economic attribution model to measure the impact of the entire agri-food value chain. This model tracks '
    'three interconnected stages:'
)
new_doc.add_paragraph(
    '1. Primary Agriculture (Farming): The raw commodities produced on local farms.\n'
    '2. Food, Beverage and Tobacco Manufacturing: The secondary processing of those raw agricultural products.\n'
    '3. Food Retail: The final sale of finished food products to consumers.'
)
new_doc.add_paragraph(
    'Crucially, the OMAFA attribution model measures the total economic activity and jobs supported throughout '
    'the entire province of Ontario that can be directly attributed back to the agricultural production in a '
    'specific county. For example, a pig raised on a farm in Perth County might support a truck driving job '
    'transporting it, a meat-packing job at a processing facility in another region, and a retail job at a grocery '
    'store in Toronto. The OMAFA data rolls all of these province-wide downstream impacts up and attributes '
    'them back to the county where the raw agricultural product originated [13].'
)

new_doc.add_heading('Perth County: Feeding the Province', level=3)
new_doc.add_paragraph(
    'In 2024, the primary agricultural output from Perth County farms ultimately generated $2.98 billion in '
    'agri-food GDP across Ontario. This makes Perth County the third-largest economic driver of Ontario\'s '
    'agri-food system among all counties and regions, trailing only Essex ($4.06 billion) and Huron ($3.58 '
    'billion). The farm production from this single county is responsible for supporting 5.8% of Ontario\'s '
    'entire $51.4 billion agri-food GDP [13].'
)

add_styled_table(new_doc,
    ['Year', 'Agri-Food GDP ($M)', 'Employment (Jobs)'],
    [
        ['2012', '$2,204.6', '39,957'],
        ['2014', '$2,439.8', '42,779'],
        ['2016', '$2,522.9', '43,742'],
        ['2017', '$2,666.0', '45,273'],
        ['2019', '$2,798.4', '47,070'],
        ['2020', '$2,593.1', '39,572'],
        ['2022', '$2,907.3', '45,490'],
        ['2023', '$2,970.2', '47,487'],
        ['2024', '$2,983.8', 'N/A'],
    ]
)

new_doc.add_paragraph(
    'Over the 12-year period from 2012 to 2024, the province-wide GDP attributed to Perth County\'s agri-food '
    'sector grew by 35.3%, representing a compound annual growth rate (CAGR) of 2.6%. All GDP figures are '
    'expressed in chained 2017 dollars, meaning they have been adjusted for inflation. This real, inflation-adjusted '
    'growth demonstrates that the county\'s agricultural base is genuinely expanding its productive capacity and '
    'creating more downstream value—not simply benefiting from rising market prices [13].'
)

new_doc.add_heading('Agri-Food Employment Footprint', level=3)
new_doc.add_paragraph(
    'In 2023, the agricultural output from Perth County supported approximately 47,487 jobs across the province. '
    'These 47,487 jobs represent 5.5% of Ontario\'s total agri-food workforce spanning farm operators, processing '
    'technicians, and supply chain logistics professionals [13].'
)
new_doc.add_paragraph(
    'It is important to understand that while these jobs are distributed throughout the provincial economy, Perth '
    'County itself serves as a highly integrated hub. The county captures a significant portion of this downstream '
    'economic activity locally, anchored by a robust local food manufacturing and processing base around '
    'communities like Stratford and Listowel. Facilities such as meat packers, dairy processors, and feed mills '
    'operate within the county specifically because of their proximity to Perth\'s world-class primary agricultural '
    'output.'
)

new_doc.add_heading('Provincial Agri-Food GDP Rankings', level=3)

add_styled_table(new_doc,
    ['Rank', 'County/Region', '2024 Agri-Food GDP'],
    [
        ['1', 'Essex County', '$4,058.9M'],
        ['2', 'Huron County', '$3,576.3M'],
        ['3', 'Perth County', '$2,983.8M'],
        ['4', 'Middlesex County', '$2,888.0M'],
        ['5', 'Wellington County', '$2,692.1M'],
        ['6', 'Oxford County', '$2,681.7M'],
        ['7', 'Chatham-Kent', '$2,585.6M'],
        ['8', 'Bruce County', '$1,814.7M'],
        ['9', 'Lambton County', '$1,682.8M'],
        ['10', 'Elgin County', '$1,424.0M'],
    ]
)

# =========================================================================
# ECONOMIC IMPACT - WELLINGTON COUNTY
# =========================================================================
new_doc.add_page_break()
new_doc.add_heading('Economic Impact of the Agri-Food Sector in Wellington County', level=2)

new_doc.add_paragraph(
    'Wellington County\'s farms are another indispensable engine of the provincial economy. Using the same OMAFA '
    'attribution model—which measures the localized and downstream province-wide impact generated by a single '
    'county\'s agricultural output—Wellington County\'s farm production was responsible for generating $2.69 '
    'billion in Ontario agri-food GDP in 2024. This makes Wellington the fifth-largest agri-food economic driver '
    'in the province, accounting for 5.2% of Ontario\'s entire agri-food GDP [13].'
)

new_doc.add_heading('Agri-Food GDP Growth and Resilience', level=3)

add_styled_table(new_doc,
    ['Year', 'Agri-Food GDP ($M)', 'Employment (Jobs)'],
    [
        ['2012', '$2,037.0', '36,920'],
        ['2014', '$2,401.0', '42,099'],
        ['2016', '$2,244.2', '38,910'],
        ['2017', '$2,339.0', '39,719'],
        ['2019', '$2,205.1', '37,090'],
        ['2020', '$2,225.0', '33,955'],
        ['2022', '$2,624.3', '41,062'],
        ['2023', '$2,681.1', '42,845'],
        ['2024', '$2,692.1', 'N/A'],
    ]
)

new_doc.add_paragraph(
    'Wellington County\'s attributed agri-food GDP has grown by 32.2% over the 2012 to 2024 period (a real '
    'inflation-adjusted CAGR of 2.4%). The growth trajectory has seen some year-to-year fluctuations reflecting '
    'the county\'s specific commodity mix. Notably, the downstream supply chains anchored by Wellington\'s '
    'agri-food sector proved exceptionally resilient during the 2020 pandemic downturn. While many other counties '
    'saw double-digit economic contractions, Wellington\'s agri-food footprint continued to grow by 0.9%. The '
    'sector has continued to expand strongly, posting back-to-back records in 2022, 2023, and 2024 [13].'
)

new_doc.add_heading('Agri-Food Employment Footprint', level=3)
new_doc.add_paragraph(
    'In 2023, the agricultural output from Wellington County farms supported 42,845 jobs throughout Ontario\'s '
    'value chain (farming, processing, and retail) — the fifth-highest employment impact generated by any '
    'county. These positions represent 4.9% of Ontario\'s total agri-food workforce [13].'
)
new_doc.add_paragraph(
    'Much like Perth County, Wellington County captures a massive share of this downstream economic activity '
    'within its own geographic borders. The region, particularly in Guelph and Centre Wellington, is home to a '
    'dense cluster of food manufacturing and agribusiness operations. This local processing ecosystem is uniquely '
    'fortified by the presence of the University of Guelph—Canada\'s premier agricultural university—which '
    'provides a continuous pipeline of world-class agricultural research, technological innovation, and highly '
    'skilled graduates.'
)
# =========================================================================
# COMBINED ECONOMIC COMPARISON
# =========================================================================
new_doc.add_heading('Perth and Wellington: Combined Agri-Food Economic Impact', level=3)

add_styled_table(new_doc,
    ['Metric', 'Perth County', 'Wellington County', 'Combined'],
    [
        ['Agri-Food GDP (2024)', '$2,983.8M', '$2,692.1M', '$5,675.9M'],
        ['Provincial GDP share', '5.8%', '5.2%', '11.0%'],
        ['Provincial GDP rank', '#3', '#5', '—'],
        ['Agri-Food employment (2023)', '47,487', '42,845', '90,332'],
        ['Provincial employment share', '5.5%', '4.9%', '10.4%'],
        ['GDP growth 2012\u20132024', '+35.3%', '+32.2%', '—'],
        ['GDP CAGR (real)', '2.6%', '2.4%', '—'],
    ]
)

new_doc.add_paragraph(
    'Together, Perth and Wellington counties generated $5.68 billion in agri-food GDP in 2024 — '
    'accounting for 11.0% of Ontario\'s entire agri-food economic output. The two counties combined '
    'supported over 90,000 agri-food jobs in 2023, representing more than one in ten of all agri-food '
    'workers in the province. These figures demonstrate that this two-county region is not merely an '
    'important farming area — it is one of the engines of Ontario\'s food system and a critical '
    'contributor to the provincial economy [13].'
)


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
    'reality: for every 1% of a county\'s land mass that is removed from agricultural production, its municipal '
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
    'of the county\'s total upper-tier tax levy. Driven by soaring assessments rather than an increase in service '
    'demands, the total municipal tax paid by farm properties has since soared by 224.8% to over $5.50 million. '
    'Today, despite requiring minimal municipal services, the agricultural sector shoulders 27.1% of Perth '
    'County\'s entire upper-tier municipal tax burden [17].'
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
    'Wellington County\'s upper-tier tax levy. By the latest reporting cycle, the total municipal tax paid by the '
    'agricultural sector surged by 197.8%, reaching $8.89 million. As a result of this disproportionate assessment '
    'growth, the agricultural sector\'s share of the total upper-tier tax burden expanded significantly to 6.5% [17].'
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
    '5. Ontario Ministry of Agriculture, Food and Agribusiness (OMAFA). 2025. "Ontario Farm Cash Receipts by County and Commodity, 2011–2024." Ontario Data Catalogue. Toronto: King\'s Printer for Ontario. Available at: https://data.ontario.ca/dataset/farm-cash-receipts-by-county',
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
    '17. Ontario Ministry of Municipal Affairs and Housing (MMAH). 2024. "Financial Information Return (FIR) Database." Toronto: King\'s Printer for Ontario. Available at: https://efis.fma.csc.gov.on.ca/fir/',
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
    'business structure, technology adoption, and employment) is sourced from Statistics Canada\'s Census '
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
    
    'Provincial livestock rankings (e.g., "second-largest hog-producing county") are based on the authors\' '
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
print(f"\nReport saved to: {output_path}")
print("DONE")
