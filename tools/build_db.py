#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_db.py — сборка единой базы знаний по конфигам Anomaly 1.5.3.

Скрипт только читает _unpacked/configs и пересоздаёт data/anomaly_db.sqlite.

Запуск:
    python tools/build_db.py
    python tools/build_db.py --configs "D:\\Anomaly\\_unpacked\\configs" --db "data\\anomaly_db.sqlite"
    python tools/build_db.py --no-progress

Зависимости: стандартная библиотека Python 3.9+ и (необязательно) rich.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        TextColumn,
        TimeElapsedColumn,
    )

    _HAS_RICH = True
except Exception:  # rich не установлен — используем простой текстовый прогресс
    _HAS_RICH = False


# ---------------------------------------------------------------------------
# Пути и константы
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_CONFIGS = PROJECT_ROOT / "_unpacked" / "configs"
DEFAULT_DB = PROJECT_ROOT / "data" / "anomaly_db.sqlite"

# Сборка смешанная: большинство XML в windows-1251, но часть LTX/профилей
# сохранена в UTF-8. windows-1251 с errors="replace" остаётся надёжным
# fallback-декодером.
WINDOWS_1251 = "windows-1251"


# Справочник уровней. Ключи — канонические префиксы smart-террейнов/NPC.
LOCATIONS: Dict[str, str] = {
    "esc": "Кордон",
    "gar": "Свалка",
    "agr": "Агропром",
    "bar": "Бар",
    "mil": "Армейские склады",
    "zat": "Затон",
    "jup": "Юпитер",
    "pri": "Припять",
    "red": "Рыжий лес",
    "lim": "Лиманск",
    "rad": "Радар",
    "yan": "Янтарь",
    "val": "Тёмная долина",
    "marsh": "Болота",
    "mar": "Болота",
    "ds": "Тёмная лощина",
    "trucks": "Кладбище техники",
    "trc": "Кладбище техники",
    "aes": "ЧАЭС",
    # Дополнительные уровни/подлокации, встречающиеся в этой сборке.
    "aes2": "Север ЧАЭС",
    "gen": "Генераторы",
    "ros": "Дикая территория",
    "sar": "Саркофаг",
    "dead": "Мёртвый город",
    "hosp": "Заброшенный госпиталь",
    "katacomb": "Заброшенный госпиталь",
    "warlab": "Военная лаборатория",
    "lx8": "Лаборатория X-8",
    "x162": "Лаборатория X-16",
    "pas": "Путепровод «Припять-1»",
    "pol": "Поляна",
    # Общий fallback для сущностей без определяемого уровня.
    "zone": "Зона",
}

# Варианты написания префиксов -> канонический ключ LOCATIONS.
LOCATION_ALIASES: Dict[str, str] = {
    "escape": "esc",
    "agroprom": "agr",
    "agroprom_underground": "agr",
    "garbage": "gar",
    "darkvalley": "val",
    "dark_valley": "val",
    "darkscape": "ds",
    "military": "mil",
    "yantar": "yan",
    "pripyat": "pri",
    "zaton": "zat",
    "jupiter": "jup",
    "limansk": "lim",
    "rostok": "ros",
    "generators": "gen",
    "sarcofag": "sar",
    "underpass": "pas",
    "hospital": "hosp",
    "labx8": "lx8",
    "pole": "pol",
    "deadcity": "dead",
    "red_forest": "red",
    "redforest": "red",
    "marsh": "mar",
    "trucks": "trc",
    "trucks_cemetery": "trc",
    "ds2": "ds",
    "rad2": "rad",
    "aes2": "aes",
    "katacombs": "katacomb",
    # Уверенно определяемые подлокации, у которых первый токен ID не совпадает
    # с префиксом уровня.
    "novice": "esc",
    "atp": "esc",
    "elevator": "esc",
    "south": "esc",
    "north": "esc",
    "bar100rent": "bar",
    "yanbunker": "yan",
    "yancomplex": "yan",
    "dasc": "ds",
    "cit": "pri",
    "hotel": "pri",
}

SPECIAL_NPC_ROLES = {"trader", "mechanic", "medic", "leader", "guide"}

# ГОСТ-подобная транслитерация (нижний регистр).
TRANSLIT: Dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ї": "i", "є": "e", "ґ": "g", "ў": "u",
}


# ---------------------------------------------------------------------------
# Чтение файлов и строковые таблицы
# ---------------------------------------------------------------------------


