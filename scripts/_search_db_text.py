import sqlite3
import re

DB = r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Ben Desktop Files\Economic Analyst Position\Economic papers\Ag eastern Research Database\ag_econ_research.db"
DB = r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Ben Desktop Files\Economic Analyst Position\Economic papers\Ag Economic Research Database\ag_econ_research.db"

conn = sqlite3.connect(DB)
c = conn.cursor()

titles = [
    "Understanding the Risks and Vulnerabilities Facing the Canadian Agricultural Fertilizer Market",
    "Food Security in the Wake of the Ukrainian Crisis",
    "Application of Border Carbon Adjustments (BCAs) to International Fertilizer Trade",
    "Tariffs and U.S. beer demand: How protectionist policies could impact market shares and consumer welfare"
]

print("--- Checking Full Text for specific policies ---")
for t in titles:
    c.execute("SELECT id, title, full_text, abstract FROM papers WHERE LOWER(title) LIKE ?", (f"%{t.lower()}%",))
    row = c.fetchone()
    if row:
        pid, title, ftext, abstract = row
        text = ftext or abstract or ""
        print(f"\nTitle: {title}")
        print(f"Has full text: {bool(ftext)}. Length: {len(text)}")
        
        # Look for keywords in text
        for kw in ['tariff', 'domestic production', 'eastern', 'ontario', 'remove', 'supply chain', 'infrastructure', 'capacity']:
            matches = re.finditer(r'.{0,80}' + kw + r'.{0,80}', text, re.IGNORECASE)
            snippets = [m.group(0).replace('\n', ' ') for m in list(matches)[:3]]
            if snippets:
                print(f"  Key '{kw}':")
                for s in snippets:
                    print(f"    - ...{s.strip()}...")

print("\n--- Searching for Eastern Canada Domestic Fertilizer Production ---")
c.execute("""
    SELECT title, year, abstract, full_text FROM papers
    WHERE (LOWER(title) LIKE '%fertilizer%' OR LOWER(abstract) LIKE '%fertilizer%')
    AND (LOWER(abstract) LIKE '%domestic production%' OR LOWER(abstract) LIKE '%eastern canada%' OR LOWER(abstract) LIKE '%ontario%')
    ORDER BY year DESC
    LIMIT 10
""")
for row in c.fetchall():
    title, year, abstract, ftext = row
    text = ftext or abstract or ""
    if 'eastern canada' in text.lower() or 'ontario' in text.lower() or 'domestic production' in text.lower():
        print(f"\n[{year}] {title[:100]}")
        matches = re.finditer(r'.{0,80}(domestic production|eastern canada|ontario).{0,80}', text, re.IGNORECASE)
        for m in list(matches)[:2]:
            print(f"  - ...{m.group(0).strip()}...")

conn.close()
