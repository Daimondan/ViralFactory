# CORRECTION: Feedback Plumbing & Pipeline Fixes — Direct Edits, Revise Loop, Series Spawn

**Version:** 1.0
**Status:** Approved by operator — ready for implementation
**Supersedes:** Nothing. Complements CORRECTION-module-context-assembly-v1.0 (coordinate the draft prompt version bump — see §2.4).
**Priority:** F1 and F2 are P1 — they break the co-production loop's core promise (the human's highest-weight signal is captured and then ignored). F3 is P2. F4 and F5 are P3 cleanups.

---

## F1 (P1): Direct edits are a dead end — make draft_text the authoritative, editable artifact

### Current behavior
`POST /api/draft/<id>/feedback` with `feedback_type=direct_edit` stores the text in the `human_edits` JSON column via `save_human_edits()`. **Nothing ever reads that column again.** Fan-out consumes `draft["draft_text"]` untouched; regeneration overwrites `draft_text` wholesale. The schema comment calls direct edits "authoritative text" — currently false.

Compounding this, the UI (`draft.html` `sendDirectEdit()`) submits freeform text from the shared feedback textarea with no line reference, so there is nothing mechanical to merge even if downstream did read `human_edits`. Meanwhile `update_audit_flag(action='apply')` already edits `draft_text` in place correctly — proof of the right pattern.

### Ruling
"Direct edit" means editing the draft. The operator edits the draft body itself; the edited text **becomes** `draft_text`. Downstream (fan-out, assets, assembly) is then automatically correct with zero further changes, because it already reads `draft_text`.

### Implementation
1. **UI (`draft.html`):** render the draft body in an editable state (an "Edit draft" toggle switching the display block to a textarea pre-filled with current `draft_text`, with Save / Cancel). Keep the existing chip/text feedback controls as they are. Remove the freeform "direct edit" button — it is replaced by real editing.
2. **New endpoint** `POST /api/draft/<int:draft_id>/edit-text` accepting `{draft_text: str}`:
   - Reject if empty or identical to current text.
   - Save the new text (do **not** route through `save_draft_content` — that resets state to `draft_ready` and would clobber `visual_direction`/flags; write `draft_text` + `updated_at` only, via a new store method `save_edited_text(draft_id, text)`).
   - Bump `draft_version`.
   - Log a `feedback_log` entry: `feedback_type='direct_edit'`, weight 3, `feedback_text` = a compact unified diff of old→new (use `difflib.unified_diff`, cap at 4000 chars). The diff, not the full text, is the voice signal the learning loop wants.
   - Invalidate any existing self-audit flags whose `line` no longer appears in the new text (mark `status='stale'`; `update_audit_flag` already guards on line presence).
3. **Deprecate the `human_edits` write path:** `feedback_type=direct_edit` via the old `/feedback` endpoint returns 400 with a message pointing to `/edit-text`. Leave the column in place (historical rows; no migration).
4. **Gate rule unchanged:** editing does not change `draft_state`. Ship/kill/revise remain the only state transitions.

### Acceptance
- Edit → fan-out: platform variants are generated from the edited text (test asserts the edited sentinel string appears in the fan-out prompt variables).
- Edit logs a weight-3 `direct_edit` diff entry and bumps version.
- Old direct_edit path returns 400.

---

## F2 (P1): Revise is a blind re-roll — feed accumulated feedback and the previous draft into regeneration

### Current behavior
`POST /api/draft/<id>/gate {action: revise}` only calls `increment_draft_version()` (version +1, state `revised`). The operator then re-runs `/api/draft/<card_id>/generate`, whose prompt variables contain **no feedback and no previous draft** — identical inputs, new dice roll. The `feedback_log` (chips weight 1, text weight 2, direct-edit diffs weight 3, kill reasons) is consumed only by the nightly learning cron.

### Ruling
Regeneration of an existing draft is a *revision*, not a fresh draft. The prompt must receive (a) the previous draft text and (b) the accumulated feedback for this draft, weight-ordered, so the model preserves what wasn't criticized and fixes what was.

### Implementation
1. **`draft_generate` route:** when an existing draft is found for the card (the `existing` branch), assemble two additional variables:
   - `previous_draft`: current `draft_text` (cap 6000 chars, truncate at paragraph boundary with marker — reuse the helper from CORRECTION-module-context-assembly).
   - `revision_feedback`: all `feedback_log` entries for this draft via `list_feedback(business_slug, draft_id)`, rendered newest-last, weight-tagged, e.g. `[direct_edit w3] <diff>` / `[text w2] ...` / `[chip w1] ...`. Cap 3000 chars, keep the highest-weight entries when trimming.
   - When no existing draft: both variables are the literal string `(first draft — no previous version)`.
2. **Prompt (`prompts/draft/generate_v2.md` → v2.2):** add a conditional-by-content block:

   > ## Previous draft (if revising)
   > {previous_draft}
   >
   > ## Operator feedback on the previous draft (weight 3 = authoritative edits; treat as law)
   > {revision_feedback}
   >
   > If a previous draft exists: this is a REVISION. Preserve everything the feedback did not criticize — same hook unless criticized, same structure unless criticized. Apply weight-3 edits exactly. Do not re-imagine the piece.

   Version note: CORRECTION-module-context-assembly bumps this file to v2.1 (wording). If both corrections are implemented in one batch, land a single v2.2 containing both changes; update `views.yaml` key accordingly.
