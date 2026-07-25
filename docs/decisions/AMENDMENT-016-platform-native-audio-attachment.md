# AMENDMENT-016 — Platform-native audio attachment as a distinct audio role

**Filed:** 2026-07-25
**Filed by:** Architect (vf-architect)
**Status:** APPROVED WITH BINDING CONDITIONS — ratifies DIVERGENCE-024; incorporated into Charter v3.11
**Ratifies:** `docs/decisions/DIVERGENCE-024-bundle-native-instagram-audio.md`
**Related:** AMENDMENT-010; AMENDMENT-011; `docs/inbox/BUILDER-NOTE-019-bundle-native-instagram-audio.md`
**Repo state reviewed:** `1208220` — "DOCS: request Bundle native-audio ruling"

## Decision

Approve a **third audio role**, `platform_native_audio`, distinct from the existing `music_bed` and
`vo_only` roles.

Under this role ViralFactory does not acquire, hash, mix, or republish audio. It transmits a
platform-issued identifier alongside the publish payload, and the destination platform applies the
track inside its own product under its own licence. The audio never enters our render.

**Scope is narrow and does not generalise:** Instagram Reels only, via Bundle Social, on an
Instagram account connected through Facebook Login. No other destination, provider, or format
inherits this role. Extending it requires a separate ratification with its own verified provider
evidence.

The builder is commended for filing this rather than implementing it. Discovering a charter conflict
mid-task and stopping to file it is the behaviour the operating loop is built to produce.

## Why AMENDMENT-011 C1 does not bar this

C1 holds that discovery metadata is not usage rights, and that a candidate is render-eligible only
with a persisted rights record carrying `rights_status: verified`, a terms URL, a retrieval
timestamp, and a SHA-256 evidence hash. That apparatus was written for **acquisition**: taking
possession of a track, synchronising it into our MP4, and republishing it. That act requires a
licence we do not hold, and C1 correctly refuses it.

Attachment is a different act. Sending an `audio_id` that resolves to a track already inside Meta's
own licensed catalogue, and letting Meta apply it inside Meta's own product, involves no possession,
no synchronisation by us, and no republication by us. C1's prohibition is not engaged.

C1's *machinery* must not be applied here either. There is no acquisition, so there is no
`acquisition_method`; there is no downloaded artifact, so there is no meaningful content hash. Routing
this role through `validate_rights_record` would mean manufacturing an evidence hash of a terms page
to satisfy a validator designed for a transaction that never occurs. That is compliance theatre and
it degrades the value of every genuine rights record in the table. This role gets its own evidence
schema (C2) and is explicitly exempt from `soundtrack_rights.validate_rights_record`.

## What this does not change

**The bed library remains required and is not superseded by this ruling.** Platform-native attachment
reaches exactly one surface. Every other destination carries only the audio baked into the file we
render. Owned beds are the brand audio layer and a registry asset under the reference asset registry —
generated once, gated once, reused. Native attachment is a per-piece distribution tactic on Instagram.
The two are complements, not substitutes, and this amendment must not be cited as grounds for
deferring music bed work.

## Binding conditions

### C1 — Mutual exclusivity with a local music bed

A piece using `platform_native_audio` renders locally with **VO and SFX only**. No music bed may be
mixed into a render that also carries a native attachment. Selecting native audio on a piece with an
approved bed invalidates the bed selection and requires re-approval of the resulting artifact.

Rationale: two independent music sources stacked by two systems, one of which we cannot preview,
produces an unbounded and unpredictable result. With this condition the published piece is fully
determined by one approved artifact plus one named identifier.

### C2 — Distinct evidence schema; no manufactured rights record

Persist an immutable `native_audio_attachment` record: provider, endpoint, team/account context,
`audio_id`, audio type, title/artist/creator where available, duration, retrieval timestamp, and a
hash of the candidate response payload. Sanitise URLs per the existing `sanitize_url` rules.

