# Pre-assembly Component Workbench — builder implementation plan

> **Builder:** work only from `docs/CHARTER-v3.9.md`, AMENDMENT-013, this plan, and VF-CW tasks in `BUILD_PLAN.md`. Do not redesign in code. Ask through a divergence when a contract is ambiguous.

**Goal:** replace the current mutable-inventory/legacy-soundtrack pause with a resumable Assets-stage workbench where the operator approves exact narration, visuals, soundtrack, SFX/source sound, typography, graphics, and format-declared elements before manifest-locked assembly. Preserve final exact-artifact Gate 3.

**Architecture:** introduce a tenant-scoped `ProductionSession` aggregate, config/prompt-driven component requirements, immutable candidate versions, append-only decisions, deterministic completeness, immutable assembly manifests, and a shared resume service. Existing media/VO/soundtrack tables remain artifact-specific stores; the workbench references them rather than duplicating their binary metadata. `EditPlanningService` and `RenderReviewService` are narrowed to accept one verified manifest, never mutable “latest” inventory.

**Primary implementation areas:** `src/pipeline.py`, new `src/services/component_workbench.py`, new `src/services/production_orchestrator.py`, `src/services/media_planning.py`, `src/services/edit_planning.py`, `src/services/render_review.py`, `src/produce_chain.py`, `src/app.py`, `src/templates/assets.html` or a dedicated workbench template, config, prompts/schemas, tests, and binding docs.

---

## Phase 0 — Preserve a reproducible failing baseline

### Task 0.1: Record representative failure fixtures

Before schema changes, encode sanitized fixtures for:

- card 59 / asset 18 waiting at soundtrack approval with no durable continuation;
- a `done` generation job followed by edit-plan failure because required visuals are absent;
- missing VO followed by a route-only manual recovery;
- multiple assets under one draft where `get_asset_by_draft()` selects only the first;
- direct Gate 3 approval without an active final artifact;
- multiple edit plans where newest is not explicitly active.

These are behavior fixtures, not copies of personal content or provider credentials. The RED tests must call the current shared boundaries and fail for the documented reason.

### Task 0.2: Add observability correlation IDs

Every production log/job/step must carry `business_slug`, `production_session_id`, `draft_id`, `asset_id`, current state, attempt, and upstream hash. This is mechanics, not judgment. Do not postpone correlation until the UI phase.

---

## Phase 1 — Production session and exact component contracts

### Task 1.1: Add tenant-scoped persisted production sessions

Add append-only/current-state persistence initialized by every writer that may touch it. A session belongs to exactly one platform asset, not merely a draft. Required fields:

- ID, business, draft, asset, platform, format;
- Writer contract ID/hash;
- current state and reason;
- active requirements version, active manifest version, active render version;
- created/updated/transition timestamps;
- retry/attempt metadata.

Allowed states are those in AMENDMENT-013. State transitions live in one service and use compare-and-set semantics. Routes never update state directly.

### Task 1.2: Add config-driven category registry

Create a generic category registry in config. Each format declares required/optional categories and role cardinality. The first schema supports narration, visual media, soundtrack, SFX/source sound, typography, graphics, and extra tenant-defined categories.

Python validates registry structure and role completeness. It must not derive creative requirements from business keywords. No StackPenni category or visual value may appear in Python.

### Task 1.3: Add component requirement planner

Create a versioned prompt + JSON schema + validator registered through the Process Registry. Input: approved Writer contract, format/platform, visual events, audio intents, capture policy, and relevant module/config context. Output: required category roles with semantic descriptions, beat/event scope, allowed source types, preview requirement, and whether explicit `none` is allowed.

Validator rules are mechanical: known category/role IDs, correct beat/event references, allowed source types, cardinality, and no audience-copy mutation. Persist prompt/model/provenance/input hash and cache at temperature 0.

### Task 1.4: Add immutable candidate and decision stores

Candidate versions are append-only. Store stable candidate lineage separately from immutable version identity. A candidate references the owning artifact table (`vo_takes`, `asset_media`, soundtrack artifacts/mixes, renderer specimens) and stores its exact artifact/preview hashes and provenance linkage.

Operator decisions are append-only and bind `candidate_version_id + artifact_hash + requirement_version_hash`. Selection and approval are explicit; a failed/regenerated/superseded version cannot be approved. Never add a single `approved` Boolean as the source of truth.

---

## Phase 2 — Generate candidate sets, not one hidden choice

### Task 2.1: Narration candidates

Refactor VO generation to produce the configured number of complete-take candidates per piece. A take must have:

