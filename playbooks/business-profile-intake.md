# Playbook: Business Profile Intake

*Repo location: `playbooks/business-profile-intake.md` · Executed by the system's AI during onboarding, through the console. v1.0*

## Purpose

Build `config/business.yaml` and the brand context the drafter loads. This runs FIRST — every other playbook reads its output.

## Inputs

Guided Q&A (spoken or typed): what the business is, brands/sub-brands, core subjects, platforms, goals, who the person thinks the audience is, tone red-lines (topics/stances never to take).

## Procedure

1. Q&A through console.
2. AI drafts: business summary, brand list, subject taxonomy (the tag allowlist the validator enforces), platform list, red-lines.
3. Present draft back in plain language: "Here's what I understood — correct anything."
4. Gate → write `business.yaml` + `modules/{biz}/brand-context.md`.

## Output

`business.yaml` (machine) + brand-context module (drafter-readable).

## Gate

User confirms the understanding. Nothing downstream runs until this passes.