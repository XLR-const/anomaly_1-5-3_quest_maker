"""Полировочные тесты SDK ``aqm`` v1.0.1.

Проверяют автономную сборку ``CustomNpc``/``ModBuilder()`` без ``_unpacked``,
отсутствие ложных срабатываний ``XRAY-SPAWN-001``/``XRAY-DIALOG-001`` и
резолвинг прямых секций предметов/отрядов без лишних warning.
"""

from __future__ import annotations

import contextlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aqm.compiler import lua_gen
from aqm.compiler.builder import ModBuilder
from aqm.compiler.lua_gen import LuaGenerator
from aqm.compiler.npc_gen import resolve_npc_template
from aqm.core.models import (
    ClearSmart,
    CustomNpc,
    CustomSquad,
    Dialog,
    HasInfo,
    HasItem,
    ModProject,
    Phrase,
    Quest,
    Stage,
)
from aqm.db.repository import GameDatabase
from aqm.paths import get_default_db_path
from aqm.validation.report import Severity, ValidationReport
from aqm.validation.xray_linter import XrayLinter


def _codes(report: ValidationReport, severity: Severity) -> set[str]:
    """Возвращает коды замечаний заданной важности."""
    return {
        issue.code
        for issue in report.issues
        if issue.severity == severity
    }


class TestAutonomousCustomNpc(unittest.TestCase):
    """CustomNpc и ModBuilder по умолчанию работают без ``_unpacked``."""

    def test_resolve_and_build_from_embedded_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "aqm.json").write_text(
                '{"output_dir": "output", "db_path": null, '
                '"vanilla_dir": null}',
                encoding="utf-8",
            )
            npc = CustomNpc(
                id="polish_autonomous_guide",
                template_npc_id="esc_2_12_stalker_wolf",
                faction="stalker",
                name_ru="Проводник",
                name_en="Guide",
                spawn_smart="esc_smart_terrain_2_12",
            )
            project = ModProject(
                name="Polish Autonomous Mod",
                mod_slug="polish_autonomous",
                npcs={npc.id: npc},
            )

            with contextlib.chdir(root):
                builder = ModBuilder()
                try:
                    self.assertIsNotNone(builder.db_client)
                    self.assertEqual(builder.output_dir, root / "output")
                    resolved = resolve_npc_template(
                        npc, builder.db_client, None
                    )
                    self.assertEqual(resolved["community"], "stalker")
                    self.assertTrue(resolved["visual"])

                    self.assertTrue(builder.build_project(project))
                finally:
                    builder.close()

            project_dir = root / "output" / "polish_autonomous_mod"
            self.assertTrue(
                (project_dir / "gamedata" / "configs" / "gameplay"
                 / "character_desc_polish_autonomous_mod.xml").is_file()
            )
            self.assertTrue(
                (project_dir / "gamedata" / "configs" / "gameplay"
                 / "npc_profile_polish_autonomous_mod.xml").is_file()
            )
            self.assertFalse((root / "_unpacked").exists())


class TestFalseLinterWarnings(unittest.TestCase):
    """Ложные XRAY-SPAWN-001/XRAY-DIALOG-001 не выдаются."""

    @staticmethod
    def _project_with_giver() -> ModProject:
        npc = CustomNpc(
            id="polish_giver",
            faction="stalker",
            visual="actors\\stalker_black_stalker",
            spawn_smart="giver_smart",
        )
        quest = Quest(
            id="polish_quest",
            npc_id=npc.id,
            stages={
                0: Stage(
                    id=0,
                    target_alias="target_smart",
                    on_start_actions=[
                        ClearSmart(smart_alias="target_smart"),
                    ],
                ),
            },
        )
        return ModProject(
            name="Polish Linter",
            mod_slug="polish_linter",
            quests={quest.id: quest},
            npcs={npc.id: npc},
        )

    def test_clear_smart_on_stage_target_is_not_giver_error(self) -> None:
        report = ValidationReport()
        XrayLinter(None, report).validate(self._project_with_giver())
        self.assertNotIn(
            "XRAY-SPAWN-001", _codes(report, Severity.ERROR)
        )

    def test_clear_smart_on_actual_giver_still_errors(self) -> None:
        project = self._project_with_giver()
        quest = project.quests["polish_quest"]
        quest.stages[0].on_start_actions = [
            ClearSmart(smart_alias="giver_smart")
        ]
        report = ValidationReport()
        XrayLinter(None, report).validate(project)
        self.assertIn(
            "XRAY-SPAWN-001", _codes(report, Severity.ERROR)
        )

    def test_turnin_phrase_gate_suppresses_dialog_warning(self) -> None:
        gates = [
            [HasInfo(info="polish_ready")],
            [HasItem(item_alias="itm_pda_common")],
        ]
        for gate in gates:
            with self.subTest(gate=gate[0].type):
                dialog = Dialog(
                    id="polish_turnin",
                    role="turnin",
                    task_id="polish_dialog_quest",
                    phrases={
                        0: Phrase(
                            id=0,
                            text_ru="Готов.",
                            text_en="Ready.",
                            next_phrases=[1],
                        ),
                        1: Phrase(
                            id=1,
                            text_ru="Сдаю.",
                            text_en="Turning in.",
                            preconditions=gate,
                        ),
                    },
                )
                quest = Quest(
                    id="polish_dialog_quest",
                    dialog_ids=[dialog.id],
                    stages={0: Stage(id=0)},
                )
                project = ModProject(
                    name="Polish Dialog",
                    mod_slug="polish_dialog",
                    quests={quest.id: quest},
                    dialogs={dialog.id: dialog},
                )
                report = ValidationReport()
                XrayLinter(None, report).validate(project)
                self.assertNotIn(
                    "XRAY-DIALOG-001", _codes(report, Severity.WARNING)
                )


class TestDirectSectionResolution(unittest.TestCase):
    """Прямые секции items/squads и project.squads не дают warning."""

    def test_item_and_squad_sections_resolve_without_warning(self) -> None:
        with GameDatabase(get_default_db_path()) as db:
            rows = db._query("SELECT id FROM squads ORDER BY id LIMIT 1")
            self.assertTrue(rows, "В БД должен быть хотя бы один отряд")
            db_squad_id = str(rows[0]["id"])

            custom = CustomSquad(
                id="polish_custom_squad",
                faction="stalker",
                npc=["sim_default_stalker_0"],
            )
            quest = Quest(
                id="polish_alias_quest",
                reward_item_alias="itm_pda_common",
                stages={
                    0: Stage(id=0, target_squad_id=db_squad_id),
                    1: Stage(id=1, target_squad_id=custom.id),
                },
                transfer_conditions={
                    0: {
                        "complete": [
                            HasItem(item_alias="itm_pda_common")
                        ]
                    }
                },
            )
            project = ModProject(
                name="Polish Aliases",
                mod_slug="polish_aliases",
                quests={quest.id: quest},
                squads={custom.id: custom},
            )

            generator = LuaGenerator(db_client=db)
            with patch.object(lua_gen.logger, "warning") as warning:
                script = generator.generate_quests_script(
                    project,
                    script_name="polish_aliases_quests",
                    mod_prefix="polish_aliases",
                )

        messages = " ".join(str(call) for call in warning.call_args_list)
        self.assertNotIn("не найдена в БД", messages)
        self.assertIn("itm_pda_common", script)
        self.assertIn(db_squad_id, script)
        self.assertIn(custom.id, script)


if __name__ == "__main__":
    unittest.main(verbosity=2)
