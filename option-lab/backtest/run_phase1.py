import os
import pandas as pd

from config import RESULTS_DIR
from engine import run_backtest, summarize
from report import print_summary, daily_table, save_json
from params import (IN_SAMPLE_FROM, IN_SAMPLE_TO, OUT_SAMPLE_FROM, OUT_SAMPLE_TO,
                    ensure_meta)

ensure_meta()
SPOTS = pd.read_pickle(r"C:\Dev\Dev\Trading\option-lab\data\spots.pkl")


def split_dates():
    is_dates = [str(d.date()) for d in
                sorted(SPOTS["NIFTY"]["date"].unique()) if
                pd.Timestamp(IN_SAMPLE_FROM) <= d <= pd.Timestamp(IN_SAMPLE_TO)]
    oos_dates = [str(d.date()) for d in
                 sorted(SPOTS["NIFTY"]["date"].unique()) if
                 pd.Timestamp(OUT_SAMPLE_FROM) <= d <= pd.Timestamp(OUT_SAMPLE_TO)]
    return is_dates, oos_dates


def main():
    print("#" * 70)
    print("# PHASE 1 — BASE CASE: NIFTY monthly ATM strangle (real candles)")
    print("# entry 09:25, SL 25%, TP 40%, EOD 15:15, 1 lot x 2 legs")
    print("#" * 70)

    is_dates, oos_dates = split_dates()
    all_dates = is_dates + oos_dates
    print(f"IS days: {len(is_dates)} ({is_dates[0]}..{is_dates[-1]})")
    print(f"OOS days: {len(oos_dates)} ({oos_dates[0]}..{oos_dates[-1]})")

    res_is = run_backtest("NIFTY", SPOTS, dates=is_dates)
    res_oos = run_backtest("NIFTY", SPOTS, dates=oos_dates)
    res_all = run_backtest("NIFTY", SPOTS, dates=all_dates)

    print_summary("IN-SAMPLE (Aug 1-22)", summarize(res_is))
    print_summary("OUT-OF-SAMPLE (Aug 25-Sep 8)", summarize(res_oos))
    print_summary("FULL WINDOW", summarize(res_all))

    if res_is or res_oos:
        tbl = pd.concat([pd.DataFrame(res_is), pd.DataFrame(res_oos)])
        print("\n--- Daily table ---")
        print(tbl[["date", "spot_entry", "atm_strike", "ce_entry", "pe_entry",
                   "ce_reason", "pe_reason", "net_pnl"]].to_string(index=False))
        save_json("phase1_basecase.json", {
            "is": res_is, "oos": res_oos,
            "summaries": {
                "is": summarize(res_is), "oos": summarize(res_oos),
                "all": summarize(res_all)
            }})


if __name__ == "__main__":
    main()