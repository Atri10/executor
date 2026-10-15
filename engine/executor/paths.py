# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The one path authority for the executor store.

Every file the engine reads or writes is located by a function here —
nothing else in the codebase constructs a path. Naming is uniform:
``<ID>.<role>.<ext>`` nested under the owning entity's directory, so a
store is browsable top-down from initiative to artifact to task to round.

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
            impl/D<NN>.report.json
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
    <repo>/docs/executor/INIT-NNNN/      committed thinking store
      <ARTIFACT-ID>.json + .md
      plans/<PLAN-ID>.json + .md
      export/events.jsonl                durable journal snapshot (handoff)
"""
from __future__ import annotations

from pathlib import Path

RUN_STORE = ".executor"
DOCS_STORE = "docs/executor"


# ---------------------------------------------------------------- roots

def run_root(root: Path) -> Path:
    return root / RUN_STORE


def docs_root(root: Path) -> Path:
    return root / DOCS_STORE


def init_dir(root: Path, init_id: str) -> Path:
    return run_root(root) / init_id


# ---------------------------------------------------------------- journal

def journal_dir(idir: Path) -> Path:
    return idir / "journal"


def journal_file(idir: Path, version: int = 1) -> Path:
    return journal_dir(idir) / f"events.v{version}.jsonl"


def state_file(idir: Path) -> Path:
    return journal_dir(idir) / "state.json"


def lock_file(idir: Path) -> Path:
    return journal_dir(idir) / ".lock"


# ---------------------------------------------------------------- meta

def meta_dir(idir: Path) -> Path:
    return idir / "meta"


def meta_file(idir: Path) -> Path:
    return meta_dir(idir) / "meta.json"


def autonomy_file(idir: Path) -> Path:
    return meta_dir(idir) / "autonomy.json"


def run_meta_file(root: Path) -> Path:
    return run_root(root) / "meta.json"


# ---------------------------------------------------------------- artifacts

def artifact_dir(idir: Path, aid: str) -> Path:
    return idir / "artifacts" / aid


def artifact_file(idir: Path, aid: str) -> Path:
    return artifact_dir(idir, aid) / "artifact.json"


def audit_file(idir: Path, aid: str, rnd: int) -> Path:
    return artifact_dir(idir, aid) / "audits" / f"R{rnd:02d}.audit.json"


def repair_file(idir: Path, aid: str, rnd: int) -> Path:
    return artifact_dir(idir, aid) / "repairs" / f"R{rnd:02d}.repair.json"


# ---------------------------------------------------------------- plans

def plan_dir(idir: Path, pid: str) -> Path:
    return idir / "plans" / pid


def plan_file(idir: Path, pid: str) -> Path:
    return plan_dir(idir, pid) / "plan.json"


def preflight_file(idir: Path, pid: str) -> Path:
    return plan_dir(idir, pid) / "preflight.json"


def plan_audit_file(idir: Path, pid: str, rnd: int) -> Path:
    return plan_dir(idir, pid) / "audits" / f"R{rnd:02d}.audit.json"
# ---------------------------------------------------------------- committed

def docs_init_dir(root: Path, init_id: str) -> Path:
    return docs_root(root) / init_id


def docs_index_file(root: Path, init_id: str) -> Path:
    return docs_init_dir(root, init_id) / "meta" / "index.json"


def docs_index_md(root: Path, init_id: str) -> Path:
    return docs_init_dir(root, init_id) / "meta" / "index.md"


def docs_artifact_dir(root: Path, init_id: str, aid: str) -> Path:
    return docs_init_dir(root, init_id) / "artifacts" / aid


def docs_artifact_file(root: Path, init_id: str, aid: str) -> Path:
    return docs_artifact_dir(root, init_id, aid) / "artifact.json"


def docs_artifact_md(root: Path, init_id: str, aid: str) -> Path:
    return docs_artifact_dir(root, init_id, aid) / "artifact.md"


def docs_plan_dir(root: Path, init_id: str, pid: str) -> Path:
    return docs_init_dir(root, init_id) / "plans" / pid


def docs_plan_file(root: Path, init_id: str, pid: str) -> Path:
    return docs_plan_dir(root, init_id, pid) / "plan.json"


def docs_plan_md(root: Path, init_id: str, pid: str) -> Path:
    return docs_plan_dir(root, init_id, pid) / "plan.md"


def docs_task_dir(root: Path, init_id: str, tid: str) -> Path:
    pid = tid.rsplit("-", 1)[0]
    return docs_plan_dir(root, init_id, pid) / "tasks" / tid


def docs_report_file(root: Path, init_id: str, tid: str,
                     did: str) -> Path:
    return docs_task_dir(root, init_id, tid) / "impl" / f"{did}.report.md"


def docs_verdict_file(root: Path, init_id: str, tid: str,
                      rnd: int) -> Path:
    return docs_task_dir(root, init_id, tid) / "reviews" / \
        f"R{rnd:02d}.verdict.md"


def docs_export_journal(root: Path, init_id: str) -> Path:
    return docs_init_dir(root, init_id) / "export" / "events.jsonl"


def plan_repair_file(idir: Path, pid: str, rnd: int) -> Path:
    return plan_dir(idir, pid) / "repairs" / f"R{rnd:02d}.repair.json"


# ---------------------------------------------------------------- tasks

def task_dir(idir: Path, tid: str) -> Path:
    pid = tid.rsplit("-", 1)[0]
    return plan_dir(idir, pid) / "tasks" / tid


def task_impl_report(idir: Path, tid: str, did: str) -> Path:
    return task_dir(idir, tid) / "impl" / f"{did}.report.json"


def review_package_file(idir: Path, tid: str, rnd: int) -> Path:
    return task_dir(idir, tid) / "reviews" / f"R{rnd:02d}.package.json"


def verdict_file(idir: Path, tid: str, rnd: int) -> Path:
    return task_dir(idir, tid) / "reviews" / f"R{rnd:02d}.verdict.json"


def fix_package_file(idir: Path, tid: str, rnd: int) -> Path:
    return task_dir(idir, tid) / "fixes" / f"R{rnd:02d}.fix-package.json"


def fix_report_file(idir: Path, tid: str, rnd: int) -> Path:
    return task_dir(idir, tid) / "fixes" / f"R{rnd:02d}.report.json"


# ---------------------------------------------------------------- dispatches

def dispatch_dir(idir: Path, did: str) -> Path:
    return idir / "dispatches" / did


def slot_file(idir: Path, did: str) -> Path:
    return dispatch_dir(idir, did) / "slot.json"


def prompt_file(idir: Path, did: str) -> Path:
    return dispatch_dir(idir, did) / "prompt.md"


def payload_file(idir: Path, did: str) -> Path:
    """The respond_to target the worker writes."""
    return dispatch_dir(idir, did) / "payload.json"


def dispatches_dir(idir: Path) -> Path:
    return idir / "dispatches"


# ---------------------------------------------------------------- views

def views_dir(idir: Path) -> Path:
    return idir / "views"


def view_file(idir: Path, name: str) -> Path:
    return views_dir(idir) / name


