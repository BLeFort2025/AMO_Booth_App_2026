"""Fix crosswalk edge cases with manual overrides."""
import pandas as pd

df = pd.read_csv("config/fir_sgc_crosswalk.csv")
df["fir_code"] = df["fir_code"].astype(str).str.zfill(4)

# Normalize sgc_code formatting
def fix_sgc(x):
    if pd.isna(x) or x == "":
        return ""
    return str(int(float(x))).zfill(7)
df["sgc_code"] = df["sgc_code"].apply(fix_sgc)

# Fix Selwyn (unmatched -> Smith-Ennismore-Lakefield)
mask = df["fir_code"] == "1516"
df.loc[mask, "sgc_code"] = "3515015"
df.loc[mask, "sgc_name"] = "Smith-Ennismore-Lakefield"
df.loc[mask, "match_score"] = 1.0
df.loc[mask, "match_method"] = "manual"

# Fix Trent Lakes -> Galway-Cavendish and Harvey
mask = df["fir_code"] == "1542"
df.loc[mask, "sgc_code"] = "3515044"
df.loc[mask, "sgc_name"] = "Galway-Cavendish and Harvey"
df.loc[mask, "match_score"] = 1.0
df.loc[mask, "match_method"] = "manual"

# Verify weak matches that are actually correct
for code in ["1509", "4624", "5751"]:
    mask = df["fir_code"] == code
    df.loc[mask, "match_score"] = 1.0
    df.loc[mask, "match_method"] = "verified"

df.to_csv("config/fir_sgc_crosswalk.csv", index=False, encoding="utf-8")

# Summary
auto = df[df["match_method"].isin(["auto", "manual", "verified"])]
unmatched = df[df["match_method"] == "unmatched"]
upper = df[df["match_method"] == "upper_tier"]
print(f"Total: {len(df)}")
print(f"Matched (lower-tier): {len(auto)} ({len(auto[auto.match_score >= 0.8])} strong)")
print(f"Unmatched: {len(unmatched)}")
print(f"Upper-tier (no CSD): {len(upper)}")
print(f"Manual/Verified: {len(df[df.match_method.isin(['manual','verified'])])}")
