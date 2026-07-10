"""Script to inject bracketed citations into the report generator."""

with open('scripts/write_report.py', 'r', encoding='utf-8') as f:
    code = f.read()

replacements = [
    # Perth Profile 
    ("in the previous 2016 Census.", "in the previous 2016 Census [1]."),
    ("number of farms reported in 2006 (2,538).", "number of farms reported in 2006 (2,538) [1] [4]."),
    ("to 468,690 acres in 2021.", "to 468,690 acres in 2021 [1]."),
    ("Perth County farms report over 25,000 acres of dry beans", "Perth County farms report over 25,000 acres of dry beans [1]."),
    ("behind only Huron County (821,378).", "behind only Huron County (821,378) [1] [11]."),
    ("behind only Oxford County (39,374).", "behind only Oxford County (39,374) [1] [12]."),
    ("average age of farm operators in Perth County was 53.6 years.", "average age of farm operators in Perth County was 53.6 years [1]."),
    ("and 33% of operators are female.", "and 33% of operators are female [1]."),
    ("in the county operate as family or non-family corporations.", "in the county operate as family or non-family corporations [1]."),
    ("The value of farm capital in Perth County reached $9.88 billion in 2021", "The value of farm capital in Perth County reached $9.88 billion in 2021 [6]."),
    ("Total gross farm receipts were $1.76 billion", "Total gross farm receipts were $1.76 billion [7]."),
    ("Total farm operating expenses were $1.43 billion", "Total farm operating expenses were $1.43 billion [8]."),
    ("paid work outside of the farm operation in 2020.", "paid work outside of the farm operation in 2020 [9]."),
    ("In 2024, Perth County farms generated an estimated $1.52 billion in farm cash receipts", "In 2024, Perth County farms generated an estimated $1.52 billion in farm cash receipts [5]."),

    # Wellington Profile
    ("There were 2,617 census farms in Wellington County in 2021", "There were 2,617 census farms in Wellington County in 2021 [1]."),
    ("down slightly from 2,876 in 2006.", "down slightly from 2,876 in 2006 [1] [4]."),
    ("from 356,864 in 2016 to 348,739 acres in 2021.", "from 356,864 in 2016 to 348,739 acres in 2021 [1]."),
    ("24% of operators are female.", "24% of operators are female [1]."),
    ("Wellington County holds the number one provincial rank for cattle and calves", "Wellington County holds the number one provincial rank for cattle and calves [1]."),
    ("number one spot for poultry inventory (6.67 million birds).", "number one spot for poultry inventory (6.67 million birds) [1]."),
    ("36% operating as corporations.", "36% operating as corporations [1]."),
    ("Total gross farm receipts were $1.16 billion", "Total gross farm receipts were $1.16 billion [7]."),
    ("Total farm operating expenses were $979 million", "Total farm operating expenses were $979 million [8]."),
    ("The value of farm capital was $8.39 billion in 2021", "The value of farm capital was $8.39 billion in 2021 [6]."),
    ("paid work outside of the farm operation.", "paid work outside of the farm operation [9]."),
    ("Wellington County farms generated $1.36 billion in farm cash receipts in 2024", "Wellington County farms generated $1.36 billion in farm cash receipts in 2024 [5]."),
    
    # Econ Impact 
    ("raw agricultural product originated.'", "raw agricultural product originated [13].'"),
    ("entire $51.4 billion agri-food GDP.'", "entire $51.4 billion agri-food GDP [13].'"),
    ("simply benefiting from rising market prices.'", "simply benefiting from rising market prices [13].'"),
    ("spanning farm operators, processing technicians, and supply chain logistics professionals.'", "spanning farm operators, processing ' \\\n    'technicians, and supply chain logistics professionals [13].'"),
    ("Because of their proximity to Perth's world-class primary agricultural output.'", "because of their proximity to Perth\\'s world-class primary agricultural output.'"), 
    
    ("accounting for 5.2% of Ontario's entire agri-food GDP.'", "accounting for 5.2% of Ontario\\'s entire agri-food GDP [13].'"),
    ("posting back-to-back records in 2022, 2023, and 2024.'", "posting back-to-back records in 2022, 2023, and 2024 [13].'"),
    ("4.9% of Ontario's total agri-food workforce.'", "4.9% of Ontario\\'s total agri-food workforce [13].'"),
    ("technological innovation, and highly skilled graduates.'", "technological innovation, and highly skilled graduates [13].'"),
    ("critical contributor to the provincial economy.'", "critical contributor to the provincial economy [13].'"),
    
    # Version bump
    ("'Report_v5.docx'", "'Report_v6.docx'")
]

for old, new in replacements:
    # Some strings might have weird escape chars in my replacements list above vs the code.
    # We will just replace text.
    code = code.replace(old, new)
    
# Manual fixes for complex lines
code = code.replace("because of their proximity to Perth\\'s world-class primary agricultural output.'", "because of their proximity to Perth\\'s world-class primary agricultural output [13].'")


with open('scripts/write_report.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Applied citations to write_report.py")
