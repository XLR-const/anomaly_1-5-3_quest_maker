# GOLDEN DIFF AUDIT v4 — финальный контрольный дифф-аудит слепка `golden_shield_test`

> **Объект аудита:** `tools/manual_mod_snapshot_golden_shield_test.txt` — свежий авто-слепок
> после закрытия `FAIL-1`.
> **База:** `docs/GOLDEN_DIFF_AUDIT_v3.md` (35 узлов + критерии V1–V12 + 8 `ARCH_DIFF`).
> **Контракт:** `docs/API_v2.md` (§2.6, §2.8, §3.4, §3.5).
> **Дата:** 2026-11-15. **Режим:** read-only.
>
> **Границы.** Прочитаны только три файла: `docs/GOLDEN_DIFF_AUDIT_v3.md`,
> `tools/manual_mod_snapshot_golden_shield_test.txt`, `docs/API_v2.md`. Каталоги
> `_unpacked/`, `output/`, `src/`, `tests/` не открывались и не сканировались; поиск
> по проекту не запускался; существующие файлы в `docs/` и `tools/` не изменялись.
> Создан только этот файл. Аудит статический: динамические проверки V13–V20
> (прогон в игре) не выполнялись.

---

## 1. Краткое резюме и вердикт

**Вердикт одной строкой:** обязательный блокер `FAIL-1` закрыт — поршни
`mymod_av_quest_ready` / `mymod_atp_quest_ready` теперь входят в `cleanup_infos`
и снимаются в `_reward` и `_cleanup`; сценарий «отменил → взял заново → сдал без
прохождения» больше не воспроизводится. Все 35 узлов v3 и критерии V1–V12
регрессионно подтверждены, документация `API_v2.md` синхронизирована с рабочей
схемой.

**Общий вердикт: `READY FOR PHASE 2` — блокеров 0.**

### 1.1. Баланс статусов

| Статус | Кол-во | Состав |
|---|---|---|
| **FAIL** | **0** | — |
| **ARCH_DIFF** | **9** | A1–A8 (унаследованы из v3, безопасны) + **A9** (новая: асимметрия стадийного гейта сдачи, не блокер) |
| **PASS** | **33 из 35 узлов** + **11 из 12 критериев** | см. §3, §4 |

### 1.2. Что изменилось относительно v3

| Пункт v3 | Было в v3 | Стало в v4 |
|---|---|---|
| `QUESTS["mymod_av_quest"].cleanup_infos` | `{}` | `{ "mymod_av_quest_ready" }` (2354–2356) |
| `QUESTS["mymod_atp_quest"].cleanup_infos` | `{ "mymod_q2_assault", "mymod_q2_solo" }` | + `"mymod_atp_quest_ready"` (2268–2272) |
| Узел 35 «сдача Q1/Q2» | **FAIL** | **PASS** |
| Узлов с `FAIL` | 1 | **0** |

---

## 2. Подтверждение закрытия `FAIL-1`

### 2.1. Требование 1.1 — поршни в `cleanup_infos`

**Q1 — поршень добавлен** (`tools/manual_mod_snapshot_golden_shield_test.txt`, 2354–2356):

```lua
		cleanup_infos = {
			"mymod_av_quest_ready",
		},
```

**Q2 — поршень добавлен, вариантные поршни сохранены** (2268–2272):

```lua
		cleanup_infos = {
			"mymod_q2_assault",
			"mymod_q2_solo",
			"mymod_atp_quest_ready",
		},
```

> **PASS.** Оба поршня готовности присутствуют; `mymod_q2_assault` / `mymod_q2_solo`
> не потеряны.

### 2.2. Требование 1.2 — снятие поршней при провале/отмене

**Q1 `_cleanup`** (3415–3430) — цикл по `cleanup_infos` есть:

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
	pda_tip(quest.msg_fail)
```

**Q2 `_cleanup`** (3209–3224) — идентичная структура:

```lua
	unmark_quest_squads(quest)
	vset(quest.key_prefix .. "_dyn_squad_cnt", 0)
	run_actions(quest.fail_actions, actor or db.actor, npc, "mymod_atp_quest")
	if db.actor and quest.taken_info ~= "" then
		db.actor:disable_info_portion(quest.taken_info)
	end
	for _, info in ipairs(quest.cleanup_infos or {}) do
		db.actor:disable_info_portion(info)
	end
