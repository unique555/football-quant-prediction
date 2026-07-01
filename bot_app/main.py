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
from requests import HTTPError
from services.telegram_mvp.api_football import ApiFootballClient
from services.telegram_mvp.fixtures import FixtureCandidate
from services.telegram_mvp.names import parse_match_text
from services.telegram_mvp.pipeline import TelegramAnalysisPipeline, add_alias, stats_summary

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("football_quant.bot")


@dataclass
class CandidateCache:
    candidates: list[FixtureCandidate]
    expires_at: float


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

    def send_message(self, chat_id: int | str, text: str) -> None:
        chunks = [text[i : i + 3800] for i in range(0, len(text), 3800)] or [text]
        for chunk in chunks:
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
                timeout=20,
            )
            if not resp.ok:
                logger.warning("Telegram send failed: %s %s", resp.status_code, resp.text[:300])

    def get_updates(self) -> list[dict[str, Any]]:
        resp = requests.get(
            f"{self.base_url}/getUpdates",
            params={"offset": self.offset, "timeout": 30, "allowed_updates": ["message"]},
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

        if normalized.startswith("/start") or normalized in {"/帮助", "帮助", "/help"}:
            self.send_message(chat_id, self.help_text())
            return

        if normalized.startswith("/status"):
            self.send_message(chat_id, self.status_text())
            return

        if normalized.startswith("/stats"):
            async with AsyncSessionLocal() as session:
                stats = await stats_summary(session)
            self.send_message(chat_id, self.format_stats(stats))
            return

        if normalized.startswith("/addalias"):
            await self.handle_add_alias(chat_id, normalized)
            return

        if normalized.isdigit() and str(chat_id) in self.candidate_cache:
            await self.handle_candidate_choice(chat_id, int(normalized))
            return

        if normalized.startswith("/今日") or normalized == "今日":
            await self.handle_today(chat_id)
            return

        if normalized.startswith("/热门") or normalized == "热门":
            await self.handle_popular(chat_id)
            return

        if normalized.startswith("/分析") or parse_match_text(normalized):
            self.send_message(chat_id, f"🔍 正在分析: {normalized.replace('/分析', '').strip()}...")
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
                )
            self.send_message(chat_id, result.message)
            return

        self.send_message(chat_id, "未识别的指令。发送 /帮助 查看用法。")

    async def handle_candidate_choice(self, chat_id: int, choice: int) -> None:
        cache = self.candidate_cache.get(str(chat_id))
        if not cache or cache.expires_at <= time.time():
            self.send_message(chat_id, "候选列表已过期，请重新发送比赛名称。")
            return
        if choice < 1 or choice > len(cache.candidates[:5]):
            self.send_message(chat_id, "编号无效，请回复候选列表中的编号。")
            return
        candidate = cache.candidates[choice - 1]
        self.send_message(chat_id, f"🔍 正在分析: {candidate.home_team} vs {candidate.away_team}...")
        try:
            async with AsyncSessionLocal() as session:
                result = await self.pipeline.analyze_fixture(session, candidate.fixture_id)
        except Exception as exc:
            logger.exception("candidate analysis failed chat=%s fixture_id=%s", chat_id, candidate.fixture_id)
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
            "Botafogo SP vs CRB - 也可直接发送\n"
            "/今日 - 今日比赛\n"
            "/热门 - 热门比赛\n"
            "/stats - 统计摘要\n"
            "/status - 系统状态\n"
            "/addalias 别名 API球队名 - 添加球队别名\n"
        )

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

    def run(self) -> None:
        logger.info("Telegram polling worker started")
        self.clear_webhook()
        # Drop stale updates only once on startup.
        try:
            updates = requests.get(f"{self.base_url}/getUpdates", params={"offset": -1}, timeout=10).json().get("result", [])
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
