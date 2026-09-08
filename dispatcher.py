from multiprocessing import Process
from config import TICKERS, IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
from live_listener import run_live
from ib_insync import IB
from session_tracker import set_initial_balance, get_initial_balance, get_all_trades

def show_full_report(ib):
    # fetch NetLiquidation value
    account_vals = ib.accountValues()
    net_liq = next(
        (float(v.value) for v in account_vals if v.tag == "NetLiquidation"),
        None
    )
    if net_liq is None:
        print("⚠️ Could not fetch NetLiquidation.")
        return

    # record initial if first time
    set_initial_balance(net_liq)
    initial = get_initial_balance()
    final = round(net_liq, 2)
    gain = round(final - initial, 2)

    print("\n💰 IBKR Account Summary:")
    print(f"  Initial NetLiquidation: ${initial:.2f}")
    print(f"  Final   NetLiquidation: ${final:.2f}")
    print(f"  Gain/Loss:             ${gain:+.2f}")

    print("\n📝 Trade History (UTC):")
    trades = get_all_trades()
    for t in trades:
        ts = t["timestamp"]
        print(f"  → {ts} | {t['ticker']} | PnL=${t['pnl']:.2f}")

def launch_all():
    jobs = []
    for ticker in TICKERS:
        p = Process(target=run_live, args=(ticker,))
        p.start()
        jobs.append(p)

    print("✅ All tickers are running.")
    print("🔁 Type '0' + Enter to stop and show full report.")

    while True:
        if input(">> ").strip() == "0":
            print("🛑 Terminating all live listeners...")
            for job in jobs:
                job.terminate()

            ib = IB()
            ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
            show_full_report(ib)
            ib.disconnect()
            break

if __name__ == "__main__":
    launch_all()
