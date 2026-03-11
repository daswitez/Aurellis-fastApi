import re
from bs4 import BeautifulSoup
from typing import Dict, List, Set, Tuple
from urllib.parse import urljoin, urlparse


INTERNAL_LINK_KEYWORDS = ["contact", "contacto", "about", "nosotros", "equipo", "careers", "trabajo", "empleo"]
EMAIL_REGEX = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
PHONE_REGEX = re.compile(r"(?:(?:\+|00)\d{1,3}[\s\-./]?)?(?:\(?\d{2,4}\)?[\s\-./]?){2,5}\d{2,4}")
EMAIL_BLOCKLIST_TOKENS = {"example.com", "yourdomain", "domain.com", "email.com", "test.com", "localhost"}


def _normalize_href(base_url: str, href: str) -> str | None:
    normalized_href = href.strip()
    if not normalized_href or normalized_href.startswith("#"):
        return None
    if normalized_href.lower().startswith(("javascript:", "mailto:", "tel:")):
        return None
    return urljoin(base_url, normalized_href)


def _is_same_site(base_url: str, candidate_url: str) -> bool:
    base_netloc = urlparse(base_url).netloc.lower().removeprefix("www.")
    candidate_netloc = urlparse(candidate_url).netloc.lower().removeprefix("www.")
    return bool(base_netloc) and base_netloc == candidate_netloc


def _looks_like_internal_key_page(anchor_text: str, href: str) -> bool:
    anchor_lower = anchor_text.lower()
    href_lower = href.lower()
    return any(keyword in anchor_lower or keyword in href_lower for keyword in INTERNAL_LINK_KEYWORDS)


def _normalize_email(candidate: str) -> str | None:
    normalized = candidate.strip().strip(".,;:()[]{}<>\"'").lower()
    if "@" not in normalized:
        return None
    if any(token in normalized for token in EMAIL_BLOCKLIST_TOKENS):
        return None
    return normalized


def _normalize_phone(candidate: str) -> str | None:
    normalized = re.sub(r"[^\d+]", "", candidate.strip())
    if normalized.startswith("00"):
        normalized = f"+{normalized[2:]}"
    if normalized.count("+") > 1 or ("+" in normalized and not normalized.startswith("+")):
        return None

    digits_only = re.sub(r"\D", "", normalized)
    if len(digits_only) < 7 or len(digits_only) > 15:
        return None
    return normalized


def _extract_visible_contacts(text: str) -> tuple[set[str], set[str]]:
    emails: set[str] = set()
    phones: set[str] = set()

    for match in EMAIL_REGEX.findall(text):
        normalized_email = _normalize_email(match)
        if normalized_email:
            emails.add(normalized_email)

    for match in PHONE_REGEX.findall(text):
        normalized_phone = _normalize_phone(match)
        if normalized_phone:
            phones.add(normalized_phone)

    return emails, phones

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
        "internal_links": set(), # Para buscar la página de "Contacto" si es necesario
        "form_detected": False,
    }
    
    # Title
    if soup.title and soup.title.string:
        metadata["title"] = soup.title.string.strip()
        
    # Meta Description
    meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if meta_desc and meta_desc.get("content"):
        metadata["description"] = meta_desc["content"].strip()

    # Detectar si la página tiene formulario visible
    metadata["form_detected"] = soup.find("form") is not None
        
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
            normalized_phone = _normalize_phone(href[4:])
            if normalized_phone:
                metadata["phones"].add(normalized_phone)
            
        # Enlaces a Redes Sociales o "Páginas de Contacto"
        elif any(social in href.lower() for social in ['linkedin.com', 'instagram.com', 'facebook.com', 'twitter.com']):
            normalized_social = _normalize_href(base_url, href)
            if normalized_social:
                metadata["social_links"].add(normalized_social)
            
        # Links internos (buscar 'contacto', 'about', 'nosotros')
        else:
            text = a_tag.get_text().lower()
            if hasattr(text, 'strip') and _looks_like_internal_key_page(text, href):
                normalized_link = _normalize_href(base_url, href)
                if normalized_link and _is_same_site(base_url, normalized_link):
                    metadata["internal_links"].add(normalized_link)

    # 2. Limpiar todo lo irrelevante para dejar puro texto listo para RegEx
    # Destruir scripts, estilos, svgs e imágenes
    for element in soup(["script", "style", "svg", "img", "noscript", "iframe", "header", "footer"]):
        element.decompose()
        
    # Obtener el texto que queda
    raw_text = soup.get_text(separator=' ', strip=True)
    
    # Limpiador Regex de espacios redundantes
    clean_text = re.sub(r'\s+', ' ', raw_text)

    visible_emails, visible_phones = _extract_visible_contacts(clean_text)
    metadata["emails"].update(visible_emails)
    metadata["phones"].update(visible_phones)
    
    # Convertir sets a listas para que sea JSON serializable
    metadata["emails"] = sorted(metadata["emails"])
    metadata["phones"] = sorted(metadata["phones"])
    metadata["social_links"] = sorted(metadata["social_links"])
    metadata["internal_links"] = sorted(metadata["internal_links"])
    
    return clean_text, metadata
