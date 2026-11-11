"""Сюжетная цепочка «Братья по оружию» (Душман, Мёртвый Город).

Финальная версия. Все секции предметов и NPC подтверждены.

Логика:
  1. Душман просит АК-105 и бронебойные патроны 5.45.
     Сдача -> 15 000 рублей, переход на этап «принести РПГ».
  2. Душман просит РПГ-7. Сдача -> переход на этап «забрать награду».
  3. Финальная награда — АС ВАЛ (wpn_val_modern_kobra).

R&D-ограничения фреймворка:
  * переходы стадий, выдача предметов и условия — ТОЛЬКО через инфопоршни
    (GiveInfo / HasInfo / DontHasInfo);
  * HasItem не поддерживается — сдача предметов завязана на поршни,
    выдаваемые в репликах диалогов;
  * никаких проверок смерти NPC — эта ветка удалена.

Запуск из корня проекта:
    python tools/build_bro_story.py
"""

from __future__ import annotations

from pathlib import Path
import sys


# Добавляем корень проекта в sys.path, чтобы `import src.*` работал
# при запуске `python examples/merc_test_v2.py` из любой директории.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.compiler.builder import ModBuilder
from src.core.models import (
    CompleteTask,
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveItem,
    GiveMoney,
    GiveTask,
    HasInfo,
    ModProject,
    Phrase,
    Quest,
    Stage,
)

# ---------------------------------------------------------------------------
# Константы сценария
# ---------------------------------------------------------------------------

PROJECT_NAME = "Brothers in Arms"

# --- Квест и диалоги ---
QUEST_ID = "mymod_bro_quest"
TAKE_DIALOG_ID = "mymod_bro_take"
TURNIN_ITEMS_DIALOG_ID = "mymod_bro_turnin_items"
TURNIN_RPG_DIALOG_ID = "mymod_bro_turnin_rpg"
TURNIN_REWARD_DIALOG_ID = "mymod_bro_turnin_reward"

# --- NPC-квестодатель ---
NPC_ID = "cit_killers_merc_trader_stalker"
NPC_LOCATION = "deadcity"
NPC_ALIAS = "deadcity.dushman"

# --- Секции предметов (подтверждены) ---
AMMO_AP_SECTION = "ammo_5.45x39_ap"
AMMO_AP_COUNT = 60

AK105_SECTION = "wpn_ak105"
RPG_SECTION = "wpn_rpg7"

# ВНИМАНИЕ: wpn_val_modern_kobra — это ВАЛ «Кобра», а не «Синдикат».
# Если нужен именно «Синдикат» — заменить секцию и тексты ниже.
VAL_REWARD_SECTION = "wpn_val_modern_kobra"
VAL_REWARD_NAME_RU = "АС ВАЛ «Кобра»"
VAL_REWARD_NAME_EN = "AS VAL 'Kobra'"

# --- Поршни сценария ---
INFO_STARTED = "mymod_bro_started"
INFO_ITEMS_GIVEN = "mymod_items_given"
INFO_RPG_GIVEN = "mymod_rpg_given"
INFO_DONE = "mymod_bro_done"

# --- Награды ---
REWARD_MONEY_STAGE1 = 15000


# ---------------------------------------------------------------------------
# Построение моделей проекта
# ---------------------------------------------------------------------------

