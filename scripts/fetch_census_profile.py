"""
Multi-Year Census Profile Processor — Rural Ontario Wellbeing Dashboard
========================================================================

Processes Statistics Canada Census Profile bulk CSVs from 2006–2021 into a
unified time-series indicator dataset for the Wellbeing Dashboard.

Handles FOUR different CSV formats:
  - 2021 (98-401-X2021):  CHARACTERISTIC_NAME / ALT_GEO_CODE / C1_COUNT_TOTAL
  - 2016 (98-401-X2016):  DIM: Profile... / ALT_GEO_CODE / Dim: Sex Total
  - 2011 (98-316-XWE):    Characteristics / Geo_Code / Total   (header row 1)
  - 2006 (92-591-XE):     Characteristic / Geo_Code / Total    (header row 2)

SETUP:
    1. Download ZIPs from StatCan (one-time; Census updates every 5 years)
    2. Place all ZIPs in data/raw/
    3. Run:  python scripts/fetch_census_profile.py

OUTPUT:
    data/latest/wellbeing/census_indicators.csv  — Long format: year×community×indicator
    data/latest/wellbeing/dim_geography.csv      — SGC crosswalk (code→name, county, type)
"""

import os
import sys
import glob
import zipfile
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
OUT_DIR = os.path.join(BASE_DIR, "data", "latest", "wellbeing")

