"""Интеграционные проверки пакета ``aqm`` и команды ``aqm init``.

Тест запускает установленную команду в изолированном временном каталоге:
никаких ``_unpacked``, ``scripts/`` и ``aqm.json`` проекта-репозитория,
никакого явного ``db_path``. База должна браться из самого пакета.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestPackageInit(unittest.TestCase):
    """Проверяет структуру рабочего пространства и автономную сборку."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Запускает ``python -m aqm`` в изолированном каталоге."""
        return subprocess.run(
            [sys.executable, "-m", "aqm", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )

    def test_init_creates_workspace(self) -> None:
        """``aqm init`` создаёт scripts, output, doc.md и aqm.json."""
        result = self._run("init", ".")
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertTrue((self.root / "scripts" / "example_quest.py").is_file())
        self.assertTrue((self.root / "output").is_dir())
        self.assertTrue((self.root / "doc.md").is_file())
        self.assertTrue((self.root / "aqm.json").is_file())
        self.assertGreater((self.root / "doc.md").stat().st_size, 1000)

    def test_init_does_not_overwrite_without_force(self) -> None:
        """Повторный ``aqm init`` сохраняет пользовательский файл."""
        self.assertEqual(self._run("init", ".").returncode, 0)
        quest = self.root / "scripts" / "example_quest.py"
        quest.write_text("# custom\n", encoding="utf-8")

        self.assertEqual(self._run("init", ".").returncode, 0)
        self.assertEqual(quest.read_text(encoding="utf-8"), "# custom\n")

        self.assertEqual(self._run("init", ".", "--force").returncode, 0)
        self.assertIn("from aqm import", quest.read_text(encoding="utf-8"))

    def test_isolated_validate_and_build(self) -> None:
        """Шаблон валидируется и собирается без ``_unpacked``."""
        self.assertEqual(self._run("init", ".").returncode, 0)
        self.assertFalse((self.root / "_unpacked").exists())

        validate = self._run(
            "validate", "scripts/example_quest.py", "--strict"
        )
        self.assertEqual(
            validate.returncode, 0, validate.stdout + validate.stderr
        )
        self.assertIn("no issues", validate.stdout.lower())

        build = self._run("build", "scripts/example_quest.py")
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        self.assertNotIn("WARNING", build.stdout + build.stderr)

        project_dir = self.root / "output" / "aqm_example_quest"
        gamedata = project_dir / "gamedata"
        system_path = gamedata / "configs" / "system.ltx"
        self.assertTrue(system_path.is_file())
        self.assertTrue(
            (gamedata / "scripts" / "aqm_example_quest_quests.script").is_file()
        )

        # Вшитые ванильные индексы должны давать полноценный system.ltx,
        # а не минимальную заглушку.
        system_text = system_path.read_text(
            encoding="windows-1251", errors="replace"
        )
        self.assertGreater(len(system_text), 50_000)
        self.assertIn("[dialogs]", system_text)
        self.assertIn("[profiles]", system_text)
        self.assertIn("dialogs_aqm_example_quest", system_text)
        self.assertIn("npc_profile_aqm_example_quest", system_text)
        self.assertIn("character_desc_aqm_example_quest", system_text)
        self.assertIn("dialogs_bar", system_text)

        configs = gamedata / "configs"
        squad_index = (
            configs / "misc" / "squad_descr" / "squad_descr.ltx"
        ).read_text(encoding="windows-1251", errors="replace")
        spawn_index = (
            configs / "creatures" / "spawn_sections.ltx"
        ).read_text(encoding="windows-1251", errors="replace")
        self.assertTrue(
            "squad_descr_aqm_example_quest.ltx" in squad_index
            or 'squad_descr_*.ltx' in squad_index
        )
        self.assertIn(
            "spawn_sections_aqm_example_quest.ltx", spawn_index
        )
        self.assertTrue(
            (configs / "misc" / "squad_descr"
             / "squad_descr_aqm_example_quest.ltx").is_file()
        )
        self.assertTrue(
            (configs / "gameplay" / "character_desc_aqm_example_quest.xml").is_file()
        )
        self.assertTrue(
            (configs / "gameplay" / "npc_profile_aqm_example_quest.xml").is_file()
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
