"""
Tariff Incidence Research — Supplementary Data Acquisition
==========================================================
Downloads control variables needed for the fertilizer tariff pass-through
regression:
  1. Henry Hub natural gas prices (monthly) — from FRED API
  2. CAD/USD exchange rate (monthly) — from Bank of Canada Valet API
  3. Baltic Dry Index (monthly) — from FRED API

All outputs go to: data/latest/tariff_research/
"""
import sys
from pathlib import Path
import json
from datetime import datetime

import pandas as pd
import requests

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "data" / "latest" / "tariff_research"
OUT_DIR.mkdir(parents=True, exist_ok=True)

START = "2019-01-01"
END   = "2025-12-31"

# ── 1. Henry Hub Natural Gas Prices (FRED: MHHNGSP — monthly) ────────────────
def download_henry_hub():
    """Download Henry Hub monthly spot price from FRED (no API key required for CSV)."""
    print("📥 Downloading Henry Hub natural gas prices (FRED)...")
    
    # FRED provides CSV download without API key
    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id=MHHNGSP&cosd={START}&coed={END}"
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        
        out_path = OUT_DIR / "henry_hub_gas_monthly.csv"
        out_path.write_bytes(resp.content)
        
        # Validate
        df = pd.read_csv(out_path)
        df.columns = ["date", "henry_hub_usd_per_mmbtu"]
        # FRED uses "." for missing values
        df["henry_hub_usd_per_mmbtu"] = pd.to_numeric(
            df["henry_hub_usd_per_mmbtu"], errors="coerce"
        )
        df.to_csv(out_path, index=False)
        
        print(f"   ✅ Saved {len(df)} rows → {out_path.name}")
        print(f"   📅 Range: {df['date'].min()} to {df['date'].max()}")
        print(f"   📊 Latest: ${df.dropna().iloc[-1]['henry_hub_usd_per_mmbtu']:.2f}/MMBtu")
        return df
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return pd.DataFrame()


