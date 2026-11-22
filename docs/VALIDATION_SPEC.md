# VALIDATION_SPEC — валидация квестовых проектов Anomaly 1.5.3

**Версия:** 1.0  
**Дата:** 2026-11-19  
**Область:** `examples/phase3/*.py`, эталонные `examples/build_story_relay.py` и `examples/build_golden_test.py`, контракт `docs/API_v2.md`, runtime-валидатор `src/core/validator.py`, модели `src/core/models.py`.  
**Статус:** спецификация; implementation не входит в `src/` и `examples/` этим документом.

---

## 0. Краткий итог

Проверены 12 сторонних сценариев Phase 3. Результат:

| Показатель | Значение |
|---|---:|
| Синтаксически корректны | 12 / 12 |
| Проходят Pydantic-модели | 11 / 12 |
| Сборка успешна | 7 / 12 |
| Сборка падает | 4 / 12 |
| Падает до сборки на модели | 1 / 12 |

Успешно собрались: `story_01`, `story_02`, `story_05`, `story_07`, `warfare_01`, `warfare_02`, `warfare_04`.  
Не собрались: `story_03`, `story_04`, `story_06`, `story_08`.  
Не дошли до сборки: `warfare_03`.

**Главные причины отказов:**

1. **Ассеты не проверяются до сборки.** Четыре `BuildError` вызваны отсутствующими `<specific_character>`; ещё два отсутствующих NPC и один отсутствующий смарт скрыты за первым падением `story_08`.
2. **Смешаны три разные семантики смарта:** точка спавна (`SpawnSquad.smart_alias`), точка назначения (`CustomSquad.target_smart`) и цель маркера (`Stage.target_alias`). В `story_01` и `story_03` вражеский отряд спавнится прямо на смарте квестодателя.
3. **Story-отряды не имеют устойчивой идентичности.** В `story_02` и `story_07` не задан `CustomSquad.story_id`; `SpawnNpcItem`, `RemoveSquad` и `target_squad_id` не могут надёжно резолвить командира/отряд.
4. **Граф завершения квеста неполон или преждевременен.** `story_02` зависает на финальном этапе без `CompleteTask`; `story_04` завершает квест по `HasItem` до диалога и теряет выбор награды; `story_08` теряет награду из-за `GiveMoney`/`GiveItem` рядом с `CompleteTask` при пустых `reward_*`.
5. **Условие-сирота.** В `story_05` `INFO_INTEL_FOUND` только читается в `TargetVariant`, но нигде не выдаётся; смена цели недостижима.
6. **Режимные гейты.** В `warfare_01`, `warfare_02`, `warfare_04` стоит `requires_warfare=True`: вне Warfare закрывается `_can_take` и не тикают `_start`/`_status`. Если тест шёл в Story/freeplay, стартовой фразы не будет.
7. **Неверные алиасы отрядов.** `squad.mercenary_advanced` в БД не найден; `sim_default_stalker_1` — это NPC-секция, а не отряд. Это ломает `WarfareCapture` даже при включённом Warfare.
8. **Уникальные NPC и `meet`-диалоги.** `zat_a2_stalker_barmen` и `cit_killers_merc_trader_stalker` — уникальные торговцы; привязка `<actor_dialog>` может не проявиться в игре из-за `meet`-диалога/профиля. Для `story_05` и `story_07` это вероятная, но не доказанная по разрешённым файлам причина.

---

## 1. Методика и границы проверки

### 1.1. Что проверялось

1. **Синтаксис.** Все 12 файлов читались и компилировались в память через `compile(source, filename, "exec")`; `__pycache__` в `examples/` не создавался.
2. **Pydantic-модели.** Импортировался `create_project()` каждого файла; ошибки `ValidationError` фиксировались без запуска сборки.
3. **Сборка.** Использовался `logs/app.log` как основной источник фактов: `BuildError`, предупреждения `find_phrase_reward_conflicts`, количество записанных файлов.
4. **Ассеты.** Проверялись через разрешённый CLI:
   ```text
   venv\Scripts\python.exe main.py search <name> -t npc
   venv\Scripts\python.exe main.py search <name> -t smart
   venv\Scripts\python.exe main.py search <name> -t item
   venv\Scripts\python.exe main.py search <name> -t squad
   ```
5. **Контракт.** Сверялись `docs/API_v2.md`, `src/core/validator.py`, `src/core/models.py`, эталонные примеры.

### 1.2. Ограничения

- `_unpacked/` и `tools/standart_manual_mod_snapshot.txt` не открывались и не искались.
- Для `story_05` и `story_07` точная runtime-причина не доказана: сборка успешна, а runtime-логи недоступны. В таблице такие выводы помечены как **вероятная причина**.
- `story_08` не мог быть проверен в игре: сборка падает до записи диалогов. Симптом «нет стартовой фразы» здесь является следствием неудачной сборки, а не ошибки привязки диалога.
- `warfare_03` не доходит до сборки: ошибка возникает при создании `Quest`.
- Проверка ассетов через `main.py search` отражает SQLite-базу `data/anomaly_db.sqlite`; если секция есть в игре, но не проиндексирована, это отдельный случай и должен логироваться как «не подтверждено БД».

---

## 2. Диагностика 12 файлов

### 2.1. Story-сценарии

