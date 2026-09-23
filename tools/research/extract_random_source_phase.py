"""Bounded source-seeded frame phase extraction on three frozen adaptive dwells."""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

import leo.analysis.qam.pilot as pilot_module
import leo.analysis.starlink.templates as template_module
from leo.analysis.qam.pilot import estimate_edge_pilot_frame_complex_split
from leo.analysis.research.random_phase_validation import random_phase_groups
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S
from leo.application.adaptive_dual_rx_phase_v2 import _phase_blind_pairs
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopVisitAnalysisV1,
    DualRx10mAdaptiveHopVisitAnalysisV2,
    Feature103VisitAnalysisV3,
    Feature104VisitAnalysisV4,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore

ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / "reports/figures"
OUTPUT = FIGURES / "2026_09_23_source_phase_random"
SEED = 20260923
MODELS = {
    1: AdaptiveHopVisitAnalysisV1,
    2: DualRx10mAdaptiveHopVisitAnalysisV2,
    3: Feature103VisitAnalysisV3,
    4: Feature104VisitAnalysisV4,
}


def serial(value):
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [serial(v) for v in value]
    if isinstance(value, np.ndarray):
        return serial(value.tolist())
    if isinstance(value, complex):
        return [value.real, value.imag]
    if isinstance(value, np.generic):
        return serial(value.item())
    return value


def select_training_branch(branches):
    """Select a local GLRT seed using equal-weight training-even margins only."""
    scores = []
    for rows in branches:
        groups = sorted({r["group_id"] for r in rows if r["partition"] == "train"})
        if not groups:
            raise ValueError("branch selection requires training groups")
        scores.append(
            float(
                np.mean(
                    [
                        np.mean(
                            [
                                r["frame"]["even"]["coherence_margin"]
                                if r["frame"]["even"] and not r["frame"]["even"]["search_boundary"]
                                else 0.0
                                for r in rows
                                if r["partition"] == "train" and r["group_id"] == group
                            ]
                        )
                        for group in groups
                    ]
                )
            )
        )
    return int(np.argmax(scores)), scores


def run():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    selection_path = FIGURES / "2026_09_23_phase_multirate/selection.json"
    selections = json.loads(selection_path.read_text())
    frozen = []
    for selection in selections:
        if not selection["selected_visits"]:
            continue
        session = selection["session_id"]
        path = (
            FIGURES / "2026_09_23_scan_1aa_phase_methods/comparison.json"
            if selection["sample_rate_hz"] == 2500000
            else FIGURES / "2026_09_23_phase_multirate" / session / "comparison.json.gz"
        )
        with gzip.open(path, "rt") if path.suffix == ".gz" else path.open() as source:
            comparison = json.load(source)
        candidates = []
        for row in comparison["visits"]:
            dense = row["dense_glrt"]
            visit = MODELS[dense["schema_version"]].model_validate(dense)
            rate = visit.configuration.sample_rate_hz
            split = random_phase_groups(row["iq_shape"][0], rate, seed=SEED)
            # Detection selection is frozen using training-group GLRT only.
            for group in split["training_groups"]:
                subset = visit.model_copy(
                    update={"probes": tuple(p for p in visit.probes if p.probe_index == group)}
                )
                for left, right, _, start in _phase_blind_pairs(subset):
                    quality = min(left.fractional_margin, right.fractional_margin)
                    candidates.append(
                        (quality, row["visit"], group, start, left, right, row, split)
                    )
        quality, index, group, start, left, right, row, split = max(
            candidates, key=lambda c: (c[0], -c[1], -c[2])
        )
        frozen.append(
            dict(
                session_id=session,
                visit=index,
                sample_rate_hz=rate,
                training_probe=group,
                probe_start=start,
                quality=quality,
                candidates=[left.model_dump(mode="json"), right.model_dump(mode="json")],
                iq_sha256=row["iq_sha256"],
                split=split,
                edge=row["dense_glrt"]["target"]["edge"],
                comparison_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    manifest = dict(
        seed=SEED,
        selection_sha256=hashlib.sha256(selection_path.read_bytes()).hexdigest(),
        rule="one maximum training-only paired GLRT margin per rate from frozen 24",
        source_specificity="one frozen timing/CFO source hypothesis, no decoded identity",
        branch_policy=(
            "acquired and refined GLRT seeds; equal-group training-even "
            "exact-control margin; boundary score zero"
        ),
        epoch_policy=(
            "integer GLRT lattice; fractional epoch retained in "
            "candidate metadata but not corrected"
        ),
        validation_scope="retrospective development comparison; previously inspected recordings",
        source_sha256={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), Path(pilot_module.__file__), Path(template_module.__file__))
        },
        selections=frozen,
    )
    (OUTPUT / "selection.json").write_text(json.dumps(manifest, indent=2) + "\n")
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    results = []
    try:
        for item in frozen:
            with AdaptiveHopAnalysisInputStore(store).source(item["session_id"]) as source:
                ordinal = next(
                    i for i, v in enumerate(source.visits) if v.event.visit_index == item["visit"]
                )
                iq = source.read_visit(ordinal)
                assert hashlib.sha256(iq.tobytes()).hexdigest() == item["iq_sha256"]
                rate = item["sample_rate_hz"]
                content = round(302 * rate * OFDM_SYMBOL_DURATION_S)
                rows = []
                alternatives = []
                for receiver, candidate in enumerate(item["candidates"]):
                    epoch = item["probe_start"] + candidate["integer_epoch_sample"]
                    opportunities = []
                    for offset in range(-100, 101):
                        start = epoch + round(offset * rate / 750)
                        group = start // item["split"]["group_samples"]
                        low = group * item["split"]["group_samples"]
                        high = low + item["split"]["group_samples"]
                        if (
                            start < 1
                            or start + content + 1 > len(iq)
                            or start - 1 < low
                            or start + content + 1 > high
                        ):
                            continue
                        opportunities.append((start, group))
                    seeds = list(
                        dict.fromkeys(
                            [candidate["acquired_cfo_hz"], candidate["fractional_tracking_cfo_hz"]]
                        )
                    )
                    branches = []
                    for seed in seeds:
                        branch = []
                        for start, group in opportunities:
                            observation = estimate_edge_pilot_frame_complex_split(
                                iq[start - 1 : start + content + 1, receiver],
                                rate,
                                frame_start_sample=start,
                                acquisition_absolute_cfo_hz=seed,
                                edge=item["edge"],
                            )
                            branch.append(
                                dict(
                                    receiver_id=receiver,
                                    group_id=group,
                                    partition="train"
                                    if group in item["split"]["training_groups"]
                                    else "held",
                                    frame=serial(asdict(observation)),
                                )
                            )
                        branches.append(branch)
                    chosen, scores = select_training_branch(branches)
                    rows.extend(branches[chosen])
                    alternatives.append(
                        dict(
                            receiver_id=receiver,
                            seed_cfo_hz=seeds,
                            selected_branch_index=chosen,
                            training_even_margin=scores,
                            frames_by_branch=branches,
                        )
                    )
                result = dict(
                    selection=item,
                    input_manifest_sha256=source.input_manifest_sha256,
                    frames=rows,
                    seed_alternatives=alternatives,
                )
                results.append(result)
                print(
                    item["session_id"],
                    item["visit"],
                    len(rows),
                    sum(r["frame"]["training_supported"] for r in rows),
                    flush=True,
                )
                with gzip.open(OUTPUT / "frames.json.gz", "wt") as out:
                    json.dump(
                        serial(dict(manifest=manifest, results=results)), out, allow_nan=False
                    )
    finally:
        store.close()


if __name__ == "__main__":
    run()
