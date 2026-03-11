from __future__ import annotations

import re
import unicodedata
from typing import Any

TAXONOMY_TOP_LEVEL_VALUES = (
    "health",
    "legal",
    "finance",
    "real_estate",
    "retail",
    "food_hospitality",
    "beauty",
    "professional_services",
    "technology",
    "marketplace",
    "media",
    "association",
    "general_services",
    "unknown",
)
TAXONOMY_BUSINESS_TYPE_VALUES = (
    "dental_clinic",
    "medical_clinic",
    "veterinary_clinic",
    "beauty_salon",
    "law_firm",
    "accounting_firm",
    "financial_service",
    "real_estate_agency",
    "restaurant",
    "retail_store",
    "marketing_agency",
    "design_studio",
    "software_agency",
    "consultant_service",
    "professional_service",
    "local_business",
    "directory_listing",
    "aggregator_platform",
    "marketplace_platform",
    "media_publisher",
    "editorial_content",
    "association_org",
    "unknown",
)
TAXONOMY_DEFINITIONS = {
    "dental_clinic": {
        "top_level": "health",
        "display_niche": "Dental",
        "display_category": "Clinica dental",
        "keywords": (
            "dental clinic",
            "clinica dental",
            "dental",
            "dentist",
            "dentista",
            "ortodoncia",
            "implantes",
            "odontologia",
            "odontologia",
        ),
        "schema_types": {"dentalclinic", "dentist"},
    },
    "medical_clinic": {
        "top_level": "health",
        "display_niche": "Clinica",
        "display_category": "Clinica",
        "keywords": ("clinica", "clinic", "medical", "medico", "médico", "salud", "health", "doctor"),
        "schema_types": {"medicalbusiness", "medicalclinic", "physician"},
    },
    "veterinary_clinic": {
        "top_level": "health",
        "display_niche": "Veterinaria",
        "display_category": "Clinica veterinaria",
        "keywords": ("veterinaria", "veterinary", "vet", "mascotas", "pet clinic"),
        "schema_types": set(),
    },
    "beauty_salon": {
        "top_level": "beauty",
        "display_niche": "Belleza",
        "display_category": "Salon de belleza",
        "keywords": ("beauty", "belleza", "spa", "estetica", "estética", "salon", "salon de belleza"),
        "schema_types": {"beautysalon", "healthandbeautybusiness"},
    },
    "law_firm": {
        "top_level": "legal",
        "display_niche": "Legal",
        "display_category": "Estudio juridico",
        "keywords": ("abogado", "abogados", "legal", "law firm", "attorney", "bufete", "juridico", "jurídico"),
        "schema_types": {"attorney", "legalservice"},
    },
    "accounting_firm": {
        "top_level": "finance",
        "display_niche": "Contabilidad",
        "display_category": "Estudio contable",
        "keywords": ("accounting", "accountant", "contador", "contable", "bookkeeping"),
        "schema_types": {"accountingservice"},
    },
    "financial_service": {
        "top_level": "finance",
        "display_niche": "Finanzas",
        "display_category": "Servicio financiero",
        "keywords": ("financial", "finanzas", "seguros", "insurance", "investment", "credito", "crédito"),
        "schema_types": {"financialservice"},
    },
    "real_estate_agency": {
        "top_level": "real_estate",
        "display_niche": "Inmobiliaria",
        "display_category": "Agencia inmobiliaria",
        "keywords": ("real estate", "inmobiliaria", "propiedades", "realtor", "property"),
        "schema_types": {"realestateagent"},
    },
    "restaurant": {
        "top_level": "food_hospitality",
        "display_niche": "Restaurantes",
        "display_category": "Restaurante",
        "keywords": ("restaurant", "restaurante", "cafe", "cafeteria", "bar", "bistro", "menu"),
        "schema_types": set(),
    },
    "retail_store": {
        "top_level": "retail",
        "display_niche": "Retail",
        "display_category": "Tienda",
        "keywords": ("tienda", "store", "shop", "retail", "ecommerce", "e-commerce"),
        "schema_types": {"store"},
    },
    "marketing_agency": {
        "top_level": "professional_services",
        "display_niche": "Marketing",
        "display_category": "Agencia de marketing",
        "keywords": ("marketing agency", "agencia de marketing", "seo agency", "branding", "performance marketing", "paid media"),
        "schema_types": {"employmentagency"},
    },
    "design_studio": {
        "top_level": "professional_services",
        "display_niche": "Diseno",
        "display_category": "Estudio de diseno",
        "keywords": ("design studio", "estudio de diseno", "graphic design", "creative studio", "branding studio", "diseno grafico"),
        "schema_types": set(),
    },
    "software_agency": {
        "top_level": "technology",
        "display_niche": "Software",
        "display_category": "Agencia de desarrollo",
        "keywords": ("software agency", "web development", "desarrollo web", "app development", "software house", "digital product studio"),
        "schema_types": set(),
    },
    "consultant_service": {
        "top_level": "professional_services",
        "display_niche": "Consultoria",
        "display_category": "Consultoria",
        "keywords": ("consultor", "consultora", "consulting", "consultancy", "advisor", "asesoria", "asesoría"),
        "schema_types": set(),
    },
    "professional_service": {
        "top_level": "professional_services",
        "display_niche": "Servicios profesionales",
        "display_category": "Servicio profesional",
        "keywords": ("professional service", "servicios profesionales", "estudio", "agency", "agencia"),
        "schema_types": {"professionalservice", "organization"},
    },
    "local_business": {
        "top_level": "general_services",
        "display_niche": "Negocio local",
        "display_category": "Negocio local",
        "keywords": ("local business", "negocio local", "servicios", "empresa"),
        "schema_types": {"localbusiness", "homeandconstructionbusiness", "automotivbusiness"},
    },
    "directory_listing": {
        "top_level": "marketplace",
        "display_niche": "Directorio",
        "display_category": "Directorio",
        "keywords": ("directory", "directorio", "listado", "listing"),
        "schema_types": {"itemlist", "collectionpage", "searchresultspage"},
    },
    "aggregator_platform": {
        "top_level": "marketplace",
        "display_niche": "Comparador",
        "display_category": "Comparador",
        "keywords": ("comparador", "compare", "comparison", "ranking", "top 10", "reviews"),
        "schema_types": set(),
    },
    "marketplace_platform": {
        "top_level": "marketplace",
        "display_niche": "Marketplace",
        "display_category": "Marketplace",
        "keywords": ("marketplace", "vendors", "seller", "multiple providers"),
        "schema_types": set(),
    },
    "media_publisher": {
        "top_level": "media",
        "display_niche": "Media",
        "display_category": "Medio",
        "keywords": ("news", "magazine", "revista", "press", "publisher", "newsroom"),
        "schema_types": set(),
    },
    "editorial_content": {
        "top_level": "media",
        "display_niche": "Editorial",
        "display_category": "Articulo editorial",
        "keywords": ("blog", "article", "articulo", "post", "noticias"),
        "schema_types": {"article", "blogposting", "newsarticle", "reportagearticle"},
    },
    "association_org": {
        "top_level": "association",
        "display_niche": "Asociacion",
        "display_category": "Asociacion",
        "keywords": ("association", "asociacion", "asociación", "camara", "cámara", "federacion", "federación"),
        "schema_types": set(),
    },
    "unknown": {
        "top_level": "unknown",
        "display_niche": "Desconocido",
        "display_category": "Desconocido",
        "keywords": (),
        "schema_types": set(),
    },
}
ENTITY_TYPE_TAXONOMY_OVERRIDES = {
    "directory": "directory_listing",
    "aggregator": "aggregator_platform",
    "marketplace": "marketplace_platform",
    "media": "media_publisher",
    "blog_post": "editorial_content",
    "association": "association_org",
    "consultant": "consultant_service",
}
AGENCY_ENTITY_TYPE_HINTS = {
    "marketing_agency": ("marketing", "seo", "ads", "paid media", "growth"),
    "design_studio": ("design", "diseño", "diseno", "branding", "creative"),
    "software_agency": ("software", "development", "desarrollo", "app", "web"),
}