| Файл | Синтаксис / модель | Сборка по `logs/app.log` | Проверка ассетов | Диагноз | Что исправлять |
|---|---|---|---|---|---|
| `story_01.py` | OK / OK | **OK**, 8 файлов, 19:10:23 | `esc_2_12_stalker_wolf` есть; `esc_smart_terrain_2_12` есть; `medkit_army` есть | `SpawnSquad` и `CustomSquad.target_smart` указывают на `esc_smart_terrain_2_12` — это смарт Волка. Вражеский отряд появляется в лагере квестодателя, сразу начинается бой; Волк/база могут погибнуть, а квест — уйти в fail по `fail_on_giver_death=True`. Диалог сдачи при этом избыточен: завершение идёт через `extra_condlists`. | Спавнить отряд на удалённом смарте, а `target_smart` вести к цели; не использовать смарт квестодателя как точку спавна врага. Добавить `ClearSmart`/`clear_smart` или проверку «spawn smart ≠ giver smart». |
| `story_02.py` | OK / OK | **OK**, 8 файлов, 19:30:56 | `esc_smart_terrain_5_7` есть; `itm_pda_common` есть; `sim_default_killer_1/2` есть | `CustomSquad.story_id` не задан. `SpawnNpcItem(target_alias=SQUAD_ID)` и `RemoveSquad` резолвят отряд через story-ID, поэтому командир/отряд ненадёжны. `npc_in_squad=[3,4]` при двух шаблонах — риск переспавна/подмены. Главное: в диалоге сдачи **нет `CompleteTask`**, а у этапа 1 нет условия завершения — квест навсегда остаётся на «Вернуться к Волку». `GiveInfo(INFO_DONE)` продублирован, но задачу не закрывает. При провале удаляется отряд, но не изымается ПДА: повторное взятие сразу закроет этап 0 по `HasItem`. | Задать `story_id=SQUAD_ID`; добавить `CompleteTask` в реплику сдачи или `return_to_giver_stage=1`; добавить `RemoveItem(itm_pda_common)` в `on_fail_actions`; согласовать `npc_in_squad` с числом шаблонов; убрать дубль `GiveInfo`. |
| `story_03.py` | OK / OK | **FAIL**: `BuildError: <specific_character id="esc_m_trader"> не найден в character_desc_*.xml.` 19:31:00,693 | `esc_m_trader` — **0**; корректный Сидорович — `esc_2_12_stalker_trader`; `esc_smart_terrain_5_7` есть; `itm_pda_common`, `wpn_ak74`, `conserva` есть | Падение на отсутствующем профиле. Даже после замены NPC остаётся вторая ошибка: `SMART_TRADER = SMART_TARGET = esc_smart_terrain_5_7`, то есть отряд снова спавнится на смарте квестодателя. Q1 использует `faction="killer"` с шаблоном `sim_default_stalker_1`; `npc_in_squad=[3,5]` при одном шаблоне. Цепочка Q1→Q2 и награда Q2 сами по себе корректны. | Заменить NPC на `esc_2_12_stalker_trader`; развести смарт спавна и смарт квестодателя; согласовать фракцию и шаблоны; проверить `fail_on_giver_death` для Q1/Q2. |
| `story_04.py` | OK / OK | **FAIL** на `esc_m_trader`; до падения два warning: `story_04_turnin`, реплики 2 и 4 — `GiveMoney`/`GiveItem` вместе с `CompleteTask` при пустых `reward_money`/`reward_item_alias` | `esc_m_trader` — 0; `esc_smart_terrain_5_7` есть; `itm_pda_common`, `wpn_ak74` есть | Кроме отсутствующего NPC: в квесте **один этап**, а `transfer_conditions[0] = {"complete": [HasItem(...)]}` завершает весь квест сразу при получении ПДА, ещё до возврата к Сидоровичу. `reward_*` пусты, награда есть только в ветках диалога с `CompleteTask`; после автозавершения `CompleteTask` уже не даёт награду, а `_reward` ничего не выдаёт. Выбор «деньги/оружие» теряется. | Добавить явный этап возврата и переходить на него по `HasItem`, а завершать через `CompleteTask`; либо убрать автопереход и завершать только диалогом. Награду вынести в `Quest.reward_*` или `on_complete_actions`; ветвление награды строить на взаимоисключающих info и одном completion-пути. |
| `story_05.py` | OK / OK | **OK**, 7 файлов, 19:31:28 | `zat_a2_stalker_barmen` есть; `zat_b52`, `zat_b7`, `zat_b14_smart_terrain` есть; `itm_pda_common`, `medkit_army` есть | `INFO_INTEL_FOUND` только читается в `TargetVariant`, но **нигде не выдаётся** — смена цели на `zat_b14_smart_terrain` недостижима; вариант цели мёртвый. В игре нет стартовой фразы: **вероятно**, уникальный `meet`-профиль Бармена не показывает добавленный `<actor_dialog>`, либо в сохранении уже есть `story_05_started` и `DontHasInfo` блокирует диалог. Сборка и модели корректны. | Выдавать `INFO_INTEL_FOUND` из этапа/реплики или удалить вариант; проверить `meet`-диалог Бармена и порядок `actor_dialog`; тестировать на чистом сохранении/новом профиле; для детерминированного теста взять неуникального NPC. |
| `story_06.py` | OK / OK | **FAIL**: `BuildError: <specific_character id="zat_a2_stalker_leader_freedom"> не найден...` 19:31:32,055 | `zat_a2_stalker_leader_freedom` — **0**; лидер Свободы в игре — Лукаш `mil_smart_terrain_7_7_freedom_leader_stalker` (локация `mil`/Армейские склады, не `zaton`); `zat_b52`, `zat_b7`, `medkit_army` есть | Падение на отсутствующем профиле. После замены NPC важен `requires_faction="freedom"`: вне фракции Свободы `_can_take` закрыт, стартовой фразы не будет. `npc_in_squad=[4,6]` при двух шаблонах — риск. Автосдача через `return_to_giver_stage=1` зависит от правильной локации и живого квестодателя. | Использовать Лукаша и правильную локацию либо создать отдельный Freedom-профиль; проверить тест под фракцией Свободы; согласовать `npc_in_squad`; проверить `return_distance` и доступность NPC. |
| `story_07.py` | OK / OK | **OK**, 8 файлов, 19:31:34 | `cit_killers_merc_trader_stalker` есть; `cit_killers`, `cit_bandits` есть; `medkit_army` есть | В игре отряд не появляется (по результату теста). Наиболее вероятно: `CustomSquad.story_id` не задан, поэтому `SpawnSquad(mode="story")`/`RemoveSquad` не дают устойчивого story-отряда; спавн идёт прямо на `cit_bandits`, где может уже стоять ванильный отряд/владелец; `target_squad_id` отсутствует, поэтому завершение зависит только от `death_infos`. Уникальный торговец Душман может не показать take-диалог из-за `meet`. Точная причина не доказана по разрешённым файлам. | Задать `story_id=SQUAD_ID`; спавнить на безопасном смарте и вести `target_smart` к `cit_bandits`; добавить `target_squad_id`/`target_seen`; проверить `get_story_squad` в игре; для уникального NPC проверить `meet`/`actor_dialog`; добавить debug-лог спавна. |
| `story_08.py` | OK / OK | **FAIL**: `BuildError: <specific_character id="esc_2_12_stalker_rookie"> не найден...` 19:31:37,019; до падения warning для `story_08_wolf_turnin`, реплики 2 и 4 (`GiveMoney` и `GiveItem` + `CompleteTask`, `reward_*` пусты) | `esc_2_12_stalker_rookie` — **0**; `garb_bandit_boss_sultan` — **0**; `garb_smart_terrain_1_6` — **0**; реальный Султан — `zat_b7_bandit_boss_sultan` (Затон, АТП), а не Свалка; `esc_2_12_stalker_wolf`, `itm_pda_common`, `wpn_ak74` есть | «Нет стартовой фразы» — это следствие **несобранного мода**: падение на профиле свидетеля происходит до записи диалогов. После замены свидетеля останутся ещё две ошибки: отсутствующий подозреваемый и отсутствующий смарт. Награда также под угрозой: `complete_info=None`, `reward_*` пусты, а `GiveMoney`/`GiveItem` стоят рядом с `CompleteTask`; warning подтверждён логом. | Заменить свидетеля на существующего NPC (например, `esc_2_12_stalker_fanat`); заменить Султана на `zat_b7_bandit_boss_sultan` и локацию/смарт на реальные (Затон), либо взять реального NPC Свалки; вынести награду в `Quest.reward_*`/`on_complete_actions`; развести ветки по info и оставить один completion-путь. |

### 2.2. Warfare-сценарии