def create_bro_project() -> ModProject:
    """Собирает ModProject для цепочки «Братья по оружию».

    Этапы:
      0 — Принести АК-105 и бронебойные патроны 5.45 Душману.
      1 — Принести РПГ-7 Душману.
      2 — Получить финальную награду (АС ВАЛ) у Душмана.

    Переходы стадий завязаны на инфопоршни:
      0 -> 1 : mymod_items_given   (выдаёт Диалог 2)
      1 -> 2 : mymod_rpg_given      (выдаёт Диалог 3)
      2 -> done : mymod_bro_done    (выдаёт CompleteTask в Диалоге 4)

    Returns:
        ModProject: валидный проект, готовый к сборке.

    Raises:
        pydantic.ValidationError: при нарушении инвариантов моделей.
    """
    quest = Quest(
        id=QUEST_ID,
        npc_id=NPC_ID,
        giver_npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id=TAKE_DIALOG_ID,
        dialog_ids=[
            TAKE_DIALOG_ID,
            TURNIN_ITEMS_DIALOG_ID,
            TURNIN_RPG_DIALOG_ID,
            TURNIN_REWARD_DIALOG_ID,
        ],
        title_ru="Братья по оружию",
        title_en="Brothers in Arms",
        descr_ru=(
            "Душман просит достать снаряжение и РПГ, а затем "
            "обещает щедрую награду."
        ),
        descr_en=(
            "Dushman asks for gear and an RPG, promising a generous "
            "reward in return."
        ),
        is_storyline=True,
        icon="ui_inGame2_Put_v_pripyat",
        prior=60,
        stages={
            # -----------------------------------------------------------------
            # Этап 0. Принести снаряжение
            # -----------------------------------------------------------------
            0: Stage(
                id=0,
                title_ru="Снаряжение для Душмана",
                title_en="Gear for Dushman",
                descr_ru=(
                    "Добудьте автомат АК-105 и бронебойные патроны 5.45 "
                    "и принесите их Душману в Мёртвый Город."
                ),
                descr_en=(
                    "Obtain an AK-105 rifle and 5.45 AP rounds, then "
                    "bring them to Dushman in Dead City."
                ),
                target_alias="deadcity.dushman",
                on_start_actions=[],
            ),
            # -----------------------------------------------------------------
            # Этап 1. Принести РПГ
            # -----------------------------------------------------------------
            1: Stage(
                id=1,
                title_ru="РПГ для Душмана",
                title_en="RPG for Dushman",
                descr_ru=(
                    "Душману нужен РПГ-7. Добудьте его и принесите "
                    "в Мёртвый Город."
                ),
                descr_en=(
                    "Dushman needs an RPG-7. Obtain it and bring it "
                    "to Dead City."
                ),
                target_alias="deadcity.dushman",
                on_start_actions=[],
            ),
            # -----------------------------------------------------------------
            # Этап 2. Забрать награду
            # -----------------------------------------------------------------
            2: Stage(
                id=2,
                title_ru="Забрать награду у Душмана",
                title_en="Claim the reward from Dushman",
                descr_ru=(
                    "РПГ сдан. Вернитесь к Душману за обещанной "
                    "наградой."
                ),
                descr_en=(
                    "The RPG is handed over. Return to Dushman for "
                    "the promised reward."
                ),
                target_alias="deadcity.dushman",
                on_start_actions=[],
            ),
        },
        # Переходы стадий — только через инфопоршни.
        transfer_conditions={
            0: {"complete": [HasInfo(info=INFO_ITEMS_GIVEN)]},
            1: {"complete": [HasInfo(info=INFO_RPG_GIVEN)]},
            # Этап 2 завершается через CompleteTask в Диалоге 4.
        },
        # Награды выдаются в actions диалогов, чтобы не дублировать
        # автоматическую выдачу из _reward.
        reward_money=None,
        reward_item_alias=None,
        reward_item_count=1,
        # complete_info=INFO_DONE выдастся из _reward при завершении
        # квеста; отдельный GiveInfo(INFO_DONE) в Диалоге 4 не нужен.
        complete_info=INFO_DONE,
        taken_info=INFO_STARTED,
    )

    # -----------------------------------------------------------------------
    # ДИАЛОГ 1. Старт квеста
    # -----------------------------------------------------------------------
    take_dialog = Dialog(
        id=TAKE_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="take",
        preconditions=[DontHasInfo(info=INFO_STARTED)],
        phrases={
            0: Phrase(
                id=0,
                text_ru=(
                    "Слышал, ты ищешь работу, бродяга? Есть дело, но "
                    "сначала — снаряжение. Нужен АК-105 и бронебойные "
                    "пятисорокопятки. Достанешь?"
                ),
                text_en=(
                    "I heard you're looking for work, stalker. I have "
                    "a job, but first — gear. I need an AK-105 and "
                    "armor-piercing 5.45 rounds. Can you get them?"
                ),
                next_phrases=[1, 2],
            ),
            1: Phrase(
                id=1,
                text_ru="Достану. Говори, где искать.",
                text_en="I'll get them. Where do I look?",
                actions=[
                    GiveInfo(info=INFO_STARTED),
                    GiveTask(task_id=QUEST_ID),
                ],
            ),
            2: Phrase(
                id=2,
                text_ru="Не сейчас. Слишком много возни.",
                text_en="Not now. Too much hassle.",
            ),
        },
    )

    # -----------------------------------------------------------------------
    # ДИАЛОГ 2. Сдача снаряжения (этап 0 -> 1)
    # -----------------------------------------------------------------------
    turnin_items_dialog = Dialog(
        id=TURNIN_ITEMS_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turnin",
        preconditions=[
            HasInfo(info=INFO_STARTED),
            DontHasInfo(info=INFO_ITEMS_GIVEN),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru=(
                    "Ну что, принёс? Показывай, что там у тебя в рюкзаке."
                ),
                text_en=(
                    "So, did you bring it? Show me what's in that "
                    "backpack of yours."
                ),
                next_phrases=[1, 2],
            ),
            1: Phrase(
                id=1,
                text_ru=(
                    "Держи. АК-105 и патроны. Всё как договаривались."
                ),
                text_en=(
                    "Here. AK-105 and the rounds. Everything as agreed."
                ),
                actions=[
                    GiveInfo(info=INFO_ITEMS_GIVEN),
                    GiveMoney(amount=REWARD_MONEY_STAGE1),
                ],
            ),
            2: Phrase(
                id=2,
                text_ru="Ещё не всё собрал. Подожди.",
                text_en="I haven't got everything yet. Wait.",
            ),
        },
    )

    # -----------------------------------------------------------------------
    # ДИАЛОГ 3. Сдача РПГ (этап 1 -> 2)
    # -----------------------------------------------------------------------
    turnin_rpg_dialog = Dialog(
        id=TURNIN_RPG_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turnin",
        preconditions=[
            HasInfo(info=INFO_ITEMS_GIVEN),
            DontHasInfo(info=INFO_RPG_GIVEN),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru=(
                    "А это что у тебя? РПГ-7? Вот это уже серьёзный "
                    "разговор. Давай сюда."
                ),
                text_en=(
                    "And what's that you've got? An RPG-7? Now we're "
                    "talking serious. Hand it over."
                ),
                next_phrases=[1, 2],
            ),
            1: Phrase(
                id=1,
                text_ru=(
                    "Держи. Тяжёлая штука, но я донёс."
                ),
                text_en=(
                    "Here. Heavy thing, but I carried it."
                ),
                actions=[
                    GiveInfo(info=INFO_RPG_GIVEN),
                ],
            ),
            2: Phrase(
                id=2,
                text_ru="Пока не достал. Работаю над этим.",
                text_en="Haven't got it yet. Working on it.",
            ),
        },
    )

    # -----------------------------------------------------------------------
    # ДИАЛОГ 4. Финальная награда (этап 2 -> done)
    # -----------------------------------------------------------------------
    turnin_reward_dialog = Dialog(
        id=TURNIN_REWARD_DIALOG_ID,
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=QUEST_ID,
        role="turn_in",
        preconditions=[
            HasInfo(info=INFO_RPG_GIVEN),
            DontHasInfo(info=INFO_DONE),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru=(
                    "Снаряжение есть, РПГ есть. Ты сделал всё, что "
                    "нужно, бродяга. Вот твоя награда — "
                    f"{VAL_REWARD_NAME_RU}. Работай с ним аккуратно."
                ),
                text_en=(
                    "Gear's here, RPG's here. You did everything "
                    "needed, stalker. Here's your reward — "
                    f"{VAL_REWARD_NAME_EN}. Handle it carefully."
                ),
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Благодарю. Если будет ещё работа — заходи.",
                text_en="Thanks. If there's more work — drop by.",
                actions=[
                    GiveItem(item_alias=VAL_REWARD_SECTION, count=1),
                    CompleteTask(task_id=QUEST_ID),
                ],
            ),
        },
    )

    return ModProject(
        name=PROJECT_NAME,
        required_mods=[],
        quests={quest.id: quest},
        dialogs={
            take_dialog.id: take_dialog,
            turnin_items_dialog.id: turnin_items_dialog,
            turnin_rpg_dialog.id: turnin_rpg_dialog,
            turnin_reward_dialog.id: turnin_reward_dialog,
        },
    )


# ---------------------------------------------------------------------------
# Сборка
# ---------------------------------------------------------------------------

def main() -> None:
    """Создаёт проект и запускает сборку установочного каталога мода."""
    project = create_bro_project()

    builder = ModBuilder(
        output_dir=Path("output"),
        vanilla_root=Path("_unpacked"),
    )

    if not builder.build_project(project):
        raise SystemExit("Сборка не удалась: смотрите logs/app.log.")

    print(f"Мод собран в: {builder.output_dir}")


if __name__ == "__main__":
    main()