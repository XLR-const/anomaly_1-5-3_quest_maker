"""Тесты Lua-генератора ``<mod>_quests.script``.

Проверяются требования ``standart_of_auto.md`` (2.3):

* статическая таблица ``local QUESTS`` вместо динамической инъекции;
* плоские ключи регистрации в ``task_functor``,
  ``task_status_functor``, ``xr_effects`` и ``dialogs``;
* канонические сигнатуры ``function(actor, npc, p)``;
* отсутствие DLTX, ``.ext`` и ``start_dialogs``.

Запуск::

    .\\venv\\Scripts\\python.exe -m unittest tests.test_compiler_lua -v
"""

from __future__ import annotations

import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compiler.lua_gen import LuaGenerator  # noqa: E402
from src.compiler.xml_gen import XmlGenerator  # noqa: E402
from src.core.models import (  # noqa: E402
    CompleteTask,
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveItem,
    GiveMoney,
    GiveTask,
    HasInfo,
    HasItem,
    HasMoney,
    ModProject,
    Phrase,
    Quest,
    SpawnSquad,
    Stage,
    TakeItem,
    TakeMoney,
    WarfareCapture,
)

QUEST_ID = "mymod_test_quest"
DIALOG_ID = "mymod_test_dialog"
SCRIPT_NAME = "mymod_quests"
MOD_PREFIX = "mymod"


def _make_project() -> ModProject:
    """Создаёт проект с одним квестом и одним диалогом.

    Returns:
        ModProject: Модель с наградой, этапами и динамическими условиями.
    """
    quest = Quest(
        id=QUEST_ID,
        npc_id="esc_mayor",
        npc_location="escape",
        dialog_id=DIALOG_ID,
        title_ru="Тестовый квест",
        title_en="Test quest",
        descr_ru="Описание",
        descr_en="Description",
        taken_info="mymod_taken",
        complete_info="mymod_done",
        reward_money=5000,
        reward_item_alias="medkit",
        reward_item_count=2,
        return_to_giver_stage=1,
        return_distance=25.0,
        stages={
            0: Stage(
                id=0,
                title_ru="Захват",
                title_en="Capture",
                target_alias="esc_smart",
                on_start_actions=[GiveInfo(info="mymod_stage_0")],
                warfare_capture=WarfareCapture(
                    smart_alias="esc_smart",
                    enemy_squad_alias="esc_enemy",
                    ally_squad_alias="army_ally",
                    ally_count=2,
                ),
            ),
            1: Stage(
                id=1,
                title_ru="Возврат",
                title_en="Return",
                target_alias="esc_mayor",
            ),
        },
        transfer_conditions={
            0: {"complete": [HasInfo(info="mymod_stage_0")]}
        },
        on_init_actions=[GiveInfo(info="mymod_started")],
        on_complete_actions=[
            GiveItem(item_alias="mymod_reward", count=1)
        ],
        on_fail_actions=[GiveInfo(info="mymod_failed")],
    )
    dialog = Dialog(
        id=DIALOG_ID,
        npc_id="esc_mayor",
        npc_location="escape",
        task_id=QUEST_ID,
        role="take",
        preconditions=[HasItem(item_alias="mymod_item")],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Привет",
                text_en="Hi",
                next_phrases=[1],
                actions=[GiveTask(task_id=QUEST_ID)],
            ),
            1: Phrase(
                id=1,
                text_ru="Возьму",
                text_en="Take",
                preconditions=[HasItem(item_alias="mymod_item")],
                actions=[
                    GiveItem(item_alias="mymod_consumable", count=1),
                    CompleteTask(task_id=QUEST_ID),
                ],
            ),
        },
    )
    return ModProject(
        name="Lua Test",
        quests={QUEST_ID: quest},
        dialogs={DIALOG_ID: dialog},
    )


