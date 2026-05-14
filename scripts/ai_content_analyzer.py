#!/usr/bin/env python3
"""
Generate candidate title, summary, and tags via LLM API call.

Uses OpenAI-compatible chat completions API.
Config: AI_API_BASE and AI_API_KEY in .env, or falls back to Hermes config.yaml.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Tuple

from env_loader import load_env_file

load_env_file()

# ── API config resolution ──────────────────────────────────────────

def _resolve_api_config() -> Tuple[str, str, str]:
    """Resolve API base URL, key, and model from env or Hermes config."""
    base = os.environ.get("AI_API_BASE", "")
    key = os.environ.get("AI_API_KEY", "")
    model = os.environ.get("AI_API_MODEL", "")

    if base and key:
        return base, key, model or "deepseek-v4-pro"

    # Fallback: read from Hermes config.yaml
    hermes_config = Path.home() / ".hermes" / "config.yaml"
    if hermes_config.exists():
        try:
            content = hermes_config.read_text()
            if not base:
                m = re.search(r'^\s*base_url:\s*(\S+)', content, re.MULTILINE)
                if m:
                    base = m.group(1)
            if not key:
                m = re.search(r'^\s*api_key:\s*(\S+)', content, re.MULTILINE)
                if m:
                    key = m.group(1)
            if not model:
                # Try provider-specific model first (deepseek > openrouter)
                for provider in ["deepseek", "openrouter"]:
                    pattern = rf'{provider}:.*?\n\s+model:\s*(\S+)'
                    m = re.search(pattern, content, re.DOTALL)
                    if m and m.group(1):
                        model = m.group(1)
                        break
                # Fallback: any non-empty model line
                if not model:
                    for m in re.finditer(r'^\s*model:\s*(\S+)', content, re.MULTILINE):
                        if m.group(1):
                            model = m.group(1)
                            break
        except Exception:
            pass

    return base, key, model or "deepseek-v4-flash"


def _chat_completion(
    system_prompt: str,
    user_prompt: str,
    timeout: int = 120,
) -> str:
    """Call OpenAI-compatible chat completions API, return response text."""
    base, key, model = _resolve_api_config()
    if not base or not key:
        raise RuntimeError(
            "AI_API_BASE and AI_API_KEY not configured. "
            "Set them in .env or ensure Hermes config.yaml has base_url and api_key."
        )

    url = base.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 1024,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            return content.strip()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API error {e.code}: {detail}") from e
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Invalid API response: {e}")


# ── Content processing ─────────────────────────────────────────────

def load_content(content_file: str) -> str:
    with open(content_file, "r", encoding="utf-8") as handle:
        return handle.read()


def sample_content(content: str, max_content_len: int = 3200) -> str:
    if len(content) <= max_content_len:
        return content

    segment = max_content_len // 3
    start = content[:segment].strip()
    middle_start = max((len(content) // 2) - (segment // 2), 0)
    middle = content[middle_start:middle_start + segment].strip()
    end = content[-segment:].strip()

    sampled_parts = []
    for label, chunk in (("开头", start), ("中段", middle), ("结尾", end)):
        if chunk:
            sampled_parts.append(f"[{label}]\n{chunk}")

    sampled = "\n\n".join(sampled_parts)
    if len(sampled) < len(content):
        sampled += "\n\n... (内容为分段采样)"
    return sampled


def build_prompt(original_title: str, content: str, source: str) -> str:
    return f"""请分析以下内容，生成标题、摘要和标签，只输出 JSON：
{{
  "title": "生成标题",
  "summary": "信息型摘要",
  "tags": ["标签1", "标签2", "标签3"]
}}

要求：
1. 摘要必须是信息型摘要，用于收藏后的快速回顾
2. 摘要必须覆盖：
- 主题是什么
- 关键观点/做法是什么
- 有什么特别值得记住的信息
3. 摘要避免空泛评价，不要写"本文介绍了""这篇文章讲了"这类套话
4. 优先保证信息完整和信息密度，不限制句数和字数
5. 标签输出 3-5 个即可
6. 标签只允许三类：
- 核心对象：人、产品、工具、组织、项目、协议、事件，如 OpenAI、ClaudeCode、SamAltman、MCP
- AI概念：统一英文标准词且不能有空格，如 Agent、Workflow、PromptEngineering、MemorySystem、HarnessEngineering
- 业务场景：统一中文，如 知识管理、办公自动化、代码生成、产品设计、内容创作、投资分析
7. 只保留高检索价值标签，不要复述标题碎片
8. 不要输出空泛词、兜底词或带空格标签
9. 同义词归一：
智能体→Agent
工作流→Workflow
提示工程→PromptEngineering
记忆系统→MemorySystem
Claude Code/claude-code→ClaudeCode
Open Claw/openclaw→OpenClaw
Twitter/X→XTwitter

【来源】
{source}

【原标题】
{original_title}

【内容】
{content}
"""


def analyze_content(
    original_title: str,
    content: str,
    source: str,
    url: str = "",
    max_content_len: int = 3200,
) -> Tuple[str, str, List[str]]:
    sampled = sample_content(content, max_content_len=max_content_len)
    user_prompt = build_prompt(original_title, sampled, source)
    system_prompt = "你是一个专业的内容分析助手。只输出 JSON，不要有任何额外文字。"

    try:
        output = _chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout=120,
        )

        # Extract JSON from response (handle ```json fences or bare JSON)
        code_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", output)
        if code_match:
            output = code_match.group(1).strip()

        json_match = re.search(r"\{[\s\S]*\}", output)
        if json_match:
            output = json_match.group()

        data = json.loads(output)
        generated_title = data.get("title", original_title)
        summary = data.get("summary", "")
        tags = data.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        tags = [str(tag).strip() for tag in tags if str(tag).strip()]
        return generated_title, summary, tags

    except Exception as error:
        print(f"Warning: AI analysis failed: {error}", file=sys.stderr)
        return "", "", []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--content-file", required=True)
    parser.add_argument("--source", default="")
    parser.add_argument("--url", default="")
    args = parser.parse_args()

    if not os.path.exists(args.content_file):
        print(json.dumps({
            "success": False,
            "error": {
                "code": "CONTENT_FILE_MISSING",
                "message": f"Not found: {args.content_file}",
                "retryable": False,
            },
        }, ensure_ascii=False))
        return 1

    content = load_content(args.content_file)
    generated_title, summary, tags = analyze_content(
        args.title,
        content,
        args.source,
        url=args.url,
    )

    print(json.dumps({
        "success": True,
        "data": {
            "title": generated_title,
            "summary": summary,
            "tags": tags,
        },
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
