"""
ViralFactory — M0 Foundation Tests

Tests for:
- Config loader (T0.2): schema validation, bad config fails loudly
- LLM adapter (T0.3): backend config, prompt loading, rendering
- Validator (T0.4): JSON-schema, allowlist, missing fields, unknown tags
- Provenance (T0.5): every call writes a row
- Cache (T0.6): same input twice = one cached result
"""

import json
import os
import tempfile
import pytest
import yaml

# Add src to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config_loader import (
    load_business, load_models, load_sources, load_all,
    ConfigError,
)
from validator import (
    validate_json_schema, validate_allowlist, validate_llm_output,
    ValidationError,
)
from provenance import ProvenanceLog
from cache import ContentHashCache
from llm_adapter import LLMAdapter, LLMAdapterError


# --- Fixtures ---

@pytest.fixture
def tmp_db():
    """Temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.unlink(db_path)  # remove so SQLite creates fresh
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def tmp_config_dir():
    """Temporary config directory with valid configs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # business.yaml
        business = {
            "business": {
                "name": "TestBrand",
                "slug": "testbrand",
                "description": "A test business",
            },
            "brands": [{"name": "TestBrand", "purpose": "Testing"}],
            "subjects": ["AI", "wealth"],
            "platforms": [{"name": "X", "handle": "@test", "priority": 1}],
            "goals": ["Build audience"],
            "red_lines": ["No spam"],
            "audience_description": "Testers",
        }
        with open(os.path.join(tmpdir, "business.yaml"), "w") as f:
            yaml.dump(business, f)

        # models.yaml
        models = {
            "default": {
                "provider": "ollama_cloud",
                "model": "qwen2.5:32b",
                "temperature": 0,
                "max_tokens": 4096,
                "base_url": "https://example.com",
            },
            "drafter": {
                "provider": "ollama_cloud",
                "model": "qwen2.5:32b",
                "temperature": 0.7,
                "max_tokens": 8192,
                "base_url": "https://example.com",
            },
            "drafter_ab_candidate": {},
        }
        with open(os.path.join(tmpdir, "models.yaml"), "w") as f:
            yaml.dump(models, f)

        # sources.yaml
        sources = {
            "feeds": [{"name": "TestFeed", "url": "https://example.com/feed", "type": "rss", "enabled": True}],
            "channels": [],
            "queries": [],
        }
        with open(os.path.join(tmpdir, "sources.yaml"), "w") as f:
            yaml.dump(sources, f)

        yield tmpdir


# --- T0.2: Config Loader Tests ---

class TestConfigLoader:

    def test_load_business_valid(self, tmp_config_dir):
        """Valid business.yaml loads correctly."""
        biz = load_business(tmp_config_dir)
        assert biz["business"]["name"] == "TestBrand"
        assert biz["business"]["slug"] == "testbrand"
        assert "AI" in biz["subjects"]
        assert len(biz["platforms"]) == 1

    def test_load_models_valid(self, tmp_config_dir):
        """Valid models.yaml loads correctly."""
        models = load_models(tmp_config_dir)
        assert models["default"]["model"] == "qwen2.5:32b"
        assert models["drafter"]["temperature"] == 0.7

    def test_load_sources_valid(self, tmp_config_dir):
        """Valid sources.yaml loads correctly."""
        sources = load_sources(tmp_config_dir)
        assert len(sources["feeds"]) == 1
        assert sources["feeds"][0]["name"] == "TestFeed"

    def test_load_all(self, tmp_config_dir):
        """load_all returns all three configs."""
        all_config = load_all(tmp_config_dir)
        assert "business" in all_config
        assert "models" in all_config
        assert "sources" in all_config

    def test_missing_business_file(self):
        """Missing business.yaml raises ConfigError with clear message."""
        with pytest.raises(ConfigError, match="not found"):
            load_business("/nonexistent/path")

    def test_missing_required_field(self, tmp_config_dir):
        """Missing required field raises ConfigError."""
        with open(os.path.join(tmp_config_dir, "business.yaml"), "r") as f:
            data = yaml.safe_load(f)
        del data["business"]["slug"]
        with open(os.path.join(tmp_config_dir, "business.yaml"), "w") as f:
            yaml.dump(data, f)
        with pytest.raises(ConfigError, match="slug"):
            load_business(tmp_config_dir)

    def test_empty_subjects_rejected(self, tmp_config_dir):
        """Empty subjects list (min_items=1) raises ConfigError."""
        with open(os.path.join(tmp_config_dir, "business.yaml"), "r") as f:
            data = yaml.safe_load(f)
        data["subjects"] = []
        with open(os.path.join(tmp_config_dir, "business.yaml"), "w") as f:
            yaml.dump(data, f)
        with pytest.raises(ConfigError, match="at least 1"):
            load_business(tmp_config_dir)

    def test_no_platforms_rejected(self, tmp_config_dir):
        """No platforms fails — must have at least 1."""
        with open(os.path.join(tmp_config_dir, "business.yaml"), "r") as f:
            data = yaml.safe_load(f)
        data["platforms"] = []
        with open(os.path.join(tmp_config_dir, "business.yaml"), "w") as f:
            yaml.dump(data, f)
        with pytest.raises(ConfigError, match="platforms"):
            load_business(tmp_config_dir)


