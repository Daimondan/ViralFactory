# World Canon — The Pennifold World (v2)

**Status:** DRAFT — pending operator gate. Supersedes WORLD-pennifold-canon-v1.
**Change in v2:** rendering style amended from stylized illustration to painterly realism, per operator ruling of 2026-07-14 on the Fitzroy reference render. Adds the single-style rule, the artifact-class distinction for text, and tagline discipline.
**Registry role:** Reference asset registry entries `world/grade` and `world/location-*`. The Grade String is inserted verbatim into every image-generation prompt for every character and every location.

---

## The family

The Pennifolds are the brand. Fitzroy "Shillings" Pennifold (74, grandfather, the teller) and Stackwell "Stacks" Pennifold (24, grandson, the doer). Shillings to stacks: the island's currency history and the brand's thesis — wealth and knowledge passed down — in two nicknames. Every episode is an entry in one continuous family story.

## Rendering style ruling (new in v2)

- The world renders in **painterly cinematic realism**: realistic skin texture, natural anatomy, cinematic lighting, painted rather than photographic finish. Reference standard: the gated Fitzroy porch render (2026-07-14).
- **One world, one style.** Both characters and all six locations render in this single style. The stylized 2026-05-12 Stackwell badge illustration is retired from the film layer; Stackwell requires a realism re-render matched to the Fitzroy standard before appearing in episodes.
- The flat vector character marks and type lockups remain the **graphic tier** — avatars, watermarks, end cards, journal cover, merch. Vector for identity, realism for film. The two tiers never mix inside a frame except where the renderer composites the vector trident or wordmark as a graphic element.
- Realism raises the consistency bar: a slightly-off realistic face reads as a different person. Therefore no character appears in any episode until a gated face reference set (3–5 angles and expressions in the locked style) exists for that character, and every shot prompt conditions on that set.

## Grade string (verbatim prompt block — amended)

> Warm golden-hour Caribbean light, low sun, long soft shadows, deep navy-blue shadow tones, rich gold and amber highlights, cream and ochre midtones, painterly cinematic realism, realistic skin texture and natural anatomy, painted cinematic finish, consistent character likeness from reference.

This string travels with every image prompt, no exceptions. If the grade ever changes, it changes here, through the gate, and applies forward only.

## Palette

- Deep navy `#0E1A2F` — ground, shadow, night, the brand base
- Gold `#D9A93F` / highlight gold `#E8B84B` — light, money, the trident
- Cream `#F3EBD8` — paper, Fitzroy's shirt, daylight walls
- Accent sky/amber tones permitted in backgrounds; no saturated reds or purples

## Locked locations (6)

Each becomes one gated reference still in the locked realism style. Shot prompts reference the still, never re-describe the place freehand.

1. **The gallery porch** — Fitzroy's chattel-style house, painted wood, two chairs, view toward the sea. The two-hander stage and the emotional home of the brand. (First reference candidate exists in the gated Fitzroy render.)
2. **The kitchen table** — inside the same house. Oilcloth, enamel cups, morning light. Where the notebook comes out.
3. **The sea-view desk** — Stackwell's workspace, simple desk, window on the water, journal and coffee. Modern but spare.
4. **Bridgetown streets** — market activity, the Parliament clock tower permitted in background. The world of transactions.
5. **The rum shop exterior** — village social hub, painted signage kept illegible or renderer-drawn. Fitzroy holds court with tea.
6. **The beach at dusk** — closing-shot location. Navy water, gold sky.

## Text rules by artifact class (clarified in v2)

- **Episode stills and video frames:** AI never renders legible text, numbers, screens, phones face-up, logos, or currency close-ups. All titles, figures, captions, plates, and end cards are drawn by the deterministic renderer in the fixed styles.
- **One-off gated poster artworks** (character badges, cover art): painted in-image text is permitted because the artwork itself passes the gate as a whole. These artifacts never enter the episode pipeline as shot references for text.

## Tagline discipline (new in v2)

- The brand carries exactly one printed tagline on all lockups and end cards: **Smart Money. Stronger Future.**
- Character mottos are spoken, not printed. Fitzroy's episode sign-off: *"Stories build wealth. Values build legacy."* Stackwell's sign-off line: to be ruled.
- No additional taglines may appear on lockups, badges, or end cards.

## Shared hard rules (both characters, all shots)

- One grade, one world: no shot leaves the palette or the style. A shot that reads as a different film is rejected at the stills gate.
- Stills gate before animation: character-consistent stills are approved first; only approved stills go to image-to-video spend.
- Character sheets and this world sheet are gated documents. Prompts consume them verbatim; nothing paraphrases canon.

## Trident usage across the world

The broken trident is the single brand glyph everywhere it appears in-world: Stackwell's pendant, Fitzroy's stick head and ring, the journal cover motif. Where crispness matters (covers, cards, graphics), the renderer composites the approved vector mark rather than trusting generation.
