"""
ViralFactory — LLM Adapter

One function: complete(prompt_file, variables, schema) -> validated JSON.
Backend from config — Ollama local, Ollama Cloud, or external API.
Model swap = config edit, zero code change.

The adapter handles:
- Loading prompt templates from files
- Calling the LLM backend
- Caching by content hash (unchanged input = cached result)
- Validating output against schema
- Logging every call to provenance
- Retry-once on invalid JSON, then flag "manual review"
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

import requests

# Support both package imports (from src.llm_adapter) and direct imports
try:
    from .cache import ContentHashCache
    from .provenance import ProvenanceLog
    from .validator import validate_llm_output, ValidationError
except ImportError:
    from cache import ContentHashCache
    from provenance import ProvenanceLog
    from validator import validate_llm_output, ValidationError


class LLMAdapterError(Exception):
    """Raised when the LLM adapter cannot complete a request."""
    pass


class LLMAdapter:
    """
    The single entry point for all LLM calls in ViralFactory.

    Usage:
        adapter = LLMAdapter(models_config, db_path="data/viralfactory.db")
        result = adapter.complete(
            prompt_file="prompts/draft/v1.md",
            variables={"seed": "Wealth is about community not just cash"},
            schema={"type": "object", "required": ["title", "body"], "properties": {...}},
            backend="drafter",  # or "default"
        )
    """

    def __init__(
        self,
        models_config: dict,
        db_path: str = "data/viralfactory.db",
        prompts_dir: str = "prompts",
    ):
        self.models_config = models_config
        self.prompts_dir = prompts_dir
        self.cache = ContentHashCache(db_path)
        self.provenance = ProvenanceLog(db_path)

    def _load_prompt(self, prompt_file: str) -> tuple[str, str]:
        """
        Load a prompt template from file. Returns (template, version).
        Version is extracted from a `<!-- version: X.Y -->` comment or defaults to '1.0'.
        """
        path = os.path.join(self.prompts_dir, prompt_file)
        if not os.path.exists(path):
            # Also try without the prompts/ prefix if already included
            if prompt_file.startswith("prompts/"):
                path = prompt_file
            if not os.path.exists(path):
                raise LLMAdapterError(f"Prompt file not found: {prompt_file}")

        with open(path, "r") as f:
            content = f.read()

        # Extract version from comment
        version_match = re.search(r'<!--\s*version:\s*([\d.]+)\s*-->', content)
        version = version_match.group(1) if version_match else "1.0"

        return content, version

    def _render_prompt(self, template: str, variables: dict) -> str:
        """Render a prompt template with variables using single-pass substitution.

        R8/T2.10: Uses regex single-pass replacement to prevent double-substitution.
        If a variable's value contains '{another_var}', that brace is NOT re-interpreted.
        """
        def replacer(match):
            key = match.group(1)
            if key in variables:
                return str(variables[key])
            return match.group(0)  # leave unknown placeholders as-is

        # Single pass: replace all {key} occurrences in one regex sweep
        return re.sub(r'\{(\w+)\}', replacer, template)

    def _call_ollama(
        self,
        prompt: str,
        model: str,
        base_url: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, int]:
        """
        Call an Ollama-compatible API. Returns (response_text, latency_ms).
        Works with both Ollama local (http://localhost:11434) and Ollama Cloud.

        For Ollama Cloud, set OLLAMA_API_KEY in the environment — the adapter
        sends it as a Bearer token. Local Ollama needs no auth.
        """
        # Ollama API: POST /api/chat or /api/generate
        # We use /api/chat with messages format
        url = base_url.rstrip("/") + "/api/chat"

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        headers = {"Content-Type": "application/json"}
        api_key = os.environ.get("OLLAMA_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        start = time.time()
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
        except requests.RequestException as e:
            raise LLMAdapterError(f"Ollama API call failed: {e}")
        latency_ms = int((time.time() - start) * 1000)

        data = response.json()
        # Ollama chat format: {"message": {"content": "..."}}
        content = data.get("message", {}).get("content", "")
        return content, latency_ms

    def _call_openai_compatible(
        self,
        prompt: str,
        model: str,
        base_url: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, int]:
        """
        Call an OpenAI-compatible API (OpenAI, Together, Anyscale, etc.).
        Returns (response_text, latency_ms).
        """
        url = base_url.rstrip("/") + "/v1/chat/completions"

        # Get API key from environment
        api_key = os.environ.get("OPENAI_API_KEY", "")

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        start = time.time()
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
        except requests.RequestException as e:
            raise LLMAdapterError(f"OpenAI-compatible API call failed: {e}")
        latency_ms = int((time.time() - start) * 1000)

        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content, latency_ms

    def complete(
        self,
        prompt_file: str,
        variables: dict,
        schema: dict,
        backend: str = "default",
        allowlists: Optional[dict[str, list[str]]] = None,
        context: str = "",
        business_slug: Optional[str] = None,
    ) -> dict:
        """
        The main entry point. Load prompt, render, call LLM, validate, cache, log.

        Args:
            prompt_file: Path to the prompt template (relative to prompts/)
            variables: Dict of variables to substitute into the template
            schema: JSON-schema-like dict for validating the output
            backend: "default" or "drafter" (from models.yaml)
            allowlists: Optional dict of {field: [allowed_values]} for taxonomy enforcement
            context: Human-readable description of what this call is for

        Returns:
            Validated dict (the LLM's output, schema-checked)

        Raises:
            LLMAdapterError if the call fails after retry
            ValidationError if the output can't be validated after retry
        """
        # Get backend config
        # The config may use an "active" block that maps role names ("default", "drafter")
        # to named backend definitions, OR it may have backends as top-level keys (legacy).
        # "backend" can be: "default" / "drafter" (resolved via active block),
        # or a named backend key directly (e.g. "ollama_glm52").
        models_config = self.models_config
        backend_config = None

        # Try active-block resolution: backend="default" → active.default → named backend
        active = models_config.get("active")
        if active and backend in active:
            backend_name = active[backend]
            if backend_name:
                backend_config = models_config.get(backend_name)

        # If not resolved via active block, try direct lookup (legacy or named backend)
        if not backend_config:
            backend_config = models_config.get(backend)

        if not backend_config:
            raise LLMAdapterError(f"Backend '{backend}' not found in models config")

        provider = backend_config["provider"]
        model = backend_config["model"]
        temperature = backend_config["temperature"]
        max_tokens = backend_config["max_tokens"]
        base_url = backend_config.get("base_url", "")

        # Load prompt
        template, prompt_version = self._load_prompt(prompt_file)
        rendered = self._render_prompt(template, variables)

        # Compute hashes
        variables_hash = ContentHashCache.hash_variables(variables)

        # Check cache
        cached = self.cache.get(prompt_file, prompt_version, variables_hash, model)
        if cached is not None:
            self.provenance.log(
                input_hash=variables_hash,
                prompt_file=prompt_file,
                prompt_version=prompt_version,
                model=model,
                provider=provider,
                raw_output="(cached)",
                validated_output=cached,
                validator_verdict="valid",
                context=f"{context} (cached)",
                temperature=temperature,
                cached=True,
                business_slug=business_slug,
            )
            return cached

        # Call the LLM
        call_fn = self._call_ollama if "ollama" in provider else self._call_openai_compatible

        try:
            raw_output, latency_ms = call_fn(
                rendered, model, base_url, temperature, max_tokens
            )
        except LLMAdapterError:
            # Log the failure
            self.provenance.log(
                input_hash=variables_hash,
                prompt_file=prompt_file,
                prompt_version=prompt_version,
                model=model,
                provider=provider,
                raw_output="",
                validated_output=None,
                validator_verdict="error",
                validator_errors="API call failed",
                context=context,
                temperature=temperature,
                business_slug=business_slug,
            )
            raise

        # Validate (retry once on failure)
        for attempt in range(2):
            try:
                validated = validate_llm_output(
                    raw_output, schema, allowlists, context=context
                )
                # Success — cache and log
                self.cache.put(prompt_file, prompt_version, variables_hash, model, validated)
                self.provenance.log(
                    input_hash=variables_hash,
                    prompt_file=prompt_file,
                    prompt_version=prompt_version,
                    model=model,
                    provider=provider,
                    raw_output=raw_output,
                    validated_output=validated,
                    validator_verdict="valid",
                    context=context,
                    temperature=temperature,
                    latency_ms=latency_ms,
                    business_slug=business_slug,
                    )
                return validated
            except ValidationError as e:
                if attempt == 0:
                    # Log the failed attempt before retrying — every LLM call logged
                    self.provenance.log(
                        input_hash=variables_hash,
                        prompt_file=prompt_file,
                        prompt_version=prompt_version,
                        model=model,
                        provider=provider,
                        raw_output=raw_output,
                        validated_output=None,
                        validator_verdict="invalid",
                        validator_errors=str(e),
                        context=f"{context} (attempt 1, failed validation)",
                        temperature=temperature,
                        latency_ms=latency_ms,
                        business_slug=business_slug,
                        )
                    # Retry once — append "Please respond with valid JSON only" and re-call
                    retry_prompt = rendered + "\n\n---\nIMPORTANT: Your previous response was not valid JSON. Please respond with ONLY valid JSON, no markdown, no explanation."
                    raw_output, latency_ms = call_fn(
                        retry_prompt, model, base_url, temperature, max_tokens
                    )
                else:
                    # Two attempts failed — log and flag for manual review
                    self.provenance.log(
                        input_hash=variables_hash,
                        prompt_file=prompt_file,
                        prompt_version=prompt_version,
                        model=model,
                        provider=provider,
                        raw_output=raw_output,
                        validated_output=None,
                        validator_verdict="invalid",
                        validator_errors=str(e),
                        context=f"{context} (attempt 2, failed validation)",
                        temperature=temperature,
                        latency_ms=latency_ms,
                        business_slug=business_slug,
                        )
                    raise LLMAdapterError(
                        f"LLM output failed validation after retry: {e}. "
                        f"Flagged for manual review. Context: {context}"
                    )