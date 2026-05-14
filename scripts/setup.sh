#!/usr/bin/env bash
# web-collector setup — clone/update external dependencies
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEPS_DIR="$SKILL_DIR/.."  # openclaw-imports/

XTWEET_DIR="${WEB_COLLECTOR_X_TWEET_FETCHER_DIR:-$DEPS_DIR/x-tweet-fetcher}"
XTWEET_REPO="https://github.com/ythx-101/x-tweet-fetcher.git"

echo "=== web-collector setup ==="

# --- x-tweet-fetcher ---
if [ -d "$XTWEET_DIR/.git" ]; then
    echo "[x-tweet-fetcher] pulling latest..."
    git -C "$XTWEET_DIR" pull --ff-only 2>&1
else
    echo "[x-tweet-fetcher] cloning..."
    git clone "$XTWEET_REPO" "$XTWEET_DIR"
fi

echo "[x-tweet-fetcher] commit: $(git -C "$XTWEET_DIR" rev-parse --short HEAD)"

echo "=== done ==="
