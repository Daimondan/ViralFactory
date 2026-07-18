# CHANGELOG — ViralFactory

> **If you made a decision and it's not in the changelog, it is a bug.**

All decisions — tech, logic, structure, strategy, ops — logged here with type tag + rationale.

---

## 2026-07-18

### VF-VS-303 — episode_plan delegates chunking to caption_timing [STRUCTURE]
**What:** `episode_plan.EpisodePlanCompiler._chunk_vo_text` now delegates to `services.caption_timing._chunk_words` with episode-pinned bounds (3, 5). The duplicated no-dangling-fragment algorithm is removed; episode format keeps its 3–5 spec while the generic reel path uses the amendment's 3–6 default through the same shared function.
**Why:** Two copies of the chunking algorithm drift. VF-VS-301 extracted the service; VF-VS-303 completes the no-duplication acceptance criterion.
**Rationale:** Episode format's 3–5 bound is a format-spec decision, not a code decision — passing it as a parameter keeps one algorithm with two bound sets. The shared `_chunk_words` is the single source of truth for phrase splitting.
**Verification:** 5 new delegation tests prove equivalence with the shared service, 3–5 bounds, no dangling tails, exact reconstruction, and empty handling. 83 tests across episode/caption suites green. Full suite pending.

### VF-VS-302 — Cue compiler produces phrase-level captions [LOGIC/FIX]
**What:** `services/cue_compiler.py` now imports and calls `caption_timing.chunk_captions` for each `function=caption` text intent. A long caption splits into multiple `CompiledCue`s — one per 3–6 word phrase, timed proportionally within the beat's VO span. Short captions (≤6 words) stay a single cue. Blank/zero-duration captions emit one spanning cue so the text intent stays visible. Each phrase cue carries `metadata.phrase_index`, `metadata.word_count`, and `metadata.approximate_timing=True` (until word timestamps land).
**Why:** The cue compiler previously emitted one full-beat caption per text intent — the Draft 8 defect (AMENDMENT-010 Condition 3, ledger §7 cause #2). Short-caption tests passed while long captions silently shipped as one giant overlay.
**Rationale:** Caption chunking is mechanical timing that belongs in one shared service (`caption_timing`), not inlined per compiler. The cue compiler now delegates rather than duplicates. Existing single-caption tests (2-word "Read this", "Eighth wonder") still pass because short text produces one phrase by construction.
**Verification:** 7 new multi-phrase tests (long caption splits, within-span, contiguous, short-stays-single, multi-beat, metadata, blank). 49 tests across caption/cue/integration suites green. Full suite pending.

### VF-VS-301 — Caption timing service extracted [STRUCTURE]
**What:** Added `src/services/caption_timing.py` with `chunk_captions(vo_text, duration_sec, word_timestamps=None) -> list[CaptionPhrase]`. Reuses the no-dangling-fragment algorithm from `episode_plan._chunk_vo_text`, lifted to 3–6 word bounds per AMENDMENT-010 (configurable). Proportional timing is flagged `approximate: True`; a complete word-timestamp path is ready for T2.6–T2.8. `reconstruct_text()` guarantees exact-text join.
**Why:** Full-beat captions are a confirmed Draft 8 defect. The cue compiler (VF-VS-302) and episode plan compiler (VF-VS-303) must share one chunking implementation rather than duplicating logic.
**Rationale:** Caption chunking is mechanical timing, not judgment — it belongs in a shared deterministic service, not inlined in two compilers. The `approximate` flag makes the proportional-timing assumption visible so downstream compliance can discount it until word clocks arrive.
**Verification:** 16 new tests cover phrase bounds, dangling-tail rebalancing, exact reconstruction, proportional coverage, timestamp fallback, and edge cases. 154 tests across caption/cue/episode/integration suites green.

### VF-VS-203 — Tautological config-style tests replaced with behavioral proof [STRUCTURE/FIX]
**What:** Deleted `tests/test_vf_au_302_304_config_style.py`. Its `TestVisualStyleRenderTokens` and `TestConfigDrivenMusicSFX` classes inspected Python source (`inspect.getsource`) and DB schema strings to claim VF-AU-302/304 acceptance — they never loaded two configs and rendered. Added `tests/test_vf_vs_203_behavioral_replacement.py`: a single two-tenant pass that loads two Visual Style modules and asserts different resolved overlay + SFX parameters through real `AssemblyRenderer` instances with zero Python edits, plus explicit fallback-path tests and a silence-valid CueCompiler check. A guard test pins the deleted file to keep it from returning.
**Why:** AMENDMENT-010 Condition 2 and the re-opened VF-AU-302/304 require "two tenant fixtures render different styles with zero Python edits" verified by behavior, not source inspection. The old tests passed while the code they claimed to cover was still hardcoded.
**Rationale:** Acceptance criteria met by reading code rather than exercising it are tautological — they cannot detect regression and they let charter violations ship. Behavioral proof now lives in `test_vf_vs_201_render_styles.py`, `test_vf_vs_202_sfx_presets.py`, and the new `test_vf_vs_203_behavioral_replacement.py`. Reference-asset coverage (the old `TestReferenceAssetInjection`) was already behavioral in `test_reference_assets.py` and `test_vf_au_202_media_inventory.py`; the silence-valid case is retained both here and in `test_vf_au_601_integration_suite.TestSilentPiece`.
**Verification:** The six relevant test modules (68 tests) pass after deletion; full suite 1,631 tests green in 167s.

### VF-VS-202 — SFX presentation moved to config/modules [STRUCTURE/LOGIC]
**What:** Replaced `AssemblyRenderer._SFX_PRESETS` with `sfx_presets` and `sfx_default_preset` in `config/render_styles.yaml`. The shared style loader applies optional tenant Visual Style frontmatter overrides, and missing/unknown cue names use the configured fallback rather than a Python-owned preset name.
**Why:** SFX frequencies, durations, volumes, and fallback selection were embedded in renderer code. Tenants could not change sound presentation without editing Python.
**Rationale:** Deterministic synthesis is a renderer mechanism; its presentation parameters are generic config and tenant module data. Silence remains valid when no cue exists, while explicitly requested cues retain the prior safe-fallback behavior through config.
**Verification:** A fail-first behavioral test creates two tenant modules with different `accent` frequencies/volumes and resolves both through real renderers. Existing SFX mixing behavior remains green. 14 focused tests and the full 1,632-test suite pass.

### VF-VS-201 — Overlay presentation moved to config/modules [STRUCTURE/LOGIC]
**What:** Replaced `AssemblyRenderer._OVERLAY_STYLES` with `config/render_styles.yaml` and a mechanical loader that applies optional `render_styles.overlay_styles` YAML frontmatter from each tenant's Visual Style module. Renderer construction now carries config/module/tenant context through `RenderReviewService`; unknown style refs use the configured `default` style.
**Why:** Python contained presentation values and the old structural test only proved that a config parameter existed. Tenants could not actually render different styles without code edits.
**Rationale:** Generic FFmpeg defaults belong in config; tenant presentation belongs in the tenant-owned Visual Style module. Module values override matching generic fields, while missing module values inherit config without Python color/font/size constants.
**Verification:** A fail-first behavioral test creates two tenant modules with different hook colors/sizes and resolves both through real `AssemblyRenderer` instances. The configured fallback is also asserted. 31 focused tests and the full 1,633-test suite pass.

### VF-VS-103 — Behavioral dual-path equivalence locked [STRUCTURE/LOGIC/FIX]
**What:** Added a behavioral test that executes identical asset input through the Flask edit-plan route and `ProductionChain._step_edit_plan`, then compares the complete LLM invocation, plan, and operator cut list. Added deterministic draft-to-asset lookup and durable `production_step_data` storage required by the autonomous chain. Video polling now follows the provider returned by submission rather than a pre-submission fallback guess.
**Why:** The prior AST checks proved only that service names appeared in source. Executing the real route and chain exposed that the autonomous path called nonexistent store methods and therefore could not run. Full-suite execution also exposed provider mismatch when a mocked/adapter-selected submission differed from the initially resolved fallback.
**Rationale:** Shared service behavior must be proven at the transport boundary, and autonomous step outputs must survive process restarts. Provider-specific polling must follow the accepted submission contract, not stale resolver state.
**Verification:** The new equivalence test failed first on missing `get_asset_by_draft`, then on missing step persistence, and passes after both fixes. The four affected video-handoff tests pass after provider propagation. 30 focused tests and the full 1,633-test suite pass.

### VF-VS-102 — Legacy VO-led Reel path retired [STRUCTURE/LOGIC/OPS]
**What:** Removed the old provider/planning/render body from `reel_production_runner.run_reel_production`. The compatibility entrypoint now fails before database or provider setup. `/api/assets/<id>/produce-reel` also fails closed with HTTP 409 and does not enqueue a legacy job.
**Why:** The old runner compiled full-beat captions, forced hard cuts, and filled speech overruns with still images. Leaving it reachable would preserve the exact dual-path defects M13 retires.
**Rationale:** Until the shared service workflow is behaviorally locked, disabling the superseded path is safer than silently producing known-bad or paid output. Recovery helpers for already-submitted provider jobs remain available, while `build_reel_plan` has no runtime caller.
**Verification:** Two fail-first regressions prove the runner exits before state/provider work and the operator route creates no job. 24 focused tests and the full 1,632-test suite pass; source search finds only the `build_reel_plan` definition under `src/`.

### Structured Reel overlay extraction locked by regression [FIX/LOGIC]
**What:** `extract_reel_beats()` now treats dictionary-shaped `text_on_screen` as structured renderer intent and extracts only its `text` field; string-shaped legacy overlays remain unchanged. Writer self-audit revisions now update either shape without calling dictionary methods on legacy strings or discarding structured metadata.
**Why:** Coercing the whole dictionary with `str()` burned internal `position` and `style` metadata into Draft 8 as audience-visible text.
**Rationale:** Approved audience text and renderer metadata are separate roles. Mechanical extraction must preserve the exact approved text without exposing the transport structure.
**Verification:** The extraction regression failed against the old coercion with the full dictionary in `overlay_text`; the sibling revision regression failed with `AttributeError` on a string overlay. Both pass after the fixes. The 10 Reel-production tests plus the 3 self-audit-fix tests pass; the full 1,630-test suite passes.

### VF-VS-101 — Operator and autonomous Assembler paths reconciled [STRUCTURE/LOGIC/FIX]
**What:** Moved edit-plan generation, missing-media planning/acquisition, and render/review orchestration behind transport-neutral `EditPlanningService.generate_for_asset`, `MediaPlanningService.generate_for_asset`, and `RenderReviewService.render_for_asset` entrypoints. The three Flask routes now handle only request validation, job bookkeeping, response serialization, and status mapping; `ProductionChain` calls the same methods. Added `ServiceResponse` as the shared boundary and persisted binary material `file_path` values so scoped inventory can identify real render-ready capture uploads.
**Why:** The operator routes duplicated hundreds of lines of LLM, inventory, provider, and renderer logic while the autonomous path called separate service stubs. That made route and chain behavior diverge and caused the Draft 8 failure class to bypass the intended Assembler controls. The inventory service also expected a durable binary path that Materials Intake did not persist.
**Rationale:** HTTP transport and job state remain in Flask; production judgment and mechanics live in shared services. Both entry paths now execute the same service methods for the same asset. Inventory remains fail-closed: missing tables or nonexistent local files are treated as no render-ready media, never as usable ingredients.
**Verification:** Added behavioral route delegation, HTTP-only source-boundary, shared-chain-entrypoint, binary-path inventory, final-cut review-linkage, and extended-review preservation regressions. 199 focused tests and the full 1,628-test suite pass. A real Flask server on port 9131 returned the service-owned `Asset not found` 404 from all three POST routes; no paid provider or publish call was made.

### Architect inbox batch fully applied [OPS/FIX/STRUCTURE]
**What:** Processed `MANIFEST-2026-07-18-draft8-pipeline-upgrade.md` into `docs/inbox/processed/`; completed its missing APPLY work by correcting the new charter's own v3.7 header/path, making `docs/CONTEXT.md` the v3.7 operational mirror, and updating README role/status references. Removed two byte-identical stale inbox duplicates whose canonical copies were already filed under `docs/decisions/` and `docs/corrections/`.
**Why:** The architect payload had already added AMENDMENT-010, Charter v3.7, and M13, but the manifest was deliberately left in the builder inbox and the operational mirror still identified v3.6. The new charter file also retained v3.6 in its title and metadata.
**Rationale:** Inbox batches are complete only after filing, APPLY execution, and an empty inbox. The context now records both the binding M13 target and the currently unimplemented dual-path, config-style, caption, soundtrack, visual-event, and false-green gaps without claiming they are already built.

### AMENDMENT-010 ratified — Visual + soundtrack pipeline, Charter v3.7 [STRATEGIC/STRUCTURE]
**What:** Architect ratified DIVERGENCE-014 (visual + soundtrack pipeline + dual-path reconciliation) as AMENDMENT-010 → Charter v3.7. Added M13 milestone (23 tasks: VF-VS-101..703). Filed `docs/decisions/DIVERGENCE-014-*.md`, `docs/decisions/AMENDMENT-010-*.md`, `docs/CHARTER-v3.7.md`. BUILD_PLAN.md → v2.0.
**Why:** Builder filed Track B proposal to promote Draft 8 visual + soundtrack lessons into the reusable pipeline. Architect's live-code audit found: (1) the Assembler Full Upgrade built correct services (`src/services/*.py`) that the operator-facing route never reaches — `src/app.py` routes bypass every new service; (2) VF-AU-208/302/304 tests are tautological (AST structural / source inspection, not behavioral); (3) cue compiler produces full-beat captions not phrase-level; (4) no soundtrack plan contract exists; (5) no semantic visual events; (6) `build_reel_plan` hardcodes `transition_in: "cut"`.
**Rationale:** The dual-path gap is the root cause of Draft 8 defects reaching the operator. M13-A (dual-path reconciliation) is the foundation — wire operator routes to the existing services first, then extend with visual events, soundtrack plan, config-driven styles, phrase-level captions, and false-green fixes. Seven binding conditions. Five tasks re-opened (VF-AU-208, 302, 304, 205, 402).
**Verification:** Charter v3.7 written with all amendments incorporated. BUILD_PLAN.md patched with 23 M13 tasks. DIVERGENCE-014 and AMENDMENT-010 filed. v3.6 marked superseded. Builder note moved to processed.

### Transcription worker test lifecycle and SQLite cleanup [FIX/TECH]
**What:** Guaranteed SQLite connection closure across transcription polling, updates, and startup backfill, and added an explicit process-level background-worker disable switch used by the pytest harness.
**Why:** Every temporary Flask app started a daemon transcription worker. Failed queries against deleted or schema-light test databases leaked descriptors until the suite hit `Too many open files`, causing late video-handoff failures.
**Rationale:** Worker behavior remains tested directly; unit-test app factories must not launch process daemons. Production behavior is unchanged unless `VIRALFACTORY_DISABLE_BACKGROUND_WORKERS=1` is explicitly set.
**Verification:** Four lifecycle regressions and all 17 video-handoff tests pass; full suite 1,621 passed with no worker-loop error flood.

### Draft 8 director’s cut ratified as the Reel visual standard [STRATEGIC/LOGIC/FIX]
**What:** Rebuilt Draft 8 as a VO-led hybrid editorial Reel using 22 semantic visual events, licensed human footage, deterministic StackPenni graphics, 51 exact phrase captions, and an exclusive caption lane. Operator-approved v3 is registered as media ID 42 at `data/media/6/final_2.mp4`; the failed baseline remains versioned at `final_1.mp4`.
**Why:** The baseline used unrelated generated presenters, froze motion after five seconds, leaked structured overlay metadata into audience text, clipped captions, and falsely green-lit missing visual evidence. The v2 review also exposed style-preview captions being baked into production graphics and then obscured by the live VO caption layer.
**Rationale:** Promote the decision process—not this Reel’s exact scenes—into the reusable pipeline: semantic visual events, provenance-aware source policy, separate renderer text roles, caption-lane collision validation, event-aware evidence, and fail-closed review completeness. StackPenni styling remains module/config-owned; generic code owns mechanics.
**Verification:** Approved hash `f94c4ad44d94b4054b9cd267ee45b878239cbd012042ed3c35bf176c57aa172a`; 1080×1920, 30fps, 72.10s, audio present and unclipped, no black frames, exact 190-word caption reconstruction, 22-event visual audit, live route resolves `final_2.mp4`, 1,621 tests passed. Publication was not approved or triggered.

### Reel production moved out of Gunicorn [FIX/STRUCTURE/OPS]
**What:** The cost-approved reel request now validates and enqueues a durable `reel_production` job, returns HTTP 202 immediately, and is executed by a dedicated systemd worker. The operator UI polls job state, survives non-JSON proxy errors, prevents duplicate retries/spend, and starts final rendering only after the worker has produced VO, motion clips, and an exact plan.
**Why:** A real 185-word reel held a synchronous Gunicorn request open while local Chatterbox generated six VO segments. The request exceeded the web-worker/proxy lifetime, surfaced `Bad Gateway` as JSON, and a retry created concurrent 2.4–6.2 GB voice workloads that caused swap pressure and a worker timeout.
**Rationale:** Long local inference and provider polling are worker responsibilities, not HTTP-handler responsibilities. The jobs table is the durable handoff and idempotency boundary; systemd owns the process lifecycle.
**Verification:** 1,617 tests pass. Asset 6's complete 72.1-second VO survived the failed HTTP request; all six already-paid Kling tasks were recovered from provenance without duplicate spend; the final 1080×1920 reel rendered at 72.066 seconds with an AAC audio stream (mean -18.0 dB, max -0.1 dB).

### Reel production — VO-first motion pipeline [FIX/LOGIC/TECH]
**What:** Replaced the misleading still-image slideshow path with a VO-first reel workflow. Structured `vo_text` is generated completely and measured before planning; incomplete or mismatched VO now blocks rendering. Each approved beat receives a stable media link, configured Kling image-to-video clips are submitted in one concurrent batch after an exact operator cost approval, and the measured VO timeline compiles deterministic cuts, exact captions, and untouched `text_on_screen` overlays. FAL jobs now poll through their configured endpoint, cached files receive owner-scoped media rows, and the manual seconds/aspect/prompt dialog was removed.
**Why:** Draft 7 produced a 15.5-second silent slideshow for a 176-word reel, then passed audio review because the edit plan declared silence. The UI said “Generate video” but never invoked a video provider.
**Rationale:** VO is the constitutional master clock; Writer text and visual intent are immutable; Media Planner judgment lives in a versioned prompt; format/render values and provider prices live in config; and paid motion calls occur only after the operator sees and accepts the current per-piece estimate. Existing stills remain as intentional hold coverage after each motion clip rather than silently replacing motion.
**Verification:** 1,610 tests passing; live no-spend estimate for asset 5 reports six ready storyboard stills, six 5-second Kling clips, and a $3.00 animation estimate. No paid provider calls were made during verification.

## 2026-07-17

### T11.5-T11.10 — Episode format complete [TECH]
**What:** Six tasks completing the episode format capability: (T11.5) episode-format module schema + bootstrap flow + StackPenni show bible + visual-style amendment (pending gate); (T11.6) EpisodePlan schema + Writer beats + mechanical shot spec assembly + edit plan with beat_id + enforced loudnorm I=-14; (T11.7) storyboard gate infrastructure; (T11.8) Layer-2 asset QC — face-embedding identity check + color-histogram grade check, thresholds from config, flags advisory; (T11.9) Layer-3 critic — rubric in module, advisory scores, never blocks; (T11.10) golden episode fixtures + Layer-1 pass-rate metric.
**Why:** The episode format enables recurring-character, beat-structured, reference-conditioned episode production — the target genre. All show-specific content lives in gated tenant assets; the harness knows the schema, never the character.
**Rationale:** Three subagents worked in parallel on T11.5 (module+bootstrap), T11.6 (plan schema+Writer), and T11.8 (asset QC). T11.9 (critic) and T11.10 (goldens) were built directly. 168 new tests, 1,598 total passing.

### T11.4 — fal provider in MediaAdapter [TECH]
**What:** Added fal.ai provider to MediaAdapter: `generate_image(reference_images=[...])` uploads local reference files to fal storage and passes URLs for reference-conditioned image generation. `submit_video(mode="image_to_video", source_image=...)` uploads the source still and submits an image-to-video job. `check_fal_job()` polls via `fal_client.status`/`result`. All endpoints read from `config/models.yaml` — zero hardcoded. Cost from config `cost_per_image_usd`/`cost_per_second_usd`. Provenance logged with `provider="fal"`.
**Why:** Reference conditioning (character sheets, location plates) is the mechanism that makes recurring character/visual consistency possible. Image-to-video from approved stills is the cheap-to-expensive ordering (storyboard → animation).
**Rationale:** The fal_client library (v1.0.0) provides submit/poll/result with file upload — matching the existing async pattern. The adapter routes by config `provider: "fal"` — no code changes needed to switch between fal and legacy providers.

### T11.2 — EpisodePlan Layer-1 lints [TECH]
**What:** New `src/episode_lints.py` module with 6 deterministic pre-spend lints: registry referential integrity (approved assets only), beat grammar (hook first, ≤3s, lesson+cta present), duration budget (±10%), banned-token scan (config-driven), grade-token-present, numbers→graphics. Banned tokens read from `config/models.yaml` `episode_lint.banned_prompt_tokens` — config, not code.
**Why:** A plan violating any lint cannot trigger a paid media call. The mush-image failure class (text/screens/logos in generated images) is eliminated by construction, not by review.
**Rationale:** The lints are mechanical (no LLM, no judgment). They extend the existing feasibility-checks pattern (T10.3) with episode-format-specific checks. The reference_assets module (T11.3) provides the registry that lints resolve against.

### T10.10 — Compliance test suite [TECH]
**What:** 45-test consolidated suite covering all 8 acceptance criteria: 92s/18s regression, coverage proof, generic content corpus (no tenant strings), three-round cap, cost cap, text-boundary firewall, approval integrity, real rendered asset validation.
**Why:** T10.10 requires a dedicated test suite proving the compliance loop catches real failures, never auto-publishes, never changes approved text, and works with all format types without tenant-specific code.
**Rationale:** Individual pieces were already tested across multiple files (test_feasibility_t10, test_compliance_review_t10, test_remediation_loop_t10, test_vf_au_401_404). This suite consolidates them and adds the missing pieces: no-tenant-strings scan across 14 generic source files, approval integrity state-model checks, and operator-facing review panel integration test.

### T10.7 — Assets UI: remediation history + coverage [TECH]
**What:** New `/api/assets/<id>/compliance` API endpoint + compliance panel in `assets.html`. The panel shows per-beat coverage (status + evidence), remediation round history (verdict, actions, cost per round), total remediation spend, issues (severity + description + beat), and a plain-language stop reason. Technical JSON is available in a collapsible details section — not the default view. All user-generated content is escaped via `escapeHtml()` using `textContent` (XSS-safe).
**Why:** Acceptance criteria require the operator to see the full remediation history without reading JSON, with per-beat coverage human-readable and the stop reason in plain language.
**Rationale:** The compliance data already existed in `asset_reviews.findings_json` and `edit_plans.review_round_history` — this task surfaces it in the UI rather than creating new data structures.
**Fix:** Also fixed pre-existing `sqlite3.Row.get()` AttributeError in `AssetReviewer.get_compliance_state()` and a template crash on dict-shaped reel posts (`reel_excerpt[:300]` on a dict).

**[STRUCTURE] VF-AU-003: DIVERGENCE-013 ratified via AMENDMENT-009 — Charter v3.5 → v3.6**

DIVERGENCE-013 APPROVED WITH CONDITIONS. Three boundary refinements ratified with seven binding conditions:

1. **Capture policy approved with treatment at Gate 1** — `capture_required`, `capture_preferred`, `archive_preferred`, `stock_allowed`, `generated_allowed`, `text_card`. No silent inference or downgrade downstream.
2. **`capture_required` blocks compliance and Gate 3 readiness** — drafting, VO, media planning, and preview rendering continue. Rough previews render with `preview_only` flag.
3. **Legacy capture tasks not silently migrated** — mark `legacy_unclassified`, require classification when next entering production.
4. **Hash-lock protects entire approved Writer contract** — not just `platform_content` but semantic beats, evidence references, visual/audio intent, capture policy, and primary audience action.
5. **Media Planner translates intent, does not redefine it** — may not change claim, subject, evidence requirement, beats, emotional job, audience action, or capture policy. AMENDMENT-007 §2 "zero LLM text calls" clarified: "no text generation" = no audience-copy generation. Schema-validated LLM judgment for media planning, edit planning, and compliance review is permitted.
6. **Playbook type metadata required and enforced** — `playbook_type: onboarding | production | learning`. Onboarding UI fails closed on missing metadata.
7. **Process changes remain versioned and human-gated** — same discipline as the eight modules (AMENDMENT-005 R3).

Decisions D (compliance authority) and E (learning authority) require no new transfer — already governed by AMENDMENT-008 and the existing charter.

Files: AMENDMENT-009 (new), CHARTER-v3.6.md (new — supersedes v3.5), DIVERGENCE-013 (status updated), CONTEXT.md, BUILD_PLAN.md (M12 milestone with 30 tasks), PROGRESS.md, CHANGELOG.md.

**[STRUCTURE] VF-AU-001: Assembler upgrade baseline verified**

Audited all 10 drift claims from the handoff's `09-VERIFIED-CODE-DRIFT.md` against live code at commit `7ab6d1b`. All 10 confirmed. Classification: 7 implementation compliance, 1 design change (route→service refactor), 2 schema enrichment (identity chain + learning loop). 1,084 tests collected (1,083 pass, 1 pre-existing test-isolation flake). Baseline document at `docs/reviews/ASSEMBLER-UPGRADE-BASELINE.md`. No behavior changes made.

Rationale: the handoff requires verified current-state before any implementation work. All claims re-checked against live code with exact paths and line numbers.

**[STRUCTURE/LOGIC] VF-AU-002: DIVERGENCE-013 filed — assembler production-contract boundaries**

Filed `docs/decisions/DIVERGENCE-013-assembler-production-contract-boundaries.md` with three boundary refinements requiring architect/operator ratification before behavior changes:

- **A: Capture semantics** — split capture intent into `capture_required` (blocking until real evidence exists), `capture_preferred` (real preferred, declared fallback allowed), `archive_preferred`, `stock_allowed`, `generated_allowed`, `text_card`. Refines AMENDMENT-006's non-blocking capture flag.
- **B: Writer vs Media Planner** — Writer owns exact approved content + semantic visual/audio intent; Media Planner owns provider-aware acquisition/generation prompts. Refines AMENDMENT-007's Writer/Assembler split.
- **C: Production playbook classification** — eight onboarding playbooks remain onboarding; viral-content production playbook is a Process Registry composition with `playbook_type: onboarding | production | learning` metadata.

Decisions D (compliance authority) and E (learning authority) are already ratified via AMENDMENT-008 and the charter — no new divergence needed. Status: PENDING architect/operator decision.

Rationale: these three boundaries materially refine previously approved rules and must not be hidden inside implementation work.

**[STRUCTURE] P0: Working-tree artifacts committed before Assembler Full Upgrade Phase 0**

Committed all uncommitted working-tree state (11 modified files + 2 untracked docs) to establish a clean baseline before any Phase 0 ratification work. Includes: evidence-bounded meta-analysis v2, production playbook v1, viral-patterns module v3, Writer/Assembler prompt updates (generate_v3 v4.1, edit_plan_v1 v1.5), assembly/VO/pipeline code changes, test fix for prompt version assertion. 1,084 tests passing.

Rationale: the authority hierarchy requires a clean repo before any ratification or boundary-change work proceeds. The handoff package (00-READ-ME-FIRST.md) explicitly warns the builder to reconcile local state before designing against the repo.

**[LOGIC] Viral-patterns module v3.0 → v3.1: five operator amendments**

Five amendments to `modules/stackpenni/viral-patterns.md` per operator review of the Assembler Full Upgrade handoff:

1. **Corpus-bias caveat (borrowed authority):** The corpus is a borrowed-authority set — every piece was already a public winner selected by third-party rankings, not a StackPenni-matched sample. Patterns observed in winners may reflect what ranking sources valued (outrage-driven engagement bait, celebrity reach, algorithm-favored controversy) rather than what serves StackPenni's brand. All corpus-derived patterns are transferable hypotheses requiring tenant validation.

2. **StackPenni-accessible patterns note:** The corpus includes formats not currently accessible to StackPenni's production capabilities (celebrity interviews, multi-camera studio, high-budget animation, licensed music). Patterns requiring unavailable resources are flagged as aspirational and excluded from active production rules. Only patterns achievable with current tools (VO, generated imagery, text overlays, licensed SFX/music, reference-conditioned generation) drive active Writer/Assembler decisions.

3. **Polarization house rule:** Outrage and polarization mechanics (us-vs-them framing, manufactured conflict, identity-group attacks) appear in the corpus as high-comment drivers but are not approved StackPenni production patterns. StackPenni's brand is Caribbean AI + wealth — authority, trust, and community are the assets. Pieces whose primary comment driver is manufactured outrage must be flagged for operator review before drafting. Debate and contrarian takes are allowed; caricature and bad-faith provocation are not.

4. **Comment-ratio performance hypothesis:** Added comment-to-like ratio (comments ÷ likes) as a performance hypothesis. A high ratio suggests debate-driven reach; a low ratio suggests passive agreement. StackPenni should track this ratio per piece to learn which treatments generate discussion versus approval, and whether discussion serves the brand's authority goal.

5. **Cross-tab contrast-set note:** The corpus currently supports only single-dimension tabulations. The next evidence pass should capture cross-tab contrast sets (format × audio mode × comment-to-like ratio, hook mechanism × emotional job × completion). Cross-tabs reveal interaction effects that single-dimension averages mask. Added to both viral-patterns module (Evidence limits section) and meta-analysis v2 (Recommended next evidence pass section).

Also updated production playbook v1 with `derived_ratios` block (comment_to_like, share_to_like, save_to_like) in the performance record schema, and added a comment-ratio-based action validation section to the Analyst analysis spec.

Rationale: the operator identified that the v3.0 module, while evidence-bounded, still carried implicit assumptions about borrowed authority, accessible patterns, and brand alignment. These five amendments make the module's scope explicit and prevent corpus-derived patterns from silently overriding brand judgment.

---

## 2026-07-16

**[RESEARCH/LOGIC] Winner-corpus meta-analysis redone with evidence boundaries**

Replaced the prior keyword-frequency and raw-average interpretation with `docs/research/viral-content-meta-analysis-v2.md`. The new analysis explicitly separates OBSERVED, MEASURED, HYPOTHESIS, and HOUSE RULE claims; documents winner-only selection bias, missing retention/share/save/reach metrics, category confounding, small groups, and scene-level rather than literal frame-by-frame analysis; and removes unsupported causal claims including universal format/audio rankings, fixed cut cadence, overlay-every-segment, SFX-every-change, implied-CTA lift, and uncited muted-view percentages.

Rationale: the prior sheet and runtime module converted a useful admired-content corpus into false precision. Likes/comments and free-form AI mention counts cannot establish which treatment caused performance. The corrected standard preserves useful creative observations while preventing hypotheses from masquerading as tenant evidence.

**[STRUCTURE/CONTENT] Evidence-bounded production playbook, contract, and StackPenni runtime module v3**

Added `docs/playbooks/viral-content-production-playbook-v1.md` and machine-readable example `docs/playbooks/viral-content-production-contract-v1.yaml.example`. The contract defines one content brief, stable semantic beat IDs, functional text intents, function/provenance-based media recipes, explicit audio modes, source-resolved edit plans, mechanical/compliance/creative gates, and a post-publication creative fingerprint. Replaced `modules/stackpenni/viral-patterns.md` v2 with v3 so existing `prompts/views.yaml` projections immediately supply the corrected rules to ideation, drafting, series breakdown, and edit planning. The first 3,000 characters contain the runtime assembler rules so the edit-plan view budget does not truncate them. Updated `prompts/draft/generate_v3.md` to v4.1 and `prompts/assembly/edit_plan_v1.md` to v1.5, removing the conflicting hardcoded overlay-every-segment, cut-every-2–4-seconds, CTA-every-piece, music-preferred, and SFX-every-change directives.

Rationale: the Writer must own approved words and semantic intent; the Media Planner must choose feasible media from available tools; the Assembler must resolve real ingredients and timing without inventing copy. Stable beat IDs are the handoff that lets compliance and learning trace the same content contract end to end.

**[ARCHITECTURE AUDIT] Full playbook automation gaps documented**

The production playbook now distinguishes prompt-level integration from end-to-end automation. `ProductionChain._step_media_plan`, `_step_media_exec`, `_step_edit_plan`, and `_step_render` remain stubs while equivalent behavior lives in route handlers. P0 gaps are stable beat IDs, deterministic text/audio translation, registry drift between draft v2/v3 paths, and comprehensive pre-render feasibility. P1 gaps are config-driven overlay/SFX styles, reference-asset injection/provenance, post-render module context, performance ingestion, and human-gated learning proposals. These are documented in the playbook and the Sheet's `Implementation Gaps v1` tab; no claim is made that the autonomous assembler already consumes the full contract.

**[RESEARCH/OPS] Google Sheet v2 analysis and production tabs written and verified**

Added four live tabs to the existing analysis workbook: `Meta-Analysis v2` (52 rows), `Production Contract v1` (42 rows), `Assembler QA v1` (23 rows), and `Implementation Gaps v1` (14 rows). The original Meta-Analysis tab remains as an audit trail. A second audit added explicit modality and corpus-hygiene findings: 9 unavailable ranks, 10 thumbnail-only rows, one duplicate pair (32/98), uneven batch depth, overlapping/contradictory coding, and the Rank 23 Caribbean misclassification. Read-back verification confirmed all required markers and confirmed the removed unsupported claims are absent from v2.

Rationale: the Sheet remains the primary analysis artifact, while the repository documents and runtime module keep the same conclusions executable.

---

## 2026-07-14

**[STRUCTURE/STRATEGIC] M11 — Episode format + reference assets correction filed and added to BUILD_PLAN (v1.8)**
Architect correction `CORRECTION-episode-format-and-reference-assets-v1.0` filed to `docs/corrections/`. BUILD_PLAN.md bumped to v1.8 with M11 addendum (10 tasks + checkpoint). Core architectural shift: the harness gains one generic capability — reference-conditioned, beat-structured episode production. All show-specific content lives in gated per-tenant assets (episode-format module, reference asset registry, storyboard gate). Media generation becomes stills-first (cheap, operator-approved) then animation of approved stills only (expensive). Sora retired (API discontinued 2026-09-24). fal.ai added as media provider with config-driven per-unit costs. Four validation layers (deterministic lints, embedding/histogram QC, gated critic rubric, golden-episode fixtures). ElevenLabs Music for one-time registry music beds. Sequencing: Sora retirement + Layer-1 lints (P0 immediate) → registry + fal provider → format module + bootstrap → EpisodePlan + Writer/media-plan v2 → storyboard gate → validation layers 2–3 + goldens.
Rationale: Operator diagnosed that rendered videos have no recurring character, style, or format — each output is a different genre. Root cause: no reference conditioning in the media path, no beat structure, no stills-before-animation ordering, stale models.yaml. The correction introduces the "episode of a show" paradigm (vs "a video") where freshness comes from the story seed, never format drift.

**[TECH] T11.1 — Sora retired + models.yaml media block v2**
Removed sora generator entry from `config/models.yaml` (OpenAI API discontinued 2026-09-24). Restructured media block per correction §5.2: `image_generators` list (nano-banana-2 = fal-ai/gemini-3.1-flash-image-preview, flux2-pro = fal-ai/flux-2-pro) with `cost_per_image_usd` + `supports_reference_images`; `video_generators` (kling-3 = fal-ai/kling-video/v3/standard/image-to-video, veo-3.1-fast = fal-ai/veo3.1/fast/image-to-video) with `cost_per_second_usd` + `mode: image_to_video` + `native_audio: false`; `music_generators` (eleven-music via ElevenLabs). Legacy grok-imagine-video and veo kept as named backends in video_generators for fallback compatibility. `video_default` changed from grok-imagine-video to kling-3. Verified fal endpoint IDs against live fal.ai API docs. Updated `prompts/assembly/media_plan_v1.md` to reference new generator names. Updated `tests/test_video_fallback.py` with new config shape + added `test_no_sora_in_config` assertion. Assets UI cost estimate (`assets.html`) now reads `cost_per_second_usd` from config instead of hardcoded `$0.05–0.15`. App.py passes `video_cost_min`/`video_cost_max` to template (computed from config, 5s min / 8s max clip). 1,042 tests passing.
Rationale: Sora API is dead — building on it is a defect. Per-unit costs in config are the deterministic inputs to every gate cost card — estimates are computed, never guessed. The correction mandates this structure.

**[STRUCTURE] T11.3 — Reference asset registry + gate surface**
New `reference_assets` SQLite table per correction §2.1 schema (id, business_slug, kind, name, status, payload_json, version, timestamps). New `src/reference_assets.py` — `ReferenceAssetStore` class with propose→approve→retire lifecycle: proposals create version N+1; approving retires any previous approved version of the same kind+name; approved payloads are locked (mutation requires new version through the same gate); `resolve_ref()` returns only approved assets (unapproved = unusable by any generation path — hard business rule); `get_grade_token()` convenience; `get_generation_context()` returns all approved assets structured for prompt injection (grade string, characters with face/wardrobe canon, locations, music beds, card styles, lockup SVGs). New `/setup/reference-assets` UI: per-asset cards grouped by kind, status badges, inline payload JSON editing for proposed assets, approve/retire/new-version buttons, reference image thumbnails with lightbox viewing, stats dashboard, propose-new-asset form. 7 API endpoints. 35 new tests covering schema, lifecycle, versioning, queries, error conditions, generation context. 1,077 total tests passing.
Rationale: The registry is the system of record for every recurring visual/audio identity asset. Characters, locations, grade string, music beds, and card styles all live here, gated by the operator. This is the infrastructure that makes reference-conditioned content generation possible — the grade string gets injected into every image prompt, character refs condition face consistency, location refs anchor scene plates. Without it, every generated video is a different genre with no recurring identity.

**[OPS] T11.3 — Pennifold canon assets seeded from operator Drive folder**
Downloaded 10 files from operator-provided Google Drive folder (WORLD-pennifold-canon-v2.md, CHARACTER-fitzroy-pennifold-v1_1.md, CHARACTER-stackwell-pennifold-v1.md, 2 reference render PNGs, 4 lockup SVGs). Files organized under `data/media/reference/stackpenni/` by kind (character_ref/fitzroy, character_ref/stackwell, grade_token, lockup_svgs). 7 assets seeded via `scripts/seed_reference_assets.py`: grade_token:default (painterly cinematic realism grade string + palette), character_ref:fitzroy (face canon, wardrobe canon, voice register, signature props), character_ref:stackwell (same structure + note about stylized badge needing realism re-render), 4 lockup_svg assets. All in 'proposed' status — operator must approve via /setup/reference-assets before they can be referenced in content generation.
Rationale: The operator provided the show bible (lockup + visual guide) for StackPenni. These are the canonical brand identity assets that define the Pennifold world — characters, grade, palette, tagline. Seeding them into the registry makes them manageable through the UI and referenceable by the content creation pipeline once approved.

---

## 2026-07-11

**[OPS] Pipeline cleanup — full reset for fresh generation**
Wiped all pipeline run data (idea_cards, drafts, assets, edit_plans, asset_media, jobs, feedback_log, playbook_runs — 150 rows total). Deleted 7 old backup DB files (~1.8GB freed). VACUUM'd main DB. Cleaned orphaned media files (157MB). Preserved infrastructure: 92 sources, 629 provenance records, 234 LLM cache entries, 259 materials, 99 image cache entries. System is clean and ready for new video generation.
Rationale: Operator confirmed first full video-with-VO completed successfully. Closing all cards to generate more. No backup needed — just delete.

**[RESEARCH] Viral content mechanics — comprehensive research compiled**
Compiled actionable research on what makes short-form video go viral, covering: (1) 3-part hook formula (pattern interrupt + identity signal + open loop), (2) retention mechanics (2–4s visual changes, payoff ladder, sound design as 50% of retention), (3) emotional trigger hierarchy (Fear/Empathy/Outrage = 3–5x views vs Curiosity; Aspiration/Hope are worst), (4) platform-specific differences (TikTok vs Reels vs Shorts), (5) MrBeast production pipeline analysis (leaked onboarding doc: retention architecture, editing style, creative process), (6) AI tool landscape (Opus Clip, CapCut, ReelsBuilder, Remotion, kinetic-text-ffmpeg, videopython, mosaico, movis, mcp-video). Research doc at docs/research/viral-content-mechanics-2026-07-11.md. Identifies 4-phase upgrade path: Phase 1 (text overlays + captions) → Phase 2 (sound design) → Phase 3 (pacing + structure) → Phase 4 (format templates + advanced). Key finding: our current output (stock clips + VO) is missing every engagement layer — text overlays, SFX, music, captions, pacing variety. These are the upgrade targets.

### 2026-07-11 — Affordance-based format selection and explicit user distribution intent

**LOGIC / STRUCTURE** — Replaced deterministic message-type → format routing with a descriptive Format Guide v2 contract. Formats now describe audience experience, native mechanics, expressive strengths, limitations, production demands, aspect ratio, and evidence quality; `decision_table` and `best_for` taxonomy fields are retired. Idea generation now runs as two LLM stages: format-neutral concept creation followed by treatment selection. Requests carry an explicit `distribution_intent` (`open`, `platform_constrained`, or `exact_format`), every idea records one primary platform and format, and `constraint_source` distinguishes `user_request` from `llm_selected`. Cross-platform derivatives are optional rather than automatic. Approved guides persist gated Markdown and structured JSON sidecars. Rationale: the prior flow discarded requests such as “five Instagram Reels,” encouraged generic category mappings, and made platform coverage look mandatory instead of choosing the medium that best expresses each idea.

**OPS** — Migrated StackPenni's Format Guide to v2.0 under Daimon's explicit approval and added `docs/architect/2026-07-11-affordance-based-format-selection.md`. Real LLM verification showed exact Reel intent remained `Instagram` + `Instagram Reel Script` with `constraint_source=user_request`; open intent selected one X Thread with `constraint_source=llm_selected` and affordance-based alternatives. Full suite: 1,015 passed. Live service restarted and active.

### 2026-07-11 — DIVERGENCE-012 ratified via AMENDMENT-008 (Charter v3.5)

**STRATEGIC / STRUCTURE** — Architect approved DIVERGENCE-012 (final-output compliance loop). Filed AMENDMENT-008 (`docs/decisions/AMENDMENT-008-final-output-compliance-loop.md`) and published Charter v3.5 (`docs/CHARTER-v3.5.md`). The Assembler side gains a compliance contract (LLM-authored alongside the edit plan, defining every required narrative beat and its planned representation), a final-output compliance review (LLM checks rendered asset against approved script + contract), and a bounded remediation loop (max 3 rounds, config-driven cost cap). This is the Assembler-side counterpart to AMENDMENT-007 §3 (Writer-side AI review loop). Three architect conditions: (1) text-boundary firewall — remediation loop must never modify approved `platform_content`, enforced by SHA-256 hash lock at loop entry; (2) config-driven cost guard — `max_remediation_cost_usd` in `models.yaml`, absent = review-only no auto-fix; (3) operator visibility — full remediation history (rounds, changes, verdict, provenance) shown in Assets UI. Retires keyword-based VO/content detection (`asset_review.py:686-705`) as a compliance decision — it was judgment in code, a charter violation. The `_extract_vo_lines` regex in `vo_generator.py` remains as mechanical extraction input only. Supersedes the advisory-only rule from CORRECTION-final-output-review-and-audio-fix-v1.0 Part 2 (the existing ASSET-REVIEW-1 through ASSET-REVIEW-6 checks remain in force; the compliance loop builds on top of them).

### 2026-07-11 — Builder applied AMENDMENT-008 inbox (BUILD_PLAN v1.7, charter refs → v3.5)

**STRUCTURE** — Builder processed inbox MANIFEST-2026-07-11-amendment-008. Filed AMENDMENT-008 to `docs/decisions/` (already present from architect). Applied M10 addendum to BUILD_PLAN.md (10 tasks T10.1–T10.10 + checkpoint, review-w8). Updated BUILD_PLAN header v1.6→v1.7, charter reference v3.4→v3.5. Updated CONTEXT.md and PROGRESS.md charter references to v3.5. Moved manifest to `docs/inbox/processed/`. No code changes — this is the plan-filing step; M10 implementation starts next.

### 2026-07-11 — VO extraction decodes structured reel posts before parsing dialogue

**FIX** — `assets.posts` is stored as a JSON array. VO generation previously ran its line-oriented regex against the encoded JSON string, where newlines were escaped; the first `VO:` match therefore swallowed later frame labels, visual directions, overlays, and dialogue into one 323-word TTS request. The extractor now decodes the array and joins its entries before selecting spoken lines. Real asset #2 now yields the five intended VO lines (198 words) with no frame or visual directions. This fixes extraction only; script-to-timeline feasibility remains governed by proposed `DIVERGENCE-012`.

### 2026-07-10 — Generic VO fallback no longer imposes a tenant dialect

**FIX** — Removed the tenant-specific default TTS style from `src/vo_generator.py`. Voice style remains tenant configuration in `config/models.yaml`; if an older or incomplete configuration omits it, the Gemini TTS instruction is neutral (`Say: …`) rather than injecting a business dialect. Regression coverage proves the generic source remains tenant-free and that the neutral prompt is well-formed.

### 2026-07-10 — Audio bed fix: plan-driven audio mixing (AUDIO-1)

**FIX** — Removed the post-concat audio bed heuristic (assembly.py lines 454–518) that looped the first video clip's ambient audio to fill output duration. This was a charter violation — judgment in code (the code decided to loop audio without the LLM's direction). Replaced with `_apply_audio_strategy()` which reads `plan["audio"]` and executes the LLM's strategy: silent (original_audio=false, no music → strip + replace with silence), original (preserve concat audio, loudnorm), music (resolve stock ref, mix at specified volume), VO (duck under VO, deferred if no file). Provenance logs the audio strategy decision.

