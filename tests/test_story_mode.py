"""Тесты Story-режима Фазы 2, итерация 1.

Покрываются:

* новые модели и поля ``TargetVariant``, ``DescrVariant``,
  ``QuestCondlist``, ``RemoveSquad``, ``SpawnSquad.mode``,
  ``Stage.target_variants/descr_variants``,
  ``Quest.fail_on_giver_death/extra_condlists`` и расширенный
  ``CustomSquad``;
* эмиссия ``squad_descr_<slug>.ltx`` с фиксированным порядком полей;
* нумерация и сериализация ``condlist`` в ``tm_<slug>.ltx``;
* варианты описаний этапов в ``st_<mod>.xml``;
* проверки ``ProjectValidator`` для Story-отрядов и смешанных квестов.

Запуск::

    .\\venv\\Scripts\\python.exe -m unittest tests.test_story_mode -v
"""

from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compiler.builder import BuildError  # noqa: E402
from src.compiler.ltx_gen import LtxGenerator  # noqa: E402
from src.compiler.xml_gen import XmlGenerator  # noqa: E402
from src.core.models import (  # noqa: E402
    Action,
    CustomSquad,
    DescrVariant,
    Dialog,
    DontHasInfo,
    HasInfo,
    HasItem,
    HasMoney,
    ModProject,
    Phrase,
    Quest,
    QuestCondlist,
    RemoveSquad,
    SmartOwner,
    SpawnSquad,
    Stage,
    TargetVariant,
    WarfareCapture,
)
from src.core.validator import ProjectValidator  # noqa: E402

QUEST_ID = "mymod_story_quest"
SQUAD_ID = "mymod_story_squad"


class _DummyDatabase:
    """Минимальный двойник базы для runtime-проверок валидатора."""

    def __init__(self, squads: dict[str, dict[str, object]] | None = None):
        self.squads = squads or {}

    def find_squad_by_alias(self, alias: str) -> dict[str, object] | None:
        """Возвращает отряд из подготовленной карты."""
        return self.squads.get(alias)


def _stage(stage_id: int = 0, **kwargs: object) -> Stage:
    """Создаёт минимальный этап с переопределяемыми полями."""
    data: dict[str, object] = {
        "id": stage_id,
        "title_ru": f"Этап {stage_id}",
        "title_en": f"Stage {stage_id}",
        "descr_ru": f"Описание {stage_id}",
        "descr_en": f"Description {stage_id}",
    }
    data.update(kwargs)
    return Stage(**data)  # type: ignore[arg-type]


def _quest(**kwargs: object) -> Quest:
    """Создаёт минимальный валидный квест."""
    data: dict[str, object] = {
        "id": QUEST_ID,
        "title_ru": "Story-квест",
        "title_en": "Story quest",
        "stages": {0: _stage()},
    }
    data.update(kwargs)
    return Quest(**data)  # type: ignore[arg-type]


def _story_squad(squad_id: str = SQUAD_ID, **kwargs: object) -> CustomSquad:
    """Создаёт Story-отряд с разумными значениями по умолчанию."""
    data: dict[str, object] = {
        "id": squad_id,
        "faction": "killer",
        "npc": ["sim_default_killer_1"],
    }
    data.update(kwargs)
    return CustomSquad(**data)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Модели
# ---------------------------------------------------------------------------


