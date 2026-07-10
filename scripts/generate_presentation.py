import os, sys
from pptx import Presentation
from pptx.util import Pt, Inches
from pptx.chart.data import CategoryChartData, ChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.chart import XL_LEGEND_POSITION

sys.path.append(os.path.dirname(__file__))
from write_report import REPORT_PATH

TEMPLATE_PATH = r'C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Ben Desktop Files\TEMPLATES\2025\OFA Presentation Template - March 2025 - Copy.pptx'
OUTPUT_DIR = os.path.dirname(REPORT_PATH)
OUTPUT_PATH = os.path.join(OUTPUT_DIR, 'Perth_Wellington_Economic_Report_2026_V2.pptx')

os.makedirs(OUTPUT_DIR, exist_ok=True)
prs = Presentation(TEMPLATE_PATH)

WHITE_LAYOUT = prs.slide_layouts[2] # Let's use Layout 2 (Fillable Content A) to avoid the "Future Focus" red banner
COVER_LAYOUT = prs.slide_layouts[0]
CONCLUSION_LAYOUT = prs.slide_layouts[5]

# Using explicit physical bounding boxes to completely prevent text overflow and chart overlap
# Assuming a standard 16:9 widescreen layout: 13.33 inches wide X 7.5 inches tall.
text_x = Inches(0.5)
text_y = Inches(1.5)
text_cx = Inches(5.5)
text_cy = Inches(5.5)

chart_x = Inches(6.5)
chart_y = Inches(1.5)
chart_cx = Inches(6.0)
chart_cy = Inches(5.5)

def prep_clean_slide(prs, layout_choice):
    slide = prs.slides.add_slide(layout_choice)
    # Remove any arbitrary body placeholders that the template contains so we don't accidentally write to them or overlap them
    for shape in list(slide.placeholders):
        if shape.placeholder_format.type != 1: # If it's not the TITLE
            sp = shape.element
            sp.getparent().remove(sp)
    return slide

def populate_slide_left_text(slide, title_text, body_text):
    if slide.shapes.title:
        slide.shapes.title.text = title_text
        
    # Draw our own custom strict-bounded text box for the left side
    txBox = slide.shapes.add_textbox(text_x, text_y, text_cx, text_cy)
    tf = txBox.text_frame
    tf.word_wrap = True
    
    bullets = [b.strip('- ').strip() for b in body_text.split('\n') if b.strip()]
    for i, bullet in enumerate(bullets):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = bullet
        p.font.size = Pt(21)
        p.level = 0
        p.space_after = Pt(14)

# Slide 1: Cover
slide = prs.slides.add_slide(COVER_LAYOUT)
for shape in slide.placeholders:
    if shape.placeholder_format.type == 1:
        shape.text = "The Economic & Fiscal Impact of Agriculture in Perth and Wellington Counties"
    elif shape.placeholder_format.type == 2:
        shape.text = "A Comparative Analysis | Spring 2026\nOntario Federation of Agriculture"

# Slide 2: Purpose
slide = prep_clean_slide(prs, WHITE_LAYOUT)
populate_slide_left_text(slide, "Purpose of the Report", 
"""- Analyze foundational agricultural metrics of two Ontario powerhouse counties.
- Quantify the downstream economic footprint (Agri-Food GDP and Jobs) tracking how they "Feed the Province".
- Establish the net-positive fiscal impact of farmland on municipal budgets.
- Measure the dramatic shift in municipal property tax burden borne by farmers from 2010 to 2024.""")

# Slide 3: Perth Primary (PIE CHART)
slide = prep_clean_slide(prs, WHITE_LAYOUT)
populate_slide_left_text(slide, "Perth County: Primary Production", 
"""- 2,420 farms operating across 533,244 total acres.
- Generated $1.51 Billion in Farm Cash Receipts in 2024.
- Total Farm Capital stands at $12.71 Billion.
- Ontario's 2nd largest hog herd (661k pigs) & 2nd largest dairy herd (37k cows).""")

