# PROCESS: Definition of Done for Hermes

**File:** PROCESS-definition-of-done-v1.0.md
**Date:** 2026-07-03
**Status:** Operator ruling. Binding on all Hermes work from this date. To be referenced from CONTEXT.md.

---

## The rule

Hermes does not report work as done until Hermes has fully tested it — and "fully tested" includes a hands-on human-style UI test, not only the automated suite. The operator's first end-to-end run surfaced roughly a dozen defects that a passing test suite did not catch: a literal `{corpus}` placeholder reaching the LLM, raw Python dicts rendered to the operator, conversation history lost on reload, silent upload failures. Every one of these is invisible to unit tests and obvious within two minutes of actually using the product. The operator's time is the most expensive test harness in the system; it is reserved for judgment calls, not for discovering that a button doesn't work.

## What "done" requires, in order

1. **Automated suite passes.** All existing tests plus new tests covering the change. A change that cannot be covered by at least one automated test should say so explicitly and why.

2. **Human UI test.** Hermes opens the actual UI in a browser and exercises the changed surface as an operator would:
   - Navigate to it the way the operator would (from the console, not by pasting a deep URL).
   - Click every button and control on the changed surface; confirm each does what its label says.
   - If the change touches auth or entry flow: perform the login flow end to end, including the failure path (wrong credentials behave sanely).
   - If the change touches upload: upload a real file and watch the full lifecycle — indicator appears during upload, success state on completion, and force one failure (e.g., oversized or unsupported file) to confirm the error is visible and honest.
   - Read every operator-visible string produced by the change: no machine-facing copy, no raw data structures, no clipped or overflowing text at both desktop and narrow widths.
   - Reload the page mid-flow and confirm state survives.

3. **End-to-end pass when the change touches a flow.** If the change is part of onboarding, run onboarding start to finish with realistic inputs (real files, multi-paragraph answers), not minimal stubs. Thin inputs hide input-plumbing bugs — that is precisely how the drafting-starvation defect survived.

4. **Report format.** The done report states what was tested and how: which automated tests, which UI paths were manually walked, what inputs were used, and anything observed but out of scope (filed as a note, not silently ignored). "Tests pass" alone is not a done report.

## Boundary

This does not change the gate structure: Hermes testing its own work is a precondition for reporting done, not a substitute for the operator's review. The operator still gates. The point is that when the operator sits down to review, the trivial breakage layer has already been burned away.