class TestStoryModels(unittest.TestCase):
    """Проверка новых моделей и полей Story-режима."""

    def test_target_variant_requires_conditions_and_value(self) -> None:
        """Пустой ``when`` и пустой ``value`` отклоняются."""
        variant = TargetVariant(
            when=[HasInfo(info="mymod_target")],
            value="esc_smart_terrain_1",
        )
        self.assertEqual(variant.value, "esc_smart_terrain_1")

        with self.assertRaises(ValidationError):
            TargetVariant(when=[], value="x")
        with self.assertRaises(ValidationError):
            TargetVariant(when=[HasInfo(info="i")], value="")

    def test_descr_variant_defaults_and_validation(self) -> None:
        """Тексты по умолчанию пусты, а ``when`` обязателен."""
        variant = DescrVariant(when=[DontHasInfo(info="mymod_done")])
        self.assertEqual(variant.text_ru, "")
        self.assertEqual(variant.text_en, "")

        with self.assertRaises(ValidationError):
            DescrVariant(when=[])

    def test_quest_condlist_result_is_literal(self) -> None:
        """``result`` принимает только complete/fail."""
        condlist = QuestCondlist(
            when=[HasInfo(info="mymod_dead")],
            result="complete",
        )
        self.assertEqual(condlist.result, "complete")

        with self.assertRaises(ValidationError):
            QuestCondlist(when=[HasInfo(info="i")], result="unknown")

    def test_remove_squad_is_polymorphic_action(self) -> None:
        """``RemoveSquad`` входит в дискриминируемый union ``Action``."""
        adapter = TypeAdapter(Action)
        action = adapter.validate_python(
            {"type": "remove_squad", "squad_alias": SQUAD_ID}
        )
        self.assertIsInstance(action, RemoveSquad)
        self.assertEqual(action.squad_alias, SQUAD_ID)

    def test_spawn_squad_mode_defaults_to_warfare(self) -> None:
        """Режим по умолчанию — warfare, story принимается."""
        warfare = SpawnSquad(squad_alias="s", smart_alias="p")
        story = SpawnSquad(
            squad_alias="s", smart_alias="p", mode="story"
        )
        self.assertEqual(warfare.mode, "warfare")
        self.assertEqual(story.mode, "story")

        with self.assertRaises(ValidationError):
            SpawnSquad(
                squad_alias="s", smart_alias="p", mode="invalid"
            )

    def test_stage_variants_default_empty_and_roundtrip(self) -> None:
        """Варианты этапа по умолчанию пусты и сохраняются в JSON."""
        self.assertEqual(_stage().target_variants, [])
        self.assertEqual(_stage().descr_variants, [])

        stage = _stage(
            target_variants=[
                TargetVariant(
                    when=[HasInfo(info="mymod_alt")],
                    value="alt_target",
                )
            ],
            descr_variants=[
                DescrVariant(
                    when=[HasInfo(info="mymod_alt")],
                    text_ru="Альтернатива",
                    text_en="Alternative",
                )
            ],
        )
        restored = Stage.model_validate_json(stage.model_dump_json())
        self.assertIsInstance(restored.target_variants[0], TargetVariant)
        self.assertIsInstance(restored.descr_variants[0], DescrVariant)
        self.assertEqual(restored.target_variants[0].value, "alt_target")
        self.assertEqual(restored.descr_variants[0].text_en, "Alternative")

    def test_quest_condlists_fields_roundtrip(self) -> None:
        """``fail_on_giver_death`` и ``extra_condlists`` сохраняются."""
        quest = _quest(
            npc_id="esc_giver",
            fail_on_giver_death=False,
            extra_condlists=[
                QuestCondlist(
                    when=[HasItem(item_alias="itm_pda", count=2)],
                    result="complete",
                )
            ],
        )
        self.assertFalse(quest.fail_on_giver_death)
        self.assertEqual(_quest().fail_on_giver_death, True)
        self.assertEqual(_quest().extra_condlists, [])

        restored = Quest.model_validate_json(quest.model_dump_json())
        self.assertFalse(restored.fail_on_giver_death)
        self.assertIsInstance(restored.extra_condlists[0], QuestCondlist)
        self.assertIsInstance(
            restored.extra_condlists[0].when[0], HasItem
        )

    def test_custom_squad_new_fields_roundtrip(self) -> None:
        """Все новые поля ``CustomSquad`` сериализуются без потерь."""
        squad = _story_squad(
            npc=["sim_default_killer_1", "sim_default_killer_2"],
            npc_random=["sim_default_killer_3"],
            npc_in_squad=[2, 4],
            relationship="enemy",
            idle_time=12.5,
            spawn_point="zat_b52_spawn",
            target_smart="zat_b52",
            story_id=SQUAD_ID,
            death_infos=["mymod_dead_a", "mymod_dead_b"],
        )
        restored = CustomSquad.model_validate_json(squad.model_dump_json())

        self.assertEqual(restored.npc_random, ["sim_default_killer_3"])
        self.assertEqual(restored.npc_in_squad, [2, 4])
        self.assertEqual(restored.relationship, "enemy")
        self.assertEqual(restored.idle_time, 12.5)
        self.assertEqual(restored.spawn_point, "zat_b52_spawn")
        self.assertEqual(
            restored.death_infos, ["mymod_dead_a", "mymod_dead_b"]
        )

    def test_custom_squad_accepts_npc_random_without_npc(self) -> None:
        """Достаточно ``npc_random``; оба пустых списка запрещены."""
        squad = CustomSquad(
            id="random_squad",
            faction="bandit",
            npc_random=["sim_default_bandit_1"],
        )
        self.assertEqual(squad.npc, [])

        with self.assertRaises(ValidationError):
            CustomSquad(id="empty_squad", faction="bandit")

    def test_custom_squad_npc_in_squad_validation(self) -> None:
        """Диапазон ``npc_in_squad``: 0–2 неотрицательных числа, min<=max."""
        self.assertEqual(
            _story_squad(npc_in_squad=[3]).npc_in_squad, [3]
        )
        self.assertEqual(
            _story_squad(npc_in_squad=[1, 5]).npc_in_squad, [1, 5]
        )

        with self.assertRaises(ValidationError):
            _story_squad(npc_in_squad=[1, 2, 3])
        with self.assertRaises(ValidationError):
            _story_squad(npc_in_squad=[-1])
        with self.assertRaises(ValidationError):
            _story_squad(npc_in_squad=[4, 2])


