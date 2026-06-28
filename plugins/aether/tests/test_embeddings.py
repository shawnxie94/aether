import os
import unittest

from aether_core.embeddings import OpenAIEmbeddingProvider, provider_from_config


class EmbeddingProviderTests(unittest.TestCase):
    def test_openai_provider_supports_custom_base_url_and_direct_api_key(self):
        provider = provider_from_config(
            {
                "embedding": {
                    "provider": "openai",
                    "providers": {
                        "openai": {
                            "baseUrl": "https://example.test/openai/v1/",
                            "apiKey": "test-key",
                            "model": "compatible-embedding",
                            "dimensions": 768,
                        }
                    },
                }
            }
        )

        self.assertIsInstance(provider, OpenAIEmbeddingProvider)
        self.assertEqual(provider.base_url, "https://example.test/openai/v1/")
        self.assertEqual(provider.model, "compatible-embedding")
        self.assertEqual(provider.dimensions, 768)

    def test_openai_provider_ignores_top_level_model_base_url_and_dimensions(self):
        provider = provider_from_config(
            {
                "embedding": {
                    "provider": "openai",
                    "model": "ignored-model",
                    "baseUrl": "https://ignored.test/v1",
                    "dimensions": 1024,
                    "providers": {
                        "openai": {
                            "baseUrl": "https://example.test/v1",
                            "apiKey": "provider-key",
                            "model": "provider-model",
                            "dimensions": 768,
                        }
                    },
                }
            }
        )

        self.assertEqual(provider.base_url, "https://example.test/v1")
        self.assertEqual(provider.model, "provider-model")
        self.assertEqual(provider.dimensions, 768)

    def test_openai_provider_still_supports_api_key_env(self):
        os.environ["AETHER_TEST_EMBEDDING_KEY"] = "test-key"
        try:
            provider = provider_from_config(
                {
                    "embedding": {
                        "provider": "openai",
                        "providers": {
                            "openai": {
                                "apiKeyEnv": "AETHER_TEST_EMBEDDING_KEY",
                                "model": "env-model",
                            }
                        },
                    }
                }
            )
        finally:
            os.environ.pop("AETHER_TEST_EMBEDDING_KEY", None)

        self.assertEqual(provider.model, "env-model")

    def test_siliconflow_provider_uses_openai_compatible_defaults_and_direct_api_key(self):
        provider = provider_from_config(
            {
                "embedding": {
                    "provider": "siliconflow",
                    "providers": {
                        "siliconflow": {
                            "apiKey": "test-key",
                        }
                    },
                }
            }
        )

        self.assertEqual(provider.provider_name, "siliconflow")
        self.assertEqual(provider.base_url, "https://api.siliconflow.cn/v1")
        self.assertEqual(provider.model, "BAAI/bge-m3")
        self.assertEqual(provider.dimensions, 0)


if __name__ == "__main__":
    unittest.main()


class EmbeddingRetryTests(unittest.TestCase):
    """Retry and chunking helpers for the embedding provider."""

    def test_retry_then_succeed(self):
        from aether_core.embeddings import embed_with_retry
        calls = {"n": 0}
        sleeps = []

        def fake_fn(texts):
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("flaky")
            return [[float(len(t))] for t in texts]

        def fake_sleep(d):
            sleeps.append(d)

        result = embed_with_retry(
            fake_fn, ["ab", "c"], max_attempts=3, base_delay=0.1, sleep=fake_sleep
        )
        self.assertEqual(calls["n"], 3)
        self.assertEqual(result, [[2.0], [1.0]])
        self.assertEqual(len(sleeps), 2)
        # Second sleep should be at least the doubled first delay.
        self.assertGreater(sleeps[1], sleeps[0])

    def test_retry_propagates_non_retryable_immediately(self):
        from aether_core.embeddings import embed_with_retry
        calls = {"n": 0}

        def fake_fn(texts):
            calls["n"] += 1
            raise ValueError("invalid input")

        with self.assertRaises(ValueError):
            embed_with_retry(fake_fn, ["x"], max_attempts=5, base_delay=0.01, sleep=lambda d: None)
        self.assertEqual(calls["n"], 1)

    def test_retry_exhausts_then_raises(self):
        from aether_core.embeddings import embed_with_retry
        calls = {"n": 0}

        def fake_fn(texts):
            calls["n"] += 1
            raise ConnectionError("never recovers")

        with self.assertRaises(ConnectionError):
            embed_with_retry(fake_fn, ["x"], max_attempts=3, base_delay=0.01, sleep=lambda d: None)
        self.assertEqual(calls["n"], 3)

    def test_retryable_http_status_5xx_is_retried(self):
        import io
        import urllib.error
        from aether_core.embeddings import embed_with_retry
        calls = {"n": 0}

        def fake_fn(texts):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.HTTPError(
                    "https://api.example.com/embeddings",
                    503,
                    "Service Unavailable",
                    {},
                    io.BytesIO(b"try again"),
                )
            return [[0.0]]

        result = embed_with_retry(
            fake_fn, ["a"], max_attempts=2, base_delay=0.01, sleep=lambda d: None
        )
        self.assertEqual(result, [[0.0]])
        self.assertEqual(calls["n"], 2)

    def test_non_retryable_http_status_not_retried(self):
        import io
        import urllib.error
        from aether_core.embeddings import embed_with_retry
        calls = {"n": 0}

        def fake_fn(texts):
            calls["n"] += 1
            raise urllib.error.HTTPError(
                "https://api.example.com/embeddings",
                400,
                "Bad Request",
                {},
                io.BytesIO(b"bad"),
            )

        with self.assertRaises(urllib.error.HTTPError) as raised:
            embed_with_retry(fake_fn, ["a"], max_attempts=5, base_delay=0.01, sleep=lambda d: None)
        raised.exception.close()
        self.assertEqual(calls["n"], 1)

    def test_chunk_texts_splits_and_handles_empty(self):
        from aether_core.embeddings import chunk_texts
        self.assertEqual(chunk_texts([], batch_size=2), [])
        self.assertEqual(chunk_texts(["a"], batch_size=2), [["a"]])
        self.assertEqual(
            chunk_texts(["a", "b", "c", "d", "e"], batch_size=2),
            [["a", "b"], ["c", "d"], ["e"]],
        )
        with self.assertRaises(ValueError):
            chunk_texts(["a"], batch_size=0)
