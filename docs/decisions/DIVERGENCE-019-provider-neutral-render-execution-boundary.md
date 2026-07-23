# DIVERGENCE-019 — Provider-neutral render execution boundary

**Filed:** 2026-07-22
**Status:** APPROVED AS ARCHITECTURAL DIRECTION; production provider selection remains gated by a two-provider bake-off
**Owner:** Architect
**Charter impact:** None. Charter v3.9 already permits swappable service adapters and requires immutable manifest-only assembly, exact provenance, human gates, and no auto-publish.

## Operator question

ViralFactory is producing good ideas and scripts, but the assembled videos still have weak captions, transitions, timing, pacing, composition, and final polish. Should final assembly stay in the custom FFmpeg/PIL renderer, move to Vizard, or use another service?

## Ruling

**Use a hybrid architecture. Keep ViralFactory as the creative and governance brain; move commodity timeline execution behind a provider-neutral renderer adapter. Do not use Vizard as the production assembler.**

The first controlled bake-off is:

1. **Creatomate — primary candidate.** Its RenderScript model exposes explicit timeline layers, element timing, tracks, trims, fit/crop behavior, keyframes/animations, transitions, audio elements, custom fonts, webhooks, and exact supplied word-level transcript data. That is the closest documented fit for ViralFactory's manifest-derived composition contract.
2. **Shotstack — second candidate and fallback contender.** Its Edit API exposes JSON tracks/clips, transitions, overlays, uploaded fonts, animations including volume, webhooks, and rich captions from supplied SRT/VTT with word-level effects. It has transparent usage pricing and explicit API/white-label positioning.
3. **Existing FFmpeg/PIL — conformance baseline and portable fallback, not the default quality ceiling.** Keep it for tests, emergency rendering, deterministic inspection, probing, hashing, loudness normalization, and any composition the selected provider cannot faithfully express.

No production vendor is selected from documentation alone. Creatomate and Shotstack must render the same frozen ViralFactory fixtures and pass operator blind review plus lineage/cost/reliability checks. The operator selects the winner; the adapter keeps that choice reversible.

## Why this is not a Vizard problem

Vizard's documented API begins with uploading or linking an existing long-form video, choosing a language and clip length, then retrieving generated clips. Its API can identify speakers, apply a template, add supplied media, and translate, but it is fundamentally a clipping/repurposing workflow. ViralFactory needs deterministic composition from separately approved narration, scenes, stills, captures, captions, typography, graphics, soundtrack, source sound, and SFX.

Using Vizard would transfer creative selection and reframing to another AI after ViralFactory's component gate. That creates silent substitution/content-drift risk and does not expose the exact per-layer timeline contract required by Charter v3.9. Vizard may later be tested as an optional derivative-clipping adapter for already approved long-form media, but not as the canonical assembler.

## Diagnosis: what a render vendor will and will not fix

### Failures before rendering — a vendor cannot fix these

- Missing or unusable visuals.
- Missing, partial, or unmeasured VO segments.
- Human waits that do not resume from durable state.
- First-child ownership in multi-platform production.
- Mutable/latest inventory rather than exact approved candidates.
- Missing rights, cost, preview, hash, or approval lineage.
- Gate 3 approval without a current artifact, manifest, and blocking evidence.

VF-CW-001..012 remain mandatory. An external renderer must not become a shortcut around the Component Workbench or manifest freeze.

### Specification failures — ViralFactory must fix these before any renderer can succeed

- Captions are phrase-chunked, but remain proportionally timed when word timestamps are absent.
- The cue compiler can request transitions that the current renderer does not implement faithfully; unsupported values silently become hard cuts at execution.
- The present render plan does not carry the full approved SFX/source-sound composition into each segment.
- Many desired roles—hook graphics, proof cards, lower thirds, charts, split layouts, and deliberate per-word caption motion—are style names rather than a complete executable composition.
- Visual crop, focal point, keyframed motion, audio gain envelopes, and sidechain ducking are under-specified.

The fix is a canonical **RendererSpec v1**, not vendor-specific judgment in Python.

### Render-execution failures — a stronger renderer can fix these

- Crude static PIL caption plates.
- Limited text animation and layout.
- One-size-fits-all transitions.
- Weak layer composition and motion graphics.
- Hard-to-maintain FFmpeg filter graphs.
- Slow iteration on visual polish.
- Inconsistent crop/fit/keyframe behavior across stills and clips.

