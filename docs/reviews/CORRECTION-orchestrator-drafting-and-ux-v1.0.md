# CORRECTION: Orchestrator Drafting Starvation & Onboarding UX

**File:** CORRECTION-orchestrator-drafting-and-ux-v1.0.md
**Date:** 2026-07-03
**Repo state reviewed:** commit `372f81e`
**Supersedes:** Nothing. Extends CORRECTION-onboarding-single-thread-v1.0.md with defects found in the operator's first hands-on end-to-end run.
**Status:** Approved by operator for implementation.

---

## Context

The operator ran the single-thread onboarding end to end with a rich material set (docx, audio, style references). Every generated living document came back thin or empty: Voice Profile said "Corpus was not provided in the prompt," Sources Engine returned bare headers, Visual Style ignored the uploaded references, Viral Patterns was empty. Additional failures: raw Python dicts rendered in readbacks, dead air after gate approval, no conversation restore on page reload, no upload progress indicator, a hard validation crash (`next_focus` NoneType), and slow conversational turns.

All of the "thin output" symptoms share one root cause. Fix that first — everything downstream of it is unmeasurable until the drafting calls actually receive input.

---

## P0-1: Drafting calls receive almost no input (root cause of all thin documents)

### Diagnosis

Three compounding faults in `src/app.py`:

1. **`routed_seeds` is discarded.** The orchestrator schema (line ~640) requires `routed_seeds` — the per-doc seed extraction that is the orchestrator's core function. `onboarding_message` never reads `result["routed_seeds"]`. The only two occurrences of the string `routed_seeds` in the entire codebase are the schema definition itself. The orchestrator does its job every turn and the application throws the work away.

2. **`_draft_onboarding_doc` fills prompt variables from keys the orchestrator never writes.** The variable map (`seed_sources`, `anti_examples`, `admired_examples`, `brand_assets`, `visual_examples`, `operator_stories`, `voice_summary`, `audience_data`, `format_observations`, etc.) reads from `collected` keys that only the legacy eight-card flow populated. In the single-thread flow every one of them resolves to "(none provided)" or equivalent. `shot_library_summary` is hardcoded to the literal string `"(see uploaded files)"` — the LLM cannot see uploaded files; this tells it nothing.

3. **Materials content never reaches drafting.** `_build_materials_summary` (capped at 6,000 chars) is passed only to the conversational orchestrator turn. No drafting call receives any material content. Voice Profile's prompt requires `{corpus}`; `_draft_onboarding_doc` never sets a `corpus` variable, and `_render_prompt` leaves unknown placeholders as-is — so the model literally received the text `{corpus}` and correctly reported that no corpus was provided. Additionally, of the eight analyze prompts only `business_profile/analyze_v1.md` accepts `{qa_transcript}` — the conversation itself doesn't reach the other seven drafts either.

### Fix

**(a) Persist routed seeds.** In `onboarding_message`, after the orchestrator call, append each routed seed to `collected["seeds"][doc_name]` (a list per doc). This becomes the primary input store for drafting.

**(b) Build a per-doc drafting package.** Replace the per-playbook variable scavenging in `_draft_onboarding_doc` with a uniform input package assembled at draft time:

- All routed seeds for that doc (from `collected["seeds"][doc]`), verbatim.
- The full conversation transcript (existing `business_qa` build), most recent turns prioritized if truncation is needed.
- **Materials content relevant to the doc** — full `raw_content` of each uploaded material, with a per-draft budget of ~24,000 chars (drafting is a one-shot analysis call, not a conversational turn; it can and should carry far more context than the 6,000-char conversational summary). Truncate per-material proportionally if over budget, longest materials first.

**(c) Update the eight analyze prompts (bump each to v2)** to accept the package. Each prompt gains three variables: `{routed_seeds}`, `{conversation_transcript}`, `{materials_content}`. Keep the existing specific variables where the orchestrator can populate them, but the prompts must instruct the model to mine seeds, transcript, and materials as primary sources. For Voice Profile specifically, `{corpus}` is built from: all materials whose type is text-bearing (docx/pdf/txt/whatsapp extractions) plus the operator's own conversational messages — that IS the corpus in the single-thread flow. Audio remains excluded until the transcription hosting decision lands (known blocker, unchanged).

**(d) Kill the `"(see uploaded files)"` literal.** Visual Style's `shot_library_summary` gets the actual materials listing (filenames, types, and extracted content for image-adjacent text materials), or "(no shot library uploaded)" honestly.

