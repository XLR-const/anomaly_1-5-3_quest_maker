"""Генератор файла задач ``gamedata/configs/misc/task/tm_<slug>.ltx``.

Модуль реализует ``[4] RENDER`` для LTX-слоя и следует
``standart_of_auto.md`` (2.2):

* имена функторов — **плоские** (``<task_id>_target``, ``_descr``,
  ``_status``), без префикса Lua-модуля;
* эффекты в ``on_init`` / ``on_complete`` / ``on_fail`` / ``on_cancel``
  записываются только в форме ``%=<task_id>_start()%`` (скобки вызова
  обязательны);
* ``reward_money`` / ``reward_item`` в LTX не попадают — награда выдаётся
  из Lua-эффекта ``<task_id>_reward``;
* каждый сгенерированный функтор имеет одноимённый ключ в
  ``task_functor``/``task_status_functor``/``xr_effects``
  (регистрацию создаёт :class:`src.compiler.lua_gen.LuaGenerator`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.logger import get_logger

if TYPE_CHECKING:
    from src.core.models import CustomSquad, Quest

logger = get_logger("compiler.ltx_gen")


class LtxGenerator:
    """Собирает LTX-секции задач мода из карты квестов.

    Один :class:`~src.core.models.Quest` превращается в одну секцию
    ``[<quest_id>]``. Файл целиком подхватывается ванильным
    ``task_manager.ltx`` через ``#include "tm_*.ltx"``, поэтому сам
    ``task_manager.ltx`` не патчится.
    """

    #: Иконка PDA по умолчанию, если ``Quest.icon`` не задан.
    DEFAULT_ICON: str = "ui_inGame2_Put_v_pripyat"
    #: Приоритет задачи в PDA по умолчанию.
    DEFAULT_PRIOR: int = 60

    def generate_tasks_ltx(self, quests: dict[str, "Quest"]) -> str:
        """Генерирует полный текст ``tm_<slug>.ltx``.

        Каждый квест обрабатывается изолированно: ошибка данных одного
        квеста логируется, а остальные секции всё равно попадают в файл.

        Args:
            quests (dict[str, Quest]):
                Карта квестов проекта. Ключ обязан совпадать с ``Quest.id``.

        Returns:
            str: Секции LTX, разделённые пустой строкой, с завершающим
            переводом строки. Если секций нет — пустая строка.

        Raises:
            TypeError: Если ``quests`` не является словарём.
        """
        logger.debug("Начата генерация tm_<slug>.ltx.")

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
            except Exception as exc:  # noqa: BLE001 - изоляция одного квеста
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
                "tm_<slug>.ltx не содержит ни одной секции "
                "(всего квестов: %d, пропущено: %d).",
                len(quests),
                skipped,
            )
            return ""

        content = "\n\n".join(sections) + "\n"
        logger.info(
            "Сформирован tm_<slug>.ltx: секций=%d, пропущено=%d.",
            len(sections),
            skipped,
        )
        return content

    def generate_squads_ltx(self, squads: dict[str, "CustomSquad"]) -> str:
        """Генерирует ``squad_descr_<slug>.ltx`` с кастомными отрядами.

        Движок автоматически подхватывает любой файл
        ``gamedata/configs/misc/squad_descr/squad_descr_*.ltx`` через глоб в
        ванильном ``squad_descr.ltx``, поэтому ``system.ltx`` патчить не
        нужно.

        Каждая модель превращается в секцию
        ``[<squad_id>]:online_offline_group`` с обязательными полями
        ``faction``/``npc`` и необязательными ``target_smart``/``story_id``.

        Args:
            squads (dict[str, CustomSquad]):
                Карта кастомных отрядов. Ключ обязан совпадать с
                ``CustomSquad.id``.

        Returns:
            str: Секции LTX, разделённые пустой строкой, с завершающим
            переводом строки; пустая строка, если отрядов нет.

        Raises:
            TypeError: Если ``squads`` не является словарём.
        """
        if not isinstance(squads, dict):
            raise TypeError(
                "Аргумент squads должен быть словарём кастомных отрядов, "
                f"а получен {type(squads).__name__}."
            )
        if not squads:
            return ""

        sections: list[str] = []
        for squad_id, squad in squads.items():
            if not isinstance(squad_id, str) or not squad_id.strip():
                logger.warning(
                    "Кастомный отряд с некорректным ключом %r пропущен.",
                    squad_id,
                )
                continue

            faction = str(getattr(squad, "faction", "") or "").strip()
            npc_values = [
                str(value).strip()
                for value in (getattr(squad, "npc", None) or [])
                if str(value).strip()
            ]
            if not faction or not npc_values:
                logger.warning(
                    "Кастомный отряд '%s' пропущен: faction/npc не заданы.",
                    squad_id,
                )
                continue

            lines = [
                f"[{squad_id.strip()}]:online_offline_group",
                f"faction = {faction}",
                f"npc     = {', '.join(npc_values)}",
            ]
            target_smart = getattr(squad, "target_smart", None)
            if isinstance(target_smart, str) and target_smart.strip():
                lines.append(f"target_smart = {target_smart.strip()}")
            story_id = getattr(squad, "story_id", None)
            if isinstance(story_id, str) and story_id.strip():
                lines.append(f"story_id = {story_id.strip()}")
            sections.append("\n".join(lines))

        if not sections:
            return ""
        logger.info("Сформирован squad_descr_<slug>.ltx: секций=%d.", len(sections))
        return "\n\n".join(sections) + "\n"

    def _build_quest_section(self, quest_id: str, quest: "Quest") -> str:
        """Собирает одну секцию ``[<quest_id>]``.

        Формат повторяет эталон ``standart_of_auto.md`` (2.2): плоские
        функторы, ``descr_functor``, ``dont_send_update_news = true`` и
        эффекты с обязательными скобками вызова.

        Args:
            quest_id (str): ID квеста (ключ карты и имя секции).
            quest (Quest): Модель квеста.

        Returns:
            str: Текст секции без завершающего перевода строки.

        Raises:
            ValueError: Если ключ карты не совпадает с ``Quest.id``.
            TypeError: Если обязательные поля модели имеют неверный тип.
        """
        self._validate_quest(quest_id, quest)

        storyline = "true" if quest.is_storyline else "false"
        icon = quest.icon or self.DEFAULT_ICON
        prior = (
            quest.prior
            if quest.prior is not None
            else self.DEFAULT_PRIOR
        )
        stage_complete = len(quest.stages)
        giver_npc_id = quest.npc_id or quest.giver_npc_id

        lines = [
            f"[{quest_id}]",
            f"icon                  = {icon}",
            f"prior                 = {prior}",
            f"storyline             = {storyline}",
            f"title                 = {quest_id}_title",
            f"descr                 = {quest_id}_descr",
            f"descr_functor         = {quest_id}_descr",
            f"target_functor        = {quest_id}_target",
            f"status_functor        = {quest_id}_status",
            f"stage_complete        = {stage_complete}",
            "dont_send_update_news = true",
            "",
            f"on_init               = %={quest_id}_start()%",
            f"on_complete           = %={quest_id}_reward()%",
            f"on_fail               = %={quest_id}_cleanup()%",
            f"on_cancel             = %={quest_id}_cleanup()%",
        ]

        if isinstance(giver_npc_id, str) and giver_npc_id.strip():
            lines.extend(
                [
                    "",
                    f"condlist_0            = "
                    f"{{!task_giver_alive({quest_id})}} fail",
                ]
            )

        logger.debug(
            "Секция '%s' сформирована: строк=%d, storyline=%s, этапов=%d.",
            quest_id,
            len(lines),
            storyline,
            stage_complete,
        )
        return "\n".join(lines)

    def _validate_quest(self, quest_id: object, quest: object) -> None:
        """Проверяет данные квеста перед сериализацией в LTX.

        Args:
            quest_id (object): Ключ карты квестов.
            quest (object): Модель квеста (может быть произвольным объектом).

        Returns:
            None: Функция ничего не возвращает.

        Raises:
            ValueError: Если ID пуст/содержит пробелы или недопустимые для
                LTX-секции символы, либо не совпадает с ``Quest.id``.
            TypeError: Если обязательные поля отсутствуют или имеют
                неверный тип.
        """
        if not isinstance(quest_id, str) or not quest_id.strip():
            raise ValueError(
                "Идентификатор секции квеста должен быть непустой строкой."
            )
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
        stages = getattr(quest, "stages", None)
        if not isinstance(stages, dict) or not stages:
            raise TypeError(
                f"Квест '{quest_id}' не содержит непустой карты stages."
            )
        logger.debug("Данные квеста '%s' прошли проверку.", quest_id)


__all__ = ["LtxGenerator"]