## Constitutional boundary

The binding path is:

`approved components → immutable manifest → RendererSpec v1 → selected renderer adapter → downloaded local artifact → hash/probe/evidence → Gate 3`

The renderer:

- **may** execute exact layers, timing, transitions, keyframes, text layout, and audio automation;
- **must not** choose or regenerate ingredients, rewrite text, transcribe as the authority, add stock media, add emojis/hashtags, change captions, or publish;
- **must not** receive an open-ended prompt such as "make this viral";
- **must not** make semantic decisions that bypass Visual Director, Writer, component approval, or Gate 3.

Any vendor AI feature is disabled unless separately designed as a proposal-producing step before component approval.

## RendererSpec v1 — required provider-neutral contract

The builder must define and schema-validate a canonical spec generated mechanically from the current immutable manifest and approved edit plan.

### Identity and lineage

- `spec_version`
- tenant/business, production session, platform asset, manifest ID/hash
- approved Writer contract, VO timing, module/config/style hashes
- canonical spec hash and idempotency key
- exact renderer adapter/config version

### Output contract

- dimensions, aspect ratio, frame rate, duration, codec/container, color space
- safe zones and platform preview geometry
- target loudness/true peak and audio sample rate

### Visual timeline

- frame- or millisecond-exact layer start/end and z-order
- source artifact ID/hash plus provider-readable staged URL
- trim in/out, fit mode, crop/focal point, opacity, mask, blend
- position/scale/rotation and explicit keyframes/easing
- transition type, duration, parameters, and reason/reference
- no implicit auto-placement or silent fallback

### Text and graphics

- exact approved display text and text hash
- role, start/end, safe region, line/word grouping
- supplied word timestamps where required
- exact font artifact/hash and style-token/config hash
- deterministic size/wrap/alignment/stroke/shadow/background
- entry/exit/per-word animation with explicit keyframes
- versioned composition/template/graphic ID and hash

### Audio

- exact VO, soundtrack, source-sound, and SFX artifact IDs/hashes
- timeline placement, trims, channel role, gain envelopes, fades
- explicit ducking/automation contract; no guessed mix
- final local loudness normalization and verification remains authoritative

### Execution policy

- required capability list and fail-closed preflight
- no provider transcription or stock/generative substitution
- no default template or effect when a declared feature is unsupported
- output retention/export policy and expected cost estimate

## Adapter contract

Each provider adapter must implement the same boring mechanics:

1. `validate_capabilities(spec) -> structured blockers`
2. `estimate(spec) -> provider, units, currency, estimate evidence`
3. `submit(spec, idempotency_key) -> provider_job_id`
4. `get_status(provider_job_id)` plus authenticated webhook reconciliation where available
5. `cancel(provider_job_id)` when supported
6. `download(provider_job_id) -> local immutable file`
7. `collect_evidence() -> request hash, provider response/status, timings, cost, output identity`

The orchestration layer persists provider job ID, spec hash, idempotency key, attempts, webhook/poll history, timestamps, provider region where exposed, cost, downloaded artifact hash, and terminal reason. Retries reuse the same identity and cannot create a second authoritative artifact silently.

All external outputs are untrusted until locally downloaded, hashed, ffprobed, duration/stream checked, text/audio/visual evidence completed, and linked to the current manifest. Green provider status is not Gate 3 readiness.

## Bake-off protocol

### Fixed inputs

Render the same immutable, redacted fixtures through:

- current FFmpeg/PIL baseline;
- Creatomate;
- Shotstack.

At minimum include:

1. a normal 9:16 Reel with mixed still/video media, exact VO, phrase captions, hook/proof/CTA graphics, soundtrack, and at least three motivated transition types;
2. an adversarial Reel with long words, punctuation, fast and slow speech, safe-zone pressure, still-image motion, a split composition, source sound/SFX, and a platform-duration boundary;
3. two tenant/style fixtures producing visibly different treatment from the same generic composition structure with zero Python edits.

### Blind operator judgment

Label outputs A/B/C, not by provider. Daimon reviews:

- caption synchronization, readability, line breaks, and emphasis;
- pacing and whether cuts/transitions feel motivated rather than templated;
- crop/focal framing and still-image motion;
- hierarchy and polish of hooks, proof, lower thirds, charts, and CTA;
- VO/music/source-sound/SFX balance;
- fidelity to approved text and selected components;
- whether the result looks native rather than AI/template-made.

