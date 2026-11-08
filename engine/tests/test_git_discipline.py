# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Git discipline, enforced: descent, base-branch purity, branch ownership,
merge direction, and the commit-subject convention (audit D07)."""
import unittest

import _payloads as PL
from _live import Live
import executor.engine as E
from executor.engine import fold, ingest
from executor.paths import prompt_file
from executor.store import Rejection, append_event, make_event


class Rules(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init
        # one commit before the dispatch, so the dispatch base is never the
        # repository root and a sibling branch really can diverge from it
        self.live.land_change()
        self.act = self.live.run(
            lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")
        self.task = self.act["entity"]
        self.base = self.act["base"]

    def report(self, sha: str, **kw) -> None:
        ingest(self.init, PL.report(task=self.task, commits=(sha,), **kw))

    def refuse(self, code: str, sha: str, **kw) -> None:
        with self.assertRaises(Rejection) as err:
            self.report(sha, **kw)
        self.assertEqual(err.exception.code, code)

    def root_commit(self) -> str:
        return self.live.git("rev-list", "--max-parents=0", "HEAD")

    def test_a_commit_that_does_not_descend_from_the_base_is_refused(self):
        """The hole this closes: a sibling branch that never contained the
        dispatch base used to satisfy 'the work advanced'."""
        self.live.branch_at("side/x", base=self.root_commit())
        sha = self.live.land_change()
        self.refuse("not_descendant", sha)

    def test_a_commit_on_the_integration_branch_is_refused(self):
        sha = self.live.land_change()          # HEAD is still the dispatch branch
        self.refuse("commit_on_base", sha)

    def test_a_commit_without_its_task_branch_is_refused(self):
        self.live.branch_at("feature/x", base=self.base)
        sha = self.live.land_change()
        self.refuse("branch_mismatch", sha)

    def test_naming_the_wrong_branch_is_refused(self):
        sha = self.live.land_change(f"task/{self.task}")
        self.refuse("branch_mismatch", sha, branch="side/x")

    def test_a_non_conventional_subject_is_refused(self):
        self.live.branch_at(f"task/{self.task}", base=self.base)
        (self.live.root / "x.txt").write_text("x", encoding="utf-8")
        self.live.git("add", "-A")
        self.live.git("commit", "-q", "-m", "change 1")
        sha = self.live.git("rev-parse", "HEAD")
        self.refuse("bad_commit_message", sha)

    def test_the_cooperative_branch_and_subject_are_accepted(self):
        sha = self.live.land_change(f"task/{self.task}")
        self.report(sha, branch=f"task/{self.task}")
        self.assertEqual(fold(self.init.events)["tasks"][self.task]["state"],
                         "reported")

    def test_a_dispatch_minted_before_this_engine_is_exempt(self):
        """An upgrade must not reject the work it inherited: a dispatch with no
        rules marker is judged by the rules it was asked under."""
        # The fold reads a dispatch from its latest task_dispatched record, so
        # re-recording the open dispatch without a rules marker is exactly the
        # pre-upgrade state: a dispatch whose rules were never written.
        ctx = {k: v for k, v in self.act["context"].items() if k != "rules"}
        ev = make_event(self.init.idir, "engine", "task_dispatched",
                        self.act["entity"],
                        {"role": "impl", "schema": "report",
                         "respond_to": self.act["respond_to"],
                         "base": self.base, "context": ctx},
                        dispatch_id=self.act["dispatch_id"])
        append_event(self.init.idir, ev)
        self.init.events.append(ev)
        self.live.branch_at("side/x", base=self.root_commit())
        sha = self.live.land_change()
        self.report(sha)                       # accepted: no marker, no rules
        self.assertIn(self.act["dispatch_id"], fold(self.init.events)["answered"])


class Merge(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init
        act = self.live.run(lambda a: a["action"] == "MERGE")
        self.plan = act["plan"]

    def test_a_merge_that_does_not_contain_a_task_head_is_refused(self):
        branch = f"initiative/{self.init.id}"
        self.live.branch_at(branch,
                            base=self.live.git("rev-list", "--max-parents=0",
                                               "HEAD"))
        sha = self.live.git("rev-parse", "HEAD")
        with self.assertRaises(Rejection) as err:
            ingest(self.init, PL.merge(plan=self.plan, sha=sha, branch=branch))
        self.assertEqual(err.exception.code, "merge_not_descendant")
    def test_a_plan_merged_only_onto_its_own_branch_is_refused(self):
        """The fault this closes: the plan merged onto `plan/<PLAN>` and never
        reached the initiative. The refusal must say where it belongs."""
        self.live.branch_at(f"plan/{self.plan}")
        sha = self.live.git("rev-parse", "HEAD")
        with self.assertRaises(Rejection) as err:
            ingest(self.init, PL.merge(plan=self.plan, sha=sha,
                                       branch=f"plan/{self.plan}"))
        self.assertEqual(err.exception.code, "merge_branch_mismatch")
        self.assertIn(f"initiative/{self.init.id}", err.exception.hint)

    def test_a_plan_merged_onto_the_initiative_branch_is_accepted(self):
        self.live.branch_at(f"initiative/{self.init.id}")
        sha = self.live.git("rev-parse", "HEAD")
        ingest(self.init, PL.merge(plan=self.plan, sha=sha,
                                   branch=f"initiative/{self.init.id}"))
        self.assertEqual(fold(self.init.events)["plans"][self.plan]["status"], "merged")

    def test_a_merge_naming_a_branch_it_is_not_on_is_refused(self):
        self.live.branch_at(f"plan/{self.plan}")
        sha = self.live.git("rev-parse", "HEAD")
        with self.assertRaises(Rejection) as err:
            ingest(self.init, PL.merge(plan=self.plan, sha=sha,
                                       branch=f"initiative/{self.init.id}"))
        self.assertEqual(err.exception.code, "merge_branch_mismatch")

    def test_a_merge_on_another_branch_name_is_refused(self):
        sha = self.live.git("rev-parse", "HEAD")
        with self.assertRaises(Rejection) as err:
            ingest(self.init, PL.merge(plan=self.plan, sha=sha,
                                       branch="side/x"))
        self.assertEqual(err.exception.code, "merge_branch_mismatch")


class PromptCarriesTheRule(unittest.TestCase):
    def test_a_dispatch_prompt_names_the_rules_it_is_minted_under(self):
        live = Live()
        self.addCleanup(live.close)
        act = live.run(lambda a: a["action"] == "DISPATCH")
        text = prompt_file(live.init.idir, act["dispatch_id"]).read_text(
            encoding="utf-8")
        self.assertIn(f"rules: {act['context']['rules']}", text)


class PlanBase(unittest.TestCase):
    """Every implementation of a plan starts from the plan branch tip. The
    checked-out branch is never the base: that was how one plan acquired thirteen
    different bases."""

    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.live.land_change()

    def test_the_first_implementation_starts_from_the_plan_branch_tip(self):
        act = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")
        plan = fold(self.live.init.events)["tasks"][act["entity"]]["plan"]
        self.assertEqual(act["base"], self.live.git("rev-parse", f"plan/{plan}"))

    def test_a_missing_plan_branch_refuses_the_dispatch_instead_of_using_head(self):
        """The fault this closes: with no plan branch, the engine used to take
        whatever HEAD was. It must refuse, naming the branch to create."""
        with self.assertRaises(Rejection) as err:
            self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl",
                          provision=False)
        self.assertEqual(err.exception.code, "missing_plan_branch")


class PlanDocs(unittest.TestCase):
    """A plan is cut after its documents are committed on the initiative line."""

    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.head = self.live.git("rev-parse", "HEAD")
        self.plan = f"{self.live.init.id}-P01"

    def test_refused_before_the_initiative_branch_exists(self):
        with self.assertRaises(Rejection) as err:
            E._require_plan_docs(self.live.init, self.plan, self.head)
        self.assertEqual(err.exception.code, "initiative_branch_missing")

    def test_refused_when_no_plan_document_was_ever_committed(self):
        self.live.git("branch", f"initiative/{self.live.init.id}", "HEAD")
        with self.assertRaises(Rejection) as err:
            E._require_plan_docs(self.live.init, self.plan, self.head)
        self.assertEqual(err.exception.code, "projections_uncommitted")

    def test_accepted_once_the_documents_are_committed(self):
        self.live.git("branch", f"initiative/{self.live.init.id}", "HEAD")
        E._project(self.live.init)
        self.live._docs_commit(f"initiative/{self.live.init.id}", "docs: plan")
        plan = fold(self.live.init.events)["plan_order"]
        if plan:
            E._require_plan_docs(self.live.init, plan[0], self.head)

    def test_a_missing_initiative_branch_has_no_documents(self):
        self.assertEqual(
            E._plan_docs_commit(self.live.root, self.live.init.id, self.plan), "")


class Dependencies(unittest.TestCase):
    """A base that lacks a dependency's head cannot start the dependent task."""

    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)

    def test_a_head_outside_the_base_is_reported(self):
        base = self.live.git("rev-parse", "HEAD")
        head = self.live.land_change()
        self.assertEqual(E._deps_in_base(self.live.root, {"T1": head}, base), ["T1"])

    def test_a_head_inside_the_base_is_accepted(self):
        head = self.live.land_change()
        self.assertEqual(E._deps_in_base(self.live.root, {"T1": head}, head), [])

    def test_a_dependent_task_refuses_a_base_without_its_dependency(self):
        base = self.live.git("rev-parse", "HEAD")
        head = self.live.land_change()
        s = {"tasks": {"T2": {"plan": "INIT-0001-P01", "depends_on": ["T1"]}},
             "reports": {"INIT-0001-P01-T1": {"commits": [head]}}}
        with self.assertRaises(Rejection) as err:
            E._require_dependencies(self.live.init, s, "T2", base)
        self.assertEqual(err.exception.code, "dependency_not_contained")

    def test_a_task_without_dependencies_is_unaffected(self):
        s = {"tasks": {"T2": {"plan": "INIT-0001-P01", "depends_on": []}},
             "reports": {}}
        E._require_dependencies(self.live.init, s, "T2",
                                self.live.git("rev-parse", "HEAD"))

    def test_a_dependency_that_has_not_reported_is_not_checked(self):
        s = {"tasks": {"T2": {"plan": "INIT-0001-P01", "depends_on": ["T9"]}},
             "reports": {}}
        E._require_dependencies(self.live.init, s, "T2",
                                self.live.git("rev-parse", "HEAD"))