| Файл | Синтаксис / модель | Сборка по `logs/app.log` | Проверка ассетов | Диагноз | Что исправлять |
|---|---|---|---|---|---|
| `warfare_01.py` | OK / OK | **OK**, 7 файлов, 19:31:51 | `zat_a2_stalker_barmen`, `zat_b14_smart_terrain`, `wpn_ak74` есть; `squad.mercenary_advanced` — **0**; `sim_default_stalker_1` — NPC-секция, не отряд | `requires_warfare=True` закрывает `_can_take` и `_start`/`_status` вне Warfare; в Story/freeplay стартовой фразы не будет. `WarfareCapture` дополнительно ставит `world=true`. Вражеский алиас `squad.mercenary_advanced` в БД отсутствует; корректный алиас — `squad.killer_advanced` (игровой ID `merc_sim_squad_advanced`). Союзник задан NPC-секцией, а `ally_squad_alias` ожидает отряд. | Тестировать в Warfare; заменить enemy на `squad.killer_advanced` или `merc_sim_squad_advanced`; заменить ally на проверенный squad alias/ID; если нужен Story-режим — убрать `requires_warfare` и `WarfareCapture`. |
| `warfare_02.py` | OK / OK | **OK**, 7 файлов, 19:31:55 | `zat_b7`, `zat_b14_smart_terrain`, `wpn_ak74`, `medkit_army` есть; `squad.mercenary_advanced` — **0**; `sim_default_stalker_1` — NPC, не отряд | Те же режимные и ассетные ошибки, что в `warfare_01`. Два этапа используют один и тот же `ENEMY_SQUAD`; после зачистки первого этапа повторный спавн той же секции может быть отклонён/создать неоднозначность. `GiveItem` в `on_start_actions` работает только в Warfare: вне режима `_status` не тикает. | Тестировать в Warfare; исправить enemy/ally; для двух этапов использовать разные enemy-секции или подтвердить повторный спавн; проверить выдачу предметов на обоих этапах. |
| `warfare_03.py` | OK / **FAIL** `ValidationError` в `Quest.extra_condlists` (2 ошибки): передан сырой `dict` вместо `QuestCondlist` | **Нет сборки**; в логе отсутствует, ошибка возникает при создании модели | `cit_kanaliz1`, `cit_killers`, `cit_killers_merc_trader_stalker` есть; `warfare_03_player_squad` не объявлен в `project.squads` и не найден в БД; `SQUAD_SECTION` не используется | Первая ошибка — форма `extra_condlists`: нужен `QuestCondlist(when=[...], result="complete")`, а не `{"complete": [SmartOwner(...)]}`. Даже после исправления формы `SmartOwner` **не поддерживается** в `QuestCondlist` по `docs/API_v2.md` (Фаза 2 → `BuildError`). Кроме того, `SpawnSquad(squad_alias=PLAYER_SQUAD_ALIAS, mode="warfare")` и `SetTarget` ссылаются на несуществующий отряд; `requires_warfare=True`; своего `WarfareCapture` нет. Завершение невозможно. | Переписать на `WarfareCapture` с валидными enemy/ally и завершением через `stage_cleared`; либо объявить `CustomSquad`/`story_id` и использовать поддерживаемые условия; убрать `SmartOwner`; исправить `extra_condlists`; проверить отряд в БД. |
| `warfare_04.py` | OK / OK | **OK**, 7 файлов, 19:32:02 | `zat_b7`, `zat_a2_stalker_barmen`, `medkit_army` есть; `squad.mercenary_advanced` — **0**; `sim_default_stalker_1` — NPC, не отряд | Q1 — Warfare-захват с `requires_warfare=True`; вне Warfare стартовой фразы нет. Q2 — Story-доклад, но он выдаётся только из `on_complete_actions` Q1, поэтому при незавершённом Q1 (из-за отсутствующего enemy или выключенного Warfare) Q2 никогда не появится. Q2 сам завершается одним `CompleteTask`, награда задана в `reward_*` — это корректно. | Тестировать в Warfare; исправить enemy/ally; проверить, что Q1 реально доходит до `stage_cleared`; после этого Q2 должен выдаться и корректно завершиться. |

### 2.3. Сводка по ассетам

Проверено через `main.py search`; число — количество найденных записей.

| Ассет | Тип | Найдено | Комментарий |
|---|---|---:|---|
| `esc_2_12_stalker_wolf` | NPC | 1 | Волк, валиден |
| `zat_a2_stalker_barmen` | NPC | 1 | Бармен, валиден |
| `cit_killers_merc_trader_stalker` | NPC | 1 | Душман, валиден |
| `esc_m_trader` | NPC | **0** | Не существует в 1.5.3; Сидорович — `esc_2_12_stalker_trader` |
| `esc_2_12_stalker_rookie` | NPC | **0** | Нет такого профиля; есть `esc_2_12_stalker_fanat`, `esc_2_12_stalker_nimble`, `esc_2_12_stalker_trader`, `esc_2_12_stalker_wolf` |
| `zat_a2_stalker_leader_freedom` | NPC | **0** | Лидер Свободы — Лукаш `mil_smart_terrain_7_7_freedom_leader_stalker` |
| `garb_bandit_boss_sultan` | NPC | **0** | Султан — `zat_b7_bandit_boss_sultan` (Затон, АТП) |
| `sim_default_bandit_1`, `sim_default_bandit_2` | NPC | 18, 31 | Валидные шаблоны |
| `sim_default_killer_1`, `sim_default_killer_2` | NPC | 22, 22 | Валидные шаблоны |
| `sim_default_stalker_1` | NPC | 88 | Валидный NPC, **не отряд** |
| `esc_smart_terrain_2_12` | smart | 1 | Смарт Волка |
| `esc_smart_terrain_5_7` | smart | 1 | Бункер Сидоровича |
| `zat_b52` | smart | 1 | Скадовск |
| `zat_b7` | smart | 2 | АТП Затона |
| `zat_b14_smart_terrain` | smart | 1 | Катакомбы/Земснаряд |
| `cit_killers` | smart | 3 | База наёмников |
| `cit_bandits` | smart | 2 | Лагерь бандитов |
| `cit_kanaliz1` | smart | 1 | Канализация |
| `garb_smart_terrain_1_6` | smart | **0** | Нет смарта с префиксом `garb_`; для Свалки нужен реальный смарт |
| `itm_pda_common` | item | 1 | Валиден |
| `medkit_army` | item | 1 | Валиден |
| `wpn_ak74` | item | 55 | Валиден |
| `conserva` | item | 2 | Валиден |
| `wpn_vintorez` | item | 10 | Валиден |
| `squad.mercenary_advanced` | squad | **0** | Не существует; корректно `squad.killer_advanced` / `merc_sim_squad_advanced` |
| `squad.killer_advanced` | squad | 1 | Валидный enemy-отряд наёмников |
| `bandit_sim_squad_advanced` | squad | 1 | Валидный игровой ID (используется в golden) |

> **Важно:** `sim_default_stalker_1` не является отрядом. `WarfareCapture.ally_squad_alias` и `SpawnSquad.squad_alias` ожидают секцию/ID отряда, а не NPC-шаблон. Это отдельная семантическая ошибка, которая не ловится текущим `ProjectValidator`.

---

## 3. Корневые причины и правила, которые их ловят

### 3.1. Ассеты

- **NPC.** `Quest.npc_id` и `Dialog.npc_id` — это точный `<specific_character id="...">` в `character_desc_<npc_location>.xml`, а не произвольный «человекочитаемый» ID. Профиль обязан существовать ровно один раз; `npc_location` обязателен. `esc_m_trader`, `esc_2_12_stalker_rookie`, `zat_a2_stalker_leader_freedom`, `garb_bandit_boss_sultan` — отрицательные примеры.
- **Смарты.** `SpawnSquad.smart_alias`, `WarfareCapture.smart_alias`, `SetTarget.smart_alias`, `Stage.target_alias`, `CustomSquad.target_smart` должны указывать на существующий smart. `garb_smart_terrain_1_6` — отрицательный пример; `cit_bandits`, `zat_b7`, `zat_b14_smart_terrain` — положительные.
- **Предметы.** Все `item_alias` должны существовать в БД/алиасах; `itm_pda_common`, `medkit_army`, `wpn_ak74`, `conserva`, `wpn_vintorez` подтверждены.
- **Отряды.** `squad_alias` — это `project.squads`, игровой ID отряда или алиас отряда БД. `squad.mercenary_advanced` не найден; `sim_default_stalker_1` — NPC, не отряд. Для Story-отряда нужен `CustomSquad`, а для его удаления/адресации — `story_id`.
- **Фракции.** `requires_faction` и `CustomSquad.faction` должны быть валидными техническими именами (`freedom`, `killer`, `bandit`, `army`, ...). Гейт `requires_faction="freedom"` в `story_06` — не ошибка сам по себе, но он объясняет отсутствие фразы у нефракционного персонажа.

