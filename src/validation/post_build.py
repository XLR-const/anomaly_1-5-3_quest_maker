"""Пост-проверка уже записанных артефактов мода.

Модуль намеренно лёгкий: он читает только сгенерированные файлы внутри
каталога сборки и не обращается к ``_unpacked/``. Цель — поймать ситуации,
когда XML ссылается на строковый ключ, которого нет или который пуст в
одной из таблиц ``text/rus|eng/st_<slug>.xml``.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

#: Теги, содержимое которых в сгенерированных XML является ключом строки.
_TEXT_TAGS = ("text", "title", "descr", "target")
#: Ключи LTX-секции квеста, значения которых — идентификаторы строк.
_LTX_STRING_KEYS = re.compile(
    r"^\s*(title|descr|target)\s*=\s*([^\s;]+)", re.IGNORECASE
)


def _read_cp1251(path: Path) -> str:
    """Читает файл в windows-1251 без изменения байтов."""
    return path.read_bytes().decode("windows-1251")


def _parse_xml(path: Path) -> ET.Element | None:
    """Парсит XML, возвращая ``None`` при ошибке чтения/разбора."""
    try:
        return ET.fromstring(_read_cp1251(path))
    except (OSError, UnicodeError, ET.ParseError):
        return None


def _string_table(path: Path) -> dict[str, str]:
    """Возвращает карту ``id -> текст`` таблицы строк."""
    root = _parse_xml(path)
    if root is None:
        return {}
    table: dict[str, str] = {}
    for element in root.iter("string"):
        entry_id = str(element.get("id") or "").strip()
        if entry_id:
            table[entry_id] = str(element.findtext("text") or "")
    return table


def _collect_xml_keys(root: ET.Element | None) -> list[str]:
    """Собирает непустые значения тегов ``text/title/descr/target``."""
    if root is None:
        return []
    keys: list[str] = []
    for element in root.iter():
        if element.tag not in _TEXT_TAGS:
            continue
        value = str(element.text or "").strip()
        if value:
            keys.append(value)
    return keys


def _collect_ltx_keys(text: str) -> list[str]:
    """Собирает значения ``title``/``descr``/``target`` из ``tm_*.ltx``."""
    keys: list[str] = []
    for line in text.splitlines():
        match = _LTX_STRING_KEYS.match(line)
        if not match:
            continue
        value = match.group(2).strip().strip('"').strip("'")
        if value and value not in {"nil", "true", "false"}:
            keys.append(value)
    return keys


def verify_built_mod(output_dir: Path, slug: str) -> list[str]:
    """Проверяет целостность строк и профилей собранного мода.

    Args:
        output_dir (Path): Каталог ``output/<slug>`` с готовой ``gamedata``.
        slug (str): Slug мода.

    Returns:
        list[str]: Человекочитаемые ошибки; пустой список означает успех.
    """
    root = Path(output_dir)
    if not slug or not root.is_dir():
        return [f"Каталог сборки не найден: '{root}'."]

    configs = root / "gamedata" / "configs"
    st_rus_path = configs / "text" / "rus" / f"st_{slug}.xml"
    st_eng_path = configs / "text" / "eng" / f"st_{slug}.xml"
    errors: list[str] = []

    if not st_rus_path.is_file():
        errors.append(f"Не найден файл локализации: '{st_rus_path}'.")
    if not st_eng_path.is_file():
        errors.append(f"Не найден файл локализации: '{st_eng_path}'.")
    if errors:
        return errors

    rus_table = _string_table(st_rus_path)
    eng_table = _string_table(st_eng_path)
    if not rus_table:
        errors.append(f"Пустая или повреждённая таблица: '{st_rus_path}'.")
    if not eng_table:
        errors.append(f"Пустая или повреждённая таблица: '{st_eng_path}'.")

    keys: list[str] = []
    dialogs_path = configs / "gameplay" / f"dialogs_{slug}.xml"
    if dialogs_path.is_file():
        keys.extend(_collect_xml_keys(_parse_xml(dialogs_path)))
    else:
        errors.append(f"Не найден файл диалогов: '{dialogs_path}'.")

    tasks_path = configs / "misc" / "task" / f"tm_{slug}.ltx"
    if tasks_path.is_file():
        try:
            keys.extend(_collect_ltx_keys(_read_cp1251(tasks_path)))
        except (OSError, UnicodeError) as exc:
            errors.append(f"Не читается '{tasks_path}': {exc}.")
    else:
        errors.append(f"Не найден файл заданий: '{tasks_path}'.")

    character_desc_path = configs / "gameplay" / f"character_desc_{slug}.xml"
    if character_desc_path.is_file():
        character_root = _parse_xml(character_desc_path)
        if character_root is None:
            errors.append(f"Повреждён XML: '{character_desc_path}'.")
        else:
            keys.extend(_collect_xml_keys(character_root))
            for name_element in character_root.iter("name"):
                name_key = str(name_element.text or "").strip()
                if name_key:
                    keys.append(name_key)
            for character in character_root.iter("specific_character"):
                character_id = str(character.get("id") or "<без id>")
                dialogs = {
                    str(element.text or "").strip()
                    for element in character.findall("actor_dialog")
                }
                if "actor_break_dialog" not in dialogs:
                    errors.append(
                        "В <specific_character id=\""
                        f"{character_id}\"> нет "
                        "<actor_dialog>actor_break_dialog</actor_dialog>."
                    )

    seen: set[str] = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        for language, table in (("rus", rus_table), ("eng", eng_table)):
            if key not in table:
                errors.append(
                    f"Ключ '{key}' отсутствует в st_{slug}.xml ({language})."
                )
            elif not table[key].strip():
                errors.append(
                    f"Ключ '{key}' пуст в st_{slug}.xml ({language})."
                )

    return list(dict.fromkeys(errors))


__all__ = ["verify_built_mod"]