# --- T0.4: Validator Tests ---

class TestValidator:

    def test_valid_schema(self):
        """Valid output passes schema validation."""
        output = {"title": "Test", "body": "Content", "tags": ["AI"]}
        schema = {
            "type": "object",
            "required": ["title", "body"],
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        }
        result = validate_json_schema(output, schema)
        assert result == output

    def test_missing_required_field(self):
        """Missing required field raises ValidationError."""
        output = {"title": "Test"}
        schema = {
            "type": "object",
            "required": ["title", "body"],
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
        }
        with pytest.raises(ValidationError, match="body"):
            validate_json_schema(output, schema)

    def test_wrong_type(self):
        """Wrong type raises ValidationError."""
        output = {"title": 123, "body": "Content"}
        schema = {
            "type": "object",
            "required": ["title", "body"],
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
        }
        with pytest.raises(ValidationError, match="title"):
            validate_json_schema(output, schema)

    def test_unknown_tag_rejected(self):
        """Unknown tag in allowlist is rejected."""
        output = {"subject": "quantum_physics"}
        schema = {
            "type": "object",
            "required": ["subject"],
            "properties": {"subject": {"type": "string"}},
        }
        allowlist = {"subject": ["AI", "wealth", "Caribbean culture"]}
        with pytest.raises(ValidationError, match="quantum_physics"):
            validate_llm_output(
                json.dumps(output), schema, allowlist, context="test"
            )

    def test_valid_json_parse(self):
        """Valid JSON string is parsed and validated."""
        raw = json.dumps({"title": "Test", "body": "Content"})
        schema = {
            "type": "object",
            "required": ["title", "body"],
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
        }
        result = validate_llm_output(raw, schema)
        assert result["title"] == "Test"

    def test_invalid_json_rejected(self):
        """Invalid JSON raises ValidationError."""
        with pytest.raises(ValidationError, match="not valid JSON"):
            validate_llm_output("not json at all", {"type": "object", "required": [], "properties": {}})

    def test_array_items_validated(self):
        """Array items are type-checked."""
        output = {"tags": ["AI", 123]}
        schema = {
            "type": "object",
            "required": ["tags"],
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        }
        with pytest.raises(ValidationError, match="tags"):
            validate_json_schema(output, schema)

    def test_nested_object_validated(self):
        """Nested objects are validated recursively."""
        output = {"meta": {"count": "not a number"}}
        schema = {
            "type": "object",
            "required": ["meta"],
            "properties": {
                "meta": {
                    "type": "object",
                    "required": ["count"],
                    "properties": {"count": {"type": "integer"}},
                },
            },
        }
        with pytest.raises(ValidationError, match="count"):
            validate_json_schema(output, schema)


# --- T0.5: Provenance Tests ---

