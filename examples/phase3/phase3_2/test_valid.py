"""Merc Courier Hunt — Story Mode quest for S.T.A.L.K.E.R. Anomaly 1.5.3.

Declarative mod generated strictly against API_v2.md.
Two stages:
  0 — kill the bandit squad at cit_kanaliz1 and take the PDA from the commander.
  1 — return to Dushman in Dead City with the PDA and turn it in.

Build: python this_file.py
"""

from pathlib import Path

from src.compiler.builder import ModBuilder
from src.core.models import (
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
    SpawnNpcItem,
    SpawnSquad,
    Stage,
)

# ---------------------------------------------------------------------------
# Identifiers (all valid Lua identifiers, unique within the project)
# ---------------------------------------------------------------------------

MOD = "merc_courier_hunt"

QUEST_ID = "merc_courier_hunt_quest"

SQUAD_ID = "merc_courier_hunt_bandit_squad"

INFO_TAKEN = "merc_courier_hunt_taken"
INFO_DONE = "merc_courier_hunt_done"
INFO_SQUAD_DEAD = "merc_courier_hunt_squad_dead"
INFO_PDA_READY = "merc_courier_hunt_pda_ready"

DIALOG_TAKE = "merc_courier_hunt_take"
DIALOG_TURNIN = "merc_courier_hunt_turnin"

NPC_ID = "cit_killers_merc_trader_stalker"
NPC_LOCATION = "deadcity"
SPAWN_SMART = "cit_kanaliz1"

PDA_SECTION = "itm_pda_common"


# ---------------------------------------------------------------------------
# Project construction
# ---------------------------------------------------------------------------

