"""
五步分析引擎 — 比赛画像 → 机构共识 → 技术验证 → 定价检验 → 综合判断
"""

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests

from model.national_trainer import get_national_model
from model.trainer import get_model

# ══════════════════════════════════════════════════════════════
# 第一步: 比赛画像 — 基本面 + 盘赔组合分类
# ══════════════════════════════════════════════════════════════


class MatchProfiler:
    """比赛画像: 根据基本面 + 赔率结构给比赛分类"""

    STRONG_FAV = "强队碾压"  # 赔率 <1.5
    CLEAR_FAV = "明显倾向"  # 1.5-1.8
    MODERATE = "均势偏主"  # 1.8-2.3
    BALANCE = "完全均势"  # 2.3-3.0
    UPSET_RISK = "冷门风险"  # 3.0+

    @staticmethod
    def profile(match: dict, model_pred: dict, odds: Optional[dict]) -> dict:
        """返回比赛画像"""
        home, away = match["home_team"], match["away_team"]

        # 基本面: 球队评分差距
        club_model = get_model()
        nat_model = get_national_model()

        # 选择评分源
        is_national = match.get("competition") in ("WC", "EC")
        ratings = nat_model.ratings if is_national else club_model.ratings
        hr = ratings.get(home, {})
        ar = ratings.get(away, {})

        rating_gap = 0
        if hr and ar:
            rating_gap = (hr.get("off", 1) - hr.get("def", 1)) - (
                ar.get("off", 1) - ar.get("def", 1)
            )

        # 赔率结构分析
        odds_type = MatchProfiler.BALANCE
        fav_side = None

        if odds:
            if odds["home"] < 1.5:
                odds_type = MatchProfiler.STRONG_FAV
                fav_side = "主队"
            elif odds["home"] < 1.8:
                odds_type = MatchProfiler.CLEAR_FAV
                fav_side = "主队"
            elif odds["home"] < 2.3:
                odds_type = MatchProfiler.MODERATE
                fav_side = "主队" if odds["home"] < odds["away"] else "客队"
            elif odds["away"] < 2.3:
                odds_type = MatchProfiler.MODERATE
                fav_side = "客队"
            elif odds["away"] < 1.8:
                odds_type = MatchProfiler.CLEAR_FAV
                fav_side = "客队"
            elif odds["away"] < 1.5:
                odds_type = MatchProfiler.STRONG_FAV
                fav_side = "客队"
            elif max(odds["home"], odds["away"]) > 3.5:
                odds_type = MatchProfiler.UPSET_RISK

        # xG 分析
        xg_home = model_pred.get("home_xg", 0)
        xg_away = model_pred.get("away_xg", 0)
        xg_total = xg_home + xg_away

        goal_type = (
            "小球 (<2.5)" if xg_total < 2.3 else ("大球 (>2.5)" if xg_total > 2.8 else "中等进球")
        )

        # 赛事权重
        stage = match.get("stage", "")
        tournament_weight = (
            1.5
            if "FINAL" in stage
            else (1.3 if "SEMI" in stage else (1.1 if "QUARTER" in stage else 1.0))
        )

        return {
            "match_type": odds_type,
            "favored_side": fav_side,
            "rating_gap": round(rating_gap, 2),
            "xg_total": round(xg_total, 2),
            "goal_profile": goal_type,
            "tournament_weight": tournament_weight,
            "volatility": "高"
            if odds_type in (MatchProfiler.BALANCE, MatchProfiler.UPSET_RISK)
            else ("中" if odds_type == MatchProfiler.MODERATE else "低"),
            "confidence_zone": "可重注"
            if odds_type == MatchProfiler.STRONG_FAV
            else (
                "稳健"
                if odds_type == MatchProfiler.CLEAR_FAV
                else ("谨慎" if odds_type == MatchProfiler.MODERATE else "高风险")
            ),
        }


# ══════════════════════════════════════════════════════════════
# 第二步: 机构共识 — 多家机构方向统一度
# ══════════════════════════════════════════════════════════════


