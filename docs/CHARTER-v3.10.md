# ViralFactory Charter — v3.10

*The constitution of the system. Any AI or collaborator reads this before working on it.*
*v3.10 — 2026-07-23 — supersedes v3.9. Incorporates AMENDMENT-014 (`docs/decisions/AMENDMENT-014-two-phase-composition-plan-and-ratification.md`) — two-phase assembly: a CompositionPlan declaring every video element as structured data, per-element local previews, and a composition ratification sub-gate between manifest freeze and render. All prior amendments through AMENDMENT-013 remain in force. AMENDMENT-014 extends AMENDMENT-013's manifest freeze with a composition plan and ratification step; it does not weaken component approval, manifest freeze, or Gate 3. Repo location: `docs/CHARTER-v3.10.md`.*

## What this is

**ViralFactory** is a generic content co-creation system for entrepreneurs who have ideas and domain experience but don't produce content themselves. **StackPenni** — a Caribbean AI + wealth brand (X / Instagram; sub-brands Island Futurist, Digital Sou-Sou, Caribbean Receipts) run by Daimon — is tenant #1. Paying customers are a real near-term plan; their timing is decided when they're real, not hypothesized now.

**The harness is code; the business lives entirely in config and modules.** Nothing business-specific is ever hardcoded. A second business onboards with zero code changes.

**Fresh start.** ViralFactory is a new app, new database, new repo. The prior StackPenni v2 pipeline keeps running at its own address until ViralFactory is production-ready; no v2 code, schema, or data is reused. **The v2 database is backed up before any decommission**, and the Sources Engine retains an optional deferred bulk-import path — "not migrated" never means "destroyed."

## North Star

A machine that co-creates viral-capable content with a person who supplies ideas and taste. Output must read — **and look** — as made by a specific human for a human, rooted in that person's lived domain, at a pace sustainable for a solo, non-developer operator.

## The human role: originate + react + edit + lived material

The system never *requires* the person to produce. It defaults to AI production and supports four input modes:

1. **Seeds** — ideas, opinions, stories, real numbers. Spoken or typed; a 30-second voice note is a perfect seed; messy is fine.
2. **Reactions** — taste as recognition. Plain-words feedback via typed text and tap/click chips where chips genuinely speed things up. The drafter self-audits against the Tells Checklist, auto-fixes flagged items, and passes a second-AI alignment check before the person judges the result at Gate 2.
3. **Direct edits** — when the person writes or rewrites draft text themselves, their text is **authoritative** and overrides the AI draft. Direct edits are the strongest voice signal and enter the Feedback Log at the highest weight. The system supports and encourages this mode. (Patterns extracted from direct edits still reach the Voice Profile through the gate as proposals — evidence, not silent self-update.)
4. **Lived material** — phone footage, receipts, screenshots, real artifacts. No craft required.

## Interaction & interface principles

- **Laptop-first, mobile-friendly.** The primary operator works on a laptop (1280px+); every screen scales responsively to mobile. Mobile-friendliness is a hard requirement for future customers, not an afterthought — but it does not constrain the primary design.
- **Voice available everywhere, assumed nowhere.** Every input point offers recording; typed text and chips are equal citizens.
- **Evidence beside every AI claim.** Proposals, flags, scores, and trend labels always show their supporting evidence. Provider, endpoint meaning, region, metric, and observation time travel with external evidence; recommendation, popularity, trend, usage rights, and causal interpretation are never treated as synonyms.
- **One-go intake.** All human materials are gathered in a single onboarding session; afterward the system returns to the person only for reactions, edits, and gate decisions.

## The repeatability rule

**If an AI does something once in a chat, it must be written down as a playbook the system can run for user #2.** Onboarding is itself a pipeline with the same gates as everything else.

## The Onboarding Engine (playbooks)

For every module there is a **playbook**: procedure + prompt templates + output schema + gate, as text files in `playbooks/`, executed by a generic runner. Material-agnostic intake with fallbacks (e.g., guided spoken interview when a user has no corpus). Calibration closes every playbook — no module reaches v1 without the person's confirmation. The eight playbooks: Business Profile intake · Voice Profile builder · Sources Engine · Viral Patterns starter · Audience Insights · Story Frameworks · Format Guide · Visual Style intake. Production processes (e.g., the viral-content production playbook) are versioned Process Registry compositions consuming those modules, not ninth onboarding cards. Every playbook carries `playbook_type` metadata distinguishing onboarding from production from learning. (AMENDMENT-009) The Visual Director and Soundtrack Planner are production processes registered in the Process Registry with `playbook_type: production`. They are Assembler-side planning steps, not audience-copy generators. (AMENDMENT-010)

