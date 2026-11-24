"""Тесты контентного аудита: fallback, XRAY-TEXT/DLG/TASK и post-build."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compiler.xml_gen import XmlGenerator  # noqa: E402
from src.core.models import (  # noqa: E402
    CompleteTask,
    DescrVariant,
    Dialog,
    HasInfo,
    HasItem,
    ModProject,
    Phrase,
    Quest,
    Stage,
)
from src.validation.post_build import verify_built_mod  # noqa: E402
from src.validation.report import Severity, ValidationReport  # noqa: E402
from src.validation.xray_linter import XrayLinter  # noqa: E402


def make_stage(stage_id: int = 0, **kwargs) -> Stage:
    data = {
        "id": stage_id,
        "title_ru": "Этап",
        "title_en": "Stage",
        "descr_ru": "Описание этапа",
        "descr_en": "Stage description",
    }
    data.update(kwargs)
    return Stage(**data)


def make_quest(quest_id: str = "quest_a", **kwargs) -> Quest:
    data = {
        "id": quest_id,
        "title_ru": "Квест",
        "title_en": "Quest",
        "descr_ru": "Описание",
        "descr_en": "Description",
        "stages": {0: make_stage()},
    }
    data.update(kwargs)
    return Quest(**data)


def make_project(quests=None, dialogs=None) -> ModProject:
    return ModProject(
        name="Content Audit",
        quests={quest.id: quest for quest in (quests or [])},
        dialogs={dialog.id: dialog for dialog in (dialogs or [])},
    )


def analyze(project: ModProject) -> ValidationReport:
    report = ValidationReport()
    XrayLinter(None, report).validate(project)
    return report


def codes(report: ValidationReport, severity=None) -> set[str]:
    return {
        issue.code
        for issue in report.issues
        if severity is None or issue.severity == severity
    }


def make_dialog(
    dialog_id: str = "dialog_a",
    *,
    role: str = "turnin",
    preconditions=None,
    phrase_actions=None,
    text_ru: str = "Реплика",
    text_en: str = "Line",
) -> Dialog:
    return Dialog(
        id=dialog_id,
        role=role,
        task_id="quest_a",
        preconditions=list(preconditions or []),
        phrases={
            0: Phrase(
                id=0,
                text_ru=text_ru,
                text_en=text_en,
                next_phrases=[1],
                actions=list(phrase_actions or []),
            ),
            1: Phrase(id=1, text_ru="Ответ", text_en="Reply"),
        },
    )


class TestLocalizationFallback(unittest.TestCase):
    """Двусторонний fallback rus <-> eng в st_<slug>.xml."""

    def setUp(self) -> None:
        self.generator = XmlGenerator()

    def test_rus_is_copied_to_empty_eng(self) -> None:
        quest = make_quest(title_ru="Русский заголовок", title_en="")
        tables = self.generator.generate_string_tables(make_project([quest]))
        self.assertIn("<text>Русский заголовок</text>", tables["eng"])
        self.assertNotIn("<text></text>", tables["rus"])
        self.assertNotIn("<text></text>", tables["eng"])

    def test_eng_is_copied_to_empty_rus(self) -> None:
        quest = make_quest(title_ru="", title_en="English title")
        tables = self.generator.generate_string_tables(make_project([quest]))
        self.assertIn("<text>English title</text>", tables["rus"])
        self.assertNotIn("<text></text>", tables["rus"])
        self.assertNotIn("<text></text>", tables["eng"])

    def test_both_languages_are_untouched(self) -> None:
        quest = make_quest(title_ru="Рус", title_en="Eng")
        tables = self.generator.generate_string_tables(make_project([quest]))
        self.assertIn("<text>Рус</text>", tables["rus"])
        self.assertIn("<text>Eng</text>", tables["eng"])
        self.assertNotIn("<text>Eng</text>", tables["rus"])


class TestContentLinterRules(unittest.TestCase):
    """Правила XRAY-TEXT-001, XRAY-DLG-005 и XRAY-TASK-005."""

    def test_both_languages_empty_is_error(self) -> None:
        quest = make_quest(title_ru="", title_en="")
        report = analyze(make_project([quest]))
        self.assertIn("XRAY-TEXT-001", codes(report, Severity.ERROR))

    def test_only_one_empty_language_keeps_loc_only(self) -> None:
        quest = make_quest(title_ru="", title_en="English")
        report = analyze(make_project([quest]))
        self.assertNotIn("XRAY-TEXT-001", codes(report))
        self.assertIn("XRAY-LOC-001", codes(report, Severity.WARNING))

    def test_empty_stage_descr_variant_and_phrase(self) -> None:
        quest = make_quest(
            stages={
                0: make_stage(
                    title_ru="",
                    title_en="",
                    descr_variants=[
                        DescrVariant(
                            when=[HasInfo(info="ready")],
                            text_ru="",
                            text_en="",
                        )
                    ],
                )
            }
        )
        dialog = make_dialog(text_ru="", text_en="")
        report = analyze(make_project([quest], [dialog]))
        self.assertIn("XRAY-TEXT-001", codes(report, Severity.ERROR))

    def test_turnin_root_item_gate_warns(self) -> None:
        quest = make_quest()
        dialog = make_dialog(
            preconditions=[HasItem(item_alias="itm_pda_common")]
        )
        report = analyze(make_project([quest], [dialog]))
        self.assertIn("XRAY-DLG-005", codes(report, Severity.WARNING))

    def test_phrase_level_gate_does_not_warn(self) -> None:
        quest = make_quest()
        dialog = make_dialog()
        dialog.phrases[0].preconditions.append(
            HasItem(item_alias="itm_pda_common")
        )
        report = analyze(make_project([quest], [dialog]))
        self.assertNotIn("XRAY-DLG-005", codes(report))

    def test_complete_task_dialog_with_root_info_gate_warns(self) -> None:
        quest = make_quest()
        dialog = make_dialog(
            role="branch",
            preconditions=[HasInfo(info="ready")],
            phrase_actions=[CompleteTask(task_id=quest.id)],
        )
        report = analyze(make_project([quest], [dialog]))
        self.assertIn("XRAY-DLG-005", codes(report, Severity.WARNING))

    def test_non_final_has_item_transfer_warns(self) -> None:
        quest = make_quest(
            stages={0: make_stage(0), 1: make_stage(1)},
            transfer_conditions={
                0: {"complete": [HasItem(item_alias="itm_pda_common")]}
            },
        )
        report = analyze(make_project([quest]))
        self.assertIn("XRAY-TASK-005", codes(report, Severity.WARNING))

    def test_has_info_with_has_item_transfer_is_clean(self) -> None:
        quest = make_quest(
            stages={0: make_stage(0), 1: make_stage(1)},
            transfer_conditions={
                0: {
                    "complete": [
                        HasItem(item_alias="itm_pda_common"),
                        HasInfo(info="ready"),
                    ]
                }
            },
        )
        report = analyze(make_project([quest]))
        self.assertNotIn("XRAY-TASK-005", codes(report))

    def test_final_stage_has_item_transfer_is_clean(self) -> None:
        quest = make_quest(
            stages={0: make_stage(0), 1: make_stage(1)},
            transfer_conditions={
                1: {"complete": [HasItem(item_alias="itm_pda_common")]}
            },
        )
        report = analyze(make_project([quest]))
        self.assertNotIn("XRAY-TASK-005", codes(report))


class TestVerifyBuiltMod(unittest.TestCase):
    """Пост-проверка st_*.xml, диалогов и character_desc_<slug>.xml."""

    SLUG = "audit_mod"

    def _write_build(
        self,
        root: Path,
        *,
        skip_eng_key: str | None = None,
        empty_rus_key: str | None = None,
        with_break_dialog: bool = True,
    ) -> Path:
        configs = root / "gamedata" / "configs"
        text_rus = configs / "text" / "rus"
        text_eng = configs / "text" / "eng"
        for directory in (text_rus, text_eng, configs / "gameplay",
                          configs / "misc" / "task"):
            directory.mkdir(parents=True, exist_ok=True)

        entries = {
            "dialog_a_phrase_0_text": "Реплика",
            "quest_a_title": "Квест",
            "quest_a_descr": "Описание",
            "npc_a_name": "Имя",
        }

        def table(language: str) -> str:
            lines = ['<?xml version="1.0" encoding="windows-1251"?>',
                     "<string_table>"]
            for key, value in entries.items():
                if language == "eng" and key == skip_eng_key:
                    continue
                text = "" if (language == "rus" and key == empty_rus_key) else value
                lines.append(f'\t<string id="{key}">')
                lines.append(f"\t\t<text>{text}</text>")
                lines.append("\t</string>")
            lines.append("</string_table>")
            return "\n".join(lines)

        (text_rus / f"st_{self.SLUG}.xml").write_bytes(
            table("rus").encode("windows-1251")
        )
        (text_eng / f"st_{self.SLUG}.xml").write_bytes(
            table("eng").encode("windows-1251")
        )

        dialogs = f"""<?xml version="1.0" encoding="windows-1251"?>
