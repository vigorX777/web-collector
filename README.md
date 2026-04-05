# web-collector

`web-collector` 是一个面向内部收藏场景的独立 Skill。

它的目标是：当用户在聊天中发送一个或多个链接时，默认进入 `internal` 路由，根据平台自动选择合适的抓取器提取正文内容，整理为 Markdown，并上传到 OneDrive 指定目录下的当天文件夹。

## 适用场景

- 聊天窗口收到网页链接，希望自动收藏
- 需要保留原文内容，而不是只保留摘要
- 需要统一输出为 Markdown 文件
- 需要将结果上传到 OneDrive 个人账号
- 需要为不同平台逐步接入不同抓取器

不适用：

- 只需要临时阅读，不需要落库
- 希望在抓取失败时自动 fallback 到其他抓取器
- 目标存储不是 OneDrive

## 核心逻辑

`web-collector` 的处理链路如下：

1. 接收一个或多个链接
2. 默认进入 `internal` 路由
3. 做平台检测和 URL 标准化
4. 根据平台注册表选择抓取器
5. 抓取器导出原始 Markdown 和 payload
6. 做 URL 去重
7. 生成中文优先标签
8. 组装最终 Markdown 文件
9. 上传到 OneDrive 基准目录下的当天日期子目录
10. 成功后写入本地缓存，避免重复收藏

## 当前抓取器

| 平台 | 抓取器 | 说明 |
|------|--------|------|
| 普通网页 / 微信公众号 / 现有默认平台 | `defuddle` | 默认抓取器，支持通用网页正文提取，包含微信公众号普通文与短文适配 |
| X / Twitter | `x-tweet-fetcher` | 当前只接入单条 Tweet / X Article 抓取，不包含 replies / timeline / monitor |

## 仓库结构

```text
web-collector/
  README.md
  SKILL.md
  scripts/
    extract_content.py
    export_from_defuddle.py
    collect_from_defuddle.py
    build_markdown.py
    deduplicate.py
    tag_rules.py
    upload_to_onedrive.py
    onedrive_device_code.py
    extractors/
      registry.py
      shared.py
      defuddle_extractor.py
      twitter_extractor.py
```

## 依赖与前期准备

### 1. Python

需要 Python 3.9 或更高版本。

### 2. 抓取器依赖

默认网页抓取依赖 `defuddle` CLI：

```bash
npm install -g defuddle
```

Twitter 抓取依赖同级 skill `x-tweet-fetcher`，默认按 sibling skill 目录查找：

```text
$CODEX_HOME/skills/web-collector
$CODEX_HOME/skills/x-tweet-fetcher
```

如果云端目录结构不同，可通过环境变量覆盖：

```bash
WEB_COLLECTOR_X_TWEET_FETCHER_DIR=/absolute/path/to/x-tweet-fetcher
```

### 3. OneDrive 应用注册

需要先在 Microsoft Entra 中注册一个支持个人 Microsoft 账号的应用，并启用 public client flow。

至少需要：

- `ONEDRIVE_CLIENT_ID`
- `ONEDRIVE_REFRESH_TOKEN`
- `ONEDRIVE_TARGET_PATH`

可选：

- `ONEDRIVE_CLIENT_SECRET`

## 环境变量

### 必需

```bash
ONEDRIVE_CLIENT_ID=<your-client-id>
ONEDRIVE_REFRESH_TOKEN=<your-refresh-token>
ONEDRIVE_TARGET_PATH=/✒️ 文稿项目/剪藏文件
```

### 可选

```bash
ONEDRIVE_CLIENT_SECRET=<optional>
WEB_COLLECTOR_OUTPUT_DIR=/tmp/web-collector-output
WEB_COLLECTOR_RAW_DIR=/tmp/web-collector-raw
WEB_COLLECTOR_X_TWEET_FETCHER_DIR=/opt/skills-src/x-tweet-fetcher
```

## 使用方式

### 方式 1：直接抓取 URL 并继续处理

这是推荐方式。入口脚本名暂时仍保留 `export_from_defuddle.py`，但内部已经会按平台自动选择抓取器。

