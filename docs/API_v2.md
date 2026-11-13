# API справочник ядра квестов S.T.A.L.K.E.R. Anomaly

> **Статус документа:** единственный источник правды для внешних разработчиков и сторонних LLM.
> **Версия ядра:** стабилизированное ядро `src/core/models.py` + `src/compiler/*`.
> **Область применения:** Python 3.10+, Pydantic 2.x, S.T.A.L.K.E.R. Anomaly (X-Ray, Lua 5.1).

Этот файл описывает **весь публичный контракт** конструктора квестов: модели данных,
правила генерации игровых файлов, ограничения рантайма X-Ray и эталонный шаблон
сложного сюжета. Прочитав только `API.md`, можно писать новые Python-скрипты квестов
без изучения исходников ядра.

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

| Класс | `type` | Поля | Что генерируется / делает |
|---|---|---|---|
| `GiveInfo` | `"give_info"` | `info: RequiredId` | В реплике — `<give_info>info</give_info>`. В квесте/этапе — Lua `db.actor:give_info_portion(info)`. |
| `RemoveInfo` | `"remove_info"` | `info: RequiredId` | Lua `db.actor:disable_info_portion(info)`. |
| `SpawnSquad` | `"spawn_squad"` | `squad_alias: str`, `smart_alias: str` | Lua `SIMBOARD:create_squad` + `sim_squad_warfare.set_target` + заморозка. |
| `SetTarget` | `"set_target"` | `squad_alias: str`, `smart_alias: str` | Lua `sim_squad_warfare.set_target`. |
| `GiveItem` | `"give_item"` | `item_alias: str`, `count: int = 1` (`ge=1`) | Lua `give_item(...)`: `alife_create_item(section, actor)` по одному и одно уведомление `news_manager.relocate_item(actor, "in", section, count)`. Алиас разрешается в реальную секцию. |
| `RemoveItem` | `"remove_item"` | `item_alias: str`, `count: int = 1` (`ge=1`) | Lua `take_item(...)`: прямое изъятие из инвентаря игрока через `actor:iterate_inventory` + `alife_release`. |
| `TakeItem` | `"take_item"` | `item_alias: str`, `count: int = 1` (`ge=1`) | Семантический алиас `RemoveItem`: та же реализация `take_item`; ровно одно уведомление `news_manager.relocate_item(..., "out", ...)` при `removed > 0`. |
| `GiveMoney` | `"give_money"` | `amount: int` (`ge=0`) | Lua `give_money(...)`: `actor:give_money(amount)` и одно уведомление `news_manager.relocate_money(actor, "in", amount)`. |
| `TakeMoney` | `"take_money"` | `amount: int` (`ge=0`) | Lua `take_money(...)`: списание с ограничением по текущему балансу, без ухода в минус. |
| `GiveTask` | `"give_task"` | `task_id: RequiredId` | Единственное действие реплики — `<action>dialogs.<текущий_dialog_id>_accept</action>`; в Lua — `give_task`. В комбинации с другими действиями сливается в единую `dialogs.<dialog_id>_phrase_<n>_action`. |
| `CompleteTask` | `"complete_task"` | `task_id: RequiredId` | Единственное действие реплики — `<action>dialogs.<текущий_dialog_id>_turn_in</action>`; в Lua — `complete_task`. В комбинации с другими действиями сливается в единую `dialogs.<dialog_id>_phrase_<n>_action`. |

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

