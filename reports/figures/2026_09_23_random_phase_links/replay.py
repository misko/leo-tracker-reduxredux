"""Replay the frozen 24 dwells with random whole-group phase validation.

Research only: the resulting score concerns a same-waveform receiver link. It
does not identify a satellite and does not interpret residual phase as geometry.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from pathlib import Path

import numpy as np

import leo.analysis.research.phase_association as phase_association_module
import leo.analysis.research.random_phase_validation as random_phase_module
import leo.analysis.starlink.broadband_alignment as broadband_alignment_module
from leo.analysis.research.phase_association import (
    HeldoutPhaseLinkEvidence,
    PhaseAssociationHypothesis,
    RandomGroupSplit,
    score_phase_association_hypotheses,
)
from leo.analysis.research.random_phase_validation import (
    extract_random_phase,
    random_phase_groups,
)
from leo.application.adaptive_relative_phase import relative_phase_probes
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopVisitAnalysisV1,
    DualRx10mAdaptiveHopVisitAnalysisV2,
    Feature103VisitAnalysisV3,
    Feature104VisitAnalysisV4,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore

ROOT = Path(__file__).resolve().parent
MULTIRATE = ROOT.parent / "2026_09_23_phase_multirate"
ANCHOR = ROOT.parent / "2026_09_23_scan_1aa_phase_methods"
CAPTURE_ROOT = Path("/srv/bulk/leo")
SEED = 20260923
VISIT_MODELS = {
    1: AdaptiveHopVisitAnalysisV1,
    2: DualRx10mAdaptiveHopVisitAnalysisV2,
    3: Feature103VisitAnalysisV3,
    4: Feature104VisitAnalysisV4,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replay_identity(selection_path: Path) -> dict:
    sources = {
        "phase_association": _sha256(Path(phase_association_module.__file__)),
        "random_phase_validation": _sha256(Path(random_phase_module.__file__)),
        "broadband_alignment": _sha256(Path(broadband_alignment_module.__file__)),
        "replay": _sha256(Path(__file__)),
    }
    protocol = {
        "seed": SEED,
        "grouping": "three-successive-40ms-strata-one-random-train-one-held-20ms-group-v1",
        "carrier_seed": "median-paired-GLRT-relative-CFO-from-wholly-contained-training-groups",
        "held_target": "B-conditioned-on-same-held-block-A",
        "waveform_gate": "extract_random_phase.supported",
        "selection_sha256": _sha256(selection_path),
        "sources": sources,
    }
    encoded = json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()
    return {
        "protocol": protocol,
        "protocol_sha256": hashlib.sha256(encoded).hexdigest(),
        "source_sha256": hashlib.sha256(
            json.dumps(sources, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _serial(value):
    if isinstance(value, dict):
        return {str(key): _serial(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serial(item) for item in value]
    if isinstance(value, np.ndarray):
        return _serial(value.tolist())
    if isinstance(value, np.generic):
        return _serial(value.item())
    return value


def _save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(_serial(value), separators=(",", ":"), allow_nan=False) + "\n"
    if path.suffix == ".gz":
        with gzip.open(path, "wt", compresslevel=6) as destination:
            destination.write(payload)
    else:
        path.write_text(payload)


def _load_checkpoint(path: Path) -> dict:
    with gzip.open(path, "rt") as source:
        return json.load(source)


def _load_comparison(session_id: str) -> dict:
    if session_id == "scan-fw-1aa1d50103d97388":
        path = ANCHOR / "comparison.json"
        return json.loads(path.read_text())
    path = MULTIRATE / session_id / "comparison.json.gz"
    with gzip.open(path, "rt") as source:
        return json.load(source)


def _load_inventory(session_id: str) -> dict:
    path = MULTIRATE / session_id / "inventory.json.gz"
    with gzip.open(path, "rt") as source:
        return json.load(source)


def _carrier_seed_hz(dense, split: dict, sample_rate_hz: int) -> tuple[float, list[dict]]:
    """Use only phase-blind paired probes wholly inside random training groups."""
    group_samples = int(split["group_samples"])
    train = set(split["training_groups"])
    probe_samples = sample_rate_hz * 20 // 1000
    retained = []
    for probe in relative_phase_probes(dense):
        start = int(probe.start_sample)
        group = start // group_samples
        if (
            group in train
            and start >= group * group_samples
            and start + probe_samples <= (group + 1) * group_samples
        ):
            retained.append(
                {
                    "group_id": group,
                    "start_sample": start,
                    "relative_cfo_hz": float(
                        probe.seeds[1].acquired_cfo_hz - probe.seeds[0].acquired_cfo_hz
                    ),
                }
            )
    if not retained:
        raise ValueError("no paired GLRT carrier seed lies wholly in a training group")
    return float(np.median([item["relative_cfo_hz"] for item in retained])), retained


def _association_score(session_id: str, visit: int, phase: dict) -> dict:
    split = phase["split"]
    held = phase["held_rows"]
    link_id = f"{session_id}:visit-{visit}:rx0-rx1"
    evidence = HeldoutPhaseLinkEvidence(
        link_id=link_id,
        split=RandomGroupSplit(
            seed=int(split["seed"]),
            training_group_ids=tuple(split["training_groups"]),
            heldout_group_ids=tuple(split["held_groups"]),
        ),
        residual_phase_rad=np.asarray([item["residual_phase_rad"] for item in held]),
        residual_group_id=np.asarray([item["group_id"] for item in held]),
        wrong_pair_phase_rad=np.asarray([item["wrong_residual_phase_rad"] for item in held]),
        wrong_pair_group_id=np.asarray([item["group_id"] for item in held]),
    )
    # The two shared-link labels stand in for arbitrary catalogue candidates
    # downstream. Equal output weights demonstrate that this phase observable
    # cannot alter their relative NORAD rank.
    hypotheses = (
        PhaseAssociationHypothesis("shared-link-candidate-a", frozenset({link_id})),
        PhaseAssociationHypothesis("shared-link-candidate-b", frozenset({link_id})),
        PhaseAssociationHypothesis("separate-receiver-episodes", frozenset()),
    )
    diagnostic = score_phase_association_hypotheses(hypotheses, (evidence,)).as_serializable()
    if phase["supported"]:
        applied = diagnostic["hypotheses"]
    else:
        applied = [
            {
                "hypothesis_id": item.hypothesis_id,
                "normalized_conditional_weight": 1.0 / len(hypotheses),
                "phase_log_factor": 0.0,
            }
            for item in hypotheses
        ]
    return {
        "waveform_gate_supported": bool(phase["supported"]),
        "phase_only_diagnostic": diagnostic,
        "applied_hypothesis_weights": applied,
    }


def run() -> None:
    selection_path = MULTIRATE / "selection.json"
    selections = json.loads(selection_path.read_text())
    identity = _replay_identity(selection_path)
    expected_count = sum(len(item["selected_visits"]) for item in selections)
    if expected_count != 24:
        raise ValueError(f"frozen selection contains {expected_count}, expected 24 dwells")
    output_rows = ROOT / "rows"
    started = time.monotonic()
    results = []
    captures = AdaptiveHopIqStore(CAPTURE_ROOT, read_only=True)
    try:
        for selection in selections:
            visits = selection["selected_visits"]
            if not visits:
                continue
            session_id = selection["session_id"]
            comparison = _load_comparison(session_id)
            inventory = _load_inventory(session_id)
            rows_by_visit = {int(item["visit"]): item for item in comparison["visits"]}
            if set(rows_by_visit) != set(visits):
                raise ValueError(
                    f"comparison inventory differs from frozen selection: {session_id}"
                )
            with AdaptiveHopAnalysisInputStore(captures).source(session_id) as source:
                if source.input_manifest_sha256 != inventory["input_manifest_sha256"]:
                    raise ValueError(f"capture manifest differs from inventory: {session_id}")
                ordinals = {
                    item.event.visit_index: index for index, item in enumerate(source.visits)
                }
                for visit in visits:
                    checkpoint = output_rows / f"{session_id}-visit-{visit}.json.gz"
                    if checkpoint.exists():
                        saved = _load_checkpoint(checkpoint)
                        if (
                            saved.get("protocol_sha256") == identity["protocol_sha256"]
                            and saved.get("source_sha256") == identity["source_sha256"]
                            and saved.get("input_manifest_sha256") == source.input_manifest_sha256
                        ):
                            results.append(saved)
                            continue
                    prior = rows_by_visit[visit]
                    result = {
                        "session_id": session_id,
                        "visit": visit,
                        "sample_rate_hz": int(selection["sample_rate_hz"]),
                        "seed": SEED,
                        "protocol_sha256": identity["protocol_sha256"],
                        "source_sha256": identity["source_sha256"],
                        "input_manifest_sha256": source.input_manifest_sha256,
                        "state": "abstained",
                    }
                    try:
                        iq = source.read_visit(ordinals[visit])
                        digest = hashlib.sha256(iq.tobytes()).hexdigest()
                        if digest != prior["iq_sha256"]:
                            raise ValueError("saved IQ digest differs from frozen phase replay")
                        dense_payload = prior["dense_glrt"]
                        dense = VISIT_MODELS[int(dense_payload["schema_version"])].model_validate(
                            dense_payload
                        )
                        rate = int(dense.configuration.sample_rate_hz)
                        if rate != result["sample_rate_hz"]:
                            raise ValueError("dense GLRT and frozen selection rates differ")
                        split = random_phase_groups(len(iq), rate, seed=SEED)
                        result["frozen_split"] = split
                        carrier_seed, seed_probes = _carrier_seed_hz(dense, split, rate)
                        phase = extract_random_phase(
                            iq,
                            rate,
                            receiver_cfo_seed_hz=carrier_seed,
                            seed=SEED,
                        )
                        if phase["split"] != split:
                            raise ValueError("extractor changed the frozen random group assignment")
                        result.update(
                            state="replayed",
                            iq_sha256=digest,
                            carrier_seed_hz=carrier_seed,
                            carrier_seed_probes=seed_probes,
                            random_phase=phase,
                            association_research_score=_association_score(session_id, visit, phase),
                        )
                    except Exception as error:
                        result["reason"] = f"{type(error).__name__}: {error}"
                    _save(checkpoint, result)
                    results.append(result)
                    print(session_id, visit, result["state"], flush=True)
                    _save(
                        ROOT / "comparison.json.gz",
                        {
                            "seed": SEED,
                            "selection_sha256": hashlib.sha256(
                                selection_path.read_bytes()
                            ).hexdigest(),
                            **identity,
                            "expected_dwell_count": expected_count,
                            "elapsed_s": time.monotonic() - started,
                            "rows": results,
                        },
                    )
    finally:
        captures.close()
    _save(
        ROOT / "comparison.json.gz",
        {
            "seed": SEED,
            "selection_sha256": hashlib.sha256(selection_path.read_bytes()).hexdigest(),
            **identity,
            "expected_dwell_count": expected_count,
            "elapsed_s": time.monotonic() - started,
            "rows": results,
        },
    )


if __name__ == "__main__":
    run()
