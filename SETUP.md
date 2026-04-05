# Web Collector 配置指南

## 安装状态
✅ Skill 已安装到 `~/.openclaw/workspace/skills/web-collector`
✅ 旧 content-collector-skill 已禁用

## 配置步骤

### 1. 获取 Microsoft 应用凭证

1. 访问 https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade
2. 点击 "New registration"
3. 填写应用名称（如：WebCollector）
4. 选择 "Personal Microsoft accounts only"
5. 点击 "Register"
6. 记录 **Application (client) ID**

### 2. 获取 Refresh Token

在本地机器（有浏览器环境）执行：

```bash
cd ~/.openclaw/workspace/skills/web-collector
python3 scripts/onedrive_device_code.py
```

按照提示：
1. 复制显示的 code
2. 访问 https://microsoft.com/devicelogin
3. 登录你的 Microsoft 账号
4. 授权应用访问 OneDrive
5. 脚本会输出 refresh_token，保存好

### 3. 配置环境变量

在 OpenClaw 环境中设置：

```bash
export ONEDRIVE_CLIENT_ID="your_client_id"
export ONEDRIVE_REFRESH_TOKEN="your_refresh_token"
export ONEDRIVE_TARGET_PATH="/Documents/WebClips"
```

或者写入 `~/.openclaw/workspace/skills/web-collector/.env` 文件

### 4. 测试运行

```bash
# 测试单个链接
cd ~/.openclaw/workspace/skills/web-collector/scripts
python3 collect_from_web_access.py \
  --url "https://example.com" \
  --title "Example Page" \
  --source "example.com" \
  --markdown-path /tmp/test.md \
  --skip-upload
```

## 使用方式

发送链接时说"收藏"，系统会自动：
1. 使用 web-access skill 抓取页面
2. 生成标签（至少5个）
3. 组装 Markdown（含元数据头部）
4. 上传到 OneDrive
5. 写入本地缓存

## 输出格式

生成的 Markdown 文件示例：

```markdown
---
title: 页面标题
source: 站点名
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

文件名格式：`标题 - YYYY-MM-DD.md`

存储路径：`ONEDRIVE_TARGET_PATH/YYYY-MM-DD/`
