# BUILDER-NOTE-022 — Requested carousel + native Instagram soundtrack

**Filed by:** Builder (Hermes)
**Date:** 2026-08-02
**Status:** SUPERSEDED — correction recorded in `DIVERGENCE-027`, 2026-08-02

## Request

Operator approved the seven-slide “AI Receipts” caption (with the Thoreau quote removed from the caption) and directed immediate publishing as a ViralFactory-tracked Instagram carousel using the opening/main segment of “i was only temporary 2 u.”

## Corrected finding

The live Buffer connection has the Stackwell Pennifold Instagram integration and can transport multiple image assets for a carousel. The current external-import UI still cannot create an ordered multi-image external carousel asset.

The initial note incorrectly treated Reel-only API-native attachment under AMENDMENT-016 as a bar on all carousel music. Instagram supports music on multiple-photo posts in its mobile app, and Buffer supports it through notification publishing: the operator completes the scheduled carousel in Instagram and selects the audio there. This is a normal implementation gap, not an architect decision.

## Superseded request

No architect ruling is requested. The corrected work is to add ordered external-carousel import and Buffer notification-publish handoff, then capture the final Instagram post ID/URL after the operator adds the music in Instagram.

## Builder status

No publish was attempted. The approved caption is retained without the Thoreau quote, and the seven rendered carousel images remain available in the Drive review folder.