# ---------------------------------------------------------------------------
# Indicator Map — normalized indicator slugs
# Keys are characteristic names (lowercased, stripped) → slug
# We match case-insensitively because naming varies across Census years.
# ---------------------------------------------------------------------------
INDICATOR_MAP = {
    # -- Demographics --
    "population, 2021": "population",
    "population, 2016": "population",
    "population in 2016": "population",
    "population in 2011": "population",
    "population in 2006": "population",
    "population percentage change, 2016 to 2021": "pop_change_pct",
    "population percentage change, 2011 to 2016": "pop_change_pct",
    "2006 to 2011 population change (%)": "pop_change_pct",
    "2001 to 2006 population change (%)": "pop_change_pct",
    "population density per square kilometre": "pop_density",
    "land area in square kilometres": "land_area_sqkm",
    "land area (square km)": "land_area_sqkm",                    # 2006/2011
    # -- 5-year age cohorts (for true Hamilton-Perry diagonal survival) --
    "0 to 4 years": "cohort_0_4",
    "5 to 9 years": "cohort_5_9",
    "10 to 14 years": "cohort_10_14",
    "15 to 19 years": "cohort_15_19",
    "20 to 24 years": "cohort_20_24",
    "25 to 29 years": "cohort_25_29",
    "30 to 34 years": "cohort_30_34",
    "35 to 39 years": "cohort_35_39",
    "40 to 44 years": "cohort_40_44",
    "45 to 49 years": "cohort_45_49",
    "50 to 54 years": "cohort_50_54",
    "55 to 59 years": "cohort_55_59",
    "60 to 64 years": "cohort_60_64",
    "65 to 69 years": "cohort_65_69",
    "70 to 74 years": "cohort_70_74",
    "75 to 79 years": "cohort_75_79",
    "80 to 84 years": "cohort_80_84",
    "85 years and over": "cohort_85_plus",
    "average age of the population": "avg_age",
    "median age of the population": "median_age",

    # -- Income --
    # 2021
    "median total income of household in 2020 ($)": "median_hh_income",
    "median after-tax income of household in 2020 ($)": "median_hh_income_at",
    "prevalence of low income based on the low-income measure, after tax (lim-at) (%)": "low_income_pct",
    # 2016
    "median total income of households in 2015 ($)": "median_hh_income",
    "median after-tax income of households in 2015 ($)": "median_hh_income_at",
    # 2011 (NHS; may not be in Census Profile file)
    "median household total income ($)": "median_hh_income",
    "median after-tax household income ($)": "median_hh_income_at",           # FIX: 2011 NHS word order
    "prevalence of low income in 2010 based on after-tax low-income measure (%)": "low_income_pct",  # FIX: 2010 not 2005
    # 2006
    "median household total income $": "median_hh_income",
    "median income in 2005 - all private households ($)": "median_hh_income",  # 2006 variant
    "median after-tax income in 2005 - all private households ($)": "median_hh_income_at",  # 2006
    "incidence of low income in 2005 (%)": "low_income_pct",
    "% in low income after tax - all persons": "low_income_pct",    # 2006 variant

    # -- Housing --
    "owner": "owner_households",
    "renter": "renter_households",
    "number of owned dwellings": "owner_households",               # 2006
    "number of rented dwellings": "renter_households",             # 2006
    "average household size": "avg_hh_size",
    "average number of persons in private households": "avg_hh_size",  # 2011
    # P0 FIX U2: Split median and average shelter costs into separate slugs
    "median monthly shelter costs for owned dwellings ($)": "shelter_cost_owned_med",
    "median monthly shelter costs for rented dwellings ($)": "shelter_cost_rented_med",
    "average monthly shelter costs for owned dwellings ($)": "shelter_cost_owned_avg",
    "average monthly shelter costs for rented dwellings ($)": "shelter_cost_rented_avg",
    "median monthly payments for owner-occupied dwellings ($)": "shelter_cost_owned_med",  # 2006
    "median monthly payments for rented dwellings ($)": "shelter_cost_rented_med",        # 2006
    "% of tenant households in subsidized housing": "subsidized_housing_pct",
    # FIX H6: 2016/2021 affordability strings
    "% of tenant households spending 30% or more of its income on shelter costs": "unaffordable_renter_pct",
    "% of owner households spending 30% or more of its income on shelter costs": "unaffordable_owner_pct",
    # FIX H6: 2011 NHS affordability strings ("household total income" variant)
    "% of tenant households spending 30% or more of household total income on shelter costs": "unaffordable_renter_pct",
    "% of owner households spending 30% or more of household total income on shelter costs": "unaffordable_owner_pct",
    "major repairs needed": "major_repairs_needed",
    "dwellings requiring major repair - as a % of total occupied private dwellings": "major_repairs_pct",  # 2006 (helper for H5 synthesis)
    "not suitable": "unsuitable_housing",
    "in core housing need": "core_housing_need",
    "in core need": "core_housing_need",                                              # FIX H2: 2021 string
    "% in core housing need": "core_housing_need_pct",
    "average value of owned dwelling ($)": "avg_dwelling_value",    # 2006
    "average value of dwellings ($)": "avg_dwelling_value",        # FIX H4: 2011/2016/2021
    "average value of dwelling ($)": "avg_dwelling_value",         # FIX H4: 2011 NHS variant
    # N1: Crowding proxies (replaces non-existent avg_persons_per_room)
    "more than one person per room": "crowding_above_1ppr",
    "more than 1 person per room": "crowding_above_1ppr",              # FIX N4: 2016 uses digit "1"
    "average number of rooms per dwelling": "avg_rooms_per_dwelling",
    # FIX N6: 2006 crowding percentage helper (for back-calculation synthesis)
    "dwellings with more than one person per room - as a % of total occupied private dwellings": "_crowding_above_1ppr_pct",
    # N2: Median dwelling value
    "median value of dwellings ($)": "median_dwelling_value",

    # -- Education --
    "no certificate, diploma or degree": "no_education",
    "secondary (high) school diploma or equivalency certificate": "high_school",
    "high (secondary) school diploma or equivalency certificate": "high_school",  # 2021 (FIX E1)
    "high school certificate or equivalent": "high_school",
    "high school diploma or equivalent": "high_school",                            # 2011 NHS (FIX E2)
    "postsecondary certificate, diploma or degree": "postsecondary",
    "apprenticeship or trades certificate or diploma": "trades_cert",
    "college, cegep or other non-university certificate or diploma": "college_cert",
    "university certificate, diploma or degree at bachelor level or above": "uni_bachelor_plus",
    "bachelor's degree or higher": "uni_bachelor_plus",                            # 2021 (FIX E3)
    "university certificate or diploma above bachelor level": "uni_above_bachelor",
    "university certificate, diploma or degree above bachelor level": "uni_above_bachelor",  # 2011 (FIX E4)
    "university certificate, diploma or degree": "uni_bachelor_plus",              # 2006 (sibling, not parent — confirmed R3)
    "bachelor's degree": "uni_bachelor",                                            # 2021 (new indicator)

    # -- Commuting --
    "car, truck or van - as a driver": "commute_driver",
    "car, truck, van - as a driver": "commute_driver",
    "car, truck or van - as a passenger": "commute_passenger",
    "car, truck, van - as a passenger": "commute_passenger",
    "car, truck, van, as driver": "commute_driver",                # 2006
    "car, truck, van, as passenger": "commute_passenger",          # 2006
    "public transit": "commute_transit",
    "walked": "commute_walk",
    "bicycle": "commute_bike",
    "walked or bicycled": "commute_walk_bike",                     # 2006 (combined)

    # -- Labour Force --
    "in the labour force": "in_labour_force",
    "employed": "employed",
    "unemployed": "unemployed",
    "not in the labour force": "not_in_labour_force",
    "participation rate": "participation_rate",
    "employment rate": "employment_rate",
    "unemployment rate": "unemployment_rate",

    # -- Diversity --
    "total visible minority population": "visible_minority",
    "aboriginal identity": "indigenous_pop",
    "aboriginal identity population": "indigenous_pop",            # 2006
    "indigenous identity": "indigenous_pop",                        # 2021 (FIX F1)
    "immigrants": "immigrant_pop",
    "non-immigrants": "non_immigrant_pop",

    # -- Language --
    "english only": "lang_english_only",
    "french only": "lang_french_only",
    "english and french": "lang_bilingual",
    "neither english nor french": "lang_neither",

    # -- Housing stock --
    "single-detached house": "dwelling_single_detached",
    "semi-detached house": "dwelling_semi_detached",
    "row house": "dwelling_row",
    "apartment in a building that has five or more storeys": "dwelling_apt_5plus",
    "apartment, building that has five or more storeys": "dwelling_apt_5plus",      # 2011
    "apartment in a building that has fewer than five storeys": "dwelling_apt_under5",
    "apartment, building that has fewer than five storeys": "dwelling_apt_under5",  # 2011
    "movable dwelling": "dwelling_movable",
    "apartment or flat in a duplex": "dwelling_duplex",
    "apartment, duplex": "dwelling_duplex",                                        # FIX H8: 2011
    "private dwellings occupied by usual residents": "dwellings_occupied",
    # FIX H7: 2006 percentage-based dwelling type strings (helpers for synthesis)
    "single-detached houses - as a % of total occupied private dwellings": "_dwelling_single_detached_pct",
    "semi-detached houses - as a % of total occupied private dwellings": "_dwelling_semi_detached_pct",
    "row houses - as a % of total occupied private dwellings": "_dwelling_row_pct",
    "apartments in buildings with five or more storeys - as a % of total occupied private dwellings": "_dwelling_apt_5plus_pct",
    "apartments in buildings with fewer than five storeys - as a % of total occupied private dwellings": "_dwelling_apt_under5_pct",
    "apartments, duplex - as a % of total occupied private dwellings": "_dwelling_duplex_pct",
    "other dwellings - as a % of total occupied private dwellings": "_dwelling_movable_pct",

    # -- Household Size Distribution --
    "1 person": "hh_size_1",
    "2 persons": "hh_size_2",
    "3 persons": "hh_size_3",
    "4 persons": "hh_size_4",
    "5 or more persons": "hh_size_5_plus",
    # FIX H10: 2011 splits 5+ into separate categories (helpers for synthesis)
    "5 persons": "_hh_5_persons",
    "6 or more persons": "_hh_6_plus_persons",

    # -- Shelter Affordability --
    "spending 30% or more of income on shelter costs": "unaffordable_shelter",
    "spending less than 30% of income on shelter costs": "affordable_shelter",
    # FIX H6: 2011 NHS variants ("household total income")
    "spending 30% or more of household total income on shelter costs": "unaffordable_shelter",
    "spending less than 30% of household total income on shelter costs": "affordable_shelter",

    # -- Household Income Distribution --
    # REMOVED from generic map — extracted via _extract_income_bands()
    # to target the household AFTER-TAX section specifically.

    # -- Commuting Duration --
    "less than 15 minutes": "commute_lt_15min",                                    # (recommended addition)
    "45 to 59 minutes": "commute_45_59min",
    "60 minutes and over": "commute_60min_plus",

    # -- Commuting Destination --
    "commute within census subdivision (csd) of residence": "commute_local",
    "worked in census subdivision of residence": "commute_local",                   # 2006/2011 variant (FIX C2)
    "worked in census subdivision (municipality) of residence": "commute_local",    # 2006 parenthetical (FIX Q1)
    "commute to a different census subdivision (csd) within census division (cd) of residence": "commute_diff_csd",
    "worked in a different census subdivision (municipality) within the census division (county) of residence": "commute_diff_csd",  # 2006 (FIX Q3)
    "worked at home": "commute_wfh",

    # -- Religion --
    "no religion and secular perspectives": "no_religion",
    "no religious affiliation": "no_religion",                     # 2011 NHS (FIX F3)
}

