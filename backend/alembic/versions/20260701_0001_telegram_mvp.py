"""telegram first mvp

Revision ID: 20260701_0001
Revises:
Create Date: 2026-07-01 11:20:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260701_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leagues",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("tier", sa.Integer(), nullable=True),
        sa.Column("api_source", sa.String(length=50), nullable=True),
        sa.Column("external_id", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("short_name", sa.String(length=100), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("elo_rating", sa.Float(), nullable=True),
        sa.Column("xg_for_avg", sa.Float(), nullable=True),
        sa.Column("xg_against_avg", sa.Float(), nullable=True),
        sa.Column("form_score", sa.Float(), nullable=True),
        sa.Column("external_id", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("hashed_password", sa.String(length=200), nullable=False),
        sa.Column("subscription", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("home_team_id", sa.Integer(), nullable=True),
        sa.Column("away_team_id", sa.Integer(), nullable=True),
        sa.Column("league_id", sa.Integer(), nullable=True),
        sa.Column("api_fixture_id", sa.Integer(), nullable=True),
        sa.Column("api_league_id", sa.Integer(), nullable=True),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("home_team_name", sa.String(length=200), nullable=True),
        sa.Column("away_team_name", sa.String(length=200), nullable=True),
        sa.Column("league_name", sa.String(length=200), nullable=True),
        sa.Column("match_date", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("ht_home_score", sa.Integer(), nullable=True),
        sa.Column("ht_away_score", sa.Integer(), nullable=True),
        sa.Column("venue", sa.String(length=300), nullable=True),
        sa.Column("attendance", sa.Integer(), nullable=True),
        sa.Column("external_id", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["away_team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["home_team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id", name="uq_matches_external_id"),
    )
    op.create_index("ix_matches_api_fixture_id", "matches", ["api_fixture_id"])
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=True),
        sa.Column("fixture_id", sa.Integer(), nullable=True),
        sa.Column("model_version", sa.String(length=50), nullable=True),
        sa.Column("model_name", sa.String(length=50), nullable=True),
        sa.Column("home_win_prob", sa.Float(), nullable=True),
        sa.Column("draw_prob", sa.Float(), nullable=True),
        sa.Column("away_win_prob", sa.Float(), nullable=True),
        sa.Column("predicted_home_score", sa.Float(), nullable=True),
        sa.Column("predicted_away_score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("best_market", sa.String(length=50), nullable=True),
        sa.Column("best_pick", sa.String(length=120), nullable=True),
        sa.Column("best_display_pick", sa.String(length=160), nullable=True),
        sa.Column("best_odds", sa.Float(), nullable=True),
        sa.Column("best_ev", sa.Float(), nullable=True),
        sa.Column("best_kelly", sa.Float(), nullable=True),
        sa.Column("value_score", sa.Integer(), nullable=True),
        sa.Column("confidence_text", sa.String(length=20), nullable=True),
        sa.Column("risk", sa.String(length=20), nullable=True),
        sa.Column("report_text", sa.Text(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_predictions_fixture_id", "predictions", ["fixture_id"])
    op.create_table(
        "odds",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("bookmaker", sa.String(length=100), nullable=False),
        sa.Column("home_win_odds", sa.Float(), nullable=True),
        sa.Column("draw_odds", sa.Float(), nullable=True),
        sa.Column("away_win_odds", sa.Float(), nullable=True),
        sa.Column("over_25_odds", sa.Float(), nullable=True),
        sa.Column("btts_odds", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "team_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alias", sa.String(length=200), nullable=False),
        sa.Column("alias_key", sa.String(length=200), nullable=False),
        sa.Column("api_team_id", sa.Integer(), nullable=True),
        sa.Column("api_team_name", sa.String(length=200), nullable=False),
        sa.Column("lang", sa.String(length=20), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alias_key", name="uq_team_aliases_alias_key"),
    )
    op.create_table(
        "odds_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fixture_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_type", sa.String(length=30), nullable=False),
        sa.Column("market", sa.String(length=40), nullable=False),
        sa.Column("bookmaker", sa.String(length=100), nullable=True),
        sa.Column("home_odds", sa.Float(), nullable=True),
        sa.Column("draw_odds", sa.Float(), nullable=True),
        sa.Column("away_odds", sa.Float(), nullable=True),
        sa.Column("ah_line", sa.Float(), nullable=True),
        sa.Column("ah_home_odds", sa.Float(), nullable=True),
        sa.Column("ah_away_odds", sa.Float(), nullable=True),
        sa.Column("ou_line", sa.Float(), nullable=True),
        sa.Column("over_odds", sa.Float(), nullable=True),
        sa.Column("under_odds", sa.Float(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("captured_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_odds_snapshots_fixture_id", "odds_snapshots", ["fixture_id"])
    op.create_index("ix_odds_snapshots_captured_at", "odds_snapshots", ["captured_at"])
    op.create_table(
        "value_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fixture_id", sa.Integer(), nullable=False),
        sa.Column("market", sa.String(length=40), nullable=False),
        sa.Column("pick", sa.String(length=80), nullable=False),
        sa.Column("display_pick", sa.String(length=120), nullable=False),
        sa.Column("prob", sa.Float(), nullable=True),
        sa.Column("odds", sa.Float(), nullable=True),
        sa.Column("market_prob", sa.Float(), nullable=True),
        sa.Column("edge", sa.Float(), nullable=True),
        sa.Column("ev", sa.Float(), nullable=True),
        sa.Column("kelly", sa.Float(), nullable=True),
        sa.Column("risk", sa.String(length=20), nullable=True),
        sa.Column("bookmaker_count", sa.Integer(), nullable=True),
        sa.Column("consensus_score", sa.Integer(), nullable=True),
        sa.Column("disagreement_index", sa.Float(), nullable=True),
        sa.Column("value_score", sa.Integer(), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_value_candidates_fixture_id", "value_candidates", ["fixture_id"])
    op.create_index("ix_value_candidates_created_at", "value_candidates", ["created_at"])
    op.create_table(
        "results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fixture_id", sa.Integer(), nullable=False),
        sa.Column("home_goals", sa.Integer(), nullable=True),
        sa.Column("away_goals", sa.Integer(), nullable=True),
        sa.Column("halftime_home", sa.Integer(), nullable=True),
        sa.Column("halftime_away", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fixture_id", name="uq_results_fixture_id"),
    )
    op.create_index("ix_results_fixture_id", "results", ["fixture_id"])
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=80), nullable=False),
        sa.Column("chat_id", sa.String(length=80), nullable=False),
        sa.Column("fixture_id", sa.Integer(), nullable=False),
        sa.Column("notify_t6", sa.Boolean(), nullable=True),
        sa.Column("notify_t1", sa.Boolean(), nullable=True),
        sa.Column("notify_result", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "fixture_id", name="uq_subscriptions_user_fixture"),
    )
    op.create_index("ix_subscriptions_fixture_id", "subscriptions", ["fixture_id"])


def downgrade() -> None:
    op.drop_index("ix_subscriptions_fixture_id", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index("ix_results_fixture_id", table_name="results")
    op.drop_table("results")
    op.drop_index("ix_value_candidates_created_at", table_name="value_candidates")
    op.drop_index("ix_value_candidates_fixture_id", table_name="value_candidates")
    op.drop_table("value_candidates")
    op.drop_index("ix_odds_snapshots_captured_at", table_name="odds_snapshots")
    op.drop_index("ix_odds_snapshots_fixture_id", table_name="odds_snapshots")
    op.drop_table("odds_snapshots")
    op.drop_table("team_aliases")
    op.drop_table("odds")
    op.drop_index("ix_predictions_fixture_id", table_name="predictions")
    op.drop_table("predictions")
    op.drop_index("ix_matches_api_fixture_id", table_name="matches")
    op.drop_table("matches")
    op.drop_table("users")
    op.drop_table("teams")
    op.drop_table("leagues")
