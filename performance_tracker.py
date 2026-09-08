import matplotlib.pyplot as plt

# Assume you maintain lists: performance.history (e.g. equity curve)
def plot_performance(equity_curve, show=False):
    plt.figure(figsize=(10, 6))
    plt.plot(equity_curve, marker="o", linestyle="-")
    plt.title("Simulated Equity Curve • Performance Tracker")
    plt.xlabel("Trade #")
    plt.ylabel("Equity")
    plt.grid(True)
    plt.tight_layout()

    if show:
        plt.show()       # Opens an interactive window
    else:
        plt.savefig("earnings_chart.png")
        print("📊 Chart saved as earnings_chart.png")
