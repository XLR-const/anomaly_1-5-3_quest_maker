# GOLDEN DIFF AUDIT — ручной эталон «M» vs авто-слепок `golden_shield_test`

> **Объект аудита:** `tools/standart_manual_mod_snapshot.txt` (ручной рабочий мод «M») и
> `tools/manual_mod_snapshot_golden_shield_test.txt` (слепок, собранный фреймворком по
> `examples/build_golden_test.py`).
> **Дата:** 2026-11-13. **Версия ядра:** `src/core/models.py` + `src/compiler/*` (текущая).
> **Режим:** read-only. Каталоги `output/` и `_unpacked/` не открывались, код проекта не
> изменялся. Отчёт создан как единственный артефакт.
>
> **Методика.** Построчное сравнение слепков; трассировка «модель → LTX/XML/Lua» по
> `examples/build_golden_test.py`, `src/compiler/lua_gen.py`, `src/core/models.py`;
> сверка заявленных контрактов с `docs/API_v2.md`. Для XML-диалогов дополнительно
> посчитано количество тегов `<action>` на реплику (скрипт-проверка по слепкам, результат
> приведён в 2.1 и 3.2).
>
> **Ключевой вывод (одной строкой):** авто-слепок структурно валиден, но в нём **потеряны
> все эффекты, которые в одной реплике идут вторыми** (`<action>`-дубль), **сломан резолв
> story-ID квестодателя** (`alife():story_object(<имя>)` вместо `get_story_object_id`) и
> **отсутствуют Warfare-механики эталона** (учёт союзников, `who_is_npc`, faction-гейт,
> `squad_descr`). Оба инцидента ручного тестирования объясняются этими тремя причинами и
> являются **багами компилятора**, а не ошибками сценариста.

---

## 1. Сводная матрица соответствия (Executive Summary)

### 1.1. Матрица по компонентам мода

| # | Компонент | Ручной эталон «M» | Авто-слепок | Статус |
|---|---|---|---|---|
| 1 | `gamedata/configs/system.ltx` | `[dialogs] files = ..., dialogs_mymod`; `[profiles] specific_characters_files` без изменений (escape уже в списке) | `[dialogs] files = ..., dialogs_golden_shield_test`; `[profiles]` без изменений (escape уже в списке) | **[СОВПАДАЕТ]** (различие только в выравнивании `files = ` vs `files                                    = `) |
| 2 | `gamedata/configs/gameplay/character_desc_escape.xml` | 5 своих `<actor_dialog>` в профиле `esc_3_16_military_trader`, без дублей | те же 5 диалогов, без дублей, но другой порядок и место вставки (в конец профиля) | **[ЧАСТИЧНОЕ РАСХОЖДЕНИЕ]** (косметика + порядок ролей) |
| 3 | `gamedata/configs/misc/task/tm_*.ltx` | 2 секции; Q1: 3 этапа/`stage_complete=3`; Q2: **3 этапа**/`stage_complete=3`; `storyline=false`; разные иконки; шапка-комментарий | 2 секции; Q1: 3 этапа/`stage_complete=3`; Q2: **2 этапа**/`stage_complete=2`; `storyline=true`; одна иконка `ui_inGame2_Put_v_pripyat`; без шапки | **[ЧАСТИЧНОЕ РАСХОЖДЕНИЕ]** |
| 4 | `gamedata/configs/gameplay/dialogs_*.xml` | ровно **1** `<action>` на реплику; диалог-сдача закрыт одной `dialogs.*_can_turn_in` | **2** `<action>` в 4 репликах; `precondition` после `<next>`; иная схема guard'ов | **[КРИТИЧЕСКИЙ ПРОБЕЛ]** |
| 5 | `gamedata/configs/text/{rus,eng}/st_*.xml` | 32/32 строки: `_descr_elevator`, `_descr_done`, `_descr_docs`, `_msg_village`, `_msg_elevator`, `_msg_cleared`, `_msg_handin`, `_msg_reward`, `_msg_reward_solo` | 34/34 строки: `_title`, `_descr`, `_stage_<n>_{title,descr,msg}`, все реплики; **нет** `_msg_reward`/`_msg_fail`; нет вариативных описаний Q2 | **[ЧАСТИЧНОЕ РАСХОЖДЕНИЕ]** |
| 6 | `gamedata/scripts/*.script` | ручной модуль: `mark_task_squad`, `freeze_squad` c `current_action==1`, `smart_cleared`, `q2_variant_solo`, `q2_give_item`, faction-гейт, `who_is_npc`, `get_story_object_id` | авто-модуль: `mark_task_squad`, `freeze_squad` без guard, `stage_cleared`, нет variant-логики, нет faction-гейта, `resolve_target` через `alife():story_object` | **[КРИТИЧЕСКИЙ ПРОБЕЛ]** |
| 7 | `gamedata/configs/misc/squad_descr/squad_descr_*.ltx` | есть `squad_descr_mymod.ltx`, секция `[mymod_atp_bandit_leader_squad]:online_offline_group` | **файла нет вообще** | **[КРИТИЧЕСКИЙ ПРОБЕЛ]** |

### 1.2. Сводка по инцидентам

| Инцидент | Симптом | Root cause | Вердикт |
|---|---|---|---|
| 1 | После сдачи Q1 не выдан `wpn_vssk` (и не начислены 10 000 ₽) | `<action>`-дубль в реплике: движок хранит **одно** действие на реплику, первым идёт `..._turn_in`, второй `..._phrase_1_action` (деньги+оружие) отбрасывается. `_reward` при этом пуст (`money=0`, `item=""`) | **Баг компилятора (P0)** + противоречие в `API_v2.md` §2.8/§4.2. Сценарист не виноват — он воспроизвёл документированный шаблон |
| 2 | На этапе сдачи Q1 жёлтая метка на игроке вместо Журова | `target_alias=""` → `return tsk.task_giver_id`; `task_giver_id` испорчен: `give_task` пишет `0` (truthy в Lua) при нерезолвленном NPC, а `resolve_target` ищет story-ID через `alife():story_object(<имя>)` вместо `get_story_object_id(<имя>)` | **Баг компилятора (P0)** + пробел в документации §2.7 |

### 1.3. Цифры

| Метрика | Эталон «M» | Авто-слепок |
|---|---|---|
| Файлов в слепке | 8 | 7 (нет `squad_descr_*`) |
| Квестов / этапов | 2 / 3+3 | 2 / 3+2 |
| Реплик с `>1` `<action>` | **0** | **4** (`av_turnin/1`, `atp_take_assault/2`, `atp_turnin/2`, `atp_turnin/4`) |
| Поршней `*_ready` | 0 (используется `stage >= 2`) | 2 (`mymod_av_quest_ready`, `mymod_atp_quest_ready`) |
| pstor-ключей | 16 явных | 4×N генерируемых (`<prefix>_<quest>_v_<stage>_<suffix>`) |
| Проверок фракции `army` | 2 (`q1_can_take`, `q2_can_take`) | **0** |
| Проверок `IsWarfare()` в диалогах | 2 | **0** (только `world`-гейт в `_status`) |

---

## 2. Разбор инцидентов ручного тестирования (Root Cause Analysis)

### 2.1. Инцидент 1 — не выдан `wpn_vssk` после Квеста 1

#### 2.1.1. Трассировка: сценарий → модель → XML → Lua

**Шаг 1. Сценарий.** Награда объявлена **только в реплике диалога сдачи**,
`examples/build_golden_test.py:289-293`:

```python
                actions=[
                    GiveMoney(amount=Q1_REWARD_MONEY),
                    GiveItem(item_alias=Q1_REWARD_WEAPON, count=1),
                    CompleteTask(task_id=Q1_ID),
                ],
```

