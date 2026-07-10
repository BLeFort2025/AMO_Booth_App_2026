import sys
from pathlib import Path

# --- PROJECT SETUP ---
current_file = Path(__file__).resolve()
project_root = current_file.parents[2]          # app/pages/ → app/ → project root
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.smart_read import smart_read
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

try:
    from scripts.forecasting_engine import FarmIncomeEngine, ForecastScenario
except ImportError:
    st.error("⚠️ Engine not found. Please ensure 'scripts/forecasting_engine.py' exists.")
    st.stop()

# -----------------------------------------------------------------------------
# 1. PAGE CONFIG
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Cdn Farm Income Forecaster", page_icon="🚜", layout="wide")

from app.utils import inject_standalone_mode, show_data_freshness
inject_standalone_mode()
show_data_freshness(
    table_ids=["32-10-0045-01", "32-10-0049-01", "32-10-0052-01"],
    source_labels={
        "32-10-0045-01": "Cash Receipts",
        "32-10-0049-01": "Operating Expenses",
        "32-10-0052-01": "Net Income",
    },
)


st.markdown("""
<style>
    .metric-card { background-color: #f0f2f6; padding: 20px; border-radius: 10px; border-left: 5px solid #2e7d32; }
    .stMetric { text-align: center; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. SIDEBAR
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Scenario Builder")
    selected_region = st.selectbox("Select Region", ["Canada", "Ontario", "Alberta", "Saskatchewan", "Quebec", "Manitoba", "British Columbia"])
    
    st.divider()
    
    # REVENUE
    st.subheader("🌾 Revenue Drivers")
    grain_price = st.slider("Grain Price Outlook (%)", -0.30, 0.50, 0.0, 0.01)
    basis_shock = st.slider("Basis / Transport (%)", -0.20, 0.10, 0.0, 0.01)
    yield_shock = st.slider("Yield Outlook (%)", -0.40, 0.20, 0.0, 0.05)
    cattle_price = st.slider("Livestock Price Outlook (%)", -0.30, 0.50, 0.0, 0.01)
    
    st.divider()
    
    # SMART EXPENSES
    st.subheader("🛢️ Smart Expense Model")
    try:
        signals = smart_read(Path("data/latest/market_signals.csv")).set_index('ticker')
        oil_price = signals.loc['CL=F', 'current_price'] if 'CL=F' in signals.index else 0
        gas_price = signals.loc['NG=F', 'current_price'] if 'NG=F' in signals.index else 0
        col_s1, col_s2 = st.columns(2)
        col_s1.metric("Crude Oil", f"${oil_price:.2f}")
        col_s2.metric("Nat Gas", f"${gas_price:.2f}")
    except:
        st.caption("Live signals unavailable.")

    oil_shock = st.slider("Oil Price Outlook (%)", -0.50, 0.50, 0.0, 0.05, help="Drives Fuel")
    natgas_shock = st.slider("NatGas Price Outlook (%)", -0.50, 0.50, 0.0, 0.05, help="Drives Fertilizer")
    gen_inflation = st.slider("General Inflation (%)", -0.05, 0.20, 0.02, 0.01)
    
    # NEW: Labor
    wage_shock = st.slider("Wage Inflation (%)", 0.0, 0.15, 0.03, 0.01, help="Adjusts Labor/Salary costs.")
    
    interest_bps = st.slider("Interest Rate Shock (bps)", -200, 500, 0, 25)

# -----------------------------------------------------------------------------
# 3. EXECUTION
# -----------------------------------------------------------------------------
st.title(f"🚜 Farm Income Forecaster: {selected_region}")
st.markdown("### Strategic Planning Dashboard • Research Grade (V2.0)")
st.markdown("---")

try:
    engine = FarmIncomeEngine(region=selected_region)
except Exception as e:
    st.warning(f"Could not load data. Error: {e}")
    st.stop()

scenario = ForecastScenario(
    grain_price_shock_pct=grain_price,
    basis_shock_pct=basis_shock,
    livestock_price_shock_pct=cattle_price,
    yield_shock_pct=yield_shock,
    general_inflation_pct=gen_inflation,
    wage_inflation_pct=wage_shock, # NEW
    oil_price_shock_pct=oil_shock,
    natgas_price_shock_pct=natgas_shock,
    interest_rate_shock_bps=interest_bps
)

results = engine.forecast(scenario, n_sims=1000)
forecast_median = results['p50'] 
baseline_nci = engine.baseline['Net_Cash_Income']

# -----------------------------------------------------------------------------
# 4. KPI CARDS
# -----------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
delta_pct = ((forecast_median - baseline_nci) / baseline_nci) * 100 if baseline_nci != 0 else 0

with col1:
    st.metric("Baseline NCI (Trend)", f"${baseline_nci/1000:,.1f} B")
with col2:
    st.metric("2025 Forecast (Median)", f"${forecast_median/1000:,.1f} B", f"{delta_pct:+.1f}%")
with col3:
    st.metric("Bear Case (P5)", f"${results['p05']/1000:,.1f} B")
with col4:
    st.metric("Bull Case (P95)", f"${results['p95']/1000:,.1f} B")

# -----------------------------------------------------------------------------
# 5. CHARTS & TABLES
# -----------------------------------------------------------------------------

# --- Chart 1: The Cone ---
st.subheader("📈 Income Trajectory (Net Cash Income)")
hist_df = engine.history
x_hist = hist_df['Year'].tolist()
y_hist = hist_df['Net_Cash_Income'].tolist()

last_real_year = int(hist_df['Year'].max())
bridge_val = (y_hist[-1] + forecast_median) / 2
x_fore = [last_real_year, last_real_year + 1, last_real_year + 2]
y_fore = [y_hist[-1], bridge_val, forecast_median]

fig = go.Figure()
fig.add_trace(go.Scatter(x=x_hist, y=y_hist, mode='lines+markers', name='Historical Actuals', line=dict(color='#1f77b4', width=3)))
fig.add_trace(go.Scatter(x=x_fore, y=y_fore, mode='lines+markers', name='Forecast', line=dict(color='#ff7f0e', width=3, dash='dash')))

y_upper = [y_hist[-1], bridge_val + (results['p95']-forecast_median)*0.5, results['p95']]
y_lower = [y_hist[-1], bridge_val - (forecast_median-results['p05'])*0.5, results['p05']]
fig.add_trace(go.Scatter(x=x_fore+x_fore[::-1], y=y_upper+y_lower[::-1], fill='toself', fillcolor='rgba(255,127,14,0.2)', line=dict(width=0), name='95% Range'))

fig.update_layout(template="plotly_white", hovermode="x unified", height=400)
st.plotly_chart(fig, use_container_width=True)
st.caption("Historical Trend (2015-2023) projected linearly to 2025 Baseline.")

# --- Chart 2: Waterfall ---
col_L, col_R = st.columns([3, 2])

with col_L:
    st.subheader("📉 Drivers of Change (Waterfall)")
    
    d_crops = results['det_crops'] - engine.baseline['Crop_Receipts']
    d_live  = results['det_livestock'] - engine.baseline['Livestock_Receipts']
    d_prog  = results['det_program'] - engine.baseline['Program_Payments']
    d_exp   = results['det_expenses'] - engine.baseline['Total_Expenses']
    d_exp_step = -d_exp 
    
    measures = ["relative", "relative", "relative", "relative", "relative", "total"]
    x_lbls = ["Baseline", "Crops", "Livestock", "Programs", "Expenses", "Forecast"]
    y_vals = [baseline_nci, d_crops, d_live, d_prog, d_exp_step, forecast_median]
    
    text_vals = [f"{v/1000:+.1f}B" for v in y_vals]
    text_vals[0] = f"{baseline_nci/1000:.1f}B"
    text_vals[-1] = f"{forecast_median/1000:.1f}B"

    wf = go.Figure(go.Waterfall(
        name="2025 Bridge", orientation="v",
        measure=measures, x=x_lbls, y=y_vals, text=text_vals,
        textposition="outside", connector={"line":{"color":"rgb(63,63,63)"}},
        decreasing={"marker":{"color":"#d62728"}}, increasing={"marker":{"color":"#2ca02c"}}, totals={"marker":{"color":"#ff7f0e"}}
    ))
    wf.update_layout(template="plotly_white", height=400, title="From Baseline to Forecast")
    st.plotly_chart(wf, use_container_width=True)

with col_R:
    st.subheader("📋 The Economic Triad")
    st.caption("Liquidity • Profitability • Economic Value")
    
    items = [
        "Total Revenue", 
        "Fuel Expenses (Smart)", "Fertilizer Expenses (Smart)", 
        "Labor Expenses", "General Expenses", # Added Labor
        "Total Expenses", 
        "1. Net Cash Income (Liquidity)", 
        "Depreciation", 
        "2. Realized Net Income (Profitability)",
        "Value of Inventory Change (VIC)",
        "3. Total Net Income (Economic Value)"
    ]
    
    b = engine.baseline
    base_vals = [
        b['Total_Revenue'],
        b['Fuel_Expenses'], b['Fertilizer_Expenses'], 
        b['Labor_Expenses'], b['General_Expenses'],
        b['Total_Expenses'],
        b['Net_Cash_Income'],
        b['Depreciation'],
        b['Realized_Net_Income'],
        b['Value_Inventory_Change'],
        b['Total_Net_Income']
    ]
    
    r = results
    fore_vals = [
        (r['det_crops']+r['det_livestock']+r['det_program']),
        r['breakdown_fuel'], r['breakdown_fert'],
        r['breakdown_labor'], r['breakdown_gen'],
        r['det_expenses'],
        r['sim_nci_median'],
        r['det_depreciation'],
        r['sim_rni_median'],
        r['det_vic'],
        r['sim_tni_median']
    ]
    
    df_fin = pd.DataFrame({"Metric": items, "Baseline": base_vals, "Forecast": fore_vals})
    df_fin["Change ($)"] = df_fin["Forecast"] - df_fin["Baseline"]
    df_fin["Change (%)"] = df_fin.apply(
        lambda row: (row["Change ($)"] / row["Baseline"]) if row["Baseline"] != 0 else 0, axis=1
    )
    
    st.dataframe(df_fin.style.format({
        "Baseline": "${:,.0f}", "Forecast": "${:,.0f}", "Change ($)": "${:+,.0f}", "Change (%)": "{:+.1%}"
    }), hide_index=True, use_container_width=True)
    
    st.info("**Trend Note:** Baseline is a linear projection of 2015-2023 data, capturing long-term genetic yield gains.")

# -----------------------------------------------------------------------------
# 6. METHODOLOGY CARD (Phase 4D)
# -----------------------------------------------------------------------------
st.markdown("---")

with st.expander("📖 Methodology — How This Forecast Works", expanded=False):
    st.markdown("""
### Baseline Construction
The baseline is a **linear trend projection** of historical data from **2015–2023** (StatCan tables),
projected forward to the target year. Each income/expense component is trended independently:
- **Crop Receipts** → [32-10-0045-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3210004501)
- **Operating Expenses** → [32-10-0049-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3210004901)
- **Net Income** → [32-10-0052-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3210005201)

### Smart Expense Model
Expense shocks are **not flat multipliers** — they use commodity-specific pass-through rates:
| Input Shock | Primary Driver | Pass-Through |
|-------------|----------------|-------------|
| Oil Price   | Fuel Expenses  | 25% of oil Δ |
| NatGas Price| Fertilizer     | 40% of gas Δ |
| Wage Inflation | Labor/Salary | 100% direct |
| General Inflation | General Expenses | 100% direct |
| Interest Rate | All Expenses | 1.5% per 100bps |

### Monte Carlo Simulation
The forecast fan (P5–P95) is generated from **1,000 Monte Carlo simulations**:
- **Crop Revenue**: Log-normal distribution using historical corn futures volatility (~18%)
- **Livestock Revenue**: Log-normal distribution using live cattle futures volatility (~8%)
- **Expenses**: Normal distribution with 5% standard deviation
- Market volatilities update when `market_signals.csv` is available

### Program Payments (AgriStability Proxy)
If the deterministic Net Cash Income falls below baseline, program payments automatically
increase to cover **40%** of the margin shortfall — mimicking AgriStability-style support.
    """)

# -----------------------------------------------------------------------------
# 7. TABLE OF ASSUMPTIONS (Phase 4D)
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("📋 Assumptions & Impact Translation")

b = engine.baseline
r = results

# Build the assumptions table from current scenario settings
_assumptions = []

# Revenue shocks
_crop_delta = r['det_crops'] - b['Crop_Receipts']
_live_delta = r['det_livestock'] - b['Livestock_Receipts']

if grain_price != 0 or yield_shock != 0:
    _assumptions.append({
        "Parameter": "Grain Price + Yield",
        "Setting": f"{grain_price:+.0%} price, {yield_shock:+.0%} yield",
        "Baseline ($)": b['Crop_Receipts'],
        "Impact ($)": _crop_delta,
        "Impact (%)": _crop_delta / b['Crop_Receipts'] * 100 if b['Crop_Receipts'] != 0 else 0,
    })
if basis_shock != 0:
    _assumptions.append({
        "Parameter": "Basis / Transport",
        "Setting": f"{basis_shock:+.0%}",
        "Baseline ($)": b['Crop_Receipts'],
        "Impact ($)": b['Crop_Receipts'] * basis_shock,
        "Impact (%)": basis_shock * 100,
    })
if cattle_price != 0:
    _assumptions.append({
        "Parameter": "Livestock Price",
        "Setting": f"{cattle_price:+.0%}",
        "Baseline ($)": b['Livestock_Receipts'],
        "Impact ($)": _live_delta,
        "Impact (%)": cattle_price * 100,
    })

# Expense shocks
_expense_items = [
    ("Oil → Fuel", oil_shock, b['Fuel_Expenses'], r['breakdown_fuel']),
    ("NatGas → Fertilizer", natgas_shock, b['Fertilizer_Expenses'], r['breakdown_fert']),
    ("Wage Inflation → Labor", wage_shock, b['Labor_Expenses'], r['breakdown_labor']),
    ("General Inflation → Other", gen_inflation, b['General_Expenses'], r['breakdown_gen']),
]
for label, shock, baseline_val, forecast_val in _expense_items:
    if shock != 0:
        _assumptions.append({
            "Parameter": label,
            "Setting": f"{shock:+.0%}" if abs(shock) >= 0.01 else f"{shock:+.2%}",
            "Baseline ($)": baseline_val,
            "Impact ($)": forecast_val - baseline_val,
            "Impact (%)": (forecast_val - baseline_val) / baseline_val * 100 if baseline_val != 0 else 0,
        })

if interest_bps != 0:
    _int_impact = (r['det_expenses'] - b['Total_Expenses']) - sum(
        f - bl for _, _, bl, f in _expense_items
    )
    _assumptions.append({
        "Parameter": "Interest Rate",
        "Setting": f"{interest_bps:+d} bps",
        "Baseline ($)": b['Total_Expenses'],
        "Impact ($)": _int_impact,
        "Impact (%)": _int_impact / b['Total_Expenses'] * 100 if b['Total_Expenses'] != 0 else 0,
    })

if _assumptions:
    _assum_df = pd.DataFrame(_assumptions)
    st.dataframe(
        _assum_df.style.format({
            "Baseline ($)": "${:,.0f}",
            "Impact ($)": "${:+,.0f}",
            "Impact (%)": "{:+.1f}%",
        }),
        hide_index=True, use_container_width=True,
    )
    st.caption("Shows how each sidebar parameter translates into dollar impacts on the forecast.")
else:
    st.info("All scenario parameters are at default (zero shock). Adjust the sidebar sliders to see impact translations.")

# -----------------------------------------------------------------------------
# 8. KEY RISKS SUMMARY (Phase 4D)
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("⚠️ Key Risk Factors")

# Compute risk contributions
_spread = r['p95'] - r['p05']
_nci_delta = r['p50'] - b['Net_Cash_Income']

# Rank shock impacts by absolute magnitude
_risk_items = []
if _crop_delta != 0:
    _risk_items.append(("Crop Revenue", abs(_crop_delta), _crop_delta))
if _live_delta != 0:
    _risk_items.append(("Livestock Revenue", abs(_live_delta), _live_delta))

for label, shock, baseline_val, forecast_val in _expense_items:
    delta = forecast_val - baseline_val
    if delta != 0:
        _risk_items.append((label, abs(delta), -delta))  # negative because expense increases reduce NCI

_risk_items.sort(key=lambda x: x[1], reverse=True)
_total_abs_impact = sum(x[1] for x in _risk_items)

if _risk_items:
    # Top risk callout
    _top_risk = _risk_items[0]
    _top_pct = _top_risk[1] / _total_abs_impact * 100 if _total_abs_impact > 0 else 0
    _direction = "upside" if _top_risk[2] > 0 else "downside"

    st.warning(
        f"**🔴 #{1} Risk Factor: {_top_risk[0]}** — accounts for "
        f"**{_top_pct:.0f}%** of total forecast movement "
        f"(**${_top_risk[1]/1e6:,.1f}M** {_direction})"
    )

    # Risk breakdown table
    _risk_df = pd.DataFrame([
        {
            "Rank": f"#{i+1}",
            "Factor": name,
            "Absolute Impact": abs_val,
            "Share of Total": abs_val / _total_abs_impact * 100 if _total_abs_impact > 0 else 0,
            "Direction": "▲ Upside" if signed > 0 else "▼ Downside",
        }
        for i, (name, abs_val, signed) in enumerate(_risk_items)
    ])
    st.dataframe(
        _risk_df.style.format({
            "Absolute Impact": "${:,.0f}",
            "Share of Total": "{:.1f}%",
        }),
        hide_index=True, use_container_width=True,
    )

    # Uncertainty spread
    col_u1, col_u2, col_u3 = st.columns(3)
    col_u1.metric("Forecast Spread (P95 − P5)", f"${_spread/1e6:,.1f}M",
                   help="Width of the 90% confidence interval from Monte Carlo")
    col_u2.metric("Net Change from Baseline", f"${_nci_delta/1e6:+,.1f}M",
                   delta=f"{_nci_delta / b['Net_Cash_Income'] * 100:+.1f}%" if b['Net_Cash_Income'] != 0 else "N/A",
                   delta_color="normal" if _nci_delta >= 0 else "inverse")
    col_u3.metric("Scenarios Run", "1,000",
                   help="Number of Monte Carlo simulations used to generate the P5–P95 range")
else:
    st.info("No active shocks — all parameters are at baseline. Adjust the sidebar sliders to see risk analysis.")
from app.utils import global_footer
global_footer()