# ---------------------------------------------------------------------------
# LTX: squad_descr
# ---------------------------------------------------------------------------


class TestSquadDescrEmission(unittest.TestCase):
    """Проверка точного текста ``squad_descr_<slug>.ltx``."""

    def setUp(self) -> None:
        self.generator = LtxGenerator()

    def test_full_new_field_order_is_fixed(self) -> None:
        """Новые поля эмитируются в заданном порядке и с точным текстом."""
        squads = {
            SQUAD_ID: _story_squad(
                npc=[
                    "sim_default_killer_1",
                    "sim_default_killer_2",
                ],
                npc_random=["sim_default_killer_3"],
                npc_in_squad=[2, 4],
                relationship="enemy",
                idle_time=12.5,
                spawn_point="zat_b52_spawn",
                target_smart="zat_b52",
                story_id=SQUAD_ID,
                death_infos=[
                    "mymod_merc_dead",
                    "mymod_merc_dead_2",
                ],
            )
        }
        content = self.generator.generate_squads_ltx(squads)
        expected = (
            f"[{SQUAD_ID}]:online_offline_group\n"
            "faction = killer\n"
            "relationship = enemy\n"
            "npc     = sim_default_killer_1, sim_default_killer_2\n"
            "npc_random = sim_default_killer_3\n"
            "npc_in_squad = 2, 4\n"
            "target_smart = zat_b52\n"
            "idle_time = 12.5\n"
            "spawn_point = zat_b52_spawn\n"
            f"story_id = {SQUAD_ID}\n"
            "on_death = %+mymod_merc_dead +mymod_merc_dead_2%\n"
        )
        self.assertEqual(content, expected)

    def test_old_squad_output_is_unchanged(self) -> None:
        """Старая модель без новых полей даёт прежний байт-текст."""
        squads = {
            "mymod_old_squad": CustomSquad(
                id="mymod_old_squad",
                faction="bandit",
                npc=["sim_default_bandit_4"],
                target_smart="esc_smart_terrain_7_11",
                story_id="mymod_old_story",
            )
        }
        content = self.generator.generate_squads_ltx(squads)
        expected = (
            "[mymod_old_squad]:online_offline_group\n"
            "faction = bandit\n"
            "npc     = sim_default_bandit_4\n"
            "target_smart = esc_smart_terrain_7_11\n"
            "story_id = mymod_old_story\n"
        )
        self.assertEqual(content, expected)

    def test_npc_random_only_omits_npc_line(self) -> None:
        """При пустом ``npc`` строка ``npc = ...`` не эмитируется."""
        content = self.generator.generate_squads_ltx(
            {
                "random_squad": CustomSquad(
                    id="random_squad",
                    faction="bandit",
                    npc_random=["sim_default_bandit_1"],
                )
            }
        )
        self.assertNotIn("npc     =", content)
        self.assertIn("npc_random = sim_default_bandit_1", content)

    def test_integral_idle_time_has_no_trailing_zero(self) -> None:
        """Целое ``idle_time`` печатается как ``10``, а не ``10.0``."""
        content = self.generator.generate_squads_ltx(
            {SQUAD_ID: _story_squad(idle_time=10)}
        )
        self.assertIn("idle_time = 10\n", content)


