"""Справочная валидация ассетов проекта по SQLite-базе Anomaly.

Модуль реализует проверки ``CAT-*`` из ``docs/VALIDATION_SPEC.md`` (§4.3).
Валидатор не изменяет проект и не поднимает исключений: все нарушения
накапливаются в переданном :class:`~src.validation.report.ValidationReport`.
"""

from __future__ import annotations

import re
import sqlite3
from typing import TYPE_CHECKING, Any, Iterator

from src.core.models import (
    BaseAction,
    BaseCondition,
    CustomSquad,
    Dialog,
    GiveItem,
    HasItem,
    ModProject,
    Phrase,
    Quest,
    RemoveItem,
    RemoveSquad,
    SetTarget,
    SmartOwner,
    SpawnNpcItem,
    SpawnSquad,
    Stage,
    TakeItem,
    WarfareCapture,
)
from src.validation.report import Severity, ValidationReport

if TYPE_CHECKING:
    from src.db.repository import GameDatabase


#: Синонимы полных названий локаций и технических префиксов БД.
_LOCATION_SYNONYMS = {
    "cordon": "esc",
    "escape": "esc",
    "zaton": "zat",
    "jupiter": "jup",
    "pripyat": "pri",
    "agroprom": "agr",
    "deadcity": "dc",
    "dead_city": "dc",
    "generators": "gen",
    "limansk": "lim",
}

#: Фракции, которые считаются валидными даже на пустой/урезанной БД.
_FALLBACK_FACTIONS = {
    "army",
    "bandit",
    "csky",
    "dolg",
    "ecolog",
    "freedom",
    "greh",
    "isg",
    "killer",
    "merc",
    "monolith",
    "renegade",
    "stalker",
    "trader",
    "zombied",
}

#: Соответствие префиксов случайных NPC-шаблонов техническим фракциям.
_TEMPLATE_FACTION_ALIASES = {
    "military": "army",
    "merc": "killer",
    "monster": "monster",
}

_GENERIC_NPC_TEMPLATE_RE = re.compile(
    r"^sim_default_(?:"
    r"stalker|bandit|killer|military|army|dolg|freedom|monolith|csky|"
    r"ecolog|greh|renegade|zombied|isg|merc|trader|novice|rookie|"
    r"veteran|master|expert|assault|patrol|defense|defence|sniper|guard"
    r")_[a-z0-9_]+$",
    re.IGNORECASE,
)

#: Суффикс XML-профиля ``<specific_character id="..._default_N">``.
#: Такие ID — профили персонажей, а не LTX spawn-секции: движок X-Ray
#: отвечает на них ``!ERROR: npc section ... does not exist!``.
_SPAWN_PROFILE_SUFFIX_RE = re.compile(r"^(?P<base>.+)_default_\d+$", re.IGNORECASE)

#: Допустимый технический ID кастомного NPC/отряда (``CAT-CUSTOM-001``).
_CUSTOM_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")

#: Допустимые ранги ``CustomNpc.spec_rank``.
_CUSTOM_SPEC_RANKS = {"novice", "regular", "veteran", "master"}


class _ActionContext:
    """Контекст одного действия проекта для формирования ``target_id``."""

    __slots__ = ("owner", "quest", "stage", "action")

    def __init__(
        self,
        owner: str,
        quest: Quest | None,
        stage: Stage | None,
        action: BaseAction,
    ) -> None:
        self.owner = owner
        self.quest = quest
        self.stage = stage
        self.action = action


