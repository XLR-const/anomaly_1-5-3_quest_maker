from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from examples.build_story_relay import build_project as build_relay_ch1
from aqm.compiler.builder import ModBuilder
from aqm.core.models import (
    ClearSmart,
    CompleteTask,
    CustomSquad,
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveTask,
    HasInfo,
    ModProject,
    Phrase,
    Quest,
    RemoveSquad,
    SpawnSquad,
    Stage,
)
from aqm.validation import MergeValidator, ValidationReport

MERGED_SLUG = "boroda_merged_test"
NPC_ID = "zat_a2_stalker_barmen"
NPC_LOCATION = "zaton"
NPC_ALIAS = "zaton.barman"


def build_chapter_1() -> ModProject:
    """Глава 1: эталонный квест Бороды + ClearSmart на Шевченко (zat_b7)."""
    ch1 = build_relay_ch1()
    ch1.mod_slug = MERGED_SLUG
    ch1.name = "Boroda Merged Story"
    q1 = ch1.quests["mymod_relay_01_silence"]
    q1.on_init_actions = [
        ClearSmart(smart_alias="zat_b7"),
        *q1.on_init_actions,
    ]
    return ch1


def build_chapter_2() -> ModProject:
    """Глава 2: параллельный мини-квест у того же Бороды на Затоне."""
    q3_id = "boroda_merged_test_03_forestry"
    squad_id = "boroda_merged_test_03_bandits"
    info_taken = "boroda_merged_test_03_taken"
    info_dead = "boroda_merged_test_03_dead"
    info_done = "boroda_merged_test_03_done"
    target_smart = "zat_b5_smart_terrain"

    q3 = Quest(
        id=q3_id,
        npc_id=NPC_ID,
        giver_npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id="boroda_merged_test_03_take",
        dialog_ids=["boroda_merged_test_03_take", "boroda_merged_test_03_turnin"],
        title_ru="Зачистка Лесничества",
        title_en="Forestry Sweep",
        descr_ru="Борода просит выбить шайку бандитов, засевшую в Лесничестве.",
        descr_en="Beard asks you to clear out a bandit gang at the Forestry.",
        is_storyline=False,
        prior=50,
        stages={
            0: Stage(
                id=0,
                title_ru="Уничтожить бандитов в Лесничестве",
                title_en="Eliminate bandits at the Forestry",
                descr_ru="Отправляйтесь в Лесничество и ликвидируйте отряд бандитов.",
                descr_en="Head to the Forestry and eliminate the bandit squad.",
                target_squad_id=squad_id,
            ),
            1: Stage(
                id=1,
                title_ru="Доложить Бороде о зачистке",
                title_en="Report back to Beard",
                descr_ru="Бандиты в Лесничестве уничтожены. Вернитесь к Бороде.",
                descr_en="The bandits at the Forestry are dead. Return to Beard.",
                target_alias=NPC_ID,
            ),
        },
        on_init_actions=[
            ClearSmart(smart_alias=target_smart),
            SpawnSquad(squad_alias=squad_id, smart_alias=target_smart, mode="story"),
        ],
        transfer_conditions={
            0: {"complete": [HasInfo(info=info_dead)]},
        },
        taken_info=info_taken,
        complete_info=info_done,
        cleanup_infos=[info_dead],
        on_fail_actions=[RemoveSquad(squad_alias=squad_id)],
        reward_money=4000,
    )

    take_dialog = Dialog(
        id="boroda_merged_test_03_take",
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=q3_id,
        role="take",
        preconditions=[DontHasInfo(info=info_taken)],
        phrases={
            0: Phrase(id=0, text_ru="Борода, насчёт бандитов в Лесничестве — есть дело?", next_phrases=[1]),
            1: Phrase(id=1, text_ru="Да, совсем обнаглели, караваны щупают. Зачистишь точку?", next_phrases=[2, 4]),
            2: Phrase(
                id=2,
                text_ru="Сделаю. Жди с новостями.",
                actions=[GiveInfo(info=info_taken), GiveTask(task_id=q3_id)],
                next_phrases=[3],
            ),
            3: Phrase(id=3, text_ru="Вот и славно. Будь осторожен."),
            4: Phrase(id=4, text_ru="Пока не до этого.", next_phrases=[5]),
            5: Phrase(id=5, text_ru="Дело твоё."),
        },
    )

    turnin_dialog = Dialog(
        id="boroda_merged_test_03_turnin",
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=q3_id,
        role="turnin",
        preconditions=[HasInfo(info=info_dead), DontHasInfo(info=info_done)],
        phrases={
            0: Phrase(id=0, text_ru="Борода, в Лесничестве теперь тихо.", next_phrases=[1]),
            1: Phrase(id=1, text_ru="Отлично сработано! Держи обещанную награду.", next_phrases=[2]),
            2: Phrase(id=2, text_ru="Спасибо, Борода.", actions=[CompleteTask(task_id=q3_id)]),
        },
    )

    return ModProject(
        name="Boroda Chapter 2",
        mod_slug=MERGED_SLUG,
        quests={q3.id: q3},
        dialogs={take_dialog.id: take_dialog, turnin_dialog.id: turnin_dialog},
        squads={
            squad_id: CustomSquad(
                id=squad_id,
                faction="bandit",
                npc=["sim_default_bandit_1", "sim_default_bandit_2", "sim_default_bandit_3"],
                target_smart=target_smart,
                story_id=squad_id,
                death_infos=[info_dead],
                relationship="enemy",
            ),
        },
    )


def main() -> None:
    ch1 = build_chapter_1()
    ch2 = build_chapter_2()

    report = ValidationReport()
    MergeValidator(report).validate_chapters([ch1, ch2], target_slug=MERGED_SLUG)
    print("=== MERGE VALIDATION REPORT ===")
    print(report.to_text())

    merged = ModProject.merge(ch1, ch2, mod_slug=MERGED_SLUG, mod_title="Boroda Merged Story")
    builder = ModBuilder(output_dir=Path("output"), vanilla_root=Path("_unpacked"))
    if not builder.build_project(merged):
        raise SystemExit("Сборка объединённого проекта не удалась.")

    print(f"Успешно собрано в output/{MERGED_SLUG}: квесты = {list(merged.quests.keys())}")


if __name__ == "__main__":
    main()