```

**Та же очистка продублирована в успешной ветке `_reward`** (3197–3202 и 3403–3408),
поэтому поршень не «залипает» и после штатной сдачи:

```lua
	run_actions(quest.complete_actions, actor or db.actor, npc, "mymod_atp_quest")
	for _, info in ipairs(quest.cleanup_infos or {}) do
		db.actor:disable_info_portion(info)
	end
	unmark_quest_squads(quest)
	vset(quest.key_prefix .. "_dyn_squad_cnt", 0)
```

> **PASS.** Провал и отмена снимают оба `*_ready`; успешная сдача — тоже.

**Повторная проверка сценария из v3 §5.2/§5.3:**

1. Q1: отмена на этапе 2 → `_cleanup` снимает `mymod_av_quest_started` **и**
   `mymod_av_quest_ready`. Повторное взятие сбрасывает этапы; диалог сдачи скрыт,
   т.к. `<has_info>mymod_av_quest_ready</has_info>` (1758) больше не выполняется.
   Ветка «сдать без захвата точек и получить 10 000 ₽ + `wpn_vssk`» **закрыта**.
2. Q2: отмена → снимаются `mymod_atp_quest_started`, `mymod_q2_assault`,
   `mymod_q2_solo`, `mymod_atp_quest_ready`, изымается `itm_pda_common`
   (`fail_actions`, 2329–2335). Повторное взятие не открывает сдачу — гейт
   `<has_info>mymod_atp_quest_ready</has_info>` (1832) не проходит.
   Ветка «сдать при любом ПДА в инвентаре» **закрыта**.

### 2.3. Требование 1.3 — стадийная проверка в `*_turnin_can_turn_in`

**Фактическое состояние (3598–3610 и 3769–3781):**

```lua
local function mymod_atp_quest_turnin_can_turn_in(actor, npc, p)
	local linked = "mymod_atp_quest"
	if linked == "" then return true end
	local quest = QUESTS[linked]
	if not quest then return true end
	local tm = task_manager and task_manager.get_task_manager()
	local tsk = tm and tm.task_info[linked]
	if not tsk then return false end
	if quest.return_stage >= 0 and (tsk.stage or 0) < quest.return_stage then
		return false
	end
	return true
end
```

```lua
	if quest.return_stage >= 0 and (tsk.stage or 0) < quest.return_stage then
		return false
	end
	return true
end
```

При `return_stage = -1` (2283 для Q2, 2367 для Q1) эта ветка **не срабатывает**,
а `last_stage`-ветки в этих двух функциях **нет**. Ветка `last_stage` есть только
в `mymod_av_quest_take_can_turn_in` (3720–3726), которая XML **не используется**:

```lua
	if quest.return_stage < 0 and (tsk.stage or 0) < (quest.last_stage or 0) then
		return false
	end
