"""Audit tables.yml vs app usage. JSON output."""
import re, yaml, json
from pathlib import Path

ROOT = Path(__file__).parent
CONFIG = ROOT / "config" / "tables.yml"
APP_DIR = ROOT / "app"
SCRIPTS_DIR = ROOT / "scripts"

cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
tables_list = cfg.get("tables", cfg)

all_tables = {}
for t in tables_list:
    tid = str(t.get("id", ""))
    all_tables[tid] = {
        "name": t.get("name", ""),
        "theme": t.get("theme", ""),
        "source": t.get("source", "statcan"),
        "active": t.get("active", True),
        "csv": t.get("csv", ""),
    }

csv_names = {}
for tid, info in all_tables.items():
    csv_val = info["csv"]
    if csv_val:
        csv_names[csv_val] = tid
    csv_names[f"{tid}.csv"] = tid

app_files = list(APP_DIR.rglob("*.py"))
engine_file = SCRIPTS_DIR / "io_multipliers_engine.py"
if engine_file.exists():
    app_files.append(engine_file)

statcan_pattern = re.compile(r'\b(\d{2}-\d{2}-\d{4}-\d{2})\b')
compact_pattern = re.compile(r'\b(\d{8})\b')

found_in_app = set()

for pyfile in app_files:
    content = pyfile.read_text(encoding="utf-8", errors="ignore")
    for m in statcan_pattern.finditer(content):
        found_in_app.add(m.group(1))
    for m in compact_pattern.finditer(content):
        cid = m.group(1)
        if len(cid) == 8:
            dashed = f"{cid[:2]}-{cid[2:4]}-{cid[4:8]}-01"
            if dashed.startswith(("32-", "18-", "34-", "36-", "38-", "12-", "23-", "16-")):
                found_in_app.add(dashed)
    for csv_name in csv_names:
        if csv_name in content:
            found_in_app.add(csv_names[csv_name])
    for tid in all_tables:
        if tid in content:
            found_in_app.add(tid)

result = {"not_used": [], "used": [], "inactive": []}

for tid, info in sorted(all_tables.items()):
    entry = {"id": tid, "name": info["name"], "theme": info["theme"], "source": info["source"]}
    if not info["active"]:
        result["inactive"].append(entry)
    elif tid in found_in_app:
        result["used"].append(entry)
    else:
        result["not_used"].append(entry)

result["summary"] = {
    "total": len(all_tables),
    "active": len(all_tables) - len(result["inactive"]),
    "used": len(result["used"]),
    "not_used": len(result["not_used"]),
    "inactive": len(result["inactive"]),
}

app_only = found_in_app - set(all_tables.keys())
result["in_app_not_in_yml"] = sorted(app_only)

with open("_audit_results.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=True)
print("DONE")