class TestLuaGeneratorStructure(unittest.TestCase):
    """Проверка структуры и сигнатур сгенерированного скрипта."""

    def setUp(self) -> None:
        """Генерирует скрипт с явными именем модуля и префиксом."""
        self.project = _make_project()
        self.generator = LuaGenerator()
        self.script = self.generator.generate_quests_script(
            self.project,
            script_name=SCRIPT_NAME,
            mod_prefix=MOD_PREFIX,
        )

    def test_header_uses_script_name_once(self) -> None:
        """Имя модуля не дублирует суффикс ``_quests``."""
        self.assertIn(f"{SCRIPT_NAME}.script", self.script)
        self.assertNotIn(f"{SCRIPT_NAME}_quests.script", self.script)
        self.assertIn(
            f"-- End of auto-generated {SCRIPT_NAME}.script",
            self.script,
        )

    def test_static_quests_table_contains_metadata(self) -> None:
        """``local QUESTS`` содержит NPC, диалог, награду и этапы."""
        self.assertIn("local QUESTS = {", self.script)
        self.assertIn(f'key_prefix = "{MOD_PREFIX}_{QUEST_ID}"', self.script)
        self.assertIn('npc = "esc_mayor"', self.script)
        self.assertIn('npc_location = "escape"', self.script)
        self.assertIn(f'dialog = "{DIALOG_ID}"', self.script)
        self.assertIn("money = 5000", self.script)
        self.assertIn('item = "medkit"', self.script)
        self.assertIn("item_count = 2", self.script)
        self.assertIn("return_stage = 1", self.script)
        self.assertIn("return_distance = 25.0", self.script)
        self.assertIn("ally_count = 2", self.script)
        self.assertIn('kind = "has_info"', self.script)
        self.assertIn('info = "mymod_stage_0"', self.script)

    def test_flat_functor_registrations(self) -> None:
        """Функторы регистрируются плоскими ключами в четырёх таблицах."""
        expected = (
            f'task_functor["{QUEST_ID}_target"] = {QUEST_ID}_target',
            f'task_functor["{QUEST_ID}_descr"] = {QUEST_ID}_descr',
            f'task_status_functor["{QUEST_ID}_status"] = '
            f"{QUEST_ID}_status",
            f'xr_effects["{QUEST_ID}_start"] = {QUEST_ID}_start',
            f'xr_effects["{QUEST_ID}_reward"] = {QUEST_ID}_reward',
            f'xr_effects["{QUEST_ID}_cleanup"] = {QUEST_ID}_cleanup',
            f'dialogs["{QUEST_ID}_accept"] = {QUEST_ID}_accept',
            f'dialogs["{QUEST_ID}_turn_in"] = {QUEST_ID}_turn_in',
            f'dialogs["{DIALOG_ID}_can_take"] = {DIALOG_ID}_can_take',
            f'dialogs["{DIALOG_ID}_can_turn_in"] = '
            f"{DIALOG_ID}_can_turn_in",
            f'dialogs["{DIALOG_ID}_phrase_1_precondition"] = '
            f"{DIALOG_ID}_phrase_1_precondition",
            f'dialogs["{DIALOG_ID}_phrase_1_action"] = '
            f"{DIALOG_ID}_phrase_1_action",
        )
        for line in expected:
            with self.subTest(line=line):
                self.assertIn(line, self.script)

    def test_engine_functor_signatures(self) -> None:
        """Функторы задач имеют фиксированные сигнатуры движка."""
        self.assertRegex(
            self.script,
            rf"local function {QUEST_ID}_target"
            r"\s*\(\s*task_id\s*,\s*field\s*,\s*p\s*,\s*tsk\s*\)",
        )
        self.assertRegex(
            self.script,
            rf"local function {QUEST_ID}_descr"
            r"\s*\(\s*task_id\s*,\s*field\s*,\s*p\s*,\s*tsk\s*\)",
        )
        self.assertRegex(
            self.script,
            rf"local function {QUEST_ID}_status"
            r"\s*\(\s*tsk\s*,\s*task_id\s*\)",
        )

    def test_effects_use_canonical_actor_npc_p_signature(self) -> None:
        """Все эффекты и диалоговые функции — ``(actor, npc, p)``."""
        names = [
            f"{QUEST_ID}_start",
            f"{QUEST_ID}_reward",
            f"{QUEST_ID}_cleanup",
            f"{QUEST_ID}_accept",
            f"{QUEST_ID}_turn_in",
            f"{DIALOG_ID}_can_take",
            f"{DIALOG_ID}_can_turn_in",
            f"{DIALOG_ID}_accept",
            f"{DIALOG_ID}_turn_in",
            f"{DIALOG_ID}_phrase_1_precondition",
            f"{DIALOG_ID}_phrase_1_action",
        ]
        for name in names:
            with self.subTest(function=name):
                self.assertRegex(
                    self.script,
                    rf"local function {name}"
                    r"\s*\(\s*actor\s*,\s*npc\s*,\s*p\s*\)",
                )

    def test_register_runs_at_module_level(self) -> None:
        """``register()`` вызывается в конце модуля и на старте игры."""
        self.assertIn("local function register()", self.script)
        self.assertIn("function on_game_start()", self.script)
        self.assertIn("RegisterScriptCallback(\"on_game_load\"", self.script)
        self.assertIn(
            "RegisterScriptCallback(\"actor_on_first_update\"",
            self.script,
        )
        self.assertTrue(
            self.script.rstrip().endswith(
                f"-- End of auto-generated {SCRIPT_NAME}.script"
            )
        )
        self.assertRegex(self.script, r"(?m)^register\(\)$")

    def test_no_dynamic_dialog_injection_or_dltx(self) -> None:
        """Нет ``start_dialogs``, ``.ext`` и DLTX-механизмов."""
        lowered = self.script.lower()
        for forbidden in (
            "start_dialogs",
            "mymod_dialog_injections",
            "dltx",
            ".ext",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)

    def test_no_module_prefixed_function_names(self) -> None:
        """Имена функций плоские, без ``<mod>.`` и ``<mod>_quests.``."""
        self.assertNotIn(f"function {SCRIPT_NAME}.", self.script)
        self.assertNotIn("function mymod_quests.", self.script)
        self.assertNotIn(f"{MOD_PREFIX}.{QUEST_ID}", self.script)

    def test_phrase_action_merges_task_and_rewards_in_order(self) -> None:
        """Единая ``_action`` исполняет реплику в порядке объявления."""
        start = self.script.index(
            f"local function {DIALOG_ID}_phrase_1_action"
        )
        end = self.script.index("end", start)
        block = self.script[start:end]

        self.assertIn('kind = "give_item"', block)
        self.assertIn('kind = "complete_task"', block)
        self.assertLess(
            block.index('kind = "give_item"'),
            block.index('kind = "complete_task"'),
        )

    def test_xml_has_single_action_per_phrase(self) -> None:
        """Сгенерированный XML не содержит двух ``<action>`` в реплике."""
        xml = XmlGenerator().generate_dialogs_xml(self.project.dialogs)
        root = ET.fromstring(xml)
        for dialog in root.findall("dialog"):
            for phrase in dialog.findall("./phrase_list/phrase"):
                with self.subTest(
                    phrase=f"{dialog.get('id')}/{phrase.get('id')}"
                ):
                    self.assertLessEqual(len(phrase.findall("action")), 1)

    def test_resolve_target_uses_get_story_object_id(self) -> None:
        """Строковый story-id резолвится через ``get_story_object_id``."""
        self.assertIn("get_story_object_id(target)", self.script)
        self.assertIn("if get_story_object_id then", self.script)
        self.assertNotIn("alife():story_object", self.script)

    def test_give_task_never_writes_zero_giver_id(self) -> None:
        """``give_task`` не передаёт ``0``: в Lua он truthy и ломает маркер."""
        self.assertNotIn("giver_id = 0", self.script)
        self.assertIn(
            "if giver_id == 0 then giver_id = nil end", self.script
        )
        self.assertIn(
            "pcall(dialogs.who_is_npc, db.actor, npc)", self.script
        )
        self.assertIn("resolve_target(quest.npc)", self.script)

    def test_target_functor_ignores_zero_giver(self) -> None:
        """Этап возврата проверяет ``task_giver_id ~= 0`` перед возвратом."""
        start = self.script.index(f"local function {QUEST_ID}_target")
        end = self.script.index(f"local function {QUEST_ID}_descr")
        target_block = self.script[start:end]
        self.assertIn(
            "if tsk and tsk.task_giver_id and tsk.task_giver_id ~= 0 then",
            target_block,
        )
        self.assertIn("return resolve_target(quest.npc)", target_block)


