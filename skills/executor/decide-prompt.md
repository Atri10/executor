# Decide Dispatch Template

Use this when a question the engine cannot answer from a script blocks a
lane, and the question is genuinely a `decision` — a choice between
defensible options. The DECIDE agent answers it, and the answer becomes a
ruling with a record of who made it.

If the answer is a constraint the human already stated, it is a `rule` and
belongs in a `rulings.md` entry written directly — dispatching an agent to
echo it wastes a context window and buries a settled fact under a
deliberation. If the answer is "stop", use `exec-ruling --stop` and skip
this role entirely.

Fill every `[BRACKET]`. An unfilled bracket is a defect — the subagent has no
session history to infer it from.

```text
Subagent (general-purpose):
  description: "Decide [QUESTION_SUMMARY] for [LANE]"
  agent_identity: "[DECIDE-<scope> — e.g. DECIDE-P01-T03. Must match the dispatches.md Agent cell.]"
  model: [MODEL — REQUIRED. Choose per the phase skill's Model Selection.]
  prompt: |
    ## Identity

    | Field | Value |
    |---|---|
    | Initiative | [INIT-NNNN] |
    | Lane | [LANE — the task or phase this decision blocks] |
    | Question | [QUESTION — verbatim, not paraphrased] |
    | Options | [OPTIONS — the defensible choices, with what each costs] |
    | Evidence | [absolute paths of the artifacts and logs you may read] |
    | Rulings log | [absolute path of the rulings.md you append to via exec-ruling] |

    Every ID above belongs to [INIT-NNNN]. Do not reference an ID from any
    other initiative anywhere in your work or your ruling.

    ## What You Are Deciding

    [QUESTION] — the human or a gate needs this settled before the lane can
    move, and no script can settle it because the options are defensible on
    more than one axis.

    Read [EVIDENCE] before deciding. The options as stated above are a
    summary; the artifacts are the actual constraint. If they disagree, the
    artifacts win and you record the divergence.

    ## How to Decide

    1. **Name the axis.** Every real decision here trades something against
       something. Write down what is being traded before you pick. A
       decision with no axis is a preference, and preferences do not belong
       in a ruling.
    2. **Weigh against the binding constraints**, not against taste. The
       global constraints in the spec and the rulings already recorded are
       the yardstick; if your choice violates one, either the ruling is
       wrong or the constraint is — say which, and do not quietly ignore it.
    3. **Prefer the reversible option** when the axis is close and the
       options differ mainly in cost to undo. Reversibility is a real
       property; say you are using it.
    4. **Decide.** A ruling that only lays out the options has moved nothing.

    ## What You May Not Do

    - Do not edit the artifacts the decision is about. You rule; the next
      actor acts.
    - Do not expand scope. A decision that quietly enlarges the work is
      not a decision, it is a scope change wearing one.
    - Do not pass a gate or advance a phase.

    ## Self-Critique Before You Return

    1. Did you read the evidence, or decide from the options summary alone?
    2. Would the losing option's advocate find your reason stated fairly?
    3. Is your stated axis one the artifacts actually care about?
    4. Have you recorded the cost if you are wrong, concretely — not
       "rework may be needed"?

    ## Verification

    - Your ruling is recorded with `exec-ruling`, carrying the question
      verbatim and the cost if wrong. Paste the path the script printed.
    - Every factual claim you make about the evidence cites a file you read.
    - You modified no artifact: confirm with `git status --short` that your
      ruling is the only file you wrote.

    ## What You Return

    Return exactly these four things, in this order:

    1. **Status** — `DONE`, `DONE_WITH_CONCERNS`, or `BLOCKED`.
    2. **Decision** — the choice, in one sentence, plus the axis it traded
       on.
    3. **Ruling** — the path of the ruling you recorded.
    4. **Concerns** — anything the evidence made you doubt, and what would
       change your answer. `None` if genuinely none.

    Do not paste the artifacts' content back to the controller. The
    controller does not read artifacts; that is the point.
```

**Placeholders**

| Placeholder | Fill with |
|---|---|
| `[QUESTION]` | The question verbatim, exactly as asked |
| `[QUESTION_SUMMARY]` | One line for the dispatch description |
| `[LANE]` | The task or phase this decision blocks |
| `[OPTIONS]` | The defensible choices and what each costs |
| `[EVIDENCE]` | Absolute paths of the artifacts and logs you may read |
| `[RULINGS_LOG]` | Absolute path of the `rulings.md` you append to |
| `[MODEL]` | The model to dispatch, per the phase skill's Model Selection |
