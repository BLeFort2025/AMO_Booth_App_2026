"""Regex-based script to inject citations securely at line-level."""
import re

with open('scripts/write_report.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Map unique substrings to their required citation
replacements = {
    # Perth Profile
    "in the previous 2016 Census.": "in the previous 2016 Census [1].",
    "number of farms reported in 2006 (2,538).": "number of farms reported in 2006 (2,538) [1] [4].",
    "to 468,690 acres in 2021.": "to 468,690 acres in 2021 [1].",
    "acres of dry beans.": "acres of dry beans [1].",
    "behind only Huron County (821,378).": "behind only Huron County (821,378) [1] [11].",
    "behind only Oxford County (39,374).": "behind only Oxford County (39,374) [1] [12].",
    "average age of farm operators in Perth County was 53.6 years.": "average age of farm operators in Perth County was 53.6 years [1].",
    "and 33% of operators are female.": "and 33% of operators are female [1].",
    "in the county operate as family or non-family corporations.": "in the county operate as family or non-family corporations [1].",
    "Perth County reached $9.88 billion in 2021.": "Perth County reached $9.88 billion in 2021 [6].",
    "Total gross farm receipts were $1.76 billion.": "Total gross farm receipts were $1.76 billion [7].",
    "Total farm operating expenses were $1.43 billion.": "Total farm operating expenses were $1.43 billion [8].",
    "paid work outside of the farm operation in 2020.": "paid work outside of the farm operation in 2020 [9].",
    "estimated $1.52 billion in farm cash receipts.": "estimated $1.52 billion in farm cash receipts [5].",

    # Wellington Profile
    "farms in Wellington County in 2021.": "farms in Wellington County in 2021 [1].",
    "down slightly from 2,876 in 2006.": "down slightly from 2,876 in 2006 [1] [4].",
    "from 356,864 in 2016 to 348,739 acres in 2021.": "from 356,864 in 2016 to 348,739 acres in 2021 [1].",
    "24% of operators are female.": "24% of operators are female [1].",
    "value of farm capital was $8.39 billion in 2021.": "value of farm capital was $8.39 billion in 2021 [6].",
    "Total gross farm receipts were $1.16 billion.": "Total gross farm receipts were $1.16 billion [7].",
    "Total farm operating expenses were $979 million.": "Total farm operating expenses were $979 million [8].",
    "paid work outside of the farm operation.": "paid work outside of the farm operation [9].",
    "1 spot for poultry inventory (6.67 million birds).": "1 spot for poultry inventory (6.67 million birds) [1].",
    "in farm cash receipts in 2024.": "in farm cash receipts in 2024 [5].",

    # Economic impact (Note the new strings from my previous OMAFA rewrite)
    "raw agricultural product originated.'": "raw agricultural product originated [13].'",
    "entire $51.4 billion agri-food GDP.'": "entire $51.4 billion agri-food GDP [13].'",
    "simply benefiting from rising market prices.'": "simply benefiting from rising market prices [13].'",
    "spanning farm operators, processing technicians, and supply chain logistics professionals.'": "spanning farm operators, processing ' \\\n    'technicians, and supply chain logistics professionals [13].'",
    "primary agricultural output.'": "primary agricultural output [13].'",
    "entire agri-food GDP.'": "entire agri-food GDP [13].'",
    "posting back-to-back records in 2022, 2023, and 2024.'": "posting back-to-back records in 2022, 2023, and 2024 [13].'",
    "total agri-food workforce.'": "total agri-food workforce [13].'",
    "highly skilled graduates.'": "highly skilled graduates [13].'",
    "contributor to the provincial economy.'": "contributor to the provincial economy [13].'",
    
    # Filename
    "'Report_v5.docx'": "'Report_v6.docx'",
    "'Report_v6.docx'": "'Report_v6.docx'" # To prevent double replacements
}

success_count = 0
for i in range(len(lines)):
    for target, replacement in replacements.items():
        if target in lines[i] and replacement not in lines[i]:
            lines[i] = lines[i].replace(target, replacement)
            success_count += 1

with open('scripts/write_report.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f"Applied {success_count} citations to write_report.py")
