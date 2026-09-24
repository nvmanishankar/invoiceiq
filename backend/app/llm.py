"""Gemini adapter: extraction cached by file hash, fallback model, graceful failure.

The rest of the app only sees `extract()` returning an `Extraction` or None.
Switching provider means rewriting `_call_model` and nothing else.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import BACKEND_DIR, settings
from app.prompts import extraction_prompt
from app.schemas import Extraction

log = logging.getLogger(__name__)

CACHE_DIR = BACKEND_DIR / "fixtures" / "extractions"
TIMEOUT_MS = 90_000

_client = None


def _cache_path(file_hash: str) -> Path:
    return CACHE_DIR / f"{file_hash}.json"


def load_cache(file_hash: str) -> Extraction | None:
    path = _cache_path(file_hash)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Extraction.model_validate(data["extraction"])
    except Exception as e:  # a bad cache file must not break a run; treat as a miss
        log.warning("Ignoring unreadable cache file %s: %s", path.name, type(e).__name__)
        return None


def save_cache(file_hash: str, extraction: Extraction, model: str, source: str | None = None) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "file_hash": file_hash,
        "source": source,
        "model": model,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "extraction": extraction.model_dump(mode="json"),
    }
    _cache_path(file_hash).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _get_client():
    global _client
    if _client is None:
        from google import genai
        from google.genai import types

        _client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=TIMEOUT_MS),
        )
    return _client


def _safe_error(e: Exception) -> str:
    """Error summary for logs: type, HTTP code, short message, with the key scrubbed."""
    code = getattr(e, "code", None)
    msg = str(e)[:200]
    if settings.GEMINI_API_KEY:
        msg = msg.replace(settings.GEMINI_API_KEY, "***")
    return f"{type(e).__name__}" + (f" {code}" if code else "") + f": {msg}"


def _call_model(model: str, file_bytes: bytes, text: str) -> Extraction:
    from google.genai import types

    # No sampling parameters on purpose: Flash-Lite ignores temperature/top_p/top_k and
    # rejects frequency/presence penalties. The response schema keeps output consistent.
    resp = _get_client().models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=file_bytes, mime_type="application/pdf"),
            extraction_prompt(text),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Extraction,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    return Extraction.model_validate_json(resp.text)


def models() -> list[str]:
    return [m for m in (settings.GEMINI_MODEL, settings.GEMINI_MODEL_FALLBACK) if m]


def extract(file_bytes: bytes, file_hash: str, text: str = "", source: str | None = None, ctx=None) -> Extraction | None:
    """Cached extraction, else primary model, else fallback model, else None. Never raises."""
    cached = load_cache(file_hash)
    if cached is not None:
        return cached
    if not settings.GEMINI_API_KEY:
        log.warning("GEMINI_API_KEY is not set; extraction unavailable")
        return None
    for model in models():
        if ctx is not None:
            ctx.llm_calls += 1
        try:
            data = _call_model(model, file_bytes, text)
        except Exception as e:  # quota, server, network, bad JSON: try the next model
            log.warning("Extraction with %s failed: %s", model, _safe_error(e))
            continue
        try:
            save_cache(file_hash, data, model, source)
        except OSError as e:
            log.warning("Couldn't write extraction cache: %s", type(e).__name__)
        return data
    return None