### 2026-07-10 — Edit plan prompt v1.2: audio strategy guidance (AUDIO-2)

**LOGIC** — Added Audio Strategy section to `prompts/assembly/edit_plan_v1.md` (v1.1 → v1.2). The LLM is now explicitly told: no VO + no music → original_audio: false (silent is better than nonsense); video clip ambient sound meaningful → original_audio: true; music available → use stock ref with volume 0.2–0.4; renderer will NOT invent audio. This prevents the edit plan from leaving audio ambiguous, which previously caused the renderer to apply its own (broken) heuristic.

### 2026-07-10 — Asset review layer: mechanical checks (ASSET-REVIEW-1)

**STRUCTURE** — New `src/asset_review.py` module with `AssetReviewer` class. Mechanical post-render checks run after every render: file size, duration, video/audio stream presence, resolution, SAR via ffprobe. Duration mismatch > 2s flagged, missing audio when expected flagged, unexpected audio when plan says silent flagged, resolution mismatch with canvas flagged. Results saved to new `asset_reviews` table + provenance. Advisory only — does not block the operator. Wired into `render_final_cut` route and `render-status` endpoint.

### 2026-07-10 — Asset review layer: vision inspection (ASSET-REVIEW-2)

**STRUCTURE** — Vision-based visual inspection: keyframes extracted at 20/40/60/80% of duration + first frame via ffmpeg, encoded as base64, sent to vision-capable LLM (config-driven: `asset_review.vision_model` in models.yaml). New prompt `prompts/assembly/asset_review_v1.md` (v1.0) checks content alignment, caption presence, visual quality, style conformance. Graceful degradation: skips if disabled, no API key, or no model configured. Results saved to `asset_reviews` + provenance with model + prompt version.

