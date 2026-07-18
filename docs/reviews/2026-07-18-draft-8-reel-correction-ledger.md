# Draft 8 Reel — Assessment, Correction, and Pipeline Learning Ledger

**Status:** Living document — update after every operator review, correction render, and pipeline learning
**Started:** 2026-07-18
**Operator:** Daimon
**ViralFactory route:** `https://vf.glenbeu.com/create/assets/8`
**Draft ID:** 8
**Asset ID:** 6
**Idea card:** 31

## Purpose

This is the durable source of truth for correcting the Draft 8 money-scripts Reel and then upgrading the reusable ViralFactory pipeline from proven learnings. It separates observed evidence from external reports, hypotheses, operator rulings, implemented changes, and verified outcomes.

Do not silently overwrite earlier conclusions. Add dated updates to the decision and learning logs.

---

## 1. Artifact identity — resolve before editing

### Artifact A — current ViralFactory final cut

- Route HTML resolves Draft 8 to Asset 6.
- Current final-cut row: `asset_media.id=41`.
- Local production path: `data/media/6/final_1.mp4`.
- Route video reference: `/media/data/media/6/final_1.mp4`.
- SHA-256: `e7adba69a872bf10799e2b69f098421263ea7de626880c082809b6e70ccf224d`.
- Modified: `2026-07-18 03:02:40 UTC`.
- Duration: 72.066s.
- Resolution: 1080×1920 at 30fps.
- Audio: mono AAC, 96kHz.
- Size: 18,673,387 bytes.
- Measured volume: mean -18.0 dB, sample peak -0.1 dB.

This is the file directly inspected by Hermes. It contains generated male presenter shots, a static three-item money-scripts card, clipped full-beat captions, and leaked `text_on_screen` dictionary metadata across the center.

### Artifact B — Google Drive copy (resolved)

- User-provided source: `https://drive.google.com/file/d/1fxI302ijgfncHNm-1k10F4Wr_na5sDY9/view?usp=sharing`
- External AI report describes: wedding ceremony, couple over coffee, woman budgeting, couch argument, intergenerational coin jar, and couple at laptop; word-synced all-caps captions; peak around -11.5 dB; grade B-.
- After the sharing permission changed, the file downloaded successfully.
- Downloaded size: 18,673,387 bytes.
- Downloaded duration: 72.066s.
- Downloaded SHA-256: `e7adba69a872bf10799e2b69f098421263ea7de626880c082809b6e70ccf224d`.
- **Resolution:** Artifact B is byte-for-byte identical to Artifact A.

The external review is therefore not evidence about a different edit. It is a hallucinated/misidentified description of this exact artifact.

---

## 2. Evidence labels

- **OBSERVED:** directly inspected in the actual media or database.
- **MEASURED:** produced by ffprobe/FFmpeg/database queries.
- **EXTERNAL REPORT:** supplied by another reviewer but not yet independently verified.
- **HYPOTHESIS:** plausible explanation or improvement to test.
- **OPERATOR RULING:** decision approved by Daimon.
- **IMPLEMENTED:** changed in an artifact or pipeline.
- **VERIFIED:** exercised against a rendered artifact or passing test.

---

## 3. Current content contract

### Core claim

Caribbean couples can love each other while carrying incompatible inherited money beliefs; durable partnership requires making those beliefs explicit and aligning deliberately.

### Audience value

Make hidden family money conditioning visible and give couples a reason to discuss it before conflict hardens.

### Emotional movement

Recognition → curiosity → explanation → conflict reframe → practical resolution → save/share prompt.

### Primary audience action

Save the Reel and use it to start a financial-alignment conversation.

### Approved VO

- 185 words.
- 72.066s rendered duration.
- 154 words per minute.
- Six measured VO beats.
- VO is the master timeline.

### Capture requirement from the idea treatment

> Capture or source footage representing Caribbean couples and domestic life to anchor the script visually.

The recorded “capture” (`materials.id=262`) is itself AI-generated and points to `data/media/31/image_fe65cb9eea05623a.png`. It depicts a couple reviewing papers and a tablet in a domestic setting, but it is not real capture.

**OBSERVED integrity issue:** the production requirement called for capture or sourced couple/domestic footage, while the system accepted an AI-generated still as `capture_upload` and the final cut largely used unrelated generated presenters. This is not an honest satisfaction of the capture contract.

