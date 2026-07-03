# UI-REVIEW-002 — Deep Walk-Through Findings (2026-07-03)

**Filed by:** Hermes (builder)
**Trigger:** Operator asked for a deep human UI inspection after CORRECTION-module-context-assembly + CORRECTION-feedback-plumbing were implemented. Operator explicitly said "don't just check for the obvious — even slight confusion or grievances should be noted."
**Status:** 15 findings. Builder is fixing all in this session. This note is for the architect's record.

---

## Findings from this batch (introduced by the corrections):

### 1. CRITICAL: Shipped draft page has no locked state
The draft page shows ALL controls active even when `draft_state = 'shipped'`: Edit draft, Regenerate, Kill, Revise, Ship forward, Apply/Dismiss audit flags, feedback chips. An operator can:
- Kill a shipped draft that already has assets — no indicator of downstream impact
- Regenerate and overwrite draft_text — assets become silently stale
- Click "Ship forward" again — no feedback on what happens
- Apply audit flags — edits shipped text, assets stale with no warning

**Ruling needed:** Should the page lock editing controls when shipped? The F1 correction says "Gate rule unchanged: editing does not change draft_state" — but the UI doesn't prevent destructive actions on shipped drafts. Recommendation: disable Edit/Regenerate/Kill/Revise/audit-apply/feedback when shipped; show only "Proceed to Assets" and a "Reopen for revision" action that explicitly transitions back.

### 2. CRITICAL: Asset staleness — editing shipped draft makes assets silently stale
After editing draft #5 (v1→v3), the assets page still shows v1 text. No staleness indicator, no "assets out of sync" warning, no "re-fan-out" button. The operator would think assets reflect the current draft.

**Ruling needed:** Should editing a shipped draft mark its assets as stale? Should the assets page show a "draft was edited after fan-out — re-generate?" banner?

### 3. Series children not grouped under parent on Ideas page
F3 correction says "group children under their parent visually." I added a badge but cards are scattered randomly. The operator sees Part 4/4 next to an unrelated idea.

**Builder fix:** Sort cards so children appear immediately after their parent, with visual indentation.

### 4. Old series children have identical idea text
6 existing children (from pre-F3 clone behavior) all have the exact same idea text as parent + "(Part X/4)". The All view is a wall of duplicates. F3 fixes this for new series only.

**Ruling needed:** Should legacy children be cleaned up? Or left as historical data?

---

## Pre-existing findings (not from this batch, but operator-flagged):

### 5. Technical jargon in UI: "pillar_with_derivatives", "series_of_n"
Scope types shown as raw technical strings. Operator doesn't know what these mean.
**Builder fix:** Config-driven human-readable mapping.

### 6. Create page: "Draft #9 — shipped" — no descriptive titles
Can't tell what any draft is about without clicking in.
**Builder fix:** Show idea text snippet in draft list.

### 7. Create page: "Shipped" section duplicates the drafts list
All 9 drafts appear in both columns. Redundant.
**Builder fix:** Show only in-progress drafts in "Drafts" column; shipped ones in "Shipped" column only.

### 8. Dashboard: Recent Activity is a raw event log, not grouped by idea
Same idea appears 6+ times. Asset entries ("Instagram carousel") lack parent context.
**Builder fix:** Group by idea, show relative timestamps.

### 9. Draft page: version indicator is nearly invisible
`.draft-version` has `font-size: 0.75rem; color: #666` — tiny grey text.
**Builder fix:** Make it a visible badge.

### 10. Empty draft state: "Generate draft" button in bottom-left, far from instruction text
Disjointed visual flow on an empty page.
**Builder fix:** Center the button under the instruction text.

### 11. Published page: "Scheduled" label is a false green when Postiz not configured
**Builder fix:** Show "Draft schedule (Postiz not connected)" instead of "Scheduled".

### 12. Metrics page: "Pull metrics now" button active below "Postiz not available" warning
**Builder fix:** Disable button when Postiz not configured.

### 13. Library page: modules shown as raw markdown, truncated mid-sentence
No rendering, no "show more" expansion. "Edit" button bypasses the gate.
**Builder fix:** Add "Show more" toggle, render basic markdown formatting.

### 14. Fan-out prompt: LLM adds emojis and excessive hashtags not in the source draft
The Instagram variant got 🇹🇹🇯🇲🇧🇧💪🤖💸 and 13 hashtags. The original draft had none. The prompt says "do NOT add new content the human didn't approve" but the LLM ignores this.
**Builder fix:** Strengthen the fan-out prompt with an explicit "Do NOT add emojis or hashtags that were not in the source draft" rule.

### 15. Raw ISO timestamps throughout the UI
"2026-07-03T18:13" — not human-readable.
**Builder fix:** Format as relative time or "Jul 3, 6:13 PM".