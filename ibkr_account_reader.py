# ibkr_account_reader.py

from ib_insync import *

def get_account_snapshot():
    ib = IB()
    ib.connect("127.0.0.1", 7497, clientId=999)

    account_values = ib.accountValues()
    positions = ib.positions()
    pnl = ib.pnl()

    print("\n💰 Account Overview:")
    for tag in account_values:
        print(f"{tag.tag}: {tag.value}")

    print("\n📦 Positions:")
    for pos in positions:
        contract = pos.contract
        print(f"{contract.symbol}: {pos.position} shares @ ${pos.averageCost:.2f}")

    print("\n📊 Real-Time PnL:")
    for entry in pnl:
        print(f"{entry.account} → Unrealized PnL: ${entry.unrealizedPnL:.2f}, Realized: ${entry.realizedPnL:.2f}")

    ib.disconnect()
