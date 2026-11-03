"""Preserve terminal DS23 result bytes on bulk storage using atomic symlinks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

RUN = Path(__file__).resolve().parents[1] / "reports/2026_10_20_ds23_combined_recovery_full"
BULK = Path("/srv/bulk/leo/research/ds23-combined-recovery-20261020-full")
QNAP = Path("/mnt/qnap01")
TERMINAL = {"complete", "budget_exhausted", "failed", "interrupted", "interrupted_before_checkpoint"}


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def archive_result(source, bulk=BULK):
    """Copy and verify before atomically replacing this one terminal result."""
    source, bulk = Path(source).absolute(), Path(bulk).resolve()
    if source.name != "result.json" or not re.fullmatch(r"DS23-\d{4}", source.parent.name):
        raise ValueError("only a DS23 result.json may be archived")
    if any(path.is_relative_to(QNAP) for path in (source.resolve(), bulk)):
        raise ValueError("QNAP paths are read-only")
    destination = bulk / source.parent.name / "result.json"
    if destination.resolve().is_relative_to(QNAP):
        raise ValueError("QNAP paths are read-only")
    if not destination.parent.resolve().is_relative_to(bulk):
        raise ValueError("archive directory escapes the selected bulk root")
    if source.is_symlink():
        if source.resolve() != destination:
            raise ValueError("result already links to an unexpected archive")
        return dict(source=str(source), destination=str(destination), sha256=digest(source), cached=True)
    status = json.loads(source.read_text())["status"]
    if status not in TERMINAL:
        raise ValueError("active result cannot be archived")
    expected, size = digest(source), source.stat().st_size
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        if destination.exists():
            if digest(destination) != expected:
                raise ValueError("archive destination has different scientific bytes")
        else:
            fd, name = tempfile.mkstemp(prefix=".result-copy-", dir=destination.parent)
            temporary = Path(name)
            with os.fdopen(fd, "wb") as output, source.open("rb") as stream:
                shutil.copyfileobj(stream, output)
                output.flush()
                os.fsync(output.fileno())
            if digest(temporary) != expected or digest(source) != expected:
                raise ValueError("scientific result changed during archival")
            try:
                os.link(temporary, destination)
            except FileExistsError:
                if digest(destination) != expected:
                    raise ValueError("concurrent archive destination differs") from None
        if digest(destination) != expected or digest(source) != expected:
            raise ValueError("scientific result changed before atomic replacement")
        # Readers see either the original file or the complete verified copy.
        link = source.with_name(".result-archive-link-" + uuid.uuid4().hex)
        created = False
        try:
            link.symlink_to(destination)
            created = True
            os.replace(link, source)
        finally:
            if created:
                link.unlink(missing_ok=True)
        if digest(source) != expected:
            raise ValueError("archived result digest changed")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return dict(source=str(source), destination=str(destination), sha256=expected,
                bytes=size, status=status, cached=False)


def terminal_paths(run):
    """Use completion receipts; a newly appearing result may still be writing."""
    run = Path(run)
    plan_path, progress_path = run / "durable_recovery_plan.json", run / "progress.json"
    plan = json.loads(plan_path.read_text()) if plan_path.exists() else {}
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
    committed = set(plan.get("original_terminal_cases", [])) | set(plan.get("interrupted_cases", []))
    committed.update(r["case"] for r in progress.get("receipts", []) if r.get("status") in TERMINAL)
    return [p for p in run.glob("DS23-*/result.json")
            if p.parent.name in committed and not p.is_symlink()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trigger-gib", type=float, default=1.25)
    parser.add_argument("--target-gib", type=float, default=1.75)
    args = parser.parse_args()
    if shutil.disk_usage(RUN).free >= args.trigger_gib * 1024**3:
        print("Archive threshold not reached; no files changed.")
        return
    path = RUN / "result_archive_audit.json"
    audit = json.loads(path.read_text()) if path.exists() else dict(results=[])
    audit["free_bytes"] = shutil.disk_usage(RUN).free
    candidates = terminal_paths(RUN)
    for source in sorted(candidates, key=lambda p: p.stat().st_size, reverse=True):
        audit["results"].append(archive_result(source))
        audit["source_sha256"] = digest(Path(__file__))
        audit["free_bytes"] = shutil.disk_usage(RUN).free
        temporary = path.with_name(path.name + ".writing")
        temporary.write_text(json.dumps(audit, indent=2) + "\n")
        os.replace(temporary, path)
        if audit["free_bytes"] >= args.target_gib * 1024**3:
            break
    print("Archived", len(audit["results"]), "terminal results; free GiB", audit["free_bytes"] / 1024**3)


if __name__ == "__main__":
    main()
