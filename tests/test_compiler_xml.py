"""Тесты XML-генератора диалогов и таблиц локализации.

Проверяются требования ``standart_of_auto.md`` (2.1):

* корень ``<game_dialogs>`` и обязательный ``<phrase_list>`` у каждого
  диалога;
* переходы только парными ``<next>ID</next>``;
* условия/эффекты только как ``dialogs.<flat_function>``;
* идентификатор диалога берётся из модели, а не из ключа словаря.

Запуск::

    .\\venv\\Scripts\\python.exe -m unittest tests.test_compiler_xml -v
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
    CompleteTask,
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveItem,
    GiveTask,
    HasInfo,
    HasItem,
    ModProject,
    Phrase,
    Quest,
    Stage,
)

QUEST_ID = "mymod_xml_quest"
DIALOG_ID = "mymod_xml_dialog_take"
DICT_KEY = "different_dict_key"


def _make_project() -> ModProject:
    """Создаёт проект с квестом и диалогом для XML-тестов.

    Returns:
        ModProject: Проект с проверочными текстами и условиями.
    """
    quest = Quest(
        id=QUEST_ID,
        title_ru="Квест & проверка",
        title_en="Quest & check",
        descr_ru="Описание <квеста>",
        descr_en="Quest <description>",
        stages={
            0: Stage(
                id=0,
                title_ru="Этап 0",
                title_en="Stage 0",
                descr_ru="Описание этапа 0",
                descr_en="Stage 0 description",
            ),
            1: Stage(
                id=1,
                title_ru="Этап 1",
                title_en="Stage 1",
                descr_ru="Описание этапа 1",
                descr_en="Stage 1 description",
            ),
        },
    )
    dialog = Dialog(
        id=DIALOG_ID,
        npc_id="esc_mayor",
        npc_location="escape",
        task_id=QUEST_ID,
        role="take",
        preconditions=[
            HasInfo(info="mymod_available"),
            DontHasInfo(info="mymod_blocked"),
            HasItem(item_alias="mymod_item"),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Здравствуй, сталкер!",
                text_en="Hello, stalker!",
                next_phrases=[1],
                preconditions=[HasInfo(info="mymod_met")],
                actions=[GiveInfo(info="mymod_talked")],
            ),
            1: Phrase(
                id=1,
                text_ru="Возьму работу.",
                text_en="I will take the job.",
                preconditions=[HasItem(item_alias="mymod_item")],
                actions=[
                    GiveTask(task_id=QUEST_ID),
                    GiveItem(item_alias="mymod_reward", count=1),
                ],
            ),
            2: Phrase(
                id=2,
                text_ru="Готово.",
                text_en="Done.",
                actions=[CompleteTask(task_id=QUEST_ID)],
            ),
        },
    )
    return ModProject(
        name="XML Test",
        quests={QUEST_ID: quest},
        dialogs={DICT_KEY: dialog},
    )


def _find_dialog(root: ET.Element, dialog_id: str) -> ET.Element:
    """Находит ``<dialog id="...">`` в дереве.

    Args:
        root (ET.Element): Корень ``<game_dialogs>``.
        dialog_id (str): Искомый id.

    Returns:
        ET.Element: Найденный элемент.

    Raises:
        AssertionError: Если диалог отсутствует.
    """
    for element in root.findall("dialog"):
        if element.get("id") == dialog_id:
            return element
    raise AssertionError(f"Диалог id='{dialog_id}' не найден.")


def _find_phrase(dialog: ET.Element, phrase_id: str) -> ET.Element:
    """Находит ``<phrase id="...">`` внутри ``<phrase_list>``.

    Args:
        dialog (ET.Element): Элемент диалога.
        phrase_id (str): Искомый id реплики.

    Returns:
        ET.Element: Найденная реплика.

    Raises:
        AssertionError: Если ``<phrase_list>`` или реплика отсутствуют.
    """
    phrase_list = dialog.find("phrase_list")
    if phrase_list is None:
        raise AssertionError("У диалога нет обязательного <phrase_list>.")
    for phrase in phrase_list.findall("phrase"):
        if phrase.get("id") == phrase_id:
            return phrase
    raise AssertionError(f"Реплика id='{phrase_id}' не найдена.")


class TestXmlGeneratorDialogs(unittest.TestCase):
    """Проверка структуры ``dialogs_<mod>.xml``."""

    def setUp(self) -> None:
        """Готовит проект и XML-дерево перед каждым тестом."""
        self.project = _make_project()
        self.generator = XmlGenerator()
        self.xml = self.generator.generate_dialogs_xml(self.project.dialogs)
        self.root = ET.fromstring(self.xml)

    def test_root_and_dialog_id_from_model(self) -> None:
        """Корень ``game_dialogs``, id берётся из модели, не из ключа."""
        self.assertEqual(self.root.tag, "game_dialogs")
        dialog = _find_dialog(self.root, DIALOG_ID)
        self.assertEqual(dialog.get("id"), DIALOG_ID)
        self.assertIsNone(
            self.root.find(f"./dialog[@id='{DICT_KEY}']")
        )

    def test_every_dialog_contains_phrase_list(self) -> None:
        """У каждого ``<dialog>`` есть непустой ``<phrase_list>``."""
        for dialog in self.root.findall("dialog"):
            phrase_list = dialog.find("phrase_list")
            self.assertIsNotNone(phrase_list)
            self.assertGreater(len(phrase_list.findall("phrase")), 0)

    def test_next_tags_are_paired_and_integer(self) -> None:
        """Переходы записаны только как парные ``<next>ID</next>``."""
        phrase = _find_phrase(
            _find_dialog(self.root, DIALOG_ID), "0"
        )
        next_tags = phrase.findall("next")
        self.assertEqual([tag.text for tag in next_tags], ["1"])
        self.assertTrue(all(tag.attrib == {} for tag in next_tags))

    def test_dialog_level_infos_and_flat_precondition(self) -> None:
        """Info-условия остаются тегами, остальные уходят в ``can_take``."""
        dialog = _find_dialog(self.root, DIALOG_ID)
        self.assertEqual(
            dialog.findtext("has_info"), "mymod_available"
        )
        self.assertEqual(
            dialog.findtext("dont_has_info"), "mymod_blocked"
        )
        self.assertEqual(
            dialog.findtext("precondition"),
            f"dialogs.{DIALOG_ID}_can_take",
        )
        self.assertNotIn("mymod_quests", self.xml)

    def test_phrase_preconditions_and_actions(self) -> None:
        """Условия и эффекты фраз — только ``dialogs.<fn>``."""
        dialog = _find_dialog(self.root, DIALOG_ID)
        phrase_0 = _find_phrase(dialog, "0")
        phrase_1 = _find_phrase(dialog, "1")

        self.assertEqual(phrase_0.findtext("has_info"), "mymod_met")
        self.assertEqual(phrase_0.findtext("give_info"), "mymod_talked")

        actions_1 = [
            tag.text for tag in phrase_1.findall("action")
        ]
        self.assertEqual(
            actions_1,
            [f"dialogs.{DIALOG_ID}_phrase_1_action"],
        )
        self.assertEqual(
            phrase_1.findtext("precondition"),
            f"dialogs.{DIALOG_ID}_phrase_1_precondition",
        )

    def test_turn_in_dialog_gets_can_turn_in_precondition(self) -> None:
        """Диалог сдачи закрывается по стадии через ``_can_turn_in``."""
        project = _make_project()
        turnin_id = "mymod_xml_dialog_turnin"
        project.dialogs["turnin"] = Dialog(
            id=turnin_id,
            npc_id="esc_mayor",
            npc_location="escape",
            task_id=QUEST_ID,
            role="turnin",
            preconditions=[
                HasInfo(info="mymod_ready"),
                DontHasInfo(info="mymod_done"),
            ],
            phrases={
                0: Phrase(
                    id=0,
                    text_ru="Докладываю.",
                    text_en="Reporting.",
                )
            },
        )
        root = ET.fromstring(
            XmlGenerator().generate_dialogs_xml(project.dialogs)
        )
        dialog = _find_dialog(root, turnin_id)

        self.assertEqual(
            dialog.findtext("precondition"),
            f"dialogs.{turnin_id}_can_turn_in",
        )
        self.assertEqual(dialog.findtext("has_info"), "mymod_ready")
        self.assertEqual(dialog.findtext("dont_has_info"), "mymod_done")

    def test_turn_in_with_manual_non_info_condition_uses_can_take(self) -> None:
        """Ручное не-info условие оставляет общий ``_can_take``."""
        project = _make_project()
        turnin_id = "mymod_xml_dialog_turnin"
        project.dialogs["turnin"] = Dialog(
            id=turnin_id,
            task_id=QUEST_ID,
            role="turn_in",
            preconditions=[
                HasItem(item_alias="itm_pda_common"),
                DontHasInfo(info="mymod_done"),
            ],
            phrases={
                0: Phrase(
                    id=0,
                    text_ru="Вот ПДА.",
                    text_en="Here is the PDA.",
                )
            },
        )
        root = ET.fromstring(
            XmlGenerator().generate_dialogs_xml(project.dialogs)
        )
        dialog = _find_dialog(root, turnin_id)

        self.assertEqual(
            dialog.findtext("precondition"),
            f"dialogs.{turnin_id}_can_take",
        )

    def test_phrase_has_at_most_one_action(self) -> None:
        """Движок читает один ``<action>``: второй тег недопустим."""
        for dialog in self.root.findall("dialog"):
            for phrase in dialog.findall("./phrase_list/phrase"):
                with self.subTest(
                    phrase=f"{dialog.get('id')}/{phrase.get('id')}"
                ):
                    self.assertLessEqual(len(phrase.findall("action")), 1)

    def test_single_give_task_keeps_accept_effect(self) -> None:
        """Одиночный ``GiveTask`` остаётся ``dialogs.<id>_accept``."""
        project = _make_project()
        project.dialogs[DICT_KEY].phrases[1].actions = [
            GiveTask(task_id=QUEST_ID)
        ]
        root = ET.fromstring(
            XmlGenerator().generate_dialogs_xml(project.dialogs)
        )
        phrase_1 = _find_phrase(_find_dialog(root, DIALOG_ID), "1")
        self.assertEqual(
            [tag.text for tag in phrase_1.findall("action")],
            [f"dialogs.{DIALOG_ID}_accept"],
        )

    def test_give_info_stays_native_and_precedes_action(self) -> None:
        """``GiveInfo`` остаётся тегом и идёт перед единственным действием."""
        project = _make_project()
        project.dialogs[DICT_KEY].phrases[1].actions = [
            GiveInfo(info="mymod_extra"),
            GiveTask(task_id=QUEST_ID),
            GiveItem(item_alias="mymod_reward", count=1),
        ]
        root = ET.fromstring(
            XmlGenerator().generate_dialogs_xml(project.dialogs)
        )
        phrase_1 = _find_phrase(_find_dialog(root, DIALOG_ID), "1")
        self.assertEqual(phrase_1.findtext("give_info"), "mymod_extra")
        self.assertEqual(
            [tag.text for tag in phrase_1.findall("action")],
            [f"dialogs.{DIALOG_ID}_phrase_1_action"],
        )
        tags = [child.tag for child in phrase_1]
        self.assertLess(
            tags.index("give_info"),
            tags.index("action"),
        )

    def test_complete_task_uses_turn_in_effect(self) -> None:
        """``CompleteTask`` превращается в ``dialogs.<id>_turn_in``."""
        phrase_2 = _find_phrase(
            _find_dialog(self.root, DIALOG_ID), "2"
        )
        self.assertEqual(
            [tag.text for tag in phrase_2.findall("action")],
            [f"dialogs.{DIALOG_ID}_turn_in"],
        )

    def test_every_action_and_precondition_has_dialogs_prefix(self) -> None:
        """Любой функциональный тег имеет префикс ``dialogs.``."""
        for dialog in self.root.findall("dialog"):
            for tag_name in ("precondition",):
                for tag in dialog.findall(tag_name):
                    self.assertTrue(
                        (tag.text or "").startswith("dialogs."),
                        tag.text,
                    )
            for phrase in dialog.findall("./phrase_list/phrase"):
                for tag in phrase.findall("precondition"):
                    self.assertTrue(
                        (tag.text or "").startswith("dialogs."),
                        tag.text,
                    )
                for tag in phrase.findall("action"):
                    self.assertTrue(
                        (tag.text or "").startswith("dialogs."),
                        tag.text,
                    )

    def test_invalid_dialog_is_skipped(self) -> None:
        """Повреждённый диалог логируется и не ломает остальные."""
        broken = Dialog.model_construct(
            id="mymod_broken",
            dialog_id="mymod_broken",
            phrases=None,
        )
        dialogs = dict(self.project.dialogs)
        dialogs["broken"] = broken

        with self.assertLogs(
            "aqb.compiler.xml_gen", level="ERROR"
        ):
            xml = self.generator.generate_dialogs_xml(dialogs)

        self.assertIn(f'id="{DIALOG_ID}"', xml)
        self.assertNotIn('id="mymod_broken"', xml)

    def test_rejects_non_dict_dialogs(self) -> None:
        """Неверный тип карты диалогов даёт ``TypeError``."""
        with self.assertRaises(TypeError):
            self.generator.generate_dialogs_xml([])  # type: ignore[arg-type]


class TestXmlGeneratorStringTables(unittest.TestCase):
    """Проверка ``st_<mod>.xml`` для русского и английского языков."""

    def setUp(self) -> None:
        """Готовит таблицы строк для одного проекта."""
        self.project = _make_project()
        self.tables = XmlGenerator().generate_string_tables(self.project)

    def _string_map(self, language: str) -> dict[str, str]:
        """Возвращает ``id -> text`` для выбранного языка.

        Args:
            language (str): ``"rus"`` или ``"eng"``.

        Returns:
            dict[str, str]: Карта строк.
        """
        root = ET.fromstring(self.tables[language])
        return {
            element.get("id", ""): element.findtext("text", "")
            for element in root.findall("string")
        }

    def test_contains_all_quest_and_phrase_strings(self) -> None:
        """Таблицы содержат заголовки, описания, этапы и реплики."""
        expected = {
            f"{QUEST_ID}_title",
            f"{QUEST_ID}_descr",
            f"{QUEST_ID}_msg_reward",
            f"{QUEST_ID}_msg_fail",
            f"{QUEST_ID}_stage_0_title",
            f"{QUEST_ID}_stage_0_descr",
            f"{QUEST_ID}_stage_0_msg",
            f"{QUEST_ID}_stage_1_title",
            f"{QUEST_ID}_stage_1_descr",
            f"{QUEST_ID}_stage_1_msg",
            f"{DIALOG_ID}_phrase_0_text",
            f"{DIALOG_ID}_phrase_1_text",
            f"{DIALOG_ID}_phrase_2_text",
        }
        self.assertEqual(set(self._string_map("rus")), expected)
        self.assertEqual(set(self._string_map("eng")), expected)

    def test_russian_and_english_texts_are_separated(self) -> None:
        """Русский текст попадает только в ``rus``, английский — в ``eng``."""
        rus = self._string_map("rus")
        eng = self._string_map("eng")

        self.assertEqual(rus[f"{QUEST_ID}_title"], "Квест & проверка")
        self.assertEqual(eng[f"{QUEST_ID}_title"], "Quest & check")
        self.assertEqual(
            rus[f"{DIALOG_ID}_phrase_0_text"],
            "Здравствуй, сталкер!",
        )
        self.assertEqual(
            eng[f"{DIALOG_ID}_phrase_0_text"],
            "Hello, stalker!",
        )

    def test_xml_is_escaped_and_declares_cp1251(self) -> None:
        """Спецсимволы экранируются, декларация — windows-1251."""
        xml = self.tables["rus"]
        self.assertTrue(
            xml.startswith(
                '<?xml version="1.0" encoding="windows-1251"?>'
            )
        )
        self.assertIn("Квест &amp; проверка", xml)
        self.assertIn("Описание &lt;квеста&gt;", xml)
        self.assertNotIn("Квест & проверка", xml)

    def test_reward_and_fail_messages_have_defaults(self) -> None:
        """Без кастомных полей генерируются осмысленные подсказки."""
        rus = self._string_map("rus")
        eng = self._string_map("eng")

        self.assertEqual(
            rus[f"{QUEST_ID}_msg_reward"],
            "Задание выполнено: Квест & проверка.",
        )
        self.assertEqual(
            eng[f"{QUEST_ID}_msg_reward"],
            "Task completed: Quest & check.",
        )
        self.assertEqual(
            rus[f"{QUEST_ID}_msg_fail"],
            "Задание провалено: Квест & проверка.",
        )
        self.assertEqual(
            eng[f"{QUEST_ID}_msg_fail"],
            "Task failed: Quest & check.",
        )

    def test_custom_reward_and_fail_messages_override_defaults(self) -> None:
        """Поля ``Quest.msg_*`` имеют приоритет над автогенерацией."""
        quest = self.project.quests[QUEST_ID]
        quest.msg_reward_ru = "Награда получена."
        quest.msg_reward_en = "Reward received."
        quest.msg_fail_ru = "Квест провален."
        quest.msg_fail_en = "Quest failed."

        tables = XmlGenerator().generate_string_tables(self.project)
        rus = {
            element.get("id", ""): element.findtext("text", "")
            for element in ET.fromstring(tables["rus"]).findall("string")
        }
        eng = {
            element.get("id", ""): element.findtext("text", "")
            for element in ET.fromstring(tables["eng"]).findall("string")
        }

        self.assertEqual(rus[f"{QUEST_ID}_msg_reward"], "Награда получена.")
        self.assertEqual(eng[f"{QUEST_ID}_msg_reward"], "Reward received.")
        self.assertEqual(rus[f"{QUEST_ID}_msg_fail"], "Квест провален.")
        self.assertEqual(eng[f"{QUEST_ID}_msg_fail"], "Quest failed.")

    def test_generator_does_not_render_character_desc(self) -> None:
        """Генератор не создаёт ``character_desc_<mod>.xml``."""
        generator = XmlGenerator()
        self.assertFalse(
            hasattr(generator, "generate_character_desc_xml")
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
