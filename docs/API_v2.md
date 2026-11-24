# API справочник ядра квестов S.T.A.L.K.E.R. Anomaly

> **Статус документа:** единственный источник правды для внешних разработчиков и сторонних LLM.
> **Версия ядра:** стабилизированное ядро `src/core/models.py` + `src/compiler/*`.
> **Область применения:** Python 3.10+, Pydantic 2.x, S.T.A.L.K.E.R. Anomaly (X-Ray, Lua 5.1).

Этот файл описывает **весь публичный контракт** конструктора квестов: модели данных,
правила генерации игровых файлов, ограничения рантайма X-Ray и эталонный шаблон
сложного сюжета. Прочитав только `API_v2.md`, можно писать новые Python-скрипты квестов
без изучения исходников ядра.

## Единая архитектура и режимы применения

`docs/API_v2.md` — **единственное руководство** по декларативному конструктору
квестов Anomaly 1.5.3. Отдельного второго руководства «для Warfare» нет:
базовый режим конструктора — обычная свободная игра и сюжетные квесты
(**Story**), а **Warfare** — опциональная надстройка для захвата смартов.

| Маркер | Что означает |
|---|---|
| `[Общее]` | Элемент работает в freeplay, Story и Warfare. Ничего включать не нужно. |
| `[Story]` | Сюжетный путь: инфопоршни, `on_death`, `condlist_N`, `GiveTask`. Не требует Warfare и не вызывает `sim_squad_warfare`. |
| `[Warfare]` | Надстройка захвата точек: `WarfareCapture`, `requires_warfare=True`, `SetTarget`, `stage_cleared`. Работает только при включённом Warfare. |

Правило выбора:

1. Обычный сюжетный квест — `[Story]` + `[Общее]`; `requires_warfare` остаётся
   `False`, `WarfareCapture` не задаётся.
2. Квест на захват точки — `[Warfare]`; он помечается `world = true` и вне
   Warfare не тикает.
3. Смешивать захват и Story-спавн в одном `Quest` запрещено: валидатор
   возвращает ошибку. Разделяйте сценарий на два квеста.

Эталон Story-цепочки: `examples/build_story_relay.py`.

---

## Содержание

