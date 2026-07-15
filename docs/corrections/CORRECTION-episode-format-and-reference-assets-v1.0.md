# CORRECTION — Episode Format, Reference Asset Registry, and Storyboard Gate — v1.0

**Date:** 2026-07-14
**Author:** Architect (Claude)
**Status:** Approved by operator (this session)
**Supersedes:** Nothing. Extends AMENDMENT-007 (Writer/Assembler boundary), AMENDMENT-008 (compliance contract + remediation loop), CORRECTION-generation-diversity-and-asset-continuity (S-series), and the media plan / edit plan prompt contracts in `prompts/assembly/`.
**Related:** `docs/research/viral-content-mechanics-2026-07-11.md` (this correction implements its Phase 4 — format templates — and closes the "missing engagement layers" finding at the format level rather than per-video).
**Priority:** P1 architecture. Section 5 (retire Sora) and Section 7.1 (Layer-1 lints) are P0/cheap and may land immediately.

---

## Operator intent driving this correction

1. Current videos are bad in a specific way: no style, no personality, no recurring visual elements or characters, no transitions/music/text-graphics system, images that don't match the narration. Posts look generated, not authored.
2. The target genre is the first-person AI parable (reference: Bob Invests–style reels): one recurring character, cinematic consistent grade, a story told beat by beat, every sentence matched by a staged shot of that character living that moment, 1–2 minute pieces breaking down small ideas.
3. The operator wants a consistent, high-quality, repeatable format — "an episode of a show," not "a video" — where the freshness comes from the story seed, never from format drift.
4. Everything must run fully automated through APIs behind the existing gates. No manual editing tools.

## Architect findings (live repo at 2026-07-14 + analysis of four rendered outputs)

- **F-A: No reference conditioning anywhere in the media path.** `prompts/assembly/media_plan_v1.md` asks the LLM for prose "style directives" per clip, and `media_adapter.generate_image` / `submit_video` accept only text prompts. Nothing passes reference images. Character and location consistency is therefore impossible by construction — the four uploaded outputs confirm it (four videos, four unrelated genres; the one accidental character in `final_1` drifts to off-palette silhouettes by the end).
- **F-B: The mush-image failure class is unguarded.** `final_1` contains an AI-rendered phone close-up with melted fake icons. No lint prevents generation prompts from requesting text, screens, logos, or devices — the categories current models reliably ruin. The renderer already has an overlay/caption system (`_burn_overlays`, `visual_style` module) that should own all on-screen text and numbers; nothing enforces that division.
- **F-C: VO-as-master-clock exists; beats do not.** `edit_plan_v1.md` correctly pins canvas duration to measured VO duration. But there is no beat structure: no schema unit tying one narration sentence to one staged shot with a role (hook/setup/struggle/turn/lesson/cta). The AMENDMENT-008 compliance contract has `beat_id` fields — but beats are reverse-engineered from finished scripts rather than authored as the script's structure. The format needs beats to be first-class from the Writer stage.
- **F-D: Cheap-to-expensive ordering is absent in media generation.** Video is generated directly from text prompts. There is no stills-first storyboard step, so the operator's first look at visuals is after the expensive spend, and rejected shots waste video-generation cost. This also conflicts in spirit with the no-surprise-spending principle: the current cost confirmation gates total spend but gives no ability to approve the *look* before paying for motion.
- **F-E: `models.yaml` media block is stale and thin.** Sora is listed as a generator (API discontinued 2026-09-24 — must not be built on). Grok is the default video provider. There is no aggregator provider, no image-to-video call shape (only text-to-video), and no per-second cost table to drive gate cost estimates deterministically.
- **F-F: Music has no system.** `music_source: pixabay` pulls arbitrary stock tracks per piece; measured loudness across the four outputs swings 10 dB (mean −15.3 to −25.5 dB). Loudnorm exists in the renderer (`_apply_loudnorm`) but there is no fixed target enforced per format, and no fixed set of beds, so every episode sounds like a different show.
- **F-G: Visual-style module conflict (must be resolved by gate, not silently).** `modules/stackpenni/visual-style.md` blend rules state real people require real footage and generated visuals never replace them, plus "Never present a generated visual as a real person." A recurring AI narrator character is a *fictional, disclosed persona* — a different thing from faking a real person — but introducing it is a module change and therefore must pass the module review gate with the operator's explicit approval (Section 1.4).

---

## Design ruling (one paragraph)

