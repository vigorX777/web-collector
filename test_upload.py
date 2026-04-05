#!/usr/bin/env python3
"""Test OneDrive upload with configured credentials."""

import os
import sys

# Load environment from .env file
env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value

# Import upload function
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
from upload_to_onedrive import upload_markdown_file

# Test file
test_file = os.path.join(os.path.dirname(__file__), "README.md")

if not os.path.exists(test_file):
    print(f"Test file not found: {test_file}")
    sys.exit(1)

try:
    result = upload_markdown_file(test_file)
    print(f"Upload successful!")
    print(f"File: {result['name']}")
    print(f"URL: {result['web_url']}")
    print(f"Target: {result['target_dir']}")
except Exception as e:
    print(f"Upload failed: {e}")
    sys.exit(1)
