---
name: web-collector
description: "当用户在聊天窗口发送一个或多个链接，并希望默认进入内部收藏流程时使用。根据平台自动选择抓取器提取正文内容，整理为 Markdown，并上传到 OneDrive 个人账号目录。"
---

# Web Collector

把聊天中的网页链接整理为内部收藏 Markdown 文件，并上传到 OneDrive。

这是一个独立 skill，不依赖其他收藏 skill 的目录结构或调度关系。

## 什么时候用

在这些场景使用：

- 用户发送一个或多个链接，希望“收藏”“保存”“整理”
- 用户没有特别说明目标流程时，默认进入内部收藏
- 需要根据平台自动选择合适的抓取器
- 需要把结果保存到 OneDrive，而不是飞书

不适用：

- 只想看网页摘要，不需要落库
- 需要自动 fallback 到其他抓取器
- 需要写入飞书文档

## 核心约束

- 默认路由：`internal`
- 一个链接生成一个 Markdown 文件
- 只做 URL 去重
- 不做分类
- 标签默认输出 3 到 5 个
- 标签只允许来自三类：核心对象、AI 概念、业务场景
- AI 概念统一英文标准词且不能有空格；业务场景统一中文
- 网页抓取失败时直接报错，不允许 fallback
- 下游 payload 契约保持稳定

## 当前抓取器

- `defuddle`
  - 默认网页抓取器
  - 负责通用网页、微信公众号及当前其他默认平台
- `x-tweet-fetcher`
  - X / Twitter 专用抓取器
  - 当前只接入单条 Tweet / X Article 抓取

## 依赖边界

`web-collector` 本身只依赖“抓取器输出契约”，不直接依赖某一个抓取实现。

上游最终至少要能提供一个 payload：

```json
{
  "title": "页面标题",
  "url": "https://example.com/post",
  "source": "来源站点",
  "markdown_path": "/tmp/web-collector/raw/example.md",
  "route": "internal"
}
```

## 工作流

```text
用户发送链接
  -> 拆分为多个 URL
  -> 默认进入 internal 路由
  -> 平台检测
  -> 选择抓取器
  -> 导出原始 Markdown
  -> 生成标题 / 来源 / 标签
  -> 组装最终 Markdown
  -> 上传到 OneDrive
  -> 写入本地缓存
```

## 推荐入口

优先使用总入口脚本，而不是逐个手动调用下游脚本。

抓取入口脚本名暂时保留为：

```bash
python3 scripts/export_from_defuddle.py --url "https://example.com/post"
```

虽然脚本名还是 `defuddle`，但内部已经会根据平台自动选择抓取器。

当原始 Markdown 已经导出后，使用：

```bash
python3 scripts/collect_from_defuddle.py --payload-file /tmp/extractor-export.json
```

## 标签与标题

- AI 只生成候选标签，规则层负责最终规范化
- 标签会统一做：
  - 同义词归一
  - Obsidian 兼容
  - 英文标准词收口
  - 低价值标签过滤
- 默认保留抓取器提取出的原标题
- AI 标题只作为增强信息保留；如需覆盖主标题，可通过 `WEB_COLLECTOR_USE_AI_TITLE=1` 启用

## 平台检测

运行：

```bash
python3 scripts/extract_content.py "https://x.com/user/status/123"
```

输出会包含：

- `platform_id`
- `platform_label`
- `skill`
- `extractor`

其中：

- `skill` 是兼容字段
- `extractor` 是内部标准字段，表示实际选中的抓取器

## 脚本

- `scripts/extract_content.py`
- `scripts/export_from_defuddle.py`
- `scripts/collect_from_defuddle.py`
- `scripts/build_markdown.py`
- `scripts/deduplicate.py`
- `scripts/tag_rules.py`
- `scripts/upload_to_onedrive.py`
- `scripts/onedrive_device_code.py`
- `scripts/extractors/registry.py`
- `scripts/extractors/defuddle_extractor.py`
- `scripts/extractors/twitter_extractor.py`

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
- `DEFUDDLE_FAILED`
- `TWITTER_FETCH_FAILED`
- `MARKDOWN_EXPORT_FAILED`
- `TAG_GENERATION_FAILED`
- `ONEDRIVE_AUTH_REQUIRED`
- `ONEDRIVE_TOKEN_REFRESH_FAILED`
- `ONEDRIVE_UPLOAD_FAILED`
- `CONFIG_MISSING`

## 运行前提

还需要用户提供或确认：

- OneDrive 目标目录
- `defuddle` 在目标运行环境中可用
- `x-tweet-fetcher` 在目标运行环境中可访问
