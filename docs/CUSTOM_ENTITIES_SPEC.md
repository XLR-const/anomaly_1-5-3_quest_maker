# Спецификация кастомных NPC и отрядов (Anomaly 1.5.3)

Статус: **Фаза 3.5 — финализация спецификации**.
Документ фиксирует только то, что подтверждено чтением конкретных файлов.
Всё, что не удалось проверить, помечено `[ТРЕБУЕТ ПРОВЕРКИ]` и **не должно**
реализовываться «по догадке». Раздел иммунитетов/бессмертия закрыт
подтверждёнными данными (§1.5, §5).

Источники (единственные прочитанные файлы):

| Файл | Что дал |
|---|---|
| `_unpacked/configs/system.ltx` (1–130) | порядок `#include`, секция `[profiles]` |
| `_unpacked/configs/creatures/spawn_sections.ltx` | список инклюдов, отсутствие wildcard |
| `_unpacked/configs/creatures/spawn_sections_escape.ltx` (1–60) | синтаксис секций NPC |
| `_unpacked/configs/creatures/spawn_sections_general.ltx` (1–70) | `stalker_silent`, `default_*`, `stalker_regular` |
| `_unpacked/configs/creatures/stalkers.ltx` | только 6 `#include`; сам секций не содержит |
| `_unpacked/configs/creatures/m_stalker.ltx` (224–253, 325–364, 530–699) | базовый `[stalker]`, `stalker_sakharov`, `stalker_die_hard`, полные секции иммунитетов |
| `_unpacked/configs/creatures/immunities.ltx` (1–65) | шкала сопротивлений, 9 полей иммунитета, `[strelok_resistance]` |
| `_unpacked/configs/gameplay/character_desc_escape.xml` (1–70) | синтаксис `<specific_character>` |
| `_unpacked/configs/gameplay/npc_profile.xml` (1–120, 515–539, 703–732) | реестр `<character>` |
| `src/db/repository.py` | реальные колонки `npcs`/`squads`/`aliases` |
| `src/core/models.py` | текущий `CustomSquad`, `ModProject`, конфиг Pydantic |

---

## 0. TL;DR — что подтверждено на 100%

1. `spawn_sections.ltx` **не содержит wildcard**. Это плоский список из 28 строк
   `#include "spawn_sections_<level>.ltx"` (`spawn_sections.ltx:1-28`).
   Новый файл `spawn_sections_<slug>.ltx` сам по себе **не подхватится**.
2. `system.ltx` подключает `creatures\spawn_sections.ltx` одной строкой
   (`system.ltx:48`). Wildcard-инклюдов для spawn-секций нет.
3. **Регистрация NPC состоит из трёх реестров**, и все три — явные списки
   без глобов:
   * `[profiles] files` → XML-файлы `<character>` (`system.ltx:98`);
   * `[profiles] specific_characters_files` → XML-файлы
     `<specific_character>` (`system.ltx:99`);
   * `#include` внутри `spawn_sections.ltx` (`:1-28`).
4. Секция NPC в `spawn_sections_*.ltx` — это `[<section_id>]:<parent>`, где
   обязательны как минимум `$spawn`, `character_profile`, `spec_rank`,
   `community`; `story_id` и `immunities_sect` — опциональны
   (`spawn_sections_escape.ltx:1-53`). `story_id` в ваниле совпадает с именем
   секции.
5. `<specific_character>` требует `id`, а `id` обязан совпадать со значением
   `character_profile` из spawn-секции. Внутри используются
   `<name>`, `<icon>`, `<bio>`, `<class>`, `<community>`, `<map_icon>`,
   `<terrain_sect>`, `<visual>`, `<rank>`, `<reputation>`, `<money>`,
   `<supplies>`, `<start_dialog>`, `<actor_dialog>`
   (`character_desc_escape.xml:6-70`). XML в **windows-1251** (`:1`).
6. **`npc_profile.xml` обязателен.** Это отдельный реестр
   `<character id="<profile>"><class>...</class>
   <specific_character>...</specific_character></character>`
   (`npc_profile.xml:5-8, 521-537`). Без записи в нём движок не свяжет
   `character_profile` с профилем. В отличие от `character_desc_*.xml`, этот
   файл в **UTF-8** (`:1`).
7. В БД у `npcs`/`squads` **нет** полей внешности/профиля. `repository.py`
   знает только `npcs(id, name_ru, faction, location_prefix, role, source_file)`
   и `squads(id, faction, npc_list, is_safe_field, source_file)`
   (`repository.py:238-243, 444-456, 639`). Значит, `visual/icon/bio/rank/
   reputation/money/supplies` компилятор обязан брать из YAML-оверрайдов или
   дефолтов, а не из БД.
8. `CustomNpc` в `src/core/models.py` **отсутствует**. Есть только
   `CustomSquad` (`models.py:1041-1154`) и `ModProject` с полями
   `quests/dialogs/squads` (`models.py:1173-1188`).
