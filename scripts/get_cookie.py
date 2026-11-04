#!/usr/bin/env python3
"""手动登录抖音后，将当前会话的 Cookie 保存到项目目录。"""

import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error, sync_playwright

CHAT_URL = "https://www.douyin.com/chat"
COOKIE_FILE = Path(__file__).resolve().parents[1] / "cookies.json"


def main():
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            try:
                context = browser.new_context(locale="zh-CN")
                page = context.new_page()
                page.goto(CHAT_URL, wait_until="domcontentloaded")
                input("请在打开的浏览器中登录抖音，确认能看到私信列表后按回车。")
                location = urlsplit(page.url)
                if location.hostname != "www.douyin.com" or location.path.rstrip("/") != "/chat":
                    print("当前页面不是抖音私信页，原 Cookie 文件保留。")
                    return 1
                chat_list = page.locator('[class*="conversation"]:visible, [class*="chat-list"]:visible, [data-e2e*="conversation"]:visible')
                if not chat_list.first.is_visible():
                    print("未识别到私信列表，原 Cookie 文件保留。")
                    return 1
                cookies = context.cookies(CHAT_URL)
                if not cookies:
                    print("未读取到私信页 Cookie，原 Cookie 文件保留。")
                    return 1
            finally:
                browser.close()
    except (Error, EOFError, KeyboardInterrupt):
        print("Cookie 获取已中止，请检查 Chromium 是否安装、抖音页面是否可打开。")
        return 1

    with tempfile.NamedTemporaryFile(
        dir=COOKIE_FILE.parent, mode="w", encoding="utf-8", delete=False
    ) as temporary:
        path = Path(temporary.name)
        try:
            json.dump(cookies, temporary, ensure_ascii=False)
            temporary.close()
            os.replace(path, COOKIE_FILE)
        finally:
            path.unlink(missing_ok=True)
    print("Cookie 已保存到 cookies.json。请运行 python main.py 验证登录。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