chart_data = ChartData()
chart_data.categories = ['Dairy', 'Hogs', 'Beef', 'Corn', 'Chicken', 'Other']
chart_data.add_series('Farm Cash Receipts ($M)', (339, 329, 148, 132, 124, 441))
chart = slide.shapes.add_chart(XL_CHART_TYPE.PIE, chart_x, chart_y, chart_cx, chart_cy, chart_data).chart
chart.has_legend = True
chart.legend.position = XL_LEGEND_POSITION.BOTTOM

# Slide 4: Wellington Primary (PIE CHART)
slide = prep_clean_slide(prs, WHITE_LAYOUT)
populate_slide_left_text(slide, "Wellington County: Diversification & Scale", 
"""- 2,617 farms operating across 523,903 total acres.
- Generated $1.36 Billion in Farm Cash Receipts in 2024.
- Total Farm Capital stands at $10.64 Billion.
- Holds the largest total cattle inventory in Ontario (150,093 head) and the largest poultry flock (7 million birds).""")

chart_data = ChartData()
chart_data.categories = ['Beef', 'Dairy', 'Chicken', 'Hogs', 'Soybean', 'Other']
chart_data.add_series('Farm Cash Receipts ($M)', (315, 275, 213, 112, 77, 372))
chart = slide.shapes.add_chart(XL_CHART_TYPE.PIE, chart_x, chart_y, chart_cx, chart_cy, chart_data).chart
chart.has_legend = True
chart.legend.position = XL_LEGEND_POSITION.BOTTOM

# Slide 5: Demographics & Structure
slide = prep_clean_slide(prs, WHITE_LAYOUT)
populate_slide_left_text(slide, "Demographics & Farm Structure", 
"""- Perth County: Average age is 54.1 years. 54% of farmers are 55 or older.
- Wellington County: A younger demographic (52.7 years). 14.6% of operators are under 35, driven by multi-generational Mennonite traditions.
- Both counties are structurally shifting toward family corporations (Perth: +38%) and partnerships (Wellington: +16%) to adapt to heavy capital requirements.""")

# Slide 6: OMAFA Model
slide = prep_clean_slide(prs, WHITE_LAYOUT)
populate_slide_left_text(slide, "The Upstream & Downstream Impact", 
"""- The economic footprint extends far beyond the farm gate.
- The OMAFA Attribution Model measures all economic activity & jobs supported across Ontario directly attributed back to local farms.
- It covers three stages: Primary Agriculture, Manufacturing, and Retail.
- This proves how Perth and Wellington are literally "Feeding the Province." """)

# Slide 7: Perth GDP (COLUMN CHART)
slide = prep_clean_slide(prs, WHITE_LAYOUT)
populate_slide_left_text(slide, "Perth's Provincial Value Chain Impact", 
"""- Generates $2.98 Billion in Agri-Food GDP directly attributed to its raw farm output (Ranked #3 in Ontario).
- Achieved a massive 35.3% real inflation-adjusted GDP growth from 2012–2024.
- Supports 47,487 supply chain jobs province-wide (5.5% of Ontario's total agri-food workforce).""")

chart_data = CategoryChartData()
chart_data.categories = ['2012', '2014', '2019', '2022', '2024']
chart_data.add_series('Real GDP ($M)', (2204, 2439, 2798, 2907, 2983))
chart = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, chart_x, chart_y, chart_cx, chart_cy, chart_data).chart

# Slide 8: Wellington GDP (COLUMN CHART)
slide = prep_clean_slide(prs, WHITE_LAYOUT)
populate_slide_left_text(slide, "Wellington's Provincial Value Chain Impact", 
"""- Generates $2.69 Billion in Agri-Food GDP (Ranked #5 in the province).
- Achieved a 32.2% real inflation-adjusted GDP growth from 2012–2024.
- Proved Exceptionally resilient: Wellington grew during the 2020 pandemic downturn (+0.9%) while others suffered.
- Supports 42,845 supply chain jobs (4.9% of Ontario's total).""")

