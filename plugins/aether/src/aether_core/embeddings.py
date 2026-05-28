from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


class EmbeddingProvider(Protocol):
    provider_name: str
    model: str
    dimensions: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


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
    dimensions: int = 0
    provider_name: str = "openai"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        payload: dict[str, Any] = {"model": self.model, "input": texts}
        if self.dimensions:
            payload["dimensions"] = self.dimensions
        request = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI embedding request failed: {exc.code} {detail}") from exc
        vectors = [item["embedding"] for item in sorted(body.get("data", []), key=lambda item: item["index"])]
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
    if provider_name == "openai":
        provider_config = providers.get("openai", {})
        model = embedding.get("model") or provider_config.get("model") or "text-embedding-3-small"
        dimensions = int(embedding.get("dimensions") or provider_config.get("dimensions") or 0)
        api_key_env = provider_config.get("apiKeyEnv", "OPENAI_API_KEY")
        api_key = os.environ.get(api_key_env, "")
        if not api_key:
            raise RuntimeError(f"Embedding provider openai requires ${api_key_env}")
        return OpenAIEmbeddingProvider(api_key=api_key, model=model, dimensions=dimensions)

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
