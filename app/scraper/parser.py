import json
import re
from typing import Any, Dict, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from app.services.identity_resolution import (
    classify_surface as classify_identity_surface,
    detect_platform as detect_social_platform,
    extract_social_handle as extract_canonical_social_handle,
    normalize_social_profile_url,
)


INTERNAL_LINK_KEYWORDS = [
    "contact",
    "contacto",
    "about",
    "nosotros",
    "equipo",
    "careers",
    "trabajo",
    "empleo",
    "services",
    "servicios",
    "pricing",
    "precios",
    "book",
    "booking",
    "reserv",
    "locations",
    "ubicaciones",
]
EMAIL_REGEX = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
PHONE_REGEX = re.compile(r"(?:(?:\+|00)\d{1,3}[\s\-./]?)?(?:\(?\d{2,4}\)?[\s\-./]?){2,5}\d{2,4}")
EMAIL_BLOCKLIST_TOKENS = {"example.com", "yourdomain", "domain.com", "email.com", "test.com", "localhost"}
ADDRESS_HINT_REGEX = re.compile(
    r"((?<![a-z])(?:calle|av(?:\.|enida)?|street|st\.|road|rd\.|plaza|paseo|carrera|camino)\s+[^|]{8,120})",
    re.IGNORECASE,
)
ADDRESS_CONFIRMATION_HINTS = (
    " argentina",
    " madrid",
    " mexico",
    " méxico",
    " españa",
    " spain",
    " buenos aires",
    " barcelona",
    " valencia",
    " cdmx",
    " ciudad de mexico",
    " ciudad de méxico",
)
JSON_LD_TYPES_OF_INTEREST = {
    "localbusiness",
    "organization",
    "medicalbusiness",
    "dentist",
    "physician",
    "attorney",
    "store",
    "postaladdress",
}
CTA_PATTERNS = {
    "booking": ["book", "booking", "reserve", "reservar", "reserva", "agenda", "agendar", "cita"],
    "contact_form": ["contact", "contacto", "habla", "hablemos", "escribenos", "escríbenos"],
    "whatsapp": ["whatsapp", "wa.me", "api.whatsapp.com"],
    "call": ["call", "llamar", "telefono", "teléfono"],
    "quote": ["quote", "cotiza", "cotizar", "presupuesto"],
    "signup": ["signup", "sign up", "registrate", "regístrate", "suscribete", "suscríbete"],
}
REFERENCE_PAGE_HINTS = (
    "enciclopedia",
    "definicion",
    "definición",
    "concepto",
    "wikipedia",
    "diccionario",
)
SOCIAL_PLATFORMS = {
    "instagram": ["instagram.com"],
    "tiktok": ["tiktok.com"],
    "linkedin": ["linkedin.com"],
    "facebook": ["facebook.com"],
    "twitter": ["twitter.com", "x.com"],
}
SOCIAL_HANDLE_REGEX = re.compile(r"^@?[a-z0-9._]{2,64}$", re.IGNORECASE)
EXTERNAL_BOOKING_HINTS = (
    "cal.com",
    "calendly.com",
    "booksy.com",
    "simplybook.me",
    "setmore.com",
    "acuityscheduling.com",
    "appointments",
    "booking",
    "book",
    "agenda",
    "reserv",
    "cita",
)


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


def _looks_like_date_digits(digits_only: str) -> bool:
    if len(digits_only) != 8 or not digits_only.isdigit():
        return False

    day = int(digits_only[:2])
    month = int(digits_only[2:4])
    year = int(digits_only[4:])
    if 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100:
        return True

    year = int(digits_only[:4])
    month = int(digits_only[4:6])
    day = int(digits_only[6:])
    return 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31


def _looks_like_sequence_noise(digits_only: str) -> bool:
    if len(set(digits_only)) == 1:
        return True

    ascending = "01234567890"
    descending = "09876543210"
    return digits_only in ascending or digits_only in descending


