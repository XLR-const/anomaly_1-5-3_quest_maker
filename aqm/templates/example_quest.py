"""Стартовый квест, созданный командой ``aqm init``.

Скрипт полностью автономен: он не требует папки ``_unpacked`` и явного
пути к базе. Проверка и сборка::

    aqm validate scripts/example_quest.py --strict
    aqm build scripts/example_quest.py
"""

from __future__ import annotations

from aqm import (
    CompleteTask,
    Dialog,
    DontHasInfo,
    GiveTask,
    HasInfo,
    ModProject,
    Phrase,
    Quest,
    Stage,
)

QUEST_ID = "aqm_example_quest"
TAKE_DIALOG_ID = "aqm_example_take"
TURNIN_DIALOG_ID = "aqm_example_turnin"
NPC_ID = "bar_arena_stalker_4_4"
NPC_LOCATION = "bar"
NPC_ALIAS = "bar.bar_arena_stalker_4_4"
TAKEN_INFO = "aqm_example_taken"


def build_project() -> ModProject:
    """Создаёт и возвращает валидный демонстрационный проект.

    Returns:
        ModProject: Проект с одним квестом и двумя диалогами.
    """
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        giver_npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[TAKE_DIALOG_ID, TURNIN_DIALOG_ID],
        title_ru="Первый квест AQM",
        title_en="AQM first quest",
        descr_ru="Дойдите до южной заставы и вернитесь к заказчику.",
        descr_en="Reach the southern checkpoint and return to the customer.",
        taken_info=TAKEN_INFO,
        return_to_giver_stage=1,
        stages={
            0: Stage(
                id=0,
                title_ru="Дойти до южной заставы",
                title_en="Reach the southern checkpoint",
                descr_ru="Южная застава находится на локации Бар.",
                descr_en="The southern checkpoint is located in the Bar area.",
                target_alias="bar.yuzhnaya_zastava",
            ),
            1: Stage(
                id=1,
                title_ru="Вернуться к заказчику",
                title_en="Return to the customer",
                descr_ru="Расскажите заказчику о выполнении.",
                descr_en="Report back to the customer.",
                target_alias=NPC_ALIAS,
            ),
        },
        transfer_conditions={
            0: {"complete": [HasInfo(info=TAKEN_INFO)]},
        },
    )

    take_dialog = Dialog(
        id=TAKE_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="take",
        preconditions=[DontHasInfo(info=TAKEN_INFO)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Есть работа?",
                text_en="Got any work?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Сходи на южную заставу и доложи.",
                text_en="Go to the southern checkpoint and report back.",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Берусь.",
                text_en="I am in.",
                actions=[GiveTask(task_id=QUEST_ID)],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Не подведи.",
                text_en="Do not let me down.",
            ),
            4: Phrase(
                id=4,
                text_ru="Не сейчас.",
                text_en="Not now.",
            ),
        },
    )

    turnin_dialog = Dialog(
        id=TURNIN_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turnin",
        phrases={
            0: Phrase(
                id=0,
                text_ru="Я вернулся с заставы.",
                text_en="I am back from the checkpoint.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Докладывай.",
                text_en="Report.",
                next_phrases=[2],
            ),
            2: Phrase(
                id=2,
                text_ru="Всё чисто.",
                text_en="All clear.",
                actions=[CompleteTask(task_id=QUEST_ID)],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Хорошая работа.",
                text_en="Good work.",
            ),
        },
    )

    return ModProject(
        name="AQM Example Quest",
        mod_slug="aqm_example",
        required_mods=[],
        quests={quest.id: quest},
        dialogs={
            take_dialog.id: take_dialog,
            turnin_dialog.id: turnin_dialog,
        },
    )