def decode_bytes(data: bytes) -> str:
    """Декодирует cp1251/UTF-8, не падая на битых байтах."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig", errors="replace")

    head = data[:400].lower()
    if b"windows-1251" in head or b"cp1251" in head:
        return data.decode(WINDOWS_1251, errors="replace")

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(WINDOWS_1251, errors="replace")


def read_text(path: Path) -> str:
    try:
        return decode_bytes(path.read_bytes())
    except OSError:
        return ""


def xml_unescape(value: str) -> str:
    value = re.sub(
        r"&#x([0-9a-fA-F]+);",
        lambda m: chr(int(m.group(1), 16)),
        value,
    )
    value = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), value)
    for entity, char in (
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&apos;", "'"),
        ("&amp;", "&"),
    ):
        value = value.replace(entity, char)
    return value


def clean_text(value: str) -> str:
    """Убирает XML-теги/комментарии, служебные коды и лишние пробелы."""
    if not value:
        return ""
    value = re.sub(r"<!--.*?-->", " ", value, flags=re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = xml_unescape(value)
    value = value.replace("\\n", " ").replace("\\t", " ")
    value = re.sub(r"%c\[[^\]]*\]", " ", value, flags=re.I)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def unquote(value: str) -> str:
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()
    return value


STRING_RE = re.compile(
    r"<string\b[^>]*?\bid\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</string>",
    re.S | re.I,
)
TEXT_RE = re.compile(r"<text\b[^>]*>(.*?)</text>", re.S | re.I)
CYRILLIC_RE = re.compile(r"[А-Яа-яЁёІіЇїЄєҐґ]")


def has_cyrillic(value: str) -> bool:
    return bool(value and CYRILLIC_RE.search(value))


def parse_string_table(path: Path) -> Dict[str, str]:
    """Устойчивый разбор XML-таблицы строк (без ElementTree, чтобы не падать
    на #include, битых комментариях и неэкранированных символах)."""
    text = read_text(path)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    result: Dict[str, str] = {}
    for match in STRING_RE.finditer(text):
        string_id = match.group(2).strip()
        body = match.group(3)
        text_match = TEXT_RE.search(body)
        raw = text_match.group(1) if text_match else body
        value = clean_text(raw)
        if string_id:
            result[string_id] = value
    return result


def load_strings(configs: Path, progress) -> Dict[str, str]:
    strings: Dict[str, str] = {}
    files = sorted((configs / "text" / "rus").glob("*.xml"))
    task = progress.add_task("text/rus", total=len(files))
    for path in files:
        try:
            strings.update(parse_string_table(path))
        except Exception as exc:  # битый файл не должен останавливать сборку
            warn(f"string table skipped: {path.name}: {exc}")
        progress.advance(task)
    return strings


def load_smart_names(
    configs: Path,
    progress,
) -> Dict[str, str]:
    """Возвращает smart_id -> name_ru.

    ID в st_smart_names.xml имеют вид st_<smart_id>_name. Дополнительно
    проверяем text/eng: если там лежит русская строка, отсутствующая в rus,
    добавляем её.
    """
    candidates: Dict[str, str] = {}

    rus_path = configs / "text" / "rus" / "st_smart_names.xml"
    if rus_path.exists():
        candidates.update(parse_string_table(rus_path))

    eng_path = configs / "text" / "eng" / "st_smart_names.xml"
    if eng_path.exists():
        try:
            eng = parse_string_table(eng_path)
            for key, value in eng.items():
                if key not in candidates and has_cyrillic(value):
                    candidates[key] = value
        except Exception as exc:
            warn(f"eng smart names skipped: {exc}")

    result: Dict[str, str] = {}
    for string_id, value in candidates.items():
        if string_id.startswith("st_") and string_id.endswith("_name"):
            smart_id = string_id[3:-5]
            if smart_id:
                result[smart_id] = value
    return result


# ---------------------------------------------------------------------------
# LTX
# ---------------------------------------------------------------------------

SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(?::\s*(.*))?$")
KV_RE = re.compile(r"^\s*([A-Za-z0-9_$@#]+)\s*=\s*(.*)$")


def strip_ltx_comment(line: str) -> str:
    """Убирает ;-комментарий, не трогая ; внутри кавычек."""
    out: List[str] = []
    quote: Optional[str] = None
    for char in line:
        if quote is not None:
            out.append(char)
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
            out.append(char)
        elif char == ";":
            break
        else:
            out.append(char)
    return "".join(out)


def parse_ltx_files(
    files: Sequence[Path],
    progress,
    description: str,
) -> Tuple[Dict[str, dict], List[str]]:
    """Парсит все секции LTX. Возвращает словарь секций и порядок появления."""
    sections: Dict[str, dict] = {}
    order: List[str] = []
    task = progress.add_task(description, total=len(files))

    for path in files:
        text = read_text(path)
        current: Optional[str] = None
        last_key: Optional[str] = None

        for raw_line in text.splitlines():
            line = strip_ltx_comment(raw_line).strip()
            if not line or line.startswith("#"):
                continue

            section_match = SECTION_RE.match(line)
            if section_match:
                name = section_match.group(1).strip()
                parents: List[str] = []
                if section_match.group(2):
                    parents = [
                        part.strip()
                        for part in section_match.group(2).split(",")
                        if part.strip()
                    ]

                if name not in sections:
                    sections[name] = {
                        "parents": parents,
                        "values": {},
                        "source": path,
                        "order": len(order),
                    }
                    order.append(name)
                else:
                    sections[name]["parents"] = parents
                    # Значения накапливаем: поздние файлы переопределяют
                    # только реально указанные ключи.
                    sections[name]["source"] = path

                current = name
                last_key = None
                continue

            kv_match = KV_RE.match(line)
            if kv_match and current is not None:
                key = kv_match.group(1).lower()
                value = kv_match.group(2).strip()
                sections[current]["values"][key] = value
                last_key = key
                continue

            # Перенос длинного значения на следующую строку.
            if current is not None and last_key is not None and "=" not in line:
                sections[current]["values"][last_key] += " " + line

        progress.advance(task)

    return sections, order


def resolve_ltx_sections(sections: Dict[str, dict]) -> Dict[str, Dict[str, str]]:
    """Разворачивает наследование [child]:parent1,parent2 с защитой от циклов."""
    cache: Dict[str, Dict[str, str]] = {}

    def resolve(section_id: str, stack: frozenset) -> Dict[str, str]:
        if section_id in cache:
            return cache[section_id]
        if section_id in stack:
            return {}

        section = sections.get(section_id)
        if not section:
            return {}

        merged: Dict[str, str] = {}
        for parent in section.get("parents", []):
            merged.update(resolve(parent, stack | {section_id}))
        merged.update(section.get("values", {}))
        cache[section_id] = merged
        return merged

    for section_id in sections:
        resolve(section_id, frozenset())
    return cache


# ---------------------------------------------------------------------------
# NPC
# ---------------------------------------------------------------------------

SPECIFIC_RE = re.compile(
    r"<specific_character\b([^>]*)>(.*?)</specific_character>",
    re.S | re.I,
)
ID_ATTR_RE = re.compile(r"\bid\s*=\s*([\"'])(.*?)\1", re.S | re.I)
INCLUDE_RE = re.compile(r"#include\s+[\"']([^\"']+)[\"']", re.I)
ACTOR_DIALOG_RE = re.compile(
    r"<actor_dialog\b[^>]*>(.*?)</actor_dialog>", re.S | re.I
)
START_DIALOG_RE = re.compile(
    r"<start_dialog\b[^>]*>(.*?)</start_dialog>", re.S | re.I
)


def extract_xml_tag(text: str, tag: str) -> str:
    match = re.search(
        rf"<{re.escape(tag)}\b[^>]*>(.*?)</{re.escape(tag)}>",
        text,
        re.S | re.I,
    )
    return clean_text(match.group(1)) if match else ""


def extract_identity_tags(text: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for tag in ("name", "community", "class"):
        value = extract_xml_tag(text, tag)
        if value:
            result[tag] = value
    return result


def collect_include_identity_tags(
    text: str,
    configs: Path,
    text_cache: Dict[Path, str],
    tags_cache: Dict[Path, Dict[str, str]],
    depth: int = 0,
) -> Dict[str, str]:
    """Достаёт name/community/class из #include-профилей (рекурсивно)."""
    if depth > 8:
        return {}

    result: Dict[str, str] = {}
    for include in INCLUDE_RE.findall(text):
        relative = include.replace("\\", "/").lstrip("/")
        path = configs / relative
        if not path.exists():
            continue

        if path not in tags_cache:
            include_text = text_cache.get(path)
            if include_text is None:
                include_text = read_text(path)
                text_cache[path] = include_text
            tags = collect_include_identity_tags(
                include_text, configs, text_cache, tags_cache, depth + 1
            )
            tags.update(extract_identity_tags(include_text))
            tags_cache[path] = tags

        result.update(tags_cache[path])
    return result


def extract_dialogs(text: str) -> List[str]:
    dialogs = [
        match.group(1).strip()
        for match in ACTOR_DIALOG_RE.finditer(text)
        if match.group(1).strip()
    ]
    dialogs.extend(
        match.group(1).strip()
        for match in START_DIALOG_RE.finditer(text)
        if match.group(1).strip()
    )
    return dialogs


def resolve_string(value: str, strings: Dict[str, str]) -> str:
    value = unquote(clean_text(value))
    if not value:
        return ""
    return strings.get(value, value)


def canonical_location(token: str) -> Optional[str]:
    token = (token or "").strip().lower()
    if not token:
        return None
    token = LOCATION_ALIASES.get(token, token)
    return token if token in LOCATIONS else None


def location_from_id(entity_id: str) -> Optional[str]:
    token = re.split(r"[^a-z0-9]+", (entity_id or "").lower())[0]
    return canonical_location(token)


def npc_location(npc_id: str, source_path: Path) -> Optional[str]:
    location = location_from_id(npc_id)
    if location:
        return location

    suffix = source_path.stem
    prefix = "character_desc_"
    if suffix.startswith(prefix):
        suffix = suffix[len(prefix):]
    return canonical_location(suffix)


def detect_npc_role(
    npc_id: str,
    npc_class: str,
    name_raw: str,
    dialogs: Sequence[str],
) -> Optional[str]:
    identity = " ".join([npc_id, npc_class]).lower()
    haystack = " ".join([npc_id, npc_class, name_raw, *dialogs]).lower()

    # Это шаблон, а не конкретный генерал: слово "general" в ID не должно
    # делать его лидером.
    if npc_id == "stalker_general_default":
        return None

    # Явные признаки в ID/классе важнее диалогов: механик и медик часто
    # одновременно являются торговцами, но роль должна быть точнее.
    identity_keywords = (
        ("mechanic", ("mechanic", "механик")),
        ("medic", ("medic", "doctor", "feldsher", "медик", "доктор")),
        ("guide", ("guide", "guid", "проводник")),
        (
            "leader",
            (
                "leader",
                "boss",
                "glavar",
                "commander",
                "colonel",
                "general",
                "лидер",
                "главар",
            ),
        ),
        ("trader", ("trader", "barman", "торгов")),
    )
    for role, keywords in identity_keywords:
        if any(keyword in identity for keyword in keywords):
            return role

    # Затем — диалоги и имя.
    dialog_keywords = (
        ("mechanic", ("mechanic", "механик")),
        ("medic", ("medic", "doctor", "feldsher", "медик", "доктор")),
        ("guide", ("guide", "guid", "проводник")),
        (
            "leader",
            (
                "leader",
                "boss",
                "glavar",
                "commander",
                "colonel",
                "general",
                "лидер",
                "главар",
            ),
        ),
        ("trader", ("trader", "barman", "торгов")),
    )
    for role, keywords in dialog_keywords:
        if any(keyword in haystack for keyword in keywords):
            return role

    if dialogs:
        return "unique"

    if (
        npc_id.startswith("sim_")
        or npc_id.startswith("stalker_general_default")
        or name_raw.startswith("GENERATE_NAME_")
    ):
        return None
    return "unique"


def parse_npcs(
    configs: Path,
    strings: Dict[str, str],
    progress,
) -> List[Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str], str]]:
    files = sorted((configs / "gameplay").glob("character_desc_*.xml"))
    task = progress.add_task("NPC", total=len(files))

    rows: Dict[str, Tuple[int, tuple]] = {}
    text_cache: Dict[Path, str] = {}
    tags_cache: Dict[Path, Dict[str, str]] = {}

    for path in files:
        try:
            text = read_text(path)
        except Exception as exc:
            warn(f"character desc skipped: {path.name}: {exc}")
            progress.advance(task)
            continue

        text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
        source_file = str(path.relative_to(configs)).replace("/", "\\")

        for match in SPECIFIC_RE.finditer(text):
            id_match = ID_ATTR_RE.search(match.group(1))
            if not id_match:
                continue
            npc_id = id_match.group(2).strip()
            if not npc_id:
                continue

            body = match.group(2)
            body_tags = extract_identity_tags(body)
            include_tags = collect_include_identity_tags(
                body, configs, text_cache, tags_cache
            )

            name_raw = body_tags.get("name") or include_tags.get("name") or ""
            community = body_tags.get("community") or include_tags.get("community") or ""
            npc_class = body_tags.get("class") or include_tags.get("class") or ""

            # GENERATE_NAME_* — не готовая строка, а рантайм-генератор имени.
            name_ru = (
                ""
                if name_raw.startswith("GENERATE_NAME_")
                else resolve_string(name_raw, strings)
            )
            dialogs = extract_dialogs(body)
            role = detect_npc_role(npc_id, npc_class, name_raw, dialogs)
            location = npc_location(npc_id, path)

            row = (
                npc_id,
                name_ru or None,
                community or None,
                location,
                role,
                source_file,
            )

            # При дубликатах ID выбираем запись с максимумом заполненных полей,
            # отдавая предпочтение не-general файлам.
            score = (
                (10 if name_ru else 0)
                + (5 if community else 0)
                + (3 if role else 0)
                + (2 if location else 0)
                - (2 if "general" in path.name else 0)
            )
            previous = rows.get(npc_id)
            if previous is None or score > previous[0]:
                rows[npc_id] = (score, row)

        progress.advance(task)

    return [row for _, row in rows.values()]


