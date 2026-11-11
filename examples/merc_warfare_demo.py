"""Сквозной сценарий: кампания против наёмников на Болоте."""

import sys
from pathlib import Path

# ВАЖНО: sys.path ДО всех импортов из src.*
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compiler.builder import ModBuilder, _slugify
from src.core.models import (
    CompleteTask,
    Dialog,
    DontHasInfo,
    GiveTask,
    HasInfo,
    ModProject,
    Phrase,
    Quest,
    Stage,
    WarfareCapture,
)
from src.core.validator import ProjectValidator
from src.db.repository import GameDatabase

PROJECT_NAME = "Merc Hunt Campaign"
QUEST_ID = "mymod_merc_hunt"
ZHUROV_ID = "esc_3_16_military_trader"
ZHUROV_ALIAS = "esc.mayor_zhurov"

TAKEN_INFO = "mymod_merc_taken"
DONE_INFO = "mymod_merc_done"


def build_project() -> ModProject:
    quest = Quest(
        id=QUEST_ID,
        npc_id=ZHUROV_ID,
        giver_npc_id=ZHUROV_ID,
        npc_location="escape",
        dialog_id="mymod_merc_hunt_take",
        dialog_ids=["mymod_merc_hunt_turnin"],
        title_ru="Охота на наёмников",
        title_en="Merc Hunt",
        descr_ru="Зачистите базу на Болоте.",
        descr_en="Clear the Swamps base.",
        taken_info=TAKEN_INFO,
        complete_info=DONE_INFO,
        reward_money=25000,
        reward_item_alias="weapon.vssk_vykhlop",
        return_to_giver_stage=1,
        stages={
            0: Stage(
                id=0,
                title_ru="Зачистить",
                title_en="Clear",
                descr_ru="Убейте наёмников на Болоте.",
                descr_en="Kill mercs in the Swamps.",
                target_alias="marsh.hidden_merc_base",
                warfare_capture=WarfareCapture(
                    smart_alias="marsh.hidden_merc_base",
                    enemy_squad_alias="merc_sim_squad_advanced",
                    ally_squad_alias="army_sim_squad_advanced",
                    ally_count=1,
                ),
            ),
            1: Stage(
                id=1,
                title_ru="Вернуться к Журову",
                title_en="Return to Zhurov",
                descr_ru="Вернитесь к майору на Южный блокпост.",
                descr_en="Return to the Major at the Southern checkpoint.",
                target_alias=ZHUROV_ALIAS,
            ),
        },
    )

    dlg_take = Dialog(
        id="mymod_merc_hunt_take",
        npc_alias=ZHUROV_ALIAS,
        npc_id=ZHUROV_ID,
        npc_location="escape",
        task_id=QUEST_ID,
        role="take",
        preconditions=[
            DontHasInfo(info=TAKEN_INFO),
            DontHasInfo(info=DONE_INFO),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Есть работа, майор?",
                text_en="Got any work, Major?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="На Болоте наёмники обосновались. Возьмёшься?",
                text_en="Mercs have set up in the Swamps. Will you take it?",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Возьму. Выдвигаюсь.",
                text_en="I'll take it. Moving out.",
                actions=[GiveTask(task_id=QUEST_ID)],
            ),
            4: Phrase(
                id=4,
                text_ru="Не сейчас, майор.",
                text_en="Not now, Major.",
            ),
        },
    )

    dlg_turnin = Dialog(
        id="mymod_merc_hunt_turnin",
        npc_alias=ZHUROV_ALIAS,
        npc_id=ZHUROV_ID,
        npc_location="escape",
        task_id=QUEST_ID,
        role="turnin",
        preconditions=[
            HasInfo(info=TAKEN_INFO),
            DontHasInfo(info=DONE_INFO),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Наёмники на Болоте уничтожены, майор.",
                text_en="The mercs in the Swamps are destroyed, Major.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Отличная работа. Вот награда.",
                text_en="Excellent work. Here is your reward.",
                actions=[CompleteTask(task_id=QUEST_ID)],
            ),
        },
    )

    return ModProject(
        name=PROJECT_NAME,
        quests={quest.id: quest},
        dialogs={
            dlg_take.id: dlg_take,
            dlg_turnin.id: dlg_turnin,
        },
    )


def main() -> None:
    project = build_project()
    db_path = PROJECT_ROOT / "data" / "anomaly_db.sqlite"

    with GameDatabase(db_path) as db:
        if not ProjectValidator(db).validate_project(project):
            raise SystemExit("Ошибка валидации проекта.")
        builder = ModBuilder(
            output_dir=PROJECT_ROOT / "output",
            db_client=db,
        )
        if not builder.build_project(project):
            raise SystemExit("Ошибка сборки мода.")

    out_dir = builder.output_dir / _slugify(project.name)
    print(f"\nМод собран: {out_dir.resolve()}")
    print("\nУстановка:")
    print("1. Скопировать gamedata в игру.")
    print("2. system.ltx и character_desc_escape.xml уже пропатчены в сборке.")
    print("3. Новая игра. Поговорить с майором Журовым.")


if __name__ == "__main__":
    main()