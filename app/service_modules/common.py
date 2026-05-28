from __future__ import annotations

import re
from typing import Any


def safe_identifier(value: Any, *, fallback: str = "item") -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(value)).strip("_") or fallback
