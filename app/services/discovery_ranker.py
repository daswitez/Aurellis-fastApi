from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

BLOCKED_DOMAIN_TOKENS = [
    "mercadolibre",
    "bing.com",
    "duckduckgo.com",
    "search.yahoo.com",
    "youtube",
    "reddit.com",
    "redd.it",
    "twitter",
    "x.com",
    "whatsapp.com",
    "web.whatsapp.com",
    "infoisinfo",
    "habitissimo",
    "foursquare",
    "google.com",
    "googleusercontent",
    "dafont.com",
    "pinterest.com",
    "github.com",
    "fiverr.com",
]
REFERENCE_DOMAIN_TOKENS = [
    "wikipedia.org",
    "wiktionary.org",
    "ecured.cu",
    "zhidao.baidu.com",
    "baike.baidu.com",
    "quora.com",
    "fandom.com",
    "wikia.com",
    "concepto.de",
    "dle.rae.es",
    "rae.es",
    "britannica.com",
    "dictionary.com",
    "infoescola.com",
    "statista.com",
    "mordorintelligence.com",
    "verywellhealth.com",
    "verywellmind.com",
    "verywellfit.com",
    "zhihu.com",
]
MEDIA_NEWS_DOMAIN_TOKENS = [
    "marketwatch.com",
    "forbes.com",
    "bloomberg.com",
    "cnn.com",
    "elpais.com",
    "expansion.com",
    "exame.com",
]
FINANCE_DOMAIN_TOKENS = [
    "marketwatch.com",
    "investing.com",
    "finance.yahoo.com",
    "yahoo.com/finance",
    "morningstar.",
    "tradingview.com",
]
LARGE_ENTERPRISE_DOMAIN_TOKENS = [
    "amazon.",
    "microsoft.",
    "meta.com",
    "apple.com",
    "ibm.com",
    "salesforce.com",
    "hubspot.com",
    "adobe.com",
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
    "/historia/",
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
    "/wiki/",
    "/question/",
    "/questions/",
    "/pregunta/",
    "/que-es",
    "/que-es-",
    "/como-funciona",
    "/como-funciona-",
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
    "que es",
    "qué es",
    "como funciona",
    "cómo funciona",
    "para que sirve",
    "para qué sirve",
    "estadisticas",
    "estadísticas",
    "mejores",
    "top ",
    "lista de",
    "enciclopedia",
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
SOCIAL_POST_PATH_PATTERNS = (
    "/p/",
    "/reel/",
    "/reels/",
    "/tv/",
    "/explore/",
    "/hashtag/",
    "/share",
    "/video/",
    "/photo/",
)
SOCIAL_NOISE_QUERY_TOKENS = ("?hl=", "/share?", "sharer.php", "/intent/")
SOCIAL_PROFILE_HINTS = (
    "link in bio",
    "dm",
    "escribeme",
    "escríbeme",
    "agenda",
    "book",
    "consulta",
    "servicios",
    "services",
    "shop",
)
COMMERCIAL_HINTS = (
    "coach",
    "coaches",
    "marca personal",
    "ecommerce",
    "tienda online",
    "agencia",
    "estudio",
    "editor",
    "filmmaker",
    "creator",
    "creador",
    "curso",
    "infoproducto",
)
REFERENCE_TOKENS = (
    "wiki",
    "wikipedia",
    "q&a",
    "preguntas y respuestas",
    "preguntas",
    "respuestas",
    "foro",
    "forum",
    "knowledge base",
    "base de conocimiento",
    "ecured",
    "zhidao",
    "enciclopedia",
    "definicion",
    "definición",
    "concepto",
    "meaning",
    "definition",
)
SEARCH_UTILITY_PATH_TOKENS = (
    "/images/feed",
    "/images/search",
    "/images/",
    "/search",
)
SEARCH_UTILITY_TOKENS = (
    "bing images",
    "imagenes de bing",
    "imágenes de bing",
    "image search",
    "wallpaper",
    "fondos de pantalla",
)
QUIZ_TRIVIA_TOKENS = (
    " quiz ",
    " trivia ",
    "entertainment quiz",
    "daily quiz",
    "microsoft rewards",
)
LARGE_ENTERPRISE_TOKENS = (
    "fortune 500",
    "nasdaq",
    "nyse",
    "earnings",
    "investor relations",
)
BINARY_DOCUMENT_PATH_SUFFIXES = (
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".rar",
    ".7z",
)
AUTH_HELP_TITLE_TOKENS = (
    "sign up",
    "signup",
    "log in",
    "login",
    "welcome to",
    "help center",
    "help center",
)


def clean_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def is_blocked_result(url: str, allow_social_profiles: bool = False) -> str | None:
    lowered_url = url.lower()
    path = urlparse(url).path.lower()
    if any(path.endswith(suffix) for suffix in BINARY_DOCUMENT_PATH_SUFFIXES):
        return "blocked_binary_document"
    for blocked_token in BLOCKED_DOMAIN_TOKENS:
        if allow_social_profiles and blocked_token in {"facebook", "instagram", "tiktok", "linkedin"}:
            continue
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


def _is_social_domain(url: str) -> bool:
    lowered_url = url.lower()
    return any(token in lowered_url for token in SOCIAL_DOMAIN_TOKENS)


def _is_canonical_social_profile(url: str) -> tuple[bool, str | None, str | None]:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.strip("/")
    segments = [segment for segment in path.split("/") if segment]

    if "instagram.com" in host:
        if not segments or len(segments) != 1:
            return False, "instagram", None
        handle = segments[0]
        if handle.startswith(("p", "reel", "reels", "explore", "stories")):
            return False, "instagram", None
        return True, "instagram", handle.lstrip("@")

    if "tiktok.com" in host:
        if len(segments) != 1 or not segments[0].startswith("@"):
            return False, "tiktok", None
        return True, "tiktok", segments[0].lstrip("@")

    return False, None, None


def _looks_like_social_post(url: str) -> bool:
    lowered_url = url.lower()
    return any(token in lowered_url for token in [*SOCIAL_POST_PATH_PATTERNS, *SOCIAL_NOISE_QUERY_TOKENS])


def _looks_like_reference_page(url: str, title: str, snippet: str) -> bool:
    lowered_blob = f"{title} {snippet}".lower()
    host = urlparse(url).netloc.lower()
    return (
        any(token in host for token in REFERENCE_DOMAIN_TOKENS)
        or any(token in lowered_blob for token in REFERENCE_TOKENS)
    )


def _looks_like_search_utility(url: str, title: str, snippet: str) -> bool:
    lowered_blob = f"{title} {snippet}".lower()
    path = urlparse(url).path.lower()
    return any(token in path for token in SEARCH_UTILITY_PATH_TOKENS) or any(
        token in lowered_blob for token in SEARCH_UTILITY_TOKENS
    )


def _looks_like_auth_or_help_page(url: str, title: str, snippet: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    lowered_blob = f"{title} {snippet}".lower()
    return (
        host.startswith(("accounts.", "help.", "support."))
        or "shopify.com" in host
        or any(token in path for token in ("/account", "/accounts", "/login", "/signup", "/help", "/support"))
        or any(token in lowered_blob for token in AUTH_HELP_TITLE_TOKENS)
    )


def _looks_like_quiz_or_trivia(title: str, snippet: str) -> bool:
    lowered_blob = f" {title} {snippet} ".lower()
    return any(token in lowered_blob for token in QUIZ_TRIVIA_TOKENS)


def _looks_like_editorial_article(url: str, title: str, snippet: str) -> bool:
    lowered_blob = f"{title} {snippet}".lower()
    path = urlparse(url).path.lower()
    return any(token in path for token in EDITORIAL_PATH_TOKENS) or any(token in lowered_blob for token in EDITORIAL_TITLE_TOKENS)


def _looks_like_media_or_finance(url: str, title: str, snippet: str) -> bool:
    lowered_blob = f"{title} {snippet}".lower()
    host = urlparse(url).netloc.lower()
    return any(token in host for token in [*MEDIA_NEWS_DOMAIN_TOKENS, *FINANCE_DOMAIN_TOKENS]) or any(
        token in lowered_blob for token in LARGE_ENTERPRISE_TOKENS
    )


def _looks_like_large_enterprise_noise(url: str, title: str, snippet: str) -> bool:
    lowered_blob = f"{title} {snippet}".lower()
    host = urlparse(url).netloc.lower()
    return any(token in host for token in LARGE_ENTERPRISE_DOMAIN_TOKENS) or any(
        token in lowered_blob for token in LARGE_ENTERPRISE_TOKENS
    )


def looks_like_social_or_marketplace(url: str, allow_social_profiles: bool = False) -> bool:
    lowered_url = url.lower()
    tokens_to_check = SOCIAL_DOMAIN_TOKENS + BLOCKED_DOMAIN_TOKENS
    if allow_social_profiles:
        tokens_to_check = [
            token
            for token in tokens_to_check
            if token not in SOCIAL_DOMAIN_TOKENS and token not in {"facebook", "instagram", "tiktok", "linkedin", "twitter", "x.com"}
        ]
    return any(token in lowered_url for token in tokens_to_check)


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


def classify_discovery_candidate(
    url: str,
    title: str,
    snippet: str,
    *,
    allow_social_profiles: bool = False,
) -> dict[str, Any]:
    lowered_blob = f"{title} {snippet}".lower()
    path = urlparse(url).path.lower()
    title_tokens = extract_brand_tokens(title)
    url_tokens = domain_brand_tokens(url)
    reasons: list[str] = []
    blocked_reason = is_blocked_result(url, allow_social_profiles=allow_social_profiles)

    if blocked_reason:
        return {
            "result_kind": "website_home" if path in {"", "/"} else "website_inner_page",
            "website_result_score": -0.5,
            "social_profile_score": 0.0,
            "score": -0.5,
            "reasons": [blocked_reason],
            "exclusion_reason": blocked_reason,
        }

    if _looks_like_reference_page(url, title, snippet):
        return {
            "result_kind": "article_or_reference",
            "website_result_score": 0.0,
            "social_profile_score": 0.0,
            "score": 0.0,
            "reasons": ["reference_or_article"],
            "exclusion_reason": "excluded_reference_page",
        }

    if _looks_like_search_utility(url, title, snippet):
        return {
            "result_kind": "search_utility",
            "website_result_score": 0.0,
            "social_profile_score": 0.0,
            "score": 0.0,
            "reasons": ["search_utility_noise"],
            "exclusion_reason": "excluded_reference_page",
        }

    if _looks_like_auth_or_help_page(url, title, snippet):
        return {
            "result_kind": "website_inner_page",
            "website_result_score": 0.0,
            "social_profile_score": 0.0,
            "score": 0.0,
            "reasons": ["auth_or_help_page"],
            "exclusion_reason": "excluded_auth_or_help_page",
        }

    if _looks_like_quiz_or_trivia(title, snippet):
        return {
            "result_kind": "article_or_reference",
            "website_result_score": 0.0,
            "social_profile_score": 0.0,
            "score": 0.0,
            "reasons": ["quiz_or_trivia_noise"],
            "exclusion_reason": "excluded_reference_page",
        }

    if _looks_like_editorial_article(url, title, snippet):
        return {
            "result_kind": "article_or_reference",
            "website_result_score": 0.0,
            "social_profile_score": 0.0,
            "score": 0.0,
            "reasons": ["editorial_path" if any(token in path for token in EDITORIAL_PATH_TOKENS) else "editorial_title"],
            "exclusion_reason": "excluded_as_article",
        }

    if _looks_like_media_or_finance(url, title, snippet):
        return {
            "result_kind": "media_or_news",
            "website_result_score": 0.0,
            "social_profile_score": 0.0,
            "score": 0.0,
            "reasons": ["media_or_finance"],
            "exclusion_reason": "excluded_reference_page",
        }

    if _looks_like_large_enterprise_noise(url, title, snippet):
        return {
            "result_kind": "large_enterprise_noise",
            "website_result_score": 0.0,
            "social_profile_score": 0.0,
            "score": 0.0,
            "reasons": ["large_enterprise_noise"],
            "exclusion_reason": "excluded_large_enterprise",
        }

    if _is_social_domain(url):
        if not allow_social_profiles:
            return {
                "result_kind": "social_profile",
                "website_result_score": 0.0,
                "social_profile_score": 0.0,
                "score": 0.0,
                "reasons": ["social_profiles_not_allowed"],
                "exclusion_reason": "blocked_domain:social_profile",
            }
        if _looks_like_social_post(url):
            return {
                "result_kind": "social_post",
                "website_result_score": 0.0,
                "social_profile_score": 0.0,
                "score": 0.0,
                "reasons": ["social_post_or_share"],
                "exclusion_reason": "excluded_social_post",
            }

        is_profile, platform, handle = _is_canonical_social_profile(url)
        if not is_profile:
            return {
                "result_kind": "social_post",
                "website_result_score": 0.0,
                "social_profile_score": 0.0,
                "score": 0.0,
                "reasons": ["non_canonical_social_profile"],
                "exclusion_reason": "excluded_social_post",
            }

        social_score = 0.35
        reasons.extend(["social_profile_candidate", f"platform:{platform}"])
        if handle:
            social_score += 0.2
            reasons.append("canonical_handle_detected")
        if any(token in lowered_blob for token in SOCIAL_PROFILE_HINTS):
            social_score += 0.2
            reasons.append("social_commercial_cta_hint")
        if any(token in lowered_blob for token in COMMERCIAL_HINTS):
            social_score += 0.15
            reasons.append("social_commercial_niche_hint")
        if title and len(title.split()) <= 12:
            social_score += 0.05
            reasons.append("concise_title")

        return {
            "result_kind": "social_profile",
            "website_result_score": 0.0,
            "social_profile_score": round(min(social_score, 1.0), 4),
            "score": round(min(social_score, 1.0), 4),
            "reasons": reasons,
            "exclusion_reason": None,
        }

    website_score = 0.0
    positive_rules = [
        ("official_site_hint", 0.35, ["oficial", "official", "sitio oficial"]),
        ("contact_or_services_hint", 0.18, ["contacto", "contact", "servicios", "services", "nosotros", "about"]),
        ("conversion_cta_hint", 0.18, ["reserva", "booking", "agenda", "cotiza", "quote"]),
        ("business_category_hint", 0.12, ["clinica", "clínica", "estudio", "agencia", "tienda", "retail", "consultora"]),
        ("commercial_hint", 0.14, COMMERCIAL_HINTS),
    ]
    negative_rules = [
        ("product_page", -0.35, PRODUCT_PAGE_PATH_TOKENS + PRODUCT_PAGE_TOKENS),
        ("institutional_page", -0.25, INSTITUTIONAL_TOKENS),
        ("marketplace_or_listing", -0.25, ["marketplace", "listing", "directory", "directorio"]),
    ]

    for reason, delta, tokens in positive_rules:
        if any(token in lowered_blob for token in tokens):
            website_score += delta
            reasons.append(reason)

    for reason, delta, tokens in negative_rules:
        if any(token in lowered_blob or token in path for token in tokens):
            website_score += delta
            reasons.append(reason)

    depth = len([segment for segment in path.split("/") if segment])
    if depth <= 1:
        website_score += 0.12
        reasons.append("shallow_url")
    elif depth == 2:
        website_score += 0.04
        reasons.append("moderate_depth")
    else:
        website_score -= 0.18
        reasons.append("deep_url")

    if path.endswith(".html") or path.endswith(".php"):
        website_score -= 0.05
        reasons.append("document_like_path")

    if title and len(title.split()) <= 10:
        website_score += 0.08
        reasons.append("concise_title")

    if url_tokens and title_tokens and url_tokens & title_tokens:
        website_score += 0.22
        reasons.append("brand_domain_match")
    if path in {"", "/"}:
        website_score += 0.08
        reasons.append("root_domain_url")
    if get_directory_seed_token(url):
        website_score -= 0.2
        reasons.append("directory_seed_candidate")

    result_kind = "website_home" if path in {"", "/"} else "website_inner_page"
    exclusion_reason = None
    if "product_page" in reasons:
        exclusion_reason = "excluded_as_product_page"
    elif website_score < 0.15:
        exclusion_reason = "low_business_likeness"

    return {
        "result_kind": result_kind,
        "website_result_score": round(website_score, 4),
        "social_profile_score": 0.0,
        "score": round(website_score, 4),
        "reasons": reasons,
        "exclusion_reason": exclusion_reason,
    }


def score_business_likeness(
    url: str,
    title: str,
    snippet: str,
    allow_social_profiles: bool = False,
) -> tuple[float, list[str], str | None]:
    classified = classify_discovery_candidate(
        url,
        title,
        snippet,
        allow_social_profiles=allow_social_profiles,
    )
    return classified["score"], classified["reasons"], classified["exclusion_reason"]
