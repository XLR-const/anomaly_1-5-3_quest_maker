# GOLDEN DIFF AUDIT v3 — финальный контрольный аудит авто-слепка `golden_shield_test`

> **Объект аудита:** `tools/manual_mod_snapshot_golden_shield_test.txt` (актуальный авто-слепок
> после всех правок) и `tools/standart_manual_mod_snapshot.txt` (ручной рабочий эталон «M»).
> **База:** `docs/GOLDEN_DIFF_AUDIT_v2.md`. **Контракты:** `docs/API_v2.md`, `docs/RULE.md`.
> **Дата:** 2026-11-15. **Режим:** read-only. Каталоги `_unpacked/`, `output/`, `src/`, `tests/`
> не открывались и не сканировались; код проекта не изменялся. Создан только этот файл.
>
> **Методика.** Построчное сравнение трёх слепков; проверка XML-структуры диалогов
> (количество `<action>` на `<phrase>`, порядок тегов, кросс-ссылки `dialogs.*`);
> сверка LTX/локализации/`system.ltx`/`character_desc_escape.xml`; трассировка Lua-логики
> `give_task`, `*_target`, `freeze_squad`, гейтов, очистки поршней и отрядов; сверка
> заявленных контрактов с `docs/API_v2.md` и `docs/RULE.md`.
>
> **Границы:** это статический дифф-аудит. Динамические проверки V13–V20 (прогон в игре)
> не выполнялись; выводы основаны на коде слепка и документации.

---

## 1. Краткое резюме и общий вердикт

**Вердикт одной строкой:** авто-слепок закрывает практически весь P0/P1-бэклог v2
(дубль `<action>`, резолв story-ID, `giver_id = 0`, награда Q1, Warfare/army-гейты,
`freeze_squad`, `squad_descr`, учёт динамических отрядов, `_msg_reward`/`_msg_fail`,
повторная выдача ПДА), но содержит **один реальный блокер** — утечку поршней
`mymod_av_quest_ready` / `mymod_atp_quest_ready` при провале/отмене в сочетании с
нестадийной проверкой `_can_turn_in`. После отмены и повторного взятия квеста сдача
открывается сразу, что позволяет пропустить этапы и получить награду.

**Общий вердикт: НЕ ГОТОВО К PHASE 2 — 1 блокер (`FAIL-1`).**

### 1.1. Блокеры

| ID | Блокер | Кратко |
|---|---|---|
| **FAIL-1** | Утечка `*_ready` при `on_fail`/`on_cancel` + `_can_turn_in` не проверяет стадию | После отмены Q1 на этапе 2 и повторного взятия диалог сдачи доступен сразу; одно нажатие завершает Q1 и выдаёт 10 000 ₽ + `wpn_vssk`. Для Q2 — аналогично при наличии любого `itm_pda_common`. |

### 1.2. Что закрыто (кратко)

- В `dialogs_golden_shield_test.xml` **нет ни одной** реплики с более чем одним `<action>`.
- Q1-награда живёт в `_reward`: `money = 10000`, `item = "wpn_vssk"`.
- `give_task` использует `dialogs.who_is_npc(actor, npc)` и `get_story_object_id`; строки
  `giver_id = 0` и `alife():story_object(<имя>)` отсутствуют.
- `*_target` проверяет `tsk.task_giver_id ~= 0` и имеет fallback на `Quest.npc`.
- `freeze_squad` замораживает только `squad.current_action == 1`.
- Гейты `requires_faction = "army"` и `requires_warfare = true` реально проверяются в
  `*_can_take`.
- `squad_descr_golden_shield_test.ltx` существует и содержит нужную секцию.
- `_dyn_squad_cnt` **не** сбрасывается в `mymod_atp_quest_start`; сброс стоит в
  `_reward`/`_cleanup` строго после `unmark_quest_squads`.
- В `fail_actions` Q2 есть изъятие `itm_pda_common` (`take_item`, `count = 1`).
- В `st_*.xml` (rus/eng) есть `_msg_start`, `_msg_reward`, `_msg_fail` и все
  `_stage_<n>_msg`.
- ПДА Q2 выдаётся идемпотентно на каждом тике этапа 1, если его нет в инвентаре.

### 1.3. Цифры

| Метрика | Эталон «M» | Авто-слепок v3 |
|---|---|---|
| Файлов в слепке | 8 | **8** (добавлен `squad_descr_*`) |
| Квестов / этапов | 2 / 3+3 | 2 / 3+2 |
| Реплик с `>1` `<action>` | 0 | **0** |
| `giver_id = 0` | 0 | **0** |
| `alife():story_object(<имя>)` | 0 | **0** |
| Проверок `army` в диалогах | 2 | **4** (все take/turnin-функции) |
| Проверок `IsWarfare()` в диалогах | 2 | **4** |
| Поршней `*_ready`, не снимаемых при cleanup | 0 | **2** (`FAIL-1`) |

