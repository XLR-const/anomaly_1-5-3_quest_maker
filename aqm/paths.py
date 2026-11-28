"""Изоляция путей пакета ``aqm`` от рабочего пространства пользователя.

Пакет хранит собственную SQLite-базу и шаблоны рядом с кодом, тогда как
пользовательские файлы (``aqm.json``, ``scripts/``, ``output/``, ``doc.md``)
живут в рабочем пространстве, которое определяется по маркеру ``aqm.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

#: Имя файла-маркера рабочего пространства.
WORKSPACE_MARKER = "aqm.json"
#: Значения по умолчанию для отсутствующих ключей ``aqm.json``.
_DEFAULT_CONFIG = {
    "output_dir": "output",
    "db_path": None,
    "vanilla_dir": None,
}


def get_package_dir() -> Path:
    """Возвращает каталог установленного пакета ``aqm``.

    Returns:
        Path: Абсолютный путь к каталогу, содержащему ``__init__.py`` пакета.
    """
    return Path(__file__).resolve().parent


def get_default_db_path() -> Path:
    """Возвращает путь к вшитой в пакет базе ассетов Anomaly.

    Returns:
        Path: ``<package>/data/anomaly_db.sqlite``.
    """
    return get_package_dir() / "data" / "anomaly_db.sqlite"


def get_default_vanilla_dir() -> Path:
    """Возвращает корень вшитых ванильных индексов ``configs``.

    Returns:
        Path: ``<package>/data/vanilla``.
    """
    return get_package_dir() / "data" / "vanilla"


def get_templates_dir() -> Path:
    """Возвращает каталог шаблонов, поставляемых вместе с пакетом.

    Returns:
        Path: ``<package>/templates``.
    """
    return get_package_dir() / "templates"


def find_workspace_root(start_dir: Path | None = None) -> Path:
    """Ищет корень рабочего пространства по файлу ``aqm.json``.

    Поиск начинается с ``start_dir`` (по умолчанию текущий каталог) и
    поднимается по родительским каталогам. Если маркер не найден,
    возвращается текущий рабочий каталог.

    Args:
        start_dir (Path | None): Каталог, с которого начинается поиск.

    Returns:
        Path: Каталог с ``aqm.json`` или ``Path.cwd()``.
    """
    current = Path(start_dir).resolve() if start_dir is not None else Path.cwd()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / WORKSPACE_MARKER).is_file():
            return candidate
    return Path.cwd()


def load_workspace_config(workspace_root: Path) -> dict:
    """Читает ``aqm.json`` рабочего пространства.

    Отсутствующий или повреждённый файл не считается фатальной ошибкой:
    возвращаются значения по умолчанию, чтобы сборка работала автономно.

    Args:
        workspace_root (Path): Корень рабочего пространства.

    Returns:
        dict: Ключи ``output_dir``, ``db_path`` и ``vanilla_dir``.
    """
    config = dict(_DEFAULT_CONFIG)
    config_path = Path(workspace_root) / WORKSPACE_MARKER
    if not config_path.is_file():
        return config

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return config

    if isinstance(raw, dict):
        for key in _DEFAULT_CONFIG:
            if key in raw:
                config[key] = raw[key]
    return config


__all__ = [
    "WORKSPACE_MARKER",
    "find_workspace_root",
    "get_default_db_path",
    "get_default_vanilla_dir",
    "get_package_dir",
    "get_templates_dir",
    "load_workspace_config",
]
