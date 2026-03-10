from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from app.config import settings

# Usando el engine asíncrono compatible con asyncpg
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    pool_pre_ping=True,       # Verifica la conexión antes de usarla (evita "connection is closed")
    pool_recycle=1800,        # Recicla conexiones cada 30 min (evita timeouts del servidor)
    pool_size=5,              # Máximo de conexiones simultáneas en el pool
    max_overflow=10,          # Conexiones extras permitidas sobre pool_size
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
