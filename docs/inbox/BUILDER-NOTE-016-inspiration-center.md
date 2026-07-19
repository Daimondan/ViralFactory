# BUILDER-NOTE-016 — Inspiration Center and trend discovery divergence

**To:** Architect
**From:** Builder
**Date:** 2026-07-19
**Status:** AWAITING ARCHITECT
**Subject:** Operator-approved top-level Inspiration surface requires architecture and Build Plan ruling

Daimon approved beginning a top-level **Inspiration** surface with separate **Top Trending Audio** and **Top Trending Videos** sections.

I filed the full proposal and live provider evidence at:

`docs/decisions/DIVERGENCE-016-inspiration-center-and-trend-discovery.md`

Tracking issue: https://github.com/Daimondan/ViralFactory/issues/4

## Live capability already proved

- Bundle.social Instagram audio: HTTP 200; ranked music and original sounds.
- Bundle.social TikTok: unavailable because the provider team has no connected TikTok account.
- TikHub TikTok Top 50 and Viral 50 audio: HTTP 200 with music metadata and usage evidence.
- TikHub TikTok regional/recommendation videos: HTTP 200 with IDs, captions, creators, timestamps, engagement, linked audio, and media references; the Barbados request did not prove Barbados-specific ranking.
- TikHub Instagram recommended Reels: HTTP 200 with two usable records, but no reliable view counts in the tested payload.
- TikHub Instagram Explore: HTTP 400; excluded from the proposed first slice.

## Proposed first task

`VF-INSP-001` is a read-only vertical slice: provider-neutral audio/video records, immutable snapshot evidence, configured TTL caching, stale/error states, and a server-rendered `/inspiration` page. It performs no idea creation, media download, paid generation, or publish action.

## Decisions needed

1. Treat Inspiration as a top-level Researcher-owned operator workbench, or keep it nested under an existing role surface?
2. Dedicated trend evidence tables, Source Bank extension, or dedicated records registered into Source Bank only after explicit operator action?
3. Permit “Top Trending Videos” as the operator heading when cards label exact recommendation/chart evidence and do not claim measured momentum from one observation?
4. Place VF-INSP as a post-M13 bounded slice, extend M6, or use another milestone?
5. Keep creative trend-audio discovery contractually separate from production soundtrack acquisition while sharing only mechanical provider utilities?

No Inspiration route, schema, config, or template has been implemented pending this ruling. Existing protected credentials are not included in repository files.