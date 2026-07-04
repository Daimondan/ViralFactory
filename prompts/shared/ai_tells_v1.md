<!-- version: 1.0 -->
# AI Writing Tells — The Catalog

This is the system's canonical reference for AI writing patterns. Every LLM call that produces operator-facing text (ideas, drafts, fan-out) must self-audit against this catalog. The alignment check also scans for high-confidence tells that survived the self-audit.

Sources: Wikipedia "Signs of AI writing" (WikiProject AI Cleanup), Tropes.fyi AI Writing Pattern Directory, operator-specific findings.

Each tell has a confidence level:
- **HIGH** — almost always AI. Auto-fix in the self-audit loop. The operator should rarely see these.
- **MEDIUM** — frequently AI, but has legitimate uses in some contexts. Flag for review; auto-fix if the context doesn't justify it.
- **LOW** — can be AI, but also common in human writing. Flag only; let the operator decide.

A single occurrence of any tell might be fine. Multiple tells co-occurring is the real signal. The self-audit should weight by density, not just presence.

---

## 1. Word Choice — The Vocabulary That Betrays the Machine

### 1.1 The "delve" family
- **AI tell (X):** "delve", "let's delve into", "delving deeper"
- **Human version (Y):** "look at", "dig into", "examine", or just say the thing
- **Confidence:** HIGH
- **Source:** Wikipedia + Tropes

### 1.2 The "tapestry" and "landscape" family
- **AI tell (X):** "tapestry" (of experiences, of culture), "landscape" (the evolving landscape of...)
- **Human version (Y):** "mix", "blend", "field", "scene", or drop the abstraction and name the things
- **Confidence:** HIGH
- **Source:** Wikipedia + Tropes

### 1.3 The corporate buzzword family
- **AI tell (X):** "robust", "streamline", "leverage" (as verb), "harness", "utilize", "bolster"
- **Human version (Y):** "solid", "simplify", "use", "put to work", "support"
- **Confidence:** HIGH
- **Source:** Wikipedia + Tropes

### 1.4 The significance inflation family
- **AI tell (X):** "crucial", "pivotal", "vital", "key" (as adjective), "testament", "stands as a testament"
- **Human version (Y):** "important", "central", or just show it by spending time on it — don't tell me it's crucial, make me feel it
- **Confidence:** HIGH
- **Source:** Wikipedia

### 1.5 The verb inflation family
- **AI tell (X):** "underscore" / "highlight" (as verb replacing "show"), "enhance", "foster", "cultivate", "bolster"
- **Human version (Y):** "show", "reveal", "improve", "build", "grow", "support"
- **Confidence:** HIGH
- **Source:** Wikipedia + Tropes

### 1.6 The promotional family
- **AI tell (X):** "vibrant", "rich" (cultural heritage), "diverse array", "nestled", "in the heart of", "groundbreaking", "renowned", "exemplifies", "boasts" (meaning "has")
- **Human version (Y):** name the actual colors, sounds, people, or just describe what's there without selling it
- **Confidence:** HIGH
- **Source:** Wikipedia

### 1.7 The quiet adverb family
- **AI tell (X):** "quietly", "deeply", "fundamentally", "remarkably", "arguably"
- **Human version (Y):** drop the adverb — the verb is enough. If the action is quiet, the reader will feel it
- **Confidence:** MEDIUM
- **Source:** Tropes

### 1.8 The meticulous family
- **AI tell (X):** "meticulous", "meticulously", "intricate", "intricacies"
- **Human version (Y):** "careful", "carefully", "detailed", or show the care in the detail itself
- **Confidence:** HIGH
- **Source:** Wikipedia

### 1.9 The copulative avoidance
- **AI tell (X):** "serves as", "stands as", "marks", "represents" instead of "is" / "are" / "was" / "has"
- **Human version (Y):** use the boring copula. "The building is a reminder" not "The building serves as a reminder"
- **Confidence:** HIGH
- **Source:** Wikipedia + Tropes (the "Serves As Dodge")

### 1.10 The marketing verb family
- **AI tell (X):** "features", "offers", "maintains" instead of "has"
- **Human version (Y):** "has". Or just describe the thing
- **Confidence:** MEDIUM
- **Source:** Wikipedia

