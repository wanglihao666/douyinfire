#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音私信自动续火花 - 主程序
基于 Playwright 模拟真人操作，接入一言API生成文艺文案
支持 GitHub Action / 本地 / 云服务器 部署
"""

import argparse
import json
import os
import re
import sys
import time
import random
import logging
import requests
from datetime import datetime
from enum import IntEnum
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import Error as PlaywrightError, sync_playwright, TimeoutError as PlaywrightTimeoutError

# ==================== 路径配置 ====================
BASE_DIR = Path(__file__).parent.resolve()
CONFIG_DIR = BASE_DIR / "config"
LOG_DIR = BASE_DIR / "logs"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
COOKIE_FILE = BASE_DIR / "cookies.json"
CHAT_LIST_SELECTOR = '[class*="conversationConversationListwrapper"]:visible, [class*="conversationConversationItemwrapper"]:visible, [class*="chat-list"]:visible, [data-e2e*="conversation"]:visible'
CHAT_URL = "https://www.douyin.com/chat"

for d in [LOG_DIR, SCREENSHOT_DIR]:
    d.mkdir(exist_ok=True)

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"run_{datetime.now().strftime('%Y%m%d')}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ==================== 配置加载 ====================
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_settings():
    return load_json(CONFIG_DIR / "settings.json")

def load_friends():
    data = load_json(CONFIG_DIR / "friends.json")
    return [f for f in data["friends"] if f.get("enabled", True)]

# ==================== 一言API ====================
def get_hitokoto(settings):
    """从一言API获取随机文艺文案"""
    msg_cfg = settings["message"]
    if msg_cfg["source"] != "hitokoto_api":
        return random.choice(msg_cfg["fallback_messages"])

    api_url = msg_cfg["hitokoto_api"]
    params = msg_cfg["hitokoto_params"]

    try:
        # 随机选一个分类
        category = random.choice(params["c"])
        resp = requests.get(api_url, params={"c": category, "encode": "json"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("hitokoto", "").strip()
        if text and len(text) <= msg_cfg.get("max_length", 50):
            logger.info(f"一言API获取成功: {text[:30]}...")
            return text
        else:
            logger.warning(f"一言API返回文本过长或为空，使用备用文案")
    except Exception as e:
        logger.warning(f"一言API请求失败: {e}，使用备用文案")

    return random.choice(msg_cfg["fallback_messages"])

def build_message(settings):
    """构建最终发送的消息（文案 + 可选表情）"""
    text = get_hitokoto(settings)
    msg_cfg = settings["message"]
    if msg_cfg.get("add_emoji", False):
        emoji = random.choice(msg_cfg["emoji_pool"])
        text = f"{text} {emoji}"
    return text

# ==================== 真人模拟 ====================
def human_typing(page, selector, text, settings):
    """模拟真人打字输入"""
    hum = settings["humanizer"]
    if not hum.get("enabled", True):
        page.fill(selector, text)
        return

    input_el = page.locator(selector).first
    input_el.click()
    time.sleep(random.uniform(0.3, 0.8))

    for char in text:
        input_el.type(char, delay=random.randint(
            hum["typing_speed_min_ms"],
            hum["typing_speed_max_ms"]
        ))

    time.sleep(random.uniform(0.5, 1.5))

def human_pause(settings, min_key="pre_send_pause_min_s", max_key="pre_send_pause_max_s"):
    """随机停顿模拟真人"""
    hum = settings["humanizer"]
    if not hum.get("enabled", True):
        return
    delay = random.uniform(hum[min_key], hum[max_key])
    logger.info(f"真人模拟停顿 {delay:.1f} 秒")
    time.sleep(delay)

# ==================== 浏览器操作 ====================
def init_browser(playwright, settings, cookies):
    """启动浏览器并加载Cookie"""
    br_cfg = settings["browser"]
    browser = playwright.chromium.launch(
        headless=br_cfg["headless"],
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--window-size=1280,960",
        ]
    )
    context = browser.new_context(
        viewport={"width": br_cfg["viewport_width"], "height": br_cfg["viewport_height"]},
        user_agent=br_cfg["user_agent"],
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )

    # 反检测：注入脚本隐藏自动化特征
    context.add_init_script("""
        // 隐藏 webdriver
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });

        // 伪造 plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });

        // 伪造 languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en']
        });

        // 伪造 chrome 对象
        window.chrome = {
            runtime: {}
        };

        // 伪造 permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """)

    try:
        context.add_cookies(cookies)
    except Exception:
        browser.close()
        raise ValueError("Cookie 格式不符合 Playwright 要求") from None

    page = context.new_page()
    page.set_default_timeout(br_cfg["timeout_ms"])
    return browser, context, page

