"""Restartable NVMe-to-RAID publisher for sealed adaptive captures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from leo.storage.adaptive_hop import AdaptiveHopIqStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--spool-root", type=Path, required=True)
    arguments = parser.parse_args()
    store = AdaptiveHopIqStore(
        arguments.bulk_root,
        spool_root=arguments.spool_root,
        defer_spool_transfer=True,
    )
    try:
        recovered = store.recover_spooled_sessions()
    finally:
        store.close()
    print(json.dumps({"published_session_ids": recovered}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
