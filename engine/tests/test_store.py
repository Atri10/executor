# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""store.py: the durable mechanics every other module trusts.

Each test pins one behavior. Several pin a defect found in the first
implementation: an event edited in place went undetected, a torn journal tail
(or a multibyte character cut in half) hid or crashed everything after it, a
failed atomic write leaked its temp file, and re-initialising an initiative
silently reset its meta and autonomy.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))
from executor import __version__, paths as P, store  # noqa: E402
from executor.store import ExecError, Initiative, Rejection  # noqa: E402

ISO = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


class TmpCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.idir = P.init_dir(self.root, "INIT-0001")

    def append(self, kind="emit", entity="INIT-0001", dispatch_id=None,
               **data) -> dict:
        ev = store.make_event(self.idir, "engine", kind, entity, data,
                              dispatch_id=dispatch_id)
        return store.append_event(self.idir, ev)

    def write_journal(self, raw: bytes) -> None:
        path = P.journal_file(self.idir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def event_line(self, **data) -> bytes:
        """One real chained event, serialised as the journal stores it."""
        ev = store.make_event(self.idir, "engine", "emit", "INIT-0001", data)
        return (json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8")


class CanonicalTests(unittest.TestCase):
    def test_key_order_does_not_change_the_bytes(self):
        self.assertEqual(store.canonical({"b": 1, "a": 2}),
                         store.canonical({"a": 2, "b": 1}))

    def test_output_is_compact_sorted_utf8(self):
        self.assertEqual(store.canonical({"b": [1, 2], "a": "é"}),
                         '{"a":"é","b":[1,2]}'.encode("utf-8"))

    def test_sha256_is_the_hash_of_the_canonical_bytes(self):
        self.assertEqual(store.sha256({"x": 1}),
                         hashlib.sha256(b'{"x":1}').hexdigest())

    def test_sha256_distinguishes_payloads(self):
        self.assertNotEqual(store.sha256({"x": 1}), store.sha256({"x": 2}))

    def test_sha_line_hashes_the_line_without_its_newline(self):
        want = hashlib.sha256(b"abc").hexdigest()
        self.assertEqual(store.sha_line(b"abc\n"), want)
        self.assertEqual(store.sha_line(b"abc"), want)

    def test_now_iso_is_utc_and_well_formed(self):
        stamp = store.now_iso()
        self.assertRegex(stamp, ISO)
        parsed = calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))
        self.assertLess(abs(parsed - time.time()), 5)


class ErrorTests(unittest.TestCase):
    def test_exec_error_carries_a_code_and_a_message(self):
        e = ExecError("boom")
        self.assertEqual((e.code, e.msg, str(e)),
                         ("engine_error", "boom", "boom"))
        self.assertEqual(ExecError("x", "custom").code, "custom")

    def test_rejection_is_structured(self):
        r = Rejection("enum", "$.verdict", "PASS|FAIL", "'MAYBE'", "pick one")
        self.assertEqual(
            str(r), "enum at $.verdict: expected PASS|FAIL, got 'MAYBE'")
        self.assertEqual(r.to_dict(), {
            "code": "enum", "field": "$.verdict", "expected": "PASS|FAIL",
            "got": "'MAYBE'", "hint": "pick one"})
        self.assertEqual(Rejection("a", "b", "c", "d").hint, "")

    def test_exec_error_built_by_keyword_still_prints_its_message(self):
        e = ExecError(msg="boom", code="c")
        self.assertEqual((str(e), e.msg, e.code), ("boom", "boom", "c"))


