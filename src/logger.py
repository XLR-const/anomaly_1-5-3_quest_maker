import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from rich.logging import RichHandler

LOGS_DIR = Path("logs")
LOG_FILE = LOGS_DIR / "app.log"
_INITIALIZED = False


def setup_logging(level: int = logging.INFO) -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("aqb")
    root_logger.setLevel(logging.DEBUG)

    # Консольный вывод через Rich
    console_handler = RichHandler(
        rich_tracebacks=True,
        show_path=False,
        markup=True,
    )
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))

    # Файловый лог с ротацией (макс 2 МБ, 3 бэкапа)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    _INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(f"aqb.{name}")
