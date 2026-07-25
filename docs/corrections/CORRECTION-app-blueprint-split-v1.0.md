# CORRECTION — Split `app.py` into Domain Blueprints — v1.0

**Date:** 2026-07-25
**Author:** Architect (Claude)
**Status:** Approved by operator (verbal, this session — scope explicitly approved)
**Repo state reviewed:** `2b793f1`
**Depends on:** `CORRECTION-repo-health-v1.0.md` Definition of Done. Do not begin until that
batch is complete and green.
**Priority:** P1 structural. Eighteen sequenced commits, each independently revertible.

---

## Why this is being done

`src/app.py` is 10,647 lines. `create_app()` alone spans lines 238–10642 — 10,405 lines in a
single function containing 172 routes, 48 nested helpers, three Jinja filters, one error
handler, one `after_request` hook, and one context processor.

The cost is concentrated in exactly the wrong place. Every correction batch requires Hermes
to walk the full UI before reporting done, and every edit to any surface touches the same
file, so unrelated changes collide. A route at line 9,600 and a helper at line 4,650 are in
the same lexical scope with no boundary between them, which means nothing about the file
tells a reader which helpers a given surface may safely use. Locating a defect means grepping
a ten-thousand-line function. As the correction cadence continues, this compounds.

## Why it is safe to do now

Three properties of the current code make this refactor mechanical rather than exploratory.
Each was verified against the tree at `2b793f1`.

**Nothing resolves endpoint names.** `url_for` is imported at `app.py:16` and called **zero**
times — in `src`, in `scripts`, and in all 38 templates. Templates use literal paths
(`href="/onboard"`, `fetch('/api/assets/...')` across 30 of them). Blueprint registration
prefixes endpoint names (`index` becomes `dashboard.index`), which is normally the primary
hazard of this refactor and the usual source of silent 500s. Here it cannot break anything,
because no code depends on endpoint names. As long as **URL rules are preserved
byte-identical**, the entire UI keeps working.

**No route closes over anything but `app.config`.** Of 550 `app.*` references inside nested
functions, every one is `app.config[...]`: 231 `DB_PATH`, 98 `CONFIG_DIR`, 18
`PLAYBOOKS_DIR`, 2 `JOBS_DB_PATH`, 2 `TRANSCRIPTION_WORKER`, plus 19 bare `app.config`. There
is no closure over request state, no mutable shared object, no captured connection. Every one
of these becomes `current_app.config[...]` with no behavioural change. The residual closure
surface is 17 references to the `config_dir` parameter and 14 to `db_path` — 31 sites total,
each with an exact `app.config` equivalent already populated at `create_app()` lines 246–248.

**Helper coupling is almost entirely local.** Reference analysis across all 48 nested helpers
shows only four are cross-cutting:

| Helper | Routes using it | Called by other helpers |
|---|---|---|
| `_get_business_slug` | 74 | 1 |
| `_get_pipeline_store` | 55 | 9 |
| `_get_jobs_store` | 11 | 1 |
| `_check_job_running` | 10 | 0 |

The remaining 44 are used by between zero and four routes each, all within one domain. So the
shared surface is four functions totalling 30 lines, and all four read nothing but
`app.config` — they convert to module-level functions verbatim.

---

## Target package layout

```
src/
  app.py                     # create_app() only — factory, config, filters, hooks, registration
  web/
    __init__.py              # register_blueprints(app)
    context.py               # the 4 shared helpers + Jinja filters + context processor
    dashboard.py
    inspiration.py
    onboarding.py
    library.py
    materials.py
    ideas.py
    draft.py
    assets.py
    soundtrack.py
    publish.py
    metrics.py
    research.py
    proposals.py
    sources.py
    voices.py
    reference_assets.py
    workbench.py
    composition.py
```

`src/services/` is untouched. This refactor moves the HTTP layer only; no service, store, or
adapter changes. If a domain module starts wanting business logic, that logic belongs in
`services/` and is a separate correction — do not let the split become a rewrite.

