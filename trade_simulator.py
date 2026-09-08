# trade_simulator.py

def simulate_trade(df, signal, confidence):
    """
    Simulate a trade on the latest close price, print it, 
    and return the P&L so you can update your equity curve.
    """
    # 1️⃣ Extract the last closing price as a pure float
    price = float(df["Close"].iloc[-1])

    # 2️⃣ Choose how many shares to trade
    shares = 100

    # 3️⃣ Calculate P&L:
    #    BUY   means you pay cash  → P&L is negative
    #    SELL  means you receive cash → P&L is positive
    pnl = shares * (price if signal == "SELL" else -price)

    # 4️⃣ Log the trade with 2-decimal formatting
    print(
        f"📝 Trade logged: {signal} "
        f"{shares} @ ${price:.2f} | "
        f"Confidence: {confidence:.2f} | "
        f"P&L: ${pnl:.2f}"
    )

    # 5️⃣ Return P&L so main.py can do: equity += pnl
    return pnl