---

## 2. Sentence Structure — The Shapes AI Loves

### 2.1 Negative parallelism (the #1 identified AI tell)
- **AI tell (X):** "It's not X — it's Y", "Not only X, but also Y", "not because X, but because Y", "The question isn't X. The question is Y."
- **Human version (Y):** State Y directly. If contrast matters, use "but" once, not as a recurring pattern. One per piece is fine; multiple is AI
- **Confidence:** HIGH (single use is MEDIUM; repeated use is HIGH)
- **Source:** Wikipedia + Tropes ("the single most commonly identified AI writing tell")

### 2.2 The dramatic countdown
- **AI tell (X):** "Not X. Not Y. Just Z." (negating two+ things before revealing the point)
- **Human version (Y):** State Z. If you need to dismiss X and Y, do it in one clause
- **Confidence:** MEDIUM
- **Source:** Tropes

### 2.3 Self-posed rhetorical questions
- **AI tell (X):** "The result? Devastating." "The worst part? Nobody saw it coming."
- **Human version (Y):** If the question matters, let it sit. If it doesn't, don't ask it
- **Confidence:** MEDIUM
- **Source:** Tropes

### 2.4 Anaphora abuse
- **AI tell (X):** Repeating the same sentence opening multiple times ("They assume... They assume... They assume...")
- **Human version (Y):** Vary naturally. Humans don't anaphora in prose unless making a deliberate speech
- **Confidence:** MEDIUM
- **Source:** Tropes

### 2.5 Rule of three everywhere
- **AI tell (X):** "X, Y, and Z" in every paragraph. Tricolon abuse extended to 4-5
- **Human version (Y):** Two items. One item. Four items. Mix it. Three is fine once; three in every paragraph is AI
- **Confidence:** MEDIUM (single use is fine for social copy; repeated use is AI)
- **Source:** Wikipedia + Tropes

### 2.6 Filler transitions
- **AI tell (X):** "It's worth noting that...", "Importantly,...", "Notably,...", "It bears mentioning"
- **Human version (Y):** Just say the thing. If it's important, the reader will know
- **Confidence:** HIGH
- **Source:** Tropes

### 2.7 Superficial analysis (-ing phrases)
- **AI tell (X):** Present participle at end of sentence: "...contributing to the region's cultural heritage", "...underscoring its role as a hub", "...reflecting broader trends"
- **Human version (Y):** End the sentence. Start a new one if you have something to say
- **Confidence:** HIGH
- **Source:** Wikipedia + Tropes

### 2.8 False ranges
- **AI tell (X):** "From X to Y" where there's no real spectrum ("from innovation to cultural transformation")
- **Human version (Y):** Name both things. Or pick one. Don't fake a spectrum
- **Confidence:** MEDIUM
- **Source:** Tropes

---

## 3. Paragraph Structure — The Rhythm of the Machine

### 3.1 Uniform short fragments
- **AI tell (X):** Every paragraph is one sentence. Short punchy fragments as standalone paragraphs throughout
- **Human version (Y):** Mix paragraph lengths. Some 3 sentences, some 1, some 5. Natural variation matches how humans think
- **Confidence:** MEDIUM
- **Source:** Tropes

### 3.2 Listicle in a trench coat
- **AI tell (X):** "The first... The second... The third..." disguised as continuous prose
- **Human version (Y):** Use an actual list, or write actual prose with real transitions
- **Confidence:** MEDIUM
- **Source:** Tropes

---

## 4. Tone — The Attitude of the Machine

### 4.1 False suspense
- **AI tell (X):** "Here's the kicker", "Here's the thing", "Here's where it gets interesting", "Here's what most people miss"
- **Human version (Y):** Just make the point. False suspense is worse than no suspense
- **Confidence:** HIGH
- **Source:** Tropes

### 4.2 Patronizing analogies
- **AI tell (X):** "Think of it as...", "It's like a..."
- **Human version (Y):** Explain the thing directly. If a metaphor helps, use it once, not as a frame
- **Confidence:** MEDIUM
- **Source:** Tropes

