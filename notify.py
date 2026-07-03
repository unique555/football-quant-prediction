"""
推送通知模块 — Telegram / Webhook / 微信预留
用法:
  from notify import send
  send("预测完成: France vs Sweden → 主胜 53%")
"""

import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── 从环境变量读取配置 ──
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # 通用 webhook (飞书/钉钉/自定义)
WECHAT_APPID = os.getenv("WECHAT_APPID", "")  # 微信公众号 AppID (预留)
WECHAT_SECRET = os.getenv("WECHAT_SECRET", "")  # 微信公众号 Secret (预留)

# ── 缓存 ──
_last_send = 0
_MIN_INTERVAL = 0.5  # 最小间隔秒


def send(msg: str, disable_preview: bool = True) -> dict:
    """主入口: 自动选择可用渠道发送"""
    results = {}

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        results["telegram"] = _send_telegram(msg, disable_preview)

    if WEBHOOK_URL:
        results["webhook"] = _send_webhook(msg)

    return results


def send_file(filepath: str, caption: str = "") -> dict:
    """发送文件 (仅 Telegram 支持)"""
    global _last_send
    results = {}

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        _rate_limit()
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
        with open(filepath, "rb") as f:
            r = requests.post(
                url,
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": caption or os.path.basename(filepath),
                },
                files={"document": f},
                timeout=30,
            )
        results["telegram"] = {"status": r.status_code, "ok": r.json().get("ok", False)}

    return results


def send_md_report(md_text: str, title: str = "") -> dict:
    """发送 Markdown 格式消息 (Telegram MarkdownV2)"""
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return {}

    global _last_send
    _rate_limit()

    # Telegram MarkdownV2 转义
    import re

    esc_chars = r"_*[]()~`>#+-=|{}.!"

    def esc(text):
        return re.sub(f"([{re.escape(esc_chars)}])", r"\\\\\\1", text)

    # 限制长度 (Telegram 限制 4096 字符)
    if len(md_text) > 3800:
        md_text = md_text[:3800] + "\n\n...(truncated, see full report)"

    title_line = f"*{esc(title)}*\n\n" if title else ""
    msg = title_line + md_text

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        },
        timeout=15,
    )

    return {"status": r.status_code, "ok": r.json().get("ok", False)}


# ── 内部实现 ──


def _send_telegram(msg: str, disable_preview: bool = True) -> dict:
    global _last_send
    _rate_limit()
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "disable_web_page_preview": disable_preview,
        },
        timeout=15,
    )
    resp = r.json()
    if not resp.get("ok"):
        print(f"  ⚠️ Telegram 发送失败: {resp.get('description', '?')}")
    return {"status": r.status_code, "ok": resp.get("ok", False)}


def _send_webhook(msg: str) -> dict:
    """通用 webhook (飞书/钉钉格式: {"msgtype":"text","text":{"content":"..."}})"""
    try:
        r = requests.post(
            WEBHOOK_URL,
            json={
                "msgtype": "text",
                "text": {"content": f"[Football-Q] {msg}"},
            },
            timeout=15,
        )
        return {"status": r.status_code}
    except Exception as e:
        return {"error": str(e)}


def _rate_limit():
    global _last_send
    elapsed = time.time() - _last_send
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_send = time.time()


# ── 状态查询 ──


def status() -> dict:
    return {
        "telegram": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "webhook": bool(WEBHOOK_URL),
        "wechat": bool(WECHAT_APPID and WECHAT_SECRET),
    }


if __name__ == "__main__":
    print("📡 通知系统状态:", json.dumps(status(), indent=2))
    if status()["telegram"]:
        r = send("✅ Football-Quant 通知系统已就绪")
        print("测试发送:", r)
    else:
        print("⚠️ Telegram 未配置, 请设置环境变量 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID")
