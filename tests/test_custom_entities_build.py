"""Интеграционные тесты сборки кастомных NPC и наследования отрядов.

Проверяется полный проход :meth:`src.compiler.builder.ModBuilder.build_project`
(``validate=False``) на временном ``vanilla_root`` и мок-базе ассетов:

* генерация ``spawn_sections_<slug>.ltx``, ``npc_profile_<slug>.xml`` и
  ``character_desc_<slug>.xml``;
* идемпотентный инклюд spawn-секций и регистрация профилей в ``system.ltx``;
* отсутствие патча ванильного ``character_desc_<location>.xml`` для диалога,
  привязанного к ``CustomNpc``;
* строки имени/биографии в ``st_<slug>.xml`` (rus/eng);
* заголовок ``[<id>]:<template_squad_id>`` в ``squad_descr_<slug>.ltx``.

Запуск::

    .\\venv\\Scripts\\python.exe -m unittest tests.test_custom_entities_build -v
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compiler.builder import BuildError, ModBuilder  # noqa: E402
from src.compiler.npc_gen import patch_spawn_sections_index  # noqa: E402
from src.core.models import (  # noqa: E402
    CustomNpc,
    CustomSquad,
    Dialog,
    ModProject,
    Phrase,
)

MOD_SLUG = "test_mod"
PROJECT_NAME = "Test Mod"

#: Минимальный ванильный system.ltx с обоими реестрами профилей.
SYSTEM_LTX = """\
[settings]
language = rus

[profiles]
files                     = npc_profile
specific_characters_files = character_desc_escape, character_desc_general

[dialogs]
files                     = dialogs_general
"""

#: Базовый индекс spawn-секций (без файла мода).
SPAWN_SECTIONS_LTX = """\
#include "spawn_sections_general.ltx"
#include "spawn_sections_escape.ltx"
"""

#: Ванильный XML с шаблоном NPC и обычным NPC для проверки патча.
CHARACTER_DESC_ESCAPE_XML = """\
<?xml version='1.0' encoding="windows-1251"?>
<xml>
  <specific_character id="vanilla_template" no_random="1">
    <name>vanilla_template_name</name>
    <icon>ui_inGame2_vanilla</icon>
    <bio>vanilla_template_bio</bio>
    <class>vanilla_template</class>
    <community>stalker</community>
    <map_icon x="1" y="0"/>
    <terrain_sect>stalker_terrain</terrain_sect>
    <visual>actors\\stalker_vanilla\\stalker_vanilla</visual>
    <rank>12345</rank>
    <reputation>678</reputation>
    <money min="100" max="200" infinitive="1"/>
    <supplies>
      [spawn]
      wpn_pm
    </supplies>
  </specific_character>

  <specific_character id="vanilla_npc" no_random="1">
    <name>vanilla_npc_name</name>
    <icon>ui_inGame2_vanilla_npc</icon>
    <bio>vanilla_npc_bio</bio>
    <class>vanilla_npc</class>
    <community>stalker</community>
    <terrain_sect>stalker_terrain</terrain_sect>
    <visual>actors\\stalker_vanilla\\stalker_npc</visual>
    <rank>100</rank>
    <reputation>10</reputation>
    <money min="0" max="0"/>
    <supplies>
      [spawn]
    </supplies>
  </specific_character>
</xml>
"""

SQUAD_DESCR_LTX = '#include "squad_descr_general.ltx"\n'


class _MockDatabase:
    """Мок ``GameDatabase`` с точечным запросом ``source_file``.

    Резолвер ``resolve_npc_template`` использует либо ``_query``, либо
    ``conn.cursor()``. Реализован только первый, чтобы тест не открывал
    реальную SQLite-базу.
    """

    def __init__(self, source_files: dict[str, str]) -> None:
        self.source_files = dict(source_files)

    def _query(self, sql: str, params: tuple[object, ...]) -> list[dict[str, str]]:
        """Возвращает строку ``npcs`` с ``source_file`` или пустой список."""
        entity_id = str(params[0]) if params else ""
        source_file = self.source_files.get(entity_id)
        if source_file is None:
            return []
        return [{"source_file": source_file}]


def _write_cp1251(path: Path, text: str) -> None:
    """Записывает временный ванильный файл в windows-1251."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("windows-1251"))