def _classify_phone_candidate(candidate: str) -> tuple[str | None, str | None]:
    normalized = re.sub(r"[^\d+]", "", candidate.strip())
    if normalized.startswith("00"):
        normalized = f"+{normalized[2:]}"
    if normalized.count("+") > 1 or ("+" in normalized and not normalized.startswith("+")):
        return None, "invalid_plus_format"

    digits_only = re.sub(r"\D", "", normalized)
    if len(digits_only) < 7 or len(digits_only) > 15:
        return None, "invalid_length"
    if _looks_like_date_digits(digits_only):
        return None, "date_like"
    if _looks_like_timestamp_noise(candidate, digits_only):
        return None, "timestamp_like"
    if _looks_like_metric_noise(candidate, digits_only):
        return None, "metric_like"
    if _looks_like_sequence_noise(digits_only):
        return None, "sequence_noise"
    return normalized, None


def _normalize_phone(candidate: str) -> str | None:
    return _classify_phone_candidate(candidate)[0]


def _looks_like_timestamp_noise(candidate: str, digits_only: str) -> bool:
    lowered = candidate.lower().strip()
    if ":" in lowered and len(digits_only) <= 8:
        return True
    if re.search(r"\b\d{1,2}:\d{2}\b", lowered):
        return True
    return False


def _looks_like_metric_noise(candidate: str, digits_only: str) -> bool:
    lowered = candidate.lower()
    metric_hints = ("followers", "likes", "views", "seguidores", "vistas", "likes", "k", "m")
    if any(hint in lowered for hint in metric_hints):
        return True
    return len(digits_only) <= 10 and digits_only.startswith(("19", "20")) and len(digits_only) in {8, 10}


def _detect_platform(url: str) -> str | None:
    return detect_social_platform(url)


def _extract_social_handle(url: str) -> tuple[str | None, str | None]:
    platform, handle = extract_canonical_social_handle(url)
    if handle and not SOCIAL_HANDLE_REGEX.match(handle):
        return platform, None
    return platform, handle


def _build_social_profile_record(url: str, *, is_primary: bool = False) -> dict[str, Any] | None:
    surface = classify_identity_surface(url)
    if not surface or surface.get("surface_type") != "social_profile":
        return None
    platform = str(surface.get("platform") or "").strip().lower()
    handle = str(surface.get("handle") or "").strip()
    canonical_url = normalize_social_profile_url(url) or str(surface.get("url") or url)
    return {
        "platform": platform,
        "url": canonical_url,
        "handle": handle,
        "is_primary": is_primary,
        "profile_kind": "profile",
        "contact_signals": [],
        "activity_signals": [],
        "confidence": "high",
    }


def _looks_like_reference_page(base_url: str, title: str, description: str) -> bool:
    lowered_blob = f"{base_url} {title} {description}".lower()
    return any(token in lowered_blob for token in REFERENCE_PAGE_HINTS)


def _extract_social_profile_metadata(
    soup: BeautifulSoup,
    base_url: str,
    clean_text: str,
    metadata: Dict[str, Any],
) -> dict[str, Any] | None:
    platform, handle = _extract_social_handle(base_url)
    if platform not in {"instagram", "tiktok"} or not handle:
        return None

    title = metadata.get("title") or ""
    description = metadata.get("description") or ""
    meta_site_name = soup.find("meta", attrs={"property": "og:site_name"})
    bio = description
    display_name = title.split("|")[0].split("(")[0].strip() if title else handle or platform
    if meta_site_name and meta_site_name.get("content"):
        display_name = display_name or meta_site_name["content"].strip()

    external_links: list[str] = []
    platform_ctas: list[str] = []
    offer_signals: list[str] = []
    activity_signals: list[str] = []
    audience_signals: list[str] = []

    lowered_text = clean_text.lower()
    if any(token in lowered_text for token in ["link in bio", "linktree", "agenda", "dm", "mensaje"]):
        platform_ctas.append("profile_cta_visible")
    if any(token in lowered_text for token in ["curso", "coaching", "servicios", "editor", "filmmaker", "agencia", "ecommerce", "shop"]):
        offer_signals.append("commercial_offer_detected")
    if any(token in lowered_text for token in ["reels", "shorts", "contenido", "videos", "ugc"]):
        activity_signals.append("content_format_visible")
    if any(token in lowered_text for token in ["clientes", "marcas", "founder", "ceo", "coach"]):
        audience_signals.append("buyer_audience_visible")

    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "").strip()
        normalized_href = _normalize_href(base_url, href)
        if not normalized_href:
            continue
        if _detect_platform(normalized_href):
            continue
        if normalized_href.startswith("http"):
            external_links.append(normalized_href)

    deduped_external_links: list[str] = []
    for link in external_links:
        if link not in deduped_external_links:
            deduped_external_links.append(link)

    return {
        "platform": platform,
        "handle": handle,
        "display_name": display_name or handle,
        "bio": bio,
        "external_links": deduped_external_links[:5],
        "platform_ctas": platform_ctas,
        "offer_signals": offer_signals,
        "activity_signals": activity_signals,
        "audience_signals": audience_signals,
        "content_text": clean_text[:1500],
    }


