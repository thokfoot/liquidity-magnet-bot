"""Thin wrapper over the official fyers_apiv3 SDK (quotes/optionchain/history)."""
from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)


def build_model(client_id: str, token: str) -> tuple:
    from fyers_apiv3.fyersModel import FyersModel

    model = FyersModel(client_id=client_id, token=token,
                       is_async=False, log_path=None, log_level="ERROR")
    return model


# ---------------------------------------------------------------- throttling
class _Gate:
    def __init__(self, gap: float):
        self.gap = gap
        self.last = 0.0

    def wait(self):
        wait = self.gap - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.time()


class FyersAPI:
    """Rate-limited facade over quotes(), optionchain(), history()."""

    def __init__(self, client_id: str, token: str, gap: float = 0.45):
        self.client_id = client_id
        self.model = build_model(client_id, token)
        self.gate = _Gate(gap)

    # -------------------------------------------------------------- helpers
    def quote_batch(self, symbols: list[str]):
        """chunked (<=QUOTE_BATCH) SDK quotes() call -> {symbol: parsed}."""
        from . import config as C

        out = {}
        for i in range(0, len(symbols), C.QUOTE_BATCH):
            chunk = symbols[i:i + C.QUOTE_BATCH]
            self.gate.wait()
            resp = self.model.quotes(data={"symbols": ",".join(chunk)})
            for item in (resp or {}).get("d", []):
                v = item.get("v") or {}
                out[item.get("n")] = {
                    "ltp": v.get("lp"),
                    "oi": v.get("oi"),
                    "vol": v.get("volume"),
                    "ts": v.get("ts"),
                    "lp_ts": v.get("lp_ts"),
                }
        return out

    def optionchain(self, spot_symbol: str, expiry_epoch: int, strikecount: int) -> dict | None:
        """Return the chain payload (v3: {'code':200,'data':{...optionsChain,expiryData,...}}).

        Legacy shape ({'s':'ok','option_data':...}) is also accepted if returned.
        """
        self.gate.wait()
        resp = self.model.optionchain(data={
            "symbol": spot_symbol, "timestamp": expiry_epoch, "strikecount": strikecount,
        })
        if not resp or not isinstance(resp, dict):
            return None
        data = resp.get("data")
        if isinstance(data, dict) and ("optionsChain" in data or "expiryData" in data):
            return data
        if resp.get("s") == "ok":
            return resp.get("option_data")
        log.warning("optionchain fail %s/%s: %s", spot_symbol, expiry_epoch,
                    str(resp)[:200])
        return None

    def history(self, symbol: str, range_from: str, range_to: str,
                resolution: int = 1, retries: int = 3):
        """Return list of [epoch,o,h,l,c,v] candles or None."""
        from .minute import minute_key
        _ = minute_key
        for attempt in range(retries):
            self.gate.wait()
            try:
                resp = self.model.history(data={
                    "symbol": symbol, "resolution": resolution, "date_format": 1,
                    "range_from": range_from, "range_to": range_to, "cont_flag": 0,
                })
            except Exception as exc:  # noqa: BLE001 - network/SDK crash
                log.warning("history %s attempt %d failed: %s", symbol, attempt, exc)
                time.sleep(1.5 * (attempt + 1))
                continue
            if not resp or resp.get("s") != "ok":
                if resp and "Invalid" in str(resp.get("message", "")):
                    return None
                time.sleep(1.5 * (attempt + 1))
                continue
            return (resp or {}).get("candles") or []
        return []