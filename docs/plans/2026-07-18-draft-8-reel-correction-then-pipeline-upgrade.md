# Draft 8 Reel Correction, Then Pipeline Upgrade — Implementation Plan

> **For Hermes:** Execute the artifact correction with operator review after each creative gate. Promote only operator-approved and verified learnings into reusable pipeline code.

**Goal:** Produce a publishable director’s cut of Draft 8, prove its quality against the exact VO and marketing contract, then upgrade ViralFactory so future Reels inherit the proven improvements and cannot false-green the defects found here.

**Architecture:** Work in two deliberately separated tracks. Track A creates a versioned correction of one artifact without overwriting the baseline. Track B extracts shared services and gates only after Daimon approves the corrected artifact. Measured VO remains the master clock; accurate text remains renderer-owned; paid acquisition remains cost-gated.

**Tech stack:** Python 3.12, Flask, SQLite, FFmpeg/ffprobe, existing `AssemblyRenderer`, `reel_production`, `AssetReviewer`, PIL/numpy, optional local faster-whisper or another approved aligner, configured media providers through existing adapters.

**Living evidence:** `docs/reviews/2026-07-18-draft-8-reel-correction-ledger.md`

---

## Non-negotiable execution rules

1. Do not rewrite the approved VO during assembly.
2. Do not overwrite `data/media/6/final_1.mp4`; every correction receives a new version and media row.
3. Do not incur image, video, music, transcription, or LLM API spend without displaying and receiving explicit approval for the fresh estimate.
4. Do not label generated media as real capture.
5. Do not treat a skipped review as a pass.
6. Do not promote a one-off treatment into the reusable pipeline until the operator approves the corrected Reel.
7. Update the living ledger after every review round.
8. No commit or push unless Daimon explicitly requests it.

---

# Track A — Correct Draft 8 first

## Phase A0 — Lock baseline and creative ruling

### Task A0.1: Preserve the baseline evidence

**Objective:** Make the existing artifact and assessment reproducible.

**Files:**
- Keep: `data/media/6/final_1.mp4`
- Update: `docs/reviews/2026-07-18-draft-8-reel-correction-ledger.md`
- Create during execution: `data/media/6/correction/manifest.json`

**Steps:**

1. Record SHA-256, ffprobe JSON, integrated loudness, true peak, scene-change timestamps, and frame-contact sheets.
2. Export the exact Draft 8 posts, VO segment metadata, source media rows, edit plan, and compliance contract into the correction manifest.
3. Record the current Git diff separately; do not mix baseline preservation with pipeline changes.
4. Verify the manifest points to existing files and exact database IDs.

**Acceptance:** Another reviewer can identify the exact baseline by hash and reconstruct why it failed.

### Task A0.2: Operator chooses the presentation model

**Objective:** Resolve the creative direction before sourcing or editing.

**Recommended ruling:** **Real-footage-led editorial visual essay.** Use VO as narration; do not pretend generated/stock subjects are speaking it.

**Alternative:** Openly stylized generated editorial essay, with no fake talking heads and clear AI disclosure.

**Decision also required:**

- Preserve the exact 72.066s VO for the first director’s cut (recommended), or return to Writer for a shorter approved VO.
- Voice-only versus a restrained licensed music bed.
- Whether real operator-provided couple/domestic footage is available; otherwise source licensed stock.

**Acceptance:** The ledger records an explicit operator ruling on treatment, duration, and audio bed.

---

## Phase A1 — Build a semantic storyboard

### Task A1.1: Convert six broad beats into visual events

**Objective:** Give every meaningful phrase a visual job without enforcing an arbitrary cut cadence.

**Files:**
- Create: `data/media/6/correction/storyboard_v1.json`
- Update: `docs/reviews/2026-07-18-draft-8-reel-correction-ledger.md`

**Provisional visual-event map:**

#### b01 HOOK — 0.00–9.72s

1. Couple connection/love establishes relationship context.
2. Saver behavior: transfer, envelope, account, or deliberate restraint.
3. Enjoy-today behavior: social/lifestyle spending with no caricature.
4. Renderer emphasis: **Two people. Two money codes.**

#### b02 SETUP — 9.72–22.04s

