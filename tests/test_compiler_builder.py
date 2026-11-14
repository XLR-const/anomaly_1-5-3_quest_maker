"""Интеграционные тесты сборщика и текстового патчера ванильных файлов.

Проверяются требования ``standart_of_auto.md`` (1.2 и 1.3):

* ``system.ltx`` копируется и патчится в ``[dialogs]``/``[profiles]``;
* ``character_desc_<level>.xml`` копируется и патчится строково;
* BOM и CRLF патченных файлов сохраняются;
* отсутствие DLTX, ``.ext`` и README/INSTALL;
* понятные ``BuildError`` при отсутствии или дубликате NPC.

Тесты используют **только временное fake-дерево** ``_unpacked`` и никогда
не читают реальный ``_unpacked``.

Запуск::

    .\\venv\\Scripts\\python.exe -m unittest tests.test_compiler_builder -v
"""

from __future__ import annotations

import codecs
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compiler.builder import (  # noqa: E402
    BuildError,
    ModBuilder,
    _slugify,
)
from src.core.models import (  # noqa: E402
    CompleteTask,
    CustomSquad,
    Dialog,
    GiveTask,
    ModProject,
    Phrase,
    Quest,
    Stage,
)

PROJECT_NAME = "My Super Warfare Mod"
PROJECT_SLUG = "my_super_warfare_mod"
QUEST_ID = "mymod_builder_quest"
TAKE_DIALOG = "mymod_builder_take"
TURNIN_DIALOG = "mymod_builder_turnin"
NPC_ID = "esc_leader"
NPC_OTHER = "esc_other"
BUILDER_LOGGER_NAME = "aqb.compiler.builder"

SYSTEM_LTX = (
    "[dialogs]\r\n"
    "files = dialogs, dialogs_escape, \\\r\n"
    "dialogs_zaton\r\n"
    "\r\n"
    "[profiles]\r\n"
    "files                     = npc_profile\r\n"
    "specific_characters_files = character_desc_general, "
    "character_desc_escape, \\\r\n"
    "character_desc_zaton\r\n"
)

CHARACTER_DESC = """<?xml version="1.0" encoding="windows-1251"?>
<xml>
\t<!-- vanilla comment must survive -->
\t<specific_character id="esc_leader" team_default="1">
\t\t<name>esc_leader_name</name>
\t\t<actor_dialog>dm_init</actor_dialog>
\t</specific_character>
\t<specific_character id="esc_other">
\t\t<name>esc_other_name</name>
\t</specific_character>
</xml>
"""


def _make_project(*, bind_dialogs: bool = True) -> ModProject:
    """Создаёт проект с квестом и двумя диалогами выдачи/сдачи.

    Args:
        bind_dialogs (bool): Если ``True``, диалоги привязаны к NPC и
            quest; если ``False`` — добавлен несвязанный диалог.

    Returns:
        ModProject: Полностью валидная модель мода.
    """
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID if bind_dialogs else None,
        npc_location="escape" if bind_dialogs else None,
        dialog_id=TAKE_DIALOG if bind_dialogs else None,
        title_ru="Помощь блокпосту",
        title_en="Help the outpost",
        descr_ru="Проверка сквозной сборки мода.",
        descr_en="End-to-end mod build check.",
        stages={
            0: Stage(
                id=0,
                title_ru="Поговорить с командиром",
                title_en="Talk to the commander",
                descr_ru="Найдите командира блокпоста.",
                descr_en="Find the outpost commander.",
                target_alias="esc.mayor_zhurov",
            )
        },
    )
    take = Dialog(
        id=TAKE_DIALOG,
        npc_id=NPC_ID if bind_dialogs else None,
        npc_location="escape" if bind_dialogs else None,
        task_id=QUEST_ID if bind_dialogs else None,
        role="take",
        phrases={
            0: Phrase(
                id=0,
                text_ru="Здравствуй, сталкер!",
                text_en="Hello, stalker!",
                next_phrases=[1],
                actions=[GiveTask(task_id=QUEST_ID)],
            ),
            1: Phrase(
                id=1,
                text_ru="До встречи.",
                text_en="See you.",
            ),
        },
    )
    turnin = Dialog(
        id=TURNIN_DIALOG,
        npc_id=NPC_ID if bind_dialogs else None,
        npc_location="escape" if bind_dialogs else None,
        task_id=QUEST_ID if bind_dialogs else None,
        role="turnin",
        phrases={
            0: Phrase(
                id=0,
                text_ru="Готово.",
                text_en="Done.",
                actions=[CompleteTask(task_id=QUEST_ID)],
            )
        },
    )
    dialogs = {TAKE_DIALOG: take, TURNIN_DIALOG: turnin}
    if not bind_dialogs:
        dialogs["unbound"] = Dialog(
            id="mymod_unbound",
            phrases={0: Phrase(id=0, text_ru="...", text_en="...")},
        )
    return ModProject(
        name=PROJECT_NAME,
        quests={QUEST_ID: quest},
        dialogs=dialogs,
    )


