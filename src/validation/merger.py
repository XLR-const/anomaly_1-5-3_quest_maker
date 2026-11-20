"""Проверки слияния независимых глав мода в единый проект.

Модуль дополняет :meth:`src.core.models.ModProject.merge`: сама модель
гарантирует отсутствие коллизий, а :class:`MergeValidator` объясняет
пользователю, какие именно ID пересеклись и чем опасны общие инфопоршни.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from src.core.models import GiveInfo, ModProject, Quest
from src.validation.report import Severity, ValidationReport

_SLUG_PATTERN = re.compile(r"[^a-z0-9_]+")
_REPEATED_UNDERSCORES = re.compile(r"_+")


def _fallback_slug(project: ModProject) -> str:
    """Возвращает безопасный slug для проверки пространства имён.

    Args:
        project (ModProject): Глава, у которой нет явного ``mod_slug``.

    Returns:
        str: Нижний регистр имени проекта с заменой недопустимых символов
        на ``_``. Если получить slug не удалось, возвращается ``"mod"``.
    """
    raw = getattr(project, "name", "") or ""
    slug = _SLUG_PATTERN.sub("_", str(raw).strip().lower())
    slug = _REPEATED_UNDERSCORES.sub("_", slug).strip("_")
    return slug or "mod"


def _quest_give_infos(quest: Quest) -> set[str]:
    """Собирает инфопоршни, которые квест выдаёт игроку.

    Учитываются ``Quest.complete_info`` и все действия ``GiveInfo`` на
    уровне квеста и его этапов. Реплики диалогов проверяются отдельно
    графовым валидатором, поэтому здесь не дублируются.

    Args:
        quest (Quest): Квест главы.

    Returns:
        set[str]: Уникальные идентификаторы выдаваемых инфопоршней.
    """
    infos: set[str] = set()
    if quest.complete_info:
        infos.add(quest.complete_info)

    action_lists: list[list[Any]] = [
        list(quest.on_init_actions),
        list(quest.on_complete_actions),
        list(quest.on_fail_actions),
    ]
    for stage in quest.stages.values():
        action_lists.append(list(stage.on_start_actions))

    for actions in action_lists:
        for action in actions:
            if isinstance(action, GiveInfo) and action.info:
                infos.add(action.info)
    return infos


class MergeValidator:
    """Проверяет набор глав перед их объединением в один ``ModProject``.

    Attributes:
        report (ValidationReport): Накопительный отчёт, в который
            добавляются замечания.
    """

    def __init__(self, report: ValidationReport) -> None:
        """Сохраняет отчёт для накопления замечаний.

        Args:
            report (ValidationReport): Целевой отчёт валидации.
        """
        self.report = report

    def validate_chapters(
        self,
        chapters: Sequence[ModProject],
        target_slug: str | None = None,
    ) -> None:
        """Проверяет коллизии, общие инфопоршни и пространство имён.

        Args:
            chapters (Sequence[ModProject]): Главы в порядке объединения.
            target_slug (str | None): Ожидаемый префикс ID. Если ``None``,
                используется ``mod_slug`` первой главы, а при его
                отсутствии — slug, вычисленный из ``name``.

        Returns:
            None: Замечания добавляются в :attr:`report`.
        """
        chapter_list = list(chapters)
        if not chapter_list:
            return

        slug = (
            target_slug
            or getattr(chapter_list[0], "mod_slug", None)
            or _fallback_slug(chapter_list[0])
        )
        prefix = f"{slug}_"

        quest_origins: dict[str, int] = {}
        dialog_origins: dict[str, int] = {}
        squad_origins: dict[str, int] = {}
        story_origins: dict[str, int] = {}
        info_origins: dict[str, list[tuple[int, str]]] = {}

        for chapter_index, chapter in enumerate(chapter_list):
            for quest_id, quest in chapter.quests.items():
                previous = quest_origins.get(quest_id)
                if previous is not None:
                    self.report.add(
                        "MERGE-ID-001",
                        Severity.ERROR,
                        quest_id,
                        f"Ключ квеста '{quest_id}' встречается в главах "
                        f"{previous} и {chapter_index}.",
                        hint="Переименуйте квест в одной из глав.",
                        owner="quest",
                        chapter_a=previous,
                        chapter_b=chapter_index,
                    )
                else:
                    quest_origins[quest_id] = chapter_index

                if not str(quest.id).startswith(prefix):
                    self.report.add(
                        "MERGE-NS-001",
                        Severity.WARNING,
                        str(quest.id),
                        f"ID квеста '{quest.id}' не начинается с префикса "
                        f"'{prefix}'.",
                        hint=f"Используйте ID вида '{prefix}<name>'.",
                        owner="quest",
                    )

                for info in _quest_give_infos(quest):
                    info_origins.setdefault(info, []).append(
                        (chapter_index, quest.id)
                    )

            for dialog_id, dialog in chapter.dialogs.items():
                previous = dialog_origins.get(dialog_id)
                if previous is not None:
                    self.report.add(
                        "MERGE-ID-001",
                        Severity.ERROR,
                        dialog_id,
                        f"Ключ диалога '{dialog_id}' встречается в главах "
                        f"{previous} и {chapter_index}.",
                        hint="Переименуйте диалог в одной из глав.",
                        owner="dialog",
                        chapter_a=previous,
                        chapter_b=chapter_index,
                    )
                else:
                    dialog_origins[dialog_id] = chapter_index

                if not str(dialog.id).startswith(prefix):
                    self.report.add(
                        "MERGE-NS-001",
                        Severity.WARNING,
                        str(dialog.id),
                        f"ID диалога '{dialog.id}' не начинается с префикса "
                        f"'{prefix}'.",
                        hint=f"Используйте ID вида '{prefix}<name>'.",
                        owner="dialog",
                    )

            for squad_id, squad in chapter.squads.items():
                previous = squad_origins.get(squad_id)
                if previous is not None:
                    self.report.add(
                        "MERGE-ID-001",
                        Severity.ERROR,
                        squad_id,
                        f"Ключ отряда '{squad_id}' встречается в главах "
                        f"{previous} и {chapter_index}.",
                        hint="Переименуйте отряд в одной из глав.",
                        owner="squad",
                        chapter_a=previous,
                        chapter_b=chapter_index,
                    )
                else:
                    squad_origins[squad_id] = chapter_index

                if not str(squad.id).startswith(prefix):
                    self.report.add(
                        "MERGE-NS-001",
                        Severity.WARNING,
                        str(squad.id),
                        f"ID отряда '{squad.id}' не начинается с префикса "
                        f"'{prefix}'.",
                        hint=f"Используйте ID вида '{prefix}<name>'.",
                        owner="squad",
                    )

                story_id = getattr(squad, "story_id", None)
                if story_id:
                    previous = story_origins.get(story_id)
                    if previous is not None and previous != chapter_index:
                        self.report.add(
                            "MERGE-ID-001",
                            Severity.ERROR,
                            str(story_id),
                            f"story_id отряда '{story_id}' встречается в "
                            f"главах {previous} и {chapter_index}.",
                            hint="Сделайте story_id уникальным.",
                            owner="squad",
                            chapter_a=previous,
                            chapter_b=chapter_index,
                        )
                    else:
                        story_origins.setdefault(story_id, chapter_index)

        for info, origins in info_origins.items():
            unique_origins: list[tuple[int, str]] = []
            for origin in origins:
                if not unique_origins or unique_origins[-1] != origin:
                    unique_origins.append(origin)

            quest_ids = {quest_id for _, quest_id in unique_origins}
            chapter_indexes = {
                chapter_index for chapter_index, _ in unique_origins
            }
            if len(quest_ids) < 2 or len(chapter_indexes) < 2:
                continue

            owners = ", ".join(
                f"'{quest_id}' (глава {chapter_index})"
                for chapter_index, quest_id in unique_origins
            )
            self.report.add(
                "MERGE-INFO-001",
                Severity.WARNING,
                info,
                f"Инфопоршень '{info}' выдают разные квесты из разных глав: "
                f"{owners}.",
                hint=(
                    "Разведите инфопоршни по главам или убедитесь, что "
                    "повторная выдача безопасна."
                ),
                owner="info",
            )


__all__ = ["MergeValidator"]
