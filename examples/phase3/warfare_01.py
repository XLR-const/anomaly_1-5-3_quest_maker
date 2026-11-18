"""
Скрипт квеста warfare_01.py для S.T.A.L.K.E.R. Anomaly 1.5.3.
Демонстрирует Warfare-паттерн: захват смарт-террейна с помощью WarfareCapture.

Логика ID и выбор локации:
- Локация: zaton (Затон).
- Смарт: zat_b14_smart_terrain (Катакомбы). Выбран как хорошо защищенная точка, часто контролируемая наемниками или бандитами в ваниле, что подходит для штурма.
- Вражеский отряд: squad.mercenary_advanced (стандартный сильный отряд наемников).
- Союзное подкрепление: sim_default_killer_1 (наемники, если игрок за них, или просто нейтральные/дружественные сталкеры для массовки). 
  Примечание: В Warfare логике ally_squad обычно должен быть дружественен игроку. Если игрок за Долг/Свободу, лучше использовать их отряды, но так как мы не знаем фракцию игрока в коде генератора, используем стандартный "свой" отряд или нейтральный. 
  Для теста возьмем sim_default_stalker_1 (сталкеры) как союзников, предполагая, что игрок может быть за них или они просто помогают. 
  Однако, API требует faction в CustomSquad? Нет, WarfareCapture использует секции.
  Пусть союзники будут из группировки игрока? API не позволяет динамически менять faction в Capture.
  Используем sim_default_csky_1 (Чистое Небо) как пример союзного отряда, или просто оставим ally_count=0 если не уверены. 
  Но требование: "союзное подкрепление через ally_squad_alias с ally_count=2".
  Возьмем sim_default_stalker_1. Если игрок за другую фракцию, они могут быть врагами, но это тест механики.
  
- Квестодатель: Бармен (zat_a2_stalker_barmen), смарт zat_b52.
- Требуется: requires_warfare=True.
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
    Stage,
    WarfareCapture,
)

# ---------------------------------------------------------------------------
# Константы сценария
# ---------------------------------------------------------------------------
MOD_SLUG = "warfare_01"
PROJECT_NAME = "Warfare 01: Catacombs Assault"

# NPC и локации
NPC_ID = "zat_a2_stalker_barmen"
NPC_LOCATION = "zaton"
SMART_GIVER = "zat_b52"  # Скадовск
SMART_TARGET = "zat_b14_smart_terrain"  # Катакомбы

# Отряды
ENEMY_SQUAD = "squad.mercenary_advanced"
ALLY_SQUAD = "sim_default_stalker_1"  # Союзное подкрепление

# Квест
QUEST_ID = f"{MOD_SLUG}_capture_catacombs"
TAKE_DIALOG_ID = f"{MOD_SLUG}_take"

# Инфопоршни
INFO_STARTED = f"{MOD_SLUG}_started"
INFO_DONE = f"{MOD_SLUG}_done"


def create_project() -> ModProject:
    """Создаёт проект Warfare-квеста на захват точки."""

    # 1. Квест
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[TAKE_DIALOG_ID],
        title_ru="Штурм Катакомб",
        title_en="Catacombs Assault",
        descr_ru="Захватите Катакомбы у наёмников.",
        descr_en="Capture the Catacombs from the mercenaries.",
        is_storyline=False,  # Warfare квесты обычно не storyline в смысле глобального сюжета, но могут быть
        requires_warfare=True,  # Обязательно для Warfare
        taken_info=INFO_STARTED,
        complete_info=INFO_DONE,
        reward_money=15000,
        reward_item_alias="wpn_ak74",
        reward_item_count=1,
        stages={
            0: Stage(
                id=0,
                title_ru="Захватить точку",
                title_en="Capture the point",
                descr_ru="Уничтожьте врагов и дождитесь захвата смарта.",
                descr_en="Destroy enemies and wait for the smart to be captured.",
                target_alias=SMART_TARGET,
                warfare_capture=WarfareCapture(
                    smart_alias=SMART_TARGET,
                    enemy_squad_alias=ENEMY_SQUAD,
                    ally_squad_alias=ALLY_SQUAD,
                    ally_count=2,
                ),
            ),
        },
        # Warfare квесты завершаются автоматически при захвате точки (stage_cleared)
        # transfer_conditions не нужны для основного перехода, если используется warfare_capture
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
                text_ru="Бармен, есть военная работа?",
                text_en="Barman, got any military work?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Наёмники засели в Катакомбах. Выбей их оттуда.",
                text_en="Mercenaries are dug in at the Catacombs. Kick them out.",
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