class TestSlugify(unittest.TestCase):
    """Проверка безопасного имени проекта."""

    def test_spaces_and_specials_become_underscores(self) -> None:
        """Пробелы, дефисы и спецсимволы нормализуются."""
        self.assertEqual(_slugify(PROJECT_NAME), PROJECT_SLUG)
        self.assertEqual(_slugify("  My-Mod!!!  "), "my_mod")

    def test_cyrillic_name_is_transliterated(self) -> None:
        """Кириллица превращается в латинский slug."""
        self.assertEqual(_slugify("Тестовый мод"), "testovyy_mod")

    def test_invalid_name_gets_fallback(self) -> None:
        """Имя без допустимых символов заменяется на ``mod``."""
        self.assertEqual(_slugify("!!!"), "mod")

    def test_non_string_raises(self) -> None:
        """Неверный тип имени даёт ``TypeError``."""
        with self.assertRaises(TypeError):
            _slugify(123)  # type: ignore[arg-type]


class TestSystemLtxPatcher(unittest.TestCase):
    """Проверка текстового патча ``system.ltx``."""

    def setUp(self) -> None:
        """Создаёт патчер с временным ``vanilla_root``."""
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.builder = ModBuilder(
            output_dir=Path(self._temp_dir.name) / "out",
            vanilla_root=Path(self._temp_dir.name) / "_unpacked",
        )

    def test_appends_values_to_multiline_csv(self) -> None:
        """Значения дописываются после многострочного продолжения."""
        patched = self.builder.patch_system_ltx(
            SYSTEM_LTX,
            PROJECT_SLUG,
            ["character_desc_escape", "character_desc_bunker"],
        )

        self.assertIn(
            "files = dialogs, dialogs_escape, dialogs_zaton, "
            f"dialogs_{PROJECT_SLUG}",
            patched,
        )
        self.assertIn(
            "specific_characters_files = character_desc_general, "
            "character_desc_escape, character_desc_zaton, "
            "character_desc_bunker",
            patched,
        )
        self.assertEqual(patched.count(f"dialogs_{PROJECT_SLUG}"), 1)
        self.assertEqual(patched.count("character_desc_escape"), 1)
        self.assertNotIn("\\\r\n", patched)

    def test_is_idempotent(self) -> None:
        """Повторный патч не создаёт дубликатов."""
        first = self.builder.patch_system_ltx(
            SYSTEM_LTX,
            PROJECT_SLUG,
            ["character_desc_escape"],
        )
        second = self.builder.patch_system_ltx(
            first,
            PROJECT_SLUG,
            ["character_desc_escape"],
        )
        self.assertEqual(first, second)
        self.assertEqual(second.count(f"dialogs_{PROJECT_SLUG}"), 1)

    def test_preserves_existing_values_and_crlf(self) -> None:
        """Старые значения и CRLF сохраняются."""
        patched = self.builder.patch_system_ltx(
            SYSTEM_LTX,
            PROJECT_SLUG,
            ["character_desc_escape", "character_desc_zaton"],
        )
        self.assertIn("dialogs_escape", patched)
        self.assertIn("dialogs_zaton", patched)
        self.assertNotIn("\n", patched.replace("\r\n", ""))

    def test_missing_section_raises(self) -> None:
        """Отсутствие ``[dialogs]`` поднимает ``BuildError``."""
        with self.assertRaises(BuildError):
            self.builder.patch_system_ltx(
                "[profiles]\nspecific_characters_files = x\n",
                PROJECT_SLUG,
            )

    def test_missing_key_raises(self) -> None:
        """Отсутствие ключа внутри секции поднимает ``BuildError``."""
        with self.assertRaises(BuildError):
            self.builder.patch_system_ltx(
                "[dialogs]\nother = value\n",
                PROJECT_SLUG,
            )

    def test_empty_slug_raises(self) -> None:
        """Пустой slug недопустим."""
        with self.assertRaises(ValueError):
            self.builder.patch_system_ltx(SYSTEM_LTX, "")