### Mechanical and operational evidence

For each output record:

- identical semantic spec hash or an explicit provider lowering map;
- every consumed input ID/hash and every lowered feature;
- no text or component drift;
- output hash, ffprobe facts, duration/frame-rate/resolution, loudness facts;
- submit-to-ready time, retries, webhook behavior, errors, and downloaded-file availability;
- actual provider charge and storage/egress facts;
- terms/privacy/data-retention and commercial multi-tenant review.

Thresholds and budgets are set in config before production integration. Unsupported mandatory features fail the candidate; they are not silently removed.

### Creatomate trial-credit guard

The operator has 50 Creatomate trial credits. Creatomate documents one video credit as 100 million output pixels, rounded up per render; width, height, frame rate, and duration therefore all affect consumption. The Creatomate spike must estimate and persist projected credits before submission and use this maximum planned budget:

| Stage | Output | Planned renders | Credits |
|---|---:|---:|---:|
| Transport smoke | 540×960, 24 fps, 5 seconds | 1 | 1 |
| Isolated captions/transitions/audio previews | 540×960, 24 fps, 15 seconds | 3 | 6 total |
| Integrated normal/adversarial previews | 540×960, 24 fps, 30 seconds | 2 | 8 total |
| Quality proof | 720×1280, 25 fps, 45 seconds | 1 | 11 |
| Full-resolution crop/type proof | 1080×1920, 30 fps, 12 seconds | 1 | 8 |
| **Planned maximum** |  |  | **34** |
| **Failure/retry reserve** |  |  | **16** |

Validate schema, URLs, hashes, durations, capability lowering, and idempotency locally before any paid submission. Never spend the 16-credit reserve merely to iterate on JSON syntax or cosmetic guesses. A request that would exceed the remaining planned stage budget requires an explicit operator decision. Dashboard/API-log usage is the authoritative actual-credit record.

#### Live smoke evidence — 2026-07-23

Operator-authorized direct RenderScript testing proved that this Creatomate project can render without a template. One initial Python `urllib` request was rejected by the edge with HTTP 403 / code 1010 and created no render. A standards-compliant client then created and downloaded two successful five-second portrait H.264 renders while diagnosing output scaling. Both provider jobs reported no `template_id`, 24 fps, five seconds, `render_scale: 0.5`, and 270×480 output from a 540×960 composition; explicitly requesting `render_scale: 1` did not change the provider-reported 0.5 scale. Both local files had the same SHA-256, proving deterministic output for this static fixture. Visual inspection found the cream background and centered orange text, no visible watermark, and an apparent sans-serif fallback instead of the requested Georgia serif.

The two successful renders are expected to cost one credit each; the dashboard API Log remains authoritative. Treat the second credit as consumed from the retry reserve: projected total is now 35 and reserve is 15 if the remaining stages proceed unchanged. **Do not submit another paid render until the 0.5 scale override and font fallback are explained or accepted as explicit trial limitations.** This smoke proves transport and template-free execution only; it does not satisfy the quality/provider-selection gate.

#### Shotstack sandbox smoke evidence — 2026-07-23

The operator identified the supplied Shotstack credential as a sandbox key. An operator-authorized call therefore used only `https://api.shotstack.io/edit/stage/render`; no production endpoint or AI asset was invoked. The sandbox returned plan `sandbox`, completed one five-second timeline, and produced the exact requested 540×960, 24 fps H.264 output. The artifact was downloaded outside the repo, SHA-256 hashed, and visually inspected. The cream background, centered orange Montserrat text, wrapping, and vertical composition rendered correctly. The expected Shotstack sandbox watermark appeared at top left. Shotstack also inserted an AAC audio stream despite no audio asset; it measured as digital silence at approximately -91 dB and must not be mistaken for approved audio evidence.

This materially improves Shotstack's transport/exact-dimension evidence relative to the Creatomate trial smoke, but it is still only a static sandbox card. It does not prove captions, source clips, transitions, keyframes, custom fonts, audio envelopes, webhooks, production watermark removal, cost, or multi-tenant fidelity. Do not select Shotstack from this smoke alone.

#### Operator-supplied reference recreation — 2026-07-23

