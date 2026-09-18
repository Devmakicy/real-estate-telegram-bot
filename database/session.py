from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import DATA_DIR, DATABASE_URL
from database.models import Base

DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate)


def _migrate(connection) -> None:
    from sqlalchemy import inspect, text

    inspector = inspect(connection)
    if "users" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("users")}
    if "topic_id" not in columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN topic_id BIGINT"))
