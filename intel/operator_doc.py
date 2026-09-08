"""Google Doc ↔ Operator AI transport + local markdown fallback.

Doc ID default: 1fEuErs8mTMzSoJm4WMesxmhsfqvnlhzzFINycbRCIeU

Auth (first match wins):
  1. GOOGLE_SERVICE_ACCOUNT_JSON / GOOGLE_APPLICATION_CREDENTIALS (service account)
  2. data/secrets/google_docs_token.json + OAuth client (GOOGLE_OAUTH_CLIENT_JSON)
  3. Local fallback: data/intel/operator_chat.md (same protocol — work never blocked)

Protocol markers in the doc / markdown:
  USER: …          — human message
  AI: …            — operator reply (persona + optional code actions)
  [[status]] [[train]] [[explain last loss]] [[evolve]] [[fix]] [[math]] [[mood]] [[help]]
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOC_ID = "1fEuErs8mTMzSoJm4WMesxmhsfqvnlhzzFINycbRCIeU"
LOCAL_CHAT = ROOT / "data" / "intel" / "operator_chat.md"
STATE_PATH = ROOT / "data" / "intel" / "operator_doc_state.json"
SCOPES = ("https://www.googleapis.com/auth/documents",)

USER_RE = re.compile(r"(?m)^(USER|Human|You)\s*:\s*(.+)$", re.I)
AI_RE = re.compile(r"(?m)^(AI|Operator|Bot)\s*:\s*", re.I)


def doc_id() -> str:
    return (os.getenv("OPERATOR_DOC_ID") or os.getenv("GOOGLE_DOC_ID") or DEFAULT_DOC_ID).strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"last_user_hash": "", "backend": "unknown"}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"last_user_hash": "", "backend": "unknown"}


def _save_state(st: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")


def ensure_local_chat() -> Path:
    LOCAL_CHAT.parent.mkdir(parents=True, exist_ok=True)
    if not LOCAL_CHAT.is_file():
        LOCAL_CHAT.write_text(
            "# FATE Operator Chat (local fallback)\n\n"
            "Same protocol as the Google Doc. Write below as `USER: …`\n"
            "Commands: [[status]] [[train]] [[explain last loss]] [[evolve]] [[fix]] [[math]] [[mood]] [[help]]\n\n"
            "USER: hey — paper is trash, pivot to pure math and talk to me\n",
            encoding="utf-8",
        )
    return LOCAL_CHAT


def _sa_path() -> Path | None:
    for key in ("GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_APPLICATION_CREDENTIALS", "OPERATOR_DOC_SA_JSON"):
        raw = (os.getenv(key) or "").strip()
        if not raw:
            continue
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT / p
        if p.is_file():
            return p
    for cand in (
        ROOT / "data" / "secrets" / "google_service_account.json",
        ROOT / "credentials" / "google_service_account.json",
    ):
        if cand.is_file():
            return cand
    return None


def google_docs_available() -> tuple[bool, str]:
    try:
        import googleapiclient  # noqa: F401
        from google.oauth2 import service_account  # noqa: F401
    except Exception:
        return False, "pip_missing:google-api-python-client google-auth"
    if _sa_path() is None:
        return False, "no_service_account_json"
    return True, "service_account"


def _docs_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    sa = _sa_path()
    if sa is None:
        raise RuntimeError("no_service_account")
    creds = service_account.Credentials.from_service_account_file(str(sa), scopes=list(SCOPES))
    return build("docs", "v1", credentials=creds, cache_discovery=False)


def read_google_doc(document_id: str | None = None) -> str:
    svc = _docs_service()
    doc = svc.documents().get(documentId=document_id or doc_id()).execute()
    chunks: list[str] = []
    for el in doc.get("body", {}).get("content", []):
        para = el.get("paragraph") or {}
        for pe in para.get("elements") or []:
            tr = pe.get("textRun") or {}
            t = tr.get("content")
            if t:
                chunks.append(t)
    return "".join(chunks)


def append_google_doc(text: str, document_id: str | None = None) -> dict[str, Any]:
    svc = _docs_service()
    did = document_id or doc_id()
    # End index: fetch once
    doc = svc.documents().get(documentId=did).execute()
    end_index = 1
    for el in doc.get("body", {}).get("content", []):
        if "endIndex" in el:
            end_index = max(end_index, int(el["endIndex"]))
    # Insert before final newline
    insert_at = max(1, end_index - 1)
    body = text if text.endswith("\n") else text + "\n"
    req = [{"insertText": {"location": {"index": insert_at}, "text": "\n" + body}}]
    return svc.documents().batchUpdate(documentId=did, body={"requests": req}).execute()


def read_local() -> str:
    return ensure_local_chat().read_text(encoding="utf-8")


def append_local(text: str) -> None:
    p = ensure_local_chat()
    with p.open("a", encoding="utf-8") as f:
        body = text if text.endswith("\n") else text + "\n"
        f.write("\n" + body)


def read_doc() -> tuple[str, str]:
    """Returns (text, backend) where backend is 'google' or 'local'."""
    ok, reason = google_docs_available()
    if ok:
        try:
            return read_google_doc(), "google"
        except Exception as e:
            ensure_local_chat()
            st = _load_state()
            st["last_google_err"] = str(e)[:300]
            st["backend"] = "local"
            _save_state(st)
            return read_local(), "local"
    ensure_local_chat()
    st = _load_state()
    st["backend"] = "local"
    st["auth_reason"] = reason
    _save_state(st)
    return read_local(), "local"


def append_doc(text: str, *, backend: str | None = None) -> str:
    """Append reply; returns backend used."""
    if backend is None:
        ok, _ = google_docs_available()
        backend = "google" if ok else "local"
    if backend == "google":
        try:
            append_google_doc(text)
            return "google"
        except Exception as e:
            append_local(text + f"\n\n_(google append failed: {e}; mirrored local)_\n")
            return "local"
    append_local(text)
    return "local"


def extract_latest_user_message(text: str) -> str | None:
    """Latest USER: line that is not already followed by a newer AI reply after it."""
    matches = list(USER_RE.finditer(text or ""))
    if not matches:
        return None
    last = matches[-1]
    after = text[last.end() :]
    # If an AI reply already exists after this USER line, treat as handled
    if AI_RE.search(after):
        # unless there's another USER after that AI — handled by taking last USER
        # If last USER already has AI after it → skip
        return None
    return last.group(2).strip()


def auth_setup_instructions() -> str:
    return (
        "## Google Docs auth setup\n"
        "1. Create a GCP service account with Docs API enabled.\n"
        "2. Download JSON key → `data/secrets/google_service_account.json`\n"
        "   (or set GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/key.json).\n"
        "3. Share the Doc with the service account email (Editor).\n"
        "4. pip install google-api-python-client google-auth\n"
        "5. OPERATOR_DOC_ID=1fEuErs8mTMzSoJm4WMesxmhsfqvnlhzzFINycbRCIeU\n"
        "6. ./run_all.sh doc-chat\n\n"
        "Until auth works, chat in `data/intel/operator_chat.md` with the same USER:/AI: protocol.\n"
    )