The operator then requested a direct, provider-labeled recreation of an 8.9-second 1080×1920 reference video. The Google Drive download matched the existing local `netflix_v2_styled.mp4` byte-for-byte, so the bake-off used the exact component construction rather than visually inferred substitutes: one immutable base-video hash, one transparent caption-overlay hash, and one exact mechanically transcoded soundtrack hash. Both providers received one common 8.9-second, 24 fps fixture contract with spec hash `058d415d9850f1e9f999a878c9fd853bbd8916d6bb047c3b1f72b593e6877e3b`. Every temporary provider-readable input was downloaded back and matched locally before submission.

Shotstack stage job `eed6b4f7-f155-4bc5-a283-a3814d1251f0` returned the exact 540×960 target in 12.67 seconds. The locally verified file was H.264/AAC, 24 fps, 8.917 seconds, 3,974,227 bytes, SHA-256 `fe2bc874cc9c15d1eb0d90f5ab6b4ae54ad6729e6c803c8d13caffc9e9aa19ed`, with -15.3 LUFS / -1.3 dBFS peak audio. Composition, timing, caption alpha, framing, and color were faithful; the expected sandbox watermark remained. Critically, two prior `done` jobs were video-only when the request explicitly carried `output.mute: false`; omitting the property restored audio. An earlier M4A soundtrack was also omitted. Provider success cannot therefore prove audio presence, and the adapter must omit the buggy false-valued field, preflight audio transport format, and keep local stream/loudness checks blocking.

Creatomate job `cbdc2a55-b8b4-4f11-8213-70cf31c070b1` completed in 7.64 seconds with faithful composition, exact overlay timing/alpha, correct audio, and no visible watermark. Its locally verified H.264/AAC file was 24 fps, 8.917 seconds, 675,924 bytes, SHA-256 `9e29f201d185b48d1a7284327a1a78262e84b623c08730cd26aec0158a2c3343`, with the same -15.3 LUFS / -1.3 dBFS measurements. The trial/project nevertheless returned only 270×480 and reported `render_scale: 0.25` from the 1080×1920 logical canvas; explicit requested scales 0.5 and 1.0 produced distinct job IDs but byte-identical 270×480 files. Exact-size compliance remains unproven until the account/project can render above this apparent 480-pixel portrait cap. Each actual 270×480 job estimates to one rounded-up credit; the Creatomate dashboard/API Log remains authoritative.

Mechanical comparison against the reference downscaled to each actual output produced SSIM/PSNR of 0.922184/25.583 dB for Shotstack and 0.961144/33.485 dB for Creatomate. These are not directly rankable: Shotstack's watermark depresses its score, while Creatomate is measured after a much stronger downscale. Human inspection found no content/component drift in either. Shotstack wins exact preview resolution; Creatomate wins clean appearance and successful-job latency; neither wins production selection.

This was not VF-RA-003's blind gate. It was provider-labeled and uses a pre-rendered caption PNG over one continuous clip, so it does not test native typography, word-level captions, transitions, focal keyframes, graphics, gain automation, tenant differentiation, production watermark removal, webhooks/recovery, privacy/retention, or commercial cost. Full evidence and artifacts are recorded in `docs/reviews/REVIEW-reference-video-renderer-bakeoff-2026-07-23.md`.

## Provider comparison

| Candidate | Fit | Decision |
|---|---|---|
| **Creatomate** | Arbitrary RenderScript layers, timing/tracks, composition, trims, fit/crop, animations/keyframes, transitions, audio, custom fonts, webhooks, supplied word-level transcript data | **First bake-off candidate** |
| **Shotstack** | Mature JSON timeline API, transitions/overlays, volume animation, custom fonts, webhooks, rich captions from supplied SRT/VTT, transparent usage pricing | **Second bake-off candidate / likely operational fallback** |
| **Remotion** | Maximum control and portability; React composition, local/server rendering, transitions, caption primitives, Lambda | **Reserve option** if hosted APIs cannot meet fidelity or economics; higher engineering/operations burden and risks rebuilding the renderer in another language |
| **JSON2Video** | JSON scenes/elements, subtitle element, transitions, webhooks, flat monthly minute plans | **Reserve only**; spike later if first two fail. Documented webhook is unsigned and retries are not automatic, raising orchestration work |
| **Vizard** | Strong long-video-to-clips workflow and derived social clips | **Reject for canonical assembly**; optional future derivative-clipping adapter only |
| **Plainly / Canva / template-only renderers** | Strong template automation, weaker evidence for arbitrary per-piece timeline lowering | **Do not shortlist now** |

