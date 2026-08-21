# ViralFactory Charter — v3.12

*The constitution of the system. Any AI or collaborator reads this before working on it.*
*v3.12 — 2026-08-21 — supersedes v3.11. Incorporates AMENDMENT-020 (`docs/decisions/AMENDMENT-020-story-room-conversational-co-creation.md`). All prior amendments through AMENDMENT-019 remain in force. Repo location: `docs/CHARTER-v3.12.md`.*

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
- **One persistent Story Room per piece.** Conversation continues from unfinished thought through publish; stage changes alter the current goal, context view, tools, and artifact without starting a new siloed chat.
- **Conversation controls; versioned artifacts govern.** The room is the operator control surface. Human-readable Creative Brief, Idea Map, Story Map, exact copy, and Asset Plan versions are the durable truth; machine production contracts compile only after the relevant artifact lock.
- **One-go business intake.** Baseline business/voice/source materials are gathered in onboarding. A Story Room may later ask one high-leverage piece-specific question when lived experience, belief, boundary, or taste would materially change that story; it never re-runs setup questionnaires.

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

Eight versioned markdown documents per business in `modules/{business}/` — the system of record, gate-only writes, schema-checked on load, provenance per entry. Fully standalone — ViralFactory has its own database; no OB1 dependency. Available to every Story Room and production process through declared context views; exact relevant entries and versions are logged:

1. **Voice Profile** (incl. Tells Checklist) · 2. **Viral Patterns Playbook** · 3. **Story Frameworks** · 4. **Format Guide** · 5. **Audience Insights** · 6. **Feedback Log** · 7. **Visual Style Guide** · 8. **Source Bank** (+ its Source Criteria)

## The Story Room core loop

The primary operator-facing creative experience is one persistent **Story Room per piece**. The staged pipeline remains available as a controlled compatibility/baseline mode until the AMENDMENT-020 comparison gate, but it is no longer the target creative boundary.

1. **Gather and notice** — Source Bank, operator materials, and Inspiration collect evidence with their existing semantics and gates. Nothing becomes a story or system rule automatically.
2. **Brief** — the room accepts an unfinished thought, source, observation, file, voice note, or imported legacy piece. It reads relevant approved context, reflects the working understanding, and produces a human-readable Creative Brief: purpose, human stake, audience, desired effect, evidence, gaps, and red lines.
3. **Idea** — the room develops two or three materially different directions when a choice is useful. The selected Idea Map binds core claim, source-grounded editorial lens, tension, audience promise, evidence, human stake, and emotional job.
4. **Shape** — claim → frame → narrative movement → hook direction → ending → format → per-piece style. The Story Map carries the exact Format Guide reference, platform set, production binding, visual treatment, capture policy, and red lines. **Locking the Story Map is Gate 1.** It may compile a compatibility idea/treatment record but does not enqueue the legacy Writer chain in Story Room mode.
5. **Draft** — skeleton, opening options, full draft, local collaborative revision, direct edit, and internal review happen in the room. Exact audience-facing artifacts remain separate: main text, spoken text, on-screen text, platform variants, public caption, hashtags, title, and evidence notes. **Locking exact copy is Gate 2.** Machine Writer/Production Contracts compile afterward and must prove no copy drift.
6. **Build** — the room first produces a human-readable Asset Plan. Existing backstage production then runs: component requirements → immutable candidates → Component Workbench decisions → manifest freeze → CompositionPlan and local previews → composition ratification → RendererSpec → renderer → local artifact verification. New creative judgment pauses after the last lock; authorized deterministic mechanics may continue.
7. **Final review and publish** — **Gate 3** approves/fixes/kills the exact final artifact bound to its current manifest/composition/render lineage. **Gate 4** is go/hold + timing. No auto-publish, ever.
8. **Learn** — metrics and operator reaction link back to the exact room, artifacts, and decisions. Module/process changes remain exact proposals through the asynchronous gate.

The room maintains a visible **Known / Assumed / Missing / Locked** understanding map. AI assumptions are labeled. Human corrections supersede rather than erase. A Locked entry requires a server-verified decision bound to an exact artifact version/hash.