def _extract_visible_contacts(text: str) -> tuple[set[str], set[str], dict[str, int]]:
    emails: set[str] = set()
    phones: set[str] = set()
    phone_validation_rejections: dict[str, int] = {}

    for match in EMAIL_REGEX.findall(text):
        normalized_email = _normalize_email(match)
        if normalized_email:
            emails.add(normalized_email)

    for match in PHONE_REGEX.findall(text):
        normalized_phone, rejection_reason = _classify_phone_candidate(match)
        if normalized_phone:
            phones.add(normalized_phone)
        elif rejection_reason:
            phone_validation_rejections[rejection_reason] = phone_validation_rejections.get(rejection_reason, 0) + 1

    return emails, phones, phone_validation_rejections


def _append_contact_channel(
    channels: list[dict[str, str]],
    *,
    channel_type: str,
    value: str | None,
    source: str,
) -> None:
    normalized_value = " ".join((value or "").strip().split())
    if not normalized_value:
        return
    channels.append({"type": channel_type, "value": normalized_value, "source": source})


def _add_unique(container: list[str], value: str | None, *, limit: int = 10) -> None:
    normalized = " ".join((value or "").strip().split())
    if not normalized or normalized in container:
        return
    if len(container) >= limit:
        return
    container.append(normalized)


def _flatten_json_ld(candidate: Any) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    if isinstance(candidate, dict):
        if any(key in candidate for key in ["@type", "address", "areaServed", "telephone", "email"]):
            flattened.append(candidate)
        graph = candidate.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                flattened.extend(_flatten_json_ld(item))
    elif isinstance(candidate, list):
        for item in candidate:
            flattened.extend(_flatten_json_ld(item))
    return flattened


def _parse_json_ld_blocks(
    soup: BeautifulSoup,
) -> tuple[list[dict[str, Any]], list[str], list[str], list[str], list[str], dict[str, int]]:
    structured_blocks: list[dict[str, Any]] = []
    addresses: list[str] = []
    phones: list[str] = []
    emails: list[str] = []
    opening_hours: list[str] = []
    phone_validation_rejections: dict[str, int] = {}

    for script_tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if not script_tag.string:
            continue
        try:
            parsed = json.loads(script_tag.string)
        except json.JSONDecodeError:
            continue

        for node in _flatten_json_ld(parsed):
            node_type = str(node.get("@type") or "").lower()
            if node_type and node_type not in JSON_LD_TYPES_OF_INTEREST:
                continue
            structured_blocks.append(node)

            address = node.get("address")
            if isinstance(address, dict):
                address_parts = [
                    str(address.get(key)).strip()
                    for key in ["streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"]
                    if address.get(key)
                ]
                _add_unique(addresses, ", ".join(address_parts), limit=5)
            elif isinstance(address, str):
                _add_unique(addresses, address, limit=5)

            area_served = node.get("areaServed")
            if isinstance(area_served, list):
                for item in area_served:
                    if isinstance(item, dict):
                        _add_unique(addresses, item.get("name"), limit=5)
                    else:
                        _add_unique(addresses, str(item), limit=5)
            elif isinstance(area_served, dict):
                _add_unique(addresses, area_served.get("name"), limit=5)
            elif isinstance(area_served, str):
                _add_unique(addresses, area_served, limit=5)

            for raw_phone in [node.get("telephone"), node.get("phone")]:
                normalized_phone, rejection_reason = _classify_phone_candidate(str(raw_phone)) if raw_phone else (None, None)
                if normalized_phone and normalized_phone not in phones:
                    phones.append(normalized_phone)
                elif rejection_reason:
                    phone_validation_rejections[rejection_reason] = phone_validation_rejections.get(rejection_reason, 0) + 1

            normalized_email = _normalize_email(str(node.get("email"))) if node.get("email") else None
            if normalized_email and normalized_email not in emails:
                emails.append(normalized_email)

            opening_data = node.get("openingHours") or node.get("openingHoursSpecification")
            if isinstance(opening_data, list):
                for item in opening_data:
                    _add_unique(opening_hours, str(item), limit=7)
            elif opening_data:
                _add_unique(opening_hours, str(opening_data), limit=7)

    return structured_blocks, addresses, phones, emails, opening_hours, phone_validation_rejections


