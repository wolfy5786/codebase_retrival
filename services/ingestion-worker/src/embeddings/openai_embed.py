"""
OpenAI embedding API: batch inputs, return vectors only (no persisted text).
"""
from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "text-embedding-3-small"
_BATCH_SIZE = 64
_MAX_RETRIES = 5


def get_embedding_model() -> str:
    return os.environ.get("OPENAI_EMBEDDING_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL


def require_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for Phase 1 embeddings")
    return key


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed each string; returns vectors in the same order.
    Batches requests to reduce round-trips.
    """
    if not texts:
        return []
    require_api_key()
    model = get_embedding_model()

    from openai import OpenAI

    client = OpenAI()
    out: list[list[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        chunk = texts[i : i + _BATCH_SIZE]
        vectors = _embed_batch_with_retry(client, model, chunk)
        out.extend(vectors)
    return out


def _http_status(exc: Exception) -> int | None:
    st = getattr(exc, "status_code", None)
    if st is not None:
        return int(st)
    resp = getattr(exc, "response", None)
    if resp is not None:
        st2 = getattr(resp, "status_code", None)
        if st2 is not None:
            return int(st2)
    return None


def _embed_batch_with_retry(client: object, model: str, inputs: list[str]) -> list[list[float]]:
    last_err: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return _embed_batch(client, model, inputs)
        except Exception as e:
            last_err = e
            status = _http_status(e)
            if status == 401:
                raise
            if status is not None and status not in (429, 500, 502, 503):
                raise
            wait = min(2**attempt, 30)
            logger.warning(
                "OpenAI embedding error (attempt %s/%s): %s; retry in %ss",
                attempt + 1,
                _MAX_RETRIES,
                e,
                wait,
            )
            time.sleep(wait)
    if last_err:
        raise last_err
    raise RuntimeError("embedding failed without exception")


def _embed_batch(client: object, model: str, inputs: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(model=model, input=inputs)
    data = list(resp.data)
    data.sort(key=lambda d: d.index)
    return [list(d.embedding) for d in data]