---

## 4. Artifact A assessment

### Overall grades

| Dimension | Grade | Notes |
|---|---:|---|
| Idea / positioning | 8/10 | Culturally particular relationship + finance insight |
| Script / narrative | 7.5/10 | Clear six-beat reframe; useful CTA |
| VO timing | 9/10 | Beat boundaries within 40–80ms of plan |
| Audio signal | 8/10 | Present and audible; sample peak too close to 0 dB |
| Visual-to-audio semantics | 4/10 | Mostly generic presenters; little direct depiction of claims |
| Performance continuity | 3/10 | ~5s motion followed by static fallback for 8–15s beats |
| Information design | 3/10 | One static list; no progressive teaching |
| Captions | 1/10 | Whole-beat lines clipped horizontally; not phrase-level |
| Emphasis text | 0/10 | Metadata rendered instead of approved copy |
| Transitions | 4/10 | Beat cuts function mechanically, not semantically |
| Brand / trust | 2/10 | Generated presenters + debug text undermine finance credibility |
| Publish readiness | 0/10 | Stop-ship |

**Current exported Artifact A:** 2.5/10, F / stop-ship.
**Underlying concept:** approximately 7.5/10.

### Audio synchronization — three separate findings

1. **Timeline sync — strong.** Detected VO beat boundaries are within 80ms of planned boundaries.
2. **Performance sync — weak.** Most beats receive about 5.04s of motion, followed by a still fallback while speech continues.
3. **Semantic sync — weak.** The visual often communicates tone but not the actual relationship, family, bill, alignment, or conversation being described.

### Beat audit

#### b01 HOOK — 0.00–9.72s

- VO establishes two Caribbean people with opposing money codes.
- Visual shows one generated male presenter.
- Initial face/hand movement exists, then falls into a still-like hold.
- No visible contrast between two people or two financial behaviors.
- Intended hook text is replaced by metadata.
- Bottom caption is clipped.

#### b02 SETUP — 9.72–22.04s

- VO lists children, religion, where to live, then the missing money conversation.
- Visual is one close-up generated man.
- No couple, wedding, family, home-planning sequence, or visual list progression.
- Motion is concentrated in the first ~5s; later VO continues over a static face.
- Intended question overlay is absent/broken; caption is clipped.

#### b03 BUILD — 22.04–36.72s

- Visual correctly lists “Save everything / Property is wealth / Enjoy today.”
- This is the only substantial information visualization.
- The card remains virtually unchanged for nearly 15s.
- Detected freeze from approximately 22.37–27.03s; visual remains essentially unchanged afterward.
- All items appear simultaneously rather than resolving with VO.
- No heading or visual grammar explains inheritance/family transmission.
- Metadata crosses the middle item; bottom caption competes and clips.

#### b04 TURN — 36.72–49.44s

- VO reframes a credit-card argument as conflicting money codes.
- Angry/intense generated presenter provides some emotional match.
- No couple, card, bill, statement, household, or symptom-versus-cause visualization.
- Motion again ends before VO.
- Critical reframe text is absent/broken.

#### b05 PAYOFF — 49.44–63.72s

- VO says love alone does not build wealth; alignment does; compare family scripts.
- Visual is a generated man at a tropical beach.
- Attractive but generic Caribbean lifestyle imagery; does not show alignment, partnership, or conversation.
- Essential payoff overlay is absent/broken.
- Motion becomes a static smiling portrait while guidance continues.

#### b06 CLOSE — 63.72–72.07s

- VO describes alignment as partnership infrastructure and asks for a save.
- Visual is an older generated man standing in a domestic setting.
- Does not show partnership, infrastructure, or a practical conversation prompt.
- CTA overlay is absent/broken.
- No designed landing or saveable framework.

### Transition and hold evidence

Detected visual changes occur near 9.7, 14.73, 22.0, 36.67, 49.4, 54.43, and 63.67 seconds. This is about seven detectable changes over 72s.

The problem is not failure to obey a universal cut-every-2–4-seconds rule. ViralFactory’s evidence standard rejects such a rule. The problem is that most holds do not earn their duration through evolving performance, proof, information, or emotion. They are consequences of a deterministic 5s motion clip followed by an image fallback.

