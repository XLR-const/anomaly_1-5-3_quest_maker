"""
Скрипт квеста story_04.py для S.T.A.L.K.E.R. Anomaly 1.5.3.
Демонстрирует Story-паттерн с ветвлением диалога:
1. Взятие: развилка "Согласие" (выдача квеста) vs "Отказ" (завершение диалога).
2. Сдача: выбор награды ("Деньги" или "Оружие") через разные ветки реплик.

Логика ID:
- Локация: escape (Кордон).
- NPC: esc_m_trader (Сидорович), смарт esc_smart_terrain_5_7 (Бункер).
- Квест: story_04_delivery (доставка документа).
- Предмет сдачи: itm_pda_common (ПДА как документ).
- Награды: wpn_ak74 (оружие) и деньги (5000).
- Поршни: story_04_reward_cash / story_04_reward_gun (чтобы блокировать повторный выбор другой награды, если нужно, или просто для логирования).
"""
from __future__ import annotations

from pathlib import Path
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
MOD_SLUG = "story_04"
PROJECT_NAME = "Story 04: Branching Rewards"

# NPC и локации
NPC_ID = "esc_m_trader"
NPC_LOCATION = "escape"
SMART_TRADER = "esc_smart_terrain_5_7"

# Квест и предмет
QUEST_ID = f"{MOD_SLUG}_delivery"
QUEST_ITEM = "itm_pda_common"

# Диалоги
TAKE_DIALOG_ID = f"{MOD_SLUG}_take"
TURNIN_DIALOG_ID = f"{MOD_SLUG}_turnin"

# Инфопоршни
INFO_STARTED = f"{MOD_SLUG}_started"
INFO_DONE = f"{MOD_SLUG}_done"
INFO_REWARD_CASH = f"{MOD_SLUG}_reward_cash"
INFO_REWARD_GUN = f"{MOD_SLUG}_reward_gun"

# Награды
REWARD_MONEY = 5000
REWARD_WEAPON = "wpn_ak74"


def create_project() -> ModProject:
    """Создаёт проект квеста с ветвлением выбора награды."""

    # 1. Квест
    # Примечание: Так как сдача идёт через диалог с выбором, return_to_giver_stage не задаём.
    # Завершение квеста происходит внутри диалога через CompleteTask.
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[TAKE_DIALOG_ID, TURNIN_DIALOG_ID],
        title_ru="Важная доставка",
        title_en="Important Delivery",
        descr_ru="Сидорович просит доставить ПДА на базу.",
        descr_en="Sidorovich asks you to deliver a PDA to the base.",
        is_storyline=True,
        taken_info=INFO_STARTED,
        complete_info=INFO_DONE,
        stages={
            0: Stage(
                id=0,
                title_ru="Доставить ПДА",
                title_en="Deliver the PDA",
                descr_ru="Найдите ПДА и принесите его Сидоровичу.",
                descr_en="Find the PDA and bring it to Sidorovich.",
                target_alias=SMART_TRADER,
            ),
        },
        # Переход на этап 1 (сдача) при наличии предмета
        transfer_conditions={
            0: {"complete": [HasItem(item_alias=QUEST_ITEM)]},
        },
        # Награда не задаётся здесь, так как она выбирается в диалоге
        reward_money=None,
        reward_item_alias=None,
    )

    # 2. Диалог взятия (с ветвлением согласия/отказа)
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
                text_ru="Сидорович, есть работа?",
                text_en="Sidorovich, got any work?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Нужно отнести ПДА на базу. Берёшься?",
                text_en="Need to take a PDA to the base. Will you take it?",
                next_phrases=[2, 4], # 2 - Согласие, 4 - Отказ
            ),
            2: Phrase(
                id=2,
                text_ru="Давай сюда.",
                text_en="Give it here.",
                actions=[
                    GiveInfo(info=INFO_STARTED),
                    GiveTask(task_id=QUEST_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Не подведи.",
                text_en="Don't let me down.",
            ),
            4: Phrase(
                id=4,
                text_ru="Нет, не сейчас.",
                text_en="No, not now.",
                # Ветка отказа просто завершает диалог (нет next_phrases или пустой список)
            ),
        },
    )

    # 3. Диалог сдачи (с выбором награды)
    turnin_dialog = Dialog(
        id=TURNIN_DIALOG_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turnin",
        # Доступен, если квест взят
        preconditions=[HasInfo(info=INFO_STARTED)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Я принёс ПДА.",
                text_en="I brought the PDA.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Отлично. Что хочешь в награду?",
                text_en="Great. What do you want as a reward?",
                next_phrases=[2, 4], # 2 - Деньги, 4 - Оружие
            ),
            # Ветка 1: Выбор денег
            2: Phrase(
                id=2,
                text_ru="Мне нужны деньги.",
                text_en="I need money.",
                preconditions=[HasItem(item_alias=QUEST_ITEM)],
                actions=[
                    RemoveItem(item_alias=QUEST_ITEM, count=1),
                    GiveMoney(amount=REWARD_MONEY),
                    GiveInfo(info=INFO_REWARD_CASH),
                    GiveInfo(info=INFO_DONE),
                    CompleteTask(task_id=QUEST_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Держи купюры.",
                text_en="Here are the bills.",
            ),
            # Ветка 2: Выбор оружия
            4: Phrase(
                id=4,
                text_ru="Лучше дай ствол.",
                text_en="Better give me a gun.",
                preconditions=[HasItem(item_alias=QUEST_ITEM)],
                actions=[
                    RemoveItem(item_alias=QUEST_ITEM, count=1),
                    GiveItem(item_alias=REWARD_WEAPON, count=1),
                    GiveInfo(info=INFO_REWARD_GUN),
                    GiveInfo(info=INFO_DONE),
                    CompleteTask(task_id=QUEST_ID),
                ],
                next_phrases=[5],
            ),
            5: Phrase(
                id=5,
                text_ru="Бери АК-74. Не благодари.",
                text_en="Take the AK-74. Don't mention it.",
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