# СТАНДАРТ АВТОМАТИЧЕСКОГО КОНВЕЙЕРА (No-Code Quest Framework)

> **Источник истины:** `tools/manual_mod_snapshot.txt` (эталонный ручной мод «M», 100% рабочий в игре).
> **Вспомогательный контекст:** `RULE.md` (проверенные точки входа движка X-Ray 1.6 / Monolith, Lua 5.1).
> **Назначение документа:** техническое задание на полное переписывание дата-моделей и генераторов
> с нуля. Всё, чего нет в эталонном слепке, считается недоказанным и в конвейер не попадает.
>
> **Дата фиксации:** 2026-11-11
> **Статус:** обязательный к исполнению стандарт (единственная истинная ДНК проекта).

---

## 0. Жёсткие запреты и их штатные замены

| Запрещено | Почему | Штатная замена из слепка «M» |
|---|---|---|
| **DLTX** (`*.dltx`, `*.ltx.dltx`-механики) | Не используется в эталоне; требует внешнего загрузчика | Прямой текст-патч ванильных `system.ltx` и `character_desc_*.xml` в собственной копии `gamedata` |
| **Директивы `.ext`** | Нет в эталоне | Обычные `.ltx` / `.xml` / `.script` |
| **Динамический Lua-код / `start_dialogs`** | Нет в эталоне; диалоги привязываются декларативно | Только `<actor_dialog>ID</actor_dialog>` внутри `<specific_character>` + `files = ..., dialogs_<mod>` в `[dialogs]` |
| Редактирование `_unpacked\configs`, `_unpacked\scripts` | Исходники игры read-only | Все патчи пишутся **только** в `build_root\gamedata\...` |
| `reward_item` в LTX задачи | Баг движка: ключ читается из `reward_money` | Предмет выдаётся эффектом `%=<task_id>_reward()%` через `alife_create_item` |
| Хранение состояния под ключом = `task_id` | `task_manager` чистит `save_var(db.actor, task_id, nil)` при завершении | Собственные pstor-ключи с префиксом мода (`<mod>_q1_v_spawn`, ...) |

**Три файла, которые требуют патча ванильных конфигов (и только они):**
1. `configs/system.ltx` — секции `[dialogs]` и `[profiles]`.
2. `configs/gameplay/character_desc_<level>.xml` — вживление `<actor_dialog>`.
3. (опционально) новый `configs/gameplay/character_desc_<mod>.xml` — тогда его имя добавляется в `specific_characters_files`.

**Файлы, которые НЕ требуют патча `system.ltx`** (движок подхватывает сам):
- `configs/misc/task/tm_<mod>.ltx` — через `#include "tm_*.ltx"` в `task_manager.ltx`;
- `configs/misc/squad_descr/squad_descr_<mod>.ltx` — через глоб `squad_descr_*.ltx`;
- `scripts/<mod>_quests.script` — через автосканер `axr_main` (непустой файл + `on_game_start()`).

---

## 1. ЭТАЛОННАЯ АРХИТЕКТУРА И СВЯЗИ ОВЕРЛЕЯ

### 1.1. Дерево `gamedata`, которое конвейер обязан генерировать с нуля

Дерево воспроизводит слепок «M» построчно. `<mod>` — технический префикс мода (например `mymod`),
`<level>` — имя локации персонажа (`escape`, `zaton`, `jupiter`, `pripyat`, ...).

```
<build_root>\
└── gamedata\
    ├── configs\
    │   ├── system.ltx                                  # ПАТЧ ванильного (копия + правка 2 секций)
    │   ├── gameplay\
    │   │   ├── dialogs_<mod>.xml                       # НОВЫЙ: весь граф диалогов мода
    │   │   └── character_desc_<level>.xml              # ПАТЧ ванильного: +<actor_dialog>
    │   ├── misc\
    │   │   ├── squad_descr\
    │   │   │   └── squad_descr_<mod>.ltx               # НОВЫЙ: квестовые отряды (авто-глоб)
    │   │   └── task\
    │   │       └── tm_<mod>.ltx                        # НОВЫЙ: секции задач (авто-#include)
    │   └── text\
    │       ├── eng\
    │       │   └── st_<mod>.xml                        # НОВЫЙ: английские строки
    │       └── rus\
    │           └── st_<mod>.xml                        # НОВЫЙ: русские строки (cp1251)
    └── scripts\
        └── <mod>_quests.script                         # НОВЫЙ: единый Lua-модуль квестов
```

Правила именования (жёсткие, иначе связи рвутся):
- `dialogs_<mod>.xml` — имя без расширения ровно то, что дописывается в `[dialogs] files = ...`;
- `character_desc_<level>.xml` — имя ровно из списка `specific_characters_files`;
- `squad_descr_<mod>.ltx` и `tm_<mod>.ltx` — соответствуют маскам `squad_descr_*.ltx` и `tm_*.ltx`;
- `<mod>_quests.script` — имя файла = имя глобальной таблицы `_G.<mod>_quests`; файл **непустой**;
- `<mod>` — единый префикс для **всех** глобальных имён Lua, секций LTX, id диалогов и id строк текста.