- one voice/model/source identity;
- complete measured beat segments and a playable full preview;
- exact spoken-text hash and timing contract;
- generation provenance and cost status;
- immutable audio hash.

Existing complete valid takes may register as candidates. Partial takes are visible as failed/incomplete and cannot satisfy narration. The operator can listen, select, reject with feedback, or regenerate. Regeneration creates a new version.

### Task 2.2: Visual candidates by event/role

Media planning produces candidate sets per declared visual role/event without assembling. Group captures, uploaded archive, stock, generated video, generated stills, and renderer plates under the requirement they may satisfy. Every candidate must have a thumbnail plus full image/lightbox or playable video preview, duration/dimensions, source type, rights/cost facts where applicable, and exact hash.

Do not silently choose the first stock search result. Existing media can be offered only after scoped ownership, file existence, measurement, and hash validation. Required-real capture cannot be satisfied by generated media.

### Task 2.3: Soundtrack and SFX candidates

Reuse VF-VS-511..514 rights/acquisition/ranking/version stores. Register the top pick and alternatives as workbench candidates only after rights, local hash, preview, and cost checks pass. Each soundtrack candidate needs a playable representative VO-under-bed preview. VO-only is an explicit candidate/decision with rationale when allowed.

SFX/source-sound roles are separate candidates. A music selection does not approve SFX. No audio item enters the manifest merely because the planner proposed it.

### Task 2.4: Typography and graphics specimens

Resolve available font files and renderer styles from config/modules, then generate deterministic specimens or short test renders for only the roles declared by requirements. Bind exact font file hashes, style/config hashes, and renderer versions. Show caption readability, hook/emphasis, lower-third/proof-card, CTA, and transition/overlay specimens as applicable.

Defaults may be preselected in the interface but remain unapproved until the operator records the exact decision. Missing font files or failed specimens are visible blockers, never silent fallback.

---

## Phase 3 — Workbench UI and approval semantics

### Task 3.1: Build one server-rendered workbench

Create one laptop-first, mobile-friendly workbench for a platform asset. Use category sections/tabs, role-grouped cards, and a sticky readiness summary. The operator should answer in order:

1. What does this piece still need?
2. What choices are available for this role?
3. Which exact version is selected and approved?
4. Why can or cannot assembly start?

Actions: Preview, Select/Approve, Reject, Regenerate, Add feedback, Replace/upload where permitted. Every action uses a shared workbench service and returns current server truth. No optimistic green status.

### Task 3.2: Cover all human UI states

For every category and overall session, cover fresh, planning, generating, partial, available, selected-not-approved (if kept as a distinct interaction), approved, rejected, regeneration requested, failed, stale, superseded, unavailable, rights blocked, cost blocked, and complete.

Use descriptive piece/beat labels, friendly timestamps plus exact detail, visible versions, plain language, expandable provenance, and fullscreen/playable previews. A killed/shipped/stale item must not expose invalid actions. Mobile must retain the readiness summary and action clarity.

### Task 3.3: Component feedback and regeneration

Feedback is scoped to category, role, candidate version, and session. It may inform the relevant generation prompt but cannot modify a living module automatically. Regeneration receives approved upstream context plus the exact human feedback and records new provenance. It supersedes the prior candidate only when the new candidate validates; it always invalidates the role's old selection for a new manifest.

---

## Phase 4 — Freeze and manifest-locked assembly

### Task 4.1: Deterministic completeness service

Given one current requirements version, verify mechanically that every required role has exactly one current approved selection and every selected artifact is:

- tenant/session/asset scoped;
- existent, non-empty, measured, and hash-valid;
- previewed where required;
- not failed/rejected/superseded/stale;
- rights-valid and cost-approved when applicable;
- compatible with the approved Writer/VO/timing/format contract.

Return structured blockers by category/role. Never collapse partial state to a generic 409.

### Task 4.2: Freeze immutable manifest

`freeze_manifest(session_id)` runs completeness in one transaction, records exact component decision IDs and artifact hashes, snapshots all upstream contract/module/config hashes, computes a canonical manifest hash, activates that manifest version, and advances the session to `manifest_ready`.

A retry with identical inputs is idempotent. Any changed input creates a new version. A new active manifest invalidates the old final render/Gate 3 approval.

### Task 4.3: Make edit planning and rendering accept manifest only

The new production boundary is `assemble(manifest_id)`. Eliminate mutable inventory lookup from the current path. `EditPlanningService` may use only manifest-listed visual/audio/text/style IDs. Renderer job construction carries manifest item IDs and hashes. Before and after render, verify all source hashes and record consumed IDs.

