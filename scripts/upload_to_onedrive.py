#!/usr/bin/env python3
"""
Refresh a personal OneDrive token and upload a markdown file to a configured target path.
"""

import json
import mimetypes
import os
import sys
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from datetime import datetime


TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
DEFAULT_SCOPE = "Files.ReadWrite offline_access"

# 代理设置
PROXY_HOST = os.environ.get("ONEDRIVE_PROXY_HOST", "127.0.0.1:7890")


def get_proxy_handler():
    """创建代理处理器"""
    proxy_url = f"http://{PROXY_HOST}"
    return urllib.request.ProxyHandler({
        'http': proxy_url,
        'https': proxy_url
    })


def error(code: str, message: str, retryable: bool = False) -> None:
    print(json.dumps({
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
        },
    }, ensure_ascii=False))
    raise SystemExit(1)


def post_form(url: str, payload: dict) -> dict:
    body = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    
    # 使用代理
    proxy_handler = get_proxy_handler()
    opener = urllib.request.build_opener(proxy_handler)
    
    with opener.open(request) as response:
        return json.loads(response.read().decode("utf-8"))


def refresh_access_token() -> dict:
    client_id = os.environ.get("ONEDRIVE_CLIENT_ID")
    refresh_token = os.environ.get("ONEDRIVE_REFRESH_TOKEN")
    client_secret = os.environ.get("ONEDRIVE_CLIENT_SECRET")
    scope = os.environ.get("ONEDRIVE_SCOPE", DEFAULT_SCOPE)

    if not client_id:
        error("CONFIG_MISSING", "ONEDRIVE_CLIENT_ID is required")
    if not refresh_token:
        error("CONFIG_MISSING", "ONEDRIVE_REFRESH_TOKEN is required")

    payload = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": scope,
    }
    if client_secret:
        payload["client_secret"] = client_secret

    try:
        return post_form(TOKEN_URL, payload)
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        error("ONEDRIVE_TOKEN_REFRESH_FAILED", details)


def resolve_target_dir(base_target_dir: str) -> str:
    normalized = base_target_dir.strip().strip("/")
    date_folder = datetime.now().strftime("%Y-%m-%d")
    if normalized:
        return f"{normalized}/{date_folder}"
    return date_folder


def build_upload_url(target_dir: str, filename: str) -> str:
    normalized = target_dir.strip().strip("/")
    if normalized:
        remote_path = f"{normalized}/{filename}"
    else:
        remote_path = filename
    encoded_segments = "/".join(urllib.parse.quote(segment) for segment in remote_path.split("/"))
    return f"{GRAPH_ROOT}/me/drive/root:/{encoded_segments}:/content"


def upload_file(file_path: str, access_token: str, target_dir: str) -> dict:
    filename = os.path.basename(file_path)
    upload_url = build_upload_url(target_dir, filename)
    content_type = mimetypes.guess_type(filename)[0] or "text/markdown"

    with open(file_path, "rb") as handle:
        body = handle.read()

    request = urllib.request.Request(upload_url, data=body, method="PUT")
    request.add_header("Authorization", f"Bearer {access_token}")
    request.add_header("Content-Type", content_type)
    
    # 使用代理
    proxy_handler = get_proxy_handler()
    opener = urllib.request.build_opener(proxy_handler)

    with opener.open(request) as response:
        return json.loads(response.read().decode("utf-8"))


def upload_markdown_file(file_path: str) -> dict:
    file_path = os.path.abspath(file_path)
    if not os.path.exists(file_path):
        error("FILE_NOT_FOUND", f"File not found: {file_path}")

    base_target_dir = os.environ.get("ONEDRIVE_TARGET_PATH")
    if not base_target_dir:
        error("CONFIG_MISSING", "ONEDRIVE_TARGET_PATH is required")
    target_dir = resolve_target_dir(base_target_dir)

    tokens = refresh_access_token()
    access_token = tokens.get("access_token")
    if not access_token:
        error("ONEDRIVE_TOKEN_REFRESH_FAILED", "No access_token returned from refresh flow")

    try:
        result = upload_file(file_path, access_token, target_dir)
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        error("ONEDRIVE_UPLOAD_FAILED", details)

    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "web_url": result.get("webUrl"),
        "size": result.get("size"),
        "target_dir": target_dir,
        "parent_path": result.get("parentReference", {}).get("path"),
        "refreshed_refresh_token": tokens.get("refresh_token"),
    }


def main() -> None:
    if len(sys.argv) < 2:
        error("INVALID_INPUT", "Usage: python3 upload_to_onedrive.py <file_path>")

    result = upload_markdown_file(sys.argv[1])
    print(json.dumps({"success": True, "data": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()