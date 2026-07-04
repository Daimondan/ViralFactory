# MANIFEST-2026-07-04-ai-tells-voice-deepening.md

**Filed by:** Architect (vf-architect profile)  
**Date:** 2026-07-04  
**Purpose:** Notify builder of the AI tells + voice-deepening correction applied after M9/T9.5 review. This is the builder's starting point for understanding what changed and what must be preserved.

## What happened

The operator challenged the system's approach to avoiding AI writing. The correction is **not** a bolt-on humanizer. It changes the pipeline so ideas and drafts are shaped by the person's voice and cognitive patterns from the start, and so the AI review loop automatically fixes high-confidence AI writing tells before Gate 2.

The architect reviewed the live repo after builder completed M9 and found two concrete T9.5 implementation defects:

1. **Self-audit fix was a no-op:** flags were marked `applied`, but `platform_content` did not change.
2. **AI-review revision stripped real module context:** revision calls used placeholders like `(same as previous)` instead of loading the real Voice Profile, Tells Checklist, Story Frameworks, Audience Insights, Viral Patterns, Visual Style, and Format Guide.

Both defects are now fixed and tested.

## Files already committed by the architect

These files are already in the repo in commit `3e7bd9c` (`FIX: apply AI tells and voice deepening correction`). The builder does **not** need to file or recreate them. This manifest is the starting note and reading order.

| File | Action | Notes |
|---|---|---|
| `docs/reviews/CORRECTION-ai-tells-and-voice-deepening-v1.md` | ADD | Main correction document. **Read this first.** It explains findings, rationale, and acceptance criteria. |
| `prompts/shared/ai_tells_v1.md` | ADD | Canonical AI writing tells catalog with HIGH/MEDIUM/LOW confidence levels. Includes negative parallelism (`it's not X, it's Y`) and broader Wikipedia/Tropes-derived tells. |
| `prompts/views.yaml` | REPLACE | Adds `voice_profile` to idea generation and `ai_tells` to draft generation. |
| `prompts/ideas/generate_v1.md` | REPLACE | v1.4. Ideas now load Voice Profile first and must be born in the person's mental shape. |
| `prompts/draft/generate_v3.md` | REPLACE | Loads the shared AI tells catalog and performs a concrete 6-category self-audit. HIGH-confidence tells require `fix_applied`. |
| `prompts/draft/alignment_check_v1.md` | REPLACE | v1.1. Alignment check now does a second pass for surviving HIGH-confidence AI tells via `ai_tell_survived`. |
| `prompts/voice_profile/analyze_v2.md` | REPLACE | v2.1. Adds cognitive dimensions: mental models, obsessions, contrarian takes, story instincts, frame. |
| `playbooks/voice-profile-builder.md` | REPLACE | v1.1. Playbook now requires cognitive patterns and evidence. |
| `src/context_assembly.py` | REPLACE | Adds generic shared prompt-file loading from views.yaml (`file: shared/...`) with provenance. |
| `src/produce_chain.py` | REPLACE | Fixes self-audit no-op and restores full module context during AI-review revision rounds. |
| `src/pipeline.py` | REPLACE | Documents/permits `confidence` and `fix_applied` in `self_audit_flags`. |
| `tests/test_module_context_assembly.py` | REPLACE | Adds regression for shared prompt-file loading. |
| `tests/test_t9_5_ai_review_loop.py` | REPLACE | Adds regressions proving self-audit fixes change real `platform_content` and flags without concrete fixes stay active. |
| `tests/test_t8_4_source_refs.py` | REPLACE | Updates idea prompt version expectation to v1.4. |
| `README.md`, `docs/CONTEXT.md`, `BUILD_PLAN.md`, `docs/PROGRESS.md`, `CHANGELOG.md` | REPLACE | Living docs updated to current state and 761 passing tests. |

## Builder reading order

Before doing any next implementation work, read:

1. `docs/reviews/CORRECTION-ai-tells-and-voice-deepening-v1.md`
2. `prompts/shared/ai_tells_v1.md`
3. `prompts/draft/generate_v3.md`
4. `prompts/draft/alignment_check_v1.md`
5. `src/produce_chain.py` — especially `_apply_self_audit_fixes()` and `_revise_draft_with_recommendations()`
6. `prompts/ideas/generate_v1.md`
7. `prompts/voice_profile/analyze_v2.md`
8. `playbooks/voice-profile-builder.md`
9. `docs/CONTEXT.md` and `BUILD_PLAN.md`

## Rules builder must preserve

1. **No bolt-on humanizer.** AI tells are handled at ideation, drafting, self-audit, and review-loop levels.
2. **High-confidence tells are auto-fix candidates.** The Writer must provide concrete `fix_applied` text; the pipeline may only mark a flag `applied` if text actually changed.
3. **Medium/low-confidence tells are context-dependent.** Do not overcorrect good copy just because it resembles an AI tell.
4. **Alignment check is the second pass.** It must flag surviving HIGH-confidence tells as `ai_tell_survived`.
5. **Revision rounds must load real module context.** Do not replace module variables with placeholders like `(same as previous)`.
6. **Voice Profile includes cognition, not just wording.** Ideation must use mental models, obsessions, contrarian takes, story instincts, and frame.
7. **The StackPenni Voice Profile is still not complete.** The prompt/playbook are fixed, but tenant #1 still needs real corpus upload or interview fallback + calibration.

## Verification already run

```bash
cd /home/daimon/ViralFactory
source .venv/bin/activate
python3 -m pytest -q
# 761 passed in 38.10s
```

Pytest emitted non-fatal worker cleanup messages about `no such table: materials`, but exit code was 0 and all tests passed.

## What the builder does NOT need to do

- Do not re-file the correction document.
- Do not recreate the AI tells catalog.
- Do not re-implement the self-audit fix from scratch.
- Do not make new design decisions around AI tells without filing a divergence.

## Next likely builder task

The next practical quality unlock is to run/complete real Voice Profile onboarding for StackPenni using either:

- real Daimon/StackPenni corpus uploads, or
- interview fallback, followed by calibration.

Until that happens, the system can avoid generic AI tells better, but it still cannot fully think like Daimon from evidence.
