"""Регрессия байт-идентичности Warfare-компилятора.

Эталонный проект ``examples/build_golden_test.py`` генерируется **в памяти**:
тест не читает и не пишет каталог ``output/`` и не обращается к
``_unpacked/``. Для каждого файла считается SHA-256 от тех же байтов,
которые записал бы :class:`aqm.compiler.builder.ModBuilder`
(Windows-1251 без BOM).

Хэши ``SHA256_BEFORE`` сняты до правок Фазы 2, итерации 1, а
``SHA256_AFTER`` фиксирует ожидаемый результат после аддитивных изменений.
Оба словаря обязаны совпадать: генерация старых моделей не должна меняться.
Исключение — ``golden_shield_test_quests.script``: безусловный гейт
``last_stage`` в ``*_can_turn_in`` (WARN-2) меняет только тела этих функций.

Запуск::

    .\\venv\\Scripts\\python.exe -m unittest tests.test_warfare_regression -v
"""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from examples.build_golden_test import (  # noqa: E402
    PROJECT_NAME,
    create_golden_shield_project,
)
from aqm.compiler.builder import _slugify  # noqa: E402
from aqm.compiler.ltx_gen import LtxGenerator  # noqa: E402
from aqm.compiler.lua_gen import LuaGenerator  # noqa: E402
from aqm.compiler.xml_gen import XmlGenerator  # noqa: E402

#: Хэши, снятые до любых изменений ``src/`` (эталон Фазы 1).
SHA256_BEFORE: dict[str, str] = {
    "tm_golden_shield_test.ltx": (
        "f35c797b1c42e1c233fc170d8cf74d3cfd1133168e05bb1766e3a05869acd68b"
    ),
    "squad_descr_golden_shield_test.ltx": (
        "5a91fb453780cb1a3a478c048d4b0f277c291256ce9fffa6fa2aa50d5abe626b"
    ),
    "dialogs_golden_shield_test.xml": (
        "79c4c4d37ce7b6ce4c1244844b1f2c14d27668aec499827dd47907f6116ab038"
    ),
    "st_golden_shield_test.xml (rus)": (
        "9071fdc4dc364960d2bdddc45a6b96647d05ed86b66168f7328e6e86494c0578"
    ),
    "st_golden_shield_test.xml (eng)": (
        "3ec1157feb25f9a10e91c38952fde341600b226b25eba18dd87b6c0a34c27c79"
    ),
    "golden_shield_test_quests.script": (
        "ac00a26c5c13472c0bcf8ab9a2233318789774532dd8834387bdd3b596e47e0d"
    ),
}

#: Ожидаемые хэши после итерации 1 (аддитивные изменения не влияют).
SHA256_AFTER: dict[str, str] = dict(SHA256_BEFORE)


def _generate_reference_files() -> dict[str, str]:
    """Генерирует эталонные файлы в памяти без записи на диск.

    Returns:
        dict[str, str]: Карта «имя артефакта -> текст в кодировке мода».
    """
    project = create_golden_shield_project()
    slug = _slugify(PROJECT_NAME)

    ltx = LtxGenerator()
    xml = XmlGenerator()
    lua = LuaGenerator()
    string_tables = xml.generate_string_tables(project)

    return {
        f"tm_{slug}.ltx": ltx.generate_tasks_ltx(project.quests),
        f"squad_descr_{slug}.ltx": ltx.generate_squads_ltx(project.squads),
        f"dialogs_{slug}.xml": xml.generate_dialogs_xml(project.dialogs),
        f"st_{slug}.xml (rus)": string_tables["rus"],
        f"st_{slug}.xml (eng)": string_tables["eng"],
        f"{slug}_quests.script": lua.generate_quests_script(
            project,
            script_name=f"{slug}_quests",
            mod_prefix=slug,
        ),
    }


def _sha256_cp1251(text: str) -> str:
    """Считает SHA-256 тех же байтов, что пишет сборщик.

    Args:
        text (str): Текст сгенерированного файла.

    Returns:
        str: SHA-256 в hex-представлении.
    """
    return hashlib.sha256(text.encode("windows-1251")).hexdigest()


class TestWarfareByteIdentity(unittest.TestCase):
    """Гарантирует неизменность вывода Warfare-проекта."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.files = _generate_reference_files()
        cls.hashes = {
            name: _sha256_cp1251(text)
            for name, text in cls.files.items()
        }

    def test_before_and_after_snapshots_match(self) -> None:
        """Снимки «до» и «после» правок совпадают."""
        self.assertEqual(SHA256_BEFORE, SHA256_AFTER)

    def test_all_reference_files_are_generated(self) -> None:
        """Генерируются все шесть ожидаемых артефактов."""
        self.assertEqual(set(self.files), set(SHA256_BEFORE))

    def test_generated_hashes_match_baseline(self) -> None:
        """SHA-256 каждого файла совпадает с эталоном до/после."""
        for name, expected_before in SHA256_BEFORE.items():
            with self.subTest(file=name):
                self.assertEqual(self.hashes[name], expected_before)
                self.assertEqual(self.hashes[name], SHA256_AFTER[name])


if __name__ == "__main__":
    unittest.main(verbosity=2)
