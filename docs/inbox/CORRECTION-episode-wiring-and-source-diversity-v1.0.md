# CORRECTION — Episode wiring and source diversity — v1.0

**Date:** 2026-07-25
**From:** Architect
**To:** Builder
**Repo state reviewed:** `da1d3b4` — "FIX: Nav counter not updating when ideas move to draft"
**Artifact reviewed:** `final_1.mp4` — 70.0s, 1080×1920, 30fps, H.264 High, mono AAC 48kHz
**Companion:** `AMENDMENT-015-shots-per-beat-and-two-tier-render.md` — read it first

---

## Framing

The operator's report was that the video output is poor and the ideas are not diverse. Both
are true. Neither is caused by what a first reading suggests.

The video is not a rendering-quality failure and not a style failure. **The episode-format
architecture never ran.** `prompts/assembly/media_plan_v2.md` — the registry-anchored
shot-spec prompt with mechanical prompt assembly and banned text tokens — is invoked by no
code path in the repository. The live path is `media_plan_v1.md`, whose only instruction is
to fill each frame's measured VO duration with "visual coverage." It contains no character
instruction of any kind. Asking a coverage-filling prompt for coverage returns coverage,
and coverage of an eleven-second beat by a single generated image is a slideshow. The
output is exactly what the wired code specifies.

The idea diversity failure is not in the prompt either. `prompts/ideas/generate_v1.md`
already carries an existing-ideas anti-repetition block, kill lessons, and format-usage
spreading. Those constraints can only redistribute *within* the available source pool, and
that pool is currently five YouTube channels and five frozen search queries, with
`feeds: []`. A static query set returns substantially the same material on every run. The
ideas converge because the inputs are the same inputs.

Ten items. P0 items are blocking. Report per item by P-number with evidence.

---

## P0-1 — Foundational documents exist only in the working tree (third recurrence)

**Finding.** `grep -ril "character.bible\|character_bible"` across the repository returns
nothing. The character bible referenced in the builder's own analysis of this render as
"the character bible v2.0 we wrote today" is not committed. This is the third occurrence of
this failure mode; it was flagged as a non-negotiable precondition before Phase 0 and it
has recurred.

Separately, two documents that govern everything downstream are unratified:

- `assets/reference/stackpenni/grade_token/world_canon.md` — header reads
  `**Status:** DRAFT — pending operator gate.`
- `modules/stackpenni/visual-style-amendment-proposed.md` — header reads
  `**Status:** PROPOSED — awaiting operator gate approval`

No compliant code path may consume an ungated canon. Until these are gated, every
registry-anchored feature below is architecturally blocked.

**Required.**
1. Commit the character bible to `modules/stackpenni/character-bible.md`. It is a module,
   not a prompt fragment — see P0-2 acceptance criteria for why this matters.
2. Surface both DRAFT/PROPOSED documents on the module review gate for operator decision.
   Do not self-approve, do not apply, and do not add an approve-all shortcut.
3. Audit the working tree against `main` and report **every** uncommitted document, not
   just these. Paste `git status --porcelain` output for the VPS working tree.

**Acceptance criteria.** Character bible present on `main`. Both gate items appear in the
module review UI awaiting decision. A written list of any other uncommitted documents is in
the report. No document is applied without a recorded operator approval.

---

## P0-2 — `media_plan_v2` is dead code; the episode path is unreachable

**Finding.** `src/services/media_planning.py` hardcodes the v1 prompt at two call sites:

- line 318 — `assemble_module_context("assembly/media_plan_v1.md", ...)`
- line 395 — `adapter.complete(prompt_file="assembly/media_plan_v1.md", ...)`

`media_plan_v2` is registered in `config/processes.yaml` at line 152 and called by nothing.
`grep -rn "media_plan_v2" src/` returns zero hits. `grep -n "episode" config/processes.yaml`
returns zero hits — there is no episode-format process wired at all.

**Required.** Make `media_plan_v2` the live path for episode-format assets.

- Selection is driven by the asset's format resolving to an episode format, read from the
  format guide. Do not add a tenant string, a business slug, or a hardcoded format name to
  harness code.
- `media_plan_v1` remains reachable for non-episode assets. Do not delete it and do not
  rewrite it — a third divergent path is worse than two clear ones.
- The character bible is consumed as a **module**, resolved into `character_block` through
  the registry and the existing section-addressable module view map. It is not pasted into
  the prompt. Prompts carry procedures; modules carry knowledge. A domain taxonomy embedded
  in a prompt is a defect.

