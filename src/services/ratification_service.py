"""
VF-CP-003 — Composition ratification surface.

Assembles the CompositionPlan with per-element previews for operator
ratification. Provides the single Ratify composition action plus a
Reject-with-feedback path that sends the plan back to composition
planning.

States covered:

- ``plan_generated`` — plan exists but previews not yet generated
- ``preview_generating`` — some previews exist, some are missing
- ``ready_for_review`` — all previews generated and all elements trace
  to an approved manifest ingredient
- ``ratified`` — operator approved; spec hash is bound
- ``rejected`` — operator rejected with structured feedback; session
  transitions back to ``composition_planning``
- ``stale`` — plan hash changed after ratification (spec hash mismatch)

No false greens. Ratify is only enabled when every preview exists and
every audio/visual element's ``source_hash`` traces to a candidate in
the frozen manifest. Text elements must trace to the Writer contract.

Ratification decisions are persisted in
``composition_ratifications`` so the full decision history is available
for lineage and re-ratification after stale.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS composition_ratifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    production_session_id INTEGER NOT NULL,
    plan_hash TEXT NOT NULL,
    decision TEXT NOT NULL,
    feedback TEXT,
    actor TEXT NOT NULL DEFAULT 'operator',
    created_at TEXT NOT NULL,
    FOREIGN KEY (production_session_id) REFERENCES production_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_comp_rat_session
    ON composition_ratifications(production_session_id);
CREATE INDEX IF NOT EXISTS idx_comp_rat_hash
    ON composition_ratifications(plan_hash);
"""


# ── Ratification status values ─────────────────────────────────────────────

STATUS_PLAN_GENERATED = "plan_generated"
STATUS_PREVIEW_GENERATING = "preview_generating"
STATUS_READY_FOR_REVIEW = "ready_for_review"
STATUS_RATIFIED = "ratified"
STATUS_REJECTED = "rejected"
STATUS_STALE = "stale"


class RatificationError(Exception):
    """Ratification surface error."""
    pass


