"""Backfill a missing intraday window into today's opts parquets from the Fyers
history API, then re-sync to GCS. Run after market close.

    python -m scripts.backfill_gap                 # default 09:15-10:45 IST, today
    python -m scripts.backfill_gap --start 09:10 --end 11:00
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "option-lab"))

from collector import config as C  # noqa: E402  (reads .env; must import after sys.path)
from collector.gcs import sync_tree  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
DATA = APP / "data_live"
HIST = "https://api-t1.fyers.in/data/history"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
PREFIX = {"NIFTY": "NSE:NIFTY", "BANKNIFTY": "NSE:BANKNIFTY",
          "FINNIFTY": "NSE:FINNIFTY", "MIDCPNIFTY": "NSE:MIDCPNIFTY"}


def epoch_sec(hm: str, day: str) -> int:
    dt = datetime.strptime(f"{day} {hm}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    return int(dt.timestamp())


def symbol_for(index: str, filename: str) -> str:
    stem = filename[:-8]  # -> 26OCT_56300_CE
    sym, strike, typ = stem.split("_")
    return f"{PREFIX[index]}{sym}{strike}{typ}"


def fetch_history(symbol: str, frm_sec: int, to_sec: int) -> list:
    q = (f"?symbol={urllib.parse.quote(symbol)}&resolution=1&date_format=0"
         f"&range_from={frm_sec}&range_to={to_sec}&cont_flag=1")
    req = urllib.request.Request(HIST + q, headers={
        "Authorization": f"{C.FYERS_CLIENT_ID}:{C.FYERS_ACCESS_TOKEN}", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    if data.get("s") != "ok":
        raise RuntimeError(f"{symbol}: {data.get('s')} {data}")
    return data["candles"]


def candle_to_row(c) -> dict:
    ts0 = c[0]
    if ts0 > 10 ** 11:
        ts0 /= 1000
    ts = datetime.fromtimestamp(ts0, tz=timezone.utc).astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
    return dict(ts=ts, open=float(c[1]), high=float(c[2]), low=float(c[3]),
                close=float(c[4]), vol=int(c[5]), oi=0, n=1)


def merge_into(df: pd.DataFrame, rows: list) -> pd.DataFrame:
    if not rows:
        return df
    if len(df) and "ts" in df and not all(isinstance(v, str) for v in df["ts"].head(1)):
        df = df.assign(ts=pd.to_datetime(df["ts"]).dt.strftime("%Y-%m-%d %H:%M:%S"))
    out = pd.concat([df, pd.DataFrame(rows)]) if len(df) else pd.DataFrame(rows)
    out = out.drop_duplicates(subset=["ts"], keep="last").sort_values("ts")
    return out[["ts", "open", "high", "low", "close", "vol", "oi", "n"]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="09:15")
    ap.add_argument("--end", default="10:45")
    ap.add_argument("--day", default=datetime.now(IST).strftime("%Y-%m-%d"))
    ap.add_argument("--sync", action="store_true", help="re-sync data_live to GCS after merge")
    args = ap.parse_args()

    if not C.FYERS_ACCESS_TOKEN:
        print("[backfill] no FYERS_ACCESS_TOKEN in env/.env", flush=True)
        return

    files = []
    opts_root = DATA / "opts"
    if opts_root.exists():
        for idx in sorted(opts_root.iterdir()):
            if not idx.is_dir():
                continue
            p = opts_root / idx.name / args.day
            if p.exists():
                files += [(idx.name, f.name, f) for f in p.glob("*.parquet")]
    if not files:
        print(f"[backfill] no opts files for day {args.day}", flush=True)
        return

    frm, to = epoch_sec(args.start, args.day), epoch_sec(args.end, args.day)
    print(f"[backfill] window {args.start}-{args.end} IST day={args.day} files={len(files)}", flush=True)

    done = fail = added = skipped = 0
    for index, name, path in files:
        symbol = symbol_for(index, name)
        df = pd.read_parquet(path) if path.exists() else pd.DataFrame()
        if len(df) and "ts" in df:
            ts = df["ts"].astype(str)
            in_win = ts.between(f"{args.day} {args.start}:00", f"{args.day} {args.end}:59")
            if bool(in_win.any()):
                skipped += 1
                continue
        candles = []
        for attempt in range(3):
            try:
                candles = fetch_history(symbol, frm, to)
                break
            except Exception as exc:
                print(f"[backfill] {name} attempt{attempt + 1}: {exc}", flush=True)
                time.sleep(2 + attempt * 3)
        if not candles:
            fail += 1
            continue
        merged = merge_into(df, [candle_to_row(c) for c in candles])
        n_new = max(0, len(merged) - len(df))
        merged.to_parquet(path)
        added += n_new
        print(f"[backfill] {name}: +{n_new} rows (total {len(merged)})", flush=True)
        done += 1
        time.sleep(0.7)

    print(f"[backfill] done={done} failed={fail} added={added} already_had={skipped}", flush=True)
    if args.sync:
        n = sync_tree(DATA)
        print(f"[backfill] GCS synced {n} files", flush=True)


if __name__ == "__main__":
    main()