def search_and_open_chat(page, friend_name):
    """打开唯一匹配好友名称的会话"""
    logger.info(f"正在打开与 {friend_name} 的聊天窗口")

    rows = page.locator('[class*="conversation"]:visible, [class*="Conversation"]:visible')
    name = page.get_by_text(friend_name, exact=True)
    conversations = rows.and_(name).or_(rows.filter(has=name))
    try:
        conversations.click(timeout=8000)
        page.locator('[contenteditable="true"][data-placeholder*="发"]').wait_for(
            state="visible", timeout=8000
        )
    except Exception:
        logger.error("无法唯一定位好友会话或消息输入框，跳过发送")
        return False
    return True


def send_message(page, message, settings):
    """在当前聊天窗口发送消息"""
    logger.info(f"准备发送消息: {message[:30]}...")

    # 抖音私信输入框：contenteditable=true，placeholder=发送消息
    input_selectors = [
        '[contenteditable="true"][data-placeholder*="发"]',
    ]

    input_box = None
    for sel in input_selectors:
        try:
            loc = page.locator(sel)
            if loc.is_visible(timeout=3000):
                input_box = loc
                break
        except Exception:
            continue

    if not input_box:
        logger.error("无法找到消息输入框")
        take_screenshot(page, "input_not_found")
        return False

    if (input_box.text_content() or "").strip():
        logger.error("会话输入框已有内容，保留原草稿并跳过")
        return False

    existing_messages = page.get_by_text(message, exact=True).count()

    # 真人模拟：先停顿，模拟看消息
    human_pause(settings)

    # 点击输入框聚焦
    input_box.click()
    time.sleep(random.uniform(0.3, 0.8))

    # 用键盘逐字输入（模拟真人打字）
    try:
        for char in message:
            page.keyboard.type(char, delay=random.randint(
                settings["humanizer"]["typing_speed_min_ms"],
                settings["humanizer"]["typing_speed_max_ms"]
            ))
    except Exception as e:
        logger.warning(f"键盘逐字输入异常: {e}，改用插入文本")
        try:
            page.keyboard.insert_text(message)
        except Exception as e2:
            logger.error(f"插入文本失败: {e2}")
            return False

    # 发送前停顿
    human_pause(settings)

    if (input_box.text_content() or "").strip() != message:
        logger.error("输入框内容与待发送消息不一致")
        return False

    # 发送：按Enter（抖音私信默认Enter发送）
    input_box.press("Enter")
    try:
        page.wait_for_function("(editor) => !editor.textContent.trim()", arg=input_box.element_handle(), timeout=5000)
        page.get_by_text(message, exact=True).nth(existing_messages).wait_for(state="visible", timeout=5000)
    except PlaywrightTimeoutError:
        logger.error("未在会话中确认新消息，避免重复发送，本次不重试")
        return False
    logger.info("已在会话中看到新消息")
    return True


