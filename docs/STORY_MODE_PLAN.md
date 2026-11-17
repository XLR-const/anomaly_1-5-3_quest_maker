# Story-режим Anomaly 1.5.3: архитектурный план Фазы 2

> Статус: **Реализовано (Итерации 1–3 завершены)**.
>
> База анализа: распакованный ванильный Anomaly 1.5.3 в `_unpacked/`,
> текущий компилятор в `src/`, контракт `docs/API_v2.md`, правила
> `docs/RULE.md`. Эталон — `examples/build_story_relay.py`,
> регрессия — `tests/test_story_mode.py`.

---

## 0. Резюме

1. В Anomaly нет отдельного «Story-режима» как переключателя. Есть
   freeplay-симуляция, в которой сюжетные квесты живут на тех же
   `sim_squad_scripted`, что и обычные отряды, но завершаются не захватом
   смарта, а **инфопоршнями из `on_death` и `condlist_N`**.
2. Ванильный сюжетный квест — это в первую очередь **данные**: секция
   `tm_*.ltx`, секция `squad_descr_*.ltx`, диалоги и строки. Lua нужен
   только для нестандартных проверок. Наш компилятор сейчас всегда
   генерирует Lua-рантайм и всегда завершает этап через Warfare-логику.
3. В Фазе 2 **не генерируем уникальные профили** `character_desc_*.xml`.
   Работаем с готовыми ванильными квестодателями: патчим только
   `<actor_dialog>` в существующий `<specific_character>`.
4. Story-отряды описываются через `CustomSquad`
   (`squad_descr_<slug>.ltx`) и спавнятся как ванильные
   `create_squad(section:smart)`, без `sim_squad_warfare.set_target`.
5. Ключевая формула Story-квеста:
   `CustomSquad.on_death = %+info%` → `condlist_N = {+info} complete` →
   `on_complete` выдаёт следующий квест цепочки. Никаких
   `owning_faction`/`defense_count`.
6. Фаза 2 разбита на 3 компактные итерации: модели+генераторы →
   Story-спавн и жизненный цикл → эталонная цепочка и регрессия.
7. Обратная совместимость Warfare обеспечивается тем, что все новые поля
   опциональны, а новый Lua/шаблонный код **вставляется только при
   наличии Story-функций**. Для старых проектов вывод остаётся
   байт-идентичным.

---

## 1. Границы и определения

| Термин | Значение в этом документе |
|---|---|
| Story / сюжетный квест | Квест с `storyline = true`, который выдаётся NPC и продвигается инфопоршнями, предметами, диалогами или смертью конкретного отряда. Не зависит от Warfare. |
| Warfare-квест | Квест, этап которого требует захватить смарт: уничтожить вражеский отряд и дождаться смены `owning_faction`. |
| Квестодатель | Ванильный `specific_character` (например `zat_a2_stalker_barmen`) и его story id. |
| Story-отряд | Секция `[id]:online_offline_group` из `squad_descr_*.ltx`, созданная через `SIMBOARD:create_squad`. |
| Scripted-отряд | Отряд, которому `target_smart` задаёт пункт назначения; движок ведёт его через `sim_squad_scripted:specific_update`. |
| Гарнизон | Отряд, дошедший до смарта и назначенный ему через `assign_squad_to_smart`. |
| Инфопоршень | Строковый флаг в `db.actor`, основной «автобус» завершения Story-квестов. |
| Цепочка | Несколько отдельных задач `[q1]`, `[q2]`, где `on_complete` первой вызывает `give_task(q2)`. |

Важно: `storyline = true` — это **не режим игры**, а признак сюжетной
задачи для PDA/менеджера задач. Вне Warfare все отряды всё равно
обслуживаются `sim_squad_scripted`.

---

## 2. Как устроены ванильные Story-квесты

### 2.1. Минимальная анатомия

Эталон — `_unpacked/configs/misc/task/tm_lostzone_ms.ltx:13-25`:

```ini
[lttz_ms_start_dolg]
icon = ui_iconsTotal_bar_crazy_veterans_quest
prior = 195
storyline = true

title = lttz_ms_start_title
target = {+greh_envoy_dead} bar_dolg_leader, {+mortal_sin_envoy} bar_dolg_leader, bar_greh_envoy
descr = {+greh_envoy_dead} lttz_ms_start_dolg_descr_kill, {+mortal_sin_envoy} lttz_ms_start_dolg_descr_talk, lttz_ms_start_dolg_descr

on_init = %=reward_item(shovel_mili) =create_squad(bar_greh_envoy_squad:bar_visitors)%
on_complete = %=reward_money(5000) =complete_task_inc_goodwill(50:dolg) =give_task(lttz_ms_red_forester)%
condlist_0 = {+mortal_sin_red_forest} complete
condlist_1 = {-mortal_sin_envoy_complete +greh_envoy_dead} fail
```

Здесь нет ни одной строки Lua. Всё, что нужно движку:

* `on_init` создаёт отряд на смарте и выдаёт предмет;
* `target` и `descr` — condlist-строки, которые выбирают story id цели и
  строку описания по инфопоршням;
* `condlist_N` завершают/проваливают задачу;
* `on_complete` выдаёт следующий квест цепочки.

Смерть отряда приходит из его секции
(`_unpacked/configs/misc/squad_descr/squad_descr_lostzone_ms.ltx:3-8`):

```ini
[bar_greh_envoy_squad]:online_offline_group
faction = greh_npc
npc = greh_envoy
target_smart = bar_visitors
story_id = bar_greh_envoy
on_death = %+greh_envoy_dead%
```

`on_death` срабатывает в `sim_squad_scripted:remove_npc`, когда
`npc_count() == 0` (`_unpacked/scripts/sim_squad_scripted.script:445-477`).
Это работает и в офлайне: смерть члена отряда обрабатывается через
`on_npc_death` и последующий `remove_npc`.

### 2.2. Разбор `tm_lostzone_ll.ltx`

`_unpacked/configs/misc/task/tm_lostzone_ll.ltx:13-26` показывает
condlist-цели и цепочки:

```ini
[lttz_ll_find_doctor]
storyline = true
target = mar_smart_terrain_doc_doctor
descr = lttz_ll_find_doctor_task_descr
on_init = %=remove_squad(monolith_eidolon) =create_squad(stalker_gatekeeper_squad:mil_smart_terrain_4_8)%
on_complete = %=complete_task_inc_goodwill(50:stalker) =give_task(lttz_ll_visit_agro_ug) +lttz_ll_visit_agro_ug_task%
condlist_0 = {+living_legend_doctor} complete
condlist_1 = {=actor_has_item(cit_doctors_pda)} complete
```

Ключевые наблюдения:

1. `on_init` умеет **удалять** прошлый сюжетный отряд
   (`remove_squad(monolith_eidolon)`) — это штатный способ не оставлять
   «сирот» при переходах цепочки.
2. Завершение может быть по предмету
   (`{=actor_has_item(...)} complete`), а не только по инфопоршню.
3. Цель — story id смарта (`mar_smart_terrain_doc_doctor`), а не алиас
   компилятора.
4. `on_complete` одной задачи выдаёт следующую — цепочка строится
   данными, без графа в Lua.

Более сложный случай — `lttz_ll_call_north`
(`tm_lostzone_ll.ltx:71-84`): там `target` и `descr` содержат по несколько
condlist-вариантов, а `status_functor = special_steps_for_lostzone_tasks`
подмешивает таймеры и промежуточные шаги. Это уже «продвинутый» Story,
который в Фазе 2 не обязателен.

### 2.3. Как Story-отряд ведёт себя вне Warfare

1. `SIMBOARD:create_squad(spawn_smart, section)`
   (`_unpacked/scripts/sim_board.script:131-154`) создаёт отряд и
   назначает его **точке спавна**.
2. `sim_squad_scripted` читает `target_smart` как `action_condlist`
   (`sim_squad_scripted.script:55`) и через `get_script_target` получает
   story id цели (`:102`).
3. `specific_update` ведёт отряд к цели, ждёт `idle_time`
   (`:276-319`), затем вызывает `smart:on_reach_target`, и отряд
   становится гарнизоном.
4. `on_death` из секции отряда превращается в `death_condlist`
   (`:56`) и исполняется при обнулении состава (`:445-477`).

Это принципиально другая машина, чем Warfare:

* `sim_squad_warfare.squad_on_update` **сразу выходит**, если
  `IsWarfare() == false` (`_unpacked/scripts/sim_squad_warfare.script:52-57`);
* в Warfare он ставит `squad.__lock = true` и
  `squad.scripted_target = ""` (`:122-134`), перехватывая отряд у
  `sim_squad_scripted`;
* `set_target` пишет цель в `warfare.registered_squads` (`:877-914`).

### 2.4. Story vs Warfare: сравнительная таблица

| Аспект | Ванильный Story | Текущий фреймворк (Warfare) | Следствие для Фазы 2 |
|---|---|---|---|
| Спавн отряда | `create_squad(section:smart)`; цель задаёт `target_smart` секции | `SpawnSquad` → `spawn_task_squad` → `sim_squad_warfare.set_target` (`lua_gen.py:369-399`) | Нужен режим `story`, который не вызывает `set_target` |
| Пункт назначения | `target_smart` в `squad_descr_*.ltx` | `spawn_task_squad(..., target_name)` | Для Story цель берётся из секции отряда |
| Проверка зачистки | `condlist` по инфопоршню из `on_death` | `stage_cleared` по `owning_faction`/`defense_count` (`lua_gen.py:451-465`) | В Story эти поля бессмысленны |
| Завершение этапа | Инфопоршень/предмет/диалог | `target_squad_dead`, `stage_cleared`, `transfer_conditions` | Оставить `transfer_conditions`, добавить quest-level `condlist` |
| Цель маркера | `target`-condlist, значения — story id | `Stage.target_alias` + Lua-резолвер | Нужны варианты цели по условиям |
| Описание | `descr`-condlist, варианты строк | Одна строка на этап | Нужны варианты описания на этап |
| Провал | Явные `condlist_N fail` | Автоматический `condlist_0 = {!task_giver_alive(...)} fail` | Сделать авто-провал отключаемым |
| Смерть отряда | `on_death = %+info%` | Не поддерживается в `CustomSquad` | Добавить `death_infos` |
| Секция отряда | `relationship`, `idle_time`, `npc_random`, `spawn_point`, `on_death` | Только `faction/npc/target_smart/story_id` (`ltx_gen.py:160-171`) | Расширить эмиссию |
| Гейт режима | Нет | `world` при наличии `warfare_capture`; `requires_warfare` | Story не должен попадать в гейт |
| Lua | Часто не нужен | Всегда генерируется | Story-хелперы только при необходимости |

### 2.5. Что это значит для компилятора

1. Story-квест — это **не** «Warfare без захвата». Это отдельный способ
   завершения: информационный, а не территориальный.
2. Нельзя переиспользовать `spawn_task_squad`: он ставит `stay_time`,
   вызывает `set_target` и включает `force_online`. В Story это ломает
   `specific_update` и превращает отряд в «приколоченный» к смарту.
3. `stage_cleared` нельзя вызывать для Story-этапа: он вернёт `false`
   или, что хуже, завершит этап по чужому `owning_faction`.
4. `CustomSquad` — правильная точка расширения: движок сам подхватывает
   `squad_descr_*.ltx`, `system.ltx` патчить не нужно.
5. Ванильная цепочка задач — это **несколько `Quest`**, связанных
   `GiveTask` в `on_complete_actions`. Граф цепочки в модели не нужен.

---

## 3. Аудит текущего фреймворка

### 3.1. Что уже совпадает с ванильным Story

| Возможность | Где | Комментарий |
|---|---|---|
| Ванильный квестодатель | `Quest.npc_id` + `npc_location` | `builder._collect_dialog_bindings` (`builder.py:791-896`) требует локацию и патчит `character_desc_<level>.xml` |
| Без генерации профилей | `builder.patch_character_desc` (`builder.py:960-1027`) | Вставляет только `<actor_dialog>` в существующий `<specific_character>`, сохраняя `#include` и BOM |
| Кастомный отряд | `ModProject.squads` + `generate_squads_ltx` (`ltx_gen.py:106-176`) | Файл `squad_descr_<slug>.ltx` создаётся автоматически |
| Story id отряда | `CustomSquad.story_id` | Позволяет `get_story_squad`, `remove_squad`, `target` |
| Завершение по отряду | `Stage.target_squad_id` (`lua_gen.py:266-279`) | Работает и для story id |
| Завершение по инфопоршню | `transfer_conditions` | Уже генерирует `complete`/`fail` в `_status` |
| Цепочки | `GiveTask` в `on_complete_actions` | Уже исполняется в `_reward` |
| Спавн в `on_init` | `on_init_actions` | Уже исполняется в `_start` |
| Строки этапов | `xml_gen.py:147-157` | Генерирует `_stage_<id>_descr` |
| Награды | `_reward` (`lua_gen.py:1384-1409`) | Деньги, предмет, инфопоршень, очистка |

### 3.2. Пробелы

Обозначения: **G** — gap, **I** — итерация, в которой закрывается.

#### G1. Нет вариантов `target`/`descr` по условиям

**Проблема.** `Stage` умеет только одну цель (`target_alias`) и одну
строку описания (`descr_ru/descr_en`). Ванильные квесты выбирают цель и
текст по инфопоршням и предметам:
`tm_lostzone_ll.ltx:77-79`, `tm_lostzone_ms.ltx:19-20`.

