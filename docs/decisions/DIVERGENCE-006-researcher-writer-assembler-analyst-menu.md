# DIVERGENCE-006 — Menu restructure: Researcher / Writer / Assembler / Analyst + workflow change

Proposed by operator (Daimon) · Filed by builder · 2026-07-04 · Status: **PROPOSED — awaiting architect review**

## What the operator asked for

Daimon wants the operator-facing menu and workflow to reflect a four-role mental model:

1. **Researcher** (Ideas) — looks at ideas in the source banks and finds ideas based on one source or combining multiple sources. When clicked, stays the same as today: generate more ideas, seed as-is, or seed + AI develop.
2. **Writer** — takes an approved idea and fully writes out the text and visual direction. The writer *continues* the treatment/writing already approved at Gate 1 — it does NOT rewrite from scratch. Produces fully detailed-out script with all visuals needed and described, full text. Operator can work with the writer to refine. Once approved, goes to the assembler.
3. **Assembler** — takes what the writer produces and creates all the media: images, videos, voiceovers, text on screen, etc. Brings it together in its final form. When the operator clicks the assembler button, they see approved scripts done by the writer, hit a button, and the assembler creates the art and assembles it.
4. **Analyst** — once final asset is approved, posts it. Keeps track of performance and learnings. Continues to find sources on the topic (old and new news), finds trending content and content in the same topic area that has gone viral, analyses them, notes them, and enters these into the source banks.

Additional rules:
- When an idea needs human capture of real photos, it does NOT go to a separate "awaiting content" section. The card still goes to the Writer for write-up. Even if photos are needed by a human but not done yet, the Assembler will still create it (with generated/placeholder media until real material arrives).
- Menu headings should reflect the four roles. When an idea is approved at Ideas, it goes to the Writer. When the operator clicks the Writer menu, each approved card has a button where the Writer continues the treatment and writing — already approved, not rewritten from scratch. When the operator goes to the Assembler button, they see the approved scripts done by the Writer and can hit a button to create the art and assemble it.
- The menu buttons at the top should be consistent across all pages.

## What this conflicts with in the current charter/design

### Conflict 1: Awaiting-capture removal vs AMENDMENT-003

AMENDMENT-003 (staged content pipeline) explicitly defines an **awaiting-capture** state: "Cards approved with outstanding capture tasks enter awaiting-capture until the human supplies material through the materials intake." The charter diagram shows: `IDEAS (Gate 1) → Awaiting-Capture → Draft (Gate 2)`.

The operator now says: "if there is an idea that needs human capture of real photos it doesn't go to a separate waiting for content section — the card still goes to the Writer for write up, even photos are needed by human but not done, the Assembler will just create it."

This is a **removal of the awaiting-capture state**. The card flows Ideas → Writer → Assembler regardless of capture tasks. The Assembler produces the asset with whatever media it can generate; real human photos arrive later and update the asset (or a new version).

This is a structural change to the pipeline, not a label change. The architect must decide.

### Conflict 2: "Writer continues, doesn't rewrite from scratch"

The operator says the Writer "continues the treatment and writing already approved not rewrites it from scratch." Currently, the draft generation (`prompts/draft/generate_v2.md`) takes the approved idea card (with its treatment) and produces a full draft. This already continues from the approved treatment — it doesn't re-ideate. So this may be a naming/labeling clarification rather than a structural conflict. But the operator's emphasis suggests they want the Writer role to be visually distinct from the Researcher role in the UI, and to make clear that the treatment approved at Gate 1 is the starting point.

### Conflict 3: Menu restructure

Current menu is inconsistent across templates (24 different nav configurations found). The operator wants a consistent menu reflecting the four roles. The current menu mixes operational stages (Ideas, Create, Published, Metrics) with setup stages (Onboard, Library, Materials) and system stages (Research, Gate Queue). The proposed four-role menu (Researcher/Writer/Assembler/Analyst) is a different organizing principle — it's role-centric, not stage-centric.

### Conflict 4: Analyst owns publishing

Currently publishing happens at Gate 4 (Publish — go/hold + timing only) via the Create page. The operator's vision puts publishing under the Analyst, who also tracks performance and feeds learnings back into source banks. This merges the Publish stage with the Learn stage under one role. The charter currently separates them.

