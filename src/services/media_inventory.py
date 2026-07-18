"""
Scoped render-ready inventory service (VF-AU-202).

Produces one scoped render-ready inventory contract per asset.
- Asset-scoped: only media for this specific asset_id
- Privacy-isolated: session uploads never leak into public assembly
- Tenant-isolated: only this business's media
- Excludes: unrelated global uploads, session voice samples, remote-only URLs,
  submitted jobs, missing files, unapproved references

The inventory is the single source of truth for what the edit planner and
renderer can use. If an ingredient is not in this inventory, it doesn't exist
for assembly purposes.
"""

import os
import sqlite3
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InventoryItem:
    """A single render-ready (or not-ready) ingredient in the inventory."""
    ingredient_id: str          # e.g. "asset_media:5", "capture_upload:10", "reference_asset:3"
    kind: str                    # image | video | voice | music | sfx | text_card
    source_type: str             # asset_media | capture_upload | reference_asset | stock_cache
    path: str                    # local file path (or remote URL if not yet downloaded)
    is_render_ready: bool        # True if local file exists and is probeable
    status: str = "ready"        # ready | missing | remote_only | unapproved | excluded
    duration_sec: Optional[float] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Inventory:
    """The complete scoped inventory for one asset."""
    asset_id: int
    business_slug: str
    items: list[InventoryItem] = field(default_factory=list)

    @property
    def summary(self) -> dict:
        ready = sum(1 for i in self.items if i.is_render_ready)
        by_kind = {}
        for item in self.items:
            by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
        return {
            "total_items": len(self.items),
            "render_ready": ready,
            "by_kind": by_kind,
        }

    @property
    def render_ready_items(self) -> list[InventoryItem]:
        return [i for i in self.items if i.is_render_ready]


class MediaInventoryService:
    """Builds a scoped, privacy-isolated, tenant-isolated render-ready inventory."""

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path

    def build_inventory(
        self,
        asset_id: int,
        business_slug: str,
        capture_upload_ids: list[int] | None = None,
    ) -> Inventory:
        """Build the scoped inventory for one asset.

        Args:
            asset_id: the asset to scope to
            business_slug: tenant isolation
            capture_upload_ids: specific material IDs linked to this card's captures
                               (only these are included; all other materials excluded)
        """
        capture_upload_ids = capture_upload_ids or []
        inv = Inventory(asset_id=asset_id, business_slug=business_slug)

        # 1. Asset-scoped generated media (images, videos)
        self._add_asset_media(inv, asset_id)

        # 2. Linked capture uploads (only the specific IDs linked to this card)
        self._add_capture_uploads(inv, business_slug, capture_upload_ids)

        # 3. Approved reference assets (character/location/grade/music)
        self._add_reference_assets(inv, business_slug)

        return inv

    def _add_asset_media(self, inv: Inventory, asset_id: int) -> None:
        """Add asset-scoped generated media, excluding draft visuals."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'asset_media'"
        ).fetchone()
        if not table_exists:
            conn.close()
            return
        rows = conn.execute(
            """SELECT * FROM asset_media
               WHERE asset_id = ? AND (owner_type = 'asset' OR owner_type IS NULL)
               ORDER BY id ASC""",
            (asset_id,),
        ).fetchall()
        conn.close()

        for row in rows:
            row_dict = dict(row)
            path = row_dict.get("path", "") or ""
            kind = row_dict.get("kind", "image") or "image"
            item_id = f"asset_media:{row_dict['id']}"

            # Check if path is a remote URL (not a local file)
            is_remote = path.startswith("http://") or path.startswith("https://")
            file_exists = not is_remote and os.path.exists(path) if path else False

            if is_remote:
                status = "remote_only"
                ready = False
            elif not file_exists:
                status = "missing"
                ready = False
            else:
                status = "ready"
                ready = True

            inv.items.append(InventoryItem(
                ingredient_id=item_id,
                kind=kind,
                source_type="asset_media",
                path=path,
                is_render_ready=ready,
                status=status,
                metadata={"provider": row_dict.get("provider"), "prompt": row_dict.get("prompt", "")},
            ))

    def _add_capture_uploads(self, inv: Inventory, business_slug: str,
                             capture_upload_ids: list[int]) -> None:
        """Add only the specific linked capture uploads — never session uploads."""
        if not capture_upload_ids:
            return

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(capture_upload_ids))
        rows = conn.execute(
            f"""SELECT * FROM materials
               WHERE id IN ({placeholders}) AND business_slug = ?
               AND channel != 'session_upload'""",
            (*capture_upload_ids, business_slug),
        ).fetchall()
        conn.close()

        for row in rows:
            row_dict = dict(row)
            path = row_dict.get("file_path", "") or ""
            file_exists = os.path.exists(path) if path else False
            filename = str(row_dict.get("filename") or "").lower()
            kind = row_dict.get("material_type", "image") or "image"
            if filename.endswith((".mp4", ".mov", ".avi", ".webm")):
                kind = "video"

            inv.items.append(InventoryItem(
                ingredient_id=f"capture_upload:{row_dict['id']}",
                kind=kind,
                source_type="capture_upload",
                path=path,
                is_render_ready=file_exists,
                status="ready" if file_exists else "missing",
                metadata={
                    "channel": row_dict.get("channel", ""),
                    "filename": row_dict.get("filename", ""),
                },
            ))

    def _add_reference_assets(self, inv: Inventory, business_slug: str) -> None:
        """Add approved reference assets only — exclude pending/retired."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Check if reference_assets table exists
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        if "reference_assets" not in tables:
            conn.close()
            return

        rows = conn.execute(
            """SELECT * FROM reference_assets
               WHERE business_slug = ? AND status = 'approved'
               ORDER BY id ASC""",
            (business_slug,),
        ).fetchall()
        conn.close()

        for row in rows:
            row_dict = dict(row)
            path = row_dict.get("file_path", "") or ""
            file_exists = os.path.exists(path) if path else False

            inv.items.append(InventoryItem(
                ingredient_id=f"reference_asset:{row_dict['id']}",
                kind=row_dict.get("asset_type", "reference") or "reference",
                source_type="reference_asset",
                path=path,
                is_render_ready=file_exists,
                status="ready" if file_exists else "missing",
                metadata={"status": row_dict.get("status", "")},
            ))