#!/usr/bin/env bash
# Create 3 Shorts (random trending games) + SEO + thumbnails — no recording needed
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || true

COUNT="${1:-3}"
echo "Creating $COUNT AI Shorts for ProGamer..."
python pipeline.py batch --count "$COUNT" --auto --format tips --duration short
echo "Done. Review generated/ and upload bundles in processed/"