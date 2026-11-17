"""«Последний ретранслятор» — эталонный Story-проект Anomaly 1.5.3.

Сценарий собран по публичному контракту ``docs/API_v2.md`` и повторяет
ванильный паттерн сюжетной цепочки:

1. Борода на Затоне выдаёт Q1 ``mymod_relay_01_silence``.
2. ``on_init`` Q1 спавнит Story-отряд ``mymod_relay_merc_squad`` на
   ``zat_stalker_base_smart``. Отряд идёт к ``zat_b52`` по ``target_smart``
   из своей секции, без вызовов ``sim_squad_warfare``.
3. Смерть последнего NPC отряда выдаёт поршень
   ``mymod_relay_merc_dead`` (``CustomSquad.death_infos``).
4. ``condlist_1`` завершает Q1, ``on_complete`` выдаёт Q2 через ``GiveTask``.
5. Q2 ``mymod_relay_02_report`` завершается поршнем
   ``mymod_relay_reported`` из диалога; награда — 12 000 рублей и
   ``wpn_val_modern_kobra``.

Новые ``character_desc_*.xml`` не создаются: патчится только ванильный
профиль ``zat_a2_stalker_barmen`` в ``character_desc_zaton.xml``.

Запуск из корня проекта::

    venv\\Scripts\\python.exe examples\\build_story_relay.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Запуск вида ``python examples/build_story_relay.py`` кладёт в sys.path
# каталог examples, а не корень проекта. Добавляем корень явно.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.compiler.builder import ModBuilder
from src.core.models import (
    CustomSquad,
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveTask,
    HasInfo,
    ModProject,
    Phrase,
    Quest,
    QuestCondlist,
    RemoveSquad,
    SpawnSquad,
    Stage,
)

# ---------------------------------------------------------------------------
# Константы сценария
# ---------------------------------------------------------------------------

PROJECT_NAME = "Last Relay"
PROJECT_SLUG = "last_relay"

# Квестодатель: ванильный Борода на Затоне.
NPC_ID = "zat_a2_stalker_barmen"
NPC_LOCATION = "zaton"
NPC_ALIAS = "zaton.barman"

# Сюжетная цепочка.
Q1 = "mymod_relay_01_silence"
Q2 = "mymod_relay_02_report"
SQUAD = "mymod_relay_merc_squad"

# Инфопоршни (стандарт: <mod_slug>_<chapter>_<quest>_<role>).
INFO_TAKEN = "mymod_relay_01_taken"
INFO_MERC_DEAD = "mymod_relay_merc_dead"
INFO_Q1_DONE = "mymod_relay_01_done"
INFO_REPORTED = "mymod_relay_reported"
INFO_DONE = "mymod_relay_done"

# Смарт спавна отряда и точка назначения из его секции.
SPAWN_SMART = "zat_stalker_base_smart"
TARGET_SMART = "zat_b52"

# Награды.
Q1_REWARD_MONEY = 5000
Q2_REWARD_MONEY = 12000
Q2_REWARD_ITEM = "wpn_val_modern_kobra"


# ---------------------------------------------------------------------------
# Q1: «Последний ретранслятор» — уничтожить группу у ретранслятора
# ---------------------------------------------------------------------------


def create_first_quest() -> Quest:
    """Собирает Q1: спавн Story-отряда и завершение по его смерти."""
    return Quest(
        id=Q1,
        npc_id=NPC_ID,
        giver_npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id="mymod_relay_take",
        dialog_ids=["mymod_relay_take"],
        title_ru="Последний ретранслятор",
        title_en="The Last Relay",
        descr_ru=(
            "Борода просит убрать группу, захватившую ретранслятор в порту "
            "Затона."
        ),
        descr_en=(
            "The barman wants the group that seized the relay at Zaton port "
            "eliminated."
        ),
        is_storyline=True,
        icon="ui_inGame2_Put_v_pripyat",
        prior=60,
        stages={
            0: Stage(
                id=0,
                title_ru="Уничтожить группу у ретранслятора",
                title_en="Eliminate the relay group",
                descr_ru=(
                    "Наёмники заняли ретранслятор в порту Затона. "
                    "Уничтожьте их."
                ),
                descr_en=(
                    "Mercenaries have seized the relay at Zaton port. "
                    "Eliminate them."
                ),
                # Маркер держится на story id отряда после его спавна.
                target_squad_id=SQUAD,
            ),
        },
        # Story-спавн: create_squad без set_target/stay_time/force_online.
        on_init_actions=[
            SpawnSquad(
                squad_alias=SQUAD,
                smart_alias=SPAWN_SMART,
                mode="story",
            ),
        ],
        # Ванильный паттерн: on_death -> info -> condlist -> complete.
        extra_condlists=[
            QuestCondlist(
                when=[HasInfo(info=INFO_MERC_DEAD)],
                result="complete",
            ),
        ],
        fail_on_giver_death=True,
        taken_info=INFO_TAKEN,
        complete_info=INFO_Q1_DONE,
        # Иначе старый поршень смерти сразу завершит повторное взятие.
        cleanup_infos=[INFO_MERC_DEAD],
        on_complete_actions=[
            GiveTask(task_id=Q2),
        ],
        # При провале/отмене Story-отряд не должен остаться в мире.
        on_fail_actions=[
            RemoveSquad(squad_alias=SQUAD),
        ],
        reward_money=Q1_REWARD_MONEY,
    )


# ---------------------------------------------------------------------------
# Q2: «Последний ретранслятор: отчёт» — вернуться и доложить
# ---------------------------------------------------------------------------


def create_second_quest() -> Quest:
    """Собирает Q2: доклад Бороде, завершение поршнем из диалога."""
    return Quest(
        id=Q2,
        npc_id=NPC_ID,
        giver_npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id="mymod_relay_report",
        dialog_ids=["mymod_relay_report"],
        title_ru="Последний ретранслятор: отчёт",
        title_en="The Last Relay: Report",
        descr_ru="Вернитесь к Бороде и доложите о зачистке.",
        descr_en="Return to the barman and report the cleanup.",
        is_storyline=True,
        icon="ui_inGame2_Put_v_pripyat",
        prior=60,
        stages={
            0: Stage(
                id=0,
                title_ru="Доложить Бороде",
                title_en="Report to the barman",
                descr_ru="Ретранслятор чист. Поговорите с Бородой.",
                descr_en="The relay is clear. Talk to the barman.",
                target_alias=NPC_ID,
            ),
        },
        extra_condlists=[
            QuestCondlist(
                when=[HasInfo(info=INFO_REPORTED)],
                result="complete",
            ),
        ],
        fail_on_giver_death=True,
        complete_info=INFO_DONE,
        cleanup_infos=[INFO_REPORTED],
        reward_money=Q2_REWARD_MONEY,
        reward_item_alias=Q2_REWARD_ITEM,
        reward_item_count=1,
    )


# ---------------------------------------------------------------------------
# Диалоги
# ---------------------------------------------------------------------------


def create_dialogs() -> list[Dialog]:
    """Возвращает диалоги выдачи Q1 и сдачи Q2."""
    take_dialog = Dialog(
        id="mymod_relay_take",
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=Q1,
        role="take",
        preconditions=[DontHasInfo(info=INFO_TAKEN)],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Борода, слышал про ретранслятор в порту?",
                text_en="Barman, heard about the relay at the port?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru=(
                    "Слышал. Наёмники заняли его и глушат связь. Убери их."
                ),
                text_en=(
                    "I have. Mercs took it and jam the signal. Take them out."
                ),
                actions=[
                    GiveInfo(info=INFO_TAKEN),
                    GiveTask(task_id=Q1),
                ],
            ),
        },
    )

    report_dialog = Dialog(
        id="mymod_relay_report",
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=Q2,
        role="turnin",
        preconditions=[
            HasInfo(info=INFO_Q1_DONE),
            DontHasInfo(info=INFO_DONE),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Ретранслятор чист.",
                text_en="The relay is clear.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Хорошая работа. Держи свою плату.",
                text_en="Good work. Here is your payment.",
                # Завершает не CompleteTask, а condlist по этому поршню.
                actions=[GiveInfo(info=INFO_REPORTED)],
            ),
        },
    )

    return [take_dialog, report_dialog]


# ---------------------------------------------------------------------------
# Сборка проекта
# ---------------------------------------------------------------------------


def build_project() -> ModProject:
    """Создаёт эталонный Story-проект «Последний ретранслятор»."""
    first_quest = create_first_quest()
    second_quest = create_second_quest()
    dialogs = create_dialogs()

    return ModProject(
        name=PROJECT_NAME,
        # Slug зафиксирован явно; ядро также выводит last_relay из имени.
        mod_slug=PROJECT_SLUG,
        required_mods=[],
        quests={
            first_quest.id: first_quest,
            second_quest.id: second_quest,
        },
        dialogs={dialog.id: dialog for dialog in dialogs},
        squads={
            SQUAD: CustomSquad(
                id=SQUAD,
                faction="killer",
                npc=[
                    "sim_default_killer_1",
                    "sim_default_killer_2",
                    "sim_default_killer_3",
                ],
                target_smart=TARGET_SMART,
                story_id=SQUAD,
                death_infos=[INFO_MERC_DEAD],
                relationship="enemy",
            ),
        },
    )


def main() -> None:
    """Собирает мод в ``output/last_relay``."""
    project = build_project()
    builder = ModBuilder(
        output_dir=Path("output"),
        vanilla_root=Path("_unpacked"),
    )

    if not builder.build_project(project):
        raise SystemExit("Сборка не удалась: смотрите logs/app.log.")

    mod_root = builder.output_dir / PROJECT_SLUG
    if not mod_root.is_dir():
        raise SystemExit(f"Каталог сборки не найден: {mod_root}")

    print(f"Мод собран в: {mod_root}")
    print(f"Квесты: {', '.join(project.quests)}")


if __name__ == "__main__":
    main()
