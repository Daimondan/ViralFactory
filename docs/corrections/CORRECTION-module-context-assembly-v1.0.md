# CORRECTION: Module Context Assembly — Section-Addressable Modules with Per-Prompt View Maps

**Version:** 1.0
**Status:** Approved by operator — ready for implementation
**Supersedes:** Nothing (new subsystem). Removes the inline `[:2000]` / `[:3000]` / `[:1500]` character slices in `src/app.py`.
**Depends on:** Nothing blocking. Independent of the session-memory corrections and the single-thread onboarding work.
**Priority:** P1 — quality degradation is silent and worsens as modules grow. Not a crash, but every pipeline LLM call is affected.

---

## 1. Problem

Every pipeline prompt (ideas, draft, fan-out, edit plan) receives modules as raw character slices:

```python
"viral_patterns": modules.get("viral-patterns", "(not built)")[:2000],
```

This is positional truncation, not selection. It keeps whatever happens to sit at the top of the module file, cuts mid-sentence, gives the LLM no signal that the document is partial, and logs nothing. As the living modules grow through the learning loop, the slice keeps a shrinking and arbitrary fraction. Raising the budget (2000 → 3000 → 4000) only moves the cliff.

The deeper issue: the unit of prompt assembly is currently "the whole module document," when different prompts need different **projections** of the same module:

| Consumer | What it actually needs |
|---|---|
| `ideas/generate_v1` | Breadth: format *index* (names + one-liners), pattern names, audience tensions. Menus, not specs. |
| `draft/generate_v2` | Scoped depth: the **full entry** for the one format the treatment chose; the voice profile and Tells Checklist in full; relevant frameworks. |
| `assets/fan_out_v2` | Per-platform adjustment rules only. |
| `assembly/edit_plan_v1` | Visual Style caption/pacing rules; format skeleton. |

`_extract_tells_checklist()` in `src/app.py` is this exact move already done once, ad hoc, with a regex. This correction makes it the system.

## 2. Ruling (architectural decisions — do not relitigate in implementation)

1. **No LLM summarization in the context-assembly path.** A call-time summarizer creates an ungated derivative of a human-gated module, adds cost/latency, and creates a cache-invalidation problem. The living-document curation loop (learning proposals → operator gate) *is* the compressor.
2. **No embedding retrieval for modules.** Modules contain **rules**, which are task-typed, not topic-typed — dialect rules apply to every draft regardless of subject; a similarity query against a specific idea would score them near zero and drop them. Relevance and importance are different axes; retrieval measures only the first. (Retrieval remains a legitimate *future* track for the Source Bank, which contains **material** — topical by nature. See §8 CONTEXT.md addition.)
3. **Selection is structural and deterministic.** Section-addressable modules + a declared per-prompt view map. No judgment calls at assembly time; full provenance of what each call saw.
4. **Importance is a gated attribute, not a runtime inference.** The format lifecycle (experimental/proven/retired) is the template: prompts read tiers that humans approved. As other modules grow, the learning loop proposes tiering/pruning and the operator gates it.
5. **Hard ceiling stays, as a tripwire only.** With an explicit truncation marker and a provenance log entry. Once selection is structural it should almost never fire.
6. **The human-facing module stays one readable markdown file.** Section addressing is a projection layer at read time. No storage format change, no migration of existing module files.

## 3. Heading contract

The `*_to_markdown` generators in `src/module_store.py` already emit stable headings. Codify them as a contract:

- **Sections** are `## Heading` blocks. A section spans from its `##` line to the next `##` line (subsections `###`+ are included within their parent section).
- **Entries** are `### Name` blocks inside a designated parent section (currently only Format Guide: entries live under `## Formats`, keyed by exact `format_name`).
- Heading matching is case-insensitive, whitespace-normalized. Fenced code blocks are skipped by the parser (a `## ` inside a skeleton fence is not a heading).
- **Renaming or removing a `##` heading in a `*_to_markdown` generator is a breaking change** and must be accompanied by a view-map update in the same commit. Add a comment to that effect above each generator.

Known section inventory (from current generators — verify against code at implementation time):

