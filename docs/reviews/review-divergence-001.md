# Architect Review — DIVERGENCE-001

*Repo location: `docs/reviews/review-divergence-001.md` · Reviewer: Claude (architect) · 2026-07-02 window, reviewed 2026-07-01 conversation-time · Companion: `docs/CHARTER-v3.1.md` and `BUILD_PLAN.md` v1.1 (both supplied with this review)*

## Verdicts

**D1 — Direct edit: APPROVED.** The original "never produce" was an architect error — it over-corrected the owner's "I'm not good at making content" into a prohibition. Corrected framing: the system never *requires* the person to produce; it defaults to AI production; it supports and encourages direct editing. A direct edit is authoritative over the AI draft and is the strongest voice signal in the Feedback Log. One rule preserved: direct edits are *evidence* — the patterns extracted from them still reach the Voice Profile through the gate as proposals. No module updates itself from a single edit.

**D2 — Async gate queue: APPROVED with refinements.** The owner's rhythm wins. Refinements that preserve the intent of the old rule (preventing silent learning stalls):
- Every proposal card shows age ("submitted N days ago") — staleness visible, as Hermes proposed.
- **Superseding:** a newer proposal touching the same module section automatically marks the older one superseded (visible, not deleted).
- Principle, rewritten: *if the queue grows faster than it clears, the proposals are too weak or too many — fix the proposal prompt, never pressure the person.*

**D3 — Laptop-first: APPROVED.** Factual correction about the primary user. Laptop (1280px+) primary, responsive down to mobile; mobile-friendly is a hard requirement for future customers, not an afterthought. Voice input available everywhere but never assumed (see absorbed decisions below). Hermes: patch `docs/UI-DIRECTION.md` Principle 1 and Principle 5 accordingly (exact text in Actions).

**D4 — Generalization suggestive: APPROVED.** Costs nothing — config isolation from day 1 and the generic playbook runner were always the architecture. Multi-tenant UI, customer onboarding, and billing were never in the v1 plan. Phase 5 stays as the proof; its date floats.

**D5 — Fresh start: APPROVED with one flag.** New app, new DB, no v2 code/schema reuse, v2 keeps running until cutover — all fine. The flag: "not migrated" must never become "destroyed." Added to charter and plan: **back up the v2 SQLite database before any decommission**, and the Sources Engine playbook's re-score step becomes an optional, deferred bulk-import path — the 1,545 sources remain importable forever at near-zero cost. The decision not to import stands; the *option* is preserved.

## Changelog decisions absorbed into Charter v3.1 (now constitutional, not just logged)
- Per-piece human approval before publish. No auto-publish, ever, at any trust level. Hard rule.
- Outward research loop runs from v1, not deferred.
- Feedback input = typed text + tap/click chips where they help; voice available everywhere, assumed nowhere.
- Postiz confirmed as the publishing layer (direct media upload via API, per-post analytics, self-hostable).
- Naming: **ViralFactory** = the generic harness; **StackPenni** = tenant #1.

## Ruling: document hierarchy (fixing a drift risk)
CONTEXT.md currently declares itself "source of truth" and "supersedes" the charter. Two documents claiming primacy is how agents end up building against different understandings. Precedence, now in the charter:
1. **Charter** — principles and design rules. Amendments arrive only via `docs/decisions/` → architect review → version bump.
2. **BUILD_PLAN** — what to build, in what order, with what guardrails. Conforms to the charter.
3. **CONTEXT.md** — the operational mirror: current shared language, workflows, implementation state. It *conforms to* the charter and plan; where it conflicts, that conflict is a bug or a new divergence to file — never a silent override.
4. **CHANGELOG / decisions/** — the record. Feeds charter revisions; does not govern by itself.
Hermes: edit CONTEXT.md's header — replace "source of truth"/"Supersedes" language with "operational mirror; conforms to docs/CHARTER-v3.1.md; conflicts are divergences to file."

## Answers to open questions (the three flagged as needed before M2)
1. **Module storage:** repo markdown (`modules/{business}/`) is the system of record — versioned, diffable, gate-enforced via the app. OB1 becomes a read-only mirror for Daimon's browsing (a sync job, later, optional). One source of truth, and it's the one the code enforces.
2. **Postiz deployment:** self-host on the VPS (ownership preference, AGPL, no per-seat cost, API identical). Revisit only if maintenance burden bites.
3. **LLM backend:** default Ollama Cloud (existing subscription) for processing steps at temperature 0. For the *drafter* specifically, run the M3 checkpoint as an A/B: same seeds through the config-swapped backends, owner reacts blind. Voice quality is the product; the config swap exists precisely so this is a measurement, not a debate.
(Context-window strategy and video scope: genuinely deferrable; video scope is already bounded by the charter's hybrid rules.)

## Process note
DIVERGENCE-001 is exemplary — verbatim owner quotes, consequences traced, changelog discipline. This is the loop working. Keep the format exactly. One expectation to set: approvals will not always be 5/5; a review that never rejects isn't reviewing.

## Actions for Hermes (in order, before M0 code)
1. Replace `docs/CHARTER-v3.md` with `docs/CHARTER-v3.1.md` (supplied). Keep v3 in git history only.
2. Replace `BUILD_PLAN.md` with v1.1 (supplied — fresh-start stack, async gate wording, direct-edit task in M3, v2 backup task, D3 UI notes).
3. Patch `docs/UI-DIRECTION.md`: Principle 1 → "Laptop-first (1280px+), responsive to mobile; mobile-friendly is a hard requirement for future customers." Principle 5 → "Voice in, everywhere — available at every input, assumed at none; typed text and chips are equal citizens." Surface 2 draft view → add the direct-edit mode (editable draft; human text authoritative; logged to Feedback Log at highest weight).
4. Patch CONTEXT.md header per the hierarchy ruling above; update its human-role and gate sections to cite Charter v3.1.
5. Split `docs/playbooks-remaining-seven.md` into individual files under `playbooks/`; move charter/intake/UI docs to their charter-specified locations.
6. Add to M0: task T0.7 — scripted, verified backup of the v2 SQLite database to storage outside the v2 app directory.
7. Then begin T0.1. Tag `review-w1` when M0 completes.
