"""
Скрипт квеста warfare_02.py для S.T.A.L.K.E.R. Anomaly 1.5.3.
Демонстрирует Warfare-паттерн: многоэтапный штурм двух смартов подряд.

Логика ID:
- Локация: zaton (Затон).
- Квестодатель: Бармен (zat_a2_stalker_barmen), смарт zat_b52 (Скадовск).
- Этап 0: Штурм АТП (zat_b7).
- Этап 1: Штурм Катакомб (zat_b14_smart_terrain).
- Враги: squad.mercenary_advanced (наёмники).
- Союзники: sim_default_stalker_1 (сталкеры-подкрепление).
- Снаряжение: wpn_ak74 (этап 0), medkit_army (этап 1).
- Переход между этапами: через warfare_capture (stage_cleared автоматически).
- Выдача снаряжения через Stage.on_start_actions с GiveItem — API гарантирует
  идемпотентность: предмет выдаётся на каждом тике _status, пока его количество
  в инвентаре меньше count. При переходе на следующий этап выдача не повторяется,
  т.к. pstor-ключ <...>_v_<stage>_started фиксирует выполнение.
"""
from __future__ import annotations

from pathlib import Path
from src.compiler.builder import ModBuilder
from src.core.models import (
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveItem,
    GiveTask,
    ModProject,
    Phrase,
    Quest,
    Stage,
    WarfareCapture,
)

# ---------------------------------------------------------------------------
# Константы сценария
# ---------------------------------------------------------------------------
MOD_SLUG = "warfare_02"
PROJECT_NAME = "Warfare 02: Double Assault"

# NPC и локации
NPC_ID = "zat_a2_stalker_barmen"
NPC_LOCATION = "zaton"
SMART_GIVER = "zat_b52"

# Две точки штурма
SMART_STAGE_0 = "zat_b7"              # АТП
SMART_STAGE_1 = "zat_b14_smart_terrain"  # Катакомбы

# Отряды
ENEMY_SQUAD = "squad.mercenary_advanced"
ALLY_SQUAD = "sim_default_stalker_1"

# Снаряжение по этапам
ITEM_STAGE_0 = "wpn_ak74"
ITEM_STAGE_1 = "medkit_army"

# Квест
QUEST_ID = f"{MOD_SLUG}_double_assault"
TAKE_DIALOG_ID = f"{MOD_SLUG}_take"

# Инфопоршни
INFO_STARTED = f"{MOD_SLUG}_started"
INFO_DONE = f"{MOD_SLUG}_done"


def create_project() -> ModProject:
    """Создаёт проект Warfare-квеста с двумя этапами штурма."""

    # 1. Квест
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[TAKE_DIALOG_ID],
        title_ru="Двойной штурм",
        title_en="Double Assault",
        descr_ru="Захватите две ключевые точки в Затоне.",
        descr_en="Capture two key points in Zaton.",
        is_storyline=False,
        requires_warfare=True,  # Warfare-квест: вне режима не тикает
        taken_info=INFO_STARTED,
        complete_info=INFO_DONE,
        reward_money=25000,
        reward_item_alias="wpn_ak74",
        reward_item_count=1,
        stages={
            # Этап 0: Штурм АТП
            0: Stage(
                id=0,
                title_ru="Захватить АТП",
                title_en="Capture ATP",
                descr_ru="Уничтожьте врагов и захватите АТП.",
                descr_en="Destroy enemies and capture the ATP.",
                target_alias=SMART_STAGE_0,
                warfare_capture=WarfareCapture(
                    smart_alias=SMART_STAGE_0,
                    enemy_squad_alias=ENEMY_SQUAD,
                    ally_squad_alias=ALLY_SQUAD,
                    ally_count=2,
                ),
                # Автоматическая выдача АК-74 при входе в этап.
                # GiveItem идемпотентен: выдаётся, пока в инвентаре < 1.
                on_start_actions=[
                    GiveItem(item_alias=ITEM_STAGE_0, count=1),
                ],
            ),
            # Этап 1: Штурм Катакомб
            1: Stage(
                id=1,
                title_ru="Захватить Катакомбы",
                title_en="Capture Catacombs",
                descr_ru="Продвигайтесь к Катакомбам и захватите их.",
                descr_en="Advance to the Catacombs and capture them.",
                target_alias=SMART_STAGE_1,
                warfare_capture=WarfareCapture(
                    smart_alias=SMART_STAGE_1,
                    enemy_squad_alias=ENEMY_SQUAD,
                    ally_squad_alias=ALLY_SQUAD,
                    ally_count=2,
                ),
                # Автоматическая выдача армейской аптечки.
                # На этом этапе pstor-ключ этапа 0 уже установлен,
                # поэтому снаряжение этапа 0 повторно не выдаётся.
                on_start_actions=[
                    GiveItem(item_alias=ITEM_STAGE_1, count=2),
                ],
            ),
        },
        # Переходы между Warfare-этапами обрабатываются автоматически
        # через stage_cleared (уничтожение вражеского отряда + захват смарта).
        # transfer_conditions не нужны для основного продвижения.
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
                text_ru="Бармен, нужна крупная операция?",
                text_en="Barman, need a big operation?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Нужно выбить наёмников с двух точек: АТП и Катакомб.",
                text_en="Need to kick mercenaries out of two points: ATP and Catacombs.",
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
                text_ru="Удачи в бою, сталкер.",
                text_en="Good luck in battle, stalker.",
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