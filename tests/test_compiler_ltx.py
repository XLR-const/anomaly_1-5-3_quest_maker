"""Тесты LTX-генератора, кодировки и экранирования XML.

Проверяются требования ``standart_of_auto.md`` (2.2):

* плоские имена функторов без префикса Lua-модуля;
* эффекты ``%=<task_id>_start()%`` со скобками вызова;
* отсутствие ``reward_money``/``reward_item`` в LTX;
* запись cp1251 без BOM и сохранение BOM для патченных файлов.

Запуск::

    .\\venv\\Scripts\\python.exe -m unittest tests.test_compiler_ltx -v
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

from src.compiler.encoding import (  # noqa: E402
    escape_xml_text,
    read_file_cp1251,
    write_file_cp1251,
)
from src.compiler.ltx_gen import LtxGenerator  # noqa: E402
from src.core.models import CustomSquad, Quest, Stage  # noqa: E402

VALID_QUEST_ID = "mymod_test_quest"
BROKEN_QUEST_ID = "mymod_broken_quest"
LTX_LOGGER_NAME = "aqb.compiler.ltx_gen"


def _make_quest(
    quest_id: str = VALID_QUEST_ID,
    *,
    is_storyline: bool = False,
    npc_id: str | None = None,
) -> Quest:
    """Создаёт минимальный валидный квест для проверки LTX.

    Args:
        quest_id (str): ID секции и ключ карты квестов.
        is_storyline (bool): Значение поля ``storyline``.
        npc_id (str | None): ID квестодателя; при задании добавляет
            ``condlist_0``.

    Returns:
        Quest: Валидная модель с одним этапом.
    """
    return Quest(
        id=quest_id,
        npc_id=npc_id,
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
        self.assertEqual(
            escape_xml_text('&<>"\''),
            "&amp;&lt;&gt;&quot;&apos;",
        )

    def test_ampersand_is_processed_before_generated_entities(self) -> None:
        """Амперсанд не портит уже созданные сущности."""
        escaped_tag = escape_xml_text("<tag>")
        self.assertEqual(escaped_tag, "&lt;tag&gt;")
        self.assertNotIn("&amp;lt;", escaped_tag)

    def test_mixed_russian_and_english_text_is_escaped(self) -> None:
        """Русский и английский текст с спецсимволами экранируется."""
        source = 'Сталкер & "Проводник" <esc.mayor_zhurov>'
        expected = (
            "Сталкер &amp; &quot;Проводник&quot; "
            "&lt;esc.mayor_zhurov&gt;"
        )
        self.assertEqual(escape_xml_text(source), expected)


class TestEncodingIO(unittest.TestCase):
    """Проверка записи/чтения cp1251 с BOM и без него."""

    def test_writes_cp1251_without_bom_by_default(self) -> None:
        """Сгенерированные файлы пишутся без BOM."""
        content = "Привет, сталкер!\r\nСтрока & < > \" '"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "deep" / "test.txt"
            write_file_cp1251(path, content)

            raw = path.read_bytes()
            self.assertFalse(raw.startswith(codecs.BOM_UTF8))
            self.assertEqual(raw, content.encode("windows-1251"))
            self.assertEqual(
                path.read_bytes().decode("windows-1251"), content
            )

    def test_writes_bom_when_requested(self) -> None:
        """Патченные ванильные файлы сохраняют BOM."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "system.ltx"
            write_file_cp1251(path, "[dialogs]\n", bom=True)

            raw = path.read_bytes()
            self.assertTrue(raw.startswith(codecs.BOM_UTF8))
            self.assertEqual(
                raw[len(codecs.BOM_UTF8) :],
                b"[dialogs]\n",
            )

    def test_read_file_cp1251_returns_text_and_bom_flag(self) -> None:
        """Чтение отделяет BOM от текста и сообщает о нём."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "system.ltx"
            path.write_bytes(codecs.BOM_UTF8 + b"[profiles]\n")

            text, has_bom = read_file_cp1251(path)
            self.assertTrue(has_bom)
            self.assertEqual(text, "[profiles]\n")

            path.write_bytes(b"[profiles]\n")
            text, has_bom = read_file_cp1251(path)
            self.assertFalse(has_bom)
            self.assertEqual(text, "[profiles]\n")


class TestLtxGenerator(unittest.TestCase):
    """Проверка генерации и отказоустойчивости ``LtxGenerator``."""

    def setUp(self) -> None:
        """Создаёт генератор перед каждым тестом."""
        self.generator = LtxGenerator()

    def test_generates_flat_functors_and_call_effects(self) -> None:
        """Секция использует плоские функторы и ``%=fn()%``-эффекты."""
        content = self.generator.generate_tasks_ltx(
            {VALID_QUEST_ID: _make_quest()}
        )
        quest_id = re.escape(VALID_QUEST_ID)

        self.assertRegex(content, rf"(?m)^\[{quest_id}\]$")
        self.assertRegex(
            content, r"(?m)^icon\s+=\s+ui_inGame2_Put_v_pripyat$"
        )
        self.assertRegex(content, r"(?m)^prior\s+=\s+60$")
        self.assertRegex(content, r"(?m)^storyline\s+=\s+false$")
        self.assertRegex(
            content, rf"(?m)^title\s+=\s+{quest_id}_title$"
        )
        self.assertRegex(
            content, rf"(?m)^descr\s+=\s+{quest_id}_descr$"
        )
        self.assertRegex(
            content, rf"(?m)^descr_functor\s+=\s+{quest_id}_descr$"
        )
        self.assertRegex(
            content, rf"(?m)^target_functor\s+=\s+{quest_id}_target$"
        )
        self.assertRegex(
            content, rf"(?m)^status_functor\s+=\s+{quest_id}_status$"
        )
        self.assertRegex(content, r"(?m)^stage_complete\s+=\s+1$")
        self.assertRegex(
            content, r"(?m)^dont_send_update_news\s+=\s+true$"
        )

        self.assertIn(
            f"on_init               = %={VALID_QUEST_ID}_start()%",
            content,
        )
        self.assertIn(
            f"on_complete           = %={VALID_QUEST_ID}_reward()%",
            content,
        )
        self.assertIn(
            f"on_fail               = %={VALID_QUEST_ID}_cleanup()%",
            content,
        )
        self.assertIn(
            f"on_cancel             = %={VALID_QUEST_ID}_cleanup()%",
            content,
        )
        self.assertNotIn("mymod_quests.", content)

    def test_reward_money_and_item_are_not_written_to_ltx(self) -> None:
        """Награда выдаётся Lua-эффектом, а не полями LTX."""
        quest = _make_quest().model_copy(
            update={
                "reward_money": 5000,
                "reward_item_alias": "medkit",
                "reward_item_count": 2,
            }
        )
        content = self.generator.generate_tasks_ltx({VALID_QUEST_ID: quest})

        self.assertNotIn("reward_money", content)
        self.assertNotIn("reward_item", content)

    def test_uses_custom_icon_and_prior(self) -> None:
        """Значения ``icon`` и ``prior`` берутся из модели."""
        quest = _make_quest().model_copy(
            update={"icon": "ui_inGame2_Nochnaya_ohota", "prior": 75}
        )
        content = self.generator.generate_tasks_ltx({VALID_QUEST_ID: quest})

        self.assertIn("icon                  = ui_inGame2_Nochnaya_ohota", content)
        self.assertIn("prior                 = 75", content)

    def test_adds_condlist_only_for_quest_with_giver(self) -> None:
        """``condlist_0`` появляется только при заданном NPC."""
        without_npc = self.generator.generate_tasks_ltx(
            {VALID_QUEST_ID: _make_quest()}
        )
        with_npc = self.generator.generate_tasks_ltx(
            {
                VALID_QUEST_ID: _make_quest(
                    npc_id="esc_mayor_zhurov"
                )
            }
        )

        self.assertNotIn("condlist_0", without_npc)
        self.assertIn(
            "condlist_0            = "
            "{!task_giver_alive(mymod_test_quest)} fail",
            with_npc,
        )

    def test_generates_storyline_true_when_requested(self) -> None:
        """``is_storyline=True`` превращается в ``storyline = true``."""
        quest = _make_quest(is_storyline=True)
        content = self.generator.generate_tasks_ltx({VALID_QUEST_ID: quest})
        self.assertIn("storyline             = true", content)

    def test_skips_broken_quest_and_keeps_valid(self) -> None:
        """Повреждённый квест пропускается, валидная секция сохраняется."""
        broken_quest = Quest.model_construct(
            id=BROKEN_QUEST_ID,
            is_storyline="некорректный-тип",
        )

        with self.assertLogs(LTX_LOGGER_NAME, level="ERROR") as captured:
            content = self.generator.generate_tasks_ltx(
                {
                    VALID_QUEST_ID: _make_quest(),
                    BROKEN_QUEST_ID: broken_quest,
                }
            )

        self.assertIn(f"[{VALID_QUEST_ID}]", content)
        self.assertNotIn(f"[{BROKEN_QUEST_ID}]", content)
        self.assertTrue(
            any(BROKEN_QUEST_ID in message for message in captured.output),
            "В лог должно попасть сообщение о пропущенном квесте.",
        )

    def test_returns_empty_for_empty_map(self) -> None:
        """Пустая карта квестов даёт пустой LTX-контент."""
        self.assertEqual(self.generator.generate_tasks_ltx({}), "")

    def test_rejects_non_dict_input(self) -> None:
        """Неверный тип карты квестов даёт ``TypeError``."""
        with self.assertRaises(TypeError):
            self.generator.generate_tasks_ltx([])  # type: ignore[arg-type]


class TestSquadDescrGenerator(unittest.TestCase):
    """Проверка генерации ``squad_descr_<slug>.ltx``."""

    def setUp(self) -> None:
        """Создаёт генератор перед каждым тестом."""
        self.generator = LtxGenerator()

    def test_generates_online_offline_group_section(self) -> None:
        """Секция повторяет эталон ``online_offline_group``."""
        squads = {
            "mymod_atp_bandit_leader_squad": CustomSquad(
                id="mymod_atp_bandit_leader_squad",
                faction="bandit",
                npc=["sim_default_bandit_4"],
            )
        }
        content = self.generator.generate_squads_ltx(squads)

        self.assertIn(
            "[mymod_atp_bandit_leader_squad]:online_offline_group", content
        )
        self.assertRegex(content, r"(?m)^faction = bandit$")
        self.assertRegex(content, r"(?m)^npc     = sim_default_bandit_4$")
        self.assertTrue(content.endswith("\n"))

    def test_optional_fields_and_multiple_npcs(self) -> None:
        """``target_smart``/``story_id`` и несколько NPC попадают в секцию."""
        squads = {
            "mymod_squad": CustomSquad(
                id="mymod_squad",
                faction="army",
                npc=["sim_default_army_1", "sim_default_army_2"],
                target_smart="esc_smart_terrain_7_11",
                story_id="mymod_story",
            )
        }
        content = self.generator.generate_squads_ltx(squads)

        self.assertIn(
            "npc     = sim_default_army_1, sim_default_army_2", content
        )
        self.assertIn("target_smart = esc_smart_terrain_7_11", content)
        self.assertIn("story_id = mymod_story", content)

    def test_empty_map_returns_empty_string(self) -> None:
        """При пустой карте файл не генерируется (пустая строка)."""
        self.assertEqual(self.generator.generate_squads_ltx({}), "")

    def test_rejects_non_dict_input(self) -> None:
        """Неверный тип карты отрядов даёт ``TypeError``."""
        with self.assertRaises(TypeError):
            self.generator.generate_squads_ltx([])  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main(verbosity=2)
