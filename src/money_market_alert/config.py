"""Environment loading and small, shared configuration helpers."""

import logging
import math
import os
from pathlib import Path


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Не задана переменная {name}. Проверьте .env.")
    return value


def get_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} должна быть целым числом") from None
    if value < minimum:
        raise ValueError(f"{name} должна быть не меньше {minimum}")
    return value


def get_float(name: str, default: float, minimum: float = 0) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} должна быть числом") from None
    if not math.isfinite(value) or value < minimum:
        raise ValueError(f"{name} должна быть конечным числом не меньше {minimum}")
    return value


def initialize() -> None:
    from dotenv import load_dotenv

    load_dotenv(Path.cwd() / ".env", override=False)
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("LOG_LEVEL: DEBUG, INFO, WARNING, ERROR или CRITICAL")
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # HTTP client URLs may contain the Telegram bot token.
    for name in ("httpx", "httpcore", "urllib3", "telegram"):
        logging.getLogger(name).setLevel(logging.WARNING)
