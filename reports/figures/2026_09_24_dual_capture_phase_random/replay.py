"""Replay the September 24 dual-RX cohort with random group validation.

The replay is read-only with respect to saved captures and production products.
It ranks visits using phase-blind GLRT margin, then evaluates a seeded random
whole-group split.  Frequency band A in a held block supplies local phase while
disjoint band B is the response.  No chronological holdout is used.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

import leo.analysis.research.random_phase_validation as random_phase_module
import leo.analysis.starlink.broadband_alignment as broadband_alignment_module
from leo.analysis.research.random_phase_validation import (
    extract_random_phase,
    random_phase_groups,
)
from leo.application.adaptive_relative_phase import (
    relative_phase_priority,
    relative_phase_probes,
)
from leo.scanner.adaptive_hop_analysis import analyze_adaptive_hop_visit
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore

ROOT = Path(__file__).resolve().parent
CAPTURE_ROOT = Path("/srv/bulk/leo")
GLOBAL_SEED = 20260924
SELECTED_VISITS_PER_SESSION = 8


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _serial(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _serial(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serial(item) for item in value]
    if isinstance(value, np.ndarray):
        return _serial(value.tolist())
    if isinstance(value, np.generic):
        return _serial(value.item())
    return value


def _save_gzip(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    with gzip.open(temporary, "wt", compresslevel=6) as destination:
        json.dump(_serial(value), destination, separators=(",", ":"), allow_nan=False)
        destination.write("\n")
    temporary.replace(path)


def _load_gzip(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt") as source:
        return json.load(source)


def dwell_seed(session_id: str, visit_index: int, global_seed: int = GLOBAL_SEED) -> int:
    """Derive one stable independent uint32 seed for a session visit."""
    payload = f"{global_seed}:{session_id}:{visit_index}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def carrier_seed_hz(
    dense: Any, split: dict[str, Any], sample_rate_hz: int
) -> tuple[float, list[dict[str, Any]]]:
    """Use only paired phase-blind GLRT probes wholly in training groups."""
    group_samples = int(split["group_samples"])
    training_groups = set(split["training_groups"])
    probe_samples = sample_rate_hz * 20 // 1000
    retained: list[dict[str, Any]] = []
    for probe in relative_phase_probes(dense):
        start = int(probe.start_sample)
        group = start // group_samples
        if (
            group in training_groups
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
    return float(np.median([row["relative_cfo_hz"] for row in retained])), retained


def _protocol(cohort_path: Path) -> dict[str, Any]:
    sources = {
        "random_phase_validation": _sha256(Path(random_phase_module.__file__)),
        "broadband_alignment": _sha256(Path(broadband_alignment_module.__file__)),
        "replay": _sha256(Path(__file__)),
    }
    document = {
        "global_seed": GLOBAL_SEED,
        "per_dwell_seed": "first-uint32-sha256(global_seed:session_id:visit_index)",
        "selection": (
            f"top {SELECTED_VISITS_PER_SESSION} visits per session by phase-blind paired GLRT "
            "fractional-margin floor"
        ),
        "grouping": "seeded 50/50 complete 20ms groups stratified over each 120ms dwell",
        "held_target": "disjoint band B conditioned on band A in the same random-held block",
        "waveform_gate": "tracked coherence > max(0.05, 3*wrong-pair) and held residual R > 0.8",
        "chronological_holdout_used": False,
        "cohort_sha256": _sha256(cohort_path),
        "sources": sources,
    }
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return {"document": document, "sha256": hashlib.sha256(encoded).hexdigest()}


def _session_result(
    specification: dict[str, Any],
    captures: AdaptiveHopIqStore,
    analyses: AdaptiveHopAnalysisStore,
    protocol: dict[str, Any],
    rows_root: Path,
) -> dict[str, Any]:
    session_id = specification["session_id"]
    result: dict[str, Any] = {
        **specification,
        "state": "analysis_unavailable",
        "selected_visit_count": 0,
        "replayed_visit_count": 0,
        "supported_visit_count": 0,
        "visits": [],
    }
    capture = captures.inspect(session_id)
    if capture.manifest_sha256 != specification["input_manifest_sha256"]:
        raise ValueError(f"capture manifest differs from frozen cohort: {session_id}")
    receipt = capture.manifest.receipt
    geometry = receipt.plan.geometry
    if geometry.sample_rate_hz != 2_500_000 or tuple(geometry.receiver_ids) != (0, 1):
        raise ValueError(f"capture is not frozen 2.5 MS/s dual RX: {session_id}")
    result.update(
        created_utc_ns=int(capture.manifest.created_utc_ns),
        finalized_utc_ns=int(capture.manifest.finalized_utc_ns),
        complete_visit_count=int(receipt.complete_visit_count),
        valid_duty_ppm=int(receipt.valid_duty_ppm),
        receipt_schema_version=int(receipt.schema_version),
        sample_rate_hz=int(geometry.sample_rate_hz),
    )
    binding = bind_actual_visit_analysis(
        receipt,
        input_manifest_sha256=capture.manifest_sha256,
        probe_stride_ms=120,
    )
    with analyses.job(binding) as metrics:
        manifest = metrics.manifest()
        if manifest is None:
            result["reason"] = "sealed GLRT metrics unavailable at replay time"
            return result
        indexes = metrics.completed_visits()
        if len(indexes) != receipt.complete_visit_count:
            result["reason"] = (
                f"GLRT coverage incomplete: {len(indexes)} of {receipt.complete_visit_count} visits"
            )
            return result
        ranked = []
        for index in indexes:
            priority = relative_phase_priority(metrics.read_visit(index))
            if priority is not None:
                ranked.append((-float(priority), int(index)))
    selected = [
        {"visit_index": index, "phase_blind_priority": -negative_priority}
        for negative_priority, index in sorted(ranked)[:SELECTED_VISITS_PER_SESSION]
    ]
    result["phase_blind_candidate_visit_count"] = len(ranked)
    result["selected_visit_count"] = len(selected)
    if not selected:
        result.update(state="complete_no_phase_blind_candidates", reason="no paired GLRT visits")
        return result

    dense_configuration = binding.configuration.model_copy(update={"probe_stride_ms": 20})
    with AdaptiveHopAnalysisInputStore(captures).source(session_id) as source:
        if source.input_manifest_sha256 != specification["input_manifest_sha256"]:
            raise ValueError(f"analysis source differs from frozen cohort: {session_id}")
        ordinals = {visit.event.visit_index: ordinal for ordinal, visit in enumerate(source.visits)}
        for selection in selected:
            visit_index = selection["visit_index"]
            checkpoint = rows_root / f"{session_id}-visit-{visit_index:06d}.json.gz"
            if checkpoint.exists():
                saved = _load_gzip(checkpoint)
                if (
                    saved.get("protocol_sha256") == protocol["sha256"]
                    and saved.get("input_manifest_sha256") == source.input_manifest_sha256
                ):
                    result["visits"].append(saved)
                    continue
            row: dict[str, Any] = {
                **selection,
                "session_id": session_id,
                "radio_id": specification["radio_id"],
                "input_manifest_sha256": source.input_manifest_sha256,
                "protocol_sha256": protocol["sha256"],
                "state": "abstained",
            }
            try:
                ordinal = ordinals[visit_index]
                iq = source.read_visit(ordinal)
                dense = analyze_adaptive_hop_visit(
                    source,
                    ordinal,
                    configuration=dense_configuration,
                )
                seed = dwell_seed(session_id, visit_index)
                split = random_phase_groups(len(iq), dense_configuration.sample_rate_hz, seed=seed)
                carrier_seed, seed_probes = carrier_seed_hz(
                    dense, split, dense_configuration.sample_rate_hz
                )
                phase = extract_random_phase(
                    iq,
                    dense_configuration.sample_rate_hz,
                    receiver_cfo_seed_hz=carrier_seed,
                    seed=seed,
                )
                if phase["split"] != split:
                    raise ValueError("extractor changed the frozen random split")
                row.update(
                    state="replayed",
                    target_index=int(dense.target_index),
                    channel=int(dense.target.channel),
                    edge=str(dense.target.edge),
                    dwell_seed=seed,
                    iq_sha256=hashlib.sha256(iq.tobytes()).hexdigest(),
                    carrier_seed_hz=carrier_seed,
                    carrier_seed_probes=seed_probes,
                    random_phase=phase,
                )
            except Exception as error:  # replay must retain every abstention
                row["reason"] = f"{type(error).__name__}: {error}"[:1024]
            _save_gzip(checkpoint, row)
            result["visits"].append(row)
            print(session_id, visit_index, row["state"], flush=True)
    result["replayed_visit_count"] = sum(row["state"] == "replayed" for row in result["visits"])
    result["supported_visit_count"] = sum(
        row["state"] == "replayed" and row["random_phase"]["supported"] for row in result["visits"]
    )
    result["state"] = "complete"
    return result


def run(cohort_path: Path, output_path: Path, rows_root: Path) -> None:
    cohort = json.loads(cohort_path.read_text())
    protocol = _protocol(cohort_path)
    captures = AdaptiveHopIqStore(CAPTURE_ROOT, read_only=True)
    analyses = AdaptiveHopAnalysisStore(CAPTURE_ROOT, read_only=True)
    started = time.monotonic()
    sessions = []
    try:
        for specification in cohort["sessions"]:
            try:
                session = _session_result(specification, captures, analyses, protocol, rows_root)
            except Exception as error:
                session = {
                    **specification,
                    "state": "analysis_unavailable",
                    "selected_visit_count": 0,
                    "replayed_visit_count": 0,
                    "supported_visit_count": 0,
                    "visits": [],
                    "reason": f"{type(error).__name__}: {error}"[:1024],
                }
                print(specification["session_id"], session["state"], flush=True)
            sessions.append(session)
            _save_gzip(
                output_path,
                {
                    "schema_version": 1,
                    "cohort": cohort,
                    "protocol": protocol,
                    "elapsed_s": time.monotonic() - started,
                    "sessions": sessions,
                },
            )
    finally:
        analyses.close()
        captures.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, default=ROOT / "cohort.json")
    parser.add_argument("--output", type=Path, default=ROOT / "comparison.json.gz")
    parser.add_argument("--rows", type=Path, default=ROOT / "rows")
    arguments = parser.parse_args()
    run(arguments.cohort, arguments.output, arguments.rows)


if __name__ == "__main__":
    main()
