"""«Последний ретранслятор» — эталонный Story-проект Anomaly 1.5.3.

Сценарий демонстрирует **все** новые механики Фазы 2 на примере настоящей
сюжетной цепочки из двух многоэтапных квестов:

1. Борода на Затоне выдаёт Q1 ``mymod_relay_01_silence``. Диалог выдачи
   содержит выбор «согласиться / отказаться»; отказ не выдаёт задачу.
2. Q1 стартует этап 0: Story-отряд ``mymod_relay_merc_squad`` спавнится на
   Шевченко (``zat_b7``), вдали от Скадовска, и идёт к Портовым кранам
   (``zat_b52``) через ``target_smart`` своей секции. Никаких вызовов
   ``sim_squad_warfare``.
3. Смерть последнего NPC отряда выдаёт поршень ``mymod_relay_merc_dead``
   (``CustomSquad.death_infos``). ``transfer_conditions`` переключает Q1 на
   этап 1, а ``target_variants`` переносит маркер на Бороду.
4. Q1 завершается только в диалоге сдачи ``mymod_relay_01_turnin``
   (``CompleteTask``): награда — 5 000 ₽ и поршень ``mymod_relay_01_done``.
5. После Q1 открывается Q2 ``mymod_relay_02_decryptor``. Диалог выдачи —
   снова с выбором; этап 0 спавнит охрану ``mymod_relay_guard_squad`` на
   Земснаряде (``zat_b14_smart_terrain``) и требует добыть
   ``itm_pda_common``.
6. ``descr_variants`` обновляет текст этапа 0, когда охрана убита, но ПДА
   ещё не поднят. При старте этапа ``SpawnNpcItem`` кладёт ``itm_pda_common``
   в рюкзак командира охраны, поэтому шифратор снимается с трупа.
   Переход на этап 1 — по ``HasItem``.
7. Q2 завершается в диалоге сдачи: ветка ``HasItem`` изымает ПДА и вызывает
   ``CompleteTask``; ``_reward`` выдаёт 12 000 ₽ и ВСС «Винторез»
   (``wpn_vintorez``).

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
    CompleteTask,
    CustomSquad,
    DescrVariant,
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveTask,
    HasInfo,
    HasItem,
    ModProject,
    Phrase,
    Quest,
    RemoveItem,
    RemoveSquad,
    SpawnNpcItem,
    SpawnSquad,
    Stage,
    TargetVariant,
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
Q2 = "mymod_relay_02_decryptor"

# Story-отряды.
SQUAD_MERC = "mymod_relay_merc_squad"
SQUAD_GUARD = "mymod_relay_guard_squad"

# Инфопоршни (стандарт: <mod_slug>_<chapter>_<quest>_<role>).
INFO_Q1_TAKEN = "mymod_relay_01_taken"
INFO_MERC_DEAD = "mymod_relay_merc_dead"
INFO_Q1_DONE = "mymod_relay_01_done"
INFO_Q2_TAKEN = "mymod_relay_02_taken"
INFO_GUARD_DEAD = "mymod_relay_guard_dead"
INFO_Q2_DONE = "mymod_relay_02_done"

# Смарты Затона (проверены по локальной БД).
# zat_b7 — Шевченко, zat_b52 — Портовые краны,
# zat_b14_smart_terrain — Земснаряд.
Q1_SPAWN_SMART = "zat_b7"
Q1_TARGET_SMART = "zat_b52"
Q2_SMART = "zat_b14_smart_terrain"

# Квестовый предмет и награды.
DECRYPTOR_ITEM = "itm_pda_common"
Q1_REWARD_MONEY = 5000
Q2_REWARD_MONEY = 12000
Q2_REWARD_ITEM = "wpn_vintorez"

# ---------------------------------------------------------------------------
# Q1: «Последний ретранслятор» — уничтожить группу у ретранслятора
# ---------------------------------------------------------------------------


def create_first_quest() -> Quest:
    """Собирает Q1: Story-спавн, смерть отряда и возврат к Бороде."""
    return Quest(
        id=Q1,
        npc_id=NPC_ID,
        giver_npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id="mymod_relay_01_take",
        dialog_ids=["mymod_relay_01_take", "mymod_relay_01_turnin"],
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
                target_squad_id=SQUAD_MERC,
                # Story-вариативность: как только отряд уничтожен, маркер
                # переносится на Бороду, к которому нужно вернуться.
                target_variants=[
                    TargetVariant(
                        when=[HasInfo(info=INFO_MERC_DEAD)],
                        value=NPC_ID,
                    ),
                ],
            ),
            1: Stage(
                id=1,
                title_ru="Вернуться к Бороде за наградой",
                title_en="Return to the barman for the reward",
                descr_ru=(
                    "Ретранслятор чист. Вернитесь на Скадовск к Бороде."
                ),
                descr_en=(
                    "The relay is clear. Return to the barman at Skadovsk."
                ),
                target_alias=NPC_ID,
            ),
        },
        # Story-спавн: create_squad без set_target/stay_time/force_online.
        on_init_actions=[
            SpawnSquad(
                squad_alias=SQUAD_MERC,
                smart_alias=Q1_SPAWN_SMART,
                mode="story",
            ),
        ],
        # Явный переход этапа 0 -> 1 по поршню смерти отряда.
        transfer_conditions={
            0: {"complete": [HasInfo(info=INFO_MERC_DEAD)]},
        },
        fail_on_giver_death=True,
        taken_info=INFO_Q1_TAKEN,
        complete_info=INFO_Q1_DONE,
        # Иначе старый поршень смерти сразу переведёт повторное взятие.
        cleanup_infos=[INFO_MERC_DEAD],
        # При провале/отмене Story-отряд не должен остаться в мире.
        on_fail_actions=[
            RemoveSquad(squad_alias=SQUAD_MERC),
        ],
        reward_money=Q1_REWARD_MONEY,
    )


# ---------------------------------------------------------------------------
# Q2: «Шифратор связного» — найти ПДА и вернуть его Бороде
# ---------------------------------------------------------------------------


def create_second_quest() -> Quest:
    """Собирает Q2: охрана на Земснаряде, предмет и доклад Бороде."""
    return Quest(
        id=Q2,
        npc_id=NPC_ID,
        giver_npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        dialog_id="mymod_relay_02_take",
        dialog_ids=["mymod_relay_02_take", "mymod_relay_02_turnin"],
        title_ru="Шифратор связного",
        title_en="The Courier's Decryptor",
        descr_ru=(
            "Связной наёмников ушёл к Земснаряду с шифратором. "
            "Найдите ПДА и верните его Бороде."
        ),
        descr_en=(
            "The mercenary courier went to the dredge with the decryptor. "
            "Find the PDA and bring it to the barman."
        ),
        is_storyline=True,
        icon="ui_inGame2_Put_v_pripyat",
        prior=60,
        stages={
            0: Stage(
                id=0,
                title_ru="Найти шифратор на Земснаряде",
                title_en="Find the decryptor at the dredge",
                descr_ru=(
                    "Охрана связного укрепилась на Земснаряде. "
                    "Обыщите точку и заберите ПДА с шифратором."
                ),
                descr_en=(
                    "The courier's guards dug in at the dredge. "
                    "Search the site and take the PDA with the decryptor."
                ),
                # Text-вариативность: охрана убита, но ПДА ещё не поднят.
                descr_variants=[
                    DescrVariant(
                        when=[HasInfo(info=INFO_GUARD_DEAD)],
                        text_ru=(
                            "Охрана мертва. Обыщите Земснаряд и заберите "
                            "ПДА с шифратором."
                        ),
                        text_en=(
                            "The guards are dead. Search the dredge and take "
                            "the PDA with the decryptor."
                        ),
                    ),
                ],
                target_alias=Q2_SMART,
                # Этап сам спавнит охрану ровно один раз при входе.
                on_start_actions=[
                    SpawnSquad(
                        squad_alias=SQUAD_GUARD,
                        smart_alias=Q2_SMART,
                        mode="story",
                    ),
                    # Шифратор лежит в рюкзаке командира охраны: игрок
                    # снимает его с трупа после боя.
                    SpawnNpcItem(
                        item_alias=DECRYPTOR_ITEM,
                        target_alias=SQUAD_GUARD,
                        count=1,
                    ),
                ],
            ),
            1: Stage(
                id=1,
                title_ru="Доставить шифратор Бороде",
                title_en="Deliver the decryptor to the barman",
                descr_ru=(
                    "Шифратор у вас. Вернитесь на Скадовск и отдайте его "
                    "Бороде."
                ),
                descr_en=(
                    "You have the decryptor. Return to Skadovsk and hand it "
                    "to the barman."
                ),
                target_alias=NPC_ID,
            ),
        },
        # Переход этапа 0 -> 1 только когда ПДА реально в инвентаре.
        transfer_conditions={
            0: {
                "complete": [
                    HasItem(item_alias=DECRYPTOR_ITEM, count=1),
                ],
            },
        },
        fail_on_giver_death=True,
        taken_info=INFO_Q2_TAKEN,
        complete_info=INFO_Q2_DONE,
        cleanup_infos=[INFO_GUARD_DEAD],
        on_fail_actions=[
            # При отмене изымаем уже подобранный ПДА: иначе повторное
            # взятие сразу закроет этап 0 по HasItem.
            RemoveItem(item_alias=DECRYPTOR_ITEM, count=1),
            RemoveSquad(squad_alias=SQUAD_GUARD),
        ],
        reward_money=Q2_REWARD_MONEY,
        reward_item_alias=Q2_REWARD_ITEM,
        reward_item_count=1,
    )


# ---------------------------------------------------------------------------
# Диалоги
# ---------------------------------------------------------------------------


def create_dialogs() -> list[Dialog]:
    """Возвращает диалоги выдачи и сдачи обоих квестов."""
    first_take = Dialog(
        id="mymod_relay_01_take",
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=Q1,
        role="take",
        preconditions=[DontHasInfo(info=INFO_Q1_TAKEN)],
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
                    "Слышал. Наёмники заняли его и глушат связь. "
                    "Возьмёшься?"
                ),
                text_en=(
                    "I have. Mercs took it and jam the signal. "
                    "Will you take the job?"
                ),
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Берусь. Где их искать?",
                text_en="I'm in. Where do I find them?",
                actions=[
                    GiveInfo(info=INFO_Q1_TAKEN),
                    GiveTask(task_id=Q1),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru=(
                    "На Шевченко. Убери их и возвращайся на Скадовск "
                    "за наградой."
                ),
                text_en=(
                    "At Shevchenko. Take them out and come back to Skadovsk "
                    "for your reward."
                ),
            ),
            4: Phrase(
                id=4,
                text_ru="Не сейчас.",
                text_en="Not now.",
                next_phrases=[5],
            ),
            5: Phrase(
                id=5,
                text_ru="Как надумаешь — заходи.",
                text_en="Come back when you make up your mind.",
            ),
        },
    )

    first_turnin = Dialog(
        id="mymod_relay_01_turnin",
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=Q1,
        role="turnin",
        preconditions=[
            HasInfo(info=INFO_MERC_DEAD),
            DontHasInfo(info=INFO_Q1_DONE),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Борода, ретранслятор чист.",
                text_en="Barman, the relay is clear.",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Хорошая работа. Держи свои пять тысяч.",
                text_en="Good work. Here are your five thousand.",
                next_phrases=[2],
            ),
            2: Phrase(
                id=2,
                text_ru="Было дело.",
                text_en="It was a job.",
                actions=[CompleteTask(task_id=Q1)],
            ),
        },
    )

    second_take = Dialog(
        id="mymod_relay_02_take",
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=Q2,
        role="take",
        preconditions=[
            HasInfo(info=INFO_Q1_DONE),
            DontHasInfo(info=INFO_Q2_TAKEN),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Борода, есть ещё работа?",
                text_en="Barman, got more work?",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru=(
                    "Раз уж ты вернулся — у тех наёмников связной ушёл "
                    "к Земснаряду с шифратором. Возьмёшься довести дело "
                    "до конца?"
                ),
                text_en=(
                    "Since you're back — the mercs' courier went to the "
                    "dredge with a decryptor. Will you finish the job?"
                ),
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Возьмусь.",
                text_en="I'll take it.",
                actions=[
                    GiveInfo(info=INFO_Q2_TAKEN),
                    GiveTask(task_id=Q2),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru=(
                    "Охрана у Земснаряда. Принеси шифратор, и я хорошо "
                    "заплачу."
                ),
                text_en=(
                    "The guards are at the dredge. Bring me the decryptor "
                    "and I'll pay well."
                ),
            ),
            4: Phrase(
                id=4,
                text_ru="Не сейчас.",
                text_en="Not now.",
                next_phrases=[5],
            ),
            5: Phrase(
                id=5,
                text_ru="Тогда заходи позже.",
                text_en="Then come back later.",
            ),
        },
    )

    second_turnin = Dialog(
        id="mymod_relay_02_turnin",
        npc_alias=NPC_ALIAS,
        npc_id=NPC_ID,
        npc_location=NPC_LOCATION,
        task_id=Q2,
        role="turnin",
        preconditions=[
            HasInfo(info=INFO_Q2_TAKEN),
            DontHasInfo(info=INFO_Q2_DONE),
        ],
        phrases={
            0: Phrase(
                id=0,
                text_ru="Борода, насчёт шифратора...",
                text_en="Barman, about that decryptor...",
                next_phrases=[1],
            ),
            1: Phrase(
                id=1,
                text_ru="Принёс?",
                text_en="Did you bring it?",
                next_phrases=[2, 4],
            ),
            2: Phrase(
                id=2,
                text_ru="Вот он.",
                text_en="Here it is.",
                preconditions=[
                    HasItem(item_alias=DECRYPTOR_ITEM, count=1),
                ],
                actions=[
                    RemoveItem(item_alias=DECRYPTOR_ITEM, count=1),
                    CompleteTask(task_id=Q2),
                ],
                next_phrases=[3],
            ),
            3: Phrase(
                id=3,
                text_ru="Отличная работа, сталкер. Вот твоя награда.",
                text_en="Good work, stalker. Here is your reward.",
            ),
            4: Phrase(
                id=4,
                text_ru="Ещё ищу. Охрана у Земснаряда.",
                text_en="Still looking. The guards are at the dredge.",
            ),
        },
    )

    return [first_take, first_turnin, second_take, second_turnin]


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
            SQUAD_MERC: CustomSquad(
                id=SQUAD_MERC,
                faction="killer",
                npc=[
                    "sim_default_killer_1",
                    "sim_default_killer_2",
                    "sim_default_killer_3",
                ],
                target_smart=Q1_TARGET_SMART,
                story_id=SQUAD_MERC,
                death_infos=[INFO_MERC_DEAD],
                relationship="enemy",
            ),
            SQUAD_GUARD: CustomSquad(
                id=SQUAD_GUARD,
                faction="killer",
                npc=[
                    "sim_default_killer_2",
                    "sim_default_killer_4",
                ],
                target_smart=Q2_SMART,
                story_id=SQUAD_GUARD,
                death_infos=[INFO_GUARD_DEAD],
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
