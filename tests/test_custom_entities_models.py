"""Тесты моделей кастомных NPC/отрядов и генератора конфигов NPC.

Проверяются только изолированные артефакты Фазы 3.5 (Итерация 1):
модели ``CustomNpc``/``CustomSquad``/``ModProject`` и функции
``src.compiler.npc_gen``. Сборочный конвейер и Lua-генератор не
затрагиваются.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

from pydantic import ValidationError

from src.compiler import npc_gen
from src.core.models import (
    CustomNpc,
    CustomSquad,
    Dialog,
    ModProject,
    Phrase,
)

TEMPLATE_XML = """<?xml version="1.0" encoding="windows-1251"?>
<xml>
  <specific_character id="vanilla_guide" no_random="1">
    <name>vanilla_guide_name</name>
    <icon>ui_inGame2_guide</icon>
    <bio>vanilla_guide_bio</bio>
    <class>trader</class>
    <community>stalker</community>
    <terrain_sect>stalker_terrain</terrain_sect>
    <visual>actors\\stalker_guide\\stalker_guide_1</visual>
    <rank>18846</rank>
    <reputation>2302</reputation>
    <money min="1000000" max="2000000" infinitive="1"/>
    <supplies>
      [spawn]
      bandage
    </supplies>
  </specific_character>
</xml>
"""


class FakeDatabase:
    """Минимальная заглушка ``GameDatabase`` для точечных запросов."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = dict(mapping)

    def _query(
        self, sql: str, params: tuple[object, ...] = ()
    ) -> list[dict[str, str]]:
        """Возвращает строку ``source_file`` по id из первого параметра."""
        if "FROM npcs" not in sql:
            raise AssertionError(f"Неожиданный SQL: {sql}")
        source_file = self.mapping.get(str(params[0]))
        return [{"source_file": source_file}] if source_file else []


def _make_npc(**overrides: object) -> CustomNpc:
    """Создаёт валидный NPC с переопределениями."""
    data: dict[str, object] = {
        "id": "mymod_guide",
        "name_ru": "Проводник",
        "name_en": "Guide",
        "faction": "stalker",
        "visual": "actors\\stalker_guide\\stalker_guide_1",
    }
    data.update(overrides)
    return CustomNpc(**data)


def _make_project(**overrides: object) -> ModProject:
    """Создаёт проект мода с заполненным ``mod_slug``."""
    data: dict[str, object] = {
        "name": "My Mod",
        "mod_slug": "mymod",
    }
    data.update(overrides)
    return ModProject(**data)


class CustomNpcModelTests(unittest.TestCase):
    """Контракт ``CustomNpc`` (§3.2)."""

    def test_explicit_npc_defaults(self) -> None:
        """Явный NPC заполняет профиль и класс из id."""
        npc = _make_npc()
        self.assertEqual(npc.character_profile, "mymod_guide")
        self.assertEqual(npc.npc_class, "mymod_guide")
        self.assertEqual(npc.spec_rank, "regular")
        self.assertEqual(npc.parent_section, "stalker")
        self.assertEqual(npc.terrain_sect, "stalker_terrain")

    def test_class_alias_and_money_validation(self) -> None:
        """Алиас ``class`` работает, а money_max < money_min запрещён."""
        npc = _make_npc(**{"class": "custom_class"})
        self.assertEqual(npc.npc_class, "custom_class")

        with self.assertRaises(ValidationError):
            _make_npc(money_min=100, money_max=50)

    def test_visual_or_template_required(self) -> None:
        """Без visual и template_npc_id модель не создаётся."""
        with self.assertRaises(ValidationError) as ctx:
            CustomNpc(id="mymod_broken", faction="stalker")
        self.assertIn("visual", str(ctx.exception))

    def test_template_npc_allows_missing_visual(self) -> None:
        """В режиме шаблона visual не обязателен."""
        npc = CustomNpc(
            id="mymod_template_npc",
            faction="stalker",
            template_npc_id="vanilla_guide",
        )
        self.assertIsNone(npc.visual)
        self.assertEqual(npc.character_profile, "mymod_template_npc")

    def test_invalid_spec_rank(self) -> None:
        """``spec_rank`` ограничен четырьмя метками."""
        with self.assertRaises(ValidationError):
            _make_npc(spec_rank="legendary")


class CustomSquadTemplateTests(unittest.TestCase):
    """Изменения ``CustomSquad`` (§3.1)."""

    def test_template_squad_allows_empty_roster(self) -> None:
        """С ``template_squad_id`` пустой состав допустим."""
        squad = CustomSquad(
            id="mymod_squad",
            faction="stalker",
            template_squad_id="vanilla_squad",
        )
        self.assertEqual(squad.template_squad_id, "vanilla_squad")
        self.assertEqual(squad.npc, [])

    def test_empty_roster_without_template_rejected(self) -> None:
        """Без шаблона пустой состав по-прежнему ошибка."""
        with self.assertRaises(ValidationError):
            CustomSquad(id="mymod_squad", faction="stalker")


