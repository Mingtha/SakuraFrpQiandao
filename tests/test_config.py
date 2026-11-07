import os
import unittest
from unittest.mock import patch
from config import AI_PROMPT, Config


class PromptConfigTests(unittest.TestCase):
    def environment(self):
        return dict(SAKURAFRP_USER="user", SAKURAFRP_PASS="password",
                    BASE_URL="https://example.com/v1", API_KEY="test", MODEL="test")

    def test_prompt_is_built_in(self):
        expected = "这是一个儿童画册，请按从左到右、从上到下的顺序识别每个格子里的物品名称，最后识别左下角的参考图。输出格式为JSON：{\"1\":\"名称\", \"2\":\"名称\", ..., \"10\":\"参考图名称\"}。名称要简洁，参考图名称必须是九宫格里已有的名称。若有类似物品（如气球与热气球），请统一名称。"
        with patch.dict(os.environ, self.environment(), clear=True):
            self.assertEqual(Config.from_env().ai_prompt, expected)
        self.assertEqual(AI_PROMPT, expected)

    def test_old_environment_prompt_is_ignored(self):
        for value in ("", "custom prompt", "first\\nsecond"):
            with patch.dict(os.environ, dict(self.environment(), AI_PROMPT=value), clear=True):
                self.assertEqual(Config.from_env().ai_prompt, AI_PROMPT)

    def test_other_fields_remain_single_line(self):
        env = dict(self.environment(), MODEL="model\nignored")
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(Config.from_env().model, "model")


if __name__ == "__main__":
    unittest.main()

