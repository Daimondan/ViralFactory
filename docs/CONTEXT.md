# Context: ViralFactory

> **This is an operational mirror of `docs/CHARTER-v3.10.md`.** It captures
> current shared language, workflows, and implementation state. It conforms
> to the charter and BUILD_PLAN; where it conflicts, that conflict is a bug
> or a new divergence to file — never a silent override.
>
> **Change triggers:** stage added/removed/renamed, rules changed, new
> automation, paths changed, interface changed, workflow changed,
> terminology changed.
>
> **On change:** bump `updated_at` date, add/update a decision note in
> `docs/decisions/` if the change is non-obvious.

**Updated:** 2026-07-23 (AMENDMENT-014: two-phase assembly — CompositionPlan with per-element previews and a composition ratification sub-gate between manifest freeze and render. Charter bumped to v3.10. Build order updated to VF-CW-001..010 → VF-CP-001..004 → VF-RA-001..004 → VF-CW-011..012. DIVERGENCE-019 reference recreation evidence preserved: both providers rendered one frozen composition; neither selected.)
**Conforms to:** `docs/CHARTER-v3.10.md` (v3.10 — all prior amendments through AMENDMENT-013 remain in force; AMENDMENT-014 adds a CompositionPlan with per-element previews and a composition ratification sub-gate between manifest freeze and render; rights/cost/evidence rules remain; AMENDMENT-013's ingredient selection before assembly and final-artifact Gate 3 are preserved)

---

## Purpose

ViralFactory is a **generic content co-creation system** that turns a person's ideas and taste into published content that reads and looks human — made by a specific person for a human, rooted in their lived domain. The person supplies seeds (spoken or typed ideas), reactions (taste), and lived material. The system drafts in their real voice, publishes, measures, researches what goes viral in their domain, and proposes its own improvements — every improvement passing a human gate.

The system is generic: **the harness is code, the business lives entirely in config and modules.** A second business onboards with zero code changes.

**StackPenni** (Caribbean AI + wealth brand on X/IG, run by Daimon) is user #1. Paying customers are a real near-term plan.

## Users

- **Primary user (v1):** Daimon, operating StackPenni. Laptop-primary. Not a developer. Supplies seeds and taste; sometimes writes/edits directly.
- **Future users (near-term):** Paying customers — other entrepreneurs who have ideas and domain experience but don't produce content themselves. These users may be mobile-primary. The system must be mobile-friendly for them.
- **Architect (Claude):** Designs the system, writes/updates the charter, playbooks, and build plan. Reviews builder work. Not a daily user.
- **Builder (Hermes agent):** Implements the build plan task by task. Open-source models on the VPS.

## North Star

A machine that co-creates viral-capable content with a person who supplies ideas and taste but does not produce. Output must read — and look — as made by a specific human for a human, rooted in that person's lived domain, at a pace sustainable for a solo, non-creator, non-developer operator.

## The Human Role: Originate + React + Edit + Lived Material

The system does not assume the person can write, design, or edit. But it **supports and encourages** direct editing when they choose to. Four input modes:

1. **Seeds** — ideas, opinions, stories, real numbers. Spoken preferred (30-second voice note is a perfect seed); typed accepted. The system builds the finished piece around the seed.
2. **Reactions** — taste as recognition, not creation. The person doesn't fix drafts; they react in plain words ("that word isn't me", "too polished", "ending is weak") via typed text or tap chips where it makes sense. Reactions feed the Feedback Log.
3. **Direct edits** — when the user writes or rewrites draft text themselves, the system treats this as authoritative. Human text overrides AI draft. Direct edits are the strongest voice signal and feed the Feedback Log with higher weight than chip reactions.
4. **Lived material** — phone footage, receipts, screenshots, real artifacts. No craft required.

## Shared Language

### ViralFactory
The generic content co-creation system (the harness/code). Not specific to any business.

### StackPenni
The first business using ViralFactory. All StackPenni-specific values (brand name, topics, feeds, queries, voice, audience) live in config and modules, never in code.

### Seed
A spoken or typed idea/take/story from the user. In the staged pipeline, a seed becomes a **human-seeded** idea card (or a **human-seeded-ai-developed** card when the AI sharpens it). A seed can produce multiple pieces (different platforms/formats).

### Idea card
The first artifact in the staged pipeline. Each card carries: the idea, hook/title options, a **treatment** (scope: one-off | series-of-N | pillar-with-derivatives; format from the Format Guide — including experimental formats debuting on the card; capture-required tasks; reuse links; rationale), origin tag (`ai-originated` | `human-seeded` | `human-seeded-ai-developed`), and **source_refs** (JSON list of `sources.id` — one or more Source Bank records that ground this idea). `evidence_links` is a derived display field resolved from the referenced source rows, not the grounding mechanism. Every idea cites at least one source by ID; one idea may compose multiple sources into a single story. Treatment is approved WITH the idea at Gate 1 — not developed after. **The format and platform set are locked from the treatment at Gate 1 — no code in the pipeline re-derives them** (AMENDMENT-007). Capture tasks are a **non-blocking flag** on the card (per AMENDMENT-006 — awaiting-capture is deprecated as a blocking state; cards with capture tasks flow through approved → Writer like any other). Gate 1 (rigorous: approve/kill/park) decides which cards proceed to production. **Gate 1 approval triggers the Writer chain automatically** — the Writer produces complete per-platform text, runs the AI review loop, and stops at `draft_ready` for Gate 2 human review. Publishing is never automatic.

### Treatment
The decision of how an idea becomes a piece — scope, format, capture needs, reuse, and rationale. Lives ON the card, approved AT Gate 1. The human may edit any part at the gate (direct-edit authority). Compact treatment line (scope · format · capture flag) shown on cards for fast kills; full treatment expands on demand. Not a new stage or gate — it's a property of the card.

### Origin
The provenance tag that travels with a piece from idea card to Results: `ai-originated`, `human-seeded`, or `human-seeded-ai-developed`. Along with `format` and `scope`, the nightly performance note records them so the inward loop can answer: do the operator's seeds outperform AI-originated ideas? Do certain formats or scopes perform better? Instrumented from the first piece.

### Piece
A single content output — one post, one thread, one reel script, or one caption. A seed can produce multiple pieces.

### Module
One of 8 living knowledge documents (see below). Markdown files, versioned, gate-only writes. Not code.

### Gate
A human approval checkpoint. Three types:
- **Content gates (four, in the staged pipeline):** Gate 1 (Ideas — rigorous: approve/kill/park per card), Gate 2 (Draft — the human pass: chips + text + direct edits; ship-forward or kill), Gate 3 (Assets — quick, per-platform: approve/fix/kill), Gate 4 (Publish — go/hold + timing only). Gate intensity tapers: Ideas is rigorous, Draft is deep, Assets is quick, Publish is go/hold.
- **Async proposal queue:** Module updates, source proposals, experiments accumulate in a persistent queue. Daimon clears them when ready — not on a schedule. Every card shows age ("submitted N days ago"). Newer proposals on the same module section supersede older ones (marked, not deleted). No deadline or pressure mechanics. If the queue grows faster than it clears, the proposals are too weak or too many — fix the proposal prompt, never pressure the person.

### Ship
A piece Daimon approves goes to the publish queue (Buffer). Does NOT mean immediately posted — Buffer schedules per the Format Guide's timing rules. *(Postiz→Buffer swap per DIVERGENCE-008.)*

### Playbook
A written procedure (markdown) + prompt templates + output schema that the system's AI executes for any user. The generic playbook runner reads and executes these. Playbooks are text files in `playbooks/`, not code.

### Onboarding
The one-time setup that builds all 8 modules from the user's materials. Not a single session — it's a flow with multiple gates (calibration, confirmation). Realistic estimate: 1–2 sessions over a few days.

### Direct edit
When the user writes or rewrites draft text themselves. The system treats this as authoritative — the human's text overrides the AI draft, and the edit feeds the Feedback Log as a strong voice signal.

### AI Profiles
AI work runs under **named profiles** — Researcher (ideation, source scouting, social-media-native), Drafter (takes the approved, fully-specified idea and produces the final asset), and Analyst (reads results, drives the inward/outward loops, scrapes news into the Source Bank). Profiles are compositions of prompts, module views, and model settings defined in `config/profiles.yaml`, per AMENDMENT-005. They are named compositions, not code classes. Each pipeline LLM call declares the profile it runs under; the adapter resolves model/temperature through the profile → `models.yaml` roles. Provenance rows record which profile produced each artifact.

### Visual Director
An Assembler-side, schema-validated production process that translates approved Writer `visual_intent` plus measured VO timings into concrete `visual_events[]`. It plans visual jobs; it never creates or revises audience-facing copy. It is registered in the Process Registry with `playbook_type: production`.

### Soundtrack plan
A versioned production contract linked by `contract_id` that makes each Reel's audio mode explicit: `vo_only`, `music_bed`, `source_sound`, or `vo_plus_bed`. The planner supplies search intent; configured adapters gather observations; an independent rights record determines whether an exact recording may be acquired and synchronized; only a non-empty, measured, hashed local artifact enters FFmpeg. Preview discovery/mixing may run automatically, but Gate 3 approves the exact active soundtrack-bearing asset. Switching track creates a new asset version and invalidates prior Gate 3 approval. VO-only shows its rationale at Gate 3. Paid acquisition still requires fresh cost approval before spend. Discovery API access is never licence evidence. (AMENDMENT-011)

### Inspiration
A top-level Researcher-owned operator workbench at `/inspiration`, not a fifth AI profile and not a living module. Scheduled jobs write tenant-scoped, append-only observations with provider, endpoint meaning, platform, region, exact metric/rank, and collection time; the page reads the database and remains useful when providers fail. “Trending” and “Top” are evidence claims: chart-backed audio may say “Trending audio,” while recommendation/seed feeds say “Video inspiration” or “Provider recommendations.” The first slice is read-only. Later Bookmark, Source Bank, experiment, module, and production paths are explicit and keep their own gates/contracts. No trend audio is production-safe without AMENDMENT-011 rights resolution.

## The 8 Living Modules

Every business has 8 versioned knowledge documents, stored as markdown in `modules/{business}/`, loaded into every draft, updated only through the human gate:

1. **Voice Profile** (incl. Tells Checklist + cognitive patterns) — how this person sounds and thinks: expression patterns, dialect/register, mental models, obsessions, contrarian takes, story instincts, frame, and user-specific AI tells
2. **Viral Patterns Playbook** — what works in this domain (hypotheses, not facts)
3. **Story Frameworks** — how to tell a story per subject type
4. **Format Guide** — which format fits which message on which platform
5. **Audience Insights** — who the content is for and what they respond to
6. **Feedback Log** — accumulated reactions and direct edits (voice signal)
7. **Visual Style Guide** — brand look + real-vs-generated blend rules
8. **Source Bank** — trusted sources, self-growing, self-pruning. New sources from RSS feeds and research enter with `status='new'` and require operator review before feeding ideation (DIVERGENCE-007). Only `status='active'` sources feed idea generation. Operator materials enter as `active` immediately (intentionally created). The Source Bank page (`/sources`) shows all sources with filter buttons and bulk Keep/Remove for new items.

Every module has: a fixed schema, a version number, a provenance note, and an update path through the gate.

> **Modules carry rules; the Source Bank carries material.** Rules are task-typed — they apply to every piece of a given kind regardless of topic — so prompt context from modules is selected *structurally* (declared sections/entries per prompt, `prompts/views.yaml`), never by call-time summarization or similarity retrieval. Call-time compression of a module would create an ungated derivative of a human-approved document; the curation loop (learning proposals → operator gate) is the only compressor. Material is topic-typed, so similarity retrieval is a legitimate future selector for the Source Bank specifically. Character ceilings on assembled module context exist only as logged tripwires, never as the selection mechanism.

## Core Workflows

### The Core Loop (staged pipeline — four content gates)
```
GATHER (automated — configured by onboarding)
Sources Engine scouts per the person's seed sources + anti-examples
ingests + scores every item against Source Criteria
new sources enter status='new' → operator review → status='active'
        │
        ▼
INSPIRATION (parallel Researcher observatory)
scheduled provider observations → truthful audio/video evidence labels
read-only first slice; no automatic Source Bank/module/production transfer
        │ explicit later promotion only
        ▼
IDEAS  ◄── living modules ground idea generation
cards from 3 origins: ai-originated · human-seeded · human-seeded-ai-developed
ai-originated = Source Bank × Viral/Audience/Story/Format modules
each card: idea + hook options + treatment (format + platforms LOCKED here) + origin tag + source_refs
        │
        ▼
■ GATE 1 — RIGOROUS: approve / kill / park per card
  the funnel kills most here, by design — kill reasons → Feedback Log
  APPROVAL = PRODUCTION TRIGGER (Writer chain auto-starts)
  format + platforms LOCKED from treatment — no code re-derives them
        │
        ▼
WRITER CHAIN (auto-produced)
AI, all modules + grounding sources loaded
produces COMPLETE PER-PLATFORM TEXT in one pass (all platforms from treatment)
self-audits against Voice Profile + shared AI Tells Catalog → auto-fixes HIGH-confidence tells with concrete revised text
second-AI alignment check against approved idea + surviving HIGH-confidence AI tells (max 3 rounds)
= per-platform content in voice + LIGHT VISUAL DIRECTION (prompts, refs, format)
  NO rendered images at this stage
        │
        ▼
■ GATE 2 — HUMAN PASS: chips + text + DIRECT EDITS (authoritative)
  self-audit flags + fixes shown for transparency
  AI revises → ship-forward or kill · edits → Feedback Log (highest weight)
        │
        ▼
COMPONENT PRODUCTION (survivors only — MEDIA ONLY, no audience-copy generation)
Visual Director maps approved visual intent + measured VO to semantic visual events
requirements planner declares exact narration, visual, soundtrack, SFX, typography, graphics, and format roles
candidate versions generated/acquired with preview, provenance, rights/cost, measurements, and hashes
        │
        ▼
■ ASSETS COMPONENT SUB-GATE: review / select / reject / regenerate exact versions by category
  category completeness must pass; freeze immutable manifest of approved inputs
        │
        ▼
ASSEMBLER consumes the manifest only
phrase-level captions (3–6 words) and approved media assembled with approved Writer text
no latest-file lookup, unlisted fallback, or silent component substitution
        │
        ▼
■ GATE 3 — QUICK, PER PLATFORM: approve / fix / kill exact asset version, side by side
  exact final artifact hash + manifest hash + evidence visible
  any ingredient change creates a new manifest/render and invalidates approval
        │
        ▼
■ GATE 4 — PUBLISH: go/hold + timing only
  NO AUTO-PUBLISH, EVER, AT ANY TRUST LEVEL — HARD RULE
        │
        ▼
SHIP → Buffer publish queue → posted → metrics
        │
        ▼
LEARN
inward loop (weekly proposals) + outward loop (continuous research)
origin tag travels idea → nightly note: do human seeds outperform?
        │
        ▼
IMPROVE
proposals land in async gate queue
user clears when ready → approved = module version bump
```

### Onboarding Flow
```
BUSINESS PROFILE Q&A
        │
        ▼
VOICE PROFILE (from materials or interview fallback)
        │
        ▼
CALIBRATION GATE (3 samples → pick → react → revise)
        │
        ▼
SOURCES ENGINE (seed sources → criteria → monitoring plan)
        │
        ▼
VIRAL PATTERNS STARTER
        │
        ▼
AUDIENCE INSIGHTS
        │
        ▼
STORY FRAMEWORKS
        │
        ▼
FORMAT GUIDE
        │
        ▼
VISUAL STYLE
        │
        ▼
ALL 8 MODULES AT v1 — ONBOARDING COMPLETE
```

### Learning System (two loops, one async gate)

**Inward loop — weekly (proposals generated on schedule, cleared async):**
AI reads published results + Feedback Log → proposes specific module updates with evidence → proposals land in async gate queue → Daimon approves/rejects when ready.

**Outward loop — continuous (runs from v1):**
Scheduled research of what works in the wild: monitors top accounts/hashtags/channels → analyzes hook/structure/format/emotion/pacing → findings flow to Source Bank (self-growing), proposed module updates, and Experiments Queue.

**Honesty rules:** External virality is observable, its cause is inference — findings enter as hypotheses. Own-account data is small and noisy — no automatic optimization. Autonomy is earned as proposals prove out, never assumed.

## Business Rules

1. **Nothing business-specific in code.** Brand names, topics, feeds, queries, taxonomies, model names → `config/`. If a string describes the business, it is config.
2. **No judgment in code.** Understanding-tasks (tagging, titling, voice analysis, quality) = prompt template + JSON schema + validator. Never keyword heuristics.
3. **AI proposes, human gates — everywhere.** Modules are never edited silently. No gate, no write.
4. **Per-piece approval.** Every piece passes Daimon's approval before publishing. No exceptions, no auto-publish (even after trust is built).
5. **Direct edits are authoritative.** Human text overrides AI draft. Direct edits feed the Feedback Log as the strongest voice signal.
6. **If an AI does something clever once, it becomes a playbook.** Ad-hoc judgment that isn't captured is a defect.
7. **No patch scripts.** Wrong output → fix the prompt, config, or validator (committed and versioned). Never a one-off fix.
8. **Mechanics use boring libraries.** Content extraction = trafilatura. Don't spend LLM calls on mechanical work.
9. **Every LLM call is logged** to provenance: input hash, prompt file + version, model, raw output, validated output, validator verdict.
10. **Deterministic where possible.** Temperature 0 for processing steps; cache by content hash — unchanged input is never re-judged.
11. **Never invent module content.** Modules are built by playbooks from user materials and updated only via the gate.
12. **Prompts carry procedures; modules carry knowledge.** Any domain taxonomy embedded in a prompt file (message types, format structures, platform mappings) is a defect: baked-in taxonomy cannot learn. Prompts describe how to reason; living modules supply what is currently believed, and the loops update the modules. (Per AMENDMENT-005 + CORRECTION-format-selection-living-v1.0)
13. **Format and platforms are locked from the treatment at Gate 1.** No code in the pipeline re-derives them with keyword heuristics or regex parsing. The Writer reads them from the locked treatment; the Assembler reads them from the approved draft. (Per AMENDMENT-007)
14. **The Writer produces all per-platform text and semantic intent; the Assembler does no audience-copy generation.** The Media Planner owns provider-aware production prompts and may use schema-validated LLM judgment for media planning, edit planning, and compliance review. It may never generate or revise audience-facing content. (Per AMENDMENT-007, clarified by AMENDMENT-009)
15. **An AI review loop runs before Gate 2.** The Writer self-audits, auto-fixes flagged items, and a second-AI alignment check verifies the draft against the approved idea (max 3 rounds). The human is still the final gate. (Per AMENDMENT-007)
16. **Capture policy is approved with the treatment at Gate 1.** `capture_required` blocks final compliance and Gate 3 readiness; drafting and planning continue. No generated substitute may represent required real evidence. The operator may change the policy through an authoritative treatment revision. (Per AMENDMENT-009)
17. **The hash-lock protects the entire approved Writer contract** — not only `platform_content` text but semantic beats, evidence references, visual/audio intent, capture policy, and primary audience action. Any remediation or planning action that would change these fields is rejected and escalated. (Per AMENDMENT-009)
18. **Production playbooks are Process Registry compositions, not onboarding cards.** Every playbook carries `playbook_type: onboarding | production | learning` metadata. The Onboarding UI filters mechanically on `playbook_type: onboarding` and fails closed on missing metadata. (Per AMENDMENT-009)
19. **Operator-facing routes and the autonomous chain call the same production services.** Equivalent input must produce equivalent plans; route-specific production logic is a defect. (Per AMENDMENT-010)
20. **Skipped evidence is not pass.** Any required visual, transcript, text-integrity, semantic-coverage, or soundtrack evidence that is missing or skipped yields `needs_operator_decision`, never `ready_for_operator`. (Per AMENDMENT-010)
21. **Every Reel has an explicit soundtrack mode.** VO-only requires a visible rationale and exact-asset Gate 3 approval. Music/SFX require independent rights evidence, a validated local artifact, and exact-asset Gate 3 approval; a track switch invalidates prior approval. Fresh cost approval is required before paid acquisition. Discovery metadata is not a licence. (Per AMENDMENT-010, amended by AMENDMENT-011)
22. **Renderer presentation values live in config/modules, not Python.** Overlay styles, fonts, colors, and SFX presets must vary by tenant with zero code edits. (Per AMENDMENT-010)
23. **Captions are phrase-level.** Caption cues contain 3–6 words timed within the VO beat and must reconstruct the approved text exactly; full-beat captions are a defect. (Per AMENDMENT-010)
24. **External evidence preserves meaning.** Provider, endpoint type, platform, region, metric/rank, and collection time travel with each observation. Recommendation, popularity, trend, usage rights, and creative interpretation are distinct. (Per AMENDMENT-012)
25. **Inspiration never silently teaches or produces.** It is read-only in the first slice. Later promotion to Source Bank, experiments, modules, or production is explicit and retains the destination's gate/contract. (Per AMENDMENT-012)
26. **Assembly is manifest-only.** Every materially used narration, clip/still/capture, soundtrack, source sound/SFX, font/style, graphic, transition, or format-declared component must be an exact current operator-approved candidate in the immutable manifest. Missing, failed, stale, rejected, superseded, unprobeable, rights-invalid, cost-unapproved, or hash-mismatched inputs block assembly. (Per AMENDMENT-013)
27. **Component approval does not replace Gate 3.** Candidate approval permits one exact ingredient; completeness proves every required role; manifest freeze locks the set; Gate 3 approves the exact finished artifact. Any upstream or ingredient change requires a new manifest, render, and Gate 3 decision. (Per AMENDMENT-013)
28. **Production resumes from persisted state per platform asset.** Human waits are durable states, not long-running jobs. Operator routes and autonomous production advance the same orchestrator; one draft's first child never stands in for all platform assets. (Per AMENDMENT-013)
29. **The CompositionPlan declares every element of the final video.** After manifest freeze, a provider-neutral CompositionPlan structures every text, audio, visual, graphics, transition, and canvas element with exact source hashes, timing, position, style, and animation. The plan is generated mechanically from the frozen manifest and Writer contract. (Per AMENDMENT-014)
30. **Per-element previews are generated locally before ratification.** Text specimens, audio waveforms, visual thumbnails, graphics frames, transition diagrams, and a full timeline diagram are produced from the CompositionPlan using local tools. No provider API is called for previews. (Per AMENDMENT-014)
31. **Composition ratification is a sub-gate between manifest freeze and render.** The operator reviews per-element previews and ratifies or rejects the plan. Ratification binds the composition spec hash. Any change invalidates and forces re-ratification. Ratification does not approve the final artifact — Gate 3 still does. (Per AMENDMENT-014)
32. **Assembly consumes only a ratified CompositionPlan.** The RendererSpec compiles from the ratified plan. Unratified, stale, rejected, or hash-mismatched plans fail closed. (Per AMENDMENT-014)

## Edge Cases

- **Missing voice materials:** Interview fallback runs a 10–12 question guided spoken interview to produce a corpus from nothing.
- **Two sources disagree:** The source with higher trust score wins; both are preserved in the Source Bank with their scores.
- **Draft doesn't sound like the user:** The Tells Checklist flags it; the user reacts; the system revises. If 3 revise rounds don't converge, the piece is killed and the failure feeds the Feedback Log.
- **User directly rewrites most of a draft:** The rewrite is stored as authoritative; the AI's draft is preserved in provenance for comparison; the rewrite patterns feed the Voice Profile update queue.
- **Buffer is down:** Pieces stay in the publish queue. The system alerts but never loses data. Retries are automatic. *(Postiz→Buffer swap per DIVERGENCE-008.)*
- **Module is empty at draft time:** The drafter says so explicitly ("Voice Profile not yet built — draft will be generic"). Never fills empty modules with invented content.
- **Proposal queue gets large (>50 pending):** Group by module, show oldest first, allow bulk approve/reject for low-risk proposals (source additions, criteria amendments).
- **Generalization (customer #2):** Same playbooks run with different config. No code changes. The playbook engine handles it.

## Working Agreements

- **Definition of Done** (`docs/PROCESS-definition-of-done-v1.0.md`): Hermes does not report work as done until (1) the automated suite passes, (2) a hands-on human-style UI test in the browser exercises the changed surface as the operator would, (3) an end-to-end pass runs for flow changes, and (4) the done report states what was tested and how. "Tests pass" alone is not a done report.

## Open Questions

1. ~~**Module storage:**~~ **RESOLVED** (Divergence-002): Repo markdown (`modules/{business}/`) is the system of record — fully standalone. No OB1 dependency whatsoever. ViralFactory has its own SQLite database. Every user onboards the same way (upload materials, share docs, connect Obsidian). OB1 is not involved.
2. ~~**Publishing platform:**~~ **RESOLVED** (DIVERGENCE-008): Buffer is the publishing + analytics platform (operator confirmed cost-driven swap from Postiz). The `buffer:` block in `config/models.yaml` holds channel IDs. `src/buffer_adapter.py` is the adapter. `src/postiz_adapter.py` deleted.
3. ~~**LLM backend:**~~ **RESOLVED** (Claude review): Default Ollama Cloud for processing at temperature 0. For the drafter specifically, run an A/B at the M3 checkpoint — same seeds through two configured backends, Daimon reacts blind. Voice quality is the product; the config swap makes this a measurement, not a debate.
4. **8 modules in context window:** Load all 8 every draft (may exceed smaller model limits), or load essential 4 (Voice, Viral, Story, Format) always and pull others on demand? — *Genuinely deferrable; resolve at M3 when drafter is built.*
5. **Video generation scope:** xAI Grok for generated video, or text/image only for v1? — *Genuinely deferrable; bounded by the charter's hybrid rules (real anchors for lived claims, generated is supporting layer).*

## M13 implementation status

AMENDMENT-010 is ratified. Component implementations for M13 exist, but the first fresh live Reel (draft 11 / asset 7) proved that several were not integrated into the shared production call graph. The operator ruled on 2026-07-18 to reopen the affected tasks and complete the existing design without a new charter amendment:

- `EditPlanningService.generate_for_asset()` must consume the exact measured VO and `CueCompiler` output rather than persist a legacy plan with no VO take.
- The production path must invoke the registered Visual Director, persist validated `visual_events[]` with provenance, and run feasibility before paid acquisition and before FFmpeg.
- Every Reel must persist a soundtrack plan and stop at the operator preview/VO-only approval gate before render.
- Final review must invoke soundtrack mix, beat-aware frame evidence, and deterministic text-integrity checks; missing evidence cannot pass.
- Operator and autonomous entrypoints require a real behavioral equivalence test, not source inspection or a patched service response.
- VF-VS-702/703 remain open until a genuinely fresh deployed Reel passes the complete path, mechanical evidence, and operator review.

Charter v3.9 is now the binding target. Runtime audit on 2026-07-21 found that health/test counts do not prove completion: cards remained in `assembling`/`awaiting_soundtrack_approval`, a human decision did not coherently resume the autonomous chain, mutable inventory entered planning without component approval, multi-platform production selected the first asset, and the Gate 3 route could write approval without proving a current final artifact/manifest/evidence. AMENDMENT-013 therefore supersedes VF-VS-515's old single-Gate-3 soundtrack UX with VF-CW-001..012. The Component Workbench must close those boundaries before VF-VS-516/702/703 fresh proof.

Assembly-quality review on 2026-07-22 found a second, distinct boundary: VF-CW fixes prerequisite identity, approvals, and orchestration, but the current FFmpeg/PIL implementation is still too narrow to be the sole production-quality finish layer. Phrase captions can remain proportionally timed without word clocks; compiler transition vocabulary and renderer capabilities diverge; the render plan can lose planned SFX/source sound; caption/graphics motion, focal crops, keyframes, and audio automation are under-specified. DIVERGENCE-019 therefore inserts a provider-neutral `RendererSpec v1` after manifest freeze. Creatomate and Shotstack will render the same frozen fixtures in a blind operator bake-off; Vizard is rejected for canonical assembly because its documented API is a long-video clipping/repurposing workflow rather than exact multi-layer composition. Existing FFmpeg/PIL remains the conformance and emergency fallback. No vendor may choose/regenerate ingredients, rewrite text, publish, or report Gate 3 readiness; all outputs are downloaded, hashed, probed, reviewed locally, and bound to the current manifest/spec. BUILD_PLAN v2.3 orders VF-CW-001..010 → VF-RA-001..004 → VF-CW-011..012.

The first operator-authorized Creatomate smoke on 2026-07-23 proved template-free direct RenderScript execution and local artifact verification. Two successful five-second portrait jobs were downloaded; both reported `render_scale: 0.5` and 270×480 output from a 540×960 composition even when scale 1 was explicitly requested. Visual inspection found no watermark but suggested font fallback from requested Georgia to sans-serif. Further credit-bearing calls are paused until scale and font behavior are understood; this is transport evidence, not a renderer-selection pass.

The same day's Shotstack sandbox smoke used only the stage endpoint and no AI assets. It returned the exact requested 540×960, 24 fps H.264 portrait video with the expected sandbox watermark and correct cream/orange centered Montserrat card. The output included an unrequested AAC stream that measured as digital silence, so stream presence cannot count as approved-audio evidence. This strengthens Shotstack's exact-size transport evidence only; the mandatory frozen-fixture quality and operational bake-off remains open.

An operator-requested recreation then used the exact components behind a supplied 8.9-second 1080×1920 reference under one provider-neutral fixture hash. Both providers preserved the continuous video, caption PNG timing/alpha, framing, color, and measured soundtrack without content drift. Shotstack stage returned exact 540×960 in 12.67 seconds with its sandbox watermark; Creatomate returned a clean, unwatermarked result in 7.64 seconds but enforced 270×480 despite a 1080×1920 logical canvas and scale requests 0.5/1.0. Shotstack also produced `done` video-only artifacts when `output.mute: false` was explicitly present; omitting the property restored audio. Local stream/loudness verification therefore remains blocking, and false-valued provider options cannot be assumed harmless.

This reference is useful transport/composition evidence, not the VF-RA-003 selection gate: the run was provider-labeled, not blind, and its caption is a pre-rendered PNG over one continuous clip. Native text/word captions, transitions, keyframes, graphics, gain automation, two-tenant styling, production watermark removal, webhooks/recovery, retention/privacy, and commercial cost remain unproven. See `docs/reviews/REVIEW-reference-video-renderer-bakeoff-2026-07-23.md`.

## M14 Inspiration status

AMENDMENT-012 is ratified as design only. M14 begins after M13 proof. VF-INSP-001..004 define the read-only first slice: strict evidence contracts and redacted fixtures; scheduled append-only collection; DB-only top-level UI; and separate deployed live-provider smoke. VF-INSP-005 adds explicit bookmark/promotion paths only after operator sign-off. No Inspiration code or schema existed at ratification.

**Video generation handoff status (2026-07-10):** VH-1 through VH-6 corrections applied. Both video generation routes (`generate-clip` and `generate-media`) poll, download, and register AI-generated video in `asset_media` with valid file paths. Google/Veo bugs were fixed (aspect ratio, response nesting, download API key, env var). Duration is read from the LLM media plan. Zero-byte render files are cleaned up and output size validation is present. See `docs/reviews/REVIEW-video-generation-handoff-2026-07-09.md` and `docs/inbox/processed/CORRECTION-video-generation-handoff-v1.0.md`.

## Architecture

- **Python + Flask** console (new, not extending v2)
- **SQLite** for provenance, cache, source bank, queues
- **Buffer** (API) for publishing + analytics (replaced Postiz per DIVERGENCE-008 — operator confirmed cost-driven swap)
- **LLM adapter:** one function, backend from config — swappable without code changes
- **trafilatura** for content extraction
- **systemd** on the VPS for deployment
- **GitHub** for code AND docs (one repo, public — deliberate so architect can read without auth)
- **Console auth (R10):** the Flask console has no authentication in M0–M2 code. Deployment posture: bind to localhost/VPN only on the VPS, or add auth before the operator end-to-end test. Endpoints trigger paid LLM calls and overwrite config files — not safe to expose publicly.
- **Claude = architect** | **Hermes = builder** | **Daimon = operator**
- **LLM backend swappable in config** — Ollama local/cloud, external APIs
- **Render execution swappable behind RendererSpec v1** — Creatomate and Shotstack are the first controlled candidates; local FFmpeg/PIL remains the verified fallback. The renderer executes exact approved composition only and cannot select media, rewrite text, regenerate, publish, or replace local evidence/Gate 3.
- **The console renders sessions, not documentation.** Playbook markdown is the machine's script. The operator's surface is always: AI asks → operator gives anything (text, paste, files) → AI clarifies → AI drafts → plain-language readback → gate. The AI is present at every stage; the operator is never handed a form or a procedure to execute manually.

## System Diagram

See `docs/diagrams/README.md` for the system overview (vertical-flow text + Mermaid + SVG). It predates Charter v3.9 and must be refreshed during VF-CW-009/012. The binding flow is: Gather plus parallel Inspiration observations → explicit promotion where chosen → Ideas+Treatment (Gate 1) → Writer Chain → Gate 2 → component requirements/candidates → Component Workbench exact-input approval → immutable manifest freeze → provider-neutral RendererSpec → selected/local renderer execution → local download/hash/probe/evidence → Gate 3 exact-artifact approval → Publish (Gate 4) → Learn.