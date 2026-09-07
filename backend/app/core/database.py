import logging
from typing import AsyncGenerator
from sqlalchemy import TypeDecorator, JSON, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from app.core.config import settings

logger = logging.getLogger("synapse.database")

# Declarative Base for ORM models
Base = declarative_base()

# Conditional Vector column type:
# Uses pgvector.sqlalchemy.Vector on PostgreSQL, falls back to JSON on SQLite/others
try:
    from pgvector.sqlalchemy import Vector as PgVector
except ImportError:
    PgVector = None


class VectorColumn(TypeDecorator):
    """
    Custom SQLAlchemy type that dynamically maps to:
    - pgvector.sqlalchemy.Vector on PostgreSQL + pgvector
    - JSON on SQLite and other development databases
    """
    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = 768, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and PgVector is not None:
            return dialect.type_descriptor(PgVector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        if hasattr(value, "tolist"):
            return value.tolist()
        return list(value)

    def process_result_value(self, value, dialect):
        return value


# Engine & Session Factory
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True
)

def import_all_models():
    """Ensure all model definitions are loaded into the Base registry."""
    import app.modules.schedules.models  # noqa: F401
    import app.modules.field_capture.models  # noqa: F401
    import app.modules.semantic_matcher.models  # noqa: F401
    import app.modules.dependency_validator.models  # noqa: F401
    import app.modules.review_inbox.models  # noqa: F401

import_all_models()

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for obtaining an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables and extensions with graceful SQLite fallback."""
    global engine, async_session_factory
    try:
        async with engine.begin() as conn:
            # If running on PostgreSQL, ensure pgvector extension exists
            if engine.dialect.name == "postgresql":
                try:
                    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                    logger.info("pgvector extension verified on PostgreSQL.")
                except Exception as e:
                    logger.warning(f"Could not enable pgvector extension: {e}")

            # Create all declared tables
            await conn.run_sync(Base.metadata.create_all)

            # Ensure Phase 4 OCC columns exist on legacy SQLite files
            if engine.dialect.name == "sqlite":
                try:
                    await conn.execute(text("ALTER TABLE schedule_activities ADD COLUMN actuals_version INTEGER DEFAULT 1;"))
                except Exception:
                    pass
                try:
                    await conn.execute(text("ALTER TABLE match_candidates ADD COLUMN validated_activity_version INTEGER DEFAULT 1;"))
                except Exception:
                    pass

            logger.info(f"Database tables initialized successfully on {engine.url.render_as_string(hide_password=True)}.")
    except Exception as e:
        if "postgresql" in str(settings.DATABASE_URL):
            logger.warning(
                f"PostgreSQL connection failed ({e}). "
                f"Switching engine to local SQLite fallback: sqlite+aiosqlite:///./project_synapse.db"
            )
            fallback_url = "sqlite+aiosqlite:///./project_synapse.db"
            engine = create_async_engine(fallback_url, echo=False, future=True)
            async_session_factory.configure(bind=engine)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                try:
                    await conn.execute(text("ALTER TABLE schedule_activities ADD COLUMN actuals_version INTEGER DEFAULT 1;"))
                except Exception:
                    pass
                try:
                    await conn.execute(text("ALTER TABLE match_candidates ADD COLUMN validated_activity_version INTEGER DEFAULT 1;"))
                except Exception:
                    pass
            logger.info("Local SQLite development database initialized successfully.")
        else:
            raise
