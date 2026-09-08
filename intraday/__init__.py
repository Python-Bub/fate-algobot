"""Intraday (minute / hourly) data and training pipeline.

Daily-and-up training stays in `model_trainer.py`. The HFT module (`hft/`)
handles sub-second microstructure. This package fills the **minutely** and
**hourly** horizons in between, using Alpaca's free IEX minute bars (paper
account) so every ticker can have a dedicated head per holding window.
"""
