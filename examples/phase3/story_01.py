"""
Скрипт квеста story_01.py для S.T.A.L.K.E.R. Anomaly 1.5.3.
Демонстрирует Story-паттерн: спавн отряда -> смерть отряда (on_death) -> condlist -> завершение.
"""
from __future__ import annotations

from pathlib import Path
from aqm.compiler.builder import ModBuilder
from aqm.core.models import (
    CustomSquad,
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveTask,
    HasInfo,
    ModProject,
    Phrase,
    Quest,
    QuestCondlist,
    RemoveSquad,
    SpawnSquad,
    Stage,
)

# ---------------------------------------------------------------------------
# Константы сценария
# ---------------------------------------------------------------------------
MOD_SLUG = "story_01"
PROJECT_NAME = "Story 01: Wolf's Request"

# NPC и локации
NPC_ID = "esc_2_12_stalker_wolf"
NPC_LOCATION = "escape"
SMART_WOLF = "esc_smart_terrain_2_12"

# Отряд бандитов
SQUAD_ID = f"{MOD_SLUG}_bandit_squad"
INFO_SQUAD_DEAD = f"{MOD_SLUG}_bandits_dead"

# Квест
QUEST_ID = f"{MOD_SLUG}_cleanse_bandits"
TAKE_DIALOG_ID = f"{MOD_SLUG}_take"
TURNIN_DIALOG_ID = f"{MOD_SLUG}_turnin"

# Награда
REWARD_ITEM = "medkit_army"
REWARD_MONEY = 5000

# Инфопоршни
INFO_STARTED = f"{MOD_SLUG}_started"
INFO_DONE = f"{MOD_SLUG}_done"


def create_project() -> ModProject:
    """Создаёт проект квеста на зачистку бандитов у Волка."""

    # 1. Описание кастомного отряда бандитов
    # death_infos выдаст поршень INFO_SQUAD_DEAD при полном уничтожении отряда
    bandit_squad = CustomSquad(
        id=SQUAD_ID,
        faction="bandit",
        npc=["sim_default_bandit_1", "sim_default_bandit_2"],
        npc_in_squad=[3, 5],
        target_smart=SMART_WOLF,  # Отряд будет двигаться к этому смарту или оставаться рядом
        relationship="enemy",
        death_infos=[INFO_SQUAD_DEAD],
    )

    # 2. Квест
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[TAKE_DIALOG_ID, TURNIN_DIALOG_ID],
        title_ru="Зачистка лагеря",
        title_en="Camp Cleansing",
        descr_ru="Волк просит зачистить лагерь бандитов неподалёку.",
        descr_en="Wolf asks you to clear out the nearby bandit camp.",
        is_storyline=True,
        reward_money=REWARD_MONEY,
        reward_item_alias=REWARD_ITEM,
        reward_item_count=1,
        complete_info=INFO_DONE,
        taken_info=INFO_STARTED,
        cleanup_infos=[INFO_SQUAD_DEAD],  # Снимаем поршень смерти при провале/повторе
        stages={
            0: Stage(
                id=0,
                title_ru="Уничтожить бандитов",
                title_en="Kill the bandits",
                descr_ru="Найдите и уничтожьте отряд бандитов.",
                descr_en="Find and destroy the bandit squad.",
                target_alias=SMART_WOLF, # Маркер цели
                on_start_actions=[
                    # Спавним отряд в режиме Story (без Warfare логики)
                    SpawnSquad(
                        squad_alias=SQUAD_ID,
                        smart_alias=SMART_WOLF,
                        mode="story",
                    ),
                ],
            ),
        },
        # Условие завершения квеста: наличие инфопоршня о смерти отряда
        extra_condlists=[
            QuestCondlist(
                when=[HasInfo(info=INFO_SQUAD_DEAD)],
                result="complete",
            ),
        ],
        on_fail_actions=[
            RemoveSquad(squad_alias=SQUAD_ID),
        ],
    )

    # 3. Диалог взятия квеста
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
                text_ru="Волк, есть работа?",
                text_en="Wolf, got any work?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Бандиты засели недалеко. Зачисти их.",
                text_en="Bandits are camped nearby. Clear them out.",
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
                text_ru="Удачи, сталкер.",
                text_en="Good luck, stalker.",
            ),
            4: Phrase(
                id=4,
                text_ru="Не сейчас.",
                text_en="Not now.",
            ),
        },
    )

    # 4. Диалог сдачи квеста
    # Примечание: Так как квест завершается автоматически через condlist (extra_condlists),
    # диалог сдачи служит для получения награды и финального разговора.
    # Однако, в данной архитектуре награда выдается через Quest.reward_* в момент completion.
    # Диалог turnin нужен, если мы хотим проверить наличие предмета или просто поговорить.
    # В данном простом случае сдача автоматическая, но добавим диалог для lore.
    turnin_dialog = Dialog(
        id=TURNIN_DIALOG_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turnin",
        # Диалог доступен, если квест взят (INFO_STARTED) и выполнен (INFO_DONE)
        # Но так как complete_info выдается после завершения, используем HasInfo(INFO_DONE)
        preconditions=[HasInfo(info=INFO_DONE)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Бандиты уничтожены.",
                text_en="The bandits are dead.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Хорошая работа. Держи награду.",
                text_en="Good job. Here's your reward.",
                next_phrases=[2],
                # Награда уже выдана через Quest.reward_*, здесь просто текст
            ),
            2: Phrase(
                id=2,
                text_ru="Спасибо.",
                text_en="Thanks.",
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
        squads={SQUAD_ID: bandit_squad},
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