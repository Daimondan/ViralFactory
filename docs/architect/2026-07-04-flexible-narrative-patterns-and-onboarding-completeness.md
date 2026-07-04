# Architect Brief: Flexible Narrative Patterns + Onboarding Completeness

**Date:** 2026-07-04
**Author:** Hermes Agent (for Daimon)
**Status:** In Progress — implementation plan at `docs/plans/2026-07-04-flexible-narrative-patterns-and-onboarding-completeness.md`

---

## Problem 1: Hardcoded Narrative Structure

### What's Wrong

The story frameworks module forces every subject type into the same 4-beat dramatic arc: `entry_point → tension → turn → landing`. This is hardcoded in three places:

1. **Schema** (`src/module_store.py:1058-1084`) — `STORY_FRAMEWORKS_SCHEMA` requires `entry_point`, `tension`, `turn`, `landing` as mandatory fields
2. **Prompt** (`prompts/story_frameworks/analyze_v2.md`) — explicitly demands these 4 beats per framework
3. **Converter** (`src/module_store.py:1087-1111`) — `story_frameworks_to_markdown()` renders only these 4 fields

### Why It's Wrong

A listicle doesn't have tension/turn. A tutorial is problem/steps/result. A hot take is claim/evidence/counter/verdict. A receipt card is claim/source/meaning/move. Forcing every subject into the same shape produces awkward frameworks where "tension" and "turn" are stretched to mean nothing.

### The Fix

**Config-driven narrative patterns.** A new `config/narrative_patterns.yaml` declares known patterns:

| Pattern | Beats | Best for |
|---|---|---|
| dramatic_arc | entry_point, tension, turn, landing | Emotional stories, cultural pieces |
| myth_buster | myth, reality, proof, takeaway | Debunking misconceptions |
| how_to | problem, steps, result | Practical tutorials |
| hot_take | claim, evidence, counter, verdict | Contrarian opinions |
| listicle | hook, items, summary | Numbered insights |
| before_after | before, catalyst, after, lesson | Transformation stories |
| receipt_card | claim, source, meaning, move | Evidence-first content |
| pattern_breaker | setup, fork, divergence, lesson | "Same background, different decision" |

The LLM **selects** the best pattern per subject type from the config. If none fit, it can propose a custom one (`structure_name: "custom"` + its own beats).

**Schema change:** `structure_name` + `beats: [{name, content}]` replaces the 4 hardcoded fields.

**Generalizability:** Any business can add their own patterns to `narrative_patterns.yaml`. The config is the single source of truth — no code changes needed to add a pattern.

### Files Changed

| File | Change |
|---|---|
| `config/narrative_patterns.yaml` | NEW — 8 default patterns + allow_custom flag |
| `src/module_store.py` | `STORY_FRAMEWORKS_SCHEMA` — flexible beats; `story_frameworks_to_markdown()` — renders any beats |
| `prompts/story_frameworks/analyze_v3.md` | NEW — LLM sees available patterns, selects per subject |
| `src/app.py:3212` | Route points to v3 prompt, loads patterns config |
| `src/app.py:1080,1443` | Playbook runner references updated to v3 |
| `tests/test_narrative_patterns.py` | NEW — schema, converter, diversity tests |

### Backward Compatibility

The existing `modules/stackpenni/story-frameworks.md` (v1.0 with old format) still works because:
- The drafter prompt (`draft/generate_v2.md`) injects `{story_frameworks}` as raw markdown — it doesn't parse specific beat names
- The LLM reads whatever structure is in the module and adapts
- No code assumes specific beat names downstream

When story frameworks are re-generated, they'll use the new v2 schema. Old modules remain readable until explicitly regenerated.

### Future Evolution

- When a published piece performs well, the pattern that produced it gets reinforced
- New patterns discovered in the wild (admired examples, what works on X/IG) get added to the config
- The patterns config is a living document, not a fixed schema
- This is where "learnings shape it over time" comes in

---

## Problem 2: Onboarding Inputs Left Blank

### What's Wrong

During onboarding, 188 materials were uploaded but all show **0 chars** of normalized content. The dependent playbook runs (viral-patterns-starter, voice-profile-builder) stayed "pending" — never completed. The story frameworks analysis ran with all blank inputs:

| Required Input | Status | What Happened |
|---|---|---|
| `admired_examples` | ❌ Missing | Viral Patterns playbook never completed |
| `operator_stories` | ❌ Missing | Not extracted from onboarding conversation |
| `voice_summary` | ❌ Missing | Voice Profile Builder never completed |

Every story framework says "No admired examples provided" and "No operator stories provided" — the LLM generated ungrounded output from business config alone.

### Root Causes

1. **No visibility** — the system doesn't show what's missing vs what's collected
2. **No enrichment path** — when inputs are blank, there's no way to fill them without re-running entire onboarding
3. **Materials not processed** — 188 uploaded materials all show 0 chars of normalized content (separate issue, but compounding)
4. **Onboarding conversation has rich data** — the entire Brand Strategy Lock Sheet is in `session_messages` (14K chars), but none was extracted into structured fields

