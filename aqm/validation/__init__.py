"""Пакет валидации квестовых проектов Anomaly 1.5.3."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqm.validation.catalog_validator import CatalogValidator
from aqm.validation.graph_validator import GraphIndex, GraphValidator
from aqm.validation.merger import MergeValidator
from aqm.validation.report import (
    Severity,
    ValidationIssue,
    ValidationReport,
    ValidationReportError,
)
from aqm.validation.xray_linter import XrayLinter

if TYPE_CHECKING:
    from aqm.core.models import ModProject
    from aqm.db.repository import GameDatabase


def validate_project(
    project: "ModProject",
    db: "GameDatabase | None" = None,
) -> ValidationReport:
    """Запускает полный пайплайн валидации проекта.

    Порядок фиксирован: сначала каталог ассетов, затем граф диалогов и
    этапов, затем X-Ray-линтер. Все валидаторы пишут замечания в один
    :class:`ValidationReport`, поэтому отчёт не теряет ни одного кода.

    Args:
        project (ModProject): Проверяемый проект мода.
        db (GameDatabase | None): Необязательный клиент SQLite. Если
            ``None``, проверки, требующие БД, пропускаются или выполняются
            в режиме без ассетов.

    Returns:
        ValidationReport: Накопленный отчёт валидации.
    """
    report = ValidationReport()
    CatalogValidator(db, report).validate(project)
    GraphValidator(report).validate(project)
    XrayLinter(db, report).validate(project)
    return report


__all__ = [
    "CatalogValidator",
    "GraphIndex",
    "GraphValidator",
    "MergeValidator",
    "Severity",
    "ValidationIssue",
    "ValidationReport",
    "ValidationReportError",
    "XrayLinter",
    "validate_project",
]
