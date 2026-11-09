#!/usr/bin/env python
"""Интерактивное демо поиска по базе ассетов Anomaly.

Запуск из корня проекта::

    python examples/db_search_demo.py

Скрипт ищет отряды по слову ``army`` и предметы по слову ``выхлоп``/``vssk``,
после чего печатает цветное превью через ``GameDatabase.print_assets_table``.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console  # noqa: E402

from src.db.repository import GameDatabase  # noqa: E402


def main() -> None:
    console = Console()
    db_path = PROJECT_ROOT / "data" / "anomaly_db.sqlite"

    with GameDatabase(db_path) as db:
        console.print(
            f"[bold cyan]База:[/bold cyan] {db_path}\n"
            f"[bold cyan]Всего алиасов:[/bold cyan] "
            f"{len(db.get_all_valid_aliases())}"
        )

        # 1. Живой поиск отрядов: faction/id/alias содержат "army".
        squads = db.search_assets("army", entity_type="squad")
        if not squads:
            # Резервный запрос, если в базе когда-нибудь поменяются id/faction.
            squads = db.search_assets("воен", entity_type="squad")
        console.print(
            f"\n[bold]Найдено отрядов по запросу «army»:[/bold] {len(squads)}"
        )
        db.print_assets_table(squads, title="Отряды: поиск «army»")

        # 2. Живой поиск предметов: сначала русское название, затем section.
        items = db.search_assets("выхлоп", entity_type="item")
        query_used = "выхлоп"
        if not items:
            items = db.search_assets("vssk", entity_type="item")
            query_used = "vssk"
        console.print(
            f"\n[bold]Найдено предметов по запросу «{query_used}»:[/bold] "
            f"{len(items)}"
        )
        db.print_assets_table(
            items, title=f"Предметы: поиск «{query_used}»"
        )


if __name__ == "__main__":
    main()
