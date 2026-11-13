"""Квест: Помощь деревне одиночек (Warfare, S.T.A.L.K.E.R. Anomaly 1.5.3).

Сюжет:
  Волк (esc_2_12_stalker_wolf, локация escape) просит помочь деревне новичков.
  Этап 0: принести АК-105          -> награда 15 000 руб.
  Этап 1: принести РПГ-7           -> награда 25 000 руб.
  Этап 2: убить майора Журова на блокпосте -> награда 50 000 руб. (финал)

Награды за этапы 0 и 1 выдаются через Stage.on_start_actions следующего этапа
(срабатывают ровно один раз благодаря pstor). Финальная награда 50 000 руб.
выдаётся через on_complete_actions квеста.

Запуск из любого места:
    python examples/village_help_demo.py
"""

from __future__ import annotations

from pathlib import Path
import sys

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
    RemoveItem,
    Stage,
)

# ---------------------------------------------------------------------------
# Константы сценария
# ---------------------------------------------------------------------------

PROJECT_NAME = "Village Help: Wolf's Request"

QUEST_ID = "village_help"
TAKE_DIALOG_ID = "village_help_take"
STAGE0_DIALOG_ID = "village_help_turnin_ak"
STAGE1_DIALOG_ID = "village_help_turnin_rpg"
STAGE2_DIALOG_ID = "village_help_turnin_zhurov"

NPC_ID = "esc_2_12_stalker_wolf"
NPC_LOCATION = "escape"
NPC_ALIAS = "escape.wolf"

# Предметы (секции Anomaly 1.5.3 — при необходимости замените на свои).
ITEM_AK105 = "wpn_ak105"
ITEM_RPG7 = "wpn_rpg7"

# Отряд майора Журова на блокпосте (пример из документации, раздел 2.7).
# Если у вас другая секция — замените здесь.
ZHUROV_SQUAD = "esc_3_16_military_trader_squad"
ZHUROV_SMART = "esc_blockpost"

# Награды.
REWARD_AK = 15000
REWARD_RPG = 25000
REWARD_ZHUROV = 50000

# Информационные поршни (для управления доступностью диалогов).
START_INFO = "village_help_started"
AK_DONE_INFO = "village_help_ak_done"
RPG_DONE_INFO = "village_help_rpg_done"
ZHUROV_DONE_INFO = "village_help_zhurov_done"


# ---------------------------------------------------------------------------
# Построение проекта
# ---------------------------------------------------------------------------