- `voice-profile`: Identity line, Audience, Positive patterns, Dialect & register, Anti-patterns, Tells Checklist, Provenance
- `format-guide`: Summary, Formats (entry container), Decision table, Provenance
- Other modules: implement the parser generically; declare their sections in the view map as needed.

## 4. Implementation

### 4.1 `ModuleStore` additions (`src/module_store.py`)

```python
def get_section(self, business_slug: str, module_name: str,
                heading: str) -> Optional[str]:
    """Return the text of one ## section (heading line included,
    subsections included). None if module or section missing.
    Deterministic parse; cached in-process keyed on file mtime."""

def get_entry(self, business_slug: str, module_name: str,
              parent_section: str, entry_name: str) -> Optional[str]:
    """Return one ### entry inside a parent ## section.
    Exact-match on normalized entry_name. None if absent."""

def get_index(self, business_slug: str, module_name: str,
              parent_section: str) -> Optional[str]:
    """Return a generated index of a container section: one line per
    ### entry — the entry name plus its first list line or sentence
    (for Format Guide: name + platforms + status). Deterministic."""
```

Parser rules: split on `\n## ` outside code fences; within a section, split entries on `\n### `. No regex fragility beyond that — this is line-structural parsing.

### 4.2 View map — `prompts/views.yaml`

Lives beside the prompts so it versions with them. Declares, per prompt file, which module projections feed which template variables. `{treatment.format_name}` is a dynamic key resolved at call time.

```yaml
# prompts/views.yaml — module context view map (v1.0)
# section: one ## block   entry: one ### under a parent   index: generated entry list
# full: entire module     Budgets in chars, per projection, boundary-enforced by design.

ideas/generate_v1.md:
  viral_patterns:     {module: viral-patterns,   mode: full,  budget: 6000}
  audience_insights:  {module: audience-insights, mode: full, budget: 4000}
  story_frameworks:   {module: story-frameworks, mode: full,  budget: 4000}
  format_guide:       {module: format-guide,     mode: index, parent: Formats, budget: 3000}

draft/generate_v2.md:
  voice_profile:      {module: voice-profile,    mode: full,  budget: 8000}
  tells_checklist:    {module: voice-profile,    mode: section, heading: Tells Checklist, budget: 2000}
  story_frameworks:   {module: story-frameworks, mode: full,  budget: 5000}
  audience_insights:  {module: audience-insights, mode: full, budget: 4000}
  viral_patterns:     {module: viral-patterns,   mode: full,  budget: 5000}
  visual_style:       {module: visual-style,     mode: full,  budget: 5000}
  format_guide:       {module: format-guide,     mode: entry, parent: Formats,
                       key: "{treatment.format_name}", budget: 4000,
                       fallback: index}

assets/fan_out_v2.md:
  visual_style:       {module: visual-style,     mode: section, heading: Platform adjustments, budget: 2000,
                       fallback: full}

assembly/edit_plan_v1.md:
  viral_patterns:     {module: viral-patterns,   mode: full,  budget: 3000}
  format_guide:       {module: format-guide,     mode: entry, parent: Formats,
                       key: "{format_name}", budget: 3000, fallback: index}
  visual_style:       {module: visual-style,     mode: full,  budget: 4000}
```

