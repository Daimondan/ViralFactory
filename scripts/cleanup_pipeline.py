#!/usr/bin/env python3
"""
One-time cleanup: wipe all pipeline run data so new videos can be generated fresh.
Preserves infrastructure: sources, provenance, caches, materials.
No backup — just delete (per operator directive).
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "viralfactory.db"

def main():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # Tables to wipe — pipeline data only, in FK-safe order (children first)
    wipe_order = [
        "asset_media",      # FK -> assets
        "edit_plans",       # FK -> assets, drafts
        "assets",           # FK -> drafts
        "drafts",           # FK -> idea_cards
        "idea_cards",       # root entity
        "jobs",             # standalone (no FK)
        "feedback_log",
        "publish_log",
        "post_metrics",
        "playbook_runs",
    ]

    print(f"Database: {DB_PATH}")
    print(f"Size before: {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")

    for table in wipe_order:
        c.execute(f"SELECT count(*) FROM {table}")
        count = c.fetchone()[0]
        if count > 0:
            c.execute(f"DELETE FROM {table} WHERE id >= 0")
            print(f"  Deleted {count} rows from {table}")
        else:
            print(f"  {table}: already empty")
        # Reset autoincrement
        c.execute(f"DELETE FROM sqlite_sequence WHERE name = ?", (table,))

    conn.commit()

    # Verify
    print("\n--- VERIFICATION (all should be 0) ---")
    for table in wipe_order:
        c.execute(f"SELECT count(*) FROM {table}")
        print(f"  {table}: {c.fetchone()[0]} rows")

    # Confirm preserved tables
    print("\n--- PRESERVED (infrastructure) ---")
    preserved = ["sources", "provenance", "llm_cache", "materials",
                 "stock_cache", "image_cache", "source_research",
                 "source_snapshot", "material_edits", "asset_reviews"]
    for table in preserved:
        c.execute(f"SELECT count(*) FROM {table}")
        print(f"  {table}: {c.fetchone()[0]} rows")

    conn.close()
    print(f"\nSize after: {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")
    print("Done. Pipeline wiped, infrastructure preserved.")


if __name__ == "__main__":
    main()