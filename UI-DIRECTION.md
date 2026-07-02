# UI Direction — The Console

*Repo location: `docs/UI-DIRECTION.md`. Direction for Hermes when building console screens. Evolves the existing Flask review app. v1.0*

## Principles

1. **Mobile-first.** The operator runs this from a phone. Every screen works one-handed on a phone; desktop is the bonus, not the target.
2. **The person's verbs are: speak, tap, react, approve.** No screen ever asks the person to compose or edit text. If a flow needs typed prose from the person, the flow is wrong — redesign it as a reaction or a voice note.
3. **Reactions are first-class input.** Reacting to a draft line = tap the line → quick chips (**not me · too polished · flat · too long · keep · love it**) + optional voice note for anything nuanced. Every reaction writes to the Feedback Log with the draft version it applied to.
4. **Gates are card stacks.** One proposal per card: the proposed change, the evidence, the exact diff. Swipe/tap: approve · reject (with quick reason chips) · park. A weekly gate session must be finishable in one sitting on a phone.
5. **Voice in, everywhere.** Anywhere the person provides input (seeds, reactions, interview answers, corrections), a record button sits next to it. Spoken input is preferred by design, not a fallback.
6. **Status always visible.** The person can always see: what the system is doing now, what's waiting on them, what shipped, what's scheduled. No mystery states.
7. **Evidence beside every AI claim.** A proposed pattern shows the reactions/results that support it; a proposed source shows the sample item and matched criteria; a flagged draft line shows which Tells Checklist rule flagged it.
8. **Boring web tech.** Server-rendered Flask + minimal JS. No SPA framework. Fast on island bandwidth.

## The five surfaces

### 1. Onboard (runs once per business; M1–M2)
Wizard driven by the playbook runner: intake checklist (upload/paste/record per material type, progress shown against `docs/INTAKE-USER1.md`) → playbook chain runs → calibration screens (e.g., Voice: 3 samples side-by-side, tap closest, chip/speak what's off) → per-playbook confirmation gates. Exit state: all 8 modules at v1, `business.yaml` + `sources.yaml` written.

### 2. Create (the co-production loop; M3)
- **Seed capture:** big record button + paste field. A seed = 30 seconds of talking. Seeds land in a seed list with AI-suggested pairings from the Source Bank and approved experiments from the Experiments Queue.
- **Draft view:** the draft with self-audit flags inline (flagged lines subtly marked; tap to see which tell fired). Per-line reaction chips + voice note. One button: **revise with my reactions**. Then **ship** (→ Publish queue) or **kill** (chip for why).
- Target: 15–20 minutes of the person's time per piece, tracked and shown.

### 3. Review (the existing source queue, evolved; M2/M6)
The current approve/reject/park queue for ingested items, plus: criteria-match score per item, bulk actions by group, and a "proposed new sources" tab fed by the Sources Engine loop (each with evidence + sample item).

### 4. Gate (the weekly sitting; M5)
Card stack of all pending proposals across the system: module updates, new/pruned sources, criteria amendments, experiments. Grouped by module, evidence on every card, exact diff shown. Approve = version bump with provenance, automatically. A counter shows "N cards left"; the design goal is zero cards in under 20 minutes.

### 5. Library (transparency; M2+)
Read-only browse of: the 8 modules with version history and provenance per entry · Source Bank with scores · shot library index · Feedback Log · provenance log per published piece ("which prompt, which model, which module versions made this"). This is where trust in the system lives — the person can always read what the machine believes and why.

## Build sequencing for Hermes
M1: Onboard (Voice path + calibration). M2: Onboard (remaining playbooks) + Library v0 + Review evolution. M3: Create. M4: Publish status in Create/Library. M5: Gate. M6: Review's proposed-sources tab + Experiments in Create. Screens land ugly-but-working first; polish is never a milestone blocker.
