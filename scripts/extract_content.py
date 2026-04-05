#!/usr/bin/env python3
"""
Detect the source platform for a URL and emit the configured extractor route.
"""

import json
import sys
from extractors.registry import detect_platform


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": {
                "code": "INVALID_INPUT",
                "message": "Usage: python3 extract_content.py <url>",
                "retryable": False,
            },
        }, ensure_ascii=False))
        sys.exit(1)

    result = detect_platform(sys.argv[1])
    print(json.dumps({"success": True, "data": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
