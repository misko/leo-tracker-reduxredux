#!/usr/bin/env python3
"""Shared bounded preparation controller for the final Wave 9 chronological group."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


def write_exclusive(path: Path, value) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def last_validated_path(output: Path, first_ordinal: int, validated: list[str]) -> Path | None:
    if not validated:
        return None
    return output / f"inputs-through-single-{first_ordinal + len(validated) - 1:03d}-ready-v1.json"


def validate_progressive(
    start: dict, frozen: dict, added: list[str], expected_start_ready: int
) -> None:
    if len(frozen["captures"]) != 88:
        raise ValueError("progressive input lost DS7 identities")
    old = {row["session_id"]: row for row in start["captures"] if row["state"] == "ready"}
    new = {row["session_id"]: row for row in frozen["captures"]}
    if len(old) != expected_start_ready or any(
        new[session] != row for session, row in old.items()
    ):
        raise ValueError("predecessor ready rows changed")
    ready_ids = {row["session_id"] for row in frozen["captures"] if row["state"] == "ready"}
    if ready_ids != set(old) | set(added):
        raise ValueError("progressive ready identity set mismatch")
    for session in added:
        row = new[session]
        if len(row["artifacts"]) != 3:
            raise ValueError("new capture does not have three frozen artifacts")
        for artifact in row["artifacts"]:
            if digest(Path(artifact["path"])) != artifact["sha256"]:
                raise ValueError("new frozen artifact changed")


def main(sessions: list[str], group_name: str) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--start-index", type=Path, required=True)
    parser.add_argument("--start-frozen", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bank-root", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--first-ordinal", type=int, required=True)
    parser.add_argument("--expected-start-ready", type=int, default=80)
    args = parser.parse_args()

    started = time.monotonic()
    deadline = started + 1180.0
    args.output.mkdir(parents=True, exist_ok=True)
    args.bank_root.mkdir(parents=True, exist_ok=True)
    status_path = args.output / "controller-status.log"
    start_frozen = json.loads(args.start_frozen.read_text())
    index = json.loads(args.start_index.read_text())
    by_id = {row["session_id"]: row for row in index["captures"]}
    prepared: list[str] = []
    validated: list[str] = []
    reports = []
    terminal_state = "complete"

    for ordinal, session in enumerate(sessions, args.first_ordinal):
        remaining = deadline - time.monotonic()
        if remaining <= 5.0:
            terminal_state = "whole_worker_deadline"
            break
        tracks = args.output / f"{session}-tracks.json"
        banks = args.bank_root / session
        receipt = args.output / f"{session}-receipt.json"
        command = [
            str(args.python),
            str(args.repo / "tools/ds7_combined_export.py"),
            "--plan",
            str(args.plan),
            "--session",
            session,
            "--tracks-output",
            str(tracks),
            "--banks-output",
            str(banks),
            "--receipt",
            str(receipt),
        ]
        capture_started = time.monotonic()
        timeout = min(240.0, max(1.0, remaining - 5.0))
        try:
            completed = subprocess.run(
                command,
                cwd=args.repo,
                check=False,
                timeout=timeout,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            state = "ok" if completed.returncode == 0 else f"exit_{completed.returncode}"
            output_tail = completed.stdout[-4000:]
        except subprocess.TimeoutExpired as exc:
            state = "timeout"
            output_tail = str(exc.stdout or "")[-4000:]
        elapsed = time.monotonic() - capture_started
        with status_path.open("a") as stream:
            stream.write(f"{ordinal} {session} {state} {elapsed:.6f}\n{output_tail}\n")
        reports.append(
            {"ordinal": ordinal, "session_id": session, "state": state, "seconds": elapsed}
        )
        if state != "ok":
            terminal_state = state
            break

        manifest = banks / "manifest.json"
        bank = banks / "banks.npz"
        shortlist = banks / "shortlists.json"
        for path in (tracks, receipt, manifest, bank, shortlist):
            if not path.is_file():
                raise ValueError(f"missing generated artifact: {path}")
        row = by_id[session]
        row["state"] = "ready"
        row["reason"] = None
        row["artifacts"] = [
            {"kind": "observations", "path": str(tracks)},
            {"kind": "candidates", "path": str(manifest)},
            {"kind": "candidates", "path": str(bank)},
        ]
        prepared.append(session)
        index_path = args.output / f"inputs-through-single-{ordinal:03d}-index.json"
        frozen_path = args.output / f"inputs-through-single-{ordinal:03d}-ready-v1.json"
        write_exclusive(index_path, index)
        try:
            freeze = subprocess.run(
                [
                    str(args.python),
                    str(args.repo / "tools/ds7_eval.py"),
                    "freeze-inputs",
                    "--plan",
                    str(args.plan),
                    "--index",
                    str(index_path),
                    "--output",
                    str(frozen_path),
                ],
                cwd=args.repo,
                check=False,
                timeout=min(60.0, max(1.0, deadline - time.monotonic())),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except subprocess.TimeoutExpired as exc:
            with status_path.open("a") as stream:
                stream.write(f"freeze_timeout {ordinal} {str(exc.stdout or '')[-4000:]}\n")
            terminal_state = "freeze_timeout"
            break
        if freeze.returncode != 0:
            with status_path.open("a") as stream:
                stream.write(f"freeze_failure {ordinal} {freeze.stdout[-4000:]}\n")
            terminal_state = "freeze_failure"
            break
        try:
            validate_progressive(
                start_frozen,
                json.loads(frozen_path.read_text()),
                [*validated, session],
                args.expected_start_ready,
            )
        except (KeyError, OSError, TypeError, ValueError) as exc:
            with status_path.open("a") as stream:
                stream.write(f"validation_failure {ordinal} {exc}\n")
            terminal_state = "validation_failure"
            break
        validated.append(session)

    final_path = last_validated_path(args.output, args.first_ordinal, validated)
    terminal = {
        "schema": "ds7-wave9-controller-terminal/v1",
        "group": group_name,
        "state": terminal_state,
        "whole_worker_cap_seconds": 1200,
        "internal_deadline_seconds": 1180,
        "per_capture_cap_seconds": 240,
        "controller_wall_seconds": time.monotonic() - started,
        "sessions_declared": sessions,
        "sessions_prepared": prepared,
        "sessions_added": validated,
        "reports": reports,
        "start_index_sha256": digest(args.start_index),
        "start_frozen_sha256": digest(args.start_frozen),
        "final_frozen": str(final_path) if final_path else None,
        "final_frozen_sha256": digest(final_path) if final_path else None,
    }
    write_exclusive(args.output / "controller-terminal-receipt.json", terminal)
    if terminal_state != "complete" or len(validated) != len(sessions):
        raise SystemExit(1)
