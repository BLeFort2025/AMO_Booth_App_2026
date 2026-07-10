import pandas as pd
import yaml
from pathlib import Path

class EconomicAnalyzer:
    def __init__(self, io_data_df, baskets_config_path):
        """
        io_data_df: DataFrame containing columns ['code', 'gross_output', 'jobs', 'multiplier_output']
        baskets_config_path: Path to io_baskets.yml
        """
        self.io_data = io_data_df
        # Ensure codes are strings for matching
        if 'code' in self.io_data.columns:
            self.io_data['code'] = self.io_data['code'].astype(str)
            
        with open(baskets_config_path, 'r') as file:
            self.config = yaml.safe_load(file)
            
    def _filter_data_for_basket(self, basket_info):
        """
        Handles the complex 'match' logic (prefixes + exacts - excludes)
        found in the existing io_baskets.yml
        """
        df = self.io_data.copy()
        
        # 1. Matches
        match_rules = basket_info.get('match', {})
        prefixes = tuple(match_rules.get('any_code_prefix', []))
        exacts = match_rules.get('any_code_exact', [])
        
        # Create mask for inclusion
        # Starts with tuple of prefixes OR is in exact list
        mask = df['code'].isin(exacts)
        if prefixes:
            mask = mask | df['code'].str.startswith(prefixes)
            
        # 2. Excludes
        exclude_rules = basket_info.get('exclude', {})
        ex_prefixes = tuple(exclude_rules.get('any_code_prefix', []))
        ex_exacts = exclude_rules.get('any_code_exact', [])
        
        if ex_exacts:
            mask = mask & ~df['code'].isin(ex_exacts)
        if ex_prefixes:
            mask = mask & ~df['code'].str.startswith(ex_prefixes)
            
        return df[mask]

    def _get_sector_weight(self, basket_key, basket_info):
        """
        Determines what % of the sector to include.
        Prioritizes dynamic 'calculated_share' from update_baskets.py
        """
        weight_type = basket_info.get('weight_type', 'full')
        
        if weight_type == "full":
            return 1.0
        elif weight_type == "weighted":
            if 'calculated_share' in basket_info:
                return float(basket_info['calculated_share'])
            return 0.15  # Fallback
        return 1.0

    def calculate_contribution(self):
        """
        MODE A: CONTRIBUTION (The Sector Footprint)
        """
        total_direct_output = 0
        total_direct_jobs = 0
        breakdown = []

        # Iterate through 'baskets' (Note: changed from 'sectors' to match your file)
        baskets = self.config.get('baskets', {})
        
        for basket_key, basket_info in baskets.items():
            
            # Get the weight
            weight = self._get_sector_weight(basket_key, basket_info)
            
            # Filter data using the robust matching logic
            sector_data = self._filter_data_for_basket(basket_info)
            
            # Calculate values
            basket_output = 0
            for index, row in sector_data.iterrows():
                val = row.get('gross_output', 0) * weight
                jobs = row.get('jobs', 0) * weight
                
                basket_output += val
                total_direct_output += val
                total_direct_jobs += jobs

            breakdown.append({
                "Sector": basket_info['label'],
                "Direct Output": basket_output,
                "Weight Used": f"{weight:.1%}",
                "Type": basket_info.get('weight_type', 'full')
            })

        return {
            "mode": "Contribution",
            "narrative": "Total size of the Cluster (Direct)",
            "total_direct_output": total_direct_output,
            "total_direct_jobs": total_direct_jobs,
            "breakdown": breakdown
        }

    def calculate_impact(self, shock_basket_key, shock_amount_millions):
        """
        MODE B: IMPACT (The Shock)
        """
        baskets = self.config.get('baskets', {})
        if shock_basket_key not in baskets:
            return {"error": "Sector not found"}
            
        basket_info = baskets[shock_basket_key]
        
        # Get data subset
        subset = self._filter_data_for_basket(basket_info)
        
        if subset.empty:
            avg_multiplier = 1.0
        else:
            avg_multiplier = subset['multiplier_output'].mean()
        
        direct = shock_amount_millions
        total = direct * avg_multiplier
        indirect = total - direct
        
        return {
            "mode": "Impact",
            "narrative": f"Impact of ${shock_amount_millions}M investment in {basket_info['label']}",
            "shock_amount": direct,
            "indirect_impact": indirect,
            "total_impact": total,
            "multiplier_used": avg_multiplier
        }