import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from config import Config
from automation import CheckInAutomation, PlaywrightTimeoutError
import send_email


class ConfigValidationTests(unittest.TestCase):
    def test_invalid_retry_limits_fail_at_startup(self):
        for value in ("0", "-1", "abc"):
            with self.subTest(value=value), patch.dict(os.environ, {"MAX_RETRIES": value}):
                with self.assertRaisesRegex(ValueError, "MAX_RETRIES"):
                    Config.from_env()

    def test_boolean_typos_fail_instead_of_silently_disabling(self):
        env = dict(SAKURAFRP_USER="user", SAKURAFRP_PASS="pass",
                   API_KEY="key", BASE_URL="https://example.test", MODEL="model",
                   AI_PROMPT="prompt", IMAGE_AS_BASE64="treu")
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, "IMAGE_AS_BASE64"):
                Config.from_env()

    def test_secrets_are_excluded_from_repr(self):
        cfg = Config("user", "test-password", "https://example.test",
                     "test-api-key", "model", "prompt")
        self.assertNotIn("test-password", repr(cfg))
        self.assertNotIn("test-api-key", repr(cfg))


class DashboardReadinessTests(unittest.TestCase):
    def test_browser_is_closed_after_failure_even_in_headed_mode(self):
        from playwright.sync_api import Error
        runner = CheckInAutomation.__new__(CheckInAutomation)
        runner._resolve_chrome_path = Mock(return_value=None)
        runner._login = Mock(return_value=False)
        with patch("automation.sync_playwright") as runtime, patch.dict(
                os.environ, {"CI": "false", "HEADLESS": "false"}):
            browser = runtime.return_value.__enter__.return_value.chromium.launch.return_value
            self.assertFalse(runner.run())
            browser.close.assert_called_once()
            # A cleanup failure must not replace the original False result.
            browser.close.side_effect = Error("closed already")
            self.assertFalse(runner.run())

    def test_hidden_first_candidate_does_not_hide_ready_dashboard(self):
        page = Mock()
        page.locator.return_value.is_visible.return_value = False
        page.get_by_role.return_value.is_visible.return_value = True
        runner = CheckInAutomation.__new__(CheckInAutomation)
        runner._wait_for_dashboard(page)
        page.wait_for_timeout.assert_not_called()

    def test_no_candidate_has_bounded_wait(self):
        page = Mock()
        page.locator.return_value.is_visible.return_value = False
        page.get_by_role.return_value.is_visible.return_value = False
        page.get_by_text.return_value.first.is_visible.return_value = False
        runner = CheckInAutomation.__new__(CheckInAutomation)
        with patch("automation.time.monotonic", side_effect=[0, 61]):
            with self.assertRaises(PlaywrightTimeoutError):
                runner._wait_for_dashboard(page)


class EmailResultTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, dict(
            EMAIL_USERNAME="sender@example.test", EMAIL_PASSWORD="secret",
            RECEIVER_EMAIL="", SMTP_PORT="587"), clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.log = Path(self.directory.name) / "checkin.log"
        self.log.write_text("历史记录：签到流程完成", encoding="utf-8")

    def test_old_success_log_cannot_override_failed_result(self):
        with patch("send_email.checkin_succeeded", return_value=False), patch("send_email.smtplib.SMTP") as smtp:
            self.assertTrue(send_email.send_log_email(self.log))
        smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
        connection = smtp.return_value
        message = connection.send_message.call_args.args[0]
        self.assertIn("签到失败", message["Subject"])
        self.assertEqual(message["To"], "sender@example.test")
        connection.starttls.assert_called_once()

    def test_result_success_does_not_need_log_keyword(self):
        self.log.unlink()
        with patch("send_email.checkin_succeeded", return_value=True), patch("send_email.smtplib.SMTP") as smtp:
            self.assertTrue(send_email.send_log_email(self.log))
        self.assertIn("签到成功", smtp.return_value.send_message.call_args.args[0]["Subject"])

    def test_invalid_port_is_a_clean_failure(self):
        with patch.dict(os.environ, {"SMTP_PORT": "invalid"}), patch("send_email.smtplib.SMTP") as smtp:
            self.assertFalse(send_email.send_log_email(self.log))
        smtp.assert_not_called()

    def test_tls_failure_closes_connection_and_hides_exception(self):
        output = io.StringIO()
        with patch("send_email.smtplib.SMTP") as smtp, contextlib.redirect_stdout(output):
            smtp.return_value.starttls.side_effect = RuntimeError("sensitive-detail")
            self.assertFalse(send_email.send_log_email(self.log))
        smtp.return_value.__exit__.assert_called_once()
        self.assertNotIn("sensitive-detail", output.getvalue())

    def test_missing_credentials_skips_without_network_failure(self):
        with patch.dict(os.environ, {"EMAIL_PASSWORD": ""}), patch("send_email.smtplib.SMTP") as smtp:
            self.assertTrue(send_email.send_log_email(self.log))
        smtp.assert_not_called()