---

## 5. External AI feedback — reconciliation

### Claims disproven for this artifact

The following external claims contradict measured/observed Artifact A evidence:

- six stock clips depicting wedding/coffee/budgeting/couch argument/coin jar/laptop;
- word-synced all-caps captions;
- safe-zone caption placement;
- audio peaking around -11.5 dB;
- six correct thematic assignments out of six;
- B- publish-quality assessment.

The Drive file and production file have the same SHA-256. These claims cannot accurately describe either copy and must not enter the correction specification as observed evidence.

### Useful hypotheses from the external review

Preserve these as hypotheses for either artifact:

1. Phrase boundaries should govern caption chunks.
2. Visual cuts should align to semantic/sentence changes where possible.
3. Caption styling should be an explicit StackPenni brand ruling, not an accidental generic TikTok default.
4. Long visual holds need evolving performance, information, reframing, or motivated motion.
5. Audio should be measured with integrated loudness and true peak, not judged only by sample peak.
6. A low-level music bed may help continuity only if it has a declared narrative job and does not compete with VO.

### External recommendation rejected as a universal rule

> “Visual change every 2–4 seconds.”

This may be a useful test treatment, but it is not supported as a universal causal rule by the admired-content corpus. A hold is valid when expression, proof, information, or silence earns it. The correction should use semantic visual events, not arbitrary cadence.

---

## 6. Comparison with the admired-content meta-analysis

### Aligned

- Immediate orientation: Caribbean people, love, conflicting money beliefs.
- Specificity in the script: saving, property, enjoy-today belief, credit-card bill.
- Genuine change in understanding: the bill is a symptom; inherited codes are the mechanism.
- Coherent primary action: save and start the conversation.

### Misaligned

- Human texture is simulated rather than credible or sustained.
- Visuals rarely do something the audio alone cannot do.
- Essential text functions fail in execution.
- The most particular human moment—the bill argument—is not concretely depicted in Artifact A.
- Generated imagery dominates a trust-sensitive financial message despite StackPenni’s visual-style rule that real footage should anchor Reels and trust-critical claims.
- Decorative generated presenters can be swapped between beats without changing meaning; therefore many visuals do not earn their place.

---

## 7. Root-cause map discovered so far

### Confirmed code/data causes

1. `src/reel_production.py:45` previously coerced a `text_on_screen` dict to a string. The dictionary representation became audience-visible overlay text.
2. `build_reel_plan()` maps a full beat’s VO text into one caption overlay for the entire beat; no phrase-level chunking/timing exists in this reel path.
3. `build_reel_plan()` opens each beat with one generated motion clip and deterministically fills all remaining VO time with the source image.
4. Every segment transition is forced to `cut`, ignoring Writer `transition_in` intent.
5. Overlay rendering in `src/assembly.py` centers unwrapped text using `x=(w-text_w)/2`; long lines run outside the canvas.
6. Style refs `caption` and `emphasis` are not defined in `_OVERLAY_STYLES`, so both fall back to generic `default` styling.
7. Position `bottom-third` is not defined by `_overlay_position_y`; unknown positions fall back to center.
8. The Writer requested caption animation and overlay styles, but the plan/renderer loses those instructions.
9. The idea treatment’s capture requirement can be satisfied by an AI-generated item labeled `capture_upload`.

### False-green review causes

1. Artifact A contains no saved visual review record.
2. The visual reviewer can return `skipped` when its key/model is unavailable.
3. Skipped visual inspection is not persisted as an explicit warning/evidence row.
4. Content alignment can return `ready_for_operator` when visual evidence is missing.
5. Five generic timeline keyframes are insufficient for beat-level coverage, transition checks, caption timing, or short-lived defects.
6. Mechanical review confirms structure, not marketing quality.
7. Audio review recorded “transcription unavailable,” yet alignment still reported ready.
8. The review layer did not OCR audience-visible text or detect leaked metadata/debug syntax.

---

## 8. Correction quality bar

The corrected Reel is not complete merely because FFmpeg succeeds. It must satisfy all of these:

### Content and visual storytelling