actions = [
    GiveInfo(info="my_quest_started"),
    SpawnSquad(squad_alias="squad.mercenary_advanced", smart_alias="deadcity.hospital"),
    SetTarget(squad_alias="squad.mercenary_advanced", smart_alias="deadcity.hospital"),
    GiveItem(item_alias="wpn_ak74", count=1),
    RemoveItem(item_alias="itm_pda_common", count=1),
    TakeItem(item_alias="itm_pda_common", count=1),
    GiveMoney(amount=50000),
    TakeMoney(amount=2500),
    GiveTask(task_id="my_quest"),
    CompleteTask(task_id="my_quest"),
]
```

> **Алиасы и секции.** Поля `item_alias` в `GiveItem`/`RemoveItem`/`TakeItem`
> и `item_alias` в `HasItem` принимают как прямую секцию (`itm_pda_common`,
> `wpn_ak105`), так и алиас из `data/anomaly_db.sqlite`. Если генератор получил
> `db_client`, алиас разрешается в секцию на этапе компиляции; без БД или при
> ошибке запроса строка используется как есть и сборка не падает.

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

| Класс | `type` | Поля | Где проверяется |
|---|---|---|---|
| `HasInfo` | `"has_info"` | `info: RequiredId` | XML `<has_info>`; Lua `has_alife_info(info)`. |
| `DontHasInfo` | `"dont_has_info"` | `info: RequiredId` | XML `<dont_has_info>`; Lua `not has_alife_info(info)`. |
| `HasItem` | `"has_item"` | `item_alias: str`, `count: int = 1` (`ge=1`) | Только Lua: подсчёт стаков в инвентаре `actor_item_count(item, actor) >= count`. Выносится в `dialogs.<...>_precondition` или `dialogs.<dialog_id>_can_take`. |
| `HasMoney` | `"has_money"` | `amount: int` (`ge=0`) | Только Lua: `db.actor:money() >= amount`. |
| `SmartOwner` | `"smart_owner"` | `smart_alias: str`, `faction: str` | Только Lua: `SIMBOARD.smarts_by_names[smart_alias].owning_faction == faction`. |

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
| `role` | `str \| None` | `None` | Роль: `take`, `take_assault`, `take_solo`, `turnin`, `turn_in`, `branch`. Влияет на порядок вставки `<actor_dialog>`. Для `take`/`take_*` диалог всегда получает `<precondition>dialogs.<dialog_id>_can_take</precondition>`, который блокирует повторное взятие после выдачи `complete_info`. |
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

## 2.6. `WarfareCapture` — опциональный сценарий захвата смарта

```python
class WarfareCapture(BaseModel):
    model_config = _MODEL_CONFIG

    smart_alias: str
    enemy_squad_alias: str
    ally_squad_alias: str | None = None
    ally_count: int = 0
```

| Поле | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `smart_alias` | `str` | обязательное | Алиас смарт-террейна, который нужно захватить. |
| `enemy_squad_alias` | `str` | обязательное | Секция вражеского отряда, который нужно уничтожить. |
| `ally_squad_alias` | `str \| None` | `None` | Секция союзного отряда, который спавнится на помощь. |
| `ally_count` | `int` (`ge=0`) | `0` | Сколько союзных отрядов заспавнить. |

Если `Stage.warfare_capture` задан, Lua-генератор включает автоматическую логику:

- `spawn_stage_for` спавнит вражеский отряд (и союзников) один раз за этап;
- `freeze_stage_for` замораживает отряды на точке;
- `stage_cleared` проверяет, что вражеский отряд уничтожен, а смарт захвачен
  (`smart.owning_faction == "army"` или `smart.defense_count <= 0`).

> **Ограничение рантайма:** при наличии `warfare_capture` квест помечается как
> `world = true`, и его `_status` не работает вне режима Warfare
> (`IsWarfare() == false`). Для обычных сюжетных квестов не задавайте
> `warfare_capture`.

## 2.7. `Stage` — один этап квеста

```python
class Stage(BaseModel):
    model_config = _MODEL_CONFIG

    id: int
    title_ru: str = ""
    title_en: str = ""
    descr_ru: str = ""
    descr_en: str = ""
    target_alias: str = ""
    target_squad_id: str | None = None
    on_start_actions: list[Action] = []
    warfare_capture: WarfareCapture | None = None
