# CORRECTION — Session Memory & Materials — v1.1

**Date:** 2026-07-03
**Author:** Claude (architect review), from Daimon's field report (voice-profile session transcript)
**Applies to:** current main (post-5b12e45)
**Supersedes nothing; extends CORRECTION-onboarding-single-thread-v1.0** (Item 2 there — the single-thread orchestrator — is not yet built; the card hub is still live, as expected. The fixes below apply to the *current* per-playbook session loop AND carry forward as requirements for the orchestrator.)

---

## Field report (verbatim symptoms)

In a voice-profile session, the operator uploaded a zip of voice notes and a brand report docx, answered questions, and the AI:
1. Asked "what kind of stuff did you send?" *after* receiving the zip.
2. Re-asked "what's the business?" *after* receiving the full StackPenni Brand Report.
3. Finally repeated an earlier reply **word-for-word**.

These are not one bug. They are four, and together they make every intake session degrade into a loop. Traced below in order of impact.

---

## F1 — File-only turns are invisible to the AI (P0)

**Where:** `app.py`, `session_message` (~line 388).

**Bug:** The operator's message text is appended to `collected["session_messages"]`, but the `[Files attached: ...]` note is appended only to `business_qa`:

```python
collected["session_messages"].append(text)          # text only — no file note
...
collected["business_qa"].append({"q": "(session message)", "a": text + file_note})
```

`_build_conversation_history` builds operator lines from `session_messages` and **explicitly excludes** `business_qa` pairs where `q == "(session message)"`. Net effect: when the operator sends a file with no text (exactly what happened with the zip), their turn renders in the transcript as `Operator:` — a blank line. The LLM has no idea an upload occurred.

This explains symptom 1 precisely: the model received a blank operator turn, so "i just sent you it" on the next turn referenced nothing it could see.

**Fix:** Store the file note in the transcript source of truth:

```python
turn_text = text
if files:
    turn_text = (text + "\n" if text else "") + f"[Operator attached files: {', '.join(files)}]"
collected["session_messages"].append(turn_text)
```

(Interim fix. F4 replaces this storage shape entirely — do F4 if touching this area anyway.)

---

## F2 — Uploaded material content never reaches the conversation LLM (P0, and a hard blocker for voice profile)

**Where:** `session_upload` → `MaterialsIntake.ingest_file`; `session_message` LLM call; `prompts/session/generic_converse_v1.md`.

**Three compounding gaps:**

1. **The converse prompt has no materials variable at all.** `generic_converse_v1.md` receives `playbook_purpose`, `conversation_so_far`, `playbook_inputs` — nothing about ingested materials. Whatever intake extracts, the conversational AI never sees it. This explains symptom 2: the Brand Report was ingested, then the model re-asked what the business is, because from its viewpoint no report exists.

2. **No docx extraction exists.** `materials.py` handles zip (extracts and recurses — good), PDF (`_extract_pdf_text`), and audio (stub). There is no `.docx` branch anywhere in the codebase. The Brand Report's text was never extracted even into the materials table.