class ConsensusAnalyzer:
    """机构共识分析: 拉取多家庄家赔率, 分析方向统一度"""

    # OddsPapi 支持的庄家
    BOOKMAKERS = {
        "pinnacle": "Pinnacle",
        "bet365": "Bet365",
        "williamhill": "William Hill",
        "betfair": "Betfair",
        "onexbet": "1xBet",
    }

    @staticmethod
    def analyze(match: dict, odds_api_key: str) -> dict:
        """拉多家赔率, 分析共识度"""
        market_odds = match.get("market_odds")
        if not odds_api_key and market_odds:
            raw = 1 / market_odds["home"] + 1 / market_odds["draw"] + 1 / market_odds["away"]
            implied = {
                "home": (1 / market_odds["home"]) / raw,
                "draw": (1 / market_odds["draw"]) / raw,
                "away": (1 / market_odds["away"]) / raw,
            }
            direction = max(implied, key=implied.get)
            breakdown = {"home": 0, "draw": 0, "away": 0}
            breakdown[direction] = 1
            return {
                "bookmakers_count": 1,
                "consensus_score": 0.5,
                "consensus_direction": direction,
                "consensus_level": "单源赔率",
                "breakdown": breakdown,
                "pinnacle_odds": None,
                "avg_odds": {
                    "home": market_odds["home"],
                    "draw": market_odds["draw"],
                    "away": market_odds["away"],
                },
            }

        tid = {16: 16, 17: 17, 8: 8, 7: 7}.get(match.get("tournament_id")) or 16  # 默认世界杯

        bookmakers_odds = {}
        consensus_count = {"home": 0, "draw": 0, "away": 0}
        total_bm = 0

        for bm_code in ["pinnacle", "bet365", "williamhill", "betfair", "onexbet"]:
            try:
                url = f"https://api.oddspapi.io/v4/odds-by-tournaments?bookmaker={bm_code}&tournamentIds={tid}&apiKey={odds_api_key}"
                r = requests.get(url, timeout=10)
                if r.status_code != 200:
                    continue

                # 找这场比赛
                for item in r.json():
                    bm = item.get("bookmakerOdds", {}).get(bm_code, {})
                    mkt = bm.get("markets", {}).get("101", {}).get("outcomes", {})
                    try:
                        h = float(mkt["101"]["players"]["0"]["price"])
                        d = float(mkt["102"]["players"]["0"]["price"])
                        a = float(mkt["103"]["players"]["0"]["price"])
                        bookmakers_odds[bm_code] = {"home": h, "draw": d, "away": a}
                        raw = 1 / h + 1 / d + 1 / a
                        p_h = (1 / h) / raw
                        p_d = (1 / d) / raw
                        p_a = (1 / a) / raw
                        best = max(
                            [("home", p_h), ("draw", p_d), ("away", p_a)], key=lambda x: x[1]
                        )
                        consensus_count[best[0]] += 1
                        total_bm += 1
                    except Exception:
                        pass
                time.sleep(0.3)
            except Exception:
                pass

        # 共识度评分
        if total_bm >= 3:
            top = max(consensus_count.values())
            consensus_score = top / total_bm  # 0-1
            direction = max(consensus_count, key=consensus_count.get)
        else:
            consensus_score = 0
            direction = "unknown"

        level = (
            "高度一致"
            if consensus_score >= 0.8
            else (
                "多数一致"
                if consensus_score >= 0.6
                else ("分歧较大" if consensus_score >= 0.4 else "严重分歧")
            )
        )

        return {
            "bookmakers_count": total_bm,
            "consensus_score": round(consensus_score, 2),
            "consensus_direction": direction,
            "consensus_level": level,
            "breakdown": consensus_count,
            "pinnacle_odds": bookmakers_odds.get("pinnacle"),
            "avg_odds": ConsensusAnalyzer._avg_odds(bookmakers_odds),
        }

    @staticmethod
    def _avg_odds(odds_dict: dict) -> Optional[dict]:
        if not odds_dict:
            return None
        n = len(odds_dict)
        return {
            "home": round(sum(o["home"] for o in odds_dict.values()) / n, 2),
            "draw": round(sum(o["draw"] for o in odds_dict.values()) / n, 2),
            "away": round(sum(o["away"] for o in odds_dict.values()) / n, 2),
        }