def take_screenshot(page, friend_name):
    """截图留证"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c for c in friend_name if c.isalnum() or c in "_-")
    path = SCREENSHOT_DIR / f"{safe_name}_{timestamp}.png"
    try:
        page.screenshot(path=str(path))
        logger.info(f"截图已保存: {path.name}")
    except Exception as e:
        logger.warning(f"截图失败: {e}")

# ==================== 主流程 ====================
class RunStatus(IntEnum):
    OK = 0
    OUTSIDE_WINDOW = 2
    INVALID_RECIPIENT = 3
    LOGIN_REQUIRED = 4
    CHAT_UNAVAILABLE = 5
    SEND_FAILED = 6
    HTTP_REJECTED = 7
    VERIFICATION_REQUIRED = 8
    NAVIGATION_FAILED = 9
    UNEXPECTED_PAGE = 10


def in_send_window(now, schedule):
    current = now.strftime("%H:%M")
    start = schedule["send_window_start"]
    end = schedule["send_window_end"]
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def open_chat_page(page, timeout):
    response = None
    for attempt in range(3):
        try:
            response = page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=60000)
            break
        except PlaywrightError:
            if attempt == 2:
                return RunStatus.NAVIGATION_FAILED
            time.sleep(5)

    if response and response.status >= 400:
        logger.warning("抖音私信页返回 HTTP %s", response.status)
        if response.status == 401:
            return RunStatus.LOGIN_REQUIRED
        return RunStatus.HTTP_REJECTED

    try:
        page.locator(CHAT_LIST_SELECTOR).first.wait_for(state="visible", timeout=timeout)
        return RunStatus.OK
    except PlaywrightTimeoutError:
        location = urlsplit(page.url)
        challenge = page.get_by_text(
            re.compile(r"请完成(?:安全)?验证|拖动滑块|请进行安全验证|访问过于频繁")
        ).first
        if "captcha" in location.path.lower() or challenge.is_visible():
            return RunStatus.VERIFICATION_REQUIRED
        login = page.get_by_text(
            re.compile(r"登录后.*(?:私信|聊天)|扫码登录|手机号登录|验证码登录|密码登录")
        ).first
        if "login" in location.path or "passport" in location.netloc or login.is_visible():
            return RunStatus.LOGIN_REQUIRED
        if location.hostname != "www.douyin.com" or location.path.rstrip("/") != "/chat":
            return RunStatus.UNEXPECTED_PAGE
        return RunStatus.CHAT_UNAVAILABLE


def run(recipient):
    logger.info("=" * 50)
    logger.info("抖音自动续火花任务开始")
    logger.info("=" * 50)

    settings = load_settings()
    friends = load_friends()
    check_only = recipient == 0
    if not check_only:
        if not 1 <= recipient <= len(friends):
            logger.error("好友序号超出启用好友列表")
            return RunStatus.INVALID_RECIPIENT
        friends = [friends[recipient - 1]]
    logger.info(f"加载配置完成，共 {len(friends)} 个启用的好友")

    sched = settings["schedule"]
    now = datetime.now(ZoneInfo(sched["timezone"]))
    if not check_only and not in_send_window(now, sched):
        logger.info("当前时间不在发送窗口，跳过发送")
        return RunStatus.OUTSIDE_WINDOW

    try:
        cookies = load_json(COOKIE_FILE)
        if not isinstance(cookies, list) or not cookies or not all(isinstance(cookie, dict) for cookie in cookies):
            raise ValueError
    except (OSError, ValueError):
        logger.error("缺少有效的 cookies.json，请先运行 scripts/get_cookie.py")
        return RunStatus.LOGIN_REQUIRED

    with sync_playwright() as p:
        try:
            browser, _, page = init_browser(p, settings, cookies)
        except ValueError:
            logger.error("Cookie 格式无效，请重新导出")
            return RunStatus.LOGIN_REQUIRED

        try:
            status = open_chat_page(page, settings["browser"]["timeout_ms"])
            if status != RunStatus.OK:
                return status

            if check_only:
                logger.info("登录检查通过，已打开私信列表")
                return RunStatus.OK

            logger.info("抖音私信页面加载成功")

            # 处理可能的弹窗（如"是否保存登录信息"）
            logger.info("检查并处理弹窗...")
            try:
                # 处理"是否保存登录信息"弹窗 - 点击取消
                cancel_selectors = [
                    'button:has-text("取消")',
                    'div:has-text("取消")',
                    '[class*="cancel"]',
                ]
                for sel in cancel_selectors:
                    try:
                        btn = page.locator(sel).first
                        if btn.is_visible(timeout=2000):
                            btn.click()
                            logger.info(f"已点击取消按钮: {sel}")
                            time.sleep(1)
                            break
                    except Exception:
                        continue

                # 处理其他可能的弹窗（按ESC关闭）
                page.keyboard.press("Escape")
                time.sleep(1)
            except Exception as e:
                logger.warning(f"弹窗处理异常: {e}")

            # 截图记录处理弹窗后的状态
            take_screenshot(page, "after_popup")

            # 逐个好友发送
            success_count = 0
            fail_count = 0

            for i, friend in enumerate(friends):
                friend_name = friend["name"]
                logger.info(f"\n--- [{i+1}/{len(friends)}] 处理好友: {friend_name} ---")

                try:
                    # 搜索并打开聊天
                    if not search_and_open_chat(page, friend_name):
                        logger.error(f"跳过 {friend_name}: 无法打开聊天")
                        fail_count += 1
                        continue

                    # 生成消息
                    message = build_message(settings)
                    logger.info(f"消息内容: {message}")

                    # 发送
                    if send_message(page, message, settings):
                        success_count += 1
                        take_screenshot(page, friend_name)
                    else:
                        fail_count += 1

                except PlaywrightTimeoutError:
                    logger.error(f"处理 {friend_name} 超时")
                    fail_count += 1
                    take_screenshot(page, f"{friend_name}_timeout")
                except Exception as e:
                    logger.error(f"处理 {friend_name} 出错: {e}", exc_info=True)
                    fail_count += 1
                    take_screenshot(page, f"{friend_name}_error")

                # 好友之间随机间隔（真人模拟）
                if i < len(friends) - 1:
                    delay = random.randint(
                        sched["random_delay_per_friend_min"],
                        sched["random_delay_per_friend_max"]
                    )
                    logger.info(f"等待 {delay} 秒后处理下一个好友...")
                    time.sleep(delay)

            logger.info("\n" + "=" * 50)
            logger.info(f"任务完成！成功: {success_count}, 失败: {fail_count}")
            logger.info("=" * 50)
            return RunStatus.SEND_FAILED if fail_count else RunStatus.OK

        except Exception as e:
            logger.error(f"主流程出错: {e}", exc_info=True)
            take_screenshot(page, "fatal_error")
            return RunStatus.CHAT_UNAVAILABLE
        finally:
            browser.close()
            logger.info("浏览器已关闭")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="检查抖音私信登录，或在发送窗口内给一位好友试发")
    parser.add_argument(
        "--recipient-index", type=int, default=os.getenv("DOUYIN_RECIPIENT_INDEX") or "0",
        help="0 只检查登录（默认），正整数对应启用好友的配置顺序",
    )
    sys.exit(run(parser.parse_args().recipient_index))