Question policy is materiality-based: read approved context first; research factual gaps where permitted; ask the human about lived experience, belief, boundaries, and taste; show concrete alternatives; ask one meaningful decision at a time; permit “you decide” for low-risk choices; never re-ask answered questions; label safe assumptions and proceed to a preview. Question selection is LLM judgment through versioned prompts/schemas/validators/provenance, never keyword code.

Story Room uses one active-stage pointer plus append-only room events, artifact versions, decisions, dependencies, and understanding entries. It does not create a second giant workflow state machine. Existing `ProductionSession` remains authoritative for per-platform Build execution.

The four content gates remain:

- **Gate 1:** lock the Idea Map + Story Map/treatment meaning;
- **Gate 2:** lock exact copy;
- **Assets component sub-gate:** approve exact ingredients and freeze the immutable manifest;
- **Gate 3:** approve the exact final artifact;
- **Gate 4:** publish go/hold + timing.

The target primary navigation is organized by human jobs: `Desk · Inspiration · Stories · Knowledge · Results`. Desk orders rooms by the next meaningful human decision. Setup, Upload, Treatments, Component Workbench, Composition, and technical utilities remain reachable in context but do not compete as primary creative destinations.

| Operator surface | Primary route target | What happens here |
|---|---|---|
| Desk | `/desk` | Start with a thought; resume stories by next meaningful decision |
| Inspiration | `/inspiration` | Inspect evidence and explicitly carry an exact observation into a room |
| Stories / Story Room | `/stories`, `/stories/<story_id>` | Persistent conversation + live artifact + stage rail + understanding map |
| Knowledge | `/knowledge` | Modules, sources, treatments, proposals, versions, and evidence |
| Results | `/results` | Exact publish records, metrics, and learning linked back to a story |

Legacy `/ideas`, `/create`, `/assemble`, workbench, composition, and publish routes remain available during the experiment. Story Room reuses their services and may deep-link tools from Build, but legacy rows may not silently outrank room artifact locks.

## Provenance requirement

Story Room preserves every typed contribution (human seed, Inspiration observation, Source Bank evidence, attachment, research, AI development) with exact refs. A derived compatibility `origin` (`ai-originated` | `human-seeded` | `human-seeded-ai-developed` | historical `inspiration`), plus `format` and `scope`, still travels to Results for baseline/performance comparison. The derived tag never replaces the contribution ledger.

## The learning system (two loops, one asynchronous gate)

**Inward loop** — generated on a schedule (weekly): results + Feedback Log (direct edits weighted highest) → specific proposed module updates with evidence and exact diffs.

**Outward loop — continuous from v1, not deferred.** Scheduled research of the domain: monitors the sources/channels/queries the Sources Engine maintains and writes append-only external observations with provider, endpoint meaning, platform, region, metric, and time. The Inspiration workbench renders those observations without converting recommendation into trend or trend into rights. Researcher analysis of hook/structure/format/emotion/pacing is stored **as hypotheses, never facts**. Nothing flows automatically from Inspiration: explicit operator actions create Source Bank candidates, experiment proposals, or module proposals, each retaining evidence and its existing gate. (AMENDMENT-012)

**The Gate is a persistent asynchronous queue,** not a scheduled sitting. Proposals accumulate; the person clears them when ready. Rules:
- Every card shows its age; staleness is always visible.
- A newer proposal touching the same module section supersedes the older one (marked, not deleted).
- No deadlines, no pressure mechanics. If the queue grows faster than it clears, the proposals are too weak or too many — **fix the proposal prompt, never pressure the person.**
- Own-account data is small and noisy: no automatic optimization; autonomy is earned as proposals prove out, never assumed.

## Build architecture

