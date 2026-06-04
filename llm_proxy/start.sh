#!/usr/bin/env bash
# Start LiteLLM Proxy
# Usage: ./start.sh

set -e
cd "$(dirname "$0")"
exec uv run litellm --config config.yaml --port 4000
