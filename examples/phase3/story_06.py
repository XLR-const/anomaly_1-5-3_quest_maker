"""
Скрипт квеста story_06.py для S.T.A.L.K.E.R. Anomaly 1.5.3.
Демонстрирует Story-паттерн с ограничением по фракции и автоматической сдачей.

Логика ID:
- Локация: zaton (Затон).
- Квестодатель: Шустрый (zat_a2_stalker_leader_freedom), смарт zat_b52 (Скадовск).
- Фракция: "freedom" (Свобода). Квест доступен только членам группировки.
- Цель: Зачистить лагерь бандитов на смарте zat_b7 (АТП).
- Сдача: Автоматическая при приближении к Шустрому (return_to_giver_stage).
"""
from __future__ import annotations

from pathlib import Path
from src.compiler.builder import ModBuilder
from src.core.models import (
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
MOD_SLUG = "story_06"
PROJECT_NAME = "Story 06: Freedom Duty"

# NPC и локации
NPC_ID = "zat_a2_stalker_leader_freedom"  # Шустрый
NPC_LOCATION = "zaton"
SMART_GIVER = "zat_b52"  # Скадовск
SMART_TARGET = "zat_b7"  # АТП (лагерь бандитов)

# Отряд и предметы
SQUAD_ID = f"{MOD_SLUG}_bandit_squad"
INFO_SQUAD_DEAD = f"{MOD_SLUG}_bandits_dead"

# Квест
QUEST_ID = f"{MOD_SLUG}_cleanse_atp"
TAKE_DIALOG_ID = f"{MOD_SLUG}_take"

# Инфопоршни
INFO_STARTED = f"{MOD_SLUG}_started"
INFO_DONE = f"{MOD_SLUG}_done"


def create_project() -> ModProject:
    """Создаёт проект квеста для фракции Свобода с автосдачей."""

    # 1. Описание кастомного отряда бандитов
    bandit_squad = CustomSquad(
        id=SQUAD_ID,
        faction="bandit",
        npc=["sim_default_bandit_1", "sim_default_bandit_2"],
        npc_in_squad=[4, 6],
        target_smart=SMART_TARGET,
        relationship="enemy",
        death_infos=[INFO_SQUAD_DEAD],
    )

    # 2. Квест
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[TAKE_DIALOG_ID],
        title_ru="Помощь Свободе",
        title_en="Help for Freedom",
        descr_ru="Шустрый просит зачистить бандитов на АТП.",
        descr_en="Shustry asks you to clear out the bandits at ATP.",
        is_storyline=True,
        taken_info=INFO_STARTED,
        complete_info=INFO_DONE,
        # Ограничение по фракции: доступно только Свободе
        requires_faction="freedom",
        # Награда за автоматическую сдачу
        reward_money=10000,
        reward_item_alias="medkit_army",
        reward_item_count=2,
        stages={
            0: Stage(
                id=0,
                title_ru="Зачистить АТП",
                title_en="Clear ATP",
                descr_ru="Уничтожьте отряд бандитов на АТП.",
                descr_en="Destroy the bandit squad at ATP.",
                target_alias=SMART_TARGET,
                on_start_actions=[
                    SpawnSquad(
                        squad_alias=SQUAD_ID,
                        smart_alias=SMART_TARGET,
                        mode="story",
                    ),
                ],
            ),
            # Этап 1: Возврат к квестодателю для автосдачи
            1: Stage(
                id=1,
                title_ru="Вернуться к Шустрому",
                title_en="Return to Shustry",
                descr_ru="Вернитесь на базу Свободы за наградой.",
                descr_en="Return to the Freedom base for your reward.",
                target_alias=SMART_GIVER,
            ),
        },
        # Переход на этап 1 (возврат) при смерти отряда
        transfer_conditions={
            0: {"complete": [HasInfo(info=INFO_SQUAD_DEAD)]},
        },
        # Автоматическая сдача при подходе к NPC на этапе 1
        return_to_giver_stage=1,
        return_distance=40.0,
        cleanup_infos=[INFO_SQUAD_DEAD],
        on_fail_actions=[
            RemoveSquad(squad_alias=SQUAD_ID),
        ],
    )

    # 3. Диалог взятия квеста
    # Так как сдача автоматическая, диалог сдачи не нужен.
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
                text_ru="Шустрый, нужна помощь?",
                text_en="Shustry, need help?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Бандиты засели на АТП. Зачисти их.",
                text_en="Bandits are camped at ATP. Clear them out.",
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
                text_ru="Удачи, брат.",
                text_en="Good luck, brother.",
            ),
            4: Phrase(
                id=4,
                text_ru="Не сейчас.",
                text_en="Not now.",
            ),
        },
    )

    return ModProject(
        name=PROJECT_NAME,
        mod_slug=MOD_SLUG,
        quests={QUEST_ID: quest},
        dialogs={
            TAKE_DIALOG_ID: take_dialog,
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