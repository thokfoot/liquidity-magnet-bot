"""Local collector runner: quote snapshots -> minute bars -> parquet -> GCS.

Run options:
    python -m collector.run_collector --auto        (default; market-day loop)
    python -m collector.run_collector --once        (one snapshot + flush + exit)
    python -m collector.run_collector --backfill    (EOD history upgrade only)
    python -m collector.run_collector --health-only (serve /healthz only)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import sys
import threading
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ZONE = dt.timezone(dt.timedelta(hours=5, minutes=30))

OPTION_LAB = Path(__file__).resolve().parents[1]
if str(OPTION_LAB) not in sys.path:
    sys.path.insert(0, str(OPTION_LAB))

from collector import config as C  # noqa: E402
from collector.discover import (discover, live_expiry_codes, month_code)  # noqa: E402
from collector.fyers_api import FyersAPI  # noqa: E402
from collector.minute import SnapshotAggregator, chain_df_to_rows  # noqa: E402
from collector.schema import local, write_frame, write_meta  # noqa: E402
from collector import gcs  # noqa: E402
from collector.tokens import ensure_valid_tokens  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("collector")

INDEX_NAME = {"NSE:NIFTY50-INDEX": "NIFTY", "NSE:NIFTYBANK-INDEX": "BANKNIFTY",
              "NSE:FINNIFTY-INDEX": "FINNIFTY", "NSE:MIDCPNIFTY-INDEX": "MIDCPNIFTY"}
# option symbol prefix per index (spot symbols differ: NIFTYBANK-INDEX vs BANKNIFTY...)
RAW_PREFIX = {"NIFTY": "NIFTY", "BANKNIFTY": "BANKNIFTY",
              "FINNIFTY": "FINNIFTY", "MIDCPNIFTY": "MIDCPNIFTY"}


def ist() -> dt.datetime:
    return dt.datetime.now(ZONE)


def classify(sym: str):
    """Return ('spot'|'opts', index, file_tail) for a Fyers symbol."""
    if sym in INDEX_NAME:
        return ("spot", INDEX_NAME[sym], "")
    for raw, idx in (("NIFTYBANK", "BANKNIFTY"), ("BANKNIFTY", "BANKNIFTY"),
                     ("NIFTY", "NIFTY"),
                     ("FINNIFTY", "FINNIFTY"), ("MIDCPNIFTY", "MIDCPNIFTY")):
        prefix = f"NSE:{raw}"
        if sym.startswith(prefix):
            m = re.match(r"(\d{2})([A-Z]{3})(\d+)(CE|PE)", sym[len(prefix):])
            if not m or int(m.group(3)) == 0:
                return ("unknown", "-", "")
            return ("opts", idx, f"{m.group(1)}{m.group(2)}_{m.group(3)}_{m.group(4)}")
    return ("unknown", "-", "")


def sel_df(rows: list[dict]):
    import pandas as pd
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"]).dt.floor("min")
    df["__k"] = df["ts"].dt.strftime("%Y-%m-%d %H:%M").astype(str) + "|" + \
        df["expiry"].astype(str) + "|" + df["strike"].astype(str)
    return df.drop_duplicates("__k", keep="last")


def frame_to_records(df: object) -> list[dict]:
    import pandas as pd
    if isinstance(df, pd.DataFrame):
        return df.to_dict("records")
    return df or []


class Collector:
    def __init__(self, api: FyersAPI):
        self.api = api
        self.meta = discover()
        self.agg = SnapshotAggregator()
        self.spot_agg = SnapshotAggregator()
        self.day = ist().strftime("%Y-%m-%d")
        self.state = "booting"
        self.last_tick_ts = None
        self.last_chain_ts = None
        self.chain_min = -1
        self._last_sync = 0.0
        self._backfilled = False
        self.live_exps: dict[str, list[tuple[int, str, str]]] = {}

    # ------------------------------------------------------------ preflight
    def preflight(self) -> None:
        self.day = ist().strftime("%Y-%m-%d")
        for index, info in self.meta.items():
            live = live_expiry_codes(self.api, index, C.INDICES[index], self.meta)
            self.live_exps[index] = live or info["expiries"]
            log.info("[preflight] %s live expiries=%s (W/M flags)",
                     index, [(month_code(e), f) for e, _c, f in self.live_exps[index]][:6])
        write_meta(self.day, {
            "generated_by": "collector.preflight",
            "indices": {i: {"expiries": [c for _, c in v["expiries"]],
                            "step": v["step"], "lot": v["lot"]}
                        for i, v in self.meta.items()},
            "today_expiries": {i: [(e, mc, f) for e, mc, f in v[:6]]
                               for i, v in self.live_exps.items()},
        })
        self.state = "ready"

    # ------------------------------------------------------- symbol builders
    def stream_symbols(self, index: str) -> list[str]:
        info = self.meta.get(index)
        if not info:
            return [C.INDICES[index]]
        exps = (self.live_exps.get(index) or info["expiries"])[:2]
        step = info["step"]
        last = self._last_spot(index)
        atm = int(round(last / step) * step) if last else 0
        raw = RAW_PREFIX.get(index, index)
        syms = [C.INDICES[index]]
        for e in exps:
            code = e[1] if len(e) > 1 else e
            base = f"NSE:{raw}{code}"
            for k in range(-C.STREAM_HALF_WIDTH[index], C.STREAM_HALF_WIDTH[index] + 1):
                st = atm + k * step
                syms.append(f"{base}{st}CE")
                syms.append(f"{base}{st}PE")
        return syms

    def _last_spot(self, index: str) -> float | None:
        key = C.INDICES[index]
        bucket = self.spot_agg._bars.get(key, {})
        if not bucket:
            return None
        return bucket[max(bucket)]["close"]

    # ------------------------------------------------------------- snapshot
    def snapshot_ticks(self, now: dt.datetime) -> int:
        pushed = 0
        for index, sym in C.INDICES.items():
            syms = self.stream_symbols(index) if self.meta.get(index) else [sym]
            quotes = self.api.quote_batch(syms)
            for name, q in quotes.items():
                if q.get("ltp") is None:
                    continue
                agg = self.spot_agg if name in INDEX_NAME else self.agg
                agg.push(name, now, float(q["ltp"]), q.get("oi") or 0.0,
                         q.get("vol") or 0.0)
                pushed += 1
        self.last_tick_ts = now
        return pushed

    def snapshot_chain(self, now: dt.datetime) -> int:
        rows = defaultdict(list)
        n = 0
        for index, info in self.meta.items():
            exps = (self.live_exps.get(index) or info["expiries"])[:5]
            for e in exps:
                epoch = e[0]
                od = self.api.optionchain(C.INDICES[index], epoch,
                                          C.CHAIN_STRIKE_COUNT[index])
                if not od:
                    continue
                for r in chain_df_to_rows(now, index, od, epoch):
                    rows[index].append(r)
                    n += 1
        day = now.strftime("%Y-%m-%d")
        for index, lst in rows.items():
            if lst:
                p = local(C.DATA_ROOT, day, "chain", index)
                write_frame(p, sel_df(lst).drop(columns=["__k"], errors="ignore"),
                            drop_key=["ts", "expiry", "strike"])
        self.chain_min = now.minute
        self.last_chain_ts = now
        return n

    # ---------------------------------------------------------------- flush
    def flush_frames(self) -> int:
        """Upsert closed minute rows from both aggregators into parquet."""
        n = 0
        cutoff = ist() - dt.timedelta(seconds=5)
        for agg, kind in ((self.spot_agg, "spot"), (self.agg, "opts")):
            df = agg.finalize(cutoff)
            if df.empty:
                continue
            for key, g in df.groupby("symbol"):
                kind2, index, tail = classify(key)
                if kind2 != kind:
                    continue
                if kind == "spot":
                    g = g.rename(columns={"vol": "volume"})
                    g["source"] = "collector"
                    cols = ["ts", "open", "high", "low", "close", "volume", "source"]
                    p = local(C.DATA_ROOT, self.day, "spot", index)
                else:
                    cols = ["ts", "open", "high", "low", "close", "vol", "oi", "n"]
                    p = local(C.DATA_ROOT, self.day, "opts", index,
                              f"{tail}.parquet")
                n += write_frame(p, g[cols], drop_key="ts")
        return n

    def flush_chain_jsonl(self, rows: list[dict], csv=False):  # noqa: ARG002
        """Unused; chain goes to parquet via flush chain(). Kept for parity."""
        return 0


def collection_symbols() -> list[str]:
    """Rebuild the Fyers symbol list from already-written parquet tails."""
    syms = []
    for idx, spot_sym in C.INDICES.items():
        p = C.DATA_ROOT / "spot" / idx
        if p.exists() and any(p.glob("*.parquet")):
            syms.append(spot_sym)
    root = C.DATA_ROOT / "opts"
    if root.exists():
        # opts/<index>/<day>/<code>_<CE|PE>_<strike>.parquet
        for f in root.glob("*/*/*_*_*.parquet"):
            parts = f.stem.split("_")
            if len(parts) == 3:
                syms.append(f"NSE:{parts[0]}{parts[2]}{parts[1]}")
    return syms


def backfill_day(col: Collector, day_str: str) -> int:
    """EOD: replace snapshot-derived minute rows with true 1-min history bars."""
    from2 = f"{day_str} 09:15:00"
    to2 = f"{day_str} 15:35:00"
    upgraded = 0
    for sym in sorted(set(collection_symbols())):
        candles = col.api.history(sym, from2, to2, resolution=1)
        kind, index, tail = classify(sym)
        if not candles:
            continue
        import pandas as pd
        df = pd.DataFrame(candles, columns=["epoch", "open", "high", "low",
                                            "close", "volume"])
        ts = pd.to_datetime(df["epoch"], unit="s") + pd.Timedelta(hours=5, minutes=30)
        df["ts"] = ts.dt.floor("min")
        df = df[(df["ts"].dt.date == pd.Timestamp(day_str).date())]
        if kind == "spot":
            df["source"] = "history"
            cols = ["ts", "open", "high", "low", "close", "volume", "source"]
            p = local(C.DATA_ROOT, day_str, "spot", index)
        else:
            df["oi"] = 0
            df["n"] = 1
            cols = ["ts", "open", "high", "low", "close", "volume", "oi", "n"]
            if tail:
                cols = ["ts", "open", "high", "low", "close", "volume", "oi", "n"]
            p = local(C.DATA_ROOT, day_str, "opts", index, f"{tail}.parquet")
        write_frame(p, df[cols], drop_key="ts")
        upgraded += len(df)
    return upgraded


def sync_now() -> int:
    if not gcs.enabled():
        return 0
    if not C.DATA_ROOT.exists():
        return 0
    return gcs.sync_tree(C.DATA_ROOT)


# ------------------------------------------------------------------ health
class H(BaseHTTPRequestHandler):
    collector = None

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        c = H.collector
        if self.path in ("/healthz", "/", "/status"):
            self._send(200, {
                "status": c.state, "day": c.day,
                "last_tick": c.last_tick_ts.strftime("%H:%M:%S") if c.last_tick_ts else "-",
                "last_chain": c.last_chain_ts.strftime("%H:%M:%S") if c.last_chain_ts else "-",
                "gcs": gcs.enabled(),
            })
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *a):  # noqa: A003
        pass


def start_health(collector) -> ThreadingHTTPServer:
    H.collector = collector
    srv = ThreadingHTTPServer(("0.0.0.0", C.PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info("health server on :%d", C.PORT)
    return srv


# -------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--health-only", action="store_true")
    args = ap.parse_args()

    if not args.health_only:
        cid, tok = ensure_valid_tokens()
        api = FyersAPI(cid, tok, gap=C.CALL_GAP)
        col = Collector(api)
        col.preflight()
    else:
        api, col = None, Collector(api_fake())

    start_health(col)

    if args.health_only:
        log.info("health-only mode; Ctrl+C to stop")
        while True:
            time.sleep(60)

    if args.once:
        now = ist()
        n_tick = col.snapshot_ticks(now)
        n_chain = col.snapshot_chain(now)
        rows = col.flush_frames()
        log.info("once: ticks=%d chain=%d flushed=%d", n_tick, n_chain, rows)
        sync_now()
        return 0

    if args.backfill:
        rows = backfill_day(col, ist().strftime("%Y-%m-%d"))
        log.info("backfill upgraded rows=%d", rows)
        sync_now()
        return 0

    log.info("day loop start at %s", ist().strftime("%Y-%m-%d %H:%M:%S"))
    while True:
        now = ist()
        cur = now.strftime("%H:%M:%S")
        col.state = "running" if C.START <= cur <= C.END else "idle"

        if C.START <= cur <= C.END:
            if now.second % C.TICK_SECONDS < 2:
                try:
                    col.snapshot_ticks(now)
                except Exception as exc:  # noqa: BLE001
                    log.warning("tick error: %s", exc)
            if now.second % C.CHAIN_SECONDS < 2 and now.minute != col.chain_min:
                try:
                    col.snapshot_chain(now)
                except Exception as exc:  # noqa: BLE001
                    log.warning("chain error: %s", exc)
            if now.minute % 5 == 0 and now.minute != 0 and now.second < 2:
                rows = col.flush_frames()
                if rows:
                    log.info("flush wrote %d rows", rows)
            if time.time() - col._last_sync > C.SYNC_SECONDS:
                n = sync_now()
                col._last_sync = time.time()
                if n:
                    log.info("gcs synced %d files", n)
        else:
            # outside market hours: one final backfill + sync, then idle quietly
            if not col._backfilled and cur >= C.BACKFILL_AT:
                rows = backfill_day(col, ist().strftime("%Y-%m-%d"))
                log.info("EOD backfill upgraded rows=%d", rows)
                col._backfilled = True
                sync_now()
            time.sleep(60)

        time.sleep(1.0)


def api_fake():
    class _F:
        def __getattr__(self, _k):
            raise RuntimeError("health-only mode")
    return _F()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("stopped")
        sys.exit(0)