class CatalogValidator:
    """Проверяет ссылки проекта на NPC, смарты, предметы, отряды и фракции."""

    def __init__(self, db: "GameDatabase", report: ValidationReport) -> None:
        """Сохраняет клиент БД и целевой отчёт.

        Args:
            db: Клиент ``GameDatabase`` с открытым соединением.
            report: Отчёт, в который добавляются замечания.
        """
        self.db = db
        self.report = report

        self._npc_rows: dict[str, list[dict[str, Any]]] | None = None
        self._npc_spawn_sections: set[str] | None = None
        self._smart_rows: dict[str, list[dict[str, Any]]] | None = None
        self._item_ids: set[str] | None = None
        self._squad_rows: dict[str, list[dict[str, Any]]] | None = None
        self._aliases: dict[tuple[str, str], str] | None = None
        self._factions: set[str] | None = None
        self._project: ModProject | None = None
        self._project_npc_aliases: set[str] | None = None
        self._vanilla_aliases_cache: set[str] | None = None

    # ------------------------------------------------------------------
    # Низкоуровневый доступ к БД
    # ------------------------------------------------------------------

    def _fetch_all(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        """Выполняет SELECT и возвращает список словарей.

        Ошибки SQLite не пробрасываются: валидатор обязан завершиться и
        сохранить уже найденные замечания.
        """
        conn = getattr(self.db, "conn", None)
        if conn is None:
            return []
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            if rows and not isinstance(rows[0], sqlite3.Row):
                columns = [description[0] for description in cursor.description]
                return [dict(zip(columns, row)) for row in rows]
            return [dict(row) for row in rows]
        except sqlite3.Error:
            return []
        finally:
            cursor.close()

    def _npc_index(self) -> dict[str, list[dict[str, Any]]]:
        """Возвращает индекс NPC-профилей по ``specific_character id``."""
        if self._npc_rows is None:
            rows = self._fetch_all(
                "SELECT id, name_ru, faction, location_prefix, source_file "
                "FROM npcs"
            )
            index: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                entity_id = str(row.get("id") or "").strip()
                if entity_id:
                    index.setdefault(entity_id, []).append(row)
            self._npc_rows = index
        return self._npc_rows

    def _npc_spawn_section_names(self) -> set[str]:
        """Возвращает имена реальных LTX spawn-секций NPC.

        В таблице ``npcs`` хранятся XML-профили ``<specific_character>``,
        поэтому профили с суффиксом ``_default_N`` приводятся к базовой
        spawn-секции (``sim_default_monolith_3_default_0`` ->
        ``sim_default_monolith_3``). Дополнительно учитываются NPC-секции,
        которые ванильные отряды используют в ``squads.npc_list``.
        """
        if self._npc_spawn_sections is None:
            sections: set[str] = set()
            for row in self._fetch_all("SELECT id FROM npcs"):
                entity_id = self._normalize(row.get("id"))
                if not entity_id:
                    continue
                match = _SPAWN_PROFILE_SUFFIX_RE.match(entity_id)
                if match:
                    sections.add(match.group("base"))
                else:
                    # Уникальные профили (esc_2_12_stalker_wolf) обычно
                    # имеют одноимённую spawn-секцию.
                    sections.add(entity_id)
            for row in self._fetch_all("SELECT npc_list FROM squads"):
                raw = row.get("npc_list")
                if isinstance(raw, str):
                    for part in raw.split(","):
                        token = part.strip()
                        if token:
                            sections.add(token)
            self._npc_spawn_sections = sections
        return self._npc_spawn_sections

    def _smart_index(self) -> dict[str, list[dict[str, Any]]]:
        """Возвращает индекс смартов по ID."""
        if self._smart_rows is None:
            rows = self._fetch_all(
                "SELECT id, name_ru, location_prefix FROM smarts"
            )
            index: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                entity_id = str(row.get("id") or "").strip()
                if entity_id:
                    index.setdefault(entity_id, []).append(row)
            self._smart_rows = index
        return self._smart_rows

    def _squad_index(self) -> dict[str, list[dict[str, Any]]]:
        """Возвращает индекс отрядов БД по ID."""
        if self._squad_rows is None:
            rows = self._fetch_all(
                "SELECT id, faction, tier, is_safe_field, npc_list FROM squads"
            )
            index: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                entity_id = str(row.get("id") or "").strip()
                if entity_id:
                    index.setdefault(entity_id, []).append(row)
            self._squad_rows = index
        return self._squad_rows

    def _item_index(self) -> set[str]:
        """Возвращает множество ID предметов БД."""
        if self._item_ids is None:
            rows = self._fetch_all("SELECT id FROM items")
            self._item_ids = {
                str(row.get("id") or "").strip()
                for row in rows
                if str(row.get("id") or "").strip()
            }
        return self._item_ids

    def _alias_index(self) -> dict[tuple[str, str], str]:
        """Возвращает индекс ``(entity_type, alias) -> entity_id``."""
        if self._aliases is None:
            rows = self._fetch_all(
                "SELECT alias, entity_type, entity_id FROM aliases"
            )
            index: dict[tuple[str, str], str] = {}
            for row in rows:
                alias = str(row.get("alias") or "").strip()
                entity_type = str(row.get("entity_type") or "").strip()
                entity_id = str(row.get("entity_id") or "").strip()
                if alias and entity_type and entity_id:
                    index[(entity_type, alias)] = entity_id
            self._aliases = index
        return self._aliases

    # ------------------------------------------------------------------
    # Резолверы
    # ------------------------------------------------------------------

    def resolve_npc(
        self, alias_or_id: str | None, location: str | None = None
    ) -> dict[str, Any] | None:
        """Ищет NPC по точному ID или алиасу."""
        name = self._normalize(alias_or_id)
        if not name:
            return None
        rows = self._npc_index().get(name)
        if rows:
            return self._select_by_location(rows, location)
        entity_id = self._alias_index().get(("npc", name))
        if entity_id:
            rows = self._npc_index().get(entity_id)
            if rows:
                return self._select_by_location(rows, location)
        return None

    def resolve_smart(self, name: str | None) -> dict[str, Any] | None:
        """Ищет смарт по точному ID или алиасу."""
        value = self._normalize(name)
        if not value:
            return None
        rows = self._smart_index().get(value)
        if rows:
            return rows[0]
        entity_id = self._alias_index().get(("smart", value))
        if entity_id:
            rows = self._smart_index().get(entity_id)
            if rows:
                return rows[0]
        return None

    def resolve_item(self, alias_or_id: str | None) -> dict[str, Any] | None:
        """Ищет предмет по точному ID или алиасу."""
        value = self._normalize(alias_or_id)
        if not value:
            return None
        if value in self._item_index():
            return {"id": value}
        entity_id = self._alias_index().get(("item", value))
        if entity_id and entity_id in self._item_index():
            return {"id": entity_id}
        return None

    def resolve_squad(self, alias_or_id: str | None) -> dict[str, Any] | None:
        """Ищет отряд БД по точному ID или алиасу."""
        value = self._normalize(alias_or_id)
        if not value:
            return None
        rows = self._squad_index().get(value)
        if rows:
            return rows[0]
        entity_id = self._alias_index().get(("squad", value))
        if entity_id:
            rows = self._squad_index().get(entity_id)
            if rows:
                return rows[0]
        return None

    def resolve_faction(self, name: str | None) -> str | None:
        """Проверяет техническое имя фракции и возвращает его в нижнем регистре."""
        value = self._normalize(name).lower()
        if not value:
            return None
        return value if value in self._valid_factions() else None

    def _valid_factions(self) -> set[str]:
        """Собирает валидные фракции из БД и встроенного fallback-набора."""
        if self._factions is None:
            factions = set(_FALLBACK_FACTIONS)
            for row in self._fetch_all(
                "SELECT DISTINCT faction FROM npcs "
                "WHERE faction IS NOT NULL AND faction <> ''"
            ):
                value = str(row.get("faction") or "").strip().lower()
                if value:
                    factions.add(value)
            for row in self._fetch_all(
                "SELECT DISTINCT faction FROM squads "
                "WHERE faction IS NOT NULL AND faction <> ''"
            ):
                value = str(row.get("faction") or "").strip().lower()
                if value:
                    factions.add(value)
            self._factions = factions
        return self._factions

    # ------------------------------------------------------------------
    # Вспомогательные проверки
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(value: Any) -> str:
        """Приводит необязательное значение к очищенной строке."""
        if value is None:
            return ""
        return str(value).strip()

    # ------------------------------------------------------------------
    # Кастомные NPC/отряды: общие помощники
    # ------------------------------------------------------------------

    def _custom_npc_aliases(self) -> set[str]:
        """Возвращает ID/профили/story_id кастомных NPC проекта."""
        if self._project_npc_aliases is None:
            aliases: set[str] = set()
            for npc in (
                getattr(self._project, "npcs", None) or {}
            ).values():
                for value in (
                    getattr(npc, "id", None),
                    getattr(npc, "character_profile", None),
                    getattr(npc, "story_id", None),
                ):
                    name = self._normalize(value)
                    if name:
                        aliases.add(name)
            self._project_npc_aliases = aliases
        return self._project_npc_aliases

    def _find_custom_npc(self, alias: str | None):
        """Ищет ``CustomNpc`` проекта по id, профилю или ``story_id``."""
        name = self._normalize(alias)
        if not name or self._project is None:
            return None
        for npc in (getattr(self._project, "npcs", None) or {}).values():
            for value in (
                getattr(npc, "id", None),
                getattr(npc, "character_profile", None),
                getattr(npc, "story_id", None),
            ):
                if self._normalize(value) == name:
                    return npc
        return None

    @staticmethod
    def _project_slug(project: ModProject) -> str:
        """Возвращает ``mod_slug`` проекта или безопасный slug из ``name``."""
        slug = CatalogValidator._normalize(
            getattr(project, "mod_slug", None)
        ).lower()
        if slug:
            return slug
        raw = CatalogValidator._normalize(getattr(project, "name", "")).lower()
        slug = re.sub(r"[^a-z0-9_]+", "_", raw)
        slug = re.sub(r"_+", "_", slug).strip("_")
        return slug

    def _vanilla_aliases(self) -> set[str]:
        """Собирает известные ванильные алиасы для ``CAT-CUSTOM-001/005``."""
        if self._vanilla_aliases_cache is None:
            aliases: set[str] = set()
            if self.db is not None:
                getter = getattr(self.db, "get_all_valid_aliases", None)
                if callable(getter):
                    try:
                        aliases.update(
                            self._normalize(value)
                            for value in (getter() or set())
                            if self._normalize(value)
                        )
                    except Exception:  # noqa: BLE001 - БД не должна ронять валидатор
                        pass
            if not aliases:
                aliases.update(
                    alias for (_type, alias) in self._alias_index().items()
                )
            self._vanilla_aliases_cache = aliases
        return self._vanilla_aliases_cache

    @staticmethod
    def _select_by_location(
        rows: list[dict[str, Any]], location: str | None
    ) -> dict[str, Any]:
        """Выбирает профиль NPC, предпочитая совпадение по локации."""
        wanted = str(location or "").strip().lower()
        if wanted:
            for row in rows:
                prefix = str(row.get("location_prefix") or "").lower()
                source = str(row.get("source_file") or "").lower()
                if wanted in source or wanted == prefix:
                    return row
        return rows[0]

    @staticmethod
    def _is_generic_npc_template(name: str) -> bool:
        """``True`` для стандартных ``sim_default_*`` NPC-секций."""
        return bool(_GENERIC_NPC_TEMPLATE_RE.match(name))

    @staticmethod
    def _location_matches(
        row: dict[str, Any], location: str
    ) -> bool:
        """Проверяет, что локация соответствует профилю NPC."""
        wanted = location.strip().lower().replace(" ", "_")
        if not wanted:
            return True
        mapped = _LOCATION_SYNONYMS.get(wanted, wanted)
        prefix = str(row.get("location_prefix") or "").strip().lower()
        source = str(row.get("source_file") or "").strip().lower()
        if prefix and (
            mapped == prefix
            or mapped.startswith(prefix)
            or prefix.startswith(mapped)
        ):
            return True
        if wanted in source or mapped in source:
            return True
        return False

    @staticmethod
    def _location_matches_prefix(location: str, prefix: str) -> bool:
        """Сравнивает полное имя локации с техническим префиксом."""
        wanted = location.strip().lower().replace(" ", "_")
        if not wanted or not prefix:
            return True
        mapped = _LOCATION_SYNONYMS.get(wanted, wanted)
        prefix = prefix.strip().lower()
        return (
            mapped == prefix
            or mapped.startswith(prefix)
            or prefix.startswith(mapped)
            or wanted in prefix
        )

    def _find_project_squad(
        self, project: ModProject, alias: str
    ) -> CustomSquad | None:
        """Ищет отряд проекта по ключу, ``id`` или ``story_id``."""
        for key, squad in (project.squads or {}).items():
            if str(key).strip() == alias:
                return squad
            if str(squad.id).strip() == alias:
                return squad
            if self._normalize(squad.story_id) == alias:
                return squad
        return None

    def _squad_exists(self, project: ModProject, alias: str) -> bool:
        """``True``, если алиас есть в ``project.squads`` или в БД отрядов."""
        name = self._normalize(alias)
        if not name:
            return False
        if self._find_project_squad(project, name) is not None:
            return True
        return self.resolve_squad(name) is not None

    # ------------------------------------------------------------------
    # Итераторы по проекту
    # ------------------------------------------------------------------

    def _quest_for_dialog(
        self, project: ModProject, dialog: Dialog
    ) -> Quest | None:
        """Находит квест, связанный с диалогом через ``task_id``/``dialog_ids``."""
        if dialog.task_id:
            quest = (project.quests or {}).get(dialog.task_id)
            if quest is not None:
                return quest
            for candidate in (project.quests or {}).values():
                if candidate.id == dialog.task_id:
                    return candidate
        dialog_id = self._normalize(dialog.id)
        for quest in (project.quests or {}).values():
            if dialog_id and (
                self._normalize(quest.dialog_id) == dialog_id
                or dialog_id in {
                    self._normalize(item) for item in quest.dialog_ids
                }
            ):
                return quest
        return None

    def _iter_actions(self, project: ModProject) -> Iterator[_ActionContext]:
        """Перебирает все действия квестов, этапов и реплик."""
        for quest in (project.quests or {}).values():
            for field_name in (
                "on_init_actions",
                "on_complete_actions",
                "on_fail_actions",
            ):
                for index, action in enumerate(
                    getattr(quest, field_name, []) or []
                ):
                    yield _ActionContext(
                        f"quest:{quest.id}.{field_name}[{index}]",
                        quest,
                        None,
                        action,
                    )
            for stage in (quest.stages or {}).values():
                for index, action in enumerate(
                    stage.on_start_actions or []
                ):
                    yield _ActionContext(
                        f"quest:{quest.id}.stage:{stage.id}"
                        f".on_start_actions[{index}]",
                        quest,
                        stage,
                        action,
                    )
        for dialog in (project.dialogs or {}).values():
            quest = self._quest_for_dialog(project, dialog)
            for phrase in (dialog.phrases or {}).values():
                for index, action in enumerate(phrase.actions or []):
                    yield _ActionContext(
                        f"dialog:{dialog.id}.phrase:{phrase.id}"
                        f".actions[{index}]",
                        quest,
                        None,
                        action,
                    )

    def _iter_conditions(
        self, project: ModProject
    ) -> Iterator[tuple[str, Quest | None, BaseCondition]]:
        """Перебирает условия, которые могут ссылаться на ассеты."""
        for dialog in (project.dialogs or {}).values():
            quest = self._quest_for_dialog(project, dialog)
            for index, condition in enumerate(dialog.preconditions or []):
                yield f"dialog:{dialog.id}.preconditions[{index}]", quest, condition
            for phrase in (dialog.phrases or {}).values():
                for index, condition in enumerate(
                    phrase.preconditions or []
                ):
                    yield (
                        f"dialog:{dialog.id}.phrase:{phrase.id}"
                        f".preconditions[{index}]",
                        quest,
                        condition,
                    )

        for quest in (project.quests or {}).values():
            for stage_id, rules in (quest.transfer_conditions or {}).items():
                for result, conditions in (rules or {}).items():
                    for index, condition in enumerate(conditions or []):
                        yield (
                            f"quest:{quest.id}.transfer_conditions"
                            f"[{stage_id}].{result}[{index}]",
                            quest,
                            condition,
                        )
            for index, condlist in enumerate(quest.extra_condlists or []):
                for condition_index, condition in enumerate(
                    condlist.when or []
                ):
                    yield (
                        f"quest:{quest.id}.extra_condlists[{index}]"
                        f".when[{condition_index}]",
                        quest,
                        condition,
                    )
            for stage in (quest.stages or {}).values():
                for index, variant in enumerate(
                    stage.target_variants or []
                ):
                    for condition_index, condition in enumerate(
                        variant.when or []
                    ):
                        yield (
                            f"quest:{quest.id}.stage:{stage.id}"
                            f".target_variants[{index}]"
                            f".when[{condition_index}]",
                            quest,
                            condition,
                        )
                for index, variant in enumerate(
                    stage.descr_variants or []
                ):
                    for condition_index, condition in enumerate(
                        variant.when or []
                    ):
                        yield (
                            f"quest:{quest.id}.stage:{stage.id}"
                            f".descr_variants[{index}]"
                            f".when[{condition_index}]",
                            quest,
                            condition,
                        )

    # ------------------------------------------------------------------
    # Публичная точка входа
    # ------------------------------------------------------------------

    def validate(self, project: ModProject) -> None:
        """Проверяет проект по всем правилам ``CAT-*``."""
        self._project = project
        self._project_npc_aliases = None
        self._vanilla_aliases_cache = None
        self._validate_custom_entities(project)
        self._validate_npcs(project)
        self._validate_smarts(project)
        self._validate_items(project)
        self._validate_squads(project)
        self._validate_warfare(project)
        self._validate_factions(project)
        self._validate_dialogs(project)

    # ------------------------------------------------------------------
    # CAT-CUSTOM-001..012
    # ------------------------------------------------------------------

    def _validate_custom_entities(self, project: ModProject) -> None:
        """Проверяет ``project.npcs`` и ``template_squad_id`` отрядов."""
        npcs = list((getattr(project, "npcs", None) or {}).values())
        squads = list((getattr(project, "squads", None) or {}).values())
        if not npcs and not squads:
            return

        slug = self._project_slug(project)
        prefix = f"{slug}_" if slug else ""
        vanilla_aliases = self._vanilla_aliases()
        story_owners: dict[str, list[str]] = {}
        profiles: dict[str, str] = {}

        giver_ids: set[str] = set()
        for quest in (project.quests or {}).values():
            for value in (quest.npc_id, quest.giver_npc_id):
                name = self._normalize(value)
                if name:
                    giver_ids.add(name)
        for dialog in (project.dialogs or {}).values():
            name = self._normalize(getattr(dialog, "npc_id", None))
            if name:
                giver_ids.add(name)

        for npc in npcs:
            npc_id = self._normalize(getattr(npc, "id", None))
            target_id = f"npc:{npc_id or '<unknown>'}"
            if not npc_id:
                continue

            # CAT-CUSTOM-001: синтаксис, префикс slug и коллизия с ванилью.
            if not _CUSTOM_ID_RE.match(npc_id):
                self.report.add(
                    "CAT-CUSTOM-001",
                    Severity.ERROR,
                    target_id,
                    f"ID кастомного NPC '{npc_id}' не соответствует "
                    "^[a-z][a-z0-9_]{2,63}$.",
                    hint="Используйте нижний регистр, цифры и '_'.",
                    owner="npc",
                    npc_id=npc_id,
                )
            elif prefix and not npc_id.startswith(prefix):
                self.report.add(
                    "CAT-CUSTOM-001",
                    Severity.ERROR,
                    target_id,
                    f"ID кастомного NPC '{npc_id}' не начинается с "
                    f"префикса '{prefix}'.",
                    hint=f"Используйте ID вида '{prefix}<name>'.",
                    owner="npc",
                    npc_id=npc_id,
                )
            if npc_id in vanilla_aliases or npc_id in self._npc_index():
                self.report.add(
                    "CAT-CUSTOM-001",
                    Severity.ERROR,
                    target_id,
                    f"ID кастомного NPC '{npc_id}' совпадает с ванильным "
                    "алиасом/ID из БД.",
                    hint="Переименуйте NPC: он не должен перезаписывать ваниль.",
                    owner="npc",
                    npc_id=npc_id,
                )

            # CAT-CUSTOM-007: $spawn строится только из id.
            if npc_id.startswith("respawn_"):
                self.report.add(
                    "CAT-CUSTOM-007",
                    Severity.ERROR,
                    target_id,
                    f"ID '{npc_id}' переиспользует ванильный respawn-путь.",
                    hint="Уберите префикс 'respawn_': $spawn строится из id.",
                    owner="npc",
                    npc_id=npc_id,
                )

            # CAT-CUSTOM-003: community и spec_rank.
            if self.resolve_faction(getattr(npc, "faction", None)) is None:
                self.report.add(
                    "CAT-CUSTOM-003",
                    Severity.ERROR,
                    f"{target_id}.faction",
                    f"Неизвестная фракция кастомного NPC '{npc_id}': "
                    f"'{getattr(npc, 'faction', '')}'.",
                    hint="Используйте техническое имя: stalker, bandit, army, ...",
                    owner="npc",
                    npc_id=npc_id,
                    faction=getattr(npc, "faction", ""),
                )
            spec_rank = self._normalize(getattr(npc, "spec_rank", ""))
            if spec_rank and spec_rank not in _CUSTOM_SPEC_RANKS:
                self.report.add(
                    "CAT-CUSTOM-003",
                    Severity.ERROR,
                    f"{target_id}.spec_rank",
                    f"Недопустимый spec_rank '{spec_rank}'.",
                    hint="novice, regular, veteran или master.",
                    owner="npc",
                    npc_id=npc_id,
                )

            # CAT-CUSTOM-009: visual/icon/bio (WARN, шаблон считается донором).
            template_id = self._normalize(
                getattr(npc, "template_npc_id", None)
            )
            visual = self._normalize(getattr(npc, "visual", None))
            if not template_id:
                if not visual:
                    self.report.add(
                        "CAT-CUSTOM-009",
                        Severity.WARNING,
                        f"{target_id}.visual",
                        f"У NPC '{npc_id}' не задан visual и нет шаблона.",
                        hint="Задайте visual='actors\\\\...' или template_npc_id.",
                        owner="npc",
                        npc_id=npc_id,
                    )
                elif not visual.startswith("actors\\"):
                    self.report.add(
                        "CAT-CUSTOM-009",
                        Severity.WARNING,
                        f"{target_id}.visual",
                        f"visual NPC '{npc_id}' не начинается с 'actors\\'.",
                        hint="Путь модели обычно начинается с 'actors\\\\'.",
                        owner="npc",
                        npc_id=npc_id,
                    )
                if not self._normalize(getattr(npc, "icon", None)):
                    self.report.add(
                        "CAT-CUSTOM-009",
                        Severity.WARNING,
                        f"{target_id}.icon",
                        f"У NPC '{npc_id}' не задан icon.",
                        hint="Задайте icon или template_npc_id.",
                        owner="npc",
                        npc_id=npc_id,
                    )
                if not self._normalize(getattr(npc, "bio", None)):
                    self.report.add(
                        "CAT-CUSTOM-009",
                        Severity.WARNING,
                        f"{target_id}.bio",
                        f"У NPC '{npc_id}' не задан bio.",
                        hint="Задайте bio или template_npc_id.",
                        owner="npc",
                        npc_id=npc_id,
                    )

            # CAT-CUSTOM-011: template_npc_id обязан быть в npcs БД.
            if template_id and self.resolve_npc(template_id) is None:
                self.report.add(
                    "CAT-CUSTOM-011",
                    Severity.ERROR,
                    f"{target_id}.template_npc_id",
                    f"template_npc_id '{template_id}' не найден в таблице "
                    "npcs БД.",
                    hint="Проверьте ID донора через main.py search.",
                    owner="npc",
                    npc_id=npc_id,
                    template_npc_id=template_id,
                )

            # CAT-CUSTOM-008: spawn_smart — существующий алиас смарта.
            spawn_smart = self._normalize(
                getattr(npc, "spawn_smart", None)
            )
            if spawn_smart and self.resolve_smart(spawn_smart) is None:
                self.report.add(
                    "CAT-CUSTOM-008",
                    Severity.ERROR,
                    f"{target_id}.spawn_smart",
                    f"spawn_smart '{spawn_smart}' не найден в БД смартов.",
                    hint="Укажите существующий ID/алиас смарта.",
                    owner="npc",
                    npc_id=npc_id,
                    smart_alias=spawn_smart,
                )

            # CAT-CUSTOM-002: профиль обязан быть уникален (тройная связка
            # проверяется после сборки, здесь ловятся дубли до эмита).
            profile = self._normalize(
                getattr(npc, "character_profile", None)
            ) or npc_id
            if profile in profiles:
                self.report.add(
                    "CAT-CUSTOM-002",
                    Severity.ERROR,
                    f"{target_id}.character_profile",
                    f"character_profile '{profile}' уже занят NPC "
                    f"'{profiles[profile]}'.",
                    hint="Профиль должен быть уникален в проекте.",
                    owner="npc",
                    npc_id=npc_id,
                    character_profile=profile,
                )
            else:
                profiles[profile] = npc_id

            # CAT-CUSTOM-006: бессмертный квестодатель обязан иметь story_id.
            story_id = self._normalize(getattr(npc, "story_id", None))
            aliases = {
                npc_id,
                profile,
                self._normalize(getattr(npc, "character_profile", None)),
                story_id,
            }
            is_giver = bool(aliases & giver_ids)
            if getattr(npc, "immortal", False) and is_giver and not story_id:
                self.report.add(
                    "CAT-CUSTOM-006",
                    Severity.ERROR,
                    f"{target_id}.story_id",
                    f"Бессмертный квестодатель '{npc_id}' не имеет story_id.",
                    hint="Задайте CustomNpc.story_id: гайд должен быть найден "
                    "скриптом.",
                    owner="npc",
                    npc_id=npc_id,
                )
            if story_id:
                story_owners.setdefault(story_id, []).append(
                    f"NPC '{npc_id}'"
                )

        for squad in squads:
            squad_id = self._normalize(getattr(squad, "id", None))
            if not squad_id:
                continue
            template_squad_id = self._normalize(
                getattr(squad, "template_squad_id", None)
            )
            if template_squad_id and self.resolve_squad(template_squad_id) is None:
                self.report.add(
                    "CAT-CUSTOM-012",
                    Severity.ERROR,
                    f"squad:{squad_id}.template_squad_id",
                    f"template_squad_id '{template_squad_id}' не найден в "
                    "таблице squads БД.",
                    hint="Проверьте ID отряда через main.py search -t squad.",
                    owner="squad",
                    squad_id=squad_id,
                    template_squad_id=template_squad_id,
                )
            story_id = self._normalize(getattr(squad, "story_id", None))
            if story_id:
                story_owners.setdefault(story_id, []).append(
                    f"отряд '{squad_id}'"
                )

        # CAT-CUSTOM-005: story_id уникален и не пересекается с ванилью.
        for story_id, owners in story_owners.items():
            if len(owners) > 1:
                self.report.add(
                    "CAT-CUSTOM-005",
                    Severity.ERROR,
                    f"story_id:{story_id}",
                    f"story_id '{story_id}' дублируется у: "
                    f"{', '.join(sorted(owners))}.",
                    hint="story_id обязан быть уникальным в проекте.",
                    owner="project",
                    story_id=story_id,
                )
            if story_id in vanilla_aliases:
                self.report.add(
                    "CAT-CUSTOM-005",
                    Severity.ERROR,
                    f"story_id:{story_id}",
                    f"story_id '{story_id}' совпадает с ванильным алиасом.",
                    hint="Переименуйте story_id, чтобы не перезаписать ваниль.",
                    owner="project",
                    story_id=story_id,
                )

    # ------------------------------------------------------------------
    # CAT-NPC-001..004, CAT-LOC-001
    # ------------------------------------------------------------------

    def _validate_npcs(self, project: ModProject) -> None:
        """Проверяет ``Quest.npc_id`` и ``Dialog.npc_id``."""
        for quest in (project.quests or {}).values():
            npc_id = quest.npc_id or quest.giver_npc_id
            self._check_npc_ref(
                npc_id,
                quest.npc_location,
                f"quest:{quest.id}.npc_id",
                "quest",
            )
        for dialog in (project.dialogs or {}).values():
            self._check_npc_ref(
                dialog.npc_id,
                dialog.npc_location,
                f"dialog:{dialog.id}.npc_id",
                "dialog",
            )

    def _check_npc_ref(
        self,
        npc_id: str | None,
        location: str | None,
        target_id: str,
        owner: str,
    ) -> None:
        """Проверяет один NPC-профиль и его локацию."""
        name = self._normalize(npc_id)
        if not name:
            return
        # Кастомный NPC живёт в файлах мода, а не в ванильном
        # character_desc_<level>.xml, поэтому CAT-NPC-001/002 к нему не
        # применяются.
        if name in self._custom_npc_aliases():
            return

        rows = self._npc_index().get(name, [])
        if not rows:
            self.report.add(
                "CAT-NPC-001",
                Severity.ERROR,
                target_id,
                f"NPC-профиль '{name}' не найден среди specific_character.",
                hint=(
                    "Укажите существующий <specific_character id> из "
                    "character_desc_*.xml; проверьте написание ID."
                ),
                owner=owner,
                npc_id=name,
            )
        elif len(rows) > 1:
            self.report.add(
                "CAT-NPC-003",
                Severity.ERROR,
                target_id,
                f"NPC-профиль '{name}' найден более одного раза "
                f"({len(rows)} записей).",
                hint="Оставьте ровно один <specific_character> с таким id.",
                owner=owner,
                npc_id=name,
                count=len(rows),
            )

        location_value = self._normalize(location)
        if not location_value:
            self.report.add(
                "CAT-NPC-002",
                Severity.ERROR,
                target_id,
                f"Для NPC '{name}' не задан npc_location.",
                hint=(
                    "Укажите локацию профиля (escape, zaton, jupiter, ...), "
                    "чтобы патчер выбрал правильный character_desc_*.xml."
                ),
                owner=owner,
                npc_id=name,
            )
        elif rows and not self._location_matches(rows[0], location_value):
            self.report.add(
                "CAT-NPC-004",
                Severity.WARNING,
                target_id,
                f"Локация '{location_value}' не соответствует профилю "
                f"NPC '{name}'.",
                hint=(
                    "Сверьте npc_location с location_prefix/source_file "
                    "выбранного specific_character."
                ),
                owner=owner,
                npc_id=name,
                npc_location=location_value,
            )

    # ------------------------------------------------------------------
    # CAT-SMART-001..003
    # ------------------------------------------------------------------

    def _validate_smarts(self, project: ModProject) -> None:
        """Проверяет смарты, цели этапов и точки спавна отрядов."""
        for squad in (project.squads or {}).values():
            if squad.target_smart:
                self._check_smart(
                    squad.target_smart,
                    f"squad:{squad.id}.target_smart",
                    "squad",
                )

        for quest in (project.quests or {}).values():
            giver_smarts = self._giver_smart_ids(quest)
            for stage in (quest.stages or {}).values():
                if stage.target_alias:
                    self._check_target_alias(
                        stage.target_alias,
                        f"quest:{quest.id}.stage:{stage.id}.target_alias",
                        quest,
                    )
                for index, variant in enumerate(
                    stage.target_variants or []
                ):
                    self._check_target_alias(
                        variant.value,
                        f"quest:{quest.id}.stage:{stage.id}"
                        f".target_variants[{index}].value",
                        quest,
                    )
                if stage.warfare_capture is not None:
                    self._check_smart(
                        stage.warfare_capture.smart_alias,
                        f"quest:{quest.id}.stage:{stage.id}"
                        ".warfare_capture.smart_alias",
                        "stage",
                    )

            for context in self._iter_actions_for_quest(project, quest):
                action = context.action
                if isinstance(action, SpawnSquad):
                    self._check_smart(
                        action.smart_alias,
                        f"{context.owner}.smart_alias",
                        "quest",
                    )
                    smart_name = self._normalize(action.smart_alias)
                    if smart_name and smart_name in giver_smarts:
                        self.report.add(
                            "CAT-SMART-003",
                            Severity.ERROR,
                            f"{context.owner}.smart_alias",
                            f"Отряд спавнится на смарте квестодателя "
                            f"'{smart_name}'.",
                            hint=(
                                "Выберите отдельную точку спавна: враг не "
                                "должен появляться в лагере квестодателя."
                            ),
                            owner="quest",
                            smart_alias=smart_name,
                            quest_id=quest.id,
                        )
                elif isinstance(action, SetTarget):
                    self._check_smart(
                        action.smart_alias,
                        f"{context.owner}.smart_alias",
                        "quest",
                    )

        for target_id, _quest, condition in self._iter_conditions(project):
            if isinstance(condition, SmartOwner):
                self._check_smart(
                    condition.smart_alias,
                    f"{target_id}.smart_alias",
                    "condition",
                )

    def _iter_actions_for_quest(
        self, project: ModProject, quest: Quest
    ) -> Iterator[_ActionContext]:
        """Перебирает действия, относящиеся к конкретному квесту."""
        for context in self._iter_actions(project):
            if context.quest is quest:
                yield context

    def _giver_smart_ids(self, quest: Quest) -> set[str]:
        """Выводит вероятные смарты квестодателя из ID его NPC-профиля.

        База не хранит прямую связь ``specific_character -> smart``. Поэтому
        используются устойчивые шаблоны ID: ``esc_2_12_stalker_wolf`` даёт
        ``esc_smart_terrain_2_12``, ``zat_b7_bandit_boss_sultan`` — ``zat_b7``.
        """
        npc_id = self._normalize(quest.npc_id or quest.giver_npc_id)
        if not npc_id:
            return set()
        row = self.resolve_npc(npc_id, quest.npc_location)
        parts = npc_id.split("_")
        if len(parts) < 2:
            return set()
        location = (
            self._normalize(row.get("location_prefix"))
            if row is not None
            else ""
        )
        if not location:
            location = parts[0]
        candidates: set[str] = set()
        for length in range(1, len(parts)):
            coord = "_".join(parts[1 : 1 + length])
            if not coord:
                continue
            candidates.add(f"{location}_{coord}")
            candidates.add(f"{location}_smart_terrain_{coord}")
        return candidates

    def _check_target_alias(
        self, value: str | None, target_id: str, quest: Quest | None
    ) -> None:
        """Проверяет алиас цели этапа (смарт, уникальный NPC или предмет)."""
        name = self._normalize(value)
        if not name:
            return
        if self._find_custom_npc(name) is not None:
            return
        smart = self.resolve_smart(name)
        if smart is not None:
            if quest is not None and quest.npc_location:
                prefix = self._normalize(smart.get("location_prefix"))
                if not self._location_matches_prefix(
                    quest.npc_location, prefix
                ):
                    self.report.add(
                        "CAT-LOC-001",
                        Severity.WARNING,
                        target_id,
                        f"Локация NPC '{quest.npc_location}' не совпадает "
                        f"с локацией смарта '{name}' ({prefix}).",
                        hint="Сверьте npc_location и location_prefix смарта.",
                        owner="stage",
                        smart_alias=name,
                    )
            return
        if self.resolve_npc(name) is not None:
            return
        if self.resolve_item(name) is not None:
            return
        if self._is_generic_npc_template(name):
            self.report.add(
                "CAT-SMART-002",
                Severity.ERROR,
                target_id,
                f"Цель '{name}' указывает на обычную NPC-секцию, а не на "
                "смарт или story-объект.",
                hint=(
                    "Для маркера используйте смарт, уникальный "
                    "specific_character или предмет."
                ),
                owner="stage",
                target_alias=name,
            )
            return
        self.report.add(
            "CAT-SMART-001",
            Severity.ERROR,
            target_id,
            f"Цель '{name}' не найдена ни как смарт, ни как NPC/предмет.",
            hint="Сверьте алиас с БД смартов, NPC и предметов.",
            owner="stage",
            target_alias=name,
        )

    def _check_smart(
        self, value: str | None, target_id: str, owner: str
    ) -> None:
        """Проверяет, что значение является существующим смартом."""
        name = self._normalize(value)
        if not name:
            return
        if self.resolve_smart(name) is None:
            self.report.add(
                "CAT-SMART-001",
                Severity.ERROR,
                target_id,
                f"Смарт-террейн '{name}' не найден в БД.",
                hint="Укажите существующий smart_alias/smart id.",
                owner=owner,
                smart_alias=name,
            )

    # ------------------------------------------------------------------
    # CAT-ITEM-001
    # ------------------------------------------------------------------

    def _validate_items(self, project: ModProject) -> None:
        """Проверяет все ссылки на предметы."""
        for context in self._iter_actions(project):
            action = context.action
            if isinstance(action, (GiveItem, RemoveItem, TakeItem, SpawnNpcItem)):
                self._check_item(
                    action.item_alias,
                    f"{context.owner}.item_alias",
                    "action",
                )
        for target_id, _quest, condition in self._iter_conditions(project):
            if isinstance(condition, HasItem):
                self._check_item(
                    condition.item_alias,
                    f"{target_id}.item_alias",
                    "condition",
                )
        for quest in (project.quests or {}).values():
            if quest.reward_item_alias:
                self._check_item(
                    quest.reward_item_alias,
                    f"quest:{quest.id}.reward_item_alias",
                    "quest",
                )

    def _check_item(
        self, value: str | None, target_id: str, owner: str
    ) -> None:
        """Проверяет, что предмет существует в БД или алиасах."""
        name = self._normalize(value)
        if not name:
            return
        if self.resolve_item(name) is None:
            self.report.add(
                "CAT-ITEM-001",
                Severity.ERROR,
                target_id,
                f"Предмет '{name}' не найден в БД.",
                hint="Укажите существующую секцию или алиас предмета.",
                owner=owner,
                item_alias=name,
            )

    # ------------------------------------------------------------------
    # CAT-SQUAD-001..006
    # ------------------------------------------------------------------

    def _validate_squads(self, project: ModProject) -> None:
        """Проверяет отряды проекта и все ссылки на них."""
        for squad in (project.squads or {}).values():
            self._validate_custom_squad(project, squad)

        for context in self._iter_actions(project):
            action = context.action
            if isinstance(action, SpawnSquad):
                if not self._squad_exists(project, action.squad_alias):
                    self.report.add(
                        "CAT-SQUAD-001",
                        Severity.ERROR,
                        f"{context.owner}.squad_alias",
                        f"Отряд '{action.squad_alias}' не найден ни в "
                        "project.squads, ни в БД отрядов.",
                        hint=(
                            "Объявите CustomSquad или укажите игровой "
                            "ID/алиас отряда из БД."
                        ),
                        owner="action",
                        squad_alias=self._normalize(action.squad_alias),
                    )
            elif isinstance(action, RemoveSquad):
                self._check_remove_squad(
                    project,
                    action.squad_alias,
                    f"{context.owner}.squad_alias",
                )
            elif isinstance(action, SetTarget):
                if not self._squad_exists(project, action.squad_alias):
                    self.report.add(
                        "CAT-SQUAD-001",
                        Severity.ERROR,
                        f"{context.owner}.squad_alias",
                        f"Отряд '{action.squad_alias}' не найден ни в "
                        "project.squads, ни в БД отрядов.",
                        hint="Сверьте squad_alias с БД отрядов.",
                        owner="action",
                        squad_alias=self._normalize(action.squad_alias),
                    )
            elif isinstance(action, SpawnNpcItem):
                self._check_spawn_npc_item_target(
                    project,
                    action.target_alias,
                    f"{context.owner}.target_alias",
                )

        for quest in (project.quests or {}).values():
            for stage in (quest.stages or {}).values():
                if stage.target_squad_id:
                    self._check_target_squad(
                        project,
                        stage.target_squad_id,
                        f"quest:{quest.id}.stage:{stage.id}.target_squad_id",
                    )

    def _validate_custom_squad(
        self, project: ModProject, squad: CustomSquad
    ) -> None:
        """Проверяет состав и метаданные ``CustomSquad``."""
        templates = [
            self._normalize(value)
            for value in [*(squad.npc or []), *(squad.npc_random or [])]
            if self._normalize(value)
        ]
        owner_target = f"squad:{squad.id}"
        has_custom_npcs = bool(getattr(project, "npcs", None))
        # Пустой состав допустим только при наследовании от ванильного
        # шаблона (CAT-CUSTOM-004, §3.1).
        if not templates and not self._normalize(squad.template_squad_id):
            self.report.add(
                "CAT-CUSTOM-004" if has_custom_npcs else "CAT-SQUAD-003",
                Severity.ERROR,
                f"{owner_target}.npc",
                f"У отряда '{squad.id}' пусты и npc, и npc_random.",
                hint=(
                    "Задайте хотя бы один NPC-шаблон или "
                    "CustomSquad.template_squad_id."
                ),
                owner="squad",
                squad_id=squad.id,
            )

        for index, template in enumerate(templates):
            if self._find_custom_npc(template) is not None:
                continue
            if not self._npc_template_exists(template):
                profile_match = _SPAWN_PROFILE_SUFFIX_RE.match(template)
                if profile_match:
                    message = (
                        f"NPC-секция '{template}' отряда '{squad.id}' — "
                        "XML-профиль specific_character, а не LTX "
                        "spawn-секция."
                    )
                    hint = (
                        f"Укажите LTX spawn-секцию "
                        f"'{profile_match.group('base')}' (без суффикса "
                        "_default_N), иначе движок X-Ray напишет "
                        "'npc section ... does not exist!'."
                    )
                else:
                    message = (
                        f"NPC-секция '{template}' отряда '{squad.id}' "
                        "не найдена."
                    )
                    hint = (
                        "Используйте существующую LTX spawn-секцию NPC "
                        "или CustomNpc.id (например, sim_default_monolith_3)."
                    )
                self.report.add(
                    "CAT-CUSTOM-004" if has_custom_npcs else "CAT-SQUAD-004",
                    Severity.ERROR,
                    f"{owner_target}.template[{index}]",
                    message,
                    hint=hint,
                    owner="squad",
                    squad_id=squad.id,
                    template=template,
                )

        if squad.npc_in_squad:
            if (
                len(squad.npc_in_squad) == 2
                and squad.npc_in_squad[0] > squad.npc_in_squad[1]
            ):
                self.report.add(
                    "CAT-SQUAD-005",
                    Severity.WARNING,
                    f"{owner_target}.npc_in_squad",
                    f"У отряда '{squad.id}' min больше max в npc_in_squad.",
                    hint="Задайте диапазон в порядке min, max.",
                    owner="squad",
                    squad_id=squad.id,
                )
            elif templates and max(squad.npc_in_squad) > len(templates):
                self.report.add(
                    "CAT-SQUAD-005",
                    Severity.WARNING,
                    f"{owner_target}.npc_in_squad",
                    f"У отряда '{squad.id}' npc_in_squad={max(squad.npc_in_squad)} "
                    f"больше числа шаблонов ({len(templates)}).",
                    hint="Согласуйте npc_in_squad с числом NPC-шаблонов.",
                    owner="squad",
                    squad_id=squad.id,
                )

        faction = self._normalize(squad.faction).lower()
        if faction and templates:
            inferred = {
                self._infer_template_faction(template)
                for template in templates
            }
            inferred.discard(None)
            mismatched = {
                value for value in inferred if value and value != faction
            }
            if mismatched:
                self.report.add(
                    "CAT-SQUAD-006",
                    Severity.WARNING,
                    f"{owner_target}.faction",
                    f"Фракция отряда '{squad.id}' ({faction}) не совпадает "
                    f"с фракцией шаблонов: {', '.join(sorted(mismatched))}.",
                    hint="Приведите faction и NPC-шаблоны к одной фракции.",
                    owner="squad",
                    squad_id=squad.id,
                    faction=faction,
                )

    def _npc_template_exists(self, template: str) -> bool:
        """``True`` только для реальной LTX spawn-секции NPC.

        XML-профили ``<specific_character id="..._default_N">`` не являются
        spawn-секциями: движок X-Ray не находит их в ``spawn_sections`` и
        пишет ``!ERROR: npc section ... does not exist!``. Поэтому такой ID
        принимается только при наличии одноимённой LTX-секции в БД.
        """
        name = self._normalize(template)
        if not name:
            return False
        sections = self._npc_spawn_section_names()
        if name in sections:
            return True
        row = self.resolve_npc(name)
        if row is not None:
            entity_id = self._normalize(row.get("id"))
            if entity_id in sections:
                return True
        return False

    def _infer_template_faction(self, template: str) -> str | None:
        """Выводит фракцию NPC-шаблона по его ID, если это возможно."""
        row = self.resolve_npc(template)
        if row is not None:
            faction = self._normalize(row.get("faction")).lower()
            if faction:
                return faction
        match = re.match(
            r"^sim_default_([a-z]+)", template.strip(), re.IGNORECASE
        )
        if not match:
            return None
        token = match.group(1).lower()
        faction = _TEMPLATE_FACTION_ALIASES.get(token, token)
        if faction in self._valid_factions():
            return faction
        return None

    def _check_remove_squad(
        self, project: ModProject, alias: str | None, target_id: str
    ) -> None:
        """Проверяет ``RemoveSquad.squad_alias``."""
        name = self._normalize(alias)
        if not name:
            return
        squad = self._find_project_squad(project, name)
        if squad is not None:
            if not self._normalize(squad.story_id):
                self.report.add(
                    "CAT-SQUAD-002",
                    Severity.ERROR,
                    target_id,
                    f"RemoveSquad адресует отряд '{squad.id}' без story_id.",
                    hint=(
                        "Задайте CustomSquad.story_id: RemoveSquad резолвит "
                        "отряд через get_story_squad(alias)."
                    ),
                    owner="squad",
                    squad_id=squad.id,
                )
            return
        if self.resolve_squad(name) is not None:
            return
        self.report.add(
            "CAT-SQUAD-001",
            Severity.ERROR,
            target_id,
            f"RemoveSquad ссылается на отсутствующий отряд '{name}'.",
            hint="Объявите CustomSquad или укажите отряд из БД.",
            owner="action",
            squad_alias=name,
        )

    def _check_spawn_npc_item_target(
        self, project: ModProject, alias: str | None, target_id: str
    ) -> None:
        """Проверяет ``SpawnNpcItem.target_alias``."""
        name = self._normalize(alias)
        if not name:
            return
        squad = self._find_project_squad(project, name)
        if squad is not None:
            if not self._normalize(squad.story_id):
                self.report.add(
                    "CAT-SQUAD-002",
                    Severity.ERROR,
                    target_id,
                    f"SpawnNpcItem адресует отряд '{squad.id}' без story_id.",
                    hint=(
                        "Задайте CustomSquad.story_id, иначе командир отряда "
                        "не будет найден."
                    ),
                    owner="squad",
                    squad_id=squad.id,
                )
            return
        if name.isdigit():
            return
        if self.resolve_npc(name) is not None:
            return
        if self._is_generic_npc_template(name):
            self.report.add(
                "CAT-SQUAD-001",
                Severity.ERROR,
                target_id,
                f"SpawnNpcItem.target_alias '{name}' — NPC-секция, а не "
                "story-отряд или NPC story-ID.",
                hint="Укажите story_id/NPC story-ID или числовой server ID.",
                owner="action",
                target_alias=name,
            )
            return
        if self.resolve_squad(name) is not None:
            return
        self.report.add(
            "CAT-SQUAD-001",
            Severity.ERROR,
            target_id,
            f"SpawnNpcItem.target_alias '{name}' не найден.",
            hint="Укажите story_id/NPC story-ID или числовой server ID.",
            owner="action",
            target_alias=name,
        )

    def _check_target_squad(
        self, project: ModProject, alias: str | None, target_id: str
    ) -> None:
        """Проверяет ``Stage.target_squad_id``."""
        name = self._normalize(alias)
        if not name:
            return
        squad = self._find_project_squad(project, name)
        if squad is not None:
            if not self._normalize(squad.story_id):
                self.report.add(
                    "CAT-SQUAD-002",
                    Severity.ERROR,
                    target_id,
                    f"Stage.target_squad_id адресует отряд '{squad.id}' "
                    "без story_id.",
                    hint="Задайте CustomSquad.story_id для story-отряда.",
                    owner="squad",
                    squad_id=squad.id,
                )
            return
        if self.resolve_squad(name) is not None:
            return
        if name.isdigit():
            return
        self.report.add(
            "CAT-SQUAD-001",
            Severity.ERROR,
            target_id,
            f"Stage.target_squad_id ссылается на отсутствующий отряд "
            f"'{name}'.",
            hint="Укажите story_id отряда проекта или отряд из БД.",
            owner="stage",
            target_squad_id=name,
        )

    # ------------------------------------------------------------------
    # CAT-WARFARE-001..003
    # ------------------------------------------------------------------

    def _validate_warfare(self, project: ModProject) -> None:
        """Проверяет отряды в ``WarfareCapture`` и warfare-спавн."""
        for quest in (project.quests or {}).values():
            for stage in (quest.stages or {}).values():
                capture: WarfareCapture | None = stage.warfare_capture
                if capture is None:
                    continue
                enemy = self._normalize(capture.enemy_squad_alias)
                if not enemy or not self._squad_exists(project, enemy):
                    self.report.add(
                        "CAT-WARFARE-001",
                        Severity.ERROR,
                        f"quest:{quest.id}.stage:{stage.id}"
                        ".warfare_capture.enemy_squad_alias",
                        f"Вражеский алиас '{enemy}' не является отрядом.",
                        hint=(
                            "WarfareCapture ожидает ID/алиас отряда, а не "
                            "NPC-секцию."
                        ),
                        owner="stage",
                        enemy_squad_alias=enemy,
                    )

                ally = self._normalize(capture.ally_squad_alias)
                if ally:
                    if not self._squad_exists(project, ally):
                        self.report.add(
                            "CAT-WARFARE-002",
                            Severity.ERROR,
                            f"quest:{quest.id}.stage:{stage.id}"
                            ".warfare_capture.ally_squad_alias",
                            f"Союзный алиас '{ally}' не является отрядом.",
                            hint=(
                                "ally_squad_alias ожидает ID/алиас отряда, "
                                "а не NPC-секцию."
                            ),
                            owner="stage",
                            ally_squad_alias=ally,
                        )
                elif capture.ally_count > 0:
                    self.report.add(
                        "CAT-WARFARE-002",
                        Severity.ERROR,
                        f"quest:{quest.id}.stage:{stage.id}"
                        ".warfare_capture.ally_count",
                        "ally_count > 0, но ally_squad_alias не задан.",
                        hint="Задайте ally_squad_alias или ally_count=0.",
                        owner="stage",
                        ally_count=capture.ally_count,
                    )

        for context in self._iter_actions(project):
            action = context.action
            if not isinstance(action, SpawnSquad):
                continue
            if getattr(action, "mode", "warfare") != "warfare":
                continue
            if not self._squad_exists(project, action.squad_alias):
                self.report.add(
                    "CAT-WARFARE-003",
                    Severity.ERROR,
                    f"{context.owner}.squad_alias",
                    f"SpawnSquad(mode='warfare') ссылается на отсутствующий "
                    f"отряд '{action.squad_alias}'.",
                    hint="Укажите игровой ID/алиас отряда из БД.",
                    owner="action",
                    squad_alias=self._normalize(action.squad_alias),
                )

    # ------------------------------------------------------------------
    # CAT-FACTION-001
    # ------------------------------------------------------------------

    def _validate_factions(self, project: ModProject) -> None:
        """Проверяет технические имена фракций."""
        for quest in (project.quests or {}).values():
            if quest.requires_faction:
                self._check_faction(
                    quest.requires_faction,
                    f"quest:{quest.id}.requires_faction",
                    "quest",
                )
        for squad in (project.squads or {}).values():
            if squad.faction:
                self._check_faction(
                    squad.faction,
                    f"squad:{squad.id}.faction",
                    "squad",
                )
        for target_id, _quest, condition in self._iter_conditions(project):
            if isinstance(condition, SmartOwner):
                self._check_faction(
                    condition.faction,
                    f"{target_id}.faction",
                    "condition",
                )

    def _check_faction(
        self, value: str | None, target_id: str, owner: str
    ) -> None:
        """Проверяет известность фракции."""
        name = self._normalize(value)
        if not name:
            return
        if self.resolve_faction(name) is None:
            self.report.add(
                "CAT-FACTION-001",
                Severity.WARNING,
                target_id,
                f"Неизвестная фракция '{name}'.",
                hint=(
                    "Используйте техническое имя: army, bandit, killer, "
                    "freedom, dolg, stalker, ..."
                ),
                owner=owner,
                faction=name,
            )

    # ------------------------------------------------------------------
    # CAT-DIALOG-001
    # ------------------------------------------------------------------

    def _validate_dialogs(self, project: ModProject) -> None:
        """Проверяет перекрёстные ссылки ``Quest`` и ``Dialog``."""
        dialog_ids = set((project.dialogs or {}).keys())
        dialog_ids.update(
            self._normalize(dialog.id)
            for dialog in (project.dialogs or {}).values()
        )
        quest_ids = set((project.quests or {}).keys())
        quest_ids.update(
            self._normalize(quest.id)
            for quest in (project.quests or {}).values()
        )

        for quest in (project.quests or {}).values():
            references = list(quest.dialog_ids or [])
            if quest.dialog_id:
                references.append(quest.dialog_id)
            for reference in references:
                name = self._normalize(reference)
                if name and name not in dialog_ids:
                    self.report.add(
                        "CAT-DIALOG-001",
                        Severity.ERROR,
                        f"quest:{quest.id}.dialog_id",
                        f"Квест '{quest.id}' ссылается на отсутствующий "
                        f"диалог '{name}'.",
                        hint="Добавьте диалог в project.dialogs.",
                        owner="quest",
                        dialog_id=name,
                    )

        for dialog in (project.dialogs or {}).values():
            name = self._normalize(dialog.task_id)
            if name and name not in quest_ids:
                self.report.add(
                    "CAT-DIALOG-001",
                    Severity.ERROR,
                    f"dialog:{dialog.id}.task_id",
                    f"Диалог '{dialog.id}' ссылается на отсутствующий "
                    f"квест '{name}'.",
                    hint="Добавьте квест в project.quests.",
                    owner="dialog",
                    task_id=name,
                )


__all__ = ["CatalogValidator"]
