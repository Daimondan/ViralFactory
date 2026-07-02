# UI Direction — The Console

*Repo location: `docs/UI-DIRECTION.md`. Direction for Hermes when building console screens. v1.3 — 2026-07-02 — patched per UI-REVIEW-001 (F3 session interaction model, F4 copy rule, Onboard surface redesigned as conversational sessions not procedure documents).*

## Principles

1. **Laptop-first (1280px+), responsive to mobile.** Mobile-friendly is a hard requirement for future customers, not an afterthought — but it does not constrain the primary design. Multi-column layouts allowed on laptop.
2. **The person's verbs are: speak, type, tap, react, edit, approve.** The system defaults to AI production but supports and encourages direct editing when the person chooses to write or rewrite draft text.
3. **Reactions are first-class input.** Reacting to a draft line = tap the line → quick chips (**not me · too polished · flat · too long · keep · love it**) + typed text for anything nuanced. Every reaction writes to the Feedback Log with the draft version it applied to.
4. **Gates are a persistent async queue.** One proposal per card: the proposed change, the evidence, the exact diff. Tap/click: approve · reject (with quick reason chips) · park. No deadline or pressure mechanics — the person clears when ready. Every card shows age ("submitted N days ago"); newer proposals on the same module section supersede older ones (marked, not deleted).
5. **Voice in, everywhere — available at every input, assumed at none.** Typed text and chips are equal citizens. A record button sits next to every input point, but the person is never required to use it.
6. **Status always visible.** The person can always see: what the system is doing now, what's waiting on them, what shipped, what's scheduled. No mystery states.
7. **Evidence beside every AI claim.** A proposed pattern shows the reactions/results that support it; a proposed source shows the sample item and matched criteria; a flagged draft line shows which Tells Checklist rule flagged it.
8. **Boring web tech.** Server-rendered Flask + minimal JS. No SPA framework. Fast on island bandwidth.
9. **The console renders sessions, not documentation.** Playbook markdown is the machine's script. The operator's surface is always: AI asks → operator gives anything (text, paste, files) → AI clarifies → AI drafts → plain-language readback → gate. The AI is present at every stage; the operator is never handed a form or a procedure to execute manually. (UI-REVIEW-001 F3)
10. **Every string the operator reads is written for a business owner.** File paths, module targets, and playbook internals are never visible in the default operator view — they live in a collapsible "technical details" element and the provenance log. Where a playbook step needs an operator-facing label, use `display_label`. (UI-REVIEW-001 F4)

## The five surfaces

### 1. Onboard (runs once per business; M1–M2)
**Conversational sessions, not procedure documents (UI-REVIEW-001 F3).** Each playbook runs as an AI-driven chat session through one reusable, config-driven session component:

1. **Chat transcript pane.** The AI opens by asking the first question from the playbook's Q&A. One question at a time — grill-session format. The AI ingests whatever it's given, asks clarifying follow-ups when an answer is thin or ambiguous, and moves on when it has enough.
2. **Input box.** Multiline text entry. The operator can answer the question asked, or paste anything — a brand doc, a rant, a half-formed thought.
3. **Add files button.** Uploads (docs, exports, images) attach into the session and are ingested as intake material.
4. **Voice input** — deferred per T2.6–T2.8. Mic button hidden or stubbed, not broken-looking.
5. **Readback → gate.** When the AI has enough, it presents the draft in the chat, in plain language: "Here's what I understood — correct anything." The operator can reply conversationally OR edit the draft text directly (direct editing is authoritative). Approve / Reject / Park appear attached to the readback, not floating at the bottom of a procedure list.
6. **Progress rail.** The playbook's steps survive only as a slim progress indicator ("Step 2 of 4 — drafting"). Steps are status, not content.

Playbook cards on the Onboard landing page are numbered and sorted by `run_order` from config. A playbook whose prerequisites haven't been approved yet renders as locked/pending. Exit state: all 8 modules at v1, `business.yaml` + `sources.yaml` written.

### 2. Create (the co-production loop; M3)
- **Ideas queue view:** cards from three origins (ai-originated, human-seeded, human-seeded-ai-developed), each tagged with an origin badge. Each card shows: the idea, hook/title options, suggested format, and evidence links. Per-card actions: approve / kill / park (Gate 1 — rigorous). Kill reasons logged to Feedback Log. This is the top of the funnel — most cards die here by design.
- **Seed capture:** paste field + record button. A seed = 30 seconds of talking or a typed idea. Seeds become human-seeded (or human-seeded-ai-developed) idea cards. AI-suggested pairings from the Source Bank and approved experiments from the Experiments Queue appear alongside.
- **Draft view:** the draft with self-audit flags inline (flagged lines subtly marked; click to see which tell fired). Draft = full text in voice + light visual direction (image prompts, reference notes, shot/format choices). **No rendered images at this stage.** Two input modes side by side:
  - **Reaction mode:** per-line reaction chips + typed text. One button: **revise with my reactions**.
  - **Direct-edit mode:** the draft text is editable. Human text is authoritative — it overrides the AI draft. Edits are logged to the Feedback Log at the highest weight with the draft version. The system encourages this mode; it's the strongest voice signal.
- Then **ship-forward** (→ Assets stage) or **kill** (chip for why).
- **Assets review view:** for ship-forward drafts only — real images generated per the visual direction, captions rendered, per-platform variants (X thread, IG carousel/reel, …) shown side by side. Per-variant actions: approve / fix / kill (Gate 3 — quick, per platform). Approved variants flow to Publish (Gate 4: go/hold + timing).
- Target: 15–20 minutes of the person's time per piece, tracked and shown.

### 3. Review (the existing source queue, evolved; M2/M6)
The current approve/reject/park queue for ingested items, plus: criteria-match score per item, bulk actions by group, and a "proposed new sources" tab fed by the Sources Engine loop (each with evidence + sample item).

### 4. Gate (the async queue; M5)
Card stack of all pending proposals across the system: module updates, new/pruned sources, criteria amendments, experiments. Grouped by module, evidence on every card, exact diff shown. Approve = version bump with provenance, automatically. A counter shows "N pending"; every card shows age ("submitted N days ago"); newer proposals on the same module section supersede older ones (marked, not deleted). No deadline or pressure mechanics — the person clears when ready.

### 5. Library (transparency; M2+)
Read-only browse of: the 8 modules with version history and provenance per entry · Source Bank with scores · shot library index · Feedback Log · provenance log per published piece ("which prompt, which model, which module versions made this"). This is where trust in the system lives — the person can always read what the machine believes and why.

## Build sequencing for Hermes
M1: Onboard (Voice path + calibration). M2: Onboard (remaining playbooks) + Library v0 + Review evolution. M3: Create (Ideas queue + Draft + Assets review — staged pipeline per AMENDMENT-003). M4: Publish status in Create/Library. M5: Gate. M6: Review's proposed-sources tab + Experiments in Create. Screens land ugly-but-working first; polish is never a milestone blocker.
