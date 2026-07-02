# Decision: OB1 is NOT the data store — ViralFactory is fully standalone

## Status
Accepted — overrides architect recommendation in `docs/reviews/review-divergence-001.md`

## Context
Claude's review of DIVERGENCE-001 recommended that module storage use repo markdown as system of record with OB1 as a "read-only mirror for Daimon's browsing (sync job, later, optional)." Daimon clarified on 2026-07-02 that ViralFactory must be a **completely separate system** with its own database. OB1 is not involved — not even as a mirror. Daimon loads his sources for StackPenni like any user would: through the onboarding flow, sharing docs, connecting Obsidian, etc.

## Decision
- ViralFactory has its own SQLite database. No OB1 Supabase connection, no OB1 MCP tools, no OB1 dependency.
- Module storage = repo markdown in `modules/{business}/` only. No OB1 mirror.
- Source onboarding = user uploads materials, shares docs, connects Obsidian, etc. — same as any user. No privileged import from OB1.
- The Sources Engine playbook's "existing source bank" reference to OB1 exports is removed. If a user has prior sources, they bring them as files.
- OB1 is Daimon's personal knowledge system. ViralFactory is a product. They don't touch.

## Consequences
- Simpler architecture: one database (SQLite), no external Supabase dependency
- Cleaner generalization: every user onboards the same way, including user #1
- No risk of messing up OB1's 257 entities / 1747 edges
- The "OB1 mirror optional" language in CONTEXT.md, BUILD_PLAN, and charter must be removed

## Owner Input
Daimon said: "please dont mess up my ob1 brain, this should be a separate system its own database, when i as a user load my sources for stackpenni, i have to do so like any user, like share docs, or connect obsidian etc"