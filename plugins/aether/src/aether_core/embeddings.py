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
    base_url: str = "https://api.openai.com/v1"
    dimensions: int = 0
    provider_name: str = "openai"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        payload: dict[str, Any] = {"model": self.model, "input": texts}
        if self.dimensions:
            payload["dimensions"] = self.dimensions
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/embeddings",
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
        model = embedding.get("model") or provider_config.get("model") or defaults["model"]
        base_url = embedding.get("baseUrl") or provider_config.get("baseUrl") or defaults["baseUrl"]
        dimensions = int(embedding.get("dimensions") or provider_config.get("dimensions") or 0)
        api_key_env = provider_config.get("apiKeyEnv", defaults["apiKeyEnv"])
        api_key = embedding.get("apiKey") or provider_config.get("apiKey") or os.environ.get(api_key_env, "")
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
