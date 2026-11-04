import unittest
from unittest.mock import Mock, patch

from automation import CheckInAutomation, PlaywrightTimeoutError


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.automation = CheckInAutomation.__new__(CheckInAutomation)
        self.page = Mock()

    def test_absent_age_overlay_does_not_click(self):
        overlay = self.page.locator.return_value
        overlay.is_visible.return_value = False
        self.automation._dismiss_age_confirmation(self.page)
        overlay.locator.assert_not_called()

    def test_age_overlay_must_disappear(self):
        overlay = self.page.locator.return_value
        overlay.is_visible.return_value = True
        self.automation._dismiss_age_confirmation(self.page)
        overlay.locator.return_value.filter.return_value.click.assert_called_once()
        overlay.wait_for.assert_called_once_with(state="hidden", timeout=15000)

    def test_stuck_age_overlay_fails_navigation(self):
        overlay = self.page.locator.return_value
        overlay.wait_for.side_effect = PlaywrightTimeoutError("still visible")
        self.assertFalse(self.automation._navigate_to_sakurafrp(self.page))

    def test_dashboard_timeout_is_not_success(self):
        with patch.object(self.automation, "_wait_for_dashboard",
                          side_effect=PlaywrightTimeoutError("not ready")):
            self.assertFalse(self.automation._navigate_to_sakurafrp(self.page))

    def test_late_overlay_is_checked_again_after_blocked_click(self):
        button = Mock()
        button.click.side_effect = [PlaywrightTimeoutError("intercepted"), None]
        with patch.object(self.automation, "_dismiss_age_confirmation") as dismiss:
            self.automation._click_checkin(self.page, button)
        self.assertEqual(dismiss.call_count, 2)
        self.assertEqual(button.click.call_count, 2)

    def test_unrelated_blocker_has_bounded_retries(self):
        button = Mock()
        button.click.side_effect = PlaywrightTimeoutError("other overlay")
        with patch("automation.time.monotonic", side_effect=[0, 0, 31]):
            with self.assertRaises(PlaywrightTimeoutError):
                self.automation._click_checkin(self.page, button)
        button.click.assert_called_once()

    def test_click_success_is_not_repeated(self):
        button = Mock()
        self.automation._click_checkin(self.page, button)
        button.click.assert_called_once()


if __name__ == "__main__":
    unittest.main()
