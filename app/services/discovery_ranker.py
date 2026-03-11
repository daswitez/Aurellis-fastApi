from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

BLOCKED_DOMAIN_TOKENS = [
    "mercadolibre",
    "linkedin",
    "facebook",
    "instagram",
    "tiktok",
    "youtube",
    "twitter",
    "x.com",
    "infoisinfo",
    "habitissimo",
    "foursquare",
    "google.com",
    "googleusercontent",
]
DIRECTORY_SEED_DOMAIN_TOKENS = [
    "doctoralia",
    "topdoctors",
    "paginasamarillas",
    "guiatelefonica",
    "yellowpages",
    "yelp",
    "tripadvisor",
]
SOCIAL_DOMAIN_TOKENS = [
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "youtube.com",
    "twitter.com",
    "x.com",
]
DIRECTORY_CTA_HINTS = [
    "sitio web",
    "website",
    "web oficial",
    "official site",
    "pagina web",
    "página web",
    "visitar web",
    "visitar sitio",
    "homepage",
]
EDITORIAL_PATH_TOKENS = [
    "/blog/",
    "/ideas/",
    "/noticias/",
    "/news/",
    "/prensa/",
    "/press/",
    "/categories/",
    "/category/",
    "/guia/",
    "/guía/",
    "/article/",
    "/articulo/",
    "/artículos/",
    "/informe",
    "/informes/",
    "/report/",
    "/reports/",
    "/study/",
    "/studies/",
    "/insights/",
    "/tag/",
]
EDITORIAL_TITLE_TOKENS = [
    "100 ideas",
    "ideas de negocio",
    "qué vender",
    "que vender",
    "guia",
    "guía",
    "categorías",
    "categories",
    "tendencias",
    "informe",
    "informes",
    "report",
    "reports",
    "estudio",
    "estudios",
    "prensa",
    "press",
    "newsroom",
    "estadisticas",
    "estadísticas",
    "mejores",
    "top ",
    "lista de",
]
PRODUCT_PAGE_PATH_TOKENS = [
    "/product/",
    "/products/",
    "/producto/",
    "/productos/",
]
PRODUCT_PAGE_TOKENS = [
    "añadir al carrito",
    "anadir al carrito",
    "carrito",
    "sku",
    "referencia",
    "serie completa",
    "distribuidor oficial",
    "catalogo",
    "catálogo",
]
INSTITUTIONAL_TOKENS = [
    "ministerio",
    "gobierno",
    "ayuntamiento",
    "diputacion",
    "diputación",
    "comision nacional",
    "comisión nacional",
    "federacion",
    "federación",
    "fundacion",
    "fundación",
    "universidad",
]


def clean_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def is_blocked_result(url: str) -> str | None:
    lowered_url = url.lower()
    for blocked_token in BLOCKED_DOMAIN_TOKENS:
        if blocked_token in lowered_url:
            return f"blocked_domain:{blocked_token}"
    return None


def get_directory_seed_token(url: str) -> str | None:
    lowered_url = url.lower()
    for token in DIRECTORY_SEED_DOMAIN_TOKENS:
        if token in lowered_url:
            return token
    return None


def extract_brand_tokens(value: str) -> set[str]:
    cleaned = "".join(char.lower() if char.isalnum() else " " for char in value)
    return {
        token
        for token in cleaned.split()
        if len(token) >= 4 and token not in {"http", "https", "www", "site", "oficial", "official", "contacto", "contact"}
    }


def domain_brand_tokens(url: str) -> set[str]:
    hostname = urlparse(url).netloc.lower().removeprefix("www.")
    primary = hostname.split(":")[0].split(".")[0]
    return extract_brand_tokens(primary)


def is_same_root_domain(left_url: str, right_url: str) -> bool:
    left_parts = urlparse(left_url).netloc.lower().removeprefix("www.").split(".")
    right_parts = urlparse(right_url).netloc.lower().removeprefix("www.").split(".")
    return len(left_parts) >= 2 and len(right_parts) >= 2 and left_parts[-2:] == right_parts[-2:]


def looks_like_social_or_marketplace(url: str) -> bool:
    lowered_url = url.lower()
    return any(token in lowered_url for token in SOCIAL_DOMAIN_TOKENS + BLOCKED_DOMAIN_TOKENS)


