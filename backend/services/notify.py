"""
通知服务 — Telegram 推送（价值投注 / 日报 / 告警）
"""

from __future__ import annotations

import logging

import requests
from core.config import settings

logger = logging.getLogger(__name__)


def send_telegram(message: str, parse_mode: str = "HTML") -> bool:
    """发送 Telegram 消息"""
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        logger.warning("Telegram not configured: token=%s chat_id=%s", bool(token), bool(chat_id))
        return False

    try:
        # Telegram 消息上限 4096 字符，截断
        if len(message) > 4000:
            message = message[:4000] + "\n\n... (截断)"

        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": parse_mode,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return True
        logger.warning("Telegram send failed: %s %s", resp.status_code, resp.text[:200])
        return False
    except Exception as e:
        logger.warning("Telegram send error: %s", e)
        return False


def send_value_bet(message: str) -> bool:
    """推送价值投注消息"""
    return send_telegram(f"💎 <b>价值投注提醒</b>\n\n{message}")


def send_daily_report(message: str) -> bool:
    """推送每日报告"""
    return send_telegram(f"📊 <b>每日分析报告</b>\n\n{message}")


def send_alert(message: str) -> bool:
    """推送系统告警"""
    return send_telegram(f"⚠️ <b>系统告警</b>\n\n{message}")


def send_error_alert(error_type: str, error_msg: str, source: str = "") -> bool:
    """发送异常告警到 Telegram"""
    return send_telegram(f"🚨 系统告警：{error_type}\n来源：{source}\n详情：{error_msg[:300]}")


def send_quota_alert(used: int, limit: int) -> bool:
    """发送 API 额度预警"""
    pct = used / limit * 100 if limit else 0
    level = "🔴" if pct > 90 else "🟡" if pct > 80 else "🟢"
    return send_telegram(f"{level} API 额度预警\n已使用：{used}/{limit} ({pct:.1f}%)")