### 1.2. Каноничная структура `system.ltx` и обязательный патчер

Эталонная структура (фрагмент слепка «M», раздел 1 — файл `gamedata/configs/system.ltx`):

```ini
[dialogs]
files = dialogs, dialogs_agroprom, dialogs_agroprom_underground, dialogs_yantar, dialogs_marsh, \
dialogs_redforest, dialogs_katacomb, dialogs_escape, dialogs_bar, dialogs_zaton, dialogs_jupiter, \
dialogs_pripyat, dialogs_darkvalley, dialogs_deadcity, dialogs_garbage, dialogs_military, \
dialogs_truck, dialogs_warlab, dialogs_minigames, dialogs_mlr, dialogs_mlr_arena, \
dialogs_lostzone_ll, dialogs_lostzone_ms, dialogs_lostzone_oa, dialogs_lostzone_hb, dialogs_mymod

[profiles]
files                     = npc_profile, npc_profile_mlr, npc_profile_lostzone
specific_characters_files = character_desc_general, character_desc_marsh, character_desc_agroprom, \
character_desc_agroprom_underground, character_desc_darkvalley, character_desc_bar, \
character_desc_escape, character_desc_red_forest, character_desc_yantar, character_desc_military, \
character_desc_deadcity, character_desc_katacomb, character_desc_zaton, character_desc_pripyat, \
character_desc_jupiter, character_desc_underpass, character_desc_sarcofag, character_desc_warlab, \
character_desc_garbage, character_desc_darkscape, character_desc_truck, \
character_desc_lostzone_ll, character_desc_lostzone_ms, character_desc_lostzone_oa, \
character_desc_lostzone_hb
```

**Что обязан делать Python (алгоритм `ModBuilder.patch_system_ltx`):**

1. Открыть ванильный `system.ltx` как `bytes`, декодировать `cp1251` (BOM, если есть, сохранить отдельно).
2. Найти секцию `[dialogs]` **в границах секции** (от строки `[dialogs]` до следующей строки, начинающейся с `[`).
   Регулярное выражение:
   ```python
   SECTION_TMPL = r"(?ms)^\[{section}\][ \t]*\n(?P<body>.*?)(?=^\[|\Z)"
   FILES_LINE  = r"(?m)^(?P<key>files)[ \t]*=[ \t]*(?P<val>[^\n]*)$"
   ```
3. В найденном `body` взять строку `files = ...`, распарсить по запятым, `strip()` каждого элемента,
   и **в конец** списка добавить `dialogs_<mod>` (idempotent: если уже есть — не добавлять).
4. Переписать строку, сохранив исходный ключ и стиль `key + spaces + "= " + ", ".join(...)`.
5. Для секции `[profiles]`:
   - `files` — не трогать (там только `npc_profile*`; в эталоне новых профилей не добавлялось);
   - `specific_characters_files` — гарантировать наличие **каждого** `character_desc_<level>`, который
     патчится или генерируется конвейером. Отсутствующие имена дописываются в конец
     (для `character_desc_escape` — уже присутствует, повторно не добавлять).
6. Записать результат обратно байтами в `cp1251` без смешивания с UTF-8, сохранив исходный перенос строк.
7. Пост-проверка (assert): `dialogs_<mod>` встречается в `[dialogs].files` ровно 1 раз;
   каждый целевой `character_desc_<level>` встречается в `specific_characters_files` ровно 1 раз.

Псевдокод (обязателен к реализации в `ModBuilder`):

```python
def _append_csv_in_section(text: str, section: str, key: str, values: list[str]) -> str:
    m = re.search(SECTION_TMPL.format(section=re.escape(section)), text)
    if not m:
        raise BuildError(f"section [{section}] not found in system.ltx")
    body = m.group("body")
    lm = re.search(FILES_LINE.format(key=re.escape(key)), body)
    if not lm:
        raise BuildError(f"key '{key}' not found in [{section}]")
    current = [v.strip() for v in lm.group("val").split(",") if v.strip()]
    for v in values:
        if v not in current:
            current.append(v)
    new_line = f"{lm.group('key')} = {', '.join(current)}"
    body = body[: lm.start()] + new_line + body[lm.end() :]
    return text[: m.start("body")] + body + text[m.end("body") :]
```

**Важно:** `[dialogs] files` — это единственный канал подключения XML-графа диалогов.
Без этой строки диалоги не компилируются движком, даже если `<actor_dialog>` прописан.

### 1.3. Механизм перекрытия профилей NPC (`character_desc_*.xml`)

