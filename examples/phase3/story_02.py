"""
Скрипт квеста story_02.py для S.T.A.L.K.E.R. Anomaly 1.5.3.
Демонстрирует Story-паттерн: спавн отряда с предметом у командира -> изъятие предмета игроком -> сдача.

Логика ID:
- Локация: escape (Кордон).
- NPC: esc_2_12_stalker_wolf (Волк, стандартный квестодатель на Кордоне).
- Отряд: story_02_merc_squad (наёмники, враги).
- Предмет: itm_pda_common (стандартный ПДА, используем как "секретные данные").
- Спавн предмета: SpawnNpcItem кладёт ПДА командиру отряда.
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
    HasItem,
    ModProject,
    Phrase,
    Quest,
    QuestCondlist,
    RemoveItem,
    RemoveSquad,
    SpawnNpcItem,
    SpawnSquad,
    Stage,
)

# ---------------------------------------------------------------------------
# Константы сценария
# ---------------------------------------------------------------------------
MOD_SLUG = "story_02"
PROJECT_NAME = "Story 02: Mercenary Data"

# NPC и локации
NPC_ID = "esc_2_12_stalker_wolf"
NPC_LOCATION = "escape"
SMART_WOLF = "esc_smart_terrain_2_12"
SMART_MERC = "esc_smart_terrain_5_7"  # Смарт наёмников/бандитов на Кордоне (например, АТП или блокпост)

# Отряд и предмет
SQUAD_ID = f"{MOD_SLUG}_merc_squad"
ITEM_ALIAS = "itm_pda_common"
INFO_ITEM_LOOTED = f"{MOD_SLUG}_item_looted" # Поршень, который игрок получает сам, когда находит предмет (опционально, но полезно для логики)

# Квест
QUEST_ID = f"{MOD_SLUG}_retrieve_data"
TAKE_DIALOG_ID = f"{MOD_SLUG}_take"
TURNIN_DIALOG_ID = f"{MOD_SLUG}_turnin"

# Награда
REWARD_MONEY = 10000

# Инфопоршни
INFO_STARTED = f"{MOD_SLUG}_started"
INFO_DONE = f"{MOD_SLUG}_done"


def create_project() -> ModProject:
    """Создаёт проект квеста на поиск данных у наёмников."""

    # 1. Описание кастомного отряда наёмников
    merc_squad = CustomSquad(
        id=SQUAD_ID,
        faction="killer",
        npc=["sim_default_killer_1", "sim_default_killer_2"],
        npc_in_squad=[3, 4],
        target_smart=SMART_MERC,
        relationship="enemy",
        # death_infos не обязателен, если мы проверяем наличие предмета, 
        # но полезен для очистки, если игрок убьёт всех до лута.
        death_infos=[], 
    )

    # 2. Квест
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[TAKE_DIALOG_ID, TURNIN_DIALOG_ID],
        title_ru="Похищенные данные",
        title_en="Stolen Data",
        descr_ru="Наёмники украли важные данные. Найди их лидера и забери ПДА.",
        descr_en="Mercenaries stole important data. Find their leader and retrieve the PDA.",
        is_storyline=True,
        reward_money=REWARD_MONEY,
        complete_info=INFO_DONE,
        taken_info=INFO_STARTED,
        cleanup_infos=[INFO_ITEM_LOOTED], # Очищаем поршень лута при провале
        stages={
            0: Stage(
                id=0,
                title_ru="Найти лидера наёмников",
                title_en="Find the mercenary leader",
                descr_ru="Отряд засел на блокпосту. Убей лидера и забери ПДА.",
                descr_en="The squad is camped at the checkpoint. Kill the leader and take the PDA.",
                target_alias=SMART_MERC,
                on_start_actions=[
                    # Спавним отряд в режиме Story
                    SpawnSquad(
                        squad_alias=SQUAD_ID,
                        smart_alias=SMART_MERC,
                        mode="story",
                    ),
                    # Кладем предмет в инвентарь командира этого отряда
                    SpawnNpcItem(
                        item_alias=ITEM_ALIAS,
                        target_alias=SQUAD_ID, # Резолвится в командира отряда
                        count=1,
                    ),
                ],
            ),
            1: Stage(
                id=1,
                title_ru="Вернуться к Волку",
                title_en="Return to Wolf",
                descr_ru="Принеси ПДА Волку.",
                descr_en="Bring the PDA to Wolf.",
                target_alias=SMART_WOLF,
            ),
        },
        # Переход на этап 1 (сдача) происходит, когда у игрока появляется предмет
        transfer_conditions={
            0: {"complete": [HasItem(item_alias=ITEM_ALIAS, count=1)]},
        },
        # Если квестодатель умрет - провал
        fail_on_giver_death=True,
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
                text_ru="Волк, есть срочное дело?",
                text_en="Wolf, got any urgent work?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Наёмники украли мои данные. Найди их лидера и верни ПДА.",
                text_en="Mercenaries stole my data. Find their leader and return the PDA.",
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
                text_ru="Будь осторожен, они хорошо вооружены.",
                text_en="Be careful, they are well armed.",
            ),
            4: Phrase(
                id=4,
                text_ru="Не сейчас.",
                text_en="Not now.",
            ),
        },
    )

    # 4. Диалог сдачи квеста
    turnin_dialog = Dialog(
        id=TURNIN_DIALOG_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turnin",
        # Доступен, когда квест взят (INFO_STARTED) и игрок вернулся (этап 1)
        # Проверка наличия предмета делается внутри фразы, чтобы не блокировать диалог полностью, если предмет потерян (хотя это редкость)
        preconditions=[HasInfo(info=INFO_STARTED)], 
        phrases={
            0: Phrase(
                id=0,
                text_ru="Я нашел твои данные.",
                text_en="I found your data.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Покажи.",
                text_en="Show me.",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Держи ПДА.",
                text_en="Here's the PDA.",
                # Проверяем наличие предмета перед сдачей
                preconditions=[HasItem(item_alias=ITEM_ALIAS, count=1)],
                actions=[
                    RemoveItem(item_alias=ITEM_ALIAS, count=1),
                    GiveInfo(info=INFO_DONE),
                    # CompleteTask не нужен здесь, так как переход на этап 1 уже произошел по HasItem,
                    # а завершение квеста (выдача награды) произойдет автоматически при достижении финального этапа 
                    # и выборе этой реплики? Нет, в данной архитектуре сдача через диалог требует явного завершения.
                    # Однако, у нас нет return_to_giver_stage. 
                    # В API_v2 сказано: "Если сдача должна идти через диалог... return_to_giver_stage не задавайте."
                    # И "CompleteTask... если действие в реплике единственное...".
                    # Но у нас есть RemoveItem. Значит, нужна единая функция action.
                    # Важно: Квест завершается, когда игрок находится на этапе 1 и выполняет условия сдачи.
                    # В данном примере мы используем стандартный механизм: 
                    # Этап 1 - это "Вернуться". Как только игрок подходит к Волку, квест может завершиться, 
                    # если бы был return_to_giver_stage. Но мы хотим диалог.
                    # Поэтому мы используем CompleteTask в действиях диалога.
                    # Так как действий несколько (RemoveItem + GiveInfo + CompleteTask), они сольются в одну Lua-функцию.
                    GiveInfo(info=INFO_DONE), # Дублируем для надежности, хотя complete_info в Quest тоже сработает в _reward
                    # Примечание: В API_v2 сказано, что награда выдается через Quest.reward_*. 
                    # CompleteTask здесь нужен, чтобы перевести задачу в статус "выполнена" и закрыть её.
                    # Но wait, в API_v2 примерах часто используется просто переход по условию.
                    # Давайте последуем примеру "Dead City Dushman": там CompleteTask есть в диалоге.
                    # Но там также был переход по HasItem на этап 1.
                    # Здесь мы сделаем так: HasItem переводит на этап 1. На этапе 1 игрок идет к Волку.
                    # Диалог сдачи проверяет HasItem и делает CompleteTask.
                    # Это корректно.
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Отличная работа, сталкер. Деньги твои.",
                text_en="Great job, stalker. The money is yours.",
            ),
            4: Phrase(
                id=4,
                text_ru="У меня его нет.",
                text_en="I don't have it.",
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