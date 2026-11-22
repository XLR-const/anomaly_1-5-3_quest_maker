"""Интеграционные тесты слияния глав и единого пайплайна валидации."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path

from main import DEFAULT_DB_PATH, _load_project_from_script
from src.compiler.builder import ModBuilder
from src.core.models import (
    CustomSquad,
    Dialog,
    GiveInfo,
    ModProject,
    Phrase,
    Quest,
    Stage,
)
from src.db.repository import GameDatabase
from src.validation import (
    MergeValidator,
    Severity,
    ValidationReport,
    validate_project,
)

ROOT = Path(__file__).resolve().parents[1]
ETALON_RELAY = ROOT / "examples" / "build_story_relay.py"
ETALON_GOLDEN = ROOT / "examples" / "build_golden_test.py"
BROKEN_STORY = ROOT / "examples" / "phase3" / "story_03.py"


def _make_quest(
    quest_id: str,
    *,
    complete_info: str | None = None,
    give_infos: tuple[str, ...] = (),
) -> Quest:
    """Создаёт минимальный валидный квест."""
    actions = [GiveInfo(info=info) for info in give_infos]
    return Quest(
        id=quest_id,
        complete_info=complete_info,
        stages={0: Stage(id=0, on_start_actions=actions)},
    )


def _make_dialog(dialog_id: str) -> Dialog:
    """Создаёт минимальный валидный диалог."""
    return Dialog(id=dialog_id, phrases={0: Phrase(id=0)})


def _make_squad(squad_id: str, *, story_id: str | None = None) -> CustomSquad:
    """Создаёт минимальный валидный отряд."""
    return CustomSquad(
        id=squad_id,
        faction="bandit",
        npc=["sim_default_bandit_4"],
        story_id=story_id,
    )


def _make_project(
    slug: str,
    *,
    quests: dict[str, Quest] | None = None,
    dialogs: dict[str, Dialog] | None = None,
    squads: dict[str, CustomSquad] | None = None,
) -> ModProject:
    """Создаёт проект-главу с явным slug в extra-поле."""
    return ModProject(
        name=f"Project {slug}",
        mod_slug=slug,
        mod_title=f"Project {slug}",
        quests=quests or {},
        dialogs=dialogs or {},
        squads=squads or {},
    )


def _validate_with_optional_db(project: ModProject) -> ValidationReport:
    """Запускает пайплайн с реальной БД, если она есть."""
    context = (
        GameDatabase(DEFAULT_DB_PATH)
        if DEFAULT_DB_PATH.is_file()
        else nullcontext(None)
    )
    with context as db:
        return validate_project(project, db=db)


def _normalize_level(value: object) -> str | None:
    """Повторяет нормализацию уровня из builder для тестовой ванилы."""
    if not isinstance(value, str):
        return None
    level = value.strip()
    if not level:
        return None
    if level.lower().endswith(".xml"):
        level = level[:-4]
    if level.lower().startswith("character_desc_"):
        level = level[len("character_desc_") :]
    return level.strip() or None


def _make_vanilla_root(project: ModProject, root: Path) -> Path:
    """Создаёт минимальное ванильное дерево под профили проекта."""
    configs = root / "configs"
    gameplay = configs / "gameplay"
    gameplay.mkdir(parents=True, exist_ok=True)

    system_ltx = (
        "[dialogs]\n"
        "files = dialogs_vanilla\n"
        "\n"
        "[profiles]\n"
        "specific_characters_files = character_desc_vanilla\n"
    )
    (configs / "system.ltx").write_text(system_ltx, encoding="cp1251")

    levels: set[str] = set()
    npc_ids: set[str] = set()
    for quest in project.quests.values():
        level = _normalize_level(quest.npc_location)
        if level:
            levels.add(level)
        for value in (quest.npc_id, quest.giver_npc_id):
            if value:
                npc_ids.add(str(value))
    for dialog in project.dialogs.values():
        level = _normalize_level(dialog.npc_location)
        if level:
            levels.add(level)
        if dialog.npc_id:
            npc_ids.add(str(dialog.npc_id))

    for level in levels:
        profiles = "\n".join(
            f'  <specific_character id="{npc_id}"></specific_character>'
            for npc_id in sorted(npc_ids)
        )
        content = (
            '<?xml version="1.0" encoding="windows-1251"?>\n'
            f"<character_desc_{level}>\n"
            f"{profiles}\n"
            f"</character_desc_{level}>\n"
        )
        (gameplay / f"character_desc_{level}.xml").write_text(
            content, encoding="cp1251"
        )
    return root


def _build_project_in_temp(project: ModProject) -> bool:
    """Собирает проект во временном каталоге с тестовой ванилой."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        vanilla = _make_vanilla_root(project, temp / "vanilla")
        builder = ModBuilder(
            output_dir=temp / "output",
            vanilla_root=vanilla,
        )
        return builder.build_project(project)


