"""Advance both scanner publication paths without one failure starving the other."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from leo.sky.sites import preset_names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bulk-root", type=Path, default=Path(os.environ.get("LEO_BULK_ROOT", "/srv/bulk/leo"))
    )
    parser.add_argument("--site", choices=preset_names(), required=True)
    arguments = parser.parse_args()
    # These are the existing public CLIs, each taking the shared nonblocking
    # analysis lease. No extra queue, scientific policy, or storage coupling.
    jobs = (
        (
            "adaptive",
            "leo.cli.adaptive_hop_analysis",
            "--pending",
            "--maximum-visits",
            "2500",
            "--maximum-seconds",
            "300",
        ),
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
    )
    failures = []
    for name, module, *options in jobs:
        command = [
            sys.executable,
            "-m",
            module,
            "--bulk-root",
            str(arguments.bulk_root),
            "--maximum-workers",
            "2",
            "--probe-stride-ms",
            "120",
            *options,
        ]
        try:
            result = subprocess.run(command, check=False)
            if result.returncode:
                failures.append({"job": name, "returncode": result.returncode})
        except OSError as error:
            failures.append({"job": name, "error_type": type(error).__name__})
    if failures:
        print(json.dumps({"state": "failed", "jobs": failures}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