# ---------------------------------------------------------------------------
# Отряды
# ---------------------------------------------------------------------------

def split_list(value: str) -> List[str]:
    value = unquote(value)
    if not value:
        return []
    result: List[str] = []
    for part in value.split(","):
        item = unquote(part.strip())
        if item:
            result.append(item)
    return result


def squad_tier(squad_id: str, has_story: bool) -> str:
    lowered = squad_id.lower()
    for tier in ("novice", "advanced", "veteran", "master", "unique"):
        if re.search(rf"(^|_){tier}(_|$)", lowered):
            return tier
    return "unique" if has_story else "unknown"


def looks_like_unique_npc(npc_id: str, unique_ids: set) -> bool:
    if npc_id in unique_ids:
        return True
    lowered = npc_id.lower()
    return any(
        keyword in lowered
        for keyword in (
            "trader",
            "barman",
            "mechanic",
            "medic",
            "leader",
            "guide",
            "guid",
            "boss",
        )
    )


def parse_squads(
    configs: Path,
    npcs: Sequence[tuple],
    progress,
) -> List[Tuple[str, Optional[str], Optional[str], int, Optional[str]]]:
    files = sorted((configs / "misc" / "squad_descr").glob("*.ltx"))
    sections, order = parse_ltx_files(files, progress, "Squads")
    resolved = resolve_ltx_sections(sections)

    unique_ids = {
        row[0] for row in npcs if row[4] in SPECIAL_NPC_ROLES
    }

    rows: List[Tuple[str, Optional[str], Optional[str], int, Optional[str]]] = []
    seen: set = set()

    for squad_id in order:
        if squad_id in seen:
            continue
        seen.add(squad_id)

        values = resolved.get(squad_id, {})
        if not values:
            continue

        faction = unquote(values.get("faction", ""))
        npc_list: List[str] = []
        for key in ("npc", "npc_random"):
            for npc_id in split_list(values.get(key, "")):
                if npc_id not in npc_list:
                    npc_list.append(npc_id)

        story_id = unquote(values.get("story_id", ""))
        target_smart = unquote(values.get("target_smart", ""))
        has_story_or_target = bool(story_id or target_smart)

        has_unique_npc = any(
            looks_like_unique_npc(npc_id, unique_ids) for npc_id in npc_list
        )
        is_safe = 0 if (has_story_or_target or has_unique_npc) else 1
        tier = squad_tier(squad_id, bool(story_id))

        rows.append(
            (
                squad_id,
                faction or None,
                tier,
                is_safe,
                ", ".join(npc_list) or None,
            )
        )

    return rows