class TestLuaGeneratorBehaviour(unittest.TestCase):
    """Проверка данных и отказоустойчивости Lua-генератора."""

    def test_default_names_are_safe(self) -> None:
        """Без явных имён используются значения по умолчанию."""
        script = LuaGenerator().generate_quests_script(_make_project())
        self.assertIn("quests.script", script)
        self.assertIn('key_prefix = "quests_mymod_test_quest"', script)

    def test_broken_quest_is_skipped_and_valid_one_remains(self) -> None:
        """Повреждённый квест не ломает генерацию остальных."""
        project = _make_project()
        project.quests["broken_quest"] = Quest.model_construct(
            id="broken_quest",
            stages={"bad": "not-a-stage"},
        )

        with self.assertLogs(
            "aqb.compiler.lua_gen", level="ERROR"
        ):
            script = LuaGenerator().generate_quests_script(project)

        self.assertIn(f"local function {QUEST_ID}_target", script)
        self.assertNotIn("broken_quest", script)

    def test_unknown_condition_is_isolated(self) -> None:
        """Неизвестный тип условия не ломает весь диалог."""
        project = _make_project()
        dialog = project.dialogs[DIALOG_ID]
        dialog.phrases[0].preconditions = [
            HasInfo(info="mymod_ok")
        ]

        script = LuaGenerator().generate_quests_script(project)
        self.assertIn(f"local function {DIALOG_ID}_can_take", script)

    def test_rejects_non_dict_project(self) -> None:
        """Проект без словарей quests/dialogs даёт ``TypeError``."""
        with self.assertRaises(TypeError):
            LuaGenerator().generate_quests_script(object())  # type: ignore[arg-type]


