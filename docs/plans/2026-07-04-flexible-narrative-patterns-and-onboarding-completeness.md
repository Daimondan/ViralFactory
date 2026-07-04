# Flexible Narrative Patterns + Onboarding Completeness Dashboard

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Replace hardcoded narrative structure (entry_point/tension/turn/landing) with config-driven narrative patterns that the LLM selects per subject, and build an onboarding completeness dashboard that surfaces missing inputs and lets the operator fill them from existing uploaded sources.

**Architecture:** Two independent features sharing a common principle — make implicit assumptions explicit and config-driven. Feature 1 changes how story frameworks are structured (schema, prompt, converter, downstream consumption). Feature 2 changes how onboarding gaps are surfaced and filled. Both follow the config-driven, LLM-does-judgment pattern.

**Tech Stack:** Flask, SQLite, Jinja2 templates, existing LLMAdapter, existing ModuleStore, existing PlaybookRunner

---

## Feature 1: Config-Driven Narrative Patterns

### Background

Currently `STORY_FRAMEWORKS_SCHEMA` in `module_store.py` hardcodes 4 required fields: `entry_point`, `tension`, `turn`, `landing`. The prompt `story_frameworks/analyze_v2.md` explicitly demands these 4 beats per framework. The markdown converter `story_frameworks_to_markdown()` renders only these 4 fields. The drafter prompt (`draft/generate_v2.md`) receives the story framework module and follows that structure.

This forces every subject type into the same dramatic-arc shape — but a listicle doesn't have tension/turn, a tutorial is problem/steps/result, a hot take is claim/evidence/counter/verdict.

### Design

A new config file `config/narrative_patterns.yaml` declares known patterns. The LLM picks the best pattern per subject type (or proposes a custom one). The schema becomes flexible: `structure_name` + `beats: [{name, content}]` instead of 4 fixed fields. The markdown converter renders whatever beats exist. The drafter prompt reads whatever structure is in the module.

The patterns config is generalizable — any business can define their own patterns or use the defaults.

---

### Task 1: Create narrative_patterns.yaml config

**Objective:** Define the default narrative patterns config file.

**Files:**
- Create: `config/narrative_patterns.yaml`

**Step 1: Write the config**

```yaml
# Narrative Patterns — config-driven story structure options
# Each pattern defines a set of beats the LLM fills per subject type.
# The LLM selects the best-fitting pattern per subject, or proposes a custom one.

patterns:
  - name: dramatic_arc
    description: "Classic tension-driven story — hook, conflict, revelation, resolution"
    beats: [entry_point, tension, turn, landing]

  - name: myth_buster
    description: "Bust a common misconception — state the myth, reveal reality, prove it, deliver takeaway"
    beats: [myth, reality, proof, takeaway]

  - name: how_to
    description: "Practical tutorial — problem, steps, result"
    beats: [problem, steps, result]

  - name: hot_take
    description: "Contrarian opinion with evidence — claim, evidence, counter-argument, verdict"
    beats: [claim, evidence, counter, verdict]

  - name: listicle
    description: "Numbered insights — hook, items, summary"
    beats: [hook, items, summary]

  - name: before_after
    description: "Transformation story — before state, catalyst, after state, lesson"
    beats: [before, catalyst, after, lesson]

  - name: receipt_card
    description: "Evidence-first — claim, source, meaning, move"
    beats: [claim, source, meaning, move]

  - name: pattern_breaker
    description: "Same background, different decision — setup, fork, divergence, lesson"
    beats: [setup, fork, divergence, lesson]

# Allow the LLM to propose custom patterns when none fit
allow_custom: true
```

**Step 2: Verify config loads**

Run: `cd /home/daimon/ViralFactory && PYTHONPATH=src .venv/bin/python -c "import yaml; d=yaml.safe_load(open('config/narrative_patterns.yaml')); print(len(d['patterns']), 'patterns'); print(d['allow_custom'])"`

Expected: `8 patterns` / `True`

**Step 3: Commit**

```bash
git add config/narrative_patterns.yaml
git commit -m "config: add narrative_patterns.yaml — config-driven story structures"
```

---

### Task 2: Update STORY_FRAMEWORKS_SCHEMA to flexible beats

**Objective:** Replace hardcoded entry_point/tension/turn/landing with structure_name + beats array.

**Files:**
- Modify: `src/module_store.py:1058-1084` (STORY_FRAMEWORKS_SCHEMA)

**Step 1: Write failing test**

Add to `tests/test_pipeline_ux_and_assembly.py` or a new `tests/test_narrative_patterns.py`:

```python
def test_story_frameworks_schema_accepts_flexible_beats():
    """Schema must accept structure_name + beats instead of hardcoded 4 fields."""
    from module_store import STORY_FRAMEWORKS_SCHEMA
    import jsonschema
    
    framework = {
        "subject_type": "AI",
        "structure_name": "myth_buster",
        "beats": [
            {"name": "myth", "content": "AI will replace Caribbean jobs"},
            {"name": "reality", "content": "AI will replace businesses that don't adopt"},
            {"name": "proof", "content": "Evidence from..."},
            {"name": "takeaway", "content": "Start integrating AI today"},
        ],
        "grounded_in_example": "GaryVee content",
        "grounded_in_story": "Operator's AI adoption story",
        "voice_compatible": True,
        "voice_note": "",
    }
    # Should not raise
    jsonschema.validate({"frameworks": [framework], "summary": "test"}, STORY_FRAMEWORKS_SCHEMA)
```