```

| Поле | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `id` | `int` (`ge=0`) | обязательное | Номер этапа. Ключ в `Quest.stages` обязан совпадать. |
| `title_ru` | `str` | `""` | Русский заголовок этапа. |
| `title_en` | `str` | `""` | Английский заголовок этапа. |
| `descr_ru` | `str` | `""` | Русское описание этапа. |
| `descr_en` | `str` | `""` | Английское описание этапа. |
| `target_alias` | `str` | `""` | Цель маркера: имя смарта, числовой server ID или story ID. |
| `target_squad_id` | `str \| None` | `None` | ID/секция/алиас отряда, который нужно физически уничтожить. Включает автоматическую проверку в `_status`. |
| `on_start_actions` | `list[Action]` | `[]` | Действия, выполняемые ровно один раз при входе в этап. |
| `warfare_capture` | `WarfareCapture \| None` | `None` | Включает автоматическую логику захвата смарта. |

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
текущего этапа. Факт выполнения сохраняется в pstor, поэтому действия не
повторяются после загрузки сохранения.

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

## 2.8. `Quest` — сюжетный квест

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
    is_storyline: bool = True
    icon: str | None = None
    prior: int | None = None
    stages: dict[int, Stage] = {}
    on_init_actions: list[Action] = []
    on_complete_actions: list[Action] = []
    on_fail_actions: list[Action] = []
    transfer_conditions: dict[int, dict[str, list[Condition]]] = {}
    reward_money: int | None = None
    reward_item_alias: str | None = None
    reward_item_count: int = 1
    complete_info: str | None = None
    taken_info: str | None = None
    return_to_giver_stage: int | None = None
    return_distance: float = 40.0
    available_info: str | None = None
    done_info: str | None = None
```

### Идентификаторы и связи

| Поле | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `id` | `RequiredId` | обязательное | ID секции LTX `[id]`, ключ `task_functor` и префикс всех функций. |
| `giver_npc_id` | `OptionalId` | `None` | Устаревшее имя ID квестодателя. Используется, если `npc_id` не задан. |
| `npc_id` | `OptionalId` | `None` | Игровой ID NPC-квестодателя. Попадает в `give_task` и `task_giver_alive`. |
| `npc_location` | `str \| None` | `None` | Локация квестодателя для патча `character_desc_<level>.xml`. |
| `dialog_id` | `OptionalId` | `None` | ID основного диалога выдачи квеста. |
| `dialog_ids` | `list[str]` | `[]` | Все связанные диалоги (выдача, сдача, ветки). |

### Тексты и PDA

| Поле | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `title_ru` / `title_en` | `str` | `""` | Название квеста в PDA. |
| `descr_ru` / `descr_en` | `str` | `""` | Описание квеста в PDA. |
| `is_storyline` | `bool` | `True` | Попадает в LTX как `storyline = true/false`. |
| `icon` | `str \| None` | `None` | Иконка PDA. По умолчанию `ui_inGame2_Put_v_pripyat`. |
| `prior` | `int \| None` (`ge=0`) | `None` | Приоритет в PDA. По умолчанию `60`. |

### Этапы и логика

| Поле | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `stages` | `dict[int, Stage]` | `{}` | Карта этапов. Ключи обязаны идти подряд с `0` и совпадать с `Stage.id`. |
| `on_init_actions` | `list[Action]` | `[]` | Действия эффекта `on_init` (`<quest_id>_start`). |
| `on_complete_actions` | `list[Action]` | `[]` | Действия эффекта `on_complete` (`<quest_id>_reward`). |
| `on_fail_actions` | `list[Action]` | `[]` | Действия `on_fail`/`on_cancel` (`<quest_id>_cleanup`). |
| `transfer_conditions` | `dict[int, dict[str, list[Condition]]]` | `{}` | Правила перехода этапов: `{stage: {"complete": [...], "fail": [...]}}`. |

Логика `_status` (упрощённо):

```text
каждый тик (с троттлингом):
  выполнить on_start_actions текущего этапа ровно один раз
  заспавнить/заморозить отряды warfare_capture, если задано
  если transfer_conditions[stage]["fail"] истинно -> "fail"
  если warfare_capture этап зачищён -> следующий этап или "complete"
  если transfer_conditions[stage]["complete"] истинно -> следующий этап или "complete"
  если stage == return_to_giver_stage и игрок рядом с квестодателем -> "complete"
```

### Награды и информационные поршни

| Поле | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `reward_money` | `int \| None` (`ge=0`) | `None` | Деньги, автоматически выдаваемые в `_reward`. |
| `reward_item_alias` | `str \| None` | `None` | Секция предмета, автоматически выдаваемого в `_reward`. |
| `reward_item_count` | `int` (`ge=1`) | `1` | Количество предметов награды. |
| `complete_info` | `str \| None` | `None` | Поршень, выдаваемый в `_reward`. |
| `taken_info` | `str \| None` | `None` | Поршень, выдаваемый в `_start`. Снимается только в `_cleanup` (провал/отмена); при успешном завершении сохраняется. |
| `return_to_giver_stage` | `int \| None` | `None` | Этап, на котором игрок должен вернуться к квестодателю. |
| `return_distance` | `float` (`ge=0`) | `40.0` | Радиус «подошёл к квестодателю» в метрах. |
| `available_info` | `str \| None` | `None` | Зарезервировано для внешних скриптов/UI; ядро только сохраняет значение в таблице `QUESTS`. |
| `done_info` | `str \| None` | `None` | Зарезервировано для внешних скриптов/UI; ядро только сохраняет значение в таблице `QUESTS`. |

