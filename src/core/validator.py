"""Оркестратор runtime-валидации проекта мода.

Модуль связывает Pydantic-модели :mod:`src.core.models` с проверками игровых
ассетов из :mod:`src.core.conditions` и :mod:`src.core.actions`. Структурная
валидация типов и графов уже выполняется Pydantic при создании моделей; здесь
добавляется следующий уровень — сверка ссылок с SQLite-базой игры.

Класс :class:`ProjectValidator` получает клиент базы через конструктор, что
позволяет использовать как реальный :class:`src.db.repository.GameDatabase`,
так и тестовый двойник с тем же интерфейсом.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from src.core.actions import validate_action_assets
from src.core.conditions import validate_condition_assets
from src.core.models import (
    BaseAction,
    BaseCondition,
    ModProject,
    RemoveSquad,
    SpawnSquad,
)
from src.logger import get_logger

if TYPE_CHECKING:
    from src.db.repository import GameDatabase

logger = get_logger("core.validator")


class ProjectValidator:
    """Проводит runtime-валидацию всех квестов и диалогов проекта мода.

    Валидатор обходит действия этапов/квестов и условия диалогов/реплик,
    делегируя проверку конкретных ассетов функциям :mod:`src.core.conditions`
    и :mod:`src.core.actions`. Логические ошибки сюжета (сиротские инфопоршни
    и циклические блокировки) будут добавлены отдельным этапом.

    Attributes:
        db_client (GameDatabase):
            Клиент SQLite-базы, через который проверяются предметы, смарты и
            отряды. Может быть тестовым двойником с совместимым интерфейсом.
    """

    db_client: GameDatabase

    def __init__(self, db_client: GameDatabase) -> None:
        """Сохраняет клиент базы для последующих проверок.

        Args:
            db_client (GameDatabase):
                Клиент игровой базы данных. Валидатор не открывает соединение
                самостоятельно и не управляет его жизненным циклом.
        """
        self.db_client = db_client

    def validate_project(self, project: ModProject) -> bool:
        """Валидирует проект мода по всем доступным runtime-правилам.

        Метод последовательно обходит:

        * действия ``Quest.on_init_actions``, ``on_complete_actions`` и
          ``on_fail_actions``;
        * действия ``Stage.on_start_actions`` каждого этапа квеста;
        * условия ``Dialog.preconditions``;
        * условия ``Phrase.preconditions`` и действия ``Phrase.actions``
          каждой реплики диалога.

        Для каждого элемента вызываются соответствующие функции из
        :mod:`src.core.conditions` и :mod:`src.core.actions`. Если хотя бы одна
        проверка вернула ``False``, итоговый результат также будет ``False``.

        Args:
            project (ModProject):
                Структурно валидный проект мода. Pydantic уже проверил типы,
                обязательные поля, граф реплик и непрерывность этапов при
                создании объекта.

        Returns:
            bool:
                ``True``, если все runtime-проверки ассетов пройдены. Сейчас
                проверки являются заглушками, поэтому метод возвращает
                ``True`` для любого корректного Pydantic-проекта.

        TODO:
            Реализовать поиск логических ошибок в сюжете:
            1) Проверка на сиротские инфопоршни (квест или фраза требуют
               ``has_info``, но этот поршень физически никогда не выдается ни
               в одном действии ``GiveInfo`` внутри проекта).
            2) Проверка циклических блокировок квестов.

            Для поиска сиротских поршней потребуется собрать множество всех
            ``HasInfo.info``/``DontHasInfo.info``, требуемых условиями, и
            сопоставить его с множеством ``GiveInfo.info``, выдаваемых любыми
            действиями проекта. Разница множеств и будет списком никогда не
            выдаваемых поршней. Для анализа циклов потребуется отдельно
            описать зависимости между квестами (например, квест A требует
            завершения B, а B — завершения A) и выполнить поиск циклов в графе.

        Notes:
            Метод намеренно не пересоздаёт Pydantic-модели: проект считается
            структурно валидным уже на момент передачи. Повторная валидация
            сырых данных относится к слою загрузки, а не к runtime-проверке
            игровых ассетов.
        """
        logger.info(
            "Глобальная валидация проекта '%s' запущена...",
            project.name,
        )

        is_valid = True

        for quest in project.quests.values():
            logger.debug("Проверка квеста '%s'.", quest.id)

            quest_actions = (
                ("on_init_actions", quest.on_init_actions),
                ("on_complete_actions", quest.on_complete_actions),
                ("on_fail_actions", quest.on_fail_actions),
            )
            for field_name, actions in quest_actions:
                if not self._validate_actions(
                    actions,
                    f"квест '{quest.id}' ({field_name})",
                ):
                    is_valid = False

            for stage in quest.stages.values():
                if not self._validate_actions(
                    stage.on_start_actions,
                    f"квест '{quest.id}', этап {stage.id} (on_start_actions)",
                ):
                    is_valid = False

        for dialog in project.dialogs.values():
            logger.debug("Проверка диалога '%s'.", dialog.id)

            if not self._validate_conditions(
                dialog.preconditions,
                f"диалог '{dialog.id}' (preconditions)",
            ):
                is_valid = False

            for phrase in dialog.phrases.values():
                phrase_owner = f"диалог '{dialog.id}', фраза {phrase.id}"

                if not self._validate_conditions(
                    phrase.preconditions,
                    f"{phrase_owner} (preconditions)",
                ):
                    is_valid = False

                if not self._validate_actions(
                    phrase.actions,
                    f"{phrase_owner} (actions)",
                ):
                    is_valid = False

        if not self._validate_story_squad_data(project):
            is_valid = False
        if not self._validate_mixed_quests(project):
            is_valid = False

        # TODO: Реализовать поиск логических ошибок в сюжете:
        # 1) Проверка на сиротские инфопоршни (квест или фраза требуют
        #    `has_info`, но этот поршень физически никогда не выдается ни в
        #    одном действии `GiveInfo` внутри проекта).
        # 2) Проверка циклических блокировок квестов.
        # Для этого здесь нужно собрать индексы требуемых и выдаваемых
        # поршней, а затем построить и проверить граф зависимостей квестов.

        logger.info(
            "Глобальная валидация проекта '%s' завершена. Результат: %s.",
            project.name,
            "успешно" if is_valid else "найдены ошибки",
        )
        return is_valid

    @staticmethod
    def _iter_actions_with_owner(
        project: ModProject,
    ) -> Iterable[tuple[str, BaseAction]]:
        """Перебирает все действия проекта вместе с контекстом.

        Args:
            project (ModProject): Проект мода.

        Yields:
            tuple[str, BaseAction]: Человекочитаемый владелец и действие.
        """
        for quest in (project.quests or {}).values():
            for field_name in (
                "on_init_actions",
                "on_complete_actions",
                "on_fail_actions",
            ):
                for action in getattr(quest, field_name, []) or []:
                    yield f"квест '{quest.id}' ({field_name})", action
            for stage in (quest.stages or {}).values():
                for action in stage.on_start_actions or []:
                    yield (
                        f"квест '{quest.id}', этап {stage.id} "
                        "(on_start_actions)",
                        action,
                    )
        for dialog in (project.dialogs or {}).values():
            for phrase in (dialog.phrases or {}).values():
                for action in phrase.actions or []:
                    yield (
                        f"диалог '{dialog.id}', фраза {phrase.id} (actions)",
                        action,
                    )

    def _squad_alias_exists(
        self,
        project: ModProject,
        alias: str,
    ) -> bool:
        """Проверяет, что алиас отряда существует в проекте или в БД.

        Args:
            project (ModProject): Проект мода.
            alias (str): Секция/Story-ID отряда.

        Returns:
            bool: ``True``, если отряд найден в ``project.squads`` или в
            SQLite-базе через ``find_squad_by_alias``.
        """
        normalized = str(alias or "").strip()
        if not normalized:
            return False
        for squad_key, squad in (project.squads or {}).items():
            if str(squad_key).strip() == normalized:
                return True
            story_id = getattr(squad, "story_id", None)
            if isinstance(story_id, str) and story_id.strip() == normalized:
                return True

        finder = getattr(self.db_client, "find_squad_by_alias", None)
        if callable(finder):
            try:
                return finder(normalized) is not None
            except Exception as exc:  # noqa: BLE001 - БД может быть недоступна
                logger.warning(
                    "Не удалось проверить отряд '%s' по БД: %s",
                    normalized,
                    exc,
                )
        return False

    def _validate_story_squad_data(self, project: ModProject) -> bool:
        """Проверяет Story-отряды и ссылки на них.

        Проверки:

        * ``CustomSquad.story_id`` уникален в проекте;
        * ``CustomSquad.death_infos`` не содержит пустых строк;
        * ``SpawnSquad(mode="story").squad_alias`` и ``RemoveSquad.squad_alias``
          ссылаются на существующий отряд проекта или ванильной БД.

        Args:
            project (ModProject): Проект мода.

        Returns:
            bool: ``True``, если нарушений нет.
        """
        is_valid = True
        seen_story_ids: dict[str, str] = {}

        for squad_key, squad in (project.squads or {}).items():
            story_id = getattr(squad, "story_id", None)
            normalized_story_id = (
                story_id.strip() if isinstance(story_id, str) else ""
            )
            if normalized_story_id:
                previous = seen_story_ids.get(normalized_story_id)
                if previous is not None:
                    logger.error(
                        "Story-ID отряда '%s' дублируется: '%s' и '%s'.",
                        normalized_story_id,
                        previous,
                        squad_key,
                    )
                    is_valid = False
                else:
                    seen_story_ids[normalized_story_id] = str(squad_key)

            for index, death_info in enumerate(
                getattr(squad, "death_infos", None) or []
            ):
                if (
                    not isinstance(death_info, str)
                    or not death_info.strip()
                ):
                    logger.error(
                        "Отряд '%s': death_infos[%d] пуст или не является "
                        "строкой.",
                        squad_key,
                        index,
                    )
                    is_valid = False

        for owner, action in self._iter_actions_with_owner(project):
            if isinstance(action, SpawnSquad):
                if getattr(action, "mode", "warfare") != "story":
                    continue
                if not self._squad_alias_exists(
                    project, action.squad_alias
                ):
                    logger.error(
                        "Действие SpawnSquad(mode='story') в %s ссылается на "
                        "отсутствующий отряд '%s'.",
                        owner,
                        action.squad_alias,
                    )
                    is_valid = False
            elif isinstance(action, RemoveSquad):
                if not self._squad_alias_exists(
                    project, action.squad_alias
                ):
                    logger.error(
                        "Действие RemoveSquad в %s ссылается на "
                        "отсутствующий отряд '%s'.",
                        owner,
                        action.squad_alias,
                    )
                    is_valid = False

        return is_valid

    def _validate_mixed_quests(self, project: ModProject) -> bool:
        """Запрещает смешивать Warfare-захват и Story-спавн в одном квесте.

        Фаза 2 не поддерживает квесты, где одновременно есть
        ``Stage.warfare_capture`` и ``SpawnSquad(mode="story")``: world-гейт
        Warfare делает такой квест недоступным в freeplay.

        Args:
            project (ModProject): Проект мода.

        Returns:
            bool: ``True``, если смешанных квестов нет.
        """
        is_valid = True
        for quest in (project.quests or {}).values():
            has_capture = any(
                stage.warfare_capture is not None
                for stage in (quest.stages or {}).values()
            )
            if not has_capture:
                continue

            actions: list[BaseAction] = []
            for field_name in (
                "on_init_actions",
                "on_complete_actions",
                "on_fail_actions",
            ):
                actions.extend(getattr(quest, field_name, []) or [])
            for stage in (quest.stages or {}).values():
                actions.extend(stage.on_start_actions or [])

            related_dialogs = set(quest.dialog_ids or [])
            if quest.dialog_id:
                related_dialogs.add(quest.dialog_id)
            for dialog in (project.dialogs or {}).values():
                dialog_id = getattr(dialog, "dialog_id", None) or dialog.id
                if (
                    getattr(dialog, "task_id", None) == quest.id
                    or dialog_id in related_dialogs
                ):
                    for phrase in (dialog.phrases or {}).values():
                        actions.extend(phrase.actions or [])

            story_spawns = [
                action
                for action in actions
                if isinstance(action, SpawnSquad)
                and getattr(action, "mode", "warfare") == "story"
            ]
            if story_spawns:
                logger.error(
                    "Квест '%s' смешивает warfare_capture и "
                    "SpawnSquad(mode='story'); разделите его на два квеста.",
                    quest.id,
                )
                is_valid = False

        return is_valid

    def _validate_conditions(
        self,
        conditions: Iterable[BaseCondition],
        owner: str,
    ) -> bool:
        """Проверяет группу условий и агрегирует результат.

        Args:
            conditions (Iterable[BaseCondition]):
                Условия диалога или реплики.
            owner (str):
                Человекочитаемый контекст для сообщений лога, например
                ``"диалог 'start_dialog', фраза 0 (preconditions)"``.

        Returns:
            bool:
                ``True``, если все условия прошли runtime-проверку. Сейчас
                проверки-заглушки всегда возвращают ``True``.
        """
        is_valid = True

        for condition in conditions:
            if not validate_condition_assets(condition, self.db_client):
                is_valid = False
                logger.warning(
                    "Условие %s в %s не прошло runtime-проверку.",
                    type(condition).__name__,
                    owner,
                )

        return is_valid

    def _validate_actions(
        self,
        actions: Iterable[BaseAction],
        owner: str,
    ) -> bool:
        """Проверяет группу действий и агрегирует результат.

        Args:
            actions (Iterable[BaseAction]):
                Действия квеста, этапа или реплики.
            owner (str):
                Человекочитаемый контекст для сообщений лога, например
                ``"квест 'main_quest' (on_init_actions)"``.

        Returns:
            bool:
                ``True``, если все действия прошли runtime-проверку. Сейчас
                проверки-заглушки всегда возвращают ``True``.
        """
        is_valid = True

        for action in actions:
            if not validate_action_assets(action, self.db_client):
                is_valid = False
                logger.warning(
                    "Действие %s в %s не прошло runtime-проверку.",
                    type(action).__name__,
                    owner,
                )

        return is_valid


__all__ = ["ProjectValidator"]