**Решение.** Добавить в `Stage`:

```python
class TargetVariant(BaseModel):
    when: list[Condition] = Field(min_length=1)
    value: str = Field(min_length=1)

class DescrVariant(BaseModel):
    when: list[Condition] = Field(min_length=1)
    text_ru: str = ""
    text_en: str = ""

target_variants: list[TargetVariant] = []
descr_variants: list[DescrVariant] = []
```

Семантика: варианты проверяются по порядку, побеждает первый, у которого
все условия истинны; если ни один не подошёл — базовые `target_alias` и
`descr_*`.

**I:** 1 (модели/XML/Lua-функции).

#### G2. `CustomSquad` не умеет `on_death`

**Проблема.** `ltx_gen.generate_squads_ltx` эмитит только
`faction/npc/target_smart/story_id` (`ltx_gen.py:160-171`), поэтому
Story-отряд не может выдать инфопоршень о своей смерти. Без этого
приходится полагаться на `target_squad_dead`, который не сработает, если
отряд погиб до входа в этап.

**Решение.**

```python
death_infos: list[str] = []
```

Эмиссия:

```ini
on_death = %+info_a +info_b%
```

Несколько действий в `%...%` — штатный синтаксис Anomaly (ср.
`on_init = %=reward_item(...) =create_squad(...)%`).

**I:** 1.

#### G3. Секция отряда бедна полями

**Проблема.** Нельзя задать `relationship`, `idle_time`, `spawn_point`,
`npc_random`, `npc_in_squad`. Ванильные секции используют их массово
(`squad_descr_agroprom.ltx:90-93`, `squad_descr_zaton.ltx:75-83`).

**Решение.**

```python
relationship: Literal["neutral", "friend", "enemy"] | None = None
idle_time: float | None = Field(default=None, ge=0)
spawn_point: str | None = None
npc_random: list[str] = []
npc_in_squad: list[int] = []   # 1 или 2 значения: min[, max]
```

Правила:

* `npc` и `npc_random` могут быть заданы вместе, но хотя бы одно — нет;
* `npc_in_squad` — 1–2 неотрицательных числа, `min <= max`;
* порядок эмиссии фиксирован: `faction`, `relationship`, `npc`,
  `npc_random`, `npc_in_squad`, `target_smart`, `spawn_point`,
  `story_id`, `on_death`.

**I:** 1.

#### G4. `SpawnSquad` — Warfare-only

**Проблема.** `spawn_task_squad` (`lua_gen.py:369-399`) всегда вызывает
`sim_squad_warfare.set_target`, ставит `stay_time` и `force_online`.
В freeplay это либо ошибка, либо ломает `specific_update`.

**Решение.** Добавить режим:

```python
class SpawnSquad(BaseAction):
    type: Literal["spawn_squad"] = "spawn_squad"
    squad_alias: str
    smart_alias: str
    mode: Literal["warfare", "story"] = "warfare"
```

Для `story` генерируется отдельный вид действия
`spawn_story_squad`, который:

1. вызывает `SIMBOARD:create_squad(spawn_smart, section)`;
2. **не** вызывает `set_target`;
3. **не** трогает `stay_time`;
4. **не** включает `force_online`;
5. помечает отряд в `sim_offline_combat.task_squads`;
6. регистрирует его в списке Story-отрядов квеста для очистки.

Пункт назначения берётся из `target_smart` секции отряда.

**I:** 2.

#### G5. Спавн этапов существует только внутри `warfare_capture`

**Проблема.** `spawn_stage_for`/`freeze_stage_for` работают только при
`data.capture` (`lua_gen.py:414-440`). Story-этап не может спавнить отряд
в начале этапа, кроме `on_start_actions`.

**Решение.** Не расширять `warfare_capture`. Использовать
`Stage.on_start_actions` с `SpawnSquad(mode="story")`; идемпотентность
обеспечивается `stage_key(q, stage, "started")`, который уже
выставляется один раз (`lua_gen.py:1308-1312`). Отдельный
`story_spawn`-блок не нужен.

**I:** 2 (после G4).

#### G6. `world`-гейт блокирует Story с захватом

**Проблема.** `world` вычисляется как «есть хотя бы один
`warfare_capture`» (`lua_gen.py:1154-1157`), а `_start`/`_status`
возвращаются без работы вне Warfare (`:1295-1297`, `:1359-1361`).
Любой Story-этап с захватом станет недоступен в freeplay.

**Решение.**

* Story-квесты не используют `warfare_capture`;
* `requires_warfare` для Story остаётся `False`;
* смешанные квесты (Story + захват) в Фазе 2 **не поддерживаются**:
  разделять на два квеста;
* при попытке смешать — ошибка валидатора с понятным текстом.

**I:** 1 (валидатор) + 2 (тест).

#### G7. Перегрузка `npc_id`

**Проблема.** В `Quest` поле `npc_id` — это story id для
`task_giver_alive`/`target`, а в `Dialog` — это `<specific_character id>`
для патча профиля. Имена совпадают, домены разные.

**Решение.** Не переименовывать в Фазе 2 (сломает API), но:

* задокументировать домены в docstring;
* в `builder._collect_dialog_bindings` профиль уже обязан существовать:
  `patch_character_desc` падает с `BuildError`, если
  `<specific_character id="...">` не найден (`builder.py:1003-1007`);
* в примерах всегда задавать `npc_id` и `npc_location` явно;
* в `Quest` добавить необязательное `giver_profile_id` на будущее, если
  story id и profile id разойдутся (Phase 3, без изменения вывода).

**I:** 1 (документация/валидатор).

#### G8. Автопровал по смерти квестодателя нельзя отключить

**Проблема.** `ltx_gen._build_quest_section` всегда добавляет
`condlist_0 = {!task_giver_alive(<quest>)} fail`, если задан
`giver_npc_id` (`ltx_gen.py:227-234`). Для цепочек, где квестодатель
может погибнуть по сюжету, это неверно.

**Решение.**

```python
fail_on_giver_death: bool = True
extra_condlists: list[QuestCondlist] = []
```

```python
class QuestCondlist(BaseModel):
    when: list[Condition] = Field(min_length=1)
    result: Literal["complete", "fail"]
```

Нумерация:

* `condlist_0` — авто-провал, если `fail_on_giver_death`;
* далее — `extra_condlists` в порядке объявления.

Сериализация условий в condlist:

| Модель | Синтаксис |
|---|---|
| `HasInfo` | `+info` |
| `DontHasInfo` | `-info` |
| `HasItem` (count=1) | `=actor_has_item(section)` |
| `HasItem` (count>1) | `=actor_has_item_amount(section:count)` |
| `HasMoney` | **не поддерживается** в Фазе 2 (`BuildError`) |
| `SmartOwner` | **не поддерживается** в Фазе 2 (`BuildError`) |

