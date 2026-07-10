import pandas as pd
import numpy as np
from pathlib import Path
from dataclasses import dataclass
import sys

# --- CONFIGURATION ---
DATA_DIR = Path("data/latest")

# StatCan File Names
FILE_RECEIPTS = DATA_DIR / "32-10-0045-01.csv"
FILE_EXPENSES = DATA_DIR / "32-10-0049-01.csv"
FILE_NET_INCOME = DATA_DIR / "32-10-0052-01.csv"
FILE_MARKET   = DATA_DIR / "market_signals.csv"

@dataclass
class ForecastScenario:
    # Revenue Shocks
    grain_price_shock_pct: float = 0.0
    basis_shock_pct: float = 0.0
    livestock_price_shock_pct: float = 0.0
    yield_shock_pct: float = 0.0
    
    # Expense Shocks
    general_inflation_pct: float = 0.0
    wage_inflation_pct: float = 0.0     
    oil_price_shock_pct: float = 0.0    
    natgas_price_shock_pct: float = 0.0 
    interest_rate_shock_bps: int = 0

class FarmIncomeEngine:
    def __init__(self, region: str = "Canada"):
        self.region = region
        
        # SELF-HEALING: Check and fetch data if missing (Critical for Cloud)
        self._ensure_data_exists()
        
        self.history = self._load_and_process_history()
        self.market_signals = self._load_market_signals()
        
        # Calculate Trend Baseline (Linear Projection to 2025)
        self.baseline = self._calculate_trend_baseline(target_year=2025)

    def _ensure_data_exists(self):
        """
        Checks if required CSVs exist. If not, attempts to fetch and 
        FORCE SAVE them to the DATA_DIR path to ensure consistency.
        """
        # Ensure the directory exists first
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        missing_statcan = []
        if not FILE_RECEIPTS.exists(): missing_statcan.append("32-10-0045-01")
        if not FILE_EXPENSES.exists(): missing_statcan.append("32-10-0049-01")
        if not FILE_NET_INCOME.exists(): missing_statcan.append("32-10-0052-01")
        
        if missing_statcan:
            print(f"⚠️ Missing StatCan data: {missing_statcan}. Attempting fetch...")
            try:
                from scripts.fetch_statcan import fetch_table
                for tid in missing_statcan:
                    print(f"   Fetching {tid}...")
                    # Capture the dataframe directly
                    df, _ = fetch_table(tid)
                    
                    # FORCE SAVE to the exact path this engine expects
                    target_path = DATA_DIR / f"{tid}.csv"
                    df.to_csv(target_path, index=False)
                    print(f"   ✅ Force saved {tid} to {target_path}")
                    
            except ImportError:
                print("❌ Could not import fetch_table. Ensure scripts/fetch_statcan.py exists.")
            except Exception as e:
                print(f"❌ Error fetching StatCan data: {e}")

        if not FILE_MARKET.exists():
            print("⚠️ Missing Market Signals. Attempting fetch...")
            try:
                from scripts.fetch_market_signals import fetch_signals
                fetch_signals()
                # fetch_market_signals already saves to the correct path defined in its own script,
                # but we trigger it here just in case.
            except ImportError:
                print("❌ Could not import fetch_signals.")
            except Exception as e:
                print(f"❌ Error fetching market signals: {e}")

    def _get_col_name(self, df, candidates):
        """Helper to find a column name from a list of candidates."""
        for candidate in candidates:
            if candidate in df.columns: return candidate
        for col in df.columns:
            if col.strip().lower() in [c.lower() for c in candidates]: return col
        return None

    def _load_and_process_history(self):
        """Loads Receipts, Decomposed Expenses, and Net Income components."""
        # --- 1. Load Receipts ---
        if not FILE_RECEIPTS.exists(): raise FileNotFoundError(f"Missing file: {FILE_RECEIPTS}")
        df_rev = pd.read_csv(FILE_RECEIPTS)
        
        geo_col = self._get_col_name(df_rev, ['GEO', 'Geography', 'Region'])
        item_col = self._get_col_name(df_rev, ['Type of cash receipts', 'Commodity', 'Item'])
        val_col = self._get_col_name(df_rev, ['VALUE', 'Value'])
        date_col = self._get_col_name(df_rev, ['REF_DATE', 'Year'])

        target_items = {
            "Total crop receipts": "Crop_Receipts",
            "Total livestock and livestock product receipts": "Livestock_Receipts",
            "Total direct payments": "Program_Payments"
        }
        
        mask = (df_rev[geo_col] == self.region) & (df_rev[item_col].isin(target_items.keys()))
        df_pivot = df_rev[mask].pivot_table(index=date_col, columns=item_col, values=val_col, aggfunc='sum').reset_index().rename(columns={date_col: 'Year'})
        df_pivot = df_pivot.rename(columns={k:v for k,v in target_items.items()})
        for col in target_items.values():
            if col not in df_pivot.columns: df_pivot[col] = 0.0

        # --- 2. Load Expenses ---
        if not FILE_EXPENSES.exists():
             # Fallback
             df_pivot['Total_Expenses'] = (df_pivot['Crop_Receipts'] + df_pivot['Livestock_Receipts']) * 0.75
             df_pivot['Fuel_Expenses'] = df_pivot['Total_Expenses'] * 0.05
             df_pivot['Fertilizer_Expenses'] = df_pivot['Total_Expenses'] * 0.12
             df_pivot['Labor_Expenses'] = df_pivot['Total_Expenses'] * 0.15 
        else:
            df_exp = pd.read_csv(FILE_EXPENSES)
            geo_col_ex = self._get_col_name(df_exp, ['GEO', 'Geography'])
            item_col_ex = self._get_col_name(df_exp, ['Expenses and rebates', 'Item'])
            val_col_ex = self._get_col_name(df_exp, ['VALUE', 'Value'])
            date_col_ex = self._get_col_name(df_exp, ['REF_DATE', 'Year'])

            expense_map = {
                'Total operating expenses after rebates': 'Total_Expenses',
                'Machinery fuel, after rebates': 'Fuel_Machinery',
                'Heating fuel, after rebates': 'Fuel_Heating',
                'Fertilizer and lime, after rebates': 'Fertilizer_Expenses',
                'Cash wages including room and board, after rebates': 'Labor_Expenses'
            }
            mask_exp = (df_exp[geo_col_ex] == self.region) & (df_exp[item_col_ex].isin(expense_map.keys()))
            df_exp_pivot = df_exp[mask_exp].pivot_table(index=date_col_ex, columns=item_col_ex, values=val_col_ex, aggfunc='sum').reset_index().rename(columns={date_col_ex: 'Year'})
            df_exp_pivot = df_exp_pivot.rename(columns=expense_map)
            
            if 'Fuel_Machinery' not in df_exp_pivot.columns: df_exp_pivot['Fuel_Machinery'] = 0
            if 'Fuel_Heating' not in df_exp_pivot.columns: df_exp_pivot['Fuel_Heating'] = 0
            df_exp_pivot['Fuel_Expenses'] = df_exp_pivot['Fuel_Machinery'] + df_exp_pivot['Fuel_Heating']
            
            df_pivot = pd.merge(df_pivot, df_exp_pivot, on='Year', how='left')

        # --- 3. Load Net Income Components ---
        if FILE_NET_INCOME.exists():
            df_nfi = pd.read_csv(FILE_NET_INCOME)
            geo_col_nfi = self._get_col_name(df_nfi, ['GEO', 'Geography'])
            item_col_nfi = self._get_col_name(df_nfi, ['Income components', 'Item'])
            val_col_nfi = self._get_col_name(df_nfi, ['VALUE', 'Value'])
            date_col_nfi = self._get_col_name(df_nfi, ['REF_DATE', 'Year'])

            targets_nfi = {'Depreciation charges': 'Depreciation', 'Value of inventory change': 'Value_Inventory_Change'}
            df_subset = df_nfi[(df_nfi[geo_col_nfi] == self.region) & (df_nfi[item_col_nfi].isin(targets_nfi.keys()))].copy()

            if not df_subset.empty:
                df_nfi_pivot = df_subset.pivot_table(index=date_col_nfi, columns=item_col_nfi, values=val_col_nfi, aggfunc='first').reset_index().rename(columns={date_col_nfi: 'Year'})
                df_nfi_pivot = df_nfi_pivot.rename(columns=targets_nfi)
                df_pivot = pd.merge(df_pivot, df_nfi_pivot, on='Year', how='left')

        # Cleanup & Scaling
        df_pivot = df_pivot.fillna(0)
        cols_to_scale = ['Crop_Receipts', 'Livestock_Receipts', 'Program_Payments', 
                         'Total_Expenses', 'Fuel_Expenses', 'Fertilizer_Expenses', 'Labor_Expenses',
                         'Depreciation', 'Value_Inventory_Change']
        for c in cols_to_scale:
            if c in df_pivot.columns: df_pivot[c] = df_pivot[c] * 1000
            else: df_pivot[c] = 0.0

        # Labor Fallback check
        if 'Labor_Expenses' not in df_pivot.columns: df_pivot['Labor_Expenses'] = 0.0
        mask_lab_missing = (df_pivot['Labor_Expenses'] == 0) & (df_pivot['Total_Expenses'] > 0)
        df_pivot.loc[mask_lab_missing, 'Labor_Expenses'] = df_pivot.loc[mask_lab_missing, 'Total_Expenses'] * 0.15

        # Derived General Expenses
        df_pivot['General_Expenses'] = (
            df_pivot['Total_Expenses'] - 
            df_pivot['Fuel_Expenses'] - 
            df_pivot['Fertilizer_Expenses'] - 
            df_pivot['Labor_Expenses']
        ).clip(lower=0)

        # Dep Fallback (Calibrated 13.5% Rule)
        mask_dep_missing = (df_pivot['Depreciation'] == 0) & (df_pivot['Total_Expenses'] > 0)
        df_pivot.loc[mask_dep_missing, 'Depreciation'] = df_pivot.loc[mask_dep_missing, 'Total_Expenses'] * 0.135
            
        df_pivot['Total_Revenue'] = df_pivot['Crop_Receipts'] + df_pivot['Livestock_Receipts'] + df_pivot['Program_Payments']
        df_pivot['Net_Cash_Income'] = df_pivot['Total_Revenue'] - df_pivot['Total_Expenses']
        df_pivot['Realized_Net_Income'] = df_pivot['Net_Cash_Income'] - df_pivot['Depreciation']
        df_pivot['Total_Net_Income'] = df_pivot['Realized_Net_Income'] + df_pivot['Value_Inventory_Change']
        
        return df_pivot.sort_values('Year')

    def _calculate_trend_baseline(self, target_year=2025):
        """Projects a Linear Trend (2015-LastActual) forward to the Target Year."""
        cols = ['Crop_Receipts', 'Livestock_Receipts', 'Program_Payments', 
                'Total_Expenses', 'Fuel_Expenses', 'Fertilizer_Expenses', 'Labor_Expenses', 'General_Expenses', 
                'Depreciation']
        
        if self.history.empty or len(self.history) < 2:
            return self.history.iloc[-1] if not self.history.empty else pd.Series({k:0 for k in cols})

        df_trend = self.history[self.history['Year'] >= 2015].copy()
        if len(df_trend) < 3: df_trend = self.history.copy()
        
        x = df_trend['Year'].values
        baseline = {}
        
        for col in cols:
            y = df_trend[col].values
            try:
                slope, intercept = np.polyfit(x, y, 1)
                projected_val = slope * target_year + intercept
                baseline[col] = max(0, projected_val)
            except:
                baseline[col] = y.mean()
                
        # VIC: Use 5 year average (Mean Reverting)
        baseline['Value_Inventory_Change'] = df_trend['Value_Inventory_Change'].tail(5).mean()
        
        # Re-calc Totals
        baseline['Total_Expenses'] = baseline['Fuel_Expenses'] + baseline['Fertilizer_Expenses'] + baseline['Labor_Expenses'] + baseline['General_Expenses']
        baseline['Total_Revenue'] = baseline['Crop_Receipts'] + baseline['Livestock_Receipts'] + baseline['Program_Payments']
        baseline['Net_Cash_Income'] = baseline['Total_Revenue'] - baseline['Total_Expenses']
        baseline['Realized_Net_Income'] = baseline['Net_Cash_Income'] - baseline['Depreciation']
        baseline['Total_Net_Income'] = baseline['Realized_Net_Income'] + baseline['Value_Inventory_Change']
        
        return pd.Series(baseline)

    def _load_market_signals(self):
        if not FILE_MARKET.exists(): return None
        try: return pd.read_csv(FILE_MARKET).set_index('ticker')
        except: return None

    def forecast(self, scenario: ForecastScenario, n_sims=1000):
        # --- 1. Deterministic Logic ---
        eff_grain_price = scenario.grain_price_shock_pct + scenario.basis_shock_pct
        if eff_grain_price == 0 and scenario.yield_shock_pct < 0:
            eff_grain_price = abs(scenario.yield_shock_pct) * 0.5 

        adj_crops = self.baseline['Crop_Receipts'] * (1 + eff_grain_price) * (1 + scenario.yield_shock_pct)
        adj_livestock = self.baseline['Livestock_Receipts'] * (1 + scenario.livestock_price_shock_pct)
        
        interest_impact = (scenario.interest_rate_shock_bps / 100) * 0.015
        
        adj_fuel = self.baseline['Fuel_Expenses'] * (1 + (scenario.oil_price_shock_pct * 0.25) + interest_impact)
        adj_fert = self.baseline['Fertilizer_Expenses'] * (1 + (scenario.natgas_price_shock_pct * 0.40) + interest_impact)
        adj_labor = self.baseline['Labor_Expenses'] * (1 + scenario.wage_inflation_pct) 
        adj_general = self.baseline['General_Expenses'] * (1 + scenario.general_inflation_pct + interest_impact)
        
        adj_total_expenses = adj_fuel + adj_fert + adj_labor + adj_general
        adj_depreciation = self.baseline['Depreciation'] * (1 + scenario.general_inflation_pct)

        adj_program_base = self.baseline['Program_Payments']
        initial_nci = (adj_crops + adj_livestock + adj_program_base) - adj_total_expenses
        margin_shortfall = self.baseline['Net_Cash_Income'] - initial_nci
        if margin_shortfall > 0: adj_program = adj_program_base + (margin_shortfall * 0.40)
        else: adj_program = adj_program_base

        det_nci = (adj_crops + adj_livestock + adj_program) - adj_total_expenses
        det_rni = det_nci - adj_depreciation
        
        excess_yield_pct = max(0, scenario.yield_shock_pct)
        det_vic = self.baseline['Crop_Receipts'] * excess_yield_pct * 0.50
        det_tni = det_rni + det_vic
        
        # --- 2. Probabilistic Logic ---
        np.random.seed(42)
        vol_crops, vol_live = 0.18, 0.08
        if self.market_signals is not None and not self.market_signals.empty:
            if 'ZC=F' in self.market_signals.index: vol_crops = self.market_signals.loc['ZC=F', 'volatility']
            if 'LE=F' in self.market_signals.index: vol_live = self.market_signals.loc['LE=F', 'volatility']
        
        sim_crops = adj_crops * np.random.lognormal(0, vol_crops, n_sims)
        sim_live = adj_livestock * np.random.lognormal(0, vol_live, n_sims)
        sim_exp = adj_total_expenses * np.random.normal(1, 0.05, n_sims)
        
        sim_nci = (sim_crops + sim_live + adj_program) - sim_exp
        sim_rni = sim_nci - adj_depreciation 
        sim_tni = sim_rni + det_vic 
        
        return {
            "p05": np.percentile(sim_nci, 5),
            "p50": np.percentile(sim_nci, 50),
            "p95": np.percentile(sim_nci, 95),
            "det_crops": adj_crops,
            "det_livestock": adj_livestock,
            "det_program": adj_program,
            "det_expenses": adj_total_expenses,
            "det_depreciation": adj_depreciation,
            "det_vic": det_vic, 
            "sim_nci_median": np.percentile(sim_nci, 50),
            "sim_rni_median": np.percentile(sim_rni, 50),
            "sim_tni_median": np.percentile(sim_tni, 50),
            "breakdown_fuel": adj_fuel,
            "breakdown_fert": adj_fert,
            "breakdown_labor": adj_labor,
            "breakdown_gen": adj_general
        }