---

## 2. Сводная таблица статусов

### 2.1. Проверенные узлы

| # | Узел / проверка | Статус | Доказательство в авто-слепке |
|---|---|---|---|
| 1 | `system.ltx`: `dialogs_golden_shield_test` в `[dialogs] files` ровно 1 раз | **PASS** | строка 97, других вхождений нет |
| 2 | `system.ltx`: `character_desc_escape` в `[profiles] specific_characters_files` ровно 1 раз | **PASS** | строка 104 |
| 3 | `system.ltx`: глоб `squad_descr_*.ltx` подключён | **PASS** | строка 26 `#include "misc\squad_descr\squad_descr.ltx"` |
| 4 | `character_desc_escape.xml`: 5 диалогов у `esc_3_16_military_trader`, без дублей | **PASS** | строки 1713–1717, 5 уникальных `<actor_dialog>` |
| 5 | Порядок диалогов `take → take_assault → take_solo → turnin` | **PASS** | 1713 `av_take` → 1714 `atp_take_assault` → 1715 `atp_take_solo` → 1716/1717 turnin |
| 6 | Не более 1 `<action>` на `<phrase>` | **PASS** | `<action>` только на 1748, 1767, 1790, 1819, 1850, 1860 — каждая в своей реплике |
| 7 | Порядок тегов в `<phrase>`: `text → next → precondition → has_info → give_info → action` | **PASS** | 1845–1851, 1855–1861; 1786–1791; 1815–1820 |
| 8 | Все `dialogs.*` из XML зарегистрированы в `register()` | **PASS** | 13 уникальных ссылок; все 13 есть в 3792–3842 |
| 9 | `tm_golden_shield_test.ltx`, Q1: `storyline=false`, `prior=60`, иконка `ui_inGame2_Nochnaya_ohota` | **PASS** | 1884–1894 |
| 10 | `tm_golden_shield_test.ltx`, Q2: `storyline=false`, `prior=60`, иконка `ui_inGame2_Osobiy_zakaz` | **PASS** | 1903–1913 |
| 11 | `dont_send_update_news = true` в обеих секциях | **PASS** | 1894, 1913 |
| 12 | `condlist_0 = {!task_giver_alive(<id>)} fail` в обеих секциях | **PASS** | 1901, 1920 |
| 13 | Эффекты LTX в форме `%=...()%` | **PASS** | 1896–1899, 1915–1918 |
| 14 | `stage_complete` Q1 = 3 при трёх этапах | **PASS** | 1893; этапы 0–2 в `QUESTS` 2368–2417 |
| 15 | `stage_complete` Q2 = 2 при двух этапах | **ARCH_DIFF** | 1912; этапы 0–1 в `QUESTS` 2286–2325; `last_stage = 1` (2284) |
| 16 | `squad_descr_golden_shield_test.ltx` и секция `[mymod_atp_bandit_leader_squad]:online_offline_group` | **PASS** | 1876–1878 |
| 17 | `st_*.xml` rus/eng: `_msg_start`, `_msg_reward`, `_msg_fail` | **PASS** | eng 1935–1943, 1977–1985; rus 2091–2099, 2133–2141 |
| 18 | `st_*.xml` rus/eng: `_stage_<n>_msg` для всех этапов | **PASS** | Q1: 1950/1959/1968, 2106/2115/2124; Q2: 1992/2001, 2148/2157 |
| 19 | Q1-награда в `_reward`: 10 000 ₽ + `wpn_vssk` | **PASS** | `money = 10000`, `item = "wpn_vssk"` (2361–2363); выдача 3386–3394 |
| 20 | Q2-награда в реплике сдачи: 15 000 / 30 000 | **ARCH_DIFF** | 3633–3649 (15 000), 3663–3679 (30 000); `money = 0`, `item = ""` (2279–2280) |
| 21 | `_dyn_squad_cnt` не сбрасывается в `mymod_atp_quest_start` | **PASS** | в 3151–3177 и 3357–3383 сброса нет; сброс только на 3199, 3211, 3405, 3417 |
| 22 | Сброс `_dyn_squad_cnt` после `unmark_quest_squads` в Q2 `_reward`/`_cleanup` | **PASS** | 3198→3199; 3210→3211 |
| 23 | Изъятие `itm_pda_common` в `QUESTS["mymod_atp_quest"].fail_actions` | **PASS** | 2328–2334: `kind = "take_item"`, `item = "itm_pda_common"`, `count = 1` |
| 24 | Снятие `mymod_q2_assault` / `mymod_q2_solo` в `_reward` и `_cleanup` | **PASS** | `cleanup_infos` 2268–2271; цикл 3195–3197 и 3216–3218 |
| 25 | `give_task`: `dialogs.who_is_npc(actor, npc)` | **PASS** | 2908; fallback на `npc`/`actor` 2909–2916 |
| 26 | `give_task`: резолв story-ID, отсутствие `giver_id = 0` | **PASS** | 2918–2939; `resolve_target` → `get_story_object_id` 2481–2488 |
| 27 | Отсутствие `alife():story_object(<имя>)` | **PASS** | grep по слепку: только `get_story_object_id` (2481–2488, 2563–2571) |
| 28 | `mymod_av_quest_target`: `tsk.task_giver_id ~= 0` + fallback | **PASS** | 3252–3258; аналогично Q2 3046–3052 |
| 29 | `freeze_squad`: guard `squad.current_action == 1` | **PASS** | 2734–2743 |
| 30 | Гейты `army` и `IsWarfare()` в `*_can_take` | **PASS** | 3444–3451, 3518–3525, 3572–3579, 3686–3693; поля 2274–2275, 2356–2357 |
| 31 | Повторная выдача ПДА Q2 при потере | **PASS** | `item_actions` 2315–2321; цикл `_status` 3091–3097 |
| 32 | `announce` использует сообщение завершённого этапа, а не следующего | **PASS** | 3114–3115, 3320–3321: передаётся `stage_data.msg` текущего этапа |
| 33 | `resolve_target` / `resolve_alife_object`: story-ID по имени | **PASS** | 2472–2491; 2546–2595 (`get_story_object`, `get_story_squad`, `get_story_object_id`) |
| 34 | Учёт динамических отрядов `SpawnSquad`: pstor, заморозка, освобождение | **PASS** | `register_dyn_squad` 2690–2699; `freeze_dyn_squads` 2775–2781; `unmark_quest_squads` 2670–2686; вызов 3494–3511 |
| 35 | Сдача Q1/Q2: гейт по `*_ready` + `_can_turn_in` | **FAIL** | `*_ready` не снимается в `_cleanup`; `return_stage = -1` делает `_can_turn_in` почти безусловной. См. §5 |
| 36 | Кросс-ссылки «без сирот» (V3, обратная сторона) | **PASS** | все XML-ссылки зарегистрированы; 20 «мёртвых» регистраций остались, но это P2, не дефект |