### 3.2. Семантика трёх смартов

Это главная ловушка Phase 3:

| Поле | Что означает | Где используется |
|---|---|---|
| `Stage.target_alias` | Цель **маркера** в PDA. Не точка спавна. | `target_functor` |
| `SpawnSquad.smart_alias` | Точка **спавна** отряда. | `spawn_squad`/`create_squad` |
| `CustomSquad.target_smart` | Точка **назначения** отряда; куда он идёт после спавна. | секция `squad_descr_*.ltx` |

В эталоне `build_story_relay.py` Q1 спавнится на `zat_b7`, а идёт к `zat_b52`; это разные смарты. В `story_01` и `story_03` все три роли фактически collapsed в один смарт квестодателя — отсюда мгновенный бой. В `story_07` спавн и цель совпадают (`cit_bandits`), что тоже рискованно, хотя это не смарт квестодателя.

**Правило:** для вражеского Story-отряда `SpawnSquad.smart_alias` не должен совпадать со смартом квестодателя; `CustomSquad.target_smart` должен отличаться от точки спавна, если нужен марш; `Stage.target_alias` — независимое поле.

### 3.3. Story-идентичность отряда

`CustomSquad.story_id` в API назван необязательным, но для квестового отряда он фактически обязателен:

- `RemoveSquad` резолвит отряд через `get_story_squad(alias)`;
- `SpawnNpcItem(target_alias=SQUAD)` резолвит командира через story-отряд;
- `Stage.target_squad_id` и `target_seen` используют story-ID;
- без `story_id` нет устойчивой связи «отряд → командир → предмет → смерть → completion».

В `story_02` и `story_07` `story_id` нет. В `story_02` это усугубляется тем, что `SpawnNpcItem` и `SpawnSquad` стоят в одном `on_start_actions`; порядок правильный (сначала спавн, затем предмет), но без `story_id` резолв командира ненадёжен.

### 3.4. Завершение и награда

- `story_02`: финальный этап не имеет completion-пути; `CompleteTask` отсутствует.
- `story_04`: `transfer_conditions` на единственном этапе завершает весь квест по `HasItem`; диалог с выбором награды уже не нужен и не может выдать награду.
- `story_08`: `CompleteTask` + `GiveMoney`/`GiveItem` при пустых `reward_*`; warning `find_phrase_reward_conflicts` подтверждён логом.
- `story_05`: `TargetVariant` требует info, которое никто не выдаёт.
- `story_07`: завершение зависит от `death_infos`, но нет гарантии, что отряд вообще заспавнился.

**Правило:** у каждого не-финального этапа должен быть исходящий edge; у финального — completion-путь (`CompleteTask` в turnin, `return_to_giver_stage`, `extra_condlists` или `warfare_capture`). Награда должна быть в `Quest.reward_*` или `Quest.on_complete_actions`, а не рядом с `CompleteTask` при пустых reward-полях.

### 3.5. Режимные гейты

`requires_warfare=True` — это не «подсказка», а жёсткий гейт:

- `<dialog_id>_can_take` возвращает false вне Warfare;
- `<quest_id>_start` и `<quest_id>_status` не выполняются вне Warfare;
- `WarfareCapture` дополнительно включает `world=true`.

Поэтому `warfare_01`, `warfare_02`, `warfare_04` не покажут стартовую фразу в Story/freeplay. Это ожидаемое поведение API, но оно должно быть явно проверено тестом «в каком режиме запускали». `warfare_03` вдобавок не имеет валидного отряда и завершения.

### 3.6. Уникальные NPC и `meet`

`Dialog.npc_id` + `npc_location` лишь **добавляют** `<actor_dialog>` в профиль. Они не заменяют `meet`-диалог и не гарантируют, что уникальный торговец покажет новую ветку. Для `zat_a2_stalker_barmen` (`story_05`) и `cit_killers_merc_trader_stalker` (`story_07`) это вероятная причина отсутствия стартовой фразы. `story_05` дополнительно мог получить «залипший» `taken_info` в старом сохранении: `DontHasInfo(INFO_STARTED)` тогда блокирует диалог навсегда.

**Правило:** для уникальных `meet`-торговцев нужен отдельный тест на чистом сохранении; если диалог не появляется — использовать неуникального NPC, патчить `meet` или добавлять ветку в существующий `meet`-диалог, а не только `actor_dialog`.

---

## 4. Пакет валидации `src/validation/`

### 4.1. Структура

```text
src/validation/
    __init__.py
    report.py
    catalog_validator.py
    graph_validator.py
    xray_linter.py
```

Пакет не читает `_unpacked/` и не пишет в `examples/`. Он работает с `ModProject`, `GameDatabase` и, при необходимости, с уже собранными индексами.

### 4.2. `report.py` — единый формат результата

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Iterable


class Severity(IntEnum):
    INFO = 10
    WARNING = 20
    ERROR = 30


@dataclass(frozen=True)
class ValidationIssue:
    code: str                 # "CAT-NPC-001"
    severity: Severity
    target_id: str            # "story_08.dialog_witness"
    message: str              # человекочитаемо, без путей к _unpacked
    hint: str = ""            # как исправить
    owner: str = ""           # "quest", "dialog", "stage", "squad"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    def add(self, code: str, severity: Severity, target_id: str,
            message: str, hint: str = "", owner: str = "",
            **details: Any) -> None: ...

    def extend(self, issues: Iterable[ValidationIssue]) -> None: ...
    @property
    def errors(self) -> list[ValidationIssue]: ...
    @property
    def warnings(self) -> list[ValidationIssue]: ...
    @property
    def has_errors(self) -> bool: ...
    def sorted(self) -> list[ValidationIssue]: ...
    def to_dict(self) -> dict[str, Any]: ...
    def to_json(self, *, indent: int = 2) -> str: ...
    def to_text(self) -> str: ...
    def raise_if_errors(self) -> None: ...
```

Требования:

- Код стабилен и не зависит от языка сообщения: `CAT-*`, `GRAPH-*`, `XRAY-*`.
- Сортировка: severity desc, code, target_id; вывод детерминирован.
- Дедупликация по `(code, target_id, message)`.
- `to_dict()` содержит `summary: {errors, warnings, info, total}` и `issues: [...]`.
- `ValidationReport` не бросает исключений в валидаторах; `raise_if_errors()` вызывает только CLI/CI.

### 4.3. `catalog_validator.py` — проверка ассетов по БД

Класс:

```python
class CatalogValidator:
    def __init__(self, db: GameDatabase, report: ValidationReport): ...
    def validate(self, project: ModProject) -> None: ...