The harness gains one generic capability — **reference-conditioned, beat-structured episode production** — and all show-specific content lives in gated per-tenant assets: an Episode Format module (the show bible), a Reference Asset Registry (character sheets, location plates, grade token, music beds, card styles), and the existing visual-style/viral-patterns modules. The LLM's creative surface per episode shrinks to the words and the staged actions; everything recurring is registry-resolved. Media generation becomes stills-first (cheap, reference-conditioned, operator-approved as a storyboard) then animation of approved stills only (expensive). Validation is layered: deterministic lints before any spend, embedding/histogram QC on returned assets feeding the existing ASSET-REVIEW + AMENDMENT-008 machinery, an editorial critic scored against a rubric that lives in the format module, and golden-episode regression fixtures for the renderer.

---

## Section 1 — Episode Format module (the show bible)

### 1.1 New module type: `episode-format`

Per-tenant, gated, section-addressable like every other module. First instance: `modules/stackpenni/episode-format-parable.md`. It defines the show, not any episode:

- **Cast** — the recurring character(s): name, age, description, wardrobe (fixed), demeanor. References registry `character_ref` IDs (Section 2).
- **World** — 4–6 recurring locations, each referencing a registry `location_ref` ID (for StackPenni: e.g. gallery porch, kitchen table at dawn, market in town, rum shop, beach at dusk — the operator seeds and approves these).
- **Grade** — one verbatim color/light description string (the `grade_token` text) that is appended to every image prompt. E.g. "warm golden-hour Caribbean light, teal and coral accents, soft film grain, shallow depth of field." Stored once, injected mechanically.
- **Beat grammar** — the ordered roles an episode must contain and their rules: `hook` (≤3s, spoken contradiction or confession, character shown in that exact state), `setup`, `struggle` ×2–4, `turn`, `lesson` (concept named in plain words), `cta` (recurring sign-off line, payoff-first per existing standing order 5). Target 60–120s.
- **Delivery mode** — narration-over-scenes. The character is shown living each beat; VO narrates. **No on-camera dialogue, no lip-sync.** (Cheapest tier, zero sync failure class, and it is the reference genre's native grammar.)
- **Audio register map** — beat registers (`somber`/`hopeful`/`wry` or as authored) → registry `music_bed` IDs. Fixed duck level and −14 LUFS target.
- **Graphics vocabulary** — which renderer-drawn card styles exist (`number_card`, `title_card`, `quote_card`) and when the format calls for them (every number spoken in VO gets a card — Section 3).
- **Critic rubric** — the Layer-3 editorial checklist (Section 7.3) lives here so it is gated and improvable by the Analyst through the module review gate, same as everything else.

### 1.2 Prompts carry procedure; this module carries the show

The Writer/ideation prompts gain a view of this module (via the existing `config/processes.yaml` composition mechanism — no new injection machinery). The Writer's job per episode becomes: produce `beats[]` — each with `role`, `vo_text`, `register`, and `staged_action` (one sentence describing what the character is doing in that beat's shot). No visual style, no character description, no location invention — those are token references the Assembler resolves.

### 1.3 Format is per-tenant config, zero harness knowledge

The harness knows the *schema* of an episode-format module; it never knows StackPenni's character or grade. A second tenant defines a different show by writing a different module. Any StackPenni-specific string in generic code is a defect (standing rule).

### 1.4 Visual-style module amendment (module review gate — operator decision required)

Add to `modules/stackpenni/visual-style.md` blend rules, via the module review gate:

> **Fictional recurring persona (episode format):** The show's narrator character is an openly fictional, AI-generated persona — a storytelling device, not a depiction of any real person. Episodes using the persona follow platform AI-disclosure rules (fully generated visuals → platform AI label). The persona never makes first-person claims about real events, real results, or real partnerships; those remain real-footage anchors. "Never present a generated visual as a real person" stands unchanged.

This is the resolution of F-G: the rule protecting trust stays intact; the parable device is added beside it, gated.

---

## Section 2 — Reference Asset Registry

### 2.1 New table: `reference_assets`

```sql
CREATE TABLE IF NOT EXISTS reference_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    kind TEXT NOT NULL,           -- 'character_ref' | 'location_ref' | 'music_bed' | 'grade_token' | 'card_style'
    name TEXT NOT NULL,           -- 'stackwell_the_elder', 'kitchen_dawn', 'bed_somber'
    status TEXT NOT NULL DEFAULT 'proposed',  -- 'proposed' | 'approved' | 'retired'
    payload_json TEXT NOT NULL,   -- kind-specific: file paths, prompt text, params
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT, approved_at TEXT, approved_by TEXT
);
```

