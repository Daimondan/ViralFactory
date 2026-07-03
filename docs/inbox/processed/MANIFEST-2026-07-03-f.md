# Inbox Manifest — 2026-07-03 (batch F)

| File | Destination | Action |
|---|---|---|
| CORRECTION-generation-diversity-and-asset-continuity-v1.0.md | docs/corrections/CORRECTION-generation-diversity-and-asset-continuity-v1.0.md | ADD |

## Notes for Hermes

Fixes four operator-reported failures confirmed at HEAD `ce307a3`: (S1) idea generation is deterministic — temp-0 backend + static input + no memory of existing/killed cards; (S2) no format-usage feedback into treatments; (S3) fan-out loops business.yaml platforms and paraphrases the Gate-2-approved text even on the native platform; (S4) draft-stage preview images orphaned when assets regenerate.

Key rulings: new `ideator` backend alias with real temperature (drafter also gets non-zero temp — the temp-0 guardrail covers judgment/extraction only, clarify in BUILD_PLAN); recent-ideas + kill-lessons context in the ideas prompt (→ v1.2); mechanical RSS source snapshot as interim real material (NOT M6 — dumb fetch only); fan-out platform set resolved from the treatment format's Format Guide entry with per-draft override; native platform packaged verbatim (structure-only LLM call at most, new `assets/structure_v1.md`); draft media rows linked into spawned assets (same file paths, no re-render), Gate 3 badges them.

Coordination: fold the S3 preserve-wording instruction into the same `fan_out` v2.1 bump already owed to the module-context correction. When T2.12 `processes.yaml` lands, the new variables join the ideas process `inputs` and structuring becomes its own spec. Sequence: S1a → S3 → S1b/S1c → S4 → S2. Do NOT run the 10-piece M3 sprint checkpoint before S1 and S3 land.

Add T3.13 to BUILD_PLAN per §7 and annotate T3.7's AC. Update changelog; move this manifest to docs/inbox/processed/ when done.
