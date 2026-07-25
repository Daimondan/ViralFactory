#!/usr/bin/env python3
"""Route parity tool — snapshot and check the Flask URL table.

Captures every URL rule and its methods from a live ``create_app()`` and
diffs against a baseline JSON file. Used by the blueprint-split refactor
(CORRECTION-app-blueprint-split-v1.0) to enforce that moving routes into
domain blueprints does not alter the route table.

Usage::

    # Capture the baseline from the current tree
    PYTHONPATH=src python3 scripts/route_parity.py --write docs/reviews/route-baseline.json

    # Check the current tree against a stored baseline
    PYTHONPATH=src python3 scripts/route_parity.py --check docs/reviews/route-baseline.json

The snapshot is a JSON object mapping ``rule`` -> sorted list of methods
(excluding HEAD and OPTIONS, which Flask adds implicitly). ``/static/<path:filename>``
is included so the count matches ``app.url_map.iter_rules()`` exactly.

Exit codes:
    0 — parity holds (or baseline written successfully)
    1 — parity violation (missing, added, or method-changed rules)
    2 — operational error (import failure, file I/O)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Tuple


def _capture_routes(pythonpath_src: bool = True) -> Dict[str, List[str]]:
    """Boot ``create_app()`` and return ``{rule: sorted_methods}``.

    Assumes ``PYTHONPATH=src`` is set in the environment or that ``src`` is
    otherwise importable. We import lazily so the script's own module-level
    imports never trigger the Flask app import.
    """
    if pythonpath_src and "src" not in sys.path:
        # Make ``src`` importable when run as a standalone script.
        src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "src")
        sys.path.insert(0, os.path.abspath(src_dir))

    import app as app_module  # noqa: E402 — intentional lazy import

    flask_app = app_module.create_app()

    snapshot: Dict[str, List[str]] = {}
    for rule in flask_app.url_map.iter_rules():
        methods = sorted(rule.methods - {"HEAD", "OPTIONS"})
        snapshot[rule.rule] = methods

    return dict(sorted(snapshot.items()))


def _write_baseline(path: str) -> Dict[str, List[str]]:
    """Capture routes and write them to ``path`` as JSON."""
    snapshot = _capture_routes()
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return snapshot


def _check_baseline(path: str) -> Tuple[int, Dict[str, List[str]]]:
    """Compare the live route table against the baseline at ``path``.

    Returns ``(exit_code, live_snapshot)``. Prints a human-readable diff.
    """
    if not os.path.exists(path):
        print(f"ERROR: baseline file not found: {path}", file=sys.stderr)
        return 2, {}

    with open(path, "r", encoding="utf-8") as fh:
        baseline = json.load(fh)

    live = _capture_routes()

    baseline_keys = set(baseline)
    live_keys = set(live)

    missing = sorted(baseline_keys - live_keys)
    added = sorted(live_keys - baseline_keys)
    method_changed: List[Tuple[str, List[str], List[str]]] = []
    for key in sorted(baseline_keys & live_keys):
        if baseline[key] != live[key]:
            method_changed.append((key, baseline[key], live[key]))

    if not missing and not added and not method_changed:
        print(f"Route parity OK — {len(live)} rules match baseline ({path}).")
        return 0, live

    print("Route parity VIOLATION:", file=sys.stderr)
    if missing:
        print(f"  Missing ({len(missing)}):", file=sys.stderr)
        for rule in missing:
            print(f"    - {rule}  methods={baseline[rule]}", file=sys.stderr)
    if added:
        print(f"  Added ({len(added)}):", file=sys.stderr)
        for rule in added:
            print(f"    + {rule}  methods={live[rule]}", file=sys.stderr)
    if method_changed:
        print(f"  Method-changed ({len(method_changed)}):", file=sys.stderr)
        for rule, base_methods, live_methods in method_changed:
            print(f"    ~ {rule}  {base_methods} -> {live_methods}", file=sys.stderr)

    return 1, live


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Snapshot or check Flask route parity against a baseline.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--write",
        metavar="PATH",
        help="Capture the current route table and write it to PATH.",
    )
    group.add_argument(
        "--check",
        metavar="PATH",
        help="Compare the current route table against the baseline at PATH.",
    )
    args = parser.parse_args(argv)

    if args.write:
        snapshot = _write_baseline(args.write)
        print(f"Wrote {len(snapshot)} rules to {args.write}")
        return 0

    if args.check:
        exit_code, _ = _check_baseline(args.check)
        return exit_code

    return 2  # unreachable — argparse enforces one of the group


if __name__ == "__main__":
    sys.exit(main())