- `character_ref` payload: 3–6 approved reference images (front, ¾ left, ¾ right; ≥1024px), wardrobe description, generation notes. Files under `data/media/reference/{business}/{name}/`.
- `location_ref` payload: 1–2 approved establishing plates per location + prompt text that produced them.
- `music_bed` payload: audio file path, register, duration, source (`elevenlabs_music`), license note.
- `grade_token` payload: the verbatim grade string.
- `card_style` payload: renderer parameters (font, palette from visual-style module tokens, position, animation).

This generalizes the existing `voice-samples/` pattern (voice cloning reference clips) into one registry. Voice refs may migrate into it later; not required by this correction.

### 2.2 Gate-only writes; approved assets are inviolable

Reference assets are created through a proposal flow (AI generates candidates → operator approves on a registry surface within the existing module review gate area — reuse its no-bulk-approve discipline). Once `approved`, the payload is locked; changes create a new version through the same gate. Every generation call logs which registry versions it used (provenance).

### 2.3 Bootstrap flow (one-time per show)

A guided sequence, all through existing gate patterns: (1) generate character candidates from the operator's seed description → operator picks/approves the canonical set; (2) generate each location plate *conditioned on the grade token* → approve; (3) generate 3 music beds via ElevenLabs Music (Section 6) → approve; (4) card styles derived from the visual-style module → approve. After bootstrap, episodes reference; they never regenerate these.

---

## Section 3 — EpisodePlan schema (beats → shots → existing edit plan)

### 3.1 Beats become first-class at the Writer stage

Extend the draft/asset content schema for episode-format pieces:

```json
{
  "format_module": "episode-format-parable@vN",
  "beats": [
    {
      "id": "b01",
      "role": "hook",
      "vo_text": "I worked fifty years and retired with nothing.",
      "register": "somber",
      "staged_action": "the man sits alone at the kitchen table at dawn, hands folded around a cooling cup",
      "location_ref": "kitchen_dawn",
      "graphics": [{"type": "number_card", "text": "50 YEARS", "style": "title_card_v1"}]
    }
  ]
}
```

Rules: exactly one shot per beat; `staged_action` must literally depict `vo_text`'s content (Layer-3 rubric checks this); every number in any `vo_text` must have a `graphics` entry (Layer-1 lint); `location_ref` must resolve to an approved registry asset (Layer-1).

The `platform_content` (approved text) for these pieces **is** the ordered `vo_text` sequence — so AMENDMENT-008's text-boundary firewall automatically protects the script verbatim through remediation, and the compliance contract's per-beat coverage becomes native rather than reverse-engineered.

### 3.2 Shot generation contract (Assembler side, media plan v2)

For each beat the Assembler produces a **shot spec**, mechanically assembled (not LLM-freeform):

```
image_prompt = character_block(character_ref) + staged_action + location_block(location_ref) + grade_token
reference_images = character_ref images + location_ref plate   (always the canonical registry files — never chained outputs; re-anchoring is structural)
motion_prompt = camera/movement line only (LLM-authored, e.g. "slow push-in as he exhales")
duration_ms = measured VO duration of the beat (existing master-clock rule, now per-beat)
```

Banned tokens in `staged_action`/prompts (Layer-1 lint, hard fail): `text`, `words`, `sign`, `screen`, `phone`, `logo`, `document`, `chart`, `letters`, `numbers on`. All text/numbers are renderer-drawn graphics — the mush class is eliminated by construction, not by review.

### 3.3 Edit plan mapping (no renderer rewrite)

The EpisodePlan compiles down to the existing edit plan schema: one segment per beat (`source: generated:<video_media_id>`, `in/out` = full clip), overlays = captions chunked 3–5 words from `vo_text` (styles from visual-style module) + the beat's graphics as overlay entries, `sfx` per existing standing order 10, `audio` block = VO primary + registry `music_bed` for the dominant register, ducked, `loudnorm` to −14 LUFS enforced (not optional) for this format. `beat_id` is carried on each segment for compliance-contract linkage. The AssemblyRenderer changes only where card styles need richer drawing (`card_style` payload → `_resolve_overlay_style` extension).

---

## Section 4 — Storyboard gate (stills before animation)

### 4.1 Flow

