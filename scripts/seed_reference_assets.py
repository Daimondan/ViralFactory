#!/usr/bin/env python3
"""
Seed the reference asset registry with the Pennifold canon assets.

This is a one-time bootstrap script that populates the registry with:
- Grade token (the verbatim grade string from WORLD-pennifold-canon-v2)
- Character refs (Fitzroy + Stackwell, with face/wardrobe canon blocks)
- Lockup SVGs (the 4 vector sheets)

Run: python3 scripts/seed_reference_assets.py
"""
import json
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from reference_assets import ReferenceAssetStore

DB_PATH = os.environ.get("VF_DB_PATH", "data/viralfactory.db")
BUSINESS_SLUG = "stackpenni"
REF_BASE = "data/media/reference"


def read_file(path):
    with open(path, "r") as f:
        return f.read()


def main():
    store = ReferenceAssetStore(DB_PATH)

    # ── Grade Token ──────────────────────────────────────────────
    grade_string = (
        "Warm golden-hour Caribbean light, low sun, long soft shadows, "
        "deep navy-blue shadow tones, rich gold and amber highlights, "
        "cream and ochre midtones, painterly cinematic realism, "
        "realistic skin texture and natural anatomy, painted cinematic finish, "
        "consistent character likeness from reference."
    )

    world_canon_path = os.path.join(REF_BASE, BUSINESS_SLUG, "grade_token", "world_canon.md")
    existing = store.get_latest_version(BUSINESS_SLUG, "grade_token", "default")
    if existing:
        print(f"  grade_token:default already exists (v{existing['version']}, status={existing['status']}) — skipping")
    else:
        store.propose(
            BUSINESS_SLUG,
            "grade_token",
            "default",
            {
                "grade_string": grade_string,
                "palette": {
                    "deep_navy": "#0E1A2F",
                    "gold": "#D9A93F",
                    "highlight_gold": "#E8B84B",
                    "cream": "#F3EBD8",
                },
                "canon_doc": world_canon_path,
                "tagline": "Smart Money. Stronger Future.",
            },
            notes="Seeded from WORLD-pennifold-canon-v2.md — painterly cinematic realism grade",
        )
        print("  ✓ Proposed grade_token:default")

    # ── Character Ref: Fitzroy ───────────────────────────────────
    fitzroy_canon = read_file(os.path.join(REF_BASE, BUSINESS_SLUG, "character_ref", "fitzroy", "canon.md"))
    fitzroy_ref_img = os.path.join(REF_BASE, BUSINESS_SLUG, "character_ref", "fitzroy", "reference_render.png")

    existing = store.get_latest_version(BUSINESS_SLUG, "character_ref", "fitzroy")
    if existing:
        print(f"  character_ref:fitzroy already exists (v{existing['version']}) — skipping")
    else:
        store.propose(
            BUSINESS_SLUG,
            "character_ref",
            "fitzroy",
            {
                "name": "Fitzroy \"Shillings\" Pennifold",
                "age": 74,
                "role": "the teller — grandfather, story engine",
                "face_canon": "Elderly Black Barbadian man, age 74, deep brown weathered skin, close-cropped white-grey hair, neat short white-grey beard, deep smile lines and lined forehead, kind heavy-lidded eyes, thin gold-rimmed reading glasses often pushed up or held in hand, medium build with a straight proud posture.",
                "wardrobe_canon": "Cream short-sleeve guayabera shirt with subtle vertical pleats, dark navy trousers, worn gold ring on right hand, brown felt trilby hat worn or resting nearby. No other jewelry, no modern athletic wear.",
                "voice_register": "Past tense, measured, unhurried Bajan cadence. Speaks in specifics — years, amounts, what things cost then — and closes each parable by naming the lesson plainly in one sentence.",
                "signature_props": [
                    "Decades-old black notebook with elastic band",
                    "Wooden walking stick with brass broken-trident head",
                    "Enamel cup of tea or mauby",
                    "Reading glasses — his thinking gesture is removing them",
                ],
                "canon_doc": fitzroy_canon,
                "files": ["reference_render.png", "canon.md"] if os.path.isfile(fitzroy_ref_img) else ["canon.md"],
            },
            notes="Seeded from CHARACTER-fitzroy-pennifold-v1_1.md — pending operator gate approval",
        )
        print("  ✓ Proposed character_ref:fitzroy")

    # ── Character Ref: Stackwell ─────────────────────────────────
    stackwell_canon = read_file(os.path.join(REF_BASE, BUSINESS_SLUG, "character_ref", "stackwell", "canon.md"))
    stackwell_ref_img = os.path.join(REF_BASE, BUSINESS_SLUG, "character_ref", "stackwell", "badge_illustration.png")

    existing = store.get_latest_version(BUSINESS_SLUG, "character_ref", "stackwell")
    if existing:
        print(f"  character_ref:stackwell already exists (v{existing['version']}) — skipping")
    else:
        store.propose(
            BUSINESS_SLUG,
            "character_ref",
            "stackwell",
            {
                "name": "Stackwell \"Stacks\" Pennifold",
                "age": 24,
                "role": "the doer — grandson, face of StackPenni",
                "face_canon": "Young Black Barbadian man, age 24, deep brown skin, short tapered afro with defined sponge-curl coils, thick straight eyebrows, warm brown eyes, faint chinstrap beard with light goatee, confident closed-mouth half-smile, athletic slim build.",
                "wardrobe_canon": "Plain black crew-neck t-shirt, gold rope chain with small gold broken-trident pendant, gold wristwatch on left wrist. No other jewelry, no hats, no patterns or logos on clothing.",
                "voice_register": "Present tense, quick, concrete, numbers-forward. Receipts energy. Light Bajan inflection, current slang used sparingly. Never preachy, never hypothetical-rich-guy.",
                "signature_props": [
                    "Black hardcover journal: Plan · Save · Invest · Repeat (renderer draws lettering)",
                    "Takeaway coffee cup, kraft-paper sleeve",
                    "Phone face-down on table (screen never shown — hard rule)",
                    "Small stack of gold coins as visual motif",
                ],
                "canon_doc": stackwell_canon,
                "files": ["badge_illustration.png", "canon.md"] if os.path.isfile(stackwell_ref_img) else ["canon.md"],
            },
            notes="Seeded from CHARACTER-stackwell-pennifold-v1.md — pending operator gate approval. NOTE: badge illustration is stylized vector, not realism — requires realism re-render per world canon v2",
        )
        print("  ✓ Proposed character_ref:stackwell")

    # ── Lockup SVGs ──────────────────────────────────────────────
    svg_files = [
        ("pennifold_character_lockups_v1", "pennifold_character_lockups_v1.svg", "Character lockup sheet — both characters as vector badges with nameplates"),
        ("stackpenni_social_treatment_frames_v1", "stackpenni_social_treatment_frames_v1.svg", "Social treatment frame layouts for posts"),
        ("stackwell_pennifold_lockup_sheet_v1", "stackwell_pennifold_lockup_sheet_v1.svg", "Stackwell character lockup sheet v1"),
        ("stackwell_pennifold_lockup_sheet_v1b", "stackwell_pennifold_lockup_sheet_v1b.svg", "Stackwell character lockup sheet v1b (variant)"),
    ]

    for name, filename, description in svg_files:
        existing = store.get_latest_version(BUSINESS_SLUG, "lockup_svg", name)
        if existing:
            print(f"  lockup_svg:{name} already exists — skipping")
        else:
            store.propose(
                BUSINESS_SLUG,
                "lockup_svg",
                name,
                {
                    "description": description,
                    "files": [filename],
                    "usage": "Vector tier — avatars, watermarks, end cards, merch. Never mixed with realism film layer except where renderer composites vector mark as graphic element.",
                },
                notes=f"Seeded from {filename}",
            )
            print(f"  ✓ Proposed lockup_svg:{name}")

    # ── Summary ──────────────────────────────────────────────────
    all_assets = store.list_assets(BUSINESS_SLUG)
    print(f"\nSeeded {len(all_assets)} reference assets for {BUSINESS_SLUG}:")
    for a in all_assets:
        print(f"  [{a['status']}] {a['kind']}:{a['name']} v{a['version']}")
    print("\nAll assets are in 'proposed' status. Approve them via /setup/reference-assets")

    store.close()


if __name__ == "__main__":
    main()