# Soundtrack Ranking (VF-VS-511)

You are ranking music tracks for a short-form video. The video has a voiceover (VO) and you need to pick the best background music bed.

## Inputs

### Script audio intent
- **Emotional register:** {emotional_register}
- **Content summary:** {content_summary}
- **VO duration:** {vo_duration_s}s
- **Energy curve intent:** {energy_curve}

### Candidates
{candidates_json}

## Your task

Rank these tracks by **mood/fit as the primary criterion (80% weight)** and **popularity/trending at 20% weight**. When two tracks are similarly matched on mood and voice fit, prefer the more popular/trending one. Never sacrifice mood fit for popularity.

Consider:
1. Does the track's mood match the script's emotional register?
2. Does the track's energy complement (not compete with) the VO?
3. Is the track long enough for the VO duration?
4. Is the track from a commercial-safe source?
5. Is the track trending or widely used (when mood fit is close)?

## Output

Return a JSON object with:
- `recommended`: the single best track (object with `audio_id`, `title`, `artist`, `source`, `rationale`, `fit_score` 0-100, `popularity_tier`)
- `alternatives`: exactly 2 alternative tracks (same shape, plus `trade_off` explaining why they're #2 and #3)
- `vo_only_fallback`: boolean — true if NO candidate is suitable (all rank below quality threshold)
- `vo_only_rationale`: string (required if vo_only_fallback is true)

## Rules

- Pick tracks that complement the VO, not dominate it. The bed ducks under the voice.
- Prefer instrumental tracks over vocal tracks (vocals compete with the VO).
- If all candidates are unsuitable (wrong mood, too short, vocal-heavy), set `vo_only_fallback: true` and explain why.
- Never invent tracks that aren't in the candidates list.
- `fit_score` is your judgment of how well the track fits the script's mood and energy (0-100, higher is better).
- `popularity_tier` is your read of the track's trending/usage level: "high", "medium", or "low".