"""Строго типизированные модели сюжетных квестов и диалогов S.T.A.L.K.E.R. Anomaly.

Модуль является ``[1] LOAD``-слоем конвейера, описанного в
``standart_of_auto.md`` (раздел 3). Pydantic-модели:

* принимают «сырые» строки SQLite (``NULL``/``TEXT``/``INTEGER`` вперемешку)
  благодаря ``extra="allow"`` и ``coerce_numbers_to_str=True``;
* сохраняют любые неизвестные колонки БД в ``model_extra`` и не теряют их при
  сериализации;
* проверяют структурные инварианты графов реплик и этапов до того, как данные
  попадут в генераторы ``dialogs_<mod>.xml``, ``tm_<mod>.ltx`` и
  ``<mod>_quests.script``.

Модели намеренно не содержат runtime-идентификаторов отрядов: ``alife``-id
появляются только в pstor во время игры (см. ``standart_of_auto.md``, 3.3).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated, Any, Literal, Self, TypeAlias, Union

import yaml
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Общая конфигурация моделей
# ---------------------------------------------------------------------------

#: Единая конфигурация всех моделей проекта.
#:
#: * ``extra="allow"`` — колонки SQLite, которых нет в схеме, сохраняются в
#:   ``model_extra`` и не вызывают ``ValidationError`` (стандарт, 3.3.3).
#: * ``coerce_numbers_to_str=True`` — числовые server/story id из БД
#:   превращаются в строки, как того требует движок X-Ray.
#: * ``populate_by_name=True`` — позволяет создавать модели и по имени поля,
#:   и по алиасу.
#: * ``validate_assignment=True`` — изменение поля после создания снова
#:   запускает валидаторы, поэтому граф диалога/квеста нельзя испортить
#:   присваиванием.
_MODEL_CONFIG = ConfigDict(
    extra="allow",
    coerce_numbers_to_str=True,
    populate_by_name=True,
    validate_assignment=True,
)


def _normalize_optional_id(value: Any) -> Any:
    """Нормализует необязательный идентификатор перед Pydantic-валидацией.

    В SQLite идентификаторы часто хранятся как ``NULL``, пустая строка или
    число ``0``. Для игровых ссылок все три значения означают «ссылки нет».
    Функция приводит их к ``None``; остальные значения оставляет без изменения,
    чтобы ``coerce_numbers_to_str`` превратил числа в строки.

    Args:
        value (Any):
            Сырое значение из JSON, YAML или строки SQLite.

    Returns:
        Any: ``None`` для ``None``/``""``/``0``, иначе исходное значение.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return None if value == 0 else value
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _require_non_empty_id(value: Any) -> Any:
    """Проверяет обязательный идентификатор до приведения к строке.

    Args:
        value (Any):
            Сырое значение идентификатора.

    Returns:
        Any: Исходное значение, если оно не пустое.

    Raises:
        ValueError: Если идентификатор пуст, равен ``None`` или состоит из
            одних пробелов.
    """
    if value is None:
        raise ValueError("Обязательный идентификатор не может быть None.")
    if isinstance(value, str) and not value.strip():
        raise ValueError("Обязательный идентификатор не может быть пустым.")
    return value


#: Необязательный строковый идентификатор с нормализацией ``None``/``""``/``0``.
OptionalId: TypeAlias = Annotated[str | None, BeforeValidator(_normalize_optional_id)]

#: Обязательный непустой строковый идентификатор.
RequiredId: TypeAlias = Annotated[str, BeforeValidator(_require_non_empty_id)]


# ---------------------------------------------------------------------------
# Условия
# ---------------------------------------------------------------------------


class BaseCondition(BaseModel):
    """Базовое условие диалога или реплики.

    Условия транслируются генераторами в теги ``<has_info>``,
    ``<dont_has_info>`` и Lua-проверки внутри ``dialogs_<mod>.xml`` /
    ``<mod>_quests.script`` (``standart_of_auto.md``, 2.1 и 2.3).
    """

    model_config = _MODEL_CONFIG

    type: str = Field(description="Строковый дискриминатор типа условия.")


class HasInfo(BaseCondition):
    """Условие «у игрока есть инфопоршень».

    Генерирует ``<has_info>`` в XML и ``has_alife_info(...)`` в Lua.
    """

    type: Literal["has_info"] = Field(default="has_info")
    info: RequiredId = Field(description="Идентификатор информации.")


class DontHasInfo(BaseCondition):
    """Условие «у игрока нет инфопоршня».

    Генерирует ``<dont_has_info>`` в XML и ``not has_alife_info(...)`` в Lua.
    """

    type: Literal["dont_has_info"] = Field(default="dont_has_info")
    info: RequiredId = Field(description="Идентификатор информации.")