class RatificationService:
    """Assemble plan + previews + state for operator ratification.

    Parameters
    ----------
    db_path
        Path to the ViralFactory SQLite database.
    config_dir
        Directory containing ``render_styles.yaml`` and ``models.yaml``.
    """

    def __init__(
        self,
        db_path: str = "data/viralfactory.db",
        config_dir: str = "config",
    ) -> None:
        self.db_path = db_path
        self.config_dir = config_dir
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()

    # ── internal helpers ──────────────────────────────────────────────

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        conn.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── public API ────────────────────────────────────────────────────

    def build_ratification_view(
        self,
        business_slug: str,
        production_session_id: int,
        plan: dict,
        previews: dict[str, list[str]],
        manifest: Optional[dict] = None,
        writer_contract: Optional[dict] = None,
        preview_generator=None,
    ) -> dict:
        """Assemble plan + previews + state for rendering.

        Parameters
        ----------
        business_slug
            Tenant slug.
        production_session_id
            Production session ID.
        plan
            The CompositionPlan dict (as produced by
            ``CompositionPlanGenerator.generate``).
        previews
            Mapping of category → list of preview file paths, as
            produced by ``CompositionPreviewGenerator.generate_all``.
            May be empty or partial — the service detects missing
            previews and never reports a false green.
        manifest
            Optional frozen manifest dict. When provided, every
            audio/visual element's ``source_hash`` is checked against
            manifest candidate hashes.  When omitted, manifest tracing
            is skipped (useful for unit tests that only exercise
            preview readiness).
        writer_contract
            Optional Writer contract dict. When provided, text elements
            are traced to ``text_intents``.  When omitted, text tracing
            is skipped.
        preview_generator
            Optional ``CompositionPreviewGenerator`` instance.  When
            provided, the service will call ``generate_all`` to produce
            previews if the ``previews`` dict is empty.  When omitted,
            the caller is responsible for generating previews.

        Returns
        -------
        dict
            {
                "session": {...},
                "plan": {...},
                "previews": {...},
                "plan_hash": "...",
                "status": "ready_for_review" | ...,
                "ratify_enabled": bool,
                "stale": bool,
                "previous_ratification": {...} or None,
            }
        """
        from services.production_orchestrator import ProductionSessionService

        session_svc = ProductionSessionService(db_path=self.db_path)
        session = session_svc.get_session(business_slug, production_session_id)

        plan_hash = plan.get("plan_hash", "")
        if not plan_hash:
            from services.composition_plan import compute_plan_hash
            plan_hash = compute_plan_hash(plan)

        # ── Generate previews if a generator is supplied and none given
        if not previews and preview_generator is not None:
            try:
                previews = preview_generator.generate_all(plan)
            except Exception:
                previews = {}

        # ── Check preview completeness
        previews_complete, preview_gaps = self._check_previews(plan, previews)

        # ── Check manifest tracing
        manifest_ok, manifest_gaps = self._check_manifest_tracing(
            plan, manifest, writer_contract
        )

        # ── Determine stale
        stale = self.check_stale(business_slug, production_session_id, plan_hash)

        # ── Previous ratification
        previous = self.get_latest_ratification(business_slug, production_session_id)

        # ── Determine status
        status = self._compute_status(
            session, plan_hash, previews_complete, manifest_ok, stale, previous
        )

        # ── Ratify enabled only when all checks pass
        ratify_enabled = (
            previews_complete
            and manifest_ok
            and not stale
            and status in (STATUS_READY_FOR_REVIEW,)
        )

        return {
            "session": session,
            "plan": plan,
            "previews": previews,
            "plan_hash": plan_hash,
            "status": status,
            "ratify_enabled": ratify_enabled,
            "stale": stale,
            "previous_ratification": previous,
            "preview_gaps": preview_gaps,
            "manifest_gaps": manifest_gaps,
        }

    def ratify(
        self,
        business_slug: str,
        production_session_id: int,
        plan: dict,
        previews: dict[str, list[str]],
        manifest: Optional[dict] = None,
        writer_contract: Optional[dict] = None,
        actor: str = "operator",
        feedback: str = None,
    ) -> dict:
        """Operator approves the plan.

        Binds the spec (plan) hash, transitions the session to
        ``composition_ratified``, and records the decision.

        Raises ``RatificationError`` if previews are incomplete, any
        element fails to trace to the manifest, or the session is not
        in ``composition_review_required``.
        """
        from services.production_orchestrator import (
            ProductionSessionService,
            STATE_COMPOSITION_REVIEW_REQUIRED,
            STATE_COMPOSITION_RATIFIED,
        )

        view = self.build_ratification_view(
            business_slug,
            production_session_id,
            plan,
            previews,
            manifest,
            writer_contract,
        )

        if not view["ratify_enabled"]:
            gaps = view.get("preview_gaps", []) + view.get("manifest_gaps", [])
            raise RatificationError(
                "Cannot ratify — not ready: " + "; ".join(gaps)
            )

        session = view["session"]
        if session["current_state"] != STATE_COMPOSITION_REVIEW_REQUIRED:
            raise RatificationError(
                f"Session state is '{session['current_state']}', "
                f"must be '{STATE_COMPOSITION_REVIEW_REQUIRED}'"
            )

        plan_hash = view["plan_hash"]

        # Record the decision
        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """INSERT INTO composition_ratifications
               (business_slug, production_session_id, plan_hash,
                decision, feedback, actor, created_at)
               VALUES (?, ?, ?, 'ratify', ?, ?, ?)""",
            (business_slug, production_session_id, plan_hash,
             feedback, actor, ts),
        )
        decision_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Bind the spec hash on the session
        session_svc = ProductionSessionService(db_path=self.db_path)
        session_svc.set_composition_plan_hash(
            business_slug, production_session_id, plan_hash
        )

        # Transition to composition_ratified
        session_svc.transition(
            business_slug, production_session_id,
            STATE_COMPOSITION_RATIFIED,
            "operator ratified plan",
            actor=actor,
        )

        return self._fetch_decision(decision_id)

    def reject(
        self,
        business_slug: str,
        production_session_id: int,
        feedback: str,
        actor: str = "operator",
    ) -> dict:
        """Operator rejects the plan with structured feedback.

        Transitions the session back to ``composition_planning`` and
        records the decision.
        """
        from services.production_orchestrator import (
            ProductionSessionService,
            STATE_COMPOSITION_REVIEW_REQUIRED,
            STATE_COMPOSITION_PLANNING,
        )

        session_svc = ProductionSessionService(db_path=self.db_path)
        session = session_svc.get_session(business_slug, production_session_id)

        # Reject is valid from composition_review_required or
        # composition_planning (operator may abort early).
        allowed_states = {
            STATE_COMPOSITION_REVIEW_REQUIRED,
            STATE_COMPOSITION_PLANNING,
        }
        if session["current_state"] not in allowed_states:
            raise RatificationError(
                f"Session state is '{session['current_state']}', "
                f"must be one of {sorted(allowed_states)}"
            )

        # Use the session's active plan hash if available
        plan_hash = session.get("active_composition_plan_hash") or ""

        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """INSERT INTO composition_ratifications
               (business_slug, production_session_id, plan_hash,
                decision, feedback, actor, created_at)
               VALUES (?, ?, ?, 'reject', ?, ?, ?)""",
            (business_slug, production_session_id, plan_hash,
             feedback, actor, ts),
        )
        decision_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Transition back to composition_planning
        if session["current_state"] == STATE_COMPOSITION_REVIEW_REQUIRED:
            session_svc.transition(
                business_slug, production_session_id,
                STATE_COMPOSITION_PLANNING,
                "operator rejected plan: " + feedback[:200],
                actor=actor,
            )

        return self._fetch_decision(decision_id)

    def get_ratification_status(
        self,
        business_slug: str,
        production_session_id: int,
        plan: Optional[dict] = None,
        previews: Optional[dict[str, list[str]]] = None,
        manifest: Optional[dict] = None,
        writer_contract: Optional[dict] = None,
    ) -> str:
        """Return the current ratification status.

        Returns one of:
        ``plan_generated``, ``preview_generating``,
        ``ready_for_review``, ``ratified``, ``rejected``, ``stale``.
        """
        from services.production_orchestrator import (
            ProductionSessionService,
            STATE_COMPOSITION_RATIFIED,
            STATE_COMPOSITION_PLANNING,
            STATE_COMPOSITION_REVIEW_REQUIRED,
        )

        session_svc = ProductionSessionService(db_path=self.db_path)
        session = session_svc.get_session(business_slug, production_session_id)
        state = session["current_state"]

        # If ratified, check for stale
        if state == STATE_COMPOSITION_RATIFIED:
            if plan is not None:
                plan_hash = plan.get("plan_hash", "")
                if not plan_hash:
                    from services.composition_plan import compute_plan_hash
                    plan_hash = compute_plan_hash(plan)
                if self.check_stale(business_slug, production_session_id, plan_hash):
                    return STATUS_STALE
            return STATUS_RATIFIED

        # If in composition_planning and there's a prior rejection
        if state == STATE_COMPOSITION_PLANNING:
            previous = self.get_latest_ratification(
                business_slug, production_session_id
            )
            if previous and previous["decision"] == "reject":
                return STATUS_REJECTED

        # If plan is provided, compute preview/manifest readiness
        if plan is not None:
            view = self.build_ratification_view(
                business_slug,
                production_session_id,
                plan,
                previews or {},
                manifest,
                writer_contract,
            )
            return view["status"]

        # No plan — plan not yet generated
        return STATUS_PLAN_GENERATED

    def check_stale(
        self,
        business_slug: str,
        production_session_id: int,
        plan_hash: str,
    ) -> bool:
        """Detect if the plan changed after ratification.

        Compares the given ``plan_hash`` against the most recent
        ratified plan hash.  If they differ, the ratification is stale.
        """
        previous = self.get_latest_ratification(
            business_slug, production_session_id
        )
        if not previous:
            return False
        if previous["decision"] != "ratify":
            return False
        return previous["plan_hash"] != plan_hash

    # ── private methods ───────────────────────────────────────────────

    def _fetch_decision(self, decision_id: int) -> dict:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM composition_ratifications WHERE id = ?",
            (decision_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else {}

    def get_latest_ratification(
        self,
        business_slug: str,
        production_session_id: int,
    ) -> Optional[dict]:
        """Get the most recent ratification decision for a session."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT * FROM composition_ratifications
               WHERE business_slug = ? AND production_session_id = ?
               ORDER BY id DESC LIMIT 1""",
            (business_slug, production_session_id),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_ratification_history(
        self,
        business_slug: str,
        production_session_id: int,
    ) -> list[dict]:
        """Get all ratification decisions for a session, newest first."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT * FROM composition_ratifications
               WHERE business_slug = ? AND production_session_id = ?
               ORDER BY id DESC""",
            (business_slug, production_session_id),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _check_previews(
        self,
        plan: dict,
        previews: dict[str, list[str]],
    ) -> tuple[bool, list[str]]:
        """Check that all plan elements have previews.

        Returns (complete, gaps).
        """
        gaps: list[str] = []

        # Text previews
        for te in plan.get("text_elements", []):
            eid = te.get("element_id", "")
            if not self._has_preview(previews, "text", eid):
                gaps.append(f"Missing text preview: {eid}")

        # Audio preview (single, keyed by "mix")
        audio = plan.get("audio", {})
        if audio and (audio.get("vo_track") or audio.get("music_track")
                       or audio.get("sfx_events")):
            if not self._has_preview(previews, "audio", "mix"):
                gaps.append("Missing audio mix preview")

        # Visual previews
        for ve in plan.get("visual_elements", []):
            eid = ve.get("element_id", "")
            if not self._has_preview(previews, "visual", eid):
                gaps.append(f"Missing visual preview: {eid}")

        # Graphics previews
        for ge in plan.get("graphics_elements", []):
            eid = ge.get("element_id", "")
            if not self._has_preview(previews, "graphics", eid):
                gaps.append(f"Missing graphics preview: {eid}")

        # Transition previews
        for tr in plan.get("transitions", []):
            eid = tr.get("transition_id", "")
            if not self._has_preview(previews, "transition", eid):
                gaps.append(f"Missing transition preview: {eid}")

        # Timeline preview
        if not self._has_preview(previews, "timeline", "full"):
            gaps.append("Missing full timeline preview")

        return (len(gaps) == 0, gaps)

    @staticmethod
    def _has_preview(
        previews: dict[str, list[str]],
        category: str,
        element_id: str,
    ) -> bool:
        """Check that a preview path exists and points to a real file."""
        paths = previews.get(category, [])
        for p in paths:
            basename = os.path.basename(p)
            if element_id in basename:
                return os.path.exists(p) and os.path.getsize(p) > 0
        # If no element_id match but category has paths and element_id
        # is "mix" or "full" (single-preview categories), accept the
        # first non-empty path.
        if element_id in ("mix", "full") and paths:
            return os.path.exists(paths[0]) and os.path.getsize(paths[0]) > 0
        return False

    def _check_manifest_tracing(
        self,
        plan: dict,
        manifest: Optional[dict],
        writer_contract: Optional[dict],
    ) -> tuple[bool, list[str]]:
        """Check that all elements trace to approved manifest ingredients.

        - Audio VO/music ``source_hash`` must be in manifest candidates
        - Visual element ``source_hash`` must be in manifest candidates
        - Text elements must trace to Writer contract text_intents
          (when writer_contract is provided)

        Returns (ok, gaps).
        """
        gaps: list[str] = []

        if manifest is None and writer_contract is None:
            return (True, [])

        # Build manifest hash set
        manifest_hashes: set[str] = set()
        if manifest:
            manifest_data = manifest
            if isinstance(manifest_data, dict) and "manifest_json" in manifest_data:
                manifest_data = manifest["manifest_json"]
            if isinstance(manifest_data, str):
                manifest_data = json.loads(manifest_data)
            for c in manifest_data.get("candidates", []):
                h = c.get("artifact_hash")
                if h:
                    manifest_hashes.add(h)

        # Audio tracing
        audio = plan.get("audio", {})
        vo_track = audio.get("vo_track")
        if vo_track and manifest:
            if vo_track.get("source_hash") not in manifest_hashes:
                gaps.append(
                    f"VO track source_hash not in manifest: "
                    f"{vo_track.get('source_hash')}"
                )
        music_track = audio.get("music_track")
        if music_track and manifest:
            if music_track.get("source_hash") not in manifest_hashes:
                gaps.append(
                    f"Music track source_hash not in manifest: "
                    f"{music_track.get('source_hash')}"
                )

        # Visual tracing
        for ve in plan.get("visual_elements", []):
            if manifest:
                if ve.get("source_hash") not in manifest_hashes:
                    gaps.append(
                        f"Visual element '{ve.get('element_id')}' "
                        f"source_hash not in manifest: "
                        f"{ve.get('source_hash')}"
                    )

        # Text tracing
        if writer_contract:
            text_intents_by_id: dict[str, dict] = {}
            for ti in writer_contract.get("text_intents", []):
                text_intents_by_id[ti["text_intent_id"]] = ti

            beat_evidence_refs: dict[str, list[str]] = {}
            for beat in writer_contract.get("beats", []):
                beat_evidence_refs[beat.get("beat_id", "")] = (
                    beat.get("evidence_refs") or []
                )

            for te in plan.get("text_elements", []):
                role = te.get("role", "")
                text = te.get("text", "")
                if role == "citation":
                    beat_id = te.get("beat_id", "")
                    refs = beat_evidence_refs.get(beat_id, [])
                    if text not in refs:
                        gaps.append(
                            f"Text element '{te.get('element_id')}' "
                            f"(citation) text not in beat '{beat_id}' "
                            f"evidence_refs"
                        )
                else:
                    ti_id = te.get("text_intent_id")
                    if not ti_id:
                        gaps.append(
                            f"Text element '{te.get('element_id')}' "
                            f"has no text_intent_id"
                        )
                    elif ti_id not in text_intents_by_id:
                        gaps.append(
                            f"Text element '{te.get('element_id')}' "
                            f"references unknown text_intent_id: {ti_id}"
                        )
                    else:
                        ti = text_intents_by_id[ti_id]
                        if ti.get("text", "") != text:
                            gaps.append(
                                f"Text element '{te.get('element_id')}' "
                                f"text does not match text_intent '{ti_id}'"
                            )

        return (len(gaps) == 0, gaps)

    def _compute_status(
        self,
        session: dict,
        plan_hash: str,
        previews_complete: bool,
        manifest_ok: bool,
        stale: bool,
        previous: Optional[dict],
    ) -> str:
        """Compute the ratification status from all signals."""
        from services.production_orchestrator import (
            STATE_COMPOSITION_RATIFIED,
            STATE_COMPOSITION_PLANNING,
            STATE_COMPOSITION_REVIEW_REQUIRED,
        )

        state = session["current_state"]

        # Stale takes priority — plan changed post-ratification
        if stale:
            return STATUS_STALE

        # Ratified
        if state == STATE_COMPOSITION_RATIFIED:
            return STATUS_RATIFIED

        # Rejected (back in composition_planning with prior reject)
        if state == STATE_COMPOSITION_PLANNING:
            if previous and previous["decision"] == "reject":
                return STATUS_REJECTED

        # Ready for review only when previews and manifest both pass
        if previews_complete and manifest_ok:
            return STATUS_READY_FOR_REVIEW

        # Previews exist but not all — generating
        if previews_complete is False and self._has_any_previews(session, plan_hash):
            return STATUS_PREVIEW_GENERATING

        # Plan exists but no previews yet
        return STATUS_PLAN_GENERATED

    @staticmethod
    def _has_any_previews(session: dict, plan_hash: str) -> bool:
        """Heuristic: check if any preview files exist for this plan hash.

        Looks in the default cache directory for a subfolder matching
        the plan hash.  This is a lightweight check — the authoritative
        completeness check is in ``_check_previews``.
        """
        cache_root = os.path.join("data", "previews")
        plan_cache = os.path.join(cache_root, plan_hash)
        if os.path.isdir(plan_cache):
            files = os.listdir(plan_cache)
            if any(f.endswith(".png") for f in files):
                return True
        return False