**Step 2: Run test to verify failure**

Run: `pytest tests/test_narrative_patterns.py::test_story_frameworks_schema_accepts_flexible_beats -v`
Expected: FAIL — schema still requires entry_point/tension/turn/landing

**Step 3: Update the schema**

Replace `STORY_FRAMEWORKS_SCHEMA` (lines 1058-1084) with:

```python
STORY_FRAMEWORKS_SCHEMA = {
    "type": "object",
    "required": ["frameworks", "summary"],
    "properties": {
        "frameworks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["subject_type", "structure_name", "beats",
                             "grounded_in_example", "grounded_in_story",
                             "voice_compatible", "voice_note"],
                "properties": {
                    "subject_type": {"type": "string"},
                    "structure_name": {"type": "string"},
                    "beats": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name", "content"],
                            "properties": {
                                "name": {"type": "string"},
                                "content": {"type": "string"},
                            },
                        },
                    },
                    "grounded_in_example": {"type": "string"},
                    "grounded_in_story": {"type": "string"},
                    "voice_compatible": {"type": "boolean"},
                    "voice_note": {"type": "string"},
                },
            },
        },
        "summary": {"type": "string"},
    },
}
```

**Step 4: Run test to verify pass**

Run: `pytest tests/test_narrative_patterns.py::test_story_frameworks_schema_accepts_flexible_beats -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/module_store.py tests/test_narrative_patterns.py
git commit -m "schema: flexible beats replace hardcoded entry/tension/turn/landing"
```

---

### Task 3: Update story_frameworks_to_markdown converter

**Objective:** Render flexible beats instead of hardcoded 4 fields.

**Files:**
- Modify: `src/module_store.py:1087-1111` (story_frameworks_to_markdown)

**Step 1: Write failing test**

```python
def test_story_frameworks_markdown_renders_flexible_beats():
    from module_store import story_frameworks_to_markdown
    
    data = {
        "frameworks": [
            {
                "subject_type": "AI",
                "structure_name": "myth_buster",
                "beats": [
                    {"name": "myth", "content": "AI replaces jobs"},
                    {"name": "reality", "content": "AI replaces businesses that don't adopt"},
                    {"name": "proof", "content": "Evidence here"},
                    {"name": "takeaway", "content": "Adopt AI now"},
                ],
                "grounded_in_example": "GaryVee",
                "grounded_in_story": "My AI story",
                "voice_compatible": True,
                "voice_note": "",
            }
        ],
        "summary": "Test summary",
    }
    md = story_frameworks_to_markdown(data, "1.0")
    assert "### AI" in md
    assert "Structure: myth_buster" in md
    assert "AI replaces jobs" in md
    assert "AI replaces businesses" in md
    # Old hardcoded labels should NOT appear
    assert "Entry point:" not in md
    assert "Tension:" not in md
```

**Step 2: Run test to verify failure**

Run: `pytest tests/test_narrative_patterns.py::test_story_frameworks_markdown_renders_flexible_beats -v`
Expected: FAIL — converter still renders entry_point/tension/turn/landing

**Step 3: Update the converter**

Replace `story_frameworks_to_markdown` (lines 1087-1111) with:

```python
def story_frameworks_to_markdown(data: dict, version: str = "1.0") -> str:
    """Convert validated Story Frameworks JSON into the module markdown.
    Renders flexible beats — any structure_name + beats array."""
    lines = [f"# Story Frameworks — v{version}"]

    lines.append(f"\n## Summary\n{data.get('summary', '')}")

    lines.append("\n## Frameworks")
    for f in data.get("frameworks", []):
        lines.append(f"\n### {f['subject_type']}")
        lines.append(f"- **Structure:** {f['structure_name']}")
        for beat in f.get("beats", []):
            lines.append(f"- **{beat['name'].replace('_', ' ').title()}:** {beat['content']}")
        lines.append(f"- **Grounded in example:** {f['grounded_in_example']}")
        lines.append(f"- **Grounded in story:** {f['grounded_in_story']}")
        vc = "✓" if f.get("voice_compatible") else "✗"
        lines.append(f"- **Voice compatible:** {vc}")
        if f.get("voice_note"):
            lines.append(f"- **Voice note:** {f['voice_note']}")

    lines.append(f"\n## Provenance\n- Version: {version}")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Schema: story_frameworks_v2")

    return "\n".join(lines)
```

**Step 4: Run test to verify pass**

Run: `pytest tests/test_narrative_patterns.py::test_story_frameworks_markdown_renders_flexible_beats -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/module_store.py tests/test_narrative_patterns.py
git commit -m "converter: render flexible beats in story_frameworks_to_markdown"
```

---

### Task 4: Update story frameworks analysis prompt

**Objective:** Update the LLM prompt to know about narrative patterns and select the best one per subject.

**Files:**
- Create: `prompts/story_frameworks/analyze_v3.md` (new version, v3.0)
- Modify: `src/app.py:3212` — point to analyze_v3.md
- Modify: `src/app.py:1080` and `src/app.py:1443` — update playbook prompt references

**Step 1: Write the new prompt**

Create `prompts/story_frameworks/analyze_v3.md`:

```markdown
<!-- version: 3.0 -->
# Story Frameworks Analysis

You are building a Story Frameworks module for a content co-creation system — how to tell a story per subject type for this business.

## Context
- Business name: {business_name}
- Business subjects (tag taxonomy): {subjects}
- Audience: {audience_description}

## Available narrative patterns

The following narrative patterns are available. For each subject type, SELECT the pattern that best fits the topic and audience — or propose a custom pattern if none fit (set structure_name to "custom" and define your own beats).

{narrative_patterns}

## Routed seeds (from onboarding conversation)

{routed_seeds}

## Full conversation transcript

{conversation_transcript}

## Uploaded materials (full content)

{materials_content}

## Admired examples (from Viral Patterns intake — for grounding)

{admired_examples}

## The operator's own stories (spoken or typed — stories they tell often)

{operator_stories}

## Voice Profile summary (for voice-compatibility checking)

{voice_summary}

## Your task

For each core subject type in the taxonomy, draft a story framework as JSON. Each framework must have:

1. **subject_type** — from the business's subject taxonomy
2. **structure_name** — name of the narrative pattern you selected (from the Available patterns above), or "custom" if you propose a new one
3. **beats** — array of {name, content} objects, one per beat in the selected pattern. Each beat's name must match the pattern's beat labels. For custom patterns, define your own beat names.
4. **grounded_in_example** — which admired example informs this framework
5. **grounded_in_story** — which of the operator's own stories informs this
6. **voice_compatible** — boolean: does this framework fit the Voice Profile?
7. **voice_note** — if not fully compatible, what to adjust

## Rules

- One framework per subject type — no more, no less
- SELECT the narrative pattern that best fits the subject matter and audience — do not default to the same pattern for every subject
- Beat content must be specific, not generic ("Start with a contrarian claim about AI adoption in Caribbean SMEs" not "Start with a hook")
- Grounding in admired examples: cite the specific URL/name
- Grounding in operator stories: use the operator's actual story, not an invented one
- Voice compatibility: if the framework requires a pattern the Voice Profile says to avoid, mark voice_compatible=false and explain in voice_note
- Frameworks should be actionable: a drafter reading this should know exactly how to structure content for that subject type
- Mine the conversation transcript and materials for story references the operator_stories list doesn't capture
- If operator stories or admired examples are empty, say so honestly in the grounding fields rather than pretending they exist

## Output format

Respond with ONLY valid JSON:

```json
{
  "frameworks": [
    {
      "subject_type": "string — from taxonomy",
      "structure_name": "string — pattern name or 'custom'",
      "beats": [
        {"name": "string — beat label", "content": "string — specific guidance"}
      ],
      "grounded_in_example": "string — admired example URL/name, or '(none provided)'",
      "grounded_in_story": "string — operator's story reference, or '(none provided)'",
      "voice_compatible": true,
      "voice_note": "string — empty if compatible, adjustment guidance if not"
    }
  ],
  "summary": "string — one paragraph plain-language summary"
}
```
```

**Step 2: Update the route to use v3 prompt and load patterns config**

In `src/app.py`, the `analyze_story_frameworks` route (line 3212) and the playbook runner references (lines 1080, 1443) need to:
- Point to `story_frameworks/analyze_v3.md`
- Load `config/narrative_patterns.yaml` and pass it as the `narrative_patterns` variable

For the route at line 3212, change `prompt_file="story_frameworks/analyze_v1.md"` to `prompt_file="story_frameworks/analyze_v3.md"` and add:

```python
import yaml
patterns_path = os.path.join(app.config["CONFIG_DIR"], "narrative_patterns.yaml")
with open(patterns_path) as f:
    patterns_data = yaml.safe_load(f)
patterns_text = "\n".join(
    f"- **{p['name']}**: {p['description']}\n  Beats: {', '.join(p['beats'])}"
    for p in patterns_data["patterns"]
)
if patterns_data.get("allow_custom"):
    patterns_text += "\n\nYou may also propose a custom pattern if none of the above fit."
```

Then add `"narrative_patterns": patterns_text` to the `variables` dict.

For the playbook runner references (lines 1080, 1443), update the prompt filename from `story_frameworks/analyze_v2.md` to `story_frameworks/analyze_v3.md` and add the same patterns loading.

**Step 3: Run existing story framework tests**

Run: `pytest tests/ -k "story_framework or framework" -v`
Expected: Any existing tests that assert the old 4-field structure will fail — update them to use the new flexible beats schema.

**Step 4: Fix any failing existing tests**

Update existing tests to use the new schema format (structure_name + beats instead of entry_point/tension/turn/landing).

**Step 5: Commit**

```bash
git add prompts/story_frameworks/analyze_v3.md src/app.py tests/
git commit -m "prompt: story frameworks v3 — LLM selects narrative pattern per subject"
```

---

### Task 5: Verify backward compatibility with existing module

**Objective:** The existing `modules/stackpenni/story-frameworks.md` (v1.0 with old format) should still be readable by the drafter without breaking.

**Files:**
- Verify: `prompts/draft/generate_v2.md` — the `{story_frameworks}` variable injection still works because it's just markdown text

**Step 1: Verify the drafter prompt doesn't assume specific beat names**

Read `prompts/draft/generate_v2.md` lines 35-37 — it just injects `{story_frameworks}` as a markdown block. The LLM reads whatever structure is there. No code changes needed — the drafter naturally adapts to whatever beats are in the module.