chart_data = CategoryChartData()
chart_data.categories = ['2012', '2014', '2019', '2022', '2024']
chart_data.add_series('Real GDP ($M)', (2037, 2401, 2205, 2624, 2692))
chart = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, chart_x, chart_y, chart_cx, chart_cy, chart_data).chart

# Slide 9: Combined
slide = prep_clean_slide(prs, WHITE_LAYOUT) 
populate_slide_left_text(slide, "A Two-County Agronomic Powerhouse", 
"""- Together, Perth and Wellington generate $5.68 Billion in Agri-Food GDP.
- This accounts for a staggering 11.0% of Ontario's entire agri-food economy.
- Combined, the two counties support over 90,000 agri-food jobs across the province.
- This represents more than one in ten of all agri-food workers in Ontario.""")

# Slide 10: COCS
slide = prep_clean_slide(prs, WHITE_LAYOUT)
populate_slide_left_text(slide, "Farmland Pays Its Own Way", 
"""- A recent OFA study proves farmland acts as a massive net fiscal positive for rural municipalities.
- Farmland pays significantly more in property tax revenue than it ever demands in municipal services.
- Data proves for every 1% of a county's land mass removed from agriculture, municipal operating surpluses drop by over $240,000 annually.
- Agriculture effectively subsidizes other property classes in rural regions.""")

# Slide 11: Perth Tax (BAR CHART)
slide = prep_clean_slide(prs, WHITE_LAYOUT)
populate_slide_left_text(slide, "Surging Tax Burden: Perth County", 
"""- Farm property assessment (CVA) exploded from $2.44B in 2010 to $7.57B (+209.6%).
- Driven by speculative land values, farming's share of the upper-tier tax burden expanded from 17.5% to 27.1%.
- Total municipal property tax paid by farmers soared 224% to over $5.50 million.""")

chart_data = CategoryChartData()
chart_data.categories = ['2010', '2024']
chart_data.add_series('Ag Share of Upper-Tier Tax %', (17.5, 27.1))
chart = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, chart_x, chart_y, chart_cx, chart_cy, chart_data).chart
chart.has_legend = False

# Slide 12: Wellington Tax (BAR CHART)
slide = prep_clean_slide(prs, WHITE_LAYOUT)
populate_slide_left_text(slide, "Surging Tax Burden: Wellington County", 
"""- Farm property assessment (CVA) exploded from $1.88B to $5.16B (+173.8%).
- Total municipal farm tax payments surged 197.8%, ballooning to $8.89 million annually.
- The agricultural share of Wellington's total upper-tier tax burden surged massively from 4.1% to 6.5%.
- Agriculture is increasingly carrying rural county budgets.""")

chart_data = CategoryChartData()
chart_data.categories = ['2010', '2024']
chart_data.add_series('Ag Share of Upper-Tier Tax %', (4.1, 6.5))
chart = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, chart_x, chart_y, chart_cx, chart_cy, chart_data).chart
chart.has_legend = False

# Slide 13: Conclusion
slide = prep_clean_slide(prs, CONCLUSION_LAYOUT) 
populate_slide_left_text(slide, "Key Takeaways", 
"""- Perth and Wellington are undisputed, multi-billion dollar economic engines.
- They sustain 11% of Ontario's entire agri-food economy and support 90,000 jobs.
- However, uncontrolled residential/speculative assessment growth has forced farmers to absorb a rapidly increasing and heavily disproportionate share of the local municipal tax levy.
- Farmland is not just food—it's a critical financial pillar of municipal government.""")

prs.save(OUTPUT_PATH)
print("Formatting fixed successfully! Strict strict spatial coordinate layouts implemented.")
