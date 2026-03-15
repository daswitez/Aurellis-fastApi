from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


IDENTITY_HUB_DOMAINS = {
    "beacons.ai",
    "bio.site",
    "bit.ly",
    "campsite.bio",
    "hoo.be",
    "linktr.ee",
    "lnk.bio",
    "msha.ke",
    "solo.to",
    "stan.store",
    "taplink.cc",
}
SOCIAL_PLATFORM_DOMAINS = {
    "instagram": ("instagram.com",),
    "tiktok": ("tiktok.com",),
    "linkedin": ("linkedin.com",),
    "facebook": ("facebook.com",),
    "twitter": ("twitter.com", "x.com"),
}
SOCIAL_PLATFORM_PRIORITY = {
    "instagram": 0,
    "tiktok": 1,
    "linkedin": 2,
    "facebook": 3,
    "twitter": 4,
}
SOCIAL_NOISE_HANDLES = {"intent", "share", "sharer", "sharearticle"}
SOCIAL_POST_SEGMENTS = {
    "instagram": {"explore", "p", "reel", "reels", "stories", "tv"},
    "linkedin": {"feed", "posts", "pulse"},
    "facebook": {"permalink.php", "posts", "reel", "reels", "share.php", "sharer.php", "watch"},
    "twitter": {"intent", "status"},
    "tiktok": {"video"},
}


def extract_domain(url: str | None) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower()
    except Exception:
        return str(url).lower()


def normalize_root_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}/"


def detect_platform(url: str | None) -> str | None:
    domain = extract_domain(url)
    for platform, domains in SOCIAL_PLATFORM_DOMAINS.items():
        if any(domain == item or domain.endswith(f".{item}") for item in domains):
            return platform
    return None


def is_identity_hub_url(url: str | None) -> bool:
    domain = extract_domain(url)
    return domain in IDENTITY_HUB_DOMAINS


def extract_social_handle(url: str | None) -> tuple[str | None, str | None]:
    if not url:
        return None, None

    platform = detect_platform(url)
    parsed = urlparse(url)
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
    if not platform or not segments:
        return platform, None

    candidate = segments[0]
    if platform == "linkedin":
        if len(segments) < 2 or segments[0].lower() not in {"company", "in"}:
            return platform, None
        candidate = segments[1]
    elif platform == "tiktok":
        if not candidate.startswith("@"):
            return platform, None
        candidate = candidate[1:]
    elif candidate.startswith("@"):
        candidate = candidate[1:]

    lowered_candidate = candidate.lower()
    if lowered_candidate in SOCIAL_NOISE_HANDLES:
        return platform, None
    if lowered_candidate in SOCIAL_POST_SEGMENTS.get(platform, set()):
        return platform, None

    allowed_chars = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
    if not candidate or any(char.lower() not in allowed_chars for char in candidate):
        return platform, None
    return platform, candidate


