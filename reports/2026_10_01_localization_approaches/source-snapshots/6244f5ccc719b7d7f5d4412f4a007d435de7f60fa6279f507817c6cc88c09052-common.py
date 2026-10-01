"""Source-bound I/O adapter for the private broad-acquisition experiment."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = HERE.parent / "2026_09_30_gaussian_sum_64_scan"
CACHE = Path.home() / ".cache/leo/research/broad_prior_acquisition"
sys.path.append(str(BASE))
from physics import OrbitBank, StateLayout, TrackObservations, geometric_candidate_union  # noqa: E402
from prior import make_config  # noqa: E402
from run import independent_tracks  # noqa: E402


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def write_new(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(document, stream, indent=2, allow_nan=False)
        stream.write("\n")


def seal(path, document):
    write_new(path, document)
    write_new(Path(path).with_suffix(".seal.json"), {"prediction_sha256": digest(path)})


def selected_units():
    selection = json.loads((BASE / "selection.json").read_text())
    groups = [selection["selected"][name] for name in ("DS9", "DS10", "DS11")]
    return [group[i]["unit_id"] for i in range(max(map(len, groups)))
            for group in groups if i < len(group)]


@dataclass
class Scan:
    unit_id: str
    session_id: str
    bank: OrbitBank
    layout: StateLayout
    config: object
    tracks: list
    exclusions: list
    inputs: dict
    catalogue_gap: bool
    candidate_union: object


def load_scan(unit):
    if unit not in selected_units():
        raise ValueError("unit is outside frozen 64-scan panel")
    observation_path = BASE / "evidence" / (unit + ".json")
    meta_path = BASE / "evidence" / (unit + "-orbits.json")
    evidence = json.loads(observation_path.read_text())
    meta = json.loads(meta_path.read_text())
    source_path = Path(evidence["source"]["path"])
    bank_path = Path(meta["state_file"])
    if digest(source_path) != evidence["source"]["sha256"]:
        raise ValueError("source observation digest mismatch")
    if meta["observation_sha256"] != evidence["source"]["sha256"]:
        raise ValueError("orbit-to-observation binding mismatch")
    if meta["session_id"] != evidence["session_id"] or not meta["tle"]["causal"]:
        raise ValueError("orbit identity or causality mismatch")
    if digest(bank_path) != meta["state_sha256"]:
        raise ValueError("orbit state digest mismatch")
    with np.load(bank_path, allow_pickle=False) as data:
        bank = OrbitBank(tuple(map(int, data["satellite_ids"])), data["knot_times_s"],
                         data["positions_ecef_km"], data["velocities_ecef_km_s"])
    config = make_config()
    union = geometric_candidate_union(bank, config)
    ids = set(union.norad_ids)
    ix = np.array([i for i, identifier in enumerate(bank.norad_ids) if identifier in ids])
    if not ix.size:
        raise ValueError("empty response-free candidate union")
    bank = OrbitBank(tuple(bank.norad_ids[i] for i in ix), bank.times_s,
                     bank.positions_ecef_km[ix], bank.velocities_ecef_km_s[ix])
    start = json.loads(source_path.read_text())["start_utc_ns"]
    retained, excluded = independent_tracks(evidence)
    tracks = []
    for row in retained:
        times = (np.asarray(row["times_utc_ns"], dtype=np.int64) - start) / 1e9
        obs = TrackObservations(tuple(row["physical_observation_ids"]), times,
                                np.asarray(row["measured_hz"]),
                                np.full(len(times), row["receiver_id"], dtype=int), row["rf_hz"])
        tracks.append((row["track_id"], obs))
    bindings = {str(p): digest(p) for p in (observation_path, meta_path, source_path, bank_path)}
    return Scan(unit, evidence["session_id"], bank, StateLayout(bank.norad_ids), config,
                tracks, excluded, bindings, bool(meta["catalogue_gap"]), union)


def source_bindings(extra=()):
    paths = [Path(__file__), HERE / "PROTOCOL.md", BASE / "physics.py", BASE / "prior.py",
             BASE / "run.py", BASE / "selection.json", ROOT / "src/leo/analysis/gaussian_sum_location.py"]
    return {str(p): digest(p) for p in paths + list(extra)}
