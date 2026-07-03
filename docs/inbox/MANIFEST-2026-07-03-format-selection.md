# Inbox Manifest — 2026-07-03 (format selection)

| File | Destination | Action |
|---|---|---|
| `CORRECTION-format-selection-living-v1.0.md` | `docs/corrections/CORRECTION-format-selection-living-v1.0.md` | ADD |

## Notes for Hermes

- **Diagnosis correction first:** the earlier analysis assumed the LLM sees the Format Guide decision table. It does not — `src/app.py` truncates all module injections to 2,000 chars (`[:2000]`, one site `[:1500]`) and the guide is 17KB. The model sees only the summary and half the X Thread entry. Read Part A before touching any prompts.
- Do NOT patch the decision table or add "prefer video" language anywhere. The table is being removed as selection authority (Part B). Any table-weighting fix is superseded by this correction.
- This work is pipeline-side and does not depend on the session-memory correction; it can proceed in parallel.
- Item 3 of the checklist (guide v1.1 migration) is human-gated: produce it, then hold for Daimon's approval before wiring it as the selection source.
- Update CHANGELOG on completion; move this manifest to `docs/inbox/processed/`.
