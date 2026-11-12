#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ -f .venv/bin/python ]; then py=.venv/bin/python; else py=python3; fi
exec "$py" scripts/launch.py "$@"
