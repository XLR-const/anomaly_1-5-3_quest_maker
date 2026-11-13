"""Golden Shield Test — сюжетный мод для S.T.A.L.K.E.R. Anomaly 1.5.3.

Сценарий написан исключительно по публичному контракту ``docs/API_v2.md``.
Никакие внутренние модули ядра, кроме ``src.compiler.builder`` и
``src.core.models``, не используются.

Сюжет:
    Майор Журов на Южном блокпосту Кордона выдаёт два связанных квеста:
    1. ``mymod_av_quest`` — захват Деревни новичков и Элеватора.
    2. ``mymod_atp_quest`` — зачистка АТП (два варианта старта: штурм
       с подкреплением или одиночная диверсия).

Ограничение доступа (фракция ``army`` + режим Warfare):
    В публичном union условий ядра нет проверки фракции актора. Единственный
    документированный механизм — ``Quest.available_info``: ядро сохраняет
    значение в таблице ``QUESTS``, а внешний фракционный/Warfare-скрипт
    выдаёт этот поршень бойцу группировки ``army`` и проверяет ``IsWarfare()``.
    Оба квеста помечены поршнем ``mymod_army_warfare_access``.
    Дополнительно оба квеста используют ``WarfareCapture``, поэтому ядро
    помечает их ``world = true``, и их ``_status`` работает только в Warfare.

Запуск из корня проекта:
    python examples/build_golden_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Запуск вида ``python examples/build_golden_test.py`` кладёт в sys.path
# каталог examples, а не корень проекта. Добавляем корень явно, чтобы
# документированные импорты ``src.*`` работали из любой точки.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.compiler.builder import ModBuilder
from src.core.models import (
    CompleteTask,
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveItem,
    GiveMoney,
    GiveTask,
    HasInfo,
    HasItem,
    ModProject,
    Phrase,
    Quest,
    SpawnSquad,
    Stage,
    TakeItem,
    WarfareCapture,
)

# ---------------------------------------------------------------------------
# Константы сценария
# ---------------------------------------------------------------------------

PROJECT_NAME = "Golden Shield Test"
PROJECT_SLUG = "golden_shield_test"

# Квестодатель: майор Журов, Южный блокпост Кордона.
NPC_ID = "esc_3_16_military_trader"
NPC_LOCATION = "escape"
NPC_ALIAS = "escape.zhurov"

# Внешний поршень доступа: армия + Warfare (см. docstring модуля).
ARMY_WARFARE_INFO = "mymod_army_warfare_access"

# Смарты и отряды Warfare.
ROOKIE_VILLAGE = "esc_smart_terrain_2_12"
ROOKIE_VILLAGE_ENEMY = "der_stalker_esc_smart_terrain_2_12"
ELEVATOR = "esc_smart_terrain_5_7"
ELEVATOR_ENEMY = "bandit_sim_squad_advanced"
ATP = "esc_smart_terrain_7_11"
ATP_ENEMY = "bandit_sim_squad_advanced"
ARMY_SQUAD = "army_sim_squad_advanced"

# --- Квест 1 ---------------------------------------------------------------
Q1_ID = "mymod_av_quest"
Q1_TAKE_DIALOG = "mymod_av_quest_take"
Q1_TURNIN_DIALOG = "mymod_av_quest_turnin"
Q1_STARTED = "mymod_av_quest_started"
Q1_READY = "mymod_av_quest_ready"
Q1_DONE = "mymod_quest_1_done"
Q1_REWARD_MONEY = 10000
Q1_REWARD_WEAPON = "wpn_vssk"

# --- Квест 2 ---------------------------------------------------------------
Q2_ID = "mymod_atp_quest"
Q2_ASSAULT_DIALOG = "mymod_atp_quest_take_assault"
Q2_SOLO_DIALOG = "mymod_atp_quest_take_solo"
Q2_TURNIN_DIALOG = "mymod_atp_quest_turnin"
Q2_STARTED = "mymod_atp_quest_started"
Q2_READY = "mymod_atp_quest_ready"
Q2_DONE = "mymod_atp_quest_done"
Q2_ASSAULT_INFO = "mymod_q2_assault"
Q2_SOLO_INFO = "mymod_q2_solo"
Q2_ASSAULT_REWARD = 15000
Q2_SOLO_REWARD = 30000
QUEST_ITEM_PDA = "itm_pda_common"


# ---------------------------------------------------------------------------
# Квест 1: «Операция "Южный щит": Зачистка периметра»
# ---------------------------------------------------------------------------


def create_first_quest() -> Quest:
    """Собирает квест о зачистке Деревни новичков и Элеватора."""
    return Quest(
        id=Q1_ID,
        npc_id=NPC_ID,
        giver_npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=Q1_TAKE_DIALOG,
        dialog_ids=[Q1_TAKE_DIALOG, Q1_TURNIN_DIALOG],
        title_ru='Операция "Южный щит": Зачистка периметра',
        title_en='Operation "Southern Shield": Perimeter Sweep',
        descr_ru=(
            "Майор Журов приказал зачистить южный периметр Кордона: "
            "сначала Деревню новичков, затем Элеватор. Действуйте вместе "
            "с штурмовыми группами военных."
        ),
        descr_en=(
            "Major Zhurov ordered the southern perimeter of the Cordon "
            "cleared: first the Rookie Village, then the Elevator. Operate "
            "together with army assault groups."
        ),
        is_storyline=True,
        prior=60,
        available_info=ARMY_WARFARE_INFO,
        taken_info=Q1_STARTED,
        complete_info=Q1_DONE,
        stages={
            0: Stage(
                id=0,
                title_ru="Захватить Деревню новичков",
                title_en="Capture the Rookie Village",
                descr_ru=(
                    "Возглавьте две штурмовые группы и выбейте одиночек "
                    "из Деревни новичков."
                ),
                descr_en=(
                    "Lead two assault groups and drive the loners out of "
                    "the Rookie Village."
                ),
                target_alias=ROOKIE_VILLAGE,
                warfare_capture=WarfareCapture(
                    smart_alias=ROOKIE_VILLAGE,
                    enemy_squad_alias=ROOKIE_VILLAGE_ENEMY,
                    ally_squad_alias=ARMY_SQUAD,
                    ally_count=2,
                ),
            ),
            1: Stage(
                id=1,
                title_ru="Захватить Элеватор",
                title_en="Capture the Elevator",
                descr_ru=(
                    "Перебросьте штурмовые группы к Элеватору и зачистите "
                    "его от бандитов."
                ),
                descr_en=(
                    "Move the assault groups to the Elevator and clear it "
                    "of bandits."
                ),
                target_alias=ELEVATOR,
                warfare_capture=WarfareCapture(
                    smart_alias=ELEVATOR,
                    enemy_squad_alias=ELEVATOR_ENEMY,
                    ally_squad_alias=ARMY_SQUAD,
                    ally_count=2,
                ),
            ),
            2: Stage(
                id=2,
                title_ru="Вернуться к майору Журову",
                title_en="Return to Major Zhurov",
                descr_ru=(
                    "Доложите майору Журову на Южном блокпосту о захвате "
                    "Деревни новичков и Элеватора."
                ),
                descr_en=(
                    "Report the capture of the Rookie Village and the "
                    "Elevator to Major Zhurov at the southern checkpoint."
                ),
                target_alias="",
                on_start_actions=[GiveInfo(info=Q1_READY)],
            ),
        },
    )


def create_first_quest_dialogs() -> list[Dialog]:
    """Диалоги взятия и сдачи первого квеста (чётные — Игрок, нечётные — Журов)."""
    take_dialog = Dialog(
        id=Q1_TAKE_DIALOG,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=Q1_ID,
        role="take",
        preconditions=[DontHasInfo(info=Q1_STARTED)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Товарищ майор, есть работа для бойца?",
                text_en="Comrade Major, got any work for a soldier?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru=(
                    "Есть, боец. Деревня новичков и Элеватор до сих пор "
                    "под контролем врага. Нужно выбить их оттуда."
                ),
                text_en=(
                    "There is, soldier. The Rookie Village and the Elevator "
                    "are still held by the enemy. We need to push them out."
                ),
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Понял. Штурмовые группы выделишь?",
                text_en="Understood. Will you assign assault groups?",
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru=(
                    "Возьмёшь две штурмовые группы и выдвигайся. Сначала "
                    "Деревня новичков, затем Элеватор. Выполняй."
                ),
                text_en=(
                    "You will take two assault groups and move out. The "
                    "Rookie Village first, then the Elevator. Get to it."
                ),
                actions=[GiveTask(task_id=Q1_ID)],
            ),
            4: Phrase(
                id=4,
                text_ru="Не сейчас, товарищ майор. Сначала подготовлюсь.",
                text_en="Not now, Comrade Major. I need to prepare first.",
            ),
        },
    )

    turnin_dialog = Dialog(
        id=Q1_TURNIN_DIALOG,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=Q1_ID,
        role="turnin",
        # Info-условия безопасны на уровне диалога: _can_take не создаётся.
        preconditions=[
            HasInfo(info=Q1_READY),
            DontHasInfo(info=Q1_DONE),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru=(
                    "Товарищ майор, Деревня новичков и Элеватор взяты "
                    "под контроль."
                ),
                text_en=(
                    "Comrade Major, the Rookie Village and the Elevator "
                    "are under our control."
                ),
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru=(
                    "Отлично, боец. Южный периметр закрыт. Держи награду: "
                    "десять тысяч рублей и ВССК. Свободен."
                ),
                text_en=(
                    "Excellent, soldier. The southern perimeter is sealed. "
                    "Here is your reward: ten thousand rubles and a VSSK. "
                    "Dismissed."
                ),
                actions=[
                    GiveMoney(amount=Q1_REWARD_MONEY),
                    GiveItem(item_alias=Q1_REWARD_WEAPON, count=1),
                    CompleteTask(task_id=Q1_ID),
                ],
            ),
        },
    )

    return [take_dialog, turnin_dialog]


# ---------------------------------------------------------------------------
# Квест 2: «Зачистка АТП»
# ---------------------------------------------------------------------------


def create_second_quest() -> Quest:
    """Собирает квест о зачистке АТП с двумя вариантами старта."""
    return Quest(
        id=Q2_ID,
        npc_id=NPC_ID,
        giver_npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=Q2_ASSAULT_DIALOG,
        dialog_ids=[
            Q2_ASSAULT_DIALOG,
            Q2_SOLO_DIALOG,
            Q2_TURNIN_DIALOG,
        ],
        title_ru="Зачистка АТП",
        title_en="Clearing the ATP",
        descr_ru=(
            "Бандиты закрепились на АТП. Майор Журов предлагает на выбор "
            "штурм с двумя группами или одиночную диверсию за двойную плату."
        ),
        descr_en=(
            "Bandits have dug in at the ATP. Major Zhurov offers a choice: "
            "an assault with two squads or a solo sabotage for double pay."
        ),
        is_storyline=True,
        prior=61,
        available_info=ARMY_WARFARE_INFO,
        taken_info=Q2_STARTED,
        complete_info=Q2_DONE,
        stages={
            0: Stage(
                id=0,
                title_ru="Захватить АТП",
                title_en="Capture the ATP",
                descr_ru=(
                    "Зачистите АТП от бандитов и заберите трофейные данные "
                    "с их ПДА."
                ),
                descr_en=(
                    "Clear the ATP of bandits and recover the trophy data "
                    "from their PDA."
                ),
                target_alias=ATP,
                # Вражеский отряд спавнится автоматически на старте этапа.
                # Союзники варианта А появляются из реплики диалога, чтобы
                # вариант Б оставался действительно одиночным.
                warfare_capture=WarfareCapture(
                    smart_alias=ATP,
                    enemy_squad_alias=ATP_ENEMY,
                ),
            ),
            1: Stage(
                id=1,
                title_ru="Вернуться к майору Журову",
                title_en="Return to Major Zhurov",
                descr_ru=(
                    "Отнесите трофейный ПДА майору Журову на Южный блокпост."
                ),
                descr_en=(
                    "Bring the trophy PDA to Major Zhurov at the southern "
                    "checkpoint."
                ),
                target_alias="",
                # Этап начинается ровно в момент зачистки АТП: здесь игрок
                # автоматически получает квестовый предмет и поршень готовности.
                on_start_actions=[
                    GiveItem(item_alias=QUEST_ITEM_PDA, count=1),
                    GiveInfo(info=Q2_READY),
                ],
            ),
        },
    )


def create_second_quest_dialogs() -> list[Dialog]:
    """Диалоги двух вариантов старта и общий диалог сдачи второго квеста."""
    assault_dialog = Dialog(
        id=Q2_ASSAULT_DIALOG,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=Q2_ID,
        role="take_assault",
        preconditions=[
            HasInfo(info=Q1_DONE),
            DontHasInfo(info=Q2_STARTED),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Товарищ майор, что с АТП?",
                text_en="Comrade Major, what about the ATP?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru=(
                    "Бандиты окопались на АТП. Нужен штурм. Пойдёшь "
                    "с двумя штурмовыми группами?"
                ),
                text_en=(
                    "Bandits have dug in at the ATP. We need an assault. "
                    "Will you go with two assault groups?"
                ),
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Иду с штурмовыми группами. Выдвигаемся.",
                text_en="I'll go with the assault groups. Moving out.",
                actions=[
                    SpawnSquad(squad_alias=ARMY_SQUAD, smart_alias=ATP),
                    SpawnSquad(squad_alias=ARMY_SQUAD, smart_alias=ATP),
                    GiveInfo(info=Q2_ASSAULT_INFO),
                    GiveTask(task_id=Q2_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru=(
                    "Группы уже ждут у АТП. Зачистите точку и принеси "
                    "трофейные данные. Не подведи."
                ),
                text_en=(
                    "The groups are already waiting at the ATP. Clear the "
                    "site and bring back the trophy data. Don't fail me."
                ),
            ),
            4: Phrase(
                id=4,
                text_ru="Не сейчас. Слишком горячо там.",
                text_en="Not now. It's too hot out there.",
            ),
        },
    )

    solo_dialog = Dialog(
        id=Q2_SOLO_DIALOG,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=Q2_ID,
        role="take_solo",
        preconditions=[
            HasInfo(info=Q1_DONE),
            DontHasInfo(info=Q2_STARTED),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="А если я пойду на АТП один?",
                text_en="What if I go to the ATP alone?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru=(
                    "Один? Это самоубийство. Но если справишься — заплачу "
                    "двойную цену. Тридцать тысяч."
                ),
                text_en=(
                    "Alone? That's suicide. But if you pull it off, I'll pay "
                    "double. Thirty thousand."
                ),
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Иду один. Готовь деньги.",
                text_en="I'll go alone. Get the money ready.",
                actions=[
                    GiveInfo(info=Q2_SOLO_INFO),
                    GiveTask(task_id=Q2_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru=(
                    "Не подведи. И не вздумай погибнуть — данные должны "
                    "попасть ко мне."
                ),
                text_en=(
                    "Don't fail me. And don't you dare die — the data must "
                    "reach me."
                ),
            ),
            4: Phrase(
                id=4,
                text_ru="Нет, слишком рискованно. Найду другой способ.",
                text_en="No, it's too risky. I'll find another way.",
            ),
        },
    )

    turnin_dialog = Dialog(
        id=Q2_TURNIN_DIALOG,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=Q2_ID,
        role="turnin",
        preconditions=[
            HasInfo(info=Q2_READY),
            DontHasInfo(info=Q2_DONE),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Товарищ майор, АТП зачищено.",
                text_en="Comrade Major, the ATP is cleared.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Докладывай. Данные с АТП у тебя?",
                text_en="Report. Do you have the data from the ATP?",
                next_phrases=[2, 4, 6],
            ),
            2: Phrase(
                id=2,
                text_ru=(
                    "Держите трофейный ПДА. Штурм удался, группы отработали "
                    "чисто."
                ),
                text_en=(
                    "Here is the trophy PDA. The assault worked; the groups "
                    "performed cleanly."
                ),
                preconditions=[
                    HasItem(item_alias=QUEST_ITEM_PDA, count=1),
                    HasInfo(info=Q2_ASSAULT_INFO),
                ],
                actions=[
                    TakeItem(item_alias=QUEST_ITEM_PDA, count=1),
                    GiveMoney(amount=Q2_ASSAULT_REWARD),
                    CompleteTask(task_id=Q2_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru=(
                    "Работа принята. Держи пятнадцать тысяч, как "
                    "договаривались."
                ),
                text_en=(
                    "Work accepted. Here are fifteen thousand, as agreed."
                ),
            ),
            4: Phrase(
                id=4,
                text_ru=(
                    "Держите ПДА. Справился один, как и обещал."
                ),
                text_en=(
                    "Here is the PDA. I handled it alone, as promised."
                ),
                preconditions=[
                    HasItem(item_alias=QUEST_ITEM_PDA, count=1),
                    HasInfo(info=Q2_SOLO_INFO),
                ],
                actions=[
                    TakeItem(item_alias=QUEST_ITEM_PDA, count=1),
                    GiveMoney(amount=Q2_SOLO_REWARD),
                    CompleteTask(task_id=Q2_ID),
                ],
                next_phrases=[5],
            ),
            5: Phrase(
                id=5,
                text_ru=(
                    "Один? Хорошая работа. Держи тридцать тысяч — двойная "
                    "плата, как обещал."
                ),
                text_en=(
                    "Alone? Good work. Here are thirty thousand — double "
                    "pay, as promised."
                ),
            ),
            6: Phrase(
                id=6,
                text_ru="Данных пока нет. АТП ещё не зачищено.",
                text_en="I don't have the data yet. The ATP isn't cleared.",
            ),
        },
    )

    return [assault_dialog, solo_dialog, turnin_dialog]


# ---------------------------------------------------------------------------
# Сборка проекта
# ---------------------------------------------------------------------------


def create_golden_shield_project() -> ModProject:
    """Создаёт полный проект мода «Golden Shield Test».

    Returns:
        ModProject: Валидный проект, готовый к передаче в ``ModBuilder``.

    Raises:
        pydantic.ValidationError: Если нарушены инварианты моделей.
    """
    first_quest = create_first_quest()
    second_quest = create_second_quest()
    dialogs = create_first_quest_dialogs() + create_second_quest_dialogs()

    return ModProject(
        name=PROJECT_NAME,
        required_mods=[],
        quests={
            first_quest.id: first_quest,
            second_quest.id: second_quest,
        },
        dialogs={dialog.id: dialog for dialog in dialogs},
    )


def main() -> None:
    """Собирает мод в ``output/golden_shield_test`` и проверяет результат."""
    project = create_golden_shield_project()

    builder = ModBuilder(
        output_dir=Path("output"),
        vanilla_root=Path("_unpacked"),
    )

    if not builder.build_project(project):
        raise SystemExit("Сборка не удалась: смотрите logs/app.log.")

    mod_root = builder.output_dir / PROJECT_SLUG
    if not mod_root.is_dir():
        raise SystemExit(f"Каталог сборки не найден: {mod_root}")

    print(f"Мод собран в: {mod_root}")
    print(f"Квесты: {', '.join(project.quests)}")
    print(f"Диалоги: {', '.join(project.dialogs)}")


if __name__ == "__main__":
    main()
