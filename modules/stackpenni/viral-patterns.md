# Viral Patterns Playbook — v2.0

## Summary

Researched viral content mechanics from 4,000+ short-form video analyses, MrBeast's leaked production handbook, neuroscience-backed hook studies, and platform-specific data (TikTok, Reels, YouTube Shorts). Patterns are framed as actionable rules for the content drafter and edit plan generator. Each is a hypothesis grounded in data, not a guarantee.

## Hook Mechanics (first 3 seconds = 70% of swipe-vs-watch decision)

### The 3-Part Hook Formula
1. **Pattern Interrupt (0–0.8s):** Something unexpected in the first frame — rapid motion, mid-action start, bold text overlay, unexpected visual. Break the viewer's mental state.
2. **Identity Signal (0.8–1.5s):** A few words confirming "this is for me" — targets the audience explicitly.
3. **Open Loop (1.5–3s):** A question, claim, or tease that creates an information gap the brain must resolve.

### Hook Archetypes (by performance, 2026 data)
- **Hot Take** (~140K avg views): Bold opinionated first sentence. Best for commentary/POV.
- **Investigator** (~140K): Question or unfolding mystery. Best for stories, reveals.
- **Proof Drop** (~90K views, **1,761 saves** — highest): Screenshot, chart, specific number. Best for educational/reference.
- **Contrarian** (~120K): "Stop doing X..." Inverts consensus. Best for myth-busting.
- **Stat/Number** (~115K): "I lost $10K in 30 seconds." Specific results.
- **Before/After** (~100K): Visual transformation.

**AVOID:** Story hooks ("So the other day...", "Let me tell you about...") — only 7K avg views. The algorithm decides in 1.5 seconds.

### What This Means for Drafting
- Open mid-action, not at the beginning of a story
- First line should be a claim or question, not a greeting
- The hook text should appear as a burned-in text overlay in the first 2 seconds
- 85% of views are muted — the text overlay is the hook for sound-off viewers

## Retention Mechanics

### Pacing
- **Visual change every 2–4 seconds.** Cut, text overlay, B-roll, zoom. Visual monotony kills retention.
- **Max segment duration: 4 seconds** without a visual change (cut, overlay, or transition).
- **Breathing room matters:** After rapid cuts, allow 3–5 seconds where music drops and emotion lands. The "low" makes the "high" feel high.

### The Payoff Ladder (structure)
Each video is a series of mini-stories, each 30–60 seconds (compressed for 30–60s Reels):
```
0–3s    Hook (pattern interrupt + open loop + text overlay)
3–10s   Problem / stakes (what's at risk, what's possible)
10–45s  Build / solution (value delivery, scene changes every 2-4s)
45–60s+ Payoff + implied CTA (end on the result, not the ask)
```

### Text on Screen
- **Every segment should have at least one text overlay** — a key phrase from the VO
- Word-by-word or phrase-by-phrase, synced to VO cadence
- Never full sentences at once — viewers have scrolled past
- Text overlays boost watch time by up to 37%
- Use `style_ref: "hook"` for the opening, `"highlight"` for key stats, `"default"` for body text

### Sound Design (50% of retention)
- **Every visual change should have an audio cue:** text pop → whoosh, cut → hit, transition → riser
- **Risers before transitions:** build tension, then SNAP — cut happens, tension releases
- **Strategic silence:** music cuts for key moments — absence of sound is a pattern interrupt
- **SFX cues in the edit plan:** `whoosh`, `pop`, `hit`, `riser` at segment-level timestamps

## Emotional Triggers (what drives shares, saves, comments)

### The Emotion Hierarchy (from 4,000 video analysis)
| Emotion | Avg Views | Avg Shares | Avg Saves | Best For |
|---|---|---|---|---|
| Fear | 264K | 480 | 393 | Awareness, reach |
| Empathy | 170K | **2,139** | 975 | Distribution, shares |
| Outrage | 168K | 616 | 313 | Comments, engagement |
| Curiosity | 98K | 720 | 532 | Balanced all-around |
| Humor | 92K | 645 | 276 | Entertainment |
| Trust | 42K | 691 | **1,294** | Authority, return viewers |
| Aspiration | 29K | 255 | 151 | (weak — avoid defaulting here) |
| Hope | 5K | 91 | 39 | (weakest — avoid) |

