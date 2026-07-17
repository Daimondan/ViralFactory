# Playbook: Sources Engine

<!-- playbook_type: onboarding -->

*Repo location: `playbooks/sources-engine.md` · Executed by the system's AI during onboarding (Part A) and continuously (Part B). v1.0*

<!-- run_order: 3 -->
<!-- display_label: Sources Engine -->

*The most important playbook after Voice. Two parts: onboarding discovery (runs once) and the continuous learning loop (runs forever). This is an engine, not a one-time setup.*

## Purpose

Turn the user's trusted sources into explicit, learnable criteria for what a good source is for THIS business — then continuously find, score, propose, and prune sources against those criteria.

## Inputs (onboarding)

- **Seed sources from the user:** 10–30 URLs, RSS feeds, YouTube channels, newsletters, social accounts they already trust and read
- **Seed content:** documents, notes, saved articles that represent "the kind of material we work from"
- **Anti-examples (optional but valuable):** 3–5 sources or pieces the user considers junk for this business
- Existing source bank, if any (user brings their own files — no privileged import from external systems)

## Procedure — Part A, onboarding discovery

1. Ingest seed sources; extract clean content (deterministic extractor, not LLM).
2. AI analyzes the seed set and writes the **Source Criteria** — an explicit, human-readable document: subjects covered, formats favored, freshness expectations, quality signals (original data? practitioner-written? regional relevance?), and disqualifiers (drawn from anti-examples). Every criterion cites which seed sources evidence it. **Criteria are text the user can read and edit at the gate — never hidden weights.**
3. From the criteria, AI generates the monitoring plan: search queries, feed subscriptions, channels/accounts to watch → proposed `sources.yaml`.
4. If a prior source bank exists: re-score every entry against the criteria; propose keep / park / drop in bulk (grouped, one sitting — not 1,545 individual decisions).
5. Gate → criteria stored as the **Source Criteria module**; `sources.yaml` written; bank re-scored.

## Procedure — Part B, continuous loop (scheduled)

1. Monitor everything in `sources.yaml`; ingest new items into the Source Bank (scored against criteria; low scores auto-parked, never silently deleted).
2. **Discover:** run the monitoring queries + follow citation/link trails from high-scoring items to find candidate NEW sources not yet in `sources.yaml`.
3. Score candidates against the criteria. Candidates above threshold → **proposed source additions** at the async gate, each with evidence ("found via X, matches criteria A/C/D, sample item attached").
4. **Prune:** sources dormant or persistently low-scoring → proposed removals at the gate.
5. **Criteria learning:** when the user's approvals/rejections at the source gate contradict the criteria (they keep rejecting a type the criteria likes), AI proposes a criteria amendment — through the gate, versioned, with the contradicting decisions as evidence.

## Output

Source Criteria module (versioned) · `sources.yaml` (versioned) · self-growing, self-pruning Source Bank.

## Gate

New sources, removals, and criteria changes all pass the async gate. Item-level ingestion inside approved sources does not (that's the existing approve/reject/park review queue).