### Domain decomposition

Derived by AST from the live tree. Line counts are route-body totals and exclude the
domain-local helpers that move alongside them.

| Blueprint | Routes | Route lines | Current span | URL prefixes |
|---|---|---|---|---|
| `onboarding` | 58 | 2,553 | L1104–L9104 | `/onboard*`, `/api/onboarding/*`, `/api/run/*`, `/api/session/*` |
| `assets` | 24 | 1,198 | L6609–L8115 | `/create/assets`, `/api/assets/*`, `/media/*`, `/api/stock/*`, `/api/reel-production-jobs/*` |
| `ideas` | 10 | 671 | L4861–L5843 | `/ideas*`, `/api/ideas/*` |
| `draft` | 9 | 714 | L5848–L6604 | `/create/draft/*`, `/api/draft/*` |
| `inspiration` | 8 | 483 | L604–L1101 | `/inspiration`, `/api/inspiration/*` |
| `workbench` | 7 | 402 | L9619–L10032 | `/workbench/*`, `/api/workbench/*` |
| `reference_assets` | 7 | 154 | L9430–L9595 | `/setup/reference-assets`, `/api/reference-assets/*` |
| `voices` | 6 | 217 | L9199–L9425 | `/setup/voices`, `/api/voices/*` |
| `soundtrack` | 6 | 207 | L7405–L7622 | `/api/assets/<id>/soundtrack-*` |
| `publish` | 5 | 230 | L8120–L8743 | `/create/publish/*`, `/api/publish/*`, `/api/buffer/status`, `/published`, `/api/assets/<id>/schedule` |
| `proposals` | 5 | 109 | L8581–L8697 | `/proposals`, `/api/proposals/*` |
| `materials` | 5 | 95 | L2770–L2872 | `/materials*`, `/api/materials/*` |
| `dashboard` | 4 | 349 | L409–L9194 | `/`, `/health`, `/create`, `/assemble` |
| `composition` | 4 | 278 | L10217–L10518 | `/composition/*`, `/api/composition/*`, `/api/assets/<id>/gate3` |
| `research` | 4 | 145 | L8386–L8536 | `/research`, `/api/research/*` |
| `sources` | 4 | 115 | L8539–L9189 | `/sources`, `/api/sources/*` |
| `library` | 4 | 106 | L2654–L2765 | `/library`, `/api/library/*` |
| `metrics` | 2 | 62 | L8318–L8381 | `/metrics`, `/api/metrics/pull` |
| **Total** | **172** | **8,088** | | |

Three grouping decisions worth recording, because each could reasonably have gone the other
way and future readers should not have to re-derive the reasoning:

`soundtrack` is split out of `assets` despite sharing the `/api/assets/<id>/` prefix. The six
soundtrack routes form a self-contained review-and-decision loop with their own gate
semantics, and leaving them inside a 24-route `assets` module keeps that module the second
worst file in the repo. URL prefixes need not map one-to-one onto blueprints; Flask does not
require it and coherence matters more.

`/api/assets/<id>/gate3` goes to `composition`, not `assets`, because it is the composition
ratification gate and its helpers (`_gate3_approved`, `_invalidate_gate3_approval`) serve that
flow.

`/api/sources/discover` sits at L8539 among the research routes but is grouped under
`sources`. Verify during migration which store it actually writes to and follow that; if it
belongs with research, move it and note the change.

`onboarding` remains large at 58 routes. It is one genuine domain — eight playbook flows
sharing a session and gate model — and splitting it per playbook would fragment that shared
model across eight files. Land it as one module, then assess. If it needs further division,
that is a follow-up correction with its own reasoning, not a decision to improvise mid-batch.

---

## The shared context module

`src/web/context.py` — the four cross-cutting helpers, converted to module level. This file
is written **once**, before any domain migrates.