9. **`stalker_silent` — это НЕ бессмертие.** Секция `[stalker_silent]:stalker`
   лишь обнуляет все `sound_*` (крики, тревоги, реакции), а профиль берёт у
   `sim_default_stalker_0` (`spawn_sections_general.ltx:1-34`). Бессмертие
   делается **только** через `immunities_sect`: секция с `0.0` по всем типам
   урона. Подтверждённые «полностью неубиваемые» секции —
   `[stalker_immunities_sakharov]` (`m_stalker.ltx:562-572`) и
   `[stalker_immunities_die_hard]` (`m_stalker.ltx:622-632`); обе задают
   `0.0` для всех 9 полей **включая** `telepatic_immunity` и
   `wound_2_immunity` (§1.5, §5).

---

## 1. Механизм регистрации в Anomaly 1.5.3

### 1.1. `spawn_sections`: wildcard или явный инклюд?

**Подтверждено:** wildcard **отсутствует**. Ванильный файл — это ровно 28
явных инклюдов:

```
#include "spawn_sections_general.ltx"
...
#include "spawn_sections_escape.ltx"
...
#include "spawn_sections_lostzone.ltx"
```
(`spawn_sections.ltx:1-28`)

Следствие: `#include "spawn_sections_<slug>.ltx"` **не появится сам**.
Нужен один из двух вариантов:

* **A (предпочтительно): патч-инклюд.** Компилятор формирует
  `spawn_sections_<slug>.ltx` и добавляет в `spawn_sections.ltx` одну строку
  `#include "spawn_sections_<slug>.ltx"` (без пути — файл лежит рядом).
* **B: полная замена `spawn_sections.ltx`** копией ванильного файла с
  добавленной строкой. Допустимо, но конфликтует с другими модами.

Патч должен быть идемпотентным: искать строку по точному имени и не
добавлять второй раз.

> Контраст: `CustomSquad` в `models.py:1044-1049` утверждает, что
> `squad_descr_*.ltx` подключается глобом ванильного `squad_descr.ltx`.
> Это утверждение докстринга, **отдельно нами не проверялось**; для
> spawn-секций глоба точно нет.

### 1.2. Регистрация профиля: `npc_profile` + `character_desc`

**Подтверждено.** `system.ltx` содержит два независимых реестра XML:

```ini
[profiles]
files                     = npc_profile, npc_profile_mlr, npc_profile_lostzone
specific_characters_files = character_desc_general, character_desc_marsh, ...,
                            character_desc_escape, ..., character_desc_lostzone_hb
```
(`system.ltx:97-99`)

Оба значения:

* перечисляются **через запятую**, **без `.xml`**;
* не поддерживают wildcard — только явное дописывание имени.

**Роль `files` (`npc_profile*.xml`).** Это карта «профиль → класс/профиль»:

```xml
<character id="esc_2_12_stalker_trader">
    <class>stalker</class>
    <specific_character>esc_2_12_stalker_trader</specific_character>
</character>

<character id="esc_2_12_stalker_wolf">
    <class>esc_2_12_stalker_wolf</class>
</character>
```
(`npc_profile.xml:521-530`)

Наблюдения:

* `id` — это значение `character_profile` из spawn-секции.
* `<specific_character>` **опционален**. У уникальных сюжетных NPC (Волк,
  Нимбль, Фанат, Сахаров) его нет — движок неявно использует `id`
  (`npc_profile.xml:525-533, 710-712`).
* У Сидоровича `<class>stalker</class>` + явный
  `<specific_character>esc_2_12_stalker_trader</specific_character>`
  (`:521-524`) — так связывают «роль» и конкретный профиль.
* `stalker_silent` в `npc_profile.xml` **не зарегистрирован**: он использует
  `character_profile = sim_default_stalker_0`, то есть уже существующий
  sim-профиль (`spawn_sections_general.ltx:1-3`). Отсюда правило: регистрировать
  надо именно `character_profile`, а не имя spawn-секции.

**Роль `specific_characters_files`.** Здесь лежат файлы с
`<specific_character id="...">`. `id` обязан совпадать с `character_profile`
(и, как правило, с `id` записи в `npc_profile`).

**Правильная схема для мода (без правки ванильных файлов):**

1. `gameplay/npc_profile_<slug>.xml` — по записи на каждого NPC:
   ```xml
   <character id="<character_profile>">
       <class><npc_class></class>
       <specific_character><character_profile></specific_character>
   </character>
   ```
   (при уникальном NPC можно опустить `<specific_character>` и оставить только
   `<class>` = id — как у Волка).
2. `gameplay/character_desc_<slug>.xml` — `<specific_character>`.
3. В `system.ltx` дописать **оба** имени: `npc_profile_<slug>` в `files` и
   `character_desc_<slug>` в `specific_characters_files`.

Патчи `system.ltx` идемпотентны: проверить вхождение имени, иначе дописать
через запятую.

### 1.3. Синтаксис spawn-секции NPC

Подтверждённые формы (`spawn_sections_escape.ltx:1-53`):

```ini
[esc_2_12_stalker_nimble]:stalker_immune_anomaly
$spawn                     = "respawn\esc_2_12_stalker_nimble"
character_profile          = esc_2_12_stalker_nimble
spec_rank                  = novice
community                  = stalker
story_id                   = esc_2_12_stalker_nimble
```

```ini
[devushka]:stalker
$spawn                     = "respawn\devushka"
immunities_sect            = stalker_immunities_greh_master
character_profile          = devushka
story_id                   = devushka
community                  = stalker
```

