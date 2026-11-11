"""Оркестратор сборки мода и текстовый патчер ванильных конфигов.

Модуль реализует шаги ``[3] PLAN`` и ``[7] EMIT`` из
``standart_of_auto.md`` (раздел 1):

* генерирует собственные файлы мода (``tm_<slug>.ltx``,
  ``dialogs_<slug>.xml``, ``st_<slug>.xml``, ``<slug>_quests.script``);
* копирует ванильный ``configs/system.ltx`` в ``build_root/gamedata`` и
  дописывает ``dialogs_<slug>`` в ``[dialogs] files`` и нужные
  ``character_desc_<level>`` в ``[profiles] specific_characters_files``;
* копирует ванильные ``configs/gameplay/character_desc_<level>.xml`` и
  вставляет ``<actor_dialog>ID</actor_dialog>`` в нужные
  ``<specific_character>`` **текстово**, без DOM-пересериализации.

DLTX, ``.ext``-директивы и динамическая Lua-инъекция диалогов не
используются: движок получает уже пропатченные копии ванильных файлов.

Все записи выполняются в кодировке Windows-1251. Сгенерированные файлы
пишутся без BOM, а унаследованные патченные файлы сохраняют исходный BOM
(``standart_of_auto.md``, 1.2, 1.3, 2.1).
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Sequence

from src.compiler.encoding import (
    read_file_cp1251,
    write_file_cp1251,
)
from src.compiler.ltx_gen import LtxGenerator
from src.compiler.lua_gen import LuaGenerator
from src.compiler.xml_gen import XmlGenerator
from src.logger import get_logger

if TYPE_CHECKING:
    from src.core.models import Dialog, ModProject, Quest
    from src.db.repository import GameDatabase

logger = get_logger("compiler.builder")

#: Таблица транслитерации для безопасного имени каталога и файлов мода.
_TRANSLITERATION = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
        "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
        "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
        "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "yu", "я": "ya", "і": "i", "ї": "yi", "є": "ye",
        "ґ": "g",
    }
)
_SEPARATOR_PATTERN = re.compile(r"[\s\-]+")
_FORBIDDEN_SLUG_PATTERN = re.compile(r"[^a-z0-9_]+")
_REPEATED_UNDERSCORES_PATTERN = re.compile(r"_+")

#: Каталоги, которые обязаны существовать в сборочной копии ``gamedata``.
_PROJECT_DIRECTORIES = (
    Path("gamedata") / "configs",
    Path("gamedata") / "configs" / "misc" / "task",
    Path("gamedata") / "configs" / "gameplay",
    Path("gamedata") / "configs" / "text" / "rus",
    Path("gamedata") / "configs" / "text" / "eng",
    Path("gamedata") / "scripts",
)

#: Порядок ролей диалогов при вставке ``<actor_dialog>`` (стандарт, 1.3).
_ROLE_ORDER = {
    "take": 0,
    "take_assault": 1,
    "take_solo": 2,
    "turnin": 3,
    "turn_in": 3,
    "branch": 4,
}


class BuildError(RuntimeError):
    """Критическая ошибка структуры проекта или патча ванильного файла.

    Исключение поднимается, когда продолжать сборку нельзя без угадывания:
    в ``system.ltx`` нет обязательной секции/ключа, ванильный
    ``character_desc_<level>.xml`` отсутствует, ``<specific_character>`` не
    найден или найден более одного раза, у NPC не задана локация и т. п.
    """


@dataclass(frozen=True)
class _DialogBinding:
    """Одна привязка ``<dialog id>`` к профилю NPC.

    Attributes:
        level (str): Имя локации без префикса ``character_desc_``
            (``escape``, ``zaton``, ...).
        npc_id (str): Значение ``<specific_character id="...">``.
        dialog_id (str): Значение ``<actor_dialog>...``.
        role (str): Роль диалога (``take``, ``turnin``, ...).
        order (int): Исходная позиция в проекте для стабильной сортировки.
    """

    level: str
    npc_id: str
    dialog_id: str
    role: str
    order: int


def _slugify(name: str) -> str:
    """Преобразует имя проекта в безопасный ASCII-slug.

    Slug используется как имя каталога сборки и префикс всех файлов мода
    (``tm_<slug>.ltx``, ``dialogs_<slug>.xml`` и т. д.), поэтому в нём
    разрешены только ``a-z``, цифры и ``_``.

    Args:
        name (str): Человекочитаемое имя проекта (может быть кириллицей).

    Returns:
        str: Нижний регистр, транслитерация, пробелы/дефисы заменены на
        ``_``, недопустимые символы удалены. Если не осталось ни одного
        допустимого символа, возвращается ``"mod"``.

    Raises:
        TypeError: Если ``name`` не является строкой.
    """
    if not isinstance(name, str):
        raise TypeError(
            f"Имя проекта должно быть строкой, получено "
            f"{type(name).__name__}."
        )
    normalized = name.strip().lower()
    transliterated = normalized.translate(_TRANSLITERATION)
    separated = _SEPARATOR_PATTERN.sub("_", transliterated)
    slug = _FORBIDDEN_SLUG_PATTERN.sub("", separated)
    slug = _REPEATED_UNDERSCORES_PATTERN.sub("_", slug).strip("_")
    if not slug:
        logger.warning(
            "Имя %r не содержит допустимых символов, используется 'mod'.",
            name,
        )
        slug = "mod"
    return slug


def _detect_newline(text: str) -> str:
    """Определяет доминирующий перенос строк в тексте.

    Патченные ванильные файлы должны сохранять исходный стиль переноса,
    иначе diff становится шумным, а некоторые редакторы ломают LTX.

    Args:
        text (str): Исходный текст файла.

    Returns:
        str: ``"\\r\\n"``, если в тексте есть CRLF; иначе ``"\\r"``, если
        есть одиночный CR; иначе ``"\\n"``.
    """
    if "\r\n" in text:
        return "\r\n"
    if "\r" in text:
        return "\r"
    return "\n"


def _line_ending(line: str) -> str:
    """Возвращает фактическое окончание одной физической строки.

    Args:
        line (str): Строка, полученная через ``splitlines(keepends=True)``.

    Returns:
        str: ``"\\r\\n"``, ``"\\r"``, ``"\\n"`` или пустая строка.
    """
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    if line.endswith("\r"):
        return "\r"
    return ""


class ModBuilder:
    """Собирает установочную структуру мода Anomaly для Mod Organizer 2.

    Attributes:
        output_dir (Path): Корень, внутри которого создаётся каталог
            ``<slug>`` с готовой ``gamedata``.
        db_client (GameDatabase | None): Необязательный клиент SQLite,
            передаваемый генератору Lua для будущих проверок ассетов.
        vanilla_root (Path): Корень распакованной ванильной игры. По
            умолчанию ``_unpacked``; тесты обязаны передавать временную
            копию и не читать реальный ``_unpacked``.
    """

    def __init__(
        self,
        output_dir: Path = Path("output"),
        db_client: "GameDatabase | None" = None,
        vanilla_root: Path = Path("_unpacked"),
    ) -> None:
        """Инициализирует сборщик путями вывода и ванильных исходников.

        Args:
            output_dir (Path):
                Корень сборки. Внутри создаётся каталог ``<slug>``.
            db_client (GameDatabase | None):
                Необязательный клиент БД для :class:`LuaGenerator`.
            vanilla_root (Path):
                Каталог ``_unpacked`` с ванильными ``configs``. Может быть
                подменён временным деревом в тестах.

        Raises:
            TypeError: Если ``output_dir`` или ``vanilla_root`` не являются
                ``str``/``Path``.
        """
        if not isinstance(output_dir, (str, Path)):
            raise TypeError(
                f"output_dir должен быть Path или str, получено "
                f"{type(output_dir).__name__}."
            )
        if not isinstance(vanilla_root, (str, Path)):
            raise TypeError(
                f"vanilla_root должен быть Path или str, получено "
                f"{type(vanilla_root).__name__}."
            )
        self.output_dir = Path(output_dir)
        self.db_client = db_client
        self.vanilla_root = Path(vanilla_root)
        logger.info(
            "ModBuilder инициализирован: output='%s', vanilla='%s', БД=%s.",
            self.output_dir,
            self.vanilla_root,
            type(db_client).__name__ if db_client else "не передана",
        )

    # ------------------------------------------------------------------
    # Публичная точка входа
    # ------------------------------------------------------------------

    def build_project(self, project: "ModProject") -> bool:
        """Собирает полный установочный каталог мода.

        Порядок шагов соответствует ``standart_of_auto.md``:

        1. Проверить ``name``/``quests``/``dialogs`` и вычислить slug.
        2. Очистить старый каталог ``output/<slug>`` и создать структуру
           ``gamedata``.
        3. Отрендерить собственные LTX/XML/Lua-файлы генераторами.
        4. Собрать привязки ``dialog → specific_character`` и скопировать
           ванильные ``character_desc_<level>.xml`` с вставленными
           ``<actor_dialog>``.
        5. Скопировать ванильный ``system.ltx`` и пропатчить секции
           ``[dialogs]`` и ``[profiles]``.
        6. Записать все файлы в cp1251, проверив их физическое наличие.

        Args:
            project (ModProject):
                Полностью валидный проект мода.

        Returns:
            bool: ``True`` при успешной сборке; ``False`` при любой
            критической ошибке (исключение журналируется).
        """
        project_name = getattr(project, "name", "<без имени>")
        logger.info("Начата сборка проекта '%s'.", project_name)
        try:
            name = getattr(project, "name", None)
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Непустое строковое поле name обязательно.")
            quests = getattr(project, "quests", None)
            dialogs = getattr(project, "dialogs", None)
            if not isinstance(quests, dict) or not isinstance(dialogs, dict):
                raise TypeError(
                    f"quests и dialogs должны быть dict, получены "
                    f"{type(quests).__name__} и {type(dialogs).__name__}."
                )

            slug = _slugify(name)
            project_dir = self.output_dir / slug
            self._prepare_project_directory(project_dir)

            ltx = LtxGenerator()
            xml = XmlGenerator()
            lua = LuaGenerator(db_client=self.db_client)

            tasks_content = ltx.generate_tasks_ltx(quests)
            dialogs_content = xml.generate_dialogs_xml(dialogs)
            string_tables = xml.generate_string_tables(project)
            script_content = lua.generate_quests_script(
                project,
                script_name=f"{slug}_quests",
                mod_prefix=slug,
            )

            if not isinstance(string_tables, dict):
                raise TypeError("Генератор локализации вернул не dict.")
            rus = string_tables.get("rus")
            eng = string_tables.get("eng")
            if not isinstance(rus, str) or not isinstance(eng, str):
                raise ValueError(
                    "Генератор локализации не вернул 'rus' и 'eng'."
                )

            files: dict[Path, str] = {
                project_dir / "gamedata" / "configs" / "misc" / "task"
                / f"tm_{slug}.ltx": tasks_content,
                project_dir / "gamedata" / "configs" / "gameplay"
                / f"dialogs_{slug}.xml": dialogs_content,
                project_dir / "gamedata" / "configs" / "text" / "rus"
                / f"st_{slug}.xml": rus,
                project_dir / "gamedata" / "configs" / "text" / "eng"
                / f"st_{slug}.xml": eng,
                project_dir / "gamedata" / "scripts"
                / f"{slug}_quests.script": script_content,
            }

            bindings = self._collect_dialog_bindings(project)
            patched_descriptions = self._patch_character_desc_files(
                bindings
            )
            system_content = self._build_patched_system_ltx(
                slug,
                tuple(
                    f"character_desc_{level}"
                    for level in patched_descriptions
                ),
            )

            for path, content in files.items():
                if not isinstance(content, str):
                    raise TypeError(
                        f"Содержимое '{path}' не строка: "
                        f"{type(content).__name__}."
                    )
                write_file_cp1251(path, content)
                self._ensure_written(path)

            system_path = (
                project_dir / "gamedata" / "configs" / "system.ltx"
            )
            write_file_cp1251(
                system_path,
                system_content[0],
                bom=system_content[1],
            )
            self._ensure_written(system_path)

            gameplay_dir = (
                project_dir / "gamedata" / "configs" / "gameplay"
            )
            for level, (content, has_bom) in patched_descriptions.items():
                target = gameplay_dir / f"character_desc_{level}.xml"
                write_file_cp1251(target, content, bom=has_bom)
                self._ensure_written(target)

            total = (
                len(files)
                + 1
                + len(patched_descriptions)
            )
            logger.info(
                "Сборка '%s' завершена: файлов=%d, каталог='%s'.",
                slug,
                total,
                project_dir,
            )
            return True
        except (OSError, UnicodeError) as exc:
            logger.exception(
                "Критическая ошибка ввода-вывода при сборке '%s': %s",
                project_name,
                exc,
            )
            return False
        except BuildError as exc:
            logger.exception(
                "Критическая ошибка патча ванильных файлов для '%s': %s",
                project_name,
                exc,
            )
            return False
        except Exception as exc:  # noqa: BLE001 - сборка не должна падать наружу
            logger.exception(
                "Критическая ошибка сборки '%s': %s", project_name, exc
            )
            return False

    # ------------------------------------------------------------------
    # Патч system.ltx
    # ------------------------------------------------------------------

    def patch_system_ltx(
        self,
        text: str,
        mod_slug: str,
        character_desc_files: Sequence[str] = (),
    ) -> str:
        """Патчит декодированный текст ``configs/system.ltx``.

        В ``[dialogs] files`` добавляется ``dialogs_<slug>``, а в
        ``[profiles] specific_characters_files`` — каждый патченный
        ``character_desc_<level>``. Существующие значения сохраняются,
        дубликаты не появляются (``standart_of_auto.md``, 1.2).

        Args:
            text (str): Содержимое ванильного ``system.ltx`` без BOM.
            mod_slug (str): Slug мода (без ``dialogs_``).
            character_desc_files (Sequence[str]):
                Имена файлов без расширения, например
                ``("character_desc_escape",)``.

        Returns:
            str: Пропатченный текст с исходными переносами строк.

        Raises:
            BuildError: Если обязательная секция/ключ отсутствует или
                после патча значение встречается не ровно один раз.
            ValueError: Если ``mod_slug`` пуст.
        """
        if not isinstance(mod_slug, str) or not mod_slug.strip():
            raise ValueError("mod_slug должен быть непустой строкой.")
        dialogs_name = f"dialogs_{mod_slug.strip()}"
        patched = self._append_csv_in_section(
            text,
            "dialogs",
            "files",
            [dialogs_name],
        )

        profiles_values = [
            str(value).strip()
            for value in character_desc_files
            if str(value).strip()
        ]
        if profiles_values:
            patched = self._append_csv_in_section(
                patched,
                "profiles",
                "specific_characters_files",
                profiles_values,
            )

        dialog_values = self._read_csv_in_section(
            patched, "dialogs", "files"
        )
        if dialog_values.count(dialogs_name) != 1:
            raise BuildError(
                f"После патча '{dialogs_name}' встречается в "
                f"[dialogs] files {dialog_values.count(dialogs_name)} раз."
            )

        if profiles_values:
            profile_values = self._read_csv_in_section(
                patched,
                "profiles",
                "specific_characters_files",
            )
            for value in profiles_values:
                if profile_values.count(value) != 1:
                    raise BuildError(
                        f"После патча '{value}' встречается в "
                        "[profiles] specific_characters_files "
                        f"{profile_values.count(value)} раз."
                    )
        return patched

    def _append_csv_in_section(
        self,
        text: str,
        section: str,
        key: str,
        values: Iterable[str],
    ) -> str:
        """Добавляет значения в CSV-ключ LTX-секции идемпотентно.

        Значение может занимать несколько физических строк с символом
        продолжения ``\\`` в конце (как ванильные ``files`` и
        ``specific_characters_files``). Функция собирает логическое значение,
        дописывает отсутствующие элементы в конец и заменяет весь диапазон
        одной строкой, сохраняя исходный перенос строк.

        Args:
            text (str): Полный текст LTX.
            section (str): Имя секции без квадратных скобок.
            key (str): Имя ключа внутри секции.
            values (Iterable[str]): Добавляемые значения.

        Returns:
            str: Новый текст; при отсутствии новых значений возвращается
            исходный объект строки без изменений.

        Raises:
            BuildError: Если секция или ключ не найдены.
            TypeError: Если аргументы имеют неверный тип.
        """
        if not isinstance(text, str):
            raise TypeError("text должен быть строкой.")
        additions: list[str] = []
        for value in values:
            candidate = str(value).strip()
            if candidate and candidate not in additions:
                additions.append(candidate)
        if not additions:
            return text

        lines = text.splitlines(keepends=True)
        start, end = self._find_section_bounds(lines, section)
        index, stop, logical = self._find_logical_value(
            lines, start, end, section, key
        )

        key_part, separator, value_part = logical.partition("=")
        if not separator:
            raise BuildError(
                f"Ключ '{key}' в секции [{section}] не содержит '='."
            )
        current = [
            item.strip() for item in value_part.split(",") if item.strip()
        ]
        missing = [value for value in additions if value not in current]
        if not missing:
            return text

        current.extend(missing)
        newline = _line_ending(lines[stop]) or _detect_newline(text)
        new_line = (
            f"{key_part.rstrip()} = {', '.join(current)}{newline}"
        )
        lines[index : stop + 1] = [new_line]
        return "".join(lines)

    def _read_csv_in_section(
        self,
        text: str,
        section: str,
        key: str,
    ) -> list[str]:
        """Читает логическое CSV-значение ключа LTX-секции.

        Args:
            text (str): Полный текст LTX.
            section (str): Имя секции без скобок.
            key (str): Имя ключа.

        Returns:
            list[str]: Элементы списка без пробелов, в исходном порядке.

        Raises:
            BuildError: Если секция или ключ не найдены.
        """
        lines = text.splitlines(keepends=True)
        start, end = self._find_section_bounds(lines, section)
        _, _, logical = self._find_logical_value(
            lines, start, end, section, key
        )
        _, separator, value_part = logical.partition("=")
        if not separator:
            raise BuildError(
                f"Ключ '{key}' в секции [{section}] не содержит '='."
            )
        return [
            item.strip() for item in value_part.split(",") if item.strip()
        ]

    @staticmethod
    def _find_section_bounds(
        lines: Sequence[str], section: str
    ) -> tuple[int, int]:
        """Находит границы тела LTX-секции.

        Args:
            lines (Sequence[str]): Физические строки с окончаниями.
            section (str): Имя секции без скобок.

        Returns:
            tuple[int, int]: Индекс первой строки тела и индекс первой
            строки следующей секции (или ``len(lines)``).

        Raises:
            BuildError: Если секция не найдена.
        """
        header = re.compile(
            rf"^[ \t]*\[{re.escape(section)}\][ \t]*(?:;.*)?$"
        )
        start_index: int | None = None
        for index, line in enumerate(lines):
            if header.match(line.rstrip("\r\n")):
                start_index = index
                break
        if start_index is None:
            raise BuildError(
                f"Секция [{section}] не найдена в system.ltx."
            )
        end_index = len(lines)
        for index in range(start_index + 1, len(lines)):
            if lines[index].lstrip().startswith("["):
                end_index = index
                break
        return start_index + 1, end_index

    @staticmethod
    def _find_logical_value(
        lines: Sequence[str],
        start: int,
        end: int,
        section: str,
        key: str,
    ) -> tuple[int, int, str]:
        """Находит ключ и собирает его многострочное логическое значение.

        LTX допускает продолжение значения обратным слешем в конце строки.
        Ванильные ``[dialogs] files`` и
        ``[profiles] specific_characters_files`` используют именно такую
        форму, поэтому парсер обязан склеивать физические строки.

        Args:
            lines (Sequence[str]): Все строки файла с окончаниями.
            start (int): Первая строка тела секции.
            end (int): Граница секции (исключая).
            section (str): Имя секции для сообщения об ошибке.
            key (str): Имя искомого ключа.

        Returns:
            tuple[int, int, str]: Индекс первой строки, индекс последней
            строки (включительно) и склеенное логическое значение без
            символов продолжения.

        Raises:
            BuildError: Если ключ не найден или оборван в конце секции.
        """
        key_pattern = re.compile(
            rf"^[ \t]*{re.escape(key)}[ \t]*="
        )
        first: int | None = None
        for index in range(start, end):
            if key_pattern.match(lines[index]):
                first = index
                break
        if first is None:
            raise BuildError(
                f"Ключ '{key}' не найден в секции [{section}] system.ltx."
            )

        parts: list[str] = []
        last = first
        for index in range(first, end):
            physical = lines[index].rstrip("\r\n")
            stripped = physical.rstrip()
            if stripped.endswith("\\"):
                parts.append(stripped[:-1])
                last = index
                continue
            parts.append(physical)
            last = index
            break
        else:
            raise BuildError(
                f"Значение '{key}' в [{section}] оборвано продолжением '\\'."
            )

        logical = "".join(parts).strip()
        if not logical:
            raise BuildError(
                f"Значение '{key}' в [{section}] пустое."
            )
        return first, last, logical

    def _build_patched_system_ltx(
        self,
        slug: str,
        character_desc_files: Sequence[str],
    ) -> tuple[str, bool]:
        """Читает ванильный ``system.ltx`` и возвращает патченую копию.

        Args:
            slug (str): Slug мода.
            character_desc_files (Sequence[str]):
                Патченные ``character_desc_<level>`` без расширения.

        Returns:
            tuple[str, bool]: Текст без BOM и исходный флаг BOM.

        Raises:
            BuildError: Если ванильный ``system.ltx`` отсутствует.
            OSError: Если файл не читается.
        """
        source = self.vanilla_root / "configs" / "system.ltx"
        if not source.is_file():
            raise BuildError(
                f"Ванильный system.ltx не найден: '{source}'."
            )
        text, has_bom = read_file_cp1251(source)
        patched = self.patch_system_ltx(text, slug, character_desc_files)
        logger.info(
            "system.ltx пропатчен: dialogs_%s, profiles=%s, BOM=%s.",
            slug,
            ", ".join(character_desc_files) or "нет",
            has_bom,
        )
        return patched, has_bom

    # ------------------------------------------------------------------
    # Патч character_desc_<level>.xml
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_level(value: object) -> str | None:
        """Приводит имя локации/файла профиля к суффиксу ``<level>``.

        Модель хранит ``npc_location="escape"``, но старые SQLite-колонки
        могли содержать ``character_desc_escape`` или
        ``character_desc_escape.xml``. Все три формы должны вести к одному
        файлу ``character_desc_escape.xml``.

        Args:
            value (object): Сырое значение локации или имени файла.

        Returns:
            str | None: Очищенный суффикс или ``None``.
        """
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

    @staticmethod
    def _legacy_extra(source: object, *names: str) -> str | None:
        """Возвращает первое непустое строковое extra-поле объекта.

        Модели ``Dialog`` и ``Quest`` используют ``extra="allow"``, поэтому
        исторические SQLite-колонки остаются доступны как атрибуты. Этот
        помощник извлекает из них значение без падения на отсутствующих
        полях и без приведения нестроковых значений.

        Args:
            source (object): Диалог или квест с возможными extra-полями.
            *names (str): Имена полей в порядке приоритета.

        Returns:
            str | None: Очищенное значение первого непустого поля либо
            ``None``, если ни одно поле не задано.
        """
        for name in names:
            value = getattr(source, name, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _collect_dialog_bindings(
        self, project: "ModProject"
    ) -> list[_DialogBinding]:
        """Строит список привязок диалогов к профилям NPC.

        Источники данных:

        * ``Dialog.npc_id`` и ``Dialog.npc_location``;
        * связанный ``Quest`` (``Dialog.task_id`` или обратная ссылка
          ``Quest.dialog_id``/``Quest.dialog_ids``) — его ``npc_id`` и
          ``npc_location`` используются как запасной вариант;
        * устаревшие extra-поля SQLite (``owner_profile_id``,
          ``owner_character_desc``, ``giver_character_desc``), которые
          сохраняются благодаря ``extra="allow"`` и исторически хранили
          профиль NPC и имя файла ``character_desc_<level>.xml``.

        Значение локации нормализуется :meth:`_normalize_level`, поэтому
        ``escape``, ``character_desc_escape`` и
        ``character_desc_escape.xml`` ведут к одному файлу
        ``character_desc_escape.xml``.

        Диалог без ``npc_id`` не привязывается (в лог пишется warning):
        угадывать профиль запрещено стандартом (1.3). Если ``npc_id`` есть,
        а ``npc_location`` нет — поднимается :class:`BuildError`, потому что
        нельзя выбрать ``character_desc_<level>.xml``.

        Args:
            project (ModProject): Проект мода.

        Returns:
            list[_DialogBinding]: Привязки в порядке ролей.

        Raises:
            BuildError: Если у диалога есть ``npc_id``, но нет локации.
        """
        quest_by_dialog: dict[str, "Quest"] = {}
        for quest in project.quests.values():
            if quest.dialog_id:
                quest_by_dialog.setdefault(quest.dialog_id, quest)
            for dialog_id in quest.dialog_ids:
                quest_by_dialog.setdefault(dialog_id, quest)

        bindings: list[_DialogBinding] = []
        for order, dialog in enumerate(project.dialogs.values()):
            dialog_id = (
                getattr(dialog, "dialog_id", None)
                or getattr(dialog, "id", None)
            )
            if not isinstance(dialog_id, str) or not dialog_id.strip():
                raise BuildError(
                    f"Диалог #{order} не содержит корректного ID."
                )
            dialog_id = dialog_id.strip()

            linked = None
            task_id = getattr(dialog, "task_id", None)
            if isinstance(task_id, str) and task_id in project.quests:
                linked = project.quests[task_id]
            if linked is None:
                linked = quest_by_dialog.get(dialog_id)

            npc_id = getattr(dialog, "npc_id", None) or self._legacy_extra(
                dialog, "owner_profile_id"
            )
            level = getattr(dialog, "npc_location", None) or self._legacy_extra(
                dialog, "owner_character_desc", "giver_character_desc"
            )
            if linked is not None:
                if not npc_id:
                    npc_id = (
                        linked.npc_id
                        or linked.giver_npc_id
                        or self._legacy_extra(linked, "owner_profile_id")
                    )
                if not level:
                    level = linked.npc_location or self._legacy_extra(
                        linked,
                        "owner_character_desc",
                        "giver_character_desc",
                    )

            if not npc_id:
                logger.warning(
                    "Диалог '%s' не привязан к NPC: npc_id не задан ни в "
                    "диалоге, ни в связанном квесте.",
                    dialog_id,
                )
                continue
            level = self._normalize_level(level)
            if not level:
                raise BuildError(
                    f"Диалог '{dialog_id}' ссылается на NPC '{npc_id}', "
                    "но npc_location не задана: невозможно выбрать "
                    "character_desc_<level>.xml."
                )

            role = (getattr(dialog, "role", None) or "").strip().lower()
            bindings.append(
                _DialogBinding(
                    level=str(level).strip(),
                    npc_id=str(npc_id).strip(),
                    dialog_id=dialog_id,
                    role=role,
                    order=order,
                )
            )

        bindings.sort(
            key=lambda item: (
                item.level,
                item.npc_id,
                _ROLE_ORDER.get(item.role, 99),
                item.order,
            )
        )
        return bindings

    def _patch_character_desc_files(
        self, bindings: Sequence[_DialogBinding]
    ) -> dict[str, tuple[str, bool]]:
        """Копирует и патчит все нужные ``character_desc_<level>.xml``.

        Args:
            bindings (Sequence[_DialogBinding]): Привязки диалогов.

        Returns:
            dict[str, tuple[str, bool]]: Карта ``level -> (текст, BOM)``.

        Raises:
            BuildError: Если ванильный файл локации отсутствует.
        """
        by_npc: dict[tuple[str, str], list[str]] = {}
        for binding in bindings:
            key = (binding.level, binding.npc_id)
            values = by_npc.setdefault(key, [])
            if binding.dialog_id not in values:
                values.append(binding.dialog_id)

        by_level: dict[str, dict[str, list[str]]] = {}
        for (level, npc_id), dialog_ids in by_npc.items():
            by_level.setdefault(level, {})[npc_id] = dialog_ids

        patched: dict[str, tuple[str, bool]] = {}
        for level, npc_map in sorted(by_level.items()):
            source = (
                self.vanilla_root
                / "configs"
                / "gameplay"
                / f"character_desc_{level}.xml"
            )
            if not source.is_file():
                raise BuildError(
                    "Ванильный файл профилей не найден: "
                    f"'{source}' (npc_location={level!r})."
                )
            text, has_bom = read_file_cp1251(source)
            for npc_id, dialog_ids in npc_map.items():
                text = self.patch_character_desc(
                    text, npc_id, dialog_ids
                )
            patched[level] = (text, has_bom)
            logger.info(
                "character_desc_%s пропатчен: NPC=%d, BOM=%s.",
                level,
                len(npc_map),
                has_bom,
            )
        return patched

    def patch_character_desc(
        self,
        text: str,
        npc_id: str,
        dialog_ids: Sequence[str],
    ) -> str:
        """Вставляет ``<actor_dialog>`` в один ``<specific_character>``.

        Функция работает только со строкой и никогда не использует
        ``xml.etree``/``lxml``: DOM-пересериализация потеряла бы
        ``#include``, комментарии и чужие профили (``standart_of_auto.md``,
        1.3). Вставка идемпотентна, порядок ``dialog_ids`` сохраняется.

        Args:
            text (str): Содержимое ``character_desc_<level>.xml`` без BOM.
            npc_id (str): Значение ``id`` целевого профиля.
            dialog_ids (Sequence[str]): ID диалогов для ``<actor_dialog>``.

        Returns:
            str: Текст с добавленными (только отсутствующими) диалогами.

        Raises:
            BuildError: Если профиль не найден, найден более одного раза
                или в файле нет закрывающего ``</specific_character>``.
            ValueError: Если ``npc_id`` пуст.
        """
        if not isinstance(npc_id, str) or not npc_id.strip():
            raise ValueError("npc_id должен быть непустой строкой.")
        requested: list[str] = []
        for value in dialog_ids:
            candidate = str(value).strip()
            if candidate and candidate not in requested:
                requested.append(candidate)
        if not requested:
            return text

        npc_pattern = re.compile(
            r"(?s)(?P<open><specific_character\b[^>]*\bid\s*=\s*"
            rf"[\"']{re.escape(npc_id)}[\"'][^>]*>)"
            r"(?P<body>.*?)"
            r"(?P<close></specific_character>)"
        )
        matches = list(npc_pattern.finditer(text))
        if not matches:
            raise BuildError(
                f"<specific_character id=\"{npc_id}\"> не найден в "
                "character_desc_*.xml."
            )
        if len(matches) > 1:
            raise BuildError(
                f"<specific_character id=\"{npc_id}\"> встречается "
                f"{len(matches)} раза: дубликат id ломает профили."
            )

        match = matches[0]
        body = match.group("body")
        missing = [
            dialog_id
            for dialog_id in requested
            if not re.search(
                rf"<actor_dialog>\s*{re.escape(dialog_id)}\s*"
                r"</actor_dialog>",
                body,
            )
        ]
        if not missing:
            return text

        newline = _detect_newline(text)
        trailing = re.search(r"[ \t]*$", body)
        indent = trailing.group(0) if trailing else ""
        content = body[: trailing.start()] if trailing else body
        if not content.endswith(("\n", "\r")):
            content += newline

        insertion = "".join(
            f"\t\t<actor_dialog>{dialog_id}</actor_dialog>{newline}"
            for dialog_id in missing
        )
        new_body = f"{content}{insertion}{indent}"

        start = match.start("body")
        end = match.end("body")
        return f"{text[:start]}{new_body}{text[end:]}"

    # ------------------------------------------------------------------
    # Служебные операции с каталогом
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_written(path: Path) -> None:
        """Проверяет, что файл физически создан и не пуст.

        Args:
            path (Path): Путь записанного файла.

        Returns:
            None: Функция ничего не возвращает.

        Raises:
            OSError: Если файл отсутствует.
        """
        if not path.is_file():
            raise OSError(f"Файл '{path}' не создан.")
        logger.info("Файл записан: '%s'.", path)

    def _prepare_project_directory(self, project_dir: Path) -> None:
        """Очищает старый каталог проекта и создаёт структуру ``gamedata``.

        Args:
            project_dir (Path): Каталог ``output/<slug>``.

        Returns:
            None: Функция ничего не возвращает.

        Raises:
            ValueError: Если каталог не является прямым потомком
                ``output_dir``.
            OSError: Если путь существует и не является каталогом.
        """
        output_root = self.output_dir.resolve()
        target = Path(project_dir).resolve()
        if target.parent != output_root:
            raise ValueError(
                f"Каталог '{target}' должен быть прямым потомком "
                f"'{output_root}'."
            )
        output_root.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_dir():
                raise OSError(f"'{target}' существует и не каталог.")
            shutil.rmtree(target)
            logger.info("Старый каталог удалён: '%s'.", target)
        for rel in _PROJECT_DIRECTORIES:
            (project_dir / rel).mkdir(parents=True, exist_ok=True)
        logger.info(
            "Структура gamedata создана: '%s', каталогов=%d.",
            target,
            len(_PROJECT_DIRECTORIES),
        )


__all__ = ["BuildError", "ModBuilder", "_slugify"]