def normalize_social_profile_url(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlparse(url)
    platform = detect_platform(url)
    if not platform:
        return None
    surface_type, handle, profile_root = _classify_social_surface(parsed, platform)
    if surface_type != "social_profile" or not handle:
        return None
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc
    if not netloc:
        return None

    if platform == "instagram":
        return f"{scheme}://{netloc}/{handle}/"
    if platform == "tiktok":
        return f"{scheme}://{netloc}/@{handle}"
    if platform == "linkedin":
        profile_root = str(profile_root or "in").strip("/")
        return f"{scheme}://{netloc}/{profile_root}/{handle}/"
    if platform in {"facebook", "twitter"}:
        return f"{scheme}://{netloc}/{handle}/"
    return str(url)


def _classify_social_surface(parsed_url, platform: str) -> tuple[str, str | None, str | None]:
    segments = [segment for segment in parsed_url.path.strip("/").split("/") if segment]
    lowered_segments = [segment.lower() for segment in segments]
    query = parsed_url.query.lower()

    if platform == "linkedin":
        if "sharearticle" in parsed_url.path.lower():
            return "social_share", None, None
        if lowered_segments[:1] == ["feed"] or "posts" in lowered_segments or "pulse" in lowered_segments:
            return "social_post", None, None
        if len(segments) >= 2 and lowered_segments[0] in {"company", "in"}:
            _, handle = extract_social_handle(parsed_url.geturl())
            if handle:
                return "social_profile", handle, lowered_segments[0]
        return "social_surface", None, None

    if platform == "facebook":
        if any(token in parsed_url.path.lower() for token in ["share.php", "sharer.php"]):
            return "social_share", None, None
        if any(token in lowered_segments for token in {"posts", "reel", "reels", "watch"}):
            return "social_post", None, None
    elif platform == "twitter":
        if "intent" in parsed_url.path.lower() or "intent=" in query:
            return "social_intent", None, None
        if len(segments) >= 2 and lowered_segments[1] == "status":
            return "social_post", None, None
    elif platform == "instagram":
        if lowered_segments[:1] and lowered_segments[0] in SOCIAL_POST_SEGMENTS["instagram"]:
            return "social_post", None, None
    elif platform == "tiktok":
        if len(segments) >= 2 and lowered_segments[1] == "video":
            return "social_post", None, None

    _, handle = extract_social_handle(parsed_url.geturl())
    if handle:
        profile_root = lowered_segments[0] if platform == "linkedin" and lowered_segments else None
        return "social_profile", handle, profile_root
    return "social_surface", None, None


def classify_surface(url: str | None) -> dict[str, Any] | None:
    if not url:
        return None

    domain = extract_domain(url)
    root_url = normalize_root_url(url)
    platform = detect_platform(url)
    parsed = urlparse(url)
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]

    if is_identity_hub_url(url):
        return {
            "url": url,
            "surface_type": "identity_hub",
            "identity_type": "hub",
            "domain": domain,
        }

    if platform:
        surface_type, handle, profile_root = _classify_social_surface(parsed, platform)
        canonical_url = normalize_social_profile_url(url) if surface_type == "social_profile" else None
        return {
            "url": canonical_url or url,
            "surface_type": surface_type,
            "identity_type": "social_profile" if surface_type == "social_profile" else "social_surface",
            "domain": domain,
            "platform": platform,
            "handle": handle,
            "profile_root": profile_root,
            "path_segments": segments[:3],
        }

    is_home = bool(root_url and root_url.rstrip("/") == url.rstrip("/") and not parsed.query)
    return {
        "url": url,
        "surface_type": "website_home" if is_home else "website_page",
        "identity_type": "website",
        "domain": domain,
        "root_url": root_url,
    }


def _dedupe_urls(candidates: list[str]) -> list[str]:
    unique_urls: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_urls.append(normalized)
    return unique_urls