```ini
[esc_3_16_military_trader]:stalker
$spawn                     = "respawn\esc_3_16_military_trader"
character_profile          = esc_3_16_military_trader
community                  = stalker
story_id                   = esc_3_16_military_trader
```

Дополнительно из `spawn_sections_general.ltx:1-62`:

```ini
[stalker_silent]:stalker
$spawn        = "respawn\stalker_silent"
character_profile = sim_default_stalker_0
; ... все sound_* = пусто ...

[stalker_regular]:stalker
$spawn        = "respawn\dolg_regular"
character_profile = default

[stalker_monolith_default]:stalker
$spawn        = "respawn\stalker_monolith_default"
character_profile = sim_default_monolith_0
```

Выводы:

* Родитель (`:stalker`, `:stalker_strong`, `:stalker_immune_anomaly`,
  `:stalker_silent`) задаёт базовый набор параметров. Базовый `[stalker]`
  объявлен **не в `stalkers.ltx`**: тот состоит всего из шести `#include`
  (`m_stalker.ltx`, `m_person.ltx`, `immunities.ltx`, `damages.ltx`,
  `m_stalker_zombied.ltx`, `m_stalker_monolith.ltx`;
  `stalkers.ltx:1-6`). Значит, `[stalker]` и секции иммунитетов лежат в
  `m_stalker.ltx` / `immunities.ltx` — **подтверждено** (§1.5, §5).
* `$spawn` в ваниле **всегда** указывает на `respawn\<section_id>`.
  Обязан ли движок иметь реальный spawn-ресурс по этому пути или достаточно
  строки — `[ТРЕБУЕТ ПРОВЕРКИ]`. Безопасная стратегия: `$spawn =
  "respawn\<custom_id>"`; **не переиспользовать** `$spawn` ванильного
  сюжетного NPC.
* `character_profile` — это **id** записи в `npc_profile*.xml` и
  `<specific_character>`.
* `spec_rank` — метка (`novice`, `regular`, `veteran`, `master`), тогда как
  `<rank>` в XML — абсолютное число (`17568`, `18846`). Это разные поля.
* `community` — техническое имя фракции (`stalker`, `trader`, ...).
* `story_id` опционален, но для квестодателя обязателен по смыслу: на него
  ссылаются `task_giver_alive`, `get_story_squad`, `SpawnNpcItem.target_alias`.
* `immunities_sect` — ссылка на секцию иммунитетов (единственный
  подтверждённый рычаг «неубиваемости», см. §1.5).

### 1.4. Синтаксис `<specific_character>`

Подтверждено (`character_desc_escape.xml:1-70`):

```xml
<?xml version='1.0' encoding="windows-1251"?>
<xml>

  <specific_character id="esc_2_12_stalker_trader" no_random="1">
    <name>escape_trader_name</name>
    <icon>ui_inGame2_sid</icon>
    <bio>escape_trader_bio</bio>
    <class>trader</class>
    <community>trader</community>
    <map_icon x="1" y="0"/>
    <terrain_sect>stalker_terrain</terrain_sect>
    <visual>actors\stalker_trader\stalker_trader_1</visual>
    <rank>18846</rank>
    <reputation>2302</reputation>
    <money min="1000000" max="1000000" infinitive="1"/>
    <supplies>
      [spawn] \n
    </supplies>
#include "gameplay\character_criticals.xml"

    <start_dialog>esc_2_12_stalker_trader_start_dialog</start_dialog>
    <actor_dialog>dm_init_trader</actor_dialog>
    ...
  </specific_character>
```

Наблюдения:

* `name`, `icon`, `bio` — **строковые id локализации**, а не текст.
* `<class>` в ваниле бывает двух видов: роль (`trader`) или имя секции
  (`esc_2_12_stalker_wolf`, `:58`). Для кастомного уникального NPC безопасно
  ставить `<class>` = `id` секции.
* `no_random="1"` исключает персонажа из случайной генерации — то, что нужно
  квестодателю. `team_default="1"` (`:54`) — другой режим.
* `<supplies>` содержит литеральные строки `[spawn] \n <section> \n ...`;
  пустой инвентарь допустим (`[spawn] \n`).
* `#include` внутри `<specific_character>` поддерживается и вставляет
  соседние теги (`character_criticals.xml`, `:21`).
* `<map_icon>` присутствует почти всегда; точная обязательность
  `[ТРЕБУЕТ ПРОВЕРКИ]`.

**Безопасный минимальный набор для генератора** (надмножество всех трёх
примеров):

```
id, name, icon, bio, class, community, terrain_sect, visual,
rank, reputation, money, supplies
```
Плюс для квестодателя: `start_dialog`, один или несколько `actor_dialog`,
`no_random="1"`.

### 1.5. Бессмертный квестодатель (`immortal`) и удержание на `spawn_smart`

**Подтверждено.**

* Тега `immortal` нет ни в `character_desc_escape.xml`, ни в spawn-секциях.
  Движок не знает флага «бессмертный»: единственный конфигурационный рычаг —
  строка `immunities_sect` в spawn-секции (`spawn_sections_escape.ltx:38`,
  `m_stalker.ltx:560, 576, 620, 636, 679`).
* **`stalker_silent` — не бессмертие.** Он обнуляет только звуки
  (`spawn_sections_general.ltx:1-34`). Не использовать его как «immortal».