1. Couple discussing future together.
2. Visual progression: children → values/religion → home/location.
3. Deliberate pause/reframe.
4. Renderer question card: **What did your family teach you about money?**

#### b03 BUILD — 22.04–36.72s

1. Family/inheritance context—not fake documentary evidence.
2. Sequential card: **Save everything.**
3. Sequential card: **Property is the only real wealth.**
4. Sequential card: **Enjoy today.**
5. Header/reframe: **The money code you inherited.**

#### b04 TURN — 36.72–49.44s

1. Credit-card statement or phone transaction establishes the symptom.
2. Couple conflict footage establishes consequence.
3. Graphic separation: **The bill** versus **the money codes underneath it**.
4. Renderer emphasis: **The argument isn’t about the bill.**

#### b05 PAYOFF — 49.44–63.72s

1. Couple deliberately reviewing two family histories/assumptions.
2. Two-column graphic resolves into a shared plan.
3. Renderer emphasis: **Love doesn’t build wealth. Alignment does.**
4. Practical action is visible: name, compare, align.

#### b06 CLOSE — 63.72–72.07s

1. Calm shared-planning image/footage.
2. Saveable conversation prompt—not merely another portrait.
3. CTA: **Save this. Have the conversation.**
4. Restrained StackPenni end treatment.

**Acceptance:** Each event states its narrative function, source policy, exact time range, and required audience-visible text. No event exists merely to “keep motion going.”

### Task A1.2: Review storyboard with operator

**Objective:** Get human approval before media acquisition or rendering.

**Steps:**

1. Present the storyboard as a plain-language numbered checklist.
2. Show what is real/licensed/generated/renderer-drawn.
3. Flag any cultural-authenticity concern.
4. Revise until Daimon approves.
5. Log approval and revisions in the ledger.

**Acceptance:** Operator approves visual meaning, not merely file availability.

---

## Phase A2 — Source and approve ingredients

### Task A2.1: Inventory existing usable media

**Objective:** Reuse only assets that actually serve the approved storyboard.

**Sources to inspect:**

- `data/media/6/` current stills and clips
- `data/media/31/image_fe65cb9eea05623a.png`
- approved reference assets under `data/media/reference/stackpenni/`
- registered stock/cache inventory
- operator-provided real capture

**Rules:**

- Current generated presenter clips are not automatically reusable.
- The generated couple still may support an openly stylized treatment but cannot be labeled real capture.
- A stock clip must be culturally plausible and semantically specific; generic beach footage is insufficient for alignment.

**Acceptance:** Ingredient table has stable IDs, paths, provenance, permission, source type, beat/event linkage, and operator status.

### Task A2.2: Estimate missing media

**Objective:** Provide choices and exact cost before acquisition.

**Steps:**

1. Search approved/free/licensed inventory before generation.
2. For each missing event, propose at least one feasible treatment.
3. Calculate exact provider calls, durations, and cost.
4. Separate no-spend stock/reuse, low-cost still generation, and paid motion options.
5. Ask for explicit approval of the exact total.

**Acceptance:** Zero paid submissions occur before approval; estimate is fresh and retry-safe.

### Task A2.3: Acquire and gate ingredients

**Objective:** Approve visual ingredients before assembly.

**Steps:**

1. Submit approved acquisition jobs through provider-aware services.
2. Persist external IDs immediately.
3. Download and register returned media with stable event/beat IDs.
4. Run mechanical and visual ingredient checks.
5. Present fullscreen/contact-sheet review to operator.
6. Regenerate or replace rejected ingredients only after a revised cost estimate.

**Acceptance:** Every storyboard event has approved, resolvable media before edit compilation.

---

## Phase A3 — Build correction-specific caption and graphic tracks

### Task A3.1: Produce phrase-level timed captions

**Objective:** Replace clipped full-beat sentences with readable, timed phrases.

**Files:**
- Create: `data/media/6/correction/captions_v1.json`
- Reuse carefully: `src/episode_plan.py:392-457` chunking concepts

**Steps:**