class AtomicIoTests(TmpCase):
    def names(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir())

    def test_creates_parents_and_writes_exact_bytes(self):
        target = self.root / "a" / "b" / "f.bin"
        store.atomic_write(target, b"\x00\xffdata")
        self.assertEqual(target.read_bytes(), b"\x00\xffdata")

    def test_overwrites_the_whole_file_and_leaves_no_temp(self):
        target = self.root / "f.json"
        store.atomic_write(target, b"long original content")
        store.atomic_write(target, b"new")
        self.assertEqual(target.read_bytes(), b"new")
        self.assertEqual(self.names(), ["f.json"])

    def test_a_failed_write_keeps_the_original_and_removes_the_temp(self):
        target = self.root / "f.json"
        store.atomic_write(target, b"original")
        with mock.patch.object(store.os, "fsync",
                               side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.atomic_write(target, b"replacement")
        self.assertEqual(target.read_bytes(), b"original")
        self.assertEqual(self.names(), ["f.json"])

    def test_a_failed_first_write_leaves_nothing_behind(self):
        with mock.patch.object(store.os, "fsync",
                               side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.atomic_write(self.root / "f.json", b"x")
        self.assertEqual(self.names(), [])

    def test_an_interrupt_mid_write_also_cleans_up(self):
        with mock.patch.object(store.os, "fsync",
                               side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                store.atomic_write(self.root / "f.json", b"x")
        self.assertEqual(self.names(), [])

    def test_write_json_is_utf8_ordered_and_newline_terminated(self):
        target = self.root / "x.json"
        store.write_json(target, {"z": 1, "a": "é"})
        raw = target.read_bytes()
        self.assertTrue(raw.endswith(b"\n"))
        self.assertIn("é".encode("utf-8"), raw)          # not \u-escaped
        self.assertLess(raw.index(b'"z"'), raw.index(b'"a"'))
        self.assertEqual(store.read_json(target), {"z": 1, "a": "é"})

    def test_read_json_falls_back_for_missing_corrupt_and_unreadable(self):
        corrupt = self.root / "bad.json"
        corrupt.write_text("{not json", encoding="utf-8")
        directory = self.root / "dir.json"
        directory.mkdir()
        for path in (self.root / "none.json", corrupt, directory):
            with self.subTest(path=path.name):
                self.assertIsNone(store.read_json(path))
                self.assertEqual(store.read_json(path, {"d": 1}), {"d": 1})

    def test_data_is_flushed_then_fsynced_before_the_rename(self):
        target = self.root / "f.json"
        tmp = target.with_suffix(".json.tmp")
        seen = []

        def spy(_fd):
            seen.append((tmp.read_bytes(), target.exists()))

        with mock.patch.object(store.os, "fsync", side_effect=spy) as fsync:
            store.atomic_write(target, b"payload")
        # one fsync, and when it ran the whole payload was already in the
        # temp file while the target had not been replaced yet
        self.assertEqual(fsync.call_count, 1)
        self.assertEqual(seen, [(b"payload", False)])
        self.assertEqual(target.read_bytes(), b"payload")

    def test_a_failure_before_the_temp_file_exists_is_not_masked(self):
        with mock.patch.object(store, "open", create=True,
                               side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                store.atomic_write(self.root / "f.json", b"x")

    def test_write_json_is_two_space_indented_and_newline_terminated(self):
        target = self.root / "x.json"
        store.write_json(target, {"a": 1, "b": [2]})
        self.assertEqual(target.read_text(encoding="utf-8"),
                         '{\n  "a": 1,\n  "b": [\n    2\n  ]\n}\n')


CHILD = """
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from executor.store import StoreLock
idir, counter = Path(sys.argv[2]), Path(sys.argv[3])
for _ in range(int(sys.argv[4])):
    with StoreLock(idir):
        n = int(counter.read_text())
        time.sleep(0.002)
        counter.write_text(str(n + 1))
"""


FD0_CHILD = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from executor.store import StoreLock
os.close(0)                       # free descriptor 0 so the lock lands on it
with StoreLock(Path(sys.argv[2])) as lock:
    assert lock.fd == 0, lock.fd
try:
    os.fstat(0)
except OSError:
    sys.exit(0)                   # released and closed, as it must be
sys.exit("descriptor 0 leaked past the lock")
"""


def must(value):
    """Narrow an Optional for the type checker: the value must be present."""
    assert value is not None
    return value


def fake_fcntl(calls, fail=None):
    def flock(_fd, op):
        calls.append(("flock", op))
        if fail:
            raise OSError(fail)
    return types.SimpleNamespace(LOCK_EX=101, LOCK_UN=102, flock=flock)


def fake_msvcrt(calls, fail=None):
    def locking(_fd, mode, nbytes):
        calls.append(("locking", mode, nbytes))
        if fail:
            raise OSError(fail)
    return types.SimpleNamespace(LK_LOCK=201, LK_UNLCK=202, locking=locking)


class StoreLockTests(TmpCase):
    def counter(self) -> Path:
        path = self.root / "counter.txt"
        path.write_text("0", encoding="utf-8")
        return path

    def test_threads_never_interleave_inside_the_lock(self):
        counter, errors = self.counter(), []

        def work():
            try:
                for _ in range(5):
                    with store.StoreLock(self.idir):
                        n = int(counter.read_text())
                        time.sleep(0.002)
                        counter.write_text(str(n + 1))
            except BaseException as e:  # noqa: BLE001 - reported below
                errors.append(e)

        threads = [threading.Thread(target=work) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(int(counter.read_text()), 20)

    def test_processes_never_interleave_inside_the_lock(self):
        counter = self.counter()
        procs = [subprocess.Popen(
            [sys.executable, "-c", CHILD, str(ENGINE), str(self.idir),
             str(counter), "5"]) for _ in range(3)]
        self.assertEqual([p.wait(timeout=60) for p in procs], [0, 0, 0])
        self.assertEqual(int(counter.read_text()), 15)

    def test_the_lock_is_released_when_the_body_raises(self):
        with self.assertRaises(RuntimeError):
            with store.StoreLock(self.idir):
                raise RuntimeError("boom")
        self.assertTrue(self.free_within())

    def test_the_descriptor_is_closed_on_exit(self):
        lock = store.StoreLock(self.idir)
        with lock:
            fd = lock.fd
            self.assertGreaterEqual(fd, 0)
        self.assertEqual(lock.fd, -1)
        with self.assertRaises(OSError):
            os.fstat(fd)

    def test_exiting_twice_is_harmless(self):
        lock = store.StoreLock(self.idir)
        with lock:
            pass
        lock.__exit__(None, None, None)
        self.assertEqual(lock.fd, -1)

    def test_entering_creates_the_journal_directory(self):
        with store.StoreLock(self.idir):
            self.assertTrue(P.journal_dir(self.idir).is_dir())

    def test_posix_branch_takes_an_exclusive_flock_then_unlocks(self):
        calls: list = []
        with mock.patch.object(store, "_WINDOWS", False), \
                mock.patch.dict(sys.modules, {"fcntl": fake_fcntl(calls)}):
            with store.StoreLock(self.idir):
                self.assertEqual(calls, [("flock", 101)])
        self.assertEqual(calls, [("flock", 101), ("flock", 102)])

    def test_windows_branch_rewinds_then_locks_one_byte_then_unlocks(self):
        calls: list = []
        real_lseek = os.lseek

        def lseek(fd, pos, how):
            calls.append(("lseek", pos, how))
            return real_lseek(fd, pos, how)

        with mock.patch.object(store, "_WINDOWS", True), \
                mock.patch.dict(sys.modules, {"msvcrt": fake_msvcrt(calls)}), \
                mock.patch.object(store.os, "lseek", side_effect=lseek):
            with store.StoreLock(self.idir):
                pass
        rewind = ("lseek", 0, os.SEEK_SET)
        self.assertEqual(calls, [rewind, ("locking", 201, 1),
                                 rewind, ("locking", 202, 1)])

    def test_a_posix_lock_failure_is_typed_and_closes_the_descriptor(self):
        lock = store.StoreLock(self.idir)
        with mock.patch.object(store, "_WINDOWS", False), \
                mock.patch.dict(sys.modules,
                                {"fcntl": fake_fcntl([], fail="busy")}):
            with self.assertRaises(ExecError) as err:
                lock.__enter__()
        self.assertEqual(err.exception.code, "store_locked")
        self.assertIsInstance(err.exception.__cause__, OSError)
        self.assertEqual(lock.fd, -1)

    def test_a_windows_lock_failure_is_typed_too(self):
        lock = store.StoreLock(self.idir)
        with mock.patch.object(store, "_WINDOWS", True), \
                mock.patch.dict(sys.modules,
                                {"msvcrt": fake_msvcrt([], fail="busy")}):
            with self.assertRaises(ExecError) as err:
                lock.__enter__()
        self.assertEqual(err.exception.code, "store_locked")
        self.assertEqual(lock.fd, -1)

    def free_within(self, seconds: float = 10.0) -> bool:
        """Whether another acquirer gets the lock promptly. It runs in a daemon
        thread so a lock that was never released fails the test instead of
        hanging the whole suite."""
        got = threading.Event()

        def grab():
            try:
                with store.StoreLock(self.idir):
                    got.set()
            except ExecError:
                pass

        threading.Thread(target=grab, daemon=True).start()
        return got.wait(seconds)

    def test_the_lock_is_held_while_inside_and_free_after(self):
        with store.StoreLock(self.idir):
            self.assertFalse(self.free_within(0.3))
        self.assertTrue(self.free_within())

    def test_a_fresh_lock_holds_no_descriptor(self):
        self.assertEqual(store.StoreLock(self.idir).fd, -1)

    def test_a_failed_lock_closes_the_descriptor_it_opened(self):
        opened: list[int] = []
        real_open = os.open

        def spy(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            opened.append(fd)
            return fd

        with mock.patch.object(store, "_WINDOWS", False), \
                mock.patch.dict(sys.modules,
                                {"fcntl": fake_fcntl([], fail="busy")}), \
                mock.patch.object(store.os, "open", side_effect=spy):
            with self.assertRaises(ExecError):
                store.StoreLock(self.idir).__enter__()
        (fd,) = opened
        with self.assertRaises(OSError):
            os.fstat(fd)

    def test_the_lock_works_when_it_lands_on_descriptor_zero(self):
        r = subprocess.run(
            [sys.executable, "-c", FD0_CHILD, str(ENGINE), str(self.idir)],
            capture_output=True, text=True, timeout=60,
            stdin=subprocess.DEVNULL)
        self.assertEqual((r.returncode, r.stderr), (0, ""))


class JournalTests(TmpCase):
    def chain(self, n: int = 3) -> list[dict]:
        for i in range(n):
            self.append(note=f"e{i}")
        return store.read_events(self.idir)

    def test_an_empty_journal_has_the_genesis_tip_and_seq_one(self):
        self.assertEqual(store.read_events(self.idir), [])
        self.assertEqual(store.next_seq([]), 1)
        self.assertEqual(store.chain_tip([]), store.GENESIS_SHA)
        self.assertEqual(store.verify_chain([]), [])

    def test_the_first_event_is_seq_one_chained_to_genesis(self):
        ev = store.make_event(self.idir, "engine", "created", "INIT-0001",
                              {"title": "t"})
        self.assertEqual(ev["seq"], 1)
        self.assertEqual(ev["prev_sha"], store.GENESIS_SHA)
        for key, want in (("actor", "engine"), ("kind", "created"),
                          ("entity", "INIT-0001"), ("dispatch_id", None),
                          ("payload_sha", None), ("v", "v1"),
                          ("engine_version", __version__),
                          ("data", {"title": "t"})):
            self.assertEqual(ev[key], want, key)
        self.assertRegex(ev["ts"], ISO)
        body = {k: v for k, v in ev.items() if k != "line_sha"}
        self.assertEqual(ev["line_sha"], store.sha256(body))

    def test_dispatch_id_and_payload_sha_are_recorded(self):
        ev = store.make_event(self.idir, "worker", "report", "T", {},
                              dispatch_id="D00007", payload_sha="abc")
        self.assertEqual((ev["dispatch_id"], ev["payload_sha"]),
                         ("D00007", "abc"))

    def test_events_chain_by_seq_and_prev_sha(self):
        events = self.chain()
        self.assertEqual([e["seq"] for e in events], [1, 2, 3])
        self.assertEqual(events[0]["prev_sha"], store.GENESIS_SHA)
        for before, after in zip(events, events[1:]):
            self.assertEqual(after["prev_sha"], before["line_sha"])
        self.assertEqual(store.verify_chain(events), [])

    def test_next_seq_and_tip_follow_the_last_event(self):
        events = self.chain()
        self.assertEqual(store.next_seq(events), 4)
        self.assertEqual(store.chain_tip(events), events[-1]["line_sha"])

    def test_each_event_is_one_utf8_line(self):
        self.append(note="café — ünïcode")
        raw = P.journal_file(self.idir).read_bytes()
        self.assertEqual(raw.count(b"\n"), 1)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertIn("café".encode("utf-8"), raw)
        self.assertEqual(store.read_events(self.idir)[0]["data"]["note"],
                         "café — ünïcode")

    def test_appending_creates_the_journal_directory(self):
        self.assertFalse(P.journal_dir(self.idir).exists())
        self.append()
        self.assertTrue(P.journal_file(self.idir).is_file())

    def test_append_returns_the_event_it_wrote(self):
        ev = store.make_event(self.idir, "engine", "emit", "INIT-0001", {})
        self.assertIs(store.append_event(self.idir, ev), ev)

    def test_events_are_written_in_reading_order_not_sorted(self):
        self.append()
        line = P.journal_file(self.idir).read_text(encoding="utf-8")
        keys = list(json.loads(line))
        self.assertTrue(line.startswith('{"seq": 1, "ts": '))
        self.assertEqual(keys[:3], ["seq", "ts", "v"])
        self.assertEqual(keys[-1], "line_sha")

    def test_an_append_is_flushed_then_fsynced_exactly_once(self):
        ev = store.make_event(self.idir, "engine", "emit", "INIT-0001", {})
        on_disk = []

        def spy(_fd):
            on_disk.append(P.journal_file(self.idir).read_bytes())

        with mock.patch.object(store.os, "fsync", side_effect=spy) as fsync:
            store.append_event(self.idir, ev)
        self.assertEqual(fsync.call_count, 1)
        self.assertEqual(len(on_disk), 1)
        self.assertIn(b'"seq": 1', on_disk[0])      # flushed before the fsync

    def test_a_clean_chain_has_no_problems(self):
        self.assertEqual(store.verify_chain(self.chain(5)), [])

    def test_genesis_is_a_zero_sha_as_long_as_a_real_one(self):
        self.assertEqual(store.GENESIS_SHA, "0" * 64)
        self.assertEqual(len(store.GENESIS_SHA), len(store.sha256({})))

    def test_an_edited_event_is_detected_even_when_it_is_the_last(self):
        events = self.chain()
        events[-1]["data"]["note"] = "tampered"
        problems = store.verify_chain(events)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("line_sha mismatch", problems[0])

    def test_an_edited_middle_event_is_one_problem_not_a_cascade(self):
        events = self.chain()
        events[1]["data"]["note"] = "tampered"
        problems = store.verify_chain(events)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("seq 2", problems[0])

    def test_a_dropped_event_breaks_the_seq_and_the_link(self):
        events = self.chain()
        del events[1]
        problems = store.verify_chain(events)
        self.assertIn("event 2: seq 3 != 2", problems)
        self.assertTrue(any("prev_sha mismatch" in p for p in problems))

    def test_reordered_events_are_detected(self):
        events = self.chain()
        events[0], events[1] = events[1], events[0]
        self.assertTrue(store.verify_chain(events))

    def test_a_forged_prev_sha_is_detected(self):
        events = self.chain()
        events[2]["prev_sha"] = "f" * 64
        problems = store.verify_chain(events)
        self.assertTrue(any("prev_sha mismatch" in p for p in problems))

    def test_a_missing_line_sha_is_detected(self):
        events = self.chain()
        del events[1]["line_sha"]
        self.assertTrue(any("line_sha mismatch" in p
                            for p in store.verify_chain(events)))

    def test_a_missing_journal_reads_empty(self):
        self.assertEqual(store.scan_journal(self.idir), ([], 0))

    def test_parsing_nothing_or_only_blanks_is_empty(self):
        self.assertEqual(store.parse_journal(b""), ([], 0))
        self.assertEqual(store.parse_journal(b"\n\r\n \n"), ([], 0))

    def test_the_file_scan_is_the_pure_parser_over_the_file_bytes(self):
        self.write_journal(self.event_line(note="a") + b'{"seq": 2, "kin')
        raw = P.journal_file(self.idir).read_bytes()
        self.assertEqual(store.scan_journal(self.idir),
                         store.parse_journal(raw))
        self.assertEqual(store.scan_journal(self.idir)[1], 1)

    def test_a_carriage_return_inside_a_line_is_json_whitespace(self):
        line = self.event_line(note="a").rstrip(b"\n")
        joined = line.replace(b'{"seq": 1,', b'{"seq": 1,\r')
        self.assertEqual(store.parse_journal(joined + b"\r\n")[1], 0)
        self.assertEqual(len(store.parse_journal(joined + b"\r\n")[0]), 1)

    def test_blank_lines_and_crlf_endings_are_tolerated(self):
        first = self.event_line(note="a")
        self.write_journal(b"\n" + first.replace(b"\n", b"\r\n") + b"\n")
        events, torn = store.scan_journal(self.idir)
        self.assertEqual((len(events), torn), (1, 0))

    def test_lines_that_are_not_events_are_counted_and_skipped(self):
        junk = b'[1,2]\n"x"\n{"no_seq":1}\n{"seq":"5"}\n'
        self.write_journal(junk + self.event_line(note="ok"))
        events, torn = store.scan_journal(self.idir)
        self.assertEqual((len(events), torn), (1, 4))

    def test_garbage_in_the_middle_does_not_hide_later_events(self):
        first = self.event_line(note="a")
        self.write_journal(first)
        self.append(note="b")                     # a real second event
        raw = P.journal_file(self.idir).read_bytes().split(b"\n")
        self.write_journal(b"\n".join([raw[0], b"{garbage", raw[1], b""]))
        events, torn = store.scan_journal(self.idir)
        self.assertEqual(([e["seq"] for e in events], torn), ([1, 2], 1))
        self.assertEqual(len(store.read_events(self.idir)), 2)

    def test_a_torn_tail_is_ignored_and_counted(self):
        self.write_journal(self.event_line(note="a") + b'{"seq": 2, "kind": "emi')
        events, torn = store.scan_journal(self.idir)
        self.assertEqual((len(events), torn), (1, 1))

    def test_a_multibyte_character_cut_in_half_is_torn_not_a_crash(self):
        cut = '{"seq": 2, "data": "é'.encode("utf-8")[:-1]
        self.write_journal(self.event_line(note="a") + cut)
        events, torn = store.scan_journal(self.idir)
        self.assertEqual((len(events), torn), (1, 1))

    def test_appending_after_a_torn_tail_starts_a_fresh_line(self):
        self.append(note="a")
        with open(P.journal_file(self.idir), "ab") as f:
            f.write(b'{"seq": 2, "kin')                # crash mid-append
        self.append(note="b")
        events, torn = store.scan_journal(self.idir)
        self.assertEqual(([e["seq"] for e in events], torn), ([1, 2], 1))
        self.assertEqual(store.verify_chain(events), [])

    def test_appending_to_an_existing_empty_journal_adds_no_blank_line(self):
        self.write_journal(b"")
        self.append(note="a")
        raw = P.journal_file(self.idir).read_bytes()
        self.assertFalse(raw.startswith(b"\n"))
        self.assertEqual(raw.count(b"\n"), 1)

    def test_appending_to_a_clean_journal_adds_no_blank_line(self):
        self.append(note="a")
        self.append(note="b")
        lines = P.journal_file(self.idir).read_bytes().split(b"\n")
        self.assertEqual([bool(x) for x in lines], [True, True, False])


class SlotTests(TmpCase):
    def setUp(self):
        super().setUp()
        store.init_store(self.root, "INIT-0001", "t")

    def mint(self, entity="INIT-0001-P01-T01"):
        return store.mint_slot(self.idir, "impl", entity, "report")

    def test_the_slot_id_follows_the_grammar_and_the_next_seq(self):
        first = self.mint()
        self.assertEqual(first["dispatch_id"], "D00001")
        self.assertTrue(P.is_dispatch_id(first["dispatch_id"]))
        self.append()
        self.assertEqual(self.mint()["dispatch_id"], "D00002")

    def test_the_slot_records_what_a_worker_needs(self):
        slot = self.mint("INIT-0001-P01-T09")
        self.assertEqual(slot["respond_to"],
                         str(P.payload_file(self.idir, "D00001")))
        self.assertEqual((slot["action"], slot["entity"], slot["schema"]),
                         ("impl", "INIT-0001-P01-T09", "report"))
        self.assertEqual((slot["consumed"], slot["retries"]), (False, 0))
        self.assertRegex(slot["minted_at"], ISO)

    def test_minting_alone_writes_nothing(self):
        self.mint()
        self.assertEqual(list(P.dispatches_dir(self.idir).iterdir()), [])

    def test_save_and_load_round_trip(self):
        slot = self.mint()
        store.save_slot(self.idir, slot)
        self.assertEqual(store.load_slot(self.idir, "D00001"), slot)
        self.assertIsNone(store.load_slot(self.idir, "D00099"))

    def test_open_slots_are_the_unconsumed_ones_in_id_order(self):
        ids = []
        for entity in ("A", "B", "C"):
            slot = self.mint(entity)
            store.save_slot(self.idir, slot)
            ids.append(slot["dispatch_id"])
            self.append()
        done = must(store.load_slot(self.idir, ids[1]))
        done["consumed"] = True
        store.save_slot(self.idir, done)
        self.assertEqual([s["dispatch_id"]
                          for s in store.open_slots(self.idir)],
                         [ids[0], ids[2]])

    def test_open_slots_skip_corrupt_and_foreign_entries(self):
        d = P.dispatches_dir(self.idir)
        (d / "D00009").mkdir()
        (d / "D00009" / "slot.json").write_text("{bad", encoding="utf-8")
        (d / "D00010").mkdir()
        (d / "stray.txt").write_text("x", encoding="utf-8")
        self.assertEqual(store.open_slots(self.idir), [])

    def test_a_store_without_a_dispatches_dir_has_no_open_slots(self):
        other = P.init_dir(self.root, "INIT-0002")
        self.assertEqual(store.open_slots(other), [])


class InitStoreTests(TmpCase):
    def test_scaffolds_every_directory_and_meta_file(self):
        idir = store.init_store(self.root, "INIT-0001", "My title")
        self.assertEqual(idir, self.idir)
        for d in (P.journal_dir(idir), P.meta_dir(idir),
                  P.dispatches_dir(idir), P.views_dir(idir),
                  P.docs_init_dir(self.root, "INIT-0001")):
            self.assertTrue(d.is_dir(), d)
        meta = must(store.read_json(P.meta_file(idir)))
        self.assertEqual(
            {k: meta[k] for k in ("initiative", "title", "engine_version",
                                  "schema_version", "store_version")},
            {"initiative": "INIT-0001", "title": "My title",
             "engine_version": __version__, "schema_version": "v1",
             "store_version": "v1"})
        self.assertRegex(meta["created_at"], ISO)
        self.assertEqual(store.read_json(P.run_meta_file(self.root)),
                         {"engine_version": __version__,
                          "schema_version": "v1", "store_version": "v1"})

    def test_autonomy_fails_closed_for_every_phase(self):
        idir = store.init_store(self.root, "INIT-0001", "t")
        self.assertEqual(store.read_json(P.autonomy_file(idir)),
                         {p: "deny" for p in store.PHASES})

    def test_the_phases_are_the_eleven_in_order(self):
        self.assertEqual(store.PHASES, [
            "intake", "discovery", "architecture", "design", "specification",
            "planning", "plan_regression", "execution", "review",
            "verification", "handoff"])

    def test_every_scaffolded_file_fits_the_naming_grammar(self):
        store.init_store(self.root, "INIT-0001", "t")
        run = P.run_root(self.root)
        files = [f for f in run.rglob("*") if f.is_file()]
        self.assertTrue(files)
        for f in files:
            with self.subTest(file=f.relative_to(run).as_posix()):
                self.assertIsNotNone(P.classify(f.relative_to(run), "run"))

    def test_reinitialising_refuses_and_keeps_the_existing_files(self):
        idir = store.init_store(self.root, "INIT-0001", "t")
        store.write_json(P.autonomy_file(idir), {"intake": "allow"})
        with self.assertRaises(ExecError) as err:
            store.init_store(self.root, "INIT-0001", "other")
        self.assertEqual(err.exception.code, "exists")
        self.assertEqual(store.read_json(P.autonomy_file(idir)),
                         {"intake": "allow"})
        self.assertEqual(
            must(store.read_json(P.meta_file(idir)))["title"], "t")

    def test_an_existing_committed_docs_dir_is_kept_not_an_error(self):
        docs = P.docs_init_dir(self.root, "INIT-0001")
        docs.mkdir(parents=True)
        (docs / "keep.md").write_text("tracked", encoding="utf-8")
        store.init_store(self.root, "INIT-0001", "t")
        self.assertEqual((docs / "keep.md").read_text(encoding="utf-8"),
                         "tracked")


class VersionTests(TmpCase):
    def put_meta(self, **meta) -> None:
        P.meta_dir(self.idir).mkdir(parents=True)
        store.write_json(P.meta_file(self.idir), meta)

    def refused(self) -> ExecError:
        with self.assertRaises(ExecError) as err:
            store.check_store_version(self.idir)
        return err.exception

    def test_a_directory_without_meta_is_not_a_store(self):
        err = self.refused()
        self.assertEqual(err.code, "no_meta")
        self.assertNotIn("--adopt", err.msg)       # no such flag exists

    def test_the_same_major_passes_whatever_the_minor(self):
        major = store._major(__version__)
        self.put_meta(engine_version=f"{major}.9.9")
        store.check_store_version(self.idir)

    def test_a_store_from_a_newer_engine_names_the_version_needed(self):
        major = store._major(__version__) + 1
        self.put_meta(engine_version=f"{major}.0.0")
        err = self.refused()
        self.assertEqual(err.code, "engine_too_old")
        self.assertIn(f"{major}.x", err.msg)

    def test_a_store_from_an_older_engine_asks_for_migrate(self):
        self.put_meta(engine_version="1.4.0")
        err = self.refused()
        self.assertEqual(err.code, "store_outdated")
        self.assertIn("migrate", err.msg)

    def test_an_unreadable_or_missing_version_counts_as_oldest(self):
        for meta in ({"engine_version": "garbage"}, {}):
            with self.subTest(meta=meta):
                P.meta_dir(self.idir).mkdir(parents=True, exist_ok=True)
                store.write_json(P.meta_file(self.idir), meta)
                self.assertEqual(self.refused().code, "store_outdated")

    def test_major_parsing(self):
        for text, want in (("2.0.0", 2), ("10.1", 10), ("x", 0),
                           ("", 0), (None, 0)):
            with self.subTest(text=text):
                self.assertEqual(store._major(text), want)  # type: ignore[arg-type]


class InitiativeTests(TmpCase):
    def test_meta_and_state_read_their_files_and_default_to_empty(self):
        init = Initiative("INIT-0001", self.root, self.idir)
        self.assertEqual((init.meta, init.state), ({}, {}))
        store.init_store(self.root, "INIT-0001", "t")
        store.write_json(P.state_file(self.idir), {"phase": "intake"})
        self.assertEqual(init.meta["title"], "t")
        self.assertEqual(init.state, {"phase": "intake"})

    def test_reload_reads_the_journal_and_returns_self(self):
        init = Initiative("INIT-0001", self.root, self.idir)
        self.assertEqual(init.events, [])
        self.append()
        self.assertIs(init.reload(), init)
        self.assertEqual(len(init.events), 1)

    def test_find_by_id_returns_a_reloaded_initiative(self):
        store.init_store(self.root, "INIT-0001", "t")
        self.append()
        init = store.find_initiative(self.root, "INIT-0001")
        self.assertEqual((init.id, init.idir, len(init.events)),
                         ("INIT-0001", self.idir, 1))

    def test_an_unknown_id_is_a_typed_error(self):
        with self.assertRaises(ExecError) as err:
            store.find_initiative(self.root, "INIT-0042")
        self.assertEqual(err.exception.code, "no_initiative")

    def test_an_empty_store_is_a_typed_error(self):
        with self.assertRaises(ExecError) as err:
            store.find_initiative(self.root)
        self.assertEqual(err.exception.code, "no_initiative")

    def test_a_single_initiative_is_found_without_an_id(self):
        store.init_store(self.root, "INIT-0001", "t")
        self.assertEqual(store.find_initiative(self.root).id, "INIT-0001")

    FINISHED = {"phase": "handoff", "phase_state": {"handoff": "passed"}}
    HANDOFF_IN_PROGRESS = {"phase": "handoff",
                           "phase_state": {"handoff": "in_progress"}}

    def make(self, init_id: str, state=None) -> Path:
        idir = store.init_store(self.root, init_id, init_id)
        if state is not None:
            store.write_json(P.state_file(idir), state)
        return idir

    def test_the_active_initiative_is_chosen_over_a_newer_finished_one(self):
        self.make("INIT-0001")
        self.make("INIT-0002", self.FINISHED)
        self.assertEqual(store.find_initiative(self.root).id, "INIT-0001")

    def test_a_handoff_still_in_progress_is_not_finished(self):
        self.make("INIT-0001", self.HANDOFF_IN_PROGRESS)
        self.make("INIT-0002", self.FINISHED)
        self.assertEqual(store.find_initiative(self.root).id, "INIT-0001")

    def test_an_unreadable_state_cache_counts_as_active(self):
        for junk in ("{broken", "[]", '{"phase_state": 5}', "null"):
            with self.subTest(junk=junk):
                idir = self.make("INIT-0001")
                P.state_file(idir).write_text(junk, encoding="utf-8")
                self.make("INIT-0002", self.FINISHED)
                self.assertEqual(store.find_initiative(self.root).id,
                                 "INIT-0001")
                shutil.rmtree(P.run_root(self.root))

    def test_two_active_initiatives_are_ambiguous_and_both_are_named(self):
        self.make("INIT-0001")
        self.make("INIT-0002")
        with self.assertRaises(ExecError) as err:
            store.find_initiative(self.root)
        self.assertEqual(err.exception.code, "ambiguous")
        self.assertIn("INIT-0001", err.exception.msg)
        self.assertIn("INIT-0002", err.exception.msg)

    def test_when_every_initiative_is_finished_the_newest_is_returned(self):
        self.make("INIT-0001", self.FINISHED)
        self.make("INIT-0002", self.FINISHED)
        self.assertEqual(store.find_initiative(self.root).id, "INIT-0002")

    def test_an_explicit_id_wins_over_the_active_initiative(self):
        self.make("INIT-0001", self.FINISHED)
        self.make("INIT-0002")
        self.assertEqual(store.find_initiative(self.root, "INIT-0001").id,
                         "INIT-0001")

    def test_the_auto_selected_initiative_is_version_checked(self):
        idir = self.make("INIT-0001")
        meta = must(store.read_json(P.meta_file(idir)))
        meta["engine_version"] = "99.0.0"
        store.write_json(P.meta_file(idir), meta)
        with self.assertRaises(ExecError) as err:
            store.find_initiative(self.root)
        self.assertEqual(err.exception.code, "engine_too_old")

    def test_a_version_skew_is_refused_when_finding_by_id(self):
        store.init_store(self.root, "INIT-0001", "t")
        meta = must(store.read_json(P.meta_file(self.idir)))
        meta["engine_version"] = "99.0.0"
        store.write_json(P.meta_file(self.idir), meta)
        with self.assertRaises(ExecError) as err:
            store.find_initiative(self.root, "INIT-0001")
        self.assertEqual(err.exception.code, "engine_too_old")


class RepoRootTests(TmpCase):
    def test_finds_the_nearest_ancestor_with_a_git_dir(self):
        (self.root / ".git").mkdir()
        nested = self.root / "a" / "b"
        nested.mkdir(parents=True)
        self.assertEqual(store.repo_root(nested), self.root.resolve())

    def test_a_git_file_marks_a_worktree_root(self):
        (self.root / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
        self.assertEqual(store.repo_root(self.root), self.root.resolve())

    def test_defaults_to_the_current_directory(self):
        (self.root / ".git").mkdir()
        old = os.getcwd()
        self.addCleanup(os.chdir, old)
        os.chdir(self.root)
        self.assertEqual(store.repo_root(), self.root.resolve())

    def test_outside_any_repository_is_a_typed_error(self):
        real_exists = Path.exists

        def exists(path):
            return False if path.name == ".git" else real_exists(path)

        with mock.patch.object(Path, "exists", exists):
            with self.assertRaises(ExecError) as err:
                store.repo_root(self.root)
        self.assertEqual(err.exception.code, "exec_root")


if __name__ == "__main__":
    unittest.main()