Эталон (раздел 2 слепка — `character_desc_escape.xml`) показывает, как диалог привязывается к NPC:

```xml
<specific_character id="esc_3_16_military_trader" team_default="1">
    <name>esc_3_16_military_trader_name</name>
    ...
    <actor_dialog>dm_init_trader</actor_dialog>
    <actor_dialog>mymod_av_quest_take</actor_dialog>
    <actor_dialog>mymod_av_quest_turnin</actor_dialog>
    <actor_dialog>mymod_atp_quest_take_assault</actor_dialog>
    <actor_dialog>mymod_atp_quest_take_solo</actor_dialog>
    <actor_dialog>mymod_atp_quest_turnin</actor_dialog>
    <actor_dialog>actor_break_dialog</actor_dialog>
</specific_character>
```

**Требование к `ModBuilder` — текстовый патчер, а не перезапись файла:**

- Файл берётся из **ванильного источника** и копируется в `build_root\gamedata\configs\gameplay\`.
- В копии ищется ровно одна секция нужного NPC. Регулярное выражение:
  ```python
  NPC_RE = re.compile(
      r"(?s)(?P<open><specific_character\b[^>]*\bid\s*=\s*[\"']{npc_id}[\"'][^>]*>)"
      r"(?P<body>.*?)"
      r"(?P<close></specific_character>)".format(npc_id=re.escape(npc_id))
  )
  ```
- В `body` вставляется строка `\t\t<actor_dialog>{dialog_id}</actor_dialog>\n` непосредственно перед `</specific_character>`
  (в эталоне — с табуляцией, на уровне остальных `<actor_dialog>`).
- **Идемпотентность:** если такой `<actor_dialog>ID</actor_dialog>` уже есть в `body` — ничего не добавлять.
- **Сохранность контента:** `body` не парсится в DOM и не сериализуется заново. Запрещено использовать
  `xml.etree`/`lxml` для записи этого файла — иначе теряются `#include`, комментарии, отступы и порядок тегов,
  и из игры выпадают другие уникальные персонажи. Только байтово-безопасная строковая вставка.
- Если `NPC_RE` не нашёл совпадения — `BuildError` с указанием `(file, npc_id)`, **без** создания нового блока
  (нельзя угадывать профиль NPC).
- Если найдено больше одного совпадения — `BuildError` (дубликат id ломает движок).
- Кодировка: `cp1251`; **BOM сохраняется как был** (в слепке первый байт присутствует — файл начинается с BOM).
  Декодировать с `utf-8-sig`/`cp1251-sig` нельзя; работать через `bytes` + `cp1251` и явно вернуть префикс `\xef\xbb\xbf`, если он был.
- Несколько диалогов на одного NPC — вставляются одним блоком в порядке ролей:
  `take`, `take_assault`, `take_solo`, `turnin`.

**Если создаётся новый `character_desc_<mod>.xml`:**
- он генерируется с корнем `<xml>` и полными `<specific_character>` (как в ваниле), а его имя
  дописывается в `[profiles] specific_characters_files` (см. 1.2, п.5);
- предпочтительный режим по умолчанию — **патч существующего файла локации**, как в эталоне.

---

## 2. СИНТАКСИС И ЧИСТЫЕ ПАТТЕРНЫ ГЕНЕРАЦИИ

### 2.1. XML-граф диалогов (`dialogs_<mod>.xml`)

Обязательная структура (эталон, раздел 3 слепка):

```xml
<?xml version="1.0" encoding="windows-1251"?>
<game_dialogs>
  <dialog id="mymod_av_quest_take">
    <precondition>dialogs.mymod_av_can_take</precondition>
    <has_info>mymod_quest_1_done</has_info>
    <phrase_list>
      <phrase id="0">
        <text>mymod_av_q_dlg_take_0</text>
        <next>1</next>
      </phrase>
      <phrase id="3">
        <text>mymod_av_q_dlg_take_3</text>
        <action>dialogs.mymod_av_accept</action>
      </phrase>
    </phrase_list>
  </dialog>
</game_dialogs>
```

Канонические правила:
1. Корень файла — `<game_dialogs>`; корень каждого диалога — `<dialog id="...">`.
2. Внутри `<dialog>` **обязателен** `<phrase_list>`; фразы — `<phrase id="N">` с целочисленными id.
3. Переходы — только парные теги `<next>ID</next>` (может быть несколько), без атрибутов.
4. Условия/эффекты — только через глобальные таблицы движка с полным именем:
   `<precondition>dialogs.<fn></precondition>`, `<action>dialogs.<fn></action>`.
   Допустимы `xr_effects.<fn>` как `<action>`; префиксы кастомных модулей (`<mod>_quests.<fn>`) **запрещены**.
