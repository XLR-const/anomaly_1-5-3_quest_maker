"""Генератор конфигурации задач мода ``configs\\misc\\task\\tm_mymod.ltx``.

Модуль преобразует карту :class:`~src.core.models.Quest` в LTX-секции,
которые подхватываются штатным менеджером задач Anomaly через
``#include "tm_*.ltx"``. Генератор отвечает только за статическую структуру
секций; тексты, Lua-функторы и диалоги формируются другими модулями
компилятора.

Каждая секция собирается независимо: логическая ошибка в одном квесте
журналируется и не прерывает сборку остальных секций.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.logger import get_logger

if TYPE_CHECKING:
    from src.core.models import Quest

logger = get_logger("compiler.ltx_gen")


class LtxGenerator:
    """Собирает LTX-секции задач мода из карты квестов.

    Имена секций и строковых идентификаторов берутся из ``Quest.id``. Для
    квеста ``mymod_quest_id`` генерируются ссылки ``mymod_quest_id_title`` и
    ``mymod_quest_id_descr``, а также имена функций в пространстве
    ``mymod_quests``.

    Attributes:
        DEFAULT_ICON (str):
            Иконка задачи по умолчанию, используемая во всех секциях.
    """

    DEFAULT_ICON: str = "ui_inGame2_Put_v_pripyat"

    def generate_tasks_ltx(self, quests: dict[str, "Quest"]) -> str:
        """Формирует единое содержимое файла ``tm_mymod.ltx``.

        Секции разделяются одной пустой строкой, что соответствует
        читаемому оформлению штатных ``tm_*.ltx``. Ошибка в данных отдельного
        квеста перехватывается, журналируется через :meth:`logging.Logger.error`
        и не препятствует генерации остальных секций.

        Args:
            quests (dict[str, Quest]):
                Карта квестов проекта, индексированная по ``Quest.id``.

        Returns:
            str: Готовый текст LTX-файла. Если не удалось собрать ни одной
            секции, возвращается пустая строка.

        Raises:
            TypeError:
                Если ``quests`` не является словарём.
        """
        logger.debug("Начата генерация tm_mymod.ltx.")

        if not isinstance(quests, dict):
            error = TypeError(
                "Аргумент quests должен быть словарём карты квестов, "
                f"а получен {type(quests).__name__}."
            )
            logger.error("Некорректный тип карты квестов: %s", error)
            raise error

        sections: list[str] = []
        skipped = 0

        for quest_id, quest in quests.items():
            try:
                section = self._build_quest_section(quest_id, quest)
            except Exception as exc:
                skipped += 1
                logger.error(
                    "Квест '%s' пропущен из-за ошибки данных: %s",
                    quest_id,
                    exc,
                    exc_info=True,
                )
                continue

            sections.append(section)
            logger.debug("Секция квеста '%s' добавлена в LTX.", quest_id)

        if not sections:
            logger.warning(
                "tm_mymod.ltx не содержит ни одной секции "
                "(всего квестов: %d, пропущено: %d).",
                len(quests),
                skipped,
            )
            return ""

        content = "\n\n".join(sections) + "\n"
        logger.info(
            "Сформирован tm_mymod.ltx: секций — %d, пропущено — %d.",
            len(sections),
            skipped,
        )
        return content

    def _build_quest_section(self, quest_id: str, quest: "Quest") -> str:
        """Собирает LTX-секцию одного квеста по спецификации задачи.

        Args:
            quest_id (str):
                Идентификатор секции, он же ключ карты квестов.
            quest (Quest):
                Проверяемая модель квеста.

        Returns:
            str: Текст одной секции без завершающей пустой строки.

        Raises:
            ValueError:
                Если идентификатор секции пуст, содержит недопустимые
                символы или не совпадает с ``Quest.id``.
            TypeError:
                Если ``quest`` не содержит ожидаемых полей модели.
        """
        self._validate_quest(quest_id, quest)

        storyline = "true" if quest.is_storyline else "false"

        lines = [
            f"[{quest_id}]",
            f"icon = {self.DEFAULT_ICON}",
            f"storyline = {storyline}",
            "",
            f"title = {quest_id}_title",
            f"descr = {quest_id}_descr",
            "",
            f"on_init = %=mymod_quests.{quest_id}_on_init%",
            f"on_complete = %=mymod_quests.{quest_id}_on_complete%",
            f"on_fail = %=mymod_quests.{quest_id}_on_fail%",
            "",
            f"status_functor = mymod_quests.{quest_id}_status_functor",
            f"target_functor = mymod_quests.{quest_id}_target_functor",
        ]

        logger.debug(
            "Секция '%s' сформирована: строк — %d, storyline — %s.",
            quest_id,
            len(lines),
            storyline,
        )
        return "\n".join(lines)

    def _validate_quest(self, quest_id: object, quest: object) -> None:
        """Проверяет пригодность квеста для генерации LTX-секции.

        Проверки нужны для изоляции повреждённых данных: Pydantic-модель
        обычно уже валидна, но карта квестов может быть собрана вручную или
        загружена из внешнего источника.

        Args:
            quest_id (object):
                Предполагаемый идентификатор секции.
            quest (object):
                Предполагаемая модель квеста.

        Returns:
            None: Функция ничего не возвращает.

        Raises:
            ValueError:
                Если идентификатор пуст, содержит пробельные символы,
                символы ``[]=`` или не совпадает с ``Quest.id``.
            TypeError:
                Если у объекта отсутствует строковый ``id`` или булев
                признак ``is_storyline``.
        """
        if not isinstance(quest_id, str) or not quest_id.strip():
            raise ValueError("Идентификатор секции квеста должен быть непустой строкой.")

        if any(character.isspace() for character in quest_id):
            raise ValueError(
                f"Идентификатор квеста '{quest_id}' не должен содержать пробелов."
            )

        forbidden = set("[]=\r\n")
        if any(character in forbidden for character in quest_id):
            raise ValueError(
                f"Идентификатор квеста '{quest_id}' содержит недопустимые "
                "для LTX-секции символы."
            )

        actual_id = getattr(quest, "id", None)
        if not isinstance(actual_id, str) or not actual_id:
            raise TypeError(
                f"Квест '{quest_id}' не содержит строкового поля id."
            )

        if actual_id != quest_id:
            raise ValueError(
                f"Ключ карты '{quest_id}' не совпадает с Quest.id='{actual_id}'."
            )

        is_storyline = getattr(quest, "is_storyline", None)
        if not isinstance(is_storyline, bool):
            raise TypeError(
                f"Квест '{quest_id}' не содержит булева поля is_storyline."
            )

        logger.debug("Данные квеста '%s' прошли проверку.", quest_id)


__all__ = ["LtxGenerator"]
