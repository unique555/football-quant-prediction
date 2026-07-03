"""
价值筛选+推送任务 — 扫描已分析比赛 → 筛选 edge>阈值 → Kelly 注额 → Telegram 推送
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from celery.utils.log import get_task_logger
from core.database import AsyncSessionLocal
from models.match import Match
from models.prediction import Prediction
from services.notify import send_value_bet
from sqlalchemy import desc, select

from tasks.celery_app import celery_app

logger = get_task_logger(__name__)

EDGE_THRESHOLD = 0.03  # 至少 3% edge 才推送
MAX_PUSH_PER_RUN = 5   # 单次最多推送 5 场（防止刷屏）


@celery_app.task(name="tasks.value_screener.run")
def run_value_screener() -> dict:
    """定时价值筛选+推送 — auto_analyze 后 30 分钟运行"""
    return asyncio.run(_run())


async def _run() -> dict:
    stats = {"candidates": 0, "pushed": 0, "skipped": 0}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    since = now - timedelta(hours=6)  # 最近 6 小时内分析的

    async with AsyncSessionLocal() as session:
        # 查找有 edge 的预测
        preds = (
            (
                await session.execute(
                    select(Prediction, Match)
                    .outerjoin(Match, Prediction.match_id == Match.id)
                    .where(
                        Prediction.created_at >= since,
                        Prediction.settled_status == "pending",
                        Prediction.best_ev.is_not(None),
                        Prediction.best_ev > 0,
                    )
                    .order_by(desc(Prediction.best_ev))
                    .limit(MAX_PUSH_PER_RUN)
                )
            )
            .all()
        )

        stats["candidates"] = len(preds)

        if not preds:
            logger.info("value_screener: no value bets found")
            return stats

        messages = []
        for pred, match in preds:
            edge = pred.best_edge or 0
            if edge < EDGE_THRESHOLD:
                stats["skipped"] += 1
                continue

            msg = _format_value_bet(pred, match)
            messages.append(msg)
            stats["pushed"] += 1

        if messages:
            combined = "\n\n".join(messages)
            send_value_bet(combined)

    logger.info("value_screener result: %s", stats)
    return stats


def _format_value_bet(pred: Prediction, match: Match | None) -> str:
    """格式化单场价值投注消息（Telegram 精简版）"""
    home = match.home_team_name if match else "?"
    away = match.away_team_name if match else "?"
    league = match.league_name if match else ""
    kickoff = match.match_date.strftime("%m-%d %H:%M") if match and match.match_date else "?"

    lines = [
        f"⚽ {league} | {home} vs {away} | {kickoff}",
        f"推荐: {pred.best_display_pick or '?'} @ {pred.best_odds or '?'} ({pred.best_bookmaker or '?'})",
        f"Edge: {pred.best_edge or 0:+.1%} | EV: {pred.best_ev or 0:+.1%}",
        f"Kelly: {(pred.best_kelly or 0):.1%} ({_kelly_label(pred.best_kelly or 0)})",
        f"风险: {pred.risk or '?'} | 价值分: {pred.value_score or 0}/100",
    ]
    return "\n".join(lines)


def _kelly_label(kelly: float) -> str:
    if kelly >= 0.08:
        return "max"
    if kelly >= 0.05:
        return "half"
    if kelly >= 0.02:
        return "quarter"
    if kelly > 0:
        return "minimum"
    return "skip"
