"""Freeze the acquisition-only split-gauge training candidate models."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np

from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import find_element_set_record
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from tools.research import fit_independent_phase as v1
from tools.research.independent_phase_split_gauge import phase_cfo

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "reports/figures/2026_09_23_independent_phase"
OUTPUT = DIRECTORY / "v2/training-model.json"
PROTOCOL = ROOT / "reports/2026_09_23_independent_phase_v2_protocol.md"


def verify_frozen_inputs(artifact: dict) -> None:
    for relative, expected in artifact["input_sha256"].items():
        if v1.digest(ROOT / relative) != expected:
            raise ValueError(f"frozen v2 input changed: {relative}")
    for relative, expected in artifact["implementation_sha256"].items():
        if v1.digest(ROOT / relative) != expected:
            raise ValueError(f"frozen v2 implementation changed: {relative}")


predict_model = v1.predict_model


def acquisition_only_rows(rows: list[dict]) -> list[dict]:
    """Select branch zero after asserting it is the archived acquired seed."""
    for row in rows:
        observation = row["observation"]
        if not row["branches"] or not np.isclose(
            row["branches"][0]["seed_cfo_hz"],
            observation["acquired_cfo_hz"],
            rtol=0,
            atol=1e-9,
        ):
            raise ValueError("branch zero is not the archived acquired-CFO seed")
        row["selected_seed_index"] = 0
    return rows


def main() -> None:
    binding_path = DIRECTORY / "binding.json"
    frames_path = DIRECTORY / "train-frames.json.gz"
    cache_path = v1.CACHE_ROOT / "state_cache.npz"
    receipt_path = v1.CACHE_ROOT / "cache_receipt.json"
    gauge_path = ROOT / "tools/research/independent_phase_split_gauge.py"
    qualification_path = DIRECTORY / "train-all-branch-qualification.json"
    if not PROTOCOL.exists():
        raise ValueError("v2 protocol must be frozen before fitting")
    if OUTPUT.exists():
        raise ValueError("fresh v2 model output required")
    binding = json.loads(binding_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    with gzip.open(frames_path, "rt") as stream:
        frames = json.load(stream)
    if frames["fresh_held_visits_read"] or frames["old_reserved_visits_read"]:
        raise ValueError("training replay opened reserved IQ")
    rows = acquisition_only_rows(
        sorted(frames["rows"], key=lambda row: row["observation"]["time_s"])
    )
    split = {
        row["visit_index"]: row["partition"]
        for row in binding["fresh_random_whole_visit_split"]
    }
    if len(rows) != 15 or sorted(
        row["observation"]["visit_index"] for row in rows
    ) != sorted(visit for visit, role in split.items() if role == "train"):
        raise ValueError("v2 rows differ from the frozen training split")
    glrt_y = np.asarray([row["observation"]["normalized_cfo_hz"] for row in rows])
    glrt_t = np.asarray([row["observation"]["time_s"] for row in rows])
    phase_y, phase_t = map(np.asarray, zip(*(phase_cfo(row) for row in rows), strict=True))
    with np.load(cache_path, allow_pickle=False) as opened:
        cache = {key: opened[key] for key in opened.files}
    sites, metadata = v1.regional_grid()
    candidate_ids = cache["candidate_id"].astype(int)
    mirror_sum = float(glrt_t.min() + glrt_t.max())

    def screen(observed, times, observation_times, mirrored):
        query = mirror_sum - 2 * observation_times + times if mirrored else times
        p, velocity = v1.interpolate_states(cache, np.rint(query * 1e9).astype(np.int64))
        models = []
        for site_index, site in enumerate(sites):
            visible = np.all(
                np.sum((p - site) * np.asarray(metadata[site_index]["up"]), axis=-1) > 0,
                axis=1,
            )
            prediction = v1.doppler_hz(site, p, velocity)
            rms, coefficient, centre = v1.affine_score(observed, prediction, times)
            for index in np.flatnonzero(visible):
                models.append(
                    (
                        float(rms[index]),
                        int(candidate_ids[index]),
                        site_index,
                        coefficient[index],
                        centre,
                    )
                )
        return sorted(models, key=lambda row: (row[0], row[1], row[2]))[:16]

    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        prepared = prepare_adaptive_tle_position_inputs(
            binding["session_id"], inputs=store, archive=TleArchiveReader(Path("/var/lib/leo/tle"))
        )
    finally:
        store.close()
    if prepared.snapshot_digest != receipt["prepared_evidence"]["snapshot_digest"]:
        raise ValueError("causal snapshot changed")
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    matches = [
        item
        for item in archive.list_snapshots()
        if item.digest == prepared.snapshot_digest
        and item.collected_utc_ns == prepared.snapshot_collected_utc_ns
    ]
    if len(matches) != 1:
        raise ValueError("prepared causal snapshot does not resolve uniquely")
    snapshot_text = archive.read(matches[0])

    arms = {}
    for family, observed, times in (("glrt", glrt_y, glrt_t), ("phase", phase_y, phase_t)):
        for suffix, mirrored in (("candidate", False), ("wrong_time", True)):
            finalists = screen(observed, times, glrt_t, mirrored)
            geometry_times = mirror_sum - 2 * glrt_t + times if mirrored else times
            exact = v1.exact_models(
                prepared,
                [row[1] for row in finalists],
                [sites[row[2]] for row in finalists],
                [np.asarray(metadata[row[2]]["up"]) for row in finalists],
                observed,
                geometry_times,
                times,
            )
            ranked = sorted(zip(finalists, exact, strict=True), key=lambda row: row[1][0])
            cached, result = ranked[0]
            arms[f"{family}_{suffix}"] = {
                "candidate_norad": cached[1],
                "site": metadata[cached[2]],
                "cache_training_rms_hz": cached[0],
                "exact_training_rms_hz": result[0],
                "offset_hz": float(result[1][0]),
                "drift_hz_s": float(result[1][1]),
                "time_centre_s": result[2],
                "finalists": [
                    {"cache_rms_hz": row[0], "norad": row[1], "site_index": row[2]}
                    for row in finalists
                ],
            }
        rms, coefficient, centre = v1.affine_score(observed, np.zeros((1, len(times))), times)
        arms[f"{family}_constant_rate"] = {
            "training_rms_hz": float(rms[0]),
            "offset_hz": float(coefficient[0, 0]),
            "drift_hz_s": float(coefficient[0, 1]),
            "time_centre_s": centre,
        }

    selected = {}
    for name, row in arms.items():
        if name.endswith("constant_rate"):
            selected[name] = {"model_type": "constant_rate", **row}
            continue
        site = v1.Region(row["site"]["latitude_deg"], row["site"]["longitude_deg"], 1, 1)
        record = find_element_set_record(snapshot_text, row["candidate_norad"])
        if record is None:
            raise ValueError("selected candidate absent from causal snapshot")
        selected[name] = {
            "model_type": "exact_nominal_sgp4",
            "candidate_norad": row["candidate_norad"],
            "receiver_ecef_km": site.points([0], [0]).ecef_km[0].tolist(),
            "wrong_time": name.endswith("wrong_time"),
            "tle_lines": [record.name, record.first_line, record.second_line],
            "offset_hz": row["offset_hz"],
            "drift_hz_s": row["drift_hz_s"],
            "time_centre_s": row["time_centre_s"],
        }
    input_paths = (
        binding_path,
        frames_path,
        cache_path,
        receipt_path,
        PROTOCOL,
        qualification_path,
    )
    implementation_paths = (
        Path(__file__),
        Path(v1.__file__),
        gauge_path,
        ROOT / "tools/research/evaluate_independent_phase_v2.py",
        ROOT / "tools/research/evaluate_independent_phase_holdout.py",
        ROOT / "tools/research/extract_independent_phase_arc.py",
        ROOT / "tools/research/extract_longarc_phase.py",
        ROOT / "src/leo/analysis/qam/pilot.py",
        ROOT / "src/leo/analysis/starlink/templates.py",
        ROOT / "src/leo/analysis/adaptive_tle_prediction.py",
        ROOT / "src/leo/analysis/research/formal_orbit.py",
        ROOT / "src/leo/sky/propagation.py",
        ROOT / "reports/2026_09_23_long_cache_feasibility/helper/regular_cache.py",
    )
    output = {
        "schema": "independent-phase-training-model/v2",
        "scope": "15 random training dwells; acquisition branch zero; split-gauge calibration",
        "training_visit_count": len(rows),
        "held_iq_read": False,
        "candidate_count": len(candidate_ids),
        "site_count": len(sites),
        "exact_rerank_count_per_model": 16,
        "arms": arms,
        "selected_models": selected,
        "start_utc_ns": prepared.start_utc_ns,
        "wrong_time_mirror_sum_s": mirror_sum,
        "tle_authority": {
            "snapshot_digest": prepared.snapshot_digest,
            "snapshot_collected_utc_ns": prepared.snapshot_collected_utc_ns,
        },
        "input_sha256": {
            str(path.relative_to(ROOT)): v1.digest(path) for path in input_paths
        },
        "implementation_sha256": {
            str(path.relative_to(ROOT)): v1.digest(path) for path in implementation_paths
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