# ---------------------------------------------------------------------------
# LTX: condlist
# ---------------------------------------------------------------------------


class TestQuestCondlists(unittest.TestCase):
    """Проверка нумерации и сериализации ``condlist_N``."""

    def setUp(self) -> None:
        self.generator = LtxGenerator()

    def _content(
        self,
        *,
        giver: str | None = "esc_giver",
        fail_on_giver_death: bool = True,
        extra: list[QuestCondlist] | None = None,
    ) -> str:
        quest = _quest(
            npc_id=giver,
            fail_on_giver_death=fail_on_giver_death,
            extra_condlists=list(extra or []),
        )
        return self.generator.generate_tasks_ltx({QUEST_ID: quest})

    def test_auto_fail_is_condlist_0_and_extras_follow(self) -> None:
        """После авто-провала дополнительные condlist начинаются с 1."""
        content = self._content(
            extra=[
                QuestCondlist(
                    when=[HasInfo(info="mymod_merc_dead")],
                    result="complete",
                ),
                QuestCondlist(
                    when=[DontHasInfo(info="mymod_relay_ok")],
                    result="fail",
                ),
            ]
        )
        self.assertIn(
            f"condlist_0            = "
            f"{{!task_giver_alive({QUEST_ID})}} fail",
            content,
        )
        self.assertIn(
            "condlist_1            = {+mymod_merc_dead} complete",
            content,
        )
        self.assertIn(
            "condlist_2            = {-mymod_relay_ok} fail",
            content,
        )

    def test_disabled_auto_fail_starts_extras_at_zero(self) -> None:
        """При ``fail_on_giver_death=False`` первый extra — condlist_0."""
        content = self._content(
            fail_on_giver_death=False,
            extra=[
                QuestCondlist(
                    when=[HasInfo(info="mymod_merc_dead")],
                    result="complete",
                )
            ],
        )
        self.assertNotIn("task_giver_alive", content)
        self.assertIn(
            "condlist_0            = {+mymod_merc_dead} complete",
            content,
        )

    def test_disabled_auto_fail_without_extras_has_no_condlists(self) -> None:
        """Без авто-провала и extras блок ``condlist_*`` не эмитится."""
        content = self._content(fail_on_giver_death=False)
        self.assertNotIn("condlist_", content)

    def test_has_item_count_one_uses_actor_has_item(self) -> None:
        """``HasItem(count=1)`` -> ``actor_has_item(section)``."""
        content = self._content(
            extra=[
                QuestCondlist(
                    when=[HasItem(item_alias="itm_pda_common")],
                    result="complete",
                )
            ]
        )
        self.assertIn(
            "condlist_1            = "
            "{=actor_has_item(itm_pda_common)} complete",
            content,
        )

    def test_has_item_count_above_one_uses_amount(self) -> None:
        """``HasItem(count>1)`` -> ``actor_has_item_amount(section:count)``."""
        content = self._content(
            extra=[
                QuestCondlist(
                    when=[HasItem(item_alias="itm_pda_common", count=3)],
                    result="complete",
                )
            ]
        )
        self.assertIn(
            "condlist_1            = "
            "{=actor_has_item_amount(itm_pda_common:3)} complete",
            content,
        )

    def test_has_money_raises_build_error(self) -> None:
        """``HasMoney`` в condlist даёт ``BuildError`` и не глотается."""
        with self.assertRaises(BuildError) as context:
            self._content(
                extra=[
                    QuestCondlist(
                        when=[HasMoney(amount=50000)],
                        result="complete",
                    )
                ]
            )
        self.assertIn("HasMoney", str(context.exception))

    def test_smart_owner_raises_build_error(self) -> None:
        """``SmartOwner`` в condlist также не поддерживается в Фазе 2."""
        with self.assertRaises(BuildError):
            self._content(
                extra=[
                    QuestCondlist(
                        when=[
                            SmartOwner(
                                smart_alias="esc_smart",
                                faction="army",
                            )
                        ],
                        result="fail",
                    )
                ]
            )


