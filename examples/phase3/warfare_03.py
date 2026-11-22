"""
Скрипт квеста warfare_03.py для S.T.A.L.K.E.R. Anomaly 1.5.3.
Демонстрирует Warfare-паттерн с ручным управлением отрядом:
1. Спавн отряда через SpawnSquad(mode="warfare").
2. Установка цели через SetTarget.
3. Завершение по условию SmartOwner (захват точки).

Локация: Мёртвый Город (deadcity).
Квестодатель: Душман (cit_killers_merc_trader_stalker), смарт cit_killers.
Цель: Отправить свой отряд на захват смарта cit_kanaliz1.
"""
from __future__ import annotations

from pathlib import Path
from src.compiler.builder import ModBuilder
from src.core.models import (
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveTask,
    HasInfo,
    ModProject,
    Phrase,
    Quest,
    SmartOwner,
    SpawnSquad,
    Stage,
    SetTarget,
)

# ---------------------------------------------------------------------------
# Константы сценария
# ---------------------------------------------------------------------------
MOD_SLUG = "warfare_03"
PROJECT_NAME = "Warfare 03: Manual Squad Control"

# NPC и локации
NPC_ID = "cit_killers_merc_trader_stalker"
NPC_LOCATION = "deadcity"
SMART_GIVER = "cit_killers"
SMART_TARGET = "cit_kanaliz1"

# Отряд игрока (союзный)
PLAYER_SQUAD_ALIAS = f"{MOD_SLUG}_player_squad"
# Используем стандартную секцию наемников как базу для своего отряда
SQUAD_SECTION = "sim_default_killer_1"

# Квест
QUEST_ID = f"{MOD_SLUG}_capture_kanaliz"
TAKE_DIALOG_ID = f"{MOD_SLUG}_take"

# Инфопоршни
INFO_STARTED = f"{MOD_SLUG}_started"
INFO_DONE = f"{MOD_SLUG}_done"


def create_project() -> ModProject:
    """Создаёт проект Warfare-квеста с ручным управлением отрядом."""

    # 1. Квест
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[TAKE_DIALOG_ID],
        title_ru="Захват Канализации",
        title_en="Capture the Sewers",
        descr_ru="Отправьте свой отряд на захват Канализации.",
        descr_en="Send your squad to capture the Sewers.",
        is_storyline=False,
        requires_warfare=True,  # Обязательно для Warfare
        taken_info=INFO_STARTED,
        complete_info=INFO_DONE,
        reward_money=20000,
        reward_item_alias="wpn_vintorez",
        reward_item_count=1,
        stages={
            0: Stage(
                id=0,
                title_ru="Отправить отряд",
                title_en="Deploy the squad",
                descr_ru="Прикажите отряду выдвинуться на Канализацию.",
                descr_en="Order the squad to move to the Sewers.",
                target_alias=SMART_TARGET,
                on_start_actions=[
                    # Спавн отряда в режиме Warfare.
                    # Он будет зарегистрирован как динамический отряд квеста.
                    SpawnSquad(
                        squad_alias=PLAYER_SQUAD_ALIAS,
                        smart_alias=SMART_GIVER, # Спавн рядом с квестодателем
                        mode="warfare",
                    ),
                    # Установка цели для отряда.
                    # Отряд начнет движение к SMART_TARGET.
                    SetTarget(
                        squad_alias=PLAYER_SQUAD_ALIAS,
                        smart_alias=SMART_TARGET,
                    ),
                ],
            ),
        },
        # Условие завершения: точка cit_kanaliz1 принадлежит фракции killer (наемники)
        # Так как мы играем за наемников (или отряд наемников), это означает успех.
        extra_condlists=[
            {
                "complete": [
                    SmartOwner(smart_alias=SMART_TARGET, faction="killer")
                ]
            }
        ],
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
                text_ru="Душман, есть задание?",
                text_en="Dushman, got a mission?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Нужно взять под контроль Канализацию. Твой отряд готов?",
                text_en="Need to take control of the Sewers. Is your squad ready?",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Готов. Выдвигаемся.",
                text_en="Ready. Moving out.",
                actions=[
                    GiveInfo(info=INFO_STARTED),
                    GiveTask(task_id=QUEST_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Удачи в бою.",
                text_en="Good luck in battle.",
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