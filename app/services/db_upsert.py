from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert
import logging

from app.models import Prospect, ScrapingJob
from typing import Dict, Any

logger = logging.getLogger(__name__)

async def upsert_prospect(db: AsyncSession, prospect_data: Dict[str, Any]) -> Prospect:
    """
    Guarda un nuevo prospecto en la base de datos o lo actualiza 
    si ya existe un registro con el mismo `domain`.
    
    Usa la cláusula de PostgreSQL "ON CONFLICT" adaptada por SQLAlchemy para
    un verdadero *Upsert*, lo que evita errores de concurrencia y duplicación múltiple.
    """
    
    # El domain es nuestra llave primaria lógica
    domain = prospect_data.get("domain")
    if not domain:
        logger.error(f"No se puede guardar el prospecto sin dominio válido: {prospect_data}")
        return None
        
    # Preparar el statement parametrizado
    stmt = insert(Prospect).values(**prospect_data)
    
    # Definir qué columnas actualizar durante el Upsert si hay colisión.
    # (Obtenemos un diccionario dinámico evitando intentar sobrescribir columnas intocables como ID, domain, created_at)
    update_dict = {
        col.name: getattr(stmt.excluded, col.name)
        for col in Prospect.__table__.columns
        if col.name not in ["id", "domain", "created_at"] and col.name in prospect_data
    }
    
    if update_dict:
        stmt = stmt.on_conflict_do_update(
            index_elements=["domain"], 
            set_=update_dict
        )
    else:
        # En caso extraño donde no querramos actualizar nada, solo no hacemos nada.
        stmt = stmt.on_conflict_do_nothing(index_elements=["domain"])

    # Ejecutar guardado
    result = await db.execute(stmt)
    await db.commit()
    
    logger.info(f"Upsert exitoso para dominio: {domain}")
    
    # Devolver el objeto guardado o actualizado (requiere segunda consulta en asyncpg al hacer on_conflict_do_update)
    query = select(Prospect).where(Prospect.domain == domain)
    prospect_obj = await db.execute(query)
    
    return prospect_obj.scalars().first()