5. Инфопоршни — без `+`/`-`: `<has_info>`, `<dont_has_info>`, `<give_info>`.
6. Порядок тегов внутри `<phrase>`: `<text>` → `<next>` → `<action>`; допускается `<script_text>`
   вместо `<text>`.
7. Соглашение эталона: чётные id — реплики актора, нечётные — реплики NPC (для читаемости; движок этого не требует).
8. Кодировка: `windows-1251`, BOM отсутствует, декларация `encoding="windows-1251"`.

**Чистый шаблон XML-генератора (f-строки):**

```python
DIALOG_XML = """<?xml version="1.0" encoding="windows-1251"?>
<game_dialogs>
{dialogs}</game_dialogs>
"""

DIALOG_BLOCK = """\t<dialog id="{dialog_id}">
{dialog_level_tags}\t\t<phrase_list>
{phrases}\t\t</phrase_list>
\t</dialog>
"""

DIALOG_LEVEL_TAG = "\t\t<{tag}>{value}</{tag}>\n"

PHRASE_BLOCK = """\t\t<phrase id="{phrase_id}">
{phrase_tags}\t\t</phrase>
"""

PHRASE_TAG = "\t\t\t<{tag}>{value}</{tag}>\n"
```

Сборка (референсная реализация):

```python
def render_dialog(d) -> str:
    head = ""
    for fn in d.preconditions:
        head += DIALOG_LEVEL_TAG.format(tag="precondition", value=f"dialogs.{fn}")
    for info in d.has_info:
        head += DIALOG_LEVEL_TAG.format(tag="has_info", value=info)
    for info in d.dont_has_info:
        head += DIALOG_LEVEL_TAG.format(tag="dont_has_info", value=info)

    phrases = ""
    for ph in sorted(d.phrases, key=lambda p: p.id):
        tags = ""
        if ph.script_text:
            tags += PHRASE_TAG.format(tag="script_text", value=f"dialogs.{ph.script_text}")
        else:
            tags += PHRASE_TAG.format(tag="text", value=ph.text_id)
        for nxt in ph.next:
            tags += PHRASE_TAG.format(tag="next", value=nxt)
        for act in ph.actions:          # порядок действий = порядок тегов
            tags += PHRASE_TAG.format(tag="action", value=f"dialogs.{act}")
        for info in ph.give_info:
            tags += PHRASE_TAG.format(tag="give_info", value=info)
        phrases += PHRASE_BLOCK.format(phrase_id=ph.id, phrase_tags=tags)

    return DIALOG_BLOCK.format(dialog_id=d.id, dialog_level_tags=head, phrases=phrases)
```

### 2.2. Паттерн LTX-задач (`tm_<mod>.ltx`)

Эталон (раздел 5 слепка — `tm_mymod.ltx`):

```ini
[mymod_av_quest]
icon                  = ui_inGame2_Nochnaya_ohota
prior                 = 60
storyline             = false
title                 = mymod_av_q_title
descr                 = mymod_av_q_descr
descr_functor         = mymod_av_quest_descr
target_functor        = mymod_av_quest_target
status_functor        = mymod_av_quest_status
stage_complete        = 3
dont_send_update_news = true

on_init               = %=mymod_av_quest_start()%
on_complete           = %=mymod_av_quest_reward()%
on_fail               = %=mymod_av_quest_cleanup()%
on_cancel             = %=mymod_av_quest_cleanup()%

condlist_0            = {!task_giver_alive(mymod_av_quest)} fail
```

Обязательные правила:
1. **Скобки вызова обязательны.** Каждый эффект в `on_init` / `on_complete` / `on_fail` / `on_cancel`
   оборачивается в `%= ... %`, а внутри — имя функции с круглыми скобками:
   `%={task_id}_start()%`, `%={task_id}_reward()%`, `%={task_id}_cleanup()%`.
   Форма без скобок, с пробелом перед `(` или с аргументами из воздуха — запрещена: аргументы
   передаются только если они реально объявлены в сигнатуре и перечислены через `:`.
2. `condlist_N` — состояние строго из `complete | fail | reversed | nil`; в эталоне используется
   `condlist_0 = {!task_giver_alive(<task_id>)} fail`.
3. `descr_functor`, `target_functor`, `status_functor` — **плоские** имена, совпадающие с ключами
   регистрации в Lua (см. 2.3), без `модуль.` префикса.
4. `stage_complete` — финальный номер этапа (в эталоне `3`), но завершение задачи делает
   `status_functor`, возвращая `"complete"`; `stage_complete` не завершает задачу сам.
5. `storyline = false` для побочных квестов; `prior = 60` — приоритет в PDA.
6. Секция задачи уникальна; файл кладётся рядом с ванильными `tm_*.ltx` и подхватывается
   `#include "tm_*.ltx"` — оригинальный `task_manager.ltx` не правится.
