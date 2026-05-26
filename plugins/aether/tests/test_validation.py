import unittest

from aether_core.validation import ValidationError, validate_generation_run, validate_prompt_record, validate_style


class ValidationTests(unittest.TestCase):
    def test_style_requires_name(self):
        with self.assertRaises(ValidationError):
            validate_style({"style_profile": {}})

    def test_prompt_requires_refined_prompt(self):
        with self.assertRaises(ValidationError):
            validate_prompt_record({"source_prompt": "x"})

    def test_prompt_generation_params_must_be_object(self):
        with self.assertRaises(ValidationError):
            validate_prompt_record(
                {
                    "source_prompt": "x",
                    "refined_prompt": "y",
                    "generation_params": "16:9",
                }
            )

    def test_generation_requires_skill(self):
        with self.assertRaises(ValidationError):
            validate_generation_run({"refined_prompt": "x"})

    def test_generation_visual_review_must_be_object(self):
        with self.assertRaises(ValidationError):
            validate_generation_run(
                {
                    "refined_prompt": "x",
                    "generation_skill": "imagegen",
                    "visual_review": "pass",
                }
            )


if __name__ == "__main__":
    unittest.main()
