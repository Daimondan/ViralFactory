# Viral Content Research: Mechanics, Patterns & AI Workflows

**Purpose:** actionable research for upgrading ViralFactory's video pipeline from "stock clips + VO" to engaging, high-retention short-form content.

**Date:** 2026-07-11  
**Status:** Research compiled, not yet implemented

---

## 1. WHY OUR CURRENT VIDEOS FALL FLAT

Our pipeline produces: stock video clips + AI voiceover. No text overlays, no transitions, no sound design, no engagement mechanics. This is the baseline. Everything below is what we're missing.

---

## 2. THE HOOK: FIRST 3 SECONDS (70% of the swipe-vs-watch decision)

### The 3-Part Hook Formula (neuroscience-backed, platform-agnostic)

1. **Pattern Interrupt (0–0.8s):** Something unexpected in the first frame. Rapid motion, direct eye contact, unexpected visual/audio, movement toward camera. Break the viewer's current mental state.
   - Examples: start mid-action, start mid-sentence, whip-pan into frame, unexpected visual element, bold text overlay that contradicts the visual

2. **Identity Signal (0.8–1.5s):** A few words or visual cue confirming "this is for me." Without it, attention doesn't sustain.
   - Examples: "if you create short-form content...", "stop making this mistake...", "most people don't know..."

3. **Open Loop (1.5–3s):** A question, claim, or tease that creates an information gap. The brain physically resists swiping away until it's resolved.
   - Examples: "The one thing killing your retention...", "Why your best videos underperform...", "What I learned analyzing 500 hooks..."

### Hook Archetypes That Work in 2026 (by performance data)

| Hook Type | Avg Views | When to Use |
|---|---|---|
| **Hot Take** (bold opinionated first sentence) | ~140K | Commentary, POV content |
| **Investigator** (question/unfolding mystery) | ~140K | Stories, reveals, "what happened" |
| **Proof Drop** (screenshot/chart/specific number) | ~90K views but **1,761 saves** (highest) | Educational, reference content |
| **Contrarian** ("Stop doing X...") | ~120K | Myth-busting, advice |
| **Stat/Number** ("I lost $10K in 30 seconds") | ~115K | Results, transformations |
| **Before/After/Transformation** | ~100K | Visual transformations |

**AVOID:** Story hooks ("So the other day...", "Let me tell you about...") — average only 7K views. The algorithm decides in 1.5 seconds.

### What This Means for ViralFactory

- **The LLM must generate hooks in these archetypes**, not generic openers
- The hook should be decided in the ideation or drafting stage with explicit hook type + reasoning
- The first 3 seconds of the video need a **text overlay** matching the hook (for sound-off viewers — 85% of views are muted)
- The first frame needs visual energy — not a slow stock clip establishing a scene

---

## 3. RETENTION: KEEPING THEM WATCHING

### Pacing

- **Change the visual every 2–4 seconds.** Scene cuts, angle shifts, text overlays, B-roll insertions. Visual monotony kills retention.
- **MrBeast's pattern interrupt cadence:** every 3–4 seconds. A 15-minute video = 300+ cuts.
- **Breathing room matters:** post-2024, pure sensory overload causes "retention fatigue." Build in 3–5 second slow moments where music drops and emotion lands. The "low" makes the "high" feel high.

### The Payoff Ladder (MrBeast's structure)

Each video is a series of mini-stories, each 30–60 seconds:
```
0:00–0:30   Hook + setup (the promise)
0:30–2:00   First beat (immediate payoff to validate the hook)
2:00–4:00   Escalation (stakes get higher)
4:00–6:00   Complication (twist, obstacle, new information)
6:00+       Payoff (deliver on the promise)
```

For our 30–60s Reels, this compresses to:
```
0–3s    Hook (pattern interrupt + open loop)
3–10s   Problem / setup (what's at stake)
10–45s  Solution / build (value delivery, scene changes every 2-4s)
45–60s  Payoff + implied CTA (end on the result, not the ask)
```

### Sound Design = 50% of Retention

- **Every visual change should have an audio cue.** Text pop → "whoosh" or "pop". Camera zoom → "whip". Scene change → "hit" or "boom".
- **Risers before reveals:** audio that builds tension, then SNAP — cut happens, tension releases.
- **Strategic silence:** music cuts out completely for key moments. The absence of sound is a pattern interrupt.
- **Dynamic range:** don't let audio become white noise. Vary the energy. Loud peaks + quiet valleys.

### Text on Screen

