"""Семантический линтер X-Ray/Anomaly для квестовых проектов.

Модуль реализует правила ``XRAY-*`` из ``docs/VALIDATION_SPEC.md`` (§4.5).
Он не читает ``_unpacked/`` и не пишет в ``examples/``: единственные
источники данных — :class:`~src.core.models.ModProject` и необязательная
:class:`~src.db.repository.GameDatabase`.

Линтер намеренно не бросает исключений: все замечания складываются в
:class:`~src.validation.report.ValidationReport`.
"""

from __future__ import annotations

from typing import Any, Iterator

from src.core.models import (
    ClearSmart,
    CompleteTask,
    CustomSquad,
    Dialog,
    GiveInfo,
    GiveItem,
    GiveMoney,
    GiveTask,
    HasInfo,
    HasItem,
    HasMoney,
    ModProject,
    Quest,
    QuestCondlist,
    RemoveInfo,
    RemoveSquad,
    SmartOwner,
    SpawnNpcItem,
    SpawnSquad,
)
from src.db.repository import GameDatabase
from src.validation.report import Severity, ValidationReport

#: Роли NPC из БД, для которых ``meet``-диалог может перекрыть ``actor_dialog``.
_UNIQUE_MEET_ROLES = frozenset(
    {"trader", "barmen", "barman", "mechanic", "leader", "unique"}
)

#: Подстроки id/имени, указывающие на уникального торговца/лидера.
_UNIQUE_MEET_MARKERS = (
    "trader",
    "barmen",
    "barman",
    "mechanic",
    "leader",
    "торгов",
    "бармен",
    "механик",
    "лидер",
)