class ModProjectTests(unittest.TestCase):
    """Карта ``npcs``, перекрёстные ссылки и слияние глав."""

    def test_npcs_key_must_match_id(self) -> None:
        """Ключ карты обязан совпадать с ``CustomNpc.id``."""
        with self.assertRaises(ValidationError):
            _make_project(npcs={"wrong_key": _make_npc()})

    def test_duplicate_story_id_between_npc_and_squad(self) -> None:
        """story_id уникален среди NPC и отрядов."""
        npc = _make_npc(story_id="shared_story")
        squad = CustomSquad(
            id="mymod_squad",
            faction="stalker",
            npc=["mymod_guide"],
            story_id="shared_story",
        )
        with self.assertRaises(ValidationError):
            _make_project(
                npcs={npc.id: npc},
                squads={squad.id: squad},
            )

    def test_merge_npcs(self) -> None:
        """Слияние глав сохраняет NPC обеих глав."""
        first = _make_project(npcs={"mymod_guide": _make_npc()})
        second_npc = _make_npc(
            id="mymod_guide_2",
            visual="actors\\stalker_guide\\stalker_guide_2",
            story_id="mymod_guide_2_story",
        )
        second = _make_project(npcs={second_npc.id: second_npc})
        merged = ModProject.merge(first, second)
        self.assertEqual(
            set(merged.npcs), {"mymod_guide", "mymod_guide_2"}
        )
        self.assertEqual(
            merged.npcs["mymod_guide_2"].story_id,
            "mymod_guide_2_story",
        )

    def test_merge_npc_id_collision(self) -> None:
        """Одинаковый NPC.id в двух главах — ошибка с индексами."""
        first = _make_project(npcs={"mymod_guide": _make_npc()})
        second = _make_project(npcs={"mymod_guide": _make_npc()})
        with self.assertRaises(ValueError) as ctx:
            ModProject.merge(first, second)
        message = str(ctx.exception)
        self.assertIn("mymod_guide", message)
        self.assertIn("0", message)
        self.assertIn("1", message)

    def test_merge_npc_story_collision(self) -> None:
        """Одинаковый story_id NPC в двух главах — ошибка."""
        first_npc = _make_npc(story_id="same_story")
        second_npc = _make_npc(
            id="mymod_guide_2",
            visual="actors\\stalker_guide\\stalker_guide_2",
            story_id="same_story",
        )
        first = _make_project(npcs={first_npc.id: first_npc})
        second = _make_project(npcs={second_npc.id: second_npc})
        with self.assertRaises(ValueError) as ctx:
            ModProject.merge(first, second)
        self.assertIn("same_story", str(ctx.exception))


class TemplateResolverTests(unittest.TestCase):
    """Резолвер ``template_npc_id`` (§3.2, CAT-CUSTOM-011)."""

    def setUp(self) -> None:
        """Готовит временный ``vanilla_root`` с одним XML-шаблоном."""
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.vanilla_root = Path(self._tmpdir.name)
        gameplay = self.vanilla_root / "configs" / "gameplay"
        gameplay.mkdir(parents=True)
        (gameplay / "character_desc_escape.xml").write_bytes(
            TEMPLATE_XML.encode("windows-1251")
        )
        self.db = FakeDatabase({"vanilla_guide": "character_desc_escape.xml"})

    def test_resolve_extracts_allowed_tags(self) -> None:
        """Из шаблона копируются только разрешённые теги."""
        npc = CustomNpc(
            id="mymod_template_npc",
            faction="stalker",
            template_npc_id="vanilla_guide",
        )
        resolved = npc_gen.resolve_npc_template(
            npc, self.db, self.vanilla_root
        )
        self.assertEqual(
            resolved["visual"], "actors\\stalker_guide\\stalker_guide_1"
        )
        self.assertEqual(resolved["icon"], "ui_inGame2_guide")
        self.assertEqual(resolved["bio"], "vanilla_guide_bio")
        self.assertEqual(resolved["rank"], 18846)
        self.assertEqual(resolved["reputation"], 2302)
        self.assertEqual(
            resolved["money"],
            {"min": 1000000, "max": 2000000, "infinitive": True},
        )
        self.assertEqual(resolved["supplies"], ["[spawn]", "bandage"])
        self.assertNotIn("class", resolved)

    def test_missing_template_in_db(self) -> None:
        """Отсутствие id в БД — ValueError, а не молчаливый пропуск."""
        npc = CustomNpc(
            id="mymod_template_npc",
            faction="stalker",
            template_npc_id="unknown_npc",
        )
        with self.assertRaises(ValueError) as ctx:
            npc_gen.resolve_npc_template(npc, self.db, self.vanilla_root)
        self.assertIn("CAT-CUSTOM-011", str(ctx.exception))

    def test_missing_vanilla_root(self) -> None:
        """Без vanilla_root резолвер падает понятной ошибкой."""
        npc = CustomNpc(
            id="mymod_template_npc",
            faction="stalker",
            template_npc_id="vanilla_guide",
        )
        with self.assertRaises(ValueError):
            npc_gen.resolve_npc_template(npc, self.db, None)