```

**Оценка.** Буквальная формулировка пункта 1.3 не выполнена: в самих
`*_turnin_can_turn_in` стадийного `last_stage`-гейта нет. Однако это **не блокер**:

1. Обязательная мера из v3 §5.5 п. 1 (поршни в `cleanup_infos`) реализована —
   именно она закрывает эксплуатационный путь.
2. `*_ready` выдаётся **только** в `start_actions` финального этапа (2410–2415 для
   Q1, 2310–2315 для Q2), где `capture = nil`. Держать поршень, не дойдя до
   финального этапа, невозможно.
3. Поведение соответствует документированному контракту генератора:
   `API_v2.md` §3.4 п. 10 (1174–1183) добавляет проверку `tsk.stage >=
   Quest.last_stage` **только** «если у диалога нет собственного `HasInfo`»;
   §3.5 (1476–1482) повторяет это же условие. Оба диалога сдачи имеют
   собственный `<has_info>` (1758, 1832), поэтому генератор стадийную ветку
   законно не эмитит.

> **Статус: ARCH_DIFF A9** (defense-in-depth не реализован; расхождение с
> рекомендацией v3 §5.5 п. 2, но не с контрактом генератора и не с
> безопасностью слепка). Рекомендация на следующую итерацию — включить
> `last_stage`-ветку в `*_turnin_can_turn_in` безусловно.

### 2.4. Итог по `FAIL-1`

| Подпункт | Требование | Статус | Доказательство |
|---|---|---|---|
| 1.1 | `mymod_av_quest_ready` в `cleanup_infos` Q1 | **PASS** | 2354–2356 |
| 1.1 | `mymod_atp_quest_ready` в `cleanup_infos` Q2 (+ assault/solo) | **PASS** | 2268–2272 |
| 1.2 | Цикл `cleanup_infos` в Q1 `_cleanup` | **PASS** | 3425–3427 |
| 1.2 | Цикл `cleanup_infos` в Q2 `_cleanup` | **PASS** | 3219–3221 |
| 1.3 | Стадийный `min_stage` в `*_turnin_can_turn_in` | **ARCH_DIFF A9** | 3606–3609, 3777–3780; `return_stage = -1` |

**`FAIL-1` считается закрытым: блокер снят, остаточный пункт 1.3 переведён в
неблокирующий `ARCH_DIFF A9`.**

---

## 3. Регрессионная сводная таблица — 35 узлов v3

| # | Узел / проверка | Статус | Доказательство в слепке v4 |
|---|---|---|---|
| 1 | `system.ltx`: `dialogs_golden_shield_test` в `[dialogs] files` ровно 1 раз | **PASS** | 97 |
| 2 | `system.ltx`: `character_desc_escape` в `[profiles] specific_characters_files` ровно 1 раз | **PASS** | 104 |
| 3 | `system.ltx`: глоб `squad_descr_*.ltx` подключён | **PASS** | 26 |
| 4 | `character_desc_escape.xml`: 5 диалогов у `esc_3_16_military_trader`, без дублей | **PASS** | 1713–1717, 5 уникальных `<actor_dialog>` |
| 5 | Порядок `take → take_assault → take_solo → turnin` | **PASS** | 1713 `av_take` → 1714 `atp_take_assault` → 1715 `atp_take_solo` → 1716/1717 turnin |
| 6 | Не более 1 `<action>` на `<phrase>` | **PASS** | ровно 6 тегов: 1748, 1767, 1790, 1819, 1850, 1860 — каждый в своей реплике |
| 7 | Порядок тегов `text → next → precondition → has_info → give_info → action` | **PASS** | 1845–1851, 1855–1861, 1786–1791, 1815–1820 |
| 8 | Все `dialogs.*` из XML зарегистрированы в `register()` | **PASS** | 13 ссылок; все присутствуют в 3804–3844 |
| 9 | `tm_*.ltx`, Q1: `storyline=false`, `prior=60`, `ui_inGame2_Nochnaya_ohota` | **PASS** | 1884–1894 |
| 10 | `tm_*.ltx`, Q2: `storyline=false`, `prior=60`, `ui_inGame2_Osobiy_zakaz` | **PASS** | 1903–1913 |
| 11 | `dont_send_update_news = true` в обеих секциях | **PASS** | 1894, 1913 |
| 12 | `condlist_0 = {!task_giver_alive(<id>)} fail` в обеих секциях | **PASS** | 1901, 1920 |
| 13 | Эффекты LTX в форме `%=...()%` | **PASS** | 1896–1899, 1915–1918 |
| 14 | `stage_complete` Q1 = 3 при трёх этапах | **PASS** | 1893; этапы 0–2: 2371–2420 |
| 15 | `stage_complete` Q2 = 2 при двух этапах | **ARCH_DIFF A1** | 1912; этапы 0–1: 2287–2326; `last_stage = 1` (2285) |
| 16 | `squad_descr_golden_shield_test.ltx` + секция `[mymod_atp_bandit_leader_squad]:online_offline_group` | **PASS** | 1876–1878 |
| 17 | `st_*.xml` rus/eng: `_msg_start`, `_msg_reward`, `_msg_fail` | **PASS** | eng 1935–1943, 1977–1985; rus 2091–2099, 2133–2141 |
| 18 | `st_*.xml` rus/eng: `_stage_<n>_msg` для всех этапов | **PASS** | Q1: 1950/1959/1968, 2106/2115/2124; Q2: 1992/2001, 2148/2157 |
| 19 | Q1-награда в `_reward`: 10 000 ₽ + `wpn_vssk` | **PASS** | 2364–2366; выдача 3394, 3397 |
| 20 | Q2-награда в реплике сдачи: 15 000 / 30 000 | **ARCH_DIFF A2** | 3636–3652 (15 000), 3666–3682 (30 000); `money = 0`, `item = ""` (2280–2281) |
| 21 | `_dyn_squad_cnt` **не** сбрасывается в `*_start` | **PASS** | Q2 start 3154–3180, Q1 start 3360–3386 — сброса нет; сброс только 3202, 3214, 3408, 3420 |
| 22 | Сброс `_dyn_squad_cnt` **после** `unmark_quest_squads` в `_reward`/`_cleanup` | **PASS** | 3201→3202, 3213→3214, 3407→3408, 3419→3420 |
| 23 | Изъятие `itm_pda_common` в `fail_actions` Q2 | **PASS** | 2329–2335: `take_item`, `itm_pda_common`, `count = 1` |
| 24 | Снятие `mymod_q2_assault` / `mymod_q2_solo` в `_reward` и `_cleanup` | **PASS** | `cleanup_infos` 2268–2272; циклы 3198–3200, 3219–3221 |
| 25 | `give_task`: `dialogs.who_is_npc(actor, npc)` | **PASS** | 2911 (+ fallback 2912–2919) |
| 26 | `give_task`: резолв story-ID, нет `giver_id = 0` | **PASS** | 2921–2942; `resolve_target` 2475–2494 |
| 27 | Отсутствие `alife():story_object(<имя>)` | **PASS** | 0 вхождений; используется `get_story_object_id` |
| 28 | `*_target`: `tsk.task_giver_id ~= 0` + fallback на `Quest.npc` | **PASS** | Q2 3049–3055; Q1 3255–3261 |
| 29 | `freeze_squad`: guard `squad.current_action == 1` | **PASS** | 2741–2745 |
| 30 | Гейты `requires_faction = "army"` и `requires_warfare` в `*_can_take` | **PASS** | 3448–3452, 3522–3526, 3576–3580, 3690–3694; поля 2275–2276, 2359–2360 |
| 31 | Повторная выдача ПДА Q2 при потере | **PASS** | `item_actions` 2316–2322; идемпотентный цикл 3094–3100 |
| 32 | `announce` передаёт сообщение **завершённого** этапа | **PASS** | 3117–3118, 3127–3128, 3138–3139; 3323–3324 и далее |
| 33 | `resolve_target` / `resolve_alife_object` по story-ID | **PASS** | 2475–2494, 2549–2596 |
| 34 | Учёт динамических отрядов `SpawnSquad` | **PASS** | `unmark_quest_squads` 2673, `register_dyn_squad` 2693, `freeze_dyn_squads` 2778 |
| 35 | Сдача Q1/Q2: гейт по `*_ready` + `_can_turn_in`, жизненный цикл поршня | **PASS** (с A9) | `cleanup_infos` 2268–2272 / 2354–2356; циклы 3198–3200, 3219–3221, 3404–3406, 3425–3427 |

**Итог по узлам: PASS — 33, ARCH_DIFF — 2 (№15, №20), FAIL — 0.**

### 3.1. Дополнительно перепроверено по заданию

| Проверка | Результат |
|---|---|
| Единый `<action>` на реплику (всего 6 тегов) | **PASS** — 1748, 1767, 1790, 1819, 1850, 1860 |
| Регистрация в `register()` | **PASS** — 3804–3844, включая `*_turnin_can_turn_in` и `*_phrase_*_action` |
| Привязка 5 диалогов в `character_desc_escape.xml` | **PASS** — 1713–1717 |
| `system.ltx` | **PASS** — 97, 104, 26 |
| `squad_descr` | **PASS** — 1876–1878 |
| Локализация `_msg_start`/`_msg_reward`/`_msg_fail` | **PASS** — rus и eng |
| `give_task` без `giver_id = 0` | **PASS** — 0 вхождений |
| `freeze_squad` с `current_action == 1` | **PASS** — 2741 |
| Сброс `_dyn_squad_cnt` после `unmark_quest_squads` | **PASS** — 3201→3202, 3213→3214, 3407→3408, 3419→3420 |
| Повторная выдача ПДА | **PASS** — 2316–2322, 3094–3100 |

---

## 4. Критерии V1–V12

| Критерий | Статус | Комментарий |
|---|---|---|
| **V1.** Один `<action>` на реплику | **PASS** | 6 тегов / 6 реплик; 0 нарушений |
| **V2.** Один `<precondition>` на реплику/диалог, порядок тегов | **PASS** | канонический порядок, см. узел 7 |
| **V3.** Кросс-ссылки XML→Lua | **PASS** | 13 ссылок, все зарегистрированы; обратные сироты — P2 |
| **V4.** Награда Q1 в `_reward` | **PASS** | `money = 10000`, `item = "wpn_vssk"`, `item_count = 1` (2364–2366) |
| **V5.** Нет `giver_id = 0` и `alife():story_object(<имя>)` | **PASS** | 0 вхождений обоих паттернов |
| **V6.** Резолв цели с fallback | **PASS** | `task_giver_id ~= 0` → `resolve_target` → `resolve_alife_object` |
| **V7.** `stage_complete` | **ARCH_DIFF A1** | Q1 3/3 — PASS; Q2 2 этапа / `stage_complete = 2` — осознанная модель |
| **V8.** `dont_send_update_news` + `condlist_0` | **PASS** | 1894/1913, 1901/1920 |
| **V9.** `squad_descr_*.ltx` | **PASS** | 1876–1878 |
| **V10.** `_msg_reward`, `_msg_fail` (+ вариативные описания) | **PASS** | оба сообщения rus/eng; общее описание — ARCH_DIFF A3 |
| **V11.** Нет дублей `<actor_dialog>`, порядок ролей | **PASS** | 5 уникальных, порядок по API_v2 §2.5 |
| **V12.** `system.ltx` — ровно один раз | **PASS** | 97, 104 |

**Итог V1–V12: PASS — 11, ARCH_DIFF — 1 (V7), FAIL — 0.**

---

## 5. Обоснование `ARCH_DIFF`

| ID | Суть | Безопасность |
|---|---|---|
| **A1** | Q2 — 2 этапа, `stage_complete = 2`, `last_stage = 1` (1912, 2285, 2287–2326) | Модель внутренне согласована; завершение делает только `complete_task` из реплики сдачи; повтор исключён `mymod_atp_quest_done`. Соответствует `API_v2` §3.5 (1476–1482). |
| **A2** | Q2-награда 15 000 / 30 000 в реплике сдачи (3636–3652, 3666–3682), `_reward` пуст (2280–2281) | Все действия слиты в одну функцию: `take_item` → `give_money` → `complete_task`; двойной награды нет. |
| **A3** | Общее описание вместо `_descr_assault` / `_descr_solo` (1908–1909) | Только UI-текст; `descr_functor` подменяет по этапам. |
| **A4** | Схема pstor-ключей `stage_key` (namespace на квест/этап) | Коллизий с `task_id` нет; `_dyn_squad_*` — отдельный префикс. |
| **A5** | `world = true` / `requires_warfare` и ранний выход `_status` | Совпадает с эталоном; квест нельзя взять вне Warfare. |
| **A6** | Динамические отряды `SpawnSquad` вместо `WarfareCapture.ally_count` | Контракт `API_v2` §2.6; счётчик сбрасывается только после `unmark_quest_squads`. |
| **A7** | Поэтапные `descr_functor` / `_stage_<n>_msg` | `announce` передаёт сообщение завершённого этапа. |
| **A8** | `force_online` через `pcall`, прямое изъятие/выдача предметов | Безопаснее ванильных хелперов; без дублей уведомлений. |
| **A9** | `*_turnin_can_turn_in` не содержит `last_stage`-ветки (3606–3609, 3777–3780); она есть только в неиспользуемой `mymod_av_quest_take_can_turn_in` (3723–3725) | **Не блокер:** `*_ready` выдаётся только на финальном этапе и теперь снимается в `_reward`/`_cleanup`; поведение соответствует `API_v2` §3.4 п. 10 и §3.5 (условие «диалог без собственного `HasInfo`»). Рекомендация: включить ветку безусловно. |

---

## 6. Синхронизация `docs/API_v2.md`

### 6.1. §2.6 — сброс `_dyn_squad_cnt` (было главное расхождение v3)

Документ исправлен и теперь описывает рабочую схему (538–548):

```text
3. `<quest_id>_start` **не** сбрасывает `..._dyn_squad_cnt`: отряды могут
   быть заспавнены в реплике диалога **до** `give_task`, и сброс счётчика в
   `_start` обнулил бы уже зарегистрированные отряды. Счётчик сбрасывается в
   `0` в `<quest_id>_reward` и `<quest_id>_cleanup` строго после вызова
   `unmark_quest_squads`.
