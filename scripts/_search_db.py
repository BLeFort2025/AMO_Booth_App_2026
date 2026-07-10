"""Extract key papers for policy analysis."""
import sqlite3

DB = r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Ben Desktop Files\Economic Analyst Position\Economic papers\Ag Economic Research Database\ag_econ_research.db"

conn = sqlite3.connect(DB)
c = conn.cursor()

# Get full abstracts of the most relevant papers
key_papers = [
    ("Understanding the Risks and Vulnerabilities Facing the Canadian Agricultural Fertilizer Market", 2022),
    ("Food Security in the Wake of the Ukrainian Crisis", 2022),
    ("Producer margins in a high-expense and high-price environment", 2023),
    ("Application of Border Carbon Adjustments (BCAs) to International Fertilizer Trade", 2023),
    ("2025 FCC Food and Beverage Report", 2025),
    ("Unraveling demand and supply shocks in the U.S. nitrogen market", 2025),
    ("Carbon tax pass-through in western Canadian grain transportation", 2025),
    ("Tariffs and U.S. beer demand", 2025),
]

for title_search, yr in key_papers:
    c.execute("""
        SELECT title, year, source_name, abstract, full_text, pdf_local_path FROM papers 
        WHERE LOWER(title) LIKE ? AND year = ?
    """, (f"%{title_search.lower()}%", yr))
    rows = c.fetchall()
    if rows:
        for row in rows:
            title, year, src, abstract, ftext, pdf = row
            print("=" * 70)
            print(f"  [{year}] {title}")
            print(f"  Source: {src}")
            print(f"  PDF: {pdf}")
            if abstract:
                print(f"\n  ABSTRACT:\n  {abstract}\n")
            if ftext:
                # Print first 2000 chars of full text
                print(f"  FULL TEXT (first 2000 chars):\n  {ftext[:2000]}...")
            print()

# Also search for tariff pass-through reversal literature
print("\n\n" + "=" * 70)
print("  TARIFF REMOVAL / REVERSAL LITERATURE")
print("=" * 70)
c.execute("""
    SELECT title, year, source_name, abstract FROM papers 
    WHERE (LOWER(abstract) LIKE '%tariff remov%' OR LOWER(abstract) LIKE '%tariff reduct%'
           OR LOWER(abstract) LIKE '%tariff elimin%' OR LOWER(abstract) LIKE '%trade liberal%')
    AND (LOWER(abstract) LIKE '%price%' OR LOWER(abstract) LIKE '%pass%through%')
    ORDER BY citation_count DESC LIMIT 10
""")
for row in c.fetchall():
    title, year, src, abstract = row
    print(f"\n  [{year}] {title[:100]}")
    print(f"    Source: {src}")
    if abstract:
        print(f"    Abstract: {abstract[:300]}...")

# Search for green energy / hydrogen / green ammonia papers
print("\n\n" + "=" * 70)
print("  GREEN AMMONIA / HYDROGEN / CLEAN ENERGY FERTILIZER")
print("=" * 70)
c.execute("""
    SELECT title, year, source_name, abstract FROM papers 
    WHERE (LOWER(title) LIKE '%green ammonia%' OR LOWER(title) LIKE '%green hydrogen%'
           OR LOWER(title) LIKE '%renewable%fertiliz%' OR LOWER(title) LIKE '%clean%fertiliz%'
           OR LOWER(abstract) LIKE '%green ammonia%' OR LOWER(abstract) LIKE '%green hydrogen%fertiliz%')
    ORDER BY year DESC LIMIT 10
""")
for row in c.fetchall():
    title, year, src, abstract = row
    print(f"\n  [{year}] {title[:100]}")
    print(f"    Source: {src}")
    if abstract:
        print(f"    Abstract: {abstract[:300]}...")

conn.close()
