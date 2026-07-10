"""
Ontario Farm Cost Impact Model v2
===================================
Rebuilt using OMAFRA Publication 60 (2025 Field Crop Budgets) per-acre costs
as the 2025 baseline. Scenario 1: 500 acres grain corn (no-till).

All 2025 baseline numbers are directly from Pub 60, page 12.
2026 estimates use validated escalation factors from World Bank / DTN / Ridgetown.
"""

import json
import os

# ============================================================
# OMAFRA PUB 60 - 2025 FIELD CROP BUDGET: GRAIN CORN (NO-TILL)
# Source: Publication 60: Field Crop Budgets, 2025, page 12
# Projected yield: 4.90 tonnes/acre (193 bu/acre)
# ============================================================

OMAFRA_2025 = {
    "source": "OMAFRA Publication 60: Field Crop Budgets, 2025 (p.12, No-Till column)",
    "yield_tonnes_per_acre": 4.90,
    "yield_bu_per_acre": 193,

    # Fertility — per acre
    "n_fertilizer_per_acre": 147.35,      # 171 kg/ha N as 611 kg/ha UAN 28-0-0
    "p2o5_fertilizer_per_acre": 75.95,    # 89 kg/ha P₂O₅ (crop removal: 7.25 kg/t)
    "k2o_fertilizer_per_acre": 28.45,     # 60 kg/ha K₂O (crop removal: 4.9 kg/t)

    # Fuel + lubricant — per acre
    "fuel_and_lube_per_acre": 22.90,      # 16 L diesel (no-till) + lubricant

    # Drying — per acre
    "drying_per_acre": 102.20,            # $20.85/tonne × 4.90 t/ac, 8 points removal

    # Trucking — per acre
    "trucking_per_acre": 53.95,           # $11.00/tonne × 4.90 t/ac
}

# ============================================================
# 2026 ESCALATION FACTORS
# Source: World Bank Pink Sheet (March 2026), DTN (March 2026),
#         Ridgetown 2025 baseline, Trading Economics (April 7, 2026)
# ============================================================

ESCALATION = {
    "nitrogen": {
        # UAN/Urea track together — both nitrogen products driven by nat gas
        # WB: urea +53.7% in March; DTN: +35% MoM; News: 40-50% since conflict
        "conservative": 0.45,  # Low end of news range
        "mid": 0.50,           # Midpoint
        "worst": 0.54,         # WB single-month spike
        "source": "World Bank urea +53.7% (March 2026); DTN US retail +35% MoM"
    },
    "phosphate": {
        # MAP: WB escalation vs DTN cross-reference
        "conservative": 0.06,
        "mid": 0.16,
        "worst": 0.26,
        "source": "Triangulated: WB MAP escalation +26%, DTN MAP cross-ref +6%"
    },
    "potash": {
        # MOP: least affected — Canada is world's largest producer
        "conservative": 0.04,
        "mid": 0.15,
        "worst": 0.26,
        "source": "Triangulated: WB potash escalation +26%, DTN potash cross-ref +4%"
    },
    "fuel": {
        # Diesel: Ridgetown 2025 $1.16/L → estimated $2.04-$2.22/L farm bulk
        # Applied to entire fuel+lube line (lube is also petroleum-derived)
        "conservative": 0.76,
        "mid": 0.85,
        "worst": 0.91,
        "source": "CTV retail $2.37/L → farm bulk via validated 14% discount"
    },
    "drying": {
        # Custom drying rate is driven primarily by propane cost
        # Propane estimated from crude oil correlation ($65 → $110 Brent)
        # Propane is ~60-70% of custom drying charge; remainder is equipment/labour
        # Blended escalation: ~60% × propane increase + ~40% × flat
        "conservative": 0.19,  # 60% × 32% propane increase
        "mid": 0.28,           # 60% × 46%
        "worst": 0.36,         # 60% × 60%
        "source": "Estimated: propane ~60% of $20.85/t drying charge; propane up 32-60% est.",
        "caveat": "WEAKEST ESTIMATE — propane pricing derived from crude oil correlation"
    },
}


def fmt(val, decimals=0):
    if decimals == 0:
        return f"${val:,.0f}"
    return f"${val:,.{decimals}f}"