### 2.2. Критерии V1–V12

| Критерий | Статус | Комментарий |
|---|---|---|
| **V1.** Один `<action>` на реплику | **PASS** | 6 тегов `<action>` на 6 разных реплик; 0 нарушений |
| **V2.** Один `<precondition>` на реплику/диалог, порядок тегов | **PASS** | по одному precondition на реплику; порядок канонический (API_v2 §2.2/§3.4) |
| **V3.** Кросс-ссылки XML→Lua | **PASS** | все 13 ссылок существуют; обратные сироты — только «мёртвый код» P2 |
| **V4.** Награда Q1 в `_reward` | **PASS** | `money = 10000`, `item = "wpn_vssk"`, `item_count = 1` |
| **V5.** Нет `giver_id = 0` и `alife():story_object(<имя>)` | **PASS** | обе строки отсутствуют; используется `get_story_object_id` |
| **V6.** Резолв цели с fallback | **PASS** | `task_giver_id ~= 0` → `resolve_target(quest.npc)` → `resolve_alife_object(quest.npc)` |
| **V7.** `stage_complete` | **ARCH_DIFF** | Q1: 3/3 — PASS; Q2: 2 этапа / `stage_complete = 2` — осознанная 2-этапная модель |
| **V8.** `dont_send_update_news` + `condlist_0` | **PASS** | обе секции, значения и форма совпадают |
| **V9.** `squad_descr_*.ltx` | **PASS** | файл и секция присутствуют; глоб `squad_descr.ltx` уже подключён |
| **V10.** `_msg_reward`, `_msg_fail` (и вариативные описания) | **PASS** | оба сообщения есть в rus/eng; вариативные `_descr_assault/solo` заменены общим описанием — см. ARCH_DIFF A3 |
| **V11.** Нет дублей `<actor_dialog>`, порядок ролей | **PASS** | 5 уникальных, порядок соответствует API_v2 §2.5 |
| **V12.** `system.ltx` — ровно один раз | **PASS** | `dialogs_golden_shield_test` — 1; `character_desc_escape` — 1 |

---

## 3. Разбор закрытых проблем `docs/GOLDEN_DIFF_AUDIT_v2.md`

### 3.1. Инцидент 1 v2 — потеря награды Q1 из-за дубля `<action>`

**Закрыто: PASS.**

Причина v2 — второй `<action>` в реплике молча отбрасывался движком. В v3:

1. В `dialogs_golden_shield_test.xml` у каждой реплики ровно один `<action>`:
   Q1-сдача (1765–1768) содержит только `dialogs.mymod_av_quest_turnin_turn_in`;
   Q2-сдача (1845–1851, 1855–1861) — только `..._phrase_2_action` / `..._phrase_4_action`.
2. Q1-награда перенесена в `_reward`:

