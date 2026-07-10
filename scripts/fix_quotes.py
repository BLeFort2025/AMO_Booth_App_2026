"""Fix syntax errors introduced by escaped quotes in write_report.py."""

with open('scripts/write_report.py', 'r', encoding='utf-8') as f:
    text = f.read()

# I carelessly injected [1].\' using raw strings. 
# Here we fix `.\'` by replacing it with just `.'`
while r"\]\.\'" in text:
    text = text.replace(r"\]\.\'", "].'")
    
# Same for just `[13].\'`
while "\].\\'" in text:
    text = text.replace("\].\\'", "].'")

# Actually the literal string in python source looks like: `[13].\'`
text = text.replace("].\\'", "].'")

with open('scripts/write_report.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("Quotes fixed")
