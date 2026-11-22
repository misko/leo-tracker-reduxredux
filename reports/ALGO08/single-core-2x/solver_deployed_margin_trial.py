"""Trace deployed arithmetic through the released radio-noise preparation."""

import argparse
import json
import runpy
from contextlib import ExitStack
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
MARGIN = "fractional_margin"


def observation_support(rows):
    support = {row["observation_id"]: {k: v for k, v in row.items() if k != MARGIN}
               for row in rows}
    if len(support) != len(rows):
        raise ValueError("Duplicate winning observation identity")
    return support


def matched_margins(original_rows, observed_rows):
    """Substitute archived native margins after exact winning-support comparison."""
    first, second = (json.dumps(observation_support(rows), sort_keys=True)
                     for rows in (original_rows, observed_rows))
    if first != second:
        raise ValueError("The deployed and candidate observations do not match")
    margins = {row["observation_id"]: row[MARGIN] for row in original_rows}
    return [dict(row, fractional_margin=margins[row["observation_id"]]) for row in observed_rows]


def read_inputs(pair_path):
    from leo.contracts.algo08_region import Algo08Region
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    helper = runpy.run_path(str(HERE / "residual_attribution_trial.py"))
    pair = helper["read"](pair_path)
    archive = Path(pair["archive"]["root"])
    if archive_identity(archive) != pair["archive"] or "failure" in pair:
        raise ValueError("Expected the completed, bound pair and its original orbit archive")
    offer = Algo08Region.parse(helper["read"](Path(pair["region"]))).document()
    if any(row["receipt"]["region"] != offer or row["receipt"]["decision"] != "complete"
           for row in pair["runs"].values()):
        raise ValueError("Expected both published fixes and the original offer")
    native = {key: helper["saved_native"](pair_path, key, pair["runs"][key])
              for key in ("baseline", "candidate")}
    if len({doc["source"]["raw_recording_authority_digest"] for doc in native.values()}) != 1:
        raise ValueError("Expected both native documents to bind the same sealed recording")
    return pair, archive, offer, native


def readout(noise):
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.digests import canonical_digest

    noise = json.loads(json.dumps(noise, default=_json_value))
    return {k: noise[k] for k in ("constant_radio_sigma_hz", "floor_sigma_hz", "strength_hz2",
                                  "extra_parameter_BIC_gain", "heteroscedastic_selected")
            if k in noise} | {"sha256": canonical_digest(noise)}


def prep(pair_files, output):
    import numpy as np

    from leo.analysis.localization_v3.noise import estimate_noise
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.digests import canonical_digest

    config = TrackConfig(**json.loads((RELEASE / "assets/tracks.json").read_bytes())["config"])
    results = {}
    for path in pair_files:
        pair, _, _, inputs = read_inputs(path)
        prepared, clocks, noise = {}, {}, {}
        for key, native in inputs.items():
            start = process_time_ns()
            tracks = prepare_tracks(native, config)
            prepare_ns = process_time_ns() - start
            start = process_time_ns()
            noise[key] = estimate_noise(tracks["tracks"], tracks["observations"])
            clocks[key] = dict(tracks_cpu_ns=prepare_ns, noise_cpu_ns=process_time_ns() - start)
            prepared[key] = tracks
        stock, candidate = prepared["baseline"], prepared["candidate"]
        original, observed = stock["observations"], candidate["observations"]
        restored = matched_margins(original, observed)
        graph = {
            key: canonical_digest(json.loads(json.dumps(tracks["tracks"], default=_json_value)))
            for key, tracks in prepared.items()
        }
        if graph["baseline"] != graph["candidate"]:
            raise ValueError("Original winning support matched but Graph output changed")
        margins = np.array([abs(a[MARGIN] - b[MARGIN])
                            for a, b in zip(restored, observed, strict=True)])
        original_noise, candidate_noise = (noise[k]["per_observation_noise_sigma_hz"]
                                           for k in ("baseline", "candidate"))
        deltas = np.array([abs(value - candidate_noise[oid])
                           for oid, value in original_noise.items()])
        replay = estimate_noise(candidate["tracks"], restored)
        results[path.parent.name] = dict(
            offer=pair["runs"]["candidate"]["receipt"]["region"], archive=pair["archive"],
            pair_specification=pair["candidate_specification_digest"], clocks=clocks,
            native={key: canonical_digest(value) for key, value in inputs.items()}, graph=graph,
            observations=len(observed), changed_margins=int(np.count_nonzero(margins)),
            maximum_margin_delta=float(margins.max(initial=0.)),
            changed_noise_standard_deviations=int(np.count_nonzero(deltas)),
            maximum_noise_sigma_delta_hz=float(deltas.max(initial=0.)),
            noise={key: readout(value) for key, value in noise.items()},
            restored_noise_matches=replay == noise["baseline"],
        )
    with output.open("x") as stream:
        json.dump(results, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def cross_worker(native, reference, spec, archive, offer, output):
    """Replay candidate using only the deployed native margins at the noise port."""
    from tools.pipeline_eval.variants.experimental import lean_startup

    install = lean_startup.install
    baseline_native = json.loads(reference.read_bytes())
    authority = json.loads(native.read_bytes())["source"]["raw_recording_authority_digest"]
    if authority != baseline_native["source"]["raw_recording_authority_digest"]:
        raise ValueError("Exact noise crossover requires the same sealed recording")
    with ExitStack() as stack:
        def install_then_bind():
            install()
            from leo.analysis.localization_v3.tracks import winning_observations
            from leo.application import localization_v3

            original = localization_v3.estimate_noise
            baseline, _ = winning_observations(baseline_native)

            def exact_noise(tracks, observations):
                return original(tracks, matched_margins(baseline, observations))

            stack.enter_context(patch.object(localization_v3, "estimate_noise", exact_noise))

        stack.enter_context(patch.object(lean_startup, "install", install_then_bind))
        helper = runpy.run_path(str(HERE / "residual_attribution_trial.py"))["worker"]
        helper(native, spec, archive, offer, output, include_evidence=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    prepare = modes.add_parser("prep")
    prepare.add_argument("output", type=Path)
    prepare.add_argument("pair_files", nargs="+", type=Path)
    cross = modes.add_parser("cross-worker")
    for name in ("native", "reference", "spec", "archive", "offer", "output"):
        cross.add_argument(name, type=Path)
    options = vars(parser.parse_args())
    {"prep": prep, "cross-worker": cross_worker}[options.pop("mode")](**options)
