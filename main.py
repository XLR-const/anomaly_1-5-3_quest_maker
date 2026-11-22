"""Единый CLI-интерфейс конструктора сюжетных квестов Anomaly.

Модуль предоставляет команды:

* ``search`` — живой поиск предметов, NPC, смартов и отрядов в SQLite-базе
  игры с выводом результата в виде цветной Rich-таблицы;
* ``build`` — создание демонстрационного Warfare-проекта, его runtime-проверка
  и автоматическая сборка установочной папки мода в ``output/<slug>``;
* ``validate`` — запуск единого пайплайна валидации для произвольного
  Python-скрипта, возвращающего :class:`~src.core.models.ModProject`.

Запуск из корня проекта::

    python main.py search выхлоп --type item
    python main.py build
    python main.py validate examples/build_story_relay.py --strict
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from typing import Optional

import rich
import typer

from examples.cordon_warfare_demo import create_demo_project
from src.compiler.builder import ModBuilder, _slugify
from src.core.models import ModProject
from src.core.validator import ProjectValidator
from src.db.repository import GameDatabase
from src.logger import get_logger
from src.validation import validate_project

logger = get_logger("cli")

#: Корень проекта. Путь к базе не зависит от текущего рабочего каталога.
PROJECT_ROOT = Path(__file__).resolve().parent
#: Основная SQLite-база ассетов Anomaly.
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "anomaly_db.sqlite"


def _is_modproject_annotation(annotation: object) -> bool:
    """Проверяет, что аннотация возврата означает ``ModProject``.

    Модули примеров часто используют ``from __future__ import annotations``,
    поэтому аннотация может быть строкой, а не классом.

    Args:
        annotation (object): Значение ``inspect.Signature.return_annotation``.

    Returns:
        bool: ``True``, если аннотация указывает на ``ModProject``.
    """
    if annotation is ModProject:
        return True
    if isinstance(annotation, str):
        normalized = annotation.strip().strip("\"'")
        return normalized in {
            "ModProject",
            "src.core.models.ModProject",
        } or normalized.endswith(".ModProject")
    return getattr(annotation, "__name__", None) == "ModProject"


def _find_project_factory(module: object) -> object | None:
    """Находит функцию, создающую ``ModProject``.

    Сначала проверяются канонические имена ``build_project`` и
    ``create_project``, затем — любая публичная функция без обязательных
    аргументов с аннотацией возврата ``ModProject``.

    Args:
        module (object): Загруженный Python-модуль скрипта.

    Returns:
        object | None: Функция-фабрика или ``None``, если её нет.
    """
    for name in ("build_project", "create_project"):
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate

    for name, candidate in vars(module).items():
        if name.startswith("_") or not inspect.isfunction(candidate):
            continue
        try:
            signature = inspect.signature(candidate)
        except (TypeError, ValueError):
            continue
        required = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.default is parameter.empty
            and parameter.kind
            in (
                parameter.POSITIONAL_ONLY,
                parameter.POSITIONAL_OR_KEYWORD,
                parameter.KEYWORD_ONLY,
            )
        ]
        if required:
            continue
        if _is_modproject_annotation(signature.return_annotation):
            return candidate
    return None


def _load_project_from_script(script_path: Path) -> ModProject:
    """Загружает Python-скрипт и вызывает его фабрику ``ModProject``.

    Args:
        script_path (Path): Путь к скрипту с функцией сборки проекта.

    Returns:
        ModProject: Созданный скриптом проект.

    Raises:
        FileNotFoundError: Если скрипт не существует.
        ImportError: Если модуль не удалось загрузить.
        ValueError: Если фабрика не найдена или вернула не ``ModProject``.
    """
    path = Path(script_path)
    if not path.is_file():
        raise FileNotFoundError(f"Скрипт не найден: '{path}'.")

    module_name = f"_quest_validate_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Не удалось загрузить модуль '{path}'.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    factory = _find_project_factory(module)
    if factory is None:
        raise ValueError(
            f"В скрипте '{path}' не найдена функция сборки ModProject "
            "(build_project/create_project или функция с аннотацией "
            "возврата ModProject)."
        )

    project = factory()  # type: ignore[operator]
    if not isinstance(project, ModProject):
        raise ValueError(
            f"Функция '{getattr(factory, '__name__', factory)}' вернула "
            f"{type(project).__name__}, ожидался ModProject."
        )
    return project


app = typer.Typer(
    help="Конструктор сюжетных квестов для S.T.A.L.K.E.R. Anomaly"
)


@app.command()
def search(
    query: str,
    type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Тип сущности (item, npc, smart, squad)",
    ),
) -> None:
    """Ищет игровые ассеты в базе Anomaly и печатает Rich-таблицу.

    Команда открывает :class:`~src.db.repository.GameDatabase` как контекстный
    менеджер, выполняет живой поиск по имени, игровому ID и алиасу, после чего
    передаёт найденные записи в :meth:`GameDatabase.print_assets_table`.

    Args:
        query (str):
            Подстрока для поиска. Может содержать кириллицу; репозиторий
            выполняет регистронезависимое сравнение.
        type (Optional[str]):
            Необязательный фильтр типа сущности: ``item``, ``npc``, ``smart``
            или ``squad``. При ``None`` поиск идёт по всем типам.

    Raises:
        typer.Exit:
            Если файл базы данных отсутствует или во время поиска возникла
            непредвиденная ошибка. Код выхода — ``1``.
    """
    logger.info("CLI search запущен: query=%r, type=%r.", query, type)

    try:
        with GameDatabase(DEFAULT_DB_PATH) as db:
            assets = db.search_assets(query, type)
            db.print_assets_table(assets)
    except FileNotFoundError as exc:
        logger.error("База данных для поиска не найдена: %s", DEFAULT_DB_PATH)
        rich.print(
            "[bold red]Ошибка:[/bold red] файл базы данных не найден: "
            f"[underline]{DEFAULT_DB_PATH}[/underline]"
        )
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        logger.exception("Непредвиденная ошибка при поиске ассетов: %s", exc)
        rich.print(
            "[bold red]Ошибка поиска:[/bold red] "
            f"{exc}"
        )
        raise typer.Exit(code=1) from exc

    logger.info(
        "CLI search завершён: query=%r, type=%r, найдено=%d.",
        query,
        type,
        len(assets),
    )


@app.command()
def build() -> None:
    """Собирает демонстрационный Warfare-мод в ``output/<slug>``.

    Команда программно создаёт проект из
    :func:`examples.cordon_warfare_demo.create_demo_project`, открывает
    игровую базу, прогоняет проект через глобальный
    :class:`~src.core.validator.ProjectValidator` и, если runtime-валидация
    успешна, запускает :class:`~src.compiler.builder.ModBuilder`.

    Raises:
        typer.Exit:
            Если не удалось создать проект, открыть базу, пройти валидацию
            или выполнить сборку. Код выхода — ``1``.
    """
    logger.info("CLI build запущен: создание демонстрационного проекта.")

    try:
        project = create_demo_project()
    except Exception as exc:
        logger.exception("Не удалось создать демонстрационный проект: %s", exc)
        rich.print(
            "[bold red]Ошибка:[/bold red] не удалось создать проект мода."
        )
        raise typer.Exit(code=1) from exc

    try:
        with GameDatabase(DEFAULT_DB_PATH) as db:
            validator = ProjectValidator(db)

            if not validator.validate_project(project):
                logger.error(
                    "Проект '%s' не прошёл глобальную runtime-валидацию.",
                    project.name,
                )
                rich.print(
                    "[bold red]Валидация не пройдена:[/bold red] "
                    "автоматическая сборка мода отменена."
                )
                raise typer.Exit(code=1)

            builder = ModBuilder()
            if not builder.build_project(project):
                logger.error(
                    "Сборщик не смог скомпилировать проект '%s'.",
                    project.name,
                )
                rich.print(
                    "[bold red]Ошибка сборки:[/bold red] "
                    "проверьте подробности в logs/app.log."
                )
                raise typer.Exit(code=1)

            project_dir = builder.output_dir / _slugify(project.name)
    except typer.Exit:
        # Явный выход CLI не должен перехватываться общим обработчиком ниже.
        raise
    except FileNotFoundError as exc:
        logger.error("База данных для сборки не найдена: %s", DEFAULT_DB_PATH)
        rich.print(
            "[bold red]Ошибка:[/bold red] файл базы данных не найден: "
            f"[underline]{DEFAULT_DB_PATH}[/underline]"
        )
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        logger.exception("Непредвиденная ошибка при сборке мода: %s", exc)
        rich.print(
            "[bold red]Ошибка сборки:[/bold red] "
            f"{exc}"
        )
        raise typer.Exit(code=1) from exc

    absolute_path = project_dir.resolve()
    logger.info(
        "CLI build успешно завершён: проект '%s' собран в '%s'.",
        project.name,
        absolute_path,
    )

    rich.print(
        "[bold green]Мод успешно скомпилирован автоматически![/bold green]"
    )
    rich.print(
        "[bold cyan]Готовая папка мода:[/bold cyan] "
        f"[bold]{project_dir}[/bold] "
        f"([underline]{absolute_path}[/underline])"
    )


@app.command()
def validate(
    script_path: Path = typer.Argument(
        ...,
        help="Python-скрипт с функцией сборки ModProject.",
    ),
    json_path: Optional[Path] = typer.Option(
        None,
        "--json",
        help="Сохранить машинночитаемый JSON-отчёт по указанному пути.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Считать предупреждения (WARNING) ошибкой для кода выхода.",
    ),
) -> None:
    """Проверяет проект из Python-скрипта единым пайплайном валидации.

    Команда загружает файл, находит функцию ``build_project`` /
    ``create_project`` (или любую функцию с аннотацией возврата
    ``ModProject``), при наличии БД подключает её и печатает отчёт.

    Args:
        script_path (Path): Путь к Python-скрипту с фабрикой проекта.
        json_path (Optional[Path]): Необязательный путь для JSON-отчёта.
        strict (bool): Если ``True``, наличие WARNING даёт код выхода ``2``.

    Raises:
        typer.Exit: Код ``1`` при ошибке загрузки или ``ERROR`` в отчёте;
            код ``2`` при ``--strict`` и наличии WARNING.
    """
    logger.info(
        "CLI validate запущен: script=%s, json=%s, strict=%s.",
        script_path,
        json_path,
        strict,
    )

    try:
        project = _load_project_from_script(script_path)
        if DEFAULT_DB_PATH.is_file():
            with GameDatabase(DEFAULT_DB_PATH) as db:
                report = validate_project(project, db=db)
        else:
            report = validate_project(project, db=None)

        typer.echo(report.to_text())

        if json_path is not None:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(report.to_json(), encoding="utf-8")
            typer.echo(f"JSON-отчёт сохранён: {json_path}")
    except Exception as exc:  # noqa: BLE001 - CLI обязан вернуть код 1
        logger.exception("Ошибка загрузки/валидации проекта: %s", exc)
        rich.print(f"[bold red]Ошибка валидации:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    logger.info(
        "CLI validate завершён: errors=%d, warnings=%d.",
        len(report.errors),
        len(report.warnings),
    )

    if report.has_errors:
        raise typer.Exit(code=1)
    if strict and report.warnings:
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()


__all__ = ["app", "build", "search", "validate"]
