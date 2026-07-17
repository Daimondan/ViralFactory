# Viral Patterns Playbook — v3.1

## Runtime rules

These are gated StackPenni production rules derived from an admired-content corpus of 91 analyzed rows representing 90 unique pieces: 80 videos, 10 thumbnail/static analyses, and one duplicate row. Thumbnail-only items do not support audio, pacing, transition, or full-storyline claims. These rules are not guarantees of virality.

### Corpus-bias caveat (borrowed authority)

The corpus is a borrowed-authority set: every piece was already a public winner selected by third-party rankings, not a controlled or StackPenni-matched sample. Patterns observed in winners may reflect what the ranking sources valued (e.g., outrage-driven engagement bait, celebrity reach, algorithm-favored controversy) rather than what serves StackPenni's audience, brand, or publishing goals. Treat all corpus-derived patterns as transferable hypotheses requiring tenant validation, not as proven mechanics for this brand. A mechanic that correlates with reach in a general winner pool may conflict with trust, authority, or community goals that StackPenni prioritizes.

### Evidence labels

- **OBSERVED:** directly visible or audible in a source.
- **MEASURED:** captured platform metric.
- **HYPOTHESIS:** plausible explanation that must be tested.
- **HOUSE RULE:** an editorial or production choice.

Never describe a hypothesis or platform prior as tenant performance evidence.

### StackPenni-accessible patterns

The corpus includes formats and treatments that are not currently accessible to StackPenni's production capabilities (e.g., celebrity interviews, multi-camera studio setups, high-budget animation, licensed music beds). Patterns that require unavailable resources, permissions, or talent should be flagged as aspirational and excluded from active production rules until the capability gap is closed. Only patterns achievable with StackPenni's current tools (voice-over, generated imagery, text overlays, licensed SFX/music, reference-conditioned generation) should drive activeWriter and Assembler decisions. The gap between admired patterns and accessible patterns is itself a learning-loop input: it identifies capability investments to evaluate, not constraints to silently work around.

### Content contract

Every piece must establish:

1. one source-grounded core claim;
2. one audience value or change;
3. one primary emotional job;
4. one primary audience action (finish, share, save, comment, follow, or click);
5. one approved format and production-feasible treatment;
6. at least one particular detail, scene, receipt, quote, or lived observation.

### Opening

Orient immediately. In the first meaningful beat, make at least two clear: who/what this concerns, the tension or claim, why it matters, and the emotional register. The opening can be quiet; forced movement and false suspense are not hooks.

### Development

Choose the narrative movement that fits the idea. Useful patterns include:

- proof-first: claim → receipt → mechanism → implication → move;
- emotional reframe: recognizable moment → interpretation → deeper meaning → landing;
- contrarian: claim → conventional view → evidence → boundary/nuance → verdict;
- story: cold open → context → pressure → choice → consequence → meaning;
- practical list: promise → ordered utility → synthesis;
- reaction: source claim → reaction → context/evidence → own position → invitation;
- candid moment: real event → minimal orientation/reframe → natural payoff;
- curated excerpt: strongest quote → source label → essential excerpt → landing.

Do not force every idea into Hook–Tension–Reframe–Payoff. Each beat must create an earned change in understanding or feeling.

### Text on screen

Every overlay needs a declared function: hook, orientation, accessibility caption, emphasis, proof, reframe, or CTA. Remove decorative text. Do not require text on every segment. Keep captions phrase-level and VO-synced; preserve safe areas and visual hierarchy. Never ask a generator to render accurate text, numbers, logos, screens, charts, or evidence — the renderer owns those layers.

### Audio

Choose audio by narrative function: voice-only for clarity/intimacy; original sound for proof, atmosphere, or humor; music for pace, contrast, tension, continuity, or emotional color; silence for an intentional landing. SFX are optional and motivated, never a blanket whoosh-per-caption rule. Voice intelligibility wins.

### Visual assembly

Preserve useful authenticity. A hold is valid when expression, proof, or silence needs time. A cut is valid when the semantic beat, evidence, perspective, or energy changes. Do not impose a universal 2–4 second cut rule.

Media order: required real capture/evidence → approved archive/reference assets → stock for generic context → generated media for metaphor or deliberate art direction → text card when words should carry the frame. Every source must be local, registered, permitted, and referenced by its exact inventory ID.