**Анатомия секции иммунитетов.** Секция — обычная LTX-секция без родителя;
имя произвольное. В `immunities.ltx:1-43` используются 9 полей
(шкала `no_resistance` → `high_resistance`, значения монотонно убывают):

| Поле | Смысл |
|---|---|
| `burn_immunity` | ожог/термический урон |
| `strike_immunity` | удар/укус |
| `shock_immunity` | электрошок |
| `wound_immunity` | пулевой/осколочный урон |
| `radiation_immunity` | радиация |
| `telepatic_immunity` | пси-урон |
| `chemical_burn_immunity` | химический ожог |
| `explosion_immunity` | взрыв |
| `fire_wound_immunity` | огнестрельная рана |

Семантика: **`1.0` — полная восприимчивость (нет сопротивления),
`0.0` — полная неуязвимость к типу урона.** Поэтому «бессмертие» = `0.0`
по **всем** полям. В секциях `m_stalker.ltx` дополнительно встречается
`wound_2_immunity` (`:572, 616, 632, 675, 691`) — десятое поле, которого нет
в базовой шкале `immunities.ltx`. Для полной неуязвимости его тоже надо
ставить в `0.0`.

**Эталонные секции:**

| Секция | Файл:строки | Набор | Итог |
|---|---|---|---|
| `[strelok_resistance]` | `immunities.ltx:49-58` | 8 полей `0.0`, но `telepatic_immunity = 1.0` | **НЕ полное бессмертие** (пси-урон проходит) |
| `[stalker_immunities_sakharov]` | `m_stalker.ltx:562-572` | все 9 + `wound_2_immunity` = `0.0` | **полное бессмертие** |
| `[stalker_immunities_die_hard]` | `m_stalker.ltx:622-632` | все 9 + `wound_2_immunity` = `0.0` | **полное бессмертие** |
| `[stalker_immunities_strelok]` | `m_stalker.ltx:606-616` | 9 × `0.0` (вкл. `wound_2`), `telepatic_immunity = 1.0` | не полное (пси-урон) |
| `[stalker_immunities_strong]` | `m_stalker.ltx:681-691` | `0.25…0.5` | усиленный, но убиваемый |

**Как это использовать при `immortal=True`.** Не ссылаться на
`strelok_resistance` (в нём `telepatic_immunity = 1.0`) и не полагаться на
чужую ванильную секцию. Компилятор генерирует **собственную** секцию,
дословно повторяя `stalker_immunities_sakharov` / `_die_hard`:

```ini
[<slug>_immunities_immortal]
burn_immunity            = 0.0
strike_immunity          = 0.0
shock_immunity           = 0.0
wound_immunity           = 0.0
radiation_immunity       = 0.0
telepatic_immunity       = 0.0
chemical_burn_immunity   = 0.0
explosion_immunity       = 0.0
fire_wound_immunity      = 0.0
wound_2_immunity         = 0.0
```

и ставит в spawn-секцию `immunities_sect = <slug>_immunities_immortal`.
Если `immunities_sect` задан явно — используется он, а `immortal=True`
лишь валидируется (`CAT-CUSTOM-006`).

**Порядок объявления важен.** X-Ray разбирает LTX текстуально, поэтому
секция иммунитетов должна быть объявлена **раньше** ссылающейся на неё
spawn-секции. Практика: генерировать `[<slug>_immunities_immortal]` в начале
`spawn_sections_<slug>.ltx` (или в отдельном `immunities_<slug>.ltx`,
подключённом `#include` первой строкой файла) — до секций `[<id>]:<parent>`.

**Ограничение области действия.** Иммунитеты гасят урон; они не отменяют
скриптовое убийство/деспавн и не удерживают NPC на смарте. Удержание —
отдельная runtime-логика (ниже).

**Удержание на смарте** — это runtime-логика, а не конфиг. Кандидаты:

* одиночный NPC, заспавненный скриптом в точке смарта с периодическим
  возвратом позиции;
* одиночный Story-отряд (`CustomSquad`) с `target_smart`, чтобы `SIMBOARD`
  держал его на смарте.

Точный API и поведение `smart_terrain` — `[ТРЕБУЕТ ПРОВЕРКИ]`, но
существующие `SpawnSquad`/`SpawnNpcItem`/`ClearSmart` (`models.py:279-383`)
уже дают нужные примитивы.

**Совместимость с `ClearSmart`:** если квестодатель стоит на смарте, который
чистится, нужен `allow_giver_smart=True`, иначе `XrayLinter` даёт
`ERROR XRAY-SPAWN-001` (`models.py:321-357`). Валидатор `CAT-CUSTOM-*` обязан
это проверять.

---

## 2. Что есть и чего нет в `data/anomaly_db.sqlite`

По `src/db/repository.py` (единственный источник схемы в этой фазе):

| Таблица | Колонки, которые точно используются | Источник |
|---|---|---|
| `npcs` | `id`, `name_ru`, `faction`, `location_prefix`, `role`, `source_file` (+ любые `n.*`) | `repository.py:238-245, 412-420, 517-530` |
| `smarts` | `id`, `name_ru`, `location_prefix`, `source_file` | `repository.py:422-432, 494-509` |
| `items` | `id`, `name_ru`, `category`, `cost`, `source_file` | `repository.py:433-443, 633-637` |
| `squads` | `id`, `faction`, `npc_list` (TEXT через запятую), `is_safe_field` (0/1), `source_file` | `repository.py:444-456, 536-555, 576-581` |
| `aliases` | `alias`, `entity_type` (`npc`/`smart`/`item`/`squad`), `entity_id` | `repository.py:92-109, 310-380` |
| `locations` | `prefix`, `name_ru` | `repository.py:483-492` |

