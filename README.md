# web-collector

`web-collector` 是一个面向内部收藏场景的 Skill。

它的目标很简单：当用户在聊天中发送一个或多个链接时，默认进入 `internal` 路由，强制通过 `web-access` 抓取网页内容，保留完整原文，整理为 Markdown，并上传到 OneDrive 指定目录下的当天文件夹。

## 适用场景

- 聊天窗口收到网页链接，希望自动收藏
- 需要保留完整原文，而不是只保留摘要
- 需要统一输出为 Markdown 文件
- 需要将结果上传到 OneDrive 个人账号
- 需要每天自动按日期分文件夹归档

不适用：

- 只需要临时阅读，不需要落库
- 希望在抓取失败时自动 fallback 到其他抓取器
- 目标存储不是 OneDrive

## 核心逻辑

`web-collector` 的处理链路如下：

1. 接收一个或多个链接
2. 默认进入 `internal` 路由
3. 做平台检测和 URL 标准化
4. 做 URL 去重
5. 调用 `web-access` 抓取页面
6. 从 `web-access` 页面结果导出原始 Markdown 和 payload
7. 生成中文优先标签
8. 组装最终 Markdown 文件
9. 上传到 OneDrive 基准目录下的当天日期子目录
10. 成功后写入本地缓存，避免重复收藏

## 仓库结构

```text
web-collector/
  README.md
  SKILL.md
  scripts/
    extract_content.py
    deduplicate.py
    export_from_web_access.py
    tag_rules.py
    build_markdown.py
    collect_from_web_access.py
    onedrive_device_code.py
    upload_to_onedrive.py
```

## 依赖与前期准备

### 1. Python

需要 Python 3.9 或更高版本。

### 2. web-access

本仓库不包含浏览器控制器本身，依赖外部 `web-access` Skill 提供：

- Chrome / Chromium CDP 连接
- 本地代理接口
- 页面打开与 DOM 读取能力

`web-collector` 默认假设 `web-access` 代理运行在：

```text
http://127.0.0.1:3456
```

### 3. OneDrive 应用注册

需要先在 Microsoft Entra 中注册一个支持个人 Microsoft 账号的应用，并启用 public client flow。

至少需要：

- `ONEDRIVE_CLIENT_ID`
- `ONEDRIVE_REFRESH_TOKEN`
- `ONEDRIVE_TARGET_PATH`

可选：

- `ONEDRIVE_CLIENT_SECRET`

### 4. OneDrive 首次授权

在本地执行：

```bash
ONEDRIVE_CLIENT_ID="<your-client-id>" \
python3 scripts/onedrive_device_code.py
```

完成浏览器登录后，保存返回的最新 `refresh_token` 到云端密钥管理。

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
WEB_ACCESS_PROXY_ROOT=http://127.0.0.1:3456
```

## OneDrive 路径规则

`ONEDRIVE_TARGET_PATH` 是基准目录。

上传时会自动追加当天日期子目录，例如：

```text
/✒️ 文稿项目/剪藏文件/2026-04-04/
```

每条链接会生成一个独立 Markdown 文件。

## 使用方式

### 方式 1：从已打开的 web-access 页面继续处理

这是推荐方式。

先让 `web-access` 打开页面，拿到 `targetId`，然后执行：

```bash
python3 scripts/export_from_web_access.py --target <TARGET_ID> --output-dir /tmp/web-collector-raw
python3 scripts/collect_from_web_access.py --payload-file /tmp/web-collector-raw/<file>.md.payload.json
```

第一步会生成：

- 原始 Markdown 文件
- 一个 sidecar payload JSON

第二步会自动完成：

- 去重
- 标签生成
- 最终 Markdown 组装
- OneDrive 上传
- 缓存写入

### 方式 2：直接喂给总入口 payload

如果上游系统已经能提供 payload，可以直接执行：

```bash
python3 scripts/collect_from_web_access.py --payload-file /tmp/web-access-export.json
```

payload 格式：

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
python3 scripts/collect_from_web_access.py \
  --payload-file /tmp/web-access-export.json \
  --skip-upload
```

## 标签规则

- 至少生成 5 个标签
- 中文优先
- 英文仅用于产品名、标准术语、API 名、语言名
- 同义词会归一
- 不允许同义词中英混用成两份标签
- 标签最终写入 Markdown 前会做 Obsidian 兼容处理，不保留空格；多词标签会统一成紧凑写法，例如 `CodexCLI`、`MicrosoftGraph`

当前内置了一些基础规则，例如：

- `人工智能`
- `大语言模型`
- `智能体`
- `工作流`
- `自动化`
- `知识管理`
- `Git`
- `Symlink`
- `CodexCLI`

## 部署建议

推荐的云端部署方式：

1. 将本仓库放到 GitHub
2. 云端拉取固定 tag 或固定 commit
3. 通过软链接或固定路径挂到 Skill 目录
4. 用 Secret Manager 注入 OneDrive 凭证
5. 在运行环境中保证 `web-access` 和 Chrome CDP 可用

推荐部署形式：

```text
/opt/skills-src/web-collector
$CODEX_HOME/skills/web-collector -> /opt/skills-src/web-collector
```

不建议：

- 云端直接追 `main` 最新提交
- 把 `refresh_token`、`client_secret` 提交进 Git
- 把测试输出和缓存一并提交到公共仓库

## 部署注意事项

### 1. refresh token 会轮换

每次成功刷新 token 后，微软可能返回新的 `refresh_token`。

生产环境应保存最新值，否则未来可能失效。

### 2. 公共仓库不要提交密钥

请确保以下内容永远不进仓库：

- `ONEDRIVE_REFRESH_TOKEN`
- `ONEDRIVE_CLIENT_SECRET`
- 云端环境配置文件
- 临时输出目录
- `.cache/`

### 3. web-access 是硬依赖

本 Skill 当前不做 fallback。

只要 `web-access` 无法打开页面、读取 DOM 或导出原始 Markdown，流程就会报错停止。

### 4. X / 动态网站依赖浏览器上下文

像 X 这种站点通常必须通过浏览器 DOM 抓取，静态 HTTP 抓取不可靠。

这也是本 Skill 强制依赖 `web-access` 的原因。

## 发布与更新建议

推荐流程：

1. 本地修改并测试
2. 提交到 Git
3. 打 tag，例如 `v0.1.0`
4. 云端部署固定 tag
5. 新版本验证通过后再升级

## 当前限制

- 只做 URL 去重，不做语义去重
- 不做分类字段
- 标签规则仍然是基础版，后续可以继续增强
- 对不同站点的正文提取目前主要依赖 DOM 文本，不是站点专用解析器

## 许可证与公开发布前检查

在上传到公共 GitHub 仓库前，请再次确认：

- 仓库中没有真实 token、secret、cookie
- 仓库中没有本地缓存和调试输出
- README 中没有暴露你的私有 OneDrive 链接或账号信息