class TestProvenance:

    def test_log_writes_row(self, tmp_db):
        """Every adapter call writes a provenance row."""
        log = ProvenanceLog(tmp_db)
        log.log(
            input_hash="abc123",
            prompt_file="prompts/test.md",
            prompt_version="1.0",
            model="qwen2.5:32b",
            provider="ollama_cloud",
            raw_output='{"title": "Test"}',
            validated_output={"title": "Test"},
            validator_verdict="valid",
            context="test call",
        )
        assert log.count() == 1
        entries = log.get_by_hash("abc123")
        assert len(entries) == 1
        assert entries[0]["model"] == "qwen2.5:32b"
        assert entries[0]["validator_verdict"] == "valid"
        log.close()

    def test_log_invalid_verdict(self, tmp_db):
        """Invalid outputs are logged with verdict='invalid'."""
        log = ProvenanceLog(tmp_db)
        log.log(
            input_hash="def456",
            prompt_file="prompts/test.md",
            prompt_version="1.0",
            model="qwen2.5:32b",
            provider="ollama_cloud",
            raw_output="not json",
            validated_output=None,
            validator_verdict="invalid",
            validator_errors="JSON parse error",
            context="failed call",
        )
        entries = log.get_by_hash("def456")
        assert entries[0]["validator_verdict"] == "invalid"
        assert entries[0]["validated_output"] is None
        log.close()

    def test_multiple_calls_tracked(self, tmp_db):
        """Multiple calls are all logged."""
        log = ProvenanceLog(tmp_db)
        for i in range(5):
            log.log(
                input_hash=f"hash_{i}",
                prompt_file="prompts/test.md",
                prompt_version="1.0",
                model="qwen2.5:32b",
                provider="ollama_cloud",
                raw_output=f'{{"i": {i}}}',
                validated_output={"i": i},
                validator_verdict="valid",
                context=f"call {i}",
            )
        assert log.count() == 5
        log.close()

    def test_append_only_same_call_twice(self, tmp_db):
        """R2: Logging the same call twice creates two rows, original intact."""
        log = ProvenanceLog(tmp_db)

        # First call with real raw output
        log.log(
            input_hash="dup_hash",
            prompt_file="prompts/test.md",
            prompt_version="1.0",
            model="qwen2.5:32b",
            provider="ollama_cloud",
            raw_output='{"real": "output"}',
            validated_output={"real": "output"},
            validator_verdict="valid",
            context="first attempt",
        )

        # Second call — same key fields, cached/different raw output
        log.log(
            input_hash="dup_hash",
            prompt_file="prompts/test.md",
            prompt_version="1.0",
            model="qwen2.5:32b",
            provider="ollama_cloud",
            raw_output="(cached)",
            validated_output={"real": "output"},
            validator_verdict="valid",
            context="cache hit",
            cached=True,
        )

        # Must have TWO rows, not one
        assert log.count() == 2

        entries = log.get_by_hash("dup_hash")
        assert len(entries) == 2

        # The original row must still have the real raw output
        originals = [e for e in entries if e["raw_output"] == '{"real": "output"}']
        assert len(originals) == 1, "Original raw output was overwritten — not append-only!"
        assert originals[0]["cached"] == 0

        # The second row has the cached marker
        cached = [e for e in entries if e["raw_output"] == "(cached)"]
        assert len(cached) == 1
        assert cached[0]["cached"] == 1

        log.close()


# --- T0.6: Cache Tests ---

class TestCache:

    def test_same_input_twice_one_call(self, tmp_db):
        """Same input twice returns cached result — one cached entry."""
        cache = ContentHashCache(tmp_db)

        variables = {"seed": "Caribbean wealth is about community"}
        variables_hash = ContentHashCache.hash_variables(variables)

        # First call — not cached
        result1 = cache.get("prompts/test.md", "1.0", variables_hash, "qwen2.5:32b")
        assert result1 is None

        # Put result in cache
        cache.put("prompts/test.md", "1.0", variables_hash, "qwen2.5:32b", {"title": "Test"})

        # Second call — cached
        result2 = cache.get("prompts/test.md", "1.0", variables_hash, "qwen2.5:32b")
        assert result2 is not None
        assert result2["title"] == "Test"

        # Only 1 entry in cache
        assert cache.count() == 1
        cache.close()

    def test_different_inputs_different_cache(self, tmp_db):
        """Different inputs get separate cache entries."""
        cache = ContentHashCache(tmp_db)

        vars1 = {"seed": "first idea"}
        vars2 = {"seed": "second idea"}

        hash1 = ContentHashCache.hash_variables(vars1)
        hash2 = ContentHashCache.hash_variables(vars2)

        assert hash1 != hash2

        cache.put("prompts/test.md", "1.0", hash1, "model", {"result": 1})
        cache.put("prompts/test.md", "1.0", hash2, "model", {"result": 2})

        assert cache.count() == 2

        r1 = cache.get("prompts/test.md", "1.0", hash1, "model")
        r2 = cache.get("prompts/test.md", "1.0", hash2, "model")
        assert r1["result"] == 1
        assert r2["result"] == 2
        cache.close()

    def test_different_models_different_cache(self, tmp_db):
        """Same input but different model gets separate cache entry."""
        cache = ContentHashCache(tmp_db)

        variables = {"seed": "same idea"}
        vhash = ContentHashCache.hash_variables(variables)

        cache.put("prompts/test.md", "1.0", vhash, "model_a", {"result": "a"})
        cache.put("prompts/test.md", "1.0", vhash, "model_b", {"result": "b"})

        assert cache.count() == 2

        ra = cache.get("prompts/test.md", "1.0", vhash, "model_a")
        rb = cache.get("prompts/test.md", "1.0", vhash, "model_b")
        assert ra["result"] == "a"
        assert rb["result"] == "b"
        cache.close()

    def test_deterministic_hash(self):
        """Same variables produce the same hash regardless of key order."""
        v1 = {"a": 1, "b": 2}
        v2 = {"b": 2, "a": 1}
        assert ContentHashCache.hash_variables(v1) == ContentHashCache.hash_variables(v2)