def run_grain_corn_scenario(acres=500):
    """500-acre grain corn farm using OMAFRA Pub 60 baseline."""
    o = OMAFRA_2025
    e = ESCALATION

    print("=" * 80)
    print(f"SCENARIO 1: {acres}-ACRE GRAIN CORN FARM")
    print("=" * 80)
    print(f"\nBaseline: OMAFRA Publication 60, 2025 (No-Till)")
    print(f"Projected yield: {o['yield_bu_per_acre']} bu/acre ({o['yield_tonnes_per_acre']} t/ac)")
    print(f"Total acres: {acres}")

    # 2025 per-acre and total costs
    categories = {
        "N Fertilizer (UAN 28-0-0)": {
            "per_acre_2025": o["n_fertilizer_per_acre"],
            "escalation": e["nitrogen"],
        },
        "P₂O₅ Fertilizer": {
            "per_acre_2025": o["p2o5_fertilizer_per_acre"],
            "escalation": e["phosphate"],
        },
        "K₂O Fertilizer": {
            "per_acre_2025": o["k2o_fertilizer_per_acre"],
            "escalation": e["potash"],
        },
        "Fuel + Lubricant": {
            "per_acre_2025": o["fuel_and_lube_per_acre"],
            "escalation": e["fuel"],
        },
        "Drying": {
            "per_acre_2025": o["drying_per_acre"],
            "escalation": e["drying"],
        },
    }

    # Calculate
    results = {}
    for name, cat in categories.items():
        pa = cat["per_acre_2025"]
        esc = cat["escalation"]
        total_2025 = pa * acres
        total_cons = total_2025 * (1 + esc["conservative"])
        total_mid = total_2025 * (1 + esc["mid"])
        total_worst = total_2025 * (1 + esc["worst"])
        results[name] = {
            "per_acre_2025": pa,
            "total_2025": total_2025,
            "total_2026_cons": total_cons,
            "total_2026_mid": total_mid,
            "total_2026_worst": total_worst,
            "esc_cons": esc["conservative"],
            "esc_mid": esc["mid"],
            "esc_worst": esc["worst"],
        }

    # Print detail
    print(f"\n{'Category':<28} {'$/ac 2025':>10} {'Total 2025':>12} {'Esc %':>8} "
          f"{'2026 Cons':>12} {'2026 Mid':>12} {'2026 Worst':>12}")
    print("-" * 100)

    grand_2025 = 0
    grand_cons = 0
    grand_mid = 0
    grand_worst = 0

    # Subtotals for fertilizer
    fert_2025 = 0
    fert_cons = 0
    fert_mid = 0
    fert_worst = 0

    for name, r in results.items():
        print(f"{name:<28} {fmt(r['per_acre_2025'], 2):>10} {fmt(r['total_2025']):>12} "
              f"{r['esc_mid']*100:>7.0f}% "
              f"{fmt(r['total_2026_cons']):>12} {fmt(r['total_2026_mid']):>12} "
              f"{fmt(r['total_2026_worst']):>12}")
        grand_2025 += r["total_2025"]
        grand_cons += r["total_2026_cons"]
        grand_mid += r["total_2026_mid"]
        grand_worst += r["total_2026_worst"]

        if "Fertilizer" in name or "Fert" in name:
            fert_2025 += r["total_2025"]
            fert_cons += r["total_2026_cons"]
            fert_mid += r["total_2026_mid"]
            fert_worst += r["total_2026_worst"]

    fuel_r = results["Fuel + Lubricant"]
    dry_r = results["Drying"]

    print("-" * 100)
    print(f"{'TOTAL':<28} {'':>10} {fmt(grand_2025):>12} {'':>8} "
          f"{fmt(grand_cons):>12} {fmt(grand_mid):>12} {fmt(grand_worst):>12}")

    inc_cons = grand_cons - grand_2025
    inc_mid = grand_mid - grand_2025
    inc_worst = grand_worst - grand_2025

    pac_cons = round(inc_cons / acres)
    pac_mid = round(inc_mid / acres)
    pac_worst = round(inc_worst / acres)

    pct_cons = round((grand_cons / grand_2025 - 1) * 100)
    pct_mid = round((grand_mid / grand_2025 - 1) * 100)
    pct_worst = round((grand_worst / grand_2025 - 1) * 100)

    print(f"\n{'Metric':<28} {'Conservative':>12} {'Midpoint':>12} {'Worst-Case':>12}")
    print("-" * 68)
    print(f"{'Total Increase ($)':<28} {fmt(inc_cons):>12} {fmt(inc_mid):>12} {fmt(inc_worst):>12}")
    print(f"{'Increase (%)':<28} {'+' + str(pct_cons) + '%':>12} {'+' + str(pct_mid) + '%':>12} {'+' + str(pct_worst) + '%':>12}")
    print(f"{'Per Acre Increase':<28} {'$' + str(pac_cons) + '/ac':>12} {'$' + str(pac_mid) + '/ac':>12} {'$' + str(pac_worst) + '/ac':>12}")

    return {
        "scenario": f"{acres}-acre grain corn farm",
        "source": "OMAFRA Publication 60, 2025 (No-Till)",
        "acres": acres,
        "yield_bu_per_acre": o["yield_bu_per_acre"],
        "total_2025": round(grand_2025),
        "total_2026_range": [round(grand_cons), round(grand_mid), round(grand_worst)],
        "increase_range": [round(inc_cons), round(inc_mid), round(inc_worst)],
        "per_acre_increase": [pac_cons, pac_mid, pac_worst],
        "pct_increase": [pct_cons, pct_mid, pct_worst],
        "details": {
            "fertilizer": {"2025": round(fert_2025), "2026_mid": round(fert_mid)},
            "fuel": {"2025": round(fuel_r["total_2025"]), "2026_mid": round(fuel_r["total_2026_mid"])},
            "drying": {"2025": round(dry_r["total_2025"]), "2026_mid": round(dry_r["total_2026_mid"])},
        }
    }


