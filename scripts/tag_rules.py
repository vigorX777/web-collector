#!/usr/bin/env python3
"""
Shared tag normalization rules for web-collector.
"""

import argparse
import json
import os
import re
from typing import Dict, Iterable, List


CANONICAL_TAGS: Dict[str, List[str]] = {
    "Agent": ["agent", "agents", "智能体"],
    "Workflow": ["workflow", "workflows", "工作流"],
    "PromptEngineering": ["promptengineering", "prompt engineering", "prompt-engineering", "prompt", "提示工程"],
    "MemorySystem": ["memorysystem", "memory system", "memory-system", "记忆系统"],
    "HarnessEngineering": ["harnessengineering", "harness engineering", "驾驭工程"],
    "ContextEngineering": ["contextengineering", "context engineering", "上下文工程"],
    "VibeCoding": ["vibecoding", "vibe coding"],
    "ModelCompression": ["modelcompression", "model compression", "模型压缩"],
    "ClaudeCode": ["claudecode", "claude code", "claude-code"],
    "OpenClaw": ["openclaw", "open claw", "open-claw", "autoclaw", "auto claw"],
    "OpenAI": ["openai", "open ai"],
    "Anthropic": ["anthropic"],
    "Claude": ["claude"],
    "MCP": ["mcp", "model context protocol"],
    "OpenCLI": ["opencli", "open cli", "open-cli"],
    "Obsidian": ["obsidian"],
    "XTwitter": ["xtwitter", "x/twitter", "twitter", "twitterx"],
    "知识管理": ["知识管理", "knowledgemanagement", "knowledge management", "pkm"],
    "办公自动化": ["办公自动化", "officeautomation", "office automation"],
    "代码生成": ["代码生成", "codegeneration", "code generation"],
    "产品设计": ["产品设计", "productdesign", "product design"],
    "内容创作": ["内容创作", "contentcreation", "content creation"],
    "投资分析": ["投资分析", "investmentanalysis", "investment analysis"],
    "量化交易": ["量化交易", "quanttrading", "quant trading"],
    "招聘面试": ["招聘面试", "jobinterview", "job interview"],
    "工作流搭建": ["工作流搭建"],
    "信息收集": ["信息收集", "informationcollection", "information collection"],
}


LOW_VALUE_TAGS = {
    "ai",
    "工具",
    "技术",
    "效率",
    "文章",
    "内容",
    "资料归档",
    "原文备份",
    "网页收藏",
    "学习资源",
    "by",
    "the",
}


GENERIC_FALLBACK_TAGS = [
    "知识管理",
    "办公自动化",
    "代码生成",
    "内容创作",
    "信息收集",
]


def load_content(content_file: str) -> str:
    with open(content_file, "r", encoding="utf-8") as handle:
        return handle.read()


def normalize_lookup_key(tag: str) -> str:
    cleaned = tag.strip().replace("\u3000", " ")
    cleaned = cleaned.replace("（", "(").replace("）", ")")
    cleaned = re.sub(r"[\"'`“”‘’]", "", cleaned)
    cleaned = re.sub(r"[\s\-_()/]+", "", cleaned)
    return cleaned.lower()


def is_chinese_text(tag: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", tag))


def to_pascal_case(tag: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", tag)
    if not parts:
        return ""
    normalized = []
    for part in parts:
        if part.isupper() and len(part) <= 4:
            normalized.append(part)
        else:
            normalized.append(part[:1].upper() + part[1:])
    return "".join(normalized)


def normalize_tag_for_obsidian(tag: str) -> str:
    raw = tag.strip().replace("\u3000", " ")
    raw = raw.replace("（", "(").replace("）", ")")
    raw = re.sub(r"[\"'`“”‘’]", "", raw).strip()
    if not raw:
        return ""

    lookup = normalize_lookup_key(raw)
    for canonical, aliases in CANONICAL_TAGS.items():
        candidates = {normalize_lookup_key(canonical), *(normalize_lookup_key(alias) for alias in aliases)}
        if lookup in candidates:
            return canonical

    if lookup in LOW_VALUE_TAGS:
        return ""

    if is_chinese_text(raw):
        cleaned = re.sub(r"[\s\-_./]+", "", raw)
        cleaned = cleaned.strip()
        return "" if normalize_lookup_key(cleaned) in LOW_VALUE_TAGS else cleaned

    if re.search(r"[A-Za-z]", raw):
        return to_pascal_case(raw)

    return raw


def detect_known_tags(text: str) -> List[str]:
    lowered = text.lower()
    detected = []
    for canonical, aliases in CANONICAL_TAGS.items():
        needles = [canonical.lower(), *[alias.lower() for alias in aliases]]
        if any(needle in lowered for needle in needles):
            detected.append(canonical)
    return detected


def dedupe_tags(tags: Iterable[str]) -> List[str]:
    result = []
    seen = set()
    for tag in tags:
        normalized = normalize_tag_for_obsidian(tag)
        if not normalized:
            continue
        key = normalize_lookup_key(normalized)
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def normalize_candidate_tags(
    candidates: Iterable[str],
    *,
    title: str,
    content: str,
    source: str = "",
    minimum: int = 3,
    maximum: int = 5,
) -> List[str]:
    normalized = dedupe_tags(candidates)

    if len(normalized) < minimum:
        auto_detected = detect_known_tags("\n".join([title, source, content[:4000]]))
        normalized = dedupe_tags([*normalized, *auto_detected])

    if len(normalized) < minimum:
        normalized = dedupe_tags([*normalized, *GENERIC_FALLBACK_TAGS])

    return normalized[:max(maximum, minimum)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tags-json", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--content-file")
    parser.add_argument("--source", default="")
    parser.add_argument("--minimum", type=int, default=3)
    parser.add_argument("--maximum", type=int, default=5)
    args = parser.parse_args()

    try:
        payload = json.loads(args.tags_json)
    except json.JSONDecodeError as error:
        print(json.dumps({
            "success": False,
            "error": {
                "code": "INVALID_INPUT",
                "message": f"Invalid tags JSON: {error}",
                "retryable": False,
            },
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    content = ""
    if args.content_file:
        if not os.path.exists(args.content_file):
            print(json.dumps({
                "success": False,
                "error": {
                    "code": "CONTENT_FILE_MISSING",
                    "message": f"Content file not found: {args.content_file}",
                    "retryable": False,
                },
            }, ensure_ascii=False, indent=2))
            raise SystemExit(1)
        content = load_content(args.content_file)

    tags = payload if isinstance(payload, list) else payload.get("tags", [])
    normalized = normalize_candidate_tags(
        tags,
        title=args.title,
        content=content,
        source=args.source,
        minimum=args.minimum,
        maximum=args.maximum,
    )

    print(json.dumps({"success": True, "data": {"tags": normalized}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
