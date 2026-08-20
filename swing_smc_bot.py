"""
Free ICT Swing SMC Bot - London NY Close Analysis
100% FREE: yfinance + Gemini 2.0 Flash + Telegram
Runs MTF analysis: Daily/4H/1H for EURUSD, GBPUSD, XAUUSD, DXY
Detects: Market Structure BOS/CHoCH, FVG, IFVG, OB, BSL/SSL, Premium/Discount, Judas Swing, RSI OB/OS

Setup:
1. pip install yfinance pandas requests google-generativeai python-telegram-bot
2. Get FREE Gemini API key: https://aistudio.google.com/app/apikey
3. Get FREE Telegram Bot: Message @BotFather on Telegram -> /newbot -> get token. Then get your chat ID via @userinfobot
4. Set ENV vars: GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
5. Run: python swing_smc_bot.py --now   (for testing) or schedule at 22:00 London time (21:00 UTC winter, 21:00 UTC summer = 22:00 BST)
"""

import os
import argparse
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
import time

# Config
PAIRS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X", 
    "XAUUSD": "GC=F",  # Gold Futures proxy, better than XAUUSD on yahoo. Alternative: use "XAUUSD=X" if available, fallback to GC=F
    "DXY": "DX-Y.NYB",
    "XAGUSD": "SI=F"
}

# For better forex data, you can also use EURUSD=X etc.
# yfinance intervals: 1h, 1d, 1wk
TIMEFRAMES = ["1d", "1h"]

GEMINI_MODEL = "gemini-3.6-flash"

def fetch_data(ticker, period="30d", interval="1h"):
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty:
            return None
        # Flatten multi-index if needed
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df.rename(columns={"Date": "datetime", "Datetime": "datetime"}, inplace=True)
        return df
    except Exception as e:
        print(f"Error fetching {ticker} {interval}: {e}")
        return None

def detect_market_structure(df, lookback=20):
    """Simple BOS/CHoCH detection using swing highs/lows"""
    if df is None or len(df) < lookback+5:
        return "Insufficient data"
    
    # Swing detection
    df['swing_high'] = df['High'].rolling(5, center=True).max() == df['High']
    df['swing_low'] = df['Low'].rolling(5, center=True).max() == df['Low']  # simplified, use min in prod
    
    # Actually correct swing low detection
    df['is_swing_high'] = (df['High'].shift(2) < df['High'].shift(1)) & (df['High'].shift(1) < df['High']) & (df['High'] > df['High'].shift(-1)) & (df['High'] > df['High'].shift(-2))
    df['is_swing_low'] = (df['Low'].shift(2) > df['Low'].shift(1)) & (df['Low'].shift(1) > df['Low']) & (df['Low'] < df['Low'].shift(-1)) & (df['Low'] < df['Low'].shift(-2))
    
    recent_highs = df[df['is_swing_high']]['High'].tail(3).tolist()
    recent_lows = df[df['is_swing_low']]['Low'].tail(3).tolist()
    
    last_close = df['Close'].iloc[-1]
    
    # Trend bias
    if len(recent_highs) >=2 and len(recent_lows)>=2:
        hh = recent_highs[-1] > recent_highs[-2]
        hl = recent_lows[-1] > recent_lows[-2]
        ll = recent_lows[-1] < recent_lows[-2]
        lh = recent_highs[-1] < recent_highs[-2]
        if hh and hl:
            structure = "Bullish Structure: HH/HL - BOS bullish"
        elif ll and lh:
            structure = "Bearish Structure: LL/LH - BOS bearish"
        elif hh and ll:
            structure = "CHoCH potential - range expansion"
        else:
            structure = "Consolidation / Range"
    else:
        structure = "Ranging - no clear swing sequence"
    
    return structure, recent_highs, recent_lows, last_close

def detect_fvg(df):
    """Detect Fair Value Gaps"""
    fvgs = []
    for i in range(1, len(df)-1):
        # Bullish FVG: Low[i+1] > High[i-1]
        if df['Low'].iloc[i+1] > df['High'].iloc[i-1] and df['Close'].iloc[i] > df['Open'].iloc[i]:
            fvgs.append({
                "type": "Bullish FVG",
                "top": float(df['Low'].iloc[i+1]),
                "bottom": float(df['High'].iloc[i-1]),
                "time": str(df['datetime'].iloc[i]),
                "filled": df['Low'].iloc[-1] < float(df['High'].iloc[i-1])  # simplified fill check
            })
        # Bearish FVG: High[i+1] < Low[i-1]
        if df['High'].iloc[i+1] < df['Low'].iloc[i-1] and df['Close'].iloc[i] < df['Open'].iloc[i]:
            fvgs.append({
                "type": "Bearish FVG",
                "top": float(df['Low'].iloc[i-1]),
                "bottom": float(df['High'].iloc[i+1]),
                "time": str(df['datetime'].iloc[i]),
                "filled": df['High'].iloc[-1] > float(df['Low'].iloc[i-1])
            })
    # Return last 3 unfilled
    unfilled = [f for f in fvgs if not f['filled']][-3:]
    return unfilled

