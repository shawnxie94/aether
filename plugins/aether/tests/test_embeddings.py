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
