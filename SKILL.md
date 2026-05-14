---
name: web-collector
description: "当用户在聊天窗口发送一个或多个链接，并希望默认进入内部收藏流程时使用。根据平台自动选择抓取器提取正文内容，整理为 Markdown，并上传到 OneDrive 个人账号目录。"
---

# Web Collector

把聊天中的网页链接整理为内部收藏 Markdown 文件，并上传到 OneDrive。

这是一个独立 skill，不依赖其他收藏 skill 的目录结构或调度关系。

## 什么时候用

在这些场景使用：

- 用户发送一个或多个链接，希望"收藏""保存""整理"
- 用户没有特别说明目标流程时，默认进入内部收藏
- **用户在聊天中发送任何链接，默认即走此 skill**（已设为用户偏好）
- 需要根据平台自动选择合适的抓取器
- 需要把结果保存到 OneDrive，而不是飞书

不适用：

- 只想看网页摘要，不需要落库
- 需要自动 fallback 到其他抓取器
- 需要写入飞书文档

## 运行前提

### 必须安装

```bash
sudo npm install -g defuddle
```

`defuddle` 是通用网页和微信公众号的抓取器。微信文章走 `defuddle_extractor.extract_wechat()` 内建路径（fetch HTML → 提取 js_content → 包成最小 HTML → `defuddle parse --md`），其他网页走 `defuddle parse --json --md` 直接抓取。

### Twitter/X 支持

X/Twitter 抓取依赖 `x-tweet-fetcher` 外部 skill（不在本仓库内）：

```bash
bash scripts/setup.sh
```

`setup.sh` 自动将 `x-tweet-fetcher` 克隆/更新到 `openclaw-imports/x-tweet-fetcher/`，源仓库为 `ythx-101/x-tweet-fetcher`。抓取器入口在 `x-tweet-fetcher/scripts/fetch_tweet.py`。可通过 `WEB_COLLECTOR_X_TWEET_FETCHER_DIR` 环境变量自定义路径。

### OneDrive 配置（`.env` 文件）

skill 根目录的 `.env` 需要包含：

- `ONEDRIVE_CLIENT_ID` — Azure App Registration
- `ONEDRIVE_REFRESH_TOKEN` — 通过 device code flow 获取
- `ONEDRIVE_TARGET_PATH` — OneDrive 中的目标目录（如 `/✒️ 文稿项目/剪藏文件`）
- `WEB_COLLECTOR_OUTPUT_DIR` — 本地缓存目录
- `ONEDRIVE_PROXY_HOST` — 可选，HTTP 代理地址（如 `127.0.0.1:7890`）。服务器在国内无法直连 Microsoft 时必填。`upload_to_onedrive.py` 自动读取此变量走代理，未设置则直连。

**迁移注意**：从 OpenClaw 迁移到 Hermes 后，`.env` 中的路径必须更新。旧路径如 `/root/.openclaw/workspace/skills/web-collector/...` 需要改为 Hermes 技能目录下的路径。详见 `references/hermes-migration.md`。

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

所有入口脚本会自动加载 skill 根目录下的 `.env`，系统环境变量优先于 `.env`。

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

- `scripts/setup.sh` — 初始化/更新外部依赖
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

## 常见问题与回退策略

### AI 分析不可用 ✅ 双模式支持 (2026-05-14)

`ai_content_analyzer.py` 支持两种后端，按环境自动切换：

| 环境 | 模式 | 后端 |
|------|------|------|
| OpenClaw | `openclaw` | `openclaw agent --local` CLI |
| Hermes | `api` | OpenAI 兼容 API（自动读 Hermes config.yaml） |

**自动检测**：检查 `openclaw` CLI 是否存在，有则 OpenClaw 模式，无则 API 模式。  
**手动覆盖**：`AI_ANALYSIS_MODE=openclaw` 或 `--mode api` CLI 参数。  
**降级**：失败时输出 Warning，回退到 `tag_rules.py` 规则标签。  
**代理**：API 模式通过系统 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量自动走代理（Python urllib 默认行为），无需额外配置。如需不走代理（如国内 API），在 `NO_PROXY` 中加对应域名。

> ⚠️ API 模式默认使用 `deepseek-v4-flash`。不要改用 `v4-pro` 等推理模型——详见 `references/deepseek-reasoning-pitfall.md`。

### OneDrive 上传失败

常见原因：

1. **Refresh token 过期** — token 生命周期有限，过期后需重新授权。

**Agent 环境专用：两阶段授权流程**

> ⚠️ 绝对不要用 `execute_code` 跑 OAuth 交互流程 —— 用户看不到中间输出，验证码永远浪费。  
> ⚠️ 不要用 `terminal` 前台跑 `poll` —— 5-15 分钟阻塞整个对话。

正确分两步，用不同的 Hermes 工具：

```
第 1 步（terminal 前台）：获取验证码
  python3 scripts/onedrive_device_code.py request
  → 用户立即看到 code → 去浏览器授权

第 2 步（terminal 后台）：轮询等 token
  python3 scripts/onedrive_device_code.py poll --update-env
  → terminal(background=true), notify_on_complete=true
  → 拿到 refresh_token 自动写入 .env
```

也支持旧的单次阻塞模式：`python3 scripts/onedrive_device_code.py`（交互式终端可用）
2. **网络不通** — 服务器需能访问 `login.microsoftonline.com` 和 `graph.microsoft.com`
3. **Token 被撤销** — 密码变更或安全策略触发

**降级方案**：使用 `--skip-upload` 参数跳过上传，仅本地保存：

```bash
python3 scripts/collect_from_defuddle.py --payload-file payload.json --skip-upload
```

### 环境迁移（OpenClaw → Hermes）

从 OpenClaw 迁移到 Hermes 后需检查：

- `.env` 中的 `WEB_COLLECTOR_OUTPUT_DIR` 路径（旧：`/root/.openclaw/...`）
- `defuddle` 是否已安装（`which defuddle`）
- OneDrive token 是否仍然有效
- `openclaw` CLI 已不存在，✅ 已适配：AI 分析自动切换到 API 模式

详见 `references/hermes-migration.md`。

## 参考文档

- `references/hermes-migration.md` — OpenClaw → Hermes 迁移完整记录
- `references/agent-oauth-pattern.md` — Agent 环境下 OAuth 设备码两阶段模式（可复用于任何 OAuth 流）