7. `reward_money`/`reward_item` в LTX **не использовать** (баг чтения `reward_item`).
   Деньги и предметы выдаются только в `_reward()`-эффекте.

**Шаблон LTX-генератора (f-строка; фигурные скобки condlist удваиваются):**

```python
TASK_LTX = """[{task_id}]
icon                  = {icon}
prior                 = {prior}
storyline             = false
title                 = {title_id}
descr                 = {descr_id}
descr_functor         = {task_id}_descr
target_functor        = {task_id}_target
status_functor        = {task_id}_status
stage_complete        = {stage_complete}
dont_send_update_news = true

on_init               = %={task_id}_start()%
on_complete           = %={task_id}_reward()%
on_fail               = %={task_id}_cleanup()%
on_cancel             = %={task_id}_cleanup()%

condlist_0            = {{!task_giver_alive({task_id})}} fail
"""
```

**Трансляция действий из дата-модели в код эффектов:**

| Действие в модели | Куда попадает | Что генерируется |
|---|---|---|
| `SpawnSquad(squad_section, base_smart, target_smart, is_ally)` | тело `%={task_id}_start()%` | вызов локального хелпера `spawn_squad(get_smart("<base>"), "<section>", get_smart("<target>"))`; для врага — `vset("<mod>_qN_enemy", squad.id)`, для союзника — `vset("<mod>_qN_allyK", squad.id)`; обязательно `mark_task_squad(squad)` + `stay_time` (см. 2.3) |
| `GiveMoney(amount)` | тело `%={task_id}_reward()%` | `db.actor:give_money(<amount>)` (в эталоне — `db.actor:give_money(10000)`) |
| `GiveItem(section, count)` | тело `%={task_id}_reward()%` | `alife_create_item("<section>", db.actor)` с `printe`, если вернулось `nil` |
| `GiveInfo(info_id)` | `_start()` / `_reward()` | `db.actor:give_info_portion("<info_id>")` |
| `RemoveInfo(info_id)` | `_cleanup()` | `db.actor:disable_info_portion("<info_id>")` |
| `UnmarkSquads` | `_cleanup()` | `unmark_task_squad(vget(key, 0))` для всех сохранённых id (обязательно, иначе отряды навсегда выпадают из симуляции) |

Данные квеста попадают в эффекты **не через аргументы**, а через статическую таблицу в начале скрипта:
`local QUESTS = { ["<task_id>"] = { smart = "...", enemy = "...", allies = {...}, money = 10000, item = "..." } }`.
Причина: в эталоне вызовы в `on_init`/`on_complete` идут без аргументов, а `p` в телах функций —
пустой список. Генератор обязан сохранить эту форму.

### 2.3. Паттерн Lua-генератора (`<mod>_quests.script`)

**Плоская сигнатура.** Все условия и экшены — строго `function(actor, npc, p)`.
Функторы задач имеют фиксированные сигнатуры движка:

| Таблица | Ключ | Сигнатура |
|---|---|---|
| `task_functor` | `<task_id>_target` | `function(task_id, field, p, tsk)` → возвращает story id / server id / имя; `field == "target"` |
| `task_functor` | `<task_id>_descr` | `function(task_id, field, p, tsk)` → id строки; `field == "descr"` |
| `task_status_functor` | `<task_id>_status` | `function(tsk, task_id)` → `"complete"` / `"fail"` / `nil`; здесь же переключается `tsk.stage` |
| `xr_effects` | `<task_id>_start` / `_reward` / `_cleanup` | `function(actor, npc, p)` |
| `dialogs` | `<dialog_slug>_can_take` / `_can_turn_in` | `function(actor, npc, p)` → `true/false` |
| `dialogs` | `<dialog_slug>_accept` / `_turn_in` | `function(actor, npc, p)` |

**Структура файла (обязательный скелет):**

