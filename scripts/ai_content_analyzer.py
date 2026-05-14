#!/usr/bin/env python3
"""
Generate candidate title, summary, and tags via LLM.

Supports two backends, auto-detected by environment:
  OpenClaw mode:  subprocess call to `openclaw agent --local`
  API mode:       OpenAI-compatible chat completions (Hermes / DeepSeek / etc.)

Selection (first match wins):
  1. AI_ANALYSIS_MODE env var: "openclaw" | "api" | "auto"
  2. Auto-detect: if `openclaw` CLI exists → OpenClaw, else → API

API config (env vars, optional — falls back to Hermes config.yaml):
  AI_API_BASE   — OpenAI-compatible base URL
  AI_API_KEY    — API key
  AI_API_MODEL  — model name (default: deepseek-v4-flash)
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Tuple

from env_loader import load_env_file

load_env_file()

# ── Mode detection ──────────────────────────────────────────────────

def _detect_mode() -> str:
    """Return 'openclaw' or 'api' based on env var or auto-detection."""
    mode = os.environ.get("AI_ANALYSIS_MODE", "auto").strip().lower()
    if mode in ("openclaw", "api"):
        return mode
    # auto: prefer openclaw if available
    if shutil.which("openclaw"):
        return "openclaw"
    return "api"


# ── OpenClaw backend ────────────────────────────────────────────────

def _build_session_id(seed: str) -> str:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    suffix = uuid.uuid4().hex[:8]
    return f"web-collector-{int(time.time())}-{digest}-{suffix}"


def _analyze_via_openclaw(prompt: str, session_id: str, timeout: int = 120) -> str:
    """Call openclaw agent CLI and return raw response text."""
    result = subprocess.run(
        ["openclaw", "agent", "--local", "--session-id", session_id, "-m", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"openclaw exited {result.returncode}: {result.stderr}")
    return result.stdout.strip()


# ── API backend ─────────────────────────────────────────────────────

def _resolve_api_config() -> Tuple[str, str, str]:
    """Resolve API base URL, key, and model from env or Hermes config."""
    base = os.environ.get("AI_API_BASE", "")
    key = os.environ.get("AI_API_KEY", "")
    model = os.environ.get("AI_API_MODEL", "")

    if base and key:
        return base, key, model or "deepseek-v4-flash"

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
                for provider in ["deepseek", "openrouter"]:
                    pattern = rf'{provider}:.*?\n\s+model:\s*(\S+)'
                    m = re.search(pattern, content, re.DOTALL)
                    if m and m.group(1):
                        model = m.group(1)
                        break
                if not model:
                    for m in re.finditer(r'^\s*model:\s*(\S+)', content, re.MULTILINE):
                        if m.group(1):
                            model = m.group(1)
                            break
        except Exception:
            pass

    return base, key, model or "deepseek-v4-flash"


def _analyze_via_api(
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


# ── Content processing (shared) ─────────────────────────────────────

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


def _parse_json_response(raw: str) -> Tuple[str, str, List[str]]:
    """Extract title, summary, tags from LLM response (handles fences etc.)."""
    output = raw.strip()

    # Remove ```json fences
    code_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", output)
    if code_match:
        output = code_match.group(1).strip()

    # Extract outermost JSON object
    json_match = re.search(r"\{[\s\S]*\}", output)
    if json_match:
        output = json_match.group()

    data = json.loads(output)
    generated_title = data.get("title", "").strip()
    summary = data.get("summary", "").strip()
    tags = data.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(tag).strip() for tag in tags if str(tag).strip()]
    return generated_title, summary, tags


# ── Unified entry point ─────────────────────────────────────────────

def analyze_content(
    original_title: str,
    content: str,
    source: str,
    url: str = "",
    max_content_len: int = 3200,
) -> Tuple[str, str, List[str]]:
    sampled = sample_content(content, max_content_len=max_content_len)
    prompt = build_prompt(original_title, sampled, source)
    mode = _detect_mode()

    try:
        if mode == "openclaw":
            session_id = _build_session_id(url or original_title)
            raw = _analyze_via_openclaw(prompt, session_id)
        else:
            system_prompt = "你是一个专业的内容分析助手。只输出 JSON，不要有任何额外文字。"
            raw = _analyze_via_api(system_prompt, prompt)

        return _parse_json_response(raw)

    except Exception as error:
        print(f"Warning: AI analysis failed [{mode} mode]: {error}", file=sys.stderr)
        return "", "", []


# ── CLI ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="AI content analysis (dual-mode: openclaw / api)"
    )
    parser.add_argument("--title", required=True)
    parser.add_argument("--content-file", required=True)
    parser.add_argument("--source", default="")
    parser.add_argument("--url", default="")
    parser.add_argument(
        "--mode", choices=["openclaw", "api", "auto"], default=None,
        help="Override AI_ANALYSIS_MODE env var for this run"
    )
    args = parser.parse_args()

    if args.mode:
        os.environ["AI_ANALYSIS_MODE"] = args.mode

    mode = _detect_mode()
    print(f"[INFO] AI analysis mode: {mode}", file=sys.stderr)

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
            "mode": mode,
        },
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
