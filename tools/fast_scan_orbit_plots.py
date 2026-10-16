"""Render saved Hard60 selections without running acquisition or fitting.

Execute in the selected standard worker environment, which owns the numerical
contracts and propagation routines. The repository's renderer is storage-free.
"""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def receiver_nuisance(state, obs):
    """Evaluate the published receiver terms in the original frequency frame."""
    vector = np.asarray(state.vector)
    baseline = np.asarray(state.receiver_baseline_hz)
    if baseline.shape != obs.times_s.shape:
        raise ValueError("published calibration inventory differs from GLRT windows")
    dt = obs.times_s - obs.time_center_s
    rx = obs.receiver
    rf = (obs.rf_hz - obs.rf_center_hz) / 1e9
    result = baseline + vector[2 + 2 * rx] + vector[3 + 2 * rx] * dt + vector[6] * rf
    for receiver in (0, 1):
        mask = rx == receiver
        result[mask] += np.interp(
            obs.times_s[mask], state.clock_nodes_s, state.clock_knots_hz[receiver]
        )
    result += rf * dt / 100 * np.asarray(state.rf_time_coefficients)[rx]
    return result


def publish_orbit_plots(*, source, root, tle_root, run_id, title):
    from leo.analysis.hard60_score import likelihood
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.analysis.regional_position_score import predict_orbits, zero_sum_basis
    from leo.application.hard60_runner import HARD60_SCORE
    from leo.application.regional_position_inputs import prepare_position_windows
    from leo.contracts.digests import canonical_digest
    from leo.contracts.regional_position import PositionObservations, RegionalPrior
    from leo.operations.tle_archive import TleArchiveReader
    from leo.presentation.fast_scan_orbits import render_fast_scan_orbits
    from leo.presentation.orbit_plot import OrbitCurve, OrbitLane, OrbitPeak
    from leo.sky.propagation import parse_element_sets
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.regional_position_v3 import B7Store

    store = FastScanStore(root)
    if store.orbit_manifest(run_id)["artifacts"]:
        # Verify every existing artifact before accepting a resumed publication.
        for entry in store.orbit_manifest(run_id)["artifacts"]:
            store.orbit_artifact(run_id, entry["name"])
        return
    status = B7Store(root).status(source.session_id)
    if status.manifest is None:
        raise ValueError("orbit plots require a published regional selection")
    document = status.manifest.document
    if (
        document.input_manifest_sha256 != source.input_manifest_sha256
        or document.analysis_manifest_sha256 != source.analysis_manifest_sha256
    ):
        raise ValueError("orbit selection belongs to different GLRT inputs")
    selected = document.methods[0].arms[0].selected
    if selected is None:
        reason = "No satellite selection published"
        lanes = tuple(
            OrbitLane(f"RX{rx + 1}", f"CH{channel}", ()) for channel in range(1, 9) for rx in (0, 1)
        )
        store.publish_orbits(
            run_id,
            render_fast_scan_orbits(
                lanes, title=title, alias_period_hz=1 / 4.4e-6, subtitle=reason
            ),
            {
                "state": "unavailable",
                "reason": reason,
                "input_sha256": source.input_manifest_sha256,
                "analysis_sha256": source.analysis_manifest_sha256,
            },
        )
        return
    state = selected.joint_state
    if state is None:
        matches = [
            row
            for row in document.diagnostics["final_starts"]
            if row["arm"] == "fitted-c"
            and row["basin"] == selected.source_basin
            and row["fit"]
            and np.isclose(row["fit"]["objective"], selected.objective, atol=1e-6, rtol=0)
        ]
        if not matches:
            raise ValueError("selected fallback fit is absent from published diagnostics")
        vector = np.asarray(matches[0]["fit"]["vector"])
        relative = zero_sum_basis(len(selected.satellites)) @ vector[8:]
        timing_penalty = 0.5 * (vector[7] / HARD60_SCORE.common_sigma_s) ** 2
        timing_penalty += 0.5 * np.sum((relative / HARD60_SCORE.relative_sigma_s) ** 2)
        calibration = document.diagnostics["calibrations"][selected.source_basin]
        state = SimpleNamespace(
            vector=vector,
            stage="B1",
            receiver_baseline_hz=calibration["receiver_baseline_hz"],
            clock_nodes_s=[0.0, 300.0],
            clock_knots_hz=[[0.0, 0.0], [0.0, 0.0]],
            rf_time_coefficients=[0.0, 0.0],
            satellite_centers_s=[],
            satellite_offsets_hz=[],
            satellite_slopes_hz_s=[],
            likelihood_nll=selected.objective - timing_penalty,
        )
    prepared = prepare_position_windows(source)
    obs = prepared.observations
    archive = TleArchiveReader(tle_root)
    snapshot = archive.select_latest_before(prepared.start_utc_ns - 505_000_000_000)
    if snapshot.digest != document.diagnostics["snapshot_sha256"]:
        raise ValueError("orbit plot TLE snapshot differs from selected model")
    catalogue = parse_element_sets(archive.read(snapshot))
    lookup = {int(n): i for i, n in enumerate(catalogue.satellite_numbers)}
    # Include all 300 seconds even if passing GLRT windows cover a shorter interval.
    extent = PositionObservations(
        ("start", "end"),
        np.array([0.0, 300.0]),
        np.zeros(2),
        np.full(2, obs.rf_hz[0]),
        np.zeros(2),
        np.ones(2),
        np.ones(2),
    )
    bank, _ = build_regional_bank(
        catalogue,
        [lookup[n] for n in selected.satellites],
        prepared.start_utc_ns,
        extent,
        RegionalPrior(),
        maximum_seconds=60,
    )
    bank = bank.select([list(bank.numbers).index(n) for n in selected.satellites])
    vector = np.asarray(state.vector)
    shifts = vector[7] + zero_sum_basis(len(bank.numbers)) @ vector[8:]
    rx = obs.receiver
    nuisance = receiver_nuisance(state, obs)
    centers = np.asarray(state.satellite_centers_s)
    offsets = np.asarray(state.satellite_offsets_hz)
    slopes = np.asarray(state.satellite_slopes_hz_s)

    def prediction(observations):
        values, visible, _, _ = predict_orbits(
            bank, observations, RegionalPrior(), vector[:2], shifts, derivatives=False
        )
        if len(centers):
            values += offsets + (observations.times_s[:, None] - centers) * slopes
        return values, visible

    values, visible = prediction(obs)
    terms = likelihood(obs.measured_hz, values + nuisance[:, None], visible, HARD60_SCORE)
    if not np.isclose(terms.nll, state.likelihood_nll, atol=1e-5, rtol=0):
        raise ValueError(
            f"replayed orbit likelihood differs: {terms.nll} vs {state.likelihood_nll}"
        )
    # Explicit posterior classification; never claim frozen bootstrap membership.
    best = terms.responsibilities.argmax(axis=1)
    associated = terms.responsibilities[np.arange(len(best)), best] > terms.clutter_probability
    times = np.linspace(0, 300, 1201)
    lanes = []
    for channel in range(1, 9):
        for receiver in (0, 1):
            mask = (obs.channel == channel) & (rx == receiver)
            channel_rf = np.unique(obs.rf_hz[obs.channel == channel])
            if len(channel_rf) != 1:
                raise ValueError(f"CH{channel} requires one recorded RF reference")
            dense = PositionObservations(
                tuple(f"dense-{i}" for i in range(len(times))),
                times,
                np.zeros(len(times)),
                np.full(len(times), channel_rf[0]),
                np.full(len(times), receiver),
                np.full(len(times), channel),
                np.ones(len(times)),
            )
            curves, visibility = prediction(dense)
            lanes.append(
                OrbitLane(
                    f"RX{receiver + 1}",
                    f"CH{channel}",
                    tuple(
                        OrbitPeak(
                            obs.window_ids[i],
                            float(obs.times_s[i]),
                            float(obs.measured_hz[i] - nuisance[i]),
                            str(bank.numbers[best[i]]) if associated[i] else None,
                        )
                        for i in np.flatnonzero(mask)
                    ),
                    tuple(
                        OrbitCurve(
                            str(number),
                            tuple(times),
                            tuple(np.where(visibility[:, j], curves[:, j], np.nan)),
                        )
                        for j, number in enumerate(bank.numbers)
                    ),
                )
            )
    provenance = {
        "input_sha256": source.input_manifest_sha256,
        "analysis_sha256": source.analysis_manifest_sha256,
        "selection_sha256": canonical_digest(document.model_dump(mode="json")),
        "snapshot_sha256": snapshot.digest,
        "arm": "fitted-c",
        "stage": state.stage,
        "satellites": list(selected.satellites),
        "time_limits_s": [0, 300],
        "observations": len(best),
        "associated": int(associated.sum()),
        "unassociated": int((~associated).sum()),
        "replayed_likelihood_nll": terms.nll,
        "association": "selected-model maximum satellite posterior exceeds clutter posterior",
        "frequency_frame": "receiver calibration removed; wrapped at GLRT alias period",
    }
    pngs = render_fast_scan_orbits(
        lanes,
        title=title,
        alias_period_hz=1 / 4.4e-6,
        subtitle=f"{state.stage} fitted-c selection · receiver calibration removed · "
        "posterior association · conditional satellite identities",
    )
    store.publish_orbits(run_id, pngs, provenance)


def main():
    if __package__:
        from .fast_scan_standard_pipeline import load_tracking_input
    else:
        from fast_scan_standard_pipeline import load_tracking_input
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--title", required=True)
    args = parser.parse_args()
    publish_orbit_plots(
        source=load_tracking_input(json.loads(args.input.read_bytes())),
        root=args.output,
        tle_root=args.tle_root,
        run_id=args.run_id,
        title=args.title,
    )


if __name__ == "__main__":
    main()
