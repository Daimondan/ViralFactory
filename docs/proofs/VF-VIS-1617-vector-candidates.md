# VF-VIS-1617 — StackPenni vector comparison candidate proof

**Date:** 2026-07-30
**Status:** Registered as proposed candidates; operator approval remains pending

## Deployed proposal

- Endpoint: `POST /api/visual-treatments/proposals`
- Result: HTTP `200`, `status: pending`
- Pending proposal: `2`
- Treatment: `flat_vector_pennifold@1.0`
- Treatment status: `proposed`
- Reference status: all five `proposed`
- Operator page: `/visual-treatments`

The page presents five image cards with in-page previews and links that open the original PNG in a new fullscreen browser view. It shows the artifact SHA-256, dimensions, palette-lock verdict, forbidden SVG element counts, and report path. Mechanical evidence is not treated as approval.

## Exact comparison outputs

| Candidate | Artifact | SHA-256 | Dimensions | Palette evidence |
|---|---|---|---|---|
| room | `A-room-clean.png` | `09cf01db793976d20a8a0c0b618ad837f88df216de51ba92d21a259719fcd738` | 774×1376 | pass; forbidden SVG elements all zero |
| Fitzroy | `B-fitzroy-clean.png` | `06f7ffd6bb7d6cc4f21415eed4ea0b52fbf7250bfe0ff2167567443b3ff95e32` | 774×1376 | pass; forbidden SVG elements all zero |
| Stacks | `C-stacks-clean.png` | `e8f33b3093db6ef90daa036c8c3f731861eeafe6b0a2711e79d85dd575ca5cb7` | 774×1376 | pass; forbidden SVG elements all zero |
| newspaper | `D-newspaper-clean.png` | `eca80b2bc4a4ec8a0e3d9cb327b7372385a369f3f48424ea569d320928e6e3e3` | 774×1376 | pass; forbidden SVG elements all zero |
| controller | `E-controller-clean.png` | `194ba9afe9d460c479419ed5c455a0cd4c9acad449e094ca32869df2ad5673a1` | 774×1376 | pass; forbidden SVG elements all zero |

Source configuration and report paths are in `config/visual_treatment_proposals/stackpenni_flat_vector_pennifold.yaml`.

## Boundaries preserved

- Existing cinematic-painted Visual Style and existing cinematic assets remain intact.
- The vector treatment is not installed into the current module by this builder action.
- No vector candidate is approved or production-selectable.
- A future vector episode still requires separately approved treatment/reference candidates and an approved format/module binding.

## Verification

```text
/tmp/viralfactory-test/bin/python -m pytest -q \
  tests/test_vf_vis_1617_vector_candidates.py \
  tests/test_vf_vis_1615_visual_treatments.py \
  tests/test_vf_vis_1616_treatment_lineage.py
13 passed
```

The preview route test verifies one real PNG is served as `image/png` and traversal outside `assets/reference/` is rejected.