```python
"""Shared request-scoped helpers for the web layer.

Every helper here reads configuration through flask.current_app, so blueprints
need no closure over create_app's locals. Nothing in this module may hold
per-request state.
"""
from flask import current_app

from config_loader import load_all, ConfigError


def get_business_slug() -> str | None:
    """The current business slug from config, or None if not configured."""
    try:
        config = load_all(current_app.config["CONFIG_DIR"])
        return config["business"]["business"]["slug"]
    except ConfigError:
        return None


def get_pipeline_store():
    """A PipelineStore bound to the configured database."""
    from pipeline import PipelineStore
    return PipelineStore(db_path=current_app.config["DB_PATH"])


def get_jobs_store():
    """A JobsStore for idempotency and async job tracking."""
    from jobs import JobsStore
    return JobsStore(current_app.config["DB_PATH"])


def check_job_running(job_type, entity_id=None, input_hash=None, stale_timeout_s=None):
    """Return (is_running, job_info). Callers return 409 when is_running is True.

    stale_timeout_s forwards to JobsStore.start_job — jobs older than this are
    treated as stale and a new job starts instead of reporting running.
    """
    store = get_jobs_store()
    kwargs = {}
    if stale_timeout_s:
        kwargs["stale_timeout_s"] = stale_timeout_s
    result = store.start_job(job_type, entity_id, input_hash, **kwargs)
    if result["status"] == "running":
        return True, result
    return False, result
```

The leading underscores are dropped because these are now a deliberate cross-module API
rather than function-local privates. Domain modules import them explicitly:

```python
from web.context import get_business_slug, get_pipeline_store
```

The three Jinja filters (`from_json`, `relative_time`, `strip_md`), the `413` error handler,
the `after_request` no-cache hook, and the `inject_nav_counts` context processor stay
registered on the app in `create_app()`, since they are app-level rather than
blueprint-level. Move their bodies into `web/context.py` as plain functions and register
thin wrappers in the factory, so `app.py` holds registration and not implementation.
`_latest_draft_by_card` is used by `inject_nav_counts` and three routes — it moves to
`web/context.py` as `latest_draft_by_card`.

`src/web/__init__.py`:

```python
"""Web layer — domain blueprints."""


def register_blueprints(app) -> None:
    """Register every domain blueprint. Import order is irrelevant; no blueprint
    may import another."""
    from web import (
        assets, composition, dashboard, draft, ideas, inspiration, library,
        materials, metrics, onboarding, proposals, publish, reference_assets,
        research, sources, soundtrack, voices, workbench,
    )

    for module in (
        dashboard, inspiration, onboarding, library, materials, ideas, draft,
        assets, soundtrack, publish, metrics, research, proposals, sources,
        voices, reference_assets, workbench, composition,
    ):
        app.register_blueprint(module.bp)
```

That no-blueprint-imports-another rule is load-bearing. A domain module needing something
from a sibling is the signal that the shared thing belongs in `web/context.py` or, if it is
business logic, in `services/`. Cross-imports between blueprints would recreate the coupling
this refactor exists to remove.

---

## Per-domain migration procedure

Identical for all eighteen. One domain per commit, suite green at each commit.

**1. Create the module with no URL prefix.** Blueprints must not use `url_prefix`, because
these routes have heterogeneous paths (`assets` spans `/create/assets`, `/api/assets/*`,
`/media/*`, and `/api/stock/*`) and a prefix would silently rewrite them. Declare full paths
exactly as they are today:

```python
"""Metrics surface — performance pull and display."""
from flask import Blueprint, render_template, request, jsonify, current_app

from web.context import get_business_slug, get_pipeline_store

bp = Blueprint("metrics", __name__)


@bp.route("/metrics")
def metrics():
    ...
```

**2. Move route bodies verbatim.** Cut from `app.py`, paste into the domain module. Change
`@app.route` to `@bp.route` and nothing else about the decorator — the rule string, the
`methods` list, and the argument converters must be byte-identical.

