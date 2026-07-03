<!-- version: 1.0 -->
# Series Breakdown

You are breaking down a series idea into its constituent parts. The parent idea (Part 1) has been approved. Now you must define Parts 2 through N so each part stands alone but declares its place in the arc.

## Context
- Business: {business_name}
- Subjects: {subjects}
- Audience: {audience_description}
- Cadence: {cadence}

## Parent idea (Part 1 — already approved)

{parent_idea}

## Parent hooks

{parent_hooks}

## Parent treatment

{parent_treatment}

## Available modules

### Viral Patterns
{viral_patterns}

### Audience Insights
{audience_insights}

### Story Frameworks
{story_frameworks}

### Format Guide (index of available formats)
{format_guide}

## Your task

Break this series into {n} parts total. Part 1 is the parent (already defined above). Generate Parts 2 through {n}.

Each part must:
- Stand alone as a complete piece of content (a reader who only sees Part 3 should still get value)
- Declare its place in the arc (e.g., "Part 2 of {n}: After the opening, we go deeper into...")
- Have its own distinct idea — NOT a reworded version of the parent
- Have its own hook options (2-3, different from the parent's)
- Have capture_required tasks if the part needs human-captured material
- Follow the same format and treatment as the parent, unless the breakdown naturally calls for a different angle

## Rules
- Each part's idea must be genuinely different from the parent and from each other
- The arc should build: Part 1 hooks, middle parts deepen, final part lands
- Hook options per part must be different in approach (not just reworded)
- If a part needs footage/recording that the operator must capture, list it in capture_required
- Do not repeat the parent's idea text — each part has its own focus

## Output format

Respond with ONLY valid JSON:

```json
{
  "parts": [
    {
      "part_number": 2,
      "idea": "string — the core concept for this part, distinct from the parent",
      "hook_options": ["string — 2-3 alternative hooks for this part"],
      "capture_required": ["string — human capture tasks needed, empty list if none"]
    }
  ]
}
```

Only output parts 2 through {n}. Part 1 is the parent and is not included.