# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The one path authority for the executor store.

Every file the engine reads or writes is located by a function here, and
every name it can take is defined by the grammar at the bottom of this
module: nothing else in the codebase constructs a path, and `classify`
refuses any file that does not fit. Naming is uniform: ``<ID>.<role>.<ext>``
nested under the owning entity's directory, so a store is browsable
top-down from initiative to artifact to task to round.

Identifiers
-----------
    INIT-NNNN                initiative
    INIT-NNNN-<KIND>-NN      artifact (CHTR OPTS BRN ARCH ADR IFCE DSGN SPEC
                             RISK VRFY)
    INIT-NNNN-PNN            plan
    INIT-NNNN-PNN-TNN        task, always inside its plan
    D<NNNNN>                 dispatch: the seq of the journal event minting it
    R<NN>                    round (audit, repair, review, fix)

Layout
------
    <repo>/.executor/
      meta.json                          engine/schema/store versions
      INIT-NNNN/
        journal/
          events.v<N>.jsonl              append-only hash-chained truth
          state.json                     derived fold cache
          .lock                          single-writer lock
        meta/
          meta.json                      initiative meta
          autonomy.json                  per-phase deny|gate|allow
        artifacts/<ARTIFACT-ID>/
          artifact.json                  latest validated payload
          audits/R<NN>.audit.json
          repairs/R<NN>.repair.json
        plans/<PLAN-ID>/
          plan.json                      latest validated plan payload
          preflight.json                 conflict-scan verdict
          audits/R<NN>.audit.json
          repairs/R<NN>.repair.json
          tasks/<TASK-ID>/
            impl/D<NNNNN>.report.json
            reviews/R<NN>.package.json   review package (what reviewer saw)
            reviews/R<NN>.verdict.json
            fixes/R<NN>.fix-package.json
            fixes/R<NN>.report.json
        dispatches/D<NNNNN>/
          slot.json                      minted single-use slot
          prompt.md                      rendered worker prompt
          payload.json                   the respond_to target
        views/
          progress.md  dispatches.md  summary.md  graph.json
          <TASK-ID>-R<NN>-verdict.md
    <repo>/docs/executor/INIT-NNNN/      committed thinking store
      meta/index.json + index.md
      artifacts/<ARTIFACT-ID>/artifact.json + artifact.md
      plans/<PLAN-ID>/plan.json + plan.md
      plans/<PLAN-ID>/tasks/<TASK-ID>/impl/D<NNNNN>.report.md
      plans/<PLAN-ID>/tasks/<TASK-ID>/reviews/R<NN>.verdict.md
      export/events.jsonl                durable journal snapshot (handoff)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import TypeVar

# Helpers are pure path arithmetic: they return the same flavour of path
# they are given (a Path in, a Path out), and never touch the filesystem.
_P = TypeVar("_P", bound=PurePath)

RUN_STORE = ".executor"
DOCS_STORE = "docs/executor"


# ---------------------------------------------------------------- id grammar
# One definition per identifier shape. schemas.py, the engine and the layout
# grammar below all import these; a second copy anywhere is a bug.

INIT_ID = r"INIT-\d{4}"
ARTIFACT_ID = INIT_ID + r"-[A-Z]+-\d{2}"
PLAN_ID = INIT_ID + r"-P\d{2}"
TASK_ID = PLAN_ID + r"-T\d{2}"
DISPATCH_ID = r"D\d{5,}"
ROUND_ID = r"R\d{2}"


def dispatch_id(seq: int) -> str:
    """The id of the dispatch recorded by journal event `seq`."""
    return f"D{seq:05d}"


def is_dispatch_id(text: str) -> bool:
    return re.fullmatch(DISPATCH_ID, text) is not None


# ---------------------------------------------------------------- roots

def run_root(root: _P) -> _P:
    return root / RUN_STORE


def docs_root(root: _P) -> _P:
    return root / DOCS_STORE


def init_dir(root: _P, init_id: str) -> _P:
    return run_root(root) / init_id


# ---------------------------------------------------------------- journal

def journal_dir(idir: _P) -> _P:
    return idir / "journal"


def journal_file(idir: _P, version: int = 1) -> _P:
    return journal_dir(idir) / f"events.v{version}.jsonl"


def state_file(idir: _P) -> _P:
    return journal_dir(idir) / "state.json"


def lock_file(idir: _P) -> _P:
    return journal_dir(idir) / ".lock"


# ---------------------------------------------------------------- meta

def meta_dir(idir: _P) -> _P:
    return idir / "meta"


def meta_file(idir: _P) -> _P:
    return meta_dir(idir) / "meta.json"


def autonomy_file(idir: _P) -> _P:
    return meta_dir(idir) / "autonomy.json"


def run_meta_file(root: _P) -> _P:
    return run_root(root) / "meta.json"


# ---------------------------------------------------------------- artifacts

def artifact_dir(idir: _P, aid: str) -> _P:
    return idir / "artifacts" / aid


def artifact_file(idir: _P, aid: str) -> _P:
    return artifact_dir(idir, aid) / "artifact.json"


