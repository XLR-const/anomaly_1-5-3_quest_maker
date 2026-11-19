"""Тесты семантического линтера ``XRAY-*`` и действия ``ClearSmart``.

Проверяются:

* модель ``ClearSmart`` и условная генерация Lua-хелпера ``clear_smart``;
* неизменность SHA-256 эталонного Warfare-проекта (замок
  ``tests/test_warfare_regression.py``);
* ключевые правила :class:`~src.validation.xray_linter.XrayLinter`;
* отсутствие ``ERROR`` на обоих эталонных проектах.

Запуск::

    venv\\Scripts\\python.exe -m unittest tests.test_validation_xray -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
for _path in (str(PROJECT_ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from examples.build_golden_test import create_golden_shield_project  # noqa: E402
from examples.build_story_relay import build_project as build_story_relay  # noqa: E402
from src.compiler.lua_gen import LuaGenerator  # noqa: E402
from src.core.models import (  # noqa: E402
    ClearSmart,
    CompleteTask,
    CustomSquad,
    Dialog,
    GiveMoney,
    GiveTask,
    HasInfo,
    ModProject,
    Phrase,
    Quest,
    QuestCondlist,
    RemoveSquad,
    SmartOwner,
    SpawnNpcItem,
    SpawnSquad,
    Stage,
    WarfareCapture,
)
from src.db.repository import GameDatabase  # noqa: E402
from src.validation.report import Severity, ValidationReport  # noqa: E402
from src.validation.xray_linter import XrayLinter  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "anomaly_db.sqlite"


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------


def make_stage(
    stage_id: int = 0,
    *,
    actions: list | None = None,
    target_alias: str = "",
    warfare_capture: WarfareCapture | None = None,
) -> Stage:
    """Создаёт минимальный валидный этап с непустыми текстами."""
    return Stage(
        id=stage_id,
        title_ru="Этап",
        title_en="Stage",
        descr_ru="Описание этапа",
        descr_en="Stage description",
        target_alias=target_alias,
        on_start_actions=list(actions or []),
        warfare_capture=warfare_capture,
    )


def make_quest(
    quest_id: str = "quest_a",
    *,
    stages: dict[int, Stage] | None = None,
    **kwargs,
) -> Quest:
    """Создаёт минимальный валидный квест."""
    stages = stages or {0: make_stage()}
    return Quest(
        id=quest_id,
        title_ru="Квест",
        title_en="Quest",
        descr_ru="Описание квеста",
        descr_en="Quest description",
        stages=stages,
        **kwargs,
    )


def make_project(
    *,
    quests: list[Quest] | None = None,
    dialogs: list[Dialog] | None = None,
    squads: list[CustomSquad] | None = None,
) -> ModProject:
    """Собирает проект из переданных объектов."""
    quest_map = {quest.id: quest for quest in (quests or [])}
    dialog_map = {dialog.id: dialog for dialog in (dialogs or [])}
    squad_map = {squad.id: squad for squad in (squads or [])}
    return ModProject(
        name="Xray Linter Test",
        quests=quest_map,
        dialogs=dialog_map,
        squads=squad_map,
    )


def make_dialog(
    dialog_id: str = "dialog_a",
    *,
    role: str = "take",
    task_id: str | None = None,
    npc_id: str | None = None,
    preconditions: list | None = None,
    phrase_actions: list | None = None,
) -> Dialog:
    """Создаёт минимальный валидный диалог 0 -> 1."""
    return Dialog(
        id=dialog_id,
        role=role,
        task_id=task_id,
        npc_id=npc_id,
        preconditions=list(preconditions or []),
        phrases={
            0: Phrase(
                id=0,
                text_ru="Реплика игрока",
                text_en="Player line",
                next_phrases=[1],
                actions=list(phrase_actions or []),
            ),
            1: Phrase(
                id=1,
                text_ru="Ответ NPC",
                text_en="NPC line",
            ),
        },
    )


def analyze(project: ModProject, db=None) -> ValidationReport:
    """Прогоняет ``XrayLinter`` и возвращает отчёт."""
    report = ValidationReport()
    XrayLinter(db, report).validate(project)
    return report


def codes(report: ValidationReport, severity: Severity | None = None) -> set[str]:
    """Возвращает множество кодов замечаний (опционально по severity)."""
    return {
        issue.code
        for issue in report.issues
        if severity is None or issue.severity == severity
    }


class _FakeNpcDatabase:
    """Минимальная заглушка ``GameDatabase`` для data-driven теста."""

    def __init__(self, role: str | None) -> None:
        self.role = role

    def find_npc_by_alias(self, alias: str) -> dict:
        """Возвращает строку NPC с заданной ролью."""
        return {"id": "npc_test", "alias": alias, "role": self.role}


# ---------------------------------------------------------------------------
# ClearSmart: модель
# ---------------------------------------------------------------------------


class TestClearSmartModel(unittest.TestCase):
    """Проверяет поля и участие ``ClearSmart`` в union ``Action``."""

    def test_defaults(self) -> None:
        action = ClearSmart(smart_alias="smart_bandits")
        self.assertEqual(action.type, "clear_smart")
        self.assertEqual(action.smart_alias, "smart_bandits")
        self.assertIsNone(action.faction)
        self.assertEqual(action.keep_story_ids, [])
        self.assertFalse(action.allow_giver_smart)

    def test_explicit_fields(self) -> None:
        action = ClearSmart(
            smart_alias="smart_bandits",
            faction="bandit",
            keep_story_ids=["quest_squad"],
            allow_giver_smart=True,
        )
        self.assertEqual(action.faction, "bandit")
        self.assertEqual(action.keep_story_ids, ["quest_squad"])
        self.assertTrue(action.allow_giver_smart)

    def test_action_is_parsed_inside_stage(self) -> None:
        stage = make_stage(actions=[ClearSmart(smart_alias="smart_bandits")])
        self.assertIsInstance(stage.on_start_actions[0], ClearSmart)


# ---------------------------------------------------------------------------
# ClearSmart: Lua
# ---------------------------------------------------------------------------


class TestClearSmartLua(unittest.TestCase):
    """Проверяет условную генерацию хелпера ``clear_smart``."""

    def _project_with_clear_smart(self) -> ModProject:
        quest = make_quest(
            stages={
                0: make_stage(
                    actions=[
                        ClearSmart(
                            smart_alias="smart_bandits",
                            faction="bandit",
                            keep_story_ids=["keep_squad"],
                        ),
                        SpawnSquad(
                            squad_alias="quest_squad",
                            smart_alias="smart_bandits",
                            mode="story",
                        ),
                        SpawnNpcItem(
                            item_alias="itm_pda_common",
                            target_alias="quest_squad",
                        ),
                    ]
                )
            }
        )
        squad = CustomSquad(
            id="quest_squad",
            faction="bandit",
            npc=["sim_default_bandit_1"],
            story_id="quest_squad",
        )
        return make_project(quests=[quest], squads=[squad])

    def test_helper_and_branch_are_generated(self) -> None:
        script = LuaGenerator().generate_quests_script(
            self._project_with_clear_smart(),
            script_name="xray_test_quests",
            mod_prefix="xray_test",
        )
        self.assertIn("local function clear_smart(", script)
        self.assertIn('elseif kind == "clear_smart" then', script)
        self.assertIn('faction = "bandit"', script)
        self.assertIn('"keep_squad"', script)
        self.assertIn("get_squad_community", script)
        self.assertIn("remove_squad", script)
        self.assertIn("sim_offline_combat", script)

    def test_helper_absent_without_clear_smart(self) -> None:
        script = LuaGenerator().generate_quests_script(
            make_project(quests=[make_quest()]),
            script_name="plain_quests",
            mod_prefix="plain",
        )
        self.assertNotIn("clear_smart", script)

    def test_golden_reference_hashes_unchanged(self) -> None:
        """SHA-256 замок ``test_warfare_regression`` остаётся неизменным."""
        try:
            from tests.test_warfare_regression import (  # noqa: PLC0415
                SHA256_BEFORE,
                _generate_reference_files,
                _sha256_cp1251,
            )
        except ImportError:
            from test_warfare_regression import (  # noqa: PLC0415
                SHA256_BEFORE,
                _generate_reference_files,
                _sha256_cp1251,
            )

        files = _generate_reference_files()
        hashes = {
            name: _sha256_cp1251(text) for name, text in files.items()
        }
        self.assertEqual(hashes, SHA256_BEFORE)
        self.assertNotIn(
            "clear_smart", files["golden_shield_test_quests.script"]
        )


# ---------------------------------------------------------------------------
# XRAY-SPAWN-*, SPAWNITEM-*, CLEAN-003, NAME-001
# ---------------------------------------------------------------------------


class TestXraySpawnRules(unittest.TestCase):
    """Проверки спавна, предметов и имён."""

    def test_clear_smart_on_giver_smart_is_error(self) -> None:
        quest = make_quest(
            stages={
                0: make_stage(
                    target_alias="giver_smart",
                    actions=[ClearSmart(smart_alias="giver_smart")],
                )
            }
        )
        report = analyze(make_project(quests=[quest]))
        self.assertIn("XRAY-SPAWN-001", codes(report, Severity.ERROR))

    def test_clear_smart_on_giver_smart_allowed(self) -> None:
        quest = make_quest(
            stages={
                0: make_stage(
                    target_alias="giver_smart",
                    actions=[
                        ClearSmart(
                            smart_alias="giver_smart",
                            allow_giver_smart=True,
                        )
                    ],
                )
            }
        )
        report = analyze(make_project(quests=[quest]))
        self.assertNotIn("XRAY-SPAWN-001", codes(report))

    def test_clear_smart_after_spawn_is_error(self) -> None:
        quest = make_quest(
            stages={
                0: make_stage(
                    actions=[
                        SpawnSquad(
                            squad_alias="quest_squad",
                            smart_alias="spawn_smart",
                            mode="story",
                        ),
                        ClearSmart(smart_alias="spawn_smart"),
                    ]
                )
            }
        )
        squad = CustomSquad(
            id="quest_squad",
            faction="bandit",
            npc=["sim_default_bandit_1"],
            story_id="quest_squad",
        )
        report = analyze(make_project(quests=[quest], squads=[squad]))
        self.assertIn("XRAY-SPAWN-001", codes(report, Severity.ERROR))

    def test_spawn_squad_on_target_smart_warns(self) -> None:
        quest = make_quest(
            stages={
                0: make_stage(
                    actions=[
                        SpawnSquad(
                            squad_alias="quest_squad",
                            smart_alias="target_smart",
                            mode="story",
                        )
                    ]
                )
            }
        )
        squad = CustomSquad(
            id="quest_squad",
            faction="bandit",
            npc=["sim_default_bandit_1"],
            story_id="quest_squad",
            target_smart="target_smart",
        )
        report = analyze(make_project(quests=[quest], squads=[squad]))
        self.assertIn("XRAY-SPAWN-002", codes(report, Severity.WARNING))

    def test_spawn_npc_item_before_squad_is_error(self) -> None:
        quest = make_quest(
            stages={
                0: make_stage(
                    actions=[
                        SpawnNpcItem(
                            item_alias="itm_pda_common",
                            target_alias="quest_squad",
                        ),
                        SpawnSquad(
                            squad_alias="quest_squad",
                            smart_alias="spawn_smart",
                            mode="story",
                        ),
                    ]
                )
            }
        )
        squad = CustomSquad(
            id="quest_squad",
            faction="bandit",
            npc=["sim_default_bandit_1"],
            story_id="quest_squad",
        )
        report = analyze(make_project(quests=[quest], squads=[squad]))
        self.assertIn("XRAY-SPAWNITEM-001", codes(report, Severity.ERROR))

    def test_spawn_npc_item_target_without_story_id_is_error(self) -> None:
        quest = make_quest(
            stages={
                0: make_stage(
                    actions=[
                        SpawnSquad(
                            squad_alias="quest_squad",
                            smart_alias="spawn_smart",
                            mode="story",
                        ),
                        SpawnNpcItem(
                            item_alias="itm_pda_common",
                            target_alias="quest_squad",
                        ),
                    ]
                )
            }
        )
        squad = CustomSquad(
            id="quest_squad",
            faction="bandit",
            npc=["sim_default_bandit_1"],
        )
        report = analyze(make_project(quests=[quest], squads=[squad]))
        self.assertIn("XRAY-SPAWNITEM-002", codes(report, Severity.ERROR))

    def test_remove_squad_without_story_id_is_error(self) -> None:
        quest = make_quest(
            on_fail_actions=[RemoveSquad(squad_alias="quest_squad")],
        )
        squad = CustomSquad(
            id="quest_squad",
            faction="bandit",
            npc=["sim_default_bandit_1"],
        )
        report = analyze(make_project(quests=[quest], squads=[squad]))
        self.assertIn("XRAY-CLEAN-003", codes(report, Severity.ERROR))

    def test_duplicate_story_id_is_error(self) -> None:
        quest = make_quest()
        squads = [
            CustomSquad(
                id="squad_a",
                faction="bandit",
                npc=["sim_default_bandit_1"],
                story_id="shared_story",
            ),
            CustomSquad(
                id="squad_b",
                faction="bandit",
                npc=["sim_default_bandit_2"],
                story_id="shared_story",
            ),
        ]
        report = analyze(make_project(quests=[quest], squads=squads))
        self.assertIn("XRAY-NAME-001", codes(report, Severity.ERROR))


# ---------------------------------------------------------------------------
# XRAY-MODE-*, XRAY-WARFARE-*
# ---------------------------------------------------------------------------


class TestXrayModeAndWarfareRules(unittest.TestCase):
    """Проверки режимов и Warfare-условий."""

    def test_mixing_capture_and_story_spawn_is_error(self) -> None:
        quest = make_quest(
            stages={
                0: make_stage(
                    actions=[
                        SpawnSquad(
                            squad_alias="story_squad",
                            smart_alias="smart_a",
                            mode="story",
                        )
                    ],
                    warfare_capture=WarfareCapture(
                        smart_alias="smart_b",
                        enemy_squad_alias="enemy_squad",
                    ),
                )
            }
        )
        report = analyze(make_project(quests=[quest]))
        self.assertIn("XRAY-MODE-001", codes(report, Severity.ERROR))

    def test_requires_warfare_with_story_spawn_is_error(self) -> None:
        quest = make_quest(
            requires_warfare=True,
            stages={
                0: make_stage(
                    actions=[
                        SpawnSquad(
                            squad_alias="story_squad",
                            smart_alias="smart_a",
                            mode="story",
                        )
                    ]
                )
            },
        )
        report = analyze(make_project(quests=[quest]))
        self.assertIn("XRAY-MODE-002", codes(report, Severity.ERROR))

    def test_warfare_spawn_without_gate_warns(self) -> None:
        quest = make_quest(
            stages={
                0: make_stage(
                    actions=[
                        SpawnSquad(
                            squad_alias="war_squad",
                            smart_alias="smart_a",
                        )
                    ]
                )
            }
        )
        report = analyze(make_project(quests=[quest]))
        self.assertIn("XRAY-MODE-003", codes(report, Severity.WARNING))

    def test_smart_owner_in_extra_condlists_is_error(self) -> None:
        quest = make_quest(
            extra_condlists=[
                QuestCondlist(
                    when=[SmartOwner(smart_alias="smart_a", faction="army")],
                    result="complete",
                )
            ]
        )
        report = analyze(make_project(quests=[quest]))
        self.assertIn("XRAY-WARFARE-003", codes(report, Severity.ERROR))

    def test_requires_warfare_without_capture_warns(self) -> None:
        quest = make_quest(requires_warfare=True)
        report = analyze(make_project(quests=[quest]))
        self.assertIn("XRAY-WARFARE-004", codes(report, Severity.WARNING))

    def test_completion_path_suppresses_warfare_warning(self) -> None:
        quest = make_quest(requires_warfare=True, return_to_giver_stage=0)
        report = analyze(make_project(quests=[quest]))
        self.assertNotIn("XRAY-WARFARE-004", codes(report))


# ---------------------------------------------------------------------------
# XRAY-REWARD-003, DIALOG-001, LOC, MEET
# ---------------------------------------------------------------------------


class TestXrayDialogAndLocalizationRules(unittest.TestCase):
    """Проверки диалогов, локализации и data-driven meet-NPC."""

    def test_complete_task_in_take_is_error(self) -> None:
        quest = make_quest()
        dialog = make_dialog(
            role="take",
            task_id=quest.id,
            phrase_actions=[CompleteTask(task_id=quest.id)],
        )
        report = analyze(make_project(quests=[quest], dialogs=[dialog]))
        self.assertIn("XRAY-REWARD-003", codes(report, Severity.ERROR))

    def test_give_task_in_turnin_is_error(self) -> None:
        quest = make_quest()
        dialog = make_dialog(
            role="turnin",
            task_id=quest.id,
            preconditions=[HasInfo(info="ready")],
            phrase_actions=[GiveTask(task_id=quest.id)],
        )
        report = analyze(make_project(quests=[quest], dialogs=[dialog]))
        self.assertIn("XRAY-REWARD-003", codes(report, Severity.ERROR))

    def test_inline_reward_near_complete_is_warning(self) -> None:
        quest = make_quest()
        dialog = make_dialog(
            role="turnin",
            task_id=quest.id,
            phrase_actions=[
                GiveMoney(amount=1000),
                CompleteTask(task_id=quest.id),
            ],
        )
        report = analyze(make_project(quests=[quest], dialogs=[dialog]))
        self.assertIn("XRAY-REWARD-002", codes(report, Severity.WARNING))
        self.assertNotIn("XRAY-REWARD-002", codes(report, Severity.ERROR))

    def test_turnin_without_readiness_gate_warns(self) -> None:
        quest = make_quest()
        dialog = make_dialog(role="turnin", task_id=quest.id)
        report = analyze(make_project(quests=[quest], dialogs=[dialog]))
        self.assertIn("XRAY-DIALOG-001", codes(report, Severity.WARNING))

    def test_turnin_with_info_gate_is_clean(self) -> None:
        quest = make_quest()
        dialog = make_dialog(
            role="turnin",
            task_id=quest.id,
            preconditions=[HasInfo(info="ready")],
        )
        report = analyze(make_project(quests=[quest], dialogs=[dialog]))
        self.assertNotIn("XRAY-DIALOG-001", codes(report))

    def test_phrase_parity_violation_warns(self) -> None:
        quest = make_quest()
        dialog = Dialog(
            id="dialog_parity",
            role="branch",
            phrases={
                0: Phrase(
                    id=0,
                    text_ru="Игрок",
                    text_en="Player",
                    next_phrases=[2],
                ),
                2: Phrase(
                    id=2,
                    text_ru="Снова игрок",
                    text_en="Player again",
                ),
            },
        )
        report = analyze(make_project(quests=[quest], dialogs=[dialog]))
        self.assertIn("XRAY-LOC-002", codes(report, Severity.WARNING))

    def test_empty_and_too_long_localization(self) -> None:
        empty = make_quest("quest_empty")
        empty.title_ru = ""
        empty.descr_ru = ""
        long_title = make_quest("quest_long")
        long_title.title_ru = "Я" * 65
        report = analyze(make_project(quests=[empty, long_title]))
        self.assertIn("XRAY-LOC-001", codes(report, Severity.WARNING))
        self.assertIn("XRAY-LOC-003", codes(report, Severity.INFO))

    def test_meet_detection_is_data_driven(self) -> None:
        quest = make_quest()
        npc_dialog = make_dialog(
            "dialog_meet",
            role="take",
            task_id=quest.id,
            npc_id="npc_test",
        )
        project = make_project(quests=[quest], dialogs=[npc_dialog])

        trader_report = analyze(project, db=_FakeNpcDatabase("trader"))
        self.assertIn(
            "XRAY-MEET-001", codes(trader_report, Severity.WARNING)
        )

        plain_report = analyze(project, db=_FakeNpcDatabase(None))
        self.assertNotIn("XRAY-MEET-001", codes(plain_report))

    def test_meet_detection_against_real_database(self) -> None:
        quest = make_quest()
        dialog = make_dialog(
            "dialog_dushman",
            role="take",
            task_id=quest.id,
            npc_id="cit_killers_merc_trader_stalker",
        )
        project = make_project(quests=[quest], dialogs=[dialog])
        with GameDatabase(DB_PATH) as db:
            report = analyze(project, db=db)
        self.assertIn("XRAY-MEET-001", codes(report, Severity.WARNING))


# ---------------------------------------------------------------------------
# Эталоны
# ---------------------------------------------------------------------------


class TestReferenceProjects(unittest.TestCase):
    """Оба эталона обязаны проходить линтер без ``ERROR``."""

    def test_story_relay_has_no_errors(self) -> None:
        project = build_story_relay()
        with GameDatabase(DB_PATH) as db:
            report = analyze(project, db=db)
        self.assertEqual(report.errors, [])

    def test_golden_shield_has_no_errors(self) -> None:
        project = create_golden_shield_project()
        with GameDatabase(DB_PATH) as db:
            report = analyze(project, db=db)
        self.assertEqual(report.errors, [])

    def test_linter_works_without_database(self) -> None:
        report = analyze(create_golden_shield_project(), db=None)
        self.assertEqual(report.errors, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
