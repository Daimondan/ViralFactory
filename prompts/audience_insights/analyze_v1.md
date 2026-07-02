<!-- version: 1.0 -->
# Audience Insights Analysis

You are building an Audience Insights module for a content co-creation system — a plain-language picture of who the content is for and what they respond to.

## Context
- Business name: {business_name}
- Business subjects: {subjects}
- Audience description (from Business Profile): {audience_description}

## Operator's own description of their audience

{operator_description}

## Observed audience data (comments, DMs, analytics exports — may be empty)

{audience_data}

## Audience signals from admired examples (what commenters say on the content the operator admires)

{admired_signals}

## Your task

Produce a structured Audience Insights document as JSON. Clearly distinguish between "user's belief" (what the operator thinks) and "observed evidence" (what data shows). The module must capture:

1. **who_they_are** — demographics, psychographics, context
2. **what_they_care_about** — core concerns, desires, fears
3. **language** — words, phrases, slang they use (the drafter should echo these)
4. **what_they_reward** — what gets engagement (likes, shares, comments, DMs)
5. **what_turns_them_off** — what gets ignored or criticized
6. **evidence_vs_belief** — a reconciliation: which operator beliefs have evidence, which are untested

## Rules

- Mark each insight as either "belief" (operator's assertion) or "evidence" (observed in data)
- If audience data is empty, work from the operator's description and admired signals — but mark everything as "belief"
- Language patterns must be verbatim quotes where possible, not paraphrases
- Do not invent audience segments the operator didn't describe
- "What they reward" should be specific to THIS audience, not generic social media advice

## Output format

Respond with ONLY valid JSON:

```json
{
  "who_they_are": "string — plain language paragraph",
  "what_they_care_about": [
    {"concern": "string", "type": "belief|evidence", "evidence": ["string"]}
  ],
  "language": [
    {"phrase": "string — verbatim if possible", "context": "string — where/when used", "type": "belief|evidence"}
  ],
  "what_they_reward": [
    {"behavior": "string — what gets engagement", "type": "belief|evidence", "evidence": ["string"]}
  ],
  "what_turns_them_off": [
    {"turn_off": "string", "type": "belief|evidence", "evidence": ["string"]}
  ],
  "evidence_vs_belief": "string — summary of which beliefs are tested vs untested",
  "summary": "string — one paragraph plain-language summary"
}
```