class Integration(unittest.TestCase):
    """Handoff must not sign off work that never reached the initiative line."""

    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.head = self.live.git("rev-parse", "HEAD")
        self.plan = f"{self.live.init.id}-P01"

    def test_an_unmerged_plan_blocks_handoff(self):
        s = {"plans": {self.plan: {"status": "planned", "merge_sha": ""}}}
        with self.assertRaises(Rejection) as err:
            E._require_integration_complete(self.live.init, s)
        self.assertEqual(err.exception.code, "integration_incomplete")

    def test_a_merge_contained_in_the_initiative_branch_is_accepted(self):
        self.live.git("branch", f"initiative/{self.live.init.id}", self.head)
        s = {"plans": {self.plan: {"status": "merged", "merge_sha": self.head}}}
        E._require_integration_complete(self.live.init, s)

    def test_a_merge_outside_the_initiative_branch_is_reported(self):
        self.live.git("branch", f"initiative/{self.live.init.id}", self.head)
        elsewhere = self.live.land_change()
        s = {"plans": {self.plan: {"status": "merged", "merge_sha": elsewhere}}}
        with self.assertRaises(Rejection) as err:
            E._require_integration_complete(self.live.init, s)
        self.assertEqual(err.exception.code, "integration_incomplete")


if __name__ == "__main__":
    unittest.main()
