#!/usr/bin/env python3
"""
Twitter/X extractor backed by x-tweet-fetcher.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List

from extractors.shared import ExtractionError, ExtractionResult, get_string


DEFAULT_X_TWEET_FETCHER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "x-tweet-fetcher")
)


def get_x_tweet_fetcher_script() -> str:
    base_dir = os.environ.get("WEB_COLLECTOR_X_TWEET_FETCHER_DIR", DEFAULT_X_TWEET_FETCHER_DIR)
    script_path = os.path.join(base_dir, "scripts", "fetch_tweet.py")
    if not os.path.exists(script_path):
        raise ExtractionError(
            "TWITTER_FETCH_FAILED",
            f"x-tweet-fetcher script not found: {script_path}",
        )
    return script_path


def run_x_tweet_fetcher(url: str) -> Dict[str, Any]:
    script_path = get_x_tweet_fetcher_script()
    result = subprocess.run(
        ["python3", script_path, "--url", url, "--pretty"],
        capture_output=True,
        text=True,
        check=False,
    )

    parsed = None
    if result.stdout.strip():
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise ExtractionError(
                "TWITTER_FETCH_FAILED",
                f"Invalid JSON from x-tweet-fetcher: {error}",
            ) from error

    if result.returncode != 0:
        message = ""
        if isinstance(parsed, dict) and parsed.get("error"):
            message = get_string(parsed["error"])
        if not message:
            message = get_string(result.stderr) or "x-tweet-fetcher failed"
        raise ExtractionError("TWITTER_FETCH_FAILED", message)

    if not isinstance(parsed, dict):
        raise ExtractionError("TWITTER_FETCH_FAILED", "x-tweet-fetcher returned no JSON payload")

    if parsed.get("error"):
        raise ExtractionError("TWITTER_FETCH_FAILED", get_string(parsed["error"]))

    return parsed


def render_quote(quote: Dict[str, Any]) -> str:
    text = get_string(quote.get("text"))
    if not text:
        return ""

    author = get_string(quote.get("screen_name"))
    prefix = f"@{author}: " if author else ""
    return f"## 引用推文\n\n{prefix}{text}"


def render_media_items(media: Dict[str, Any]) -> str:
    lines: List[str] = []

    for image in media.get("images", []) or []:
        url = get_string(image.get("url"))
        if url:
            lines.append(f"- 图片: {url}")

    for video in media.get("videos", []) or []:
        url = get_string(video.get("url"))
        if url:
            lines.append(f"- 视频: {url}")
            continue

        variants = video.get("variants", []) or []
        if variants:
            first_url = get_string(variants[0].get("url"))
            if first_url:
                lines.append(f"- 视频: {first_url}")

    if not lines:
        return ""

    return "## 媒体\n\n" + "\n".join(lines)


def build_body(tweet: Dict[str, Any]) -> str:
    parts: List[str] = []
    article = tweet.get("article") or {}

    if tweet.get("is_article") and get_string(article.get("full_text")):
        parts.append(get_string(article["full_text"]))
    elif get_string(tweet.get("text")):
        parts.append(get_string(tweet["text"]))
    elif get_string(article.get("preview_text")):
        parts.append(get_string(article["preview_text"]))

    quote_block = render_quote(tweet.get("quote") or {})
    if quote_block:
        parts.append(quote_block)

    media_block = render_media_items(tweet.get("media") or {})
    if media_block:
        parts.append(media_block)

    return "\n\n".join(part for part in parts if part).strip()


def choose_title(tweet: Dict[str, Any]) -> str:
    article = tweet.get("article") or {}
    article_title = get_string(article.get("title"))
    if tweet.get("is_article") and article_title:
        return article_title

    screen_name = get_string(tweet.get("screen_name"))
    if screen_name:
        return f"Tweet by @{screen_name}"
    return "Tweet"


def extract(url: str) -> ExtractionResult:
    data = run_x_tweet_fetcher(url)
    tweet = data.get("tweet") or {}
    if not tweet:
        raise ExtractionError("TWITTER_FETCH_FAILED", "x-tweet-fetcher returned no tweet payload")

    body_markdown = build_body(tweet)
    if not body_markdown:
        raise ExtractionError("TWITTER_FETCH_FAILED", "No tweet body returned by x-tweet-fetcher")

    return ExtractionResult(
        title=choose_title(tweet),
        source="X/Twitter",
        body_markdown=body_markdown,
        url=url,
        metadata={
            "tweet_id": get_string(data.get("tweet_id")),
            "username": get_string(data.get("username")),
            "author": get_string(tweet.get("author")),
            "screen_name": get_string(tweet.get("screen_name")),
            "created_at": get_string(tweet.get("created_at")),
            "is_article": bool(tweet.get("is_article")),
        },
    )
