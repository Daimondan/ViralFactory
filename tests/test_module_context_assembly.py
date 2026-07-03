"""
Tests for CORRECTION-module-context-assembly:
- ModuleStore parser methods (get_section, get_entry, get_index)
- Context assembler (assemble_module_context)
- Wiring: no inline [:N] slices in pipeline routes

Acceptance tests 1-8 from the correction doc.
"""
import os
import sys
import tempfile
import shutil
import pytest

# Ensure src on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from module_store import ModuleStore


# ── Fixtures ──────────────────────────────────────────────────────────────────

VOICE_PROFILE_FIXTURE = """# Voice Profile — Test Brand — v1.0

## Identity line
We help people build real wealth, island style.

## Audience
Caribbean entrepreneurs 25-45 who are curious about AI but skeptical of hype.

## Positive patterns
- **[Rhythm]** Staccato one-liners that land hard
- **[Specificity]** Real numbers, not vague claims

## Dialect & register
- Bajan expressions used naturally
  - DO NOT SANITIZE

## Anti-patterns
- Generic "good writing"
  - Evidence of absence: never seen in the corpus

## Tells Checklist
- **No tricolon lists** — check for "X, Y, and Z" three-part rhythm
- **No "imagine" hooks** — check for "Imagine if you could..."
- **No AI summary endings** — check for "In conclusion" or "Ultimately"

## Provenance
- Version: 1.0
- Generated: 2026-01-01
- Schema: voice_profile_v1
"""

FORMAT_GUIDE_FIXTURE = """# Format Guide — v1.0

## Summary
A guide to formats that work for this brand.

## Formats

### Street Receipt
- **Platforms:** Instagram, X
- **Best for:** Quick takes, hot takes
- **Length:** 1-2 paragraphs
- **Status:** proven
- **Structure notes:** Punchy opening, evidence, sharp close

**Skeleton:**
```
[Hook line that stops the scroll]

## This is a sub-heading inside a skeleton

[Body with specific evidence]
[Sharp close]
```

### Thread Tear-Down
- **Platforms:** X
- **Best for:** Analysis, breakdowns
- **Length:** 5-8 tweets
- **Status:** experimental
- **Structure notes:** Numbered, each tweet stands alone

**Skeleton:**
```
1. [Hook tweet]
2-7. [Analysis tweets]
8. [CTA tweet]
```

### Carousel Story
- **Platforms:** Instagram
- **Best for:** Step-by-step guides
- **Length:** 7-10 slides
- **Status:** proven
- **Structure notes:** Each slide one idea

## Decision table
- **Announcement** on X → **Thread**
  - Rationale: threads get more reach for news

## Provenance
- Version: 1.0
- Schema: format_guide_v1
"""

VISUAL_STYLE_FIXTURE = """# Visual Style Guide — v1.0

## Summary
Vibrant, island-inspired visuals with clean typography.

## Palette
- **Primary:** Ocean Blue (#1a5a8a)
- **Secondary:** Sand (#e8d5a8)

## Typography
- **Feel:** Bold and confident
- **Weight:** Semibold headers, regular body

## Stylization level
Moderate — real footage anchors, generated visuals support.

## Blend rules
- **Real anchors:** street footage, product shots
- **Generated supporting:** backgrounds, illustrations

## Platform adjustments
- **Instagram** — 1:1: tighter crops, bolder text
- **X** — 16:9: wider composition, less text
- **TikTok** — 9:16: vertical-first, large captions

## Provenance
- Version: 1.0
- Schema: visual_style_v1
"""


@pytest.fixture
def temp_modules_dir():
    """Create a temp modules dir with fixture modules."""
    tmpdir = tempfile.mkdtemp()
    slug = "testbrand"
    biz_dir = os.path.join(tmpdir, slug)
    os.makedirs(biz_dir)
    with open(os.path.join(biz_dir, "voice-profile.md"), "w") as f:
        f.write(VOICE_PROFILE_FIXTURE)
    with open(os.path.join(biz_dir, "format-guide.md"), "w") as f:
        f.write(FORMAT_GUIDE_FIXTURE)
    with open(os.path.join(biz_dir, "visual-style.md"), "w") as f:
        f.write(VISUAL_STYLE_FIXTURE)
    yield tmpdir, slug
    shutil.rmtree(tmpdir)


# ── Test 1: get_section ───────────────────────────────────────────────────────