- Every beat has a declared visual job: human presence, context, contrast, proof, explanation, reframe, action, or landing.
- Visuals concretely depict the relationship/money mechanism rather than generic Caribbean decoration.
- Generated people are not presented as authentic documentary subjects.
- The piece uses real/licensed footage or an openly stylized VO-led essay treatment consistent with an operator ruling.
- Holds are intentional and earn their duration.

### Text and captions

- No metadata, prompt fragments, JSON/dict syntax, or technical labels appear.
- Exact approved emphasis text appears with its intended function.
- Captions are phrase-level, VO-synced, and fully inside platform safe zones.
- Caption and emphasis layers have clear hierarchy and do not compete.
- Accurate text is renderer-owned.
- StackPenni typography, teal/coral/gold/cream palette, and editorial treatment are visible without becoming a corporate template.

### Audio

- Exact approved VO is complete and intelligible.
- Transcript coverage matches ordered VO.
- Integrated loudness and true peak meet the selected Instagram delivery target.
- Music/SFX are optional and function-driven; VO remains dominant.
- Deliberate pauses remain deliberate.

### Editing

- Cuts land on semantic changes rather than arbitrary clip exhaustion.
- No motion-to-still performance collapse while a supposed speaker continues talking.
- Transitions communicate a change in meaning or emotional state.
- Ending visibly lands and makes the save action useful.

### Review evidence

- Mechanical, audio, visual, text/OCR, semantic alignment, and operator review are all present.
- Skipped required evidence cannot produce `ready_for_operator`.
- Fullscreen human review confirms captions, sound, pacing, transitions, and final landing.

---

## 9. Proposed correction direction — pending operator ruling

### Recommended treatment: real-footage-led editorial visual essay

Use one coherent VO narrator without pretending stock/generated subjects are speaking. Build the story from:

- licensed/approved Caribbean couple and domestic-life footage;
- concrete financial objects and actions;
- deterministic StackPenni cards/diagrams;
- restrained brand motifs;
- exact phrase-level captions;
- purposeful cuts and holds.

This is preferred over AI talking heads because it is more honest, more semantically flexible, and better aligned with StackPenni’s trust rules.

### Provisional beat treatment

1. **HOOK:** visible contrast between two partners’ money behaviors; split or matched actions establish two codes.
2. **SETUP:** couple discussing life choices; visual progression through children/home/values; missing money question lands as an editorial card.
3. **BUILD:** sequential three-script visualization tied to family/inheritance imagery; each belief resolves with VO.
4. **TURN:** concrete credit-card bill/statement conflict; visual reframe separates symptom (“the bill”) from cause (“different money codes”).
5. **PAYOFF:** couple places both money histories/values on the table and aligns around a shared plan.
6. **CLOSE:** saveable conversation prompt or compact framework, followed by a restrained StackPenni landing.

This is a direction, not authorization to rewrite approved VO or incur media spend.

---

## 10. Decision log

| Date | Decision | Status | Evidence / reason |
|---|---|---|---|
| 2026-07-18 | Preserve measured VO as master clock | Existing ruling | Exact beat sync is strong |
| 2026-07-18 | Current Artifact A is not publishable | Assessment | Metadata, clipped captions, weak visual semantics |
| 2026-07-18 | Reject external B- review as artifact evidence | Verified | Drive and production copies are byte-identical; the report invents nonexistent scenes/captions/audio measurements |
| 2026-07-18 | Correct one video with operator first; upgrade reusable pipeline second | User direction | Learn from a real approved artifact |
| 2026-07-18 | Canonical correction target is hash `e7adba69…ccf224d` | Verified | Drive and production copies are identical |
| 2026-07-18 | Use a real/licensed-footage-led editorial visual essay | Operator ruling | Highest-trust route; VO narrates rather than pretending sourced people speak |
| 2026-07-18 | Preserve the exact 72s approved VO for the director’s cut | Operator ruling | VO is sacred and remains the master clock |
| Pending | Music-bed ruling | Open | Must have narrative job and licensed source |

---

## 11. Learning log

### 2026-07-18 — Initial audit

- Route IDs must be resolved: `/create/assets/8` means Draft 8, not Asset 8.
- Structural sync can be excellent while marketing sync is poor.
- Five-second motion coverage per 8–15s beat creates performance collapse.
- Full-beat caption overlays cannot substitute for timed captions.
- Post-render visual evidence must fail closed when missing; “skipped” is not “clean.”
- Capture labels need source-policy enforcement, not naming conventions.
- External AI reports must be tied to an artifact hash before synthesis.
- A confident scene-by-scene AI report can be fully fabricated even when given the correct file; artifact hash identity plus direct frame/audio inspection is mandatory.

