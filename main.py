import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from feature_engineering import build_features
from ml_model import predict_row
from news_reader import analyze_sentiment, fetch_news
from utils import log
from video_analyzer import analyze_transcription, transcribe_video

load_dotenv()

USE_REAL_MONEY = os.getenv("USE_REAL_MONEY", "false").lower() in ("1", "true", "yes")
TARGET_DAILY_MIN = float(os.getenv("TARGET_DAILY_GAIN_PCT_MIN", "5"))
TARGET_DAILY_MAX = float(os.getenv("TARGET_DAILY_GAIN_PCT_MAX", "10"))


def _model_path_for(ticker: str) -> str:
    p = os.getenv("MODEL_PATH")
    if p and os.path.isfile(p):
        return p
    return os.path.join("models", f"{ticker}_model.pkl")


def _blend_sentiment(headlines: list[float], transcript_sent: float) -> float:
    if headlines:
        h = sum(headlines) / len(headlines)
        if transcript_sent:
            return max(-1.0, min(1.0, 0.5 * h + 0.5 * transcript_sent))
        return h
    return transcript_sent


def run_bot(ticker: str, live_price: float | None = None) -> float:
    """
    Pull recent bars + headlines, score with the saved RF model, print intent.
    Returns a simple PnL placeholder (0.0) unless you wire execution fills.
    """
    end = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=800)).strftime("%Y-%m-%d")

    df = build_features(ticker, start, end)
    if df.empty:
        log.warning("[BOT] No features for %s", ticker)
        return 0.0

    news = fetch_news(ticker)
    headline_scores = [analyze_sentiment(a["headline"] + " " + a.get("summary", "")) for a in news]

    audio = os.getenv("PODCAST_AUDIO_PATH", "").strip()
    transcript = transcribe_video(audio) if audio else ""
    video_sent = analyze_transcription(transcript)

    blended = _blend_sentiment(headline_scores, video_sent)
    try:
        from analytics.completed_bar import completed_daily_signal_row

        row, _px = completed_daily_signal_row(df)
    except Exception:
        row = df.iloc[-1].copy()
    # Models train with sentiment=0; keep serve aligned. Live news is a gate, not a fake feature.
    row["sentiment"] = 0.0
    row["lag_1_sentiment"] = 0.0
    row["lag_2_sentiment"] = 0.0
    row["lag_3_sentiment"] = 0.0

    path = _model_path_for(ticker)
    if not os.path.isfile(path):
        log.warning("[BOT] No model at %s — train with: python FATE_AlgoBot.py train", path)
        return 0.0

    pred, p_up = predict_row(path, row)
    try:
        from intraday.live_infer import blend_intraday_p, live_intraday_p_up

        p_up, _ = blend_intraday_p(float(p_up), live_intraday_p_up(ticker))
        pred = 1 if p_up >= 0.5 else 0
    except Exception:
        pass
    try:
        from sentiment_pipeline import block_long_on_sentiment

        if block_long_on_sentiment(blended, symbol=ticker):
            p_up = min(p_up, 0.49)
    except Exception:
        if blended < float(os.getenv("SENTIMENT_BLOCK_THRESHOLD", "-0.35")):
            p_up = min(p_up, 0.49)

    if p_up >= float(os.getenv("BUY_THRESHOLD", "0.55")):
        signal = 1
    elif p_up <= float(os.getenv("SELL_THRESHOLD", "0.45")):
        signal = -1
    else:
        signal = 0

    if live_price is not None:
        log.info("[BOT] %s last=%s", ticker, live_price)

    if signal == 1:
        log.info("[BOT] BUY %s (p_up=%.3f) [paper=%s]", ticker, p_up, not USE_REAL_MONEY)
    elif signal == -1:
        log.info("[BOT] SELL/REDUCE %s (p_up=%.3f) [paper=%s]", ticker, p_up, not USE_REAL_MONEY)
    else:
        log.info("[BOT] HOLD %s (p_up=%.3f)", ticker, p_up)

    log.info(
        "[BOT] Target band from env: %.1f-%.1f%% daily (not guaranteed; markets risk loss)",
        TARGET_DAILY_MIN,
        TARGET_DAILY_MAX,
    )

    if USE_REAL_MONEY:
        log.warning("[BOT] USE_REAL_MONEY enabled — ensure broker integration is reviewed.")

    return 0.0


if __name__ == "__main__":
    run_bot("AAPL")