# ══════════════════════════════════════════════════════════════
# 第三步: 技术验证 — CLV + 赔率走势 + 成交量指标
# ══════════════════════════════════════════════════════════════


class TechnicalValidator:
    """技术面验证: CLV偏差 + 赔率变动方向 + 凯利值"""

    @staticmethod
    def validate(
        model_pred: dict, market_odds: Optional[dict], consensus: dict, profile: dict
    ) -> dict:
        checks = []
        score = 0  # 通过的检查数

        # 1) CLV 检验 — 模型公平赔率 vs 市场赔率
        if market_odds:
            fair_h = round(1 / model_pred["p_home"], 2) if model_pred["p_home"] > 0 else 99
            fair_d = round(1 / model_pred["p_draw"], 2) if model_pred["p_draw"] > 0 else 99
            fair_a = round(1 / model_pred["p_away"], 2) if model_pred["p_away"] > 0 else 99

            clv_signals = []
            for side, fair, mk in [
                ("主", fair_h, market_odds["home"]),
                ("平", fair_d, market_odds["draw"]),
                ("客", fair_a, market_odds["away"]),
            ]:
                clv = (fair - mk) / mk * 100
                if clv > 5:
                    clv_signals.append(f"{side}胜被低估 {clv:.1f}%")
                    if side == "主" and model_pred["prediction"] == "主胜":
                        score += 1
                    if side == "客" and model_pred["prediction"] == "客胜":
                        score += 1
                elif clv < -15:
                    clv_signals.append(f"{side}胜被高估 {abs(clv):.1f}%")

            checks.append(
                {"name": "CLV检验", "signals": clv_signals, "passed": len(clv_signals) > 0}
            )

        # 2) 机构共识检验
        consensus_ok = consensus.get("consensus_score", 0) >= 0.5
        if consensus_ok:
            score += 1
            pred_dir = model_pred["prediction"]
            cons_dir = consensus.get("consensus_direction", "")
            dir_map = {"主胜": "home", "平局": "draw", "客胜": "away"}
            aligned = dir_map.get(pred_dir) == cons_dir
            checks.append(
                {
                    "name": "机构共识",
                    "passed": True,
                    "aligned": aligned,
                    "detail": f"共识度 {consensus.get('consensus_score', 0):.0%}",
                }
            )
        else:
            checks.append({"name": "机构共识", "passed": False, "detail": "机构分歧大"})

        # 3) 赔率结构验证
        if market_odds:
            raw = 1 / market_odds["home"] + 1 / market_odds["draw"] + 1 / market_odds["away"]
            payout = 1 / raw
            structure_ok = 0.92 <= payout <= 0.99
            if structure_ok:
                score += 1
            checks.append(
                {"name": "赔率结构", "passed": structure_ok, "detail": f"返还率 {payout:.1%}"}
            )

        # 4) 波动性检查
        vol_ok = profile.get("volatility") == "低" or (
            profile.get("volatility") == "中" and model_pred["confidence"] > 0.4
        )
        if vol_ok:
            score += 1
        checks.append(
            {"name": "波动性", "passed": vol_ok, "detail": profile.get("volatility", "?")}
        )

        return {
            "checks": checks,
            "score": score,
            "max_score": len(checks),
            "verdict": "通过"
            if score >= len(checks) * 0.6
            else ("部分通过" if score >= len(checks) * 0.3 else "不通过"),
        }


# ══════════════════════════════════════════════════════════════
# 第四步: 市场定价检验 — 凯利值 + 期望值
# ══════════════════════════════════════════════════════════════