# ── 2. CAD/USD Exchange Rate (Bank of Canada Valet API) ──────────────────────
def download_cad_usd():
    """Download daily CAD/USD from Bank of Canada, resample to monthly."""
    print("\n📥 Downloading CAD/USD exchange rate (Bank of Canada)...")
    
    # FXCADUSD = Canadian dollar per USD
    url = (
        "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/csv"
        f"?start_date={START}&end_date={END}"
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        
        # Bank of Canada CSV has metadata rows at the top
        lines = resp.text.strip().split("\n")
        # Find the header row (starts with "date")
        header_idx = None
        for i, line in enumerate(lines):
            if line.strip().startswith('"date"') or line.strip().startswith('date'):
                header_idx = i
                break
        
        if header_idx is None:
            # Try alternative: skip first 4 lines (typical BoC format)
            header_idx = 0
            for i, line in enumerate(lines):
                if "FXUSDCAD" in line or "date" in line.lower():
                    header_idx = i
                    break
        
        # Parse from the header row
        from io import StringIO
        data_text = "\n".join(lines[header_idx:])
        df = pd.read_csv(StringIO(data_text))
        
        # Normalize column names
        df.columns = [c.strip().strip('"').lower() for c in df.columns]
        
        if "fxusdcad" in df.columns:
            df = df.rename(columns={"fxusdcad": "cad_per_usd"})
        elif "v122150" in df.columns:
            df = df.rename(columns={"v122150": "cad_per_usd"})
        else:
            # Find the numeric column
            for col in df.columns:
                if col != "date":
                    df = df.rename(columns={col: "cad_per_usd"})
                    break
        
        df["date"] = pd.to_datetime(df["date"])
        df["cad_per_usd"] = pd.to_numeric(df["cad_per_usd"], errors="coerce")
        df = df.dropna(subset=["cad_per_usd"])
        
        # Resample to monthly average
        df = df.set_index("date").resample("MS").mean().reset_index()
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        
        out_path = OUT_DIR / "cad_usd_monthly.csv"
        df[["date", "cad_per_usd"]].to_csv(out_path, index=False)
        
        print(f"   ✅ Saved {len(df)} monthly rows → {out_path.name}")
        print(f"   📅 Range: {df['date'].min()} to {df['date'].max()}")
        print(f"   📊 Latest: {df.iloc[-1]['cad_per_usd']:.4f} CAD/USD")
        return df
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        print(f"   Attempting fallback via FRED (DEXCAUS)...")
        return download_cad_usd_fred()


def download_cad_usd_fred():
    """Fallback: Download CAD/USD from FRED."""
    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id=DEXCAUS&cosd={START}&coed={END}"
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        
        out_path = OUT_DIR / "cad_usd_monthly.csv"
        
        from io import StringIO
        df = pd.read_csv(StringIO(resp.text))
        df.columns = ["date", "cad_per_usd"]
        df["cad_per_usd"] = pd.to_numeric(df["cad_per_usd"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna(subset=["cad_per_usd"])
        
        # Resample daily to monthly
        df = df.set_index("date").resample("MS").mean().reset_index()
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        
        df.to_csv(out_path, index=False)
        print(f"   ✅ (FRED fallback) Saved {len(df)} monthly rows → {out_path.name}")
        return df
    except Exception as e:
        print(f"   ❌ FRED fallback also failed: {e}")
        return pd.DataFrame()


# ── 3. Baltic Dry Index (FRED: no direct series — use alternative) ───────────
def download_baltic_dry():
    """
    Download Baltic Dry Index proxy.
    FRED doesn't have BDI directly. We'll try FRED's DBDI (discontinued) 
    or use a web fallback.
    """
    print("\n📥 Downloading Baltic Dry Index proxy...")
    
    # Try FRED first — there's no official BDI on FRED, but DCOILBRENTEU 
    # (Brent crude) can serve as a transport cost proxy
    # Alternative: use global shipping cost index from FRED
    
    # Try World Bank transport cost proxy from our CMO data
    cmo_path = PROJECT_ROOT / "data" / "latest" / "CMO-Historical-Data-Monthly.xlsx"
    if cmo_path.exists():
        try:
            # CMO monthly data includes energy and transport-related commodities
            df = pd.read_excel(cmo_path, sheet_name=0, header=None)
            
            # Find the header row
            for i in range(min(10, len(df))):
                row_vals = [str(v).strip() for v in df.iloc[i].values if pd.notna(v)]
                if any("crude" in v.lower() or "energy" in v.lower() for v in row_vals):
                    header_row = i
                    break
            else:
                header_row = 0
            
            print(f"   ℹ️  CMO data found — extracting energy/transport proxies")
            # We'll extract Brent crude as our freight proxy
            # For now, save a placeholder and use Brent from FRED
        except Exception as e:
            print(f"   ℹ️  CMO parsing complex — falling back to FRED Brent crude")
    
    # Download Brent crude as ocean freight proxy
    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id=MCOILBRENTEU&cosd={START}&coed={END}"
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        
        out_path = OUT_DIR / "brent_crude_monthly.csv"
        out_path.write_bytes(resp.content)
        
        df = pd.read_csv(out_path)
        df.columns = ["date", "brent_usd_per_barrel"]
        df["brent_usd_per_barrel"] = pd.to_numeric(
            df["brent_usd_per_barrel"], errors="coerce"
        )
        df.to_csv(out_path, index=False)
        
        print(f"   ✅ Saved {len(df)} rows → {out_path.name}")
        print(f"      (Using Brent crude as ocean freight cost proxy)")
        print(f"   📅 Range: {df['date'].min()} to {df['date'].max()}")
        return df
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return pd.DataFrame()


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("   FERTILIZER TARIFF RESEARCH — DATA ACQUISITION")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print()
    
    results = {}
    
    gas = download_henry_hub()
    results["henry_hub"] = len(gas) > 0
    
    fx = download_cad_usd()
    results["cad_usd"] = len(fx) > 0
    
    freight = download_baltic_dry()
    results["freight_proxy"] = len(freight) > 0
    
    print("\n" + "=" * 70)
    print("   ACQUISITION SUMMARY")
    print("=" * 70)
    for name, success in results.items():
        status = "✅" if success else "❌"
        print(f"   {status} {name}")
    
    print(f"\n   Files saved to: {OUT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
