# Decision: Charter v3 Amendments — Daimon Grill Session 2026-07-02

## Status
Proposed — pending Claude (architect) review and incorporation into Charter v3.1

## Context
On 2026-07-02, Daimon grilled the Charter v3, BUILD_PLAN, UI-DIRECTION, and playbooks before any code was written. Five divergences from the architect's original design were identified. Each was confirmed by Daimon in plain language. These amendments must be incorporated into the next Charter revision so the architect and all future agents build against the same understanding.

## Divergence 1: Human role — "never produce" → "sometimes produce directly"

**Charter says:** "The system does not assume the person can write, design, or edit." Human role = originate + react + lived material. "Never produce."

**Daimon says:** Sometimes you want to write/edit directly, and the system should respect and encourage that.

**Decision:** Add a fourth human input mode: **direct edit**. When the user writes or rewrites draft text themselves, the system treats this as authoritative — the human's text overrides the AI draft, and the edit feeds the Feedback Log as the strongest possible voice signal. The UI needs a direct-edit mode in the draft view, not just reaction chips.

**Consequences:**
- UI: draft view needs an editable text area alongside reaction chips
- Feedback Log: direct edits are logged with higher weight than chip reactions
- Voice Profile: direct edits are a first-class signal for the inward learning loop
- The "never produce" framing was too restrictive; the system should *default* to AI production but *support* human production

## Divergence 2: Gate rhythm — weekly sitting → async queue

**Charter says:** "The gate is one sitting per week — if longer, fix the proposal prompt, not the gate."

**Daimon says:** Async queue you clear when ready. Not a scheduled sitting.

**Decision:** The Gate is a persistent queue, not a weekly batch. Proposals accumulate; Daimon clears them whenever he has time. The inward loop can still generate proposals on a schedule (weekly), but the human review is asynchronous.

**Consequences:**
- Gate UI: persistent queue with "N pending" counter, not a weekly session that resets
- No "you must clear this by X" pressure
- The counter shows total pending across all proposal types (module updates, sources, experiments)
- Proposals can age — old proposals should show "submitted N days ago" so staleness is visible

## Divergence 3: UI — mobile-first → laptop-first, mobile-friendly

**UI-DIRECTION.md says:** "Mobile-first. The operator runs this from a phone. Every screen works one-handed on a phone; desktop is the bonus, not the target."

**Daimon says:** Laptop primary for Daimon. Mobile-friendly for other users (paying customers).

**Decision:** Design for laptop screens first. Ensure responsive down to mobile. Don't restrict to one-handed phone interactions. The "mobile-first" constraint was forcing unnecessary design limitations on the primary user.

**Consequences:**
- Layouts target laptop viewport (1280px+), scale down responsively
- Reaction chips work as tap (mobile) or click (laptop) — same UI, different input
- Voice notes work via laptop mic — no phone assumption
- Multi-column layouts acceptable on laptop (e.g., draft + source side-by-side)
- Mobile-friendly is a requirement for future customers, not an afterthought, but it doesn't constrain the primary design

## Divergence 4: Generalization timeline — week 11+ → near-term but not blocking

**Charter says:** Phase 5 (week 11+) for generalization proof. Earlier phases are StackPenni-focused.

**Daimon says:** Real near-term plan with paying customers, but "suggestive for now, when we get there we can decide what we are doing."

**Decision:** Keep the "nothing business-specific in code" rule as architecture (it's good practice regardless). Build for StackPenni first. Don't let generalization block v1 delivery. Onboard customer #2 when it's real, not hypothetical.

**Consequences:**
- Config isolation enforced from day 1 (cheap if done early, expensive if retrofit)
- Playbook engine built generic (it's the same effort as purpose-built)
- BUT: no multi-tenant UI, no customer onboarding flow, no billing — those wait for a real customer
- The Charter's Phase 5 stays as-is conceptually, but the timeline may compress

## Divergence 5: BUILD_PLAN references "extend the existing Flask app"

**BUILD_PLAN says:** "Python + Flask console (extend the existing app), SQLite (existing)."

**Daimon says:** Fresh start from scratch.

**Decision:** New Flask app, new SQLite DB, new repo structure. The old v2 StackPenni pipeline stays running at stackpenni.glenbeu.com until ViralFactory is ready. No migration of data or code.

**Consequences:**
- No v2 code imports, no v2 DB schema reuse
- BUILD_PLAN must be updated to remove "extend existing app" references
- StackPenni config (sources, topics, brand values) will be re-entered through the onboarding flow, not migrated
- The ~1,545 sources in v2 are NOT carried over (fresh start)
- v2 stays operational during the build; cutover happens when ViralFactory is production-ready

## Owner Input
Daimon confirmed all five divergences in a single message on 2026-07-02. Exact quotes:

1. "yes sometimes i should be able to write edit directly myself and the system respect and encourage that"
2. "a queue i clear" (re: gate rhythm)
3. "laptop primary I am, but it should be mobile friendly esp for other people"
4. "real near term plan... thats more suggestive for now, when we get there we can decide"
5. "fresh start for now"