class TestCustomEntitiesBuild(unittest.TestCase):
    """Полная сборка проекта с CustomNpc и CustomSquad.template_squad_id."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vanilla = self.root / "vanilla"
        self.output = self.root / "output"
        self._create_vanilla_tree()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create_vanilla_tree(self) -> None:
        """Создаёт минимальный ``vanilla_root`` без чтения ``_unpacked``."""
        _write_cp1251(self.vanilla / "configs" / "system.ltx", SYSTEM_LTX)
        _write_cp1251(
            self.vanilla / "configs" / "creatures" / "spawn_sections.ltx",
            SPAWN_SECTIONS_LTX,
        )
        _write_cp1251(
            self.vanilla
            / "configs"
            / "gameplay"
            / "character_desc_escape.xml",
            CHARACTER_DESC_ESCAPE_XML,
        )
        _write_cp1251(
            self.vanilla
            / "configs"
            / "misc"
            / "squad_descr"
            / "squad_descr.ltx",
            SQUAD_DESCR_LTX,
        )

    def _project(self) -> ModProject:
        """Создаёт проект с явным NPC, шаблонным NPC и отрядом-наследником."""
        explicit = CustomNpc(
            id="test_mod_explicit",
            faction="stalker",
            name_ru="Явный",
            name_en="Explicit",
            visual="actors\\stalker_custom\\stalker_custom",
            icon="ui_inGame2_custom",
            bio="Биография явного NPC",
            rank=1000,
            reputation=200,
            money_min=10,
            money_max=20,
            supplies=["wpn_pm"],
            story_id="test_mod_explicit_story",
            actor_dialogs=["test_mod_dialog_explicit"],
        )
        templated = CustomNpc(
            id="test_mod_templated",
            faction="dolg",
            template_npc_id="vanilla_template",
            name_ru="Шаблонный",
            name_en="Templated",
            story_id="test_mod_templated_story",
        )
        dialog = Dialog(
            id="test_mod_dialog_explicit",
            dialog_id="test_mod_dialog_explicit",
            npc_id="test_mod_explicit",
            npc_location="escape",
            phrases={
                0: Phrase(
                    id=0,
                    text_ru="Привет.",
                    text_en="Hello.",
                )
            },
        )
        squad = CustomSquad(
            id="test_mod_squad",
            faction="stalker",
            npc=["test_mod_explicit"],
            template_squad_id="vanilla_squad",
            story_id="test_mod_squad_story",
        )
        return ModProject(
            name=PROJECT_NAME,
            mod_slug=MOD_SLUG,
            npcs={
                explicit.id: explicit,
                templated.id: templated,
            },
            dialogs={dialog.dialog_id: dialog},
            squads={squad.id: squad},
        )

    def _build(self, project: ModProject) -> ModBuilder:
        """Собирает проект с ``validate=False`` на мок-базе."""
        builder = ModBuilder(
            output_dir=self.output,
            db_client=_MockDatabase(
                {"vanilla_template": "character_desc_escape.xml"}
            ),
            vanilla_root=self.vanilla,
        )
        self.assertTrue(builder.build_project(project, validate=False))
        return builder

    def _gamedata(self) -> Path:
        """Возвращает каталог ``output/<slug>/gamedata``."""
        return self.output / MOD_SLUG / "gamedata"

    def test_full_build_generates_custom_npc_artifacts(self) -> None:
        """Создаются все три файла NPC и подключаются в реестры."""
        self._build(self._project())
        gamedata = self._gamedata()

        spawn_path = (
            gamedata / "configs" / "creatures" / "spawn_sections_test_mod.ltx"
        )
        profile_path = (
            gamedata / "configs" / "gameplay" / "npc_profile_test_mod.xml"
        )
        desc_path = (
            gamedata / "configs" / "gameplay" / "character_desc_test_mod.xml"
        )
        for path in (spawn_path, profile_path, desc_path):
            with self.subTest(path=path):
                self.assertTrue(path.is_file(), f"не создан {path}")

        spawn_text = spawn_path.read_bytes().decode("windows-1251")
        self.assertIn("[test_mod_explicit]:stalker", spawn_text)
        self.assertIn("[test_mod_templated]:stalker", spawn_text)
        self.assertIn(
            '$spawn                     = "respawn\\test_mod_templated"',
            spawn_text,
        )

        profile_text = profile_path.read_bytes().decode("utf-8")
        ElementTree.fromstring(profile_text)
        self.assertIn('<character id="test_mod_explicit">', profile_text)
        self.assertIn(
            "<specific_character>test_mod_explicit</specific_character>",
            profile_text,
        )

        desc_text = desc_path.read_bytes().decode("windows-1251")
        ElementTree.fromstring(desc_text)
        self.assertIn(
            '<specific_character id="test_mod_explicit" no_random="1">',
            desc_text,
        )
        self.assertIn(
            "<actor_dialog>test_mod_dialog_explicit</actor_dialog>",
            desc_text,
        )

    def test_template_npc_copies_allowed_tags(self) -> None:
        """Режим ``template_npc_id`` копирует visual/icon/bio/rank/money."""
        self._build(self._project())
        desc_path = (
            self._gamedata()
            / "configs"
            / "gameplay"
            / "character_desc_test_mod.xml"
        )
        desc_text = desc_path.read_bytes().decode("windows-1251")
        block = re.search(
            r'<specific_character id="test_mod_templated".*?</specific_character>',
            desc_text,
            re.DOTALL,
        )
        self.assertIsNotNone(block)
        fragment = block.group(0) if block else ""
        self.assertIn(
            "<visual>actors\\stalker_vanilla\\stalker_vanilla</visual>",
            fragment,
        )
        self.assertIn("<icon>ui_inGame2_vanilla</icon>", fragment)
        self.assertIn("<bio>vanilla_template_bio</bio>", fragment)
        self.assertIn("<rank>12345</rank>", fragment)
        self.assertIn("<reputation>678</reputation>", fragment)
        self.assertIn(
            '<money min="100" max="200" infinitive="1"/>',
            fragment,
        )
        self.assertIn("wpn_pm", fragment)

    def test_spawn_sections_index_is_idempotent(self) -> None:
        """Инклюд spawn-секций присутствует ровно один раз и не дублируется."""
        project = self._project()
        self._build(project)
        index_path = (
            self._gamedata()
            / "configs"
            / "creatures"
            / "spawn_sections.ltx"
        )
        first_text = index_path.read_bytes().decode("windows-1251")
        include = '#include "spawn_sections_test_mod.ltx"'
        self.assertEqual(first_text.count(include), 1)

        # Повторная сборка полностью пересоздаёт output/<slug>.
        self._build(project)
        second_text = index_path.read_bytes().decode("windows-1251")
        self.assertEqual(second_text.count(include), 1)

        # Патчер идемпотентен и на одном и том же тексте.
        once = patch_spawn_sections_index(SPAWN_SECTIONS_LTX, MOD_SLUG)
        twice = patch_spawn_sections_index(once, MOD_SLUG)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count(include), 1)

    def test_system_ltx_registers_npc_profile_and_character_desc(self) -> None:
        """В ``[profiles]`` появляются оба имени мода без дублей."""
        self._build(self._project())
        system_path = self._gamedata() / "configs" / "system.ltx"
        text = system_path.read_bytes().decode("windows-1251")

        files_line = re.search(r"^\s*files\s*=\s*(.+)$", text, re.MULTILINE)
        self.assertIsNotNone(files_line)
        self.assertIn("npc_profile_test_mod", files_line.group(1))
        self.assertEqual(
            files_line.group(1).count("npc_profile_test_mod"), 1
        )

        specific_line = re.search(
            r"^\s*specific_characters_files\s*=\s*(.+)$",
            text,
            re.MULTILINE,
        )
        self.assertIsNotNone(specific_line)
        self.assertIn("character_desc_test_mod", specific_line.group(1))
        self.assertEqual(
            specific_line.group(1).count("character_desc_test_mod"), 1
        )
        self.assertIn("dialogs_test_mod", text)

    def test_custom_npc_dialog_does_not_patch_vanilla_location(self) -> None:
        """Диалог CustomNpc не вызывает патч ``character_desc_escape.xml``."""
        project = self._project()
        builder = self._build(project)
        vanilla_target = (
            self._gamedata()
            / "configs"
            / "gameplay"
            / "character_desc_escape.xml"
        )
        self.assertFalse(vanilla_target.exists())
        self.assertEqual(builder._collect_dialog_bindings(project), [])

    def test_npc_localization_lines_are_merged(self) -> None:
        """Имена и биография NPC попадают в ``st_test_mod.xml`` (rus/eng)."""
        self._build(self._project())
        text_dir = self._gamedata() / "configs" / "text"
        rus = (text_dir / "rus" / "st_test_mod.xml").read_bytes().decode(
            "windows-1251"
        )
        eng = (text_dir / "eng" / "st_test_mod.xml").read_bytes().decode(
            "windows-1251"
        )

        self.assertEqual(rus.count('<string id="test_mod_explicit_name">'), 1)
        self.assertEqual(rus.count('<string id="test_mod_explicit_bio">'), 1)
        self.assertIn("Явный", rus)
        self.assertIn("Биография явного NPC", rus)
        self.assertIn("Шаблонный", rus)
        self.assertEqual(eng.count('<string id="test_mod_explicit_name">'), 1)
        self.assertIn("Explicit", eng)
        self.assertIn("Templated", eng)

    def test_squad_template_inheritance_header(self) -> None:
        """Секция отряда наследует ``template_squad_id`` вместо ванильного."""
        self._build(self._project())
        squad_path = (
            self._gamedata()
            / "configs"
            / "misc"
            / "squad_descr"
            / "squad_descr_test_mod.ltx"
        )
        text = squad_path.read_bytes().decode("windows-1251")
        self.assertIn("[test_mod_squad]:vanilla_squad", text)
        self.assertNotIn("[test_mod_squad]:online_offline_group", text)
        self.assertIn("npc     = test_mod_explicit", text)

    def test_missing_template_is_reported_as_build_error(self) -> None:
        """``ValueError`` резолвера превращается в :class:`BuildError`."""
        builder = ModBuilder(
            output_dir=self.output,
            db_client=_MockDatabase({}),
            vanilla_root=self.vanilla,
        )
        npc = CustomNpc(
            id="test_mod_missing",
            faction="stalker",
            template_npc_id="missing_template",
        )
        with self.assertRaises(BuildError):
            builder._resolve_npc_templates({npc.id: npc})


if __name__ == "__main__":
    unittest.main(verbosity=2)
