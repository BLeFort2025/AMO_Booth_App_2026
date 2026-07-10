"""
Offline trace of the projection engine with Ontario data.
This replicates the exact math to diagnose the capital stock decline.
"""
import sys
sys.stdout = open("_trace_output.txt", "w", encoding="utf-8")
import pandas as pd
import json

# Load real data
capex = pd.read_csv("data/derived/basket_capex.csv")
fin = pd.read_csv("data/derived/farm_financial_health.csv")
with open("data/derived/farm_expense_profiles.json") as f:
    profiles = json.load(f)

# Ontario financial health
ont = fin[fin["geo"] == "Ontario"].iloc[0]
print("=== Ontario Financial Health ===")
for col in fin.columns:
    print(f"  {col}: {ont[col]}")

# CapEx data (national — primary_agriculture)
capex_row = capex[capex["basket_key"] == "primary_agriculture"].iloc[0]
print(f"\n=== CapEx Baseline ===")
print(f"  Total CapEx: ${capex_row['total_capex']:.1f}M")

# Sector params (Mixed/All)
alpha = 0.18
delta = 0.12
phi = 0.30
lag = 2

# Projection inputs
base_output = 21_130_000_000  # $21.13B (from sim)
gdp_coeff = 0.368

# Capital stock initialization
base_investment = capex_row["total_capex"] * 1_000_000  # $10,452.6M → dollars
K = base_investment / delta  # steady-state: K = I/delta
K_0 = K

print(f"\n=== Capital Initialization ===")
print(f"  K_0 = ${K/1e9:.2f}B")
print(f"  base_investment = ${base_investment/1e6:.1f}M")
print(f"  depreciation/yr = ${K * delta/1e6:.1f}M (K × δ)")
print(f"  Net = ${(base_investment - K * delta)/1e6:.1f}M (should be ~0)")

# Financial health integration
total_debt = ont["total_debt_M"] * 1_000_000
nci = ont["net_cash_income_M"] * 1_000_000
coverage = ont["interest_coverage"]
interest_expense = nci / coverage if coverage > 0 else total_debt * 0.05
implied_rate = interest_expense / total_debt if total_debt > 0 else 0.05
implied_rate = max(0.02, min(0.10, implied_rate))

print(f"\n=== Debt & Interest ===")
print(f"  Total Debt (Ontario): ${total_debt/1e9:.2f}B")
print(f"  Net Cash Income: ${nci/1e9:.2f}B")
print(f"  Interest Coverage (StatCan): {coverage:.3f}x")
print(f"  Implied interest expense: ${interest_expense/1e9:.2f}B")
print(f"  Implied interest rate: {implied_rate:.3%}")

# Debt ratio for Ontario
debt_ratio = 0.15  # from slider (Ontario default)
shocked_rate = implied_rate  # no shock

# 5-year projection (no shocks)
output_t = base_output  # no shock → final_output = base_output
A_t = 1.0
investment_history = [base_investment] * (lag + 1)
annual_cost_shock = 0.0
tfp_g = 0.015  # 1.5%

print(f"\n=== Year-by-Year Trace (No Shocks) ===")
print(f"{'Year':<6} {'Output($B)':<12} {'GDP($B)':<10} {'DSCR':<8} {'FSF':<8} {'Investment($M)':<16} {'K($B)':<10} {'K_chg%':<8}")
print(f"{'0':<6} {output_t/1e9:<12.2f} {output_t*gdp_coeff/1e9:<10.2f} {'1.50':<8} {'1.00':<8} {base_investment/1e6:<16.1f} {K/1e9:<10.2f} {'0.0%':<8}")

for t in range(1, 6):
    # DSCR
    ebitda = output_t * gdp_coeff - annual_cost_shock
    annual_principal = total_debt * 0.10
    debt_service = (total_debt * shocked_rate) + annual_principal
    dscr = ebitda / debt_service if debt_service > 0 else 9.99
    
    # FSF
    if dscr > 1.25:
        fsf = 1.0
    elif dscr > 1.0:
        fsf = 1.0 - 0.20 * (1.25 - dscr)
    else:
        fsf = max(0.0, 1.0 - 0.80 * (1.0 - dscr) - 0.05)
    
    # Investment
    investment_t = base_investment * fsf
    investment_history.append(investment_t)
    
    # Capital accumulation (with lag)
    lagged_investment = investment_history[max(0, len(investment_history) - 1 - lag)]
    K = K * (1 - delta) + lagged_investment
    
    # TFP
    A_t *= (1 + tfp_g)
    
    # Output
    potential_output = base_output * A_t * (K / K_0) ** alpha
    output_t = potential_output  # no LRF effect (no vacancy shock)
    
    # GDP
    gdp_t = output_t * gdp_coeff - annual_cost_shock
    
    k_chg = (K - K_0) / K_0 * 100
    
    print(f"{t:<6} {output_t/1e9:<12.2f} {gdp_t/1e9:<10.2f} {dscr:<8.3f} {fsf:<8.4f} {investment_t/1e6:<16.1f} {K/1e9:<10.2f} {k_chg:<+8.2f}%")

print(f"\n=== Key Diagnostic ===")
print(f"  EBITDA: ${ebitda/1e9:.2f}B")
print(f"  Debt Service: ${debt_service/1e9:.2f}B")
print(f"    - Interest: ${total_debt * shocked_rate/1e9:.2f}B (rate={shocked_rate:.3%})")
print(f"    - Principal: ${annual_principal/1e9:.2f}B (10% of debt)")
print(f"  DSCR < 1.25? → FSF < 1.0 → investment throttled → K declines")
