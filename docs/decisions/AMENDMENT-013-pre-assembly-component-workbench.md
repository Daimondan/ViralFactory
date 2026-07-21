# AMENDMENT-013 — Pre-assembly Component Workbench and manifest-locked assembly

**Filed:** 2026-07-21
**Filed by:** Architect (vf-architect)
**Status:** APPROVED — ratifies DIVERGENCE-018; incorporated into Charter v3.9
**Related:** AMENDMENT-003, AMENDMENT-009, AMENDMENT-010, AMENDMENT-011

## Decision

For composited media, the Assets stage gains a mandatory **Component Workbench** before assembly. The operator reviews generated ingredients by category, selects exact versions, and freezes an immutable assembly manifest. The assembler may consume only that manifest. Existing Gate 3 remains mandatory and approves the exact assembled artifact; it is not replaced by component selection.

## Binding flow

1. Lock the approved Writer contract and its hash.
2. Derive a config- and prompt-driven component requirement set for the piece.
3. Generate candidates without assembling the final artifact.
4. Present candidates in category/role groups with previews, provenance, cost, rights, status, and versions.
5. Record operator selection/rejection/regeneration decisions against exact candidate hashes.
6. Compute category completeness mechanically.
7. Freeze an immutable manifest containing exact approved component versions and all upstream hashes.
8. Assemble deterministically from the manifest only.
9. Run blocking evidence and compliance review.
10. Present the exact assembled version at Gate 3 for approve/fix/kill.
11. Preserve Gate 4 go/hold and the no-auto-publish rule.

## Component categories

Categories are declared in config and may vary by format. Generic first-party category keys are:

- `narration` — complete voice takes and, when useful, beat-level auditions;
- `visual_media` — operator captures, archive/reference media, stock, generated clips, generated stills, and renderer-ready plates, grouped by beat or visual event;
- `soundtrack` — rights-valid local tracks, VO-under-bed previews, mode, and explicit VO-only option;
- `sound_effects` — source sound and motivated SFX cues;
- `typography` — exact font files and role specimens for hook, caption, emphasis, proof, lower-third, and CTA roles used by the piece;
- `graphics` — style frames for renderer graphics, overlays, information cards, caption treatments, and declared transitions;
- config-declared optional categories for format-specific elements.

A category name does not grant approval. Each required role within a category must resolve to one exact active approved candidate, or to an explicit approved `none`/`not_applicable` decision when the requirement contract allows it.

## Candidate contract

Every candidate must carry:

- tenant, production session, asset, category, role, beat/event scope;
- stable candidate ID and immutable version;
- artifact reference, local path where required, SHA-256, size, measured media facts, and preview artifact/hash;
- generation/source provenance, prompt/config/model versions, and source identity;
- cost estimate/approval and rights snapshot when applicable;
- status: `generating | available | failed | rejected | approved | superseded | stale`;
- append-only operator decisions and feedback;
- supersession lineage.

Candidate approval means only: “this exact version may be used for this declared role.” It does not approve the category, manifest, final artifact, or publication.

## Requirement and completeness contract

A schema-validated planning process may decide which creative roles are required from the approved Writer contract, format, visual events, audio intent, and tenant modules. Python may validate IDs, types, file facts, hashes, rights, costs, timing, and completeness; it may not decide creative fit with keywords or business-specific rules.

Category completeness requires every mandatory role to have exactly one active approved selection. Missing, failed, rejected, superseded, stale, rights-invalid, unprobeable, hash-mismatched, or cost-unapproved candidates fail closed.

## Immutable assembly manifest

Freezing creates a new append-only manifest version containing:

- business, production session, draft, asset, platform, and format IDs;
- approved Writer contract/hash;
- VO/timing contract and selected narration hash;
- exact candidate IDs, versions, artifact hashes, and role mappings;
- module snapshot/version hashes;
- render-style/config hash;
- rights and cost-approval references;
- component decision IDs and completeness evidence;
- manifest hash, creator, and creation time.

The assembler entrypoint becomes `assemble(manifest_id)`. It must not query “latest” media, infer substitutions, reuse unlisted files, or choose a fallback. Any stale dependency blocks assembly and requires a new manifest.

## Invalidation rules

- Regenerate/edit/replace creates a new candidate version and invalidates the affected role's approval and category completeness.
- Any change to approved Writer content, VO, timing, visual events, soundtrack mode, font/style choice, module snapshot, rights validity, or render config after freeze marks the manifest stale.
- A new manifest invalidates any final render and Gate 3 approval based on the old manifest.
- A failed replacement preserves the last valid candidate but does not silently select it for a new manifest.
- Gate 3 approval binds exact final artifact hash + manifest hash. Track, clip, font, graphic, timing, or config changes require reassembly and reapproval.

## Durable orchestration

The production path must be a persisted resumable state machine, not a monolithic function that returns at a human pause:

`planning_components → generating_components → component_review_required → manifest_ready → assembling → final_review_required → gate3_approved | blocked | failed`

Human decisions advance the same shared service used by operator routes and autonomous production. Waiting states are not failures. A visible **Continue to assembly** action freezes the manifest and enqueues the next durable step. Stale `running` jobs are detected and recoverable. Retries are idempotent by content hash.

## UI requirements

The workbench is one operator surface with category tabs/sections and a persistent readiness summary. It must show:

- category and required role;
- descriptive beat/event label, not internal IDs alone;
- playable/fullscreen preview appropriate to the medium;
- candidate version, generation status, source/provenance, rights/cost facts, and evidence age;
- `Select`, `Reject`, `Regenerate`, and feedback actions valid for the current state;
- selected-vs-approved distinction;
- empty, partial, generating, failed, stale, superseded, and unavailable states in plain language;
- visible reasons assembly is blocked;
- one final **Freeze choices and assemble** action only when complete.

No green approval styling may appear before a recorded human decision on the exact version. Technical states such as `asset_ready` or `production_failed` are translated into plain language.

## Soundtrack amendment

AMENDMENT-011's rights-first discovery, rights snapshots, local hashed acquisition, ranking evidence, immutable mixes, cost approval, and Gate 3 exact-artifact approval remain binding.

Its single-approval rule is superseded as follows:

- the Component Workbench selects/approves the exact soundtrack ingredient before assembly;
- a representative VO-under-bed preview is required for selection when music is used;
- Gate 3 separately approves the exact final mixed video;
- switching a track after assembly creates a new manifest/render and invalidates Gate 3 approval.

These are different decisions, not duplicate clicks: ingredient selection answers “use this”; Gate 3 answers “this exact finished piece is ready.”

## What this does not change

- Gate 1, Gate 2, Gate 3, and Gate 4 semantics remain.
- The Writer/Assembler boundary remains: the Assembler cannot rewrite approved audience copy.
- Per-piece publication approval and no auto-publish remain hard rules.
- Rights, provenance, cost approval, evidence completeness, and tenant isolation remain mandatory.
- Final creative judgment belongs to the operator; LLM review is advisory except where a schema-validated compliance contract is explicitly blocking.

## Implementation order

The binding task sequence is VF-CW-001 through VF-CW-012 in `BUILD_PLAN.md`. VF-VS-515 is superseded by the broader Component Workbench state machine. VF-VS-516 and VF-VS-702/703 remain blocked until the new workbench and manifest path pass a genuinely fresh deployed Reel proof.