class MarketPricingTester:
    """市场定价检验: 凯利值 / 期望值 / 赔率异常检测"""

    @staticmethod
    def test(model_pred: dict, market_odds: Optional[dict], profile: dict) -> dict:
        if not market_odds:
            return {"status": "无赔率数据", "kelly": None, "ev": None}

        raw = 1 / market_odds["home"] + 1 / market_odds["draw"] + 1 / market_odds["away"]

        # 凯利值计算 (半凯利 = 保守)
        results = {}
        for side, mk_odds, p_key, outcome in [
            ("home", market_odds["home"], "p_home", "主胜"),
            ("draw", market_odds["draw"], "p_draw", "平局"),
            ("away", market_odds["away"], "p_away", "客胜"),
        ]:
            p = model_pred[p_key]
            b = mk_odds - 1  # 净赔率
            kelly_full = (p * b - (1 - p)) / b if b > 0 else -1
            kelly_half = kelly_full * 0.5  # 半凯利
            ev = p * mk_odds - 1  # 期望值

            results[outcome] = {
                "kelly_full": round(kelly_full, 4),
                "kelly_half": round(kelly_half, 4),
                "ev": round(ev, 4),
                "recommend": "重注"
                if kelly_half > 0.05
                else ("轻注" if kelly_half > 0.02 else ("观望" if kelly_half > -0.02 else "回避")),
            }

        # 赔率异常: 检查是否有明显的赔率异常偏离
        mp_h = (1 / market_odds["home"]) / raw
        anomalies = []
        if mp_h > 0.7 and model_pred["p_home"] < 0.45:
            anomalies.append("市场过度看好主队")
        elif mp_h < 0.25 and model_pred["p_home"] > 0.4:
            anomalies.append("市场过度低估主队")

        return {
            "kelly_analysis": results,
            "pinnacle_payout": round(1 / raw, 4),
            "pinnacle_margin": round(1 - 1 / raw, 4),
            "anomalies": anomalies,
            "best_value": max(results.items(), key=lambda x: x[1]["kelly_half"])
            if results
            else None,
        }


# ══════════════════════════════════════════════════════════════
# 第五步: 综合判断
# ══════════════════════════════════════════════════════════════


@dataclass
class FinalVerdict:
    direction: str  # 主胜/平局/客胜
    confidence: str  # 高/中/低
    risk_level: str  # 低/中/高
    suggested_action: str  # 推荐操作
    score_breakdown: dict  # 各步评分
    key_reasons: list  # 核心理由
    warnings: list  # 风险提示


