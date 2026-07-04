"""
ViralFactory — Context Assembly (CORRECTION-module-context-assembly)

Resolves per-prompt module context views via prompts/views.yaml into a dict of
{template_variable: text}. Applies mode (full/section/entry/index), resolves
dynamic keys, applies fallbacks, enforces budgets at the nearest paragraph
boundary BELOW the budget with an explicit marker, and returns a parallel
provenance summary string.

The caller merges the result into the prompt variables and appends the
provenance summary to the adapter.complete(..., context=...) field.
"""

import logging
import os
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


def _truncate_at_boundary(text: str, budget: int) -> tuple[str, bool]:
    """Truncate text at the nearest paragraph boundary BELOW budget.

    Returns (text, was_truncated). If text fits, returns it whole.
    Paragraph boundary = double newline. If no boundary found below budget,
    falls back to the last single newline before budget, then to a hard cut.
    """
    if len(text) <= budget:
        return text, False

    # Try double-newline boundary first (paragraph break)
    cut = text.rfind('\n\n', 0, budget)
    if cut > budget * 0.5:  # found a reasonable boundary
        marker = f'\n\n[module truncated: shown {cut} of {len(text)} chars]'
        return text[:cut].rstrip() + marker, True

    # Fall back to single newline
    cut = text.rfind('\n', 0, budget)
    if cut > budget * 0.5:
        marker = f'\n[module truncated: shown {cut} of {len(text)} chars]'
        return text[:cut].rstrip() + marker, True

    # Hard cut at budget
    marker = f'\n[module truncated: shown {budget} of {len(text)} chars]'
    return text[:budget].rstrip() + marker, True


def _apply_budget(text: str, budget: int) -> tuple[str, bool]:
    """Apply budget enforcement. Returns (text, was_truncated)."""
    if not text or len(text) <= budget:
        return text, False
    return _truncate_at_boundary(text, budget)


def _resolve_dynamic_key(key_template: str, dynamic: dict) -> str:
    """Resolve a {dotted.path} key template against the dynamic dict.

    e.g. "{treatment.format_name}" with dynamic={"treatment": {"format_name": "X"}}
    → "X". Falls back to the template string if resolution fails.
    """
    if not key_template or '{' not in key_template:
        return key_template
    # Find {key} and resolve dotted path
    import re
    def resolve(match):
        path = match.group(1)
        obj = dynamic
        for part in path.split('.'):
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                return match.group(0)  # can't resolve — leave as-is
        return str(obj) if obj is not None else match.group(0)
    return re.sub(r'\{([a-zA-Z_][a-zA-Z0-9_.]*)\}', resolve, key_template)


