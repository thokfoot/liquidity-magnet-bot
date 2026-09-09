from config import LOT_SIZE, STRIKE_STEP

# ---- Strategy defaults (Phase 1 base case) ----
ENTRY_TIME = "09:25:00"
EXIT_TIME = "15:15:00"
SL_PCT = 0.25     # 25% stop loss above entry premium
TP_PCT = 0.40     # 40% profit target below entry premium
ATM_HALF_WIDTH = 6
IN_SAMPLE_FROM = "2026-08-01"
IN_SAMPLE_TO = "2026-08-22"
OUT_SAMPLE_FROM = "2026-08-25"
OUT_SAMPLE_TO = "2026-09-08"

# ---- Friction model (per leg) ----
BROKERAGE_PER_EXECUTION = 20.0   # buy & sell each ₹20
EXCHANGE_RATE = 0.0005           # ~0.05% of premium turnover
SEBI_PER_RS = 1e-7               # negligible
SLIP_PCT = 0.005                 # slippage as % of premium (min 1.0)
STT_SELL_RATE = 0.0005           # 0.05% on sell-side premium (options)
GST_RATE = 0.18


def friction_calc(entry_px, exit_px, qty, sell_side):
    """Return total friction ₹ for one leg round-trip."""
    brok = BROKERAGE_PER_EXECUTION * 2
    turnover = (entry_px + exit_px) * qty
    exch = EXCHANGE_RATE * turnover
    sebi = SEBI_PER_RS * turnover
    stt = STT_SELL_RATE * entry_px * qty if sell_side else 0.0
    gst = GST_RATE * (brok + exch + sebi)
    return brok + exch + sebi + stt + gst


def get_lot(index):
    return LOT_SIZE.get(index, 0)


def get_step(index):
    return STRIKE_STEP.get(index, 50)


def ensure_meta():
    if LOT_SIZE:
        return
    from symbols import load_masters, derive_lot_and_step
    derive_lot_and_step(load_masters())
    print("[meta] lot:", LOT_SIZE, "step:", STRIKE_STEP)