# ---------------------------------------------------------------------------
# XML: варианты описаний
# ---------------------------------------------------------------------------


class TestXmlDescrVariants(unittest.TestCase):
    """Проверка строк ``_stage_<id>_descr_vN`` в rus/eng."""

    @staticmethod
    def _strings(xml: str) -> dict[str, str]:
        root = ET.fromstring(xml)
        return {
            element.get("id", ""): element.findtext("text", "")
            for element in root.findall("string")
        }

    def test_variants_are_added_in_declaration_order(self) -> None:
        """Варианты получают стабильные индексы и правильные тексты."""
        quest = _quest(
            stages={
                0: _stage(
                    descr_variants=[
                        DescrVariant(
                            when=[HasInfo(info="mymod_a")],
                            text_ru="Вариант А",
                            text_en="Variant A",
                        ),
                        DescrVariant(
                            when=[HasInfo(info="mymod_b")],
                            text_ru="Вариант Б",
                            text_en="Variant B",
                        ),
                    ]
                )
            }
        )
        project = ModProject(name="XML variants", quests={QUEST_ID: quest})
        tables = XmlGenerator().generate_string_tables(project)
        rus = self._strings(tables["rus"])
        eng = self._strings(tables["eng"])

        prefix = f"{QUEST_ID}_stage_0_descr"
        self.assertEqual(rus[f"{prefix}_v1"], "Вариант А")
        self.assertEqual(rus[f"{prefix}_v2"], "Вариант Б")
        self.assertEqual(eng[f"{prefix}_v1"], "Variant A")
        self.assertEqual(eng[f"{prefix}_v2"], "Variant B")

    def test_no_variants_means_no_new_keys(self) -> None:
        """При пустом ``descr_variants`` ключи ``_vN`` не появляются."""
        project = ModProject(
            name="No variants", quests={QUEST_ID: _quest()}
        )
        tables = XmlGenerator().generate_string_tables(project)
        for language in ("rus", "eng"):
            ids = set(self._strings(tables[language]))
            self.assertFalse(
                any("_descr_v" in entry_id for entry_id in ids),
                ids,
            )


# ---------------------------------------------------------------------------
# Валидатор
# ---------------------------------------------------------------------------


