"""
Unified Similarity Engine
=========================
Shared module for computing community similarity scores used by both the
Streamlit UI and the PDF report generator.

Red Team Remediation: Fixes Q1–Q6, Q9–Q10, Q16–Q17, A1–A2
"""

import numpy as np
import pandas as pd

# ── Canonical weight set (ONLY these indicators participate) ── Fixes Q4, Q5
SIMILARITY_WEIGHTS = {
    "population": 2.0,
    "median_hh_income": 2.0,
    "unemployment_rate": 1.5,
    "median_age": 1.5,
    "pop_density": 1.5,
    "participation_rate": 1.2,
    "avg_hh_size": 1.2,
}

# Indicators where lower = better (used by gap analysis)
INVERSE_INDICATORS = {
    "unemployment_rate", "low_income_pct", "unemployed",
    "unaffordable_renter_pct", "unaffordable_owner_pct",
    "major_repairs_pct", "core_housing_need", "unsuitable_housing",
    "broadband_underserved_pct", "broadband_unserved_pct",
}

# Variables requiring log-transform before z-scoring (right-skewed) — Fixes A1
LOG_TRANSFORM_COLS = ["population", "median_hh_income", "pop_density"]

# Minimum number of indicators a community must have (out of 7) — Fixes Q2
MIN_INDICATOR_COVERAGE = 5


def get_peer_communities(
    indicators_df: pd.DataFrame,
    ref_code: str,
    latest_year: int,
    exclude_codes: list = None,
    n: int = 10,
):
    """
    Compute peer communities using weighted z-score Euclidean distance.

    Returns
    -------
    (top_n_distances, similarity_scores) : tuple[pd.Series, pd.Series]
        top_n_distances : smallest n distances (index = sgc_code)
        similarity_scores : absolute 0-100 similarity for those peers
        Returns (None, None) if ref_code is missing or insufficient data.
    """
    core_cols = list(SIMILARITY_WEIGHTS.keys())

    # 1. Isolate ONLY the weighted indicators — Fixes Q5
    df_filtered = indicators_df[
        (indicators_df["census_year"] == latest_year)
        & (indicators_df["indicator"].isin(core_cols))
    ]

    # 2. Pivot deterministically — Fixes Q9
    profile_data = df_filtered.pivot_table(
        index="sgc_code", columns="indicator", values="value", aggfunc="mean"
    )

    # 3. Strict row-level coverage — Fixes Q2
    profile_data = profile_data.dropna(thresh=MIN_INDICATOR_COVERAGE)
    if ref_code not in profile_data.index:
        return None, None

    # 4. Log-transform skewed variables — Fixes A1
    for col in LOG_TRANSFORM_COLS:
        if col in profile_data.columns:
            profile_data[col] = np.log1p(profile_data[col].clip(lower=0))

    # 5. Z-score normalization — Fixes Q6
    stds = profile_data.std().replace(0, 1)
    profile_z = (profile_data - profile_data.mean()) / stds

    # 6. Pairwise weighted distance — Fixes Q1, Q3, A2
    ref_vector = profile_z.loc[ref_code]
    weights = pd.Series(SIMILARITY_WEIGHTS)

    diff = profile_z.subtract(ref_vector, axis=1)
    sq_diff = diff.pow(2).mul(weights, axis=1)

    # Normalize for missing data (Weighted Mean Squared Error) — Fixes A2
    sum_sq_diff = sq_diff.sum(axis=1, skipna=True)
    valid_weights = diff.notna().mul(weights, axis=1).sum(axis=1)

    # Scale back up by total weight to maintain absolute distance scale
    total_w = weights.sum()
    distances = np.sqrt((sum_sq_diff / valid_weights.replace(0, np.nan)) * total_w)

    # 7. Absolute similarity score using exponential decay — Fixes Q10
    sim_scores = np.exp(-0.4 * distances) * 100

    # 8. Filter & rank
    drop_list = [ref_code] + (exclude_codes if exclude_codes else [])
    distances = distances.drop(index=drop_list, errors="ignore")
    sim_scores = sim_scores.drop(index=drop_list, errors="ignore")

    top_n = distances.dropna().nsmallest(n)
    return top_n, sim_scores.loc[top_n.index]
