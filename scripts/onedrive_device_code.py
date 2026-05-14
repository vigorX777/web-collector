#!/usr/bin/env python3
"""
OneDrive OAuth device code flow for personal accounts.

Two-phase mode (recommended for agent environments):
  python3 onedrive_device_code.py request     # Get device code, print for user
  python3 onedrive_device_code.py poll --update-env  # Poll for token, update .env

Legacy single-run mode:
  python3 onedrive_device_code.py             # Request + poll in one blocking call

Why two-phase:
  In agent environments (Hermes, OpenClaw), "tell the user a code" and "poll for
  5 minutes" must be separate steps. The user can't see execute_code output until
  it finishes, and terminal foreground blocks the conversation. Two-phase lets the
  agent show the code immediately, then poll in background.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

from env_loader import load_env_file

DEVICE_CODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
SCOPES = "offline_access Files.ReadWrite"

# Where device_code is saved between request and poll phases
DEVICE_CODE_CACHE = ".cache/device_code.json"

# Path to .env (relative to script's skill root)
ENV_FILE = ".env"

load_env_file()


def _skill_root() -> Path:
    """Resolve skill root directory (where .env and .cache live)."""
    return Path(__file__).resolve().parent.parent


def post_form(url: str, payload: dict) -> dict:
    encoded = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=encoded, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {details}") from error


def request_device_code(client_id: str) -> dict:
    return post_form(DEVICE_CODE_URL, {"client_id": client_id, "scope": SCOPES})


def poll_token(client_id: str, device_code: str, interval: int,
               expires_in: int, timeout: int | None = None) -> dict:
    deadline = time.time() + min(expires_in, timeout or expires_in)
    while time.time() < deadline:
        time.sleep(interval)
        try:
            return post_form(TOKEN_URL, {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": client_id,
                "device_code": device_code,
            })
        except RuntimeError as error:
            message = str(error)
            payload_text = message.split(": ", 1)[1] if ": " in message else "{}"
            payload = json.loads(payload_text)
            err = payload.get("error")
            if err in {"authorization_pending", "slow_down"}:
                if err == "slow_down":
                    interval += 5
                continue
            raise RuntimeError(payload.get("error_description", err))
    raise RuntimeError(
        f"Device code not authorized within {timeout or expires_in}s "
        f"({'timeout' if timeout else 'expired'})")


def _get_client_id() -> str:
    client_id = os.environ.get("ONEDRIVE_CLIENT_ID")
    if not client_id:
        print(json.dumps({
            "success": False,
            "error": {
                "code": "CONFIG_MISSING",
                "message": "ONEDRIVE_CLIENT_ID is required in .env",
                "retryable": False,
            },
        }, ensure_ascii=False))
        sys.exit(1)
    return client_id


def _update_env_file(refresh_token: str) -> None:
    """Write the refresh_token back to .env."""
    env_path = _skill_root() / ENV_FILE
    if not env_path.exists():
        print(f"[WARN] .env not found at {env_path}", file=sys.stderr)
        return

    content = env_path.read_text()
    new_content = re.sub(
        r'^ONEDRIVE_REFRESH_TOKEN=.*',
        f'ONEDRIVE_REFRESH_TOKEN={refresh_token}',
        content,
        flags=re.MULTILINE,
    )
    env_path.write_text(new_content)
    print(f"[OK] {env_path} updated with new refresh_token", file=sys.stderr)


# ── Subcommand: request ──────────────────────────────────────────────

def cmd_request() -> None:
    """Get device code, print it for the user, save device_code for poll phase."""
    client_id = _get_client_id()

    try:
        device = request_device_code(client_id)
    except RuntimeError as error:
        print(json.dumps({
            "success": False,
            "error": {
                "code": "ONEDRIVE_AUTH_REQUIRED",
                "message": str(error),
                "retryable": False,
            },
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    user_code = device["user_code"]
    verification_uri = device["verification_uri"]
    expires_in = int(device.get("expires_in", 900))

    # Human-readable output (the agent relays this to the user)
    print(f"""