```

Проверки:

| Код | Проверка | Severity |
|---|---|---|
| `CAT-NPC-001` | `Quest.npc_id`/`Dialog.npc_id` не найден как `<specific_character id>` | ERROR |
| `CAT-NPC-002` | `npc_id` задан, но `npc_location` пуст | ERROR |
| `CAT-NPC-003` | `<specific_character>` найден более одного раза | ERROR |
| `CAT-NPC-004` | `npc_location` не соответствует файлу/локации профиля | WARNING |
| `CAT-SMART-001` | `smart_alias`/`target_alias`/`target_smart` не найден | ERROR |
| `CAT-SMART-002` | `Stage.target_alias` указывает на NPC, а не на смарт | ERROR |
| `CAT-SMART-003` | `SpawnSquad.smart_alias` равен смарту квестодателя | ERROR |
| `CAT-ITEM-001` | `item_alias` не найден в БД/алиасах | ERROR |
| `CAT-SQUAD-001` | `squad_alias` не найден ни в `project.squads`, ни в БД | ERROR |
| `CAT-SQUAD-002` | `CustomSquad.story_id` отсутствует, но отряд адресуется `RemoveSquad`, `SpawnNpcItem` или `target_squad_id` | ERROR |
| `CAT-SQUAD-003` | У `CustomSquad` пусты и `npc`, и `npc_random` | ERROR |
| `CAT-SQUAD-004` | `CustomSquad.npc`/`npc_random` содержит несуществующую NPC-секцию | ERROR |
| `CAT-SQUAD-005` | `npc_in_squad` больше числа шаблонов или `min > max` | WARNING |
| `CAT-SQUAD-006` | `CustomSquad.faction` не совпадает с фракцией шаблонов | WARNING |
| `CAT-WARFARE-001` | `WarfareCapture.enemy_squad_alias` — не отряд (например, NPC-секция) | ERROR |
| `CAT-WARFARE-002` | `WarfareCapture.ally_squad_alias` — не отряд или `ally_count > 0` без алиаса | ERROR |
| `CAT-WARFARE-003` | `SpawnSquad(mode="warfare").squad_alias` не найден в БД | ERROR |
| `CAT-FACTION-001` | `requires_faction`/`faction` — неизвестная фракция | WARNING |
| `CAT-DIALOG-001` | `Dialog.task_id`/`Quest.dialog_id`/`dialog_ids` ссылаются на отсутствующий ID | ERROR |
| `CAT-LOC-001` | `npc_location` не совпадает с локацией смарта/профиля | WARNING |

Детали:

- Резолверы: `resolve_npc(alias_or_id, location)`, `resolve_smart(name)`, `resolve_item(alias)`, `resolve_squad(alias)`, `resolve_faction(name)`.
- Для NPC проверять именно `specific_character`, а не просто наличие алиаса; `esc_2_12_stalker_trader` — положительный пример, `esc_m_trader` — отрицательный.
- Для отрядов различать:
  - `project.squads` (CustomSquad) — допустим для `mode="story"` и `WarfareCapture` только после проверки семантики;
  - игровой ID/алиас отряда БД — допустим для `mode="warfare"`/`WarfareCapture`;
  - NPC-секция (`sim_default_*`) — **не** допустима как `squad_alias`/`ally_squad_alias`.
- Для `SpawnNpcItem.target_alias`:
  - NPC story-ID или числовой server ID — OK;
  - `CustomSquad.id`/`story_id` — OK, но `story_id` обязателен;
  - NPC-секция — ERROR;
  - отряд без `story_id` — ERROR `CAT-SQUAD-002`.

### 4.4. `graph_validator.py` — PK/FK и логический граф

Класс:

```python
class GraphValidator:
    def __init__(self, report: ValidationReport): ...
    def validate(self, project: ModProject) -> GraphIndex: ...
```

`GraphIndex` собирает:

- узлы: `Quest`, `Dialog`, `Phrase`, `Stage`, `CustomSquad`, info, item, money, faction;
- рёбра: `GiveTask`, `CompleteTask`, `next_phrases`, `transfer_conditions`, `extra_condlists`, `return_to_giver_stage`, `warfare_capture`, `target_squad_id`, `on_complete_actions`, `on_fail_actions`, `on_start_actions`, `cleanup_infos`, `death_infos`, `HasInfo`/`DontHasInfo`, `HasItem`/`HasMoney`, `GiveInfo`/`RemoveInfo`, `GiveItem`/`RemoveItem`/`TakeItem`, `GiveMoney`/`TakeMoney`.

Проверки:

| Код | Проверка | Severity |
|---|---|---|
| `GRAPH-INFO-001` | **Сиротский `HasInfo`/`DontHasInfo`:** info требуется, но нигде не выдаётся (с учётом `GiveInfo`, `taken_info`, `complete_info`, `death_infos`, `done_info`; внешние info — allowlist) | WARNING/ERROR |
| `GRAPH-INFO-002` | **Мёртвый `GiveInfo`/`death_infos`:** info выдаётся, но нигде не читается и не снимается | INFO/WARNING |
| `GRAPH-INFO-003` | `death_infos` отряда не используется ни в `QuestCondlist`, ни в `transfer_conditions` | WARNING |
| `GRAPH-ROOT-001` | **Корневое предусловие невыполнимо:** take-диалог требует `HasInfo` своего `complete_info`/`death_info`, `HasItem` награды, info, выдаваемый только позже | ERROR |
| `GRAPH-CONTRADICTION-001` | В одной конъюнкции одновременно `HasInfo(x)` и `DontHasInfo(x)` | ERROR |
| `GRAPH-ITEM-001` | **`RemoveItem`/`TakeItem` без `HasItem`** в той же реплике/диалоге | WARNING |
| `GRAPH-MONEY-001` | **`TakeMoney` без `HasMoney`** | WARNING |
| `GRAPH-ITEM-002` | `RemoveItem`/`TakeItem` с `count`, превышающим требуемый `HasItem.count` | WARNING |
| `GRAPH-QUEST-001` | **Недостижимый квест:** нет входящего `GiveTask`, нет take-диалога/`npc_id`, нет внешнего старта | ERROR |
| `GRAPH-QUEST-002` | **Цикл зависимостей квестов** через `GiveTask`/`on_complete_actions` | ERROR |
| `GRAPH-STAGE-001` | **Залипший этап:** не-финальный этап без `transfer_conditions`, `target_squad_id`, `warfare_capture`, `extra_condlists`, `return_to_giver_stage` и без `CompleteTask`-пути | ERROR |
| `GRAPH-STAGE-002` | Финальный этап без completion-пути (`CompleteTask`, `return_to_giver_stage`, `extra_condlists`, `warfare_capture`) | ERROR |
| `GRAPH-STAGE-003` | `transfer_conditions`/`return_to_giver_stage` ссылается на несуществующий этап | ERROR |
| `GRAPH-STAGE-004` | `transfer_conditions` на последнем этапе завершает квест раньше диалога/награды | WARNING/ERROR |
| `GRAPH-EDGE-001` | **Целостность рёбер:** `GiveTask`/`CompleteTask`/`task_id`/`dialog_id(s)`/`next_phrases`/`stage_complete`/финальный этап | ERROR |
| `GRAPH-REWARD-001` | `CompleteTask` + `GiveMoney`/`GiveItem` при пустых `Quest.reward_*` | **ERROR** |
| `GRAPH-REWARD-002` | Дублирование награды: `reward_*` + `on_complete_actions`/диалог с тем же `GiveMoney`/`GiveItem` | WARNING/ERROR |
| `GRAPH-REWARD-003` | `complete_info` выдан и вручную, и через `_reward` | WARNING |
| `GRAPH-CLEAN-001` | Квестовый предмет выдан игроку, но не изымается в `on_fail_actions`; повторное взятие сразу завершит этап | ERROR |
| `GRAPH-CLEAN-002` | Временный `GiveInfo` из `Stage.on_start_actions` не попадает в `cleanup_infos` (если генератор не добавил автоматически) | WARNING |
| `GRAPH-CLEAN-003` | `cleanup_infos` содержит `taken_info`/`complete_info` | WARNING |
| `GRAPH-DEATH-001` | Завершение по `death_infos`, но нет `SpawnSquad`/`story_id`, который может выдать этот info | ERROR |
| `GRAPH-CYCLE-001` | Цикл `next_phrases` без изменения состояния/действия | WARNING |

**Edge export.** `GraphIndex.export_edges(path)` пишет JSON и/или DOT:

```json
{
  "nodes": [{"id": "story_02_retrieve_data", "type": "quest"}],
  "edges": [
    {"source": "story_02_take", "target": "story_02_retrieve_data",
     "kind": "GiveTask", "owner": "phrase:2"}
  ]
}
```

Экспорт нужен для отладки «залипших» этапов и циклов; он не является обязательным артефактом сборки.

### 4.5. `xray_linter.py` — правила рантайма X-Ray/Anomaly

Класс:

```python
class XrayLinter:
    def __init__(self, db: GameDatabase, report: ValidationReport): ...
    def validate(self, project: ModProject) -> None: ...
