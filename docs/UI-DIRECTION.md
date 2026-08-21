# UI Direction — Story Room Console

*Repo location: `docs/UI-DIRECTION.md`. Direction for Hermes when building operator screens. v2.0 — 2026-08-21 — AMENDMENT-020 makes one persistent Story Room per piece the target creative center while preserving conversational onboarding and the existing production tool bench.*

## Principles

1. **Laptop-first (1280px+), responsive to mobile.** Mobile-friendly is a hard requirement for future customers, not an afterthought — but it does not constrain the primary design. Multi-column layouts allowed on laptop.
2. **The person's verbs are: speak, type, tap, react, edit, approve.** The system defaults to AI production but supports and encourages direct editing when the person chooses to write or rewrite draft text.
3. **Reactions are first-class input.** Reacting to a draft line = tap the line → quick chips (**not me · too polished · flat · too long · keep · love it**) + typed text for anything nuanced. Every reaction writes to the Feedback Log with the draft version it applied to.
4. **Gates are a persistent async queue.** One proposal per card: the proposed change, the evidence, the exact diff. Tap/click: approve · reject (with quick reason chips) · park. No deadline or pressure mechanics — the person clears when ready. Every card shows age ("submitted N days ago"); newer proposals on the same module section supersede older ones (marked, not deleted).
5. **Voice in, everywhere — available at every input, assumed at none.** Typed text and chips are equal citizens. A record button sits next to every input point, but the person is never required to use it.
6. **Status always visible.** The person can always see: what the system is doing now, what's waiting on them, what shipped, what's scheduled. No mystery states.
7. **Evidence beside every AI claim.** A proposed pattern shows the reactions/results that support it; a proposed source shows the sample item and matched criteria; a flagged draft line shows which Tells Checklist rule flagged it.
8. **Boring web tech.** Server-rendered Flask + minimal JS. No SPA framework. Fast on island bandwidth.
9. **The console renders sessions, not documentation.** Playbook markdown is the machine's script. The operator's surface is always: AI asks → operator gives anything (text, paste, files) → AI clarifies → AI drafts → plain-language readback → gate. The AI is present at every stage; the operator is never handed a form or a procedure to execute manually. (UI-REVIEW-001 F3)
10. **Every string the operator reads is written for a business owner.** File paths, module targets, and playbook internals are never visible in the default operator view — they live in a collapsible "technical details" element and the provenance log. Where a playbook step needs an operator-facing label, use `display_label`. (UI-REVIEW-001 F4)
11. **One persistent Story Room per piece.** Stage changes swap goal, context, tools, and artifact inside the same room; they do not create separate chats or throw the operator into unrelated queues.
12. **Conversation and artifact stay together.** Chat is the control surface; the current human-readable artifact, version, lock/stale state, and understanding map are always one action away.
13. **One meaningful action at a time.** The primary button reflects the next decision; secondary tools remain available but do not compete. Green means externally or cryptographically verified truth, not “a job ran.”

## Primary information architecture

The target primary navigation under Story Room experiment mode is:

`Desk · Inspiration · Stories · Knowledge · Results`

Setup, Upload, Treatments, Component Workbench, Composition, and technical logs remain reachable in context or utility navigation. They are not primary creative destinations. Legacy Pipeline remains a clearly labeled utility during the controlled comparison.

## The primary surfaces

### 1. Onboard (runs once per business; M1–M2)
**Conversational sessions, not procedure documents (UI-REVIEW-001 F3).** Each playbook runs as an AI-driven chat session through one reusable, config-driven session component:

1. **Chat transcript pane.** The AI opens by asking the first question from the playbook's Q&A. One question at a time — grill-session format. The AI ingests whatever it's given, asks clarifying follow-ups when an answer is thin or ambiguous, and moves on when it has enough.
2. **Input box.** Multiline text entry. The operator can answer the question asked, or paste anything — a brand doc, a rant, a half-formed thought.
3. **Add files button.** Uploads (docs, exports, images) attach into the session and are ingested as intake material.
4. **Voice input** — deferred per T2.6–T2.8. Mic button hidden or stubbed, not broken-looking.
5. **Readback → gate.** When the AI has enough, it presents the draft in the chat, in plain language: "Here's what I understood — correct anything." The operator can reply conversationally OR edit the draft text directly (direct editing is authoritative). Approve / Reject / Park appear attached to the readback, not floating at the bottom of a procedure list.
6. **Progress rail.** The playbook's steps survive only as a slim progress indicator ("Step 2 of 4 — drafting"). Steps are status, not content.