**Step 2: Run full test suite**

Run: `pytest tests/ -q`
Expected: All tests pass (665+)

**Step 3: Commit if any test fixes were needed**

---

### Task 6: Add test for narrative pattern selection diversity

**Objective:** Ensure the LLM doesn't pick the same pattern for every subject.

**Files:**
- Add to: `tests/test_narrative_patterns.py`

**Step 1: Write test**

```python
def test_story_frameworks_schema_allows_multiple_structures():
    """Multiple frameworks in one output can have different structure_names."""
    from module_store import STORY_FRAMEWORKS_SCHEMA
    import jsonschema
    
    data = {
        "frameworks": [
            {
                "subject_type": "AI",
                "structure_name": "myth_buster",
                "beats": [{"name": "myth", "content": "x"}, {"name": "reality", "content": "y"},
                          {"name": "proof", "content": "z"}, {"name": "takeaway", "content": "w"}],
                "grounded_in_example": "", "grounded_in_story": "",
                "voice_compatible": True, "voice_note": "",
            },
            {
                "subject_type": "wealth",
                "structure_name": "how_to",
                "beats": [{"name": "problem", "content": "x"}, {"name": "steps", "content": "y"},
                          {"name": "result", "content": "z"}],
                "grounded_in_example": "", "grounded_in_story": "",
                "voice_compatible": True, "voice_note": "",
            },
        ],
        "summary": "test",
    }
    jsonschema.validate(data, STORY_FRAMEWORKS_SCHEMA)  # should not raise
```

**Step 2: Run and verify pass**

Run: `pytest tests/test_narrative_patterns.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_narrative_patterns.py
git commit -m "test: verify multiple narrative structures can coexist"
```

---

## Feature 2: Onboarding Completeness Dashboard + Source Mining

### Background

During onboarding, 188 materials were uploaded but all show 0 chars of normalized content. The dependent playbook runs (viral-patterns-starter, voice-profile-builder) stayed "pending" — never completed. The story frameworks analysis ran with all blank inputs because the upstream playbooks didn't finish. The onboarding conversation has rich data (Brand Strategy Lock Sheet, operator stories) but none was extracted into structured fields.

The problem is two-fold: (1) no visibility into what's missing, and (2) no way to fill gaps from existing data.

### Design

**Part A — Completeness Dashboard:** A new page/section that declares each module's required inputs (from the playbook `## Inputs` section), checks what's been collected vs what's missing, and shows the gap.

**Part B — Source Mining:** For each missing input, the operator can either type it directly or click "Find in my sources" — the AI runs a targeted extraction LLM call against uploaded materials, onboarding transcript, and source bank to find the missing info.

---

### Task 7: Add required_inputs to playbook frontmatter

**Objective:** Make playbook input requirements machine-readable so the dashboard can check them.

**Files:**
- Modify: `playbooks/story-frameworks-starter.md` — add `required_inputs` frontmatter
- Modify: `playbooks/viral-patterns-starter.md`
- Modify: `playbooks/voice-profile-builder.md`
- Modify: `playbooks/audience-insights-builder.md`
- Modify: `playbooks/format-guide-starter.md`
- Modify: `playbooks/visual-style-intake.md`
- Modify: `playbooks/business-profile-intake.md`
- Modify: `src/playbook_runner.py:42-53` — add `required_inputs` to Playbook dataclass
- Modify: `src/playbook_runner.py:60-100` — parse `required_inputs` from frontmatter

**Step 1: Add frontmatter to each playbook**

For `story-frameworks-starter.md`, add after the display_label comment:

```markdown
<!-- required_inputs: admired_examples, operator_stories, voice_summary -->
```

For `viral-patterns-starter.md`:
```markdown
<!-- required_inputs: admired_links, anti_examples, top_performers -->
```

For `voice-profile-builder.md`:
```markdown
<!-- required_inputs: voice_samples, tone_redlines -->
```

For `audience-insights-builder.md`:
```markdown
<!-- required_inputs: audience_description, audience_data, admired_signals -->
```

For `format-guide-starter.md`:
```markdown
<!-- required_inputs: platform_list, format_observations, platform_norms -->
```

For `visual-style-intake.md`:
```markdown
<!-- required_inputs: photo_library, brand_assets, visual_examples, platform_list -->
```

For `business-profile-intake.md`:
```markdown
<!-- required_inputs: business_qa -->
```

**Step 2: Add required_inputs to Playbook dataclass**

In `src/playbook_runner.py`, add field:

```python
required_inputs: list[str] = field(default_factory=list)  # machine-readable input keys
```

**Step 3: Parse required_inputs in PlaybookParser**

In `PlaybookParser.parse()`, add after display_label parsing:

```python
# Extract required_inputs from comment
required_inputs_match = re.search(r'<!--\s*required_inputs:\s*(.+?)\s*-->', content)
required_inputs = []
if required_inputs_match:
    required_inputs = [s.strip() for s in required_inputs_match.group(1).split(",")]
```

And set it on the Playbook object.

**Step 4: Write test**

```python
def test_playbook_parser_reads_required_inputs():
    from playbook_runner import PlaybookParser
    pb = PlaybookParser.parse("playbooks/story-frameworks-starter.md")
    assert "admired_examples" in pb.required_inputs
    assert "operator_stories" in pb.required_inputs
    assert "voice_summary" in pb.required_inputs
```

