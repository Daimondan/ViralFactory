#!/usr/bin/env python3
"""
ViralFactory — Nightly Metrics Pull Cron (T4.2)

Pulls post analytics from Buffer for all published pieces.
Designed to run via cron nightly. Stores metrics in post_metrics table.

Usage:
    python3 cron_pull_metrics.py [--days 7] [--business slug]

Exit codes:
    0 — success (even if some pulls failed; failures are logged)
    1 — configuration error (Buffer not configured)
"""

import sys
import os
import logging

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from config_loader import load_all, ConfigError
from buffer_adapter import BufferAdapter, BufferError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s",
)
logger = logging.getLogger("viralfactory.cron.metrics")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Pull Buffer metrics for all published pieces")
    parser.add_argument("--days", type=int, default=7, help="Days to look back (default 7)")
    parser.add_argument("--business", type=str, default=None, help="Business slug (auto-detected if omitted)")
    parser.add_argument("--config-dir", type=str, default="config", help="Config directory")
    parser.add_argument("--db-path", type=str, default="data/viralfactory.db", help="Database path")
    args = parser.parse_args()

    # Load config
    try:
        config = load_all(args.config_dir)
        models_config = config["models"]
    except ConfigError as e:
        logger.error(f"Config error: {e}")
        sys.exit(1)

    # Auto-detect business slug
    business_slug = args.business
    if not business_slug:
        try:
            business_slug = config["business"]["business"]["slug"]
        except (KeyError, ConfigError):
            logger.error("Could not determine business slug from config")
            sys.exit(1)

    # Create adapter
    buffer = BufferAdapter(models_config, db_path=args.db_path)

    if not buffer.is_available():
        logger.warning("Buffer not available — skipping metrics pull")
        sys.exit(0)

    # Pull metrics
    logger.info(f"Pulling metrics for business '{business_slug}', days={args.days}")
    try:
        result = buffer.pull_all_metrics(business_slug, days=args.days)
        logger.info(f"Metrics pull complete: {result['pulled']} succeeded, {result['failed']} failed, {result['total']} total")
    except BufferError as e:
        logger.error(f"Metrics pull failed: {e}")
        sys.exit(0)  # Don't fail the cron — retry next night

    sys.exit(0)


if __name__ == "__main__":
    main()