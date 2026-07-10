"""
Scenario Planning Engine
=========================
Hamilton-Perry projection engine with MOF Share-Capture raking.

Provides:
  - Cohort Change Ratio (CCR) calculations from Census data
  - Population projections by age band (2021 → 2041)
  - MOF Census Division share-capture controls
  - Scenario presets (decline, stable, growth, boom)

Used by: pages/10_🔮_Scenario_Planner.py
"""

import pandas as pd
import numpy as np
from pathlib import Path
import yaml

# --- Data paths ---
WELLBEING_DIR = Path("data/latest/wellbeing")
CENSUS_FILE = WELLBEING_DIR / "census_indicators.csv"
GEO_FILE = WELLBEING_DIR / "dim_geography.csv"
MOF_FILE = WELLBEING_DIR / "mof_projections.csv"
POP_ESTIMATES_FILE = Path("data/derived/pop_estimates_annual.csv")


# --- Scenario presets ---
SCENARIO_PRESETS = {
    "Decline": {
        "migration_factor": 0.6,
        "aging_factor": 1.15,
        "description": "Out-migration, accelerated aging. Typical of resource-dependent communities after a major employer closure.",
    },
    "Stable": {
        "migration_factor": 1.0,
        "aging_factor": 1.0,
        "description": "Current trends continue. Historical CCRs maintained without adjustment.",
    },
    "Growth": {
        "migration_factor": 1.3,
        "aging_factor": 0.95,
        "description": "Moderate in-migration, GTA spillover effect. Common in communities within 90 min of major centres.",
    },
    "Boom": {
        "migration_factor": 1.8,
        "aging_factor": 0.9,
        "description": "Strong in-migration, new major development. Comparable to communities near Highway 413 or GO Transit expansion.",
    },
}

# Age band labels for display
AGE_BANDS = ["0–14", "15–64", "65+"]
AGE_BAND_KEYS = ["pop_0_14", "pop_15_64", "pop_65_plus"]

# --- 5-year cohort keys (true Hamilton-Perry) ---
COHORT_KEYS = [
    "cohort_0_4", "cohort_5_9", "cohort_10_14", "cohort_15_19",
    "cohort_20_24", "cohort_25_29", "cohort_30_34", "cohort_35_39",
    "cohort_40_44", "cohort_45_49", "cohort_50_54", "cohort_55_59",
    "cohort_60_64", "cohort_65_69", "cohort_70_74", "cohort_75_79",
    "cohort_80_84", "cohort_85_plus",
]

# Map each cohort to a summary band for backwards compatibility
COHORT_TO_BAND = {}
for _ck in COHORT_KEYS:
    _idx = COHORT_KEYS.index(_ck)
    if _idx <= 2:      # 0-4, 5-9, 10-14 → youth
        COHORT_TO_BAND[_ck] = "youth"
    elif _idx <= 12:   # 15-19 through 60-64 → working
        COHORT_TO_BAND[_ck] = "working"
    else:              # 65-69 through 85+ → senior
        COHORT_TO_BAND[_ck] = "senior"


def get_census_age_data(sgc_code: str) -> pd.DataFrame:
    """
    Load age-band data for all Census years for a given CSD.

    Returns DataFrame with columns: census_year, pop_0_14, pop_15_64, pop_65_plus, population
    """
    if not CENSUS_FILE.exists():
        return pd.DataFrame()

    df = pd.read_csv(CENSUS_FILE)
    df["sgc_code"] = df["sgc_code"].astype(str).str.zfill(7)

    csd = df[df["sgc_code"] == sgc_code].copy()
    if csd.empty:
        return pd.DataFrame()

    # Pivot: rows = census_year, columns = indicator, values = value
    pivot = csd.pivot_table(index="census_year", columns="indicator", values="value")
    pivot = pivot.reset_index()

    # Ensure we have the needed columns
    needed = ["census_year", "population"] + AGE_BAND_KEYS
    available = [c for c in needed if c in pivot.columns]
    result = pivot[available].copy()

    # Sort by year
    result = result.sort_values("census_year").reset_index(drop=True)
    return result


def get_pop_estimates(sgc_code: str) -> pd.DataFrame:
    """
    Load annual population estimates (StatCan 17-10-0155-01) for a given CSD.

    Returns DataFrame with columns: year, population
    Only includes post-Census years (2022+).
    """
    if not POP_ESTIMATES_FILE.exists():
        return pd.DataFrame()

    df = pd.read_csv(POP_ESTIMATES_FILE)
    df["sgc_code"] = df["sgc_code"].astype(str).str.zfill(7)
    csd = df[df["sgc_code"] == sgc_code][["year", "population"]].copy()
    return csd.sort_values("year").reset_index(drop=True)


def get_census_cohort_data(sgc_code: str) -> pd.DataFrame:
    """
    Load 5-year age cohort data for all Census years for a given CSD.

    Returns DataFrame with columns: census_year + 18 cohort columns.
    Returns empty DataFrame if cohort data is not available.
    """
    if not CENSUS_FILE.exists():
        return pd.DataFrame()

    df = pd.read_csv(CENSUS_FILE)
    df["sgc_code"] = df["sgc_code"].astype(str).str.zfill(7)

    csd = df[df["sgc_code"] == sgc_code].copy()
    if csd.empty:
        return pd.DataFrame()

    # Filter to cohort indicators only
    cohort_df = csd[csd["indicator"].isin(COHORT_KEYS)].copy()
    if cohort_df.empty:
        return pd.DataFrame()

    # Pivot: rows = census_year, columns = cohort key, values = population
    pivot = cohort_df.pivot_table(
        index="census_year", columns="indicator", values="value"
    ).reset_index()

    # Only include years where we have at least 15 of 18 cohorts
    cohort_cols = [c for c in COHORT_KEYS if c in pivot.columns]
    if len(cohort_cols) < 15:
        return pd.DataFrame()

    # Fill any missing cohorts with 0
    for ck in COHORT_KEYS:
        if ck not in pivot.columns:
            pivot[ck] = 0

    return pivot.sort_values("census_year").reset_index(drop=True)


