---
name: web-collector
description: "当用户在聊天窗口发送一个或多个链接，并希望默认进入内部收藏流程时使用。强制通过 web-access 抓取网页内容，保留完整原文，整理为 Markdown，并上传到 OneDrive 个人账号目录。"
---

# Web Collector

把聊天中的网页链接整理为内部收藏 Markdown 文件，并上传到 OneDrive。

## 什么时候用

在这些场景使用：

- 用户发送一个或多个链接，希望“收藏”“保存”“整理”
- 用户没有特别说明目标流程时，默认进入内部收藏
- 需要强制通过 `web-access` 抓网页内容
- 需要把结果保存到 OneDrive，而不是飞书

不适用：

- 只想看网页摘要，不需要落库
- 需要 fallback 到其他抓取器
- 需要写入飞书文档

## 核心约束

- 默认路由：`internal`
- 一个链接生成一个 Markdown 文件
- 只做 URL 去重
- 不做分类
- 标签至少 5 个
- 标签以中文为主；产品名、API 名、编程语言、标准技术术语可保留英文
- 原文必须完整保留
- 原文先通过 `web-access` 导出为 Markdown，再补充头部元数据
- 网页抓取失败时直接报错，不允许 fallback

## 依赖边界

这里需要明确区分两层：

1. `web-collector` 的依赖
2. 云端如何实现 `web-access`

`web-collector` 本身只依赖 `web-access` 的输出契约，不直接依赖 `OpenClaw browser`。

它真正要求的是：上游最终要能提供一个 payload，至少包含：

```json
{
  "title": "页面标题",
  "url": "https://example.com/post",
  "source": "来源站点",
  "markdown_path": "/tmp/web-collector/raw/example.md",
  "route": "internal"
}
```

如果云端的 `web-access` 恰好是基于 `OpenClaw browser` 实现的，那么：

- `OpenClaw browser` 只是运行环境实现细节
- 不是 `web-collector` 的设计依赖

因此，当云端出现 Chrome/CORS/WebSocket 问题时，应判断为：

- `web-access` 运行环境不满足
- 而不是 `web-collector` 依赖错了工具

运行前真正需要检查的是：

- Chrome / Chromium 是否可用
- CDP 是否可用
- `web-access` proxy 是否可用
- 是否能导出 `markdown_path`

## 工作流

```text
用户发送链接
  -> 拆分为多个 URL
  -> 默认进入 internal 路由
  -> 平台检测
  -> URL 标准化 + 去重
  -> 使用 web-access 抓取页面并导出原始 Markdown
  -> 生成标题 / 来源 / 标签
  -> 组装最终 Markdown
  -> 上传到 OneDrive
  -> 写入本地缓存
```

## 推荐入口

优先使用总入口脚本，而不是逐个手动调用下游脚本。

当 `web-access` 已经导出原始 Markdown 后，使用：

```bash
python3 scripts/collect_from_web_access.py --payload-file /tmp/web-access-export.json
```

其中 `/tmp/web-access-export.json` 至少应包含：

```json
{
  "title": "页面标题",
  "url": "https://example.com/post",
  "source": "站点名",
  "markdown_path": "/tmp/web-collector/raw/example.md",
  "route": "internal"
}
```

这个入口会自动完成：

- URL 去重
- 标签生成
- 最终 Markdown 组装
- 上传到 OneDrive
- 上传成功后写入本地缓存

如果只想先本地验证，不上传远端：

```bash
python3 scripts/collect_from_web_access.py \
  --payload-file /tmp/web-access-export.json \
  --skip-upload
```

## 执行步骤

### 1. 平台检测

运行：

```bash
python3 scripts/extract_content.py "https://example.com/post"
```

只做来源标记，不做抓取器路由切换。输出里的 `skill` 固定为 `web-access`。

### 2. URL 去重

运行：

```bash
python3 scripts/deduplicate.py "https://example.com/post"
```

规则：

- 使用标准化 URL 去重
- 命中本地缓存则跳过该链接
- v1 不做语义去重

### 3. 调用 web-access 导出原文