This record proves *what was selected and when*. It does not assert rights, and no field may be named
or valued so as to imply a rights verdict. `rights_status` does not appear in this schema. No provider
may be marked `commercial_safe`.

### C3 — Gate 3 approves a bounded artifact, and the identifier is part of the approval

The approved piece is the **pair**: the exact local artifact plus the exact `audio_id`. Changing the
identifier invalidates the Gate 3 approval and requires approval of the new pair, exactly as a track
switch does under AMENDMENT-011 §3.

The Gate 3 and publish surfaces must state plainly that the final audio is applied by Instagram at
publish time and cannot appear in the local preview, and must display the selected audio identity and
any provider preview. Disclosure alone does not satisfy this condition — it is satisfied by C1
bounding the delta and by the identifier being an approved object rather than a downstream detail.

### C4 — VO intelligibility must be measured before use on any VO-led piece

This role is **barred from narration-led pieces** until the following is completed and reported:
publish one probe Reel with a native attachment over a representative VO track, retrieve the live
Reel, and measure whether the narration remains intelligible and at what relative level against the
applied music.

If the publish payload exposes no control over the music-to-VO balance and the narration loses, the
role remains available for non-narration cutdowns and stays barred from VO-led pieces until a control
path exists. This is a measurement to be reported, not an argument to be made. VO is the master clock
under AMENDMENT-010; an audio layer we cannot balance against it is a production risk, not a
preference.

### C5 — Post-publish verification is mandatory

Because the artifact cannot be previewed, it must be audited. After publish, retrieve the live Reel
and confirm the attached audio matches the approved `audio_id`. A mismatch fails loudly, is recorded
against the piece, and surfaces an unpublish path to the operator. A publish path with no preview and
no verification is unreviewable and is not approved.

### C6 — Per-piece human approval, no automation of the choice

No auto-selection, no auto-publish, no bulk approve, no "apply to all Reels" affordance. The operator
selects and approves one identifier for one piece. Ranking may order candidates; it may not choose.

### C7 — The temporary preview is never persisted as final audio

The provider's `download_url`/preview field is temporary and may be absent. It may be played for the
operator at the point of decision. It must never be saved, hashed, registered as a reference asset,
mixed into a render, or treated as the piece's audio.

### C8 — No inheritance by other destinations

X, TikTok, YouTube, and every other destination are excluded. Each has different catalogue rights,
different account eligibility, and different or absent third-party attachment support. Any extension
requires its own divergence with live provider evidence.

## Charter impact

Amends AMENDMENT-011 §2 — "Gate 3 is the first and only approval of the soundtrack-bearing asset...
the operator sees and plays the actual mixed asset" — **for this role only**, replacing it with the
bounded-pair approval defined in C3 and made bounded by C1. AMENDMENT-011 is otherwise unchanged and
continues to govern `music_bed` and `vo_only` in full.

Bump Charter to **v3.11** recording the third audio role, the scope limit, and conditions C1–C8.

## Definition of Done

1. `platform_native_audio` exists as a named role in the soundtrack plan contract, rejected by the
   validator for any destination other than Instagram Reels on an eligible connected account.
2. The `native_audio_attachment` evidence record persists and is immutable; a test proves the role
   does not pass through `validate_rights_record` and that no rights verdict is implied.
3. A test proves C1: a piece cannot hold both an approved music bed and a native attachment.
4. A test proves C3: changing `audio_id` invalidates a prior Gate 3 approval.
5. C4's probe measurement is completed and its result pasted into the changelog, including the
   measured relative levels. Until then, a VO-led piece must be refused this role by code, not by
   convention.
6. C5 verification runs after publish, with a proven failure path on mismatch.
7. Human UI walkthrough: candidate list, selection, the Gate 3 pair display and its notice, the
   publish surface, a deliberate mismatch triggering the C5 failure, and the unpublish path. Report
   what was clicked and what happened. A passing test suite is not a walkthrough.
8. One `CHANGELOG.md` entry, inserted in correct reverse-chronological position at the top of the
   file. `docs/PROGRESS.md` updated.
