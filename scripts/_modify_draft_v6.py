import docx
from docx.enum.text import WD_COLOR_INDEX
from pathlib import Path

# Paths
base_dir = Path(r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Ben Desktop Files\Budgets\Federal\2026")
in_path = base_dir / "DRAFT OFA 2026 Federal Prebudget Submission.docx" # reading from the original untouched draft again
out_path = base_dir / "DRAFT OFA 2026 Federal Prebudget Submission_v6.docx"

doc = docx.Document(str(in_path))

# The blocks of text to insert
insert1_text = "The cost of failing to build this infrastructure is steep. A glaring example is Canada’s lack of a domestic, high-velocity West-East agricultural input corridor. While Western Canada produces abundant domestic nitrogen, Eastern Canada lacks the rail infrastructure to access it. When the federal government imposed a 35% tariff on Russian fertilizer in 2022, OFA’s econometric modeling revealed that Ontario farmers bore the brunt of the penalty. The tariff intentionally severed baseline supply, forcing Eastern importers to substitute via the global spot maritime market right when ocean freight and insurance costs had skyrocketed. Predictably, this structural isolation drove a +46.3% explosion in Ontario nitrogen prices compared to just +29.2% in Western Canada."

insert2a_text = "High-Velocity Regional Blending Hubs: Expanding throughput capabilities at regional rail-to-truck transfer yards. Current bottlenecked transloads prevent the rapid deployment of inputs during the narrow spring seeding window. Advanced blending hubs allow retailers to rapidly deploy inputs and apply local Nitrogen Stabilizers (e.g., urease inhibitors) immediately prior to farm delivery, explicitly advancing the ECCC’s 30% emissions reduction mandate without physically destroying the fragile coatings of Enhanced Efficiency Fertilizers (EEFs)."

insert2b_text = "Direct Unit-Train Rail Connectivity: Expanding dedicated agricultural passing sidings and high-velocity terminal infrastructure to enable \"continuous motion\" direct unit trains from Western Canada. This eliminates the necessity of destructive multi-touch transloads (such as augering into Laker vessels), preserves the agronomic integrity of modern EEFs, and permanently expands absolute rail network capacity without penalizing Western grain exports."

new_recommendation = "Recommendation: Establish a dedicated agriculture and agri-food infrastructure funding stream. Furthermore, we urge Transport Canada’s National Supply Chain Office and the National Trade Corridors Fund (NTCF) to prioritize 50/50 matching investments for a sovereign, direct-rail West-East Agricultural Input Corridor to protect the integrity of the domestic food supply."

found_insert1 = False
found_insert2 = False

for i, p in enumerate(doc.paragraphs):
    text = p.text.strip()
    
    # Insertion 1
    if "that are not easily captured through direct revenue streams" in text and not found_insert1:
        next_p = doc.paragraphs[i+1]
        new_p = next_p.insert_paragraph_before("")
        run = new_p.add_run(insert1_text)
        run.font.highlight_color = WD_COLOR_INDEX.PINK
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
        run1.font.highlight_color = WD_COLOR_INDEX.PINK
        
        # Add Bullet 2
        new_b2 = next_p.insert_paragraph_before("", style='List Paragraph')
        try:
            new_b2.style = 'List Bullet'
        except:
            pass
        run2 = new_b2.add_run(insert2b_text)
        run2.font.highlight_color = WD_COLOR_INDEX.PINK
        found_insert2 = True
        
    # Insertion 3 (Recommendation)
    if text.startswith("Recommendation: Establish a dedicated agriculture and agri-food infrastructure funding stream"):
        p.clear()
        r1 = p.add_run("Recommendation: ")
        r1.bold = True
        rest = new_recommendation.replace("Recommendation: ", "")
        r2 = p.add_run(rest)
        r2.font.highlight_color = WD_COLOR_INDEX.PINK

print("Saving V6 modified document...")
doc.save(str(out_path))
print(f"Document saved successfully: {out_path}")
