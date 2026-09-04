#!/usr/bin/env bash
# Quick helper: process + optional upload
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || true

VIDEO="${1:?Usage: ./upload.sh video.mp4 [game] [hook]}"
GAME="${2:-}"
HOOK="${3:-}"
EXTRA=()
[[ -n "$GAME" ]] && EXTRA+=(--game "$GAME")
[[ -n "$HOOK" ]] && EXTRA+=(--hook "$HOOK")

python pipeline.py process "$VIDEO" "${EXTRA[@]}"
BUNDLE="processed/$(basename "${VIDEO%.*}")_upload.json"
echo ""
read -r -p "Upload to YouTube now? [y/N] " ans
if [[ "${ans,,}" == "y" ]]; then
  python pipeline.py upload "$BUNDLE" --public
fi