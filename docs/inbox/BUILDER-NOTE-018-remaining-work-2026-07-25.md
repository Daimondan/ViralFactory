# BUILDER-NOTE-018 — Remaining work after 2026-07-25 session

> **Filed by:** Builder (Hermes)
> **Date:** 2026-07-25
> **Context:** Operator session focused on idea diversity, rendering, posting, and feedback. Cinematic realism direction chosen for Penny characters. 10 assets now at Gate 3.

## What was done this session

1. **Cinematic realism direction chosen** — Character Bible v2.0 (Fitzroy/Stackwell Pennifold) + Visual Style Guide v2.0 committed (ddf8904). 3-second test videos generated in both styles for comparison.
2. **Idea diversity fixes** — 10 travel RSS sources purged from DB, Reel bias removed from ideation prompt, story-frameworks.md confirmed deleted. New ideas show improved format distribution (2 Reels + 1 X Thread vs ~80% Reel before).
3. **Render state repair** — 9 assets fixed from pending→rendered (had final MP4s but state not updated). Stale job #75 force-failed. 10 assets now at Gate 3 ready for operator approval.

## Remaining work (in priority order)

### 1. FIX: Render service not updating asset_state after successful render
- **Problem:** `RenderReviewService.render_for_asset()` completes the render and writes the final MP4, but does not call `update_asset_state(asset_id, "rendered")`. The asset stays at "pending" even though the render succeeded and the file exists on disk.
- **Evidence:** 9 assets had completed render jobs with final MP4 files but asset_state stuck at "pending". Manual DB fix applied this session. Job #128 (asset 11) also completed without updating state (was fixed by the manual batch).
- **Fix location:** `src/services/render_review.py` — after successful render, before returning `ServiceResponse`, call `store.update_asset_state(asset_id, "rendered")`.
- **Priority:** P0 — every future render will get stuck without this fix.
- **Test:** Render an asset with a fresh DB entry, verify asset_state transitions to "rendered" after the render job completes.

### 2. FEED: Replacement RSS feeds for sources.yaml
- **Problem:** `config/sources.yaml` has `feeds: []` with a TODO comment. The source bank has no incoming RSS — all active sources are static seed_reference (books, papers) and manual operator seeds. No fresh material enters the source bank automatically.
- **What's needed:** Real RSS feeds covering AI tools and their impact on small businesses / Caribbean economies, wealth-building strategies / investing / financial literacy, Caribbean entrepreneurship and economic development, tech trends relevant to Caribbean professionals.
- **Constraint:** Feeds must be config-driven (charter rule: no business values in code). Add them to the `feeds:` list in `config/sources.yaml`.
- **Priority:** P1 — idea diversity is improved but will stagnate without fresh source material entering the bank.
- **Note:** The source_snapshot job (systemd/cron) ingests these feeds and writes items to the `sources` table as `source_type='rss_item'` with `status='new'`. The operator reviews them at `/sources` (Keep → active, Remove → killed).

### 3. DESIGN: Ending card templates for cinematic style
- **Problem:** The episode format (`modules/stackpenni/episode-format-parable.md`) references `title_card_v1` and `quote_card_v1` card styles, but no visual templates exist for these. They need to be designed as actual visual assets (PNG/SVG) that the renderer overlays on the final frame.
- **Context:** Operator chose cinematic painted realism (2026-07-25). Ending cards should match: warm golden-hour tones, StackPenni palette (teal, coral, gold, cream), Montserrat Bold + Anton fonts (per render_styles.yaml).
- **What's needed:**
  - `title_card_v1` — episode title at the open, lesson at the close. Brand name "StackPenni" + handle.
  - `quote_card_v1` — key line from VO quoted on screen for emphasis.
  - Both as PIL-rendered overlay templates (not baked into images) — consistent with the existing renderer overlay system.
  - Card style refs should be registered in the reference_assets system (T11.3) as approved assets.
- **Priority:** P2 — enhances finished quality but doesn't block the pipeline.
- **Operator input needed:** What text should appear on the ending card? Brand name? Handle? CTA ("Follow for more")? Logo?

### 4. FIX: Kill reason text not captured in feedback_log
- **Problem:** 18 entries in `feedback_log` with `feedback_type='kill_reason'` but `feedback_text` is empty. When the operator kills an idea card at Gate 1, the kill reason is stored on the card (`kill_reason` column) but not written to the feedback log with text.
- **Investigation needed:** Trace the Gate 1 kill path in `src/app.py` (`ideas_gate_decision` route) → find where `store.add_feedback()` is called for kill reasons → check if the kill reason text is being passed or if it's empty.
- **Priority:** P2 — the feedback loop can't learn from kills if the text isn't captured.
- **Fix:** Ensure `feedback_text` is populated with the operator's kill reason when a card is killed at Gate 1.

### 5. OPS: Test approve → publish end-to-end
- **Context:** 10 assets are now at Gate 3 (rendered). The publish path (Gate 4) is wired: `/create/publish/<draft_id>` + `/api/assets/<id>/schedule` → Buffer adapter. But nothing has ever been published through the system.
- **What's needed:** Operator approves an asset at Gate 3 → asset_state transitions to "approved" → operator goes to Gate 4 → schedules to Buffer → verify Buffer receives the post → verify `publish_log` table gets an entry.
- **Blocker:** Buffer API credentials must be configured in `config/models.yaml` (`buffer:` block with channel IDs and access token). Verify these are set before testing.
- **Priority:** P1 — this is the first end-to-end publish test and will validate (or surface bugs in) the entire posting path.

## Related files
- `src/services/render_review.py` — render service (item 1)
- `config/sources.yaml` — RSS feeds config (item 2)
- `modules/stackpenni/episode-format-parable.md` — card style refs (item 3)
- `src/app.py` — Gate 1 kill path + Gate 4 publish path (items 4, 5)
- `src/buffer_adapter.py` — Buffer posting adapter (item 5)
- `config/models.yaml` — Buffer credentials (item 5)