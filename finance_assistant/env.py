"""Load settings from a local .env file (KEY=value lines), without extra libraries.

The .env file is in .gitignore, so your API key never goes to GitHub.
"""

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        # setdefault: a variable already set in the system wins over the file
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
