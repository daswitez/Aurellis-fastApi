import httpx
import random
import logging
from typing import Optional

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]

async def fetch_html(url: str, timeout: int = 15) -> Optional[str]:
    """
    Realiza una petición HTTP asíncrona a la URL indicada seleccionando
    un User-Agent aleatorio para evadir las defensas antibot más básicas.
    
    Args:
        url: La dirección web a descargar.
        timeout: Segundos a esperar antes de abortar (default: 15).
        
    Returns:
        El HTML de la página como string, o None si falla.
    """
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "DNT": "1",  # Do Not Track request header
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    try:
        # follows_redirects=True permite perseguir mudanzas de sitios web limpios a www o https sin fallar
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, verify=False, timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status() # Lanza excepción para 400s y 500s
            return response.text
            
    except httpx.ConnectTimeout:
        logger.warning(f"Timeout al intentar conectar a {url}")
    except httpx.HTTPStatusError as e:
        logger.warning(f"Error de estado HTTP {e.response.status_code} al visitar {url}")
    except httpx.RequestError as e:
        logger.warning(f"Error de red genérico al visitar {url}: {str(e)}")
    except Exception as e:
        logger.error(f"Error desconocido extrayendo {url}: {str(e)}")
        
    return None
