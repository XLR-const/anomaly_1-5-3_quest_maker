"""Единый формат результата валидации квестовых проектов.

Модуль реализует контракт ``docs/VALIDATION_SPEC.md`` (§4.2): severity,
неизменяемое описание проблемы, накопительный отчёт с дедупликацией и
детерминированными текстовым/JSON-представлениями.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Iterable


class Severity(IntEnum):
    """Уровень важности замечания.

    Значения выбраны с запасом, чтобы в будущем можно было добавить
    промежуточные уровни без изменения числовых контрактов.
    """

    INFO = 10
    WARNING = 20
    ERROR = 30


@dataclass(frozen=True)
class ValidationIssue:
    """Одно замечание валидатора.

    Attributes:
        code: Стабильный машинный код (``CAT-NPC-001``, ``GRAPH-*``).
        severity: Уровень важности.
        target_id: Идентификатор проверяемого объекта внутри проекта.
        message: Человекочитаемое описание проблемы.
        hint: Подсказка, как исправить проблему.
        owner: Тип владельца (``quest``, ``dialog``, ``stage``, ``squad``).
        details: Дополнительные машинночитаемые детали.
    """

    code: str
    severity: Severity
    target_id: str
    message: str
    hint: str = ""
    owner: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class ValidationReportError(ValueError):
    """Исключение, поднимаемое при наличии ошибок в отчёте.

    Хранит ссылку на исходный :class:`ValidationReport`, чтобы CLI/CI могли
    дополнительно сериализовать полный отчёт, не разбирая текст исключения.
    """

    def __init__(self, message: str, report: "ValidationReport") -> None:
        super().__init__(message)
        self.report = report


@dataclass
class ValidationReport:
    """Накопительный отчёт о результатах валидации."""

    issues: list[ValidationIssue] = field(default_factory=list)

    @staticmethod
    def _key(issue: ValidationIssue) -> tuple[str, str, str]:
        """Возвращает ключ дедупликации замечания."""
        return (issue.code, issue.target_id, issue.message)

    def add(
        self,
        code: str,
        severity: Severity,
        target_id: str,
        message: str,
        hint: str = "",
        owner: str = "",
        **details: Any,
    ) -> None:
        """Добавляет замечание, если такого ещё нет.

        Дедупликация выполняется по тройке ``(code, target_id, message)``.
        """
        issue = ValidationIssue(
            code=code,
            severity=severity,
            target_id=target_id,
            message=message,
            hint=hint,
            owner=owner,
            details=dict(details),
        )
        if self._key(issue) in {self._key(existing) for existing in self.issues}:
            return
        self.issues.append(issue)

    def extend(self, issues: Iterable[ValidationIssue]) -> None:
        """Добавляет коллекцию замечаний с той же дедупликацией."""
        for issue in issues:
            if self._key(issue) in {
                self._key(existing) for existing in self.issues
            }:
                continue
            self.issues.append(issue)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Все замечания уровня ``ERROR``."""
        return [
            issue for issue in self.issues if issue.severity == Severity.ERROR
        ]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Все замечания уровня ``WARNING``."""
        return [
            issue for issue in self.issues if issue.severity == Severity.WARNING
        ]

    @property
    def has_errors(self) -> bool:
        """``True``, если в отчёте есть хотя бы одна ошибка."""
        return any(issue.severity == Severity.ERROR for issue in self.issues)

    def sorted(self) -> list[ValidationIssue]:
        """Возвращает замечания в детерминированном порядке.

        Сортировка: severity по убыванию, затем ``code``, затем ``target_id``.
        """
        return sorted(
            self.issues,
            key=lambda issue: (
                -int(issue.severity),
                issue.code,
                issue.target_id,
            ),
        )

    @staticmethod
    def _issue_to_dict(issue: ValidationIssue) -> dict[str, Any]:
        """Преобразует замечание в сериализуемый словарь."""
        return {
            "code": issue.code,
            "severity": issue.severity.name,
            "target_id": issue.target_id,
            "message": issue.message,
            "hint": issue.hint,
            "owner": issue.owner,
            "details": dict(issue.details),
        }

    def to_dict(self) -> dict[str, Any]:
        """Возвращает JSON-совместимое представление отчёта."""
        info_count = sum(
            1 for issue in self.issues if issue.severity == Severity.INFO
        )
        return {
            "summary": {
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "info": info_count,
                "total": len(self.issues),
            },
            "issues": [
                self._issue_to_dict(issue) for issue in self.sorted()
            ],
        }

    def to_json(self, *, indent: int = 2) -> str:
        """Сериализует отчёт в детерминированный JSON без escape-кириллицы."""
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )

    def to_text(self) -> str:
        """Возвращает читаемый текстовый отчёт для человека."""
        if not self.issues:
            return "Validation report: no issues."

        lines: list[str] = []
        for issue in self.sorted():
            lines.append(
                f"[{issue.severity.name}] {issue.code} "
                f"{issue.target_id}: {issue.message}"
            )
            if issue.hint:
                lines.append(f"  hint: {issue.hint}")

        info_count = sum(
            1 for issue in self.issues if issue.severity == Severity.INFO
        )
        lines.append("")
        lines.append(
            "Summary: "
            f"{len(self.errors)} error(s), "
            f"{len(self.warnings)} warning(s), "
            f"{info_count} info, "
            f"{len(self.issues)} issue(s)."
        )
        return "\n".join(lines)

    def raise_if_errors(self) -> None:
        """Поднимает :class:`ValidationReportError`, если есть ошибки."""
        if self.has_errors:
            raise ValidationReportError(self.to_text(), self)


__all__ = [
    "Severity",
    "ValidationIssue",
    "ValidationReport",
    "ValidationReportError",
]
