# System Diagrams — ViralFactory

*Destination: `docs/diagrams/README.md` (replaces prior version) · Authoritative overview, current as of **Charter v3.3** (AMENDMENT-004). SVG: `system-overview-v3.3.svg`. The v3.2 SVG is superseded — leave in place for history.*

## Vertical flow (text)

```
THE PERSON ──────────────► ONBOARDING ENGINE (8 playbooks, console-only)
   │ materials · seeds ·            │
   │ reactions · edits ·            ▼
   │ capture                 8 LIVING MODULES ◄──────────────────────────┐
   │                         (versioned · gate-token writes · own DB)    │
   ▼                                │                                    │
GATHER — Sources Engine  ◄── Source Criteria + sources.yaml              │
   ▼                                                                     │
IDEAS — cards, 3 origins  ◄── modules ground ideas + treatments          │
   card = idea + hooks + TREATMENT + origin + evidence                   │
   treatment = scope (one-off | series-of-N | pillar) · format · capture │
   ▼                                                                     │
■ GATE 1 — RIGOROUS: idea + treatment approved TOGETHER                  │
   · approve / kill / park — most die here, by design                    │
   · experimental formats may DEBUT in a treatment — approval            │
     writes the format to the Format Guide (status: experimental) ───────┤
   ▼                                                                     │
AWAITING-CAPTURE (only if treatment requires it)                         │
   person films/records → materials intake → audio transcribed           │
   capture_required = none → passes straight through                     │
   ▼                                                                     │
DRAFT — ONE master script  ◄── all modules loaded into every draft       │
   full text in voice, in the treatment's format + light visual          │
   direction (NO renders) · self-audit vs Tells Checklist                │
   ▼                                                                     │
■ GATE 2 — HUMAN PASS: deep, once, on the master                         │
   chips + text + DIRECT EDITS (authoritative) → ship / kill             │
   ▼                                                                     │
ASSETS — survivors only  ◄── Visual Style + Format Guide + Voice         │
   real images per Visual Style Guide + shot library · captions          │
   in voice · per-platform fan-out per Format Guide                      │
   ▼                                                                     │
■ GATE 3 — QUICK, PER PLATFORM: approve / fix / kill                     │
   ▼                                                                     │
■ GATE 4 — PUBLISH: go / hold · NO AUTO-PUBLISH, EVER (HARD RULE)        │
   ▼                                                                     │
SHIP → POSTIZ (self-hosted) — schedule (series cadence dates) · post     │
   ▼                                                                     │
INWARD LOOP (weekly)                 OUTWARD LOOP (always on)            │
   nightly note: origin · format ·      decomposes format mechanics      │
   scope per piece · Feedback Log       in domain: what works, how,      │
   (direct edits highest) · formats     for what messaging & audience    │
   graduate proven / retire                 │                            │
        └──────────► ASYNC GATE QUEUE ◄─────┘                            │
                     approve = module version bump ──────────────────────┘
                     NEXT DRAFT inherits updated modules
   kill reasons (gates 1–3) → Feedback Log → inward loop
   approved experiments & debut-format proposals enter as idea cards
```

## Mermaid (renders on GitHub)

```mermaid
flowchart TD
    P[THE PERSON<br/>materials · seeds · reactions · edits · capture] --> OB[Onboarding Engine<br/>8 playbooks, console-only]
    OB --> MODS
    subgraph MODS[8 living modules — versioned, gate-token writes, own DB]
        V[Voice] & VP[Viral] & SF[Story] & FG[Format] & AI2[Audience] & FL[Feedback] & VS[Visual] & SRC[Sources]
    end
    MODS -.Source Criteria.-> G[Gather — Sources Engine]
    P -.raw + AI-developed seeds.-> I
    G --> I[IDEAS — cards, 3 origins<br/>card = idea + hooks + TREATMENT + origin + evidence<br/>treatment: scope · format · capture]
    MODS -.ground ideas + treatments.-> I
    I --> GATE1{{GATE 1 · RIGOROUS<br/>idea + treatment together<br/>approve / kill / park}}
    GATE1 -.experimental format debut → Format Guide.-> FG
    GATE1 -->|capture required| AC[AWAITING-CAPTURE<br/>person films/records → intake → transcription]
    GATE1 -->|no capture| D
    AC --> D[DRAFT — ONE master script<br/>in voice, in treatment's format<br/>+ light visual direction, NO renders]
    P <-.capture loop.-> AC
    MODS -.loaded into every draft.-> D
    D --> GATE2{{GATE 2 · HUMAN PASS<br/>deep, once, on the master<br/>direct edits authoritative}}
    GATE2 --> A[ASSETS — survivors only<br/>images per Visual Style + shot library<br/>fan-out per platform per Format Guide]
    MODS -.Visual · Format · Voice shape renders & fan-out.-> A
    A --> GATE3{{GATE 3 · QUICK, PER PLATFORM}}
    GATE3 --> GATE4{{GATE 4 · PUBLISH — go / hold<br/>NO AUTO-PUBLISH, EVER}}
    GATE4 --> POST[Postiz — schedule series cadence · post · metrics]
    POST --> IN[INWARD LOOP — weekly<br/>nightly note: origin · format · scope<br/>formats graduate proven / retire]
    OUT[OUTWARD LOOP — always on<br/>decomposes format mechanics in domain] --> Q
    IN --> Q[ASYNC GATE QUEUE<br/>approve = module version bump]
    Q -.approved proposals bump modules.-> MODS
    OUT -.experiments & debut formats enter as cards.-> I
```

## What changed v3.2 → v3.3

1. Idea cards carry a **treatment** (scope · format · capture · reuse · rationale), approved with the idea at Gate 1.
2. **Awaiting-capture** state between Gate 1 and Draft, with the person's capture loop through materials intake + transcription.
3. **Experimental format debut**: Gate-1 approval of a debut treatment writes the format to the Format Guide (experimental → proven/retired via inward loop).
4. **Modules → Assets arrow added** (operator-spotted omission): Visual Style Guide + shot library, Format Guide fan-out mechanics, and Voice Profile captions all shape asset creation. The arrow documents existing behavior, not new behavior.
5. Nightly note carries `format` and `scope` alongside `origin`; series cadence dates land at the Postiz scheduling step, still behind Gate 4.
