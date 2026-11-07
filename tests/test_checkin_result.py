import unittest
from unittest.mock import Mock, patch
from automation import CheckInAutomation, PlaywrightTimeoutError


class ResultTests(unittest.TestCase):
    def setUp(self):
        self.runner = CheckInAutomation.__new__(CheckInAutomation)
        self.runner.max_retries = 1
        self.runner.simulator = Mock()
        self.runner.captcha_handler = Mock()
        self.page = Mock()
        p = patch.object(self.runner, "_click_checkin")
        p.start()
        self.addCleanup(p.stop)

    def test_already_done_does_not_wait_for_button(self):
        self.assertEqual(self.runner._wait_for_checkin_state(self.page), "done")
        self.page.get_by_role.assert_not_called()
        with patch.object(self.runner, "_wait_for_checkin_state", return_value="done"):
            self.assertTrue(self.runner._perform_checkin(self.page))
        self.runner.captcha_handler.handle_geetest_captcha.assert_not_called()

    def test_first_success_only_logs_one_attempt(self):
        with patch.object(self.runner, "_wait_for_checkin_state", return_value="ready"):
            with self.assertLogs("automation", level="INFO") as logs:
                self.assertTrue(self.runner._perform_checkin(self.page))
        attempts = [line for line in logs.output if "验证码尝试 " in line]
        self.assertEqual(len(attempts), 1)
        self.assertIn("1/1", attempts[0])
        self.page.reload.assert_not_called()
        self.page.get_by_text.return_value.first.wait_for.assert_called_once_with(
            state="visible", timeout=20000)

    def test_last_attempt_success_after_refresh(self):
        self.page.get_by_text.return_value.first.wait_for.side_effect = PlaywrightTimeoutError("pending")
        with patch.object(self.runner, "_wait_for_checkin_state", side_effect=["ready", "done"]):
            self.assertTrue(self.runner._perform_checkin(self.page))
        self.page.reload.assert_called_once()
        self.runner.captcha_handler.handle_geetest_captcha.assert_called_once()

    def test_exhaustion_does_not_claim_success(self):
        self.page.get_by_text.return_value.first.wait_for.side_effect = PlaywrightTimeoutError("pending")
        with patch.object(self.runner, "_wait_for_checkin_state", return_value="ready"):
            self.assertFalse(self.runner._perform_checkin(self.page))
        self.runner.captcha_handler.handle_geetest_captcha.assert_called_once()

    def test_missing_both_states_times_out(self):
        self.page.get_by_text.return_value.first.is_visible.return_value = False
        self.page.get_by_role.return_value.is_visible.return_value = False
        with patch("automation.time.monotonic", side_effect=[0, 21]):
            with self.assertRaises(PlaywrightTimeoutError):
                self.runner._wait_for_checkin_state(self.page)