class TestTraderMechanicsAndSquadTracking(unittest.TestCase):
    """Новые действия/условия, алиасы БД и отслеживание целевого отряда."""

    @staticmethod
    def _make_trader_project() -> ModProject:
        """Создаёт квест с изъятием предмета/денег и целью-отрядом."""
        quest = Quest(
            id="trader_kill_quest",
            npc_id="esc_mayor",
            stages={
                0: Stage(
                    id=0,
                    target_squad_id="esc_3_16_military_trader_squad",
                    on_start_actions=[
                        TakeItem(item_alias="itm_pda_common", count=2),
                        TakeMoney(amount=1500),
                    ],
                ),
            },
            transfer_conditions={
                0: {
                    "complete": [
                        HasItem(item_alias="itm_pda_common", count=2),
                        HasMoney(amount=5000),
                    ]
                }
            },
        )
        dialog = Dialog(
            id="trader_kill_dialog",
            task_id=quest.id,
            phrases={
                0: Phrase(
                    id=0,
                    text_ru="Проверка",
                    text_en="Check",
                    preconditions=[
                        HasItem(item_alias="itm_pda_common", count=2),
                        HasMoney(amount=5000),
                    ],
                    actions=[
                        TakeItem(item_alias="itm_pda_common", count=2),
                        TakeMoney(amount=1500),
                        GiveItem(item_alias="itm_pda_common", count=1),
                        GiveMoney(amount=2500),
                    ],
                ),
            },
        )
        return ModProject(
            name="Trader Kill",
            quests={quest.id: quest},
            dialogs={dialog.id: dialog},
        )

    def test_new_action_and_condition_specs_are_emitted(self) -> None:
        """``take_item``/``take_money``/``has_money`` попадают в Lua-таблицы."""
        script = LuaGenerator().generate_quests_script(
            self._make_trader_project(),
            script_name="trader_quests",
            mod_prefix="trader",
        )

        for fragment in (
            'kind = "take_item"',
            'kind = "take_money"',
            'kind = "give_item"',
            'kind = "give_money"',
            'kind = "has_money"',
            'item = "itm_pda_common"',
            "count = 2",
            "amount = 1500",
            "amount = 2500",
            "amount = 5000",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, script)

    def test_helpers_are_generated(self) -> None:
        """Генератор создаёт безопасные хелперы подсчёта и списания."""
        script = LuaGenerator().generate_quests_script(
            self._make_trader_project()
        )

        for fragment in (
            "local function actor_item_count(section, actor)",
            "local function resolve_alife_object(target)",
            "local function target_squad_dead(q, stage)",
            "local function take_item(section, count, actor)",
            "local function take_money(amount, actor)",
            "local function give_item(section, count, actor)",
            "local function give_money(amount, actor)",
            'local function trader_kill_dialog_phrase_0_precondition',
            'local function trader_kill_dialog_phrase_0_action',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, script)

    def test_take_item_uses_inventory_and_single_notification(self) -> None:
        """Изъятие идёт через инвентарь и сообщает о потере один раз."""
        script = LuaGenerator().generate_quests_script(
            self._make_trader_project()
        )

        for fragment in (
            "obj:iterate_inventory",
            "alife_release(alife_object(item_id))",
            'news_manager.relocate_item(obj, "out", section, removed)',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, script)

        self.assertEqual(script.count("news_manager.relocate_item("), 2)
        self.assertIn(
            'news_manager.relocate_item(obj, "out", section, removed)',
            script,
        )
        self.assertIn(
            'news_manager.relocate_item(obj, "in", section, given)',
            script,
        )
        self.assertNotIn("dialogs.relocate_item_section", script)
        self.assertNotIn("itms_manager.relocate_item_from_actor", script)

    def test_give_money_and_item_use_standard_in_notifications(self) -> None:
        """Выдача денег/предмета показывает стандартные иконки и перевод."""
        script = LuaGenerator().generate_quests_script(
            self._make_trader_project()
        )

        for fragment in (
            "news_manager.relocate_money(obj, \"in\", amount)",
            "news_manager.relocate_item(obj, \"in\", section, given)",
            "give_money(spec.amount, actor or db.actor)",
            "give_item(spec.item, spec.count, actor or db.actor)",
            "give_money(quest.money, actor or db.actor)",
            "give_item(quest.item, quest.item_count, actor or db.actor)",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, script)

        # Сырые строковые ID не должны попадать в левый бар КПК.
        self.assertIn("game.translate_string", script)
        self.assertNotIn("pda_tip(spec.item", script)
        self.assertNotIn("pda_tip(section", script)
        self.assertNotIn("pda_tip(quest.item", script)

    def test_completed_quest_cannot_be_taken_again(self) -> None:
        """После выдачи complete_info стартовый диалог закрыт навсегда."""
        quest = Quest(
            id="once_quest",
            npc_id="esc_mayor",
            stages={0: Stage(id=0)},
            complete_info="once_done",
            taken_info="once_started",
        )
        dialog = Dialog(
            id="once_take",
            task_id=quest.id,
            role="take",
            preconditions=[DontHasInfo(info="once_started")],
            phrases={
                0: Phrase(
                    id=0,
                    text_ru="Есть работа?",
                    text_en="Got a job?",
                )
            },
        )
        project = ModProject(
            name="Once",
            quests={quest.id: quest},
            dialogs={dialog.id: dialog},
        )

        lua = LuaGenerator().generate_quests_script(
            project,
            script_name="once_quests",
            mod_prefix="once",
        )
        xml = XmlGenerator().generate_dialogs_xml(project.dialogs)

        # role="take" обязан ссылаться на _can_take даже при info-условиях.
        self.assertIn(
            "<precondition>dialogs.once_take_can_take</precondition>",
            xml,
        )

        can_take = lua[
            lua.index("local function once_take_can_take"):
            lua.index("local function once_take_can_turn_in")
        ]
        self.assertIn('local complete_info = "once_done"', can_take)
        self.assertIn("has_alife_info(complete_info)", can_take)
        self.assertIn('local done_info = ""', can_take)

        reward = lua[
            lua.index("local function once_quest_reward"):
            lua.index("local function once_quest_cleanup")
        ]
        self.assertIn('complete_info = "once_done"', lua)
        self.assertIn("db.actor:give_info_portion(quest.complete_info)", reward)
        self.assertNotIn(
            "disable_info_portion(quest.taken_info)", reward
        )
        self.assertNotIn(
            "disable_info_portion(quest.complete_info)", reward
        )

        cleanup = lua[
            lua.index("local function once_quest_cleanup"):
            lua.index("local function once_quest_accept")
        ]
        self.assertIn('taken_info = "once_started"', lua)
        self.assertIn("db.actor:disable_info_portion(quest.taken_info)", cleanup)

    def test_resolve_alife_object_searches_squad_section(self) -> None:
        """Секция сквада находится через SIMBOARD и перебор ``alife()``."""
        script = LuaGenerator().generate_quests_script(
            self._make_trader_project()
        )

        for fragment in (
            "if get_story_squad then",
            "return get_story_squad(target)",
            "if get_story_object then",
            "if SIMBOARD and SIMBOARD.squads then",
            "squad:section_name() == target",
            "game:iterate_objects",
            "se_obj:section_name() == target",
            "prefer_squad(se_obj, found)",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, script)

        target_start = script.index("local function trader_kill_quest_target")
        target_end = script.index("local function trader_kill_quest_descr")
        target_block = script[target_start:target_end]
        self.assertIn(
            "local target_obj = resolve_alife_object(target_name)",
            target_block,
        )
        self.assertIn("return target_obj.id", target_block)
        self.assertIn(
            "if squad.id and not alife_object(squad.id) then return true end",
            script,
        )
        self.assertIn("return squad_npc_count(squad) <= 0", script)

    def test_target_squad_is_tracked_in_status_functor(self) -> None:
        """``target_squad_id`` даёт автоматическую проверку в ``_status``."""
        script = LuaGenerator().generate_quests_script(
            self._make_trader_project()
        )

        self.assertIn(
            'target_squad = "esc_3_16_military_trader_squad"', script
        )
        self.assertIn("if target_squad_dead(quest, stage) then", script)
        self.assertIn('vset(seen_key, 1)', script)

    def test_database_aliases_are_resolved(self) -> None:
        """Алиасы БД заменяются секциями; прямые секции не меняются."""

        class FakeDatabase:
            """Минимальный двойник ``GameDatabase`` для разрешения алиасов."""

            def find_item_by_alias(self, alias: str):
                if alias == "weapon.pda":
                    return {"id": "itm_pda_common"}
                if alias == "weapon.kobra":
                    return {"id": "wpn_val_modern_kobra"}
                return None

            def find_squad_by_alias(self, alias: str):
                if alias == "squad.merc_target":
                    return {"id": "esc_3_16_military_trader_squad"}
                return None

        project = self._make_trader_project()
        project.quests["trader_kill_quest"].stages[0].target_squad_id = (
            "squad.merc_target"
        )
        project.quests["trader_kill_quest"].stages[0].on_start_actions[0] = (
            TakeItem(item_alias="weapon.pda", count=2)
        )
        project.quests["trader_kill_quest"].reward_item_alias = "weapon.kobra"
        project.dialogs["trader_kill_dialog"].phrases[0].actions[2] = (
            GiveItem(item_alias="weapon.pda", count=1)
        )

        script = LuaGenerator(db_client=FakeDatabase()).generate_quests_script(
            project
        )

        self.assertIn('item = "itm_pda_common"', script)
        self.assertIn('item = "wpn_val_modern_kobra"', script)
        self.assertNotIn('item = "weapon.pda"', script)
        self.assertNotIn('item = "weapon.kobra"', script)
        self.assertIn(
            'target_squad = "esc_3_16_military_trader_squad"', script
        )

    def test_database_failure_falls_back_to_raw_section(self) -> None:
        """Ошибка или отсутствие БД не роняет генерацию."""

        class BrokenDatabase:
            """Двойник, который всегда падает."""

            def find_item_by_alias(self, alias: str):
                raise RuntimeError("database is not connected")

            def find_squad_by_alias(self, alias: str):
                raise RuntimeError("database is not connected")

        project = self._make_trader_project()

        with self.assertLogs(
            "aqb.compiler.lua_gen", level="WARNING"
        ):
            script = LuaGenerator(
                db_client=BrokenDatabase()
            ).generate_quests_script(project)

        self.assertIn('item = "itm_pda_common"', script)
        self.assertIn(
            'target_squad = "esc_3_16_military_trader_squad"', script
        )