def _extract_address_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for match in ADDRESS_HINT_REGEX.findall(text):
        normalized_match = " ".join(match.split())
        lowered_match = normalized_match.lower()
        if not any(char.isdigit() for char in normalized_match) and not any(
            hint in lowered_match for hint in ADDRESS_CONFIRMATION_HINTS
        ):
            continue
        _add_unique(candidates, normalized_match, limit=5)
    return candidates


def _classify_page_url(url: str) -> str:
    lowered = url.lower()
    if any(token in lowered for token in ["book", "booking", "reserv", "agenda", "cita"]):
        return "booking"
    if any(token in lowered for token in ["pricing", "precio", "precios", "quote", "cotiza"]):
        return "pricing"
    if "service" in lowered or "servicio" in lowered:
        return "services"
    if "location" in lowered or "ubicacion" in lowered or "locations" in lowered or "sede" in lowered:
        return "locations"
    if "contact" in lowered or "contacto" in lowered:
        return "contact"
    if "about" in lowered or "nosotros" in lowered or "equipo" in lowered:
        return "about"
    if "career" in lowered or "trabajo" in lowered or "empleo" in lowered:
        return "careers"
    return "other"


def _detect_primary_cta(text: str, href: str) -> str | None:
    lowered_blob = f"{text} {href}".lower()
    for cta_type, patterns in CTA_PATTERNS.items():
        if any(pattern in lowered_blob for pattern in patterns):
            return cta_type
    return None


def _looks_like_external_booking_url(url: str) -> bool:
    lowered = str(url or "").strip().lower()
    if not lowered.startswith("http"):
        return False
    return any(token in lowered for token in EXTERNAL_BOOKING_HINTS)