1. [Краткий гайд быстрого старта](#1-краткий-гайд-быстрого-старта-quick-start-guide)
2. [Полное обоснование и анатомия моделей](#2-полное-обоснование-и-анатомия-моделей-srccoremodelspy)
3. [Правила и ограничения сталкерского рантайма](#3-правила-и-ограничения-сталкерского-рантайма-x-ray--gamedata)
4. [Практический шаблон-руководство для сложных сюжетов](#4-практический-шаблон-руководство-для-сложных-сюжетов)

---

# 1. Краткий гайд быстрого старта (Quick Start Guide)

Ниже — пять шагов, после которых у вас есть валидный проект и готовый установочный
каталог мода. Все шаги выполняются в одном Python-файле, запускаемом из корня
проекта (там, где лежат каталоги `src/` и `examples/`).

## Шаг 1. Импортируйте модели и сборщик

```python
from pathlib import Path

from src.compiler.builder import ModBuilder
from src.core.models import (
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveTask,
    HasItem,
    ModProject,
    Phrase,
    Quest,
    Stage,
)
```

- `src.core.models` — строгие Pydantic-модели предметной области.
- `src.compiler.builder.ModBuilder` — оркестратор сборки: генерирует файлы мода,
  копирует и текстово патчит ванильные `system.ltx` и `character_desc_*.xml`.

## Шаг 2. Объявите квест и его этапы

Квест — это `Quest`, этапы — `Stage`. Ключи словаря `stages` обязаны совпадать с
`Stage.id`, а нумерация — идти подряд с нуля: `0, 1, 2, ...`.

```python
quest = Quest(
    id="my_first_quest",
    npc_id="cit_killers_merc_trader_stalker",
    npc_location="deadcity",
    dialog_id="my_first_take",
    title_ru="Мой первый квест",
    title_en="My first quest",
    descr_ru="Проверьте, что ядро собирает мод.",
    descr_en="Verify that the core builds a mod.",
    stages={
        0: Stage(
            id=0,
            title_ru="Найти предмет",
            title_en="Find the item",
            descr_ru="Найдите квестовый предмет.",
            descr_en="Find the quest item.",
            target_alias="deadcity.hospital",
        ),
    },
    transfer_conditions={
        0: {"complete": [HasItem(item_alias="itm_pda_common")]},
    },
)
```

## Шаг 3. Объявите диалог и граф реплик

Диалог — это `Dialog`, реплики — `Phrase`. В каждом диалоге обязательна стартовая
реплика `id=0`, и она **всегда принадлежит Игроку**. Далее действует правило:
чётные ID (`0`, `2`, `4`, ...) — реплики Игрока, нечётные (`1`, `3`, ...) —
реплики NPC. Ключи словаря `phrases` обязаны совпадать с `Phrase.id`. Каждый
элемент `next_phrases` обязан ссылаться на существующую реплику.

```python
take_dialog = Dialog(
    id="my_first_take",
    npc_alias="deadcity.dushman",
    npc_id="cit_killers_merc_trader_stalker",
    npc_location="deadcity",
    task_id="my_first_quest",
    role="take",
    preconditions=[DontHasInfo(info="my_first_quest_started")],
    phrases={
        0: Phrase(
            id=0,
            text_ru="Душман, есть работёнка?",
            text_en="Dushman, got any work?",
            next_phrases=[1],
        ),
        1: Phrase(
            id=1,
            text_ru="Есть. Возьмёшься?",
            text_en="I do. Will you take it?",
            next_phrases=[2, 4],
        ),
        2: Phrase(
            id=2,
            text_ru="Берусь.",
            text_en="I'm in.",
            actions=[
                GiveInfo(info="my_first_quest_started"),
                GiveTask(task_id="my_first_quest"),
            ],
            next_phrases=[3],
        ),
        3: Phrase(
            id=3,
            text_ru="Не подведи.",
            text_en="Don't let me down.",
        ),
        4: Phrase(
            id=4,
            text_ru="Не сейчас.",
            text_en="Not now.",
        ),
    },
)
```

## Шаг 4. Соберите `ModProject`

`ModProject` — корневой контейнер. Ключи `quests` обязаны совпадать с `Quest.id`;
ключи `dialogs` могут отличаться от `Dialog.id`, но сам XML и Lua всегда берут
канонический ID из модели (`dialog.dialog_id` или `dialog.id`).

```python
project = ModProject(
    name="My First Quest Mod",
    required_mods=[],
    quests={quest.id: quest},
    dialogs={take_dialog.id: take_dialog},
)
```

## Шаг 5. Запустите сборку

```python
builder = ModBuilder(
    output_dir=Path("output"),
    vanilla_root=Path("_unpacked"),  # распакованная ванильная игра
)

if not builder.build_project(project):
    raise SystemExit("Сборка не удалась: смотрите logs/app.log.")

print(f"Готовый мод: {builder.output_dir}")
```

После успешного вызова в `output/<slug>/gamedata` появятся:

- `configs/misc/task/tm_<slug>.ltx`;
- `configs/gameplay/dialogs_<slug>.xml`;
- `configs/text/rus/st_<slug>.xml` и `configs/text/eng/st_<slug>.xml`;
- `scripts/<slug>_quests.script`;
- пропатченная копия `configs/system.ltx`;
- пропатченные копии `configs/gameplay/character_desc_<level>.xml` для всех
  локаций, к которым привязаны диалоги.

> **Важно:** `_unpacked` читается только на этапе сборки. В тестах и при
> разработке моделей используйте временное fake-дерево, чтобы не зависеть от
> установленной игры.

### Чек-лист валидности перед сборкой

- [ ] У каждого `Quest` есть непустой `id`, хотя бы один этап и непрерывная
      нумерация этапов с `0`.
- [ ] Ключи `Quest.stages` совпадают с `Stage.id`.
- [ ] У каждого `Dialog` есть непустой `id`, стартовая фраза `id=0` и хотя бы одна
      фраза.
- [ ] Ключи `Dialog.phrases` совпадают с `Phrase.id`.
- [ ] Все `next_phrases` ссылаются на существующие фразы.
- [ ] Все `GiveTask.task_id` и `CompleteTask.task_id` ссылаются на существующие
      `Quest.id`.
- [ ] Все `Dialog.task_id`, `Quest.dialog_id` и `Quest.dialog_ids` ссылаются на
      существующие диалоги/квесты.
- [ ] Для диалогов, которые должны быть привязаны к NPC, заданы и `npc_id`, и
      `npc_location`.
- [ ] ID квестов и диалогов — валидные Lua-идентификаторы:
      `[A-Za-z_][A-Za-z0-9_]*`, без пробелов и зарезервированных слов Lua.
- [ ] `validate_project(project, db)` не возвращает `ERROR`
      (см. §3.6), либо `build_project(..., validate=True)` проходит.
- [ ] При модульной сборке `ModProject.merge(...)` не бросает `ValueError`,
      а `MergeValidator` не находит `MERGE-ID-001` (см. §2.13).

---

# 2. Полное обоснование и анатомия моделей (`src/core/models.py`)

## 2.1. Общая конфигурация и типы идентификаторов

Все модели наследуются от `pydantic.BaseModel` и используют единый
`ConfigDict`:

```python
_MODEL_CONFIG = ConfigDict(
    extra="allow",
    coerce_numbers_to_str=True,
    populate_by_name=True,
    validate_assignment=True,
)
```

Что это означает на практике:

| Настройка | Смысл |
|---|---|
| `extra="allow"` | Любые неизвестные колонки SQLite/JSON сохраняются в `model_extra` и **не теряются** при сериализации. Это критично для старых баз и полей метаданных Сталкера. |
| `coerce_numbers_to_str=True` | Числовые server/story ID из БД автоматически становятся строками, как того требует X-Ray. |
| `populate_by_name=True` | Модель можно создавать и по имени поля, и по алиасу. |
| `validate_assignment=True` | Присваивание полю после создания снова запускает валидаторы; граф нельзя испортить случайной мутацией. |

Два типа идентификаторов объявлены как `Annotated`-алиасы:

```python
OptionalId: TypeAlias = Annotated[
    str | None,
    BeforeValidator(_normalize_optional_id),
]
RequiredId: TypeAlias = Annotated[
    str,
    BeforeValidator(_require_non_empty_id),
]
```

- `OptionalId` нормализует `None`, пустую строку `""` и числовой `0` в `None`.
  Остальные числа приводятся к строкам благодаря `coerce_numbers_to_str`.
- `RequiredId` запрещает `None`, пустую строку и строку из одних пробелов.

## 2.2. Действия (`Action`)

`Action` — дискриминируемый union по полю `type`. В коде используйте конкретные
классы, а не словари.

| Класс | `type` | Режим | Поля | Что генерируется / делает |
|---|---|---|---|---|
| `GiveInfo` | `"give_info"` | `[Общее]` | `info: RequiredId` | В реплике — `<give_info>info</give_info>`. В квесте/этапе — Lua `db.actor:give_info_portion(info)`. |
| `RemoveInfo` | `"remove_info"` | `[Общее]` | `info: RequiredId` | Lua `db.actor:disable_info_portion(info)`. |
| `SpawnSquad` | `"spawn_squad"` | `[Общее]`; `mode="warfare"` — `[Warfare]`, `mode="story"` — `[Story]` | `squad_alias: str`, `smart_alias: str`, `mode: "warfare" \| "story" = "warfare"` | `warfare`: `SIMBOARD:create_squad` + `sim_squad_warfare.set_target` + заморозка. `story`: `SIMBOARD:create_squad` без `set_target`, `stay_time` и `force_online`; цель берётся из `target_smart` секции отряда. |
| `SetTarget` | `"set_target"` | `[Warfare]` | `squad_alias: str`, `smart_alias: str` | Lua `sim_squad_warfare.set_target`. |
| `SpawnNpcItem` | `"spawn_npc_item"` | `[Общее] / [Story]` | `item_alias: str`, `target_alias: str`, `count: int = 1` (`ge=1`) | Lua `spawn_npc_item(...)`: резолвит NPC через `resolve_alife_object`/`get_story_squad`, для отряда берёт `commander_id()` и кладёт предмет в инвентарь командира через `alife_create_item(section, npc)` в цикле `1..count`. Уведомления `news_manager` не выводятся: предмет предназначен для лута. |
| `GiveItem` | `"give_item"` | `[Общее]` | `item_alias: str`, `count: int = 1` (`ge=1`) | Lua `give_item(...)`: `alife_create_item(section, actor)` по одному и одно уведомление `news_manager.relocate_item(actor, "in", section, count)`. Алиас разрешается в реальную секцию. |
| `RemoveItem` | `"remove_item"` | `[Общее]` | `item_alias: str`, `count: int = 1` (`ge=1`) | Lua `take_item(...)`: прямое изъятие из инвентаря игрока через `actor:iterate_inventory` + `alife_release`. |
| `TakeItem` | `"take_item"` | `[Общее]` | `item_alias: str`, `count: int = 1` (`ge=1`) | Семантический алиас `RemoveItem`: та же реализация `take_item`; ровно одно уведомление `news_manager.relocate_item(..., "out", ...)` при `removed > 0`. |
| `GiveMoney` | `"give_money"` | `[Общее]` | `amount: int` (`ge=0`) | Lua `give_money(...)`: `actor:give_money(amount)` и одно уведомление `news_manager.relocate_money(actor, "in", amount)`. |
| `TakeMoney` | `"take_money"` | `[Общее]` | `amount: int` (`ge=0`) | Lua `take_money(...)`: списание с ограничением по текущему балансу, без ухода в минус. |
| `GiveTask` | `"give_task"` | `[Общее]` | `task_id: RequiredId` | Единственное действие реплики — `<action>dialogs.<текущий_dialog_id>_accept</action>`; в Lua — `give_task`. В комбинации с другими действиями сливается в единую `dialogs.<dialog_id>_phrase_<n>_action`. |
| `CompleteTask` | `"complete_task"` | `[Общее]` | `task_id: RequiredId` | Единственное действие реплики — `<action>dialogs.<текущий_dialog_id>_turn_in</action>`; в Lua — `complete_task`. В комбинации с другими действиями сливается в единую `dialogs.<dialog_id>_phrase_<n>_action`. |
| `RemoveSquad` | `"remove_squad"` | `[Story]` | `squad_alias: str` | Lua `get_story_squad(alias)` → `SIMBOARD:remove_squad(squad)`. Если отряд уже мёртв/не найден — безопасный no-op. Используется в `Quest.on_fail_actions` для очистки Story-отряда. |
| `ClearSmart` | `"clear_smart"` | `[Story]` | `smart_alias: str`, `faction: str \| None = None`, `keep_story_ids: list[str] = []`, `allow_giver_smart: bool = False` | Lua `clear_smart(...)`: удаляет ванильные и не-сюжетные отряды на смарте **перед** спавном квестового. Пропускает актора, компаньонов, `keep_story_ids`, Story-отряды и отряды текущего квеста; при заданном `faction` — только отряды этой фракции. Не меняет владельца смарта. |

> **`ClearSmart` — только Story и строго до `SpawnSquad`.**
> `ClearSmart` вызывается **до** `SpawnSquad` в одном и том же списке
> `on_start_actions`: иначе действие удалит только что созданный квестовый
> отряд. Оно несовместимо с `WarfareCapture` в одном квесте (используйте
> отдельный Story-квест). Если `smart_alias` совпадает со смартом
> квестодателя, требуется явный `allow_giver_smart=True`; без него
> `XrayLinter` возвращает `ERROR XRAY-SPAWN-001`. Повторный вызов
> идемпотентен (no-op).
>
> ```python
> on_start_actions=[
>     ClearSmart(smart_alias=SPAWN_SMART, faction="bandit"),
>     SpawnSquad(squad_alias=SQUAD, smart_alias=SPAWN_SMART, mode="story"),
>     SpawnNpcItem(item_alias=ITEM, target_alias=SQUAD, count=1),
> ]
> ```

> **Story-спавн.** `SpawnSquad(mode="story")` — штатный способ создать
> сюжетный отряд. Действие вызывает `SIMBOARD:create_squad(spawn_smart, section)`,
> **не** вызывает `sim_squad_warfare.set_target`, **не** ставит `stay_time` и
> **не** включает `force_online`. Отряд идёт к `target_smart` из своей секции
> `squad_descr_<slug>.ltx` и обслуживается `sim_squad_scripted`. Спавн
> идемпотентен: для `on_init_actions` используется ключ `_init_spawn`, для
> `Stage.on_start_actions` — `_story_spawn`.

> **`RemoveSquad`.** Story-отряд удаляется через `RemoveSquad(squad_alias=...)`
> в `Quest.on_fail_actions` (эффекты `on_fail`/`on_cancel`). Действие не
> падает, если отряд уже уничтожен. Оно не предназначено для Warfare-отрядов:
> те освобождаются через `unmark_quest_squads`.

> **Ровно один `<action>` на реплику.** Движок X-Ray/OpenXRay хранит
> **одно** действие на `<phrase>` и молча отбрасывает второй и последующие
> теги `<action>`. Поэтому компилятор обязан сгенерировать не более одного
> такого тега:
>
> - только `GiveInfo` → `<action>` не нужен (остаются нативные `<give_info>`);
> - одиночный `GiveTask` → `<action>dialogs.<dialog_id>_accept</action>`;
> - одиночный `CompleteTask` → `<action>dialogs.<dialog_id>_turn_in</action>`;
> - любая другая комбинация (включая `GiveTask`/`CompleteTask` вместе с
>   `GiveMoney`, `GiveItem`, `RemoveItem`, `TakeItem`, `TakeMoney`,
>   `RemoveInfo`, `SpawnSquad`, `SetTarget`) → **одна** функция
>   `dialogs.<dialog_id>_phrase_<n>_action`, внутри которой все Lua-действия
>   исполняются строго в порядке объявления в `Phrase.actions`.
>
> `GiveInfo` всегда остаётся нативным тегом `<give_info>` и в слиянии не
> участвует. Порядок тегов в реплике: `<text>` → `<next>` →
> `<precondition>` → `<has_info>`/`<dont_has_info>` → `<give_info>` →
> `<action>`.

Примеры:

```python
from src.core.models import (
    ClearSmart,
    CompleteTask,
    GiveInfo,
    GiveItem,
    GiveMoney,
    GiveTask,
    RemoveItem,
    SetTarget,
    SpawnSquad,
    TakeItem,
    TakeMoney,
)

# Story: ClearSmart строго перед SpawnSquad(mode="story").
story_actions = [
    GiveInfo(info="my_quest_started"),
    ClearSmart(smart_alias="deadcity.hospital", faction="bandit"),
    SpawnSquad(
        squad_alias="squad.killer_advanced",
        smart_alias="deadcity.hospital",
        mode="story",
    ),
]

# Warfare: SpawnSquad(mode="warfare") + SetTarget. ClearSmart здесь запрещён.
warfare_actions = [
    SpawnSquad(
        squad_alias="squad.killer_advanced",
        smart_alias="deadcity.hospital",
        mode="warfare",
    ),
    SetTarget(squad_alias="squad.killer_advanced", smart_alias="deadcity.hospital"),
]

item_actions = [
    GiveItem(item_alias="wpn_ak74", count=1),
    RemoveItem(item_alias="itm_pda_common", count=1),
    TakeItem(item_alias="itm_pda_common", count=1),
    GiveMoney(amount=50000),
    TakeMoney(amount=2500),
]

# GiveTask и CompleteTask — взаимоисключающие действия разных реплик.
task_actions = [GiveTask(task_id="my_quest")]  # или CompleteTask(task_id=...)
```

> **Алиасы и секции.** Поля `item_alias` в `GiveItem`/`RemoveItem`/`TakeItem`
> и `item_alias` в `HasItem` принимают как прямую секцию (`itm_pda_common`,
> `wpn_ak105`), так и алиас из `data/anomaly_db.sqlite`. Если генератор получил
> `db_client`, алиас разрешается в секцию на этапе компиляции, а при
> отсутствии записи в БД выводится **warning** (строка используется как есть,
> сборка не падает). Без БД или при ошибке запроса строка также используется
> как есть. Warning важен: несуществующая секция иначе даёт молчаливый no-op
> в игре (`give_item` только пишет `printe` в лог).

> **Секции отрядов в `SpawnSquad.squad_alias`/`SetTarget.squad_alias`.**
> Это всегда секция/игровой ID **отряда** (`squad.killer_advanced`,
> `merc_sim_squad_advanced`, `squad.army_advanced`), а не NPC-шаблон.
> `sim_default_stalker_1` — NPC-секция и как `squad_alias`/`ally_squad_alias`
> запрещена (`CAT-WARFARE-001`/`CAT-SQUAD-001`). Секция
> `squad.mercenary_advanced` в БД Anomaly 1.5.3 отсутствует — используйте
> `squad.killer_advanced` (игровой ID `merc_sim_squad_advanced`).

> **Порядок `SpawnSquad` → `SpawnNpcItem`.** Если `SpawnNpcItem.target_alias`
> указывает на `CustomSquad`, действие обязано идти **после** `SpawnSquad`
> в том же списке `on_start_actions`. Для отряда принимается
> `CustomSquad.id`/`story_id`, но без заданного `story_id` командир не
> гарантирован (`CAT-SQUAD-002`/`XRAY-SPAWNITEM-002`). Если командир не
> найден, предмет не создаётся.

> **Уведомления при изъятии предмета.** `TakeItem`/`RemoveItem` удаляют
> предметы напрямую через `actor:iterate_inventory` и `alife_release`. Сообщение
> о передаче выводится ровно один раз — вызовом
> `news_manager.relocate_item(actor, "out", section, removed)` и только если
> хотя бы один предмет действительно был изъят. Ванильные
> `dialogs.relocate_item_section` и `itms_manager.relocate_item_from_actor` не
> используются: в Anomaly 1.5.3 они приводили к дублированию сообщения
> «Потерян предмет».

> **Уведомления при выдаче наград.** `GiveMoney` после начисления вызывает
> `news_manager.relocate_money(actor, "in", amount)`, а `GiveItem` — одно
> `news_manager.relocate_item(actor, "in", section, count)` на всю выданную
> стопку. Это показывает стандартные иконки денег/оружия в окне диалога.
> `GiveItem` всегда получает уже разрешённую секцию (`wpn_val_modern_kobra`), а
> не алиас из БД, поэтому в КПК отображается переведённое название предмета.

> **Семантика `GiveTask`/`CompleteTask` в XML:** если действие в реплике
> единственное, оно ссылается на **текущий диалог**:
> `dialogs.<dialog_id>_accept` или `dialogs.<dialog_id>_turn_in`. Если рядом
> есть другие Lua-действия, отдельного тега для задачи нет: `GiveTask` и
> `CompleteTask` становятся элементами массива `run_actions` единой функции
> `dialogs.<dialog_id>_phrase_<n>_action`. Имя квеста берётся из связи
> `Dialog.task_id` (или обратной связи `Quest.dialog_id`/`Quest.dialog_ids`).

## 2.3. Условия (`Condition`)

`Condition` — дискриминируемый union по полю `type`.

| Класс | `type` | Режим | Поля | Где проверяется |
|---|---|---|---|---|
| `HasInfo` | `"has_info"` | `[Общее]` / `[Story]` | `info: RequiredId` | XML `<has_info>`; Lua `has_alife_info(info)`. Основной контракт Story-завершения. |
| `DontHasInfo` | `"dont_has_info"` | `[Общее]` / `[Story]` | `info: RequiredId` | XML `<dont_has_info>`; Lua `not has_alife_info(info)`. |
| `HasItem` | `"has_item"` | `[Общее]` / `[Story]` | `item_alias: str`, `count: int = 1` (`ge=1`) | Только Lua: подсчёт стаков в инвентаре `actor_item_count(item, actor) >= count`. Выносится в `dialogs.<...>_precondition` или `dialogs.<dialog_id>_can_take`. В `condlist` поддерживается как `actor_has_item`/`actor_has_item_amount`. |
| `HasMoney` | `"has_money"` | `[Общее]` | `amount: int` (`ge=0`) | Только Lua: `db.actor:money() >= amount`. В `Quest.extra_condlists` (`[Story]`) не поддерживается — `BuildError`. |
| `SmartOwner` | `"smart_owner"` | `[Warfare]` | `smart_alias: str`, `faction: str` | Только Lua: `SIMBOARD.smarts_by_names[smart_alias].owning_faction == faction`. В `Quest.extra_condlists` (`[Story]`) не поддерживается — `BuildError`. |

Пример:

```python
from src.core.models import (
    DontHasInfo,
    HasInfo,
    HasItem,
    HasMoney,
    SmartOwner,
)

conditions = [
    HasInfo(info="my_quest_started"),
    DontHasInfo(info="my_quest_done"),
    HasItem(item_alias="itm_pda_common", count=2),
    HasMoney(amount=50000),
    SmartOwner(smart_alias="deadcity.hospital", faction="army"),
]
```

> **Подсчёт `HasItem`.** Условие учитывает количество в стаке: два ПДА или
> патроны с `count()` суммируются. Для одиночных предметов поведение прежнее.
> `HasItem` принимает и прямую секцию, и алиас БД (см. примечание в 2.2).

> **Важно:** `HasInfo` и `DontHasInfo` имеют штатные XML-теги и не создают
> Lua-функцию. Все остальные условия не представимы тегами X-Ray, поэтому
> генератор создаёт Lua-функцию с канонической сигнатурой `(actor, npc, p)` и
> ссылается на неё из XML как `dialogs.<flat_function_name>`.

> **Ловушка при сдаче квеста:** не задавайте `HasItem` или `SmartOwner` в
> `Dialog.preconditions` у turn-in диалога. Любое не-info условие уровня
> диалога генерирует `dialogs.<dialog_id>_can_take`, а `_can_take` возвращает
> `false`, если задача уже выдана. Для проверки предмета при сдаче используйте
> `Phrase.preconditions` (как в примере раздела 4).

> **Одноразовые квесты.** Для диалога с `role="take"` (а также `take_assault`,
> `take_solo`, ...) генератор `xml_gen.py` всегда добавляет
> `<precondition>dialogs.<dialog_id>_can_take</precondition>`, даже если все
> условия заданы простыми info-тегами. Сгенерированная `_can_take` возвращает
> `false`, если у актора уже есть `Quest.complete_info` или `Quest.done_info`,
> либо задача всё ещё активна в `task_manager`. Поэтому после успешной сдачи
> стартовый диалог не открывается повторно. `taken_info` при успехе не
> снимается — только `_cleanup` (провал/отмена) очищает его.

## 2.4. `Phrase` — одна реплика диалога

```python
class Phrase(BaseModel):
    model_config = _MODEL_CONFIG

    id: int
    text_ru: str = ""
    text_en: str = ""
    next_phrases: list[int] = []
    preconditions: list[Condition] = []
    actions: list[Action] = []
```

| Поле | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `id` | `int` (`ge=0`) | обязательное | Целочисленный ID реплики внутри диалога. |
| `text_ru` | `str` | `""` | Русский текст реплики. |
| `text_en` | `str` | `""` | Английский текст реплики. |
| `next_phrases` | `list[int]` | `[]` | ID следующих реплик. Каждый элемент становится отдельным парным тегом `<next>ID</next>`. |
| `preconditions` | `list[Condition]` | `[]` | Условия показа реплики. |
| `actions` | `list[Action]` | `[]` | Действия при выборе реплики. |

Правила:

1. `Phrase.id` — целое число `>= 0`.
2. Ключ в `Dialog.phrases` обязан совпадать с `Phrase.id`.
3. `next_phrases` может быть пустым — это конечная реплика ветки.
4. Каждый ID в `next_phrases` обязан существовать в том же диалоге.
5. Текст реплики попадает в `st_<mod>.xml` под ID
   `<dialog_id>_phrase_<id>_text`.

## 2.5. `Dialog` — диалог NPC с деревом реплик

```python
class Dialog(BaseModel):
    model_config = _MODEL_CONFIG

    id: RequiredId
    dialog_id: OptionalId = None
    npc_alias: str = ""
    npc_id: OptionalId = None
    npc_location: str | None = None
    task_id: OptionalId = None
    role: str | None = None
    preconditions: list[Condition] = []
    phrases: dict[int, Phrase] = {}
```

| Поле | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `id` | `RequiredId` | обязательное | Канонический ID диалога. Именно он попадает в `<dialog id="...">` и `<actor_dialog>`. |
| `dialog_id` | `OptionalId` | `None` | Дублирующий ID. Автоматически синхронизируется с `id` валидатором `_sync_dialog_id`. |
| `npc_alias` | `str` | `""` | Человекочитаемый алиас NPC. На привязку не влияет. |
| `npc_id` | `OptionalId` | `None` | Точный `<specific_character id="...">` из `character_desc_<level>.xml`. |
| `npc_location` | `str \| None` | `None` | Имя локации (`deadcity`, `escape`, `zaton`, ...). Выбирает `character_desc_<level>.xml`. |
| `task_id` | `OptionalId` | `None` | ID связанного квеста (`Quest.id`) для `GiveTask`/`CompleteTask` и `_can_take`/`_can_turn_in`. |
| `role` | `str \| None` | `None` | Роль: `take`, `take_assault`, `take_solo`, `turnin`, `turn_in`, `branch`. Влияет на порядок вставки `<actor_dialog>`. Для `take`/`take_*` диалог всегда получает `<precondition>dialogs.<dialog_id>_can_take</precondition>`, который блокирует повторное взятие после выдачи `complete_info`. Для `turnin`/`turn_in` с заданным `task_id` и без ручных не-info условий диалог получает `<precondition>dialogs.<dialog_id>_can_turn_in</precondition>`: доступ проверяется по стадии задачи (`tsk.stage >= Quest.return_to_giver_stage`), а не по поршню из `on_start_actions`. |
| `preconditions` | `list[Condition]` | `[]` | Условия доступности всего диалога. |
| `phrases` | `dict[int, Phrase]` | `{}` | Карта реплик. Ключ обязан совпадать с `Phrase.id`. |

Валидаторы `Dialog`:

1. `id` не может быть пустым.
2. `npc_location` обрезается по краям; пустая строка превращается в `None`.
3. `dialog_id` всегда приравнивается к `id`.
4. Диалог обязан содержать хотя бы одну фразу.
5. Стартовая фраза `id=0` обязательна.
6. Ключи `phrases` обязаны совпадать с `Phrase.id`.
7. Все `next_phrases` обязаны ссылаться на существующие фразы.

> **Обязательное правило порядка реплик.** В любом `<actor_dialog>` первую
> реплику произносит Игрок: `Phrase(id=0)` — Игрок, `Phrase(id=1)` — NPC,
> `Phrase(id=2)` — снова Игрок и так далее. Чётные ID (`0`, `2`, `4`, ...)
> принадлежат Игроку, нечётные (`1`, `3`, ...) — NPC. Если нужно показать
> несколько вариантов ответа Игрока, используйте чётные ID, а нечётные
> оставляйте за NPC.

Порядок ролей при вставке `<actor_dialog>`:

```text
take            -> 0
take_assault    -> 1
take_solo       -> 2
turnin/turn_in  -> 3
branch          -> 4
неизвестная     -> 99
```

> **Без дублирования info-условий.** `HasInfo`/`DontHasInfo` уровня диалога
> генератор выносит в нативные теги `<has_info>`/`<dont_has_info>` и **не**
> повторяет их внутри `_can_take`. В Lua попадают только не-info условия
> (`HasItem`, `HasMoney`, `SmartOwner`) и встроенные проверки
> `complete_info`/`done_info`/`task_info`/фракции/Warfare. Это правило
> действует и для диалога сдачи: если у него есть ручное не-info условие,
> используется общий `_can_take`; иначе — `_can_turn_in` по стадии задачи.

## 2.6. `WarfareCapture` — опциональный сценарий захвата смарта `[Warfare]`

`[Warfare]` — это надстройка, а не базовый режим. Поле `Stage.warfare_capture`
включает `world = true`, и `_start`/`_status` работают только при
`IsWarfare() == true`. Story-квесты **не задают** `WarfareCapture` и не
смешивают его со `SpawnSquad(mode="story")` в одном `Quest`.

```python
class WarfareCapture(BaseModel):
    model_config = _MODEL_CONFIG

    smart_alias: str
    enemy_squad_alias: str
    ally_squad_alias: str | None = None
    ally_count: int = 0
```

| Поле | Режим | Тип | По умолчанию | Назначение |
|---|---|---|---|---|
| `smart_alias` | `[Warfare]` | `str` | обязательное | Алиас смарт-террейна, который нужно захватить. |
| `enemy_squad_alias` | `[Warfare]` | `str` | обязательное | Секция вражеского отряда, который нужно уничтожить. |
| `ally_squad_alias` | `[Warfare]` | `str \| None` | `None` | Секция союзного отряда, который спавнится на помощь. |
| `ally_count` | `[Warfare]` | `int` (`ge=0`) | `0` | Сколько союзных отрядов заспавнить. |

Если `Stage.warfare_capture` задан, Lua-генератор включает автоматическую логику:

- `spawn_stage_for` спавнит вражеский отряд (и союзников) один раз за этап;
- `freeze_stage_for` замораживает отряды на точке: `freeze_squad` выставляет
  `stay_time` только отряду с `squad.current_action == 1` (то есть уже
  дошедшему до цели), затем `force_online` и `mark_task_squad`;
- `stage_cleared` проверяет, что вражеский отряд уничтожен, а смарт захвачен
  (`smart.owning_faction == "army"` или `smart.defense_count <= 0`);
- `unmark_quest_squads` при завершении/провале снимает отряды с
  `sim_offline_combat.task_squads`.

### Автоматический учёт отрядов из `SpawnSquad`

Отряды, заспавненные действием `SpawnSquad` в реплике диалога или в
`on_start_actions`/`on_init_actions`, учитываются автоматически, даже если они
не объявлены в `WarfareCapture`:

1. `run_actions(actions, actor, npc, quest_id)` получает id связанного квеста
   (для диалога — `Dialog.task_id` или обратная ссылка `Quest.dialog_id`/
   `Quest.dialog_ids`; для функций квеста — собственный `quest_id`).
2. `register_dyn_squad(quest_id, squad)` увеличивает счётчик
   `<prefix>_<quest_id>_dyn_squad_cnt` и сохраняет `squad.id` в
   `<prefix>_<quest_id>_dyn_squad_<n>` (pstor).
3. `<quest_id>_start` **не** сбрасывает `..._dyn_squad_cnt`: отряды могут
   быть заспавнены в реплике диалога **до** `give_task`, и сброс счётчика в
   `_start` обнулил бы уже зарегистрированные отряды. Счётчик сбрасывается в
   `0` в `<quest_id>_reward` и `<quest_id>_cleanup` строго после вызова
   `unmark_quest_squads`.
4. `<quest_id>_status` каждый тик вызывает `freeze_dyn_squads(quest)`, который
   морозит все зарегистрированные отряды через `freeze_squad`.
5. `<quest_id>_reward`/`<quest_id>_cleanup` вызывают `unmark_quest_squads`,
   который освобождает и `capture`-отряды, и все динамические
   `..._dyn_squad_<n>` из `sim_offline_combat.task_squads`; сразу после этого
   `..._dyn_squad_cnt` сбрасывается в `0`.

Поэтому `SpawnSquad` в реплике больше не создаёт «неуправляемый» отряд: он
попадает в pstor, замораживается на точке и освобождается вместе с квестом.

> **Рекомендация.** Если отряд должен участвовать в проверке зачистки
> (`stage_cleared`), объявляйте его через
> `WarfareCapture.enemy_squad_alias`/`ally_squad_alias`: только эти отряды
> входят в `capture.ally_count` и проверяются как цель этапа. `SpawnSquad` в
> реплике удобен для подкрепления и сопровождения.

> **Ограничение рантайма:** при наличии `warfare_capture` квест помечается как
> `world = true`, и его `_status` не работает вне режима Warfare
> (`IsWarfare() == false`). Для обычных сюжетных квестов не задавайте
> `warfare_capture`. Явный `Quest.requires_warfare=True` действует так же,
> даже без `warfare_capture`.

> **Запрет смешивания `[Warfare]` и `[Story]`.** Если в одном `Quest` есть
> `warfare_capture` **и** `SpawnSquad(mode="story")`, `ProjectValidator`
> возвращает ошибку. Причина — `world`-гейт: Story-отряд не должен зависеть
> от Warfare. Разделяйте сценарий на два квеста.

## 2.7. `Stage` — один этап квеста `[Общее]`

```python
class Stage(BaseModel):
    model_config = _MODEL_CONFIG

    id: int
    title_ru: str = ""
    title_en: str = ""
    msg_complete_ru: str | None = None
    msg_complete_en: str | None = None
    descr_ru: str = ""
    descr_en: str = ""
    descr_variants: list[DescrVariant] = []
    target_alias: str = ""
    target_variants: list[TargetVariant] = []
    target_squad_id: str | None = None
    on_start_actions: list[Action] = []
    warfare_capture: WarfareCapture | None = None
```

| Поле | Режим | Тип | По умолчанию | Назначение |
|---|---|---|---|---|
| `id` | `[Общее]` | `int` (`ge=0`) | обязательное | Номер этапа. Ключ в `Quest.stages` обязан совпадать. |
| `title_ru` | `[Общее]` | `str` | `""` | Русский заголовок этапа. |
| `title_en` | `[Общее]` | `str` | `""` | Английский заголовок этапа. |
| `msg_complete_ru` | `[Общее]` | `str \| None` | `None` | Текст уведомления КПК при **завершении** этапа. `None` → «Этап выполнен: <title_ru>.». |
| `msg_complete_en` | `[Общее]` | `str \| None` | `None` | То же для английского языка; `None` → «Stage completed: <title_en>.». |
| `descr_ru` | `[Общее]` | `str` | `""` | Русское описание этапа. |
| `descr_en` | `[Общее]` | `str` | `""` | Английское описание этапа. |
| `descr_variants` | `[Story]` | `list[DescrVariant]` | `[]` | Варианты описания по инфопоршням/предметам. Проверяются по порядку; первый подошедший побеждает. |
| `target_alias` | `[Общее]` | `str` | `""` | Цель маркера: имя смарта, числовой server ID или story ID. |
| `target_variants` | `[Story]` | `list[TargetVariant]` | `[]` | Варианты цели маркера по условиям. Первый подошедший побеждает; иначе используется `target_alias`. |
| `target_squad_id` | `[Общее]` | `str \| None` | `None` | ID/секция/алиас отряда, который нужно физически уничтожить. Включает автоматическую проверку в `_status`. Для Story-отряда обычно указывается его `story_id`. |
| `on_start_actions` | `[Общее]` | `list[Action]` | `[]` | Действия, выполняемые ровно один раз при входе в этап. `SpawnSquad(mode="story")` здесь также допустим. |
| `warfare_capture` | `[Warfare]` | `WarfareCapture \| None` | `None` | Включает автоматическую логику захвата смарта. Только для Warfare. |

### Варианты цели и описания `[Story]`

```python
class TargetVariant(BaseModel):
    when: list[Condition]   # min_length=1
    value: str              # min_length=1

class DescrVariant(BaseModel):
    when: list[Condition]   # min_length=1
    text_ru: str = ""
    text_en: str = ""
```

Семантика:

1. Варианты проверяются в порядке объявления.
2. Побеждает первый вариант, у которого **все** условия `when` истинны.
3. Если ни один не подошёл, используются базовые `target_alias` и `descr_ru/en`.
4. XML-строки вариантов получают стабильные ключи
   `<quest_id>_stage_<n>_descr_v1`, `_v2`, …; индексы не зависят от локали.
5. Пустой `when` — ошибка валидации.

### Три семантики смарта: маркер / спавн / назначение

Это главная ловушка Phase 3. Три поля с `alias`/`smart` **не взаимозаменяемы**:

| Поле | Что означает | Где используется | Типичная ошибка |
|---|---|---|---|
| `Stage.target_alias` | Цель **маркера** в КПК. Не точка спавна. | `target_functor` | Считать, что это место появления отряда. |
| `SpawnSquad.smart_alias` | Точка **спавна** отряда. | `spawn_squad`/`create_squad` | Спавн врага на смарте квестодателя → мгновенный бой и гибель NPC. |
| `CustomSquad.target_smart` | Точка **назначения**; куда отряд идёт после спавна. | секция `squad_descr_*.ltx` | Совпадение с точкой спавна → отряд не марширует. |

Правильный пример: спавн на `zat_b7`, марш к `zat_b52`, маркер — на
`zat_b7` (или на цели, если игрок должен идти туда):

```python
Stage(
    id=0,
    target_alias="zat_b7",                       # маркер КПК
    on_start_actions=[
        SpawnSquad(
            squad_alias=SQUAD,
            smart_alias="zat_b7",                # точка спавна
            mode="story",
        ),
    ],
)
# CustomSquad(SQUAD, ..., target_smart="zat_b52")  # точка назначения
```

> **Жёсткое правило.** Вражеский отряд **не должен** спавниться на смарте
> квестодателя (`XRAY-SPAWN-001`/`CAT-SMART-003`). `target_alias` —
> независимое поле маркера: оно не задаёт ни спавн, ни маршрут.

Как работает `target_alias`:

```text
1. Если имя есть в SIMBOARD.smarts_by_names -> возвращается smart.id.
2. Если строка — число -> alife_object(number).id.
3. Иначе -> get_story_object_id(name); полученный числовой story-id
   проверяется через alife_object(story_id).id.
4. Если ничего не найдено -> nil.
```

`get_story_object_id(name)` — штатный способ Anomaly 1.5.3 превратить
строковое имя story-объекта в числовой ID. Движковый поиск story-объекта
принимает **только числовой** story-id; передача строки возвращает `nil`,
поэтому имя обязано сначала пройти через `get_story_object_id(name)`.

Если `target_alias` пуст, `target_functor` резолвит цель в таком порядке:

```text
1. tsk.task_giver_id, если он задан и ~= 0.
2. get_story_object_id(Quest.npc_id) (через resolve_target).
3. nil, если квестодатель не найден.
```

`0` в Lua является truthy, поэтому проверка `~= 0` обязательна: иначе
`task_manager` принимает актора за квестодателя и рисует жёлтую метку на
игроке вместо NPC. Возврат `nil` также означает «цель неизвестна» — маркер
не должен вешаться на актора.

`on_start_actions` выполняются Lua-функцией `_status` при первом обнаружении
текущего этапа. Факт выполнения сохраняется в pstor-ключе
`<...>_v_<stage>_started`, поэтому действия не повторяются после загрузки
сохранения. Исключение — `GiveItem`: такой предмет выдаётся **идемпотентно**
на каждом тике `_status`, пока его количество в инвентаре меньше заданного
`count` (например, выброшенный ПДА возвращается). Это не касается
`taken_info`/`complete_info`: они управляются только `_start`/`_reward`/
`_cleanup`.

> **Важно при `world = true`/`requires_warfare`.** Вне Warfare `_status` не
> тикает (возвращает `nil`), поэтому `on_start_actions` не выполнятся вовсе.
> Критичные поршни (например, `*_ready`) выпускайте в
> `Quest.on_init_actions`, а не в `Stage.on_start_actions`. Идемпотентный
> `GiveItem` в `on_start_actions` тоже не сработает, пока Warfare не
> включён; если предмет обязателен для не-Warfare сценария, используйте
> `Quest.on_init_actions` или отдельный этап без `warfare_capture`.

### Автоматическое отслеживание ликвидации отряда (`target_squad_id`)

Если у этапа задано `target_squad_id`, генератор добавляет в
`<quest_id>_status` проверку `target_squad_dead(quest, stage)` **до** обычных
условий `transfer_conditions`. Когда целевой отряд уничтожен, этап продвигается
тем же кодом, что и при выполнении `complete`-условий; последний этап
возвращает `"complete"`.

```python
from src.core.models import Quest, Stage

quest = Quest(
    id="my_kill_quest",
    npc_id="esc_mayor",
    stages={
        0: Stage(
            id=0,
            target_squad_id="esc_3_16_military_trader_squad",
        ),
        # ... последующие этапы
    },
)
```

`target_squad_id` принимает:

- числовой server ID (`"12345"`) — `alife_object(id)`;
- строковое story-имя — `get_story_object(name)` /
  `get_story_squad(name)` либо `get_story_object_id(name)` +
  `alife_object(story_id)`;
- секцию/алиас отряда из `SIMBOARD.squads` (при наличии) или БД.

Рантайм-проверка использует проверенные вызовы эталона:
`resolve_alife_object` → `alife_object`/`get_story_object`/
`get_story_squad`/`get_story_object_id`/`SIMBOARD.squads`, а признак смерти —
`squad:npc_count() <= 0` под `pcall`. Строковое имя всегда резолвится через
`get_story_object_id(name)`; числовой story-id допустим только после такого
резолва.

> **Защита от преждевременного завершения.** Этап не завершится, пока отряд
> хотя бы раз не был обнаружен живым. Факт обнаружения хранится в pstor-ключе
> `<mod_prefix>_<quest_id>_v_<stage>_target_seen`; он сбрасывается в `_start`.
> Это не даёт «мёртвому»/ещё не заспавненному отряду закрыть этап сразу.

Если `target_alias` пуст, `target_functor` использует `target_squad_id` как
источник маркера цели.

## 2.8. `Quest` — сюжетный квест `[Общее] / [Story] / [Warfare]`

```python
class Quest(BaseModel):
    model_config = _MODEL_CONFIG

    id: RequiredId
    giver_npc_id: OptionalId = None
    npc_id: OptionalId = None
    npc_location: str | None = None
    dialog_id: OptionalId = None
    dialog_ids: list[str] = []
    title_ru: str = ""
    title_en: str = ""
    descr_ru: str = ""
    descr_en: str = ""
    msg_reward_ru: str | None = None
    msg_reward_en: str | None = None
    msg_fail_ru: str | None = None
    msg_fail_en: str | None = None
    is_storyline: bool = True
    icon: str | None = None
    prior: int | None = None
    stages: dict[int, Stage] = {}
    on_init_actions: list[Action] = []
    on_complete_actions: list[Action] = []
    on_fail_actions: list[Action] = []
    transfer_conditions: dict[int, dict[str, list[Condition]]] = {}
    fail_on_giver_death: bool = True
    extra_condlists: list[QuestCondlist] = []
    reward_money: int | None = None
    reward_item_alias: str | None = None
    reward_item_count: int = 1
    complete_info: str | None = None
    taken_info: str | None = None
    cleanup_infos: list[str] = []
    return_to_giver_stage: int | None = None
    return_distance: float = 40.0
    available_info: str | None = None
    done_info: str | None = None
    requires_faction: str | None = None
    requires_warfare: bool = False
```

### Идентификаторы и связи

| Поле | Режим | Тип | По умолчанию | Назначение |
|---|---|---|---|---|
| `id` | `[Общее]` | `RequiredId` | обязательное | ID секции LTX `[id]`, ключ `task_functor` и префикс всех функций. |
| `giver_npc_id` | `[Общее]` | `OptionalId` | `None` | Устаревшее имя ID квестодателя. Эффективный квестодатель вычисляется как `giver_npc_id or npc_id`; он используется в `give_task`, `task_giver_alive`, `condlist_0` и `target_functor`. |
| `npc_id` | `[Общее]` | `OptionalId` | `None` | Игровой ID NPC-квестодателя. Попадает в `give_task` и `task_giver_alive`; используется, если `giver_npc_id` не задан. Для привязки диалога приоритет у `Dialog.npc_id`. |
| `npc_location` | `[Общее]` | `str \| None` | `None` | Локация квестодателя для патча `character_desc_<level>.xml`. |
| `dialog_id` | `[Общее]` | `OptionalId` | `None` | ID основного диалога выдачи квеста. |
| `dialog_ids` | `[Общее]` | `list[str]` | `[]` | Все связанные диалоги (выдача, сдача, ветки). |

> **`giver_npc_id` vs `npc_id`.** Это не два независимых квестодателя.
> Эффективный квестодатель — `giver_npc_id or npc_id`; `giver_npc_id`
> перекрывает `npc_id`, если задан. `condlist_0 = {!task_giver_alive(...)} fail`
> создаётся, если **эффективный** giver задан и `fail_on_giver_death=True`
> (а не только при заполненном `giver_npc_id`). Для привязки диалога
> `Dialog.npc_id` имеет приоритет над `Quest.npc_id`/`Quest.giver_npc_id`.

### Тексты и PDA

| Поле | Режим | Тип | По умолчанию | Назначение |
|---|---|---|---|---|
| `title_ru` / `title_en` | `[Общее]` | `str` | `""` | Название квеста в PDA. |
| `descr_ru` / `descr_en` | `[Общее]` | `str` | `""` | Описание квеста в PDA. |
| `msg_reward_ru` / `msg_reward_en` | `[Общее]` | `str \| None` | `None` | Тексты PDA-подсказки при завершении. `None` → автогенерация «Задание выполнено: <title>.» / «Task completed: <title>.». |
| `msg_fail_ru` / `msg_fail_en` | `[Общее]` | `str \| None` | `None` | Тексты PDA-подсказки при провале/отмене. `None` → автогенерация «Задание провалено: <title>.» / «Task failed: <title>.». |
| `is_storyline` | `[Story]` | `bool` | `True` | Попадает в LTX как `storyline = true/false`. Сюжетные цепочки используют `True`. |
| `icon` | `[Общее]` | `str \| None` | `None` | Иконка PDA. По умолчанию `ui_inGame2_Put_v_pripyat`. |
| `prior` | `[Общее]` | `int \| None` (`ge=0`) | `None` | Приоритет в PDA. По умолчанию `60`. |

### Этапы и логика

| Поле | Режим | Тип | По умолчанию | Назначение |
|---|---|---|---|---|
| `stages` | `[Общее]` | `dict[int, Stage]` | `{}` | Карта этапов. Ключи обязаны идти подряд с `0` и совпадать с `Stage.id`. |
| `on_init_actions` | `[Общее]` | `list[Action]` | `[]` | Действия эффекта `on_init` (`<quest_id>_start`). Для Story здесь размещается `SpawnSquad(mode="story")`. |
| `on_complete_actions` | `[Общее]` | `list[Action]` | `[]` | Действия эффекта `on_complete` (`<quest_id>_reward`). Для цепочки — `GiveTask(next)`. |
| `on_fail_actions` | `[Общее]` | `list[Action]` | `[]` | Действия `on_fail`/`on_cancel` (`<quest_id>_cleanup`). Для Story — `RemoveSquad(...)`. |
| `transfer_conditions` | `[Общее]` | `dict[int, dict[str, list[Condition]]]` | `{}` | Правила перехода этапов: `{stage: {"complete": [...], "fail": [...]}}`. Для многоэтапного Story. |
| `fail_on_giver_death` | `[Общее]` / `[Story]` | `bool` | `True` | Добавлять ли `condlist_0 = {!task_giver_alive(<quest>)} fail`. `False` отключает авто-провал. |
| `extra_condlists` | `[Story]` | `list[QuestCondlist]` | `[]` | Дополнительные `condlist_N`, завершающие/проваливающие весь квест. Нумерация продолжает авто-провал. |

### `QuestCondlist` и сериализация условий `[Story]`

```python
class QuestCondlist(BaseModel):
    when: list[Condition]                      # min_length=1
    result: Literal["complete", "fail"]
```

> **Только объекты `QuestCondlist`.** `Quest.extra_condlists` принимает
> исключительно `QuestCondlist`. Сырой `dict` вида
> `{"complete": [SmartOwner(...)]}` даёт `pydantic.ValidationError` ещё до
> сборки. Внутри `when` допустимы только `HasInfo`, `DontHasInfo` и
> `HasItem`; `SmartOwner` и `HasMoney` в `[Story]`-condlist **не
> поддерживаются** и дают `BuildError` (см. таблицу ниже).
>
> ```python
> from src.core.models import HasInfo, QuestCondlist
>
> extra_condlists=[
>     QuestCondlist(when=[HasInfo(info="mymod_merc_dead")], result="complete"),
> ]
> ```

Нумерация:

* `condlist_0` — авто-провал `{!task_giver_alive(<quest_id>)} fail`, если
  `fail_on_giver_death=True`;
* далее `extra_condlists` в порядке объявления (`condlist_1`, `condlist_2`, …);
* при `fail_on_giver_death=False` первый extra становится `condlist_0`;
* при `fail_on_giver_death=False` и пустых extras блок `condlist_*` не
  эмитится вовсе.

Поддерживаемые условия в `condlist`:

| Модель | Синтаксис LTX |
|---|---|
| `HasInfo` | `+info` |
| `DontHasInfo` | `-info` |
| `HasItem(count=1)` | `=actor_has_item(section)` |
| `HasItem(count>1)` | `=actor_has_item_amount(section:count)` |
| `HasMoney` | **не поддерживается** в Фазе 2 → `BuildError` |
| `SmartOwner` | **не поддерживается** в Фазе 2 → `BuildError` |

`condlist_N` завершает **весь квест**, а не отдельный этап, и
`task_objects` проверяет его раньше `status_functor`. Для многоэтапных
квестов используйте `transfer_conditions`; `extra_condlists` — для
одноэтапных звеньев цепочки, как в ванильном `tm_lostzone_ms.ltx`.

Логика `_status` (упрощённо):

```text
каждый тик (с троттлингом):
  выполнить on_start_actions текущего этапа ровно один раз
  повторно выдать GiveItem из on_start_actions, если предмета меньше count
  заспавнить/заморозить отряды warfare_capture, если задано
  если transfer_conditions[stage]["fail"] истинно -> "fail"
  если warfare_capture этап зачищён -> следующий этап или "complete"
  если transfer_conditions[stage]["complete"] истинно -> следующий этап или "complete"
  если stage == return_to_giver_stage и игрок рядом с квестодателем -> "complete"
```

### Награды и информационные поршни

| Поле | Режим | Тип | По умолчанию | Назначение |
|---|---|---|---|---|
| `reward_money` | `[Общее]` | `int \| None` (`ge=0`) | `None` | Деньги, автоматически выдаваемые в `_reward`. |
| `reward_item_alias` | `[Общее]` | `str \| None` | `None` | Секция предмета, автоматически выдаваемого в `_reward`. |
| `reward_item_count` | `[Общее]` | `int` (`ge=1`) | `1` | Количество предметов награды. |
| `complete_info` | `[Общее]` / `[Story]` | `str \| None` | `None` | Поршень, выдаваемый в `_reward`. В Story-цепочке служит предусловием следующего диалога. |
| `taken_info` | `[Общее]` / `[Story]` | `str \| None` | `None` | Поршень, выдаваемый в `_start`. Снимается только в `_cleanup` (провал/отмена); при успешном завершении сохраняется. |
| `cleanup_infos` | `[Общее]` / `[Story]` | `list[str]` | `[]` | Поршни, снимаемые в конце `_reward` и в `_cleanup`. Предназначены для взаимоисключающих вариантов (`assault`/`solo`) и временных маркеров; `taken_info`/`complete_info` в список включать не нужно. Дополнительно генератор **автоматически** добавляет сюда все `GiveInfo` из `Stage.on_start_actions` (кроме `complete_info`/`done_info`), поэтому поршни готовности вида `*_ready` снимаются при провале/отмене квеста и не открывают диалог сдачи при повторном взятии. В Story сюда обязательно включается поршень смерти отряда. |
| `return_to_giver_stage` | `[Общее]` | `int \| None` | `None` | Этап, на котором игрок должен вернуться к квестодателю. |
| `return_distance` | `[Общее]` | `float` (`ge=0`) | `40.0` | Радиус «подошёл к квестодателю» в метрах. |
| `available_info` | `[Общее]` | `str \| None` | `None` | Маркер доступности для внешних скриптов/UI. Ядро только сохраняет значение в `QUESTS` и **не проверяет** его в сгенерированном коде. Для встроенного гейта используйте `requires_faction`/`requires_warfare` (см. ниже). |
| `done_info` | `[Общее]` | `str \| None` | `None` | Зарезервировано для внешних скриптов/UI; ядро только сохраняет значение в таблице `QUESTS`. |
| `requires_faction` | `[Общее]` | `str \| None` | `None` | Техническое имя фракции игрока (например, `"army"`). Встроенный гейт: `<dialog_id>_can_take` вызывает `is_actor_faction(...)` и закрывает диалог для чужой фракции. |
| `requires_warfare` | `[Warfare]` | `bool` | `False` | Встроенный гейт Warfare: `<dialog_id>_can_take` требует `is_warfare()`; `<quest_id>_start`/`<quest_id>_status` не выполняются вне Warfare (`if (quest.world or quest.requires_warfare) and not is_warfare() then return nil end`). Для Story оставляйте `False`. |

### Гейты доступа: `requires_faction` и `requires_warfare`

В отличие от `available_info`/`done_info`, которые остаются **маркерами для
внешних скриптов** и не проверяются сгенерированным кодом, поля
`requires_faction` и `requires_warfare` — это первоклассные встроенные гейты:

```python
class Quest(BaseModel):
    ...
    requires_faction: str | None = None   # например, "army"
    requires_warfare: bool = False
```

Генератор добавляет в `<dialog_id>_can_take` связанного диалога:

```lua
if requires_warfare and not is_warfare() then return false end
if requires_faction ~= "" and not is_actor_faction(requires_faction) then
	return false
end
```

`is_actor_faction(faction)` повторяет эталонный `is_actor_army()`:

```lua
local function is_actor_faction(faction)
	if not faction or faction == "" then return false end
	if warfare and warfare.actor_faction == faction then
		return true
	end
	local ok, comm = pcall(function() return get_actor_true_community() end)
	return (ok and comm == faction) or false
end
```

Проверка сначала смотрит на `warfare.actor_faction` (режим Warfare), затем —
на `get_actor_true_community()` (работает и вне Warfare). Если нужен доступ
только в Warfare, задайте `requires_warfare=True` **и** `requires_faction`;
если нужен доступ любой фракции — только `requires_warfare`.

`requires_warfare` также блокирует `_start`/`_status` наравне с `world`:
квест не будет «висеть» вне Warfare, а его эффекты не выполнятся без
включённого режима.

> **Жёсткое правило: `requires_warfare=True` — это гейт, а не подсказка.**
> Вне Warfare:
>
> - `<dialog_id>_can_take` возвращает `false` — стартовой фразы не будет;
> - `<quest_id>_start` не выполняется — `on_init_actions`/`taken_info` не сработают;
> - `<quest_id>_status` не тикает — `on_start_actions`, `transfer_conditions`
>   и `target_squad_id` не продвигают квест;
> - `WarfareCapture` дополнительно включает `world = true`.
>
> Если сценарий тестируется в Story/freeplay, **не задавайте**
> `requires_warfare` и не используйте `WarfareCapture`. Смешение
> `WarfareCapture` и `SpawnSquad(mode="story")` в одном квесте — `BuildError`;
> разделяйте сценарий на два квеста.

> **Запрет: `CompleteTask` + ручная выдача награды при пустых `reward_*`.**
> Если `reward_money`/`reward_item_alias` **пусты**, награда в `actions`
> реплики, где есть `CompleteTask`, **не поддерживается** и считается
> ошибкой (`GRAPH-REWARD-001`/`XRAY-REWARD-002`): движок исполняет только
> один `<action>` на реплику, а `CompleteTask` завершает задачу раньше
> остальных эффектов. В результате игрок не получает ни денег, ни предмета.
>
> ```python
> # ПЛОХО: награда потеряется, reward_* пусты
> Phrase(
>     id=2,
>     actions=[
>         CompleteTask(task_id=QUEST_ID),
>         GiveMoney(amount=50000),
>         GiveItem(item_alias="wpn_ak74"),
>     ],
> )
>
> # ХОРОШО: награда в Quest.reward_* (эффект _reward)
> Quest(
>     ...,
>     reward_money=50000,
>     reward_item_alias="wpn_ak74",
>     reward_item_count=1,
> )
>
> # ХОРОШО: награда в Quest.on_complete_actions
> Quest(..., on_complete_actions=[GiveItem(item_alias="wpn_ak74")])
> ```
>
> Надёжные пути: `Quest.reward_money`/`Quest.reward_item_alias`
> (эффект `_reward`), `Quest.on_complete_actions` (Lua после завершения
> задачи) или `Quest.complete_info` для поршня завершения. Компилятор
> выводит warning, а предполётная валидация трактует это как `ERROR`
> (см. §3.6).

> **Автоматическая сдача vs диалоговая сдача.** Если задан
> `return_to_giver_stage`, квест завершится автоматически при приближении к
> квестодателю. Если сдача должна идти через диалог (проверка предмета,
> ветвление, выбор награды), `return_to_giver_stage` не задавайте.

### Валидаторы `Quest`

1. `id` не может быть пустым.
2. `npc_location` обрезается; пустая строка превращается в `None`.
3. `stages` не может быть пустым.
4. Ключи `stages` обязаны идти подряд с `0`.
5. Ключ `stages` обязан совпадать с `Stage.id`.
6. `return_to_giver_stage`, если задан, обязан существовать в `stages`.

## 2.9. `ModProject` — корневой контейнер `[Общее]`

```python
class ModProject(BaseModel):
    model_config = _MODEL_CONFIG

    name: str
    required_mods: list[str] = []
    quests: dict[str, Quest] = {}
    dialogs: dict[str, Dialog] = {}
    squads: dict[str, CustomSquad] = {}
```

| Поле | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `name` | `str` | обязательное | Человекочитаемое имя проекта. Из него вычисляется slug. |
| `required_mods` | `list[str]` | `[]` | Декларативный список зависимостей. Ядро его не проверяет. |
| `quests` | `dict[str, Quest]` | `{}` | Карта квестов. Ключ обязан совпадать с `Quest.id`. |
| `dialogs` | `dict[str, Dialog]` | `{}` | Карта диалогов. Ключ может отличаться от `Dialog.id`; канонический ID всегда берётся из модели. |
| `squads` | `dict[str, CustomSquad]` | `{}` | Карта кастомных секций отрядов. Ключ обязан совпадать с `CustomSquad.id`. При непустой карте сборщик пишет `squad_descr_<slug>.ltx`. |

Валидатор `ModProject._validate_cross_references` проверяет:

- ключ `quests` совпадает с `Quest.id`;
- каждый `Quest.dialog_id` и каждый элемент `Quest.dialog_ids` существует в
  `dialogs`;
- каждый `Dialog.task_id` существует в `quests`;
- ключ `squads` совпадает с `CustomSquad.id`.

Методы сериализации:

```python
json_text = project.to_json()
restored = ModProject.from_json(json_text)

yaml_text = project.to_yaml()
restored = ModProject.from_yaml(yaml_text)
```

Все методы сохраняют `model_extra`, поэтому неизвестные колонки SQLite не
теряются.

## 2.10. Метаданные Сталкера: `npc_id`, `npc_location`, `dialog_id`

Это **ключевой раздел** для привязки диалогов к NPC. Ядро хранит метаданные в
двух слоях:

1. **Объявленные поля моделей** — основной и рекомендуемый способ:
   `Quest.npc_id`, `Quest.npc_location`, `Quest.dialog_id`,
   `Dialog.npc_id`, `Dialog.npc_location`, `Dialog.dialog_id`,
   `Dialog.task_id`.
2. **Устаревшие extra-поля SQLite** — сохраняются благодаря `extra="allow"`:
   `owner_profile_id`, `owner_character_desc`, `giver_character_desc`.

Сборщик `ModBuilder._collect_dialog_bindings` использует их в таком порядке:

```text
npc_id:
  Dialog.npc_id
  -> Dialog.owner_profile_id          (legacy extra)
  -> Quest.npc_id
  -> Quest.giver_npc_id
  -> Quest.owner_profile_id           (legacy extra)

npc_location:
  Dialog.npc_location
  -> Dialog.owner_character_desc      (legacy extra)
  -> Dialog.giver_character_desc      (legacy extra)
  -> Quest.npc_location
  -> Quest.owner_character_desc       (legacy extra)
  -> Quest.giver_character_desc       (legacy extra)
```

Значение локации нормализуется:

```text
"escape"                       -> "escape"
"character_desc_escape"        -> "escape"
"character_desc_escape.xml"    -> "escape"
```

Итоговый файл всегда называется:

```text
gamedata/configs/gameplay/character_desc_<npc_location>.xml
```

Пример корректных метаданных для Душмана в Мёртвом Городе:

```python
npc_id = "cit_killers_merc_trader_stalker"
npc_location = "deadcity"
dialog_id = "deadcity_dushman_take"
```

Правила и ошибки:

| Ситуация | Поведение сборщика |
|---|---|
| Есть `npc_id` и `npc_location` | Диалог привязывается: в профиль NPC вставляется `<actor_dialog>dialog_id</actor_dialog>`. |
| Есть `npc_id`, но нет `npc_location` | `BuildError`: невозможно выбрать `character_desc_<level>.xml`. Сборка возвращает `False`. |
| Нет `npc_id` (ни в диалоге, ни в квесте) | Warning в лог. Диалог генерируется в `dialogs_<mod>.xml`, но **не привязывается** к профилю. |
| Ванильный профиль не найден | `BuildError`. |
| `<specific_character id="...">` не найден | `BuildError`. |
| `<specific_character id="...">` найден более одного раза | `BuildError`. |

> **Жёсткое правило:** не угадывайте профиль NPC. Если диалог должен быть
> доступен у конкретного NPC, всегда задавайте и `npc_id`, и `npc_location`.
> `dialog_id` — это ровно то значение, которое попадёт в `<actor_dialog>`.

### Уникальные торговцы и `meet`-диалоги (`XRAY-MEET-001`)

`Dialog.npc_id` + `npc_location` лишь **добавляют** `<actor_dialog>` в профиль.
Они не заменяют существующий `meet`-диалог и не гарантируют, что уникальный
торговец покажет новую ветку. Для уникальных NPC с `meet`-схемой стартовая
фраза может не появиться, хотя сборка успешна.

Типичные примеры: `zat_a2_stalker_barmen`, `cit_killers_merc_trader_stalker`,
`esc_2_12_stalker_nimble`, `esc_2_12_stalker_trader`. Профиль `esc_m_trader`
в Anomaly 1.5.3 отсутствует (Сидорович — `esc_2_12_stalker_trader`).

`XrayLinter` сообщает `XRAY-MEET-001` (WARNING с ручной проверкой). Что делать:

1. Тестировать на **чистом сохранении/новом профиле** — старый
   `taken_info` может блокировать диалог через `DontHasInfo`.
2. Если ветка не появляется — патчить `meet`-диалог или добавлять реплику в
   существующий `meet`, а не только `<actor_dialog>`.
3. Для детерминированного теста использовать неуникального NPC.

## 2.11. `CustomSquad` — кастомные секции отрядов `[Общее]`

```python
class CustomSquad(BaseModel):
    model_config = _MODEL_CONFIG

    id: RequiredId
    faction: str
    npc: list[str] = []
    npc_random: list[str] = []
    npc_in_squad: list[int] = []
    target_smart: str | None = None
    relationship: Literal["neutral", "friend", "enemy"] | None = None
    idle_time: float | None = None
    spawn_point: str | None = None
    story_id: str | None = None
    death_infos: list[str] = []
```

| Поле | Режим | Тип | По умолчанию | Назначение |
|---|---|---|---|---|
| `id` | `[Общее]` | `RequiredId` | обязательное | Имя LTX-секции, например `mymod_atp_bandit_leader_squad`. Ключ в `ModProject.squads` обязан совпадать. |
| `faction` | `[Общее]` | `str` | обязательное | Фракция отряда, например `bandit` или `army`. |
| `npc` | `[Общее]` | `list[str]` | `[]` | Явный список секций NPC, например `["sim_default_bandit_4"]`. |
| `npc_random` | `[Общее]` | `list[str]` | `[]` | Пул секций, из которого движок выбирает NPC случайно. |
| `npc_in_squad` | `[Общее]` | `list[int]` | `[]` | Размер отряда: `[n]` или `[min, max]`, где `0 <= min <= max`. Значение `max` не должно превышать число шаблонов `npc`/`npc_random`. |
| `target_smart` | `[Общее]` | `str \| None` | `None` | **Точка назначения** отряда после спавна, а не точка спавна. Должна отличаться от `SpawnSquad.smart_alias`, если нужен марш. |
| `relationship` | `[Общее]` | `"neutral" \| "friend" \| "enemy" \| None` | `None` | Отношение отряда к актору. |
| `idle_time` | `[Общее]` | `float \| None` | `None` | Время ожидания отряда на точке, `>= 0`. |
| `spawn_point` | `[Общее]` | `str \| None` | `None` | Именованная точка спавна отряда. |
| `story_id` | `[Общее]` | `str \| None` | `None` | **Обязателен** для отряда, который адресуется `RemoveSquad`, `SpawnNpcItem` или `Stage.target_squad_id`. Без него нет устойчивой связи «отряд → командир → предмет → смерть → completion». |
| `death_infos` | `[Story]` | `list[str]` | `[]` | Инфопоршни, выдаваемые в `on_death` отряда. Сериализуются как `on_death = %+info_a +info_b%`. |

Обязательное условие валидности: непустой `faction` **и** хотя бы один из
`npc` / `npc_random`. Иначе `BuildError` (секция пропускается).

> **`story_id` фактически обязателен.** В модели поле необязательное, но для
> квестового отряда оно обязательно, если отряд адресуется:
>
> - `RemoveSquad(squad_alias=...)` — резолв через `get_story_squad(alias)`;
> - `SpawnNpcItem(target_alias=...)` — резолв командира через story-отряд;
> - `Stage.target_squad_id` / `target_seen` — используют story-ID.
>
> Без `story_id` валидатор возвращает `CAT-SQUAD-002`/`XRAY-SPAWNITEM-002`.
> `target_smart` — это точка **назначения**, а не спавна: если нужен марш,
> она должна отличаться от `SpawnSquad.smart_alias`.

> **`npc_in_squad`.** Формат `[n]` или `[min, max]`; `max` не должен
> превышать число шаблонов в `npc` + `npc_random`. Иначе
> `CAT-SQUAD-005`/`XRAY-SQUAD-001` (WARNING): движок может переспавнить или
> подменить NPC. Для детерминированного отряда задавайте явные шаблоны.

Пример проекта `[Story]`:

```python
from src.core.models import CustomSquad, ModProject

project = ModProject(
    name="My Mod",
    mod_slug="mymod",
    squads={
        "mymod_relay_merc_squad": CustomSquad(
            id="mymod_relay_merc_squad",
            faction="monolith",
            npc=["sim_default_monolith_3", "sim_default_monolith_4"],
            npc_in_squad=[2, 2],
            target_smart="zat_stalker_base_smart",
            story_id="mymod_relay_merc_squad",
            death_infos=["mymod_relay_merc_dead"],
        )
    },
)
```

Если `project.squads` не пуст, `ModBuilder.build_project` создаёт каталог
`gamedata/configs/misc/squad_descr` и записывает файл
`gamedata/configs/misc/squad_descr/squad_descr_<slug>.ltx` в cp1251 **без
BOM**. Порядок строк фиксирован:

```ltx
[mymod_relay_merc_squad]:online_offline_group
faction = monolith
relationship = enemy
npc = sim_default_monolith_3, sim_default_monolith_4
npc_random = ...
npc_in_squad = 3, 5
target_smart = zat_stalker_base_smart
idle_time = 30
spawn_point = ...
story_id = ...
on_death = %+mymod_relay_merc_dead%
```

Необязательные строки (`relationship`, `npc_random`, `npc_in_squad`,
`target_smart`, `idle_time`, `spawn_point`, `story_id`, `on_death`)
эмитируются только при непустом значении. При пустом `project.squads` файл
**не создаётся**.

> **`on_death` — единственный «мостик» Story → сюжет.** Движок выдаёт
> инфопоршень при полном уничтожении отряда, а квест ловит его через
> `extra_condlists` с условием `HasInfo("mymod_relay_merc_dead")`. Это
> устраняет необходимость в `sim_squad_warfare` и любых Lua-опросах
> симуляции.

> **`system.ltx` патчить не нужно.** Ванильный
> `gamedata/configs/misc/squad_descr/squad_descr.ltx` подключает все файлы
> `squad_descr_*.ltx` через глоб, поэтому новый файл загружается движком
> автоматически. Секция `:online_offline_group` позволяет объявить уникальный
> квестовый отряд, который симуляция Warfare не создаёт сама (в отличие от
> «common»-секций).

## 2.12. Story-паттерн: отряд → `condlist_N` → следующая задача `[Story]`

### 2.12.1. Стандарт имён `<mod_slug>_<chapter>_<quest>_<role>`

Все генерируемые сущности Story-проекта следуют одному шаблону:

```text
<mod_slug>_<chapter>_<quest>_<role>
```

| Часть | Смысл | Пример |
|---|---|---|
| `mod_slug` | Слаг мода: явное extra-поле `mod_slug` (если задано) или слаг, выведенный из `ModProject.name`. | `mymod` |
| `chapter` | Номер главы или ветки сюжета (`01`, `02`, `side_a`). | `relay_01` |
| `quest` | Короткое имя задачи. | `silence`, `report` |
| `role` | Роль сущности. | `take`, `done`, `dead`, `squad`, `reported` |

Единые роли:

| Роль | Назначение | Пример |
|---|---|---|
| `take` | Диалог выдачи задачи. | `mymod_relay_take` |
| `report` | Диалог сдачи/доклада. | `mymod_relay_report` |
| `squad` | Секция `CustomSquad` Story-отряда. | `mymod_relay_merc_squad` |
| `dead` | Поршень смерти отряда (`CustomSquad.death_infos`). | `mymod_relay_merc_dead` |
| `taken` | Поршень «задача взята». | `mymod_relay_01_taken` |
| `done` | Поршень «задача завершена» (`complete_info`). | `mymod_relay_01_done` |
| `reported` | Поршень события диалога сдачи. | `mymod_relay_reported` |

Первые две части часто сливаются: `mymod_relay_01_silence` — это
`<mod_slug>_<chapter>` в `chapter=relay_01`, а `quest=silence` уже входит
в состав ID задачи. Главное — **не переиспользовать один и тот же ID** для
поршня, диалога и задачи.

### 2.12.2. Компактный шаблон цепочки

Канонический Story-паттерн состоит из трёх звеньев. Копируйте его как
скелет новой сюжетной ветки. `mod_slug` — необязательное extra-поле
`ModProject`: если его не задать, слаг выводится из `name`.

```python
from src.core.models import (
    CustomSquad, GiveInfo, GiveTask, HasInfo, ModProject, Quest,
    QuestCondlist, RemoveSquad, SpawnSquad, Stage,
)

MOD = "mymod"
Q1 = f"{MOD}_relay_01_silence"
Q2 = f"{MOD}_relay_02_report"
SQUAD = f"{MOD}_relay_merc_squad"
INFO_DEAD = f"{MOD}_relay_merc_dead"
INFO_TAKEN = f"{MOD}_relay_01_taken"

project = ModProject(
    name="My Mod",
    mod_slug=MOD,
    squads={
        SQUAD: CustomSquad(
            id=SQUAD,
            faction="killer",
            npc=["sim_default_killer_1", "sim_default_killer_3"],
            target_smart="zat_b52",          # точка назначения отряда
            story_id=SQUAD,
            death_infos=[INFO_DEAD],         # on_death = %+...%
            relationship="enemy",
        ),
    },
    quests={
        Q1: Quest(
            id=Q1,
            npc_id="zat_a2_stalker_barmen",
            npc_location="zaton",
            is_storyline=True,
            title_ru="...",
            stages={0: Stage(id=0, target_squad_id=SQUAD, title_ru="...")},
            on_init_actions=[                # звено 1: спавн
                SpawnSquad(
                    squad_alias=SQUAD,
                    smart_alias="zat_stalker_base_smart",
                    mode="story",
                ),
            ],
            extra_condlists=[                # звено 2: condlist_N
                QuestCondlist(when=[HasInfo(info=INFO_DEAD)], result="complete"),
            ],
            cleanup_infos=[INFO_DEAD],
            on_complete_actions=[            # звено 3: GiveTask
                GiveTask(task_id=Q2),
            ],
            on_fail_actions=[RemoveSquad(squad_alias=SQUAD)],
            taken_info=INFO_TAKEN,
        ),
        Q2: Quest(id=Q2, npc_id="zat_a2_stalker_barmen",
                  npc_location="zaton", is_storyline=True,
                  stages={0: Stage(id=0, title_ru="...")}),
    },
)
```

Что и зачем:

1. **Спавн.** `SpawnSquad(mode="story")` вызывает `create_squad` без
   `set_target` / `stay_time` / `force_online`. Маршрут задаёт
   `CustomSquad.target_smart`, поэтому Lua не трогает `sim_squad_warfare`.
2. **Смерть.** `CustomSquad.death_infos` сериализуется в
   `on_death = %+<info>%`. Движок выдаёт поршень сам, когда отряд уничтожен.
3. **Завершение.** `QuestCondlist(when=[HasInfo(...)], result="complete")`
   генерирует `condlist_N` в `tm_<mod>.ltx`. Квест закрывается без
   `CompleteTask` из диалога и без `transfer_conditions` на Lua.
4. **Мост к следующей задаче.** `on_complete_actions=[GiveTask(task_id=Q2)]`
   сразу выдаёт Q2, не требуя возврата к NPC.
5. **Очистка.** `cleanup_infos=[INFO_DEAD]` снимает поршень при повторном
   взятии, `on_fail_actions=[RemoveSquad(...)]` не оставляет Story-отряд в
   мире после провала или отмены.

Сериализованный фрагмент `tm_<mod>.ltx` для такой цепочки выглядит так:

```ltx
[<quest_id>]
...
on_init               = %=<quest_id>_start()%
on_complete           = %=<quest_id>_reward()%
on_fail               = %=<quest_id>_cleanup()%
on_cancel             = %=<quest_id>_cleanup()%

condlist_0            = {!task_giver_alive(<quest_id>)} fail
condlist_1            = {+<info_dead>} complete
```

`condlist_1` — это ваш `extra_condlists[0]`; нумерация продолжается после
автоматического `condlist_0` (смерть квестодателя). `GiveTask` из
`on_complete_actions` выполняется внутри `<quest_id>_reward()` в Lua, а не
в LTX-строке `on_complete`. Если `fail_on_giver_death=False` или
**эффективный** квестодатель (`giver_npc_id or npc_id`) не задан, `condlist_0`
не создаётся и ваш condlist получает индекс `0`.

> **Не смешивайте режимы.** `WarfareCapture` и `SpawnSquad(mode="story")`
> в одном квесте недопустимы: `WarfareCapture` требует живой симуляции
> Warfare и пишет `sim_squad_warfare`-вызовы, а `SpawnSquad(mode="story")`
> обязан работать в чистом Story без симуляции. Валидатор возвращает
> `BuildError`. Если сценарию нужны и захват точки, и сюжетный отряд,
> разделите его на два квеста: Warfare-квест с `requires_warfare=True`
> и Story-квест с `SpawnSquad(mode="story")`.

## 2.13. Модульная сборка и слияние глав (`ModProject.merge` и `MergeValidator`)

Большой мод удобно писать главами: каждая глава — независимый
`ModProject` со своими `quests`, `dialogs` и `squads`. Перед сборкой главы
объединяются в один проект методом `ModProject.merge`:

```python
class ModProject(BaseModel):
    ...
    @classmethod
    def merge(
        cls,
        *projects: "ModProject",
        mod_slug: str | None = None,
        mod_title: str | None = None,
    ) -> "ModProject": ...
```

`merge` не перезаписывает данные: при коллизии ключа или `story_id` между
главами он поднимает `ValueError`. Если `mod_slug`/`mod_title` не заданы,
они берутся из первой главы (`mod_slug`/`mod_title`, иначе `name`).

```python
from src.core.models import ModProject
from src.validation import MergeValidator, ValidationReport

# Каждая глава — самостоятельный ModProject со своим mod_slug.
ch1 = ModProject(name="My Mod — Chapter 1", mod_slug="mymod", quests={...}, dialogs={...})
ch2 = ModProject(name="My Mod — Chapter 2", mod_slug="mymod", quests={...}, dialogs={...})
side_quests = ModProject(name="My Mod — Side Quests", mod_slug="mymod", quests={...})

merged = ModProject.merge(
    ch1,
    ch2,
    side_quests,
    mod_slug="mymod",
    mod_title="My Mod",
)

# Диагностика слияния: коллизии, общие поршни, пространство имён.
report = ValidationReport()
MergeValidator(report).validate_chapters(
    [ch1, ch2, side_quests],
    target_slug="mymod",
)
if report.has_errors:
    report.raise_if_errors()

# Дальше — обычная предполётная валидация объединённого проекта (§3.6).
```

Правила изоляции глав:

| Код | Severity | Что проверяется | Как исправить |
|---|---|---|---|
| `MERGE-ID-001` | `ERROR` | Дубль ключа `quests`/`dialogs`/`squads` или `CustomSquad.story_id` между главами. `merge` в этом случае также бросает `ValueError`. | Переименуйте сущность/`story_id` в одной из глав. |
| `MERGE-INFO-001` | `WARNING` | Один инфопоршень выдают разные квесты из **разных** глав. | Разведите поршни по главам или убедитесь, что повторная выдача безопасна. |
| `MERGE-NS-001` | `WARNING` | ID квеста/диалога/отряда не начинается с единого префикса `<mod_slug>_`. | Приведите ID к виду `<mod_slug>_<chapter>_<quest>_<role>` (см. §2.12.1). |

> **Единый префикс.** Все главы обязаны использовать один `mod_slug` и
> один префикс `<mod_slug>_` для квестов, диалогов, отрядов и поршней.
> Иначе возможны коллизии при объединении и смешение пространств имён
> (`MERGE-NS-001`).

---

# 3. Правила и ограничения сталкерского рантайма (X-Ray & gamedata)

## 3.1. Прямое перекрытие файлов: никаких DLTX и рантайм-инъекций

Ядро **не использует**:

- DLTX (`.dltx`, DLTX-оверрайды);
- `.ext`-директивы;
- динамическую Lua-инъекцию диалогов (`start_dialogs`,
  `MYMOD_DIALOG_INJECTIONS`);
- рантайм-инъекцию отрядов/сквадов в диалоговые таблицы и подмену
  сквад-таблиц «на лету».

Отряды спавнятся только штатными игровыми действиями (`SpawnSquad`,
`WarfareCapture`) через `SIMBOARD`; диалоги привязываются только через
`character_desc_<level>.xml`. Никаких скрытых таблиц-инъекций в рантайме нет.

Вместо этого `ModBuilder` работает как **текстовый патчер**:

1. Копирует ванильный `configs/system.ltx` в выходной каталог.
2. Дописывает `dialogs_<slug>` в `[dialogs] files`.
3. Дописывает `character_desc_<level>` в
   `[profiles] specific_characters_files`.
4. Копирует ванильный `configs/gameplay/character_desc_<level>.xml`.
5. Вставляет `<actor_dialog>dialog_id</actor_dialog>` в нужный
   `<specific_character id="npc_id">`.
6. Записывает все файлы в Windows-1251.

Это детерминированный и проверяемый способ, не требующий DLTX и не зависящий от
порядка загрузки скриптов.

### Что именно патчится в `system.ltx`

```ltx
[dialogs]
files = dialogs, dialogs_escape, dialogs_<slug>

[profiles]
specific_characters_files = character_desc_general, character_desc_escape, character_desc_<level>
```

- Существующие значения сохраняются.
- Повторная сборка не создаёт дубликатов (идемпотентность).
- Поддерживаются многострочные значения с продолжением `\`.
- Отсутствие секции `[dialogs]`/`[profiles]` или ключа `files`/
  `specific_characters_files` — `BuildError`.
- BOM и стиль переносов строк исходного файла сохраняются.

### Что именно патчится в `character_desc_<level>.xml`

Исходный фрагмент:

```xml
<specific_character id="cit_killers_merc_trader_stalker" team_default="1">
    <name>Душман</name>
    <actor_dialog>dm_init</actor_dialog>
</specific_character>
```

После патча:

```xml
<specific_character id="cit_killers_merc_trader_stalker" team_default="1">
    <name>Душман</name>
    <actor_dialog>dm_init</actor_dialog>
    <actor_dialog>deadcity_dushman_take</actor_dialog>
    <actor_dialog>deadcity_dushman_turnin</actor_dialog>
</specific_character>
```

- Комментарии, `#include`, отступы и чужие профили сохраняются: DOM-пересериализация
  не используется.
- Вставка идемпотентна: повторный диалог не дублируется.
- Порядок диалогов определяется ролью (`take` → `take_assault` → `take_solo` →
  `turnin`/`turn_in` → `branch`).
- Если профиль не найден или найден дважды — `BuildError`.

## 3.2. Структура выходного каталога

```text
output/<slug>/
└── gamedata/
    ├── configs/
    │   ├── gameplay/
    │   │   ├── dialogs_<slug>.xml
    │   │   └── character_desc_<level>.xml   # копия ванильного + патч
    │   ├── misc/
    │   │   └── task/
    │   │       └── tm_<slug>.ltx
    │   ├── text/
    │   │   ├── rus/
    │   │   │   └── st_<slug>.xml
    │   │   └── eng/
    │   │       └── st_<slug>.xml
    │   └── system.ltx                        # копия ванильного + патч
    └── scripts/
        └── <slug>_quests.script
```

`<slug>` вычисляется из `ModProject.name`:

- нижний регистр;
- кириллица транслитерируется;
- пробелы и дефисы становятся `_`;
- недопустимые символы удаляются;
- повторные `_` схлопываются;
- если не осталось допустимых символов — используется `mod`.

## 3.3. Стандарты генерации XML-графа диалогов

Файл: `gamedata/configs/gameplay/dialogs_<slug>.xml`.

Жёсткие правила:

1. Корневой тег — `<game_dialogs>`.
2. Каждый диалог — `<dialog id="...">`; ID берётся из модели
   (`dialog.dialog_id` или `dialog.id`), а не из ключа словаря.
3. У каждого `<dialog>` обязан быть `<phrase_list>`.
4. Каждая реплика — `<phrase id="N">`.
5. Переходы — **только парные теги** `<next>ID</next>`; каждый ID обязан
   существовать в этом же диалоге.
6. Текст реплики — `<text><dialog_id>_phrase_<id>_text</text>`.
7. Условия/действия, требующие Lua, ссылаются строго на глобальную таблицу
   `dialogs`:
   - `<precondition>dialogs.<flat_function_name></precondition>`
   - `<action>dialogs.<flat_function_name></action>`
8. `HasInfo`/`DontHasInfo`/`GiveInfo` используют штатные теги:
   `<has_info>`, `<dont_has_info>`, `<give_info>`.
9. `GiveTask`/`CompleteTask`, если они единственные Lua-действия реплики,
   ссылаются на **текущий диалог**: `dialogs.<dialog_id>_accept` и
   `dialogs.<dialog_id>_turn_in`.
10. Диалог `role="turnin"`/`"turn_in"` с заданным `task_id` и без ручных
    не-info условий получает
    `<precondition>dialogs.<dialog_id>_can_turn_in</precondition>`. Функция
    проверяет наличие задачи и стадию: при `return_to_giver_stage >= 0` —
    `tsk.stage >= Quest.return_to_giver_stage`, а если у диалога нет
    собственного `HasInfo` и `return_to_giver_stage` не задан —
    `tsk.stage >= Quest.last_stage`. Поэтому сдача работает после save/load
    даже без тика `_status`. Поршень `*_ready` из `on_start_actions` для
    этого не используется и автоматически снимается в `_cleanup` при
    провале/отмене (см. §2.8).
11. **Ровно один `<action>` на реплику.** Если действий несколько, все они
    (включая `GiveTask`/`CompleteTask`) исполняются единой функцией
    `dialogs.<dialog_id>_phrase_<n>_action` строго в порядке объявления.
    Второй тег `<action>` движок отбрасывает.
12. Никакого захардкоженного `hello_dialog`: ID всегда приходит из модели.
13. `Phrase(id=0)` всегда принадлежит Игроку; чётные ID — Игрок, нечётные —
    NPC. Не начинайте `<actor_dialog>` с реплики NPC.

Пример сгенерированного файла:

```xml
<?xml version="1.0" encoding="windows-1251"?>
<game_dialogs>

    <dialog id="deadcity_dushman_take">
        <dont_has_info>deadcity_dushman_pda_started</dont_has_info>
        <phrase_list>
            <phrase id="0">
                <!-- Игрок -->
                <text>deadcity_dushman_take_phrase_0_text</text>
                <next>1</next>
            </phrase>
            <phrase id="1">
                <!-- NPC -->
                <text>deadcity_dushman_take_phrase_1_text</text>
                <next>2</next>
                <next>4</next>
            </phrase>
            <phrase id="2">
                <!-- Игрок -->
                <text>deadcity_dushman_take_phrase_2_text</text>
                <next>3</next>
                <give_info>deadcity_dushman_pda_started</give_info>
                <action>dialogs.deadcity_dushman_take_accept</action>
            </phrase>
            <phrase id="3">
                <!-- NPC -->
                <text>deadcity_dushman_take_phrase_3_text</text>
            </phrase>
            <phrase id="4">
                <!-- Игрок -->
                <text>deadcity_dushman_take_phrase_4_text</text>
            </phrase>
        </phrase_list>
    </dialog>

    <dialog id="deadcity_dushman_turnin">
        <phrase_list>
            <phrase id="0">
                <!-- Игрок -->
                <text>deadcity_dushman_turnin_phrase_0_text</text>
                <next>1</next>
            </phrase>
            <phrase id="1">
                <!-- NPC -->
                <text>deadcity_dushman_turnin_phrase_1_text</text>
                <next>2</next>
                <next>4</next>
            </phrase>
            <phrase id="2">
                <!-- Игрок -->
                <text>deadcity_dushman_turnin_phrase_2_text</text>
                <next>3</next>
                <precondition>dialogs.deadcity_dushman_turnin_phrase_2_precondition</precondition>
                <give_info>deadcity_dushman_pda_done</give_info>
                <!-- Один <action>: RemoveItem + GiveMoney + GiveItem + CompleteTask
                     исполняются внутри единой Lua-функции. -->
                <action>dialogs.deadcity_dushman_turnin_phrase_2_action</action>
            </phrase>
            <phrase id="3">
                <!-- NPC -->
                <text>deadcity_dushman_turnin_phrase_3_text</text>
            </phrase>
            <phrase id="4">
                <!-- Игрок -->
                <text>deadcity_dushman_turnin_phrase_4_text</text>
            </phrase>
        </phrase_list>
    </dialog>

</game_dialogs>
```

### Анатомия тегов

| Тег | Обязателен | Смысл |
|---|---|---|
| `<game_dialogs>` | да | Корень файла диалогов. |
| `<dialog id="...">` | да | Один диалог. ID — значение `<actor_dialog>`. |
| `<phrase_list>` | да | Контейнер всех реплик диалога. |
| `<phrase id="N">` | да | Одна реплика. `N` — целое `>= 0`. |
| `<text>...</text>` | да | ID строки в `st_<mod>.xml`. |
| `<next>ID</next>` | нет | Переход к реплике `ID`. Только парный тег, не атрибут. |
| `<precondition>dialogs.func</precondition>` | нет | Lua-условие показа реплики/диалога. |
| `<has_info>...</has_info>` | нет | У игрока есть поршень. |
| `<dont_has_info>...</dont_has_info>` | нет | У игрока нет поршня. |
| `<give_info>...</give_info>` | нет | Выдать поршень при выборе реплики. |
| `<action>dialogs.func</action>` | нет | Lua-эффект при выборе реплики. |

## 3.4. Стандарты генерации Lua-скрипта

Файл: `gamedata/scripts/<slug>_quests.script` (Lua 5.1).

Скрипт состоит из пяти слоёв:

1. Шапка-комментарий с именем модуля.
2. Статическая таблица `local QUESTS = { ... }` со всеми данными квестов.
3. Общие helper-функции (`vget`, `vset`, `get_smart`, `resolve_target`,
   `spawn_task_squad`, `freeze_squad`, `stage_cleared`, `run_actions`,
   `eval_conditions` и т. д.).
4. Плоские функции квестов и диалогов.
5. Модульная регистрация `register()`.

### Имена и регистрация

| Функция | Сигнатура | Таблица движка |
|---|---|---|
| `<quest_id>_target` | `(task_id, field, p, tsk)` | `task_functor` |
| `<quest_id>_descr` | `(task_id, field, p, tsk)` | `task_functor` |
| `<quest_id>_status` | `(tsk, task_id)` | `task_status_functor` |
| `<quest_id>_start` | `(actor, npc, p)` | `xr_effects` |
| `<quest_id>_reward` | `(actor, npc, p)` | `xr_effects` |
| `<quest_id>_cleanup` | `(actor, npc, p)` | `xr_effects` |
| `<quest_id>_accept` | `(actor, npc, p)` | `dialogs` |
| `<quest_id>_turn_in` | `(actor, npc, p)` | `dialogs` |
| `<dialog_id>_can_take` | `(actor, npc, p)` | `dialogs` |
| `<dialog_id>_can_turn_in` | `(actor, npc, p)` | `dialogs` |
| `<dialog_id>_accept` | `(actor, npc, p)` | `dialogs` |
| `<dialog_id>_turn_in` | `(actor, npc, p)` | `dialogs` |
| `<dialog_id>_phrase_<n>_precondition` | `(actor, npc, p)` | `dialogs` |
| `<dialog_id>_phrase_<n>_action` | `(actor, npc, p)` | `dialogs` |

> **Сигнатуры:** все эффекты и диалоговые функции имеют каноническую сигнатуру
> `(actor, npc, p)`. Функции `task_functor`/`task_status_functor` имеют штатные
> сигнатуры движка X-Ray и генерируются автоматически — вручную их не пишите.

### Модульная регистрация

`register()` вызывается на уровне модуля, а также через callback'и загрузки.
Регистрация идемпотентна и использует только плоские ключи:

```lua
local function register()
    if registered then return end
    if not (task_functor and task_status_functor and xr_effects and dialogs) then
        return
    end

    task_functor["my_quest_target"] = my_quest_target
    task_functor["my_quest_descr"] = my_quest_descr
    task_status_functor["my_quest_status"] = my_quest_status
    xr_effects["my_quest_start"] = my_quest_start
    xr_effects["my_quest_reward"] = my_quest_reward
    xr_effects["my_quest_cleanup"] = my_quest_cleanup
    dialogs["my_quest_accept"] = my_quest_accept
    dialogs["my_quest_turn_in"] = my_quest_turn_in

    registered = true
    printf("[my_mod_quests] task functors registered")
end

function on_game_start()
    register()
end

pcall(function()
    RegisterScriptCallback("on_game_load", function(binder) register() end)
    RegisterScriptCallback("actor_on_first_update", function(binder, delta) register() end)
end)

register()
```

Ключи **никогда** не получают префикс модуля: `task_functor["my_quest_target"]`,
а не `task_functor["my_mod_quests.my_quest_target"]`.

### Как выполняются действия

- `Quest.on_init_actions` — в `<quest_id>_start`, после выдачи `taken_info`.
- `Quest.on_complete_actions` — в `<quest_id>_reward`, после `reward_money`/
  `reward_item_alias`/`complete_info`. `taken_info` и `complete_info` при
  успехе **не снимаются**: это защищает стартовый диалог от повторного
  открытия. Поршни из `Quest.cleanup_infos` снимаются в конце `_reward`.
- `Quest.on_fail_actions` — в `<quest_id>_cleanup`; здесь `taken_info`
  снимается, потому что квест можно взять заново, а затем снимаются все
  `Quest.cleanup_infos`.
- `Stage.on_start_actions` — в `<quest_id>_status` ровно один раз за этап
  (ключ `<...>_v_<stage>_started`). `GiveItem` выносится в отдельный список
  `item_actions` и выдаётся идемпотентно на каждом тике, пока предмета в
  инвентаре меньше `count`. Все `GiveInfo` из `Stage.on_start_actions`
  автоматически добавляются в `Quest.cleanup_infos` (кроме `complete_info` и
  `done_info`) и снимаются в `<quest_id>_cleanup` при провале/отмене задачи.
  Это предотвращает утечку поршней готовности (`*_ready`) и открытие диалога
  сдачи сразу после повторного взятия квеста.
- `Phrase.actions`:
  - `GiveInfo` → прямой XML-тег `<give_info>`;
  - одиночный `GiveTask` → XML `<action>dialogs.<dialog_id>_accept</action>`;
  - одиночный `CompleteTask` → XML
    `<action>dialogs.<dialog_id>_turn_in</action>`;
  - любая комбинация действий (включая `GiveTask`/`CompleteTask` рядом с
    `SpawnSquad`, `GiveMoney`, `TakeMoney`, `GiveItem`, `RemoveItem`,
    `TakeItem`, `RemoveInfo`, `SetTarget`) → **одна** Lua-функция
    `dialogs.<dialog_id>_phrase_<n>_action`, которая вызывает `run_actions`
    со всеми действиями в порядке объявления. В XML при этом ровно один
    `<action>`.
  - Второй `<action>` в реплике недопустим: движок его игнорирует.

> **Строки подсказок `_msg_start`, `_msg_reward`, `_msg_fail` и
> `_stage_<n>_msg`.** Генератор `st_<slug>.xml` **всегда** создаёт:
> `<quest_id>_msg_start` («Новое задание: <title_ru>.» / «New task:
> <title_en>.») для `pda_tip` в `<quest_id>_start`;
> `<quest_id>_msg_reward` и `<quest_id>_msg_fail` для `_reward`/`_cleanup`;
> `<quest_id>_stage_<n>_msg` — сообщение о **завершении** этапа. Для
> последнего используется `Stage.msg_complete_ru/en`, а если они не заданы —
> «Этап выполнен: <title_ru>.» / «Stage completed: <title_en>.». Так игрок
> видит результат выполненного этапа, а не заголовок следующего. Свои
> формулировки задаются через `Quest.msg_reward_ru/en`,
> `Quest.msg_fail_ru/en` и `Stage.msg_complete_ru/en`. `pda_tip`
> дополнительно проверяет перевод через `game.translate_string` и не выводит
> строку, если перевода нет, — сырые ID не попадают в левый бар КПК.
> Отсутствие строки больше не является тихим no-op: она генерируется всегда.

### Pstor и отряды

- Ключи pstor имеют вид `<mod_prefix>_<quest_id>_v_<stage>_<suffix>` и никогда
  не совпадают с `task_id` (его `task_manager` очищает сам).
- Отряды, заспавненные квестом, помечаются в
  `sim_offline_combat.task_squads`, чтобы не уходить в офлайн-бой.
- Для `Stage.target_squad_id` используется отдельный ключ
  `<...>_target_seen`: он фиксирует, что отряд был обнаружен живым, и
  сбрасывается при старте квеста.
- При завершении/провале квеста отряды освобождаются.

## 3.5. Стандарты генерации LTX-задач

Файл: `gamedata/configs/misc/task/tm_<slug>.ltx`.

Пример секции:

```ltx
[my_quest]
icon                  = ui_inGame2_Put_v_pripyat
prior                 = 60
storyline             = true
title                 = my_quest_title
descr                 = my_quest_descr
descr_functor         = my_quest_descr
target_functor        = my_quest_target
status_functor        = my_quest_status
stage_complete        = 2
dont_send_update_news = true

on_init               = %=my_quest_start()%
on_complete           = %=my_quest_reward()%
on_fail               = %=my_quest_cleanup()%
on_cancel             = %=my_quest_cleanup()%
```

Жёсткие правила:

1. Секция называется ровно `[<quest_id>]`.
2. Имена функторов — плоские, без префикса Lua-модуля.
3. Эффекты записываются только в форме `%=<quest_id>_start()%`: скобки вызова
   обязательны.
4. Награды (`reward_money`, `reward_item_alias`) в LTX не попадают — они
   выдаются из Lua-эффекта `_reward`.
5. `stage_complete` равен количеству этапов. Финальный этап «сдача» обязан
   существовать явно, **если сдача не идёт через диалог с `HasInfo`-гейтом**
   (поршнем готовности `*_ready` из `Stage.on_start_actions`): явный этап даёт
   корректный маркер цели и `stage_complete`, а также позволяет `_can_turn_in`
   проверить `tsk.stage`. Если сдача держится на `*_ready`, такой поршень
   должен быть в `Quest.cleanup_infos` и сниматься при провале/отмене (см. ниже
   и §2.8).
6. Если задан `npc_id`/`giver_npc_id`, добавляется
   `condlist_0 = {!task_giver_alive(<quest_id>)} fail`.
7. Файл `task_manager.ltx` не патчится: он сам подхватывает `tm_*.ltx` через
   `#include`.

Пример явного этапа сдачи (3 этапа, `stage_complete = 3`):

```python
stages={
    0: Stage(id=0, target_alias="esc_smart_terrain_2_12"),
    1: Stage(id=1, target_alias="esc_smart_terrain_5_7"),
    # Финальный этап «вернуться» существует явно. Сдача идёт диалогом:
    # return_to_giver_stage не задаётся, а _can_turn_in проверяет tsk.stage.
    2: Stage(id=2, target_alias=""),
}
```

```ltx
[mymod_av_quest]
stage_complete        = 3
```

Если финальный этап убрать, `stage_complete` станет `2`, а сдача будет
держаться на `*_ready` из `on_start_actions`. Это допустимо только при
обязательной очистке такого поршня: генератор автоматически добавляет все
`GiveInfo` из `Stage.on_start_actions` в `Quest.cleanup_infos` и снимает их в
`_cleanup`, а для диалога сдачи без `HasInfo` дополнительно включает проверку
`tsk.stage >= Quest.last_stage`. В противном случае `_can_turn_in` открыл бы
сдачу на этапе захвата.

## 3.6. Предполётная валидация (`validate_project` и CLI `main.py validate`)

До записи файлов проект проверяется пакетом `src/validation/`. Точка входа:

```python
from src.validation import validate_project

report = validate_project(project, db)   # db: GameDatabase | None
if report.has_errors:
    report.raise_if_errors()             # или обработайте report.to_dict()
```

`validate_project(project, db=None) -> ValidationReport` запускает три
валидатора в фиксированном порядке: `CatalogValidator` → `GraphValidator` →
`XrayLinter`. Все замечания попадают в один отчёт; `ERROR` блокирует сборку,
`WARNING` выводится в отчёт и не блокирует её (кроме режима `--strict`).

### Автоматическая проверка в `ModBuilder`

```python
builder.build_project(project)                 # validate=True по умолчанию
builder.build_project(project, validate=False) # отключить предполётную проверку
```

При `validate=True` сборщик вызывает `validate_project` **до** создания
каталогов и записи файлов. Если в отчёте есть `ERROR`:

1. сборка не начинается и возвращает `False`;
2. причина и коды замечаний пишутся в `logs/app.log`;
3. файлы мода не записываются.

`WARNING` не блокирует сборку, но попадает в лог. Отключайте проверку только
для диагностических запусков — не для релизной сборки.

### CLI

```text
python main.py validate <script.py> [--json report.json] [--strict]
```

- `<script.py>` — файл-сценарий, который создаёт и возвращает `ModProject`;
- `--json report.json` — сохранить машиночитаемый отчёт
  (`summary` + `issues`) в указанный файл;
- `--strict` — считать `WARNING` ошибкой (для CI).

Коды выхода:

| Код | Значение |
|---:|---|
| `0` | Ошибок нет (при `--strict` — нет и предупреждений). |
| `1` | Есть хотя бы один `ERROR`. Сборку запускать нельзя. |
| `2` | `ERROR` нет, но при `--strict` есть `WARNING`. |

### Категории правил

`CAT-*`, `GRAPH-*` и `XRAY-*` выдаёт `validate_project`; `MERGE-*` — отдельный
`MergeValidator` на этапе объединения глав (§2.13).

| Префикс | Что проверяет | Примеры кодов |
|---|---|---|
| `CAT-*` | Ассеты по БД: NPC/`specific_character`, смарты, предметы, отряды, фракции, диалоги. | `CAT-NPC-001`, `CAT-SMART-003`, `CAT-SQUAD-002`, `CAT-WARFARE-001` |
| `GRAPH-*` | Связи PK/FK и логический граф: info, этапы, награды, очистка, смерть отряда. | `GRAPH-INFO-001`, `GRAPH-STAGE-002`, `GRAPH-REWARD-001`, `GRAPH-CLEAN-001` |
| `XRAY-*` | Ловушки движка X-Ray/Anomaly: спавн, `meet`, порядок действий, режимы, локализация. | `XRAY-SPAWN-001`, `XRAY-MEET-001`, `XRAY-SPAWNITEM-001`, `XRAY-MODE-002` |
| `MERGE-*` | Слияние глав: дубли ключей/`story_id`, общие поршни, единый префикс. | `MERGE-ID-001`, `MERGE-INFO-001`, `MERGE-NS-001` |

> **Порядок работы.** Сначала `ModProject.merge` (§2.13) и
> `MergeValidator`, затем `validate_project` для объединённого проекта,
> и только после успешной проверки — `build_project(..., validate=True)`.

## 3.7. Кодировка, BOM и переносы строк

| Файл | Кодировка | BOM | Переносы |
|---|---|---|---|
| `tm_<slug>.ltx` | Windows-1251 | нет | `\n` |
| `dialogs_<slug>.xml` | Windows-1251 | нет | `\n` |
| `st_<slug>.xml` | Windows-1251 | нет | `\n` |
| `<slug>_quests.script` | Windows-1251 | нет | `\n` |
| патченный `system.ltx` | Windows-1251 | как в ванили | как в ванили |
| патченный `character_desc_<level>.xml` | Windows-1251 | как в ванили | как в ванили |

- Сгенерированные файлы пишутся **без BOM**.
- Унаследованные патченные файлы сохраняют исходный BOM (`EF BB BF`) и
  доминирующий стиль переносов.
- XML-декларация всегда:
  `<?xml version="1.0" encoding="windows-1251"?>`.
- Текст экранируется: `&`, `<`, `>`, `"`, `'` превращаются в XML-сущности.

## 3.8. Ограничения идентификаторов и данных

1. `Quest.id` и `Dialog.id` должны быть валидными Lua-идентификаторами:
   `[A-Za-z_][A-Za-z0-9_]*`.
2. Зарезервированные слова Lua (`end`, `for`, `local`, `nil`, `then`, `true`,
   `false`, `function`, `return`, ...) запрещены.
3. `Quest.id` не должен содержать пробелы и символы `[]=\r\n` (ограничение
   LTX-секции).
4. ID должны быть уникальны в пределах проекта.
5. Этапы нумеруются подряд с `0`; ключи совпадают с `Stage.id`.
6. Фразы нумеруются целыми числами `>= 0`; ключи совпадают с `Phrase.id`.
7. `next_phrases` не могут ссылаться на несуществующие фразы.
8. `GiveTask.task_id` и `CompleteTask.task_id` должны ссылаться на
   существующий `Quest.id`.
9. `Dialog.task_id`, `Quest.dialog_id`, `Quest.dialog_ids` должны ссылаться на
   существующие сущности.
10. Игровые алиасы предметов, смартов и отрядов (`item_alias`, `smart_alias`,
    `squad_alias`) должны существовать в вашей сборке Anomaly/базе
    `data/anomaly_db.sqlite`. Ядро не подставляет их автоматически.

## 3.9. Ошибки сборки и их причины

`ModBuilder.build_project(project, *, validate=True)` возвращает `bool`:

- `True` — сборка успешна;
- `False` — критическая ошибка; подробности в `logs/app.log`.

Исключение `BuildError` поднимается внутри патчеров и перехватывается
`build_project`. Типичные причины:

| Причина | Результат |
|---|---|
| `validate=True` и в отчёте есть `ERROR` | `False`, коды в `logs/app.log`; файлы не пишутся. |
| Пустое `ModProject.name` | `False`, ERROR в лог. |
| `quests`/`dialogs` не словари | `False`, ERROR в лог. |
| Нет ванильного `_unpacked/configs/system.ltx` | `False`, ERROR в лог. |
| В `system.ltx` нет `[dialogs]`/`[profiles]` или нужного ключа | `False`, ERROR в лог. |
| Нет `character_desc_<level>.xml` | `False`, ERROR в лог. |
| `<specific_character id="...">` не найден | `False`, ERROR в лог. |
| `<specific_character id="...">` найден дважды | `False`, ERROR в лог. |
| У диалога есть `npc_id`, но нет `npc_location` | `False`, ERROR в лог. |
| Ошибка записи файла / кодировки | `False`, ERROR в лог. |

## 3.10. Публичный API сборщика

```text
ModBuilder(
    output_dir: Path = Path("output"),
    db_client: GameDatabase | None = None,
    vanilla_root: Path = Path("_unpacked"),
)

ModBuilder.build_project(project: ModProject, *, validate: bool = True) -> bool
ModBuilder.patch_system_ltx(
    text: str,
    mod_slug: str,
    character_desc_files: Sequence[str] = (),
) -> str
ModBuilder.patch_character_desc(
    text: str,
    npc_id: str,
    dialog_ids: Sequence[str],
) -> str
```

### `ModBuilder.__init__`

| Аргумент | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `output_dir` | `Path` | `Path("output")` | Корень сборки. Внутри создаётся каталог `<slug>`. |
| `db_client` | `GameDatabase \| None` | `None` | Необязательный клиент SQLite. Передаётся в `LuaGenerator`; сейчас не используется для проверок ассетов. |
| `vanilla_root` | `Path` | `Path("_unpacked")` | Корень распакованной ванильной игры. Тесты обязаны передавать временное fake-дерево. |

### `build_project(project, *, validate=True) -> bool`

Главная точка входа. Выполняет полный цикл:

1. Проверяет `name`, `quests`, `dialogs`.
2. При `validate=True` запускает `validate_project`; при `ERROR` возвращает
   `False` и пишет отчёт в `logs/app.log` (см. §3.6).
3. Вычисляет slug и очищает `output/<slug>`.
4. Создаёт структуру `gamedata`.
5. Генерирует LTX/XML/Lua.
6. Собирает привязки диалогов к NPC и патчит профили.
7. Патчит `system.ltx`.
8. Записывает все файлы в cp1251 и проверяет их физическое наличие.

Возвращает `True` при успехе и `False` при любой критической ошибке. Исключения
не выходят наружу: они журналируются в `logs/app.log`.

### `patch_system_ltx(...) -> str`

Публичный текстовый патчер для диагностики и тестов. Принимает декодированный
текст `system.ltx`, slug мода и список имён `character_desc_<level>` (без
расширения). Возвращает пропатченный текст. Поднимает `BuildError`, если нет
обязательной секции/ключа или после патча значение встречается не ровно один
раз. Обычным скриптам вызывать не нужно — используйте `build_project`.

### `patch_character_desc(...) -> str`

Публичный текстовый патчер одного профиля. Принимает XML-текст, точный
`npc_id` и последовательность `dialog_ids`. Вставляет отсутствующие
`<actor_dialog>` перед `</specific_character>`, сохраняя комментарии,
форматирование и чужие профили. Поднимает `BuildError` при отсутствии или
дубликате `<specific_character>`. Обычным скриптам вызывать не нужно.

### `BuildError`

```python
from src.compiler.builder import BuildError
```

Внутреннее исключение патчеров. Наружу из `build_project` не выходит; если вы
вызываете `patch_system_ltx` или `patch_character_desc` напрямую, обработайте
его сами.

---

# 4. Практический шаблон-руководство для сложных сюжетов

## 4.1. Сценарий примера

| Элемент | Значение |
|---|---|
| Квестодатель | Душман |
| `npc_id` | `cit_killers_merc_trader_stalker` |
| `npc_location` | `deadcity` |
| Квест | `deadcity_dushman_pda` — найти ПДА в лагере наёмников и вернуть Душману |
| Квестовый предмет | `itm_pda_common` |
| Награда | 50 000 рублей + `wpn_ak74` + поршень завершения |
| Диалог выдачи | `deadcity_dushman_take` (Согласие / Отказ) |
| Диалог сдачи | `deadcity_dushman_turnin` (проверка `itm_pda_common`) |
| Этап 0 | Спавн вражеского отряда через `SpawnSquad`; завершается при наличии ПДА |
| Этап 1 | Вернуться к Душману и сдать квест через диалог |

Логика:

1. Игрок говорит с Душманом. В диалоге две ветки: «Берусь» и «Не сейчас».
2. При согласии выдаются поршень старта `deadcity_dushman_pda_started` и задача
   через `GiveTask`.
3. На этапе 0 срабатывает `SpawnSquad` и спавнит вражеский отряд на смарте.
4. Когда в инвентаре появляется `itm_pda_common`, `transfer_conditions`
   переводит квест на этап 1.
5. Игрок возвращается к Душману. В диалоге сдачи вторая ветка проверяет
   `HasItem(item_alias="itm_pda_common")`.
6. При сдаче Душман забирает ПДА, выдаёт 50 000 рублей, оружие, поршень
   завершения и завершает задачу через `CompleteTask`.

## 4.2. Полный Python-скрипт

Скрипт рассчитан на запуск из корня проекта:

```text
python examples/deadcity_dushman_demo.py
```

```python
"""Эталонный сюжет: Душман в Мёртвом Городе.

Сценарий демонстрирует полный цикл:
- диалог-выбор «Согласие / Отказ»;
- выдачу поршня старта и задачи через GiveTask;
- SpawnSquad на этапе квеста;
- проверку квестового предмета в preconditions диалога сдачи;
- сдачу через RemoveItem + GiveInfo + CompleteTask в одной реплике
  (единый `<action>`);
- награду через Quest.reward_money / Quest.reward_item_alias, а не через
  GiveMoney/GiveItem в actions;
- сборку мода через ModBuilder.

Запуск из корня проекта:
    python examples/deadcity_dushman_demo.py
"""

from __future__ import annotations

from pathlib import Path

from src.compiler.builder import ModBuilder
from src.core.models import (
    CompleteTask,
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveTask,
    HasItem,
    ModProject,
    Phrase,
    Quest,
    RemoveItem,
    SpawnSquad,
    Stage,
)

# ---------------------------------------------------------------------------
# Константы сценария
# ---------------------------------------------------------------------------

PROJECT_NAME = "Dead City: Dushman's Debt"

QUEST_ID = "deadcity_dushman_pda"
TAKE_DIALOG_ID = "deadcity_dushman_take"
TURNIN_DIALOG_ID = "deadcity_dushman_turnin"

NPC_ID = "cit_killers_merc_trader_stalker"
NPC_LOCATION = "deadcity"
NPC_ALIAS = "deadcity.dushman"

# Секция квестового предмета. Должна существовать в вашей сборке Anomaly.
QUEST_ITEM = "itm_pda_common"

# Секция оружия-награды. Замените на реальную секцию из data/anomaly_db.sqlite.
REWARD_WEAPON = "wpn_ak74"
REWARD_MONEY = 50000

# Секция вражеского отряда и алиас смарта. Оба значения должны существовать
# в вашей сборке; проверьте их через `python main.py search <имя> -t squad/smart`.
# Валидный enemy-отряд Anomaly 1.5.3: squad.killer_advanced
# (игровой ID merc_sim_squad_advanced). NPC-секция здесь недопустима.
ENEMY_SQUAD = "squad.killer_advanced"
TARGET_SMART = "deadcity.hospital"

# Информационные поршни сценария.
START_INFO = "deadcity_dushman_pda_started"
DONE_INFO = "deadcity_dushman_pda_done"


# ---------------------------------------------------------------------------
# Построение моделей проекта
# ---------------------------------------------------------------------------

def create_dushman_project() -> ModProject:
    """Создаёт проект с квестом Душмана в Мёртвом Городе.

    Returns:
        ModProject: Полностью валидный проект мода, готовый к сборке.

    Raises:
        pydantic.ValidationError: Если нарушены инварианты моделей.
    """
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        giver_npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[TAKE_DIALOG_ID, TURNIN_DIALOG_ID],
        title_ru="Долг Душмана",
        title_en="Dushman's Debt",
        descr_ru=(
            "Найдите ПДА в лагере наёмников в Мёртвом Городе и верните "
            "его Душману."
        ),
        descr_en=(
            "Find the PDA in the mercenary camp in Dead City and return "
            "it to Dushman."
        ),
        is_storyline=True,
        icon="ui_inGame2_Put_v_pripyat",
        prior=60,
        # Награда выдаётся эффектом _reward после завершения задачи.
        reward_money=REWARD_MONEY,
        reward_item_alias=REWARD_WEAPON,
        reward_item_count=1,
        stages={
            0: Stage(
                id=0,
                title_ru="ПДА в лагере наёмников",
                title_en="PDA in the mercenary camp",
                descr_ru=(
                    "Обыщите лагерь наёмников и заберите квестовый ПДА."
                ),
                descr_en=(
                    "Search the mercenary camp and recover the quest PDA."
                ),
                target_alias=TARGET_SMART,
                on_start_actions=[
                    # Точка спавна не должна совпадать со смартом квестодателя.
                    # target_alias — независимый маркер КПК, а не место спавна.
                    SpawnSquad(
                        squad_alias=ENEMY_SQUAD,
                        smart_alias=TARGET_SMART,
                        mode="story",
                    ),
                ],
            ),
            1: Stage(
                id=1,
                title_ru="Вернуться к Душману",
                title_en="Return to Dushman",
                descr_ru=(
                    "Вернитесь в Мёртвый Город и отдайте ПДА Душману."
                ),
                descr_en=(
                    "Return to Dead City and give the PDA to Dushman."
                ),
                target_alias="",
            ),
        },
        # Этап 0 завершается, как только ПДА оказывается в инвентаре игрока.
        transfer_conditions={
            0: {"complete": [HasItem(item_alias=QUEST_ITEM)]},
        },
    )

    take_dialog = Dialog(
        id=TAKE_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="take",
        # После старта квеста диалог выдачи больше не показывается.
        preconditions=[DontHasInfo(info=START_INFO)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Душман, слышал, у тебя проблемы с наёмниками?",
                text_en="Dushman, I heard you have a problem with the mercenaries?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Есть дело. Возьмёшься?",
                text_en="I have a job. Will you take it?",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Берусь. Говори, где искать.",
                text_en="I'm in. Tell me where to look.",
                actions=[
                    GiveInfo(info=START_INFO),
                    GiveTask(task_id=QUEST_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Не подведи.",
                text_en="Don't let me down.",
            ),
            4: Phrase(
                id=4,
                text_ru="Не сейчас. Найди кого-нибудь другого.",
                text_en="Not now. Find someone else.",
            ),
        },
    )

    turnin_dialog = Dialog(
        id=TURNIN_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turnin",
        phrases={
            0: Phrase(
                id=0,
                text_ru="Душман, я принёс ПДА.",
                text_en="Dushman, I brought the PDA.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Показывай, что там у тебя.",
                text_en="Show me what you've got.",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Держи. ПДА у меня.",
                text_en="Here. I have the PDA.",
                # Ветка сдачи доступна только при наличии предмета.
                preconditions=[HasItem(item_alias=QUEST_ITEM)],
                # GiveInfo — нативный <give_info>; остальные действия
                # сливаются в одну dialogs.<dialog>_phrase_2_action.
                actions=[
                    RemoveItem(item_alias=QUEST_ITEM, count=1),
                    GiveInfo(info=DONE_INFO),
                    CompleteTask(task_id=QUEST_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Хорошая работа. Держи награду.",
                text_en="Good work. Here's your reward.",
            ),
            4: Phrase(
                id=4,
                text_ru="Ещё ищу. Не всё так просто.",
                text_en="Still looking. It's not that simple.",
            ),
        },
    )

    return ModProject(
        name=PROJECT_NAME,
        required_mods=[],
        quests={quest.id: quest},
        dialogs={
            take_dialog.id: take_dialog,
            turnin_dialog.id: turnin_dialog,
        },
    )


# ---------------------------------------------------------------------------
# Сборка
# ---------------------------------------------------------------------------

def main() -> None:
    """Создаёт проект и запускает сборку установочного каталога мода."""
    project = create_dushman_project()

    builder = ModBuilder(
        output_dir=Path("output"),
        vanilla_root=Path("_unpacked"),
    )

    if not builder.build_project(project):
        raise SystemExit("Сборка не удалась: смотрите logs/app.log.")

    print(f"Мод собран в: {builder.output_dir}")


if __name__ == "__main__":
    main()
```

## 4.3. Что сгенерируется и как это проверить

После запуска скрипта появится каталог:

```text
output/dead_city_dushmans_debt/gamedata/
├── configs/
│   ├── gameplay/
│   │   ├── dialogs_dead_city_dushmans_debt.xml
│   │   └── character_desc_deadcity.xml
│   ├── misc/task/tm_dead_city_dushmans_debt.ltx
│   ├── text/rus/st_dead_city_dushmans_debt.xml
│   ├── text/eng/st_dead_city_dushmans_debt.xml
│   └── system.ltx
└── scripts/
    └── dead_city_dushmans_debt_quests.script
```

Проверьте:

1. В `character_desc_deadcity.xml` у профиля
   `cit_killers_merc_trader_stalker` появились:
   ```xml
   <actor_dialog>deadcity_dushman_take</actor_dialog>
   <actor_dialog>deadcity_dushman_turnin</actor_dialog>
   ```
2. В `system.ltx` в `[dialogs] files` добавлен
   `dialogs_dead_city_dushmans_debt`, а в
   `[profiles] specific_characters_files` — `character_desc_deadcity`.
3. В `dialogs_dead_city_dushmans_debt.xml`:
   - у обоих диалогов есть `<phrase_list>`;
   - `phrase id="0"` — реплика Игрока, `phrase id="1"` — ответ NPC;
   - переходы оформлены как `<next>1</next>`, `<next>2</next>`;
   - в диалоге сдачи есть
     `<precondition>dialogs.deadcity_dushman_turnin_phrase_2_precondition</precondition>`;
   - в реплике сдачи ровно **один** `<action>`:
     `<action>dialogs.deadcity_dushman_turnin_phrase_2_action</action>`
     (RemoveItem + GiveInfo + CompleteTask внутри одной Lua-функции).
4. В `<slug>_quests.script`:
   - есть `local QUESTS = { ... }`;
   - функции имеют сигнатуру `(actor, npc, p)`;
   - в конце модуля вызывается `register()`;
   - ключи плоские: `task_functor["deadcity_dushman_pda_target"]`,
     `dialogs["deadcity_dushman_turnin_phrase_1_action"]` и т. д.
5. Ни в одном файле нет DLTX, `.ext`, `start_dialogs` или
   `MYMOD_DIALOG_INJECTIONS`.

## 4.4. Чек-лист адаптации шаблона под свой сюжет

1. Замените `NPC_ID` и `NPC_LOCATION` на реальные значения из вашей сборки.
2. Замените `QUEST_ITEM`, `REWARD_WEAPON`, `ENEMY_SQUAD`, `TARGET_SMART` на
   существующие секции/алиасы. Проверяйте их через:
   ```text
   python main.py search <имя> -t item
   python main.py search <имя> -t npc
   python main.py search <имя> -t smart
   python main.py search <имя> -t squad
   ```
3. Переименуйте `QUEST_ID`, `TAKE_DIALOG_ID`, `TURNIN_DIALOG_ID` в уникальные
   валидные Lua-идентификаторы.
4. Проверьте, что все `next_phrases` ссылаются на существующие фразы, а
   `phrases` содержит `id=0`.
5. Проверьте, что этапы идут подряд с `0`.
6. Если сдача должна быть автоматической при приближении к NPC, задайте
   `return_to_giver_stage` и уберите `CompleteTask` из диалога.
7. Если награда должна выдаваться автоматически эффектом `_reward`, заполните
   `reward_money`/`reward_item_alias`/`complete_info` и уберите соответствующие
   действия из реплики, чтобы не дублировать награду.
8. Если диалог не должен быть привязан к NPC, не задавайте `npc_id`
   (будет warning, диалог всё равно попадёт в XML).
9. Для Warfare-квестов используйте `WarfareCapture` и **не** добавляйте в тот
   же квест `SpawnSquad(mode="story")`. Для Story-квестов используйте только
   `SpawnSquad(mode="story")` и завершайте цепочку через
   `CustomSquad.death_infos` → `QuestCondlist` → `GiveTask`.
10. Если задача должна закрываться по смерти отряда, задайте
    `CustomSquad.death_infos`, продублируйте поршень в
    `QuestCondlist(when=[HasInfo(...)])` и не забудьте `cleanup_infos`,
    иначе повторное взятие задачи завершится мгновенно.
11. Проверьте, что все ID следуют стандарту `<mod_slug>_<chapter>_<quest>_<role>`
    и не пересекаются между поршнями, диалогами и задачами.
12. Запускайте сборку и проверяйте `logs/app.log` при `False`.

---

## 4.5. Кастомные NPC и отряды-наследники

### `CustomNpc`

`ModProject.npcs` объявляет уникального NPC мода. Сборщик создаёт
`spawn_sections_<slug>.ltx`, `npc_profile_<slug>.xml` и
`character_desc_<slug>.xml`, а диалоги с `npc_id=<CustomNpc.id>` привязывает
к профилю мода (ванильный `character_desc_<level>.xml` не патчится).

```python
from src.core.models import CustomNpc

envoy = CustomNpc(
    id="mymod_envoy",                 # секция spawn и профиль по умолчанию
    faction="stalker",
    template_npc_id="esc_2_12_stalker_wolf",  # донор visual/icon/bio/rank/...
    immortal=True,                    # секция <slug>_immunities_immortal
    story_id="mymod_envoy",           # обязателен для квестодателя
    spawn_smart="esc_smart_terrain_2_12",
    name_ru="Связной",
    name_en="Envoy",
)
```

* `template_npc_id` — ID из таблицы `npcs` БД. Недостающие
  `visual/icon/bio/rank/reputation/money/supplies` копируются из
  `<vanilla_root>/configs/gameplay/<source_file>`.
* Из шаблона также переносятся базовые диалоги взаимодействия:
  `<start_dialog>` и общие `<actor_dialog>` (`actor_break_dialog`, `dm_*`,
  `hello_dialog`, `meet_*`); чужие сюжетные диалоги шаблона не копируются.
  Если `CustomNpc.start_dialog` не задан, используется шаблонный, иначе
  `hello_dialog`. В `<specific_character>` всегда добавляется
  `<actor_dialog>actor_break_dialog</actor_dialog>` (кнопка «До встречи»),
  затем общие диалоги шаблона, затем `actor_dialogs` из модели и
  `project.dialogs` — без дублей.
* `immortal=True` генерирует `[<slug>_immunities_immortal]` (все 9 полей +
  `wound_2_immunity` = `0.0`) и `immunities_sect` в spawn-секции.
* `money_infinitive=True` выставляет `infinitive="1"` у `<money>`; для
  торговца/квестодателя это даёт бесконечные деньги.
* `spawn_smart` включает автоспавн: для NPC создаётся Story-отряд
  `[<npc_id>_solo_squad]` (`faction`, `npc`, `npc_in_squad = 1, 1`,
  `target_smart`, `story_id = <npc_id>_solo_squad`, `relationship = friend`).
  Lua-генератор вызывает его в `actor_on_first_update` и помечает факт
  спавна инфопоршнем `<mod_slug>_npc_<npc_id>_spawned`; повторный спавн после
  загрузки сейва не выполняется. `ClearSmart` всегда сохраняет этот отряд.
  После спавна `story_id` регистрируется **на самом NPC** (первый член
  отряда), поэтому `target_alias="<npc.story_id>"` ставит маркер КПК ровно на
  персонажа, а не на центр смарта.
* Валидация: `CAT-CUSTOM-001..012` (ID/префикс, фракция, story_id,
  `template_npc_id`, `spawn_smart`, бессмертие и т. д.).

### `CustomSquad.template_squad_id`

```python
from src.core.models import CustomSquad

squad = CustomSquad(
    id="mymod_atp_squad",
    faction="bandit",
    template_squad_id="bandit_sim_squad_advanced",
    target_smart="esc_smart_terrain_7_11",
    story_id="mymod_atp_squad",
)
```

Секция генерируется как `[<id>]:<template_squad_id>`, поэтому состав
`npc`/`npc_random` может быть пустым: он наследуется от ванильного отряда.
`template_squad_id` обязан существовать в таблице `squads` БД
(`CAT-CUSTOM-012`). Ссылки `npc`/`npc_random` на `CustomNpc.id` допустимы
(`CAT-CUSTOM-004`).

**Командир отряда:** первый элемент списка `CustomSquad.npc` всегда является
лидером (командиром) отряда. Именно к нему привязываются диалоги с отрядом,
выдача предметов в рюкзак через `SpawnNpcItem` и маркер `target_squad_id`.
Поэтому именной `CustomNpc`-командир должен стоять первым:

```python
squad = CustomSquad(
    id="mymod_freedom_squad",
    faction="freedom",
    npc=["mymod_freedom_leader", "sim_default_freedom_1"],
    npc_in_squad=[2, 2],
    target_smart="esc_smart_terrain_7_11",
    relationship="neutral",
    story_id="mymod_freedom_squad",
)
```

**Неквестовые диалоги и пункты взаимодействия (скупка/обмен/лор):**
`Dialog` может работать без квеста: `task_id=None`. Такой диалог привязывается
к `CustomNpc` через `npc_id` и может проверять предмет, забирать его и выдавать
деньги/информацию.

```python
from src.core.models import Dialog, GiveInfo, GiveMoney, HasItem, Phrase, RemoveItem

trade_dialog = Dialog(
    id="mymod_envoy_trade",
    dialog_id="mymod_envoy_trade",
    npc_id="mymod_envoy",
    npc_location="escape",
    task_id=None,                     # не создаёт квест
    role="",
    preconditions=[HasItem(item_alias="itm_pda_common", count=1)],
    phrases={
        0: Phrase(id=0, text_ru="Хочешь продать КПК?", next_phrases=[1]),
        1: Phrase(
            id=1,
            text_ru="Держи, мне он больше не нужен.",
            actions=[
                RemoveItem(item_alias="itm_pda_common", count=1),
                GiveMoney(amount=3000),
                GiveInfo(info="mymod_envoy_pda_sold"),
            ],
        ),
    },
)
```

---

## Приложение. Минимальная шпаргалка по импортам

```python
from src.compiler.builder import ModBuilder
from src.core.models import (
    # Корневые модели
    ModProject,
    Quest,
    QuestCondlist,
    Stage,
    TargetVariant,
    DescrVariant,
    Dialog,
    Phrase,
    CustomSquad,
    WarfareCapture,
    # Действия
    GiveInfo,
    RemoveInfo,
    SpawnSquad,
    SpawnNpcItem,
    RemoveSquad,
    ClearSmart,
    SetTarget,
    GiveItem,
    RemoveItem,
    TakeItem,
    GiveMoney,
    TakeMoney,
    GiveTask,
    CompleteTask,
    # Условия
    HasInfo,
    DontHasInfo,
    HasItem,
    HasMoney,
    SmartOwner,
    # Типы-алиасы
    Action,
    Condition,
    OptionalId,
    RequiredId,
)
```

Валидация и слияние глав:

```python
from src.validation import (
    MergeValidator,
    Severity,
    ValidationReport,
    validate_project,
)
```

---

## Приложение. Полная карта генерируемых имён

```text
Квест <quest_id>:
  LTX-секция:                         [<quest_id>]
  task_functor:                       <quest_id>_target, <quest_id>_descr
  task_status_functor:                <quest_id>_status
  xr_effects:                         <quest_id>_start,
                                      <quest_id>_reward,
                                      <quest_id>_cleanup
  dialogs:                            <quest_id>_accept,
                                      <quest_id>_turn_in
  строки:                             <quest_id>_title,
                                      <quest_id>_descr,
                                      <quest_id>_msg_start,
                                      <quest_id>_msg_reward,
                                      <quest_id>_msg_fail,
                                      <quest_id>_stage_<n>_title,
                                      <quest_id>_stage_<n>_descr,
                                      <quest_id>_stage_<n>_msg
  Story-поршни:                       condlist_N = {+<info>} complete,
                                      on_death = %+<info>% в squad_descr_<slug>.ltx

Диалог <dialog_id>:
  XML:                                <dialog id="<dialog_id>">
  dialogs:                            <dialog_id>_can_take,
                                      <dialog_id>_can_turn_in,
                                      <dialog_id>_accept,
                                      <dialog_id>_turn_in
  реплика <n>:
    XML text:                         <dialog_id>_phrase_<n>_text
    dialogs precondition:             <dialog_id>_phrase_<n>_precondition
    dialogs action:                   <dialog_id>_phrase_<n>_action
```

---

## Приложение. Быстрые ответы на частые вопросы

**Нужно ли писать Lua вручную?**
Нет. Вы описываете квест, этапы, диалоги, условия и действия Python-моделями.
Lua-скрипт генерируется автоматически.

**Где хранится привязка диалога к NPC?**
В ванильном `character_desc_<level>.xml`: сборщик копирует файл и вставляет
`<actor_dialog>dialog_id</actor_dialog>` в `<specific_character id="npc_id">`.

**Почему диалог не появился у NPC?**
Проверьте `npc_id`, `npc_location`, наличие ванильного
`character_desc_<level>.xml` и точное совпадение `id` профиля. При отсутствии
`npc_id` сборка выдаёт warning, при отсутствии `npc_location` — ошибку.

**Почему квест не продвигается?**
Проверьте `transfer_conditions`, `extra_condlists` (Story-поршни),
`warfare_capture` (работает только в Warfare), `target_squad_id` (отряд
должен быть обнаружен живым, а затем уничтожен), `on_start_actions` и
наличие этапа с нужным `target_alias`. Состояние хранится в pstor; после
изменения логики лучше начать новую игру или очистить сохранение.

**Чем Story-квест отличается от Warfare-квеста?**
Story-квест использует `SpawnSquad(mode="story")` и `CustomSquad` с
`death_infos`; он не обращается к `sim_squad_warfare` и работает при
отключённой симуляции. Warfare-квест использует `WarfareCapture` и требует
живой симуляции. Смешивать оба режима в одном квесте запрещено: валидатор
возвращает `BuildError`, поэтому такой сценарий разделяют на два квеста —
Warfare-квест с `requires_warfare=True` и Story-квест со
`SpawnSquad(mode="story")`.

**Как объединить несколько глав мода?**
Соберите каждую главу как отдельный `ModProject` с одним `mod_slug` и
объедините через `ModProject.merge(ch1, ch2, side_quests, mod_slug=..., mod_title=...)`.
Коллизии ключей и `story_id` дают `ValueError`; диагностику пространства имён
и общих поршней показывает `MergeValidator` (см. §2.13).

**Как проверить проект до сборки?**
Вызовите `validate_project(project, db)` или CLI
`python main.py validate <script.py> --json report.json --strict`.
`ERROR` блокирует сборку; `build_project(..., validate=True)` делает это
автоматически и пишет отчёт в `logs/app.log` (см. §3.6).

**Можно ли использовать DLTX?**
Нет. Ядро намеренно не генерирует `.dltx`, `.ext` и рантайм-инъекции диалогов.

**Где менять тексты?**
В моделях: `Quest.title_ru/en`, `Quest.descr_ru/en`,
`Stage.title_ru/en`, `Stage.msg_complete_ru/en`, `Stage.descr_ru/en`,
`Phrase.text_ru/en`.
Генератор сам создаст `st_<slug>.xml` для `rus` и `eng`.

**Что делать, если сборка вернула `False`?**
Откройте `logs/app.log`: там будет либо `Критическая ошибка ввода-вывода`,
либо `Критическая ошибка патча ванильных файлов` с точной причиной.
