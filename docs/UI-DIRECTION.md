# UI Direction — The Console

*Repo location: `docs/UI-DIRECTION.md`. Direction for Hermes when building console screens. v1.1 — 2026-07-02 — patched per `docs/reviews/review-divergence-001.md` (laptop-first, voice available not assumed, direct-edit mode).*

## Principles

1. **Laptop-first (1280px+), responsive to mobile.** Mobile-friendly is a hard requirement for future customers, not an afterthought — but it does not constrain the primary design. Multi-column layouts allowed on laptop.
2. **The person's verbs are: speak, type, tap, react, edit, approve.** The system defaults to AI production but supports and encourages direct editing when the person chooses to write or rewrite draft text.
3. **Reactions are first-class input.** Reacting to a draft line = tap the line → quick chips (**not me · too polished · flat · too long · keep · love it**) + typed text for anything nuanced. Every reaction writes to the Feedback Log with the draft version it applied to.
4. **Gates are a persistent async queue.** One proposal per card: the proposed change, the evidence, the exact diff. Tap/click: approve · reject (with quick reason chips) · park. No deadline or pressure mechanics — the person clears when ready. Every card shows age ("submitted N days ago"); newer proposals on the same module section supersede older ones (marked, not deleted).
5. **Voice in, everywhere — available at every input, assumed at none.** Typed text and chips are equal citizens. A record button sits next to every input point, but the person is never required to use it.
6. **Status always visible.** The person can always see: what the system is doing now, what's waiting on them, what shipped, what's scheduled. No mystery states.
7. **Evidence beside every AI claim.** A proposed pattern shows the reactions/results that support it; a proposed source shows the sample item and matched criteria; a flagged draft line shows which Tells Checklist rule flagged it.
8. **Boring web tech.** Server-rendered Flask + minimal JS. No SPA framework. Fast on island bandwidth.

## The five surfaces

### 1. Onboard (runs once per business; M1–M2)
Wizard driven by the playbook runner: intake checklist (upload/paste/record per material type, progress shown against `docs/INTAKE-USER1.md`) → playbook chain runs → calibration screens (e.g., Voice: 3 samples side-by-side, tap closest, chip/speak what's off) → per-playbook confirmation gates. Exit state: all 8 modules at v1, `business.yaml` + `sources.yaml` written.

### 2. Create (the co-production loop; M3)
- **Seed capture:** paste field + record button. A seed = 30 seconds of talking or a typed idea. Seeds land in a seed list with AI-suggested pairings from the Source Bank and approved experiments from the Experiments Queue.
- **Draft view:** the draft with self-audit flags inline (flagged lines subtly marked; click to see which tell fired). Two input modes side by side:
  - **Reaction mode:** per-line reaction chips + typed text. One button: **revise with my reactions**.
  - **Direct-edit mode:** the draft text is editable. Human text is authoritative — it overrides the AI draft. Edits are logged to the Feedback Log at the highest weight with the draft version. The system encourages this mode; it's the strongest voice signal.
- Then **ship** (→ Publish queue, after per-piece approval) or **kill** (chip for why).
- Target: 15–20 minutes of the person's time per piece, tracked and shown.

### 3. Review (the existing source queue, evolved; M2/M6)
The current approve/reject/park queue for ingested items, plus: criteria-match score per item, bulk actions by group, and a "proposed new sources" tab fed by the Sources Engine loop (each with evidence + sample item).

### 4. Gate (the async queue; M5)
Card stack of all pending proposals across the system: module updates, new/pruned sources, criteria amendments, experiments. Grouped by module, evidence on every card, exact diff shown. Approve = version bump with provenance, automatically. A counter shows "N pending"; every card shows age ("submitted N days ago"); newer proposals on the same module section supersede older ones (marked, not deleted). No deadline or pressure mechanics — the person clears when ready.

### 5. Library (transparency; M2+)
Read-only browse of: the 8 modules with version history and provenance per entry · Source Bank with scores · shot library index · Feedback Log · provenance log per published piece ("which prompt, which model, which module versions made this"). This is where trust in the system lives — the person can always read what the machine believes and why.

## Build sequencing for Hermes
M1: Onboard (Voice path + calibration). M2: Onboard (remaining playbooks) + Library v0 + Review evolution. M3: Create. M4: Publish status in Create/Library. M5: Gate. M6: Review's proposed-sources tab + Experiments in Create. Screens land ugly-but-working first; polish is never a milestone blocker.
