import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
import main


class SessionTest(unittest.TestCase):
    def test_lost_login_stops_before_next_recipient(self):
        settings = main.load_settings()
        browser = MagicMock()
        page = MagicMock()
        state = MagicMock()
        state.day = datetime.now(main.ZoneInfo(settings["schedule"]["timezone"])).date().isoformat()
        state.was_attempted.return_value = False
        with patch.object(main, "load_settings", return_value=settings), \
             patch.object(main, "load_friends", return_value=[{"name": "fixture"}] * 2), \
             patch.object(main, "in_send_window", return_value=True), \
             patch.object(main, "load_json", return_value=[{"name": "test", "value": "synthetic"}]), \
             patch.object(main, "DeliveryState", return_value=state), \
             patch.object(main, "sync_playwright"), \
             patch.object(main, "init_browser", return_value=(browser, MagicMock(), page)), \
             patch.object(main, "take_screenshot"), \
             patch.object(main.time, "sleep"), \
             patch.object(main, "find_conversation", return_value=None), \
             patch.object(main, "open_chat_page", side_effect=[main.RunStatus.OK, main.RunStatus.LOGIN_REQUIRED]) as check, \
             patch.object(main, "send_message") as send:
            result = main.run(1)
            self.assertEqual(result, main.RunStatus.LOGIN_REQUIRED)
            self.assertEqual(check.call_count, 2)
            send.assert_not_called()
            browser.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