def audit_file(idir: _P, aid: str, rnd: int) -> _P:
    return artifact_dir(idir, aid) / "audits" / f"R{rnd:02d}.audit.json"


def repair_file(idir: _P, aid: str, rnd: int) -> _P:
    return artifact_dir(idir, aid) / "repairs" / f"R{rnd:02d}.repair.json"


# ---------------------------------------------------------------- plans

def plan_dir(idir: _P, pid: str) -> _P:
    return idir / "plans" / pid


def plan_file(idir: _P, pid: str) -> _P:
    return plan_dir(idir, pid) / "plan.json"


def preflight_file(idir: _P, pid: str) -> _P:
    return plan_dir(idir, pid) / "preflight.json"


def plan_audit_file(idir: _P, pid: str, rnd: int) -> _P:
    return plan_dir(idir, pid) / "audits" / f"R{rnd:02d}.audit.json"


def plan_repair_file(idir: _P, pid: str, rnd: int) -> _P:
    return plan_dir(idir, pid) / "repairs" / f"R{rnd:02d}.repair.json"


# ---------------------------------------------------------------- tasks

def task_dir(idir: _P, tid: str) -> _P:
    pid = tid.rsplit("-", 1)[0]
    return plan_dir(idir, pid) / "tasks" / tid


def task_impl_report(idir: _P, tid: str, did: str) -> _P:
    return task_dir(idir, tid) / "impl" / f"{did}.report.json"


def review_package_file(idir: _P, tid: str, rnd: int) -> _P:
    return task_dir(idir, tid) / "reviews" / f"R{rnd:02d}.package.json"


def verdict_file(idir: _P, tid: str, rnd: int) -> _P:
    return task_dir(idir, tid) / "reviews" / f"R{rnd:02d}.verdict.json"


def fix_package_file(idir: _P, tid: str, rnd: int) -> _P:
    return task_dir(idir, tid) / "fixes" / f"R{rnd:02d}.fix-package.json"


def fix_report_file(idir: _P, tid: str, rnd: int) -> _P:
    return task_dir(idir, tid) / "fixes" / f"R{rnd:02d}.report.json"


# ---------------------------------------------------------------- dispatches

def dispatches_dir(idir: _P) -> _P:
    return idir / "dispatches"


def dispatch_dir(idir: _P, did: str) -> _P:
    return dispatches_dir(idir) / did


def slot_file(idir: _P, did: str) -> _P:
    return dispatch_dir(idir, did) / "slot.json"


def prompt_file(idir: _P, did: str) -> _P:
    return dispatch_dir(idir, did) / "prompt.md"


def payload_file(idir: _P, did: str) -> _P:
    """The respond_to target the worker writes."""
    return dispatch_dir(idir, did) / "payload.json"


# ---------------------------------------------------------------- views

def views_dir(idir: _P) -> _P:
    return idir / "views"


def view_file(idir: _P, name: str) -> _P:
    return views_dir(idir) / name


def verdict_view_file(idir: _P, tid: str, rnd: int) -> _P:
    return views_dir(idir) / f"{tid}-R{rnd:02d}-verdict.md"


# ---------------------------------------------------------------- committed

def docs_init_dir(root: _P, init_id: str) -> _P:
    return docs_root(root) / init_id


def docs_index_file(root: _P, init_id: str) -> _P:
    return docs_init_dir(root, init_id) / "meta" / "index.json"


def docs_index_md(root: _P, init_id: str) -> _P:
    return docs_init_dir(root, init_id) / "meta" / "index.md"


def docs_artifact_dir(root: _P, init_id: str, aid: str) -> _P:
    return docs_init_dir(root, init_id) / "artifacts" / aid


def docs_artifact_file(root: _P, init_id: str, aid: str) -> _P:
    return docs_artifact_dir(root, init_id, aid) / "artifact.json"


def docs_artifact_md(root: _P, init_id: str, aid: str) -> _P:
    return docs_artifact_dir(root, init_id, aid) / "artifact.md"


def docs_plan_dir(root: _P, init_id: str, pid: str) -> _P:
    return docs_init_dir(root, init_id) / "plans" / pid


def docs_plan_file(root: _P, init_id: str, pid: str) -> _P:
    return docs_plan_dir(root, init_id, pid) / "plan.json"


def docs_plan_md(root: _P, init_id: str, pid: str) -> _P:
    return docs_plan_dir(root, init_id, pid) / "plan.md"


def docs_task_dir(root: _P, init_id: str, tid: str) -> _P:
    pid = tid.rsplit("-", 1)[0]
    return docs_plan_dir(root, init_id, pid) / "tasks" / tid


def docs_report_file(root: _P, init_id: str, tid: str, did: str) -> _P:
    return docs_task_dir(root, init_id, tid) / "impl" / f"{did}.report.md"


def docs_verdict_file(root: _P, init_id: str, tid: str, rnd: int) -> _P:
    return (docs_task_dir(root, init_id, tid) / "reviews"
            / f"R{rnd:02d}.verdict.md")


def docs_export_journal(root: _P, init_id: str) -> _P:
    return docs_init_dir(root, init_id) / "export" / "events.jsonl"


