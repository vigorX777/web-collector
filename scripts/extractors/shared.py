#!/usr/bin/env python3
"""
Shared result types and payload writing helpers for web-collector extractors.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ExtractionResult:
    title: str
    source: str
    body_markdown: str
    url: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class ExtractionError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def sanitize_filename(name: str) -> str:
    safe = "".join(ch if ch not in '\\/:*?"<>|' else " " for ch in name)
    safe = " ".join(safe.split()).strip()
    return safe or "untitled"


def render_markdown(title: str, source: str, url: str, body: str) -> str:
    lines = [f"# {title}", "", f"来源: {source}", f"原始链接: {url}", "", body]
    return "\n".join(lines).strip() + "\n"


def write_markdown(output_dir: str, title: str, content: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{sanitize_filename(title)}.md"
    path = os.path.abspath(os.path.join(output_dir, filename))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def write_payload(payload: Dict[str, Any], payload_out: str) -> str:
    payload_path = os.path.abspath(payload_out)
    os.makedirs(os.path.dirname(payload_path), exist_ok=True)
    with open(payload_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return payload_path


def build_payload(
    result: ExtractionResult,
    *,
    route: str,
    markdown_path: str,
    extractor_id: str,
    platform: Dict[str, Any],
) -> Dict[str, Any]:
    payload = {
        "title": result.title,
        "url": result.url,
        "source": result.source,
        "markdown_path": markdown_path,
        "route": route,
        "extractor": extractor_id,
        "platform_id": platform.get("platform_id"),
        "platform_label": platform.get("platform_label"),
    }
    for key, value in result.metadata.items():
        if key not in payload and value is not None:
            payload[key] = value
    return payload


def choose_title(title: str, body: str) -> str:
    candidate = (title or "").strip()
    lines = [line.strip() for line in body.splitlines() if line.strip()]

    if candidate and len(candidate) > 6:
        return candidate

    for line in lines:
        if line.startswith("@"):
            continue
        if line in {"引用", "帖子", "对话", "登录", "注册"}:
            continue
        if len(line) < 6:
            continue
        return line[:80]

    return candidate or "未命名网页"


def get_string(value: Optional[str]) -> str:
    return (value or "").strip()

