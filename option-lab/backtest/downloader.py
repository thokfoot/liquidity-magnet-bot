import os
import time
import pandas as pd

from config import SPOT_SYMBOLS, MONTH_CODES, LOT_SIZE, STRIKE_STEP, RAW_DIR, RESULTS_DIR
from fyers import FyersClient
from symbols import (load_masters, derive_lot_and_step, build_calendar,
                     build_symbols)

FT = FyersClient(min_interval=0.7)

WINDOW_FROM = "2026-07-20"
WINDOW_TO = "2026-09-08"
TEST_FROM = "2026-08-01"
TEST_TO = "2026-09-08"

ATM_HALF_WIDTH = 6


def download_spots():
    out = {}
    for name, sym in SPOT_SYMBOLS.items():
        df = FT.fetch_and_cache(sym, WINDOW_FROM, WINDOW_TO)
        if df is None:
            print(f"[spot] {name}: NO DATA")
            continue
        out[name] = df
        print(f"[spot] {name}: {len(df)} bars, days {df['date'].dt.date.min()}..{df['date'].dt.date.max()}")
    return out


def compute_strike_universe(spots, step):
    all_strikes = set()
    for name, df in spots.items():
        if name not in STRIKE_STEP:
            continue
        s = STRIKE_STEP[name]
        sub = df[df["date"] >= pd.Timestamp(TEST_FROM)]
        atm = (sub["close"] // s * s).round(0).astype(int)
        for a in atm.unique():
            for k in range(-6, 7):
                all_strikes.add(int(a) + k * s)
    return sorted(all_strikes)


def download_options(spots):
    m = load_masters()
    lot, step = derive_lot_and_step(m)
    cal = build_calendar(m)
    cal.to_parquet(os.path.join(os.path.dirname(RAW_DIR), "expiry_calendar.parquet"))
    print("[calendar] saved")

    # expiry epoch of the Sep-29 monthly per index from calendar
    expiry_map = {}
    for name in MONTH_CODES:
        sub = cal[cal["index"] == name]
        if len(sub):
            expiry_map[name] = sub.iloc[0]["expiry_epoch"]

    meta_rows = []
    for name in MONTH_CODES:
        s = STRIKE_STEP.get(name, 50)
        strikes = sorted(last for last in compute_strike_universe({name: spots.get(name)}, s)
                         if last)
        syms = build_symbols(name, strikes)
        print(f"[opts] {name}: {len(syms)} symbols, strikes {min(strikes)}..{max(strikes)}")
        for sym in syms:
            df = FT.fetch_and_cache(sym, TEST_FROM, TEST_TO)
            if df is None:
                meta_rows.append({"symbol": sym, "ok": False, "bars": 0})
                continue
            meta_rows.append({"symbol": sym, "ok": True, "bars": len(df),
                              "days": df["date"].nunique(),
                              "first": str(df["datetime"].iloc[0]),
                              "last": str(df["datetime"].iloc[-1])})
        lz = LOT_SIZE.get(name, 0)
        print(f"[opts] {name} done. lot={lz} step={s} expiry={expiry_map.get(name)}")

    pd.DataFrame(meta_rows).to_csv(os.path.join(RESULTS_DIR, "download_meta.csv"), index=False)
    print("[download] meta saved:", len(meta_rows))


if __name__ == "__main__":
    spots = download_spots()
    pd.to_pickle({k: v[["datetime", "date", "time", "open", "high", "low", "close", "volume"]]
                  for k, v in spots.items()},
                 os.path.join(os.path.dirname(RAW_DIR), "spots.pkl"))
    download_options(spots)
    print("ALL DONE")