import docx
from docx.enum.text import WD_COLOR_INDEX
from pathlib import Path

# Paths
base_dir = Path(r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Ben Desktop Files\Budgets\Federal\2026")
in_path = base_dir / "DRAFT OFA 2026 Federal Prebudget Submission.docx" # reading from the original untouched draft again
out_path = base_dir / "DRAFT OFA 2026 Federal Prebudget Submission_v7.docx"

doc = docx.Document(str(in_path))

# The blocks of text to insert
insert1_text = "The cost of failing to build this infrastructure is steep. The 35% tariff on Russian fertilizer was a necessary geopolitical sanction; however, it inadvertently exposed the crippling fragility of Eastern Canada's agricultural supply chain. Because Eastern Canada is completely unintegrated with Western Canadian bulk production, the region absorbed entirely disproportionate economic damage from the federal policy. The resulting +46.3% explosion in Ontario nitrogen prices proved that Canada cannot execute aggressive foreign policy mandates without simultaneously dealing devastating economic blowback to its own agricultural producers. A sovereign, domestic West-East agricultural corridor is the physical infrastructure required for Canada to achieve permanent Sanction Resilience."

insert2a_text = "Centralized Break-Bulk Rail Terminals: Establishing a massive, centralized Class-1 Hub-and-Spoke Rail Terminal in Southern Ontario. 100-car unit trains from the West unpack rapidly via high-velocity loop tracks at a singular industrial Hub, avoiding demurrage, and are seamlessly dispersed via short-line 'spokes' to regional retailers. This permanently solves the Eastern bulk-capacity bottleneck while respecting CN/CPKC's Precision Scheduled Railroading physics."

insert2b_text = "Inter-Ministerial Infrastructure Modernization: A bifurcated capital stack where Transport Canada (via the NTCF) funds the heavy civil engineering of the centralized Hub (concrete, track loops, mainline passing tracks), while Agriculture and Agri-Food Canada (AAFC) and ECCC fund the advanced agronomic technologies at the regional spokes. This equips retail spokes with state-of-the-art liquid-impregnation and blending equipment, enabling the just-in-time deployment of Nitrogen Stabilizers to directly execute the ECCC's 30% emissions reduction mandate."

new_recommendation = "Recommendation: Establish a dedicated agriculture and agri-food infrastructure funding stream. Furthermore, we urge an Inter-Ministerial capital stack where Transport Canada (NTCF) and AAFC prioritize co-investments into a sovereign West-East Hub-and-Spoke rail corridor, ensuring Sanction Resilience and decarbonizing the agricultural supply chain."

found_insert1 = False
found_insert2 = False

for i, p in enumerate(doc.paragraphs):
    text = p.text.strip()
    
    # Insertion 1
    if "that are not easily captured through direct revenue streams" in text and not found_insert1:
        next_p = doc.paragraphs[i+1]
        new_p = next_p.insert_paragraph_before("")
        run = new_p.add_run(insert1_text)
        run.font.highlight_color = WD_COLOR_INDEX.YELLOW
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
        r1 = p.add_run("Recommendation: ")
        r1.bold = True
        rest = new_recommendation.replace("Recommendation: ", "")
        r2 = p.add_run(rest)
        r2.font.highlight_color = WD_COLOR_INDEX.YELLOW

print("Saving V7 modified document...")
doc.save(str(out_path))
print(f"Document saved successfully: {out_path}")
