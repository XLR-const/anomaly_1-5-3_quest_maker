"""
Скрипт квеста story_05.py для S.T.A.L.K.E.R. Anomaly 1.5.3.
Демонстрирует Story-паттерн с динамическим изменением цели (target_variants) 
и описания этапа (descr_variants) в зависимости от инфопоршней и наличия предмета.

Локация: Затон (zaton).
Квестодатель: Борода (zat_a2_stalker_barmen).
Сценарий:
1. Игрок получает задание найти данные. Цель — смарт zat_b7.
2. При получении поршня 'story_05_intel_found' цель меняется на затон B52 (zat_b52).
3. Описание этапа меняется, если у игрока есть ПДА (itm_pda_common).
"""
from __future__ import annotations

from pathlib import Path
from src.compiler.builder import ModBuilder
from src.core.models import (
    CompleteTask,
    DescrVariant,
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
    TargetVariant,
)

# ---------------------------------------------------------------------------
# Константы сценария
# ---------------------------------------------------------------------------
MOD_SLUG = "story_05"
PROJECT_NAME = "Story 05: Dynamic Targets Zaton"

# NPC и локации
NPC_ID = "zat_a2_stalker_barmen"
NPC_LOCATION = "zaton"
SMART_BAR = "zat_b52"  # Смарт Бармена (Skadovsk)
SMART_TARGET_A = "zat_b7"  # Смарт АТП (начальная цель)
SMART_TARGET_B = "zat_b14_smart_terrain"  # Смарт Катакомбы (вторая цель)

# Предметы
QUEST_ITEM = "itm_pda_common"
REWARD_MONEY = 8000
REWARD_ITEM = "medkit_army"

# Квест
QUEST_ID = f"{MOD_SLUG}_dynamic_search"
TAKE_DIALOG_ID = f"{MOD_SLUG}_take"
TURNIN_DIALOG_ID = f"{MOD_SLUG}_turnin"

# Инфопоршни
INFO_STARTED = f"{MOD_SLUG}_started"
INFO_INTEL_FOUND = f"{MOD_SLUG}_intel_found"  # Поршень, меняющий цель
INFO_DONE = f"{MOD_SLUG}_done"


def create_project() -> ModProject:
    """Создаёт проект квеста с динамической целью и описанием."""

    # 1. Квест
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[TAKE_DIALOG_ID, TURNIN_DIALOG_ID],
        title_ru="Поиск данных в Затоне",
        title_en="Data Search in Zaton",
        descr_ru="Борода просит найти важные данные в Затоне.",
        descr_en="Beard asks you to find important data in Zaton.",
        is_storyline=True,
        taken_info=INFO_STARTED,
        complete_info=INFO_DONE,
        reward_money=REWARD_MONEY,
        reward_item_alias=REWARD_ITEM,
        reward_item_count=1,
        stages={
            0: Stage(
                id=0,
                title_ru="Найти данные",
                title_en="Find the data",
                descr_ru="Ищи данные в указанной зоне.",
                descr_en="Look for data in the specified zone.",
                # Базовая цель
                target_alias=SMART_TARGET_A,
                # Динамические варианты цели
                target_variants=[
                    TargetVariant(
                        when=[HasInfo(info=INFO_INTEL_FOUND)],
                        value=SMART_TARGET_B, # Если нашли намек/поршень, идем в Катакомбы
                    ),
                ],
                # Динамические варианты описания
                descr_variants=[
                    DescrVariant(
                        when=[HasItem(item_alias=QUEST_ITEM)],
                        text_ru="У тебя есть ПДА с данными. Неси его Бороде.",
                        text_en="You have the PDA with data. Take it to Beard.",
                    ),
                ],
            ),
            1: Stage(
                id=1,
                title_ru="Вернуться к Бороде",
                title_en="Return to Beard",
                descr_ru="Отнеси найденные данные Бороде на Скадовск.",
                descr_en="Take the found data to Beard on Skadovsk.",
                target_alias=SMART_BAR,
            ),
        },
        # Переход на этап 1 при наличии предмета
        transfer_conditions={
            0: {"complete": [HasItem(item_alias=QUEST_ITEM)]},
        },
    )

    # 2. Диалог взятия
    take_dialog = Dialog(
        id=TAKE_DIALOG_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="take",
        preconditions=[DontHasInfo(info=INFO_STARTED)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Борода, есть работа?",
                text_en="Beard, got any work?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Нужно проверить одну точку на АТП. Там могут быть данные.",
                text_en="Need to check a spot at ATP. There might be data.",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Я займусь этим.",
                text_en="I'll handle it.",
                actions=[
                    GiveInfo(info=INFO_STARTED),
                    GiveTask(task_id=QUEST_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Будь осторожен.",
                text_en="Be careful.",
            ),
            4: Phrase(
                id=4,
                text_ru="Не сейчас.",
                text_en="Not now.",
            ),
        },
    )

    # 3. Диалог сдачи
    turnin_dialog = Dialog(
        id=TURNIN_DIALOG_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turnin",
        preconditions=[HasInfo(info=INFO_STARTED)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Я нашёл данные.",
                text_en="I found the data.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Что там?",
                text_en="What's there?",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Вот ПДА.",
                text_en="Here's the PDA.",
                preconditions=[HasItem(item_alias=QUEST_ITEM)],
                actions=[
                    RemoveItem(item_alias=QUEST_ITEM, count=1),
                    GiveInfo(info=INFO_DONE),
                    CompleteTask(task_id=QUEST_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Хорошо. Держи награду.",
                text_en="Good. Here's your reward.",
            ),
            4: Phrase(
                id=4,
                text_ru="Ещё ищу.",
                text_en="Still looking.",
            ),
        },
    )

    return ModProject(
        name=PROJECT_NAME,
        mod_slug=MOD_SLUG,
        quests={QUEST_ID: quest},
        dialogs={
            TAKE_DIALOG_ID: take_dialog,
            TURNIN_DIALOG_ID: turnin_dialog,
        },
    )


if __name__ == "__main__":
    project = create_project()
    builder = ModBuilder(
        output_dir=Path("output/phase3"),
        vanilla_root=Path("_unpacked"),
    )
    if not builder.build_project(project):
        raise SystemExit("Сборка не удалась: смотрите logs/app.log.")
    print(f"Мод собран в: {builder.output_dir}")