class HasItem(BaseCondition):
    """Условие «в инвентаре игрока есть предмет».

    В XML не имеет отдельного тега, поэтому выносится в Lua-предусловие
    ``dialogs.<dialog_id>_phrase_<id>_precondition``. Поле ``count`` задаёт
    минимальное требуемое количество; значение по умолчанию — один предмет.
    """

    type: Literal["has_item"] = Field(default="has_item")
    item_alias: str = Field(description="Секция/алиас предмета.")
    count: int = Field(
        default=1,
        ge=1,
        description="Минимальное количество предметов в инвентаре актора.",
    )


class HasMoney(BaseCondition):
    """Условие «у игрока достаточно денег».

    В XML не имеет отдельного тега, поэтому транслируется в Lua-проверку
    ``db.actor:money() >= amount``.
    """

    type: Literal["has_money"] = Field(default="has_money")
    amount: int = Field(ge=0, description="Минимальная сумма денег у актора.")


class SmartOwner(BaseCondition):
    """Условие «смарт-террейн принадлежит указанной фракции».

    Используется в Warfare-квестах; транслируется в Lua-проверку через
    ``SIMBOARD.smarts_by_names`` и ``smart.owning_faction``.
    """

    type: Literal["smart_owner"] = Field(default="smart_owner")
    smart_alias: str = Field(description="Алиас смарт-террейна.")
    faction: str = Field(description="Техническое имя фракции-владельца.")


