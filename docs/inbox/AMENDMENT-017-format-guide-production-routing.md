# AMENDMENT-017 — Format Guide production routing is explicit, generic, and gated

**Filed:** 2026-07-30
**Filed by:** Architect
**Status:** APPROVED — ratifies DIVERGENCE-023
**Ratifies:** `docs/decisions/DIVERGENCE-023-episode-format-guide-resolution.md`
**Type:** STRUCTURE / LOGIC

## Decision

A selected Format Guide entry may declare a production binding. The binding is business-owned module data, approved through the normal module gate. The generic harness resolves it mechanically from the exact format locked at Gate 1. The harness may not infer production behavior from a format name, filename, tenant slug, prompt-view hardcode, or keyword.

## Contract

Every Format Guide entry gains an optional structured block:

```yaml
production_binding:
  mode: standard | episode
  process_ref: <Process Registry key>
  governance_module_ref: <module slug or null>
  governance_module_version: <exact approved version or null>
```

Rules:

1. `mode: standard` may omit the governance module.
2. A non-standard mode requires both a registered `process_ref` and an exact approved `governance_module_ref` + version.
3. The module reference resolves through `ModuleStore`; filename conventions and `prompts/views.yaml` tenant bindings are not authoritative.
4. Missing, draft, proposed, rejected, stale, version-mismatched, or schema-invalid references fail closed before media planning or spend.
5. The selected binding is copied into the Gate-1 treatment and hash-locked with the Writer contract. Later Format Guide changes apply only to new or explicitly revised treatments.
6. A format entry without a binding follows the standard production path; it never falls into an episode path by name matching.
7. The Process Registry remains generic. `playbook_type` continues to classify playbooks/processes; it is not overloaded as a format-entry field.

## StackPenni application

The existing `Instagram Reel Script` remains standard. Add a separate, operator-gated Format Guide entry for the Pennifold parable episode. Its business-specific module reference belongs in the StackPenni module, never in Python or global prompt views. `episode-format-parable.md` and its referenced canon/registry assets must be approved and version-resolvable before the binding becomes runnable.

The current hardcoded `episode-format-parable` entries in `prompts/views.yaml` are temporary divergence evidence, not the approved resolver. They must be removed from the active path when the generic binding lands.

## Definition of Done

- Format Guide schema, markdown converter/parser, gate UI, and module history preserve the block.
- Gate-1 treatment persists the exact binding and version.
- `media_plan_v2` receives the resolved module dynamically.
- Standard Reel and episode Reel fixtures choose different production paths with zero tenant strings in Python.
- Missing/unapproved/version-mismatched modules fail before LLM/provider spend with plain-language operator copy.
- Operator gates the new StackPenni episode entry and governing module; tests cannot self-approve them.
- DIVERGENCE-023 is marked ratified; P0-2 is then unblocked.