Поля `Quest.reward_money` / `Quest.reward_item_alias` в `create_first_quest()`
**не заданы** (`examples/build_golden_test.py:114-195`) — награда в модель квеста не
попадает.

**Шаг 2. Модель → `local QUESTS`.** `src/compiler/lua_gen.py:1009-1011`:

```python
            "money": quest.reward_money or 0,
            "item": self._resolve_item_section(quest.reward_item_alias or ""),
            "item_count": quest.reward_item_count,
```

Результат в слепке — `tools/manual_mod_snapshot_golden_shield_test.txt:2299-2300`:

```lua
		money = 0,
		item = "",
```

**Шаг 3. Модель → XML.** Генератор раскладывает действия реплики на два вида:
`CompleteTask` — нативный тег `<action>`, остальные — одна Lua-функция
`..._phrase_<n>_action` (`src/compiler/lua_gen.py:1449-1453`):

```python
            lua_actions = [
                action
                for action in phrase.actions
                if not isinstance(action, (GiveInfo, GiveTask, CompleteTask))
            ]
```

Итог в слепке — `tools/manual_mod_snapshot_golden_shield_test.txt:1764-1768`:

```xml
			<phrase id="1">
				<text>mymod_av_quest_turnin_phrase_1_text</text>
				<action>dialogs.mymod_av_quest_turnin_turn_in</action>
				<action>dialogs.mymod_av_quest_turnin_phrase_1_action</action>
			</phrase>
```

**Шаг 4. Что реально исполняет движок.** В X-Ray/OpenXRay `CPhrase` хранит
**одно** строковое поле действия (`m_sAction`, читается одним `Read("action", ...)`)
и одно поле предусловия. Второй и последующие теги `<action>` парсером не
учитываются. Проверка по слепкам (подсчёт тегов на реплику):

| Слепок | Реплики с `<action>` | Кол-во `<action>` |
|---|---|---|
| Ручной «M» (`dialogs_mymod.xml`) | `av_take/3`, `av_turnin/1`, `atp_take_assault/3`, `atp_take_solo/3`, `atp_turnin/1` | **по 1** |
| Авто (`dialogs_golden_shield_test.xml`) | `av_take/3`, `av_turnin/1`, `atp_take_assault/2`, `atp_take_solo/2`, `atp_turnin/2`, `atp_turnin/4` | `av_turnin/1` = **2**; `atp_take_assault/2` = **2**; `atp_turnin/2` = **2**; `atp_turnin/4` = **2** |

Ручной эталон, который в игре работает, всегда имеет **ровно один** `<action>` на
реплику — например `tools/standart_manual_mod_snapshot.txt:1765-1768`:

```xml
			<phrase id="1">
				<text>mymod_av_q_dlg_done_1</text>
				<action>dialogs.mymod_av_turn_in</action>
			</phrase>
```

**Шаг 5. Следствие.** Первым в XML всегда идёт `..._turn_in` (генератор сортирует
действия модели, а `CompleteTask` стоит в сценарии последним — но в XML попадает
первым, см. фрагмент выше). Значит:

1. `dialogs.mymod_av_quest_turnin_turn_in` → `complete_task("mymod_av_quest")`;
2. `task_manager:set_task_completed()` вызывает `on_complete = %=mymod_av_quest_reward()%`
   (`tm_golden_shield_test.ltx:1891`);
3. `mymod_av_quest_reward` (`...golden_shield_test.txt:3185-3204`) не выдаёт ничего,
   потому что `quest.money == 0` и `quest.item == ""`:

```lua
	if quest.money and quest.money > 0 then
		give_money(quest.money, actor or db.actor)
	end
	if quest.item ~= "" then
		give_item(quest.item, quest.item_count, actor or db.actor)
	end
```

4. Второй `<action>` — `..._phrase_1_action` с `give_money(10000)` и
   `give_item("wpn_vssk", 1)` (`...golden_shield_test.txt:3570-3582`) — **движком не
   исполняется**.

Для сравнения, как это сделано в рабочем эталоне: награда живёт в `on_complete`,
`tools/standart_manual_mod_snapshot.txt:1898` и `2575-2589`:

```ltx
on_complete           = %=mymod_av_quest_reward()%
```
```lua
local function q1_reward(actor, npc, p)
	if not db.actor then return end

	db.actor:give_money(10000)
	if not alife_create_item(REWARD_Q1, db.actor) then
		printe("[mymod_quests] ! could not give %s to the actor", tostring(REWARD_Q1))
	end
	db.actor:give_info_portion(INFO_Q1_DONE)
```

#### 2.1.2. Тот же дефект ломает ещё три механики (доказательство системности)

| Реплика | 1-й `<action>` (исполняется) | 2-й `<action>` (теряется) | Последствие в игре |
|---|---|---|---|
| `mymod_av_quest_turnin` / 1 | `..._turn_in` | `..._phrase_1_action` = 10 000 ₽ + `wpn_vssk` | **Инцидент 1** |
| `mymod_atp_quest_take_assault` / 2 | `..._accept` | `..._phrase_2_action` = `SpawnSquad`×2 | **Вариант А «штурм» остаётся без подкрепления** (ломается требование ТЗ о вариантах) |
| `mymod_atp_quest_turnin` / 2 | `..._turn_in` | `..._phrase_2_action` = изъять ПДА + 15 000 ₽ | ПДА не изымается, деньги не выдаются |
| `mymod_atp_quest_turnin` / 4 | `..._turn_in` | `..._phrase_4_action` = изъять ПДА + 30 000 ₽ | То же для соло-варианта |

#### 2.1.3. Точный вердикт

**Это баг компилятора `src/compiler/` (P0), а не ошибка сценариста.**

Обоснование:
1. `Phrase.actions` документирован как список (`API_v2.md:396`), а §3.4
   (`API_v2.md:1110-1116`) прямо предписывает раскладывать `GiveTask`/`CompleteTask`
   в XML-теги, а остальные действия — в Lua-функцию, **не предупреждая**, что это
   даёт два `<action>` в одной реплике.
2. §3.3 приводит пример сгенерированного файла с **двумя** `<action>` подряд
   (`API_v2.md:990-991`) как норму.
3. §4.2 «эталонный» шаблон содержит в одной реплике `RemoveItem + GiveMoney +
   GiveItem + GiveInfo + CompleteTask` (`API_v2.md:1556-1562`) — то есть сценарий
   `build_golden_test.py` дословно повторил рекомендованный шаблон.
4. Ручной рабочий мод обходит это архитектурно: награда в `on_complete`, в реплике
   один `<action>`.

Доля вины: **компилятор ~70 %, документация ~30 %, сценарист 0 %** (он действовал
по опубликованному контракту). Дополнительно сценарий мог бы «случайно спастись»,
задав `reward_money=10000` и `reward_item_alias="wpn_vssk"` — но документация этого
не требует и даже не намекает, что иначе награда потеряется.

---

### 2.2. Инцидент 2 — жёлтая метка на игроке вместо Журова на этапе сдачи Q1

#### 2.2.1. Трассировка `target_alias` → `_target` → `task_giver_id`

**Шаг 1. Сценарий.** Этап 2 Q1 объявлен без цели (`examples/build_golden_test.py:179-193`):

```python
            2: Stage(
                id=2,
                ...
                target_alias="",
                on_start_actions=[GiveInfo(info=Q1_READY)],
            ),
```

Это **документированный** приём: `API_v2.md:532-533` — «Если `target_alias` пуст,
`target_functor` возвращает `task_giver_id` (серверный ID квестодателя)».

**Шаг 2. Модель → QUESTS.** `...golden_shield_test.txt:2337-2342`:

```lua
			[2] = {
				target = "",
				target_squad = "",
```

**Шаг 3. Сгенерированный `_target`** (`src/compiler/lua_gen.py:1113-1135`,
артефакт `...golden_shield_test.txt:3052-3072`):