- **Hermes (`vf-architect`) = architect**: designs, documents, reviews; speaks through versioned files in the repo.
- **Hermes (`viralfactory`) = builder**: works BUILD_PLAN top-down under its guardrails; never decides design.
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
- **Shots are subdivided mechanically within each beat.** For measured beat duration, `N = ceil(beat_duration_ms / 4000)`, minimum 1; shots share character, location, and grade, vary by framing and motion prompt, divide VO duration without crossing beat boundaries, and use the framing cycle wide → medium → close → insert. (AMENDMENT-015)
- **The render has two explicit tiers.** Tier 1 is the painterly cinematic world layer; Tier 2 is deterministic renderer-drawn graphics. The end card is the single permitted full-frame Tier-2 surface. A Tier-1 world subject may not be rendered as a Tier-2 graphic unless an exact versioned treatment later authorizes that piece-scoped transition. (AMENDMENT-015, amended by AMENDMENT-018)
- **Platform-native audio is a separate, narrow role.** `platform_native_audio` is allowed only for Instagram Reels through an eligible Bundle Social/Facebook-connected account. It is transmitted as an identifier, never acquired, hashed, mixed, or entered into our render; it is mutually exclusive with a local music bed, requires an immutable attachment evidence record, and the exact artifact-plus-identifier pair requires Gate 3 approval. Until a real VO intelligibility probe passes, VO-led pieces must refuse this role. Post-publish retrieval must verify the live attachment and expose an unpublish path on mismatch. (AMENDMENT-016)
- **Format Guide production routing is explicit and gated.** A Format Guide entry may carry `production_binding: {mode, process_ref, governance_module_ref, governance_module_version}`. Standard entries may omit the governance module; non-standard entries require exact approved registry and module/version references. The generic harness resolves the binding from the locked Gate-1 treatment, never from names, filenames, tenant slugs, prompt views, or keywords. Missing, unapproved, stale, or mismatched references fail closed before spend. (AMENDMENT-017)
- **Visual treatments are versioned and piece-scoped.** Visual Style carries `visual_treatments` with exact IDs, versions, references, palette/rules, allowed formats, continuity, disclosure, status, and provenance. One approved Tier-1 treatment governs every world subject in a piece; the exact treatment reference travels through requirements, candidates, manifest, CompositionPlan, RendererSpec, Gate 3, and provenance. Python validates identity, versions, hashes, declared palette membership, dimensions, and consistency only; it does not choose aesthetics. (AMENDMENT-018)
- **Editorial identity is a point of view, not a compulsory wrapper.** Every generated concept persists an `editorial_fit` object with a configured primary lens, source-specific justification, evidence references, excluded default lenses, and identity expression. Lens choice and source-fit judgment belong to a versioned LLM Source-Fit Critic; Python checks structure, configured IDs, resolvable references, hashes, and counts only. One bounded repair pass may run, then invalid cards are omitted. Recent balance is prompt evidence, not a deterministic rejection gate, and module/config changes remain operator-gated proposals. (AMENDMENT-019)
- **One persistent Story Room owns each piece's creative continuity.** It carries one conversation, typed contributions, a visible understanding map, immutable artifact versions, and exact locks from Brief through Publish. Separate stage chats and one global content chat are forbidden. (AMENDMENT-020)
- **Creative automation stops at judgment boundaries.** After the last human lock, authorized deterministic compilation/mechanics may continue; new creative judgment must pause or be shown as a visible assumption. Tool failure is local and cannot erase conversation, locks, or unaffected artifacts. (AMENDMENT-020)
- **Human-readable artifacts precede machine contracts.** Creative Brief, Idea Map, Story Map, exact copy, and Asset Plan are the operator artifacts. Production schemas compile only from current locks and must retain exact lineage and copy. (AMENDMENT-020)
- **Story Room and production state remain separate.** Room stage is an artifact/navigation pointer, not a duplicate production state machine. Existing ProductionSession governs Build execution. Compatibility projections carry story/artifact/version/hash and cannot silently outrank room truth. (AMENDMENT-020)
- **“Take to Story Room” preserves Inspiration as evidence.** It binds the exact item/observation/run and begins shared interpretation; it does not silently create Source Bank truth, a Format Guide rule, soundtrack rights, or a completed idea/treatment. (AMENDMENT-020)

## Effective Amendment Contracts v3.12

This section is the concise operational incorporation of the six amendments added after v3.10. Their full decision records remain the audit source of detail and are linked in the header.

### AMENDMENT-015 — shots per beat and two-tier rendering

One staged action may contain multiple shots. Measured VO remains the master clock; no shot crosses a beat boundary. All shots in a beat preserve the same character block, location block, and grade token. Text and numbers remain renderer-drawn, and canonical reference images remain the source for world subjects. Tier 1 footage is painterly cinematic realism; Tier 2 is flat deterministic graphics composited over it. A flat-vector world subject is not valid under this amendment alone.

