# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""paths.py is the one naming authority.

These tests pin the layout as a literal contract (every helper, its exact
path), prove every file helper's output classifies under the grammar, and
prove the grammar rejects drift: stray directories, mis-nested ids, the old
verbose dispatch ids, atomic-write residue.
"""
from __future__ import annotations

import dataclasses
import inspect
import re
import sys
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from executor import paths as P  # noqa: E402

ROOT = PurePosixPath("/repo")
INIT, ART = "INIT-0007", "INIT-0007-CHTR-01"
PLAN, TASK, DID = "INIT-0007-P03", "INIT-0007-P03-T02", "D00042"
IDIR = P.init_dir(ROOT, INIT)
RUN, DOCS = ROOT / ".executor", ROOT / "docs" / "executor"

R = f".executor/{INIT}"
D = f"docs/executor/{INIT}"
PD = f"{R}/plans/{PLAN}"
TD = f"{PD}/tasks/{TASK}"
DD = f"{D}/plans/{PLAN}/tasks/{TASK}"

# helper name -> (call, expected path relative to the repo root,
#                 None for a directory | (store, kind, ids) for a file)
SPEC = {
    "run_root": (lambda: P.run_root(ROOT), ".executor", None),
    "docs_root": (lambda: P.docs_root(ROOT), "docs/executor", None),
    "init_dir": (lambda: P.init_dir(ROOT, INIT), R, None),
    "run_meta_file": (lambda: P.run_meta_file(ROOT), ".executor/meta.json",
                      ("run", "run_meta", {})),
    "journal_dir": (lambda: P.journal_dir(IDIR), f"{R}/journal", None),
    "journal_file": (lambda: P.journal_file(IDIR),
                     f"{R}/journal/events.v1.jsonl",
                     ("run", "journal", {"init": INIT, "ver": "1"})),
    "state_file": (lambda: P.state_file(IDIR), f"{R}/journal/state.json",
                   ("run", "state", {"init": INIT})),
    "lock_file": (lambda: P.lock_file(IDIR), f"{R}/journal/.lock",
                  ("run", "lock", {"init": INIT})),
    "meta_dir": (lambda: P.meta_dir(IDIR), f"{R}/meta", None),
    "meta_file": (lambda: P.meta_file(IDIR), f"{R}/meta/meta.json",
                  ("run", "init_meta", {"init": INIT})),
    "autonomy_file": (lambda: P.autonomy_file(IDIR),
                      f"{R}/meta/autonomy.json",
                      ("run", "autonomy", {"init": INIT})),
    "artifact_dir": (lambda: P.artifact_dir(IDIR, ART),
                     f"{R}/artifacts/{ART}", None),
    "artifact_file": (lambda: P.artifact_file(IDIR, ART),
                      f"{R}/artifacts/{ART}/artifact.json",
                      ("run", "artifact", {"init": INIT, "art": ART})),
    "audit_file": (lambda: P.audit_file(IDIR, ART, 3),
                   f"{R}/artifacts/{ART}/audits/R03.audit.json",
                   ("run", "artifact_audit",
                    {"init": INIT, "art": ART, "rnd": "R03"})),
    "repair_file": (lambda: P.repair_file(IDIR, ART, 3),
                    f"{R}/artifacts/{ART}/repairs/R03.repair.json",
                    ("run", "artifact_repair",
                     {"init": INIT, "art": ART, "rnd": "R03"})),
    "plan_dir": (lambda: P.plan_dir(IDIR, PLAN), PD, None),
    "plan_file": (lambda: P.plan_file(IDIR, PLAN), f"{PD}/plan.json",
                  ("run", "plan", {"init": INIT, "plan": PLAN})),
    "preflight_file": (lambda: P.preflight_file(IDIR, PLAN),
                       f"{PD}/preflight.json",
                       ("run", "preflight", {"init": INIT, "plan": PLAN})),
    "plan_audit_file": (lambda: P.plan_audit_file(IDIR, PLAN, 3),
                        f"{PD}/audits/R03.audit.json",
                        ("run", "plan_audit",
                         {"init": INIT, "plan": PLAN, "rnd": "R03"})),
    "plan_repair_file": (lambda: P.plan_repair_file(IDIR, PLAN, 3),
                         f"{PD}/repairs/R03.repair.json",
                         ("run", "plan_repair",
                          {"init": INIT, "plan": PLAN, "rnd": "R03"})),
    "task_dir": (lambda: P.task_dir(IDIR, TASK), TD, None),
    "task_impl_report": (lambda: P.task_impl_report(IDIR, TASK, DID),
                         f"{TD}/impl/{DID}.report.json",
                         ("run", "task_report",
                          {"init": INIT, "plan": PLAN, "task": TASK,
                           "disp": DID})),
    "review_package_file": (lambda: P.review_package_file(IDIR, TASK, 2),
                            f"{TD}/reviews/R02.package.json",
                            ("run", "review_package",
                             {"init": INIT, "plan": PLAN, "task": TASK,
                              "rnd": "R02"})),
    "verdict_file": (lambda: P.verdict_file(IDIR, TASK, 2),
                     f"{TD}/reviews/R02.verdict.json",
                     ("run", "verdict",
                      {"init": INIT, "plan": PLAN, "task": TASK,
                       "rnd": "R02"})),
    "fix_package_file": (lambda: P.fix_package_file(IDIR, TASK, 2),
                         f"{TD}/fixes/R02.fix-package.json",
                         ("run", "fix_package",
                          {"init": INIT, "plan": PLAN, "task": TASK,
                           "rnd": "R02"})),
    "fix_report_file": (lambda: P.fix_report_file(IDIR, TASK, 2),
                        f"{TD}/fixes/R02.report.json",
                        ("run", "fix_report",
                         {"init": INIT, "plan": PLAN, "task": TASK,
                          "rnd": "R02"})),
    "dispatches_dir": (lambda: P.dispatches_dir(IDIR),
                       f"{R}/dispatches", None),
    "dispatch_dir": (lambda: P.dispatch_dir(IDIR, DID),
                     f"{R}/dispatches/{DID}", None),
    "slot_file": (lambda: P.slot_file(IDIR, DID),
                  f"{R}/dispatches/{DID}/slot.json",
                  ("run", "dispatch_slot", {"init": INIT, "disp": DID})),
    "prompt_file": (lambda: P.prompt_file(IDIR, DID),
                    f"{R}/dispatches/{DID}/prompt.md",
                    ("run", "dispatch_prompt", {"init": INIT, "disp": DID})),
    "payload_file": (lambda: P.payload_file(IDIR, DID),
                     f"{R}/dispatches/{DID}/payload.json",
                     ("run", "dispatch_payload",
                      {"init": INIT, "disp": DID})),
    "views_dir": (lambda: P.views_dir(IDIR), f"{R}/views", None),
    "view_file": (lambda: P.view_file(IDIR, "progress.md"),
                  f"{R}/views/progress.md",
                  ("run", "view", {"init": INIT, "name": "progress.md"})),
    "verdict_view_file": (lambda: P.verdict_view_file(IDIR, TASK, 2),
                          f"{R}/views/{TASK}-R02-verdict.md",
                          ("run", "view_verdict",
                           {"init": INIT, "task": TASK, "rnd": "R02"})),
    "docs_init_dir": (lambda: P.docs_init_dir(ROOT, INIT), D, None),
    "docs_index_file": (lambda: P.docs_index_file(ROOT, INIT),
                        f"{D}/meta/index.json",
                        ("docs", "docs_index_json", {"init": INIT})),
    "docs_index_md": (lambda: P.docs_index_md(ROOT, INIT),
                      f"{D}/meta/index.md",
                      ("docs", "docs_index_md", {"init": INIT})),
    "docs_artifact_dir": (lambda: P.docs_artifact_dir(ROOT, INIT, ART),
                          f"{D}/artifacts/{ART}", None),
    "docs_artifact_file": (lambda: P.docs_artifact_file(ROOT, INIT, ART),
                           f"{D}/artifacts/{ART}/artifact.json",
                           ("docs", "docs_artifact_json",
                            {"init": INIT, "art": ART})),
    "docs_artifact_md": (lambda: P.docs_artifact_md(ROOT, INIT, ART),
                         f"{D}/artifacts/{ART}/artifact.md",
                         ("docs", "docs_artifact_md",
                          {"init": INIT, "art": ART})),
    "docs_plan_dir": (lambda: P.docs_plan_dir(ROOT, INIT, PLAN),
                      f"{D}/plans/{PLAN}", None),
    "docs_plan_file": (lambda: P.docs_plan_file(ROOT, INIT, PLAN),
                       f"{D}/plans/{PLAN}/plan.json",
                       ("docs", "docs_plan_json",
                        {"init": INIT, "plan": PLAN})),
    "docs_plan_md": (lambda: P.docs_plan_md(ROOT, INIT, PLAN),
                     f"{D}/plans/{PLAN}/plan.md",
                     ("docs", "docs_plan_md", {"init": INIT, "plan": PLAN})),
    "docs_task_dir": (lambda: P.docs_task_dir(ROOT, INIT, TASK), DD, None),
    "docs_report_file": (lambda: P.docs_report_file(ROOT, INIT, TASK, DID),
                         f"{DD}/impl/{DID}.report.md",
                         ("docs", "docs_task_report",
                          {"init": INIT, "plan": PLAN, "task": TASK,
                           "disp": DID})),
    "docs_verdict_file": (lambda: P.docs_verdict_file(ROOT, INIT, TASK, 2),
                          f"{DD}/reviews/R02.verdict.md",
                          ("docs", "docs_task_verdict",
                           {"init": INIT, "plan": PLAN, "task": TASK,
                            "rnd": "R02"})),
    "docs_export_journal": (lambda: P.docs_export_journal(ROOT, INIT),
                            f"{D}/export/events.jsonl",
                            ("docs", "docs_export", {"init": INIT})),
    "project_policy_file": (lambda: P.project_policy_file(ROOT),
                            "docs/executor/config.json",
                            ("docs", "docs_project_policy", {})),
    "initiative_policy_file": (lambda: P.initiative_policy_file(ROOT, INIT),
                               f"{D}/meta/policy.json",
                               ("docs", "docs_initiative_policy", {"init": INIT})),
}

# Grammar utilities that are not path helpers.
NOT_HELPERS = {"classify", "dispatch_id", "is_dispatch_id",
               "artifact_pattern"}

ID_CASES = {
    "INIT_ID": (P.INIT_ID, ["INIT-0001", "INIT-9999"],
                ["INIT-001", "INIT-00001", "init-0001", "XINIT-0001",
                 "INIT-0001-", " INIT-0001"]),
    "ARTIFACT_ID": (P.ARTIFACT_ID,
                    ["INIT-0001-CHTR-01", "INIT-0001-ADR-12",
                     "INIT-0001-BRN-99"],
                    ["INIT-0001-chtr-01", "INIT-0001-CHTR-1",
                     "INIT-0001-CHTR-001", "INIT-0001-P01", "CHTR-01",
                     "INIT-0001-CHTR-01-x"]),
    "PLAN_ID": (P.PLAN_ID, ["INIT-0001-P01", "INIT-0042-P99"],
                ["INIT-0001-P1", "INIT-0001-P001", "INIT-0001-p01",
                 "INIT-0001-P01-T01"]),
    "TASK_ID": (P.TASK_ID, ["INIT-0001-P01-T01", "INIT-0003-P04-T11"],
                ["INIT-0001-P01-T1", "INIT-0001-P01-T001", "INIT-0001-T01",
                 "P01-T01", "INIT-0001-P01"]),
    "DISPATCH_ID": (P.DISPATCH_ID, ["D00001", "D00042", "D123456"],
                    ["D1", "D0001", "d00001", "D00001x",
                     "d-00001-INIT-0001-CHTR-01-charter"]),
    "ROUND_ID": (P.ROUND_ID, ["R01", "R12", "R99"],
                 ["R1", "R001", "r01", "R0a"]),
}

BAD_RUN = [
    "", ".", "INIT-0007", "INIT-0007/journal",
    "INIT-7/journal/state.json", "INIT-00007/journal/state.json",
    "init-0007/journal/state.json",
    "INIT-0007/journal/state.json.tmp",       # atomic-write residue
    "INIT-0007/journal/state.json.bak",
    "INIT-0007/journal/events.jsonl",         # journal needs a version
    "INIT-0007/journal/events.v1.json",
    "INIT-0007/notes/todo.md",                # unknown directory
    "INIT-0007/prompts/AUTHOR.prompt.md",     # INIT-0002's stray dir
    f"INIT-0007/artifacts/{ART}/notes.json",
    "INIT-0007/artifacts/INIT-0008-CHTR-01/artifact.json",   # other init
    "INIT-0007/artifacts/INIT-0007-chtr-01/artifact.json",
    "INIT-0007/artifacts/INIT-0007-CHTR-1/artifact.json",
    "INIT-0007/artifacts/INIT-0007-P03/artifact.json",       # plan id
    "INIT-0007/artifacts/INIT-0007-FOO-01/artifact.json",    # no such kind
    "INIT-0007/artifacts/INIT-0007-RSCH-01/artifact.json",
    f"INIT-0007/artifacts/{ART}/audits/R1.audit.json",
    f"INIT-0007/artifacts/{ART}/audits/R001.audit.json",
    f"INIT-0007/artifacts/{ART}/audits/r01.audit.json",
    "INIT-0007/plans/INIT-0008-P03/plan.json",
    "INIT-0007/plans/INIT-0007-P3/plan.json",
    f"INIT-0007/plans/{PLAN}/tasks/INIT-0007-P04-T02/impl/D00042.report.json",
    f"INIT-0007/plans/{PLAN}/tasks/INIT-0007-P03-T2/impl/D00042.report.json",
    f"INIT-0007/plans/{PLAN}/tasks/{TASK}/impl/d-00042.report.json",
    f"INIT-0007/plans/{PLAN}/tasks/{TASK}/impl/D42.report.json",
    f"INIT-0007/plans/{PLAN}/tasks/{TASK}/reviews/R01.verdict.md",
    f"INIT-0007/plans/{PLAN}/tasks/{TASK}/fixes/R01.fix_package.json",
    "INIT-0007/dispatches/d-00005-INIT-0007-CHTR-01-charter/slot.json",
    "INIT-0007/dispatches/D00005/extra.json",
    "INIT-0007/dispatches/D00005/nested/slot.json",
    "INIT-0007/views/notes.md",
    "INIT-0007/views/INIT-0008-P03-T02-R01-verdict.md",
    "../INIT-0007/meta/meta.json", "/INIT-0007/meta/meta.json",
    "INIT-0007//meta/meta.json", "INIT-0007/meta/Meta.json",
    "meta.json.orig",
]

BAD_DOCS = [
    "", ".", "INIT-0007", "INIT-0007/meta/index.txt",
    "INIT-0007/artifacts/INIT-0007-CHTR-01.json",       # flat, not nested
    "INIT-0007/plans/INIT-0007-P03.json",
    "INIT-0007/plans/INIT-0007-P03/plan.txt",
    f"INIT-0007/plans/{PLAN}/tasks/{TASK}/impl/d-00042.report.md",
    f"INIT-0007/plans/{PLAN}/tasks/INIT-0007-P04-T02/reviews/R01.verdict.md",
    "INIT-0007/export/events.json",
    "INIT-0008/artifacts/INIT-0007-CHTR-01/artifact.json",
    "INIT-0007/journal/events.v1.jsonl",     # a run-store file
]


class LayoutContract(unittest.TestCase):
    def test_every_helper_yields_its_documented_path(self):
        for name, (call, literal, _cls) in SPEC.items():
            with self.subTest(helper=name):
                self.assertEqual(str(call().relative_to(ROOT)), literal)

    def test_every_public_helper_has_a_spec_row_and_no_row_is_stale(self):
        public = {n for n, f in inspect.getmembers(P, inspect.isfunction)
                  if not n.startswith("_") and f.__module__ == P.__name__}
        self.assertEqual(public - NOT_HELPERS, set(SPEC))

    def test_journal_version_is_part_of_the_file_name(self):
        self.assertEqual(P.journal_file(IDIR, 2).name, "events.v2.jsonl")

    def test_task_helpers_derive_the_plan_from_the_task_id(self):
        self.assertEqual(P.task_dir(IDIR, TASK).parent.parent.name, PLAN)
        self.assertEqual(P.docs_task_dir(ROOT, INIT, TASK).parent.parent.name,
                         PLAN)


class GrammarRoundTrip(unittest.TestCase):
    def test_every_file_helper_classifies_to_its_documented_entry(self):
        for name, (call, _lit, cls) in SPEC.items():
            if cls is None:
                continue
            store, kind, ids = cls
            base = RUN if store == "run" else DOCS
            with self.subTest(helper=name):
                self.assertEqual(
                    P.classify(call().relative_to(base), store),
                    P.Entry(store, kind, ids))

    def test_directories_never_classify_as_files(self):
        for name, (call, literal, cls) in SPEC.items():
            if cls is not None:
                continue
            store = "docs" if literal.startswith("docs/") else "run"
            base = DOCS if store == "docs" else RUN
            with self.subTest(helper=name):
                self.assertIsNone(
                    P.classify(call().relative_to(base), store))

    def test_every_grammar_row_has_exactly_one_helper_and_vice_versa(self):
        from_spec = [(s, k) for _c, _l, cls in SPEC.values() if cls
                     for s, k, _ids in [cls]]
        from_grammar = [(store, kind) for store, rows in P.GRAMMAR.items()
                        for kind, _rx in rows]
        self.assertEqual(sorted(from_spec), sorted(from_grammar))
        self.assertEqual(len(set(from_grammar)), len(from_grammar))

    def test_windows_style_paths_classify_like_posix_ones(self):
        win = PureWindowsPath(f"{INIT}\\journal\\state.json")
        self.assertEqual(P.classify(win, "run"),
                         P.Entry("run", "state", {"init": INIT}))

    def test_entries_are_immutable(self):
        entry = P.classify(f"{INIT}/meta/meta.json", "run")
        assert entry is not None
        with self.assertRaises(dataclasses.FrozenInstanceError):
            entry.kind = "other"  # type: ignore[misc]

    def test_a_string_path_is_read_as_posix(self):
        self.assertEqual(P.classify(f"{INIT}/meta/autonomy.json", "run"),
                         P.Entry("run", "autonomy", {"init": INIT}))

    def test_large_journal_versions_and_dispatch_numbers_are_canonical(self):
        self.assertIsNotNone(
            P.classify(f"{INIT}/journal/events.v10.jsonl", "run"))
        self.assertIsNotNone(
            P.classify(f"{INIT}/dispatches/D123456/slot.json", "run"))

    def test_an_unknown_store_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            P.classify("meta.json", "elsewhere")


class GrammarRejectsDrift(unittest.TestCase):
    def test_run_store_rejects_every_non_canonical_path(self):
        for rel in BAD_RUN:
            with self.subTest(path=rel):
                self.assertIsNone(P.classify(rel, "run"))

    def test_docs_store_rejects_every_non_canonical_path(self):
        for rel in BAD_DOCS:
            with self.subTest(path=rel):
                self.assertIsNone(P.classify(rel, "docs"))

    def test_a_docs_index_is_not_a_run_store_file(self):
        self.assertIsNone(P.classify(f"{INIT}/meta/index.json", "run"))

    def test_nesting_is_enforced_by_back_references(self):
        # same shapes, different owners: each pair must be refused
        self.assertIsNone(P.classify(
            f"INIT-0008/plans/{PLAN}/plan.json", "run"))
        self.assertIsNone(P.classify(
            f"{INIT}/plans/{PLAN}/tasks/INIT-0007-P99-T01/impl/D00001"
            ".report.json", "run"))


class IdGrammar(unittest.TestCase):
    def test_ids_match_exactly_and_never_partially(self):
        for name, (rx, good, bad) in ID_CASES.items():
            for s in good:
                with self.subTest(id=name, value=s):
                    self.assertIsNotNone(re.fullmatch(rx, s))
            for s in bad:
                with self.subTest(id=name, value=s):
                    self.assertIsNone(re.fullmatch(rx, s))

    def test_dispatch_id_pads_to_five_digits_and_grows_past_them(self):
        self.assertEqual(P.dispatch_id(5), "D00005")
        self.assertEqual(P.dispatch_id(123456), "D123456")
        for seq in (1, 99999, 100000):
            self.assertTrue(P.is_dispatch_id(P.dispatch_id(seq)))

    def test_only_real_artifact_segments_are_artifact_ids(self):
        for seg in P.ARTIFACT_SEGMENTS.values():
            with self.subTest(segment=seg):
                self.assertIsNotNone(
                    re.fullmatch(P.ARTIFACT_ID, f"INIT-0001-{seg}-01"))
                self.assertIsNotNone(P.classify(
                    f"INIT-0001/artifacts/INIT-0001-{seg}-01/artifact.json",
                    "run"))
        for seg in ("FOO", "RSCH", "CHT", "CHTRR", "chtr"):
            with self.subTest(segment=seg):
                self.assertIsNone(
                    re.fullmatch(P.ARTIFACT_ID, f"INIT-0001-{seg}-01"))

    def test_artifact_pattern_ties_each_kind_to_its_own_segment(self):
        for kind, seg in P.ARTIFACT_SEGMENTS.items():
            rx = P.artifact_pattern(kind)
            with self.subTest(kind=kind):
                self.assertIsNotNone(re.fullmatch(rx, f"INIT-0001-{seg}-01"))
                self.assertIsNone(re.fullmatch(rx, "INIT-0001-P01"))
                for other in set(P.ARTIFACT_SEGMENTS.values()) - {seg}:
                    self.assertIsNone(
                        re.fullmatch(rx, f"INIT-0001-{other}-01"), other)
        self.assertIsNotNone(re.fullmatch(P.artifact_pattern("plan"),
                                          "INIT-0001-P01"))
        self.assertIsNone(re.fullmatch(P.artifact_pattern("plan"),
                                       "INIT-0001-CHTR-01"))

    def test_artifact_pattern_rejects_a_kind_it_does_not_know(self):
        with self.assertRaises(KeyError):
            P.artifact_pattern("research")

    def test_is_dispatch_id_rejects_the_old_verbose_form(self):
        self.assertTrue(P.is_dispatch_id("D00005"))
        for bad in ("d-00005-INIT-0001-CHTR-01-charter", "D1", "d00005", ""):
            with self.subTest(value=bad):
                self.assertFalse(P.is_dispatch_id(bad))


if __name__ == "__main__":
    unittest.main()
