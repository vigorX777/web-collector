#!/usr/bin/env python3
"""
Single-entry orchestrator for web-collector.

It consumes an extractor export payload, then runs:
deduplicate -> AI analysis (title + summary + tags) -> markdown assembly -> OneDrive upload -> cache update.
"""

import argparse
import json
import os
from urllib.parse import urlparse

from build_markdown import build_markdown_file
from deduplicate import add_to_cache, is_duplicate
from extract_content import detect_platform
from ai_content_analyzer import analyze_content, load_content
from upload_to_onedrive import upload_markdown_file


def emit_error(code: str, message: str, retryable: bool = False) -> None:
    print(json.dumps({
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
        },
    }, ensure_ascii=False, indent=2))
    raise SystemExit(1)


def load_payload(args: argparse.Namespace) -> dict:
    if args.payload_json:
        return json.loads(args.payload_json)

    if args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as handle:
            return json.load(handle)

    payload = {
        "title": args.title,
        "source": args.source,
        "url": args.url,
        "markdown_path": args.markdown_path,
        "route": args.route,
    }
    return payload


def validate_payload(payload: dict) -> dict:
    url = payload.get("url")
    markdown_path = payload.get("markdown_path")
    title = payload.get("title")

    if not url:
        emit_error("INVALID_INPUT", "payload must include url")
    if not markdown_path:
        emit_error("INVALID_INPUT", "payload must include markdown_path")
    if not title:
        emit_error("INVALID_INPUT", "payload must include title")
    if not os.path.exists(markdown_path):
        emit_error("MARKDOWN_EXPORT_FAILED", f"markdown_path not found: {markdown_path}")

    return payload


def derive_source(payload: dict, platform: dict) -> str:
    if payload.get("source"):
        return payload["source"].strip()

    if platform.get("platform_label") and platform["platform_label"] != "Web":
        return platform["platform_label"]

    netloc = urlparse(payload["url"]).netloc.lower().strip()
    return netloc or "Web"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload-file")
    parser.add_argument("--payload-json")
    parser.add_argument("--url")
    parser.add_argument("--title")
    parser.add_argument("--source")
    parser.add_argument("--markdown-path")
    parser.add_argument("--route", default="internal")
    parser.add_argument("--output-dir", default=os.environ.get("WEB_COLLECTOR_OUTPUT_DIR", os.path.join(os.path.dirname(__file__), "..", ".cache", "output")))
    parser.add_argument("--minimum-tags", type=int, default=5)
    parser.add_argument("--skip-upload", action="store_true")
    args = parser.parse_args()

    try:
        payload = validate_payload(load_payload(args))
    except json.JSONDecodeError as error:
        emit_error("INVALID_INPUT", f"Invalid JSON payload: {error}")

    route = payload.get("route") or args.route or "internal"
    platform = detect_platform(payload["url"])
    duplicate = is_duplicate(payload["url"])
    if duplicate["is_duplicate"]:
        emit_error("DUPLICATE_URL", duplicate["message"])

    content = load_content(payload["markdown_path"])
    source = derive_source(payload, platform)

    # 合并 AI 调用：一次生成标题 + 摘要 + 标签
    generated_title, summary, tags_dict = analyze_content(payload["title"], content, source)

    # 验证并扁平化标签
    tags = []
    tags.extend(tags_dict.get("对象", [])[:2])
    tags.extend(tags_dict.get("场景", [])[:1])
    tags.extend(tags_dict.get("类型", [])[:1])
    tags.extend(tags_dict.get("方法", [])[:1])

    # 规范化标签
    seen = set()
    normalized_tags = []
    for tag in tags:
        tag = tag.strip().lower()
        if tag and tag not in seen:
            seen.add(tag)
            normalized_tags.append(tag)

    # 确保至少 minimum-tags 个标签
    while len(normalized_tags) < args.minimum_tags:
        fallback = ["资料归档", "知识管理", "原文备份", "学习资源", "工具推荐"]
        for f in fallback:
            if f not in normalized_tags:
                normalized_tags.append(f)
                break
        if len(normalized_tags) >= args.minimum_tags:
            break

    # 使用生成的标题
    final_title = generated_title if generated_title else payload["title"]

    try:
        markdown_result = build_markdown_file(
            title=final_title,
            source=source,
            url=payload["url"],
            route=route,
            content_file=payload["markdown_path"],
            tags=normalized_tags[:args.minimum_tags],
            output_dir=args.output_dir,
        )
    except FileNotFoundError as error:
        emit_error("MARKDOWN_EXPORT_FAILED", str(error))

    upload_result = None
    if not args.skip_upload:
        upload_result = upload_markdown_file(markdown_result["output_path"])
        add_to_cache(payload["url"], {
            "title": final_title,
            "source": source,
            "route": route,
            "platform_id": platform.get("platform_id"),
            "platform_label": platform.get("platform_label"),
            "filename": markdown_result["filename"],
            "web_url": upload_result.get("web_url"),
            "target_dir": upload_result.get("target_dir"),
            "summary": summary,
        })

    print(json.dumps({
        "success": True,
        "data": {
            "route": route,
            "platform": platform,
            "source": source,
            "original_title": payload["title"],
            "generated_title": generated_title,
            "title": final_title,
            "summary": summary,
            "tags": normalized_tags[:args.minimum_tags],
            "markdown": markdown_result,
            "upload": upload_result,
            "cached": upload_result is not None,
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