def create_project() -> ModProject:
    """Build the declarative ModProject for the Merc Courier Hunt quest."""

    # --- Stage 0: hostile bandit squad + PDA on commander ----------------
    stage0 = Stage(
        id=0,
        title_ru="Ликвидировать отряд и забрать КПК",
        title_en="Eliminate the squad and take the PDA",
        descr_ru=(
            "Отряд бандитов засел в канализации. Уничтожьте их и заберите "
            "КПК у командира отряда."
        ),
        descr_en=(
            "A bandit squad has holed up in the sewers. Eliminate them and "
            "take the PDA from the squad commander."
        ),
        target_alias=SPAWN_SMART,
        target_squad_id=SQUAD_ID,
    )

    # --- Stage 1: return to Dushman with the PDA --------------------------
    stage1 = Stage(
        id=1,
        title_ru="Вернуться к Душману с КПК",
        title_en="Return to Dushman with the PDA",
        descr_ru="Вернитесь в Мёртвый Город и отдайте КПК Душману.",
        descr_en="Return to Dead City and hand the PDA to Dushman.",
        target_alias="",
    )

    # --- Quest -----------------------------------------------------------
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=DIALOG_TAKE,
        dialog_ids=[DIALOG_TAKE, DIALOG_TURNIN],
        title_ru="Курьер наёмников",
        title_en="Merc Courier Hunt",
        descr_ru=(
            "Душман поручил найти курьера бандитов в канализации и "
            "доставить его КПК."
        ),
        descr_en=(
            "Dushman wants you to find the bandit courier in the sewers "
            "and bring back his PDA."
        ),
        is_storyline=True,
        stages={0: stage0, 1: stage1},
        # Spawn the story squad on quest start (story mode: no set_target,
        # no stay_time, no force_online).
        on_init_actions=[
            SpawnSquad(
                squad_alias=SQUAD_ID,
                smart_alias=SPAWN_SMART,
                mode="story",
            ),
        ],
        # Clean up the squad and the PDA if the quest fails / is cancelled.
        on_fail_actions=[
            RemoveSquad(squad_alias=SQUAD_ID),
            RemoveItem(item_alias=PDA_SECTION, count=1),
        ],
        # Stage progression:
        #   0 -> 1 when the player has the PDA OR the squad is dead.
        #   1 -> complete is handled by the turn-in dialog (CompleteTask).
        transfer_conditions={
            0: {
                "complete": [
                    HasItem(item_alias=PDA_SECTION),
                ],
            },
        },
        # Belt-and-braces: if the squad dies without the player taking the
        # PDA, the quest still advances (the PDA is spawned on the
        # commander, so a dead commander means the player can loot it).
        extra_condlists=[
            QuestCondlist(
                when=[HasInfo(info=INFO_SQUAD_DEAD)],
                result="complete",
            ),
        ],
        # Reward: money AND weapon, issued by Quest.reward_* in _reward.
        reward_money=5000,
        reward_item_alias="wpn_ak74",
        reward_item_count=1,
        complete_info=INFO_DONE,
        taken_info=INFO_TAKEN,
        cleanup_infos=[INFO_SQUAD_DEAD, INFO_PDA_READY],
        fail_on_giver_death=True,
        requires_warfare=False,
    )

    # --- Take dialog -----------------------------------------------------
    take_dialog = Dialog(
        id=DIALOG_TAKE,
        npc_alias="deadcity.dushman",
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="take",
        preconditions=[DontHasInfo(info=INFO_TAKEN)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Душман, есть работёнка?",
                text_en="Dushman, got any work?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru=(
                    "Есть. Один курьер бандитов засел в канализации. "
                    "Нужен его КПК. Возьмёшься?"
                ),
                text_en=(
                    "There is. A bandit courier is holed up in the sewers. "
                    "I need his PDA. Will you take it?"
                ),
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Берусь.",
                text_en="I'm in.",
                actions=[
                    GiveInfo(info=INFO_TAKEN),
                    GiveTask(task_id=QUEST_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Не подведи. КПК должен быть у меня.",
                text_en="Don't let me down. I want that PDA.",
            ),
            4: Phrase(
                id=4,
                text_ru="Не сейчас.",
                text_en="Not now.",
            ),
        },
    )

    # --- Turn-in dialog --------------------------------------------------
    turnin_dialog = Dialog(
        id=DIALOG_TURNIN,
        npc_alias="deadcity.dushman",
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turnin",
        preconditions=[HasInfo(info=INFO_TAKEN)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Душман, вот КПК курьера.",
                text_en="Dushman, here is the courier's PDA.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Отлично. Держи свою награду.",
                text_en="Good work. Here is your reward.",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Забирай.",
                text_en="Take it.",
                preconditions=[
                    HasItem(item_alias=PDA_SECTION, count=1),
                ],
                actions=[
                    GiveInfo(info=INFO_DONE),
                    RemoveItem(item_alias=PDA_SECTION, count=1),
                    GiveMoney(amount=5000),
                    GiveItem(item_alias="wpn_ak74", count=1),
                    CompleteTask(task_id=QUEST_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Если понадобишься — позову.",
                text_en="I'll call you if I need you.",
            ),
            4: Phrase(
                id=4,
                text_ru="Ещё не готов.",
                text_en="Not ready yet.",
            ),
        },
    )

    # --- Custom squad section for the bandit ambush ----------------------
    bandit_squad = CustomSquad(
        id=SQUAD_ID,
        faction="bandit",
        npc=["sim_default_bandit_1", "sim_default_bandit_2"],
        npc_in_squad=[2, 3],
        target_smart=SPAWN_SMART,
        relationship="enemy",
        story_id=SQUAD_ID,
        death_infos=[INFO_SQUAD_DEAD],
    )

    return ModProject(
        name="Merc Courier Hunt",
        required_mods=[],
        quests={QUEST_ID: quest},
        dialogs={
            DIALOG_TAKE: take_dialog,
            DIALOG_TURNIN: turnin_dialog,
        },
        squads={SQUAD_ID: bandit_squad},
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    project = create_project()
    builder = ModBuilder(
        output_dir=Path("output"),
        vanilla_root=Path("_unpacked"),
    )
    if not builder.build_project(project):
        raise SystemExit("Сборка не удалась: смотрите logs/app.log.")
    print(f"Готовый мод: {builder.output_dir}")