#!/usr/bin/env bash
# One-time setup for the selftaught skill on Debian/Ubuntu (including WSL).
# Installs the system libraries WeasyPrint needs (Pango), Poppler for the
# visual QA, a dedicated virtualenv at ~/.venvs/selftaught, and the fonts.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${SELFTAUGHT_VENV:-$HOME/.venvs/selftaught}"

sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-pip \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    poppler-utils fontconfig

python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$HERE/requirements.txt"

"$VENV/bin/python" "$HERE/fetch_fonts.py"

echo
"$VENV/bin/python" -m weasyprint --info
echo
echo "Ready. Python for this skill: $VENV/bin/python"