## Cost posture

Do not choose on headline subscription alone. Normalize actual bake-off cost to:

- successful downloaded minute;
- failed/retried minute;
- storage/egress and concurrency;
- operator iteration count;
- engineering time required for unsupported features.

At research time, Shotstack documents pay-as-you-go pricing starting at **$0.30/min** and subscriptions starting at **$39/month plus $0.20/min**, with API access on all plans. Creatomate documents one credit as 100 million output pixels, rounded up per render; its own example prices one minute at 1280×720 and 25 fps at about 14 credits. Resolution, frame rate, and duration therefore matter, and 1080×1920 vertical output costs materially more than a 720p preview. API access is available on all plans. These facts are spike evidence only and must not be hardcoded as production pricing; re-check before commitment.

## Build order

1. Keep VF-CW-001..010 in order. Do not delay exact component identity.
2. Implement `VF-RA-001` after the manifest schema is stable: RendererSpec v1, capability registry, local FFmpeg lowering, conformance fixtures.
3. Implement `VF-RA-002`: thin Creatomate and Shotstack spike adapters, same frozen fixtures, no production route.
4. Complete `VF-RA-003`: blind operator review, mechanical/cost/terms evidence, select primary and fallback through an appended ruling here.
5. Implement `VF-RA-004`: production adapter, durable job/webhook reconciliation, local import/hash/probe/evidence, no external publish.
6. Complete VF-CW-011 and VF-CW-012 against the selected adapter and the local fallback before fresh VF-VS-516/702/703 proof.

## Hard stops

- No direct vendor call from Flask routes.
- No vendor-specific fields in the immutable component manifest.
- No open-ended vendor editing or generative features after manifest freeze.
- No authoritative provider-hosted URL; the final must be downloaded and hashed locally.
- No provider success state shown as "Ready" until local blocking evidence passes.
- No silent capability degradation or fallback to a different renderer.
- No production credential in repo, DB, logs, fixture, provenance payload, or client-side HTML.
- No vendor lock-in: canonical spec and evidence remain provider-neutral and local fallback remains executable.

## Official research sources checked 2026-07-22

- Vizard API: <https://docs.vizard.ai/docs/introduction>, <https://docs.vizard.ai/docs/basic>, <https://docs.vizard.ai/docs/advanced>, <https://docs.vizard.ai/docs/retrieve-video-clips>
- Creatomate API: <https://creatomate.com/docs/api/reference/create-a-render>, <https://creatomate.com/docs/api/render-script/element-properties>, <https://creatomate.com/docs/api/render-script/the-timeline>, <https://creatomate.com/docs/api/render-script/text-element>, <https://creatomate.com/docs/api/quick-start/provide-your-own-subtitles>, <https://creatomate.com/docs/api/reference/limits-and-concurrency>, <https://creatomate.com/pricing>
- Shotstack API: <https://shotstack.io/docs/api/>, <https://shotstack.io/docs/guide/architecting-an-application/rich-captions/>, <https://shotstack.io/docs/guide/architecting-an-application/animations/>, <https://shotstack.io/docs/guide/architecting-an-application/webhooks/>, <https://shotstack.io/pricing/>
- Remotion: <https://www.remotion.dev/docs/renderer/render-media>, <https://www.remotion.dev/docs/transitioning>, <https://www.remotion.dev/docs/captions>, <https://www.remotion.dev/docs/lambda>, <https://www.remotion.dev/docs/license/pricing>
- JSON2Video: <https://json2video.com/docs/v2/reference/json-syntax>, <https://json2video.com/docs/v2/reference/json-syntax/element/subtitles>, <https://json2video.com/docs/v2/tutorials/03-multiple-scenes-and-transitions>, <https://json2video.com/docs/v2/reference/webhooks>, <https://json2video.com/pricing/>

## Final decision statement

ViralFactory was not wrong to own assembly semantics, but it went too low-level by making FFmpeg/PIL the creative finish layer. The correction is not to hand the finished script to another AI editor. The correction is to compile ViralFactory's exact approved decisions into a portable render specification and let a specialized renderer execute it. **Start with Creatomate and Shotstack; reject Vizard for canonical assembly; preserve local FFmpeg as the verified fallback.**