```lua
		money = 10000,
		item = "wpn_vssk",
		item_count = 1,
```

3. `mymod_av_quest_reward` действительно выдаёт деньги и предмет (3386–3394) и вызывает
   `give_info_portion(complete_info)` (3396–3398).
4. Q2-награда теперь в **одной** Lua-функции вместе с изъятием ПДА и `complete_task`
   (3633–3649 / 3663–3679), поэтому второй тег не нужен и ничего не теряется.

**Остаточный вывод:** инцидент 1 закрыт полностью; Q1-награда гарантированно в `_reward`,
Q2-награда — в единственном `<action>` (ARCH_DIFF A2).

### 3.2. Инцидент 2 v2 — жёлтая метка на игроке вместо Журова

**Закрыто: PASS.**

В v3 `give_task` (2900–2940) сначала нормализует говорящего:

```lua
	local giver = (dialogs and dialogs.who_is_npc and dialogs.who_is_npc(actor, npc)) or nil
```

затем берёт id только если он ненулевой:

```lua
	local giver_id = nil
	if giver and giver.id then
		local id = giver:id()
		if id and id ~= 0 then
			giver_id = id
		end
	end
```

и только после этого использует fallback:

```lua
	if not giver_id then
		local quest = QUESTS[task_id]
		if quest and quest.npc ~= "" then
			giver_id = resolve_target(quest.npc)
			if not giver_id then
				local obj = resolve_alife_object(quest.npc)
				if obj and obj.id and obj.id ~= 0 then
					giver_id = obj.id
				end
			end
		end
	end
```

`resolve_target` резолвит имя через `get_story_object_id` (2481–2488), а не через
`alife():story_object(<строка>)`. `mymod_av_quest_target` и `mymod_atp_quest_target`
проверяют `tsk.task_giver_id ~= 0` (3252, 3046) и имеют fallback на `Quest.npc`.
Строк `giver_id = 0` и `alife():story_object(` в слепке нет. **Инцидент 2 закрыт.**

### 3.3. Таблица закрытия P0/P1-бэклога v2

| Пункт v2 | Суть | Статус v3 | Подтверждение |
|---|---|---|---|
| P0-1 | Слияние действий реплики в один `<action>` | **PASS** | 6 `<action>` на 6 реплик; 0 дублей |
| P0-2 | Резолв story-ID по имени | **PASS** | `get_story_object_id` 2481–2488, 2563–2571 |
| P0-3 | Запрет `giver_id = 0` | **PASS** | 2918–2939; `~= 0` перед записью |
| P0-4 | Контракт `target_alias=""` | **PASS** | 3046–3052, 3252–3258 |
| P0-5 | Награда сдачи только через `_reward` | **PASS** (Q1) / **ARCH_DIFF** (Q2) | Q1: 2361–2363; Q2: 3633–3649 — см. A2 |
| P0-6 | Faction/Warfare-гейт как модель | **PASS** | `requires_faction`/`requires_warfare` 2274–2275, 2356–2357; проверки 3444–3451 и др. |
| P0-7 | Учёт союзников вне `WarfareCapture` | **PASS** | `register_dyn_squad`/`freeze_dyn_squads`/`unmark_quest_squads` |
| P1-1 | `freeze_squad` — guard `current_action == 1` | **PASS** | 2734–2743 |
| P1-2 | Генерация `squad_descr_<slug>.ltx` | **PASS** | 1874–1878 |
| P1-3 | Идемпотентная выдача квестового предмета | **PASS** | `item_actions` 2315–2321; 3091–3097 |
| P1-4 | `_cleanup` снимает все поршни варианта | **PASS** | `cleanup_infos` 2268–2271; 3195–3197, 3216–3218 |
| P1-5 | `announce` — сообщение завершённого этапа | **PASS** | 3114–3115, 3320–3321; текст берётся из `stage_data` старого этапа |
| P1-6 | Автогенерация `_msg_reward`/`_msg_fail` | **PASS** | 1938–1943, 1980–1985; 2094–2099, 2136–2141 |
| P1-7 | Сдача по `tsk.stage >= N`, а не по поршню из `on_start_actions` | **FAIL** | `*_ready` не снимается в cleanup, `return_stage = -1`; см. §5 |
| P1-8 | Критичные действия в `init_actions` при `world=true` | **PASS** (с оговоркой) | `*_ready` выдаётся в `on_start_actions` этапа возврата; этап входит только при работающем Warfare. Остаточный риск — только при выключении Warfare в окне 3 с; для `requires_warfare`-квеста это вне контракта |
| P1-9 | Убрать дублирование `_can_take` + `<dont_has_info>` | **PASS** (с оговоркой) | Дублирование осталось (XML `dont_has_info` + проверка `task_info`), но не ломает логику; P2-чистота |

### 3.4. P2-хвост v2 (не входит в V1–V12, не влияет на вердикт)