def calculate_ccrs(census_data: pd.DataFrame) -> dict:
    """
    Calculate Cohort Change Ratios from the two most recent Census periods.

    CCR = P(age_band, t) / P(age_band, t-5)

    If a cohort grew, CCR > 1.0 (in-migration exceeds out-migration + mortality).
    If a cohort shrank, CCR < 1.0.
    """
    if len(census_data) < 2:
        return {"youth": 1.0, "working": 1.0, "senior": 1.0}

    # Use the two most recent Census years
    latest = census_data.iloc[-1]
    previous = census_data.iloc[-2]

    def safe_ratio(new, old):
        if pd.isna(old) or pd.isna(new) or old <= 0:
            return 1.0
        return max(0.5, min(2.0, new / old))  # Clamp to [0.5, 2.0]

    return {
        "youth": safe_ratio(latest.get("pop_0_14", 0), previous.get("pop_0_14", 1)),
        "working": safe_ratio(latest.get("pop_15_64", 0), previous.get("pop_15_64", 1)),
        "senior": safe_ratio(latest.get("pop_65_plus", 0), previous.get("pop_65_plus", 1)),
    }


def calculate_cohort_ccrs(cohort_data: pd.DataFrame) -> dict:
    """
    Calculate diagonal Cohort Change Survival Ratios (CCSRs).

    True Hamilton-Perry: each 5-year cohort ages into the NEXT band.
      CCSR[i] = cohort[i+1](t) / cohort[i](t-5)

    For example:
      CCSR for 25-29 = cohort_30_34(2021) / cohort_25_29(2016)

    The youngest cohort (0-4) uses a Child-Woman Ratio:
      CWR = cohort_0_4(t) / sum(cohort_20_24..cohort_35_39)(t-5)

    The oldest cohort (85+) is open-ended:
      survival_85 = cohort_85_plus(t) / (cohort_80_84(t-5) + cohort_85_plus(t-5))
    """
    if len(cohort_data) < 2:
        # Fallback: no diagonal ratios possible
        return None

    t1 = cohort_data.iloc[-1]   # Most recent (e.g., 2021)
    t0 = cohort_data.iloc[-2]   # Previous (e.g., 2016)

    def safe_ratio(new, old, lo=0.3, hi=2.5):
        if pd.isna(old) or pd.isna(new) or old <= 0:
            return 1.0
        return max(lo, min(hi, new / old))

    ccsrs = {}

    # Child-Woman Ratio: births proxy
    # How many 0-4 year olds per woman of childbearing age (20-39)?
    women_20_39 = sum(
        t0.get(ck, 0) for ck in ["cohort_20_24", "cohort_25_29", "cohort_30_34", "cohort_35_39"]
    )
    ccsrs["cwr"] = safe_ratio(t1.get("cohort_0_4", 0), women_20_39, lo=0.05, hi=1.0) if women_20_39 > 0 else 0.25

    # Diagonal survival: cohort[i] at t-5 → cohort[i+1] at t
    for i in range(len(COHORT_KEYS) - 2):  # Skip last (85+); handle separately
        from_key = COHORT_KEYS[i]
        to_key = COHORT_KEYS[i + 1]
        ccsrs[from_key] = safe_ratio(t1.get(to_key, 0), t0.get(from_key, 1))

    # Open-ended 85+: survival from 80-84 + continuation of 85+
    old_80_84 = t0.get("cohort_80_84", 0)
    old_85_plus = t0.get("cohort_85_plus", 0)
    new_85_plus = t1.get("cohort_85_plus", 0)
    combined_old = old_80_84 + old_85_plus
    ccsrs["cohort_80_84"] = safe_ratio(new_85_plus, combined_old, lo=0.1, hi=1.5) if combined_old > 0 else 0.5

    return ccsrs


def project_population_cohort(
    base_cohorts: dict,
    ccsrs: dict,
    start_year: int = 2021,
    end_year: int = 2041,
    step: int = 5,
    migration_factor: float = 1.0,
    aging_factor: float = 1.0,
) -> pd.DataFrame:
    """
    Project population using true Hamilton-Perry diagonal cohort survival.

    Each 5-year step:
      1. Births: new cohort_0_4 = women_20_39 × adjusted CWR
      2. Aging: cohort[i+1] = cohort[i] × adjusted CCSR[i]
      3. Open-ended: cohort_85+ = cohort_80_84 × CCSR + cohort_85+ × survival_85

    Migration factor scales working-age CCSRs (15-64).
    Aging factor scales senior CCSRs (65+).
    Youth CCSRs get a dampened migration effect (0.3 exponent).
    """
    results = []

    # Build initial population vector
    current = {ck: float(base_cohorts.get(ck, 0)) for ck in COHORT_KEYS}

    # Compute summary bands
    def summarize(cohorts):
        youth = sum(cohorts.get(ck, 0) for ck in COHORT_KEYS[:3])
        working = sum(cohorts.get(ck, 0) for ck in COHORT_KEYS[3:13])
        senior = sum(cohorts.get(ck, 0) for ck in COHORT_KEYS[13:])
        return {
            "youth": round(youth),
            "working": round(working),
            "senior": round(senior),
            "total": round(youth + working + senior),
        }

    row = {"year": start_year}
    row.update({ck: round(current[ck]) for ck in COHORT_KEYS})
    row.update(summarize(current))
    results.append(row)

    # Adjust CCSRs by scenario factors
    adj_ccsrs = {}
    for key, raw in ccsrs.items():
        if key == "cwr":
            # CWR scales with migration (more families = more births)
            adj_ccsrs[key] = 1.0 + (raw - 1.0) * (migration_factor ** 0.5) if raw != 0 else raw
            continue

        band = COHORT_TO_BAND.get(key, "working")
        if band == "youth":
            factor = migration_factor ** 0.3
        elif band == "senior":
            factor = aging_factor
        else:
            factor = migration_factor

        adj_ccsrs[key] = 1.0 + (raw - 1.0) * factor
        # Clamp to reasonable per-step range
        adj_ccsrs[key] = max(0.3, min(2.0, adj_ccsrs[key]))

    years = list(range(start_year + step, end_year + 1, step))
    # Ensure we reach at least end_year (rebase can shift alignment)
    if years and years[-1] < end_year:
        years.append(years[-1] + step)

    for year in years:
        new = {}

        # 1. Births: new 0-4 cohort from Child-Woman Ratio
        women_20_39 = sum(
            current.get(ck, 0) for ck in ["cohort_20_24", "cohort_25_29", "cohort_30_34", "cohort_35_39"]
        )
        new["cohort_0_4"] = women_20_39 * adj_ccsrs.get("cwr", 0.25)

        # 2. Diagonal aging: each cohort ages into the next
        for i in range(len(COHORT_KEYS) - 2):  # 0-4 → 5-9, ..., 75-79 → 80-84
            from_key = COHORT_KEYS[i]
            to_key = COHORT_KEYS[i + 1]
            ccsr = adj_ccsrs.get(from_key, 1.0)
            new[to_key] = current[from_key] * ccsr

        # 3. Open-ended 85+: inflow from 80-84 + survival of existing 85+
        ccsr_80 = adj_ccsrs.get("cohort_80_84", 0.5)
        # Split: 80-84 aging in + 85+ surviving
        # The CCSR for 80-84 represents the combined survival into 85+
        new["cohort_85_plus"] = (
            current["cohort_80_84"] * ccsr_80 +
            current["cohort_85_plus"] * ccsr_80 * 0.6  # Higher mortality for 85+
        )

        # Floor: no negative populations
        for ck in COHORT_KEYS:
            new[ck] = max(0, new.get(ck, 0))

        row = {"year": year}
        row.update({ck: round(new[ck]) for ck in COHORT_KEYS})
        row.update(summarize(new))
        results.append(row)

        current = new

    df = pd.DataFrame(results)
    return df


