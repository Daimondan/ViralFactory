# DIVERGENCE-023: No ratified Format Guide mapping for episode-format routing

**Filed by:** Builder
**Date:** 2026-07-25
**Status:** AWAITING ARCHITECT RULING
**Severity:** P0 — blocks `CORRECTION-episode-wiring-and-source-diversity-v1.0` P0-2
**Type:** LOGIC / STRUCTURE

## Observed gap

P0-2 requires `media_plan_v2` selection to be driven by an asset format resolving to an episode format **from the Format Guide**. The active `modules/stackpenni/format-guide.md` has no episode-format entry, no `playbook_type`/equivalent field, and no reference to `episode-format-parable`.

The repository does contain `modules/stackpenni/episode-format-parable.md`, and `prompts/views.yaml` exposes it to the Writer and `media_plan_v2`. That is not a Format Guide mapping and cannot safely be used to infer selection: doing so would introduce an unratified routing convention or hardcode a tenant-specific format/module name in the harness.

The two governing visual documents also remain DRAFT/PROPOSED. The registry intentionally exposes only approved reference assets to generation, so a registry-anchored episode path must not consume their knowledge before their explicit operator decisions.

## Consequence

The required live route cannot be truthfully enabled for any production asset yet. A generic resolver can be built only after the guide supplies a ratified, structured signal identifying:

1. which Format Guide entry is an episode format;
2. the episode-format module that governs it; and
3. whether a recorded governance decision is sufficient to consume the associated registry/canon material.

## Requested ruling

Define the versioned Format Guide fields that express episode routing and the approved module reference. The field vocabulary must be generic (not tenant names) and must be added to the Format Guide through its normal gate.

## Builder action

- Did **not** hardcode a business slug, format name, or module name.
- Did **not** infer episode status from filename conventions.
- Did **not** consume the DRAFT World Canon or PROPOSED Visual Style Amendment.
- Attempted to open the required GitHub blocker issue; `gh` is unauthenticated in this environment (`gh auth login` / `GH_TOKEN` required).