After VO renders and shot specs are built: generate **one still per beat** (reference-conditioned, Section 5 image path; ~$0.04–0.08 each). Present the full storyboard on a new Assets sub-surface: each card = still + beat role + vo_text + measured duration + Layer-2 QC flags + **the exact animation cost for that shot** (duration × per-second rate from config). Operator actions per shot: approve / regenerate (with note) / swap location. Global action: **"Approve storyboard → animate (est. $X.XX total)"** — the explicit cost confirmation required by the constitution now happens with the film visible, not blind.

### 4.2 Only approved stills are animated

Animation calls are image-to-video from the approved still + motion prompt. A regenerated-after-approval still resets that shot to unapproved. This is the cheap-to-expensive ordering (resolves F-D): the ~$2 storyboard gates the ~$9–13 animation spend.

### 4.3 Remediation interaction

Within AMENDMENT-008's loop, `regenerate_media` for this format means: regenerate the *animation* from the same approved still (or flag the still itself → `needs_operator_decision`). The loop never silently replaces an operator-approved still — same spirit as the text firewall, applied to approved images. Cost guard applies unchanged.

---

## Section 5 — Media adapter: fal.ai provider, image-to-video, cost table

### 5.1 Add `fal` provider to `MediaAdapter`

Async queue pattern (submit → poll → download) — same shape as the existing `submit_video`/`check_video_job`/`download_video` trio. `FAL_API_KEY` env. Endpoints are config strings in `models.yaml`, never hardcoded.

### 5.2 `models.yaml` media block (REPLACE semantics for the listed keys)

```yaml
media:
  image_generators:
    - name: "nano-banana-2"            # character/location shots — reference-conditioned
      provider: "fal"
      endpoint: "fal-ai/gemini-3-flash-image"   # Hermes: verify exact current fal endpoint id at implementation time
      cost_per_image_usd: 0.08
      supports_reference_images: true
      best_for: "recurring characters, identity-critical shots (up to 5 characters / 14 refs)"
    - name: "flux2-pro"
      provider: "fal"
      endpoint: "fal-ai/flux-2-pro"
      cost_per_image_usd: 0.03
      supports_reference_images: true
      best_for: "b-roll and non-character shots, highest photorealism"
  image_default: "nano-banana-2"

  video_generators:
    - name: "kling-3"                  # workhorse — best subject consistency per $/sec
      provider: "fal"
      endpoint: "fal-ai/kling-video/v3/standard/image-to-video"
      cost_per_second_usd: 0.10
      mode: "image_to_video"
      native_audio: false              # ALWAYS off — VO is ours; saves 30–50%
      best_for: "all standard shots"
    - name: "veo-3.1-fast"
      provider: "fal"
      endpoint: "fal-ai/veo-3.1-fast/image-to-video"
      cost_per_second_usd: 0.15
      mode: "image_to_video"
      native_audio: false
      best_for: "hook/hero shots"
  video_default: "kling-3"

  music_generators:
    - name: "eleven-music"
      provider: "elevenlabs"
      api_key_env: "ELEVENLABS_API_KEY"
      best_for: "registry music beds only — licensed training data, clean commercial rights"
```

**Retire the `sora` entry entirely** (API discontinued 2026-09-24). Grok/direct-Google entries may remain as named backends but drop out of the default path. `cost_per_second_usd` / `cost_per_image_usd` are the deterministic inputs to every gate cost card — estimates are computed, never guessed.

### 5.3 `generate_image` gains `reference_images: list[str]`

Paths from the registry, uploaded/passed per fal endpoint contract. `submit_video` gains `mode="image_to_video"` + `source_image` path. Provenance rows record registry asset IDs + versions used.

---

## Section 6 — Music beds

Three beds per show (one per register), generated once via ElevenLabs Music API during bootstrap, ~60–90s each, instrumental, operator-approved into the registry, reused every episode. Per-episode music generation is prohibited for this format (consistency is the point; cost rounds to zero). Pixabay stock music remains available to *other* formats; the episode format resolves music only from the registry. Renderer: existing duck/mix path; add enforced `loudnorm` I=-14 for episode-format renders.

---

## Section 7 — Validation and testing

### 7.1 Layer 1 — deterministic lints (free, pre-spend; extend `src/validator.py` / `feasibility_checks.py`)

Run on every EpisodePlan before any media call:
- Referential integrity: every `character_ref`/`location_ref`/`music_bed`/`card_style` resolves to an **approved** registry asset; exactly one shot per beat; beat roles satisfy the format module's grammar (hook first, ≤3s measured; lesson and cta present).
- Duration budget: Σ measured VO within format target ±10% (extends the existing T10.3 feasibility check with per-beat granularity).
- Banned-token scan on all image/motion prompts (Section 3.2 list). Grade token present verbatim in every image prompt.
- Numbers rule: every numeral in `vo_text` has a matching `graphics` entry.
Failure → bounce to Writer/Assembler LLM with lint errors (auto-retry, capped), then `needs_operator_decision`. No money is spendable on a plan that fails Layer 1.

