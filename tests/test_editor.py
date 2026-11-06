"""Regression for Douyin's Slate editor empty-text markers."""
import unittest
from unittest.mock import patch

from playwright.sync_api import sync_playwright
import main


class EditorTest(unittest.TestCase):
    def test_invisible_empty_markers_and_send_confirmation(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content("""
                    <div contenteditable="true" data-placeholder="发送消息"
                         style="min-height:30px"><span>&#8203;</span></div>
                    <section id="messages"></section>
                    <script>
                    document.querySelector('[contenteditable]').addEventListener('keydown', event => {
                        if (event.key !== 'Enter') return;
                        event.preventDefault();
                        const bubble = document.createElement('p');
                        bubble.className = 'TextMessageTextpureText';
                        bubble.textContent = event.target.textContent.replace(/[\\u200B\\uFEFF]/g, '').trim();
                        document.querySelector('#messages').append(bubble);
                        event.target.innerHTML = '<span>&#8203;</span>';
                    });
                    </script>
                """)
                settings = {"humanizer": {"typing_speed_min_ms": 1, "typing_speed_max_ms": 1}}
                reserve = unittest.mock.Mock(return_value=False)
                with patch.object(main, "human_pause"), patch.object(main.time, "sleep"):
                    self.assertIsNone(main.send_message(page, "hi", settings, reserve))
                    reserve.assert_called_once()
                    self.assertEqual(page.locator(main.MESSAGE_TEXT_SELECTOR).count(), 0)
                    page.locator(main.EDITOR_SELECTOR).fill("\ufeff")
                    self.assertTrue(main.send_message(page, "hi", settings, lambda: True))
                self.assertEqual(page.locator(main.MESSAGE_TEXT_SELECTOR).inner_text(), "hi")
                self.assertEqual(main.editor_text(page.locator(main.EDITOR_SELECTOR).text_content()), "")
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
