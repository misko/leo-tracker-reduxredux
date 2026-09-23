"""Bounded saved-IQ timing sensitivity with frozen source branches and masks."""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

import leo.analysis.qam.pilot as pilot_module
import leo.analysis.starlink.fractional_epoch as fractional_module
import leo.analysis.starlink.templates as template_module
from leo.analysis.qam.pilot import estimate_edge_pilot_frame_complex_split
from leo.analysis.starlink.fractional_epoch import fractional_take
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from tools.research import evaluate_longarc_phase as cfo
from tools.research import evaluate_longarc_phase_advances as advances
from tools.research.extract_longarc_phase import digest, save, serial

OUTPUT = cfo.ROOT / "reports/figures/2026_09_23_longarc_timing"
VARIANTS = ("minus_one", "plus_one", "fractional")


def shifted_slice(iq, start, content, shift, group_bounds=None):
    """Sample a shifted guarded frame, retaining the interpolation guard in-dwell."""
    left = start - 1 + int(np.floor(shift)) - 8
    right = start + content + 1 + int(np.ceil(shift)) + 8
    if left < 0 or right > len(iq):
        raise ValueError("shifted frame lacks within-dwell interpolation support")
    if group_bounds is not None and (left < group_bounds[0] or right > group_bounds[1]):
        raise ValueError("shifted interpolation support crosses its assigned group")
    positions = np.arange(start - 1, start + content + 1, dtype=float) + shift - left
    return fractional_take(iq[left:right], positions)


def frozen_mask_row(original, variant):
    """Use baseline even eligibility on every variant without changing saved results."""
    row = copy.deepcopy(variant)
    source = original["branches"][original["selected_seed_index"]]["frames"]
    frames = row["branches"][0]["frames"]
    if len(source) != len(frames):
        raise ValueError("timing variant changed frame opportunities")
    for old, new in zip(source, frames, strict=True):
        if old["frame"]["frame_start_sample"] != new["frame"]["frame_start_sample"]:
            raise ValueError("timing variant changed physical frame identity")
        new["frame"]["training_supported"] = old["frame"]["training_supported"]
    return row


def require_same_pairs(original, variant):
    def identity(pairs):
        return [(pair["group"], tuple(pair["endpoint_ids"])) for pair in pairs]

    if identity(original) != identity(variant):
        raise ValueError("timing variant lost or changed a frozen phase pair")