def test_get_section_returns_tells_checklist(temp_modules_dir):
    """Acceptance test 1: get_section returns Tells Checklist from voice-profile."""
    tmpdir, slug = temp_modules_dir
    store = ModuleStore(modules_dir=tmpdir)
    section = store.get_section(slug, "voice-profile", "Tells Checklist")
    assert section is not None
    assert "Tells Checklist" in section
    assert "No tricolon lists" in section
    assert "No \"imagine\" hooks" in section
    # Should NOT include the next section (Provenance)
    assert "Provenance" not in section


def test_get_section_heading_inside_code_fence_not_treated_as_heading(temp_modules_dir):
    """Acceptance test 1b: ## inside a fenced skeleton block is not a heading."""
    tmpdir, slug = temp_modules_dir
    store = ModuleStore(modules_dir=tmpdir)
    # The format guide skeleton has "## This is a sub-heading" inside a fence
    # Asking for it as a section should return None
    section = store.get_section(slug, "format-guide", "This is a sub-heading inside a skeleton")
    assert section is None  # it's inside a fence, not a real section


def test_get_section_missing_returns_none(temp_modules_dir):
    """get_section returns None for a missing section."""
    tmpdir, slug = temp_modules_dir
    store = ModuleStore(modules_dir=tmpdir)
    assert store.get_section(slug, "voice-profile", "Nonexistent Section") is None


def test_get_section_missing_module_returns_none(temp_modules_dir):
    """get_section returns None for a missing module."""
    tmpdir, slug = temp_modules_dir
    store = ModuleStore(modules_dir=tmpdir)
    assert store.get_section(slug, "nonexistent-module", "Anything") is None


def test_get_section_case_insensitive(temp_modules_dir):
    """Heading matching is case-insensitive."""
    tmpdir, slug = temp_modules_dir
    store = ModuleStore(modules_dir=tmpdir)
    section = store.get_section(slug, "voice-profile", "tells checklist")
    assert section is not None
    assert "No tricolon lists" in section


def test_get_section_whitespace_tolerant(temp_modules_dir):
    """Heading matching is whitespace-normalized."""
    tmpdir, slug = temp_modules_dir
    store = ModuleStore(modules_dir=tmpdir)
    section = store.get_section(slug, "voice-profile", "  Tells   Checklist  ")
    assert section is not None


# ── Test 2: get_entry ─────────────────────────────────────────────────────────

def test_get_entry_returns_correct_format(temp_modules_dir):
    """Acceptance test 2: get_entry returns the correct format entry by name."""
    tmpdir, slug = temp_modules_dir
    store = ModuleStore(modules_dir=tmpdir)
    entry = store.get_entry(slug, "format-guide", "Formats", "Street Receipt")
    assert entry is not None
    assert "Street Receipt" in entry
    assert "Instagram" in entry
    assert "proven" in entry
    # Should NOT include the next entry (Thread Tear-Down)
    assert "Thread Tear-Down" not in entry


def test_get_entry_case_insensitive(temp_modules_dir):
    """get_entry matches case-insensitively."""
    tmpdir, slug = temp_modules_dir
    store = ModuleStore(modules_dir=tmpdir)
    entry = store.get_entry(slug, "format-guide", "formats", "street receipt")
    assert entry is not None
    assert "Street Receipt" in entry


def test_get_entry_missing_returns_none(temp_modules_dir):
    """get_entry returns None for a missing entry."""
    tmpdir, slug = temp_modules_dir
    store = ModuleStore(modules_dir=tmpdir)
    assert store.get_entry(slug, "format-guide", "Formats", "Nonexistent Format") is None


def test_get_entry_missing_parent_returns_none(temp_modules_dir):
    """get_entry returns None for a missing parent section."""
    tmpdir, slug = temp_modules_dir
    store = ModuleStore(modules_dir=tmpdir)
    assert store.get_entry(slug, "format-guide", "Nonexistent", "Street Receipt") is None


# ── Test 3: get_index ──────────────────────────────────────────────────────────