**I:** 1.

#### G9. Нет таймеров и `status_functor_params`

**Проблема.** Ванильный `special_steps_for_lostzone_tasks`
(`task_status_functor.script`) управляет стадиями по предметам,
инфопоршням и таймерам; параметры передаются через
`status_functor_params`. Фреймворк всегда генерирует собственный
`status_functor` и не умеет подключать ванильные.

**Решение Фазы 2.** Не поддерживать. Таймерные этапы выражать через
отдельные задачи цепочки и инфопоршни, которые выставляет внешний
скрипт. Поле `status_functor` в модель не добавляется; если оно придёт
из SQLite/JSON как extra-поле, валидатор выдаёт предупреждение
«не поддерживается, будет проигнорировано».

**I:** Phase 3.

#### G10. Динамические задачи и `reward_item`

**Проблема.** `tasks_assault/bounty/fetch` — это генераторы динамических
задач, а не сюжет. У них своя модель (`job_descr`, `fetch_func`,
`target_func`). Кроме того, в ванильном `task_objects.script:82`
`reward_item` ошибочно читает ключ `reward_money`; полагаться на него
нельзя.

**Решение Фаз 2.** Не смешивать динамические задачи со Story. Награды
выдавать через `_reward` (Lua), а не через ванильный `reward_item`.
Задокументировать в `RULE`/плане.

**I:** Phase 3.

#### G11. Нет удаления Story-отряда при провале/отмене

**Проблема.** `_cleanup` снимает метки и инфопоршни
(`lua_gen.py:1411-1428`), но не удаляет заспавненный отряд. Если игрок
отменил квест, отряд останется в мире и `on_death` может выдать
инфопоршень следующей попытки.

**Решение.**

```python
class RemoveSquad(BaseAction):
    type: Literal["remove_squad"] = "remove_squad"
    squad_alias: str
```

Lua: `get_story_squad(alias)` → `SIMBOARD:remove_squad(squad)`.
Если отряд уже мёртв, `get_story_squad` вернёт `nil` — действие должно
быть no-op, а не падать. Добавить в `Action` union и в `run_actions`.

Ванильный аналог: `on_init = %=remove_squad(monolith_eidolon) ...%`
(`tm_lostzone_ll.ltx:22`).

**I:** 2.

#### G12. Валидатор не проверяет ссылки на отряды

**Проблема.** `core/validator.py` не содержит проверок `squads` вообще;
`ModProject` проверяет только совпадение ключей (`models.py:953-958`).
`SpawnSquad.squad_alias` может ссылаться в никуда, `target_squad_id` —
на несуществующую секцию.

**Решение.** Добавить проверки:

* `SpawnSquad(mode="story").squad_alias` ∈ `project.squads` или
  существует в ванильном `squad_descr` (по БД, если доступна);
* `RemoveSquad.squad_alias` — то же;
* `Stage.target_squad_id` — предупреждение, если не найдено;
* `CustomSquad.story_id` уникален в проекте;
* `CustomSquad.death_infos` — валидные идентификаторы.

**I:** 1–2.

---

## 4. Целевая архитектура Фазы 2

### 4.1. Принципы

1. **Данные важнее кода.** Story-квест должен по возможности описываться
   LTX + XML + секцией отряда, как ванильный.
2. **Инфопоршень — основной контракт.** Смерть отряда, диалог, предмет и
   внешний скрипт общаются с квестом через `info`.
3. **Никаких уникальных профилей.** Только ванильные
   `specific_character` + `<actor_dialog>`.
4. **Warfare не трогаем.** Все изменения аддитивны; старый вывод
   байт-идентичен.
5. **Один квест — один `Quest`.** Цепочка — это несколько `Quest`,
   связанных `GiveTask`.

### 4.2. Поток данных

```text
ModProject
  ├─ Quest (story)
  │    ├─ on_init_actions: GiveInfo, SpawnSquad(mode="story")
  │    ├─ stages[].target_alias / target_variants
  │    ├─ stages[].descr_* / descr_variants
  │    ├─ transfer_conditions  → status_functor (Lua)
  │    ├─ extra_condlists      → condlist_N (LTX)
  │    └─ on_complete_actions: GiveTask(next), GiveInfo
  ├─ Dialog (ванильный NPC)
  │    └─ GiveInfo / GiveTask / CompleteTask
  └─ CustomSquad
       ├─ target_smart  → specific_update
       ├─ story_id      → get_story_squad / target
       └─ on_death      → инфопоршень
```

### 4.3. Генерация LTX

Секция задачи остаётся прежней, добавляются только condlist-строки:

```ini
[mymod_relay_01_silence]
icon = ui_inGame2_Put_v_pripyat
prior = 60
storyline = true
title = mymod_relay_01_silence_title
descr = mymod_relay_01_silence_descr
descr_functor = mymod_relay_01_silence_descr
target_functor = mymod_relay_01_silence_target
status_functor = mymod_relay_01_silence_status
stage_complete = 1
dont_send_update_news = true

on_init = %=mymod_relay_01_silence_start()%
on_complete = %=mymod_relay_01_silence_reward()%
on_fail = %=mymod_relay_01_silence_cleanup()%
on_cancel = %=mymod_relay_01_silence_cleanup()%

condlist_0 = {!task_giver_alive(mymod_relay_01_silence)} fail
condlist_1 = {+mymod_relay_merc_dead} complete
```

Правила:

* `condlist_0` остаётся авто-провалом при `fail_on_giver_death = True`;
* `extra_condlists` нумеруются с 1;
* при отсутствии `extra_condlists` и `fail_on_giver_death = True` вывод
  не меняется;
* при `fail_on_giver_death = False` и пустых `extra_condlists` блок
  `condlist_*` не эмитится вовсе.

Важно: `condlist_N` завершает **весь квест**, а не этап, и
`task_objects` проверяет его раньше `status_functor`
(`task_objects.script:233-243`). Поэтому:

* для многоэтапного квеста используйте `transfer_conditions`;
* `extra_condlists` — для одноэтапных звеньев цепочки, как в ванильном
  `tm_lostzone_ms.ltx`.

### 4.4. Генерация `squad_descr_<slug>.ltx`

Порядок полей фиксирован, пустые поля не эмитятся:

```ini
[mymod_relay_merc_squad]:online_offline_group
faction = killer
relationship = enemy
npc = sim_default_killer_1, sim_default_killer_2, sim_default_killer_3
target_smart = zat_b52
story_id = mymod_relay_merc_squad
on_death = %+mymod_relay_merc_dead%
```

Для старой модели без новых полей вывод совпадает с текущим
(`ltx_gen.py:160-171`).

