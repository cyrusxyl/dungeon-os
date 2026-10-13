#!/usr/bin/env bash
# Start the TTS service on 127.0.0.1:8770.
# Usage: tts/run.sh [f5|mock]   (default: f5)
# Env: TTS_PORT (8770), TTS_HOST (127.0.0.1), TTS_VOICES_DIR, BG3_VOICE_HOME
set -euo pipefail
cd "$(dirname "$0")"
export TTS_ENGINE="${1:-${TTS_ENGINE:-f5}}"
exec .venv/bin/uvicorn service.app:app --host "${TTS_HOST:-127.0.0.1}" --port "${TTS_PORT:-8770}"