```lua
	if tsk and tsk.task_giver_id then return tsk.task_giver_id end
	return resolve_target(quest.npc)
```

**Шаг 4. Откуда берётся `task_giver_id`.** `src/compiler/lua_gen.py:500-519`:

```lua
	local giver_id = nil
	if npc then giver_id = npc:id() end
	if not giver_id then
		local quest = QUESTS[task_id]
		if quest and quest.npc ~= "" then
			giver_id = resolve_target(quest.npc)
		end
	end
	if not giver_id then giver_id = 0 end
	tm:give_task(task_id, giver_id)
```

**Шаг 5. Чем плох `resolve_target`.** `src/compiler/lua_gen.py:124-136`:

```lua
local function resolve_target(target)
	if target == nil or target == "" then return nil end
	local smart = get_smart(target)
	if smart then return smart.id end
	local numeric_id = tonumber(target)
	if numeric_id then
		local obj = alife_object(numeric_id)
		return obj and obj.id or nil
	end
	local ok, story_obj = pcall(function() return alife():story_object(target) end)
	return (ok and story_obj and story_obj.id) or nil
end
```

`alife():story_object()` в X-Ray принимает **числовой** story-ID, а не строковое имя.
Для имени нужен `get_story_object_id(name)` / `get_story_object(name)` — именно их
использует эталон (`tools/standart_manual_mod_snapshot.txt:2485`, `2797`):

```lua
		return tsk.task_giver_id or get_story_object_id(GIVER_STORY)
```
```lua
	local giver = dialogs.who_is_npc(actor, npc)
	local giver_id = (giver and giver:id()) or get_story_object_id(GIVER_STORY)
```

**Шаг 6. Цепочка отказа.**

```text
dialog effect (actor, npc, p)
   └─ npc не передан/передан актор  ──┐
   └─ npc:id() == nil                ├──> give_task(..., giver_id)
                                     │        └─ resolve_target("esc_3_16_military_trader")
                                     │              └─ alife():story_object(<строка>) -> nil
                                     │        └─ giver_id = 0        <-- 0 truthy в Lua!
                                     └──> tm:give_task(task_id, 0)
                                              └─ tsk.task_giver_id = 0
   target functor: `if tsk and tsk.task_giver_id then return tsk.task_giver_id end`
                                              └─ возвращает 0 (не nil!) -> fallback на quest.npc недостижим
   task_manager рисует маркер цели по id 0 / по актору -> ЖЁЛТАЯ МЕТКА НА ИГРОКЕ
```

Ключевые два дефекта, каждый из которых самодостаточен:

1. **`giver_id = 0` как sentinel.** В Lua `0` — истина, поэтому строка
   `if tsk and tsk.task_giver_id then return tsk.task_giver_id end` **никогда** не
   уходит в резервную ветку `return resolve_target(quest.npc)`, даже если она могла
   бы спасти ситуацию. Ноль уходит в движок как «цель».
2. **Резолв story-ID через `alife():story_object(<имя>)`.** Даже резервная ветка
   нерезолвит имя Журова: нужен `get_story_object_id`. То же самое в
   `resolve_alife_object` (`src/compiler/lua_gen.py:196`), из-за чего не работают
   `target_squad_id` и строковые story-ID в `target_alias`.

Дополнительно: генератор нигде не вызывает `dialogs.who_is_npc(actor, npc)` —
эталон делает это намеренно, потому что второй аргумент диалогового эффекта не
гарантированно NPC (может быть `nil` или сам актор при вызове из некоторых веток).
Генератор же делает `if npc then giver_id = npc:id() end` без нормализации.

#### 2.2.2. Точный вердикт

**Баг компилятора (P0) в двух местах `src/compiler/lua_gen.py`: `give_task`
(строки 509-518) и `_target` (строка 1133), плюс дефектный `resolve_target`
(строка 134).** Сценарий корректен: он использует `target_alias=""` ровно так, как
разрешает §2.7 (`API_v2.md:532`), и передаёт `npc_id`/`npc_location`
(`examples/build_golden_test.py:66-68`, `116-118`).

Документация тоже виновна: §2.7 не описывает (а) что делать, если `task_giver_id`
равен `0`/`nil`, (б) обязательный fallback на `get_story_object_id(Quest.npc_id)`,
(в) что возврат `0`/`nil` из `target_functor` заставляет Anomaly рисовать маркер на
акторе.

---

## 3. Аудит конфигов и XML-структур (LTX / XML Diff)

### 3.1. `tm_*.ltx` — построчное сравнение

**Q1 — `mymod_av_quest`**

| Параметр | Эталон «M» (`standart...txt:1882-1905`) | Авто (`...golden_shield_test.txt:1878-1895`) | Статус |
|---|---|---|---|
| секция | `[mymod_av_quest]` | `[mymod_av_quest]` | ✅ |
| `icon` | `ui_inGame2_Nochnaya_ohota` | `ui_inGame2_Put_v_pripyat` (дефолт) | ⚠️ расхождение (сценарий не задал `icon`) |
| `prior` | `60` | `60` | ✅ |
| `storyline` | `false` | `true` | ⚠️ расхождение (`is_storyline=True` в сценарии) |
| `title` | `mymod_av_q_title` | `mymod_av_quest_title` | ✅ (своя схема имён) |
| `descr` | `mymod_av_q_descr` | `mymod_av_quest_descr` | ✅ |
| `descr_functor` | `mymod_av_quest_descr` | `mymod_av_quest_descr` | ✅ |
| `target_functor` | `mymod_av_quest_target` | `mymod_av_quest_target` | ✅ (но дефектный, см. 2.2) |
| `status_functor` | `mymod_av_quest_status` | `mymod_av_quest_status` | ✅ |
| `stage_complete` | `3` (3 этапа: 0,1,2) | `3` (3 этапа: 0,1,2) | ✅ |
| `dont_send_update_news` | `true` | `true` | ✅ |
| `on_init` | `%=mymod_av_quest_start()%` | `%=mymod_av_quest_start()%` | ✅ (скобки `()%` на месте) |
| `on_complete` | `%=mymod_av_quest_reward()%` | `%=mymod_av_quest_reward()%` | ✅ |
| `on_fail`/`on_cancel` | `%=mymod_av_quest_cleanup()%` | `%=mymod_av_quest_cleanup()%` | ✅ |
| `condlist_0` | `{!task_giver_alive(mymod_av_quest)} fail` | `{!task_giver_alive(mymod_av_quest)} fail` | ✅ |
| шапка-комментарий | 12 строк с описанием механик | отсутствует | ⚠️ косметика |

**Q2 — `mymod_atp_quest`**

| Параметр | Эталон «M» (`standart...txt:1909-1932`) | Авто (`...golden_shield_test.txt:1897-1914`) | Статус |
|---|---|---|---|
| `icon` | `ui_inGame2_Osobiy_zakaz` | `ui_inGame2_Put_v_pripyat` | ⚠️ |
| `prior` | `60` | `61` (сценарий задал `prior=61`) | ⚠️ (осознанный выбор сценария, на логику не влияет) |
| `storyline` | `false` | `true` | ⚠️ |
| `descr` | `mymod_atp_q_descr_assault` | `mymod_atp_quest_descr` (общий) | ⚠️ потеря assault/solo-варианта |
| `descr_functor` | `mymod_atp_quest_descr` (возвращает `_descr_solo` при поршне) | `mymod_atp_quest_descr` (только `_stage_<n>_descr`) | ⚠️ **деградация**: в слепке нет ни одной строки `mymod_atp_q_descr_solo` |
| `stage_complete` | `3` (3 этапа: 0,1,2 — 2-й этап «сдача в 40 м») | `2` (2 этапа: 0,1) | ⚠️ структурное расхождение |
| `dont_send_update_news` | `true` | `true` | ✅ |
| `condlist_0` | `{!task_giver_alive(mymod_atp_quest)} fail` | `{!task_giver_alive(mymod_atp_quest)} fail` | ✅ |
| эффекты | `%=...()%` | `%=...()%` | ✅ |

