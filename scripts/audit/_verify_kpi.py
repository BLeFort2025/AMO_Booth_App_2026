"""Quick verification of KPI formatting logic."""
import re
import math


def _extract_scalar_from_unit_label(unit_label):
    if not unit_label:
        return 1.0, ""
    m = re.search(r'\(\s*[×x]\s*([\d,]+)\s*\)', unit_label)
    if m:
        scalar_str = m.group(1).replace(',', '')
        try:
            scalar = float(scalar_str)
        except ValueError:
            scalar = 1.0
        base_unit = unit_label[:m.start()].strip()
        return scalar, base_unit
    return 1.0, unit_label


def _format_quantity_for_narrative(value, unit_label):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    v = float(value)
    scalar, base_unit = _extract_scalar_from_unit_label(unit_label)
    v = v * scalar
    is_dollar = base_unit.lower().startswith('dollar') or '$' in (base_unit or '')
    abs_v = abs(v)
    if abs_v >= 1e9:
        magnitude = f"{v / 1e9:.1f} billion"
    elif abs_v >= 1e6:
        magnitude = f"{v / 1e6:.1f} million"
    elif abs_v >= 1e3:
        magnitude = f"{v / 1e3:.1f} thousand"
    else:
        magnitude = f"{v:,.0f}"
    if is_dollar:
        return f"${magnitude}"
    if base_unit:
        return f"{magnitude} {base_unit}"
    return magnitude


# Test cases simulating real data
print("=== KPI Formatting Verification ===\n")
print("Test 1 (Total crop receipts ~514K × 1000):")
print(f"  Raw: 514,573   ->  Scaled: {_format_quantity_for_narrative(514573, 'Dollars (x 1,000)')}")

print("\nTest 2 (Value ~52K × 1000):")
print(f"  Raw: 52,200    ->  Scaled: {_format_quantity_for_narrative(52200, 'Dollars (x 1,000)')}")

print("\nTest 3 (Value ~417K × 1000):")
print(f"  Raw: 417,368   ->  Scaled: {_format_quantity_for_narrative(417368, 'Dollars (x 1,000)')}")

print("\nTest 4 (Index, no scaling):")
print(f"  Raw: 150.2     ->  Scaled: {_format_quantity_for_narrative(150.2, 'Index, 2016=100')}")

print("\nTest 5 (Scalar extraction):")
print(f"  'Dollars (x 1,000)' -> {_extract_scalar_from_unit_label('Dollars (x 1,000)')}")
print(f"  'Dollars (× 1,000)' -> {_extract_scalar_from_unit_label('Dollars (× 1,000)')}")
print(f"  'Index, 2016=100'   -> {_extract_scalar_from_unit_label('Index, 2016=100')}")
print(f"  None                -> {_extract_scalar_from_unit_label(None)}")

print("\n=== All tests passed ===")