# ---------------------------------------------------------------------------
# Household After-Tax Income Distribution — contextual extraction
# ---------------------------------------------------------------------------
# Census Profile CSVs contain MULTIPLE income distribution sections
# (individual total, individual after-tax, employment, HH total, HH after-tax).
# We specifically target the HOUSEHOLD AFTER-TAX section by detecting its
# header row, then extracting only the bands within that section.
#
# Band structures differ by year:
#   2021: $5K sub-bands below $50K; $10K bands $50K-$100K; $100K-$125K,
#         $125K-$150K, $150K-$200K, $200K+ above
#   2016: same $5K sub-bands; $100K-$125K, $125K-$150K, $150K+ above
#   2011 NHS: $10K bands throughout; $100K+ aggregate only
#   2006: $10K bands; $100K+ aggregate only (different header)
# ---------------------------------------------------------------------------

# Header patterns to detect the household after-tax income section.
# Split into two groups based on matching strategy:
#   - PREFIXED: Match when row starts with "total - " AND contains the substring
#               (2016/2021 headers: "Total - Household after-tax income groups...")
#   - STARTS_WITH: Match when row directly starts with the substring
#               (2011 NHS: "After-tax income of households in 2010...")
# This split prevents false matches on rows like "Median after-tax income of
# households..." which contain the 2011 substring but aren't section headers.
INCOME_SECTION_HEADERS_PREFIXED = [
    "household after-tax income groups",      # 2021, 2016
    "after-tax income of private households", # 2006 variant
]
INCOME_SECTION_HEADERS_STARTSWITH = [
    "after-tax income of households",         # 2011 NHS
]

# Map Census characteristic names → our 14-band slugs.
# $5K sub-bands are aggregated into $10K bins in post-processing.
INCOME_BAND_MAP = {
    # -- Under $10K (including $5K sub-bands for 2016/2021) --
    "under $5,000":                       "hh_income_under_10k",
    "$5,000 to $9,999":                   "hh_income_under_10k",
    "under $10,000":                      "hh_income_under_10k",   # 2006/2011
    "under $10,000 (including loss)":     "hh_income_under_10k",   # if in HH section
    # -- $10K–$20K --
    "$10,000 to $14,999":                 "hh_income_10k_20k",
    "$15,000 to $19,999":                 "hh_income_10k_20k",
    "$10,000 to $19,999":                 "hh_income_10k_20k",     # 2006/2011
    # -- $20K–$30K --
    "$20,000 to $24,999":                 "hh_income_20k_30k",
    "$25,000 to $29,999":                 "hh_income_20k_30k",
    "$20,000 to $29,999":                 "hh_income_20k_30k",     # 2006/2011
    # -- $30K–$40K --
    "$30,000 to $34,999":                 "hh_income_30k_40k",
    "$35,000 to $39,999":                 "hh_income_30k_40k",
    "$30,000 to $39,999":                 "hh_income_30k_40k",     # 2006/2011
    # -- $40K–$50K --
    "$40,000 to $44,999":                 "hh_income_40k_50k",
    "$45,000 to $49,999":                 "hh_income_40k_50k",
    "$40,000 to $49,999":                 "hh_income_40k_50k",     # 2006/2011
    # -- $50K–$60K --
    "$50,000 to $59,999":                 "hh_income_50k_60k",
    # -- $60K–$70K --
    "$60,000 to $69,999":                 "hh_income_60k_70k",
    # -- $70K–$80K --
    "$70,000 to $79,999":                 "hh_income_70k_80k",
    # -- $80K–$90K --
    "$80,000 to $89,999":                 "hh_income_80k_90k",
    # -- $90K–$100K --
    "$90,000 to $99,999":                 "hh_income_90k_100k",
    # -- $100K–$125K --
    "$100,000 to $124,999":               "hh_income_100k_125k",
    # -- $125K–$150K --
    "$125,000 to $149,999":               "hh_income_125k_150k",
    # -- $150K–$200K --
    "$150,000 to $199,999":               "hh_income_150k_200k",
    # -- $200K+ --
    "$200,000 and over":                  "hh_income_200k_plus",
    # -- $150K+ aggregate (2016/2021 after-tax: no $150K-$200K / $200K+ split) --
    "$150,000 and over":                  "hh_income_150k_plus",
    # -- Aggregate high-income (2011: "$100,000 and over") --
    # This is a PARENT row in years that have child splits.
    # If children are missing (2011 NHS), handled by fallback in _extract_income_bands.
}



