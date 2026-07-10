import pandas as pd
df = pd.read_csv("config/fir_sgc_crosswalk.csv")
with open("scripts/crosswalk_review.txt", "w", encoding="utf-8") as f:
    u = df[df["match_method"] == "unmatched"]
    f.write(f"=== UNMATCHED ({len(u)}) ===\n")
    for _, r in u.iterrows():
        f.write(f"  {r.fir_code} = {r.fir_name} (best_score={r.match_score})\n")
    f.write("\n")
    low = df[(df["match_method"] == "auto") & (df["match_score"] < 0.8)]
    f.write(f"=== WEAK MATCHES (<0.8, {len(low)}) ===\n")
    for _, r in low.iterrows():
        f.write(f"  {r.fir_code} '{r.fir_name}' -> {r.sgc_code} '{r.sgc_name}' (score={r.match_score})\n")
    f.write("\n")
    f.write(f"=== SUMMARY ===\n")
    f.write(f"  Total: {len(df)}\n")
    f.write(f"  Auto-matched: {len(df[df.match_method=='auto'])}\n")
    f.write(f"  Strong (>=0.8): {len(df[(df.match_method=='auto')&(df.match_score>=0.8)])}\n")
    f.write(f"  Weak (0.5-0.8): {len(low)}\n")
    f.write(f"  Unmatched: {len(u)}\n")
print("Done - see scripts/crosswalk_review.txt")
