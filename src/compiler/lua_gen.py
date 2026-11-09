"""Генератор Lua 5.1 скрипта логики квестов для S.T.A.L.K.E.R. Anomaly.

Модуль собирает единый текст ``scripts\\mymod_quests.script`` из моделей
:class:`~src.core.models.ModProject`. В сгенерированном скрипте находятся:

* безопасная обвязка ``save_var``/``load_var`` для служебных флагов;
* хелперы Warfare: проверка захвата смарта и спавн квестового отряда;
* квестовые функторы ``on_init``, ``on_complete``, ``on_fail``,
  ``status_functor`` и ``target_functor``;
* XML-функторы предусловий и действий реплик диалогов.

Генератор не пишет файлы на диск: он возвращает готовую Unicode-строку.
Сохранение в Windows-1251 без BOM выполняет отдельный слой компилятора.

Каждый квест и каждый диалог обрабатываются изолированно. Если один элемент
повреждён, ошибка журналируется через ``logger.error``, а остальные элементы
продолжают собираться. Имена функций соответствуют ожиданиям
:class:`~src.compiler.ltx_gen.LtxGenerator` и
:class:`~src.compiler.xml_gen.XmlGenerator` (префикс ``mymod_quests.``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from src.core.models import (
    DontHasInfo,
    GiveInfo,
    GiveItem,
    GiveMoney,
    HasInfo,
    HasItem,
    RemoveInfo,
    RemoveItem,
    SetTarget,
    SmartOwner,
    SpawnSquad,
)
from src.logger import get_logger

if TYPE_CHECKING:
    from src.core.models import BaseAction, BaseCondition, ModProject

logger = get_logger("compiler.lua_gen")

#: Имя глобальной таблицы, которую образует файл ``mymod_quests.script``.
SCRIPT_TABLE = "mymod_quests"
#: Звук КПК, воспроизводимый при выдаче новой задачи.
PDA_SOUND = "pda_task"
#: Префикс ключей ``save_var`` для флагов уже проигранных звуков.
PDA_FLAG_PREFIX = "mymod_quests_pda"
#: Допустимый идентификатор Lua-функции и таблицы.
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: Явно поддерживаемые результаты правил ``transfer_conditions``.
_TRANSFER_RESULTS = ("complete", "fail")


class LuaGenerator:
    """Собирает Lua-скрипт логики квестов и диалогов проекта.

    Класс рассчитан на модели :class:`~src.core.models.ModProject`,
    :class:`~src.core.models.Quest`, :class:`~src.core.models.Stage`,
    :class:`~src.core.models.Dialog` и :class:`~src.core.models.Phrase`.

    Дополнительно поддерживается необязательное поле
    ``transfer_conditions`` у квеста или этапа. Оно не входит в текущую
    базовую Pydantic-модель, но может быть добавлено наследником модели или
    загружено из расширенной схемы. Поддерживаемые формы:

    * ``{0: {"complete": [...], "fail": [...]}, 1: [...]}`` — правила для
      конкретных этапов; список без словаря означает условия завершения
      этапа;
    * ``{"complete": [...], "fail": [...]}`` — правила всего квеста;
    * список условий — условие завершения последнего этапа.

    Условия — обычные Pydantic-объекты из :mod:`src.core.models`.
    """

    # ------------------------------------------------------------------
    # Публичная точка входа
    # ------------------------------------------------------------------

    def generate_quests_script(self, project: "ModProject") -> str:
        """Формирует единый Lua-скрипт ``mymod_quests.script``.

        Метод собирает шапку с хелперами, затем блоки всех квестов и всех
        диалогов проекта. Ошибка в одном квесте или диалоге перехватывается,
        журналируется и не мешает генерации остальных сущностей.

        Args:
            project (ModProject):
                Корневая модель проекта с картами ``quests`` и ``dialogs``.

        Returns:
            str: Готовый текст Lua 5.1 скрипта. Даже для пустого проекта
            возвращается корректная шапка со служебными хелперами.

        Raises:
            TypeError:
                Если проект не содержит словарных карт ``quests`` и
                ``dialogs``.
        """
        logger.debug("Начата генерация mymod_quests.script.")

        try:
            quests = getattr(project, "quests", None)
            dialogs = getattr(project, "dialogs", None)

            if not isinstance(quests, dict) or not isinstance(dialogs, dict):
                raise TypeError(
                    "Проект должен содержать словарные карты quests и "
                    "dialogs, а получены "
                    f"{type(quests).__name__} и {type(dialogs).__name__}."
                )
        except TypeError as exc:
            logger.error("Некорректный проект для генерации Lua: %s", exc)
            raise
        except Exception as exc:
            logger.exception(
                "Не удалось прочитать карты проекта для генерации Lua: %s",
                exc,
            )
            raise

        blocks: list[str] = [self._build_header()]
        generated_quests = 0
        generated_dialogs = 0
        skipped_quests = 0
        skipped_dialogs = 0

        for quest_id in sorted(quests, key=lambda value: str(value)):
            try:
                block = self._build_quest(quest_id, quests[quest_id])
            except Exception as exc:
                skipped_quests += 1
                logger.error(
                    "Квест '%s' пропущен из-за ошибки данных: %s",
                    quest_id,
                    exc,
                    exc_info=True,
                )
                continue

            blocks.append(block)
            generated_quests += 1
            logger.debug("Квест '%s' добавлен в Lua-скрипт.", quest_id)

        for dialog_id in sorted(dialogs, key=lambda value: str(value)):
            try:
                block = self._build_dialog(dialog_id, dialogs[dialog_id])
            except Exception as exc:
                skipped_dialogs += 1
                logger.error(
                    "Диалог '%s' пропущен из-за ошибки данных: %s",
                    dialog_id,
                    exc,
                    exc_info=True,
                )
                continue

            if block:
                blocks.append(block)
                generated_dialogs += 1
                logger.debug("Диалог '%s' добавлен в Lua-скрипт.", dialog_id)
            else:
                logger.debug(
                    "Диалог '%s' не содержит фраз с логикой и пропущен.",
                    dialog_id,
                )

        blocks.append(self._build_footer())

        content = "\n\n".join(
            block.rstrip() for block in blocks if block and block.strip()
        )
        content += "\n"

        logger.info(
            "Сформирован mymod_quests.script: квестов — %d, диалогов — %d, "
            "пропущено квестов — %d, пропущено диалогов — %d.",
            generated_quests,
            generated_dialogs,
            skipped_quests,
            skipped_dialogs,
        )
        return content

    # ------------------------------------------------------------------
    # Шапка и служебные хелперы
    # ------------------------------------------------------------------

    def _build_header(self) -> str:
        """Собирает шапку скрипта со служебными функциями.

        Шапка содержит безопасные обёртки над штатными ``save_var`` и
        ``load_var``, resolver целей, проверку захвата смарта и спавн отряда.
        Именно эти хелперы используют сгенерированные квестовые функторы.

        Returns:
            str: Текст шапки без завершающих пустых строк.

        Raises:
            Exception:
                Любая ошибка формирования шапки журналируется и пробрасывается
                вызывающему коду.
        """
        try:
            lines = [
                "-- =========================================================",
                "-- mymod_quests.script",
                "-- Автоматически сгенерирован компилятором квестов.",
                "-- Lua 5.1 / S.T.A.L.K.E.R. Anomaly.",
                "-- Не редактируйте файл вручную: изменения будут потеряны.",
                "-- =========================================================",
                "",
                f"{SCRIPT_TABLE} = {SCRIPT_TABLE} or {{}}",
                "",
                f'local PDA_FLAG_PREFIX = "{PDA_FLAG_PREFIX}"',
                "",
                "-- Сохраняет служебный флаг в сейв актора.",
                "local function mymod_save_var(key, value)",
                "    if not db or not db.actor then",
                "        return",
                "    end",
                "    save_var(db.actor, key, value)",
                "end",
                "",
                "-- Читает служебный флаг из сейва актора.",
                "local function mymod_load_var(key)",
                "    if not db or not db.actor then",
                "        return nil",
                "    end",
                "    return load_var(db.actor, key)",
                "end",
                "",
                "-- Разрешает алиас смарта, story_id или числовой id в id объекта.",
                "local function mymod_resolve_target(target)",
                '    if target == nil or target == "" then',
                "        return nil",
                "    end",
                "",
                "    if SIMBOARD and SIMBOARD.smarts_by_names then",
                "        local smart = SIMBOARD.smarts_by_names[target]",
                "        if smart then",
                "            return smart.id",
                "        end",
                "    end",
                "",
                "    local numeric_id = tonumber(target)",
                "    if numeric_id then",
                "        local obj = alife_object(numeric_id)",
                "        return obj and obj.id or nil",
                "    end",
                "",
                "    local story_obj = alife():story_object(target)",
                "    return story_obj and story_obj.id or nil",
                "end",
                "",
                "-- Проверяет, захвачен ли смарт указанной фракцией.",
                "function mymod_quests.is_smart_captured(smart_id, faction)",
                "    local smart = nil",
                "",
                "    if SIMBOARD and SIMBOARD.smarts_by_names then",
                "        smart = SIMBOARD.smarts_by_names[smart_id]",
                "    end",
                "",
                "    if not smart then",
                "        local numeric_id = tonumber(smart_id)",
                "        smart = numeric_id and alife_object(numeric_id) or nil",
                "    end",
                "",
                "    if not smart then",
                "        return false",
                "    end",
                "",
                "    local squads = smart.squads or {}",
                "    for _, squad in pairs(squads) do",
                "        if squad and squad.npc_count and squad:npc_count() > 0 then",
                "            return false",
                "        end",
                "    end",
                "",
                "    local owner = smart.owning_faction",
                "    local defense_count = smart.defense_count or 0",
                "    return (owner == faction) or (defense_count <= 0)",
                "end",
                "",
                "-- Спавнит квестовый отряд и удерживает его на смарте.",
                "function mymod_quests.spawn_task_squad(squad_id, smart_id)",
                "    local smart = nil",
                "",
                "    if SIMBOARD and SIMBOARD.smarts_by_names then",
                "        smart = SIMBOARD.smarts_by_names[smart_id]",
                "    end",
                "",
                "    if not smart then",
                "        local numeric_id = tonumber(smart_id)",
                "        smart = numeric_id and alife_object(numeric_id) or nil",
                "    end",
                "",
                "    if not smart then",
                "        return nil",
                "    end",
                "",
                "    local board = sim_board.get_sim_board()",
                "    if not board then",
                "        return nil",
                "    end",
                "",
                "    local squad = board:setup_squad_and_move(squad_id, smart)",
                "    if not squad then",
                "        return nil",
                "    end",
                "",
                "    squad.stay_time = nil",
                "    if sim_squad_warfare and sim_squad_warfare.set_target then",
                "        sim_squad_warfare.set_target(squad, smart.id)",
                "    end",
                "    squad.stay_time = game.get_game_time()",
                "    squad.force_online = true",
                "",
                "    if sim_offline_combat and sim_offline_combat.task_squads then",
                "        sim_offline_combat.task_squads[squad.id] = true",
                "    end",
                "",
                "    return squad",
                "end",
                "",
                "-- Назначает отряду цель и фиксирует его на смарте.",
                "function mymod_quests.set_task_target(squad_alias, smart_id)",
                "    local target = mymod_resolve_target(smart_id)",
                "    if not target then",
                "        return",
                "    end",
                "",
                "    local squad = nil",
                "    if SIMBOARD and SIMBOARD.squads_by_names then",
                "        squad = SIMBOARD.squads_by_names[squad_alias]",
                "    end",
                "",
                "    if not squad then",
                "        return",
                "    end",
                "",
                "    squad.stay_time = nil",
                "    if sim_squad_warfare and sim_squad_warfare.set_target then",
                "        sim_squad_warfare.set_target(squad, target)",
                "    end",
                "    squad.stay_time = game.get_game_time()",
                "    squad.force_online = true",
                "end",
            ]

            logger.debug("Шапка Lua-скрипта сформирована: строк — %d.", len(lines))
            return "\n".join(lines)
        except Exception as exc:
            logger.exception("Не удалось сформировать шапку Lua-скрипта: %s", exc)
            raise

    def _build_footer(self) -> str:
        """Собирает завершающий комментарий скрипта.

        Returns:
            str: Короткий финальный комментарий Lua-файла.

        Raises:
            Exception:
                Ошибка формирования журналируется и пробрасывается дальше.
        """
        try:
            logger.debug("Формирование завершающего блока Lua-скрипта.")
            return "-- Конец автоматически сгенерированного mymod_quests.script"
        except Exception as exc:
            logger.exception(
                "Не удалось сформировать завершающий блок Lua-скрипта: %s",
                exc,
            )
            raise

    # ------------------------------------------------------------------
    # Сборка квеста
    # ------------------------------------------------------------------

    def _build_quest(self, quest_id: Any, quest: Any) -> str:
        """Собирает все Lua-функторы одного квеста.

        Args:
            quest_id (Any):
                Ключ карты квестов; должен совпадать с ``Quest.id``.
            quest (Any):
                Модель квеста или совместимый объект с ожидаемыми полями.

        Returns:
            str: Блок функций квеста без завершающей пустой строки.

        Raises:
            ValueError:
                Если идентификатор квеста некорректен или не совпадает с
                ``Quest.id``.
            TypeError:
                Если карта этапов или списки действий имеют неверный тип.
            Exception:
                Любая ошибка сборки журналируется и пробрасывается, чтобы
                ``generate_quests_script`` мог пропустить повреждённый квест.
        """
        try:
            self._validate_quest(quest_id, quest)

            blocks = [
                self._build_quest_on_init(quest_id, quest),
                self._build_quest_on_complete(quest_id, quest),
                self._build_quest_on_fail(quest_id, quest),
                self._build_quest_status_functor(quest_id, quest),
                self._build_quest_target_functor(quest_id, quest),
            ]
            content = "\n\n".join(blocks)

            logger.debug(
                "Квест '%s' собран: функций — %d, символов — %d.",
                quest_id,
                len(blocks),
                len(content),
            )
            return content
        except Exception as exc:
            logger.error(
                "Не удалось собрать Lua-квест '%s': %s",
                quest_id,
                exc,
                exc_info=True,
            )
            raise

    def _build_quest_on_init(self, quest_id: str, quest: Any) -> str:
        """Собирает функцию ``{quest_id}_on_init(tsk)``.

        Функция проигрывает звук КПК только один раз. Признак уже
        проигранного звука сохраняется через ``mymod_save_var``, поэтому
        загрузка сейва не вызывает повторный звук.

        Args:
            quest_id (str):
                Идентификатор квеста.
            quest (Any):
                Модель квеста с полем ``on_init_actions``.

        Returns:
            str: Текст функции ``on_init``.

        Raises:
            TypeError:
                Если ``on_init_actions`` не является списком.
            Exception:
                Ошибка формирования блока журналируется и пробрасывается.
        """
        try:
            actions = getattr(quest, "on_init_actions", None)
            self._require_list(actions, f"on_init_actions квеста '{quest_id}'")

            lines = [
                f"function {SCRIPT_TABLE}.{quest_id}_on_init(tsk)",
                "    if not tsk then",
                "        return",
                "    end",
                "",
                f'    local sound_key = PDA_FLAG_PREFIX .. "_{quest_id}_on_init"',
                "    if not mymod_load_var(sound_key) then",
                "        mymod_save_var(sound_key, true)",
                f'        xr_sound.set_sound_play(db.actor, "{PDA_SOUND}")',
                "    end",
                "",
            ]
            action_lines = self._build_action_lines(
                actions,
                f"квест '{quest_id}' (on_init)",
                actor_expr="db.actor",
            )
            lines.extend(action_lines or ["    -- Действий при выдаче квеста нет."])
            lines.append("end")

            logger.debug(
                "Функция '%s_on_init' сформирована: действий — %d.",
                quest_id,
                len(actions),
            )
            return "\n".join(lines)
        except Exception as exc:
            logger.error(
                "Ошибка формирования '%s_on_init': %s",
                quest_id,
                exc,
            )
            raise

    def _build_quest_on_complete(self, quest_id: str, quest: Any) -> str:
        """Собирает функцию ``{quest_id}_on_complete(tsk)``.

        Args:
            quest_id (str):
                Идентификатор квеста.
            quest (Any):
                Модель квеста с полями ``on_complete_actions`` и
                ``title_ru``.

        Returns:
            str: Текст функции завершения квеста.

        Raises:
            TypeError:
                Если ``on_complete_actions`` не является списком.
            Exception:
                Ошибка формирования блока журналируется и пробрасывается.
        """
        try:
            actions = getattr(quest, "on_complete_actions", None)
            self._require_list(
                actions,
                f"on_complete_actions квеста '{quest_id}'",
            )
            title = self._require_text(
                getattr(quest, "title_ru", None),
                f"title_ru квеста '{quest_id}'",
            )

            lines = [
                f"function {SCRIPT_TABLE}.{quest_id}_on_complete(tsk)",
                "    if not tsk then",
                "        return",
                "    end",
                "",
                "    news_manager.send_tip(",
                "        db.actor,",
                f"        {self._lua_string(title + ' — квест завершён.')},",
                "        nil,",
                "        nil,",
                "        10000",
                "    )",
                "",
            ]
            action_lines = self._build_action_lines(
                actions,
                f"квест '{quest_id}' (on_complete)",
                actor_expr="db.actor",
            )
            lines.extend(action_lines or ["    -- Наград у квеста нет."])
            lines.append("end")

            logger.debug(
                "Функция '%s_on_complete' сформирована: действий — %d.",
                quest_id,
                len(actions),
            )
            return "\n".join(lines)
        except Exception as exc:
            logger.error(
                "Ошибка формирования '%s_on_complete': %s",
                quest_id,
                exc,
            )
            raise

    def _build_quest_on_fail(self, quest_id: str, quest: Any) -> str:
        """Собирает функцию ``{quest_id}_on_fail(tsk)``.

        Args:
            quest_id (str):
                Идентификатор квеста.
            quest (Any):
                Модель квеста с полями ``on_fail_actions`` и ``title_ru``.

        Returns:
            str: Текст функции провала квеста.

        Raises:
            TypeError:
                Если ``on_fail_actions`` не является списком.
            Exception:
                Ошибка формирования блока журналируется и пробрасывается.
        """
        try:
            actions = getattr(quest, "on_fail_actions", None)
            self._require_list(
                actions,
                f"on_fail_actions квеста '{quest_id}'",
            )
            title = self._require_text(
                getattr(quest, "title_ru", None),
                f"title_ru квеста '{quest_id}'",
            )

            lines = [
                f"function {SCRIPT_TABLE}.{quest_id}_on_fail(tsk)",
                "    if not tsk then",
                "        return",
                "    end",
                "",
                "    news_manager.send_tip(",
                "        db.actor,",
                f"        {self._lua_string(title + ' — квест провален.')},",
                "        nil,",
                "        nil,",
                "        10000",
                "    )",
                "",
            ]
            action_lines = self._build_action_lines(
                actions,
                f"квест '{quest_id}' (on_fail)",
                actor_expr="db.actor",
            )
            lines.extend(action_lines or ["    -- Действий при провале нет."])
            lines.append("end")

            logger.debug(
                "Функция '%s_on_fail' сформирована: действий — %d.",
                quest_id,
                len(actions),
            )
            return "\n".join(lines)
        except Exception as exc:
            logger.error(
                "Ошибка формирования '%s_on_fail': %s",
                quest_id,
                exc,
            )
            raise

    def _build_quest_status_functor(
        self,
        quest_id: str,
        quest: Any,
    ) -> str:
        """Собирает функцию ``{quest_id}_status_functor(tsk, task_id)``.

        Функтор проверяет Pydantic-условия ``transfer_conditions``. Правила
        провала имеют приоритет над правилами завершения. При выполнении
        условия не последнего этапа ``tsk.stage`` увеличивается на единицу;
        на последнем этапе функтор возвращает ``"complete"``.

        Args:
            quest_id (str):
                Идентификатор квеста.
            quest (Any):
                Модель квеста с картой ``stages`` и необязательным полем
                ``transfer_conditions``.

        Returns:
            str: Текст функции ``status_functor``.

        Raises:
            TypeError:
                Если карта этапов повреждена или правила переходов имеют
                неподдерживаемую структуру.
            Exception:
                Ошибка формирования блока журналируется и пробрасывается.
        """
        try:
            stages = getattr(quest, "stages", None)
            self._require_mapping(stages, f"stages квеста '{quest_id}'")
            stage_ids = sorted(stages)
            if not stage_ids:
                raise ValueError(f"Квест '{quest_id}' не содержит этапов.")

            quest_rules, stage_rules = self._extract_transfer_rules(
                quest_id,
                quest,
                stage_ids,
            )

            lines = [
                f"function {SCRIPT_TABLE}.{quest_id}_status_functor(tsk, task_id)",
                "    if not tsk then",
                "        return nil",
                "    end",
                "",
                "    tsk.stage = tsk.stage or 0",
                "",
            ]

            quest_fail = self._conditions_to_lua(
                quest_rules["fail"],
                owner=f"квест '{quest_id}', общий fail",
            )
            if quest_rules["fail"]:
                lines.extend(
                    [
                        f"    if {quest_fail} then",
                        '        return "fail"',
                        "    end",
                        "",
                    ]
                )

            quest_complete = self._conditions_to_lua(
                quest_rules["complete"],
                owner=f"квест '{quest_id}', общий complete",
            )
            if quest_rules["complete"]:
                lines.extend(
                    [
                        f"    if {quest_complete} then",
                        '        return "complete"',
                        "    end",
                        "",
                    ]
                )

            last_stage_id = stage_ids[-1]

            for stage_id in stage_ids:
                rules = stage_rules[stage_id]
                lines.append(f"    if tsk.stage == {stage_id} then")

                if rules["fail"]:
                    fail_expression = self._conditions_to_lua(
                        rules["fail"],
                        owner=f"квест '{quest_id}', этап {stage_id}, fail",
                    )
                    lines.extend(
                        [
                            f"        if {fail_expression} then",
                            '            return "fail"',
                            "        end",
                        ]
                    )

                if rules["complete"]:
                    complete_expression = self._conditions_to_lua(
                        rules["complete"],
                        owner=f"квест '{quest_id}', этап {stage_id}, complete",
                    )
                    lines.append(f"        if {complete_expression} then")
                    if stage_id == last_stage_id:
                        lines.append('            return "complete"')
                    else:
                        lines.append(
                            f"            tsk.stage = {stage_id + 1}"
                        )
                        next_stage = stages.get(stage_id + 1)
                        next_actions = getattr(
                            next_stage,
                            "on_start_actions",
                            [],
                        )
                        if isinstance(next_actions, list) and next_actions:
                            lines.extend(
                                self._build_action_lines(
                                    next_actions,
                                    (
                                        f"квест '{quest_id}', переход на этап "
                                        f"{stage_id + 1}"
                                    ),
                                    actor_expr="db.actor",
                                    indent="            ",
                                )
                            )
                        lines.append("            return nil")
                    lines.append("        end")

                lines.extend(["        return nil", "    end", ""])

            lines.extend(["    return nil", "end"])

            logger.debug(
                "Функция '%s_status_functor' сформирована: этапов — %d.",
                quest_id,
                len(stage_ids),
            )
            return "\n".join(lines)
        except Exception as exc:
            logger.error(
                "Ошибка формирования '%s_status_functor': %s",
                quest_id,
                exc,
            )
            raise

    def _build_quest_target_functor(
        self,
        quest_id: str,
        quest: Any,
    ) -> str:
        """Собирает функцию ``{quest_id}_target_functor(tsk, task_id)``.

        Для текущего ``tsk.stage`` функтор возвращает id цели, полученный из
        ``Stage.target_alias`` через ``mymod_resolve_target``. Если алиас
        пуст или движок не смог его разрешить, возвращается ``nil``.

        Args:
            quest_id (str):
                Идентификатор квеста.
            quest (Any):
                Модель квеста с картой этапов.

        Returns:
            str: Текст функции ``target_functor``.

        Raises:
            TypeError:
                Если карта этапов повреждена или алиас цели не является
                строкой.
            Exception:
                Ошибка формирования блока журналируется и пробрасывается.
        """
        try:
            stages = getattr(quest, "stages", None)
            self._require_mapping(stages, f"stages квеста '{quest_id}'")
            stage_ids = sorted(stages)
            if not stage_ids:
                raise ValueError(f"Квест '{quest_id}' не содержит этапов.")

            lines = [
                f"function {SCRIPT_TABLE}.{quest_id}_target_functor(tsk, task_id)",
                "    if not tsk then",
                "        return nil",
                "    end",
                "",
                "    local stage = tsk.stage or 0",
                "",
            ]

            for stage_id in stage_ids:
                stage = stages[stage_id]
                target_alias = getattr(stage, "target_alias", None)
                if not isinstance(target_alias, str):
                    raise TypeError(
                        f"Этап {stage_id} квеста '{quest_id}' содержит "
                        "нестроковый target_alias."
                    )

                lines.append(f"    if stage == {stage_id} then")
                if target_alias.strip():
                    lines.append(
                        "        return mymod_resolve_target("
                        f"{self._lua_string(target_alias)})"
                    )
                else:
                    lines.append("        return nil")
                lines.extend(["    end", ""])

            lines.extend(["    return nil", "end"])

            logger.debug(
                "Функция '%s_target_functor' сформирована: этапов — %d.",
                quest_id,
                len(stage_ids),
            )
            return "\n".join(lines)
        except Exception as exc:
            logger.error(
                "Ошибка формирования '%s_target_functor': %s",
                quest_id,
                exc,
            )
            raise

    # ------------------------------------------------------------------
    # Сборка диалогов
    # ------------------------------------------------------------------

    def _build_dialog(self, dialog_id: Any, dialog: Any) -> str:
        """Собирает Lua-функторы всех фраз одного диалога.

        Args:
            dialog_id (Any):
                Ключ карты диалогов; должен совпадать с ``Dialog.id``.
            dialog (Any):
                Модель диалога с картой ``phrases``.

        Returns:
            str: Блок функций диалога или пустая строка, если ни одна фраза не
            содержит условий и действий.

        Raises:
            ValueError:
                Если идентификатор диалога некорректен или не совпадает с
                ``Dialog.id``.
            TypeError:
                Если карта фраз повреждена.
            Exception:
                Любая ошибка сборки журналируется и пробрасывается, чтобы
                ``generate_quests_script`` мог пропустить диалог.
        """
        try:
            self._validate_dialog(dialog_id, dialog)
            phrases = getattr(dialog, "phrases", None)
            self._require_mapping(phrases, f"phrases диалога '{dialog_id}'")

            blocks: list[str] = []
            for phrase_id in sorted(phrases):
                block = self._build_phrase_functions(
                    dialog_id,
                    phrase_id,
                    phrases[phrase_id],
                )
                if block:
                    blocks.append(block)

            content = "\n\n".join(blocks)
            logger.debug(
                "Диалог '%s' собран: фраз с логикой — %d.",
                dialog_id,
                len(blocks),
            )
            return content
        except Exception as exc:
            logger.error(
                "Не удалось собрать Lua-диалог '%s': %s",
                dialog_id,
                exc,
                exc_info=True,
            )
            raise

    def _build_phrase_functions(
        self,
        dialog_id: str,
        phrase_id: Any,
        phrase: Any,
    ) -> str:
        """Собирает precondition и action одной фразы диалога.

        Функции создаются только для «фраз с логикой» — тех, у которых есть
        хотя бы одно предусловие или хотя бы одно действие.

        Args:
            dialog_id (str):
                Идентификатор родительского диалога.
            phrase_id (Any):
                Ключ карты фраз; должен совпадать с ``Phrase.id``.
            phrase (Any):
                Модель реплики с полями ``preconditions`` и ``actions``.

        Returns:
            str: Две Lua-функции или пустая строка для фразы без логики.

        Raises:
            ValueError:
                Если номер фразы некорректен или не совпадает с ``Phrase.id``.
            TypeError:
                Если списки условий или действий повреждены.
            Exception:
                Ошибка формирования блока журналируется и пробрасывается.
        """
        try:
            self._validate_phrase_identity(dialog_id, phrase_id, phrase)

            preconditions = getattr(phrase, "preconditions", None)
            actions = getattr(phrase, "actions", None)
            self._require_list(
                preconditions,
                f"preconditions фразы {phrase_id} диалога '{dialog_id}'",
            )
            self._require_list(
                actions,
                f"actions фразы {phrase_id} диалога '{dialog_id}'",
            )

            if not preconditions and not actions:
                logger.debug(
                    "Фраза %s диалога '%s' не содержит логики.",
                    phrase_id,
                    dialog_id,
                )
                return ""

            prefix = f"{dialog_id}_phrase_{phrase_id}"

            if preconditions:
                condition_expression = self._conditions_to_lua(
                    preconditions,
                    owner=(
                        f"диалог '{dialog_id}', фраза {phrase_id}, "
                        "preconditions"
                    ),
                    actor_expr="second_speaker",
                )
            else:
                condition_expression = "true"

            precondition_lines = [
                (
                    f"function {SCRIPT_TABLE}.{prefix}_precondition("
                    "first_speaker, second_speaker, dialog_id, phrase_id)"
                ),
                f"    return {condition_expression}",
                "end",
            ]

            action_lines = self._build_action_lines(
                actions,
                f"диалог '{dialog_id}', фраза {phrase_id}, actions",
                actor_expr="second_speaker",
            )
            action_function = [
                (
                    f"function {SCRIPT_TABLE}.{prefix}_action("
                    "first_speaker, second_speaker, dialog_id, phrase_id)"
                ),
            ]
            action_function.extend(
                action_lines or ["    -- Действий у фразы нет."]
            )
            action_function.append("end")

            logger.debug(
                "Логика фразы %s диалога '%s' сформирована: условий — %d, "
                "действий — %d.",
                phrase_id,
                dialog_id,
                len(preconditions),
                len(actions),
            )
            return "\n".join(precondition_lines + [""] + action_function)
        except Exception as exc:
            logger.error(
                "Ошибка формирования логики фразы %s диалога '%s': %s",
                phrase_id,
                dialog_id,
                exc,
            )
            raise

    # ------------------------------------------------------------------
    # Трансляция действий и условий
    # ------------------------------------------------------------------

    def _build_action_lines(
        self,
        actions: Iterable[Any],
        owner: str,
        *,
        actor_expr: str,
        indent: str = "    ",
    ) -> list[str]:
        """Переводит список Pydantic-действий в строки Lua.

        Повреждённое действие не прерывает сборку всей сущности: оно
        журналируется и заменяется Lua-комментарием.

        Args:
            actions (Iterable[Any]):
                Действия квеста, этапа или реплики.
            owner (str):
                Контекст для сообщений лога.
            actor_expr (str):
                Lua-выражение получателя предмета (``db.actor`` или
                ``second_speaker``).
            indent (str):
                Отступ для каждой строки действия.

        Returns:
            list[str]: Строки Lua-кода с указанным отступом.

        Raises:
            TypeError:
                Если ``actions`` не является итерируемой коллекцией.
            Exception:
                Непредвиденная ошибка журналируется и пробрасывается.
        """
        try:
            if isinstance(actions, (str, bytes)) or not isinstance(
                actions,
                Iterable,
            ):
                raise TypeError(
                    f"Список действий ({owner}) должен быть итерируемым, "
                    f"а получен {type(actions).__name__}."
                )

            lines: list[str] = []
            for index, action in enumerate(actions):
                try:
                    lua_code = self._action_to_lua(
                        action,
                        actor_expr=actor_expr,
                    )
                except Exception as exc:
                    logger.error(
                        "Действие #%d (%s) пропущено: %s",
                        index,
                        owner,
                        exc,
                        exc_info=True,
                    )
                    lines.append(
                        f"{indent}-- Пропущено действие #{index}: "
                        f"{self._sanitize_comment(str(exc))}"
                    )
                    continue

                lines.append(f"{indent}{lua_code}")

            logger.debug(
                "Действия (%s) переведены в Lua: строк — %d.",
                owner,
                len(lines),
            )
            return lines
        except Exception as exc:
            logger.error(
                "Не удалось перевести действия (%s) в Lua: %s",
                owner,
                exc,
            )
            raise

    def _action_to_lua(self, action: Any, *, actor_expr: str) -> str:
        """Переводит одно Pydantic-действие в вызов Lua-API Anomaly.

        Поддерживаемые действия:

        * ``GiveInfo`` — ``db.actor:give_info_portion``;
        * ``RemoveInfo`` — ``db.actor:disable_info_portion``;
        * ``SpawnSquad`` — ``mymod_quests.spawn_task_squad``;
        * ``SetTarget`` — ``mymod_quests.set_task_target``;
        * ``GiveItem`` — ``dialogs.relocate_item_section(..., "in")``;
        * ``RemoveItem`` — ``dialogs.relocate_item_section(..., "out")``;
        * ``GiveMoney`` — ``db.actor:give_money``.

        Args:
            action (Any):
                Конкретный наследник ``BaseAction``.
            actor_expr (str):
                Lua-выражение игрока — получателя предмета.

        Returns:
            str: Одна строка Lua-кода без отступа.

        Raises:
            TypeError:
                Если действие имеет неподдерживаемый тип или повреждённые
                обязательные поля.
        """
        try:
            if isinstance(action, GiveInfo):
                return (
                    "db.actor:give_info_portion("
                    f"{self._lua_string(action.info)})"
                )

            if isinstance(action, RemoveInfo):
                return (
                    "db.actor:disable_info_portion("
                    f"{self._lua_string(action.info)})"
                )

            if isinstance(action, SpawnSquad):
                return (
                    f"{SCRIPT_TABLE}.spawn_task_squad("
                    f"{self._lua_string(action.squad_alias)}, "
                    f"{self._lua_string(action.smart_alias)})"
                )

            if isinstance(action, SetTarget):
                return (
                    f"{SCRIPT_TABLE}.set_task_target("
                    f"{self._lua_string(action.squad_alias)}, "
                    f"{self._lua_string(action.smart_alias)})"
                )

            if isinstance(action, GiveItem):
                return (
                    "dialogs.relocate_item_section("
                    f"{actor_expr}, {self._lua_string(action.item_alias)}, "
                    '"in")'
                )

            if isinstance(action, RemoveItem):
                return (
                    "dialogs.relocate_item_section("
                    f"{actor_expr}, {self._lua_string(action.item_alias)}, "
                    '"out")'
                )

            if isinstance(action, GiveMoney):
                amount = action.amount
                if not isinstance(amount, int) or isinstance(amount, bool):
                    raise TypeError(
                        "Сумма GiveMoney должна быть целым числом, а "
                        f"получена {type(amount).__name__}."
                    )
                return f"db.actor:give_money({amount})"

            raise TypeError(
                "Неподдерживаемый тип действия: "
                f"{type(action).__name__}."
            )
        except Exception as exc:
            logger.error("Ошибка трансляции действия в Lua: %s", exc)
            raise

    def _conditions_to_lua(
        self,
        conditions: Iterable[Any],
        *,
        owner: str,
        actor_expr: str = "db.actor",
    ) -> str:
        """Переводит список Pydantic-условий в Lua-выражение.

        Условия объединяются логическим ``and``. Пустой список даёт ``true``.

        Args:
            conditions (Iterable[Any]):
                Условия доступности или перехода.
            owner (str):
                Контекст для сообщений лога.
            actor_expr (str):
                Lua-выражение игрока для проверки предметов.

        Returns:
            str: Lua-выражение, пригодное для ``if`` и ``return``.

        Raises:
            TypeError:
                Если список условий не является итерируемой коллекцией.
            ValueError:
                Если хотя бы одно условие не удалось перевести в Lua.
        """
        try:
            if isinstance(conditions, (str, bytes)) or not isinstance(
                conditions,
                Iterable,
            ):
                raise TypeError(
                    f"Список условий ({owner}) должен быть итерируемым, "
                    f"а получен {type(conditions).__name__}."
                )

            expressions: list[str] = []
            failures = 0
            for index, condition in enumerate(conditions):
                try:
                    expressions.append(
                        self._condition_to_lua(
                            condition,
                            actor_expr=actor_expr,
                        )
                    )
                except Exception as exc:
                    failures += 1
                    logger.error(
                        "Условие #%d (%s) не удалось перевести: %s",
                        index,
                        owner,
                        exc,
                        exc_info=True,
                    )

            if failures:
                raise ValueError(
                    f"Не удалось перевести условий ({owner}): {failures}."
                )

            if not expressions:
                return "true"

            if len(expressions) == 1:
                return expressions[0]

            logger.debug(
                "Условия (%s) объединены: выражений — %d.",
                owner,
                len(expressions),
            )
            return " and ".join(f"({expression})" for expression in expressions)
        except Exception as exc:
            logger.error(
                "Не удалось перевести условия (%s) в Lua: %s",
                owner,
                exc,
            )
            raise

    def _condition_to_lua(self, condition: Any, *, actor_expr: str) -> str:
        """Переводит одно Pydantic-условие в Lua-выражение.

        Args:
            condition (Any):
                Конкретный наследник ``BaseCondition``.
            actor_expr (str):
                Lua-выражение игрока для проверки инвентаря.

        Returns:
            str: Lua-выражение без завершающей точки с запятой.

        Raises:
            TypeError:
                Если тип условия не поддерживается или его поля повреждены.
        """
        try:
            if isinstance(condition, HasInfo):
                return (
                    "has_alife_info("
                    f"{self._lua_string(condition.info)})"
                )

            if isinstance(condition, DontHasInfo):
                return (
                    "not has_alife_info("
                    f"{self._lua_string(condition.info)})"
                )

            if isinstance(condition, HasItem):
                return (
                    f"{actor_expr}:object("
                    f"{self._lua_string(condition.item_alias)}) ~= nil"
                )

            if isinstance(condition, SmartOwner):
                return (
                    f"{SCRIPT_TABLE}.is_smart_captured("
                    f"{self._lua_string(condition.smart_alias)}, "
                    f"{self._lua_string(condition.faction)})"
                )

            raise TypeError(
                "Неподдерживаемый тип условия: "
                f"{type(condition).__name__}."
            )
        except Exception as exc:
            logger.error("Ошибка трансляции условия в Lua: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Правила transfer_conditions
    # ------------------------------------------------------------------

    def _extract_transfer_rules(
        self,
        quest_id: str,
        quest: Any,
        stage_ids: Sequence[int],
    ) -> tuple[dict[str, list[Any]], dict[int, dict[str, list[Any]]]]:
        """Извлекает правила завершения и провала из модели квеста.

        Правила могут храниться в поле ``transfer_conditions`` самого квеста
        или отдельного этапа. Метод приводит обе формы к единому виду:
        общие правила квеста и правила для каждого этапа.

        Args:
            quest_id (str):
                Идентификатор квеста для логов и сообщений об ошибках.
            quest (Any):
                Модель квеста.
            stage_ids (Sequence[int]):
                Отсортированные идентификаторы этапов.

        Returns:
            tuple[dict[str, list[Any]], dict[int, dict[str, list[Any]]]]:
                Пара ``(quest_rules, stage_rules)``. Каждый словарь содержит
                ключи ``"complete"`` и ``"fail"`` со списками условий.

        Raises:
            TypeError:
                Если ``transfer_conditions`` имеет неподдерживаемую структуру
                или ссылается на несуществующий этап.
        """
        try:
            quest_rules: dict[str, list[Any]] = {
                result: [] for result in _TRANSFER_RESULTS
            }
            stage_rules: dict[int, dict[str, list[Any]]] = {
                stage_id: {result: [] for result in _TRANSFER_RESULTS}
                for stage_id in stage_ids
            }

            raw_quest_rules = getattr(quest, "transfer_conditions", None)
            if raw_quest_rules is not None:
                self._merge_transfer_rules(
                    raw_quest_rules,
                    quest_id=quest_id,
                    owner="квест",
                    quest_rules=quest_rules,
                    stage_rules=stage_rules,
                    stage_ids=stage_ids,
                )

            for stage_id in stage_ids:
                stage = quest.stages[stage_id]
                raw_stage_rules = getattr(
                    stage,
                    "transfer_conditions",
                    None,
                )
                if raw_stage_rules is not None:
                    self._merge_transfer_rules(
                        raw_stage_rules,
                        quest_id=quest_id,
                        owner=f"этап {stage_id}",
                        quest_rules=quest_rules,
                        stage_rules=stage_rules,
                        stage_ids=stage_ids,
                        forced_stage_id=stage_id,
                    )

            logger.debug(
                "Правила transfer_conditions квеста '%s' разобраны: "
                "общих условий — %d, этапов с правилами — %d.",
                quest_id,
                len(quest_rules["complete"]) + len(quest_rules["fail"]),
                sum(
                    1
                    for rules in stage_rules.values()
                    if rules["complete"] or rules["fail"]
                ),
            )
            return quest_rules, stage_rules
        except Exception as exc:
            logger.error(
                "Не удалось разобрать transfer_conditions квеста '%s': %s",
                quest_id,
                exc,
            )
            raise

    def _merge_transfer_rules(
        self,
        raw_rules: Any,
        *,
        quest_id: str,
        owner: str,
        quest_rules: dict[str, list[Any]],
        stage_rules: dict[int, dict[str, list[Any]]],
        stage_ids: Sequence[int],
        forced_stage_id: int | None = None,
    ) -> None:
        """Добавляет одну порцию правил в нормализованные структуры.

        Args:
            raw_rules (Any):
                Значение ``transfer_conditions`` квеста или этапа.
            quest_id (str):
                Идентификатор квеста для сообщений об ошибках.
            owner (str):
                Человекочитаемый владелец правил (``"квест"`` или
                ``"этап 1"``).
            quest_rules (dict[str, list[Any]]):
                Накопитель общих правил квеста.
            stage_rules (dict[int, dict[str, list[Any]]]):
                Накопитель правил по этапам.
            stage_ids (Sequence[int]):
                Допустимые идентификаторы этапов.
            forced_stage_id (int | None):
                Если задан, все правила относятся к этому этапу.

        Returns:
            None: Функция изменяет переданные словари на месте.

        Raises:
            TypeError:
                Если структура правил не поддерживается.
            ValueError:
                Если правило ссылается на несуществующий этап.
        """
        try:
            if forced_stage_id is not None:
                target = stage_rules[forced_stage_id]
                self._store_stage_rule_value(
                    raw_rules,
                    target,
                    quest_id=quest_id,
                    owner=f"{owner} (этап {forced_stage_id})",
                )
                return

            if isinstance(raw_rules, Mapping):
                keys = {str(key) for key in raw_rules}
                if keys & set(_TRANSFER_RESULTS):
                    for result in _TRANSFER_RESULTS:
                        quest_rules[result].extend(
                            self._as_condition_list(
                                raw_rules.get(result),
                                quest_id=quest_id,
                                owner=f"{owner}, {result}",
                            )
                        )
                    return

                for raw_stage_id, value in raw_rules.items():
                    stage_id = self._coerce_stage_id(
                        raw_stage_id,
                        quest_id=quest_id,
                        owner=owner,
                    )
                    if stage_id not in stage_rules:
                        raise ValueError(
                            f"Правило {owner} ссылается на несуществующий "
                            f"этап {stage_id} квеста '{quest_id}'."
                        )
                    self._store_stage_rule_value(
                        value,
                        stage_rules[stage_id],
                        quest_id=quest_id,
                        owner=f"{owner}, этап {stage_id}",
                    )
                return

            if isinstance(raw_rules, (list, tuple)):
                last_stage_id = stage_ids[-1]
                stage_rules[last_stage_id]["complete"].extend(
                    self._as_condition_list(
                        raw_rules,
                        quest_id=quest_id,
                        owner=f"{owner}, последний этап",
                    )
                )
                return

            raise TypeError(
                f"Правила {owner} квеста '{quest_id}' должны быть словарём "
                "или списком условий, а получены "
                f"{type(raw_rules).__name__}."
            )
        except Exception as exc:
            logger.error(
                "Ошибка правил %s квеста '%s': %s",
                owner,
                quest_id,
                exc,
            )
            raise

    def _store_stage_rule_value(
        self,
        value: Any,
        target: dict[str, list[Any]],
        *,
        quest_id: str,
        owner: str,
    ) -> None:
        """Сохраняет правила одного этапа в накопителе.

        Args:
            value (Any):
                Список условий завершения либо словарь с ключами
                ``"complete"``/``"fail"``.
            target (dict[str, list[Any]]):
                Накопитель правил конкретного этапа.
            quest_id (str):
                Идентификатор квеста для сообщений об ошибках.
            owner (str):
                Контекст правила для логов.

        Returns:
            None: Функция изменяет ``target`` на месте.

        Raises:
            TypeError:
                Если значение правила имеет неподдерживаемый тип.
        """
        try:
            if isinstance(value, Mapping):
                for result in _TRANSFER_RESULTS:
                    target[result].extend(
                        self._as_condition_list(
                            value.get(result),
                            quest_id=quest_id,
                            owner=f"{owner}, {result}",
                        )
                    )
                return

            target["complete"].extend(
                self._as_condition_list(
                    value,
                    quest_id=quest_id,
                    owner=f"{owner}, complete",
                )
            )
        except Exception as exc:
            logger.error(
                "Ошибка правила %s квеста '%s': %s",
                owner,
                quest_id,
                exc,
            )
            raise

    def _as_condition_list(
        self,
        value: Any,
        *,
        quest_id: str,
        owner: str,
    ) -> list[Any]:
        """Приводит значение правила к списку Pydantic-условий.

        Args:
            value (Any):
                ``None``, одно условие или последовательность условий.
            quest_id (str):
                Идентификатор квеста для сообщений об ошибках.
            owner (str):
                Контекст правила для логов.

        Returns:
            list[Any]: Список условий; для ``None`` возвращается пустой список.

        Raises:
            TypeError:
                Если значение не является условием или их последовательностью.
        """
        try:
            if value is None:
                return []

            if isinstance(value, (HasInfo, DontHasInfo, HasItem, SmartOwner)):
                return [value]

            if isinstance(value, (str, bytes, Mapping)):
                raise TypeError(
                    f"Условия {owner} квеста '{quest_id}' должны быть "
                    "Pydantic-объектами, а получены "
                    f"{type(value).__name__}."
                )

            if isinstance(value, Sequence):
                result = list(value)
                for index, condition in enumerate(result):
                    if not isinstance(
                        condition,
                        (HasInfo, DontHasInfo, HasItem, SmartOwner),
                    ):
                        raise TypeError(
                            f"Условие #{index} ({owner}) квеста "
                            f"'{quest_id}' имеет неподдерживаемый тип "
                            f"{type(condition).__name__}."
                        )
                return result

            raise TypeError(
                f"Условия {owner} квеста '{quest_id}' имеют "
                f"неподдерживаемый тип {type(value).__name__}."
            )
        except Exception as exc:
            logger.error(
                "Ошибка списка условий %s квеста '%s': %s",
                owner,
                quest_id,
                exc,
            )
            raise

    def _coerce_stage_id(
        self,
        value: Any,
        *,
        quest_id: str,
        owner: str,
    ) -> int:
        """Приводит ключ правила к целочисленному номеру этапа.

        Args:
            value (Any):
                Ключ словаря ``transfer_conditions``.
            quest_id (str):
                Идентификатор квеста для сообщений об ошибках.
            owner (str):
                Контекст правила для логов.

        Returns:
            int: Неотрицательный номер этапа.

        Raises:
            TypeError:
                Если ключ не является целым числом или числовой строкой.
            ValueError:
                Если номер этапа отрицательный.
        """
        try:
            if isinstance(value, bool):
                raise TypeError(
                    f"Ключ этапа ({owner}) квеста '{quest_id}' не может быть "
                    "булевым значением."
                )

            if isinstance(value, int):
                stage_id = value
            elif isinstance(value, str) and value.strip().isdigit():
                stage_id = int(value.strip())
            else:
                raise TypeError(
                    f"Ключ этапа ({owner}) квеста '{quest_id}' должен быть "
                    f"целым числом, а получен {type(value).__name__}."
                )

            if stage_id < 0:
                raise ValueError(
                    f"Номер этапа ({owner}) квеста '{quest_id}' не может "
                    f"быть отрицательным: {stage_id}."
                )

            return stage_id
        except Exception as exc:
            logger.error(
                "Ошибка ключа этапа %r (%s) квеста '%s': %s",
                value,
                owner,
                quest_id,
                exc,
            )
            raise

    # ------------------------------------------------------------------
    # Валидация и вспомогательные функции
    # ------------------------------------------------------------------

    def _validate_quest(self, quest_id: Any, quest: Any) -> None:
        """Проверяет минимальную структуру квеста перед генерацией.

        Args:
            quest_id (Any):
                Ключ карты квестов.
            quest (Any):
                Проверяемая модель квеста.

        Returns:
            None: Функция ничего не возвращает.

        Raises:
            ValueError:
                Если идентификатор некорректен или не совпадает с
                ``Quest.id``.
            TypeError:
                Если отсутствуют обязательные поля или карта этапов имеет
                неверный тип.
        """
        try:
            self._validate_identifier(quest_id, "квеста")

            actual_id = getattr(quest, "id", None)
            if actual_id != quest_id:
                raise ValueError(
                    f"Ключ карты '{quest_id}' не совпадает с "
                    f"Quest.id='{actual_id}'."
                )

            stages = getattr(quest, "stages", None)
            self._require_mapping(stages, f"stages квеста '{quest_id}'")
            if not stages:
                raise ValueError(
                    f"Квест '{quest_id}' не содержит ни одного этапа."
                )

            for stage_id, stage in stages.items():
                if not isinstance(stage_id, int) or isinstance(stage_id, bool):
                    raise TypeError(
                        f"Ключ этапа квеста '{quest_id}' должен быть целым "
                        f"числом, а получен {type(stage_id).__name__}."
                    )

                actual_stage_id = getattr(stage, "id", None)
                if actual_stage_id != stage_id:
                    raise ValueError(
                        f"Ключ этапа {stage_id} квеста '{quest_id}' не "
                        f"совпадает с Stage.id='{actual_stage_id}'."
                    )

                target_alias = getattr(stage, "target_alias", None)
                if not isinstance(target_alias, str):
                    raise TypeError(
                        f"Этап {stage_id} квеста '{quest_id}' содержит "
                        "нестроковый target_alias."
                    )

            for field_name in (
                "on_init_actions",
                "on_complete_actions",
                "on_fail_actions",
            ):
                self._require_list(
                    getattr(quest, field_name, None),
                    f"{field_name} квеста '{quest_id}'",
                )

            self._require_text(
                getattr(quest, "title_ru", None),
                f"title_ru квеста '{quest_id}'",
            )

            logger.debug("Структура квеста '%s' корректна.", quest_id)
        except Exception as exc:
            logger.error(
                "Квест '%s' не прошёл проверку структуры: %s",
                quest_id,
                exc,
            )
            raise

    def _validate_dialog(self, dialog_id: Any, dialog: Any) -> None:
        """Проверяет минимальную структуру диалога перед генерацией.

        Args:
            dialog_id (Any):
                Ключ карты диалогов.
            dialog (Any):
                Проверяемая модель диалога.

        Returns:
            None: Функция ничего не возвращает.

        Raises:
            ValueError:
                Если идентификатор некорректен или не совпадает с
                ``Dialog.id``.
            TypeError:
                Если карта фраз отсутствует или имеет неверный тип.
        """
        try:
            self._validate_identifier(dialog_id, "диалога")

            actual_id = getattr(dialog, "id", None)
            if actual_id != dialog_id:
                raise ValueError(
                    f"Ключ карты '{dialog_id}' не совпадает с "
                    f"Dialog.id='{actual_id}'."
                )

            phrases = getattr(dialog, "phrases", None)
            self._require_mapping(phrases, f"phrases диалога '{dialog_id}'")
            if not phrases:
                raise TypeError(
                    f"Диалог '{dialog_id}' должен содержать непустую карту "
                    "phrases."
                )

            logger.debug("Структура диалога '%s' корректна.", dialog_id)
        except Exception as exc:
            logger.error(
                "Диалог '%s' не прошёл проверку структуры: %s",
                dialog_id,
                exc,
            )
            raise

    def _validate_phrase_identity(
        self,
        dialog_id: str,
        phrase_id: Any,
        phrase: Any,
    ) -> None:
        """Проверяет номер фразы и его совпадение с моделью.

        Args:
            dialog_id (str):
                Идентификатор родительского диалога.
            phrase_id (Any):
                Ключ карты фраз.
            phrase (Any):
                Проверяемая модель реплики.

        Returns:
            None: Функция ничего не возвращает.

        Raises:
            ValueError:
                Если номер фразы некорректен или не совпадает с ``Phrase.id``.
        """
        try:
            if not isinstance(phrase_id, int) or isinstance(phrase_id, bool):
                raise ValueError(
                    f"Номер фразы диалога '{dialog_id}' должен быть целым "
                    f"числом, а получен {type(phrase_id).__name__}."
                )

            if phrase_id < 0:
                raise ValueError(
                    f"Номер фразы диалога '{dialog_id}' не может быть "
                    f"отрицательным: {phrase_id}."
                )

            actual_id = getattr(phrase, "id", None)
            if actual_id != phrase_id:
                raise ValueError(
                    f"Ключ фразы {phrase_id} диалога '{dialog_id}' не "
                    f"совпадает с Phrase.id='{actual_id}'."
                )

            logger.debug(
                "Фраза %s диалога '%s' прошла проверку идентификатора.",
                phrase_id,
                dialog_id,
            )
        except Exception as exc:
            logger.error(
                "Ошибка идентификатора фразы %s диалога '%s': %s",
                phrase_id,
                dialog_id,
                exc,
            )
            raise

    def _validate_identifier(self, value: Any, entity: str) -> str:
        """Проверяет, что значение можно использовать в имени Lua-функции.

        Args:
            value (Any):
                Проверяемый идентификатор.
            entity (str):
                Название сущности для сообщения об ошибке.

        Returns:
            str: Исходный идентификатор после успешной проверки.

        Raises:
            ValueError:
                Если значение пустое, не является строкой или содержит
                недопустимые для Lua-идентификатора символы.
        """
        try:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Идентификатор {entity} должен быть непустой строкой, "
                    f"а получен {value!r}."
                )

            if not _IDENTIFIER_PATTERN.match(value):
                raise ValueError(
                    f"Идентификатор {entity} '{value}' должен содержать "
                    "только латиницу, цифры и символ подчёркивания и не "
                    "начинаться с цифры."
                )

            return value
        except Exception as exc:
            logger.error(
                "Некорректный идентификатор %s %r: %s",
                entity,
                value,
                exc,
            )
            raise

    def _require_mapping(self, value: Any, owner: str) -> Mapping[Any, Any]:
        """Проверяет, что значение является словарём.

        Args:
            value (Any):
                Проверяемое значение.
            owner (str):
                Название поля для сообщения об ошибке.

        Returns:
            Mapping[Any, Any]: Исходный словарь после проверки.

        Raises:
            TypeError:
                Если значение не является ``Mapping``.
        """
        try:
            if not isinstance(value, Mapping):
                raise TypeError(
                    f"Поле {owner} должно быть словарём, а получен "
                    f"{type(value).__name__}."
                )
            return value
        except Exception as exc:
            logger.error("Ошибка поля %s: %s", owner, exc)
            raise

    def _require_list(self, value: Any, owner: str) -> list[Any]:
        """Проверяет, что значение является списком.

        Args:
            value (Any):
                Проверяемое значение.
            owner (str):
                Название поля для сообщения об ошибке.

        Returns:
            list[Any]: Исходный список после проверки.

        Raises:
            TypeError:
                Если значение не является списком.
        """
        try:
            if not isinstance(value, list):
                raise TypeError(
                    f"Поле {owner} должно быть списком, а получен "
                    f"{type(value).__name__}."
                )
            return value
        except Exception as exc:
            logger.error("Ошибка поля %s: %s", owner, exc)
            raise

    def _require_text(self, value: Any, owner: str) -> str:
        """Проверяет, что значение является строкой.

        Args:
            value (Any):
                Проверяемое значение.
            owner (str):
                Название поля для сообщения об ошибке.

        Returns:
            str: Исходная строка после проверки.

        Raises:
            TypeError:
                Если значение не является строкой.
        """
        try:
            if not isinstance(value, str):
                raise TypeError(
                    f"Поле {owner} должно быть строкой, а получен "
                    f"{type(value).__name__}."
                )
            return value
        except Exception as exc:
            logger.error("Ошибка поля %s: %s", owner, exc)
            raise

    def _lua_string(self, value: Any) -> str:
        """Экранирует Python-строку для использования в Lua-литерале.

        Args:
            value (Any):
                Значение, которое нужно превратить в строковый литерал.

        Returns:
            str: Lua-литерал в двойных кавычках с экранированными символами.

        Raises:
            TypeError:
                Если значение не является строкой.
        """
        try:
            self._require_text(value, "Lua-строки")
            escaped = (
                value.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\r", "\\r")
                .replace("\n", "\\n")
                .replace("\t", "\\t")
            )
            return f'"{escaped}"'
        except Exception as exc:
            logger.error("Не удалось сформировать Lua-строку: %s", exc)
            raise

    def _sanitize_comment(self, text: str) -> str:
        """Очищает текст для безопасного Lua-комментария.

        Args:
            text (str):
                Произвольный текст исключения или пояснения.

        Returns:
            str: Однострочный текст без переводов строк и ``--``.

        Raises:
            TypeError:
                Если ``text`` не является строкой.
        """
        try:
            self._require_text(text, "текста комментария")
            sanitized = " ".join(text.split())
            return sanitized.replace("--", "- -")
        except Exception as exc:
            logger.error("Не удалось подготовить Lua-комментарий: %s", exc)
            raise


__all__ = ["LuaGenerator"]
