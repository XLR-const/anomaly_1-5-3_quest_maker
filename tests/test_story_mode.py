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

import importlib.util
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType

from pydantic import TypeAdapter, ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compiler.builder import BuildError, ModBuilder  # noqa: E402
from src.compiler.ltx_gen import LtxGenerator  # noqa: E402
from src.compiler.lua_gen import LuaGenerator  # noqa: E402
from src.compiler.xml_gen import XmlGenerator  # noqa: E402
from src.core.models import (  # noqa: E402
    Action,
    CustomSquad,
    DescrVariant,
    Dialog,
    DontHasInfo,
    GiveTask,
    HasInfo,
    HasItem,
    HasMoney,
    ModProject,
    Phrase,
    Quest,
    QuestCondlist,
    RemoveItem,
    RemoveSquad,
    SmartOwner,
    SpawnNpcItem,
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

    def test_spawn_npc_item_model_and_union(self) -> None:
        """``SpawnNpcItem`` входит в union, ``count`` ограничен снизу."""
        action = SpawnNpcItem(
            item_alias="itm_pda_common",
            target_alias=SQUAD_ID,
        )
        self.assertEqual(action.type, "spawn_npc_item")
        self.assertEqual(action.count, 1)

        adapter = TypeAdapter(Action)
        parsed = adapter.validate_python(
            {
                "type": "spawn_npc_item",
                "item_alias": "itm_pda_common",
                "target_alias": SQUAD_ID,
                "count": 2,
            }
        )
        self.assertIsInstance(parsed, SpawnNpcItem)
        self.assertEqual(parsed.count, 2)
        self.assertEqual(parsed.target_alias, SQUAD_ID)

        with self.assertRaises(ValidationError):
            SpawnNpcItem(
                item_alias="itm_pda_common",
                target_alias=SQUAD_ID,
                count=0,
            )

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


# ---------------------------------------------------------------------------
# Lua: Story-рантайм
# ---------------------------------------------------------------------------


class TestStoryLuaRuntime(unittest.TestCase):
    """Проверяет условную генерацию Story-фрагментов в Lua-рантайме."""

    @staticmethod
    def _build(**quest_kwargs: object) -> str:
        """Собирает Lua-скрипт одного Story-квеста в памяти."""
        quest = _quest(**quest_kwargs)
        project = ModProject(
            name="Story runtime",
            quests={QUEST_ID: quest},
            squads={SQUAD_ID: _story_squad(story_id=SQUAD_ID)},
        )
        return LuaGenerator().generate_quests_script(
            project,
            script_name="st_story_test",
            mod_prefix="mymod",
        )

    @staticmethod
    def _function_body(script: str, header: str, next_header: str) -> str:
        """Возвращает текст функции от ``header`` до ``next_header``."""
        start = script.index(header)
        end = script.index(next_header, start + len(header))
        return script[start:end]

    def test_spawn_story_squad_avoids_warfare_api(self) -> None:
        """Story-спавн не трогает ``sim_squad_warfare`` и не ставит таймеры."""
        script = self._build(
            on_init_actions=[
                SpawnSquad(
                    squad_alias=SQUAD_ID,
                    smart_alias="zat_b52",
                    mode="story",
                )
            ]
        )
        body = self._function_body(
            script,
            "local function spawn_story_squad",
            "local function remove_story_squad",
        )

        self.assertIn("SIMBOARD:create_squad(base, section)", body)
        self.assertIn("mark_task_squad(squad)", body)
        self.assertIn("register_story_squad(quest_id, squad)", body)
        self.assertNotIn("sim_squad_warfare", body)
        self.assertNotIn("set_target", body)
        self.assertNotIn("stay_time", body)
        self.assertNotIn("force_online", body)

    def test_spawn_story_squad_is_idempotent_and_resets(self) -> None:
        """Спавн защищён ``once_key`` и сбрасывается при отмене/повторе."""
        script = self._build(
            on_init_actions=[
                SpawnSquad(
                    squad_alias=SQUAD_ID,
                    smart_alias="zat_b52",
                    mode="story",
                )
            ],
            stages={
                0: _stage(
                    on_start_actions=[
                        SpawnSquad(
                            squad_alias=SQUAD_ID,
                            smart_alias="zat_b52",
                            mode="story",
                        )
                    ]
                )
            },
        )
        spawn_body = self._function_body(
            script,
            "local function spawn_story_squad",
            "local function remove_story_squad",
        )
        self.assertIn(
            "if once_key and vget(once_key, 0) == 1 then", spawn_body
        )
        self.assertIn("vset(once_key, 1)", spawn_body)

        self.assertIn(
            'stage_key(quest, stage_idx, "story_spawn")', script
        )
        self.assertIn('quest.key_prefix .. "_init_spawn"', script)

        unmark_body = self._function_body(
            script,
            "local function unmark_quest_squads",
            "-- Remembers a squad",
        )
        self.assertIn('"_story_squad_cnt"', unmark_body)
        self.assertIn('"_init_spawn"', unmark_body)

        start_body = self._function_body(
            script,
            f"local function {QUEST_ID}_start",
            f"local function {QUEST_ID}_reward",
        )
        self.assertIn(
            'vset(stage_key(quest, stage, "story_spawn"), 0)', start_body
        )

    def test_remove_squad_is_safe_noop_and_clears_story_list(self) -> None:
        """``RemoveSquad`` использует Story-API и переносит ``nil``."""
        script = self._build(
            on_fail_actions=[RemoveSquad(squad_alias=SQUAD_ID)]
        )
        self.assertIn('kind = "remove_squad"', script)
        self.assertIn("remove_story_squad(spec.squad)", script)

        remove_body = self._function_body(
            script,
            "local function remove_story_squad",
            "-- Executes a list of serialized action specs",
        )
        self.assertIn(
            'if not alias_or_section or alias_or_section == "" then '
            "return end",
            remove_body,
        )
        self.assertIn("get_story_squad(alias_or_section)", remove_body)
        self.assertIn("SIMBOARD.remove_squad", remove_body)
        self.assertIn("if squad and SIMBOARD", remove_body)

        unmark_body = self._function_body(
            script,
            "local function unmark_quest_squads",
            "-- Remembers a squad",
        )
        self.assertIn('"_story_squad_" .. tostring(i)', unmark_body)
        self.assertIn("unmark_task_squad(", unmark_body)
        self.assertIn('"_story_squad_cnt"', unmark_body)

    def test_freeze_dyn_squads_ignores_story_list(self) -> None:
        """``freeze_dyn_squads`` читает только ``_dyn_squad_*``."""
        script = self._build(
            on_init_actions=[
                SpawnSquad(
                    squad_alias=SQUAD_ID,
                    smart_alias="zat_b52",
                    mode="story",
                )
            ]
        )
        body = self._function_body(
            script,
            "local function freeze_dyn_squads",
            "-- A stage with capture data",
        )
        self.assertIn('"_dyn_squad_"', body)
        self.assertNotIn("_story_squad_", body)

    def test_variants_are_emitted_only_when_present(self) -> None:
        """Проверки вариантов появляются в ``_target``/``_descr``."""
        script = self._build(
            stages={
                0: _stage(
                    target_variants=[
                        TargetVariant(
                            when=[HasInfo(info="mymod_alt")],
                            value="alt_smart",
                        )
                    ],
                    descr_variants=[
                        DescrVariant(
                            when=[HasInfo(info="mymod_alt")],
                            text_ru="Вариант",
                            text_en="Variant",
                        )
                    ],
                )
            }
        )
        target_body = self._function_body(
            script,
            f"local function {QUEST_ID}_target",
            f"local function {QUEST_ID}_descr",
        )
        self.assertIn("stage_data.target_variants", target_body)
        self.assertIn("eval_conditions(var.when, db.actor)", target_body)
        self.assertIn("resolve_target(var.value)", target_body)

        descr_body = self._function_body(
            script,
            f"local function {QUEST_ID}_descr",
            f"local function {QUEST_ID}_status",
        )
        self.assertIn("stage_data.descr_variants", descr_body)
        self.assertIn("return var.key", descr_body)

        self.assertIn(f"{QUEST_ID}_stage_0_descr_v1", script)

    def test_no_variants_means_no_variant_blocks(self) -> None:
        """Без вариантов ``_target``/``_descr`` остаются прежними."""
        script = self._build()
        target_body = self._function_body(
            script,
            f"local function {QUEST_ID}_target",
            f"local function {QUEST_ID}_descr",
        )
        descr_body = self._function_body(
            script,
            f"local function {QUEST_ID}_descr",
            f"local function {QUEST_ID}_status",
        )
        for body in (target_body, descr_body):
            self.assertNotIn("target_variants", body)
            self.assertNotIn("descr_variants", body)
            self.assertNotIn("var.when", body)

    def test_spawn_npc_item_helper_and_branch(self) -> None:
        """``SpawnNpcItem`` вставляет хелпер и ветку в ``run_actions``."""
        script = self._build(
            stages={
                0: _stage(
                    on_start_actions=[
                        SpawnNpcItem(
                            item_alias="itm_pda_common",
                            target_alias=SQUAD_ID,
                        )
                    ]
                )
            }
        )
        self.assertIn('kind = "spawn_npc_item"', script)
        self.assertIn('item = "itm_pda_common"', script)
        self.assertIn(f'target = "{SQUAD_ID}"', script)
        self.assertIn("count = 1", script)
        self.assertIn(
            "spawn_npc_item(spec.item, spec.target, spec.count)", script
        )

        body = self._function_body(
            script,
            "local function spawn_npc_item",
            "-- Executes a list of serialized action specs",
        )
        # Резолв NPC напрямую и через Story-отряд.
        self.assertIn("resolve_alife_object(target_name)", body)
        self.assertIn("get_story_squad(target_name)", body)
        # Для отряда предмет кладётся в инвентарь командира.
        self.assertIn("if obj.commander_id then", body)
        self.assertIn("local cmd_id = obj:commander_id()", body)
        self.assertIn("alife_object(cmd_id)", body)
        # Создание предмета защищено и возвращает статус успеха.
        self.assertIn("alife_create_item(section, obj)", body)
        self.assertIn("if not (ok and se_item) then", body)
        self.assertIn("return false", body)
        self.assertIn("return true", body)
        self.assertNotIn("news_manager", body)
        self.assertNotIn("sim_squad_warfare", body)

    def test_spawn_npc_item_retries_on_later_status_ticks(self) -> None:
        """Неудачный ``SpawnNpcItem`` повторяется по ``npc_item_done``."""
        script = self._build(
            stages={
                0: _stage(
                    on_start_actions=[
                        SpawnSquad(
                            squad_alias=SQUAD_ID,
                            smart_alias="zat_b52",
                            mode="story",
                        ),
                        SpawnNpcItem(
                            item_alias="itm_pda_common",
                            target_alias=SQUAD_ID,
                        ),
                    ]
                )
            }
        )
        status_body = self._function_body(
            script,
            f"local function {QUEST_ID}_status",
            f"local function {QUEST_ID}_start",
        )
        self.assertIn('stage_data.npc_item_actions or {}', status_body)
        self.assertIn('"npc_item_done"', status_body)
        self.assertIn(
            "spawn_npc_item(item_spec.item, item_spec.target, "
            "item_spec.count)",
            status_body,
        )
        self.assertLess(
            status_body.index("npc_items_done = false"),
            status_body.index('vset(stage_key(quest, stage, "npc_item_done"), 1)'),
        )

        start_body = self._function_body(
            script,
            f"local function {QUEST_ID}_start",
            f"local function {QUEST_ID}_reward",
        )
        self.assertIn('vset(stage_key(quest, stage, "npc_item_done"), 0)', start_body)
        self.assertIn('"npc_item_done_" .. tostring(i)', start_body)

    def test_turn_in_last_stage_gate_is_unconditional(self) -> None:
        """Гейт ``last_stage`` работает и при собственном ``HasInfo``."""
        quest = _quest(
            stages={0: _stage(0), 1: _stage(1)},
        )
        take = Dialog(
            id="mymod_gate_take",
            task_id=QUEST_ID,
            role="take",
            phrases={
                0: Phrase(id=0, text_ru="Взять", text_en="Take"),
            },
        )
        turnin = Dialog(
            id="mymod_gate_turnin",
            task_id=QUEST_ID,
            role="turnin",
            preconditions=[HasInfo(info="mymod_gate_taken")],
            phrases={
                0: Phrase(id=0, text_ru="Сдать", text_en="Turn in"),
            },
        )
        project = ModProject(
            name="Gate runtime",
            quests={QUEST_ID: quest},
            dialogs={take.id: take, turnin.id: turnin},
        )
        script = LuaGenerator().generate_quests_script(
            project,
            script_name="st_gate_test",
            mod_prefix="mymod",
        )
        body = self._function_body(
            script,
            "local function mymod_gate_turnin_can_turn_in",
            "local function mymod_gate_turnin_accept",
        )
        self.assertIn(
            "if quest.return_stage < 0 and "
            "(tsk.stage or 0) < (quest.last_stage or 0) then",
            body,
        )
        self.assertIn("return false", body)
        self.assertLess(
            body.index("(quest.last_stage or 0)"),
            body.rindex("return true"),
        )

    def test_spawn_npc_item_absent_without_action(self) -> None:
        """Без ``SpawnNpcItem`` хелпер и ветка не генерируются."""
        script = self._build()
        self.assertNotIn("spawn_npc_item", script)

    def test_warfare_project_keeps_old_runtime(self) -> None:
        """Warfare-проект не получает Story-фрагментов и аргумента stage."""
        quest = _quest(
            on_init_actions=[
                SpawnSquad(squad_alias=SQUAD_ID, smart_alias="zat_b52")
            ]
        )
        project = ModProject(
            name="Warfare runtime",
            quests={QUEST_ID: quest},
            squads={SQUAD_ID: _story_squad()},
        )
        script = LuaGenerator().generate_quests_script(
            project,
            script_name="st_warfare_test",
            mod_prefix="mymod",
        )

        self.assertIn(
            "local function run_actions(actions, actor, npc, quest_id)",
            script,
        )
        self.assertIn("sim_squad_warfare.set_target", script)
        self.assertIn("squad.stay_time = nil", script)
        for marker in (
            "spawn_story_squad",
            "register_story_squad",
            "remove_story_squad",
            "_story_squad_",
        ):
            self.assertNotIn(marker, script)

    def test_give_task_from_reward_handles_nil_npc(self) -> None:
        """``GiveTask`` из ``on_complete_actions`` не падает без ``npc``."""
        script = self._build(
            on_complete_actions=[GiveTask(task_id="mymod_next_quest")]
        )
        self.assertIn('kind = "give_task"', script)

        reward_body = self._function_body(
            script,
            f"local function {QUEST_ID}_reward",
            f"local function {QUEST_ID}_cleanup",
        )
        self.assertIn(
            "run_actions(quest.complete_actions, actor or db.actor, npc",
            reward_body,
        )

        give_body = self._function_body(
            script,
            "local function give_task",
            "local function complete_task",
        )
        self.assertIn("if npc and npc.id", give_body)
        self.assertIn("if not giver_id then", give_body)


# ---------------------------------------------------------------------------
# Интеграция: сборка эталонного проекта «Последний ретранслятор»
# ---------------------------------------------------------------------------


class TestStoryRelayIntegration(unittest.TestCase):
    """Собирает ``examples/build_story_relay.py`` во временную директорию."""

    @staticmethod
    def _load_example() -> ModuleType:
        """Загружает эталонный сценарий как отдельный модуль."""
        path = PROJECT_ROOT / "examples" / "build_story_relay.py"
        spec = importlib.util.spec_from_file_location(
            "build_story_relay_example", path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Не удалось загрузить {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _function_body(script: str, header: str, next_header: str) -> str:
        """Возвращает тело функции от ``header`` до ``next_header``."""
        start = script.index(header)
        end = script.index(next_header, start + len(header))
        return script[start:end]

    @staticmethod
    def _write_fake_vanilla(root: Path) -> None:
        """Создаёт минимальное fake-дерево ванильной игры для сборщика."""
        configs = root / "configs"
        gameplay = configs / "gameplay"
        gameplay.mkdir(parents=True)
        (configs / "system.ltx").write_text(
            "[dialogs]\n"
            "files = dialogs, dialogs_zaton\n"
            "\n"
            "[profiles]\n"
            "specific_characters_files = character_desc_general, "
            "character_desc_zaton\n",
            encoding="cp1251",
        )
        (gameplay / "character_desc_zaton.xml").write_text(
            '<?xml version="1.0" encoding="windows-1251"?>\n'
            "<specific_characters>\n"
            '    <specific_character id="zat_a2_stalker_barmen">\n'
            "        <name>Борода</name>\n"
            "    </specific_character>\n"
            "</specific_characters>\n",
            encoding="cp1251",
        )

    def test_example_builds_all_story_artifacts(self) -> None:
        """Валидация, сборка и проверка двухэтапной Story-цепочки."""
        module = self._load_example()
        project = module.build_project()

        self.assertEqual(
            (project.model_extra or {}).get("mod_slug"), "last_relay"
        )
        self.assertEqual(
            set(project.quests),
            {"mymod_relay_01_silence", "mymod_relay_02_decryptor"},
        )

        first = project.quests["mymod_relay_01_silence"]
        second = project.quests["mymod_relay_02_decryptor"]

        # Оба квеста — настоящие многоэтапные звенья цепочки.
        self.assertEqual(len(first.stages), 2)
        self.assertEqual(len(second.stages), 2)
        self.assertEqual(first.stages[0].target_squad_id,
                         "mymod_relay_merc_squad")
        self.assertEqual(len(first.stages[0].target_variants), 1)
        self.assertEqual(
            first.stages[0].target_variants[0].value,
            "zat_a2_stalker_barmen",
        )
        self.assertEqual(len(second.stages[0].descr_variants), 1)
        self.assertIsInstance(
            first.transfer_conditions[0]["complete"][0], HasInfo
        )
        self.assertIsInstance(
            second.transfer_conditions[0]["complete"][0], HasItem
        )
        self.assertEqual(first.cleanup_infos, ["mymod_relay_merc_dead"])
        self.assertEqual(second.cleanup_infos, ["mymod_relay_guard_dead"])
        self.assertEqual(first.reward_money, 5000)
        self.assertEqual(second.reward_money, 12000)
        self.assertEqual(second.reward_item_alias, "wpn_vintorez")

        # Два Story-отряда, у каждого — свой on_death.
        self.assertEqual(len(project.squads), 2)
        self.assertEqual(
            project.squads["mymod_relay_merc_squad"].death_infos,
            ["mymod_relay_merc_dead"],
        )
        self.assertEqual(
            project.squads["mymod_relay_guard_squad"].death_infos,
            ["mymod_relay_guard_dead"],
        )
        for squad in project.squads.values():
            self.assertEqual(squad.relationship, "enemy")
            self.assertEqual(squad.story_id, squad.id)

        # Q2 stage 0 сначала спавнит охрану, затем кладёт шифратор
        # в рюкзак её командира.
        q2_start_actions = second.stages[0].on_start_actions
        self.assertEqual(len(q2_start_actions), 2)
        self.assertIsInstance(q2_start_actions[0], SpawnSquad)
        self.assertIsInstance(q2_start_actions[1], SpawnNpcItem)
        looter = q2_start_actions[1]
        self.assertEqual(looter.item_alias, "itm_pda_common")
        self.assertEqual(looter.target_alias, "mymod_relay_guard_squad")
        self.assertEqual(looter.count, 1)

        # WARN-1: при отмене Q2 уже подобранный ПДА изымается, чтобы
        # повторное взятие не закрыло этап 0 мгновенно.
        self.assertEqual(len(second.on_fail_actions), 2)
        self.assertIsInstance(second.on_fail_actions[0], RemoveItem)
        self.assertEqual(
            second.on_fail_actions[0].item_alias, "itm_pda_common"
        )
        self.assertEqual(second.on_fail_actions[0].count, 1)
        self.assertIsInstance(second.on_fail_actions[1], RemoveSquad)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vanilla = root / "vanilla"
            self._write_fake_vanilla(vanilla)

            self.assertTrue(
                ProjectValidator(_DummyDatabase()).validate_project(project),
                "Эталонный Story-проект не прошёл валидацию.",
            )

            builder = ModBuilder(
                output_dir=root / "output",
                vanilla_root=vanilla,
            )
            self.assertTrue(
                builder.build_project(project),
                "Сборка эталонного Story-проекта не удалась.",
            )

            mod_root = root / "output" / "last_relay"
            gamedata = mod_root / "gamedata"
            expected_files = [
                "configs/misc/task/tm_last_relay.ltx",
                "configs/misc/squad_descr/squad_descr_last_relay.ltx",
                "configs/gameplay/dialogs_last_relay.xml",
                "configs/gameplay/character_desc_zaton.xml",
                "configs/text/rus/st_last_relay.xml",
                "configs/text/eng/st_last_relay.xml",
                "scripts/last_relay_quests.script",
            ]
            for relative in expected_files:
                self.assertTrue(
                    (gamedata / relative).is_file(),
                    f"Не найден артефакт: {relative}",
                )

            squad_ltx = (
                gamedata
                / "configs"
                / "misc"
                / "squad_descr"
                / "squad_descr_last_relay.ltx"
            ).read_text(encoding="cp1251")
            self.assertEqual(squad_ltx.count("on_death ="), 2)
            self.assertIn(
                "on_death = %+mymod_relay_merc_dead%", squad_ltx
            )
            self.assertIn(
                "on_death = %+mymod_relay_guard_dead%", squad_ltx
            )
            self.assertIn("target_smart = zat_b52", squad_ltx)
            self.assertIn(
                "target_smart = zat_b14_smart_terrain", squad_ltx
            )
            # Спавн не должен происходить на Скадовске.
            self.assertNotIn("zat_stalker_base_smart", squad_ltx)

            lua = (
                gamedata / "scripts" / "last_relay_quests.script"
            ).read_text(encoding="cp1251")
            # Story-спавн вызывается ровно для двух отрядов.
            self.assertEqual(lua.count('kind = "spawn_story_squad"'), 2)
            self.assertNotIn('kind = "spawn_squad"', lua)
            self.assertNotIn('kind = "set_target"', lua)

            # Шифратор спавнится в инвентарь командира охраны Q2.
            self.assertEqual(lua.count('kind = "spawn_npc_item"'), 1)
            guard_block_start = lua.index('kind = "spawn_npc_item"')
            guard_block = lua[guard_block_start:guard_block_start + 200]
            self.assertIn('item = "itm_pda_common"', guard_block)
            self.assertIn(
                'target = "mymod_relay_guard_squad"', guard_block
            )
            self.assertIn("count = 1", guard_block)

            npc_item_helper = self._function_body(
                lua,
                "local function spawn_npc_item",
                "-- Executes a list of serialized action specs",
            )
            self.assertIn(
                "local cmd_id = obj:commander_id()", npc_item_helper
            )
            self.assertIn(
                "alife_object(cmd_id)", npc_item_helper
            )
            self.assertIn(
                "alife_create_item(section, obj)", npc_item_helper
            )
            self.assertIn(
                "get_story_squad(target_name)", npc_item_helper
            )
            self.assertNotIn("news_manager", npc_item_helper)

            # Story-функция спавна не обращается к Warfare-симуляции.
            story_spawn = self._function_body(
                lua,
                "local function spawn_story_squad",
                "local function remove_story_squad",
            )
            self.assertNotIn("sim_squad_warfare", story_spawn)

            # Общий Warfare-хелпер остаётся в шаблоне для обратной
            # совместимости, но Story-путь не должен к нему обращаться.
            warfare_helper = self._function_body(
                lua,
                "local function spawn_task_squad",
                "local function freeze_squad",
            )
            self.assertIn("sim_squad_warfare", warfare_helper)
            story_path = "\n".join(
                line
                for line in lua.replace(warfare_helper, "").splitlines()
                if not line.lstrip().startswith("--")
            )
            self.assertNotIn("sim_squad_warfare", story_path)

            # Story-вариативность цели и описания попала в Lua.
            self.assertIn("target_variants = {", lua)
            self.assertIn("descr_variants = {", lua)
            self.assertIn(
                'key = "mymod_relay_02_decryptor_stage_0_descr_v1"',
                lua,
            )
            self.assertIn('item = "itm_pda_common"', lua)
            self.assertIn("mymod_relay_guard_dead", lua)

            strings_ru = (
                gamedata / "configs" / "text" / "rus" / "st_last_relay.xml"
            ).read_text(encoding="cp1251")
            self.assertIn(
                'id="mymod_relay_02_decryptor_stage_0_descr_v1"',
                strings_ru,
            )
            self.assertIn(
                'id="mymod_relay_01_silence_stage_1_descr"',
                strings_ru,
            )

            dialogs_root = ET.parse(
                gamedata
                / "configs"
                / "gameplay"
                / "dialogs_last_relay.xml"
            ).getroot()
            dialogs_by_id = {
                dialog.get("id"): dialog
                for dialog in dialogs_root.findall("dialog")
            }
            self.assertEqual(
                set(dialogs_by_id),
                {
                    "mymod_relay_01_take",
                    "mymod_relay_01_turnin",
                    "mymod_relay_02_take",
                    "mymod_relay_02_turnin",
                },
            )

            # Разветвление «согласие / отказ»: у обоих диалогов выдачи
            # есть как минимум две ветки игрока (чётные ID 2 и 4).
            for take_id in ("mymod_relay_01_take", "mymod_relay_02_take"):
                take_phrases = {
                    phrase.get("id")
                    for phrase in dialogs_by_id[take_id].findall(
                        "./phrase_list/phrase"
                    )
                }
                self.assertTrue({"0", "1", "2", "4"} <= take_phrases)

            second_take = dialogs_by_id["mymod_relay_02_take"]
            self.assertEqual(second_take.findtext("has_info"),
                             "mymod_relay_01_done")
            self.assertEqual(second_take.findtext("dont_has_info"),
                             "mymod_relay_02_taken")

            # Ветка сдачи Q2 проверяет ПДА в Phrase.preconditions,
            # а альтернативная реплика «ещё ищу» имеет чётный ID.
            turnin_phrases = {
                phrase.get("id"): phrase
                for phrase in dialogs_by_id["mymod_relay_02_turnin"].findall(
                    "./phrase_list/phrase"
                )
            }
            self.assertEqual(
                set(turnin_phrases), {"0", "1", "2", "3", "4"}
            )
            self.assertEqual(
                turnin_phrases["3"].findtext("text"),
                "mymod_relay_02_turnin_phrase_3_text",
            )
            self.assertEqual(
                turnin_phrases["4"].findtext("text"),
                "mymod_relay_02_turnin_phrase_4_text",
            )
            self.assertEqual(
                [
                    next_phrase.text
                    for next_phrase in turnin_phrases["1"].findall("next")
                ],
                ["2", "4"],
            )
            self.assertEqual(
                [
                    next_phrase.text
                    for next_phrase in turnin_phrases["2"].findall("next")
                ],
                ["3"],
            )
            # Нарушение FAIL-1: реплика Игрока не должна иметь нечётный ID.
            self.assertNotEqual(
                (int(turnin_phrases["4"].get("id")) % 2), 1
            )
            self.assertEqual(
                turnin_phrases["2"].findtext("precondition"),
                "dialogs.mymod_relay_02_turnin_phrase_2_precondition",
            )
            self.assertEqual(
                turnin_phrases["2"].findtext("action"),
                "dialogs.mymod_relay_02_turnin_phrase_2_action",
            )

            # WARN-2: диалог сдачи Q2 не открывается до последнего этапа,
            # несмотря на собственный HasInfo (mymod_relay_02_taken).
            turnin_gate = self._function_body(
                lua,
                "local function mymod_relay_02_turnin_can_turn_in",
                "local function mymod_relay_02_turnin_accept",
            )
            self.assertIn(
                "if quest.return_stage < 0 and "
                "(tsk.stage or 0) < (quest.last_stage or 0) then",
                turnin_gate,
            )

            # WARN-3: SpawnNpcItem повторяется на следующих тиках _status.
            q2_status = self._function_body(
                lua,
                "local function mymod_relay_02_decryptor_status",
                "local function mymod_relay_02_decryptor_start",
            )
            self.assertIn("stage_data.npc_item_actions or {}", q2_status)
            self.assertIn('"npc_item_done"', q2_status)
            self.assertIn(
                "spawn_npc_item(item_spec.item, item_spec.target, "
                "item_spec.count)",
                q2_status,
            )
            self.assertIn(
                "kind = \"remove_item\"", lua
            )

            profile_xml = (
                gamedata / "configs" / "gameplay" / "character_desc_zaton.xml"
            )
            tree = ET.parse(profile_xml)
            profiles = tree.getroot().findall("specific_character")
            self.assertEqual(len(profiles), 1)
            self.assertEqual(
                profiles[0].get("id"), "zat_a2_stalker_barmen"
            )
            actor_dialogs = [
                element.text
                for element in profiles[0].findall("actor_dialog")
            ]
            for dialog_id in dialogs_by_id:
                self.assertIn(dialog_id, actor_dialogs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
