# DIVERGENCE-020 — Operator visual engagement criteria

**Filed:** 2026-07-23
**Filed by:** Daimon (operator)
**Status:** OPERATOR DIRECTION — pending architect review
**Conflicts with:** `docs/research/viral-content-meta-analysis-v2.md` ("never exceed four seconds without a change" listed under "What v1 got wrong"), `docs/playbooks/viral-content-production-playbook-v1.md` Phase 7 ("A hold is valid when expression, proof, or silence needs time")

## What the operator directs

The operator has observed the last several rendered videos and directs the following criteria additions and changes. These are operator taste directives, not hypotheses.

### 1. Visual change floor: maximum 4 seconds per segment (ENFORCED, not advisory)

The meta-analysis v2 rejected "never exceed four seconds without a change" as an unsupported hard rule. The operator disagrees for practical production: the last several videos held still images for 6–10 seconds and felt static and boring. The 4-second maximum is reinstated as a **blocking validator rule**: no segment may exceed 4 seconds without an overlay, text pop, B-roll cut, or angle shift.

The Writer prompt already states this rule ("Visual change every 2-4 seconds. No single clip should exceed 4 seconds without a text pop, B-roll cut, or angle shift. The edit plan validator enforces this.") but the validator at `edit_planning.py:1341-1354` is advisory-only (`pass`). The intent was never implemented.

**Exception:** a segment may exceed 4 seconds IF it has an active overlay or text element that appears at or before the 4-second mark. This preserves the "text pop" exception.

### 2. Caption emphasis: keyword highlighting with varied fonts and styles

"Fun" is not a hard-coded requirement for every caption. But emphasis on key words via highlighting, different fonts, and varied styles IS required as a production criterion. The system should:
- Highlight key words/phrases within captions (color, weight, or size change)
- Use varied font families and styles as appropriate to the piece (not one font for everything)
- Match emphasis style to the emotional register of the beat

This is a prompt-level directive, not a Python heuristic. The Visual Style Guide module and caption prompts carry the style vocabulary.

### 3. Supporting visual elements: graphs, icons, inserted images

Add as a production criterion: videos should use supporting visual elements to reinforce words and concepts — small graphs, data visualizations, icons, and inserted images that emphasize what's being said. These are not decorative; they perform a narrative function (proof, emphasis, explanation).

This maps to the existing `renderer_graphic` source policy and the `emphasis`/`proof` text functions, but the prompts do not currently encourage their use.

### 4. VO-only videos must have background visual life

VO-only audio mode does not mean visually static. Add as a production criterion: VO-only videos must have visual movement or texture in the background — motion on stills (zoom/pan/parallax, not just Ken Burns), animated graphics, text emphasis pops, or B-roll cutaways. A VO-only video with a series of static held images is not acceptable.

### 5. More video clips, fewer stills with Ken Burns

The current `media_type` vocabulary is `video` (generated 5s clip) or `motion_graphic` (still image + Ken Burns). The operator observes most videos end up as 1 video clip + many stills with Ken Burns. Direct the Writer and Visual Director to:
- Prefer `video` media type for beats that show people, actions, places, or motion
- Use `motion_graphic` (stills) for abstract concepts, data, text emphasis — not as a default for everything
- Aim for a mix, not 1 video + 5 stills

### 6. Creative motion beyond Ken Burns

Ken Burns (slow zoom/pan) is the only motion applied to stills today. Add motion vocabulary:
- Parallax (foreground/background layers moving at different speeds)
- Dynamic zoom (zoom to a focal point, not just slow drift)
- Animated graphic elements (text/number reveals, icon animations)
- Whip-pans and motivated transitions between scenes

### 7. Scene-to-scene coherence

Videos should flow from one scene to the next coherently — not look like stock images/videos randomly stitched together. Add as a production criterion: adjacent segments should have visual continuity (consistent grade, complementary compositions, motivated transitions). The Visual Director should plan visual events as a sequence, not as independent shots.

## What this changes in the system

| Change location | What changes |
|---|---|
| `src/services/edit_planning.py:1341-1354` | 4-second max clip: advisory → blocking error (with overlay exception) |
| `prompts/draft/generate_v3.md` | Add media mix guidance, supporting visual elements, VO-only visual life, scene coherence |
| `prompts/assembly/visual_director_v1.md` | Prefer video over stills, richer motion vocabulary, scene coherence as a sequence |
| `prompts/assembly/edit_plan_v1.md` | 4-second max as hard rule (not "pace by meaning" alone), supporting visuals, VO-only background life |
| Visual Style Guide module (StackPenni) | Emphasis/highlighting vocabulary, varied fonts per role |

## Charter conflict

This divergence conflicts with the meta-analysis v2 rejection of the 4-second rule and the playbook's "pace by meaning" principle. The operator's position: the system is producing boring videos in practice, and the meaning-based pacing rule is being used by the LLM as a license to hold static images too long. The 4-second floor with the overlay exception preserves meaning-driven pacing while preventing the static-image problem.