def _normalize(s):
    """Lowercase, strip whitespace for matching."""
    return str(s).strip().lower()


# ---------------------------------------------------------------------------
# Year-specific loaders
# ---------------------------------------------------------------------------

def _load_2021(zip_path):
    """2021 Census Profile: CHARACTERISTIC_NAME / ALT_GEO_CODE / C1_COUNT_TOTAL"""
    print(f"  Loading 2021 from {os.path.basename(zip_path)}...")
    with zipfile.ZipFile(zip_path, "r") as z:
        csv_name = next(f for f in z.namelist() if f.endswith("_data.csv"))
        with z.open(csv_name) as f:
            df = pd.read_csv(f, low_memory=False, encoding="latin-1")

    return _extract_long(df, 2021,
                         char_col="CHARACTERISTIC_NAME",
                         geo_col="ALT_GEO_CODE",
                         val_col="C1_COUNT_TOTAL",
                         name_col="GEO_NAME",
                         level_col="GEO_LEVEL")


def _load_2016(zip_path):
    """2016 Census Profile: DIM: Profile... / ALT_GEO_CODE / Dim: Sex Total"""
    print(f"  Loading 2016 from {os.path.basename(zip_path)}...")
    with zipfile.ZipFile(zip_path, "r") as z:
        csv_name = next(f for f in z.namelist() if f.endswith("_data.csv"))
        with z.open(csv_name) as f:
            df = pd.read_csv(f, low_memory=False, encoding="latin-1")

    # Find the characteristic column (contains "DIM: Profile")
    char_col = next(c for c in df.columns if "DIM:" in c and "Profile" in c)
    # Value column: "Dim: Sex (3): Member ID: [1]: Total - Sex"
    val_col = next(c for c in df.columns if "Total - Sex" in c)

    return _extract_long(df, 2016,
                         char_col=char_col,
                         geo_col="ALT_GEO_CODE",
                         val_col=val_col,
                         name_col="GEO_NAME")


def _load_2011(zip_path):
    """2011 Census Profile: Characteristics / Geo_Code / Total (header=1)"""
    print(f"  Loading 2011 from {os.path.basename(zip_path)}...")
    with zipfile.ZipFile(zip_path, "r") as z:
        csv_name = next(f for f in z.namelist()
                        if f.endswith(".CSV") and "Metadata" not in f and "DQ" not in f)
        with z.open(csv_name) as f:
            df = pd.read_csv(f, low_memory=False, encoding="latin-1", header=1)

    # Filter to Ontario only (SGC codes starting with 35)
    df["Geo_Code"] = df["Geo_Code"].astype(str).str.strip()
    before = len(df)
    df = df[df["Geo_Code"].str.startswith("35")].copy()
    print(f"    Filtered {before:,} -> {len(df):,} rows (Ontario only)")

    return _extract_long(df, 2011,
                         char_col="Characteristics",
                         geo_col="Geo_Code",
                         val_col="Total",
                         name_col="CSD_Name",
                         cd_col="CD_Name",
                         type_col="CSD_Type")


def _load_2011_nhs(zip_path):
    """2011 National Household Survey (NHS): per-province CSVs inside ZIP.

    The NHS contains income, labour, education, housing cost, commuting,
    immigration, and visible minority indicators that were NOT in the
    2011 Census short-form.

    Structure differs from Census Profile:
      - ZIP contains one CSV per province (e.g., *-ONT.csv)
      - Header at row 0 (not row 1 like Census Profile)
      - Columns: Geo_Code, Characteristic (singular), Total, etc.
    """
    print(f"  Loading 2011 NHS from {os.path.basename(zip_path)}...")
    with zipfile.ZipFile(zip_path, "r") as z:
        # Find Ontario-specific CSV (file per province)
        ont_files = [
            f for f in z.namelist()
            if f.lower().endswith(".csv")
            and ("-ont" in f.lower() or "ontario" in f.lower())
            and "metadata" not in f.lower()
        ]
        if not ont_files:
            # Fallback: try any non-metadata CSV
            ont_files = [
                f for f in z.namelist()
                if f.lower().endswith(".csv")
                and "metadata" not in f.lower()
                and "dq" not in f.lower()
            ]
        if not ont_files:
            print(f"    [WARNING] No Ontario CSV found in {os.path.basename(zip_path)}")
            return pd.DataFrame(), pd.DataFrame()
        csv_name = ont_files[0]
        print(f"    Reading: {csv_name}")
        with z.open(csv_name) as f:
            # NHS has headers at row 0 (unlike Census Profile which uses row 1)
            df = pd.read_csv(f, low_memory=False, encoding="latin-1")

    print(f"    Read {len(df):,} rows, {len(df.columns)} columns")

    # Already Ontario-only (province-specific file), but SGC starts with 35
    # No additional province filtering needed

    return _extract_long(df, 2011,
                         char_col="Characteristic",
                         geo_col="Geo_Code",
                         val_col="Total",
                         name_col="CSD_Name",
                         cd_col="CD_Name",
                         type_col="CSD_type")



def _find_column(df, candidates, required=True):
    """Find the first matching column name from a list of candidates."""
    for col in candidates:
        if col in df.columns:
            return col
    # Case-insensitive fallback
    lower_map = {c.lower().strip(): c for c in df.columns}
    for col in candidates:
        if col.lower().strip() in lower_map:
            return lower_map[col.lower().strip()]
    if required:
        print(f"    [WARNING] None of {candidates} found in columns")
    return None