╔══════════════════════════════════════════╗
║  OneDrive 授权                           ║
╠══════════════════════════════════════════╣
║  浏览器打开: {verification_uri:<28s} ║
║  输入验证码: {user_code:<28s} ║
║  有效期:     {expires_in // 60} 分钟{'':<25s} ║
╚══════════════════════════════════════════╝
""")

    # Save device_code for poll phase
    cache_path = _skill_root() / DEVICE_CODE_CACHE
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({
        "device_code": device["device_code"],
        "client_id": client_id,
        "expires_in": expires_in,
        "interval": int(device.get("interval", 5)),
        "created_at": time.time(),
    }, ensure_ascii=False, indent=2))

    # Also output machine-readable JSON to stdout (for scripting)
    print(json.dumps({
        "success": True,
        "data": {
            "user_code": user_code,
            "verification_uri": verification_uri,
            "expires_in": expires_in,
            "message": device.get("message"),
        },
    }, ensure_ascii=False))


# ── Subcommand: poll ─────────────────────────────────────────────────

def cmd_poll(update_env: bool = False, timeout: int | None = None) -> None:
    """Read saved device_code, poll for token, optionally update .env."""
    cache_path = _skill_root() / DEVICE_CODE_CACHE

    if not cache_path.exists():
        print(json.dumps({
            "success": False,
            "error": {
                "code": "CONFIG_MISSING",
                "message": f"No cached device_code at {cache_path}. Run 'request' first.",
                "retryable": False,
            },
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    cached = json.loads(cache_path.read_text())

    # Check expiry
    age = time.time() - cached["created_at"]
    if age > cached["expires_in"]:
        print(json.dumps({
            "success": False,
            "error": {
                "code": "DEVICE_CODE_EXPIRED",
                "message": f"Device code expired ({age:.0f}s old, max {cached['expires_in']}s). Run 'request' again.",
                "retryable": True,
            },
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    print(f"[poll] Device code age: {age:.0f}s / {cached['expires_in']}s, "
          f"timeout: {timeout or 'none'}", file=sys.stderr)

    try:
        tokens = poll_token(
            client_id=cached["client_id"],
            device_code=cached["device_code"],
            interval=cached["interval"],
            expires_in=int(cached["expires_in"] - age),
            timeout=timeout,
        )
    except RuntimeError as error:
        print(json.dumps({
            "success": False,
            "error": {
                "code": "ONEDRIVE_TOKEN_REFRESH_FAILED",
                "message": str(error),
                "retryable": False,
            },
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print(json.dumps({
            "success": False,
            "error": {
                "code": "ONEDRIVE_TOKEN_REFRESH_FAILED",
                "message": "No refresh_token in response. Device code may have been consumed.",
                "retryable": True,
            },
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    # Update .env if requested
    if update_env:
        _update_env_file(refresh_token)

    # Clean up cache
    cache_path.unlink(missing_ok=True)

    print(json.dumps({
        "success": True,
        "data": {
            "access_token": tokens.get("access_token"),
            "refresh_token": refresh_token,
            "scope": tokens.get("scope"),
            "expires_in": tokens.get("expires_in"),
        },
    }, ensure_ascii=False, indent=2))


# ── Subcommand: legacy (default, no args) ────────────────────────────

def cmd_legacy() -> None:
    """Original behavior: request + poll in one blocking call."""
    client_id = _get_client_id()

    try:
        device = request_device_code(client_id)
    except RuntimeError as error:
        print(json.dumps({
            "success": False,
            "error": {
                "code": "ONEDRIVE_AUTH_REQUIRED",
                "message": str(error),
                "retryable": False,
            },
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    print(json.dumps({
        "success": True,
        "data": {
            "message": device.get("message"),
            "user_code": device.get("user_code"),
            "verification_uri": device.get("verification_uri"),
            "expires_in": device.get("expires_in"),
        },
    }, ensure_ascii=False, indent=2))
    sys.stderr.write(
        "\nComplete the sign-in in your local browser, then wait for token "
        "polling to finish.\n")

    tokens = poll_token(
        client_id=client_id,
        device_code=device["device_code"],
        interval=int(device.get("interval", 5)),
        expires_in=int(device.get("expires_in", 900)),
    )
    print(json.dumps({
        "success": True,
        "data": {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "scope": tokens.get("scope"),
            "expires_in": tokens.get("expires_in"),
        },
    }, ensure_ascii=False, indent=2))


# ── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="OneDrive OAuth device code flow",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("request", help="Get device code and print for user")

    poll_p = sub.add_parser("poll", help="Poll for token after user authorizes")
    poll_p.add_argument("--update-env", action="store_true",
                        help="Automatically write refresh_token to .env")
    poll_p.add_argument("--timeout", type=int, default=None,
                        help="Max seconds to poll (default: until expiry)")

    args = parser.parse_args()

    if args.command == "request":
        cmd_request()
    elif args.command == "poll":
        cmd_poll(update_env=args.update_env, timeout=args.timeout)
    else:
        cmd_legacy()


if __name__ == "__main__":
    main()
