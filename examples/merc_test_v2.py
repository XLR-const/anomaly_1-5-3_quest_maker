"""Сюжетная цепочка «Братья по оружию» (Душман, Мёртвый Город).

Финальная выверенная версия (Исправлены роли реплик):
  1. Этап 0: Принести АК-105 -> награда 15 000 руб.
  2. Этап 1: Принести РПГ-7 -> инструктаж на ликвидацию Журова.
  3. Этап 2: Устранить отряд майора Журова на Кордоне (авто-закрытие по target_squad_id).
  4. Этап 3: Вернуться к Душману за АС ВАЛ «Кобра».
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
# Константы
# ---------------------------------------------------------------------------

PROJECT_NAME = "Brothers in Arms"

QUEST_ID = "mymod_bro_quest"
TAKE_DIALOG_ID = "mymod_bro_take"
TURNIN_ITEMS_DIALOG_ID = "mymod_bro_turnin_items"
TURNIN_RPG_DIALOG_ID = "mymod_bro_turnin_rpg"
TURNIN_REWARD_DIALOG_ID = "mymod_bro_turnin_reward"

NPC_ID = "cit_killers_merc_trader_stalker"
NPC_LOCATION = "deadcity"
NPC_ALIAS = "deadcity.dushman"

AK105_SECTION = "wpn_ak105"
RPG_SECTION = "wpn_rpg7"

ZHUROV_SQUAD_ID = "esc_3_16_military_trader_squad"
ZHUROV_MARKER_ALIAS = ZHUROV_SQUAD_ID

VAL_REWARD_SECTION = "wpn_val_modern_kobra"
VAL_REWARD_NAME_RU = "АС ВАЛ «Кобра»"
VAL_REWARD_NAME_EN = "AS VAL 'Kobra'"

# Поршни каскада
INFO_STARTED = "mymod_bro_started"
INFO_ITEMS_DONE = "mymod_bro_items_done"
INFO_RPG_DONE = "mymod_bro_rpg_done"
INFO_ZHUROV_DEAD = "mymod_bro_zhurov_dead"
INFO_DONE = "mymod_bro_done"

REWARD_MONEY_STAGE1 = 15000


def create_bro_project() -> ModProject:
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        giver_npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[
            TAKE_DIALOG_ID,
            TURNIN_ITEMS_DIALOG_ID,
            TURNIN_RPG_DIALOG_ID,
            TURNIN_REWARD_DIALOG_ID,
        ],
        title_ru="Братья по оружию",
        title_en="Brothers in Arms",
        descr_ru=(
            "Душман просит достать снаряжение, РПГ, а затем убрать "
            "майора Журова на Кордоне."
        ),
        descr_en=(
            "Dushman asks for gear, an RPG, and the elimination of "
            "Major Zhurov in Cordon."
        ),
        is_storyline=True,
        icon="ui_inGame2_Put_v_pripyat",
        prior=60,
        stages={
            0: Stage(
                id=0,
                title_ru="Принести АК-105",
                title_en="Bring the AK-105",
                descr_ru="Душману нужен автомат АК-105. Принесите его в Мёртвый Город.",
                descr_en="Dushman needs an AK-105 rifle. Bring it to Dead City.",
                target_alias=NPC_ALIAS,
            ),
            1: Stage(
                id=1,
                title_ru="РПГ для Душмана",
                title_en="RPG for Dushman",
                descr_ru="Душману нужен РПГ-7. Добудьте его и принесите в Мёртвый Город.",
                descr_en="Dushman needs an RPG-7. Obtain it and bring it to Dead City.",
                target_alias=NPC_ALIAS,
            ),
            2: Stage(
                id=2,
                title_ru="Ликвидировать майора Журова",
                title_en="Eliminate Major Zhurov",
                descr_ru="Майор Журов находится на Кордоне. Устраните его — и возвращайтесь к Душману.",
                descr_en="Major Zhurov is in Cordon. Eliminate him and return to Dushman.",
                target_alias=ZHUROV_MARKER_ALIAS,
                target_squad_id=ZHUROV_SQUAD_ID,
            ),
            3: Stage(
                id=3,
                title_ru="Вернуться к Душману",
                title_en="Return to Dushman",
                descr_ru="Журов мёртв. Вернитесь к Душману в Мёртвый Город за наградой.",
                descr_en="Zhurov is dead. Return to Dushman in Dead City for the reward.",
                target_alias=NPC_ALIAS,
                on_start_actions=[
                    GiveInfo(info=INFO_ZHUROV_DEAD),
                ],
            ),
        },
        transfer_conditions={
            0: {"complete": [HasInfo(info=INFO_ITEMS_DONE)]},
            1: {"complete": [HasInfo(info=INFO_RPG_DONE)]},
        },
        reward_money=None,
        reward_item_alias=None,
        reward_item_count=1,
        complete_info=INFO_DONE,
        taken_info=INFO_STARTED,
    )

    # --- ДИАЛОГ 1. Старт квеста ---
    # ID 0 - Душман, ID 1, 2 - ответы игрока
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
                text_ru="Слышал, ты ищешь работу, бродяга? Есть дело. Для начала достань мне АК-105. Справишься?",
                text_en="I heard you're looking for work, stalker. I have a job. First, get me an AK-105. Can you do that?",
                next_phrases=[1, 2],
            ),
            1: Phrase(
                id=1,
                text_ru="Достану. Говори, где искать.",
                text_en="I'll get it. Where do I look?",
                actions=[
                    GiveInfo(info=INFO_STARTED),
                    GiveTask(task_id=QUEST_ID),
                ],
            ),
            2: Phrase(
                id=2,
                text_ru="Не сейчас. Слишком много возни.",
                text_en="Not now. Too much hassle.",
            ),
        },
    )

    # --- ДИАЛОГ 2. Сдача АК-105 (этап 0 -> 1) ---
    # ID 0 - Душман спрашивает. ID 1 - игрок дает пушку. ID 2 - игрок отказывается.
    turnin_items_dialog = Dialog(
        id=TURNIN_ITEMS_DIALOG_ID,
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
                text_ru="Ну что, принёс АК-105? Показывай, что там у тебя в рюкзаке.",
                text_en="So, did you bring the AK-105? Show me what's in that backpack of yours.",
                next_phrases=[1, 2],
            ),
            1: Phrase(
                id=1,
                text_ru="Держи. Всё как договаривались.",
                text_en="Here. Everything as agreed.",
                preconditions=[
                    HasItem(item_alias=AK105_SECTION, count=1),
                ],
                actions=[
                    TakeItem(item_alias=AK105_SECTION, count=1),
                    GiveMoney(amount=REWARD_MONEY_STAGE1),
                    GiveInfo(info=INFO_ITEMS_DONE),
                ],
            ),
            2: Phrase(
                id=2,
                text_ru="Ещё не достал. Подожди.",
                text_en="Haven't got it yet. Wait.",
            ),
        },
    )

    # --- ДИАЛОГ 3. Сдача РПГ (этап 1 -> 2) ---
    # ID 0 - Душман. ID 1 - игрок дает РПГ. ID 2 - отказ. ID 3 - инструктаж.
    turnin_rpg_dialog = Dialog(
        id=TURNIN_RPG_DIALOG_ID,
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
                text_ru="А это что у тебя? РПГ-7? Вот это уже серьёзный разговор. Давай сюда.",
                text_en="And what's that you've got? An RPG-7? Now we're talking serious. Hand it over.",
                next_phrases=[1, 2],
            ),
            1: Phrase(
                id=1,
                text_ru="Держи. Тяжёлая штука, но я донёс.",
                text_en="Here. Heavy thing, but I carried it.",
                preconditions=[
                    HasItem(item_alias=RPG_SECTION, count=1),
                ],
                actions=[
                    TakeItem(item_alias=RPG_SECTION, count=1),
                ],
                # Игрок отдает РПГ, и Душман сразу говорит текст (ID=3)
                next_phrases=[3],
            ),
            2: Phrase(
                id=2,
                text_ru="Пока не достал. Работаю над этим.",
                text_en="Haven't got it yet. Working on it.",
            ),
            3: Phrase(
                id=3,
                text_ru=(
                    "Отлично. Теперь главная цель: на Южном блокпосту Кордона "
                    "сидит майор Журов. Убери его — и возвращайся за уникальным ВАЛом."
                ),
                text_en=(
                    "Great. Now the main target: Major Zhurov is at the Cordon "
                    "Southern Checkpoint. Take him out and come back for your custom VAL."
                ),
                actions=[
                    GiveInfo(info=INFO_RPG_DONE),
                ],
            ),
        },
    )

    # --- ДИАЛОГ 4. Финальная награда (этап 3 -> done) ---
    # ID 0 - Душман. ID 1 - игрок забирает награду.
    turnin_reward_dialog = Dialog(
        id=TURNIN_REWARD_DIALOG_ID,
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
                text_ru=(
                    f"Журов мёртв? Хорошо. Ты сделал всё, что нужно, бродяга. "
                    f"Вот твоя награда — {VAL_REWARD_NAME_RU}. Работай с ним аккуратно."
                ),
                text_en=(
                    f"Zhurov is dead? Good. You did everything needed, stalker. "
                    f"Here's your reward — {VAL_REWARD_NAME_EN}. Handle it carefully."
                ),
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Благодарю. Если будет ещё работа — заходи.",
                text_en="Thanks. If there's more work — drop by.",
                actions=[
                    GiveItem(item_alias=VAL_REWARD_SECTION, count=1),
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
            turnin_items_dialog.id: turnin_items_dialog,
            turnin_rpg_dialog.id: turnin_rpg_dialog,
            turnin_reward_dialog.id: turnin_reward_dialog,
        },
    )


def main() -> None:
    project = create_bro_project()
    builder = ModBuilder(
        output_dir=Path("output"),
        vanilla_root=Path("_unpacked"),
    )
    if not builder.build_project(project):
        raise SystemExit("Сборка не удалась: смотрите logs/app.log.")
    print(f"Мод собран в: {builder.output_dir}")


if __name__ == "__main__":
    main()