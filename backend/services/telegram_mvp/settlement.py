"""Settlement helpers for value candidates."""

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


def _settle_half(diff: float, pick_home: bool) -> str:
    if diff > 0:
        return "win" if pick_home else "loss"
    if diff == 0:
        return "push"
    return "loss" if pick_home else "win"


def settle_asian_handicap(home_goals: int, away_goals: int, line: float, pick: str) -> str:
    """Return win/half_win/push/half_loss/loss for Asian handicap picks."""
    pick_home = pick == "home"
    signed_line = line if pick_home else -line
    diff = home_goals - away_goals + signed_line
    quarter = abs(line * 4) % 2 == 1
    if not quarter:
        return _settle_half(diff, pick_home=True)

    lower_line = signed_line - 0.25 if signed_line > 0 else signed_line - 0.25
    upper_line = signed_line + 0.25 if signed_line > 0 else signed_line + 0.25
    outcomes = []
    for part_line in (lower_line, upper_line):
        outcomes.append(_settle_half(home_goals - away_goals + part_line, pick_home=True))
    wins = outcomes.count("win")
    losses = outcomes.count("loss")
    pushes = outcomes.count("push")
    if wins == 2:
        return "win"
    if losses == 2:
        return "loss"
    if wins and pushes:
        return "half_win"
    if losses and pushes:
        return "half_loss"
    return "push"
