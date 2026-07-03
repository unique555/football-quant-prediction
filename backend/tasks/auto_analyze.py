"""
自动批量分析任务 — 扫描今日+明日比赛 → 11 维度分析 → 入库

这是全自动闭环的核心：系统自动发现已入库的比赛，逐场执行完整的 11 维度分析，
生成报告并入库，供 value_screener 筛选推送。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from celery.utils.log import get_task_logger
from core.database import AsyncSessionLocal
from models.match import Match
from models.prediction import Prediction
from models.telegram_mvp import OddsSnapshot, Result, ValueCandidate
from services.prediction_service import PredictionService
from services.telegram_mvp.api_football import ApiFootballClient
from services.telegram_mvp.odds import (
    aggregate_1x2,
    aggregate_two_way,
    parse_api_football_odds,
)
from services.analyzers import (
    fundamental_analyzer,
    tactical_analyzer,
    motivation_analyzer,
    goals_analyzer,
    corners_analyzer,
    htft_analyzer,
    data_quality,
)
from services.notify import send_error_alert
from services.report_formatter import format_reports
from sqlalchemy import desc, select

from tasks.celery_app import celery_app

logger = get_task_logger(__name__)

MODEL_VERSION = "engine-auto-analyze-v1"
ANALYZE_HOURS_AHEAD = 48  # 分析未来 48 小时内的比赛
MAX_ANALYZE_PER_RUN = 80  # 单次最多分析 80 场，全量联赛覆盖
MIN_BOOKMAKERS = 3  # 赔率少于此数跳过（自然过滤无赔率的小联赛）


@celery_app.task(name="tasks.auto_analyze.run")
def run_auto_analyze() -> dict:
    """定时自动分析任务 — 每 3 小时运行"""
    return asyncio.run(_run())


async def _run() -> dict:
    stats = {"total": 0, "analyzed": 0, "skipped": 0, "failed": 0}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now + timedelta(hours=ANALYZE_HOURS_AHEAD)

    async with AsyncSessionLocal() as session:
        # 查询待分析的比赛
        matches = (
            (
                await session.execute(
                    select(Match)
                    .where(
                        Match.match_date >= now,
                        Match.match_date <= cutoff,
                        Match.status == "scheduled",
                        Match.api_fixture_id.is_not(None),
                    )
                    .order_by(Match.match_date)
                    .limit(MAX_ANALYZE_PER_RUN)
                )
            )
            .scalars()
            .all()
        )

        stats["total"] = len(matches)
        service = PredictionService()

        for match in matches:
            try:
                # 检查是否已有近期分析（3 小时内）
                existing = (
                    (
                        await session.execute(
                            select(Prediction)
                            .where(Prediction.fixture_id == match.api_fixture_id)
                            .order_by(desc(Prediction.created_at))
                            .limit(1)
                        )
                    )
                    .scalar_one_or_none()
                )
                if existing and existing.created_at:
                    age = now - existing.created_at.replace(tzinfo=None)
                    if age.total_seconds() < 3 * 3600:  # 3 小时内已分析
                        stats["skipped"] += 1
                        continue

                await _analyze_single(session, service, match)
                stats["analyzed"] += 1
            except Exception as e:
                logger.warning("analyze failed fixture=%s: %s", match.api_fixture_id, e)
                stats["failed"] += 1

        await session.commit()

    if stats.get("failed", 0) > 0:
        send_error_alert("分析失败", f"{stats['failed']} 场比赛分析失败，原因见日志", "auto_analyze")

    logger.info("auto_analyze result: %s", stats)
    return stats


async def _analyze_single(session, service: PredictionService, match: Match) -> None:
    """对单场比赛执行完整 11 维度分析"""
    fixture_id = match.api_fixture_id
    api = service.api

    # 获取 fixture 详情
    fixture = api.fixture_by_id(fixture_id)
    if not fixture:
        raise ValueError(f"fixture {fixture_id} not found")

    # 拉取赔率
    parsed_odds = parse_api_football_odds(api.odds_by_fixture(fixture_id))
    if not parsed_odds:
        # 无赔率数据，跳过（无法分析）
        raise ValueError(f"no odds for fixture {fixture_id}")

    # 赔率庄家数不足，跳过（自然过滤无赔率的小联赛）
    one_x_two_count = sum(
        1 for o in parsed_odds
        if o.market == "1x2" and o.home and o.draw and o.away
    )
    if one_x_two_count < MIN_BOOKMAKERS:
        raise ValueError(
            f"insufficient bookmakers ({one_x_two_count}<{MIN_BOOKMAKERS}) for fixture {fixture_id}"
        )

    aggregates = {
        "1x2": aggregate_1x2(parsed_odds),
        "asian_handicap": aggregate_two_way(parsed_odds, "asian_handicap"),
        "over_under": aggregate_two_way(parsed_odds, "over_under"),
    }

    # 1. 基本面分析
    fundamental = fundamental_analyzer.analyze(api, fixture)

    # 2. 战术分析
    tactical = tactical_analyzer.analyze(api, fixture, fundamental)

    # 3. 战意与剧本
    motivation = motivation_analyzer.analyze(api, fixture, fundamental)

    # 4. 盘口分析（从 aggregates 提取）
    odds_data = _extract_odds_data(aggregates, parsed_odds)

    # 5. 进球市场
    goals = goals_analyzer.analyze(api, fixture, fundamental, aggregates)

    # 6. 角球分析
    corners = corners_analyzer.analyze(api, fixture, fundamental, aggregates)

    # 7. 半全场
    htft = htft_analyzer.analyze(api, fixture, fundamental, aggregates)

    # 8. 胜平负判定（通过引擎 pipeline + ML 修正）
    verdict = await _run_engine_analysis(
        session, service, match, fixture, aggregates, parsed_odds,
        fundamental=fundamental,
    )

    # 9. 风险提示
    risks = _extract_risks(verdict, motivation, fundamental)

    # 10. 数据质量
    dq = data_quality.assess(fixture, fundamental, aggregates, motivation)

    # 组装报告
    match_data = {
        "home_team": match.home_team_name,
        "away_team": match.away_team_name,
        "league_name": match.league_name,
        "round_name": fixture.get("league", {}).get("round", ""),
        "kickoff_str": match.match_date.strftime("%Y-%m-%d %H:%M") if match.match_date else "",
        "venue": match.venue or fixture.get("fixture", {}).get("venue", {}).get("name", ""),
    }

    reports = format_reports(
        match_data=match_data,
        classification=verdict.get("classification", {}),
        fundamental=fundamental,
        tactical=tactical,
        motivation=motivation,
        odds_data=odds_data,
        goals=goals,
        corners=corners,
        htft=htft,
        verdict=verdict,
        risks=risks,
        data_quality_data=dq,
    )

    # 入库
    _persist(
        session, match, fixture_id, verdict, reports,
        parsed_odds, aggregates,
    )


async def _run_engine_analysis(
    session, service, match, fixture, aggregates, parsed_odds,
    fundamental=None,
) -> dict[str, Any]:
    """调用引擎 pipeline 获取胜平负判定（接入 ML 修正）"""
    from services.prediction_service import (
        _bookmaker_snapshots,
        _estimate_model_probs,
        _selected_candidate_fields,
    )
    from engine.orchestrator.pipeline import run_full_pipeline

    one_x_two = aggregates.get("1x2")

    # ── ML 概率（Phase 2）──
    ml_probs = None
    try:
        from services.ml.predictor import get_predictor
        predictor = get_predictor()
        if predictor.is_ready() and fundamental:
            ml_probs = predictor.predict(fixture, fundamental, aggregates)
    except Exception as e:
        logger.warning("ML predict failed, falling back to API predictions: %s", e)

    # ── 市场隐含概率（基准）──
    prediction_response = api_get_predictions(service.api, match.api_fixture_id)
    api_probs = _estimate_model_probs(
        one_x_two, prediction_response[0] if prediction_response else None
    )

    # ── 市场为主 + ML 修正 ──
    if ml_probs:
        from services.ml.predictor import get_predictor
        predictor = get_predictor()
        market_probs_dict = {
            "home": one_x_two.no_vig_probs.get("home", api_probs.home) if one_x_two else api_probs.home,
            "draw": one_x_two.no_vig_probs.get("draw", api_probs.draw) if one_x_two else api_probs.draw,
            "away": one_x_two.no_vig_probs.get("away", api_probs.away) if one_x_two else api_probs.away,
        }
        corrected = predictor.apply_correction(market_probs_dict, ml_probs)
        model_home_prob = corrected["home"]
        model_draw_prob = corrected["draw"]
        model_away_prob = corrected["away"]
        ml_source = "ML修正(市场+Stacking)"
    else:
        # 无 ML 模型，用 API predictions + 市场隐含概率
        model_home_prob = api_probs.home
        model_draw_prob = api_probs.draw
        model_away_prob = api_probs.away
        ml_source = "市场隐含概率(API-Football)"

    # 构建 bookmaker snapshots
    snapshots = _bookmaker_snapshots(parsed_odds)

    # 获取最佳赔率
    best_home = best_draw = best_away = None
    if one_x_two:
        best_home = one_x_two.best_odds.get("home", (None, ""))[0]
        best_draw = one_x_two.best_odds.get("draw", (None, ""))[0]
        best_away = one_x_two.best_odds.get("away", (None, ""))[0]

    initial_odds = None
    if one_x_two:
        initial_odds = (
            float(one_x_two.avg_odds["home"]),
            float(one_x_two.avg_odds["draw"]),
            float(one_x_two.avg_odds["away"]),
        )

    ah = aggregates.get("asian_handicap")
    asian_handicap = float(ah.avg_odds["line"]) if ah and "line" in ah.avg_odds else None

    # TSI：从排名差推断（Phase 2 改进，不再硬编码 50）
    tsi_home, tsi_away = _estimate_tsi(fundamental)

    report = run_full_pipeline(
        home_team=match.home_team_name or "",
        away_team=match.away_team_name or "",
        league=match.league_name or "",
        tsi_home=tsi_home,
        tsi_away=tsi_away,
        asian_handicap=asian_handicap,
        initial_odds=initial_odds,
        match_date=match.match_date,
        bookmaker_snapshots=snapshots,
        model_home_prob=model_home_prob,
        model_draw_prob=model_draw_prob,
        model_away_prob=model_away_prob,
        best_home_odds=best_home,
        best_draw_odds=best_draw,
        best_away_odds=best_away,
    )

    selected = _selected_candidate_fields(report, one_x_two)

    return {
        "classification": {
            "match_type": report.classification.match_type.value if report.classification else "unknown",
            "phase": report.classification.match_phase.value if report.classification else "unknown",
            "favorite": report.classification.favorite_side if report.classification else "none",
            "is_derby": False,
            "reason": report.classification.reason if report.classification else "",
        },
        "final_probs": {
            "home": report.final_home_prob,
            "draw": report.final_draw_prob,
            "away": report.final_away_prob,
        },
        "market_probs": _market_probs(one_x_two),
        "recommendation": _pick_label(report, match.home_team_name, match.away_team_name),
        "best_edge": selected.get("edge"),
        "best_ev": selected.get("ev"),
        "best_odds": selected.get("odds"),
        "best_bookmaker": selected.get("bookmaker"),
        "kelly": selected.get("kelly"),
        "kelly_label": _kelly_label(selected.get("kelly", 0)),
        "risk": _risk_label(report),
        "signal_score": round(report.confidence_score * 100),
        "signals": _extract_signals(report),
        "engine_report": report,
        "selected_fields": selected,
    }


def _estimate_tsi(fundamental: dict[str, Any] | None) -> tuple[float, float]:
    """
    从基本面数据推断 TSI（Team Strength Index）。
    不再硬编码 50，用排名+积分+近况推断 0-100 的实力分。
    """
    if not fundamental:
        return 50.0, 50.0

    standings = fundamental.get("standings", {})
    form = fundamental.get("form", {})

    def _calc_tsi(side: str) -> float:
        s = standings.get(side, {})
        f = form.get(side, {})
        rank = s.get("rank", 10)
        points = s.get("points", 0)
        played = s.get("played", 1)
        form_score = f.get("form_score", 0.5)

        # 排名分：第1名=100，第20名=30
        rank_score = max(30, 100 - (rank - 1) * 3.5)
        # 积分率
        points_rate = points / (played * 3) if played > 0 else 0.5
        points_score = points_rate * 100
        # 状态分
        form_pts = form_score * 100

        # 加权平均
        return round(rank_score * 0.5 + points_score * 0.3 + form_pts * 0.2, 1)

    return _calc_tsi("home"), _calc_tsi("away")


def _extract_odds_data(aggregates: dict, parsed_odds: list) -> dict[str, Any]:
    """从 aggregates 提取盘口数据"""
    one_x_two = aggregates.get("1x2")
    ah = aggregates.get("asian_handicap")

    odds_data: dict[str, Any] = {
        "bookmakers": [],
        "asian_handicap": {},
    }

    if one_x_two:
        odds_data["bookmakers"] = [
            {"name": bm.bookmaker, "home": bm.home, "draw": bm.draw, "away": bm.away}
            for bm in one_x_two.raw_bookmakers[:6]
        ]
        odds_data["consensus"] = one_x_two.consensus_score
        odds_data["avg_odds"] = one_x_two.avg_odds

    if ah:
        odds_data["asian_handicap"] = {
            "handicap": ah.avg_odds.get("line"),
            "home_water": ah.avg_odds.get("home"),
            "away_water": ah.avg_odds.get("away"),
            "trend": "—",  # Phase 2: 从时间序列计算
            "initial": "—",
        }

    return odds_data


def _extract_risks(verdict: dict, motivation: dict, fundamental: dict) -> list[str]:
    """提取风险提示"""
    risks = []
    report = verdict.get("engine_report")

    if report and hasattr(report, "warnings") and report.warnings:
        risks.extend(report.warnings[:4])

    # 从 motivation 提取伤病/停赛
    for factor in (motivation or {}).get("script_factors", []):
        impact = factor.get("impact", "")
        weight = factor.get("weight", "")
        if "⚠️" in weight or "高" in weight:
            risks.append(f"{factor.get('factor', '')}: {impact}")

    return risks[:6]


def _market_probs(one_x_two) -> dict[str, float]:
    if not one_x_two:
        return {}
    return {
        "home": one_x_two.no_vig_probs.get("home", 0),
        "draw": one_x_two.no_vig_probs.get("draw", 0),
        "away": one_x_two.no_vig_probs.get("away", 0),
    }


def _pick_label(report, home_name: str, away_name: str) -> str | None:
    direction = report.recommended_direction
    if not direction:
        return None
    return {"home": home_name, "draw": "平局", "away": away_name}.get(direction)


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


def _risk_label(report) -> str:
    if not hasattr(report, "final_verdict"):
        return "中"
    v = report.final_verdict.value
    if v in {"high_confidence", "moderate"} and not report.warnings:
        return "低"
    if v == "skip" or len(report.warnings) >= 2:
        return "高"
    return "中"


def _extract_signals(report) -> list[str]:
    """从引擎报告提取信号列表"""
    signals = []
    if report.consensus:
        signals.append(f"✅ 机构共识: {report.consensus.consensus_level.value}")
    if report.asian and report.asian.direction_signal:
        signals.append(f"✅ 亚盘指向: {report.asian.direction_signal}")
    if report.validation and report.validation.verdict.value != "neutral":
        signals.append(f"✅ 指数验证: {report.validation.verdict.value}")
    if report.pricing and report.pricing.best_value_side:
        signals.append(f"✅ 市场定价: {report.pricing.best_value_side}")
    if report.warnings:
        signals.append(f"⚠️ {report.warnings[0]}")
    return signals[:5]


def _persist(session, match, fixture_id, verdict, reports, parsed_odds, aggregates):
    """入库 Prediction + ValueCandidate + OddsSnapshot"""
    selected = verdict.get("selected_fields", {})
    report = verdict.get("engine_report")

    # 持久化赔率快照
    for row in parsed_odds:
        session.add(
            OddsSnapshot(
                fixture_id=fixture_id,
                snapshot_type="latest",
                market=row.market,
                bookmaker=row.bookmaker,
                home_odds=row.home if row.market == "1x2" else None,
                draw_odds=row.draw if row.market == "1x2" else None,
                away_odds=row.away if row.market == "1x2" else None,
                ah_line=row.line if row.market == "asian_handicap" else None,
                ah_home_odds=row.home if row.market == "asian_handicap" else None,
                ah_away_odds=row.away if row.market == "asian_handicap" else None,
                ou_line=row.line if row.market == "over_under" else None,
                over_odds=row.over if row.market == "over_under" else None,
                under_odds=row.under if row.market == "over_under" else None,
                raw_json=row.raw,
            )
        )

    # 持久化 Prediction
    probs = verdict.get("final_probs", {})
    session.add(
        Prediction(
            match_id=match.id,
            fixture_id=fixture_id,
            model_version=MODEL_VERSION,
            model_name="engine-orchestrator-auto",
            home_win_prob=probs.get("home", 0),
            draw_prob=probs.get("draw", 0),
            away_win_prob=probs.get("away", 0),
            confidence=report.confidence_score if report else 0,
            best_market=selected.get("market"),
            best_pick=selected.get("pick"),
            best_display_pick=selected.get("display_pick"),
            best_bookmaker=selected.get("bookmaker"),
            best_odds=selected.get("odds"),
            best_ev=selected.get("ev"),
            best_kelly=selected.get("kelly"),
            best_edge=selected.get("edge"),
            market_prob=selected.get("market_prob"),
            value_score=round((report.confidence_score if report else 0) * 100),
            confidence_text=_confidence_text(report.confidence_score if report else 0),
            risk=verdict.get("risk", "中"),
            settled_status="pending",
            report_text=reports["full_report"],
            raw_json=reports["raw_json"],
        )
    )

    # 持久化 ValueCandidate（如果有价值方向）
    if selected and selected.get("ev") and selected["ev"] > 0:
        one_x_two = aggregates.get("1x2")
        session.add(
            ValueCandidate(
                fixture_id=fixture_id,
                market=selected.get("market", "1x2"),
                pick=selected.get("pick", ""),
                display_pick=selected.get("display_pick", ""),
                best_bookmaker=selected.get("bookmaker"),
                prob=probs.get(selected.get("pick", "home"), 0),
                odds=selected.get("odds"),
                market_prob=selected.get("market_prob"),
                edge=selected.get("edge"),
                ev=selected.get("ev"),
                kelly=selected.get("kelly"),
                risk=verdict.get("risk", "中"),
                bookmaker_count=one_x_two.bookmaker_count if one_x_two else 0,
                consensus_score=round(
                    (report.consensus.direction_strength if report and report.consensus else 0) * 100
                ),
                value_score=round((report.confidence_score if report else 0) * 100),
                selected=True,
                reason=report.summary if report else "",
                settled_status="pending",
            )
        )


def _confidence_text(score: float) -> str:
    if score >= 0.10:
        return "高"
    if score >= 0.05:
        return "中"
    return "低"


def api_get_predictions(api: ApiFootballClient, fixture_id: int) -> list[dict]:
    """获取 API-Football 内置预测（作为 Phase 1 的模型概率来源）"""
    data = api.get("/predictions", {"fixture": fixture_id})
    return data.get("response", [])
