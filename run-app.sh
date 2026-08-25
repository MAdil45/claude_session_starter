#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Use Ubuntu's Tk build. Conda/Miniforge Tk can fall back to legacy X11 bitmap
# fonts even when scalable desktop fonts are installed, producing jagged text.
system_python="/usr/bin/python3"
if [[ ! -x "$system_python" ]]; then
    system_python="$(command -v python3)"
fi

exec "$system_python" "$app_dir/app.py"