```lua
--[[<mod>_quests.script
     Generated by quest-framework. Lua 5.1. No goto, no bitwise ops.
     All globals are flat and prefixed with "<mod>_".]]

local QUESTS = { ... }              -- статические данные квестов
local registered = false

-- 1) generic helpers
local function vget(key, def) ; return load_var(db.actor, key, def) ; end
local function vset(key, val) ; save_var(db.actor, key, val) ; end
local function get_smart(name) ; return SIMBOARD.smarts_by_names[name] ; end

-- 2) spawn / ownership helpers
local function mark_task_squad(squad) ... end
local function spawn_squad(base_smart, section, target_smart) ... end

-- 3) per-quest functors (local!)
local function <task_id>_target(task_id, field, p, tsk) ... end
local function <task_id>_descr (task_id, field, p, tsk) ... end
local function <task_id>_status(tsk, task_id) ... end

-- 4) effects (actor, npc, p)
local function <task_id>_start  (actor, npc, p) ... end
local function <task_id>_reward (actor, npc, p) ... end
local function <task_id>_cleanup(actor, npc, p) ... end

-- 5) dialog conditions/actions (actor, npc, p)
local function <dialog_slug>_can_take(actor, npc, p) ... end
local function <dialog_slug>_accept  (actor, npc, p) ... end
local function <dialog_slug>_turn_in (actor, npc, p) ... end

-- 6) registration на нулевом (модульном) уровне
local function register()
    if registered then return end
    if not (task_functor and task_status_functor and xr_effects and dialogs) then
        return
    end

    task_functor["<task_id>_target"]                 = <task_id>_target
    task_functor["<task_id>_descr"]                  = <task_id>_descr
    task_status_functor["<task_id>_status"]          = <task_id>_status

    xr_effects["<task_id>_start"]                    = <task_id>_start
    xr_effects["<task_id>_reward"]                   = <task_id>_reward
    xr_effects["<task_id>_cleanup"]                  = <task_id>_cleanup

    dialogs["<dialog_slug>_can_take"]                = <dialog_slug>_can_take
    dialogs["<dialog_slug>_accept"]                  = <dialog_slug>_accept
    dialogs["<dialog_slug>_turn_in"]                 = <dialog_slug>_turn_in

    registered = true
    printf("[<mod>_quests] task functors registered")
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

**Правила регистрации (критично для «видения» парсерами):**
- Функции объявляются `local`, а в глобальные таблицы попадают **только присваиванием по плоскому ключу**.
- Ключ = имя, которое написано в XML/LTX один-в-один (`dialogs.<fn>` и `xr_effects.<fn>` без префикса модуля;
  `task_functor.<fn>` без префикса модуля).
- Никакого `return { ... }` из модуля и никаких вызовов через `<mod>_quests.fn(...)` из конфигов.
- `register()` вызывается трижды: на `on_game_start()` (новая игра), на `on_game_load` и на
  `actor_on_first_update` (Lua-состояние пересоздаётся при загрузке сейва).
- Повторная регистрация защищена флагом `registered`.
- Все сохранения — только через `save_var/load_var` под ключами, **не равными** `task_id`
  (`<mod>_q1_v_spawn`, `<mod>_q1_enemy`, ...). `task_manager` очищает ключ задачи при завершении.
- `tsk.stage` меняется **только** в `*_status`; `stage` стартует с `0`, индекс массива этапов — `stage + 1` (эквивалент `stage <= 0`).
- Троттлинг статуса: `local now = time_global(); if tsk.__<mod>_next and now < tsk.__<mod>_next then return nil end; tsk.__<mod>_next = now + 3000`.
- Завершение задачи — `task_manager.get_task_manager():set_task_completed(<task_id>)` из `dialogs.*_turn_in`.
- Lua 5.1: без `goto`, без `//`, `&`, `|`, `~`, `unpack` вместо `table.unpack`, рискованные вызовы — в `pcall`.
- Кодировка `.script` — Windows-1251 без BOM (русские комментарии допустимы, но безопаснее — латиница).

---

## 3. АРХИТЕКТУРА НОВЫХ ДАТА-МОДЕЛЕЙ (`src/core/models.py` с нуля)

Общие требования к Pydantic-моделям (v2):
- `model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True, populate_by_name=True)`
  — свойства из SQLite, которых нет в схеме, проходят без `ValidationError`;
- **все идентификаторы — `str`** (server id и story id в игре бывают и числами, и строками;
  `int`-приведение ломает `alife_object(id)` и story-объекты);
- обязательные для сборки поля имеют дефолты (`Optional[...] = None`, `list = Field(default_factory=list)`),
  чтобы неполная строка БД не роняла конвейер;
- `field_validator(mode="before")` нормализует `None`/`""`/`0` в `None` для id-полей;
- никаких runtime-идентификаторов в модели: `alife`-id отрядов появляются только в pstor во время игры.

### 3.1. `Quest` — поля сталкерских метаданных (обязательный минимум)