**(e) Regression test:** a test that runs `_draft_onboarding_doc` for each of the eight docs against a `collected` blob populated only via the orchestrator path (seeds + session messages + materials), and asserts the rendered prompt contains (i) no unresolved `{placeholder}` tokens and (ii) the material content string. The unresolved-placeholder assertion should be generalized: **no rendered prompt anywhere in the system may ship with an unresolved placeholder** — add a check in `_render_prompt` that logs a warning to provenance when a `{token}` survives rendering.

---

## P0-2: Validation crash on `next_focus` null

### Diagnosis

Schema requires `next_focus` as string. When the orchestrator judges the conversation complete (or has no single next doc), the model returns `null`. Validation fails; retry re-sends with a generic "respond with valid JSON only" note that doesn't say what was wrong; second failure surfaces a raw error to the operator.

### Fix

1. Remove `next_focus` from `required`; before validation, coerce `None` → `""` for any optional string field.
2. Improve the retry: include the actual validation error text in the retry prompt ("Your previous response failed validation: Field 'next_focus' must be string, got NoneType. Correct this and respond with valid JSON only."). This is a one-line change in the adapter's retry path and materially raises retry success rates for schema (not just JSON-parse) failures.
3. Operator-facing error copy: never surface raw validator internals. "I hit a snag processing that — say 'continue' and I'll pick up where we left off." Log the real error to provenance as today.

---

## P1-1: Gate placement moves out of the conversation (operator ruling)

### Ruling

Living documents do **not** require approval inside the onboarding conversation. When the orchestrator marks a doc `ready`, drafting fires (as today) and the result is **stored immediately as a draft-status module**. The conversation acknowledges it in one line ("I've drafted your Story Frameworks — it's in your Library whenever you want to review it") and moves on to the next gap. No gate card blocks the thread.

The **Library becomes the review surface**: it gains (a) draft/approved status display, (b) inline edit of module markdown, (c) an Approve action that issues the gate token and promotes the module. Gate discipline is fully preserved — **draft-status modules never feed production pipelines** (ideas, drafting, publishing all read approved modules only). This is a relocation of the gate, not a removal. T2.9 gate-token enforcement applies at the Library approve action.

### Implementation notes

- `ModuleStore.store` gains a `status` parameter (`draft` | `approved`); default remains `approved` for existing call sites so nothing else breaks. Onboarding auto-drafts store with `status="draft"` and no gate token.
- The existing `/api/onboarding/<run>/gate/<playbook>` endpoint is retained but repointed: it becomes the Library's approve/edit backend (approve issues the token and flips status).
- Remove gate cards from `onboarding_session.html`. Coverage chips gain a `drafted` state that links to the Library entry.
- The eight-card hub redirect logic stays as-is.

---

## P1-2: Conversation continuity — resume, dead air, and pause

### Diagnosis

1. The template branch meant to re-render existing conversation on page load is an empty Jinja comment — reopening a run shows only the opening question. Pausing means visually losing the whole thread.
2. After any doc is drafted (and previously, after a gate decision), nothing re-engages the orchestrator. The operator had to keep asking "what next."
3. No navigation out of the conversation — no back link, no signal that leaving is safe.

### Fix

1. **Render history on load.** Server passes the structured message list (operator turns + AI replies from `collected["session_messages"]` / `collected["ai_replies"]`) to the template; template renders them in order. This also motivates finishing the session-storage refactor from CORRECTION-session-memory-and-materials-v1.1 (parallel arrays are exactly what makes this fragile) — store turns as a single ordered list of `{role, text, ts}` objects.
2. **No dead ends.** Every orchestrator reply must end with either a question or an explicit next step; when a doc drafts, the acknowledgment line and the next question arrive in the same reply. Enforce in the orchestrator prompt ("Never end a reply without a question or a clearly stated next step unless all eight docs are drafted") and verify in the human UI test.
3. **Header gains** a "← Console" link and a persistent line: "Your progress saves automatically — you can leave and come back anytime." Because history now renders on load, this claim becomes true.

---

## P1-3: Readback / message rendering

### Diagnosis

