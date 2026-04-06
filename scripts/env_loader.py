#!/usr/bin/env python3
"""
Minimal .env loader for web-collector.

Priority:
1. Existing process environment
2. .env file
3. Code defaults
"""

import os
from typing import Dict, Optional, Tuple


_LOADED = False


def _resolve_env_file() -> str:
    custom_path = os.environ.get("WEB_COLLECTOR_ENV_FILE", "").strip()
    if custom_path:
        return os.path.abspath(custom_path)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))


def _parse_env_line(line: str) -> Optional[Tuple[str, str]]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    if stripped.startswith("export "):
        stripped = stripped[len("export "):].strip()

    if "=" not in stripped:
        return None

    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]

    return key, value


def load_env_file(override: bool = False) -> Dict[str, str]:
    global _LOADED

    if _LOADED and not override:
        return {}

    env_path = _resolve_env_file()
    loaded: Dict[str, str] = {}
    if not os.path.exists(env_path):
        _LOADED = True
        return loaded

    with open(env_path, "r", encoding="utf-8") as handle:
        for line in handle:
            parsed = _parse_env_line(line)
            if not parsed:
                continue
            key, value = parsed
            if override or key not in os.environ:
                os.environ[key] = value
                loaded[key] = value

    _LOADED = True
    return loaded