def project_population(
    base_year_data: dict,
    ccrs: dict,
    start_year: int = 2021,
    end_year: int = 2041,
    step: int = 5,
    migration_factor: float = 1.0,
    aging_factor: float = 1.0,
) -> pd.DataFrame:
    """
    Project population using Hamilton-Perry CCRs.

    Slider factors modify the DEVIATION from 1.0 in each CCR:
      adjusted_ccr = 1.0 + (raw_ccr - 1.0) * factor

    This prevents unrealistic compounding. For example:
      CCR=1.076, migration=0.6 → 1.0 + (0.076 × 0.6) = 1.046 (slower growth)
      CCR=1.076, migration=1.5 → 1.0 + (0.076 × 1.5) = 1.114 (faster growth)
      CCR=0.95,  migration=0.6 → 1.0 + (-0.05 × 0.6) = 0.970 (slower decline)
    """
    results = []
    current = {
        "year": start_year,
        "youth": base_year_data.get("youth", 0),
        "working": base_year_data.get("working", 0),
        "senior": base_year_data.get("senior", 0),
    }
    current["total"] = current["youth"] + current["working"] + current["senior"]
    results.append(current.copy())

    # Compute adjusted CCRs (apply slider factors to deviation from 1.0)
    adj_ccrs = {
        "youth": 1.0 + (ccrs["youth"] - 1.0) * (migration_factor ** 0.3),
        "working": 1.0 + (ccrs["working"] - 1.0) * migration_factor,
        "senior": 1.0 + (ccrs["senior"] - 1.0) * aging_factor,
    }

    # Clamp adjusted CCRs to reasonable range [0.8, 1.5] per 5-year step
    for k in adj_ccrs:
        adj_ccrs[k] = max(0.8, min(1.5, adj_ccrs[k]))

    years = list(range(start_year + step, end_year + 1, step))
    # Ensure we reach at least end_year (rebase can shift alignment)
    if years and years[-1] < end_year:
        years.append(years[-1] + step)

    for year in years:
        new = {
            "year": year,
            "youth": current["youth"] * adj_ccrs["youth"],
            "working": current["working"] * adj_ccrs["working"],
            "senior": current["senior"] * adj_ccrs["senior"],
        }
        new["total"] = new["youth"] + new["working"] + new["senior"]

        # Floor: population can't go below 50
        new["total"] = max(50, new["total"])

        results.append(new.copy())
        current = new

    df = pd.DataFrame(results)

    # Round to integers
    for col in ["youth", "working", "senior", "total"]:
        df[col] = df[col].round(0).astype(int)

    return df


def interpolate_annual(projection_df: pd.DataFrame) -> pd.DataFrame:
    """
    Interpolate 5-year projections to annual values for smoother charts.
    """
    if projection_df.empty:
        return projection_df

    years_full = list(range(
        int(projection_df["year"].min()),
        int(projection_df["year"].max()) + 1,
    ))

    result = pd.DataFrame({"year": years_full})
    result = result.merge(projection_df, on="year", how="left")

    # Always interpolate summary bands
    interp_cols = ["youth", "working", "senior", "total"]

    # Also interpolate cohort columns if present
    cohort_cols_present = [c for c in COHORT_KEYS if c in result.columns]
    interp_cols += cohort_cols_present

    for col in interp_cols:
        if col in result.columns:
            result[col] = result[col].interpolate(method="linear").round(0).astype(int)

    # Ensure total == youth + working + senior (independent rounding can diverge)
    if all(c in result.columns for c in ["youth", "working", "senior"]):
        result["total"] = result["youth"] + result["working"] + result["senior"]

    return result


def get_mof_county_projection(county_name: str) -> pd.DataFrame:
    """
    Load MOF projection for a Census Division (county).

    Returns DataFrame with year, total, age_0_14, age_15_64, age_65_plus
    (annual values, 2024–2051).
    """
    if not MOF_FILE.exists():
        return pd.DataFrame()

    mof = pd.read_csv(MOF_FILE)
    county_data = mof[mof["county"].str.lower() == county_name.lower()].copy()

    if county_data.empty:
        # Try partial match
        county_data = mof[mof["county"].str.contains(county_name, case=False, na=False)]

    return county_data


def share_capture_rake(
    local_projection: pd.DataFrame,
    mof_county: pd.DataFrame,
    base_share: float,
    method: str = "constant",
    share_trend: float = 0.0,
) -> pd.DataFrame:
    """
    Rake local projection to MOF county-level controls.

    The MOF total dictates the population envelope; the local HP projection's
    age-band *ratios* (shaped by scenario sliders) distribute that envelope
    across youth/working/senior. This means:
      - Total tracks MOF (defensible)
      - Age structure reflects scenario (useful)
    """
    if mof_county.empty or local_projection.empty:
        return local_projection

    raked = local_projection.copy()

    for idx, row in raked.iterrows():
        year = row["year"]
        mof_year = mof_county[mof_county["year"] == year]

        if mof_year.empty:
            continue

        mof_total = mof_year["total"].values[0]

        if method == "constant":
            target_pop = mof_total * base_share
        elif method == "trended":
            years_from_base = year - raked["year"].min()
            adjusted_share = base_share * (1 + share_trend) ** years_from_base
            target_pop = mof_total * adjusted_share
        else:
            target_pop = mof_total * base_share

        # Scale total to MOF target, preserving age-band proportions from HP
        local_total = row["youth"] + row["working"] + row["senior"]
        if local_total > 0:
            y_share = row["youth"] / local_total
            w_share = row["working"] / local_total
            s_share = row["senior"] / local_total
            raked.at[idx, "youth"] = round(target_pop * y_share)
            raked.at[idx, "working"] = round(target_pop * w_share)
            raked.at[idx, "senior"] = round(target_pop * s_share)
            raked.at[idx, "total"] = round(target_pop)

    return raked


