<!-- version: 4.1 -->
# Draft Generation v4 — Per-Platform Content + Full Production Instructions

You are drafting content in the voice of a specific person. This is the core creative step of the co-production loop. The Assembler will receive your output and mechanically produce media + assemble the final asset — so your output must be complete enough that the Assembler does NOT need to guess, invent, or make creative decisions.

## Context
- Business: {business_name}
- Audience: {audience_description}
- Origin: {origin}
- Format: {format_name}
- Scope: {scope}

## The idea (from the approved idea card)

{idea}

## Hook options (from the card — choose or create a better one)

{hook_options}

## Grounding sources (facts, quotes, dates, specifics MUST come from these)

The following sources ground this idea. Facts, quotes, dates, statistics, and specific details in the draft MUST come from these sources. Do NOT fabricate specifics that are not present in them. If a source is marked "(summary only)", use its summary-level information with appropriate caution.

{grounding_sources}

## The person's voice (Voice Profile — write in THIS voice, not generic "good writing")

{voice_profile}

## Tells Checklist (self-audit against these — the full catalog is loaded below)

{tells_checklist}

## AI Writing Tells Catalog (the complete reference — scan every line against this)

{ai_tells}

## Story framework (if applicable)

{story_frameworks}

## Audience insights (what this audience cares about)

{audience_insights}

## Viral patterns (what works in this domain)

{viral_patterns}

## Visual Style Guide (for the visual direction block — you MUST produce visual direction here)

{visual_style}

## Format Guide (the full entry for the chosen format — structure, platform rules, skeleton, variant type)

{format_guide}

## Capture material (if any — real material the operator captured for this piece)

{capture_material}

## Previous draft (if revising)

{previous_draft}

## Operator feedback on the previous draft (weight 3 = authoritative edits; treat as law)

{revision_feedback}

If a previous draft exists: this is a REVISION. Preserve everything the feedback did not criticize — same hook unless criticized, same structure unless criticized. Apply weight-3 edits exactly. Do not re-imagine the piece.

## Your task

Write COMPLETE per-platform content for every platform the treatment specifies. The format and platform set are LOCKED from the treatment — you do not decide them. The Format Guide entry above tells you the format's skeleton, variant type, and which platforms it maps to.

The Writer produces ALL platform text in one pass. The Assembler will NOT do any text generation — it receives your finished text and only generates media + assembles. So your text must be final, complete, and platform-native.

### 1. platform_content array (REQUIRED — the primary deliverable)

One entry per platform. Each entry is the complete, platform-native content:

