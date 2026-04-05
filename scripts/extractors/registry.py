#!/usr/bin/env python3
"""
Platform detection and extractor registry for web-collector.
"""

from __future__ import annotations

from typing import Any, Callable, Dict
from urllib.parse import urlparse

from extractors import defuddle_extractor, twitter_extractor


PLATFORM_RULES = {
    "twitter": {
        "domains": ["x.com", "twitter.com", "mobile.twitter.com"],
        "label": "X/Twitter",
        "extractor": "x-tweet-fetcher",
    },
    "weixin": {
        "domains": ["mp.weixin.qq.com"],
        "label": "微信公众号",
        "extractor": "defuddle",
    },
    "jike": {
        "domains": ["okjike.com", "jike.cn", "m.okjike.com", "web.okjike.com"],
        "label": "即刻",
        "extractor": "defuddle",
    },
    "reddit": {
        "domains": ["reddit.com", "www.reddit.com", "old.reddit.com"],
        "label": "Reddit",
        "extractor": "defuddle",
    },
    "hackernews": {
        "domains": ["news.ycombinator.com"],
        "label": "Hacker News",
        "extractor": "defuddle",
    },
    "zhihu": {
        "domains": ["zhihu.com", "www.zhihu.com", "zhuanlan.zhihu.com"],
        "label": "知乎",
        "extractor": "defuddle",
    },
    "bilibili": {
        "domains": ["bilibili.com", "www.bilibili.com", "b23.tv"],
        "label": "Bilibili",
        "extractor": "defuddle",
    },
}

EXTRACTORS: Dict[str, Callable[[str], Any]] = {
    "defuddle": defuddle_extractor.extract,
    "x-tweet-fetcher": twitter_extractor.extract,
}


def detect_platform(url: str) -> dict:
    domain = urlparse(url).netloc.lower()
    bare_domain = domain.lstrip("www.")

    for platform_id, rule in PLATFORM_RULES.items():
        for candidate in rule["domains"]:
            if candidate in domain or candidate in bare_domain:
                extractor_id = rule["extractor"]
                return {
                    "platform_id": platform_id,
                    "platform_label": rule["label"],
                    "url": url,
                    "route": "internal",
                    "skill": extractor_id,
                    "extractor": extractor_id,
                    "fallback_skills": [],
                    "note": f"Use {extractor_id} for extraction and markdown export.",
                }

    return {
        "platform_id": "generic",
        "platform_label": "Web",
        "url": url,
        "route": "internal",
        "skill": "defuddle",
        "extractor": "defuddle",
        "fallback_skills": [],
        "note": "Use defuddle for extraction and markdown export.",
    }


def get_extractor(extractor_id: str) -> Callable[[str], Any]:
    if extractor_id not in EXTRACTORS:
        raise KeyError(f"Unknown extractor: {extractor_id}")
    return EXTRACTORS[extractor_id]

