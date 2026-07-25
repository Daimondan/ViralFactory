# DIVERGENCE-024: Bundle Instagram audio is platform-native, not a local music bed

**Filed by:** Builder
**Date:** 2026-07-25
**Status:** RATIFIED — see `docs/decisions/AMENDMENT-016-platform-native-audio-attachment.md` (approved with binding conditions C1–C8, Charter v3.11)
**Severity:** P1 — blocks using Bundle-discovered audio in a production render/publish path
**Type:** LOGIC / STRUCTURE / OPS

## Operator direction

Use Bundle Social audio returned for a Reel as the near-term music source. The operator does not want a fixed five-bed library to constrain creative fit.

## Verified provider behavior

A live call to the configured `bundle_instagram` discovery adapter for asset 26 returned 38 candidates (25 duration/preview-filtered) from planner queries. Bundle's documented Instagram audio API returns an `audio_id` which is attached to an **Instagram Reel publish payload** as `data.INSTAGRAM.musicSoundInfo.musicSoundId`. It is not a general-purpose, durably downloadable music library:

- the `download_url`/preview field is temporary and may be absent;
- audio attachment is supported only for Instagram Reels;
- the connected Instagram account must use Facebook Login;
- Bundle documents the result as Meta-authorized audio for third-party Reel publishing;
- Bundle/Meta do not provide a final attached-audio Reel preview before it is live.

## Conflict with current charter

CHARTER v3.10 requires only current, locally hashed, rights-valid, cost-approved soundtrack candidates in a frozen manifest; Gate 3 approves the exact final artifact. It explicitly says discovery metadata does not imply synchronization/republication rights.

Using Bundle's `audio_id` is a different media role: Instagram applies the platform-native audio after ViralFactory has rendered its local video. Treating a temporary `download_url` as a local final mix would violate both provider semantics and the current charter. The local final artifact cannot contain the native Instagram audio, and the published Reel cannot be fully previewed with that attachment through the API.

## Requested ruling

Approve or reject a distinct **platform-native audio attachment** role with all of these safeguards:

1. Only Instagram Reels using a Facebook-Login-connected eligible account may select it.
2. Persist immutable evidence: provider, endpoint, team/account context, `audio_id`, type, title/artist/creator when available, duration, retrieval timestamp, and candidate response hash.
3. Display the selected audio identity and any provider preview to the operator before the publish decision.
4. Require explicit per-piece operator approval of the selected `audio_id`; never auto-select or auto-publish.
5. Do not save/download/embed temporary preview audio as the local final MP4.
6. Leave all non-Instagram destinations without this attachment unless their own native-audio contracts are separately ratified.
7. Gate 3 / Publish UI must show that final native audio is applied by Instagram at publish time and cannot be included in the local render preview.

## Builder action

- Verified Bundle discovery against the real running service without reading credentials.
- Did not download, hash, embed, register, or publish an unverified Bundle preview as a local music bed.
- Did not weaken per-piece human approval.
- Did not add a platform-specific code path pending the requested ruling.
