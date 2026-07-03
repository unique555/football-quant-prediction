"""
回测路由 — 发起回测、查看状态、获取报告
"""
from __future__ import annotations
import asyncio
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter
import requests
import numpy as np

router = APIRouter()
_backtest_tasks: dict[str, dict] = {}

def _calc_brier(probs, actual):
    p = [probs.get("home",0), probs.get("draw",0), probs.get("away",0)]
    t = [0,0,0]
    t[actual] = 1
    return sum((p[i]-t[i])**2 for i in range(3))

@router.post("/backtest/run")
async def run_backtest(payload: dict):
    task_id = str(uuid.uuid4())[:8]
    _backtest_tasks[task_id] = {"status": "running", "progress": 0, "total": 0}
    asyncio.create_task(_run_backtest_async(task_id, payload))
    return {"status": "running", "task_id": task_id, "message": "回测任务已启动"}

@router.get("/backtest/{task_id}/status")
async def backtest_status(task_id: str):
    task = _backtest_tasks.get(task_id)
    if not task:
        return {"status": "not_found"}
    return {"status": task["status"], "progress": task.get("progress",0), "total": task.get("total",0)}

@router.get("/backtest/{task_id}/report")
async def backtest_report(task_id: str):
    task = _backtest_tasks.get(task_id)
    if not task:
        return {"status": "not_found"}
    if task["status"] != "completed":
        return {"status": task["status"], "message": "回测尚未完成"}
    return task.get("result", {})

async def _run_backtest_async(task_id: str, payload: dict):
    try:
        from services.telegram_mvp.api_football import ApiFootballClient
        from services.telegram_mvp.odds import parse_api_football_odds, aggregate_1x2
        from services.feature_builder import FeatureBuilder
        from services.ml.predictor import get_predictor
        
        api = ApiFootballClient()
        league_id = payload.get("league_id", 39)
        season_start = payload.get("season_start", 2024)
        season_end = payload.get("season_end", 2024)
        
        all_fixtures = []
        for season in range(season_start, season_end + 1):
            data = api.get("/fixtures", {"league": league_id, "season": season, "status": "FT"})
            all_fixtures.extend(data.get("response", []))
        
        _backtest_tasks[task_id]["total"] = len(all_fixtures)
        predictor = get_predictor()
        results = {"total": 0, "correct": 0, "brier_sum": 0.0, "profit": 0.0, "max_drawdown": 0.0, "peak": 0.0, "by_result": {"home": {"total": 0, "correct": 0}, "draw": {"total": 0, "correct": 0}, "away": {"total": 0, "correct": 0}}}
        
        for i, fixture in enumerate(all_fixtures):
            goals = fixture.get("goals", {})
            hg, ag = goals.get("home"), goals.get("away")
            if hg is None or ag is None:
                continue
            actual = 0 if hg > ag else (1 if hg == ag else 2)
            
            odds_data = api.odds_by_fixture(fixture.get("fixture", {}).get("id"))
            parsed = parse_api_football_odds(odds_data)
            agg_1x2 = aggregate_1x2(parsed) if parsed else None
            
            fb = FeatureBuilder(api=api)
            fundamental = {"standings": {}, "form": {}, "h2h_summary": {}, "home_record": {}, "away_record": {}}
            features = fb.build(fixture, fundamental, {"1x2": agg_1x2, "asian_handicap": None, "over_under": None})
            
            # 用市场概率或ML概率
            if agg_1x2:
                probs = {"home": agg_1x2.no_vig_probs.get("home",0.33), "draw": agg_1x2.no_vig_probs.get("draw",0.33), "away": agg_1x2.no_vig_probs.get("away",0.34)}
                if predictor.is_ready():
                    ml = predictor.predict(fixture, fundamental, {"1x2": agg_1x2})
                    if ml:
                        probs = predictor.apply_correction(probs, ml)
            else:
                probs = {"home": 0.4, "draw": 0.3, "away": 0.3}
            
            pred = max(probs, key=probs.get)
            pred_idx = {"home": 0, "draw": 1, "away": 2}[pred]
            correct = pred_idx == actual
            if correct:
                results["correct"] += 1
            results["brier_sum"] += _calc_brier(probs, actual)
            results["total"] += 1
            
            label = {0: "home", 1: "draw", 2: "away"}[actual]
            results["by_result"][label]["total"] += 1
            if correct:
                results["by_result"][label]["correct"] += 1
            
            # 模拟 Kelly 下注收益
            if agg_1x2:
                best_odds = agg_1x2.best_odds.get(pred, (0, ""))[0]
                if best_odds and best_odds > 1:
                    kelly = (probs[pred] * best_odds - 1) / (best_odds - 1)
                    kelly = max(0, min(kelly * 0.25, 0.1))
                    if correct:
                        results["profit"] += kelly * (best_odds - 1)
                    else:
                        results["profit"] -= kelly
                    results["peak"] = max(results["peak"], results["profit"])
                    results["max_drawdown"] = max(results["max_drawdown"], results["peak"] - results["profit"])
            
            if i % 10 == 0:
                _backtest_tasks[task_id]["progress"] = i
        
        t = results["total"]
        accuracy = results["correct"] / t if t else 0
        brier = results["brier_sum"] / t if t else 0
        roi = results["profit"] / (t * 0.1) if t else 0
        
        _backtest_tasks[task_id].update({
            "status": "completed",
            "progress": t,
            "result": {
                "accuracy": round(accuracy, 4),
                "brier_score": round(brier, 4),
                "roi": round(roi, 4),
                "total_matches": t,
                "correct": results["correct"],
                "profit_units": round(results["profit"], 4),
                "max_drawdown": round(results["max_drawdown"], 4),
                "by_result": results["by_result"],
                "report": _format_backtest_report(league_id, results, accuracy, brier, roi),
            }
        })
    except Exception as e:
        _backtest_tasks[task_id] = {"status": "failed", "error": str(e)}

def _format_backtest_report(league_id, results, accuracy, brier, roi):
    lines = [f"# 回测报告\n", f"联赛ID: {league_id}", f"总场次: {results['total']}", f"命中率: {accuracy:.2%}", f"Brier Score: {brier:.4f}", f"ROI: {roi:.2%}", f"收益: {results['profit']:+.2f}u", f"最大回撤: {results['max_drawdown']:.2%}", ""]
    lines.append("## 分层分析")
    for label in ["home", "draw", "away"]:
        d = results["by_result"][label]
        rate = d["correct"] / d["total"] if d["total"] else 0
        lines.append(f"- {label}: {d['correct']}/{d['total']} ({rate:.1%})")
    return "\n".join(lines)