class TestCharacterDescPatcher(unittest.TestCase):
    """Проверка строкового патча ``character_desc_<level>.xml``."""

    def setUp(self) -> None:
        """Создаёт патчер."""
        self.builder = ModBuilder(output_dir=Path(tempfile.gettempdir()))

    def test_inserts_actor_dialogs_before_closing_tag(self) -> None:
        """``<actor_dialog>`` вставляются перед ``</specific_character>``."""
        patched = self.builder.patch_character_desc(
            CHARACTER_DESC,
            NPC_ID,
            [TAKE_DIALOG, TURNIN_DIALOG],
        )

        self.assertIn(
            "\t\t<actor_dialog>dm_init</actor_dialog>\n"
            f"\t\t<actor_dialog>{TAKE_DIALOG}</actor_dialog>\n"
            f"\t\t<actor_dialog>{TURNIN_DIALOG}</actor_dialog>\n"
            "\t</specific_character>",
            patched,
        )
        self.assertIn("<!-- vanilla comment must survive -->", patched)
        self.assertLess(
            patched.index(TAKE_DIALOG),
            patched.index(TURNIN_DIALOG),
        )

    def test_other_npc_is_untouched(self) -> None:
        """Соседний ``<specific_character>`` не изменяется."""
        patched = self.builder.patch_character_desc(
            CHARACTER_DESC, NPC_ID, [TAKE_DIALOG]
        )
        other = patched.split(f'id="{NPC_OTHER}"', 1)[1]
        self.assertNotIn(TAKE_DIALOG, other)

    def test_is_idempotent(self) -> None:
        """Повторная вставка того же диалога ничего не меняет."""
        first = self.builder.patch_character_desc(
            CHARACTER_DESC, NPC_ID, [TAKE_DIALOG]
        )
        second = self.builder.patch_character_desc(
            first, NPC_ID, [TAKE_DIALOG]
        )
        self.assertEqual(first, second)
        self.assertEqual(first.count(TAKE_DIALOG), 1)

    def test_missing_npc_raises(self) -> None:
        """Неизвестный NPC — ``BuildError`` без угадывания профиля."""
        with self.assertRaises(BuildError):
            self.builder.patch_character_desc(
                CHARACTER_DESC, "missing_npc", [TAKE_DIALOG]
            )

    def test_duplicate_npc_raises(self) -> None:
        """Дубликат ``<specific_character id>`` — ``BuildError``."""
        duplicated = CHARACTER_DESC.replace(
            "</xml>",
            f'\t<specific_character id="{NPC_ID}">'
            "<name>x</name></specific_character>\n</xml>",
        )
        with self.assertRaises(BuildError):
            self.builder.patch_character_desc(
                duplicated, NPC_ID, [TAKE_DIALOG]
            )


