"""Phase 8-10 Paper-Trader: sell +/-100 OTM strangle, 25% SL / 25% premium-decay TP,
EOD force exit 15:15, loss-breaker (skip day after a loss), live from local collector files.

Run modes:
    python -m paper.paper_trader daemon     # browser market hours, fills from fresh chain/spot parquets
    python -m paper.paper_trader check      # simulate today from stored data (no broker), print result
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data_live"
LEDGER = Path(__file__).resolve().parent / "ledger.csv"
INDEX = "BANKNIFTY"
SL_PCT = 0.25
TP_PCT = 0.25
ENTRY_AT = time(9, 25)
EOD_AT = time(15, 15)
TODAY = datetime.now(timezone.utc)
IST = timezone(timedelta(hours=5, minutes=30))

# friction model (mirrors backtest/params.py)
BROKERAGE = 20.0
EXCH_RATE = 0.0005
SEBI_RATE = 1e-7
SLIP_PCT = 0.005
STT_SELL = 0.0005
GST = 0.18


def now_ist() -> datetime:
    return datetime.now(IST)


def today_str() -> str:
    return now_ist().strftime("%Y-%m-%d")


def meta() -> dict:
    p = DATA / "meta" / f"{today_str()}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def is_trading_day() -> bool:
    return now_ist().weekday() < 5


def load_spot(day: str) -> pd.DataFrame:
    p = DATA / "spot" / INDEX / f"{day}.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if "ts" in df and len(df):
        df["ts"] = df["ts"].astype(str)
    return df


def load_chain(day: str) -> pd.DataFrame:
    p = DATA / "chain" / INDEX / f"{day}.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    for col in ("ce_ltp", "pe_ltp"):
        if col in df:
            df[col] = df[col].fillna(0.0).astype(float)
    return df


def pick_expiry(chain: pd.DataFrame, spot: float) -> str:
    if "expiry" not in chain:
        return ""
    strikes = chain["strike"]
    codes = sorted(chain["expiry"].unique())
    best, best_score = "", -1
    for code in codes:
        near = chain[chain["expiry"] == code].query("strike >= @spot - 50 and strike <= @spot + 50")
        score = near["ce_ltp"].sum() + near["pe_ltp"].sum()
        if score > best_score:
            best, best_score = code, score
    return best


def friction(entry_sum: float, exit_sum: float, lot: int) -> float:
    sold = entry_sum * lot
    turnover = (entry_sum + exit_sum) * lot
    brok = BROKERAGE * 4
    exch = EXCH_RATE * turnover
    sebi = SEBI_RATE * turnover
    stt = STT_SELL * sold
    gst = GST * (brok + exch + sebi)
    return brok + exch + sebi + stt + gst


def slip(prem: float) -> float:
    return max(1.0, SLIP_PCT * prem)


def entry_strikes(spot: float, step: int) -> tuple[int, int]:
    base = round(spot / step) * step
    return base + step, base - step


def exit_reason(prem_sum: float, entry_sum: float) -> str:
    if prem_sum >= entry_sum * (1 + SL_PCT):
        return "SL"
    if entry_sum > 0 and prem_sum <= entry_sum * (1 - TP_PCT):
        return "TP"
    return ""


def read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    return pd.read_csv(LEDGER).to_dict("records")


def last_net() -> float:
    rows = read_ledger()
    prev = None
    for r in rows:
        if r.get("date") != today_str():
            prev = r
    return float(prev["net_pnl"]) if prev else 0.0


def append_ledger(date: str, spot: float, ce: int, pe: int, entry: float,
                  exitp: float, reason: str, lot: int, fees: float, net: float):
    import csv
    new = not LEDGER.exists()
    with open(LEDGER, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "index", "spot", "ce", "pe", "entry_prem",
                                          "exit_prem", "reason", "lot", "fees", "net_pnl"])
        if new:
            w.writeheader()
        w.writerow(dict(date=date, index=INDEX, spot=round(spot, 2), ce=ce, pe=pe,
                        entry_prem=round(entry, 2), exit_prem=round(exitp, 2), reason=reason,
                        lot=lot, fees=round(fees, 2), net_pnl=round(net, 2)))


def entry_snapshot(day: str) -> dict:
    spot_df = load_spot(day)
    chain = load_chain(day)
    if spot_df.empty or chain.empty:
        return {}
    target = f"{day} 09:25:00"
    sdf = spot_df.sort_values("ts")
    row = None
    for _, r in sdf.iterrows():
        if r["ts"] >= target:
            row = r
            break
    if row is None:
        return {}
    spot = float(row["close"])
    exp = pick_expiry(chain, spot)
    ce, pe = entry_strikes(spot, int(meta().get("indices", {}).get(INDEX, {}).get("step", 100)))
    cdf = chain[(chain["expiry"] == exp) & (chain["ts"] >= target)]
    if cdf.empty:
        return {}
    ce_ltp = pe_ltp = 0.0
    for _, r in cdf.sort_values("ts").iterrows():
        if r["strike"] == ce:
            ce_ltp = float(r["ce_ltp"])
        if r["strike"] == pe:
            pe_ltp = float(r["pe_ltp"])
        if ce_ltp and pe_ltp:
            break
    if not ce_ltp or not pe_ltp:
        return {}
    return dict(spot=spot, exp=exp, ce=ce, pe=pe, entry=(ce_ltp + pe_ltp),
                ce_entry=ce_ltp, pe_entry=pe_ltp)


def run_day(day: str, live: bool) -> None:
    es = entry_snapshot(day)
    m = meta().get("indices", {}).get(INDEX, {})
    lot = int(m.get("lot", 0))
    if not es or lot == 0:
        print(f"[paper] no entry snapshot/lot for {day}; skipped", flush=True)
        return
    entry = es["entry"]
    fees = friction(entry, entry, lot)
    print(f"[paper] entry day={day} spot={es['spot']:.0f} CE{es['ce']} PE{es['pe']} "
          f"prem={entry:.0f} lot={lot}", flush=True)

    if last_net() < 0:
        print("[paper] LOSS-BREAKER: previous day loss -> skip today", flush=True)
        append_ledger(day, es["spot"], es["ce"], es["pe"], entry, entry, "SKIP_LOSS", lot, 0, 0)
        return

    chain = load_chain(day)
    rows = chain[(chain["expiry"] == es["exp"])].sort_values("ts")
    reason, exit_prem = "EOD", entry
    for _, r in rows.iterrows():
        if str(r["ts"]) <= f"{day} 09:25:00":
            continue
        ce_px = float(r["ce_ltp"]) if r["strike"] == es["ce"] else 0
        pe_px = float(r["pe_ltp"]) if r["strike"] == es["pe"] else 0
        prem = ce_px + pe_px
        if prem == 0:
            continue
        reason = exit_reason(prem, entry)
        exit_prem = prem
        if reason:
            break
        if str(r["ts"]) >= f"{day} 15:15:00":
            exit_prem = prem
            reason = "EOD"
            break
    if live and reason in ("SL", "TP", "EOD"):
        exit_prem += slip(exit_prem)
    net = (entry - exit_prem) * lot - friction(entry, exit_prem, lot)
    print(f"[paper] exit reason={reason} exit_prem={exit_prem:.0f} net={net:+.0f}", flush=True)
    if live:
        append_ledger(day, es["spot"], es["ce"], es["pe"], entry, exit_prem, reason, lot,
                      friction(entry, exit_prem, lot), net)


def daemon() -> None:
    print(f"[paper] daemon start {today_str()} index={INDEX} SL={SL_PCT} TP-decay={TP_PCT}", flush=True)
    while True:
        n = now_ist()
        if is_trading_day() and n.time() >= time(9, 20) and n.time() <= time(15, 35):
            day = today_str()
            rows = read_ledger()
            if not any(r["date"] == day for r in rows):
                run_day(day, live=True)
            else:
                prev = [r for r in rows if r["date"] == day][0]
                print(f"[paper] {day} already in ledger: {prev['reason']}", flush=True)
        import time as _t
        _t.sleep(30)


def check() -> None:
    run_day(today_str(), live=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", default="check", choices=["daemon", "check"])
    args = ap.parse_args()
    if args.mode == "daemon":
        daemon()
    else:
        check()


if __name__ == "__main__":
    main()