### 4.5. Генерация Lua

Добавляются только условные фрагменты:

1. `spawn_story_squad(base_name, section)` — рядом с
   `spawn_task_squad`, но без `set_target`.
2. `register_story_squad(quest_id, squad)` — отдельный список
   `_story_squad_*`, чтобы `freeze_dyn_squads` не трогал Story-отряды.
3. `unmark_quest_squads` — цикл по Story-списку, если фича включена.
4. `run_actions` — ветка `spawn_story_squad` и `remove_squad`.
5. `_target` — блок вариантов, если `target_variants` непуст.
6. `_descr` — блок вариантов, если `descr_variants` непуст.

`_status` не меняется: Story-этапы завершаются либо
`transfer_conditions`, либо quest-level `condlist` (его обрабатывает
`task_manager`). `stage_cleared` для Story не вызывается, потому что
`capture == nil`.

### 4.6. Генерация XML

Для каждого этапа:

* база: `_stage_<id>_title`, `_stage_<id>_descr`, `_stage_<id>_msg`;
* варианты: `_stage_<id>_descr_v1`, `_stage_<id>_descr_v2`, … в порядке
  объявления.

Индексы стабильны и не зависят от локали. При пустом списке вариантов
новые ключи не появляются.

### 4.7. Валидация (минимум Фазы 2)

1. `Quest.requires_warfare == True` и есть Story-этапы без capture —
   предупреждение.
2. `Quest` содержит `warfare_capture` и `SpawnSquad(mode="story")` —
   ошибка (смешанный квест).
3. `CustomSquad` без `npc` и без `npc_random` — ошибка.
4. `CustomSquad.death_infos` содержит пустые строки — ошибка.
5. `Stage.target_variants`/`descr_variants` с пустым `when` — ошибка.
6. `QuestCondlist` с `HasMoney`/`SmartOwner` — `BuildError` при генерации
   LTX.
7. `SpawnSquad(mode="story").squad_alias` не найден — ошибка
   (если доступна БД) или предупреждение.
8. `Dialog.npc_id` без `Dialog.npc_location` — уже ошибка
   (`builder.py:879-885`), не ослаблять.

---

## 5. План итераций Фазы 2

### 5.1. Итерация 1 — модель и генерация артефактов

**Цель:** научиться описывать и генерировать Story-данные, не меняя
рантайм-семантику Warfare.

**Файлы:**

* `src/core/models.py`
* `src/compiler/ltx_gen.py`
* `src/compiler/xml_gen.py`
* `src/core/validator.py`

**Работы:**

1. Добавить `TargetVariant`, `DescrVariant`, `QuestCondlist`,
   `RemoveSquad`; поля `Stage.target_variants`,
   `Stage.descr_variants`, `Quest.extra_condlists`,
   `Quest.fail_on_giver_death`, `SpawnSquad.mode`,
   `CustomSquad.death_infos/relationship/idle_time/spawn_point/npc_random/npc_in_squad`.
2. Обновить `Action`/`Condition` union и docstring-и.
3. `generate_squads_ltx`: новая эмиссия, строгий порядок, пропуск пустых.
4. `_build_quest_section`: нумерация condlist, сериализатор условий,
   `fail_on_giver_death`.
5. `generate_string_tables`: варианты описаний.
6. Валидатор: G12 и проверки смешанного квеста.

**Тесты:**

* точный текст секции отряда со всеми новыми полями;
* точный текст секции отряда без новых полей (регрессия);
* `condlist_0/1/2`, отключение авто-провала;
* `HasItem(count>1)` → `actor_has_item_amount`;
* `HasMoney` → `BuildError`;
* варианты строк в XML и их отсутствие без вариантов;
* невалидные `npc_in_squad`/`npc_random`.

**Definition of Done:**

* `python -m pytest` зелёный;
* сборка всех существующих проектов даёт байт-идентичные файлы;
* новые тесты покрывают каждое новое поле.

### 5.2. Итерация 2 — Story-спавн и жизненный цикл

**Цель:** Story-отряд спавнится и живёт по ванильным правилам, не
задевая Warfare.

**Файлы:**

* `src/compiler/lua_gen.py`
* `src/compiler/builder.py` (только если нужен новый путь/валидация)
* `src/core/validator.py`

**Работы:**

1. `_action_spec`: `mode="warfare"` → старый `spawn_squad`;
   `mode="story"` → `spawn_story_squad`.
2. Хелпер `spawn_story_squad`: `create_squad`, метка
   `task_squads`, регистрация в `_story_squad_*`, без `set_target`,
   без `stay_time`, без `force_online`.
3. `spawn_story_squad` идемпотентен: ключ
   `stage_key(q, stage, "story_spawn")` для этапных действий и
   `key_prefix .. "_init_spawn"` для `on_init`.
4. `RemoveSquad`: `get_story_squad` + `SIMBOARD:remove_squad`.
5. `unmark_quest_squads`: очистка Story-списка.
6. Условная вставка фрагментов в `_HELPERS_TEMPLATE` и
   `_build_quest_functions`.

**Тесты:**

* Story-действие не вызывает `set_target` (текстовый ассерт);
* Warfare-действие не изменилось;
* `freeze_dyn_squads` не видит Story-отряды;
* `RemoveSquad` вызывает `get_story_squad`/`remove_squad`;
* повторный `_start` не спавнит второй отряд;
* `_cleanup` удаляет Story-отряд.

**Definition of Done:**

* Story-отряд доходит до `target_smart` и становится гарнизоном;
* `on_death` выдаёт инфопоршень;
* при отмене квеста отряд удаляется;
* Warfare-проекты байт-идентичны.

### 5.3. Итерация 3 — эталонная цепочка, документация, регрессия

**Цель:** доказать, что Фаза 2 работает на реальном сценарии, и
зафиксировать контракт.

**Файлы:**

* `examples/build_story_relay.py` (новый пример, не менять существующие)
* `tests/test_story_mode.py`
* `docs/API_v2.md` (раздел Story)
* `docs/RULE.md` (правила `on_death` → `condlist`)
* `docs/STORY_MODE_PLAN.md` (обновить статус)

**Работы:**

1. Собрать эталонную цепочку из раздела 6.
2. Проверить в игре: выдача, спавн, смерть отряда, завершение, выдача
   второго квеста, награда.
3. Зафиксировать хэши вывода 5 существующих проектов до/после.
4. Добавить интеграционный тест сборки эталонного проекта.
5. Описать в `API_v2.md` новые поля и их семантику.

**Definition of Done:**

* эталонный проект собирается одной командой;
* в игре цепочка проходится без Lua-ошибок;
* старые проекты не изменились ни на байт;
* документация описывает Story-паттерн без чтения исходников.

### 5.4. Общие критерии Фазы 2