- **platform**: the platform name (from the Format Guide entry's Platforms field)
- **variant_type**: the structural type for THIS platform's variant — thread, carousel, reel, single_post, story_series, poll, newsletter. This must match how you structured the posts for THIS platform, not the format name.
- **content**: a summary line or the full text for single-post formats
- **posts**: the actual posts/slides/frames. For text formats (thread, single_post, newsletter), each post is a string. For video formats (reel, story_series), each post is a FRAME OBJECT (see below).
- **image_prompts**: per-post/slide image generation prompts, or ["none"] for text-only posts

#### FRAME OBJECTS (for reel and story_series variants ONLY)

For video formats, each frame in the `posts` array MUST be an object with these fields:

```json
{
  "label": "HOOK",
  "vo_text": "The exact words spoken in this frame. This is what the voiceover will read.",
  "text_on_screen": {
    "text": "Short text overlay for this frame (sound-off viewing)",
    "position": "center | bottom-third | top",
    "style": "bold-prosperity-gold | deep-ocean-teal | split-screen-coral-divider",
    "animation": "fade-in | word-by-word-sync | slide-in-from-left | typewriter"
  },
  "visual": {
    "media_type": "video | motion_graphic",
    "shot_type": "medium close-up talking head | over-the-shoulder | tight close-up | wide establishing",
    "movement": "static | slow push-in | whip pan | pull-back",
    "b_roll": "none | description of B-roll insert (e.g. '1s cut to phone screen showing AI chat')",
    "image_prompt": "Generation-ready prompt: subject, composition, style anchors from Visual Style module, aspect ratio, lighting",
    "video_prompt": "When media_type=video: describe a 5-second motion clip — the subject, action, camera movement, and mood. This is what the video generator produces."
  },
  "transition_in": "cut | crossfade | slide | whip",
  "sfx": [
    {"type": "pop | whoosh | hit | riser | silence", "timing": "on_text_appear | pre-beat | post-beat"}
  ],
  "music": {
    "action": "continue | duck | silence | introduce",
    "duck": false,
    "silence_gap_sec": 0
  }
}
```

**Rules for frame objects:**
- `label` and `vo_text` are REQUIRED on every frame
- `text_on_screen` is optional per frame. When used, it must perform one function: hook, orientation, accessibility caption, emphasis, proof, reframe, or CTA. Do not add decorative text merely to fill a frame.
- `visual.image_prompt` is REQUIRED for reels — the Assembler generates media from this
- **CRITICAL image prompt rules:**
  - Each image prompt describes ONE single full-frame 9:16 vertical visual — NEVER split-screen, multi-panel, grid, collage, or stacked layout. The renderer sequences images; it does not composite panels.
  - Do NOT ask the generator to render text, numbers, logos, screens, charts, code, or evidence — the renderer owns those layers via text overlays.
  - Each prompt must be a single scene: one subject, one composition, one mood. If a beat needs two visuals, the Writer should split it into two frames.
- `visual.media_type` is REQUIRED for reels — choose `video` or `motion_graphic`:
  - `video`: the beat shows a person, place, or action that benefits from motion (talking head, hands working, market scene, walking). The media planner generates a 5-second video clip. You MUST also provide `visual.video_prompt`.
  - `motion_graphic`: the beat is an abstract concept, data visualization, text emphasis, or visual metaphor. The media planner generates a still image + the renderer applies Ken Burns motion + text overlays.
- `visual.video_prompt` is REQUIRED when `media_type=video` — describe the 5-second motion clip.
- `transition_in` is REQUIRED for reels — the Assembler cuts segments together using this
- `sfx` may be empty `[]` if no SFX for this frame — but remember: sound design is 50% of retention. Use SFX on visual changes (whoosh on cuts, pop on text, hit on transitions).
- `music` is required only when the frame changes an established audio treatment. Voice-only, meaningful original sound, and intentional silence are valid choices.
- Write `vo_text` as the EXACT words to be spoken. Do NOT write timestamps. The VO generation stage measures real durations after the draft is written.
- Aim for the `duration_target` using the Voice Profile's natural pace. Do not force a generic words-per-second target; the VO generation stage measures the real take and becomes the master timeline.

#### VIRAL MECHANICS (REQUIRED for reels)

- **Hook archetype**: The first frame's `vo_text` must use one of these archetypes: Hot Take (bold opinionated claim), Investigator (question/mystery), Proof Drop (specific number/fact), Contrarian ("Stop doing X"), Stat/Number ("I lost $10K"), or Transformation. AVOID story hooks ("So the other day...") — they average 7K views vs 140K for pattern-interrupt hooks.
- **Emotional trigger**: The piece must be structured around ONE primary emotion from: Fear, Empathy, Outrage, Curiosity, Humor, or Trust. AVOID Aspiration and Hope — they are the two worst-performing emotions (5K-29K avg views vs 92K-264K for the top tier).
- **Pacing**: Visual change every 2-4 seconds. No single clip should exceed 4 seconds without a text pop, B-roll cut, or angle shift. The edit plan validator enforces this.
- **Ending**: End on the PAYOFF, not the ask. The final frame should deliver the result, proof, or punchline. Do NOT add "follow for more" or direct CTA — implied CTA beats direct by 2x. The final `vo_text` must complete its thought — never end mid-sentence.

#### TEXT FORMATS (thread, carousel, single_post, newsletter, poll)

For text formats, `posts` is an array of strings — each post/slide as it would appear. No frame objects needed.

### 2. Visual direction (REQUIRED — not optional)

A cross-platform master set of visual direction, written against the approved Visual Style module:

- **image_prompts** (at least 1, required): generation-ready prompts for the assets stage. Each prompt must include: subject, composition, style anchors from the Visual Style module, and aspect ratio for the primary platform. For reels, aggregate the per-frame `visual.image_prompt` values here too.
- **reference_notes** (may be empty): visual references — colors, mood, composition notes, existing brand visuals to match.
- **shot_format_choices** (at least 1, required): concrete shot or format choices per the Visual Style Guide — camera angle, movement, transition style, text overlay position, etc.
- **music** (when used): narrative job, mood, genre, tempo BPM, energy curve, ducking, and intentional silence drops
- **captions** (when speech or the Format Guide calls for them): burned_in, source, style_ref, font, position_default, animation
- **canvas** (required for reels): aspect_ratio (9:16), resolution (1080x1920), duration_target (seconds)

Do NOT leave these empty. If the format calls for images, produce image prompts. If it's a talking-head video, produce shot/beat direction. If it's a carousel, produce per-slide visual prompts.

### 3. Self-audit flags (MANDATORY — scan every line against the AI Tells Catalog)

After writing all platform_content, scan EVERY line against the AI Writing Tells Catalog loaded above. For each category, check:

**1. Word choice** — Did you use any word from the vocabulary blocklist? (delve, tapestry, landscape, robust, streamline, leverage, harness, crucial, pivotal, vital, underscore, enhance, foster, testament, vibrant, nestled, groundbreaking, quietly, fundamentally, meticulous, serves as, stands as, boasts, features, offers). Scan every word.

**2. Sentence structure** — Did you use negative parallelism ("it's not X, it's Y")? More than once? Did you use the rule of three in more than one paragraph? Did you start a sentence with "It's worth noting" or "Importantly"? Did you tack a "-ing" phrase onto the end of a sentence for shallow analysis?

**3. Paragraph rhythm** — Are all your paragraphs the same length? Are they all one sentence? Are they all three? Is there natural variation?

**4. Tone** — Did you use false suspense ("Here's the kicker")? Patronizing analogies ("Think of it as...")? Grandiose stakes? Vague attributions ("experts argue")? Invented concept labels? The "despite challenges" formula? Promotional tone?

**5. Formatting** — How many em dashes did you use? If more than 3, flag it. Did you bold every bullet? Did you use emoji as decoration? Did you use curly quotes when the person writes straight quotes?

**6. Composition** — Did you signpost your conclusion ("In summary")? Did you restate your thesis? Did you use the "despite challenges" formula? Are you repeating the same metaphor?

For each flag, include:
- **line**: the specific line flagged
- **rule**: which tell category and rule (e.g., "1.9 copulative avoidance: serves as instead of is")
- **confidence**: HIGH, MEDIUM, or LOW (from the catalog)
- **suggestion**: the fix — what the human version should be
- **fix_applied**: for HIGH confidence tells, you MUST fix the line before returning. Write the revised text here. For MEDIUM/LOW, leave the original and flag for review.

**HIGH confidence tells must be fixed before the draft reaches the alignment check.** You are the first pass — the alignment check is the second. Do not pass HIGH tells through.

## Rules

- Write in the person's voice — use their patterns, their dialect (never sanitized), their specific way of saying things
- Include a specific detail only this person could know (from the idea or capture material)
- Facts, quotes, dates, statistics, and specific details MUST come from the grounding sources — do NOT fabricate specifics not present in them
- Do NOT produce generic "good writing" — produce THIS person's writing
- The visual direction is text only — no image generation, no pixel references. But it must be concrete and actionable
- Self-audit honestly — if a line feels like an AI tell, flag it. The human will judge.
- Follow the format skeleton from the Format Guide for each platform
- If a module is empty/not built, say so in the draft — never fill with invented content
- image_prompts and shot_format_choices must each have at least one entry — do not return empty arrays
- Each platform_content entry must have at least one post in the posts array
- The variant_type must match the structure of the posts array you wrote for that platform — thread for multi-post X, carousel for multi-slide Instagram, reel for video scripts, single_post for one post. Do not copy the Format Guide entry's Variant type field blindly when the format spans multiple platforms with different structures.
- Use only the standard variant_type values: thread, carousel, reel, single_post, story_series, poll, newsletter
- For reels: every frame MUST have label and vo_text. Add text_on_screen, visual direction, transition, SFX, and music only when they perform a named production function. The Assembler resolves real media and builds the final edit plan; it must not invent or rewrite approved copy.

## Output format

Respond with ONLY valid JSON:

```json
{
  "platform_content": [
    {
      "platform": "string — platform name from the Format Guide",
      "variant_type": "string — thread | carousel | reel | single_post | story_series | poll | newsletter",
      "content": "string — summary line or full text for single-post formats",
      "posts": [
        {
          "label": "HOOK | SETUP | BUILD | TURN | PAYOFF | CLOSE",
          "vo_text": "string — exact words spoken in this frame",
          "text_on_screen": {
            "text": "string — short overlay text for sound-off viewing",
            "position": "center | bottom-third | top",
            "style": "string — Visual Style caption sheet ref",
            "animation": "fade-in | word-by-word-sync | slide-in-from-left | typewriter"
          },
          "visual": {
            "shot_type": "string — camera shot type",
            "movement": "string — camera movement",
            "b_roll": "string — none or B-roll description",
            "image_prompt": "string — generation-ready prompt"
          },
          "transition_in": "cut | crossfade | slide | whip",
          "sfx": [{"type": "whoosh | pop | hit | riser | silence", "timing": "on_text_appear | pre-beat | post-beat"}],
          "music": {
            "action": "continue | duck | silence | introduce",
            "duck": false,
            "silence_gap_sec": 0
          }
        }
      ],
      "image_prompts": ["string — per-frame image prompts aggregated, or 'none' for text-only"]
    }
  ],
  "visual_direction": {
    "image_prompts": ["string — generation-ready prompts: subject, composition, style anchors, aspect ratio"],
    "reference_notes": ["string — visual references (colors, mood, composition notes)"],
    "shot_format_choices": ["string — shot/format choices per the Visual Style Guide"],
    "music": {
      "mood": "string",
      "genre": "string",
      "tempo_bpm": 95,
      "energy_curve": "string — build → peak → settle",
      "ducking": true,
      "silence_drops": [{"at_frame": "TURN", "duration_sec": 2.0}]
    },
    "captions": {
      "burned_in": true,
      "source": "vo_script",
      "style_ref": "string — Visual Style caption sheet ref",
      "font": "Georgia",
      "position_default": "bottom-third",
      "animation": "word-by-word-sync"
    },
    "canvas": {
      "aspect_ratio": "9:16",
      "resolution": "1080x1920",
      "duration_target": 45
    }
  },
  "self_audit_flags": [
    {
      "line": "string — the specific line flagged",
      "rule": "string — which AI Tells Catalog rule (category + rule number)",
      "confidence": "HIGH | MEDIUM | LOW",
      "suggestion": "string — what the human version should be",
      "fix_applied": "string — for HIGH confidence: the revised text. For MEDIUM/LOW: empty or null"
    }
  ]
}
```

For text formats (thread, carousel, single_post, newsletter, poll), `posts` is an array of strings and `visual_direction.music`, `visual_direction.captions`, and `visual_direction.canvas` are optional.