import os

BASE_DIR = r"C:\Dev\Dev\Trading\option-lab"
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
MASTER_NSE = os.path.join(DATA_DIR, "NSE_FO.csv")
MASTER_BSE = os.path.join(DATA_DIR, "BSE_FO.csv")

AUTH = "L0I73P22YA-100:eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiZDoxIiwiZDoyIiwieDowIiwieDoxIl0sImF0X2hhc2giOiJnQUFBQUFCcW4zWE1uRVE2SThNUG90bHM0cE1PU1dsd1lweW00eFNjYmhYMzVncEVYTnlqZ3ZQQzJUNy1HMWhvSVB4ckNUaVAyNXV5NnFjeFpseUotUm1jQ2t4dzdUVVBZajBCdEg4TXBSWkd6Um41VmtIN2ZzTT0iLCJkaXNwbGF5X25hbWUiOiIiLCJvbXMiOiJLMSIsImhzbV9rZXkiOiIyMGJmMWI3ZGI4MGIzMjRhNGQ4NzYxNmE3MGI0MThlNjg0MGU2ZDYzMzY3NDA2MGQ4YjFlYjU4NCIsImlzRGRwaUVuYWJsZWQiOiJOIiwiaXNNdGZFbmFibGVkIjoiTiIsImZ5X2lkIjoiRkFENjc4ODYiLCJhcHBUeXBlIjoxMDAsImV4cCI6MTc4ODkxMzgwMCwiaWF0IjoxNzg4ODM1Mjc2LCJpc3MiOiJhcGkuZnllcnMuaW4iLCJuYmYiOjE3ODg4MzUyNzYsInN1YiI6ImFjY2Vzc190b2tlbiJ9.5psNLIyG2AvFG4uukrs--S1RrMiQczNT3jfeJM9XJYU"

HISTORY_URL = "https://api-t1.fyers.in/data/history"

# ---- Session / timing ----
MARKET_OPEN_IST = "09:15:00"
MARKET_CLOSE_IST = "15:30:00"

# ---- Index metadata ----
SPOT_SYMBOLS = {
    "NIFTY": "NSE:NIFTY50-INDEX",
    "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
    "FINNIFTY": "NSE:FINNIFTY-INDEX",
    "MIDCPNIFTY": "NSE:MIDCPNIFTY-INDEX",
    "SENSEX": "BSE:SENSEX-INDEX",
}

# monthly-contract code used in Fyers symbols for the Sep 29 expiry
MONTH_CODES = {
    "NIFTY": "NIFTY26SEP",
    "BANKNIFTY": "BANKNIFTY26SEP",
    "FINNIFTY": "FINNIFTY26SEP",
    "MIDCPNIFTY": "MIDCPNIFTY26SEP",
}

# known lot & strike-step fallbacks (overwritten from master files at runtime)
LOT_SIZE = {}
STRIKE_STEP = {}

for _d in (DATA_DIR, RAW_DIR, RESULTS_DIR):
    os.makedirs(_d, exist_ok=True)