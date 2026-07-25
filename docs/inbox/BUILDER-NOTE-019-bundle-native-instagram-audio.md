# BUILDER-NOTE-019 — Bundle native Instagram audio routing

**Filed by:** Builder (Hermes)
**Date:** 2026-07-25
**Status:** AWAITING ARCHITECT

## Request

Operator directs ViralFactory to use Bundle Social audio dynamically per Reel rather than constrain music to a fixed five-bed library.

## Verified evidence

The running Bundle discovery route returned 38 candidates (25 filtered) for asset 26. Bundle's documented API exposes a platform-native Instagram `audio_id` for attachment to an Instagram Reel publish payload; it is not a stable local audio library. The local preview/download field is temporary/optional, and the final published Reel cannot be previewed with the native attachment through the API.

## Required architect ruling

Please review `docs/decisions/DIVERGENCE-024-bundle-native-instagram-audio.md` and ratify or reject the proposed platform-native-audio role. The proposal retains immutable candidate evidence and explicit per-piece operator approval, but does not download/embed the audio in ViralFactory's local MP4.

## Builder status

No unratified code path was added. Bundle discovery is operational in the live Flask service; the reel worker was restarted and now inherits the Bundle runtime credentials.
