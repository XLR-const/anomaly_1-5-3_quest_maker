"""
Скрипт квеста story_08.py для S.T.A.L.K.E.R. Anomaly 1.5.3.
Демонстрирует сложный 3-этапный детективный квест с несколькими NPC и локациями.

Логика ID и Сценарий:
- Локации: escape (Кордон), garbage (Свалка).
- Квестодатель: Волк (esc_2_12_stalker_wolf, esc_smart_terrain_2_12).
- Свидетель (Этап 1): Бродяга (esc_2_12_stalker_rookie, тот же смарт). Выдает поршень улики.
- Подозреваемый (Этап 2): Наемник на Свалке (garb_smart_terrain_1_6, NPC garb_bandit_boss_sultan - используем как пример "подозреваемого" в другой локации).
- Предмет-улика: itm_pda_common (используется как физическое подтверждение для диалога).
- Этапы:
  1. Поговорить со свидетелем -> Получаем поршень INFO_WITNESS_TALKED.
  2. Найти подозреваемого на Свалке -> Проверка поршня -> Получаем предмет (ПДА) или просто инфопоршень INFO_SUSPECT_CONFRONTED. Для наглядности используем SpawnNpcItem у подозреваемого, чтобы игрок его "забрал" (лут) или просто диалоговый обмен. Пусть будет диалоговый обмен с выдачей предмета игроку через GiveItem для проверки на этапе 3.
  3. Вернуться к Волку. Выбор: сдать (получить деньги) или покрыть (получить оружие/меньше денег).

Примечание: Так как это Story Mode, мы не используем WarfareCapture.
"""
from __future__ import annotations

