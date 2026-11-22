"""Phase 3.2: Story-квест с ClearSmart, SpawnSquad и SpawnNpcItem.

Сценарий проверяет штатный порядок действий на этапе 0:

1. ``ClearSmart`` очищает смарт АТП на Кордоне от ванильных отрядов.
2. ``SpawnSquad(mode="story")`` спавнит туда отряд Монолита.
3. ``SpawnNpcItem`` кладёт квестовый КПК командиру этого отряда.

Квестодатель — Волк в Деревне новичков. Смарт Волка
(``esc_smart_terrain_2_12``) намеренно не используется как точка спавна.

Запуск из корня проекта:
    venv\\Scripts\\python.exe -m examples.phase3.phase3_2.test_remove_squad
"""

from __future__ import annotations

from pathlib import Path

from src.compiler.builder import ModBuilder
from src.db.repository import GameDatabase
from src.core.models import (
    ClearSmart,
    CompleteTask,
    CustomSquad,
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveTask,
    HasItem,
    ModProject,
    Phrase,
    Quest,
    RemoveItem,
    RemoveSquad,
    SpawnNpcItem,
    SpawnSquad,
    Stage,
)
from src.validation import validate_project

# ---------------------------------------------------------------------------
# Параметры сценария
# ---------------------------------------------------------------------------

MOD_SLUG = "atp_monolith_clear"
MOD_TITLE = "ATP Monolith Clear Test"

QUEST_ID = "atp_monolith_clear_01_clear_atp"
TAKE_DIALOG_ID = "atp_monolith_clear_01_take"
TURNIN_DIALOG_ID = "atp_monolith_clear_01_turnin"

GIVER_NPC_ID = "esc_2_12_stalker_wolf"
GIVER_LOCATION = "escape"

# Реальный смарт АТП на Кордоне (проверено через main.py search).
ATP_SMART = "esc_smart_terrain_7_11"

# Story-отряд Монолита. story_id обязателен: по нему адресуются
# SpawnNpcItem, RemoveSquad и Stage.target_squad_id.
SQUAD_ID = "atp_monolith_clear_01_monolith_squad"

# Проверенные LTX spawn-секции Монолита из БД (без суффиксов XML-профилей
# _default_N). Именно такие имена ожидает движок X-Ray в squad_descr.
MONOLITH_NPCS = [
    "sim_default_monolith_1",
    "sim_default_monolith_2",
    "sim_default_monolith_3",
]

PDA_ITEM = "itm_pda_common"
REWARD_MONEY = 3500
REWARD_ITEM = "medkit_army"

INFO_STARTED = "atp_monolith_clear_01_started"
INFO_DONE = "atp_monolith_clear_01_done"


# ---------------------------------------------------------------------------
# Модели проекта
# ---------------------------------------------------------------------------