def extract(limit):
    binding_path = cfo.FIGURE / "binding.json"
    baseline_path = cfo.FIGURE / "replay/frames.json.gz"
    binding = json.loads(binding_path.read_text())
    with gzip.open(baseline_path, "rt") as stream:
        baseline = json.load(stream)
    protocol = {
        "schema": "longarc-timing-sensitivity-replay/v1",
        "baseline_sha256": digest(baseline_path),
        "binding_sha256": digest(binding_path),
        "source_sha256": digest(__file__),
        "dependency_sha256": {
            "pilot": digest(pilot_module.__file__),
            "templates": digest(template_module.__file__),
            "fractional_interpolation": digest(fractional_module.__file__),
        },
        "variants": VARIANTS,
        "branch_policy": "baseline-selected source CFO, frozen for all shifts",
        "support_policy": "baseline even eligibility frozen for paired evaluation",
        "new_rf": False,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    chunks = OUTPUT / ("rows-" + protocol["source_sha256"][:12])
    chunks.mkdir(exist_ok=True)
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    completed, processed = [], 0
    try:
        with AdaptiveHopAnalysisInputStore(store).source(binding["session_id"]) as source:
            if source.input_manifest_sha256 != binding["source_input_manifest_sha256"]:
                raise ValueError("saved capture binding changed")
            for original in baseline["rows"]:
                bound = original["observation"]
                target = chunks / f"visit-{bound['visit_index']}.json.gz"
                if target.exists():
                    with gzip.open(target, "rt") as stream:
                        chunk = json.load(stream)
                    if chunk["protocol"] != serial(protocol):
                        raise ValueError("stale checkpoint: choose fresh output")
                    completed.append(chunk)
                    continue
                if processed >= limit:
                    break
                iq = source.read_visit(bound["iq_ordinal"])
                if hashlib.sha256(iq.tobytes()).hexdigest() != original["iq_sha256"]:
                    raise ValueError("saved IQ changed")
                branch = original["branches"][original["selected_seed_index"]]
                rate = binding["sample_rate_hz"]
                content = round(302 * rate * 4.4e-6)
                variants = {}
                for label, shift in (
                    ("minus_one", -1.0),
                    ("plus_one", 1.0),
                    ("fractional", bound["fractional_epoch_offset_samples"]),
                ):
                    frames = []
                    for old in branch["frames"]:
                        start = old["frame"]["frame_start_sample"]
                        group = old["group_id"]
                        bounds = (round(group * 0.02 * rate), round((group + 1) * 0.02 * rate))
                        values = shifted_slice(
                            iq[:, bound["receiver_id"]], start, content, shift, bounds
                        )
                        measured = estimate_edge_pilot_frame_complex_split(
                            values,
                            rate,
                            frame_start_sample=start,
                            acquisition_absolute_cfo_hz=branch["seed_cfo_hz"],
                            edge=bound["edge"],
                        )
                        frames.append(
                            {
                                "group_id": old["group_id"],
                                "frame": serial(asdict(measured)),
                                "session_time_s": old["session_time_s"] + shift / rate,
                                "visit_reference_sample": measured.reference_sample + shift,
                                "session_reference_sample": (
                                    bound["valid_start_counter"]
                                    - binding["source_first_counter"]
                                    + measured.reference_sample
                                    + shift
                                ),
                            }
                        )
                    variants[label] = {
                        "observation": bound,
                        "outer_partition": original["outer_partition"],
                        "shift_samples": shift,
                        "selected_seed_index": 0,
                        "branches": [{"seed_cfo_hz": branch["seed_cfo_hz"], "frames": frames}],
                    }
                chunk = {"protocol": protocol, "variants": variants}
                save(target, chunk)
                completed.append(chunk)
                processed += 1
                print(bound["visit_index"], len(completed), flush=True)
    finally:
        store.close()
    save(
        OUTPUT / "frames.json.gz",
        {"protocol": protocol, "rows": completed, "expected_visit_count": len(baseline["rows"])},
    )


def evaluate():
    with gzip.open(OUTPUT / "frames.json.gz", "rt") as stream:
        extracted = json.load(stream)
    with gzip.open(cfo.FIGURE / "replay/frames.json.gz", "rt") as stream:
        baseline = json.load(stream)
    protocol = extracted["protocol"]
    if protocol["source_sha256"] != digest(__file__):
        raise ValueError("timing extraction source changed")
    for name, module in (
        ("pilot", pilot_module),
        ("templates", template_module),
        ("fractional_interpolation", fractional_module),
    ):
        if protocol["dependency_sha256"][name] != digest(module.__file__):
            raise ValueError("timing extraction dependency changed")
    if protocol["baseline_sha256"] != digest(cfo.FIGURE / "replay/frames.json.gz"):
        raise ValueError("timing baseline changed")
    if protocol["binding_sha256"] != digest(cfo.FIGURE / "binding.json"):
        raise ValueError("timing binding changed")
    if len(extracted["rows"]) != extracted["expected_visit_count"]:
        raise ValueError("timing replay incomplete")
    binding = json.loads((cfo.FIGURE / "binding.json").read_text())
    primary = json.loads((cfo.FIGURE / "evaluation.json").read_text())
    for path, expected in primary["input_sha256"].items():
        if digest(cfo.ROOT / path) != expected:
            raise ValueError("frozen candidate comparison inputs changed")
    norad = primary["candidate_norad"]
    reference = primary["receiver_reference"]
    receiver = cfo.geodetic_to_ecef_km(reference["latitude_deg"], reference["longitude_deg"], 0)
    with gzip.open(cfo.ORBIT / "audit.retained-tles.json.gz", "rt") as stream:
        records = json.load(stream)[binding["session_id"]]["records"]
    catalogue = cfo.parse_element_sets("".join(records[str(value)] for value in norad))
    results = []
    for label in ("integer", *VARIANTS):
        calibration, response, training, coherence = [], [], [], []
        for old, new in zip(baseline["rows"], extracted["rows"], strict=True):
            row = old if label == "integer" else frozen_mask_row(old, new["variants"][label])
            even = advances.pair_rows(row, [0, 3, 5], "even")
            odd = advances.pair_rows(row, [1, 2, 4], "odd")
            require_same_pairs(advances.pair_rows(old, [0, 3, 5], "even"), even)
            require_same_pairs(advances.pair_rows(old, [1, 2, 4], "odd"), odd)
            if len(even) < 2 or not odd:
                raise ValueError("fixed paired population lost a phase response")
            origin = float(np.mean([pair["midpoint_s"] for pair in even]))
            scale = row["observation"]["historical_rf_normalization_scale"]
            for pairs, target in ((even, calibration), (odd, response)):
                times = np.asarray([pair["midpoint_s"] for pair in pairs])
                duration = np.asarray([pair["duration_s"] for pair in pairs])
                p, v, valid = cfo.replay.state_arrays(
                    catalogue,
                    list(range(len(norad))),
                    binding["historical_inventory"]["reference_utc_ns"],
                    times,
                )
                if not np.array_equal(valid, np.arange(len(norad))):
                    raise ValueError("candidate propagation failed")
                phase = 2 * np.pi * cfo.doppler_hz(receiver, p, v) / scale * duration
                target.append(
                    {
                        "measured": np.asarray([pair["phase_rad"] for pair in pairs]),
                        "prediction": np.vstack([np.zeros(len(pairs)), phase]),
                        "rate_phase": 2 * np.pi * (times - origin) * duration,
                        "weights": advances.group_weights(pairs),
                    }
                )
            training.append(row["outer_partition"] == "train")
            branch = row["branches"][row["selected_seed_index"]]
            folds = [
                frame["frame"]["odd"]
                for frame in branch["frames"]
                if frame["group_id"] in (1, 2, 4) and frame["frame"]["training_supported"]
            ]
            coherence.append(float(np.mean([fold["exact_coherence"] for fold in folds])))
        models = advances.fit_and_score(
            calibration, response, training, np.linspace(-5000, 5000, 401)
        )
        for identity, model in zip(["constant_rate", *norad], models, strict=True):
            model["candidate"] = identity
        winner = 1 + int(np.argmax([model["training_score"] for model in models[1:]]))
        results.append(
            {
                "variant": label,
                "models": models,
                "training_selected_candidate": models[winner]["candidate"],
                "selected_vs_constant_rate": advances.paired_bootstrap(
                    models[winner]["held_visit_scores"], models[0]["held_visit_scores"]
                ),
                "held_exact_coherence": float(
                    np.mean(np.asarray(coherence)[~np.asarray(training)])
                ),
            }
        )
    output = {
        "schema": "longarc-timing-sensitivity/v1",
        "outer_seed": binding["seed"],
        "training_visits": sum(training),
        "held_visits": len(training) - sum(training),
        "variant_selection_on_held": False,
        "results": results,
        "source_sha256": digest(__file__),
        "frames_sha256": digest(OUTPUT / "frames.json.gz"),
    }
    (OUTPUT / "evaluation.json").write_text(json.dumps(output, indent=2) + "\n")
    for row in results:
        print({key: value for key, value in row.items() if key != "models"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--limit", type=int, default=78)
    args = parser.parse_args()
    evaluate() if args.evaluate else extract(args.limit)