def _load_2006(zip_path):
    """2006 Community Profiles: Characteristic / Geo_Code / Total (skiprows=2, Ontario file)"""
    print(f"  Loading 2006 from {os.path.basename(zip_path)}...")
    with zipfile.ZipFile(zip_path, "r") as z:
        # Use the Ontario-specific file
        ont_file = next(f for f in z.namelist() if "ONT" in f.upper())
        with z.open(ont_file) as f:
            df = pd.read_csv(f, low_memory=False, encoding="utf-8-sig",
                             skiprows=2, on_bad_lines="skip",
                             index_col=False)

    # Filter out notes rows (Geo_Code is numeric for real data)
    df["Geo_Code"] = df["Geo_Code"].astype(str).str.strip()
    df = df[df["Geo_Code"].str.match(r"^\d{7}$")].copy()
    print(f"    Loaded {len(df):,} rows (Ontario CSDs)")

    return _extract_long(df, 2006,
                         char_col="Characteristic",
                         geo_col="Geo_Code",
                         val_col="Total",
                         name_col="CSD_Name",
                         cd_col="CD_Name",
                         type_col="CSD_Type")


# ---------------------------------------------------------------------------
# Income band extraction — contextual section detection
# ---------------------------------------------------------------------------

def _extract_income_bands(df, year, char_col, geo_col, val_col):
    """
    Extract household after-tax income distribution bands using
    contextual section detection.

    Instead of relying on characteristic names alone (which repeat
    across individual/household and before-tax/after-tax sections),
    we find the section header row and only extract bands that
    appear within that section.

    N1 FIX: Uses groupby(geo_col) so the section_active state machine
    runs independently per CSD, preventing cross-CSD state bleeding
    if CSDs are interleaved in the CSV.

    N3 FIX: Also extracts the section header "Total" row as
    hh_income_total to provide a true denominator for percentages.

    Returns a DataFrame with columns: census_year, sgc_code, indicator, value
    (aggregated from $5K sub-bands into $10K slugs where needed).
    """
    df = df.copy()
    df["_char_norm"] = df[char_col].apply(_normalize)

    # --- Step 1: Find rows that belong to the HH after-tax section ---
    # N1 FIX: Process per-CSD to prevent state bleeding across geographies.
    # Each CSD gets its own section_active flag, so interleaved data is safe.
    section_indices = []    # Indices of band rows within the section
    total_indices = []      # Indices of the "Total" header row (for N3 denominator)

    for _geo_code, geo_group in df.groupby(geo_col):
        section_active = False
        section_found = False  # Lock: only extract the FIRST matching section per CSD
        for idx in geo_group.index:
            char_norm = geo_group.at[idx, "_char_norm"]
            # Check if this is the start of the HH after-tax section.
            # Only match if we haven't already found the aggregate section.
            # This prevents capturing demographic sub-sections (e.g.,
            # "one-person households", "two-or-more-person households")
            # whose headers also match substrings of our target headers.
            #
            # Two matching strategies:
            # 1. PREFIXED: Row starts with "total - " AND contains a target
            #    substring (catches 2016/2021 headers)
            # 2. STARTS_WITH: Row directly starts with the target substring
            #    (catches 2011 NHS which lacks "Total - " prefix)
            is_header = False
            if not section_found:
                if (char_norm.startswith("total - ")
                        and any(h in char_norm for h in INCOME_SECTION_HEADERS_PREFIXED)):
                    is_header = True
                elif any(char_norm.startswith(h) for h in INCOME_SECTION_HEADERS_STARTSWITH):
                    is_header = True
            if is_header:
                section_active = True
                section_found = True  # Lock out subsequent sub-section matches
                # N3 FIX: The header row itself contains the "Total" count
                # (e.g., "Total - Household after-tax income groups  2,345")
                # We extract it as the true denominator for percentage calc.
                total_indices.append(idx)
                continue  # Skip the header row from band extraction
            # Check if we've left the section (next "Total -" header)
            if section_active and char_norm.startswith("total -"):
                section_active = False
                continue
            if section_active:
                section_indices.append(idx)

    section_df = df.loc[section_indices].copy() if section_indices else pd.DataFrame(columns=df.columns)
    if section_df.empty:
        print(f"    [INCOME] No household after-tax income section found for {year}")
        return pd.DataFrame(columns=["census_year", "sgc_code", "indicator", "value"])

    # --- Step 1b: Extract total-households from section header (N3 FIX) ---
    total_rows_list = []
    if total_indices:
        total_df = df.loc[total_indices].copy()
        total_df["value"] = pd.to_numeric(total_df[val_col], errors="coerce")
        total_df["census_year"] = year
        _geo_raw = pd.to_numeric(total_df[geo_col], errors="coerce")
        _geo_int = _geo_raw.dropna().astype("int64").astype(str).str.zfill(7)
        total_df["sgc_code"] = _geo_int.reindex(total_df.index, fill_value="0000000")
        total_df["indicator"] = "hh_income_total"
        total_rows_list.append(total_df[["census_year", "sgc_code", "indicator", "value"]].copy())
        print(f"    [INCOME] {year}: extracted {len(total_df)} total-household rows for denominator")

    # --- Step 2: Map band names to our slugs ---
    section_df["indicator"] = section_df["_char_norm"].map(INCOME_BAND_MAP)
    matched = section_df.dropna(subset=["indicator"]).copy()
    matched["value"] = pd.to_numeric(matched[val_col], errors="coerce")
    matched["census_year"] = year

    # Normalize SGC codes
    _geo_raw = pd.to_numeric(matched[geo_col], errors="coerce")
    _geo_int = _geo_raw.dropna().astype("int64").astype(str).str.zfill(7)
    matched["sgc_code"] = _geo_int.reindex(matched.index, fill_value="0000000")

    # --- Step 3: Aggregate $5K sub-bands into $10K bins ---
    # The INCOME_BAND_MAP maps two $5K sub-bands to the same slug
    # (e.g., "$10,000 to $14,999" and "$15,000 to $19,999" both → hh_income_10k_20k).
    # Sum them per CSD.
    result = (
        matched
        .groupby(["census_year", "sgc_code", "indicator"], as_index=False)["value"]
        .sum()
    )

    # --- Step 4: Handle 2011 NHS "$100,000 and over" aggregate ---
    # If the fine $100K+ split bands are missing (2011 NHS only has aggregate),
    # check whether we got ANY of the $100K+ sub-bands. If not, the "$100,000
    # and over" row wasn't in INCOME_BAND_MAP — we handle it here.
    hk_slugs = ["hh_income_100k_125k", "hh_income_125k_150k",
                "hh_income_150k_200k", "hh_income_200k_plus"]
    has_fine_split = result["indicator"].isin(hk_slugs).any()
    if not has_fine_split:
        # Look for the aggregate "$100,000 and over" row in the section
        agg_mask = section_df["_char_norm"].str.contains("100,000 and over", na=False)
        agg_rows = section_df[agg_mask].copy()
        if not agg_rows.empty:
            agg_rows["value"] = pd.to_numeric(agg_rows[val_col], errors="coerce")
            agg_rows["census_year"] = year
            _geo_raw = pd.to_numeric(agg_rows[geo_col], errors="coerce")
            _geo_int = _geo_raw.dropna().astype("int64").astype(str).str.zfill(7)
            agg_rows["sgc_code"] = _geo_int.reindex(agg_rows.index, fill_value="0000000")
            agg_rows["indicator"] = "hh_income_100k_plus"
            agg_append = agg_rows[["census_year", "sgc_code", "indicator", "value"]].copy()
            result = pd.concat([result, agg_append], ignore_index=True)
            print(f"    [INCOME] {year}: using aggregate $100K+ band (no fine split available)")

    # --- Step 5: Append total-household rows ---
    if total_rows_list:
        result = pd.concat([result] + total_rows_list, ignore_index=True)

    n_bands = result[result["indicator"] != "hh_income_total"]["indicator"].nunique()
    n_geos = result["sgc_code"].nunique()
    print(f"    [INCOME] {year}: extracted {len(result):,} rows -> {n_bands} bands x {n_geos} communities")

    return result