<game_dialogs>
\t<dialog id="dialog_a">
\t\t<phrase_list>
\t\t\t<phrase id="0">
\t\t\t\t<text>dialog_a_phrase_0_text</text>
\t\t\t</phrase>
\t\t</phrase_list>
\t</dialog>
</game_dialogs>
"""
        (configs / "gameplay" / f"dialogs_{self.SLUG}.xml").write_bytes(
            dialogs.encode("windows-1251")
        )
        tasks = (
            "[quest_a]\n"
            "title = quest_a_title\n"
            "descr = quest_a_descr\n"
            "status_functor = quest_a_status\n"
        )
        (configs / "misc" / "task" / f"tm_{self.SLUG}.ltx").write_bytes(
            tasks.encode("windows-1251")
        )

        actor_dialog = (
            "\t\t<actor_dialog>actor_break_dialog</actor_dialog>\n"
            if with_break_dialog
            else ""
        )
        character_desc = f"""<?xml version="1.0" encoding="windows-1251"?>
<character_desc>
\t<specific_character id="npc_a">
\t\t<name>npc_a_name</name>
{actor_dialog}\t</specific_character>
</character_desc>
"""
        (configs / "gameplay" / f"character_desc_{self.SLUG}.xml").write_bytes(
            character_desc.encode("windows-1251")
        )
        return root

    def test_valid_build_has_no_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self._write_build(Path(temp))
            self.assertEqual(verify_built_mod(root, self.SLUG), [])

    def test_missing_key_in_english_table_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self._write_build(
                Path(temp), skip_eng_key="dialog_a_phrase_0_text"
            )
            errors = verify_built_mod(root, self.SLUG)
            self.assertTrue(any("dialog_a_phrase_0_text" in e for e in errors))

    def test_empty_key_in_russian_table_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self._write_build(
                Path(temp), empty_rus_key="quest_a_title"
            )
            errors = verify_built_mod(root, self.SLUG)
            self.assertTrue(any("quest_a_title" in e for e in errors))

    def test_missing_actor_break_dialog_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self._write_build(Path(temp), with_break_dialog=False)
            errors = verify_built_mod(root, self.SLUG)
            self.assertTrue(any("actor_break_dialog" in e for e in errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