def calculate_derived_metrics(projection_df: pd.DataFrame, avg_hh_size: float = 2.5) -> pd.DataFrame:
    """Add planning-relevant derived columns to projection."""
    df = projection_df.copy()

    # Dependency ratio: (youth + seniors) / working-age × 100
    df["dependency_ratio"] = ((df["youth"] + df["senior"]) / df["working"].clip(lower=1) * 100).round(1)

    # Senior share (%)
    df["senior_share_pct"] = (df["senior"] / df["total"].clip(lower=1) * 100).round(1)

    # Estimated households
    df["est_households"] = (df["total"] / avg_hh_size).round(0).astype(int)

    # Youth share (%)
    df["youth_share_pct"] = (df["youth"] / df["total"].clip(lower=1) * 100).round(1)

    # Working-age share (%)
    df["working_share_pct"] = (df["working"] / df["total"].clip(lower=1) * 100).round(1)

    # Population change from base year
    base = df["total"].iloc[0]
    df["change_from_base"] = df["total"] - base
    df["change_pct"] = ((df["total"] / base - 1) * 100).round(1) if base > 0 else 0

    return df


def run_scenario(
    sgc_code: str,
    county_name: str = None,
    migration_factor: float = 1.0,
    aging_factor: float = 1.0,
    housing_cap: int = 0,
    avg_hh_size: float = 2.5,
    use_mof_controls: bool = True,
    mof_method: str = "constant",
    end_year: int = 2041,
) -> dict:
    """
    Run a complete scenario for a community. Returns dict with:
      - projection: DataFrame of year-by-year population
      - ccrs: raw Cohort Change Ratios
      - census_history: historical Census data
      - mof_county: county-level controls (if available)
      - metadata: scenario parameters
    """
    # 1. Load Census data (both broad-band and cohort)
    census = get_census_age_data(sgc_code)
    if census.empty:
        return {"error": "No Census data found for this community."}

    # 1b. Try to load 5-year cohort data for true Hamilton-Perry
    cohort_census = get_census_cohort_data(sgc_code)
    cohort_mode = not cohort_census.empty and len(cohort_census) >= 2

    # 2. Calculate CCRs
    ccrs = calculate_ccrs(census)  # Always compute for display/fallback
    cohort_ccrs = None
    if cohort_mode:
        cohort_ccrs = calculate_cohort_ccrs(cohort_census)
        if cohort_ccrs is None:
            cohort_mode = False  # Fallback if calculation fails

    # 3. Build base year data
    latest = census.iloc[-1]
    base_year = int(latest["census_year"])
    base = {
        "youth": float(latest.get("pop_0_14", 0)),
        "working": float(latest.get("pop_15_64", 0)),
        "senior": float(latest.get("pop_65_plus", 0)),
        "total": float(latest.get("population", 0)),
    }

    # Build cohort base if available
    cohort_base = {}
    if cohort_mode:
        cohort_latest = cohort_census.iloc[-1]
        for ck in COHORT_KEYS:
            cohort_base[ck] = float(cohort_latest.get(ck, 0))

    # 3b. Rebase from latest intercensal estimate if available
    estimates = get_pop_estimates(sgc_code)
    estimate_history = pd.DataFrame()
    if not estimates.empty:
        latest_est = estimates.iloc[-1]
        est_year = int(latest_est["year"])
        est_pop = float(latest_est["population"])

        if est_year > base_year and est_pop > 0 and base["total"] > 0:
            # Scale factor for rebase
            scale = est_pop / base["total"]

            # Rebase broad bands
            base["youth"] = base["youth"] * scale
            base["working"] = base["working"] * scale
            base["senior"] = base["senior"] * scale
            base["total"] = est_pop

            # Rebase cohorts proportionally
            if cohort_mode:
                cohort_total = sum(cohort_base.values())
                if cohort_total > 0:
                    cohort_scale = est_pop / cohort_total
                    for ck in COHORT_KEYS:
                        cohort_base[ck] *= cohort_scale

            base_year = est_year
            estimate_history = estimates.copy()

    # 4. Project
    if cohort_mode:
        projection = project_population_cohort(
            cohort_base, cohort_ccrs,
            start_year=base_year,
            end_year=end_year,
            migration_factor=migration_factor,
            aging_factor=aging_factor,
        )
    else:
        projection = project_population(
            base, ccrs,
            start_year=base_year,
            end_year=end_year,
            migration_factor=migration_factor,
            aging_factor=aging_factor,
        )

    # 5. MOF share-capture if available (rake 5-year steps, NOT annual)
    mof_county = pd.DataFrame()
    if use_mof_controls and county_name:
        mof_county = get_mof_county_projection(county_name)
        if not mof_county.empty:
            # Calculate current share
            mof_base = mof_county[mof_county["year"] == 2024]
            if not mof_base.empty:
                county_total = mof_base["total"].values[0]
                local_share = base["total"] / county_total if county_total > 0 else 0

                # Rake 5-year projection directly (MOF has annual, so
                # this only adjusts years that appear in both datasets)
                projection = share_capture_rake(
                    projection, mof_county, local_share, method=mof_method
                )

    # 6. Interpolate to annual AFTER raking (smooth curves, no kinks)
    if projection["year"].diff().max() > 1:
        projection = interpolate_annual(projection)

    # 7. Add derived metrics
    projection = calculate_derived_metrics(projection, avg_hh_size)

    # 8. Apply housing cap as FINAL constraint (after MOF raking + interpolation)
    #    Housing cap = max NEW units approved. Total stock = existing + cap.
    #    Max pop = (existing_stock + cap) × avg_hh_size
    if housing_cap > 0:
        housing_profile = get_census_housing_profile(sgc_code)
        current_stock = housing_profile.get("total_dwellings", 0) or 0
        max_units = current_stock + housing_cap
        max_pop = max_units * avg_hh_size

        over_cap = projection["total"] > max_pop
        if over_cap.any():
            for idx in projection[over_cap].index:
                row = projection.loc[idx]
                scale = max_pop / row["total"]
                projection.at[idx, "youth"] = round(row["youth"] * scale)
                projection.at[idx, "working"] = round(row["working"] * scale)
                projection.at[idx, "senior"] = round(row["senior"] * scale)
                projection.at[idx, "total"] = round(max_pop)
            # Recalculate derived metrics after capping
            projection = calculate_derived_metrics(projection, avg_hh_size)

    return {
        "projection": projection,
        "ccrs": ccrs,
        "census_history": census,
        "estimate_history": estimate_history,
        "mof_county": mof_county,
        "metadata": {
            "sgc_code": sgc_code,
            "county": county_name,
            "base_year": base_year,
            "end_year": end_year,
            "migration_factor": migration_factor,
            "aging_factor": aging_factor,
            "housing_cap": housing_cap,
            "avg_hh_size": avg_hh_size,
            "use_mof": use_mof_controls and not mof_county.empty,
            "rebased_from_estimate": not estimate_history.empty,
            "cohort_mode": cohort_mode,
        },
    }