- **Word-by-word or phrase-by-phrase captions** synced to VO cadence. Never full sentences at once.
- **85% of views are muted.** If the video doesn't work without sound, it doesn't work.
- **Text overlays boost watch time by up to 37%** (YouTube Shorts data).
- **Pre-rendered static text** — don't animate text reveal letter-by-letter (viewers have scrolled past). Show immediately.
- **Arrows, circles, countdown timers** to highlight specific elements. Visual anchors telling the audience what matters right now.

### What This Means for ViralFactory

1. **Edit plan must include text overlay events** — not just video clips. Every 2–4 seconds: a text pop, a visual change, a B-roll cut.
2. **Renderer must burn in text overlays** — ffmpeg `drawtext` with `enable='between(t,start,end)'` for timing. We can chain multiple overlays in one `-filter_complex` pass.
3. **Sound design layer in the edit plan** — SFX cues (whoosh, pop, hit) tied to visual events. Background music with energy changes.
4. **Captions from VO transcript** — word-by-word or phrase-by-phrase, synced to VO timing. We already have per-frame VO timing.

---

## 4. EMOTIONAL TRIGGERS: WHAT DRIVES SHARES, SAVES, COMMENTS

### The Emotion Hierarchy (from 4,000 video analysis)

| Emotion | Avg Views | Avg Shares | Avg Saves | Best For |
|---|---|---|---|---|
| **Fear** | 264K | 480 | 393 | Awareness, reach |
| **Empathy** | 170K | **2,139** | 975 | Distribution, shares |
| **Outrage** | 168K | 616 | 313 | Comments, engagement |
| **Curiosity** | 98K | 720 | 532 | Balanced all-around |
| **Humor** | 92K | 645 | 276 | Entertainment |
| **Trust** | 42K | 691 | **1,294** | Authority, return viewers |
| **Aspiration** | 29K | 255 | 151 | (weak) |
| **Hope** | 5K | 91 | 39 | (weakest) |

**Key insight:** Fear, Empathy, and Outrage are a tier unto themselves — 3-5x the views of Curiosity. Most creators default to Aspiration ("here's how to become X") or Hope ("it gets better"), which are the two worst-performing.

### What Drives Each Action

- **Views:** Fear > Empathy > Outrage (high arousal emotions)
- **Shares:** Empathy (2,139 avg, 3x anything else — people share what they relate to)
- **Comments:** Outrage (the fight in the comments IS the point)
- **Saves:** Trust (1,294 avg — people bookmark what they believe) and Proof Drop hooks

### CTA Strategy

**Implied CTAs beat direct CTAs by nearly 2x** (138K vs 72K avg views).

- **Implied:** the video itself is the CTA. End on the payoff, let the comment section do the work. The algorithm rewards the watch-time you preserve.
- **Direct:** "follow for more," "link in bio," "comment X below" — signals to the algorithm you're extracting an action, which depresses back-half watch time.

### What This Means for ViralFactory

1. **Ideation must tag the primary emotional trigger** for each idea. The LLM should pick from Fear, Empathy, Outrage, Curiosity, Humor, Trust — and avoid defaulting to Aspiration/Hope.
2. **The draft should be structured around the chosen emotion.** Fear = what you stand to lose. Empathy = relatable struggle. Outrage = something unfair. Curiosity = information gap.
3. **End on payoff, not ask.** No "follow for more" outro. The video's final frame should be the result, the proof, the punchline.

---

## 5. PLATFORM-SPECIFIC DIFFERENCES

| Factor | TikTok | Instagram Reels | YouTube Shorts |
|---|---|---|---|
| **Decision window** | 1.3s | 1.3s | 2.1s |
| **Sound default** | On | On | On |
| **Best hook type** | Pattern interrupt, incomplete visual | Direct address, mid-action | Authority interrupt, stakes |
| **Top metric** | Completion rate, loop rate | Watch-through, saves | CTR + completion |
| **Hook length** | 0.5–1.5s | 0.5–1.5s | 1–3s |
| **Ideal duration** | 15–30s (highest completion) | Under 90s | 38–47s |
| **Key insight** | Rewatches = strongest signal | Trending audio = algorithmic boost | Search discoverability = evergreen |

### Duration Data (2026 study, 4,000 videos)

| Duration | Avg Views | Why |
|---|---|---|
| **90s+** | 170K | More watch time = algorithm loves it. 31x more views than 0–15s |
| **61–90s** | 126K | Sweet spot for Reels |
| **31–60s** | 28K | Our current target range — underperforming |
| **16–30s** | 32K | |
| **0–15s** | 5K | Too short to build watch time |

