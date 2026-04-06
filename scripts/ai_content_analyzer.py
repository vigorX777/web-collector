#!/usr/bin/env python3
"""
Generate candidate title, summary, and tags with a single AI call.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from typing import List, Tuple


def load_content(content_file: str) -> str:
    with open(content_file, "r", encoding="utf-8") as handle:
        return handle.read()


def build_session_id(seed: str) -> str:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    suffix = uuid.uuid4().hex[:8]
    return f"web-collector-{int(time.time())}-{digest}-{suffix}"


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
  "summary": "2-3句摘要",
  "tags": ["标签1", "标签2", "标签3"]
}}

要求：
1. 标签输出 3-5 个即可
2. 标签只允许三类：
- 核心对象：人、产品、工具、组织、项目、协议、事件，如 OpenAI、ClaudeCode、SamAltman、MCP
- AI概念：统一英文标准词且不能有空格，如 Agent、Workflow、PromptEngineering、MemorySystem、HarnessEngineering
- 业务场景：统一中文，如 知识管理、办公自动化、代码生成、产品设计、内容创作、投资分析
3. 只保留高检索价值标签，不要复述标题碎片
4. 不要输出空泛词、兜底词或带空格标签
5. 同义词归一：
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
    prompt = build_prompt(original_title, sampled, source)
    session_id = build_session_id(url or original_title)

    try:
        result = subprocess.run(
            ["openclaw", "agent", "--local", "--session-id", session_id, "-m", prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise Exception(f"AI call failed: {result.stderr}")

        output = result.stdout.strip()
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
