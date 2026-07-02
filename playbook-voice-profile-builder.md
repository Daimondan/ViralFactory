# Playbook: Voice Profile Builder

*Repo location: `playbooks/voice-profile-builder.md` · Executed by the system's AI during onboarding, through the console. v1.0*

## Purpose

Produce a versioned **Voice Profile** module for a user, from whatever materials they have, such that a drafter loading it produces text the user recognizes as "sounds like me." This playbook replaces any ad-hoc AI voice analysis. It ends with a calibration gate — the profile is not stored until the user confirms it.

## Inputs (material-agnostic — any combination, in preference order)

1. **Natural speech** (best — unperformed): voice-note transcripts, dictated messages, podcast/interview transcripts
2. **Casual writing**: chat exports (WhatsApp/Telegram/Slack/DMs), emails written by the user, social posts
3. **Edited writing**: articles, newsletters, scripts (usable, weight lower — edited text performs a voice)
4. **Nothing** → run the **Interview Fallback** (Step 1b)

Minimum viable corpus: ~2,000 words of the user's own words, or ~30 minutes of transcribed speech. More is better; recency matters more than volume.

## Procedure

### Step 1 — Intake
Console asks the user what they have (checklist of the input types above) and accepts uploads/pastes. Record per sample: channel, approximate date, audience (who it was written/said to). If corpus < minimum → Step 1b.

### Step 1b — Interview Fallback (no-corpus path)
Run a guided spoken interview through the console (voice preferred, text accepted). 10–12 open questions designed to elicit natural speech about their domain, e.g.: "Tell me about a money lesson someone in your family taught you — what happened?" · "What's a popular belief in your industry you think is wrong? Why?" · "Explain what your business does like you're telling a friend at a bar." · "What's a story you tell often?" The *answers* become the corpus. Do not clean them up.

### Step 2 — Normalize
Keep only the user's own words: strip other parties' messages, quoted/forwarded text, boilerplate signatures. Tag each retained sample with its channel. Never "correct" grammar, spelling, or dialect — variance is signal.

### Step 3 — Analyze (with evidence)
Analyze the corpus across these dimensions. Every finding MUST cite 1–3 verbatim examples from the corpus as evidence. No finding without evidence.

- **Lexicon**: recurring words/phrases, characteristic verbs, intensity words, filler habits
- **Rhythm**: sentence-length mix, use of fragments, where the point lands (front-loaded vs built-to)
- **Connectors**: how they actually transition between ideas (and what they never use)
- **Openings & closers**: how they start a thought; how they end one
- **Stance**: how opinions are voiced; humor style; how they disagree
- **Dialect & register**: dialect features and code-switching patterns (e.g., Caribbean English features) — these go on a **do-not-sanitize list**, preserved verbatim in output
- **Channel shifts**: how voice differs by audience/channel (note, don't average away)
- **Negative space**: what this person never does (words, structures, tones absent from the corpus)

### Step 4 — Draft the profile (fixed schema below)
Write the Voice Profile using the output schema. Include the **Tells Checklist**: the global AI-tell list (uniform sentence length, state-then-restate, announced transitions, puffery, generic conclusions) PLUS user-specific anti-patterns discovered in Step 3 (things that would ring false for THIS person).

### Step 5 — Calibration gate (mandatory — the profile is a proposal until this passes)
1. Generate **3 short pieces (~100 words each) on the same topic** from the user's domain, each using the candidate profile with slightly different emphasis.
2. Console asks: "Which is closest to you? What's off in each?" (plain-words reactions, tap + type/speak)
3. Revise the profile from the reactions. Repeat, max 3 rounds.
4. Exit condition: user says one reads as "sounds like me" → store as **Voice Profile v1.0**. If 3 rounds don't converge → store best candidate as v0.9 flagged "refine via Feedback Log," and proceed — the inward loop will sharpen it.

### Step 6 — Version & provenance
Store the module with: version, date, list of source materials used (by type + date range, not content), and the calibration outcome. Log the run in the provenance log.

## Update procedure (post-onboarding)
The inward loop mines the **Feedback Log** (the user's plain-words reactions to drafts) for candidate voice patterns and anti-patterns. Candidates are proposed at the weekly gate with evidence (the reactions that support them). Approved → version bump. The Voice Profile is never edited silently.

## Output schema (fixed headings — the drafter depends on these)

```markdown
# Voice Profile — {user/brand} — v{X.Y}
## Identity line          (one sentence: who is speaking, to whom, from what experience)
## Audience               (who the reader/viewer is, in plain language)
## Positive patterns      (8–12 entries: pattern → 1–2 verbatim examples from corpus)
## Dialect & register     (features to preserve verbatim; code-switch rules; do-not-sanitize list)
## Channel notes          (how voice shifts per platform, if evidenced)
## Anti-patterns          (what this person never does — with evidence of absence)
## Tells Checklist        (global AI tells + user-specific; the drafter self-audits against this)
## Provenance             (sources by type + date range; calibration outcome; version history)
```

## Guardrails
- This playbook is a procedure + prompts, not code. Prompts live in `prompts/voice_profile/*.md`; the runner is generic.
- Findings without verbatim evidence are invalid — the validator rejects them.
- Dialect is preserved, never corrected. Sanitizing a voice is a defect.
- The calibration gate cannot be skipped, including for user #1.
