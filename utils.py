# utils.py

import logging
import warnings

# 1) Suppress specific IBKR/ib_insync warnings at the source
warnings.filterwarnings(
    "ignore",
    message="No market data during competing live session"
)
warnings.filterwarnings(
    "ignore",
    message="Positions info is not available yet."
)

# 2) Route ib_insync’s internal logs to ERROR only
ib_logger = logging.getLogger("ib_insync")
ib_logger.setLevel(logging.ERROR)

# 3) Optional: Custom filter to drop recurring nuisance messages
class IBWarningFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        # suppress “market data farm broken/OK” chatter
        if "Market data farm connection" in msg:
            return False
        return True

ib_logger.addFilter(IBWarningFilter())

# 4) Configure the root logger for your bot
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
# Clear any existing handlers and attach ours
root_logger.handlers.clear()
root_logger.addHandler(stream_handler)

# 5) Expose a logger for your modules
log = logging.getLogger("FATE_AlgoBot")
