"""Value candidate selection with hard risk gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from services.telegram_mvp.odds import MarketAggregate


@dataclass
class ModelProbabilities:
    home: float
    draw: float
    away: float
    over: float = 0.0
    under: float = 0.0
    ah_home: float = 0.0
    ah_away: float = 0.0


@dataclass
class ValueCandidateDTO:
    fixture_id: int
    market: str
    pick: str
    display_pick: str
    prob: float
    odds: float
    market_prob: float
    edge: float
    ev: float
    kelly: float
    risk: str
    bookmaker_count: int
    consensus_score: int
    disagreement_index: float
    value_score: int
    selected: bool
    reason: str
    line: float | None = None
    best_bookmaker: str | None = None
    data_quality_score: int = 0
    return_rate: float = 0.0
    overround: float = 0.0
    is_shadow: bool = False

    def asdict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ValueSelectorConfig:
    min_bookmakers: int = 3
    min_consensus: int = 60
    max_disagreement: float = 0.10
    min_data_quality: int = 45
    max_kelly: float = 0.18
    min_edge: float = 0.005
    ev_weight: float = 320
    edge_weight: float = 210
    kelly_weight: float = 100
    consensus_weight: float = 0.18
    bookmaker_weight: float = 3.0
    data_quality_weight: float = 0.12
    disagreement_penalty: float = 130


def kelly_fraction(prob: float, odds: float) -> float:
    if odds <= 1:
        return 0.0
    k = (prob * odds - 1) / (odds - 1)
    return max(0.0, k)


class ValueSelector:
    def __init__(self, config: ValueSelectorConfig | None = None):
        self.config = config or ValueSelectorConfig()

    def select(
        self,
        fixture_id: int,
        model: ModelProbabilities,
        aggregates: dict[str, MarketAggregate | None],
    ) -> list[ValueCandidateDTO]:
        candidates: list[ValueCandidateDTO] = []
        one_x_two = aggregates.get("1x2")
        if one_x_two:
            for side, pick, display, prob in (
                ("home", "home", "胜平负：主胜", model.home),
                ("draw", "draw", "胜平负：平局", model.draw),
                ("away", "away", "胜平负：客胜", model.away),
            ):
                candidates.append(self._candidate(fixture_id, one_x_two, pick, display, prob, side))

        ah = aggregates.get("asian_handicap")
        if ah:
            line = ah.avg_odds.get("line", 0.0)
            candidates.append(
                self._candidate(
                    fixture_id, ah, "home", f"亚盘：主队 {line:+g}", model.ah_home, "home"
                )
            )
            candidates.append(
                self._candidate(
                    fixture_id, ah, "away", f"亚盘：客队 {-line:+g}", model.ah_away, "away"
                )
            )

        ou = aggregates.get("over_under")
        if ou:
            line = ou.avg_odds.get("line", 0.0)
            candidates.append(
                self._candidate(fixture_id, ou, "over", f"大小球：大 {line:g}", model.over, "over")
            )
            candidates.append(
                self._candidate(
                    fixture_id, ou, "under", f"大小球：小 {line:g}", model.under, "under"
                )
            )

        selected = [item for item in candidates if item.selected]
        if selected:
            winner = max(selected, key=lambda item: item.value_score)
            candidates = [
                ValueCandidateDTO(**{**item.asdict(), "selected": item is winner})
                for item in candidates
            ]
        return sorted(candidates, key=lambda item: (item.selected, item.value_score), reverse=True)

    def _risk(self, aggregate: MarketAggregate, kelly: float) -> str:
        cfg = self.config
        if (
            aggregate.bookmaker_count < cfg.min_bookmakers
            or aggregate.consensus_score < cfg.min_consensus
            or aggregate.disagreement_index > cfg.max_disagreement
            or aggregate.data_quality_score < cfg.min_data_quality
            or kelly > cfg.max_kelly
        ):
            return "高"
        if (
            aggregate.bookmaker_count < 4
            or aggregate.consensus_score < 72
            or aggregate.disagreement_index > 0.07
        ):
            return "中"
        return "低"

    def _score(
        self,
        edge: float,
        ev: float,
        kelly: float,
        aggregate: MarketAggregate,
        risk: str,
        is_shadow: bool,
    ) -> int:
        cfg = self.config
        base = (
            ev * cfg.ev_weight
            + edge * cfg.edge_weight
            + kelly * cfg.kelly_weight
            + aggregate.consensus_score * cfg.consensus_weight
            + min(aggregate.bookmaker_count, 8) * cfg.bookmaker_weight
            + aggregate.data_quality_score * cfg.data_quality_weight
            - aggregate.disagreement_index * cfg.disagreement_penalty
        )
        if risk == "高":
            base -= 35
        elif risk == "中":
            base -= 10
        if is_shadow:
            base -= 20
        return max(0, min(100, round(base)))

    def _candidate(
        self,
        fixture_id: int,
        aggregate: MarketAggregate,
        pick: str,
        display_pick: str,
        prob: float,
        best_side: str,
    ) -> ValueCandidateDTO:
        odds, bookmaker = aggregate.best_odds[best_side]
        market_prob = aggregate.no_vig_probs.get(best_side, 0.0)
        edge = prob - market_prob
        ev = prob * odds - 1
        kelly = kelly_fraction(prob, odds)
        risk = self._risk(aggregate, kelly)
        is_shadow = aggregate.market != "1x2" and abs(prob - 0.5) < 0.015
        hard_pass = (
            prob > market_prob
            and ev > 0
            and 0 < kelly <= self.config.max_kelly
            and edge > self.config.min_edge
            and aggregate.bookmaker_count >= self.config.min_bookmakers
            and aggregate.consensus_score >= self.config.min_consensus
            and aggregate.disagreement_index <= self.config.max_disagreement
            and aggregate.data_quality_score >= self.config.min_data_quality
            and risk != "高"
            and odds > 1.01
            and not is_shadow
        )
        score = self._score(edge, ev, kelly, aggregate, risk, is_shadow)
        reasons = []
        if prob <= market_prob:
            reasons.append("模型概率未高于市场")
        if ev <= 0:
            reasons.append("EV不足")
        if kelly <= 0 or kelly > self.config.max_kelly:
            reasons.append("Kelly不合理")
        if aggregate.bookmaker_count < self.config.min_bookmakers:
            reasons.append("机构数不足")
        if aggregate.consensus_score < self.config.min_consensus:
            reasons.append("一致性不足")
        if aggregate.disagreement_index > self.config.max_disagreement:
            reasons.append("赔率分歧偏高")
        if aggregate.data_quality_score < self.config.min_data_quality:
            reasons.append("数据完整度不足")
        if is_shadow:
            reasons.append("概率来源不足，仅观察")
        reason = "通过价值筛选" if hard_pass else "；".join(reasons) or "未达标"
        return ValueCandidateDTO(
            fixture_id=fixture_id,
            market=aggregate.market,
            pick=pick,
            display_pick=display_pick,
            prob=round(prob, 4),
            odds=round(odds, 3),
            market_prob=round(market_prob, 4),
            edge=round(edge, 4),
            ev=round(ev, 4),
            kelly=round(kelly, 4),
            risk=risk,
            bookmaker_count=aggregate.bookmaker_count,
            consensus_score=aggregate.consensus_score,
            disagreement_index=aggregate.disagreement_index,
            value_score=score,
            selected=hard_pass,
            reason=reason,
            line=aggregate.avg_odds.get("line"),
            best_bookmaker=bookmaker,
            data_quality_score=aggregate.data_quality_score,
            return_rate=aggregate.return_rate,
            overround=aggregate.overround,
            is_shadow=is_shadow,
        )


def select_value_candidates(
    fixture_id: int,
    model: ModelProbabilities,
    aggregates: dict[str, MarketAggregate | None],
) -> list[ValueCandidateDTO]:
    return ValueSelector().select(fixture_id, model, aggregates)
