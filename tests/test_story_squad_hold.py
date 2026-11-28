"""Тесты удержания Story-отрядов и правила ``XRAY-SPAWN-004``.

Проверяется, что генератор:

* помечает Story-отряд как ``hold``, если у ``CustomSquad`` нет
  ``target_smart`` или он совпадает с точкой спавна;
* не удерживает отряд, которому задан марш на другой смарт;
* вставляет в Lua-хелпер ``spawn_story_squad`` установку ``stay_time`` и
  ``force_online``;
* линтер предупреждает о Story-спавне без ``target_smart``.

Запуск::

    .\\venv\\Scripts\\python.exe -m unittest tests.test_story_squad_hold -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from examples.phase3.phase3_2.test_remove_squad import create_project  # noqa: E402
from aqm.compiler.lua_gen import LuaGenerator  # noqa: E402
from aqm.core.models import CustomSquad, SpawnSquad  # noqa: E402
from aqm.validation.report import ValidationReport  # noqa: E402
from aqm.validation.xray_linter import XrayLinter  # noqa: E402

SPAWN_SMART = "esc_smart_terrain_7_11"
OTHER_SMART = "esc_smart_terrain_2_12"


def _make_squad(target_smart: str | None) -> CustomSquad:
    """Собирает минимальный ``CustomSquad`` для проверки удержания."""
    return CustomSquad(
        id="test_squad",
        faction="monolith",
        npc=["sim_default_monolith_3"],
        npc_in_squad=[1, 1],
        relationship="enemy",
        target_smart=target_smart,
        story_id="test_squad",
    )


class TestStorySquadHoldSpec(unittest.TestCase):
    """Проверяет флаг ``hold`` в спецификации Story-спавна."""

    def test_hold_without_target_smart(self) -> None:
        """Без ``target_smart`` отряд удерживается на точке спавна."""
        spec = LuaGenerator()._action_spec(
            SpawnSquad(
                squad_alias="test_squad",
                smart_alias=SPAWN_SMART,
                mode="story",
            ),
            squads={"test_squad": _make_squad(None)},
        )
        self.assertEqual(spec["kind"], "spawn_story_squad")
        self.assertTrue(spec["hold"])

    def test_hold_when_target_equals_spawn(self) -> None:
        """Совпадение ``target_smart`` и точки спавна означает удержание."""
        spec = LuaGenerator()._action_spec(
            SpawnSquad(
                squad_alias="test_squad",
                smart_alias=SPAWN_SMART,
                mode="story",
            ),
            squads={"test_squad": _make_squad(SPAWN_SMART)},
        )
        self.assertTrue(spec["hold"])

    def test_no_hold_when_target_is_other_smart(self) -> None:
        """Марш на другой смарт не должен блокироваться ``stay_time``."""
        spec = LuaGenerator()._action_spec(
            SpawnSquad(
                squad_alias="test_squad",
                smart_alias=SPAWN_SMART,
                mode="story",
            ),
            squads={"test_squad": _make_squad(OTHER_SMART)},
        )
        self.assertFalse(spec["hold"])


class TestGeneratedStorySquadLua(unittest.TestCase):
    """Проверяет сгенерированный Lua для примера ``test_remove_squad``."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.script = LuaGenerator().generate_quests_script(
            create_project(),
            script_name="test_story_hold_quests",
            mod_prefix="test_story_hold",
        )

    def test_story_spawn_spec_has_hold(self) -> None:
        self.assertIn('kind = "spawn_story_squad"', self.script)
        self.assertIn("hold = true", self.script)

    def test_helper_sets_stay_time_and_force_online(self) -> None:
        self.assertIn(
            "squad.stay_time = game.get_game_time()", self.script
        )
        self.assertIn(
            "pcall(function() squad.force_online = true end)", self.script
        )

    def test_branch_passes_hold_flag(self) -> None:
        self.assertIn("spec.hold", self.script)

    def test_clear_smart_checks_target_binding_fields(self) -> None:
        """Отряд ищется по smart_id и по offline-полям привязки к цели."""
        for field in (
            "smart_id",
            "m_smart_terrain_id",
            "assigned_target_id",
            "current_target_id",
        ):
            with self.subTest(field=field):
                self.assertIn(f"squad.{field} == smart_id", self.script)
        self.assertIn("clear_smart_bound_to(squad, smart.id)", self.script)

    def test_clear_smart_still_drops_stale_smart_squads(self) -> None:
        """После ``remove_squad`` ссылка в ``smart.squads`` очищается."""
        self.assertIn("smart.squads[key] = nil", self.script)


class TestStorySquadLinter(unittest.TestCase):
    """Проверяет ``XRAY-SPAWN-004`` для Story-спавна без ``target_smart``."""

    @staticmethod
    def _report(project) -> str:  # noqa: ANN001 - тестовый помощник
        report = ValidationReport()
        XrayLinter(None, report).validate(project)
        return report.to_text()

    def test_warns_when_target_smart_missing(self) -> None:
        project = create_project()
        squad_id = next(iter(project.squads))
        old = project.squads[squad_id]
        project.squads[squad_id] = CustomSquad(
            id=old.id,
            faction=old.faction,
            npc=old.npc,
            npc_in_squad=old.npc_in_squad,
            relationship=old.relationship,
            story_id=old.story_id,
        )
        self.assertIn("XRAY-SPAWN-004", self._report(project))

    def test_silent_when_target_smart_present(self) -> None:
        self.assertNotIn("XRAY-SPAWN-004", self._report(create_project()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
