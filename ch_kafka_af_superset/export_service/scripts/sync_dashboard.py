#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.sync import sync_dashboard  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate draft export manifest from Superset dashboard charts",
    )
    parser.add_argument("--dashboard-id", type=int, required=True)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output YAML path (default: manifests/dashboard_<id>.yaml)",
    )
    args = parser.parse_args()
    out = args.out or (ROOT / "manifests" / f"dashboard_{args.dashboard_id}.yaml")
    manifest = sync_dashboard(args.dashboard_id, out_path=out)
    print(f"wrote {out}")
    print(f"id={manifest['id']} table={manifest['source']['table']} exports={len(manifest['exports'])}")


if __name__ == "__main__":
    main()