```

Проверки:

| Код | Проверка | Severity |
|---|---|---|
| `XRAY-SPAWN-001` | **Враг спавнится на смарте квестодателя:** `SpawnSquad` или `WarfareCapture` с `relationship="enemy"` совпадает со смартом `npc_id` | ERROR |
| `XRAY-SPAWN-002` | `SpawnSquad.smart_alias == CustomSquad.target_smart`: отряд не идёт к цели, а появляется на ней | WARNING |
| `XRAY-SPAWN-003` | `relationship="enemy"` и спавн на смарте, где стоит квестодатель/база | ERROR |
| `XRAY-MEET-001` | **Уникальный `meet`/торговец:** `Dialog.npc_id` привязан к уникальному NPC с `meet`-диалогом; `actor_dialog` может не появиться | WARNING/ERROR |
| `XRAY-MEET-002` | `npc_id` без `npc_location` или неоднозначная привязка | ERROR |
| `XRAY-SPAWNITEM-001` | **`SpawnNpcItem` раньше `SpawnSquad`** в том же списке действий | ERROR |
| `XRAY-SPAWNITEM-002` | **`SpawnNpcItem.target_alias` не является `CustomSquad` с `story_id`** | ERROR |
| `XRAY-SPAWNITEM-003` | `SpawnNpcItem` в этапе, который не спавнит отряд | WARNING |
| `XRAY-CLEAN-001` | **Утечка предмета/поршня:** квестовый предмет выдан игроку, но не удаляется при провале; временный info не снят | ERROR/WARNING |
| `XRAY-CLEAN-002` | `cleanup_infos` содержит `taken_info`/`complete_info` или неизвестный info | WARNING |
| `XRAY-CLEAN-003` | `on_fail_actions` удаляет отряд без `story_id` | ERROR |
| `XRAY-NAME-001` | **Коллизии имён:** одинаковые ID у quest/dialog/info/squad; дубли `story_id`; повторное использование ID | ERROR |
| `XRAY-NAME-002` | Невалидный Lua-идентификатор, зарезервированное слово, пробелы/`[]=`/переводы строк | ERROR |
| `XRAY-NAME-003` | `Quest.stages`/`Dialog.phrases` ключи не совпадают с `id`; нет `phrase id=0`; `next_phrases` наружу | ERROR |
| `XRAY-REWARD-001` | **Дублирование награды** в `reward_*`, `on_complete_actions` и реплике | WARNING/ERROR |
| `XRAY-REWARD-002` | `GiveMoney`/`GiveItem` рядом с `CompleteTask` при пустых `reward_*` | **ERROR** |
| `XRAY-REWARD-003` | `CompleteTask` в take-реплике или `GiveTask` в turnin-реплике | ERROR |
| `XRAY-MODE-001` | **Смешение режимов:** `WarfareCapture` + `SpawnSquad(mode="story")` в одном квесте | ERROR |
| `XRAY-MODE-002` | `requires_warfare=True` + Story-спавн/Story-квест | ERROR/WARNING |
| `XRAY-MODE-003` | `SpawnSquad(mode="warfare")` без `requires_warfare`/`WarfareCapture` | WARNING |
| `XRAY-WARFARE-001` | `WarfareCapture.enemy_squad_alias`/`ally_squad_alias` — NPC-секция, а не отряд | ERROR |
| `XRAY-WARFARE-002` | Один и тот же enemy-отряд на нескольких этапах без подтверждения респавна | WARNING |
| `XRAY-WARFARE-003` | `SmartOwner`/`HasMoney`/сырой dict в `extra_condlists` | ERROR |
| `XRAY-WARFARE-004` | `requires_warfare=True` без `WarfareCapture` и без валидного completion-пути | WARNING |
| `XRAY-LOC-001` | **Локализация:** пустые `text_ru`/`text_en`, `title_ru/en`, `descr_ru/en`, `msg_*`; битые placeholder'ы | WARNING/ERROR |
| `XRAY-LOC-002` | Нарушен порядок говорящих: чётные ID — игрок, нечётные — NPC; `next_phrases` ведёт на неверную чётность | WARNING |
| `XRAY-LOC-003` | В тексте есть неэкранированные `&`, `<`, `>` или управляющие символы; дубли text-ID | WARNING |
| `XRAY-DIALOG-001` | Несколько `take` на один квест; `turnin` раньше `take`; `take` без `DontHasInfo(taken_info)`; `turnin` без `HasInfo(complete_info)`/stage-гейта | WARNING/ERROR |
| `XRAY-SAVE-001` | Повторное взятие после успеха/провала: `taken_info` остаётся, `complete_info` не снимается, `cleanup_infos` не покрывает временные info | WARNING |
| `XRAY-SQUAD-001` | `npc_in_squad` больше числа шаблонов; `npc`/`npc_random` пусты; фракция не совпадает | WARNING |
| `XRAY-CONDLIST-001` | `extra_condlists` не `QuestCondlist`; неподдерживаемое условие; неверная нумерация `condlist_N` | ERROR |

**Список уникальных `meet`-торговцев** должен быть data-driven: строиться по `character_desc_*.xml`/БД, а не хардкодиться. В качестве примеров для тестов: `esc_m_trader` (в 1.5.3 отсутствует), `esc_2_12_stalker_nimble`, `esc_2_12_stalker_trader`, `zat_a2_stalker_barmen`, `cit_killers_merc_trader_stalker`.

### 4.6. Пайплайн и интеграция

```python
from src.validation.report import ValidationReport
from src.validation.catalog_validator import CatalogValidator
from src.validation.graph_validator import GraphValidator
from src.validation.xray_linter import XrayLinter


def validate_project(project, db, *, strict: bool = False) -> ValidationReport:
    report = ValidationReport()
    CatalogValidator(db, report).validate(project)
    GraphValidator(report).validate(project)
    XrayLinter(db, report).validate(project)
    if strict and report.warnings:
        report.raise_if_errors()  # либо отдельный exit code 2
    if report.has_errors:
        report.raise_if_errors()
    return report