# ========================================================================
#  PHASE 2 — HOUSING DEMAND PROJECTIONS
# ========================================================================

# Headship rates by age band (proportion of people who head a household).
# Source: Derived from 2021 Census — national averages, adjusted for rural.
HEADSHIP_RATES = {
    "youth": 0.0,     # 0–14 don't form households
    "working": 0.42,  # ~42% of 15–64 head a household (includes couples, singles)
    "senior": 0.62,   # ~62% of 65+ head a household (more single/couple HH)
}

# Ontario average HH size has been declining ~0.5% per 5-year Census period
HH_SIZE_DECLINE_RATE = 0.005  # per year


def get_census_housing_profile(sgc_code: str) -> dict:
    """
    Extract dwelling stock, tenure, and affordability indicators from Census data.

    Returns dict with current housing stock breakdown for the base year.
    """
    if not CENSUS_FILE.exists():
        return {}

    df = pd.read_csv(CENSUS_FILE)
    df["sgc_code"] = df["sgc_code"].astype(str).str.zfill(7)

    csd = df[(df["sgc_code"] == sgc_code)].copy()
    if csd.empty:
        return {}

    # Get the most recent Census year
    latest_year = csd["census_year"].max()
    latest = csd[csd["census_year"] == latest_year]

    # Pivot to indicator → value
    vals = dict(zip(latest["indicator"], latest["value"]))

    # Dwelling types
    dwelling_types = {
        "Single Detached": vals.get("dwelling_single_detached", 0),
        "Semi-Detached": vals.get("dwelling_semi_detached", 0),
        "Row House": vals.get("dwelling_row", 0),
        "Apt (5+ storeys)": vals.get("dwelling_apt_5plus", 0),
        "Apt (<5 storeys)": vals.get("dwelling_apt_under5", 0),
        "Movable": vals.get("dwelling_movable", 0),
    }

    total_dwellings = sum(v for v in dwelling_types.values() if pd.notna(v))

    # Tenure
    owners = vals.get("owner_households", 0)
    renters = vals.get("renter_households", 0)
    total_hh = (owners or 0) + (renters or 0)

    # Affordability
    profile = {
        "census_year": latest_year,
        "dwelling_types": dwelling_types,
        "total_dwellings": total_dwellings,
        "owner_households": owners or 0,
        "renter_households": renters or 0,
        "total_households": total_hh,
        "owner_pct": round(owners / total_hh * 100, 1) if total_hh > 0 else 0,
        "renter_pct": round(renters / total_hh * 100, 1) if total_hh > 0 else 0,
        "avg_hh_size": vals.get("avg_hh_size", 2.5),
        "shelter_cost_owned": vals.get("shelter_cost_owned", 0),
        "shelter_cost_rented": vals.get("shelter_cost_rented", 0),
        "unaffordable_owner_pct": vals.get("unaffordable_owner_pct", 0),
        "unaffordable_renter_pct": vals.get("unaffordable_renter_pct", 0),
        "major_repairs_needed": vals.get("major_repairs_needed", 0),
        "unsuitable_housing": vals.get("unsuitable_housing", 0),
        "subsidized_housing_pct": vals.get("subsidized_housing_pct", 0),
    }

    return profile


def project_housing_demand(
    projection_df: pd.DataFrame,
    base_hh_size: float = 2.5,
    vacancy_buffer: float = 0.03,
    hh_size_decline: bool = True,
    base_year: int = 2021,
    current_stock: int = 0,
    dwelling_types: dict = None,
) -> pd.DataFrame:
    """
    Convert population projections to housing unit demand.

    Methodology:
      1. Project avg household size (declining trend)
      2. Households = projected_pop / projected_hh_size
      3. Housing units needed = households / (1 - vacancy_rate)
      4. New units = units_needed - current_stock
      5. Unit mix based on age-structure headship rates

    Parameters:
      vacancy_buffer: healthy vacancy rate (3% default, CMHC standard)
      hh_size_decline: whether to project declining household sizes
      current_stock: existing dwelling count (from Census)
      dwelling_types: current dwelling mix for proportional projection
    """
    results = []

    for _, row in projection_df.iterrows():
        year = int(row["year"])
        years_elapsed = year - base_year

        # 1. Project declining household size
        if hh_size_decline and years_elapsed > 0:
            proj_hh_size = base_hh_size * (1 - HH_SIZE_DECLINE_RATE) ** years_elapsed
            proj_hh_size = max(1.8, proj_hh_size)  # Floor at 1.8 PPU
        else:
            proj_hh_size = base_hh_size

        # 2. Households from population
        pop = row["total"]
        households = pop / proj_hh_size

        # 3. Units needed (with vacancy buffer)
        units_needed = households / (1 - vacancy_buffer)

        # 4. New units required
        new_units = max(0, units_needed - current_stock)

        # 5. Headship-rate households by age band
        hh_youth = row.get("youth", 0) * HEADSHIP_RATES["youth"]
        hh_working = row.get("working", 0) * HEADSHIP_RATES["working"]
        hh_senior = row.get("senior", 0) * HEADSHIP_RATES["senior"]

        # Senior household share drives unit type demand
        senior_hh_share = hh_senior / max(1, hh_working + hh_senior) * 100

        results.append({
            "year": year,
            "population": int(pop),
            "proj_hh_size": round(proj_hh_size, 2),
            "households": round(households),
            "units_needed": round(units_needed),
            "new_units_from_base": round(new_units),
            "hh_working_age": round(hh_working),
            "hh_senior": round(hh_senior),
            "senior_hh_share_pct": round(senior_hh_share, 1),
        })

    return pd.DataFrame(results)


