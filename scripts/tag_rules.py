#!/usr/bin/env python3
"""
AI-powered tag generation for web-collector.
Generates structured tags: 对象(2) + 场景(1) + 类型(1) + 方法(1) = 5 tags
"""

import argparse
import json
import os
import re
import subprocess
import sys
from typing import List, Dict


def load_content(content_file: str) -> str:
    with open(content_file, "r", encoding="utf-8") as handle:
        return handle.read()


def normalize_tag_for_obsidian(tag: str) -> str:
    """Obsidian 兼容的标签规范化"""
    cleaned = tag.strip().replace("\u3000", " ")
    cleaned = cleaned.replace("/", "")
    cleaned = re.sub(r"[\s\-_]+", "", cleaned)
    return cleaned


def normalize_tag(tag: str) -> str:
    """规范化标签：去空格、英文转小写、多词用-连接"""
    tag = tag.strip()
    tag = tag.lower()
    # 多词英文用 - 连接
    if ' ' in tag and all(c.isalpha() or c.isspace() or c == '-' for c in tag):
        tag = '-'.join(tag.split())
    return tag


def call_llm_for_tags(title: str, content: str, source: str = "") -> Dict[str, List[str]]:
    """
    调用 LLM 生成结构化标签
    """
    # 截断内容避免 token 过多
    max_content_len = 8000
    truncated_content = content[:max_content_len]
    if len(content) > max_content_len:
        truncated_content += "\n... (内容已截断)"

    prompt = f"""请阅读以下内容，并严格按照"对象、场景、类型、方法"四类标签体系输出 5 个标签。

【标签体系】
- 对象（2个）：内容涉及的核心主体/技术/工具，如 openclaw、agent、mcp、prompt、浏览器自动化、记忆系统、量化交易、学习资源、实战案例、产品思考
- 场景（1个）：内容应用的实际场景/用途，如 投资分析、自动化测试、知识管理、代码生成
- 类型（1个）：内容的表现形式，如 技术教程、实战案例、产品分析、工具推荐、观点分享
- 方法（1个）：内容涉及的方法论/技巧，如 工作流、评测、prompt优化、架构设计

【规则】
1. 对象 2 个，场景 1 个，类型 1 个，方法 1 个，共 5 个
2. 不参考历史标签，只根据当前文章内容生成
3. 英文标签小写，多个单词用 `-` 连接（如 claude-code）
4. 中文标签使用简洁固定短语（如 投资分析、技术教程）
5. 不输出空泛标签，如 AI、工具、技术、效率
6. 不要从标题中提取无意义的片段（如 "by @username" 中的 "by"）
7. 只输出 JSON，不输出解释

【来源】
{source}

【标题】
{title}

【内容】
{truncated_content}

【输出格式】
{{
  "tags": {{
    "对象": ["标签1", "标签2"],
    "场景": ["标签3"],
    "类型": ["标签4"],
    "方法": ["标签5"]
  }}
}}"""

    try:
        # 调用 OpenClaw 的本地 agent（使用 main session）
        result = subprocess.run(
            ["openclaw", "agent", "--local", "--session-id", "main", "-m", prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            raise Exception(f"LLM call failed: {result.stderr}")

        # 从输出中提取 JSON
        output = result.stdout

        # 尝试找到 JSON 块
        json_match = re.search(r'\{[\s\S]*\}', output)
        if json_match:
            json_str = json_match.group()
            data = json.loads(json_str)
            return data.get("tags", {})

        # 直接尝试解析整个输出
        data = json.loads(output)
        return data.get("tags", {})

    except Exception as e:
        print(f"Warning: LLM tag generation failed: {e}", file=sys.stderr)
        return {}


def validate_and_flatten_tags(tags_dict: Dict[str, List[str]]) -> List[str]:
    """
    验证标签结构并扁平化为列表
    """
    errors = []

    # 检查各类别数量
    if len(tags_dict.get("对象", [])) != 2:
        errors.append(f"对象需要 2 个，当前 {len(tags_dict.get('对象', []))} 个")
    if len(tags_dict.get("场景", [])) != 1:
        errors.append(f"场景需要 1 个，当前 {len(tags_dict.get('场景', []))} 个")
    if len(tags_dict.get("类型", [])) != 1:
        errors.append(f"类型需要 1 个，当前 {len(tags_dict.get('类型', []))} 个")
    if len(tags_dict.get("方法", [])) != 1:
        errors.append(f"方法需要 1 个，当前 {len(tags_dict.get('方法', []))} 个")

    # 扁平化
    all_tags = []
    all_tags.extend(tags_dict.get("对象", [])[:2])
    all_tags.extend(tags_dict.get("场景", [])[:1])
    all_tags.extend(tags_dict.get("类型", [])[:1])
    all_tags.extend(tags_dict.get("方法", [])[:1])

    # 规范化
    normalized = [normalize_tag(t) for t in all_tags if t.strip()]

    # 去重
    seen = set()
    result = []
    for tag in normalized:
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)

    return result


def fallback_tags(title: str, content: str) -> List[str]:
    """
    当 AI 生成失败时的备用标签
    """
    # 从标题提取关键词（简单规则）
    fallback = []

    # 检测常见技术关键词
    text = (title + " " + content[:2000]).lower()

    keyword_map = {
        "claude": "claude",
        "openai": "openai",
        "agent": "智能体",
        "ai": "人工智能",
        "llm": "大语言模型",
        "workflow": "工作流",
        "automation": "自动化",
        "github": "github",
        "python": "python",
        "javascript": "javascript",
    }

    for keyword, tag in keyword_map.items():
        if keyword in text:
            fallback.append(tag)

    # 补充通用标签
    if len(fallback) < 5:
        fallback.extend(["知识管理", "资料归档", "原文备份"])

    return fallback[:5]


def generate_tags(title: str, content: str, source: str = "") -> List[str]:
    """
    生成标签的主函数
    """
    # 调用 LLM 生成结构化标签
    tags_dict = call_llm_for_tags(title, content, source)

    if tags_dict:
        tags = validate_and_flatten_tags(tags_dict)
        if len(tags) >= 4:  # 至少 4 个就算成功
            return tags[:5]

    # 失败时使用备用方案
    return fallback_tags(title, content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--content-file", required=True)
    parser.add_argument("--source", default="")
    parser.add_argument("--minimum", type=int, default=5)
    args = parser.parse_args()

    if not os.path.exists(args.content_file):
        print(json.dumps({
            "success": False,
            "error": {
                "code": "CONTENT_FILE_MISSING",
                "message": f"Content file not found: {args.content_file}",
                "retryable": False,
            },
        }, ensure_ascii=False))
        raise SystemExit(1)

    content = load_content(args.content_file)
    tags = generate_tags(args.title, content, args.source)

    # 确保至少 minimum 个标签
    while len(tags) < args.minimum:
        tags.append("资料归档")

    print(json.dumps({
        "success": True,
        "data": {"tags": tags[:args.minimum]}
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