# ---------------------------------------------------------------------------
# Common extraction logic
# ---------------------------------------------------------------------------

def _extract_long(df, year, char_col, geo_col, val_col,
                  name_col=None, cd_col=None, type_col=None, level_col=None):
    """
    Extract indicators from a Census Profile DataFrame in long format.
    Returns (indicators_df, geo_df).
    """
    # Normalize SGC codes to 7-digit strings
    # Guard against float parsing: 3523008.0 → "3523008.0" → bad zfill
    # Convert through numeric → Int64 to strip .0 suffix safely
    _geo_raw = pd.to_numeric(df[geo_col], errors="coerce")
    _geo_int = _geo_raw.dropna().astype("int64").astype(str).str.zfill(7)
    df["sgc_code"] = _geo_int.reindex(df.index, fill_value="0000000")

    # Match characteristics to our indicator map (excludes income bands)
    df["_char_norm"] = df[char_col].apply(_normalize)
    df["indicator"] = df["_char_norm"].map(INDICATOR_MAP)

    matched = df.dropna(subset=["indicator"]).copy()
    n_indicators = matched["indicator"].nunique()
    n_geos = matched["sgc_code"].nunique()
    print(f"    Matched {len(matched):,} rows -> {n_indicators} indicators x {n_geos} geographies")

    # Convert value to numeric
    matched["value"] = pd.to_numeric(matched[val_col], errors="coerce")
    matched["census_year"] = year

    # Build indicator result
    indicators = matched[["census_year", "sgc_code", "indicator", "value"]].copy()
    # Deduplicate (some characteristics appear in multiple sections)
    indicators = indicators.drop_duplicates(subset=["census_year", "sgc_code", "indicator"], keep="first")

    # --- Extract household after-tax income bands (contextual) ---
    income_bands = _extract_income_bands(df, year, char_col, geo_col, val_col)
    if not income_bands.empty:
        indicators = pd.concat([indicators, income_bands], ignore_index=True)

    # Build geography dimension
    geo_data = {"sgc_code": df["sgc_code"]}
    if name_col and name_col in df.columns:
        geo_data["geo_name"] = df[name_col]
    if cd_col and cd_col in df.columns:
        geo_data["county"] = df[cd_col]
    if type_col and type_col in df.columns:
        geo_data["csd_type"] = df[type_col]
    if level_col and level_col in df.columns:
        geo_data["geo_level"] = df[level_col]

    geo_df = pd.DataFrame(geo_data).drop_duplicates(subset=["sgc_code"]).reset_index(drop=True)

    return indicators, geo_df


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

# Map file patterns → loader functions
FILE_LOADERS = [
    ("98-401-X2021*_eng_CSV*.zip", _load_2021),
    ("98-401-X2016*_eng_CSV*.zip", _load_2016),
    ("98-316-XWE2011*_CSV*.zip",   _load_2011),
    ("99-004-XWE2011*_CSV*.zip",   _load_2011_nhs),  # 2011 NHS (income, labour, education, etc.)
    ("92-591-XE*_CSV*.zip",        _load_2006),
]

# CRITICAL ENFORCEMENT: 100% Census MUST precede 30% NHS to ensure global
# deduplication (keep="first") retains the higher-quality mandatory data.
_loader_names = [func.__name__ for _pattern, func in FILE_LOADERS]
if "_load_2011" in _loader_names and "_load_2011_nhs" in _loader_names:
    assert _loader_names.index("_load_2011") < _loader_names.index("_load_2011_nhs"), \
        "ETL FATAL: _load_2011 must appear before _load_2011_nhs in FILE_LOADERS."