class MatchAnalyzer:
    """完整五步分析主控"""

    def __init__(self, odds_api_key: str):
        self.odds_key = odds_api_key
        self.club_model = get_model()
        self.nat_model = get_national_model()

    def analyze(self, match: dict) -> FinalVerdict:
        """执行完整五步分析"""
        home, away = match["home_team"], match["away_team"]
        is_national = match.get("competition") in ("WC", "EC")
        model = self.nat_model if is_national else self.club_model

        # 模型预测
        if is_national:
            pred = model.predict(home, away, neutral=True)
        else:
            pred = model.predict(home, away)

        scores = {}

        # ── 第①步: 比赛画像 ──
        market_odds = match.get("market_odds")
        profile = MatchProfiler.profile(match, pred, market_odds)
        scores["profile"] = 1.0  # 总是通过

        # ── 第②步: 机构共识 ──
        consensus = ConsensusAnalyzer.analyze(match, self.odds_key)
        scores["consensus"] = consensus.get("consensus_score", 0)

        # ── 第③步: 技术验证 ──
        tech = TechnicalValidator.validate(pred, market_odds, consensus, profile)
        scores["technical"] = tech["score"] / tech["max_score"] if tech["max_score"] > 0 else 0

        # ── 第④步: 定价检验 ──
        pricing = MarketPricingTester.test(pred, market_odds, profile)
        best_kelly = 0
        if pricing.get("best_value"):
            best_kelly = pricing["best_value"][1].get("kelly_half", 0)
        scores["pricing"] = min(1.0, max(0, best_kelly * 5 + 0.5))

        # ── 第⑤步: 综合裁决 ──
        total_score = sum(scores.values())
        max_possible = len(scores)
        score_pct = total_score / max_possible if max_possible > 0 else 0

        # 检查 CLV 与 consensus 是否矛盾
        clv_contradiction = False
        if tech.get("checks"):
            for c in tech["checks"]:
                if c["name"] == "CLV检验" and c.get("signals"):
                    for sig in c["signals"]:
                        if "被高估" in sig:
                            overvalued_side = sig[0]  # "主"/"平"/"客"
                            side_map = {"主": "主胜", "平": "平局", "客": "客胜"}
                            if side_map.get(overvalued_side) == pred["prediction"]:
                                clv_contradiction = True  # CLV 说高估, 模型却预测这个方向

        # 确定方向
        if clv_contradiction:
            if pred["confidence"] < 0.35:
                direction = "方向不明(CLV矛盾)"
                confidence = "低"
            elif score_pct >= 0.65:
                direction = pred["prediction"] + "(CLV警示)"
                confidence = "中"
            else:
                direction = "方向不明(CLV矛盾)"
                confidence = "低"
        elif pred["confidence"] < 0.35:
            direction = "方向不明"
            confidence = "低"
        else:
            direction = pred["prediction"]
            if score_pct >= 0.7 and model.has_team(home) and model.has_team(away):
                confidence = "高"
            elif score_pct >= 0.5:
                confidence = "中"
            else:
                confidence = "低"

        # 风险
        risk = profile.get("volatility", "中")

        # 操作建议
        if confidence == "高":
            action = f"可重点关注{direction}"
        elif confidence == "中":
            action = f"谨慎参考{direction}"
        else:
            action = "建议观望, 不确定性过高"

        # 理由
        reasons = []
        if profile.get("match_type") == MatchProfiler.BALANCE:
            reasons.append("比赛高度均势, 任何结果都可能")
        if consensus.get("consensus_score", 0) >= 0.7:
            reasons.append(f"机构共识度{consensus['consensus_score']:.0%}")
        if pricing.get("anomalies"):
            reasons.extend(pricing["anomalies"])
        if profile.get("rating_gap", 0) > 0.3:
            reasons.append(f"{home}实力评分领先")

        # 风险提示
        warnings = []
        if confidence == "低":
            warnings.append("模型信心不足, 不推荐重注")
        if profile.get("volatility") == "高":
            warnings.append("比赛波动性高, 注意风险控制")
        if not consensus.get("consensus_score", 0):
            warnings.append("机构数据不足, 共识度无法计算")

        return {
            "direction": direction,
            "confidence": confidence,
            "risk_level": risk,
            "suggested_action": action,
            "score_breakdown": scores,
            "total_score": round(score_pct, 2),
            "key_reasons": reasons,
            "warnings": warnings,
            "details": {
                "profile": profile,
                "consensus": consensus,
                "technical": tech,
                "pricing": pricing,
                "prediction": pred,
            },
        }


# ══════════════════════════════════════════════════════════════
# 快速入口
# ══════════════════════════════════════════════════════════════


def analyze_match(match: dict, odds_api_key: str) -> dict:
    analyzer = MatchAnalyzer(odds_api_key)
    return analyzer.analyze(match)