# ---------------------------------------------------------------------------
# Предметы
# ---------------------------------------------------------------------------

def parse_int(value: str) -> Optional[int]:
    value = unquote(value or "")
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    if not match:
        return None
    try:
        return int(float(match.group(0)))
    except ValueError:
        return None


def is_true(value: str) -> bool:
    return unquote(value or "").strip().lower() in {"1", "true", "yes", "on"}


def classify_item(
    item_id: str,
    raw_section: dict,
    values: Dict[str, str],
) -> str:
    kind = unquote(values.get("kind", "")).lower()
    item_class = unquote(values.get("class", "")).lower()
    source = str(raw_section.get("source", "")).lower().replace("\\", "/")
    filename = Path(source).name
    parents = {parent.lower() for parent in raw_section.get("parents", [])}

    if kind == "i_quest" or "items_quest" in filename:
        return "quest"
    if kind.startswith("i_letter"):
        return "quest"
    if kind == "i_upgrade" or "upgr" in filename or "tch_upgr" in parents:
        return "upgrade"
    if (
        "addon" in filename
        or "attachment" in filename
        or "scope" in item_class
        or "silencer" in item_class
        or "suppressor" in item_class
    ):
        return "attachment"
    if kind.startswith("w_"):
        return "explosive" if kind == "w_explosive" else "weapon"
    if kind.startswith("o_"):
        return "armor"
    if kind.startswith("i_arty"):
        return "artefact"
    if kind.startswith("i_medical"):
        return "medical"
    if kind.startswith(("i_food", "i_drink")):
        return "food"
    if kind.startswith(("i_mutant", "i_part")):
        return "part"
    if kind.startswith("i_attach"):
        return "attachment"
    if kind.startswith(("i_tool", "i_kit")):
        return "tool"
    if kind.startswith("i_device"):
        return "device"
    if kind.startswith("i_backpack"):
        return "container"
    if kind.startswith("s_"):
        return "ammo"

    if item_class in {"ammo", "ammo_s"} or item_class.startswith("ammo"):
        return "ammo"
    if "artefact" in item_class or "artefact" in filename:
        return "artefact"
    if item_class.startswith("wp_") or "weapon" in filename:
        return "weapon"
    if (
        item_class in {"equ_stlk", "e_stlk", "e_hlmet", "eq_bakpk"}
        or "outfit" in filename
    ):
        return "armor"
    if item_class == "ii_attch":
        return "attachment"
    if item_class in {"ii_explo", "s_explo"} or item_class.startswith("g_"):
        return "explosive"
    if item_class.startswith("ii_food"):
        return "food"
    if item_class.startswith("ii_antir"):
        return "medical"
    if item_class.startswith(("d_", "det_")) or item_class == "torch_s":
        return "device"

    if "medical" in filename:
        return "medical"
    if "food" in filename or "drink" in filename:
        return "food"
    if "artefact" in filename:
        return "artefact"
    if "weapon" in filename:
        return "weapon"
    if "outfit" in filename:
        return "armor"

    return "misc"


