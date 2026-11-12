import os
from pathlib import Path


def load_sandbox_settings():
    config = Path.home() / ".config/getby/paypal.env"
    if config.is_file():
        for line in config.read_text().splitlines():
            key, sep, value = line.strip().removeprefix("export ").partition("=")
            if sep and key.startswith("PAYPAL_") and key.isidentifier():
                os.environ.setdefault(key, value.strip().strip("\"'"))
