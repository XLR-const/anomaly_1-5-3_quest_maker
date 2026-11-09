"""Репозиторий для чтения игровых данных Anomaly из SQLite.

Слой намеренно не выполняет записи в базу: только подключение, чтение и
удобное представление найденных ассетов. Все ошибки SQL логируются через
``logger.exception`` и не роняют UI/демо-скрипт.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from rich.console import Console
from rich.table import Table
from rich.text import Text

from src.logger import get_logger

logger = get_logger("db.repository")


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _py_lower(value: Any) -> Any:
    """Регистронезависимое сравнение для SQLite, включая кириллицу.

    Встроенный SQLite ``LOWER()`` корректно понижает регистр только ASCII.
    Python-функция, зарегистрированная в соединении, позволяет искать
    ``"выхлоп"`` в значении ``"ВССК «Выхлоп»"``.
    """
    if isinstance(value, str):
        return value.lower()
    return value


def _like_pattern(query: str) -> str:
    """Собирает безопасный LIKE-шаблон, экранируя спецсимволы пользователя."""
    escaped = (
        query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"


def _compact_sql(sql: str) -> str:
    """Схлопывает переводы строк для читаемого DEBUG-лога."""
    return " ".join(sql.split())


def _normalize_entity_type(entity_type: str | None) -> str | None:
    """Приводит внешнее имя типа сущности к внутреннему: npc/smart/item/squad."""
    if entity_type is None:
        return None

    mapping = {
        "npc": "npc",
        "npcs": "npc",
        "нпс": "npc",
        "персонаж": "npc",
        "smart": "smart",
        "smarts": "smart",
        "smart_terrain": "smart",
        "smart_terrains": "smart",
        "смарт": "smart",
        "item": "item",
        "items": "item",
        "предмет": "item",
        "squad": "squad",
        "squads": "squad",
        "отряд": "squad",
    }
    return mapping.get(entity_type.strip().lower())


def _split_npc_list(raw: Any) -> list[str]:
    """Возвращает человекочитаемый список NPC из TEXT-поля ``npc_list``."""
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, (list, tuple, set)):
        return [str(part).strip() for part in raw if str(part).strip()]
    return []


# ---------------------------------------------------------------------------
# SQL-шаблоны поиска
# ---------------------------------------------------------------------------


_ALIAS_SUBQUERY = {
    "npc": (
        "SELECT entity_id, MIN(alias) AS alias FROM aliases "
        "WHERE entity_type = 'npc' GROUP BY entity_id"
    ),
    "smart": (
        "SELECT entity_id, MIN(alias) AS alias FROM aliases "
        "WHERE entity_type = 'smart' GROUP BY entity_id"
    ),
    "item": (
        "SELECT entity_id, MIN(alias) AS alias FROM aliases "
        "WHERE entity_type = 'item' GROUP BY entity_id"
    ),
    "squad": (
        "SELECT entity_id, MIN(alias) AS alias FROM aliases "
        "WHERE entity_type = 'squad' GROUP BY entity_id"
    ),
}


# ---------------------------------------------------------------------------
# Основной класс
# ---------------------------------------------------------------------------


class GameDatabase:
    """Контекстный менеджер доступа к базе ассетов Anomaly.

    Пример::

        with GameDatabase(Path("data/anomaly_db.sqlite")) as db:
            npc = db.find_npc_by_alias("esc.mayor_zhurov")
            db.print_assets_table([npc])

    :param db_path: путь к основной SQLite-базе;
    :param extra_dbs: зарезервированные базы модов. Слияние пока неактивно.
    """

    def __init__(
        self,
        db_path: Path = Path("data/anomaly_db.sqlite"),
        extra_dbs: list[Path] = [],
    ) -> None:
        self.db_path = Path(db_path)
        self.extra_dbs = list(extra_dbs)
        self._closed = False

        if not self.db_path.exists():
            logger.error("Файл базы данных не найден: %s", self.db_path)
            raise FileNotFoundError(
                f"База данных не найдена: {self.db_path.resolve()}"
            )

        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            # Нужна для регистронезависимого LIKE по кириллице.
            self.conn.create_function(
                "py_lower", 1, _py_lower, deterministic=True
            )
            logger.info("Подключение к БД: %s", self.db_path.resolve())
        except sqlite3.Error:
            logger.exception("Не удалось подключиться к БД: %s", self.db_path)
            raise

        if self.extra_dbs:
            logger.warning(
                "Переданы дополнительные БД модов (%d шт.), но модуль "
                "слияния баз пока неактивен. Используется только %s.",
                len(self.extra_dbs),
                self.db_path,
            )
            try:
                cursor = self.conn.cursor()
                try:
                    self._stub_attach_extra_dbs(cursor)
                finally:
                    cursor.close()
            except Exception:
                # Заглушка не должна ломать основное подключение.
                logger.exception(
                    "Ошибка в заглушке подключения дополнительных БД модов"
                )

    # ------------------------------------------------------------------
    # Контекстный менеджер
    # ------------------------------------------------------------------

    def __enter__(self) -> "GameDatabase":
        logger.debug("Вход в контекст БД: %s", self.db_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            logger.error(
                "Работа с БД завершилась исключением %s: %s",
                exc_type.__name__,
                exc_val,
            )

        try:
            if self.conn is not None and not self._closed:
                self.conn.close()
                self._closed = True
                logger.debug("Соединение с БД закрыто: %s", self.db_path)
        except sqlite3.Error:
            logger.exception("Не удалось закрыть соединение с БД: %s", self.db_path)

        # Не подавляем исключение, если оно возникло внутри with.
        return False

    # ------------------------------------------------------------------
    # Заглушка модов
    # ------------------------------------------------------------------

    def _stub_attach_extra_dbs(self, cursor: sqlite3.Cursor) -> None:
        """Заглушка будущего слияния основной базы с базами модов (BaS и др.).

        Сейчас метод намеренно ничего не делает, кроме записи в DEBUG-лог.
        Он вызывается из ``__init__`` в try/except, поэтому даже будущая
        ошибка ATTACH не должна ломать доступ к ванильной базе.

        Архитектура будущей реализации
        ------------------------------
        1. Проверка путей
           Для каждого пути из ``extra_dbs`` проверить ``Path.exists()`` и
           убедиться, что файл действительно является SQLite-базой. Битые
           или отсутствующие моды пропускать с ``logger.warning``.

        2. ATTACH DATABASE
           Подключить каждую базу под уникальным псевдонимом::

               ATTACH DATABASE ? AS mod_1;
               ATTACH DATABASE ? AS mod_2;

           Псевдоним нельзя подставлять параметром, поэтому имя схемы
           формируется только из безопасного счётчика (``mod_1``, ``mod_2``),
           а путь передаётся через параметр. SQLite по умолчанию разрешает
           до 10 одновременно подключённых баз (можно поднять
           ``SQLITE_MAX_ATTACHED`` при сборке, но лучше не полагаться на это).

        3. Единое представление через UNION ALL
           Схемы модов могут отличаться от основной, поэтому для каждой
           таблицы создаётся временное представление с общим набором колонок.
           Например, для NPC::

               CREATE TEMP VIEW all_npcs AS
                   SELECT id, name_ru, faction, location_prefix, role,
                          source_file, 'core' AS source_db
                   FROM main.npcs
                   UNION ALL
                   SELECT id, name_ru, faction, location_prefix, role,
                          source_file, 'mod_1' AS source_db
                   FROM mod_1.npcs;

           Аналогично строятся ``all_smarts``, ``all_items``, ``all_squads``
           и ``all_aliases``. Недостающие в моде колонки заменяются на
           ``NULL``/``''``, чтобы UNION ALL не падал.

        4. Приоритет и конфликты
           Ванильные записи должны иметь приоритет. Для этого при выборке
           используется ``ROW_NUMBER() OVER (PARTITION BY id ORDER BY
           source_priority)`` либо ``GROUP BY id`` с ``MIN(source_priority)``.
           Алиасы модов добавляются к ванильным, а при совпадении алиаса
           побеждает ядро (его ``entity_id`` сохраняется).

        5. Чтение и отключение
           Все публичные методы репозитория должны обращаться не к
           ``main.npcs``, а к временным представлениям ``all_*``. После
           окончания работы (или при переподключении) выполняется::

               DETACH DATABASE mod_1;
               DETACH DATABASE mod_2;

           Временные VIEW удаляются автоматически при закрытии соединения,
           но ``DETACH`` всё равно нужен, чтобы освободить файлы модов.

        Ограничения, которые нужно учесть при реализации
        -------------------------------------------------
        * Таблицы BaS могут иметь другой набор колонок и типов — нужна
          явная миграционная карта ``mod_schema -> core_schema``.
        * Одинаковые ``id`` в моде и ванили требуют политики приоритета.
        * ATTACH не является потокобезопасным при одновременной записи,
          поэтому базы модов лучше открывать в режиме ``mode=ro``.
        * Поиск по ``name_ru`` должен использовать ту же PyLower-функцию,
          зарегистрированную в соединении, иначе кириллица снова станет
          регистрозависимой.
        """
        logger.debug(
            "Заглушка _stub_attach_extra_dbs: подготовлено %d дополнительных "
            "БД, ATTACH/UNION ALL пока не выполняется. cursor=%r",
            len(self.extra_dbs),
            cursor,
        )

    # ------------------------------------------------------------------
    # Низкоуровневые запросы
    # ------------------------------------------------------------------

    def _query(
        self, sql: str, params: Iterable[Any] = ()
    ) -> list[sqlite3.Row]:
        """Выполняет SELECT, логирует его и возвращает все строки."""
        params = tuple(params)
        logger.debug(
            "SQL: %s | params=%r", _compact_sql(sql), params
        )
        cursor = self.conn.cursor()
        try:
            cursor.execute(sql, params)
            return cursor.fetchall()
        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # Точечный поиск по алиасу
    # ------------------------------------------------------------------

    def find_npc_by_alias(self, alias: str) -> dict[str, Any] | None:
        """Найти NPC по алиасу (например, ``esc.mayor_zhurov``)."""
        try:
            rows = self._query(
                """
                SELECT 'npc' AS entity_type, a.alias, n.*
                FROM aliases AS a
                JOIN npcs AS n ON n.id = a.entity_id
                WHERE a.alias = ? AND a.entity_type = 'npc'
                LIMIT 1
                """,
                (alias,),
            )
            return dict(rows[0]) if rows else None
        except sqlite3.Error:
            logger.exception("Ошибка поиска NPC по алиасу: %r", alias)
            return None

    def find_smart_by_alias(self, alias: str) -> dict[str, Any] | None:
        """Найти смарт-террейн по алиасу."""
        try:
            rows = self._query(
                """
                SELECT 'smart' AS entity_type, a.alias, s.*
                FROM aliases AS a
                JOIN smarts AS s ON s.id = a.entity_id
                WHERE a.alias = ? AND a.entity_type = 'smart'
                LIMIT 1
                """,
                (alias,),
            )
            return dict(rows[0]) if rows else None
        except sqlite3.Error:
            logger.exception("Ошибка поиска смарта по алиасу: %r", alias)
            return None

    def find_item_by_alias(self, alias: str) -> dict[str, Any] | None:
        """Найти предмет по алиасу (например, ``weapon.vssk_vykhlop``)."""
        try:
            rows = self._query(
                """
                SELECT 'item' AS entity_type, a.alias, i.*
                FROM aliases AS a
                JOIN items AS i ON i.id = a.entity_id
                WHERE a.alias = ? AND a.entity_type = 'item'
                LIMIT 1
                """,
                (alias,),
            )
            return dict(rows[0]) if rows else None
        except sqlite3.Error:
            logger.exception("Ошибка поиска предмета по алиасу: %r", alias)
            return None

    def find_squad_by_alias(self, alias: str) -> dict[str, Any] | None:
        """Найти отряд по алиасу и добавить разобранный список NPC."""
        try:
            rows = self._query(
                """
                SELECT 'squad' AS entity_type, a.alias, s.*
                FROM aliases AS a
                JOIN squads AS s ON s.id = a.entity_id
                WHERE a.alias = ? AND a.entity_type = 'squad'
                LIMIT 1
                """,
                (alias,),
            )
            return self._decorate_squad(rows[0]) if rows else None
        except sqlite3.Error:
            logger.exception("Ошибка поиска отряда по алиасу: %r", alias)
            return None

    # ------------------------------------------------------------------
    # Живой поиск
    # ------------------------------------------------------------------

    def search_assets(
        self, query: str, entity_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Живой поиск по ``name_ru``, ``id`` и ``alias`` через SQL LIKE.

        :param query: подстрока для поиска;
        :param entity_type: ``npc``/``npcs``, ``smart``/``smarts``,
            ``item``/``items``, ``squad``/``squads`` или ``None`` (все типы).
        """
        if not isinstance(query, str) or not query.strip():
            logger.warning("Пустой поисковый запрос: %r", query)
            return []

        wanted_type = _normalize_entity_type(entity_type)
        if entity_type is not None and wanted_type is None:
            logger.warning("Неизвестный тип сущности для поиска: %r", entity_type)
            return []

        pattern = _like_pattern(query.strip())
        types = [wanted_type] if wanted_type else ["npc", "smart", "item", "squad"]
        results: list[dict[str, Any]] = []

        for asset_type in types:
            alias_subquery = _ALIAS_SUBQUERY[asset_type]

            if asset_type == "npc":
                sql = f"""
                    SELECT 'npc' AS entity_type, al.alias, n.*
                    FROM npcs AS n
                    LEFT JOIN ({alias_subquery}) AS al ON al.entity_id = n.id
                    WHERE py_lower(COALESCE(n.name_ru, '')) LIKE py_lower(?) ESCAPE '\\'
                       OR py_lower(n.id) LIKE py_lower(?) ESCAPE '\\'
                       OR py_lower(COALESCE(al.alias, '')) LIKE py_lower(?) ESCAPE '\\'
                    ORDER BY n.id
                """
                count = 3
            elif asset_type == "smart":
                sql = f"""
                    SELECT 'smart' AS entity_type, al.alias, s.*
                    FROM smarts AS s
                    LEFT JOIN ({alias_subquery}) AS al ON al.entity_id = s.id
                    WHERE py_lower(COALESCE(s.name_ru, '')) LIKE py_lower(?) ESCAPE '\\'
                       OR py_lower(s.id) LIKE py_lower(?) ESCAPE '\\'
                       OR py_lower(COALESCE(al.alias, '')) LIKE py_lower(?) ESCAPE '\\'
                    ORDER BY s.id
                """
                count = 3
            elif asset_type == "item":
                sql = f"""
                    SELECT 'item' AS entity_type, al.alias, i.*
                    FROM items AS i
                    LEFT JOIN ({alias_subquery}) AS al ON al.entity_id = i.id
                    WHERE py_lower(COALESCE(i.name_ru, '')) LIKE py_lower(?) ESCAPE '\\'
                       OR py_lower(i.id) LIKE py_lower(?) ESCAPE '\\'
                       OR py_lower(COALESCE(al.alias, '')) LIKE py_lower(?) ESCAPE '\\'
                    ORDER BY i.id
                """
                count = 3
            else:  # squad
                # У отрядов нет name_ru: ищем по id, alias, faction и составу.
                sql = f"""
                    SELECT 'squad' AS entity_type, al.alias, s.*
                    FROM squads AS s
                    LEFT JOIN ({alias_subquery}) AS al ON al.entity_id = s.id
                    WHERE py_lower(s.id) LIKE py_lower(?) ESCAPE '\\'
                       OR py_lower(COALESCE(al.alias, '')) LIKE py_lower(?) ESCAPE '\\'
                       OR py_lower(COALESCE(s.faction, '')) LIKE py_lower(?) ESCAPE '\\'
                       OR py_lower(COALESCE(s.npc_list, '')) LIKE py_lower(?) ESCAPE '\\'
                    ORDER BY s.id
                """
                count = 4

            try:
                rows = self._query(sql, (pattern,) * count)
            except sqlite3.Error:
                logger.exception(
                    "Ошибка живого поиска (%s) по запросу: %r", asset_type, query
                )
                continue

            if asset_type == "squad":
                results.extend(self._decorate_squad(row) for row in rows)
            else:
                results.extend(dict(row) for row in rows)

        logger.debug(
            "Поиск %r (тип=%r): найдено %d записей",
            query,
            entity_type,
            len(results),
        )
        return results

    # ------------------------------------------------------------------
    # Группировки
    # ------------------------------------------------------------------

    def get_locations(self) -> list[dict[str, Any]]:
        """Вернуть все локации базы (``prefix`` + ``name_ru``)."""
        try:
            rows = self._query(
                "SELECT prefix, name_ru FROM locations ORDER BY name_ru"
            )
            return [dict(row) for row in rows]
        except sqlite3.Error:
            logger.exception("Ошибка получения списка локаций")
            return []

    def get_smart_terrains_by_location(
        self, prefix: str
    ) -> list[dict[str, Any]]:
        """Вернуть смарт-террейны указанной локации (например, ``esc``)."""
        try:
            alias_subquery = _ALIAS_SUBQUERY["smart"]
            rows = self._query(
                f"""
                SELECT 'smart' AS entity_type, al.alias, s.*
                FROM smarts AS s
                LEFT JOIN ({alias_subquery}) AS al ON al.entity_id = s.id
                WHERE s.location_prefix = ?
                ORDER BY s.name_ru, s.id
                """,
                (prefix,),
            )
            return [dict(row) for row in rows]
        except sqlite3.Error:
            logger.exception(
                "Ошибка получения смартов локации: %r", prefix
            )
            return []

    def get_npcs_by_location(self, prefix: str) -> list[dict[str, Any]]:
        """Вернуть NPC, привязанных к локации ``prefix``."""
        try:
            alias_subquery = _ALIAS_SUBQUERY["npc"]
            rows = self._query(
                f"""
                SELECT 'npc' AS entity_type, al.alias, n.*
                FROM npcs AS n
                LEFT JOIN ({alias_subquery}) AS al ON al.entity_id = n.id
                WHERE n.location_prefix = ?
                ORDER BY n.name_ru, n.id
                """,
                (prefix,),
            )
            return [dict(row) for row in rows]
        except sqlite3.Error:
            logger.exception("Ошибка получения NPC локации: %r", prefix)
            return []

    def get_safe_squads_by_faction(self, faction: str) -> list[dict[str, Any]]:
        """Вернуть только безопасные полевые отряды указанной фракции."""
        try:
            alias_subquery = _ALIAS_SUBQUERY["squad"]
            rows = self._query(
                f"""
                SELECT 'squad' AS entity_type, al.alias, s.*
                FROM squads AS s
                LEFT JOIN ({alias_subquery}) AS al ON al.entity_id = s.id
                WHERE s.faction = ? AND s.is_safe_field = 1
                ORDER BY s.id
                """,
                (faction,),
            )
            return [self._decorate_squad(row) for row in rows]
        except sqlite3.Error:
            logger.exception(
                "Ошибка получения безопасных отрядов фракции: %r", faction
            )
            return []

    # ------------------------------------------------------------------
    # Системный экспорт
    # ------------------------------------------------------------------

    def get_all_valid_aliases(self) -> set[str]:
        """Вернуть множество всех валидных алиасов для быстрой валидации."""
        try:
            rows = self._query(
                "SELECT alias FROM aliases WHERE alias IS NOT NULL AND alias <> ''"
            )
            return {row["alias"] for row in rows}
        except sqlite3.Error:
            logger.exception("Ошибка экспорта множества алиасов")
            return set()

    # ------------------------------------------------------------------
    # Визуализация
    # ------------------------------------------------------------------

    @staticmethod
    def _decorate_squad(row: sqlite3.Row) -> dict[str, Any]:
        """Преобразует строку отряда в dict и разбирает ``npc_list``."""
        data = dict(row)
        data["npc_members"] = _split_npc_list(data.get("npc_list"))
        return data

    def print_assets_table(
        self, assets: list[dict[str, Any]], title: str = "Превью ассетов"
    ) -> None:
        """Печатает цветную таблицу ассетов в терминал через Rich.

        Для отрядов в колонке «Название/Состав» выводится список NPC из
        ``npc_list``. Безопасные полевые отряды (``is_safe_field == 1``)
        подсвечиваются зелёным, опасные скриптовые (``is_safe_field == 0``) —
        красным.
        """
        console = Console()
        table = Table(
            title=title,
            show_lines=True,
            header_style="bold cyan",
            title_style="bold white",
        )
        table.add_column("Тип", style="bold magenta", no_wrap=True)
        table.add_column("Алиас", style="cyan", overflow="fold", max_width=32)
        table.add_column(
            "Игровой ID", style="yellow", overflow="fold", max_width=44
        )
        table.add_column("Название/Состав", overflow="fold")

        type_labels = {
            "npc": "NPC",
            "smart": "Смарт",
            "item": "Предмет",
            "squad": "Отряд",
        }

        if not assets:
            table.add_row(
                Text("—", style="dim"),
                Text("—", style="dim"),
                Text("—", style="dim"),
                Text("Ничего не найдено", style="dim italic"),
            )
            console.print(table)
            return

        for asset in assets:
            if not isinstance(asset, dict):
                logger.warning("Пропущен не-dict ассет в превью: %r", asset)
                continue

            asset_type = str(asset.get("entity_type") or "").lower()
            if not asset_type:
                # На случай, если передан результат старой/внешней выборки
                # без явного entity_type.
                if "is_safe_field" in asset or "npc_list" in asset:
                    asset_type = "squad"
                elif "category" in asset or "cost" in asset:
                    asset_type = "item"
                elif "role" in asset or "faction" in asset:
                    asset_type = "npc"
                elif "location_prefix" in asset:
                    asset_type = "smart"

            type_label = type_labels.get(asset_type, asset_type or "—")
            alias = str(asset.get("alias") or "—")
            entity_id = str(asset.get("id") or asset.get("entity_id") or "—")

            row_style: str | None = None
            if asset_type == "squad":
                members = asset.get("npc_members")
                if members is None:
                    members = _split_npc_list(asset.get("npc_list"))
                composition = ", ".join(str(m) for m in members) or "—"
                faction = asset.get("faction") or "—"
                safe = asset.get("is_safe_field")
                name_cell = f"{composition}  (фракция: {faction})"
                if safe == 1:
                    row_style = "green"
                    name_cell = f"[БЕЗОПАСНЫЙ] {name_cell}"
                elif safe == 0:
                    row_style = "red"
                    name_cell = f"[ОПАСНЫЙ] {name_cell}"
            else:
                name_cell = str(asset.get("name_ru") or "—")

            table.add_row(
                Text(type_label),
                Text(alias),
                Text(entity_id),
                Text(name_cell),
                style=row_style,
            )

        console.print(table)
