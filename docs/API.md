# API и техническая спецификация

**Проект:** S.T.A.L.K.E.R. Anomaly Quest Builder  
**Назначение:** декларативное описание сюжетных квестов, диалогов и Warfare-сцен для S.T.A.L.K.E.R. Anomaly 1.5.2 / 1.5.3  
**Аудитория:** разработчики модов, технические писатели, сторонние ИИ-агенты, генерирующие сюжетный контент  
**Стек:** Python 3.11+, Pydantic v2, PyYAML, SQLite, Lua 5.1 / X-Ray 1.6

---

## Содержание

1. [Введение и архитектурный обзор](#1-введение-и-архитектурный-обзор)
2. [Ключевые концепции и словарь алиасов](#2-ключевые-концепции-и-словарь-алиасов)
3. [Полный атлас условий `Condition`](#3-полный-атлас-условий-condition)
4. [Полный атлас действий `Action`](#4-полный-атлас-действий-action)
5. [Спецификация диалогов: `Phrase` и `Dialog`](#5-спецификация-диалогов-phrase-и-dialog)
6. [Спецификация квестов: `Stage` и `Quest`](#6-спецификация-квестов-stage-и-quest)
7. [Сериализация проекта: `ModProject`](#7-сериализация-проекта-modproject)
8. [Сборка мода: `ModBuilder`](#8-сборка-мода-modbuilder)
9. [Комплексный сквозной пример Quick Start](#9-комплексный-сквозной-пример-quick-start)
10. [Диагностика ошибок и типовые проблемы](#10-диагностика-ошибок-и-типовые-проблемы)
11. [Чек-лист разработчика](#11-чек-лист-разработчика)
12. [Приложения](#12-приложения)

---

## 1. Введение и архитектурный обзор

### 1.1. Назначение библиотеки

`anomaly_1-5-3_quest_maker` — это **ноу-код ядро** для генерации сюжетного контента Anomaly. Разработчик описывает историю не вручную в десятках LTX/XML/Lua-файлов, а в одной строгой структуре данных:

- квесты и цепочки этапов для КПК;
- диалоги NPC с ветвлением, условиями и действиями;
- Warfare-сцены: спавн отрядов, назначение целей, проверка владельца смарт-террейна;
- награды, инфопоршни, выдачу и изъятие предметов;
- русскую и английскую локализацию;
- автоматическую привязку диалогов к NPC через сгенерированный `on_game_start()`.

Библиотека выполняет роль «компилятора сюжета»:

```text
YAML / JSON / Python-код
        │
        ▼
ModProject (Pydantic-модель, структурная валидация)
        │
        ▼
ProjectValidator + GameDatabase (runtime-проверка ассетов)
        │
        ▼
ModBuilder
   ├── LtxGenerator  ──► tm_<slug>.ltx
   ├── XmlGenerator  ──► dialogs_<slug>.xml
   │                    st_<slug>.xml (rus)
   │                    st_<slug>.xml (eng)
   └── LuaGenerator  ──► <slug>_quests.script
        │
        ▼
output/<slug>/gamedata/…  (Windows-1251 без BOM)
```

### 1.2. Зоны ответственности слоёв

| Слой | Файл | Ответственность | Чего слой не делает |
|---|---|---|---|
| Доменные модели | `src/core/models.py` | Pydantic-структуры квестов, этапов, диалогов, реплик, условий и действий; проверка типов, графов и полиморфизма | Не читает SQLite, не пишет игровые файлы, не запускает игру |
| Runtime-проверки условий | `src/core/conditions.py` | Точка расширения для проверки существования предметов и смартов, упомянутых в условиях | Сейчас это архитектурная заглушка, возвращающая `True` |
| Runtime-проверки действий | `src/core/actions.py` | Точка расширения для проверки отрядов, смартов и предметов, используемых действиями | Сейчас это архитектурная заглушка, возвращающая `True` |
| Оркестратор проверок | `src/core/validator.py` | Обход всех квестов и диалогов, вызов проверок условий и действий, агрегация результата | Не пересоздаёт Pydantic-модели; не проверяет алиасы автоматически, пока заглушки не реализованы |
| Репозиторий ассетов | `src/db/repository.py` | Read-only доступ к `data/anomaly_db.sqlite`: поиск NPC, смартов, предметов и отрядов по человекочитаемым алиасам | Не изменяет базу; не валидирует сюжетные модели |
| Генераторы игровых файлов | `src/compiler/ltx_gen.py`, `xml_gen.py`, `lua_gen.py` | Преобразование моделей в текстовые LTX/XML/Lua-документы | Не пишут файлы на диск; возвращают строки |
| Кодировка и экранирование | `src/compiler/encoding.py` | Запись в Windows-1251 без BOM, экранирование XML | Не формирует структуру файлов |
| Оркестратор сборки | `src/compiler/builder.py` | `ModBuilder`: slugify, очистка каталога, создание структуры `gamedata`, вызов генераторов, запись пяти файлов | Не запускает `ProjectValidator` автоматически; не устанавливает мод в игру |
| Логирование | `src/logger.py` | Единый логгер `aqb.*`, консоль Rich и `logs/app.log` | — |

### 1.3. Главные архитектурные инварианты

1. **Один источник истины.** Весь сюжет хранится в `ModProject`: карты `quests` и `dialogs` + метаданные мода.
2. **Строгая схема.** Все модели используют:

   ```python
   ConfigDict(extra="forbid", validate_assignment=True)
   ```

   Опечатка в имени поля (`text_ruu`, `target_alias` вместо `target_alias` и т.п.) приводит к `pydantic.ValidationError`, а не к молчаливой потере данных.
3. **Полиморфизм через `type`.** Условия и действия — дискриминируемые объединения Pydantic. Поле `type` обязательно при чтении JSON/YAML и автоматически добавляется при сериализации.
4. **Целочисленные ключи графов.** `phrases: dict[int, Phrase]`, `stages: dict[int, Stage]`. В JSON ключи становятся строками (требование стандарта), Pydantic преобразует их обратно в `int`.
5. **Двуязычность.** Каждый текст имеет пару `*_ru` / `*_en`. Оба поля обязательны.
6. **Алиасы — не произвольные строки.** Для NPC, смартов, предметов и отрядов используются человекочитаемые алиасы из игровой SQLite-базы, например `esc.volk`, `weapon.vssk_vykhlop`, `squad.army_advanced`.
7. **Компилятор не доверяет повреждённым данным.** Ошибка в одном квесте или диалоге логируется, а остальные элементы продолжают собираться. `ModBuilder.build_project()` при критической ошибке возвращает `False`, а не роняет вызывающий процесс.

### 1.4. Что именно создаётся на выходе

```text
output/<slug>/
└── gamedata/
    ├── configs/
    │   ├── misc/
    │   │   └── task/
    │   │       └── tm_<slug>.ltx
    │   ├── gameplay/
    │   │   └── dialogs_<slug>.xml
    │   └── text/
    │       ├── rus/
    │       │   └── st_<slug>.xml
    │       └── eng/
    │           └── st_<slug>.xml
    └── scripts/
        └── <slug>_quests.script
```

Все пять файлов записываются в **Windows-1251 без BOM**. `slug` — безопасное имя, полученное из `ModProject.name` (см. раздел 8).

---

## 2. Ключевые концепции и словарь алиасов

### 2.1. Импорт публичного API моделей

```python
from src.core.models import (
    # Корневые сущности
    ModProject, Quest, Stage, Dialog, Phrase,
    # Условия
    Condition, HasInfo, DontHasInfo, HasItem, SmartOwner,
    # Действия
    Action, GiveInfo, RemoveInfo, SpawnSquad, SetTarget,
    GiveItem, RemoveItem, GiveMoney,
    # Базовые классы (для расширений и isinstance-проверок)
    BaseCondition, BaseAction,
)
```

### 2.2. Дискриминаторы: как Pydantic восстанавливает полиморфные объекты

| Пространство | Значение `type` | Класс Python | Назначение |
|---|---|---|---|
| `Condition` | `has_info` | `HasInfo` | У актора есть инфопоршень |
| `Condition` | `dont_has_info` | `DontHasInfo` | У актора нет инфопоршня |
| `Condition` | `has_item` | `HasItem` | В инвентаре актора есть предмет |
| `Condition` | `smart_owner` | `SmartOwner` | Смарт принадлежит фракции |
| `Action` | `give_info` | `GiveInfo` | Выдать инфопоршень |
| `Action` | `remove_info` | `RemoveInfo` | Забрать инфопоршень |
| `Action` | `spawn_squad` | `SpawnSquad` | Заспавнить отряд в смарте |
| `Action` | `set_target` | `SetTarget` | Назначить отряду цель-смарт |
| `Action` | `give_item` | `GiveItem` | Выдать предмет |
| `Action` | `remove_item` | `RemoveItem` | Изъять предмет |
| `Action` | `give_money` | `GiveMoney` | Выдать деньги |

Пример восстановления из JSON:

```python
from pydantic import TypeAdapter
from src.core.models import Action, Condition

condition = TypeAdapter(Condition).validate_python({
    "type": "has_item",
    "item_alias": "medical.aptechka_pervoy_pomoshchi",
})

action = TypeAdapter(Action).validate_json(
    '{"type": "give_money", "amount": 3000}'
)

print(type(condition).__name__)  # HasItem
print(type(action).__name__)     # GiveMoney
```

> **Важно для сторонних ИИ-агентов:** при генерации JSON/YAML всегда указывайте `type` первым логическим полем. Без дискриминатора Pydantic не сможет выбрать конкретный класс и выбросит `ValidationError`.

### 2.3. Словарь алиасов

Алиасы — это стабильные человекочитаемые идентификаторы, которые индексатор `tools/build_db.py` создаёт из игровых ресурсов. Они не являются произвольными именами: если алиаса нет в `data/anomaly_db.sqlite`, ссылка считается ошибкой контента.

| Тип сущности | Префикс | Проверенные примеры | Где используется |
|---|---|---|---|
| NPC | `esc.`, `bar.`, `val.` и т.д. | `esc.volk`, `esc.mayor_zhurov`, `esc.sidorovich` | `Dialog.npc_alias`, `Stage.target_alias`, `SetTarget` при необходимости |
| Смарт-террейн | `esc.`, `agr.`, `jup.` и т.д. | `esc.derevnya_novichkov`, `esc.atp`, `esc.elevator`, `esc.yuzhnyy_blokpost` | `Stage.target_alias`, `SmartOwner.smart_alias`, `SpawnSquad.smart_alias`, `SetTarget.smart_alias` |
| Предмет | `weapon.`, `medical.`, `armor.`, `artefact.`, `quest.` и т.д. | `weapon.vssk_vykhlop`, `medical.aptechka_pervoy_pomoshchi` | `HasItem.item_alias`, `GiveItem.item_alias`, `RemoveItem.item_alias` |
| Отряд | `squad.` | `squad.army_advanced`, `squad.army_novice`, `squad.bandit_novice` | `SpawnSquad.squad_alias`, `SetTarget.squad_alias` |
| Инфопоршень | без префикса, задаётся автором | `mymod_quest_started`, `loner_wolf_medkit_done` | `HasInfo.info`, `DontHasInfo.info`, `GiveInfo.info`, `RemoveInfo.info` |

**Инфопоршни не хранятся в таблице ассетов.** Это строки состояния мира, которые мод создаёт сам. Рекомендуется использовать пространство имён мода, например `mymod_<quest>_started`, чтобы не конфликтовать с ванильными поршнями.

Проверка алиаса через репозиторий:

```python
from pathlib import Path
from src.db.repository import GameDatabase

with GameDatabase(Path("data/anomaly_db.sqlite")) as db:
    assert db.find_npc_by_alias("esc.volk") is not None
    assert db.find_smart_by_alias("esc.derevnya_novichkov") is not None
    assert db.find_item_by_alias("medical.aptechka_pervoy_pomoshchi") is not None
    assert db.find_squad_by_alias("squad.army_advanced") is not None
```

### 2.4. Мультиязычность

| Поле | Тип | Обязательность | Куда попадает |
|---|---|---|---|
| `title_ru`, `descr_ru` | `str` | Да | `st_<slug>.xml` (rus) |
| `title_en`, `descr_en` | `str` | Да | `st_<slug>.xml` (eng) |
| `text_ru` | `str` | Да | `st_<slug>.xml` (rus) |
| `text_en` | `str` | Да | `st_<slug>.xml` (eng) |

Игра может быть запущена с `language=eng`, поэтому английские тексты не являются «необязательным переводом». Пропуск `text_en` или `title_en` — ошибка модели.

---

## 3. Полный атлас условий `Condition`

### 3.1. Базовый контракт

```python
class BaseCondition(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    type: str
```

`Condition` — это `Annotated[Union[HasInfo, DontHasInfo, HasItem, SmartOwner], Field(discriminator="type")]`.

Условия используются в полях:

- `Phrase.preconditions: list[Condition]`;
- `Dialog.preconditions: list[Condition]`.

Список условий трактуется как логическое **И**: все условия должны быть истинны. Логического `ИЛИ` в базовой модели нет; ветвление реализуется разными репликами или разными диалогами.

### 3.2. `HasInfo` — наличие инфопоршня

**Назначение:** проверить, что у актора есть указанный информационный портфель (info portion). Типичное применение — гейт диалога или реплики после события квеста.

| Поле | Python-тип | Обязательное | Описание |
|---|---|---|---|
| `type` | `Literal["has_info"]` | Да (default) | Дискриминатор |
| `info` | `str` | Да | Идентификатор инфопоршня |

**JSON:**

```json
{
  "type": "has_info",
  "info": "mymod_quest_started"
}
```

**Python:**

```python
HasInfo(info="mymod_quest_started")
```

**Lua-трансляция:** `has_alife_info("mymod_quest_started")`.

**Правила:** `info` — не алиас из SQLite, а строковый идентификатор состояния. Используйте стабильное имя, которое не меняется между версиями мода.

---

### 3.3. `DontHasInfo` — отсутствие инфопоршня

**Назначение:** показать реплику или диалог только до наступления события. Классический пример — «поговорить с NPC до завершения квеста».

| Поле | Python-тип | Обязательное | Описание |
|---|---|---|---|
| `type` | `Literal["dont_has_info"]` | Да (default) | Дискриминатор |
| `info` | `str` | Да | Идентификатор проверяемого инфопоршня |

**JSON:**

```json
{
  "type": "dont_has_info",
  "info": "loner_wolf_medkit_done"
}
```

**Python:**

```python
DontHasInfo(info="loner_wolf_medkit_done")
```

**Lua-трансляция:** `not has_alife_info("loner_wolf_medkit_done")`.

**Правила:** не путайте с «отрицанием произвольного условия». `DontHasInfo` проверяет только инфопоршни.

---

### 3.4. `HasItem` — наличие предмета

**Назначение:** проверить, что в инвентаре актора есть предмет с указанным алиасом.

| Поле | Python-тип | Обязательное | Описание |
|---|---|---|---|
| `type` | `Literal["has_item"]` | Да (default) | Дискриминатор |
| `item_alias` | `str` | Да | Человекочитаемый алиас предмета из базы |

**JSON:**

```json
{
  "type": "has_item",
  "item_alias": "medical.aptechka_pervoy_pomoshchi"
}
```

**Python:**

```python
HasItem(item_alias="medical.aptechka_pervoy_pomoshchi")
```

**Lua-трансляция:** `db.actor:object("medical.aptechka_pervoy_pomoshchi") ~= nil` для квестовых проверок и `second_speaker:object(...) ~= nil` для предусловий реплик.

**Правила:**

- Используйте именно алиас из базы (`weapon.vssk_vykhlop`), а не внутренний section (`wpn_vssk_vykhlop`).
- Для проверки квестового предмета, созданного модом, убедитесь, что предмет существует в игре или добавлен совместимым модом. В будущем runtime-проверка будет сверять алиас с SQLite.

---

### 3.5. `SmartOwner` — владелец смарт-террейна

**Назначение:** проверить, что смарт-террейн принадлежит указанной фракции. Основной сценарий — Warfare-квесты на захват и удержание точек.

| Поле | Python-тип | Обязательное | Описание |
|---|---|---|---|
| `type` | `Literal["smart_owner"]` | Да (default) | Дискриминатор |
| `smart_alias` | `str` | Да | Алиас смарт-террейна из базы |
| `faction` | `str` | Да | Техническое имя фракции, например `army`, `stalker`, `bandit` |

**JSON:**

```json
{
  "type": "smart_owner",
  "smart_alias": "esc.derevnya_novichkov",
  "faction": "army"
}
```

**Python:**

```python
SmartOwner(
    smart_alias="esc.derevnya_novichkov",
    faction="army",
)
```

**Lua-трансляция:**

```lua
mymod_quests.is_smart_captured("esc.derevnya_novichkov", "army")
```

**Правила:**

- `faction` — техническое имя фракции, а не локализованное название. Для группировки «Военные» используйте `army`, для «Одиночек» — `stalker` (проверяйте фактическое имя в базе).
- В начале игры `owning_faction` смарта может быть `nil` или `"none"`; helper `is_smart_captured` корректно возвращает `false`, если смарт ещё не рассчитан.
- Условие имеет смысл в Warfare/ALife-симуляции; вне Warfare поведение зависит от состояния `SIMBOARD`.

---

### 3.6. Правила алиасов для условий

| Условие | Поле | Обязательный префикс/формат | Пример |
|---|---|---|---|
| `HasInfo` | `info` | Свободный стабильный идентификатор | `mymod_av_available` |
| `DontHasInfo` | `info` | Свободный стабильный идентификатор | `mymod_av_started` |
| `HasItem` | `item_alias` | Алиас предмета из базы | `weapon.vssk_vykhlop` |
| `SmartOwner` | `smart_alias` | Алиас смарта из базы | `esc.atp` |
| `SmartOwner` | `faction` | Техническое имя фракции | `army` |

**Запрещено:**

- подставлять внутренние игровые section вместо алиасов;
- использовать пробелы и кириллицу в алиасах;
- придумывать алиас, не проверив его через `GameDatabase`;
- использовать `item_alias` для NPC или смарта.

---

## 4. Полный атлас действий `Action`

### 4.1. Базовый контракт

```python
class BaseAction(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    type: str
```

`Action` — это `Annotated[Union[GiveInfo, RemoveInfo, SpawnSquad, SetTarget, GiveItem, RemoveItem, GiveMoney], Field(discriminator="type")]`.

Действия используются в полях:

- `Phrase.actions: list[Action]`;
- `Quest.on_init_actions`, `on_complete_actions`, `on_fail_actions`;
- `Stage.on_start_actions`.

Действия выполняются **в порядке списка**. Генератор сохраняет порядок, поэтому сначала выдавайте инфопоршень, затем награду, если это важно для условий.

### 4.2. `GiveInfo` — выдать инфопоршень

**Назначение:** зафиксировать событие в мире: квест взят, диалог просмотрен, этап достигнут.

| Поле | Python-тип | Обязательное | Описание |
|---|---|---|---|
| `type` | `Literal["give_info"]` | Да (default) | Дискриминатор |
| `info` | `str` | Да | Идентификатор выдаваемого инфопоршня |

**JSON:**

```json
{
  "type": "give_info",
  "info": "loner_wolf_medkit_started"
}
```

**Python:**

```python
GiveInfo(info="loner_wolf_medkit_started")
```

**Lua-трансляция:** `db.actor:give_info_portion("loner_wolf_medkit_started")`.

---

### 4.3. `RemoveInfo` — забрать инфопоршень

**Назначение:** снять состояние, чтобы диалог или событие могли произойти снова, либо чтобы закрыть ветку.

| Поле | Python-тип | Обязательное | Описание |
|---|---|---|---|
| `type` | `Literal["remove_info"]` | Да (default) | Дискриминатор |
| `info` | `str` | Да | Идентификатор удаляемого инфопоршня |

**JSON:**

```json
{
  "type": "remove_info",
  "info": "loner_wolf_medkit_active"
}
```

**Python:**

```python
RemoveInfo(info="loner_wolf_medkit_active")
```

**Lua-трансляция:** `db.actor:disable_info_portion("loner_wolf_medkit_active")`.

> **Осторожно:** не снимайте инфопоршень, который является условием текущего диалога, если это может привести к логическому циклу. Проверяйте граф инфопоршней вручную или расширяйте `ProjectValidator`.

---

### 4.4. `SpawnSquad` — спавн отряда в смарте

**Назначение:** создать Warfare-отряд в указанном смарт-террейне. Используется для подкреплений, штурмов, сцен захвата и квестовых противников.

| Поле | Python-тип | Обязательное | Описание |
|---|---|---|---|
| `type` | `Literal["spawn_squad"]` | Да (default) | Дискриминатор |
| `squad_alias` | `str` | Да | Алиас шаблона отряда из базы |
| `smart_alias` | `str` | Да | Алиас смарт-террейна, где появится отряд |

**JSON:**

```json
{
  "type": "spawn_squad",
  "squad_alias": "squad.army_advanced",
  "smart_alias": "esc.atp"
}
```

**Python:**

```python
SpawnSquad(
    squad_alias="squad.army_advanced",
    smart_alias="esc.atp",
)
```

**Lua-трансляция:** `mymod_quests.spawn_task_squad("squad.army_advanced", "esc.atp")`.

Сгенерированный helper:

1. находит смарт через `SIMBOARD.smarts_by_names`;
2. вызывает `SIMBOARD:setup_squad_and_move(squad_id, smart)`;
3. сбрасывает `stay_time`, назначает цель через `sim_squad_warfare.set_target`;
4. фиксирует отряд (`force_online`, `sim_offline_combat.task_squads`).

**Правила:**

- `squad_alias` — именно `squad.*`, а не `npc.*`;
- `smart_alias` — именно смарт, а не предмет и не NPC;
- для полевых отрядов предпочтительны шаблоны с `is_safe_field = 1`; проверка безопасности запланирована в `src/core/actions.py`;
- спавн имеет смысл в Warfare/ALife-симуляции, где доступен `SIMBOARD`.

---

### 4.5. `SetTarget` — назначить отряду цель

**Назначение:** принудительно отправить существующий отряд на смарт-террейн и удержать его там. Применяется для сцен «штурм», «оборона», «сопровождение».

| Поле | Python-тип | Обязательное | Описание |
|---|---|---|---|
| `type` | `Literal["set_target"]` | Да (default) | Дискриминатор |
| `squad_alias` | `str` | Да | Алиас отряда, которому назначается цель |
| `smart_alias` | `str` | Да | Алиас смарта-цели |

**JSON:**

```json
{
  "type": "set_target",
  "squad_alias": "squad.army_advanced",
  "smart_alias": "esc.elevator"
}
```

**Python:**

```python
SetTarget(
    squad_alias="squad.army_advanced",
    smart_alias="esc.elevator",
)
```

**Lua-трансляция:** `mymod_quests.set_task_target("squad.army_advanced", "esc.elevator")`.

**Правила:**

- `squad_alias` должен быть известен `SIMBOARD.squads_by_names` на момент выполнения;
- helper сам сбрасывает `stay_time` и заново фиксирует отряд, чтобы Warfare AI не увёл его с цели;
- не используйте `SetTarget` для личного отряда игрока (companion squad): Warfare-логика может игнорировать такие отряды.

---

### 4.6. `GiveItem` — выдать предмет

**Назначение:** награда, квестовый предмет, расходник.

| Поле | Python-тип | Обязательное | Описание |
|---|---|---|---|
| `type` | `Literal["give_item"]` | Да (default) | Дискриминатор |
| `item_alias` | `str` | Да | Алиас выдаваемого предмета |

**JSON:**

```json
{
  "type": "give_item",
  "item_alias": "weapon.vssk_vykhlop"
}
```

**Python:**

```python
GiveItem(item_alias="weapon.vssk_vykhlop")
```

**Lua-трансляция:**

- для квестовых действий: `dialogs.relocate_item_section(db.actor, "weapon.vssk_vykhlop", "in")`;
- для действий реплик: `dialogs.relocate_item_section(second_speaker, "...", "in")`.

---

### 4.7. `RemoveItem` — изъять предмет

**Назначение:** забрать квестовый предмет, оплату, образец и т.п.

| Поле | Python-тип | Обязательное | Описание |
|---|---|---|---|
| `type` | `Literal["remove_item"]` | Да (default) | Дискриминатор |
| `item_alias` | `str` | Да | Алиас изымаемого предмета |

**JSON:**

```json
{
  "type": "remove_item",
  "item_alias": "medical.aptechka_pervoy_pomoshchi"
}
```

**Python:**

```python
RemoveItem(item_alias="medical.aptechka_pervoy_pomoshchi")
```

**Lua-трансляция:**

- для квестовых действий: `dialogs.relocate_item_section(db.actor, "medical.aptechka_pervoy_pomoshchi", "out")`;
- для действий реплик: `dialogs.relocate_item_section(second_speaker, "...", "out")`.

---

### 4.8. `GiveMoney` — выдать деньги

**Назначение:** денежная награда или компенсация.

| Поле | Python-тип | Обязательное | Ограничение | Описание |
|---|---|---|---|---|
| `type` | `Literal["give_money"]` | Да (default) | — | Дискриминатор |
| `amount` | `int` | Да | `ge=0` | Неотрицательная сумма в игровой валюте |

**JSON:**

```json
{
  "type": "give_money",
  "amount": 3000
}
```

**Python:**

```python
GiveMoney(amount=3000)
```

**Lua-трансляция:** `db.actor:give_money(3000)`.

**Правила:**

- Отрицательные суммы запрещены Pydantic (`amount >= 0`). Для списания денег в будущем потребуется отдельное действие.
- `bool` не является допустимым значением для `amount` на уровне Lua-генератора: `True`/`False` не пройдут проверку `isinstance(amount, int)` с исключением bool.

---

### 4.9. Сводная таблица действий

| Класс | `type` | Обязательные поля | Игровой эффект | Lua-вызов |
|---|---|---|---|---|
| `GiveInfo` | `give_info` | `info: str` | Выдать поршень | `db.actor:give_info_portion` |
| `RemoveInfo` | `remove_info` | `info: str` | Забрать поршень | `db.actor:disable_info_portion` |
| `SpawnSquad` | `spawn_squad` | `squad_alias`, `smart_alias` | Спавн отряда | `mymod_quests.spawn_task_squad` |
| `SetTarget` | `set_target` | `squad_alias`, `smart_alias` | Назначить цель | `mymod_quests.set_task_target` |
| `GiveItem` | `give_item` | `item_alias` | Выдать предмет | `dialogs.relocate_item_section(..., "in")` |
| `RemoveItem` | `remove_item` | `item_alias` | Изъять предмет | `dialogs.relocate_item_section(..., "out")` |
| `GiveMoney` | `give_money` | `amount: int >= 0` | Выдать деньги | `db.actor:give_money` |

> **Ограничение текущей версии:** в `Action` нет действия «выдать задачу» (`give_task`). LTX-секция квеста создаётся, но фактическая выдача задачи выполняется штатным task manager Anomaly или внешним Lua-триггером. Не пытайтесь заменить это `GiveInfo`: инфопоршень не создаёт задачу в КПК.

---

## 5. Спецификация диалогов: `Phrase` и `Dialog`

### 5.1. `Phrase` — одна реплика

| Поле | Python-тип | Обязательное | Значение по умолчанию | Описание |
|---|---|---|---|---|
| `id` | `int` (`ge=0`) | Да | — | Уникальный идентификатор реплики внутри диалога |
| `text_ru` | `str` | Да | — | Русский текст |
| `text_en` | `str` | Да | — | Английский текст |
| `next_phrases` | `list[int]` | Нет | `[]` | Идентификаторы реплик, доступных после этой |
| `preconditions` | `list[Condition]` | Нет | `[]` | Условия доступности реплики |
| `actions` | `list[Action]` | Нет | `[]` | Эффекты при выборе реплики |

Конфигурация модели запрещает лишние поля:

```python
Phrase(
    id=0,
    text_ru="Здравствуй, Волк.",
    text_en="Hello, Wolf.",
    next_phrases=[1],
    preconditions=[HasInfo(info="mymod_quest_started")],
    actions=[GiveInfo(info="mymod_dialog_seen")],
)
```

**JSON-пример реплики:**

```json
{
  "id": 0,
  "text_ru": "Здравствуй, Волк. Есть работа?",
  "text_en": "Hello, Wolf. Got any work?",
  "next_phrases": [1, 2, 4],
  "preconditions": [
    {
      "type": "dont_has_info",
      "info": "loner_wolf_medkit_done"
    }
  ],
  "actions": []
}
```

### 5.2. `Dialog` — дерево диалога

| Поле | Python-тип | Обязательное | Описание |
|---|---|---|---|
| `id` | `str` | Да | Уникальная секция диалога, например `loner_wolf_medkit_dialog` |
| `npc_alias` | `str` | Да | Алиас NPC-квестодателя из базы |
| `preconditions` | `list[Condition]` | Нет | Условия доступности всего диалога |
| `phrases` | `dict[int, Phrase]` | Да | Карта реплик, ключ = `Phrase.id` |

**JSON-пример диалога:**

```json
{
  "id": "loner_wolf_medkit_dialog",
  "npc_alias": "esc.volk",
  "preconditions": [
    {
      "type": "dont_has_info",
      "info": "loner_wolf_medkit_done"
    }
  ],
  "phrases": {
    "0": {
      "id": 0,
      "text_ru": "Здравствуй, Волк. Есть работа?",
      "text_en": "Hello, Wolf. Got any work?",
      "next_phrases": [1, 2, 4],
      "preconditions": [],
      "actions": []
    },
    "1": {
      "id": 1,
      "text_ru": "Что нужно сделать?",
      "text_en": "What do you need?",
      "next_phrases": [3],
      "preconditions": [
        {
          "type": "dont_has_info",
          "info": "loner_wolf_medkit_started"
        }
      ],
      "actions": [
        {
          "type": "give_info",
          "info": "loner_wolf_medkit_started"
        }
      ]
    },
    "2": {
      "id": 2,
      "text_ru": "Вот аптечка, держи.",
      "text_en": "Here is the medkit.",
      "next_phrases": [],
      "preconditions": [
        {
          "type": "has_info",
          "info": "loner_wolf_medkit_started"
        },
        {
          "type": "has_item",
          "item_alias": "medical.aptechka_pervoy_pomoshchi"
        }
      ],
      "actions": [
        {
          "type": "remove_item",
          "item_alias": "medical.aptechka_pervoy_pomoshchi"
        },
        {
          "type": "give_info",
          "info": "loner_wolf_medkit_done"
        }
      ]
    },
    "3": {
      "id": 3,
      "text_ru": "Принесу аптечку. Жди.",
      "text_en": "I will bring a medkit. Wait for me.",
      "next_phrases": [],
      "preconditions": [],
      "actions": []
    },
    "4": {
      "id": 4,
      "text_ru": "До встречи.",
      "text_en": "See you.",
      "next_phrases": [],
      "preconditions": [],
      "actions": []
    }
  }
}
```

> В JSON ключи `phrases` — строки (`"0"`, `"1"`), потому что JSON не поддерживает целочисленные ключи объектов. Pydantic автоматически приводит их к `int`.

### 5.3. Жёсткие правила графа реплик

`Dialog` проверяет инварианты в `@model_validator(mode="after")`:

| № | Правило | Что произойдёт при нарушении |
|---|---|---|
| 1 | `phrases` не пуст | `ValueError`: диалог не содержит ни одной фразы |
| 2 | В `phrases` обязателен ключ `0` | `ValueError`: требуется стартовая фраза с `id=0` |
| 3 | Каждый ключ карты равен `Phrase.id` | `ValueError`: ключ фразы не совпадает с `Phrase.id` |
| 4 | Каждый `next_phrases[i]` существует среди ключей | `ValueError`: `next_phrases` ссылается на несуществующую фразу |
| 5 | `Phrase.id >= 0` | `ValidationError` от Pydantic |
| 6 | Нет неизвестных полей | `ValidationError` из-за `extra="forbid"` |
| 7 | Нет опечаток в имени поля | `ValidationError` с указанием лишнего поля |

**Пример ошибки:**

```text
Диалог 'broken_dialog', фраза id=0: next_phrases ссылается
на несуществующую фразу id=2.
```

**Что не проверяется автоматически:**

- достижимость каждой реплики из `id=0` (можно иметь «островные» реплики, но это почти всегда ошибка контента);
- отсутствие циклов;
- логическая непротиворечивость условий (например, `HasInfo` и `DontHasInfo` одного поршня в одном списке);
- уникальность `Dialog.id` внутри `ModProject.dialogs`;
- совпадение ключа `ModProject.dialogs` и `Dialog.id` (это проверяют генераторы и пропускают диалог при несовпадении).

### 5.4. Переходы через `next_phrases`

`next_phrases` задаёт **ориентированный граф**:

| Сценарий | Как описать |
|---|---|
| Линейный диалог | `0 → 1 → 2`, у последней реплики `next_phrases=[]` |
| Ветвление | `0 → [1, 2, 3]` |
| Слияние | `1 → [4]`, `2 → [4]`, `3 → [4]` |
| Терминальная реплика | `next_phrases=[]` |
| Возврат к предыдущей | `2 → [1]` (разрешено, но проверяйте отсутствие бесконечных циклов) |
| Несколько переходов из одной реплики | `next_phrases=[1, 2, 3]` |

В сгенерированном XML каждый переход превращается в отдельный тег:

```xml
<phrase id="0">
  <text>loner_wolf_medkit_dialog_phrase_0_text</text>
  <next id="1"/>
  <next id="2"/>
  <next id="4"/>
</phrase>
```

**Практическое правило:** стартовая реплика `id=0` — точка входа. Если вы хотите, чтобы диалог был доступен только при определённом условии, ставьте условие на реплику `0` (и/или на все ветки), потому что `Dialog.preconditions` в текущем XML-генераторе не выводятся как `<precondition>`.

### 5.5. Мультиязычность и генерация строк

Для каждого текста создаётся строковый идентификатор в `st_<slug>.xml`:

| Сущность | Идентификатор строки |
|---|---|
| Название квеста | `{quest_id}_title` |
| Описание квеста | `{quest_id}_descr` |
| Название этапа | `{quest_id}_stage_{stage_id}_title` |
| Описание этапа | `{quest_id}_stage_{stage_id}_descr` |
| Текст реплики | `{dialog_id}_phrase_{phrase_id}_text` |

Русский файл содержит `*_ru`, английский — `*_en`. Специальные символы XML (`&`, `<`, `>`, `"`, `'`) экранируются через `escape_xml_text()`.

### 5.6. Логика реплик в Lua

Для реплики, у которой есть `preconditions` или `actions`, генерируются две функции:

```lua
function mymod_quests.<dialog_id>_phrase_<id>_precondition(
    first_speaker, second_speaker, dialog_id, phrase_id
)
    return <Lua-выражение>
end

function mymod_quests.<dialog_id>_phrase_<id>_action(
    first_speaker, second_speaker, dialog_id, phrase_id
)
    -- действия
end
```

В XML реплика ссылается на них:

```xml
<precondition>mymod_quests.loner_wolf_medkit_dialog_phrase_2_precondition</precondition>
<action>mymod_quests.loner_wolf_medkit_dialog_phrase_2_action</action>
```

Если у реплики нет условий и действий, функции не создаются — это нормально.

### 5.7. Автоматическая привязка диалога к NPC

`Dialog.npc_alias` разрешается в игровой `id` NPC на этапе компиляции через `GameDatabase.find_npc_by_alias()`. В сгенерированный Lua попадает таблица:

```lua
local MYMOD_DIALOG_INJECTIONS = {
    { npc_id = "esc_2_12_stalker_wolf", dialog_id = "loner_wolf_medkit_dialog" },
}
```

И глобальная функция:

```lua
function inject_mymod_dialogs()
    if not character_community then return end
    if not character_community.get_character_profile then return end

    for _, injection in ipairs(MYMOD_DIALOG_INJECTIONS) do
        local profile = character_community.get_character_profile(injection.npc_id)
        if profile then
            profile:add_actor_dialog(injection.dialog_id)
        end
    end
end

function on_game_start()
    inject_mymod_dialogs()
end
```

Это обеспечивает автоматическую совместимость: не нужно вручную редактировать профили NPC или `dialogs.xml` игры. Если алиас не найден, диалог пропускается для инжекции с предупреждением в логе; сам XML-диалог при этом может быть сгенерирован, но в игре не появится у NPC.

---

## 6. Спецификация квестов: `Stage` и `Quest`

### 6.1. `Stage` — один этап КПК

| Поле | Python-тип | Обязательное | Описание |
|---|---|---|---|
| `id` | `int` (`ge=0`) | Да | Номер этапа |
| `title_ru` | `str` | Да | Заголовок подзадачи (рус.) |
| `title_en` | `str` | Да | Заголовок подзадачи (англ.) |
| `descr_ru` | `str` | Да | Описание подзадачи (рус.) |
| `descr_en` | `str` | Да | Описание подзадачи (англ.) |
| `target_alias` | `str` | Да | Алиас смарта/NPC/отряда для маркера цели |
| `on_start_actions` | `list[Action]` | Нет | Действия при переходе на этап |

**JSON-пример этапа:**

```json
{
  "id": 1,
  "title_ru": "Найти аптечку",
  "title_en": "Find a medkit",
  "descr_ru": "Добудьте аптечку первой помощи.",
  "descr_en": "Obtain a first-aid kit.",
  "target_alias": "esc.derevnya_novichkov",
  "on_start_actions": []
}
```

`target_alias` разрешается в `target_functor` через `mymod_resolve_target()`:

1. поиск в `SIMBOARD.smarts_by_names` (смарты);
2. числовой `id` → `alife_object(id)`;
3. story id → `alife():story_object(id)`.

Если алиас указывает на предмет, маркер цели, скорее всего, не разрешится. Для этапов «найти предмет» ставьте маркер на смарт или NPC, а не на `item_alias`.

### 6.2. `Quest` — сюжетный квест

| Поле | Python-тип | Обязательное | Значение по умолчанию | Описание |
|---|---|---|---|---|
| `id` | `str` | Да | — | Уникальная LTX-секция квеста |
| `title_ru` | `str` | Да | — | Название квеста (рус.) |
| `title_en` | `str` | Да | — | Название квеста (англ.) |
| `descr_ru` | `str` | Да | — | Описание квеста (рус.) |
| `descr_en` | `str` | Да | — | Описание квеста (англ.) |
| `is_storyline` | `bool` | Нет | `True` | Признак сюжетного квеста |
| `stages` | `dict[int, Stage]` | Да | — | Карта этапов |
| `on_init_actions` | `list[Action]` | Нет | `[]` | Эффекты при выдаче квеста |
| `on_complete_actions` | `list[Action]` | Нет | `[]` | Награды и эффекты при завершении |
| `on_fail_actions` | `list[Action]` | Нет | `[]` | Эффекты при провале |

**JSON-пример квеста:**

```json
{
  "id": "loner_wolf_medkit_quest",
  "title_ru": "Аптечка для Волка",
  "title_en": "A Medkit for Wolf",
  "descr_ru": "Волк просит принести ему аптечку первой помощи.",
  "descr_en": "Wolf asks you to bring him a first-aid kit.",
  "is_storyline": true,
  "stages": {
    "0": {
      "id": 0,
      "title_ru": "Поговорить с Волком",
      "title_en": "Talk to Wolf",
      "descr_ru": "Найдите Волка в Деревне новичков.",
      "descr_en": "Find Wolf in the Rookie Village.",
      "target_alias": "esc.volk",
      "on_start_actions": []
    },
    "1": {
      "id": 1,
      "title_ru": "Найти аптечку",
      "title_en": "Find a medkit",
      "descr_ru": "Добудьте аптечку первой помощи.",
      "descr_en": "Obtain a first-aid kit.",
      "target_alias": "esc.derevnya_novichkov",
      "on_start_actions": []
    },
    "2": {
      "id": 2,
      "title_ru": "Отдать аптечку Волку",
      "title_en": "Give the medkit to Wolf",
      "descr_ru": "Вернитесь к Волку и отдайте аптечку.",
      "descr_en": "Return to Wolf and hand him the medkit.",
      "target_alias": "esc.volk",
      "on_start_actions": []
    }
  },
  "on_init_actions": [
    {
      "type": "give_info",
      "info": "loner_wolf_medkit_active"
    }
  ],
  "on_complete_actions": [
    {
      "type": "give_money",
      "amount": 3000
    },
    {
      "type": "give_item",
      "item_alias": "weapon.vssk_vykhlop"
    }
  ],
  "on_fail_actions": [
    {
      "type": "remove_info",
      "info": "loner_wolf_medkit_active"
    }
  ]
}
```

### 6.3. Требование непрерывности этапов

`Quest` проверяет:

1. `stages` не пуст;
2. ключи образуют множество `{0, 1, ..., len(stages) - 1}`;
3. ключ каждой записи совпадает с `Stage.id`.

Разрешено:

```python
stages = {0: Stage(id=0, ...), 1: Stage(id=1, ...), 2: Stage(id=2, ...)}
```

Запрещено:

```python
stages = {0: Stage(id=0, ...), 2: Stage(id=2, ...)}  # пропущен 1
stages = {1: Stage(id=1, ...)}                       # нет 0
stages = {0: Stage(id=0, ...), 1: Stage(id=2, ...)}  # ключ != Stage.id
```

Ошибка для пропуска выглядит так:

```text
Этапы квеста 'mymod_quest' должны быть пронумерованы подряд с 0.
Ожидались ключи [0, 1], получены [0, 2].
```

### 6.4. Триггеры событий квеста

| Триггер | Где задаётся | Когда выполняется | Что генерируется в Lua |
|---|---|---|---|
| Выдача квеста | `Quest.on_init_actions` | Штатный task manager вызывает `on_init` при выдаче задачи | `function mymod_quests.<quest_id>_on_init(tsk)`; однократный звук КПК + действия |
| Переход на этап | `Stage.on_start_actions` | При переходе со стадии `N` на `N+1` внутри `status_functor` | Действия встраиваются в ветку `tsk.stage = N+1` |
| Успешное завершение | `Quest.on_complete_actions` | Игра вызывает `on_complete` после статуса `complete` | `function mymod_quests.<quest_id>_on_complete(tsk)`; новость + действия |
| Провал | `Quest.on_fail_actions` | Игра вызывает `on_fail` после статуса `fail` | `function mymod_quests.<quest_id>_on_fail(tsk)`; новость + действия |

**Важное ограничение:** `Stage.on_start_actions` этапа `0` не выполняются автоматически сгенерированным `status_functor`, потому что переход «с предыдущего этапа на 0» не существует. Для начальных эффектов используйте `Quest.on_init_actions`.

### 6.5. Условия перехода между этапами

В **базовой Pydantic-модели** `Quest` и `Stage` нет поля `transfer_conditions`. Генератор `LuaGenerator` поддерживает его как расширение через duck typing: он читает `getattr(quest, "transfer_conditions", None)` и `getattr(stage, "transfer_conditions", None)`.

Чтобы пользоваться типизированными переходами, создайте наследника:

```python
from pydantic import Field
from src.core.models import Condition, Quest, Stage

class QuestWithTransfers(Quest):
    transfer_conditions: dict[int, dict[str, list[Condition]]] = Field(
        default_factory=dict,
    )

class StageWithTransfers(Stage):
    transfer_conditions: dict[str, list[Condition]] = Field(
        default_factory=dict,
    )
```

Поддерживаемые формы:

| Форма | Пример | Смысл |
|---|---|---|
| Правила по этапам | `{0: {"complete": [...], "fail": [...]}, 1: [...]}` | Для каждого этапа — свои условия |
| Общие правила квеста | `{"complete": [...], "fail": [...]}` | Проверяются до правил этапов |
| Список условий | `[HasItem(item_alias="...")]` | Условие завершения последнего этапа |
| Только `complete` | `{0: {"complete": [HasInfo(info="...")]}}` | Переход дальше или завершение |
| Только `fail` | `{1: {"fail": [DontHasInfo(info="...")]}}` | Провал квеста |

**Приоритет:** правила `fail` проверяются раньше `complete`. Если сработал `fail`, переход не выполняется.

**Пример:**

```python
quest = QuestWithTransfers(
    id="loner_wolf_medkit_quest",
    # ...
    stages={
        0: Stage(id=0, ...),
        1: Stage(id=1, ...),
        2: Stage(id=2, ...),
    },
    transfer_conditions={
        0: {"complete": [HasInfo(info="loner_wolf_medkit_started")]},
        1: {"complete": [HasItem(item_alias="medical.aptechka_pervoy_pomoshchi")]},
        2: {"complete": [HasInfo(info="loner_wolf_medkit_done")]},
    },
)
```

Сгенерированный `status_functor` будет вести себя так:

```lua
if tsk.stage == 0 then
    if has_alife_info("loner_wolf_medkit_started") then
        tsk.stage = 1
        -- сюда встраиваются on_start_actions этапа 1
        return nil
    end
    return nil
end

if tsk.stage == 1 then
    if db.actor:object("medical.aptechka_pervoy_pomoshchi") ~= nil then
        tsk.stage = 2
        return nil
    end
    return nil
end

if tsk.stage == 2 then
    if has_alife_info("loner_wolf_medkit_done") then
        return "complete"
    end
    return nil
end
```

**Если `transfer_conditions` отсутствует:**

- `status_functor` генерируется, но всегда возвращает `nil`;
- квест не завершится автоматически по условиям;
- завершение/провал должны выполняться внешним Lua-кодом или штатным task manager;
- это не ошибка Pydantic, а осознанное ограничение текущей базовой схемы.

### 6.6. `target_alias` и маркер цели

`target_functor` вызывается игрой каждый тик и возвращает текущую цель:

```lua
function mymod_quests.loner_wolf_medkit_quest_target_functor(tsk, task_id)
    local stage = tsk.stage or 0

    if stage == 0 then
        return mymod_resolve_target("esc.volk")
    end
    if stage == 1 then
        return mymod_resolve_target("esc.derevnya_novichkov")
    end
    if stage == 2 then
        return mymod_resolve_target("esc.volk")
    end

    return nil
end
```

Практические правила:

- `target_alias` должен указывать на смарт, NPC или story-объект;
- пустая строка допустима моделью, но даст `nil`-маркер;
- для предметов используйте смарт места, а не `item_alias`;
- если смарт ещё не загружен в `SIMBOARD`, маркер может быть `nil` до инициализации симуляции.

### 6.7. Соответствие LTX

Для каждого квеста генерируется секция:

```ini
[loner_wolf_medkit_quest]
icon = ui_inGame2_Put_v_pripyat
storyline = true

title = loner_wolf_medkit_quest_title
descr = loner_wolf_medkit_quest_descr

on_init = %=mymod_quests.loner_wolf_medkit_quest_on_init%
on_complete = %=mymod_quests.loner_wolf_medkit_quest_on_complete%
on_fail = %=mymod_quests.loner_wolf_medkit_quest_on_fail%

status_functor = mymod_quests.loner_wolf_medkit_quest_status_functor
target_functor = mymod_quests.loner_wolf_medkit_quest_target_functor
```

Файл `tm_<slug>.ltx` подхватывается штатным `#include "tm_*.ltx"` task manager Anomaly. Иконка задачи фиксирована (`LtxGenerator.DEFAULT_ICON`), а `storyline` берётся из `Quest.is_storyline`.

---

## 7. Сериализация проекта: `ModProject`

### 7.1. Структура

| Поле | Python-тип | Обязательное | Описание |
|---|---|---|---|
| `name` | `str` | Да | Название модификации |
| `required_mods` | `list[str]` | Нет | Заглушка под зависимости; имена дополнительных БД |
| `quests` | `dict[str, Quest]` | Нет | Карта квестов, ключ = `Quest.id` |
| `dialogs` | `dict[str, Dialog]` | Нет | Карта диалогов, ключ = `Dialog.id` |

```python
from src.core.models import ModProject

project = ModProject(
    name="Loner Wolf Medkit Quest",
    required_mods=[],
    quests={quest.id: quest},
    dialogs={dialog.id: dialog},
)
```

### 7.2. Методы сериализации

| Метод | Сигнатура | Результат | Особенности |
|---|---|---|---|
| `to_json` | `to_json(self) -> str` | JSON-строка с отступом 2 | UTF-8, кириллица не экранируется, `type` сохраняется, ключи `phrases`/`stages` — строки |
| `from_json` | `from_json(cls, json_str: str) -> ModProject` | Проверенный проект | `model_validate_json`, автоматическое восстановление классов по `type` |
| `to_yaml` | `to_yaml(self) -> str` | YAML-строка | `yaml.safe_dump`, Unicode, целочисленные ключи сохраняются, порядок полей сохраняется |
| `from_yaml` | `from_yaml(cls, yaml_str: str) -> ModProject` | Проверенный проект | `yaml.safe_load` + `model_validate`; строковые ключи этапов/реплик приводятся к `int` |

**Пример JSON:**

```python
json_text = project.to_json()
restored = ModProject.from_json(json_text)
assert restored == project
```

**Пример YAML:**

```python
yaml_text = project.to_yaml()
restored = ModProject.from_yaml(yaml_text)
assert restored == project
```

### 7.3. Полный YAML-пример

Ниже — компактный, но полноценный проект: один квест, один диалог, условия и действия с дискриминаторами.

```yaml
name: Loner Wolf Medkit Quest
required_mods: []
quests:
  loner_wolf_medkit_quest:
    id: loner_wolf_medkit_quest
    title_ru: Аптечка для Волка
    title_en: A Medkit for Wolf
    descr_ru: Волк просит принести ему аптечку первой помощи.
    descr_en: Wolf asks you to bring him a first-aid kit.
    is_storyline: true
    stages:
      0:
        id: 0
        title_ru: Поговорить с Волком
        title_en: Talk to Wolf
        descr_ru: Найдите Волка в Деревне новичков.
        descr_en: Find Wolf in the Rookie Village.
        target_alias: esc.volk
        on_start_actions: []
      1:
        id: 1
        title_ru: Найти аптечку
        title_en: Find a medkit
        descr_ru: Добудьте аптечку первой помощи.
        descr_en: Obtain a first-aid kit.
        target_alias: esc.derevnya_novichkov
        on_start_actions: []
      2:
        id: 2
        title_ru: Отдать аптечку Волку
        title_en: Give the medkit to Wolf
        descr_ru: Вернитесь к Волку и отдайте аптечку.
        descr_en: Return to Wolf and hand him the medkit.
        target_alias: esc.volk
        on_start_actions: []
    on_init_actions:
    - type: give_info
      info: loner_wolf_medkit_active
    on_complete_actions:
    - type: give_money
      amount: 3000
    - type: give_item
      item_alias: weapon.vssk_vykhlop
    - type: remove_info
      info: loner_wolf_medkit_active
    on_fail_actions:
    - type: remove_info
      info: loner_wolf_medkit_active
dialogs:
  loner_wolf_medkit_dialog:
    id: loner_wolf_medkit_dialog
    npc_alias: esc.volk
    preconditions:
    - type: dont_has_info
      info: loner_wolf_medkit_done
    phrases:
      0:
        id: 0
        text_ru: Здравствуй, Волк. Есть работа?
        text_en: Hello, Wolf. Got any work?
        next_phrases:
        - 1
        - 2
        - 4
        preconditions: []
        actions: []
      1:
        id: 1
        text_ru: Что нужно сделать?
        text_en: What do you need?
        next_phrases:
        - 3
        preconditions:
        - type: dont_has_info
          info: loner_wolf_medkit_started
        actions:
        - type: give_info
          info: loner_wolf_medkit_started
      2:
        id: 2
        text_ru: Вот аптечка, держи.
        text_en: Here is the medkit.
        next_phrases: []
        preconditions:
        - type: has_info
          info: loner_wolf_medkit_started
        - type: has_item
          item_alias: medical.aptechka_pervoy_pomoshchi
        actions:
        - type: remove_item
          item_alias: medical.aptechka_pervoy_pomoshchi
        - type: give_info
          info: loner_wolf_medkit_done
      3:
        id: 3
        text_ru: Принесу аптечку. Жди.
        text_en: I will bring a medkit. Wait for me.
        next_phrases: []
        preconditions: []
        actions: []
      4:
        id: 4
        text_ru: До встречи.
        text_en: See you.
        next_phrases: []
        preconditions: []
        actions: []
```

> В YAML целочисленные ключи `stages` и `phrases` сохраняются как числа. Если YAML-редактор превратил их в строки, `from_yaml()` всё равно восстановит `int`, но лучше сохранять числовой вид.

### 7.4. Гарантии Round-trip

`ModProject.from_json(project.to_json()) == project` и `ModProject.from_yaml(project.to_yaml()) == project` выполняются для базовой схемы. При этом:

- сохраняются кириллица и английские тексты;
- сохраняются дискриминаторы `type`;
- восстанавливаются конкретные классы условий и действий;
- проверяются инварианты графов реплик и этапов;
- порядок полей в YAML сохраняется.

Если вы расширяете модели (`transfer_conditions`, дополнительные поля), проверяйте сериализацию отдельно: базовая схема `ModProject` не знает о полях наследников.

---

## 8. Сборка мода: `ModBuilder`

### 8.1. Сигнатура

```python
class ModBuilder:
    def __init__(
        self,
        output_dir: Path = Path("output"),
        db_client: GameDatabase | None = None,
    ) -> None: ...

    def build_project(self, project: ModProject) -> bool: ...
```

| Параметр | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `output_dir` | `Path \| str` | `Path("output")` | Корневая папка, внутри которой создаётся `<slug>/gamedata` |
| `db_client` | `GameDatabase \| None` | `None` | Клиент базы для разрешения `Dialog.npc_alias` при генерации инъекции диалогов |
| `build_project` → | `bool` | — | `True` при успешной записи всех файлов; `False` при критической ошибке |

Если `db_client=None`, `LuaGenerator` попытается открыть стандартную базу `data/anomaly_db.sqlite` относительно корня проекта. Для предсказуемости лучше передавать открытый клиент.

### 8.2. `slugify`: безопасное имя проекта

`_slugify(name: str) -> str` выполняет:

1. приводит строку к нижнему регистру;
2. транслитерирует кириллицу в латиницу;
3. заменяет пробелы и дефисы на `_`;
4. удаляет всё, кроме `a-z`, `0-9`, `_`;
5. схлопывает повторяющиеся `_`;
6. обрезает `_` по краям;
7. если ничего не осталось — возвращает `mod`.

| Вход | Выход |
|---|---|
| `My Super Warfare Mod` | `my_super_warfare_mod` |
| `  My-Mod!!!  ` | `my_mod` |
| `Тестовый мод` | `testovyy_mod` |
| `Аптечка для Волка` | `aptechka_dlya_volka` |
| `!!!` | `mod` |

`slug` используется одновременно для:

- имени каталога `output/<slug>/`;
- имён файлов `tm_<slug>.ltx`, `dialogs_<slug>.xml`, `st_<slug>.xml`, `<slug>_quests.script`.

Это гарантирует безопасность для Lua/LTX и исключает пробелы и спецсимволы в путях.

### 8.3. Структура сборки

`ModBuilder._prepare_project_directory()`:

1. проверяет, что целевой каталог — прямой потомок `output_dir` (защита от удаления чужих данных);
2. создаёт `output_dir`, если его нет;
3. если `<slug>` уже существует — полностью удаляет его (`shutil.rmtree`);
4. создаёт пять обязательных каталогов:

   ```text
   gamedata/configs/misc/task
   gamedata/configs/gameplay
   gamedata/configs/text/rus
   gamedata/configs/text/eng
   gamedata/scripts
   ```

Повторная сборка всегда даёт чистый каталог без устаревших файлов.

### 8.4. Карта генерируемых файлов

| Файл | Генератор | Содержимое |
|---|---|---|
| `gamedata/configs/misc/task/tm_<slug>.ltx` | `LtxGenerator` | Секции задач КПК, `on_init`, `on_complete`, `on_fail`, `status_functor`, `target_functor` |
| `gamedata/configs/gameplay/dialogs_<slug>.xml` | `XmlGenerator` | Деревья диалогов, `<next>`, `<precondition>`, `<action>` |
| `gamedata/configs/text/rus/st_<slug>.xml` | `XmlGenerator` | Русские строки квестов, этапов и реплик |
| `gamedata/configs/text/eng/st_<slug>.xml` | `XmlGenerator` | Английские строки |
| `gamedata/scripts/<slug>_quests.script` | `LuaGenerator` | Lua 5.1: хелперы, функторы квестов, логика реплик, `on_game_start()` |

### 8.5. Кодировка и экранирование

`write_file_cp1251(path, content)`:

- создаёт родительские каталоги;
- открывает файл в `cp1251` с `errors="strict"`;
- **не добавляет BOM**;
- при невозможности закодировать символ выбрасывает `UnicodeEncodeError`, который `ModBuilder` перехватывает и возвращает `False`.

`escape_xml_text(text)` заменяет:

| Символ | Сущность |
|---|---|
| `&` | `&amp;` |
| `<` | `&lt;` |
| `>` | `&gt;` |
| `"` | `&quot;` |
| `'` | `&apos;` |

**Практическое правило:** не используйте в текстах эмодзи и редкие Unicode-символы, которые отсутствуют в Windows-1251. Кириллица, латиница и обычная пунктуация поддерживаются.

### 8.6. Полный конвейер `build_project`

1. Проверяет, что `project.name` — непустая строка.
2. Проверяет, что `project.quests` и `project.dialogs` — словари.
3. Вычисляет `slug = _slugify(project.name)`.
4. Полностью пересоздаёт `output_dir/<slug>`.
5. Создаёт `LtxGenerator`, `XmlGenerator`, `LuaGenerator(db_client=...)`.
6. Генерирует:
   - `tasks_content`;
   - `dialogs_content`;
   - `string_tables` (`rus`, `eng`);
   - `script_content`.
7. Проверяет, что все результаты — строки.
8. Записывает пять файлов через `write_file_cp1251`.
9. Проверяет, что каждый файл существует после записи.
10. Возвращает `True`; при `OSError`, `UnicodeError` или другой критической ошибке логирует исключение и возвращает `False`.

### 8.7. Генерация `on_game_start()` и совместимость

`LuaGenerator` всегда добавляет в шапку скрипта:

- `MYMOD_DIALOG_INJECTIONS` — пары `npc_id → dialog_id`;
- `inject_mymod_dialogs()`;
- глобальную `on_game_start()`, которая вызывает инъекцию.

Это ключевой механизм совместимости:

- не нужно редактировать ванильные файлы;
- не нужно вручную прописывать диалоги в профили NPC;
- движок Anomaly сам находит скрипты с `on_game_start()` и вызывает их после старта игры;
- `npc_alias` разрешается ещё на этапе компиляции, поэтому сгенерированный Lua не зависит от SQLite во время игры.

Если в проекте нет диалогов, таблица инъекций остаётся пустой, но `on_game_start()` всё равно генерируется — это безопасно.

### 8.8. Важные ограничения сборщика

- `ModBuilder` **не вызывает** `ProjectValidator` автоматически. Валидацию нужно запускать отдельно.
- `required_mods` в текущей версии — зарезервированное поле; слияние дополнительных SQLite-баз не реализовано.
- Lua-таблица называется `mymod_quests` независимо от `slug`. Не переименовывайте её вручную: LTX и XML ссылаются на это имя.
- Имя файла скрипта — `<slug>_quests.script`, но глобальная таблица внутри — `mymod_quests`.
- Сборщик не создаёт README и не устанавливает мод в игру. Результат предназначен для Mod Organizer 2 или ручного копирования `gamedata`.

---

## 9. Комплексный сквозной пример Quick Start

### 9.1. Что делает пример

Скрипт программно собирает квест за Одиночек на Кордоне:

1. поговорить с Волком (`esc.volk`) в Деревне новичков (`esc.derevnya_novichkov`);
2. найти аптечку первой помощи (`medical.aptechka_pervoy_pomoshchi`);
3. отдать аптечку Волку;
4. получить награду: 3000 денег и винтовку ВССК «Выхлоп» (`weapon.vssk_vykhlop`).

Дополнительно показаны:

- `QuestWithTransfers` — типизированное расширение для условий перехода этапов;
- `ProjectValidator`;
- `ModBuilder.build_project(project)`;
- реальные алиасы из `data/anomaly_db.sqlite`.

> **Примечание о выдаче задачи:** текущий `Action` не содержит `give_task`. Пример компилирует данные квеста и диалога; фактическая выдача задачи в игре выполняется штатным task manager Anomaly или внешним Lua-триггером. Диалог и переходы этапов полностью описаны и готовы к использованию.

### 9.2. Полный скрипт

Сохраните файл как `examples/loner_wolf_quickstart.py` и запустите из корня проекта:

```powershell
.\venv\Scripts\python.exe examples\loner_wolf_quickstart.py
```

```python
"""Сквозной Quick Start: квест «Аптечка для Волка» на Кордоне.

Скрипт собирает проект через Pydantic-модели, проверяет его
ProjectValidator и компилирует установочную папку мода ModBuilder.

Запуск из корня проекта:
    .\\venv\\Scripts\\python.exe examples\\loner_wolf_quickstart.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import Field

# Делаем корень проекта импортируемым при запуске из examples/.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compiler.builder import ModBuilder
from src.core.models import (
    Condition,
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveItem,
    GiveMoney,
    HasInfo,
    HasItem,
    ModProject,
    Phrase,
    Quest,
    RemoveInfo,
    RemoveItem,
    Stage,
)
from src.core.validator import ProjectValidator
from src.db.repository import GameDatabase

# ---------------------------------------------------------------------------
# Реальные алиасы из data/anomaly_db.sqlite
# ---------------------------------------------------------------------------

WOLF_ALIAS = "esc.volk"                                    # NPC: Волк
VILLAGE_ALIAS = "esc.derevnya_novichkov"                   # Смарт: Деревня новичков
MEDKIT_ALIAS = "medical.aptechka_pervoy_pomoshchi"         # Предмет: аптечка
REWARD_WEAPON = "weapon.vssk_vykhlop"                      # Предмет: ВССК «Выхлоп»

# Инфопоршни мода. Не являются алиасами SQLite.
QUEST_ACTIVE = "loner_wolf_medkit_active"
QUEST_STARTED = "loner_wolf_medkit_started"
QUEST_DONE = "loner_wolf_medkit_done"


class QuestWithTransfers(Quest):
    """Квест с условиями перехода между этапами.

    Базовая модель Quest не содержит transfer_conditions, но
    LuaGenerator поддерживает это поле через duck typing. Наследник
    добавляет строгую Pydantic-типизацию.
    """

    transfer_conditions: dict[int, dict[str, list[Condition]]] = Field(
        default_factory=dict,
    )


def build_project() -> ModProject:
    """Создаёт полностью описанный проект мода."""

    quest = QuestWithTransfers(
        id="loner_wolf_medkit_quest",
        title_ru="Аптечка для Волка",
        title_en="A Medkit for Wolf",
        descr_ru="Волк просит принести ему аптечку первой помощи.",
        descr_en="Wolf asks you to bring him a first-aid kit.",
        is_storyline=True,
        stages={
            0: Stage(
                id=0,
                title_ru="Поговорить с Волком",
                title_en="Talk to Wolf",
                descr_ru="Найдите Волка в Деревне новичков и узнайте, чем помочь.",
                descr_en="Find Wolf in the Rookie Village and ask how you can help.",
                target_alias=WOLF_ALIAS,
            ),
            1: Stage(
                id=1,
                title_ru="Найти аптечку",
                title_en="Find a medkit",
                descr_ru="Добудьте аптечку первой помощи.",
                descr_en="Obtain a first-aid kit.",
                target_alias=VILLAGE_ALIAS,
            ),
            2: Stage(
                id=2,
                title_ru="Отдать аптечку Волку",
                title_en="Give the medkit to Wolf",
                descr_ru="Вернитесь к Волку и отдайте ему аптечку.",
                descr_en="Return to Wolf and hand him the medkit.",
                target_alias=WOLF_ALIAS,
            ),
        },
        on_init_actions=[
            GiveInfo(info=QUEST_ACTIVE),
        ],
        on_complete_actions=[
            GiveMoney(amount=3000),
            GiveItem(item_alias=REWARD_WEAPON),
            RemoveInfo(info=QUEST_ACTIVE),
        ],
        on_fail_actions=[
            RemoveInfo(info=QUEST_ACTIVE),
        ],
        transfer_conditions={
            0: {"complete": [HasInfo(info=QUEST_STARTED)]},
            1: {"complete": [HasItem(item_alias=MEDKIT_ALIAS)]},
            2: {"complete": [HasInfo(info=QUEST_DONE)]},
        },
    )

    dialog = Dialog(
        id="loner_wolf_medkit_dialog",
        npc_alias=WOLF_ALIAS,
        preconditions=[DontHasInfo(info=QUEST_DONE)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Здравствуй, Волк. Есть работа?",
                text_en="Hello, Wolf. Got any work?",
                next_phrases=[1, 2, 4],
                preconditions=[DontHasInfo(info=QUEST_DONE)],
            ),
            1: Phrase(
                id=1,
                text_ru="Что нужно сделать?",
                text_en="What do you need?",
                next_phrases=[3],
                preconditions=[
                    DontHasInfo(info=QUEST_STARTED),
                    DontHasInfo(info=QUEST_DONE),
                ],
                actions=[GiveInfo(info=QUEST_STARTED)],
            ),
            2: Phrase(
                id=2,
                text_ru="Вот аптечка, держи.",
                text_en="Here is the medkit.",
                preconditions=[
                    HasInfo(info=QUEST_STARTED),
                    HasItem(item_alias=MEDKIT_ALIAS),
                    DontHasInfo(info=QUEST_DONE),
                ],
                actions=[
                    RemoveItem(item_alias=MEDKIT_ALIAS),
                    GiveInfo(info=QUEST_DONE),
                ],
            ),
            3: Phrase(
                id=3,
                text_ru="Принесу аптечку. Жди.",
                text_en="I will bring a medkit. Wait for me.",
                preconditions=[DontHasInfo(info=QUEST_DONE)],
            ),
            4: Phrase(
                id=4,
                text_ru="До встречи.",
                text_en="See you.",
                preconditions=[DontHasInfo(info=QUEST_DONE)],
            ),
        },
    )

    return ModProject(
        name="Loner Wolf Medkit Quest",
        required_mods=[],
        quests={quest.id: quest},
        dialogs={dialog.id: dialog},
    )


def main() -> None:
    """Валидирует проект и собирает мод в output/<slug>."""

    project = build_project()
    db_path = PROJECT_ROOT / "data" / "anomaly_db.sqlite"

    with GameDatabase(db_path) as db:
        validator = ProjectValidator(db)
        if not validator.validate_project(project):
            raise SystemExit("Проект не прошёл runtime-валидацию.")

        builder = ModBuilder(
            output_dir=PROJECT_ROOT / "output",
            db_client=db,
        )
        if not builder.build_project(project):
            raise SystemExit("Сборка мода завершилась ошибкой.")

    project_dir = builder.output_dir / "loner_wolf_medkit_quest"
    print(f"Мод собран: {project_dir.resolve()}")


if __name__ == "__main__":
    main()
```

### 9.3. Ожидаемый результат

```text
output/
└── loner_wolf_medkit_quest/
    └── gamedata/
        ├── configs/
        │   ├── misc/
        │   │   └── task/
        │   │       └── tm_loner_wolf_medkit_quest.ltx
        │   ├── gameplay/
        │   │   └── dialogs_loner_wolf_medkit_quest.xml
        │   └── text/
        │       ├── rus/
        │       │   └── st_loner_wolf_medkit_quest.xml
        │       └── eng/
        │           └── st_loner_wolf_medkit_quest.xml
        └── scripts/
            └── loner_wolf_medkit_quest_quests.script
```

В сгенерированном Lua-скрипте будет автоматическая привязка:

```lua
local MYMOD_DIALOG_INJECTIONS = {
    { npc_id = "esc_2_12_stalker_wolf", dialog_id = "loner_wolf_medkit_dialog" },
}
```

и глобальная `on_game_start()`, которая подключит диалог Волку без ручного редактирования игры.

---

## 10. Диагностика ошибок и типовые проблемы

### 10.1. Ошибки Pydantic

| Симптом | Причина | Решение |
|---|---|---|
| `Extra inputs are not permitted` | Опечатка в поле или лишнее поле | Проверьте точное имя поля; `extra="forbid"` не прощает лишних ключей |
| `Input should be a valid dictionary` | В `stages`/`phrases` передан список вместо карты | Используйте `dict[int, Stage]` / `dict[int, Phrase]` |
| `Input should be a valid integer` | Ключ или `id` передан строкой в Python-модели | В Python используйте `int`; в JSON/YAML строковые ключи допустимы и приводятся автоматически |
| `Input should be greater than or equal to 0` | `id` или `amount` отрицательны | Исправьте значение; `GiveMoney.amount >= 0` |
| `Unable to extract tag using discriminator 'type'` | В условии/действии нет `type` | Добавьте `"type": "..."` |
| `Unknown discriminator value` | Неизвестный `type` | Используйте только значения из таблицы дискриминаторов |

### 10.2. Ошибки графов

| Симптом | Причина | Решение |
|---|---|---|
| `Диалог '...' должен содержать стартовую фразу с ключом id=0` | Нет реплики `0` | Добавьте `Phrase(id=0, ...)` |
| `next_phrases ссылается на несуществующую фразу id=2` | Битая ссылка перехода | Добавьте реплику `id=2` или исправьте `next_phrases` |
| `ключ фразы 1 не совпадает с Phrase.id=2` | Ключ карты и `Phrase.id` расходятся | Сделайте ключ равным `id` |
| `Этапы квеста '...' должны быть пронумерованы подряд с 0` | Пропуск этапа | Используйте `0, 1, 2, ...` без пропусков |
| `ключ этапа 1 не совпадает с Stage.id=2` | Ключ карты и `Stage.id` расходятся | Сделайте ключ равным `id` |
| Диалог/квест пропущен при сборке | Ключ `ModProject.dialogs`/`quests` не равен `Dialog.id`/`Quest.id` | Всегда используйте `id` как ключ карты |

### 10.3. Ошибки сборки и алиасов

| Симптом | Причина | Решение |
|---|---|---|
| `FileNotFoundError: База данных не найдена` | Нет `data/anomaly_db.sqlite` | Запустите индексатор `tools/build_db.py` или укажите корректный путь |
| Диалог не появился у NPC | `npc_alias` не найден в базе или неверен | Проверьте `db.find_npc_by_alias(...)` |
| Предмет не выдается | `item_alias` не существует или неверный section | Проверьте `db.find_item_by_alias(...)` |
| Отряд не спавнится | `squad_alias`/`smart_alias` неверны или `SIMBOARD` недоступен | Проверьте алиасы и запуск в Warfare |
| Сборка вернула `False` | `OSError`, `UnicodeError`, проблема записи | Смотрите `logs/app.log`; проверьте права и кодировку |
| `UnicodeEncodeError` | В тексте есть символ, отсутствующий в Windows-1251 | Уберите эмодзи/редкие символы |
| Файл создан, но пустой | Генератор пропустил повреждённую сущность | Проверьте лог; исправьте данные |

### 10.4. Проверка алиасов перед сборкой

```python
from pathlib import Path
from src.db.repository import GameDatabase

ALIASES = {
    "npc": ["esc.volk", "esc.mayor_zhurov"],
    "smart": ["esc.derevnya_novichkov", "esc.atp"],
    "item": ["medical.aptechka_pervoy_pomoshchi", "weapon.vssk_vykhlop"],
    "squad": ["squad.army_advanced", "squad.army_novice"],
}

with GameDatabase(Path("data/anomaly_db.sqlite")) as db:
    finders = {
        "npc": db.find_npc_by_alias,
        "smart": db.find_smart_by_alias,
        "item": db.find_item_by_alias,
        "squad": db.find_squad_by_alias,
    }

    for entity_type, aliases in ALIASES.items():
        for alias in aliases:
            if finders[entity_type](alias) is None:
                raise ValueError(f"Не найден {entity_type}: {alias}")
```

---

## 11. Чек-лист разработчика

Перед сборкой проверьте:

- [ ] `ModProject.name` непустой и содержит допустимые символы.
- [ ] Все квесты и диалоги положены в `quests`/`dialogs` под ключом, равным их `id`.
- [ ] У каждого квеста есть этапы `0, 1, 2, ...` без пропусков.
- [ ] Ключ каждого этапа равен `Stage.id`.
- [ ] У каждого диалога есть реплика `id=0`.
- [ ] Ключ каждой реплики равен `Phrase.id`.
- [ ] Все `next_phrases` ссылаются на существующие реплики.
- [ ] Все `*_ru` и `*_en` заполнены.
- [ ] Все условия и действия имеют правильный `type`.
- [ ] Алиасы NPC/смартов/предметов/отрядов проверены через `GameDatabase`.
- [ ] Инфопоршни имеют уникальные имена с префиксом мода.
- [ ] Для гейтинга диалога используются предусловия реплик, а не только `Dialog.preconditions`.
- [ ] Для переходов этапов заданы `transfer_conditions` (или внешняя логика завершения).
- [ ] `Stage.on_start_actions` не используется для начального этапа `0`; для старта есть `Quest.on_init_actions`.
- [ ] Проект прогнан через `ProjectValidator`.
- [ ] `ModBuilder.build_project()` вернул `True`.
- [ ] Сборка проверена в игре через Mod Organizer 2.

---

## 12. Приложения

### 12.1. Полная карта полей моделей

#### `ModProject`

| Поле | Тип | Обязательное |
|---|---|---|
| `name` | `str` | Да |
| `required_mods` | `list[str]` | Нет |
| `quests` | `dict[str, Quest]` | Нет |
| `dialogs` | `dict[str, Dialog]` | Нет |

#### `Quest`

| Поле | Тип | Обязательное |
|---|---|---|
| `id` | `str` | Да |
| `title_ru` | `str` | Да |
| `title_en` | `str` | Да |
| `descr_ru` | `str` | Да |
| `descr_en` | `str` | Да |
| `is_storyline` | `bool` | Нет |
| `stages` | `dict[int, Stage]` | Да |
| `on_init_actions` | `list[Action]` | Нет |
| `on_complete_actions` | `list[Action]` | Нет |
| `on_fail_actions` | `list[Action]` | Нет |

#### `Stage`

| Поле | Тип | Обязательное |
|---|---|---|
| `id` | `int >= 0` | Да |
| `title_ru` | `str` | Да |
| `title_en` | `str` | Да |
| `descr_ru` | `str` | Да |
| `descr_en` | `str` | Да |
| `target_alias` | `str` | Да |
| `on_start_actions` | `list[Action]` | Нет |

#### `Dialog`

| Поле | Тип | Обязательное |
|---|---|---|
| `id` | `str` | Да |
| `npc_alias` | `str` | Да |
| `preconditions` | `list[Condition]` | Нет |
| `phrases` | `dict[int, Phrase]` | Да |

#### `Phrase`

| Поле | Тип | Обязательное |
|---|---|---|
| `id` | `int >= 0` | Да |
| `text_ru` | `str` | Да |
| `text_en` | `str` | Да |
| `next_phrases` | `list[int]` | Нет |
| `preconditions` | `list[Condition]` | Нет |
| `actions` | `list[Action]` | Нет |

### 12.2. Таблица Lua-трансляции

| Модель | Lua-код |
|---|---|
| `HasInfo(info="x")` | `has_alife_info("x")` |
| `DontHasInfo(info="x")` | `not has_alife_info("x")` |
| `HasItem(item_alias="x")` | `db.actor:object("x") ~= nil` (или `second_speaker:object(...)`) |
| `SmartOwner(smart_alias="s", faction="f")` | `mymod_quests.is_smart_captured("s", "f")` |
| `GiveInfo(info="x")` | `db.actor:give_info_portion("x")` |
| `RemoveInfo(info="x")` | `db.actor:disable_info_portion("x")` |
| `SpawnSquad(squad_alias="s", smart_alias="t")` | `mymod_quests.spawn_task_squad("s", "t")` |
| `SetTarget(squad_alias="s", smart_alias="t")` | `mymod_quests.set_task_target("s", "t")` |
| `GiveItem(item_alias="x")` | `dialogs.relocate_item_section(actor, "x", "in")` |
| `RemoveItem(item_alias="x")` | `dialogs.relocate_item_section(actor, "x", "out")` |
| `GiveMoney(amount=3000)` | `db.actor:give_money(3000)` |

### 12.3. API репозитория ассетов

`GameDatabase` — контекстный менеджер. Все методы только читают базу и логируют ошибки SQL, не роняя вызывающий код.

| Метод | Результат | Назначение |
|---|---|---|
| `GameDatabase(db_path, extra_dbs=[])` | — | Открыть SQLite; `extra_dbs` пока зарезервированы |
| `__enter__` / `__exit__` | — | Управление соединением |
| `find_npc_by_alias(alias)` | `dict \| None` | Найти NPC по алиасу |
| `find_smart_by_alias(alias)` | `dict \| None` | Найти смарт-террейн |
| `find_item_by_alias(alias)` | `dict \| None` | Найти предмет |
| `find_squad_by_alias(alias)` | `dict \| None` | Найти отряд; добавляет `npc_members` |
| `search_assets(query, entity_type=None)` | `list[dict]` | Живой поиск по имени, id и алиасу |
| `get_locations()` | `list[dict]` | Список локаций |
| `get_smart_terrains_by_location(prefix)` | `list[dict]` | Смарты локации |
| `get_npcs_by_location(prefix)` | `list[dict]` | NPC локации |
| `get_safe_squads_by_faction(faction)` | `list[dict]` | Безопасные полевые отряды фракции |
| `get_all_valid_aliases()` | `set[str]` | Множество всех алиасов |
| `print_assets_table(assets, title=...)` | `None` | Печать Rich-таблицы в терминал |

### 12.4. Глоссарий

| Термин | Значение |
|---|---|
| **Алиас** | Человекочитаемый идентификатор ассета из SQLite, например `esc.volk` |
| **Инфопоршень (info portion)** | Строковый флаг состояния мира, проверяемый `HasInfo` / `DontHasInfo` |
| **Смарт-террейн** | Точка ALife-симуляции, которой может владеть фракция |
| **Warfare** | Режим симуляции войны фракций в Anomaly |
| **Функтор** | Lua-функция, вызываемая task manager: `on_init`, `on_complete`, `on_fail`, `status_functor`, `target_functor` |
| **Дискриминатор** | Поле `type`, по которому Pydantic выбирает конкретный класс условия/действия |
| **Slug** | Безопасное латинское имя проекта для путей и Lua/LTX |
| **Round-trip** | Полный цикл «объект → JSON/YAML → объект» без потери данных |

---

**Конец документа.**