本 skill 不扩展浏览器控制能力，只依赖 `web-access` 已有能力。

期望上游拿回以下信息：

```json
{
  "title": "页面标题",
  "url": "https://example.com/post",
  "source": "站点名",
  "markdown_path": "/tmp/web-collector/raw/example.md"
}
```

要求：

- `web-access` 必须导出完整正文 Markdown
- 导出失败则停止处理并报错

### 4. 生成标签

运行：

```bash
python3 scripts/tag_rules.py --title "页面标题" --content-file /tmp/web-collector/raw/example.md
```

标签规范：

- 至少 5 个标签
- 默认简体中文
- 同义词统一到同一个标准标签
- 不出现中英同义双份标签
- 英文仅用于专有名词或标准术语

示例规范：

- `AI`、`人工智能` -> `人工智能`
- `LLM`、`大模型`、`大语言模型` -> `大语言模型`
- `Agent`、`智能体` -> `智能体`
- `workflow`、`工作流` -> `工作流`
- `automation`、`自动化` -> `自动化`
- `knowledge management`、`PKM`、`知识管理` -> `知识管理`
- `OpenAI`、`Claude`、`API`、`Python`、`JavaScript` 保留标准写法

### 5. 组装最终 Markdown

运行：

```bash
python3 scripts/build_markdown.py \
  --title "页面标题" \
  --source "来源站点" \
  --url "https://example.com/post" \
  --route internal \
  --content-file /tmp/web-collector/raw/example.md \
  --tags "标签1,标签2,标签3,标签4,标签5"
```

生成结构：

```md
---
title: 页面标题
source: 来源站点
source_url: https://example.com/post
normalized_url: https://example.com/post
collected_at: 2026-04-04T12:00:00+08:00
route: internal
tags:
  - 标签1
  - 标签2
  - 标签3
  - 标签4
  - 标签5
---

# 原文

...完整正文 Markdown...
```

文件名：

- `标题 - YYYY-MM-DD.md`

### 6. OneDrive 认证与上传

首次授权建议在本地执行：

```bash
python3 scripts/onedrive_device_code.py
```

流程：

- 本地完成 Microsoft 账号登录
- 拿到 `refresh_token`
- 将 `refresh_token` 保存到云端密钥环境中

上传运行：

```bash
python3 scripts/upload_to_onedrive.py /path/to/final.md
```

所需环境变量：

- `ONEDRIVE_CLIENT_ID`
- `ONEDRIVE_REFRESH_TOKEN`
- `ONEDRIVE_TARGET_PATH`

目录规则：

- `ONEDRIVE_TARGET_PATH` 作为基准目录
- 上传时自动追加当天日期子目录
- 例如：`/✒️ 文稿项目/剪藏文件/2026-04-04/`

可选环境变量：

- `ONEDRIVE_CLIENT_SECRET`
- `WEB_COLLECTOR_OUTPUT_DIR`

## 脚本

- `scripts/extract_content.py`
- `scripts/deduplicate.py`
- `scripts/tag_rules.py`
- `scripts/build_markdown.py`
- `scripts/collect_from_web_access.py`
- `scripts/onedrive_device_code.py`
- `scripts/upload_to_onedrive.py`

## 错误处理

所有脚本都应尽量输出 JSON 结果。错误格式统一为：

```json
{
  "success": false,
  "error": {
    "code": "CONFIG_MISSING",
    "message": "ONEDRIVE_TARGET_PATH is required",
    "retryable": false
  }
}
```

常见错误码：

- `DUPLICATE_URL`
- `WEB_ACCESS_FAILED`
- `MARKDOWN_EXPORT_FAILED`
- `TAG_GENERATION_FAILED`
- `ONEDRIVE_AUTH_REQUIRED`
- `ONEDRIVE_TOKEN_REFRESH_FAILED`
- `ONEDRIVE_UPLOAD_FAILED`
- `CONFIG_MISSING`

## 运行前提

还需要用户提供或确认：

- OneDrive 目标目录
- `web-access` 在目标运行环境中导出 Markdown 的具体交接方式
