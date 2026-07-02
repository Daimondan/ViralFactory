# CHANGELOG — ViralFactory

> **If you made a decision and it's not in the changelog, that is a bug.**

All decisions — tech, logic, structure, strategy, ops — logged here with type tag + rationale.

---

### 2026-07-02 STRATEGIC — ViralFactory is a generic system, StackPenni is user #1
**Rationale:** Daimon confirmed the system is named ViralFactory — a generic content co-creation system. StackPenni is the first tenant. Paying customers are a real near-term plan. The harness is code; the business lives entirely in config and modules. This was established during the grill session and aligns with Charter v3's original design.

### 2026-07-02 STRATEGIC — Fresh start, no v2 migration
**Rationale:** Daimon said "fresh start for now." The old StackPenni v2 pipeline (Flask app, ~1,545 sources, 68 tests) stays running at stackpenni.glenbeu.com until ViralFactory is production-ready. No v2 code, data, or schema is reused. StackPenni config will be re-entered through the onboarding flow. BUILD_PLAN's reference to "extend the existing Flask app" is stale and must be updated. (Divergence 5 from Charter.)

### 2026-07-02 STRATEGIC — Human role includes direct edit, not just originate + react
**Rationale:** Daimon said "yes sometimes i should be able to write edit directly myself and the system respect and encourage that." The Charter's "never produce" framing was too restrictive. The system defaults to AI production but supports and encourages human direct editing. Direct edits are authoritative (override AI draft) and feed the Feedback Log as the strongest voice signal. (Divergence 1 from Charter.)

### 2026-07-02 OPS — Async gate queue, not weekly sitting
**Rationale:** Daimon said "a queue i clear." The Charter's "one sitting per week" gate model doesn't match Daimon's actual rhythm. Proposals accumulate in a persistent queue; Daimon clears when ready. The inward loop can still generate proposals on a weekly schedule, but human review is asynchronous. (Divergence 2 from Charter.)

### 2026-07-02 STRUCTURE — Laptop-first UI, mobile-friendly for future users
**Rationale:** Daimon said "laptop primary I am, but it should be mobile friendly esp for other people." UI-DIRECTION.md's "mobile-first, operator runs from phone" was wrong for the primary user. Design for laptop (1280px+), scale down responsively. Mobile-friendly is required for paying customers but doesn't constrain the primary design. (Divergence 3 from Charter.)

### 2026-07-02 STRATEGIC — Generalization is real but not blocking v1
**Rationale:** Daimon confirmed paying customers are a near-term plan, but "suggestive for now, when we get there we can decide." Keep "nothing business-specific in code" as architecture. Build for StackPenni first. Don't let generalization block v1 delivery. (Divergence 4 from Charter.)

### 2026-07-02 TECH — Postiz for publishing (not Buffer)
**Rationale:** Daimon asked "does Postiz make it easier to post?" Research confirmed yes: Postiz has direct media upload via API (Buffer requires hosted URLs — the exact pain Daimon identified), per-post analytics on all plans, 32 platform integrations, an MCP server for AI agent integration, self-hosting (free, AGPL-3.0), and OAuth 2.0 "Direct Integration" flow for onboarding paying customers. Buffer's GraphQL API is more complex and its media handling is a dealbreaker for a system that produces text + images + video. Postiz self-host vs cloud deployment TBD (open question).

### 2026-07-02 TECH — Flask + SQLite + systemd on VPS
**Rationale:** Carried from Charter v3. Flask is boring, fast on island bandwidth, server-rendered. SQLite is sufficient for a single-tenant system and easy to deploy. systemd ensures the app survives session boundaries. Fresh start = new Flask app, new SQLite DB, no v2 reuse.

