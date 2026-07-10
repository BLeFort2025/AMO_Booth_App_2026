"""
Add county/upper-tier SGC codes to the FIR-SGC crosswalk.

Each county gets a synthetic SGC code: CD_code + "000"
(e.g., Oxford County CD 3532 → SGC 3532000).

These codes don't conflict with any existing CSD codes (which end in
001-099) and allow county FIR data to flow through the entire pipeline.
"""
import pandas as pd
from pathlib import Path

CROSSWALK = Path("config/fir_sgc_crosswalk.csv")

# Manual mapping: FIR code → (CD code, canonical name)
# Derived from Ontario SGC Census Division codes.
# York Region is special: FIR prefix 20 maps to CD 3519 (not 3520 = Toronto).
COUNTY_MAPPINGS = {
    "0100": ("3501", "Stormont, Dundas and Glengarry UCo"),
    "0200": ("3502", "Prescott and Russell UCo"),
    "0700": ("3507", "Leeds and Grenville UCo"),
    "0900": ("3509", "Lanark Co"),
    "1000": ("3510", "Frontenac Co"),
    "1100": ("3511", "Lennox and Addington Co"),
    "1200": ("3512", "Hastings Co"),
    "1400": ("3514", "Northumberland Co"),
    "1500": ("3515", "Peterborough Co"),
    "1800": ("3518", "Durham R"),
    "2000": ("3519", "York R"),
    "2100": ("3521", "Peel R"),
    "2200": ("3522", "Dufferin Co"),
    "2300": ("3523", "Wellington Co"),
    "2400": ("3524", "Halton R"),
    "2600": ("3526", "Niagara R"),
    "3000": ("3530", "Waterloo R"),
    "3100": ("3531", "Perth Co"),
    "3200": ("3532", "Oxford Co"),
    "3400": ("3534", "Elgin Co"),
    "3700": ("3537", "Essex Co"),
    "3800": ("3538", "Lambton Co"),
    "3900": ("3539", "Middlesex Co"),
    "4000": ("3540", "Huron Co"),
    "4100": ("3541", "Bruce Co"),
    "4200": ("3542", "Grey Co"),
    "4300": ("3543", "Simcoe Co"),
    "4400": ("3544", "Muskoka D"),
    "4600": ("3546", "Haliburton Co"),
    "4700": ("3547", "Renfrew Co"),
}


def run():
    xw = pd.read_csv(CROSSWALK, dtype=str)
    updated = 0

    for idx, row in xw.iterrows():
        fir_code = str(row["fir_code"]).zfill(4)
        if fir_code in COUNTY_MAPPINGS:
            cd_code, name = COUNTY_MAPPINGS[fir_code]
            synth_sgc = cd_code + "000"

            # Only update if currently missing
            if pd.isna(row["sgc_code"]) or row["sgc_code"] == "":
                xw.at[idx, "sgc_code"] = synth_sgc
                xw.at[idx, "sgc_name"] = name
                xw.at[idx, "match_score"] = "1.0"
                xw.at[idx, "match_method"] = "manual_county"
                xw.at[idx, "tier"] = "upper"
                updated += 1
                print(f"  ✅ {fir_code} {name:<44} → {synth_sgc}")

    xw.to_csv(CROSSWALK, index=False)
    print(f"\nUpdated {updated} county entries in {CROSSWALK}")


if __name__ == "__main__":
    run()