def _normalize_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = re.sub(r"\s+", " ", ascii_only.strip().lower())
    return lowered


def _structured_types(metadata: dict[str, Any] | None) -> set[str]:
    detected: set[str] = set()
    for node in (metadata or {}).get("structured_data", []):
        if not isinstance(node, dict):
            continue
        node_type = node.get("@type")
        if isinstance(node_type, list):
            detected.update(_normalize_text(value) for value in node_type if value)
        elif isinstance(node_type, str):
            detected.add(_normalize_text(node_type))
    return {value for value in detected if value}


def resolve_business_taxonomy(
    *,
    clean_text: str,
    metadata: dict[str, Any] | None = None,
    entity_type_detected: str | None = None,
    inferred_niche: str | None = None,
    category: str | None = None,
    target_niche: str | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    evidence: list[str] = []
    structured_types = _structured_types(metadata)
    searchable_text = " ".join(
        [
            inferred_niche or "",
            category or "",
            str(metadata.get("title") or ""),
            str(metadata.get("description") or ""),
            " ".join(str(link) for link in metadata.get("internal_links", [])[:8]),
            clean_text[:2400],
        ]
    )
    normalized_searchable = _normalize_text(searchable_text)

    scores = {business_type: 0 for business_type in TAXONOMY_BUSINESS_TYPE_VALUES}

    entity_type = _normalize_text(entity_type_detected)
    if entity_type in ENTITY_TYPE_TAXONOMY_OVERRIDES:
        business_type = ENTITY_TYPE_TAXONOMY_OVERRIDES[entity_type]
        scores[business_type] += 10
        evidence.append(f"entity_type:{entity_type}")
    elif entity_type == "agency":
        matched_agency_type = None
        for candidate, keywords in AGENCY_ENTITY_TYPE_HINTS.items():
            if any(_normalize_text(keyword) in normalized_searchable for keyword in keywords):
                matched_agency_type = candidate
                evidence.append(f"agency_hint:{candidate}")
                break
        scores[matched_agency_type or "professional_service"] += 8
    elif entity_type == "direct_business":
        scores["local_business"] += 3
        evidence.append("entity_type:direct_business")

    for business_type, definition in TAXONOMY_DEFINITIONS.items():
        if business_type == "unknown":
            continue
        schema_matches = structured_types & definition["schema_types"]
        if schema_matches:
            scores[business_type] += 7
            evidence.append(f"schema:{business_type}:{sorted(schema_matches)[0]}")
        keyword_matches = [
            keyword
            for keyword in definition["keywords"]
            if _normalize_text(keyword) and _normalize_text(keyword) in normalized_searchable
        ]
        if keyword_matches:
            scores[business_type] += min(len(keyword_matches), 3) * 2
            evidence.append(f"keyword:{business_type}:{_normalize_text(keyword_matches[0])}")

    best_type = max(scores.items(), key=lambda item: item[1])[0]
    best_score = scores[best_type]
    if best_score < 3:
        best_type = "unknown"

    definition = TAXONOMY_DEFINITIONS[best_type]
    normalized_inferred_niche = str(definition["display_niche"])
    return {
        "taxonomy_top_level": str(definition["top_level"]),
        "taxonomy_business_type": best_type,
        "inferred_niche": normalized_inferred_niche if best_type != "unknown" else (str(inferred_niche).strip() or "Desconocido"),
        "display_category": str(definition["display_category"]),
        "taxonomy_evidence": evidence[:6],
    }