### Ending

End when the meaning lands. A CTA is optional. If used, it must serve the declared audience action and must not replace the payoff.

## Observed patterns from the admired corpus

The 91 analyzable winners span candid UGC, talking heads, lectures, interviews, podcasts, archive/film clips, reactions, skits, montages, animations, and minimal text-led treatments. No single format dominates as a universal answer.

Recurring observations:

- specific human moments, lines, evidence, and contradictions carry more meaning than generic encouragement;
- many pieces make an assumption, emotion, or event newly legible through reframe, proof, or consequence;
- faces, voices, room tone, pauses, and imperfect real footage often supply human texture;
- text commonly orients, captions speech, emphasizes, reframes, labels proof, or invites interaction;
- successful audio treatments include voice-only, original sound, silence, music, and produced mixes;
- long and short pieces both appear among winners, so duration must follow sustained value rather than a fixed target.

## Performance hypotheses to test

- Immediate orientation may reduce early confusion.
- A concrete, source-grounded particular may improve recall and sharing.
- A clear change in viewer understanding or feeling may improve completion.
- Real human texture may increase trust when authenticity is central.
- Split-screen dialogue may increase comments when two defensible perspectives are present.
- Minimal text-led footage may increase sharing when one line genuinely reframes the moment.
- Comment-to-like ratio (comments ÷ likes) may distinguish debate-driven reach from passive consumption. A high ratio suggests the piece provokes response; a low ratio suggests passive agreement. StackPenni should track this ratio per piece to learn which treatments generate discussion versus approval, and whether discussion serves the brand's authority goal.

These are hypotheses. Test against StackPenni baselines and matched formats before promoting them to tenant evidence.

### Polarization house rule

Outrage and polarization mechanics (us-vs-them framing, manufactured conflict, identity-group attacks) appear in the corpus as high-comment drivers. They are not approved StackPenni production patterns. StackPenni's brand is Caribbean AI + wealth — authority, trust, and community are the assets. Polarization tactics that generate comments by alienating or caricaturing a group conflict with the brand identity and may damage long-term audience trust for short-term engagement metrics. If a piece's primary comment driver is manufactured outrage, flag it for operator review before drafting. Debate and contrarian takes are allowed; caricature and bad-faith provocation are not.

## Never list

- Never invent facts, quotes, metrics, screens, or documentary scenes.
- Never use a greeting or long preamble before the substance.
- Never bait-and-switch: the opening promise and payoff must match.
- Never add movement, B-roll, music, overlays, transitions, or SFX without a job.
- Never bake accurate text or interfaces into generated media.
- Never substitute unrelated uploads or unregistered stock for missing required captures.
- Never rewrite approved copy during assembly.
- Never call a pattern causal without a matched comparison and relevant performance metrics.

## Learning-loop fields

For each published piece, store the creative fingerprint: format, narrative pattern, hook mechanism, emotional job, primary audience action, text functions, audio mode, media mix, operator edits, and reliable platform metrics with capture date/confidence. Aggregate before proposing an exact gated module diff.

## Evidence limits

The source set is a selected collection of winners, not a controlled sample. Likes/comments are incomplete performance signals; views, reach, watch time, completion, saves, shares, and creator baselines were generally unavailable. Free-form AI analyses are scene/beat-level and may contain transcription or interpretation errors. Use the corpus to generate production hypotheses, not universal laws.

### Next evidence pass: cross-tab contrast sets

The corpus currently supports single-dimension tabulations (format × likes, audio × likes). The next evidence pass should capture cross-tab contrast sets: e.g., format × audio mode × comment-to-like ratio, or hook mechanism × emotional job × completion (when available). Cross-tabs reveal interaction effects that single-dimension averages mask — a format that looks weak overall may perform well within a specific audio mode and emotional job combination. Record these as structured fields per piece (see Learning-loop fields above) so future analysis can slice interactions without re-coding.

## Provenance

- Version: 3.1
- Updated: 2026-07-17
- Source: `docs/research/viral-content-meta-analysis-v2.md`
- Production playbook: `docs/playbooks/viral-content-production-playbook-v1.md`
- Schema: viral_patterns_v1