Legacy assets may be displayed read-only, but no compatibility fallback may silently construct a manifest or render them as fresh compliant work.

### Task 4.4: Make final evidence and Gate 3 fail closed

Final review binds exact output hash + manifest hash + edit-plan hash. Required frame/audio/text/timing/source evidence failures or missing rows block readiness. Extended audio/content-alignment exceptions cannot be non-blocking when the requirement contract marks them required.

Move Gate 3 writes into a shared service. `approve` requires current final artifact, current manifest, complete required evidence, exact lineage, and a human decision. Direct route POSTs must not bypass these checks. Fix/kill create explicit transitions. Ingredient changes always require new manifest/render/approval.

---

## Phase 5 — Durable orchestration and multi-platform correctness

### Task 5.1: Replace monolithic pause with resumable orchestration

`ProductionChain` becomes a caller of `ProductionOrchestrator.advance(session_id)`. Each invocation performs only the next idempotent runnable step and persists its transition. Human waits end as `component_review_required`, not a still-running job. `Freeze choices and assemble` enqueues assembly; process restart/retry resumes from persisted truth.

Detect stale `running` jobs and reconcile them against downstream invariants. A job row marked done does not imply the next state unless its required records/artifacts exist.

### Task 5.2: One child session per platform asset

Stop using `get_asset_by_draft()` in the active production path. Create/advance each platform asset independently. The parent draft/card aggregates child statuses: waiting for choices, assembling, ready for final review, blocked, approved, killed. A failed child does not make another platform falsely ready.

---

## Phase 6 — Migration, testing, and deployed proof

### Task 6.1: Add fail-closed compatibility handling

Existing assets without a production session/manifest are labeled **Legacy — choices not recorded**. They may be killed or explicitly restarted into a new session. Do not auto-mark old media approved and do not infer historical human approval.

### Task 6.2: Automated behavioral proof

At minimum cover:

- tenant separation and cross-asset/cross-session rejection;
- requirement planner prompt/schema/provenance/cache;
- complete and partial candidate generation;
- exact approval hash binding and regeneration invalidation;
- role/category completeness and approved-none rules;
- rights/cost/preview/hash failure cases;
- immutable idempotent manifest freeze;
- assembler rejection without a current manifest and rejection of unlisted media;
- source hash changes before/during render;
- Gate 3 direct-route bypass prevention;
- one draft with multiple platform assets;
- process restart at every state and stale-job recovery;
- route/autonomous behavioral parity;
- all 10 UI review dimensions.

Use real small FFmpeg fixtures for media mechanics. Provider tests use fakes/redacted fixtures; paid live proof is separate.

### Task 6.3: Fresh deployed Reel proof

Create a genuinely fresh piece and record:

- Writer contract/hash and production session;
- required categories/roles;
- at least two candidates where configured for VO, a visual role, and soundtrack;
- operator decisions and feedback/regeneration lineage;
- rights/cost facts;
- manifest ID/hash and every selected artifact hash;
- exact renderer consumed-item evidence;
- final output hash and blocking review evidence;
- Gate 3 decision bound to manifest/output;
- Gate 4 hold, with no publication.

Restart the service while the session is waiting for component review and prove the same workbench resumes. Exercise one alternative after first assembly and prove new manifest/render + Gate 3 invalidation. Use port 9121, do not skip connection failures, and do not reuse an old final file.

### Task 6.4: Deep operator review

The architect walks the full workbench on laptop and mobile across all categories and failure states. Completion requires an operator-facing review in `docs/reviews/`, not screenshots of happy-path cards alone.

---

## Hard stops

The builder must stop and file a divergence if implementation would:

- reduce or remove final-artifact Gate 3;
- allow assembly without a frozen current manifest;
- use creative keyword/ranking judgment in Python;
- define tenant-specific categories or choices in code;
- infer approval for legacy or regenerated artifacts;
- permit one platform asset's choice/approval to satisfy another;
- treat a provider identity as rights evidence;
- hide a materially used font, soundtrack, clip, voice, SFX, graphic, or renderer choice from the workbench;
- preserve both the legacy assembler chain and the manifest path as competing production routes.

## Definition of done

The feature is done only when a fresh deployed multi-component Reel can survive service restart, show every required ingredient as an exact reviewable version, freeze only human-approved choices, assemble only those choices, expose all blocking evidence, and require a separate Gate 3 approval of the exact final artifact. Passing tests without this deployed proof is component completion, not system completion.
