#!/usr/bin/env python3
"""Standalone VO generation script — runs Chatterbox TTS in a subprocess
to avoid loading the model into the gunicorn worker's memory.

Usage:
    python3 src/vo_subprocess.py --asset-id <N> --db-path <path> --config-dir <dir> --business-slug <slug>

Outputs JSON to stdout:
    {"status": "ok", "segments": [...], "total_duration": N, "take_id": "..."}
    or
    {"status": "error", "error": "..."}
"""

import argparse
import json
import os
import sys
import traceback


def main():
    parser = argparse.ArgumentParser(description="Generate VO in a subprocess")
    parser.add_argument("--asset-id", type=int, required=True)
    parser.add_argument("--db-path", default="data/viralfactory.db")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--business-slug", default=None)
    args = parser.parse_args()

    try:
        from config_loader import load_all, ConfigError
        from vo_generator import VOGenerator, VOGenerationError
        from pipeline import PipelineStore

        config = load_all(args.config_dir)
        models_config = config["models"]

        business_slug = args.business_slug or config["business"]["business"]["slug"]

        store = PipelineStore(db_path=args.db_path)
        asset = store.get_asset(args.asset_id)
        if not asset:
            print(json.dumps({"status": "error", "error": "Asset not found"}))
            sys.exit(1)

        posts = json.loads(asset.get("posts") or "[]")
        if not posts:
            print(json.dumps({"status": "error", "error": "No posts found on asset"}))
            sys.exit(1)

        vo_gen = VOGenerator(models_config, db_path=args.db_path)
        result = vo_gen.generate_vo_per_frame(
            asset_id=args.asset_id,
            posts=posts,
            business_slug=business_slug,
        )
        store.save_vo_segments(args.asset_id, json.dumps(result["segments"]))

        print(json.dumps({
            "status": "ok",
            "segments_generated": len(result["segments"]),
            "total_duration": round(result["total_duration"], 2),
            "take_id": result["take_id"],
        }))
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"status": "error", "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()