**Step 5: Run test, verify pass, commit**

```bash
git add playbooks/ src/playbook_runner.py tests/
git commit -m "playbooks: machine-readable required_inputs frontmatter"
```

---

### Task 8: Build completeness check function

**Objective:** Create a function that checks each module's required inputs against what's been collected.

**Files:**
- Create: `src/onboarding_completeness.py`

**Step 1: Write the function**

```python
"""Onboarding completeness checker — surfaces missing inputs per module."""
import json
import os
from playbook_runner import PlaybookParser, PlaybookRunner


# Maps required_input keys to their source playbook and collected_inputs key
INPUT_SOURCE_MAP = {
    "admired_examples": {"playbook": "viral-patterns-starter", "collected_key": "story_admired_refs"},
    "operator_stories": {"playbook": "story-frameworks-starter", "collected_key": "operator_stories"},
    "voice_summary": {"playbook": "voice-profile-builder", "collected_key": "voice_summary"},
    "audience_description": {"playbook": "business-profile-intake", "collected_key": "business_qa"},
    "audience_data": {"playbook": "audience-insights-builder", "collected_key": "audience_data"},
    "admired_signals": {"playbook": "audience-insights-builder", "collected_key": "admired_signals"},
    "admired_links": {"playbook": "viral-patterns-starter", "collected_key": "admired_links"},
    "anti_examples": {"playbook": "viral-patterns-starter", "collected_key": "anti_examples"},
    "top_performers": {"playbook": "viral-patterns-starter", "collected_key": "top_performers"},
    "voice_samples": {"playbook": "voice-profile-builder", "collected_key": "voice_samples"},
    "tone_redlines": {"playbook": "voice-profile-builder", "collected_key": "tone_redlines"},
    "business_qa": {"playbook": "business-profile-intake", "collected_key": "business_qa"},
    "platform_list": {"playbook": "business-profile-intake", "collected_key": "platform_list"},
    "format_observations": {"playbook": "format-guide-starter", "collected_key": "format_observations"},
    "platform_norms": {"playbook": "format-guide-starter", "collected_key": "platform_norms"},
    "photo_library": {"playbook": "visual-style-intake", "collected_key": "photo_library"},
    "brand_assets": {"playbook": "visual-style-intake", "collected_key": "brand_assets"},
    "visual_examples": {"playbook": "visual-style-intake", "collected_key": "visual_examples"},
}


def check_completeness(db_path: str, playbooks_dir: str, business_slug: str) -> list[dict]:
    """Check each playbook's required inputs against collected inputs.
    
    Returns a list of dicts:
    {
        "playbook": "story-frameworks-starter",
        "display_label": "Story Frameworks",
        "inputs": [
            {"name": "admired_examples", "status": "missing|present|inferred", 
             "source_playbook": "viral-patterns-starter", "value": "..."},
        ]
    }
    """
    runner = PlaybookRunner(db_path)
    runs = runner.list_runs()
    
    # Build a map of playbook_name → collected_inputs
    collected_by_playbook = {}
    for run in runs:
        run_dict = dict(run)
        collected = json.loads(run_dict.get("collected_inputs") or "{}")
        collected_by_playbook[run_dict["playbook_name"]] = collected
    
    # Also check the main onboarding run
    # (it collects into a shared pool that downstream playbooks draw from)
    
    results = []
    for pb_file in sorted(os.listdir(playbooks_dir)):
        if not pb_file.endswith(".md"):
            continue
        pb_path = os.path.join(playbooks_dir, pb_file)
        playbook = PlaybookParser.parse(pb_path)
        
        if not playbook.required_inputs:
            continue
        
        pb_collected = collected_by_playbook.get(playbook.name, {})
        input_statuses = []
        
        for req_key in playbook.required_inputs:
            source_info = INPUT_SOURCE_MAP.get(req_key, {})
            collected_key = source_info.get("collected_key", req_key)
            
            # Check if this input exists in the playbook's own collected_inputs
            # or in the onboarding run's collected_inputs
            value = pb_collected.get(collected_key)
            if value is None:
                # Check onboarding run
                onboarding_collected = collected_by_playbook.get("onboarding", {})
                value = onboarding_collected.get(collected_key)
            
            if value and str(value).strip():
                status = "present"
            else:
                status = "missing"
            
            input_statuses.append({
                "name": req_key,
                "status": status,
                "source_playbook": source_info.get("playbook", ""),
                "collected_key": collected_key,
            })
        
        results.append({
            "playbook": playbook.name,
            "display_label": playbook.display_label or playbook.name,
            "inputs": input_statuses,
        })
    
    return results
```

**Step 2: Write tests**

```python
def test_completeness_check_finds_missing_inputs(tmp_path):
    """Completeness check should flag missing inputs."""
    from onboarding_completeness import check_completeness
    # This test uses the real DB and playbooks dir
    results = check_completeness("data/viralfactory.db", "playbooks", "stackpenni")
    assert len(results) > 0
    
    # Find story frameworks
    sf = next(r for r in results if r["playbook"] == "story-frameworks-starter")
    missing = [i for i in sf["inputs"] if i["status"] == "missing"]
    assert len(missing) > 0  # We know admired_examples, operator_stories, voice_summary are missing
```

