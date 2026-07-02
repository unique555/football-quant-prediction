"""auto analyze push logs and backtest runs

Revision ID: 20260702_0001
Revises: 20260701_0002
Create Date: 2026-07-02 10:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260702_0001"
down_revision: Union[str, None] = "20260701_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 推送记录表
    op.create_table(
        "push_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("prediction_id", sa.Integer(), nullable=True),
        sa.Column("push_type", sa.String(length=30), nullable=True),
        sa.Column("message_text", sa.Text(), nullable=True),
        sa.Column("pushed_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # 回测记录表
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_version_id", sa.Integer(), nullable=True),
        sa.Column("league_id", sa.Integer(), nullable=True),
        sa.Column("season_start", sa.Integer(), nullable=True),
        sa.Column("season_end", sa.Integer(), nullable=True),
        sa.Column("total_matches", sa.Integer(), nullable=True),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("roi", sa.Float(), nullable=True),
        sa.Column("brier_score", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("report_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # 模型版本表
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version_tag", sa.String(length=50), nullable=False),
        sa.Column("model_type", sa.String(length=50), nullable=True),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("brier_score", sa.Float(), nullable=True),
        sa.Column("log_loss", sa.Float(), nullable=True),
        sa.Column("features_hash", sa.String(length=64), nullable=True),
        sa.Column("training_samples", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=True),
        sa.Column("mlflow_run_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_tag"),
    )

    # 特征快照表
    op.create_table(
        "feature_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fixture_id", sa.Integer(), nullable=False),
        sa.Column("feature_version", sa.String(length=50), nullable=True),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feature_snapshots_fixture_id", "feature_snapshots", ["fixture_id"])


def downgrade() -> None:
    op.drop_index("ix_feature_snapshots_fixture_id", table_name="feature_snapshots")
    op.drop_table("feature_snapshots")
    op.drop_table("model_versions")
    op.drop_table("backtest_runs")
    op.drop_table("push_logs")
