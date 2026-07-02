# UI-REVIEW-001 — Operator review of the console Onboard surface

> Status: BLOCKING for the operator end-to-end test (M2 acceptance).
> Source: operator (Daimon) walkthrough of the live console, 2026-07-02, Business Profile Intake page (v1.0 · Run #3).
> Scope: Onboard + Library pages and the intake/playbook run surface. No pipeline, schema, or charter changes — this is presentation and interaction only, but one finding (F3) changes what the console *is*, so read it first.

---

## The structural finding first

**F3 — The intake page is a document, not a session.**

The current page renders the playbook procedure as static text ("Q&A through console", "AI drafts: business summary…") with Approve / Reject / Park at the bottom. There is no input box, no upload, no way for the operator to actually *do* the intake. The playbook markdown is the machine's script — it was never meant to be the UI. Rendering it verbatim to the operator inverts the design: the human is shown the machinery and given nothing to say.

**Required interaction model.** Every intake and playbook run is a conversational AI session. One reusable session component, config-driven (generic harness rule applies — nothing StackPenni-specific in the component):

1. **Chat transcript pane.** The AI opens by asking the first question from the playbook's Q&A. One question at a time, grill-session format — the same format INTAKE-USER1 used and that already worked on the operator. The AI ingests whatever it's given, asks clarifying follow-ups when an answer is thin or ambiguous, and moves on when it has enough. It never dumps the full question list at once.
2. **Input box.** Multiline text entry. The operator can answer the question asked, or paste anything — a brand doc, a rant, a half-formed thought. The AI's job is to ingest whatever arrives and route it, not to demand answers in a fixed shape.
3. **Add files button.** Uploads (docs, exports, images) attach into the session and are ingested as intake material. This is the console's version of "accepts uploads/pastes" already specified in the playbooks.
4. **Voice input** is deliberately absent for now — mic button hidden or stubbed until T2.6–T2.8 land per the recorded deferral. Do not build a placeholder that looks broken.
5. **Readback → gate.** When the AI has enough, it presents the draft *in the chat, in plain language*: "Here's what I understood — correct anything." The operator can reply conversationally OR edit the draft text directly (direct editing is authoritative input per the approved DIVERGENCE-001 amendment). Only when the operator is satisfied do Approve / Reject / Park appear, attached to the readback — not floating at the bottom of a procedure list.
6. **Progress rail.** The playbook's steps survive only as a slim progress indicator (e.g. "Step 2 of 4 — drafting") so the operator knows where they are. The steps are status, not content.

Acceptance for this finding: the operator can complete the Business Profile Intake end-to-end from the console by typing answers and uploading at least one file, and the approved output lands in `config/business.yaml` + the brand context module exactly as the playbook specifies. This is the M2 acceptance checkpoint made concrete.

---

## The remaining findings

**F1 — Playbook ordering contradicts its own instruction.** The listing says to go in order, but Audience Builder sits at the top and Business Profile Intake — whose own purpose line says it "runs FIRST — every other playbook reads its output" — is buried. Cards must carry an explicit run-order number and be sorted by it. The order comes from config (a `run_order` field per playbook), not from alphabetical or creation order. A playbook whose prerequisites haven't been approved yet should render as visibly locked/pending, not equally clickable.

**F2 — Text truncation and duplication.** Step titles clip mid-word ("correct anythi", "the tag allowlist the") and the bold title is just a truncated copy of the description shown immediately below it — the same sentence twice, once broken. Fix both: titles wrap rather than clip, and a step shows *either* a short deliberate title with the description beneath *or* the description alone. Never a truncated echo. (This becomes moot on the intake page once F3 lands, but the same rendering component likely appears in the Library and gate queue — fix it at the component.)

**F4 — Machine-facing copy in the operator's view.** "Gate → write `business.yaml` + `modules/{biz}/brand-context.md`" is a note to the machine leaked onto the operator's screen. A non-developer meeting this cold would stall. Human-facing copy for that moment: **"Review your business profile — approve to save it."** File paths, module targets, and playbook internals move to a collapsible "technical details" element and the provenance log. Rule to apply console-wide, not just here: **every string the operator reads is written for a business owner; every string the machine reads lives in the playbook and config.** Where a playbook step needs an operator-facing label, add a `display_label` field to the playbook step schema rather than exposing the internal step text.

---

## Principle to codify (CONTEXT.md)

Add to CONTEXT.md so this doesn't regress in later milestones:

> **The console renders sessions, not documentation.** Playbook markdown is the machine's script. The operator's surface is always: AI asks → operator gives anything (text, paste, files) → AI clarifies → AI drafts → plain-language readback → gate. The AI is present at every stage; the operator is never handed a form or a procedure to execute manually.

This is the UI expression of the standing charter principle: the human originates seeds and reacts at gates — any surface that positions the human as an executor of procedure is a red flag, same class of error as positioning them as a content producer.

---

## Acceptance checks (all must pass before the operator end-to-end test re-runs)

1. Onboard/Library cards are numbered, sorted by `run_order`, Business Profile Intake first.
2. No truncated text anywhere in the playbook/step rendering at 1280px+ width.
3. Business Profile Intake runs as a chat session: question-at-a-time, text input, file upload, clarifying follow-ups, plain-language readback, gate on the readback.
4. Direct edits to the readback draft are captured as authoritative input.
5. Zero file paths or module targets visible in the default operator view; all reachable under a technical-details disclosure.
6. Progress rail reflects playbook steps as status only.
7. The session component is generic — driven entirely by the playbook config, no StackPenni-specific logic in the component.
