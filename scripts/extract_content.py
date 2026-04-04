#!/usr/bin/env python3
"""
Detect the source platform for a URL and emit a unified web-access route.
"""

import json
import sys
from urllib.parse import urlparse


PLATFORM_RULES = {
    "twitter": {
        "domains": ["x.com", "twitter.com", "mobile.twitter.com"],
        "label": "X/Twitter",
    },
    "weixin": {
        "domains": ["mp.weixin.qq.com"],
        "label": "微信公众号",
    },
    "jike": {
        "domains": ["okjike.com", "jike.cn", "m.okjike.com", "web.okjike.com"],
        "label": "即刻",
    },
    "reddit": {
        "domains": ["reddit.com", "www.reddit.com", "old.reddit.com"],
        "label": "Reddit",
    },
    "hackernews": {
        "domains": ["news.ycombinator.com"],
        "label": "Hacker News",
    },
    "zhihu": {
        "domains": ["zhihu.com", "www.zhihu.com", "zhuanlan.zhihu.com"],
        "label": "知乎",
    },
    "bilibili": {
        "domains": ["bilibili.com", "www.bilibili.com", "b23.tv"],
        "label": "Bilibili",
    },
}


def detect_platform(url: str) -> dict:
    domain = urlparse(url).netloc.lower()
    bare_domain = domain.lstrip("www.")

    for platform_id, rule in PLATFORM_RULES.items():
        for candidate in rule["domains"]:
            if candidate in domain or candidate in bare_domain:
                return {
                    "platform_id": platform_id,
                    "platform_label": rule["label"],
                    "url": url,
                    "route": "internal",
                    "skill": "web-access",
                    "fallback_skills": [],
                    "note": "Force web-access for extraction and markdown export.",
                }

    return {
        "platform_id": "generic",
        "platform_label": "Web",
        "url": url,
        "route": "internal",
        "skill": "web-access",
        "fallback_skills": [],
        "note": "Force web-access for extraction and markdown export.",
    }


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": {
                "code": "INVALID_INPUT",
                "message": "Usage: python3 extract_content.py <url>",
                "retryable": False,
            },
        }, ensure_ascii=False))
        sys.exit(1)

    result = detect_platform(sys.argv[1])
    print(json.dumps({"success": True, "data": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
