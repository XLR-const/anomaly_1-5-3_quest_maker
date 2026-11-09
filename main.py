"""Единый CLI-интерфейс конструктора сюжетных квестов Anomaly.

Модуль предоставляет две команды:

* ``search`` — живой поиск предметов, NPC, смартов и отрядов в SQLite-базе
  игры с выводом результата в виде цветной Rich-таблицы;
* ``build`` — создание демонстрационного Warfare-проекта, его runtime-проверка
  и автоматическая сборка установочной папки мода в ``output/<slug>``.

Запуск из корня проекта::

    python main.py search выхлоп --type item
    python main.py build
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import rich
import typer

from examples.cordon_warfare_demo import create_demo_project
from src.compiler.builder import ModBuilder, _slugify
from src.core.validator import ProjectValidator
from src.db.repository import GameDatabase
from src.logger import get_logger

logger = get_logger("cli")

#: Корень проекта. Путь к базе не зависит от текущего рабочего каталога.
PROJECT_ROOT = Path(__file__).resolve().parent
#: Основная SQLite-база ассетов Anomaly.
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "anomaly_db.sqlite"

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


if __name__ == "__main__":
    app()


__all__ = ["app", "build", "search"]