**Acceptance criteria.** An episode-format asset routes to `media_plan_v2`; a non-episode
asset routes to `media_plan_v1`; both proven by test. No tenant identifier appears in
harness code. `character_block` is assembled from registry and module content with a
provenance record, and no character description text appears in any `.md` prompt file.

---

## P0-3 — Prompt/process input contract mismatch, and the validator that should have caught it

**Finding.** Even wired, `media_plan_v2` would fail to populate. The declared inputs in
`config/processes.yaml` and the placeholders in the prompt file do not correspond:

| Declared in `processes.yaml` | Present in `media_plan_v2.md` |
|---|---|
| `business_name` | `{business_name}` ✓ |
| `contract_beats` | — |
| `measured_vo` | — |
| `references` | — |
| `inventory`, `available_providers`, `costs`, `visual_style`, `format_guide` | — |
| — | `{format_module}` |
| — | `{episode_plan_beats}` |
| — | `{registry_context}` |
| — | `{vo_timeline}` |

One of ten declared inputs matches. `validate_process_registry()` at
`src/process_engine.py:52` — added as P2-10 in the previous batch — validates that
processes resolve but does not compare a prompt's placeholders against its declared inputs.
That check is exactly what would have caught this at startup.

**Required.**
1. Reconcile the contract. Prefer renaming the `processes.yaml` inputs to match the prompt,
   since the prompt's names are the ratified vocabulary from the episode-format correction.
2. Extend `validate_process_registry()` to assert **bidirectional** parity for every
   registered process: every `{placeholder}` in the prompt file has a declared input, and
   every declared input appears as a placeholder. Fail startup on mismatch with a message
   naming the process, the file, and the specific offending names.
3. Run the extended validator across the whole registry and report every process it flags.
   Fix the mismatches it finds; do not silence them.

**Acceptance criteria.** Validator fails startup on an induced mismatch and passes clean on
the reconciled registry. Two tests: one asserting a missing-input mismatch is caught, one
asserting an unused-input mismatch is caught. A written list of every process the validator
flagged on first run, with its resolution, is in the report.

---

## P0-4 — Loudness normalization never executes; the master is clipping

**Finding.** Measured on `final_1.mp4` with `ffmpeg -af ebur128=peak=true`:

- Integrated: **−15.3 LUFS** (target −14)
- True peak: **0.0 dBFS** — clipping
- LRA: 3.0 LU
- Channels: 1 (mono)

The cause is structural, not a missing filter. The `loudnorm` pass lives inside the SFX
mixing function in `src/assembly.py`, and that function returns early before reaching it:

```
if not all_sfx:
    return None
```

The loudnorm invocation sits at line ~1104, well past that guard. **A piece with no SFX
cues receives no loudness normalization and no true-peak control at all** — which is every
VO-only piece, including this one. The `TP` default of −1.5 at line 1207 is correct and
never runs.

A second defect exists on the path where it *does* run: `loudnorm` is applied to `[0:a]`
and SFX are mixed in *afterwards* via `amix`. Mixing after normalization can push peaks
back above the true-peak ceiling, so the guarantee is broken even in the SFX case. And
single-pass `loudnorm` does not reliably deliver its true-peak target regardless.

**Required.**
1. Extract loudness normalization into an **unconditional final audio stage** in the
   assembly engine, decoupled from SFX presence entirely. It runs on every piece.
2. Order it **after** all mixing — VO, music bed, SFX — never before.
3. Follow `loudnorm` with an explicit `alimiter` at `limit=-1.5dB`. Do not rely on
   `loudnorm`'s single-pass TP estimate as the ceiling.
4. Target `I=-14`, `TP=-1.5`, `LRA=11` for social masters.
5. Output **stereo** on the master. Mono is a correctness gap on platforms that apply
   stereo processing.

**Acceptance criteria.** A VO-only render with zero SFX cues and zero music measures
`I` within ±0.5 LU of −14 and true peak at or below −1.5 dBFS, verified by pasted `ebur128`
summary output. Master is 2-channel. A test asserts the normalization stage executes on a
plan with an empty SFX array.

**Not a defect — recorded so it is not "fixed" twice.** Video bitrate measured 3.33 Mbps.
That is CRF-driven output from `_video_encode_args`, and low motion content legitimately
encodes thin at CRF 16. Leave the encode tiers from P1-6 of the previous batch alone.

---

## P1-5 — Implement AMENDMENT-015 shots-per-beat

**Finding.** Scene analysis of the render shows change clusters at 3s, 6s, 9s, 11s, 12s,
then no visual change between 12.1s and 22.8s, and again between 22.8s and 35.8s. The
one-shot-per-beat rule from `CORRECTION-episode-format-and-reference-assets-v1.0` §3.2
produced this. That rule is the architect's error and is now amended.

