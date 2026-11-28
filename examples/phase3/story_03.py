"""
Скрипт квеста story_03.py для S.T.A.L.K.E.R. Anomaly 1.5.3.
Демонстрирует цепочку из двух связанных Story-квестов:
  Q1 (зачистка отряда) -> Q2 (доклад Сидоровичу со сдачей ПДА).
Q1: fail_on_giver_death=False, on_complete_actions=[GiveTask(Q2)].
Q2: fail_on_giver_death=True.
"""
from __future__ import annotations

from pathlib import Path
from aqm.compiler.builder import ModBuilder
from aqm.core.models import (
    CompleteTask,
    CustomSquad,
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
    QuestCondlist,
    RemoveItem,
    RemoveSquad,
    SpawnSquad,
    Stage,
)

# ---------------------------------------------------------------------------
# Константы сценария
# ---------------------------------------------------------------------------
MOD_SLUG = "story_03"
PROJECT_NAME = "Story 03: Sidorovich Chain"

# NPC и локации
NPC_ID = "esc_m_trader"
NPC_LOCATION = "escape"
SMART_TRADER = "esc_smart_terrain_5_7"
SMART_TARGET = "esc_smart_terrain_5_7"  # Точка зачистки

# Отряд и предметы
SQUAD_ID = f"{MOD_SLUG}_merc_squad"
INFO_SQUAD_DEAD = f"{MOD_SLUG}_merc_dead"
QUEST_ITEM = "itm_pda_common"
REWARD_WEAPON = "wpn_ak74"
REWARD_FOOD = "conserva"
REWARD_MONEY = 15000

# Квесты
Q1_ID = f"{MOD_SLUG}_recon"
Q2_ID = f"{MOD_SLUG}_report"

# Диалоги
Q1_TAKE_DIALOG = f"{MOD_SLUG}_recon_take"
Q2_TURNIN_DIALOG = f"{MOD_SLUG}_report_turnin"

# Инфопоршни
Q1_TAKEN = f"{MOD_SLUG}_recon_taken"
Q1_DONE = f"{MOD_SLUG}_recon_done"
Q2_TAKEN = f"{MOD_SLUG}_report_taken"
Q2_DONE = f"{MOD_SLUG}_report_done"


def create_project() -> ModProject:
    """Создаёт проект цепочки Q1 -> Q2."""

    # 1. Кастомный отряд наёмников для Q1
    merc_squad = CustomSquad(
        id=SQUAD_ID,
        faction="killer",
        npc=["sim_default_stalker_1"],
        npc_in_squad=[3, 5],
        target_smart=SMART_TARGET,
        relationship="enemy",
        death_infos=[INFO_SQUAD_DEAD],
    )

    # 2. Q1: Разведка/зачистка
    q1 = Quest(
        id=Q1_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=Q1_TAKE_DIALOG,
        dialog_ids=[Q1_TAKE_DIALOG],
        title_ru="Зачистка блокпоста",
        title_en="Checkpoint Cleansing",
        descr_ru="Сидорович просит зачистить блокпост наёмников.",
        descr_en="Sidorovich asks you to clear the mercenary checkpoint.",
        is_storyline=True,
        taken_info=Q1_TAKEN,
        complete_info=Q1_DONE,
        cleanup_infos=[INFO_SQUAD_DEAD],
        # Смерть Сидоровича НЕ проваливает Q1 (цепочка должна продолжиться)
        fail_on_giver_death=False,
        stages={
            0: Stage(
                id=0,
                title_ru="Уничтожить наёмников",
                title_en="Kill the mercenaries",
                descr_ru="Найдите и уничтожьте отряд наёмников.",
                descr_en="Find and destroy the mercenary squad.",
                target_alias=SMART_TARGET,
                on_start_actions=[
                    SpawnSquad(
                        squad_alias=SQUAD_ID,
                        smart_alias=SMART_TARGET,
                        mode="story",
                    ),
                ],
            ),
        },
        # Завершение по смерти отряда
        extra_condlists=[
            QuestCondlist(
                when=[HasInfo(info=INFO_SQUAD_DEAD)],
                result="complete",
            ),
        ],
        # После завершения Q1 сразу выдаём Q2 (мост цепочки)
        on_complete_actions=[
            GiveTask(task_id=Q2_ID),
        ],
        on_fail_actions=[
            RemoveSquad(squad_alias=SQUAD_ID),
        ],
    )

    # 3. Q2: Доклад Сидоровичу со сдачей ПДА
    q2 = Quest(
        id=Q2_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=Q2_TURNIN_DIALOG,
        dialog_ids=[Q2_TURNIN_DIALOG],
        title_ru="Доклад Сидоровичу",
        title_en="Report to Sidorovich",
        descr_ru="Принеси найденный ПДА Сидоровичу в обмен на награду.",
        descr_en="Bring the found PDA to Sidorovich in exchange for a reward.",
        is_storyline=True,
        taken_info=Q2_TAKEN,
        complete_info=Q2_DONE,
        # Смерть Сидоровича проваливает Q2
        fail_on_giver_death=True,
        reward_money=REWARD_MONEY,
        reward_item_alias=REWARD_WEAPON,
        reward_item_count=1,
        stages={
            0: Stage(
                id=0,
                title_ru="Вернуться к Сидоровичу",
                title_en="Return to Sidorovich",
                descr_ru="Вернись к Сидоровичу и сдай ПДА.",
                descr_en="Return to Sidorovich and hand over the PDA.",
                target_alias=SMART_TRADER,
            ),
        },
        on_complete_actions=[
            # Выдаём консервы как дополнительную награду через on_complete
            GiveItem(item_alias=REWARD_FOOD, count=3),
        ],
    )

    # 4. Диалог взятия Q1
    q1_take = Dialog(
        id=Q1_TAKE_DIALOG,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=Q1_ID,
        role="take",
        preconditions=[DontHasInfo(info=Q1_TAKEN)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Сидорович, есть дело?",
                text_en="Sidorovich, got any work?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Наёмники засели на блокпосту. Зачисти их.",
                text_en="Mercenaries are camped at the checkpoint. Clear them out.",
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

    # 5. Диалог сдачи Q2 (с проверкой ПДА)
    q2_turnin = Dialog(
        id=Q2_TURNIN_DIALOG,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=Q2_ID,
        role="turnin",
        preconditions=[HasInfo(info=Q2_TAKEN)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Сидорович, я нашёл ПДА.",
                text_en="Sidorovich, I found the PDA.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Показывай.",
                text_en="Show me.",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Держи.",
                text_en="Here you go.",
                preconditions=[HasItem(item_alias=QUEST_ITEM, count=1)],
                actions=[
                    RemoveItem(item_alias=QUEST_ITEM, count=1),
                    GiveInfo(info=Q2_DONE),
                    CompleteTask(task_id=Q2_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Отличная работа. Держи награду.",
                text_en="Good job. Here's your reward.",
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
        quests={
            Q1_ID: q1,
            Q2_ID: q2,
        },
        dialogs={
            Q1_TAKE_DIALOG: q1_take,
            Q2_TURNIN_DIALOG: q2_turnin,
        },
        squads={SQUAD_ID: merc_squad},
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