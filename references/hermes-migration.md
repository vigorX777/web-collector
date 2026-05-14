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

### 3. AI 分析依赖 `openclaw` CLI ✅ 双模式支持 (2026-05-14)

`scripts/ai_content_analyzer.py` 原本调用：
```python
["openclaw", "agent", "--local", "--session-id", session_id, "-m", prompt]
```

**修复**：改为双模式架构，按环境自动切换：

| 环境 | 模式 | 后端 |
|------|------|------|
| OpenClaw | `openclaw` | `openclaw agent --local` CLI（原有实现，保留） |
| Hermes | `api` | OpenAI 兼容 API（自动读 `~/.hermes/config.yaml`） |

- **自动检测**：`shutil.which("openclaw")` → 有则 OpenClaw，无则 API
- **手动覆盖**：`AI_ANALYSIS_MODE=openclaw` 或 `--mode api` CLI 参数
- **API 配置**：自动读取 Hermes `config.yaml` 中的 `base_url` / `api_key` / `model`，也支持环境变量覆盖

**踩坑：DeepSeek V4 Pro 是推理模型**
- V4 Pro 把输出放在 `reasoning_content` 字段，`content` 经常为空
- `max_tokens` 不够时，所有 token 被推理消耗，最终答案消失
- **解决**：默认模型改为 `deepseek-v4-flash`（非推理模型，`content` 直接有输出，且更便宜）

**结果**：AI 分析恢复正常，输出 5 个标签 + 详细摘要。失败时静默降级到 `tag_rules.py` 回退规则。

### 5. 上传脚本代理硬编码 ✅ 已修复 (2026-05-14)

`scripts/upload_to_onedrive.py` 原本硬编码代理 `127.0.0.1:7890`：
```python
PROXY_HOST = os.environ.get("ONEDRIVE_PROXY_HOST", "127.0.0.1:7890")
```

OpenClaw 环境有代理，Hermes 服务器没有 → 所有 HTTP 请求 `ConnectionRefused`。

**修复**：代理改为可选。`get_proxy_handler()` 读取 `ONEDRIVE_PROXY_HOST` 环境变量，未设置时使用空 `ProxyHandler`（直连），并移除硬编码默认值。

### 4. OneDrive 认证

- Token 生成日期：2026-04-04
- 当前状态：已重新授权（2026-05-14），refresh token 已更新
- 附加问题：服务器到 `login.microsoftonline.com` 网络不通（Connection refused，临时问题，已恢复）

**重要：`onedrive_device_code.py` 已优化为两阶段模式**

旧版是单次阻塞调用，在 Agent 环境（Hermes/OpenClaw）中不可用。根本原因是 Hermes 工具的约束：

- `execute_code`：输出只在脚本**完全结束后**才展示给用户。OAuth 的"请打开浏览器输入 XXX"永远不会被用户看到，验证码白白过期。
- `terminal` 前台：用户能看到输出，但 `poll` 阶段会阻塞 5-15 分钟，整个对话卡死。
- `terminal` 后台：用户可以继续对话，但脚本自己重新 `curl` 拿 device_code 会导致和用户看到的 code 不匹配。

**解决方案**：拆分为两个独立子命令，用不同 Hermes 工具跑：

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