**Вывод по LTX:** синтаксис и «скобки эффектов» генерируются корректно; расходятся
метаданные (`icon`, `storyline`) и **структура Q2** (2 этапа вместо 3). Критичной
поломки в самом LTX нет — но `stage_complete=2` закрепляет потерю промежуточного
этапа «сдать данные».

### 3.2. `dialogs_*.xml` — сравнение структуры

**3.2.1. Порядок и количество тегов внутри `<phrase>`**

Эталон (`standart...txt:1736-1751`): `<text>` → `<next>` → `<action>`; ровно один
`<action>`; `<precondition>` только на уровне диалога.

Авто (`...golden_shield_test.txt:1845-1852`):

```xml
			<phrase id="2">
				<text>mymod_atp_quest_turnin_phrase_2_text</text>
				<next>3</next>
				<precondition>dialogs.mymod_atp_quest_turnin_phrase_2_precondition</precondition>
				<has_info>mymod_q2_assault</has_info>
				<action>dialogs.mymod_atp_quest_turnin_turn_in</action>
				<action>dialogs.mymod_atp_quest_turnin_phrase_2_action</action>
			</phrase>
```

Отличия:
- `<precondition>` стоит **после** `<next>` (движок терпим, но канон эталона — до);
- **два** `<action>` → второй теряется (см. 2.1);
- `has_info` на уровне реплики — допустимо, но в эталоне таких тегов в репликах нет:
  ветвление сделано через `precondition`-функции.

**3.2.2. Прекондишены диалогов**

| Диалог | Эталон | Авто | Оценка |
|---|---|---|---|
| `mymod_av_quest_take` | `<precondition>dialogs.mymod_av_can_take</precondition>` (внутри: `IsWarfare`, `is_actor_army`, `has_info(DONE/TAKEN)`, `task_info`) | `<precondition>dialogs.mymod_av_quest_take_can_take</precondition>` + `<dont_has_info>mymod_av_quest_started</dont_has_info>`; внутри `_can_take` — только `complete_info`/`task_info`/info-условия | ⚠️ **нет faction/Warfare-гейта**, условие продублировано |
| `mymod_av_quest_turnin` | `<precondition>dialogs.mymod_av_can_turn_in</precondition>` (`tsk.stage >= 2`) | `<has_info>mymod_av_quest_ready</has_info>` + `<dont_has_info>mymod_quest_1_done</dont_has_info>` | ⚠️ замена стадии на поршень: если `on_start_actions` этапа 2 не выполнились (не-Warfare, save/load до тика) — диалог недоступен навсегда |
| `mymod_atp_quest_take_assault` | `<precondition>dialogs.mymod_atp_can_take</precondition>` + `<has_info>mymod_quest_1_done</has_info>` | `_can_take` + `<has_info>` + `<dont_has_info>` | ⚠️ то же отсутствие гейта |
| `mymod_atp_quest_take_solo` | то же | то же | ⚠️ |
| `mymod_atp_quest_turnin` | `<precondition>dialogs.mymod_atp_can_turn_in</precondition>` (`stage>=1` **и** `db.actor:object(ITEM_DATA)`) | `<has_info>mymod_atp_quest_ready</has_info>` + `<dont_has_info>mymod_atp_quest_done</dont_has_info>`; проверка предмета вынесена в `precondition` реплик 2 и 4 | ✅ по смыслу, но ⚠️ дублирование логики в двух ветках |

**3.2.3. Дубли и «мёртвые» функции**

- В авто-XML **нет** дублей `<actor_dialog>` и нет повторных `<dialog id>`.
- Но зарегистрированы и не используются: `dialogs.mymod_av_quest_turnin_can_turn_in`,
  `dialogs.mymod_atp_quest_turnin_can_turn_in`, `dialogs.mymod_*_quest_accept`,
  `dialogs.mymod_*_quest_turn_in` (`...golden_shield_test.txt:3599-3600`,
  `3607-3608`, `3627-3633`). Это «мёртвый код» (P2), но он маскирует отсутствие
  реального guard'а.

### 3.3. `character_desc_escape.xml` — сравнение

| Аспект | Эталон | Авто |
|---|---|---|
| Профиль | `esc_3_16_military_trader` | тот же |
| Кол-во своих диалогов | 5 | 5 |
| Дубли | нет | нет |
| Порядок | `av_take`, `av_turnin`, `atp_take_assault`, `atp_take_solo`, `atp_turnin` (`standart...txt:1707-1711`) | `av_take`, `atp_take_assault`, `atp_take_solo`, `av_turnin`, `atp_turnin` (`...golden_shield_test.txt:1713-1717`) |
| Место вставки | между `dm_ordered_task_completed_dialog` и `guid_esc_mlr_military` | в самый конец, после `actor_break_dialog` |
| Остальной файл | байт-в-байт ваниль + свои строки | байт-в-байт ваниль + свои строки |

**Статус: [ЧАСТИЧНОЕ РАСХОЖДЕНИЕ]** — не влияет на геймплей, но порядок авто-слепка
**соответствует** документу (`API_v2.md:455-462`: `take → take_assault → take_solo →
turnin`), а порядок эталона — нет. То есть здесь авто-код **лучше** эталона; замечание
носит характер фиксации, а не дефекта.

### 3.4. Кастомные секции сквадов (`squad_descr_*.ltx`)

Эталон содержит файл (`standart...txt:1847-1863`):

```ltx
;-------------------------------------------------------------------------------;
; squad_descr_mymod.ltx                                                          ;
;                                                                                ;
; Custom squad sections used by mymod_quests.script.                              ;
; squad_descr.ltx globs every squad_descr_*.ltx file, so this one is loaded       ;
; automatically and no original squad file has to be edited.                      ;
;-------------------------------------------------------------------------------;

; Quest-only bandit leader at the truck depot (esc_smart_terrain_7_11).
; A single veteran bandit, deliberately not marked "common" so that the
; simulation never spawns this squad on its own.
[mymod_atp_bandit_leader_squad]:online_offline_group
faction = bandit
npc     = sim_default_bandit_4
```

В авто-слепке **файла нет** (`grep squad_descr` даёт только ванильный `#include` из
`system.ltx`, строка 26). Генератор вообще не умеет эмитить `squad_descr_<slug>.ltx`,
а модель `ModProject`/`Quest` не имеет поля для кастомных секций отрядов.

**Статус: [КРИТИЧЕСКИЙ ПРОБЕЛ].** Следствия:
1. Невозможно сделать «уникального» врага, которого симуляция не заспавнит сама
   (в эталоне — `mymod_atp_bandit_leader_squad`, «not marked common»).
2. Все враги в авто-слепке — ванильные `bandit_sim_squad_advanced`, то есть
   симуляция может спавнить такие же отряды параллельно; квестовая точка может быть
   «зачищена» не тем отрядом, а `stage_cleared` смотрит только на конкретный id.

> Примечание: в эталоне секция объявлена, но в видимом скрипте не используется
> (`SQ_ATP = "bandit_sim_squad_advanced"`, `standart...txt:2236`). То есть механика
> заявлена, но не продемонстрирована. Тем не менее **возможность** её объявить —
> часть контракта эталона, и она отсутствует.

### 3.5. `st_*.xml` — сравнение

