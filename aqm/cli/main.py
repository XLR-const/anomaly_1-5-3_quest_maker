"""Единый CLI пакета ``aqm``.

Публичные команды:

* ``init`` — создать рабочее пространство с шаблонным квестом;
* ``build`` — собрать проект из Python-скрипта или демонстрационный мод;
* ``validate`` — прогнать проект через единый пайплайн валидации;
* ``merge`` — объединить независимые главы мода и собрать результат;
* ``search`` — найти ассеты в SQLite-базе Anomaly.

База и шаблоны находятся внутри установленного пакета, а ``aqm.json``,
``scripts/`` и ``output/`` — в рабочем пространстве пользователя.
"""

from __future__ import annotations

import importlib.util
import inspect
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import rich
import typer

from aqm.compiler.builder import ModBuilder, _slugify
from aqm.core.models import ModProject
from aqm.core.validator import ProjectValidator
from aqm.db.repository import GameDatabase
from aqm.logger import get_logger
from aqm.paths import (
    find_workspace_root,
    get_default_db_path,
    get_templates_dir,
    load_workspace_config,
)
from aqm.validation import (
    MergeValidator,
    ValidationReport,
    validate_project,
)

logger = get_logger("cli")

app = typer.Typer(
    help="Конструктор сюжетных квестов для S.T.A.L.K.E.R. Anomaly"
)


def _is_modproject_annotation(annotation: object) -> bool:
    """Проверяет, что аннотация возврата означает ``ModProject``.

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
            "aqm.core.models.ModProject",
            "src.core.models.ModProject",
        } or normalized.endswith(".ModProject")
    return getattr(annotation, "__name__", None) == "ModProject"


def _find_project_factory(module: object) -> object | None:
    """Находит функцию, создающую ``ModProject``.

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

    module_name = f"_aqm_quest_{path.stem}"
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


def _resolve_config_path(workspace_root: Path, raw: object) -> Path | None:
    """Преобразует значение ``aqm.json`` в абсолютный путь.

    Args:
        workspace_root (Path): Корень рабочего пространства.
        raw (object): Сырое значение из конфигурации.

    Returns:
        Path | None: Абсолютный путь или ``None``.
    """
    if not raw:
        return None
    path = Path(str(raw))
    if not path.is_absolute():
        path = workspace_root / path
    return path


def _workspace() -> tuple[Path, dict, Path, Path, Path | None]:
    """Возвращает рабочие пути, вычисленные из ``aqm.json``.

    Returns:
        tuple: ``(root, config, db_path, output_dir, vanilla_dir)``.
    """
    root = find_workspace_root()
    config = load_workspace_config(root)
    db_path = _resolve_config_path(root, config.get("db_path"))
    if db_path is None:
        db_path = get_default_db_path()
    output_dir = _resolve_config_path(
        root, config.get("output_dir") or "output"
    )
    assert output_dir is not None
    vanilla_dir = _resolve_config_path(root, config.get("vanilla_dir"))
    if vanilla_dir is None:
        candidate = root / "_unpacked"
        vanilla_dir = candidate if candidate.is_dir() else None
    return root, config, db_path, output_dir, vanilla_dir


@contextmanager
def _open_db(db_path: Path) -> Iterator[GameDatabase | None]:
    """Открывает SQLite-базу, если файл существует.

    Args:
        db_path (Path): Путь к базе ассетов.

    Yields:
        GameDatabase | None: Клиент БД или ``None`` для автономного режима.
    """
    if not Path(db_path).is_file():
        logger.warning("База ассетов не найдена: %s", db_path)
        yield None
        return
    with GameDatabase(Path(db_path)) as db:
        yield db