### 2026-07-18 — Correction direction and storyboard v1

- Operator selected a real/licensed-footage-led editorial visual essay and preserved the exact 72s VO.
- Baseline manifest saved at `data/media/6/correction/manifest.json`.
- Storyboard v1 saved at `data/media/6/correction/storyboard_v1.json` with 18 semantic visual events across six VO beats.
- The storyboard uses sourced human footage for relationship context and deterministic StackPenni graphics for exact financial concepts, reframes, and CTA.
- Timings are sentence-proportional estimates pending audio alignment; no claim of word-sync is made.

### 2026-07-18 — Licensed-footage inventory and source shortlist v1

- Storyboard v1 received operator approval.
- No cached stock or configured Pexels/Pixabay API credentials were available; candidates were discovered from public Pexels pages and downloaded through official free source URLs.
- Landscape financial-couple clips were rejected despite strong semantics because they used the wrong demographic for StackPenni and 9:16 crops removed one partner.
- Initial portrait setup clip `7226984` was rejected because one partner was mostly seen from behind and reciprocal conversation was weak.
- Selected no-cost shortlist:
  - `6574011` — portrait Black couple, warm domestic relationship opener;
  - `6574026` — same couple, seated reciprocal conversation for setup;
  - `8060562` — Black couple disagreement, correctly cropped from 4K landscape for TURN;
  - `5664557` — Black couple collaborating at laptop for PAYOFF/shared planning.
- Human footage is intentionally limited to moments where human texture matters. Saver/enjoy-today contrast, compatibility categories, inherited scripts, bill-vs-codes reframe, family comparison exercise, infrastructure metaphor, and CTA remain deterministic editorial graphics.
- Source preview: `data/media/6/correction/source_shortlist_v1.mp4` (12.0s, 1080×1920, 30fps).
- Provenance and rejection reasons: `data/media/6/correction/source_shortlist_v1.json`.
- Remaining limitation: selected people are culturally plausible for StackPenni but stock provenance cannot prove Caribbean identity; the edit must not claim that these actors are specifically Caribbean individuals.

### 2026-07-18 — Source approval and style frames v1

- Operator approved the four-source shortlist.
- Weak setup source `7226984` was replaced before approval with `6574026`, showing the same Black couple as the opener in a reciprocal seated conversation.
- Style frames created for hook, missing-question reveal, money-scripts explanation, bill reframe, and payoff/CTA.
- Initial internal style pass contained inferred explanatory lines and paraphrased caption samples; these were removed before operator presentation.
- Current frames use exact approved VO for audience-facing claims and captions.
- Style spec: `data/media/6/correction/style_spec_v1.json`.
- Contact sheet: `data/media/6/correction/style_frames_v1_contact.jpg`.
- Full-resolution frames: `data/media/6/correction/style_frames_v1/`.
- No paid media or API calls were used.

### 2026-07-18 — Director’s-cut render rounds v1 and v2

- Operator approved style frames v1.
- Edit plan compiled to 22 semantic events and 51 exact phrase captions across the preserved 72.12s VO.
- Caption text reconstructs all 190 approved VO words exactly after punctuation normalization.
- Candidate v1 internal audit found: low-contrast setup orientation, clipped home label, face-obscuring hook/planning/close overlays, long one-state BUILD definition, weak payoff crop, and CTA-brand/caption collision.
- All v1 defects were corrected before operator presentation.
- Candidate v2: `data/media/6/correction/final_candidate_v2.mp4`.
- Candidate v2 SHA-256: `3ca87adaefda305b4911d002e85018712ae1630c99468fd683aad116fcaf99f2`.
- Candidate v2 measures 1080×1920, 30fps, 72.10s, H.264/AAC mono 48kHz.
- Audio measures -15.3 LUFS integrated and -1.2 dBFS true peak; no clipping observed.
- No black frames or frozen talking-head fallbacks were detected. Freeze detections correspond to intentional information/question/reframe/CTA cards.
- Dense review covered all 22 event midpoints and six full-beat 1fps sheets.
- Candidate v2 status: ready for operator review; not registered as final.
- Review evidence: `data/media/6/correction/review_v2.json` and `data/media/6/correction/audit_v2/`.