def parse_html_basic(html_content: str, base_url: str) -> Tuple[str, Dict]:
    soup = BeautifulSoup(html_content, "html.parser")
    html_lang = (soup.html.get("lang") if soup.html else None) or ""
    meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    meta_locale = soup.find("meta", attrs={"property": "og:locale"})
    (
        structured_data,
        structured_addresses,
        structured_phones,
        structured_emails,
        opening_hours,
        phone_validation_rejections,
    ) = _parse_json_ld_blocks(soup)

    title_value = soup.title.string.strip() if soup.title and soup.title.string else ""
    description_value = meta_desc["content"].strip() if meta_desc and meta_desc.get("content") else ""
    is_reference_page = _looks_like_reference_page(base_url, title_value, description_value)
    primary_social_profile = _build_social_profile_record(base_url, is_primary=True)

    metadata = {
        "title": title_value,
        "description": description_value,
        "emails": set(structured_emails),
        "phones": set(structured_phones),
        "social_links": set(),
        "social_profiles": [primary_social_profile] if primary_social_profile else [],
        "internal_links": set(),
        "map_links": set(),
        "external_links": set(),
        "whatsapp_url": None,
        "booking_url": None,
        "pricing_page_url": None,
        "service_page_url": None,
        "social_links_count": 0,
        "form_detected": soup.find("form") is not None,
        "html_lang": html_lang.strip().lower() or None,
        "meta_locale": meta_locale["content"].strip().lower() if meta_locale and meta_locale.get("content") else None,
        "structured_data": structured_data,
        "structured_data_evidence": [],
        "addresses": structured_addresses,
        "opening_hours": opening_hours,
        "contact_channels": [],
        "cta_candidates": [],
        "primary_cta": None,
        "primary_identity_type": "social_profile" if primary_social_profile else "website",
        "primary_identity_url": base_url,
        "phone_validation_rejections": dict(phone_validation_rejections),
        "invalid_phone_candidates_count": sum(phone_validation_rejections.values()),
    }

    if structured_data:
        metadata["structured_data_evidence"].append("json_ld_detected")
    if structured_addresses:
        metadata["structured_data_evidence"].append("structured_address_detected")
    for phone in structured_phones:
        _append_contact_channel(
            metadata["contact_channels"],
            channel_type="phone",
            value=phone,
            source="structured_data",
        )
    for email in structured_emails:
        _append_contact_channel(
            metadata["contact_channels"],
            channel_type="email",
            value=email,
            source="structured_data",
        )

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        anchor_text = a_tag.get_text(" ", strip=True)
        lowered_href = href.lower()
        normalized_href = _normalize_href(base_url, href)
        cta_type = _detect_primary_cta(anchor_text, href)

        if cta_type and cta_type == "booking" and is_reference_page:
            cta_type = None

        if cta_type and cta_type not in metadata["cta_candidates"]:
            metadata["cta_candidates"].append(cta_type)
            metadata["primary_cta"] = metadata["primary_cta"] or cta_type

        if lowered_href.startswith("mailto:"):
            email = href[7:].split("?")[0]
            normalized_email = _normalize_email(email)
            if normalized_email:
                metadata["emails"].add(normalized_email)
                _append_contact_channel(
                    metadata["contact_channels"],
                    channel_type="email",
                    value=normalized_email,
                    source="mailto_link",
                )
            continue

        if lowered_href.startswith("tel:"):
            normalized_phone, rejection_reason = _classify_phone_candidate(href[4:])
            if normalized_phone:
                metadata["phones"].add(normalized_phone)
                _append_contact_channel(
                    metadata["contact_channels"],
                    channel_type="phone",
                    value=normalized_phone,
                    source="tel_link",
                )
            elif rejection_reason:
                metadata["phone_validation_rejections"][rejection_reason] = (
                    metadata["phone_validation_rejections"].get(rejection_reason, 0) + 1
                )
                metadata["invalid_phone_candidates_count"] += 1
            continue

        if "wa.me" in lowered_href or "api.whatsapp.com" in lowered_href or "whatsapp" in lowered_href:
            metadata["whatsapp_url"] = normalized_href or href
            _append_contact_channel(
                metadata["contact_channels"],
                channel_type="whatsapp",
                value=metadata["whatsapp_url"],
                source="whatsapp_link",
            )

        if any(social in lowered_href for social in ["linkedin.com", "instagram.com", "facebook.com", "twitter.com", "x.com", "tiktok.com"]):
            if normalized_href:
                social_profile = _build_social_profile_record(normalized_href, is_primary=False)
                if social_profile:
                    metadata["social_links"].add(social_profile["url"])
                    metadata["social_profiles"].append(social_profile)
            continue

        if "google.com/maps" in lowered_href or "maps.app.goo.gl" in lowered_href or "goo.gl/maps" in lowered_href:
            if normalized_href:
                metadata["map_links"].add(normalized_href)

        if normalized_href and _is_same_site(base_url, normalized_href):
            page_type = _classify_page_url(normalized_href)
            if page_type != "other":
                metadata["internal_links"].add(normalized_href)
            if page_type == "booking" and not metadata["booking_url"] and not is_reference_page:
                metadata["booking_url"] = normalized_href
            elif page_type == "pricing" and not metadata["pricing_page_url"]:
                metadata["pricing_page_url"] = normalized_href
            elif page_type == "services" and not metadata["service_page_url"]:
                metadata["service_page_url"] = normalized_href
            elif _looks_like_internal_key_page(anchor_text.lower(), href):
                metadata["internal_links"].add(normalized_href)
        elif normalized_href and normalized_href.startswith("http"):
            if not metadata["booking_url"] and not is_reference_page and _looks_like_external_booking_url(normalized_href):
                metadata["booking_url"] = normalized_href
            metadata["external_links"].add(normalized_href)

    for button_tag in soup.find_all(["button", "a"]):
        button_text = button_tag.get_text(" ", strip=True)
        cta_type = _detect_primary_cta(button_text, button_tag.get("href", ""))
        if cta_type and cta_type == "booking" and is_reference_page:
            cta_type = None
        if cta_type and cta_type not in metadata["cta_candidates"]:
            metadata["cta_candidates"].append(cta_type)
            metadata["primary_cta"] = metadata["primary_cta"] or cta_type

    for element in soup(["script", "style", "svg", "img", "noscript", "iframe"]):
        element.decompose()

    raw_text = soup.get_text(separator=" ", strip=True)
    clean_text = re.sub(r"\s+", " ", raw_text)

    visible_emails, visible_phones, visible_phone_rejections = _extract_visible_contacts(clean_text)
    metadata["emails"].update(visible_emails)
    metadata["phones"].update(visible_phones)
    for rejection_reason, count in visible_phone_rejections.items():
        metadata["phone_validation_rejections"][rejection_reason] = (
            metadata["phone_validation_rejections"].get(rejection_reason, 0) + count
        )
        metadata["invalid_phone_candidates_count"] += count
    for address_candidate in _extract_address_candidates(clean_text):
        _add_unique(metadata["addresses"], address_candidate, limit=5)

    for phone in sorted(metadata["phones"]):
        _append_contact_channel(
            metadata["contact_channels"],
            channel_type="phone",
            value=phone,
            source="visible_text",
        )
    for email in sorted(metadata["emails"]):
        _append_contact_channel(
            metadata["contact_channels"],
            channel_type="email",
            value=email,
            source="visible_text",
        )
    if metadata["form_detected"]:
        _append_contact_channel(
            metadata["contact_channels"],
            channel_type="contact_form",
            value=base_url,
            source="html_form",
        )
    if metadata["booking_url"] and not is_reference_page:
        _append_contact_channel(
            metadata["contact_channels"],
            channel_type="booking",
            value=metadata["booking_url"],
            source="booking_link",
        )

    deduped_channels: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for channel in metadata["contact_channels"]:
        pair = (channel["type"], channel["value"])
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        deduped_channels.append(channel)

    metadata["emails"] = sorted(metadata["emails"])
    metadata["phones"] = sorted(metadata["phones"])
    metadata["social_links"] = sorted(metadata["social_links"])
    deduped_social_profiles: list[dict[str, Any]] = []
    seen_social_profiles: set[tuple[str, str]] = set()
    for profile in metadata["social_profiles"]:
        if not isinstance(profile, dict):
            continue
        token = (str(profile.get("platform") or ""), str(profile.get("url") or ""))
        if token in seen_social_profiles:
            continue
        seen_social_profiles.add(token)
        deduped_social_profiles.append(profile)
    metadata["social_profiles"] = deduped_social_profiles
    metadata["internal_links"] = sorted(metadata["internal_links"])
    metadata["external_links"] = sorted(metadata["external_links"])
    metadata["map_links"] = sorted(metadata["map_links"])
    metadata["addresses"] = list(metadata["addresses"])
    metadata["contact_channels"] = deduped_channels
    metadata["social_links_count"] = len(metadata["social_links"])
    social_profile_metadata = _extract_social_profile_metadata(soup, base_url, clean_text, metadata)
    if social_profile_metadata:
        metadata["social_profile"] = social_profile_metadata
        metadata["primary_identity_type"] = "social_profile"
        metadata["primary_identity_url"] = base_url
        for profile in metadata["social_profiles"]:
            if profile.get("url") == base_url:
                profile["contact_signals"] = [
                    signal
                    for signal in [
                        "public_email" if metadata["emails"] else None,
                        "public_phone" if metadata["phones"] else None,
                        "whatsapp" if metadata["whatsapp_url"] else None,
                        "external_link" if social_profile_metadata.get("external_links") else None,
                    ]
                    if signal
                ]
                profile["activity_signals"] = social_profile_metadata.get("activity_signals", [])
    else:
        metadata["social_profile"] = None

    return clean_text, metadata
