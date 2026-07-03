<!-- version: 1.0 -->
# Source Research Analysis — YouTube video breakdown

You are analyzing a YouTube video to understand why it performs well. Your analysis feeds the Source Bank — a living knowledge document that grows through research.

## Context
- Business: {business_name}
- Source: {source_name}
- Channel: {channel_name}
- Video title: {video_title}
- Video description: {video_description}
- Watch URL: {watch_url}
- Published: {published_at}

## Source Criteria (what this business considers valuable)

{source_criteria}

## Your task

Analyze this video across five dimensions. Every finding MUST be framed as a **hypothesis** — external virality is observable, but its cause is inference. Do not state anything as a fact about why it worked.

## Output format

Respond with ONLY valid JSON:

```json
{
  "hook_analysis": "string — what makes the title/thumbnail stop the scroll (hypothesis-framed)",
  "structure_analysis": "string — how the content is organized (hook → tension → payoff, listicle, story arc, etc.)",
  "format_analysis": "string — the content format (talking head, B-roll, screen recording, mixed, etc.) and how format serves the message",
  "emotion_analysis": "string — the emotional arc and what drives engagement emotionally",
  "pacing_analysis": "string — pacing observations (fast cuts, slow builds, silence usage, etc.)",
  "hypothesis": "string — THE KEY HYPOTHESIS: what specifically might make this approach work for our audience, framed as a testable hypothesis (e.g. 'Caribbean-specific AI examples may resonate more than generic ones because...')",
  "relevance_score": "integer 1-10 — how relevant this video is to our business audience",
  "key_takeaways": ["string — actionable takeaways we could apply to our content"],
  "source_bank_entry": "string — a one-paragraph summary suitable for the Source Bank module"
}
```