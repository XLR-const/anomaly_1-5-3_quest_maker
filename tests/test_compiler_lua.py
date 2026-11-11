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
    GiveTask,
    HasInfo,
    HasItem,
    ModProject,
    Phrase,
    Quest,
    Stage,
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