Чего для профиля **нет** (репозиторий таких полей не выбирает):

* `visual` (путь модели);
* `icon`, `bio`, `name` (id локализации);
* `class`, `terrain_sect`, `snd_config`, `crouch_type`, `map_icon`;
* `rank`, `reputation`, `money`;
* `supplies` (стартовый инвентарь NPC);
* `immunities_sect`, `immortal`.

Поэтому `CustomNpc` должен **сам** содержать эти поля (с дефолтами), а БД —
использоваться только для `id`/`name_ru`/`faction`/`location_prefix`/`role`.
Исключение — режим `template_npc_id`: колонка `npcs.source_file` даёт точное
имя XML-файла с `<specific_character>` шаблона, и недостающие
`visual/icon/bio/rank/reputation/money/supplies` читаются из него (§3.2).
Модели Pydantic уже настроены на `extra="allow"` (`models.py:48-53`), так что
если в БД всё же окажутся дополнительные колонки, они не потеряются. Точный
DDL базы в этой фазе **не проверялся** (`[ТРЕБУЕТ ПРОВЕРКИ]`, при желании —
отдельный read-only `PRAGMA table_info`).

---

## 3. Контракт моделей

### 3.1. `CustomSquad` — как есть + `template_squad_id`

`models.py:1041-1154`. Поля:

`id`, `faction`, `npc`, `npc_random`, `npc_in_squad`, `target_smart`,
`relationship`, `idle_time`, `spawn_point`, `story_id`, `death_infos`.

**Новое опциональное поле:** `template_squad_id: str | None = None`.

* Если задано — секция отряда генерируется как наследование:
  ```ini
  [<id>]:<template_squad_id>
  ```
  в `squad_descr_<slug>.ltx`. Все ключи, которые компилятор пишет сам
  (`npc`, `npc_random`, `npc_in_squad`, `target_smart`, `story_id`, ...),
  перекрывают унаследованные; незаданные — остаются от шаблона.
* `template_squad_id` — это `id` строки таблицы `squads`
  (`data/anomaly_db.sqlite`); её `source_file` даёт точный файл
  `configs/misc/squad_descr/<source_file>` (без сканирования `_unpacked/`).
* Состав `npc` может ссылаться как на ванильные spawn-секции, так и на
  `CustomNpc.id` — обе формы валидны и проверяются `CAT-CUSTOM-004`.

Инварианты (уже реализованы): `id` непустой; задан хотя бы один из
`npc`/`npc_random`; `npc_in_squad` — 0/1/2 значения, неотрицательные,
`min <= max`; ключ карты `ModProject.squads` совпадает с `id`; `story_id`
уникален между главами (`models.py:1225-1231, 1293-1310`).
С `template_squad_id` требование «задан хотя бы один из `npc`/`npc_random`»
ослабляется: состав может целиком наследоваться от шаблона.

### 3.2. `CustomNpc` — предлагаемый контракт (новый класс)

```python
class CustomNpc(BaseModel):
    model_config = _MODEL_CONFIG

    id: RequiredId                      # имя секции spawn
    character_profile: OptionalId       # по умолчанию = id
    template_npc_id: str | None = None  # донор тегов из ванильного XML
    name_ru: str = ""
    name_en: str = ""

    faction: str                        # -> community
    spec_rank: Literal["novice", "regular", "veteran", "master"] = "regular"
    parent_section: str = "stalker"     # :stalker | :stalker_strong | ...

    npc_class: str | None = Field(default=None, alias="class")
    visual: str | None = None           # обязателен, если нет template_npc_id
    icon: str | None = None
    bio: str | None = None
    terrain_sect: str = "stalker_terrain"
    snd_config: str | None = None
    crouch_type: int | None = None

    rank: int = Field(default=0, ge=0)
    reputation: int = 0
    money_min: int = Field(default=0, ge=0)
    money_max: int = Field(default=0, ge=0)
    money_infinitive: bool = False
    supplies: list[str] = []            # секции предметов

    story_id: OptionalId = None
    immortal: bool = False
    immunities_sect: str | None = None

    spawn_smart: str | None = None      # алиас смарта
    start_dialog: str | None = None
    actor_dialogs: list[str] = []

    @model_validator(mode="after")
    def _defaults(self) -> Self:
        # character_profile = id, если не задан
        # npc_class = id, если не задан
        # money_max >= money_min
```

Замечания:

* `class` — зарезервированное слово Python, поэтому поле называется
  `npc_class` с `alias="class"`; `populate_by_name=True` уже включён
  (`models.py:48-53`).
* `id` кастомного NPC рекомендуется делать с префиксом slug мода:
  `<mod_slug>_<name>`.
* `character_profile` по умолчанию равен `id` — соответствует ванильной
  практике (`spawn_sections_escape.ltx:1-20`).

#### Режим простого наследования `template_npc_id`

Если `template_npc_id` задан, `visual` перестаёт быть обязательным. Компилятор:

