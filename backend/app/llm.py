"""Gemini adapter: extraction and description similarity, cached, with fallback and graceful failure.

The rest of the app only sees `extract()` returning an `Extraction` or None, and
`similarity()` returning scores or None. Switching provider means rewriting
`_call_model` and `_call_similarity_model` and nothing else.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import BACKEND_DIR, MAX_LLM_CALLS_PER_RUN, settings
from app.prompts import SIMILARITY_PROMPT_VERSION, extraction_prompt, similarity_prompt
from app.schemas import Extraction, SimilarityScores

log = logging.getLogger(__name__)

CACHE_DIR = BACKEND_DIR / "fixtures" / "extractions"
SIM_CACHE_DIR = BACKEND_DIR / "fixtures" / "similarity"
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


# --- description similarity (stage 5) ------------------------------------------

def similarity_key(pairs: list[tuple[str, str]]) -> str:
    """Cache key: hash of the prompt version and the pairs, so equal inputs share a score file."""
    blob = json.dumps({"v": SIMILARITY_PROMPT_VERSION, "pairs": [list(p) for p in pairs]}, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_similarity_cache(key: str, n: int) -> list[float] | None:
    path = SIM_CACHE_DIR / f"{key}.json"
    if not path.is_file():
        return None
    try:
        scores = [float(s) for s in json.loads(path.read_text(encoding="utf-8"))["scores"]]
        return scores if len(scores) == n else None
    except Exception as e:  # a bad cache file is a miss
        log.warning("Ignoring unreadable similarity cache %s: %s", path.name, type(e).__name__)
        return None


def save_similarity_cache(key: str, pairs: list[tuple[str, str]], scores: list[float], model: str) -> None:
    SIM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "key": key,
        "prompt_version": SIMILARITY_PROMPT_VERSION,
        "model": model,
        "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pairs": [{"invoice": a, "po": b, "score": s} for (a, b), s in zip(pairs, scores)],
        "scores": scores,
    }
    (SIM_CACHE_DIR / f"{key}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _call_similarity_model(model: str, pairs: list[tuple[str, str]]) -> list[float]:
    from google.genai import types

    resp = _get_client().models.generate_content(
        model=model,
        contents=[similarity_prompt(pairs)],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SimilarityScores,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    got = {s.pair: s.score for s in SimilarityScores.model_validate_json(resp.text).scores}
    if set(got) != set(range(len(pairs))):
        raise ValueError(f"expected {len(pairs)} scores, got pairs {sorted(got)}")
    return [min(1.0, max(0.0, float(got[i]))) for i in range(len(pairs))]


def similarity(pairs: list[tuple[str, str]], ctx=None) -> list[float] | None:
    """One batched call scoring every (invoice description, PO description) pair 0-1.

    Cached by a hash of the inputs. Returns None when no score is available (no key,
    call budget used up, or every model failed); the caller falls back to rapidfuzz.
    """
    if not pairs:
        return []
    key = similarity_key(pairs)
    cached = load_similarity_cache(key, len(pairs))
    if cached is not None:
        return cached
    if not settings.GEMINI_API_KEY:
        return None
    for model in models():
        if ctx is not None:
            if ctx.llm_calls >= MAX_LLM_CALLS_PER_RUN:
                log.info("LLM call budget used up; similarity falls back to text matching")
                return None
            ctx.llm_calls += 1
        try:
            scores = _call_similarity_model(model, pairs)
        except Exception as e:
            log.warning("Similarity with %s failed: %s", model, _safe_error(e))
            continue
        try:
            save_similarity_cache(key, pairs, scores, model)
        except OSError as e:
            log.warning("Couldn't write similarity cache: %s", type(e).__name__)
        return scores
    return None
