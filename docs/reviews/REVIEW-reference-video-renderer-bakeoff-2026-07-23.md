# Review — Reference-video Creatomate vs Shotstack recreation

**Date:** 2026-07-23
**Reviewer:** Architect
**Operator request:** Recreate the supplied Google Drive reference in both systems and compare the outputs.
**Scope:** Isolated, non-production provider bake-off outside Flask/runtime routes. No AI asset generation, templates, publication, Gate 3 decision, or production integration.
**Verdict:** Both providers reproduced the frozen composition faithfully at their available preview constraints. Shotstack met the requested 540×960 output contract but added its sandbox watermark and exposed a dangerous audio-output quirk. Creatomate produced the cleaner, faster-looking output with no visible watermark, but its trial/project enforcement returned only 270×480. This fixture does not select a production renderer because it uses a pre-rendered caption overlay and contains no transition/keyframe/native-text challenge.

## Constitution and fixture boundary

The test preserves DIVERGENCE-019's boundary:

`frozen inputs → one provider-neutral fixture spec → provider lowering → provider job → local download → SHA-256 → ffprobe/FFmpeg/visual evidence`

The original Google Drive file was downloaded directly and verified byte-for-byte against the existing local `data/media/netflix_experiment/netflix_v2_styled.mp4`. That proved the exact source construction was available rather than inferred from screenshots.

No vendor was allowed to select media, transcribe, rewrite text, add stock/generative assets, publish, or act as Gate 3. Temporary transport URLs and provider credentials are excluded from this record.

## Frozen fixture

### Reference

- File: Google Drive ID `1N9njkcUdQTagujrcajtxFCGkEipBbSlu`
- SHA-256: `59f711dd2578915bb56c50b0dc78171dc45fda9ca2adf4f9bc93a17404917186`
- Video: 1080×1920, H.264, 24 fps, 8.875 s video stream
- Audio: AAC, 96 kHz stereo, 8.9 s
- Container duration: 8.9 s
- Measured audio: -15.0 LUFS integrated, -1.0 dBFS true peak

### Final common inputs

| Role | Exact input | SHA-256 |
|---|---|---|
| Base video | `raw_interview.mp4` | `debf00caa6cccfd2da08271b4bb92be0707b12579a286f4789a11c64fb5ed45a` |
| Soundtrack | Reference audio extracted then mechanically transcoded to 192 kbps MP3, 48 kHz stereo | `c37b8d980f65dbc4d66b6f2440690b04ae37532ee845e966effec4ed4d823ce5` |
| Caption graphic | `caption_overlay.png`, transparent 1080×1920 | `69844ed173d9e2dce564a300963033f38137fc71206db2c1a85c4349bc94cf37` |

Every temporarily hosted input was downloaded again before submission and matched its local SHA-256. The final provider-neutral fixture hash was:

`058d415d9850f1e9f999a878c9fd853bbd8916d6bb047c3b1f72b593e6877e3b`

The common timeline was:

- 9:16 black canvas
- 24 fps
- 8.9 seconds
- base video at `0.0–8.9`, aspect-preserving contain, embedded source audio muted
- exact caption PNG at `1.0–8.9`, transparent full-canvas overlay
- exact MP3 soundtrack at `0.0–8.9`

This fixture deliberately tests source transport, aspect-preserving video composition, transparent overlay fidelity, timing, audio inclusion, encode facts, and output-contract behavior. It does **not** test provider-native typography, word-level captions, transitions, focal keyframes, graphics generation, or audio gain automation because the reference itself bakes its caption into a PNG and uses one continuous background clip.

## Result table

| Fact | Reference | Shotstack sandbox | Creatomate trial/project |
|---|---:|---:|---:|
| Provider job | — | `eed6b4f7-f155-4bc5-a283-a3814d1251f0` | `cbdc2a55-b8b4-4f11-8213-70cf31c070b1` |
| Output size | 1080×1920 | **540×960 requested and delivered** | **270×480; requested target not delivered** |
| Frame rate | 24 fps | 24 fps | 24 fps |
| Container duration | 8.900 s | 8.917 s | 8.917 s |
| Video codec | H.264 | H.264 | H.264 |
| Video bitrate | 4.19 Mbps | 3.33 Mbps | 359 kbps |
| Audio | AAC, 96 kHz stereo | AAC, 48 kHz stereo | AAC, 48 kHz stereo |
| Audio bitrate | 174 kbps | 230 kbps | 241 kbps |
| Integrated loudness | -15.0 LUFS | -15.3 LUFS | -15.3 LUFS |
| True peak | -1.0 dBFS | -1.3 dBFS | -1.3 dBFS |
| Local bytes | 4,854,804 | 3,974,227 | 675,924 |
| Local SHA-256 | `59f711…17186` | `fe2bc8…a19ed` | `9e29f2…c3343` |
| Successful-job ready time | — | 12.67 s | 7.64 s |
| Visible watermark | No | **Yes — sandbox watermark** | No |
| Estimated test charge | — | Sandbox stage; no AI assets | 1 credit per 270×480 render; dashboard/API Log authoritative |