class TestFactionWarfareGates(unittest.TestCase):
    """Проверка faction/Warfare-гейтов в диалоге и функциях квеста."""

    @staticmethod
    def _make_project() -> ModProject:
        """Создаёт квест с обоими гейтами и связанный диалог выдачи."""
        quest = Quest(
            id="gated_quest",
            npc_id="esc_mayor",
            dialog_id="gated_take",
            requires_faction="army",
            requires_warfare=True,
            stages={0: Stage(id=0)},
        )
        dialog = Dialog(
            id="gated_take",
            task_id="gated_quest",
            role="take",
            phrases={
                0: Phrase(id=0, text_ru="Есть работа?", text_en="Got a job?")
            },
        )
        return ModProject(
            name="Gated",
            quests={quest.id: quest},
            dialogs={dialog.id: dialog},
        )

    @staticmethod
    def _block(script: str, start: str, end: str) -> str:
        """Возвращает фрагмент скрипта между двумя маркерами."""
        start_index = script.index(start)
        return script[start_index : script.index(end, start_index)]

    def test_can_take_checks_faction_and_warfare(self) -> None:
        """``_can_take`` закрывает диалог вне Warfare и без нужной фракции."""
        script = LuaGenerator().generate_quests_script(
            self._make_project(),
            script_name="gated_quests",
            mod_prefix="gated",
        )
        can_take = self._block(
            script,
            "local function gated_take_can_take",
            "local function gated_take_can_turn_in",
        )

        self.assertIn("local requires_warfare = true", can_take)
        self.assertIn(
            "if requires_warfare and not is_warfare() then", can_take
        )
        self.assertIn('local requires_faction = "army"', can_take)
        self.assertIn(
            'if requires_faction ~= "" and not '
            "is_actor_faction(requires_faction) then",
            can_take,
        )
        self.assertIn("local function is_actor_faction(faction)", script)
        self.assertIn("warfare.actor_faction == faction", script)
        self.assertIn("get_actor_true_community()", script)

    def test_start_and_status_stop_outside_warfare(self) -> None:
        """``_start``/``_status`` учитывают ``requires_warfare`` как ``world``."""
        script = LuaGenerator().generate_quests_script(
            self._make_project(),
            script_name="gated_quests",
            mod_prefix="gated",
        )
        status = self._block(
            script,
            "local function gated_quest_status",
            "local function gated_quest_start",
        )
        start = self._block(
            script,
            "local function gated_quest_start",
            "local function gated_quest_reward",
        )
        guard = (
            "if (quest.world or quest.requires_warfare) and "
            "not is_warfare() then"
        )

        self.assertIn(guard, status)
        self.assertIn(guard, start)
        self.assertIn('requires_warfare = true', script)
        self.assertIn('requires_faction = "army"', script)


