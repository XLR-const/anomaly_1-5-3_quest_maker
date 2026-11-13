"""Автоматические тесты Pydantic-моделей редактора квестов.

Запуск из корня проекта::

    python -m unittest tests.test_models -v
    python -m unittest discover -s tests -v

Тесты проверяют полиморфную сериализацию условий и действий, внутреннюю
валидацию графов диалогов/этапов и полный Round-trip проекта мода в JSON и
YAML. Для проверки ошибок используется :class:`pydantic.ValidationError`.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import yaml
from pydantic import TypeAdapter, ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.models import (  # noqa: E402
    Action,
    CompleteTask,
    Condition,
    Dialog,
    DontHasInfo,
    GiveInfo,
    GiveItem,
    GiveMoney,
    GiveTask,
    HasInfo,
    HasItem,
    HasMoney,
    ModProject,
    Phrase,
    Quest,
    RemoveInfo,
    SpawnSquad,
    Stage,
    TakeItem,
    TakeMoney,
    find_phrase_reward_conflicts,
    phrase_action_mode,
)

#: Эталонный русский текст реплики для проверки Unicode при Round-trip.
DIALOG_TEXT_RU = "Здравствуй, сталкер. Нужна помощь?"
#: Эталонный английский текст той же реплики.
DIALOG_TEXT_EN = "Hello, stalker. Need any help?"


# ---------------------------------------------------------------------------
# Фабрики тестовых данных
# ---------------------------------------------------------------------------


def _make_phrase(
    phrase_id: int,
    *,
    next_phrases: list[int] | None = None,
    actions: list[Action] | None = None,
) -> Phrase:
    """Создаёт минимальную валидную реплику с заданным идентификатором.

    Args:
        phrase_id (int):
            Идентификатор реплики внутри диалога.
        next_phrases (list[int] | None):
            Список доступных переходов. ``None`` заменяется пустым списком.
        actions (list[Action] | None):
            Действия при выборе реплики. ``None`` заменяется пустым списком.

    Returns:
        Phrase: Новая реплика с двуязычным текстом по умолчанию.
    """
    return Phrase(
        id=phrase_id,
        text_ru=f"Реплика {phrase_id}",
        text_en=f"Phrase {phrase_id}",
        next_phrases=list(next_phrases or []),
        actions=list(actions or []),
    )


def _make_dialog() -> Dialog:
    """Создаёт валидный диалог из двух связанных реплик.

    Стартовая фраза ``id=0`` ссылается на фразу ``id=1`` через
    ``next_phrases``. Такой граф удовлетворяет всем инвариантам :class:`Dialog`.

    Returns:
        Dialog: Валидный тестовый диалог.
    """
    return Dialog(
        id="mymod_test_dialog",
        npc_alias="esc.mayor_zhurov",
        phrases={
            0: _make_phrase(0, next_phrases=[1]),
            1: _make_phrase(1),
        },
    )


def _make_stage(stage_id: int) -> Stage:
    """Создаёт минимальный валидный этап квеста.

    Args:
        stage_id (int):
            Номер этапа. Значение также используется как ключ карты этапов.

    Returns:
        Stage: Этап с двуязычными заголовком и описанием.
    """
    return Stage(
        id=stage_id,
        title_ru=f"Этап {stage_id}",
        title_en=f"Stage {stage_id}",
        descr_ru=f"Описание этапа {stage_id}",
        descr_en=f"Description of stage {stage_id}",
        target_alias="esc.yuzhnyy_blokpost",
    )


def _make_quest(stage_ids: list[int]) -> Quest:
    """Создаёт квест с этапами, номера которых переданы явно.

    Фабрика намеренно не скрывает возможные ошибки нумерации: ключ каждой
    записи равен ``Stage.id``, поэтому переданный список ``[0, 2]`` создаст
    квест с пропущенным этапом и позволит проверить валидатор.

    Args:
        stage_ids (list[int]):
            Номера создаваемых этапов.

    Returns:
        Quest: Квест с картой этапов, собранной из ``stage_ids``.
    """
    return Quest(
        id="mymod_test_quest",
        title_ru="Тестовый квест",
        title_en="Test quest",
        descr_ru="Описание тестового квеста",
        descr_en="Test quest description",
        stages={stage_id: _make_stage(stage_id) for stage_id in stage_ids},
    )


def _make_project() -> ModProject:
    """Создаёт насыщенный проект для проверки полного Round-trip.

    Проект содержит один квест и один диалог. В данных присутствуют русский
    и английский тексты, несколько типов условий и действий, а также вложенные
    этапы и реплики, чтобы сериализация проверила всю иерархию моделей.

    Returns:
        ModProject: Валидный проект мода со всеми основными типами данных.
    """
    return ModProject(
        name="Тестовый сюжетный мод",
        required_mods=["bas_db.sqlite"],
        quests={
            "mymod_av_quest": Quest(
                id="mymod_av_quest",
                title_ru="Помощь южному блокпосту",
                title_en="Help the southern outpost",
                descr_ru="Помогите бойцам удержать южный блокпост.",
                descr_en="Help the soldiers hold the southern outpost.",
                stages={
                    0: Stage(
                        id=0,
                        title_ru="Поговорить с Журовым",
                        title_en="Talk to Zhurov",
                        descr_ru="Найдите майора Журова на южном блокпосту.",
                        descr_en="Find Major Zhurov at the southern outpost.",
                        target_alias="esc.mayor_zhurov",
                        on_start_actions=[
                            GiveInfo(info="mymod_av_started"),
                        ],
                    ),
                    1: Stage(
                        id=1,
                        title_ru="Дождаться подкрепления",
                        title_en="Wait for reinforcements",
                        descr_ru="Дождитесь подхода отряда на блокпост.",
                        descr_en="Wait for the squad to reach the outpost.",
                        target_alias="esc.yuzhnyy_blokpost",
                        on_start_actions=[
                            SpawnSquad(
                                squad_alias="squad.army_novice",
                                smart_alias="esc.yuzhnyy_blokpost",
                            )
                        ],
                    ),
                },
                on_init_actions=[GiveMoney(amount=5000)],
                on_complete_actions=[
                    GiveItem(item_alias="weapon.vssk_vykhlop")
                ],
                on_fail_actions=[RemoveInfo(info="mymod_av_started")],
            )
        },
        dialogs={
            "mymod_start_dialog": Dialog(
                id="mymod_start_dialog",
                npc_alias="esc.mayor_zhurov",
                preconditions=[HasInfo(info="mymod_av_available")],
                phrases={
                    0: Phrase(
                        id=0,
                        text_ru=DIALOG_TEXT_RU,
                        text_en=DIALOG_TEXT_EN,
                        next_phrases=[1],
                        preconditions=[
                            DontHasInfo(info="mymod_av_started")
                        ],
                        actions=[GiveInfo(info="mymod_dialog_seen")],
                    ),
                    1: Phrase(
                        id=1,
                        text_ru="До встречи.",
                        text_en="See you.",
                        actions=[
                            GiveItem(item_alias="weapon.vssk_vykhlop")
                        ],
                    ),
                },
            )
        },
    )


# ---------------------------------------------------------------------------
# Полиморфизм условий и действий
# ---------------------------------------------------------------------------


class TestPolymorphism(unittest.TestCase):
    """Проверка дискриминируемых объединений ``Condition`` и ``Action``."""

    def test_give_money_json_and_yaml_roundtrip(self) -> None:
        """GiveMoney восстанавливается как GiveMoney из JSON и YAML.

        Проверяется не только равенство суммы, но и конкретный класс результата:
        ошибка дискриминатора привела бы к созданию ``BaseAction`` или к
        отклонению данных.
        """
        action = GiveMoney(amount=5000)

        with self.subTest(format="json"):
            payload = action.model_dump_json()
            self.assertEqual(json.loads(payload)["type"], "give_money")

            restored = TypeAdapter(Action).validate_json(payload)
            self.assertIsInstance(restored, GiveMoney)
            self.assertEqual(restored.amount, 5000)
            self.assertEqual(restored, action)

        with self.subTest(format="yaml"):
            payload = yaml.safe_dump(
                action.model_dump(mode="python"),
                allow_unicode=True,
                sort_keys=False,
            )
            self.assertIn("type: give_money", payload)

            restored = TypeAdapter(Action).validate_python(
                yaml.safe_load(payload)
            )
            self.assertIsInstance(restored, GiveMoney)
            self.assertEqual(restored.amount, 5000)
            self.assertEqual(restored, action)

    def test_condition_json_roundtrip_preserves_subclass(self) -> None:
        """Условие HasInfo после JSON Round-trip остаётся HasInfo."""
        condition = HasInfo(info="mymod_av_available")
        payload = condition.model_dump_json()

        self.assertEqual(json.loads(payload)["type"], "has_info")

        restored = TypeAdapter(Condition).validate_json(payload)
        self.assertIsInstance(restored, HasInfo)
        self.assertEqual(restored.info, "mymod_av_available")
        self.assertEqual(restored, condition)

    def test_phrase_fields_restore_polymorphic_objects(self) -> None:
        """Поля Phrase восстанавливают конкретные классы условий и действий.

        Проверка идёт через реальную модель :class:`Phrase`, а не только через
        отдельный ``TypeAdapter``, чтобы зафиксировать корректность аннотаций
        ``list[Condition]`` и ``list[Action]``.
        """
        phrase = Phrase(
            id=0,
            text_ru="Проверка полиморфизма",
            text_en="Polymorphism check",
            preconditions=[HasInfo(info="mymod_known")],
            actions=[GiveMoney(amount=5000), GiveInfo(info="mymod_paid")],
        )

        restored = Phrase.model_validate_json(phrase.model_dump_json())

        self.assertIsInstance(restored.preconditions[0], HasInfo)
        self.assertIsInstance(restored.actions[0], GiveMoney)
        self.assertIsInstance(restored.actions[1], GiveInfo)
        self.assertEqual(restored, phrase)

    def test_unknown_action_type_raises_validation_error(self) -> None:
        """Неизвестный дискриминатор действия приводит к ValidationError."""
        with self.assertRaises(ValidationError):
            TypeAdapter(Action).validate_python({"type": "unknown_action"})

        with self.assertRaises(ValidationError):
            Phrase(
                id=0,
                text_ru="Неизвестное действие",
                text_en="Unknown action",
                actions=[{"type": "unknown_action"}],
            )


# ---------------------------------------------------------------------------
# Валидация диалогов
# ---------------------------------------------------------------------------


class TestDialogValidation(unittest.TestCase):
    """Проверка инвариантов графа реплик :class:`Dialog`."""

    def test_valid_dialog_is_created(self) -> None:
        """Валидный граф с фразами 0 и 1 успешно создаётся."""
        dialog = _make_dialog()

        self.assertEqual(set(dialog.phrases), {0, 1})
        self.assertEqual(dialog.phrases[0].next_phrases, [1])
        self.assertEqual(dialog.phrases[0].id, 0)
        self.assertEqual(dialog.phrases[1].id, 1)

    def test_dialog_without_start_phrase_raises_error(self) -> None:
        """Диалог без фразы id=0 отклоняется валидатором."""
        with self.assertRaises(ValidationError) as context:
            Dialog(
                id="mymod_broken_dialog",
                npc_alias="esc.mayor_zhurov",
                phrases={1: _make_phrase(1)},
            )

        self.assertIn("id=0", str(context.exception))

    def test_dialog_with_broken_next_phrase_raises_error(self) -> None:
        """Ссылка next_phrases на отсутствующую фразу отклоняется."""
        with self.assertRaises(ValidationError) as context:
            Dialog(
                id="mymod_broken_dialog",
                npc_alias="esc.mayor_zhurov",
                phrases={
                    0: _make_phrase(0, next_phrases=[2]),
                    1: _make_phrase(1),
                },
            )

        self.assertIn("id=2", str(context.exception))


# ---------------------------------------------------------------------------
# Валидация квестов
# ---------------------------------------------------------------------------


class TestQuestValidation(unittest.TestCase):
    """Проверка непрерывности нумерации этапов :class:`Quest`."""

    def test_valid_quest_with_continuous_stages_is_created(self) -> None:
        """Квест с этапами 0 и 1 успешно инициализируется."""
        quest = _make_quest([0, 1])

        self.assertEqual(set(quest.stages), {0, 1})
        self.assertEqual(quest.stages[0].id, 0)
        self.assertEqual(quest.stages[1].id, 1)

    def test_quest_with_gap_in_stages_raises_error(self) -> None:
        """Пропуск этапа 1 при наличии этапа 2 отклоняется."""
        with self.assertRaises(ValidationError) as context:
            _make_quest([0, 2])

        self.assertIn("[0, 1]", str(context.exception))
        self.assertIn("[0, 2]", str(context.exception))


# ---------------------------------------------------------------------------
# Round-trip проекта мода
# ---------------------------------------------------------------------------


class TestModProjectSerialization(unittest.TestCase):
    """Проверка полного сохранения и восстановления :class:`ModProject`."""

    def setUp(self) -> None:
        """Создаёт эталонный проект перед каждым тестом."""
        self.project = _make_project()

    def test_json_roundtrip_is_lossless(self) -> None:
        """JSON Round-trip сохраняет модель, тексты и полиморфные типы."""
        payload = self.project.to_json()

        self.assertIn(DIALOG_TEXT_RU, payload)
        self.assertIn(DIALOG_TEXT_EN, payload)
        self.assertIn('"type": "give_money"', payload)

        restored = ModProject.from_json(payload)

        self.assertEqual(restored, self.project)
        self.assertEqual(restored.name, "Тестовый сюжетный мод")
        self.assertEqual(restored.required_mods, ["bas_db.sqlite"])

        restored_phrase = restored.dialogs["mymod_start_dialog"].phrases[0]
        self.assertEqual(restored_phrase.text_ru, DIALOG_TEXT_RU)
        self.assertEqual(restored_phrase.text_en, DIALOG_TEXT_EN)

        restored_quest = restored.quests["mymod_av_quest"]
        self.assertIsInstance(restored_quest.on_init_actions[0], GiveMoney)
        self.assertEqual(restored_quest.on_init_actions[0].amount, 5000)
        self.assertIsInstance(
            restored.dialogs["mymod_start_dialog"].preconditions[0],
            HasInfo,
        )

    def test_yaml_roundtrip_is_lossless(self) -> None:
        """YAML Round-trip сохраняет модель, тексты и полиморфные типы."""
        payload = self.project.to_yaml()

        self.assertIn(DIALOG_TEXT_RU, payload)
        self.assertIn(DIALOG_TEXT_EN, payload)
        self.assertIn("type: give_money", payload)

        restored = ModProject.from_yaml(payload)

        self.assertEqual(restored, self.project)
        self.assertEqual(restored.name, "Тестовый сюжетный мод")
        self.assertEqual(restored.required_mods, ["bas_db.sqlite"])

        restored_phrase = restored.dialogs["mymod_start_dialog"].phrases[0]
        self.assertEqual(restored_phrase.text_ru, DIALOG_TEXT_RU)
        self.assertEqual(restored_phrase.text_en, DIALOG_TEXT_EN)

        restored_quest = restored.quests["mymod_av_quest"]
        self.assertIsInstance(restored_quest.on_init_actions[0], GiveMoney)
        self.assertEqual(restored_quest.on_init_actions[0].amount, 5000)
        self.assertIsInstance(
            restored.dialogs["mymod_start_dialog"].preconditions[0],
            HasInfo,
        )


class TestStalkerMetadataFields(unittest.TestCase):
    """Проверка новых полей привязки NPC/диалога и ``extra='allow'``."""

    def test_quest_metadata_is_coerced_and_normalized(self) -> None:
        """Числовые ID становятся строками, пустые — ``None``."""
        quest = Quest.model_validate(
            {
                "id": 42,
                "npc_id": 7,
                "giver_npc_id": 0,
                "npc_location": "  escape  ",
                "dialog_id": 100,
                "title_ru": "Тест",
                "title_en": "Test",
                "stages": {"0": {"id": 0}},
            }
        )

        self.assertEqual(quest.id, "42")
        self.assertEqual(quest.npc_id, "7")
        self.assertIsNone(quest.giver_npc_id)
        self.assertEqual(quest.npc_location, "escape")
        self.assertEqual(quest.dialog_id, "100")
        self.assertEqual(quest.stages[0].id, 0)

    def test_dialog_metadata_and_id_sync(self) -> None:
        """``Dialog.dialog_id`` синхронизируется с ``id``."""
        dialog = Dialog.model_validate(
            {
                "id": 55,
                "npc_id": 0,
                "npc_location": "zaton",
                "task_id": 42,
                "role": "turnin",
                "phrases": {"0": {"id": 0, "text_ru": "Да"}},
            }
        )

        self.assertEqual(dialog.id, "55")
        self.assertEqual(dialog.dialog_id, "55")
        self.assertIsNone(dialog.npc_id)
        self.assertEqual(dialog.npc_location, "zaton")
        self.assertEqual(dialog.task_id, "42")
        self.assertEqual(dialog.role, "turnin")

    def test_unknown_sqlite_columns_survive_roundtrip(self) -> None:
        """Неизвестные колонки остаются в ``model_extra``."""
        quest = Quest.model_validate(
            {
                "id": "q",
                "sqlite_rowid": 17,
                "legacy_note": "keep me",
                "stages": {"0": {"id": 0}},
            }
        )

        self.assertEqual(quest.model_extra["sqlite_rowid"], 17)
        self.assertEqual(quest.model_extra["legacy_note"], "keep me")

        restored = Quest.model_validate_json(quest.model_dump_json())
        self.assertEqual(restored.model_extra["sqlite_rowid"], 17)
        self.assertEqual(
            restored.model_extra["legacy_note"], "keep me"
        )

    def test_transfer_conditions_are_typed(self) -> None:
        """Правила перехода этапов разбираются в типизированные условия."""
        quest = Quest.model_validate(
            {
                "id": "q",
                "stages": {"0": {"id": 0}},
                "transfer_conditions": {
                    "0": {
                        "complete": [
                            {"type": "has_info", "info": "done"}
                        ],
                        "fail": [
                            {
                                "type": "dont_has_info",
                                "info": "alive",
                            }
                        ],
                    }
                },
            }
        )

        rule = quest.transfer_conditions[0]
        self.assertIsInstance(rule["complete"][0], HasInfo)
        self.assertIsInstance(rule["fail"][0], DontHasInfo)
        self.assertEqual(rule["complete"][0].info, "done")


class TestTraderActionsAndConditions(unittest.TestCase):
    """Проверка новых действий/условий и поля ``target_squad_id``."""

    def test_new_actions_are_polymorphic(self) -> None:
        """``TakeItem`` и ``TakeMoney`` входят в общий ``Action`` union."""
        adapter = TypeAdapter(Action)
        take_item = adapter.validate_python(
            {"type": "take_item", "item_alias": "itm_pda_common", "count": 3}
        )
        take_money = adapter.validate_python(
            {"type": "take_money", "amount": 2500}
        )

        self.assertIsInstance(take_item, TakeItem)
        self.assertEqual(take_item.count, 3)
        self.assertIsInstance(take_money, TakeMoney)
        self.assertEqual(take_money.amount, 2500)

    def test_new_conditions_are_polymorphic(self) -> None:
        """``HasItem(count)`` и ``HasMoney`` входят в ``Condition`` union."""
        adapter = TypeAdapter(Condition)
        has_item = adapter.validate_python(
            {"type": "has_item", "item_alias": "wpn_ak105", "count": 2}
        )
        has_money = adapter.validate_python(
            {"type": "has_money", "amount": 50000}
        )

        self.assertIsInstance(has_item, HasItem)
        self.assertEqual(has_item.count, 2)
        self.assertIsInstance(has_money, HasMoney)
        self.assertEqual(has_money.amount, 50000)

    def test_has_item_defaults_to_one_and_rejects_zero(self) -> None:
        """Количество по умолчанию — 1; ``count=0`` недопустим."""
        self.assertEqual(HasItem(item_alias="x").count, 1)
        self.assertEqual(TakeItem(item_alias="x").count, 1)
        with self.assertRaises(ValidationError):
            HasItem(item_alias="x", count=0)
        with self.assertRaises(ValidationError):
            TakeItem(item_alias="x", count=0)

    def test_stage_accepts_target_squad_id(self) -> None:
        """Этап хранит ID/секцию целевого отряда."""
        stage = Stage(
            id=0,
            target_squad_id="esc_3_16_military_trader_squad",
        )
        self.assertEqual(
            stage.target_squad_id, "esc_3_16_military_trader_squad"
        )


class TestPhraseActionModes(unittest.TestCase):
    """Проверка слияния действий реплики в один ``<action>``."""

    def test_single_actions_keep_dedicated_effects(self) -> None:
        """Одиночные ``GiveTask``/``CompleteTask`` идут в ``_accept``/``_turn_in``."""
        self.assertEqual(
            phrase_action_mode([GiveTask(task_id="q")]), "accept"
        )
        self.assertEqual(
            phrase_action_mode([CompleteTask(task_id="q")]), "turn_in"
        )
        self.assertIsNone(phrase_action_mode([GiveInfo(info="i")]))
        self.assertIsNone(phrase_action_mode([]))

    def test_mixed_actions_require_combined_function(self) -> None:
        """Награда рядом с ``CompleteTask`` требует единой ``_action``."""
        mode = phrase_action_mode(
            [
                GiveItem(item_alias="itm_pda_common"),
                CompleteTask(task_id="q"),
            ]
        )
        self.assertEqual(mode, "combined")

    def test_reward_conflict_is_reported(self) -> None:
        """Реплика сдачи с наградой и пустым ``reward_*`` даёт предупреждение."""
        quest = Quest(
            id="reward_quest",
            npc_id="esc_mayor",
            stages={0: Stage(id=0)},
        )
        dialog = Dialog(
            id="reward_dialog",
            task_id=quest.id,
            phrases={
                0: Phrase(
                    id=0,
                    actions=[
                        GiveMoney(amount=10000),
                        GiveItem(item_alias="wpn_vssk"),
                        CompleteTask(task_id=quest.id),
                    ],
                )
            },
        )
        project = ModProject(
            name="Reward",
            quests={quest.id: quest},
            dialogs={dialog.id: dialog},
        )

        conflicts = find_phrase_reward_conflicts(project)
        self.assertEqual(len(conflicts), 1)
        self.assertIn("reward_dialog", conflicts[0])
        self.assertIn("GiveMoney", conflicts[0])
        self.assertIn("GiveItem", conflicts[0])

        quest.reward_money = 10000
        self.assertEqual(find_phrase_reward_conflicts(project), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
