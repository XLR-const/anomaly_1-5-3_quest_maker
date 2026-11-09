"""Автоматические тесты генератора Lua-логики квестов и диалогов.

Запуск из корня проекта::

    python -m unittest tests.test_compiler_lua -v
    python -m unittest discover -s tests -v

Тесты проверяют структуру и сигнатуры сгенерированных функторов, трансляцию
Pydantic-действий в игровые методы Anomaly, обработку ``transfer_conditions``
и отказоустойчивость генератора при повреждённом квесте.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from typing import Any

from pydantic import Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compiler.lua_gen import LuaGenerator  # noqa: E402
from src.core.models import (  # noqa: E402
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveItem,
    GiveMoney,
    HasInfo,
    HasItem,
    ModProject,
    Phrase,
    Quest,
    RemoveInfo,
    RemoveItem,
    SpawnSquad,
    Stage,
)

QUEST_ID = "mymod_test_quest"
SECOND_QUEST_ID = "mymod_transfer_quest"
BROKEN_QUEST_ID = "mymod_broken_quest"
DIALOG_ID = "mymod_test_dialog"
LUA_LOGGER_NAME = "aqb.compiler.lua_gen"

REWARD_ITEM = "mymod_reward_item"
QUEST_ITEM = "mymod_quest_item"
STAGE_TARGET_0 = "esc.test_target_0"
STAGE_TARGET_1 = "esc.test_target_1"


class QuestWithTransfers(Quest):
    """Тестовая модель квеста с расширенным полем ``transfer_conditions``.

    Базовая модель :class:`~src.core.models.Quest` пока не содержит это поле.
    Наследник демонстрирует контракт, который поддерживает генератор Lua:
    правила завершения и провала можно хранить как для квеста целиком, так и
    для отдельных этапов.
    """

    transfer_conditions: dict[Any, Any] = Field(
        default_factory=dict,
        description="Правила перехода этапов квеста.",
    )


def _make_quest(quest_id: str = QUEST_ID) -> Quest:
    """Создаёт валидный квест с двумя этапами и всеми видами действий.

    Args:
        quest_id (str):
            Идентификатор квеста и ключ карты квестов.

    Returns:
        Quest: Валидная модель с действиями выдачи, награды и провала.
    """
    return Quest(
        id=quest_id,
        title_ru="Тестовый квест",
        title_en="Test quest",
        descr_ru="Описание тестового квеста",
        descr_en="Test quest description",
        stages={
            0: Stage(
                id=0,
                title_ru="Первый этап",
                title_en="First stage",
                descr_ru="Описание первого этапа",
                descr_en="First stage description",
                target_alias=STAGE_TARGET_0,
            ),
            1: Stage(
                id=1,
                title_ru="Второй этап",
                title_en="Second stage",
                descr_ru="Описание второго этапа",
                descr_en="Second stage description",
                target_alias=STAGE_TARGET_1,
            ),
        },
        on_init_actions=[
            GiveInfo(info="mymod_quest_started"),
            SpawnSquad(
                squad_alias="mymod_task_squad",
                smart_alias="esc_smart_terrain_test",
            ),
        ],
        on_complete_actions=[
            GiveItem(item_alias=REWARD_ITEM),
            GiveMoney(amount=5000),
        ],
        on_fail_actions=[
            RemoveItem(item_alias=QUEST_ITEM),
            RemoveInfo(info="mymod_quest_started"),
        ],
    )


def _make_transfer_quest() -> QuestWithTransfers:
    """Создаёт квест с правилами ``transfer_conditions`` для двух этапов.

    Returns:
        QuestWithTransfers: Квест, который завершает первый этап по
        инфопоршню и последний — по наличию предмета; провал определяется
        отсутствием другого инфопоршня.
    """
    base_quest = _make_quest(SECOND_QUEST_ID)

    return QuestWithTransfers(
        **base_quest.model_dump(),
        transfer_conditions={
            0: {
                "complete": [HasInfo(info="mymod_stage_0_done")],
            },
            1: {
                "complete": [HasItem(item_alias=REWARD_ITEM)],
                "fail": [DontHasInfo(info="mymod_stage_1_allowed")],
            },
        },
    )


def _make_dialog() -> Dialog:
    """Создаёт диалог с предусловиями и всеми видами действий.

    Returns:
        Dialog: Три реплики, две из которых содержат логику.
    """
    return Dialog(
        id=DIALOG_ID,
        npc_alias="esc.mayor_zhurov",
        phrases={
            0: Phrase(
                id=0,
                text_ru="Здравствуй, сталкер!",
                text_en="Hello, stalker!",
                next_phrases=[1],
                preconditions=[HasInfo(info="mymod_dialog_available")],
                actions=[
                    GiveItem(item_alias=REWARD_ITEM),
                    RemoveItem(item_alias=QUEST_ITEM),
                    GiveMoney(amount=2500),
                ],
            ),
            1: Phrase(
                id=1,
                text_ru="Вот твоя награда.",
                text_en="Here is your reward.",
                preconditions=[
                    DontHasInfo(info="mymod_dialog_used"),
                    HasItem(item_alias=QUEST_ITEM),
                ],
                actions=[
                    GiveInfo(info="mymod_dialog_used"),
                    RemoveInfo(info="mymod_dialog_available"),
                ],
            ),
            2: Phrase(
                id=2,
                text_ru="До встречи.",
                text_en="See you.",
            ),
        },
    )


def _make_project() -> ModProject:
    """Создаёт валидный проект с одним квестом и одним диалогом.

    Returns:
        ModProject: Проект для проверки структуры Lua-скрипта.
    """
    return ModProject(
        name="mymod_lua_test",
        quests={QUEST_ID: _make_quest()},
        dialogs={DIALOG_ID: _make_dialog()},
    )


class TestLuaGeneratorStructure(unittest.TestCase):
    """Проверка структуры скрипта и сигнатур сгенерированных функций."""

    def setUp(self) -> None:
        """Создаёт генератор перед каждым тестом."""
        self.generator = LuaGenerator()

    def test_generates_helpers_and_strict_functor_signatures(self) -> None:
        """Скрипт содержит хелперы и точные сигнатуры Anomaly."""
        script = self.generator.generate_quests_script(_make_project())
        quest_id = re.escape(QUEST_ID)
        dialog_id = re.escape(DIALOG_ID)

        self.assertRegex(
            script,
            r"function\s+mymod_quests\.is_smart_captured"
            r"\s*\(\s*smart_id\s*,\s*faction\s*\)",
        )
        self.assertRegex(
            script,
            r"function\s+mymod_quests\.spawn_task_squad"
            r"\s*\(\s*squad_id\s*,\s*smart_id\s*\)",
        )
        self.assertIn("save_var(db.actor", script)
        self.assertIn("load_var(db.actor", script)
        self.assertIn('xr_sound.set_sound_play(db.actor, "pda_task")', script)

        for function_name, arguments in (
            ("on_init", r"tsk"),
            ("on_complete", r"tsk"),
            ("on_fail", r"tsk"),
            ("status_functor", r"tsk\s*,\s*task_id"),
            ("target_functor", r"tsk\s*,\s*task_id"),
        ):
            with self.subTest(function=function_name):
                self.assertRegex(
                    script,
                    rf"function\s+mymod_quests\.{quest_id}_{function_name}"
                    rf"\s*\(\s*{arguments}\s*\)",
                )

        self.assertRegex(
            script,
            rf"function\s+mymod_quests\.{dialog_id}_phrase_0_precondition"
            r"\s*\(\s*first_speaker\s*,\s*second_speaker\s*,\s*"
            r"dialog_id\s*,\s*phrase_id\s*\)",
        )
        self.assertRegex(
            script,
            rf"function\s+mymod_quests\.{dialog_id}_phrase_0_action"
            r"\s*\(\s*first_speaker\s*,\s*second_speaker\s*,\s*"
            r"dialog_id\s*,\s*phrase_id\s*\)",
        )

        self.assertIn(STAGE_TARGET_0, script)
        self.assertIn(STAGE_TARGET_1, script)


class TestLuaGeneratorActions(unittest.TestCase):
    """Проверка трансляции Pydantic-условий и действий в Lua-API."""

    def setUp(self) -> None:
        """Создаёт генератор перед каждым тестом."""
        self.generator = LuaGenerator()

    def test_translates_money_items_and_info_actions(self) -> None:
        """GiveMoney, GiveItem, RemoveItem и инфопоршни дают верные вызовы."""
        script = self.generator.generate_quests_script(_make_project())

        self.assertIn("db.actor:give_money(5000)", script)
        self.assertIn("db.actor:give_money(2500)", script)
        self.assertIn(
            f'dialogs.relocate_item_section(second_speaker, "{REWARD_ITEM}", "in")',
            script,
        )
        self.assertIn(
            f'dialogs.relocate_item_section(second_speaker, "{QUEST_ITEM}", "out")',
            script,
        )
        self.assertIn(
            f'dialogs.relocate_item_section(db.actor, "{REWARD_ITEM}", "in")',
            script,
        )
        self.assertIn(
            f'dialogs.relocate_item_section(db.actor, "{QUEST_ITEM}", "out")',
            script,
        )
        self.assertIn('has_alife_info("mymod_dialog_available")', script)
        self.assertIn('not has_alife_info("mymod_dialog_used")', script)
        self.assertIn('db.actor:give_info_portion("mymod_quest_started")', script)
        self.assertIn(
            'db.actor:disable_info_portion("mymod_quest_started")',
            script,
        )

    def test_translates_transfer_conditions_into_status_functor(self) -> None:
        """Правила transfer_conditions управляют stage и результатом квеста."""
        project = ModProject(
            name="mymod_transfer_test",
            quests={SECOND_QUEST_ID: _make_transfer_quest()},
            dialogs={},
        )

        script = self.generator.generate_quests_script(project)

        self.assertIn('if has_alife_info("mymod_stage_0_done") then', script)
        self.assertIn("tsk.stage = 1", script)
        self.assertIn(f'if db.actor:object("{REWARD_ITEM}") ~= nil then', script)
        self.assertIn(
            'if not has_alife_info("mymod_stage_1_allowed") then',
            script,
        )
        self.assertIn('return "complete"', script)
        self.assertIn('return "fail"', script)


class TestLuaGeneratorFaultTolerance(unittest.TestCase):
    """Проверка изоляции повреждённых квестов и отдельных действий."""

    def setUp(self) -> None:
        """Создаёт генератор перед каждым тестом."""
        self.generator = LuaGenerator()

    def test_skips_broken_quest_and_keeps_valid_one(self) -> None:
        """Повреждённый квест логируется и не ломает генерацию остальных."""
        broken_quest = Quest.model_construct(
            id=BROKEN_QUEST_ID,
            title_ru="Повреждённый квест",
            title_en="Broken quest",
            descr_ru="Описание",
            descr_en="Description",
            is_storyline=True,
            stages="повреждённая структура вместо карты этапов",
            on_init_actions=[],
            on_complete_actions=[],
            on_fail_actions=[],
        )
        project = ModProject.model_construct(
            name="mymod_broken_test",
            required_mods=[],
            quests={
                QUEST_ID: _make_quest(),
                BROKEN_QUEST_ID: broken_quest,
            },
            dialogs={DIALOG_ID: _make_dialog()},
        )

        with self.assertLogs(LUA_LOGGER_NAME, level="ERROR") as captured:
            script = self.generator.generate_quests_script(project)

        self.assertIn(f"function mymod_quests.{QUEST_ID}_on_init(tsk)", script)
        self.assertIn(
            f"function mymod_quests.{QUEST_ID}_status_functor(tsk, task_id)",
            script,
        )
        self.assertNotIn(BROKEN_QUEST_ID, script)
        self.assertTrue(
            any(BROKEN_QUEST_ID in message for message in captured.output),
            "В логе должно быть сообщение о пропущенном повреждённом квесте.",
        )

    def test_broken_action_is_logged_but_other_actions_survive(self) -> None:
        """Одно повреждённое действие не отменяет весь квест."""
        broken_action_quest = Quest.model_construct(
            id=SECOND_QUEST_ID,
            title_ru="Квест с плохим действием",
            title_en="Quest with broken action",
            descr_ru="Описание",
            descr_en="Description",
            is_storyline=True,
            stages={
                0: Stage(
                    id=0,
                    title_ru="Этап",
                    title_en="Stage",
                    descr_ru="Описание",
                    descr_en="Description",
                    target_alias=STAGE_TARGET_0,
                )
            },
            on_init_actions=[GiveInfo(info="mymod_valid_info"), object()],
            on_complete_actions=[GiveMoney(amount=100)],
            on_fail_actions=[],
        )

        with self.assertLogs(LUA_LOGGER_NAME, level="ERROR") as captured:
            script = self.generator.generate_quests_script(
                ModProject.model_construct(
                    name="mymod_broken_action_test",
                    required_mods=[],
                    quests={SECOND_QUEST_ID: broken_action_quest},
                    dialogs={},
                )
            )

        self.assertIn(
            'db.actor:give_info_portion("mymod_valid_info")',
            script,
        )
        self.assertIn("db.actor:give_money(100)", script)
        self.assertIn("-- Пропущено действие #1", script)
        self.assertTrue(
            any(
                "Действие #1" in message for message in captured.output
            ),
            "В логе должно быть сообщение о пропущенном действии.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
