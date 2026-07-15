# MANIFEST — 2026-07-14 Episode Format + Reference Assets

**Date:** 2026-07-14
**Architect:** vf-architect
**Batch:** Episode format (show bible), reference asset registry, storyboard gate, fal.ai media provider, validation layers

## Files

| File | Destination | Action |
|---|---|---|
| `CORRECTION-episode-format-and-reference-assets-v1.0.md` | `docs/corrections/` | ADD |
| `MANIFEST-2026-07-14-episode-format.md` | `docs/inbox/processed/` | (this manifest — moved after filing) |

## Context

Operator diagnosis: rendered videos have no recurring character, style, or format — each output is a different genre. Root cause confirmed against the live repo: no reference conditioning in the media path (media plan uses prose style directives only; `MediaAdapter` accepts text prompts only), no beat structure at the Writer stage, no stills-before-animation ordering, no fixed music/loudness system, and a stale `models.yaml` media block (Sora listed — its API is discontinued 2026-09-24 and must be retired).

The correction introduces one generic harness capability — reference-conditioned, beat-structured episode production — with all show-specific content in gated per-tenant assets: an `episode-format` module type, a `reference_assets` registry table + gate surface, an EpisodePlan beat schema compiling to the existing edit plan, a storyboard approval gate between stills and animation, a `fal` provider in `MediaAdapter` with config-driven per-unit costs, ElevenLabs Music for one-time registry music beds, and four validation layers (deterministic lints, embedding/histogram asset QC, gated critic rubric, golden-episode renderer fixtures).

**Constitutional notes for the builder:**
1. Approved `platform_content` for episode-format pieces is the ordered `vo_text` sequence — AMENDMENT-008's text-boundary firewall covers it unchanged.
2. Operator-approved storyboard stills are inviolable inside the remediation loop (regenerate animation from the same still, or escalate — never silently replace an approved still).
3. The recurring persona requires a visual-style module amendment (correction §1.4) — this goes through the **module review gate**; Hermes prepares the proposal, the operator approves it there. Do not edit the module directly.
4. No StackPenni strings in harness code. The harness knows the episode-format schema; only `modules/stackpenni/` knows the show.

## APPLY

1. File the correction to `docs/corrections/`.
2. Apply the BUILD_PLAN M11 addendum (below) to `BUILD_PLAN.md` — add after M10, bump header to v1.8 with note.
3. Log one CHANGELOG entry (type: STRUCTURE / STRATEGIC) for the batch.
4. Move this manifest to `docs/inbox/processed/`.

## BUILD_PLAN M11 Addendum (apply to BUILD_PLAN.md)

Add after M10, before the PROGRESS.md format section:

```markdown
### M11 — Episode format + reference assets (per CORRECTION-episode-format-and-reference-assets-v1.0)
*One generic capability — reference-conditioned, beat-structured episode production. The show lives in gated tenant assets; the harness never knows the character.*

- [ ] T11.1 **Retire Sora + models.yaml media block v2 (P0):** Remove the `sora` generator entry (API discontinued 2026-09-24). Restructure `media` block per correction §5.2: `image_generators` list with `cost_per_image_usd` + `supports_reference_images`, `video_generators` with `cost_per_second_usd` + `mode` + `native_audio: false`, `music_generators`. Verify exact current fal endpoint IDs at implementation time — AC: no `sora` reference anywhere; gate cost estimates read per-unit costs from config; legacy grok/google entries remain as non-default named backends
- [ ] T11.2 **Layer-1 EpisodePlan lints (P0):** Extend validators per §7.1 — registry referential integrity (approved assets only), beat grammar vs. format module, per-beat duration budget, banned-token scan on all media prompts, grade-token-present check, numbers→graphics rule. Bounce failures to the authoring LLM with lint errors (capped retries) then `needs_operator_decision` — AC: a plan violating any lint cannot trigger a paid media call; the banned-token list is config, not code
- [ ] T11.3 **`reference_assets` table + registry gate surface (P0):** Schema per §2.1, proposal→approve flow reusing module-review-gate discipline (no bulk approve), files under `data/media/reference/{business}/`, approved payloads locked (new version = new gate pass), provenance records registry IDs+versions per generation call — AC: an unapproved asset is unusable by any generation path; approving/retiring never mutates prior versions
- [ ] T11.4 **fal provider in MediaAdapter (P0):** Async submit/poll/download matching the existing trio; `FAL_API_KEY`; `generate_image(reference_images=[...])`; `submit_video(mode="image_to_video", source_image=...)`; endpoints from config only — AC: one reference-conditioned image and one image-to-video clip generate end-to-end with cost logged to provenance; zero hardcoded endpoints
- [ ] T11.5 **`episode-format` module type + StackPenni show bible bootstrap (P1):** Module schema per §1.1 (cast, world, grade, beat grammar, delivery mode, register map, graphics vocabulary, critic rubric); wire into `config/processes.yaml` views; guided bootstrap flow per §2.3 (character candidates → locations conditioned on grade → 3 ElevenLabs music beds → card styles), every approval through gates. Prepare the visual-style module amendment per §1.4 for the module review gate — AC: bootstrap completes with operator approvals only; harness contains no show-specific strings; visual-style amendment awaits operator decision at the module gate
- [ ] T11.6 **EpisodePlan schema + Writer beats + media plan v2 (P1):** Writer emits `beats[]` per §3.1 for episode-format pieces (approved text = ordered vo_text — AMENDMENT-008 firewall applies); shot specs assembled mechanically per §3.2 (canonical registry refs always — never chained outputs); compile to existing edit plan per §3.3 with `beat_id` carried on segments; enforced `loudnorm` I=-14 for this format — AC: one shot per beat by construction; compliance contract beats map 1:1 to authored beats; captions/cards are renderer-drawn only
- [ ] T11.7 **Storyboard gate (P1):** New Assets sub-surface per §4 — one reference-conditioned still per beat, per-shot cards (still, role, vo_text, duration, QC flags, exact animation cost), approve/regenerate/swap-location per shot, global "Approve storyboard → animate (est. $X)" as the explicit cost confirmation; only approved stills animate; post-approval regeneration resets approval; remediation may re-animate from an approved still but never replace it silently — AC: animation spend is impossible without storyboard approval; itemized costs shown are computed from config
- [ ] T11.8 **Layer-2 asset QC (P1):** Face-embedding similarity vs. canonical character refs on stills and first/mid/last animation frames; color-histogram grade check vs. location plate; thresholds in config; flags advisory → storyboard cards + AMENDMENT-008 review evidence — AC: a deliberately off-character test still is flagged; flags never auto-reject
- [ ] T11.9 **Layer-3 critic + rubric in module (P2):** Post-Writer critic scored against the format module's rubric; advisory scores on Gate 2 card; Analyst proposes rubric edits only via module review gate — AC: rubric text lives in the module, not in prompts/code; critic never blocks
- [ ] T11.10 **Golden episodes + validator pass-rate metric (P1):** Two frozen EpisodePlans + assets under `tests/fixtures/golden/`; re-render on renderer/schema change asserting duration, −14 ±0.5 LUFS, caption offsets, graphics frame hashes; 20-seed Layer-1 pass-rate harness logged per prompt version — AC: goldens in suite and blocking; pass-rate report generated per Writer prompt version
- [ ] **Checkpoint:** operator end-to-end test — two episodes a week apart; operator judges character likeness continuity and platform-native look (never self-certified); include ≥3 episodes in the 10-piece M3 sprint. Tag `review-episode-format`.
```

Update BUILD_PLAN header to:
```
v1.8 — 2026-07-14 — CORRECTION-episode-format-and-reference-assets added as M11 tasks (episode format, reference registry, storyboard gate, fal provider, validation layers). Sora retired.
```
