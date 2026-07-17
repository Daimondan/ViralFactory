# Viral Content Production Playbook v1

**Purpose:** convert a source-grounded idea into a complete script, media recipe, renderable edit plan, and measurable learning record. This playbook is generic; tenant voice, audience, visual style, formats, and evidence come from living modules.

**Evidence source:** `docs/research/viral-content-meta-analysis-v2.md`.

## Operating principles

1. **Prompts carry procedure; modules carry beliefs.** Never hardcode tenant topics, voice, visual identity, or format routing in Python.
2. **Observed ≠ causal.** Label corpus observations, performance hypotheses, and house rules separately.
3. **One content contract.** Writer, media planner, assembler, renderer, and reviewer must refer to the same beat IDs.
4. **Hardcode mechanics; use LLMs for judgment.** Schemas, IDs, duration arithmetic, source existence, safe areas, and coverage are mechanical. Meaning, treatment, shot choice, and pacing are judgmental.
5. **The assembler does not rewrite approved copy.** If the script cannot fit, return to the operator; do not silently cut meaning.
6. **Every ingredient must be real and resolvable.** Planned/submitted/remote media is not render-ready.

## Phase 1 — Content brief

Before writing, define:

```yaml
content_contract:
  core_claim: "The one proposition this piece earns"
  audience_value: "What changes for the viewer"
  evidence_refs: ["source:14", "capture:22"]
  primary_emotional_job: "recognition|tension|relief|wonder|amusement|conviction|hope"
  primary_audience_action: "finish|share|save|comment|follow|click"
  format_name: "Approved Format Guide entry"
  platform: "Primary destination"
  authenticity_anchor: "real person, lived detail, original footage, receipt, or none"
  performance_hypothesis: "Why this treatment may serve the chosen action"
  evidence_label: "HYPOTHESIS"
```

Reject the brief if the claim, audience value, or evidence is vague.

## Phase 2 — Select a narrative pattern

The LLM chooses the pattern that fits the particular idea. It may use or propose:

### A. Proof-first explainer
`claim → receipt → mechanism → implication → move`

### B. Emotional reframe
`recognizable moment → interpretation → deeper meaning → quiet landing`

### C. Contrarian argument
`claim → conventional view → evidence/experience → boundary/nuance → verdict`

### D. Story
`cold open → context → pressure → choice → consequence → meaning`

### E. Practical list
`promise → items ordered by utility or surprise → synthesis`

### F. Reaction/dialogue
`source claim → precise reaction → context/evidence → own position → invitation`

### G. Candid moment
`real event → minimal orientation/reframe text → natural payoff`

### H. Curated excerpt
`strongest quote → source/context label → essential excerpt → landing`

No pattern is mandatory. A custom pattern must state why the existing patterns do not fit.

## Phase 3 — Writer output contract

The Writer produces exact approved language and semantic beat intent. It should not invent unavailable assets.

```yaml
beats:
  - beat_id: b01
    role: "hook|orientation|setup|proof|development|turn|payoff|close"
    required: true
    vo_text: "Exact words spoken"
    register: "plain|intimate|urgent|amused|reflective|authoritative"
    evidence_refs: ["source:14"]
    intended_duration_sec: {min: 2.0, max: 4.0}
    viewer_state_before: "What the viewer assumes/feels"
    viewer_state_after: "What changes after this beat"
    staged_action: "One sentence describing the meaningful action or visual event"
    text_intents:
      - function: "hook|orientation|caption|emphasis|proof|reframe|cta"
        text: "Exact overlay text"
        required: true
```

### Writer rules

- The opening must orient quickly; it need not shout.
- One beat = one semantic job.
- Include at least one grounded particular.
- Do not invent a statistic, quote, scene, screen, product, or testimonial.
- Write for natural speech, not caption fragments. Caption segmentation happens after measured VO.
- End when the meaning lands. A CTA is optional and must match the chosen audience action.
- Keep operator voice and cognitive frame upstream; do not “humanize” generic prose later.

## Phase 4 — Text-on-screen system

Each text element must declare a function. Allowed functions:

| Function | Purpose | Default treatment |
|---|---|---|
| hook | state tension/promise | large; 3–10 words; first meaningful beat |
| orientation | speaker/source/context | small stable label |
| caption | accessibility for speech | phrase-level, VO-synced, safe-zone aware |
| emphasis | isolate key phrase/number | brief highlight, not full duplicate caption |
| proof | identify receipt/source/date | exact and verifiable |
| reframe | change meaning of footage | one concise sentence; allow visual room |
| CTA | request a relevant action | final only when earned |

### Text rules

- Text is rendered by the overlay/caption system, not baked into generated images or video.
- Do not require an overlay on every segment.
- Avoid simultaneous title + captions + labels competing for the same zone.
- Never cover faces, hands performing the key action, evidence, product, or subtitles.
- Caption phrases should be readable at normal playback speed and remain long enough to read.
- Exact spelling, numbers, names, and citations are mechanical QA checks.

## Phase 5 — Media recipe

The Media Planner receives beats, measured VO durations, visual style, reference assets, linked captures, and available generators. For every beat it chooses media by **function**, not novelty.

```yaml
media_recipe:
  - beat_id: b01
    media_function: "proof|human_presence|context|demonstration|metaphor|texture|pace|breathing_room"
    source_policy: "capture_required|capture_preferred|archive_preferred|stock_allowed|generated_allowed|text_card"
    primary:
      kind: "upload|archive|stock|generated_video|generated_image|animation|text_card"
      ingredient_id: "upload:22 or null until acquired"
      subject: "What must be visible"
      action: "What must happen"
      shot: "size, angle, composition"
      movement: "subject/camera movement only when meaningful"
      duration_needed_sec: 3.4
      original_audio: true
    fallback:
      kind: "generated_image"
      reason: "Why fallback preserves meaning"
    continuity:
      character_ref: "optional registered token"
      location_ref: "optional registered token"
      grade_ref: "approved grade token"
    disclosure: "none|ai_assisted|ai_generated"
```

### Media selection order

1. **Required real evidence/capture** when authenticity, proof, identity, product, or lived action is central.
2. **Approved archive/reference media** when continuity or a known person/location matters.
3. **Stock** for generic context or texture that does not pretend to be evidence.
4. **Generated video/image/animation** for metaphor, impossible visualization, connective tissue, or deliberate art direction.
5. **Text card** when words are the visual and imagery would dilute the point.

### Generation prohibitions

Do not ask image/video models to render readable text, numbers, logos, branded interfaces, phone screens, charts requiring accuracy, or documentary evidence. Generate clean visual plates; the renderer owns text and graphics.

## Phase 6 — Audio recipe

Choose one primary audio mode:

```yaml
audio_recipe:
  mode: "vo_only|original_sound|vo_plus_original|vo_plus_music|music_only|intentional_silence"
  narrative_reason: "Why this mode serves the piece"
  voice:
    take_id: "registered take"
    intelligibility_priority: true
  original_audio:
    preserve: true
    reason: "proof, atmosphere, humor, or emotional texture"
  music:
    required: false
    ingredient_id: "stock:123"
    mood: "descriptive, not genre-only"
    energy_curve: "flat|build|drop|resolve"
    duck_under_voice: true
  silence_events:
    - beat_id: b05
      duration_sec: 0.8
      reason: "Let the reframe land"
  sfx:
    - beat_id: b02
      type: "hit|whoosh|pop|riser|custom"
      reason: "Motivated event only"
```

Audio rules:

- Voice intelligibility wins over music.
- Preserve meaningful original sound.
- Silence is authored, not a fallback for missing audio.
- Music must perform a named narrative function.
- SFX are optional. No blanket whoosh-per-caption policy.
- Loudness, peaks, clipping, sync, and silent-track presence are mechanical QA.

## Phase 7 — Edit plan

The Assembler maps real ingredient IDs to beat IDs. It must not invent sources or rewrite copy.

Per segment require:

- `segment_id` and `beat_ids`;
- exact `source` from inventory;
- source-relative `in`/`out`;
- timeline duration aligned to measured VO;
- overlay IDs and timings;
- transition type plus reason;
- audio contribution;
- coverage of every required beat.

