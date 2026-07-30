# VF-IDEA-1613 controlled fixed-source proof

**Run:** 2026-07-30T04:17:51+00:00
**Environment:** deployed `viralfactory.service`, protected Ollama environment, real `LLMAdapter`

## Fixed source set

Loaded from `config/source_fit_proof.yaml` and resolved from the active Source Bank:

| Source ID | Proof evidence role |
|---:|---|
| 74 | policy |
| 96 | person |
| 80 | culture |
| 78 | money |
| 95 | AI |

The runner failed closed if any ID was missing, duplicated, or had empty exact content.

## Real adapter result

`scripts/source_fit_proof.py` ran through `PipelineStore -> LLMAdapter -> SourceFitCritic` using the protected service environment. The validated result returned:

- `status`: `ok`
- `critic_version`: `1.0`
- `source_fit_ids`: `74, 96, 80, 78, 95` (exact input membership)
- `card_fit`: `policy / supported`
- `batch_range.lens_ids`: `ai, policy, culture, money, entrepreneurship`
- provenance/cache logging occurred in the application database

The critic uses the config-owned `source_fit_critic` judgment backend at temperature 0 and Ollama JSON-Schema response formatting. No Python lens judgment, aliasing, padding, or malformed-output coercion is used.

## Gate 1 UI/API proof

After restarting `viralfactory.service`:

- `GET /ideas?tab=queue&review_set=source_111` → HTTP 200
- Rendered page contained `Source 111 related-card review`
- Rendered page contained `Check source fit`
- Rendered page contained `/editorial-fit`
- Rendered page contained `toggleAllIdeaChecks` and `bulkIdeaGate`
- `POST /api/ideas/88/editorial-fit` with operator-selected `policy` lens → HTTP 200
- Live result: `policy / supported`
- Live result source evidence IDs: `111, 112, 123, 126, 128`

## Empty-source-bank proof

The endpoint regression test verifies that an empty AI-originated Source Bank:

- creates zero cards;
- does not call the LLM adapter;
- returns a clear next action pointing to `/sources`;
- completes the generation job as `source-bank-empty`.

## Verification

- Focused adapter/source-fit/proof/idea tests: **80 passed**
- Fixed-source real-adapter runner: **success**
- Deployed Gate 1 page/API probes: **HTTP 200**
