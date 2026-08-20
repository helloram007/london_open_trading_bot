"""
Free ICT POSITIONAL SMC Bot - Weekly Close Analysis
For 2-12 week holds. Run Sunday 10 PM London.
Detects: Weekly/Monthly Market Structure, Weekly FVG, Premium/Discount OTE, COT proxy via DXY/Yields
100% FREE
"""

import os
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime

PAIRS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "DXY": "DX-Y.NYB",
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "US10Y": "^TNX",
    "WTI": "CL=F"
}

def fetch_data(ticker, period="2y", interval="1wk"):
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df.rename(columns={"Date": "datetime", "Datetime": "datetime"}, inplace=True)
        return df
    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None

def detect_weekly_structure(df):
    if df is None or len(df) < 20:
        return "No data", 50
    # Simple weekly BOS/CHoCH via 5-candle swing
    df['is_high'] = (df['High'].shift(2) < df['High'].shift(1)) & (df['High'].shift(1) < df['High']) & (df['High'] > df['High'].shift(-1)) & (df['High'] > df['High'].shift(-2))
    df['is_low'] = (df['Low'].shift(2) > df['Low'].shift(1)) & (df['Low'].shift(1) > df['Low']) & (df['Low'] < df['Low'].shift(-1)) & (df['Low'] < df['Low'].shift(-2))
    
    highs = df[df['is_high']]['High'].tail(3).tolist()
    lows = df[df['is_low']]['Low'].tail(3).tolist()
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_last = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50
    
    if len(highs)>=2 and len(lows)>=2:
        if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
            struct = "Weekly Bullish BOS - HH/HL"
        elif highs[-1] < highs[-2] and lows[-1] < lows[-2]:
            struct = "Weekly Bearish BOS - LL/LH"
        else:
            struct = "Weekly CHoCH / Range - indecision"
    else:
        struct = "Weekly Range"
    
    return struct, rsi_last

def detect_weekly_fvg(df):
    fvgs = []
    for i in range(1, len(df)-1):
        if df['Low'].iloc[i+1] > df['High'].iloc[i-1] and df['Close'].iloc[i] > df['Open'].iloc[i]:
            fvgs.append(f"Bull Weekly FVG {float(df['High'].iloc[i-1]):.4f}-{float(df['Low'].iloc[i+1]):.4f}")
        if df['High'].iloc[i+1] < df['Low'].iloc[i-1] and df['Close'].iloc[i] < df['Open'].iloc[i]:
            fvgs.append(f"Bear Weekly FVG {float(df['High'].iloc[i+1]):.4f}-{float(df['Low'].iloc[i-1]):.4f}")
    return fvgs[-2:]


def parse_gemini_json(text):
    import json, re
    try:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(text)
    except Exception as e:
        print(f"JSON parse failed: {e}")
        return None

def build_vertical_tables_positional(assets_data):
    tables = ""
    tables += "🏛️ POSITIONAL BRIEF - WEEKLY CLOSE\n"
    tables += f"{datetime.now().strftime('%Y-%m-%d')}\n"
    tables += "="*40 + "\n\n"
    if not assets_data:
        return tables + "No AI data"
    for item in assets_data:
        asset = item.get("asset","")
        tables += f"┌─ {asset} ─────────────────────────\n"
        tables += f"│ Macro Bias   : {item.get('macro_bias','')}\n"
        tables += f"│ W Structure  : {item.get('weekly_structure','')}\n"
        tables += f"│ RSI W        : {item.get('rsi_weekly','')}\n"
        tables += f"│ PD Zone      : {item.get('pd_zone','')}\n"
        tables += f"│ Weekly FVG   : {item.get('weekly_fvg','')}\n"
        tables += f"│ DOL          : {item.get('dol','')}\n"
        tables += f"│ POI          : {item.get('positional_poi','')}\n"
        tables += f"│ Invalidation : {item.get('invalidation','')}\n"
        tables += f"│ Roadmap      : {item.get('roadmap','')}\n"
        tables += f"└─────────────────────────────────\n\n"
    return tables


def build_positional_snapshot():
    snap = ""
    for name, ticker in PAIRS.items():
        df_w = fetch_data(ticker, period="2y", interval="1wk")
        df_m = fetch_data(ticker, period="5y", interval="1mo")
        if df_w is None:
            continue
        struct_w, rsi_w = detect_weekly_structure(df_w)
        fvg_w = detect_weekly_fvg(df_w)
        close_w = float(df_w['Close'].iloc[-1])
        
        # Premium/Discount OTE approximation
        high_6m = float(df_w['High'].tail(26).max())
        low_6m = float(df_w['Low'].tail(26).min())
        range_mid = (high_6m + low_6m)/2
        if close_w > high_6m - (high_6m-low_6m)*0.3:
            pd_zone = "Premium [Sell Side - high risk for longs]"
        elif close_w < low_6m + (high_6m-low_6m)*0.3:
            pd_zone = "Discount [Buy Side - high risk for shorts]"
        else:
            pd_zone = "Equilibrium / OTE zone"
        
        snap += f"\n--- {name} ---\nClose W: {close_w:.4f} | Weekly: {struct_w} | RSI W: {rsi_w:.1f}\nPD: {pd_zone} | 6M Range {low_6m:.4f}-{high_6m:.4f}\nWeekly FVGs: {fvg_w}\n"
    return snap

def call_gemini_positional(snapshot):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return snapshot
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
prompt = f"""
You are my ICT Positional Analyst. Time: Sunday Weekly Close 10 PM London.

LIVE WEEKLY SNAPSHOT (Weekly + Monthly data):
{snapshot}

TASK: For EACH asset (EURUSD, GBPUSD, XAUUSD, XAGUSD, DXY, US10Y, WTI), return JSON:

{{
  "asset": "EURUSD",
  "macro_bias": "Bullish/Bearish",
  "weekly_structure": "Weekly BOS/CHoCH",
  "rsi_weekly": "RSI value + OB/OS",
  "pd_zone": "Premium/Discount/OTE",
  "weekly_fvg": "Weekly FVG level",
  "dol": "Monthly/Weekly liquidity target",
  "positional_poi": "Weekly OB/FVG level to enter",
  "invalidation": "Weekly CHoCH level",
  "roadmap": "2-12 week plan 1 line"
}}

Return ONLY JSON array:
[
  {{"asset": "EURUSD", ...}},
  ...
]
"""

        model_name = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        try:
            chat = client.chats.create(model=model_name)
            resp = chat.send_message(prompt)
        except Exception as e_model:
            if "not found" in str(e_model).lower() or "404" in str(e_model):
                chat = client.chats.create(model="gemini-2.5-flash")
                resp = chat.send_message(prompt)
            else:
                raise
        return resp.text
    except Exception as e:
        return f"Gemini error {e}\n{snapshot}"

def send_telegram(msg):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print(msg)
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for i in range(0, len(msg), 4000):
        requests.post(url, data={"chat_id": chat_id, "text": msg[i:i+4000]})

if __name__ == "__main__":
    snap = build_positional_snapshot()
    raw_ai = call_gemini_positional(snap)
    print(f"Raw AI: {raw_ai[:1000]}")
    parsed = parse_gemini_json(raw_ai)
    if parsed:
        final = build_vertical_tables_positional(parsed)
        final += "\n--- RAW ---\n" + snap[:1000]
    else:
        final = f"🏛️ POSITIONAL BRIEF - WEEKLY CLOSE {datetime.now().strftime('%Y-%m-%d')}\n\n{raw_ai}\n\n--- RAW ---\n{snap[:1000]}"
    print(final)
    send_telegram(final)