## Mechanical similarity evidence

The provider outputs were compared frame-by-frame against the reference downscaled to each provider's actual resolution:

- Shotstack at 540×960: SSIM `0.922184`, PSNR `25.583 dB`
- Creatomate at 270×480: SSIM `0.961144`, PSNR `33.485 dB`

These values are evidence, not a provider ranking. Shotstack's large sandbox watermark materially depresses its score, while Creatomate is compared after the reference is downscaled to one-quarter of the reference pixel count, which smooths fine differences. The metrics are therefore not directly comparable across providers.

Human frame inspection found that both providers preserved:

- the same subject framing and movement sequence;
- the caption's exact wording, four-line wrap, rounded translucent pill, placement, and start time;
- the transparent PNG alpha edges without a visible opaque rectangle;
- the expected narrow aspect-preserving edge treatment;
- color and contrast closely enough that the provider panels do not show content or component drift.

Visible differences:

- Shotstack's sandbox watermark occupies the lower part of every frame and prevents a clean aesthetic judgment.
- Creatomate is visibly softer when enlarged to 540×960 because its provider artifact is only 270×480.
- No panel was clipped or misframed in the locally generated side-by-side artifact.

## Provider-specific findings

### Shotstack

1. **Exact preview dimensions passed.** The stage API returned 540×960 at 24 fps.
2. **Audio can silently disappear while the job is `done`.** The same fixture produced video-only files when the output payload explicitly included `"mute": false`. Removing the `mute` property produced the expected AAC stream. A provider `done` state therefore cannot prove soundtrack presence; local stream/loudness checks remain mandatory.
3. **M4A soundtrack input also yielded no audio.** The final common fixture used MP3 after this was observed. The adapter must preflight supported transport formats or transcode mechanically before submission.
4. **Sandbox watermark blocks final quality scoring.** Production/unwatermarked output remains untested.
5. **Ingest friction remains.** The sandbox Ingest upload endpoint rejected this account/key with an `ownerId` validation error, so both renderers consumed the same independently hosted, hash-verified temporary inputs instead.
6. **No spend boundary was crossed.** Only the stage endpoint was used and no Shotstack AI asset was requested.

### Creatomate

1. **Composition fidelity was clean.** No visible watermark; exact transparent overlay and audio were preserved.
2. **The trial/project output cap remained binding.** A logical 1080×1920 composition returned 270×480 with provider-reported `render_scale: 0.25`. Requests with `render_scale` 0.5 and 1.0 produced new render IDs but byte-identical 270×480 files. This is consistent with a 480-pixel portrait cap or equivalent trial/project enforcement; the exact account rule is not proven by the API response.
3. **Ready time was lower in this fixture.** 7.64 s versus Shotstack's 12.67 s successful final.
4. **Exact-size production compliance remains unproven.** A paid/project setting capable of at least 540×960—and ultimately 1080×1920—must be tested before selection.
5. **Credit evidence remains conservative.** At actual 270×480, 24 fps, 8.917 s, each render projects to one rounded-up credit. Two byte-identical reference jobs were created while diagnosing the cap; the dashboard/API Log is authoritative for whether cache reuse changed billing.

## Operational ruling

For this one reference fixture:

- **Shotstack wins exact preview resolution.** It delivered 540×960 and a higher-bitrate output.
- **Creatomate wins clean preview appearance and successful-job latency.** It had no visible watermark and rendered the frozen composition faithfully, but only at 270×480.
- **Neither wins production selection.** Shotstack's explicit `mute: false` false-green is a serious adapter trap, and Creatomate's trial/project cap prevents exact target-resolution proof.

The previous wording that Creatomate was the presumptive primary candidate must now be treated only as a documentation-based starting order, not an evidence-based preference. Live evidence currently supports **continued neutral evaluation**.

VF-RA-003 remains open because this run was operator-directed and provider-labeled, not a blind A/B/C; it lacks the mandatory normal/adversarial transition, native-caption, graphics, keyframe, audio-automation, two-tenant, production watermark, retention/privacy, webhook/recovery, and actual commercial-cost evidence.

## Verified artifacts

Outside the repository:

- Shotstack provider artifact: `/home/daimon/renderer-bakeoff/shotstack-reference-eed6b4f7-f155-4bc5-a283-a3814d1251f0.mp4`
- Creatomate provider artifact: `/home/daimon/renderer-bakeoff/creatomate-reference-cbdc2a55-b8b4-4f11-8213-70cf31c070b1.mp4`
- Labeled local comparison: `/home/daimon/renderer-bakeoff/reference-vs-shotstack-vs-creatomate.mp4`
- Comparison SHA-256: `814f5e1160a837c9b48a2128c7027c230dce31e3acfd9e753838a5b6a1cece3e`

The comparison video displays the 1080×1920 reference downscaled to 540×960, the native 540×960 Shotstack artifact, and the native 270×480 Creatomate artifact enlarged to 540×960, with provider labels. It is a review aid, not a new authoritative provider output.