def test_get_index_yields_one_line_per_format(temp_modules_dir):
    """Acceptance test 3: get_index on Format Guide yields one line per format with name + status."""
    tmpdir, slug = temp_modules_dir
    store = ModuleStore(modules_dir=tmpdir)
    index = store.get_index(slug, "format-guide", "Formats")
    assert index is not None
    assert "## Formats" in index  # section heading included
    assert "Street Receipt" in index
    assert "Thread Tear-Down" in index
    assert "Carousel Story" in index
    # Each format should have a one-line summary (the first content line which includes platforms)
    lines = index.split('\n')
    # Check that there are index entries (lines starting with "- ")
    entry_lines = [l for l in lines if l.startswith("- ")]
    assert len(entry_lines) == 3  # three formats


def test_get_index_missing_section_returns_none(temp_modules_dir):
    """get_index returns None for a missing section."""
    tmpdir, slug = temp_modules_dir
    store = ModuleStore(modules_dir=tmpdir)
    assert store.get_index(slug, "format-guide", "Nonexistent") is None


def test_get_index_missing_module_returns_none(temp_modules_dir):
    """get_index returns None for a missing module."""
    tmpdir, slug = temp_modules_dir
    store = ModuleStore(modules_dir=tmpdir)
    assert store.get_index(slug, "nonexistent-module", "Formats") is None


# ── Test 4-6: Assembler ────────────────────────────────────────────────────────

from context_assembly import assemble_module_context, _truncate_at_boundary, _resolve_dynamic_key

VIEWS_MAP = {
    "draft/generate_v2.md": {
        "voice_profile":    {"module": "voice-profile", "mode": "full", "budget": 8000},
        "tells_checklist":  {"module": "voice-profile", "mode": "section", "heading": "Tells Checklist", "budget": 2000},
        "format_guide":     {"module": "format-guide", "mode": "entry", "parent": "Formats",
                             "key": "{treatment.format_name}", "budget": 4000, "fallback": "index"},
        "visual_style":     {"module": "visual-style", "mode": "section", "heading": "Platform adjustments", "budget": 2000, "fallback": "full"},
    },
    "assembly/edit_plan_v1.md": {
        "format_guide":     {"module": "format-guide", "mode": "entry", "parent": "Formats",
                             "key": "{format_name}", "budget": 3000, "fallback": "index"},
    },
    "test/no_fallback.md": {
        "missing_var":      {"module": "voice-profile", "mode": "section", "heading": "Nonexistent Section", "budget": 2000},
    },
    "test/empty_module.md": {
        "empty_mod":        {"module": "nonexistent-module", "mode": "full", "budget": 2000},
    },
}


def test_assembler_resolves_entry_with_dynamic_key(temp_modules_dir):
    """Acceptance test 4: assembler resolves draft/generate_v2 with dynamic format_name."""
    tmpdir, slug = temp_modules_dir
    dynamic = {"treatment": {"format_name": "Street Receipt"}}
    variables, provenance = assemble_module_context(
        "draft/generate_v2.md", slug,
        dynamic=dynamic, modules_dir=tmpdir, view_map=VIEWS_MAP
    )
    # format_guide should contain only the Street Receipt entry
    assert "Street Receipt" in variables["format_guide"]
    assert "Thread Tear-Down" not in variables["format_guide"]
    # Provenance should name the entry
    assert "format-guide:entry" in provenance
    assert "Street Receipt" in provenance


def test_assembler_resolves_section(temp_modules_dir):
    """Assembler resolves a section projection (Tells Checklist)."""
    tmpdir, slug = temp_modules_dir
    dynamic = {"treatment": {"format_name": "Street Receipt"}}
    variables, provenance = assemble_module_context(
        "draft/generate_v2.md", slug,
        dynamic=dynamic, modules_dir=tmpdir, view_map=VIEWS_MAP
    )
    assert "No tricolon lists" in variables["tells_checklist"]
    assert "voice-profile:section" in provenance


def test_assembler_resolves_full(temp_modules_dir):
    """Assembler resolves a full projection."""
    tmpdir, slug = temp_modules_dir
    dynamic = {"treatment": {"format_name": "Street Receipt"}}
    variables, provenance = assemble_module_context(
        "draft/generate_v2.md", slug,
        dynamic=dynamic, modules_dir=tmpdir, view_map=VIEWS_MAP
    )
    assert "Identity line" in variables["voice_profile"]
    assert "voice-profile:full" in provenance


