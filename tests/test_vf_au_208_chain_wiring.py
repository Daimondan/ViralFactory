"""Tests for VF-AU-208: Wire routes and ProductionChain to services.

Verifies that the four chain stubs are implemented (no longer `pass`),
and that they call the shared services.
"""

import os, sys, ast, pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestChainStubsImplemented:
    """The four chain stubs must no longer be bare `pass` statements."""

    def _read_method_body(self, filepath, method_name):
        """Extract the body of a method from a Python file using AST."""
        with open(filepath, "r") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == method_name:
                # Count non-trivial statements (not just `pass`)
                real_stmts = []
                for stmt in node.body:
                    if isinstance(stmt, ast.Pass):
                        continue
                    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                        continue  # skip docstrings
                    real_stmts.append(stmt)
                return real_stmts
        return None

    def test_media_plan_stub_implemented(self):
        stmts = self._read_method_body("src/produce_chain.py", "_step_media_plan")
        assert stmts is not None, "_step_media_plan not found"
        assert len(stmts) > 0, "_step_media_plan still has empty body (pass)"

    def test_media_exec_stub_implemented(self):
        stmts = self._read_method_body("src/produce_chain.py", "_step_media_exec")
        assert stmts is not None
        assert len(stmts) > 0

    def test_edit_plan_stub_implemented(self):
        stmts = self._read_method_body("src/produce_chain.py", "_step_edit_plan")
        assert stmts is not None
        assert len(stmts) > 0

    def test_render_stub_implemented(self):
        stmts = self._read_method_body("src/produce_chain.py", "_step_render")
        assert stmts is not None
        assert len(stmts) > 0

    def test_media_plan_calls_shared_service(self):
        """_step_media_plan should import and use a shared service."""
        with open("src/produce_chain.py", "r") as f:
            content = f.read()
        # The method should reference the media planning service
        assert "MediaPlanningService" in content or "media_planning" in content
        assert "MediaInventoryService" in content or "media_inventory" in content

    def test_edit_plan_calls_cue_compiler(self):
        """_step_edit_plan should use the cue compiler."""
        with open("src/produce_chain.py", "r") as f:
            content = f.read()
        assert "CueCompiler" in content or "cue_compiler" in content

    def test_render_calls_render_review_service(self):
        """_step_render should use the render/review service."""
        with open("src/produce_chain.py", "r") as f:
            content = f.read()
        assert "RenderReviewService" in content or "render_review" in content