- **P2-2** — шапка-комментарий в `tm_*.ltx` всё ещё отсутствует (косметика).
- **P2-3** — остались «мёртвые» регистрации: `*_accept`, `*_turn_in`,
  `*_take_*_can_turn_in`, `*_turnin_can_take` и т.п. (3804–3838). Они не
  используются XML, но и не мешают.
- **P2-4/P2-5/P2-7** — build-grep-линт, валидация секций по БД и CI-тест на
  «нет реплики с >1 `<action>`» по слепку не проверяются; это задачи сборщика,
  а не дефекты данного слепка.
- **P2-6** — кодировка/экранирование: `&quot;`/`&apos;` и `—` в cp1251
  выглядят корректно; BOM унаследованного `character_desc_escape.xml` сохранён
  (`п»ї` в начале — это отображение `EF BB BF`), что соответствует API_v2 §3.6.

---

## 4. Обоснование всех `ARCH_DIFF`

### A1. Q2 — два этапа и `stage_complete = 2`

**Где:** `tm_golden_shield_test.ltx:1912`, `QUESTS.mymod_atp_quest` 2284, 2286–2325.

**Почему это не дефект.** Модель Q2: этап 0 — захват АТП, этап 1 — возврат к Журову.
`last_stage = 1`, `stage_complete = last_stage + 1 = 2`. Это внутренне согласованная
2-этапная модель: `stage_complete` — не триггер завершения, а маркер финальной стадии
(RULE.md §2.3). Сдача идёт диалогом, поэтому отдельный этап «сдать данные» не нужен.

**Безопасность в X-Ray.** `_status` не пытается завершить Q2 на этапе 1: у этапа нет
`capture`, нет `complete`-условий, `return_stage = -1`; завершение делает только
`complete_task` из реплики сдачи. Награда и изъятие ПДА выполняются в одной функции
до `complete_task`; повторное завершение невозможно из-за `mymod_atp_quest_done`.
Единственная оговорка — гейт сдачи по `*_ready` должен очищаться при отмене; это
дефект реализации, а не самой 2-этапной модели (см. FAIL-1).

### A2. Q2 — награда 15 000 / 30 000 в реплике сдачи

**Где:** 3633–3649 (15 000), 3663–3679 (30 000); `QUESTS` 2279–2280 (`money = 0`, `item = ""`).

**Почему это не дефект.** В v3 действия реплики слиты в **одну** функцию
`dialogs.mymod_atp_quest_turnin_phrase_2_action` / `..._phrase_4_action`:
`take_item("itm_pda_common")` → `give_money(15000|30000)` → `complete_task(...)`.
Движок исполняет всю функцию, а не отдельный тег. Второго `<action>` нет, потери
действия нет. `_reward` при этом ничего не добавляет (`money = 0`, `item = ""`),
поэтому двойной награды нет.

**Безопасность.** Обе ветки взаимоисключающие по поршням `mymod_q2_assault` /
`mymod_q2_solo`; после завершения выдаётся `mymod_atp_quest_done`, и диалог закрывается.
`cleanup_infos` снимает оба вариантных поршня в `_reward` и `_cleanup`. Суммы
соответствуют эталону (15 000 — штурм, 30 000 — соло).

### A3. Q2 — общее описание вместо `_descr_assault` / `_descr_solo`

**Где:** `descr = mymod_atp_quest_descr` (1908), `descr_functor = mymod_atp_quest_descr`
(1909), строки 1974–1976 / 2130–2132.

**Почему это не дефект.** Общий текст явно описывает **оба** варианта («штурм с двумя
группами или одиночная диверсия за двойную плату»), а `descr_functor` подменяет
описание по этапам (`_stage_0_descr`, `_stage_1_descr`). Игрок не теряет информацию
о выборе; логика выбора зашита в разные диалоги, а не в текст.

**Безопасность.** Описание — только UI-текст; на награду, поршни и прохождение не влияет.

### A4. Схема pstor-ключей `stage_key`

**Где:** 2493–2496; ключи вида `golden_shield_test_mymod_atp_quest_v_<stage>_<suffix>`.

**Почему это не дефект.** Эталон использует плоские константы (`mymod_q1_v_spawn` и т.п.),
авто-слепок — пространство имён на квест и этап. Это соответствует API_v2 §3.4 и
исключает коллизию с `task_id` (который `task_manager` очищает сам).

**Безопасность.** Ключи не равны `task_id`; сброс/чтение идут только через `stage_key`;
`_dyn_squad_*` использует отдельный префикс `q.key_prefix`. Утечки между квестами нет.

### A5. `world = true` / `requires_warfare` и ранний выход `_status`

**Где:** 2285, 2367 (флаги), 3070–3072, 3276–3278 (`if (quest.world or quest.requires_warfare) and not is_warfare() then return nil end`).

