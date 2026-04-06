#!/usr/bin/env python3
"""
Perform first-time local OAuth device code flow for a personal OneDrive account.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError

from env_loader import load_env_file

DEVICE_CODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
SCOPES = "offline_access Files.ReadWrite"

load_env_file()


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


def poll_token(client_id: str, device_code: str, interval: int, expires_in: int) -> dict:
    deadline = time.time() + expires_in
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
    raise RuntimeError("Device code expired before authorization completed.")


def main() -> None:
    client_id = os.environ.get("ONEDRIVE_CLIENT_ID")
    if not client_id:
        print(json.dumps({
            "success": False,
            "error": {
                "code": "CONFIG_MISSING",
                "message": "ONEDRIVE_CLIENT_ID is required",
                "retryable": False,
            },
        }, ensure_ascii=False))
        sys.exit(1)

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
    sys.stderr.write("\nComplete the sign-in in your local browser, then wait for token polling to finish.\n")

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


if __name__ == "__main__":
    main()
