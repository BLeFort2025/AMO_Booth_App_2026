import docx
from docx.enum.text import WD_COLOR_INDEX
from pathlib import Path

# Paths
base_dir = Path(r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Ben Desktop Files\Budgets\Federal\2026")
in_path = base_dir / "DRAFT OFA 2026 Federal Prebudget Submission.docx" # reading from the original untouched draft again to avoid double insertions
out_path = base_dir / "DRAFT OFA 2026 Federal Prebudget Submission_v3.docx"

doc = docx.Document(str(in_path))

# The blocks of text to insert
insert1_text = "The cost of failing to build this infrastructure is steep. A glaring example is Canada’s lack of a domestic, West-East agricultural input corridor. While Western Canada produces abundant domestic nitrogen fueled by deeply discounted local natural gas (AECO), Eastern Canada relies on international maritime supply chains tied to highly volatile global benchmarks (Henry Hub). When the federal government imposed a 35% tariff on Russian fertilizer in 2022, OFA’s econometric modeling revealed that Ontario farmers bore the brunt of the penalty. Importers shifted to US Gulf Coast supply, but lacking the rail infrastructure to seamlessly purchase from Western Canada, Eastern Canada became a captive market. Predictably, this structural rigidity drove a +46.3% explosion in Ontario nitrogen prices compared to just +29.2% in Western Canada."

insert2a_text = "Co-operative Deep-Water Storage Hubs: A public-private-cooperative partnership to build massive, specialized climate-controlled bulk silos at Great Lakes ports (e.g., Hamilton-Oshawa Port Authority). The Great Lakes maritime seaway freezes shut precisely when farmers need to seed in the spring. This Phase 1 infrastructure allows the sector to utilize lower-emission summer/fall maritime shipping to safely stockpile inventory through the winter, buffering farmers against spring geopolitical shocks and laying the warehousing foundation for future domestic 'Green Ammonia' distribution."

insert2b_text = "West-East Transload Infrastructure: Expanding bulk-handling terminals at the Port of Thunder Bay to receive Western Canadian fertilizer via dedicated rail and transfer it to domestic \"Laker\" vessels. Transitioning from bunker-fuel-burning international imports to modern domestic rail and Lakers significantly decarbonizes the agricultural supply chain while granting Eastern Canada true supply chain sovereignty."

new_recommendation = "Recommendation: Establish a dedicated agriculture and agri-food infrastructure funding stream—accessible to industry groups, co-operatives, and private-public partnerships—tailored to support mid-scale, regionally distributed supply chain projects. Furthermore, we urge Transport Canada’s National Supply Chain Office and the National Trade Corridors Fund (NTCF) to prioritize the establishment of a sovereign, decarbonized West-East Agricultural Input Corridor to protect the integrity of the domestic food supply."

found_insert1 = False
found_insert2 = False

for i, p in enumerate(doc.paragraphs):
    text = p.text.strip()
    
    # Insertion 1
    if "that are not easily captured through direct revenue streams" in text and not found_insert1:
        next_p = doc.paragraphs[i+1]
        new_p = next_p.insert_paragraph_before("")
        run = new_p.add_run(insert1_text)
        run.font.highlight_color = WD_COLOR_INDEX.BRIGHT_GREEN
        found_insert1 = True
        
    # Insertion 2 (bullets)
    if "Real-world examples of these overlooked but vital infrastructure projects include:" in text and not found_insert2:
        next_p = doc.paragraphs[i+1]
        
        # Add Bullet 1
        new_b1 = next_p.insert_paragraph_before("", style='List Paragraph')
        try:
            new_b1.style = 'List Bullet'
        except:
            pass
        run1 = new_b1.add_run(insert2a_text)
        run1.font.highlight_color = WD_COLOR_INDEX.BRIGHT_GREEN
        
        # Add Bullet 2
        new_b2 = next_p.insert_paragraph_before("", style='List Paragraph')
        try:
            new_b2.style = 'List Bullet'
        except:
            pass
        run2 = new_b2.add_run(insert2b_text)
        run2.font.highlight_color = WD_COLOR_INDEX.BRIGHT_GREEN
        found_insert2 = True
        
    # Insertion 3 (Recommendation)
    if text.startswith("Recommendation: Establish a dedicated agriculture and agri-food infrastructure funding stream"):
        p.clear()
        r1 = p.add_run("Recommendation: ")
        r1.bold = True
        rest = new_recommendation.replace("Recommendation: ", "")
        r2 = p.add_run(rest)
        r2.font.highlight_color = WD_COLOR_INDEX.BRIGHT_GREEN

print("Saving V3 modified document...")
doc.save(str(out_path))
print(f"Document saved successfully: {out_path}")