### 7.2 Layer 2 — asset QC (cheap, post-generation; extends `asset_review.py`, feeds AMENDMENT-008)

- **Identity check:** face-embedding cosine similarity of each returned still (and first/mid/last frames of each animated clip) against the canonical `character_ref` images; below-threshold → `qc_flag: identity_drift`. (Self-hosted embedding model, e.g. an insightface-class ONNX on CPU — Hermes selects; no per-call API cost.)
- **Grade check:** color-histogram distance vs. the location plate / grade reference; breach → `qc_flag: grade_break`. (This is the exact `final_1` ending failure, mechanized.)
- Flags are advisory: they render as warnings on storyboard cards and enter the AMENDMENT-008 review evidence. The operator decides — consistent with the existing review doctrine.

### 7.3 Layer 3 — editorial critic (LLM, advisory, rubric gated in the format module)

Post-Writer, pre-Gate-2: critic scores against the module rubric — hook contains contradiction/confession; each `staged_action` literally depicts its `vo_text`; one idea per beat; lesson stated plainly; sign-off present. Scores + one-line reasons on the Gate 2 card. Never blocks; the operator's judgment is the gate. Analyst may propose rubric edits only through the module review gate.

### 7.4 Golden episodes (renderer regression)

Two hand-approved EpisodePlans with frozen assets under `tests/fixtures/golden/`. Any renderer/schema change re-renders both and asserts: total duration exact vs. VO; integrated loudness −14 ±0.5 LUFS; caption timing offsets; frame hashes on graphics-only segments; stream layout. Add to the suite; failure blocks the task's Definition of Done.

### 7.5 Pipeline-quality metric

Validator pass rate: run the Writer prompt against a 20-seed corpus; record the fraction of EpisodePlans clearing Layer 1 unassisted. <80% → the prompt or schema is the defect (correction-file territory), not the model. Log per prompt version so drafter A/B (M3 checkpoint) covers this format.

### 7.6 Operator-judgment items (never self-certified)

Per the existing acceptance discipline, two judgments are the operator's alone: (a) **character likeness continuity** across an episode and across episodes — does it read as the same person; (b) **platform-native look** of the finished reel. Plus the standing voice-fidelity judgment on VO. Hermes marks these tasks done only after the operator's hands-on pass.

### 7.7 Outcome loop

Analyst reads per-episode 3-second hold and completion rates (existing metrics path) and proposes format-module amendments through the module review gate. The hook rule is thereby falsifiable by data; the format improves through the same gated process as every module.

---

## Cost model (for gate cards; computed from Section 5.2 config)

90s episode ≈ 18–22 beats: stills ~22 × $0.08 ≈ $1.80; animation ~90s × $0.10 ≈ $9.00 (+$0.05/s premium on hero shots); VO ~$0 (Gemini TTS); music $0 (registry). **≈ $11–13/episode, itemized per shot at the storyboard gate, total confirmed before animation.** Storyboard rejection wastes cents, not dollars.

## Sequencing

1. Section 5 Sora retirement + Section 7.1 lints (P0, immediate).
2. Registry (Section 2) + fal provider (Section 5) — infrastructure, no format dependency.
3. Format module schema + StackPenni bootstrap (Section 1, 2.3) — requires operator gate sessions.
4. EpisodePlan schema + Writer/media-plan prompt v2 (Section 3).
5. Storyboard gate (Section 4).
6. Validation layers 2–3, goldens, metric (Section 7).
Confirm S1/S3 landed (existing rule) before the first full episode run; the 10-piece M3 sprint checkpoint should include ≥3 episodes in this format.

## Definition of Done

A voice-note seed travels: seed → beats (Writer) → Gate 2 approval → VO rendered → shot specs → Layer-1 pass → storyboard stills → operator approves storyboard with itemized cost → animation of approved stills only → assembly (captions, cards, registry bed, −14 LUFS) → ASSET-REVIEW + AMENDMENT-008 compliance pass → operator reviews finished reel. Two consecutive episodes, generated a week apart, show the same character, same locations, same grade, same caption style, same sign-off, same music register mapping — verified by the operator (7.6) and by Layer-2 scores. All existing tests pass; goldens added; zero StackPenni strings in harness code.