# --- T0.3: LLM Adapter Tests ---

class TestLLMAdapter:

    def test_adapter_initializes(self, tmp_db):
        """Adapter initializes with cache and provenance."""
        models_config = {
            "default": {
                "provider": "ollama_cloud",
                "model": "qwen2.5:32b",
                "temperature": 0,
                "max_tokens": 4096,
                "base_url": "https://example.com",
            },
            "drafter": {
                "provider": "ollama_cloud",
                "model": "qwen2.5:32b",
                "temperature": 0.7,
                "max_tokens": 8192,
                "base_url": "https://example.com",
            }
        }
        adapter = LLMAdapter(models_config, db_path=tmp_db)
        assert adapter.cache.count() == 0
        assert adapter.provenance.count() == 0
        adapter.cache.close()
        adapter.provenance.close()

    def test_prompt_loading_and_version_extraction(self, tmp_db):
        """Prompt file loads and version is extracted from comment."""
        import tempfile, os
        prompts_dir = tempfile.mkdtemp()
        prompt_path = os.path.join(prompts_dir, "test_prompt.md")
        with open(prompt_path, "w") as f:
            f.write("<!-- version: 2.1 -->\nAnalyze this: {input}")

        models_config = {"default": {"provider": "ollama", "model": "test", "temperature": 0, "max_tokens": 100, "base_url": ""}}
        adapter = LLMAdapter(models_config, db_path=tmp_db, prompts_dir=prompts_dir)
        template, version = adapter._load_prompt("test_prompt.md")
        assert version == "2.1"
        assert "{input}" in template

        adapter.cache.close()
        adapter.provenance.close()
        os.unlink(prompt_path)
        os.rmdir(prompts_dir)

    def test_prompt_rendering(self, tmp_db):
        """Variables are substituted into the prompt template."""
        models_config = {"default": {"provider": "ollama", "model": "test", "temperature": 0, "max_tokens": 100, "base_url": ""}}
        adapter = LLMAdapter(models_config, db_path=tmp_db)
        rendered = adapter._render_prompt("Hello {name}, you are {role}.", {"name": "Daimon", "role": "operator"})
        assert "Daimon" in rendered
        assert "operator" in rendered
        assert "{name}" not in rendered
        adapter.cache.close()
        adapter.provenance.close()

    def test_missing_backend_rejected(self, tmp_db):
        """Asking for a backend not in config raises error."""
        models_config = {"default": {"provider": "ollama", "model": "test", "temperature": 0, "max_tokens": 100, "base_url": ""}}
        adapter = LLMAdapter(models_config, db_path=tmp_db)
        with pytest.raises(LLMAdapterError, match="not found"):
            adapter.complete("test.md", {}, {"type": "object", "required": [], "properties": {}}, backend="nonexistent")
        adapter.cache.close()
        adapter.provenance.close()

    def test_missing_prompt_file_rejected(self, tmp_db):
        """Missing prompt file raises error."""
        models_config = {"default": {"provider": "ollama", "model": "test", "temperature": 0, "max_tokens": 100, "base_url": ""}}
        adapter = LLMAdapter(models_config, db_path=tmp_db)
        with pytest.raises(LLMAdapterError, match="not found"):
            adapter.complete("nonexistent.md", {}, {"type": "object", "required": [], "properties": {}})
        adapter.cache.close()
        adapter.provenance.close()

    def test_invalid_then_valid_logs_both_attempts(self, tmp_db):
        """R3: When attempt 1 fails validation and attempt 2 succeeds,
        both the failed AND successful attempts are logged to provenance."""
        import tempfile, os
        from unittest.mock import patch, MagicMock

        prompts_dir = tempfile.mkdtemp()
        prompt_path = os.path.join(prompts_dir, "test_prompt.md")
        with open(prompt_path, "w") as f:
            f.write("<!-- version: 1.0 -->\nAnalyze: {input}")

        models_config = {"default": {"provider": "ollama", "model": "test", "temperature": 0, "max_tokens": 100, "base_url": "http://fake"}}
        adapter = LLMAdapter(models_config, db_path=tmp_db, prompts_dir=prompts_dir)

        # Mock: first call returns invalid JSON, second returns valid JSON
        call_count = [0]
        def mock_call(prompt, model, base_url, temperature, max_tokens):
            call_count[0] += 1
            if call_count[0] == 1:
                return "not valid json at all", 50
            else:
                return '{"result": "ok"}', 70

        with patch.object(adapter, "_call_ollama", side_effect=mock_call):
            result = adapter.complete(
                "test_prompt.md",
                {"input": "test"},
                {"type": "object", "required": ["result"], "properties": {"result": {"type": "string"}}},
                context="r3 test",
            )

        assert result == {"result": "ok"}

        # Two provenance rows: one invalid, one valid
        assert adapter.provenance.count() == 2

        rows = adapter.provenance.conn.execute(
            "SELECT * FROM provenance ORDER BY id"
        ).fetchall()
        assert rows[0]["validator_verdict"] == "invalid"
        assert rows[0]["raw_output"] == "not valid json at all"
        assert "attempt 1" in rows[0]["context"]
        assert rows[1]["validator_verdict"] == "valid"
        assert rows[1]["raw_output"] == '{"result": "ok"}'

        adapter.cache.close()
        adapter.provenance.close()
        os.unlink(prompt_path)
        os.rmdir(prompts_dir)

    def test_ollama_sends_auth_header_with_key(self, tmp_db, monkeypatch):
        """R4: When OLLAMA_API_KEY is set, the adapter sends Authorization: Bearer."""
        from unittest.mock import patch, MagicMock
        import requests as req_module

        monkeypatch.setenv("OLLAMA_API_KEY", "test-key-123")

        models_config = {"default": {"provider": "ollama_cloud", "model": "test", "temperature": 0, "max_tokens": 100, "base_url": "https://ollama.com"}}
        adapter = LLMAdapter(models_config, db_path=tmp_db)

        captured_headers = {}
        def mock_post(url, json=None, headers=None, timeout=None, **kwargs):
            captured_headers.update(headers or {})
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json = MagicMock(return_value={"message": {"content": '{"ok": true}'}})
            return mock_resp

        with patch.object(req_module, "post", side_effect=mock_post):
            adapter._call_ollama("test prompt", "test", "https://ollama.com", 0, 100)

        assert "Authorization" in captured_headers
        assert captured_headers["Authorization"] == "Bearer test-key-123"

        adapter.cache.close()
        adapter.provenance.close()

    def test_ollama_no_auth_header_without_key(self, tmp_db, monkeypatch):
        """R4: Without OLLAMA_API_KEY, no Authorization header is sent (local mode)."""
        from unittest.mock import patch, MagicMock
        import requests as req_module

        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

        models_config = {"default": {"provider": "ollama_local", "model": "test", "temperature": 0, "max_tokens": 100, "base_url": "http://localhost:11434"}}
        adapter = LLMAdapter(models_config, db_path=tmp_db)

        captured_headers = {}
        def mock_post(url, json=None, headers=None, timeout=None, **kwargs):
            captured_headers.update(headers or {})
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json = MagicMock(return_value={"message": {"content": '{"ok": true}'}})
            return mock_resp

        with patch.object(req_module, "post", side_effect=mock_post):
            adapter._call_ollama("test prompt", "test", "http://localhost:11434", 0, 100)

        assert "Authorization" not in captured_headers

        adapter.cache.close()
        adapter.provenance.close()