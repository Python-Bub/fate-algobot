import os
import joblib
from utils import log


def _rank(model, names: list[str]):
    importances = model.feature_importances_
    return sorted(zip(names, importances), key=lambda x: x[1], reverse=True)


def analyze_models():
    model_dir = "models"
    if not os.path.isdir(model_dir):
        log.warning("[META] models/ directory missing")
        return
    for file in os.listdir(model_dir):
        if not file.endswith("_model.pkl") or file.count("_") != 1:
            continue
        full = os.path.join(model_dir, file)
        raw = joblib.load(full)
        if not isinstance(raw, dict) or "features" not in raw:
            continue
        if "model_short" not in raw and "model" not in raw:
            continue
        ticker = file.split("_")[0]
        names = list(raw["features"])
        if not names:
            continue

        try:
            if raw.get("model_short") is not None and raw.get("model_long") is not None:
                log.info("[META] %s — short horizon importances:", ticker)
                for feat, score in _rank(raw["model_short"], names)[:8]:
                    log.info("       %-24s %.4f", feat, score)
                log.info("[META] %s — long horizon importances:", ticker)
                for feat, score in _rank(raw["model_long"], names)[:8]:
                    log.info("       %-24s %.4f", feat, score)
            else:
                m = raw["model"]
                log.info("[META] %s Top Features:", ticker)
                for feat, score in _rank(m, names)[:12]:
                    log.info("       %-24s %.4f", feat, score)
        except Exception as e:
            log.warning("[META] Failed for %s: %s", ticker, e)