> **Награда сдачи — только через `Quest.reward_*` или `on_complete_actions`.**
> Если вы задали `reward_money`, `reward_item_alias` или `complete_info`, не
> добавляйте те же `GiveMoney`/`GiveItem`/`GiveInfo` в диалоговые `actions`,
> иначе награда выдастся дважды.
>
> Если `reward_money`/`reward_item_alias` **пусты**, награда в `actions`
> реплики, где есть `CompleteTask`, не поддерживается: движок исполняет только
> один `<action>` на реплику, а `CompleteTask` завершает задачу раньше
> остальных эффектов. В результате игрок не получает ни денег, ни предмета.
> Надёжные пути:
>
> - `Quest.reward_money` / `Quest.reward_item_alias` (эффект `_reward`);
> - `Quest.on_complete_actions` (Lua после завершения задачи);
> - `Quest.complete_info` для поршня завершения.
>
> Компилятор (`ModBuilder.build_project`) выводит предупреждение в лог, если
> видит `GiveMoney`/`GiveItem` рядом с `CompleteTask` при пустых
> `reward_money`/`reward_item_alias`.

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

## 2.9. `ModProject` — корневой контейнер

```python
class ModProject(BaseModel):
    model_config = _MODEL_CONFIG

    name: str
    required_mods: list[str] = []
    quests: dict[str, Quest] = {}
    dialogs: dict[str, Dialog] = {}
```

| Поле | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `name` | `str` | обязательное | Человекочитаемое имя проекта. Из него вычисляется slug. |
| `required_mods` | `list[str]` | `[]` | Декларативный список зависимостей. Ядро его не проверяет. |
| `quests` | `dict[str, Quest]` | `{}` | Карта квестов. Ключ обязан совпадать с `Quest.id`. |
| `dialogs` | `dict[str, Dialog]` | `{}` | Карта диалогов. Ключ может отличаться от `Dialog.id`; канонический ID всегда берётся из модели. |

Валидатор `ModProject._validate_cross_references` проверяет:

- ключ `quests` совпадает с `Quest.id`;
- каждый `Quest.dialog_id` и каждый элемент `Quest.dialog_ids` существует в
  `dialogs`;
- каждый `Dialog.task_id` существует в `quests`.

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
10. **Ровно один `<action>` на реплику.** Если действий несколько, все они
    (включая `GiveTask`/`CompleteTask`) исполняются единой функцией
    `dialogs.<dialog_id>_phrase_<n>_action` строго в порядке объявления.
    Второй тег `<action>` движок отбрасывает.
11. Никакого захардкоженного `hello_dialog`: ID всегда приходит из модели.
12. `Phrase(id=0)` всегда принадлежит Игроку; чётные ID — Игрок, нечётные —
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
  `reward_item_alias`/`complete_info`. `taken_info` при успехе **не снимается**:
  это защищает стартовый диалог от повторного открытия.
- `Quest.on_fail_actions` — в `<quest_id>_cleanup`; здесь `taken_info`
  снимается, потому что квест можно взять заново.
- `Stage.on_start_actions` — в `<quest_id>_status` ровно один раз за этап.
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

> **Строки подсказок.** `_reward` и `_cleanup` вызывают `pda_tip` со строковыми
> ID `<quest_id>_msg_reward` и `<quest_id>_msg_fail`. Базовый генератор
> `st_<slug>.xml` создаёт `_title`, `_descr` и `_stage_<n>_*`; если вы хотите
> кастомные подсказки завершения/провала, добавьте `_msg_reward`/`_msg_fail` в
> свою таблицу строк. `pda_tip` проверяет перевод через `game.translate_string`
> и не выводит строку, если перевода нет, — сырые ID не попадают в левый бар КПК.

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
5. `stage_complete` равен количеству этапов.
6. Если задан `npc_id`/`giver_npc_id`, добавляется
   `condlist_0 = {!task_giver_alive(<quest_id>)} fail`.