Visual change cadence is chosen by meaning. A hold is valid when expression, proof, or silence needs time. A cut is valid when the semantic beat, evidence, perspective, or energy changes.

## Phase 8 — Pre-render gates

Mechanical gates:

- all required beats mapped;
- all sources local, registered, permitted, and probeable;
- every VO second has visual coverage or an intentional text/hold treatment;
- no out-point exceeds source duration;
- overlay timings fit segments;
- safe-area and collision checks pass;
- exact text/number/source labels match approved copy;
- audio mode is fully specified;
- target duration equals measured timeline within tolerance;
- generated-media disclosure present when policy requires it.

If any fail, return a structured blocker. Do not render a plausible substitute.

## Phase 9 — Post-render review

Run three layers:

1. **Mechanical:** probe streams, duration, resolution, frame rate, loudness, clipping, faststart, file integrity.
2. **Compliance:** transcript, captions, required visuals, and beat coverage match the approved contract.
3. **Creative:** hook clarity, pacing, visual relevance, hierarchy, readability, emotional landing, authenticity, and brand fit.

Creative review is advisory; compliance is blocking; operator remains the final publish gate.

## Phase 10 — Learning record

After publishing, store:

```yaml
performance_record:
  platform_post_id: "..."
  published_at: "..."
  metrics:
    views: {value: null, confidence: unknown, captured_at: null}
    likes: {value: null, confidence: unknown, captured_at: null}
    comments: {value: null, confidence: unknown, captured_at: null}
    shares: {value: null, confidence: unknown, captured_at: null}
    saves: {value: null, confidence: unknown, captured_at: null}
    average_watch_time: {value: null, confidence: unknown, captured_at: null}
    completion_rate: {value: null, confidence: unknown, captured_at: null}
  creative_fingerprint:
    format: "..."
    narrative_pattern: "..."
    hook_mechanism: "..."
    emotional_job: "..."
    primary_action: "..."
    text_functions: ["..."]
    audio_mode: "..."
    media_mix: ["capture", "archive", "generated"]
  operator_feedback:
    direct_edits: []
    keep: []
    change: []
  analysis:
    observed: []
    hypotheses: []
    proposed_module_change: null
```

Never update a living module from one post automatically. Aggregate evidence, compare with tenant baseline and matched formats, then propose an exact diff for operator approval.

## Current ViralFactory integration

The current system has useful foundations: frame objects, VO-master timing, route-based media planning and rendering, inventory validation, edit plans, compliance contracts, render review, remediation, and feedback storage. The corrected `viral-patterns` module is already loaded by ideation, drafting, series breakdown, and edit planning, so its evidence and production rules are active prompt context.

The production contract itself is **not yet fully automated end to end**:

1. `ProductionChain._step_media_plan`, `_step_media_exec`, `_step_edit_plan`, and `_step_render` are stubs. Equivalent behavior exists in Flask route handlers, but the autonomous chain does not execute it.
2. Frame `text_on_screen` values are not deterministically translated into timed edit-plan overlays.
3. Frame-level music/SFX intents and edit-plan audio cues use different shapes with no translation layer.
4. Overlay styles and SFX presets remain partly hardcoded in `assembly.py` rather than loaded from tenant configuration.
5. The approved reference-asset registry is not fully injected into media/edit planning or recorded per generation.
6. Post-publish performance ingestion and the Analyst learning loop do not yet exist.

### Implementation order

- **P0:** implement the four assembler-chain stubs by reusing the verified route behavior; preserve idempotency and provenance.
- **P0:** add deterministic beat/text/audio translation so approved Writer fields cannot disappear between draft and edit plan.
- **P0:** add pre-render source existence, source-bound, duration, stream, font, and overlay-safe-area checks.
- **P1:** move overlay/SFX style values into tenant/config modules and inject approved reference assets.
- **P1:** store post-publish metrics and creative fingerprints, then generate human-gated module proposals.

The target schemas should progressively add stable `beat_id`, `text_intents`, `media_function`, `source_policy`, audio rationale, and creative fingerprints. Until those changes land, encode them in existing fields without changing approved copy and do not claim that the autonomous assembler consumes the full contract.
