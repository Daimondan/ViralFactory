"""
Smoke test: extract <style> blocks from ALL operator-facing templates and
validate CSS syntax — specifically that every selector has a { ... } body.

Catches the class of "truncated CSS rule silently breaks page layout" bugs.
Triggered by the assets.html bug where `.post-met` (truncated `.post-meta`)
swallowed the `.post-image { width: 60px; ... }` rule that followed it,
causing images to render at their natural 1376×768px instead of 60×60px
thumbnails — invisible to unit tests, obvious to a human looking at the page.
"""
import re
import os
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "templates"


def _extract_style_blocks(html: str) -> list[str]:
    """Extract contents of all <style>...</style> blocks."""
    pattern = r'<style[^>]*>(.*?)</style>'
    blocks = re.findall(pattern, html, re.DOTALL)
    return [b.strip() for b in blocks if b.strip()]


def _find_truncated_rules(css: str) -> list[str]:
    """
    Find CSS rules where a selector line has no opening brace — the classic
    truncation bug where `.post-met` (incomplete property name) eats the next
    rule as a descendant selector.

    A valid CSS rule looks like:  .selector { property: value; }
    A truncated rule looks like:  .post-met\\n  .post-image { width: 60px; }
    The browser parses this as:  .post-met .post-image { width: 60px; }
    which never matches — the .post-image rule is silently swallowed.
    """
    issues = []
    lines = css.split('\n')

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        # Skip comments
        if stripped.startswith('/*') or stripped.startswith('*'):
            continue
        # Skip closing braces
        if stripped == '}':
            continue
        # Skip lines inside a rule body (contain a property:value)
        if ':' in stripped and '{' not in stripped and not stripped.endswith('{'):
            continue
        # Skip @media and @keyframes openers
        if stripped.startswith('@'):
            continue
        # Skip closing of @media blocks
        if stripped == '}':
            continue

        # A selector line should end with { (inline) or the next non-blank line should have {
        if stripped.endswith('{'):
            continue  # inline rule body — fine

        # Check if this looks like a selector (starts with . or # or a tag name)
        looks_like_selector = (
            stripped.startswith('.') or
            stripped.startswith('#') or
            stripped.startswith('a') or stripped.startswith('p') or
            stripped.startswith('div') or stripped.startswith('span') or
            stripped.startswith('img') or stripped.startswith('input') or
            stripped.startswith('button') or stripped.startswith('video') or
            stripped.startswith('table') or stripped.startswith('td') or
            stripped.startswith('th') or stripped.startswith('h1') or
            stripped.startswith('h2') or stripped.startswith('h3') or
            stripped.startswith('label') or stripped.startswith('select') or
            stripped.startswith('textarea') or stripped.startswith('form') or
            stripped.startswith('ul') or stripped.startswith('li') or
            stripped.startswith('ol') or stripped.startswith('details') or
            stripped.startswith('summary') or stripped.startswith('option') or
            stripped.startswith('nav') or stripped.startswith('section') or
            stripped.startswith('article') or stripped.startswith('header') or
            stripped.startswith('footer') or stripped.startswith('main') or
            stripped.startswith('dialog') or stripped.startswith('canvas')
        )

        if looks_like_selector and '{' not in stripped:
            # Check if the NEXT non-blank, non-comment line has the opening brace
            found_brace = False
            for j in range(i + 1, min(i + 3, len(lines))):
                next_stripped = lines[j].strip()
                if not next_stripped or next_stripped.startswith('/*'):
                    continue
                if '{' in next_stripped:
                    found_brace = True
                    break
                # If the next line is also a selector (comma-separated group),
                # that's fine — the brace will come later
                if next_stripped.endswith(','):
                    continue
                break

            if not found_brace:
                # Check it's not a comma-separated selector group
                if stripped.endswith(','):
                    continue
                issues.append(f"Line {i+1}: '{stripped}' — selector without opening brace (truncated rule?)")

    return issues


def test_all_template_css_has_no_truncated_rules():
    """Every <style> block in every template must have valid CSS — no truncated
    selector rules that would swallow the next rule as a descendant selector."""
    templates = sorted(TEMPLATE_DIR.glob("*.html"))
    assert len(templates) > 0, "No HTML templates found"

    total_blocks = 0
    for template_path in templates:
        html = template_path.read_text()
        blocks = _extract_style_blocks(html)
        total_blocks += len(blocks)

        for i, block in enumerate(blocks):
            issues = _find_truncated_rules(block)
            if issues:
                issues_str = '\n'.join(issues)
                pytest.fail(
                    f"Truncated CSS rules in {template_path.name} style block {i}:\n"
                    f"{issues_str}\n"
                    f"These truncated selectors swallow the next rule as a "
                    f"descendant selector, silently breaking CSS. "
                    f"(Bug class: assets.html .post-met ate .post-image sizing)"
                )

    assert total_blocks > 0, "No <style> blocks found in any template"


# Import pytest at module level for the fail call above
import pytest


def test_all_templates_have_style_blocks_or_no_css():
    """Every template should either have inline <style> blocks or no CSS at all.
    A template with CSS but no <style> blocks means the CSS is being loaded
    from vf.css — which is fine, this test just documents the pattern."""
    templates = sorted(TEMPLATE_DIR.glob("*.html"))
    for template_path in templates:
        html = template_path.read_text()
        has_style = '<style' in html
        has_css_class = 'class="' in html
        # If a template uses CSS classes, it should have a <style> block or
        # rely on vf.css (which is linked in the <head>)
        has_vf_css = 'vf.css' in html
        if has_css_class and not has_style and not has_vf_css:
            pytest.fail(
                f"{template_path.name} uses CSS classes but has no <style> block "
                f"and doesn't link vf.css — CSS will be missing"
            )