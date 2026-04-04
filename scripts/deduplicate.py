#!/usr/bin/env python3
"""
URL normalization and local cache deduplication for web-collector.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Optional
from urllib.error import URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


DOMAIN_ALIASES = {
    "twitter.com": "x.com",
    "www.twitter.com": "x.com",
    "mobile.twitter.com": "x.com",
    "www.x.com": "x.com",
    "m.okjike.com": "okjike.com",
    "web.okjike.com": "okjike.com",
    "www.okjike.com": "okjike.com",
    "old.reddit.com": "reddit.com",
    "www.reddit.com": "reddit.com",
    "np.reddit.com": "reddit.com",
    "i.reddit.com": "reddit.com",
    "amp.reddit.com": "reddit.com",
    "www.weixin.qq.com": "mp.weixin.qq.com",
}

SHORT_URL_DOMAINS = {"t.co", "bit.ly", "tinyurl.com", "goo.gl", "ow.ly", "is.gd", "buff.ly"}

CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", ".cache", "collected_urls.json")
CACHE_TTL_DAYS = 30
CACHE_MAX_ENTRIES = 1000


def ensure_cache_dir() -> None:
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)


def load_cache() -> dict:
    ensure_cache_dir()
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE, "r", encoding="utf-8") as handle:
        return _cleanup_cache(json.load(handle))


def save_cache(cache: dict) -> None:
    ensure_cache_dir()
    with open(CACHE_FILE, "w", encoding="utf-8") as handle:
        json.dump(cache, handle, ensure_ascii=False, indent=2)


def _cleanup_cache(cache: dict) -> dict:
    now = datetime.now()
    cutoff = now - timedelta(days=CACHE_TTL_DAYS)
    active = {}

    for url, entry in cache.items():
        try:
            timestamp = datetime.fromisoformat(entry.get("date", ""))
            if timestamp >= cutoff:
                active[url] = entry
        except (ValueError, TypeError):
            active[url] = entry

    if len(active) > CACHE_MAX_ENTRIES:
        sorted_entries = sorted(active.items(), key=lambda item: item[1].get("date", ""), reverse=True)
        active = dict(sorted_entries[:CACHE_MAX_ENTRIES])

    return active


def _resolve_short_url(url: str, timeout: int = 5) -> str:
    parsed = urlparse(url)
    if parsed.netloc.lower() not in SHORT_URL_DOMAINS:
        return url

    try:
        request = Request(url, method="HEAD")
        request.add_header("User-Agent", "Mozilla/5.0")
        with urlopen(request, timeout=timeout) as response:
            return response.url
    except (URLError, OSError, ValueError):
        return url


def normalize_url(url: str) -> str:
    url = _resolve_short_url(url)
    tracking_params = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "ref",
        "source",
    }

    parsed = urlparse(url)
    netloc = DOMAIN_ALIASES.get(parsed.netloc.lower(), parsed.netloc.lower())
    path = parsed.path.rstrip("/")
    query_params = parse_qs(parsed.query)
    filtered = {key: value for key, value in query_params.items() if key not in tracking_params}

    base_url = f"{parsed.scheme}://{netloc}{path}"
    if filtered:
        return f"{base_url}?{urlencode(filtered, doseq=True)}"
    return base_url


def extract_url_from_text(text: str) -> list[str]:
    pattern = r'https?://[^\s<>"\')\]]+(?:\([^\s]*\))?'
    urls = re.findall(pattern, text)
    return [normalize_url(url) for url in urls]


def is_duplicate(url: str, existing_text: Optional[str] = None) -> dict:
    normalized = normalize_url(url)
    cache = load_cache()

    if normalized in cache:
        return {
            "is_duplicate": True,
            "source": "cache",
            "normalized_url": normalized,
            "message": f"链接已在缓存中 (收藏于 {cache[normalized].get('date', '未知时间')})",
        }

    if existing_text:
        existing_urls = extract_url_from_text(existing_text)
        if normalized in existing_urls or url in existing_urls:
            return {
                "is_duplicate": True,
                "source": "existing_text",
                "normalized_url": normalized,
                "message": "链接已在现有文本中",
            }

    return {
        "is_duplicate": False,
        "source": "none",
        "normalized_url": normalized,
        "message": "新链接，可以收藏",
    }


def add_to_cache(url: str, metadata: Optional[dict] = None) -> None:
    cache = load_cache()
    normalized = normalize_url(url)
    cache[normalized] = {
        "original_url": url,
        "date": datetime.now().isoformat(),
        "metadata": metadata or {},
    }
    save_cache(cache)


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": {
                "code": "INVALID_INPUT",
                "message": "Usage: python3 deduplicate.py <url> [existing_text_file]",
                "retryable": False,
            },
        }, ensure_ascii=False))
        sys.exit(1)

    url = sys.argv[1]
    existing_text = None
    if len(sys.argv) > 2:
        with open(sys.argv[2], "r", encoding="utf-8") as handle:
            existing_text = handle.read()

    result = is_duplicate(url, existing_text)
    print(json.dumps({"success": True, "data": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
