# Review — Assembly quality and external renderer boundary

**Date:** 2026-07-22
**Reviewer:** Architect
**Scope:** Current assembly implementation, Charter v3.9/AMENDMENT-013 alignment, and official renderer API market evidence
**Verdict:** The current local renderer is an acceptable baseline/fallback but not a sufficient production-quality finish layer. Adopt the provider-neutral boundary in DIVERGENCE-019 and run a Creatomate-vs-Shotstack bake-off. Vizard is not the canonical assembler.

## Constitution and product requirements

The review used the required read order: `README.md`, `docs/CONTEXT.md`, `docs/CHARTER-v3.9.md`, `BUILD_PLAN.md`, `docs/PROGRESS.md`, `CHANGELOG.md`, AMENDMENT-013, the Component Workbench plan/review, and the production playbook.

The non-negotiable product contract is unchanged:

1. exact component candidates are reviewed before assembly;
2. completeness freezes an immutable manifest;
3. assembly consumes that manifest only;
4. the final artifact is downloaded, hashed, probed, and reviewed against the current manifest;
5. Gate 3 is a separate human decision on the exact final;
6. Gate 4 remains a publish hold/go gate, never auto-publish.

A render vendor may execute composition mechanics. It may not perform unreviewed creative judgment.

## Findings

### P0 — A renderer swap cannot repair the current prerequisite and orchestration failures

**Evidence:**

- `docs/PROGRESS.md:10-12` records the stuck soundtrack wait plus real missing-visual and zero-VO failures.
- `docs/CONTEXT.md:296-307` records incomplete shared-call-graph integration, first-child ownership, mutable inventory, and Gate 3 lineage defects.
- `BUILD_PLAN.md:259-293` keeps VF-CW-001..012 mandatory and inserts VF-RA-001..004 before final manifest consumption/proof.

**Ruling:** Preserve M15. No provider integration may bypass candidate approval, manifest freeze, durable orchestration, or Gate 3 hardening.

### P0 — Current caption timing is still approximate without word timestamps

**Evidence:** `src/services/caption_timing.py:8-11` declares proportional timing approximate; `:110-149` divides each beat by word count when complete word timestamps are absent.

**Impact:** A better caption renderer can make approximate timings look prettier while remaining out of sync. Supplied word timing must be part of RendererSpec when karaoke/active-word behavior is required. Provider transcription cannot become authoritative because exact approved VO/text lineage already exists.

### P0 — Transition semantics are not faithfully executable end to end

**Evidence:**

- `src/services/cue_compiler.py:95-106` allows `cut`, `crossfade`, `hold`, `dissolve`, and `wipe`.
- `src/services/edit_planning.py:1117-1177` carries the transition string into `transition_in`.
- `src/assembly.py:46-47` declares only `cut`, `crossfade`, `slide`, and `whip`.
- `src/assembly.py:498-518` treats only `crossfade`, `slide`, and `whip` as non-cut transitions and maps only those to xfade effects; `:541-566` gives unmapped values a near-zero transition rather than their requested semantics.

**Impact:** A compiled `dissolve`, `wipe`, or `hold` can degrade to a hard cut or static segment semantics without a capability blocker. This violates the intent of explicit, evidence-preserving transition decisions.

**Required correction:** Provider-neutral capability validation and an explicit lowering map. Unsupported mandatory transitions block. They never silently become `cut`.

### P0 — The current render plan loses part of the approved sound design

**Evidence:** `src/services/edit_planning.py:1170-1197` initializes each render segment with `sfx: []`, music `{}`, and `original_audio: False` even though compiled cues carry SFX/music/source-sound intent elsewhere.

**Impact:** Sound design can be approved/planned but absent at the renderer boundary. A hosted renderer cannot infer the missing exact artifacts or gains without violating the gate.

**Required correction:** RendererSpec must bind exact soundtrack/source-sound/SFX artifacts, timings, gain envelopes, fades, and ducking automation from the manifest.

### P1 — Current captions are styled plates, not a full motion-caption system

**Evidence:** `src/assembly.py:722-760` resolves a small placement vocabulary and starts a static PIL RGBA text-card path; `:765-892` performs fixed wrap/layout, rounded backgrounds, shadows, and placement. The implementation does not consume per-word keyframes or expose arbitrary role-specific motion composition.

**Impact:** The recent font, wrapping, pill, and brand-token changes improve legibility, but cannot deliver native active-word animation, emphasis motion, deliberate line choreography, or complex graphics at the speed the product needs.

### P1 — The local motion/transition vocabulary is too narrow

**Evidence:**

- `src/assembly.py:377-405` implements still motion as one zoompan family; the `pull-back` branch increases zoom rather than producing a distinct zoom-out camera move.
- `src/assembly.py:513-518` uses one fixed 0.5-second duration and only three xfade mappings.