def parse_items(
    configs: Path,
    strings: Dict[str, str],
    progress,
) -> List[Tuple[str, Optional[str], str, Optional[int], int]]:
    files = sorted((configs / "items").rglob("*.ltx"))
    sections, order = parse_ltx_files(files, progress, "Items")
    resolved = resolve_ltx_sections(sections)

    rows: List[Tuple[str, Optional[str], str, Optional[int], int]] = []
    seen: set = set()

    for item_id in order:
        if item_id in seen:
            continue
        seen.add(item_id)

        # Служебные секции-иконки не являются предметами.
        if item_id.lower().endswith("_ico"):
            continue

        raw_section = sections[item_id]
        values = resolved.get(item_id, {})
        inv_name = unquote(
            values.get("inv_name", "") or values.get("inv_name_short", "")
        )
        if not inv_name:
            continue

        category = classify_item(item_id, raw_section, values)
        name_ru = resolve_string(inv_name, strings)
        is_quest = 1 if (
            is_true(values.get("quest_item", "")) or category == "quest"
        ) else 0
        cost = parse_int(values.get("cost", ""))

        rows.append((item_id, name_ru or None, category, cost, is_quest))

    return rows


# ---------------------------------------------------------------------------
# Алиасы
# ---------------------------------------------------------------------------


