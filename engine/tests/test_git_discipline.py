# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Git discipline, enforced: descent, base-branch purity, branch ownership,
merge direction, and the commit-subject convention (audit D07)."""
import unittest

import _payloads as PL
from _live import Live
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
        self.live.branch_at(f"plan/{self.plan}",
                            base=self.live.git("rev-list", "--max-parents=0",
                                               "HEAD"))
        sha = self.live.git("rev-parse", "HEAD")
        with self.assertRaises(Rejection) as err:
            ingest(self.init, PL.merge(plan=self.plan, sha=sha))
        self.assertEqual(err.exception.code, "merge_not_descendant")

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


if __name__ == "__main__":
    unittest.main()