# ---------------------------------------------------------------- grammar
# Each row is (kind, pattern). A pattern describes a file path relative to its
# store root. Back-references tie every nested id to its owner, so an artifact
# of INIT-0008 inside INIT-0007's directory, or a task outside its plan, fits
# no row and is refused.

@dataclass(frozen=True)
class Entry:
    """What a canonical file is: its store, its kind and the ids in its path."""
    store: str
    kind: str
    ids: dict[str, str]


_I = r"(?P<init>" + INIT_ID + r")"
_ART = r"(?P<art>(?P=init)-[A-Z]+-\d{2})"
_PLAN = r"(?P<plan>(?P=init)-P\d{2})"
_TASK = r"(?P<task>(?P=plan)-T\d{2})"
_DISP = r"(?P<disp>" + DISPATCH_ID + r")"
_RND = r"(?P<rnd>" + ROUND_ID + r")"
_TASK_DIR = _I + r"/plans/" + _PLAN + r"/tasks/" + _TASK

_RUN_ROWS = (
    ("run_meta", r"meta\.json"),
    ("journal", _I + r"/journal/events\.v(?P<ver>\d+)\.jsonl"),
    ("state", _I + r"/journal/state\.json"),
    ("lock", _I + r"/journal/\.lock"),
    ("init_meta", _I + r"/meta/meta\.json"),
    ("autonomy", _I + r"/meta/autonomy\.json"),
    ("artifact", _I + r"/artifacts/" + _ART + r"/artifact\.json"),
    ("artifact_audit",
     _I + r"/artifacts/" + _ART + r"/audits/" + _RND + r"\.audit\.json"),
    ("artifact_repair",
     _I + r"/artifacts/" + _ART + r"/repairs/" + _RND + r"\.repair\.json"),
    ("plan", _I + r"/plans/" + _PLAN + r"/plan\.json"),
    ("preflight", _I + r"/plans/" + _PLAN + r"/preflight\.json"),
    ("plan_audit",
     _I + r"/plans/" + _PLAN + r"/audits/" + _RND + r"\.audit\.json"),
    ("plan_repair",
     _I + r"/plans/" + _PLAN + r"/repairs/" + _RND + r"\.repair\.json"),
    ("task_report", _TASK_DIR + r"/impl/" + _DISP + r"\.report\.json"),
    ("review_package", _TASK_DIR + r"/reviews/" + _RND + r"\.package\.json"),
    ("verdict", _TASK_DIR + r"/reviews/" + _RND + r"\.verdict\.json"),
    ("fix_package", _TASK_DIR + r"/fixes/" + _RND + r"\.fix-package\.json"),
    ("fix_report", _TASK_DIR + r"/fixes/" + _RND + r"\.report\.json"),
    ("dispatch_slot", _I + r"/dispatches/" + _DISP + r"/slot\.json"),
    ("dispatch_prompt", _I + r"/dispatches/" + _DISP + r"/prompt\.md"),
    ("dispatch_payload", _I + r"/dispatches/" + _DISP + r"/payload\.json"),
    ("view", _I + r"/views/(?P<name>progress\.md|dispatches\.md|summary\.md"
     r"|graph\.json)"),
    ("view_verdict",
     _I + r"/views/(?P<task>(?P=init)-P\d{2}-T\d{2})-" + _RND
     + r"-verdict\.md"),
)

_DOCS_ROWS = (
    ("docs_index_json", _I + r"/meta/index\.json"),
    ("docs_index_md", _I + r"/meta/index\.md"),
    ("docs_artifact_json", _I + r"/artifacts/" + _ART + r"/artifact\.json"),
    ("docs_artifact_md", _I + r"/artifacts/" + _ART + r"/artifact\.md"),
    ("docs_plan_json", _I + r"/plans/" + _PLAN + r"/plan\.json"),
    ("docs_plan_md", _I + r"/plans/" + _PLAN + r"/plan\.md"),
    ("docs_task_report", _TASK_DIR + r"/impl/" + _DISP + r"\.report\.md"),
    ("docs_task_verdict",
     _TASK_DIR + r"/reviews/" + _RND + r"\.verdict\.md"),
    ("docs_export", _I + r"/export/events\.jsonl"),
)

GRAMMAR = {"run": _RUN_ROWS, "docs": _DOCS_ROWS}
_COMPILED = {store: tuple((kind, re.compile(rx)) for kind, rx in rows)
             for store, rows in GRAMMAR.items()}


def classify(rel: str | PurePath, store: str) -> Entry | None:
    """The grammar entry for a file path relative to its store root (the
    `.executor/` dir for store "run", `docs/executor/` for "docs"), or None
    when the path is not canonical. Directories are never entries."""
    if store not in _COMPILED:
        raise ValueError(f"unknown store {store!r}: expected run or docs")
    text = rel.as_posix() if isinstance(rel, PurePath) else rel
    for kind, rx in _COMPILED[store]:
        m = rx.fullmatch(text)
        if m:
            return Entry(store, kind, m.groupdict())
    return None
