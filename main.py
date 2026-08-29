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
    """打开与好友的聊天窗口 - 直接点击左侧会话列表，搜索作为兜底"""
    logger.info(f"正在打开与 {friend_name} 的聊天窗口")

    # 主方案：直接点击左侧聊天列表中的会话
    conversation_selectors = [
        f'//div[contains(@class,"conversation") and .//text()="{friend_name}"]',
        f'//div[contains(@class,"Conversation") and .//text()="{friend_name}"]',
        f'//div[contains(@class,"chat") and .//text()="{friend_name}"]',
    ]

    for sel in conversation_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                loc.click()
                logger.info(f"已点击聊天列表中的 {friend_name}")
                time.sleep(random.uniform(2, 4))
                # 验证聊天窗口打开（出现消息输入框）
                try:
                    page.locator('[contenteditable="true"]').first.wait_for(state="visible", timeout=8000)
                    logger.info(f"聊天窗口已打开: {friend_name}")
                except Exception:
                    logger.warning(f"聊天窗口打开但未检测到输入框: {friend_name}")
                return True
        except Exception:
            continue

    # 兜底：搜索好友
    logger.info(f"聊天列表未找到 {friend_name}，尝试搜索")
    try:
        search_box = page.locator('input[placeholder*="搜索"]').first
        if search_box.is_visible(timeout=3000):
            search_box.click()
            time.sleep(0.5)
            search_box.fill(friend_name)
            time.sleep(2)
            # 点击搜索结果中的会话或发消息
            for sel in [
                f'//div[contains(@class,"conversation") and .//text()="{friend_name}"]',
                'button:has-text("发消息")',
            ]:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=3000):
                        loc.click()
                        logger.info(f"通过搜索打开 {friend_name}")
                        time.sleep(3)
                        return True
                except Exception:
                    continue
            # 按Enter
            search_box.press("Enter")
            time.sleep(3)
            logger.info(f"通过搜索+Enter打开 {friend_name}")
            return True
    except Exception as e:
        logger.error(f"无法打开与 {friend_name} 的聊天: {e}")
        take_screenshot(page, f"open_chat_fail_{friend_name}")
        return False


def send_message(page, message, settings):
    """在当前聊天窗口发送消息"""
    logger.info(f"准备发送消息: {message[:30]}...")

    # 抖音私信输入框：contenteditable=true，placeholder=发送消息
    input_selectors = [
        '[contenteditable="true"][data-placeholder*="发送"]',
        '[contenteditable="true"][data-placeholder*="发"]',
        '[contenteditable="true"]',
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
        take_screenshot(page, "input_not_found")
        return False

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

    # 发送：按Enter（抖音私信默认Enter发送）
    sent = False
    try:
        page.keyboard.press("Enter")
        sent = True
        logger.info("通过Enter键发送消息")
    except Exception as e:
        logger.error(f"Enter发送失败: {e}")

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

    # 发送窗口判断：只有当前时间在窗口内才发送（配合频繁的定时触发）
    def in_send_window(t, win_start, win_end):
        hm = t.strftime("%H:%M")
        if win_start <= win_end:
            return win_start <= hm <= win_end
        else:  # 跨天窗口，如 23:00 - 02:00
            return hm >= win_start or hm <= win_end

    if not in_send_window(now, sched["send_window_start"], sched["send_window_end"]):
        logger.info(f"当前时间 {now.strftime('%H:%M')} 不在发送窗口 {sched['send_window_start']}-{sched['send_window_end']} 内，跳过本次")
        return False

    with sync_playwright() as p:
        browser, context, page = init_browser(p, settings)

        try:
            # 打开抖音私信页（带重试，避免网络波动）
            logger.info("正在打开抖音私信页面...")
            page.set_default_timeout(60000)
            page_loaded = False
            for attempt in range(3):
                try:
                    page.goto("https://www.douyin.com/chat", wait_until="domcontentloaded", timeout=60000)
                    page_loaded = True
                    break
                except Exception as e:
                    logger.warning(f"打开抖音第{attempt+1}次失败: {str(e)[:60]}")
                    if attempt == 2:
                        logger.error("抖音页面打开失败")
                        take_screenshot(page, "page_open_fail")
                        return False
                    time.sleep(5)
            if not page_loaded:
                return False
            
            # 等待页面加载完成
            logger.info("等待页面加载...")
            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                logger.warning("等待networkidle超时，继续执行")
            
            # 额外等待，确保React应用渲染完成
            time.sleep(random.uniform(8, 12))
            
            # 尝试滚动页面触发懒加载
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)
                page.evaluate("window.scrollTo(0, 0)")
                time.sleep(1)
            except Exception:
                pass
            
            # 等待搜索框出现（最多等待30秒）
            logger.info("等待搜索框出现...")
            search_found = False
            for wait_sel in ['input[placeholder*="搜索"]', 'input[type="text"]', '[contenteditable="true"]', 'div[class*="search"]']:
                try:
                    page.wait_for_selector(wait_sel, timeout=10000, state="visible")
                    logger.info(f"搜索框已出现: {wait_sel}")
                    search_found = True
                    break
                except Exception:
                    continue
            
            if not search_found:
                logger.warning("未检测到搜索框，页面可能未完全渲染")
            
            # 截图记录初始页面状态
            take_screenshot(page, "initial_page")

            # 检查是否需要登录（更严格的检查：URL包含login或出现登录表单）
            current_url = page.url
            logger.info(f"当前URL: {current_url}")
            if "login" in current_url or "passport" in current_url:
                logger.error("跳转到登录页，Cookie已失效，请重新获取Cookie")
                take_screenshot(page, "login_required")
                return False

            # 检查页面是否有登录按钮（且没有聊天列表）
            try:
                has_chat_list = page.locator('[class*="conversation"], [class*="chat-list"], [data-e2e*="conversation"]').count() > 0
                has_login_btn = page.locator('button:has-text("登录"), a:has-text("登录")').count() > 0
                if has_login_btn and not has_chat_list:
                    logger.error("页面显示登录按钮且无聊天列表，Cookie可能已失效")
                    take_screenshot(page, "login_required")
                    return False
            except Exception as e:
                logger.warning(f"登录状态检查异常: {e}")

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
