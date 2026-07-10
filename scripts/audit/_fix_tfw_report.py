"""Replace TFW labor context block with enhanced version."""
import sys
from pathlib import Path

path = str(list(Path('app/pages').glob('8_*Simulator*'))[0])
content = open(path, 'r', encoding='utf-8').read()

# Find the block to replace by searching for the unique marker lines
marker_start = '    # TFW labor context\n'
marker_end_old = "vacancy shock, reducing output through the Labor Realization Factor (\u03c6={sector_params['phi']}).\\n\"\n        )\n"

start_idx = content.find(marker_start)
if start_idx == -1:
    print("ERROR: Could not find start marker")
    sys.exit(1)

end_idx = content.find(marker_end_old, start_idx)
if end_idx == -1:
    print("ERROR: Could not find end marker")
    sys.exit(1)
end_idx += len(marker_end_old)

old_block = content[start_idx:end_idx]
print(f"Found block at chars {start_idx}-{end_idx} ({len(old_block)} chars)")

new_block = """    # TFW labor context
    if proj_tfw_reduction > 0 and _tfw_dep > 0:
        tfw_implied_vacancy = _tfw_dep * (proj_tfw_reduction / 100.0)
        effective_lrf = max(0.0, 1.0 - sector_params['phi'] * tfw_implied_vacancy)
        output_loss_pct = (1 - effective_lrf) * 100
        report_parts.append(
            f"\\n\U0001f477 **Labor Impact**: {region} has a TFW dependency of "
            f"**{_tfw_dep:.0%}** ({int(_labor_row['tfw_ag']):,} temporary foreign workers "
            f"out of {int(_labor_row['total_employees']):,} total employees). "
            f"A **{proj_tfw_reduction}%** reduction in TFW access creates "
            f"**{tfw_implied_vacancy:.1%}** additional vacancies, reducing the "
            f"Labor Realization Factor to **{effective_lrf:.2f}** "
            f"(a **{output_loss_pct:.0f}%** output penalty).\\n\\n"
        )
        report_parts.append(
            f"**How to read these results:** The Immediate Impact section (Year 0) "
            f"reflects only input cost shocks and does **not** capture labor shortages. "
            f"The TFW labor penalty activates in **Year 1 onward** of the Multi-Year "
            f"Projection, reflecting the reality that program changes take at least one "
            f"growing season to affect harvesting, planting, and processing capacity. "
            f"In the Year-by-Year table, watch the **LRF column** \u2014 when it drops "
            f"below 1.0, the sector is losing potential output to unfilled positions. "
            f"At LRF = {effective_lrf:.2f}, the sector can only realize "
            f"**{effective_lrf:.0%}** of its productive capacity.\\n"
        )
"""

content = content[:start_idx] + new_block + content[end_idx:]
open(path, 'w', encoding='utf-8').write(content)
print("OK: replaced TFW block successfully")

# Verify syntax
import ast
ast.parse(content)
print("Syntax check: PASSED")
print(f"Total lines: {len(content.splitlines())}")
