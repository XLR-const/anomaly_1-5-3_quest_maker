"""
Скрипт квеста warfare_04.py для S.T.A.L.K.E.R. Anomaly 1.5.3.
Демонстрирует разделение Warfare и Story логики на два отдельных квеста:
1. Q1 (Warfare) — захват смарта через WarfareCapture.
2. Q2 (Story) — доклад квестодателю через диалог сдачи.
Связь осуществляется через on_complete_actions=[GiveTask(Q2)] в первом квесте.

Логика ID:
- Локация: zaton (Затон).
- Квестодатель: Бармен (zat_a2_stalker_barmen), смарт zat_b52 (Скадовск).
- Q1 (Warfare): захват АТП (zat_b7).
- Q2 (Story): возврат к Бармену за наградой.
"""
from __future__ import annotations

from pathlib import Path
from src.compiler.builder import ModBuilder
from src.core.models import (
    CompleteTask,
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
MOD_SLUG = "warfare_04"
PROJECT_NAME = "Warfare 04: Assault and Report"

# NPC и локации
NPC_ID = "zat_a2_stalker_barmen"
NPC_LOCATION = "zaton"
SMART_GIVER = "zat_b52"      # Скадовск (база Бармена)
SMART_TARGET = "zat_b7"      # АТП (точка захвата)

# Отряды для Warfare
ENEMY_SQUAD = "squad.mercenary_advanced"
ALLY_SQUAD = "sim_default_stalker_1"

# Квесты
Q1_ID = f"{MOD_SLUG}_assault"   # Warfare-квест на захват
Q2_ID = f"{MOD_SLUG}_report"    # Story-квест на доклад

# Диалоги
Q1_TAKE_DIALOG_ID = f"{MOD_SLUG}_take"
Q2_TURNIN_DIALOG_ID = f"{MOD_SLUG}_turnin"

# Инфопоршни
Q1_TAKEN = f"{MOD_SLUG}_taken"
Q1_DONE = f"{MOD_SLUG}_done"
Q2_TAKEN = f"{MOD_SLUG}_report_taken"
Q2_DONE = f"{MOD_SLUG}_report_done"

# Награды
REWARD_MONEY = 20000
REWARD_ITEM = "medkit_army"


def create_project() -> ModProject:
    """Создаёт проект из двух квестов: Warfare-захват и Story-доклад."""

    # 1. Q1: Warfare-квест на захват точки
    q1 = Quest(
        id=Q1_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=Q1_TAKE_DIALOG_ID,
        dialog_ids=[Q1_TAKE_DIALOG_ID],
        title_ru="Зачистка АТП",
        title_en="ATP Cleansing",
        descr_ru="Захватите АТП у наёмников.",
        descr_en="Capture the ATP from the mercenaries.",
        is_storyline=False,
        requires_warfare=True,  # Обязательно для Warfare-квеста
        taken_info=Q1_TAKEN,
        complete_info=Q1_DONE,
        stages={
            0: Stage(
                id=0,
                title_ru="Захватить АТП",
                title_en="Capture ATP",
                descr_ru="Уничтожьте врагов и захватите смарт.",
                descr_en="Destroy enemies and capture the smart.",
                target_alias=SMART_TARGET,
                warfare_capture=WarfareCapture(
                    smart_alias=SMART_TARGET,
                    enemy_squad_alias=ENEMY_SQUAD,
                    ally_squad_alias=ALLY_SQUAD,
                    ally_count=2,
                ),
            ),
        },
        # При успешном захвате выдаём второй (Story) квест
        on_complete_actions=[
            GiveTask(task_id=Q2_ID),
        ],
    )

    # 2. Q2: Story-квест на доклад квестодателю
    q2 = Quest(
        id=Q2_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=Q2_TURNIN_DIALOG_ID,
        dialog_ids=[Q2_TURNIN_DIALOG_ID],
        title_ru="Доклад Бармену",
        title_en="Report to Barman",
        descr_ru="Вернитесь на Скадовск и доложите Бармену об успехе.",
        descr_en="Return to Skadovsk and report the success to Barman.",
        is_storyline=False,
        # Story-квест, Warfare не требуется
        taken_info=Q2_TAKEN,
        complete_info=Q2_DONE,
        reward_money=REWARD_MONEY,
        reward_item_alias=REWARD_ITEM,
        reward_item_count=2,
        stages={
            0: Stage(
                id=0,
                title_ru="Вернуться к Бармену",
                title_en="Return to Barman",
                descr_ru="Поговорите с Барменом на Скадовске.",
                descr_en="Talk to Barman on Skadovsk.",
                target_alias=SMART_GIVER,
            ),
        },
    )

    # 3. Диалог взятия Q1 (Warfare)
    q1_take = Dialog(
        id=Q1_TAKE_DIALOG_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=Q1_ID,
        role="take",
        preconditions=[DontHasInfo(info=Q1_TAKEN)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Бармен, нужна военная операция?",
                text_en="Barman, need a military operation?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Наёмники заняли АТП. Выбей их оттуда.",
                text_en="Mercenaries took over the ATP. Kick them out.",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Я займусь этим.",
                text_en="I'll handle it.",
                actions=[
                    GiveInfo(info=Q1_TAKEN),
                    GiveTask(task_id=Q1_ID),
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

    # 4. Диалог сдачи Q2 (Story)
    q2_turnin = Dialog(
        id=Q2_TURNIN_DIALOG_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=Q2_ID,
        role="turnin",
        preconditions=[HasInfo(info=Q2_TAKEN)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Бармен, АТП наше.",
                text_en="Barman, the ATP is ours.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Отличная работа. Что дальше?",
                text_en="Great job. What's next?",
                next_phrases=[2],
            ),
            2: Phrase(
                id=2,
                text_ru="Докладываю: точка зачищена.",
                text_en="Reporting: the point is cleared.",
                actions=[
                    CompleteTask(task_id=Q2_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Принимай награду, сталкер.",
                text_en="Take your reward, stalker.",
            ),
        },
    )

    return ModProject(
        name=PROJECT_NAME,
        mod_slug=MOD_SLUG,
        quests={
            Q1_ID: q1,
            Q2_ID: q2,
        },
        dialogs={
            Q1_TAKE_DIALOG_ID: q1_take,
            Q2_TURNIN_DIALOG_ID: q2_turnin,
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