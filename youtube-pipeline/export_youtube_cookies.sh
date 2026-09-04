#!/usr/bin/env bash
# Export YouTube cookies for yt-dlp gameplay downloads (run when logged into YouTube).
# Re-run every 2-4 weeks or when daily logs show "YouTube blocked download".
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT="$ROOT/youtube_cookies.txt"
YTDLP="$ROOT/.venv/bin/yt-dlp"
BROWSER="${1:-chrome}"

if [[ ! -x "$YTDLP" ]]; then
  echo "ERROR: yt-dlp not found. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

echo "Exporting YouTube cookies from $BROWSER → $OUT"
echo "(Log into youtube.com in $BROWSER first. macOS may ask for your login/keychain password once.)"
echo ""

"$YTDLP" --cookies-from-browser "$BROWSER" --cookies "$OUT" --skip-download "https://www.youtube.com"

if [[ ! -s "$OUT" ]]; then
  echo "ERROR: Cookie export failed or file is empty."
  echo "Try: ./export_youtube_cookies.sh firefox"
  exit 1
fi

lines=$(grep -c '^\.youtube\.com' "$OUT" 2>/dev/null || echo 0)
echo ""
echo "✅ Exported $lines YouTube cookie(s) to youtube_cookies.txt"
echo ""
echo "Ensure config.env has:"
echo "  YT_DLP_COOKIES_FILE=youtube_cookies.txt"
echo "  YT_DLP_COOKIES_FROM_BROWSER="
echo ""
echo "Test download:"
echo "  $YTDLP --cookies $OUT -f 'bv*[height<=720]/bv+ba/b' -o /tmp/yt_test.mp4 'https://www.youtube.com/watch?v=Oqr0muaqH0c'"