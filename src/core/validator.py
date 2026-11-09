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
from src.core.models import BaseAction, BaseCondition, ModProject
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