**Required.** Implement §2 of `AMENDMENT-015` exactly as ruled:

- `N = ceil(beat_duration_ms / 4000)`, minimum 1, shots per beat.
- All N shots share `character_block`, `location_block`, `grade_token`.
- Framing cycles mechanically `wide → medium → close → insert`; the Assembler does not
  choose it.
- One LLM-authored `motion_prompt` per shot.
- Shot durations divide the beat's measured VO duration, remainder to the final shot.
- No shot crosses a beat boundary.

**Acceptance criteria.** An 11.0s beat yields exactly 3 shots. A 3.2s beat yields 1. Summed
shot durations equal the beat's measured VO duration exactly, with no drift across a
full plan. All shots in a beat carry identical character and location blocks, proven by
test. No shot spans two beats.

---

## P1-6 — Music beds: acquire five, gate them once, kill the `vo_only` fallback

**Finding.** `find . -iname "*music*"` returns nothing. There are no music beds in the
registry. The soundtrack planner is therefore correct to fail closed to `vo_only` on every
run — the architecture in `src/soundtrack_rights.py` and `src/services/audio_candidates.py`
is sound and is not the problem. The registry is empty. `vo_only` should be a deliberate
creative decision, and it is currently the only reachable outcome.

**Ruling on source — this supersedes the earlier ElevenLabs Music ruling.** Use **Pixabay**,
filtered to CC0 tracks where available. The Pixabay License grants irrevocable, worldwide,
royalty-free commercial use with no attribution requirement. The beds are one-time registry
assets under a voice; paying for distinctiveness on a layer nobody consciously hears is
misallocated spend. Do not use CC-BY sources — Free Music Archive's mainline catalogue and
Incompetech both require artist credit, and building attribution plumbing for a background
bed is not worth it. FreePD is an acceptable CC0 secondary source.

**Required.**
1. Acquire five ambient beds matched to the brand's emotional register — warm, sparse,
   Caribbean-adjacent, no strong melodic hook that competes with VO.
2. Register each as a gated registry asset with a **complete rights record**: source URL,
   license name, license text snapshot, and acquisition date. Pixabay offers no
   indemnification and does not verify contributor ownership; the snapshot is the defence.
   Note in each record that Content ID claims are possible and are resolved by presenting
   the license.
3. Route them through the existing soundtrack gate. Do not bypass it. Do not auto-apply.
4. Once gated, `vo_only` requires an explicit operator rationale — it is a decision, never
   a fallback.

**Acceptance criteria.** Five beds present in the registry, each with a complete rights
record. A fresh render selects a bed through the normal gate without operator intervention
at discovery time. Selecting `vo_only` is rejected without a written rationale. Music sits
below VO after the P0-4 normalization stage, VO intelligible throughout.

---

## P1-7 — Source pool is frozen; this is why ideas converge

**Finding.** `config/sources.yaml`:

- `feeds: []` — all three RSS feeds were removed 2026-07-24 with an inline TODO and never
  replaced. The comment correctly records why (80% travel-journalism pollution) but the
  replacement never happened.
- Two channels share the identical `channel_id` `UC9bFRvRiGR8xKDhK3xq+Phg` — "AI Explained"
  and "Two Minute Papers". A `+` is not valid in a YouTube channel ID. This is a paste
  error; at most one of these two resolves, and possibly neither.
- Five search queries, hardcoded and static, re-run unchanged on every ingestion cycle.

A frozen input pool cannot produce diverging ideas. The anti-repetition block in
`prompts/ideas/generate_v1.md` can only reshuffle what it is given, which is how synonym-
swapped angles arise. **Do not modify the idea generation prompt for this item.**

**Required.**
1. Replace the empty `feeds` list with sources that actually cover the subjects in
   `modules/stackpenni/sources.md`: AI's impact on small business and Caribbean economies,
   wealth-building and investing, Caribbean entrepreneurship and economic development, tech
   trends for Caribbean professionals. Validate each feed URL returns parseable items before
   committing it. Report the fetch status of every candidate.
2. Fix or remove the malformed channel IDs. Verify each remaining channel resolves and
   report the result per channel.
3. Convert `queries` from a static list to a **rotating pool**: a larger set of queries with
   a rotation policy so each ingestion cycle draws a different subset. Add a date window to
   queries where recency matters, per the freshness rule in the sources module (1–2 years
   for financial literacy data, AI trends, and regional developments; timeless acceptable
   for philosophy and psychology).