### AMENDMENT-016 — platform-native audio attachment

`platform_native_audio` does not create a local audio artifact. The immutable evidence record identifies the provider, endpoint, account context, `audio_id`, available metadata, duration, retrieval time, and sanitized response-payload hash; it contains no rights verdict. The role is Instagram-Reels-only, mutually exclusive with a local music bed, individually selected and approved, never bulk-applied, and never inherited by another destination. Temporary provider previews are not final audio. C4 and C5 are operational acceptance conditions, not claims that may be inferred from tests or metadata.

### AMENDMENT-017 — gated Format Guide production binding

Production behavior is selected by the exact approved Format Guide entry locked in the Gate-1 treatment. `mode: standard` may omit a governance module. Any non-standard mode requires a registered `process_ref` and an exact approved governance module and version. Resolution is through the Process Registry and ModuleStore. The selected binding is copied into the treatment and Writer-contract hash boundary; later guide edits affect only new or explicitly revised treatments.

### AMENDMENT-018 — versioned visual treatments

The Visual Style module may contain multiple coexisting treatment versions. A Format Guide binding or Gate-1 treatment selects exactly one `visual_treatment_ref` for a piece. The cinematic treatment remains valid, and the vector treatment is not a silent migration of existing pieces or the cinematic episode canon. Comparison assets remain proposed until the operator gates the treatment and each required reference candidate. Mixed or stale treatment lineage fails closed.

### AMENDMENT-019 — source-fit editorial range

The Source-Fit Critic is the authority for whether a lens is materially supported and whether a batch has meaningful editorial range. The system may return fewer cards rather than bypassing the critic or manufacturing diversity. Policy, power, ownership, energy, trade, land, work, money, culture, memory, people, humour, and regional life are available editorial subjects; AI, sou-sou, entrepreneurship, friction, and direct entrepreneur address are optional lenses requiring source or human-seed support. Existing cards receive human review, not destructive migration.

### AMENDMENT-020 — persistent Story Room conversational co-creation

One tenant-scoped room carries a piece from unfinished input through publish. Conversation is the control surface; append-only events, contribution refs, Known/Assumed/Missing/Locked entries, artifact versions, and server-bound decisions are the truth. The front-stage progression is Brief → Idea → Shape → Draft → Build. Gate 1 locks story meaning/treatment; Gate 2 locks exact copy; existing component, composition, Gate 3, Gate 4, rights, cost, provenance, and learning boundaries remain.

The legacy pipeline remains available during a controlled three-piece comparison. No destructive migration or default navigation cutover occurs until the operator judges a human-seeded carousel, source-led Reel, and half-formed personal story, including one recoverable tool failure and deep laptop/390px UI proof. DIVERGENCE-017 is superseded: Inspiration enters as exact evidence in a room rather than an immediately generated idea/treatment.

## Phases

**Phase 0 — Foundations.** Fresh repo scaffolding, config system, LLM adapter, validator, provenance, cache, v2 database backup.
**Phase 1 — Onboarding engine.** Generic playbook runner; Voice Profile end-to-end with calibration; then the remaining playbooks. Tenant #1's config re-entered through onboarding (no v2 migration).
**Phase 2 — Co-production and Story Room proof.** Preserve the legacy sprint as baseline, then compare three real Story Room pieces through Brief → Idea → Shape → Draft → Build. Operator reaction—not automation—decides cutover. Feedback Log and room evidence grow.
**Phase 3 — Publish + metrics.** Buffer API; per-piece approval enforced in the flow; nightly metrics.
**Phase 4 — Learning loops.** Inward proposals + async gate queue; outward research + Source Bank + Experiments Queue (outward runs from v1 of this phase).
**Phase 5 — Generalization proof.** Onboard business #2 through the console with zero code changes — executed when a real second business exists; the architecture for it is enforced from Phase 0 regardless.

---

*Test for any decision: does it improve the voice, the lived detail, the person's taste signal, or the system's gated learning — for ANY user, not just tenant #1? If not, it is plumbing: keep it simple or automate it away. If an AI just did something clever ad hoc: stop and write the playbook. If reality disagrees with this charter: file a divergence.*