```

Интеграция:

- Вызывать **до** `ModBuilder.build_project`; при `ERROR` сборку не запускать.
- CLI: `venv\Scripts\python.exe main.py validate <script.py> --json report.json --strict`.
- В `ProjectValidator` оставить runtime-проверки ассетов, но новые модули должны выполняться раньше и покрывать то, что сейчас в `TODO`.
- `logs/app.log` не парсить; источник — модели и БД.
- Не читать `_unpacked/`; для `meet`-профилей использовать только разрешённые БД/индексы.

### 4.7. Матрица «проверка → сценарий Phase 3»

| Проверка | Что ловит в Phase 3 |
|---|---|
| `CAT-NPC-001` | `story_03`, `story_04`, `story_06`, `story_08` |
| `CAT-SMART-001` | `story_08` (`garb_smart_terrain_1_6`) |
| `CAT-SMART-003` / `XRAY-SPAWN-001` | `story_01`, `story_03` |
| `CAT-SQUAD-001/002` | `story_02`, `story_07`, `warfare_03` |
| `CAT-WARFARE-001/002` | `warfare_01`, `warfare_02`, `warfare_04` |
| `GRAPH-INFO-001` | `story_05` (`INFO_INTEL_FOUND`) |
| `GRAPH-STAGE-001/002` | `story_02` (финальный этап), `story_04` (преждевременное завершение) |
| `GRAPH-REWARD-001` | `story_08`, `story_04` |
| `GRAPH-CLEAN-001` | `story_02` (ПДА не изымается при провале) |
| `GRAPH-DEATH-001` | `story_07` (завершение зависит от неспавненного отряда) |
| `XRAY-MEET-001` | `story_05`, `story_07` (вероятно) |
| `XRAY-MODE-001/002` | `warfare_01`, `warfare_02`, `warfare_04` |
| `XRAY-WARFARE-003` / `XRAY-CONDLIST-001` | `warfare_03` |
| `XRAY-LOC-001/002` | все Story-сценарии; особенно `story_04`, `story_08` с ветвлением |

---

## 5. Предложения по ядру и API

### 5.1. `ClearSmart` — новая операция

**Проблема.** Story-отряд спавнится на смарте, где уже могут стоять ванильные отряды, сталкеры квестодателя или база. Это даёт мгновенный бой, офлайн-бой, отсутствие слота спавна или гибель квестодателя. В `story_01` и `story_03` враг появляется прямо на смарте квестодателя; в `story_07` — на `cit_bandits`, который может быть занят.

**Предложение A — отдельное действие:**

```python
class ClearSmart(BaseAction):
    type: Literal["clear_smart"] = "clear_smart"
    smart_alias: str
    faction: str | None = None           # чистить только эту фракцию
    keep_story_ids: list[str] = []       # не трогать эти Story-отряды
    radius: float | None = None          # ограничить радиус
    allow_giver_smart: bool = False      # защита от очистки смарта квестодателя