def score_directory_official_link(seed_url: str, candidate_url: str, anchor_text: str) -> float:
    score = 0.0
    lowered_anchor = anchor_text.lower()
    if any(hint in lowered_anchor for hint in DIRECTORY_CTA_HINTS):
        score += 0.45
    if urlparse(candidate_url).path in {"", "/"}:
        score += 0.2
    if not looks_like_social_or_marketplace(candidate_url):
        score += 0.15
    if not is_same_root_domain(seed_url, candidate_url):
        score += 0.15
    if len(urlparse(candidate_url).path.split("/")) <= 2:
        score += 0.05
    return round(score, 4)


def extract_official_site_from_seed_html(seed_url: str, html: str) -> tuple[str | None, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    best_url: str | None = None
    best_score = 0.0
    best_reasons: list[str] = []

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not href:
            continue
        candidate_url = urljoin(seed_url, href)
        if not candidate_url.startswith("http"):
            continue
        if is_same_root_domain(seed_url, candidate_url):
            continue
        if looks_like_social_or_marketplace(candidate_url):
            continue

        anchor_text = " ".join(link.get_text(" ", strip=True).split())
        score = score_directory_official_link(seed_url, candidate_url, anchor_text)
        reasons: list[str] = ["directory_seed_resolved"]
        if any(hint in anchor_text.lower() for hint in DIRECTORY_CTA_HINTS):
            reasons.append("official_link_label")
        if urlparse(candidate_url).path in {"", "/"}:
            reasons.append("root_domain_candidate")

        if score > best_score:
            best_url = candidate_url
            best_score = score
            best_reasons = reasons

    if best_url and best_score >= 0.45:
        return best_url, best_reasons
    return None, ["directory_seed_without_official_site"]


def score_business_likeness(url: str, title: str, snippet: str) -> tuple[float, list[str], str | None]:
    score = 0.0
    reasons: list[str] = []
    lowered_blob = f"{title} {snippet}".lower()
    path = urlparse(url).path.lower()
    title_tokens = extract_brand_tokens(title)
    url_tokens = domain_brand_tokens(url)

    positive_rules = [
        ("official_site_hint", 0.35, ["oficial", "official", "sitio oficial"]),
        ("contact_or_services_hint", 0.18, ["contacto", "contact", "servicios", "services", "nosotros", "about"]),
        ("conversion_cta_hint", 0.18, ["reserva", "booking", "agenda", "cotiza", "quote"]),
        ("business_category_hint", 0.12, ["clinica", "clínica", "estudio", "agencia", "tienda", "retail", "consultora"]),
    ]
    negative_rules = [
        ("editorial_path", -0.35, EDITORIAL_PATH_TOKENS),
        ("editorial_title", -0.28, EDITORIAL_TITLE_TOKENS),
        ("product_page", -0.35, PRODUCT_PAGE_PATH_TOKENS + PRODUCT_PAGE_TOKENS),
        ("institutional_page", -0.25, INSTITUTIONAL_TOKENS),
        ("marketplace_or_listing", -0.25, ["marketplace", "listing", "directory", "directorio"]),
    ]

    for reason, delta, tokens in positive_rules:
        if any(token in lowered_blob for token in tokens):
            score += delta
            reasons.append(reason)

    for reason, delta, tokens in negative_rules:
        if any(token in lowered_blob or token in path for token in tokens):
            score += delta
            reasons.append(reason)

    depth = len([segment for segment in path.split("/") if segment])
    if depth <= 1:
        score += 0.12
        reasons.append("shallow_url")
    elif depth >= 3:
        score -= 0.15
        reasons.append("deep_url")

    if path.endswith(".html") or path.endswith(".php"):
        score -= 0.05
        reasons.append("document_like_path")

    if title and len(title.split()) <= 10:
        score += 0.08
        reasons.append("concise_title")

    if url_tokens and title_tokens and url_tokens & title_tokens:
        score += 0.22
        reasons.append("brand_domain_match")
    if path in {"", "/"}:
        score += 0.08
        reasons.append("root_domain_url")
    if get_directory_seed_token(url):
        score -= 0.2
        reasons.append("directory_seed_candidate")

    exclusion_reason = None
    if "product_page" in reasons:
        exclusion_reason = "excluded_as_product_page"
    elif any(reason in reasons for reason in {"editorial_path", "editorial_title"}):
        exclusion_reason = "excluded_as_article"
    elif score < 0.15:
        exclusion_reason = "low_business_likeness"

    return round(score, 4), reasons, exclusion_reason
