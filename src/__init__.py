"""Тонкий мост совместимости ``src`` -> ``aqm``.

Исторические импорты ``from src.core.models import ModProject`` продолжают
работать, но указывают на те же модульные объекты, что и ``aqm.*``. Благодаря
этому monkeypatch в тестах и внешнем коде виден и пакету ``aqm``.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType

_MODULE_ALIASES = (
    "core",
    "core.actions",
    "core.conditions",
    "core.models",
    "core.validator",
    "db",
    "db.repository",
    "compiler",
    "compiler.builder",
    "compiler.encoding",
    "compiler.ltx_gen",
    "compiler.lua_gen",
    "compiler.npc_gen",
    "compiler.xml_gen",
    "validation",
    "validation.catalog_validator",
    "validation.graph_validator",
    "validation.merger",
    "validation.post_build",
    "validation.report",
    "validation.xray_linter",
    "logger",
)


def _install_aliases() -> None:
    """Регистрирует ``src.<name>`` как псевдоним ``aqm.<name>``."""
    for suffix in _MODULE_ALIASES:
        alias_name = f"src.{suffix}"
        target = importlib.import_module(f"aqm.{suffix}")
        sys.modules[alias_name] = target

        parent_name, _, child_name = alias_name.rpartition(".")
        parent: ModuleType | None = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, child_name, target)


_install_aliases()

__all__ = ["compiler", "core", "db", "logger", "validation"]
