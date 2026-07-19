# DIVERGENCE-015 — Soundtrack discovery, LLM ranking, and auto-apply with alternatives

**Filed:** 2026-07-18
**Filed by:** Builder (vf-coder)
**Status:** RATIFIED WITH BINDING CONDITIONS — see `AMENDMENT-011-soundtrack-discovery-rights-and-asset-gate.md` (2026-07-19)
**Modifies:** AMENDMENT-010 (Phase M13-E, VF-VS-501 through 504)
**Related:** AMENDMENT-010 Condition 4 (soundtrack plan contract), DECISION-voice-cloning-vo-v1.0
**Evidence:** Draft 8 soundtrack selection session (2026-07-18) — full manual workflow demonstrated end-to-end

> **Architect ruling:** Auto-discovery and preview mixing may run before Gate 3, and Gate 3 approves the exact soundtrack-bearing asset. The proposed universal 80/20 ranking and provider-implies-commercial-safety assumptions are rejected. Trend evidence, rights resolution, local acquisition, versioned mix identity, and approval invalidation are separate mandatory contracts. The implementation that landed while this decision was pending is not completion proof; VF-VS-510..516 are blocking corrections.

## Summary

AMENDMENT-010 Phase M13-E built the soundtrack plan contract and a preview gate: the operator hears the proposed bed separately and under the VO, then approves before any mixing. This divergence proposes a different operator UX: the LLM's #1 recommendation is automatically mixed and rendered into the final video; the operator reviews the complete video at the existing Gate 2 and sees two alternatives they can switch to. This removes the separate soundtrack gate and replaces it with review-with-alternatives at the asset gate.

This divergence also adds two new pipeline stages AMENDMENT-010 did not cover: (1) a discovery service that searches commercial-safe audio catalogs via API, and (2) an LLM ranking step that selects the best track from candidates using mood/fit (80%) and popularity/trending (20%) weighting.

## What AMENDMENT-010 currently requires (Phase M13-E)

- **VF-VS-501:** Soundtrack plan contract — `mode`, `music_bed_ref`, `ducking`, `sfx_cues`, `operator_approval`
- **VF-VS-502:** Soundtrack planning prompt — LLM proposes mode + emotional register
- **VF-VS-503:** Soundtrack preview gate — operator hears bed + SFX separately and under VO before approval
- **VF-VS-504:** Soundtrack mix review — extends RenderReviewService

The gate-before-mix model means:
1. LLM proposes a soundtrack plan (mode + bed reference)
2. Operator hears the bed alone and under the VO at a dedicated gate
3. Operator approves/rejects/replaces
4. Only after approval does the mix happen
5. The mixed result is then reviewed again at Gate 2

This is two gates for one piece of music — one for the plan, one for the result.

## What this divergence changes

### 1. Discovery service (new — not in AMENDMENT-010)

A new `src/soundtrack_discovery.py` module searches commercial-safe audio catalogs via API, collects candidates, and filters by hard constraints (duration, commercial-safe, preview available).

**Sources** (config-driven, no business values in code):
```yaml
soundtrack:
  discovery:
    sources:
      - name: "bundle_instagram"
        provider: "bundle.social"
        api_key_env: "BUNDLE_SOCIAL_API_KEY"
        team_id_env: "BUNDLE_TEAM_ID"
      - name: "pixabay"
        provider: "pixabay"
        api_key_env: "PIXABAY_API_KEY"
    search_queries_from: "draft.visual_direction.music"
    min_duration_s: 30
    require_preview_url: true
    require_commercial_safe: true
```

Search queries are derived from the draft's existing `visual_direction.music` block — the Writer already produces `mood`, `genre`, `tempo_bpm`, `energy_curve`. A config mapping table converts those to search terms. No business values in code.

### 2. LLM ranking with 20% popularity weight (new — not in AMENDMENT-010)

A new `prompts/soundtrack_ranking.md` + JSON schema + validator. The LLM receives filtered candidates + the script's audio intent and returns a ranked top 3.

**Ranking weights (config-driven):**
```yaml
soundtrack:
  ranking:
    mood_fit_weight: 0.80
    popularity_weight: 0.20
    popularity_metrics: [usage_count, videos_in_window]
```

The ranking prompt instructs: "Rank by mood/fit as the primary criterion (80% weight). Factor in popularity/trending at 20% weight. When two tracks are similarly matched on mood and voice fit, prefer the more popular/trending one. Never sacrifice mood fit for popularity."

Popularity is a tie-breaker with a defined seat at the table, not the primary driver. The LLM sees usage_count and trending velocity for each candidate and applies the 20% weight in context — not as a mechanical formula.

### 3. Auto-apply (modifies VF-VS-503)

