# CORRECTION — Onboarding Single Thread — v1.0

**Date:** 2026-07-02
**Author:** Claude (architect review), from Daimon's field report
**Applies to:** commit `5b12e45` (Add no-cache headers for HTML pages)
**Contains:** one P0 bug fix (ship immediately) and one architectural correction (redesign spec)

---

## Item 1 — P0 BUG: attach button (and send, and gate buttons) dead in session chat

### Symptom
Attach button in the onboarding chat does nothing. Reported as a regression: it worked before.

### Root cause
`src/templates/session.html` has a single `<script>` block (lines 217–513). `const playbookName` is declared **twice** in that block:

- Near the top (~line 220):
  ```javascript
  const runId = {{ run_id }};
  const playbookName = "{{ playbook_name }}";
  let pendingFiles = [];
  ```
- Again in the gate-actions section appended at the bottom (~line 467):
  ```javascript
  // Gate actions — route to the correct store endpoint based on playbook
  const playbookName = "{{ playbook_name }}";
  const storeEndpoints = { ... };
  ```

A duplicate `const` declaration in the same scope is a **SyntaxError** (`Identifier 'playbookName' has already been declared`). A syntax error prevents the browser from executing the *entire* script block — not just the duplicate line. Consequences:

- The IIFE that wires `attachBtn` via `addEventListener` never runs → attach button dead.
- `sendMessage`, `handleKey`, `autoGrow`, `approveGate`, `parkGate`, `rejectGate` are never defined → send button and gate buttons throw `ReferenceError` on click.
- The no-cache headers commit does not fix this, because the freshly served code is itself broken.

This regression was introduced when the store-endpoint routing block was added with its own copy of the declaration.

### Fix
Delete the second declaration. The gate-actions section should reuse the `playbookName` already in scope:

```diff
 // Gate actions — route to the correct store endpoint based on playbook
-const playbookName = "{{ playbook_name }}";
 const storeEndpoints = {
     "business-profile-intake": "/api/run/{{ run_id }}/store-business",
```

### Guardrail (recommended, cheap)
Add a smoke test that catches this whole class of bug: render `session.html` with dummy context and run the extracted `<script>` contents through `node --check` (or `esprima`/`acorn` parse in a pytest). A template whose JS does not parse should fail CI. This is the second time a template edit has silently killed page JS; a parse check ends the category.

---

## Item 2 — ARCHITECTURAL CORRECTION: onboarding is ONE conversation, not eight chats

### What exists now
`/onboard` (route at `app.py:119`) renders a hub of eight playbook cards, sorted by `run_order`, with sequential lock/unlock. Each card opens its **own run and its own chat** (`/onboard/<playbook>/<run_id>`), each with its own `ready_to_draft` loop scoped to a single playbook (`/api/session/<run_id>/message`).

### Why this is wrong
This is eight interviews in a trench coat. It positions the human as a process-follower marching through steps, which violates the charter's core stance: the human originates seeds and reacts at gates; the *system* carries the process. Concretely:

1. **Seeds don't respect step order.** While answering voice questions, Daimon will drop a story that belongs in Story Frameworks and an audience observation that belongs in Audience Insights. In the current design those seeds are trapped in the wrong run's `collected_inputs`, invisible to the playbook that needs them.
2. **Repetition.** Eight scoped conversations re-ask for context the human already gave, because each run's history is siloed.
3. **The lock chain is a fiction.** The docs have soft dependencies (voice informs format), not hard ones. Hard sequential locking converts soft dependencies into forced ceremony.
4. **It contradicts INTAKE-USER1's promise** of one-session onboarding. One session should mean one conversation, not one sitting spent opening eight chats.

### Target design

**One onboarding conversation per business.** A single persistent run (`playbook_name = "onboarding"`, one row, reused forever). Opening `/onboard` opens that conversation directly — the hub page is retired as an entry point.

**Coverage map as first-class state.** In `collected_inputs`, maintain:

```json
{
  "coverage": {
    "business-profile-intake":   {"status": "approved",   "doc_version": "1.0"},
    "voice-profile-builder":     {"status": "drafted"},
    "sources-engine":            {"status": "collecting", "gaps": ["no competitor accounts named"]},
    "viral-patterns-starter":    {"status": "empty"},
    "audience-insights-builder": {"status": "collecting"},
    "story-frameworks-starter":  {"status": "empty"},
    "format-guide-starter":      {"status": "empty"},
    "visual-style-intake":       {"status": "empty"}
  }
}
```

Statuses: `empty → collecting → ready → drafted → approved`. The eight playbooks stop being chat destinations and become **spec sheets**: their `inputs` sections define what "ready" means per doc.

**Per-turn loop.** Every human message goes through one LLM call that receives: full conversation history, the coverage map, and the input requirements of all eight playbooks. Response schema replaces the current `{reply, ready_to_draft}`:

```json
{
  "reply": "string",
  "routed_seeds": [{"doc": "story-frameworks-starter", "seed": "the sou-sou payout story"}],
  "coverage_updates": [{"doc": "sources-engine", "status": "ready"}],
  "next_focus": "audience-insights-builder"
}
```

The AI's job each turn: route whatever the human said to every doc it touches (a single answer can feed three docs), update coverage, and either ask the single highest-leverage next question or announce that a doc is ready to draft.

**Inline drafting and gating.** When a doc hits `ready`, reuse the existing per-playbook analysis routing (`_session_trigger_analysis` already dispatches by playbook name — keep it) and render the readback as a **gate card inside the conversation**, with the existing approve / edit-directly / park actions. Approval stores the module exactly as today. The conversation continues around the card; other docs keep collecting. This preserves the async-gate-queue principle: gates surface in the thread when ready, not on a schedule.

**Resume behavior.** On reopening `/onboard`, the AI's first message is a short recap: what's approved, what's in flight, what's untouched, and one suggested next question. One shot or ten sittings — same thread, no ceremony.

**Progress rail replaces the hub.** The eight cards become a slim sidebar (or collapsible header on narrow widths — but remember: laptop-first) showing each doc's status chip. Clicking a chip does not open a new chat; it tells the AI "focus here next" by posting a focus message into the same conversation.

**Uploads.** Attach stays global to the conversation. The router tags each upload to relevant docs the same way it routes text seeds (a screenshot of a competitor post feeds viral-patterns *and* format-guide).

### Migration
- Keep `/onboard/<playbook>/<run_id>` routes alive read-only for any existing runs, but stop creating new per-playbook runs.
- Existing completed modules (approved docs) seed the coverage map as `approved` — do not re-interview for what's already stored.
- New prompt file: `prompts/session/onboarding_orchestrator_v1.md`, superseding `generic_converse_v1.md` for the onboarding surface. The generic converse prompt can remain for any future non-onboarding session use.
- Raise the `conversation_so_far[:4000]` truncation for the orchestrator — a whole-onboarding thread will exceed 4k chars fast. Summarize-then-truncate (rolling summary of older turns + verbatim recent turns) rather than hard slicing, or the AI will forget early seeds, which defeats the entire point.

### Acceptance criteria
1. Opening `/onboard` lands directly in the single conversation (new or resumed), never on a card hub.
2. A single human message containing material for three docs updates coverage on all three.
3. A doc reaching `ready` produces an inline gate card without leaving the thread; approval stores the module identically to today.
4. Closing the browser mid-way and returning resumes the same thread with an accurate recap.
5. No sequential locks anywhere. The AI may *suggest* order via `next_focus`; it may not enforce it.
6. Attach and send work (Item 1 fix landed, JS parse check in CI).

---

## Priority
- **Item 1**: ship today. It blocks all onboarding use.
- **Item 2**: next review tag. Item 1 must not wait for Item 2.