**Почему это не дефект.** Эталон тоже не работает вне Warfare:
`if not is_warfare() then return nil end` (standart, 2504/2682). Авто-слепок выражает
то же самое декларативно через `requires_warfare` и дополнительно закрывает диалоги
взятия (`*_can_take`).

**Безопасность.** Квест нельзя взять вне Warfare; внутри Warfare `_status` тикает и
двигает этапы. Если игрок выключит Warfare уже после взятия, квест остановится — это
документированное ограничение `requires_warfare` (API_v2 §2.6/§2.7), а не дефект слепка.

### A6. Динамические отряды `SpawnSquad` вместо `WarfareCapture.ally_count`

**Где:** `register_dyn_squad` 2690–2699; `freeze_dyn_squads` 2775–2781;
`unmark_quest_squads` 2670–2686; вызов из `run_actions` 3014–3018; Q2-действие 3494–3511.

**Почему это не дефект.** В v2 `SpawnSquad` в реплике создавал «неуправляемый» отряд.
В v3 `run_actions` получает `quest_id`, регистрирует отряд в pstor, `_status` морозит его
через `freeze_dyn_squads`, а `_reward`/`_cleanup` освобождают через `unmark_quest_squads`.
Это ровно контракт API_v2 §2.6 «Автоматический учёт отрядов из `SpawnSquad`».

**Безопасность.** Счётчик `_dyn_squad_cnt` увеличивается при спавне и сбрасывается
**только** в `_reward`/`_cleanup` после `unmark_quest_squads`; в `_start` сброса нет,
поэтому отряды, заспавненные до `give_task` в той же реплике, не «теряются».
Утечки в `sim_offline_combat.task_squads` нет.

### A7. Поэтапные `descr_functor` / `_stage_<n>_msg` вместо плоских `_msg_village` / `_msg_elevator`

**Где:** 3056–3062, 3262–3268; строки `_stage_<n>_msg`.

**Почему это не дефект.** Авто-схема привязывает описание и сообщение к номеру этапа,
а не к сюжетному имени точки. Для двух квестов это эквивалентно; `announce` передаёт
сообщение **завершённого** этапа (3114–3115, 3320–3321), поэтому игрок видит
«Деревня взята», а не заголовок следующего этапа.

**Безопасность.** Строки существуют для всех этапов в rus/eng; `pda_tip` проверяет
перевод и не выводит сырой ID. Потеря информативности относительно эталона — только
косметическая.

### A8. `force_online` через `pcall` и прямое изъятие предметов через `alife_release`

**Где:** 2727, 2740; `take_item` 2847–2894; `give_item` 2821–2842.

**Почему это не дефект.** `force_online` в эталоне выставляется напрямую, в авто —
через `pcall`, что безопаснее для разных сборок. `take_item`/`give_item` реализованы
по контракту API_v2 §2.2 (прямое изъятие/выдача, одно уведомление), без ванильных
`dialogs.relocate_item_section`/`itms_manager`, которые дублировали сообщение.

**Безопасность.** `take_item` не уходит в минус по количеству, `give_item` логирует
ошибку и не падает; `news_manager` вызывается только при фактическом изменении.

---

## 5. `FAIL-1` — утечка `*_ready` и нестадийная проверка сдачи

### 5.1. Точные цитаты из авто-слепка

**Q1. Поршень `mymod_av_quest_ready` выдаётся на этапе 2:**

```lua
			[2] = {
				target = "",
				target_squad = "",
				descr = "mymod_av_quest_stage_2_descr",
				msg = "mymod_av_quest_stage_2_msg",
				capture = nil,
				start_actions = {
					{
						kind = "give_info",
						info = "mymod_av_quest_ready",
					},
				},
```

**Q1. В `cleanup_infos` этого поршня нет:**

```lua
		cleanup_infos = {},
```

**Q1. `_cleanup` снимает только `taken_info` и `cleanup_infos`, но не `*_ready`:**

```lua
	local function mymod_av_quest_cleanup(actor, npc, p)
		local quest = QUESTS["mymod_av_quest"]
		if not quest then return end

		unmark_quest_squads(quest)
		vset(quest.key_prefix .. "_dyn_squad_cnt", 0)
		run_actions(quest.fail_actions, actor or db.actor, npc, "mymod_av_quest")
		if db.actor and quest.taken_info ~= "" then
			db.actor:disable_info_portion(quest.taken_info)
		end
		for _, info in ipairs(quest.cleanup_infos or {}) do
			db.actor:disable_info_portion(info)
		end
```

**Q1. Диалог сдачи открывается именно по этому поршню:**

```xml
	<dialog id="mymod_av_quest_turnin">
		<precondition>dialogs.mymod_av_quest_turnin_can_turn_in</precondition>
		<has_info>mymod_av_quest_ready</has_info>
		<dont_has_info>mymod_quest_1_done</dont_has_info>
```

