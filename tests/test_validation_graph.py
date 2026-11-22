"""Юнит-тесты графового кросс-валидатора ``GRAPH-*``."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

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
    RemoveItem,
    SpawnNpcItem,
    Stage,
    TakeMoney,
)
from src.validation.graph_validator import GraphIndex, GraphValidator
from src.validation.report import Severity, ValidationReport

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = PROJECT_ROOT / "examples"


def load_example(name: str):
    """Загружает эталонный example-модуль по пути."""
    path = EXAMPLES / name
    module_name = f"_graph_test_{name.replace('.', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Не удалось загрузить {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def make_project(
    *,
    quest_id: str = "test_quest",
    stages: dict[int, Stage] | None = None,
    reward_money: int | None = 100,
    with_turnin: bool = True,
    take_preconditions=None,
    turnin_preconditions=None,
    turnin_actions=None,
    transfer_conditions=None,
    on_init_actions=None,
    on_fail_actions=None,
    on_complete_actions=None,
    cleanup_infos=None,
    available_info: str | None = None,
    is_storyline: bool = True,
) -> ModProject:
    """Собирает минимальный валидный проект для проверки одного правила."""
    taken = f"{quest_id}_taken"
    done = f"{quest_id}_done"
    if stages is None:
        stages = {0: Stage(id=0, title_ru="Этап")}

    take_id = f"{quest_id}_take"
    turnin_id = f"{quest_id}_turnin"

    take_preconditions = (
        [DontHasInfo(info=taken)]
        if take_preconditions is None
        else take_preconditions
    )
    take = Dialog(
        id=take_id,
        task_id=quest_id,
        role="take",
        npc_id="npc_giver",
        npc_location="escape",
        preconditions=take_preconditions,
        phrases={
            0: Phrase(
                id=0,
                actions=[
                    GiveInfo(info=taken),
                    GiveTask(task_id=quest_id),
                ],
            )
        },
    )
    dialogs = {take_id: take}
    dialog_ids = [take_id]

    if with_turnin:
        turnin_preconditions = (
            [HasInfo(info=taken), DontHasInfo(info=done)]
            if turnin_preconditions is None
            else turnin_preconditions
        )
        turnin_actions = (
            [CompleteTask(task_id=quest_id)]
            if turnin_actions is None
            else turnin_actions
        )
        dialogs[turnin_id] = Dialog(
            id=turnin_id,
            task_id=quest_id,
            role="turnin",
            npc_id="npc_giver",
            npc_location="escape",
            preconditions=turnin_preconditions,
            phrases={0: Phrase(id=0, actions=turnin_actions)},
        )
        dialog_ids.append(turnin_id)

    quest = Quest(
        id=quest_id,
        npc_id="npc_giver",
        npc_location="escape",
        dialog_id=take_id,
        dialog_ids=dialog_ids,
        stages=stages,
        taken_info=taken,
        complete_info=done,
        reward_money=reward_money,
        transfer_conditions=transfer_conditions or {},
        on_init_actions=on_init_actions or [],
        on_fail_actions=on_fail_actions or [],
        on_complete_actions=on_complete_actions or [],
        cleanup_infos=cleanup_infos or [],
        available_info=available_info,
        is_storyline=is_storyline,
    )
    return ModProject(
        name="Graph Test",
        quests={quest_id: quest},
        dialogs=dialogs,
    )


def run_validator(project: ModProject) -> tuple[ValidationReport, GraphIndex]:
    report = ValidationReport()
    index = GraphValidator(report).validate(project)
    return report, index


def codes(report: ValidationReport) -> set[str]:
    return {issue.code for issue in report.issues}


def issues_with(report: ValidationReport, code: str):
    return [issue for issue in report.issues if issue.code == code]


class ReferenceProjectTests(unittest.TestCase):
    """Оба эталона обязаны проходить без ERROR."""

    def test_story_relay_has_no_errors(self) -> None:
        module = load_example("build_story_relay.py")
        project = module.build_project()
        report, index = run_validator(project)
        self.assertFalse(
            report.has_errors,
            msg="\n".join(
                f"{issue.code}: {issue.message}"
                for issue in report.errors
            ),
        )
        self.assertTrue(index.nodes)
        self.assertTrue(index.edges)

    def test_golden_test_has_no_errors(self) -> None:
        module = load_example("build_golden_test.py")
        project = module.create_golden_shield_project()
        report, index = run_validator(project)
        self.assertFalse(
            report.has_errors,
            msg="\n".join(
                f"{issue.code}: {issue.message}"
                for issue in report.errors
            ),
        )
        self.assertTrue(index.nodes)
        self.assertTrue(index.edges)


class InfoRuleTests(unittest.TestCase):
    def test_orphan_has_info_is_error(self) -> None:
        project = make_project(
            turnin_preconditions=[
                HasInfo(info="missing_info"),
            ]
        )
        report, _ = run_validator(project)
        orphan = issues_with(report, "GRAPH-INFO-001")
        self.assertTrue(
            any(issue.severity == Severity.ERROR for issue in orphan)
        )

    def test_orphan_dont_has_info_is_only_info(self) -> None:
        project = make_project(
            turnin_preconditions=[DontHasInfo(info="missing_info")]
        )
        report, _ = run_validator(project)
        orphan = issues_with(report, "GRAPH-INFO-001")
        self.assertTrue(orphan)
        self.assertTrue(
            all(issue.severity == Severity.INFO for issue in orphan)
        )

    def test_contradiction_has_and_dont_has(self) -> None:
        project = make_project(
            turnin_preconditions=[
                HasInfo(info="test_quest_taken"),
                DontHasInfo(info="test_quest_taken"),
            ]
        )
        report, _ = run_validator(project)
        self.assertIn("GRAPH-CONTRADICTION-001", codes(report))
        self.assertTrue(
            any(
                issue.severity == Severity.ERROR
                for issue in issues_with(
                    report, "GRAPH-CONTRADICTION-001"
                )
            )
        )

    def test_dead_give_info_is_warning(self) -> None:
        project = make_project(
            on_init_actions=[GiveInfo(info="unused_info")]
        )
        report, _ = run_validator(project)
        dead = issues_with(report, "GRAPH-INFO-002")
        self.assertTrue(dead)
        self.assertTrue(
            all(issue.severity == Severity.WARNING for issue in dead)
        )


class ItemMoneyRuleTests(unittest.TestCase):
    def test_remove_item_without_has_item(self) -> None:
        project = make_project(
            turnin_actions=[
                RemoveItem(item_alias="itm_test", count=1),
                CompleteTask(task_id="test_quest"),
            ]
        )
        report, _ = run_validator(project)
        issues = issues_with(report, "GRAPH-ITEM-001")
        self.assertTrue(issues)
        self.assertTrue(
            all(issue.severity == Severity.WARNING for issue in issues)
        )

    def test_remove_item_count_mismatch(self) -> None:
        project = make_project(
            turnin_preconditions=[
                HasInfo(info="test_quest_taken"),
                HasItem(item_alias="itm_test", count=1),
            ],
            turnin_actions=[
                RemoveItem(item_alias="itm_test", count=2),
                CompleteTask(task_id="test_quest"),
            ],
        )
        report, _ = run_validator(project)
        self.assertIn("GRAPH-ITEM-002", codes(report))

    def test_take_money_without_has_money(self) -> None:
        project = make_project(
            turnin_actions=[
                TakeMoney(amount=100),
                CompleteTask(task_id="test_quest"),
            ]
        )
        report, _ = run_validator(project)
        issues = issues_with(report, "GRAPH-MONEY-001")
        self.assertTrue(issues)
        self.assertTrue(
            all(issue.severity == Severity.WARNING for issue in issues)
        )


class QuestRuleTests(unittest.TestCase):
    def test_unreachable_quest_is_error(self) -> None:
        quest = Quest(
            id="lonely_quest",
            stages={0: Stage(id=0)},
            return_to_giver_stage=0,
            reward_money=100,
        )
        project = ModProject(
            name="Graph Test",
            quests={"lonely_quest": quest},
        )
        report, _ = run_validator(project)
        self.assertIn("GRAPH-QUEST-001", codes(report))

    def test_quest_cycle_is_error(self) -> None:
        first = make_project(
            quest_id="cycle_a",
            on_complete_actions=[GiveTask(task_id="cycle_b")],
        )
        second = make_project(
            quest_id="cycle_b",
            on_complete_actions=[GiveTask(task_id="cycle_a")],
        )
        project = ModProject(
            name="Graph Test",
            quests={**first.quests, **second.quests},
            dialogs={**first.dialogs, **second.dialogs},
        )
        report, _ = run_validator(project)
        self.assertIn("GRAPH-QUEST-002", codes(report))

    def test_unknown_give_task_is_broken_edge(self) -> None:
        project = make_project()
        project.dialogs["broken_edge_dialog"] = Dialog(
            id="broken_edge_dialog",
            npc_id="npc_giver",
            phrases={
                0: Phrase(
                    id=0,
                    actions=[GiveTask(task_id="missing_quest")],
                )
            },
        )
        report, _ = run_validator(project)
        self.assertIn("GRAPH-EDGE-001", codes(report))


class StageRuleTests(unittest.TestCase):
    def test_stuck_final_stage_without_completion(self) -> None:
        project = make_project(with_turnin=False)
        report, _ = run_validator(project)
        self.assertIn("GRAPH-STAGE-002", codes(report))
        self.assertTrue(
            any(
                issue.severity == Severity.ERROR
                for issue in issues_with(report, "GRAPH-STAGE-002")
            )
        )

    def test_non_final_stage_without_exit(self) -> None:
        project = make_project(
            stages={0: Stage(id=0), 1: Stage(id=1)},
        )
        report, _ = run_validator(project)
        self.assertIn("GRAPH-STAGE-001", codes(report))

    def test_premature_last_stage_transfer(self) -> None:
        project = make_project(
            transfer_conditions={
                0: {"complete": [HasInfo(info="test_quest_taken")]},
            },
        )
        report, _ = run_validator(project)
        self.assertIn("GRAPH-STAGE-004", codes(report))
        self.assertTrue(
            any(
                issue.severity == Severity.ERROR
                for issue in issues_with(report, "GRAPH-STAGE-004")
            )
        )

    def test_transfer_references_missing_stage(self) -> None:
        project = make_project(
            transfer_conditions={
                5: {"complete": [HasInfo(info="test_quest_taken")]},
            },
        )
        report, _ = run_validator(project)
        self.assertIn("GRAPH-STAGE-003", codes(report))


class RewardAndCleanupRuleTests(unittest.TestCase):
    def test_reward_in_phrase_with_empty_reward_fields(self) -> None:
        project = make_project(
            reward_money=None,
            turnin_actions=[
                GiveMoney(amount=5000),
                CompleteTask(task_id="test_quest"),
            ],
        )
        report, _ = run_validator(project)
        issues = issues_with(report, "GRAPH-REWARD-001")
        self.assertTrue(issues)
        self.assertTrue(
            all(issue.severity == Severity.ERROR for issue in issues)
        )

    def test_quest_item_without_fail_cleanup(self) -> None:
        project = make_project(
            stages={
                0: Stage(
                    id=0,
                    on_start_actions=[
                        GiveItem(item_alias="itm_quest", count=1)
                    ],
                ),
                1: Stage(id=1),
            },
            transfer_conditions={
                0: {
                    "complete": [
                        HasItem(item_alias="itm_quest", count=1)
                    ]
                }
            },
            on_fail_actions=[],
        )
        report, _ = run_validator(project)
        issues = issues_with(report, "GRAPH-CLEAN-001")
        self.assertTrue(issues)
        self.assertTrue(
            all(issue.severity == Severity.ERROR for issue in issues)
        )

    def test_spawn_npc_item_with_cleanup_is_allowed(self) -> None:
        project = make_project(
            stages={
                0: Stage(
                    id=0,
                    on_start_actions=[
                        SpawnNpcItem(
                            item_alias="itm_quest",
                            target_alias="test_squad",
                            count=1,
                        )
                    ],
                ),
                1: Stage(id=1),
            },
            transfer_conditions={
                0: {
                    "complete": [
                        HasItem(item_alias="itm_quest", count=1)
                    ]
                }
            },
            on_fail_actions=[
                RemoveItem(item_alias="itm_quest", count=1)
            ],
        )
        report, _ = run_validator(project)
        self.assertNotIn("GRAPH-CLEAN-001", codes(report))


class DeathAndCycleRuleTests(unittest.TestCase):
    def test_death_info_without_spawn(self) -> None:
        project = make_project(
            stages={0: Stage(id=0), 1: Stage(id=1)},
            transfer_conditions={
                0: {"complete": [HasInfo(info="dead_info")]},
            },
        )
        project.squads = {
            "dead_squad": CustomSquad(
                id="dead_squad",
                faction="bandit",
                npc=["sim_default_bandit_1"],
                death_infos=["dead_info"],
            )
        }
        report, _ = run_validator(project)
        issues = issues_with(report, "GRAPH-DEATH-001")
        self.assertTrue(issues)
        self.assertTrue(
            all(issue.severity == Severity.ERROR for issue in issues)
        )

    def test_phrase_cycle_without_action_is_warning(self) -> None:
        project = make_project()
        project.dialogs["loop_dialog"] = Dialog(
            id="loop_dialog",
            npc_id="npc_giver",
            phrases={
                0: Phrase(id=0, next_phrases=[1]),
                1: Phrase(id=1, next_phrases=[0]),
            },
        )
        report, _ = run_validator(project)
        issues = issues_with(report, "GRAPH-CYCLE-001")
        self.assertTrue(issues)
        self.assertTrue(
            all(issue.severity == Severity.WARNING for issue in issues)
        )


class GraphIndexTests(unittest.TestCase):
    def test_export_edges_structure_and_json(self) -> None:
        project = make_project()
        index = GraphValidator(ValidationReport()).validate(project)
        data = index.export_edges()

        self.assertEqual(set(data), {"nodes", "edges"})
        self.assertTrue(data["nodes"])
        self.assertTrue(data["edges"])
        for node in data["nodes"]:
            self.assertEqual(set(node), {"id", "type", "label"})
            self.assertIn(node["type"], {"quest", "dialog", "phrase", "stage"})
        for edge in data["edges"]:
            self.assertEqual(
                set(edge), {"source", "target", "kind", "owner", "label"}
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "graph.json"
            exported = index.export_edges(path)
            self.assertTrue(path.is_file())
            on_disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk, exported)
            self.assertEqual(exported, data)


if __name__ == "__main__":
    unittest.main()
