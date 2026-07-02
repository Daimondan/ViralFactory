<!-- version: 1.0 -->
# Business Profile Analysis

You are analyzing a business to build its profile for a content co-creation system.

## Context
- Business name: {business_name}
- Any existing info: {existing_info}

## Raw Q&A from the operator

{qa_transcript}

## Your task

Analyze the Q&A above and produce a structured business profile as JSON. The profile must capture:

1. **business** — the core identity: name, slug (lowercase, hyphenated, no spaces), and a one-line description
2. **brands** — all brands/sub-brands mentioned, each with a name and its purpose
3. **subjects** — the core topics this business covers (these become the tag allowlist the system enforces on all content)
4. **platforms** — where this business publishes, each with name, handle, and priority (1 = primary)
5. **goals** — what the business wants to achieve with content
6. **red_lines** — topics, stances, or aesthetics never to use
7. **audience_description** — who the content is for, in one paragraph

## Rules

- Extract ONLY what the operator said. Do not invent brands, subjects, or goals they didn't mention.
- If something is unclear, make your best inference but keep it conservative.
- Subjects should be short (1-3 words), lowercase. These are tags, not essays.
- The slug must be lowercase, hyphenated, no spaces or special characters.
- Red lines are hard rules — "no get-rich-quick framing", "no political content", etc.

## Output format

Respond with ONLY valid JSON matching this structure:

```json
{
  "business": {
    "name": "string",
    "slug": "string",
    "description": "string"
  },
  "brands": [
    {"name": "string", "purpose": "string"}
  ],
  "subjects": ["string"],
  "platforms": [
    {"name": "string", "handle": "string", "priority": 1}
  ],
  "goals": ["string"],
  "red_lines": ["string"],
  "audience_description": "string"
}
```