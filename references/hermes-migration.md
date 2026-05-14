# web-collector: OpenClaw → Hermes 迁移记录

## 日期：2026-05-13

## 迁移时发现的问题

### 1. `defuddle` CLI 未安装

旧 OpenClaw 环境可能预装了 `defuddle`，Hermes 环境没有。

**修复**：
```bash
sudo npm install -g defuddle
```

验证：`which defuddle && defuddle --version` → `/usr/bin/defuddle` v0.18.1

### 2. `.env` 路径指向旧 OpenClaw 目录

错误：`PermissionError: [Errno 13] Permission denied: '/root/.openclaw'`

根因：`.env` 中 `WEB_COLLECTOR_OUTPUT_DIR=/root/.openclaw/workspace/skills/web-collector/.cache/output`

**修复**：改为 Hermes 技能目录路径：
```
WEB_COLLECTOR_OUTPUT_DIR=/home/ubuntu/.hermes/skills/openclaw-imports/web-collector/.cache/output
```

### 3. AI 分析依赖 `openclaw` CLI

`scripts/ai_content_analyzer.py` 调用：
```python
["openclaw", "agent", "--local", "--session-id", session_id, "-m", prompt]
```

Hermes 上没有 `openclaw` CLI，调用抛出 `FileNotFoundError`，被 `collect_from_defuddle.py` 捕获为 Warning，AI 生成的标题/摘要/候选标签全部为空。

**当前状态**：降级运行，标签由 `tag_rules.py` 的 fallback 规则生成。

**待修复**：改为调用 Hermes 的 LLM 接口。

### 4. OneDrive 认证

- Token 生成日期：2026-04-04
- 当前状态：已重新授权（2026-05-14），refresh token 已更新
- 附加问题：服务器到 `login.microsoftonline.com` 网络不通（Connection refused，临时问题，已恢复）

**重要：`onedrive_device_code.py` 已优化为两阶段模式**

旧版是单次阻塞调用，在 Agent 环境（Hermes/OpenClaw）中不可用：用户看不到 `execute_code` 的中间输出，代码和设备码容易不匹配。

新版拆分为两个子命令：

```bash
# 阶段 1：获取验证码 → 输出给人看 → 保存 device_code → 立即退出
python3 scripts/onedrive_device_code.py request

# 阶段 2：读取 device_code → 轮询 → 拿到 token → --update-env 自动写回 .env
python3 scripts/onedrive_device_code.py poll --update-env
```

给 Agent 的标准流程：`request` 在 foreground 跑 → 用户看到验证码 → 用户去浏览器授权 → `poll --update-env` 在 background 跑 → 完成。

旧版 `python3 scripts/onedrive_device_code.py`（无参数）仍可用，适合交互式终端。

## 已验证可用的回退流程

当 OneDrive 不可用时，完整本地收藏流程：

```bash
# 1. 平台检测
python3 scripts/extract_content.py "https://mp.weixin.qq.com/s/xxx"

# 2. 抓取 + 导出 Markdown
python3 scripts/export_from_defuddle.py --url "https://mp.weixin.qq.com/s/xxx"

# 3. 收集（本地保存，跳过 OneDrive 上传）
python3 scripts/collect_from_defuddle.py \
  --payload-file .cache/raw/<标题>.md.payload.json \
  --skip-upload
```

输出文件在 `WEB_COLLECTOR_OUTPUT_DIR` 下。