4. This is config plus small ingestion logic. It is not a prompt change and not an idea
   generation change.

**Acceptance criteria.** Two consecutive ingestion cycles produce materially different
source sets, demonstrated by pasted source-ID diffs. Every configured feed and channel is
verified reachable, with per-source status in the report. No change to
`prompts/ideas/generate_v1.md`.

---

## P1-8 — Word-level caption emphasis

**Finding.** The builder's analysis of this render described the captions as "white text on
black bars." That is stale — I cropped the caption region and confirmed the PIL rounded-pill
overlays with brand styling are rendering correctly. That work landed and is fine.

The actual gap is narrower: captions render one static pill per phrase with no word-level
emphasis. P1-7 of the previous batch already threaded `faster-whisper` word timestamps
through `cue_compiler` into `chunk_captions`, and added the `materials.word_timestamps`
column. The data is present and unused.

**Required.** Highlight the active word within the pill as the VO speaks it, driven by the
existing word timestamps. Emphasis styling resolves from `config/render_styles.yaml` — no
hardcoded colors. Pill geometry stays stable as the highlight moves; the pill must not
reflow or jitter word to word.

**Acceptance criteria.** Highlight transitions align to word timestamps within 80ms across a
full render. Pill bounding box is constant for the duration of a given caption chunk.
Emphasis colors resolve from config. A render with missing word timestamps degrades to the
current static pill rather than failing.

---

## P2-9 — The graphic tier: number cards, quote cards, end card

**Finding.** `modules/stackpenni/episode-format-parable.md` and the episode format module
define `number_card_v1` and `quote_card_v1`. No rendering code creates or composites them.
There is no end card; the reviewed render simply stops on a server-rack image at 70.0s. The
end card was previously filed as P2 and remains open.

Per `AMENDMENT-015` §3, this is **tier 2** and is built as flat vector composited over the
realism footage layer. The caption pills are the existence proof that the two tiers coexist
without conflict.

**Required.**
1. Implement `number_card_v1` and `quote_card_v1` as renderer-drawn vector cards,
   composited at plan-specified timestamps. All values renderer-drawn — never generated
   into an image frame.
2. Implement a branded end card: brand name, handle, CTA. It is the one permitted full-frame
   tier-2 surface.
3. Geometry, palette, and typography resolve from config and the brand palette. No
   hardcoded brand values in renderer code.
4. Cards must be legible at 1080×1920 and must not occlude a character's face — define and
   enforce a safe region.

**Acceptance criteria.** A plan requesting a number card at a timestamp produces that card
at that timestamp, numerically correct and legible. Every render terminates on the end card.
No brand string or hex value is hardcoded in renderer code. Cards respect the face-safe
region.

---

## Registry state — shared finding for P2-10 and P2-11

`find assets/reference -type f` returns nine files. Against the world canon's requirements:

- Fitzroy: one `reference_render.png`, gated 2026-07-14. The canon requires a set of 3–5
  angles and expressions per character before that character may appear in any episode.
- Stackwell: `canon.md` and `badge_illustration.png` only. The badge is explicitly retired
  from the film layer by the canon; **Stackwell has no realism reference and cannot appear
  in an episode.**
- Locations: the canon locks six. **Zero reference plates exist.**
- Music: zero (covered by P1-6).

The registry-anchored path has almost nothing to anchor to. This is the true blocker on
episode production, ahead of every rendering concern.

These were originally filed as a single sixteen-image batch. That was an error in bundling.
Establishing a character who has no realism precedent is a different class of work from
extending a character who already has a gated standard, and it must not be approved on the
same click. Split accordingly below.

---

## P2-10 — Stackwell establishment: one render, its own gate

**Finding.** Fitzroy has a gated realism standard. Stackwell has none — the only asset is a
stylized badge illustration the canon retires from the film layer. Producing Stackwell is
therefore not a matching task. It is character establishment, and it carries a constraint no
other render in the registry carries: he must read convincingly as Fitzroy's grandson while
holding up as his own character. Family resemblance between two independently generated
faces in a locked style is the hardest single thing in this registry, and it is the render
most likely to need several iterations.

**Required.** One render at a time, iterated to the operator's standard — the same process
that produced the gated Fitzroy reference.

1. Generate a single Stackwell candidate. Grade string inserted verbatim from the world
   canon. Conditioned on Stackwell's `canon.md` for wardrobe and demeanour, and on the
   gated Fitzroy render for family resemblance and style match.
2. Present it to the operator alongside the Fitzroy reference in the same view, so
   resemblance and style consistency can be judged directly rather than from memory.