1. Делает **один** запрос к `data/anomaly_db.sqlite`:
   `SELECT source_file FROM npcs WHERE id = :template_npc_id`. Сканирование
   `_unpacked/` и любые `glob/grep` по нему **запрещены** — путь берётся
   только из БД.
2. Открывает ровно один файл
   `vanilla_root/configs/gameplay/<source_file>` (например,
   `character_desc_escape.xml`) и находит
   `<specific_character id="<template_npc_id>">`.
3. Копирует из шаблона ровно эти теги:
   `<visual>`, `<icon>`, `<bio>`, `<rank>`, `<reputation>`, `<money>`,
   `<supplies>`.
4. Подставляет скопированное в генерируемый `<specific_character>` и
   **переопределяет**: `id`, `<name>` (из `name_ru`/`name_en`), `story_id`,
   `<actor_dialog>` (из `actor_dialogs`), а также опционально
   `<community>`/`community` spawn-секции (из `faction`) и
   `immunities_sect` (из `immortal`).
5. Всё остальное (`class`, `map_icon`, `terrain_sect`, `start_dialog`,
   `no_random`) берёт из полей `CustomNpc`/дефолтов, а **не** из шаблона.

Важные ограничения режима:

* Шаблон — только **источник тегов**. `character_profile`/`<character id>`
  по-прежнему строятся от `CustomNpc.id`, чтобы не перезаписать ванильный
  профиль и не создать дубль в `npc_profile*.xml`.
* Если `name_ru`/`name_en` пусты, `<name>` берётся из шаблона (fallback);
  `visual` — из шаблона всегда, если не задан явно.
* Отсутствие `template_npc_id` в БД, отсутствие файла или
  `<specific_character>` с таким `id` — ошибка `CAT-CUSTOM-011`, а не
  молчаливый пропуск.
* Значения из шаблона считаются «ванильными» и проходят те же проверки
  кодировки/экранирования при записи в `character_desc_<slug>.xml`.

### 3.3. Изменения `ModProject`

* Добавить `npcs: dict[str, CustomNpc]` рядом с `squads`
  (`models.py:1173-1188`).
* В `_validate_cross_references`:
  * ключ `npcs` == `CustomNpc.id`;
  * `CustomSquad.npc`/`npc_random` могут ссылаться на `CustomNpc.id` (сначала
    искать в `self.npcs`, затем в ванильной БД);
  * `CustomSquad.target_smart` и `CustomNpc.spawn_smart` должны быть валидными
    алиасами смартов;
  * `story_id` уникален среди NPC и отрядов.
* В `merge` добавить слияние `npcs` и проверку коллизий `story_id` для NPC
  (по образцу отрядов, `models.py:1293-1310`).
* `Quest.giver_npc_id` может ссылаться на `CustomNpc.story_id`/`id`.
* `CustomNpc.template_npc_id` (если задан) обязан существовать в `npcs` БД;
  `visual` при этом опционален, без шаблона — обязателен
  (`CAT-CUSTOM-009/011`).
* `CustomSquad.template_squad_id` (если задан) обязан существовать в
  `squads` БД (`CAT-CUSTOM-012`); при нём пустой `npc`/`npc_random`
  допускается (состав наследуется).

### 3.4. Правила валидации `CAT-CUSTOM-*`

Коды проектные (не движковые). Предлагаемая семантика:

| Код | Уровень | Правило |
|---|---|---|
| `CAT-CUSTOM-001` | ERROR | `id` соответствует `^[a-z][a-z0-9_]{2,63}$`, начинается с `<mod_slug>_`, не совпадает с ванильным алиасом из `get_all_valid_aliases()`. |
| `CAT-CUSTOM-002` | ERROR | Тройная связка замкнута: каждый `character_profile` имеет запись `<character>` в `npc_profile_<slug>.xml` **и** ровно один `<specific_character>`; «сирот» нет ни в одну сторону. |
| `CAT-CUSTOM-003` | ERROR | `community` ∈ известных фракций; `spec_rank` ∈ `{novice, regular, veteran, master}`. |
| `CAT-CUSTOM-004` | ERROR | `CustomSquad.npc`/`npc_random` ссылаются на существующие NPC-секции (кастомные или ванильные); пустой состав запрещён, если не задан `template_squad_id`. |
| `CAT-CUSTOM-005` | ERROR | `story_id` (NPC и отряды) уникален в проекте и не пересекается с ванильными story-id. |
| `CAT-CUSTOM-006` | ERROR | `immortal=True` требует `immunities_sect` (явный или сгенерированный `[<slug>_immunities_immortal]`, все 9 + `wound_2_immunity` = `0.0`); для квестодателя также обязателен `story_id`. |
| `CAT-CUSTOM-007` | ERROR | `$spawn` не переиспользует `respawn\...` ванильного сюжетного NPC; путь строится только из `id`. |
| `CAT-CUSTOM-008` | ERROR | `spawn_smart` — валидный алиас смарта; если на этом смарте возможен `ClearSmart`, у действия стоит `allow_giver_smart=True` (иначе `XRAY-SPAWN-001`). |
| `CAT-CUSTOM-009` | WARN | `visual` не задан **и** `template_npc_id` не задан, либо `visual` не начинается с `actors\`; `icon`/`bio` не заданы ни явно, ни через шаблон. |
| `CAT-CUSTOM-010` | ERROR | `character_desc_<slug>.xml` не в windows-1251 и/или содержит неэкранированные `&`, `<`, `>`; `npc_profile_<slug>.xml` не в UTF-8. |
| `CAT-CUSTOM-011` | ERROR | `template_npc_id` не найден в `npcs` БД, либо `<specific_character id="...">` отсутствует в `configs/gameplay/<source_file>`; путь берётся только из БД (`source_file`), без сканирования `_unpacked/`. |
| `CAT-CUSTOM-012` | ERROR | `template_squad_id` не найден в `squads` БД (секция-родитель для `[<id>]:<template>`) либо его `source_file` не содержит эту секцию. |

---

## 4. Что генерирует компилятор

При непустых `ModProject.npcs` / `ModProject.squads`:

0. **Секции иммунитетов** (при `immortal=True` и/или явном
   `immunities_sect`): `[<slug>_immunities_immortal]` со всеми 9 полями +
   `wound_2_immunity` = `0.0` (эталон — `stalker_immunities_sakharov`,
   `m_stalker.ltx:562-572`). Размещается **первой** в
   `spawn_sections_<slug>.ltx` либо в отдельном `immunities_<slug>.ltx`,
   подключаемом `#include` до spawn-секций (§1.5).
