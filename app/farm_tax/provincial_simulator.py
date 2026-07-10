"""Provincial ratio simulation engine.

Computes the province-wide impact of a mandated farm tax ratio
using per-municipality True W / Model-vs-Model revenue-neutral math.
"""
import numpy as np
import pandas as pd


def simulate_mandated_ratio(fir_df: pd.DataFrame, mandated_ratio: float) -> dict:
    """Simulate province-wide impact of a mandated farm tax ratio.

    For each municipality where current ratio > mandated_ratio, computes:
    - Farm tax savings using True W / Model-vs-Model approach
    - Redistribution to residential, commercial, industrial classes

    Revenue-neutral per municipality (respects ring-fenced tax pools).
    """
    latest = fir_df.sort_values("year").drop_duplicates("sgc_code", keep="last")

    # Filter to municipalities with valid ratio data
    valid = latest[
        (latest["farmland_tax_ratio"].notna())
        & (latest["farmland_tax_ratio"] > 0)
        & (latest["residential_cva"].notna())
        & (latest["residential_cva"] > 0)
        & (latest["residential_muni_taxes"].notna())
        & (latest["residential_muni_taxes"] > 0)
        & (latest["total_muni_taxes"].notna())
        & (latest["total_muni_taxes"] > 0)
        & (latest["farmland_cva"].notna())
        & (latest["farmland_cva"] > 0)
    ].copy()

    # Only affect municipalities ABOVE the mandated ratio
    affected = valid[valid["farmland_tax_ratio"] > mandated_ratio].copy()
    unaffected = valid[valid["farmland_tax_ratio"] <= mandated_ratio]

    if affected.empty:
        return {
            "n_affected": 0, "n_unaffected": len(unaffected),
            "n_total": len(valid),
            "farm_savings_total": 0, "res_increase_total": 0,
            "com_increase_total": 0, "ind_increase_total": 0,
            "other_increase_total": 0,
            "avg_res_per_household": 0,
            "avg_res_per_household_month": 0,
            "total_households_affected": 0,
            "affected_details": pd.DataFrame(),
        }

    # ── True W approach per municipality (vectorized) ──
    a = affected
    a["res_rate"] = a["residential_muni_taxes"] / a["residential_cva"]
    a["true_W"] = a["total_muni_taxes"] / a["res_rate"]

    # Old model farm taxes (per True W)
    a["model_farm_old"] = a["farmland_tax_ratio"] * a["res_rate"] * a["farmland_cva"]

    # New True W with mandated ratio
    a["new_W"] = a["true_W"] - a["farmland_cva"] * (a["farmland_tax_ratio"] - mandated_ratio)
    a["new_res_rate"] = a["total_muni_taxes"] / a["new_W"]

    # New model farm taxes
    a["model_farm_new"] = mandated_ratio * a["new_res_rate"] * a["farmland_cva"]
    a["farm_savings"] = a["model_farm_old"] - a["model_farm_new"]

    # Increases by class (model-vs-model)
    a["model_res_old"] = a["res_rate"] * a["residential_cva"]
    a["model_res_new"] = a["new_res_rate"] * a["residential_cva"]
    a["res_increase"] = a["model_res_new"] - a["model_res_old"]

    com_ratio = a["commercial_tax_ratio"].fillna(0)
    a["com_increase"] = np.where(
        com_ratio > 0,
        com_ratio * (a["new_res_rate"] - a["res_rate"]) * a["commercial_cva"].fillna(0),
        0,
    )

    ind_ratio = a["industrial_tax_ratio"].fillna(0)
    a["ind_increase"] = np.where(
        ind_ratio > 0,
        ind_ratio * (a["new_res_rate"] - a["res_rate"]) * a["industrial_cva"].fillna(0),
        0,
    )

    # Other increase = farm_savings - res - com - ind (guarantees zero-sum)
    a["other_increase"] = a["farm_savings"] - a["res_increase"] - a["com_increase"] - a["ind_increase"]

    # Per-household impact
    total_hh = a["total_households"].sum()
    res_increase_total = a["res_increase"].sum()
    avg_per_hh = res_increase_total / total_hh if total_hh > 0 else 0

    return {
        "n_affected": len(a),
        "n_unaffected": len(unaffected),
        "n_total": len(valid),
        "current_weighted_ratio": (valid["farmland_tax_ratio"] * valid["farmland_cva"]).sum() / valid["farmland_cva"].sum(),
        "mandated_ratio": mandated_ratio,
        "farm_savings_total": a["farm_savings"].sum(),
        "res_increase_total": res_increase_total,
        "com_increase_total": a["com_increase"].sum(),
        "ind_increase_total": a["ind_increase"].sum(),
        "other_increase_total": a["other_increase"].sum(),
        "avg_res_per_household": avg_per_hh,
        "avg_res_per_household_month": avg_per_hh / 12,
        "total_households_affected": total_hh,
        "affected_details": a[["municipality_name", "farmland_tax_ratio", "farm_savings",
                                "res_increase", "total_households"]].copy(),
    }