1. Ни одного нового `character_desc_*.xml`.
2. Ни одного вызова `sim_squad_warfare.*` из Story-пути.
3. Ни одного `owning_faction`/`defense_count` в Story-завершении.
4. Любой Story-квест можно пройти в freeplay без Warfare.
5. Все старые тесты и golden-выходы зелёные.

---

## 6. Эталонный квест «Последний ретранслятор»

### 6.1. Паспорт

| Параметр | Значение |
|---|---|
| Локация | Затон (`zaton`) |
| Квестодатель | `zat_a2_stalker_barmen` (ванильный профиль в `character_desc_zaton.xml`) |
| Форма | Цепочка из двух задач |
| Отряд | `mymod_relay_merc_squad` |
| Тип завершения | Инфопоршень из `on_death` → `condlist` |
| Награда | Деньги + предмет |
| Уникальные профили | Не генерируются |

### 6.2. Модель (псевдокод проекта)

```python
Q1 = "mymod_relay_01_silence"
Q2 = "mymod_relay_02_report"
SQUAD = "mymod_relay_merc_squad"
INFO_TAKEN = "mymod_relay_01_taken"
INFO_MERC_DEAD = "mymod_relay_merc_dead"
INFO_Q1_DONE = "mymod_relay_01_done"
INFO_REPORTED = "mymod_relay_reported"
INFO_DONE = "mymod_relay_done"

project = ModProject(
    name="Last Relay",
    quests={
        Q1: Quest(
            id=Q1,
            npc_id="zat_a2_stalker_barmen",
            giver_npc_id="zat_a2_stalker_barmen",
            npc_location="zaton",
            dialog_id="mymod_relay_take",
            dialog_ids=["mymod_relay_take"],
            title_ru="Последний ретранслятор",
            title_en="The Last Relay",
            descr_ru="Бармен просит убрать группу, захватившую ретранслятор в порту.",
            descr_en="The barman wants the group at the port relay eliminated.",
            is_storyline=True,
            icon="ui_inGame2_Put_v_pripyat",
            prior=60,
            stages={
                0: Stage(
                    id=0,
                    title_ru="Уничтожить группу у ретранслятора",
                    title_en="Eliminate the relay group",
                    descr_ru="Наёмники заняли ретранслятор в порту Затона. Уничтожьте их.",
                    descr_en="Mercenaries have seized the relay at Zaton port. Eliminate them.",
                    target_squad_id=SQUAD,
                ),
            },
            on_init_actions=[
                SpawnSquad(
                    squad_alias=SQUAD,
                    smart_alias="zat_stalker_base_smart",
                    mode="story",
                ),
            ],
            extra_condlists=[
                QuestCondlist(
                    when=[HasInfo(info=INFO_MERC_DEAD)],
                    result="complete",
                ),
            ],
            fail_on_giver_death=True,
            taken_info=INFO_TAKEN,
            complete_info=INFO_Q1_DONE,
            cleanup_infos=[INFO_MERC_DEAD],
            on_complete_actions=[
                GiveTask(task_id=Q2),
            ],
            on_fail_actions=[
                RemoveSquad(squad_alias=SQUAD),
            ],
            reward_money=5000,
        ),
        Q2: Quest(
            id=Q2,
            npc_id="zat_a2_stalker_barmen",
            giver_npc_id="zat_a2_stalker_barmen",
            npc_location="zaton",
            dialog_id="mymod_relay_report",
            dialog_ids=["mymod_relay_report"],
            title_ru="Последний ретранслятор: отчёт",
            title_en="The Last Relay: Report",
            descr_ru="Вернитесь к бармену и доложите о зачистке.",
            descr_en="Return to the barman and report the cleanup.",
            is_storyline=True,
            icon="ui_inGame2_Put_v_pripyat",
            prior=60,
            stages={
                0: Stage(
                    id=0,
                    title_ru="Доложить бармену",
                    title_en="Report to the barman",
                    descr_ru="Ретранслятор чист. Поговорите с барменом.",
                    descr_en="The relay is clear. Talk to the barman.",
                    target_alias="zat_a2_stalker_barmen",
                ),
            },
            extra_condlists=[
                QuestCondlist(
                    when=[HasInfo(info=INFO_REPORTED)],
                    result="complete",
                ),
            ],
            fail_on_giver_death=True,
            complete_info=INFO_DONE,
            cleanup_infos=[INFO_REPORTED],
            reward_money=12000,
            reward_item_alias="wpn_val_modern_kobra",
            reward_item_count=1,
        ),
    },
    squads={
        SQUAD: CustomSquad(
            id=SQUAD,
            faction="killer",
            npc=[
                "sim_default_killer_1",
                "sim_default_killer_2",
                "sim_default_killer_3",
            ],
            target_smart="zat_b52",
            story_id=SQUAD,
            death_infos=[INFO_MERC_DEAD],
            relationship="enemy",
        ),
    },
    dialogs={
        "mymod_relay_take": Dialog(
            id="mymod_relay_take",
            npc_alias="zaton.barman",
            npc_id="zat_a2_stalker_barmen",
            npc_location="zaton",
            task_id=Q1,
            role="take",
            preconditions=[DontHasInfo(info=INFO_TAKEN)],
            phrases={
                0: Phrase(
                    id=0,
                    text_ru="Бармен, слышал про ретранслятор в порту?",
                    text_en="Barman, heard about the relay at the port?",
                    next_phrases=[1],
                ),
                1: Phrase(
                    id=1,
                    text_ru="Слышал. Наёмники заняли его и глушат связь. Убери их.",
                    text_en="I have. Mercs took it and jam the signal. Take them out.",
                    actions=[GiveInfo(info=INFO_TAKEN), GiveTask(task_id=Q1)],
                ),
            },
        ),
        "mymod_relay_report": Dialog(
            id="mymod_relay_report",
            npc_alias="zaton.barman",
            npc_id="zat_a2_stalker_barmen",
            npc_location="zaton",
            task_id=Q2,
            role="turnin",
            preconditions=[
                HasInfo(info=INFO_Q1_DONE),
                DontHasInfo(info=INFO_DONE),
            ],
            phrases={
                0: Phrase(
                    id=0,
                    text_ru="Ретранслятор чист.",
                    text_en="The relay is clear.",
                    next_phrases=[1],
                ),
                1: Phrase(
                    id=1,
                    text_ru="Хорошая работа. Держи свою плату.",
                    text_en="Good work. Here is your payment.",
                    actions=[GiveInfo(info=INFO_REPORTED)],
                ),
            },
        ),
    },
)
```

Замечания к модели:

* `Q1.complete_info = INFO_Q1_DONE` выдаётся автоматически в `_reward`;
  `GiveTask(Q2)` в `on_complete_actions` запускает следующую задачу.
