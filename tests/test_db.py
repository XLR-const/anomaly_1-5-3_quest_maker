"""Автоматические тесты слоя ``GameDatabase``.

Запуск из корня проекта::

    python -m unittest discover -s tests -v
    python -m unittest tests.test_db -v
"""

from __future__ import annotations

import contextlib
import io
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db.repository import GameDatabase  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "anomaly_db.sqlite"


class TestGameDatabase(unittest.TestCase):
    """Калибровка и проверка публичного API репозитория."""

    def setUp(self) -> None:
        self.db = GameDatabase(DB_PATH)

    def tearDown(self) -> None:
        if not self.db._closed:
            self.db.conn.close()

    # ------------------------------------------------------------------
    # Инициализация и контекстный менеджер
    # ------------------------------------------------------------------

    def test_initialization_success(self) -> None:
        """Успешное подключение к реальной базе проекта."""
        self.assertTrue(DB_PATH.exists())
        self.assertIsInstance(self.db.conn, sqlite3.Connection)
        self.assertIsNotNone(self.db.find_npc_by_alias("esc.mayor_zhurov"))

    def test_initialization_missing_file(self) -> None:
        """Отсутствующий файл БД должен давать FileNotFoundError."""
        missing = Path(tempfile.gettempdir()) / f"aqb_missing_{uuid.uuid4().hex}.sqlite"
        self.assertFalse(missing.exists())
        with self.assertRaises(FileNotFoundError):
            GameDatabase(missing)

    def test_context_manager_closes_connection(self) -> None:
        """После выхода из ``with`` соединение гарантированно закрыто."""
        with GameDatabase(DB_PATH) as db:
            connection = db.conn
            self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)

        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")

    # ------------------------------------------------------------------
    # Точечный поиск
    # ------------------------------------------------------------------

    def test_find_npc_by_alias(self) -> None:
        npc = self.db.find_npc_by_alias("esc.mayor_zhurov")
        self.assertIsInstance(npc, dict)
        self.assertEqual(npc["entity_type"], "npc")
        self.assertEqual(npc["id"], "esc_3_16_military_trader")
        self.assertEqual(npc["alias"], "esc.mayor_zhurov")
        self.assertIn("Журов", npc["name_ru"])

    def test_find_item_by_alias(self) -> None:
        item = self.db.find_item_by_alias("weapon.vssk_vykhlop")
        self.assertIsInstance(item, dict)
        self.assertEqual(item["entity_type"], "item")
        self.assertEqual(item["id"], "wpn_vssk")
        self.assertEqual(item["alias"], "weapon.vssk_vykhlop")
        self.assertIn("Выхлоп", item["name_ru"])

    def test_find_smart_by_alias(self) -> None:
        smart = self.db.find_smart_by_alias("esc.yuzhnyy_blokpost")
        self.assertIsInstance(smart, dict)
        self.assertEqual(smart["entity_type"], "smart")
        self.assertEqual(smart["id"], "esc_smart_terrain_3_16")

    def test_find_squad_by_alias(self) -> None:
        squad = self.db.find_squad_by_alias("squad.army_novice")
        self.assertIsInstance(squad, dict)
        self.assertEqual(squad["entity_type"], "squad")
        self.assertEqual(squad["id"], "army_sim_squad_novice")
        self.assertEqual(squad["is_safe_field"], 1)
        self.assertIsInstance(squad["npc_members"], list)
        self.assertGreater(len(squad["npc_members"]), 0)

    def test_missing_alias_returns_none(self) -> None:
        missing = "__definitely_missing_alias__"
        self.assertIsNone(self.db.find_npc_by_alias(missing))
        self.assertIsNone(self.db.find_smart_by_alias(missing))
        self.assertIsNone(self.db.find_item_by_alias(missing))
        self.assertIsNone(self.db.find_squad_by_alias(missing))

    def test_wrong_entity_type_alias_returns_none(self) -> None:
        # Алиас предмета не должен находиться как NPC.
        self.assertIsNone(self.db.find_npc_by_alias("weapon.vssk_vykhlop"))

    # ------------------------------------------------------------------
    # Живой поиск
    # ------------------------------------------------------------------

    def test_search_assets_by_item_name_cyrillic(self) -> None:
        results = self.db.search_assets("выхлоп", entity_type="item")
        self.assertGreater(len(results), 0)
        self.assertTrue(all(item["entity_type"] == "item" for item in results))
        self.assertTrue(any("Выхлоп" in item["name_ru"] for item in results))

    def test_search_assets_by_squad_faction(self) -> None:
        results = self.db.search_assets("army", entity_type="squads")
        self.assertGreater(len(results), 0)
        self.assertTrue(all(item["entity_type"] == "squad" for item in results))
        self.assertTrue(any(item.get("faction") == "army" for item in results))

    def test_search_assets_unknown_type_returns_empty(self) -> None:
        self.assertEqual(self.db.search_assets("stalker", entity_type="vehicle"), [])

    def test_search_assets_empty_query_returns_empty(self) -> None:
        self.assertEqual(self.db.search_assets("   "), [])

    # ------------------------------------------------------------------
    # Группировки и системный экспорт
    # ------------------------------------------------------------------

    def test_get_locations(self) -> None:
        locations = self.db.get_locations()
        self.assertGreater(len(locations), 0)
        self.assertTrue(all({"prefix", "name_ru"} <= set(loc) for loc in locations))

    def test_get_smart_terrains_by_location(self) -> None:
        smarts = self.db.get_smart_terrains_by_location("esc")
        self.assertGreater(len(smarts), 0)
        self.assertTrue(all(smart["location_prefix"] == "esc" for smart in smarts))

    def test_get_npcs_by_location(self) -> None:
        npcs = self.db.get_npcs_by_location("esc")
        self.assertGreater(len(npcs), 0)
        self.assertTrue(all(npc["location_prefix"] == "esc" for npc in npcs))

    def test_get_safe_squads_by_faction(self) -> None:
        squads = self.db.get_safe_squads_by_faction("army")
        self.assertGreater(len(squads), 0)
        for squad in squads:
            with self.subTest(squad=squad["id"]):
                self.assertEqual(squad["faction"], "army")
                self.assertEqual(squad["is_safe_field"], 1)

    def test_get_all_valid_aliases(self) -> None:
        aliases = self.db.get_all_valid_aliases()
        self.assertIsInstance(aliases, set)
        self.assertGreater(len(aliases), 0)
        self.assertTrue(all(isinstance(alias, str) for alias in aliases))
        self.assertIn("esc.mayor_zhurov", aliases)
        self.assertIn("weapon.vssk_vykhlop", aliases)

    # ------------------------------------------------------------------
    # Превью
    # ------------------------------------------------------------------

    def test_print_assets_table(self) -> None:
        assets = self.db.search_assets("vssk", entity_type="item")[:1]
        assets += self.db.get_safe_squads_by_faction("army")[:1]

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.db.print_assets_table(assets, title="Тестовое превью")

        output = buffer.getvalue()
        self.assertIn("Тестовое превью", output)
        self.assertIn("Предмет", output)
        self.assertIn("Отряд", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
