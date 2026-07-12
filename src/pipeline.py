"""
ViralFactory — Co-production Pipeline (M3)

The staged content pipeline: Ideas → Draft → Assets → Publish.
This module provides the data layer (SQLite tables, store/queue logic)
for the pipeline. All judgment work (idea generation, drafting, asset
production) is done by LLM calls through the adapter — never hardcoded.

Tables:
  idea_cards — the first artifact; carries treatment + origin + state
  drafts     — full text in voice + visual direction block + self-audit flags
  assets     — per-platform variants produced from approved drafts
  feedback_log — reactions + direct edits (voice signal, highest weight for edits)

States for idea_cards:
  new → approved → writing → draft_ready → (shipped → assembling → asset_ready)
  new → killed   (kill reason → feedback_log)
  new → parked   (retrievable, can be re-activated)
  NOTE: awaiting_capture is DEPRECATED as a blocking state per AMENDMENT-006.
        Capture tasks are a non-blocking flag on the card. Cards with capture
        tasks flow through approved → Writer like any other approved card.

States for drafts:
  drafting → draft_ready → human_pass → shipped  (→ assets)
  drafting → draft_ready → human_pass → killed
  drafting → revised     (after revise, back to draft_ready)

States for assets:
  pending → approved → published
  pending → fix      (→ back to pending after re-generation)
  pending → killed
"""

import os
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional


# ─── Schema ──────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS idea_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    idea TEXT NOT NULL,
    hook_options TEXT NOT NULL,          -- JSON array of hook/title strings
    treatment TEXT NOT NULL,             -- JSON: {scope, format, capture_required, reuse, rationale, experimental}
    origin TEXT NOT NULL,                -- ai_originated | human_seeded | human_seeded_ai_developed
    evidence_links TEXT,                 -- JSON array of {url, note} (derived display field)
    source_refs TEXT,                     -- JSON array of source IDs from the sources table
    seed_text TEXT,                      -- original seed (for human-seeded origins)
    parent_id INTEGER,                   -- for series children: links to parent card
    card_state TEXT NOT NULL DEFAULT 'new',  -- new | approved | awaiting_capture (DEPRECATED per AMENDMENT-006) | capture_fulfilled | writing | reviewing | draft_ready | drafted | killed | parked | producing | assembling | asset_ready | writer_failed | assembly_failed | production_failed
    kill_reason TEXT,
    capture_uploads TEXT,                -- JSON array of uploaded material IDs
    production_error TEXT,                -- JSON: {step, error} when card_state=production_failed
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (parent_id) REFERENCES idea_cards(id)
);

-- T8.3: Source Bank as addressable store
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    source_type TEXT NOT NULL,           -- 'rss_item' | 'scraped_article' | 'operator_material' | 'archival' | 'manual'
    title TEXT NOT NULL,
    url TEXT,                             -- nullable (operator materials may have none)
    summary TEXT,                         -- short extract for selection-stage injection
    content TEXT,                         -- full extracted text for production-stage injection
    origin TEXT NOT NULL DEFAULT 'system', -- 'system' (snapshot/scraper) | 'operator' | 'analyst'
    first_seen TEXT NOT NULL,
    content_hash TEXT,                    -- dedupe
    status TEXT NOT NULL DEFAULT 'active' -- 'active' | 'archived'
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    idea_card_id INTEGER NOT NULL,
    origin TEXT NOT NULL,                -- carried from idea card
    format TEXT,                         -- carried from treatment
    scope TEXT,                          -- carried from treatment
    draft_text TEXT NOT NULL DEFAULT '', -- backward compat: summary text for legacy views
    platform_content TEXT,               -- JSON array of {platform, variant_type, content, posts, image_prompts}
    visual_direction TEXT,               -- JSON: {image_prompts, reference_notes, shot_format_choices}
    self_audit_flags TEXT,               -- JSON array of {line, rule, confidence, suggestion, fix_applied, status}
    review_history TEXT,                 -- JSON array of AI review loop rounds (T9.5)
    review_converged TEXT,               -- 'true' | 'false' | null (T9.5)
    draft_version INTEGER NOT NULL DEFAULT 1,
    draft_state TEXT NOT NULL DEFAULT 'drafting',  -- drafting | draft_ready | human_pass | shipped | killed | revised | reviewing
    human_edits TEXT,                    -- JSON: direct edits (authoritative text)
    feedback_entries TEXT,               -- JSON array of feedback log entry IDs
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (idea_card_id) REFERENCES idea_cards(id)
);

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    draft_id INTEGER NOT NULL,
    platform TEXT NOT NULL,              -- X | Instagram | etc.
    variant_type TEXT NOT NULL,          -- thread | carousel | reel | single_post | etc.
    content TEXT NOT NULL,              -- the platform-specific text/caption (summary for thread/carousel)
    posts TEXT,                         -- JSON array of individual posts/slides (for thread/carousel)
    image_prompts TEXT,                 -- JSON array of image generation prompts used
    generated_images TEXT,              -- JSON array of generated image paths/URLs
    vo_segments TEXT,                     -- JSON array of per-frame VO segments: [{frame, path, duration, text}]
    asset_state TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | fix | killed | published
    publish_scheduled_at TEXT,          -- ISO timestamp for scheduled publish
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (draft_id) REFERENCES drafts(id)
);

CREATE TABLE IF NOT EXISTS feedback_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    draft_id INTEGER,                   -- optional: which draft this feedback is about
    idea_card_id INTEGER,               -- optional: which idea card (kill reasons)
    feedback_type TEXT NOT NULL,        -- chip | text | direct_edit | kill_reason
    feedback_text TEXT NOT NULL,        -- the actual feedback content
    line_reference TEXT,                -- optional: which line/section
    weight INTEGER NOT NULL DEFAULT 1,  -- direct_edit=3, chip=1, text=2, kill_reason=1
    created_at TEXT NOT NULL,
    FOREIGN KEY (draft_id) REFERENCES drafts(id),
    FOREIGN KEY (idea_card_id) REFERENCES idea_cards(id)
);