**Note:** Our pipeline currently targets 30–60s. The data suggests 60–90s or longer performs significantly better for algorithmic distribution. Our duration >60s advisory is correct — but the data says we should be pushing longer, not shorter.

### Format Types That Work

| Format | Avg Views | Notes |
|---|---|---|
| **Commentary** (POV + opinion) | Highest | Viewers want a point of view, not a lecture |
| **Educational + Commentary** | 124K | Education wrapped in opinion |
| **Storytime** | Good with Investigator hook | |
| **Greenscreen** (creator + source material) | High | Higher information density = more watch time |
| **Myth-Busting** | 8K (collapsed) | Was dominant 2023-24, now dead |
| **Promotional** | 26K | "Here's why you should buy" — weak |

### What This Means for ViralFactory

1. **Format guide should include Greenscreen as a format** — creator face + source material = high information density. We could composite our generated images with a "creator" frame.
2. **Commentary format is king.** Our drafts should have a POV, not just information delivery.
3. **Duration target should shift to 60–90s** for Reels, not 30–60s. More watch time per view.

---

## 6. MRBEAST'S SPECIFIC MECHANICS

### Retention Architecture (from leaked production document)

- **Minute 0–1:** Hook + show the title/thumbnail promise immediately. Losing 21M of 60M viewers in the first minute is "reasonably good."
- **Minute 1–3:** "Crazy progression" — cover multiple days/steps, not just the first one. Get viewers invested fast.
- **Minute 3:** First re-engagement spectacle ("only MrBeast can do this").
- **Minute 3–6:** Quick scene changes, highly stimulating simple content.
- **Minute 6:** Second re-engagement.
- **Minute 6+:** "Back half content" — viewer is in a lull, watching without realizing. Less spectacular content goes here.
- **Ending:** Abrupt stop to protect retention. Never signal the end until the payoff.

### MrBeast Editing Mechanics

- **Shot rarely lasts >4 seconds.** Often faster.
- **Multiple cameras** rolling simultaneously for alternate angles.
- **Digital zooms/keyframing** when multiple cameras aren't available — push in slowly during explanations to build subconscious urgency.
- **B-roll cutaways** — if someone says "we bought an island," immediately show the island, don't let them finish the paragraph on camera.
- **Subtitles word-by-word** synced to speech cadence — never full sentences.
- **Sound design ("Mickey Mousing"):** every visual movement has a corresponding sound. Text pop → pop/whoosh. Zoom → whip. Cut → hit/boom.
- **Risers** before transitions to build tension. Cut happens as riser peaks.
- **Strategic silence** — music cuts for key dramatic moments.
- **"Wow factor"** — something that makes you ask "who else can do this?"

### MrBeast's Creative Process

- **Starts with title + thumbnail.** Everything else is defined by what the thumbnail promises.
- **Never bait-and-switch.** If the thumbnail promises X, the first 10 seconds must deliver X.
- **"Critical components"** — the one thing without which there is no video. Protected at all costs.
- **Formats:** "Last to Leave" (payoff at end), "Stair Stepping" (progressively cooler, biggest payoff last), "Chase" (will they catch me? watch to find out).

### What This Means for ViralFactory

1. **Ideation should generate the "title + thumbnail concept" first**, then the script serves it. We're doing the reverse.
2. **Edit plan should enforce a max clip duration** (4s) and a "visual change every 2–4s" rule.
3. **Sound design is non-optional.** Every text pop, every cut, every transition needs an SFX cue. This is a new layer in the edit plan.
4. **The "wow factor" concept:** each video should have one moment that makes the viewer think "how did they do that?" — even with stock footage, a surprising visual combination or a striking data visualization can do this.

---

## 7. AI TOOLS & WORKFLOWS WE CAN LEARN FROM

### Existing AI Video Generation Platforms

| Tool | What It Does | What We Can Learn |
|---|---|---|
| **Opus Clip** | Long-form → short-form auto-clipping + animated captions + B-roll + transitions | Auto-captioning is table stakes. B-roll insertion triggered by content matching. |
| **CapCut** (and pyCapCut/pyJianYing) | Template-driven video editing, batch generation, text/sticker/animation effects | Template mode: define a visual template, swap content. CapCut draft format is programmable. |
| **ReelsBuilder API** | 10+ video modes: Magic Video, AI Story, Reddit Story, Motivational, News, Fake Chat — each is a different template structure | **Template structures per format type.** A "Motivational" video has a different structure than a "News" video. We should have format-specific edit templates. |
| **UGC Copilot API** | 4 video engines (Sora 2, Veo 3.1, Kling 3.0, Seedance 2.0), script→video pipeline | Multiple generation engines, idempotent retries, webhook completion. |
| **Creatify** | URL→video, AI avatars, product video, custom templates | Template reuse for brand consistency. |
| **GEN API** | Agent core (identity, personality, voice, look) → content ideas → template clone → render | The "agent configuration" model mirrors our module system. |