def test_assembler_fallback_to_index(temp_modules_dir):
    """Acceptance test 4b: missing entry with fallback:index falls back to the index."""
    tmpdir, slug = temp_modules_dir
    dynamic = {"treatment": {"format_name": "Nonexistent Format"}}
    variables, provenance = assemble_module_context(
        "draft/generate_v2.md", slug,
        dynamic=dynamic, modules_dir=tmpdir, view_map=VIEWS_MAP
    )
    # Should fall back to the index
    assert "Street Receipt" in variables["format_guide"]  # index lists all formats
    assert "index-fallback" in provenance or "full-fallback" in provenance


def test_assembler_missing_section_no_fallback_explicit_string(temp_modules_dir):
    """Acceptance test 5: missing section with no fallback → explicit (section not found) string."""
    tmpdir, slug = temp_modules_dir
    variables, provenance = assemble_module_context(
        "test/no_fallback.md", slug,
        modules_dir=tmpdir, view_map=VIEWS_MAP
    )
    assert "not found" in variables["missing_var"].lower()
    assert "NOT_FOUND" in provenance


def test_assembler_empty_module(temp_modules_dir):
    """Empty/missing module with full mode and no fallback."""
    tmpdir, slug = temp_modules_dir
    variables, provenance = assemble_module_context(
        "test/empty_module.md", slug,
        modules_dir=tmpdir, view_map=VIEWS_MAP
    )
    # No module → None from store.load, no fallback → (module not built) string
    assert "not built" in variables["empty_mod"].lower() or "NOT_FOUND" in provenance


def test_assembler_budget_truncation_with_marker(temp_modules_dir):
    """Acceptance test 6: budget breach → truncation at paragraph boundary, marker appended."""
    tmpdir, slug = temp_modules_dir
    # Create a large voice-profile
    big_vp = "# Voice Profile — Big — v1.0\n\n"
    for i in range(50):
        big_vp += f"## Section {i}\nThis is section {i} with some content here.\n\n"
    with open(os.path.join(tmpdir, slug, "voice-profile.md"), "w") as f:
        f.write(big_vp)

    views = {"test/truncate.md": {
        "big": {"module": "voice-profile", "mode": "full", "budget": 200}
    }}
    variables, provenance = assemble_module_context(
        "test/truncate.md", slug,
        modules_dir=tmpdir, view_map=views
    )
    assert "truncated" in variables["big"].lower()
    assert "TRUNCATED" in provenance


def test_assembler_truncate_at_paragraph_boundary():
    """Truncation hits paragraph boundary (double newline)."""
    text = "First paragraph here.\n\nSecond paragraph that is longer.\n\nThird paragraph."
    truncated, was_trunc = _truncate_at_boundary(text, 30)
    assert was_trunc is True
    assert "First paragraph" in truncated
    assert "truncated" in truncated.lower()


def test_assembler_no_truncation_when_under_budget():
    """Text under budget is returned whole."""
    text = "Short text."
    result, was_trunc = _truncate_at_boundary(text, 100)
    assert was_trunc is False
    assert result == "Short text."


def test_resolve_dynamic_key_simple():
    """Dynamic key resolution: {treatment.format_name} → value."""
    result = _resolve_dynamic_key("{treatment.format_name}", {"treatment": {"format_name": "Street Receipt"}})
    assert result == "Street Receipt"


def test_resolve_dynamic_key_no_braces():
    """Static key (no braces) returned as-is."""
    assert _resolve_dynamic_key("Street Receipt", {}) == "Street Receipt"


def test_resolve_dynamic_key_missing_path():
    """Unresolvable path leaves template as-is."""
    result = _resolve_dynamic_key("{missing.path}", {})
    assert "{" in result  # left as-is


# ── Test 7: Grep gate — no inline module slices in pipeline routes ────────────

def test_no_inline_module_slices_in_app_py():
    """Acceptance test 7: grep gate — no [:2000]/[:3000]/[:1500]/[:4000] module slices in src/app.py pipeline routes."""
    app_py = os.path.join(os.path.dirname(__file__), "..", "src", "app.py")
    with open(app_py) as f:
        content = f.read()

    # The pattern: modules.get("...")[:NNNN]
    import re
    matches = re.findall(r'modules\.get\([^)]+\)\[:\d{4}\]', content)
    assert matches == [], f"Found inline module slices that should be removed: {matches}"


# ── Test 8: Existing pipeline tests still pass ────────────────────────────────
# (Covered by the full suite — if the wiring is done, test_t3_5_to_12_pipeline.py etc. pass)