**Key insight:** Fear, Empathy, and Outrage are 3–5x the views of Curiosity. Most creators default to Aspiration or Hope, which are the two worst-performing.

### What Drives Each Action
- **Views:** High-arousal emotions (Fear > Empathy > Outrage)
- **Shares:** Empathy (people share what they relate to)
- **Comments:** Outrage (the fight in the comments IS the point)
- **Saves:** Trust (people bookmark what they believe)

### CTA Strategy
**Implied CTAs beat direct CTAs by 2x** (138K vs 72K avg views).
- Implied: end on the payoff, let the comment section do the work
- Direct: "follow for more," "link in bio" — signals extraction, depresses back-half watch time
- **End on payoff, not ask.**

## Platform Differences

| Factor | TikTok | Instagram Reels | YouTube Shorts |
|---|---|---|---|
| Decision window | 1.3s | 1.3s | 2.1s |
| Best hook type | Pattern interrupt | Direct address | Authority interrupt |
| Top metric | Completion rate | Watch-through, saves | CTR + completion |
| Ideal duration | 15–30s (completion) | Under 90s | 38–47s |
| Key insight | Rewatches = strongest signal | Trending audio = boost | Search = evergreen |

### Duration Data
| Duration | Avg Views |
|---|---|
| 90s+ | 170K (31x more than 0–15s) |
| 61–90s | 126K |
| 31–60s | 28K |
| 0–15s | 5K |

**Note:** Longer videos produce more watch time per view, which the algorithm rewards. 60–90s should be the target for Reels, not 30–60s.

## Format Types That Work

- **Commentary** (POV + opinion) = highest. Viewers want a point of view, not a lecture.
- **Educational + Commentary hybrid** = 124K avg. Education wrapped in opinion.
- **Greenscreen** (creator + source material) = high. Higher information density = more watch time.
- **Myth-Busting** = 8K (collapsed from 2023-24 dominance).
- **Promotional** = 26K (weak).

## Patterns

### Pattern: Hook-First Structure
Always open with the hook (pattern interrupt + open loop) in the first 3 seconds. Do not start with context, greetings, or backstory. The hook text must be burned in as a text overlay.

### Pattern: Text Overlay on Every Segment
Every segment gets at least one text overlay with a key phrase from the VO. This is non-negotiable for muted viewing (85% of views). Use style_ref to vary visual hierarchy: "hook" (large), "default" (body), "highlight" (stats/numbers).

### Pattern: Pacing Variety
No segment exceeds 4 seconds without a visual change. If a clip runs longer, insert a text overlay partway through. The edit plan should have a visual change (cut, overlay, transition) every 2–4 seconds.

### Pattern: Emotional Trigger Selection
Each idea should tag a primary emotional trigger. Prioritize Fear, Empathy, Outrage, Curiosity. Avoid defaulting to Aspiration or Hope. The draft structure should serve the chosen emotion.

### Pattern: Payoff Ending
End on the result, not the ask. No "follow for more." The final frame should be the proof, the punchline, or the resolution. Let the comment section be the CTA.

### Pattern: SFX Layer
Every text overlay pop gets a whoosh. Every hard cut gets a subtle hit. Before transitions, add a riser. Sound design is 50% of retention — the edit plan must include SFX cues.

## Never list
- Never open with "Hey guys," "So basically," or "Let me tell you about..."
- Never use direct CTAs ("follow for more," "link in bio") as the ending
- Never leave a segment >4 seconds without a visual change
- Never produce a video without text overlays (85% of views are muted)
- Never default to Aspiration or Hope as the emotional trigger
- Never use the "myth-busting" format (collapsed to 8K avg views)
- Never bait-and-switch: the hook must match the content

## Provenance
- Version: 2.0
- Generated: 2026-07-11T19:50:00Z
- Source: docs/research/viral-content-mechanics-2026-07-11.md
- Schema: viral_patterns_v1