**Step 3: Run test, verify pass, commit**

```bash
git add src/onboarding_completeness.py tests/
git commit -m "feat: onboarding completeness checker — surfaces missing inputs"
```

---

### Task 9: Build completeness dashboard route and template

**Objective:** New page at `/onboarding-health` that shows the completeness matrix.

**Files:**
- Modify: `src/app.py` — add route `/onboarding-health`
- Create: `src/templates/onboarding_health.html`

**Step 1: Add the route**

In `src/app.py`, add:

```python
@app.route("/onboarding-health")
def onboarding_health():
    """Module Health — shows completeness of onboarding inputs per module."""
    business_slug = _get_business_slug()
    if not business_slug:
        return "Business not configured", 500
    
    from onboarding_completeness import check_completeness
    results = check_completeness(
        app.config["DB_PATH"],
        app.config["PLAYBOOKS_DIR"],
        business_slug,
    )
    
    # Count summary
    total_inputs = sum(len(r["inputs"]) for r in results)
    missing_count = sum(1 for r in results for i in r["inputs"] if i["status"] == "missing")
    present_count = total_inputs - missing_count
    
    return render_template("onboarding_health.html",
        modules=results,
        total_inputs=total_inputs,
        missing_count=missing_count,
        present_count=present_count,
    )
```

**Step 2: Write the template**

Create `src/templates/onboarding_health.html` following the existing vf.css design system:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="/static/vf.css">
    <title>Module Health — {{ business_name }}</title>
    <script src="/static/busy.js"></script>
</head>
<body>
<div class="container">
    <div class="nav">
        <a href="/">Home</a>
        <a href="/ideas">Researcher (Ideas)</a>
        <a href="/create">Writer (Script)</a>
        <a href="/assemble">Assembler (Studio)</a>
        <a href="/published">Analyst (Learnings)</a>
        <a href="/onboard">Onboard</a>
        <a href="/onboarding-health" class="active">Module Health</a>
        <a href="/library">Library</a>
        <a href="/materials">Materials</a>
        <a href="/sources">Source Bank</a>
    </div>

    <h1>Module Health</h1>
    <p class="subtle">{{ present_count }}/{{ total_inputs }} inputs collected · {{ missing_count }} missing</p>

    <div class="card-list">
        {% for module in modules %}
        <div class="pipeline-card">
            <div class="card-header">
                <div class="card-title">{{ module.display_label }}</div>
                <span class="state-badge st-{{ 'all_approved' if (module.inputs | selectattr('status', 'equalto', 'missing') | list | length) == 0 else 'pending' }}">
                    {{ (module.inputs | selectattr('status', 'equalto', 'missing') | list | length) }} missing
                </span>
            </div>
            <div style="margin-top: 8px;">
                {% for inp in module.inputs %}
                <div style="display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 0.85rem;">
                    <span style="width: 8px; height: 8px; border-radius: 50%; background: {{ '#4A7C3A' if inp.status == 'present' else '#D8D4C8' }};"></span>
                    <span style="color: {{ '#1A1A1A' if inp.status == 'present' else '#8A857C' }};">
                        {{ inp.name | replace('_', ' ') }}
                    </span>
                    {% if inp.status == 'missing' %}
                    <span style="margin-left: auto; display: flex; gap: 6px;">
                        <button class="btn btn-secondary" style="font-size: 0.75rem; padding: 2px 10px;"
                                onclick="fillFromSources('{{ inp.name }}', '{{ inp.source_playbook }}')">Find in sources</button>
                        <button class="btn btn-secondary" style="font-size: 0.75rem; padding: 2px 10px;"
                                onclick="fillManual('{{ inp.name }}')">Enter manually</button>
                    </span>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
        </div>
        {% endfor %}
    </div>
</div>

<script>
function fillFromSources(inputName, sourcePlaybook) {
    // POST to /api/onboarding/mine-sources with the input name
    // AI scans materials, onboarding transcript, source bank
    busyAction(null, '/api/onboarding/mine-sources', {
        busyLabel: 'Mining sources…',
        body: JSON.stringify({input_name: inputName, source_playbook: sourcePlaybook}),
        reloadOnSuccess: true,
    });
}

function fillManual(inputName) {
    // Simple prompt — operator types the value
    var value = prompt('Enter value for ' + inputName.replace(/_/g, ' ') + ':');
    if (!value) return;
    busyAction(null, '/api/onboarding/fill-input', {
        busyLabel: 'Saving…',
        body: JSON.stringify({input_name: inputName, value: value}),
        reloadOnSuccess: true,
    });
}
</script>
</body>
</html>
```

**Step 3: Add nav link to existing templates**

Add `<a href="/onboarding-health">Module Health</a>` to the nav in key templates (or add to the onboarding page).

**Step 4: Run test suite**

Run: `pytest tests/ -q`
Expected: All pass (new route doesn't break anything)

**Step 5: Commit**

```bash
git add src/app.py src/templates/onboarding_health.html
git commit -m "UI: onboarding module health dashboard — surfaces missing inputs"
```

---

### Task 10: Build source mining API endpoint

**Objective:** `POST /api/onboarding/mine-sources` — AI scans uploaded materials, onboarding transcript, and source bank for a specific missing input.

**Files:**
- Modify: `src/app.py` — add route
- Create: `prompts/onboarding/mine_source_v1.md` — extraction prompt

**Step 1: Write the extraction prompt**

Create `prompts/onboarding/mine_source_v1.md`:

```markdown
<!-- version: 1.0 -->
# Source Mining — Extract Missing Onboarding Input

