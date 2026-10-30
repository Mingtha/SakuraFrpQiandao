import os
import unittest
from unittest.mock import patch
from config import Config


class PromptConfigTests(unittest.TestCase):
    def environment(self):
        return dict(SAKURAFRP_USER="user", SAKURAFRP_PASS="password",
                    BASE_URL="https://example.com/v1", API_KEY="test", MODEL="test")

    def test_prompt_is_required(self):
        for value in (None, "", " \n\t "):
            env = self.environment()
            if value is not None:
                env["AI_PROMPT"] = value
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaisesRegex(ValueError, "AI_PROMPT"):
                    Config.from_env()

    def test_multiline_prompt_preserved(self):
        env = self.environment()
        env["AI_PROMPT"] = "  第一行\n第二行\n\n第三行  "
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(Config.from_env().ai_prompt, "第一行\n第二行\n\n第三行")

    def test_other_fields_remain_single_line(self):
        env = self.environment()
        env.update(AI_PROMPT="custom", MODEL="model\nignored")
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(Config.from_env().model, "model")


if __name__ == "__main__":
    unittest.main()
