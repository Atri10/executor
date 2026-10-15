# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The journal is the truth, so it is attacked exhaustively, not by example.

The safety property: no corruption of a committed journal can change what the
engine believes without being noticed. "Noticed" means the scan counted a torn
line or the hash chain reported a problem. A corruption that changes nothing
observable (a space swapped for a tab) is allowed; a silent change is a bug.

  * every byte, replaced several ways, one position at a time
  * seeded random multi-byte damage
  * a crash at every possible byte offset of the file, then recovery: the
    surviving events must be an exact prefix and the next append must heal it
  * every reordering, duplication and deletion of whole events

One limit is pinned on purpose, not hidden: the chain proves internal
consistency, not completeness. Deleting the newest event(s) leaves a valid
shorter chain. The committed export in docs/executor is the external anchor.
"""
from __future__ import annotations

import itertools
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from executor import paths as P, store  # noqa: E402

DATAS = [
    {"title": "plain"},
    {"title": "café — ünïcode ✓ 🚀"},
    {"nested": {"a": [1, 2, {"b": None}], "t": True, "f": 1.5}},
    {"text": 'quote " backslash \\ newline \n tab \t end'},
    {},
]
WHITESPACE_SWAPS = (0x09, 0x0D)


def parses_as_event(line: bytes) -> bool:
    try:
        ev = json.loads(line)
    except ValueError:
        return False
    return isinstance(ev, dict) and isinstance(ev.get("seq"), int)


class JournalCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # durability (fsync) is asserted in test_store; inside these
        # exhaustive loops it would only make them crawl
        fsync = mock.patch.object(store.os, "fsync")
        fsync.start()
        self.addCleanup(fsync.stop)
        self.idir = P.init_dir(Path(tmp.name), "INIT-0001")
        for i, data in enumerate(DATAS):
            ev = store.make_event(
                self.idir, "engine" if i % 2 else "worker", "emit",
                "INIT-0001", data,
                dispatch_id="D00007" if i == 2 else None,
                payload_sha=store.sha256(data) if i == 3 else None)
            store.append_event(self.idir, ev)
        self.path = P.journal_file(self.idir)
        self.raw = self.path.read_bytes()
        self.base, torn = store.scan_journal(self.idir)
        self.lines = self.raw.split(b"\n")[:-1]
        # the fixture itself must be a clean, complete chain
        self.assertEqual((len(self.base), torn), (len(DATAS), 0))
        self.assertEqual(store.verify_chain(self.base), [])
        self.assertEqual(len(self.lines), len(DATAS))

    def load(self, raw: bytes):
        """What the engine would make of these bytes: (events, torn,
        problems). In memory on purpose: a file open costs milliseconds on
        some machines, and the parser is pure."""
        events, torn = store.parse_journal(raw)
        return events, torn, store.verify_chain(events)

    def crash_points(self) -> list[int]:
        """Where the file-backed recovery test cuts. A crash can stop the file
        at any byte, but recovery touches the filesystem, so it is driven at
        every line boundary (and the bytes around it) plus a stride through
        each line. Every single offset is covered in memory, above."""
        ends, at = [], 0
        for line in self.lines:
            at += len(line) + 1
            ends.append(at)
        picks = {e + d for e in ends for d in range(-3, 4)}
        picks |= set(range(0, len(self.raw) + 1, 29)) | {0, len(self.raw)}
        return sorted(p for p in picks if 0 <= p <= len(self.raw))

    def observable_change(self, raw: bytes) -> bool:
        """True when the engine would see something different. Asserts that
        whatever it sees differently was also reported."""
        events, torn, problems = self.load(raw)
        if events == self.base and not torn:
            return False
        self.assertTrue(torn or problems,
                        "silent corruption: the events changed and nothing "
                        "was reported")
        return True


class ByteCorruptionTests(JournalCase):
    def replacements(self, byte: int):
        return {byte ^ 0x01, byte ^ 0x80, 0x09, 0x0A, 0x22} - {byte}

    def test_no_single_byte_change_goes_unnoticed(self):
        cosmetic = []
        total = 0
        for pos, byte in enumerate(self.raw):
            for repl in sorted(self.replacements(byte)):
                total += 1
                mutated = self.raw[:pos] + bytes([repl]) + self.raw[pos + 1:]
                if not self.observable_change(mutated):
                    cosmetic.append((pos, repl))
        self.assertGreater(total, 5000)
        # the only changes allowed to pass are whitespace swapped for other
        # JSON whitespace: a space, or the final newline (a mere terminator).
        # Nothing the engine would read differently.
        for pos, repl in cosmetic:
            with self.subTest(pos=pos, repl=repl):
                self.assertIn(repl, WHITESPACE_SWAPS)
                self.assertTrue(
                    self.raw[pos] == 0x20 or pos == len(self.raw) - 1,
                    "only a space or the final newline may change unnoticed")
        self.assertGreater(len(cosmetic), 0)        # the carve-out is real

    def test_deleting_any_single_byte_is_noticed(self):
        for pos in range(len(self.raw)):
            mutated = self.raw[:pos] + self.raw[pos + 1:]
            with self.subTest(pos=pos):
                self.observable_change(mutated)

    def test_inserting_any_single_byte_is_noticed(self):
        for pos in range(len(self.raw) + 1):
            for byte in (0x20, 0x7B, 0x30):
                mutated = self.raw[:pos] + bytes([byte]) + self.raw[pos:]
                with self.subTest(pos=pos, byte=byte):
                    self.observable_change(mutated)

    def test_random_multi_byte_damage_is_never_silent(self):
        rng = random.Random(0xBADC0DE)
        detected = 0
        for trial in range(1500):
            buf = bytearray(self.raw)
            for _ in range(rng.randint(1, 4)):
                buf[rng.randrange(len(buf))] = rng.randrange(256)
            with self.subTest(trial=trial):
                detected += self.observable_change(bytes(buf))
        self.assertGreater(detected, 1400)            # the fuzzer has teeth

    def test_arbitrary_bytes_never_crash_the_scan(self):
        rng = random.Random(7)
        for trial in range(300):
            blob = bytes(rng.randrange(256) for _ in range(rng.randrange(400)))
            with self.subTest(trial=trial):
                events, torn = store.parse_journal(blob)
                self.assertIsInstance(events, list)
                self.assertGreaterEqual(torn, 0)
                store.verify_chain(events)                 # must not raise


class CrashRecoveryTests(JournalCase):
    def expected_after_cut(self, cut: int):
        """(surviving events, torn count) for a file cut at byte `cut`,
        worked out from the raw bytes alone, independent of store.py."""
        head = self.raw[:cut]
        *whole, tail = head.split(b"\n")
        keep = len(whole) + (1 if tail and parses_as_event(tail) else 0)
        torn = 1 if tail and not parses_as_event(tail) else 0
        return self.base[:keep], torn

    def test_a_crash_at_every_offset_leaves_an_exact_prefix(self):
        for cut in range(len(self.raw) + 1):
            events, torn, problems = self.load(self.raw[:cut])
            want, want_torn = self.expected_after_cut(cut)
            with self.subTest(cut=cut):
                self.assertEqual(events, want)
                self.assertEqual(torn, want_torn)
                self.assertEqual(problems, [])         # a prefix is a chain

    def test_the_next_append_heals_a_crash_at_every_offset(self):
        for cut in self.crash_points():
            self.path.write_bytes(self.raw[:cut])
            before, torn_before = store.scan_journal(self.idir)
            ev = store.make_event(self.idir, "engine", "emit", "INIT-0001",
                                  {"after": "crash"})
            store.append_event(self.idir, ev)
            events, torn = store.scan_journal(self.idir)
            with self.subTest(cut=cut):
                self.assertEqual(events, [*before, ev])
                self.assertEqual(ev["seq"], len(before) + 1)
                self.assertEqual(torn, torn_before)    # the stub stays, once
                self.assertEqual(store.verify_chain(events), [])
                # and the journal keeps working after the heal
                again = store.make_event(self.idir, "engine", "emit",
                                         "INIT-0001", {"n": 2})
                store.append_event(self.idir, again)
                final, _ = store.scan_journal(self.idir)
                self.assertEqual(store.verify_chain(final), [])
                self.assertEqual(final[-1], again)

    def test_a_fragment_never_swallows_the_event_after_it(self):
        fragment = self.raw[:len(self.lines[0]) // 2]
        self.path.write_bytes(fragment)
        store.append_event(self.idir, store.make_event(
            self.idir, "engine", "emit", "INIT-0001", {"k": "v"}))
        events, torn = store.scan_journal(self.idir)
        self.assertEqual((len(events), torn), (1, 1))
        self.assertEqual(events[0]["data"], {"k": "v"})


class StructuralEditTests(JournalCase):
    def assemble(self, order) -> bytes:
        return b"\n".join(order) + b"\n"

    def test_every_reordering_is_reported(self):
        checked = 0
        for perm in itertools.permutations(range(len(self.lines))):
            if list(perm) == list(range(len(self.lines))):
                continue
            events, torn, problems = self.load(
                self.assemble([self.lines[i] for i in perm]))
            with self.subTest(perm=perm):
                self.assertEqual(torn, 0)
                self.assertTrue(problems)
            checked += 1
        self.assertEqual(checked, 119)

    def test_duplicating_any_event_anywhere_is_reported(self):
        for i in range(len(self.lines)):
            for j in range(len(self.lines) + 1):
                order = list(self.lines)
                order.insert(j, self.lines[i])
                _, _, problems = self.load(self.assemble(order))
                with self.subTest(copy=i, at=j):
                    self.assertTrue(problems)

    def test_deleting_any_event_but_the_newest_is_reported(self):
        for i in range(len(self.lines) - 1):
            order = [ln for k, ln in enumerate(self.lines) if k != i]
            _, _, problems = self.load(self.assemble(order))
            with self.subTest(deleted=i):
                self.assertTrue(problems)

    def test_deleting_the_newest_events_is_a_valid_shorter_chain(self):
        """The known limit: a chain cannot prove nothing was cut off its end.
        Completeness comes from the export committed to git, not from here."""
        for keep in range(len(self.lines)):
            events, torn, problems = self.load(
                self.assemble(self.lines[:keep]) if keep else b"")
            with self.subTest(keep=keep):
                self.assertEqual(events, self.base[:keep])
                self.assertEqual((torn, problems), (0, []))

    def test_replacing_an_event_with_another_chains_event_is_reported(self):
        other = store.make_event(self.idir, "engine", "emit", "INIT-0001",
                                 {"forged": True})
        forged = (json.dumps(other, ensure_ascii=False)).encode("utf-8")
        for i in range(len(self.lines)):
            order = list(self.lines)
            order[i] = forged
            _, _, problems = self.load(self.assemble(order))
            with self.subTest(replaced=i):
                self.assertTrue(problems)


if __name__ == "__main__":
    unittest.main()
