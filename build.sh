#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv-build"

echo "==> Setting up build environment..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo "==> Installing PyInstaller..."
    pip install --quiet pyinstaller
fi

echo "==> Building dconv..."
python3 -m PyInstaller \
    --onefile \
    --name dconv \
    --distpath dist \
    --workpath build \
    --specpath build \
    --clean \
    dconv.py

deactivate

echo ""
echo "==> Build complete: dist/dconv"
echo "    Run:  ./dist/dconv -h"
