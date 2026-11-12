"""Store operator-supplied Sandbox configuration locally with owner-only file access."""

import getpass
import os
import sys
import tempfile
from pathlib import Path


def configure():
    path = Path.home() / ".config/getby/paypal.env"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.strip().removeprefix("export ").partition("=")
            if sep and key.startswith("PAYPAL_") and key.isidentifier():
                existing[key] = value.strip().strip("\"'")
    print("Use Sandbox test accounts. Blank input preserves an existing setting.")
    keys = [
        ("PAYPAL_CLIENT_ID", "Buyer app client ID"),
        ("PAYPAL_CLIENT_SECRET", "Buyer app secret"),
        ("PAYPAL_RECIPIENT_EMAIL", "Worker sandbox email"),
        (
            "PAYPAL_ELECTRICITY_CLIENT_ID",
            "Electricity test merchant app client ID (optional)",
        ),
        (
            "PAYPAL_ELECTRICITY_CLIENT_SECRET",
            "Electricity test merchant app secret (optional)",
        ),
        ("PAYPAL_MOBILE_CLIENT_ID", "Mobile test merchant app client ID (optional)"),
        ("PAYPAL_MOBILE_CLIENT_SECRET", "Mobile test merchant app secret (optional)"),
    ]
    for key, label in keys:
        text = getpass.getpass(label + ": ").strip()
        if text:
            existing[key] = text
    if any(not existing.get(k) for k, _ in keys[:3]):
        sys.exit("Three buyer/recipient settings are required. No changes were saved.")
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
        for k, v in existing.items():
            f.write(f"{k}={v}\n")
    os.replace(f.name, path)
    print(f"Saved settings to {path}. Run scripts/run.sh sandbox.")


if __name__ == "__main__":
    configure()