| Группа строк | Эталон | Авто | Статус |
|---|---|---|---|
| `_title`, `_descr` | есть | есть | ✅ |
| Этапные title/descr/msg | нет (используются `descr_functor`) | `_stage_<n>_{title,descr,msg}` | ✅ (иная схема) |
| Вариативные описания Q2 | `_descr_assault`, `_descr_solo` | **нет** | ⚠️ потеря выбора «штурм/соло» в описании |
| Прогресс-сообщения | `_msg_village`, `_msg_elevator`, `_msg_cleared`, `_msg_handin` | вместо них `_stage_<n>_msg` = заголовок этапа | ⚠️ потеря информативности |
| Награда | `_msg_reward`, `_msg_reward_solo` | **нет** (в QUESTS ссылки есть: `...golden_shield_test.txt:2221`, `2290`) | ⚠️ `pda_tip` тихо no-op |
| Провал | нет | `msg_fail` в QUESTS есть, строки нет | ⚠️ no-op |
| Экранирование | `«»`, `—` | `&quot;`, `&apos;`, `—` | ✅ (cp1251 0x97 = `—`, кодируется) |
| Кол-во строк | 32 ru / 32 en | 34 ru / 34 en | ✅ |

---

## 4. Аудит Lua-рантайма и Warfare-механик (Script Diff)

### 4.1. Спавн и контроль отрядов

| Механика | Эталон | Авто | Вердикт |
|---|---|---|---|
| `mark_task_squad` (защита от оффлайн-боёв) | есть, вызывается в `spawn_squad` и `freeze_squad` (`standart...txt:2330-2343`) | есть, вызывается в `spawn_task_squad` и `freeze_squad` (`lua_gen.py:290-302`, `334`, `355`) | ✅ **СОВПАДАЕТ** |
| `unmark_task_squad` | есть | есть + `unmark_quest_squads` (обход всех этапов) | ✅ (авто удобнее) |
| `freeze_squad` | **только при `squad.current_action == 1`** (`standart...txt:2386-2395`): | **безусловно** (`lua_gen.py:349-356`, артефакт `...:2617-2624`): | ⚠️ **РАСХОЖДЕНИЕ** |
| `smart_cleared` (`owning_faction` / `defense_count`) | `owning_faction == "army"` или `defense_count ~= nil and <= 0`; сперва проверка «враг мёртв»; `eid == 0` → false (`standart...txt:2416-2439`) | `stage_cleared`: идентичная логика (`lua_gen.py:387-401`) | ✅ **СОВПАДАЕТ** |
| Спавн «в базовом смарте» | `SIMBOARD:create_squad(base_smart, section)` + `set_target` + `stay_time` | то же + `force_online = true` | ✅ (авто чуть жёстче) |
| Спавн в `on_init` vs в `_status` | `q1_start` вызывает `q1_spawn_village()` сразу | спавн только в первом тике `_status` | ⚠️ при `world=true` и не-Warfare спавна не будет вовсе |

Цитата проблемного места (эталон):

```lua
local function freeze_squad(id)
	if not id or id == 0 then return end
	local squad = alife_object(id)
	if not squad then return end
	if squad.current_action == 1 then
		squad.stay_time = game.get_game_time()
		squad.force_online = true
		mark_task_squad(squad)
	end
end
```

Авто:

```lua
local function freeze_squad(id)
	if not id or id == 0 then return end
	local squad = alife_object(id)
	if not squad then return end
	squad.stay_time = game.get_game_time()
	pcall(function() squad.force_online = true end)
	mark_task_squad(squad)
end
```

**Последствие:** `freeze_stage_for` вызывается **каждый** тик `_status` (раз в 3 с) и
прибивает `stay_time` даже отряду, который ещё идёт к точке. `stay_time` — тот самый
флаг, который `smart_terrain_warfare.process_squads()` использует, чтобы «не трогать»
отряд; выставленный до прибытия, он может законсервировать отряд на спавне.

### 4.2. Условный спавн подкреплений во втором квесте (Вариант А vs Б)

| Аспект | Эталон | Авто |
|---|---|---|
| Где решается вариант | `q2_variant_solo()` → `db.actor:has_info("mymod_q2_solo")` (`standart...txt:2595-2611`) | вариант нигде не проверяется в Lua; выбор зашит в **разные реплики** |
| Спавн врага | `q2_spawn_atp()` — при старте квеста | `spawn_stage_for` по `warfare_capture` — при входе в этап 0 |
| Спавн союзников (А) | `spawn_ally(atp, K2_ALLY1/2)` + id в pstor | `SpawnSquad`×2 в `phrase_2_action` |
| Вариант Б | союзники не спавнятся | союзники не спавнятся (другая реплика) |
| Учёт id союзников | `vset(K2_ALLY1, squad.id)` | **не сохраняются** |
| Заморозка союзников | `freeze_squad(vget(K2_ALLY1))` каждый тик | **не замораживаются** (`ally_count=0` в `capture`) |
| Освобождение из `task_squads` | `q2_cleanup` по id | **не освобождаются** (id неизвестны) |

Артефакт авто — `...golden_shield_test.txt:3286-3299`:

```lua
local function mymod_atp_quest_take_assault_phrase_2_action(actor, npc, p)
	run_actions({
		{ kind = "spawn_squad", squad = "army_sim_squad_advanced", smart = "esc_smart_terrain_7_11" },
		{ kind = "spawn_squad", squad = "army_sim_squad_advanced", smart = "esc_smart_terrain_7_11" },
	}, actor or db.actor, npc)
end
```

**Вердикт:** из-за инцидента 1 этот код вообще не исполняется (второй `<action>`);
даже если бы исполнялся — союзники не попадают в pstor, не морозятся и навсегда
остаются в `sim_offline_combat.task_squads` (утечка + «залипшие» отряды в офлайне).

### 4.3. Вариативная награда (15 000 vs 30 000)

| Аспект | Эталон | Авто |
|---|---|---|
| Точка выдачи | `on_complete = %=mymod_atp_quest_reward()%` | `on_complete` — но `reward_money=0` |
| Вычисление | `local solo = q2_variant_solo(); local reward = solo and 30000 or 15000` (`standart...txt:2755-2771`) | Зашито в репликах: `amount = 15000` (`...:3432`) и `amount = 30000` (`...:3458`) |
| Устойчивость к смене варианта | высокая (поршень) | нулевая: если оба поршня висят, обе ветки покажутся, каждая начислит свою сумму |
| Очистка поршней варианта | `q2_cleanup` снимает `INFO_Q2_ASSAULT` и `INFO_Q2_SOLO` (`standart...txt:2741-2753`) | `_cleanup` снимает **только** `taken_info` (`...:3028-3039`) |
| Сообщение о награде | `pda_tip(solo and "..._reward_solo" or "..._reward")` | `pda_tip(quest.msg_reward)` → строки нет → no-op |

**Вердикт: [ЧАСТИЧНОЕ РАСХОЖДЕНИЕ] с элементами P1-бага.** Суммы 15 000/30 000
формально присутствуют, но: (а) не исполняются из-за дубля `<action>`; (б) не
привязаны к поршню в момент завершения; (в) поршни варианта не снимаются при
провале/отмене — после рестарта квеста оба варианта остаются «истинными».

### 4.4. `pstor` (`save_var`/`load_var`) и защита от коллизий с `task_id`

| Аспект | Эталон | Авто |
|---|---|---|
| Чтение/запись | `vget`/`vset` с защитой `if not db.actor` | идентично (`lua_gen.py:101-110`) |
| Схема ключей | 16 плоских констант `mymod_q1_v_spawn`, … | `stage_key(q, stage, suffix)` = `<prefix>_<quest>_v_<stage>_<suffix>` |
| Коллизия с `task_id` | исключена (ключи не равны id) | исключена: `golden_shield_test_mymod_av_quest_v_0_spawn` ≠ `mymod_av_quest` |
| Сброс при старте | явный сброс всех ключей в `q1_start`/`q2_start` | сброс `spawn/enemy/started/target_seen/ally*` + `_said` |
| Сохранение состояния предмета | `K2_ITEM` + идемпотентный `q2_give_item` | **нет ключа**; выдача привязана к `started` этапа 1 |
| Повторная выдача ПДА | каждый тик этапа 1, если предмета нет | **никогда** после первого тика |
| Очистка при завершении | `q1_cleanup`/`q2_cleanup` снимают поршни | снимают только `taken_info` |