3. **Audio transcription is a stub.** Every audio file becomes `"[Audio file: X — transcription pending]"` and stays pending forever — DIVERGENCE-003 approved transcription but it was never implemented. **This makes the Voice Profile playbook structurally unable to work**: its entire input is voice notes, and the system currently captures zero words from them. Everything downstream of this playbook (the humanizer's voice bank, voice-matched drafting) is starved at the source.

**Fixes:**

- **2a — Inject materials into the converse call.** After building `conversation_so_far`, query materials for this run and append a section:
  ```
  ## Materials the operator has uploaded
  - voice-note-01.opus — transcript: "..." (or: "audio, transcription pending")
  - StackPenni Brand Report.docx — extracted text (first N chars): "..."
  ```
  Add `{materials_summary}` to the prompt template. Cap per-material excerpt (~1,500 chars) and total (~6,000 chars); prefer transcripts/extractions over filenames, but *always* list filenames + status so the AI can at least acknowledge receipt and say "I have your zip — transcribing now" instead of asking what was sent.

- **2b — Add docx extraction.** `python-docx` (or `mammoth`) branch in `ingest_file` for `.docx`. Store extracted text as content, same as PDF.

- **2c — Implement transcription (blocker for voice profile).** Wire the pending-transcription queue to an actual transcriber. Given the stack, the pragmatic path is a whisper endpoint (self-hosted on the VPS via faster-whisper, or a hosted API — record the choice as a decision doc since it touches cost and data residency). On ingest of audio: enqueue → transcribe async → update material content → the next converse turn picks it up via 2a. The AI should tell the operator transcription is running rather than pretending the audio doesn't exist.

---

## F3 — History truncation keeps the OLDEST turns and drops the NEWEST (P0)

**Where:** `app.py` line ~440: `"conversation_so_far": conversation_so_far[:4000]`.

**Bug:** `[:4000]` is a head slice. Once the transcript exceeds 4,000 characters, every character past that — i.e., **the most recent turns** — is silently cut. The model is then reasoning over only the beginning of the conversation, which is why it regenerated an early question *verbatim* (symptom 3): from its perspective, the conversation genuinely was still at that point. Answers like "audionotes" and "just talking to other ppl" fell off the visible window entirely.

This is the same truncation flagged in CORRECTION v1.0's migration notes, but it's worse than flagged: it's not just too small, it's cutting from the wrong end.

**Fix (two stages):**
- **Today:** change to a tail slice — `conversation_so_far[-4000:]` — and raise the budget (the adapter can afford 12–16k chars here; 4k is far too small for a multi-turn intake).
- **Proper:** rolling summarization — keep the last ~10 turns verbatim, compress everything older into a short "established facts so far" block that is *regenerated* (not appended) each time it rolls. This is also a hard requirement for the v1.0 orchestrator, where one thread spans the whole onboarding.

---

## F4 — Parallel-array transcript storage is fragile (P1)

**Where:** `_build_conversation_history` interleaves `session_messages[i]` and `ai_replies[i]` positionally.

**Bug class:** Correct ordering depends on the two arrays staying perfectly alternating for the life of the run. Any drift — a failed LLM call after the operator message was stored, a page reload re-appending the greeting, an empty-text file turn — shifts alignment by one, and from then on every operator answer appears attached to the wrong AI question. That misattribution *also* produces re-asking (the model sees its question "unanswered"), and it is undetectable from logs because both arrays look fine individually.

**Fix:** Replace the two arrays with a single ordered turn log:

```json
"turns": [
  {"role": "ai", "text": "...", "ts": "..."},
  {"role": "operator", "text": "...", "files": ["a.zip"], "ts": "..."}
]
```

Append atomically per event, in order. Build the transcript by walking the list. Keep a one-time migration that zips the legacy arrays into `turns` on first read. This shape is also what the v1.0 orchestrator needs, so it's not throwaway.

---

## F5 — No anti-repeat guard in the prompt or the server (P1)

Even with F1–F4 fixed, nothing *forbids* re-asking. Two cheap layers:

- **Prompt:** add to `generic_converse_v1.md` a `## Questions you have already asked` section (extract the AI turns' questions) plus the instruction: *"Never re-ask a question that appears above. If the operator's answer was thin, ask a deeper or different question about the same topic — do not repeat the original wording. If the operator has answered something, treat it as answered even if the answer was short."* Terse answers like "audionotes" or "just talking to friends" ARE answers; the current prompt's "dig deeper on thin answers" guidance is being read as license to re-open settled questions.
- **Server:** before returning `reply`, compare it against prior AI turns (normalized similarity; difflib ratio > 0.9 is plenty). On a near-duplicate, regenerate once with an appended instruction naming the collision; if it duplicates again, return the reply anyway but log it — that log entry means context assembly is broken again upstream.

---

## Priority & sequencing

| Fix | Priority | Effort | Ship |
|-----|----------|--------|------|
| F3 tail-slice + bigger budget | P0 | 1 line + constant | today |
| F1 file note into transcript | P0 | ~5 lines | today |
| F2a materials into prompt | P0 | small | this tag |
| F2b docx extraction | P0 | small | this tag |
| F2c audio transcription | P0 (blocks voice profile) | medium — needs decision on whisper hosting | this tag; decision doc first |
| F4 turn log | P1 | medium | this tag or next |
| F5 anti-repeat | P1 | small | this tag |
| F3 rolling summary | P1 | medium | with orchestrator |

**Note on scope:** none of this replaces v1.0 Item 2 (single-thread orchestrator). But do NOT build the orchestrator on top of the current transcript plumbing — F1/F3/F4 are exactly the failure modes that would make a whole-onboarding thread collapse faster than the per-card sessions did. Land these first; the orchestrator inherits them.

## Acceptance criteria
1. Sending a file with no text produces an operator turn that names the attachment; the AI's next reply acknowledges the specific file.
2. Uploading a docx of business info, then asking "what do you know about my business so far?" yields specifics from the document without re-asking.
3. Uploading audio yields, within one turn, an acknowledgment that transcription is running; once complete, the transcript content is usable in conversation.
4. A 30-turn session never re-asks an answered question and never emits a reply >0.9-similar to a prior one.
5. Simulated failure test: kill the LLM call after an operator message is stored, retry — transcript alignment remains correct (F4).
