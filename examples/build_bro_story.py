"""Сборщик сюжетной цепочки «Братья по оружию».

Сценарий:
    1. Этап 0: принести Душману АК-105.
    2. Этап 1: принести Душману РПГ-7.
    3. Этап 2: ликвидировать майора Журова на Кордоне.
    4. Этап 3: вернуться к Душману за наградой.

Запуск из корня проекта:
    python tools/build_bro_story.py
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
    Stage,
    TakeItem,
)

# ---------------------------------------------------------------------------
# Константы сценария
# ---------------------------------------------------------------------------

PROJECT_NAME = "Brothers in Arms"

QUEST_ID = "mymod_bro_quest"

TAKE_DIALOG_ID = "mymod_bro_take"
ITEMS_DIALOG_ID = "mymod_bro_turnin_items"
RPG_DIALOG_ID = "mymod_bro_turnin_rpg"
REWARD_DIALOG_ID = "mymod_bro_turnin_reward"

NPC_ID = "cit_killers_merc_trader_stalker"
NPC_LOCATION = "deadcity"
NPC_ALIAS = "deadcity.dushman"

AK105_SECTION = "wpn_ak105"
RPG7_SECTION = "wpn_rpg7"
REWARD_ITEM_SECTION = "wpn_val_modern_kobra"

ZHUROV_SQUAD_ID = "esc_3_16_military_trader_squad"
ZHUROV_MARKER_ALIAS = ZHUROV_SQUAD_ID

REWARD_MONEY_AK105 = 15000

INFO_STARTED = "mymod_bro_started"
INFO_ITEMS_DONE = "mymod_bro_items_done"
INFO_RPG_DONE = "mymod_bro_rpg_done"
INFO_ZHUROV_DEAD = "mymod_bro_zhurov_dead"
INFO_DONE = "mymod_bro_done"


# ---------------------------------------------------------------------------
# Модель проекта
# ---------------------------------------------------------------------------


def create_bro_project() -> ModProject:
    """Создаёт и валидирует проект мода «Братья по оружию».

    Returns:
        ModProject: Готовый к сборке проект с квестом и четырьмя диалогами.

    Raises:
        pydantic.ValidationError: Если нарушены инварианты моделей.
    """
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        giver_npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[
            TAKE_DIALOG_ID,
            ITEMS_DIALOG_ID,
            RPG_DIALOG_ID,
            REWARD_DIALOG_ID,
        ],
        title_ru="Братья по оружию",
        title_en="Brothers in Arms",
        descr_ru=(
            "Душман просит достать АК-105 и РПГ-7, а затем убрать "
            "майора Журова на Кордоне."
        ),
        descr_en=(
            "Dushman asks for an AK-105 and an RPG-7, then for the "
            "elimination of Major Zhurov in Cordon."
        ),
        is_storyline=True,
        icon="ui_inGame2_Put_v_pripyat",
        prior=60,
        stages={
            0: Stage(
                id=0,
                title_ru="Принести АК-105",
                title_en="Bring the AK-105",
                descr_ru=(
                    "Душману нужен автомат АК-105. Принесите его в "
                    "Мёртвый Город."
                ),
                descr_en=(
                    "Dushman needs an AK-105 rifle. Bring it to Dead City."
                ),
                target_alias=NPC_ALIAS,
            ),
            1: Stage(
                id=1,
                title_ru="Принести РПГ-7",
                title_en="Bring the RPG-7",
                descr_ru=(
                    "Душману нужен РПГ-7. Добудьте его и принесите в "
                    "Мёртвый Город."
                ),
                descr_en=(
                    "Dushman needs an RPG-7. Obtain it and bring it to "
                    "Dead City."
                ),
                target_alias=NPC_ALIAS,
            ),
            2: Stage(
                id=2,
                title_ru="Ликвидировать майора Журова",
                title_en="Eliminate Major Zhurov",
                descr_ru=(
                    "Майор Журов находится на Кордоне. Уничтожьте его "
                    "отряд — этап закроется автоматически."
                ),
                descr_en=(
                    "Major Zhurov is in Cordon. Destroy his squad — the "
                    "stage closes automatically."
                ),
                target_alias=ZHUROV_MARKER_ALIAS,
                target_squad_id=ZHUROV_SQUAD_ID,
            ),
            3: Stage(
                id=3,
                title_ru="Вернуться к Душману",
                title_en="Return to Dushman",
                descr_ru=(
                    "Журов мёртв. Вернитесь к Душману в Мёртвый Город "
                    "за наградой."
                ),
                descr_en=(
                    "Zhurov is dead. Return to Dushman in Dead City for "
                    "the reward."
                ),
                target_alias=NPC_ALIAS,
                on_start_actions=[GiveInfo(info=INFO_ZHUROV_DEAD)],
            ),
        },
        transfer_conditions={
            0: {"complete": [HasInfo(info=INFO_ITEMS_DONE)]},
            1: {"complete": [HasInfo(info=INFO_RPG_DONE)]},
        },
        complete_info=INFO_DONE,
        taken_info=INFO_STARTED,
    )

    # ------------------------------------------------------------------
    # Диалог 1: выдача задания
    # ------------------------------------------------------------------
    take_dialog = Dialog(
        id=TAKE_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="take",
        preconditions=[DontHasInfo(info=INFO_STARTED)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Душман, я насчёт работы. Говорят, у тебя есть дело.",
                text_en="Dushman, I'm here about work. I hear you have a job.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru=(
                    "Есть дело. Для начала достань мне АК-105. Справишься?"
                ),
                text_en=(
                    "I have a job. First, get me an AK-105. Can you do that?"
                ),
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Достану. Говори, где искать.",
                text_en="I'll get it. Where do I look?",
                actions=[
                    GiveInfo(info=INFO_STARTED),
                    GiveTask(task_id=QUEST_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Не подведи. Жду тебя в Мёртвом Городе.",
                text_en="Don't let me down. I'll be waiting in Dead City.",
            ),
            4: Phrase(
                id=4,
                text_ru="Не сейчас. Слишком много возни.",
                text_en="Not now. Too much hassle.",
            ),
        },
    )

    # ------------------------------------------------------------------
    # Диалог 2: сдача АК-105
    # ------------------------------------------------------------------
    items_dialog = Dialog(
        id=ITEMS_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turnin",
        preconditions=[
            HasInfo(info=INFO_STARTED),
            DontHasInfo(info=INFO_ITEMS_DONE),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Душман, я насчёт АК-105.",
                text_en="Dushman, I'm here about the AK-105.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru=(
                    "Принёс? Показывай, что там у тебя в рюкзаке."
                ),
                text_en=(
                    "Did you bring it? Show me what's in that backpack "
                    "of yours."
                ),
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Держи. Всё как договаривались.",
                text_en="Here. Everything as agreed.",
                preconditions=[
                    HasItem(item_alias=AK105_SECTION, count=1),
                ],
                actions=[
                    TakeItem(item_alias=AK105_SECTION, count=1),
                    GiveMoney(amount=REWARD_MONEY_AK105),
                    GiveInfo(info=INFO_ITEMS_DONE),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Хорошо. Теперь нужен РПГ-7. Достань его.",
                text_en="Good. Now I need an RPG-7. Get one.",
            ),
            4: Phrase(
                id=4,
                text_ru="Ещё не достал. Подожди.",
                text_en="Haven't got it yet. Wait.",
            ),
        },
    )

    # ------------------------------------------------------------------
    # Диалог 3: сдача РПГ-7 и наводка на Журова
    # ------------------------------------------------------------------
    rpg_dialog = Dialog(
        id=RPG_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turnin",
        preconditions=[
            HasInfo(info=INFO_ITEMS_DONE),
            DontHasInfo(info=INFO_RPG_DONE),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Душман, я насчёт РПГ-7.",
                text_en="Dushman, I'm here about the RPG-7.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru=(
                    "А, РПГ-7. Давай сюда, посмотрим, что ты принёс."
                ),
                text_en=(
                    "Ah, the RPG-7. Hand it over, let's see what you've "
                    "brought."
                ),
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Держи. Тяжёлая штука, но я донёс.",
                text_en="Here. Heavy thing, but I carried it.",
                preconditions=[
                    HasItem(item_alias=RPG7_SECTION, count=1),
                ],
                actions=[
                    TakeItem(item_alias=RPG7_SECTION, count=1),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru=(
                    "Отлично. Теперь главная цель: на Южном блокпосту "
                    "Кордона сидит майор Журов. Убери его — и "
                    "возвращайся за уникальным ВАЛом."
                ),
                text_en=(
                    "Great. Now the main target: Major Zhurov is at the "
                    "Cordon Southern Checkpoint. Take him out and come "
                    "back for your custom VAL."
                ),
                actions=[GiveInfo(info=INFO_RPG_DONE)],
            ),
            4: Phrase(
                id=4,
                text_ru="Пока не достал. Работаю над этим.",
                text_en="Haven't got it yet. Working on it.",
            ),
        },
    )

    # ------------------------------------------------------------------
    # Диалог 4: финальная награда
    # ------------------------------------------------------------------
    reward_dialog = Dialog(
        id=REWARD_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turn_in",
        preconditions=[
            HasInfo(info=INFO_ZHUROV_DEAD),
            DontHasInfo(info=INFO_DONE),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Душман, дело сделано. Журов мёртв.",
                text_en="Dushman, it's done. Zhurov is dead.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru=(
                    "Журов мёртв? Хорошо. Ты сделал всё, что нужно, "
                    "бродяга. Вот твоя награда — АС ВАЛ «Кобра». "
                    "Работай с ним аккуратно."
                ),
                text_en=(
                    "Zhurov is dead? Good. You did everything needed, "
                    "stalker. Here's your reward — the AS VAL 'Kobra'. "
                    "Handle it carefully."
                ),
                next_phrases=[2],
            ),
            2: Phrase(
                id=2,
                text_ru="Благодарю. Если будет ещё работа — заходи.",
                text_en="Thanks. If there's more work — drop by.",
                actions=[
                    GiveItem(item_alias=REWARD_ITEM_SECTION, count=1),
                    CompleteTask(task_id=QUEST_ID),
                ],
            ),
        },
    )

    return ModProject(
        name=PROJECT_NAME,
        required_mods=[],
        quests={quest.id: quest},
        dialogs={
            take_dialog.id: take_dialog,
            items_dialog.id: items_dialog,
            rpg_dialog.id: rpg_dialog,
            reward_dialog.id: reward_dialog,
        },
    )


# ---------------------------------------------------------------------------
# Сборка
# ---------------------------------------------------------------------------


def main() -> None:
    """Валидирует проект и собирает мод в ``output/brothers_in_arms``."""
    project = create_bro_project()

    builder = ModBuilder(
        output_dir=Path("output"),
        vanilla_root=Path("_unpacked"),
    )

    if not builder.build_project(project):
        raise SystemExit("Сборка не удалась: смотрите logs/app.log.")

    print(f"Мод собран в: {builder.output_dir / 'brothers_in_arms'}")


if __name__ == "__main__":
    main()