def project_dwelling_mix(
    housing_demand: pd.DataFrame,
    base_dwelling_types: dict,
    base_stock: int,
    senior_hh_shares: pd.Series = None,
) -> pd.DataFrame:
    """
    Project the dwelling type mix based on demand growth and age structure shifts.

    As senior share increases, more units shift toward apartments and smaller forms.
    """
    if not base_dwelling_types or base_stock <= 0:
        return pd.DataFrame()

    # Base proportions
    base_props = {k: v / base_stock for k, v in base_dwelling_types.items() if pd.notna(v) and v > 0}

    results = []
    for _, row in housing_demand.iterrows():
        units = row["units_needed"]
        senior_pct = row["senior_hh_share_pct"]

        # Shift factor: as senior HH share grows, shift from single-detached to apts
        # Base senior share is ~30%, each 1% above shifts 0.5% of units from SDH to apt
        base_senior_share = 30.0
        shift = max(0, (senior_pct - base_senior_share) * 0.005)

        adjusted = {}
        for dtype, prop in base_props.items():
            if "Single" in dtype or "Semi" in dtype:
                adjusted[dtype] = max(0, prop - shift / 2)
            elif "Apt" in dtype:
                adjusted[dtype] = prop + shift / 3
            else:
                adjusted[dtype] = prop

        # Normalize
        total_prop = sum(adjusted.values())
        if total_prop > 0:
            adjusted = {k: v / total_prop for k, v in adjusted.items()}

        entry = {"year": int(row["year"]), "total_units": round(units)}
        for dtype, prop in adjusted.items():
            entry[dtype] = round(units * prop)

        results.append(entry)

    return pd.DataFrame(results)


def calculate_bill23_gap(
    housing_demand: pd.DataFrame,
    provincial_target: int,
    target_year: int = 2031,
) -> dict:
    """
    Calculate the gap between provincial housing target and demographic demand.

    Bill 23 (More Homes Built Faster Act) assigned targets to many municipalities.
    This function compares demographic-driven demand against those targets.

    Returns dict with gap analysis metrics.
    """
    if housing_demand.empty or provincial_target <= 0:
        return {}

    # Find the target year in projections
    target_row = housing_demand[housing_demand["year"] == target_year]
    if target_row.empty:
        # Find closest year
        target_row = housing_demand.iloc[-1:]

    base_row = housing_demand.iloc[0]
    demand_units = int(target_row["new_units_from_base"].values[0])

    gap = provincial_target - demand_units
    gap_pct = (gap / provincial_target * 100) if provincial_target > 0 else 0

    # Reverse-engineer population needed to fill target naturally
    base_pop = int(base_row["population"])
    base_units = int(base_row["units_needed"])
    target_units = base_units + provincial_target
    avg_hh_size = base_row["proj_hh_size"]
    # Derive vacancy buffer from existing data (units_needed / households - 1)
    base_hh = base_row["households"]
    base_units = int(base_row["units_needed"])
    vacancy_used = 1.0 - (base_hh / base_units) if base_units > 0 else 0.03
    required_pop = target_units * avg_hh_size * (1 - vacancy_used)
    pop_growth_needed = required_pop - base_pop
    pop_growth_pct = (pop_growth_needed / base_pop * 100) if base_pop > 0 else 0

    years_to_target = target_year - int(base_row["year"])
    annual_units_demographic = demand_units / max(1, years_to_target)
    annual_units_target = provincial_target / max(1, years_to_target)

    return {
        "provincial_target": provincial_target,
        "target_year": target_year,
        "demographic_demand": demand_units,
        "gap": gap,
        "gap_pct": round(gap_pct, 1),
        "exceeds_demand": gap > 0,
        "annual_units_demographic": round(annual_units_demographic),
        "annual_units_target": round(annual_units_target),
        "pop_growth_needed": round(pop_growth_needed),
        "pop_growth_pct": round(pop_growth_pct, 1),
    }


def calculate_housing_metrics(
    scenario_result: dict,
    vacancy_rate: float = 0.03,
    provincial_target: int = 0,
    target_year: int = 2031,
) -> dict:
    """
    Master function: calculate all housing metrics from a scenario result.

    Returns dict with housing_demand, dwelling_mix, bill23_gap, housing_profile.
    """
    proj = scenario_result["projection"]
    meta = scenario_result["metadata"]
    sgc_code = meta["sgc_code"]

    # Get current housing profile
    profile = get_census_housing_profile(sgc_code)
    base_hh_size = profile.get("avg_hh_size", meta.get("avg_hh_size", 2.5))
    current_stock = profile.get("total_dwellings", 0)

    # Project housing demand
    housing_demand = project_housing_demand(
        proj,
        base_hh_size=base_hh_size,
        vacancy_buffer=vacancy_rate,
        base_year=meta["base_year"],
        current_stock=current_stock,
        dwelling_types=profile.get("dwelling_types"),
    )

    # Project dwelling mix
    dwelling_mix = project_dwelling_mix(
        housing_demand,
        base_dwelling_types=profile.get("dwelling_types", {}),
        base_stock=current_stock,
    )

    # Bill 23 gap analysis (if target provided)
    bill23 = {}
    if provincial_target > 0:
        bill23 = calculate_bill23_gap(housing_demand, provincial_target, target_year)

    return {
        "housing_demand": housing_demand,
        "dwelling_mix": dwelling_mix,
        "bill23_gap": bill23,
        "housing_profile": profile,
    }


# ========================================================================
#  PHASE 3 — INFRASTRUCTURE LOAD PROJECTIONS
# ========================================================================

# Ontario municipal benchmarks (per-capita or per-unit)
# Defaults below are overridden by config/scenario_assumptions.yaml if present.
_INFRA_DEFAULTS = {
    # Water & Wastewater
    "water_litres_per_capita_day": 220,         # Ontario avg residential ADD (MECP)
    "wastewater_litres_per_capita_day": 250,     # ~110% of water consumption ADD
    "mdd_peaking_factor": 2.0,                  # MECP Maximum Day Demand factor (typ. 1.5-2.5x ADD)
    "wastewater_treatment_pct_of_capacity": 80,  # typical design capacity threshold

    # Roads & Transit
    "vehicles_per_household": 1.7,               # rural Ontario avg
    "road_km_per_1000_pop": 8.5,                 # rural municipalities avg

    # Schools
    "elementary_enrollment_rate": 0.88,           # % of 5-13 enrolled (Ontario avg)
    "secondary_enrollment_rate": 0.92,            # % of 14-17 enrolled
    "elementary_students_per_school": 350,        # Ontario avg
    "secondary_students_per_school": 800,

    # Healthcare
    "er_visits_per_1000_senior": 650,             # Ontario avg 65+
    "er_visits_per_1000_working": 180,            # Ontario avg 15-64
    "er_visits_per_1000_youth": 220,              # Ontario avg 0-14
    "family_docs_per_1000_pop": 1.1,              # Ontario avg (CIHI)

    # Development Charges (FCM/Watson benchmarks, $/unit)
    "dc_per_unit_water": 12_500,
    "dc_per_unit_wastewater": 15_000,
    "dc_per_unit_roads": 8_000,
    "dc_per_unit_parks": 3_500,
    "dc_per_unit_fire_police": 2_500,
    "dc_per_unit_admin": 1_500,
}