* `Q1.cleanup_infos = [INFO_MERC_DEAD]` обязателен: иначе после провала
  и повторного взятия старый инфопоршень сразу завершит новый заход.
* `Q1.on_fail_actions = [RemoveSquad(...)]` убирает отряд при отмене.
* `Q2` не имеет `on_complete_actions`: награда выдаётся в `_reward`.
* диалог `mymod_relay_report` **не** вызывает `CompleteTask`:
  он только выдаёт `INFO_REPORTED`, а завершает `condlist_1`. Это
  ванильный паттерн `dialog → info → condlist → on_complete`.
* `target_squad_id` в Q1 даёт маркер на отряде после спавна; до спавна
  `_target` откатывается к квестодателю на один тик.

### 6.3. Ожидаемые артефакты

```text
output/last_relay/
  gamedata/configs/misc/task/tm_last_relay.ltx
  gamedata/configs/misc/squad_descr/squad_descr_last_relay.ltx
  gamedata/configs/gameplay/dialogs_last_relay.xml
  gamedata/configs/gameplay/character_desc_zaton.xml   # пропатчен, не создан
  gamedata/configs/text/rus/st_last_relay.xml
  gamedata/configs/text/eng/st_last_relay.xml
  gamedata/scripts/last_relay_quests.script
```

В `squad_descr_last_relay.ltx` обязательна строка:

```ini
on_death = %+mymod_relay_merc_dead%
```

В `tm_last_relay.ltx` у Q1 обязательны:

```ini
condlist_0 = {!task_giver_alive(mymod_relay_01_silence)} fail
condlist_1 = {+mymod_relay_merc_dead} complete
```

В `character_desc_zaton.xml` у
`<specific_character id="zat_a2_stalker_barmen">` появляются только:

```xml
<actor_dialog>mymod_relay_take</actor_dialog>
<actor_dialog>mymod_relay_report</actor_dialog>
```

### 6.4. Сценарий игрока

1. Игрок говорит с барменом на Затоне, берёт Q1.
2. `_start` выдаёт `INFO_TAKEN` и спавнит `mymod_relay_merc_squad` на
   `zat_stalker_base_smart`; отряд идёт к `zat_b52`.
3. Игрок убивает отряд. Последний NPC вызывает `remove_npc`, отряд
   пуст → `on_death` выдаёт `mymod_relay_merc_dead`.
4. `task_manager` видит `condlist_1` и завершает Q1 → `_reward` выдаёт
   5000 и `INFO_Q1_DONE`, затем `GiveTask(Q2)`.
5. Игрок возвращается к бармену, говорит, получает `INFO_REPORTED`.
6. `condlist_1` завершает Q2 → `_reward` выдаёт деньги и предмет,
   выставляет `INFO_DONE`.
7. Повторное взятие невозможно: диалоги закрыты инфопоршнями.

### 6.5. Проверки эталона

| Проверка | Ожидание |
|---|---|
| Сборка | без ошибок, все 7 файлов на месте |
| `character_desc_zaton.xml` | существует ровно один, без новых профилей |
| `on_death` | ровно одна строка в секции отряда |
| Спавн | отряд появляется на базе и идёт в порт |
| Смерть отряда | Q1 завершается без участия игрока в порту |
| Цепочка | Q2 появляется в PDA сразу после Q1 |
| Отмена Q1 | отряд исчезает, повторное взятие работает |
| Warfare-регрессия | 5 старых проектов байт-идентичны |

---

## 7. Совместимость с Warfare

### 7.1. Матрица изменений

| Изменение | Старое поведение | Влияние на Warfare |
|---|---|---|
| `CustomSquad.death_infos` | поля нет, строки нет | нет: пустой список → нет `on_death` |
| `CustomSquad.relationship/idle_time/spawn_point` | поля нет | нет: `None` → нет строки |
| `CustomSquad.npc_random/npc_in_squad` | только `npc` | нет: старые проекты не задают |
| `Stage.target_variants/descr_variants` | одна цель/строка | нет: пустые списки → старый код |
| `Quest.extra_condlists` | только авто-провал | нет: пустой список → старый LTX |
| `Quest.fail_on_giver_death=True` | авто-провал всегда | да: значение по умолчанию сохраняет вывод |
| `SpawnSquad.mode="warfare"` | старый `spawn_squad` | да: значение по умолчанию сохраняет вывод |
| `RemoveSquad` | действия нет | нет: opt-in |
| `spawn_story_squad` | хелпера нет | нет: вставляется только при Story-действии |
| `_target`/`_descr` варианты | фиксированный код | нет: фрагменты только при вариантах |

### 7.2. Стратегия байт-идентичности

1. Новые ключи в `QUESTS` добавляются **только если непусты**.
2. Новые ветки `run_actions` вставляются через условный маркер шаблона,
   который вырезается целиком для проектов без Story-действий.
3. `spawn_task_squad`, `freeze_dyn_squads`, `stage_cleared` не
   редактируются — рядом появляются новые функции.
4. `_build_quest_section` не меняет порядок существующих строк; блок
   condlist добавляется после `on_cancel`.
5. `generate_squads_ltx` сохраняет порядок `faction`, `npc`,
   `target_smart`, `story_id` для старых моделей; новые поля идут
   после `faction`/`npc` и только если заданы.
6. Перед merge: снять SHA256 всех файлов 5 существующих проектов;
   после merge: сравнить. Любое расхождение — блокер.

Проекты для регрессии:

* `output/brothers_in_arms`
* `output/cordon_warfare_campaign`
* `output/dead_city_merc_test`
* `output/golden_shield_test`
* `output/merc_hunt_campaign`
* `output/village_help_wolfs_request`

---

## 8. Риски и меры

| Риск | Причина | Мера |
|---|---|---|
| Двойной спавн Story-отряда | `_start` вызван повторно после загрузки | Ключ `_init_spawn` в pstor; проверка перед `create_squad` |
| Отряд остаётся после отмены | `_cleanup` не удаляет | `RemoveSquad` в `on_fail_actions`; тест |
| `on_death` срабатывает слишком рано | отряд убили по пути | Это ванильное поведение; для сюжетных NPC использовать `essential`/`story_id` и отдельный отряд |
| Маркер цели прыгает на квестодателя | story id отряда ещё не зарегистрирован | `target_squad_id` + `target_variants`; документировать один тик fallback |
| Смешанный Story+Warfare квест | `world`-гейт | Валидатор запрещает; разделять на два квеста |
| Смерть квестодателя ломает цепочку | авто-провал | `fail_on_giver_death=False` для сюжетно-неубиваемых |
| Потеря награды | награда в реплике диалога | Награда только в `Quest.reward_*`/`on_complete_actions`; предупреждение уже есть (`builder.py:291-298`) |
| Дубли `<actor_dialog>` | повторная сборка | `patch_character_desc` идемпотентен (`builder.py:1016-1026`) |
| Кодировка/BOM | русский текст | Не трогать существующие байты; писать в cp1251 с прежним BOM |
| `npc_random` с числом вместо секции | ванильный разнобой | Валидатор: только непустые строки-секции |
| Story-отряд в офлайн-бою | симуляция | `mark_task_squad` + `sim_offline_combat.task_squads` |
| Таймерный этап | нет условий времени | Phase 3; в Phase 2 — внешний скрипт + инфопоршень |