## What makes content read and look human

1. **A specific detail only this person could know, in every piece** — the human seed; the single biggest lever.
2. **Voice from real samples, not adjectives** — natural speech weighted highest; dialect preserved, never sanitized; concrete patterns with verbatim evidence.
3. **A human pass** — reactions or direct edits against the drafter's self-audit. AI tells are rhythm and structure; the Tells Checklist lives in the Voice Profile.
4. **Real footage anchors visual trust** — generated video (Veo-class) is the supporting, preferably stylized layer; platform AI-disclosure rules followed.

**Humanness is built in, not sprayed on.** No bolt-on humanizer step, ever.

## The living modules (the accumulating intelligence)

Eight versioned markdown documents per business in `modules/{business}/` — the system of record, gate-only writes, schema-checked on load, provenance per entry. Fully standalone — ViralFactory has its own database; no OB1 dependency. Loaded into every draft:

1. **Voice Profile** (incl. Tells Checklist) · 2. **Viral Patterns Playbook** · 3. **Story Frameworks** · 4. **Format Guide** · 5. **Audience Insights** · 6. **Feedback Log** · 7. **Visual Style Guide** · 8. **Source Bank** (+ its Source Criteria)

## The core loop

1. **Gather** — automated, **configured by onboarding**: the person's onboarding inputs (seed sources, anti-examples) produce the Source Criteria and `sources.yaml`, which dictate what the AI scouts from then on. The Sources Engine ingests and scores every item against those criteria; the continuous loop proposes new sources and criteria amendments through the gate. New sources from RSS feeds and research enter with `status='new'` and require operator review before feeding ideation (DIVERGENCE-007). Only `status='active'` sources feed idea generation.
2. **Ideas** — generation is **grounded in the living modules**, not just raw source material: AI-originated ideas are produced by crossing Source Bank items with the Viral Patterns, Audience Insights, Story Frameworks, and Format Guide modules. Cards come from three origins, each tagged with provenance:
   - **ai-originated:** AI proposes from the Source Bank × modules
   - **human-seeded:** the person's raw seed (spoken or typed; messy is fine)
   - **human-seeded, ai-developed:** the person's seed sharpened by AI — angle variants proposed, supporting Source Bank material attached. This is the primary path; the person supplies sparks, never finished ideas.
   Each card carries: the idea, its hook/title options, a **treatment** (scope, format from the Format Guide — including experimental formats debuting on the card, capture-required tasks with **capture policy** (capture_required, capture_preferred, archive_preferred, stock_allowed, generated_allowed, or text_card per capture task, approved with the treatment at Gate 1), reuse links, rationale), origin, and source_refs (Source Bank record IDs that ground this idea). Cards approved with outstanding `capture_required` tasks carry a blocking capture flag for final compliance — drafting, VO, media planning, and preview rendering may continue, but Gate 3 readiness is blocked until the real capture is registered and mapped, or the operator changes the policy through an authoritative treatment revision. (AMENDMENT-009) **The format and platform set are locked from the treatment at Gate 1. No code in the pipeline re-derives them.**
   **GATE (rigorous):** approve / kill / park per card. The funnel kills most here — by design. Kill reasons logged to the Feedback Log.