def _load_yaml_benchmarks():
    """Load benchmarks from config/scenario_assumptions.yaml if it exists."""
    yaml_path = Path("config/scenario_assumptions.yaml")
    if not yaml_path.exists():
        return {}, {}
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg.get("infrastructure", {}), cfg.get("economics", {})
    except Exception:
        return {}, {}


_yaml_infra, _yaml_econ = _load_yaml_benchmarks()

# Merge: YAML values override defaults
INFRA_BENCHMARKS = {**_INFRA_DEFAULTS, **_yaml_infra}


def project_infrastructure_load(
    projection_df: pd.DataFrame,
    housing_demand_df: pd.DataFrame,
    avg_hh_size: float = 2.5,
    user_water_capacity: float = 0,     # m³/day
    user_ww_capacity: float = 0,        # m³/day
) -> pd.DataFrame:
    """
    Project infrastructure demands from population projection.

    Returns DataFrame with year-by-year infrastructure load estimates
    for water, wastewater, schools, healthcare, and roads.
    """
    results = []
    base_pop = projection_df.iloc[0]["total"]
    base_year = int(projection_df.iloc[0]["year"])

    for _, row in projection_df.iterrows():
        year = int(row["year"])
        pop = row["total"]
        youth = row["youth"]
        working = row["working"]
        senior = row["senior"]

        # --- Water & Wastewater ---
        # Average Daily Demand (ADD)
        water_add_lpd = pop * INFRA_BENCHMARKS["water_litres_per_capita_day"]
        water_add_m3d = water_add_lpd / 1000
        ww_add_lpd = pop * INFRA_BENCHMARKS["wastewater_litres_per_capita_day"]
        ww_add_m3d = ww_add_lpd / 1000

        # Maximum Day Demand (MDD) — MECP requires systems designed for MDD
        pf = INFRA_BENCHMARKS["mdd_peaking_factor"]
        water_mdd_m3d = water_add_m3d * pf
        ww_mdd_m3d = ww_add_m3d * pf

        # Capacity utilization uses MDD (if user provided capacity)
        water_util_pct = (water_mdd_m3d / user_water_capacity * 100) if user_water_capacity > 0 else 0
        ww_util_pct = (ww_mdd_m3d / user_ww_capacity * 100) if user_ww_capacity > 0 else 0

        # --- Schools ---
        # Youth band is 0-14, but school enrollment is ~5-17
        # Rough split: elementary (5-13) ≈ 60% of youth, secondary (14-17) ≈ 20% of youth + 10% working
        elementary_pop = youth * 0.60
        secondary_pop = youth * 0.20 + working * 0.04  # ~4% of working age are 15-17
        elementary_students = elementary_pop * INFRA_BENCHMARKS["elementary_enrollment_rate"]
        secondary_students = secondary_pop * INFRA_BENCHMARKS["secondary_enrollment_rate"]
        total_students = elementary_students + secondary_students
        schools_needed_elem = elementary_students / INFRA_BENCHMARKS["elementary_students_per_school"]
        schools_needed_sec = secondary_students / INFRA_BENCHMARKS["secondary_students_per_school"]

        # --- Healthcare ---
        er_visits_youth = youth / 1000 * INFRA_BENCHMARKS["er_visits_per_1000_youth"]
        er_visits_working = working / 1000 * INFRA_BENCHMARKS["er_visits_per_1000_working"]
        er_visits_senior = senior / 1000 * INFRA_BENCHMARKS["er_visits_per_1000_senior"]
        total_er_visits = er_visits_youth + er_visits_working + er_visits_senior
        family_docs_needed = pop / 1000 * INFRA_BENCHMARKS["family_docs_per_1000_pop"]

        # --- Roads ---
        est_hh = pop / avg_hh_size
        est_vehicles = est_hh * INFRA_BENCHMARKS["vehicles_per_household"]
        road_km_needed = pop / 1000 * INFRA_BENCHMARKS["road_km_per_1000_pop"]

        results.append({
            "year": year,
            "population": int(pop),
            # Water/WW (ADD = Average Daily, MDD = Maximum Day)
            "water_demand_m3d": round(water_add_m3d, 1),    # ADD for reference
            "water_mdd_m3d": round(water_mdd_m3d, 1),       # MDD for capacity planning
            "ww_demand_m3d": round(ww_add_m3d, 1),           # ADD for reference
            "ww_mdd_m3d": round(ww_mdd_m3d, 1),              # MDD for capacity planning
            "water_util_pct": round(water_util_pct, 1),      # % of capacity at MDD
            "ww_util_pct": round(ww_util_pct, 1),
            # Schools
            "elementary_students": round(elementary_students),
            "secondary_students": round(secondary_students),
            "total_students": round(total_students),
            "schools_needed_elem": round(schools_needed_elem, 1),
            "schools_needed_sec": round(schools_needed_sec, 1),
            # Healthcare
            "total_er_visits": round(total_er_visits),
            "er_visits_senior": round(er_visits_senior),
            "family_docs_needed": round(family_docs_needed, 1),
            # Roads
            "est_vehicles": round(est_vehicles),
            "road_km_needed": round(road_km_needed, 1),
        })

    return pd.DataFrame(results)


def calculate_development_charges(new_units: int) -> dict:
    """
    Estimate Development Charges for new housing units.

    Uses FCM/Watson municipal benchmarks for Southern Ontario.
    Returns charge breakdown and total per-unit and aggregate.
    """
    dc_components = {
        "Water": INFRA_BENCHMARKS["dc_per_unit_water"],
        "Wastewater": INFRA_BENCHMARKS["dc_per_unit_wastewater"],
        "Roads & Transit": INFRA_BENCHMARKS["dc_per_unit_roads"],
        "Parks & Recreation": INFRA_BENCHMARKS["dc_per_unit_parks"],
        "Fire & Police": INFRA_BENCHMARKS["dc_per_unit_fire_police"],
        "Administration": INFRA_BENCHMARKS["dc_per_unit_admin"],
    }

    total_per_unit = sum(dc_components.values())
    total_aggregate = total_per_unit * new_units

    return {
        "components": dc_components,
        "total_per_unit": total_per_unit,
        "new_units": new_units,
        "total_aggregate": total_aggregate,
    }