class MergeModelTests(unittest.TestCase):
    """Проверки ``ModProject.merge``."""

    def test_merge_two_chapters(self) -> None:
        first = _make_project(
            "chapter",
            quests={"chapter_q1": _make_quest("chapter_q1")},
            dialogs={"chapter_d1": _make_dialog("chapter_d1")},
            squads={"chapter_s1": _make_squad("chapter_s1")},
        )
        second = _make_project(
            "chapter",
            quests={"chapter_q2": _make_quest("chapter_q2")},
            dialogs={"chapter_d2": _make_dialog("chapter_d2")},
            squads={"chapter_s2": _make_squad("chapter_s2")},
        )

        merged = ModProject.merge(first, second)

        self.assertEqual(
            set(merged.quests), {"chapter_q1", "chapter_q2"}
        )
        self.assertEqual(
            set(merged.dialogs), {"chapter_d1", "chapter_d2"}
        )
        self.assertEqual(
            set(merged.squads), {"chapter_s1", "chapter_s2"}
        )
        self.assertEqual(merged.mod_slug, "chapter")
        self.assertEqual(merged.mod_title, "Project chapter")

    def test_merge_without_projects_raises(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "Не передано ни одного проекта для слияния"
        ):
            ModProject.merge()

    def test_merge_quest_collision_raises(self) -> None:
        first = _make_project(
            "chapter",
            quests={"chapter_q1": _make_quest("chapter_q1")},
        )
        second = _make_project(
            "chapter",
            quests={"chapter_q1": _make_quest("chapter_q1")},
        )

        with self.assertRaisesRegex(
            ValueError, "Конфликт ключа квеста 'chapter_q1'"
        ):
            ModProject.merge(first, second)

    def test_merge_story_id_collision_raises(self) -> None:
        first = _make_project(
            "chapter",
            squads={
                "chapter_s1": _make_squad(
                    "chapter_s1", story_id="chapter_story"
                )
            },
        )
        second = _make_project(
            "chapter",
            squads={
                "chapter_s2": _make_squad(
                    "chapter_s2", story_id="chapter_story"
                )
            },
        )

        with self.assertRaisesRegex(
            ValueError, "Конфликт story_id отряда 'chapter_story'"
        ):
            ModProject.merge(first, second)