Playbook cards on the Onboard landing page are numbered and sorted by `run_order` from config. A playbook whose prerequisites haven't been approved yet renders as locked/pending. Exit state: all 8 modules at v1, `business.yaml` + `sources.yaml` written.

### 2. Desk

- Primary invitation: **“Pick up a story, or start with a thought.”**
- “Start with a thought” accepts text, voice when available, files, links, or a source.
- Active stories are ordered by the next meaningful human decision, not raw update time or an AI importance score.
- Each row uses a descriptive story title, current front-stage artifact, visible version, friendly age, and one sentence explaining what needs the operator.
- Parked, killed, failed, published, and empty states have clear next actions and no pressure mechanics.
- Recent activity is a receipt trail, not a productivity score.

### 3. Inspiration

- Evidence workbench semantics from AMENDMENT-012 remain.
- Cards preserve provider, endpoint meaning, region, metric/rank, age, availability, and exact observation evidence.
- Primary creative action: **Take to Story Room**.
- The action carries exact evidence into a room and asks what the operator sees or offers concrete possible uses. It does not generate a completed idea/treatment first.
- Source Bank, Format Guide, module, experiment, and soundtrack actions remain distinct gated promotions.

### 4. Stories / Story Room

#### Laptop (1280px+)

Use a working three-part layout:

1. **Stage rail + understanding summary:** Brief · Idea · Shape · Draft · Build; Known / Assumed / Missing / Locked entries visible.
2. **Conversation pane:** continuous transcript, concrete choices, composer, attachments, research/tool actions, local failures and retries.
3. **Artifact pane:** current human-readable artifact, descriptive title, visible version, working/ready/locked/stale state, direct edit where allowed, diff/history, and one primary current action.

The operator never has to leave the story to understand what changed. Component Workbench, Composition, final preview, and Publish may open as focused Build sub-surfaces, but retain story title/context and a reliable return path.

#### Mobile (true 390px)

- Compact horizontal stage rail.
- Explicit **Conversation / Artifact / Understanding** views; none disappear.
- No horizontal page overflow.
- Composer remains reachable above the mobile keyboard.
- Artifact content and platform previews expand fullscreen.
- Version/lock/stale state and the primary action remain visible.
- Browser emulation must prove actual inner width, not only requested device metrics.

#### Artifact behavior

- Brief, Idea Map, Story Map, exact copy, and Asset Plan are plain-language documents—not raw JSON.
- A lock is attached to the exact artifact version and shows friendly time + visible version badge.
- Revising upstream marks dependent work stale with an explanation and preserves unaffected work.
- Direct edit is authoritative and creates a new version immediately.
- “You decide” is valid for low-risk choices and appears as a visible assumption until the next relevant lock.

### 5. Knowledge

Browse and manage the eight modules, Source Bank, approved visual treatments, Format Guide/process bindings, Feedback Log, proposals, and provenance. Show versions and evidence. “Remember this” creates a proposal; it never silently edits a module.

### 6. Results

Published work is linked to its Story Room, exact artifacts, final asset, caption/audio choices, publish record, metrics, and learning proposals. Scheduled/Published labels require verified external truth. A Buffer/API failure is not green.

### 7. Async proposal gate

The existing persistent queue remains under Knowledge/Review. Keep age, superseding, exact diff, evidence, and bulk operations for queues over 50. No deadlines or pressure.

## Build sequencing for Hermes

1. Truthful legacy baseline and feature flag.
2. Story/event/artifact/lock/understanding contracts.
3. Prompt-backed room turn and context views.
4. Desk + Story Room shell.
5. Brief → Idea → Shape.
6. Collaborative Draft + exact copy lock.
7. Asset Plan + reuse existing production tool bench.
8. Inspiration/Results integration.
9. Three-piece laptop/390px comparison.
10. Operator cutover decision.

Do not build navigation buttons before the durable room and artifact contracts. Do not treat the approved prototype as pixel-perfect acceptance; apply the 10-dimension human UI methodology to every real state.