class TestFreezeSquadGuard(unittest.TestCase):
    """Проверка возврата guard ``current_action == 1`` в ``freeze_squad``."""

    def test_freeze_squad_waits_for_arrival(self) -> None:
        """``stay_time`` выставляется только отряду, дошедшему до цели."""
        script = LuaGenerator().generate_quests_script(_make_project())
        block = script[
            script.index("local function freeze_squad(id)"):
            script.index("local function spawn_stage_for")
        ]

        guard = block.index("if squad.current_action == 1 then")
        stay_time = block.index("squad.stay_time = game.get_game_time()")
        self.assertLess(guard, stay_time)
        self.assertIn("mark_task_squad(squad)", block[guard:])
        self.assertIn("squad.force_online = true", block[guard:])


class TestDynamicSquadTracking(unittest.TestCase):
    """Проверка учёта отрядов из ``SpawnSquad`` в репликах и действиях."""

    @staticmethod
    def _make_project() -> ModProject:
        """Создаёт квест и диалог, которые спавнят отряды через SpawnSquad."""
        quest = Quest(
            id="dyn_quest",
            npc_id="esc_mayor",
            dialog_id="dyn_take",
            stages={
                0: Stage(
                    id=0,
                    on_start_actions=[
                        SpawnSquad(
                            squad_alias="army_sim_squad_advanced",
                            smart_alias="esc_smart",
                        )
                    ],
                )
            },
        )
        dialog = Dialog(
            id="dyn_take",
            task_id="dyn_quest",
            role="take",
            phrases={
                0: Phrase(
                    id=0,
                    text_ru="Штурм",
                    text_en="Assault",
                    actions=[
                        SpawnSquad(
                            squad_alias="army_sim_squad_advanced",
                            smart_alias="esc_smart",
                        )
                    ],
                )
            },
        )
        return ModProject(
            name="Dynamic",
            quests={quest.id: quest},
            dialogs={dialog.id: dialog},
        )

    @staticmethod
    def _block(script: str, start: str, end: str) -> str:
        """Возвращает фрагмент скрипта между двумя маркерами."""
        start_index = script.index(start)
        return script[start_index : script.index(end, start_index)]

    def test_dialog_and_quest_spawns_register_squads(self) -> None:
        """``run_actions`` получает id квеста, а spawn сохраняет squad.id."""
        script = LuaGenerator().generate_quests_script(
            self._make_project(),
            script_name="dyn_quests",
            mod_prefix="dyn",
        )
        phrase_action = self._block(
            script,
            "local function dyn_take_phrase_0_action",
            "local function register()",
        )
        status = self._block(
            script,
            "local function dyn_quest_status",
            "local function dyn_quest_start",
        )

        self.assertIn('"dyn_quest")', phrase_action)
        self.assertIn(
            'run_actions(stage_data.start_actions, db.actor, nil, "dyn_quest")',
            status,
        )
        self.assertIn(
            "local function register_dyn_squad(quest_id, squad)", script
        )
        self.assertIn(
            "local squad = spawn_task_squad(spec.smart, spec.squad, spec.smart)",
            script,
        )
        self.assertIn("register_dyn_squad(quest_id, squad)", script)
        self.assertIn('quest.key_prefix .. "_dyn_squad_cnt"', script)
        self.assertIn(
            'vset(quest.key_prefix .. "_dyn_squad_" .. tostring(idx), squad.id)',
            script,
        )

    def test_start_resets_dynamic_counter(self) -> None:
        """``_start`` обнуляет счётчик динамических отрядов."""
        script = LuaGenerator().generate_quests_script(
            self._make_project(),
            script_name="dyn_quests",
            mod_prefix="dyn",
        )
        start = self._block(
            script,
            "local function dyn_quest_start",
            "local function dyn_quest_reward",
        )

        self.assertIn(
            'vset(quest.key_prefix .. "_dyn_squad_cnt", 0)', start
        )

    def test_status_freezes_and_cleanup_releases_dynamic_squads(self) -> None:
        """``_status`` морозит, а ``unmark_quest_squads`` освобождает отряды."""
        script = LuaGenerator().generate_quests_script(
            self._make_project(),
            script_name="dyn_quests",
            mod_prefix="dyn",
        )
        status = self._block(
            script,
            "local function dyn_quest_status",
            "local function dyn_quest_start",
        )
        freeze_dyn = self._block(
            script,
            "local function freeze_dyn_squads(q)",
            "local function stage_cleared",
        )
        unmark = self._block(
            script,
            "local function unmark_quest_squads(q)",
            "local function register_dyn_squad",
        )

        self.assertIn("freeze_dyn_squads(quest)", status)
        self.assertIn(
            'vget(q.key_prefix .. "_dyn_squad_cnt", 0) or 0', freeze_dyn
        )
        self.assertIn(
            'vget(q.key_prefix .. "_dyn_squad_" .. tostring(i), 0)',
            freeze_dyn,
        )
        self.assertIn(
            'vget(q.key_prefix .. "_dyn_squad_" .. tostring(i), 0)', unmark
        )
        self.assertIn("unmark_task_squad(", unmark)