def translit(value: str) -> str:
    lowered = (value or "").lower()
    out: List[str] = []
    for char in lowered:
        if char in TRANSLIT:
            out.append(TRANSLIT[char])
        elif "a" <= char <= "z" or "0" <= char <= "9":
            out.append(char)
        else:
            out.append("_")
    result = "".join(out)
    result = re.sub(r"_+", "_", result)
    return result.strip("_")


def looks_like_string_id(value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return True
    lowered = value.lower()
    if lowered.startswith("st_"):
        return True
    if not re.fullmatch(r"[A-Za-z0-9_]+", value):
        return False
    return (
        "_" in value
        or lowered.startswith(("esc_", "wpn_", "sim_", "gar_", "agr_"))
    )


def alias_name(name_ru: Optional[str], fallback_id: str) -> str:
    if name_ru and not looks_like_string_id(name_ru):
        return name_ru
    return fallback_id


class AliasGenerator:
    def __init__(self) -> None:
        self.used: set = set()

    def make(self, base: str) -> str:
        if "." in base:
            prefix, name = base.split(".", 1)
        else:
            prefix, name = "", base

        prefix = translit(prefix) or "zone"
        name = translit(name) or "unnamed"
        base = f"{prefix}.{name}"

        candidate = base
        suffix = 1
        while candidate in self.used:
            suffix += 1
            candidate = f"{base}_{suffix}"

        self.used.add(candidate)
        return candidate


def build_aliases(
    smarts: Sequence[Tuple[str, Optional[str], Optional[str]]],
    npcs: Sequence[Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str], str]],
    items: Sequence[Tuple[str, Optional[str], str, Optional[int], int]],
    squads: Sequence[Tuple[str, Optional[str], Optional[str], int, Optional[str]]],
) -> List[Tuple[str, str, str]]:
    generator = AliasGenerator()
    rows: List[Tuple[str, str, str]] = []

    for smart_id, name_ru, location in smarts:
        prefix = location or "zone"
        base = f"{prefix}.{alias_name(name_ru, smart_id)}"
        rows.append((generator.make(base), "smart", smart_id))

    for npc_id, name_ru, _faction, location, _role, _source in npcs:
        prefix = location or "zone"
        base = f"{prefix}.{alias_name(name_ru, npc_id)}"
        rows.append((generator.make(base), "npc", npc_id))

    for item_id, name_ru, category, _cost, _is_quest in items:
        base = f"{category}.{alias_name(name_ru, item_id)}"
        rows.append((generator.make(base), "item", item_id))

    for squad_id, faction, tier, is_safe, _npc_list in squads:
        if is_safe != 1:
            continue
        base = f"squad.{faction or 'unknown'}_{tier or 'unknown'}"
        rows.append((generator.make(base), "squad", squad_id))

    return rows


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------