You are mining existing data to fill a missing onboarding input.

## What we're looking for

The operator needs: **{input_name}** (normally provided by the {source_playbook} playbook)

Description of what this input should contain:
{input_description}

## Available data sources

### Onboarding conversation transcript
{conversation_transcript}

### Uploaded materials (first 8000 chars combined)
{materials_content}

### Source Bank entries
{source_bank_entries}

## Your task

Search through all the data above for content relevant to "{input_name}". Extract:
1. Any direct references to this input
2. Any content that could serve as this input
3. Specific quotes, links, or examples you find

If you find relevant content, return it as structured text. If nothing relevant exists, say so honestly.

## Output format

```json
{
    "found": true,
    "extracted_content": "string — the mined content, formatted and ready to use",
    "sources_found": ["string — list of where this was found (material IDs, message references, source IDs)"],
    "confidence": "high|medium|low"
}
```
```

**Step 2: Add the API route**

In `src/app.py`:

```python
@app.route("/api/onboarding/mine-sources", methods=["POST"])
def mine_sources():
    """Mine existing data (materials, onboarding transcript, source bank) for a missing onboarding input."""
    business_slug = _get_business_slug()
    if not business_slug:
        return jsonify({"error": "Business not configured"}), 500
    
    input_name = request.json.get("input_name", "")
    source_playbook = request.json.get("source_playbook", "")
    if not input_name:
        return jsonify({"error": "No input name provided"}), 400
    
    # Gather data sources
    # 1. Onboarding transcript
    runner = PlaybookRunner(app.config["DB_PATH"])
    onboarding_run = None
    for run in runner.list_runs():
        if dict(run).get("playbook_name") == "onboarding":
            onboarding_run = dict(run)
            break
    
    conversation_transcript = ""
    if onboarding_run:
        collected = json.loads(onboarding_run.get("collected_inputs") or "{}")
        messages = collected.get("session_messages", "")
        if isinstance(messages, str):
            conversation_transcript = messages[:10000]
        elif isinstance(messages, list):
            conversation_transcript = "\n".join(str(m) for m in messages)[:10000]
    
    # 2. Uploaded materials (normalized_content)
    from materials import MaterialsIntake
    intake = MaterialsIntake(app.config["DB_PATH"])
    materials = intake.list_materials()  # all materials
    materials_content = ""
    for m in materials[:20]:  # cap at 20 materials
        content = m.get("normalized_content") or m.get("raw_content") or ""
        if content:
            materials_content += f"--- Material {m['id']} ({m.get('filename','')}) ---\n{content[:800]}\n\n"
    if not materials_content:
        materials_content = "(no material content available)"
    
    # 3. Source bank entries
    store = _get_pipeline_store()
    active_sources = store.list_sources(business_slug, limit=30)
    source_bank_entries = "\n".join(
        f"[S{s['id']}] {s['title']} — {s.get('summary','')}"
        for s in active_sources
    ) if active_sources else "(no sources in bank)"
    
    # Input description map
    input_descriptions = {
        "admired_examples": "Links to content the operator admires in their domain — creators, posts, videos they wish they'd made",
        "operator_stories": "2-3 stories the operator tells often — about their business, life, or take on things",
        "voice_summary": "Summary of the operator's voice characteristics — tone, vocabulary, style preferences",
        "admired_links": "5-10 links to content the operator admires",
        "anti_examples": "3-5 examples of content the operator considers slop they'd never make",
        "voice_samples": "Voice samples — typed or spoken content showing the operator's natural voice",
        "tone_redlines": "Topics or stances the operator never wants to take",
    }
    
    # LLM call
    try:
        config = load_all(app.config["CONFIG_DIR"])
        models_config = config["models"]
    except ConfigError as e:
        return jsonify({"error": f"Config error: {e}"}), 500
    
    from llm_adapter import LLMAdapter
    adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")
    
    result = adapter.complete(
        prompt_file="onboarding/mine_source_v1.md",
        variables={
            "input_name": input_name,
            "source_playbook": source_playbook,
            "input_description": input_descriptions.get(input_name, input_name),
            "conversation_transcript": conversation_transcript,
            "materials_content": materials_content[:8000],
            "source_bank_entries": source_bank_entries,
        },
        backend="default",
        context=f"Source mining for {input_name} ({source_playbook})",
        business_slug=business_slug,
    )
    
    # If found, save to the onboarding run's collected_inputs
    if result.get("found"):
        onboarding_run_id = onboarding_run["id"] if onboarding_run else None
        if onboarding_run_id:
            collected = json.loads(onboarding_run.get("collected_inputs") or "{}")
            collected[input_name] = result.get("extracted_content", "")
            runner.update_run(onboarding_run_id, collected_inputs=json.dumps(collected))
    
    return jsonify({
        "status": "ok",
        "found": result.get("found", False),
        "extracted_content": result.get("extracted_content", ""),
        "sources_found": result.get("sources_found", []),
        "confidence": result.get("confidence", "low"),
    })
