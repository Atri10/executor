# Revive Preamble

This is a **preamble fragment**, not a dispatch template. The controller
prepends it to a worker's existing prompt when `executor next` emits a
`DISPATCH` re-using an abandoned lane — that is, when a dispatched worker
stopped signalling and the engine re-minted the slot.

Do not dispatch this. Do not register it as a role. It has no identity of
its own: the reviving worker keeps the task it already has, and the new
dispatch's `D<NNNNN>` records which rung of the ladder it came from.

## Why the wording is what it is

A worker that stopped mid-task has usually left real work on disk. The
failure mode this preamble exists to prevent is the resumed agent reading
its own half-finished state, deciding it looks wrong, and rewriting it —
destroying hours of correct work and producing a second, different artifact
at the same path, which then reads as tampering to every audit downstream.

So the instruction is not "continue the task". It is "establish what is
already true before you change anything".

## The fragment

```
## You Are Resuming — Establish the State Before You Change Anything

You were dispatched for this task before and stopped signalling. Your
previous context may or may not still be intact. Treat everything on disk
as more authoritative than your recollection: the filesystem is the record
of what happened, your memory of it is not.

Before you write anything:

1. **Read what is already there.** The prior `impl/*.report.json` payloads,
   the task branch, and any partial diff. Determine which of these are true:
   - work is complete or nearly so, and the failure was only in reporting;
   - work is partially done and coherent — continue from where it stops;
   - work is partially done and incoherent — say so explicitly and repair
     only what is incoherent;
   - nothing usable exists — say that, and start clean.
2. **Never rewrite work you did not check.** If a file already contains an
   implementation, it is not a starting point to overwrite; it is a claim
   to verify. Deleting or regenerating it without stating that you did so
   and why is a defect even when the result is better.
3. **Do not re-run a whole task because you lost your place.** A partial
   run that was going fine is cheaper to finish than to restart, and a
   restart discards the reasoning that produced it.
4. **Your report must state which case above applied.** A resumed agent
   that does not say what state it found gives the reviewer no way to tell
   a resume from a silent rewrite.

The engine decided to run this lane again because the liveness signals went
quiet — not because the work was judged wrong. If you believe the work on
disk should be discarded, say so in your report and let the reviewer rule
on it; do not discard it unilaterally.
```

## Placeholders

| Placeholder | Fill with |
|---|---|
| *(none)* | The prior `impl/*.report.json` is named in the re-dispatch context |

## Rung differences

The same fragment is used for both rungs, because the instruction that
matters — verify before you overwrite — is identical. The rung changes what
happens around it, not what the worker is told:

| Rung | Emitted when | Controller action |
|---|---|---|
| revive | The worker died once and still holds its own context | Resume the same agent with the same identity and the new `respond_to` |
| redispatch | The worker was resumed and went silent again | Fresh agent on a new dispatch id; the prior report is in `context` so it does not start blind |

## Boundary

This preamble does not authorize the worker to change the task's
requirements, pass a gate, mark itself complete, or record a ruling. It
restates the return contract it already has; it does not widen it.
