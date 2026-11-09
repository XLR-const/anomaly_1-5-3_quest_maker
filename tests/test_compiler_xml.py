"""Автоматические тесты генератора XML-строк и диалогов мода.

Запуск из корня проекта::

    python -m unittest tests.test_compiler_xml -v
    python -m unittest discover -s tests -v

Тесты проверяют раскладку русских и английских текстов по отдельным
string-таблицам, структуру файла диалогов и отказоустойчивость генератора
при повреждённом диалоге.
"""

from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compiler.xml_gen import XmlGenerator  # noqa: E402
from src.core.models import (  # noqa: E402
    Dialog,
    GiveInfo,
    HasInfo,
    ModProject,
    Phrase,
    Quest,
    Stage,
)

QUEST_ID = "mymod_test_quest"
DIALOG_ID = "mymod_test_dialog"
BROKEN_DIALOG_ID = "mymod_broken_dialog"
XML_LOGGER_NAME = "aqb.compiler.xml_gen"
XML_DECLARATION = '<?xml version="1.0" encoding="windows-1251"?>'

QUEST_TITLE_RU = "Квест & <тайна>"
QUEST_TITLE_EN = "Quest & <mystery>"
QUEST_DESCR_RU = "Описание квеста"
QUEST_DESCR_EN = "Quest description"
STAGE_TITLE_RU = "Первый этап"
STAGE_TITLE_EN = "First stage"
STAGE_DESCR_RU = "Описание первого этапа"
STAGE_DESCR_EN = "First stage description"
PHRASE_0_RU = "Здравствуй, сталкер!"
PHRASE_0_EN = "Hello, stalker!"
PHRASE_1_RU = "До встречи."
PHRASE_1_EN = "See you."


def _make_quest() -> Quest:
    """Создаёт валидный квест с одним этапом для тестов XML-строк.

    Returns:
        Quest: Квест с названием, описанием и этапом ``id=0``.
    """
    return Quest(
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
                target_alias="esc.test_target",
            )
        },
    )


def _make_dialog() -> Dialog:
    """Создаёт валидный диалог с переходами, условием и действием.

    Returns:
        Dialog: Диалог из двух реплик; стартовая реплика содержит переход,
        предусловие и действие.
    """
    return Dialog(
        id=DIALOG_ID,
        npc_alias="esc.mayor_zhurov",
        phrases={
            0: Phrase(
                id=0,
                text_ru=PHRASE_0_RU,
                text_en=PHRASE_0_EN,
                next_phrases=[1],
                preconditions=[HasInfo(info="mymod_test_info")],
                actions=[GiveInfo(info="mymod_test_reward_info")],
            ),
            1: Phrase(
                id=1,
                text_ru=PHRASE_1_RU,
                text_en=PHRASE_1_EN,
            ),
        },
    )


def _make_project() -> ModProject:
    """Создаёт проект мода с одним квестом и одним диалогом.

    Returns:
        ModProject: Валидный проект для проверки строковых таблиц.
    """
    return ModProject(
        name="mymod_test",
        quests={QUEST_ID: _make_quest()},
        dialogs={DIALOG_ID: _make_dialog()},
    )


def _find_phrase_by_id(dialog: ET.Element, phrase_id: str) -> ET.Element:
    """Находит XML-элемент фразы по атрибуту ``id``.

    Args:
        dialog (ET.Element):
            Корневой элемент диалога.
        phrase_id (str):
            Искомый идентификатор фразы.

    Returns:
        ET.Element: Найденный элемент ``<phrase>``.

    Raises:
        AssertionError:
            Если фраза с указанным идентификатором отсутствует.
    """
    for phrase in dialog.findall("phrase"):
        if phrase.get("id") == phrase_id:
            return phrase
    raise AssertionError(f"Фраза с id='{phrase_id}' не найдена.")