7. Файл `task_manager.ltx` не патчится: он сам подхватывает `tm_*.ltx` через
   `#include`.

## 3.6. Кодировка, BOM и переносы строк

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

## 3.7. Ограничения идентификаторов и данных

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

## 3.8. Ошибки сборки и их причины

`ModBuilder.build_project(project)` возвращает `bool`:

- `True` — сборка успешна;
- `False` — критическая ошибка; подробности в `logs/app.log`.

Исключение `BuildError` поднимается внутри патчеров и перехватывается
`build_project`. Типичные причины:

| Причина | Результат |
|---|---|
| Пустое `ModProject.name` | `False`, ERROR в лог. |
| `quests`/`dialogs` не словари | `False`, ERROR в лог. |
| Нет ванильного `_unpacked/configs/system.ltx` | `False`, ERROR в лог. |
| В `system.ltx` нет `[dialogs]`/`[profiles]` или нужного ключа | `False`, ERROR в лог. |
| Нет `character_desc_<level>.xml` | `False`, ERROR в лог. |
| `<specific_character id="...">` не найден | `False`, ERROR в лог. |
| `<specific_character id="...">` найден дважды | `False`, ERROR в лог. |
| У диалога есть `npc_id`, но нет `npc_location` | `False`, ERROR в лог. |
| Ошибка записи файла / кодировки | `False`, ERROR в лог. |

## 3.9. Публичный API сборщика

```text
ModBuilder(
    output_dir: Path = Path("output"),
    db_client: GameDatabase | None = None,
    vanilla_root: Path = Path("_unpacked"),
)

ModBuilder.build_project(project: ModProject) -> bool
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

### `build_project(project) -> bool`

Главная точка входа. Выполняет полный цикл:

1. Проверяет `name`, `quests`, `dialogs`.
2. Вычисляет slug и очищает `output/<slug>`.
3. Создаёт структуру `gamedata`.
4. Генерирует LTX/XML/Lua.
5. Собирает привязки диалогов к NPC и патчит профили.
6. Патчит `system.ltx`.
7. Записывает все файлы в cp1251 и проверяет их физическое наличие.

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
ENEMY_SQUAD = "squad.mercenary_advanced"
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
                    SpawnSquad(
                        squad_alias=ENEMY_SQUAD,
                        smart_alias=TARGET_SMART,
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
9. Для Warfare-квестов используйте `WarfareCapture` вместо ручного
   `SpawnSquad`, либо комбинируйте их осознанно.
10. Запускайте сборку и проверяйте `logs/app.log` при `False`.

---

## Приложение. Минимальная шпаргалка по импортам

```python
from src.compiler.builder import ModBuilder
from src.core.models import (
    # Корневые модели
    ModProject,
    Quest,
    Stage,
    Dialog,
    Phrase,
    WarfareCapture,
    # Действия
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
                                      <quest_id>_stage_<n>_title,
                                      <quest_id>_stage_<n>_descr,
                                      <quest_id>_stage_<n>_msg

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
Проверьте `transfer_conditions`, `warfare_capture` (работает только в Warfare),
`target_squad_id` (отряд должен быть обнаружен живым, а затем уничтожен),
`on_start_actions` и наличие этапа с нужным `target_alias`. Состояние хранится
в pstor; после изменения логики лучше начать новую игру или очистить сохранение.

**Можно ли использовать DLTX?**
Нет. Ядро намеренно не генерирует `.dltx`, `.ext` и рантайм-инъекции диалогов.

**Где менять тексты?**
В моделях: `Quest.title_ru/en`, `Quest.descr_ru/en`,
`Stage.title_ru/en`, `Stage.descr_ru/en`, `Phrase.text_ru/en`.
Генератор сам создаст `st_<slug>.xml` для `rus` и `eng`.

**Что делать, если сборка вернула `False`?**
Откройте `logs/app.log`: там будет либо `Критическая ошибка ввода-вывода`,
либо `Критическая ошибка патча ванильных файлов` с точной причиной.