class SpawnSectionsTests(unittest.TestCase):
    """``spawn_sections_<slug>.ltx`` (§4, §5)."""

    def test_immortal_section_precedes_npc_sections(self) -> None:
        """Секция иммунитетов идёт первой и содержит 10 полей 0.0."""
        immortal = _make_npc(
            id="mymod_immortal",
            immortal=True,
            story_id="mymod_immortal_story",
        )
        regular = _make_npc(id="mymod_regular")
        project = _make_project(
            npcs={immortal.id: immortal, regular.id: regular}
        )
        text = npc_gen.build_spawn_sections_ltx(project)

        section = "[mymod_immunities_immortal]"
        self.assertIn(section, text)
        self.assertLess(text.index(section), text.index("[mymod_immortal]"))
        self.assertLess(
            text.index(section),
            text.index("[mymod_regular]:stalker"),
        )

        section_body = text.split(section, 1)[1].split(
            "[mymod_immortal]", 1
        )[0]
        for field in npc_gen.IMMUNITY_FIELDS:
            self.assertRegex(
                section_body,
                rf"(?m)^{re.escape(field)}\s*=\s*0\.0$",
            )
        self.assertEqual(section_body.count("= 0.0"), 10)

        self.assertIn(
            "immunities_sect            = mymod_immunities_immortal",
            text,
        )

    def test_explicit_immunities_sect_is_used(self) -> None:
        """Явная ``immunities_sect`` отменяет генерацию секции."""
        npc = _make_npc(
            id="mymod_immortal",
            immortal=True,
            immunities_sect="vanilla_immunities",
        )
        text = npc_gen.build_spawn_sections_ltx(
            _make_project(npcs={npc.id: npc})
        )
        self.assertNotIn("[mymod_immunities_immortal]", text)
        self.assertIn("immunities_sect            = vanilla_immunities", text)

    def test_spawn_section_fields(self) -> None:
        """Spawn-секция содержит обязательные ключи и story_id."""
        npc = _make_npc(story_id="mymod_guide_story")
        text = npc_gen.build_spawn_sections_ltx(
            _make_project(npcs={npc.id: npc})
        )
        self.assertIn("[mymod_guide]:stalker", text)
        self.assertIn(
            '$spawn                     = "respawn\\mymod_guide"',
            text,
        )
        self.assertIn("character_profile          = mymod_guide", text)
        self.assertIn("spec_rank                  = regular", text)
        self.assertIn("community                  = stalker", text)
        self.assertIn("story_id                   = mymod_guide_story", text)


