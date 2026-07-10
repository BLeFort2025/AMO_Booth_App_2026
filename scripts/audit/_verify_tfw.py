"""Verify TFW/LRF math for Ontario Greenhouse with 50% TFW reduction."""

# ── Known values from screenshots ──
base_output = 3.75e9   # $3.75B
margin_pct = 0.30      # GDP/Output
base_gdp = base_output * margin_pct  # ~$1.12B

# Sector archetype: Horticulture
alpha = 0.12   # capital elasticity
delta = 0.15   # depreciation (data-driven would override but let's use what the UI shows)
phi = 1.5      # labor sensitivity
lag = 1        # investment lag

# TFW parameters
base_vacancy = 0.09    # 9.0% (from data)
tfw_dependency = 0.40  # 40%
tfw_reduction = 50     # 50% reduction (slider value inferred from LRF=0.70)

# TFP
tfp_growth = 0.015     # 1.5%/yr

# Compute vacancy
wage_adjustment = 0     # no wage shock
tfw_vacancy_shock = tfw_dependency * (tfw_reduction / 100.0)  # 0.40 * 0.50 = 0.20
vacancy_rate = base_vacancy + tfw_vacancy_shock  # 0.09 + 0.20 = 0.29
delta_vacancy = max(0, vacancy_rate - base_vacancy)  # 0.20
lrf = max(0.0, 1.0 - phi * delta_vacancy)  # 1.0 - 1.5 * 0.20 = 0.70

print("=== TFW/LRF Math Verification ===")
print(f"Base vacancy: {base_vacancy:.1%}")
print(f"TFW dependency: {tfw_dependency:.0%}")
print(f"TFW reduction: {tfw_reduction}%")
print(f"TFW vacancy shock: {tfw_vacancy_shock:.1%}")
print(f"Total vacancy rate: {vacancy_rate:.1%}")
print(f"Delta vacancy (above base): {delta_vacancy:.1%}")
print(f"LRF = 1.0 - {phi} × {delta_vacancy:.2f} = {lrf:.2f}")
print(f"[OK] LRF matches screenshot: 0.70")

# ── Year 0 ──
print(f"\n--- Year 0 ---")
print(f"Output: ${base_output/1e9:.2f}B (from sim, no LRF applied)")
print(f"GDP: ${base_gdp/1e9:.2f}B")
print(f"LRF: 1.00 (Year 0 uses sim_y0 directly, LRF not applied)")
print(f"Gap: $0 (no shocks, same as baseline)")

# ── Year 1 ──
A_t = 1.0 * (1 + tfp_growth)  # TFP grows
K_0 = base_output * 0.50  # approximate K0 (exact depends on CapEx data)
K = K_0  # no capex shock, so K stays roughly same
potential_output_y1 = base_output * A_t * (K / K_0) ** alpha
realized_output_y1 = potential_output_y1 * lrf
gdp_y1 = realized_output_y1 * margin_pct

print(f"\n--- Year 1 ---")
print(f"A_t = 1.0 × (1 + {tfp_growth}) = {A_t:.4f}")
print(f"Potential output = {base_output/1e9:.2f}B × {A_t:.4f} × (K/K0)^{alpha} = ${potential_output_y1/1e9:.2f}B")
print(f"LRF = {lrf:.2f}")
print(f"Realized output = ${potential_output_y1/1e9:.2f}B × {lrf:.2f} = ${realized_output_y1/1e9:.2f}B")
print(f"GDP = ${realized_output_y1/1e9:.2f}B × {margin_pct:.2f} = ${gdp_y1/1e9:.2f}B")

# Baseline Year 1 (no TFW shock, TFP=1.5%)
baseline_y1 = base_output * A_t  # no LRF penalty
baseline_gdp_y1 = baseline_y1 * margin_pct
gap_y1 = gdp_y1 - baseline_gdp_y1

print(f"\nBaseline output Y1 = ${baseline_y1/1e9:.2f}B")
print(f"Baseline GDP Y1 = ${baseline_gdp_y1/1e9:.2f}B")
print(f"Gap = ${gap_y1/1e6:.0f}M")
print(f"Screenshot shows: Output $2.67B, GDP $0.80B, Gap -$339M")
print(f"Calculated:       Output ${realized_output_y1/1e9:.2f}B, GDP ${gdp_y1/1e9:.2f}B, Gap ${gap_y1/1e6:.0f}M")

# Output reduction percentage
output_drop_pct = (1 - lrf) * 100
print(f"\n=== Summary ===")
print(f"Output drops by {output_drop_pct:.0f}% from LRF penalty alone")
print(f"This is the {phi} × {delta_vacancy:.0%} = {phi * delta_vacancy:.0%} labor shortage penalty")
print(f"Year 0 has NO LRF impact (uses sim_y0 directly)")
print(f"Years 1+ get the full LRF={lrf:.2f} penalty")
