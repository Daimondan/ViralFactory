#!/usr/bin/env python3
"""VF-INSP: Scheduled Inspiration collection worker.

Runs as a systemd timer. Reads config/inspiration.yaml, loads credentials
from environment, and executes one collection run per enabled provider.
No network calls during page render — this is the only process that calls
providers. The /inspiration page reads the DB this worker writes to.

Usage:
    python3 src/inspiration_collect_worker.py

Exit codes:
    0 — at least one provider collected
    1 — all providers failed
    2 — configuration error
"""
import json
import os
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import sqlite3


def main():
    repo_root = Path(__file__).parent.parent
    config_dir = repo_root / "config"
    db_path = os.environ.get("VIRALFACTORY_DB", str(repo_root / "data" / "viralfactory.db"))

    # Load business config for tenant slug
    business_path = config_dir / "business.yaml"
    if not business_path.exists():
        print("ERROR: business.yaml not found", file=sys.stderr)
        sys.exit(2)
    with open(business_path) as f:
        business_config = yaml.safe_load(f)
    business_slug = business_config["business"]["slug"]

    # Load inspiration config
    insp_path = config_dir / "inspiration.yaml"
    if not insp_path.exists():
        print("ERROR: inspiration.yaml not found", file=sys.stderr)
        sys.exit(2)
    with open(insp_path) as f:
        insp_config = yaml.safe_load(f)

    from inspiration_store import InspirationStore, run_collection

    store = InspirationStore(db_path)
    ok_count = 0
    fail_count = 0

    for provider in insp_config.get("providers", []):
        if not provider.get("enabled", False):
            continue

        # Expand chart providers into individual chart configs
        if "charts" in provider:
            chart_configs = []
            for chart in provider["charts"]:
                pconf = dict(provider)
                pconf.pop("charts")
                pconf["path"] = chart["path"]
                pconf["chart_key"] = chart["key"]
                pconf["chart_label"] = chart["label"]
                pconf["scene"] = chart.get("scene", 0)
                chart_configs.append(pconf)
        else:
            chart_configs = [provider]

        for pconf in chart_configs:
            name = pconf["name"]
            chart_label = pconf.get("chart_label", "")
            label = f"{name}/{chart_label}" if chart_label else name

            # Check credentials
            api_key_env = pconf.get("api_key_env", "")
            if api_key_env and not os.environ.get(api_key_env):
                print(f"SKIP {label}: credential {api_key_env} not set")
                fail_count += 1
                continue

            try:
                run = run_collection(
                    business_slug=business_slug,
                    provider_config=pconf,
                    redaction_config=insp_config["redaction"],
                    store=store,
                    platform_urls=insp_config.get("platform_urls"),
                )
                status = run["status"]
                count = run.get("result_count", 0)
                print(f"{label}: {status} ({count} items)")
                if status in ("ok", "empty"):
                    ok_count += 1
                else:
                    fail_count += 1
            except Exception as exc:
                print(f"ERROR {label}: {type(exc).__name__}: {exc}", file=sys.stderr)
                fail_count += 1

    print(f"\nSummary: {ok_count} ok, {fail_count} failed")
    sys.exit(0 if ok_count > 0 else 1)


if __name__ == "__main__":
    main()