class XmlGeneratorTests(unittest.TestCase):
    """XML-артефакты NPC и таблицы строк."""

    def setUp(self) -> None:
        """Готовит NPC, диалог и проект."""
        self.npc = _make_npc()
        self.dialog = Dialog(
            id="mymod_guide_dialog",
            npc_id=self.npc.id,
            phrases={0: Phrase(id=0, text_ru="Привет", text_en="Hello")},
        )
        self.project = _make_project(
            npcs={self.npc.id: self.npc},
            dialogs={self.dialog.id: self.dialog},
        )

    def test_npc_profile_xml_is_utf8(self) -> None:
        """``npc_profile_*.xml`` декодируется в UTF-8."""
        payload = npc_gen.build_npc_profile_xml(self.project)
        text = payload.decode("utf-8")
        self.assertIn('encoding="utf-8"', text)
        self.assertIn('<character id="mymod_guide">', text)
        self.assertIn("<class>mymod_guide</class>", text)
        self.assertIn(
            "<specific_character>mymod_guide</specific_character>", text
        )
        self.assertEqual(ElementTree.fromstring(payload).tag, "xml")

    def test_character_desc_xml_is_cp1251_and_inherits_template(self) -> None:
        """``character_desc_*.xml`` — windows-1251 с тегами шаблона."""
        npc = CustomNpc(
            id="mymod_template_npc",
            name_ru="Проводник",
            name_en="Guide",
            faction="stalker",
            template_npc_id="vanilla_guide",
        )
        dialog = Dialog(
            id="mymod_template_dialog",
            npc_id=npc.id,
            phrases={0: Phrase(id=0, text_ru="Да", text_en="Yes")},
        )
        project = _make_project(
            npcs={npc.id: npc},
            dialogs={dialog.id: dialog},
        )
        resolved = {
            npc.id: {
                "visual": "actors\\stalker_guide\\stalker_guide_1",
                "icon": "ui_inGame2_guide",
                "bio": "vanilla_guide_bio",
                "rank": 18846,
                "reputation": 2302,
                "money": {
                    "min": 1000000,
                    "max": 2000000,
                    "infinitive": True,
                },
                "supplies_text": "[spawn]\nbandage",
            }
        }
        payload = npc_gen.build_character_desc_xml(project, resolved)
        text = payload.decode("windows-1251")

        self.assertIn('encoding="windows-1251"', text)
        self.assertIn('id="mymod_template_npc" no_random="1"', text)
        self.assertIn("<name>mymod_template_npc_name</name>", text)
        self.assertIn("<icon>ui_inGame2_guide</icon>", text)
        self.assertIn(
            "<visual>actors\\stalker_guide\\stalker_guide_1</visual>", text
        )
        self.assertIn("<bio>vanilla_guide_bio</bio>", text)
        self.assertIn("<rank>18846</rank>", text)
        self.assertIn("<reputation>2302</reputation>", text)
        self.assertIn(
            '<money min="1000000" max="2000000" infinitive="1"/>', text
        )
        self.assertIn(
            "<actor_dialog>mymod_template_dialog</actor_dialog>", text
        )
        self.assertEqual(ElementTree.fromstring(payload).tag, "xml")

    def test_actor_dialogs_merge_without_duplicates(self) -> None:
        """Явные и привязанные диалоги объединяются без дублей."""
        npc = _make_npc(actor_dialogs=["extra_dialog", "mymod_guide_dialog"])
        project = _make_project(
            npcs={npc.id: npc},
            dialogs={self.dialog.id: self.dialog},
        )
        text = npc_gen.build_character_desc_xml(project).decode(
            "windows-1251"
        )
        self.assertEqual(
            text.count("<actor_dialog>extra_dialog</actor_dialog>"), 1
        )
        self.assertEqual(
            text.count("<actor_dialog>mymod_guide_dialog</actor_dialog>"), 1
        )

    def test_text_entries(self) -> None:
        """Строки ``<name>``/``<bio>`` попадают в rus/eng-словари."""
        npc = _make_npc(bio="Опытный проводник.")
        rus, eng = npc_gen.build_npc_text_entries(
            _make_project(npcs={npc.id: npc})
        )
        self.assertEqual(rus["mymod_guide_name"], "Проводник")
        self.assertEqual(eng["mymod_guide_name"], "Guide")
        self.assertEqual(rus["mymod_guide_bio"], "Опытный проводник.")
        self.assertEqual(eng["mymod_guide_bio"], "Опытный проводник.")


class PatchIdempotencyTests(unittest.TestCase):
    """Патчи реестров не дублируют строки (§4.5)."""

    def test_spawn_sections_index(self) -> None:
        """Инклюд добавляется ровно один раз."""
        source = '#include "spawn_sections_general.ltx"\n'
        patched = npc_gen.patch_spawn_sections_index(source, "mymod")
        patched_again = npc_gen.patch_spawn_sections_index(patched, "mymod")
        self.assertEqual(patched, patched_again)
        self.assertEqual(
            patched.count('#include "spawn_sections_mymod.ltx"'), 1
        )

    def test_system_profiles_patch(self) -> None:
        """Оба имени дописываются в [profiles] и не дублируются."""
        source = (
            "[profiles]\n"
            "files                      = npc_profile\n"
            "specific_characters_files  = character_desc_general\n"
            "\n"
            "[other]\n"
            "files                      = ignored\n"
        )
        patched = npc_gen.patch_system_ltx_profiles(source, "mymod")
        patched_again = npc_gen.patch_system_ltx_profiles(patched, "mymod")

        self.assertEqual(patched, patched_again)
        self.assertEqual(patched.count("npc_profile_mymod"), 1)
        self.assertEqual(patched.count("character_desc_mymod"), 1)
        self.assertIn(
            "files                      = npc_profile, npc_profile_mymod",
            patched,
        )
        self.assertIn(
            "specific_characters_files  = character_desc_general, "
            "character_desc_mymod",
            patched,
        )
        self.assertIn("[other]\nfiles                      = ignored", patched)

    def test_system_profiles_flags(self) -> None:
        """Флаги позволяют зарегистрировать только нужный реестр."""
        source = (
            "[profiles]\n"
            "files                      = npc_profile\n"
            "specific_characters_files  = character_desc_general\n"
        )
        patched = npc_gen.patch_system_ltx_profiles(
            source,
            "mymod",
            include_npc_profile=False,
            include_character_desc=True,
        )
        self.assertNotIn("npc_profile_mymod", patched)
        self.assertIn("character_desc_mymod", patched)


if __name__ == "__main__":
    unittest.main()
