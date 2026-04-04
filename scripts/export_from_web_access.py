#!/usr/bin/env python3
"""
Bridge web-access output into the payload format expected by collect_from_web_access.py.

Usage:
  python3 scripts/export_from_web_access.py --target <TARGET_ID>
"""

import argparse
import json
import os
import urllib.parse
import urllib.request
from urllib.parse import urlparse
from typing import Optional


PROXY_ROOT = os.environ.get("WEB_ACCESS_PROXY_ROOT", "http://127.0.0.1:3456")
DEFAULT_OUTPUT_DIR = os.environ.get(
    "WEB_COLLECTOR_RAW_DIR",
    os.path.join(os.path.dirname(__file__), "..", ".cache", "raw"),
)


def request_json(url: str, data: Optional[bytes] = None) -> dict:
    request = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def sanitize_filename(name: str) -> str:
    safe = "".join(ch if ch not in '\\/:*?"<>|' else " " for ch in name)
    safe = " ".join(safe.split()).strip()
    return safe or "untitled"


def build_eval_expression() -> str:
    return """
JSON.stringify((() => {
  const articleTexts = Array.from(document.querySelectorAll('article'))
    .map(node => (node.innerText || '').trim())
    .filter(Boolean);
  const bodyText = (document.body?.innerText || '').trim();
  const title =
    document.querySelector('meta[property="og:title"]')?.content ||
    document.querySelector('meta[name="twitter:title"]')?.content ||
    document.title ||
    '';
  const siteName =
    document.querySelector('meta[property="og:site_name"]')?.content ||
    location.hostname;
  return {
    title,
    siteName,
    articleTexts,
    bodyText,
    url: location.href
  };
})())
""".strip()


def choose_body(extracted: dict) -> str:
    articles = extracted.get("articleTexts") or []
    if articles:
        return articles[0].strip()
    return (extracted.get("bodyText") or "").strip()


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


def write_payload(payload: dict, payload_out: str) -> str:
    payload_path = os.path.abspath(payload_out)
    os.makedirs(os.path.dirname(payload_path), exist_ok=True)
    with open(payload_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return payload_path


def derive_source(site_name: str, url: str) -> str:
    return (site_name or "").strip() or urlparse(url).netloc.lower() or "Web"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--payload-out")
    args = parser.parse_args()

    info = request_json(f"{PROXY_ROOT}/info?target={urllib.parse.quote(args.target)}")
    evaluated = request_json(
        f"{PROXY_ROOT}/eval?target={urllib.parse.quote(args.target)}",
        data=build_eval_expression().encode("utf-8"),
    )

    extracted = json.loads(evaluated.get("value") or "{}")
    url = extracted.get("url") or info.get("url") or ""
    title = (extracted.get("title") or info.get("title") or "").strip()
    source = derive_source(extracted.get("siteName", ""), url)
    body = choose_body(extracted)

    if not url or not body:
        print(json.dumps({
            "success": False,
            "error": {
                "code": "WEB_ACCESS_FAILED",
                "message": "Failed to extract url or body text from the current web-access target",
                "retryable": False,
            },
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    title = choose_title(title, body)

    markdown_path = write_markdown(
        args.output_dir,
        title,
        render_markdown(title, source, url, body),
    )

    payload = {
        "title": title,
        "url": url,
        "source": source,
        "markdown_path": markdown_path,
        "route": "internal",
    }

    payload_path = args.payload_out or f"{markdown_path}.payload.json"
    payload_path = write_payload(payload, payload_path)
    payload["payload_path"] = payload_path

    print(json.dumps({"success": True, "data": payload}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
