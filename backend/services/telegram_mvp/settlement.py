"""Settlement helpers for post-match review."""

from __future__ import annotations


def settle_1x2(home_goals: int, away_goals: int, pick: str) -> str:
    actual = "home" if home_goals > away_goals else ("draw" if home_goals == away_goals else "away")
    return "win" if pick == actual else "loss"


def settle_over_under(home_goals: int, away_goals: int, line: float, pick: str) -> str:
    total = home_goals + away_goals
    diff = total - line
    if diff == 0:
        return "push"
    if pick == "over":
        return "win" if diff > 0 else "loss"
    return "win" if diff < 0 else "loss"


def _settle_spread(diff: float) -> str:
    if diff > 0:
        return "win"
    if diff == 0:
        return "push"
    return "loss"


def _quarter_parts(line: float) -> tuple[float, float]:
    doubled = round(line * 2) / 2
    if abs(line - doubled) < 1e-9:
        return line, line
    lower = line - 0.25
    upper = line + 0.25
    return lower, upper


def settle_asian_handicap(home_goals: int, away_goals: int, line: float, pick: str) -> str:
    """Return win/half_win/push/half_loss/loss for Asian handicap picks."""
    signed_line = line if pick == "home" else -line
    parts = _quarter_parts(signed_line)
    outcomes = [_settle_spread(home_goals - away_goals + part) for part in parts]
    if outcomes[0] == outcomes[1]:
        return outcomes[0]
    if "win" in outcomes and "push" in outcomes:
        return "half_win"
    if "loss" in outcomes and "push" in outcomes:
        return "half_loss"
    return "push"


def profit_units(status: str, odds: float | None) -> float:
    if status == "win":
        return round((odds or 1) - 1, 4)
    if status == "half_win":
        return round(((odds or 1) - 1) / 2, 4)
    if status == "push":
        return 0.0
    if status == "half_loss":
        return -0.5
    if status == "loss":
        return -1.0
    return 0.0


def settlement_text(status: str) -> str:
    return {
        "win": "全赢",
        "half_win": "半赢",
        "push": "走水",
        "half_loss": "半输",
        "loss": "全输",
    }.get(status, status or "pending")
