# Loop: ViralFactory Full-Pipeline Operator Evaluation

> Adapted from [Loop #010 — The full product evaluation loop](https://signals.forwardfuture.ai/loop-library/loops/full-product-evaluation-loop/) (ForwardFuture Signals loop library). Adaptations are unpublished until promoted to the live catalog.

## Use when
A full end-to-end operator-style QA pass is needed across the ViralFactory staged pipeline — from idea cards through to a rendered, inspectable video — where the operator's real review of the video is the final gate. Use this whenever the pipeline must be proven on a fresh run, not just unit tests.

## Prompt
Test ViralFactory end-to-end, as a human operator using only the web UI (Flask console at `http://127.0.0.1:9121`). Do not skip stages by hitting internal APIs unless the UI route is broken and the bug must be documented. The full pipeline must produce one finished **Reel video** that the operator (Daimon) can inspect.

**Each pass:**
1. **Reset.** End every existing idea card (kill, not delete — preserve provenance). Confirm the queue is empty.
2. **Generate.** Trigger idea generation through the UI. Wait for fresh `ai-originated` cards in `new` state.
3. **Drive the pipeline.** For each stage, use the UI exactly as Daimon would — click the action button, fill any required field, wait for the async chain to finish:
   - **Gate 1:** approve one card with a Reel-capable treatment. Capture the auto-started Writer chain.
   - **Gate 2:** review the draft, approve (ship-forward). Edits optional on first pass.
   - **Assembler / soundtrack gate:** approve the soundtrack plan when prompted (VO-only is acceptable for the first clean pass).
   - **Gate 3:** approve the assembled asset.
   - **Render:** trigger video render and wait for completion.
4. **Deliver the video for inspection.** Upload the rendered `.mp4` to Google Drive (vf-coder profile token) and produce a shareable link. Post the link + a one-paragraph pass report to Daimon.
5. **Document every issue.** Maintain `docs/QA-loop-findings.md` with one entry per issue, no matter how small — UI jank, stale state, wrong counts, dead buttons, copy confusion, minor annoyance, suggested improvement, backend error, slow step, missing feedback. Each entry: id, severity (blocker / major / minor / polish), surface (route), reproduction, expected, actual, fix commit (filled when fixed).
6. **Wait for operator inspection.** Daimon reviews the video link and the findings list. He gates the next pass — approve, reject, or add issues.
7. **Fix all issues.** Apply fixes in code/config, commit each with a test, mark the findings entry fixed. Re-run the relevant surface to confirm.
8. **Repeat.** Reset again, generate, drive the pipeline, produce a new video, send the link, append findings. Stop only when a full pass produces a clean video AND an empty findings list AND Daimon signs off.

### Rules
- Test as a human. Read every screen, count every button, expand every preview. Don't trust the DOM to match the database — verify both.
- No patch scripts. Wrong output → fix the prompt/config/validator, versioned. (Per charter §7.)
- Every fix commits with at least one test; suite stays green.
- Log every decision in `CHANGELOG.md` with type tag (TECH, LOGIC, STRUCTURE, STRATEGIC, OPS, FIX).
- A task is done only when its acceptance criteria pass. Can't meet them? Open a GitHub issue with the blocker; move on.

## Verify
A full pass produces one finished Reel video, delivered as a shareable Google Drive link, that Daimon has inspected and approved. The findings list is empty. Every earlier finding is fixed, committed with a regression test, and backed by evidence. The automated suite passes green throughout.

## Keywords
viral factory, staged pipeline, end-to-end video pipeline, operator UI test, real user testing, QA loop, reel render, soundtrack gate, content gate, production-grade QA

## Related
The quality streak loop, The full product evaluation loop (source)