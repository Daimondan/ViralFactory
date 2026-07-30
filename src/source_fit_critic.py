"""VF-IDEA-1609 Source-Fit Critic.

The LLM decides whether supplied source evidence supports a proposed editorial
lens. This module only assembles exact inputs, validates configured references,
and delegates judgment to the configured adapter.
"""

from __future__ import annotations

from typing import Any

try:
    from .editorial_lenses import load_lens_catalogue
except ImportError:
    from editorial_lenses import load_lens_catalogue


SOURCE_FIT_CRITIC_SCHEMA = {
    "type": "object",
    "required": ["critic_version", "card_fit", "source_fit", "batch_range"],
    "properties": {
        "critic_version": {"type": "string"},
        "card_fit": {
            "type": "object",
            "required": ["lens_id", "verdict", "evidence_quotes", "rationale"],
            "properties": {
                "lens_id": {"type": "string"},
                "verdict": {"type": "string", "enum": ["supported", "partial", "unsupported"]},
                "evidence_quotes": {"type": "array", "items": {"type": "string"}},
                "rationale": {"type": "string"},
            },
        },
        "source_fit": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["source_id", "fits", "unresolved"],
                "properties": {
                    "source_id": {"type": "integer"},
                    "fits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["lens_id", "verdict", "evidence_quotes", "rationale"],
                            "properties": {
                                "lens_id": {"type": "string"},
                                "verdict": {"type": "string", "enum": ["supported", "partial", "unsupported"]},
                                "evidence_quotes": {"type": "array", "items": {"type": "string"}},
                                "rationale": {"type": "string"},
                            },
                        },
                    },
                    "unresolved": {"type": "boolean"},
                },
            },
        },
        "batch_range": {
            "type": "object",
            "required": ["lens_ids", "coverage_note"],
            "properties": {
                "lens_ids": {"type": "array", "items": {"type": "string"}},
                "coverage_note": {"type": "string"},
            },
        },
    },
}


class SourceFitValidationError(ValueError):
    """Raised when a critic result crosses the mechanical boundary incorrectly."""


def validate_source_fit_result(
    result: dict,
    source_ids: list[int],
    lens_ids: list[str],
) -> dict:
    """Validate membership and shape after adapter schema validation.

    This function deliberately does not assess whether a quote supports a lens.
    """
    if result.get("critic_version") != "1.0":
        raise SourceFitValidationError("unsupported critic version")
    expected_sources = set(source_ids)
    actual_sources = {item.get("source_id") for item in result.get("source_fit", [])}
    if actual_sources != expected_sources or len(actual_sources) != len(source_ids):
        raise SourceFitValidationError("source membership does not match supplied source evidence")
    configured = set(lens_ids)
    card_fit = result.get("card_fit", {})
    if card_fit.get("lens_id") not in configured:
        raise SourceFitValidationError("card lens is not configured")
    if card_fit.get("verdict") not in {"supported", "partial", "unsupported"}:
        raise SourceFitValidationError("card verdict is invalid")
    for source in result["source_fit"]:
        if not isinstance(source.get("source_id"), int) or isinstance(source.get("source_id"), bool):
            raise SourceFitValidationError("source_id must be an integer")
        for fit in source.get("fits", []):
            if fit.get("lens_id") not in configured:
                raise SourceFitValidationError(f"lens '{fit.get('lens_id')}' is not configured")
            if fit.get("verdict") not in {"supported", "partial", "unsupported"}:
                raise SourceFitValidationError("verdict is invalid")
            if not isinstance(fit.get("evidence_quotes"), list):
                raise SourceFitValidationError("evidence_quotes must be a list")
    for lens_id in result.get("batch_range", {}).get("lens_ids", []):
        if lens_id not in configured:
            raise SourceFitValidationError(f"batch lens '{lens_id}' is not configured")
    return result


class SourceFitCritic:
    """Run the registry-owned Source-Fit Critic through the shared adapter."""

    prompt_file = "ideas/source_fit_critic_v1.md"
    repair_prompt_file = "ideas/source_fit_repair_v1.md"

    def __init__(self, adapter: Any, config_dir: str = "config"):
        self.adapter = adapter
        self.config_dir = config_dir

    def run(
        self,
        business_slug: str,
        sources: list[dict],
        proposed_fit: list[dict],
    ) -> dict:
        source_evidence = []
        seen_source_ids = set()
        for source in sources:
            if not isinstance(source, dict) or not isinstance(source.get("id"), int):
                raise SourceFitValidationError("each source must include an integer id")
            if isinstance(source.get("id"), bool) or source["id"] in seen_source_ids:
                raise SourceFitValidationError("source IDs must be unique integers")
            if not isinstance(source.get("content"), str) or not source["content"].strip():
                raise SourceFitValidationError("each source must include exact content")
            seen_source_ids.add(source["id"])
            source_evidence.append(dict(source))
        catalogue = load_lens_catalogue(business_slug, self.config_dir)
        configured = {item.get("id") for item in catalogue if isinstance(item, dict)}
        for fit in proposed_fit:
            if not isinstance(fit, dict) or fit.get("lens_id") not in configured:
                raise SourceFitValidationError("proposed fit contains an unconfigured lens")
        variables = {
            "source_evidence": source_evidence,
            "proposed_fit": proposed_fit,
        }
        result = self.adapter.complete(
            prompt_file=self.prompt_file,
            variables=variables,
            schema=SOURCE_FIT_CRITIC_SCHEMA,
            backend="source_fit_critic",
            context=f"Source-Fit Critic for {business_slug}",
            business_slug=business_slug,
            profile="source_fit_critic",
        )
        return validate_source_fit_result(
            result,
            [source["id"] for source in source_evidence],
            sorted(configured),
        )

    def run_with_bounded_repair(
        self,
        business_slug: str,
        card_context: dict,
        sources: list[dict],
        proposed_fit: list[dict],
    ) -> dict:
        """Run once, then allow exactly one card-specific repair attempt."""
        try:
            return self.run(business_slug, sources, proposed_fit)
        except SourceFitValidationError as first_error:
            source_evidence = [dict(source) for source in sources]
            catalogue = load_lens_catalogue(business_slug, self.config_dir)
            configured = {item.get("id") for item in catalogue if isinstance(item, dict)}
            repaired = self.adapter.complete(
                prompt_file=self.repair_prompt_file,
                variables={
                    "card_context": card_context,
                    "source_evidence": source_evidence,
                    "proposed_fit": proposed_fit,
                    "critic_findings": str(first_error),
                },
                schema=SOURCE_FIT_CRITIC_SCHEMA,
                backend="source_fit_critic",
                context=f"Source-Fit Critic bounded repair for {business_slug}",
                business_slug=business_slug,
                profile="source_fit_critic_repair",
            )
            return validate_source_fit_result(
                repaired,
                [source["id"] for source in source_evidence],
                sorted(configured),
            )

    @staticmethod
    def retain_valid_results(results: list[tuple[Any, dict]], source_ids_by_card: dict, lens_ids: list[str]):
        """Keep valid results and report invalid cards without padding."""
        kept = []
        omitted = []
        for card_id, result in results:
            try:
                kept.append((card_id, validate_source_fit_result(result, source_ids_by_card[card_id], lens_ids)))
            except (KeyError, SourceFitValidationError, TypeError, ValueError) as exc:
                omitted.append({"card_id": card_id, "reason": str(exc)})
        return kept, omitted
