"""Историческая точка входа: делегирует в ``aqm.cli.main``.

CLI-ядро перенесено в устанавливаемый пакет ``aqm``. Этот файл сохранён для
совместимости команд вида ``python main.py build`` и старых импортов
``from main import DEFAULT_DB_PATH, _load_project_from_script``.
"""

from __future__ import annotations

from pathlib import Path

from aqm.paths import get_default_db_path
from aqm.cli.main import (
    _find_project_factory,
    _is_modproject_annotation,
    _load_project_from_script,
    app,
    build,
    init,
    main,
    merge,
    search,
    validate,
)

#: Корень репозитория (историческое имя из ``main.py``).
PROJECT_ROOT = Path(__file__).resolve().parent
#: Основная SQLite-база ассетов (историческое имя из ``main.py``).
DEFAULT_DB_PATH = get_default_db_path()

if __name__ == "__main__":
    main()

__all__ = [
    "DEFAULT_DB_PATH",
    "PROJECT_ROOT",
    "_find_project_factory",
    "_is_modproject_annotation",
    "_load_project_from_script",
    "app",
    "build",
    "init",
    "main",
    "merge",
    "search",
    "validate",
]