1. Start from exact approved VO text and existing per-beat audio boundaries.
2. Create phrase chunks at punctuation and semantic boundaries, normally 3–6 words; avoid dangling fragments.
3. Use word timestamps from an approved local aligner where available; otherwise use beat audio evidence and manually verify the one-off correction.
4. Keep captions inside Instagram safe zones.
5. Never allow captions to cross a semantic cut incorrectly.
6. Verify reconstructed caption text exactly matches approved VO after punctuation normalization.

**Acceptance:** Every phrase is readable by itself, timed to speech, fully visible, and exact.

### Task A3.2: Design StackPenni text system for this Reel

**Objective:** Establish clear hierarchy among captions, emphasis, information cards, and CTA.

**Treatment:**

- Captions: high-contrast mobile sans serif, phrase-level, lower safe area, restrained emphasis.
- Editorial cards: cream ground, deep-ocean teal text, prosperity-gold accent; coral only for deliberate contrast.
- Emphasis overlays: short, single-purpose, not permanently present.
- CTA: saveable and uncluttered.
- Accurate text remains deterministic renderer output.

**Acceptance:** Operator approves a representative hook frame, information card, reframe frame, and CTA frame before full render.

---

## Phase A4 — Compile and render the director’s cut

### Task A4.1: Compile a versioned correction edit plan

**Objective:** Build a source-resolved plan from approved media, timed captions, graphics, and exact VO.

**Files:**
- Create: `data/media/6/correction/edit_plan_v1.json`
- Do not modify the live database plan until operator approval of the correction plan.

**Rules:**

- VO is the master clock.
- Cuts follow semantic events and sentence/phrase boundaries.
- Still motion is allowed only when intentional and visually useful.
- No supposed speaker may freeze while continuing to “speak.”
- Transition choice must declare its job.
- The original `transition_in` intent is considered, but duration math remains exact.

**Acceptance:** Total visual/audio duration equals measured VO; every event and text intent resolves to real local ingredients.

### Task A4.2: Render without overwriting baseline

**Objective:** Produce `final_2` or a clearly named correction candidate.

**Output:**
- Candidate: `data/media/6/correction/final_candidate_v1.mp4`
- After approval: register as a new `final_cut` version; keep `final_1.mp4` intact.

**Audio target:**

- Measure with EBU R128.
- Provisional Instagram target: integrated loudness near -14 LUFS, true peak no higher than -1.0 to -1.5 dBTP; confirm against existing project standard before final render.
- VO remains dominant; music, if approved, is ducked and function-driven.

**Acceptance:** FFmpeg completes; expected streams, duration, resolution, frame rate, audio levels, and file size are verified.

---

## Phase A5 — Deep review and operator iteration

### Task A5.1: Run deterministic checks

**Objective:** Catch structural and text failures before AI/human review.

**Checks:**

- File/stream/duration/resolution/SAR.
- Integrated loudness, true peak, silence, and clipping.
- Transcript coverage against exact VO.
- Caption text reconstruction.
- Caption bounding boxes inside safe zones.
- Forbidden debug syntax OCR/pattern checks: `{`, `}`, `position`, `style`, `prompt`, JSON/dict fragments.
- Expected emphasis text presence.
- Beat/event visual coverage.
- Freeze/hold report with intentional-hold exemptions.

**Acceptance:** No blocking deterministic issue.

### Task A5.2: Run dense beat-aware visual review

**Objective:** Review the entire content progression rather than five generic timeline frames.

**Evidence:**

- First/middle/last frame per semantic event.
- Frames before/after every cut.
- Full beat contact sheets.
- Motion/freeze evidence.
- Script, storyboard, text intents, and source policy supplied to reviewer.

**Acceptance:** Reviewer identifies actual scenes and checks semantic alignment, text, artifacts, transitions, visual hierarchy, and landing. Missing evidence returns `needs_operator_decision`, never pass.

### Task A5.3: Operator review round

**Objective:** Daimon reviews the correction as a real Instagram viewer.

**Plain-language checklist:**

1. Does the first three seconds tell you what this is about?
2. Do the visuals make the two money codes visible?
3. Does every caption read naturally and remain fully visible?
4. Does the conflict section feel emotionally true rather than generic?
5. Does the payoff teach what alignment looks like?
6. Is the CTA worth saving?
7. Do any shots feel fake, culturally generic, or interchangeable?
8. Does sound feel intentional throughout?
9. Would you publish this under StackPenni’s name?