3. On rejection, iterate. Carry the operator's specific defect feedback into the next
   attempt and present the pair again. Do not batch candidates and do not ask for a pick
   from a grid — one candidate, one decision, per the no-bulk-approve discipline.
4. On approval, the render enters the registry as Stackwell's canonical reference and the
   badge illustration is marked retired from the film layer in the registry record.
5. Cost is surfaced per iteration before each generation call, not once at the start.

**Acceptance criteria.** Exactly one candidate is generated per iteration. Each is presented
paired with the gated Fitzroy render. Rejection feedback is recorded and visibly carried into
the next attempt. On approval, Stackwell has a canonical realism reference in the registry
with a provenance record, and the badge is flagged retired. No grid, no multi-select, no
bulk approve.

**Blocked on P0-1.** The canon and grade string this render conditions on must be ratified
first.

---

## P2-11 — Fan-out plan and cost surface (fifteen remaining renders)

**Finding.** Once both characters have an approved realism reference, the remaining registry
work is extension and matching: four additional Fitzroy angles, four additional Stackwell
angles, and six location plates. Fifteen images. That work has a known standard to match
against and is genuinely batchable — unlike P2-10.

**Required.** Do not generate anything under this item. Produce the plan and the surface:

1. A written render plan covering the fifteen: 2 characters × 4 additional angles and
   expressions, plus 6 location plates. Each entry names the target, the framing, and the
   conditioning references it will use.
2. An explicit cost confirmation surface presenting per-image and total cost **before any
   spend**, per the standing stills-gate-before-animation-spend rule. Cost is never implicit.
3. Each render enters the registry only through the gate. No ungated generative derivatives.
4. The plan is written but not executed. Execution is a later, separately approved unit of
   work.

**Acceptance criteria.** Written plan for fifteen renders committed. Cost surface renders the
full breakdown and requires explicit operator confirmation before any generation call. No
generation occurs under this item.

**Blocked on P0-1 and P2-10.** The canon must be ratified, and Stackwell's reference must be
approved, before there is a standard to plan the fan-out against.

---

## Definition of Done

This batch is complete when all of the following hold. Partial completion is reported as
partial — do not report done on a subset.

1. Every item above reported by P-number, with evidence. Evidence means pasted command
   output, pasted measurements, or a named passing test — not a description of the change.
2. **P0-4 verified by measurement.** Paste the full `ebur128` summary for a fresh VO-only
   render. `I` within ±0.5 LU of −14, true peak at or below −1.5 dBFS, 2 channels.
3. **P0-3 verified by induced failure.** Show the validator rejecting a deliberately
   mismatched process, then passing on the reconciled registry.
4. **P1-7 verified by diff.** Paste source-ID sets from two consecutive ingestion cycles
   showing they differ materially.
5. **P2-10 verified by walkthrough, not by asset.** Show the paired presentation surface with
   the Stackwell candidate beside the gated Fitzroy render, and show a rejection carrying
   feedback into a second candidate. If the operator has not yet approved a Stackwell render
   when the rest of the batch is done, that is an acceptable outcome — report it as awaiting
   operator decision, not as incomplete work.
6. A full human UI walkthrough: click every button on every surface this batch touches —
   module review gate, soundtrack gate, Stackwell iteration gate, cost confirmation surface,
   production run — and
   exercise idea → draft → asset → media plan → render end to end. Report what you clicked
   and what happened. A green test suite is not a walkthrough.
7. `CHANGELOG.md` updated with one entry for this batch. `PROGRESS.md` updated.
8. `AMENDMENT-015` filed to `docs/decisions/`.
9. Any item you could not complete is filed as a divergence with the reason, not silently
   dropped and not worked around.

## Explicitly out of scope

- Do not rewrite `prompts/assembly/media_plan_v1.md`. A third divergent media planning path
  is worse than the two that exist.
- Do not modify `prompts/ideas/generate_v1.md`. The diversity defect is upstream in config.
- Do not change the encode tiers from the previous batch. The 3.33 Mbps measurement is
  correct CRF behaviour, not a defect.
- Do not self-approve any DRAFT or PROPOSED document.
- Do not add an approve-all or bulk-approve control to any gate, and in particular not to
  the module review gate.
- Do not generate any registry asset under P2-11. Plan and cost surface only. P2-10 is the
  single exception in this batch where generation occurs, and only one candidate at a time,
  only through the iteration gate, and only after P0-1.
- Do not generate the fan-out renders early because Stackwell's approval came in quickly.
  P2-11 is a plan in this batch regardless of how P2-10 lands.