| Поле | Тип | Обяз. | Источник / смысл |
|---|---|---|---|
| `task_id` | `str` | да | id секции LTX, уникален (например `mymod_av_quest`) |
| `mod_prefix` | `str` | да | префикс всех глобалов и pstor-ключей |
| `title_id` | `str` | да | id строки `<mod>_..._title` |
| `descr_id` | `str` | да | id строки стартового описания |
| `descr_by_stage` | `dict[int, str]` | нет | описания по этапам (`0/1/2`), как `mymod_av_q_descr_elevator` |
| `icon` | `str` | нет | иконка PDA (`ui_inGame2_...`) |
| `prior` | `int` | нет | приоритет (эталон `60`) |
| `storyline` | `bool` | нет | `false` для побочных |
| `stage_complete` | `int` | нет | финальный этап (эталон `3`) |
| `descr_functor` / `target_functor` / `status_functor` | `str` | да | плоские имена, автоген `f"{task_id}_descr"` и т.д. |
| `giver_profile_id` | `str` | да | **ID профиля NPC** = `specific_character id` (например `esc_3_16_military_trader`) |
| `giver_story_id` | `str` | да | story id персонажа (для `get_story_object_id`, fallback в target) |
| `giver_level` | `str` | да | **имя локации персонажа**: `escape`, `zaton`, `jupiter`, ... |
| `giver_character_desc` | `str` | да | имя файла без расширения: `character_desc_escape` |
| `dialog_ids` | `dict[str, str]` | да | роли → id диалогов: `take`, `take_assault`, `take_solo`, `turnin` |
| `stages` | `list[QuestStage]` | да | этапы: `index`, `target_smart`, `target_type`, `descr_id`, `completion_rule` |
| `spawns` | `list[SquadSpawn]` | нет | отряды: `squad_section`, `is_ally`, `base_smart`, `target_smart`, `faction`, `npc_section`, `count` |
| `enemy_squad_section` | `str` | нет | section враждебного отряда (в эталоне `der_stalker_esc_smart_terrain_2_12`) |
| `ally_squad_section` | `str` | нет | section союзного отряда (`army_sim_squad_advanced`) |
| `target_smarts` | `list[str]` | да | **имена смарт-террейнов** по этапам (`esc_smart_terrain_2_12`, ...) |
| `reward_money` | `int` | нет | сумма для `db.actor:give_money` |
| `reward_item` | `str` | нет | section предмета для `alife_create_item` |
| `reward_item_count` | `int` | нет | количество (по умолчанию 1) |
| `info_taken` / `info_done` | `str` | да | инфопоршни выдачи/завершения |
| `info_required` / `info_forbidden` | `list[str]` | нет | условия доступности диалога |
| `faction_required` | `str` | нет | фракция игрока (эталон — `army`) |
| `warfare_required` | `bool` | нет | проверка `IsWarfare()` |
| `fail_on_giver_death` | `bool` | нет | генерирует `condlist_0 = {!task_giver_alive(...)} fail` |
| `return_distance` | `float` | нет | метры для этапа «подойти к квестодателю» (эталон `40`) |
| `status_throttle_ms` | `int` | нет | эталон `3000` |
| `texts_eng` / `texts_rus` | `dict[str, str]` | да | id строки → текст для `text/eng|rus/st_<mod>.xml` |
| `pstor_prefix` | `str` | да | префикс runtime-ключей (не равен `task_id`) |
| `source_row_id` | `str` | нет | id записи в SQLite (сквозная связь) |

Вложенные модели: `QuestStage {index:int, target_smart:str|None, target_type: Literal["smart","npc","item"], descr_id:str|None, completion_rule:str|None}`, `SquadSpawn {squad_section:str, is_ally:bool, base_smart:str, target_smart:str, faction:str|None, npc_section:str|None, count:int=1}`.

### 3.2. `Dialog` — поля привязки к NPC и графу

| Поле | Тип | Обяз. | Источник / смысл |
|---|---|---|---|
| `dialog_id` | `str` | да | id `<dialog id="...">` = значение `<actor_dialog>` |
| `role` | `Literal["take","take_assault","take_solo","turnin","branch"]` | да | роль в сценарии |
| `task_id` | `str` | да | **связь с квестом** (сквозной ключ) |
| `owner_profile_id` | `str` | да | **ID профиля NPC** (`specific_character id`) |
| `owner_character_desc` | `str` | да | файл для патча (`character_desc_escape`) |
| `owner_level` | `str` | да | локация персонажа (`escape`) |
| `preconditions` | `list[str]` | нет | имена функций в таблице `dialogs` (без префикса) |
| `has_info` / `dont_has_info` | `list[str]` | нет | инфопоршни уровня `<dialog>` |
| `phrases` | `list[Phrase]` | да | граф реплик |
| `condition_fns` | `dict[str,str]` | нет | роли → имена: `can_take`, `can_turn_in` |
| `action_fns` | `dict[str,str]` | нет | роли → имена: `accept`, `accept_assault`, `accept_solo`, `turn_in` |
| `entry_phrase_id` | `int` | нет | стартовая фраза (по умолчанию `0`) |
| `texts_eng` / `texts_rus` | `dict[str,str]` | да | строки фраз (`<mod>_..._dlg_..._N`) |
| `source_row_id` | `str` | нет | id записи в SQLite |

`Phrase {id:int, text_id:str|None, script_text:str|None, next:list[int], actions:list[str], preconditions:list[str], has_info:list[str], dont_has_info:list[str], give_info:list[str]}`.

### 3.3. Сквозные связи и чтение SQLite без `ValidationError`