3. **Direct-edit interaction (F1):** because F1 makes edits live in `draft_text`, the previous draft passed here already contains them; the diffs in `revision_feedback` additionally tell the model *which* lines are human-authored and must survive verbatim.
4. **No new endpoint.** The revise gate action stays as-is; the intelligence moves into the existing generate path.

### Acceptance
- Regenerating a draft that has feedback: prompt variables contain the previous text and the weight-tagged feedback (assert sentinel strings).
- First-time generation: both variables carry the `(first draft ...)` marker.
- Feedback trimming keeps weight-3 entries when over budget.

---

## F3 (P2): Series children spawn as identical clones — differentiate parts, keep the gate honest

### Current behavior
On approval of a `series_of_n` card, `ideas_gate_decision` spawns n−1 children with the **same idea text** plus "(Part i/n)", the **same hooks**, same treatment — and force-sets them to `approved`. The drafter will receive the identical card n times, and n−1 pieces of AI-developed content advance past Gate 1 without the operator ever seeing their actual per-part content.

### Ruling
Differentiation happens at spawn via one LLM call producing a per-part breakdown; children enter state **`new`**, not `approved` — "AI proposes, humans gate everything" applies to parts as much as to cards. To keep gate friction proportionate, the ideas page gets a bulk affordance for a series group. Gate intensity is brutal at Ideas by design; a series that can't survive n quick looks shouldn't ship n pieces.

### Implementation
1. **New prompt** `prompts/ideas/series_breakdown_v1.md`: input = parent idea, hooks, treatment, n, cadence, plus the same module context as idea generation (via the view map — add an entry mirroring `ideas/generate_v1.md`). Output schema: `{parts: [{part_number, idea, hook_options[2..3], capture_required[]}]}` for parts 2..n (part 1 is the parent). Each part must stand alone but declare its place in the arc.
2. **Gate route:** replace the clone loop with the breakdown call. Children are created with the part-specific idea/hooks, parent treatment (capture_required overridden per part if the breakdown supplies it), `parent_id` set, state `new`. On LLM failure, fall back to the current clone behavior but in state `new` with a warning in the response — never block the parent's approval on the breakdown call.
3. **Ideas page:** group children under their parent visually (parent_id already exists); add "Approve remaining parts" on the group, which POSTs the existing gate endpoint per child.

### Acceptance
- Approving a series_of_3 parent yields 2 children in state `new` with ideas that differ from the parent and from each other.
- Breakdown failure still yields children (clones, state `new`) and a surfaced warning.
- Bulk approve transitions all `new` children of a parent.

---

## F4 (P3): Draft-visual synthetic asset ID (`draft_id + 100000`) — replace the magic number

### Current behavior
Draft-stage visual previews are stored in `asset_media` under `asset_id = draft_id + 100000` (both in `draft_generate_visuals` and the draft page loader). Breaks silently when real asset IDs cross 100000; unreadable in the raw table.

### Implementation
1. `ALTER TABLE asset_media ADD COLUMN owner_type TEXT NOT NULL DEFAULT 'asset'` (media_adapter's `_init_tables` runs the migration idempotently; check column existence via `PRAGMA table_info`).
2. `MediaAdapter.generate_image`, `_record_media`, `list_asset_media` gain an `owner_type: str = "asset"` parameter; queries filter on `(owner_type, asset_id)`.
3. One-time data migration in the same init: rows with `asset_id >= 100000` → `owner_type='draft'`, `asset_id = asset_id - 100000`.
4. Update the two call sites in `app.py` to pass `owner_type="draft"` with the plain `draft_id`; delete the synthetic-ID comments.

### Acceptance
- New draft visuals recorded with `owner_type='draft'` and the real draft_id; asset media unaffected; migrated legacy rows readable on the draft page.

---

## F5 (P3): Edit-plan inventory uses fictional durations — probe real ones

### Current behavior
`generate_edit_plan` hardcodes durations: generated video 5.0s, uploads 10.0s (comments admit "real duration via ffprobe"). The LLM plans trims against numbers that are wrong, producing edit plans that fail or mis-trim at render.

### Implementation
- `AssemblyRenderer._get_duration` (ffprobe) already exists. Expose it as a module-level `probe_duration(path) -> Optional[float]` in `assembly.py` and call it in the inventory loop for generated **videos** and uploaded **video/audio** materials (skip images — their 3.0s is a plan intent, not a file property). On probe failure, keep the current defaults and append `(duration unverified)` to the ingredient description so the LLM knows.
- Cache probe results in-process per request only; no schema change.

### Acceptance
- Inventory lines for real video files carry probed durations; a corrupt/missing file falls back with the unverified marker instead of raising.

---

## Explicitly deferred (recorded, not built)
- Crossfade/slide/whip transitions and caption burn-in in `AssemblyRenderer` — declared v1 scope limits in the code; roadmap items, not corrections.
- Bulk-gate affordances beyond the series group (F3.3).

## Suggested implementation order
F1 → F2 (F2's diff-awareness depends on F1's diff logging) → F5 → F4 → F3. F3 last because it adds a prompt and a view-map entry and is the only one touching Gate 1 semantics.