class TestModBuilderIntegration(unittest.TestCase):
    """Сквозная сборка с временным fake-деревом ``_unpacked``."""

    def setUp(self) -> None:
        """Создаёт временные ``output`` и ``_unpacked``."""
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.root = Path(self._temp_dir.name)
        self.vanilla = self.root / "_unpacked"
        self._create_vanilla_tree()

        self.output_dir = self.root / "output"
        self.project = _make_project()
        self.builder = ModBuilder(
            output_dir=self.output_dir,
            vanilla_root=self.vanilla,
        )
        self.project_dir = self.output_dir / PROJECT_SLUG

    def _create_vanilla_tree(self) -> None:
        """Создаёт минимальные ванильные ``system.ltx`` и профили."""
        configs = self.vanilla / "configs"
        gameplay = configs / "gameplay"
        gameplay.mkdir(parents=True, exist_ok=True)
        (configs / "system.ltx").write_bytes(
            codecs.BOM_UTF8 + SYSTEM_LTX.encode("cp1251")
        )
        (gameplay / "character_desc_escape.xml").write_bytes(
            codecs.BOM_UTF8 + CHARACTER_DESC.encode("cp1251")
        )

    def _expected_generated_files(self) -> tuple[Path, ...]:
        """Возвращает относительные пути обязательных файлов сборки."""
        return (
            Path("gamedata") / "configs" / "misc" / "task"
            / f"tm_{PROJECT_SLUG}.ltx",
            Path("gamedata") / "configs" / "gameplay"
            / f"dialogs_{PROJECT_SLUG}.xml",
            Path("gamedata") / "configs" / "text" / "rus"
            / f"st_{PROJECT_SLUG}.xml",
            Path("gamedata") / "configs" / "text" / "eng"
            / f"st_{PROJECT_SLUG}.xml",
            Path("gamedata") / "scripts"
            / f"{PROJECT_SLUG}_quests.script",
            Path("gamedata") / "configs" / "system.ltx",
            Path("gamedata") / "configs" / "gameplay"
            / "character_desc_escape.xml",
        )

    def test_build_creates_all_files_and_no_dltx(self) -> None:
        """Сборка создаёт 7 файлов и не создаёт DLTX/README/INSTALL."""
        self.assertTrue(self.builder.build_project(self.project))

        for relative in self._expected_generated_files():
            path = self.project_dir / relative
            with self.subTest(path=str(relative)):
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 0)

        all_names = [
            path.name.lower()
            for path in self.project_dir.rglob("*")
            if path.is_file()
        ]
        self.assertFalse(any(name.endswith(".dltx") for name in all_names))
        self.assertNotIn("readme.txt", all_names)
        self.assertNotIn("install.txt", all_names)
        self.assertFalse((self.project_dir / "INSTALL.txt").exists())

    def test_squad_descr_is_written_only_when_squads_exist(self) -> None:
        """``squad_descr_<slug>.ltx`` создаётся только при непустых squads."""
        squad_path = (
            self.project_dir / "gamedata" / "configs" / "misc"
            / "squad_descr" / f"squad_descr_{PROJECT_SLUG}.ltx"
        )

        self.assertTrue(self.builder.build_project(self.project))
        self.assertFalse(squad_path.exists())

        self.project.squads["mymod_atp_bandit_leader_squad"] = CustomSquad(
            id="mymod_atp_bandit_leader_squad",
            faction="bandit",
            npc=["sim_default_bandit_4"],
        )
        self.assertTrue(self.builder.build_project(self.project))
        self.assertTrue(squad_path.is_file())

        raw = squad_path.read_bytes()
        self.assertFalse(raw.startswith(codecs.BOM_UTF8))
        text = raw.decode("cp1251")
        self.assertIn(
            "[mymod_atp_bandit_leader_squad]:online_offline_group", text
        )
        self.assertIn("faction = bandit", text)
        self.assertIn("npc     = sim_default_bandit_4", text)
        # system.ltx не должен упоминать squad_descr: файл подхватывается
        # ванильным глобом squad_descr.ltx автоматически.
        system_text = (
            self.project_dir / "gamedata" / "configs" / "system.ltx"
        ).read_bytes().decode("cp1251")
        self.assertNotIn("squad_descr", system_text)

    def test_generated_files_contain_project_data(self) -> None:
        """Сгенерированные файлы содержат данные квеста и диалогов."""
        self.assertTrue(self.builder.build_project(self.project))

        ltx = (
            self.project_dir / "gamedata" / "configs" / "misc"
            / "task" / f"tm_{PROJECT_SLUG}.ltx"
        ).read_text(encoding="cp1251")
        dialogs = (
            self.project_dir / "gamedata" / "configs" / "gameplay"
            / f"dialogs_{PROJECT_SLUG}.xml"
        ).read_text(encoding="cp1251")
        script = (
            self.project_dir / "gamedata" / "scripts"
            / f"{PROJECT_SLUG}_quests.script"
        ).read_text(encoding="cp1251")

        self.assertIn(f"[{QUEST_ID}]", ltx)
        self.assertIn(f"%={QUEST_ID}_start()%", ltx)
        self.assertIn(f'id="{TAKE_DIALOG}"', dialogs)
        self.assertIn("<phrase_list>", dialogs)
        self.assertIn(f"{PROJECT_SLUG}_quests.script", script)
        self.assertIn(f'task_functor["{QUEST_ID}_target"]', script)
        self.assertNotIn("dltx", script.lower())

    def test_system_ltx_is_patched_and_bom_preserved(self) -> None:
        """``system.ltx`` пропатчен и сохраняет BOM/CRLF."""
        self.assertTrue(self.builder.build_project(self.project))
        path = (
            self.project_dir / "gamedata" / "configs" / "system.ltx"
        )
        raw = path.read_bytes()

        self.assertTrue(raw.startswith(codecs.BOM_UTF8))
        text = raw[len(codecs.BOM_UTF8) :].decode("cp1251")
        self.assertIn(f"dialogs_{PROJECT_SLUG}", text)
        self.assertEqual(text.count(f"dialogs_{PROJECT_SLUG}"), 1)
        self.assertIn("character_desc_escape", text)
        self.assertEqual(text.count("character_desc_escape"), 1)
        self.assertNotIn("\n", text.replace("\r\n", ""))

    def test_character_desc_is_patched_and_bom_preserved(self) -> None:
        """Профиль NPC получает ``<actor_dialog>`` с сохранением BOM."""
        self.assertTrue(self.builder.build_project(self.project))
        path = (
            self.project_dir / "gamedata" / "configs" / "gameplay"
            / "character_desc_escape.xml"
        )
        raw = path.read_bytes()

        self.assertTrue(raw.startswith(codecs.BOM_UTF8))
        text = raw[len(codecs.BOM_UTF8) :].decode("cp1251")
        self.assertIn(TAKE_DIALOG, text)
        self.assertIn(TURNIN_DIALOG, text)
        self.assertIn("<actor_dialog>dm_init</actor_dialog>", text)
        self.assertIn("<!-- vanilla comment must survive -->", text)
        self.assertLess(text.index(TAKE_DIALOG), text.index(TURNIN_DIALOG))

    def test_rebuild_removes_stale_files(self) -> None:
        """Повторная сборка очищает старый каталог."""
        self.assertTrue(self.builder.build_project(self.project))
        stale = self.project_dir / "stale.txt"
        stale.write_text("stale", encoding="utf-8")

        self.assertTrue(self.builder.build_project(self.project))
        self.assertFalse(stale.exists())
        for relative in self._expected_generated_files():
            self.assertTrue((self.project_dir / relative).is_file())

    def test_write_failure_returns_false_and_logs(self) -> None:
        """Ошибка записи журналируется и даёт ``False``."""
        failing = "src.compiler.builder.write_file_cp1251"
        with patch(failing, side_effect=OSError("диск недоступен")):
            with self.assertLogs(
                BUILDER_LOGGER_NAME, level="ERROR"
            ) as captured:
                result = self.builder.build_project(self.project)

        self.assertFalse(result)
        self.assertTrue(
            any(
                "Критическая ошибка ввода-вывода" in message
                for message in captured.output
            ),
            captured.output,
        )

    def test_invalid_project_name_returns_false(self) -> None:
        """Проект без имени отклоняется без исключения."""
        invalid = ModProject.model_construct(
            name="",
            required_mods=[],
            quests={},
            dialogs={},
        )
        with self.assertLogs(BUILDER_LOGGER_NAME, level="ERROR"):
            result = self.builder.build_project(invalid)
        self.assertFalse(result)

    def test_missing_vanilla_system_returns_false(self) -> None:
        """Отсутствие ванильного ``system.ltx`` — ``False`` и ERROR."""
        self.builder.vanilla_root = self.root / "empty_vanilla"
        with self.assertLogs(BUILDER_LOGGER_NAME, level="ERROR"):
            result = self.builder.build_project(self.project)
        self.assertFalse(result)

    def test_missing_character_desc_level_returns_false(self) -> None:
        """Отсутствие файла локации — ``False`` и ERROR."""
        (self.vanilla / "configs" / "gameplay"
         / "character_desc_escape.xml").unlink()
        with self.assertLogs(BUILDER_LOGGER_NAME, level="ERROR"):
            result = self.builder.build_project(self.project)
        self.assertFalse(result)

    def test_npc_without_location_returns_false(self) -> None:
        """NPC без ``npc_location`` не позволяет выбрать файл."""
        project = _make_project()
        project.dialogs[TAKE_DIALOG].npc_location = None
        project.dialogs[TURNIN_DIALOG].npc_location = None
        project.quests[QUEST_ID].npc_location = None
        with self.assertLogs(BUILDER_LOGGER_NAME, level="ERROR"):
            result = self.builder.build_project(project)
        self.assertFalse(result)

    def test_legacy_dialog_extras_bind_profile(self) -> None:
        """Устаревшие extra-поля диалога привязывают профиль NPC.

        Исторические SQLite-колонки ``owner_profile_id`` и
        ``owner_character_desc`` должны переживать загрузку модели и
        использоваться патчером, даже если новых полей ``npc_id`` и
        ``npc_location`` в данных нет.
        """
        project = _make_project(bind_dialogs=False)
        project.dialogs.pop("unbound", None)
        take = project.dialogs[TAKE_DIALOG]
        take.npc_id = None
        take.npc_location = None
        take.owner_profile_id = NPC_ID
        take.owner_character_desc = "character_desc_escape.xml"

        self.assertTrue(self.builder.build_project(project))

        path = (
            self.project_dir / "gamedata" / "configs" / "gameplay"
            / "character_desc_escape.xml"
        )
        text = path.read_bytes()[len(codecs.BOM_UTF8) :].decode("cp1251")
        self.assertIn(f"<actor_dialog>{TAKE_DIALOG}</actor_dialog>", text)

    def test_legacy_quest_extras_are_fallback(self) -> None:
        """Extra-поля связанного квеста работают как запасной источник.

        Если у диалога нет ни ``npc_id``, ни ``npc_location``, но он связан
        с квестом через ``task_id``, патчер берёт
        ``owner_profile_id``/``giver_character_desc`` из квеста и
        нормализует имя файла профиля.
        """
        project = _make_project(bind_dialogs=False)
        project.dialogs.pop("unbound", None)
        take = project.dialogs[TAKE_DIALOG]
        take.npc_id = None
        take.npc_location = None
        take.task_id = QUEST_ID

        quest = project.quests[QUEST_ID]
        quest.npc_id = None
        quest.giver_npc_id = None
        quest.npc_location = None
        quest.owner_profile_id = NPC_ID
        quest.giver_character_desc = "character_desc_escape"

        self.assertTrue(self.builder.build_project(project))

        path = (
            self.project_dir / "gamedata" / "configs" / "gameplay"
            / "character_desc_escape.xml"
        )
        text = path.read_bytes()[len(codecs.BOM_UTF8) :].decode("cp1251")
        self.assertIn(f"<actor_dialog>{TAKE_DIALOG}</actor_dialog>", text)

    def test_unbound_dialog_is_skipped_with_warning(self) -> None:
        """Диалог без NPC не патчит профили, но сборка succeeds."""
        project = _make_project(bind_dialogs=False)
        with self.assertLogs(BUILDER_LOGGER_NAME, level="WARNING"):
            result = self.builder.build_project(project)

        self.assertTrue(result)
        self.assertTrue(
            (self.project_dir / "gamedata" / "configs" / "system.ltx")
            .is_file()
        )

    def test_absolute_output_and_slug_are_respected(self) -> None:
        """Slug используется в имени каталога и файлов."""
        self.assertTrue(self.builder.build_project(self.project))
        self.assertEqual(self.project_dir.name, PROJECT_SLUG)
        self.assertNotIn(" ", str(self.project_dir))
        for path in self.project_dir.rglob("*"):
            if path.is_file():
                self.assertEqual(path.name, path.name.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
