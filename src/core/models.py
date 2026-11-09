"""Строго типизированные модели сюжетных квестов и диалогов S.T.A.L.K.E.R. Anomaly.

Модуль содержит только предметную модель редактора: условия, действия,
реплики, диалоги, этапы, квесты и корневой проект мода. Здесь нет логики
сборки игровых файлов (LTX/XML/Lua) — она вынесена в слой ``src.compiler``.

Полиморфизм условий и действий реализован через дискриминируемые объединения
Pydantic. Каждый конкретный класс содержит литеральное поле ``type``, которое
выступает дискриминатором при чтении JSON/YAML:

* условия: ``has_info``, ``dont_has_info``, ``has_item``, ``smart_owner``;
* действия: ``give_info``, ``remove_info``, ``spawn_squad``, ``set_target``,
  ``give_item``, ``remove_item``, ``give_money``.

Пример создания минимального диалога::

    dialog = Dialog(
        id="mymod_start_dialog",
        npc_alias="esc.mayor_zhurov",
        phrases={
            0: Phrase(id=0, text_ru="Здравствуй.", text_en="Hello."),
            1: Phrase(id=1, text_ru="До встречи.", text_en="See you."),
        },
    )

Все модели используют ``extra="forbid"``: опечатка в имени поля приводит к
ошибке валидации, а не к молчаливой потере данных. Для графов фраз и этапов
дополнительно проверяются ссылочная целостность и непрерывность нумерации.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self, TypeAlias, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Общая конфигурация всех моделей модуля.
#:
#: ``extra="forbid"`` запрещает неизвестные поля, ``validate_assignment=True``
#: повторно запускает валидаторы при присваивании значений атрибутам.
_MODEL_CONFIG = ConfigDict(extra="forbid", validate_assignment=True)


# ---------------------------------------------------------------------------
# Условия
# ---------------------------------------------------------------------------


class BaseCondition(BaseModel):
    """Базовый класс условия доступности диалога или отдельной реплики.

    Класс не предназначен для прямого создания: в модели используются его
    наследники, объединённые в дискриминируемый псевдоним :data:`Condition`.
    Поле :attr:`type` является строковым дискриминатором и должно совпадать
    с литеральным значением конкретного наследника.

    Attributes:
        type (str):
            Идентификатор типа условия. В конкретных наследниках сужается до
            ``Literal``, например ``"has_info"`` или ``"has_item"``.
    """

    model_config = _MODEL_CONFIG

    type: str = Field(
        description=(
            "Строковый дискриминатор типа условия. Определяется конкретным "
            "наследником BaseCondition."
        )
    )


class HasInfo(BaseCondition):
    """Условие: у актора есть указанный информационный портфель.

    Attributes:
        type (Literal["has_info"]):
            Дискриминатор условия, всегда ``"has_info"``.
        info (str):
            Идентификатор информации (info portion), наличие которой
            проверяется у актора.
    """

    type: Literal["has_info"] = Field(
        default="has_info",
        description="Дискриминатор условия: наличие информации у актора.",
    )
    info: str = Field(
        description="Идентификатор информации, наличие которой проверяется.",
    )


class DontHasInfo(BaseCondition):
    """Условие: у актора отсутствует указанный информационный портфель.

    Attributes:
        type (Literal["dont_has_info"]):
            Дискриминатор условия, всегда ``"dont_has_info"``.
        info (str):
            Идентификатор информации, отсутствие которой проверяется.
    """

    type: Literal["dont_has_info"] = Field(
        default="dont_has_info",
        description="Дискриминатор условия: отсутствие информации у актора.",
    )
    info: str = Field(
        description="Идентификатор информации, отсутствие которой проверяется.",
    )


class HasItem(BaseCondition):
    """Условие: в инвентаре актора есть указанный предмет.

    Attributes:
        type (Literal["has_item"]):
            Дискриминатор условия, всегда ``"has_item"``.
        item_alias (str):
            Алиас предмета из игровой базы данных, например
            ``"weapon.vssk_vykhlop"``.
    """

    type: Literal["has_item"] = Field(
        default="has_item",
        description="Дискриминатор условия: наличие предмета у актора.",
    )
    item_alias: str = Field(
        description="Алиас предмета, наличие которого проверяется.",
    )


class SmartOwner(BaseCondition):
    """Условие: смарт-террейн принадлежит указанной фракции.

    Attributes:
        type (Literal["smart_owner"]):
            Дискриминатор условия, всегда ``"smart_owner"``.
        smart_alias (str):
            Алиас смарт-террейна из игровой базы данных.
        faction (str):
            Техническое имя фракции, которая должна владеть смартом,
            например ``"army"`` или ``"stalker"``.
    """

    type: Literal["smart_owner"] = Field(
        default="smart_owner",
        description="Дискриминатор условия: принадлежность смарта фракции.",
    )
    smart_alias: str = Field(
        description="Алиас проверяемого смарт-террейна.",
    )
    faction: str = Field(
        description="Техническое имя фракции-владельца смарта.",
    )


#: Дискриминируемое объединение всех поддерживаемых условий.
#:
#: Pydantic выбирает конкретный класс по значению поля ``type``. Именно этот
#: псевдоним следует использовать в полях ``preconditions``.
Condition: TypeAlias = Annotated[
    Union[HasInfo, DontHasInfo, HasItem, SmartOwner],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Действия
# ---------------------------------------------------------------------------


class BaseAction(BaseModel):
    """Базовый класс действия, выполняемого игрой при событии квеста.

    Класс не предназначен для прямого создания: в модели используются его
    наследники, объединённые в дискриминируемый псевдоним :data:`Action`.
    Поле :attr:`type` является строковым дискриминатором и должно совпадать
    с литеральным значением конкретного наследника.

    Attributes:
        type (str):
            Идентификатор типа действия. В конкретных наследниках сужается до
            ``Literal``, например ``"give_info"`` или ``"give_money"``.
    """

    model_config = _MODEL_CONFIG

    type: str = Field(
        description=(
            "Строковый дискриминатор типа действия. Определяется конкретным "
            "наследником BaseAction."
        )
    )


class GiveInfo(BaseAction):
    """Действие: выдать актору информационный портфель.

    Attributes:
        type (Literal["give_info"]):
            Дискриминатор действия, всегда ``"give_info"``.
        info (str):
            Идентификатор выдаваемой информации.
    """

    type: Literal["give_info"] = Field(
        default="give_info",
        description="Дискриминатор действия: выдача информации.",
    )
    info: str = Field(
        description="Идентификатор выдаваемой информации.",
    )


class RemoveInfo(BaseAction):
    """Действие: забрать у актора информационный портфель.

    Attributes:
        type (Literal["remove_info"]):
            Дискриминатор действия, всегда ``"remove_info"``.
        info (str):
            Идентификатор удаляемой информации.
    """

    type: Literal["remove_info"] = Field(
        default="remove_info",
        description="Дискриминатор действия: удаление информации.",
    )
    info: str = Field(
        description="Идентификатор удаляемой информации.",
    )


class SpawnSquad(BaseAction):
    """Действие: заспавнить отряд в указанном смарт-террейне.

    Attributes:
        type (Literal["spawn_squad"]):
            Дискриминатор действия, всегда ``"spawn_squad"``.
        squad_alias (str):
            Алиас шаблона отряда из игровой базы данных.
        smart_alias (str):
            Алиас смарт-террейна, в котором должен появиться отряд.
    """

    type: Literal["spawn_squad"] = Field(
        default="spawn_squad",
        description="Дискриминатор действия: спавн отряда.",
    )
    squad_alias: str = Field(
        description="Алиас шаблона спавнимого отряда.",
    )
    smart_alias: str = Field(
        description="Алиас смарт-террейна для спавна отряда.",
    )


class SetTarget(BaseAction):
    """Действие: назначить отряду цель в виде смарт-террейна.

    Attributes:
        type (Literal["set_target"]):
            Дискриминатор действия, всегда ``"set_target"``.
        squad_alias (str):
            Алиас отряда, которому назначается цель.
        smart_alias (str):
            Алиас смарт-террейна, выступающего целью.
    """

    type: Literal["set_target"] = Field(
        default="set_target",
        description="Дискриминатор действия: назначение цели отряду.",
    )
    squad_alias: str = Field(
        description="Алиас отряда, которому назначается цель.",
    )
    smart_alias: str = Field(
        description="Алиас смарт-террейна-цели.",
    )


class GiveItem(BaseAction):
    """Действие: выдать актору предмет.

    Attributes:
        type (Literal["give_item"]):
            Дискриминатор действия, всегда ``"give_item"``.
        item_alias (str):
            Алиас выдаваемого предмета из игровой базы данных.
    """

    type: Literal["give_item"] = Field(
        default="give_item",
        description="Дискриминатор действия: выдача предмета.",
    )
    item_alias: str = Field(
        description="Алиас выдаваемого предмета.",
    )


class RemoveItem(BaseAction):
    """Действие: забрать у актора предмет.

    Attributes:
        type (Literal["remove_item"]):
            Дискриминатор действия, всегда ``"remove_item"``.
        item_alias (str):
            Алиас изымаемого предмета из игровой базы данных.
    """

    type: Literal["remove_item"] = Field(
        default="remove_item",
        description="Дискриминатор действия: изъятие предмета.",
    )
    item_alias: str = Field(
        description="Алиас изымаемого предмета.",
    )


class GiveMoney(BaseAction):
    """Действие: изменить количество денег у актора.

    Attributes:
        type (Literal["give_money"]):
            Дискриминатор действия, всегда ``"give_money"``.
        amount (int):
            Сумма в игровой валюте. Неотрицательное целое число; для списания
            денег используйте отдельное действие в будущих расширениях.
    """

    type: Literal["give_money"] = Field(
        default="give_money",
        description="Дискриминатор действия: выдача денег.",
    )
    amount: int = Field(
        ge=0,
        description="Неотрицательная сумма в игровой валюте.",
    )


#: Дискриминируемое объединение всех поддерживаемых действий.
#:
#: Pydantic выбирает конкретный класс по значению поля ``type``. Именно этот
#: псевдоним следует использовать в полях ``actions`` и ``*_actions``.
Action: TypeAlias = Annotated[
    Union[
        GiveInfo,
        RemoveInfo,
        SpawnSquad,
        SetTarget,
        GiveItem,
        RemoveItem,
        GiveMoney,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Диалоги
# ---------------------------------------------------------------------------


class Phrase(BaseModel):
    """Одна реплика в дереве диалога.

    Реплика с ``id=0`` всегда является стартовой фразой актора. Остальные
    реплики могут ссылаться друг на друга через :attr:`next_phrases`;
    ссылочная целостность проверяется на уровне :class:`Dialog`.

    Attributes:
        id (int):
            Уникальный идентификатор реплики внутри диалога. Должен быть
            неотрицательным; значение ``0`` зарезервировано за стартовой
            фразой актора.
        text_ru (str):
            Русский текст реплики для файла ``st_mymod.xml``.
        text_en (str):
            Английский текст реплики. Обязателен, поскольку игра может быть
            запущена с ``language=eng``.
        next_phrases (list[int]):
            Идентификаторы реплик, к которым можно перейти после этой фразы.
        preconditions (list[Condition]):
            Условия доступности данной реплики. Пустой список означает, что
            реплика доступна всегда.
        actions (list[Action]):
            Эффекты, выполняемые при выборе данной реплики.
    """

    model_config = _MODEL_CONFIG

    id: int = Field(
        ge=0,
        description=(
            "Уникальный id реплики внутри диалога; 0 — стартовая фраза актора."
        ),
    )
    text_ru: str = Field(
        description="Текст реплики на русском языке.",
    )
    text_en: str = Field(
        description="Текст реплики на английском языке.",
    )
    next_phrases: list[int] = Field(
        default_factory=list,
        description="Идентификаторы доступных следующих реплик.",
    )
    preconditions: list[Condition] = Field(
        default_factory=list,
        description="Условия доступности реплики.",
    )
    actions: list[Action] = Field(
        default_factory=list,
        description="Действия, выполняемые при выборе реплики.",
    )


class Dialog(BaseModel):
    """Диалог NPC-квестодателя с деревом реплик.

    Модель проверяет два инварианта графа:

    1. в :attr:`phrases` присутствует стартовая реплика с ключом и ``id``,
       равными ``0``;
    2. каждый идентификатор из ``next_phrases`` ссылается на существующую
       реплику этого же диалога.

    Дополнительно ключ словаря ``phrases`` должен совпадать с полем
    ``Phrase.id``, чтобы сериализация не создавала двух разных представлений
    одной и той же реплики.

    Attributes:
        id (str):
            Уникальная секция диалога, например ``"mymod_start_dialog"``.
        npc_alias (str):
            Алиас NPC-квестодателя из игровой базы данных, к которому
            привязывается диалог.
        preconditions (list[Condition]):
            Условия доступности всего диалога.
        phrases (dict[int, Phrase]):
            Карта дерева реплик: ключ — идентификатор реплики, значение —
            сама реплика.

    Raises:
        pydantic.ValidationError:
            Если граф реплик нарушает перечисленные инварианты.
    """

    model_config = _MODEL_CONFIG

    id: str = Field(
        description="Уникальная секция диалога в конфигурации игры.",
    )
    npc_alias: str = Field(
        description="Алиас NPC-квестодателя, к которому крепится диалог.",
    )
    preconditions: list[Condition] = Field(
        default_factory=list,
        description="Условия доступности всего диалога.",
    )
    phrases: dict[int, Phrase] = Field(
        description="Карта реплик диалога, индексированная по Phrase.id.",
    )

    @model_validator(mode="after")
    def _validate_phrase_graph(self) -> Self:
        """Проверяет ссылочную целостность дерева реплик диалога.

        Логика проверки:

        1. Словарь :attr:`phrases` не должен быть пустым.
        2. В нём обязателен ключ ``0`` — стартовая фраза актора.
        3. Ключ каждой записи должен совпадать с ``Phrase.id``.
        4. Каждый элемент ``next_phrases`` должен присутствовать среди ключей
           :attr:`phrases`.

        Возвращаемое значение позволяет Pydantic использовать валидатор в
        цепочке ``mode="after"`` без изменения модели.

        Returns:
            Dialog: Тот же проверенный экземпляр диалога.

        Raises:
            ValueError:
                Если отсутствует стартовая фраза, ключ не совпадает с
                ``Phrase.id`` или найдена ссылка на несуществующую реплику.
        """
        if not self.phrases:
            raise ValueError(
                f"Диалог '{self.id}' не содержит ни одной фразы; "
                "требуется стартовая фраза с id=0."
            )

        if 0 not in self.phrases:
            raise ValueError(
                f"Диалог '{self.id}' должен содержать стартовую фразу "
                "с ключом id=0."
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
                        f"next_phrases ссылается на несуществующую фразу "
                        f"id={target_id}."
                    )

        return self


# ---------------------------------------------------------------------------
# Квесты
# ---------------------------------------------------------------------------


class Stage(BaseModel):
    """Один этап (подзадача) квеста.

    Attributes:
        id (int):
            Номер этапа. В составе :class:`Quest` этапы нумеруются подряд
            начиная с ``0``.
        title_ru (str):
            Заголовок подзадачи в КПК на русском языке.
        title_en (str):
            Заголовок подзадачи в КПК на английском языке.
        descr_ru (str):
            Описание подзадачи в КПК на русском языке.
        descr_en (str):
            Описание подзадачи в КПК на английском языке.
        target_alias (str):
            Алиас смарта, NPC или отряда, на который вешается маркер цели.
        on_start_actions (list[Action]):
            Действия, выполняемые при переходе на этот этап.
    """

    model_config = _MODEL_CONFIG

    id: int = Field(
        ge=0,
        description="Номер этапа квеста, начиная с 0.",
    )
    title_ru: str = Field(
        description="Заголовок подзадачи в КПК на русском языке.",
    )
    title_en: str = Field(
        description="Заголовок подзадачи в КПК на английском языке.",
    )
    descr_ru: str = Field(
        description="Описание подзадачи в КПК на русском языке.",
    )
    descr_en: str = Field(
        description="Описание подзадачи в КПК на английском языке.",
    )
    target_alias: str = Field(
        description="Алиас смарта, NPC или отряда для маркера цели.",
    )
    on_start_actions: list[Action] = Field(
        default_factory=list,
        description="Действия при переходе на этап.",
    )


class Quest(BaseModel):
    """Сюжетный квест с линейной нумерацией этапов.

    Модель проверяет, что ключи :attr:`stages` образуют непрерывную
    последовательность ``0, 1, 2, ...`` без пропусков, а ключ каждого этапа
    совпадает с ``Stage.id``.

    Attributes:
        id (str):
            Уникальная LTX-секция квеста, например ``"mymod_av_quest"``.
        title_ru (str):
            Название квеста на русском языке.
        title_en (str):
            Название квеста на английском языке.
        descr_ru (str):
            Описание квеста на русском языке.
        descr_en (str):
            Описание квеста на английском языке.
        is_storyline (bool):
            Признак сюжетного квеста. По умолчанию ``True``.
        stages (dict[int, Stage]):
            Карта этапов квеста, индексированная по ``Stage.id``.
        on_init_actions (list[Action]):
            Эффекты при выдаче квеста.
        on_complete_actions (list[Action]):
            Награды и эффекты при успешном завершении квеста.
        on_fail_actions (list[Action]):
            Эффекты при провале квеста.

    Raises:
        pydantic.ValidationError:
            Если этапы пусты, пронумерованы с пропусками или ключ этапа не
            совпадает с ``Stage.id``.
    """

    model_config = _MODEL_CONFIG

    id: str = Field(
        description="Уникальная LTX-секция квеста.",
    )
    title_ru: str = Field(
        description="Название квеста на русском языке.",
    )
    title_en: str = Field(
        description="Название квеста на английском языке.",
    )
    descr_ru: str = Field(
        description="Описание квеста на русском языке.",
    )
    descr_en: str = Field(
        description="Описание квеста на английском языке.",
    )
    is_storyline: bool = Field(
        default=True,
        description="Признак сюжетного квеста.",
    )
    stages: dict[int, Stage] = Field(
        description="Карта этапов квеста, индексированная по Stage.id.",
    )
    on_init_actions: list[Action] = Field(
        default_factory=list,
        description="Действия при выдаче квеста.",
    )
    on_complete_actions: list[Action] = Field(
        default_factory=list,
        description="Действия при успешном завершении квеста.",
    )
    on_fail_actions: list[Action] = Field(
        default_factory=list,
        description="Действия при провале квеста.",
    )

    @model_validator(mode="after")
    def _validate_stage_sequence(self) -> Self:
        """Проверяет непрерывность и согласованность этапов квеста.

        Ключи :attr:`stages` должны образовывать множество
        ``{0, 1, ..., len(stages) - 1}``. Пустая карта этапов запрещена,
        поскольку квест обязан иметь хотя бы одну подзадачу. Дополнительно
        ключ каждой записи сравнивается с ``Stage.id``.

        Returns:
            Quest: Тот же проверенный экземпляр квеста.

        Raises:
            ValueError:
                Если карта этапов пуста, содержит пропуски/отрицательные
                номера или ключ этапа не совпадает с ``Stage.id``.
        """
        if not self.stages:
            raise ValueError(
                f"Квест '{self.id}' должен содержать хотя бы один этап "
                "(этап с id=0)."
            )

        actual_keys = sorted(self.stages)
        expected_keys = list(range(len(self.stages)))

        if actual_keys != expected_keys:
            raise ValueError(
                f"Этапы квеста '{self.id}' должны быть пронумерованы подряд "
                f"с 0. Ожидались ключи {expected_keys}, получены "
                f"{actual_keys}."
            )

        for stage_key, stage in self.stages.items():
            if stage_key != stage.id:
                raise ValueError(
                    f"Квест '{self.id}': ключ этапа {stage_key} не совпадает "
                    f"с Stage.id={stage.id}."
                )

        return self


# ---------------------------------------------------------------------------
# Корневой проект
# ---------------------------------------------------------------------------


class ModProject(BaseModel):
    """Корневая модель проекта модификации.

    Объединяет все квесты и диалоги мода и умеет сериализоваться в JSON и
    YAML. Формат обоих представлений полностью обратим: дискриминаторы
    ``type`` у условий и действий сохраняются, поэтому проект можно прочитать
    обратно без потери полиморфных данных.

    Attributes:
        name (str):
            Название модификации.
        required_mods (list[str]):
            Заглушка под будущие зависимости модов. Сюда записываются имена
            файлов дополнительных баз данных, например
            ``["bas_db.sqlite"]``, необходимых для валидации кастомных
            предметов.
        quests (dict[str, Quest]):
            Карта квестов проекта, индексированная по ``Quest.id``.
        dialogs (dict[str, Dialog]):
            Карта диалогов проекта, индексированная по ``Dialog.id``.
    """

    model_config = _MODEL_CONFIG

    name: str = Field(
        description="Название модификации.",
    )
    required_mods: list[str] = Field(
        default_factory=list,
        description=(
            "Заглушка под будущие зависимости модов. Сюда записываются имена "
            "файлов доп. баз данных, например ['bas_db.sqlite'], необходимых "
            "для валидации кастомных предметов"
        ),
    )
    quests: dict[str, Quest] = Field(
        default_factory=dict,
        description="Карта квестов проекта, индексированная по Quest.id.",
    )
    dialogs: dict[str, Dialog] = Field(
        default_factory=dict,
        description="Карта диалогов проекта, индексированная по Dialog.id.",
    )

    def to_json(self) -> str:
        """Сериализует проект в JSON-строку.

        Используется ``model_dump_json`` Pydantic, поэтому:

        * строки сохраняются в UTF-8 без экранирования кириллицы;
        * полиморфные условия и действия включают поле-дискриминатор ``type``;
        * числовые ключи словарей ``phrases`` и ``stages`` становятся
          строковыми ключами JSON, как того требует стандарт.

        Returns:
            str: Отформатированная JSON-строка с отступом в два пробела.
        """
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "ModProject":
        """Восстанавливает проект из JSON-строки.

        Pydantic автоматически:

        * преобразует строковые ключи ``phrases``/``stages`` обратно в ``int``;
        * выбирает конкретные классы условий и действий по полю ``type``;
        * запускает все валидаторы графов реплик и этапов.

        Args:
            json_str (str):
                JSON-документ, созданный методом :meth:`to_json` или вручную.

        Returns:
            ModProject: Полностью проверенный экземпляр проекта.

        Raises:
            pydantic.ValidationError:
                Если JSON синтаксически корректен, но нарушает схему модели
                или инварианты графов.
        """
        return cls.model_validate_json(json_str)

    def to_yaml(self) -> str:
        """Сериализует проект в YAML-строку.

        Для безопасности используется :func:`yaml.safe_dump`. Ключи этапов и
        реплик остаются целыми числами (режим ``model_dump(mode="python")``),
        поэтому итоговый YAML удобно читать и редактировать вручную.
        Порядок полей и ключей сохраняется таким же, как в модели.

        Returns:
            str: YAML-документ в Unicode с отступом в два пробела.
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
        """Восстанавливает проект из YAML-строки.

        Сначала :func:`yaml.safe_load` разбирает документ в Python-словарь,
        затем Pydantic валидирует его по схеме :class:`ModProject`. Если YAML
        использует строковые ключи для этапов или реплик, они автоматически
        приводятся к ``int``.

        Args:
            yaml_str (str):
                YAML-документ, созданный методом :meth:`to_yaml` или вручную.

        Returns:
            ModProject: Полностью проверенный экземпляр проекта.

        Raises:
            yaml.YAMLError:
                Если документ не является корректным YAML.
            pydantic.ValidationError:
                Если структура данных не соответствует модели или нарушает
                инварианты графов.
        """
        data = yaml.safe_load(yaml_str)
        return cls.model_validate(data)


__all__ = [
    "Action",
    "BaseAction",
    "BaseCondition",
    "Condition",
    "Dialog",
    "DontHasInfo",
    "GiveInfo",
    "GiveItem",
    "GiveMoney",
    "HasInfo",
    "HasItem",
    "ModProject",
    "Phrase",
    "Quest",
    "RemoveInfo",
    "RemoveItem",
    "SetTarget",
    "SmartOwner",
    "SpawnSquad",
    "Stage",
]
