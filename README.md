# london_open_trading_bot
This BOT Does the Heavy Lifting of Analysing the Swing and Positional Trades with Market Strucuture and Identifying the Key Levels.

## What it does at 10 PM London
    1. Pulls live data for EURUSD, GBPUSD, XAUUSD, XAGUSD, DXY via yfinance[free]
    2. Auto-detects:
        - Market Structure: BOS/CHoCH using swing highs/lows
        - FVG / IFVG: unfilled gaps + fill tracking
        - BSL/SSL: Equal Highs/Lows = liquidity pools
        - RSI Daily + H1 for Overbought/Oversold
        - Premium/Discount from range
    3. Sends it to Gemini 2.0 Flash FREE to generate your swing brief in ICT language
    4. Pushes to Telegram so you wake up to it before London Open