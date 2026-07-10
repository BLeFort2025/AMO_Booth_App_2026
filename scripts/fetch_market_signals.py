import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime

# Configuration
DATA_DIR = Path("data/latest")
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = DATA_DIR / "market_signals.csv"

# Ticker Mapping (Yahoo Finance)
# We use these to gauge the % change from historical average to 2025 Outlook.
TICKERS = {
    "ZC=F": "Corn Futures (USD/bu)",
    "LE=F": "Live Cattle Futures (USD/lb)",
    "CL=F": "Crude Oil WTI (USD/bbl)",
    "NG=F": "Natural Gas (USD/MMBtu)",
    "CAD=X": "USD/CAD Exchange Rate" 
}

def fetch_signals():
    print("📡 Fetching live market signals from Yahoo Finance...")
    
    records = []
    
    for ticker, name in TICKERS.items():
        try:
            # Fetch 2 years of history to get current trend
            tick = yf.Ticker(ticker)
            hist = tick.history(period="1y")
            
            if hist.empty:
                print(f"⚠️  No data found for {ticker}")
                continue
            
            # 1. Current Spot Price (Last Close)
            current_price = hist['Close'].iloc[-1]
            
            # 2. Volatility (Annualized Standard Deviation of daily returns)
            # Used for Monte Carlo "Cone of Uncertainty"
            daily_returns = hist['Close'].pct_change().dropna()
            volatility = daily_returns.std() * (252 ** 0.5) # Annualize
            
            records.append({
                "ticker": ticker,
                "name": name,
                "current_price": current_price,
                "volatility": volatility,
                "last_updated": datetime.now().strftime("%Y-%m-%d")
            })
            
            print(f"   ✅ {name}: {current_price:.2f} (Vol: {volatility:.1%})")
            
        except Exception as e:
            print(f"   ❌ Failed to fetch {ticker}: {e}")

    # Save to CSV
    df = pd.DataFrame(records)
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"💾 Market signals saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    fetch_signals()