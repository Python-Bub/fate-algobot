# IBKR Connection Settings (TWS / IB Gateway — enable API in Global Configuration)
IBKR_HOST = "127.0.0.1"
IBKR_PORT = 7497  # paper TWS often 7497; live often 7496 — match your TWS settings
IBKR_CLIENT_ID = 3

# Price data for features (override with env PRICE_DATA_SOURCE):
#   yfinance — Yahoo only (default when BROKER=ibkr or Alpaca keys missing)
#   ibkr     — daily bars from IBKR (requires TWS/Gateway + data subscriptions)
#   hybrid   — IBKR first, then Yahoo if IBKR returns empty / connection fails
#   alpaca   — Alpaca Market Data daily bars (needs ALPACA_API_KEY + ALPACA_SECRET_KEY)
#   hybrid_alpaca — Alpaca first, then Yahoo
#
# Execution broker (env BROKER, default alpaca): alpaca | ibkr
#   Alpaca paper default: ALPACA_BASE_URL=https://paper-api.alpaca.markets
#   Live trading API: https://api.alpaca.markets (only if you intentionally switch)

# Logging Configuration
LOG_LEVEL = "INFO"

MODEL_DIR = "models"

# Symbols used by dispatcher / live_trader (US SMART USD)
TICKERS = [
    "AAPL",
    "TSLA",
    "NVDA",
    "AMZN",
    "MSFT",
    "COIN",
    "AMD",
    "META",
    "GOOGL",
    "INTC",
    "AVGO",
    "SPY",
    "QQQ",
]

# Broader training universe (yfinance symbols; include non-US suffixes where needed)
TRAIN_TICKERS = TICKERS + [
    "JPM",
    "BAC",
    "XOM",
    "JNJ",
    "UNH",
    "V",
    "MA",
    "WMT",
    "COST",
    "DIS",
    "NFLX",
    "CRM",
    "ORCL",
    "IBM",
    "CSCO",
    "PEP",
    "KO",
    "MCD",
    "PG",
    "HD",
    "LOW",
    "IWM",
    "EFA",
    "EEM",
    "VEA",
    "VWO",
    "EWJ",
    "EWG",
    "EWZ",
    "FXI",
    "ASML",
    "TSM",
    "NVO",
    "BABA",
    "SONY",
    "BP",
    "SAP",
    "UBER",
    "SHOP",
    "XYZ",
    "PANW",
    "CRWD",
    "SNOW",
    "PLTR",
]

CLIENT_IDS = {
    "AAPL": 101,
    "TSLA": 102,
    "NVDA": 103,
    "AMZN": 104,
    "MSFT": 105,
    "COIN": 106,
    "AMD": 107,
    "META": 108,
    "GOOGL": 109,
}
