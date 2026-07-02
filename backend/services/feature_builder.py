"""
特征工程 — 从 API-Football 数据构建特征向量

目标：为 ML Stacking 模型提供统一的特征输入
特征维度：~120 维（实用版，不是 358 维过度设计）

特征分组：
  - basic (20维)：排名、积分、胜平负、进球失球、净胜球
  - form (24维)：近5/10场状态、进球均、失球均、零封率、状态分
  - home_away (20维)：主客场拆分战绩
  - h2h (12维)：交锋历史
  - odds (24维)：赔率隐含概率、凯利指数、离散度、赔率差
  - tactical (20维)：控球率、射门、射正、传球、犯规、角球

用法：
  features = FeatureBuilder(api).build(fixture, fundamental_data, odds_aggregates)
  → 返回 dict: {feature_name: value, ...} + target (如果有结果)
"""

from __future__ import annotations

import logging
from typing import Any

from services.telegram_mvp.api_football import ApiFootballClient

logger = logging.getLogger(__name__)


class FeatureBuilder:
    """特征构建器"""

    def __init__(self, api: ApiFootballClient | None = None):
        self.api = api

    def build(
        self,
        fixture: dict[str, Any],
        fundamental: dict[str, Any],
        odds_aggregates: dict[str, Any],
    ) -> dict[str, float]:
        """
        构建单场比赛的特征向量。

        Args:
            fixture: API-Football fixture 原始数据
            fundamental: fundamental_analyzer.analyze() 返回值
            odds_aggregates: {"1x2": MarketAggregate|None, ...}

        Returns:
            dict of feature_name → float (所有值已转为 float，缺失=0.0)
        """
        features: dict[str, float] = {}

        teams = fixture.get("teams", {})
        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")

        # 1. 基本面特征
        features.update(self._basic_features(fundamental))

        # 2. 近期状态特征
        features.update(self._form_features(fundamental))

        # 3. 主客场拆分
        features.update(self._home_away_features(fundamental))

        # 4. 交锋历史
        features.update(self._h2h_features(fundamental))

        # 5. 赔率特征
        features.update(self._odds_features(odds_aggregates))

        # 6. 战术特征
        features.update(self._tactical_features(fundamental))

        return features

    def build_target(self, fixture: dict[str, Any]) -> int | None:
        """
        从已结束的比赛提取标签（0=主胜, 1=平, 2=客胜）。
        未结束的比赛返回 None。
        """
        goals = fixture.get("goals", {})
        hg = goals.get("home")
        ag = goals.get("away")
        if hg is None or ag is None:
            return None
        if hg > ag:
            return 0
        elif hg == ag:
            return 1
        else:
            return 2

    # ==================================================================
    # 特征分组
    # ==================================================================

    def _basic_features(self, fundamental: dict[str, Any]) -> dict[str, float]:
        """基本面：排名、积分、胜负、进球"""
        features: dict[str, float] = {}
        standings = fundamental.get("standings", {})

        for side in ["home", "away"]:
            s = standings.get(side, {})
            prefix = f"{side}_"
            features[f"{prefix}rank"] = float(s.get("rank", 20))
            features[f"{prefix}points"] = float(s.get("points", 0))
            features[f"{prefix}played"] = float(s.get("played", 0))
            features[f"{prefix}win"] = float(s.get("win", 0))
            features[f"{prefix}draw"] = float(s.get("draw", 0))
            features[f"{prefix}lose"] = float(s.get("lose", 0))
            features[f"{prefix}goals_for"] = float(s.get("goals_for", 0))
            features[f"{prefix}goals_against"] = float(s.get("goals_against", 0))
            features[f"{prefix}goal_diff"] = float(s.get("goal_diff", 0))
            features[f"{prefix}win_rate"] = (
                float(s["win"]) / float(s["played"]) if s.get("played") and s.get("win") else 0.0
            )

        # 差值特征
        h = standings.get("home", {})
        a = standings.get("away", {})
        features["rank_diff"] = float(h.get("rank", 20)) - float(a.get("rank", 20))
        features["points_diff"] = float(h.get("points", 0)) - float(a.get("points", 0))
        features["goals_for_diff"] = float(h.get("goals_for", 0)) - float(a.get("goals_for", 0))
        features["goals_against_diff"] = float(h.get("goals_against", 0)) - float(a.get("goals_against", 0))
        features["win_rate_diff"] = features.get("home_win_rate", 0) - features.get("away_win_rate", 0)

        return features

    def _form_features(self, fundamental: dict[str, Any]) -> dict[str, float]:
        """近期状态：近5/10场"""
        features: dict[str, float] = {}
        form = fundamental.get("form", {})

        for side in ["home", "away"]:
            f = form.get(side, {})
            prefix = f"{side}_form_"
            features[f"{prefix}wins"] = float(f.get("wins", 0))
            features[f"{prefix}draws"] = float(f.get("draws", 0))
            features[f"{prefix}losses"] = float(f.get("losses", 0))
            features[f"{prefix}goals_for_avg"] = float(f.get("goals_for_avg", 0))
            features[f"{prefix}goals_against_avg"] = float(f.get("goals_against_avg", 0))
            features[f"{prefix}clean_sheet_rate"] = float(f.get("clean_sheet_rate", 0))
            features[f"{prefix}form_score"] = float(f.get("form_score", 0.5))
            # 近5场胜率
            total = f.get("wins", 0) + f.get("draws", 0) + f.get("losses", 0)
            features[f"{prefix}win_rate"] = (
                float(f["wins"]) / float(total) if total and f.get("wins") else 0.0
            )

        # 状态差值
        hf = form.get("home", {})
        af = form.get("away", {})
        features["form_score_diff"] = float(hf.get("form_score", 0.5)) - float(af.get("form_score", 0.5))
        features["form_goals_for_diff"] = float(hf.get("goals_for_avg", 0)) - float(af.get("goals_for_avg", 0))
        features["form_goals_against_diff"] = float(hf.get("goals_against_avg", 0)) - float(af.get("goals_against_avg", 0))

        return features

    def _home_away_features(self, fundamental: dict[str, Any]) -> dict[str, float]:
        """主客场拆分战绩"""
        features: dict[str, float] = {}
        standings = fundamental.get("standings", {})

        # 主队主场战绩
        h = standings.get("home", {})
        features["home_home_goals_for"] = float(h.get("home_goals_for", 0))
        features["home_home_goals_against"] = float(h.get("home_goals_against", 0))
        features["home_home_goal_diff"] = (
            features["home_home_goals_for"] - features["home_home_goals_against"]
        )

        # 客队客场战绩
        a = standings.get("away", {})
        features["away_away_goals_for"] = float(a.get("away_goals_for", 0))
        features["away_away_goals_against"] = float(a.get("away_goals_against", 0))
        features["away_away_goal_diff"] = (
            features["away_away_goals_for"] - features["away_away_goals_against"]
        )

        # 主场进攻 vs 客场防守
        features["home_attack_vs_away_defense"] = (
            features["home_home_goals_for"] + features["away_away_goals_against"]
        ) / 2
        features["away_attack_vs_home_defense"] = (
            features["away_away_goals_for"] + features["home_home_goals_against"]
        ) / 2

        return features

    def _h2h_features(self, fundamental: dict[str, Any]) -> dict[str, float]:
        """交锋历史"""
        features: dict[str, float] = {}
        h2h = fundamental.get("h2h_summary", {})
        total = h2h.get("home_wins", 0) + h2h.get("draws", 0) + h2h.get("away_wins", 0)

        features["h2h_home_win_rate"] = (
            float(h2h["home_wins"]) / float(total) if total else 0.33
        )
        features["h2h_draw_rate"] = (
            float(h2h["draws"]) / float(total) if total else 0.33
        )
        features["h2h_away_win_rate"] = (
            float(h2h["away_wins"]) / float(total) if total else 0.34
        )
        features["h2h_total"] = float(total)

        return features

    def _odds_features(self, odds_aggregates: dict[str, Any]) -> dict[str, float]:
        """赔率特征 — 市场隐含概率、凯利、离散度"""
        features: dict[str, float] = {}

        one_x_two = odds_aggregates.get("1x2")
        if one_x_two:
            # 去水后隐含概率（ML 的基准）
            features["odds_home_prob"] = float(one_x_two.no_vig_probs.get("home", 0.33))
            features["odds_draw_prob"] = float(one_x_two.no_vig_probs.get("draw", 0.33))
            features["odds_away_prob"] = float(one_x_two.no_vig_probs.get("away", 0.34))

            # 均值赔率
            features["odds_home_avg"] = float(one_x_two.avg_odds.get("home", 0))
            features["odds_draw_avg"] = float(one_x_two.avg_odds.get("draw", 0))
            features["odds_away_avg"] = float(one_x_two.avg_odds.get("away", 0))

            # 最佳赔率
            best_home = one_x_two.best_odds.get("home", (0, ""))[0]
            best_draw = one_x_two.best_odds.get("draw", (0, ""))[0]
            best_away = one_x_two.best_odds.get("away", (0, ""))[0]
            features["odds_home_best"] = float(best_home or 0)
            features["odds_draw_best"] = float(best_draw or 0)
            features["odds_away_best"] = float(best_away or 0)

            # 共识度和离散度
            features["odds_consensus_score"] = float(one_x_two.consensus_score) / 100.0
            features["odds_disagreement"] = float(one_x_two.disagreement_index)
            features["odds_bookmaker_count"] = float(one_x_two.bookmaker_count)

            # 概率差
            features["odds_home_away_prob_diff"] = features["odds_home_prob"] - features["odds_away_prob"]
            features["odds_home_draw_prob_diff"] = features["odds_home_prob"] - features["odds_draw_prob"]

            # 赔率差（主客）
            features["odds_home_away_diff"] = features["odds_home_avg"] - features["odds_away_avg"]

            # 水位（overround）
            features["odds_overround"] = float(one_x_two.overround)
            features["odds_return_rate"] = float(one_x_two.return_rate)
        else:
            # 无赔率数据，填默认值
            for key in [
                "odds_home_prob", "odds_draw_prob", "odds_away_prob",
                "odds_home_avg", "odds_draw_avg", "odds_away_avg",
                "odds_home_best", "odds_draw_best", "odds_away_best",
                "odds_consensus_score", "odds_disagreement", "odds_bookmaker_count",
                "odds_home_away_prob_diff", "odds_home_draw_prob_diff", "odds_home_away_diff",
                "odds_overround", "odds_return_rate",
            ]:
                features[key] = 0.0

        # 亚盘特征
        ah = odds_aggregates.get("asian_handicap")
        if ah:
            features["ah_line"] = float(ah.avg_odds.get("line", 0))
            features["ah_home_water"] = float(ah.avg_odds.get("home", 0))
            features["ah_away_water"] = float(ah.avg_odds.get("away", 0))
        else:
            features["ah_line"] = 0.0
            features["ah_home_water"] = 0.0
            features["ah_away_water"] = 0.0

        # 大小球特征
        ou = odds_aggregates.get("over_under")
        if ou:
            features["ou_line"] = float(ou.avg_odds.get("line", 2.5))
            features["ou_over_odds"] = float(ou.avg_odds.get("over", 0))
            features["ou_under_odds"] = float(ou.avg_odds.get("under", 0))
        else:
            features["ou_line"] = 2.5
            features["ou_over_odds"] = 0.0
            features["ou_under_odds"] = 0.0

        return features

    def _tactical_features(self, fundamental: dict[str, Any]) -> dict[str, float]:
        """战术特征：控球、射门、传球等"""
        features: dict[str, float] = {}

        for side in ["home", "away"]:
            record = fundamental.get(f"{side}_record", {})
            prefix = f"{side}_tac_"

            features[f"{prefix}goals_for_avg"] = float(record.get("goals_for_avg", 0))
            features[f"{prefix}goals_against_avg"] = float(record.get("goals_against_avg", 0))
            features[f"{prefix}shots_avg"] = float(record.get("avg_shots", 0))
            features[f"{prefix}possession"] = float(record.get("avg_possession", 0))
            features[f"{prefix}win_rate"] = (
                float(record.get("wins", 0)) / float(record.get("matches_played", 1))
                if record.get("matches_played") else 0.0
            )

        # 战术差值
        h = fundamental.get("home_record", {})
        a = fundamental.get("away_record", {})
        features["tac_possession_diff"] = float(h.get("avg_possession", 0)) - float(a.get("avg_possession", 0))
        features["tac_shots_diff"] = float(h.get("avg_shots", 0)) - float(a.get("avg_shots", 0))
        features["tac_goals_for_diff"] = float(h.get("goals_for_avg", 0)) - float(a.get("goals_for_avg", 0))
        features["tac_goals_against_diff"] = float(h.get("goals_against_avg", 0)) - float(a.get("goals_against_avg", 0))

        return features