1. `gamedata/configs/creatures/spawn_sections_<slug>.ltx` — по секции на
   каждого `CustomNpc`:
   ```ini
   [<id>]:<parent_section>
   $spawn                     = "respawn\<id>"
   character_profile          = <character_profile or id>
   spec_rank                  = <spec_rank>
   community                  = <faction>
   story_id                   = <story_id>              ; если задан
   immunities_sect            = <immunities_sect or      ; если задан
                                 <slug>_immunities_immortal>
   ```
2. `gamedata/configs/gameplay/npc_profile_<slug>.xml` (**UTF-8**) — по записи
   на каждого NPC:
   ```xml
   <character id="<character_profile>">
       <class><npc_class or id></class>
       <specific_character><character_profile></specific_character>
   </character>
   ```
3. `gamedata/configs/gameplay/character_desc_<slug>.xml` (**windows-1251**) —
   `<specific_character id="<character_profile>">` на каждого NPC:
   `name/icon/bio/class/community/map_icon/terrain_sect/visual/rank/
   reputation/money/supplies/start_dialog/actor_dialog`;
   `no_random="1"` для `immortal`/квестодателей.
   При `template_npc_id` теги `visual/icon/bio/rank/reputation/money/supplies`
   копируются из ванильного `<specific_character>` шаблона (файл найден через
   `npcs.source_file`), а `id/name/actor_dialog` (+ опционально
   `community`) переопределяются (§3.2).
4. `gamedata/configs/misc/squad_descr/squad_descr_<slug>.ltx` — уже
   предусмотрено текущей моделью `CustomSquad` (`models.py:1042-1049`).
   При `template_squad_id` секция пишется как
   `[<id>]:<template_squad_id>`, состав `npc`/`npc_random` перекрывает
   унаследованный и может ссылаться на ванильные spawn-секции или
   `CustomNpc.id`.
5. **Патчи (идемпотентные):**
   * `gamedata/configs/creatures/spawn_sections.ltx` — добавить
     `#include "spawn_sections_<slug>.ltx"`;
   * `gamedata/configs/system.ltx` — дописать `npc_profile_<slug>` в
     `[profiles] files` и `character_desc_<slug>` в
     `[profiles] specific_characters_files`.

Шаблоны читаются **только по пути из БД** (`npcs.source_file` /
`squads.source_file`); компилятор не сканирует `_unpacked/`.

Кодировки: `character_desc_*.xml` — **windows-1251**; `npc_profile_*.xml` —
**UTF-8** (подтверждено разными declaration в ванильных файлах); LTX — обычный
текст.

---

## 5. Иммунитеты и бессмертие — закрыто

Раздел подтверждён чтением `m_stalker.ltx:530-699` и `immunities.ltx:1-65`.
Открытых вопросов по «неубиваемости» больше нет.

**Поля секции иммунитетов** (полный набор, `immunities.ltx:1-43`; в
`m_stalker.ltx` добавляется `wound_2_immunity`):

```
burn_immunity, strike_immunity, shock_immunity, wound_immunity,
radiation_immunity, telepatic_immunity, chemical_burn_immunity,
explosion_immunity, fire_wound_immunity, [+ wound_2_immunity]
```

**Шкала:** `1.0` — нет сопротивления (полный урон), `0.0` — полная
неуязвимость. Аномальные секции `no/low/medium/high_resistance`
(`immunities.ltx:1-43`) — примеры градаций.

**Готовые секции в Anomaly 1.5.3:**

| Секция | Где | Значения | Бессмертие |
|---|---|---|---|
| `[strelok_resistance]` | `immunities.ltx:49-58` | 8 × `0.0`, `telepatic_immunity = 1.0` | нет (пси-урон) |
| `[stalker_immunities_sakharov]` | `m_stalker.ltx:562-572` | 9 + `wound_2` = `0.0` | **да, 100 %** |
| `[stalker_immunities_die_hard]` | `m_stalker.ltx:622-632` | 9 + `wound_2` = `0.0` | **да, 100 %** |
| `[stalker_immunities_strelok]` | `m_stalker.ltx:606-616` | 8 × `0.0`, `telepatic = 1.0` | нет |
| `[stalker_immunities_strong]` | `m_stalker.ltx:681-691` | `0.25…0.5` | нет |
| `[stalker_immunities_devushka]` | `m_stalker.ltx:665-675` | `0.25` | нет |