```

Семантика:

1. Резолвит смарт; если не найден — `BuildError`/`ERROR`.
2. Идёт по `SIMBOARD.squads`/`alife()` и удаляет отряды на смарте:
   - пропускает актора, компаньонов, `keep_story_ids`, отряды текущего квеста;
   - если задан `faction`, удаляет только эту фракцию;
   - не удаляет уникальных NPC/сюжетных персонажей;
   - снимает записи из `sim_offline_combat.task_squads`.
3. Не меняет владельца смарта по умолчанию; для Warfare-захвата владелец меняется отдельно через `WarfareCapture`.
4. Идемпотентен: повторный вызов — no-op; факт очистки можно хранить в pstor.
5. Логирует `smart`, `removed_count`, `kept_story_ids`, `faction`.
6. Запрещён в одном квесте с `WarfareCapture`; только Story.
7. Если `smart_alias` совпадает со смартом квестодателя, требуется явный `allow_giver_smart=True`; иначе `ERROR`.

**Предложение B — флаг у спавна:**

```python
SpawnSquad(
    squad_alias=SQUAD_ID,
    smart_alias=SPAWN_SMART,
    mode="story",
    clear_smart=True,
    clear_faction="bandit",     # опционально
    clear_keep_story_ids=[],    # опционально
)
```

Плюсы: не нужно добавлять отдельное действие в каждый `on_start_actions`; минусы: неявная побочная операция. Для читаемости лучше `ClearSmart` отдельным действием **непосредственно перед** `SpawnSquad`; `clear_smart=True` оставить как сахар.

**Правила порядка:**

```python
on_start_actions=[
    ClearSmart(smart_alias=SPAWN_SMART, faction="bandit"),
    SpawnSquad(squad_alias=SQUAD_ID, smart_alias=SPAWN_SMART, mode="story"),
    SpawnNpcItem(item_alias=ITEM, target_alias=SQUAD_ID, count=1),
]
```

`ClearSmart` обязан идти до `SpawnSquad`; `SpawnNpcItem` — после `SpawnSquad`; `story_id` у отряда обязателен.

### 5.2. Исправления `docs/API_v2.md`

| Раздел | Текущая проблема | Предлагаемая правка |
|---|---|---|
| `target_alias` / `SpawnSquad.smart_alias` / `CustomSquad.target_smart` | Три разных поля описаны в разных местах; примеры Phase 3 трактуют их как одно. Читатель думает, что `target_alias` задаёт точку спавна. | Добавить явную таблицу «маркер / спавн / назначение» и пример: спавн на `zat_b7`, `target_smart=zat_b52`, `target_alias=zat_b7` для маркера. Добавить предупреждение: «враг не должен спавниться на смарте квестодателя». |
| `giver_npc_id` | Сказано «устаревшее имя, используется если `npc_id` не задан», но ниже: «если `giver_npc_id` не задан, `condlist_0` не создаётся». Это противоречит случаю, когда задан только `npc_id`. | Явно указать эффективного квестодателя: `giver_npc_id or npc_id`; `condlist_0` создаётся, если эффективный giver задан и `fail_on_giver_death=True`. `Dialog.npc_id` имеет приоритет для привязки. |
| `SpawnNpcItem.target_alias` | Не сказано, что для `CustomSquad` нужен `story_id`, и что действие должно идти после `SpawnSquad`. | Добавить: «Для отряда принимается `CustomSquad.id`/`story_id`; без `story_id` командир не гарантирован. Вызывайте после `SpawnSquad` в том же списке действий. Если командир не найден — предмет не создаётся». |
| `requires_warfare` | Правило есть, но оно легко теряется среди описания Warfare. Примеры с `requires_warfare=True` выглядят как Story-квесты. | Добавить блок «Если тестируете в Story/freeplay — не ставьте `requires_warfare` и не используйте `WarfareCapture`». Явно: `_can_take` и `_start/_status` гейтятся; `WarfareCapture` включает `world=true`. |
| Награда и `CompleteTask` | Сказано «не поддерживается», но компилятор только предупреждает; `story_04`/`story_08` всё равно доходят до сборки. Читатель может решить, что warning не критичен. | Сделать `GRAPH-REWARD-001`/`XRAY-REWARD-002` ошибкой сборки. Добавить пары «плохо/хорошо»: `CompleteTask` + `GiveMoney` при пустых `reward_*` → потеря; `reward_money`/`on_complete_actions` → норма. |
| `QuestCondlist` | Не сказано, что `extra_condlists` принимает только `QuestCondlist`, а `SmartOwner`/`HasMoney` не поддерживаются. `warfare_03` использует сырой dict и `SmartOwner`. | Добавить пример `QuestCondlist(when=[...], result="complete")` и список запрещённых условий. Указать, что сырой dict даёт `ValidationError`, а `SmartOwner`/`HasMoney` — `BuildError` в Фазе 2. |
| `CustomSquad.story_id` | Назван «необязательным». Для квестовых отрядов это не так. | Пометить: «Обязателен для отрядов, которые адресуются `RemoveSquad`, `SpawnNpcItem` или `Stage.target_squad_id`». Добавить `story_id` в эталонный пример (он там уже есть). |
| Уникальные NPC / `meet` | Сказано, что `npc_id` + `npc_location` добавляет `<actor_dialog>`, но не сказано, что `meet`-диалог уникального торговца может перекрыть ветку. | Добавить раздел «Уникальные торговцы и `meet`»: `actor_dialog` не заменяет `meet`; для `zat_a2_stalker_barmen`, `cit_killers_merc_trader_stalker`, `esc_2_12_stalker_nimble` нужен отдельный тест/патч `meet`; при проблеме использовать неуникального NPC. |
| `npc_in_squad` | Не сказано, что количество может превышать число шаблонов и как движок это трактует. | Уточнить семантику `[min, max]`; добавить предупреждение, если `max` больше числа `npc`/`npc_random`; рекомендовать явные шаблоны. |
| Ассеты отрядов | В примерах фигурирует `squad.mercenary_advanced`, которого нет в БД; `sim_default_stalker_1` используется как ally. | Заменить примеры на проверенные `squad.killer_advanced`/`merc_sim_squad_advanced` и `squad.army_advanced`/`army_sim_squad_advanced`. Добавить правило: `ally_squad_alias` — только отряд, не NPC. |
| Предварительная валидация | API говорит «алиасы должны существовать», но сборщик падает только на `<specific_character>`; смарты/предметы/отряды проверяются слабо. | Добавить раздел «Pre-build validation»: `CatalogValidator` обязателен; `ERROR` блокирует сборку; `WARNING` показывает отчёт. |

---

## 6. Критерии приёмки

1. **Синтаксис/модели.** Все 12 файлов Phase 3 проходят `compile()`; 11 проходят модели; `warfare_03` даёт ожидаемый `ValidationError` с понятным сообщением о `QuestCondlist`, а не сырой stack trace.
2. **Ассеты.** `CatalogValidator` находит:
   - `esc_m_trader`, `esc_2_12_stalker_rookie`, `zat_a2_stalker_leader_freedom`, `garb_bandit_boss_sultan`;
   - `garb_smart_terrain_1_6`;
   - `squad.mercenary_advanced`;
   - `sim_default_stalker_1` как NPC в роли отряда.
3. **Граф.** `GraphValidator` находит:
   - `story_02`: нет completion-пути и нет `CompleteTask`;
   - `story_04`: `transfer_conditions` завершает последний этап до диалога;
   - `story_05`: `INFO_INTEL_FOUND` — сирота;
   - `story_08`: `CompleteTask` + награда при пустых `reward_*`;
   - `story_02`: предмет не изымается при провале;
   - `story_07`: completion зависит от `death_infos` без гарантии спавна.
4. **X-Ray linter.** Находит:
   - `story_01`, `story_03`: враг на смарте квестодателя;
   - `story_02`, `story_07`: Story-отряд без `story_id`;
   - `story_05`, `story_07`: уникальный `meet`-торговец (WARNING с ручной проверкой);
   - `warfare_01`, `warfare_02`, `warfare_04`: `requires_warfare` + неверные enemy/ally;
   - `warfare_03`: смешение/неподдерживаемый `SmartOwner`;
   - коллизии имён и локализационные пропуски.
5. **Эталоны.** `build_story_relay.py` и `build_golden_test.py` проходят без `ERROR`; допускаются только обоснованные `WARNING` (например, `npc_in_squad`).
6. **Детерминизм.** Один и тот же проект даёт одинаковый JSON-отчёт; коды не меняются при изменении текста сообщений.
7. **Безопасность.** Пакет не читает `_unpacked/`, не пишет в `examples/`, не создаёт `__pycache__` в `examples/`.
8. **CLI/CI.** `main.py validate --strict` возвращает:
   - `0` — нет ошибок;
   - `1` — есть `ERROR`;
   - `2` — только `WARNING` при `--strict`.
9. **Регрессия.** После исправления `story_03`, `story_04`, `story_06`, `story_08` сборка должна доходить до записи файлов; после исправления `warfare_03` — до `BuildError`/успеха без `ValidationError`.
10. **Runtime-тест.** Для `story_05` и `story_07` — отдельный чек-лист на чистом сохранении: проверить `meet`, `actor_dialog`, `get_story_squad`, `death_infos`, `spawn` в `SIMBOARD`.

---

## 7. Приложение: точные фрагменты лога

### 7.1. `BuildError`

```text
2026-11-18 19:31:00,693 | ERROR | aqb.compiler.builder | Сборка невозможна: ...
Story 03: Sidorovich Chain: <specific_character id="esc_m_trader"> не найден в character_desc_*.xml.
2026-11-18 19:31:20,256 | ERROR | aqb.compiler.builder | ...
Story 04: Branching Rewards: <specific_character id="esc_m_trader"> не найден в character_desc_*.xml.
2026-11-18 19:31:32,055 | ERROR | aqb.compiler.builder | ...
Story 06: Freedom Duty: <specific_character id="zat_a2_stalker_leader_freedom"> не найден в character_desc_*.xml.
2026-11-18 19:31:37,019 | ERROR | aqb.compiler.builder | ...
Story 08: The Detective: <specific_character id="esc_2_12_stalker_rookie"> не найден в character_desc_*.xml.
```

### 7.2. Предупреждения о награде

```text
2026-11-18 19:31:20,245 | WARNING | aqb.compiler.builder |
диалог 'story_04_turnin', реплика 2: GiveMoney вместе с CompleteTask,
а Quest.reward_money/reward_item_alias пусты.
2026-11-18 19:31:20,246 | WARNING | aqb.compiler.builder |
диалог 'story_04_turnin', реплика 4: GiveItem вместе с CompleteTask,
а Quest.reward_money/reward_item_alias пусты.
2026-11-18 19:31:37,003 | WARNING | aqb.compiler.builder |
диалог 'story_08_wolf_turnin', реплика 2: GiveMoney вместе с CompleteTask,
а Quest.reward_money/reward_item_alias пусты.
2026-11-18 19:31:37,004 | WARNING | aqb.compiler.builder |
диалог 'story_08_wolf_turnin', реплика 4: GiveItem, GiveMoney вместе с CompleteTask,
а Quest.reward_money/reward_item_alias пусты.
```

### 7.3. Успешные сборки

| Файл | Время | Файлов |
|---|---|---:|
| `story_01` | 19:10:23 | 8 |
| `story_02` | 19:30:56 | 8 |
| `story_05` | 19:31:28 | 7 |
| `story_07` | 19:31:34 | 8 |
| `warfare_01` | 19:31:51 | 7 |
| `warfare_02` | 19:31:55 | 7 |
| `warfare_04` | 19:32:02 | 7 |

Успешная сборка **не означает** корректный runtime: `story_05` и `story_07` имеют runtime-симптомы, а `warfare_01/02/04` требуют Warfare-режима.

---

## 8. Итоговая формулировка для отчёта

> Основная масса отказов Phase 3 — не синтаксис и не Pydantic, а отсутствие предполётной проверки ассетов и логического графа. Четыре сценария падают на несуществующих `<specific_character>`, ещё два NPC и один смарт скрыты за первым падением. Успешно собранные сценарии ломаются семантически: враг спавнится на смарте квестодателя, Story-отряд не имеет `story_id`, финальный этап не имеет completion-пути, награда стоит рядом с `CompleteTask` при пустых `reward_*`, а `TargetVariant` читает info, которое никто не выдаёт. Для Warfare-сценариев добавляются режимный гейт `requires_warfare` и неверные алиасы отрядов. Исправление — не правка каждого файла вручную, а пакет `src/validation/` из четырёх модулей, который блокирует сборку до записи файлов.