class XrayLinter:
    """Проверяет проект на типичные ошибки рантайма X-Ray/Anomaly.

    Args:
        db (GameDatabase | None): База ассетов для data-driven проверок
            (уникальные ``meet``-NPC). ``None`` отключает только те правила,
            которым нужна БД.
        report (ValidationReport): Накопительный отчёт валидации.
    """

    def __init__(
        self, db: GameDatabase | None, report: ValidationReport
    ) -> None:
        self.db = db
        self.report = report
        self._project: ModProject | None = None
        self._custom_npc_aliases: set[str] = set()
        self._custom_npc_spawn_smarts: set[str] = set()

    # ------------------------------------------------------------------
    # Публичная точка входа
    # ------------------------------------------------------------------

    def validate(self, project: ModProject) -> None:
        """Добавляет в отчёт все замечания ``XRAY-*`` для проекта.

        Args:
            project (ModProject): Проверяемый проект мода.
        """
        self._project = project
        self._custom_npc_aliases: set[str] = set()
        self._custom_npc_spawn_smarts: set[str] = set()
        for npc in (getattr(project, "npcs", None) or {}).values():
            for value in (
                getattr(npc, "id", None),
                getattr(npc, "character_profile", None),
                getattr(npc, "story_id", None),
            ):
                name = str(value or "").strip()
                if name:
                    self._custom_npc_aliases.add(name)
            spawn_smart = str(
                getattr(npc, "spawn_smart", None) or ""
            ).strip()
            if spawn_smart:
                self._custom_npc_spawn_smarts.add(spawn_smart)
        self._check_names(project)

        for quest in project.quests.values():
            self._check_quest(quest)

        for dialog in project.dialogs.values():
            self._check_dialog(dialog)

        self._check_localization(project)

    # ------------------------------------------------------------------
    # Общие помощники
    # ------------------------------------------------------------------

    @staticmethod
    def _dialog_id(dialog: Dialog) -> str:
        """Возвращает канонический ID диалога."""
        return str(
            getattr(dialog, "dialog_id", None)
            or getattr(dialog, "id", None)
            or "<dialog>"
        )

    @staticmethod
    def _role(dialog: Dialog) -> str:
        """Возвращает нормализованную роль диалога."""
        role = str(getattr(dialog, "role", None) or "").strip().lower()
        if role:
            return role
        dialog_id = XrayLinter._dialog_id(dialog).lower()
        if "turnin" in dialog_id or "turn_in" in dialog_id:
            return "turnin"
        if "take" in dialog_id:
            return "take"
        return ""

    def _find_squad(self, alias: str | None) -> CustomSquad | None:
        """Ищет ``CustomSquad`` проекта по id, story_id или ключу карты."""
        if not alias or self._project is None:
            return None
        value = str(alias).strip()
        if not value:
            return None
        for key, squad in self._project.squads.items():
            if value in (
                str(key),
                str(getattr(squad, "id", "") or ""),
                str(getattr(squad, "story_id", "") or ""),
            ):
                return squad
        return None

    def _linked_quest(self, dialog: Dialog) -> Quest | None:
        """Находит квест, связанный с диалогом."""
        if self._project is None:
            return None
        task_id = getattr(dialog, "task_id", None)
        if task_id and task_id in self._project.quests:
            return self._project.quests[task_id]
        dialog_id = self._dialog_id(dialog)
        for quest in self._project.quests.values():
            linked = [quest.dialog_id, *quest.dialog_ids]
            if dialog_id in linked:
                return quest
        return None

    def _linked_dialogs(self, quest: Quest) -> Iterator[Dialog]:
        """Итерирует диалоги, связанные с квестом."""
        if self._project is None:
            return
        ids = {quest.dialog_id, *quest.dialog_ids}
        for dialog in self._project.dialogs.values():
            if self._dialog_id(dialog) in ids or getattr(
                dialog, "task_id", None
            ) == quest.id:
                yield dialog

    @staticmethod
    def _quest_action_lists(
        quest: Quest,
    ) -> Iterator[tuple[str, list[Any]]]:
        """Итерирует списки действий квеста с человекочитаемым владельцем."""
        yield (
            f"{quest.id}.on_init_actions",
            list(getattr(quest, "on_init_actions", None) or []),
        )
        yield (
            f"{quest.id}.on_complete_actions",
            list(getattr(quest, "on_complete_actions", None) or []),
        )
        yield (
            f"{quest.id}.on_fail_actions",
            list(getattr(quest, "on_fail_actions", None) or []),
        )
        for stage_id, stage in sorted(
            (getattr(quest, "stages", None) or {}).items()
        ):
            yield (
                f"{quest.id}.stage_{stage_id}.on_start_actions",
                list(getattr(stage, "on_start_actions", None) or []),
            )

    def _giver_smarts(self, quest: Quest) -> set[str]:
        """Возвращает смарты, которые проект использует как маркер квестодателя."""
        values: set[str] = set(self._custom_npc_spawn_smarts)
        for stage in (getattr(quest, "stages", None) or {}).values():
            target = str(getattr(stage, "target_alias", "") or "").strip()
            if target:
                values.add(target)
            for variant in getattr(stage, "target_variants", None) or []:
                value = str(getattr(variant, "value", "") or "").strip()
                if value:
                    values.add(value)
        return values

    def _has_completion_path(self, quest: Quest) -> bool:
        """True, если у квеста есть явный путь завершения."""
        if getattr(quest, "return_to_giver_stage", None) is not None:
            return True
        for condlist in getattr(quest, "extra_condlists", None) or []:
            if isinstance(condlist, QuestCondlist) and condlist.result == "complete":
                return True
        last_stage = max(quest.stages) if quest.stages else 0
        rules = (getattr(quest, "transfer_conditions", None) or {}).get(
            last_stage, {}
        )
        if rules.get("complete"):
            return True
        for dialog in self._linked_dialogs(quest):
            for phrase in (getattr(dialog, "phrases", None) or {}).values():
                if any(
                    isinstance(action, CompleteTask)
                    for action in (getattr(phrase, "actions", None) or [])
                ):
                    return True
        return False

    # ------------------------------------------------------------------
    # Проверки квестов
    # ------------------------------------------------------------------

    def _check_quest(self, quest: Quest) -> None:
        """Запускает все проверки, относящиеся к одному квесту."""
        self._check_clear_smart(quest)
        self._check_spawn_squad(quest)
        self._check_spawn_npc_item(quest)
        self._check_cleanup(quest)
        self._check_modes(quest)
        self._check_warfare(quest)
        self._check_task_transfer(quest)

    def _check_clear_smart(self, quest: Quest) -> None:
        """``XRAY-SPAWN-001``: очистка смарта квестодателя и порядок действий."""
        giver_smarts = self._giver_smarts(quest)
        for owner, actions in self._quest_action_lists(quest):
            spawned_smarts: set[str] = set()
            for index, action in enumerate(actions):
                if isinstance(action, SpawnSquad):
                    spawned_smarts.add(str(action.smart_alias))
                    continue
                if not isinstance(action, ClearSmart):
                    continue
                smart = str(action.smart_alias)
                if not action.allow_giver_smart and smart in giver_smarts:
                    self.report.add(
                        "XRAY-SPAWN-001",
                        Severity.ERROR,
                        f"{owner}.clear_smart[{index}]",
                        (
                            f"ClearSmart очищает смарт '{smart}', который "
                            "используется как смарт квестодателя."
                        ),
                        hint=(
                            "Разведите точку спавна и смарт квестодателя либо "
                            "явно задайте allow_giver_smart=True."
                        ),
                        owner="quest",
                        smart=smart,
                    )
                if smart in spawned_smarts:
                    self.report.add(
                        "XRAY-SPAWN-001",
                        Severity.ERROR,
                        f"{owner}.clear_smart[{index}]",
                        (
                            f"ClearSmart стоит после SpawnSquad для смарта "
                            f"'{smart}' в одном списке действий."
                        ),
                        hint=(
                            "Перенесите ClearSmart перед SpawnSquad: иначе он "
                            "удалит только что созданный квестовый отряд."
                        ),
                        owner="quest",
                        smart=smart,
                    )

    def _check_spawn_squad(self, quest: Quest) -> None:
        """``XRAY-SPAWN-002``: отряд появляется прямо на точке назначения."""
        for owner, actions in self._quest_action_lists(quest):
            for index, action in enumerate(actions):
                if not isinstance(action, SpawnSquad):
                    continue
                squad = self._find_squad(action.squad_alias)
                if squad is None:
                    continue
                target_smart = str(
                    getattr(squad, "target_smart", None) or ""
                ).strip()
                if (
                    getattr(action, "mode", "warfare") == "story"
                    and not target_smart
                ):
                    self.report.add(
                        "XRAY-SPAWN-004",
                        Severity.WARNING,
                        f"{owner}.spawn_squad[{index}]",
                        (
                            f"SpawnSquad(mode='story') для CustomSquad "
                            f"'{squad.id}' без target_smart: A-Life может "
                            "переназначить отряд на другой смарт, и он уйдёт "
                            "с точки спавна."
                        ),
                        hint=(
                            "Задайте CustomSquad.target_smart: тот же смарт, "
                            "что и точка спавна, для удержания, либо другой "
                            "смарт для марша."
                        ),
                        owner="squad",
                        squad=squad.id,
                    )
                if target_smart and target_smart == str(action.smart_alias):
                    self.report.add(
                        "XRAY-SPAWN-002",
                        Severity.WARNING,
                        f"{owner}.spawn_squad[{index}]",
                        (
                            f"SpawnSquad.smart_alias совпадает с "
                            f"CustomSquad.target_smart ('{target_smart}'): "
                            "отряд появляется прямо на точке назначения."
                        ),
                        hint=(
                            "Спавните отряд на отдельном смарте, чтобы он "
                            "дошёл до цели маршем."
                        ),
                        owner="stage",
                        smart=target_smart,
                        squad=squad.id,
                    )

    def _check_spawn_npc_item(self, quest: Quest) -> None:
        """``XRAY-SPAWNITEM-001/002``: порядок и адресация предмета."""
        for owner, actions in self._quest_action_lists(quest):
            saw_spawn = False
            for index, action in enumerate(actions):
                if isinstance(action, SpawnSquad):
                    saw_spawn = True
                    continue
                if not isinstance(action, SpawnNpcItem):
                    continue
                if not saw_spawn:
                    self.report.add(
                        "XRAY-SPAWNITEM-001",
                        Severity.ERROR,
                        f"{owner}.spawn_npc_item[{index}]",
                        (
                            "SpawnNpcItem стоит раньше SpawnSquad в одном "
                            "списке действий."
                        ),
                        hint=(
                            "Сначала заспавните отряд, затем кладите предмет "
                            "в инвентарь его командира."
                        ),
                        owner="stage",
                    )
                squad = self._find_squad(action.target_alias)
                if squad is not None and not str(
                    getattr(squad, "story_id", None) or ""
                ).strip():
                    self.report.add(
                        "XRAY-SPAWNITEM-002",
                        Severity.ERROR,
                        f"{owner}.spawn_npc_item[{index}]",
                        (
                            f"SpawnNpcItem.target_alias ссылается на "
                            f"CustomSquad '{squad.id}' без story_id."
                        ),
                        hint=(
                            "Задайте CustomSquad.story_id, иначе командир "
                            "отряда не будет надёжно найден."
                        ),
                        owner="squad",
                        squad=squad.id,
                    )

    def _check_cleanup(self, quest: Quest) -> None:
        """``XRAY-CLEAN-003``: удаление отряда без story_id при провале."""
        for index, action in enumerate(
            getattr(quest, "on_fail_actions", None) or []
        ):
            if not isinstance(action, RemoveSquad):
                continue
            squad = self._find_squad(action.squad_alias)
            if squad is None:
                continue
            if str(getattr(squad, "story_id", None) or "").strip():
                continue
            self.report.add(
                "XRAY-CLEAN-003",
                Severity.ERROR,
                f"{quest.id}.on_fail_actions.remove_squad[{index}]",
                (
                    f"RemoveSquad адресует CustomSquad '{squad.id}' без "
                    "story_id."
                ),
                hint="Добавьте story_id: get_story_squad иначе не найдёт отряд.",
                owner="squad",
                squad=squad.id,
            )

    def _check_modes(self, quest: Quest) -> None:
        """``XRAY-MODE-001/002/003``: смешение Warfare и Story-режимов."""
        has_capture = any(
            getattr(stage, "warfare_capture", None) is not None
            for stage in (quest.stages or {}).values()
        )
        story_spawns: list[str] = []
        warfare_spawns: list[str] = []
        for owner, actions in self._quest_action_lists(quest):
            for action in actions:
                if not isinstance(action, SpawnSquad):
                    continue
                if getattr(action, "mode", "warfare") == "story":
                    story_spawns.append(owner)
                else:
                    warfare_spawns.append(owner)

        if has_capture and story_spawns:
            self.report.add(
                "XRAY-MODE-001",
                Severity.ERROR,
                f"{quest.id}.warfare_capture",
                (
                    "В одном квесте смешаны WarfareCapture и "
                    "SpawnSquad(mode='story')."
                ),
                hint="Warfare-квест должен использовать только Warfare-спавн.",
                owner="quest",
            )
        if getattr(quest, "requires_warfare", False) and story_spawns:
            self.report.add(
                "XRAY-MODE-002",
                Severity.ERROR,
                f"{quest.id}.requires_warfare",
                (
                    "requires_warfare=True сочетается со "
                    "SpawnSquad(mode='story')."
                ),
                hint=(
                    "Уберите requires_warfare или замените Story-спавн на "
                    "Warfare-спавн."
                ),
                owner="quest",
            )
        if (
            warfare_spawns
            and not getattr(quest, "requires_warfare", False)
            and not has_capture
        ):
            self.report.add(
                "XRAY-MODE-003",
                Severity.WARNING,
                f"{quest.id}.spawn_squad",
                (
                    "SpawnSquad(mode='warfare') используется без "
                    "requires_warfare и без WarfareCapture."
                ),
                hint=(
                    "В Story/freeplay такой спавн может не работать: "
                    "добавьте requires_warfare или используйте mode='story'."
                ),
                owner="quest",
            )

    def _check_warfare(self, quest: Quest) -> None:
        """``XRAY-WARFARE-003/004``: несовместимые условия и completion-путь."""
        for index, condlist in enumerate(
            getattr(quest, "extra_condlists", None) or []
        ):
            if not isinstance(condlist, QuestCondlist):
                self.report.add(
                    "XRAY-WARFARE-003",
                    Severity.ERROR,
                    f"{quest.id}.extra_condlists[{index}]",
                    "extra_condlists содержит не QuestCondlist.",
                    hint="Передайте QuestCondlist(when=[...], result=...).",
                    owner="quest",
                )
                continue
            for condition in condlist.when:
                if isinstance(condition, (SmartOwner, HasMoney)):
                    self.report.add(
                        "XRAY-WARFARE-003",
                        Severity.ERROR,
                        f"{quest.id}.extra_condlists[{index}]",
                        (
                            f"Условие {type(condition).__name__} не "
                            "поддерживается в extra_condlists."
                        ),
                        hint=(
                            "Используйте HasInfo/DontHasInfo/HasItem или "
                            "перенесите проверку в status_functor."
                        ),
                        owner="quest",
                    )

        has_capture = any(
            getattr(stage, "warfare_capture", None) is not None
            for stage in (quest.stages or {}).values()
        )
        if (
            getattr(quest, "requires_warfare", False)
            and not has_capture
            and not self._has_completion_path(quest)
        ):
            self.report.add(
                "XRAY-WARFARE-004",
                Severity.WARNING,
                f"{quest.id}.requires_warfare",
                (
                    "requires_warfare=True без WarfareCapture и без "
                    "completion-пути."
                ),
                hint=(
                    "Добавьте WarfareCapture или завершение через "
                    "CompleteTask/return_to_giver_stage/extra_condlists."
                ),
                owner="quest",
            )

    def _check_task_transfer(self, quest: Quest) -> None:
        """``XRAY-TASK-005``: переход этапа только по ``HasItem``.

        В X-Ray статус этапа надёжнее продвигать по инфопоршню: предмет
        может быть потерян или переложен, а ``*_status`` вызывается по
        таймеру. Предупреждение не блокирует сборку.
        """
        stages = quest.stages or {}
        if not stages:
            return
        last_stage = max(stages)
        for stage_id in sorted(stages):
            if stage_id >= last_stage:
                continue
            rules = (quest.transfer_conditions or {}).get(stage_id) or {}
            conditions = [
                condition
                for values in rules.values()
                for condition in (values or [])
            ]
            has_item = any(isinstance(c, HasItem) for c in conditions)
            has_info = any(isinstance(c, HasInfo) for c in conditions)
            if has_item and not has_info:
                self.report.add(
                    "XRAY-TASK-005",
                    Severity.WARNING,
                    f"{quest.id}.stage_{stage_id}.transfer_conditions",
                    (
                        "Переход с нефинального этапа привязан только к "
                        "HasItem, без HasInfo."
                    ),
                    hint=(
                        "Добавьте HasInfo(info): в X-Ray переходы через "
                        "*_status надёжнее проверять по инфопоршню."
                    ),
                    owner="stage",
                )

    # ------------------------------------------------------------------
    # Проверки диалогов
    # ------------------------------------------------------------------

    def _check_dialog(self, dialog: Dialog) -> None:
        """Запускает проверки одного диалога."""
        dialog_id = self._dialog_id(dialog)
        role = self._role(dialog)
        linked_quest = self._linked_quest(dialog)

        self._check_meet(dialog, dialog_id)
        self._check_reward(dialog, dialog_id, role, linked_quest)
        self._check_dialog_gate(dialog, dialog_id, role, linked_quest)
        self._check_dialog_turnin_preconditions(dialog, dialog_id, role)
        self._check_phrase_parity(dialog, dialog_id)

    def _check_meet(
        self, dialog: Dialog, dialog_id: str
    ) -> None:
        """``XRAY-MEET-001``: уникальный ``meet``-NPC и ``actor_dialog``."""
        npc_id = str(getattr(dialog, "npc_id", None) or "").strip()
        if not npc_id:
            return
        # Диалог кастомного NPC привязан через файлы мода, а не через
        # ванильный meet/actor_dialog.
        if npc_id in self._custom_npc_aliases:
            return
        if not self._is_unique_meet_npc(npc_id):
            return
        self.report.add(
            "XRAY-MEET-001",
            Severity.WARNING,
            dialog_id,
            (
                f"Диалог привязан к уникальному meet-NPC '{npc_id}': "
                "actor_dialog может не появиться в игре."
            ),
            hint=(
                "Проверьте стартовый диалог на чистом сохранении; при "
                "необходимости патчите meet или используйте неуникального NPC."
            ),
            owner="dialog",
            npc=npc_id,
        )

    def _check_reward(
        self,
        dialog: Dialog,
        dialog_id: str,
        role: str,
        linked_quest: Quest | None,
    ) -> None:
        """``XRAY-REWARD-002/003``: награда и неверные реплики."""
        reward_money = (
            getattr(linked_quest, "reward_money", None)
            if linked_quest is not None
            else None
        )
        reward_item = (
            getattr(linked_quest, "reward_item_alias", None)
            if linked_quest is not None
            else None
        )
        empty_rewards = not reward_money and not reward_item

        for phrase_id, phrase in sorted(
            (getattr(dialog, "phrases", None) or {}).items()
        ):
            actions = list(getattr(phrase, "actions", None) or [])
            has_complete = any(
                isinstance(action, CompleteTask) for action in actions
            )
            has_give_task = any(
                isinstance(action, GiveTask) for action in actions
            )
            inline_reward = any(
                isinstance(action, (GiveMoney, GiveItem))
                for action in actions
            )

            if role.startswith("take") and has_complete:
                self.report.add(
                    "XRAY-REWARD-003",
                    Severity.ERROR,
                    f"{dialog_id}.phrase_{phrase_id}",
                    "CompleteTask находится в take-диалоге.",
                    hint="Завершайте квест только в turnin-диалоге.",
                    owner="dialog",
                )
            if role.startswith("turnin") and has_give_task:
                self.report.add(
                    "XRAY-REWARD-003",
                    Severity.ERROR,
                    f"{dialog_id}.phrase_{phrase_id}",
                    "GiveTask находится в turnin-диалоге.",
                    hint="Выдавайте задачу в take-диалоге, а не при сдаче.",
                    owner="dialog",
                )
            if has_complete and inline_reward and empty_rewards:
                self.report.add(
                    "XRAY-REWARD-002",
                    Severity.WARNING,
                    f"{dialog_id}.phrase_{phrase_id}",
                    (
                        "GiveMoney/GiveItem стоят рядом с CompleteTask, а "
                        "Quest.reward_money/reward_item_alias пусты."
                    ),
                    hint=(
                        "Перенесите награду в Quest.reward_* или "
                        "Quest.on_complete_actions."
                    ),
                    owner="dialog",
                )

    def _check_dialog_gate(
        self,
        dialog: Dialog,
        dialog_id: str,
        role: str,
        linked_quest: Quest | None,
    ) -> None:
        """``XRAY-DIALOG-001``: turnin без гейта готовности."""
        if not role.startswith("turnin"):
            return
        has_info_gate = any(
            isinstance(condition, HasInfo)
            for condition in (getattr(dialog, "preconditions", None) or [])
        )
        has_stage_gate = (
            linked_quest is not None
            and getattr(linked_quest, "return_to_giver_stage", None) is not None
        )
        if has_info_gate or has_stage_gate:
            return
        self.report.add(
            "XRAY-DIALOG-001",
            Severity.WARNING,
            dialog_id,
            "Turnin-диалог не имеет гейта готовности.",
            hint=(
                "Добавьте HasInfo(complete/death info) или задайте "
                "Quest.return_to_giver_stage."
            ),
            owner="dialog",
        )

    def _check_dialog_turnin_preconditions(
        self, dialog: Dialog, dialog_id: str, role: str
    ) -> None:
        """``XRAY-DLG-005``: item/info-гейт на корне диалога сдачи.

        ``Dialog.preconditions`` с ``HasItem``/``HasInfo``/``HasMoney`` (без
        ``TaskStage``) заставляют генератор повесить ``_can_take`` на корень
        диалога. При активном квесте такой диалог блокируется, и
        ``_can_turn_in`` не получает управления.
        """
        is_turnin = role in ("turnin", "turn_in")
        if not is_turnin:
            is_turnin = any(
                isinstance(action, CompleteTask)
                for phrase in (getattr(dialog, "phrases", None) or {}).values()
                for action in (getattr(phrase, "actions", None) or [])
            )
        if not is_turnin:
            return
        root_conditions = list(getattr(dialog, "preconditions", None) or [])
        if not root_conditions:
            return
        has_task_gate = any(
            type(condition).__name__ in {"TaskStage", "TaskActive"}
            or str(getattr(condition, "type", "")) in {
                "task_stage",
                "task_active",
            }
            for condition in root_conditions
        )
        if has_task_gate:
            return
        if not any(
            isinstance(condition, (HasItem, HasInfo, HasMoney))
            for condition in root_conditions
        ):
            return
        self.report.add(
            "XRAY-DLG-005",
            Severity.WARNING,
            dialog_id,
            (
                "Dialog.preconditions содержит HasItem/HasInfo/HasMoney "
                "без TaskStage: компилятор повесит _can_take на корень "
                "диалога и заблокирует сдачу при активном квесте."
            ),
            hint=(
                "Перенесите условие на стартовую фразу "
                "(DialogPhrase.preconditions), чтобы на корень встал "
                "_can_turn_in."
            ),
            owner="dialog",
        )

    def _check_phrase_parity(self, dialog: Dialog, dialog_id: str) -> None:
        """``XRAY-LOC-002``: чётные ID — Игрок, нечётные — NPC."""
        for phrase_id, phrase in sorted(
            (getattr(dialog, "phrases", None) or {}).items()
        ):
            for next_id in getattr(phrase, "next_phrases", None) or []:
                if (int(phrase_id) % 2) == (int(next_id) % 2):
                    self.report.add(
                        "XRAY-LOC-002",
                        Severity.WARNING,
                        f"{dialog_id}.phrase_{phrase_id}.next_{next_id}",
                        (
                            f"Нарушена чётность говорящих: фраза {phrase_id} "
                            f"ведёт на фразу {next_id} с тем же говорящим."
                        ),
                        hint=(
                            "Чётные ID — реплики Игрока, нечётные — NPC; "
                            "соседние реплики должны чередоваться."
                        ),
                        owner="dialog",
                    )

    # ------------------------------------------------------------------
    # Имена и локализация
    # ------------------------------------------------------------------

    def _check_names(self, project: ModProject) -> None:
        """``XRAY-NAME-001``: дубли story_id и коллизии ID между типами."""
        story_owners: dict[str, list[str]] = {}
        for squad in project.squads.values():
            story_id = str(getattr(squad, "story_id", None) or "").strip()
            if story_id:
                story_owners.setdefault(story_id, []).append(str(squad.id))
        for story_id, owners in story_owners.items():
            if len(owners) > 1:
                self.report.add(
                    "XRAY-NAME-001",
                    Severity.ERROR,
                    f"squad.{story_id}",
                    (
                        f"Дублирующийся CustomSquad.story_id '{story_id}' "
                        f"у отрядов: {', '.join(sorted(owners))}."
                    ),
                    hint="story_id обязан быть уникальным в проекте.",
                    owner="squad",
                )

        namespaces: dict[str, set[str]] = {}

        def register(value: Any, kind: str) -> None:
            text = str(value or "").strip()
            if text:
                namespaces.setdefault(text, set()).add(kind)

        for quest in project.quests.values():
            register(quest.id, "quest")
            for info in self._quest_infos(quest):
                register(info, "info")
        for dialog in project.dialogs.values():
            register(self._dialog_id(dialog), "dialog")
            for info in self._dialog_infos(dialog):
                register(info, "info")
        for squad in project.squads.values():
            register(squad.id, "squad")
            register(getattr(squad, "story_id", None), "squad")
            for info in getattr(squad, "death_infos", None) or []:
                register(info, "info")

        for value, kinds in namespaces.items():
            if len(kinds) > 1:
                self.report.add(
                    "XRAY-NAME-001",
                    Severity.ERROR,
                    f"name.{value}",
                    (
                        f"ID '{value}' используется в разных пространствах "
                        f"имён: {', '.join(sorted(kinds))}."
                    ),
                    hint="Переименуйте один из объектов, чтобы ID был уникален.",
                    owner="project",
                )

        dialog_ids = [self._dialog_id(dialog) for dialog in project.dialogs.values()]
        duplicates = {
            dialog_id
            for dialog_id in dialog_ids
            if dialog_ids.count(dialog_id) > 1
        }
        for dialog_id in duplicates:
            self.report.add(
                "XRAY-NAME-001",
                Severity.ERROR,
                f"dialog.{dialog_id}",
                f"Несколько диалогов используют один ID '{dialog_id}'.",
                hint="ID диалога должен быть уникальным.",
                owner="dialog",
            )

    @staticmethod
    def _quest_infos(quest: Quest) -> Iterator[str]:
        """Итерирует все информационные поршни, объявленные квестом."""
        for field in (
            "taken_info",
            "complete_info",
            "available_info",
            "done_info",
        ):
            value = getattr(quest, field, None)
            if value:
                yield str(value)
        for info in getattr(quest, "cleanup_infos", None) or []:
            yield str(info)
        for actions in (
            getattr(quest, "on_init_actions", None) or [],
            getattr(quest, "on_complete_actions", None) or [],
            getattr(quest, "on_fail_actions", None) or [],
        ):
            for action in actions:
                if isinstance(action, (GiveInfo, RemoveInfo)):
                    yield str(action.info)

    @staticmethod
    def _dialog_infos(dialog: Dialog) -> Iterator[str]:
        """Итерирует информационные поршни, упомянутые в диалоге."""
        for phrase in (getattr(dialog, "phrases", None) or {}).values():
            for action in getattr(phrase, "actions", None) or []:
                if isinstance(action, (GiveInfo, RemoveInfo)):
                    yield str(action.info)

    def _check_localization(self, project: ModProject) -> None:
        """``XRAY-LOC-001/003``: пустые тексты и слишком длинные заголовки."""
        for quest in project.quests.values():
            if not str(getattr(quest, "title_ru", "") or "").strip():
                self._add_empty_text(
                    f"{quest.id}.title_ru", "title_ru", "quest"
                )
            if not str(getattr(quest, "descr_ru", "") or "").strip():
                self._add_empty_text(
                    f"{quest.id}.descr_ru", "descr_ru", "quest"
                )
            title = str(getattr(quest, "title_ru", "") or "")
            if len(title) > 64:
                self.report.add(
                    "XRAY-LOC-003",
                    Severity.INFO,
                    f"{quest.id}.title_ru",
                    (
                        f"Заголовок квеста длиннее 64 символов "
                        f"({len(title)})."
                    ),
                    hint="Сократите заголовок, чтобы он поместился в КПК.",
                    owner="quest",
                )

            for stage_id, stage in sorted((quest.stages or {}).items()):
                owner_id = f"{quest.id}.stage_{stage_id}"
                if not str(getattr(stage, "title_ru", "") or "").strip():
                    self._add_empty_text(
                        f"{owner_id}.title_ru", "title_ru", "stage"
                    )
                if not str(getattr(stage, "descr_ru", "") or "").strip():
                    self._add_empty_text(
                        f"{owner_id}.descr_ru", "descr_ru", "stage"
                    )
                for variant_index, variant in enumerate(
                    getattr(stage, "descr_variants", None) or []
                ):
                    if not str(
                        getattr(variant, "text_ru", "") or ""
                    ).strip():
                        self._add_empty_text(
                            f"{owner_id}.descr_variant_{variant_index}",
                            "text_ru",
                            "stage",
                        )

        for dialog in project.dialogs.values():
            dialog_id = self._dialog_id(dialog)
            for phrase_id, phrase in sorted(
                (getattr(dialog, "phrases", None) or {}).items()
            ):
                if not str(getattr(phrase, "text_ru", "") or "").strip():
                    self._add_empty_text(
                        f"{dialog_id}.phrase_{phrase_id}.text_ru",
                        "text_ru",
                        "dialog",
                    )

        self._check_fully_empty_texts(project)

    def _check_fully_empty_texts(self, project: ModProject) -> None:
        """``XRAY-TEXT-001``: оба языка пусты — недопустимый ``<text>``.

        Правило проверяет только случай, когда пусты и ``rus``, и ``eng``.
        Частично пустой перевод остаётся зоной ``XRAY-LOC-*`` и
        обрабатывается fallback-генератором.
        """

        def check(
            target_id: str,
            field_ru: str,
            field_en: str,
            source: Any,
            owner: str,
        ) -> None:
            ru = str(getattr(source, field_ru, "") or "")
            en = str(getattr(source, field_en, "") or "")
            if ru.strip() or en.strip():
                return
            self.report.add(
                "XRAY-TEXT-001",
                Severity.ERROR,
                target_id,
                (
                    f"Оба языка пусты ({field_ru}/{field_en}): в игре "
                    "будет пустая строка <text></text>."
                ),
                hint="Заполните хотя бы один язык: fallback подставит его во второй.",
                owner=owner,
                field=field_ru,
            )

        for quest in project.quests.values():
            check(f"{quest.id}.title", "title_ru", "title_en", quest, "quest")
            check(f"{quest.id}.descr", "descr_ru", "descr_en", quest, "quest")
            for stage_id, stage in sorted((quest.stages or {}).items()):
                owner_id = f"{quest.id}.stage_{stage_id}"
                check(f"{owner_id}.title", "title_ru", "title_en", stage, "stage")
                check(f"{owner_id}.descr", "descr_ru", "descr_en", stage, "stage")
                for index, variant in enumerate(
                    getattr(stage, "descr_variants", None) or []
                ):
                    check(
                        f"{owner_id}.descr_variant_{index}",
                        "text_ru",
                        "text_en",
                        variant,
                        "stage",
                    )

        for dialog in project.dialogs.values():
            dialog_id = self._dialog_id(dialog)
            for phrase_id, phrase in sorted(
                (getattr(dialog, "phrases", None) or {}).items()
            ):
                check(
                    f"{dialog_id}.phrase_{phrase_id}.text",
                    "text_ru",
                    "text_en",
                    phrase,
                    "dialog",
                )

    def _add_empty_text(
        self, target_id: str, field: str, owner: str
    ) -> None:
        """Добавляет ``XRAY-LOC-001`` для пустого русского текста."""
        self.report.add(
            "XRAY-LOC-001",
            Severity.WARNING,
            target_id,
            f"Пустой текст локализации: {field}.",
            hint="Заполните русский текст, иначе в игре будет пустая строка.",
            owner=owner,
            field=field,
        )

    # ------------------------------------------------------------------
    # Data-driven уникальные meet-NPC
    # ------------------------------------------------------------------

    def _lookup_npc(self, npc_id: str) -> dict[str, Any] | None:
        """Ищет строку NPC в БД по id или алиасу."""
        if self.db is None or not npc_id:
            return None

        finder = getattr(self.db, "find_npc_by_alias", None)
        if callable(finder):
            try:
                row = finder(npc_id)
            except Exception:  # noqa: BLE001 - БД не должна ронять линтер
                row = None
            if isinstance(row, dict) and row:
                return row

        search = getattr(self.db, "search_assets", None)
        if callable(search):
            try:
                rows = search(npc_id, "npc")
            except Exception:  # noqa: BLE001
                rows = []
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                if str(row.get("id") or "") == npc_id or str(
                    row.get("alias") or ""
                ) == npc_id:
                    return row

        conn = getattr(self.db, "conn", None)
        if conn is not None:
            try:
                cursor = conn.execute(
                    "SELECT * FROM npcs WHERE id = ? LIMIT 1", (npc_id,)
                )
                row = cursor.fetchone()
            except Exception:  # noqa: BLE001
                row = None
            if row is not None:
                return dict(row) if not isinstance(row, dict) else row
        return None

    def _is_unique_meet_npc(self, npc_id: str) -> bool:
        """True, если NPC — уникальный торговец/лидер/механик из БД."""
        row = self._lookup_npc(npc_id)
        if not row:
            return False
        role = str(row.get("role") or "").strip().lower()
        if role in _UNIQUE_MEET_ROLES:
            return True
        marker = f"{npc_id} {row.get('name_ru') or ''}".lower()
        return any(token in marker for token in _UNIQUE_MEET_MARKERS)


__all__ = ["XrayLinter"]
