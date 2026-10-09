"""Freeze pilot membership, complete source snapshots, budgets and numerical closure."""

import datetime
import hashlib
from pathlib import Path

from inventory import pilot_members
from overlay import read, write

from leo.application.hard60_b7 import B7_POLICY
from leo.application.hard60_runner import Hard60Configuration
from leo.application.regional_position_runner import json_value

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    authority = HERE.parent / "2026_10_09_position_error_iter104/source_bindings.json"
    snapshot_path = HERE / "source-snapshot.json"
    snapshot = read(snapshot_path)
    members = pilot_members(read(authority))
    labels = [row["label"] for row in members]
    assert set(labels) == {row["label"] for row in snapshot["members"]}
    assert snapshot["authority_sha256"] == hashlib.sha256(authority.read_bytes()).hexdigest()
    previous = HERE.parent / "2026_10_09_position_error_iter103/protocol.json"
    old = read(previous)
    hashes = dict(old["source_sha256"])
    for name, digest in hashes.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    files = {authority, snapshot_path, previous, HERE / "README.md"}
    files.update(
        HERE / name
        for name in (
            "inventory.py",
            "overlay.py",
            "run.py",
            "freeze.py",
            "source_snapshot.py",
            "controller.py",
            "test_controller.py",
            "test_inventory.py",
            "test_overlay.py",
            "test_run.py",
        )
    )
    for member in snapshot["members"]:
        for entry in member["checkpoints"].values():
            path = HERE / entry["file"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["file_sha256"]
            files.add(path)
    for path in files:
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    plan = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        labels=labels,
        membership=members,
        slice_seconds=500,
        maximum_slices_per_phase=6,
        phases=["baseline", "candidate"],
        maximum_workers=2,
        threads_per_worker=1,
        b7_policy=B7_POLICY,
        hard60_configuration=json_value(Hard60Configuration()),
        maximum_retained_regions_per_member=3 * Hard60Configuration().basins,
        trigger="All ordinary retained calibration failures, every pass and grid level",
        source_cache="Verified exact keys, plus explicitly bound old hard60 coarse-only alias",
        nonnumeric_source_exclusions=["application/regional_position_report.py"],
        coarse_alias=(
            "Only old hard60 baseline config:point -> b7-shared:point; "
            "same input/evidence/prior/bank/current config/physical code; exact objective check"
        ),
        candidate="Direct102 prefit; fresh103 correction/postfit; optional one102 postfit polish",
        c_scope="Shared calibration/association; matched c finals and B7",
        source_sha256=hashes,
    )
    write(HERE / "protocol.json", plan)
    print("Frozen", len(labels), "members; no numerical work executed")


if __name__ == "__main__":
    main()