from pathlib import Path
from aqm.compiler.builder import ModBuilder
from aqm.core.models import (
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
MOD_SLUG = "story_08"
PROJECT_NAME = "Story 08: The Detective"

# NPC и Локации
NPC_WOLF_ID = "esc_2_12_stalker_wolf"
NPC_WOLF_LOC = "escape"
SMART_WOLF = "esc_smart_terrain_2_12"

NPC_WITNESS_ID = "esc_2_12_stalker_rookie"  # Используем существующего сталкера на базе Волка как свидетеля
NPC_WITNESS_LOC = "escape"

NPC_SUSPECT_ID = "garb_bandit_boss_sultan"  # Султан на Свалке как "подозреваемый"
NPC_SUSPECT_LOC = "garbage"
SMART_SUSPECT = "garb_smart_terrain_1_6"

# Предметы
EVIDENCE_ITEM = "itm_pda_common"  # Улика
REWARD_MONEY_HIGH = 10000
REWARD_MONEY_LOW = 2000
REWARD_WEAPON = "wpn_ak74"

# Квест
QUEST_ID = f"{MOD_SLUG}_detective"
DIALOG_WOLF_TAKE = f"{MOD_SLUG}_wolf_take"
DIALOG_WITNESS = f"{MOD_SLUG}_witness_talk"
DIALOG_SUSPECT = f"{MOD_SLUG}_suspect_talk"
DIALOG_WOLF_TURNIN = f"{MOD_SLUG}_wolf_turnin"

# Инфопоршни
INFO_STARTED = f"{MOD_SLUG}_started"
INFO_WITNESS_TALKED = f"{MOD_SLUG}_witness_talked"
INFO_SUSPECT_CONFRONTED = f"{MOD_SLUG}_suspect_confronted"
INFO_DONE_GOOD = f"{MOD_SLUG}_done_good"   # Сдал преступника
INFO_DONE_BAD = f"{MOD_SLUG}_done_bad"     # Покрыл преступника


def create_project() -> ModProject:
    """Создаёт проект детективного квеста."""

    # 1. Квест
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_WOLF_ID,
        npc_location=NPC_WOLF_LOC,
        dialog_id=DIALOG_WOLF_TAKE,
        dialog_ids=[DIALOG_WOLF_TAKE, DIALOG_WITNESS, DIALOG_SUSPECT, DIALOG_WOLF_TURNIN],
        title_ru="Тайна пропавшего тайника",
        title_en="The Missing Stash Mystery",
        descr_ru="Волк просит разобраться, кто украл его заначку.",
        descr_en="Wolf asks you to find out who stole his stash.",
        is_storyline=True,
        taken_info=INFO_STARTED,
        complete_info=None, # Завершение происходит через диалог выбора
        cleanup_infos=[INFO_WITNESS_TALKED, INFO_SUSPECT_CONFRONTED],
        stages={
            0: Stage(
                id=0,
                title_ru="Опросить свидетеля",
                title_en="Question the witness",
                descr_ru="Поговори с Бродягой на базе Волка.",
                descr_en="Talk to Rookie at Wolf's base.",
                target_alias=SMART_WOLF,
            ),
            1: Stage(
                id=1,
                title_ru="Найти подозреваемого",
                title_en="Find the suspect",
                descr_ru="Отправляйся на Свалку и поговори с Султаном.",
                descr_en="Go to the Garbage and talk to Sultan.",
                target_alias=SMART_SUSPECT,
            ),
            2: Stage(
                id=2,
                title_ru="Вернуться к Волку",
                title_en="Return to Wolf",
                descr_ru="Реши, что делать с информацией.",
                descr_en="Decide what to do with the information.",
                target_alias=SMART_WOLF,
            ),
        },
        # Переходы между этапами
        transfer_conditions={
            0: {"complete": [HasInfo(info=INFO_WITNESS_TALKED)]},
            1: {"complete": [HasInfo(info=INFO_SUSPECT_CONFRONTED)]},
        },
    )

    # 2. Диалог взятия у Волка
    dialog_wolf_take = Dialog(
        id=DIALOG_WOLF_TAKE,
        npc_id=NPC_WOLF_ID,
        npc_location=NPC_WOLF_LOC,
        task_id=QUEST_ID,
        role="take",
        preconditions=[DontHasInfo(info=INFO_STARTED)],
        phrases={
            0: Phrase(id=0, text_ru="Волк, есть проблемы?", text_en="Wolf, got problems?", next_phrases=[1]),
            1: Phrase(id=1, text_ru="Кто-то рылся в моих вещах. Спроси у Бродяги, он видел подозрительного типа.", text_en="Someone dug in my stuff. Ask Rookie, he saw a suspicious guy.", next_phrases=[2, 4]),
            2: Phrase(id=2, text_ru="Я займусь этим.", text_en="I'll handle it.", actions=[GiveInfo(info=INFO_STARTED), GiveTask(task_id=QUEST_ID)], next_phrases=[3]),
            3: Phrase(id=3, text_ru="Удачи.", text_en="Good luck."),
            4: Phrase(id=4, text_ru="Не мое дело.", text_en="Not my business."),
        },
    )

    # 3. Диалог со свидетелем (Бродяга)
    dialog_witness = Dialog(
        id=DIALOG_WITNESS,
        npc_id=NPC_WITNESS_ID,
        npc_location=NPC_WITNESS_LOC,
        task_id=QUEST_ID,
        role="branch", # Нейтральная роль, просто ветка сюжета
        preconditions=[HasInfo(info=INFO_STARTED), DontHasInfo(info=INFO_WITNESS_TALKED)],
        phrases={
            0: Phrase(id=0, text_ru="Ты от Волка? Я кое-что видел.", text_en="From Wolf? I saw something.", next_phrases=[1]),
            1: Phrase(id=1, text_ru="Рассказывай.", text_en="Tell me.", next_phrases=[2]),
            2: Phrase(id=2, text_ru="Там был наемник с Свалки. Держи записку с его приметами.", text_en="It was a merc from Garbage. Here's a note with his description.", actions=[GiveInfo(info=INFO_WITNESS_TALKED)], next_phrases=[3]),
            3: Phrase(id=3, text_ru="Спасибо.", text_en="Thanks."),
        },
    )

    # 4. Диалог с подозреваемым (Султан)
    # Игрок должен иметь поршень от свидетеля, чтобы начать этот диалог по квесту
    dialog_suspect = Dialog(
        id=DIALOG_SUSPECT,
        npc_id=NPC_SUSPECT_ID,
        npc_location=NPC_SUSPECT_LOC,
        task_id=QUEST_ID,
        role="branch",
        preconditions=[HasInfo(info=INFO_WITNESS_TALKED), DontHasInfo(info=INFO_SUSPECT_CONFRONTED)],
        phrases={
            0: Phrase(id=0, text_ru="Я знаю, зачем ты пришел. Ты про ту заначку?", text_en="I know why you're here. About that stash?", next_phrases=[1]),
            1: Phrase(id=1, text_ru="Давай без глупостей. Где она?", text_en="No nonsense. Where is it?", next_phrases=[2, 4]),
            2: Phrase(id=2, text_ru="Ладно, ладно. Вот, забери. Только не говори Волку, что это я.", text_en="Okay, okay. Here, take it. Just don't tell Wolf it was me.", actions=[GiveItem(item_alias=EVIDENCE_ITEM, count=1), GiveInfo(info=INFO_SUSPECT_CONFRONTED)], next_phrases=[3]),
            3: Phrase(id=3, text_ru="Посмотрим.", text_en="We'll see."),
            4: Phrase(id=4, text_ru="Мне не до тебя сейчас.", text_en="Not now."),
        },
    )

    # 5. Диалог сдачи Волку (Выбор награды)
    dialog_wolf_turnin = Dialog(
        id=DIALOG_WOLF_TURNIN,
        npc_id=NPC_WOLF_ID,
        npc_location=NPC_WOLF_LOC,
        task_id=QUEST_ID,
        role="turnin",
        preconditions=[HasInfo(info=INFO_SUSPECT_CONFRONTED)],
        phrases={
            0: Phrase(id=0, text_ru="Я нашел виновного.", text_en="I found the culprit.", next_phrases=[1]),
            1: Phrase(id=1, text_ru="И кто это? Говори всё как есть.", text_en="Who is it? Tell me everything.", next_phrases=[2, 4]),
            
            # Ветка 1: Сдать (Честный путь)
            2: Phrase(id=2, text_ru="Это был Султан. Вот его ПДА.", text_en="It was Sultan. Here's his PDA.", preconditions=[HasItem(item_alias=EVIDENCE_ITEM)], actions=[RemoveItem(item_alias=EVIDENCE_ITEM, count=1), GiveMoney(amount=REWARD_MONEY_HIGH), GiveInfo(info=INFO_DONE_GOOD), CompleteTask(task_id=QUEST_ID)], next_phrases=[3]),
            3: Phrase(id=3, text_ru="Хорошая работа. Деньги твои.", text_en="Good job. Money is yours."),
            
            # Ветка 2: Покрыть (Путь хитрости/корысти)
            4: Phrase(id=4, text_ru="Я не нашел ничего конкретного. Но вот... 'случайно' найденный ствол.", text_en="I didn't find anything concrete. But here's a 'randomly' found gun.", actions=[GiveItem(item_alias=REWARD_WEAPON, count=1), GiveMoney(amount=REWARD_MONEY_LOW), GiveInfo(info=INFO_DONE_BAD), CompleteTask(task_id=QUEST_ID)], next_phrases=[5]),
            5: Phrase(id=5, text_ru="Ну ладно. И на этом спасибо.", text_en="Well, okay. Thanks for that too."),
        },
    )

    return ModProject(
        name=PROJECT_NAME,
        mod_slug=MOD_SLUG,
        quests={QUEST_ID: quest},
        dialogs={
            DIALOG_WOLF_TAKE: dialog_wolf_take,
            DIALOG_WITNESS: dialog_witness,
            DIALOG_SUSPECT: dialog_suspect,
            DIALOG_WOLF_TURNIN: dialog_wolf_turnin,
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