"""Advance both scanner publication paths without one failure starving the other."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from leo.cli.adaptive_hop_analysis import pending_sessions
from leo.sky.sites import preset_names
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore


def _pending_adaptive_sessions(bulk_root: Path, *, limit: int) -> tuple[str, ...]:
    captures = AdaptiveHopIqStore(bulk_root, read_only=True)
    try:
        return pending_sessions(
            captures,
            AdaptiveHopAnalysisPresentationStore(bulk_root),
            probe_stride_ms=120,
            limit=limit,
        )
    finally:
        captures.close()


def _run(command: list[str]) -> dict[str, object] | None:
    try:
        result = subprocess.run(command, check=False)
        if result.returncode:
            return {"job": command[2], "returncode": result.returncode}
    except OSError as error:
        return {"job": command[2], "error_type": type(error).__name__}
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bulk-root", type=Path, default=Path(os.environ.get("LEO_BULK_ROOT", "/srv/bulk/leo"))
    )
    parser.add_argument("--site", choices=preset_names(), required=True)
    parser.add_argument("--fixed-maximum-workers", type=int, choices=(1, 2, 3, 4), default=2)
    parser.add_argument("--adaptive-sessions", type=int, choices=(1, 2), default=2)
    arguments = parser.parse_args()
    adaptive_commands = [
        [
            sys.executable,
            "-m",
            "leo.cli.adaptive_hop_analysis",
            "--bulk-root",
            str(arguments.bulk_root),
            "--maximum-workers",
            "2",
            "--probe-stride-ms",
            "120",
            "--session-id",
            session_id,
            "--maximum-visits",
            "2500",
            "--maximum-seconds",
            "580",
        ]
        for session_id in _pending_adaptive_sessions(
            arguments.bulk_root, limit=arguments.adaptive_sessions
        )
    ]
    failures = []
    with ThreadPoolExecutor(max_workers=arguments.adaptive_sessions) as executor:
        for failure in executor.map(_run, adaptive_commands):
            if failure is not None:
                failures.append(failure)

    # Shared fixed-analysis and catalogue publication remain serialized.
    jobs = (
        (
            "fixed",
            "leo.cli.persistent_hop_analysis",
            "--maximum-sessions",
            "1",
            "--site",
            arguments.site,
            "--maximum-tracking-groups",
            "4",
            "--json",
        ),
        ("refinement", "leo.cli.scanner_refinement", "--maximum-seconds", "180"),
        (
            "tracking",
            "leo.cli.scanner_tracking",
            "--site",
            arguments.site,
            "--maximum-seconds",
            "180",
            "--maximum-sessions",
            "2",
        ),
    )
    for name, module, *options in jobs:
        command = [
            sys.executable,
            "-m",
            module,
            "--bulk-root",
            str(arguments.bulk_root),
            *(
                []
                if name in ("refinement", "tracking")
                else [
                    "--maximum-workers",
                    str(arguments.fixed_maximum_workers),
                    "--probe-stride-ms",
                    "120",
                ]
            ),
            *options,
        ]
        failure = _run(command)
        if failure is not None:
            failure["job"] = name
            failures.append(failure)
    if failures:
        print(json.dumps({"state": "failed", "jobs": failures}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