### 2026-07-10 — Asset review config block (ASSET-REVIEW-2)

**TECH** — New `asset_review` block in `config/models.yaml`: `vision_model` (default `google/gemini-3.1-flash`), `vision_provider`, `vision_api_key_env`, `max_keyframes` (5), `enabled` (true). Config-driven — a second business could use a different vision model with zero code changes.

### 2026-07-10 — Asset review layer: audio inspection (ASSET-REVIEW-3)

**STRUCTURE** — Audio inspection via faster-whisper transcription. Extracts audio from rendered video, transcribes, checks for looping (same 5+ word phrase appearing 3+ times → flagged), unexpected audio (plan says no audio but transcript has speech → flagged), no speech when non-silent (catches ambient/looping → flagged). Graceful degradation if whisper not installed. Results saved to `asset_reviews` + provenance.

### 2026-07-10 — Asset review layer: content alignment (ASSET-REVIEW-4)

**STRUCTURE** — Content alignment aggregation: combines mechanical + visual + audio review results into a single advisory verdict. `ready_for_operator` (no issues) / `needs_operator_decision` (medium issues) / `needs_rerender` (high-severity issues like looping). Pure aggregation, no LLM call. Saved to `asset_reviews` + provenance.

### 2026-07-10 — Asset review layer: UI integration (ASSET-REVIEW-5)

**STRUCTURE** — AI Review Summary panel in `assets.html` below the video player. Fetches from `/api/assets/<id>/reviews` on page load. Each check (mechanical, visual, audio, alignment) shown with ✓/⚠/✗ icon. Overall verdict badge: Passed / Ready for review / Issues found / Needs re-render. Expandable "View detailed review" shows full JSON findings. Advisory only — does not block operator from approving/fixing/killing. New `/api/assets/<id>/reviews` endpoint.

### 2026-07-10 — Asset review layer: image review (ASSET-REVIEW-6)

**STRUCTURE** — Extended the AI review pattern to standalone generated images. `run_image_review()` does mechanical checks (file exists, size > 10KB) + a single vision LLM call comparing the image to the prompt that generated it. Lighter-weight than video review. Mismatch flagged with original prompt + what the AI sees. Results saved to `asset_reviews` + provenance.

### 2026-07-10 — Audio bed mixing for reels with image segments

**FIX** — Reels that mix video clips with image segments had dead silence during the image portions (image segments use `anullsrc` for concat compatibility). Added a post-concat audio pass: extracts the first video source's audio, loops it to full output duration, mixes it under the concat audio at reduced volume with loudnorm. This gives reels ambient audio throughout instead of 3 seconds of sound followed by 15 seconds of silence. Falls back to plain loudnorm if the bed extraction fails.

### 2026-07-10 — Edit plan source validator + orphaned media cleanup

**FIX** — Post-LLM source validation for edit plans: the edit plan prompt explicitly says "ONLY use ingredient ids from the inventory" but the LLM sometimes hallucinates `stock:` IDs anyway. Added a mechanical referential integrity guard that checks every segment source against the ingredient inventory after the LLM returns. Invalid sources → 422 response, plan not saved, job marked failed. This prevents the failure mode where the plan is saved with fake stock references and only fails at render time. 4 tests added (`TestEditPlanSourceValidation`).

**FIX** — Orphaned media cleanup: a previous pipeline archive/reset wiped `asset_media` records but left image files on disk. Asset 2 had 13 orphaned PNGs from a previous content topic ("The Ownership Gap") while the current asset is about biscuit tins. Cleaned up orphaned files and regenerated images for the current asset's 5 image prompts. Generated a valid edit plan using only real ingredients (1 Veo video + 5 images) and rendered a working 18s final cut.

### 2026-07-10 — Video generator fallback + Veo API bug fixes

**FIX** — Video generator fallback: when the requested video generator's API key is not set, the system now automatically falls back to the next available generator from `config/models.yaml`. This applies to all three video generation paths: the media plan executor (`ai_video:<name>`), the direct `/generate-video` endpoint, and the `/generate-clip` endpoint. The operator's instruction: "if asking for xai then use next best system — system should always work that way."

**FIX** — Veo `durationSeconds` bug: Google Veo 3.1 Fast only accepts even-numbered durations (4, 6, 8). Odd values (5, 7) return 400 "out of bound" despite docs saying 4-8. Added `_veo_clamp_duration()` to clamp to nearest valid value.

**FIX** — Veo download URL extraction: response field is `video.uri`, not `video.gcsUri` or `video.url`. Added `uri` to the key extraction chain. Without this, Veo jobs completed successfully but the system reported "failed" because it couldn't find the download URL.

**FIX** — Veo download URL authentication: URLs from Veo contain `?alt=media` — the API key needs to be appended with `&key=`, not `?key=`. Fixed the conditional to handle both cases.

**FIX** — Veo error logging: API errors now include the response body for debugging instead of just the HTTP status code.

**TECH** — `_find_available_video_generator()` and `_resolve_ai_video_generator_with_fallback()` added to `src/app.py`. 10 new tests in `tests/test_video_fallback.py`. 808 tests passing.

## 2026-07-10 — VH-1 through VH-6: Video generation → assembly handoff correction

**[FIX] VH-1 (P0): generate-clip route no longer poisons asset_media.** The route read `poll_result.get("path")` but `check_video_job()` returns `download_url`, not `path` — so `video_path` was always `""`. It then called `_record_media()` with that empty path, inserting a bogus `asset_media` row. Fixed: route now reads `download_url`, calls `download_video()` which downloads the file AND records it in `asset_media`, returns `{file_path, media_id}` so the caller can construct `ingredient_id: "generated:<media_id>"`.
**Rationale:** Both video generation routes were broken — no AI-generated video could ever reach the assembler. This was the first of 5 P0 bugs identified by the architect audit.

**[FIX] VH-2 (P0): generate-media route no longer submits and walks away.** After `submit_video()`, both the direct AI video path and the stock-fallback path set `status="submitted"` and returned. No polling, no download, no `_record_media` — the job floated indefinitely. Fixed: new `_poll_download_register_video()` helper polls `check_video_job()` (5s intervals, max 60 polls = 5min timeout), calls `download_video()` on completion, returns `ingredient_id`. On timeout, returns `status="processing"` with `external_job_id` so the operator knows to check back.
**Rationale:** The operator saw "submitted" and nothing ever came back. No AI video was ever registered as an assembler ingredient (asset_media had 0 rows).

**[FIX] VH-3 (P0): Google/Veo — 5 independent bugs fixed.** (1) Aspect ratio sent `9x16` instead of `9:16` — removed `.replace(":", "x")`. (2) Response parsing missed a nesting level — now navigates `response.generateVideoResponse.generatedSamples` with shallow fallback. (3) Download URL omitted API key — `download_video()` now appends `?key={api_key}` for Google URLs + rejects files <1KB (error blobs are ~100 bytes). (4) API key env var only checked `GOOGLE_API_KEY` — now checks `GEMINI_API_KEY` first, then `GOOGLE_API_KEY`. (5) Duration hardcoded — fixed in VH-5.
**Rationale:** Each bug independently prevented Google/Veo from working. The system is config-driven — any business could configure either provider.

**[FIX] VH-4 (P1): 0-byte render files cleaned up + output size validation.** Three 0-byte `final_*.mp4` files existed in `data/media/3/` — silent render failures that weren't cleaned up. Deleted them. Render route now checks output file size after FFmpeg: if 0 bytes, deletes the file, marks job as failed, surfaces the failure to the operator. No more false greens.
**Rationale:** 0-byte files could be served as "rendered outputs" — the operator would see a broken video player with no error message.

**[FIX] VH-5 (P1): Duration read from plan_item, not hardcoded to 5.** Both AI video paths hardcoded `duration=5`, silently overriding the LLM's creative direction. The media plan LLM could write "Cinematic 15-second clip..." but the API always sent 5. Fixed: `plan_item.get("duration", 5)`.
**Rationale:** Charter concern — this is judgment in code. The LLM decided the duration; code overrides it. Per charter §"No judgment in code," the LLM's plan should be honored.

**[STRUCTURE] download_video() return type changed from str to dict.** Was returning only the file path string; now returns `{file_path, media_id}` so callers can construct `ingredient_id: "generated:<media_id>"` without calling `_record_media` separately (which would double-register).
**Rationale:** The correction required `media_id` to be returned alongside the file path. No external callers existed (generate-clip never used it, generate-media never used it), so the signature change is safe.

**[OPS] _summarize_media_generation_results updated to track processing_count.** New status "processing" (timeout jobs still running) added to the summary dict and the error check at the end of generate-media.
**Rationale:** The summary is the honest UI messaging layer — "processing" means a job is still running, not ready to render.

## 2026-07-07 — UI: Fix 7 operator-identified defects from UIIX review