```xml
			<phrase id="1">
				<text>mymod_av_quest_turnin_phrase_1_text</text>
				<action>dialogs.mymod_av_quest_turnin_turn_in</action>
			</phrase>
```

**Q1. `_can_turn_in` фактически не проверяет стадию, потому что `return_stage = -1`:**

```lua
		return_stage = -1,
```

```lua
	if quest.return_stage >= 0 and (tsk.stage or 0) < quest.return_stage then
		return false
	end
	return true
```

**Q2. Та же картина: `*_ready` не входит в `cleanup_infos`:**

```lua
		cleanup_infos = {
			"mymod_q2_assault",
			"mymod_q2_solo",
		},
```

```lua
					{
						kind = "give_info",
						info = "mymod_atp_quest_ready",
					},
```

```xml
		<has_info>mymod_atp_quest_ready</has_info>
```

`mymod_atp_quest` тоже имеет `return_stage = -1` (2282), поэтому
`mymod_atp_quest_turnin_can_turn_in` возвращает `true` при одном лишь наличии задачи.

### 5.2. Сценарий поломки (Q1 — безусловный)

1. Взять Q1 у Журова, захватить Деревню и Элеватор, дойти до этапа 2.
   На первом тике этапа 2 выдаётся `mymod_av_quest_ready`.
2. Отменить задачу в КПК/скриптом (`on_cancel`) до сдачи.
   `mymod_av_quest_cleanup` снимает `mymod_av_quest_started`, но **не** снимает
   `mymod_av_quest_ready` (`cleanup_infos = {}`).
3. Снова взять Q1: диалог взятия доступен, потому что `started` снят, а
   `mymod_quest_1_done` ещё нет.
4. Не выполняя ни одного этапа, открыть диалог сдачи: он виден, потому что
   `mymod_av_quest_ready` остался, `mymod_quest_1_done` нет, а
   `mymod_av_quest_turnin_can_turn_in` при `return_stage = -1` проверяет только
   наличие задачи.
5. Выбрать реплику 1 → `complete_task("mymod_av_quest")` → `_reward` выдаёт
   **10 000 ₽ + `wpn_vssk`**, ставит `mymod_quest_1_done` и открывает Q2.

**Итог:** квест Q1 пройден без захвата точек, награда получена, прогрессия Q2
разблокирована досрочно. Это утечка состояния и sequence break.

### 5.3. Сценарий поломки (Q2 — при наличии любого `itm_pda_common`)

1. Взять Q2 «штурм»/«соло», дойти до этапа 1 (ПДА выдан, `mymod_atp_quest_ready` стоит).
2. Отменить/провалить Q2: `cleanup` снимает `mymod_atp_quest_started`,
   `mymod_q2_assault`/`mymod_q2_solo`, изымает ПДА (`fail_actions`), но
   `mymod_atp_quest_ready` остаётся.
3. Снова взять Q2 (любой вариант). Диалог сдачи уже виден на этапе 0.
4. Если в инвентаре есть **любой** `itm_pda_common` (обычный предмет, часто лежит
   в тайниках/луте), реплика 2 или 4 проходит precondition `has_item`, и Q2
   завершается сразу: 15 000/30 000 ₽ + `mymod_atp_quest_done`, АТП не зачищено.
   Если ПДА нет — показывается только реплика 6 («данных нет»), то есть диалог
   как минимум вводит в заблуждение и ломает сценарий «сначала зачисти АТП».

### 5.4. Почему статические V1–V12 это не ловят

V1–V12 проверяют количество `<action>`, порядок тегов, кросс-ссылки, награду,
резолв цели, `stage_complete`, `dont_send_update_news`, `squad_descr`, строки,
дубли диалогов и `system.ltx`. Ни один из этих критериев не проверяет **жизненный
цикл инфопоршней**: выдан ли `*_ready` повторно, снимается ли он при `on_fail`/
`on_cancel`, и не делает ли `_can_turn_in` проверку стадии фиктивной при
`return_stage = -1`. Поэтому слепок проходит V1–V12, но имеет функциональный блокер.

### 5.5. Рекомендации по исправлению

1. **Обязательно:** добавить `mymod_av_quest_ready` и `mymod_atp_quest_ready` в
   `Quest.cleanup_infos` (или явно снимать их в `_cleanup`). Тогда после отмены
   повторное взятие не откроет сдачу до реального прохождения этапов.
2. **Защита в глубину:** сделать `*_can_turn_in` стадийной проверкой:
   `if (tsk.stage or 0) < (quest.last_stage or 0) then return false end` —
   при `return_stage = -1` использовать `last_stage`. Это соответствует
   API_v2 §3.4, п. 10, и закрывает проблему даже при случайно оставшемся поршне.
3. **Генератору:** при `world = true`/`requires_warfare` либо автоматически
   добавлять стадийные `give_info`-поршни в cleanup, либо генерировать
   `_can_turn_in` по `tsk.stage`, а не полагаться только на `<has_info>`.
