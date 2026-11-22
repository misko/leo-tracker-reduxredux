"""Replay two saved completions with a fixed 1e-13 score-only perturbation."""

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from leo.analysis.glrt_frequency_input import frequency_evidence
from leo.contracts.digests import canonical_digest
from tools import algo08_position, algo08_scan
from tools.pipeline_eval.qualification import experimental_publication

work = Path("/tmp/leo-algo08v2-2x-bench")
specification = json.loads((work / "integration-moments-v2/spec.json").read_bytes())


def perturb(native):
    changed = deepcopy(native)
    source = changed["source"]
    scores = []
    for i, probe in enumerate(source["probes"]):
        for factor in probe["candidates"]:
            old = factor["fractional_margin"]
            factor["fractional_exact_score"] += 1e-13 if i % 2 else -1e-13
            new = factor["fractional_exact_score"] - factor["fractional_control_score"]
            if (old >= .025) != (new >= .025) or (old >= .1) != (new >= .1):
                raise ValueError("perturbation crossed an inherited margin threshold")
            factor["fractional_margin"] = new
            scores.append(abs(old - new))
    detector = changed["provenance"]["detector_sha256"].removeprefix("sha256:")
    detection = canonical_digest([
        "cancellation", source["raw_recording_authority_digest"], detector, source["probes"],
    ])
    source["analysis_manifest_sha256"] = detection
    changed["provenance"]["run_id"] = "blind-compact-" + detection[7:39]
    return changed, max(scores)


def solve(native, pair):
    result = {}

    def analyze(recording, root, assets, archive, offer):
        prepare = algo08_position.prepare_native_scan

        def audited_prepare(*args, **kwargs):
            prepared = prepare(*args, **kwargs)
            result["noise"] = prepared["noise"]
            rows = prepared["tracks"]["observations"]
            result["observations"] = rows
            result["tracks"] = prepared["tracks"]["tracks"]
            return prepared

        with patch.object(algo08_position, "prepare_native_scan", audited_prepare):
            prediction, packet, policy = algo08_scan.solve(
                native, algo08_scan.TleArchiveReader(archive), assets, offer,
            )
        if prediction["status"] != "ok" or not packet:
            raise ValueError("saved perturbation did not exercise the completed solution")
        pngs = algo08_scan.render(packet, title=recording.name)
        result.update(
            arms=prediction["arms"],
            policy=policy,
            grid=canonical_digest({k: v for k, v in packet["position_grid"].items()
                                   if k not in ("binding", "elapsed_seconds")}),
            path=canonical_digest(packet["position_path"]),
            pngs={key: sha256(png).hexdigest() for key, png in pngs.items()},
        )
        return {}

    with TemporaryDirectory() as scratch:
        args = SimpleNamespace(recording=Path(pair["recording"]), region=Path(pair["region"]),
                               bulk_root=Path(scratch), archive=Path("/var/lib/leo/tle"))
        with patch.object(algo08_scan, "analyze", analyze):
            experimental_publication.run(args, specification)
    return result


def summarize(before, after, stock, shifted, max_margin):
    original, original_rf, _ = frequency_evidence(before)
    proposed, proposed_rf, _ = frequency_evidence(after)
    target = {}
    target["max_fractional_margin_change"] = max_margin
    target["fractional_marks_only_fields"] = {
        "native_hash_equal": canonical_digest(before) == canonical_digest(after),
        "ids_equal": original.ids == proposed.ids,
        "cfo_equal": np.array_equal(original.frequency_hz, proposed.frequency_hz),
        "rf_equal": np.array_equal(original_rf, proposed_rf),
        "weights_equal": np.array_equal(original.candidate_weight, proposed.candidate_weight),
        "max_signal_probability_delta": float(np.max(abs(
            original.signal_probability - proposed.signal_probability))),
    }
    a, b = stock["noise"], shifted["noise"]
    distributions = "per_observation_noise_sigma_hz"
    target["noise_summary"] = {
        "reference": {k: v for k, v in a.items() if k != distributions},
        "perturbed": {k: v for k, v in b.items() if k != distributions},
        "max_observation_sigma_delta_hz": max(abs(v - b[distributions][k])
                                               for k, v in a[distributions].items()),
        "equal": a == b,
    }
    target["changed_figure_names"] = [n for n in stock["pngs"]
                                       if stock["pngs"][n] != shifted["pngs"][n]]
    target["changes_in_saved_consumer"] = {
        k: stock[k] != shifted[k] for k in ("arms", "policy", "grid", "path", "pngs")
    }
    target["location_arms_equal"] = {
        k: stock["arms"][k]["latlon"] == shifted["arms"][k]["latlon"] for k in stock["arms"]
    }
    target["graph_equal"] = json.dumps(stock["tracks"], default=algo08_position._json_value) == (
        json.dumps(shifted["tracks"], default=algo08_position._json_value))
    target["observation_equal_excluding_margin"] = [
        {k: v for k, v in row.items() if k != "fractional_margin"} for row in stock["observations"]
    ] == [{k: v for k, v in row.items() if k != "fractional_margin"}
          for row in shifted["observations"]]
    return target


receipt = {}
for case in ("DS30-0016", "south"):
    root = work / "integration-shared/pairs" / case
    pair = json.loads((root / "pair.json").read_bytes())
    path, = (root / "candidate/fast-scan-automatic-work").glob("*/detections.json")
    before = json.loads(path.read_bytes())
    after, max_margin = perturb(before)
    if case == "south":
        shifted, stock = solve(after, pair), solve(before, pair)
    else:
        stock, shifted = solve(before, pair), solve(after, pair)
    receipt[case] = summarize(before, after, stock, shifted, max_margin)
print(json.dumps(receipt, indent=2, allow_nan=False, default=algo08_position._json_value))