def calculate_infrastructure_metrics(
    scenario_result: dict,
    housing_metrics: dict,
    user_water_capacity: float = 0,
    user_ww_capacity: float = 0,
) -> dict:
    """
    Master function for Phase 3 infrastructure projections.
    """
    proj = scenario_result["projection"]
    meta = scenario_result["metadata"]
    avg_hh_size = meta.get("avg_hh_size", 2.5)

    h_demand = housing_metrics.get("housing_demand", pd.DataFrame())

    infra = project_infrastructure_load(
        proj, h_demand,
        avg_hh_size=avg_hh_size,
        user_water_capacity=user_water_capacity,
        user_ww_capacity=user_ww_capacity,
    )

    # Calculate DC estimate from latest housing demand
    new_units = 0
    if not h_demand.empty:
        new_units = int(h_demand.iloc[-1].get("new_units_from_base", 0))
    dc = calculate_development_charges(new_units)

    return {
        "infrastructure_load": infra,
        "development_charges": dc,
        "benchmarks": INFRA_BENCHMARKS,
    }


# ========================================================================
#  PHASE 4 — ECONOMIC IMPACT PROJECTIONS
# ========================================================================

# Ontario municipal economics benchmarks
# Defaults below are overridden by config/scenario_assumptions.yaml if present.
_ECON_DEFAULTS = {
    # Tax base
    "avg_assessment_per_unit": 350_000,          # Ontario avg residential CVA (frozen 2016 MPAC)
    "residential_mill_rate": 0.0085,             # ~0.85% typical
    "commercial_ratio": 1.8,                     # commercial/residential tax ratio

    # Labour force (from Census rates)
    "participation_rate_working": 0.65,           # 15-64 labour force participation
    "participation_rate_senior": 0.15,            # 65+ participation (growing)
    "unemployment_rate_default": 0.055,           # Ontario avg

    # Municipal operating costs per capita (FIR-sourced, excl. education & healthcare)
    # Source: Ontario Financial Information Return aggregate data
    # These cover: roads, water/sewer, fire/EMS, parks, planning, general government
    # NOT included: school boards (provincial), hospitals (LHIN/OH), social services (DSSAB)
    "service_cost_youth": 1_400,                  # recreation, parks, library
    "service_cost_working": 1_100,                # roads, transit, planning, admin
    "service_cost_senior": 2_200,                 # EMS, fire, transit, social housing

    # Economic multipliers
    "construction_jobs_per_100_units": 150,       # direct + indirect
    "construction_value_per_unit": 320_000,       # avg residential construction value
}

# Merge: YAML values override defaults
ECON_BENCHMARKS = {**_ECON_DEFAULTS, **_yaml_econ}


def project_economic_impact(
    projection_df: pd.DataFrame,
    housing_demand_df: pd.DataFrame = None,
    avg_hh_size: float = 2.5,
    local_mill_rate: float = 0,
    local_assessment: float = 0,
) -> pd.DataFrame:
    """
    Project economic impacts from population and housing demand projections.

    Covers: tax revenue, labour force, service costs, fiscal balance.
    """
    mill_rate = local_mill_rate if local_mill_rate > 0 else ECON_BENCHMARKS["residential_mill_rate"]
    avg_assessment = local_assessment if local_assessment > 0 else ECON_BENCHMARKS["avg_assessment_per_unit"]

    results = []
    base_pop = projection_df.iloc[0]["total"]
    base_year = int(projection_df.iloc[0]["year"])
    base_hh = base_pop / avg_hh_size

    for _, row in projection_df.iterrows():
        year = int(row["year"])
        pop = row["total"]
        youth = row["youth"]
        working = row["working"]
        senior = row["senior"]
        est_hh = pop / avg_hh_size

        # --- Tax Revenue ---
        residential_tax_base = est_hh * avg_assessment
        residential_tax_rev = residential_tax_base * mill_rate
        # Commercial typically ~20% of units at higher ratio
        commercial_rev = residential_tax_rev * 0.20 * ECON_BENCHMARKS["commercial_ratio"]
        total_tax_rev = residential_tax_rev + commercial_rev

        # --- Labour Force ---
        labour_force = (
            working * ECON_BENCHMARKS["participation_rate_working"]
            + senior * ECON_BENCHMARKS["participation_rate_senior"]
        )
        employed = labour_force * (1 - ECON_BENCHMARKS["unemployment_rate_default"])
        unemployed = labour_force - employed

        # --- Service Costs ---
        service_cost_total = (
            youth * ECON_BENCHMARKS["service_cost_youth"]
            + working * ECON_BENCHMARKS["service_cost_working"]
            + senior * ECON_BENCHMARKS["service_cost_senior"]
        )

        # --- Fiscal Balance ---
        fiscal_balance = total_tax_rev - service_cost_total
        fiscal_per_capita = fiscal_balance / max(1, pop)

        # --- Construction Economic Impact (from housing growth) ---
        new_hh = max(0, est_hh - base_hh)
        construction_value = new_hh * ECON_BENCHMARKS["construction_value_per_unit"]
        construction_jobs = new_hh / 100 * ECON_BENCHMARKS["construction_jobs_per_100_units"]

        results.append({
            "year": year,
            "population": int(pop),
            # Tax
            "residential_tax_base": round(residential_tax_base),
            "residential_tax_rev": round(residential_tax_rev),
            "total_tax_rev": round(total_tax_rev),
            "tax_rev_per_capita": round(total_tax_rev / max(1, pop)),
            # Labour
            "labour_force": round(labour_force),
            "employed": round(employed),
            "unemployed": round(unemployed),
            "participation_rate": round(labour_force / max(1, working + senior) * 100, 1),
            # Service Costs
            "service_cost_total": round(service_cost_total),
            "service_cost_per_capita": round(service_cost_total / max(1, pop)),
            # Fiscal
            "fiscal_balance": round(fiscal_balance),
            "fiscal_per_capita": round(fiscal_per_capita),
            # Construction
            "construction_value": round(construction_value),
            "construction_jobs": round(construction_jobs),
        })

    return pd.DataFrame(results)


def calculate_economic_metrics(
    scenario_result: dict,
    housing_metrics: dict,
    local_mill_rate: float = 0,
    local_assessment: float = 0,
) -> dict:
    """
    Master function for Phase 4 economic impact projections.
    """
    proj = scenario_result["projection"]
    meta = scenario_result["metadata"]
    avg_hh_size = meta.get("avg_hh_size", 2.5)
    h_demand = housing_metrics.get("housing_demand", pd.DataFrame())

    econ = project_economic_impact(
        proj, h_demand,
        avg_hh_size=avg_hh_size,
        local_mill_rate=local_mill_rate,
        local_assessment=local_assessment,
    )

    return {
        "economic_projection": econ,
        "benchmarks": ECON_BENCHMARKS,
    }

