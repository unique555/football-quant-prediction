"""Telegram long-polling worker for the Docker MVP."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import requests
from core.config import settings
from core.database import AsyncSessionLocal
from models.match import Match
from models.prediction import Prediction
from models.telegram_mvp import OddsSnapshot, Result, Subscription
from requests import HTTPError
from services.telegram_mvp.api_football import ApiFootballClient
from services.telegram_mvp.fixtures import FixtureCandidate
from services.telegram_mvp.names import MatchQuery, parse_match_text
from services.telegram_mvp.pipeline import (
    TelegramAnalysisPipeline,
    add_alias,
    performance_summary,
    stats_summary,
)
from sqlalchemy import delete, desc, select

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("football_quant.bot")


@dataclass
class CandidateCache:
    candidates: list[FixtureCandidate]
    expires_at: float
    query: MatchQuery | None = None


class TelegramBotWorker:
    def __init__(self):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise RuntimeError("TELEGRAM_BOT_TOKEN 未配置")
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.pipeline = TelegramAnalysisPipeline()
        self.processing_messages: set[str] = set()
        self.processed_messages: dict[str, float] = {}
        self.candidate_cache: dict[str, CandidateCache] = {}
        self.offset = 0

    def send_message(
        self, chat_id: int | str, text: str, reply_markup: dict[str, Any] | None = None
    ) -> None:
        chunks = [text[i : i + 3800] for i in range(0, len(text), 3800)] or [text]
        for chunk in chunks:
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json=payload,
                timeout=20,
            )
            if not resp.ok:
                logger.warning("Telegram send failed: %s %s", resp.status_code, resp.text[:300])

    def get_updates(self) -> list[dict[str, Any]]:
        resp = requests.get(
            f"{self.base_url}/getUpdates",
            params={
                "offset": self.offset,
                "timeout": 30,
                "allowed_updates": ["message", "callback_query"],
            },
            timeout=35,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])

    def clear_webhook(self) -> None:
        try:
            resp = requests.post(
                f"{self.base_url}/deleteWebhook",
                json={"drop_pending_updates": False},
                timeout=15,
            )
            if resp.ok:
                logger.info("Telegram webhook cleared for polling mode")
            else:
                logger.warning("Telegram deleteWebhook failed: %s", resp.text[:300])
        except requests.RequestException as exc:
            logger.warning("Telegram deleteWebhook request failed: %s", exc)

    def cleanup(self) -> None:
        now = time.time()
        self.processed_messages = {
            key: ts for key, ts in self.processed_messages.items() if now - ts < 900
        }
        self.candidate_cache = {
            key: cache for key, cache in self.candidate_cache.items() if cache.expires_at > now
        }

    async def handle_update(self, update: dict[str, Any]) -> None:
        self.offset = max(self.offset, update.get("update_id", 0) + 1)
        if update.get("callback_query"):
            await self.handle_callback(update["callback_query"])
            return
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = (message.get("text") or "").strip()
        message_id = message.get("message_id")
        if not chat_id or not text or not message_id:
            return

        key = f"{chat_id}:{message_id}"
        if key in self.processing_messages or key in self.processed_messages:
            return
        self.processing_messages.add(key)
        try:
            await self.process_message(chat_id, text)
            self.processed_messages[key] = time.time()
        finally:
            self.processing_messages.discard(key)
            self.cleanup()

    async def process_message(self, chat_id: int, text: str) -> None:
        logger.info("message chat=%s text=%s", chat_id, text)
        normalized = text.replace("／", "/").strip()
        command = self.command_name(normalized)

        if command in {"/start", "/help", "/menu", "/菜单", "/帮助"} or normalized in {
            "帮助",
            "菜单",
        }:
            self.send_message(chat_id, self.help_text(), reply_markup=self.main_menu())
            return

        if command == "/status":
            self.send_message(chat_id, self.status_text())
            return

        if command in {"/stats", "/hitstats", "/performance", "/命中率", "/表现"}:
            async with AsyncSessionLocal() as session:
                if command in {"/hitstats", "/performance", "/命中率", "/表现"}:
                    perf = await performance_summary(session)
                    self.send_message(chat_id, self.format_performance(perf))
                else:
                    stats = await stats_summary(session)
                    self.send_message(chat_id, self.format_stats(stats))
            return

        if command == "/web":
            self.send_message(
                chat_id,
                "🌐 后台网页：Docker 本地 http://localhost:3000\nRailway/服务器部署后请打开你的前端域名。",
            )
            return

        if command == "/addalias":
            await self.handle_add_alias(chat_id, normalized)
            return

        if command in {"/match", "/比赛"}:
            await self.handle_match_detail(chat_id, normalized)
            return

        if command in {"/odds", "/赔率"}:
            await self.handle_odds(chat_id, normalized)
            return

        if command in {"/review", "/复盘"}:
            await self.handle_review(chat_id, normalized)
            return

        if command in {"/follow", "/关注"}:
            await self.handle_follow(chat_id, normalized)
            return

        if command in {"/unfollow", "/取消关注"}:
            await self.handle_unfollow(chat_id, normalized)
            return

        if command in {"/myfollows", "/我的关注"}:
            await self.handle_my_follows(chat_id)
            return

        if command in {"/value", "/高价值"}:
            await self.handle_high_value(chat_id)
            return

        if normalized.isdigit() and str(chat_id) in self.candidate_cache:
            await self.handle_candidate_choice(chat_id, int(normalized))
            return

        if command in {"/today", "/今日"} or normalized == "今日":
            await self.handle_today(chat_id)
            return

        if command in {"/popular", "/热门"} or normalized == "热门":
            await self.handle_popular(chat_id)
            return

        if command == "/analyze":
            normalized = (
                "/分析 " + normalized.split(maxsplit=1)[1].strip()
                if len(normalized.split(maxsplit=1)) > 1
                else "/分析"
            )

        if command in {"/分析", "/analyze"} or parse_match_text(normalized):
            display_text = normalized.replace("/分析", "").replace("/analyze", "").strip()
            self.send_message(chat_id, f"🔍 正在分析: {display_text}...")
            try:
                async with AsyncSessionLocal() as session:
                    result = await self.pipeline.resolve_text(session, normalized)
            except Exception as exc:
                logger.exception("analysis failed chat=%s text=%s", chat_id, normalized)
                self.send_message(chat_id, f"❌ 分析失败：{exc}")
                return
            if result.status == "candidates" and result.candidates:
                self.candidate_cache[str(chat_id)] = CandidateCache(
                    candidates=result.candidates,
                    expires_at=time.time() + 300,
                    query=parse_match_text(normalized),
                )
            self.send_message(chat_id, result.message)
            if result.fixture_id:
                self.send_message(
                    chat_id,
                    "可关注本场，赛前和完场后接收提醒。",
                    reply_markup=self.follow_markup(result.fixture_id),
                )
            return

        self.send_message(chat_id, "未识别的指令。发送 /帮助 查看用法。")

    @staticmethod
    def command_name(text: str) -> str:
        if not text.startswith("/"):
            return ""
        command = text.split(maxsplit=1)[0]
        command = command.split("@", 1)[0]
        return command.lower()

    @staticmethod
    def command_arg(text: str) -> str:
        parts = text.split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""

    async def handle_callback(self, callback: dict[str, Any]) -> None:
        query_id = callback.get("id")
        message = callback.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        user_id = str((callback.get("from") or {}).get("id") or "")
        data = callback.get("data") or ""
        if query_id:
            requests.post(
                f"{self.base_url}/answerCallbackQuery",
                json={"callback_query_id": query_id},
                timeout=10,
            )
        if not chat_id:
            return
        if data == "menu:today":
            await self.handle_today(chat_id)
        elif data == "menu:popular":
            await self.handle_popular(chat_id)
        elif data == "menu:stats":
            async with AsyncSessionLocal() as session:
                stats = await stats_summary(session)
            self.send_message(chat_id, self.format_stats(stats))
        elif data == "menu:status":
            self.send_message(chat_id, self.status_text())
        elif data == "menu:help":
            self.send_message(chat_id, self.help_text(), reply_markup=self.main_menu())
        elif data == "menu:input":
            self.send_message(chat_id, "请直接发送：主队 vs 客队，例如：美国 vs 波黑")
        elif data.startswith("follow:"):
            fixture_id = int(data.split(":", 1)[1])
            async with AsyncSessionLocal() as session:
                existing = (
                    await session.execute(
                        select(Subscription).where(
                            Subscription.user_id == user_id,
                            Subscription.fixture_id == fixture_id,
                        )
                    )
                ).scalar_one_or_none()
                if not existing:
                    session.add(
                        Subscription(user_id=user_id, chat_id=str(chat_id), fixture_id=fixture_id)
                    )
                    await session.commit()
            self.send_message(
                chat_id, f"✅ 已关注 fixture {fixture_id}，将提醒赛前6小时、赛前1小时和完场复盘。"
            )

    async def handle_candidate_choice(self, chat_id: int, choice: int) -> None:
        cache = self.candidate_cache.get(str(chat_id))
        if not cache or cache.expires_at <= time.time():
            self.send_message(chat_id, "候选列表已过期，请重新发送比赛名称。")
            return
        if choice < 1 or choice > len(cache.candidates[:5]):
            self.send_message(chat_id, "编号无效，请回复候选列表中的编号。")
            return
        candidate = cache.candidates[choice - 1]
        self.send_message(
            chat_id, f"🔍 正在分析: {candidate.home_team} vs {candidate.away_team}..."
        )
        try:
            async with AsyncSessionLocal() as session:
                result = await self.pipeline.analyze_fixture(
                    session,
                    candidate.fixture_id,
                    source_query=cache.query,
                )
        except Exception as exc:
            logger.exception(
                "candidate analysis failed chat=%s fixture_id=%s", chat_id, candidate.fixture_id
            )
            self.send_message(chat_id, f"❌ 分析失败：{exc}")
            return
        self.candidate_cache.pop(str(chat_id), None)
        self.send_message(chat_id, result.message)

    async def handle_add_alias(self, chat_id: int, text: str) -> None:
        parts = text.split(maxsplit=2)
        if len(parts) != 3:
            self.send_message(chat_id, "格式: /addalias 博塔弗戈SP Botafogo SP")
            return
        async with AsyncSessionLocal() as session:
            item = await add_alias(session, parts[1], parts[2])
        self.send_message(chat_id, f"✅ 已添加别名：{item.alias} -> {item.api_team_name}")

    async def handle_match_detail(self, chat_id: int, text: str) -> None:
        arg = self.command_arg(text)
        if not arg.isdigit():
            self.send_message(chat_id, "格式：/match 1567307 或 /比赛 1567307")
            return
        fixture_id = int(arg)
        async with AsyncSessionLocal() as session:
            match = (
                await session.execute(select(Match).where(Match.api_fixture_id == fixture_id))
            ).scalar_one_or_none()
            pred = (
                await session.execute(
                    select(Prediction)
                    .where(Prediction.fixture_id == fixture_id)
                    .order_by(desc(Prediction.created_at))
                    .limit(1)
                )
            ).scalar_one_or_none()
            result = (
                await session.execute(select(Result).where(Result.fixture_id == fixture_id))
            ).scalar_one_or_none()
        if not match:
            self.send_message(chat_id, f"未找到 fixture_id={fixture_id} 的比赛记录。")
            return
        score = (
            f"{result.home_goals}:{result.away_goals}"
            if result and result.home_goals is not None
            else "未完赛"
        )
        lines = [
            f"📊 {match.home_team_name} vs {match.away_team_name}",
            f"🏆 {match.league_name or '-'}",
            f"⏰ {match.match_date.isoformat()[:16].replace('T', ' ') if match.match_date else '-'}",
            f"状态：{match.status}",
            f"比分：{score}",
            "",
            f"最优方向：{pred.best_display_pick if pred and pred.best_display_pick else '暂无/观望'}",
            f"评分：{pred.value_score if pred else '-'} | 风险：{pred.risk if pred else '-'}",
        ]
        self.send_message(chat_id, "\n".join(lines), reply_markup=self.follow_markup(fixture_id))

    async def handle_odds(self, chat_id: int, text: str) -> None:
        arg = self.command_arg(text)
        if not arg.isdigit():
            self.send_message(chat_id, "格式：/odds 1567307 或 /赔率 1567307")
            return
        fixture_id = int(arg)
        async with AsyncSessionLocal() as session:
            rows = (
                (
                    await session.execute(
                        select(OddsSnapshot)
                        .where(OddsSnapshot.fixture_id == fixture_id)
                        .order_by(desc(OddsSnapshot.captured_at))
                        .limit(12)
                    )
                )
                .scalars()
                .all()
            )
        if not rows:
            self.send_message(chat_id, f"fixture {fixture_id} 暂无赔率快照。")
            return
        lines = [f"📈 赔率快照 fixture {fixture_id}", ""]
        for row in rows:
            if row.market == "1x2":
                value = f"{row.home_odds or '-'} / {row.draw_odds or '-'} / {row.away_odds or '-'}"
            elif row.market == "asian_handicap":
                line = f"{row.ah_line:g}" if row.ah_line is not None else "-"
                value = f"AH {line} | {row.ah_home_odds or '-'} / {row.ah_away_odds or '-'}"
            else:
                line = f"{row.ou_line:g}" if row.ou_line is not None else "-"
                value = f"OU {line} | {row.over_odds or '-'} / {row.under_odds or '-'}"
            lines.append(f"{row.snapshot_type} | {row.bookmaker} | {row.market}: {value}")
        self.send_message(chat_id, "\n".join(lines))

    async def handle_review(self, chat_id: int, text: str) -> None:
        arg = self.command_arg(text)
        if not arg.isdigit():
            self.send_message(chat_id, "格式：/review 1567307 或 /复盘 1567307")
            return
        fixture_id = int(arg)
        async with AsyncSessionLocal() as session:
            match = (
                await session.execute(select(Match).where(Match.api_fixture_id == fixture_id))
            ).scalar_one_or_none()
            pred = (
                await session.execute(
                    select(Prediction)
                    .where(Prediction.fixture_id == fixture_id)
                    .order_by(desc(Prediction.created_at))
                    .limit(1)
                )
            ).scalar_one_or_none()
        if not match or not pred:
            self.send_message(chat_id, f"fixture {fixture_id} 暂无可复盘预测。")
            return
        if pred.settled_status in {None, "pending"}:
            self.send_message(chat_id, f"fixture {fixture_id} 尚未完成复盘，等待赛果同步。")
            return
        score = f"{match.home_score}:{match.away_score}" if match.home_score is not None else "-"
        lines = [
            "✅ 已复盘",
            "",
            f"{match.home_team_name} {score} {match.away_team_name}",
            "",
            f"预测最优方向：{pred.best_display_pick or '-'}",
            f"结果：{pred.settlement_note or pred.settled_status}",
            f"EV：{pred.best_ev:+.1%}" if pred.best_ev is not None else "EV：-",
            f"价值评分：{pred.value_score or 0}%",
            "",
            "复盘结论：",
            "本场方向命中。"
            if pred.settled_status in {"win", "half_win"}
            else "本场方向未命中或走水。",
        ]
        self.send_message(chat_id, "\n".join(lines))

    async def handle_follow(self, chat_id: int, text: str) -> None:
        arg = self.command_arg(text)
        if not arg.isdigit():
            self.send_message(chat_id, "格式：/follow 1567307 或 /关注 1567307")
            return
        fixture_id = int(arg)
        async with AsyncSessionLocal() as session:
            existing = (
                await session.execute(
                    select(Subscription).where(
                        Subscription.user_id == str(chat_id), Subscription.fixture_id == fixture_id
                    )
                )
            ).scalar_one_or_none()
            if not existing:
                session.add(
                    Subscription(user_id=str(chat_id), chat_id=str(chat_id), fixture_id=fixture_id)
                )
                await session.commit()
        self.send_message(chat_id, f"✅ 已关注 fixture {fixture_id}")

    async def handle_unfollow(self, chat_id: int, text: str) -> None:
        arg = self.command_arg(text)
        if not arg.isdigit():
            self.send_message(chat_id, "格式：/unfollow 1567307 或 /取消关注 1567307")
            return
        fixture_id = int(arg)
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(Subscription).where(
                    Subscription.user_id == str(chat_id), Subscription.fixture_id == fixture_id
                )
            )
            await session.commit()
        self.send_message(chat_id, f"✅ 已取消关注 fixture {fixture_id}")

    async def handle_my_follows(self, chat_id: int) -> None:
        async with AsyncSessionLocal() as session:
            rows = (
                (
                    await session.execute(
                        select(Subscription)
                        .where(Subscription.user_id == str(chat_id))
                        .order_by(desc(Subscription.created_at))
                        .limit(10)
                    )
                )
                .scalars()
                .all()
            )
        if not rows:
            self.send_message(chat_id, "你还没有关注比赛。")
            return
        lines = ["⭐ 我的关注", ""]
        for row in rows:
            lines.append(f"- fixture {row.fixture_id}")
        self.send_message(chat_id, "\n".join(lines))

    async def handle_high_value(self, chat_id: int) -> None:
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(Prediction, Match)
                    .outerjoin(Match, Prediction.match_id == Match.id)
                    .where(
                        Prediction.value_score >= 80,
                        Prediction.risk != "高",
                        Prediction.best_ev > 0,
                    )
                    .order_by(desc(Prediction.created_at))
                    .limit(8)
                )
            ).all()
        if not rows:
            self.send_message(chat_id, "暂无高价值比赛。")
            return
        lines = ["🔥 高价值比赛", ""]
        for pred, match in rows:
            title = (
                f"{match.home_team_name} vs {match.away_team_name}"
                if match
                else f"fixture {pred.fixture_id}"
            )
            lines.append(
                f"{title}\n"
                f"方向：{pred.best_display_pick or '-'} | 评分 {pred.value_score or 0} | EV {pred.best_ev or 0:+.1%}\n"
                f"/match {pred.fixture_id}\n"
            )
        self.send_message(chat_id, "\n".join(lines).strip())

    async def handle_today(self, chat_id: int) -> None:
        api = ApiFootballClient()
        fixtures = api.upcoming_fixtures(days=1)
        if not fixtures:
            self.send_message(chat_id, "📭 今日暂无可展示赛事")
            return
        lines = ["📅 今日比赛", ""]
        for item in fixtures[:12]:
            fixture = item.get("fixture", {})
            teams = item.get("teams", {})
            league = item.get("league", {})
            kickoff = fixture.get("date", "")[:16].replace("T", " ")
            lines.append(
                f"{kickoff} | {league.get('name', '')}\n"
                f"{teams.get('home', {}).get('name', '')} vs {teams.get('away', {}).get('name', '')}\n"
                f"分析: /分析 {teams.get('home', {}).get('name', '')} vs {teams.get('away', {}).get('name', '')}\n"
            )
        self.send_message(chat_id, "\n".join(lines).strip())

    async def handle_popular(self, chat_id: int) -> None:
        api = ApiFootballClient()
        fixtures = api.upcoming_fixtures(days=3)
        if not fixtures:
            self.send_message(chat_id, "📭 最近暂无可展示赛事")
            return
        candidates = []
        for item in fixtures:
            league = item.get("league", {})
            fixture = item.get("fixture", {})
            score = 0
            if league.get("id") in {1, 2, 3, 39, 61, 78, 135, 140, 15}:
                score += 100
            if fixture.get("status", {}).get("short") in {"1H", "HT", "2H"}:
                score += 30
            candidates.append((score, item))
        lines = ["🔥 热门比赛", ""]
        for _, item in sorted(candidates, key=lambda row: row[0], reverse=True)[:10]:
            fixture = item.get("fixture", {})
            teams = item.get("teams", {})
            league = item.get("league", {})
            kickoff = fixture.get("date", "")[:16].replace("T", " ")
            lines.append(
                f"{kickoff} | {league.get('name', '')}\n"
                f"{teams.get('home', {}).get('name', '')} vs {teams.get('away', {}).get('name', '')}\n"
                f"分析: /分析 {teams.get('home', {}).get('name', '')} vs {teams.get('away', {}).get('name', '')}\n"
            )
        self.send_message(chat_id, "\n".join(lines).strip())

    @staticmethod
    def help_text() -> str:
        return (
            "🤖 FootballQuantBot\n\n"
            "/分析 Botafogo SP vs CRB - 单场分析\n"
            "/analyze Botafogo SP vs CRB - 单场分析\n"
            "Botafogo SP vs CRB - 也可直接发送\n"
            "/today 或 /今日 - 今日比赛\n"
            "/popular 或 /热门 - 热门比赛\n"
            "/value - 高价值比赛\n"
            "/match fixture_id - 比赛详情\n"
            "/odds fixture_id - 赔率快照\n"
            "/review fixture_id - 赛后复盘\n"
            "/follow fixture_id - 关注比赛\n"
            "/myfollows - 我的关注\n"
            "/stats - 统计摘要\n"
            "/status - 系统状态\n"
            "/web - 后台网页地址\n"
            "/addalias 别名 API球队名 - 添加球队别名\n"
        )

    @staticmethod
    def main_menu() -> dict[str, Any]:
        return {
            "inline_keyboard": [
                [
                    {"text": "今日比赛", "callback_data": "menu:today"},
                    {"text": "热门赛事", "callback_data": "menu:popular"},
                ],
                [
                    {"text": "输入比赛", "callback_data": "menu:input"},
                    {"text": "命中统计", "callback_data": "menu:stats"},
                ],
                [
                    {"text": "系统状态", "callback_data": "menu:status"},
                    {"text": "帮助", "callback_data": "menu:help"},
                ],
            ]
        }

    @staticmethod
    def follow_markup(fixture_id: int) -> dict[str, Any]:
        return {
            "inline_keyboard": [[{"text": "关注比赛", "callback_data": f"follow:{fixture_id}"}]]
        }

    @staticmethod
    def status_text() -> str:
        api_status = "已配置" if settings.API_FOOTBALL_PRIMARY_KEY else "未配置"
        return f"✅ Bot 在线\nAPI-Football: {api_status}\n模式: polling only"

    @staticmethod
    def format_stats(stats: dict[str, Any]) -> str:
        lines = [
            "📊 统计摘要",
            f"总分析: {stats['total_predictions']}",
            f"有价值方向: {stats['value_predictions']}",
            f"已复盘: {stats.get('settled_predictions', 0)}",
            f"价值方向占比: {stats['recent_value_rate']:.1%}",
        ]
        if stats.get("recent"):
            lines.append("")
            lines.append("最近记录:")
            for item in stats["recent"][:5]:
                lines.append(
                    f"- fixture {item['fixture_id']} | {item.get('best_pick') or '观望'} | {item.get('value_score') or 0}"
                )
        return "\n".join(lines)

    @staticmethod
    def format_performance(perf: dict[str, Any]) -> str:
        lines = [
            "🎯 命中统计",
            f"总复盘: {perf.get('settled_count', 0)}",
            f"总命中率: {perf.get('overall_hit_rate', 0):.1%}",
            f"平均收益: {perf.get('avg_profit', 0):+.2f}",
        ]
        by_market = perf.get("by_market") or []
        if by_market:
            lines.extend(["", "按市场:"])
            for item in by_market[:6]:
                lines.append(
                    f"- {item.get('market') or '-'} | {item.get('count', 0)}场 | "
                    f"命中 {item.get('hit_rate', 0):.1%} | 收益 {item.get('avg_profit', 0):+.2f}"
                )
        recommendations = perf.get("recommendations") or []
        if recommendations:
            lines.extend(["", "系统建议:"])
            for item in recommendations[:5]:
                lines.append(f"- {item}")
        return "\n".join(lines)

    def run(self) -> None:
        logger.info("Telegram polling worker started")
        self.clear_webhook()
        # Drop stale updates only once on startup.
        try:
            updates = (
                requests.get(f"{self.base_url}/getUpdates", params={"offset": -1}, timeout=10)
                .json()
                .get("result", [])
            )
            if updates:
                self.offset = updates[-1]["update_id"] + 1
        except requests.RequestException:
            self.offset = 0

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            while True:
                try:
                    for update in self.get_updates():
                        loop.run_until_complete(self.handle_update(update))
                except HTTPError as exc:
                    status_code = exc.response.status_code if exc.response is not None else None
                    if status_code == 409:
                        logger.error(
                            "Telegram polling conflict: another getUpdates/webhook consumer is active. Retrying in 30s."
                        )
                        time.sleep(30)
                        continue
                    logger.exception("polling HTTP error: %s", exc)
                    time.sleep(10)
                except KeyboardInterrupt:
                    logger.info("Telegram polling worker stopped")
                    return
                except Exception as exc:
                    logger.exception("polling loop error: %s", exc)
                    time.sleep(5)
        finally:
            loop.close()


def main() -> None:
    TelegramBotWorker().run()


if __name__ == "__main__":
    main()
