import docx
from docx.enum.text import WD_COLOR_INDEX
from pathlib import Path

# Paths
base_dir = Path(r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Ben Desktop Files\Budgets\Federal\2026")
in_path = base_dir / "DRAFT OFA 2026 Federal Prebudget Submission.docx"
out_path = base_dir / "DRAFT OFA 2026 Federal Prebudget Submission_v2.docx"

doc = docx.Document(str(in_path))

# The blocks of text to insert
insert1_text = "The cost of failing to build this infrastructure is steep. A glaring example is Canada’s lack of a domestic, West-East agricultural input corridor. While Western Canada produces abundant domestic nitrogen and potash, Eastern Canada relies on international supply chains via the St. Lawrence Seaway. When the federal government imposed a 35% tariff on Russian fertilizer in 2022, OFA’s econometric modeling revealed that Ontario farmers bore the brunt of the geopolitical fallout. Because they lacked the trade-enabling infrastructure to simply purchase from Western Canada, Ontario farmers were forced to substitute with much more expensive international suppliers, driving a +46.3% explosion in Ontario nitrogen prices compared to just +29.2% in Western Canada. Securing our food supply requires physically connecting our domestic supply chains."

insert2a_text = "Deep-Water Agricultural Storage Hubs: A coalition of agricultural co-operatives partnering with local port authorities (such as the Hamilton-Oshawa Port Authority) to build massive, climate-controlled bulk silos. This Phase 1 infrastructure would allow the sector to stockpile fertilizer during global price valleys, buffering farmers against sudden geopolitical supply chain disruptions."

insert2b_text = "West-East Transload Infrastructure: Expanding bulk-handling terminals at the Port of Thunder Bay to receive Western Canadian fertilizer via rail and transfer it to domestic \"Laker\" vessels. This \"Nation Building\" infrastructure would finally allow Eastern Canada to purchase its agricultural inputs domestically rather than relying on vulnerable international imports."

new_recommendation = "Recommendation: Establish a dedicated agriculture and agri-food infrastructure funding stream—accessible to industry groups, co-operatives, and private-public partnerships—tailored to support mid-scale, regionally distributed supply chain projects. Furthermore, we urge the Major Projects Management Office (MPMO) and the National Trade Corridors Fund (NTCF) to prioritize the establishment of a sovereign West-East Agricultural Input Corridor as a critical nation-building and food security initiative."


def insert_paragraph_after(paragraph, text, style=None, highlight=True):
    new_p = paragraph.insert_paragraph_before(text, style)
    # Move the new paragraph down one so it comes AFTER the target
    p = new_p._p
    p.addnext(paragraph._p)
    
    # We just clear it and rebuild with highlight
    new_p.clear()
    run = new_p.add_run(text)
    if highlight:
        run.font.highlight_color = WD_COLOR_INDEX.YELLOW
    return new_p

found_insert1 = False
found_insert2 = False

# We have to manipulate the runs or paragraphs. 
# It's safer to just iterate and use insert_paragraph_before on the *next* paragraph.
for i, p in enumerate(doc.paragraphs):
    text = p.text.strip()
    
    # Insertion 1
    if "that are not easily captured through direct revenue streams" in text and not found_insert1:
        # Insert before the next paragraph
        next_p = doc.paragraphs[i+1]
        new_p = next_p.insert_paragraph_before("")
        run = new_p.add_run(insert1_text)
        run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        found_insert1 = True
        
    # Insertion 2 (bullets)
    if "Real-world examples of these overlooked but vital infrastructure projects include:" in text and not found_insert2:
        # Insert our bullets before the next paragraph
        next_p = doc.paragraphs[i+1]
        
        # Add Bullet 1
        new_b1 = next_p.insert_paragraph_before("", style='List Paragraph')
        # Workaround for bullet style if 'List Paragraph' doesn't auto-bullet (it depends on word template)
        # We'll just style it as List Bullet if it exists, otherwise normal
        try:
            new_b1.style = 'List Bullet'
        except:
            pass
        run1 = new_b1.add_run(insert2a_text)
        run1.font.highlight_color = WD_COLOR_INDEX.YELLOW
        
        # Add Bullet 2
        new_b2 = next_p.insert_paragraph_before("", style='List Paragraph')
        try:
            new_b2.style = 'List Bullet'
        except:
            pass
        run2 = new_b2.add_run(insert2b_text)
        run2.font.highlight_color = WD_COLOR_INDEX.YELLOW
        found_insert2 = True
        
    # Insertion 3 (Recommendation)
    if text.startswith("Recommendation: Establish a dedicated agriculture and agri-food infrastructure funding stream"):
        p.clear()
        
        # Bold the 'Recommendation:' part
        r1 = p.add_run("Recommendation: ")
        r1.bold = True
        
        # Add rest with highlight
        rest = new_recommendation.replace("Recommendation: ", "")
        r2 = p.add_run(rest)
        r2.font.highlight_color = WD_COLOR_INDEX.YELLOW

print("Saving modified document...")
doc.save(str(out_path))
print(f"Document saved successfully: {out_path}")
