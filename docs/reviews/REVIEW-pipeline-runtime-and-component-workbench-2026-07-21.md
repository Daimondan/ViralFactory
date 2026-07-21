# REVIEW — Pipeline runtime audit and pre-assembly Component Workbench

**Date:** 2026-07-21
**Reviewer:** Architect (vf-architect)
**Scope:** live repo at `4c444ff`, deployed service, SQLite state, shared production services, operator Assets UI, and requested component-level human control
**Verdict:** P0 architecture correction required before fresh M13 proof. Do not patch another button onto the current chain.

## Executive finding

The service is available but the production system is not reliably completable. `/health` returned HTTP 200 while the database showed stalled cards, stale jobs, repeated prerequisite failures, and no contract proving which ingredient versions enter assembly. The present workflow auto-generates or auto-selects most taste-bearing components, pauses on a legacy soundtrack gate, and then assembles from mutable inventory rather than a frozen set of human-approved ingredients.

The correct fix is a **Component Workbench + immutable assembly manifest**, not a larger Gate 3 page and not additional conditionals in `src/app.py`.

## Live evidence

Observed on 2026-07-21 without triggering generation or paid calls:

- systemd service active; `GET /health` returned 200;
- 59 idea cards: 49 killed, 4 `assembling`, 2 `awaiting_soundtrack_approval`, 2 `asset_ready`, 2 new;
- 18 assets: 9 pending, 8 killed, 1 rendered, 0 approved;
- 78 jobs: 50 done, 26 failed, 1 dead, 1 running;
- card 59 / asset 18 remained `awaiting_soundtrack_approval` / pending for 25 minutes with no final artifact;
- job 75 remained `running` without completion while its edit plan and soundtrack proposal already existed;
- recent edit-plan jobs repeatedly failed first for missing visuals and then for missing VO;
- 151 `asset_media` rows existed, while many recent generated video/image rows had no `beat_id`; the schema has no category, candidate version, approval, or manifest identity;
- 11 soundtrack plans existed but only 2 soundtrack approval rows;
- only one asset was `rendered`; no asset was Gate 3 approved.

Availability is therefore not completion proof.

## P0 findings

### P0-1 — Human pause has no coherent durable continuation

`src/produce_chain.py:330-356` runs one monolithic sequence and returns when `_step_soundtrack_gate()` is false. The approval route at `src/app.py:7253-7275` records a decision but does not resume the autonomous chain or reconcile the card state. Card 59 consequently remained in `awaiting_soundtrack_approval` indefinitely.

**Correction:** persisted production-session state machine; approval/freeze enqueues the next idempotent step; operator and autonomous paths call the same resume service.

### P0-2 — Current pipeline approves only soundtrack before render, not the requested ingredients

VO is generated once and silently reused (`src/produce_chain.py:367-421`). Media generation executes planner choices immediately (`src/services/media_planning.py:418-450`) and stock takes the first match (`src/services/media_planning.py:508-527`). Fonts, graphics, caption treatments, and transitions are hidden renderer/config choices. There is no candidate comparison or exact-version component approval.

**Correction:** candidate contracts and category review for narration, visual media, soundtrack, SFX/source sound, typography, graphics, and config-declared roles.

### P0-3 — Assembly has no approved-input manifest

`EditPlanningService` builds an inventory from whatever is currently render-ready (`src/services/edit_planning.py:167-224`). It receives no operator-approved candidate set. The assembler can therefore use media that happens to exist rather than media the operator selected.

**Correction:** freeze an immutable manifest; edit planning and rendering receive `manifest_id` and reject all unlisted ingredient IDs.

### P0-4 — Gate 3 backend can approve without proving a final artifact

The UI disables approval until `has_final` (`src/templates/assets.html:812-823`), but the API route at `src/app.py:6702-6728` accepts `approve` and directly writes `asset_state='approved'` without checking a final artifact, active version/hash, manifest, review evidence, or current approval lineage. A direct request bypasses the UI lock.

