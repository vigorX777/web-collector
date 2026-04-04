#!/usr/bin/env python3
"""
Chinese-first tag generation and canonicalization rules for web-collector.
"""

import argparse
import json
import os
import re
from collections import OrderedDict


CANONICAL_RULES = OrderedDict({
    "Git": ["git"],
    "Symlink": ["symlink", "symbolic link", "软链接", "符号链接"],
    "Codex CLI": ["codex cli", "codex"],
    "技能管理": ["skills 管理", "skill 管理", "技能管理", "skills maintenance", "skill maintenance"],
    "人工智能": ["人工智能", "ai", "a.i."],
    "大语言模型": ["大语言模型", "大模型", "llm", "large language model"],
    "智能体": ["智能体", "agent", "ai agent"],
    "工作流": ["工作流", "workflow"],
    "自动化": ["自动化", "automation"],
    "知识管理": ["知识管理", "knowledge management", "pkm"],
    "提示工程": ["提示工程", "prompt engineering"],
    "OpenAI": ["openai"],
    "Claude": ["claude"],
    "API": ["api"],
    "Python": ["python"],
    "JavaScript": ["javascript", "js"],
    "OneDrive": ["onedrive"],
    "Microsoft Graph": ["microsoft graph", "graph api"],
    "微信公众号": ["微信公众号", "微信公众平台", "mp.weixin.qq.com"],
    "Reddit": ["reddit"],
    "X/Twitter": ["x.com", "twitter", "tweet", "推特"],
})

GENERIC_FALLBACK_TAGS = [
    "网页收藏",
    "内部收藏",
    "资料归档",
    "在线内容",
    "原文备份",
]

STOPWORD_TAGS = {
    "测试",
    "验证",
    "上传验证",
    "调试",
    "示例",
    "skills",
    "cli",
    "团队内的",
    "用的",
    "目录为例）",
    "维护的一点经验分享（以",
    "维护的一点经验分享",
    "的一点经验分享",
}


def load_content(content_file: str) -> str:
    with open(content_file, "r", encoding="utf-8") as handle:
        return handle.read()


def canonicalize_tag(tag: str) -> str:
    raw = tag.strip()
    lowered = raw.lower()
    for canonical, variants in CANONICAL_RULES.items():
        if lowered == canonical.lower():
            return canonical
        if lowered in {variant.lower() for variant in variants}:
            return canonical
    return raw


def detect_tags(text: str) -> list[str]:
    lowered = text.lower()
    tags = []
    for canonical, variants in CANONICAL_RULES.items():
        needles = [canonical.lower(), *[variant.lower() for variant in variants]]
        if any(needle in lowered for needle in needles):
            tags.append(canonical)
    return tags


def extract_title_phrases(title: str) -> list[str]:
    phrases = []
    for part in re.split(r"[\s|/·:：,，。？！!?\-—_与和及]+", title):
        part = part.strip()
        if len(part) < 2:
            continue
        if part in {"文章", "网页", "内容", "标题"}:
            continue
        if part in STOPWORD_TAGS:
            continue
        if "经验分享" in part or "目录为例" in part:
            continue
        if len(part) > 12:
            continue
        if part.count("的") >= 2:
            continue
        lowered = part.lower()
        if any(
            lowered != canonical.lower() and (
                canonical.lower() in lowered
                or any(variant.lower() in lowered for variant in variants)
            )
            for canonical, variants in CANONICAL_RULES.items()
        ):
            continue
        phrases.append(canonicalize_tag(part))
    return phrases


def unique_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        normalized = canonicalize_tag(item)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def generate_tags(title: str, content: str, minimum: int = 5) -> list[str]:
    tags = []
    tags.extend(extract_title_phrases(title))
    tags.extend(detect_tags(title))
    tags.extend(detect_tags(content[:12000]))
    tags = unique_preserve_order(tags)

    if len(tags) < minimum:
        for fallback in GENERIC_FALLBACK_TAGS:
            if fallback not in tags:
                tags.append(fallback)
            if len(tags) >= minimum:
                break

    return tags[: max(minimum, len(tags))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--content-file", required=True)
    parser.add_argument("--minimum", type=int, default=5)
    args = parser.parse_args()

    if not os.path.exists(args.content_file):
        print(json.dumps({
            "success": False,
            "error": {
                "code": "CONTENT_FILE_MISSING",
                "message": f"Content file not found: {args.content_file}",
                "retryable": False,
            },
        }, ensure_ascii=False))
        raise SystemExit(1)

    content = load_content(args.content_file)
    tags = generate_tags(args.title, content, args.minimum)
    print(json.dumps({"success": True, "data": {"tags": tags}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
