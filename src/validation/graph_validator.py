"""Графовый кросс-валидатор связей PK/FK квестового проекта.

Модуль реализует контракт ``docs/VALIDATION_SPEC.md`` (§4.4): собирает
индекс сущностей и рёбер проекта, проверяет достижимость, циклы, завершение
этапов, награды, очистку предметов и целостность ссылок.

Индекс :class:`GraphIndex` не является обязательным артефактом сборки, но
служит готовым источником данных для отрисовки графа в GUI: узлы содержат
``id``/``type``/``label``, рёбра — ``source``/``target``/``kind``/``owner``/
``label``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from src.core.models import (
    CompleteTask,
    DontHasInfo,
    GiveInfo,
    GiveItem,
    GiveMoney,
    GiveTask,
    HasInfo,
    HasItem,
    HasMoney,
    ModProject,
    RemoveInfo,
    RemoveItem,
    RemoveSquad,
    SpawnNpcItem,
    SpawnSquad,
    TakeItem,
    TakeMoney,
)
from src.validation.report import Severity, ValidationReport

#: Допустимые типы узлов графа (контракт §4.4).
NODE_TYPES = frozenset({"quest", "dialog", "phrase", "stage", "squad"})


class GraphIndex:
    """Индекс узлов и направленных рёбер проекта.

    Attributes:
        nodes: Список словарей ``{"id", "type", "label"}``.
        edges: Список словарей ``{"source", "target", "kind", "owner",
            "label"}``.
    """

    def __init__(self) -> None:
        self.nodes: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []
        self._node_ids: set[str] = set()
        self._edge_keys: set[tuple[str, str, str, str, str]] = set()

    def add_node(self, node_id: str, node_type: str, label: str = "") -> None:
        """Добавляет узел, если узла с таким ``id`` ещё нет."""
        if not node_id or node_id in self._node_ids:
            return
        if node_type not in NODE_TYPES:
            node_type = "quest"
        self._node_ids.add(node_id)
        self.nodes.append(
            {"id": str(node_id), "type": node_type, "label": str(label or "")}
        )

    def add_edge(
        self,
        source: str,
        target: str,
        kind: str,
        owner: str = "",
        label: str = "",
    ) -> None:
        """Добавляет направленное ребро без дублей."""
        if not source or not target:
            return
        key = (str(source), str(target), str(kind), str(owner), str(label))
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self.edges.append(
            {
                "source": key[0],
                "target": key[1],
                "kind": key[2],
                "owner": key[3],
                "label": key[4],
            }
        )

    def to_dict(self) -> dict[str, Any]:
        """Возвращает детерминированное JSON-совместимое представление."""
        nodes = sorted(
            (dict(node) for node in self.nodes),
            key=lambda node: (str(node["type"]), str(node["id"])),
        )
        edges = sorted(
            (dict(edge) for edge in self.edges),
            key=lambda edge: (
                str(edge["source"]),
                str(edge["target"]),
                str(edge["kind"]),
                str(edge["owner"]),
                str(edge["label"]),
            ),
        )
        return {"nodes": nodes, "edges": edges}

    def export_edges(self, path: Path | None = None) -> dict[str, Any]:
        """Возвращает граф и при необходимости пишет его в JSON-файл.

        Args:
            path: Необязательный путь к JSON-файлу. Родительские каталоги
                создаются автоматически.

        Returns:
            dict[str, Any]: Структура ``{"nodes": [...], "edges": [...]}``.
        """
        data = self.to_dict()
        if path is not None:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
        return data


class GraphValidator:
    """Проверяет логический граф квестов, диалогов и этапов.

    Args:
        report: Накопительный отчёт, в который добавляются замечания.
        external_infos: Дополнительный allowlist внешних инфопоршней, которые
            выдаются вне проекта. Обычно достаточно ``Quest.available_info``.
    """

    def __init__(
        self,
        report: ValidationReport,
        *,
        external_infos: Iterable[str] | None = None,
    ) -> None:
        self.report = report
        self.external_infos = set(external_infos or ())
        self.index = GraphIndex()
        self.project: ModProject | None = None
        self.quests: dict[str, Any] = {}
        self.dialogs: dict[str, Any] = {}
        self.squads: dict[str, Any] = {}
        self.dialog_quests: dict[str, list[str]] = {}
        self.quest_dialogs: dict[str, list[Any]] = {}
        self.info_sources: dict[str, list[tuple[str, str, str | None]]] = {}
        self.info_reads: dict[str, set[str]] = {}
        self.item_sources: dict[str, list[tuple[str, str, str | None]]] = {}
        self.item_checks: dict[str, set[str]] = {}
        self.death_info_squads: dict[str, set[str]] = {}
        self.spawned_squads: dict[str, set[str]] = {}
        self.completion_phrases: dict[str, list[tuple[Any, Any]]] = {}

    # ------------------------------------------------------------------
    # Публичная точка входа
    # ------------------------------------------------------------------

    def validate(self, project: ModProject) -> GraphIndex:
        """Строит индекс и выполняет все проверки ``GRAPH-*``."""
        self.project = project
        self.quests = dict(getattr(project, "quests", {}) or {})
        self.dialogs = dict(getattr(project, "dialogs", {}) or {})
        self.squads = dict(getattr(project, "squads", {}) or {})

        self.index = GraphIndex()
        self._build_context()
        self._collect_all()
        self._build_index()

        self._check_info()
        self._check_contradictions()
        self._check_items_and_money()
        self._check_root_preconditions()
        self._check_quests()
        self._check_stages()
        self._check_edges()
        self._check_rewards()
        self._check_cleanup()
        self._check_death_refs()
        self._check_phrase_cycles()
        return self.index

    # ------------------------------------------------------------------
    # Контекст и сбор данных
    # ------------------------------------------------------------------

    def _build_context(self) -> None:
        """Строит карты связей quest ↔ dialog."""
        self.dialog_quests = defaultdict(list)
        self.quest_dialogs = defaultdict(list)

        for quest in self.quests.values():
            dialog_ids = [getattr(quest, "dialog_id", None)]
            dialog_ids.extend(getattr(quest, "dialog_ids", []) or [])
            for dialog_id in dialog_ids:
                if not dialog_id or dialog_id not in self.dialogs:
                    continue
                if dialog_id not in self.dialog_quests:
                    self.dialog_quests[dialog_id] = []
                if quest.id not in self.dialog_quests[dialog_id]:
                    self.dialog_quests[dialog_id].append(quest.id)
                if quest.id not in self.quest_dialogs:
                    self.quest_dialogs[quest.id] = []
                if dialog_id not in {
                    d.id for d in self.quest_dialogs[quest.id]
                }:
                    self.quest_dialogs[quest.id].append(
                        self.dialogs[dialog_id]
                    )

        for dialog in self.dialogs.values():
            task_id = getattr(dialog, "task_id", None)
            if task_id and task_id in self.quests:
                if dialog.id not in self.dialog_quests:
                    self.dialog_quests[dialog.id] = []
                if task_id not in self.dialog_quests[dialog.id]:
                    self.dialog_quests[dialog.id].append(task_id)
                if task_id not in self.quest_dialogs:
                    self.quest_dialogs[task_id] = []
                if dialog.id not in {
                    d.id for d in self.quest_dialogs[task_id]
                }:
                    self.quest_dialogs[task_id].append(dialog)

    @staticmethod
    def _add_list(
        mapping: dict[str, list[tuple[str, str, str | None]]],
        key: str,
        value: tuple[str, str, str | None],
    ) -> None:
        mapping.setdefault(key, []).append(value)

    @staticmethod
    def _add_set(mapping: dict[str, set[str]], key: str, value: str) -> None:
        mapping.setdefault(key, set()).add(value)

    def _iter_actions(self):
        """Yield ``(action, quest_id, owner, dialog, phrase, stage)``."""
        for quest in self.quests.values():
            owner = f"quest:{quest.id}"
            for action in getattr(quest, "on_init_actions", []) or []:
                yield action, quest.id, owner, None, None, None
            for action in getattr(quest, "on_complete_actions", []) or []:
                yield action, quest.id, owner, None, None, None
            for action in getattr(quest, "on_fail_actions", []) or []:
                yield action, quest.id, owner, None, None, None
            for stage_id, stage in (quest.stages or {}).items():
                stage_owner = f"stage:{quest.id}:{stage_id}"
                for action in getattr(stage, "on_start_actions", []) or []:
                    yield action, quest.id, stage_owner, None, None, stage

        for dialog in self.dialogs.values():
            quest_ids = self.dialog_quests.get(dialog.id, [])
            task_id = getattr(dialog, "task_id", None)
            if task_id in self.quests:
                quest_id = task_id
            elif quest_ids:
                quest_id = quest_ids[0]
            else:
                quest_id = None
            for phrase_id, phrase in (dialog.phrases or {}).items():
                phrase_owner = f"phrase:{dialog.id}:{phrase_id}"
                for action in getattr(phrase, "actions", []) or []:
                    yield action, quest_id, phrase_owner, dialog, phrase, None

    def _iter_condition_groups(self):
        """Yield ``(quest_id, owner, conditions)`` для каждой конъюнкции."""
        for dialog in self.dialogs.values():
            quest_ids = self.dialog_quests.get(dialog.id, [])
            task_id = getattr(dialog, "task_id", None)
            quest_id = (
                task_id
                if task_id in self.quests
                else (quest_ids[0] if quest_ids else None)
            )
            if getattr(dialog, "preconditions", None):
                yield (
                    quest_id,
                    f"dialog:{dialog.id}",
                    list(dialog.preconditions),
                )
            for phrase_id, phrase in (dialog.phrases or {}).items():
                if getattr(phrase, "preconditions", None):
                    yield (
                        quest_id,
                        f"phrase:{dialog.id}:{phrase_id}",
                        list(phrase.preconditions),
                    )

        for quest in self.quests.values():
            for index, condlist in enumerate(
                getattr(quest, "extra_condlists", []) or []
            ):
                when = getattr(condlist, "when", []) or []
                if when:
                    yield (
                        quest.id,
                        f"quest:{quest.id}:extra_condlists[{index}]",
                        list(when),
                    )
            for stage_id, stage in (quest.stages or {}).items():
                for index, variant in enumerate(
                    getattr(stage, "target_variants", []) or []
                ):
                    when = getattr(variant, "when", []) or []
                    if when:
                        yield (
                            quest.id,
                            f"stage:{quest.id}:{stage_id}:target[{index}]",
                            list(when),
                        )
                for index, variant in enumerate(
                    getattr(stage, "descr_variants", []) or []
                ):
                    when = getattr(variant, "when", []) or []
                    if when:
                        yield (
                            quest.id,
                            f"stage:{quest.id}:{stage_id}:descr[{index}]",
                            list(when),
                        )
            for stage_id, rules in (
                getattr(quest, "transfer_conditions", {}) or {}
            ).items():
                if not isinstance(rules, dict):
                    continue
                for result, conditions in rules.items():
                    if conditions:
                        yield (
                            quest.id,
                            f"stage:{quest.id}:{stage_id}:transfer[{result}]",
                            list(conditions),
                        )

    def _iter_conditions(self):
        """Yield ``(quest_id, owner, condition)``."""
        for quest_id, owner, conditions in self._iter_condition_groups():
            for condition in conditions:
                yield quest_id, owner, condition

    def _collect_all(self) -> None:
        """Собирает источники/потребители info, item, squad и т.п."""
        self.info_sources = defaultdict(list)
        self.info_reads = defaultdict(set)
        self.item_sources = defaultdict(list)
        self.item_checks = defaultdict(set)
        self.death_info_squads = defaultdict(set)
        self.spawned_squads = defaultdict(set)
        self.completion_phrases = defaultdict(list)

        for quest in self.quests.values():
            owner = f"quest:{quest.id}"
            for kind, info in (
                ("taken_info", getattr(quest, "taken_info", None)),
                ("complete_info", getattr(quest, "complete_info", None)),
                ("done_info", getattr(quest, "done_info", None)),
            ):
                if info:
                    self._add_list(
                        self.info_sources, info, (kind, owner, quest.id)
                    )
            if getattr(quest, "reward_item_alias", None):
                self._add_list(
                    self.item_sources,
                    quest.reward_item_alias,
                    ("reward_item_alias", owner, quest.id),
                )

        for squad in self.squads.values():
            owner = f"squad:{squad.id}"
            for info in getattr(squad, "death_infos", []) or []:
                self._add_list(
                    self.info_sources, info, ("death_infos", owner, None)
                )
                self.death_info_squads[info].add(squad.id)

        for action, quest_id, owner, _dialog, _phrase, _stage in (
            self._iter_actions()
        ):
            if isinstance(action, GiveInfo):
                self._add_list(
                    self.info_sources,
                    action.info,
                    ("GiveInfo", owner, quest_id),
                )
            elif isinstance(action, RemoveInfo):
                self._add_set(self.info_reads, action.info, owner)
            elif isinstance(action, (GiveItem, SpawnNpcItem)):
                self._add_list(
                    self.item_sources,
                    action.item_alias,
                    (type(action).__name__, owner, quest_id),
                )
            elif isinstance(action, SpawnSquad):
                aliases = {action.squad_alias}
                for squad_id, squad in self.squads.items():
                    if (
                        squad_id == action.squad_alias
                        or getattr(squad, "story_id", None)
                        == action.squad_alias
                    ):
                        aliases.add(squad_id)
                if quest_id:
                    self.spawned_squads[quest_id].update(aliases)

        for quest_id, owner, condition in self._iter_conditions():
            if isinstance(condition, (HasInfo, DontHasInfo)):
                self._add_set(self.info_reads, condition.info, owner)
            elif isinstance(condition, HasItem):
                if quest_id:
                    self.item_checks[quest_id].add(condition.item_alias)

        for quest in self.quests.values():
            for info in getattr(quest, "cleanup_infos", []) or []:
                self._add_set(
                    self.info_reads, info, f"quest:{quest.id}:cleanup_infos"
                )

            for dialog in self.quest_dialogs.get(quest.id, []):
                for phrase_id, phrase in (dialog.phrases or {}).items():
                    for action in getattr(phrase, "actions", []) or []:
                        if (
                            isinstance(action, CompleteTask)
                            and action.task_id in self.quests
                        ):
                            self.completion_phrases[action.task_id].append(
                                (dialog, phrase)
                            )
                            break

    # ------------------------------------------------------------------
    # Построение индекса
    # ------------------------------------------------------------------

    def _index_condition(self, condition: Any, source: str, owner: str) -> None:
        if isinstance(condition, (HasInfo, DontHasInfo)):
            target = condition.info
        elif isinstance(condition, HasItem):
            target = condition.item_alias
        elif isinstance(condition, HasMoney):
            target = f"money:{condition.amount}"
        else:
            target = getattr(condition, "smart_alias", "") or ""
        self.index.add_edge(
            source,
            target,
            type(condition).__name__,
            owner,
            target,
        )

    def _index_action(self, action: Any, source: str, owner: str) -> None:
        if isinstance(action, (GiveInfo, RemoveInfo)):
            target = action.info
        elif isinstance(action, (GiveItem, RemoveItem, TakeItem, SpawnNpcItem)):
            target = action.item_alias
        elif isinstance(action, GiveMoney):
            target = f"money:{action.amount}"
        elif isinstance(action, TakeMoney):
            target = f"money:{action.amount}"
        elif isinstance(action, (GiveTask, CompleteTask)):
            target = action.task_id
        else:
            target = getattr(action, "squad_alias", "") or ""
        self.index.add_edge(
            source, target, type(action).__name__, owner, target
        )

    def _build_index(self) -> None:
        """Заполняет :class:`GraphIndex` узлами и рёбрами."""
        for quest in self.quests.values():
            self.index.add_node(
                quest.id,
                "quest",
                getattr(quest, "title_ru", "")
                or getattr(quest, "title_en", "")
                or quest.id,
            )
            owner = f"quest:{quest.id}"
            for stage_id, stage in (quest.stages or {}).items():
                stage_node = f"{quest.id}:stage:{stage_id}"
                self.index.add_node(
                    stage_node,
                    "stage",
                    getattr(stage, "title_ru", "")
                    or getattr(stage, "title_en", "")
                    or f"{quest.id} stage {stage_id}",
                )
                self.index.add_edge(quest.id, stage_node, "stage", owner)
                if getattr(stage, "target_squad_id", None):
                    self.index.add_edge(
                        stage_node,
                        stage.target_squad_id,
                        "target_squad_id",
                        f"stage:{quest.id}:{stage_id}",
                        stage.target_squad_id,
                    )
                capture = getattr(stage, "warfare_capture", None)
                if capture is not None:
                    self.index.add_edge(
                        stage_node,
                        capture.enemy_squad_alias,
                        "warfare_capture",
                        f"stage:{quest.id}:{stage_id}",
                        "enemy",
                    )
                    if capture.ally_squad_alias:
                        self.index.add_edge(
                            stage_node,
                            capture.ally_squad_alias,
                            "warfare_capture",
                            f"stage:{quest.id}:{stage_id}",
                            "ally",
                        )
                for action in getattr(stage, "on_start_actions", []) or []:
                    self._index_action(
                        action, stage_node, f"stage:{quest.id}:{stage_id}"
                    )
                for variant in getattr(stage, "target_variants", []) or []:
                    for condition in getattr(variant, "when", []) or []:
                        self._index_condition(
                            condition,
                            stage_node,
                            f"stage:{quest.id}:{stage_id}",
                        )

            for kind, info in (
                ("taken_info", getattr(quest, "taken_info", None)),
                ("complete_info", getattr(quest, "complete_info", None)),
                ("done_info", getattr(quest, "done_info", None)),
                ("available_info", getattr(quest, "available_info", None)),
            ):
                if info:
                    self.index.add_edge(quest.id, info, kind, owner, info)
            for info in getattr(quest, "cleanup_infos", []) or []:
                self.index.add_edge(
                    quest.id, info, "cleanup_infos", owner, info
                )
            for action in getattr(quest, "on_init_actions", []) or []:
                self._index_action(action, quest.id, owner)
            for action in getattr(quest, "on_complete_actions", []) or []:
                self._index_action(action, quest.id, owner)
            for action in getattr(quest, "on_fail_actions", []) or []:
                self._index_action(action, quest.id, owner)
            for stage_id, rules in (
                getattr(quest, "transfer_conditions", {}) or {}
            ).items():
                if not isinstance(rules, dict):
                    continue
                if stage_id not in (quest.stages or {}):
                    target = quest.id
                elif stage_id + 1 in (quest.stages or {}):
                    target = f"{quest.id}:stage:{stage_id + 1}"
                else:
                    target = quest.id
                for result, conditions in rules.items():
                    self.index.add_edge(
                        f"{quest.id}:stage:{stage_id}",
                        target,
                        "transfer_conditions",
                        f"stage:{quest.id}:{stage_id}",
                        result,
                    )
                    for condition in conditions or []:
                        self._index_condition(
                            condition,
                            f"{quest.id}:stage:{stage_id}",
                            f"stage:{quest.id}:{stage_id}",
                        )
            if getattr(quest, "return_to_giver_stage", None) is not None:
                target = f"{quest.id}:stage:{quest.return_to_giver_stage}"
                self.index.add_edge(
                    quest.id, target, "return_to_giver_stage", owner, target
                )
            for index, condlist in enumerate(
                getattr(quest, "extra_condlists", []) or []
            ):
                for condition in getattr(condlist, "when", []) or []:
                    self._index_condition(
                        condition,
                        quest.id,
                        f"quest:{quest.id}:extra_condlists[{index}]",
                    )
            if getattr(quest, "reward_item_alias", None):
                self.index.add_edge(
                    quest.id,
                    quest.reward_item_alias,
                    "reward_item_alias",
                    owner,
                    quest.reward_item_alias,
                )
            if getattr(quest, "reward_money", None) is not None:
                target = f"money:{quest.reward_money}"
                self.index.add_edge(
                    quest.id, target, "reward_money", owner, target
                )
            dialog_ids = [getattr(quest, "dialog_id", None)]
            dialog_ids.extend(getattr(quest, "dialog_ids", []) or [])
            for dialog_id in dialog_ids:
                if dialog_id:
                    self.index.add_edge(
                        quest.id, dialog_id, "dialog_id", owner, dialog_id
                    )

        for squad in self.squads.values():
            self.index.add_node(
                squad.id, "squad", f"squad {squad.id}"
            )
            owner = f"squad:{squad.id}"
            for info in getattr(squad, "death_infos", []) or []:
                self.index.add_edge(
                    squad.id, info, "death_infos", owner, info
                )

        for dialog in self.dialogs.values():
            self.index.add_node(
                dialog.id,
                "dialog",
                getattr(dialog, "npc_alias", "")
                or getattr(dialog, "id", ""),
            )
            owner = f"dialog:{dialog.id}"
            if getattr(dialog, "task_id", None):
                self.index.add_edge(
                    dialog.id, dialog.task_id, "task_id", owner, dialog.task_id
                )
            for condition in getattr(dialog, "preconditions", []) or []:
                self._index_condition(condition, dialog.id, owner)
            for phrase_id, phrase in (dialog.phrases or {}).items():
                phrase_node = f"{dialog.id}:phrase:{phrase_id}"
                self.index.add_node(
                    phrase_node,
                    "phrase",
                    getattr(phrase, "text_ru", "")
                    or getattr(phrase, "text_en", "")
                    or f"{dialog.id}/{phrase_id}",
                )
                phrase_owner = f"phrase:{dialog.id}:{phrase_id}"
                if phrase_id == 0:
                    self.index.add_edge(
                        dialog.id, phrase_node, "start", owner
                    )
                for next_id in getattr(phrase, "next_phrases", []) or []:
                    if next_id in dialog.phrases:
                        self.index.add_edge(
                            phrase_node,
                            f"{dialog.id}:phrase:{next_id}",
                            "next_phrases",
                            phrase_owner,
                            str(next_id),
                        )
                for condition in getattr(phrase, "preconditions", []) or []:
                    self._index_condition(condition, phrase_node, phrase_owner)
                for action in getattr(phrase, "actions", []) or []:
                    self._index_action(action, phrase_node, phrase_owner)

    # ------------------------------------------------------------------
    # GRAPH-INFO-*
    # ------------------------------------------------------------------

    def _allowed_external_infos(self) -> set[str]:
        allowed = set(self.external_infos)
        for quest in self.quests.values():
            if getattr(quest, "available_info", None):
                allowed.add(quest.available_info)
        return allowed

    def _check_info(self) -> None:
        """GRAPH-INFO-001/002/003."""
        allowed = self._allowed_external_infos()

        for _quest_id, owner, condition in self._iter_conditions():
            if isinstance(condition, HasInfo):
                info = condition.info
                if info in self.info_sources or info in allowed:
                    continue
                self.report.add(
                    "GRAPH-INFO-001",
                    Severity.ERROR,
                    owner,
                    f"HasInfo('{info}') требует инфопоршень, который нигде "
                    "не выдаётся в проекте.",
                    hint=(
                        "Добавьте GiveInfo/taken_info/complete_info/"
                        "death_infos или явный внешний allowlist."
                    ),
                    owner=self._owner_kind(owner),
                    info=info,
                )
            elif isinstance(condition, DontHasInfo):
                info = condition.info
                if info in self.info_sources or info in allowed:
                    continue
                self.report.add(
                    "GRAPH-INFO-001",
                    Severity.INFO,
                    owner,
                    f"DontHasInfo('{info}') ссылается на неизвестный "
                    "инфопоршень; он может выдаваться позже или внешне.",
                    hint="Проверьте порядок выдачи поршня или добавьте allowlist.",
                    owner=self._owner_kind(owner),
                    info=info,
                )

        for info, sources in sorted(self.info_sources.items()):
            for kind, owner, _quest_id in sources:
                if kind != "GiveInfo":
                    continue
                if info in self.info_reads or info in allowed:
                    continue
                self.report.add(
                    "GRAPH-INFO-002",
                    Severity.WARNING,
                    owner,
                    f"GiveInfo('{info}') нигде не читается и не снимается.",
                    hint="Удалите мёртвый поршень или добавьте условие/cleanup.",
                    owner="dialog",
                    info=info,
                )

        used_in_condlists: set[str] = set()
        for quest in self.quests.values():
            for condlist in getattr(quest, "extra_condlists", []) or []:
                for condition in getattr(condlist, "when", []) or []:
                    if isinstance(condition, (HasInfo, DontHasInfo)):
                        used_in_condlists.add(condition.info)
            for rules in (
                getattr(quest, "transfer_conditions", {}) or {}
            ).values():
                if not isinstance(rules, dict):
                    continue
                for conditions in rules.values():
                    for condition in conditions or []:
                        if isinstance(condition, (HasInfo, DontHasInfo)):
                            used_in_condlists.add(condition.info)

        for squad in self.squads.values():
            for info in getattr(squad, "death_infos", []) or []:
                if info in used_in_condlists:
                    continue
                self.report.add(
                    "GRAPH-INFO-003",
                    Severity.WARNING,
                    f"squad:{squad.id}",
                    f"death_infos('{info}') не используется ни в "
                    "QuestCondlist, ни в transfer_conditions.",
                    hint="Добавьте условие перехода или удалите поршень.",
                    owner="squad",
                    info=info,
                )

    # ------------------------------------------------------------------
    # GRAPH-CONTRADICTION-001
    # ------------------------------------------------------------------

    def _check_contradictions(self) -> None:
        for _quest_id, owner, conditions in self._iter_condition_groups():
            has = {
                condition.info
                for condition in conditions
                if isinstance(condition, HasInfo)
            }
            dont = {
                condition.info
                for condition in conditions
                if isinstance(condition, DontHasInfo)
            }
            for info in sorted(has & dont):
                self.report.add(
                    "GRAPH-CONTRADICTION-001",
                    Severity.ERROR,
                    owner,
                    f"Одновременно HasInfo('{info}') и DontHasInfo('{info}') "
                    "в одной конъюнкции.",
                    hint="Удалите одно из взаимоисключающих условий.",
                    owner=self._owner_kind(owner),
                    info=info,
                )

    # ------------------------------------------------------------------
    # GRAPH-ITEM-* / GRAPH-MONEY-001
    # ------------------------------------------------------------------

    def _check_items_and_money(self) -> None:
        for dialog in self.dialogs.values():
            dialog_items = {
                condition.item_alias: condition.count
                for condition in getattr(dialog, "preconditions", []) or []
                if isinstance(condition, HasItem)
            }
            dialog_money = [
                condition.amount
                for condition in getattr(dialog, "preconditions", []) or []
                if isinstance(condition, HasMoney)
            ]
            for phrase_id, phrase in (dialog.phrases or {}).items():
                has_items = dict(dialog_items)
                for condition in getattr(phrase, "preconditions", []) or []:
                    if isinstance(condition, HasItem):
                        has_items[condition.item_alias] = max(
                            has_items.get(condition.item_alias, 0),
                            condition.count,
                        )
                has_money = list(dialog_money)
                has_money.extend(
                    condition.amount
                    for condition in getattr(phrase, "preconditions", []) or []
                    if isinstance(condition, HasMoney)
                )
                target = f"{dialog.id}:{phrase_id}"
                for action in getattr(phrase, "actions", []) or []:
                    if isinstance(action, (RemoveItem, TakeItem)):
                        required = has_items.get(action.item_alias)
                        if required is None:
                            self.report.add(
                                "GRAPH-ITEM-001",
                                Severity.WARNING,
                                target,
                                f"{type(action).__name__}("
                                f"'{action.item_alias}') без HasItem в той же "
                                "реплике/диалоге.",
                                hint="Добавьте HasItem(...) или уберите изъятие.",
                                owner="phrase",
                                item=action.item_alias,
                            )
                        elif action.count > required:
                            self.report.add(
                                "GRAPH-ITEM-002",
                                Severity.WARNING,
                                target,
                                f"{type(action).__name__}("
                                f"'{action.item_alias}', count={action.count}) "
                                f"превышает HasItem.count={required}.",
                                hint="Согласуйте количество изымаемых предметов.",
                                owner="phrase",
                                item=action.item_alias,
                            )
                    elif isinstance(action, TakeMoney):
                        if not has_money:
                            self.report.add(
                                "GRAPH-MONEY-001",
                                Severity.WARNING,
                                target,
                                f"TakeMoney({action.amount}) без HasMoney в "
                                "той же реплике/диалоге.",
                                hint="Добавьте HasMoney(...) или уберите списание.",
                                owner="phrase",
                                amount=action.amount,
                            )
                        elif action.amount > max(has_money):
                            self.report.add(
                                "GRAPH-MONEY-001",
                                Severity.WARNING,
                                target,
                                f"TakeMoney({action.amount}) превышает "
                                f"HasMoney({max(has_money)}).",
                                hint="Согласуйте сумму списания и проверки.",
                                owner="phrase",
                                amount=action.amount,
                            )

    # ------------------------------------------------------------------
    # GRAPH-ROOT-001
    # ------------------------------------------------------------------

    def _take_dialogs(self, quest: Any) -> list[Any]:
        result: list[Any] = []
        for dialog in self.quest_dialogs.get(quest.id, []):
            role = (getattr(dialog, "role", "") or "").lower()
            if role.startswith("take"):
                result.append(dialog)
                continue
            if role:
                continue
            if any(
                isinstance(action, GiveTask)
                and action.task_id == quest.id
                for phrase in (dialog.phrases or {}).values()
                for action in getattr(phrase, "actions", []) or []
            ):
                result.append(dialog)
        return result

    def _check_root_preconditions(self) -> None:
        for quest in self.quests.values():
            take_dialogs = self._take_dialogs(quest)
            if not take_dialogs:
                continue

            own_deaths: set[str] = set()
            spawned = self.spawned_squads.get(quest.id, set())
            for info, squad_ids in self.death_info_squads.items():
                for squad_id in squad_ids:
                    squad = self.squads.get(squad_id)
                    aliases = {squad_id}
                    if squad is not None and getattr(squad, "story_id", None):
                        aliases.add(squad.story_id)
                    if aliases & spawned:
                        own_deaths.add(info)

            own_complete = {
                info
                for info in (
                    getattr(quest, "complete_info", None),
                    getattr(quest, "done_info", None),
                )
                if info
            }

            for dialog in take_dialogs:
                conditions = list(
                    getattr(dialog, "preconditions", []) or []
                )
                for phrase in (dialog.phrases or {}).values():
                    conditions.extend(
                        getattr(phrase, "preconditions", []) or []
                    )
                target = f"dialog:{dialog.id}"
                for condition in conditions:
                    if isinstance(condition, HasInfo):
                        info = condition.info
                        if info in own_complete or info in own_deaths:
                            self.report.add(
                                "GRAPH-ROOT-001",
                                Severity.ERROR,
                                target,
                                f"Стартовый take-диалог требует "
                                f"HasInfo('{info}'), который выдаётся только "
                                "после взятия/завершения этого квеста.",
                                hint=(
                                    "Уберите предусловие или перенесите его "
                                    "в turnin/ветку развития."
                                ),
                                owner="dialog",
                                info=info,
                            )
                            continue
                        sources = self.info_sources.get(info, [])
                        if sources and all(
                            source_quest == quest.id
                            for _kind, _owner, source_quest in sources
                        ):
                            self.report.add(
                                "GRAPH-ROOT-001",
                                Severity.ERROR,
                                target,
                                f"Стартовый take-диалог требует "
                                f"HasInfo('{info}'), а этот поршень выдаётся "
                                "только внутри самого квеста.",
                                hint="Уберите предусловие или выдайте поршень раньше.",
                                owner="dialog",
                                info=info,
                            )
                    elif isinstance(condition, HasItem):
                        item = condition.item_alias
                        if item == getattr(quest, "reward_item_alias", None):
                            self.report.add(
                                "GRAPH-ROOT-001",
                                Severity.ERROR,
                                target,
                                f"Стартовый take-диалог требует "
                                f"HasItem('{item}'), который является "
                                "наградой этого квеста.",
                                hint="Награда не может быть предусловием взятия.",
                                owner="dialog",
                                item=item,
                            )
                            continue
                        sources = self.item_sources.get(item, [])
                        if sources and all(
                            source_quest == quest.id
                            for _kind, _owner, source_quest in sources
                        ):
                            self.report.add(
                                "GRAPH-ROOT-001",
                                Severity.ERROR,
                                target,
                                f"Стартовый take-диалог требует "
                                f"HasItem('{item}'), а предмет выдаётся "
                                "только внутри самого квеста.",
                                hint="Уберите предусловие или выдайте предмет раньше.",
                                owner="dialog",
                                item=item,
                            )

    @staticmethod
    def _owner_kind(owner: str) -> str:
        return owner.split(":", 1)[0] if ":" in owner else owner

    # ------------------------------------------------------------------
    # GRAPH-QUEST-001/002
    # ------------------------------------------------------------------

    def _check_quests(self) -> None:
        incoming: dict[str, list[str]] = defaultdict(list)
        dependencies: dict[str, set[str]] = defaultdict(set)

        for action, quest_id, owner, _dialog, _phrase, _stage in (
            self._iter_actions()
        ):
            if not isinstance(action, GiveTask):
                continue
            if action.task_id in self.quests:
                incoming[action.task_id].append(owner)
                if quest_id and quest_id != action.task_id:
                    dependencies[quest_id].add(action.task_id)

        for quest in self.quests.values():
            take_dialogs = self._take_dialogs(quest)
            external_start = bool(
                getattr(quest, "available_info", None)
                or (
                    getattr(quest, "npc_id", None)
                    and (
                        getattr(quest, "dialog_id", None)
                        or getattr(quest, "dialog_ids", None)
                    )
                )
            )
            if incoming.get(quest.id) or take_dialogs or external_start:
                continue
            self.report.add(
                "GRAPH-QUEST-001",
                Severity.ERROR,
                f"quest:{quest.id}",
                "Квест недостижим: нет входящего GiveTask, take-диалога, "
                "NPC-квестодателя и внешнего старта.",
                hint=(
                    "Добавьте take-диалог с GiveTask или выдайте квест "
                    "из другого квеста/on_complete_actions."
                ),
                owner="quest",
            )

        for component in self._strong_components(dependencies):
            if len(component) < 2:
                continue
            cycle = sorted(component)
            self.report.add(
                "GRAPH-QUEST-002",
                Severity.ERROR,
                " -> ".join(cycle),
                "Цикл зависимостей квестов через GiveTask/on_complete_actions: "
                + " -> ".join(cycle + [cycle[0]]),
                hint="Разорвите цикл, оставив одно направление выдачи.",
                owner="quest",
                quests=cycle,
            )

    @staticmethod
    def _strong_components(graph: dict[str, set[str]]) -> list[set[str]]:
        """Итеративный алгоритм Тарьяна для поиска SCC."""
        index = 0
        stack: list[str] = []
        on_stack: set[str] = set()
        indices: dict[str, int] = {}
        low: dict[str, int] = {}
        result: list[set[str]] = []

        def visit(node: str) -> None:
            nonlocal index
            indices[node] = index
            low[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)
            for neighbour in graph.get(node, set()):
                if neighbour not in indices:
                    visit(neighbour)
                    low[node] = min(low[node], low[neighbour])
                elif neighbour in on_stack:
                    low[node] = min(low[node], indices[neighbour])
            if low[node] == indices[node]:
                component: set[str] = set()
                while True:
                    current = stack.pop()
                    on_stack.discard(current)
                    component.add(current)
                    if current == node:
                        break
                result.append(component)

        for node in sorted(set(graph) | {n for ns in graph.values() for n in ns}):
            if node not in indices:
                visit(node)
        return result

    # ------------------------------------------------------------------
    # GRAPH-STAGE-*
    # ------------------------------------------------------------------

    def _dialog_has_complete_task(self, dialog: Any, quest_id: str) -> bool:
        return any(
            isinstance(action, CompleteTask) and action.task_id == quest_id
            for phrase in (dialog.phrases or {}).values()
            for action in getattr(phrase, "actions", []) or []
        )

    def _turnin_dialogs(self, quest: Any) -> list[Any]:
        result: list[Any] = []
        for dialog in self.quest_dialogs.get(quest.id, []):
            role = (getattr(dialog, "role", "") or "").lower()
            if role.startswith("turnin") and self._dialog_has_complete_task(
                dialog, quest.id
            ):
                result.append(dialog)
        return result

    def _check_stages(self) -> None:
        for quest in self.quests.values():
            stages = dict(getattr(quest, "stages", {}) or {})
            if not stages:
                continue
            stage_ids = set(stages)
            final_id = max(stage_ids)
            turnin_dialogs = self._turnin_dialogs(quest)
            turnin_complete = bool(turnin_dialogs)
            quest_exit = bool(
                getattr(quest, "extra_condlists", None)
                or getattr(quest, "return_to_giver_stage", None) is not None
            )
            transfer = getattr(quest, "transfer_conditions", {}) or {}

            for stage_id, stage in stages.items():
                if stage_id == final_id:
                    completion = bool(
                        quest_exit
                        or getattr(stage, "warfare_capture", None) is not None
                        or turnin_complete
                    )
                    if not completion:
                        self.report.add(
                            "GRAPH-STAGE-002",
                            Severity.ERROR,
                            f"stage:{quest.id}:{stage_id}",
                            "Финальный этап не имеет способа завершения: "
                            "нет CompleteTask в turnin-диалоге, "
                            "return_to_giver_stage, extra_condlists или "
                            "warfare_capture.",
                            hint=(
                                "Добавьте CompleteTask в диалог сдачи или иной "
                                "явный completion-путь."
                            ),
                            owner="stage",
                        )
                    continue

                rules = transfer.get(stage_id) or {}
                has_transfer = isinstance(rules, dict) and any(
                    bool(conditions) for conditions in rules.values()
                )
                has_exit = bool(
                    has_transfer
                    or getattr(stage, "target_squad_id", None)
                    or getattr(stage, "warfare_capture", None) is not None
                    or quest_exit
                )
                if not has_exit:
                    self.report.add(
                        "GRAPH-STAGE-001",
                        Severity.ERROR,
                        f"stage:{quest.id}:{stage_id}",
                        "Не-финальный этап «залип»: нет transfer_conditions, "
                        "target_squad_id, warfare_capture, extra_condlists или "
                        "return_to_giver_stage.",
                        hint="Добавьте условие перехода на следующий этап.",
                        owner="stage",
                    )

            for stage_id in transfer:
                if stage_id not in stage_ids:
                    self.report.add(
                        "GRAPH-STAGE-003",
                        Severity.ERROR,
                        f"stage:{quest.id}:{stage_id}",
                        f"transfer_conditions ссылается на несуществующий "
                        f"этап {stage_id}.",
                        hint="Исправьте номер этапа или добавьте этап.",
                        owner="quest",
                    )
            return_stage = getattr(quest, "return_to_giver_stage", None)
            if return_stage is not None and return_stage not in stage_ids:
                self.report.add(
                    "GRAPH-STAGE-003",
                    Severity.ERROR,
                    f"quest:{quest.id}",
                    f"return_to_giver_stage={return_stage} ссылается на "
                    "несуществующий этап.",
                    hint="Исправьте номер этапа.",
                    owner="quest",
                )

            if turnin_complete and final_id in transfer:
                rules = transfer.get(final_id) or {}
                if isinstance(rules, dict) and rules.get("complete"):
                    self.report.add(
                        "GRAPH-STAGE-004",
                        Severity.ERROR,
                        f"stage:{quest.id}:{final_id}",
                        "Последний этап завершается через transfer_conditions "
                        "до turnin-диалога с CompleteTask; награда/выбор "
                        "награды может быть потерян.",
                        hint=(
                            "Уберите автозавершение последнего этапа и "
                            "завершайте квест через CompleteTask."
                        ),
                        owner="stage",
                    )

    # ------------------------------------------------------------------
    # GRAPH-EDGE-001
    # ------------------------------------------------------------------

    def _check_edges(self) -> None:
        for action, _quest_id, owner, _dialog, _phrase, _stage in (
            self._iter_actions()
        ):
            if not isinstance(action, (GiveTask, CompleteTask)):
                continue
            if action.task_id not in self.quests:
                self.report.add(
                    "GRAPH-EDGE-001",
                    Severity.ERROR,
                    owner,
                    f"{type(action).__name__} ссылается на отсутствующий "
                    f"квест '{action.task_id}'.",
                    hint="Исправьте task_id или создайте квест.",
                    owner=self._owner_kind(owner),
                    task_id=action.task_id,
                )

        for dialog in self.dialogs.values():
            task_id = getattr(dialog, "task_id", None)
            if task_id and task_id not in self.quests:
                self.report.add(
                    "GRAPH-EDGE-001",
                    Severity.ERROR,
                    f"dialog:{dialog.id}",
                    f"Dialog.task_id='{task_id}' ссылается на отсутствующий "
                    "квест.",
                    hint="Исправьте task_id или создайте квест.",
                    owner="dialog",
                    task_id=task_id,
                )
            for phrase_id, phrase in (dialog.phrases or {}).items():
                for next_id in getattr(phrase, "next_phrases", []) or []:
                    if next_id not in dialog.phrases:
                        self.report.add(
                            "GRAPH-EDGE-001",
                            Severity.ERROR,
                            f"phrase:{dialog.id}:{phrase_id}",
                            f"next_phrases ссылается на отсутствующую реплику "
                            f"'{next_id}'.",
                            hint="Исправьте next_phrases.",
                            owner="phrase",
                            next_id=next_id,
                        )

        for quest in self.quests.values():
            dialog_ids = [getattr(quest, "dialog_id", None)]
            dialog_ids.extend(getattr(quest, "dialog_ids", []) or [])
            for dialog_id in dialog_ids:
                if dialog_id and dialog_id not in self.dialogs:
                    self.report.add(
                        "GRAPH-EDGE-001",
                        Severity.ERROR,
                        f"quest:{quest.id}",
                        f"Квест ссылается на отсутствующий диалог "
                        f"'{dialog_id}'.",
                        hint="Исправьте dialog_id/dialog_ids.",
                        owner="quest",
                        dialog_id=dialog_id,
                    )

    # ------------------------------------------------------------------
    # GRAPH-REWARD-*
    # ------------------------------------------------------------------

    def _completion_phrases_for(self, quest_id: str) -> list[tuple[Any, Any]]:
        return list(self.completion_phrases.get(quest_id, []))

    def _is_variant_reward_scheme(
        self, quest: Any, inline: list[tuple[Any, Any]]
    ) -> bool:
        """Разрешает ветвящуюся награду в не-сюжетном Warfare-квесте.

        В эталоне ``build_golden_test`` сумма награды зависит от выбранной
        ветки (штурм/соло), поэтому её нельзя выразить одним
        ``Quest.reward_*``. Такая схема допустима, если каждая ветка закрыта
        собственным info-маркером из ``cleanup_infos``.
        """
        if getattr(quest, "is_storyline", True):
            return False
        if not getattr(quest, "available_info", None):
            return False
        if len(self._completion_phrases_for(quest.id)) < 2:
            return False
        cleanup = set(getattr(quest, "cleanup_infos", []) or [])
        if not cleanup:
            return False
        for dialog, phrase in inline:
            condition_infos = {
                condition.info
                for condition in (
                    list(getattr(dialog, "preconditions", []) or [])
                    + list(getattr(phrase, "preconditions", []) or [])
                )
                if isinstance(condition, HasInfo)
            }
            if not (condition_infos & cleanup):
                return False
        return True

    def _check_rewards(self) -> None:
        for quest in self.quests.values():
            completion = self._completion_phrases_for(quest.id)
            has_reward = bool(
                getattr(quest, "reward_money", None)
                or getattr(quest, "reward_item_alias", None)
            )

            if not has_reward:
                inline = [
                    (dialog, phrase)
                    for dialog, phrase in completion
                    if any(
                        isinstance(action, (GiveMoney, GiveItem))
                        for action in getattr(phrase, "actions", []) or []
                    )
                ]
                if inline and not self._is_variant_reward_scheme(quest, inline):
                    for dialog, phrase in inline:
                        self.report.add(
                            "GRAPH-REWARD-001",
                            Severity.ERROR,
                            f"phrase:{dialog.id}:{phrase.id}",
                            "CompleteTask и GiveMoney/GiveItem в одной реплике "
                            "при пустых Quest.reward_money/reward_item_alias: "
                            "награда может быть потеряна.",
                            hint=(
                                "Перенесите награду в Quest.reward_* или "
                                "Quest.on_complete_actions."
                            ),
                            owner="phrase",
                        )

            on_complete = list(
                getattr(quest, "on_complete_actions", []) or []
            )
            if getattr(quest, "reward_money", None) is not None:
                duplicated = any(
                    isinstance(action, GiveMoney) for action in on_complete
                ) or any(
                    any(
                        isinstance(action, GiveMoney)
                        for action in getattr(phrase, "actions", []) or []
                    )
                    for _dialog, phrase in completion
                )
                if duplicated:
                    self.report.add(
                        "GRAPH-REWARD-002",
                        Severity.WARNING,
                        f"quest:{quest.id}",
                        "Деньги награды заданы и в Quest.reward_money, и в "
                        "on_complete_actions/реплике сдачи.",
                        hint="Оставьте один источник награды.",
                        owner="quest",
                    )
            if getattr(quest, "reward_item_alias", None):
                duplicated = any(
                    isinstance(action, GiveItem)
                    and action.item_alias == quest.reward_item_alias
                    for action in on_complete
                ) or any(
                    any(
                        isinstance(action, GiveItem)
                        and action.item_alias == quest.reward_item_alias
                        for action in getattr(phrase, "actions", []) or []
                    )
                    for _dialog, phrase in completion
                )
                if duplicated:
                    self.report.add(
                        "GRAPH-REWARD-002",
                        Severity.WARNING,
                        f"quest:{quest.id}",
                        "Предмет награды задан и в Quest.reward_item_alias, и "
                        "в on_complete_actions/реплике сдачи.",
                        hint="Оставьте один источник награды.",
                        owner="quest",
                    )

            complete_info = getattr(quest, "complete_info", None)
            if complete_info:
                manual = any(
                    isinstance(action, GiveInfo)
                    and action.info == complete_info
                    for action, action_quest_id, _owner, _d, _p, _s in (
                        self._iter_actions()
                    )
                    if action_quest_id == quest.id
                )
                if manual:
                    self.report.add(
                        "GRAPH-REWARD-003",
                        Severity.WARNING,
                        f"quest:{quest.id}",
                        f"complete_info='{complete_info}' выдаётся вручную и "
                        "автоматически через _reward.",
                        hint="Уберите ручной GiveInfo(complete_info).",
                        owner="quest",
                        info=complete_info,
                    )

    # ------------------------------------------------------------------
    # GRAPH-CLEAN-*
    # ------------------------------------------------------------------

    def _given_quest_items(self, quest: Any) -> set[str]:
        items: set[str] = set()
        containers = [
            getattr(quest, "on_init_actions", []) or [],
        ]
        for stage in (quest.stages or {}).values():
            containers.append(getattr(stage, "on_start_actions", []) or [])
        for dialog in self._take_dialogs(quest):
            for phrase in (dialog.phrases or {}).values():
                containers.append(getattr(phrase, "actions", []) or [])
        for actions in containers:
            for action in actions:
                if isinstance(action, (GiveItem, SpawnNpcItem)):
                    items.add(action.item_alias)
        return items

    def _check_cleanup(self) -> None:
        for quest in self.quests.values():
            given = self._given_quest_items(quest)
            checked = self.item_checks.get(quest.id, set())
            removed = {
                action.item_alias
                for action in getattr(quest, "on_fail_actions", []) or []
                if isinstance(action, (RemoveItem, TakeItem))
            }
            for item in sorted(given & checked):
                if item in removed:
                    continue
                self.report.add(
                    "GRAPH-CLEAN-001",
                    Severity.ERROR,
                    f"quest:{quest.id}",
                    f"Квестовый предмет '{item}' выдаётся и проверяется через "
                    "HasItem, но не изымается в on_fail_actions.",
                    hint=(
                        "Добавьте RemoveItem/TakeItem в on_fail_actions, иначе "
                        "повторное взятие сразу закроет этап."
                    ),
                    owner="quest",
                    item=item,
                )

            cleanup = set(getattr(quest, "cleanup_infos", []) or [])
            permanent = {
                info
                for info in (
                    getattr(quest, "taken_info", None),
                    getattr(quest, "complete_info", None),
                    getattr(quest, "done_info", None),
                    getattr(quest, "available_info", None),
                )
                if info
            }
            for stage_id, stage in (quest.stages or {}).items():
                for action in getattr(stage, "on_start_actions", []) or []:
                    if not isinstance(action, GiveInfo):
                        continue
                    info = action.info
                    if info in cleanup or info in permanent:
                        continue
                    if self.info_reads.get(info):
                        continue
                    self.report.add(
                        "GRAPH-CLEAN-002",
                        Severity.WARNING,
                        f"stage:{quest.id}:{stage_id}",
                        f"Временный GiveInfo('{info}') из on_start_actions не "
                        "попадает в cleanup_infos и нигде не читается.",
                        hint="Добавьте info в cleanup_infos или удалите его.",
                        owner="stage",
                        info=info,
                    )

            markers = {
                info
                for info in (
                    getattr(quest, "taken_info", None),
                    getattr(quest, "complete_info", None),
                )
                if info
            }
            for info in getattr(quest, "cleanup_infos", []) or []:
                if info in markers:
                    self.report.add(
                        "GRAPH-CLEAN-003",
                        Severity.WARNING,
                        f"quest:{quest.id}",
                        f"cleanup_infos содержит служебный поршень '{info}'.",
                        hint="Уберите taken_info/complete_info из cleanup_infos.",
                        owner="quest",
                        info=info,
                    )

    # ------------------------------------------------------------------
    # GRAPH-DEATH-001
    # ------------------------------------------------------------------

    def _check_death_refs(self) -> None:
        for quest in self.quests.values():
            referenced: set[str] = set()
            for rules in (
                getattr(quest, "transfer_conditions", {}) or {}
            ).values():
                if not isinstance(rules, dict):
                    continue
                for conditions in rules.values():
                    for condition in conditions or []:
                        if isinstance(condition, (HasInfo, DontHasInfo)):
                            referenced.add(condition.info)
            for condlist in getattr(quest, "extra_condlists", []) or []:
                for condition in getattr(condlist, "when", []) or []:
                    if isinstance(condition, (HasInfo, DontHasInfo)):
                        referenced.add(condition.info)

            for dialog in self._turnin_dialogs(quest):
                for condition in getattr(dialog, "preconditions", []) or []:
                    if isinstance(condition, (HasInfo, DontHasInfo)):
                        referenced.add(condition.info)
                for phrase in (dialog.phrases or {}).values():
                    for condition in (
                        getattr(phrase, "preconditions", []) or []
                    ):
                        if isinstance(condition, (HasInfo, DontHasInfo)):
                            referenced.add(condition.info)

            spawned = self.spawned_squads.get(quest.id, set())
            for info in referenced:
                for squad_id in self.death_info_squads.get(info, set()):
                    squad = self.squads.get(squad_id)
                    aliases = {squad_id}
                    if squad is not None and getattr(squad, "story_id", None):
                        aliases.add(squad.story_id)
                    if aliases & spawned:
                        continue
                    self.report.add(
                        "GRAPH-DEATH-001",
                        Severity.ERROR,
                        f"quest:{quest.id}",
                        f"Завершение/переход зависит от death_infos('{info}') "
                        f"отряда '{squad_id}', но этот отряд не спавнится "
                        "в квесте.",
                        hint=(
                            "Добавьте SpawnSquad этого отряда в on_init_actions "
                            "или on_start_actions."
                        ),
                        owner="quest",
                        info=info,
                        squad_id=squad_id,
                    )

    # ------------------------------------------------------------------
    # GRAPH-CYCLE-001
    # ------------------------------------------------------------------

    def _check_phrase_cycles(self) -> None:
        for dialog in self.dialogs.values():
            phrases = dialog.phrases or {}
            adjacency = {
                phrase_id: [
                    next_id
                    for next_id in getattr(phrase, "next_phrases", []) or []
                    if next_id in phrases
                ]
                for phrase_id, phrase in phrases.items()
            }
            colours: dict[int, int] = {}
            stack: list[int] = []
            seen: set[tuple[int, ...]] = set()

            def visit(node: int) -> None:
                colours[node] = 1
                stack.append(node)
                for neighbour in adjacency.get(node, []):
                    colour = colours.get(neighbour, 0)
                    if colour == 1:
                        position = stack.index(neighbour)
                        cycle = tuple(sorted(stack[position:]))
                        if cycle in seen:
                            continue
                        seen.add(cycle)
                        has_action = any(
                            getattr(phrases[item], "actions", [])
                            for item in cycle
                        )
                        if not has_action:
                            self.report.add(
                                "GRAPH-CYCLE-001",
                                Severity.WARNING,
                                f"dialog:{dialog.id}",
                                "Цикл next_phrases без действия/изменения "
                                "состояния: "
                                + " -> ".join(str(item) for item in cycle),
                                hint="Разорвите цикл или добавьте действие выхода.",
                                owner="dialog",
                                cycle=list(cycle),
                            )
                    elif colour == 0:
                        visit(neighbour)
                stack.pop()
                colours[node] = 2

            for phrase_id in phrases:
                if colours.get(phrase_id, 0) == 0:
                    visit(phrase_id)


__all__ = ["GraphIndex", "GraphValidator"]
