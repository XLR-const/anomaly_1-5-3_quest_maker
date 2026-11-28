"""Демо Фазы 3.5: квестодатель-ветеран и мирный отряд Свободы.

Проект ``custom_npc_test``:

* ``CustomNpc``-квестодатель «Связной Сидоровича» с шаблоном, рангом
  ``veteran``, бесконечными деньгами и автоспавном на смарте;
* мирный ``CustomSquad`` Свободы во главе с именным ``CustomNpc``-командиром
  (первый элемент ``npc`` — лидер отряда);
* этап 0: отряд Свободы занимает АТП, игрок забирает у командира КПК;
* этап 1: маркер ведёт на Связного, который забирает КПК и закрывает квест.

Запуск из корня проекта::

    venv\\Scripts\\python.exe examples\\phase3\\phase3_5\\test_custom_npc.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from aqm.compiler.builder import ModBuilder
from aqm.core.models import (
    ClearSmart,
    CompleteTask,
    CustomNpc,
    CustomSquad,
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveItem,
    GiveTask,
    HasInfo,
    HasItem,
    ModProject,
    Phrase,
    Quest,
    RemoveItem,
    SpawnSquad,
    Stage,
    TargetVariant,
)
from aqm.db.repository import GameDatabase

MOD_SLUG = "custom_npc_test"
PROJECT_NAME = "Custom NPC Test"

NPC_ID = "custom_npc_test_envoy"
LEADER_ID = "custom_npc_test_freedom_leader"
QUEST_ID = "custom_npc_test_pda_delivery"
TAKE_DIALOG_ID = "custom_npc_test_take"
FREEDOM_DIALOG_ID = "custom_npc_test_freedom_pda"
TURNIN_DIALOG_ID = "custom_npc_test_turnin"

SQUAD_ID = "custom_npc_test_freedom_squad"

GIVER_SMART = "esc_smart_terrain_2_12"
ATP_SMART = "esc_smart_terrain_7_11"
QUEST_ITEM = "itm_pda_common"

START_INFO = "custom_npc_test_started"
PDA_INFO = "custom_npc_test_pda_received"
DONE_INFO = "custom_npc_test_done"


def create_project() -> ModProject:
    """Создаёт демонстрационный проект с отрядом Свободы и КПК.

    Returns:
        ModProject: Проект, готовый к валидации и сборке.
    """
    envoy = CustomNpc(
        id=NPC_ID,
        faction="stalker",
        template_npc_id="esc_2_12_stalker_wolf",
        immortal=True,
        spec_rank="veteran",
        money_infinitive=True,
        story_id=NPC_ID,
        spawn_smart=GIVER_SMART,
        name_ru="Связной Сидоровича",
        name_en="Sidorovich's Envoy",
        actor_dialogs=[TAKE_DIALOG_ID, TURNIN_DIALOG_ID],
    )

    leader = CustomNpc(
        id=LEADER_ID,
        faction="freedom",
        template_npc_id="esc_2_12_stalker_wolf",
        spec_rank="master",
        story_id=LEADER_ID,
        spawn_smart=None,
        name_ru="Командир разведгруппы Свободы",
        name_en="Freedom Recon Leader",
        actor_dialogs=[FREEDOM_DIALOG_ID],
    )

    squad = CustomSquad(
        id=SQUAD_ID,
        faction="freedom",
        # Первый элемент — командир отряда; к нему привязан диалог выдачи КПК.
        npc=[LEADER_ID, "sim_default_freedom_1", "sim_default_freedom_2"],
        npc_in_squad=[3, 3],
        target_smart=ATP_SMART,
        relationship="neutral",
        story_id=SQUAD_ID,
    )

    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        giver_npc_id=NPC_ID,
        npc_location="escape",
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[TAKE_DIALOG_ID, FREEDOM_DIALOG_ID, TURNIN_DIALOG_ID],
        title_ru="КПК разведгруппы Свободы",
        title_en="Freedom Recon PDA",
        descr_ru=(
            "Связной Сидоровича просит забрать КПК у разведгруппы Свободы "
            "на АТП и вернуться с ним."
        ),
        descr_en=(
            "Sidorovich's envoy wants you to take a PDA from the Freedom "
            "recon squad at the ATP and bring it back."
        ),
        is_storyline=True,
        icon="ui_inGame2_Put_v_pripyat",
        prior=60,
        reward_money=5000,
        cleanup_infos=[START_INFO, PDA_INFO, DONE_INFO],
        on_fail_actions=[
            RemoveItem(item_alias=QUEST_ITEM, count=1),
        ],
        stages={
            0: Stage(
                id=0,
                title_ru="Найти разведгруппу Свободы",
                title_en="Find the Freedom recon squad",
                descr_ru="Подойдите к командиру Свободы на АТП и заберите КПК.",
                descr_en="Approach the Freedom leader at the ATP and take the PDA.",
                target_squad_id=SQUAD_ID,
                target_variants=[
                    TargetVariant(
                        when=[HasInfo(info=PDA_INFO)],
                        value=NPC_ID,
                    )
                ],
                on_start_actions=[
                    ClearSmart(
                        smart_alias=ATP_SMART,
                        faction="bandit",
                        keep_story_ids=[SQUAD_ID],
                        allow_giver_smart=True,
                    ),
                    SpawnSquad(
                        squad_alias=SQUAD_ID,
                        smart_alias=ATP_SMART,
                        mode="story",
                    ),
                ],
            ),
            1: Stage(
                id=1,
                title_ru="Вернуться к Связному",
                title_en="Return to the envoy",
                descr_ru="Отдайте КПК Связному Сидоровича.",
                descr_en="Give the PDA to Sidorovich's envoy.",
                target_alias=NPC_ID,
            ),
        },
        transfer_conditions={
            0: {"complete": [HasInfo(info=PDA_INFO)]},
        },
    )

    take_dialog = Dialog(
        id=TAKE_DIALOG_ID,
        dialog_id=TAKE_DIALOG_ID,
        npc_id=NPC_ID,
        npc_location="escape",
        task_id=QUEST_ID,
        role="take",
        preconditions=[DontHasInfo(info=START_INFO)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Сидорович говорил, тебе нужна помощь?",
                text_en="Sidorovich said you need help?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru=(
                    "На АТП стоит разведгруппа Свободы. Забери у их командира "
                    "КПК и принеси мне."
                ),
                text_en=(
                    "A Freedom recon squad is at the ATP. Take the PDA from "
                    "their leader and bring it to me."
                ),
                actions=[
                    GiveInfo(info=START_INFO),
                    GiveTask(task_id=QUEST_ID),
                ],
                next_phrases=[2],
            ),
            2: Phrase(
                id=2,
                text_ru="Сделаю.",
                text_en="I'll do it.",
            ),
        },
    )

    freedom_dialog = Dialog(
        id=FREEDOM_DIALOG_ID,
        dialog_id=FREEDOM_DIALOG_ID,
        npc_id=LEADER_ID,
        npc_location="escape",
        task_id=QUEST_ID,
        preconditions=[
            HasInfo(info=START_INFO),
            DontHasInfo(info=PDA_INFO),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Ты командир разведгруппы? Мне нужен ваш КПК.",
                text_en="Are you the recon leader? I need your PDA.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Забирай. Нам он больше не нужен.",
                text_en="Take it. We don't need it anymore.",
                actions=[
                    GiveItem(item_alias=QUEST_ITEM, count=1),
                    GiveInfo(info=PDA_INFO),
                ],
                next_phrases=[2],
            ),
            2: Phrase(
                id=2,
                text_ru="Спасибо.",
                text_en="Thanks.",
            ),
        },
    )

    turnin_dialog = Dialog(
        id=TURNIN_DIALOG_ID,
        dialog_id=TURNIN_DIALOG_ID,
        npc_id=NPC_ID,
        npc_location="escape",
        task_id=QUEST_ID,
        role="turnin",
        preconditions=[
            HasInfo(info=PDA_INFO),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Я принёс КПК свободовцев.",
                text_en="I brought the Freedom PDA.",
                preconditions=[HasItem(item_alias=QUEST_ITEM, count=1)],
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Показывай. Да, это то, что нужно.",
                text_en="Let me see. Yes, that's the one.",
                next_phrases=[2],
            ),
            2: Phrase(
                id=2,
                text_ru="Держи свою награду.",
                text_en="Here's your reward.",
                actions=[
                    RemoveItem(item_alias=QUEST_ITEM, count=1),
                    GiveInfo(info=DONE_INFO),
                    CompleteTask(task_id=QUEST_ID),
                ],
            ),
        },
    )

    return ModProject(
        name=PROJECT_NAME,
        mod_slug=MOD_SLUG,
        npcs={envoy.id: envoy, leader.id: leader},
        squads={squad.id: squad},
        quests={quest.id: quest},
        dialogs={
            take_dialog.id: take_dialog,
            freedom_dialog.id: freedom_dialog,
            turnin_dialog.id: turnin_dialog,
        },
    )


def main() -> None:
    """Собирает демо-мод в ``output/custom_npc_test``."""
    project = create_project()
    with GameDatabase(Path("data/anomaly_db.sqlite")) as db:
        builder = ModBuilder(
            output_dir=Path("output"),
            db_client=db,
            vanilla_root=Path("_unpacked"),
        )
        if not builder.build_project(project):
            raise SystemExit("Сборка не удалась: смотрите logs/app.log.")
    print(f"Мод собран в: {builder.output_dir / MOD_SLUG}")


if __name__ == "__main__":
    main()
