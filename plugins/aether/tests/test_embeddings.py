import os
import unittest

from aether_core.embeddings import OpenAIEmbeddingProvider, provider_from_config


class EmbeddingProviderTests(unittest.TestCase):
    def test_openai_provider_supports_custom_base_url(self):
        os.environ["AETHER_TEST_EMBEDDING_KEY"] = "test-key"
        try:
            provider = provider_from_config(
                {
                    "embedding": {
                        "provider": "openai",
                        "providers": {
                            "openai": {
                                "baseUrl": "https://example.test/openai/v1/",
                                "apiKeyEnv": "AETHER_TEST_EMBEDDING_KEY",
                                "model": "compatible-embedding",
                                "dimensions": 768,
                            }
                        },
                    }
                }
            )
        finally:
            os.environ.pop("AETHER_TEST_EMBEDDING_KEY", None)

        self.assertIsInstance(provider, OpenAIEmbeddingProvider)
        self.assertEqual(provider.base_url, "https://example.test/openai/v1/")
        self.assertEqual(provider.model, "compatible-embedding")
        self.assertEqual(provider.dimensions, 768)

    def test_openai_provider_top_level_model_and_base_url_override_provider_defaults(self):
        os.environ["AETHER_TEST_EMBEDDING_KEY"] = "test-key"
        try:
            provider = provider_from_config(
                {
                    "embedding": {
                        "provider": "openai",
                        "model": "override-model",
                        "baseUrl": "https://override.test/v1",
                        "dimensions": 1024,
                        "providers": {
                            "openai": {
                                "baseUrl": "https://example.test/v1",
                                "apiKeyEnv": "AETHER_TEST_EMBEDDING_KEY",
                                "model": "provider-model",
                                "dimensions": 768,
                            }
                        },
                    }
                }
            )
        finally:
            os.environ.pop("AETHER_TEST_EMBEDDING_KEY", None)

        self.assertEqual(provider.base_url, "https://override.test/v1")
        self.assertEqual(provider.model, "override-model")
        self.assertEqual(provider.dimensions, 1024)


if __name__ == "__main__":
    unittest.main()