CREATE INDEX IF NOT EXISTS idx_idea_cards_business ON idea_cards(business_slug);
CREATE INDEX IF NOT EXISTS idx_idea_cards_state ON idea_cards(card_state);
CREATE INDEX IF NOT EXISTS idx_idea_cards_parent ON idea_cards(parent_id);
CREATE INDEX IF NOT EXISTS idx_drafts_business ON drafts(business_slug);
CREATE INDEX IF NOT EXISTS idx_drafts_idea ON drafts(idea_card_id);
CREATE INDEX IF NOT EXISTS idx_drafts_state ON drafts(draft_state);
CREATE INDEX IF NOT EXISTS idx_assets_draft ON assets(draft_id);
CREATE INDEX IF NOT EXISTS idx_assets_state ON assets(asset_state);
CREATE INDEX IF NOT EXISTS idx_feedback_business ON feedback_log(business_slug);
CREATE INDEX IF NOT EXISTS idx_feedback_draft ON feedback_log(draft_id);
CREATE INDEX IF NOT EXISTS idx_sources_business ON sources(business_slug);
CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);
CREATE INDEX IF NOT EXISTS idx_sources_hash ON sources(content_hash);

-- Voice registry (DECISION-voice-cloning-vo-v1.0)
-- Tracks cloned and stock voices for VO generation.
-- Nothing business-specific in the schema — each tenant has their own voices.
CREATE TABLE IF NOT EXISTS voices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    name TEXT NOT NULL,                -- human-friendly label
    kind TEXT NOT NULL,               -- 'cloned' | 'stock'
    engine TEXT NOT NULL,             -- 'chatterbox' | 'gemini_tts'
    reference_path TEXT,              -- for cloned: path to reference audio file
    is_default INTEGER NOT NULL DEFAULT 0,  -- 1 if this is the default voice for the business
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_voices_business ON voices(business_slug);
"""


# ─── Idea Concept Schema (format-neutral first creative act) ──────────────────

IDEA_CONCEPT_SCHEMA = {
    "type": "object",
    "required": ["cards"],
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "idea", "hook_options", "concept_basis", "origin", "source_refs"
                ],
                "properties": {
                    "idea": {"type": "string"},
                    "hook_options": {"type": "array", "items": {"type": "string"}},
                    "concept_basis": {
                        "type": "object",
                        "required": [
                            "core_claim", "audience_value", "narrative_shape",
                            "available_evidence",
                        ],
                        "properties": {
                            "core_claim": {"type": "string"},
                            "audience_value": {"type": "string"},
                            "narrative_shape": {"type": "string"},
                            "available_evidence": {
                                "type": "array", "items": {"type": "string"}
                            },
                        },
                    },
                    "origin": {"type": "string"},
                    "source_refs": {
                        "type": "array", "items": {"type": "integer"}, "minItems": 1
                    },
                    "source_notes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source_id": {"type": "integer"},
                                "note": {"type": "string"},
                            },
                        },
                    },
                    "seed_text": {"type": "string"},
                },
            },
        },
    },
}


# ─── Idea Card Schema (for LLM validation) ───────────────────────────────────

IDEA_CARD_SCHEMA = {
    "type": "object",
    "required": ["cards"],
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["idea", "hook_options", "treatment", "origin", "source_refs"],
                "properties": {
                    "idea": {"type": "string"},
                    "hook_options": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "treatment": {
                        "type": "object",
                        "required": ["scope", "format", "capture_required", "rationale"],
                        "properties": {
                            "scope": {
                                "type": "object",
                                "required": ["type"],
                                "properties": {
                                    "type": {"type": "string"},  # one_off | series_of_n | pillar_with_derivatives
                                    "n": {"type": "integer"},    # only for series_of_n
                                    "cadence": {"type": "string"}, # only for series_of_n
                                },
                            },
                            "format": {
                                "type": "object",
                                "required": [
                                    "primary_platform", "format_name", "experimental",
                                    "constraint_source", "selection_reason",
                                ],
                                "properties": {
                                    "primary_platform": {"type": "string"},
                                    "format_name": {"type": "string"},
                                    "experimental": {"type": "boolean"},
                                    "constraint_source": {
                                        "type": "string",
                                        "enum": ["user_request", "llm_selected"],
                                    },
                                    "selection_reason": {"type": "string"},
                                    "alternatives_considered": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "required": ["platform", "format_name", "reason_not_selected"],
                                            "properties": {
                                                "platform": {"type": "string"},
                                                "format_name": {"type": "string"},
                                                "reason_not_selected": {"type": "string"},
                                            },
                                        },
                                    },
                                    "format_spec": {"type": "string"},  # full spec for experimental formats
                                },
                            },
                            "capture_required": {
                                "type": "array",
                                "items": {"type": "string"},  # list of capture tasks; empty = none
                            },
                            "reuse": {
                                "type": "object",
                                "properties": {
                                    "derived_from": {"type": "integer"},  # parent card ID
                                    "reuse_notes": {"type": "string"},
                                },
                            },
                            "rationale": {"type": "string"},
                        },
                    },
                    "origin": {"type": "string"},  # ai_originated | human_seeded | human_seeded_ai_developed
                    "source_refs": {
                        "type": "array",
                        "items": {"type": "integer"},  # source IDs from the sources table
                        "minItems": 1,  # at least one source required
                    },
                    "source_notes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source_id": {"type": "integer"},
                                "note": {"type": "string"},
                            },
                        },
                    },
                    "evidence_links": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["url"],
                            "properties": {
                                "url": {"type": "string"},
                                "note": {"type": "string"},
                            },
                        },
                    },
                    "seed_text": {"type": "string"},  # only for human-seeded
                },
            },
        },
    },
}


# ─── Draft Schema (for LLM validation) ───────────────────────────────────────

DRAFT_SCHEMA = {
    "type": "object",
    "required": ["platform_content", "visual_direction", "self_audit_flags"],
    "properties": {
        "platform_content": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["platform", "variant_type", "content", "posts"],
                "properties": {
                    "platform": {"type": "string"},
                    "variant_type": {"type": "string"},
                    "content": {"type": "string"},
                    "posts": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "image_prompts": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "visual_direction": {
            "type": "object",
            "required": ["image_prompts", "reference_notes", "shot_format_choices"],
            "properties": {
                "image_prompts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "reference_notes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "shot_format_choices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
            },
        },
        "self_audit_flags": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["line", "rule", "suggestion"],
                "properties": {
                    "line": {"type": "string"},
                    "rule": {"type": "string"},
                    "confidence": {"type": "string"},  # HIGH | MEDIUM | LOW
                    "suggestion": {"type": "string"},
                    "fix_applied": {"type": "string"},  # concrete revised text for auto-fix
                    "status": {"type": "string"},  # applied | dismissed | active (for F2 persistence)
                },
            },
        },
    },
}


# ─── AI Review Loop Schema (T9.5) ────────────────────────────────────────────

ALIGNMENT_CHECK_SCHEMA = {
    "type": "object",
    "required": ["aligned", "issues", "recommendations"],
    "properties": {
        "aligned": {"type": "boolean"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["type", "description", "severity"],
                "properties": {
                    "type": {"type": "string"},  # drift | unapproved_claim | logical_error | missing_element | added_element
                    "description": {"type": "string"},
                    "severity": {"type": "string"},  # high | medium | low
                },
            },
        },
        "recommendations": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}


# ─── Edit Plan Schema (Final Assembly) ─────────────────────────────────────

EDIT_PLAN_SCHEMA = {
    "type": "object",
    "required": ["segments", "canvas"],
    "properties": {
        "segments": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["source", "in", "out"],
                "properties": {
                    "source": {"type": "string"},   # generated:<media_id> | upload:<material_id> | stock:<stock_id>
                    "in": {"type": "number"},        # trim start (seconds)
                    "out": {"type": "number"},       # trim end (seconds)
                    "speed": {"type": "number"},      # optional playback speed
                    "transition_in": {"type": "string"},  # cut | crossfade | slide | whip
                    "overlays": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["type"],
                            "properties": {
                                "type": {"type": "string"},  # caption | text_card | sticker | highlight
                                "text": {"type": "string"},
                                "start": {"type": "number"},
                                "end": {"type": "number"},
                                "style_ref": {"type": "string"},  # ref to Visual Style caption sheet
                                "position": {"type": "string"},   # top | center | bottom
                            },
                        },
                    },
                    "sfx": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["t", "type"],
                            "properties": {
                                "t": {"type": "number"},    # offset within segment (seconds)
                                "type": {"type": "string"},  # whoosh | pop | hit | riser
                            },
                        },
                    },
                },
            },
        },
        "audio": {
            "type": "object",
            "properties": {
                "vo": {
                    "type": "object",
                    "properties": {
                        "take_id": {"type": "string"},  # asset_media VO take id
                        "ducking": {"type": "boolean"},
                    },
                },
                "music": {
                    "type": "object",
                    "properties": {
                        "stock_ref": {"type": "string"},  # stock:<stock_id>
                        "volume": {"type": "number"},
                    },
                },
                "original_audio": {"type": "boolean"},  # keep original clip audio
            },
        },
        "captions": {
            "type": "object",
            "properties": {
                "burned_in": {"type": "boolean"},  # default true for short-form
                "source": {"type": "string"},        # vo_script | transcript
                "style_ref": {"type": "string"},     # Visual Style caption sheet ref
            },
        },
        "canvas": {
            "type": "object",
            "required": ["aspect_ratio", "resolution"],
            "properties": {
                "aspect_ratio": {"type": "string"},   # 9:16 | 1:1 | 16:9
                "resolution": {"type": "string"},     # 1080x1920 | 1080x1080 | 1920x1080
                "duration_target": {"type": "number"}, # target duration in seconds
            },
        },
    },
}


# ─── Compliance Contract Schema (T10.1 — AMENDMENT-008) ─────────────────────
# LLM-authored alongside the edit plan. Defines every required narrative beat
# and its planned representation in the final output.

COMPLIANCE_CONTRACT_SCHEMA = {
    "type": "object",
    "required": ["beats", "summary"],
    "properties": {
        "beats": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "beat_id",
                    "source_excerpt",
                    "requirement_type",
                    "required",
                    "planned_segment_ids",
                    "verification_method",
                ],
                "properties": {
                    "beat_id": {"type": "string"},          # b1, b2, ...
                    "source_excerpt": {"type": "string"},    # exact text from the script
                    "requirement_type": {
                        "type": "string",
                        "enum": [
                            "spoken_dialogue",
                            "caption_text",
                            "visual_element",
                            "hook",
                            "cta",
                            "duration_fit",
                            "format_convention",
                        ],
                    },
                    "required": {"type": "boolean"},        # true = must be present
                    "planned_segment_ids": {
                        "type": "array",
                        "items": {"type": "string"},         # segment indices/IDs from the plan
                    },
                    "planned_time_range": {                   # may be null if no mapping
                        "type": ["object", "null"],
                        "properties": {
                            "start": {"type": "number"},
                            "end": {"type": "number"},
                        },
                    },
                    "verification_method": {
                        "type": "string",
                        "enum": [
                            "audio_transcript_match",
                            "caption_text_match",
                            "keyframe_visual_match",
                            "duration_measurement",
                            "format_convention_check",
                        ],
                    },
                },
            },
        },
        "summary": {"type": "string"},
    },
}


# ─── Final-Output Compliance Review Schema (T10.1 — AMENDMENT-008) ──────────
# Post-render LLM review: receives approved script + contract + plan + facts +
# VO transcript + keyframes + prior findings. Returns verdict + per-beat coverage.

COMPLIANCE_REVIEW_SCHEMA = {
    "type": "object",
    "required": ["verdict", "coverage", "issues", "safe_remediation_scope", "summary"],
    "properties": {
        "verdict": {
            "type": "string",
            "enum": [
                "compliant",
                "revise_plan",
                "regenerate_media",
                "rerender",
                "needs_operator_decision",
            ],
        },
        "coverage": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["beat_id", "status", "evidence"],
                "properties": {
                    "beat_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["verified", "partial", "missing", "unverifiable"],
                    },
                    "evidence": {"type": "string"},
                    "action_needed": {"type": ["string", "null"]},
                },
            },
        },
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["severity", "description", "remediable"],
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "description": {"type": "string"},
                    "beat_id": {"type": "string"},
                    "remediable": {"type": "boolean"},
                },
            },
        },
        "safe_remediation_scope": {
            "type": "array",
            "items": {"type": "string"},
        },
        "summary": {"type": "string"},
    },
}


# ─── Remediation Instruction Schema (T10.1 — AMENDMENT-008) ─────────────────
# LLM produces specific remediation actions within the safe scope.

REMEDIATION_INSTRUCTION_SCHEMA = {
    "type": "object",
    "required": ["escalate", "actions", "estimated_cost_usd", "summary"],
    "properties": {
        "escalate": {"type": "boolean"},               # true = needs_operator_decision
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["action_id", "type", "reason", "beat_ids_affected"],
                "properties": {
                    "action_id": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "revise_plan_timing",
                            "regenerate_media_prompts",
                            "replacement_media",
                            "adjust_caption_rendering",
                            "adjust_audio_mixing",
                            "adjust_renderer_mechanics",
                        ],
                    },
                    "target": {"type": "string"},       # what to change (path-like)
                    "change": {"type": "object"},         # from/to or new value
                    "reason": {"type": "string"},
                    "beat_ids_affected": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "estimated_cost_usd": {"type": "number"},
        "summary": {"type": "string"},
    },
}


# ─── Media Plan Schema (LLM-driven missing-media generation) ────────────────

MEDIA_PLAN_SCHEMA = {
    "type": "object",
    "required": ["media_plan"],
    "properties": {
        "media_plan": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["generator"],
                "properties": {
                    "capture_index": {"type": "integer"},  # legacy field — still accepted
                    "frame": {"type": "integer"},  # v2: frame number from VO timeline
                    "vo_duration": {"type": "number"},  # v2: real VO duration for this frame
                    "capture_task": {"type": "string"},
                    "generator": {"type": "string"},  # stock | ai_video:<model_name> | ai_video | ai_image | voice | animation
                    "search_query": {"type": "string"},  # for stock
                    "generation_prompt": {"type": "string"},  # for ai_video/ai_image/animation
                    "script_text": {"type": "string"},  # for voice
                    "style_directive": {"type": "string"},
                    "fallback_generator": {"type": "string"},  # same format as generator
                    "fallback_prompt": {"type": "string"},
                    "coverage_note": {"type": "string"},  # v2: how the full VO duration is covered
                },
            },
        },
    },
}


# ─── Pipeline Store ──────────────────────────────────────────────────────────

class PipelineStore:
    """
    Data access for the co-production pipeline.
    All state transitions happen through explicit methods — no implicit writes.
    """

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA_SQL)
        # Migrations for existing databases (idempotent)
        # T8.3: add source_refs column to idea_cards if not present
        cols = [r[1] for r in conn.execute("PRAGMA table_info(idea_cards)").fetchall()]
        if "source_refs" not in cols:
            conn.execute("ALTER TABLE idea_cards ADD COLUMN source_refs TEXT")
        if "production_error" not in cols:
            conn.execute("ALTER TABLE idea_cards ADD COLUMN production_error TEXT")
        # T9.3: add platform_content, review_history, review_converged to drafts
        draft_cols = [r[1] for r in conn.execute("PRAGMA table_info(drafts)").fetchall()]
        if "platform_content" not in draft_cols:
            conn.execute("ALTER TABLE drafts ADD COLUMN platform_content TEXT")
        if "review_history" not in draft_cols:
            conn.execute("ALTER TABLE drafts ADD COLUMN review_history TEXT")
        if "review_converged" not in draft_cols:
            conn.execute("ALTER TABLE drafts ADD COLUMN review_converged TEXT")
        # VO-master-timeline: add vo_segments column to assets if not present
        asset_cols = [r[1] for r in conn.execute("PRAGMA table_info(assets)").fetchall()]
        if "vo_segments" not in asset_cols:
            conn.execute("ALTER TABLE assets ADD COLUMN vo_segments TEXT")
        conn.commit()
        conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── Idea Cards ──

    def create_idea_card(
        self,
        business_slug: str,
        idea: str,
        hook_options: list[str],
        treatment: dict,
        origin: str,
        evidence_links: list[dict] = None,
        source_refs: list[int] = None,
        seed_text: str = None,
        parent_id: int = None,
    ) -> int:
        """Create a new idea card. Returns the card ID."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        cursor = conn.execute(
            """INSERT INTO idea_cards
               (business_slug, idea, hook_options, treatment, origin,
                evidence_links, source_refs, seed_text, parent_id, card_state,
                capture_uploads, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', '[]', ?, ?)""",
            (business_slug, idea, json.dumps(hook_options),
             json.dumps(treatment), origin,
             json.dumps(evidence_links or []), json.dumps(source_refs or []),
             seed_text, parent_id, ts, ts),
        )
        card_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return card_id

    def get_idea_card(self, card_id: int) -> dict:
        """Get a single idea card by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM idea_cards WHERE id = ?", (card_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_idea_cards(
        self, business_slug: str, state: str = None,
    ) -> list[dict]:
        """List idea cards for a business, optionally filtered by state."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if state:
            rows = conn.execute(
                "SELECT * FROM idea_cards WHERE business_slug = ? AND card_state = ? ORDER BY id DESC",
                (business_slug, state),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM idea_cards WHERE business_slug = ? ORDER BY id DESC",
                (business_slug,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def list_idea_cards_by_states(
        self, business_slug: str, states: list[str],
    ) -> list[dict]:
        """List idea cards filtered by a set of states."""
        if not states:
            return []
        placeholders = ",".join("?" * len(states))
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM idea_cards WHERE business_slug = ? AND card_state IN ({placeholders}) ORDER BY id DESC",
            [business_slug] + states,
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_card_state(
        self, card_id: int, state: str,
        kill_reason: str = None,
        production_error: dict = None,
    ) -> dict:
        """Transition an idea card to a new state."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        if kill_reason is not None:
            conn.execute(
                "UPDATE idea_cards SET card_state = ?, kill_reason = ?, updated_at = ? WHERE id = ?",
                (state, kill_reason, ts, card_id),
            )
        elif production_error is not None:
            conn.execute(
                "UPDATE idea_cards SET card_state = ?, production_error = ?, updated_at = ? WHERE id = ?",
                (state, json.dumps(production_error), ts, card_id),
            )
        else:
            conn.execute(
                "UPDATE idea_cards SET card_state = ?, updated_at = ? WHERE id = ?",
                (state, ts, card_id),
            )
        conn.commit()
        conn.close()
        return self.get_idea_card(card_id)

    def update_card_treatment(self, card_id: int, treatment: dict) -> dict:
        """Update the treatment on a card (direct-edit at Gate 1)."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            "UPDATE idea_cards SET treatment = ?, updated_at = ? WHERE id = ?",
            (json.dumps(treatment), ts, card_id),
        )
        conn.commit()
        conn.close()
        return self.get_idea_card(card_id)

    def add_capture_upload(self, card_id: int, material_id: int) -> dict:
        """Record a capture upload against an awaiting-capture card."""
        card = self.get_idea_card(card_id)
        if not card:
            return None
        uploads = json.loads(card.get("capture_uploads") or "[]")
        uploads.append(material_id)
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            "UPDATE idea_cards SET capture_uploads = ?, updated_at = ? WHERE id = ?",
            (json.dumps(uploads), ts, card_id),
        )
        conn.commit()
        conn.close()
        return self.get_idea_card(card_id)

    def check_capture_fulfilled(self, card_id: int) -> bool:
        """Check if all capture tasks are fulfilled (uploads exist for each task).
        Returns True if capture_required is empty or all tasks have uploads."""
        card = self.get_idea_card(card_id)
        if not card:
            return False
        treatment = json.loads(card.get("treatment") or "{}")
        capture_required = treatment.get("capture_required", [])
        if not capture_required:
            return True
        uploads = json.loads(card.get("capture_uploads") or "[]")
        # At least one upload per capture task — we check count as a proxy
        # (the UI shows the task list; the operator marks them done)
        return len(uploads) >= len(capture_required)

    def list_series_children(self, parent_id: int) -> list[dict]:
        """List child cards spawned from a series parent."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM idea_cards WHERE parent_id = ? ORDER BY id ASC",
            (parent_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Drafts ──

    def create_draft(
        self,
        business_slug: str,
        idea_card_id: int,
        origin: str,
        format_name: str = None,
        scope: str = None,
    ) -> int:
        """Create a new draft record linked to an idea card. Returns draft ID."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        cursor = conn.execute(
            """INSERT INTO drafts
               (business_slug, idea_card_id, origin, format, scope,
                draft_text, platform_content, visual_direction, self_audit_flags,
                review_history, review_converged,
                draft_version, draft_state, human_edits, feedback_entries,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, '', '[]', '{}', '[]', '[]', NULL,
                       1, 'drafting', '{}', '[]', ?, ?)""",
            (business_slug, idea_card_id, origin, format_name, scope, ts, ts),
        )
        draft_id = cursor.lastrowid
        conn.commit()
        conn.close()
        # Update the idea card state to 'drafting'
        self.update_card_state(idea_card_id, "drafting")
        return draft_id

    def get_draft(self, draft_id: int) -> dict:
        """Get a single draft by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM drafts WHERE id = ?", (draft_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def save_draft_content(
        self,
        draft_id: int,
        draft_text: str,
        visual_direction: dict,
        self_audit_flags: list[dict],
        platform_content: list[dict] = None,
    ) -> dict:
        """Save the LLM-generated draft content and transition to draft_ready.

        T9.3: platform_content is the per-platform text array (the primary
        artifact). draft_text is kept as a backward-compat summary field —
        derived from the first platform_content entry's content for legacy
        views that still read draft_text.
        """
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        # If platform_content provided but draft_text is empty, derive a summary
        if platform_content and not draft_text:
            draft_text = platform_content[0].get("content", "") if platform_content else ""
        conn.execute(
            """UPDATE drafts SET
               draft_text = ?, platform_content = ?, visual_direction = ?,
               self_audit_flags = ?, draft_state = 'draft_ready', updated_at = ?
               WHERE id = ?""",
            (draft_text, json.dumps(platform_content or []),
             json.dumps(visual_direction),
             json.dumps(self_audit_flags), ts, draft_id),
        )
        conn.commit()
        conn.close()
        return self.get_draft(draft_id)

    def update_draft_state(self, draft_id: int, state: str) -> dict:
        """Transition a draft to a new state."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            "UPDATE drafts SET draft_state = ?, updated_at = ? WHERE id = ?",
            (state, ts, draft_id),
        )
        conn.commit()
        conn.close()
        return self.get_draft(draft_id)

    def save_review_history(self, draft_id: int, review_history: list[dict],
                            converged: bool) -> dict:
        """T9.5: Save the AI review loop history and convergence status."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            "UPDATE drafts SET review_history = ?, review_converged = ?, updated_at = ? WHERE id = ?",
            (json.dumps(review_history), "true" if converged else "false", ts, draft_id),
        )
        conn.commit()
        conn.close()
        return self.get_draft(draft_id)

    def save_platform_content(self, draft_id: int, platform_content: list[dict]) -> dict:
        """T9.3: Save updated platform_content (e.g. after AI review loop fix)."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        # Also update draft_text summary from first entry
        draft_text = platform_content[0].get("content", "") if platform_content else ""
        conn.execute(
            "UPDATE drafts SET platform_content = ?, draft_text = ?, updated_at = ? WHERE id = ?",
            (json.dumps(platform_content), draft_text, ts, draft_id),
        )
        conn.commit()
        conn.close()
        return self.get_draft(draft_id)

    def save_human_edits(self, draft_id: int, edits: dict) -> dict:
        """Save direct human edits (authoritative, highest weight).

        DEPRECATED by F1: direct edits now go through save_edited_text which
        writes draft_text directly. This method is kept for historical rows.
        """
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            "UPDATE drafts SET human_edits = ?, updated_at = ? WHERE id = ?",
            (json.dumps(edits), ts, draft_id),
        )
        conn.commit()
        conn.close()
        return self.get_draft(draft_id)

    def save_edited_text(self, draft_id: int, text: str) -> dict:
        """F1 (CORRECTION-feedback-plumbing): Save an operator's direct edit
        of the draft body. Writes draft_text + updated_at only — does NOT
        route through save_draft_content (which resets state and clobbers
        visual_direction/flags). Bumps draft_version.
        """
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            "UPDATE drafts SET draft_text = ?, "
            "draft_version = draft_version + 1, updated_at = ? WHERE id = ?",
            (text, ts, draft_id),
        )
        conn.commit()
        conn.close()
        return self.get_draft(draft_id)

    def update_audit_flag(self, draft_id: int, flag_index: int, action: str) -> dict:
        """F2: Apply or dismiss a self-audit flag by index.

        action = 'apply' | 'dismiss'
        - apply: replaces the flagged line in draft_text with the suggestion,
                 records as direct_edit feedback, bumps version, marks flag status='applied'
        - dismiss: marks flag status='dismissed', records dismissal as feedback
        Returns updated draft dict.
        """
        draft = self.get_draft(draft_id)
        if not draft:
            return None

        flags = json.loads(draft.get("self_audit_flags") or "[]")
        if flag_index < 0 or flag_index >= len(flags):
            return None

        flag = flags[flag_index]

        if action == "apply":
            # Replace the flagged line in draft_text with the suggestion
            draft_text = draft["draft_text"]
            flagged_line = flag.get("line", "")
            suggestion = flag.get("suggestion", "")
            if flagged_line and flagged_line in draft_text:
                draft_text = draft_text.replace(flagged_line, suggestion, 1)
                flag["status"] = "applied"
                # Record as direct edit (highest weight)
                self.add_feedback(
                    business_slug=draft["business_slug"],
                    feedback_type="direct_edit",
                    feedback_text=f"Applied audit suggestion: '{flagged_line}' → '{suggestion}'",
                    draft_id=draft_id,
                    line_reference=flagged_line,
                )
            else:
                # Line no longer exists — mark for manual review
                flag["status"] = "line_changed"
                self.add_feedback(
                    business_slug=draft["business_slug"],
                    feedback_type="text",
                    feedback_text=f"Audit flag line changed — review manually: '{flagged_line}'",
                    draft_id=draft_id,
                )
            # Bump version
            conn = sqlite3.connect(self.db_path)
            ts = self._now()
            conn.execute(
                "UPDATE drafts SET draft_text = ?, self_audit_flags = ?, "
                "draft_version = draft_version + 1, updated_at = ? WHERE id = ?",
                (draft_text, json.dumps(flags), ts, draft_id),
            )
            conn.commit()
            conn.close()
        elif action == "dismiss":
            flag["status"] = "dismissed"
            self.add_feedback(
                business_slug=draft["business_slug"],
                feedback_type="chip",
                feedback_text=f"Dismissed audit flag: rule='{flag.get('rule', '')}' line='{flag.get('line', '')[:100]}'",
                draft_id=draft_id,
            )
            conn = sqlite3.connect(self.db_path)
            ts = self._now()
            conn.execute(
                "UPDATE drafts SET self_audit_flags = ?, updated_at = ? WHERE id = ?",
                (json.dumps(flags), ts, draft_id),
            )
            conn.commit()
            conn.close()

        return self.get_draft(draft_id)

    def increment_draft_version(self, draft_id: int) -> int:
        """Increment the draft version (after a revise cycle). Returns new version."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            "UPDATE drafts SET draft_version = draft_version + 1, draft_state = 'revised', updated_at = ? WHERE id = ?",
            (ts, draft_id),
        )
        conn.commit()
        conn.close()
        d = self.get_draft(draft_id)
        return d["draft_version"] if d else 0

    def list_drafts(
        self, business_slug: str, state: str = None,
    ) -> list[dict]:
        """List drafts for a business, optionally filtered by state."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if state:
            rows = conn.execute(
                "SELECT * FROM drafts WHERE business_slug = ? AND draft_state = ? ORDER BY id DESC",
                (business_slug, state),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM drafts WHERE business_slug = ? ORDER BY id DESC",
                (business_slug,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Assets ──

    def create_asset(
        self,
        business_slug: str,
        draft_id: int,
        platform: str,
        variant_type: str,
        content: str,
        image_prompts: list[str] = None,
        generated_images: list[str] = None,
        posts: list[str] = None,
        native: bool = False,
    ) -> int:
        """Create a new per-platform asset variant. Returns asset ID."""
        conn = sqlite3.connect(self.db_path)
        # Ensure posts column exists (migration for existing DBs)
        cols = [row[1] for row in conn.execute("PRAGMA table_info(assets)").fetchall()]
        if "posts" not in cols:
            conn.execute("ALTER TABLE assets ADD COLUMN posts TEXT")
            conn.commit()
        # S3: Ensure native column exists (idempotent migration)
        if "native" not in cols:
            conn.execute("ALTER TABLE assets ADD COLUMN native INTEGER DEFAULT 0")
            conn.commit()
        ts = self._now()
        cursor = conn.execute(
            """INSERT INTO assets
               (business_slug, draft_id, platform, variant_type, content, posts,
                image_prompts, generated_images, asset_state, native,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (business_slug, draft_id, platform, variant_type, content,
             json.dumps(posts or []),
             json.dumps(image_prompts or []),
             json.dumps(generated_images or []),
             1 if native else 0, ts, ts),
        )
        asset_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return asset_id

    def get_asset(self, asset_id: int) -> dict:
        """Get a single asset by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_assets(self, draft_id: int) -> list[dict]:
        """List all asset variants for a draft."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM assets WHERE draft_id = ? ORDER BY id ASC",
            (draft_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_asset_state(self, asset_id: int, state: str) -> dict:
        """Transition an asset to a new state."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            "UPDATE assets SET asset_state = ?, updated_at = ? WHERE id = ?",
            (state, ts, asset_id),
        )
        conn.commit()
        conn.close()
        return self.get_asset(asset_id)

    def set_asset_schedule(self, asset_id: int, scheduled_at: str) -> dict:
        """Set the publish schedule for an approved asset."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            "UPDATE assets SET publish_scheduled_at = ?, updated_at = ? WHERE id = ?",
            (scheduled_at, ts, asset_id),
        )
        conn.commit()
        conn.close()
        return self.get_asset(asset_id)

    def save_vo_segments(self, asset_id: int, vo_segments_json: str):
        """Store per-frame VO segments on the asset row."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            "UPDATE assets SET vo_segments = ?, updated_at = ? WHERE id = ?",
            (vo_segments_json, ts, asset_id),
        )
        conn.commit()
        conn.close()

    def get_vo_segments(self, asset_id: int) -> str | None:
        """Retrieve stored VO segments JSON for an asset."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT vo_segments FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        conn.close()
        return row["vo_segments"] if row else None

    # ── Feedback Log ──

    def add_feedback(
        self,
        business_slug: str,
        feedback_type: str,
        feedback_text: str,
        draft_id: int = None,
        idea_card_id: int = None,
        line_reference: str = None,
    ) -> int:
        """Add a feedback log entry. Weight is determined by type."""
        weight_map = {
            "chip": 1,
            "kill_reason": 1,
            "text": 2,
            "direct_edit": 3,
        }
        weight = weight_map.get(feedback_type, 1)
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        cursor = conn.execute(
            """INSERT INTO feedback_log
               (business_slug, draft_id, idea_card_id, feedback_type,
                feedback_text, line_reference, weight, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (business_slug, draft_id, idea_card_id, feedback_type,
             feedback_text, line_reference, weight, ts),
        )
        entry_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return entry_id

    def list_feedback(
        self, business_slug: str, draft_id: int = None,
    ) -> list[dict]:
        """List feedback entries, optionally filtered by draft."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if draft_id:
            rows = conn.execute(
                "SELECT * FROM feedback_log WHERE business_slug = ? AND draft_id = ? ORDER BY id ASC",
                (business_slug, draft_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM feedback_log WHERE business_slug = ? ORDER BY id ASC",
                (business_slug,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Nightly Performance Note ──

    def get_pipeline_stats(self, business_slug: str) -> dict:
        """Get stats for the nightly performance note: origin/format/scope breakdown."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Count shipped drafts by origin
        shipped = conn.execute(
            "SELECT origin, format, scope FROM drafts WHERE business_slug = ? AND draft_state = 'shipped'",
            (business_slug,),
        ).fetchall()

        # Count published assets
        published = conn.execute(
            "SELECT platform, variant_type FROM assets WHERE business_slug = ? AND asset_state = 'published'",
            (business_slug,),
        ).fetchall()

        # Count idea cards by origin and state
        cards = conn.execute(
            "SELECT origin, card_state FROM idea_cards WHERE business_slug = ?",
            (business_slug,),
        ).fetchall()

        conn.close()

        origin_breakdown = {}
        for row in shipped:
            origin = row["origin"]
            origin_breakdown[origin] = origin_breakdown.get(origin, 0) + 1

        format_breakdown = {}
        for row in shipped:
            fmt = row["format"]
            if fmt:
                format_breakdown[fmt] = format_breakdown.get(fmt, 0) + 1

        scope_breakdown = {}
        for row in shipped:
            scope = row["scope"]
            if scope:
                scope_breakdown[scope] = scope_breakdown.get(scope, 0) + 1

        card_origin_breakdown = {}
        for row in cards:
            origin = row["origin"]
            state = row["card_state"]
            key = f"{origin}/{state}"
            card_origin_breakdown[key] = card_origin_breakdown.get(key, 0) + 1

        return {
            "shipped_drafts": len(shipped),
            "published_assets": len(published),
            "origin_breakdown": origin_breakdown,
            "format_breakdown": format_breakdown,
            "scope_breakdown": scope_breakdown,
            "card_origin_breakdown": card_origin_breakdown,
        }

    # ── Edit Plans (Final Assembly) ──

    # T10.2: Extended edit_plans schema with compliance contract, source hash, round history
    EDIT_PLAN_SCHEMA = """
CREATE TABLE IF NOT EXISTS edit_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    plan_json TEXT NOT NULL,
    feedback TEXT,
    status TEXT NOT NULL DEFAULT 'proposed',
    compliance_contract_json TEXT,         -- T10.2: LLM-authored compliance contract
    source_draft_hash TEXT,                -- T10.2: SHA-256 of platform_content at plan creation
    review_round_history TEXT,             -- T10.2: JSON array of {round, verdict, actions, artifact_hashes}
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (draft_id) REFERENCES drafts(id),
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);
"""

    def _ensure_edit_plan_columns(self, conn):
        """T10.2: Migrate edit_plans table — add new columns if they don't exist."""
        cols = {row[1] for row in conn.execute("PRAGMA table_info(edit_plans)").fetchall()}
        if "compliance_contract_json" not in cols:
            conn.execute("ALTER TABLE edit_plans ADD COLUMN compliance_contract_json TEXT")
        if "source_draft_hash" not in cols:
            conn.execute("ALTER TABLE edit_plans ADD COLUMN source_draft_hash TEXT")
        if "review_round_history" not in cols:
            conn.execute("ALTER TABLE edit_plans ADD COLUMN review_round_history TEXT")
        conn.commit()

    def save_edit_plan(self, draft_id: int, asset_id: int, plan: dict,
                       compliance_contract: dict = None, source_draft_hash: str = None) -> int:
        """Save an edit plan for an asset. Returns edit_plan row ID.

        T10.2: Optionally saves the compliance contract and source draft hash.
        """
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        # Create edit_plans table if not exists
        conn.executescript(self.EDIT_PLAN_SCHEMA)
        self._ensure_edit_plan_columns(conn)
        cursor = conn.execute(
            """INSERT INTO edit_plans
               (draft_id, asset_id, plan_json, status, compliance_contract_json,
                source_draft_hash, review_round_history, created_at, updated_at)
               VALUES (?, ?, ?, 'proposed', ?, ?, '[]', ?, ?)""",
            (draft_id, asset_id, json.dumps(plan),
             json.dumps(compliance_contract) if compliance_contract else None,
             source_draft_hash,
             ts, ts),
        )
        plan_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return plan_id

    def get_edit_plan(self, plan_id: int) -> dict:
        """Get an edit plan by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM edit_plans WHERE id = ?", (plan_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_edit_plans(self, asset_id: int) -> list[dict]:
        """List all edit plans for an asset."""
        conn = sqlite3.connect(self.db_path)
        # Ensure edit_plans table exists with T10.2 columns
        conn.executescript(self.EDIT_PLAN_SCHEMA)
        self._ensure_edit_plan_columns(conn)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM edit_plans WHERE asset_id = ? ORDER BY id DESC",
            (asset_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_edit_plan_status(self, plan_id: int, status: str, feedback: str = None) -> dict:
        """Update edit plan status (proposed → approved → rendering → rendered → failed)."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        if feedback:
            conn.execute(
                "UPDATE edit_plans SET status = ?, feedback = ?, updated_at = ? WHERE id = ?",
                (status, feedback, ts, plan_id),
            )
        else:
            conn.execute(
                "UPDATE edit_plans SET status = ?, updated_at = ? WHERE id = ?",
                (status, ts, plan_id),
            )
        conn.commit()
        conn.close()
        return self.get_edit_plan(plan_id)

    def append_review_round(self, plan_id: int, round_entry: dict) -> dict:
        """T10.2: Append a review round entry to review_round_history (append-only).

        round_entry: {round, verdict, actions_taken, artifact_hashes, ...}
        Returns the updated edit plan.
        """
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        self._ensure_edit_plan_columns(conn)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT review_round_history FROM edit_plans WHERE id = ?", (plan_id,)
        ).fetchone()
        if not row:
            conn.close()
            return None
        history = json.loads(row["review_round_history"] or "[]")
        history.append(round_entry)
        conn.execute(
            "UPDATE edit_plans SET review_round_history = ?, updated_at = ? WHERE id = ?",
            (json.dumps(history), ts, plan_id),
        )
        conn.commit()
        conn.close()
        return self.get_edit_plan(plan_id)

    def get_review_round_history(self, plan_id: int) -> list[dict]:
        """T10.2: Get the review round history for an edit plan."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT review_round_history FROM edit_plans WHERE id = ?", (plan_id,)
        ).fetchone()
        conn.close()
        if not row:
            return []
        return json.loads(row["review_round_history"] or "[]")

    def get_compliance_contract(self, plan_id: int) -> dict | None:
        """T10.2: Get the compliance contract for an edit plan."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT compliance_contract_json, source_draft_hash FROM edit_plans WHERE id = ?",
            (plan_id,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        contract = None
        if row["compliance_contract_json"]:
            contract = json.loads(row["compliance_contract_json"])
        return {
            "contract": contract,
            "source_draft_hash": row["source_draft_hash"],
        }

    # ── Source Bank (T8.3) ──

    def add_source(
        self,
        business_slug: str,
        source_type: str,
        title: str,
        url: str = None,
        summary: str = None,
        content: str = None,
        origin: str = "system",
        content_hash: str = None,
    ) -> int:
        """Add a source to the Source Bank. Dedupes on content_hash.
        Returns the source ID (existing if deduped)."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        # Check for existing source with same hash
        if content_hash:
            existing = conn.execute(
                "SELECT id FROM sources WHERE business_slug = ? AND content_hash = ? AND status = 'active'",
                (business_slug, content_hash),
            ).fetchone()
            if existing:
                conn.close()
                return existing[0]
        cursor = conn.execute(
            """INSERT INTO sources
               (business_slug, source_type, title, url, summary, content,
                origin, first_seen, content_hash, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
            (business_slug, source_type, title, url, summary, content,
             origin, ts, content_hash),
        )
        source_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return source_id

    def get_source(self, source_id: int) -> dict:
        """Get a single source by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_sources(
        self, business_slug: str, status: str = "active",
        limit: int = 100,
    ) -> list[dict]:
        """List sources for a business, optionally filtered by status.
        Ordered by most recently first_seen first."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT * FROM sources
               WHERE business_slug = ? AND status = ?
               ORDER BY first_seen DESC LIMIT ?""",
            (business_slug, status, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def resolve_source_refs(self, business_slug: str, source_refs: list[int]) -> list[dict]:
        """Resolve a list of source IDs to their full source records.
        Returns only sources that exist and belong to the given business."""
        if not source_refs:
            return []
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(source_refs))
        rows = conn.execute(
            f"""SELECT * FROM sources
               WHERE id IN ({placeholders}) AND business_slug = ?
               AND status = 'active'""",
            (*source_refs, business_slug),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def archive_source(self, source_id: int) -> dict:
        """Archive a source (soft delete)."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE sources SET status = 'archived' WHERE id = ?",
            (source_id,),
        )
        conn.commit()
        conn.close()
        return self.get_source(source_id)