```

Это совпадает с кодом: в `mymod_atp_quest_start` (3154–3180) и
`mymod_av_quest_start` (3360–3386) сброса счётчика нет; в `_reward`/`_cleanup`
сброс идёт сразу после `unmark_quest_squads` (3201→3202, 3213→3214, 3407→3408,
3419→3420).

> **PASS.** Замечание v3 §6.1 закрыто.

### 6.2. §2.8 — автоочистка `GiveInfo` из `Stage.on_start_actions`

Поле `cleanup_infos` (787) документирует автодобавление:

```text
Дополнительно генератор **автоматически** добавляет сюда все `GiveInfo`
из `Stage.on_start_actions` (кроме `complete_info`/`done_info`), поэтому
поршни готовности вида `*_ready` снимаются при провале/отмене квеста и не
открывают диалог сдачи при повторном взятии.
```

Это ровно то, что наблюдается в слепке: `mymod_av_quest_ready` (2410–2415 →
2355) и `mymod_atp_quest_ready` (2310–2315 → 2271).

> **PASS.**

### 6.3. §3.5 — тот же контракт для LTX-генерации и оговорка про `_can_turn_in`

1476–1482:

```text
Если финальный этап убрать, `stage_complete` станет `2`, а сдача будет
держаться на `*_ready` из `on_start_actions`. Это допустимо только при
обязательной очистке такого поршня: генератор автоматически добавляет все
`GiveInfo` из `Stage.on_start_actions` в `Quest.cleanup_infos` и снимает их в
`_cleanup`, а для диалога сдачи без `HasInfo` дополнительно включает проверку
`tsk.stage >= Quest.last_stage`.
```

> **PASS** для автоочистки. Формулировка «для диалога сдачи **без** `HasInfo`»
> объясняет отсутствие `last_stage`-ветки в `*_turnin_can_turn_in` (A9) и
> согласуется с §3.4 п. 10 (1174–1183). Документ и код непротиворечивы.

### 6.4. Остаточное замечание к документации (не блокер)

`API_v2.md` §3.5, жёсткое правило 5 (1450–1453) по-прежнему требует, чтобы
финальный этап «сдача» существовал **явно**. Q2 (A1) это правило не выполняет и
опирается на альтернативу из 1476–1482. Формального противоречия нет (в том же
разделе описано исключение), но правило 5 стоит смягчить формулировкой «если
сдача не идёт через диалог с `HasInfo`-гейтом». P2-косметика.

---

## 7. Итоговая проверка по пунктам задания

| Пункт задания | Результат |
|---|---|
| **1.** `mymod_av_quest_ready` в `cleanup_infos` Q1 | **PASS** — 2354–2356 |
| **1.** `mymod_atp_quest_ready` в `cleanup_infos` Q2 (+ assault/solo) | **PASS** — 2268–2272 |
| **1.** Снятие поршней в `_cleanup`/`_reward` | **PASS** — 3198–3200, 3219–3221, 3404–3406, 3425–3427 |
| **1.** Стадийная проверка в `*_turnin_can_turn_in` | **ARCH_DIFF A9** — ветка `last_stage` отсутствует; эксплуатационный путь закрыт очисткой поршней |
| **2.** 35 узлов v3 не сломаны | **PASS** — 33 PASS, 2 ARCH_DIFF, 0 FAIL |
| **2.** Единый `<action>`, `register()`, 5 диалогов, `system.ltx` | **PASS** |
| **2.** `squad_descr`, локализация `_msg_*`, `give_task`, `freeze_squad` | **PASS** |
| **2.** Сброс `_dyn_squad_cnt` после `unmark_quest_squads`, повторная выдача ПДА | **PASS** |
| **3.** §2.6: сброс в `_reward`/`_cleanup`, а не в `_start` | **PASS** — 538–548 |
| **3.** §2.8/§3.5: автоочистка `GiveInfo` из `Stage.on_start_actions` | **PASS** — 787, 1476–1482 |

---

## 8. Формальный вывод

- **FAIL:** **0**. `FAIL-1` из v3 закрыт: оба поршня готовности входят в
  `cleanup_infos` и снимаются в `_reward` и `_cleanup`; sequence break при
  повторном взятии квеста не воспроизводится.
- **ARCH_DIFF:** **9** (A1–A8 унаследованы и безопасны; A9 — неблокирующая
  асимметрия стадийного гейта сдачи, соответствует документированному контракту).
- **PASS:** **33/35** узлов, **11/12** критериев V1–V12, вся проверка
  документации §2.6/§2.8/§3.5.

**Итоговый вердикт: `READY FOR PHASE 2`.** Слепок можно передавать на
динамическую проверку V13–V20. Рекомендуемые (не блокирующие) доработки на
следующую итерацию: (1) добавить `last_stage`-ветку в `*_turnin_can_turn_in`
безусловно; (2) смягчить формулировку §3.5 п. 5 в `API_v2.md`; (3) удалить
«мёртвые» регистрации неиспользуемых функций из `register()` (P2).

---

*Конец отчёта. Файл создан без изменений в коде проекта, без открытия запрещённых
каталогов и без сканирования файловой системы.*