def create_village_help_project() -> ModProject:
    """Создаёт проект «Помощь деревне одиночек»."""

    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        giver_npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[
            TAKE_DIALOG_ID,
            STAGE0_DIALOG_ID,
            STAGE1_DIALOG_ID,
            STAGE2_DIALOG_ID,
        ],
        title_ru="Помощь деревне одиночек",
        title_en="Help for the Loners' Village",
        descr_ru=(
            "Волк просит помочь деревне новичков: принести оружие и "
            "разобраться с военными на блокпосте."
        ),
        descr_en=(
            "Wolf asks for help: bring weapons to the rookie village and "
            "deal with the military at the checkpoint."
        ),
        is_storyline=True,
        icon="ui_inGame2_Put_v_pripyat",
        prior=60,
        stages={
            # --- Этап 0: принести АК-105 -----------------------------------
            0: Stage(
                id=0,
                title_ru="Принести АК-105",
                title_en="Bring an AK-105",
                descr_ru=(
                    "Волк просит достать ствол АК-105 для защиты деревни. "
                    "Подойдёт любой исправный автомат."
                ),
                descr_en=(
                    "Wolf wants an AK-105 rifle to defend the village. "
                    "Any working assault rifle will do."
                ),
                target_alias="",  # маркер на Волке — вернуться к нему
                on_start_actions=[],  # старт этапа — ничего не выдаём
            ),
            # --- Этап 1: принести РПГ-7 ------------------------------------
            1: Stage(
                id=1,
                title_ru="Принести РПГ-7",
                title_en="Bring an RPG-7",
                descr_ru=(
                    "Ствол для деревни добыт. Теперь Волк просит РПГ-7 — "
                    "на случай серьёзного штурма."
                ),
                descr_en=(
                    "The rifle is delivered. Now Wolf wants an RPG-7 in "
                    "case of a serious assault."
                ),
                target_alias="",
                # Награда за этап 0 выдаётся здесь, ровно один раз.
                on_start_actions=[
                    GiveMoney(amount=REWARD_AK),
                    GiveInfo(info=AK_DONE_INFO),
                ],
            ),
            # --- Этап 2: убить майора Журова ------------------------------
            2: Stage(
                id=2,
                title_ru="Ликвидировать майора Журова",
                title_en="Eliminate Major Zhurov",
                descr_ru=(
                    "Военные на блокпосте мешают деревне. Убейте майора "
                    "Журова и его отряд."
                ),
                descr_en=(
                    "The military at the checkpoint threaten the village. "
                    "Kill Major Zhurov and his squad."
                ),
                target_alias=ZHUROV_SMART,
                target_squad_id=ZHUROV_SQUAD,
                # Награда за этап 1 выдаётся здесь, ровно один раз.
                on_start_actions=[
                    GiveMoney(amount=REWARD_RPG),
                    GiveInfo(info=RPG_DONE_INFO),
                ],
            ),
        },
        # Переходы этапов.
        transfer_conditions={
            # Этап 0 -> 1: в инвентаре есть АК-105.
            0: {"complete": [HasItem(item_alias=ITEM_AK105, count=1)]},
            # Этап 1 -> 2: в инвентаре есть РПГ-7.
            1: {"complete": [HasItem(item_alias=ITEM_RPG7, count=1)]},
            # Этап 2 не имеет transfer_conditions: его закрывает
            # автоматическая проверка target_squad_id (см. раздел 2.7 API).
        },
        # Финальная награда за этап 2 (50 000) и поршень завершения.
        on_complete_actions=[
            GiveMoney(amount=REWARD_ZHUROV),
            GiveInfo(info=ZHUROV_DONE_INFO),
        ],
        # Дополнительно: reward_money не задаём, чтобы не дублировать награду.
    )

    # -------------------------------------------------------------------
    # Диалог выдачи
    # -------------------------------------------------------------------
    take_dialog = Dialog(
        id=TAKE_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="take",
        # Выдача доступна, пока квест не взят.
        preconditions=[DontHasInfo(info=START_INFO)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Здарова Волк. Слышал нужна помощь деревне новичков.",
                text_en="Hey Wolf. Heard the rookie village needs help.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Да. Будем рады любой помощи, достань нам ствол АК 105.",
                text_en="Yes. We'd welcome any help — bring us an AK-105 rifle.",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Понял. Достану АК-105.",
                text_en="Got it. I'll bring an AK-105.",
                actions=[
                    GiveInfo(info=START_INFO),
                    GiveTask(task_id=QUEST_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Вот и славно. Ждём тебя, сталкер.",
                text_en="Good. We'll be waiting, stalker.",
            ),
            4: Phrase(
                id=4,
                text_ru="Не сейчас, Волк. Есть дела поважнее.",
                text_en="Not now, Wolf. I have more important things to do.",
            ),
        },
    )

    # -------------------------------------------------------------------
    # Диалог сдачи этапа 0 (АК-105) -> этап 1
    # -------------------------------------------------------------------
    stage0_dialog = Dialog(
        id=STAGE0_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turnin",
        # Диалог виден, только когда квест взят и АК ещё не сдан.
        # ВАЖНО: HasItem здесь НЕ ставим — только в Phrase.preconditions!
        preconditions=[
            HasInfo(info=START_INFO),
            DontHasInfo(info=AK_DONE_INFO),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Волк, я принёс АК-105.",
                text_en="Wolf, I brought the AK-105.",
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
                text_ru="Держи, ствол у меня.",
                text_en="Here, I have the rifle.",
                # Проверка предмета — только здесь.
                preconditions=[HasItem(item_alias=ITEM_AK105, count=1)],
                actions=[
                    RemoveItem(item_alias=ITEM_AK105, count=1),
                    # Деньги и поршень выдаст Stage.on_start_actions этапа 1.
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Спасибо, сталкер. Это нам очень поможет.",
                text_en="Thanks, stalker. This will help us a lot.",
            ),
            4: Phrase(
                id=4,
                text_ru="Ещё ищу, Волк. Не всё так просто.",
                text_en="Still looking, Wolf. It's not that simple.",
            ),
        },
    )

    # -------------------------------------------------------------------
    # Диалог сдачи этапа 1 (РПГ-7) -> этап 2
    # -------------------------------------------------------------------
    stage1_dialog = Dialog(
        id=STAGE1_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turnin",
        preconditions=[
            HasInfo(info=AK_DONE_INFO),
            DontHasInfo(info=RPG_DONE_INFO),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Волк, вот РПГ-7, как просил.",
                text_en="Wolf, here's the RPG-7 you asked for.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Хорошая работа. Теперь деревня не беззащитна.",
                text_en="Good work. Now the village isn't defenceless.",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Держи РПГ. Что дальше?",
                text_en="Here's the RPG. What's next?",
                preconditions=[HasItem(item_alias=ITEM_RPG7, count=1)],
                actions=[
                    RemoveItem(item_alias=ITEM_RPG7, count=1),
                    # Деньги и поршень выдаст Stage.on_start_actions этапа 2.
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru=(
                    "Есть ещё одно дело. Майор Журов на блокпосте "
                    "со своими людьми не даёт нам жить. Убей его."
                ),
                text_en=(
                    "There's one more thing. Major Zhurov at the checkpoint "
                    "and his men won't let us live. Kill him."
                ),
            ),
            4: Phrase(
                id=4,
                text_ru="Ещё ищу, Волк.",
                text_en="Still looking, Wolf.",
            ),
        },
    )

    # -------------------------------------------------------------------
    # Диалог сдачи этапа 2 (Журов) -> завершение квеста
    # -------------------------------------------------------------------
    stage2_dialog = Dialog(
        id=STAGE2_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turnin",
        preconditions=[
            HasInfo(info=RPG_DONE_INFO),
            DontHasInfo(info=ZHUROV_DONE_INFO),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Волк, Журов мёртв.",
                text_en="Wolf, Zhurov is dead.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Ты сделал то, что нужно. Деревня тебе обязана.",
                text_en="You did what was needed. The village owes you.",
                next_phrases=[2],
            ),
            2: Phrase(
                id=2,
                text_ru="Рад был помочь.",
                text_en="Glad I could help.",
                actions=[
                    # Завершаем квест; награду 50 000 выдаст _reward.
                    CompleteTask(task_id=QUEST_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Держи, это тебе за труды. Удачи, сталкер.",
                text_en="Here, this is for your trouble. Good luck, stalker.",
            ),
        },
    )

    return ModProject(
        name=PROJECT_NAME,
        required_mods=[],
        quests={quest.id: quest},
        dialogs={
            take_dialog.id: take_dialog,
            stage0_dialog.id: stage0_dialog,
            stage1_dialog.id: stage1_dialog,
            stage2_dialog.id: stage2_dialog,
        },
    )


# ---------------------------------------------------------------------------
# Сборка
# ---------------------------------------------------------------------------

def main() -> None:
    project = create_village_help_project()

    builder = ModBuilder(
        output_dir=Path("output"),
        vanilla_root=Path("_unpacked"),
    )

    if not builder.build_project(project):
        raise SystemExit("Сборка не удалась: смотрите logs/app.log.")

    print(f"Мод собран в: {builder.output_dir}")


if __name__ == "__main__":
    main()