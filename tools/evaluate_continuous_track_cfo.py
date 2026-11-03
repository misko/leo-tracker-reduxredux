"""Matched original/refined-CFO diagnostics on an unchanged Graph population."""

import argparse
import hashlib
import json
from pathlib import Path

from associate_merged_track_catalogue import write
from evaluate_shared_satellite_phase import Experiment, protocol

from leo.analysis.research.qualified_frequency_replay import replay_qualified_frequencies


def run(case, measurements, output, *, refined, fitted_c):
    root = Path(__file__).resolve().parents[1]
    recording = (
        root
        / "reports/2026_10_17_ds22_merged_satellites"
        / ("cohort" if case.startswith("DS22") else "dsx01_adapter")
        / case
    )
    study = Experiment(
        recording,
        Path(f"/tmp/ds22-shared-phase-bank-{case}"),
        fitted_c=fitted_c,
        phase_enabled=True,
        drift_sigma_hz_s=0.5,
        drift_bound_hz_s=1.0,
    )
    data_protocol = json.loads((measurements / "protocol.json").read_text())
    summary = json.loads((measurements / "summary.json").read_text())
    if (
        not data_protocol["all_graph_points"]
        or summary["selected"] != summary["evaluated"]
        or data_protocol["original_tracks_sha256"] != study.receipt["tracks_sha256"]
        or data_protocol["reference_position_used"]
        or data_protocol["satellite_identity_used"]
    ):
        raise ValueError("complete response-only original Graph measurements required")
    rows = json.loads((measurements / "results.json").read_text())
    replacement, replay = replay_qualified_frequencies(study.tracks, rows)
    if refined:
        study.tracks = replacement
        by_key = {t["key"]: t for t in replacement}
        study.groups = [(key, [by_key[key]]) for key, _ in study.groups]
    # Original measured-curvature membership is frozen in both measurement arms.
    assert study.curved_keys == frozenset(key for key, _ in study.groups)
    protocol(study, output, "continuous_cfo_diagnostic", 32)
    write(
        output / "measurement_protocol.json",
        dict(
            case=case,
            refined=refined,
            fitted_c=fitted_c,
            original_curvature_eligibility_frozen=True,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            replay_source_sha256=hashlib.sha256(
                root.joinpath(
                    "src/leo/analysis/research/qualified_frequency_replay.py"
                ).read_bytes()
            ).hexdigest(),
            measurement_files={
                name: hashlib.sha256((measurements / name).read_bytes()).hexdigest()
                for name in ("protocol.json", "results.json", "summary.json")
            },
            original_noise_scale_hz=150.0,
            original_point_times_unchanged=True,
            unsupported_measurements="retain original GLRT values",
            no_measurement_weights_changed=True,
        ),
    )
    write(output / "replay.json", replay)
    previous_root = (
        root
        / "reports/2026_10_17_shared_satellite_phase"
        / ("search" if case.startswith("DS22") else "search_resumed")
        / case
        / ("shared_fitted_c" if fitted_c else "shared_c0")
    )
    previous = json.loads((previous_root / "fit.json").read_text())["endpoint"]
    sites = [
        ("supplied_evaluation_site", 37.849061591561885, -122.48574968092912),
        ("previous_blind_endpoint", previous["latitude_deg"], previous["longitude_deg"]),
    ]
    results = []
    for label, lat, lon in sites:
        fit = study.fit(lat, lon, 32, exact=True)
        association = study.associate(fit)
        results.append(
            dict(
                site=label,
                fit=fit,
                association=association,
                use="diagnostic only; no geographic estimate",
            )
        )
        write(output / "diagnosis.json", results)
        print(
            json.dumps(
                dict(
                    case=case,
                    refined=refined,
                    fitted_c=fitted_c,
                    site=label,
                    score=fit["score"],
                    compatible_points=association["compatible_points"],
                )
            ),
            flush=True,
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=("DS22-001", "DSX01-S01"), required=True)
    p.add_argument("--measurements", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--refined", action="store_true")
    p.add_argument("--fitted-c", action="store_true")
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    run(a.case, a.measurements, a.output, refined=a.refined, fitted_c=a.fitted_c)
