"""
Скрипт квеста story_07.py для S.T.A.L.K.E.R. Anomaly 1.5.3.
Демонстрирует Story-паттерн с корректной обработкой провала/отмены (cleanup).

Локация: Мёртвый Город (deadcity).
Квестодатель: Душман (cit_killers_merc_trader_stalker).
Сценарий:
1. Игрок получает задание зачистить лагерь наёмников.
2. Спавнится отряд наёмников (Story mode).
3. Если игрок умирает или отменяет квест (через ПДА), срабатывает on_fail_actions.
4. RemoveSquad удаляет отряд, cleanup_infos снимает временные поршни.
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
MOD_SLUG = "story_07"
PROJECT_NAME = "Story 07: Dead City Cleanup"

# NPC и локации
NPC_ID = "cit_killers_merc_trader_stalker"
NPC_LOCATION = "deadcity"
SMART_GIVER = "cit_killers"  # База наёмников в Мёртвом городе
SMART_TARGET = "cit_bandits" # Лагерь бандитов/наёмников для зачистки

# Отряд и предметы
SQUAD_ID = f"{MOD_SLUG}_enemy_squad"
INFO_SQUAD_DEAD = f"{MOD_SLUG}_squad_dead"
INFO_STARTED = f"{MOD_SLUG}_started"
INFO_DONE = f"{MOD_SLUG}_done"

# Квест
QUEST_ID = f"{MOD_SLUG}_cleanse"
TAKE_DIALOG_ID = f"{MOD_SLUG}_take"

# Награда
REWARD_MONEY = 7000
REWARD_ITEM = "medkit_army"


def create_project() -> ModProject:
    """Создаёт проект квеста с полной очисткой при провале."""

    # 1. Описание кастомного отряда врагов
    enemy_squad = CustomSquad(
        id=SQUAD_ID,
        faction="killer",
        npc=["sim_default_killer_1", "sim_default_killer_2"],
        npc_in_squad=[3, 5],
        target_smart=SMART_TARGET,
        relationship="enemy",
        # При смерти отряда выдаётся поршень INFO_SQUAD_DEAD
        death_infos=[INFO_SQUAD_DEAD],
    )

    # 2. Квест
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[TAKE_DIALOG_ID],
        title_ru="Зачистка сектора",
        title_en="Sector Cleansing",
        descr_ru="Душман просит убрать лишнюю активность в секторе.",
        descr_en="Dushman asks you to remove excess activity in the sector.",
        is_storyline=True,
        taken_info=INFO_STARTED,
        complete_info=INFO_DONE,
        reward_money=REWARD_MONEY,
        reward_item_alias=REWARD_ITEM,
        reward_item_count=1,
        # Список поршней, которые нужно снять при провале/отмене/завершении
        # INFO_SQUAD_DEAD должен быть здесь, чтобы при повторном взятии квест не завершился мгновенно,
        # если отряд был убит ранее, но квест провален.
        cleanup_infos=[INFO_SQUAD_DEAD],
        stages={
            0: Stage(
                id=0,
                title_ru="Уничтожить отряд",
                title_en="Destroy the squad",
                descr_ru="Найдите и уничтожьте вражеский отряд.",
                descr_en="Find and destroy the enemy squad.",
                target_alias=SMART_TARGET,
                on_start_actions=[
                    # Спавн отряда в режиме Story (без Warfare логики)
                    SpawnSquad(
                        squad_alias=SQUAD_ID,
                        smart_alias=SMART_TARGET,
                        mode="story",
                    ),
                ],
            ),
        },
        # Условие завершения: смерть отряда (получение поршня)
        extra_condlists=[
            QuestCondlist(
                when=[HasInfo(info=INFO_SQUAD_DEAD)],
                result="complete",
            ),
        ],
        # ДЕЙСТВИЯ ПРИ ПРОВАЛЕ/ОТМЕНЕ
        # Здесь происходит очистка "мусора": удаление отряда из мира
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
                text_ru="Душман, есть работа?",
                text_en="Dushman, got any work?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="В секторе слишком шумно. Зачисти их.",
                text_en="It's too noisy in the sector. Clear them out.",
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
                text_ru="Не подведи.",
                text_en="Don't let me down.",
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
        squads={SQUAD_ID: enemy_squad},
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