### Open-Source / Programmable Video Tools

| Tool | Stack | What It Does |
|---|---|---|
| **kinetic-text-ffmpeg** (npm) | TypeScript + ffmpeg | JSON spec → ffmpeg `-filter_complex` with `drawtext` animations. Fade, slide, pop, bounce easing. Beat detection for music-synced text. **Directly usable in our ffmpeg renderer.** |
| **videopython** | Python + ffmpeg | LLM-friendly video editing. `VideoEdit` as JSON plan (like our edit plan). Auto-editor with local LLM. MCP server for agent-driven editing. |
| **mosaico** | Python | Programmatic video composition. AI script generation, media asset management, effects (pan, zoom), TTS integration. Similar architecture to ours. |
| **movis** | Python | Video production engine. Compositions, layers, text layers, effects (shadow, blur, chromakey), keyframe animation. Higher-level than raw ffmpeg. |
| **mcp-video** | Python + ffmpeg + Remotion | MCP server for AI agents to edit video. 83 tools: trim, merge, text, audio, filters, transitions, AI transcribe, scene detect. Timeline DSL for multi-track edits. |
| **Remotion** | React + Node | Programmatic video via React components. Templates: TikTok captions, prompt-to-video, overlay, audiogram. **The "prompt-to-motion-graphics" template is a SaaS for AI video generation.** |
| **MoviePy** | Python | Programmatic video editing. Simple API for cuts, text, composites. |

### Key Workflow Patterns from AI Tools

1. **Template-driven generation:** Define a visual template (scene structure, text positions, transitions, music). Swap in content. This is what ReelsBuilder, CapCut, and Remotion all do.
2. **Auto-captioning is table stakes:** Every tool does it. We must too. Word-by-word or phrase-by-phrase, synced to audio.
3. **B-roll insertion by content matching:** Opus Clip analyzes what's being said and inserts relevant B-roll automatically. Our pipeline already has stock footage matching — but we need to cut to B-roll more frequently (every 2–4s).
4. **Format-specific templates:** ReelsBuilder has "Motivational", "News", "Reddit Story", "Fake Chat" as separate templates. Each has a different visual structure. Our format guide should define edit templates per format, not just content templates.
5. **Multi-engine video generation:** UGC Copilot routes to Sora/Veo/Kling/Seedance. We could add AI-generated video clips (not just stock) as a media source.
6. **Idempotent + webhook pipelines:** For async video generation at scale. We already have a job queue.

### What This Means for ViralFactory

1. **Adopt the "edit template" concept.** The edit plan should reference a template structure that defines: text overlay positions, transition types, SFX cues, music energy levels. The LLM fills the template with content. ffmpeg executes it.
2. **kinetic-text-ffmpeg's approach** is directly applicable: JSON spec → ffmpeg `drawtext` filter chain with animations. We can implement this in our renderer without any new dependencies.
3. **Auto-captioning from VO transcript:** We already have per-frame VO timing. Generating word-by-word captions from the VO script + timing is a straightforward addition.
4. **Format-specific edit templates:** Instagram Reel, Carousel, Single Image each need a different visual treatment. The edit plan should vary by format.
5. **B-roll frequency:** The edit plan should specify a new visual (clip change or text overlay) at least every 4 seconds. Currently our clips can run 10+ seconds with nothing changing.

---

## 8. ACTIONABLE UPGRADES FOR VIRALFACTORY (Priority-Ordered)

### Phase 1: Text Overlays + Captions (highest impact, lowest effort)

1. **Auto-captioning:** Generate word-by-word or phrase-by-phrase captions from VO transcript + per-frame timing. Burn into video with ffmpeg `drawtext` + `enable='between(t,start,end)'`.
2. **Hook text overlay:** The hook (first 3s) gets a bold text overlay matching the spoken hook. Pre-rendered static (not animating in).
3. **Key phrase highlights:** During the body, pop key phrases as text overlays synced to VO. Every 4–6 seconds a new text pop.

### Phase 2: Sound Design