### 2026-07-02 TECH — LLM adapter swappable in config
**Rationale:** Carried from Charter v3. One function: `complete(prompt_file, variables, schema) -> validated JSON`. Backend from `models.yaml` — Ollama local, Ollama Cloud, or external API. Model swap = config edit, zero code change. If open-source drafting quality underwhelms, swap without touching code. Default: Ollama Cloud (Daimon's existing $20/mo subscription). Final choice is an open question.

### 2026-07-02 LOGIC — Per-piece approval, no auto-publish
**Rationale:** Daimon said "yes need to approve every piece before posting." Every piece passes human approval before shipping to Postiz. No exceptions, no auto-publish even after trust is built. This is a hard business rule.

### 2026-07-02 LOGIC — Outward research loop continuous from v1
**Rationale:** Daimon said "system to do it continuously from v1." The outward loop (monitoring top performers, analyzing viral patterns in the domain) runs from day one, not deferred to a later phase.

### 2026-07-02 LOGIC — Feedback via typed text + tap chips
**Rationale:** Daimon said "feedback via type text and tap chips where it makes sense to do so." Not voice-only (UI-DIRECTION assumed voice + chips). Typed text is always available; chips are offered for common reactions where they speed things up.

### 2026-07-02 STRUCTURE — Generic playbook engine
**Rationale:** Daimon confirmed the playbook runner should be generic — it executes markdown procedures for any user, not purpose-built for StackPenni onboarding. Same effort as purpose-built, but enables customer #2 with zero code changes.

### 2026-07-02 STRUCTURE — 8 modules as v1 reality
**Rationale:** Daimon confirmed all 8 living modules (Voice, Viral, Story, Format, Audience, Feedback, Visual, Sources) are v1 reality, not final-state vision. All built during onboarding, all loaded into drafts.

### 2026-07-02 STRUCTURE — GitHub for code AND docs
**Rationale:** Carried from Charter v3. One repo, no split between code and documentation. All agents read the same source of truth.

### 2026-07-02 OPS — All divergences logged for Claude architect awareness
**Rationale:** Daimon said "ensure any divergence from the charter is noted so Claude who is the architect is aware and updates plan going forward." DIVERGENCE-001 written to docs/decisions/. Claude must review and incorporate into Charter v3.1.

### 2026-07-02 OPS — Operating loop doc reviewed and patched
**Rationale:** Daimon added docs/OPERATING-LOOP.md (written by Claude architect). Reviewed against charter + grill amendments. Two patches applied: (1) kickoff step updated to reference docs/CONTEXT.md as primary domain doc, (2) "Weekly cycle" renamed to "Weekly cycle (architect review cadence)" with a note clarifying it's the build-process loop, NOT the product gate (which is async per DIVERGENCE-001). The operating loop complies with the charter and grill amendments — no conflicts found, just the naming clarification needed to avoid confusion between the two loops.

### 2026-07-02 STRATEGIC — Claude architect review: all 5 divergences APPROVED
**Rationale:** Claude reviewed DIVERGENCE-001 and approved all 5 amendments. D1 (direct edit): approved, direct edits are evidence — patterns still reach Voice Profile through gate, no silent self-update. D2 (async gate): approved with refinements — superseding (newer proposal on same section marks older superseded, not deleted), principle rewritten as "if queue grows faster than it clears, fix the proposal prompt, never pressure the person." D3 (laptop-first): approved. D4 (generalization): approved — costs nothing, config isolation was always the architecture. D5 (fresh start): approved with one flag — v2 database must be backed up before decommission; Sources Engine retains optional deferred bulk-import path. "Not migrated" never means "destroyed."

### 2026-07-02 STRUCTURE — Document hierarchy established
**Rationale:** Claude ruled that CONTEXT.md was claiming "source of truth" / "supersedes charter" — two documents claiming primacy causes agents to build against different understandings. New hierarchy: (1) Charter — principles and design rules, amended only via docs/decisions/ → architect review → version bump; (2) BUILD_PLAN — conforms to charter; (3) CONTEXT.md — operational mirror, conforms to charter and plan, conflicts are bugs or divergences; (4) CHANGELOG/decisions/ — the record, feeds charter revisions. CONTEXT.md header patched to reflect this.

### 2026-07-02 TECH — Open questions resolved by architect
**Rationale:** Claude resolved 3 of 5 open questions: (1) Module storage = repo markdown as system of record, OB1 is read-only mirror (optional, later); (2) Postiz = self-hosted on VPS (ownership, AGPL, no per-seat cost); (3) LLM backend = Ollama Cloud default for processing, drafter A/B at M3 checkpoint (same seeds, two backends, Daimon reacts blind). Remaining 2 (context window strategy, video scope) are genuinely deferrable.

### 2026-07-02 STRUCTURE — 8 playbooks split into individual files
**Rationale:** Per architect action item 5. docs/playbooks-remaining-seven.md split into 7 individual files in playbooks/. Combined with the existing voice-profile-builder.md, all 8 playbooks now live as individual files: business-profile-intake, voice-profile-builder, sources-engine, viral-patterns-starter, audience-insights-builder, story-frameworks-starter, format-guide-starter, visual-style-intake.

### 2026-07-02 STRUCTURE — UI-DIRECTION.md patched to v1.1
**Rationale:** Per architect action item 3. Principle 1 → laptop-first (1280px+), responsive to mobile. Principle 2 → verbs now include "type" and "edit" (direct edit supported). Principle 4 → async queue, not weekly sitting. Principle 5 → voice available everywhere, assumed nowhere. Surface 2 (Create) → two input modes: reaction mode (chips + text) and direct-edit mode (editable draft, human text authoritative, logged at highest weight). Surface 4 (Gate) → async queue with age, superseding, no pressure.

### 2026-07-02 OPS — v2 database backup task added (T0.7)
**Rationale:** Per architect action item 6. Fresh start ≠ data destruction. T0.7 added to M0: scripted, verified backup of v2 SQLite database to storage outside v2 app directory. AC: restore tested once; backup location documented in CONTEXT.md. The Sources Engine playbook retains an optional deferred bulk-import path — the 1,545 sources remain importable forever at near-zero cost.

### 2026-07-02 STRATEGIC — ViralFactory is fully standalone, no OB1 dependency (DIVERGENCE-002)
**Rationale:** Daimon said "please dont mess up my ob1 brain, this should be a separate system its own database." Claude's recommendation of OB1 as a read-only mirror is overruled. ViralFactory has its own SQLite database — no OB1 Supabase connection, no OB1 MCP tools, no OB1 dependency whatsoever. Every user onboards the same way: upload materials, share docs, connect Obsidian. OB1 is Daimon's personal knowledge system; ViralFactory is a product. They don't touch. All OB1 references removed from charter, BUILD_PLAN, CONTEXT.md, playbooks, and intake checklist.

### 2026-07-02 FIX — Review-w1 corrections R1–R5 applied
**Rationale:** Claude architect review (review-w1_1.md) identified 5 must-fix defects against M1 acceptance criteria. All 5 fixed:
- **R1 (gate bypass):** `store_voice()` now only writes to `modules/` when `approved=true`. Parked/rejected profiles stay in run state only. 2 new tests.
- **R2 (provenance append-only):** Dropped `UNIQUE` constraint + changed `INSERT OR REPLACE` to `INSERT`. Cache hits and retries no longer overwrite original rows. 1 new test.
- **R3 (failed attempt logging):** First failed validation attempt is now logged to provenance before retry. Every LLM call is logged. 1 new test.
- **R4 (Ollama auth + base_url):** Adapter now sends `Authorization: Bearer $OLLAMA_API_KEY` when env var is set. `base_url` corrected from Cloudflare URL to `https://ollama.com`. 2 new tests. Live smoke test pending `OLLAMA_API_KEY` env var.
- **R5 (WhatsApp format coverage):** Regex widened to support 24-hour format (no AM/PM), iOS bracket format with seconds, and iOS 24h. 3 new test fixtures.
- Process: PROGRESS.md header fixed, BUILD_PLAN checkboxes checked, tag reference corrected to `review-w1`.
- 101 tests passing (92 original + 9 new).

### 2026-07-02 STRUCTURE — Inbox Protocol established (first batch)
**Rationale:** Architect→builder filing standardized. All architect files land in `docs/inbox/`; Hermes files them per the manifest. `docs/inbox/README.md` carries the binding rules. First batch processed: INBOX-README → `docs/inbox/README.md`, AMENDMENT-003 → `docs/decisions/`, diagrams-README → `docs/diagrams/README.md` (replaced), system-overview-v3.2.svg → `docs/diagrams/`, manifest → `docs/inbox/processed/`.

### 2026-07-02 STRATEGIC — Charter bumped to v3.2 (AMENDMENT-003: staged content pipeline)
**Rationale:** AMENDMENT-003 (approved by operator) expands the core loop from a single Draft → React step into a staged funnel with four content gates: Ideas (rigorous: approve/kill/park) → Draft (text + visual direction, no renders; human pass) → Assets (real images + per-platform fan-out; quick gate) → Publish (go/hold). Weak ideas die at the cheapest point. `origin` field (ai-originated | human-seeded | human-seeded-ai-developed) travels end-to-end and is recorded in the nightly performance note. Charter renamed from `CHARTER-v3.1.md` to `CHARTER-v3.2.md`; all references updated (README, CONTEXT.md, BUILD_PLAN header). CONTEXT.md core loop + system diagram mirrored. UI-DIRECTION.md Surface 2 gained Ideas queue + Assets review views. BUILD_PLAN M3 expanded with 9 tasks (idea cards, Gate 1 UI, visual-direction block, Assets stage, Gate 3 UI, origin threading). M2 unchanged. Diagrams README replaced with v3.2 system overview + Mermaid. `stackpenni_v3_system_with_onboarding.png` superseded (left in place).