---

## 9. Backlog Фазы 3

1. **Уникальные NPC-профили** (опционально): генерация
   `<specific_character>` с полным набором ресурсов, только если
   ванильного квестодателя нет.
2. **Таймеры и `status_functor_params`**: условия `TimerElapsed`,
   поддержка ванильных `status_functor`.
3. **Динамические задачи**: `job_descr`, `fetch_func`, `target_func`,
   интеграция с `tasks_assault/bounty/fetch`.
4. **Сложные цепочки**: граф задач, восстановление после провала
   среднего звена, ветвления.
5. **Escort/defend Story-варианты** без Warfare-семантики.
6. **Многоуровневые цели**: несколько смартов/отрядов на этап.
7. **Локализация**: проверка полноты всех вариантов `descr`.
8. **Интеграционный тест в игре**: автоматический прогон сценария.
9. **Расширенные условия**: `HasMoney` и `SmartOwner` в condlist через
   собственные functor-ы.
10. **`on_reversed`** и обратные переходы задач.

---

## 10. Приложение A. Проверенные точки кода

### Ванильные файлы

| Файл | Строки | Что подтверждено |
|---|---|---|
| `_unpacked/configs/misc/task/tm_lostzone_ms.ltx` | 13–25, 27–39 | `storyline`, `on_init=create_squad`, `condlist_0/1`, `on_complete=give_task` |
| `_unpacked/configs/misc/task/tm_lostzone_ll.ltx` | 13–26, 71–84, 87–99 | condlist-цели, цепочки, `remove_squad`, `status_functor` |
| `_unpacked/configs/misc/squad_descr/squad_descr_lostzone_ms.ltx` | 3–8 | `target_smart`, `story_id`, `on_death` |
| `_unpacked/configs/misc/squad_descr/squad_descr_zaton.ltx` | 75–83, 91–97 | `spawn_point`, `target_smart`-condlist, `on_death` |
| `_unpacked/configs/misc/squad_descr/squad_descr_agroprom.ltx` | 90–93 | `relationship`, `npc_random`, `npc_in_squad` |
| `_unpacked/configs/gameplay/character_desc_zaton.xml` | 238+ | ванильный профиль `zat_a2_stalker_barmen` |
| `_unpacked/configs/gameplay/character_desc_deadcity.xml` | 5+ | профиль `cit_killers_merc_trader_stalker` |
| `_unpacked/scripts/sim_squad_scripted.script` | 55–56, 79, 115–116, 276, 304–319, 445–477 | `action_condlist`, `death_condlist`, `idle_time`, `specific_update`, `on_death` |
| `_unpacked/scripts/sim_squad_warfare.script` | 52–57, 122–134, 877–914 | freeplay early-return, `__lock`, `set_target` |
| `_unpacked/scripts/sim_board.script` | 131–154 | `create_squad` и назначение смарту |
| `_unpacked/scripts/xr_effects.script` | `create_squad`, `remove_squad` | ванильные эффекты спавна/удаления |
| `_unpacked/scripts/task_objects.script` | 42–56, 233–243 | `target_functor`, `descr_functor`, `condlist` до `status_functor` |
| `_unpacked/scripts/task_functor.script` | 825–830 | `target_condlist` → `get_story_object_id` |
| `_unpacked/scripts/xr_conditions.script` | 3012–3030 | `task_giver_alive` |
| `_unpacked/scripts/_g.script` | 2687–2695 | `get_story_object_id`/`get_story_squad` |

### Текущий фреймворк

| Файл | Строки | Что подтверждено |
|---|---|---|
| `src/core/models.py` | 227–236 | `SpawnSquad` |
| `src/core/models.py` | 554–631 | `WarfareCapture`, `Stage` |
| `src/core/models.py` | 634–840 | `Quest`, `transfer_conditions`, `requires_warfare` |
| `src/core/models.py` | 848–882 | `CustomSquad` |
| `src/compiler/ltx_gen.py` | 106–176 | эмиссия `squad_descr_*.ltx` |
| `src/compiler/ltx_gen.py` | 178–243 | секция задачи, авто-провал |
| `src/compiler/lua_gen.py` | 266–279 | `target_squad_dead` |
| `src/compiler/lua_gen.py` | 369–399 | `spawn_task_squad` |
| `src/compiler/lua_gen.py` | 413–465 | `spawn_stage_for`, `stage_cleared` |
| `src/compiler/lua_gen.py` | 1034–1169 | `_build_quest_data`, `world` |
| `src/compiler/lua_gen.py` | 1248–1285 | `_target`, `_descr` |
| `src/compiler/lua_gen.py` | 1288–1382 | `_status`, `_start`, гейт |
| `src/compiler/lua_gen.py` | 1411–1428 | `_cleanup` |
| `src/compiler/xml_gen.py` | 147–157 | строки этапов |
| `src/compiler/builder.py` | 300–351 | состав выходных файлов |
| `src/compiler/builder.py` | 791–896 | привязка диалогов |
| `src/compiler/builder.py` | 960–1027 | патч `character_desc` |
| `examples/build_bro_story.py` | 53–62, 152–153 | существующий Story-пример с ванильным NPC |

### Быстрые команды проверки

```powershell
git status --porcelain
python -m pytest
```

Ожидание после Фазы 2: единственный новый файл — этот план; в
`src/`, `tests/`, `output/`, `examples/` изменений нет.

---

## 11. Приложение B. Чек-лист приёмки Фазы 2

- [ ] Story-квест проходит в freeplay без Warfare.
- [ ] `CustomSquad.on_death` выдаёт инфопоршень.
- [ ] `condlist_N` завершает задачу без `owning_faction`.
- [ ] Цепочка `GiveTask` работает: Q2 появляется после Q1.
- [ ] Отряд спавнится через `create_squad`, без `set_target`.
- [ ] Отряд доходит до `target_smart` и становится гарнизоном.
- [ ] Отмена/провал удаляет Story-отряд.
- [ ] Повторное взятие после провала не ломается.
- [ ] Награда не теряется и не дублируется.
- [ ] `character_desc_*.xml` не создаётся; патчится только
      `<actor_dialog>`.
- [ ] Все старые проекты байт-идентичны.
- [ ] `pytest` зелёный.
- [ ] Документация обновлена.
