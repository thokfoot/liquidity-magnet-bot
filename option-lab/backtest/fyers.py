import os
import time
import requests
import pandas as pd

from config import AUTH, HISTORY_URL, RAW_DIR


class FyersClient:
    def __init__(self, auth=None, min_interval=0.8):
        self.headers = {"Authorization": auth or AUTH}
        self.min_interval = min_interval
        self._last_call = 0.0

    def _throttle(self):
        wait = self.min_interval - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def history(self, symbol, range_from, range_to, resolution=1, retries=4):
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": 1,
            "range_from": range_from,
            "range_to": range_to,
            "cont_flag": 0,
        }
        for attempt in range(retries):
            self._throttle()
            try:
                r = requests.get(HISTORY_URL, headers=self.headers, params=params, timeout=60)
                d = r.json()
            except Exception as e:
                d = {"s": "e", "message": str(e)}
            if d.get("s") in ("error", "e"):
                if "Invalid" in str(d.get("message", "")):
                    return None
                time.sleep(2 * (attempt + 1))
                continue
            candles = d.get("candles", [])
            return candles
        return []

    def fetch_and_cache(self, symbol, range_from, range_to, resolution=1):
        """Fetch 1-min history and cache as parquet. Returns df or None."""
        fname = "%s_-_%s_to_%s.parquet" % (symbol.replace(":", "_"), range_from, range_to)
        path = os.path.join(RAW_DIR, fname)
        if os.path.exists(path):
            return pd.read_parquet(path)
        candles = self.history(symbol, range_from, range_to, resolution)
        if candles is None:
            return None
        if not candles:
            return None
        df = candles_to_df(candles)
        if len(df) == 0:
            return None
        df.to_parquet(path)
        return df


def candles_to_df(candles):
    df = pd.DataFrame(candles, columns=["epoch", "open", "high", "low", "close", "volume"])
    ts = pd.to_datetime(df["epoch"], unit="s") + pd.Timedelta(hours=5, minutes=30)  # IST
    df["datetime"] = ts
    df["date"] = ts.dt.normalize()
    df["time"] = ts.dt.strftime("%H:%M:%S")
    df = df[(ts.dt.time >= pd.Timestamp("09:15:00").time())
            & (ts.dt.time <= pd.Timestamp("15:30:00").time())]
    return df.reset_index(drop=True)