4. **SFX cues in edit plan:** Add a `sfx` array to the edit plan: `[{t: 0.0, type: "whoosh"}, {t: 3.2, type: "pop"}, {t: 8.1, type: "hit"}]`. Renderer mixes these into the audio track.
5. **Background music:** Add a music track with energy changes. Use risers before transitions, silence for key moments. Source from a royalty-free library (config-driven).

### Phase 3: Pacing + Structure

6. **Max clip duration:** Enforce 4-second max per clip in the edit plan validator. If a clip would run longer, the LLM must split it with a text overlay or B-roll cut.
7. **Visual change audit:** Validator checks that no 4-second window goes by without a visual change (cut, text pop, zoom, overlay).
8. **Emotional trigger tagging:** Ideation tags the primary emotion. Draft is structured around that emotion. Edit plan pacing matches the emotion (Fear = fast, Empathy = breathing room).

### Phase 4: Format Templates + Advanced

9. **Format-specific edit templates:** Reel template (fast cuts, captions, SFX), Carousel template (slide transitions, text per slide), Single Post template (static composition).
10. **Greenscreen format:** Composite a "creator frame" with source material behind it. Higher information density.
11. **Duration shift:** Target 60–90s for Reels instead of 30–60s. More watch time per view.
12. **AI-generated video clips:** Add Veo/Kling/Sora as media sources for clips that stock footage can't provide. (Future, requires API integration.)

---

## 9. KEY PRINCIPLES TO ENCODE IN PROMPTS

### Ideation Prompt Additions
- Tag each idea with a **hook archetype** (Hot Take, Investigator, Proof Drop, Contrarian, Stat, Transformation)
- Tag each idea with a **primary emotional trigger** (Fear, Empathy, Outrage, Curiosity, Humor, Trust — NOT Aspiration or Hope)
- Generate the **"title + thumbnail concept"** first, then the idea serves it
- Specify the **"wow factor"** — the one moment that makes the viewer think "how did they do that?"

### Draft Prompt Additions
- Structure: Hook (0–3s) → Problem/Stakes (3–10s) → Build/Solution (10–45s) → Payoff (45–60s+)
- End on payoff, not ask. **No direct CTA.** Implied CTA only.
- Include **text overlay cues** in the draft: `[TEXT: "specific phrase"]` at key moments
- Include **B-roll cues**: `[BROLL: description of visual to show]` when referencing something concrete
- Pacing note: "A new visual (cut, text pop, B-roll) must happen every 2–4 seconds"

### Edit Plan Prompt Additions
- `text_overlays` array: `{text, start_s, end_s, position, style}`
- `sfx` array: `{t, type}` where type ∈ [whoosh, pop, hit, riser, silence]
- `music` object: `{track, energy_curve: [{t, level}]}`
- `captions` array: `{text, start_s, end_s}` generated from VO transcript
- Validator: no clip > 4s, no 4s window without a visual change

### Renderer Additions
- `drawtext` chain for text overlays with `enable` timing + `alpha` animation
- SFX audio mixing: overlay SFX clips at specified timestamps
- Background music mixing with energy level changes
- Auto-caption burn-in from VO transcript timing

---

## 10. SOURCES

### MrBeast Production
- Leaked MrBeast production onboarding document (simonwillison.net, danielscrivner.com)
- MrBeast editing style analysis (ftcreative.co)
- Pattern interrupt analysis (livecounts.io)
- Audience metrics analysis (kevinmunger.substack.com)

### Viral Mechanics
- Hook neuroscience (vidcognition.com)
- Viral hook framework (kompozy.io)
- 2026 hook patterns (greenfroglabs.com)
- Short-form script guide (eliro.pro)
- 4,000 video virality study (thecontentlabs.app)
- Hook psychology (virvid.ai)
- Engagement factors study (ScienceDirect, IEEE)

### AI Tools & Workflows
- kinetic-text-ffmpeg (github.com/SiddharthFulia)
- ffmpeg drawtext guide (braydenblackwell.com)
- videopython (github.com/bartwojtowicz)
- mosaico (github.com/folhasp)
- movis (github.com/rezoo)
- mcp-video (github.com/KyaniteLabs)
- Remotion (remotion.dev)
- Opus Clip (opus.pro)
- CapCut/pyCapCut (github.com/GuanYixuan)
- ReelsBuilder API (reelsbuilder.ai)
- UGC Copilot API (ugccopilot.ai)
- Creatify API (creatify.ai)
- GEN API (api.gen.pro)