```

**Step 3: Write test**

```python
def test_mine_sources_endpoint(client):
    """The source mining endpoint should return found content or honest not-found."""
    response = client.post("/api/onboarding/mine-sources",
                         json={"input_name": "operator_stories", "source_playbook": "story-frameworks-starter"})
    assert response.status_code == 200
    data = response.get_json()
    assert "found" in data
    assert "extracted_content" in data
```

**Step 4: Run test, verify, commit**

```bash
git add src/app.py prompts/onboarding/mine_source_v1.md tests/
git commit -m "API: source mining endpoint — AI extracts missing onboarding inputs from existing data"
```

---

### Task 11: Build manual fill API endpoint

**Objective:** `POST /api/onboarding/fill-input` — operator types a value directly.

**Files:**
- Modify: `src/app.py` — add route

**Step 1: Add route**

```python
@app.route("/api/onboarding/fill-input", methods=["POST"])
def fill_input():
    """Manually fill a missing onboarding input."""
    business_slug = _get_business_slug()
    if not business_slug:
        return jsonify({"error": "Business not configured"}), 500
    
    input_name = request.json.get("input_name", "")
    value = request.json.get("value", "")
    if not input_name or not value:
        return jsonify({"error": "Both input_name and value are required"}), 400
    
    runner = PlaybookRunner(app.config["DB_PATH"])
    
    # Find the onboarding run
    onboarding_run = None
    for run in runner.list_runs():
        if dict(run).get("playbook_name") == "onboarding":
            onboarding_run = dict(run)
            break
    
    if not onboarding_run:
        return jsonify({"error": "No onboarding run found"}), 404
    
    collected = json.loads(onboarding_run.get("collected_inputs") or "{}")
    collected[input_name] = value
    runner.update_run(onboarding_run["id"], collected_inputs=json.dumps(collected))
    
    return jsonify({"status": "ok", "input_name": input_name})
```

**Step 2: Write test, run, commit**

```bash
git add src/app.py tests/
git commit -m "API: manual fill for missing onboarding inputs"
```

---

### Task 12: Add "Module Health" link to onboarding page and nav

**Objective:** Make the dashboard discoverable.

**Files:**
- Modify: `src/templates/onboard.html` — add a link/section pointing to `/onboarding-health`
- Modify: nav sections in key templates — add `<a href="/onboarding-health">Module Health</a>`

**Step 1: Add link to onboarding page**

In `onboard.html`, add after the main content:

```html
<div style="margin-top: 20px;">
    <a href="/onboarding-health" class="btn btn-secondary">Check module health →</a>
</div>
```

**Step 2: Add to nav in all templates that have the nav bar**

Add `<a href="/onboarding-health">Module Health</a>` to the nav in: `index.html`, `ideas.html`, `create.html`, `assemble.html`, `assets.html`, `published.html`, `onboard.html`, `materials.html`, `sources.html`, `proposals.html`, `onboarding_health.html`.

**Step 3: Run test suite, verify, commit**

```bash
git add src/templates/
git commit -m "UI: add Module Health link to nav and onboarding page"
```

---

### Task 13: Full integration test and verification

**Objective:** Verify both features work end-to-end.

**Step 1: Run full test suite**

Run: `pytest tests/ -q`
Expected: All tests pass (665+ + new tests)

**Step 2: Restart service and verify pages load**

```bash
sudo systemctl restart viralfactory
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9121/onboarding-health
# Expected: 200
```

**Step 3: Verify the completeness dashboard shows real missing inputs**

```bash
curl -s http://127.0.0.1:9121/onboarding-health | grep -o 'missing'
# Should show multiple missing inputs
```

**Step 4: Test source mining endpoint**

```bash
curl -s -X POST http://127.0.0.1:9121/api/onboarding/mine-sources \
  -H 'Content-Type: application/json' \
  -d '{"input_name": "operator_stories", "source_playbook": "story-frameworks-starter"}' | python3 -m json.tool
```

**Step 5: Commit and push**

```bash
git add -A
git commit -m "verify: both features tested end-to-end"
git push origin main
```

---

### Task 14: Update CHANGELOG and PROGRESS docs

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/PROGRESS.md`

**Step 1: Add CHANGELOG entry**

```markdown
### 2026-07-04 STRUCTURE — Flexible narrative patterns + onboarding completeness

**Feature 1: Config-driven narrative patterns**
- Replaced hardcoded entry_point/tension/turn/landing with config-driven patterns
- New `config/narrative_patterns.yaml` with 8 default patterns (dramatic_arc, myth_buster, how_to, hot_take, listicle, before_after, receipt_card, pattern_breaker)
- LLM selects best pattern per subject type, or proposes custom
- Schema updated to flexible structure_name + beats[{name, content}]
- Story frameworks prompt v3 with pattern selection
- Backward compatible — old v1 modules still readable by drafter

**Feature 2: Onboarding completeness dashboard**
- New `/onboarding-health` page showing missing inputs per module
- Machine-readable `required_inputs` frontmatter added to all 7 playbooks
- Source mining API: AI extracts missing inputs from uploaded materials, onboarding transcript, source bank
- Manual fill API: operator types missing values directly
- Makes onboarding gaps visible and fillable without re-running entire onboarding
```

**Step 2: Commit and push**

```bash
git add CHANGELOG.md docs/PROGRESS.md
git commit -m "docs: changelog + progress for narrative patterns and onboarding completeness"
git push origin main
```