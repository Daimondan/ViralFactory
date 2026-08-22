# VF-PROOF-1618 — Legacy pipeline baseline

**Date:** 2026-08-22
**Scope:** truthful legacy comparison baseline before M17 Story Room implementation
**Service:** `viralfactory.service` on `127.0.0.1:9121`
**Origin baseline revision:** `b0dfc3d` (`origin/main`) before the baseline-only fixes recorded in this task

## Runtime

- `systemctl is-active viralfactory.service` → `active`
- `GET /health` → HTTP 200, `{"status":"ok","version":"0.2.0"}`
- Restart after baseline fixes completed successfully; the same health response remained 200.

## Deployed browser walkthrough

A headless Chromium CDP walkthrough exercised these real routes without approval or publish mutations:

| Surface | Result |
|---|---|
| `/` | HTTP 200; title `ViralFactory — StackPenni`; home controls rendered |
| `/ideas` | HTTP 200; Gate 1/seed controls and empty queue rendered |
| `/visual-treatments` | HTTP 200; vector proposal remained `PENDING OPERATOR DECISION` |
| `/inspiration` | HTTP 200; stale evidence labels and explicit promotion actions rendered |
| `/create/draft/35` | HTTP 200; Writer page rendered |
| `/create/assets/35` | HTTP 200; exact mapping is draft 35 → asset 29; existing final is marked `Needs re-render` |
| `/published` | HTTP 200; historical published record and historical Buffer failure rendered |

## Corrected baseline evidence

### Mobile layout

True 390px mobile emulation of `/` after the responsive topbar fix returned:

```json
{"innerWidth":390,"visual":390,"scrollWidth":390,"clientWidth":390,"overflow":false}
```

The fix wraps the topbar and its navigation at the existing 768px breakpoint. The new regression test is `tests/test_mobile_layout_css.py`.

### VO control and operator boundary

`/create/assets/35` now exposes an explicit **Regenerate voice-over** action that sends `{"regenerate": true}` and creates a new measured take without changing the approved script. The action is not automatic.

The operator explicitly stopped draft 35 regeneration. The attempted local Chatterbox run then exited with:

```json
{"error":"VO generation failed: Expecting value: line 1 column 1 (char 0)"}
```

Post-stop verification found no `vo_subprocess.py` or Chatterbox process for asset 29. The prior VO take, final artifact, and review rows were not replaced. The asset remains truthfully blocked with the persisted review verdict `needs_rerender` and the existing audio-coherence finding. This is recorded as **operator-stopped**, not as a pass.

### Buffer boundary

The current adapter's Instagram Reel payload includes:

```json
{"metadata":{"instagram":{"type":"reel","shouldShareToFeed":true}}}
```

The focused contract test passes. The Results page's missing-field message is a historical publish attempt from before the current contract; no new live publish was authorized or attempted during this proof. Live publish/auth verification is therefore recorded as **not authorized**, not as passed or failed.

## Automated verification

- Focused baseline/changed-surface suite: **50 passed in 2.11s**
- Full configured suite: **2631 passed, 2 skipped in 460.14s (0:07:40)**
- `git diff --check`: passed before this evidence commit

## Gate integrity

- No Gate 1, Gate 2, Gate 3, or Gate 4 approval was created by this walkthrough.
- No Buffer publish or schedule mutation was made.
- The pending vector treatment proposal remains pending.
- The truncated-VO artifact remains blocked; operator-stopped remediation is preserved as an honest baseline condition.

## Baseline disposition

The legacy baseline is complete for comparison: mobile overflow is corrected, the VO remediation control is visible and operator-gated, the full suite is green, and the remaining VO/live-publish rows are explicitly recorded as operator-stopped or not authorized. M17 may proceed without claiming that the blocked historical artifact or live Buffer publish proof passed.
