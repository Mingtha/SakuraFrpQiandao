import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import send_bark


class BarkTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.result = Path(self.directory.name) / "result.json"

    def result_file(self, success):
        self.result.write_text(json.dumps({"success": success}), encoding="utf-8")
        return self.result

    def response(self, code=200):
        return io.BytesIO(json.dumps({"code": code}).encode())

    def test_missing_key_skips_network(self):
        with patch("send_bark.urlopen") as request:
            self.assertTrue(send_bark.send_bark())
            request.assert_not_called()

    def test_only_explicit_boolean_success_is_accepted(self):
        self.assertFalse(send_bark.checkin_succeeded(self.result))
        for value in (False, "true", 1, None):
            self.assertFalse(send_bark.checkin_succeeded(self.result_file(value)))
        self.assertTrue(send_bark.checkin_succeeded(self.result_file(True)))
        self.result.write_text("invalid JSON")
        self.assertFalse(send_bark.checkin_succeeded(self.result))

    def test_failed_or_skipped_step_overrides_result(self):
        self.result_file(True)
        for outcome in ("failure", "skipped", "cancelled"):
            with patch.dict(os.environ, {"CHECKIN_OUTCOME": outcome}):
                self.assertFalse(send_bark.checkin_succeeded(self.result))

    def test_custom_server_path_and_unicode_json_and_run_link(self):
        os.environ.update({
            "BARK_URL": "https://notify.example/bark/test-device/",
            "GITHUB_REPOSITORY": "example/checkin",
            "GITHUB_RUN_ID": "123",
            "CHECKIN_OUTCOME": "success",
        })
        with patch("send_bark.urlopen", return_value=self.response()) as request:
            self.assertTrue(send_bark.send_bark(self.result_file(True)))
        req = request.call_args.args[0]
        self.assertEqual(req.full_url, "https://notify.example/bark/test-device")
        self.assertEqual(req.get_method(), "POST")
        payload = json.loads(req.data)
        self.assertEqual(payload["title"], "SakuraFrp")
        self.assertEqual(payload["body"], "签到成功")
        self.assertEqual(payload["url"], "https://github.com/example/checkin/actions/runs/123")
        self.assertNotIn("device_key", payload)
        self.assertTrue(payload["icon"].endswith("/1f338.png"))

    def test_custom_icon(self):
        os.environ.update({"BARK_URL": "https://api.day.app/test-device",
                           "BARK_ICON": "https://example.com/my-icon.png"})
        with patch("send_bark.urlopen", return_value=self.response()) as request:
            self.assertTrue(send_bark.send_bark(self.result))
        self.assertEqual(json.loads(request.call_args.args[0].data)["icon"],
                         "https://example.com/my-icon.png")

    def test_missing_result_sends_failure(self):
        os.environ["BARK_URL"] = "https://api.day.app/test-device"
        with patch("send_bark.urlopen", return_value=self.response()) as request:
            self.assertTrue(send_bark.send_bark(self.result))
        payload = json.loads(request.call_args.args[0].data)
        self.assertEqual(payload["title"], "SakuraFrp")
        self.assertEqual(payload["body"], "签到失败 · 点击查看日志")
        self.assertNotIn("\n", payload["body"])

    def test_transient_errors_retry_then_succeed(self):
        os.environ["BARK_URL"] = "https://api.day.app/test-device"
        with patch("send_bark.urlopen", side_effect=[URLError("offline"), self.response(429), self.response()]) as request, patch("send_bark.time.sleep"):
            self.assertTrue(send_bark.send_bark(self.result))
            self.assertEqual(request.call_count, 3)

    def test_http_auth_failure_does_not_retry_or_expose_url(self):
        url = "https://api.day.app/test-device"
        os.environ["BARK_URL"] = url
        output = io.StringIO()
        with patch("send_bark.urlopen", side_effect=HTTPError(url, 401, url, {}, None)) as request, contextlib.redirect_stdout(output):
            self.assertFalse(send_bark.send_bark(self.result))
            self.assertEqual(request.call_count, 1)
        self.assertNotIn("test-device", output.getvalue())

    def test_exhausted_retries_return_failure(self):
        os.environ["BARK_URL"] = "https://api.day.app/test-device"
        with patch("send_bark.urlopen", side_effect=URLError("offline")) as request, patch("send_bark.time.sleep"):
            self.assertFalse(send_bark.send_bark(self.result))
            self.assertEqual(request.call_count, 3)

    def test_invalid_url_rejected_before_request(self):
        for url in ("file:///tmp/test", "https://api.day.app", "https://api.day.app/key/body?x=1", "https://[invalid/key"):
            with patch.dict(os.environ, {"BARK_URL": url}), patch("send_bark.urlopen") as request:
                self.assertFalse(send_bark.send_bark(self.result))
                request.assert_not_called()


class MainResultTests(unittest.TestCase):
    def test_main_records_and_returns_real_result(self):
        config_module = types.ModuleType("config")
        config_module.Config = unittest.mock.Mock()
        config_module.Config.from_env.return_value.sakurafrp_user = "test-user"
        automation_module = types.ModuleType("automation")
        automation_module.CheckInAutomation = unittest.mock.Mock()
        with patch.dict(sys.modules, {"config": config_module, "automation": automation_module}):
            spec = importlib.util.spec_from_file_location("checkin_main", Path(__file__).resolve().parents[1] / "main.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        for value in (True, False, None):
            automation_module.CheckInAutomation.return_value.run.return_value = value
            with patch.object(module.Path, "write_text") as write:
                self.assertEqual(module.main(), 0 if value is True else 1)
                self.assertIs(json.loads(write.call_args.args[0])["success"], value is True)
        automation_module.CheckInAutomation.return_value.run.side_effect = RuntimeError("browser failed")
        with patch.object(module.Path, "write_text") as write:
            self.assertEqual(module.main(), 1)
            self.assertFalse(json.loads(write.call_args.args[0])["success"])


if __name__ == "__main__":
    unittest.main()
