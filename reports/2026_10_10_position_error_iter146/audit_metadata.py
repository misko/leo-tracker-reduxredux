"""Reproduce identity-only exposure scan; never emit localization values.

Run against a new output path; published exposure receipts are never overwritten.
The bounded size/suffix scope is deliberately incomplete and cannot certify unseen data.
"""

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOTS = (
    Path("/home/mouse9911/gits/leo-hard60-default/reports"),
    Path("/home/mouse9911/gits/leo-tracker-reduxredux/reports"),
)
RG = (
    "/home/mouse9911/.codex/packages/standalone/releases/"
    "0.161.0-x86_64-unknown-linux-musl/codex-path/rg"
)


def scan():
    began = time.monotonic()
    manifest = json.loads((HERE / "local/manifest.json").read_text())
    patterns = {}
    for capture in manifest["captures"]:
        for field in ("session_id", "uncompressed_sha256", "recording_manifest_sha256"):
            patterns[capture[field].encode()] = capture["session_id"]
    matches, skipped, errors, eligible = [], [], [], []
    for root in ROOTS:
        result = subprocess.run(
            [RG, "--files", "--hidden", "--no-ignore", str(root)], capture_output=True, text=True
        )
        if result.stderr:
            errors.append(dict(root=str(root), error=result.stderr))
        for name in result.stdout.splitlines():
            path = Path(name)
            if HERE.resolve() in path.resolve().parents:
                continue
            try:
                if path.stat().st_size > 64 * 1024**2:
                    skipped.append(
                        dict(
                            path=name,
                            reason="Explicit metadata scan size ceiling64MiB",
                            bytes=path.stat().st_size,
                        )
                    )
                    continue
                if path.suffix not in (".json", ".jsonl", ".md", ".txt", ".py", ".csv"):
                    continue
                eligible.append(name)
            except OSError as exc:
                errors.append(dict(path=name, error=repr(exc)))
    with tempfile.NamedTemporaryFile() as pattern_file:
        pattern_file.write(b"\n".join(patterns) + b"\n")
        pattern_file.flush()
        matched = set()
        for start in range(0, len(eligible), 500):
            result = subprocess.run(
                [
                    RG,
                    "-F",
                    "-l",
                    "--text",
                    "--no-ignore",
                    "-f",
                    pattern_file.name,
                    "--",
                    *eligible[start : start + 500],
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode not in (0, 1):
                errors.append(
                    dict(batch_start=start, error=result.stderr, exit_code=result.returncode)
                )
            elif result.stderr:
                errors.append(dict(batch_start=start, error=result.stderr))
            matched.update(result.stdout.splitlines())
        for name in sorted(matched):
            try:
                data = Path(name).read_bytes()
                found = sorted({sid for token, sid in patterns.items() if token in data})
                matches.append(
                    dict(
                        path=name,
                        sessions=found,
                        classification="Identity match only; outcome consumption "
                        "requires provenance review",
                    )
                )
            except OSError as exc:
                errors.append(dict(path=name, error=repr(exc)))
    return dict(
        roots=list(map(str, ROOTS)),
        files_scanned=len(eligible),
        elapsed_s=time.monotonic() - began,
        matches=matches,
        skipped_large_files=skipped,
        access_errors=errors,
        policy="Session, recording-manifest and IQ-digest tokens; no localization values emitted; "
        "no-match is not unseen proof; all22 outcomes remain closed",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = scan()
    with args.output.open("x") as stream:
        json.dump(receipt, stream, indent=2)
