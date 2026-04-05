#!/usr/bin/env python3
"""
Bridge extractor output into the payload format expected by collect_from_defuddle.py.

Usage:
  python3 scripts/export_from_defuddle.py --url <URL>
"""

import argparse
import json
import os

from extractors.registry import detect_platform, get_extractor
from extractors.shared import (
    ExtractionError,
    build_payload,
    render_markdown,
    write_markdown,
    write_payload,
)


DEFAULT_OUTPUT_DIR = os.environ.get(
    "WEB_COLLECTOR_RAW_DIR",
    os.path.join(os.path.dirname(__file__), "..", ".cache", "raw"),
)


def emit_error(code: str, message: str, retryable: bool = False) -> None:
    print(json.dumps({
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
        },
    }, ensure_ascii=False, indent=2))
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--payload-out")
    args = parser.parse_args()

    url = args.url.strip()
    platform = detect_platform(url)
    extractor_id = platform["extractor"]

    try:
        extractor = get_extractor(extractor_id)
        extraction = extractor(url)
    except KeyError as error:
        emit_error("EXTRACTOR_NOT_FOUND", str(error))
    except ExtractionError as error:
        emit_error(error.code, error.message, error.retryable)

    markdown_path = write_markdown(
        args.output_dir,
        extraction.title,
        render_markdown(extraction.title, extraction.source, extraction.url, extraction.body_markdown),
    )

    payload = build_payload(
        extraction,
        route="internal",
        markdown_path=markdown_path,
        extractor_id=extractor_id,
        platform=platform,
    )

    payload_path = args.payload_out or f"{markdown_path}.payload.json"
    payload_path = write_payload(payload, payload_path)
    payload["payload_path"] = payload_path

    print(json.dumps({"success": True, "data": payload}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