**Ссылка из spawn-секции:** `immunities_sect = <имя секции>`; так сделано у
`stalker_sakharov` (`:560`), `stalker_strelok` (`:576`), `stalker_die_hard`
(`:620`), `stalker_devushka` (`:636`), `stalker_strong` (`:679`). Секция
может лежать как в `m_stalker.ltx`, так и в `immunities.ltx` — оба файла
подключены через `stalkers.ltx:1-6` до spawn-секций.

**Решение для `immortal=True`:** генерировать собственную секцию
`[<slug>_immunities_immortal]` с `0.0` по всем 9 полям + `wound_2_immunity`
(копия `stalker_immunities_sakharov`) и ссылаться на неё из
`immunities_sect`. Не использовать `strelok_resistance` и
`stalker_immunities_strelok` — у них `telepatic_immunity = 1.0`.
Объявлять секцию до spawn-секций (§1.5, §4).

**Остаётся открытым (не блокирует Итерацию 1):**

* `$spawn` кастомной секции: обязателен ли реальный spawn-ресурс по пути
  `respawn\<id>` — §1.3.
* Точный API удержания NPC на `spawn_smart` и поведение `ClearSmart` —
  runtime-часть Итерации 2.
* Точный DDL `data/anomaly_db.sqlite` (репозиторий уже достаточен для
  `source_file`) — §2.

Формат XML, формат spawn-секций, отсутствие wildcard, роль `npc_profile.xml`,
схема БД и механика иммунитетов проверены и в догадках не нуждаются.

---

## 6. План реализации (2 короткие итерации)

### Итерация 1 — модели, валидаторы и генераторы конфигов

* Добавить `CustomNpc` и поле `ModProject.npcs`; расширить
  `CustomSquad` полем `template_squad_id` (и при необходимости
  `immortal_giver: bool`, `npc_sections: list[str]`).
* В `CustomNpc` добавить `template_npc_id: str | None`, сделать `visual`
  опциональным (`str | None`) с проверкой «visual или template_npc_id».
* Резолвер шаблонов: `source_file` из `npcs`/`squads` БД → ровно один файл
  `configs/gameplay/<source_file>` / `configs/misc/squad_descr/<source_file>`;
  без сканирования `_unpacked/`. Кеш разобранных XML на время сборки.
* Реализовать `CAT-CUSTOM-001..012` в `model_validator`/отдельном валидаторе;
  переиспользовать `GameDatabase.get_all_valid_aliases()` для проверки
  коллизий; `CAT-CUSTOM-006` проверяет полный набор `0.0`.
* Написать эмиттеры:
  * `immunities_<slug>.ltx` (или секция в начале `spawn_sections_<slug>.ltx`)
    — `[<slug>_immunities_immortal]`, 9 полей + `wound_2_immunity` = `0.0`;
  * `spawn_sections_<slug>.ltx` (иммунитеты объявлены раньше NPC-секций);
  * `npc_profile_<slug>.xml` (UTF-8);
  * `character_desc_<slug>.xml` (windows-1251, экранирование, подстановка
    тегов из `template_npc_id`);
  * `squad_descr_<slug>.ltx` (уже есть — добавить форму
    `[<id>]:<template_squad_id>` и проверку, что состав ссылается на новые
    NPC-секции).
* Патчеры `spawn_sections.ltx` и `system.ltx` (два реестра в одном патче) —
  идемпотентные, с маркер-комментариями и dry-run режимом.
* Юнит-тесты: сериализация/десериализация, кодировки XML, повторный патч не
  дублирует строки, «сиротские» профили ловятся `CAT-CUSTOM-002`,
  наследование от `template_npc_id` копирует ровно 7 разрешённых тегов,
  `template_squad_id` даёт `[id]:<parent>`, отсутствие шаблона в БД/файле
  даёт `CAT-CUSTOM-011/012`.

### Итерация 2 — бессмертный квестодатель на смарте

* Сгенерировать подтверждённую секцию бессмертия
  `[<slug>_immunities_immortal]` (все 9 полей + `wound_2_immunity` = `0.0`,
  эталон `stalker_immunities_sakharov`) и spawn-секцию с `story_id` и
  `immunities_sect`.
* Lua-спавнер: создать NPC на `spawn_smart` (одиночный NPC или
  односекционный `CustomSquad` с `target_smart`), удерживать позицию и
  исключить его из `ClearSmart` (флаг `allow_giver_smart`).
* Интеграционный тест на демо-проекте: собрать мод, проверить наличие
  инклюда, обеих записей в `[profiles]`, валидность XML/кодировок, порядок
  объявления секции иммунитетов и отсутствие `XRAY-SPAWN-001` в линтере.
* Документ финализирован: пометок `[ТРЕБУЕТ ПРОВЕРКИ]` по §1.5/§5 нет,
  механика бессмертия подтверждена.
