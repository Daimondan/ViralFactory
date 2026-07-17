# Episode Format — parable — v1.0

## Summary
The show bible for the parable format — first-person AI parable in the style of Bob Invests reels. One recurring character, cinematic consistent grade, a story told beat by beat, every sentence matched by a staged shot of that character living that moment. 60–120s pieces breaking down small ideas. Freshness comes from the story seed, never from format drift.

## Cast

### fitzroy
- **Description:** Fitzroy "Shillings" Pennifold — elderly Black Barbadian man, age 74. The teller: grandfather, story engine. Deep brown weathered skin, close-cropped white-grey hair, neat short white-grey beard, deep smile lines, kind heavy-lidded eyes, thin gold-rimmed reading glasses.
- **Wardrobe:** Cream short-sleeve guayabera shirt with subtle vertical pleats, dark navy trousers, worn gold ring on right hand, brown felt trilby hat worn or resting nearby. No other jewelry, no modern athletic wear.
- **Demeanor:** Past tense, measured, unhurried Bajan cadence. Speaks in specifics — years, amounts, what things cost then — and closes each parable by naming the lesson plainly in one sentence.

### stackwell
- **Description:** Stackwell "Stacks" Pennifold — young Black Barbadian man, age 24. The doer: grandson, face of StackPenni. Deep brown skin, short tapered afro with defined sponge-curl coils, thick straight eyebrows, warm brown eyes, faint chinstrap beard with light goatee, confident closed-mouth half-smile, athletic slim build.
- **Wardrobe:** Plain black crew-neck t-shirt, gold rope chain with small gold broken-trident pendant, gold wristwatch on left wrist. No other jewelry, no hats, no patterns or logos on clothing.
- **Demeanor:** Present tense, quick, concrete, numbers-forward. Receipts energy. Light Bajan inflection, current slang used sparingly. Never preachy, never hypothetical-rich-guy.

## World

### kitchen_dawn
- **Description:** Kitchen table at dawn — small Caribbean kitchen, early morning light through wooden louvered window, enamel cup of tea or mauby on the table, worn wooden surface.

### gallery_porch
- **Description:** Gallery porch — wide verandah of an old Barbadian chattel house, looking out to a garden, afternoon light, rocking chair, wooden walking stick resting against the wall.

### market_town
- **Description:** Market in town — Bridgetown market stalls, vibrant produce and fish, crowd movement, vendor calls, bright midday Caribbean light.

### rum_shop
- **Description:** Rum shop — small wooden rum shop, dim interior, bottles on shelf, dominoes on table, old men playing, warm amber light.

### beach_dusk
- **Description:** Beach at dusk — west coast Barbados beach, golden hour, low sun over the Caribbean Sea, long shadows on sand, gentle waves.

## Grade
- **Grade token ref:** default
- **Description:** Warm golden-hour Caribbean light, low sun, long soft shadows, deep navy-blue shadow tones, rich gold and amber highlights, cream and ochre midtones, painterly cinematic realism, realistic skin texture and natural anatomy, painted cinematic finish, consistent character likeness from reference.

## Beat grammar
- **Roles:** hook → setup → struggle → turn → lesson → cta
- **Hook max:** 3s
- **Struggle range:** 2–4 beats
- **Target duration:** 90s
- **Rules:** hook ≤3s (spoken contradiction or confession, character shown in that exact state); setup; struggle ×2–4; turn; lesson (concept named in plain words); cta (recurring sign-off line, payoff-first).

## Delivery mode
- **Mode:** narration_over_scenes
- **Rules:** The character is shown living each beat; VO narrates. No on-camera dialogue, no lip-sync.

## Audio register map

### somber
- **Music bed:** bed_somber
- **Duck level:** -12 dB
- **LUFS target:** -14

### hopeful
- **Music bed:** bed_hopeful
- **Duck level:** -12 dB
- **LUFS target:** -14

### wry
- **Music bed:** bed_wry
- **Duck level:** -12 dB
- **LUFS target:** -14

## Graphics vocabulary

### number_card
- **Card style ref:** number_card_v1
- **When:** Every number spoken in VO gets a card (e.g. "50 YEARS", "$2,000")

### title_card
- **Card style ref:** title_card_v1
- **When:** Episode title at the open, lesson at the close

### quote_card
- **Card style ref:** quote_card_v1
- **When:** Key line from the VO quoted on screen for emphasis

**Rules:**
- Every number spoken in VO gets a card
- All text/numbers are renderer-drawn graphics — never requested from image generation
- Card styles reference approved card_style registry assets

## Critic rubric
- **hook_contradiction** — Hook contains a spoken contradiction or confession
- **staged_action_depicts_vo** — Each staged_action literally depicts its vo_text content
- **one_idea_per_beat** — Each beat carries one idea, not many
- **lesson_plain** — Lesson is stated plainly in words anyone can understand
- **cta_present** — Sign-off (CTA) is present and payoff-first
- **character_continuity** — The same character reads as the same person throughout

**Notes:** Scores + one-line reasons on the Gate 2 card. Never blocks; the operator's judgment is the gate. Analyst may propose rubric edits only through the module review gate.

## Provenance
- Version: 1.0
- Generated: 2026-07-17T00:00:00.000000+00:00
- Schema: episode_format_v1