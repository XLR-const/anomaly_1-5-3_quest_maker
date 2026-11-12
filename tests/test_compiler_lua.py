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
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compiler.lua_gen import LuaGenerator  # noqa: E402
from src.core.models import (  # noqa: E402
    CompleteTask,
    Dialog,
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

    def test_resolve_alife_object_searches_squad_section(self) -> None:
        """Секция сквада находится через SIMBOARD и перебор ``alife()``."""
        script = LuaGenerator().generate_quests_script(
            self._make_trader_project()
        )

        for fragment in (
            "if get_story_squad then",
            "pcall(get_story_squad, target)",
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
