# PROCESS: Definition of Done for Hermes

**File:** PROCESS-definition-of-done-v1.0.md
**Date:** 2026-07-03
**Status:** Operator ruling. Binding on all Hermes work from this date. To be referenced from CONTEXT.md.
**Last Updated:** 2026-07-04 — added visual verification rule, CSS validation, lightbox check, and the full lesson log (Appendix A)

---

## The rule

Hermes does not report work as done until Hermes has fully tested it — and "fully tested" includes a hands-on human-style UI test, not only the automated suite. The operator's first end-to-end run surfaced roughly a dozen defects that a passing test suite did not catch: a literal `{corpus}` placeholder reaching the LLM, raw Python dicts rendered to the operator, conversation history lost on reload, silent upload failures. Every one of these is invisible to unit tests and obvious within two minutes of actually using the product. The operator's time is the most expensive test harness in the system; it is reserved for judgment calls, not for discovering that a button doesn't work.

## What "done" requires, in order

1. **Automated suite passes.** All existing tests plus new tests covering the change. A change that cannot be covered by at least one automated test should say so explicitly and why.

2. **Human UI test.** Hermes opens the actual UI in a browser and exercises the changed surface as an operator would:
   - Navigate to it the way the operator would (from the console, not by pasting a deep URL).
   - Click every button and control on the changed surface; confirm each does what its label says.
   - If the change touches auth or entry flow: perform the login flow end to end, including the failure path (wrong credentials behave sanely).
   - If the change touches upload: upload a real file and watch the full lifecycle — indicator appears during upload, success state on completion, and force one failure (e.g., oversized or unsupported file) to confirm the error is visible and honest.
   - Read every operator-visible string produced by the change: no machine-facing copy, no raw data structures, no clipped or overflowing text at both desktop and narrow widths.
   - Reload the page mid-flow and confirm state survives.
   - **VISUAL VERIFICATION:** Take a screenshot of the changed surface and look at it. Check for broken layout, disproportionate elements, text overflow, missing images, and CSS that didn't apply. `curl | grep` is not a visual test — it confirms HTML contains strings, not that the page looks right. Use the browser vision tool.

3. **End-to-end pass when the change touches a flow.** If the change is part of onboarding, run onboarding start to finish with realistic inputs (real files, multi-paragraph answers), not minimal stubs. Thin inputs hide input-plumbing bugs — that is precisely how the drafting-starvation defect survived.

4. **Report format.** The done report states what was tested and how: which automated tests, which UI paths were manually walked, what inputs were used, and anything observed but out of scope (fileed as a note, not silently ignored). "Tests pass" alone is not a done report.

## Boundary

This does not change the gate structure: Hermes testing its own work is a precondition for reporting done, not a substitute for the operator's review. The operator still gates. The point is that when the operator sits down to review, the trivial breakage layer has already been burned away.

---

## Appendix A: Lesson Log

Each time the operator catches a defect that Hermes' "testing" should have caught, the lesson is added here. This list grows. It is the accumulated wisdom of things curl-based testing missed.

### L1: Template edit kills all page JS (duplicate `const` declaration)
**Bug:** Adding a second `const playbookName` declaration in session.html caused a `SyntaxError: Identifier 'playbookName' has already been declared` — the browser refused to execute the entire `<script>` block. All interactive JS (attach, send, gate buttons) was dead.
**Root cause:** Template edit appended a gate-actions block that re-declared a variable already declared earlier in the same scope.
**Fix:** Removed the duplicate. Added `test_template_js_parse.py` — extracts `<script>` blocks, renders Jinja placeholders, runs `node --check` to validate JS syntax.
**Lesson:** Any time you edit a template's `<script>` block, the JS parse test is your safety net. But the real lesson is: open the page in a browser and click a button.

### L2: Truncated CSS rule silently swallows the next rule (`.post-met` eats `.post-image`)
**Bug:** assets.html had a truncated CSS rule `.post-met` (incomplete `.post-meta`) with no opening brace. The browser parsed `.post-met\n.post-image { width: 60px; ... }` as a single descendant selector `.post-met .post-image`, which never matched any element. The 60×60px image thumbnail sizing rule was silently swallowed. Images rendered at their natural size (1376×768px), blowing out the card layout. Text was squeezed into a narrow strip. The page looked broken to the operator.
**Root cause:** A template edit left a CSS property name truncated (`.post-met` instead of `.post-meta { ... }`). The CSS parser treated it as a selector with no body, merging it with the next rule.
**Fix:** Completed the `.post-meta` rule properly. Added `test_template_css_validate.py` — extracts `<style>` blocks from all templates, checks every selector has a `{ ... }` body. The test immediately found 3 more truncated rules in `onboarding_session.html` (`.draft-notice` ×2, `.input-area textare`) that were also silently broken.
**Lesson:** CSS truncation is invisible to curl (the HTML has all the right class names) and invisible to unit tests. Only a browser rendering the page catches it. The automated CSS validation test is the safety net, but the real test is looking at the page.

