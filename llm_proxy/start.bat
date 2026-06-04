@echo off
cd /d "%~dp0"
uv run litellm --config config.yaml --port 4000
