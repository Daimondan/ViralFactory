# BUILDER-NOTE-015 — Soundtrack discovery, ranking, and auto-apply divergence

**To:** Architect
**From:** Builder
**Date:** 2026-07-18
**Subject:** DIVERGENCE-015 filed — soundtrack pipeline redesign with auto-apply + alternatives

I've filed `docs/decisions/DIVERGENCE-015-soundtrack-discovery-ranking-auto-apply.md` for your review.

## What it proposes

During today's Draft 8 soundtrack session, Daimon and I worked through the full soundtrack selection workflow manually: searching Bundle.social's Instagram audio API, filtering 107 candidates to 78, LLM-ranking the top 3, operator-approving the pick, mixing it under the Bajan VO with energy curves, and iterating on the mix based on operator feedback ("too loud at the beginning").

The manual workflow worked well and revealed a different operator UX than what AMENDMENT-010 Phase M13-E currently specifies. This divergence proposes:

1. **Discovery service** (new) — API-based search of commercial-safe audio catalogs, config-driven
2. **LLM ranking with 20% popularity weight** (new) — mood/fit at 80%, popularity/trending at 20% as a tie-breaker
3. **Auto-apply** (modifies VF-VS-503) — LLM's #1 pick is automatically mixed and rendered; no separate soundtrack gate
4. **Alternatives box at Gate 2** (new) — operator reviews the final video with music already in it, sees 2 alternatives they can switch to
5. **Mix engineering with energy curves** (extends VF-VS-504) — per-beat volume automation from script intent + config

## What I need from you

Four questions in the divergence doc:

1. **Gate shift:** Auto-apply changes "gate before mix" to "mix then review with alternatives." Does this need a charter amendment, or is it within AMENDMENT-010's scope to modify?
2. **Licensing provenance:** Is "operator approved the final video containing the track" sufficient, or does the gate token still need explicit recording?
3. **Popularity weight:** Is 20% popularity weight in the LLM ranking acceptable, or should popularity be metadata-only for the operator?
4. **Task numbering:** Should VF-VS-510 through 515 replace or supplement VF-VS-501 through 504?

The full evidence from the manual session is in the divergence doc. Happy to discuss any of these before you rule.