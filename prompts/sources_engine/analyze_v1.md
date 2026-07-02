<!-- version: 1.0 -->
# Source Criteria Analysis

You are analyzing a business's trusted sources to build explicit, learnable criteria for what makes a good source for THIS business.

## Context
- Business name: {business_name}
- Business subjects: {subjects}
- Audience: {audience_description}

## Seed sources from the operator

{seed_sources}

## Anti-examples (sources the operator considers junk)

{anti_examples}

## Your task

Analyze the seed sources and anti-examples, then produce a **Source Criteria** document as JSON. This document must be human-readable (the operator will review and edit it at the gate — never hidden weights).

The criteria must capture:

1. **subjects_covered** — what topics good sources cover for this business
2. **formats_favored** — what formats the operator trusts (long-form articles, YouTube videos, newsletters, academic papers, social posts, etc.)
3. **freshness** — how recent content needs to be (e.g., "published within 6 months", "timeless is fine if foundational")
4. **quality_signals** — what makes a source trustworthy (original data? practitioner-written? regional relevance? peer-reviewed? cited by other trusted sources?)
5. **disqualifiers** — what makes a source junk (drawn from anti-examples: content-mill SEO? clickbait? no original reporting? regurgitation?)
6. **regional_relevance** — does the source need to be Caribbean/regional, or is global fine if the insight transfers?
7. **monitoring_plan** — proposed feeds, channels, and search queries derived from the criteria
8. **criteria_summary** — a one-paragraph plain-language summary the operator can read and edit

## Rules

- Every criterion must cite which seed sources evidence it (the `evidence` field)
- Anti-examples must inform the disqualifiers
- The monitoring plan should be actionable: real URLs, real search queries, real channel names — derived from what the operator provided
- Do not invent sources the operator didn't mention — derive the monitoring plan from their seeds
- Criteria are hypotheses, not facts — frame them as "the operator's trusted sources suggest..."
- Subjects should match the business's subject taxonomy from business.yaml

## Output format

Respond with ONLY valid JSON:

```json
{
  "subjects_covered": [
    {"subject": "string", "evidence": ["seed source name or URL"]}
  ],
  "formats_favored": [
    {"format": "string", "evidence": ["seed source name"]}
  ],
  "freshness": {
    "expectation": "string",
    "evidence": ["seed source name"]
  },
  "quality_signals": [
    {"signal": "string", "description": "string", "evidence": ["seed source name"]}
  ],
  "disqualifiers": [
    {"disqualifier": "string", "evidence": ["anti-example name or description"]}
  ],
  "regional_relevance": {
    "requirement": "string",
    "evidence": ["seed source name"]
  },
  "monitoring_plan": {
    "feeds": [
      {"name": "string", "url": "string", "type": "rss|atom|html", "enabled": true}
    ],
    "channels": [
      {"name": "string", "platform": "youtube|x|instagram|tiktok", "handle": "string", "enabled": true}
    ],
    "queries": [
      {"query": "string", "engine": "exa|duckduckgo", "enabled": true}
    ]
  },
  "criteria_summary": "string"
}
```