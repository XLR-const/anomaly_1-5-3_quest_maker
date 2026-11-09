"""Автоматические тесты компилятора LTX и слоя безопасной записи.

Запуск из корня проекта::

    python -m unittest tests.test_compiler_ltx -v
    python -m unittest discover -s tests -v

Тесты проверяют экранирование XML, запись текста в Windows-1251 без BOM,
а также успешную и отказоустойчивую генерацию секций ``tm_mymod.ltx``.
"""

from __future__ import annotations

import codecs
import re
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compiler.encoding import escape_xml_text, write_file_cp1251  # noqa: E402
from src.compiler.ltx_gen import LtxGenerator  # noqa: E402
from src.core.models import Quest, Stage  # noqa: E402

VALID_QUEST_ID = "mymod_test_quest"
BROKEN_QUEST_ID = "mymod_broken_quest"
LTX_LOGGER_NAME = "aqb.compiler.ltx_gen"


def _make_quest(
    quest_id: str = VALID_QUEST_ID,
    *,
    is_storyline: bool = True,
) -> Quest:
    """Создаёт минимальный валидный квест для проверки LTX-генератора.

    Args:
        quest_id (str):
            Идентификатор секции и одновременно ключ карты квестов.
        is_storyline (bool):
            Признак сюжетного квеста, записываемый в LTX.

    Returns:
        Quest: Валидная Pydantic-модель с одним этапом.
    """
    return Quest(
        id=quest_id,
        title_ru="Тестовый квест",
        title_en="Test quest",
        descr_ru="Описание тестового квеста",
        descr_en="Test quest description",
        is_storyline=is_storyline,
        stages={
            0: Stage(
                id=0,
                title_ru="Первый этап",
                title_en="First stage",
                descr_ru="Описание первого этапа",
                descr_en="First stage description",
                target_alias="esc.test_target",
            )
        },
    )


class TestEscapeXmlText(unittest.TestCase):
    """Проверка экранирования специальных символов XML."""

    def test_all_special_characters_are_escaped(self) -> None:
        """Пять спецсимволов заменяются на корректные XML-сущности."""
        source = '&<>"\''
        expected = "&amp;&lt;&gt;&quot;&apos;"

        self.assertEqual(escape_xml_text(source), expected)

    def test_ampersand_is_processed_before_generated_entities(self) -> None:
        """Амперсанд заменяется первым и не портит созданные сущности.

        Если сначала заменить угловые скобки, а потом амперсанд, результат
        ошибочно превратился бы в ``&amp;lt;...``. Корректный порядок должен
        дать ``&lt;...``.
        """
        escaped_tag = escape_xml_text("<tag>")

        self.assertEqual(escaped_tag, "&lt;tag&gt;")
        self.assertNotIn("&amp;lt;", escaped_tag)

    def test_mixed_russian_and_english_text_is_escaped(self) -> None:
        """Русский и английский текст с символами сохраняет порядок."""
        source = 'Сталкер & "Проводник" <esc.mayor_zhurov>'
        expected = (
            "Сталкер &amp; &quot;Проводник&quot; "
            "&lt;esc.mayor_zhurov&gt;"
        )

        self.assertEqual(escape_xml_text(source), expected)


class TestWriteFileCp1251(unittest.TestCase):
    """Проверка безопасной записи файлов в Windows-1251 без BOM."""

    def test_creates_parent_directories_and_writes_cp1251_without_bom(self) -> None:
        """Файл создаётся вместе с каталогами и читается без BOM."""
        content = (
            "Привет, сталкер!\r\n"
            "Тестовая строка с кириллицей и символами: & < > \" '"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "deep" / "test.txt"

            write_file_cp1251(path, content)

            self.assertTrue(path.parent.is_dir())
            self.assertTrue(path.is_file())

            raw = path.read_bytes()
            self.assertFalse(raw.startswith(codecs.BOM_UTF8))
            self.assertEqual(raw, content.encode("windows-1251"))

            with path.open(
                mode="r",
                encoding="windows-1251",
                newline="",
            ) as stream:
                decoded = stream.read()
            self.assertEqual(decoded, content)


class TestLtxGenerator(unittest.TestCase):
    """Проверка генерации и отказоустойчивости ``LtxGenerator``."""

    def setUp(self) -> None:
        """Создаёт генератор перед каждым тестом."""
        self.generator = LtxGenerator()

    def test_generate_tasks_ltx_for_valid_quest(self) -> None:
        """Валидный квест даёт полную секцию со всеми функторами."""
        content = self.generator.generate_tasks_ltx(
            {VALID_QUEST_ID: _make_quest()}
        )
        quest_id = re.escape(VALID_QUEST_ID)

        self.assertRegex(content, rf"(?m)^\[{quest_id}\]$")
        self.assertRegex(content, rf"(?m)^icon = ui_inGame2_Put_v_pripyat$")
        self.assertRegex(content, rf"(?m)^storyline = true$")
        self.assertRegex(
            content,
            rf"(?m)^title = {quest_id}_title$",
        )
        self.assertRegex(
            content,
            rf"(?m)^descr = {quest_id}_descr$",
        )
        self.assertIn(
            f"on_init = %=mymod_quests.{VALID_QUEST_ID}_on_init%",
            content,
        )
        self.assertIn(
            f"on_complete = %=mymod_quests.{VALID_QUEST_ID}_on_complete%",
            content,
        )
        self.assertIn(
            f"on_fail = %=mymod_quests.{VALID_QUEST_ID}_on_fail%",
            content,
        )
        self.assertIn(
            f"status_functor = "
            f"mymod_quests.{VALID_QUEST_ID}_status_functor",
            content,
        )
        self.assertIn(
            f"target_functor = "
            f"mymod_quests.{VALID_QUEST_ID}_target_functor",
            content,
        )

    def test_generate_tasks_ltx_skips_broken_quest_and_keeps_valid(self) -> None:
        """Повреждённый квест пропускается, валидная секция сохраняется."""
        broken_quest = Quest.model_construct(
            id=BROKEN_QUEST_ID,
            is_storyline="некорректный-тип",
        )

        with self.assertLogs(LTX_LOGGER_NAME, level="WARNING") as captured:
            content = self.generator.generate_tasks_ltx(
                {
                    VALID_QUEST_ID: _make_quest(),
                    BROKEN_QUEST_ID: broken_quest,
                }
            )

        self.assertIn(f"[{VALID_QUEST_ID}]", content)
        self.assertIn(
            f"status_functor = "
            f"mymod_quests.{VALID_QUEST_ID}_status_functor",
            content,
        )
        self.assertNotIn(f"[{BROKEN_QUEST_ID}]", content)
        self.assertTrue(
            any(BROKEN_QUEST_ID in message for message in captured.output),
            "В лог должно попасть сообщение о пропущенном квесте.",
        )

    def test_generate_tasks_ltx_uses_storyline_flag(self) -> None:
        """Значение ``is_storyline=False`` попадает в LTX как ``false``."""
        quest = _make_quest(is_storyline=False)

        content = self.generator.generate_tasks_ltx({VALID_QUEST_ID: quest})

        self.assertIn("storyline = false", content)
        self.assertNotIn("storyline = true", content)

    def test_generate_tasks_ltx_returns_empty_for_empty_map(self) -> None:
        """Пустая карта квестов даёт пустой LTX-контент."""
        self.assertEqual(self.generator.generate_tasks_ltx({}), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