Артефакт авто (`...golden_shield_test.txt:2407-2409`):

```lua
local function stage_key(q, stage, suffix)
	return q.key_prefix .. "_v_" .. tostring(stage) .. "_" .. suffix
end
```

**Вердикт:** защита от коллизий **реализована корректно и даже надёжнее эталона**
(пространство имён на квест). Но потерян `K2_ITEM`-эквивалент: если игрок выбросил
ПДА или он пропал при смерти, квест становится непроходимым.

### 4.5. Прочие расхождения рантайма (важные)

1. **Нет faction/Warfare-гейта в диалогах.** Эталон: `q1_can_take`/`q2_can_take`
   проверяют `is_warfare()` и `is_actor_army()` (`standart...txt:2777-2785`,
   `2808-2817`). Авто: `_can_take` проверяет только info-условия и `task_info`
   (`...golden_shield_test.txt:3465-3485`). Поршень `mymod_army_warfare_access`
   (`available_info`) **нигде не проверяется** — `lua_gen.py:1004` только кладёт его
   в таблицу. Итог: квест берёт любой персонаж; при этом `world=true` не даёт
   `_status` работать вне Warfare → квест «висит» навсегда.
2. **Off-by-one в `announce`.** `_advance_code` передаёт `next_data.msg`
   (`lua_gen.py:1313-1315`), то есть при завершении этапа 0 игрок видит сообщение
   этапа 1 («Захватить Элеватор»), а не «Деревня взята». Эталон передаёт сообщение
   о **взятой** точке (`standart...txt:2521`).
3. **Нет `q2_give_item`-логики** (см. 4.4).
4. **`is_actor_army` отсутствует полностью** — даже как хелпер.
5. **`RETURN_DISTANCE` и `reached_giver` — мёртвый код**: у обоих квестов
   `return_stage = -1` (`...golden_shield_test.txt:2302`, `2233`).
6. **`target_squad_dead`** — дополнительная механика, которой нет в эталоне;
   безопасна (см. `lua_gen.py:233-246`), но при `target_squad=""` всегда `false`.
7. **`world = true`** выставляется автоматически при любом `warfare_capture`
   (`lua_gen.py:1019-1022`) — совпадает с ручным `if not is_warfare() then return nil`.

---

## 5. Реестр пробелов документации (`docs/API_v2.md`)

| # | Место | Что написано сейчас | Почему вводит в заблуждение | Как переформулировать |
|---|---|---|---|---|
| D1 | §3.3, пример `API_v2.md:985-992` | В одной реплике два тега подряд: `<action>dialogs.deadcity_dushman_turnin_turn_in</action>` и `<action>dialogs.deadcity_dushman_turnin_phrase_2_action</action>` | Движок X-Ray хранит **одно** действие на реплику. Пример формирует у сценариста ложную модель «список действий в XML» | Добавить блок «**Один `<action>` на реплику**» и переписать пример: единственный `<action>dialogs.<dialog>_phrase_<n>_action</action>`, внутри которого `complete_task` + награды |
| D2 | §2.2 (`API_v2.md:258-259`) и §3.4 (`1110-1116`) | `GiveTask` → `<action>..._accept</action>`, `CompleteTask` → `<action>..._turn_in</action>`, остальные → Lua-функция | Не сказано, что при комбинации с другими действиями в одной реплике это порождает второй `<action>`, и он **молча теряется** | Явно: «`GiveTask`/`CompleteTask` **не** генерируют отдельный тег, если в реплике есть другие Lua-действия; все эффекты сливаются в одну функцию `dialogs.<dialog>_phrase_<n>_action` в порядке объявления» |
| D3 | §2.8 (`API_v2.md:673-675`) | «Не дублируйте награды… если задали `reward_money`/`reward_item_alias`, не добавляйте `GiveMoney`/`GiveItem` в диалоговые `actions`» | Формулировка подразумевает, что **без** `reward_*` награда в диалоге — рабочий путь. Именно так сделал сценарий → награда потеряна | Добавить: «Награда в `actions` реплики сдачи **не поддерживается**, если в этой же реплике есть `CompleteTask`. Единственный надёжный путь — `Quest.reward_money`/`reward_item_alias` (эффект `_reward`)» |
| D4 | §4.2 (`API_v2.md:1550-1562`) | Эталонный шаблон с `RemoveItem + GiveMoney + GiveItem + GiveInfo + CompleteTask` в одной реплике | Это ровно конфигурация инцидента 1. «Эталон» содержит баг | Переписать шаблон: `preconditions=[HasItem(...)]`, `actions=[CompleteTask(...)]`, а награда — через `reward_money`/`reward_item_alias`/`complete_info` |
| D5 | §2.7 (`API_v2.md:532-533`) | «Если `target_alias` пуст, `target_functor` возвращает `task_giver_id`» | Не описано поведение при `task_giver_id == 0/nil`; не требуется fallback на `get_story_object_id(Quest.npc_id)`; не сказано, что `0` — truthy и ломает резервную ветку | «Порядок: `tsk.task_giver_id` (если `> 0`) → `get_story_object_id(Quest.npc_id)` → `Quest.npc_id`, если это число → `nil`. Возврат `0`/`nil` заставляет Anomaly рисовать маркер на акторе» |
| D6 | §2.7 (`API_v2.md:524-530`) | «…Иначе → `alife():story_object(name).id`» | API принимает числовой story-ID; строковое имя надо резолвить через `get_story_object_id(name)` | Заменить на `get_story_object_id(name)` и добавить примечание про `get_story_object` |
| D7 | §2.8, таблица (`API_v2.md:670-671`) | `available_info`/`done_info`: «Зарезервировано… ядро только сохраняет значение» | Формально верно, но сценарий построил на этом **весь** гейт доступа («внешний скрипт выдаст поршень»), а внешнего скрипта в сборке нет и ядро его не проверяет | Добавить warning-блок: «`available_info` **не проверяется** сгенерированным кодом. Без собственного внешнего Lua-скрипта квест доступен всем. Для гейта используйте `Quest.available_info` + собственный `precondition`, либо добавьте `Stage`/`Quest`-условие `SmartOwner`/`HasInfo`» |
| D8 | §2.6 (`API_v2.md:483-493`) | «`spawn_stage_for` спавнит… `freeze_stage_for` замораживает…» | Не сказано, что союзники, спавненные через `SpawnSquad` в реплике, **не** попадают в `capture.ally_count` → не морозятся и не освобождаются | «Все квестовые отряды обязаны быть объявлены через `WarfareCapture.ally_squad_alias`/`ally_count`; `SpawnSquad` в реплике создаёт неуправляемый отряд (утечка в `sim_offline_combat.task_squads`)» |
| D9 | §3.4 (`API_v2.md:1118-1123`) | «`pda_tip` проверяет перевод… и не выводит строку, если перевода нет» | Это объясняет, почему потеря награды была **невидимой**: `msg_reward` в `st_*.xml` нет, подсказки нет, ошибок нет | Добавить: «Генератор **не** создаёт `_msg_reward`/`_msg_fail`; если вы их не добавили, игрок не получит уведомления о награде/провале. Сборщик обязан выдавать warning при отсутствии этих строк» |
| D10 | §2.5 (`API_v2.md:431-432`) и §3.3 | Не описано, чем закрывать **диалог сдачи** | Авто-слепок закрывает сдачу поршнем `*_ready`, который выдаётся `on_start_actions` этапа. Если действие не выполнилось — диалог недоступен навсегда | «Диалог сдачи обязан проверять **стадию задачи** (`<dialog_id>_can_turn_in` → `tsk.stage >= N`), а не поршень, выдаваемый в `on_start_actions`» |
| D11 | §2.7 (`API_v2.md:535-537`) | «`on_start_actions` выполняются… ровно один раз… сохраняется в pstor» | Не сказано, что при `world = true` и выключенном Warfare `_status` не тикает → действия **никогда** не выполнятся, а квест уже выдан | Добавить предупреждение и требование: «Если в квесте есть `warfare_capture`, все критичные поршни/предметы должны выдаваться в `on_init` (`init_actions`), а не в `on_start_actions`» |
| D12 | §2.2 (`API_v2.md:291-295`) | «Алиас разрешается… без БД строка используется как есть и сборка не падает» | Нет предупреждения, что несуществующая секция даёт **молчаливый** no-op (`give_item` логирует только `printe`) | «Добавьте build-time проверку секции; при отсутствии в БД — warning, а не тихий пропуск» |
| D13 | §3.5, правило 5 (`API_v2.md:1169`) | «`stage_complete` равен количеству этапов» | Формально верно, но эталон для Q2 использует **3** этапа там, где авто — 2, из-за чего теряется этап «сдать данные» | Добавить пример с 3 этапами и объяснить, что финальный этап «сдача» должен существовать явно, даже если сдача идёт диалогом |