### 2026-07-18 — Operator reaction to candidate v2

- Operator ruling: “pretty good” and suitable as the basis for pipeline upgrading.
- Direction and quality bar are conditionally approved.
- Candidate v2 is not yet final: operator reports a few minor tweaks still to be specified.
- Pipeline promotion may proceed at design/classification level, but the live final must not be replaced and the reusable visual treatment must not be declared fully ratified until the tweak round is reviewed.

### 2026-07-18 — Operator tweak: VO captions obscured underlying text

- Operator observed that the on-screen VO caption sometimes hid designed text underneath it.
- Root cause: production graphics `question_reveal` and `bill_reframe` were copied from style-preview frames that already contained sample caption pills; the live caption track was then composited over those baked samples.
- Correction rule: style-preview frames are review artifacts, not production layers. Production graphics must be caption-free; caption, emphasis, information, branding, and CTA remain separate renderer roles.
- The layout compiler must reserve an exclusive caption lane and reject bounding-box collisions before render.
- Candidate v3 will regenerate clean question/reframe graphics and move all non-caption content clear of the caption lane.
- Candidate v3 rendered at `data/media/6/correction/final_candidate_v3.mp4`; SHA-256 `f94c4ad44d94b4054b9cd267ee45b878239cbd012042ed3c35bf176c57aa172a`.
- Five affected events (question, bill reframe, payoff, family comparison, CTA) were re-reviewed at full detail and pass single-caption-layer/collision checks.
- Reserved caption lane: `(60,1450)–(960,1640)`; production graphics contain no sample captions; non-caption content ends above the lane.
- Mechanical recheck: 1080×1920, 30fps, 72.10s, audio present, mean -16.1 dB, max sample peak -1.3 dB, no black frames detected.
- Review evidence: `data/media/6/correction/review_v3.json` and `data/media/6/correction/audit_v3/caption_lane_fix_contact.jpg`.
- Public review proxy: `https://drive.google.com/file/d/1Wl6mGxBRYRMVZEhyHNkkqbrJcXgE6x5p/view?usp=sharing`.

### 2026-07-18 — v3 approved and registered

- Operator approved v3 as the visual standard.
- Approved master copied to `data/media/6/final_2.mp4`; baseline `final_1.mp4` remains intact.
- Registered as `asset_media.id=42`, linked to baseline media ID 41.
- Six evidence rows (mechanical, audio, visual, text integrity, alignment, compliance) are attached only to media ID 42.
- Live `/api/assets/6/render-status` resolves `final_2.mp4` with verdict `compliant` and the approved hash.
- Live `/create/assets/8` references `final_2.mp4` and does not reference `final_1.mp4`.
- Publication remains a separate operator action and is explicitly not approved by this registration.
- Full suite: 1,621 tests passed. The fresh post-registration run also exposed and fixed a pre-existing transcription-worker SQLite/thread lifecycle leak; four dedicated regressions prevent recurrence.

### 2026-07-18 — Soundtrack gap identified after approval

- Operator observed that the approved director’s cut has no music or sound effects.
- Confirmed: v3 is intentionally VO-only because no bed, licence/source, SFX design, cost, or soundtrack gate was approved during the correction.
- This is not yet fixed in the reusable pipeline. Existing renderer mechanics can mix planned audio, but Draft 8 received no explicit soundtrack plan and no completeness failure.
- Track B8 now requires an explicit soundtrack mode, approved music/SFX provenance, preview gate, VO ducking, semantic cue plan, and post-render evidence. VO-only is valid only when explicitly approved.
- Existing synthetic SFX tones are mechanics/placeholders and may not be presented as finished sound design without operator approval.
- Decision still open: whether to produce an audio-enhanced v4 of Draft 8 after soundtrack preview approval.

### Next update trigger

Update this ledger after every storyboard, ingredient, render, or operator review round. Record:

- artifact hash/version;
- operator feedback;
- what changed;
- what improved or regressed;
- newly discovered reusable pipeline rule;
- whether the rule is observed, hypothesized, approved, implemented, or verified.