### 4.3 Imagine-a-world
- **AI tell (X):** "Imagine a world where..."
- **Human version (Y):** State the argument. The reader can imagine
- **Confidence:** HIGH
- **Source:** Tropes

### 4.4 False vulnerability
- **AI tell (X):** "And yes, I'm openly in love with...", "This is not a rant; it's a diagnosis"
- **Human version (Y):** Real vulnerability is specific and uncomfortable. If you're not being specific, you're performing
- **Confidence:** MEDIUM
- **Source:** Tropes

### 4.5 Asserted simplicity
- **AI tell (X):** "The reality is simpler", "History is clear on this", "The truth is simple"
- **Human version (Y):** Prove it. Don't tell me it's simple — show me the simplicity
- **Confidence:** MEDIUM
- **Source:** Tropes

### 4.6 Grandiose stakes
- **AI tell (X):** "This will fundamentally reshape everything", "will define the next era"
- **Human version (Y):** State the actual stakes. A post about API pricing is not a meditation on civilization
- **Confidence:** HIGH
- **Source:** Tropes

### 4.7 Pedagogical hand-holding
- **AI tell (X):** "Let's break this down", "Let's unpack this", "Let's dive in", "Let's explore"
- **Human version (Y):** Just start. The reader doesn't need a roadmap sentence
- **Confidence:** HIGH
- **Source:** Tropes

### 4.8 Vague attributions
- **AI tell (X):** "Experts argue...", "Industry reports suggest...", "Observers have cited..."
- **Human version (Y):** Name the expert. Name the report. If you can't, you don't have a source
- **Confidence:** HIGH
- **Source:** Wikipedia + Tropes

### 4.9 Invented concept labels
- **AI tell (X):** "the supervision paradox", "the acceleration trap", "workload creep" — compound labels that sound analytical without being grounded
- **Human version (Y):** Describe the phenomenon in plain words. Don't name it to skip the argument
- **Confidence:** MEDIUM
- **Source:** Tropes

### 4.10 The "despite challenges" formula
- **AI tell (X):** "Despite its [positive], faces challenges... Despite these challenges, [optimistic]"
- **Human version (Y):** State the challenges directly. End honestly. Don't wrap in a bow
- **Confidence:** HIGH
- **Source:** Wikipedia + Tropes

### 4.11 Promotional tone
- **AI tell (X):** "boasts a", "vibrant", "rich cultural heritage", "natural beauty" — travel-guide prose
- **Human version (Y):** Describe what's actually there. Don't sell it
- **Confidence:** HIGH
- **Source:** Wikipedia

---

## 5. Formatting — The Visual Tells

### 5.1 Em dash addiction
- **AI tell (X):** Em dashes with spaces around them, used 20+ times per piece. AI uses them where humans use commas, parentheses, or periods
- **Human version (Y):** 2-3 per piece max. Use commas, parentheses, or periods instead
- **Confidence:** HIGH (at 5+ per piece)
- **Source:** Wikipedia + Tropes

### 5.2 Bold-first bullets
- **AI tell (X):** Every bullet point starts with bold text: "**Security**: ...", "**Performance**: ..."
- **Human version (Y):** Mix it. Some bullets have no bold. Some are just sentences
- **Confidence:** MEDIUM
- **Source:** Tropes

### 5.3 Emoji as formatting
- **AI tell (X):** Emoji before headings or bullet points (🧠 🚀 🌏)
- **Human version (Y):** No emoji as formatting. Emoji in content only if the platform calls for it and the person uses them
- **Confidence:** HIGH
- **Source:** Wikipedia

### 5.4 Curly quotation marks
- **AI tell (X):** Curly quotes (" " ' ') when the person writes straight quotes
- **Human version (Y):** Match the person's actual quote style. Most people type straight quotes
- **Confidence:** MEDIUM
- **Source:** Wikipedia

### 5.5 Unicode decoration
- **AI tell (X):** Unicode arrows (→) when the person would type -> or "to"
- **Human version (Y):** Match the person's typing habits
- **Confidence:** LOW
- **Source:** Tropes

