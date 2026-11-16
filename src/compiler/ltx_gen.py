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

from src.core.models import DontHasInfo, HasInfo, HasItem
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

        # Ленивый импорт разрывает цикл builder -> ltx_gen -> builder.
        from src.compiler.builder import BuildError

        sections: list[str] = []
        skipped = 0

        for quest_id, quest in quests.items():
            try:
                section = self._build_quest_section(quest_id, quest)
            except BuildError:
                # Ошибка данных, которую нельзя молча пропустить: неподдерживаемое
                # условие condlist делает LTX заведомо неполным.
                raise
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
        ``[<squad_id>]:online_offline_group`` с обязательным ``faction`` и
        хотя бы одним из ``npc``/``npc_random``. Новые поля эмитируются в
        фиксированном порядке и пропускаются, если не заданы:
        ``relationship``, ``npc``, ``npc_random``, ``npc_in_squad``,
        ``target_smart``, ``idle_time``, ``spawn_point``, ``story_id``,
        ``on_death``.

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
            npc_values = self._clean_values(getattr(squad, "npc", None))
            npc_random_values = self._clean_values(
                getattr(squad, "npc_random", None)
            )
            if not faction or (not npc_values and not npc_random_values):
                logger.warning(
                    "Кастомный отряд '%s' пропущен: faction/npc/npc_random "
                    "не заданы.",
                    squad_id,
                )
                continue

            lines = [
                f"[{squad_id.strip()}]:online_offline_group",
                f"faction = {faction}",
            ]
            # Порядок новых полей фиксирован; пустые поля не эмитируются.
            relationship = getattr(squad, "relationship", None)
            if isinstance(relationship, str) and relationship.strip():
                lines.append(f"relationship = {relationship.strip()}")
            if npc_values:
                lines.append(f"npc     = {', '.join(npc_values)}")
            if npc_random_values:
                lines.append(f"npc_random = {', '.join(npc_random_values)}")
            npc_in_squad = [
                int(value)
                for value in (getattr(squad, "npc_in_squad", None) or [])
            ]
            if npc_in_squad:
                lines.append(
                    "npc_in_squad = "
                    + ", ".join(str(value) for value in npc_in_squad)
                )
            target_smart = getattr(squad, "target_smart", None)
            if isinstance(target_smart, str) and target_smart.strip():
                lines.append(f"target_smart = {target_smart.strip()}")
            idle_time = getattr(squad, "idle_time", None)
            if idle_time is not None:
                lines.append(f"idle_time = {float(idle_time):g}")
            spawn_point = getattr(squad, "spawn_point", None)
            if isinstance(spawn_point, str) and spawn_point.strip():
                lines.append(f"spawn_point = {spawn_point.strip()}")
            story_id = getattr(squad, "story_id", None)
            if isinstance(story_id, str) and story_id.strip():
                lines.append(f"story_id = {story_id.strip()}")
            death_infos = self._clean_values(
                getattr(squad, "death_infos", None)
            )
            if death_infos:
                on_death = " ".join(f"+{info}" for info in death_infos)
                lines.append(f"on_death = %{on_death}%")
            sections.append("\n".join(lines))

        if not sections:
            return ""
        logger.info("Сформирован squad_descr_<slug>.ltx: секций=%d.", len(sections))
        return "\n\n".join(sections) + "\n"

    @staticmethod
    def _clean_values(values: object) -> list[str]:
        """Очищает список строковых значений от пустых элементов.

        Args:
            values (object): Сырой список из модели (может быть ``None``).

        Returns:
            list[str]: Непустые строки без ведущих/завершающих пробелов.
        """
        if not isinstance(values, (list, tuple)):
            return []
        cleaned: list[str] = []
        for value in values:
            text = str(value).strip()
            if text:
                cleaned.append(text)
        return cleaned

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

        condlists: list[str] = []
        fail_on_giver_death = bool(
            getattr(quest, "fail_on_giver_death", True)
        )
        if (
            isinstance(giver_npc_id, str)
            and giver_npc_id.strip()
            and fail_on_giver_death
        ):
            # Сохраняем исторический формат строки байт-в-байт.
            condlists.append(
                f"condlist_0            = "
                f"{{!task_giver_alive({quest_id})}} fail"
            )

        start_index = len(condlists)
        extra_condlists = getattr(quest, "extra_condlists", None) or []
        for offset, condlist in enumerate(extra_condlists):
            index = start_index + offset
            conditions = " ".join(
                self._serialize_condlist_condition(condition, quest_id)
                for condition in condlist.when
            )
            key = f"condlist_{index}"
            condlists.append(
                f"{key:<21} = {{{conditions}}} {condlist.result}"
            )

        if condlists:
            lines.append("")
            lines.extend(condlists)

        logger.debug(
            "Секция '%s' сформирована: строк=%d, storyline=%s, этапов=%d.",
            quest_id,
            len(lines),
            storyline,
            stage_complete,
        )
        return "\n".join(lines)

    def _serialize_condlist_condition(
        self,
        condition: object,
        quest_id: str,
    ) -> str:
        """Сериализует условие ``QuestCondlist`` в синтаксис LTX condlist.

        Поддерживаются только условия, представимые в строке condlist:
        ``HasInfo`` (``+info``), ``DontHasInfo`` (``-info``) и ``HasItem``
        (``=actor_has_item(...)`` / ``=actor_has_item_amount(...)``).

        Args:
            condition (object): Условие из ``QuestCondlist.when``.
            quest_id (str): ID квеста для текста ошибки.

        Returns:
            str: Фрагмент условия без фигурных скобок.

        Raises:
            BuildError: Если тип условия не поддерживается в LTX condlist.
        """
        from src.compiler.builder import BuildError

        if isinstance(condition, HasInfo):
            return f"+{condition.info}"
        if isinstance(condition, DontHasInfo):
            return f"-{condition.info}"
        if isinstance(condition, HasItem):
            count = int(getattr(condition, "count", 1))
            if count > 1:
                return (
                    f"=actor_has_item_amount("
                    f"{condition.item_alias}:{count})"
                )
            return f"=actor_has_item({condition.item_alias})"
        raise BuildError(
            f"Квест '{quest_id}': условие {type(condition).__name__} не "
            "поддерживается в extra_condlists (LTX condlist). Допустимы "
            "только HasInfo, DontHasInfo и HasItem; для HasMoney/SmartOwner "
            "используйте transfer_conditions."
        )

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