### The Fix — Two Parts

#### Part A: Completeness Dashboard

A new page at `/onboarding-health` that shows a matrix of:

| Module | Required Input | Status | Source Playbook |
|---|---|---|---|
| Story Frameworks | admired_examples | ❌ Missing | viral-patterns-starter |
| Story Frameworks | operator_stories | ❌ Missing | story-frameworks-starter |
| Story Frameworks | voice_summary | ❌ Missing | voice-profile-builder |
| Business Profile | business_qa | ✅ Present | business-profile-intake |

**How it works:**
1. Each playbook declares its `required_inputs` via `<!-- required_inputs: key1, key2 -->` frontmatter comment
2. `PlaybookParser` reads these into a `required_inputs: list[str]` field
3. `check_completeness()` function maps each required input to its `collected_inputs` key and checks if it's filled
4. The dashboard shows present/missing with visual indicators

**Non-blocking:** You can still generate with gaps — but the dashboard makes the gap visible and warns about impact.

#### Part B: Source Mining

For each missing input, two options:

1. **"Find in sources"** — AI scans uploaded materials, onboarding transcript, and source bank for the missing info
   - `POST /api/onboarding/mine-sources` with `{input_name, source_playbook}`
   - LLM extraction call against relevant data
   - If found, saves to onboarding run's `collected_inputs`
   - Honest about gaps — if nothing relevant exists, says so

2. **"Enter manually"** — operator types the value directly
   - `POST /api/onboarding/fill-input` with `{input_name, value}`
   - Saves to onboarding run's `collected_inputs`

After filling a gap, the operator can re-run the affected playbook and get a properly grounded module.

### Files Changed

| File | Change |
|---|---|
| `playbooks/*.md` (7 files) | `<!-- required_inputs: ... -->` frontmatter added |
| `src/playbook_runner.py` | `Playbook.required_inputs` field + parser |
| `src/onboarding_completeness.py` | NEW — `check_completeness()` function + `INPUT_SOURCE_MAP` |
| `src/app.py` | New routes: `/onboarding-health`, `/api/onboarding/mine-sources`, `/api/onboarding/fill-input` |
| `src/templates/onboarding_health.html` | NEW — dashboard template |
| `prompts/onboarding/mine_source_v1.md` | NEW — extraction prompt |
| `tests/test_playbook_required_inputs.py` | NEW — parser tests |
| Nav links in ~11 templates | "Module Health" link added |

---

## Implementation Status

| Task | Status | Commit |
|---|---|---|
| 1: Create narrative_patterns.yaml | ✅ Done | `ecb39f0` |
| 2: Update STORY_FRAMEWORKS_SCHEMA | In progress (subagent) | |
| 3: Update story_frameworks_to_markdown | In progress (subagent) | |
| 4: Update analysis prompt (v3) + routes | Pending | |
| 5: Verify backward compatibility | Pending | |
| 6: Test for pattern diversity | Pending | |
| 7: Add required_inputs to playbooks | In progress (subagent) | |
| 8: Build completeness checker | Pending | |
| 9: Build dashboard route + template | Pending | |
| 10: Build source mining API | Pending | |
| 11: Build manual fill API | Pending | |
| 12: Add Module Health to nav | Pending | |
| 13: Full integration test | Pending | |
| 14: CHANGELOG + PROGRESS docs | Pending | |

---

## Design Principles Followed

1. **Config-driven, not hardcoded** — patterns in YAML, required inputs in playbook frontmatter
2. **LLM does judgment work** — pattern selection per subject, source mining extraction
3. **Generalizable** — any business can add patterns or modify required inputs
4. **Honest about gaps** — source mining says "not found" rather than fabricating
5. **Non-blocking** — dashboard surfaces gaps but doesn't prevent generation
6. **Backward compatible** — old v1 modules still readable by the drafter
7. **All decisions in CHANGELOG** — every change documented

---

## Open Questions for Architect

1. **Materials processing:** 188 uploaded materials show 0 chars normalized content. This is a separate bug — the materials intake pipeline isn't processing uploads. Should this be filed as a separate issue or addressed as part of this work?

2. **Onboarding run model:** Currently there's one "onboarding" playbook run (run 26) that collected everything into a shared pool. Downstream playbooks (viral-patterns-starter, voice-profile-builder) have their own runs but stayed "pending." Should the completeness dashboard check across all runs, or should there be a canonical "latest onboarding run" that downstream playbooks draw from?

3. **Re-generation flow:** After filling a gap (e.g., operator_stories), the operator needs to re-run the affected playbook (e.g., story-frameworks-starter). Should this be a one-click "regenerate" from the dashboard, or should they navigate to the playbook page and re-run manually?

4. **Narrative patterns versioning:** When new patterns are added to `narrative_patterns.yaml`, should old story framework modules be marked as "stale" (generated with pattern set vN, current is vN+1)?