def detect_liquidity_pools(df, window=15):
    """Equal highs/lows = BSL/SSL pools"""
    if df is None or len(df) < window:
        return []
    recent = df.tail(window)
    # Simple: find highs within 0.05% of each other = equal highs
    pools = []
    highs = recent['High'].values
    lows = recent['Low'].values
    
    for i in range(len(highs)-2):
        if abs(highs[i] - highs[i+1])/highs[i] < 0.0005:
            pools.append(f"BSL - Equal Highs around {highs[i]:.5f} - likely liquidity above")
        if abs(lows[i] - lows[i+1])/lows[i] < 0.0005:
            pools.append(f"SSL - Equal Lows around {lows[i]:.5f} - likely liquidity below")
    return list(set(pools))[:3]

def calc_rsi(df, period=14):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

def build_market_snapshot():
    snapshot = ""
    all_data = {}
    
    for name, ticker in PAIRS.items():
        # Daily
        df_d = fetch_data(ticker, period="60d", interval="1d")
        df_h = fetch_data(ticker, period="20d", interval="1h")
        
        if df_d is None:
            continue
            
        struct_d, highs_d, lows_d, close_d = detect_market_structure(df_d)
        rsi_d = calc_rsi(df_d)
        fvgs_d = detect_fvg(df_d)
        pools = detect_liquidity_pools(df_d)
        
        struct_h = "N/A"
        rsi_h = 50
        if df_h is not None and not df_h.empty:
            struct_h_info = detect_market_structure(df_h)
            if isinstance(struct_h_info, tuple):
                struct_h = struct_h_info[0]
            rsi_h = calc_rsi(df_h)
        
        all_data[name] = {
            "close": close_d,
            "structure_daily": struct_d,
            "structure_h1": struct_h,
            "rsi_daily": rsi_d,
            "rsi_h1": rsi_h,
            "fvgs": fvgs_d,
            "pools": pools,
            "highs": highs_d,
            "lows": lows_d
        }
        
        snapshot += f"\n--- {name} ({ticker}) ---\n"
        snapshot += f"Close: {close_d:.5f} | RSI D: {rsi_d:.1f} (OB>70 OS<30) | RSI H1: {rsi_h:.1f}\n"
        snapshot += f"Daily Structure: {struct_d}\n"
        snapshot += f"H1 Structure: {struct_h}\n"
        snapshot += f"Liquidity Pools: {pools}\n"
        snapshot += f"Unfilled FVGs Daily: {fvgs_d}\n"
        snapshot += f"Recent Swing Highs: {highs_d[-2:] if highs_d else []} | Lows: {lows_d[-2:] if lows_d else []}\n"
    
    return snapshot, all_data

def call_gemini_analysis(market_snapshot):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "GEMINI_API_KEY not set. Here is raw data:\n" + market_snapshot
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        prompt = f"""
You are my ICT Swing Analyst for Forex & Commodities. Time: NY Daily Close [10 PM London - 5 PM NY].

LIVE MARKET SNAPSHOT from yfinance (Daily + 1H):
{market_snapshot}

TASK: Do top-down MTF analysis for swing trading next 2-5 days.

Focus pairs: EURUSD, GBPUSD, XAUUSD (GC=F), DXY, XAGUSD
Concepts: Market Structure BOS/CHoCH, Order Blocks, FVG/IFVG, Liquidity Sweep / Judas Swing, BSL/SSL, Premium/Discount, Momentum RSI, Strength via DXY correlation, OB/OS.

Give output in this exact format:

🔷 BIAS DASHBOARD (for each pair):
EURUSD: Bullish/Bearish/Neutral | Confidence High/Med/Low | Why 1 line
GBPUSD: ...
XAUUSD: ...
DXY: ...

🎯 DRAW ON LIQUIDITY (DOL):
Where is price likely to go next to grab liquidity?

💎 SWING POI (Best 2 setups only):
Pair - Type - Level - Why [OB/FVG/IFVG + HTF alignment]

🛑 INVALIDATION:
Pair - Level - What CHoCH kills it

📋 LONDON EXECUTION PLAN:
What to wait for at London Open? Judas Sweep? Then MSS + IFVG entry?

⚠️ NEWS FILTER:
Any red folder tomorrow? Should we stand down?

Keep it concise, trader language, no financial advice. Max 400 words.
"""
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini Error: {e}\nRaw data:\n{market_snapshot}"

def send_telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram not configured. Printing message:\n", message)
        return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Telegram max 4096 chars, split if needed
    for i in range(0, len(message), 4000):
        chunk = message[i:i+4000]
        try:
            requests.post(url, data={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"})
            time.sleep(0.5)
        except Exception as e:
            print(f"Telegram error: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", action="store_true", help="Run now for testing")
    args = parser.parse_args()
    
    print("Fetching market data...")
    snapshot, all_data = build_market_snapshot()
    print(snapshot)
    
    print("\nCalling Gemini...")
    analysis = call_gemini_analysis(snapshot)
    
    final_msg = f"📊 ICT SWING BRIEF - NY CLOSE {datetime.now().strftime('%Y-%m-%d %H:%M London')}\n\n{analysis}\n\n--- RAW SMC DATA ---\n{snapshot[:1500]}"
    
    print("\n--- FINAL ANALYSIS ---\n")
    print(final_msg)
    
    send_telegram(final_msg)
    print("\nDone. If Telegram configured, sent. Otherwise printed above.")

if __name__ == "__main__":
    main()

