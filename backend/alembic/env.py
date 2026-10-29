"""Alembic environment. Reads DATABASE_URL from .env; uses Base.metadata for autogen."""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from api.db.models import Base

load_dotenv()

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

_db_url = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

# Default `postgresql://` resolves to psycopg2; this project installs
# psycopg (v3). Rewrite the scheme so stale URLs still work.
if _db_url.startswith("postgresql://"):
    _db_url = "postgresql+psycopg://" + _db_url[len("postgresql://"):]

# alembic.ini is a ConfigParser file where `%` triggers interpolation.
# Escape so a password like `Rishabh01%` survives the round-trip.
config.set_main_option("sqlalchemy.url", _db_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import text

    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # pgvector must exist before 0001's create_all encounters vector(1024).
        if connection.dialect.name == "postgresql":
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