### L3: `curl | grep` is not a UI test
**Bug:** During the architect corrections session, Hermes "verified" pages by curling them and grepping for expected strings (`time-ago`, `st-new`, `bulkUpdateSources`). All checks passed. But the assets page had images rendering at 1376px because a CSS rule was broken (L2). The curl confirmed the HTML contained the right class names — it did not confirm the page looked right.
**Root cause:** Confusing "the HTML contains the right strings" with "the page renders correctly."
**Fix:** The DoD now explicitly requires visual verification — take a screenshot and look at it. Use the browser vision tool, not curl.
**Lesson:** `curl | grep` confirms the server returns the right HTML. It does not confirm the browser renders it correctly. A CSS rule can be broken, a JS event handler can be dead, a layout can be shattered — and curl will report 200 OK with the right strings. The only valid UI test is opening the page in a browser and looking at it.

### L4: Operator reviews every screen as a human user, not a developer
**Bug:** Across multiple review sessions, the operator found issues that a developer wouldn't flag: state dissonance (controls active when they should be locked), staleness (downstream artifacts stale after upstream edit), technical jargon in operator UI, descriptive titles ("Draft #9" is useless), grouping (series children scattered), timestamps (raw ISO not human-readable), content drift (fan-out adding unapproved emojis), empty states (next action unclear), version visibility (badge too small), false greens (Scheduled label when API not configured).
**Root cause:** Developer testing checks "does it work?" — operator testing checks "does it make sense?"
**Fix:** The 10-dimension UI review checklist (see Appendix B).
**Lesson:** Test as a user, not a developer. Click through the flow as if you don't know the code. Ask: "Would I understand what to do next?" "Does this label tell me what I need to know?" "Is anything confusing or misleading?"

### L5: Lightbox / fullscreen image viewing must be verified
**Bug:** Operator reported "no way to expand it to review each image in more detail" on the assets page. The lightbox code existed in the template (the `openLightbox()` JS function was present, images had `onclick` handlers), but the thumbnails were so large (1376px due to L2) that the concept of "clicking to expand" wasn't discoverable — the images were already at full size.
**Root cause:** The lightbox existed but was invisible as a feature because the thumbnails weren't thumbnails — they were full-size images.
**Fix:** Fixed the CSS (L2) so thumbnails are 120px. The lightbox now works as intended — click a 120px thumbnail → fullscreen image.
**Lesson:** A feature existing in code is not the same as a feature being usable. Verify the full interaction: click the thumbnail, see the lightbox open, see the full image, close it. Don't assume "the function is there so it works."

---

## Appendix B: 10-Dimension UI Review Checklist

When doing a UI walk-through, check each of these dimensions on every changed surface:

1. **State dissonance** — are controls locked when they should be? A shipped draft should NOT have active Edit/Kill/Regenerate buttons.
2. **Staleness** — are downstream artifacts stale after an upstream edit? If the draft was edited, are the assets marked as stale?
3. **Technical jargon** — does any developer-facing string leak into the operator UI? (`asset_ready`, `assembling`, `awaiting_capture` should not be visible text.)
4. **Descriptive titles** — "Draft #9 — shipped" is useless. The title should tell the operator what the content is about.
5. **Grouping** — are series children grouped under their parent, or scattered?
6. **Timestamps** — are timestamps human-readable ("2 hours ago") or raw ISO ("2026-07-04T15:43:12Z")?
7. **Content drift** — did fan-out add unapproved emojis/hashtags not in the source draft?
8. **Empty states** — when there's nothing here yet, is the next action clear? ("No cards yet. Generate ideas →")
9. **Version visibility** — is the version/state shown as a visible badge, not tiny grey text?
10. **False greens** — does a "Scheduled" badge appear when the publishing API isn't configured? Does a "ready" state hide a real problem?

---

*This document grows every time the operator catches something the testing should have caught. Each lesson is a permanent addition — not a note to self, a binding requirement.*