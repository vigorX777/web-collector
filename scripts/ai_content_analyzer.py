#!/usr/bin/env python3
"""
合并 AI 调用：一次生成标题 + 摘要 + 结构化标签
节省 40-50% 时间（避免多次模型启动）
"""

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Dict, List, Tuple


def load_content(content_file: str) -> str:
    """加载内容文件"""
    with open(content_file, "r", encoding="utf-8") as handle:
        return handle.read()


def analyze_content(original_title: str, content: str, source: str, max_content_len: int = 1000) -> Tuple[str, str, Dict[str, List[str]]]:
    """
    一次 AI 调用同时生成：标题 + 摘要 + 标签
    返回: (生成标题, 摘要, 标签字典)
    """
    truncated = content[:max_content_len]
    if len(content) > max_content_len:
        truncated += "\n... (内容已截断)"

    prompt = f"""请分析以下内容，生成标题、摘要和结构化标签。

【来源】
{source}

【原标题】
{original_title}

【内容】
{truncated}


【任务】
1. 生成一个简洁准确的标题（10-30字，概括核心主题）
2. 生成 2-3 句话的摘要（概括核心观点）
3. 生成 5 个结构化标签：
   - 对象（2个）：核心主体/技术/工具
   - 场景（1个）：应用场景
   - 类型（1个）：内容形式
   - 方法（1个）：方法论/技巧

【输出格式】
只输出 JSON，不要解释：
{{
  "title": "生成的标题",
  "summary": "摘要内容",
  "tags": {{
    "对象": ["标签1", "标签2"],
    "场景": ["标签3"],
    "类型": ["标签4"],
    "方法": ["标签5"]
  }}
}}"""

    try:
        result = subprocess.run(
            ["openclaw", "agent", "--local", "--session-id", "web-collector-ai", "-m", prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise Exception(f"AI call failed: {result.stderr}")

        # 提取 JSON
        output = result.stdout.strip()
        # 尝试从 markdown 代码块中提取
        code_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', output)
        if code_match:
            output = code_match.group(1).strip()
        
        # 尝试找到 JSON 对象
        json_match = re.search(r'\{[\s\S]*\}', output)
        if json_match:
            output = json_match.group()
        
        data = json.loads(output)
        generated_title = data.get("title", original_title)
        summary = data.get("summary", "")
        tags_dict = data.get("tags", {})
        return generated_title, summary, tags_dict

    except Exception as e:
        print(f"Warning: AI analysis failed: {e}", file=sys.stderr)
        # Fallback
        return original_title, "", {}


def validate_tags(tags_dict: Dict[str, List[str]]) -> List[str]:
    """验证并扁平化标签"""
    result = []
    result.extend(tags_dict.get("对象", [])[:2])
    result.extend(tags_dict.get("场景", [])[:1])
    result.extend(tags_dict.get("类型", [])[:1])
    result.extend(tags_dict.get("方法", [])[:1])

    # 规范化
    normalized = []
    seen = set()
    for tag in result:
        tag = tag.strip().lower()
        if tag and tag not in seen:
            seen.add(tag)
            normalized.append(tag)

    return normalized


def fallback_analysis(title: str, content: str) -> Tuple[str, str, List[str]]:
    """AI 失败时的降级方案"""
    # 简单摘要：前 200 字
    summary = content[:200].strip() + "..." if len(content) > 200 else content.strip()

    # 规则标签
    tags = ["资料归档", "知识管理", "原文备份"]
    return title, summary, tags


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--content-file", required=True)
    parser.add_argument("--source", default="")
    args = parser.parse_args()

    if not os.path.exists(args.content_file):
        print(json.dumps({
            "success": False,
            "error": {"code": "CONTENT_FILE_MISSING", "message": f"Not found: {args.content_file}"}, "retryable": False
        }))
        return 1

    with open(args.content_file, "r", encoding="utf-8") as f:
        content = f.read()

    generated_title, summary, tags_dict = analyze_content(args.title, content, args.source)
    tags = validate_tags(tags_dict)

    if not summary or len(tags) < 3:
        generated_title, summary, tags = fallback_analysis(args.title, content)

    print(json.dumps({
        "success": True,
        "data": {
            "title": generated_title,
            "summary": summary,
            "tags": tags[:5]
        }
    }, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
