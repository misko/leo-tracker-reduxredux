"""Freeze the ordinary failed-calibration prefit diagnostic; never run a fit."""

import datetime
import hashlib
import importlib.util
import json
from pathlib import Path

import replay_prefit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    destination = HERE / "prefit-protocol.json"
    assert not destination.exists()
    published = json.loads((HERE / "published-v3.json").read_text())["manifest"]["document"]
    for name, expected in published["configuration"]["source_digests"].items():
        actual = "sha256:" + hashlib.sha256((ROOT / "src/leo" / name).read_bytes()).hexdigest()
        assert actual == expected, name
    files = set((ROOT / "src/leo").rglob("*.py"))
    files.add(ROOT / "src/leo/analysis/_regional_orbits.cpp")
    native = importlib.util.find_spec("leo.analysis._regional_orbits")
    assert native is not None and native.origin
    files.add(Path(native.origin).resolve())
    files.update(
        HERE / name
        for name in (
            "published-v3.json",
            "verified-checkpoints.json",
            "extract_checkpoints.py",
            "replay_prefit.py",
            "freeze_prefit.py",
        )
    )
    plan = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        session_id=published["session_id"],
        selection="ordinary lowest-score retained calibration failure",
        starts=["ordinary-coarse", "zero-timing"],
        solvers=["legacy", "bounded"],
        fixed_position=True,
        maximum_seconds=20,
        maximum_iterations=600,
        maximum_fits=4,
        maximum_bank_seconds=180,
        slope_half_width_hz_s=60,
        stationarity_threshold=0.001,
        c_scope="Fitted-c production prefit; downstream final replay must match both c arms",
        continuation="Stop after four prefits; review before separately frozen final continuation",
        source_sha256={
            str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(files)
        },
        scope="Consumed user-selected scan; no reference-guided seed or production change",
    )
    replay_prefit.write(destination, plan)
    print("Frozen four prefits, not launched")


if __name__ == "__main__":
    main()
