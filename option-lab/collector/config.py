"""Collector configuration — read from environment / .env, never hardcode secrets."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]   # C:\Dev\Dev\Trading
OPTION_LAB = Path(__file__).resolve().parents[1]     # option-lab
ENV_PATH = PROJECT_ROOT / ".env"

# .env is authoritative (this box may also export stale FYERS_* in the ambient
# environment, which must NOT win over the file). On Render there is no .env,
# so env-injected secrets still work untouched.
if ENV_PATH.exists():
    load_dotenv(ENV_PATH, override=True)
else:
    load_dotenv()

get = os.getenv

# ---- Fyers ----
FYERS_CLIENT_ID = get("FYERS_CLIENT_ID", "")
FYERS_APP_TYPE = get("FYERS_APP_TYPE", "100")
FYERS_SECRET_KEY = get("FYERS_SECRET_KEY", "")
FYERS_ACCESS_TOKEN = get("FYERS_ACCESS_TOKEN", "")
FYERS_REFRESH_TOKEN = get("FYERS_REFRESH_TOKEN", "")

# ---- Index universe (Fyers spot symbols, from config.py of backtest) ----
INDICES = {
    "NIFTY": "NSE:NIFTY50-INDEX",
    "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
    "FINNIFTY": "NSE:FINNIFTY-INDEX",
    "MIDCPNIFTY": "NSE:MIDCPNIFTY-INDEX",
}
# fallback strike steps / lot sizes (refreshed from master at runtime)
LOT_SIZE = {"NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "MIDCPNIFTY": 120}
STRIKE_STEP = {"NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50, "MIDCPNIFTY": 25}

# ---- Local data root (this is what GCS mirrors) ----
DATA_ROOT = Path(get("COLLECTOR_DATA", str(OPTION_LAB / "data_live")))

# ---- GCS (optional until bucket + service-account exist) ----
GCS_BUCKET = get("GCS_BUCKET", "").strip()
GOOGLE_APPLICATION_CREDENTIALS = get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
GCS_ENABLED = bool(GCS_BUCKET and GOOGLE_APPLICATION_CREDENTIALS)

# ---- Cadence / timing (IST) ----
TIMEZONE = "Asia/Kolkata"
PRE_START = "08:55:00"    # preflight: token check, master, symbols
START = "09:05:00"        # begin streaming
END = "15:35:00"          # last live snapshot (options close 15:30-15:35)
BACKFILL_AT = "15:45:00"  # EOD history upgrade
TICK_SECONDS = 20         # quote snapshot cadence for the streamed window
CHAIN_SECONDS = 60        # option-chain OI snapshot cadence
SYNC_SECONDS = 900        # GCS push cadence (15 min)
FLUSH_SECONDS = 3600      # hourly partial writes

# ---- Coverage ----
# Trade/stream window (strikes both sides of ATM, in steps) per index per expiry.
STREAM_HALF_WIDTH = {"NIFTY": 3, "BANKNIFTY": 2, "FINNIFTY": 2, "MIDCPNIFTY": 3}
# Option-chain strikecount requested per expiry (SDK: N ITM + ATM + N OTM).
CHAIN_STRIKE_COUNT = {"NIFTY": 12, "BANKNIFTY": 8, "FINNIFTY": 10, "MIDCPNIFTY": 12}

# Fyers quotes batch limit + polite gap between calls.
QUOTE_BATCH = 45
CALL_GAP = 0.45

# HTTP health port (Render injects PORT at deploy time).
PORT = int(get("PORT", "8080"))

# Master location (reused from the backtest downloader).
MASTER_NSE = OPTION_LAB / "data" / "NSE_FO.csv"
MASTER_BSE = OPTION_LAB / "data" / "BSE_FO.csv"
ELIGIBLE_EPOCH_S = float(get("ELIGIBLE_EPOCH_S", "0"))  # live-only guard (unused default)