import docx
from docx.enum.text import WD_COLOR_INDEX
from pathlib import Path

# Paths
base_dir = Path(r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Ben Desktop Files\Budgets\Federal\2026")
in_path = base_dir / "DRAFT OFA 2026 Federal Prebudget Submission.docx" # reading from the original untouched draft
out_path = base_dir / "DRAFT OFA 2026 Federal Prebudget Submission_v4.docx"

doc = docx.Document(str(in_path))

# The blocks of text to insert
insert1_text = "The cost of failing to build this infrastructure is steep. A glaring example is Canada’s lack of a domestic, West-East agricultural input corridor. While Western Canada produces abundant domestic nitrogen fueled by deeply discounted local natural gas (AECO), Eastern Canada relies on international maritime supply chains. When the federal government imposed a 35% tariff on Russian fertilizer in 2022, OFA’s econometric modeling revealed that Ontario farmers bore the brunt of the penalty. Simply removing Russian supply forced Eastern importers to substitute via the highly volatile global spot maritime market right when ocean freight and insurance costs had skyrocketed. Predictably, this lack of domestic structural integration drove a +46.3% explosion in Ontario nitrogen prices compared to just +29.2% in Western Canada."

insert2a_text = "The Strategic Agricultural Input Reserve: The Great Lakes maritime seaway freezes shut precisely when farmers need to seed in the spring. In Phase 1, the federal government must invest in massive, specialized climate-controlled bulk silos at deep-water ports (e.g., Hamilton-Oshawa Port Authority) to establish a Strategic Agricultural Reserve. This allows the sector to safely stockpile inventory through the winter, buffering the food supply against spring geopolitical shocks while providing the physical warehousing required to expand the use of ECCC-mandated Enhanced Efficiency Fertilizers (EEFs)."

insert2b_text = "West-East Transload Infrastructure: Expanding bulk-handling terminals at the Port of Thunder Bay and funding dedicated agricultural rail sidings and hopper fleets. Transitioning from highly vulnerable international maritime imports to a secure domestic supply chain grants Eastern Canada true food security sovereignty and significantly insulates the farmgate from global warfare and maritime shipping disruptions."

new_recommendation = "Recommendation: Establish a dedicated agriculture and agri-food infrastructure funding stream tailored to support mid-scale, regionally distributed supply chain projects. Furthermore, we urge Transport Canada’s National Supply Chain Office and the National Trade Corridors Fund (NTCF) to prioritize the full federal financing of a sovereign West-East Agricultural Input Corridor to protect the integrity of the domestic food supply."

found_insert1 = False
found_insert2 = False

for i, p in enumerate(doc.paragraphs):
    text = p.text.strip()
    
    # Insertion 1
    if "that are not easily captured through direct revenue streams" in text and not found_insert1:
        next_p = doc.paragraphs[i+1]
        new_p = next_p.insert_paragraph_before("")
        run = new_p.add_run(insert1_text)
        run.font.highlight_color = WD_COLOR_INDEX.TURQUOISE
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
        run1.font.highlight_color = WD_COLOR_INDEX.TURQUOISE
        
        # Add Bullet 2
        new_b2 = next_p.insert_paragraph_before("", style='List Paragraph')
        try:
            new_b2.style = 'List Bullet'
        except:
            pass
        run2 = new_b2.add_run(insert2b_text)
        run2.font.highlight_color = WD_COLOR_INDEX.TURQUOISE
        found_insert2 = True
        
    # Insertion 3 (Recommendation)
    if text.startswith("Recommendation: Establish a dedicated agriculture and agri-food infrastructure funding stream"):
        p.clear()
        r1 = p.add_run("Recommendation: ")
        r1.bold = True
        rest = new_recommendation.replace("Recommendation: ", "")
        r2 = p.add_run(rest)
        r2.font.highlight_color = WD_COLOR_INDEX.TURQUOISE

print("Saving V4 modified document...")
doc.save(str(out_path))
print(f"Document saved successfully: {out_path}")