class TestStoryValidator(unittest.TestCase):
    """Проверка G12 и запрета смешанных квестов."""

    def _validate(self, project: ModProject, db=None) -> bool:
        return ProjectValidator(db or _DummyDatabase()).validate_project(
            project
        )

    def _valid_story_project(self) -> ModProject:
        squad = _story_squad(story_id=SQUAD_ID)
        quest = _quest(
            on_init_actions=[
                SpawnSquad(
                    squad_alias=SQUAD_ID,
                    smart_alias="zat_b52",
                    mode="story",
                )
            ]
        )
        return ModProject(
            name="Story",
            quests={QUEST_ID: quest},
            squads={SQUAD_ID: squad},
        )

    def test_valid_story_project_passes(self) -> None:
        """Корректный Story-проект валиден."""
        self.assertTrue(self._validate(self._valid_story_project()))

    def test_mixed_quest_is_invalid(self) -> None:
        """warfare_capture + SpawnSquad(story) в одном квесте — ошибка."""
        squad = _story_squad(story_id=SQUAD_ID)
        quest = _quest(
            on_init_actions=[
                SpawnSquad(
                    squad_alias=SQUAD_ID,
                    smart_alias="zat_b52",
                    mode="story",
                )
            ],
            stages={
                0: _stage(
                    warfare_capture=WarfareCapture(
                        smart_alias="zat_b52",
                        enemy_squad_alias="bandit_squad",
                    )
                )
            },
        )
        project = ModProject(
            name="Mixed",
            quests={QUEST_ID: quest},
            squads={SQUAD_ID: squad},
        )
        self.assertFalse(self._validate(project))

    def test_duplicate_story_id_is_invalid(self) -> None:
        """Два отряда с одинаковым ``story_id`` запрещены."""
        first = _story_squad("squad_a", story_id="shared_story")
        second = _story_squad("squad_b", story_id="shared_story")
        project = ModProject(
            name="Duplicates",
            squads={"squad_a": first, "squad_b": second},
        )
        self.assertFalse(self._validate(project))

    def test_empty_death_info_is_invalid(self) -> None:
        """Пустая строка в ``death_infos`` — ошибка валидации."""
        squad = _story_squad(
            story_id=SQUAD_ID, death_infos=["mymod_dead", "  "]
        )
        project = ModProject(
            name="Death infos", squads={SQUAD_ID: squad}
        )
        self.assertFalse(self._validate(project))

    def test_missing_story_spawn_squad_is_invalid(self) -> None:
        """Story-спавн на отсутствующий отряд отклоняется."""
        quest = _quest(
            on_init_actions=[
                SpawnSquad(
                    squad_alias="missing_squad",
                    smart_alias="zat_b52",
                    mode="story",
                )
            ]
        )
        project = ModProject(name="Missing", quests={QUEST_ID: quest})
        self.assertFalse(self._validate(project))

    def test_missing_remove_squad_is_invalid(self) -> None:
        """``RemoveSquad`` на отсутствующий отряд отклоняется."""
        quest = _quest(
            on_fail_actions=[RemoveSquad(squad_alias="missing_squad")]
        )
        project = ModProject(name="Remove", quests={QUEST_ID: quest})
        self.assertFalse(self._validate(project))

    def test_squad_can_be_resolved_through_database(self) -> None:
        """Ванильный отряд, найденный в БД, считается существующим."""
        quest = _quest(
            on_init_actions=[
                SpawnSquad(
                    squad_alias="vanilla_story_squad",
                    smart_alias="zat_b52",
                    mode="story",
                )
            ]
        )
        project = ModProject(name="DB", quests={QUEST_ID: quest})
        db = _DummyDatabase(
            {"vanilla_story_squad": {"id": "vanilla_story_squad"}}
        )
        self.assertTrue(self._validate(project, db))

    def test_remove_squad_existing_alias_passes(self) -> None:
        """``RemoveSquad`` на отряд проекта проходит проверку."""
        squad = _story_squad(story_id=SQUAD_ID)
        quest = _quest(
            on_fail_actions=[RemoveSquad(squad_alias=SQUAD_ID)]
        )
        project = ModProject(
            name="Remove OK",
            quests={QUEST_ID: quest},
            squads={SQUAD_ID: squad},
        )
        self.assertTrue(self._validate(project))


if __name__ == "__main__":
    unittest.main(verbosity=2)
