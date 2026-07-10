"""Final citation applier using regex on the full file text."""
import re

with open('scripts/write_report.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Tuples of (regex_pattern, replacement)
replacements = [
    (r'in the previous 2016 Census\.\'', r'in the previous 2016 Census [1].\''),
    (r'reported in 2006 \(2,538\)\.\'', r'reported in 2006 (2,538) [1] [4].\''),
    (r'to 468,690 acres in 2021\.\'', r'to 468,690 acres in 2021 [1].\''),
    (r'acres of dry beans\.\'', r'acres of dry beans [1].\''),
    (r'only Huron County \(821,378\)\.\'', r'only Huron County (821,378) [1] [11].\''),
    (r'only Oxford County \(39,374\)\.\'', r'only Oxford County (39,374) [1] [12].\''),
    (r'Perth County was 53\.6 years\.\'', r'Perth County was 53.6 years [1].\''),
    (r'33% of operators are female\.\'', r'33% of operators are female [1].\''),
    (r'family or non-family corporations\.\'', r'family or non-family corporations [1].\''),
    (r'reached \$9\.88 billion in 2021\.\'', r'reached $9.88 billion in 2021 [6].\''),
    (r'receipts were \$1\.76 billion\.\'', r'receipts were $1.76 billion [7].\''),
    (r'expenses were \$1\.43 billion\.\'', r'expenses were $1.43 billion [8].\''),
    (r'farm operation in 2020\.\'', r'farm operation in 2020 [9].\''),
    (r'1\.52 billion in farm cash receipts\.\'', r'1.52 billion in farm cash receipts [5].\''),

    (r'Wellington County in 2021\.\'', r'Wellington County in 2021 [1].\''),
    (r'slightly from 2,876 in 2006\.\'', r'slightly from 2,876 in 2006 [1] [4].\''),
    (r'to 348,739 acres in 2021\.\'', r'to 348,739 acres in 2021 [1].\''),
    (r'24% of operators are female\.\'', r'24% of operators are female [1].\''),
    (r'\$8\.39 billion in 2021\.\'', r'$8.39 billion in 2021 [6].\''),
    (r'receipts were \$1\.16 billion\.\'', r'receipts were $1.16 billion [7].\''),
    (r'expenses were \$979 million\.\'', r'expenses were $979 million [8].\''),
    (r'of the farm operation\.\'', r'of the farm operation [9].\''),
    (r'inventory \(6\.67 million birds\)\.\'', r'inventory (6.67 million birds) [1].\''),
    (r'cash receipts in 2024\.\'', r'cash receipts in 2024 [5].\''),

    (r'product originated\.\'', r'product originated [13].\''),
    (r'\$51\.4 billion agri-food GDP\.\'', r'$51.4 billion agri-food GDP [13].\''),
    (r'rising market prices\.\'', r'rising market prices [13].\''),
    (r'logistics professionals\.\'', r'logistics professionals [13].\''),
    (r'primary agricultural output\.\'', r'primary agricultural output [13].\''),
    (r'entire agri-food GDP\.\'', r'entire agri-food GDP [13].\''),
    (r'2022, 2023, and 2024\.\'', r'2022, 2023, and 2024 [13].\''),
    (r'total agri-food workforce\.\'', r'total agri-food workforce [13].\''),
    (r'highly skilled graduates\.\'', r'highly skilled graduates [13].\''),
    (r'provincial economy\.\'', r'provincial economy [13].\''),
]

for old, new in replacements:
    text = re.sub(old, new, text)

# Just in case, also ensure Report_v5 goes to Report_v6
text = text.replace("'Report_v5.docx'", "'Report_v6.docx'")

with open('scripts/write_report.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("regex search limits applied.")
