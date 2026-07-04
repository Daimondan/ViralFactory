# ViralFactory

A content co-creation system for entrepreneurs who have ideas and domain experience but don't produce content themselves. The person supplies **seeds** (spoken or typed ideas), **reactions** (taste), **direct edits** (when they choose to write), and **lived material**; the system does the making — drafting in the person's real voice, publishing, measuring, researching what goes viral in their domain, and proposing its own improvements. Every improvement passes a human gate.

**StackPenni** (Caribbean AI + wealth brand) is user #1. The system is generic: **the harness is code, the business lives entirely in config and modules.** A second business onboards with zero code changes.

> **This is a living repository.** Docs are the source of truth, not an afterthought. If you change the pipeline, update the docs in the same session. If you changed the pipeline but did not update this doc, that is a bug.
>
> **If you made a decision and it's not in `CHANGELOG.md`, that is a bug.**

## Start here, by role

| You are | Read, in order |
|---|---|
| **Builder agent (Hermes)** | 1. `docs/CONTEXT.md` (the domain + decisions) → 2. `BUILD_PLAN.md` (your tasks, guardrails) → 3. `playbooks/` (the procedures you implement). Then work `BUILD_PLAN.md` top-down, one task at a time. |
| **Architect / reviewer (Claude)** | `docs/CONTEXT.md` → `docs/decisions/DIVERGENCE-001-charter-amendments.md` → `docs/PROGRESS.md` → latest `review-wN` tag diff → write `docs/reviews/review-wN.md`. Incorporate divergences into Charter v3.3. |
| **Operator (human)** | `docs/CONTEXT.md` (what we're building and why) → `docs/INTAKE-USER1.md` (what materials you need to provide). You direct in plain language, react to drafts, and approve at gates. You never write code. |
| **New contributor / other AI** | `docs/CONTEXT.md`, then this README's repo map. |

## Repo map

```
README.md                       ← you are here
BUILD_PLAN.md                   ← milestones, tasks, acceptance criteria, guardrails
CHANGELOG.md                    ← EVERY decision logged with type + rationale
docs/
  CONTEXT.md                    ← the domain document: purpose, users, language, rules, edge cases
  PROGRESS.md                   ← living progress tracker (updated every session)
  INTAKE-USER1.md               ← onboarding materials checklist for user #1
  UI-DIRECTION.md               ← console UI direction (laptop-first, mobile-friendly)
  decisions/
    DIVERGENCE-001-charter-amendments.md  ← 5 amendments to Charter v3 from the grill session
    DIVERGENCE-002-viralfactory-fully-standalone.md ← no OB1 dependency
    AMENDMENT-003-staged-content-pipeline.md ← four content gates (Ideas → Draft → Assets → Publish)
    AMENDMENT-004-treatment-block.md ← treatment block on idea cards (scope, format, capture, reuse, rationale)
  inbox/                         ← architect→builder filing protocol (README + processed/)
  reviews/                      ← Claude's weekly review notes (review-wN.md)
  diagrams/                     ← system diagrams (Mermaid + vertical-flow text + SVG)
playbooks/                       ← written procedures the system's AI runs (text, not code)
  business-profile-intake.md        ← runs FIRST; builds business.yaml + brand context
  voice-profile-builder.md          ← builds the Voice Profile module (the first and last compromise)
  sources-engine.md                  ← onboarding discovery + continuous loop (engine, not one-time)
  viral-patterns-starter.md          ← seeds Viral Patterns module from admired + anti-examples
  audience-insights-builder.md      ← who the content is for, what they respond to
  story-frameworks-starter.md        ← how to tell a story per subject type
  format-guide-starter.md            ← which format fits which message on which platform
  visual-style-intake.md             ← brand look + shot library + real-vs-generated blend rules
prompts/                         ← every LLM prompt template, versioned (no prompts in code)
config/                          ← ALL business-specific values: business.yaml, models.yaml, sources.yaml
modules/{business}/             ← the 8 living modules per business (versioned markdown, gate-only writes)
src/                             ← the generic harness (Flask console, playbook runner, LLM adapter,
                                  validator, provenance, jobs)
tests/                           ← keep green; every task lands with a test
```

## Ground rules (full list in BUILD_PLAN.md — these are the ones that get broken)

1. **Nothing business-specific in code.** Brand names, topics, feeds, queries, taxonomies, model names → `config/`. If a string describes the business, it is config.
2. **No judgment in code.** Understanding-tasks (tagging, titling, voice analysis, quality) = prompt template + JSON schema + validator. Never keyword heuristics.
3. **AI proposes, human gates — everywhere.** Modules are never edited silently. No gate, no write.
4. **If an AI does something clever once, it becomes a playbook.** Ad-hoc judgment that isn't captured is a defect.
5. **No patch scripts.** Wrong output → fix the prompt, config, or validator, versioned. Never a one-off fix.
6. **Per-piece approval is non-negotiable.** No auto-publish, ever.
7. **Direct edits are authoritative.** Human text overrides AI draft.
8. **Gate is async.** Queue, not a scheduled sitting.

## Workflow

Builder works `BUILD_PLAN.md` top-down → commit per task (task ID in message) → append to `docs/PROGRESS.md` → log every decision to `CHANGELOG.md` → blocked? open a GitHub issue, move on → every ~7 days tag `review-wN` → operator shares repo with Claude → corrections arrive as `docs/reviews/review-wN.md` → builder applies them before new milestone work.

## Status

Charter now at v3.4 (AMENDMENT-003 staged pipeline + AMENDMENT-004 treatment block + AMENDMENT-006 Writer/Assembler split + AMENDMENT-007 Writer per-platform + Assembler media-only + AI review loop). M0-M8 complete. M9 (Writer/Assembler boundary redesign) implemented. AI tells + voice-deepening correction applied: voice-first ideation, shared AI-tells catalog, cognitive Voice Profile dimensions, and real self-audit fix application. 761 tests passing.

## Original architect docs (preserved for reference)

The following files were written by Claude (architect) before the grill session. They contain the original Charter v3 design. The grill session identified 5 divergences (see `docs/decisions/DIVERGENCE-001-charter-amendments.md`), which are incorporated into `docs/CONTEXT.md` and `BUILD_PLAN.md`. The originals are preserved for audit trail:

- `StackPenni-Build-Charter-v3_2.md` — original charter (superseded by v3.3 → v3.4)
- `playbook-voice-profile-builder.md` — Voice Profile playbook (to be moved to `playbooks/`)
- `playbooks-remaining-seven.md` — remaining 7 playbooks (to be split into `playbooks/`)
- `UI-DIRECTION.md` — UI direction (laptop-first amendment in DIVERGENCE-001)