The LLM's #1 recommended track is **automatically downloaded, mixed, and rendered** into the final video. No separate soundtrack gate. The operator reviews the complete video (with music already in it) at the existing Gate 2.

This replaces the gate-before-mix model with mix-then-review. The operator still approves the piece before publish — the music is part of what they review. The per-piece approval rule is preserved.

### 4. Alternatives box at Gate 2 (new — not in AMENDMENT-010)

The Gate 2 review page shows the final video plus a box below it with the two LLM-ranked alternatives. Each has a preview link and a "Switch" button. If the operator doesn't like the music, they click "Switch" → pipeline re-mixes and re-renders → operator reviews the new version.

The alternatives and their rationales were already computed by the LLM at ranking time and persisted on the asset. Switching is mechanical (FFmpeg mix + video audio swap) — no API spend, no LLM calls.

### 5. Mix engineering with energy curves (extends VF-VS-504)

A new `src/soundtrack_mix.py` module handles the mechanical mixing after the ranking (or after a switch):

- Download the approved track
- Normalize bed to target loudness (config)
- Generate per-beat volume automation from the script's `energy_curve` intent + measured VO timeline
- Mix bed under VO with the generated automation
- Loudness-normalize the final mix
- Mechanical checks: duration match, audio present, loudness within bounds, VO intelligible (VO mean > bed mean by at least 3 dB)

**Energy curve mapping (config-driven):**
```yaml
soundtrack:
  mixing:
    bed_target_loudness_lufs: -18
    final_target_loudness_lufs: -16
    ducking:
      default_depth: 0.20
      attack_s: 0.3
      release_s: 0.5
    energy_curve_mapping:
      intro: 0.25
      build: 0.35
      duck: 0.18
      lift: 0.40
      settle: 0.35
```

The energy curve is NOT hardcoded. It comes from the script's `energy_curve` intent (produced by the Writer) mapped through config templates. Different content needs different curves — the config drives it, not Python constants.

## Revised pipeline flow

**AMENDMENT-010 flow:**
```
Writer → Gate 1 → VO Gen → [VF-VS-502: LLM proposes soundtrack plan] → [VF-VS-503: Soundtrack gate] → Mix → Assembly → Gate 2
```

**Revised flow:**
```
Writer → Gate 1 → VO Gen → Discovery → LLM Ranking → Auto-Mix → Assembly → Gate 2 (review video + alternatives box)
                                                    ↳ if operator switches → re-mix → re-render → re-present
```

The soundtrack stage sits between VO generation and final assembly — because the mix needs the measured VO timeline (beat durations) to generate the energy curve, and the final video needs the mixed audio track.

## What gets persisted on the asset

```json
{
  "soundtrack": {
    "candidates_count": 78,
    "ranking": {
      "recommended": { "title", "artist", "audio_id", "source", "usage_count", "rationale", "fit_score", "popularity_tier" },
      "alternatives": [
        { "title", "artist", "audio_id", "rationale", "trade_off", "popularity_tier" },
        { "title", "artist", "audio_id", "rationale", "trade_off", "popularity_tier" }
      ]
    },
    "active_track": "audio_id",
    "mix": {
      "bed_path": "...",
      "mix_path": "...",
      "energy_curve": [0.25, 0.30, 0.35, 0.18, 0.40, 0.35],
      "final_loudness_lufs": -16.0,
      "vo_intelligible": true
    },
    "ranking_provenance": { "prompt_file", "prompt_version", "model", "input_hash", "validated" }
  }
}
```

`active_track` changes when the operator switches. The full ranking + provenance never changes — it's the record of what the LLM recommended and why.

## Charter compliance analysis

### What stays compliant

- **Per-piece approval before publish** — the operator still reviews and approves the final video (with music) before it publishes. No auto-publish.
- **No business values in code** — sources, weights, energy curves, target loudness, search query mappings all in config.
- **LLM does judgment, scripts do mechanics** — discovery and mixing are mechanical; ranking is LLM judgment.
- **Provenance** — the ranking LLM call is logged like every other LLM call (input hash, prompt file + version, model, raw output, validated output, verdict).
- **Deterministic where possible** — mix engineering is deterministic (same input → same output); ranking uses temperature 0.

### What changes from the charter

AMENDMENT-010 added to the charter (§4, Design rules):
> "Every Reel has an explicit soundtrack mode. VO-only requires a rationale and operator approval. Silent VO-only is not valid."
> "The operator gates the soundtrack preview before any music/SFX acquisition."

This divergence changes the second rule. With auto-apply:
- Music IS acquired and mixed before the operator sees it.
- The operator reviews the **result** (final video with music), not the **plan** (soundtrack plan before mixing).
- The operator can **reject and switch** to an alternative, or **reject entirely** and go VO-only (which still requires a rationale).

