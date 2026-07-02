"""Frontend presentation helpers for match workbench responses."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from models.prediction import Prediction
from models.telegram_mvp import OddsSnapshot, ValueCandidate


def _round(value: float | None, digits: int = 4) -> float | None:
    return round(float(value), digits) if value is not None else None


def _pct_label(value: float | None) -> str:
    return f"{value * 100:.1f}%" if value is not None else "-"


def _num_label(value: float | None, digits: int = 2) -> str:
    return f"{value:.{digits}f}" if value is not None else "-"


def _best_candidate(candidates: list[ValueCandidate], market: str) -> ValueCandidate | None:
    market_rows = [item for item in candidates if item.market == market]
    if not market_rows:
        return None
    selected = [item for item in market_rows if item.selected]
    return max(selected or market_rows, key=lambda item: item.ev or item.edge or 0)


def _latest_snapshots(snapshots: list[OddsSnapshot], market: str) -> list[OddsSnapshot]:
    rows = [item for item in snapshots if item.market == market]
    if not rows:
        return []
    latest_by_bookmaker: dict[str, OddsSnapshot] = {}
    for row in rows:
        key = row.bookmaker or f"bookmaker-{row.id}"
        current = latest_by_bookmaker.get(key)
        if not current or (row.captured_at and current.captured_at and row.captured_at > current.captured_at):
            latest_by_bookmaker[key] = row
    return list(latest_by_bookmaker.values())


def _no_vig_two(a_odds: float | None, b_odds: float | None) -> tuple[float | None, float | None]:
    if not a_odds or not b_odds or a_odds <= 1 or b_odds <= 1:
        return None, None
    a_raw = 1 / a_odds
    b_raw = 1 / b_odds
    total = a_raw + b_raw
    return a_raw / total, b_raw / total


def _avg(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return mean(clean) if clean else None


def _best(values: list[tuple[float | None, str | None]]) -> tuple[float | None, str | None]:
    clean = [(float(value), bookmaker) for value, bookmaker in values if value is not None]
    if not clean:
        return None, None
    return max(clean, key=lambda item: item[0])


def _metric(label: str, value: str) -> dict[str, str]:
    return {"label": label, "value": value}


def _outcome(label: str, probability: float | None, tone: str = "neutral") -> dict[str, Any]:
    return {"label": label, "probability": _round(probability), "tone": tone}


def _one_x_two_card(
    prediction: Prediction | None,
    snapshots: list[OddsSnapshot],
    candidate: ValueCandidate | None,
) -> dict[str, Any]:
    rows = _latest_snapshots(snapshots, "1x2")
    best_home, home_bookmaker = _best([(row.home_odds, row.bookmaker) for row in rows])
    best_draw, _ = _best([(row.draw_odds, row.bookmaker) for row in rows])
    best_away, _ = _best([(row.away_odds, row.bookmaker) for row in rows])
    return {
        "market": "1x2",
        "title": "胜平负概率",
        "subtitle": "市场 + 模型修正",
        "status": "ready" if prediction else "empty",
        "outcomes": [
            _outcome("主胜", prediction.home_win_prob if prediction else None, "positive"),
            _outcome("平局", prediction.draw_prob if prediction else None, "warning"),
            _outcome("客胜", prediction.away_win_prob if prediction else None, "neutral"),
        ],
        "metrics": [
            _metric("最佳主胜", _num_label(best_home)),
            _metric("最佳公司", home_bookmaker or "-"),
            _metric("Edge", _pct_label(candidate.edge if candidate else None)),
            _metric("EV", _pct_label(candidate.ev if candidate else None)),
        ],
        "action": "推送" if candidate and candidate.selected else "观察",
        "raw": {"best_draw": best_draw, "best_away": best_away},
    }


def _asian_card(snapshots: list[OddsSnapshot], candidate: ValueCandidate | None) -> dict[str, Any]:
    rows = _latest_snapshots(snapshots, "asian_handicap")
    line = candidate.line if candidate and candidate.line is not None else _avg([row.ah_line for row in rows])
    home_prob = candidate.prob if candidate and candidate.pick == "home" else None
    away_prob = candidate.prob if candidate and candidate.pick == "away" else None
    if home_prob is None or away_prob is None:
        home_avg = _avg([row.ah_home_odds for row in rows])
        away_avg = _avg([row.ah_away_odds for row in rows])
        implied_home, implied_away = _no_vig_two(home_avg, away_avg)
        home_prob = home_prob if home_prob is not None else implied_home
        away_prob = away_prob if away_prob is not None else implied_away
    best_home, bookmaker = _best([(row.ah_home_odds, row.bookmaker) for row in rows])
    return {
        "market": "asian_handicap",
        "title": "亚盘概率",
        "subtitle": f"主队 {line:+g}" if line is not None else "盘口待采集",
        "status": "ready" if rows or candidate else "empty",
        "outcomes": [
            _outcome(f"主 {line:+g}" if line is not None else "主队", home_prob, "positive"),
            _outcome(f"客 {-line:+g}" if line is not None else "客队", away_prob, "neutral"),
            _outcome("走水保护", 0.31 if line in {0, 0.25, -0.25} else None, "warning"),
        ],
        "metrics": [
            _metric("最佳水位", _num_label(best_home or (candidate.odds if candidate else None))),
            _metric("最佳公司", bookmaker or (candidate.best_bookmaker if candidate else "-") or "-"),
            _metric("Edge", _pct_label(candidate.edge if candidate else None)),
            _metric("Kelly", _pct_label(candidate.kelly if candidate else None)),
        ],
        "action": "观察" if candidate else "待采集",
    }


def _over_under_card(snapshots: list[OddsSnapshot], candidate: ValueCandidate | None) -> dict[str, Any]:
    rows = _latest_snapshots(snapshots, "over_under")
    line = candidate.line if candidate and candidate.line is not None else _avg([row.ou_line for row in rows])
    over_prob = candidate.prob if candidate and candidate.pick == "over" else None
    under_prob = candidate.prob if candidate and candidate.pick == "under" else None
    if over_prob is None or under_prob is None:
        over_avg = _avg([row.over_odds for row in rows])
        under_avg = _avg([row.under_odds for row in rows])
        implied_over, implied_under = _no_vig_two(over_avg, under_avg)
        over_prob = over_prob if over_prob is not None else implied_over
        under_prob = under_prob if under_prob is not None else implied_under
    best_over, bookmaker = _best([(row.over_odds, row.bookmaker) for row in rows])
    tempo = "偏快" if (over_prob or 0) >= 0.53 else "偏慢" if (under_prob or 0) >= 0.53 else "均衡"
    return {
        "market": "over_under",
        "title": "大小球概率",
        "subtitle": f"{line:g} 球" if line is not None else "盘口待采集",
        "status": "ready" if rows or candidate else "empty",
        "outcomes": [
            _outcome(f"大 {line:g}" if line is not None else "大球", over_prob, "positive"),
            _outcome(f"小 {line:g}" if line is not None else "小球", under_prob, "neutral"),
            _outcome("节奏倾向", max(over_prob or 0, under_prob or 0) or None, "warning"),
        ],
        "metrics": [
            _metric("最佳赔率", _num_label(best_over or (candidate.odds if candidate else None))),
            _metric("最佳公司", bookmaker or (candidate.best_bookmaker if candidate else "-") or "-"),
            _metric("Edge", _pct_label(candidate.edge if candidate else None)),
            _metric("结论", tempo),
        ],
        "action": "观察" if candidate else "待采集",
    }


def _corners_card(candidates: list[ValueCandidate]) -> dict[str, Any]:
    candidate = _best_candidate(candidates, "corners")
    return {
        "market": "corners",
        "title": "角球概率",
        "subtitle": f"{candidate.line:g} 角" if candidate and candidate.line is not None else "角球数据待接入",
        "status": "ready" if candidate else "empty",
        "outcomes": [
            _outcome("大角", candidate.prob if candidate and candidate.pick == "over" else None, "positive"),
            _outcome("小角", candidate.prob if candidate and candidate.pick == "under" else None, "neutral"),
            _outcome("边路强度", None, "warning"),
        ],
        "metrics": [
            _metric("最佳赔率", _num_label(candidate.odds if candidate else None)),
            _metric("Edge", _pct_label(candidate.edge if candidate else None)),
            _metric("置信", candidate.risk if candidate else "待采集"),
            _metric("动作", "人工复核"),
        ],
        "action": "人工复核" if candidate else "待采集",
    }


def build_market_cards(
    prediction: Prediction | None,
    candidates: list[ValueCandidate],
    snapshots: list[OddsSnapshot],
) -> list[dict[str, Any]]:
    return [
        _one_x_two_card(prediction, snapshots, _best_candidate(candidates, "1x2")),
        _asian_card(snapshots, _best_candidate(candidates, "asian_handicap")),
        _over_under_card(snapshots, _best_candidate(candidates, "over_under")),
        _corners_card(candidates),
    ]


def build_report_template(
    home_team_zh: str,
    away_team_zh: str,
    home_team: str,
    away_team: str,
    league: str | None,
    fixture_id: int,
    prediction: Prediction | None,
    market_cards: list[dict[str, Any]],
) -> dict[str, Any]:
    selected_card = market_cards[0] if market_cards else None
    best_pick = prediction.best_display_pick if prediction else None
    summary_lines = [
        f"{home_team_zh} vs {away_team_zh}",
        f"{home_team} vs {away_team}",
        f"{league or '-'} · fixture #{fixture_id}",
    ]
    if prediction:
        summary_lines.extend(
            [
                f"首选方向：{best_pick or '观望'}",
                f"价值分：{prediction.value_score or 0} / 风险：{prediction.risk or '-'}",
                f"EV：{_pct_label(prediction.best_ev)} / Edge：{_pct_label(prediction.best_edge)} / Kelly：{_pct_label(prediction.best_kelly)}",
            ]
        )
    else:
        summary_lines.append("当前暂无预测记录，请先运行分析。")

    return {
        "title": f"{home_team_zh} vs {away_team_zh} 分析报告",
        "sections": [
            {
                "title": "比赛信息",
                "items": summary_lines[:3],
            },
            {
                "title": "核心建议",
                "items": summary_lines[3:] if len(summary_lines) > 3 else ["暂无核心建议。"],
            },
            {
                "title": "四大市场拆解",
                "items": [
                    f"{card['title']}：{card['action']} · {card['subtitle']}" for card in market_cards
                ],
            },
            {
                "title": "风控与操作",
                "items": [
                    "胜平负首选方向可进入 Telegram 推送。",
                    "亚盘、大小球、角球默认展示给用户，数据不足或风险偏高时进入人工复核。",
                    "赛后由结果同步任务更新命中、收益和复盘结论。",
                ],
            },
        ],
        "raw_report": prediction.report_text if prediction else "",
        "primary_market": selected_card["market"] if selected_card else None,
    }


def group_candidates_by_market(candidates: list[ValueCandidate]) -> dict[str, list[ValueCandidate]]:
    grouped: dict[str, list[ValueCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.market].append(candidate)
    return dict(grouped)