**Correction:** central Gate 3 service validates active final artifact hash, current manifest hash, blocking evidence completeness, and human decision atomically. Routes never write gate state directly.

### P0-5 — Multiple platform assets are reduced to the first asset

`PipelineStore.get_asset_by_draft()` returns the first asset (`src/pipeline.py:1467-1476`). The autonomous media/edit/render steps repeatedly call it (`src/produce_chain.py:427-474`, `543-559`). A multi-platform draft therefore does not have a complete per-asset production state machine.

**Correction:** one production session/manfiest per platform asset; parent draft aggregates status but never substitutes the first child.

### P0-6 — Missing review evidence can remain non-blocking

Extended audio and content-alignment review exceptions are logged as non-blocking at `src/services/render_review.py:250-275`. This conflicts with the Charter rule that required evidence missing/skipped is not pass.

**Correction:** requirement contract declares which evidence is blocking; missing required rows yield `needs_operator_decision` and Gate 3 cannot approve.

## P1 findings

### P1-1 — Mutable “latest” selection is ambiguous

`list_edit_plans()` orders by newest ID (`src/pipeline.py:1802-1814`) but there is no explicit active-plan identity. Several assets have multiple proposed/rendered plans. The UI uses index zero. A newest row is not necessarily the approved or current row.

**Correction:** explicit active version pointers and immutable lineage for requirements, candidates, manifests, plans, and renders.

### P1-2 — Media execution reports process success before downstream readiness

`MediaPlanningService.generate_for_asset()` can return success with submitted/processing/partial results (`src/services/media_planning.py:431-451`). `_step_media_exec()` checks only a narrow combination (`src/produce_chain.py:449-455`). Recent database history shows jobs marked done followed by edit-plan failures for missing visuals.

**Correction:** candidate generation statuses remain partial until every required role has a previewable candidate; “job done” means the bounded job ended, not that the category or piece is ready.

### P1-3 — Duplicate soundtrack UX encodes contradictory governance

`src/templates/assets.html:447-530` contains Gate 3 soundtrack alternatives while `src/templates/assets.html:744-798` also contains a pre-render soundtrack proposal/approval block. The deployed card stops on the latter. AMENDMENT-011 intended one Gate 3 choice, but the operator now explicitly wants component selection before assembly.

**Correction:** replace both with one Component Workbench soundtrack category plus final-artifact Gate 3 display. Distinguish ingredient selection from finished-piece approval.

### P1-4 — Version and provenance are not operator-visible

The asset card displays raw asset state (`src/templates/assets.html:360-367`) but not candidate version/hash, source lineage, generation status per role, or a visible manifest version. Generated media is displayed positionally and can lack beat identity.

**Correction:** role-grouped candidates, visible versions/evidence age, selected/approved distinction, and manifest badge.

## Required target architecture

`Writer contract locked`

`↓`

`Component requirements planned`

`↓`

`Candidates generated by category (no final assembly)`

`↓`

`Human selects exact versions; incomplete roles remain visible`

`↓`

`Manifest freezes Writer + VO + media + audio + typography + graphics + config/module hashes`

`↓`

`Assembler consumes manifest only`

`↓`

`Blocking evidence review`

`↓`

`Gate 3 approves/fixes/kills exact final artifact`

`↓`

`Gate 4 go/hold`

## Stop conditions for the builder

Do not:

- add approval booleans to `assets` or `asset_media`;
- treat `latest` as `active`;
- reuse the current soundtrack gate as the generic component gate;
- let assembly query the mutable inventory after manifest freeze;
- put creative requirement judgment in Python keyword rules;
- claim completion from unit tests, `/health`, or a reused artifact;
- remove final-artifact Gate 3.

The implementation order and proof are specified in VF-CW-001..012 and `docs/plans/2026-07-21-pre-assembly-component-workbench.md`.
