"""
ViralFactory — Episode Bootstrap Flow (T11.5 — CORRECTION-episode-format §2.3)

Guided one-time-per-show sequence that proposes reference assets to the
registry. Every step goes through the existing gate: the AI generates
candidates, the operator picks and approves each through the gate.

Flow per §2.3:
1. Generate character candidates from operator's seed description → operator picks/approves
2. Generate each location plate conditioned on the grade token → approve
3. Generate 3 music beds (one per register) → approve
4. Card styles derived from the visual-style module → approve

The harness contains NO show-specific strings. The bootstrap flow is generic:
it takes a format module (the show bible) and a reference asset store, then
proposes candidates. The operator approves each through the gate.

After bootstrap, episodes reference these assets; they never regenerate them.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BootstrapStep:
    """One step in the guided bootstrap sequence."""
    step_number: int
    name: str                           # "characters", "locations", "music_beds", "card_styles"
    description: str                     # what this step does
    asset_kind: str                      # reference_assets kind
    candidates: list = field(default_factory=list)  # proposed candidate dicts
    approved_ids: list = field(default_factory=list)  # approved asset IDs
    status: str = "pending"              # "pending" | "proposing" | "awaiting_approval" | "done"

    def to_dict(self) -> dict:
        return {
            "step": self.step_number,
            "name": self.name,
            "description": self.description,
            "asset_kind": self.asset_kind,
            "candidates": self.candidates,
            "approved_ids": self.approved_ids,
            "status": self.status,
        }


class EpisodeBootstrapFlow:
    """Guided bootstrap for an episode-format show.

    The flow is driven by the episode-format module (the show bible), which
    defines what characters, locations, registers, and card styles the show
    needs. This class proposes candidates to the reference asset registry;
    the operator approves each through the existing gate.

    No show-specific strings here. The format module provides the names and
    descriptions; this class is the generic engine.
    """

    def __init__(self, ref_store, format_module: dict, business_slug: str):
        """
        Args:
            ref_store: ReferenceAssetStore instance
            format_module: The episode-format module dict (the show bible)
            business_slug: Current business slug
        """
        self.ref_store = ref_store
        self.format_module = format_module
        self.business_slug = business_slug

        # Build the step sequence from the format module
        self.steps = self._build_steps()

    def _build_steps(self) -> list[BootstrapStep]:
        """Build the 4-step bootstrap sequence from the format module."""
        steps = []

        # Step 1: Characters
        cast = self.format_module.get("cast", [])
        steps.append(BootstrapStep(
            step_number=1,
            name="characters",
            description=(
                "Generate character candidates from the operator's seed description. "
                "Operator picks and approves the canonical set."
            ),
            asset_kind="character_ref",
        ))

        # Step 2: Locations (conditioned on grade token)
        steps.append(BootstrapStep(
            step_number=2,
            name="locations",
            description=(
                "Generate each location plate conditioned on the grade token. "
                "Operator approves each location."
            ),
            asset_kind="location_ref",
        ))

        # Step 3: Music beds (one per register)
        steps.append(BootstrapStep(
            step_number=3,
            name="music_beds",
            description=(
                "Generate music beds — one per register. Operator approves each."
            ),
            asset_kind="music_bed",
        ))

        # Step 4: Card styles (from visual-style module)
        steps.append(BootstrapStep(
            step_number=4,
            name="card_styles",
            description=(
                "Card styles derived from the visual-style module. Operator approves each."
            ),
            asset_kind="card_style",
        ))

        return steps

    def get_step(self, step_number: int) -> Optional[BootstrapStep]:
        """Get a step by number (1-4)."""
        for s in self.steps:
            if s.step_number == step_number:
                return s
        return None

    def get_current_step(self) -> Optional[BootstrapStep]:
        """Get the first step that is not done."""
        for s in self.steps:
            if s.status != "done":
                return s
        return None

    def get_state(self) -> dict:
        """Get the full bootstrap state for display."""
        return {
            "business_slug": self.business_slug,
            "format_name": self.format_module.get("name", "unknown"),
            "steps": [s.to_dict() for s in self.steps],
            "complete": all(s.status == "done" for s in self.steps),
        }

    # ── Candidate generation ───────────────────────────────────────────

    def generate_character_candidates(self, seed_descriptions: list[dict]) -> list[dict]:
        """Step 1: Propose character candidates to the registry.

        Each seed_description is a dict with the character_ref name and payload.
        This method PROPOSES them to the registry (status='proposed').
        The operator then approves through the gate.

        Args:
            seed_descriptions: list of dicts, each with:
                - name: character_ref name (e.g. 'protagonist')
                - payload: registry payload dict (face_canon, wardrobe_canon, etc.)

        Returns:
            list of proposed asset dicts (with 'id' and 'status'='proposed')
        """
        step = self.get_step(1)
        if not step:
            return []

        candidates = []
        for seed in seed_descriptions:
            name = seed["name"]
            payload = seed["payload"]
            # Propose to registry — status will be 'proposed'
            asset = self.ref_store.propose(
                self.business_slug, "character_ref", name, payload,
                notes="Bootstrap step 1: character candidate — pending operator gate approval",
            )
            candidates.append(asset)

        step.candidates = candidates
        step.status = "awaiting_approval"
        return candidates

    def generate_location_candidates(self, seed_descriptions: list[dict]) -> list[dict]:
        """Step 2: Propose location candidates, conditioned on the grade token.

        Locations are conditioned on the grade token (the grade string is
        included in the location prompt text). This method proposes locations
        to the registry; the operator approves each.

        Args:
            seed_descriptions: list of dicts, each with:
                - name: location_ref name
                - payload: registry payload dict (prompt_text, files, etc.)
                  The prompt_text should already include the grade token.

        Returns:
            list of proposed asset dicts
        """
        step = self.get_step(2)
        if not step:
            return []

        # Get the grade token to condition location prompts
        grade_string = self.ref_store.get_grade_token(self.business_slug)

        candidates = []
        for seed in seed_descriptions:
            name = seed["name"]
            payload = seed["payload"]
            # If grade token exists, ensure it's in the prompt_text
            if grade_string and "prompt_text" in payload:
                if grade_string.lower() not in payload["prompt_text"].lower():
                    payload["prompt_text"] = payload["prompt_text"] + ", " + grade_string

            asset = self.ref_store.propose(
                self.business_slug, "location_ref", name, payload,
                notes="Bootstrap step 2: location candidate (conditioned on grade token) — pending operator gate approval",
            )
            candidates.append(asset)

        step.candidates = candidates
        step.status = "awaiting_approval"
        return candidates

    def generate_music_bed_candidates(self, seed_descriptions: list[dict]) -> list[dict]:
        """Step 3: Propose music bed candidates — one per register.

        Music beds are generated once via the music generator, then proposed
        to the registry. The operator approves each.

        Args:
            seed_descriptions: list of dicts, each with:
                - name: music_bed name (convention: 'bed_{register}')
                - payload: registry payload dict (file, register, duration, source)

        Returns:
            list of proposed asset dicts
        """
        step = self.get_step(3)
        if not step:
            return []

        candidates = []
        for seed in seed_descriptions:
            name = seed["name"]
            payload = seed["payload"]
            asset = self.ref_store.propose(
                self.business_slug, "music_bed", name, payload,
                notes="Bootstrap step 3: music bed candidate — pending operator gate approval",
            )
            candidates.append(asset)

        step.candidates = candidates
        step.status = "awaiting_approval"
        return candidates

    def generate_card_style_candidates(self, seed_descriptions: list[dict]) -> list[dict]:
        """Step 4: Propose card style candidates derived from the visual-style module.

        Card styles are renderer parameters (font, palette from visual-style
        module tokens, position, animation). The operator approves each.

        Args:
            seed_descriptions: list of dicts, each with:
                - name: card_style name
                - payload: registry payload dict (font, palette, position, animation)

        Returns:
            list of proposed asset dicts
        """
        step = self.get_step(4)
        if not step:
            return []

        candidates = []
        for seed in seed_descriptions:
            name = seed["name"]
            payload = seed["payload"]
            asset = self.ref_store.propose(
                self.business_slug, "card_style", name, payload,
                notes="Bootstrap step 4: card style candidate — pending operator gate approval",
            )
            candidates.append(asset)

        step.candidates = candidates
        step.status = "awaiting_approval"
        return candidates

    # ── Approval ─────────────────────────────────────────────────────────

    def approve_candidate(self, step_number: int, asset_id: int, approved_by: str = "operator") -> dict:
        """Approve a candidate through the gate.

        This calls the ref_store's approve() method, which transitions the
        asset from 'proposed' to 'approved'. The operator must explicitly
        approve each candidate — no bulk approve.

        Args:
            step_number: which step (1-4)
            asset_id: the reference asset ID to approve
            approved_by: who approved (default 'operator')

        Returns:
            the approved asset dict

        Raises:
            ValueError if the step doesn't exist or the asset can't be approved
        """
        step = self.get_step(step_number)
        if not step:
            raise ValueError(f"Step {step_number} does not exist")

        # Approve through the registry gate
        approved = self.ref_store.approve(asset_id, approved_by=approved_by)
        step.approved_ids.append(asset_id)

        # Check if all candidates for this step are approved
        if len(step.approved_ids) >= len(step.candidates):
            step.status = "done"

        return approved

    def reject_candidate(self, step_number: int, asset_id: int) -> dict:
        """Reject a candidate — retires it from the proposed state.

        The operator may reject a candidate. This retires the proposed asset
        (it stays in the registry for provenance but is not usable).

        Args:
            step_number: which step (1-4)
            asset_id: the reference asset ID to reject

        Returns:
            the retired asset dict
        """
        step = self.get_step(step_number)
        if not step:
            raise ValueError(f"Step {step_number} does not exist")

        # To reject a proposed asset, we retire it (retire requires approved,
        # so we update its status to retired directly for proposed assets)
        asset = self.ref_store.get_asset(asset_id)
        if not asset:
            raise ValueError(f"Asset {asset_id} not found")

        if asset["status"] == "proposed":
            # Mark as retired directly (proposed assets can't use retire() which
            # requires approved status; we just set it to retired)
            self.ref_store.conn.execute(
                "UPDATE reference_assets SET status = 'retired' WHERE id = ?",
                (asset_id,),
            )
            self.ref_store.conn.commit()
        else:
            # If already approved, use the normal retire path
            self.ref_store.retire(asset_id)

        return self.ref_store.get_asset(asset_id)

    def is_step_complete(self, step_number: int) -> bool:
        """Check if a step is complete (all candidates approved)."""
        step = self.get_step(step_number)
        if not step:
            return False
        return step.status == "done"

    def is_complete(self) -> bool:
        """Check if the entire bootstrap is complete."""
        return all(s.status == "done" for s in self.steps)

    def needs_grade_token_first(self) -> bool:
        """Check if a grade token needs to be approved before step 2 (locations).

        Locations are conditioned on the grade token. If no approved grade
        token exists, the operator must approve one first.
        """
        grade = self.ref_store.get_grade_token(self.business_slug)
        return grade is None

    def propose_grade_token(self, grade_string: str, palette: dict = None, tagline: str = "") -> dict:
        """Propose a grade token for operator approval.

        The grade token must be approved before location generation (step 2)
        because locations are conditioned on it.

        Args:
            grade_string: the verbatim grade description string
            palette: optional color palette dict
            tagline: optional tagline

        Returns:
            the proposed asset dict
        """
        payload = {"grade_string": grade_string}
        if palette:
            payload["palette"] = palette
        if tagline:
            payload["tagline"] = tagline

        return self.ref_store.propose(
            self.business_slug, "grade_token", "default", payload,
            notes="Bootstrap: grade token — must be approved before location generation",
        )

    def approve_grade_token(self, asset_id: int, approved_by: str = "operator") -> dict:
        """Approve the grade token through the gate."""
        return self.ref_store.approve(asset_id, approved_by=approved_by)