**Acceptance:** Operator explicitly approves or lists revisions. Update the living ledger after every round.

### Task A5.4: Register the approved director’s cut

**Objective:** Preserve provenance and make the approved version visible in ViralFactory.

**Steps:**

1. Copy/rename candidate to the next versioned final-cut path.
2. Register a new `asset_media` row with source plan/version notes.
3. Store all review evidence against the new media ID.
4. Leave old reviews attached only to the old media ID.
5. Verify the operator page shows the newest version without erasing history.

**Acceptance:** The page, database, and filesystem all resolve the same approved hash.

---

# Track B — Upgrade the reusable pipeline after approval

## Phase B0 — Promote only proven learnings

### Task B0.1: Ratify the correction learnings

**Objective:** Separate one-off creative choices from reusable system rules.

**Update:**
- `docs/reviews/2026-07-18-draft-8-reel-correction-ledger.md`

**Classify each learning as:**

- universal integrity rule;
- StackPenni module preference;
- format-specific affordance;
- experiment/hypothesis;
- one-off treatment.

**Acceptance:** Daimon approves the classification before runtime changes.

---

## Phase B1 — Normalize Writer frame intent correctly

### Task B1.1: Preserve structured `text_on_screen`

**Objective:** Stop flattening text, position, style, animation, and function into one string.

**Files:**
- Modify: `src/reel_production.py:39-66`
- Test: `tests/test_reel_production.py`

**TDD:**

1. Add a failing test with dict `text_on_screen` asserting exact text plus position/style/animation preservation.
2. Add legacy-string compatibility test.
3. Implement normalized `text_intent` output rather than only `overlay_text`.
4. Run targeted tests.

**Acceptance:** No dict repr can enter an edit plan; approved renderer metadata survives normalization.

### Task B1.2: Preserve visual and transition structure

**Objective:** Stop stringifying Writer visual dictionaries and ignoring transition intent.

**Files:**
- Modify: `src/reel_production.py`
- Test: `tests/test_reel_production.py`

**Acceptance:** Normalized beats retain semantic visual intent, transition request, text function, and source policy without provider-specific invention.

---

## Phase B2 — Replace five-second-motion-plus-still fallback with coverage planning

### Task B2.1: Introduce semantic visual events

**Objective:** Let the Media Planner provide multiple event-scoped ingredients per beat when the meaning changes.

**Files:**
- Modify: `src/reel_production.py:172-248`
- Modify schemas/prompts only after boundary review.
- Test: `tests/test_reel_production.py`

**Rules:**

- No universal number of events or cut cadence.
- A long beat may hold if performance/proof/information earns it.
- A supposed speaker cannot become a still while speech continues.
- Missing coverage fails closed rather than silently falling back.

**Acceptance:** A 14s beat can compile from several approved events; coverage exactly equals measured VO.

### Task B2.2: Add coverage and freeze-risk validation

**Objective:** Detect inadequate motion/performance coverage before render.

**Tests:**

- talking-head intent + shorter motion than speech → block or require explicit cutaway plan;
- deliberate text-card hold → permitted;
- missing event coverage → block;
- arbitrary still fallback → block.

---

## Phase B3 — Build a reusable caption service

### Task B3.1: Extract caption chunking from episode format

**Objective:** Avoid duplicate caption logic and support normal Reels.

**Files:**
- Create: `src/caption_timing.py`
- Modify: `src/episode_plan.py`
- Modify: `src/reel_production.py`
- Test: create `tests/test_caption_timing.py`

**Requirements:**

- punctuation/phrase-aware chunking;
- normally 3–6 words, without treating that range as inviolable;
- exact-text reconstruction;
- word-timestamp input when available;
- proportional fallback clearly labeled approximate;
- no dangling fragments;
- no cross-cut caption spill.

### Task B3.2: Add an alignment backend

**Objective:** Produce real caption timing evidence.

**Decision gate:** choose local faster-whisper/approved aligner versus configured external service. Current project venv lacks faster-whisper.

**Acceptance:** Caption timing source and confidence are persisted. Missing alignment cannot be described as word-synced.

---

## Phase B4 — Make renderer text safe and brand-capable

