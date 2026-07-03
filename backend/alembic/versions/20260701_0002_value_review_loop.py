"""value review loop

Revision ID: 20260701_0002
Revises: 20260701_0001
Create Date: 2026-07-01 15:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260701_0002"
down_revision: Union[str, None] = "20260701_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fixture_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("home_key", sa.String(length=200), nullable=False),
        sa.Column("away_key", sa.String(length=200), nullable=False),
        sa.Column("home_name", sa.String(length=200), nullable=False),
        sa.Column("away_name", sa.String(length=200), nullable=False),
        sa.Column("fixture_id", sa.Integer(), nullable=False),
        sa.Column("source_text", sa.String(length=300), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("home_key", "away_key", name="uq_fixture_aliases_home_away"),
    )
    op.create_index("ix_fixture_aliases_fixture_id", "fixture_aliases", ["fixture_id"])
    op.create_index("ix_fixture_aliases_expires_at", "fixture_aliases", ["expires_at"])

    op.add_column("predictions", sa.Column("best_line", sa.Float(), nullable=True))
    op.add_column("predictions", sa.Column("best_bookmaker", sa.String(length=100), nullable=True))
    op.add_column("predictions", sa.Column("best_edge", sa.Float(), nullable=True))
    op.add_column("predictions", sa.Column("market_prob", sa.Float(), nullable=True))
    op.add_column("predictions", sa.Column("settled_status", sa.String(length=30), nullable=True))
    op.add_column("predictions", sa.Column("profit_units", sa.Float(), nullable=True))
    op.add_column("predictions", sa.Column("settlement_note", sa.Text(), nullable=True))
    op.add_column("predictions", sa.Column("settled_at", sa.DateTime(), nullable=True))
    op.create_index("ix_predictions_settled_status", "predictions", ["settled_status"])

    op.add_column("value_candidates", sa.Column("line", sa.Float(), nullable=True))
    op.add_column(
        "value_candidates", sa.Column("best_bookmaker", sa.String(length=100), nullable=True)
    )
    op.add_column("value_candidates", sa.Column("data_quality_score", sa.Integer(), nullable=True))
    op.add_column("value_candidates", sa.Column("return_rate", sa.Float(), nullable=True))
    op.add_column("value_candidates", sa.Column("overround", sa.Float(), nullable=True))
    op.add_column("value_candidates", sa.Column("is_shadow", sa.Boolean(), nullable=True))
    op.add_column(
        "value_candidates", sa.Column("settled_status", sa.String(length=30), nullable=True)
    )
    op.add_column("value_candidates", sa.Column("profit_units", sa.Float(), nullable=True))
    op.add_column("value_candidates", sa.Column("settlement_note", sa.Text(), nullable=True))
    op.add_column("value_candidates", sa.Column("settled_at", sa.DateTime(), nullable=True))
    op.create_index("ix_value_candidates_settled_status", "value_candidates", ["settled_status"])

    op.add_column("subscriptions", sa.Column("notified_t6", sa.Boolean(), nullable=True))
    op.add_column("subscriptions", sa.Column("notified_t1", sa.Boolean(), nullable=True))
    op.add_column("subscriptions", sa.Column("notified_result", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("subscriptions", "notified_result")
    op.drop_column("subscriptions", "notified_t1")
    op.drop_column("subscriptions", "notified_t6")

    op.drop_index("ix_value_candidates_settled_status", table_name="value_candidates")
    op.drop_column("value_candidates", "settled_at")
    op.drop_column("value_candidates", "settlement_note")
    op.drop_column("value_candidates", "profit_units")
    op.drop_column("value_candidates", "settled_status")
    op.drop_column("value_candidates", "is_shadow")
    op.drop_column("value_candidates", "overround")
    op.drop_column("value_candidates", "return_rate")
    op.drop_column("value_candidates", "data_quality_score")
    op.drop_column("value_candidates", "best_bookmaker")
    op.drop_column("value_candidates", "line")

    op.drop_index("ix_predictions_settled_status", table_name="predictions")
    op.drop_column("predictions", "settled_at")
    op.drop_column("predictions", "settlement_note")
    op.drop_column("predictions", "profit_units")
    op.drop_column("predictions", "settled_status")
    op.drop_column("predictions", "market_prob")
    op.drop_column("predictions", "best_edge")
    op.drop_column("predictions", "best_bookmaker")
    op.drop_column("predictions", "best_line")

    op.drop_index("ix_fixture_aliases_expires_at", table_name="fixture_aliases")
    op.drop_index("ix_fixture_aliases_fixture_id", table_name="fixture_aliases")
    op.drop_table("fixture_aliases")