def run_vegetable_farm_scenario():
    """200-acre vegetable farm — nitrogen/urea focus (unchanged)."""
    # This scenario is simpler — just urea pricing on nitrogen demand
    # Using OMAFRA Pub 839 vegetable N rates

    data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "data", "farm_cost_impact_data.json")
    with open(data_path, "r") as f:
        DATA = json.load(f)

    RATES = DATA["application_rates"]
    CONV = RATES["conversions"]
    fert_base = DATA["baseline_2025"]["fertilizer"]["urea_46_0_0"]
    fert_est = DATA["estimated_april_2026_ontario"]["fertilizer"]["urea_46_0_0"]

    crops = {
        "sweet_corn":          {"acres": 60, "n_rate": 135},
        "potatoes":            {"acres": 50, "n_rate": 175},
        "tomatoes_processing": {"acres": 40, "n_rate": 120},
        "peppers":             {"acres": 25, "n_rate": 115},
        "leafy_greens":        {"acres": 25, "n_rate": 100},
    }
    total_acres = 200

    print("\n\n" + "=" * 80)
    print("SCENARIO 2: 200-ACRE VEGETABLE FARM (Nitrogen / Urea Focus)")
    print("=" * 80)

    total_n_lbs = 0
    for crop_name, info in crops.items():
        n_total = info["acres"] * info["n_rate"]
        total_n_lbs += n_total

    urea_lbs = total_n_lbs / CONV["urea_n_content"]
    urea_tonnes = urea_lbs / CONV["lbs_per_tonne"]

    price_2025 = fert_base["price_per_tonne"]
    price_2026_low = fert_est["working_range"]["low"]
    price_2026_mid = fert_est["midpoint"]
    price_2026_high = fert_est["working_range"]["high"]

    cost_2025 = urea_tonnes * price_2025
    cost_cons = urea_tonnes * price_2026_low
    cost_mid = urea_tonnes * price_2026_mid
    cost_worst = urea_tonnes * price_2026_high

    print(f"\n  Total nitrogen demand: {total_n_lbs:,} lbs N")
    print(f"  Urea equivalent: {urea_tonnes:.1f} tonnes")
    print(f"  2025 cost: {fmt(cost_2025)}")
    print(f"  2026 range: {fmt(cost_cons)} - {fmt(cost_mid)} - {fmt(cost_worst)}")
    print(f"  Increase: {fmt(cost_cons - cost_2025)} - {fmt(cost_worst - cost_2025)}")

    return {
        "scenario": "200-acre vegetable farm",
        "urea_tonnes": round(urea_tonnes, 1),
        "total_n_lbs": total_n_lbs,
        "cost_2025": round(cost_2025),
        "cost_2026_range": [round(cost_cons), round(cost_mid), round(cost_worst)],
        "increase_range": [round(cost_cons - cost_2025), round(cost_mid - cost_2025), round(cost_worst - cost_2025)],
        "per_acre_cost_2025": round(cost_2025 / total_acres),
        "per_acre_cost_2026_mid": round(cost_mid / total_acres),
    }


if __name__ == "__main__":
    grain = run_grain_corn_scenario(500)
    veg = run_vegetable_farm_scenario()

    output = {
        "grain_farm_500ac": grain,
        "vegetable_farm_200ac": veg,
        "data_sources": {
            "2025_baseline_grain": "OMAFRA Publication 60: Field Crop Budgets, 2025 (p.12, No-Till)",
            "2025_baseline_fertilizer_prices": "Ridgetown Farm Input Monitoring Project, April 16, 2025",
            "2026_escalation": "Triangulated: World Bank Pink Sheet (March 2026), DTN Retail Index (March 2026), Trading Economics (April 7, 2026)",
            "2026_fuel": "CTV News retail + validated 14% farm bulk discount",
            "vegetable_rates": "OMAFRA Publication 839",
            "geopolitical": "Strait of Hormuz disruption (Feb 2026 onset)"
        },
        "caveats": [
            "2026 prices are estimates — Ridgetown spring 2026 survey not yet published",
            "Drying cost escalation assumes propane is ~60% of custom drying charge — weakest estimate",
            "StatsCan FIPI Q4 2025 (releases April 10, 2026) may provide additional validation",
            "This analysis excludes crop protection, seed, machinery parts, and labour",
            "World Bank escalation (Method A) represents spot/replacement cost — blended retail may lag"
        ]
    }

    results_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                "data", "farm_cost_impact_results.json")
    with open(results_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n\nResults saved to: {results_path}")
