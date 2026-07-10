"""
Build FIR → SGC Crosswalk (v2)
===============================
Matches FIR 4-digit municipality codes to Census 7-digit SGC codes.

Two-pass approach:
  1. Lower-tier municipalities (CSDs) first — match FIR names to Census CSD names
  2. Upper-tier municipalities (Counties/Regions, code ends in 00) — these map
     to Census Divisions (CDs), not CSDs, so they get flagged separately.

Usage:
    python scripts/build_fir_sgc_crosswalk.py
"""

import re
from pathlib import Path
from difflib import SequenceMatcher

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GEO_FILE = PROJECT_ROOT / "data" / "latest" / "wellbeing" / "dim_geography.csv"
FIR_FILE = PROJECT_ROOT / "data" / "derived" / "fir_indicators.csv"
OUTPUT_FILE = PROJECT_ROOT / "config" / "fir_sgc_crosswalk.csv"


# ── CSD type suffixes used in FIR filenames ──
CSD_TYPE_RE = re.compile(
    r'\s+(Tp|Township|Town|City|Municipality|Village|Borough|'
    r'UCo|SCo|United Counties|County|RM|Regional Municipality|'
    r'DM|District Municipality|MU|T|C|M|V|B|R|S|D|P)\.?$',
    re.IGNORECASE
)


def normalize(name: str) -> str:
    """Normalize municipality name for matching."""
    s = name.strip()
    s = CSD_TYPE_RE.sub('', s)
    s = re.sub(r'\s*\(.*?\)\s*', ' ', s)    # remove parenthetical
    s = re.sub(r"[''`]", "'", s)             # normalize apostrophes
    s = re.sub(r'[-–—]', ' ', s)             # normalize dashes
    s = re.sub(r'[,.]', '', s)               # remove punctuation
    s = re.sub(r'\s+', ' ', s).strip()
    return s.lower()


def score(fir_name: str, sgc_name: str) -> float:
    """Match score between two municipality names."""
    fn = normalize(fir_name)
    sn = normalize(sgc_name)
    if fn == sn:
        return 1.0
    if fn in sn or sn in fn:
        return 0.95
    return SequenceMatcher(None, fn, sn).ratio()


def is_upper_tier(fir_code: str) -> bool:
    """Upper-tier municipalities have FIR codes ending in 00."""
    return fir_code.endswith('00')


def build_crosswalk():
    """Build FIR→SGC crosswalk."""
    geo = pd.read_csv(GEO_FILE)
    geo["sgc_code"] = geo["sgc_code"].astype(str).str.zfill(7)

    fir = pd.read_csv(FIR_FILE)
    fir_munis = (
        fir[["fir_code", "municipality_name"]]
        .drop_duplicates("fir_code")
        .reset_index(drop=True)
    )
    fir_munis["fir_code"] = fir_munis["fir_code"].astype(str).str.zfill(4)

    print(f"FIR municipalities: {len(fir_munis)}")
    print(f"  Lower-tier: {sum(~fir_munis['fir_code'].apply(is_upper_tier))}")
    print(f"  Upper-tier: {sum(fir_munis['fir_code'].apply(is_upper_tier))}")
    print(f"Census CSDs: {len(geo)}")

    results = []
    sgc_used = set()

    # ── PASS 1: Lower-tier (CSDs) ──
    lower = fir_munis[~fir_munis["fir_code"].apply(is_upper_tier)].copy()

    # Pre-compute all scores for lower-tier, then assign greedily by best match
    match_list = []
    for _, fir_row in lower.iterrows():
        fir_code = fir_row["fir_code"]
        fir_name = fir_row["municipality_name"]
        for _, geo_row in geo.iterrows():
            sgc = geo_row["sgc_code"]
            geo_name = str(geo_row["geo_name"])
            s = score(fir_name, geo_name)
            if s >= 0.45:
                match_list.append({
                    "fir_code": fir_code,
                    "fir_name": fir_name,
                    "sgc_code": sgc,
                    "sgc_name": geo_name,
                    "score": s,
                })

    # Sort by score descending, then greedily assign
    match_df = pd.DataFrame(match_list).sort_values("score", ascending=False)
    fir_matched = set()

    for _, row in match_df.iterrows():
        if row["fir_code"] in fir_matched or row["sgc_code"] in sgc_used:
            continue
        if row["score"] >= 0.5:
            results.append({
                "fir_code": row["fir_code"],
                "fir_name": row["fir_name"],
                "sgc_code": row["sgc_code"],
                "sgc_name": row["sgc_name"],
                "match_score": round(row["score"], 3),
                "match_method": "auto",
                "tier": "lower",
            })
            fir_matched.add(row["fir_code"])
            sgc_used.add(row["sgc_code"])

    # Add unmatched lower-tier
    for _, fir_row in lower.iterrows():
        if fir_row["fir_code"] not in fir_matched:
            results.append({
                "fir_code": fir_row["fir_code"],
                "fir_name": fir_row["municipality_name"],
                "sgc_code": "",
                "sgc_name": "",
                "match_score": 0,
                "match_method": "unmatched",
                "tier": "lower",
            })

    # ── PASS 2: Upper-tier (Counties/Regions) ──
    # Upper-tier FIR municipalities are Counties, Regions, Districts
    # They correspond to Census Divisions (CDs), not CSDs
    # We'll mark them as "upper_tier" — they can still be useful for aggregation
    upper = fir_munis[fir_munis["fir_code"].apply(is_upper_tier)]
    for _, fir_row in upper.iterrows():
        results.append({
            "fir_code": fir_row["fir_code"],
            "fir_name": fir_row["municipality_name"],
            "sgc_code": "",
            "sgc_name": "",
            "match_score": 0,
            "match_method": "upper_tier",
            "tier": "upper",
        })

    # ── Save ──
    df = pd.DataFrame(results)
    df = df.sort_values("fir_code").reset_index(drop=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    # ── Summary ──
    auto = df[df["match_method"] == "auto"]
    strong = auto[auto["match_score"] >= 0.8]
    weak = auto[(auto["match_score"] >= 0.5) & (auto["match_score"] < 0.8)]
    unmatched = df[df["match_method"] == "unmatched"]
    upper_tier = df[df["match_method"] == "upper_tier"]

    print(f"\n{'='*60}")
    print(f"CROSSWALK RESULTS")
    print(f"  Strong matches (≥0.8):  {len(strong)}")
    print(f"  Weak matches (0.5-0.8): {len(weak)}")
    print(f"  Unmatched lower-tier:   {len(unmatched)}")
    print(f"  Upper-tier (no CSD):    {len(upper_tier)}")
    print(f"  Total:                  {len(df)}")
    print(f"  Output:                 {OUTPUT_FILE}")
    print(f"{'='*60}")

    if len(weak) > 0:
        print(f"\nWeak matches (review these):")
        for _, r in weak.iterrows():
            print(f"  {r['fir_code']} '{r['fir_name']}' → {r['sgc_code']} '{r['sgc_name']}' ({r['match_score']})")

    if len(unmatched) > 0:
        print(f"\nUnmatched lower-tier:")
        for _, r in unmatched.iterrows():
            print(f"  {r['fir_code']} '{r['fir_name']}'")

    return df


if __name__ == "__main__":
    build_crosswalk()
