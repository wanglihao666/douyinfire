#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音私信自动续火花 - 主程序
基于 Playwright 模拟真人操作，接入一言API生成文艺文案
支持 GitHub Action / 本地 / 云服务器 部署
"""

import json
import os
import sys
import time
import random
import logging
import requests
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ==================== 路径配置 ====================
BASE_DIR = Path(__file__).parent.resolve()
CONFIG_DIR = BASE_DIR / "config"
LOG_DIR = BASE_DIR / "logs"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
COOKIE_FILE = BASE_DIR / "cookies.json"

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
def init_browser(playwright, settings):
    """启动浏览器并加载Cookie"""
    br_cfg = settings["browser"]
    browser = playwright.chromium.launch(
        headless=br_cfg["headless"],
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
    )
    context = browser.new_context(
        viewport={"width": br_cfg["viewport_width"], "height": br_cfg["viewport_height"]},
        user_agent=br_cfg["user_agent"],
        locale="zh-CN"
    )

    # 加载Cookie
    if COOKIE_FILE.exists():
        try:
            cookies = load_json(COOKIE_FILE)
            context.add_cookies(cookies)
            logger.info("Cookie加载成功")
        except Exception as e:
            logger.warning(f"Cookie加载失败: {e}")
    else:
        logger.warning("未找到cookies.json，请先运行 scripts/get_cookie.py 获取Cookie")

    page = context.new_page()
    page.set_default_timeout(br_cfg["timeout_ms"])
    return browser, context, page

def search_and_open_chat(page, friend_name, settings):
    """搜索好友并打开聊天窗口"""
    logger.info(f"正在搜索好友: {friend_name}")

    # 尝试多种搜索框选择器
    search_selectors = [
        'input[placeholder*="搜索"]',
        'input[type="text"]',
        'div[contenteditable="true"][data-placeholder*="搜索"]',
    ]

    search_box = None
    for sel in search_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                search_box = loc
                break
        except Exception:
            continue

    if not search_box:
        # 兜底：点击页面上的搜索图标
        try:
            page.click('svg[class*="search"]', timeout=3000)
            time.sleep(1)
            search_box = page.locator('input[type="text"]').first
        except Exception as e:
            logger.error(f"无法找到搜索框: {e}")
            return False

    # 清空并输入好友名
    search_box.click()
    search_box.fill("")
    human_typing(page, search_box._selector if hasattr(search_box, '_selector') else search_selectors[0], friend_name, settings)
    time.sleep(random.uniform(1.5, 3))

    # 点击搜索结果中的好友
    result_selectors = [
        f'//div[contains(@class,"conversation") and .//text()="{friend_name}"]',
        f'//div[contains(text(),"{friend_name}") and contains(@class,"name")]',
        f'div[data-e2e*="conversation"]:has-text("{friend_name}")',
    ]

    for sel in result_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                loc.click()
                logger.info(f"已打开与 {friend_name} 的聊天窗口")
                time.sleep(random.uniform(2, 4))
                return True
        except Exception:
            continue

    # 兜底：按Enter选择第一个结果
    try:
        page.press('input[type="text"]', 'Enter')
        time.sleep(2)
        logger.info(f"通过Enter键尝试打开 {friend_name} 的聊天")
        return True
    except Exception as e:
        logger.error(f"无法打开与 {friend_name} 的聊天: {e}")
        return False

def send_message(page, message, settings):
    """在当前聊天窗口发送消息"""
    logger.info(f"准备发送消息: {message[:30]}...")

    # 抖音私信输入框是 Draft.js 编辑器，contenteditable=true
    input_selectors = [
        'div[contenteditable="true"][data-placeholder*="发送"]',
        'div[contenteditable="true"][class*="draft"]',
        'div[contenteditable="true"]',
        'div.public-DraftEditor-content',
    ]

    input_box = None
    for sel in input_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                input_box = loc
                break
        except Exception:
            continue

    if not input_box:
        logger.error("无法找到消息输入框")
        return False

    # 真人模拟：先停顿，模拟看消息
    human_pause(settings)

    # 模拟打字
    input_box.click()
    time.sleep(random.uniform(0.3, 0.8))
    for char in message:
        input_box.type(char, delay=random.randint(
            settings["humanizer"]["typing_speed_min_ms"],
            settings["humanizer"]["typing_speed_max_ms"]
        ))

    # 发送前停顿
    human_pause(settings)

    # 发送：尝试点击发送按钮或按Enter
    sent = False
    send_button_selectors = [
        'button[aria-label*="发送"]',
        'div[class*="send"]',
        'svg[class*="send"]',
    ]

    for sel in send_button_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click()
                sent = True
                logger.info("通过发送按钮发送消息")
                break
        except Exception:
            continue

    if not sent:
        try:
            input_box.press("Enter")
            sent = True
            logger.info("通过Enter键发送消息")
        except Exception as e:
            logger.error(f"发送失败: {e}")

    if sent:
        time.sleep(random.uniform(2, 4))
        logger.info("消息发送成功")
    return sent

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
def run():
    logger.info("=" * 50)
    logger.info("抖音自动续火花任务开始")
    logger.info("=" * 50)

    settings = load_settings()
    friends = load_friends()
    logger.info(f"加载配置完成，共 {len(friends)} 个启用的好友")

    # 阴间随机延时：在发送窗口内随机等待一段时间再开始
    sched = settings["schedule"]
    now = datetime.now()
    logger.info(f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"发送窗口: {sched['send_window_start']} - {sched['send_window_end']}")

    with sync_playwright() as p:
        browser, context, page = init_browser(p, settings)

        try:
            # 打开抖音私信页
            logger.info("正在打开抖音私信页面...")
            page.goto("https://www.douyin.com/chat", wait_until="domcontentloaded")
            time.sleep(random.uniform(3, 6))

            # 检查是否需要登录
            if "login" in page.url or page.locator('text=登录').first.is_visible():
                logger.error("未登录或Cookie已失效，请重新获取Cookie")
                take_screenshot(page, "login_required")
                return False

            logger.info("抖音私信页面加载成功")

            # 逐个好友发送
            success_count = 0
            fail_count = 0

            for i, friend in enumerate(friends):
                friend_name = friend["name"]
                logger.info(f"\n--- [{i+1}/{len(friends)}] 处理好友: {friend_name} ---")

                try:
                    # 搜索并打开聊天
                    if not search_and_open_chat(page, friend_name, settings):
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

        except Exception as e:
            logger.error(f"主流程出错: {e}", exc_info=True)
            take_screenshot(page, "fatal_error")
        finally:
            browser.close()
            logger.info("浏览器已关闭")

    return True

if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
