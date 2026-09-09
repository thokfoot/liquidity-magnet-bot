import os
import glob
import pandas as pd

from config import RAW_DIR, MONTH_CODES
from params import (friction_calc, get_lot, get_step, SL_PCT, TP_PCT,
                    ENTRY_TIME, EXIT_TIME, ATM_HALF_WIDTH)


def load_option_df(symbol, opt_cache=None):
    if opt_cache is not None and symbol in opt_cache:
        return opt_cache[symbol]
    fpat = os.path.join(RAW_DIR, symbol.replace(":", "_") + "_-_*.parquet")
    hits = glob.glob(fpat)
    if not hits:
        return None
    return pd.read_parquet(hits[0])


def load_index_cache(index):
    """Preload all cached parquet dfs for an index into {symbol: df}."""
    pat = os.path.join(RAW_DIR, "NSE_" + MONTH_CODES[index] + "*.parquet")
    cache = {}
    for f in glob.glob(pat):
        name = os.path.basename(f).split("_-_")[0]  # 'NSE_NIFTY26SEP24550CE'
        symbol = "NSE:" + name[name.find("_") + 1:]
        cache[symbol] = pd.read_parquet(f)
    return cache


def _day_df(df, date):
    d = df[df["date"] == pd.Timestamp(date)]
    return d.sort_values("datetime").reset_index(drop=True)


def _price_at(df, date, time_str, col="close"):
    d = _day_df(df, date)
    if d.empty:
        return None
    row = d[d["time"] == time_str]
    if row.empty:
        # fall back to the last bar at/before the requested time
        pre = d[d["time"] <= time_str]
        if pre.empty:
            return None
        row = pre.iloc[[-1]]
    return float(row.iloc[0][col])


def _bars_from(df, date, start_time, stop_time):
    d = _day_df(df, date)
    mask = (d["time"] >= start_time) & (d["time"] <= stop_time)
    return d[mask].reset_index(drop=True)


def run_daily_leg(call_df, put_df, spot_df, date, index, price_opts, opt_cache=None):
    """Run one day's intraday strangle for `index`.
    Returns dict with per-leg + net PnL (₹) or None if data insufficient.
    """
    lot = get_lot(index)
    if not lot:
        return None
    step = get_step(index)

    entry_time = price_opts["entry_time"]
    exit_time = price_opts["exit_time"]
    sl_pct = price_opts["sl_pct"]
    tp_pct = price_opts["tp_pct"]

    spot_entry = _price_at(spot_df, date, entry_time)
    if spot_entry is None:
        return None
    atm = int(round(spot_entry / step) * step)

    call_symbol = f"NSE:{MONTH_CODES[index]}{atm}CE"
    put_symbol = f"NSE:{MONTH_CODES[index]}{atm}PE"

    cdf = call_df if call_df is not None else load_option_df(call_symbol, opt_cache)
    pdf = put_df if put_df is not None else load_option_df(put_symbol, opt_cache)
    if cdf is None or pdf is None:
        return None

    bars_c = _bars_from(cdf, date, entry_time, exit_time)
    bars_p = _bars_from(pdf, date, entry_time, exit_time)
    if bars_c.empty or bars_p.empty:
        return None

    entry_row = bars_c.iloc[0]
    entry_px_c = float(entry_row["close"])
    entry_row_p = bars_p.iloc[0]
    entry_px_p = float(entry_row_p["close"])
    if entry_px_c <= 0 or entry_px_p <= 0:
        return None

    slip = {
        "c": max(1.0, SLIP(entry_px_c)),
        "p": max(1.0, SLIP(entry_px_p)),
    }

    def scan(bars, entry_px, side):
        sl_price = entry_px * (1 + sl_pct)
        tp_price = entry_px * (1 - tp_pct)
        last_px = entry_px
        reason = "EOD"
        for _, row in bars.iterrows():
            last_px = float(row["close"])
            if last_px >= sl_price:
                reason = "SL"
                break
            if last_px <= tp_price:
                reason = "TP"
                break
        return last_px, reason

    exit_c, reason_c = scan(bars_c.iloc[1:], entry_px_c, "sell")
    exit_p, reason_p = scan(bars_p.iloc[1:], entry_px_p, "sell")

    pnl_c = (entry_px_c - exit_c) * lot
    pnl_p = (entry_px_p - exit_p) * lot
    fr_c = friction_calc(entry_px_c, exit_c, lot, sell_side=True)
    fr_p = friction_calc(entry_px_p, exit_p, lot, sell_side=True)
    slip_c = (slip["c"] + SLIP(exit_c)) * lot
    slip_p = (slip["p"] + SLIP(exit_p)) * lot

    return {
        "date": str(date),
        "index": index,
        "spot_entry": round(spot_entry, 2),
        "atm_strike": atm,
        "ce_entry": round(entry_px_c, 2), "pe_entry": round(entry_px_p, 2),
        "ce_exit": round(exit_c, 2), "pe_exit": round(exit_p, 2),
        "ce_reason": reason_c, "pe_reason": reason_p,
        "pnl_c": round(pnl_c, 2), "pnl_p": round(pnl_p, 2),
        "friction": round(fr_c + fr_p + slip_c + slip_p, 2),
        "net_pnl": round(pnl_c + pnl_p - fr_c - fr_p - slip_c - slip_p, 2),
    }


def SLIP(px):
    return max(1.0, 0.005 * px)


def run_backtest(index, spots, call_cache=None, put_cache=None,
                 entry_time=ENTRY_TIME, exit_time=EXIT_TIME,
                 sl_pct=SL_PCT, tp_pct=TP_PCT, dates=None, opt_cache=None):
    """Run daily strangle backtest for `index` over list of dates.
    Returns list of daily result dicts (only days with complete data).
    """
    spot_df = spots.get(index)
    if spot_df is None:
        return []
    spot_df = spot_df.sort_values("datetime").reset_index(drop=True)
    day_dates = sorted(spot_df["date"].dt.date.astype(str).unique())
    if dates is not None:
        day_dates = [d for d in day_dates if d in dates]

    opts = {"entry_time": entry_time, "exit_time": exit_time,
            "sl_pct": sl_pct, "tp_pct": tp_pct}
    results = []
    for d in day_dates:
        r = run_daily_leg(call_cache, put_cache, spot_df, d, index, opts, opt_cache)
        if r is not None:
            results.append(r)
    return results


def summarize(results):
    if not results:
        return None
    df = pd.DataFrame(results)
    wins = df[df["net_pnl"] > 0]
    losses = df[df["net_pnl"] <= 0]
    gross_win = wins["net_pnl"].sum()
    gross_loss = losses["net_pnl"].sum()
    return {
        "days": len(df),
        "win_days": len(wins),
        "loss_days": len(losses),
        "win_rate": round(100.0 * len(wins) / len(df), 1),
        "net_pnl": round(df["net_pnl"].sum(), 2),
        "avg_pnl": round(df["net_pnl"].mean(), 2),
        "worst_day": round(df["net_pnl"].min(), 2),
        "best_day": round(df["net_pnl"].max(), 2),
        "profit_factor": round(abs(gross_win / gross_loss), 2) if gross_loss else float("inf"),
        "sl_hit_days": int(((df["ce_reason"] == "SL") | (df["pe_reason"] == "SL")).sum()),
        "avg_premium": round(df[["ce_entry", "pe_entry"]].mean(axis=0).mean(), 2),
    }