class TestXmlGeneratorStringTables(unittest.TestCase):
    """Проверка раскладки локализации по русской и английской таблицам."""

    def setUp(self) -> None:
        """Создаёт генератор XML перед каждым тестом."""
        self.generator = XmlGenerator()

    def test_generate_string_tables_splits_ru_and_en_texts(self) -> None:
        """Русские и английские тексты попадают в разные XML-документы."""
        tables = self.generator.generate_string_tables(_make_project())

        self.assertEqual(set(tables), {"rus", "eng"})
        self.assertTrue(tables["rus"].startswith(f"{XML_DECLARATION}\n<string_table>\n"))
        self.assertTrue(tables["eng"].startswith(f"{XML_DECLARATION}\n<string_table>\n"))
        self.assertTrue(tables["rus"].endswith("</string_table>"))
        self.assertTrue(tables["eng"].endswith("</string_table>"))

        expected_ids = {
            f"{QUEST_ID}_title",
            f"{QUEST_ID}_descr",
            f"{QUEST_ID}_stage_0_title",
            f"{QUEST_ID}_stage_0_descr",
            f"{DIALOG_ID}_phrase_0_text",
            f"{DIALOG_ID}_phrase_1_text",
        }

        rus_root = ET.fromstring(tables["rus"].encode("windows-1251"))
        eng_root = ET.fromstring(tables["eng"].encode("windows-1251"))

        self.assertEqual(rus_root.tag, "string_table")
        self.assertEqual(eng_root.tag, "string_table")

        rus_texts = {
            element.get("id"): element.findtext("text")
            for element in rus_root.findall("string")
        }
        eng_texts = {
            element.get("id"): element.findtext("text")
            for element in eng_root.findall("string")
        }

        self.assertEqual(set(rus_texts), expected_ids)
        self.assertEqual(set(eng_texts), expected_ids)

        self.assertEqual(rus_texts[f"{QUEST_ID}_title"], QUEST_TITLE_RU)
        self.assertEqual(eng_texts[f"{QUEST_ID}_title"], QUEST_TITLE_EN)
        self.assertEqual(rus_texts[f"{QUEST_ID}_descr"], QUEST_DESCR_RU)
        self.assertEqual(eng_texts[f"{QUEST_ID}_descr"], QUEST_DESCR_EN)
        self.assertEqual(rus_texts[f"{QUEST_ID}_stage_0_title"], STAGE_TITLE_RU)
        self.assertEqual(eng_texts[f"{QUEST_ID}_stage_0_title"], STAGE_TITLE_EN)
        self.assertEqual(rus_texts[f"{QUEST_ID}_stage_0_descr"], STAGE_DESCR_RU)
        self.assertEqual(eng_texts[f"{QUEST_ID}_stage_0_descr"], STAGE_DESCR_EN)
        self.assertEqual(rus_texts[f"{DIALOG_ID}_phrase_0_text"], PHRASE_0_RU)
        self.assertEqual(eng_texts[f"{DIALOG_ID}_phrase_0_text"], PHRASE_0_EN)
        self.assertEqual(rus_texts[f"{DIALOG_ID}_phrase_1_text"], PHRASE_1_RU)
        self.assertEqual(eng_texts[f"{DIALOG_ID}_phrase_1_text"], PHRASE_1_EN)

        self.assertNotIn(PHRASE_0_EN, tables["rus"])
        self.assertNotIn(PHRASE_0_RU, tables["eng"])
        self.assertIn("&amp;", tables["rus"])
        self.assertIn("&lt;", tables["rus"])
        self.assertIn("&amp;", tables["eng"])
        self.assertIn("&lt;", tables["eng"])


class TestXmlGeneratorDialogs(unittest.TestCase):
    """Проверка структуры и отказоустойчивости файла диалогов."""

    def setUp(self) -> None:
        """Создаёт генератор XML перед каждым тестом."""
        self.generator = XmlGenerator()

    def test_generate_dialogs_xml_builds_valid_structure(self) -> None:
        """Валидный диалог содержит переходы, условие и действие."""
        content = self.generator.generate_dialogs_xml(
            {DIALOG_ID: _make_dialog()}
        )

        self.assertTrue(content.startswith(f"{XML_DECLARATION}\n<game_dialogs>"))
        self.assertTrue(content.endswith("</game_dialogs>"))

        root = ET.fromstring(content.encode("windows-1251"))
        self.assertEqual(root.tag, "game_dialogs")

        dialogs = root.findall("dialog")
        self.assertEqual(len(dialogs), 1)
        self.assertEqual(dialogs[0].get("id"), DIALOG_ID)

        phrase_0 = _find_phrase_by_id(dialogs[0], "0")
        self.assertEqual(
            phrase_0.findtext("text"),
            f"{DIALOG_ID}_phrase_0_text",
        )
        self.assertEqual(
            [next_tag.get("id") for next_tag in phrase_0.findall("next")],
            ["1"],
        )
        self.assertEqual(
            phrase_0.findtext("precondition"),
            f"mymod_quests.{DIALOG_ID}_phrase_0_precondition",
        )
        self.assertEqual(
            phrase_0.findtext("action"),
            f"mymod_quests.{DIALOG_ID}_phrase_0_action",
        )

        phrase_1 = _find_phrase_by_id(dialogs[0], "1")
        self.assertEqual(
            phrase_1.findtext("text"),
            f"{DIALOG_ID}_phrase_1_text",
        )
        self.assertEqual(phrase_1.findall("next"), [])
        self.assertIsNone(phrase_1.find("precondition"))
        self.assertIsNone(phrase_1.find("action"))

    def test_generate_dialogs_xml_skips_broken_dialog(self) -> None:
        """Повреждённый диалог логируется и пропускается без падения."""
        broken_dialog = Dialog.model_construct(
            id=BROKEN_DIALOG_ID,
            npc_alias="esc.broken_npc",
            preconditions=[],
            phrases="повреждённая структура вместо карты фраз",
        )

        with self.assertLogs(XML_LOGGER_NAME, level="ERROR") as captured:
            content = self.generator.generate_dialogs_xml(
                {
                    DIALOG_ID: _make_dialog(),
                    BROKEN_DIALOG_ID: broken_dialog,
                }
            )

        root = ET.fromstring(content.encode("windows-1251"))
        dialog_ids = [element.get("id") for element in root.findall("dialog")]

        self.assertIn(DIALOG_ID, dialog_ids)
        self.assertNotIn(BROKEN_DIALOG_ID, dialog_ids)
        self.assertEqual(content.count("<game_dialogs>"), 1)
        self.assertEqual(content.count("</game_dialogs>"), 1)
        self.assertTrue(
            any(BROKEN_DIALOG_ID in message for message in captured.output),
            "В лог должно попасть сообщение о пропущенном диалоге.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
