#!/usr/bin/env python3
"""Throwaway spike: random source chunk idea generation experiment.

Uses real ViralFactory Source Bank rows, groups them randomly in chunks of 10,
randomly selects 3 chunks, and makes 1 LLM call per selected chunk to generate
5 ranked ideas. Logs every LLM call to provenance and writes a token/call report.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cache import ContentHashCache  # noqa: E402
from provenance import ProvenanceLog  # noqa: E402
from validator import ValidationError, validate_llm_output  # noqa: E402

DB_PATH = ROOT / "data" / "viralfactory.db"
PROMPT_FILE = "spikes/idea-generation-chunk-experiment/idea_chunk_prompt_v1.md"
PROMPT_PATH = ROOT / PROMPT_FILE
OUTPUT_DIR = ROOT / "spikes" / "idea-generation-chunk-experiment"
OUTPUT_JSON = OUTPUT_DIR / "latest_results.json"
OUTPUT_MD = OUTPUT_DIR / "latest_report.md"
CHUNK_SIZE = 10
SELECTED_CHUNKS = 3
IDEAS_PER_CHUNK = 5
BUSINESS_SLUG = "stackpenni"

SCHEMA = {
    "type": "object",
    "required": ["ideas"],
    "properties": {
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "rank", "idea", "hook_options", "source_refs", "source_notes",
                    "scores", "ranking_reason", "treatment_hint",
                ],
                "properties": {
                    "rank": {"type": "integer"},
                    "idea": {"type": "string"},
                    "hook_options": {"type": "array", "items": {"type": "string"}},
                    "source_refs": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
                    "source_notes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["source_id", "facts_used", "take_built_on_facts"],
                            "properties": {
                                "source_id": {"type": "integer"},
                                "facts_used": {"type": "string"},
                                "take_built_on_facts": {"type": "string"},
                            },
                        },
                    },
                    "scores": {
                        "type": "object",
                        "required": [
                            "virality", "factual_grounding", "opinion_rooted_in_facts",
                            "audience_relevance", "business_fit", "overall",
                        ],
                        "properties": {
                            "virality": {"type": "integer"},
                            "factual_grounding": {"type": "integer"},
                            "opinion_rooted_in_facts": {"type": "integer"},
                            "audience_relevance": {"type": "integer"},
                            "business_fit": {"type": "integer"},
                            "overall": {"type": "integer"},
                        },
                    },
                    "ranking_reason": {"type": "string"},
                    "treatment_hint": {"type": "string"},
                },
            },
        },
    },
}


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f) or {}


def prompt_version() -> str:
    text = PROMPT_PATH.read_text()
    match = re.search(r"<!--\s*version:\s*([\d.]+)\s*-->", text)
    return match.group(1) if match else "1.0"


def render(template: str, variables: dict[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(variables.get(key, match.group(0)))
    return re.sub(r"\{(\w+)\}", repl, template)


def source_text(row: sqlite3.Row) -> str:
    parts = [f"[S{row['id']}] {row['title']}"]
    if row["url"]:
        parts.append(f"URL: {row['url']}")
    if row["summary"]:
        parts.append(f"Summary: {row['summary']}")
    if row["content"]:
        parts.append(f"Content: {row['content']}")
    return "\n".join(parts)


def load_sources() -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT id, source_type, title, url, summary, content, first_seen
           FROM sources
           WHERE business_slug = ? AND status = 'active'
           ORDER BY id""",
        (BUSINESS_SLUG,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_modules() -> dict[str, str]:
    names = {
        "voice_profile": "voice-profile.md",
        "viral_patterns": "viral-patterns.md",
        "audience_insights": "audience-insights.md",
        "story_frameworks": "story-frameworks.md",
        "format_guide": "format-guide.md",
    }
    out: dict[str, str] = {}
    for key, fname in names.items():
        path = ROOT / "modules" / BUSINESS_SLUG / fname
        out[key] = path.read_text() if path.exists() else "(module not built)"
    return out


def backend_config() -> dict[str, Any]:
    models = load_yaml(ROOT / "config" / "models.yaml")
    active_name = models.get("active", {}).get("ideator") or models.get("active", {}).get("default")
    cfg = models[active_name]
    return {"name": active_name, **cfg}


def call_ollama(prompt: str, cfg: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    url = cfg.get("base_url", "https://ollama.com").rstrip("/") + "/api/chat"
    headers = {"Content-Type": "application/json"}
    if os.environ.get("OLLAMA_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['OLLAMA_API_KEY']}"
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": cfg.get("temperature", 0),
            "num_predict": cfg.get("max_tokens", 4096),
        },
    }
    start = time.time()
    resp = requests.post(url, headers=headers, json=payload, timeout=180)
    latency_ms = int((time.time() - start) * 1000)
    resp.raise_for_status()
    data = resp.json()
    text = data.get("message", {}).get("content", "")
    usage = {
        "latency_ms": latency_ms,
        "prompt_eval_count": data.get("prompt_eval_count"),
        "eval_count": data.get("eval_count"),
        "total_duration_ns": data.get("total_duration"),
        "load_duration_ns": data.get("load_duration"),
        "prompt_eval_duration_ns": data.get("prompt_eval_duration"),
        "eval_duration_ns": data.get("eval_duration"),
    }
    if usage["prompt_eval_count"] is None:
        usage["prompt_eval_count_estimate"] = round(len(prompt) / 4)
    if usage["eval_count"] is None:
        usage["eval_count_estimate"] = round(len(text) / 4)
    return text, usage


def post_validate(result: dict[str, Any], allowed_ids: set[int]) -> None:
    ideas = result.get("ideas", [])
    if len(ideas) != IDEAS_PER_CHUNK:
        raise ValidationError(f"Expected exactly {IDEAS_PER_CHUNK} ideas, got {len(ideas)}")
    for idea in ideas:
        refs = set(idea.get("source_refs", []))
        if not refs:
            raise ValidationError("Idea has no source_refs")
        unknown = refs - allowed_ids
        if unknown:
            raise ValidationError(f"Idea cites source IDs outside this chunk: {sorted(unknown)}")
        scores = idea.get("scores", {})
        for key in ["virality", "factual_grounding", "opinion_rooted_in_facts", "audience_relevance", "business_fit"]:
            if not 1 <= int(scores.get(key, 0)) <= 10:
                raise ValidationError(f"Score {key} out of range: {scores.get(key)}")
        if not 0 <= int(scores.get("overall", -1)) <= 100:
            raise ValidationError(f"Overall out of range: {scores.get('overall')}")


def main() -> int:
    if not os.environ.get("OLLAMA_API_KEY"):
        print("ERROR: OLLAMA_API_KEY is not set in this shell. Source the service env first.", file=sys.stderr)
        return 2

    business_cfg = load_yaml(ROOT / "config" / "business.yaml")
    business = business_cfg["business"]
    modules = load_modules()
    sources = load_sources()
    seed = int(time.time())
    rng = random.Random(seed)
    shuffled = sources[:]
    rng.shuffle(shuffled)
    chunks = [shuffled[i:i + CHUNK_SIZE] for i in range(0, len(shuffled), CHUNK_SIZE)]
    complete_chunk_indexes = [i for i, ch in enumerate(chunks) if len(ch) == CHUNK_SIZE]
    selected = rng.sample(complete_chunk_indexes, k=min(SELECTED_CHUNKS, len(complete_chunk_indexes)))

    cfg = backend_config()
    template = PROMPT_PATH.read_text()
    version = prompt_version()
    provenance = ProvenanceLog(str(DB_PATH))
    calls: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for call_no, chunk_index in enumerate(selected, start=1):
        chunk = chunks[chunk_index]
        source_chunk = "\n\n---\n\n".join(source_text(row) for row in chunk)
        variables = {
            "business_name": business["name"],
            "subjects": ", ".join(business_cfg.get("subjects", [])),
            "audience_description": business_cfg.get("audience_description", ""),
            "source_chunk": source_chunk,
            **modules,
        }
        rendered = render(template, variables)
        input_hash = ContentHashCache.hash_variables(variables)
        allowed_ids = {int(row["id"]) for row in chunk}
        context = f"Spike random source chunk idea generation call {call_no}; chunk_index={chunk_index}; seed={seed}"

        raw, usage = call_ollama(rendered, cfg)
        attempt = 1
        try:
            validated = validate_llm_output(raw, SCHEMA, context=context)
            post_validate(validated, allowed_ids)
            verdict = "valid"
            errors = None
        except ValidationError as e:
            provenance.log(
                input_hash=input_hash,
                prompt_file=PROMPT_FILE,
                prompt_version=version,
                model=cfg["model"],
                provider=cfg["provider"],
                raw_output=raw,
                validated_output=None,
                validator_verdict="invalid",
                validator_errors=str(e),
                context=f"{context} (attempt 1 failed validation)",
                temperature=cfg.get("temperature", 0),
                latency_ms=usage["latency_ms"],
                business_slug=BUSINESS_SLUG,
                profile="researcher",
            )
            retry_prompt = rendered + f"\n\nYour previous response failed validation: {e}. Return corrected JSON only."
            raw, usage_retry = call_ollama(retry_prompt, cfg)
            attempt = 2
            usage = {**usage, "retry": usage_retry}
            validated = validate_llm_output(raw, SCHEMA, context=context)
            post_validate(validated, allowed_ids)
            verdict = "valid"
            errors = None

        provenance.log(
            input_hash=input_hash,
            prompt_file=PROMPT_FILE,
            prompt_version=version,
            model=cfg["model"],
            provider=cfg["provider"],
            raw_output=raw,
            validated_output=validated,
            validator_verdict=verdict,
            validator_errors=errors,
            context=context,
            temperature=cfg.get("temperature", 0),
            latency_ms=usage["latency_ms"],
            business_slug=BUSINESS_SLUG,
            profile="researcher",
        )
        call_log = {
            "call_no": call_no,
            "chunk_index": chunk_index,
            "chunk_size": len(chunk),
            "source_ids": sorted(allowed_ids),
            "attempts": attempt,
            "model": cfg["model"],
            "backend": cfg["name"],
            "provider": cfg["provider"],
            "temperature": cfg.get("temperature", 0),
            "usage": usage,
            "input_hash": input_hash,
            "verdict": verdict,
        }
        calls.append(call_log)
        results.append({"call": call_log, "ideas": validated["ideas"]})
        print(f"call {call_no}/3 chunk={chunk_index} sources={sorted(allowed_ids)} ideas={len(validated['ideas'])} latency_ms={usage['latency_ms']}")

    total_prompt = 0
    total_completion = 0
    total_tokens_known = True
    for c in calls:
        u = c["usage"]
        if u.get("prompt_eval_count") is None or u.get("eval_count") is None:
            total_tokens_known = False
        total_prompt += u.get("prompt_eval_count") or u.get("prompt_eval_count_estimate", 0)
        total_completion += u.get("eval_count") or u.get("eval_count_estimate", 0)
        if "retry" in u:
            ru = u["retry"]
            total_prompt += ru.get("prompt_eval_count") or ru.get("prompt_eval_count_estimate", 0)
            total_completion += ru.get("eval_count") or ru.get("eval_count_estimate", 0)

    payload = {
        "experiment": "random_source_chunks_generate_ranked_ideas",
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "random_seed": seed,
        "source_count_active": len(sources),
        "chunk_size": CHUNK_SIZE,
        "chunk_count": len(chunks),
        "chunk_sizes": [len(c) for c in chunks],
        "selected_chunk_indexes": selected,
        "calls": calls,
        "token_totals": {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "exact_from_provider": total_tokens_known,
        },
        "results": results,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2))

    lines = [
        "# Idea generation chunk experiment — latest run",
        "",
        f"Ran at: {payload['ran_at']}",
        f"Random seed: `{seed}`",
        f"Active sources: {len(sources)} → chunks: {len(chunks)} with sizes {payload['chunk_sizes']}",
        f"Selected chunk indexes: {selected}",
        f"LLM calls: {len(calls)} (plus retries if any)",
        f"Tokens burned: prompt={total_prompt}, completion={total_completion}, total={total_prompt + total_completion}, exact_from_provider={total_tokens_known}",
        "",
        "## Call log",
        "",
        "| Call | Chunk | Sources | Attempts | Latency ms | Prompt tokens | Completion tokens | Model | Verdict |",
        "|---:|---:|---|---:|---:|---:|---:|---|---|",
    ]
    for c in calls:
        u = c["usage"]
        p = u.get("prompt_eval_count") or u.get("prompt_eval_count_estimate")
        e = u.get("eval_count") or u.get("eval_count_estimate")
        lines.append(
            f"| {c['call_no']} | {c['chunk_index']} | {', '.join(map(str, c['source_ids']))} | {c['attempts']} | {u['latency_ms']} | {p} | {e} | {c['model']} | {c['verdict']} |"
        )
    lines += ["", "## Ideas", ""]
    for block in results:
        c = block["call"]
        lines.append(f"### Call {c['call_no']} — chunk {c['chunk_index']}")
        lines.append("")
        for idea in sorted(block["ideas"], key=lambda x: x["rank"]):
            s = idea["scores"]
            lines.append(f"{idea['rank']}. **{idea['idea']}**")
            lines.append(f"   - Overall: {s['overall']}/100 (virality {s['virality']}, facts {s['factual_grounding']}, opinion-on-facts {s['opinion_rooted_in_facts']}, audience {s['audience_relevance']}, business {s['business_fit']})")
            lines.append(f"   - Sources: {idea['source_refs']}")
            lines.append(f"   - Hooks: {' / '.join(idea['hook_options'])}")
            lines.append(f"   - Why ranked: {idea['ranking_reason']}")
            lines.append(f"   - Treatment hint: {idea['treatment_hint']}")
        lines.append("")
    OUTPUT_MD.write_text("\n".join(lines))
    print(f"wrote {OUTPUT_JSON.relative_to(ROOT)}")
    print(f"wrote {OUTPUT_MD.relative_to(ROOT)}")
    print(f"TOTAL_TOKENS {total_prompt + total_completion} PROMPT {total_prompt} COMPLETION {total_completion} exact={total_tokens_known}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