## What this does NOT conflict with

- **Per-piece approval before publish** — still a hard rule. The operator is not asking for auto-publish.
- **AI Profiles** — `config/profiles.yaml` already defines Researcher, Drafter, Analyst. The operator's "Writer" maps to the existing "Drafter" profile. "Assembler" is not a named profile today (asset generation currently runs under the Drafter profile). The operator's "Analyst" maps to the existing Analyst profile but with expanded scope (publishing + performance + source bank feeding).
- **No business values in code** — menu labels would come from config, not hardcoded.

## Questions for the architect

1. **Awaiting-capture removal:** Does the charter drop the awaiting-capture state entirely, or does it persist as a flag on the card (visible to the operator) without blocking the Writer/Assembler flow? The operator's intent is clear: the card does not wait. But real-photo tasks still need to be visible somewhere — otherwise the operator never knows what to capture. Does the capture task become a property of the asset ("real photo needed: [description] — generated placeholder used") rather than a blocking state on the card?

2. **Menu structure:** Is the four-role menu (Researcher / Writer / Assembler / Analyst) a relabeling of existing routes, or does it require new routes/views? The operator said "when I click on ideas page, or wherever, the menu buttons at the top should make sense and be consistent where possible." This suggests: consistent nav bar on every page, organized by the four roles, with setup/admin pages (Onboard, Library, Materials, Gate Queue) grouped separately or as a secondary nav.

3. **Writer = Drafter?** The existing Drafter profile produces both the draft text AND the assets (fan-out). The operator now splits this into Writer (text + visual direction only) and Assembler (media creation). Does the Drafter profile split into two profiles (writer, assembler), or does one profile with two prompt stages suffice? AMENDMENT-005 says profiles are compositions — a split is a config change, not a code change.

4. **Analyst scope:** Does the Analyst profile take ownership of the publish action (currently a manual gate in the Create page), or does publishing remain a separate gate that the operator triggers, with the Analyst tracking the result? The operator said the Analyst "posts it" — but the no-auto-publish hard rule means the operator still approves. Is the Analyst the one who surfaces the "ready to publish — approve?" prompt?

## What the builder can do now (no charter change needed)

- **Activity list cap to 10 + "Show more"** — already built and tested (this session).
- **Consistent nav across all templates** — this is a fix regardless of the four-role restructure. The current 24 different nav configurations are a defect. I can standardize the nav bar across all templates now, with the existing route names, and rename to the four-role labels once the architect decides.
- **Label clarification on Create page** — "Drafts" → "Writer", "Shipped (ready for assets)" → "Assembler" — these are template labels, not structural changes. But I'll wait for the architect's decision on naming before doing this, to avoid churn.

## What the builder cannot do without architect decision

- Remove the awaiting-capture state (conflicts with AMENDMENT-003).
- Split the Drafter profile into Writer + Assembler (AMENDMENT-005 says the registry is the 9th module, gate-only writes — a profile split is a registry change that needs the gate).
- Move publishing under the Analyst (structural change to the pipeline).
- Restructure the menu to the four-role model (needs the architect to decide the organizing principle: role-centric vs stage-centric).

## Builder's recommendation

The operator's mental model (Researcher → Writer → Assembler → Analyst) is clear and strong. It aligns with the existing AI Profiles. I recommend the architect:

1. **Approve the four-role menu** as the primary nav, with setup/admin pages as a secondary nav. This is a UI/labeling change, not a structural one.
2. **Approve awaiting-capture as a non-blocking flag** — the card flows through Writer → Assembler regardless. Capture tasks become a property of the asset ("real photo needed: [description]") shown in the Assembler review, not a blocking state on the card. This resolves the conflict with AMENDMENT-003 by refining it rather than removing it.
3. **Defer the Drafter profile split** to M3 (co-production sprint) where the Writer/Assembler separation actually gets built. The profiles.yaml change is a config change via the gate, not a code change.
4. **Defer Analyst-owned publishing** to M4 (publish milestone). The Analyst tracking performance and feeding source banks is M5/M6 (learning loops). The Analyst triggering the publish prompt is a UX decision for M4.

This divergence does not block any current BUILD_PLAN task. The activity list cap is done. The consistent-nav fix can proceed as a bug fix. The structural changes wait for the architect.