def generate_full_report(match: dict, result: dict) -> str:
    """生成完整的五步分析 MD 报告"""
    home = match["home_team"]
    away = match["away_team"]
    d = result["details"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# 📊 {home} vs {away} — 五步综合分析",
        "",
        f"> 生成: {now} | 赛事: {match.get('competition_name', '?')} | {match.get('stage', '')}",
        "",
        "## 🎯 最终裁决",
        "",
        "| 维度 | 结论 |",
        "|------|------|",
        f"| **方向** | **{result['direction']}** |",
        f"| **置信度** | {result['confidence']} |",
        f"| **风险等级** | {result['risk_level']} |",
        f"| **操作建议** | {result['suggested_action']} |",
        f"| **综合评分** | {result['total_score']:.0%} |",
        "",
    ]

    # 核心理由
    if result.get("key_reasons"):
        lines.append("### 核心理由")
        for r in result["key_reasons"]:
            lines.append(f"- {r}")
        lines.append("")

    # 风险
    if result.get("warnings"):
        lines.append("### ⚠️ 风险提示")
        for w in result["warnings"]:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("---")
    lines.append("")

    # 五步详情
    profile = d.get("profile", {})
    consensus = d.get("consensus", {})
    tech = d.get("technical", {})
    pricing = d.get("pricing", {})

    # ①
    lines.append("## ① 比赛画像")
    lines.append(f"- 类型: **{profile.get('match_type', '?')}**")
    lines.append(f"- 倾向方: {profile.get('favored_side', '?')}")
    lines.append(
        f"- 进球预期: {profile.get('goal_profile', '?')} (xG {profile.get('xg_total', '?')})"
    )
    lines.append(f"- 波动性: {profile.get('volatility', '?')}")
    lines.append(f"- 投注区: {profile.get('confidence_zone', '?')}")
    lines.append("")

    # ②
    lines.append("## ② 机构共识")
    lines.append(f"- 采集机构: {consensus.get('bookmakers_count', 0)} 家")
    lines.append(
        f"- 共识度: **{consensus.get('consensus_level', '?')}** ({consensus.get('consensus_score', 0):.0%})"
    )
    bd = consensus.get("breakdown", {})
    if bd:
        lines.append(
            f"- 方向分布: 主{bd.get('home', 0)} / 平{bd.get('draw', 0)} / 客{bd.get('away', 0)}"
        )
    if consensus.get("avg_odds"):
        ao = consensus["avg_odds"]
        lines.append(f"- 均赔: {ao['home']}/{ao['draw']}/{ao['away']}")
    lines.append("")

    # ③
    lines.append("## ③ 技术验证")
    lines.append(
        f"- 综合判定: {tech.get('verdict', '?')} ({tech.get('score', 0)}/{tech.get('max_score', 0)}项)"
    )
    for check in tech.get("checks", []):
        icon = "✅" if check.get("passed") else "❌"
        detail = check.get("detail", "")
        lines.append(f"  {icon} {check['name']}: {detail}")
        if check.get("signals"):
            for s in check["signals"]:
                lines.append(f"    → {s}")
    lines.append("")

    # ④
    lines.append("## ④ 市场定价检验")
    lines.append(f"- Pinnacle 返还率: {pricing.get('pinnacle_payout', 0):.1%}")
    lines.append(f"- Pinnacle 抽水: {pricing.get('pinnacle_margin', 0):.1%}")
    if pricing.get("best_value"):
        bv = pricing["best_value"]
        lines.append(f"- 最优价值: **{bv[0]}** (Kelly/2 = {bv[1].get('kelly_half', 0):.3f})")
    ka = pricing.get("kelly_analysis", {})
    if ka:
        lines.append("")
        lines.append("| 方向 | 凯利全 | 凯利半 | 期望值 | 建议 |")
        lines.append("|------|--------|--------|--------|------|")
        for outcome, v in ka.items():
            lines.append(
                f"| {outcome} | {v['kelly_full']:.3f} | {v['kelly_half']:.3f} | {v['ev']:+.3f} | {v['recommend']} |"
            )

    if pricing.get("anomalies"):
        lines.append("")
        for a in pricing["anomalies"]:
            lines.append(f"⚠️ {a}")

    lines.append("")

    # ⑤
    lines.append("## ⑤ 评分汇总")
    lines.append("")
    lines.append("| 步骤 | 评分 |")
    lines.append("|------|------|")
    step_names = {
        "profile": "①比赛画像",
        "consensus": "②机构共识",
        "technical": "③技术验证",
        "pricing": "④定价检验",
    }
    for key, label in step_names.items():
        s = result.get("score_breakdown", {}).get(key, 0)
        bar = "█" * int(s * 15)
        lines.append(f"| {label} | {bar} {s:.0%} |")
    lines.append(f"| **综合** | **{result['total_score']:.0%}** |")

    lines.append("")
    lines.append("---")
    lines.append("> 🤖 五步分析引擎 | 仅供参考, 不构成投注建议")

    return "\n".join(lines)
