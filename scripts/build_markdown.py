#!/usr/bin/env python3
"""
Build the final markdown file by prepending frontmatter to a raw markdown body.
"""

import argparse
import json
import os
import re
from datetime import datetime

from deduplicate import normalize_url
from tag_rules import normalize_tag_for_obsidian


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "未命名"


def parse_tags(raw: str) -> list[str]:
    tags = []
    for item in raw.split(","):
        item = item.strip()
        if item:
            normalized = normalize_tag_for_obsidian(item)
            if normalized:
                tags.append(normalized)
    return tags


def load_markdown(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read().strip()


def build_frontmatter(title: str, source: str, url: str, normalized_url: str, route: str, tags: list[str], collected_at: str) -> str:
    lines = [
        "---",
        f"title: {title}",
        f"source: {source}",
        f"source_url: {url}",
        f"normalized_url: {normalized_url}",
        f"collected_at: {collected_at}",
        f"route: {route}",
        "tags:",
    ]
    for tag in tags:
        lines.append(f"  - {tag}")
    lines.append("---")
    return "\n".join(lines)


def build_markdown_file(
    *,
    title: str,
    source: str,
    url: str,
    route: str,
    content_file: str,
    tags: list[str],
    output_dir: str,
) -> dict:
    if not os.path.exists(content_file):
        raise FileNotFoundError(f"Content file not found: {content_file}")

    os.makedirs(output_dir, exist_ok=True)

    normalized_url = normalize_url(url)
    collected_at = datetime.now().astimezone().isoformat(timespec="seconds")
    body = load_markdown(content_file)
    safe_title = title.strip() or "未命名"
    file_date = datetime.now().strftime("%Y-%m-%d")
    filename = f"{sanitize_filename(safe_title)} - {file_date}.md"
    output_path = os.path.abspath(os.path.join(output_dir, filename))

    frontmatter = build_frontmatter(
        title=safe_title,
        source=source.strip(),
        url=url.strip(),
        normalized_url=normalized_url,
        route=route.strip(),
        tags=tags,
        collected_at=collected_at,
    )

    final_content = f"{frontmatter}\n\n# 原文\n\n{body}\n"
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(final_content)

    return {
        "output_path": output_path,
        "filename": filename,
        "normalized_url": normalized_url,
        "collected_at": collected_at,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--route", default="internal")
    parser.add_argument("--content-file", required=True)
    parser.add_argument("--tags", required=True)
    parser.add_argument("--output-dir", default=os.environ.get("WEB_COLLECTOR_OUTPUT_DIR", os.path.join(os.path.dirname(__file__), "..", ".cache", "output")))
    args = parser.parse_args()

    try:
        result = build_markdown_file(
            title=args.title,
            source=args.source,
            url=args.url,
            route=args.route,
            content_file=args.content_file,
            tags=parse_tags(args.tags),
            output_dir=args.output_dir,
        )
    except FileNotFoundError as error:
        print(json.dumps({
            "success": False,
            "error": {
                "code": "CONTENT_FILE_MISSING",
                "message": str(error),
                "retryable": False,
            },
        }, ensure_ascii=False))
        raise SystemExit(1)

    print(json.dumps({"success": True, "data": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