**3. Move domain-local helpers with their routes.** Drop the leading underscore only for
helpers a sibling module needs (there should be none); keep it otherwise. The helper-to-domain
mapping falls out of the reference analysis — for example `_parse_draft_for_display` (4 routes)
goes to `draft`, `_build_composition_plan` (181 lines, 2 routes) to `composition`,
`_reel_production_state` to `assets`, `_writer_display_state` and `_assembler_display_state` to
`dashboard` (they serve `/create` and `/assemble`).

**4. Rewrite the 31 closure references.** `db_path` → `current_app.config["DB_PATH"]`,
`config_dir` → `current_app.config["CONFIG_DIR"]`. Then `app.config[...]` →
`current_app.config[...]` throughout the moved code. Since `current_app` requires an
application context, any moved helper called from a background thread rather than a request
would break — none of the 48 currently are, but confirm per domain rather than assuming, and
if one is, pass the path in as a parameter instead.

**5. Fix imports.** Each module imports only what it uses. Do not copy `app.py`'s import
block wholesale; that would reintroduce the coupling in eighteen places.

**6. Register and verify.** Add to `register_blueprints`, then:

```bash
PYTHONPATH=src python3 scripts/route_parity.py --check docs/reviews/route-baseline.json
PYTHONPATH=src python3 -m pytest -q
```

Parity must pass at **every** commit, not merely at the end. A domain that has not moved yet
still has its routes registered from `app.py`; a domain that has moved has them from its
blueprint. Either way the table is identical, so a parity failure means a route was dropped,
renamed, or had its converters changed — catch it in the commit that caused it.

**7. Walk the surface in a browser.** Click every button on the migrated domain's pages
before moving to the next domain. Route parity proves the rules exist; it does not prove the
handler still works.

---

## Route parity tooling