### Task B4.1: Implement wrapped text and safe zones

**Objective:** Ensure no audience text can run outside the frame.

**Files:**
- Modify: `src/assembly.py:618-797`
- Test: existing overlay tests plus new safe-zone tests

**Requirements:**

- configurable left/right/top/bottom safe margins;
- deterministic wrapping or `textfile=` rendering;
- defined `bottom-third` position;
- caption and emphasis roles rendered separately;
- style-preview frames cannot be reused as production graphic layers when they contain sample captions;
- the compiler reserves an exclusive caption lane and validates all active text-role bounding boxes for collisions;
- long text either wraps safely or fails validation;
- no unknown style silently falls back without a warning.

### Task B4.2: Move style presets to config/modules

**Objective:** Stop generic hardcoded styling from overriding StackPenni intent.

**Files:**
- Modify: `config/models.yaml` or approved renderer-style config
- Modify: `src/assembly.py`
- Test: renderer-style resolution tests

**Acceptance:** `caption`, `emphasis`, hook, proof, reframe, and CTA styles resolve explicitly. Brand values remain config/module-driven, not tenant strings in generic code.

### Task B4.3: Support timed text animations honestly

**Objective:** Implement only declared capabilities; do not claim word-by-word animation when renderer cannot execute it.

**Acceptance:** Unsupported animation is a visible planning warning or hard failure, not silently ignored.

---

## Phase B5 — Respect semantic transition intent

### Task B5.1: Compile transitions without breaking the VO clock

**Objective:** Use Writer/plan transition intent where feasible and budget overlap explicitly.

**Files:**
- Modify: `src/reel_production.py`
- Modify: `src/assembly.py` if needed
- Tests: transition duration, exact VO clock, unsupported transition behavior

**Acceptance:** Hard cuts, crossfades, and holds have explicit narrative jobs and mathematically correct duration.

---

## Phase B6 — Enforce capture/source policy

### Task B6.1: Distinguish source categories

**Objective:** Prevent AI-generated media from satisfying real-capture requirements.

**Files:**
- Modify material/capture ingestion and contract validation paths after tracing exact services.
- Tests: generated `capture_upload` cannot satisfy `capture_required=real`.

**Categories:**

- operator capture;
- licensed stock/archive;
- approved reference;
- generated still;
- generated motion;
- renderer graphic.

**Acceptance:** Source policy is explicit and machine-verifiable; labels cannot override provenance.

---

## Phase B7 — Fix post-render false green

### Task B7.1: Persist skipped/failed review evidence

**Objective:** Make absence of inspection visible.

**Files:**
- Modify: `src/asset_review.py`
- Modify: `src/app.py:7013-7089`
- Test: asset-review visual/alignment tests

**Acceptance:** Skipped vision/transcription creates a saved evidence row and cannot become “all checks passed.”

### Task B7.2: Require evidence completeness for readiness

**Objective:** Prevent `ready_for_operator` from meaning “we did not look.”

**Required evidence for VO-led Reels:**

- mechanical;
- audio signal and transcript coverage;
- visual inspection;
- exact text/OCR check;
- beat semantic coverage;
- alignment aggregation.

**Acceptance:** Missing required evidence yields `needs_operator_decision`, not pass.

### Task B7.3: Make visual inspection beat-aware

**Objective:** Replace five generic keyframes with event/beat-aware evidence.

**Files:**
- Modify: `src/asset_review.py:429-460` and review prompt
- Tests: every beat and cut gets evidence; short-lived defects are sampled

**Acceptance:** Review frame selection derives from plan timing and includes cut boundaries, not only percentages.

### Task B7.4: Add deterministic text-integrity review

**Objective:** Catch metadata leakage and clipped captions without relying solely on an LLM.

**Checks:**

- expected approved overlay text;
- forbidden debug/config tokens;
- safe-zone bounds;
- caption reconstruction;
- overlap/collision between text layers;
- baked preview-caption text in a production graphic layer.

**Acceptance:** Artifact A’s leaked `position/style` text and clipped captions fail automatically in a regression fixture.

---

## Phase B8 — Standardize audio delivery

### Task B8.1: Make loudness targets format-configured