3. **Draft** — AI, all modules loaded, self-audited against the Tells Checklist, **auto-fixes flagged items**, and passes a **second-AI alignment check** (max 3 rounds) before the human sees it at Gate 2. A draft is: **complete per-platform text in voice + light visual direction** (image prompts, reference notes, shot/format choices per the Visual Style Guide). The Writer produces all platform variants in one pass — the format and platforms come from the locked treatment, not re-derived in code. **No rendered images at this stage** — visual direction is text; render cost is only spent on survivors. *(Amendable: if co-production evidence shows drafts can't be judged without pixels, a single rough reference render per draft may be added via a future amendment — evidence first.)*
   **GATE (the human pass, unchanged from v3.1):** react via chips + text and/or direct edits (authoritative, highest Feedback Log weight); AI revises; **ship-forward or kill.** The self-audit flags and their fixes are shown to the human for transparency.
4. **Assets** — for surviving drafts only: the system plans required component roles, generates immutable candidates, and presents a **Component Workbench** before assembly. The operator reviews and approves exact versions of narration, visual media, soundtrack, source sound/SFX, typography, graphics, and format-declared elements. Category completeness is computed mechanically. The operator then freezes an immutable manifest containing the approved Writer/VO/module/config hashes and exact selected artifact versions. **The Assembler consumes only that manifest and does no audience-copy generation.** It may use schema-validated LLM judgment for component planning, edit planning, and compliance review, but may never generate or revise audience-facing content. The format and platform set remain locked from Gate 1. A compliance contract defines every required narrative beat and planned representation; final review checks the exact rendered artifact against the Writer contract and manifest. A bounded remediation loop may fix safe media/plan/render defects but never approved text or silently substitute an unapproved component. Any changed component requires a new manifest and render. (AMENDMENT-008, AMENDMENT-009, AMENDMENT-013)
   A **Visual Director** step translates Writer visual intent plus approved measured VO timing into concrete `visual_events[]`. A soundtrack plan makes audio intent explicit; rights-valid discovery, local acquisition, and candidate preview mixing may run before assembly. Discovery metadata never implies synchronization/republication rights. Only exact, current, locally hashed, rights-valid, cost-approved candidates may be selected. Soundtrack selection occurs in the Component Workbench using a representative approved-VO-under-bed preview; source sound and SFX are separately declared roles. (AMENDMENT-010, AMENDMENT-011, amended by AMENDMENT-013)
   **COMPONENT SUB-GATE (before assembly, per platform):** review/select/reject/regenerate exact component versions by category; freeze only when every required role is complete. Ingredient approval answers "use this exact version" and does not approve the final piece. After freeze, a **CompositionPlan** declares every element of the video (text, audio, visual, graphics, transitions, canvas) as structured data with per-element previews; the operator **ratifies the composition plan** before render begins. Ratification binds the composition spec hash; any change invalidates and forces re-ratification. **GATE 3 (after assembly, quick):** approve / fix / kill the exact final artifact. Gate 3 binds final artifact hash + manifest hash + ratified composition spec hash + required evidence. Any component, Writer, VO, timing, module, composition, or render-config change creates a new manifest/composition/render and invalidates Gate 3 approval. Paid acquisition still requires separate fresh cost approval. (AMENDMENT-013, AMENDMENT-014)
5. **Publish** — **every piece passes human approval before posting. No auto-publish, ever, at any trust level. Hard rule.** Go/hold + timing only; everything upstream is already approved. Approved pieces flow to Buffer for scheduling, posting, and metrics. *(Postiz→Buffer swap per DIVERGENCE-008, operator confirmed.)*
6. **Learn** — two loops (below)
7. **Improve** — gate-approved proposals update modules; every future draft inherits them

Gate intensity tapers: Ideas is rigorous, Draft is the deep human pass, the Assets Component Workbench is deliberate selection followed by quick exact-artifact Gate 3 review, and Publish is go/hold. The Component Workbench is a conditional sub-gate inside Assets, not a fifth content stage. The four content stages remain Ideas, Draft, Assets, and Publish. (AMENDMENT-013)

The system retains four AI responsibilities — Researcher, Writer, Assembler, Analyst — but operator navigation is organized by human jobs, not one tab per profile. Inspiration is a Researcher-owned workbench, not a fifth profile. The primary groups are `Home · Inspiration · Pipeline · Knowledge · Results · Setup`; Pipeline contains Ideas, Drafting, Assets, and Publish/Results transitions. (AMENDMENT-006, clarified by AMENDMENT-012)

| Operator surface | Primary route | AI owner | What happens here |
|---|---|---|---|
| Inspiration | `/inspiration` | researcher | Read current external creative observations; no automatic promotion |
| Pipeline · Ideas | `/ideas` | researcher | Gate 1: approve/kill/park idea cards |
| Pipeline · Drafting | `/create` | drafter/writer | Gate 2: review draft, edit, ship or kill |
| Pipeline · Assets | `/assemble` | assembler production processes | Component Workbench: approve exact inputs and freeze manifest; Gate 3: approve/fix/kill exact final artifact |
| Results / Publish | `/published` | analyst | Gate 4: go/hold, metrics, learning loops |

## Provenance requirement

`origin` (ai-originated | human-seeded | human-seeded-ai-developed), `format`, and `scope` travel with a piece from idea card to Results. The nightly performance note records them, so the inward loop can answer: do the operator's seeds outperform AI-originated ideas? Do certain formats or scopes perform better? These are measurable claims of the whole product thesis — they must be instrumented from the first piece.

## The learning system (two loops, one asynchronous gate)

**Inward loop** — generated on a schedule (weekly): results + Feedback Log (direct edits weighted highest) → specific proposed module updates with evidence and exact diffs.

**Outward loop — continuous from v1, not deferred.** Scheduled research of the domain: monitors the sources/channels/queries the Sources Engine maintains and writes append-only external observations with provider, endpoint meaning, platform, region, metric, and time. The Inspiration workbench renders those observations without converting recommendation into trend or trend into rights. Researcher analysis of hook/structure/format/emotion/pacing is stored **as hypotheses, never facts**. Nothing flows automatically from Inspiration: explicit operator actions create Source Bank candidates, experiment proposals, or module proposals, each retaining evidence and its existing gate. (AMENDMENT-012)

**The Gate is a persistent asynchronous queue,** not a scheduled sitting. Proposals accumulate; the person clears them when ready. Rules:
- Every card shows its age; staleness is always visible.
- A newer proposal touching the same module section supersedes the older one (marked, not deleted).
- No deadlines, no pressure mechanics. If the queue grows faster than it clears, the proposals are too weak or too many — **fix the proposal prompt, never pressure the person.**
- Own-account data is small and noisy: no automatic optimization; autonomy is earned as proposals prove out, never assumed.

## Build architecture

- **Claude = architect**: designs, documents, reviews; speaks only through versioned files in the repo.
- **Hermes agent (open-source models, VPS) = builder**: works BUILD_PLAN top-down under its guardrails; never decides design.
- **GitHub = the channel**: one repo for code and docs; divergences filed in `docs/decisions/`; architect reviews land in `docs/reviews/`.
- **LLM backend swappable in config** (`models.yaml`): Ollama local/cloud or external API; processing at temperature 0; the drafter backend chosen by blind A/B on voice quality at the M3 checkpoint.
- **The operator directs in plain language and gates. Never writes code.**

## Document hierarchy (conflicts are divergences, never silent overrides)

1. **Charter** (this file) — principles and design rules. Amended only via `docs/decisions/` → architect review → version bump.
2. **BUILD_PLAN.md** — tasks, order, guardrails. Conforms to the charter.
3. **docs/CONTEXT.md** — the operational mirror: shared language and current implementation state. Conforms to charter and plan; a conflict is a bug or a divergence to file.
4. **CHANGELOG / docs/decisions/** — the record. Feeds charter revisions; does not govern alone.

## Design rules (durable — amend only via a filed divergence)

- Human originates, reacts, edits when they choose; AI produces by default; production is never required of the person.
- Nothing hardcoded: judgment → playbooks/prompts; values → config; mechanics → deterministic libraries; taste → the person.
- One drafter, no model mixture. No bolt-on humanizer. No hand-built distributed state machine.
- AI proposes, human gates — everywhere, including onboarding. Per-piece approval before publish is absolute.
- Every LLM step = prompt template (in repo) + output schema + validator + provenance log. Content-hash caching; unchanged input is never re-judged.
- No patch scripts: wrong output → fix prompt, config, or validator, versioned.
- The Voice Profile is the first module built and the last thing compromised.
- Add complexity only when real volume forces it.
- **The format and platform set are locked from the treatment at Gate 1. No code in the pipeline re-derives them with keyword heuristics or regex parsing.** (AMENDMENT-007)
- **The Writer produces all per-platform text and semantic intent; the Assembler does no audience-copy generation.** The Media Planner owns provider-aware production prompts and may use schema-validated LLM judgment for media planning, edit planning, and compliance review. It may never generate or revise audience-facing content. (AMENDMENT-007, clarified by AMENDMENT-009)
- **An AI review loop (self-audit fix + second-AI alignment check, max 3 rounds) runs before Gate 2.** The human is still the final gate. (AMENDMENT-007)
- **A compliance contract and bounded final-output remediation loop (max 3 rounds, config-driven cost cap) runs on the Assembler side.** It can fix media/plan/render defects but never modifies approved `platform_content` text. If approved content cannot fit the format, it escalates to `needs_operator_decision`. The operator sees the full remediation history. (AMENDMENT-008)
- **Capture policy is approved with the treatment at Gate 1.** `capture_required` blocks final compliance and Gate 3 readiness; drafting and planning continue. No generated substitute may represent required real evidence. The operator may change the policy through an authoritative treatment revision. (AMENDMENT-009)
- **The hash-lock protects the entire approved Writer contract** — not only `platform_content` text but semantic beats, evidence references, visual/audio intent, capture policy, and primary audience action. Any remediation or planning action that would change these fields is rejected and escalated. (AMENDMENT-009)
- **Production playbooks are Process Registry compositions, not onboarding cards.** Every playbook carries `playbook_type: onboarding | production | learning` metadata. The Onboarding UI filters mechanically on `playbook_type: onboarding` and fails closed on missing metadata. (AMENDMENT-009)
- **The operator-facing route and the autonomous chain must call the same services.** Two code paths producing different outputs from the same input is a defect. (AMENDMENT-010)
- **Skipped evidence is not pass.** `ready_for_operator` requires all required evidence present and non-skipped. Missing evidence → `needs_operator_decision`. (AMENDMENT-010)
- **Every Reel has an explicit soundtrack mode.** VO-only requires a rationale and operator approval. Silent VO-only is not valid. (AMENDMENT-010)
- **Soundtrack discovery evidence is not a licence.** Only rights-valid, locally acquired, hashed, operator-selected media may enter a frozen manifest. Component selection approves the exact ingredient; Gate 3 separately approves the exact final mix. Changing the track creates a new manifest/render and invalidates Gate 3 approval. Paid acquisition requires fresh cost approval before spend. (AMENDMENT-011, amended by AMENDMENT-013)
- **External observation semantics are immutable evidence.** Provider, endpoint meaning, platform, region, metric, rank, and observation time travel with a claim. Recommendation, popularity, measured trend, production rights, and creative interpretation remain distinct. (AMENDMENT-012)
- **The CompositionPlan declares every element of the final video.** Text, audio, visual, graphics, transitions, and canvas are each structured as typed elements with exact source hashes, timing, position, style, and animation. The plan is generated mechanically from the frozen manifest and approved Writer contract. It is provider-neutral and contains no vendor-specific fields. (AMENDMENT-014)
- **Per-element previews are generated locally before ratification.** Text specimens, audio waveforms, visual thumbnails, graphics frames, transition diagrams, and a full timeline diagram are produced from the CompositionPlan using local tools. Previews are evidence for ratification, not final artifacts. No provider API is called for preview generation. (AMENDMENT-014)
- **Composition ratification is a sub-gate between manifest freeze and render.** The operator reviews previews and ratifies or rejects the CompositionPlan. Ratification binds the spec hash. Any change after ratification creates a new spec and invalidates ratification. Ratification does not approve the final artifact — Gate 3 still does. (AMENDMENT-014)
- **Assembly consumes only a ratified CompositionPlan.** The RendererSpec is compiled from the ratified plan. An unratified, stale, rejected, or hash-mismatched plan fails closed. The provider renders only from the ratified spec. (AMENDMENT-014)
- **Inspiration never silently teaches or produces.** It is a Researcher-owned evidence workbench. Bookmarking does not ground ideation; Source Bank, experiment, module, and soundtrack paths require explicit promotion and their own contracts/gates. (AMENDMENT-012)
- **Renderer styles, fonts, colors, and SFX presets come from config/modules, not Python.** Two tenants must render differently with zero Python edits. (AMENDMENT-010)
- **Captions are phrase-level (3–6 words), timed within the beat.** Full-beat captions are a defect. (AMENDMENT-010)
- **Assembly accepts only a current immutable manifest of exact operator-approved component versions.** No latest-file lookup, unlisted fallback, silent substitution, or inherited approval. Missing/stale/failed/rejected/superseded/unprobeable/rights-invalid/cost-unapproved components fail closed. (AMENDMENT-013)
- **Component approval and Gate 3 are distinct.** Component approval permits one exact ingredient to enter a manifest; category completeness proves all required roles; manifest freeze locks inputs; Gate 3 approves the exact assembled artifact. None substitutes for another. (AMENDMENT-013)
- **Production is a persisted resumable state machine per platform asset.** Human waits are durable states, not running jobs; operator and autonomous entrypoints advance the same service. (AMENDMENT-013)

## Phases

**Phase 0 — Foundations.** Fresh repo scaffolding, config system, LLM adapter, validator, provenance, cache, v2 database backup.
**Phase 1 — Onboarding engine.** Generic playbook runner; Voice Profile end-to-end with calibration; then the remaining playbooks. Tenant #1's config re-entered through onboarding (no v2 migration).
**Phase 2 — Co-production sprint.** ~10 pieces: seed → draft → self-audit → AI review loop → react/edit → ship or kill. Feedback Log grows.
**Phase 3 — Publish + metrics.** Buffer API; per-piece approval enforced in the flow; nightly metrics.
**Phase 4 — Learning loops.** Inward proposals + async gate queue; outward research + Source Bank + Experiments Queue (outward runs from v1 of this phase).
**Phase 5 — Generalization proof.** Onboard business #2 through the console with zero code changes — executed when a real second business exists; the architecture for it is enforced from Phase 0 regardless.

---

*Test for any decision: does it improve the voice, the lived detail, the person's taste signal, or the system's gated learning — for ANY user, not just tenant #1? If not, it is plumbing: keep it simple or automate it away. If an AI just did something clever ad hoc: stop and write the playbook. If reality disagrees with this charter: file a divergence.*