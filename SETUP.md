# Web Collector 配置指南

## 1. 基础依赖

### Python

需要 Python 3.9 或更高版本。

### 抓取器

默认网页抓取依赖 `defuddle`：

```bash
npm install -g defuddle
```

X / Twitter 抓取依赖同级 skill `x-tweet-fetcher`：

```text
$CODEX_HOME/skills/web-collector
$CODEX_HOME/skills/x-tweet-fetcher
```

如果云端目录结构不同，可通过环境变量覆盖：

```bash
export WEB_COLLECTOR_X_TWEET_FETCHER_DIR="/absolute/path/to/x-tweet-fetcher"
```

## 2. OneDrive 配置

### 获取 Microsoft 应用凭证

1. 访问 Azure / Entra 应用注册页面
2. 创建一个支持个人 Microsoft 账号的应用
3. 记录 `Application (client) ID`
4. 启用 public client flow

### 获取 Refresh Token

在本地有浏览器环境的机器执行：

```bash
cd ~/.openclaw/workspace/skills/web-collector
python3 scripts/onedrive_device_code.py
```

完成登录授权后，保存返回的 `refresh_token`。

## 3. 环境变量

至少需要：

```bash
export ONEDRIVE_CLIENT_ID="your_client_id"
export ONEDRIVE_REFRESH_TOKEN="your_refresh_token"
export ONEDRIVE_TARGET_PATH="/Documents/WebClips"
```

可选：

```bash
export WEB_COLLECTOR_OUTPUT_DIR="/tmp/web-collector-output"
export WEB_COLLECTOR_RAW_DIR="/tmp/web-collector-raw"
export WEB_COLLECTOR_X_TWEET_FETCHER_DIR="/opt/skills-src/x-tweet-fetcher"
export WEB_COLLECTOR_USE_AI_TITLE="0"
export ONEDRIVE_TOKEN_CACHE_FILE="/tmp/web-collector-onedrive-token.json"
export ONEDRIVE_TOKEN_CACHE_BUFFER="300"
export WEB_COLLECTOR_ENV_FILE="/root/.openclaw/workspace/skills/web-collector/.env"
```

说明：

- `WEB_COLLECTOR_USE_AI_TITLE=0`
  - 默认保留抓取器提取出的原标题
- `WEB_COLLECTOR_USE_AI_TITLE=1`
  - 允许用 AI 标题覆盖最终标题，同时保留 `original_title`
- `ONEDRIVE_TOKEN_CACHE_FILE`
  - OneDrive access token 本地缓存文件路径
- `ONEDRIVE_TOKEN_CACHE_BUFFER`
  - 提前多久视为即将过期并主动刷新，单位秒
- `WEB_COLLECTOR_ENV_FILE`
  - 显式指定 `.env` 文件路径；默认自动读取 skill 根目录下的 `.env`

说明：

- 入口脚本会自动加载 `.env`
- 如果系统环境里已经 export 了同名变量，则优先使用系统环境值，不会被 `.env` 覆盖

## 4. 测试运行

### 测试导出抓取 payload

```bash
cd ~/.openclaw/workspace/skills/web-collector
python3 scripts/export_from_defuddle.py \
  --url "https://example.com" \
  --output-dir /tmp/web-collector-raw
```

### 测试下游组装但不上传

```bash
python3 scripts/collect_from_defuddle.py \
  --payload-file /tmp/web-collector-raw/<file>.md.payload.json \
  --skip-upload
```

## 5. 当前行为说明

### 抓取器选择

- 普通网页 / 微信公众号 → `defuddle`
- X / Twitter → `x-tweet-fetcher`

### 标签策略

- 默认生成 3 到 5 个标签
- AI 只负责生成候选标签
- 规则层负责：
  - 同义词归一
  - Obsidian 兼容
  - 英文标准词收口
  - 低价值标签过滤

### 标题策略

- 默认使用原始标题
- AI 标题仅作为增强信息

### OneDrive 上传优化

- 上传时优先使用本地缓存的 access token
- token 即将过期或上传返回 `401` 时会自动刷新并重试一次

## 6. 输出格式

生成的 Markdown 文件包含：

- `title`
- `source`
- `source_url`
- `collected_at`
- `route`
- `tags`

在启用 AI 标题覆盖时，还会额外包含：

- `original_title`
- `generated_title`
