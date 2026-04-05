#!/usr/bin/env python3
"""
Defuddle-backed extractor for generic web pages and WeChat articles.
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

from extractors.shared import ExtractionError, ExtractionResult, choose_title, get_string


WECHAT_NOISE_LINES = {
    "继续滑动看下一个",
    "向上滑动看下一个",
    "知道了",
    "微信扫一扫",
    "使用小程序",
}

WECHAT_NOISE_SUBSTRINGS = {
    "轻点两下取消赞",
    "轻点两下取消在看",
}

WECHAT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.43 NetType/WIFI Language/zh_CN",
    "Referer": "https://mp.weixin.qq.com/",
}


def run_defuddle_json(source: str) -> dict:
    env = os.environ.copy()
    env["FORCE_COLOR"] = "0"
    env["NO_COLOR"] = "1"

    try:
        result = subprocess.run(
            ["defuddle", "parse", source, "--json", "--md"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    except FileNotFoundError as error:
        raise ExtractionError("DEFUDDLE_FAILED", "defuddle command not found") from error

    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        raise ExtractionError("DEFUDDLE_FAILED", details or "defuddle parse failed")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ExtractionError("DEFUDDLE_FAILED", f"Invalid JSON from defuddle: {error}") from error


def run_defuddle_markdown(source: str) -> str:
    env = os.environ.copy()
    env["FORCE_COLOR"] = "0"
    env["NO_COLOR"] = "1"

    try:
        result = subprocess.run(
            ["defuddle", "parse", source, "--md"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    except FileNotFoundError as error:
        raise ExtractionError("DEFUDDLE_FAILED", "defuddle command not found") from error

    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        raise ExtractionError("DEFUDDLE_FAILED", details or "defuddle parse failed")

    return result.stdout.strip()


def fetch_url(url: str, headers: Optional[Dict[str, str]] = None) -> str:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_meta_content(document: str, key: str, attribute: str = "property") -> str:
    pattern = rf'<meta[^>]+{attribute}="{re.escape(key)}"[^>]+content="([^"]*)"'
    match = re.search(pattern, document, re.I)
    if match:
        return html.unescape(match.group(1)).strip()
    return ""


def extract_title_from_html(document: str) -> str:
    for key, attribute in (("og:title", "property"), ("twitter:title", "property"), ("description", "name")):
        value = extract_meta_content(document, key, attribute=attribute)
        if value:
            return value

    match = re.search(r"<title>(.*?)</title>", document, re.I | re.S)
    if match:
        return html.unescape(match.group(1)).strip()
    return ""


def extract_wechat_source(document: str) -> str:
    match = re.search(r'<a[^>]+id="js_name"[^>]*>\s*(.*?)\s*</a>', document, re.I | re.S)
    if match:
        return html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()

    author = extract_meta_content(document, "author", attribute="name")
    if author:
        return author

    site_name = extract_meta_content(document, "og:site_name")
    if site_name:
        return site_name

    return "mp.weixin.qq.com"


def extract_element_inner_html(document: str, element_id: str) -> str:
    match = re.search(rf'<(?P<tag>[a-zA-Z0-9]+)\b[^>]*\bid="{re.escape(element_id)}"[^>]*>', document, re.I)
    if not match:
        return ""

    tag_name = match.group("tag").lower()
    search_pos = match.end()
    depth = 1
    token_pattern = re.compile(rf"</?{tag_name}\b[^>]*>", re.I)

    for token in token_pattern.finditer(document, search_pos):
        token_text = token.group(0)
        if token_text.startswith("</"):
            depth -= 1
            if depth == 0:
                return document[search_pos:token.start()]
        else:
            depth += 1

    return ""


def decode_js_string(raw: str) -> str:
    def replace_hex(match: re.Match[str]) -> str:
        return chr(int(match.group(1), 16))

    replacements = {
        r"\\n": "\n",
        r"\\r": "\r",
        r"\\t": "\t",
        r"\\'": "'",
        r'\\"': '"',
        r"\\\\": "\\",
    }

    decoded = re.sub(r"\\x([0-9a-fA-F]{2})", replace_hex, raw)
    decoded = re.sub(r"\\u([0-9a-fA-F]{4})", replace_hex, decoded)
    for old, new in replacements.items():
        decoded = decoded.replace(old, new)
    return html.unescape(decoded)


def extract_wechat_short_content(document: str) -> str:
    match = re.search(r"content_noencode:\s*JsDecode\('((?:\\.|[^'])*)'\)", document, re.S)
    if not match:
        match = re.search(r"text_page_info:\s*\{.*?content:\s*JsDecode\('((?:\\.|[^'])*)'\)", document, re.S)
    if not match:
        return ""

    content = decode_js_string(match.group(1))
    content = re.sub(r"<a\b[^>]*>(.*?)</a>", r"\1", content, flags=re.I | re.S)
    paragraphs = []
    for chunk in re.split(r"\n\s*\n", content.strip()):
        chunk = chunk.strip()
        if not chunk:
            continue
        paragraphs.append(f"<p>{html.escape(chunk).replace(chr(10), '<br>')}</p>")
    return "\n".join(paragraphs).strip()


def extract_wechat_body(document: str) -> str:
    body_html = extract_element_inner_html(document, "js_content")
    if body_html:
        return body_html.strip()
    return extract_wechat_short_content(document)


def normalize_line_for_match(line: str) -> str:
    return re.sub(r"[\s\u3000:：,，.。!！?？、/\\|]+", "", line).strip()


def is_wechat_noise_line(line: str) -> bool:
    normalized = normalize_line_for_match(line)
    if not normalized:
        return False

    if normalized in {normalize_line_for_match(item) for item in WECHAT_NOISE_LINES}:
        return True

    if any(fragment in normalized for fragment in WECHAT_NOISE_SUBSTRINGS):
        return True

    action_keywords = ["视频", "小程序", "赞", "在看", "分享", "留言", "收藏", "听过"]
    if sum(keyword in normalized for keyword in action_keywords) >= 4:
        return True

    return False


def clean_body(body: str, url: str) -> str:
    if urlparse(url).netloc.lower() != "mp.weixin.qq.com":
        return body.strip()

    cleaned_lines = []
    previous_blank = False

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if is_wechat_noise_line(line):
            continue

        if not line:
            if previous_blank:
                continue
            cleaned_lines.append("")
            previous_blank = True
            continue

        cleaned_lines.append(line)
        previous_blank = False

    return "\n".join(cleaned_lines).strip()


def derive_source(site_name: str, domain: str, url: str) -> str:
    return get_string(site_name) or get_string(domain) or urlparse(url).netloc.lower() or "Web"


def extract_wechat(url: str) -> ExtractionResult:
    document = fetch_url(url, WECHAT_HEADERS)
    body_html = extract_wechat_body(document)
    if not body_html:
        raise ExtractionError("DEFUDDLE_FAILED", "Failed to extract WeChat article body")

    resolved_title = extract_title_from_html(document) or "未命名网页"
    wrapped_html = "\n".join([
        "<!doctype html>",
        "<html>",
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{html.escape(resolved_title)}</title>",
        f'<base href="{html.escape(url)}">',
        "</head>",
        "<body>",
        f'<article id="js_content">{body_html}</article>',
        "</body>",
        "</html>",
    ])

    with tempfile.NamedTemporaryFile("w", suffix=".html", encoding="utf-8", delete=False) as handle:
        handle.write(wrapped_html)
        temp_path = handle.name

    try:
        body_markdown = run_defuddle_markdown(temp_path)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

    return ExtractionResult(
        title=choose_title(resolved_title, body_markdown),
        source=extract_wechat_source(document),
        body_markdown=clean_body(body_markdown, url),
        url=url,
        metadata={"source_domain": "mp.weixin.qq.com"},
    )


def extract_generic(url: str) -> ExtractionResult:
    extracted = run_defuddle_json(url)
    body = get_string(extracted.get("content"))
    if not body:
        raise ExtractionError("DEFUDDLE_FAILED", "Failed to extract body from defuddle output")

    title = choose_title(get_string(extracted.get("title")), body)
    return ExtractionResult(
        title=title,
        source=derive_source(extracted.get("site", ""), extracted.get("domain", ""), url),
        body_markdown=clean_body(body, url),
        url=url,
        metadata={
            "source_domain": get_string(extracted.get("domain")),
            "author": get_string(extracted.get("author")),
            "description": get_string(extracted.get("description")),
        },
    )


def extract(url: str) -> ExtractionResult:
    if urlparse(url).netloc.lower() == "mp.weixin.qq.com":
        return extract_wechat(url)
    return extract_generic(url)