**[UI] Seven defects caught by operator deep-walk of the redesigned UI.**
1. Numbers dissonance: pipeline strip labels say "total in stage", gate stats say "awaiting your X" — disambiguates total-in-pipeline vs decisions-pending
2. Contradictory state: verified live app correct (assemble page distinguishes "awaiting preview" from "rendering")
3. Red color leak: stale sources → yellow (#8A6D20), badge-stalled → yellow, "new only" filter → accent (not danger red)
4. Orange button leak: all navigation buttons (Review/Preview/Open-draft) → btn-small neutral; orange reserved for gate decisions only
5. Capture-required Approve: cards with capture_tasks show "Upload capture first" instead of live Approve (prevents auto-chain stall)
6. Gate 3 granularity: footer banners state "per-set · set ships when all are ready"
7. Constitutional footers: added to assemble page and published page
**Rationale:** Operator caught color semantics, count dissonance, and missing guardrails that the mockup hardcoded but the templates needed to enforce dynamically.

**[UI] Redesigned all 13 page templates to match the UIIX Google Drive mockup design system.**
- 5-group topbar (Home/Pipeline/Knowledge/Results/Setup) with badge counts + business switcher
- Page title blocks with serif headings + accent subtitles
- Tab bar for sub-navigation (pipeline stages, knowledge tabs, setup tabs)
- Gate stat mini-cards, pipeline strip, decision queue with gate badges
- Source type chips (rss/material/scraped/archival), module grid, coverage dots
- Expanded card pattern for Gate detail, two-column activity+health layout
- 550+ lines of new CSS component classes matching mockup design tokens
- Enriched index() route with gate_counts, pipeline_counts, decision_queue, system_health
**Rationale:** Operator provided 13 HTML mockup files defining the complete UI/UX. All templates now conform to this design system.

### 2026-07-07 FIX — Assembler cannot render from unrelated capture uploads

**FIX** — Asset #1 rendered a wrong water clip for a Barbados Landship reel because final assembly built its edit-plan ingredient inventory from all business-wide `capture_upload` materials. The LLM selected `upload:248` (`veo-water-clip.mp4`) even though that material was not linked to asset #1's idea card and did not match the required Landship/Bridgetown capture direction.

**Rationale:** Capture uploads are card-specific production ingredients, not a global B-roll library. Global substitution causes ID/direction mismatches and can send unrelated media into public review.

**Change:** Edit-plan generation now only exposes asset-scoped generated media and capture uploads explicitly linked to the source idea card. If required captures are still missing, `/api/assets/<id>/edit-plan` returns `status: missing_media` / HTTP 409 instead of asking the LLM to improvise. Stock clips found through missing-media generation are registered as asset-scoped `asset_media` rows so later edit plans consume them as `generated:<media_id>`, not global stock history. Reels without a final cut now show a disabled "Approve locked until final cut exists" control instead of an active approval button.

**OPS:** The existing wrong asset #1 final cut was archived from `data/media/1/final_1.mp4` and its edit plan marked failed after a DB backup. The page now shows no final cut and the edit-plan API reports 2 missing required visuals.

### 2026-07-07 FIX — `reviewing` cards no longer enter the Writer draft queue

**FIX** — A card in `card_state='reviewing'` could appear on the Writer draft/review surface as if it were actionable. That contradicted the state rule: only cards ready to draft (`approved` or `capture_fulfilled`) should enter the draft queue; `reviewing` is an in-flight AI review state and should not be presented as operator work.

**Rationale:** Showing `reviewing` beside actionable draft states creates state dissonance and invites the operator to click into a card while the writer/review loop is still active.

**Change:** Removed `reviewing` from `writer_eligible_states` and updated regression coverage so `/create` excludes reviewing cards while still including `approved` and `capture_fulfilled` cards. Also tightened `/assemble` so `approved` alone does not make an unshipped draft appear in Assembler; a card needs a shipped draft or asset-stage state.

### 2026-07-07 FIX — Missing-media generation no longer says "Ready to render" after zero media

**FIX** — The Assembler missing-capture flow could report `0 media items generated, 2 failed. Ready to render video.` That message was false in two layers:

1. **Frontend status bug:** `assets.html` appended `. Ready to render video.` for every `status: ok` response, even when `okCount === 0` and every plan item failed.
2. **Backend contract bug:** `/api/assets/<id>/generate-media` returned `status: ok` even when every media-plan item failed/skipped and no renderable `asset_media` file existed.
3. **Submitted ≠ renderable:** The frontend counted `status: "submitted"` video jobs as generated media, but an async provider job is not a local renderable ingredient yet.
4. **Named video fallback bug:** Stock fallback values like `ai_video:veo` were ignored; the fallback branch called `submit_video()` with no model/provider, silently falling back to legacy default `xai` and failing when `XAI_API_KEY` was not present, even though `GOOGLE_API_KEY` was configured.

**Fix:**
- Added `_resolve_ai_video_generator()` so `ai_video:veo` resolves to the configured Google/Veo model/provider and unknown named generators fail loudly instead of silently defaulting.
- Added `_summarize_media_generation_results()` and `ready_to_render` response flag. Only `status: "ok"` counts as renderable media; `submitted` is reported separately.
- `/generate-media` now returns `status: error` / HTTP 500 when zero renderable media was created and nothing was submitted.
- Assembler UI now says e.g. `0 renderable media items generated, 2 failed. Not ready to render yet.` and only says `Ready to render video` when `ready_to_render === true`.
- Stock generator inventory now tells the LLM whether stock APIs are actually available or missing keys.

### 2026-07-07 FIX — 'reviewing' card state caused UI confusion + premature Gate 2 buttons

**FIX** — The AI review loop sets `card_state = "reviewing"` during its alignment-check rounds, but this state was missing from two critical places in the Writer UI:

1. `_writer_display_state()` (app.py:7456) had no case for `"reviewing"` — it fell through to `return cs`, returning the raw string `"reviewing"`. This produced a broken badge (no CSS class, no label, no spinner) and the auto-refresh JS didn't trigger (it only watches `data-state="writing"`/`"assembling"`).

2. `writer_eligible_states` (app.py:7401) excluded `"reviewing"`, so cards in this state were filtered out of the Writer page entirely — the card vanished while the AI review loop ran.

3. The draft page (draft.html) showed Gate 2 buttons (Send to Assembler, Revise, Kill, Regenerate) whenever `draft_state != 'shipped'` — but during the AI review loop, `draft_state` is still `"drafting"`, so those buttons appeared prematurely. Clicking "Generate draft" or "Regenerate" hit the API guard at app.py:4975, which rejected with "Card state is 'reviewing' — must be approved or capture_fulfilled to draft".

**Fix:**
- `reviewing` → mapped to `"writing"` display state (spinner + "Writer working" label + auto-refresh)
- `reviewing` added to `writer_eligible_states` so the card stays visible
- draft.html Gate 2 section now only renders when `draft_state in ('draft_ready', 'revised')` — during `drafting`, shows "Writer is working" message with spinner + auto-refresh
- Per-platform Edit buttons, visual preview Generate button, and self-audit Apply/Dismiss buttons all gated to `draft_ready`/`revised` states only
- Schema comment in pipeline.py updated to document `reviewing` in the state list

### 2026-07-07 FIX — ffmpeg concat "Invalid argument" on mismatched SAR

**FIX** — The ffmpeg concat filter crashed with `Error while filtering: Invalid argument` / `Conversion failed!` when concatenating image segments that had different native aspect ratios. Root cause: `scale=...:force_original_aspect_ratio=decrease,pad=...` produces different SAR (Sample Aspect Ratio) values depending on the source image's dimensions (e.g. SAR 0:1 for one image, SAR 2880:2881 for another). The concat filter requires all inputs to have matching SAR.

**Fix:** Added `setsar=1` to the `-vf` chain in all four segment preparation branches (image, audio-only, video+audio, video-only). This normalises SAR to 1:1 on every segment before concat, guaranteeing matching parameters across all inputs.

**Rationale:** Operator hit this on asset 3 — a Reel with 8 image segments (3 generated images reused). All 8 individual segment trims succeeded, but the concat stage failed because the images had different aspect ratios producing different SARs. The error message ("Invalid argument") gave no clue about SAR mismatch — required reading the full ffmpeg stderr to find `Input link in0:v0 parameters (SAR 0:1) do not match (SAR 2880:2881)`.

**Regression test:** `test_render_concat_mismatched_sar_images` — creates wide (1280x720) and tall (720x1280) images, concatenates 4 segments, verifies output exists with SAR 1:1. Tests: 60 passing (was 59).

### 2026-07-07 FIX — Duplicate video player on Assembler reel page

**FIX (UI)** — The reel asset card on `/create/assets/<draft_id>` rendered the final cut video **twice**: once in the media-frame (with "FINAL CUT" badge) and again in the "Final cut rendered" step section below. The operator saw a "repeat video" on refresh.

**Fix:** Removed the redundant `<video>` element from the final-cut-section. The video is only shown once in the media-frame. The collapsible edit plan remains below it.

---

### 2026-07-06 FIX — variant_type mislabeling hid carousel images on Assembler page

**What:** The Assembler page (`/create/assets/1`) showed "Text-only format — ready for review" for an Instagram carousel that had 8 active image prompts, hiding the slides and the "Generate images" button. The X thread variant rendered as a newsletter mock instead of numbered tweets.

**Root cause:** The Writer prompt (`generate_v3.md` v3.0) instructed the LLM to set `variant_type` from the Format Guide entry's single `Variant type` field. For cross-platform formats like "Newsletter Section" (X→thread, Instagram→carousel), the Format Guide has one `Variant type: newsletter` field — so both platform variants got `variant_type="newsletter_section"`, the format name, not the structural type. The template's `is_text_only = is_poll or is_newsletter` then classified both as text-only.

**Fix at 3 layers:**
1. **DB** — corrected existing assets: asset 1 (X) → `variant_type="thread"`, asset 2 (Instagram) → `variant_type="carousel"`, and updated the draft's `platform_content` to match.
2. **Prompt** — `generate_v3.md` v3.0→v3.1: `variant_type` is now described as the per-platform structural type matching the posts array (thread for multi-post X, carousel for multi-slide Instagram), not a copy of the Format Guide field. The JSON schema description and rules section updated to match.
3. **Template** — `assets.html` safety net: (a) `is_text_only` now checks for active image prompts — a newsletter with image prompts is NOT text-only. (b) Auto-detect block: when `variant_type` is the format name (not thread/carousel/reel/poll) and there are 2+ posts, the template infers thread or carousel from the content description + platform. This prevents future mislabeled variants from hiding images.

**Rationale:** The Format Guide's single `Variant type` field can't represent per-platform structural variants for cross-platform formats. The Writer LLM sees the platform it's writing for and knows whether it produced a thread or a carousel — it should set `variant_type` accordingly. The template safety net catches any future mislabeling so images are never hidden from the operator.

---

### 2026-07-04 LOGIC/FIX — AI tells + voice deepening correction applied

**What:** Applied `docs/reviews/CORRECTION-ai-tells-and-voice-deepening-v1.md` after operator challenged the system to avoid AI writing at the thinking stage, not by post-hoc humanizing. Added `prompts/shared/ai_tells_v1.md`, a sourced 53-tell catalog with HIGH/MEDIUM/LOW confidence levels (including the operator-called-out “it’s not X, it’s Y” negative-parallelism tell). `draft/generate_v3.md` now loads the catalog and performs a specific 6-category self-audit. `alignment_check_v1.md` v1.1 now performs a second pass for surviving HIGH-confidence tells via `ai_tell_survived` issues.

**Voice-first ideation:** `ideas/generate_v1.md` v1.4 now loads Voice Profile context before source crossing and instructs ideas to be born in the person’s mental shape, not mechanically generated then humanized.

**Cognitive voice:** `voice_profile/analyze_v2.md` v2.1 and `playbooks/voice-profile-builder.md` v1.1 now extract cognitive patterns: mental models, obsessions, contrarian takes, story instincts, and worldview frame, each with evidence. These feed idea generation, not just draft style.

**T9.5 fixes:** Fixed the AI review loop’s self-audit no-op: flags with concrete `fix_applied` text now change real `platform_content` before Gate 2, and flags without concrete revised text remain active. AI-review revision rounds now load the same module context as first draft generation instead of placeholders like “same as previous.” Added shared-file support in `context_assembly.py` so `prompts/views.yaml` can load `prompts/shared/ai_tells_v1.md` with provenance.

**Rationale:** Humanness must be built in, not sprayed on. The Writer and reviewer should auto-handle high-confidence AI tells before the operator sees the draft, while medium/low-confidence tells remain context-dependent. Voice must shape ideation itself, not only the final wording.

**Tests:** 761 passing. Added regression coverage for shared prompt-file context loading and real self-audit fix application.

---

### 2026-07-04 UX/FIX — Operator end-to-end UI review fixes for Writer/Assembler

**What:** Fixed 15 operator-reported issues from the full UI walkthrough. Critical display fixes now render `platform_content` everywhere: single-post Reel scripts show the full beat-by-beat script on Draft review, Asset review reads approved scripts from `platform_content` instead of legacy `draft_text`, and `story_series` assets show every frame/image pair. Researcher Generate now has visible loading state, Writer/Assembler list titles use 3-line clamp instead of one-line manual ellipses, shipped drafts hide mutating self-audit controls, AI review notes no longer imply a replacement when no text changed, Reel video generation starts as step 1, asset cards show script excerpts instead of duplicating summary text, capture reminders show on Asset review, Gate 3 keeps the friendly "Needs work" label with `fix` mapping documented in the button title, and asset cards are centered/wider on laptop.

**xAI video:** Media config now supports `video_provider: xai`, xAI endpoint shape (`/v1/videos/generations`), `request_id` job IDs, xAI polling endpoint, and clear `XAI_API_KEY` errors. Attempted to copy `XAI_API_KEY` from the default Hermes profile env (`/home/daimon/.hermes/.env`) into `/home/daimon/.viralfactory.env`, but the default env does not currently contain `XAI_API_KEY`; no secret was fabricated or written.

**Rationale:** The walkthrough exposed stale template assumptions from the old `draft_text` schema and confusing controls on the redesigned Writer/Assembler boundary. These are operator-facing defects: the data was correct in SQLite, but the UI hid or duplicated the wrong fields.

**Tests:** 758 passing. Added `tests/test_ui_review_display_fixes.py` (10 regression tests) and xAI media adapter tests. Full `pytest -q` passed; worker cleanup printed a non-fatal `no such table: materials` message after completion.

---

### 2026-07-04 TECH — M9 implemented: Writer per-platform + Assembler media-only + AI review loop

**T9.1:** Removed `_determine_variant_type` keyword heuristic and `_resolve_format_platforms` regex parser from `produce_chain.py` and `app.py` — both were Business Rule #2 violations. Replaced with `_get_platforms_from_format_entry` and `_get_variant_type_from_format_entry` — mechanical parsers of the Format Guide entry's structured `- **Platforms:**` and `- **Variant type:**` fields. No judgment in code.

**T9.2:** Added `variant_type` field to `FORMAT_GUIDE_SCHEMA` (required), `format_guide_to_markdown` converter, `prompts/format_guide/analyze_v2.md` (v2.0 → v2.1), and all 8 entries in the production `modules/stackpenni/format-guide.md`. The Writer and Assembler now read variant_type from the module, not from code heuristics.

**T9.3:** DRAFT_SCHEMA restructured — `draft_text` replaced by `platform_content` array (platform, variant_type, content, posts, image_prompts per entry). New prompt `prompts/draft/generate_v3.md` instructs Writer to produce complete per-platform text for every platform the treatment specifies. Drafts table gains `platform_content`, `review_history`, `review_converged` columns. `draft_text` kept as backward-compat summary field.

**T9.4:** Assembler rewritten to media-only. `_step_fanout` in `produce_chain.py` and `assets_fan_out` route in `app.py` both read `platform_content` from the approved draft and create assets directly — zero LLM text calls. `fan_out_v2.md` and `structure_v1.md` files kept for provenance history but no longer called.

**T9.5:** AI review loop added to `run_writer_chain`. New `prompts/draft/alignment_check_v1.md` prompt + `ALIGNMENT_CHECK_SCHEMA` (`{aligned, issues, recommendations}`). Loop: (1) self-audit auto-fix, (2) alignment check, (3) revise if issues, max 3 rounds. Card state: `writing → reviewing → draft_ready | writer_failed`. Review history + convergence status saved to draft and shown in `draft.html` with transparency — operator sees what the AI caught and changed.

**T9.6:** All tests updated. 746 passed (726 baseline + 20 new tests). Tests verify: zero LLM text calls in Assembler path, `platform_content` schema validation, alignment check schema, max-3-rounds behavior, non-convergence flagging.

---

### 2026-07-04 STRUCTURE — DIVERGENCE-010 ratified via AMENDMENT-007 (Charter v3.3 → v3.4)

**What:** DIVERGENCE-010 (Writer/Assembler boundary redesign, originally filed as DIVERGENCE-009 but renamed due to numbering collision with the webhook DIVERGENCE-009) — architect APPROVED all 5 operator-raised design changes:

1. **Format + platforms locked from treatment** — removes `_determine_variant_type` keyword heuristic and `_resolve_format_platforms` regex parser (both Business Rule #2 violations). Format and platform set come from the treatment + Format Guide entry metadata.
2. **Writer produces complete per-platform text** — DRAFT_SCHEMA changes from single `draft_text` to `platform_content` array. The Writer writes all platform variants in one pass. The format and platforms come from the locked treatment.
3. **Source Bank not loaded into draft** — confirmed no redundancy exists. Grounding sources are separate from the 7 modules. No change needed.
4. **AI review loop before Gate 2** — self-audit auto-fix + second-AI alignment check, max 3 rounds. The human is still the final gate. Self-audit flags + fixes shown for transparency.
5. **Assembler is media-only** — zero LLM text calls. `fan_out_v2.md` and `structure_v1.md` retired from Assembler path. The Assembler reads `platform_content` from the approved draft and produces media + assembles.

**Rationale:** The operator's mental model is simpler and more coherent: Researcher finds ideas + assigns treatment, Writer fully writes per-platform content with AI QA, Assembler only generates media + assembles. Eliminates fan-out LLM calls, format re-derivation, keyword heuristics, and unreviewed text reaching the human. The AI review loop catches issues before the human sees the draft, but does not replace the human gate.

**Status:** APPROVED. AMENDMENT-007 filed. Charter v3.3 → v3.4. BUILD_PLAN v1.5 → v1.6 (M9 tasks T9.1-T9.6 added). CONTEXT.md updated (core loop diagram, idea card definition, business rules 13-15). All CHARTER-v3.3 references updated to CHARTER-v3.4. Builder to implement M9 tasks.

**STRUCTURE** — AMENDMENT-007 ratified; DIVERGENCE-010 approved; charter version bump v3.3 → v3.4; BUILD_PLAN M9 tasks added; `_determine_variant_type` and `_resolve_format_platforms` confirmed as charter violations to be removed.

---

### 2026-07-04 STRUCTURE — DIVERGENCE-010 filed (originally as DIVERGENCE-009): Writer/Assembler boundary redesign

**What:** Operator raised five connected design issues with the Writer/Assembler pipeline:
1. Assembler re-decides format/platforms already approved in the treatment (charter violation — keyword heuristic in `_determine_variant_type`)
2. Writer should produce complete per-platform text in one pass, not one master draft + Assembler fan-out
3. Source Bank is NOT loaded into the draft prompt (confirmed — no redundancy exists; grounding sources are separate from the 7 modules loaded for drafting)
4. AI review loop (self-audit fix + second-AI alignment check, max 3 rounds) should run before human Gate 2 review
5. Assembler should only gather/make media and stitch — no text LLM calls

**Rationale:** The operator's mental model is simpler and more coherent: Researcher finds ideas + assigns treatment, Writer fully writes per-platform content with AI QA, Assembler only generates media + assembles. Eliminates fan-out LLM calls, format re-derivation, and unreviewed text reaching the human.

**Status:** DIVERGENCE-009 filed for architect decision. The `_determine_variant_type` keyword heuristic is a confirmed Business Rule #2 violation (fixable regardless of architect decision on the structural changes).

**TECH** — DIVERGENCE-009 filed; charter violation identified in `_determine_variant_type` (keyword heuristic violates "no judgment in code").

---

### 2026-07-04 UX — six operator-reported workflow issues fixed

**What:**
1. **UX-1 (UI):** Nav menu now shows real-time pipeline counts via Flask context processor. Shared `_nav.html` include replaces hardcoded nav in all 33 templates. Researcher shows new count, Writer shows ready-for-review count, Assembler shows asset-ready count.
2. **UX-2 (FIX):** Generate ideas button was passing `null` to `busyAction` — no button disable, no visible status. Fixed: button gets `id="genBtn"`, passed to `busyAction`, status span shown explicitly before call.
3. **UX-3 (LOGIC):** Writer page was showing all cards including `new`-state series children. Fixed: Writer only shows cards in approved+ states (`approved`, `writing`, `draft_ready`, `drafted`, `shipped`, `assembling`, `asset_ready`, `awaiting_capture`, `capture_fulfilled`, failure states). New/killed/parked cards stay in Researcher.
4. **UX-4 (FIX):** Writer/Assembler spinners never stopped because pages are server-rendered with no auto-refresh. Added JS auto-refresh (10s poll) when any card is in `writing` or `assembling` state.
5. **UX-5 (UI):** Manual "Generate per-platform variants" button was redundant — the assembler chain already auto-fires on ship. Replaced with spinner + "Assembler working" message + auto-refresh.
6. **UX-6 (UI):** Video pipeline had 3 buttons (plan, render, final render). Collapsed to one "Generate video" button that chains plan→render automatically. Edit plan shown in collapsible `<details>` after render completes.

**Rationale:** Operator reported six concrete UX issues during workflow testing. Each was a real friction point: no feedback on clicks, wrong cards in wrong sections, spinners that never stopped, unnecessary manual steps for automated processes. All fixes reduce operator friction and align the UI with the actual background processing model.

**Tests:** 726 passing. Updated `test_t3_5_to_12_pipeline.py` (fan-out button assertion → spinner assertion), `test_template_css_validate.py` (exempt `_` prefixed include fragments).

---

### 2026-07-04 FIX — operator materials removed from source bank; seed sources persisted

**What:**
1. **FIX-1 (STRUCTURE):** Removed the `sources` table insertion from `materials.py:_store()`. Operator materials (voice notes, uploads, WhatsApp exports) now only enter the `materials` table — they no longer create `operator_material` rows in the `sources` table. Also removed the `sources` table creation from `MaterialsIntake._init_db()` (that table belongs to `PipelineStore`). Updated `test_t8_3_source_bank.py`: `TestMaterialsRegisterSources` → `TestMaterialsDoNotRegisterSources` — all 4 tests now assert materials do NOT create source rows.
2. **FIX-2 (STRUCTURE):** Added seed source persistence to the `store_sources` endpoint in `app.py`. When the Sources Engine gate is approved, each seed source from `collected_inputs.seed_sources` is written to the `sources` table as `source_type='seed_reference'`, `origin='operator'`, `status='active'`. Deduped on content_hash (name+url). New test file `test_fix2_seed_source_persistence.py` (4 tests): approved gate persists seeds, parked gate does not, dedup on re-approve, no-error on empty seeds.
3. **DB cleanup:** Deleted 2 existing `operator_material` rows from live DB (IDs 1, 2 — a draft review HTML page and a manifest file). Backfilled 50 seed sources from the Obsidian Strongest Sources Export (material ID 88) as `seed_reference` rows. Live DB now has 61 sources: 50 seed_reference + 10 rss_item + 1 manual.

**Rationale:** Operator materials feed the playbooks → modules (Voice Profile, Story Frameworks, etc.). The Source Bank is for external content the AI scouts and crosses with modules for ideation. Mixing operator materials into the source bank double-counts the operator's own material as external inspiration. The 50 seed sources were analyzed to produce the Source Criteria module but the individual seeds were never persisted — they were consumed and discarded, leaving the bank nearly empty (only 10 RSS items from 1 feed). Now seeds are persisted on gate approval and the backfill restores them for the live tenant.

**Tests:** 726 passing (was 722 — +4 new seed persistence tests, old materials-register-sources tests rewritten).

---

### 2026-07-04 FIX — ffmpeg concat crash + fan-out duplicate platform assets

**What:** Three fixes for the Assembler page:

1. **ffmpeg concat "matches no streams" crash** (assembly.py): The edit plan LLM generated cumulative timeline timestamps (0→2, 2→4.5, 4.5→7…) for segment in/out, but the renderer uses these as seek positions *within each source file*. When segment 11 asked for in=27, out=30 on material_70 (a 3-second audio-only file), ffmpeg produced a file with no streams, crashing the concat filter. Fix: pre-flight validation clamps in/out against the source file's actual probed duration before trimming. Non-fatal warnings logged to provenance.

2. **Edit plan prompt ambiguity** (prompts/assembly/edit_plan_v1.md): Added standing order #7 explicitly stating that "in" and "out" are seek positions within the source file, not cumulative timeline timestamps. The LLM was confusing "where in the final video this segment appears" with "where in the source file to seek."

3. **Duplicate platform assets on re-click** (app.py fan-out endpoint): Clicking "Generate per-platform variants" twice created duplicate Instagram reel cards. Fix: idempotency guard checks `list_assets(draft_id)` and skips platforms that already have non-killed assets. Returns `already_exists` status with message when all platforms are covered. busy.js updated to treat `already_exists` as a reload-triggering success.

4. **Error message readability** (assembly.py): ffmpeg errors now extract only the actual error lines, not the full copyright banner. Previously the operator saw 500 chars of ffmpeg build flags instead of the actual failure reason.

**Rationale:** The operator hit both bugs on https://vf.glenbeu.com/create/assets/3 — the render failed with an unreadable ffmpeg banner, and the page showed two identical Instagram cards. The workflow requires too many manual steps (generate → plan → render) because the format is a Reel which needs the full assembly chain; that's by design for video formats, but the bugs made it worse.

**Tests:** +3 tests (TestAssemblyInOutValidation: 2, TestFanOutIdempotency: 1). 722 total, all green.

---

### 2026-07-04 OPS — DIVERGENCE-009 implemented: Architect↔Builder webhook notification loop (configured, OFF)

**What:** Implemented and configured (but set to OFF) the asymmetric webhook notification loop:
1. **Architect → Builder (webhook):** GitHub webhook on push events → `https://vf.glenbeu.com/p/viralfactory/webhooks/architect-pushed` → Hermes webhook adapter → builder profile wakes up, does git pull, checks inbox/reviews/decisions, applies corrections. Response delivered to Daimon's WhatsApp.
2. **Builder → Architect (cron, every 2h):** Cron job runs significance-filter script → if builder pushed significant changes (feat:/fix:/refactor:/src/*.py/divergences) → architect profile wakes up, reviews diff for charter compliance, writes findings. Response delivered to WhatsApp. Minor changes pile up.

**Current state: ALL OFF.** Three components disabled:
- Webhook route: `enabled: false` (rejects all incoming POSTs with 403)
- Cron job: paused (`hermes cron pause 5ada489bfb4c`)
- GitHub webhook: `active: false` (GitHub won't send events)

**Toggle scripts (one command to turn on/off):**
- `bash ~/.hermes/scripts/vf-webhooks-on.sh` — turns everything ON + restarts gateway
- `bash ~/.hermes/scripts/vf-webhooks-off.sh` — turns everything OFF + restarts gateway

**Infrastructure (all in place, ready to activate):**
- Traefik route: `vf.glenbeu.com/webhooks/` and `/p/` → port 8644 (no basic auth, HMAC-validated)
- GitHub webhook: created on Daimondan/ViralFactory (ID: 649343246, inactive)
- Hermes webhook platform: port 8644, two routes, multiplex_profiles=true
- Cron job: `vf-builder-review-trigger` (every 2h, paused, script filters for significance)
- WhatsApp delivery: both routes configured to deliver agent responses to Daimon's WhatsApp
- Scripts: `vf-webhooks-on.sh`, `vf-webhooks-off.sh`, `vf-builder-review-trigger.sh`

**Rationale:** OPS tag — eliminates manual relay between architect and builder. Asymmetric design prevents infinite loops. Config-driven. Toggle scripts make it trivial to turn on/off without editing config files manually.

---

### 2026-07-04 FIX — Architect corrections applied: jargon cleanup, relative timestamps, config-driven platform fallback, awaiting-capture deprecation, Postiz dead code removed, source review gate

**What:**

1. **P1-1: Jargon cleanup** — Raw developer-facing state strings (`asset_ready`, `assembling`, `writer_failed`, `assembly_failed`, `production_failed`, `awaiting_capture`) no longer appear as visible text in operator-facing templates. State-label mapping dicts added to `ideas.html`, `create.html`, `assemble.html`. The Ideas page "Awaiting" tab removed (awaiting-capture cards now show under "Approved" with a "Manage capture" button when capture tasks exist).

2. **P1-2: Relative timestamps** — `relative_time` Jinja filter registered in `create_app()`. Cards on Ideas (`created_at`), Writer (`state_changed_at`), and Assembler (`state_changed_at`) pages now show relative timestamps ("2 hours ago", "3 days ago") instead of raw ISO timestamps. `.time-ago` CSS class used for display.

3. **P2-1: Config-driven platform fallback** — `produce_chain._resolve_format_platforms` no longer falls back to hardcoded `["X", "Instagram"]` when the Format Guide entry is missing. Falls back to the business config's platform list (`config/business.yaml` → `business.platforms`). Charter-compliant — no business values in code.

4. **P2-2: Awaiting-capture deprecation** — Per AMENDMENT-006, `awaiting_capture` is deprecated as a blocking state. Removed separate "Awaiting" tab from Ideas page. Removed `awaiting` key from `state_map` in app.py. `awaiting_capture` state folded into the "Approved" tab. `pipeline.py` schema comment updated to note the deprecation. Capture tasks still display on cards as a non-blocking flag.

5. **P2-3: Postiz dead code removed** — `src/postiz_adapter.py` deleted (dead code — nothing imported it; system uses `buffer_adapter.py`). `cron_pull_metrics.py` updated to import and use `BufferAdapter` + `BufferError`. `buffer_adapter.py` docstring updated to note `postiz_post_id` column name is kept for backward compat with existing publish_log rows per DIVERGENCE-008. No `postiz:` config block in `config/models.yaml`.

6. **DIVERGENCE-007 Item 1: Source review gate** — RSS sources now enter the Source Bank with `status='new'` (not `active`). Only `status='active'` sources feed idea generation. Dedup check in `source_snapshot.py` now looks at any status (prevents re-adding reviewed/removed sources). Source Bank page (`/sources`) has "New" filter button with count, `st-new` CSS class for new badge, bulk actions bar ("Keep all new →" / "Remove all new") with new `/api/sources/bulk-status` endpoint. Operator materials still enter as `active` (intentionally created by the operator). Source neural network (Item 2) deferred.

**Why:** Architect deep review (CORRECTION-jargon-timestamps-cleanup-v1.0) found jargon leaking into operator UI, missing timestamps on pipeline pages, hardcoded platform fallback, dead awaiting-capture code, and dead Postiz code. DIVERGENCE-007 designed the source review gate (soft gate, not hard — new sources visible but don't feed ideation until reviewed). DIVERGENCE-008 ratified the Postiz→Buffer swap with conditions (delete dead code, update docs).

**Rationale:** The charter requires staleness to be always visible (async gate philosophy). Raw state strings in operator UI violate the "no jargon" expectation. Hardcoded platform fallbacks violate "no business values in code." Dead code that contradicts the live system is a defect. The source review gate is consistent with the charter's async-gate philosophy: no pressure, no deadlines, operator reviews when ready.

**Files:** `src/templates/ideas.html`, `src/templates/create.html`, `src/templates/assemble.html`, `src/templates/source_bank.html`, `src/app.py`, `src/produce_chain.py`, `src/pipeline.py`, `src/source_snapshot.py`, `src/buffer_adapter.py`, `cron_pull_metrics.py`, `tests/test_architect_corrections.py`, `tests/test_t8_3_source_bank.py`, `docs/CONTEXT.md`, `docs/PROGRESS.md`

**Type:** FIX (P1-1, P1-2, P2-1, P2-2, P2-3) + STRUCTURE (DIVERGENCE-007)

---

### 2026-07-04 STRATEGIC — Architect review: DIVERGENCE-006 ratified, DIVERGENCE-007 designed, DIVERGENCE-008 filed, corrections issued

**What:**
1. **DIVERGENCE-006 RATIFIED** — AMENDMENT-006 filed: Writer/Assembler pipeline split + four-role nav (Researcher/Writer/Assembler/Analyst) + awaiting-capture as non-blocking flag. Formalizes what the builder already implemented.
2. **DIVERGENCE-007 DESIGNED** — Source review gate: new sources enter with `status='new'`, soft gate, only `active` sources feed ideation, bulk Keep/Remove on Source Bank page. Source neural network DEFERRED to future architect pass.
3. **DIVERGENCE-008 FILED** — Postiz→Buffer swap ratified. Operator confirmed: "yes we switched to buffer as its cheap to use now." The silent swap is now a filed divergence with conditions (delete dead postiz_adapter.py, update all docs).
4. **CORRECTION-jargon-timestamps-cleanup-v1.0 issued** — P1: technical jargon in operator UI (`asset_ready`, `assembling` leaking through) + missing timestamps on pipeline pages. P2: hardcoded platform fallback in produce_chain.py, dead awaiting-capture code, dead Postiz code.

**Why:** Architect deep review of repo state — read all core docs, traced code, ran test suite (673 passing), inspected live UI page by page, queried database. Found the Postiz→Buffer silent swap, unresolved divergences, jargon leaks, and missing timestamps.

**Rationale:** The charter is the constitution. Silent overrides are breaches even when the decision is correct. The operator confirmed the Buffer swap — this filing makes it official. DIVERGENCE-006 was already implemented — this ratification makes it charter-aligned. The corrections address operator-facing quality issues found during the 10-dimension UI review.

**Files:** docs/decisions/AMENDMENT-006-writer-assembler-split.md, docs/decisions/DIVERGENCE-008-postiz-to-buffer-swap.md, docs/reviews/DIVERGENCE-007-design-source-review-gate.md, docs/reviews/CORRECTION-jargon-timestamps-cleanup-v1.0.md

---

### 2026-07-04 STRUCTURE — Flexible narrative patterns + onboarding completeness dashboard

**Feature 1: Config-driven narrative patterns**
- Replaced hardcoded entry_point/tension/turn/landing with config-driven patterns
- New `config/narrative_patterns.yaml` with 8 default patterns (dramatic_arc, myth_buster, how_to, hot_take, listicle, before_after, receipt_card, pattern_breaker)
- LLM selects best pattern per subject type, or proposes custom
- Schema updated to flexible structure_name + beats[{name, content}]
- Story frameworks prompt v3 with pattern selection
- Backward compatible — old v1 modules still readable by drafter
- Files: config/narrative_patterns.yaml, src/module_store.py, prompts/story_frameworks/analyze_v3.md, src/app.py, tests/test_narrative_patterns.py, tests/test_t2_3_playbooks.py

**Feature 2: Onboarding completeness dashboard**
- New `/onboarding-health` page showing missing inputs per module
- Machine-readable `required_inputs` frontmatter added to all 7 playbooks
- `check_completeness()` function in `src/onboarding_completeness.py`
- Source mining API (`POST /api/onboarding/mine-sources`): AI extracts missing inputs from uploaded materials, onboarding transcript, source bank
- Manual fill API (`POST /api/onboarding/fill-input`): operator types missing values directly
- Makes onboarding gaps visible and fillable without re-running entire onboarding
- Files: src/onboarding_completeness.py, src/templates/onboarding_health.html, prompts/onboarding/mine_source_v1.md, src/app.py, src/playbook_runner.py, playbooks/*.md, tests/test_playbook_required_inputs.py
- Module Health link added to nav across 31 templates

**Architect docs:**
- Implementation plan: docs/plans/2026-07-04-flexible-narrative-patterns-and-onboarding-completeness.md
- Architect brief: docs/architect/2026-07-04-flexible-narrative-patterns-and-onboarding-completeness.md

---

### 2026-07-04 FIX — FFmpeg concat crash on audio-only sources

**What:**
- FFmpeg render crashed with `concat failed` when edit plan segments referenced audio-only files (WhatsApp voice memos saved as `.mp4` with no video stream). The concat filter requires `[i:v]` and `[i:a]` from every input, but audio-only sources had no video track and video-only sources had no audio track.
- `AssemblyRenderer` now probes each source with ffprobe before trimming:
  - **Audio-only sources** → synthesizes a solid black video track at canvas resolution paired with the trimmed audio.
  - **Video-only sources** → adds a silent audio track (`anullsrc`).
  - **Image sources** → also gets silent audio added (was previously missing audio for concat).
- New helpers: `_has_video_stream()`, `_has_audio_stream()`, `_stream_type_exists()`.
- 4 new regression tests: audio-only detection, video detection, audio-only source render, video-only source render.

**Rationale:** WhatsApp voice memos are a primary input source for StackPenni. They're saved as `.mp4` containers but contain only an audio stream. The renderer must handle real-world upload formats, not just standard video files.

**Type:** FIX

### 2026-07-04 STRUCTURE — Source Bank page + seed source auto-extraction + DIVERGENCE-007

**What:**
1. **Source Bank page** (`/sources`) — view all sources in the bank with filter buttons (All/Active/Parked/Removed) and per-source Keep/Park/Remove actions. Nav link added across all 29 templates.
2. **Source status API** (`/api/sources/<id>/status`) — update source status (active/parked/removed) for human review.
3. **Seed source auto-extraction** — `_extract_seed_sources_from_materials()` scans uploaded CSV/JSON files for source-like entries and auto-populates `seed_sources` before Sources Engine analysis. Fixes the root cause of empty source criteria during onboarding.
4. **DIVERGENCE-007 filed** — architect design needed for: (a) new source review gate (should new sources require human approval before feeding ideation?), (b) source neural network (connections between sources for cross-source synthesis during ideation).

**Why:** Operator: "is there a button for the sources bank i can see? also when analyst pulls new sources, it is still important to have a section where humans can review what was newly added and decide if it should be removed. we also need to set up a neural network between sources so research can easily see connected sources which would help with ideation."

**Rationale:** The source bank page is a direct build (mechanical). The review gate and source network need architect design — they involve gate semantics (hard vs soft) and judgment work (how connections between sources are determined). DIVERGENCE-007 filed with proposed approaches and open questions.

---

### 2026-07-04 FIX — Writer/Assembler UX overhaul + render crash fix

**What:** Eight issues fixed:
1. **Render crash** — `_check_job_running()` didn't accept `stale_timeout_s` kwarg, causing TypeError on every "Render final cut" click. Fixed by forwarding the kwarg to `JobsStore.start_job()`.
2. **Writer page redesigned** — replaced 6 scattered stage boxes with a single unified card list. Each card shows its state badge and a provenance trail (Idea → Script → Assets dots). Filter buttons at top with counts (All/Ready for review/Writing/Queued/Shipped/At Assembler/Failed/Killed).
3. **Assembler page split** — new `/assemble` route with its own unified card list + filter buttons + counts. Only shows cards with shipped drafts or assets. Separate from Writer page.
4. **Redundant "Proceed to Assets" button removed** — shipping a draft now auto-redirects to the Assembler assets page. Shipped state shows "✓ Script approved and shipped" confirmation + "Go to Assembler →" link.
5. **Provenance trail on every card** — dots showing Idea → Script → Assets stage progression (green=done, red=active, grey=pending). Also on draft page and assets page.
6. **Render UX improved** — background polling with status updates every 5s for up to 10min. Shows elapsed time. New `/api/assets/<id>/render-status` endpoint. No more silent blocking.
7. **Nav links updated** — `/create#assembler` → `/assemble` across all 29 templates.
8. **Similar ideas root cause identified** — source bank has only 2 junk sources (HTML page + manifest file), `feeds: []` in config, no seed sources provided to Sources Engine. LLM has nothing to ground ideas in so it generates variations on the same business subjects. Operational gap — operator needs to provide seed sources and configure RSS feeds.

**Why:** Operator feedback: "three diff cards at writer... also assembler cards in there... i just need to see all the cards and it have what state its in... filter should be at each stage also... a count so person knows how many cards are at each stage... i click on a card at writer to send to assembler but then another button at the bottom appears... when i hit the final cut button a pop up showed it will take a while but then nothing to show... still no video showed up... why are the ideas so similar"

**Rationale:** UX — operator needs a single unified view per stage with clear state + filter capability. The render crash was a code bug (unknown kwarg). The similar ideas issue is an operational gap (empty source bank) not a code bug.

---

### 2026-07-04 OPS — Activity list capped to 10 rows + "Show more" toggle

**What:** Home page (index.html) Recent Activity section now shows only the first 10 activity items by default, with a "Show more activity (N more)" button that reveals the remaining items. Button toggles to "Show less activity" when expanded. Backend cap (`all_cards[:15]`) removed so the full list is available client-side. Jinja `{% if loop.index > 10 %}style="display:none;"{% endif %}` hides extras; JS `toggleMoreActivity()` toggles visibility.

**Why:** Operator: "Recent activity list just gets longer, cap it to ten rows with a more button to see more activity."

**Rationale:** Pure UX — the activity feed grows unbounded as ideas/drafts/assets accumulate. Capping to 10 keeps the dashboard scannable. Toggle gives full access on demand.

---

### 2026-07-04 STRUCTURE — Writer/Assembler pipeline split + four-role menu (DIVERGENCE-006)

**What:** Production chain split into two stages: Writer (draft generation, stops at draft_ready for Gate 2 review) and Assembler (fan-out, triggered when operator ships the draft). `produce_chain.py`: `run_chain` → `run_writer_chain` + `run_assembler_chain`; `enqueue_chain` → `enqueue_writer_chain` + `enqueue_assembler_chain` (legacy alias kept). `app.py`: Gate 1 approve now triggers Writer chain only (not full chain); Gate 2 ship now triggers Assembler chain. Awaiting-capture blocking removed — cards with capture tasks go straight to `approved` → Writer. Card states: `producing` → `writing`; `production_failed` → `writer_failed`/`assembly_failed` (legacy state preserved). Menu standardized across ALL 29 templates: Researcher (/ideas) / Writer (/create) / Assembler (/create#assembler) / Analyst (/published) + setup links. Page titles and button labels updated to match four-role model. Create page restructured: Writer sections (in progress / ready for review / queued) + Assembler sections (in progress / ready for review / shipped drafts) + failed retry. Ideas page: "Awaiting Capture" tab removed. Home page "This Cycle" labels: Researcher/Writer/Assembler/Analyst.

**Why:** Operator: "the menus dont reflect what we discuss and workflow of the cards arent going from idea approved to the writer stage." T8.6 auto-chain bypassed Gate 2 — it auto-shipped drafts and ran fan-out without human review. Operator wants: Researcher → Writer → Assembler → Analyst as clear stages, with the card flowing through each for review.

**Rationale:** Restores Gate 2 (the human pass) which T8.6 bypassed. The Writer/Assembler split maps to the existing AI Profiles (Drafter = Writer+Assembler, but the pipeline now pauses between them for human review). Awaiting-capture removal: operator said "if there is an idea that needs human capture of real photos it doesn't go to a separate waiting section — the card still goes to the Writer." Capture tasks remain visible on the card but no longer block the pipeline. Consistent nav was a defect — 24 different nav configurations across templates.

---

### 2026-07-04 STRATEGIC — DIVERGENCE-006 filed: Researcher/Writer/Assembler/Analyst menu + workflow restructure

**What:** Filed `docs/decisions/DIVERGENCE-006-researcher-writer-assembler-analyst-menu.md` — operator proposes four-role menu (Researcher/Ideas → Writer → Assembler → Analyst) and removal of the awaiting-capture blocking state. Four conflicts with the current charter identified: (1) awaiting-capture removal vs AMENDMENT-003, (2) Writer "continues not rewrites" as naming vs structural change, (3) menu restructure from stage-centric to role-centric, (4) Analyst owning publishing vs separate Publish gate.

**Why:** Operator laid out a clear mental model of the pipeline as four roles. Some of it is labeling (maps to existing AI Profiles), some is structural (awaiting-capture removal, Analyst-owned publishing).

**Rationale:** Awaiting-capture removal and Analyst-owned publishing are structural changes that conflict with AMENDMENT-003 and the charter's pipeline design. Builder does not decide design — filed for architect review. Consistent-nav fix and activity-list cap proceed as non-structural work. Builder recommends: approve four-role menu as relabel, make awaiting-capture non-blocking flag, defer Drafter split and Analyst-publishing to M3/M4.

---

### 2026-07-03 STRUCTURE — T8.7: AI Profiles (P1)

**What:** New `config/profiles.yaml` with three named profiles: Researcher (ideation + source scouting, generative temp), Drafter (produces final asset from approved idea, generative temp), Analyst (reads results, drives loops, judgment/temp-0 class). `LLMAdapter.complete()` gains `profile` parameter, passed through to all `ProvenanceLog.log()` calls. Provenance table gains `profile` column (idempotent migration). Pipeline LLM calls declare their profile: ideas_generate → "researcher", draft_generate → "drafter", produce_chain → "drafter".

**Why:** Per CORRECTION Section 3.1. Profiles make model/temperature/prompt composition explicit and configurable. Per AMENDMENT-005, profiles are named compositions, not code classes — they describe which prompts, which module views, what temperature class. Provenance records which profile produced each artifact.

**Rationale:** Profiles are the semantic layer above backends. Backend selection flows through the adapter's `backend` parameter (BYO-AI hook, unchanged). Profiles provide the composition map: which prompts + module views + temperature class for each role.

### 2026-07-03 LOGIC — T8.6: Auto-production chain (P1)

**What:** New `src/produce_chain.py` module with `ProductionChain` class that orchestrates draft generation → fan-out in a background thread. `ideas_gate_decision` on approve (no capture): enqueues `produce_chain` job; card state transitions `producing` → `asset_ready` (success) or `production_failed` (with step + error info). New `/api/ideas/<card_id>/retry-production` endpoint for retry. No-auto-publish absolute — chain terminates at asset review.

**Why:** Per CORRECTION Section 2.1. Operator feedback: "Once an idea is approved, it should not go to a draft page where the operator clicks Generate, then an asset page where the operator clicks Generate again. Approval is the production trigger." Eliminates 3+ manual generation clicks between approval and asset review.

**Rationale:** The operator's next touchpoint after approval should be reviewing the finished asset. The chain amplifies any generation defect by running unattended, which is why T8.3-T8.5 (source grounding) landed first. No-auto-publish remains absolute.

### 2026-07-03 STRUCTURE — T8.5: Sources flow to production (P1)

**What:** `prompts/draft/generate_v2.md` → v2.3: new `{grounding_sources}` section with full content of every cited source labeled by title + ID, explicit no-fabrication rule. `draft_generate` route resolves `source_refs` to assemble this variable; empty content degrades to summary with `(summary only)` marker. `prompts/assets/fan_out_v2.md` → v2.2: new `{source_titles}` section — titles only, no full content (draft is authoritative per T3.13 S3).

**Why:** Per CORRECTION Section 1.4. Sources died at Gate 1 — the draft prompt had no source variable. Now the full content of every cited source travels with the idea through production. Fan-out receives titles only (must not re-write facts).

**Rationale:** Facts, quotes, dates, and specifics in the draft must come from real source material. The stage-appropriate injection doctrine: selection stage gets digest, production stage gets full content, fan-out gets titles only.

### 2026-07-03 STRUCTURE — T8.4: Idea cards carry source_refs (P1)

**What:** `IDEA_CARD_SCHEMA` updated — `source_refs` (integer array, minItems=1) replaces `evidence_links` in required list; `source_notes` added (optional per-source annotation). `prompts/ideas/generate_v1.md` → v1.3: Source Bank section with `[S14] title — summary` digest format, cite-by-ID instructions, multi-source synthesis rule, new `source_criteria` variable. `ideas_generate` route builds source digest from `sources` table (ID-prefixed), validates source_refs, derives evidence_links from resolved sources for backward display. `_generate_card_from_seed` auto-registers seed as `manual` source, includes seed in digest, ensures seed source always cited. Ideas page template renders resolved sources with title links + source_type badges.

**Why:** Per CORRECTION Section 1.2. `evidence_links` were decorative freeform objects — nothing verified they correspond to real Source Bank material. Now ideas cite sources by ID from the addressable `sources` table; every idea MUST cite at least one source; one idea may compose multiple sources.

**Rationale:** Grounding ideas in real source material produces better content. The digest format `[S14] title — summary` gives the LLM addressable references to cite. Multi-source synthesis is explicitly encouraged.

### 2026-07-03 STRUCTURE — T8.3: Source Bank as addressable store (P1)

**What:** New `sources` table in `pipeline.py` (id, business_slug, source_type, title, url, summary, content, origin, first_seen, content_hash, status). `source_snapshot.py` writes fetched RSS items into this table as `source_type='rss_item'` (deduped on URL-hash content_hash), with full extracted content via trafilatura. `materials.py` registers `source_type='operator_material'` rows on text ingestion (deduped on content_hash). PipelineStore gains methods: `add_source`, `get_source`, `list_sources`, `resolve_source_refs`, `archive_source`. Schema migration adds `source_refs` + `production_error` columns to `idea_cards`. All sources scoped by `business_slug`.

**Why:** Per CORRECTION-source-grounding-and-auto-production-v1.0 Section 1.1. The "Source Bank" was the source-criteria module + a 4KB-capped RSS snapshot — no addressable store of sources. Now sources are addressable by ID, with full content for production-stage injection and summary for selection-stage injection.

**Rationale:** Ideas must be grounded in real source material. An addressable store with dedup is the substrate for `source_refs` on idea cards (T8.4) and grounding sources in drafts (T8.5).

### 2026-07-03 FIX — T8.1: Kill remaining source truncation (P0)

**What:** Removed `source_material[:4000]` blind character slice in `ideas_generate` (app.py:4061). Replaced `SNAPSHOT_CHAR_CAP = 4000` in `source_snapshot.py` with `MAX_SNAPSHOT_ITEMS = 40` — count-bounded, not character-sliced. `build_snapshot_text` now takes the most recent N items across all feeds, each with its full summary (already bounded by `SUMMARY_CHAR_LIMIT` at extraction time).

**Why:** Same truncation disease CORRECTION-format-selection killed for modules — blind `[:4000]` character slicing silently drops source items mid-list as content grows. Count-bounded digest is the stage-appropriate injection doctrine: selection stage gets ID + title + summary per active source, bounded by count, not by character slicing.

**Rationale:** Per CORRECTION-source-grounding-and-auto-production-v1.0 Section 1.3 (P0, land immediately). AC: grep for `[:4000]`, `[:2000]`, `[:1500]` across `src/` returns none on module/source injection paths.

### 2026-07-03 OPS — T8.2: Dead code removal + CONTEXT.md update (P0)

**What:** Removed dead `response_data` block in `ideas_gate_decision` (series branch) — was built but never used; actual response built separately as `response`. Updated CONTEXT.md with three new lines per correction: (a) every idea cites sources by ID, one idea may compose multiple sources; (b) Gate 1 approval triggers production automatically, publishing is never automatic; (c) AI work runs under named profiles (Researcher/Drafter/Analyst) defined in `config/profiles.yaml`. Core Loop diagram updated with auto-chain. New "AI Profiles" section added to Shared Language.

**Why:** Per CORRECTION-source-grounding-and-auto-production-v1.0 Section 4 (P0 housekeeping). Dead code is a defect even if harmless. CONTEXT.md is the operational mirror — it must reflect the new architecture before the P1 tasks build it.

**Rationale:** The correction explicitly designated these as P0/quick — land immediately, before the P1 architecture tasks.

### 2026-07-03 STRUCTURE — CORRECTION-source-grounding-and-auto-production-v1.0 filed

**What:** Filed architect correction introducing three architectural changes: (1) Source Bank as addressable store (`sources` table, idea cards carry `source_refs` by ID, kill remaining blind truncation); (2) Approval is the production trigger — Gate 1 approval auto-produces through to asset review, new card states `producing`/`asset_ready`/`production_failed`, no manual Generate clicks between approval and asset review; (3) AI Profiles (Researcher/Drafter/Analyst) as named compositions in `config/profiles.yaml`, provenance gains `profile` column. No-auto-publish remains absolute.

**Priority split:** Section 1.3 (kill `source_material[:4000]` + `SNAPSHOT_CHAR_CAP`) and Section 4 (dead-code sweep, CONTEXT.md lines) are P0/quick — land immediately. Sections 1 (Source Bank + source_refs), 2 (auto-production chain), and 3.1 (profiles.yaml + provenance profile column) are P1 architecture — sequence after T3.13 S1+S3 (confirmed landed at M3 checkpoint). Section 3.2 (Analyst scraping) is M6 scope (already has landing zone via `sources` table).

**Why:** Operator feedback: (a) every idea must be grounded in listed sources, one idea may compose multiple sources; (b) approval is the production trigger — no manual Generate clicks between approval and asset review; (c) introduce AI profiles (Researcher/Drafter/Analyst). Architect confirmed via live repo walk-through: sources die at Gate 1 (draft prompt has no source variable), evidence_links are decorative (freeform, not addressable), blind truncation survives in ideation, post-approval dead air (3+ manual generation clicks).

**Sequencing:** Source plumbing (T8.3-T8.5) lands first or together so first auto-produced drafts are source-grounded. Auto-chain (T8.6) does NOT enable until T8.3-T8.5 land. Profiles (T8.7) may land in parallel. BUILD_PLAN tasks T8.1-T8.7 added under new M8 milestone.

**Rationale:** Ideas grounded in real source material produce better content. Auto-production eliminates operator friction at the most mechanical part of the pipeline. Profiles make model/temperature/prompt composition explicit and configurable rather than implicit in code.

### 2026-07-03 FIX — UI-REVIEW-002: 15 findings from deep operator walk-through

**What:** Deep UI inspection after CORRECTION-module-context-assembly + CORRECTION-feedback-plumbing. Operator explicitly asked for "slight confusion or grievances" — not just obvious issues.

**Findings filed:** `docs/reviews/UI-REVIEW-002-deep-walkthrough-2026-07-03.md` — 15 findings. All fixed in this session.

**Fixes applied:**
1. Draft page: shipped state locks editing controls (Edit/Regenerate/Kill/Revise/audit-apply/feedback hidden when shipped; only "Proceed to Assets" + "Reopen for revision" shown). Gate API accepts `reopen` to return a shipped draft to `draft_ready` without bumping the draft version.
2. Asset staleness: draft page shows warning when draft was edited after assets were generated
3. Ideas page: series children grouped under parent (sorted, not scattered)
4. Ideas page: old clone children still have identical text — noted for architect (legacy data)
5. Human-readable scope labels: "one_off" → "Single piece", "series_of_n" → "Series", "pillar_with_derivatives" → "Main + derivatives"
6. Create page: descriptive draft titles (idea text instead of "Draft #N"), deduplicated columns
7. Dashboard: activity grouped by idea with sub-events, human-readable timestamps
8. Published page: "Scheduled" badge shows "Draft schedule (Postiz not connected)" when Postiz unavailable
9. Metrics page: "Pull metrics now" button disabled when Postiz unavailable
10. Library page: module previews collapsed with "Show more" toggle
11. Fan-out prompt: explicit "Do NOT add emojis/hashtags not in source draft" rule
12. Draft page: version/state shown as visible badge instead of tiny grey text
13. Draft page: empty state "Generate draft" button centered under instruction text
14. Dashboard: relative timestamps instead of raw ISO
15. Create page: approved idea links no longer truncated mid-word

### 2026-07-03 STRUCTURE — T3.13 added to BUILD_PLAN per CORRECTION-generation-diversity-and-asset-continuity-v1.0

**What:** New task T3.13 covering four operator-reported failures: (S1) deterministic idea generation, (S2) format convergence, (S3) fan-out mutating approved text, (S4) orphaned draft previews. T3.7 AC annotated to note S3 makes the "per-platform variants from Format Guide" AC true as written (currently from business config loop).

**Why:** Operator confirmed 17 cards converging on same few ideas; fan-out paraphrasing Gate-2-approved text; draft preview images orphaned. Correction approved by operator, ready for implementation. Sequencing: S1a → S3 → S1b/S1c → S4 → S2. M3 sprint checkpoint blocked until S1+S3 land.

**Rationale:** Generative calls (ideas, drafts, fan-out) need real temperature, not the temp-0 guardrail which correctly covers judgment/extraction only. Per-piece approval semantics require native-platform packaging verbatim. Asset continuity prevents paying twice and orphaning judged previews.

**Rationale:** Operator caught that the first UI inspection was superficial — only checked for obvious presence/absence of buttons. Deep walk-through found state-locked mode missing, stale assets, scattered series children, jargon labels, and more.

### 2026-07-03 STRUCTURE + LOGIC — CORRECTION-module-context-assembly + CORRECTION-feedback-plumbing-and-pipeline-fixes

**Module Context Assembly (STRUCTURE):** New subsystem — section-addressable module reads (`get_section`, `get_entry`, `get_index` on ModuleStore) + per-prompt view map (`prompts/views.yaml`) + assembler (`src/context_assembly.py`). All inline `[:2000]`-style module slices removed from `src/app.py` pipeline routes. `_extract_tells_checklist()` deleted — replaced by the `tells_checklist` view entry. Prompt bumps: `draft/generate_v2.md` → v2.2 (revision block + Format Guide wording), `assets/fan_out_v2.md` → v2.1 (adds `{visual_style}`). CONTEXT.md updated with "rules vs material" paragraph. Rationale: positional truncation degrades silently as modules grow; different prompts need different projections of the same module.

**F1 Direct edits → draft_text authoritative (LOGIC):** New `/api/draft/<id>/edit-text` endpoint writes `draft_text` directly via `save_edited_text()` (bumps version, logs weight-3 diff as feedback, invalidates stale audit flags). Old `direct_edit` via `/feedback` returns 400. UI: "Edit draft" toggle replaces freeform "Submit as direct edit" button. Rationale: direct edits were stored in `human_edits` column but nothing ever read it — downstream reads `draft_text`.

**F2 Revision feeds previous draft + feedback (LOGIC):** `draft_generate` route now assembles `previous_draft` (current draft_text, cap 6000 chars) and `revision_feedback` (weight-tagged feedback log entries, cap 3000 chars, highest-weight kept when trimming) into the prompt variables. First-time generation carries `(first draft — no previous version)` marker. Rationale: revise was a blind re-roll with identical inputs.

**F3 Series breakdown (LOGIC):** Series children now spawn via LLM breakdown call (`prompts/ideas/series_breakdown_v1.md`) with per-part ideas/hooks. Children enter state `new` (not `approved`) — operator gates each part. New `/api/ideas/<parent_id>/bulk-approve-children` endpoint. Fallback to clones in state `new` on LLM failure with surfaced warning. Rationale: n-1 pieces of AI content were advancing past Gate 1 without operator seeing per-part content.

**F4 owner_type column (STRUCTURE):** `asset_media` table gains `owner_type` column (default `'asset'`). Draft visuals use `owner_type='draft'` with the real `draft_id` — replaces the synthetic `draft_id + 100000` scheme. Legacy rows migrated idempotently in `_init_tables`. `generate_image`, `_record_media`, `list_asset_media` all accept `owner_type` parameter. Rationale: magic number breaks silently when real asset IDs cross 100000.

**F5 ffprobe real durations (LOGIC):** `probe_duration()` module-level function in `assembly.py` called in the edit-plan inventory loop for generated videos and uploaded video/audio. Images keep 3.0s (plan intent, not file property). On probe failure, falls back to default with `(duration unverified)` marker. Rationale: LLM planned trims against fictional durations.

### 2026-07-03 STRUCTURE — Inbox batch 2026-07-03-e + format-selection filed: AMENDMENT-005 (processes are module compositions) + CORRECTION-format-selection-living-v1.0

**What:**
- Filed `docs/decisions/AMENDMENT-005-processes-are-module-compositions.md` — architecture doctrine: processes (ideation, drafting, treatment) are compositions of modules, not hardcoded route handlers. Process Registry (`config/processes.yaml`) is the 9th module — versioned, gate-only writes, AI-improvable through the gate. One compose-and-run engine replaces per-process module wiring. BUILD_PLAN updated to v1.4: T2.12 added (registry extraction), T3.2 reworded, M5/M6 targets widened.
- Filed `docs/corrections/CORRECTION-format-selection-living-v1.0.md` — P0 bug: module truncation (`[:2000]`, `[:1500]`) in idea generation routes means the LLM never sees most of the Format Guide (17KB, only first 2KB injected). Fix: remove all blind truncation; stage-appropriate injection (selection sees compact digest, production sees full entry). Architecture: format selection by affordances + evidence + distribution feedback, not decision table. Format Guide schema gains `affordances`, `performance_evidence`, `variant_type`, `aspect_ratio`; loses `decision_table`. Governing principle added to CONTEXT.md: "Prompts carry procedures; modules carry knowledge."

**Rationale:** Architect direction via inbox protocol (MANIFEST-2026-07-03-e, MANIFEST-2026-07-03-format-selection). AMENDMENT-005 stops process-first drift before M3 pipeline work accretes more hardcoded route handlers. The format-selection correction addresses the proximate cause of video under-suggestion: not decision-table weighting, but blind truncation hiding most formats from the LLM.

**Manifests:** `docs/inbox/processed/MANIFEST-2026-07-03-e.md`, `docs/inbox/processed/MANIFEST-2026-07-03-format-selection.md`

---

### 2026-07-03 TECH — T4.1 + T4.2: Postiz adapter + metrics collection (M4)

**What:**
- `src/postiz_adapter.py` — Postiz Public API adapter: publish pieces (after per-piece approval), pull post-level analytics, store metrics. Config-driven (base_url, api_key, integration_ids from `config/models.yaml`). Graceful fallback when Postiz not available — asset stays in 'approved' state, no data loss.
- Publish route updated: `/api/assets/<id>/schedule` now calls Postiz to actually post. Returns 502 with helpful hint when Postiz not configured. Retry endpoint for failed publishes.
- `/metrics` page + `/api/metrics/pull` endpoint — view metrics for published pieces, manually trigger pulls.
- `/api/postiz/status` — check Postiz availability + list connected integrations.
- `cron_pull_metrics.py` — nightly cron script for unattended metrics collection (T4.2).
- `publish_log` + `post_metrics` tables in SQLite.
- 29 new tests (471 total). Postiz config block added to `models.yaml`.

**Rationale:** T4.1 + T4.2 of BUILD_PLAN. Postiz not yet installed on VPS — Docker available but no container running. Adapter is ready; set `POSTIZ_API_KEY` env var and configure Postiz to enable end-to-end publishing. Per-piece approval enforced in code (asset_state must be 'approved').

---

### 2026-07-03 LOGIC — T5.1 + T5.2 + T5.3: Inward learning loop + async gate (M5)

**What:**
- `src/proposal_store.py` — ProposalStore: async gate queue for module improvement proposals. Superseding (newer proposal on same module+section marks older as superseded, visible not deleted), age tracking, pending counter, bulk approve/reject, summary stats. Per AMENDMENT-005: process-registry is a valid proposal target; mapping_change is a valid proposal type.
- `prompts/learning/generate_proposals_v1.md` — LLM prompt for weekly proposal generation. Reads published results + Feedback Log (direct edits weighted highest) + performance notes + module versions → produces specific, evidence-backed proposals with exact diffs. Never vibes — evidence required.
- `cron_generate_proposals.py` — weekly cron script. Gathers inputs, calls LLM via adapter (temperature 0), stores proposals in the gate queue.
- `/proposals` page + `/api/proposals/<id>/approve` + `/api/proposals/<id>/reject` + bulk approve/reject endpoints. Gate queue UI with: pending counter, age per proposal ("submitted N days ago"), evidence display, exact diff, quick-reason reject chips, bulk select-all bar.
- T5.3: Voice Profile update path — approved voice-profile proposals trigger version bump via ModuleStore (approval is the gate; the operator's approval is the human gate per the charter).
- 21 new tests (492 total). `proposals` table in SQLite.

**Rationale:** T5.1–T5.3 of BUILD_PLAN. The inward learning loop reads what the operator did (feedback + direct edits + performance data) and proposes specific module updates — the system gets better at the operator's voice and content quality over time, but every change passes the human gate. No deadline or pressure mechanics anywhere.

---

### 2026-07-03 OPS — Inbox batch 2026-07-03 filed: orchestrator correction, definition-of-done process, whisper transcription decision

**What:**
- Filed `docs/reviews/CORRECTION-orchestrator-drafting-and-ux-v1.0.md` — correction from architect review of commit `372f81e` following operator's first end-to-end onboarding run. Covers P0-1 (drafting input starvation — root cause of all thin/empty documents), P0-2 (validation crash on `next_focus: null`), P1-1 (gate relocation to Library — draft-status modules), P1-2 (conversation continuity/resume), P1-3 (readback rendering), P1-4 (upload feedback), P2-1 (conversational latency — `converse` backend role), P2-2 (orchestrator prompt v2 — agency-intake posture).
- Filed `docs/PROCESS-definition-of-done-v1.0.md` — operator ruling: Hermes does not report work as done until automated suite + human UI test + end-to-end pass + done report. Binding on all work from 2026-07-03. Reference added to `docs/CONTEXT.md` under new "Working Agreements" section.
- Filed `docs/decisions/DECISION-transcription-whisper-v1.0.md` — operator approved self-hosted Whisper via `faster-whisper` (CTranslate2, int8, medium model, CPU). Background worker in-process. Closes the transcription hosting blocker from CORRECTION-session-memory-and-materials-v1.1. Unblocks Voice Profile end-to-end.

**Rationale:** Architect direction via inbox protocol (MANIFEST-2026-07-03 + MANIFEST-2026-07-03-b). Implementation order specified: P0-1 → P0-2 → P1-1 → P1-2 → P1-3/P1-4 → P2, with transcription worker buildable in parallel but wired after P0-1. Session-storage refactor from CORRECTION-session-memory-and-materials-v1.1 is required by P1-2 and is folded into this batch.

**Manifests:** `docs/inbox/processed/MANIFEST-2026-07-03.md`, `docs/inbox/processed/MANIFEST-2026-07-03-b.md`

---

**What:**
- **P0 bug fix:** Removed duplicate `const playbookName` declaration in `src/templates/session.html` (line 467). The second declaration, introduced when the gate-actions routing block was appended, caused a `SyntaxError: Identifier 'playbookName' has already been declared` — which prevents the browser from executing the entire `<script>` block. All interactive JS (attach button, send button, gate approve/park/reject buttons) was dead.
- **Guardrail:** New `tests/test_template_js_parse.py` — extracts `<script>` blocks from session.html, renders Jinja placeholders with dummy values, and runs `node --check` to validate syntax. Catches the entire class of "template edit silently kills page JS" bugs. Verified: reintroducing the duplicate correctly fails the test with the exact SyntaxError.

**Rationale:** CORRECTION-onboarding-single-thread-v1.0 Item 1 (P0). The architect identified this as a regression that blocks all onboarding use. This is the second time a template edit silently killed page JS; the parse check ends the category.

**Corrections filed:** `docs/reviews/CORRECTION-onboarding-single-thread-v1.0.md` — arrived without manifest (inbox protocol rule 5). Filed as architect direction to `docs/reviews/` since it is a correction/review document. Item 2 (architectural redesign: single-thread onboarding) tracked as GitHub issue #2, scheduled for next review tag.

---

### 2026-07-03 FIX — Validator strips markdown code fences from LLM JSON output

**What:**
- **Validator fix:** `validate_llm_output()` in `src/validator.py` now strips markdown code fences (```json ... ```, ``` ... ```, ```javascript ... ```) before `json.loads()`. GLM-5.2 wraps JSON output in ` ```json ` fences; `json.loads()` choked on the leading backticks — both initial attempt and retry failed identically with "Expecting value: line 1 column 1 (char 0)".
- **9 new tests** (`tests/test_validator_code_fences.py`): fence stripping (json/plain/js variants), multiline JSON in fences, real provenance #5 output from run 24, and negative tests (garbage still rejected, invalid JSON in fence still rejected). 329 tests total.

**Rationale:** Operator reported error when uploading a zip to voice-profile-builder session run 24. Provenance rows #4 and #5 showed both LLM attempts returned valid JSON wrapped in ` ```json ... ``` ` — the validator rejected them as non-JSON because it didn't strip the fence wrapper. This is a mechanical parsing issue, not an LLM quality issue — the model produced correct JSON, the validator just couldn't see past the markdown wrapper.

**Root cause:** Many LLMs (GLM-5.2, Claude, GPT) wrap structured output in markdown code fences despite instructions to return raw JSON. The retry prompt ("respond with ONLY valid JSON") doesn't help because the model considers the fence to BE "only JSON." The fix is in the validator, not the prompt — stripping fences is mechanical, not judgment.

**Corrections filed:** `docs/reviews/CORRECTION-session-memory-and-materials-v1.1.md` — arrived without manifest. Filed as architect direction. 5 findings (F1–F5) covering: file-only turns invisible to AI, materials not injected into converse prompt, history truncation keeping oldest/not newest, parallel-array transcript fragility, no anti-repeat guard. Fixes in priority order starting with F3 + F1.

---

### 2026-07-03 FIX — Session memory & materials (F1, F2a, F2b, F2c, F3, F5)

**What:**
- **F3 (P0):** History truncation was a head slice (`[:4000]`) — kept the OLDEST turns, dropped the NEWEST. Changed to tail slice (`[-12000:]`) + raised budget from 4k to 12k chars. This was the root cause of the AI repeating earlier questions verbatim: from its perspective, the conversation was still at that earlier point.
- **F1 (P0):** File-only turns (uploads with no text) were invisible to the AI. The file note was stored only in `business_qa`, which `_build_conversation_history` excludes for session messages. Now `session_messages` stores `[Operator attached files: ...]` so the AI can see uploads in the transcript.
- **F2a (P0):** Uploaded material content never reached the converse LLM. Added `_build_materials_summary(run_id)` — queries materials for the run, builds a capped summary (1,500 chars/material, 6,000 total), and injects it as `{materials_summary}` into the converse prompt (v3.0). The AI now sees document excerpts and audio status.
- **F2b (P0):** No `.docx` extraction existed. Added `_extract_docx_text()` using python-docx. `.docx` files now extract paragraph text, same as PDF.
- **F2c (P0, blocks voice profile):** `.mp4`, `.opus`, `.aac`, `.flac` not recognized as audio — stored as binary garbage. Added to audio extension list. Transcription itself needs a decision (DIVERGENCE-005 filed) — interim: materials summary says "transcription pending" so the AI acknowledges receipt.
- **F5 (P1):** No anti-repeat guard. Added prompt section ("Questions you have already asked") + server-side `_is_near_duplicate()` using difflib SequenceMatcher (threshold 0.9). On near-duplicate, regenerates once with the same prompt (the anti-repeat section now visible in context).
- **18 new tests** (`tests/test_session_memory_fixes.py`). 347 total.
- **Prompt bumped to v3.0:** materials section, anti-repeat section, "reference uploaded materials" rules.
- **python-docx added to requirements-prod.txt.**
- **DIVERGENCE-005 filed:** audio transcription implementation decision (self-hosted faster-whisper vs hosted API) — operator gate required.

**Rationale:** CORRECTION-session-memory-and-materials-v1.1 traced the operator's exact field report: AI asked "what kind of stuff did you send?" after receiving a zip, re-asked "what's the business?" after receiving the Brand Report, then repeated an earlier reply word-for-word. Four compounding bugs (F1–F3, F5) made every intake session degrade into a loop. These fixes address the P0 items; F4 (turn log restructure) deferred to this tag or next.

**Not done:** F4 (replace parallel arrays with single turn log) — P1, deferred. F3 rolling summary — P1, with orchestrator. F2c transcription implementation — blocked on DIVERGENCE-005 operator decision.

---

### 2026-07-02 BUILD — Session component: LLM-driven conversation, all playbooks, run reuse

**What:**
- **LLM-driven conversation (not template questions):** Every message goes through `prompts/session/generic_converse_v1.md` — the AI reasons about what it knows and what it still needs, asks smart follow-ups referencing what was said, and decides when it has enough to trigger analysis. No hardcoded question list. The AI is present at every stage; the operator is never handed a form.
- **Run reuse:** Visiting a playbook page reuses the latest incomplete run instead of creating a new one every visit. Dashboard shows only the latest run per playbook, not the full history of dead runs.
- **All playbooks use session component:** Voice Profile, Sources, Viral Patterns, Audience, Story, Format, Visual Style — all now render the same chat interface. Gate buttons route to the correct store endpoint per playbook. No more seeing raw procedure markdown.
- **Readback shows after analysis:** When the AI says `ready_to_draft`, it triggers the playbook-specific analysis (correct prompt + schema for each of the 7 playbooks via a playbook→prompt/schema/output-key map), stores the result, reloads the page, and shows the readback with Edit / Approve / Park / Start over gate buttons.
- **Generic readback:** `_build_readback()` formats any playbook's output for display. Business Profile gets a custom format; others get a generic key-value listing.
- **PYTHONPATH fix:** Added `PYTHONPATH=/home/daimon/ViralFactory/src` to systemd service so nested `from module_store import...` calls work under gunicorn, not just in tests.
- **Graceful JS error handling:** Session frontend checks `content-type` before parsing JSON; shows human-readable error messages for 401/500/502/504 instead of raw HTML parse failure.
- **Technical details behind disclosure:** No file paths in default operator view — just playbook name + gate step behind a `<details>` element (F4 compliance).

**Rationale:** UI-REVIEW-001 F3 is structural — the console must be a conversational AI session, not a document viewer. Template questions were the first attempt; the operator correctly identified that the AI should reason about what it knows and ask smart follow-ups, not recite a fixed list. Run spam was caused by creating a new run on every page visit. All playbooks needed the session component, not just Business Profile. These changes address acceptance checks 1, 3, 4, 5, 6, 7 from UI-REVIEW-001.

---

### 2026-07-02 BUILD — Zip file support + PDF/image intake (DIVERGENCE-004)

**What:**
- `MaterialsIntake.ingest_zip()`: extracts zip archives to a temp directory, ingests each file recursively through the existing intake pipeline. Handles nested directories, skips hidden files and __MACOSX junk, cleans up temp dir. Failed files logged as error-channel materials — zip doesn't fail if one file is broken.
- `ingest_file()` extended: `.zip` delegates to `ingest_zip()`. PDF text extraction (pdfplumber → PyPDF2 → graceful fallback). Image files (.png/.jpg/.jpeg/.gif/.bmp/.webp) stored as visual references with file copied to upload dir. Binary files get graceful placeholder instead of crashing.
- Works through both `/api/run/<id>/upload` and `/api/session/<id>/upload` (session component).
- DIVERGENCE-004 filed for architect awareness.
- 9 new tests (319 total).

**Rationale:** Operator needs to upload a zip of mixed materials (chats, docs, photos, audio) in one shot. Without zip support, the file fell through to "unknown type" and tried to read binary as text. This enables true one-go intake per the charter. No charter conflict — capability extension, not a design change.

**What filed:**
- `UI-REVIEW-001-intake-console.md` → `docs/reviews/UI-REVIEW-001-intake-console.md` (ADD)
- `MANIFEST-2026-07-02-D.md` → `docs/inbox/processed/` (after filing)

**APPLY executed:**
1. UI-REVIEW-001 marked as **blocking for the operator end-to-end test**. The 7 acceptance checks must all pass before the end-to-end test re-runs.
2. UI-DIRECTION.md bumped to v1.3: added Principle 9 (console renders sessions, not documentation — F3) and Principle 10 (operator-facing copy rule — F4). Surface 1 (Onboard) rewritten to describe the session interaction model: chat transcript pane, input box, file upload, readback→gate, progress rail.
3. CONTEXT.md: added "The console renders sessions, not documentation" principle verbatim from the review.
4. Playbook step schema extended: `run_order` (integer) and `display_label` (operator-facing label) added as HTML comment metadata in all 8 playbooks. PlaybookParser reads both. Onboard route sorts playbooks by `run_order` and passes `display_label` to template. Business Profile Intake = run_order 1 (first), Visual Style = 8 (last).
5. Voice input deferred per existing T2.6–T2.8 record — session component to be built text+files only, mic slots in later.
6. PROGRESS.md updated: operator UI review received, findings accepted, end-to-end blocked on UI-REVIEW-001 acceptance checks.

**Rationale:** Architect batch D. The operator (Daimon) walked the live console and found the intake page renders playbook markdown as static text — no input, no upload, no session. F3 is structural: the console must be a conversational AI session, not a document viewer. This blocks the M2 end-to-end test until the session component is built and all 7 acceptance checks pass.

---

### 2026-07-02 BUILD T3.5–T3.12 — Co-production loop complete (M3 done)

**What:**
- **T3.5 Drafter:** prompt template (draft/generate_v1.md), DRAFT_SCHEMA (draft_text + visual_direction + self_audit_flags), Flask route loads ALL 8 modules + capture material → LLM → draft stored. Visual direction is text only (no renders). Self-audit flags shown with rule + suggestion. Uses drafter backend from models.yaml.
- **T3.6 Human pass (Gate 2):** reaction chips + typed feedback + direct-edit mode. Direct edits saved as authoritative (highest weight=3 in Feedback Log). Gate decisions: ship-forward, kill (with reason→feedback), revise (version increment).
- **T3.7 Assets stage:** prompt template (assets/fan_out_v1.md), per-platform variant generation via LLM. Image prompts generated per platform. Fan-out only on shipped drafts.
- **T3.8 Assets gate (Gate 3):** per-variant approve/fix/kill. Approved assets flow to publish.
- **T3.9 Origin threading:** origin + format + scope carried from idea card → draft → assets → nightly stats (get_pipeline_stats: origin/format/scope breakdown).
- **T3.12 Publish handoff (Gate 4):** go/hold + timing. Schedule sets publish_scheduled_at and transitions to 'published'. Non-approved assets can't be scheduled. Hard rule: no auto-publish.
- **Create surface:** dashboard at /create showing pipeline state (approved ideas, drafts in progress, shipped).
- **Templates:** draft.html (full draft display + feedback + gate), assets.html (per-platform grid), publish.html (go/hold + scheduling), create.html (pipeline overview).
- 28 new tests (310 total).

**Rationale:** M3 BUILD_PLAN T3.5–T3.12 — the full staged pipeline from approved idea to publishable asset. The co-production loop is now complete: Ideas → Draft → Assets → Publish, with all four gates operational, origin/format/scope threaded end-to-end, series spawning and experimental format debut working. No hardcoded business values — all from config and modules.

---

### 2026-07-02 BUILD T3.1–T3.3 — Idea cards, Ideas gate, awaiting-capture
**What:** 2 prompt templates (per-item indexing + style guide analysis), VISUAL_STYLE_SCHEMA (palette with hex codes, typography feel, stylization level, blend rules with real/generated/disclosure split, platform adjustments), SHOT_LIBRARY_ITEM_SCHEMA (description, tags, mood, best_for, platforms), 2 markdown converters, 5 API endpoints including per-item LLM indexing of shot library items, HTML intake page with palette swatches and shot library display. Gate-enforced write writes both visual-style and shot-library modules. 23 new tests (240 total).
**Rationale:** M2 BUILD_PLAN T2.4 — the visual identity module and shot library that feed the drafter's visual direction blocks. Blend rules enforce the charter principle: real footage anchors trust, generated is supporting.

---

### 2026-07-02 BUILD R15 — Gate step derived from parsed playbook, not hardcoded
**What:** PlaybookParser now handles numbered-list procedure format (N. Description) in addition to ### Step N format. Added get_gate_step_number() to PlaybookRunner. All 7 store endpoints (voice, business, sources, viral-patterns, audience-insights, story-frameworks, format-guide) now derive the gate step from the parsed playbook instead of hardcoded strings. create_app() defaults to absolute playbooks path so CWD changes don't break file resolution. 16 new tests (217 total).
**Rationale:** R15 correction — hardcoded gate step strings are fragile. If a playbook's procedure changes (step renumbered), the store endpoint would record the gate result on the wrong step. Deriving from the playbook makes the system self-correcting.

---

### 2026-07-02 BUILD T2.3 — Viral Patterns + Audience Insights + Story Frameworks + Format Guide playbooks
**What:** 4 playbooks fully wired with prompt templates, JSON schemas, markdown converters, API endpoints (input + analyze + store), and HTML intake pages. Format Guide schema includes AMENDMENT-004 enrichment: `requires_human_capture`, `capture_tasks`, `effort_level`, `best_for`, `platforms`, `reuse_pathways`, `status` (proven|experimental|retired), `provenance`. All 4 store endpoints enforce gate tokens (T2.9). 47 new tests (201 total).
**Rationale:** M2 BUILD_PLAN T2.3 — the remaining onboarding playbooks that feed the co-production loop. Format Guide enrichment enables the treatment block on idea cards (AMENDMENT-004).

---

### 2026-07-02 BUILD T2.9 — Gate-token enforcement on all write paths
**What:** ModuleStore.store(), business.yaml writes, and sources.yaml writes now require a verified gate token from an approved run. No more honor-system writes. Orphan prevention: "unknown" or empty business slug raises immediately. 12 new tests (154 total at that point).
**Rationale:** R13 correction — pull gate enforcement forward before building more store endpoints, so enforcement is baked in from the start rather than retrofitted.

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

### 2026-07-02 STRATEGIC — Audio transcription + voice cloning (DIVERGENCE-003)
**Rationale:** Daimon directed: implement audio transcription in M2 (resolving R6), AND add open-source voice cloning so content audio (reel voiceovers, X audio posts) is produced in the person's own voice. DIVERGENCE-003 filed with full rationale. Transcription: faster-whisper (CTranslate2, int8, CPU — our VPS has no GPU), model in config. Voice cloning: Apache 2.0 models only (commercially safe for paying customers). Qwen3-TTS primary candidate (3-second zero-shot cloning, 1.7B params). XTTS-v2/Coqui explicitly ruled out (CPML non-commercial license, Coqui org shut down). No cloud TTS APIs — self-hosted only, same data-sovereignty principle. Three new M2 tasks added: T2.6 (transcription), T2.7 (voice cloning adapter), T2.8 (voice sample management). R7–R9 also added as T2.9–T2.11.

### 2026-07-02 OPS — Repo visibility decision (R10)
**Rationale:** Architect flagged that the GitHub repo is public while PROGRESS.md said "(private)." Daimon confirmed PUBLIC is deliberate — the architect (Claude) needs to read the repo without auth. PROGRESS.md corrected. Console auth: the Flask console has no authentication in M0–M2; deployment posture documented in CONTEXT.md (bind to localhost/VPN or add auth before operator end-to-end test).

### 2026-07-02 FIX — Review-M2-midpoint corrections R10–R16 applied
**Rationale:** Architect interim review of T2.1–T2.2 identified blocking and non-blocking defects. All applied:
- **R10:** Repo visibility decision recorded (public, deliberate); console auth posture documented in CONTEXT.md.
- **R11:** v2 bulk-import enable switch moved from client-controlled request param to server-side env var `V2_IMPORT_ENABLED`; glob fix (select newest backup by mtime); truncation reporting (COUNT + paginated fetch, `truncated: true` + `total_available`). 3 new tests.
- **R12:** Tenant strings genericized in `src/templates/business_profile.html` (placeholders), `src/templates/sources_engine.html` ("a previous pipeline backup"), `prompts/sources_engine/analyze_v1.md` (parameterized `{business_region}`), `prompts/voice_profile/analyze_v1.md` ("e.g. regional dialects"). Zero-tenant-strings test extended to templates + prompts. 3 new tests.
- **R13:** BUILD_PLAN M2 reordered — T2.9 (gate-token enforcement) pulled forward before T2.3, scope expanded to cover ModuleStore.store() + both config-yaml write paths + all playbook store endpoints.
- **R14:** Config yaml writes now archive before overwrite (`config/archive/{name}-{timestamp}.yaml`). 3 new tests.
- **R15:** Queued (derive gate step from parsed playbook, land during M2).
- **R16:** Binding constraint on T2.6–T2.8: VPS audio resource plan (never hold both models in memory, synthesis as background job, smoke-test Qwen3-TTS on VPS first, T2.7 AC amended with batch-window requirement).
- 142 tests passing (133 + 9 new).

### 2026-07-02 STRUCTURE — Inbox batch B filed + AMENDMENT-004 PROPOSED (awaiting operator)
**Rationale:** Second inbox batch filed per Inbox Protocol. REVIEW-M2-MIDPOINT → `docs/reviews/`; AMENDMENT-004 (treatment block on idea cards) → `docs/decisions/` with status PROPOSED — filed but NOT applied. GitHub issue opened for operator approval. Existing reviews moved into `docs/reviews/`. Manifest → `docs/inbox/processed/`.

### 2026-07-02 STRATEGIC — Charter bumped to v3.3 (AMENDMENT-004: treatment block on idea cards)
**Rationale:** Daimon approved AMENDMENT-004. Charter v3.2 → v3.3. Idea cards now carry a **treatment** (scope, format from Format Guide, capture-required tasks, reuse links, rationale) approved WITH the idea at Gate 1 — not developed after. Format experimentation mechanism: new formats debut inside treatments, one approval admits the format to the guide. Awaiting-capture state for cards with outstanding capture tasks. Provenance requirement expanded: `format` and `scope` travel alongside `origin` to the nightly note. Charter renamed from `CHARTER-v3.2.md` to `CHARTER-v3.3.md`; all references updated. CONTEXT.md: idea-card + treatment + origin definitions updated. BUILD_PLAN M3 expanded to 12 tasks (treatment block, awaiting-capture, series spawning, experimental-format debut, format+scope threading). T2.3 Format Guide schema enrichment noted. GitHub issue #1 closed.

### 2026-07-02 BUILD — T2.5 + T2.10 + T2.11 + R15 applied; 254 tests; deployment live
**Rationale:** T2.5 (module store schema-check on load + version history visible in console), T2.10 (security fixes: materials column allowlist + llm_adapter single-pass substitution), T2.11 (provenance business_slug column + threading), R15 (gate step derivation from parsed playbook) all landed. 254 tests passing. Deployed to VPS: gunicorn + systemd + Traefik reverse proxy. Basicauth middleware on public route (per architect R10 posture). Tailscale URL (http://100.96.184.48:9121) is the approved operator review URL.

### 2026-07-02 INBOX — Batch C filed (diagram v3.3 + ops flags)
**Rationale:** Third inbox batch from architect. `system-overview-v3.3.svg` → `docs/diagrams/` (v3.2 left in place, superseded). `diagrams-README_2.md` → `docs/diagrams/README.md` (REPLACE). Manifest → `docs/inbox/processed/`. APPLY: (1) CONTEXT.md diagram pointer updated v3.2 → v3.3 with new flow (Gather → Ideas+Treatment → Awaiting-Capture → Draft → Assets → Publish → Learn). (2) BLOCKING OPS: no public DNS until Traefik basicauth — basicauth middleware added via usersFile approach, tested 401 without auth + 200 with auth. Deployment artifacts committed to `deploy/` (traefik config, systemd service, env example). (3) T2.6–T2.8 deferral recorded formally in BUILD_PLAN + PROGRESS.md — review-w2 must NOT be tagged until audio/voice tasks land. (4) Tailscale URL confirmed as operator review URL.
---

### 2026-07-03 TECH/FIX/LOGIC — CORRECTION-orchestrator-drafting-and-ux-v1.0 fully implemented

**What:**
- **P0-1 (FIX):** Drafting input starvation root cause — routed_seeds persisted, per-doc drafting package (seeds + transcript + 24k materials), 8 v2 prompts, shot_library_summary from real materials, unresolved-placeholder check in _render_prompt.
- **P0-2 (FIX):** Validation crash on next_focus null — removed from required, validator coerces None→"", retry includes actual error text, friendly operator error copy.
- **P1-1 (STRUCTURE):** Gate relocation to Library — ModuleStore.store gains status param, draft/approved badges, inline edit, approve action with gate token, drafts stored immediately on orchestration.
- **P1-2 (FIX):** Conversation continuity — structured conversation_turns passed to template, full history rendered on page load, "← Console" back link, auto-save notice, gate cards replaced with draft acknowledgments linking to /library.
- **P1-3 (FIX):** Readback rendering — no raw str(dict)[:60], unknown dicts render key:value untruncated, empty sections omitted, nested dicts handled.
- **P1-4 (FIX):** Upload feedback — immediate "uploading…" chip with spinner, error chip with retry on failure, failed uploads never added to pendingFiles.
- **P2-1 (OPS):** Conversational latency — active.converse backend role (ollama_gpt_oss_120b), adapter falls back to default if not configured.
- **P2-2 (LOGIC):** Orchestrator prompt v2 — agency-intake posture, one-line doc definitions, mine materials before asking, aggressive verbatim seed extraction, never end without question.
- **Transcription (TECH):** faster-whisper background daemon, transcription_status column (additive migration), backfill on startup, get_corpus excludes pending/failed audio, wired into create_app.

**Rationale:** CORRECTION-orchestrator-drafting-and-ux-v1.0.md from architect review of commit 372f81e following operator's first end-to-end onboarding run. All thin/empty documents shared one root cause (P0-1) — fixed first. Definition of Done (PROCESS-definition-of-done-v1.0.md) now binding.

**Test suite:** 375 passing (18 new regression tests). Service restarted, health OK.

---

### 2026-07-03 OPS — Inbox batch -c + -d filed (pipeline UX, voice cloning, final assembly)

**What:** Two manifests (-c, -d) delivering 5 files filed per instructions:
- `CORRECTION-pipeline-ux-and-media-generation-v1.0.md` → `docs/reviews/`
- `DECISION-voice-cloning-vo-v1.0.md` → `docs/decisions/`
- `CORRECTION-final-assembly-and-materials-editing-v1.0.md` → `docs/reviews/`
- Manifests -c and -d → `docs/inbox/processed/`

**Scope of the batch (build order per manifest -c note 1):**
1. Pipeline UX: shared `static/busy.js` + server-side `jobs` table with in-flight idempotency (F1). Self-audit flags become actionable with Apply/Dismiss (F2). Visual direction required in DRAFT_SCHEMA with minItems:1 and prompt v2 (F3). Media generation via OpenRouter — `src/media_adapter.py`, config in `models.yaml`, `asset_media` table (F4). Assets page becomes publish-preview card with platform framing (F5).
2. Voice cloning: Chatterbox (MIT, self-hosted), voice reference set as 9th onboarding coverage item, `voices` table, VO generation as async job on shared `jobs` framework. Operator listening test is the one non-self-certifiable gate.
3. Final assembly engine: LLM produces Edit Plan (JSON schema) → deterministic FFmpeg/MoviePy v2 renderer. Stock library via Pexels/Pixabay. Editable Materials Library (`/materials`, normalize-content editing, exclude toggle). Whisper gains word-timestamp alignment mode.

**New dependencies (noted for deployment):** `OPENROUTER_API_KEY`, `PEXELS_API_KEY`, `PIXABAY_API_KEY` env vars; pip `chatterbox-tts`, `moviepy` v2; apt `ffmpeg`. RAM budget: Whisper medium + Chatterbox may not co-reside on VPS — measure, decide, record.

**Build order:** Materials Library (Part 2, independent) → jobs table + busy states (F1, shared infra) → Whisper worker (already built, gains alignment mode) → gate/continuity fixes already done → F2/F3 → F4/F5 media + preview → voice reference set + Chatterbox VO → assembly engine (last, depends on all). Two operator-eared gates: cloned-voice listening test, publish-preview "does this look like a post" judgment.

**Rationale:** Architect batch following operator's second hands-on review round. Filed before any new milestone work per inbox protocol. No charter conflicts identified.

---

### 2026-07-03 BUILD — Materials Library (CORRECTION-final-assembly Part 2)

**What:**
- DB migrations: `excluded` INTEGER column on `materials` + `material_edits` table (material_id, edited_at, before_hash). Additive, backward-compatible.
- `MaterialsIntake.save_edit()` — writes to `normalized_content` only, logs before-hash to `material_edits`, recomputes `word_count`. `raw_content` is never touched.
- `MaterialsIntake.restore_to_raw()` — re-copies `raw_content` → `normalized_content`, logged as an edit.
- `MaterialsIntake.toggle_exclude()` — sets `excluded` flag; `get_corpus()` skips excluded materials. Excluded ≠ deleted.
- Flask routes: `GET /materials` (list with run/channel filters), `GET /materials/<id>` (detail), `POST /api/materials/<id>/edit`, `/exclude`, `/restore`.
- Templates: `materials.html` (list with excerpts, excluded badges, filters), `material_detail.html` (editable textarea, raw read-only section, exclude/restore buttons, edit history), `error.html`.
- Nav: Materials link added to `index.html` and `library.html`.
- 19 new tests (394 total). Live server verified via curl: edit, restore, exclude all work against real data.

**Rationale:** CORRECTION-final-assembly-and-materials-editing-v1.0 Part 2. Everything the operator shared is reviewable and editable. Transcripts contain errors; extraction picks up junk; an uncorrected transcription error becomes a "voice pattern." The content-hash cache means an edited material naturally changes the variables hash on the next drafting call — no cache invalidation machinery needed. Built first per manifest -c note 1 (independent, small, operator needs it to correct transcripts as soon as Whisper lands).

### 2026-07-09 REVIEW — Video generation → assembly handoff audit

**Rationale:** Operator requested full audit of the video generation → local media → edit plan → FFmpeg assembly path. Architect verified all claims against live code, DB, and rendered files.

**What:** Filed `docs/reviews/REVIEW-video-generation-handoff-2026-07-09.md` (review) and `docs/inbox/CORRECTION-video-generation-handoff-v1.0.md` (6 corrective tasks via `MANIFEST-2026-07-09-video-handoff.md`).

**Findings:** 5 P0 blocking bugs (generate-clip reads wrong key + never downloads; generate-media submits and walks away; Google/Veo has 5 independent bugs: aspect ratio, response parsing, download API key, env var, duration hardcode), 2 P1 defects (0-byte render files, duration override), 2 P2 deficiencies (VO placeholder, render limits). `asset_media` has 0 rows — no AI-generated video has ever reached the assembler. The FFmpeg stitcher itself is solid and produces valid MP4s. The edit-plan prompt is conceptually right. The failure is entirely in the execution layer between "submit job" and "local file registered as ingredient."

**Correction tasks:** VH-1 (fix generate-clip), VH-2 (fix generate-media poll/download/register), VH-3 (fix Google/Veo 5 bugs), VH-4 (0-byte cleanup + size validation), VH-5 (duration from plan_item), VH-6 (document render limits in CONTEXT.md). Blocking — builder must apply before new milestone work.