---

## 6. Бэклог доработки ядра и компилятора (`src/core/`, `src/compiler/`)

### P0 — критично (без этого авто-слепок не повторяет эталон и ломает квесты)

| ID | Задача | Файл(ы) | Критерий приёмки |
|---|---|---|---|
| P0-1 | **Слияние действий реплики в один `<action>`.** Все эффекты `Phrase.actions` (включая `GiveTask`/`CompleteTask`/`GiveInfo`-эквиваленты, если они требуют порядка) генерировать в **одной** Lua-функции `dialogs.<dialog>_phrase_<n>_action`; XML — не более одного `<action>` на реплику | `src/compiler/xml_gen.py`, `src/compiler/lua_gen.py::_build_dialog_functions` | В `dialogs_*.xml` нет реплик с 2 `<action>`; сдача Q1 выдаёт 10 000 ₽ + `wpn_vssk` |
| P0-2 | **Резолв story-ID по имени.** Заменить `alife():story_object(name)` на `get_story_object_id(name)` / `get_story_object(name)`; `resolve_target` и `resolve_alife_object` | `lua_gen.py:124-136`, `190-230` | `resolve_target("esc_3_16_military_trader")` возвращает id Журова; unit-тест с фейковым story-объектом |
| P0-3 | **Запретить `giver_id = 0`.** `give_task`: `npc` нормализовать через `dialogs.who_is_npc`, при неудаче — `get_story_object_id(Quest.npc_id)`; если id не найден, **не** писать 0 (оставить `nil`) | `lua_gen.py:500-519` | В сгенерированном коде нет `= 0` для giver; маркер на Журове |
| P0-4 | **Контракт `target_alias=""`.** Явная цепочка `task_giver_id (>0) → get_story_object_id(npc_id) → nil`; `0` считать отсутствующим (`if id and id ~= 0`) | `lua_gen.py:1113-1135` | Этап «вернуться» даёт id квестодателя даже после перезагрузки |
| P0-5 | **Награда сдачи — только через `_reward`.** Валидатор: если в реплике есть `CompleteTask` и одновременно `GiveMoney`/`GiveItem`/`TakeItem` — либо ошибка сборки, либо автоперенос в `on_complete_actions` | `src/core/models.py` (validator), `lua_gen.py` | Сборка `build_golden_test.py` либо падает с понятной ошибкой, либо генерирует награду в `_reward` |
| P0-6 | **Faction/Warfare-гейт как первоклассная модель.** Поля `Quest.requires_faction`, `Quest.requires_warfare` → в `_can_take` добавлять `is_actor_army()` и `IsWarfare()`; `available_info` оставить как «внешний маркер», но не как единственный гейт | `models.py`, `lua_gen.py` | Не-армейский персонаж не видит диалог; вне Warfare квест не выдаётся, а не «висит» |
| P0-7 | **Учёт союзников вне `WarfareCapture`.** `Stage.ally_squad_alias/ally_count` (или `SpawnSquad` с авто-регистрацией): id в pstor, заморозка, освобождение | `models.py::Stage`, `lua_gen.py` | Q2 «штурм»: 2 союзника заспавнены, заморожены, освобождены после сдачи; в логе есть их id |

### P1 — важно (поведение эталона, но без мгновенного блока)

| ID | Задача | Файл(ы) | Критерий |
|---|---|---|---|
| P1-1 | `freeze_squad` — вернуть guard `squad.current_action == 1` | `lua_gen.py:349-356` | Отряды не «залипают» на спавне; в логе отряд доходит до смарта |
| P1-2 | Генерация `squad_descr_<slug>.ltx` из модели (`ModProject.squads` / `Quest.custom_squads`) | `models.py`, `builder`, `xml_gen/lua_gen` | Кастомная секция отряда попадает в выходной `gamedata/configs/misc/squad_descr/` |
| P1-3 | Идемпотентная выдача квестового предмета: pstor-ключ `item`, повторная выдача в `_status`, если предмета нет | `lua_gen.py` (`_build_quest_data`, `start_actions`) | Выброшенный ПДА возвращается; Q2 проходим |
| P1-4 | `_cleanup` снимает **все** поршни варианта (`assault`/`solo`), а не только `taken_info` | `lua_gen.py::_reward/_cleanup` | После провала Q2 повторное взятие не тащит старый вариант |
| P1-5 | `announce` — сообщение **текущего** (завершённого) этапа, не следующего | `lua_gen.py::_build_advance_code` | Завершение этапа 0 Q1 → «Деревня взята», а не «Захватить Элеватор» |
| P1-6 | Автогенерация `_msg_reward`/`_msg_fail` (или build-warning при их отсутствии) | `xml_gen.py` (st) + валидатор | В `st_*.xml` есть строки; в игре виден tip о награде |
| P1-7 | Диалог сдачи закрывать по `tsk.stage >= N`, а не по поршню из `on_start_actions` | `xml_gen.py`/`lua_gen.py` | Сдача доступна и после save/load без тика `_status` |
| P1-8 | Критичные действия (`give_info ready`, `give_item`) переносить в `init_actions`/`on_init` при `world=true` | `lua_gen.py` | Вне Warfare квест не выдаётся, а если выдан — поршни уже стоят |
| P1-9 | Убрать дублирование условий: `_can_take` + `<dont_has_info>` одновременно | `xml_gen.py` | Нет реплик/диалогов с избыточными тегами |

### P2 — желательно (качество, совместимость, поддерживаемость)

| ID | Задача | Критерий |
|---|---|---|
| P2-1 | `icon` по умолчанию из `Quest.icon` + предупреждение при использовании дефолта | У Q1/Q2 разные иконки, как в эталоне |
| P2-2 | Шапка-комментарий в `tm_*.ltx` (что делает квест) | LTX читаем без Lua |
| P2-3 | Удаление мёртвых регистраций (`*_can_turn_in` без ссылки из XML, `*_quest_accept`) | Нет «registered but unused» |
| P2-4 | Build-grep-линт: каждый `dialogs.*` из XML существует в `register()`, и наоборот | Автотест на кросс-ссылки |
| P2-5 | Валидация секций предметов/отрядов/смартов по `anomaly_db.sqlite` | Warning на неизвестную секцию |
| P2-6 | Документировать кодировку `—`/`«»` в cp1251 | Раздел в §3.6 |
| P2-7 | Тест «нет реплики с >1 `<action>`» в CI | Защита от регрессии P0-1 |
| P2-8 | Явный этап «сдача» в примерах (3 этапа, как в эталоне Q2) | Пример в §4.2 и §3.5 |