```bash
python3 scripts/export_from_defuddle.py --url "https://example.com/post" --output-dir /tmp/web-collector-raw
python3 scripts/collect_from_defuddle.py --payload-file /tmp/web-collector-raw/<file>.md.payload.json
```

第一步会自动：

- 检测平台
- 选择抓取器
- 生成原始 Markdown 文件
- 生成 sidecar payload JSON

第二步会自动完成：

- 去重
- 标签生成
- 最终 Markdown 组装
- OneDrive 上传
- 缓存写入

### 方式 2：直接喂给总入口 payload

如果上游系统已经能提供 payload，可以直接执行：

```bash
python3 scripts/collect_from_defuddle.py --payload-file /tmp/extractor-export.json
```

payload 至少包含：

```json
{
  "title": "页面标题",
  "url": "https://example.com/post",
  "source": "来源站点",
  "markdown_path": "/tmp/web-collector-raw/example.md",
  "route": "internal"
}
```

### 方式 3：本地只验证，不上传 OneDrive

```bash
python3 scripts/collect_from_defuddle.py \
  --payload-file /tmp/extractor-export.json \
  --skip-upload
```

## 平台检测输出

运行：

```bash
python3 scripts/extract_content.py "https://x.com/user/status/123"
```

返回结果会包含：

- `platform_id`
- `platform_label`
- `skill`
- `extractor`

其中：

- `skill` 保留为兼容字段
- `extractor` 是当前内部标准字段，表示实际选中的抓取器

## 标签规则

- 至少生成 5 个标签
- 中文优先
- 英文仅用于产品名、标准术语、API 名、语言名
- 同义词会归一
- 不允许同义词中英混用成两份标签

## 部署建议

推荐的云端部署方式：

1. 将本仓库放到 GitHub
2. 云端拉取固定 tag 或固定 commit
3. 通过软链接或固定路径挂到 Skill 目录
4. 用 Secret Manager 注入 OneDrive 凭证
5. 在运行环境中保证所需抓取器可用

## 部署注意事项

### 1. 无 fallback

本 Skill 当前不做 fallback。

平台一旦选定抓取器，抓取失败就会直接报错停止。

### 2. 当前检查项

部署时真正应该检查的是：

- `defuddle` 命令是否可用
- `x-tweet-fetcher` 路径是否可访问
- 目标 URL 是否可访问
- 是否能成功导出 `markdown_path`

## 当前限制

- 只做 URL 去重，不做语义去重
- 不做分类字段
- 标签规则仍然是基础版，后续可以继续增强
- X / Twitter 当前只支持单条 Tweet / X Article，不支持 replies / timeline
- 新平台需要通过新增适配器模块接入，不会自动发现外部 skill

## 变更日志

后续每次功能、接口、文档或依赖变更，都应在这里按日期追加记录，最新变更放在最上面。

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| `v0.3.0` | `2026-04-05` | 将抓取层改造成平台注册表 + 可插拔适配器架构；新增 Twitter/X 抓取器接入，通过 `x-tweet-fetcher` 处理单条 Tweet / X Article；保留原有导出入口脚本名以兼容现有调用方。 |
| `v0.2.2` | `2026-04-05` | 新增微信公众号专用正文提取逻辑：优先提取 `#js_content`，短文场景回退到 `text_page_info.content_noencode`，解决公众号短文正文抓取不完整的问题。 |
| `v0.2.1` | `2026-04-05` | 新增微信公众号正文噪音过滤规则，屏蔽“继续滑动看下一个”“向上滑动看下一个”“知道了”“微信扫一扫”“使用小程序”以及点赞、在看、分享、留言、收藏等交互提示文案。 |
| `v0.2.0` | `2026-04-05` | 将内容抓取链路从 `web-access` 全量替换为 `defuddle`；新增 `scripts/export_from_defuddle.py`；将 `scripts/collect_from_web_access.py` 重命名为 `scripts/collect_from_defuddle.py`；更新 `scripts/extract_content.py` 中的抓取器标记；清理 README 和 SKILL 中与 Chrome、CDP、proxy、`targetId` 相关的旧说明。 |
