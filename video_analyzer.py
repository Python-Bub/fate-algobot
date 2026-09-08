import os
import logging

log = logging.getLogger("FATE_AlgoBot.video")


def transcribe_video(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        import whisper  # type: ignore

        model = whisper.load_model(os.getenv("WHISPER_MODEL", "tiny"))
        result = model.transcribe(path)
        return (result.get("text") or "").strip()
    except ImportError:
        log.info("openai-whisper not installed; skipping audio transcription")
    except Exception as e:
        log.warning("Transcription failed: %s", e)
    return ""


def analyze_transcription(text: str) -> float:
    if not text:
        return 0.0
    from news_reader import analyze_sentiment

    return analyze_sentiment(text)