1. `Quest.dialog_ids[*] → Dialog.dialog_id` и `Dialog.task_id → Quest.task_id` — двусторонняя связь;
   валидатор уровня `ProjectModel` обязан проверить, что **каждый** `dialog_id` из квеста существует,
   и что **каждый** `Dialog.owner_profile_id` имеет соответствующий `character_desc_<level>` в `specific_characters_files`.
2. `Dialog.owner_profile_id` обязан найтись в `<specific_character id="...">` целевого
   `character_desc_*.xml`; иначе — `BuildError`, а не молчаливый пропуск (иначе диалог «не появится» в игре).
3. Чтение SQLite: строки могут содержать `NULL`, `TEXT`, `INTEGER` вперемешку —
   `coerce_numbers_to_str=True` + `extra="allow"` + дефолты покрывают это; `0` и `""` в id-полях
   нормализуются в `None` валидатором `mode="before"`.
4. Любое необязательное метаданное (иконки, приоритеты, story id, имена смартов) — `Optional`,
   чтобы «сырая» база без части колонок проходила валидацию и дозаполнялась дефолтами генератора.
5. `extra="allow"` сохраняет неизвестные колонки в `model_extra` — их можно пропускать в шаблоны
   без потери данных и без падения конвейера.

---

## 4. КОНВЕЙЕР СБОРКИ (порядок, обязательный к реализации)

```
[1] LOAD        SQLite / JSON  →  list[Quest], list[Dialog]  (Pydantic, extra="allow")
[2] VALIDATE    сквозные связи: task↔dialog↔profile↔character_desc↔text_id↔lua_fn
[3] PLAN        расчёт дерева файлов и списка патчей (system.ltx, character_desc_*.xml)
[4] RENDER      XML / LTX / Lua / text-ENG / text-RUS  из шаблонов раздела 2
[5] PATCH       копия ванильного конфига → текстовые вставки (раздел 1)
[6] VERIFY      статические ассерты (ниже)
[7] EMIT        build_root/gamedata/...  (cp1251, BOM только там, где был)
```

**Обязательные `VERIFY`-ассерты (без них сборка не считается успешной):**
1. `[dialogs].files` содержит `dialogs_<mod>` ровно один раз.
2. `[profiles].specific_characters_files` содержит каждый целевой `character_desc_*` ровно один раз.
3. Каждый `<dialog id>` из `dialogs_<mod>.xml` привязан хотя бы одним `<actor_dialog>` в `character_desc_*.xml`.
4. Каждый `<actor_dialog>ID</actor_dialog>` имеет одноимённый `<dialog id="ID">`.
5. Каждый `<precondition>`/`<action>` вида `dialogs.X` имеет ключ `dialogs["X"]` в регистрации скрипта.
6. Каждый `*_functor` из `tm_<mod>.ltx` имеет ключ в `task_functor` / `task_status_functor`.
7. Каждый `on_init/on_complete/on_fail/on_cancel` имеет форму `%=<fn>()%` (скобки вызова присутствуют).
8. Каждый `<text>ID</text>` и каждый `descr`/`title` присутствует и в `st_<mod>.xml` (eng), и в `st_<mod>.xml` (rus).
9. XML well-formed; в XML нет `&`/`<` вне сущностей; LTX-секции задач уникальны.
10. Ни в одном сгенерированном файле нет `dltx`, `.ext`, `start_dialogs`.
11. Все файлы — cp1251; BOM отсутствует (кроме унаследованного от патчимого ванильного файла).
12. Lua 5.1: нет `goto`, `//`, `&`, `|`, `~`, `table.unpack`.

**Критерий приёмки:** собранный `gamedata` повторяет структуру и синтаксис слепка «M»
файл-в-файл (system.ltx → character_desc → dialogs → squad_descr → tm → text eng/rus → scripts),
и после копирования в игровую папку задача выдаётся из диалога, этапы переключаются, награда
выдаётся, сохранение/загрузка не ломает стадию, в логе нет `!ERROR` и стектрейсов.

---

## 5. Что фреймворку запрещено генерировать (сводка анти-паттернов)

- `dlg_*.ltx` с диалогами (диалоги только в `dialogs_<mod>.xml`);
- `<dialog>` без `<phrase_list>`;
- `<next>` без парного закрывающего тега, `<next>` в виде атрибута;
- `<precondition>mymod_quests.fn</precondition>` и `<action>xr_effects.fn</action>` без скобок-вызова там, где движок ждёт имя таблицы;
- `%=fn%` / `%= fn() %` / `%=fn()%` с пробелами внутри (эталон: `%=fn()%` — без пробелов);
- `task_functor["mymod.fn"]`, вложенные таблицы, возврат таблицы из модуля;
- `reward_money`/`reward_item` в секции задачи;
- сохранение состояния под `task_id`;
- пересборка `character_desc_*.xml` через DOM-сериализатор (потеря `#include` и чужих NPC);
- запись в `_unpacked\*` и любые файлы вне `build_root`.