**Impact:** Even correct creative intent collapses into a small set of similar moves. The result feels templated and is expensive to improve through filter-graph patches.

### P1 — Audio mixing is deterministic but not yet editorially expressive

**Evidence:** `src/assembly.py:1000-1089` synthesizes simple sine tones for SFX and mixes them with delayed `amix` inputs; `:1188-1218` applies scalar music volume values before the VO mix. The active boundary does not expose a full manifest-driven gain-envelope/sidechain contract.

**Impact:** This is useful as a fixture/fallback but not a replacement for exact selected production sound assets and approved mix automation.

### P1 — The manifest-to-render boundary needs a portable intermediate representation

**Evidence:** AMENDMENT-013 requires `assemble(manifest_id)`, while the active `AssemblyRenderer.render(plan, ...)` consumes a renderer-shaped plan containing local filesystem paths and current implementation assumptions (`src/assembly.py:301-385`).

**Impact:** Integrating a vendor directly here would leak provider fields into the manifest or duplicate creative rules in every adapter.

**Required correction:** Introduce canonical RendererSpec v1 between manifest and all renderers. Each adapter mechanically lowers the same spec.

## Market findings from official documentation

### Vizard — reject for canonical assembly

Vizard documents an API centered on uploading/linking an existing video, clipping it, and retrieving generated clips. Advanced options include templates, speaker identification, translation, and supplied B-roll, but it is not documented as an arbitrary multi-layer timeline renderer accepting the exact separately approved component graph ViralFactory requires.

**Fit:** derivative repurposing.
**Misfit:** canonical composition under an immutable component manifest.

### Creatomate — first bake-off candidate

Official RenderScript documentation exposes:

- arbitrary elements/compositions on tracks and timelines;
- explicit time/duration, video/image trims and fit modes;
- keyframes and named animations;
- transitions and nested compositions;
- audio elements, trim/fades/volume;
- custom fonts and text properties;
- supplied word-level transcript data for subtitles;
- async rendering, status retrieval, metadata, webhooks, and documented concurrency limits.

This is the strongest documented match for a mechanically lowered RendererSpec without transferring creative authorship.

### Shotstack — second bake-off candidate

Official documentation exposes:

- REST JSON tracks, clips, layers, trims, transitions, filters, overlays, and fonts;
- animation tweens including volume;
- rich captions using supplied SRT/VTT with word-level animations/highlighting;
- async render IDs, status, callbacks/webhooks, and asset hosting;
- transparent minute-based pricing and API access on all plans.

It is a strong operational and fallback candidate. The bake-off must prove exact caption timing import, required graphics, audio automation, and no unsupported-feature degradation.

### Remotion — reserve option

Remotion offers maximum composition control, local/server rendering, caption primitives, transitions, and cloud rendering. It preserves portability, but it changes the problem from maintaining FFmpeg/PIL to maintaining a React video product and render infrastructure. Use only if hosted APIs fail quality/economics or vendor portability becomes more valuable than implementation burden.

### JSON2Video — reserve only

Its JSON model includes scenes, elements, transitions, subtitles, and webhooks at simple monthly minute tiers. However, its documented webhook model is unsigned and does not retry delivery, so ViralFactory would need stronger polling/reconciliation. It does not outrank the first two candidates for the initial spike.

## Recommended decision

Adopt the DIVERGENCE-019 boundary:

`immutable manifest → RendererSpec v1 → adapter → external/local render → local download/hash/probe/evidence → Gate 3`

Run a blind three-way comparison of the existing renderer, Creatomate, and Shotstack using identical frozen fixtures. Select the provider only after operator quality judgment and verified cost/lineage/reliability evidence. Preserve FFmpeg/PIL as the conformance and emergency fallback.

## Required builder work

- VF-RA-001 — RendererSpec v1, capability registry, local lowering, conformance fixtures.
- VF-RA-002 — isolated Creatomate and Shotstack spike adapters, same frozen fixtures, no production route.
- VF-RA-003 — blind operator review plus cost/terms/reliability evidence and explicit provider ruling.
- VF-RA-004 — selected production adapter with idempotent jobs, authenticated webhook/poll reconciliation, local artifact import/hash/probe/review lineage, and no provider publish path.

These tasks belong after the manifest schema is stable and before final VF-CW-011/012 deployed proof. They do not supersede any VF-CW task.

## Review verdict

**Architecture:** approve hybrid render execution.
**Primary candidate:** Creatomate.
**Second/fallback candidate:** Shotstack.
**Canonical assembler:** not Vizard.
**Local FFmpeg/PIL:** keep as baseline/fallback and evidence mechanics; stop treating it as the sole polish engine.
**Charter:** no version bump required.
**Production selection:** pending real bake-off and operator decision.