def _load_view_map(prompts_dir: str) -> dict:
    """Load prompts/views.yaml. Returns {} if file missing."""
    path = os.path.join(prompts_dir, 'views.yaml')
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def assemble_module_context(
    prompt_file: str,
    business_slug: str,
    dynamic: dict = None,
    db_path: str = "data/viralfactory.db",
    modules_dir: str = "modules",
    prompts_dir: str = "prompts",
    view_map: dict = None,
) -> tuple[dict, str]:
    """Resolve the view map for prompt_file into a dict of
    {template_variable: text} + a provenance summary string.

    Args:
        prompt_file: prompt filename relative to prompts/ (e.g. "draft/generate_v2.md")
        business_slug: business slug for module lookup
        dynamic: optional dict for resolving dynamic keys (e.g. {"treatment": {"format_name": "X"}})
        db_path: path to the SQLite DB (passed to ModuleStore)
        modules_dir: path to the modules directory
        prompts_dir: path to prompts directory (for views.yaml)
        view_map: pre-loaded view map (skip file load); primarily for testing

    Returns:
        (variables_dict, provenance_summary)
        variables_dict: {template_variable_name: text}
        provenance_summary: compact string like "voice-profile:full(7412) | format-guide:entry(Street Receipt,2210)"
    """
    dynamic = dynamic or {}

    # Load view map
    if view_map is None:
        view_map = _load_view_map(prompts_dir)

    prompt_views = view_map.get(prompt_file)
    if not prompt_views:
        return {}, ""

    # Lazy import to avoid circular deps in tests
    from module_store import ModuleStore
    store = ModuleStore(modules_dir=modules_dir, db_path=db_path)

    variables = {}
    provenance_parts = []

    for var_name, spec in prompt_views.items():
        module_name = spec.get("module")
        file_ref = spec.get("file")
        mode = spec.get("mode", "full")
        budget = spec.get("budget", 10000)
        fallback = spec.get("fallback")

        # Handle raw file references (e.g. shared/ai_tells_v1.md)
        if file_ref and not module_name:
            file_path = os.path.join(prompts_dir, file_ref)
            try:
                with open(file_path) as f:
                    text = f.read()
                mode_tag = "file"
                extra = file_ref
            except (IOError, OSError):
                text = f"(file '{file_ref}' not found)"
                mode_tag = "FILE_NOT_FOUND"
                extra = None
                logger.warning("Context assembly: file '%s' not found for %s", file_ref, prompt_file)
        else:
            # Resolve the projection from modules
            text, mode_tag, extra = _resolve_projection(
                store, business_slug, module_name, spec, dynamic
            )

            if text is None:
                # Module or section missing — apply fallback
                if fallback == "index":
                    text, mode_tag = _get_index_fallback(store, business_slug, module_name, spec)
                elif fallback == "full":
                    content = store.load(business_slug, module_name)
                    text = content if content else f"(module '{module_name}' not built)"
                    mode_tag = "full-fallback"
                else:
                    heading_desc = spec.get("heading") or spec.get("parent", "")
                    text = f"(section '{heading_desc}' not found in module '{module_name}')"
                    mode_tag = "NOT_FOUND"
                    logger.warning("Context assembly: %s not found in %s for %s",
                                   heading_desc, module_name, prompt_file)

        # Apply budget
        text, was_truncated = _apply_budget(text, budget)
        if was_truncated:
            mode_tag = mode_tag + ",TRUNCATED"
            logger.warning("Context assembly: %s truncated for %s (budget %d)",
                            module_name or file_ref, prompt_file, budget)

        variables[var_name] = text
        char_count = len(text)
        source_name = module_name or file_ref
        label = f"{source_name}:{mode_tag}({extra or char_count})" if extra else f"{source_name}:{mode_tag}({char_count})"
        provenance_parts.append(label)

    provenance_summary = " | ".join(provenance_parts)
    return variables, provenance_summary


def _resolve_projection(
    store, business_slug: str, module_name: str, spec: dict, dynamic: dict
) -> tuple[str | None, str, str | None]:
    """Resolve one projection. Returns (text, mode_tag, extra_label) or (None, mode_tag, None).

    text=None signals the caller to apply fallback.
    extra_label: optional label for provenance (e.g. entry name for entry mode).
    """
    mode = spec.get("mode", "full")

    if mode == "full":
        content = store.load(business_slug, module_name)
        return (content if content else None), "full", None

    if mode == "section":
        heading = spec.get("heading")
        if not heading:
            return None, "section", None
        text = store.get_section(business_slug, module_name, heading)
        return (text if text else None), "section", None

    if mode == "entry":
        parent = spec.get("parent")
        key_template = spec.get("key", "")
        resolved_key = _resolve_dynamic_key(key_template, dynamic)
        text = store.get_entry(business_slug, module_name, parent, resolved_key)
        if text:
            return text, "entry", resolved_key
        return None, "entry", None

    if mode == "index":
        parent = spec.get("parent")
        text = store.get_index(business_slug, module_name, parent)
        return (text if text else None), "index", None

    return None, mode, None


def _get_index_fallback(store, business_slug: str, module_name: str, spec: dict) -> tuple[str, str]:
    """Get index as a fallback for entry/section misses."""
    parent = spec.get("parent")
    text = store.get_index(business_slug, module_name, parent) if parent else None
    if text:
        return text, "index-fallback"
    content = store.load(business_slug, module_name)
    return (content or f"(module '{module_name}' not built)", "full-fallback")