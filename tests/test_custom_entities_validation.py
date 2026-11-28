"""Тесты валидации и автоспавна кастомных NPC/отрядов (Фаза 3.5).

Покрываются:

* ``CAT-CUSTOM-*``: ID/префикс, фракция, ``spawn_smart``, шаблоны,
  ``story_id`` бессмертного квестодателя;
* отсутствие ложных ``CAT-NPC-001/002`` и ``CAT-SQUAD-004`` для
  ``CustomNpc.id``;
* ``XRAY-MEET-001`` и ``XRAY-SPAWN-001`` для кастомного квестодателя;
* ``MERGE-ID-001``/``MERGE-NS-001`` для ``project.npcs``;
* solo-отряд ``<npc.id>_solo_squad`` и его спавн в
  ``actor_on_first_update``.

Запуск::

    venv\\Scripts\\python.exe -m unittest tests.test_custom_entities_validation -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from aqm.compiler.builder import ModBuilder  # noqa: E402
from aqm.compiler.ltx_gen import LtxGenerator  # noqa: E402
from aqm.compiler.lua_gen import LuaGenerator  # noqa: E402
from aqm.core.models import (  # noqa: E402
    ClearSmart,
    CustomNpc,
    CustomSquad,
    Dialog,
    ModProject,
    Phrase,
    Quest,
    Stage,
)
from aqm.db.repository import GameDatabase  # noqa: E402
from aqm.paths import get_default_db_path
from aqm.validation import (  # noqa: E402
    CatalogValidator,
    MergeValidator,
    Severity,
    ValidationReport,
    XrayLinter,
)

_DB_PATH = get_default_db_path()

VALID_TEMPLATE = "esc_2_12_stalker_wolf"
VALID_SMART = "esc_smart_terrain_2_12"
OTHER_SMART = "esc_smart_terrain_7_11"
MOD_SLUG = "test_custom"


def _validate(project: ModProject) -> ValidationReport:
    """Запускает ``CatalogValidator`` на реальной БД."""
    report = ValidationReport()
    with GameDatabase(_DB_PATH) as db:
        CatalogValidator(db, report).validate(project)
    return report


def _lint(project: ModProject) -> ValidationReport:
    """Запускает ``XrayLinter`` на реальной БД."""
    report = ValidationReport()
    with GameDatabase(_DB_PATH) as db:
        XrayLinter(db, report).validate(project)
    return report


def _codes(report: ValidationReport, severity: Severity | None = None) -> set[str]:
    """Возвращает коды замечаний (всех или выбранного уровня)."""
    issues = (
        report.issues
        if severity is None
        else [issue for issue in report.issues if issue.severity == severity]
    )
    return {issue.code for issue in issues}


def _custom_npc(**overrides: object) -> CustomNpc:
    """Создаёт валидного кастомного NPC с переопределениями."""
    data: dict[str, object] = {
        "id": "test_custom_envoy",
        "faction": "stalker",
        "template_npc_id": VALID_TEMPLATE,
        "story_id": "test_custom_envoy",
        "spawn_smart": VALID_SMART,
        "name_ru": "Связной",
        "name_en": "Envoy",
    }
    data.update(overrides)
    return CustomNpc(**data)


class CustomEntitiesCatalogTests(unittest.TestCase):
    """Правила ``CAT-CUSTOM-*`` и отсутствие ложных срабатываний."""

    def test_custom_npc_refs_are_accepted(self) -> None:
        npc = _custom_npc()
        quest = Quest(
            id="test_custom_quest",
            npc_id=npc.id,
            giver_npc_id=npc.id,
            npc_location="escape",
            stages={0: Stage(id=0, target_alias=VALID_SMART)},
        )
        dialog = Dialog(
            id="test_custom_dialog",
            npc_id=npc.id,
            npc_location="escape",
            task_id=quest.id,
            phrases={0: Phrase(id=0, text_ru="Привет.")},
        )
        squad = CustomSquad(
            id="test_custom_squad",
            faction="stalker",
            npc=[npc.id],
            npc_in_squad=[1, 1],
            story_id="test_custom_squad",
        )
        report = _validate(
            ModProject(
                name="custom refs",
                mod_slug=MOD_SLUG,
                npcs={npc.id: npc},
                quests={quest.id: quest},
                dialogs={dialog.id: dialog},
                squads={squad.id: squad},
            )
        )
        codes = _codes(report)
        self.assertNotIn("CAT-NPC-001", codes)
        self.assertNotIn("CAT-NPC-002", codes)
        self.assertNotIn("CAT-SQUAD-004", codes)
        self.assertNotIn("CAT-CUSTOM-004", codes)

    def test_id_prefix_and_vanilla_collision(self) -> None:
        npc = _custom_npc(id="wrong_prefix")
        report = _validate(
            ModProject(
                name="wrong prefix",
                mod_slug=MOD_SLUG,
                npcs={npc.id: npc},
            )
        )
        self.assertIn("CAT-CUSTOM-001", _codes(report))

        vanilla = _custom_npc(id="esc_2_12_stalker_wolf")
        report = _validate(
            ModProject(
                name="vanilla collision",
                mod_slug="esc",
                npcs={vanilla.id: vanilla},
            )
        )
        self.assertIn("CAT-CUSTOM-001", _codes(report))

    def test_invalid_faction_and_spawn_smart(self) -> None:
        npc = _custom_npc(faction="no_such_faction", spawn_smart="no_such_smart")
        report = _validate(
            ModProject(
                name="bad custom",
                mod_slug=MOD_SLUG,
                npcs={npc.id: npc},
            )
        )
        codes = _codes(report)
        self.assertIn("CAT-CUSTOM-003", codes)
        self.assertIn("CAT-CUSTOM-008", codes)

    def test_immortal_giver_requires_story_id(self) -> None:
        npc = _custom_npc(immortal=True, story_id=None)
        quest = Quest(
            id="test_custom_quest",
            giver_npc_id=npc.id,
            npc_location="escape",
            stages={0: Stage(id=0)},
        )
        report = _validate(
            ModProject(
                name="immortal giver",
                mod_slug=MOD_SLUG,
                npcs={npc.id: npc},
                quests={quest.id: quest},
            )
        )
        self.assertIn("CAT-CUSTOM-006", _codes(report))

    def test_missing_npc_and_squad_templates(self) -> None:
        npc = _custom_npc(template_npc_id="missing_npc_template")
        squad = CustomSquad(
            id="test_custom_squad",
            faction="stalker",
            template_squad_id="missing_squad_template",
            story_id="test_custom_squad",
        )
        report = _validate(
            ModProject(
                name="missing templates",
                mod_slug=MOD_SLUG,
                npcs={npc.id: npc},
                squads={squad.id: squad},
            )
        )
        codes = _codes(report)
        self.assertIn("CAT-CUSTOM-011", codes)
        self.assertIn("CAT-CUSTOM-012", codes)

    def test_empty_squad_allowed_with_template_id(self) -> None:
        squad = CustomSquad(
            id="test_custom_squad",
            faction="bandit",
            template_squad_id="bandit_sim_squad_advanced",
            story_id="test_custom_squad",
        )
        report = _validate(
            ModProject(
                name="template squad",
                mod_slug=MOD_SLUG,
                squads={squad.id: squad},
            )
        )
        self.assertNotIn("CAT-CUSTOM-004", _codes(report))
        self.assertNotIn("CAT-SQUAD-003", _codes(report))


class CustomEntitiesXrayTests(unittest.TestCase):
    """X-Ray-линтер не ругается на кастомного NPC и его смарт."""

    def test_meet_exemption_and_clear_smart_guard(self) -> None:
        npc = _custom_npc()
        quest = Quest(
            id="test_custom_quest",
            npc_id=npc.id,
            npc_location="escape",
            stages={
                0: Stage(
                    id=0,
                    target_alias=OTHER_SMART,
                    on_start_actions=[
                        ClearSmart(
                            smart_alias=VALID_SMART,
                            faction="stalker",
                        )
                    ],
                )
            },
        )
        dialog = Dialog(
            id="test_custom_dialog",
            npc_id=npc.id,
            npc_location="escape",
            task_id=quest.id,
            phrases={0: Phrase(id=0, text_ru="Привет.")},
        )
        report = _lint(
            ModProject(
                name="xray custom",
                mod_slug=MOD_SLUG,
                npcs={npc.id: npc},
                quests={quest.id: quest},
                dialogs={dialog.id: dialog},
            )
        )
        self.assertNotIn("XRAY-MEET-001", _codes(report))
        self.assertIn("XRAY-SPAWN-001", _codes(report, Severity.ERROR))

        quest.stages[0].on_start_actions = [
            ClearSmart(
                smart_alias=VALID_SMART,
                faction="stalker",
                allow_giver_smart=True,
            )
        ]
        report = _lint(
            ModProject(
                name="xray custom",
                mod_slug=MOD_SLUG,
                npcs={npc.id: npc},
                quests={quest.id: quest},
                dialogs={dialog.id: dialog},
            )
        )
        self.assertNotIn("XRAY-SPAWN-001", _codes(report, Severity.ERROR))


class CustomEntitiesMergeTests(unittest.TestCase):
    """Слияние глав ловит коллизии NPC и префикс пространства имён."""

    def test_npc_collision_and_prefix(self) -> None:
        npc = _custom_npc()
        first = ModProject(
            name="chapter one",
            mod_slug=MOD_SLUG,
            npcs={npc.id: npc},
        )
        second = ModProject(
            name="chapter two",
            mod_slug=MOD_SLUG,
            npcs={npc.id: npc},
        )
        report = ValidationReport()
        MergeValidator(report).validate_chapters(
            [first, second], target_slug=MOD_SLUG
        )
        self.assertIn("MERGE-ID-001", _codes(report))

        bad = _custom_npc(id="no_prefix")
        report = ValidationReport()
        MergeValidator(report).validate_chapters(
            [ModProject(name="bad", mod_slug=MOD_SLUG, npcs={bad.id: bad})],
            target_slug=MOD_SLUG,
        )
        self.assertIn("MERGE-NS-001", _codes(report))


class CustomNpcSpawnTests(unittest.TestCase):
    """Solo-отряд и его Lua-спавн в ``actor_on_first_update``."""

    def _project(self, npcs: dict[str, CustomNpc] | None = None) -> ModProject:
        return ModProject(
            name="spawn custom",
            mod_slug=MOD_SLUG,
            npcs=npcs or {},
            quests={
                "test_custom_quest": Quest(
                    id="test_custom_quest",
                    stages={
                        0: Stage(
                            id=0,
                            target_alias=OTHER_SMART,
                            on_start_actions=[
                                ClearSmart(
                                    smart_alias=OTHER_SMART,
                                    faction="bandit",
                                )
                            ],
                        )
                    },
                )
            },
        )

    def test_solo_squad_section(self) -> None:
        npc = _custom_npc()
        solo = ModBuilder._build_custom_npc_solo_squads({npc.id: npc})
        squad_id = f"{npc.id}_solo_squad"
        self.assertIn(squad_id, solo)
        text = LtxGenerator().generate_squads_ltx(solo)
        self.assertIn(f"[{squad_id}]:online_offline_group", text)
        self.assertIn(f"npc     = {npc.id}", text)
        self.assertIn("npc_in_squad = 1, 1", text)
        self.assertIn(f"target_smart = {VALID_SMART}", text)
        self.assertIn(f"story_id = {squad_id}", text)
        self.assertIn("relationship = friend", text)

    def test_lua_custom_spawn_is_first_update_only(self) -> None:
        npc = _custom_npc()
        lua = LuaGenerator().generate_quests_script(
            self._project({npc.id: npc}),
            script_name="test_quests",
            mod_prefix=MOD_SLUG,
        )
        self.assertIn("local function spawn_custom_npc_squads()", lua)
        self.assertIn(
            "spawn_story_squad(\n\t\t\t\titem.smart, item.section, nil, nil, true",
            lua,
        )
        self.assertIn(
            f"{MOD_SLUG}_npc_{npc.id}_spawned", lua
        )
        self.assertIn(
            f"{npc.id}_solo_squad", lua
        )
        first_update = lua.split(
            'RegisterScriptCallback("actor_on_first_update"', 1
        )[1]
        self.assertIn("spawn_custom_npc_squads()", first_update)
        on_game_start = lua.split("function on_game_start()", 1)[1]
        on_game_start = on_game_start.split("end", 1)[0]
        self.assertNotIn("spawn_custom_npc_squads()", on_game_start)

    def test_lua_without_npcs_has_no_custom_spawn(self) -> None:
        lua = LuaGenerator().generate_quests_script(
            self._project({}), script_name="test_quests", mod_prefix=MOD_SLUG
        )
        self.assertNotIn("spawn_custom_npc_squads", lua)


if __name__ == "__main__":
    unittest.main(verbosity=2)
