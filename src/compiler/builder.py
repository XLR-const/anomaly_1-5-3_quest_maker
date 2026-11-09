"""Главный оркестратор автоматической сборки мода для MO2.

Модуль связывает три независимых генератора компилятора в единый конвейер:

* :class:`~src.compiler.ltx_gen.LtxGenerator` — задачи КПК;
* :class:`~src.compiler.xml_gen.XmlGenerator` — диалоги и локализацию;
* :class:`~src.compiler.lua_gen.LuaGenerator` — игровую Lua-логику.

Результатом работы :class:`ModBuilder` является готовая к установке в
Mod Organizer 2 папка ``output/<slug>/gamedata``. Никаких README и ручных
инструкций не создаётся: мод активируется как обычный мод Anomaly в один
клик, а подключение диалогов выполняется сгенерированным Lua-скриптом.

Все операции подробно журналируются через общий логгер проекта. Ошибки
ввода-вывода и повреждённые данные не приводят к неконтролируемому падению:
:meth:`ModBuilder.build_project` перехватывает их и возвращает ``False``.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from src.compiler.encoding import write_file_cp1251
from src.compiler.ltx_gen import LtxGenerator
from src.compiler.lua_gen import LuaGenerator
from src.compiler.xml_gen import XmlGenerator
from src.logger import get_logger

if TYPE_CHECKING:
    from src.core.models import ModProject

logger = get_logger("compiler.builder")

#: Таблица транслитерации кириллицы в латиницу для безопасных имён X-Ray.
#:
#: Ключи записаны в нижнем регистре: входная строка нормализуется до
#: применения таблицы. Буквы, которых нет в таблице, удаляются на следующем
#: шаге как специальные символы.
_TRANSLITERATION = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "kh",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "shch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
        "і": "i",
        "ї": "yi",
        "є": "ye",
        "ґ": "g",
    }
)

#: Пробелы и дефисы, которые превращаются в разделитель ``_``.
_SEPARATOR_PATTERN = re.compile(r"[\s\-]+")
#: Всё, что не входит в безопасный алфавит X-Ray-имени, удаляется.
_FORBIDDEN_SLUG_PATTERN = re.compile(r"[^a-z0-9_]+")
#: Повторяющиеся подчёркивания схлопываются в одно.
_REPEATED_UNDERSCORES_PATTERN = re.compile(r"_+")

#: Обязательные каталоги установочной структуры мода.
_PROJECT_DIRECTORIES = (
    Path("gamedata") / "configs" / "misc" / "task",
    Path("gamedata") / "configs" / "gameplay",
    Path("gamedata") / "configs" / "text" / "rus",
    Path("gamedata") / "configs" / "text" / "eng",
    Path("gamedata") / "scripts",
)


def _slugify(name: str) -> str:
    """Преобразует название проекта в безопасное имя для движка X-Ray.

    Метод приводит строку к нижнему регистру, транслитерирует кириллицу в
    латиницу, заменяет пробелы и дефисы на ``_``, удаляет все специальные
    символы и схлопывает повторяющиеся подчёркивания. Например, название
    ``"My Super Warfare Mod"`` превращается в ``"my_super_warfare_mod"``.

    Args:
        name (str):
            Название модификации из :attr:`ModProject.name`.

    Returns:
        str: Безопасный slug, состоящий только из латиницы, цифр и ``_``.
        Если после очистки не осталось ни одного символа, возвращается
        запасное имя ``"mod"``.

    Raises:
        TypeError:
            Если ``name`` не является строкой.
    """
    logger.debug("Нормализация имени проекта в slug: %r.", name)

    try:
        if not isinstance(name, str):
            raise TypeError(
                "Название проекта должно быть строкой, "
                f"а получено {type(name).__name__}."
            )

        normalized = name.strip().lower()
        transliterated = normalized.translate(_TRANSLITERATION)
        separated = _SEPARATOR_PATTERN.sub("_", transliterated)
        slug = _FORBIDDEN_SLUG_PATTERN.sub("", separated)
        slug = _REPEATED_UNDERSCORES_PATTERN.sub("_", slug).strip("_")

        if not slug:
            logger.warning(
                "Название проекта %r не содержит допустимых символов; "
                "используется запасной slug 'mod'.",
                name,
            )
            slug = "mod"

        logger.debug("Имя проекта %r преобразовано в slug %r.", name, slug)
        return slug
    except Exception as exc:
        logger.exception("Не удалось нормализовать имя проекта %r: %s", name, exc)
        raise


class ModBuilder:
    """Собирает установочную структуру мода Anomaly для Mod Organizer 2.

    Класс создаёт чистый каталог ``output_dir/<slug>`` и последовательно
    записывает в него все игровые файлы, сформированные генераторами LTX,
    XML и Lua. Каждый запуск полностью пересоздаёт каталог проекта, поэтому
    в установку не попадают устаревшие файлы предыдущих сборок.

    Attributes:
        output_dir (Path):
            Корневая директория экспорта, внутри которой создаются папки
            отдельных проектов.
    """

    def __init__(self, output_dir: Path = Path("output")) -> None:
        """Инициализирует сборщик и запоминает корневую директорию экспорта.

        Args:
            output_dir (Path):
                Базовая директория, внутри которой будет создан каталог
                ``<slug>/gamedata``. Может быть передана строкой.

        Returns:
            None: Конструктор ничего не возвращает.

        Raises:
            TypeError:
                Если ``output_dir`` не является путём или строкой.
        """
        logger.debug("Создание ModBuilder с output_dir=%r.", output_dir)

        try:
            if not isinstance(output_dir, (str, Path)):
                raise TypeError(
                    "output_dir должен быть экземпляром Path или строкой, "
                    f"а получен {type(output_dir).__name__}."
                )

            self.output_dir = Path(output_dir)
            logger.info(
                "ModBuilder инициализирован: output_dir='%s'.",
                self.output_dir,
            )
        except Exception as exc:
            logger.exception("Не удалось инициализировать ModBuilder: %s", exc)
            raise

    def build_project(self, project: "ModProject") -> bool:
        """Выполняет полную сборку мода и записывает игровые файлы на диск.

        Метод проверяет проект, вычисляет безопасный slug, создаёт чистую
        структуру ``gamedata`` и вызывает все три генератора компилятора.
        Файлы задач, диалогов, русской и английской локализации, а также
        Lua-скрипт сохраняются в кодировке Windows-1251 без BOM.

        Генераторы инициализируются заново на каждом запуске, поэтому
        повторная сборка не зависит от состояния предыдущего вызова.

        Args:
            project (ModProject):
                Корневая модель проекта с картами ``quests`` и ``dialogs``.

        Returns:
            bool: ``True``, если все файлы успешно созданы и записаны;
            ``False`` при любой критической ошибке данных или ввода-вывода.

        Raises:
            None: Все исключения перехватываются и журналируются внутри
            метода; наружу они не пробрасываются.
        """
        project_name = getattr(project, "name", "<без имени>")
        logger.info("Начата сборка проекта '%s'.", project_name)

        try:
            name = getattr(project, "name", None)
            if not isinstance(name, str) or not name.strip():
                raise ValueError(
                    "Проект должен содержать непустое строковое поле name."
                )

            quests = getattr(project, "quests", None)
            dialogs = getattr(project, "dialogs", None)
            if not isinstance(quests, dict) or not isinstance(dialogs, dict):
                raise TypeError(
                    "Проект должен содержать словарные карты quests и "
                    f"dialogs, а получены {type(quests).__name__} и "
                    f"{type(dialogs).__name__}."
                )

            slug = _slugify(name)
            project_dir = self.output_dir / slug
            logger.info(
                "Безопасное имя проекта: '%s'; каталог сборки: '%s'.",
                slug,
                project_dir,
            )

            self._prepare_project_directory(project_dir)

            ltx_generator = LtxGenerator()
            xml_generator = XmlGenerator()
            lua_generator = LuaGenerator()
            logger.debug(
                "Генераторы LTX, XML и Lua инициализированы для проекта '%s'.",
                slug,
            )

            tasks_content = ltx_generator.generate_tasks_ltx(quests)
            dialogs_content = xml_generator.generate_dialogs_xml(dialogs)
            string_tables = xml_generator.generate_string_tables(project)
            script_content = lua_generator.generate_quests_script(project)

            if not isinstance(string_tables, dict):
                raise TypeError(
                    "Генератор локализации должен вернуть словарь, "
                    f"а вернул {type(string_tables).__name__}."
                )

            rus_content = string_tables.get("rus")
            eng_content = string_tables.get("eng")
            if not isinstance(rus_content, str) or not isinstance(
                eng_content,
                str,
            ):
                raise ValueError(
                    "Генератор локализации не вернул строки для языков "
                    "'rus' и 'eng'."
                )

            files: dict[Path, str] = {
                project_dir
                / "gamedata"
                / "configs"
                / "misc"
                / "task"
                / f"tm_{slug}.ltx": tasks_content,
                project_dir
                / "gamedata"
                / "configs"
                / "gameplay"
                / f"dialogs_{slug}.xml": dialogs_content,
                project_dir
                / "gamedata"
                / "configs"
                / "text"
                / "rus"
                / f"st_{slug}.xml": rus_content,
                project_dir
                / "gamedata"
                / "configs"
                / "text"
                / "eng"
                / f"st_{slug}.xml": eng_content,
                project_dir
                / "gamedata"
                / "scripts"
                / f"{slug}_quests.script": script_content,
            }

            for path, content in files.items():
                if not isinstance(content, str):
                    raise TypeError(
                        f"Содержимое файла '{path}' должно быть строкой, "
                        f"а получено {type(content).__name__}."
                    )

                write_file_cp1251(path, content)

                if not path.is_file():
                    raise OSError(
                        f"Файл '{path}' не был создан после записи."
                    )

                logger.info("Файл сборки записан: '%s'.", path)

            logger.info(
                "Сборка проекта '%s' завершена успешно: файлов — %d, "
                "каталог — '%s'.",
                slug,
                len(files),
                project_dir,
            )
            return True
        except (OSError, UnicodeError) as exc:
            logger.exception(
                "Критическая ошибка ввода-вывода при сборке проекта '%s': %s",
                project_name,
                exc,
            )
            return False
        except Exception as exc:
            logger.exception(
                "Критическая ошибка при сборке проекта '%s': %s",
                project_name,
                exc,
            )
            return False

    def _prepare_project_directory(self, project_dir: Path) -> None:
        """Создаёт чистую установочную структуру каталогов проекта.

        Если каталог проекта уже существует, он полностью удаляется вместе
        со старыми файлами. Затем заново создаются все обязательные папки
        ``gamedata``: задачи, диалоги, локализация и скрипты.

        Args:
            project_dir (Path):
                Каталог конкретного проекта внутри :attr:`output_dir`.

        Returns:
            None: Функция изменяет файловую систему и ничего не возвращает.

        Raises:
            ValueError:
                Если целевой каталог не является прямым потомком
                :attr:`output_dir` (защита от удаления чужих данных).
            OSError:
                Если существующий путь не является каталогом или его не
                удалось очистить/создать.
        """
        logger.debug(
            "Подготовка чистого каталога сборки '%s'.",
            project_dir,
        )

        try:
            output_root = self.output_dir.resolve()
            target = Path(project_dir).resolve()

            if target.parent != output_root:
                raise ValueError(
                    "Каталог проекта должен находиться непосредственно "
                    f"внутри '{output_root}', а получен '{target}'."
                )

            output_root.mkdir(parents=True, exist_ok=True)

            if target.exists():
                if not target.is_dir():
                    raise OSError(
                        f"Путь сборки '{target}' существует, но не является "
                        "каталогом."
                    )

                shutil.rmtree(target)
                logger.info("Старый каталог сборки удалён: '%s'.", target)

            for relative_dir in _PROJECT_DIRECTORIES:
                (project_dir / relative_dir).mkdir(
                    parents=True,
                    exist_ok=True,
                )

            logger.info(
                "Структура gamedata создана: '%s', каталогов — %d.",
                target,
                len(_PROJECT_DIRECTORIES),
            )
        except Exception as exc:
            logger.exception(
                "Не удалось подготовить каталог сборки '%s': %s",
                project_dir,
                exc,
            )
            raise


__all__ = ["ModBuilder", "_slugify"]
