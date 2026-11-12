"""Launch with optional Sandbox keys stored outside the repository."""

import os
import runpy
import sys
from pathlib import Path
from sandbox_config import load_sandbox_settings

root = Path(__file__).resolve().parents[1]
if len(sys.argv) > 2 or (
    len(sys.argv) == 2 and sys.argv[1] not in {"sandbox", "practice"}
):
    sys.exit("Usage: scripts/run.sh [practice|sandbox]")
mode = sys.argv[1] if len(sys.argv) == 2 else os.environ.get("GETBY_MODE", "practice")
if mode == "sandbox":
    load_sandbox_settings()
os.environ["GETBY_MODE"] = mode
sys.path.insert(0, str(root))
runpy.run_path(str(root / "server.py"), run_name="__main__")