Notes:
- Budgets above are deliberately generous (all-in per prompt is still well under the drafter's context). They are **tripwires**, not sizing tools. Tune freely.
- `fallback` defines behavior when the addressed section/entry is missing: `index` (Format Guide), `full` (small modules), or omit → explicit `"(section 'X' not found in module Y)"` string is injected so the model and the provenance log both see the degradation. **Never silently inject an empty string.**
- Fan-out `visual_style` is *added* by this correction — fan-out currently produces per-platform image prompts with no Visual Style input at all; it only sees the draft's visual_direction JSON. Add `{visual_style}` to `assets/fan_out_v2.md` (bump to v2.1) under a heading `## Visual Style (platform adjustments)`.

### 4.3 Assembler — new `src/context_assembly.py`

```python
def assemble_module_context(prompt_file: str, business_slug: str,
                            dynamic: dict = None,
                            db_path: str = ..., modules_dir: str = "modules") -> dict:
    """Resolve the view map for prompt_file into a dict of
    {template_variable: text}. Applies mode (full/section/entry/index),
    resolves dynamic keys, applies fallbacks, enforces budgets at the
    nearest paragraph boundary BELOW the budget with an explicit
    '[module truncated: shown N of M chars]' marker, and returns a
    parallel provenance summary (see 4.4)."""
```

Call sites in `src/app.py` (`ideas_generate`, `_generate_card_from_seed`, `draft_generate`, `assets_fan_out`, `generate_edit_plan`) replace their inline slice blocks with one `assemble_module_context(...)` call merged into `variables`. `_extract_tells_checklist()` is deleted — replaced by the `tells_checklist` view entry. `_load_all_modules()` remains for any non-pipeline consumers but pipeline routes stop using it directly.

Dynamic keys: `draft_generate` passes `dynamic={"treatment.format_name": format_name}`; `generate_edit_plan` passes `dynamic={"format_name": draft.get("format")}`.

### 4.4 Provenance

Each `assemble_module_context` call produces a compact summary string, e.g.
`voice-profile:full(7412) | format-guide:entry(Street Receipt,2210) | viral-patterns:full(4980,TRUNCATED)`
Append it to the `context` field of the existing `adapter.complete(...)` provenance logging (do not add a new table). Any `TRUNCATED` or `NOT_FOUND` marker in the summary must also emit a `logger.warning`.

### 4.5 Prompt template changes

- `assets/fan_out_v2.md` → `v2.1`: add `{visual_style}` block (see 4.2 note).
- `draft/generate_v2.md` → `v2.1`: rename the Format Guide block heading from "the skeleton for this format" framing to reflect that it now receives **the single chosen format's full entry** (or the index as fallback). One-line wording change; the variable name `{format_guide}` is unchanged.
- No other template changes. `{tells_checklist}` already exists.

## 5. Out of scope (explicitly deferred — record, do not build)

- **Source Bank retrieval.** Material selection by similarity is the right long-term tool for the Source Bank as it grows unbounded. Separate future correction; do not conflate with module assembly.
- **Compile-time digest views.** If a single always-on section someday exceeds reason, an LLM digests it once per module version and the digest is **gated in the console** before any prompt may use it (no-ungated-derivatives principle). Escape valve only; not to be reached for first.
- **Tiering of Viral Patterns / other collection modules.** Handled through the learning loop as module-content proposals (tier attributes on entries), not through assembly code. The assembler will read tiers when they exist via the same section/entry machinery.

## 6. Acceptance tests

1. Parser: `get_section` returns Tells Checklist from a real voice-profile fixture; a `## ` inside a fenced skeleton block is not treated as a heading.
2. `get_entry` returns the correct format entry by name, case/whitespace-insensitive; missing entry → None.
3. `get_index` on Format Guide yields one line per format containing name and status.
4. Assembler resolves `draft/generate_v2.md` with a dynamic format_name → format-guide variable contains only that entry; provenance summary names it.
5. Missing section with no fallback → variable contains the explicit `(section not found)` string; warning logged.
6. Budget breach → truncation at a paragraph boundary below budget, marker appended, provenance flags TRUNCATED.
7. Grep gate: no `[:2000]`, `[:3000]`, `[:1500]`, `[:4000]` module slices remain in `src/app.py` pipeline routes.
8. Existing pipeline tests still pass with the assembler in place.

## 7. Suggested implementation order

1. Parser methods + tests (4.1, tests 1–3)
2. `views.yaml` + assembler + tests (4.2–4.3, tests 4–6)
3. Wire call sites, delete `_extract_tells_checklist`, provenance (4.4, tests 7–8)
4. Prompt bumps (4.5)

## 8. CONTEXT.md addition (copy verbatim)

> **Modules carry rules; the Source Bank carries material.** Rules are task-typed — they apply to every piece of a given kind regardless of topic — so prompt context from modules is selected *structurally* (declared sections/entries per prompt, `prompts/views.yaml`), never by call-time summarization or similarity retrieval. Call-time compression of a module would create an ungated derivative of a human-approved document; the curation loop (learning proposals → operator gate) is the only compressor. Material is topic-typed, so similarity retrieval is a legitimate future selector for the Source Bank specifically. Character ceilings on assembled module context exist only as logged tripwires, never as the selection mechanism.