def _build_project(
    project: ModProject,
    db: GameDatabase | None,
    output_dir: Path,
    vanilla_dir: Path | None,
) -> Path:
    """Проверяет и собирает проект в ``output/<slug>``.

    Args:
        project (ModProject): Проект мода.
        db (GameDatabase | None): Клиент БД или ``None``.
        output_dir (Path): Корневой каталог сборки.
        vanilla_dir (Path | None): Распакованная ванильная игра.

    Returns:
        Path: Каталог собранного мода.

    Raises:
        typer.Exit: Если runtime-валидация или сборка не удались.
    """
    if db is not None and not ProjectValidator(db).validate_project(project):
        logger.error(
            "Проект '%s' не прошёл глобальную runtime-валидацию.",
            project.name,
        )
        rich.print(
            "[bold red]Валидация не пройдена:[/bold red] "
            "автоматическая сборка мода отменена."
        )
        raise typer.Exit(code=1)

    builder = ModBuilder(
        output_dir=output_dir,
        db_client=db,
        vanilla_root=vanilla_dir,
    )
    if not builder.build_project(project):
        logger.error("Сборщик не смог скомпилировать проект '%s'.", project.name)
        rich.print(
            "[bold red]Ошибка сборки:[/bold red] "
            "проверьте подробности в logs/app.log."
        )
        raise typer.Exit(code=1)

    project_dir = builder.output_dir / _slugify(project.name)
    absolute_path = project_dir.resolve()
    logger.info(
        "Проект '%s' собран в '%s'.", project.name, absolute_path
    )
    rich.print(
        "[bold green]Мод успешно скомпилирован автоматически![/bold green]"
    )
    rich.print(
        "[bold cyan]Готовая папка мода:[/bold cyan] "
        f"[bold]{project_dir}[/bold] "
        f"([underline]{absolute_path}[/underline])"
    )
    return project_dir


