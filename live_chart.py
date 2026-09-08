import matplotlib.pyplot as plt
import matplotlib

matplotlib.rcParams['font.family'] = 'Arial Unicode MS'  # Supports 📈 emoji

def show_live_chart():
    plt.ion()
    fig, ax = plt.subplots(figsize=(10, 6))
    line, = ax.plot([], [], color="dodgerblue", linewidth=2)
    ax.set_title("📈 Live Portfolio Equity")
    ax.set_xlabel("Trades")
    ax.set_ylabel("Total Equity ($)")
    ax.grid(True)

    def update(equity_curve):
        line.set_data(range(len(equity_curve)), equity_curve)
        ax.relim()
        ax.autoscale_view()
        plt.pause(0.01)

    return update