---

## 7. План верификации (Definition of Done)

Аудит считается закрытым, когда **новый** авто-слепок (пересобранный
`python examples/build_golden_test.py`) проходит все пункты. Проверки
сформулированы так, чтобы их можно было автоматизировать.

### 7.1. Статические проверки слепка

- [ ] **V1. Один `<action>` на реплику.** Парсер XML: для каждого `<phrase>`
      `count(<action>) <= 1`. Ожидается `0` нарушений (сейчас 4).
- [ ] **V2. Один `<precondition>` на реплику/диалог**, порядок тегов
      `text → next → precondition → has_info → give_info → action`.
- [ ] **V3. Кросс-ссылки XML→Lua.** Каждый `dialogs.<name>` из
      `dialogs_golden_shield_test.xml` присутствует в `register()`
      сгенерированного скрипта; обратных «сирот» нет.
- [ ] **V4. Награда Q1 в `_reward`.** `QUESTS.mymod_av_quest.money == 10000` и
      `QUESTS.mymod_av_quest.item == "wpn_vssk"` **или** единственное действие
      реплики сдачи вызывает `complete_task` + `give_money(10000)` +
      `give_item("wpn_vssk", 1)` в одной функции.
- [ ] **V5. Нет `giver_id = 0`.** `grep -c "= 0" ` по блоку `give_task` → 0;
      `grep "alife():story_object(target)"` → 0, вместо него
      `get_story_object_id`.
- [ ] **V6. Резолв цели.** В сгенерированном `mymod_av_quest_target` для этапа 2
      присутствует fallback `get_story_object_id`, и `0` трактуется как
      отсутствие (`if id and id ~= 0`).
- [ ] **V7. `stage_complete`.** Q1: 3 при трёх этапах; Q2: 3 при трёх этапах
      (этап «сдать данные» восстановлен) — либо документировано решение о 2.
- [ ] **V8. `dont_send_update_news = true`** и `condlist_0` с
      `{!task_giver_alive(<id>)} fail` в обеих секциях.
- [ ] **V9. `squad_descr_*.ltx`.** При объявлении кастомного отряда в модели
      появляется файл и секция; без объявления — файла нет и это отражено в логе.
- [ ] **V10. `st_*.xml`.** Присутствуют `_msg_reward`, `_msg_fail`,
      `_descr_solo`/`_descr_assault` (или сборщик выдаёт warning об их отсутствии).
- [ ] **V11. Нет дублей** `<actor_dialog>` в `character_desc_escape.xml`;
      порядок соответствует `take → take_assault → take_solo → turnin`.
- [ ] **V12. `system.ltx`.** `dialogs_golden_shield_test` встречается ровно один
      раз в `[dialogs] files`; `character_desc_escape` — ровно один раз в
      `[profiles] specific_characters_files`.

### 7.2. Динамические проверки (ручной прогон в игре)

- [ ] **V13. Q1, сдача.** Забрать квест у Журова → захватить деревню → Элеватор →
      вернуться. В инвентаре: `wpn_vssk` ×1 и +10 000 ₽; в КПК виден tip о
      награде; Q2 разблокирован (`mymod_quest_1_done`).
- [ ] **V14. Q1, маркер.** На этапе «Вернуться к майору Журову» жёлтый маркер
      стоит **на Журове**, не на игроке. Проверить после save/load.
- [ ] **V15. Q2, вариант А.** Выбрать «штурм» → у АТП появляются **2** союзных
      отряда, доходят до точки, не «залипают» на спавне; после сдачи в логе
      `..._ally1/2` освобождены (нет записей в `sim_offline_combat.task_squads`).
- [ ] **V16. Q2, вариант Б.** Выбрать «соло» → союзников нет; награда 30 000 ₽,
      ПДА изъят. Для варианта А — 15 000 ₽, ПДА изъят.
- [ ] **V17. Провал/повтор.** Провалить Q2 (убить Журова или отменить) → поршни
      `mymod_q2_assault`/`mymod_q2_solo` сняты; повторное взятие не тащит старый
      вариант; награда не удваивается.
- [ ] **V18. Гейт доступа.** Не-армейский персонаж не видит диалоги; персонаж
      армии вне Warfare не может взять квест (и не получает «висящий» квест).
- [ ] **V19. Потеря предмета.** Выбросить ПДА на этапе сдачи Q2 → предмет
      возвращается на следующем тике `_status` (или документировано обратное).
- [ ] **V20. Оффлайн.** Уйти с уровня на этапе захвата, вернуться → квестовые
      отряды живы в том же состоянии, этап не перескочил.

### 7.3. Формальный результат

- [ ] **V21.** `docs/GOLDEN_DIFF_AUDIT.md` (этот файл) приложен к задаче;
      пункты 1–7 закрыты.
- [ ] **V22.** Пересобранный слепок сохранён как
      `tools/manual_mod_snapshot_golden_shield_test_v2.txt`; diff по пунктам
      V1–V12 приложен.
- [ ] **V23.** В `docs/API_v2.md` внесены правки D1–D13 (или заведены issues с
      теми же ID).

---

## Приложение A. Карта «дефект → место в коде → следствие»

| Дефект | Место | Следствие |
|---|---|---|
| Дубль `<action>` | `lua_gen.py:1449-1453` + XML-генератор | Инцидент 1; потеря подкрепления Q2; потеря денег Q2 |
| `alife():story_object(<имя>)` | `lua_gen.py:134`, `196` | Story-ID не резолвится → `giver_id = 0` |
| `giver_id = 0` | `lua_gen.py:517` | 0 truthy → fallback недостижим → маркер на игроке |
| `_target` возвращает `task_giver_id` без проверки | `lua_gen.py:1133` | Инцидент 2 |
| `money=0`, `item=""` | `lua_gen.py:1009-1011` | `_reward` пуст → награда только из реплики, а она теряется |
| `freeze_squad` без `current_action` | `lua_gen.py:349-356` | Отряды консервируются до прибытия |
| Нет faction-гейта | `lua_gen.py:1359-1377` | Квест доступен всем; вне Warfare «висит» |
| Союзники Q2 вне `capture` | `lua_gen.py:359-376` | Утечка `task_squads`, нет заморозки/освобождения |
| Нет `K2_ITEM`-эквивалента | `lua_gen.py` (start_actions) | Потеря ПДА → квест непроходим |
| `announce(next_data.msg)` | `lua_gen.py:1313-1315` | Неверный текст сообщения этапа |
| Нет `squad_descr` | модель/сборщик | Нельзя объявить квестовый отряд |

## Приложение B. Что НЕ является дефектом (снято с подозрения)

1. **`pstor`-ключи** — пространство имён `golden_shield_test_<quest>_v_<stage>_<suffix>`
   корректно защищено от очистки `task_manager` по `task_id`.
2. **`smart_cleared` / `stage_cleared`** — логика (`owning_faction == "army"` или
   `defense_count <= 0` при мёртвом враге) полностью повторяет эталон.
3. **`mark_task_squad` / `unmark_*`** — реализованы, вызываются в нужных местах.
4. **`system.ltx`** — патч идемпотентен, дублей нет, `[profiles]` не испорчен.
5. **Кодировка/экранирование** — cp1251 + XML-сущности корректны; `—` кодируется
   байтом 0x97.
6. **Порядок `<actor_dialog>`** — авто-слепок соответствует §2.5 лучше, чем эталон.
7. **`GiveInfo` в реплике** — нативный тег, работает.
8. **`on_fail`/`on_cancel` → `_cleanup`** — имена и форма `%=...()%` совпадают.

---

*Конец отчёта. Файл создан без изменений в коде проекта.*
