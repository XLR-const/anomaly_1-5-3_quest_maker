"""Юнит-тесты отчёта валидации и справочного валидатора ассетов."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from examples.build_golden_test import create_golden_shield_project
from examples.build_story_relay import build_project as build_story_relay_project
from src.core.models import (
    CustomSquad,
    GiveItem,
    ModProject,
    Quest,
    RemoveSquad,
    SpawnNpcItem,
    SpawnSquad,
    Stage,
    WarfareCapture,
)
from src.db.repository import GameDatabase
from src.validation import (
    CatalogValidator,
    Severity,
    ValidationIssue,
    ValidationReport,
    ValidationReportError,
)

_DB_PATH = _PROJECT_ROOT / "data" / "anomaly_db.sqlite"


def _validate(project: ModProject) -> ValidationReport:
    """Запускает CatalogValidator на реальной базе ``data/anomaly_db.sqlite``."""
    report = ValidationReport()
    with GameDatabase(_DB_PATH) as db:
        CatalogValidator(db, report).validate(project)
    return report


def _error_codes(report: ValidationReport) -> set[str]:
    """Возвращает коды всех ошибок отчёта."""
    return {issue.code for issue in report.errors}


def _error_text(report: ValidationReport) -> str:
    """Форматирует ошибки для assertEqual/assertIn-сообщений."""
    return "\n".join(
        f"{issue.code} {issue.target_id}: {issue.message}"
        for issue in report.errors
    )


class ValidationReportTests(unittest.TestCase):
    """Проверки контракта ``report.py``."""

    def test_severity_values(self) -> None:
        self.assertEqual(int(Severity.INFO), 10)
        self.assertEqual(int(Severity.WARNING), 20)
        self.assertEqual(int(Severity.ERROR), 30)

    def test_add_deduplicates_by_code_target_and_message(self) -> None:
        report = ValidationReport()
        report.add("CAT-NPC-001", Severity.ERROR, "quest:q", "missing")
        report.add("CAT-NPC-001", Severity.ERROR, "quest:q", "missing")
        report.add("CAT-NPC-001", Severity.ERROR, "quest:q", "other")

        self.assertEqual(len(report.issues), 2)
        self.assertEqual(len(report.errors), 2)

    def test_extend_deduplicates(self) -> None:
        issue = ValidationIssue(
            code="CAT-SMART-001",
            severity=Severity.ERROR,
            target_id="quest:q.stage:0.target_alias",
            message="smart missing",
        )
        report = ValidationReport()
        report.extend([issue, issue])

        self.assertEqual(report.issues, [issue])

    def test_properties_and_sorting(self) -> None:
        report = ValidationReport()
        report.add("Z-CODE", Severity.ERROR, "b", "z")
        report.add("A-CODE", Severity.ERROR, "a", "a")
        report.add("W-CODE", Severity.WARNING, "c", "w")
        report.add("I-CODE", Severity.INFO, "d", "i")

        self.assertTrue(report.has_errors)
        self.assertEqual(len(report.errors), 2)
        self.assertEqual(len(report.warnings), 1)
        self.assertEqual(
            [issue.code for issue in report.sorted()],
            ["A-CODE", "Z-CODE", "W-CODE", "I-CODE"],
        )

    def test_to_dict_summary(self) -> None:
        report = ValidationReport()
        report.add("E", Severity.ERROR, "q", "error")
        report.add("W", Severity.WARNING, "q", "warning")
        report.add("I", Severity.INFO, "q", "info")

        data = report.to_dict()
        self.assertEqual(
            data["summary"],
            {"errors": 1, "warnings": 1, "info": 1, "total": 3},
        )
        self.assertEqual(len(data["issues"]), 3)
        self.assertEqual(data["issues"][0]["severity"], "ERROR")

    def test_to_json_is_deterministic_and_keeps_unicode(self) -> None:
        report = ValidationReport()
        report.add("E", Severity.ERROR, "q", "Ошибка")

        first = report.to_json()
        second = report.to_json()
        self.assertEqual(first, second)
        self.assertIn("Ошибка", first)
        self.assertEqual(json.loads(first)["summary"]["errors"], 1)

    def test_to_text_contains_markers_target_and_hint(self) -> None:
        report = ValidationReport()
        report.add(
            "CAT-NPC-001",
            Severity.ERROR,
            "quest:story_08.npc_id",
            "NPC не найден",
            hint="Замените профиль",
        )
        report.add("CAT-SMART-001", Severity.WARNING, "quest:q", "Смарт")

        text = report.to_text()
        self.assertIn("[ERROR]", text)
        self.assertIn("[WARNING]", text)
        self.assertIn("quest:story_08.npc_id", text)
        self.assertIn("hint: Замените профиль", text)

    def test_raise_if_errors(self) -> None:
        warning_only = ValidationReport()
        warning_only.add("W", Severity.WARNING, "q", "warning")
        warning_only.raise_if_errors()

        report = ValidationReport()
        report.add("E", Severity.ERROR, "q", "error")
        with self.assertRaises(ValidationReportError) as context:
            report.raise_if_errors()
        self.assertIs(context.exception.report, report)


class CatalogValidatorTests(unittest.TestCase):
    """Проверки отрицательных и положительных сценариев `CAT-*`."""

    def test_missing_npc_profile_cat_npc_001(self) -> None:
        quest = Quest(
            id="test_npc_quest",
            npc_id="esc_m_trader",
            npc_location="escape",
            stages={0: Stage(id=0)},
        )
        report = _validate(
            ModProject(name="bad npc", quests={quest.id: quest})
        )

        self.assertIn("CAT-NPC-001", _error_codes(report), _error_text(report))

    def test_missing_smart_cat_smart_001(self) -> None:
        quest = Quest(
            id="test_smart_quest",
            stages={
                0: Stage(
                    id=0,
                    target_alias="garb_smart_terrain_1_6",
                )
            },
        )
        report = _validate(
            ModProject(name="bad smart", quests={quest.id: quest})
        )

        self.assertIn(
            "CAT-SMART-001", _error_codes(report), _error_text(report)
        )

    def test_missing_squad_alias_cat_squad_001(self) -> None:
        quest = Quest(
            id="test_squad_quest",
            on_init_actions=[
                SpawnSquad(
                    squad_alias="squad.mercenary_advanced",
                    smart_alias="zat_b7",
                    mode="story",
                )
            ],
            stages={0: Stage(id=0)},
        )
        report = _validate(
            ModProject(name="bad squad", quests={quest.id: quest})
        )

        self.assertIn(
            "CAT-SQUAD-001", _error_codes(report), _error_text(report)
        )

    def test_npc_sections_in_warfare_capture(self) -> None:
        quest = Quest(
            id="test_warfare_quest",
            stages={
                0: Stage(
                    id=0,
                    warfare_capture=WarfareCapture(
                        smart_alias="zat_b7",
                        enemy_squad_alias="sim_default_stalker_1",
                        ally_squad_alias="sim_default_stalker_1",
                        ally_count=1,
                    ),
                )
            },
        )
        report = _validate(
            ModProject(name="bad warfare", quests={quest.id: quest})
        )
        codes = _error_codes(report)

        self.assertIn("CAT-WARFARE-001", codes, _error_text(report))
        self.assertIn("CAT-WARFARE-002", codes, _error_text(report))

    def test_enemy_spawn_on_giver_smart_cat_smart_003(self) -> None:
        squad_id = "test_enemy_squad"
        squad = CustomSquad(
            id=squad_id,
            faction="killer",
            npc=["sim_default_killer_1"],
            story_id=squad_id,
        )
        quest = Quest(
            id="test_giver_smart_quest",
            npc_id="esc_2_12_stalker_wolf",
            npc_location="escape",
            on_init_actions=[
                SpawnSquad(
                    squad_alias=squad_id,
                    smart_alias="esc_smart_terrain_2_12",
                    mode="story",
                )
            ],
            stages={0: Stage(id=0)},
        )
        report = _validate(
            ModProject(
                name="enemy on giver smart",
                quests={quest.id: quest},
                squads={squad.id: squad},
            )
        )

        self.assertIn(
            "CAT-SMART-003", _error_codes(report), _error_text(report)
        )

    def test_story_squad_without_story_id_cat_squad_002(self) -> None:
        squad_id = "test_squad_without_story"
        squad = CustomSquad(
            id=squad_id,
            faction="killer",
            npc=["sim_default_killer_1"],
        )
        quest = Quest(
            id="test_story_id_quest",
            on_fail_actions=[RemoveSquad(squad_alias=squad_id)],
            stages={
                0: Stage(
                    id=0,
                    on_start_actions=[
                        SpawnNpcItem(
                            item_alias="itm_pda_common",
                            target_alias=squad_id,
                        )
                    ],
                )
            },
        )
        report = _validate(
            ModProject(
                name="no story id",
                quests={quest.id: quest},
                squads={squad.id: squad},
            )
        )
        squad_issues = [
            issue
            for issue in report.errors
            if issue.code == "CAT-SQUAD-002"
        ]

        self.assertGreaterEqual(
            len(squad_issues), 2, _error_text(report)
        )

    def test_missing_item_cat_item_001(self) -> None:
        quest = Quest(
            id="test_item_quest",
            stages={
                0: Stage(
                    id=0,
                    on_start_actions=[
                        GiveItem(item_alias="missing_quest_item")
                    ],
                )
            },
        )
        report = _validate(
            ModProject(name="bad item", quests={quest.id: quest})
        )

        self.assertIn(
            "CAT-ITEM-001", _error_codes(report), _error_text(report)
        )

    def test_unknown_faction_cat_faction_001(self) -> None:
        quest = Quest(
            id="test_faction_quest",
            requires_faction="unknown_faction",
            stages={0: Stage(id=0)},
        )
        report = _validate(
            ModProject(name="bad faction", quests={quest.id: quest})
        )

        self.assertIn(
            "CAT-FACTION-001",
            {issue.code for issue in report.issues},
            _error_text(report),
        )

    def test_story_relay_example_has_no_errors(self) -> None:
        report = _validate(build_story_relay_project())
        self.assertEqual(report.errors, [], _error_text(report))

    def test_golden_test_example_has_no_errors(self) -> None:
        report = _validate(create_golden_shield_project())
        self.assertEqual(report.errors, [], _error_text(report))


if __name__ == "__main__":
    unittest.main()