class TestIteration3Mechanics(unittest.TestCase):
    """P1-3…P1-9: идемпотентные предметы, cleanup_infos, announce, can_take."""

    @staticmethod
    def _make_project() -> ModProject:
        """Квест с GiveItem в этапе, вариантами и info-условием диалога."""
        quest = Quest(
            id="iter3_quest",
            npc_id="esc_mayor",
            dialog_id="iter3_take",
            taken_info="iter3_started",
            complete_info="iter3_done",
            cleanup_infos=["iter3_assault", "iter3_solo"],
            stages={
                0: Stage(
                    id=0,
                    on_start_actions=[
                        GiveItem(item_alias="itm_pda_common", count=1),
                        GiveInfo(info="iter3_ready"),
                    ],
                ),
                1: Stage(
                    id=1,
                    on_start_actions=[
                        GiveItem(item_alias="itm_pda_common", count=2),
                    ],
                ),
            },
        )
        dialog = Dialog(
            id="iter3_take",
            task_id="iter3_quest",
            role="take",
            preconditions=[
                DontHasInfo(info="iter3_started"),
                HasItem(item_alias="itm_pda_common"),
            ],
            phrases={
                0: Phrase(
                    id=0,
                    text_ru="Есть работа?",
                    text_en="Any work?",
                )
            },
        )
        return ModProject(
            name="Iteration 3",
            quests={quest.id: quest},
            dialogs={dialog.id: dialog},
        )

    @staticmethod
    def _block(script: str, start: str, end: str) -> str:
        """Возвращает фрагмент скрипта между двумя маркерами."""
        start_index = script.index(start)
        return script[start_index : script.index(end, start_index)]

    def setUp(self) -> None:
        """Генерирует скрипт и выделяет основные блоки."""
        self.script = LuaGenerator().generate_quests_script(
            self._make_project(),
            script_name="iter3_quests",
            mod_prefix="iter3",
        )
        self.quests = self._block(
            self.script, "local QUESTS = ", "-- Generic helpers"
        )
        self.status = self._block(
            self.script,
            "local function iter3_quest_status",
            "local function iter3_quest_start",
        )
        self.reward = self._block(
            self.script,
            "local function iter3_quest_reward",
            "local function iter3_quest_cleanup",
        )
        self.cleanup = self._block(
            self.script,
            "local function iter3_quest_cleanup",
            "local function iter3_quest_accept",
        )
        self.can_take = self._block(
            self.script,
            "local function iter3_take_can_take",
            "local function iter3_take_can_turn_in",
        )

    def test_give_item_is_split_into_idempotent_item_actions(self) -> None:
        """``GiveItem`` не входит в одноразовые ``start_actions``."""
        stage0 = self._block(self.quests, "[0] = {", "[1] = {")
        start_part = self._block(stage0, "start_actions =", "item_actions =")
        item_part = self._block(stage0, "item_actions =", "complete =")

        self.assertNotIn('kind = "give_item"', start_part)
        self.assertIn('kind = "give_item"', item_part)
        self.assertIn('info = "iter3_ready"', start_part)

    def test_status_regives_missing_quest_item_every_tick(self) -> None:
        """Каждый тик ``_status`` проверяет инвентарь и возвращает предмет."""
        self.assertIn(
            "run_actions(stage_data.start_actions, db.actor, nil, "
            '"iter3_quest")',
            self.status,
        )
        self.assertIn("for _, item_spec in ipairs(stage_data.item_actions or {}) do", self.status)
        self.assertIn(
            "if actor_item_count(item_spec.item, db.actor) < "
            "(item_spec.count or 1) then",
            self.status,
        )
        self.assertIn(
            "give_item(item_spec.item, item_spec.count, db.actor)",
            self.status,
        )
        self.assertIn(
            "if quest.complete_info == \"\" or "
            "not has_alife_info(quest.complete_info) then",
            self.status,
        )

    def test_cleanup_infos_are_saved_and_removed_on_reward_and_fail(self) -> None:
        """``cleanup_infos`` попадают в QUESTS и снимаются в обоих эффектах."""
        self.assertIn('"iter3_assault"', self.quests)
        self.assertIn('"iter3_solo"', self.quests)

        for block in (self.reward, self.cleanup):
            with self.subTest(block=block[:40]):
                self.assertIn(
                    "for _, info in ipairs(quest.cleanup_infos or {}) do",
                    block,
                )
                self.assertIn(
                    "db.actor:disable_info_portion(info)", block
                )

    def test_reward_does_not_remove_taken_or_complete_info(self) -> None:
        """Успешное завершение не снимает ``taken_info``/``complete_info``."""
        self.assertNotIn("disable_info_portion(quest.taken_info)", self.reward)
        self.assertNotIn(
            "disable_info_portion(quest.complete_info)", self.reward
        )

    def test_announce_uses_finished_stage_message(self) -> None:
        """Сообщение берётся у завершённого этапа, а не у следующего."""
        self.assertIn('stage_data.msg or ""', self.status)
        self.assertNotIn("next_data", self.script)

    def test_can_take_does_not_duplicate_info_conditions(self) -> None:
        """Info-условия остаются XML-тегами и не повторяются в Lua."""
        self.assertNotIn('info = "iter3_started"', self.can_take)
        self.assertNotIn('kind = "has_info"', self.can_take)
        self.assertNotIn('kind = "dont_has_info"', self.can_take)
        self.assertIn('kind = "has_item"', self.can_take)


if __name__ == "__main__":
    unittest.main(verbosity=2)
