# FATE_AlgoBot Operations Runbook

## 1) Data Sync and Quality

- Full sync (initial backfill):
  - `./venv/bin/python FATE_AlgoBot.py data-sync full`
- Incremental sync:
  - `./venv/bin/python FATE_AlgoBot.py data-sync incremental`
- Audit cache health:
  - `./venv/bin/python FATE_AlgoBot.py data-audit 500`

Artifacts:
- `data/universe/data_sync_checkpoint.json`
- `data/universe/data_sync_report.json`
- `data/universe/quarantine_symbols.json`
- `data/replay/*`

## 2) Training

- Resume full universe:
  - `TRAIN_FORCE_YAHOO=true FORCE_YAHOO_PRICES=true USE_ENSEMBLE=true ./venv/bin/python FATE_AlgoBot.py train-universe`
- Crypto models:
  - `./venv/bin/python FATE_AlgoBot.py train-crypto`

Safety controls:
- `RESET_TRAINING=true` to wipe done list.
- `RESET_FAILED=true` to retry only failed.
- `USE_META_STACK=true` to train meta calibrator.

## 3) Simulation and Live Runtime

- Paper simulation:
  - `./venv/bin/python FATE_AlgoBot.py paper-sim`
- Concurrent live scoring (signal-only unless `USE_REAL_MONEY=true`):
  - `LIVE_CONCURRENT=true ./venv/bin/python live_market.py --once --max-symbols 200`
- Fortress pass:
  - `./venv/bin/python fortress_live.py --max-symbols 100`

## 4) Policy Agent (Guarded Self-Modify)

- Inspect runtime overrides/state:
  - `./venv/bin/python FATE_AlgoBot.py policy-status`
- Lock policy adaptation:
  - `export POLICY_HUMAN_LOCK=true`
- Disable adaptation completely:
  - `export POLICY_AGENT_ENABLED=false`
- Require offline shadow validation (recommended):
  - `export POLICY_REQUIRE_SHADOW=true`
- Rollback from snapshot:
  - `./venv/bin/python FATE_AlgoBot.py policy-rollback <snapshot_path>`

Audit files:
- `data/policy/audit_trail.jsonl`
- `data/policy/runtime_policy_overrides.json`
- `data/policy/policy_agent_state.json`

## 5) Drift and Benchmarks

- Drift report:
  - `./venv/bin/python FATE_AlgoBot.py drift-report AAPL`
- Pipeline benchmark:
  - `./venv/bin/python tests/benchmarks/benchmark_pipeline.py`
- AI factor spot checks:
  - `./venv/bin/python FATE_AlgoBot.py ai-eval-symbol AAPL`
  - `./venv/bin/python FATE_AlgoBot.py ai-eval-text "Analyst upgraded AAPL and raised target"`
- Platform adapter exports:
  - `./venv/bin/python FATE_AlgoBot.py adapter-export-signals 50`
  - `./venv/bin/python FATE_AlgoBot.py adapter-export-ninjatrader 50`
- Hummingbot bridge (optional):
  - `ENABLE_HUMMINGBOT_BRIDGE=true ./venv/bin/python FATE_AlgoBot.py hummingbot-bridge status`

LLM settings:
- `USE_LLM_SIGNAL=true|false`
- `LLM_API_KEY=<key>`
- `LLM_BASE_URL=https://api.openai.com/v1` (or OpenAI-compatible endpoint)
- `LLM_MODEL=gpt-4o-mini` (or compatible model name)

## 6) SLO Targets (Initial)

- Feature build average latency for liquid symbols: `< 1200ms`
- Inference latency average: `< 80ms`
- Live loop pass over 200 symbols in concurrent mode: `< 30s` (network-dependent)
- Data-sync failure ratio per run: `< 5%` (excluding delisted/no-data symbols)

## 7) Incident Handling

- **Mass Yahoo failures / DNS issues**
  - pause training; rerun `data-sync incremental` later.
- **Policy agent unexpected behavior**
  - set `POLICY_HUMAN_LOCK=true`; inspect `audit_trail.jsonl`.
- **Model drift high**
  - run `drift-report`; retrain affected symbols first.
- **Order route degraded**
  - switch `USE_REAL_MONEY=false`; run signal-only until broker/data API stabilizes.

## 8) Compliance-first execution checklist

- Set `USE_REAL_MONEY=true` only after broker account confirms permissions for:
  - margin + shorting (if shorts enabled),
  - crypto access (if trading crypto),
  - required market data entitlements.
- Keep `POLICY_HUMAN_LOCK=true` during initial live rollout.
- Verify `MAX_SINGLE_POSITION_FRAC`, `MAX_PORTFOLIO_HEAT`, `PDT_MIN_EQUITY`.
- Review `data/policy/audit_trail.jsonl` and `data/journal/trades.csv` daily.