Condition: TypeAlias = Annotated[
    Union[HasInfo, DontHasInfo, HasItem, HasMoney, SmartOwner],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Действия
# ---------------------------------------------------------------------------


class BaseAction(BaseModel):
    """Базовое действие квеста, этапа или реплики.

    Действия транслируются в эффекты ``xr_effects.<quest_id>_*`` и
    ``dialogs.<dialog_id>_*`` внутри ``<mod>_quests.script``, а также в
    декларативные теги ``<give_info>`` / ``<action>`` файла диалогов.
    """

    model_config = _MODEL_CONFIG

    type: str = Field(description="Строковый дискриминатор типа действия.")


class GiveInfo(BaseAction):
    """Выдать игроку инфопоршень (``<give_info>`` или Lua-вызов)."""

    type: Literal["give_info"] = Field(default="give_info")
    info: RequiredId = Field(description="Идентификатор выдаваемой информации.")


class RemoveInfo(BaseAction):
    """Снять с игрока инфопоршень."""

    type: Literal["remove_info"] = Field(default="remove_info")
    info: RequiredId = Field(description="Идентификатор удаляемой информации.")


class SpawnSquad(BaseAction):
    """Заспавнить отряд на смарт-террейне.

    В Lua использует ``SIMBOARD:create_squad`` и ``sim_squad_warfare.set_target``
    с последующей заморозкой через ``stay_time`` (``standart_of_auto.md``, 2.2).
    """

    type: Literal["spawn_squad"] = Field(default="spawn_squad")
    squad_alias: str = Field(description="Секция шаблона отряда.")
    smart_alias: str = Field(description="Алиас смарт-террейна.")


class SetTarget(BaseAction):
    """Назначить отряду цель-смарт (Warfare)."""

    type: Literal["set_target"] = Field(default="set_target")
    squad_alias: str = Field(description="Секция/алиас отряда.")
    smart_alias: str = Field(description="Алиас смарта-цели.")


class GiveItem(BaseAction):
    """Выдать предмет игроку через ``alife_create_item``.

    После выдачи ровно один раз вызывается
    ``news_manager.relocate_item(actor, "in", section, count)``: в окне диалога
    появляется иконка предмета, а в КПК — переведённое название. Секция
    разрешается из алиаса БД ещё на этапе компиляции.
    """

    type: Literal["give_item"] = Field(default="give_item")
    item_alias: str = Field(description="Секция выдаваемого предмета.")
    count: int = Field(default=1, ge=1, description="Количество предметов.")


class RemoveItem(BaseAction):
    """Изъять предмет у игрока."""

    type: Literal["remove_item"] = Field(default="remove_item")
    item_alias: str = Field(description="Секция изымаемого предмета.")
    count: int = Field(default=1, ge=1, description="Количество предметов.")


class TakeItem(BaseAction):
    """Изъять предмет у игрока (семантический алиас ``RemoveItem``).

    Удаляет предметы напрямую через ``actor:iterate_inventory`` и
    ``alife_release``. Сообщение о передаче выводится ровно один раз через
    ``news_manager.relocate_item`` и только если предмет действительно был
    изъят. Поддерживает как секции, так и алиасы БД.
    """

    type: Literal["take_item"] = Field(default="take_item")
    item_alias: str = Field(description="Секция/алиас изымаемого предмета.")
    count: int = Field(default=1, ge=1, description="Количество предметов.")


class GiveMoney(BaseAction):
    """Выдать игроку деньги (``db.actor:give_money``).

    После начисления ровно один раз вызывается
    ``news_manager.relocate_money(actor, "in", amount)``, что показывает
    стандартную иконку и сумму в окне диалога.
    """

    type: Literal["give_money"] = Field(default="give_money")
    amount: int = Field(ge=0, description="Сумма в игровой валюте.")


class TakeMoney(BaseAction):
    """Списать деньги у игрока.

    Сумма ограничивается текущим балансом, чтобы ``give_money`` не ушёл в
    отрицательное значение.
    """

    type: Literal["take_money"] = Field(default="take_money")
    amount: int = Field(ge=0, description="Списываемая сумма в игровой валюте.")


class GiveTask(BaseAction):
    """Выдать игроку задачу из ``task_manager``.

    В XML превращается в ``<action>dialogs.<task_id>_accept</action>``.
    """

    type: Literal["give_task"] = Field(default="give_task")
    task_id: RequiredId = Field(description="ID задачи (``Quest.id``).")


class CompleteTask(BaseAction):
    """Завершить задачу через ``task_manager``.

    В XML превращается в ``<action>dialogs.<task_id>_turn_in</action>``.
    """

    type: Literal["complete_task"] = Field(default="complete_task")
    task_id: RequiredId = Field(description="ID задачи (``Quest.id``).")


Action: TypeAlias = Annotated[
    Union[
        GiveInfo,
        RemoveInfo,
        SpawnSquad,
        SetTarget,
        GiveItem,
        RemoveItem,
        TakeItem,
        GiveMoney,
        TakeMoney,
        GiveTask,
        CompleteTask,
    ],
    Field(discriminator="type"),
]


def phrase_action_mode(actions: Iterable[BaseAction]) -> str | None:
    """Определяет, какой ровно один ``<action>`` нужен реплике.

    Движок X-Ray/OpenXRay исполняет только **один** тег ``<action>`` на
    ``<phrase>``; все последующие теги молча отбрасываются. Поэтому
    генераторы обязаны сводить действия реплики к одному тегу:

    * ``"accept"`` — единственное действие ``GiveTask``; XML ссылается на
      ``dialogs.<dialog_id>_accept``;
    * ``"turn_in"`` — единственное действие ``CompleteTask``; XML ссылается
      на ``dialogs.<dialog_id>_turn_in``;
    * ``"combined"`` — любая другая комбинация Lua-действий (включая
      ``GiveTask``/``CompleteTask`` вместе с наградами); XML ссылается на
      единую функцию ``dialogs.<dialog_id>_phrase_<n>_action``;
    * ``None`` — Lua-действий нет (остались только ``GiveInfo``).

    ``GiveInfo`` не считается Lua-действием: он остаётся нативным
    XML-тегом ``<give_info>`` и не участвует в слиянии.

    Args:
        actions (Iterable[BaseAction]): Действия реплики в порядке объявления.

    Returns:
        str | None: ``"accept"``, ``"turn_in"``, ``"combined"`` или ``None``.
    """
    lua_actions = [
        action for action in actions if not isinstance(action, GiveInfo)
    ]
    if not lua_actions:
        return None
    if len(lua_actions) == 1:
        only = lua_actions[0]
        if isinstance(only, GiveTask):
            return "accept"
        if isinstance(only, CompleteTask):
            return "turn_in"
    return "combined"


# ---------------------------------------------------------------------------
# Диалоги
# ---------------------------------------------------------------------------


class Phrase(BaseModel):
    """Одна реплика внутри дерева диалога.

    Реплики попадают в ``dialogs_<mod>.xml`` как ``<phrase id="N">`` с
    ``<text>``, ``<next>``, ``<precondition>`` и ``<action>``. Тексты
    выносятся в ``text/rus|eng/st_<mod>.xml`` под id
    ``<dialog_id>_phrase_<id>_text``.
    """

    model_config = _MODEL_CONFIG

    id: int = Field(ge=0, description="Целочисленный id реплики внутри диалога.")
    text_ru: str = Field(default="", description="Русский текст реплики.")
    text_en: str = Field(default="", description="Английский текст реплики.")
    next_phrases: list[int] = Field(
        default_factory=list,
        description="Список id следующих реплик (теги <next>).",
    )
    preconditions: list[Condition] = Field(
        default_factory=list,
        description="Условия показа реплики.",
    )
    actions: list[Action] = Field(
        default_factory=list,
        description="Действия при выборе реплики.",
    )


class Dialog(BaseModel):
    """Диалог NPC-квестодателя с деревом реплик.

    Объект генерирует блок ``<dialog id="...">`` в
    ``gamedata/configs/gameplay/dialogs_<mod>.xml`` и функции
    ``dialogs.<dialog_id>_*`` в ``gamedata/scripts/<mod>_quests.script``.
    Идентификатор ``dialog_id`` всегда синхронизирован с ``id`` и именно он
    попадает в ``<actor_dialog>`` при патче ``character_desc_<level>.xml``.
    """

    model_config = _MODEL_CONFIG

    id: RequiredId = Field(description="ID диалога (значение <actor_dialog>).")
    dialog_id: OptionalId = Field(
        default=None,
        description="Дублирующий ID диалога; синхронизируется с id.",
    )
    npc_alias: str = Field(default="", description="Человекочитаемый алиас NPC.")
    npc_id: OptionalId = Field(
        default=None,
        description="Игровой ID профиля NPC (specific_character id).",
    )
    npc_location: str | None = Field(
        default=None,
        description=(
            "Имя локации NPC (escape, zaton, jupiter, ...). Используется "
            "патчером для выбора character_desc_<level>.xml."
        ),
    )
    task_id: OptionalId = Field(
        default=None,
        description="ID связанного квеста (Quest.id) для ролей take/turn-in.",
    )
    role: str | None = Field(
        default=None,
        description=(
            "Роль диалога в сценарии: take, take_assault, take_solo, turnin, "
            "branch. Влияет только на порядок вставки <actor_dialog>."
        ),
    )
    preconditions: list[Condition] = Field(
        default_factory=list,
        description="Условия доступности всего диалога.",
    )
    phrases: dict[int, Phrase] = Field(
        default_factory=dict,
        description="Карта реплик: ключ обязан совпадать с Phrase.id.",
    )

    @field_validator("id", mode="before")
    @classmethod
    def _validate_id(cls, value: Any) -> Any:
        """Проверяет, что id диалога не пуст.

        Args:
            value (Any): Сырое значение идентификатора.

        Returns:
            Any: Исходное значение для дальнейшей валидации.
        """
        return _require_non_empty_id(value)

    @field_validator("npc_location", mode="before")
    @classmethod
    def _normalize_location(cls, value: Any) -> Any:
        """Приводит пустую локацию диалога к ``None``.

        Args:
            value (Any): Сырое значение локации.

        Returns:
            Any: Очищенная строка или ``None``.
        """
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def _sync_dialog_id(self) -> Self:
        """Синхронизирует ``dialog_id`` с каноническим ``id``.

        ``validate_assignment=True`` может повторно вызывать валидатор после
        присваивания, поэтому запись выполняется через ``object.__setattr__``,
        чтобы не запустить бесконечную рекурсию.

        Returns:
            Self: Этот же диалог с заполненным ``dialog_id``.
        """
        object.__setattr__(self, "dialog_id", self.id)
        return self

    @model_validator(mode="after")
    def _validate_phrase_graph(self) -> Self:
        """Проверяет связность дерева реплик.

        Требования ``standart_of_auto.md`` (2.1): стартовая реплика ``id=0``
        обязательна, ключ карты совпадает с ``Phrase.id``, а каждый
        ``<next>`` ссылается на существующую реплику.

        Returns:
            Self: Валидный диалог.

        Raises:
            ValueError: Если граф реплик нарушен.
        """
        if not self.phrases:
            raise ValueError(
                f"Диалог '{self.id}' не содержит ни одной фразы; "
                "требуется стартовая фраза с id=0."
            )
        if 0 not in self.phrases:
            raise ValueError(
                f"Диалог '{self.id}' должен содержать стартовую фразу с ключом id=0."
            )
        phrase_ids = set(self.phrases)
        for phrase_key, phrase in self.phrases.items():
            if phrase_key != phrase.id:
                raise ValueError(
                    f"Диалог '{self.id}': ключ фразы {phrase_key} не совпадает "
                    f"с Phrase.id={phrase.id}."
                )
            for target_id in phrase.next_phrases:
                if target_id not in phrase_ids:
                    raise ValueError(
                        f"Диалог '{self.id}', фраза id={phrase.id}: "
                        f"next_phrases ссылается на несуществующую фразу id={target_id}."
                    )
        return self


# ---------------------------------------------------------------------------
# Квесты
# ---------------------------------------------------------------------------


class WarfareCapture(BaseModel):
    """Warfare-сценарий этапа: захватить смарт, уничтожив вражеский отряд.

    Данные попадают в статическую таблицу ``QUESTS`` Lua-скрипта и
    используются хелперами ``spawn_stage_for`` / ``stage_cleared``.
    """

    model_config = _MODEL_CONFIG

    smart_alias: str = Field(
        description="Алиас смарт-террейна, который нужно захватить."
    )
    enemy_squad_alias: str = Field(
        description="Секция вражеского отряда, который нужно уничтожить."
    )
    ally_squad_alias: str | None = Field(
        default=None,
        description="Секция союзного отряда, который спавнится на помощь.",
    )
    ally_count: int = Field(
        default=0,
        ge=0,
        description="Сколько союзных отрядов заспавнить (0 — без союзников).",
    )


class Stage(BaseModel):
    """Один этап квеста.

    Этапы нумеруются подряд с нуля; каждый этап даёт описание
    ``<quest_id>_stage_<id>_descr`` в ``st_<mod>.xml`` и цель для
    ``target_functor`` в ``tm_<mod>.ltx``.
    """

    model_config = _MODEL_CONFIG

    id: int = Field(ge=0, description="Номер этапа (0..N-1).")
    title_ru: str = Field(default="", description="Русский заголовок этапа.")
    title_en: str = Field(default="", description="Английский заголовок этапа.")
    msg_complete_ru: str | None = Field(
        default=None,
        description=(
            "Текст уведомления КПК при завершении этапа. Если не задан, "
            "генерируется 'Этап выполнен: <title_ru>.'"
        ),
    )
    msg_complete_en: str | None = Field(
        default=None,
        description=(
            "PDA notification text shown when the stage is completed. "
            "Defaults to 'Stage completed: <title_en>.'"
        ),
    )
    descr_ru: str = Field(default="", description="Русское описание этапа.")
    descr_en: str = Field(default="", description="Английское описание этапа.")
    target_alias: str = Field(
        default="",
        description="Алиас смарта/NPC/предмета для маркера цели.",
    )
    target_squad_id: str | None = Field(
        default=None,
        description=(
            "ID/секция/алиас отряда, который нужно физически уничтожить на "
            "этом этапе. При заданном значении status_functor автоматически "
            "проверяет отряд через alife()/SIMBOARD и продвигает этап."
        ),
    )
    on_start_actions: list[Action] = Field(
        default_factory=list,
        description="Действия, выполняемые при входе в этап.",
    )
    warfare_capture: WarfareCapture | None = Field(
        default=None,
        description=(
            "Если задано — Lua-генератор создаст логику захвата смарта: "
            "спавн, заморозку и проверку зачистки."
        ),
    )


class Quest(BaseModel):
    """Сюжетный квест, транслируемый в LTX и Lua.

    Объект генерирует секцию ``[<quest_id>]`` в
    ``gamedata/configs/misc/task/tm_<mod>.ltx`` и набор плоских функций
    ``<quest_id>_target``, ``<quest_id>_descr``, ``<quest_id>_status``,
    ``<quest_id>_start``, ``<quest_id>_reward``, ``<quest_id>_cleanup`` в
    ``gamedata/scripts/<mod>_quests.script``.
    """

    model_config = _MODEL_CONFIG

    id: RequiredId = Field(description="ID секции LTX и ключ task_functor.")
    giver_npc_id: OptionalId = Field(
        default=None,
        description="Игровой/стори-ID NPC-квестодателя (устаревшее имя npc_id).",
    )
    npc_id: OptionalId = Field(
        default=None,
        description="Игровой ID NPC-квестодателя для task_giver_alive.",
    )
    npc_location: str | None = Field(
        default=None,
        description=(
            "Локация квестодателя (escape, zaton, ...). Используется "
            "патчером character_desc_<level>.xml."
        ),
    )
    dialog_id: OptionalId = Field(
        default=None,
        description="ID основного диалога выдачи квеста.",
    )
    dialog_ids: list[str] = Field(
        default_factory=list,
        description="ID связанных диалогов (выдача/сдача).",
    )
    title_ru: str = Field(default="", description="Русское название квеста.")
    title_en: str = Field(default="", description="Английское название квеста.")
    descr_ru: str = Field(default="", description="Русское описание квеста.")
    descr_en: str = Field(default="", description="Английское описание квеста.")
    msg_reward_ru: str | None = Field(
        default=None,
        description=(
            "Русский текст PDA-подсказки при завершении квеста. Если не "
            "задан, генерируется 'Задание выполнено: <title_ru>.'"
        ),
    )
    msg_reward_en: str | None = Field(
        default=None,
        description=(
            "Английский текст PDA-подсказки при завершении квеста. Если не "
            "задан, генерируется 'Task completed: <title_en>.'"
        ),
    )
    msg_fail_ru: str | None = Field(
        default=None,
        description=(
            "Русский текст PDA-подсказки при провале/отмене квеста. Если не "
            "задан, генерируется 'Задание провалено: <title_ru>.'"
        ),
    )
    msg_fail_en: str | None = Field(
        default=None,
        description=(
            "Английский текст PDA-подсказки при провале/отмене квеста. Если "
            "не задан, генерируется 'Task failed: <title_en>.'"
        ),
    )
    is_storyline: bool = Field(default=True, description="Признак сюжетности.")
    icon: str | None = Field(default=None, description="Иконка PDA (ui_inGame2_...).")
    prior: int | None = Field(default=None, ge=0, description="Приоритет в PDA.")
    stages: dict[int, Stage] = Field(
        default_factory=dict,
        description="Карта этапов: ключ обязан совпадать с Stage.id.",
    )
    on_init_actions: list[Action] = Field(
        default_factory=list,
        description="Действия эффекта <quest_id>_start.",
    )
    on_complete_actions: list[Action] = Field(
        default_factory=list,
        description="Действия эффекта <quest_id>_reward.",
    )
    on_fail_actions: list[Action] = Field(
        default_factory=list,
        description="Действия эффекта <quest_id>_cleanup.",
    )
    transfer_conditions: dict[int, dict[str, list[Condition]]] = Field(
        default_factory=dict,
        description=(
            "Правила перехода этапов: {stage: {'complete': [...], "
            "'fail': [...]}}. Транслируются в status_functor."
        ),
    )

    reward_money: int | None = Field(default=None, ge=0)
    reward_item_alias: str | None = Field(default=None)
    reward_item_count: int = Field(default=1, ge=1)
    complete_info: str | None = Field(
        default=None,
        description="Инфопоршень, выдаваемый при завершении квеста.",
    )
    taken_info: str | None = Field(
        default=None,
        description="Инфопоршень, выдаваемый при выдаче квеста.",
    )
    cleanup_infos: list[str] = Field(
        default_factory=list,
        description=(
            "Инфопоршни, которые снимаются в конце _reward и в _cleanup. "
            "Используется для взаимоисключающих вариантов (assault/solo) и "
            "прочих временных маркеров; taken_info/complete_info не входят."
        ),
    )
    return_to_giver_stage: int | None = Field(
        default=None,
        description="Этап, на котором игрок должен вернуться к квестодателю.",
    )
    return_distance: float = Field(
        default=40.0,
        ge=0,
        description="Радиус «подошёл к квестодателю» в метрах.",
    )
    available_info: str | None = Field(default=None)
    done_info: str | None = Field(default=None)
    requires_faction: str | None = Field(
        default=None,
        description=(
            "Техническое имя фракции игрока (например, 'army'), при которой "
            "квест доступен. Проверяется в <dialog_id>_can_take через "
            "is_actor_faction()."
        ),
    )
    requires_warfare: bool = Field(
        default=False,
        description=(
            "Если True — квест доступен и работает только в режиме Warfare: "
            "_can_take проверяет is_warfare(), а _start/_status не выполняются "
            "вне Warfare (наравне с world)."
        ),
    )

    @field_validator("id", mode="before")
    @classmethod
    def _validate_id(cls, value: Any) -> Any:
        """Проверяет, что id квеста не пуст.

        Args:
            value (Any): Сырое значение идентификатора.

        Returns:
            Any: Исходное значение для дальнейшей валидации.
        """
        return _require_non_empty_id(value)

    @field_validator("npc_location", mode="before")
    @classmethod
    def _normalize_location(cls, value: Any) -> Any:
        """Приводит пустую локацию к ``None``.

        Args:
            value (Any): Сырое значение локации.

        Returns:
            Any: Очищенная строка или ``None``.
        """
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def _validate_stage_sequence(self) -> Self:
        """Проверяет непрерывную нумерацию этапов с нуля.

        Returns:
            Self: Валидный квест.

        Raises:
            ValueError: Если этапы пусты или пронумерованы с пропусками.
        """
        if not self.stages:
            raise ValueError(
                f"Квест '{self.id}' должен содержать хотя бы один этап (этап с id=0)."
            )
        actual_keys = sorted(self.stages)
        expected_keys = list(range(len(self.stages)))
        if actual_keys != expected_keys:
            raise ValueError(
                f"Этапы квеста '{self.id}' должны быть пронумерованы подряд с 0. "
                f"Ожидались ключи {expected_keys}, получены {actual_keys}."
            )
        for stage_key, stage in self.stages.items():
            if stage_key != stage.id:
                raise ValueError(
                    f"Квест '{self.id}': ключ этапа {stage_key} не совпадает "
                    f"с Stage.id={stage.id}."
                )
            if self.return_to_giver_stage is not None:
                if self.return_to_giver_stage not in self.stages:
                    raise ValueError(
                        f"Квест '{self.id}': return_to_giver_stage="
                        f"{self.return_to_giver_stage} отсутствует в stages."
                    )
        return self


# ---------------------------------------------------------------------------
# Корневой проект
# ---------------------------------------------------------------------------


class CustomSquad(BaseModel):
    """Кастомная секция отряда для ``squad_descr_<slug>.ltx``.

    Движок автоматически подключает любой файл
    ``gamedata/configs/misc/squad_descr/squad_descr_*.ltx`` через глоб в
    ванильном ``squad_descr.ltx``, поэтому ``system.ltx`` патчить не нужно.

    Секция ``[<id>]:online_offline_group`` позволяет объявить уникальный
    квестовый отряд, который симуляция Warfare не создаёт сама.
    """

    model_config = _MODEL_CONFIG

    id: RequiredId = Field(
        description=(
            "Имя секции отряда, например 'mymod_atp_bandit_leader_squad'."
        )
    )
    faction: str = Field(
        description="Фракция отряда, например 'bandit' или 'army'."
    )
    npc: list[str] = Field(
        min_length=1,
        description=(
            "Непустой список секций NPC, например ['sim_default_bandit_4']."
        ),
    )
    target_smart: str | None = Field(
        default=None,
        description="Опциональный target_smart секции отряда.",
    )
    story_id: str | None = Field(
        default=None,
        description="Опциональный story_id секции отряда.",
    )


class ModProject(BaseModel):
    """Корневой проект мода: имя, зависимости, квесты и диалоги.

    Это ``[1] LOAD``-контейнер конвейера. Генераторы получают из него данные
    для ``tm_<mod>.ltx``, ``dialogs_<mod>.xml``, ``st_<mod>.xml`` и
    ``<mod>_quests.script``, а патчер — список NPC для
    ``character_desc_<level>.xml``.
    """

    model_config = _MODEL_CONFIG

    name: str = Field(description="Человекочитаемое имя проекта.")
    required_mods: list[str] = Field(
        default_factory=list,
        description="Список обязательных модов/баз.",
    )
    quests: dict[str, Quest] = Field(
        default_factory=dict,
        description="Карта квестов: ключ обязан совпадать с Quest.id.",
    )
    dialogs: dict[str, Dialog] = Field(
        default_factory=dict,
        description="Карта диалогов: ключ может отличаться от Dialog.id.",
    )
    squads: dict[str, CustomSquad] = Field(
        default_factory=dict,
        description=(
            "Кастомные секции отрядов: ключ обязан совпадать с "
            "CustomSquad.id. При непустой карте сборщик создаёт "
            "squad_descr_<slug>.ltx."
        ),
    )

    @model_validator(mode="after")
    def _validate_cross_references(self) -> Self:
        """Проверяет сквозные связи quest ↔ dialog ↔ task.

        Проверяются только явно заданные ссылки, чтобы «сырая» строка SQLite
        без части колонок не роняла конвейер.

        Returns:
            Self: Проект с корректными ссылками.

        Raises:
            ValueError: Если квест ссылается на отсутствующий диалог или
                диалог ссылается на отсутствующий квест.
        """
        for quest_key, quest in self.quests.items():
            if quest_key != quest.id:
                raise ValueError(
                    f"Ключ карты квестов '{quest_key}' не совпадает "
                    f"с Quest.id='{quest.id}'."
                )
            referenced = list(quest.dialog_ids)
            if quest.dialog_id:
                referenced.append(quest.dialog_id)
            for dialog_id in referenced:
                if dialog_id not in self.dialogs:
                    raise ValueError(
                        f"Квест '{quest.id}' ссылается на отсутствующий "
                        f"диалог '{dialog_id}'."
                    )
        for dialog in self.dialogs.values():
            if dialog.task_id and dialog.task_id not in self.quests:
                raise ValueError(
                    f"Диалог '{dialog.id}' ссылается на отсутствующий "
                    f"квест '{dialog.task_id}'."
                )
        for squad_key, squad in self.squads.items():
            if squad_key != squad.id:
                raise ValueError(
                    f"Ключ карты отрядов '{squad_key}' не совпадает "
                    f"с CustomSquad.id='{squad.id}'."
                )
        return self

    def to_json(self) -> str:
        """Сериализует проект в JSON, сохраняя ``model_extra``.

        Returns:
            str: JSON-представление проекта с отступом в два пробела.
        """
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "ModProject":
        """Восстанавливает проект из JSON.

        Args:
            json_str (str): JSON-строка, созданная :meth:`to_json`.

        Returns:
            ModProject: Валидный проект мода.
        """
        return cls.model_validate_json(json_str)

    def to_yaml(self) -> str:
        """Сериализует проект в YAML.

        Returns:
            str: YAML-представление с сохранением Unicode.
        """
        data = self.model_dump(mode="python")
        return yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            indent=2,
        )

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "ModProject":
        """Восстанавливает проект из YAML.

        Args:
            yaml_str (str): YAML-строка, созданная :meth:`to_yaml`.

        Returns:
            ModProject: Валидный проект мода.
        """
        data = yaml.safe_load(yaml_str)
        return cls.model_validate(data)