def _website_candidates(target_url: str, metadata: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    entry_surface = classify_surface(target_url)
    if entry_surface and entry_surface.get("identity_type") == "website" and not is_identity_hub_url(target_url):
        root_url = normalize_root_url(target_url)
        if root_url:
            candidates.append(root_url)

    for value in [metadata.get("website_url"), metadata.get("primary_identity_url")]:
        root_url = normalize_root_url(value)
        if root_url and not is_identity_hub_url(root_url) and not detect_platform(root_url):
            candidates.append(root_url)

    social_profile = metadata.get("social_profile")
    if isinstance(social_profile, dict):
        for link in social_profile.get("external_links", []):
            root_url = normalize_root_url(link)
            if root_url and not is_identity_hub_url(root_url) and not detect_platform(root_url):
                candidates.append(root_url)

    for link in metadata.get("external_links", []) or []:
        root_url = normalize_root_url(link)
        if root_url and not is_identity_hub_url(root_url) and not detect_platform(root_url):
            candidates.append(root_url)

    return _dedupe_urls(candidates)


def _best_social_candidate(target_url: str, metadata: dict[str, Any]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []

    social_profile = metadata.get("social_profile")
    if isinstance(social_profile, dict):
        platform, handle = extract_social_handle(target_url)
        if platform and handle:
            candidates.append(
                {
                    "platform": platform,
                    "handle": handle,
                    "url": metadata.get("primary_identity_url") or target_url,
                    "is_primary": True,
                    "profile_kind": "profile",
                }
            )

    for profile in metadata.get("social_profiles", []) or []:
        if not isinstance(profile, dict):
            continue
        platform = str(profile.get("platform") or "").strip().lower()
        url = str(profile.get("url") or "").strip()
        handle = str(profile.get("handle") or "").strip().lstrip("@")
        if not platform or not url or not handle:
            continue
        profile_kind = str(profile.get("profile_kind") or "profile").strip().lower()
        if profile_kind != "profile":
            continue
        candidates.append(
            {
                "platform": platform,
                "handle": handle,
                "url": url,
                "is_primary": bool(profile.get("is_primary")),
                "profile_kind": profile_kind,
            }
        )

    if not candidates:
        return None

    ranked = sorted(
        candidates,
        key=lambda item: (
            0 if item.get("is_primary") else 1,
            SOCIAL_PLATFORM_PRIORITY.get(str(item.get("platform") or "").lower(), 99),
            str(item.get("url") or ""),
        ),
    )
    return ranked[0]


def _build_direct_channel_surface(channel_type: str, url: str) -> dict[str, Any]:
    return {
        "url": url,
        "surface_type": "direct_channel",
        "identity_type": "contact_channel",
        "channel": channel_type,
    }


def resolve_identity_surfaces(target_url: str, metadata: dict[str, Any]) -> dict[str, Any]:
    entry_surface = classify_surface(target_url) or {
        "url": target_url,
        "surface_type": "unknown",
        "identity_type": "unknown",
    }
    website_candidates = _website_candidates(target_url, metadata)
    best_social = _best_social_candidate(target_url, metadata)

    existing_primary_type = str(metadata.get("primary_identity_type") or "").strip().lower()
    identity_surface: dict[str, Any] | None = None
    identity_resolution_reason = "entry_surface_used_as_identity"

    if existing_primary_type == "social_profile" and best_social:
        identity_surface = classify_surface(best_social["url"])
        identity_resolution_reason = "social_profile_confirmed"
    elif entry_surface.get("surface_type") == "identity_hub" and website_candidates:
        identity_surface = classify_surface(website_candidates[0])
        identity_resolution_reason = "identity_hub_resolved_to_website"
    elif entry_surface.get("surface_type") == "identity_hub" and best_social:
        identity_surface = classify_surface(best_social["url"])
        identity_resolution_reason = "identity_hub_resolved_to_social_profile"
    elif entry_surface.get("identity_type") == "website":
        normalized_home = normalize_root_url(metadata.get("primary_identity_url") or target_url)
        identity_surface = classify_surface(normalized_home or target_url)
        identity_resolution_reason = "website_entry_normalized_to_home"
    elif best_social:
        identity_surface = classify_surface(best_social["url"])
        identity_resolution_reason = "resolved_from_detected_social_profile"

    identity_surface = identity_surface or entry_surface

    primary_identity_type = "social_profile" if identity_surface.get("surface_type") == "social_profile" else "website"
    primary_identity_url = identity_surface.get("url") or target_url

    if primary_identity_type == "social_profile":
        platform = str(identity_surface.get("platform") or "").strip().lower()
        handle = str(identity_surface.get("handle") or "").strip().lower()
        canonical_identity = f"{platform}:{handle}" if platform and handle else str(primary_identity_url).lower()
    else:
        canonical_identity = extract_domain(primary_identity_url)

    website_url = website_candidates[0] if website_candidates else (
        primary_identity_url if primary_identity_type == "website" else None
    )

    contact_surface: dict[str, Any] | None = None
    if metadata.get("contact_page_url"):
        contact_surface = classify_surface(metadata["contact_page_url"])
    elif metadata.get("whatsapp_url"):
        contact_surface = _build_direct_channel_surface("whatsapp", metadata["whatsapp_url"])
    elif metadata.get("booking_url"):
        contact_surface = classify_surface(metadata["booking_url"])
    else:
        contact_surface = identity_surface

    offer_surface: dict[str, Any] | None = None
    for offer_url in [metadata.get("pricing_page_url"), metadata.get("booking_url"), metadata.get("service_page_url")]:
        if offer_url:
            offer_surface = classify_surface(offer_url)
            break
    if not offer_surface:
        offer_surface = identity_surface

    return {
        "canonical_identity": canonical_identity,
        "primary_identity_type": primary_identity_type,
        "primary_identity_url": primary_identity_url,
        "website_url": website_url,
        "entry_surface": entry_surface,
        "identity_surface": identity_surface,
        "contact_surface": contact_surface,
        "offer_surface": offer_surface,
        "identity_resolution_reason": identity_resolution_reason,
        "owned_website_candidates": website_candidates,
    }