def create_project() -> ModProject:
    """Создаёт Story-проект с ClearSmart и Story-отрядом Монолита.

    Returns:
        ModProject: Проект, готовый к предполётной валидации и сборке.
    """
    quest = Quest(
        id=QUEST_ID,
        npc_id=GIVER_NPC_ID,
        npc_location=GIVER_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[TAKE_DIALOG_ID, TURNIN_DIALOG_ID],
        title_ru="Зачистка АТП",
        title_en="Clear the ATP",
        descr_ru=(
            "Зачистите АТП на Кордоне от отряда Монолита и заберите "
            "их КПК."
        ),
        descr_en=(
            "Clear the ATP in Cordon from the Monolith squad and recover "
            "their PDA."
        ),
        is_storyline=True,
        requires_warfare=False,
        reward_money=REWARD_MONEY,
        reward_item_alias=REWARD_ITEM,
        reward_item_count=1,
        taken_info=INFO_STARTED,
        complete_info=INFO_DONE,
        stages={
            0: Stage(
                id=0,
                title_ru="Зачистить АТП от отряда Монолита и забрать КПК",
                title_en="Clear the ATP from Monolith and take the PDA",
                descr_ru=(
                    "Уничтожьте отряд Монолита на АТП и заберите КПК "
                    "у командира."
                ),
                descr_en=(
                    "Destroy the Monolith squad at the ATP and take the "
                    "PDA from their commander."
                ),
                target_alias=ATP_SMART,
                on_start_actions=[
                    # 1) Сначала очищаем точку от ванильных отрядов
                    # (без faction — все не-сюжетные отряды).
                    # allow_giver_smart=True — явное разрешение линтера;
                    # фактический смарт Волка esc_smart_terrain_2_12,
                    # а не АТП esc_smart_terrain_7_11.
                    ClearSmart(
                        smart_alias=ATP_SMART,
                        allow_giver_smart=True,
                    ),
                    # 2) Затем спавним квестовый Story-отряд.
                    SpawnSquad(
                        squad_alias=SQUAD_ID,
                        smart_alias=ATP_SMART,
                        mode="story",
                    ),
                    # 3) Только после спавна выдаём предмет командиру.
                    SpawnNpcItem(
                        item_alias=PDA_ITEM,
                        target_alias=SQUAD_ID,
                        count=1,
                    ),
                ],
            ),
            1: Stage(
                id=1,
                title_ru="Вернуться к Волку и отдать КПК",
                title_en="Return to Wolf and hand over the PDA",
                descr_ru="Вернитесь в Деревню новичков и отдайте КПК Волку.",
                descr_en="Return to the Rookie Village and give the PDA to Wolf.",
                target_alias="",
            ),
        },
        transfer_conditions={
            0: {"complete": [HasItem(item_alias=PDA_ITEM)]},
        },
        on_fail_actions=[
            RemoveSquad(squad_alias=SQUAD_ID),
            RemoveItem(item_alias=PDA_ITEM, count=1),
        ],
    )

    take_dialog = Dialog(
        id=TAKE_DIALOG_ID,
        npc_alias="escape.wolf",
        npc_id=GIVER_NPC_ID,
        npc_location=GIVER_LOCATION,
        task_id=QUEST_ID,
        role="take",
        preconditions=[DontHasInfo(info=INFO_STARTED)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Волк, на АТП засели монолитовцы. Нужна помощь?",
                text_en="Wolf, Monolith fighters have dug in at the ATP. Need help?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Нужна. Зачисти АТП и принеси их КПК.",
                text_en="I do. Clear the ATP and bring me their PDA.",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Берусь. АТП зачищу.",
                text_en="I'm on it. I'll clear the ATP.",
                actions=[
                    GiveInfo(info=INFO_STARTED),
                    GiveTask(task_id=QUEST_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Не подведи. Там может быть жарко.",
                text_en="Don't let me down. It may get hot there.",
            ),
            4: Phrase(
                id=4,
                text_ru="Не сейчас. Найди кого-нибудь другого.",
                text_en="Not now. Find someone else.",
            ),
        },
    )

    turnin_dialog = Dialog(
        id=TURNIN_DIALOG_ID,
        npc_alias="escape.wolf",
        npc_id=GIVER_NPC_ID,
        npc_location=GIVER_LOCATION,
        task_id=QUEST_ID,
        role="turnin",
        phrases={
            0: Phrase(
                id=0,
                text_ru="Волк, АТП чисто. Вот их КПК.",
                text_en="Wolf, the ATP is clear. Here's their PDA.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Показывай, что там у тебя.",
                text_en="Show me what you've got.",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Держи КПК. Монолитовцы больше не помешают.",
                text_en="Here's the PDA. Monolith won't bother us anymore.",
                preconditions=[HasItem(item_alias=PDA_ITEM)],
                actions=[
                    RemoveItem(item_alias=PDA_ITEM, count=1),
                    CompleteTask(task_id=QUEST_ID),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Хорошая работа. Держи награду.",
                text_en="Good work. Here's your reward.",
            ),
            4: Phrase(
                id=4,
                text_ru="Ещё не закончил. КПК у меня.",
                text_en="Not finished yet. I still have the PDA.",
            ),
        },
    )

    squad = CustomSquad(
        id=SQUAD_ID,
        faction="monolith",
        npc=MONOLITH_NPCS,
        npc_in_squad=[3, 3],
        relationship="enemy",
        # target_smart совпадает с точкой спавна: отряд должен закрепиться
        # на АТП, а не уйти маршем на другой смарт.
        target_smart=ATP_SMART,
        story_id=SQUAD_ID,
    )

    return ModProject(
        # Builder выводит slug из name; mod_title остаётся требуемым
        # отображаемым названием проекта.
        name="ATP Monolith Clear",
        mod_slug=MOD_SLUG,
        mod_title=MOD_TITLE,
        required_mods=[],
        quests={quest.id: quest},
        dialogs={
            take_dialog.id: take_dialog,
            turnin_dialog.id: turnin_dialog,
        },
        squads={squad.id: squad},
    )


# ---------------------------------------------------------------------------
# Валидация и сборка
# ---------------------------------------------------------------------------


def main() -> None:
    """Проверяет проект, собирает мод и печатает результат."""
    project = create_project()
    db = GameDatabase()

    report = validate_project(project, db)
    print(report.to_text())

    if report.has_errors:
        raise SystemExit("Валидация не пройдена: есть ERROR.")

    builder = ModBuilder(
        output_dir=Path("output"),
        db_client=db,
        vanilla_root=Path("_unpacked"),
    )

    if not builder.build_project(project, validate=True):
        raise SystemExit("Сборка не удалась: смотрите logs/app.log.")

    print(f"Мод собран: {builder.output_dir / MOD_SLUG}")
    print(f"ERROR: {len(report.errors)}, WARNING: {len(report.warnings)}")


if __name__ == "__main__":
    main()