# ---------------------------------------------------------------------------
# Перекрёстные проверки проекта
# ---------------------------------------------------------------------------


def find_phrase_reward_conflicts(project: ModProject) -> list[str]:
    """Находит рискованную выдачу награды прямо в реплике сдачи.

    Если в одной реплике есть ``CompleteTask`` и одновременно ``GiveMoney``
    или ``GiveItem``, а у связанного квеста пусты
    ``Quest.reward_money``/``Quest.reward_item_alias``, награда может быть
    потеряна: движок исполняет только один ``<action>`` и/или
    ``CompleteTask`` завершает задачу раньше остальных эффектов. Надёжный
    путь — перенести награду в ``Quest.reward_money``/
    ``Quest.reward_item_alias`` либо в ``Quest.on_complete_actions``.

    Функция не меняет проект и не бросает исключений: она возвращает
    человекочитаемые описания конфликтов для предупреждения в лог сборки.

    Args:
        project (ModProject): Проект мода.

    Returns:
        list[str]: Описания реплик с потенциально потерянной наградой.
    """
    conflicts: list[str] = []
    quests = getattr(project, "quests", {}) or {}
    dialogs = getattr(project, "dialogs", {}) or {}

    for dialog in dialogs.values():
        dialog_id = (
            getattr(dialog, "dialog_id", None)
            or getattr(dialog, "id", None)
            or "<unknown>"
        )
        quest = quests.get(getattr(dialog, "task_id", None) or "")
        if quest is None:
            for candidate in quests.values():
                if dialog_id in (
                    getattr(candidate, "dialog_id", None),
                    *getattr(candidate, "dialog_ids", []),
                ):
                    quest = candidate
                    break
        if quest is None:
            continue
        if (
            getattr(quest, "reward_money", None)
            or getattr(quest, "reward_item_alias", None)
        ):
            continue

        for phrase_id, phrase in sorted(
            (getattr(dialog, "phrases", {}) or {}).items()
        ):
            actions = list(getattr(phrase, "actions", []) or [])
            if not any(isinstance(a, CompleteTask) for a in actions):
                continue
            inline = [
                type(action).__name__
                for action in actions
                if isinstance(action, (GiveMoney, GiveItem))
            ]
            if inline:
                conflicts.append(
                    f"диалог '{dialog_id}', реплика {phrase_id}: "
                    f"{', '.join(sorted(set(inline)))} вместе с "
                    "CompleteTask, а Quest.reward_money/"
                    "reward_item_alias пусты"
                )
    return conflicts


__all__ = [
    "Action",
    "BaseAction",
    "BaseCondition",
    "CompleteTask",
    "Condition",
    "CustomSquad",
    "Dialog",
    "DontHasInfo",
    "find_phrase_reward_conflicts",
    "GiveInfo",
    "GiveItem",
    "GiveMoney",
    "GiveTask",
    "HasInfo",
    "HasItem",
    "ModProject",
    "OptionalId",
    "Phrase",
    "phrase_action_mode",
    "Quest",
    "RemoveInfo",
    "RemoveItem",
    "RequiredId",
    "SetTarget",
    "SmartOwner",
    "SpawnSquad",
    "Stage",
    "WarfareCapture",
]