`_build_readback`'s generic path stringifies dicts (`str(item)[:60]`) producing truncated raw Python (`{'platform': 'X (@StackPenni)', 'aspect_ratio': '16:9 for pr`). Markdown bold markers render as literal asterisks. Long lines are visually cut off. Empty lists render bare headers.

### Fix

Readbacks shrink in importance under P1-1 (the Library shows the real document), but the one-line acknowledgment and the Library rendering both need this:

1. Per-schema formatters: each dict type renders its meaningful fields in prose ("X (@StackPenni): 16:9 for posts, subtitles burned in"), never `str(dict)`. Unknown dicts fall back to key: value lines, untruncated.
2. Render markdown to HTML client-side (a minimal renderer for bold/bullets is fine; no heavy dependency needed) and fix message CSS: `overflow-wrap: break-word`, no fixed heights clipping content.
3. Empty sections are omitted, not rendered as bare headers.
4. Operator-visible strings remain business-owner language (existing principle) — no output keys or schema names in the chat surface.

---

## P1-4: Upload feedback and honest failure

### Diagnosis

`uploadFile()` shows nothing while uploading; the chip appears only on completion. Worse, the `catch` block pushes failed uploads into `pendingFiles` as if they succeeded — a silent lie to the operator.

### Fix

1. On file selection, immediately render a chip in "uploading…" state (spinner or pulsing dot) per file; flip to done state on success.
2. On failure, flip the chip to an error state with a retry affordance. Never add a failed upload to `pendingFiles`. The message payload only lists files whose ingestion returned `material_id`.
3. For large files, if trivially available from fetch, show progress; otherwise indeterminate state is acceptable. Do not over-engineer.

---

## P2-1: Conversational latency

### Diagnosis

Every conversational turn routes through `active.default` → `ollama_glm52`, a reasoning model with 8K max_tokens. The operator pays full reasoning latency for lightweight conversational routing turns.

### Fix (config + one-line code change)

1. Add a role to `models.yaml`: `active.converse` pointing at a fast non-reasoning backend — `ollama_gpt_oss_120b` or `ollama_kimi_k26` (both already defined). Operator picks; either is a reasonable first choice and it's a config edit to swap.
2. `onboarding_message` calls the orchestrator with `backend="converse"` (falls back to `default` if the role is absent — adapter's active-block resolution already supports this shape with a small fallback guard).
3. **Drafting keeps the reasoning backend** (`default`). Quality lives in the drafts; speed lives in the conversation. If conversational routing quality visibly degrades on the faster model, revert with one config line — that is the test.

---

## P2-2: Orchestrator prompt — agency-intake posture and doc definitions

The operator's summary judgment: the conversation should feel like an agency gathering a new client's marketing brief. Concretely, update `prompts/session/onboarding_orchestrator_v1.md` (bump to v2):

1. **One-line plain definition when a doc first becomes the focus.** E.g., "Next I want to build your Story Frameworks — the narrative shapes your content uses, like transformation stories or myth-busting. Different from the Format Guide, which covers what the content physically is on each platform." The Format Guide / Story Frameworks confusion came from the system never explaining its own vocabulary.
2. **Mine materials before asking.** When materials cover a topic, the orchestrator confirms and extends ("Your style deck already gives me the palette and typography — two things it doesn't tell me: …") rather than asking questions the uploads already answered. Asking for what was already provided is the single strongest "this isn't listening" signal.
3. **Seed extraction is aggressive and verbatim-preserving.** Routed seeds carry the operator's actual phrasing, not paraphrase — humanness originates at input (charter principle).
4. Never end a reply without a question or next step (per P1-2).

---

## Acceptance criteria (for Hermes's own end-to-end test, per PROCESS-definition-of-done-v1.0)

1. Fresh onboarding run with at least one docx and one pdf uploaded: all eight docs draft with visibly populated fields; Voice Profile extracts patterns from the uploaded text; Sources Engine and Viral Patterns are non-empty; no rendered prompt contains an unresolved `{placeholder}`.
2. No raw dict text appears anywhere in the UI; no visually clipped text in messages or Library.
3. Reload mid-conversation: full history renders; conversation continues coherently.
4. Every AI reply ends with a question or next step until all docs are drafted.
5. Upload a file: uploading indicator appears immediately; failure shows an error chip, not silent success.
6. Draft a doc → it appears in Library as draft; edit it; approve it; gate token recorded; draft-status modules are excluded from a production read path (add one test proving this).
7. Orchestrator returning `next_focus: null` does not error.
8. Conversational turn latency measurably lower on the `converse` backend (log latency_ms before/after from provenance).