### 5.6 Title case in headings
- **AI tell (X):** Every main word capitalized in section headings
- **Human version (Y):** Sentence case, or match the platform convention
- **Confidence:** LOW
- **Source:** Wikipedia

---

## 6. Composition — The Structure of the Machine

### 6.1 Fractal summaries
- **AI tell (X):** "In this section we'll explore... [content] ...as we've seen in this section" — meta-narration at every level
- **Human version (Y):** No meta-narration. Don't tell the reader what you're going to say, say it
- **Confidence:** HIGH
- **Source:** Tropes

### 6.2 Dead metaphor
- **AI tell (X):** Same metaphor repeated 5-10 times across the piece
- **Human version (Y):** Use a metaphor once. Move on
- **Confidence:** MEDIUM
- **Source:** Tropes

### 6.3 Historical analogy stacking
- **AI tell (X):** "Apple didn't build Uber. Facebook didn't build Spotify. AWS didn't build Airbnb."
- **Human version (Y):** One analogy. If you need more, you're padding
- **Confidence:** MEDIUM
- **Source:** Tropes

### 6.4 One-point dilution
- **AI tell (X):** Same argument restated 10 ways across 4000 words
- **Human version (Y):** Make the point. Move on. If you need 4000 words, have 4000 words of substance
- **Confidence:** MEDIUM
- **Source:** Tropes

### 6.5 Signposted conclusion
- **AI tell (X):** "In conclusion", "To sum up", "In summary"
- **Human version (Y):** Just end. The reader can feel the ending
- **Confidence:** HIGH
- **Source:** Wikipedia + Tropes

---

## 7. What Human Writing Actually Does (Positive Patterns to Preserve)

These are patterns the Voice Profile analysis should extract. If the person does these naturally, the drafter should NOT "improve" them away.

### 7.1 Simple copulatives
- **Human pattern:** "is", "has", "there is a", "it has a"
- **AI avoids it:** Replaces with "serves as", "stands as", "features"
- **Source:** Wikipedia "Signs of human writing"

### 7.2 Plain verbs
- **Human pattern:** wrote (not authored), moved (not relocated), used (not utilized), tried (not attempted), died (not passed away)
- **AI avoids it:** Upgrades to the fancy synonym every time
- **Source:** Wikipedia

### 7.3 Superlatives when warranted
- **Human pattern:** "one of the best", "was the first", "the only"
- **AI avoids it:** Hedges — avoids definitive statements
- **Source:** Wikipedia

### 7.4 Natural hedging
- **Human pattern:** "very", "perhaps", "tends to" — used naturally, mixed with confidence
- **AI avoids it:** Either over-hedges or over-asserts — doesn't mix
- **Source:** Wikipedia

### 7.5 Wordy constructions left alone
- **Human pattern:** "as a result of", "in order to", "the fact that" — left as-is when natural
- **AI avoids it:** "Improves" these into tighter but less natural phrasing
- **Source:** Wikipedia

---

## How to use this catalog

### In the draft prompt (self-audit)
After writing, scan every line against categories 1-6. For each tell:
- HIGH confidence: flag it AND fix it before the draft reaches the alignment check
- MEDIUM confidence: flag it. Fix if the context doesn't justify it. Leave if it does
- LOW confidence: flag it for the operator. Don't auto-fix

Count density: if 3+ tells co-occur in the same paragraph, that's a high-confidence AI signal even if individual tells are MEDIUM.

### In the alignment check
After the self-audit fix, scan again for HIGH confidence tells that survived. Report them as issues with type "ai_tell_survived" and severity "medium". The alignment check is the second pass — it catches what the self-audit missed.

### In the idea generation prompt
Ideas should not be born in AI tone. Check idea descriptions against categories 4 (tone) and 2 (sentence structure). An idea described with negative parallelism or grandiose stakes starts AI-shaped and stays AI-shaped.

### In fan-out
If fan-out LLM calls remain (they should not per AMENDMENT-007, but if any text adaptation happens), check against categories 1 (word choice), 5 (formatting), and 2.1 (negative parallelism — the #1 tell that drifts in during adaptation).