# CORRECTION-jargon-timestamps-cleanup-v1.0

**Architect:** Hermes (vf-architect profile)
**Date:** 2026-07-04
**Priority:** P1 (operator-facing quality)
**Status:** Ready for builder

---

## P1-1: Technical jargon leaking into operator UI (Dimension 3)

### Problem

Developer-facing state strings appear directly in the operator UI on several pages:

1. **Assembler page** (`/assemble`) — filter button shows raw `assembling` as label text
2. **Writer page** (`/create`) — `asset_ready` state text leaks through in some card display paths
3. **Ideas page** (`/ideas`) — has an `awaiting` tab label that references the deprecated `awaiting_capture` state

### Fix

Every state string that reaches operator-visible HTML must pass through a human-label mapping. The create.html template already has this pattern (a Jinja dictionary mapping `display_state` → human label). Apply the same pattern to:

- `src/templates/assemble.html` — map `assembling` → "Assembling", `asset_ready` → "Ready for review"
- `src/templates/ideas.html` — remove the `awaiting` tab entirely (awaiting-capture is non-blocking per AMENDMENT-006). If any card is in `awaiting_capture` state in the DB, it should display under the `approved` tab with a "capture needed" flag, not in a separate tab.

### Acceptance criteria

- [ ] No raw state string (`asset_ready`, `assembling`, `writer_failed`, `assembly_failed`, `draft_ready`, `production_failed`, `awaiting_capture`) appears as visible text on any operator-facing page
- [ ] Assembler page filter buttons show human labels: "Assembling" (not `assembling`), "Ready for review" (not `asset_ready`)
- [ ] Ideas page has no `awaiting` tab
- [ ] Grep for `asset_ready\|assembling\|writer_failed\|assembly_failed\|production_failed` in `src/templates/*.html` returns only inside CSS class names or JS data attributes, never as visible text

---

## P1-2: Timestamps missing on pipeline pages (Dimension 6)

### Problem

The Ideas page, Writer page, and Assembler page show **zero timestamps**. The operator cannot tell how stale a card is. The charter's async-gate philosophy requires "staleness is always visible." The CSS has `.timestamp` and `.time-ago` classes defined but they're unused on pipeline pages.

### Fix

Add relative timestamps to every card on:

1. **Ideas page** (`/ideas`) — each idea card shows created time as relative ("2 hours ago", "3 days ago")
2. **Writer page** (`/create`) — each pipeline card shows last state change time as relative
3. **Assembler page** (`/assemble`) — each card shows last state change time as relative

### Implementation

The `idea_cards` table has a `created_at` column. The `drafts` table has timestamps. Use a Jinja filter or template helper to format as relative time. Python side:

```python
def relative_time(iso_string):
    """Convert ISO timestamp to relative time string."""
    if not iso_string:
        return ""
    # parse, compute delta, return "N hours ago" / "N days ago" / "just now"
```

Register as a Jinja filter in `create_app()` alongside the existing `from_json` filter.

### Acceptance criteria

- [ ] Every card on `/ideas`, `/create`, `/assemble` shows a relative timestamp (e.g., "2 hours ago", "3 days ago")
- [ ] No raw ISO timestamp (e.g., `2026-07-04T15:43:12Z`) is visible to the operator
- [ ] The `time-ago` CSS class is used for the display
- [ ] Timestamp is present on cards in all states (new, approved, writing, draft_ready, shipped, etc.)

---

## P2-1: Hardcoded platform fallback in produce_chain.py (Charter grey zone)

### Problem

`src/produce_chain.py:393`:
```python
return ["X", "Instagram"]  # fallback
```

This is a hardcoded business-specific fallback. If the Format Guide entry is missing, the code falls back to hardcoded platform names that only exist for StackPenni. A second business with different platforms would get StackPenni's platforms.

### Fix

Fall back to the business config's platform list (`config.business.platforms`), not hardcoded names:

```python
# Instead of: return ["X", "Instagram"]
# Use: return [p["name"] for p in business.get("platforms", [])]
```

The `business` config is already loaded in `_step_fanout` — pass it to `_resolve_format_platforms` or load it inside the helper.

### Acceptance criteria

- [ ] `_resolve_format_platforms` fallback returns platform names from `config/business.yaml`, not hardcoded `["X", "Instagram"]`
- [ ] Same fix applied in both `src/produce_chain.py` and `src/app.py` (if the same pattern exists there)
- [ ] Test: a business config with platforms `["TikTok", "YouTube"]` gets those as fallback, not X/Instagram

---

## P2-2: Dead awaiting-capture code (Zombie state cleanup)

### Problem

AMENDMENT-006 makes awaiting-capture non-blocking. But the code still has the full awaiting-capture machinery:

- `src/templates/ideas.html:233` — `{% if card.card_state == 'awaiting_capture' %}` block with "Manage capture" button
- `src/app.py:3917` — `"awaiting": ["awaiting_capture"]` in state_map
- `src/app.py:4033` — `"awaiting_capture": counts.get("awaiting_capture", 0)`
- `src/app.py:4658` — capture upload route with awaiting-capture docstring
- `src/pipeline.py:16,52` — state in schema comment and default
- `src/templates/capture.html` — entire capture page

### Fix

Per AMENDMENT-006, awaiting-capture is deprecated as a blocking state. Capture tasks are a non-blocking flag. The code should:

1. **Remove the awaiting tab** from ideas.html (done in P1-1)
2. **Keep the capture.html page** — it's still useful for uploading capture material, but it should not be gated on `awaiting_capture` state. Any approved card with capture tasks can link to it.
3. **Remove `awaiting_capture` from the state_map** in app.py — cards with capture tasks go to `approved` state, not `awaiting_capture`
4. **Keep the capture upload route** — it still works, just not gated on state
5. **Add a comment in pipeline.py** noting that `awaiting_capture` is deprecated per AMENDMENT-006

### Acceptance criteria

- [ ] No card enters `awaiting_capture` state (Gate 1 approve always goes to `approved` → Writer chain)
- [ ] The `awaiting` tab is removed from ideas.html
- [ ] `awaiting_capture` removed from `state_map` in app.py
- [ ] Capture tasks still display on cards (as a flag, not a blocking state)
- [ ] Capture upload route still works (reachable from card's capture task display)
- [ ] `capture.html` template still exists and works

---

## P2-3: Dead Postiz code (per DIVERGENCE-008)

### Problem

`src/postiz_adapter.py` exists but nothing imports it. The system uses Buffer (`src/buffer_adapter.py`). Dead code that contradicts the live system is a defect.

### Fix

1. Delete `src/postiz_adapter.py`
2. Remove any Postiz references from `config/models.yaml` (if a `postiz:` block exists)
3. Update `src/app.py` — any remaining `postiz` string references (e.g., `postiz_post_id` field names in DB) can stay for backward compatibility with existing publish_log rows, but add a comment noting they store Buffer post IDs now
4. Update CONTEXT.md — all "Postiz" → "Buffer"

### Acceptance criteria

- [ ] `src/postiz_adapter.py` deleted
- [ ] No `postiz:` config block in `config/models.yaml`
- [ ] No code imports `PostizAdapter` or `postiz_adapter`
- [ ] CONTEXT.md references Buffer, not Postiz
- [ ] `postiz_post_id` column name in publish_log can stay (backward compat) with a comment

---

## Implementation order

1. P1-1 (jargon) + P1-2 (timestamps) — operator-facing, do first
2. P2-1 (platform fallback) — charter compliance, small fix
3. P2-2 (awaiting-capture cleanup) — follows from AMENDMENT-006
4. P2-3 (Postiz cleanup) — follows from DIVERGENCE-008

Each item lands with tests. Suite stays green. CHANGELOG entry per item.