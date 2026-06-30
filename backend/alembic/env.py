"""
Alembic 环境配置
"""

from logging.config import fileConfig

from alembic import context
from core.config import settings
from core.database import Base

# 导入所有模型，确保 Base.metadata 包含全部表
from models.league import League  # noqa
from models.match import Match  # noqa
from models.odds import Odds  # noqa
from models.prediction import Prediction  # noqa
from models.team import Team  # noqa
from models.user import User  # noqa
from sqlalchemy import engine_from_config, pool

config = context.config
config.set_main_option("sqlalchemy.url", settings.SYNC_DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
