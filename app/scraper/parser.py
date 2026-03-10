import re
from bs4 import BeautifulSoup
from typing import Dict, List, Set, Tuple

def parse_html_basic(html_content: str, base_url: str) -> Tuple[str, Dict]:
    """
    Toma un HTML crudo y lo transforma en dos cosas:
    1. Un texto plano súper limpio preparado para análisis local basado en heurísticas.
    2. Un diccionario de metadatos exactos (links, emails directos, redes sociales).
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. Extraer Metadatos directos
    metadata = {
        "title": "",
        "description": "",
        "emails": set(),
        "phones": set(),
        "social_links": set(),
        "internal_links": set() # Para buscar la página de "Contacto" si es necesario
    }
    
    # Title
    if soup.title and soup.title.string:
        metadata["title"] = soup.title.string.strip()
        
    # Meta Description
    meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if meta_desc and meta_desc.get("content"):
        metadata["description"] = meta_desc["content"].strip()
        
    # Extraer enlaces clave (Correos y Redes)
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href'].strip()
        
        # Correos directos en enlaces mailto
        if href.lower().startswith('mailto:'):
            email = href[7:].split('?')[0] # quitar parametros como ?subject=x
            if '@' in email:
                metadata["emails"].add(email.lower())
                
        # Teléfonos directos
        elif href.lower().startswith('tel:'):
            metadata["phones"].add(href[4:])
            
        # Enlaces a Redes Sociales o "Páginas de Contacto"
        elif any(social in href.lower() for social in ['linkedin.com', 'instagram.com', 'facebook.com', 'twitter.com']):
            metadata["social_links"].add(href)
            
        # Links internos (buscar 'contacto', 'about', 'nosotros')
        elif href.startswith('/') or base_url in href:
            text = a_tag.get_text().lower()
            if hasattr(text, 'strip'):
                if any(kw in text or kw in href.lower() for kw in ['contact', 'about', 'nosotros', 'equipo']):
                    full_link = href if href.startswith('http') else f"{base_url.rstrip('/')}/{href.lstrip('/')}"
                    metadata["internal_links"].add(full_link)

    # 2. Limpiar todo lo irrelevante para dejar puro texto listo para RegEx
    # Destruir scripts, estilos, svgs e imágenes
    for element in soup(["script", "style", "svg", "img", "noscript", "iframe", "header", "footer"]):
        element.decompose()
        
    # Obtener el texto que queda
    raw_text = soup.get_text(separator=' ', strip=True)
    
    # Limpiador Regex de espacios redundantes
    clean_text = re.sub(r'\s+', ' ', raw_text)
    
    # Convertir sets a listas para que sea JSON serializable
    metadata["emails"] = list(metadata["emails"])
    metadata["phones"] = list(metadata["phones"])
    metadata["social_links"] = list(metadata["social_links"])
    metadata["internal_links"] = list(metadata["internal_links"])
    
    return clean_text, metadata
