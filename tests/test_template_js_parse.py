"""
Smoke test: extract <script> blocks from session.html, render with dummy
Jinja context, and parse with `node --check`.

Catches the whole class of "template edit silently kills page JS" bugs —
e.g. duplicate const declarations in the same scope (SyntaxError) which
prevent the browser from executing the entire script block.

Triggered by CORRECTION-onboarding-single-thread-v1.0 Item 1 (P0 bug):
duplicate `const playbookName` declaration broke attach/send/gate buttons.
"""
import re
import subprocess
import tempfile
import os
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent.parent / "src" / "templates" / "session.html"


def _extract_script_blocks(html: str) -> list[str]:
    """Extract contents of all <script>...</script> blocks (no src attribute)."""
    # Match <script> blocks that don't have a src= attribute
    pattern = r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>'
    blocks = re.findall(pattern, html, re.DOTALL)
    return [b.strip() for b in blocks if b.strip()]


def _render_jinja_placeholders(js: str) -> str:
    """
    Replace Jinja template variables with dummy values so the JS is valid.
    Handles {{ var }} and {% control blocks %}.
    """
    # Remove Jinja control blocks ({% if %}, {% endif %}, etc.)
    js = re.sub(r'\{%.*?%\}', '', js)
    # Replace {{ var }} with dummy values
    # String context: replace with a dummy string
    js = re.sub(r'"{{\s*\w+\s* }}"', '"dummy"', js)
    # Numeric context (run_id): replace with 1
    js = re.sub(r'{{\s*\w+\s*}}', '1', js)
    return js


def test_session_html_script_blocks_parse():
    """All <script> blocks in session.html must parse as valid JavaScript."""
    html = TEMPLATE_PATH.read_text()
    blocks = _extract_script_blocks(html)

    assert len(blocks) > 0, "Expected at least one <script> block in session.html"

    for i, block in enumerate(blocks):
        rendered = _render_jinja_placeholders(block)

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.js', delete=False, dir='/tmp'
        ) as f:
            f.write(rendered)
            f.flush()
            tmp_path = f.name

        try:
            result = subprocess.run(
                ['node', '--check', tmp_path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0, (
                f"Script block {i} in session.html has a JavaScript SyntaxError:\n"
                f"stderr: {result.stderr}\n"
                f"This likely means a duplicate declaration or syntax issue "
                f"that kills ALL JS on the page (attach, send, gate buttons)."
            )
        finally:
            os.unlink(tmp_path)
