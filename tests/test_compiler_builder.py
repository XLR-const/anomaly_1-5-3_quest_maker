"""Интеграционные тесты главного сборщика мода :class:`ModBuilder`.

Запуск из корня проекта::

    python -m unittest tests.test_compiler_builder -v
    python -m unittest discover -s tests -v

Тесты проверяют полный сквозной конвейер: создание временного проекта,
сборку установочной структуры ``gamedata``, физическое наличие всех игровых
файлов, кодировку Windows-1251, безопасный slug в путях и отказоустойчивость
при критической ошибке записи.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compiler.builder import ModBuilder, _slugify  # noqa: E402
from src.core.models import (  # noqa: E402
    Dialog,
    GiveInfo,
    HasInfo,
    ModProject,
    Phrase,
    Quest,
    Stage,
)

PROJECT_NAME = "My Super Warfare Mod"
PROJECT_SLUG = "my_super_warfare_mod"
QUEST_ID = "mymod_builder_quest"
DIALOG_ID = "mymod_builder_dialog"
BUILDER_LOGGER_NAME = "aqb.compiler.builder"

QUEST_TITLE_RU = "Помощь блокпосту"
QUEST_TITLE_EN = "Help the outpost"
QUEST_DESCR_RU = "Проверка сквозной сборки мода."
QUEST_DESCR_EN = "End-to-end mod build check."
STAGE_TITLE_RU = "Поговорить с командиром"
STAGE_TITLE_EN = "Talk to the commander"
STAGE_DESCR_RU = "Найдите командира блокпоста."
STAGE_DESCR_EN = "Find the outpost commander."
PHRASE_RU = "Здравствуй, сталкер!"
PHRASE_EN = "Hello, stalker!"


def _make_project() -> ModProject:
    """Создаёт тестовый проект с одним квестом и одним диалогом.

    Название проекта содержит пробелы, чтобы проверить преобразование в
    безопасный slug. Квест и диалог содержат русские и английские тексты,
    а также условие и действие для проверки сквозной генерации.

    Returns:
        ModProject: Полностью валидная модель мода для сборки.
    """
    quest = Quest(
        id=QUEST_ID,
        title_ru=QUEST_TITLE_RU,
        title_en=QUEST_TITLE_EN,
        descr_ru=QUEST_DESCR_RU,
        descr_en=QUEST_DESCR_EN,
        stages={
            0: Stage(
                id=0,
                title_ru=STAGE_TITLE_RU,
                title_en=STAGE_TITLE_EN,
                descr_ru=STAGE_DESCR_RU,
                descr_en=STAGE_DESCR_EN,
                target_alias="esc.mayor_zhurov",
            )
        },
    )

    dialog = Dialog(
        id=DIALOG_ID,
        npc_alias="esc.mayor_zhurov",
        phrases={
            0: Phrase(
                id=0,
                text_ru=PHRASE_RU,
                text_en=PHRASE_EN,
                next_phrases=[1],
                preconditions=[HasInfo(info="mymod_builder_available")],
                actions=[GiveInfo(info="mymod_builder_started")],
            ),
            1: Phrase(
                id=1,
                text_ru="До встречи.",
                text_en="See you.",
            ),
        },
    )

    return ModProject(
        name=PROJECT_NAME,
        quests={QUEST_ID: quest},
        dialogs={DIALOG_ID: dialog},
    )


class TestSlugify(unittest.TestCase):
    """Проверка внутреннего помощника безопасного имени проекта."""

    def test_spaces_and_hyphens_become_underscores(self) -> None:
        """Пробелы, дефисы и специальные символы нормализуются."""
        self.assertEqual(
            _slugify("My Super Warfare Mod"),
            PROJECT_SLUG,
        )
        self.assertEqual(_slugify("  My-Mod!!!  "), "my_mod")

    def test_cyrillic_name_is_transliterated(self) -> None:
        """Кириллическое название превращается в латинский slug."""
        self.assertEqual(_slugify("Тестовый мод"), "testovyy_mod")

    def test_name_without_valid_characters_gets_fallback(self) -> None:
        """Полностью недопустимое имя заменяется запасным slug."""
        self.assertEqual(_slugify("!!!"), "mod")


class TestModBuilderIntegration(unittest.TestCase):
    """Сквозные интеграционные тесты сборки установочного каталога мода."""

    def setUp(self) -> None:
        """Создаёт временную директорию и сборщик перед каждым тестом."""
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)

        self.output_dir = Path(self._temp_dir.name)
        self.project = _make_project()
        self.builder = ModBuilder(output_dir=self.output_dir)
        self.project_dir = self.output_dir / PROJECT_SLUG

    def _expected_files(self) -> tuple[Path, ...]:
        """Возвращает относительные пути всех игровых файлов сборки.

        Returns:
            tuple[Path, ...]: Пути внутри каталога проекта, включая LTX,
            диалоги, две локализации и Lua-скрипт.
        """
        return (
            Path("gamedata")
            / "configs"
            / "misc"
            / "task"
            / f"tm_{PROJECT_SLUG}.ltx",
            Path("gamedata")
            / "configs"
            / "gameplay"
            / f"dialogs_{PROJECT_SLUG}.xml",
            Path("gamedata")
            / "configs"
            / "text"
            / "rus"
            / f"st_{PROJECT_SLUG}.xml",
            Path("gamedata")
            / "configs"
            / "text"
            / "eng"
            / f"st_{PROJECT_SLUG}.xml",
            Path("gamedata")
            / "scripts"
            / f"{PROJECT_SLUG}_quests.script",
        )

    def _read_cp1251(self, path: Path) -> str:
        """Читает файл сборки в кодировке Windows-1251.

        Args:
            path (Path):
                Путь к созданному игровому файлу.

        Returns:
            str: Декодированное содержимое файла.
        """
        return path.read_bytes().decode("windows-1251")

    def test_build_project_creates_all_game_files(self) -> None:
        """Сборка возвращает True и создаёт все пять игровых файлов."""
        result = self.builder.build_project(self.project)

        self.assertTrue(result)
        self.assertTrue(self.project_dir.is_dir())

        for relative_path in self._expected_files():
            path = self.project_dir / relative_path
            with self.subTest(path=str(relative_path)):
                self.assertTrue(
                    path.is_file(),
                    f"Не создан обязательный файл сборки: {path}",
                )
                raw = path.read_bytes()
                self.assertGreater(
                    len(raw),
                    0,
                    f"Файл сборки пуст: {path}",
                )
                decoded = self._read_cp1251(path)
                self.assertTrue(
                    decoded.strip(),
                    f"Файл сборки не содержит текста: {path}",
                )

        self.assertFalse((self.project_dir / "README.txt").exists())
        self.assertFalse((self.project_dir / "readme.md").exists())

    def test_generated_files_contain_project_data(self) -> None:
        """Файлы содержат данные квеста, диалога и обе локализации."""
        self.assertTrue(self.builder.build_project(self.project))

        ltx_path = self.project_dir / "gamedata" / "configs" / "misc" / (
            "task"
        ) / f"tm_{PROJECT_SLUG}.ltx"
        dialogs_path = self.project_dir / "gamedata" / "configs" / (
            "gameplay"
        ) / f"dialogs_{PROJECT_SLUG}.xml"
        rus_path = self.project_dir / "gamedata" / "configs" / "text" / (
            "rus"
        ) / f"st_{PROJECT_SLUG}.xml"
        eng_path = self.project_dir / "gamedata" / "configs" / "text" / (
            "eng"
        ) / f"st_{PROJECT_SLUG}.xml"
        script_path = self.project_dir / "gamedata" / "scripts" / (
            f"{PROJECT_SLUG}_quests.script"
        )

        ltx_content = self._read_cp1251(ltx_path)
        dialogs_content = self._read_cp1251(dialogs_path)
        rus_content = self._read_cp1251(rus_path)
        eng_content = self._read_cp1251(eng_path)
        script_content = self._read_cp1251(script_path)

        self.assertIn(f"[{QUEST_ID}]", ltx_content)
        self.assertIn(f'id="{DIALOG_ID}"', dialogs_content)
        self.assertIn(QUEST_TITLE_RU, rus_content)
        self.assertIn(PHRASE_RU, rus_content)
        self.assertIn(QUEST_TITLE_EN, eng_content)
        self.assertIn(PHRASE_EN, eng_content)
        self.assertIn(
            f"function mymod_quests.{QUEST_ID}_on_init(tsk)",
            script_content,
        )
        self.assertIn(
            f"mymod_quests.{DIALOG_ID}_phrase_0_action",
            script_content,
        )

    def test_slug_is_used_for_directory_and_file_names(self) -> None:
        """Slug проекта становится именем папки и префиксом всех файлов."""
        self.assertTrue(self.builder.build_project(self.project))

        self.assertEqual(self.project_dir.name, PROJECT_SLUG)
        self.assertNotIn(" ", str(self.project_dir))

        generated_files = [
            path for path in self.project_dir.rglob("*") if path.is_file()
        ]
        self.assertEqual(len(generated_files), 5)

        for path in generated_files:
            with self.subTest(file=path.name):
                self.assertIn(PROJECT_SLUG, path.name)
                self.assertEqual(path.name, path.name.lower())

    def test_rebuild_removes_stale_files(self) -> None:
        """Повторная сборка полностью очищает старый каталог проекта."""
        self.assertTrue(self.builder.build_project(self.project))

        stale_file = self.project_dir / "stale_previous_build.txt"
        stale_file.write_text("устаревший файл", encoding="utf-8")
        self.assertTrue(stale_file.exists())

        self.assertTrue(self.builder.build_project(self.project))

        self.assertFalse(stale_file.exists())
        for relative_path in self._expected_files():
            self.assertTrue((self.project_dir / relative_path).is_file())

    def test_write_failure_returns_false_and_logs_exception(self) -> None:
        """Критическая ошибка записи журналируется и даёт результат False."""
        failing_path = "src.compiler.builder.write_file_cp1251"

        with patch(failing_path, side_effect=OSError("диск недоступен")):
            with self.assertLogs(
                BUILDER_LOGGER_NAME,
                level="ERROR",
            ) as captured:
                result = self.builder.build_project(self.project)

        self.assertFalse(result)
        self.assertTrue(
            any(
                "Критическая ошибка ввода-вывода" in message
                for message in captured.output
            ),
            "В лог должно попасть сообщение о критической ошибке записи.",
        )

    def test_invalid_project_name_returns_false(self) -> None:
        """Проект без корректного имени отклоняется без исключения."""
        invalid_project = ModProject.model_construct(
            name="",
            required_mods=[],
            quests={},
            dialogs={},
        )

        with self.assertLogs(BUILDER_LOGGER_NAME, level="ERROR"):
            result = self.builder.build_project(invalid_project)

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
