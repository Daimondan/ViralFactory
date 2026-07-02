# StackPenni Content System

A content co-creation system for entrepreneurs who have ideas and domain experience but don't produce content themselves. The person supplies **seeds** (spoken ideas), **reactions** (taste), and **lived material**; the system does the making — drafting in the person's real voice, publishing, measuring, researching what goes viral in their domain, and proposing its own improvements weekly. Every improvement passes a human gate.

StackPenni (Caribbean AI + wealth brand) is user #1. The system is generic: **the harness is code, the business lives entirely in config and modules.** A second business onboards with zero code changes.

## Start here, by role

| You are | Read, in order |
|---|---|
| **Builder agent (Hermes)** | 1. `docs/CHARTER-v3.md` (the constitution) → 2. `BUILD_PLAN.md` (your tasks, guardrails, how to work) → 3. `playbooks/` (the procedures you are implementing runners for). Then work `BUILD_PLAN.md` top-down, one task at a time. |
| **Architect / reviewer (Claude)** | `docs/CHARTER-v3.md` → `PROGRESS.md` → latest `review-wN` tag diff → write `docs/reviews/review-wN.md` |
| **Operator (human)** | `docs/OPERATOR.md` (written at M7). Until then: you direct in plain language, react to drafts, and approve/reject at gates. You never write code. |
| **New contributor / other AI** | `docs/CHARTER-v3.md`, then this README's repo map. |

## Repo map

```
README.md            ← you are here
BUILD_PLAN.md        ← milestones, tasks, acceptance criteria, guardrails (builder's source of truth)
PROGRESS.md          ← one line per completed task (builder appends)
docs/
  CHARTER-v3.md      ← the constitution: design, principles, phases, system diagram
  reviews/           ← Claude's weekly review notes (review-wN.md)
  OPERATOR.md        ← end-user manual (created at M7)
playbooks/           ← written procedures the system's AI runs to build/update modules
                       (voice-profile-builder.md + others; text, not code)
prompts/             ← every LLM prompt template, versioned (no prompts in code)
config/              ← ALL business-specific values: business.yaml, models.yaml, sources.yaml
modules/{business}/  ← the 8 living modules per business (versioned markdown; gate-only writes)
src/                 ← the generic harness (Flask console, playbook runner, LLM adapter,
                       validator, provenance, jobs)
tests/               ← keep green; every task lands with a test
```

## Ground rules (full list in BUILD_PLAN.md — these are the ones that get broken)

1. **Nothing business-specific in code.** Brand names, topics, feeds, queries, taxonomies, model names → `config/`. If a string describes the business, it is config.
2. **No judgment in code.** Understanding-tasks (tagging, titling, voice analysis, quality) = prompt template + JSON schema + validator. Never keyword heuristics.
3. **AI proposes, human gates — everywhere.** Modules are never edited silently. No gate, no write.
4. **If an AI does something clever once, it becomes a playbook.** Ad-hoc judgment that isn't captured is a defect.
5. **No patch scripts.** Wrong output → fix the prompt, config, or validator, versioned. Never a one-off fix.

## Workflow

Builder works `BUILD_PLAN.md` top-down → commit per task (task ID in message) → append to `PROGRESS.md` → blocked? open a GitHub issue, move on → every ~7 days tag `review-wN` → operator shares repo with Claude → corrections arrive as `docs/reviews/review-wN.md` → builder applies them before new milestone work.

## Status

Pre-M0. Charter v3 ratified. Voice Profile playbook written; remaining playbooks (source discovery, audience insights, story frameworks, visual intake) due from the architect before M2.