@app.command()
def init(
    target_dir: Path = typer.Argument(
        Path("."),
        help="Каталог будущего рабочего пространства.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Перезаписать существующие файлы рабочего пространства.",
    ),
) -> None:
    """Создаёт рабочее пространство ``aqm`` в ``target_dir``.

    Создаются ``scripts/example_quest.py``, ``output/``, ``doc.md`` и
    ``aqm.json``. Существующие файлы не перезаписываются без ``--force``.

    Args:
        target_dir (Path): Каталог рабочего пространства.
        force (bool): Разрешить перезапись существующих файлов.
    """
    root = Path(target_dir)
    templates = get_templates_dir()
    root.mkdir(parents=True, exist_ok=True)
    (root / "output").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)

    files = {
        root / "scripts" / "example_quest.py": templates
        / "example_quest.py",
        root / "doc.md": templates / "doc.md",
        root / "aqm.json": templates / "aqm.json",
    }

    created: list[Path] = []
    skipped: list[Path] = []
    for target, source in files.items():
        if target.exists() and not force:
            skipped.append(target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        created.append(target)

    rich.print(f"[bold green]Рабочее пространство:[/bold green] {root.resolve()}")
    for path in created:
        rich.print(f"  [green]создан[/green] {path}")
    for path in skipped:
        rich.print(f"  [yellow]пропущен[/yellow] {path} (используйте --force)")
    rich.print(
        "[cyan]Дальше:[/cyan] aqm validate scripts/example_quest.py --strict"
    )
    rich.print("[cyan]Сборка:[/cyan] aqm build scripts/example_quest.py")


@app.command()
def build(
    script: Optional[Path] = typer.Argument(
        None,
        help="Python-скрипт с функцией сборки ModProject.",
    ),
) -> None:
    """Собирает мод в ``output/<slug>``.

    Без аргумента используется ``scripts/example_quest.py`` рабочего
    пространства. Если его нет, предпринимается попытка собрать встроенный
    демонстрационный Warfare-проект (если доступен пакет ``examples``).

    Args:
        script (Optional[Path]): Необязательный Python-скрипт проекта.
    """
    _, _, db_path, output_dir, vanilla_dir = _workspace()
    logger.info("CLI build запущен: script=%s.", script)

    try:
        if script is None:
            candidate = Path.cwd() / "scripts" / "example_quest.py"
            if candidate.is_file():
                script = candidate
            else:
                try:
                    from examples.cordon_warfare_demo import (
                        create_demo_project,
                    )
                except Exception as exc:  # noqa: BLE001 - необязательный демо-мод
                    logger.exception(
                        "Демонстрационный проект недоступен: %s", exc
                    )
                    rich.print(
                        "[bold red]Ошибка:[/bold red] укажите Python-скрипт "
                        "проекта или выполните 'aqm init'."
                    )
                    raise typer.Exit(code=1) from exc
                project = create_demo_project()
                with _open_db(db_path) as db:
                    _build_project(project, db, output_dir, vanilla_dir)
                return

        project = _load_project_from_script(script)
        with _open_db(db_path) as db:
            _build_project(project, db, output_dir, vanilla_dir)
    except typer.Exit:
        raise
    except FileNotFoundError as exc:
        logger.error("Скрипт проекта не найден: %s", exc)
        rich.print(f"[bold red]Ошибка:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:  # noqa: BLE001 - CLI обязан вернуть код 1
        logger.exception("Непредвиденная ошибка при сборке мода: %s", exc)
        rich.print(f"[bold red]Ошибка сборки:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


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

    Args:
        script_path (Path): Путь к Python-скрипту с фабрикой проекта.
        json_path (Optional[Path]): Необязательный путь для JSON-отчёта.
        strict (bool): Если ``True``, наличие WARNING даёт код выхода ``2``.

    Raises:
        typer.Exit: Код ``1`` при ошибке загрузки или ``ERROR`` в отчёте;
            код ``2`` при ``--strict`` и наличии WARNING.
    """
    _, _, db_path, _, _ = _workspace()
    logger.info(
        "CLI validate запущен: script=%s, json=%s, strict=%s.",
        script_path,
        json_path,
        strict,
    )

    try:
        project = _load_project_from_script(script_path)
        with _open_db(db_path) as db:
            report = validate_project(project, db=db)
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


@app.command()
def merge(
    scripts: list[Path] = typer.Argument(
        ...,
        help="Python-скрипты независимых глав мода.",
    ),
    mod_slug: Optional[str] = typer.Option(
        None,
        "--slug",
        help="Итоговый slug мода (по умолчанию из первой главы).",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        help="Каталог сборки (по умолчанию из aqm.json).",
    ),
) -> None:
    """Объединяет главы мода, проверяет и собирает результат.

    Args:
        scripts (list[Path]): Скрипты глав в порядке объединения.
        mod_slug (Optional[str]): Общий префикс пространства имён.
        output (Optional[Path]): Переопределение каталога сборки.

    Raises:
        typer.Exit: Если слияние, валидация или сборка не удались.
    """
    _, _, db_path, output_dir, vanilla_dir = _workspace()
    if output is not None:
        output_dir = Path(output)
    logger.info(
        "CLI merge запущен: scripts=%s, slug=%s.", scripts, mod_slug
    )

    try:
        chapters = [_load_project_from_script(path) for path in scripts]
        merge_report = ValidationReport()
        MergeValidator(merge_report).validate_chapters(
            chapters, target_slug=mod_slug
        )
        typer.echo(merge_report.to_text())
        if merge_report.has_errors:
            raise typer.Exit(code=1)

        merged = ModProject.merge(*chapters, mod_slug=mod_slug)
        with _open_db(db_path) as db:
            project_report = validate_project(merged, db=db)
            typer.echo(project_report.to_text())
            if project_report.has_errors:
                raise typer.Exit(code=1)
            _build_project(merged, db, output_dir, vanilla_dir)
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI обязан вернуть код 1
        logger.exception("Ошибка слияния глав: %s", exc)
        rich.print(f"[bold red]Ошибка слияния:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


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

    Args:
        query (str): Подстрока для поиска.
        type (Optional[str]): Фильтр типа сущности.

    Raises:
        typer.Exit: Если база отсутствует или поиск завершился ошибкой.
    """
    _, _, db_path, _, _ = _workspace()
    logger.info("CLI search запущен: query=%r, type=%r.", query, type)

    try:
        with _open_db(db_path) as db:
            if db is None:
                raise FileNotFoundError(str(db_path))
            assets = db.search_assets(query, type)
            db.print_assets_table(assets)
    except FileNotFoundError as exc:
        logger.error("База данных для поиска не найдена: %s", db_path)
        rich.print(
            "[bold red]Ошибка:[/bold red] файл базы данных не найден: "
            f"[underline]{db_path}[/underline]"
        )
        raise typer.Exit(code=1) from exc
    except Exception as exc:  # noqa: BLE001 - CLI обязан вернуть код 1
        logger.exception("Непредвиденная ошибка при поиске ассетов: %s", exc)
        rich.print(f"[bold red]Ошибка поиска:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    logger.info(
        "CLI search завершён: query=%r, type=%r, найдено=%d.",
        query,
        type,
        len(assets),
    )


def main() -> None:
    """Запускает Typer-приложение (точка входа ``aqm``)."""
    app()


if __name__ == "__main__":
    main()


__all__ = ["app", "build", "init", "main", "merge", "search", "validate"]