4. **Тест:** добавить статическую проверку «каждый `give_info` из
   `Stage.on_start_actions` либо снимается в `_cleanup`, либо не используется
   как единственный гейт сдачи».

---

## 6. Замечания к документации (не блокеры слепка)

Эти пункты не влияют на статус авто-слепка, но важны, чтобы следующая пересборка
не вернула уже исправленные дефекты.

1. **`docs/API_v2.md` §2.6, п. 3 (строка 538)** утверждает:
   «`<quest_id>_start` сбрасывает `..._dyn_squad_cnt = 0` при повторной выдаче».
   Это **противоречит** рабочей схеме v3 и требованию чек-листа: в Q2 отряды
   спавнятся в реплике **до** `give_task`, и сброс счётчика в `_start` обнулил бы
   уже зарегистрированные отряды. Фактически сброс должен быть только в
   `_reward`/`_cleanup` после `unmark_quest_squads`. Документ нужно исправить,
   иначе следующая генерация по документации вернёт баг.
2. **`docs/RULE.md` §3.3 (строка 709)** говорит: «тегов `<action>` может быть
   несколько, они выполняются по порядку». Это противоречит `docs/API_v2.md`
   §2.2/§3.4 (один `<action>` на реплику) и фактическому поведению X-Ray/OpenXRay
   (второй тег отбрасывается). RULE.md в этой части устарел; ориентир — API_v2.
3. **`docs/API_v2.md` §3.5, п. 5 (строки 1437–1465)** предупреждает, что при
   отсутствии явного этапа сдачи `stage_complete` становится 2, а `_can_turn_in`
   начинает считать сдачу доступной на этапе захвата. Q2 v3 — ровно этот случай:
   `return_stage = -1`, сдача держится на `*_ready`. Это допустимо только при
   обязательной очистке `*_ready` (см. FAIL-1); в документации стоит добавить
   это условие явно.
4. **P2-чистота:** в `register()` остаются регистрации функций, не используемых
   XML (`*_accept`, `*_turn_in`, `*_take_*_can_turn_in`, `*_turnin_can_take`).
   Они безвредны, но маскируют реальные гейты; при следующей итерации лучше
   удалить или пометить.

---

## 7. Итоговая проверка по пунктам задания

| Пункт задания | Результат |
|---|---|
| 1. Сброс `_dyn_squad_cnt` | **PASS**: в `mymod_atp_quest_start` сброса нет; в `_reward`/`_cleanup` — после `unmark_quest_squads` (3198–3199, 3210–3211, 3404–3405, 3416–3417) |
| 1. Изъятие `itm_pda_common` в `fail_actions` Q2 | **PASS**: 2328–2334 |
| 1. LTX: `storyline=false`, `prior=60`, иконки, `stage_complete`, `dont_send_update_news`, `condlist_0`, `%=...()%` | **PASS** / **ARCH_DIFF A1** для `stage_complete=2` |
| 2. XML: ≤1 `<action>`, порядок тегов, регистрация `dialogs.*` | **PASS** |
| 2. `character_desc_escape.xml`: 5 диалогов, без дублей, порядок | **PASS** |
| 2. `system.ltx`: ровно 1 регистрация | **PASS** |
| 3. `squad_descr_golden_shield_test.ltx` + секция | **PASS** |
| 3. `st_*.xml` rus/eng: `_msg_start`, `_msg_reward`, `_msg_fail`, `_stage_<n>_msg` | **PASS** |
| 3. `give_task`: `who_is_npc`, `get_story_object_id`, нет `giver_id = 0`/`alife():story_object` | **PASS** |
| 3. `mymod_av_quest_target`: `~= 0` + fallback | **PASS** |
| 3. `freeze_squad`: `current_action == 1` | **PASS** |
| 3. Гейты `army` + `IsWarfare()` | **PASS** |
| 3. Очистка `mymod_q2_assault`/`mymod_q2_solo` | **PASS** |
| 3. Повторная выдача ПДА | **PASS** |
| **Дополнительно:** жизненный цикл `*_ready` и стадийность сдачи | **FAIL-1** |

---

## 8. Формальный вывод

- **FAIL:** 1 (`FAIL-1`, утечка `mymod_av_quest_ready` / `mymod_atp_quest_ready`
  + фиктивная проверка стадии в `_can_turn_in`).
- **ARCH_DIFF:** 8 (A1–A8), все безопасны при условии исправления FAIL-1.
- **PASS:** все остальные проверенные узлы и критерии V1–V12.

**Итоговый вердикт: НЕ ГОТОВО К PHASE 2.** После добавления `*_ready` в
`cleanup_infos` (или стадийной проверки в `_can_turn_in`) слепок можно пересобирать
и повторять аудит; других блокеров в статике не найдено.

---

*Конец отчёта. Файл создан без изменений в коде проекта и без открытия запрещённых каталогов.*
