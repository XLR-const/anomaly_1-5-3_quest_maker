"""Сквозной демонстрационный сценарий Warfare-кампании за Военных.

Модуль программно собирает проверенный сюжет на Кордоне:

* первый квест — захват Деревни новичков, переход на Элеватор и доклад
  майору Журову;
* второй квест — зачистка АТП от бандитов, доступная после завершения первого;
* диалог взятия второго квеста с ветвлением «штурм с отрядом» / «соло».

Проект создаётся исключительно через строгие Pydantic-модели
:mod:`src.core.models`. Все строки содержат обязательные русскую и английскую
версии, а карты этапов и реплик используют целочисленные ключи.

Запуск из корня проекта::

    python examples/cordon_warfare_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.models import (  # noqa: E402
    Dialog,
    GiveInfo,
    GiveItem,
    GiveMoney,
    HasInfo,
    ModProject,
    Phrase,
    Quest,
    SpawnSquad,
    Stage,
)
from src.logger import get_logger  # noqa: E402

logger = get_logger("examples.cordon_warfare_demo")

#: Название демонстрационного проекта мода.
PROJECT_NAME = "Cordon Warfare Campaign"

#: Идентификаторы квестов и диалогов сценария.
QUEST_1_ID = "mymod_av_quest"
QUEST_2_ID = "mymod_atp_quest"
DIALOG_ID = "mymod_q2_start_dialog"

#: Инфопоршни, связывающие завершение первого квеста и старт второго.
QUEST_1_DONE_INFO = "mymod_quest_1_done"
QUEST_2_START_INFO = "mymod_atp_quest_started"
QUEST_2_SOLO_INFO = "mymod_atp_quest_solo"

#: Ключевые игровые алиасы сценария.
ZHUROV_ID = "esc_3_16_military_trader"
ZHUROV_ALIAS = "esc.mayor_zhurov"
ROOKIE_VILLAGE_ALIAS = "esc.derevnya_novichkov"
ELEVATOR_ALIAS = "esc.elevator"
ATP_ALIAS = "esc.atp"
ARMY_SQUAD_ALIAS = "squad.army_advanced"


def create_demo_project() -> ModProject:
    """Создаёт полностью заполненный демонстрационный проект Warfare-кампании.

    Функция собирает два сюжетных квеста и один диалог-ветвление у майора
    Журова. Первый квест выдаёт поршень :data:`QUEST_1_DONE_INFO` при
    завершении; этот же поршень является условием доступности диалога взятия
    второго квеста. В диалоге игрок выбирает штурм с отрядом
    ``squad.army_advanced`` или соло-прохождение с отдельным инфопоршнем.

    Returns:
        ModProject: Готовый к сквозной валидации и сборке проект мода с
        двуязычными текстами, непрерывной нумерацией этапов и корректным
        графом реплик.

    Raises:
        pydantic.ValidationError:
            Если собранные данные нарушают инварианты моделей квестов,
            этапов, диалогов или реплик.

    Notes:
        Модели сохраняют неизвестные колонки SQLite (``extra="allow"``),
        поэтому все действия и условия всё равно создаются конкретными
        классами из :mod:`src.core.models`, а не словарями.
    """
    logger.info("Создание демо-проекта '%s'.", PROJECT_NAME)

    quest_1 = Quest(
        id=QUEST_1_ID,
        npc_id=ZHUROV_ID,
        giver_npc_id=ZHUROV_ID,
        npc_location="escape",
        title_ru="Война на Кордоне: кампания за Военных",
        title_en="Cordon Warfare: Army Campaign",
        descr_ru=(
            "Захватите Деревню новичков, выдвиньтесь на Элеватор и "
            "доложите майору Журову о закреплении Военных на Кордоне."
        ),
        descr_en=(
            "Capture the Rookie Village, advance to the Elevator and report "
            "to Major Zhurov about the Army foothold in the Cordon."
        ),
        is_storyline=True,
        stages={
            0: Stage(
                id=0,
                title_ru="Захват Деревни новичков",
                title_en="Capture the Rookie Village",
                descr_ru=(
                    "Захватите Деревню новичков и удерживайте её за "
                    "Военных."
                ),
                descr_en=(
                    "Capture the Rookie Village and hold it for the Army."
                ),
                target_alias=ROOKIE_VILLAGE_ALIAS,
            ),
            1: Stage(
                id=1,
                title_ru="Авто-переход на Элеватор",
                title_en="Advance to the Elevator",
                descr_ru=(
                    "После захвата деревни выдвигайтесь к Элеватору и "
                    "закрепитесь на точке."
                ),
                descr_en=(
                    "After capturing the village, move to the Elevator and "
                    "secure the position."
                ),
                target_alias=ELEVATOR_ALIAS,
            ),
            2: Stage(
                id=2,
                title_ru="Возврат к Журову",
                title_en="Report to Zhurov",
                descr_ru=(
                    "Вернитесь к майору Журову и доложите об успешном "
                    "захвате Кордона."
                ),
                descr_en=(
                    "Return to Major Zhurov and report the successful "
                    "capture of the Cordon."
                ),
                target_alias=ZHUROV_ALIAS,
            ),
        },
        on_complete_actions=[
            GiveMoney(amount=10000),
            GiveItem(item_alias="weapon.vssk_vykhlop"),
            GiveInfo(info=QUEST_1_DONE_INFO),
        ],
    )
    logger.debug(
        "Квест '%s' собран: этапов — %d, наград — %d.",
        quest_1.id,
        len(quest_1.stages),
        len(quest_1.on_complete_actions),
    )

    quest_2 = Quest(
        id=QUEST_2_ID,
        npc_id=ZHUROV_ID,
        giver_npc_id=ZHUROV_ID,
        npc_location="escape",
        dialog_id=DIALOG_ID,
        title_ru="Зачистка АТП",
        title_en="Clear the ATP",
        descr_ru=(
            "Зачистите АТП от бандитов и доложите майору Журову о "
            "выполнении задачи."
        ),
        descr_en=(
            "Clear the ATP of bandits and report the completed task to "
            "Major Zhurov."
        ),
        is_storyline=True,
        stages={
            0: Stage(
                id=0,
                title_ru="Зачистка АТП",
                title_en="Clear the ATP",
                descr_ru=(
                    "Уничтожьте бандитов на территории АТП и удерживайте "
                    "точку."
                ),
                descr_en=(
                    "Eliminate the bandits at the ATP and hold the area."
                ),
                target_alias=ATP_ALIAS,
            ),
            1: Stage(
                id=1,
                title_ru="Сдача Журову",
                title_en="Report to Zhurov",
                descr_ru=(
                    "Вернитесь к майору Журову и доложите о зачистке АТП."
                ),
                descr_en=(
                    "Return to Major Zhurov and report the ATP cleanup."
                ),
                target_alias=ZHUROV_ALIAS,
            ),
        },
    )
    logger.debug(
        "Квест '%s' собран: этапов — %d.",
        quest_2.id,
        len(quest_2.stages),
    )

    start_dialog = Dialog(
        id=DIALOG_ID,
        npc_alias=ZHUROV_ALIAS,
        npc_id=ZHUROV_ID,
        npc_location="escape",
        task_id=QUEST_2_ID,
        role="take",
        preconditions=[HasInfo(info=QUEST_1_DONE_INFO)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Что на этот раз, майор?",
                text_en="What is it this time, Major?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru=(
                    "Нужно зачистить АТП от бандитов. Как пойдешь?"
                ),
                text_en=(
                    "We need to clear the ATP of bandits. How do you want "
                    "to play it?"
                ),
                next_phrases=[2, 3, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Пойду на штурм с ребятами.",
                text_en="I'll go in with the boys.",
                actions=[
                    SpawnSquad(
                        squad_alias=ARMY_SQUAD_ALIAS,
                        smart_alias=ATP_ALIAS,
                    ),
                    GiveInfo(info=QUEST_2_START_INFO),
                ],
            ),
            3: Phrase(
                id=3,
                text_ru="Справлюсь один, но оплата двойная.",
                text_en="I'll handle it alone, but the pay is double.",
                actions=[
                    GiveInfo(info=QUEST_2_START_INFO),
                    GiveInfo(info=QUEST_2_SOLO_INFO),
                ],
            ),
            4: Phrase(
                id=4,
                text_ru="Я пока не готов, подумаю.",
                text_en="I'm not ready yet, let me think.",
            ),
        },
    )
    logger.debug(
        "Диалог '%s' собран: реплик — %d, условий — %d.",
        start_dialog.id,
        len(start_dialog.phrases),
        len(start_dialog.preconditions),
    )

    project = ModProject(
        name=PROJECT_NAME,
        required_mods=[],
        quests={
            quest_1.id: quest_1,
            quest_2.id: quest_2,
        },
        dialogs={
            start_dialog.id: start_dialog,
        },
    )

    logger.info(
        "Демо-проект '%s' готов к сборке: квестов — %d, диалогов — %d.",
        project.name,
        len(project.quests),
        len(project.dialogs),
    )
    return project


if __name__ == "__main__":
    demo_project = create_demo_project()
    print(demo_project.to_yaml())


__all__ = ["create_demo_project"]