SCHEMA = """
DROP TABLE IF EXISTS aliases;
DROP TABLE IF EXISTS items;
DROP TABLE IF EXISTS squads;
DROP TABLE IF EXISTS npcs;
DROP TABLE IF EXISTS smarts;
DROP TABLE IF EXISTS locations;

CREATE TABLE locations (
    prefix  TEXT PRIMARY KEY,
    name_ru TEXT
);

CREATE TABLE smarts (
    id               TEXT PRIMARY KEY,
    name_ru          TEXT,
    location_prefix  TEXT
);

CREATE TABLE npcs (
    id              TEXT PRIMARY KEY,
    name_ru         TEXT,
    faction         TEXT,
    location_prefix TEXT,
    role            TEXT,
    source_file     TEXT
);

CREATE TABLE squads (
    id             TEXT PRIMARY KEY,
    faction        TEXT,
    tier           TEXT,
    is_safe_field  INTEGER,
    npc_list       TEXT
);

CREATE TABLE items (
    id       TEXT PRIMARY KEY,
    name_ru  TEXT,
    category TEXT,
    cost     INTEGER,
    is_quest INTEGER
);

CREATE TABLE aliases (
    alias       TEXT PRIMARY KEY,
    entity_type TEXT,
    entity_id   TEXT
);

CREATE INDEX idx_npcs_faction  ON npcs(faction);
CREATE INDEX idx_npcs_location ON npcs(location_prefix);
CREATE INDEX idx_items_category ON items(category);
CREATE INDEX idx_aliases_entity ON aliases(entity_type, entity_id);
"""