class MergeValidatorTests(unittest.TestCase):
    """Проверки кодов ``MERGE-*``."""

    def test_merge_id_collision(self) -> None:
        first = _make_project(
            "chapter",
            quests={"chapter_q1": _make_quest("chapter_q1")},
        )
        second = _make_project(
            "chapter",
            quests={"chapter_q1": _make_quest("chapter_q1")},
        )
        report = ValidationReport()

        MergeValidator(report).validate_chapters([first, second], "chapter")

        issues = [
            issue for issue in report.issues if issue.code == "MERGE-ID-001"
        ]
        self.assertTrue(issues)
        self.assertTrue(
            all(issue.severity == Severity.ERROR for issue in issues)
        )
        self.assertIn("0", issues[0].message)
        self.assertIn("1", issues[0].message)

    def test_merge_shared_info_warning(self) -> None:
        first = _make_project(
            "chapter",
            quests={
                "chapter_q1": _make_quest(
                    "chapter_q1", complete_info="chapter_shared_info"
                )
            },
        )
        second = _make_project(
            "chapter",
            quests={
                "chapter_q2": _make_quest(
                    "chapter_q2", complete_info="chapter_shared_info"
                )
            },
        )
        report = ValidationReport()

        MergeValidator(report).validate_chapters([first, second], "chapter")

        issues = [
            issue
            for issue in report.issues
            if issue.code == "MERGE-INFO-001"
        ]
        self.assertTrue(issues)
        self.assertEqual(issues[0].severity, Severity.WARNING)
        self.assertEqual(issues[0].target_id, "chapter_shared_info")

    def test_merge_namespace_warning(self) -> None:
        project = _make_project(
            "chapter",
            quests={"wrong_quest": _make_quest("wrong_quest")},
            dialogs={"wrong_dialog": _make_dialog("wrong_dialog")},
            squads={"wrong_squad": _make_squad("wrong_squad")},
        )
        report = ValidationReport()

        MergeValidator(report).validate_chapters([project], "chapter")

        issues = [
            issue for issue in report.issues if issue.code == "MERGE-NS-001"
        ]
        self.assertGreaterEqual(len(issues), 3)
        self.assertTrue(
            all(issue.severity == Severity.WARNING for issue in issues)
        )


class ValidationPipelineTests(unittest.TestCase):
    """Проверки ``validate_project`` на эталонных и сломанном проектах."""

    def test_etalon_relay_has_no_errors(self) -> None:
        project = _load_project_from_script(ETALON_RELAY)
        report = _validate_with_optional_db(project)

        self.assertFalse(report.has_errors, report.to_text())

    def test_etalon_golden_has_no_errors(self) -> None:
        project = _load_project_from_script(ETALON_GOLDEN)
        report = _validate_with_optional_db(project)

        self.assertFalse(report.has_errors, report.to_text())

    def test_broken_story_has_errors(self) -> None:
        project = _load_project_from_script(BROKEN_STORY)
        report = _validate_with_optional_db(project)

        self.assertTrue(report.has_errors, report.to_text())


class BuilderIntegrationTests(unittest.TestCase):
    """Проверки встраивания валидации в ``ModBuilder``."""

    def test_builder_blocks_project_with_errors(self) -> None:
        project = _load_project_from_script(BROKEN_STORY)

        self.assertFalse(_build_project_in_temp(project))

    def test_builder_builds_relay_etalon(self) -> None:
        project = _load_project_from_script(ETALON_RELAY)

        self.assertTrue(_build_project_in_temp(project))

    def test_builder_builds_golden_etalon(self) -> None:
        project = _load_project_from_script(ETALON_GOLDEN)

        self.assertTrue(_build_project_in_temp(project))


class CliValidateTests(unittest.TestCase):
    """Проверки подкоманды ``main.py validate`` через subprocess."""

    @staticmethod
    def _run(*args: str) -> subprocess.CompletedProcess[bytes]:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            [sys.executable, str(ROOT / "main.py"), "validate", *args],
            cwd=ROOT,
            capture_output=True,
            env=env,
            timeout=180,
        )

    def test_cli_etalon_exit_zero(self) -> None:
        result = self._run(str(ETALON_RELAY))

        self.assertEqual(result.returncode, 0, result.stderr.decode(
            "utf-8", errors="replace"
        ))

    def test_cli_broken_script_exit_one(self) -> None:
        result = self._run(str(BROKEN_STORY))

        self.assertEqual(result.returncode, 1, result.stderr.decode(
            "utf-8", errors="replace"
        ))

    def test_cli_strict_warnings_exit_two(self) -> None:
        result = self._run(str(ETALON_RELAY), "--strict")

        self.assertEqual(result.returncode, 2, result.stderr.decode(
            "utf-8", errors="replace"
        ))

    def test_cli_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            result = self._run(
                str(ETALON_RELAY), "--json", str(report_path)
            )

            self.assertEqual(result.returncode, 0)
            self.assertTrue(report_path.is_file())
            data = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertIn("summary", data)
            self.assertIn("issues", data)
            self.assertEqual(data["summary"]["errors"], 0)


if __name__ == "__main__":
    unittest.main()