def discover_files():
    """Find all Census Profile ZIPs in data/raw/."""
    os.makedirs(RAW_DIR, exist_ok=True)
    found = []
    for pattern, loader in FILE_LOADERS:
        matches = glob.glob(os.path.join(RAW_DIR, pattern))
        if matches:
            found.append((matches[0], loader))
    return found


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    """Main entry point — process all available Census years."""
    print("=" * 60)
    print("Multi-Year Census Profile Processor")
    print("Rural Ontario Wellbeing Dashboard")
    print("=" * 60)

    files = discover_files()
    if not files:
        print(
            "\n  No Census Profile ZIPs found in data/raw/\n"
            "\n  Please download from StatCan and place in data/raw/:"
            "\n  - 2021: Census Profile -> Ontario -> CSDs -> CSV"
            "\n  - 2016: Census Profile -> Ontario -> CSDs -> CSV"
            "\n  - 2011: Census Profile -> CSDs -> CSV (comprehensive DL)"
            "\n  - 2006: Community Profiles -> CSDs -> CSV (comprehensive DL)"
        )
        sys.exit(1)

    print(f"\nFound {len(files)} Census file(s):\n")
    for path, _ in files:
        print(f"  - {os.path.basename(path)}")

    # Process each year
    all_indicators = []
    all_geos = []

    for path, loader in files:
        print(f"\n{'-' * 50}")
        indicators, geo = loader(path)
        all_indicators.append(indicators)
        all_geos.append(geo)

    # Combine all years
    print(f"\n{'-' * 50}")
    print("Combining all years...")

    combined = pd.concat(all_indicators, ignore_index=True)

    # FIX F2: Global cross-loader deduplication.
    # FILE_LOADERS is ordered so _load_2011 (100% Census) runs before
    # _load_2011_nhs (30% NHS). keep="first" ensures the higher-quality
    # mandatory Census data is retained when both loaders extract the
    # same indicator for the same CSD (e.g., "English and French").
    combined = combined.drop_duplicates(
        subset=["census_year", "sgc_code", "indicator"], keep="first"
    )

    # FIX C1: Synthesize continuous "commute_walk_bike" for 2011+ from
    # separate walk + bike indicators. 2006 already has the combined value
    # natively; this back-fills 2011, 2016, 2021 so planners can see an
    # unbroken active-transportation trendline.
    _walk_bike = combined[
        (combined["indicator"].isin(["commute_walk", "commute_bike"]))
        & (combined["census_year"] >= 2011)
    ]
    if not _walk_bike.empty:
        _synth = (
            _walk_bike.groupby(["census_year", "sgc_code"], as_index=False)["value"]
            .sum(min_count=1)  # FIX N2: Prevent NaN + NaN = 0.0 for suppressed CSDs
        )
        _synth["indicator"] = "commute_walk_bike"
        combined = pd.concat([combined, _synth], ignore_index=True)
        print(f"  [SYNTH] Created {len(_synth):,} synthetic commute_walk_bike rows for 2011+")

    # FIX H7: Back-calculate 2006 Housing Stock counts from percentage × dwellings_occupied.
    # The 2006 CSD Profile publishes dwelling types as percentages only.
    _dwelling_pct_map = {
        "_dwelling_single_detached_pct": "dwelling_single_detached",
        "_dwelling_semi_detached_pct":   "dwelling_semi_detached",
        "_dwelling_row_pct":             "dwelling_row",
        "_dwelling_apt_5plus_pct":       "dwelling_apt_5plus",
        "_dwelling_apt_under5_pct":      "dwelling_apt_under5",
        "_dwelling_duplex_pct":          "dwelling_duplex",
        "_dwelling_movable_pct":         "dwelling_movable",
    }
    _occ_2006 = combined[
        (combined["indicator"] == "dwellings_occupied") & (combined["census_year"] == 2006)
    ].set_index("sgc_code")["value"]
    _synth_stock_count = 0
    for pct_slug, count_slug in _dwelling_pct_map.items():
        _pct_vals = combined[
            (combined["indicator"] == pct_slug) & (combined["census_year"] == 2006)
        ].set_index("sgc_code")["value"]
        if not _pct_vals.empty and not _occ_2006.empty:
            _counts = ((_pct_vals / 100) * _occ_2006).dropna().round(0)
            _counts = _counts[_counts >= 0]
            if not _counts.empty:
                _synth_row = pd.DataFrame({
                    "census_year": 2006,
                    "sgc_code": _counts.index,
                    "indicator": count_slug,
                    "value": _counts.values,
                })
                combined = pd.concat([combined, _synth_row], ignore_index=True)
                _synth_stock_count += len(_synth_row)
    if _synth_stock_count:
        print(f"  [SYNTH] Created {_synth_stock_count:,} synthetic Housing Stock count rows for 2006")

    # FIX H5: Back-calculate 2006 major_repairs_needed from major_repairs_pct × dwellings_occupied.
    _repairs_pct = combined[
        (combined["indicator"] == "major_repairs_pct") & (combined["census_year"] == 2006)
    ].set_index("sgc_code")["value"]
    if not _repairs_pct.empty and not _occ_2006.empty:
        _repairs_count = ((_repairs_pct / 100) * _occ_2006).dropna().round(0)
        _repairs_count = _repairs_count[_repairs_count >= 0]
        if not _repairs_count.empty:
            _synth_repairs = pd.DataFrame({
                "census_year": 2006,
                "sgc_code": _repairs_count.index,
                "indicator": "major_repairs_needed",
                "value": _repairs_count.values,
            })
            combined = pd.concat([combined, _synth_repairs], ignore_index=True)
            print(f"  [SYNTH] Created {len(_synth_repairs):,} synthetic major_repairs_needed rows for 2006")

    # FIX H10: Synthesize 2011 hh_size_5_plus = "5 persons" + "6 or more persons".
    # 2011 Census splits the 5+ bucket into two categories.
    _hh5 = combined[
        (combined["indicator"] == "_hh_5_persons") & (combined["census_year"] == 2011)
    ].set_index("sgc_code")["value"]
    _hh6p = combined[
        (combined["indicator"] == "_hh_6_plus_persons") & (combined["census_year"] == 2011)
    ].set_index("sgc_code")["value"]
    if not _hh5.empty and not _hh6p.empty:
        _hh5plus = (_hh5.add(_hh6p, fill_value=0)).dropna()
        if not _hh5plus.empty:
            _synth_hh = pd.DataFrame({
                "census_year": 2011,
                "sgc_code": _hh5plus.index,
                "indicator": "hh_size_5_plus",
                "value": _hh5plus.values,
            })
            combined = pd.concat([combined, _synth_hh], ignore_index=True)
            print(f"  [SYNTH] Created {len(_synth_hh):,} synthetic hh_size_5_plus rows for 2011")

    # FIX N6: Back-calculate 2006 crowding count from percentage × dwellings_occupied.
    _crowding_pct = combined[
        (combined["indicator"] == "_crowding_above_1ppr_pct") & (combined["census_year"] == 2006)
    ].set_index("sgc_code")["value"]
    if not _crowding_pct.empty and not _occ_2006.empty:
        _crowding_count = ((_crowding_pct / 100) * _occ_2006).dropna().round(0)
        _crowding_count = _crowding_count[_crowding_count >= 0]
        if not _crowding_count.empty:
            _synth_crowding = pd.DataFrame({
                "census_year": 2006,
                "sgc_code": _crowding_count.index,
                "indicator": "crowding_above_1ppr",
                "value": _crowding_count.values,
            })
            combined = pd.concat([combined, _synth_crowding], ignore_index=True)
            print(f"  [SYNTH] Created {len(_synth_crowding):,} synthetic crowding_above_1ppr rows for 2006")

    # FIX D1: Synthesize broad age bands from 5-year cohorts (all years).
    # Guarantees 100% mandatory Census coverage; eliminates 2011 NHS contamination.
    _cohort_youth = ["cohort_0_4", "cohort_5_9", "cohort_10_14"]
    _cohort_working = ["cohort_15_19", "cohort_20_24", "cohort_25_29", "cohort_30_34",
                       "cohort_35_39", "cohort_40_44", "cohort_45_49", "cohort_50_54",
                       "cohort_55_59", "cohort_60_64"]
    _cohort_senior = ["cohort_65_69", "cohort_70_74", "cohort_75_79",
                      "cohort_80_84", "cohort_85_plus"]
    _synth_age_bands = []
    for _yr in combined["census_year"].unique():
        _yr_data = combined[combined["census_year"] == _yr]
        for _band_name, _band_cohorts in [
            ("pop_0_14", _cohort_youth),
            ("pop_15_64", _cohort_working),
            ("pop_65_plus", _cohort_senior),
        ]:
            _parts = []
            for _c in _band_cohorts:
                _s = _yr_data[_yr_data["indicator"] == _c].set_index("sgc_code")["value"]
                if not _s.empty:
                    _parts.append(_s)
            if _parts:
                _total = _parts[0]
                for _p in _parts[1:]:
                    _total = _total.add(_p, fill_value=0)
                _total = _total.dropna()
                if not _total.empty:
                    _synth_age_bands.append(pd.DataFrame({
                        "census_year": _yr,
                        "sgc_code": _total.index,
                        "indicator": _band_name,
                        "value": _total.values,
                    }))
    if _synth_age_bands:
        _synth_age_all = pd.concat(_synth_age_bands, ignore_index=True)
        combined = pd.concat([combined, _synth_age_all], ignore_index=True)
        print(f"  [SYNTH] Created {len(_synth_age_all):,} synthetic age-band rows (pop_0_14 / pop_15_64 / pop_65_plus)")

    # Drop all helper slugs — they were only needed for synthesis
    _helper_slugs = list(_dwelling_pct_map.keys()) + ["_hh_5_persons", "_hh_6_plus_persons", "_crowding_above_1ppr_pct"]
    combined = combined[~combined["indicator"].isin(_helper_slugs)]

    combined = combined.sort_values(["sgc_code", "census_year", "indicator"]).reset_index(drop=True)

    # Build unified geography table (prefer most recent name)
    geo_combined = pd.concat(all_geos, ignore_index=True)
    geo_combined = geo_combined.drop_duplicates(subset=["sgc_code"], keep="last").reset_index(drop=True)

    # Summary
    years = sorted(combined["census_year"].unique())
    n_indicators = combined["indicator"].nunique()
    n_geos = combined["sgc_code"].nunique()
    print(f"  Years: {years}")
    print(f"  Geographies: {n_geos}")
    print(f"  Indicators: {n_indicators}")
    print(f"  Total rows: {len(combined):,}")

    # Per-year coverage
    print(f"\n  Per-year indicator coverage:")
    for yr in years:
        yr_data = combined[combined["census_year"] == yr]
        print(f"    {yr}: {yr_data['indicator'].nunique()} indicators x {yr_data['sgc_code'].nunique()} communities")

    # Save
    os.makedirs(OUT_DIR, exist_ok=True)

    indicators_path = os.path.join(OUT_DIR, "census_indicators.csv")
    geo_path = os.path.join(OUT_DIR, "dim_geography.csv")

    combined.to_csv(indicators_path, index=False)
    geo_combined.to_csv(geo_path, index=False)

    print(f"\n[OK] Saved: {indicators_path}")
    print(f"[OK] Saved: {geo_path}")
    print(f"\nDone! {len(years)} Census years x {n_geos} communities x {n_indicators} indicators")

    return combined, geo_combined


if __name__ == "__main__":
    run()