### Licensing provenance question

With the gate, there was a signed gate token proving the operator approved a specific track. With auto-apply, the provenance trail is: "the LLM picked this track from a commercial-safe catalog (Meta-authorized Instagram audio, pre-cleared for commercial use), mixed it into the video, and the operator approved the final video that contained it."

**Question for the architect:** Is this provenance trail sufficient for licensing purposes, or does the gate token still need to be recorded even though the UX is "review the final video"? If the gate token is still needed, it can be recorded automatically when the operator approves the final video at Gate 2 (the approval implicitly covers the music in the video). This preserves the licensing record without requiring a separate gate.

### The vo_only case

If the LLM determines that no suitable track was found (or all candidates rank below a quality threshold), the pipeline produces a VO-only video. The `vo_only_rationale` is still required (per AMENDMENT-010 Condition 4). The operator reviews the VO-only video at Gate 2 and must explicitly approve VO-only — silent VO-only is still not valid.

## What this does NOT change

- The four content gates, per-piece publish approval, no auto-publish — unchanged.
- The Writer/Assembler boundary — soundtrack ranking is an Assembler-side process, not audience copy.
- The eight living modules, Process Registry, provenance, determinism — unchanged.
- AMENDMENT-010 Conditions 1, 2, 3, 5, 6, 7 — unchanged. This divergence only modifies Condition 4 (Phase M13-E).
- The `soundtrack_plan.py` module — still validates the plan; we feed it the ranking output instead of a manual operator plan.

## Implementation tasks (proposed for BUILD_PLAN)

### VF-VS-510 — Soundtrack discovery service
`src/soundtrack_discovery.py` — searches commercial-safe audio catalogs via API, filters candidates by hard constraints. Config-driven source registry. Output: candidate list with metadata.

### VF-VS-511 — Soundtrack ranking prompt + schema
`prompts/soundtrack_ranking.md` + `prompts/soundtrack_ranking_schema.json`. LLM ranks candidates by mood/fit (80%) + popularity (20%). Returns top 3 with rationale. Validator ensures 1 recommended + 2 alternatives. Provenance logged.

### VF-VS-512 — Soundtrack mix engineering
`src/soundtrack_mix.py` — downloads approved track, normalizes, generates per-beat volume automation from energy curve config + VO timeline, mixes under VO, loudness-normalizes. Mechanical checks: duration, loudness, VO intelligibility.

### VF-VS-513 — Auto-apply and alternatives in Gate 2 review
Wire the ranking + auto-mix into the pipeline between VO generation and assembly. Extend the Gate 2 review page to show the alternatives box with preview links and switch buttons. Switching triggers re-mix + re-render.

### VF-VS-514 — Soundtrack quality checks
Mechanical: duration match, loudness bounds, VO intelligibility (VO > bed by 3 dB), bed-too-loud-in-intro detection (first-beat bed level vs VO level). Optional LLM advisory: does the bed compete with the VO? Does ducking work?

### VF-VS-515 — Soundtrack config
`config/models.yaml` → `soundtrack` block: discovery sources, ranking weights, mixing params, energy curve mapping. All config-driven, zero business values in code.

## Evidence from the manual session

The full workflow was demonstrated manually on Draft 8 (2026-07-18):
- Searched Bundle.social Instagram API across 6 mood/genre queries → 107 candidates
- Filtered to 78 (duration ≥ 30s, preview URL) → LLM ranked top 3
- LLM recommended "Jasmine" by Giulio Cercato (matched "reflective" + "minimal")
- Operator approved the recommendation
- First mix: bed too quiet (sidechain compression over-ducked) → fixed
- Second mix: bed too loud at intro → fixed with graduated energy curve
- Final mix: bed at 25% intro → 35% build → 18% TURN → 40% PAYOFF → 35% close
- Final video produced with Bajan VO + Jasmine bed, 72s, broadcast loudness

The energy curve was tuned by ear through operator feedback. The config-driven mapping would encode this as a template, not a hardcoded constant.

## Request

Architect review requested on:
1. The shift from gate-before-mix to auto-apply-then-review — does this need a charter amendment, or is it within AMENDMENT-010's scope to modify?
2. The licensing provenance question — is the "operator approved the final video containing the track" trail sufficient, or does the gate token still need to be explicitly recorded?
3. The 20% popularity weight in the ranking prompt — is this acceptable, or should popularity be excluded from the LLM's ranking and shown only as metadata for the operator's decision?
4. The task numbering (VF-VS-510 through 515) — should these replace VF-VS-501 through 504, or supplement them?