**Objective:** Apply and verify a chosen Instagram Reel loudness target consistently.

**Files:**
- Modify: format/render config
- Reuse: `src/assembly.py` loudnorm support
- Tests: integrated loudness target selection and true-peak cap

**Acceptance:** Review reports LUFS and dBTP, not only mean/sample peak. VO-led Reel output meets configured target.

### Task B8.2: Preserve audio intent

**Objective:** Music, original sound, silence, and SFX follow an explicit approved soundtrack plan rather than disappearing silently.

**Required soundtrack-plan fields:**

- `mode`: `vo_only`, `music_bed`, `source_sound`, or an approved combination;
- approved `music_bed_ref` and source/licence provenance when music is used;
- bed start/end, loop or extension policy, fades, target gain, and VO-ducking envelope;
- semantic SFX cues with event ID, approved source/preset, timestamp, gain, and purpose;
- explicit rationale when `vo_only` or deliberate silence is selected;
- fresh cost estimate and operator gate before any paid music/SFX acquisition.

**Planning rule:** The LLM may judge emotional register and propose music/SFX intent through a prompt + schema. Python validates references, timing, licence metadata, gain bounds, and timeline coverage. Generic code must not infer genre or add random effects.

**Operator gate:** Preview the proposed bed and representative SFX separately and under the VO. The operator can approve, reject, replace, or explicitly approve VO-only delivery.

**Acceptance:** No automatic music to hide weak visuals; no unapproved looping bed; no silent fallback from an approved soundtrack to VO-only; no synthetic placeholder tone presented as finished sound design; VO intelligibility wins.

### Task B8.3: Add soundtrack completeness and mix review

**Objective:** Review whether the approved soundtrack is actually present, audible, licensed, synchronized, and subordinate to the VO.

**Required evidence:**

- expected versus rendered music/SFX source IDs;
- audible-signal windows for VO, bed, original sound, and every required SFX cue;
- integrated loudness, true peak, and VO-to-bed level relationship;
- clipping and unexpected-silence checks;
- event-aware listening points around SFX and music transitions;
- explicit `vo_only_approved` evidence when no bed/effects are intended.

**Acceptance:** A Reel cannot report audio complete merely because an AAC stream exists. Missing approved music/SFX fails; unapproved VO-only output yields `needs_operator_decision`.

---

## Phase B9 — End-to-end proof

### Task B9.1: Add Artifact A failure regression fixtures

**Objective:** Ensure the exact defect class cannot recur.

**Fixtures/tests must prove detection of:**

- dict metadata as audience text;
- long unwrapped captions;
- missing `bottom-third` mapping;
- still fallback after talking-head motion ends;
- skipped visual/transcript evidence false-green;
- missing required capture provenance.

### Task B9.2: Produce one real fresh Reel through the upgraded path

**Objective:** Prove the pipeline, not merely unit tests.

**Steps:**

1. Use an approved seed/draft and exact VO.
2. Stop at cost estimate; obtain approval.
3. Acquire approved media.
4. Render.
5. Run complete review evidence.
6. Conduct operator review.
7. Compare result with Draft 8 director’s-cut quality bar.

**Acceptance:** Working artifact, complete evidence, operator approval, and no false-green review.

### Task B9.3: Run verification

**Commands:**

- Targeted tests per task.
- Full suite: `.venv/bin/python -m pytest -q`.
- FFprobe/EBU R128/transcript/OCR/beat-frame checks on real artifact.
- Live server smoke test after any service restart.

**Acceptance:** Tests pass and real artifact evidence passes. Neither alone is sufficient.

---

# Execution sequence and gates

1. **Now:** obtain operator rulings in A0.2.
2. Approve semantic storyboard.
3. Inventory and estimate media.
4. Obtain explicit spend approval if required.
5. Acquire and approve ingredients.
6. Approve text/caption visual samples.
7. Render director’s cut.
8. Deep review and revise with operator.
9. Approve final artifact.
10. Ratify reusable learnings.
11. Implement Track B task-by-task with TDD.
12. Prove upgrade on a new real Reel.

The next action is not coding the full pipeline. It is the A0.2 operator ruling and A1 storyboard approval, because creative quality cannot be recovered by renderer parameters alone.
