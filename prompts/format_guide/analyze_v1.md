<!-- version: 1.0 -->
# Format Guide Analysis

You are building a Format Guide module for a content co-creation system — which output format fits which message on which platform.

## Context
- Business name: {business_name}
- Platforms: {platforms}
- Business subjects: {subjects}

## Format observations from analyzed winners (from Viral Patterns)

{format_observations}

## Platform norms (general knowledge of what works where)

{platform_norms}

## Your task

Produce a Format Guide as JSON. This is a decision table: message type × platform → format, with per-format skeletons the drafter follows. Each format entry MUST include the AMENDMENT-004 enrichment fields:

1. **format_name** — the format (thread, single post, reel script, carousel, long-form video, newsletter, etc.)
2. **platforms** — which platforms this format works on
3. **best_for** — what message types or subject types this format suits
4. **length** — target length (words, seconds, or slides)
5. **structure_notes** — how to structure content in this format
6. **skeleton** — a fill-in-the-blank template the drafter follows
7. **requires_human_capture** — does this format require the operator to capture real footage/photos/audio? (none | optional | required) — if required, list capture tasks
8. **capture_tasks** — list of specific capture tasks if requires_human_capture is not "none" (e.g., "Record 15s of street footage in Bridgetown", "Photograph receipt close-up")
9. **effort_level** — low | medium | high (how much production effort per piece in this format)
10. **reuse_pathways** — can this format be reused across platforms or as part of a series? How?
11. **status** — proven | experimental | retired (defaults to "proven" for established formats, "experimental" for new ones the operator wants to try)
12. **provenance** — how was this format entry established? (e.g., "Derived from Viral Patterns analysis", "Operator request", "Experiment debut via idea card")

## Rules

- Cover all platforms the business publishes on
- Skeletons must be specific enough for a drafter to follow mechanically
- requires_human_capture: "required" means the format CANNOT be produced without the operator capturing something real
- capture_tasks must be specific and actionable when present
- reuse_pathways: think about how one piece in this format can spawn derivatives
- status: use "experimental" for formats the operator hasn't tried but wants to (the Experiments Queue will update these)
- Do not invent platforms the operator didn't list
- Effort level: low = can produce in <15 min, medium = 15-60 min, high = >1 hour or needs multiple captures

## Output format

Respond with ONLY valid JSON:

```json
{
  "formats": [
    {
      "format_name": "string",
      "platforms": ["string"],
      "best_for": ["string — message types"],
      "length": "string — target length",
      "structure_notes": "string",
      "skeleton": "string — fill-in template",
      "requires_human_capture": "none|optional|required",
      "capture_tasks": ["string — specific tasks, empty if none"],
      "effort_level": "low|medium|high",
      "reuse_pathways": ["string — how this format can be reused"],
      "status": "proven|experimental|retired",
      "provenance": "string — how this entry was established"
    }
  ],
  "decision_table": [
    {
      "message_type": "string",
      "platform": "string",
      "recommended_format": "string — format_name",
      "rationale": "string"
    }
  ],
  "summary": "string — one paragraph plain-language summary"
}
```