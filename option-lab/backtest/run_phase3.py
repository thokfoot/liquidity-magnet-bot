import pandas as pd

from config import RESULTS_DIR
from engine import run_backtest, summarize, load_index_cache
from report import save_json
from params import (IN_SAMPLE_FROM, IN_SAMPLE_TO, OUT_SAMPLE_FROM, OUT_SAMPLE_TO,
                    SL_PCT, TP_PCT, ENTRY_TIME, EXIT_TIME, ensure_meta)

ensure_meta()
SPOTS = pd.read_pickle(r"C:\Dev\Dev\Trading\option-lab\data\spots.pkl")
EXPIRY = pd.Timestamp("2026-09-29")  # traded monthly contract (Sep-29 expiry)


def dte_trading(date_str):
    d = pd.Timestamp(date_str)
    return len([x for x in SPOTS["NIFTY"]["date"].unique() if d < x <= EXPIRY])


def run_index(index, dates):
    r = run_backtest(index, SPOTS, entry_time=ENTRY_TIME, exit_time=EXIT_TIME,
                     sl_pct=SL_PCT, tp_pct=TP_PCT, dates=dates,
                     opt_cache=load_index_cache(index))
    if not r:
        return [], None
    for row in r:
        row["dte"] = dte_trading(row["date"])
    return r, summarize(r)


def main():
    print("#" * 70)
    print("# PHASE 3 — INDEX x DTE DISCOVERY (monthly Sep-29 contracts)")
    print("# base config: entry 09:25, SL 25%, TP 40%, EOD 15:15")
    print("#" * 70)

    is_dates = [str(d.date()) for d in SPOTS["NIFTY"]["date"].unique()
                if pd.Timestamp(IN_SAMPLE_FROM) <= d <= pd.Timestamp(IN_SAMPLE_TO)]
    oos_dates = [str(d.date()) for d in SPOTS["NIFTY"]["date"].unique()
                 if pd.Timestamp(OUT_SAMPLE_FROM) <= d <= pd.Timestamp(OUT_SAMPLE_TO)]
    all_dates = is_dates + oos_dates

    print(f"{'INDEX':<11}{'DAYS':>5}{'WIN%':>6}{'NET_IS':>10}{'NET_OOS':>10}"
          f"{'NET_ALL':>11}{'PF':>6}{'WORST':>9}{'SLHIT':>6}{'AVG_DTE':>8}")
    payload = {}
    for idx in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]:
        r_is, s_is = run_index(idx, is_dates)
        r_oos, s_oos = run_index(idx, oos_dates)
        r_all, s_all = run_index(idx, all_dates)
        payload[idx] = {"is": r_is, "oos": r_oos, "all": r_all}
        if s_is is None:
            print(f"{idx:<11}  NO DATA")
            continue
        avg_dte = round(sum(x["dte"] for x in r_all) / len(r_all), 1) if r_all else None
        print(f"{idx:<11}{s_all['days']:>5}{s_all['win_rate']:>6.1f}"
              f"{s_is['net_pnl']:>10,.0f}{s_oos['net_pnl']:>10,.0f}"
              f"{s_all['net_pnl']:>11,.0f}{s_all['profit_factor']:>6.2f}"
              f"{s_all['worst_day']:>9,.0f}{s_all['sl_hit_days']:>6}{avg_dte:>8.1f}")

    # per-index daily logs
    for idx, d in payload.items():
        if d.get("all"):
            df = pd.DataFrame(d["all"])
            print(f"\n--- {idx} daily ---")
            print(df[["date", "dte", "spot_entry", "atm_strike", "ce_entry",
                      "pe_entry", "ce_reason", "pe_reason", "net_pnl"]].to_string(index=False))

    save_json("phase3_discovery.json", payload)


if __name__ == "__main__":
    main()