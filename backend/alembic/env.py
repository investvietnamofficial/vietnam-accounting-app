from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from sqlalchemy.dialects.postgresql import VARCHAR
from alembic import context
from app.core.config import get_settings
from app.core.database import Base
import app.models  # ensure all models are imported

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

if config.config_file_name is not None:
    if config.file_config is not None and config.file_config.has_section("formatters"):
        fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section),
                                     prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                         version_table_coltype=VARCHAR(64))
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