`scripts/route_parity.py` ships with this correction. It snapshots every URL rule and its
methods from a live `create_app()` and diffs against a baseline, reporting missing, added, and
method-changed rules. It has been verified against the tree at `2b793f1` (173 rules — 172
routes plus Flask's `/static`) and verified to fail correctly on an injected discrepancy.

**Capture the baseline before touching anything:**

```bash
git checkout <pre-refactor commit>
PYTHONPATH=src python3 scripts/route_parity.py --write docs/reviews/route-baseline.json
git add docs/reviews/route-baseline.json
```

Commit the baseline. It is the contract for the whole refactor, and it must come from the
pre-refactor tree — regenerating it mid-migration would launder exactly the error it exists
to catch.

Then add a test so parity is enforced by the suite rather than by discipline:

```python
def test_route_table_matches_baseline():
    """The blueprint split must not alter the route table. See
    CORRECTION-app-blueprint-split-v1.0."""
    import json, subprocess, sys
    result = subprocess.run(
        [sys.executable, "scripts/route_parity.py", "--check",
         "docs/reviews/route-baseline.json"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout
```

After the refactor completes, this test stays. Any *intentional* future route change updates
the baseline in the same commit, which makes route changes visible in review instead of
incidental.

---

## Sequencing

Ordered by ascending risk, so the pattern is proven on cheap domains before the expensive
ones. Commit numbers are the commit sequence, not priorities.

| # | Commit | Rationale |
|---|---|---|
| 0 | `scripts/route_parity.py` + baseline + parity test | The gate must exist before the first move |
| 1 | `web/__init__.py` + `web/context.py`, `app.py` delegates to it | Shared surface first; no routes move yet — suite green proves the four helpers converted cleanly |
| 2 | `metrics` (2 routes) | Pilot. Smallest domain; proves the whole procedure end to end |
| 3 | `materials` (5) | Small, isolated |
| 4 | `library` (4) | Small; touches the module review gate — walk it carefully |
| 5 | `proposals` (5) | Small |
| 6 | `sources` (4) | Small; resolve the `/api/sources/discover` grouping question here |
| 7 | `research` (4) | Small |
| 8 | `metrics`…`research` review checkpoint | Tag on GitHub, operator observation pass before continuing |
| 9 | `voices` (6) | Self-contained setup surface |
| 10 | `reference_assets` (7) | Self-contained; gated registry — verify approve/retire/new-version all work |
| 11 | `soundtrack` (6) | Extracted from the `/api/assets/` prefix; verify no route collision with `assets` |
| 12 | `publish` (5) | Touches Buffer; verify against the recent thread publish fix at `2b793f1` |
| 13 | `composition` (4) | Includes `gate3`; 181-line `_build_composition_plan` moves here |
| 14 | `workbench` (7) | `_register_legacy_candidates` (91 lines) moves here |
| 15 | `inspiration` (8) | First of the larger domains |
| 16 | `ideas` (10) | `_generate_card_from_seed`, `_spawn_series_children`, `_debut_experimental_format` move here |
| 17 | `draft` (9) | |
| 18 | `assets` (24, 1,198 lines) | Large; walk the full asset surface |
| 19 | `onboarding` (58, 2,553 lines) | Largest and highest-risk; all eight playbook flows walked individually |
| 20 | `dashboard` (4) + `app.py` final cleanup | Last, because `/` and `/assemble` read across domains |
| 21 | Full-system walkthrough + changelog | |

Tag a review checkpoint on GitHub at commits 8, 14, and 19 so the operator can bring the
repo link and observations back to the architect mid-refactor rather than only at the end.

---

## Explicitly out of scope

Stated so the boundary does not erode mid-refactor:

- **No behaviour changes.** Not one. If a defect is spotted while moving code, note it and
  file it — do not fix it in a migration commit. A migration commit that also changes
  behaviour cannot be reverted cleanly, which defeats the point of the sequencing.
- **No route renames**, no path normalization, no REST tidying, no method changes. The
  parity test enforces this.
- **No `url_prefix`.** Full paths only.
- **No service-layer changes.** `src/services/` is untouched.
- **No template changes.** Templates use literal paths and must keep working unmodified;
  needing to edit a template means a URL changed, which is a parity violation.
- **No new tests beyond the parity test.** Improving coverage is worthwhile and is a
  different correction.

---

## Definition of Done

1. `src/app.py` contains `create_app()` and nothing else of substance: Flask construction,
   config population, filter and hook registration, the WAL pragma from
   `CORRECTION-repo-health-v1.0` P0-4, the transcription worker start, and
   `register_blueprints(app)`. Target under 400 lines. State the actual line count in the
   changelog.
2. Eighteen modules exist under `src/web/`, each holding one domain's routes and local
   helpers. No `@app.route` decorator remains anywhere.
3. No blueprint module imports another blueprint module. Verify with
   `grep -n "from web\." src/web/*.py` — every hit should be `web.context`.
4. `scripts/route_parity.py --check` passes against the baseline captured at commit 0, and
   the parity test is part of the suite.
5. Full suite green, with the same pass count as before the refactor. A reduced count means
   tests were skipped or deleted; account for every difference.
6. **Full human UI walkthrough by domain.** Every surface, every button, in a browser. The
   eight onboarding playbook flows walked individually. The seed-to-publish path exercised
   end to end at least once after commit 20: seed → idea gate → draft gate → workbench →
   composition ratification → asset gate → soundtrack decision → schedule. Route-level tests
   do not satisfy this.
7. Each of the eighteen migrations is its own commit with parity passing at that commit, so
   any single domain can be reverted without unwinding the others.
8. CHANGELOG entry recording the before and after line counts of `app.py`, the eighteen
   modules with their route counts, and the walkthrough evidence. `PROGRESS.md` updated.

---

## Note for the operator

This refactor changes no behaviour and adds no features. Every surface should look and work
exactly as it does today; the parity test and the walkthrough exist to prove precisely that.
If anything looks different after a checkpoint tag, that is a defect to report, not an
improvement to accept.

Expect it to span several sessions. Commits 2–8 are the cheap ones and will move fast;
commits 18 and 19 are the two large domains and warrant their own sessions with unhurried
walkthroughs. The review checkpoints at commits 8, 14, and 19 are the natural points to bring
the repo link back for an architect pass.
