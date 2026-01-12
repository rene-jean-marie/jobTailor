#!/usr/bin/env bash
set -euo pipefail

# Record full terminal session, including prompts and responses.
if [[ -n "${CODEX_RECORD_LOG:-}" ]]; then
  LOG_FILE="${CODEX_RECORD_LOG}"
else
  ts="$(date +%Y%m%d_%H%M%S)"
  LOG_FILE="$HOME/codex-transcript-${ts}.log"
fi

if ! command -v script >/dev/null 2>&1; then
  echo "Error: 'script' command not found. Install util-linux or the platform equivalent." >&2
  exit 1
fi

echo "Recording Codex session to: ${LOG_FILE}"
exec script -a "$LOG_FILE" -q codex