def write_database(
    db_path: Path,
    locations: Sequence[Tuple[str, str]],
    smarts: Sequence[Tuple[str, Optional[str], Optional[str]]],
    npcs: Sequence[tuple],
    squads: Sequence[tuple],
    items: Sequence[tuple],
    aliases: Sequence[Tuple[str, str, str]],
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    try:
        connection.executescript(SCHEMA)
        connection.executemany(
            "INSERT OR REPLACE INTO locations(prefix, name_ru) VALUES (?, ?)",
            locations,
        )
        connection.executemany(
            "INSERT OR REPLACE INTO smarts(id, name_ru, location_prefix) VALUES (?, ?, ?)",
            smarts,
        )
        connection.executemany(
            "INSERT OR REPLACE INTO npcs"
            "(id, name_ru, faction, location_prefix, role, source_file) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            npcs,
        )
        connection.executemany(
            "INSERT OR REPLACE INTO squads"
            "(id, faction, tier, is_safe_field, npc_list) VALUES (?, ?, ?, ?, ?)",
            squads,
        )
        connection.executemany(
            "INSERT OR REPLACE INTO items(id, name_ru, category, cost, is_quest) "
            "VALUES (?, ?, ?, ?, ?)",
            items,
        )
        connection.executemany(
            "INSERT OR REPLACE INTO aliases(alias, entity_type, entity_id) "
            "VALUES (?, ?, ?)",
            aliases,
        )
        connection.commit()
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Прогресс и CLI
# ---------------------------------------------------------------------------


def warn(message: str) -> None:
    sys.stderr.write(f"[warn] {message}\n")


class NullProgress:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def add_task(self, description: str, total: int = 0) -> int:
        return 0

    def advance(self, task_id: int, advance: int = 1) -> None:
        return None


class TextProgress(NullProgress):
    def __init__(self) -> None:
        self.tasks: List[dict] = []

    def add_task(self, description: str, total: int = 0) -> int:
        self.tasks.append(
            {"description": description, "total": total, "done": 0}
        )
        return len(self.tasks) - 1

    def advance(self, task_id: int, advance: int = 1) -> None:
        task = self.tasks[task_id]
        task["done"] += advance
        total = task["total"]
        if total and (
            task["done"] % 50 == 0 or task["done"] >= total
        ):
            sys.stderr.write(
                f"\r{task['description']}: {task['done']}/{total}"
            )
            if task["done"] >= total:
                sys.stderr.write("\n")
            sys.stderr.flush()


def make_progress(use_progress: bool):
    if not use_progress:
        return NullProgress()
    if _HAS_RICH:
        return Progress(
            TextColumn("[cyan]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        )
    warn("rich не установлен — используется простой текстовый прогресс")
    return TextProgress()


def print_usage() -> None:
    print(
        "Usage: python tools/build_db.py "
        "[--configs PATH] [--db PATH] [--no-progress]"
    )


def parse_args(argv: Sequence[str]) -> Tuple[Path, Path, bool]:
    configs = DEFAULT_CONFIGS
    db_path = DEFAULT_DB
    use_progress = True

    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ("-h", "--help"):
            print_usage()
            raise SystemExit(0)
        if arg in ("--configs", "-c"):
            if index + 1 >= len(argv):
                raise SystemExit("--configs requires a path")
            configs = Path(argv[index + 1]).expanduser()
            index += 2
            continue
        if arg in ("--db", "-d"):
            if index + 1 >= len(argv):
                raise SystemExit("--db requires a path")
            db_path = Path(argv[index + 1]).expanduser()
            index += 2
            continue
        if arg == "--no-progress":
            use_progress = False
            index += 1
            continue
        raise SystemExit(f"Unknown argument: {arg}")

    return configs, db_path, use_progress


def main(argv: Sequence[str]) -> int:
    configs, db_path, use_progress = parse_args(argv)

    if not configs.is_dir():
        warn(f"configs directory not found: {configs}")
        return 1

    print(f"Configs: {configs}")
    print(f"DB:      {db_path}")

    with make_progress(use_progress) as progress:
        strings = load_strings(configs, progress)

        smart_names = load_smart_names(configs, progress)

        smarts: List[Tuple[str, Optional[str], Optional[str]]] = []
        smart_task = progress.add_task("Smart terrains", total=len(smart_names))
        for smart_id, name_ru in smart_names.items():
            smarts.append(
                (smart_id, name_ru or None, location_from_id(smart_id))
            )
            progress.advance(smart_task)

        npcs = parse_npcs(configs, strings, progress)
        squads = parse_squads(configs, npcs, progress)
        items = parse_items(configs, strings, progress)

        alias_task = progress.add_task(
            "Aliases",
            total=len(smarts) + len(npcs) + len(items) + len(squads),
        )
        aliases = build_aliases(smarts, npcs, items, squads)
        progress.advance(alias_task, len(smarts) + len(npcs) + len(items) + len(squads))

    locations = list(LOCATIONS.items())

    write_database(db_path, locations, smarts, npcs, squads, items, aliases)

    print()
    print(f"locations: {len(locations)}")
    print(f"smarts:    {len(smarts)}")
    print(f"npcs:      {len(npcs)}")
    print(f"squads:    {len(squads)}")
    print(f"items:     {len(items)}")
    print(f"aliases:   {len(aliases)}")
    print(f"Done:      {db_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        warn("interrupted")
        raise SystemExit(130)
