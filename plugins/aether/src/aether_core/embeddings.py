from __future__ import annotations

import hashlib
import json
import math
import os
import random
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Protocol


# HTTP status codes that are safe to retry on a remote embedding provider.
# Mirrors the list used by skills/image-generate so the embedding path is
# consistent with the generation path.
RETRYABLE_HTTP_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524})


class EmbeddingProvider(Protocol):
    provider_name: str
    model: str
    dimensions: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


def _is_retryable_error(exc: BaseException) -> bool:
    """Return True for transient network / provider errors that should be retried."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in RETRYABLE_HTTP_STATUSES
    if isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError, OSError)):
        return True
    return False


def embed_with_retry(
    fn: Callable[[list[str]], list[list[float]]],
    texts: list[str],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.4,
    max_delay: float = 4.0,
    sleep: Callable[[float], None] = time.sleep,
    is_retryable: Callable[[BaseException], bool] = _is_retryable_error,
) -> list[list[float]]:
    """Call ``fn(texts)`` with exponential backoff on transient failures.

    The first failure waits ``base_delay`` seconds, the second ``2 * base_delay``
    (capped at ``max_delay``), with a small random jitter to avoid synchronised
    retries. Non-retryable errors propagate immediately so a malformed prompt
    still fails fast.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    attempt = 1
    delay = base_delay
    while True:
        try:
            return fn(texts)
        except Exception as exc:  # noqa: BLE001 — we re-raise below
            retryable = is_retryable(exc)
            if attempt >= max_attempts or not retryable:
                raise
            if isinstance(exc, urllib.error.HTTPError):
                exc.close()
            sleep(delay + random.uniform(0, delay * 0.25))
            attempt += 1
            delay = min(delay * 2, max_delay)


def chunk_texts(texts: list[str], *, batch_size: int) -> list[list[str]]:
    """Split ``texts`` into chunks of at most ``batch_size`` items.

    An empty input returns an empty list so callers can short-circuit.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    if not texts:
        return []
    return [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]


@dataclass(frozen=True)
class DisabledEmbeddingProvider:
    provider_name: str = "disabled"
    model: str = ""
    dimensions: int = 0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("Embedding provider is disabled")


@dataclass(frozen=True)
class OpenAIEmbeddingProvider:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    dimensions: int = 0
    provider_name: str = "openai"
    timeout: float = 60.0

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        payload: dict[str, Any] = {"model": self.model, "input": texts}
        if self.dimensions:
            payload["dimensions"] = self.dimensions
        body = self._post(payload)
        vectors = [
            item["embedding"]
            for item in sorted(body.get("data", []), key=lambda item: item["index"])
        ]
        if len(vectors) != len(texts):
            raise RuntimeError("OpenAI embedding response count does not match input count")
        return vectors


@dataclass(frozen=True)
class LocalCommandEmbeddingProvider:
    command: str
    model: str
    dimensions: int
    provider_name: str = "local"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self.command:
            raise RuntimeError("Local embedding command is not configured")
        completed = subprocess.run(
            self.command,
            input=json.dumps({"model": self.model, "texts": texts}),
            text=True,
            capture_output=True,
            shell=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "Local embedding command failed")
        body = json.loads(completed.stdout)
        vectors = body.get("vectors", body if isinstance(body, list) else None)
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise RuntimeError("Local embedding command returned an invalid vector payload")
        return vectors


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def provider_from_config(config: dict[str, Any] | None) -> EmbeddingProvider:
    embedding = (config or {}).get("embedding", {})
    provider_name = embedding.get("provider", "disabled")
    if provider_name in ("", "disabled", None):
        return DisabledEmbeddingProvider()

    providers = embedding.get("providers", {})
    if provider_name in {"openai", "siliconflow"}:
        defaults = {
            "openai": {
                "apiKeyEnv": "OPENAI_API_KEY",
                "baseUrl": "https://api.openai.com/v1",
                "model": "text-embedding-3-small",
            },
            "siliconflow": {
                "apiKeyEnv": "SILICONFLOW_API_KEY",
                "baseUrl": "https://api.siliconflow.cn/v1",
                "model": "BAAI/bge-m3",
            },
        }[provider_name]
        provider_config = providers.get(provider_name, {})
        model = provider_config.get("model") or defaults["model"]
        base_url = provider_config.get("baseUrl") or defaults["baseUrl"]
        dimensions = int(provider_config.get("dimensions") or 0)
        api_key_env = provider_config.get("apiKeyEnv", defaults["apiKeyEnv"])
        api_key = provider_config.get("apiKey") or os.environ.get(api_key_env, "")
        if not api_key:
            raise RuntimeError(f"Embedding provider {provider_name} requires apiKey or ${api_key_env}")
        return OpenAIEmbeddingProvider(
            api_key=api_key,
            model=model,
            base_url=base_url,
            dimensions=dimensions,
            provider_name=provider_name,
        )

    if provider_name == "local":
        provider_config = providers.get("local", {})
        model = embedding.get("model") or provider_config.get("model") or "local"
        dimensions = int(embedding.get("dimensions") or provider_config.get("dimensions") or 0)
        return LocalCommandEmbeddingProvider(
            command=provider_config.get("command", ""),
            model=model,
            dimensions=dimensions,
        )

    raise RuntimeError(f"Unsupported embedding provider: {provider_name}")
