"""Seal metadata for a historical long-arc pilot replay; never reads IQ."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from leo.application.persistent_hop_trajectory import fractional_glrt64_support_geometry
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

SESSION = "scan-fw-f0af018448538a4c"
TRACK = "sha256:2807453f686c4475c19b1ddec248184f049acfaa3d2d3d0fbcfee5c62958846d"
CACHE_INDEX = 443
SEED = 20260923
PILOT_ALIAS_SECONDS = 4.4e-6


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def fresh_whole_visit_partition(observations: list[dict]) -> dict:
    """Make a reproducible phase split without reusing the old point split."""
    ordered = sorted(observations, key=lambda item: item["time_s"])
    rng = np.random.default_rng(SEED)
    rows = []
    # Six contiguous time strata retain arc coverage in both halves.  A visit is
    # indivisible: a later frame extractor must put every frame from it here.
    for stratum, block in enumerate(np.array_split(np.arange(len(ordered)), 6)):
        chosen = set(rng.permutation(block)[: (len(block) + 1) // 2].tolist())
        for index in block:
            rows.append(
                {
                    "visit_index": ordered[int(index)]["visit_index"],
                    "time_s": ordered[int(index)]["time_s"],
                    "temporal_stratum": stratum,
                    "partition": "train" if int(index) in chosen else "held",
                }
            )
    train = {row["visit_index"] for row in rows if row["partition"] == "train"}
    held = {row["visit_index"] for row in rows if row["partition"] == "held"}
    if len(rows) != len(train | held) or train & held:
        raise ValueError("whole-visit partition is not disjoint")
    return {
        "policy": "seeded-random-whole-visit-with-six-temporal-strata/v1",
        "seed": SEED,
        "unit": (
            "visit_index; all observations and later IQ frames from a visit follow its partition"
        ),
        "rows": rows,
        "training_visit_indices": sorted(train),
        "held_visit_indices": sorted(held),
    }


def bind(*, root: Path, evidence: Path, cache: Path) -> dict:
    document = json.loads(evidence.read_text())
    inventory = document["inventory"]
    row = next(x for x in document["series"] if x["tracklet_id"] == TRACK)
    episode = next(x for x in document["episodes"] if x["episode_id"] == TRACK)
    if episode["members"] != [TRACK] or inventory["session_id"] != SESSION:
        raise ValueError("unexpected historical episode")
    archive = np.load(cache, allow_pickle=False)
    if str(archive[f"session_id_{CACHE_INDEX}"].item()) != SESSION:
        raise ValueError("cache episode/session mismatch")
    ids, times, values = row["candidate_ids"], row["t_s"], row["y_hz"]
    if len(ids) != 78 or len(ids) != len(set(ids)) or len(times) != len(values):
        raise ValueError("historical source observations are not unique")
    # This is the historical randomized *point* split, retained only for
    # provenance.  It is deliberately not reused by the phase replay.
    cache_times = archive[f"time_s_{CACHE_INDEX}"]
    cache_values = archive[f"observed_{CACHE_INDEX}"]
    cache_train = archive[f"training_{CACHE_INDEX}"].astype(bool)
    assignment = []
    for time, value in zip(times, values, strict=True):
        hit = np.flatnonzero(
            (np.abs(cache_times - time) < 1e-8) & (np.abs(cache_values - value) < 1e-5)
        )
        if len(hit) != 1:
            raise ValueError("historical evidence does not bind uniquely to cached episode")
        assignment.append(bool(cache_train[int(hit[0])]))

    iq = AdaptiveHopIqStore(root, read_only=True)
    tracking = ScannerTrackingInputStore(root)
    analysis = None
    try:
        published = iq.inspect(SESSION)
        receipt = published.manifest.receipt
        retained = receipt.retained_visit_indices
        if tuple(retained) != tuple(range(receipt.terminal.visits_started)):
            raise ValueError("cannot equate visit index and saved-IQ ordinal")
        binding = bind_actual_visit_analysis(
            receipt, input_manifest_sha256=published.manifest_sha256, probe_stride_ms=120
        )
        analysis = AdaptiveHopAnalysisStore(root, read_only=True)
        source = tracking.load(SESSION)
        if (
            source.input_manifest_sha256 != inventory["capture_digest"]
            or source.analysis_manifest_sha256 != inventory["analysis_digest"]
        ):
            raise ValueError("public source does not bind historical capture/analysis")
        by_time = []
        for probe in source.probes:
            if (
                probe.receiver_id != 0
                or probe.channel != 4
                or probe.edge != "lower"
                or probe.probe_index != 0
            ):
                continue
            supported = [
                candidate
                for candidate in probe.candidates
                if candidate.passed_fractional_margin_gate
            ]
            if not supported:
                continue
            # The support center belongs to a probe.  Multiple retained candidate
            # ranks can share that same center and CFO, so time alone must not
            # pretend to select a rank.
            geometry = fractional_glrt64_support_geometry(
                supported[0],
                sample_rate_hz=source.sample_rate_hz,
                probe_sample_count=source.sample_rate_hz * source.probe_ms // 1000,
            )
            time = (
                probe.valid_start_counter
                - receipt.terminal.first_counter
                + probe.probe_start_ms * source.sample_rate_hz // 1000
                + geometry.center_in_probe_samples
            ) / source.sample_rate_hz
            by_time.append((time, probe, supported))
        bound = []
        for ident, time, value, train in zip(ids, times, values, assignment, strict=True):
            hit = [x for x in by_time if abs(x[0] - time) < 1e-8]
            if len(hit) != 1:
                raise ValueError("time does not have one exact public source candidate")
            _, probe, candidates = hit[0]
            scale = float(row["actual_rf_hz"]) / probe.actual_rf_hz
            alias_period = (1.0 / PILOT_ALIAS_SECONDS) * scale
            compatible = []
            for candidate in candidates:
                difference = value - candidate.fractional_tracking_cfo_hz * scale
                alias_index = int(round(difference / alias_period))
                residual = difference - alias_index * alias_period
                if abs(residual) <= 1e-3:
                    compatible.append((candidate, alias_index, residual))
            if not compatible:
                raise ValueError("no source candidate agrees after RF-normalized pilot alias")
            # Same-CFO tied ranks are retained as an explicit ambiguity.  The
            # lowest rank is a representative only; acquisition seeds must agree.
            compatible.sort(key=lambda item: item[0].candidate_rank)
            candidate, alias_index, residual = compatible[0]
            bound.append(
                dict(
                    candidate_id=ident,
                    time_s=time,
                    normalized_cfo_hz=value,
                    historical_randomized_point_training=train,
                    visit_index=probe.visit_index,
                    iq_ordinal=probe.visit_index,
                    receiver_id=probe.receiver_id,
                    channel=probe.channel,
                    edge=probe.edge,
                    probe_index=probe.probe_index,
                    probe_start_ms=probe.probe_start_ms,
                    valid_start_counter=probe.valid_start_counter,
                    source_actual_rf_hz=probe.actual_rf_hz,
                    integer_epoch_sample=candidate.integer_epoch_sample,
                    representative_candidate_rank=candidate.candidate_rank,
                    source_compatible_candidate_ranks=[x[0].candidate_rank for x in compatible],
                    fractional_epoch_offset_samples=candidate.fractional_epoch_offset_samples,
                    fractional_tracking_cfo_hz=candidate.fractional_tracking_cfo_hz,
                )
            )
        # Read only the public visit-analysis product.  Native candidate rank plus
        # the exact tracking fields is the stable source-to-analysis join.
        with analysis.job(binding) as job:
            for item in bound:
                visit = job.read_visit(item["visit_index"])
                candidates = [
                    c
                    for p in visit.probes
                    if p.receiver_id == item["receiver_id"] and p.probe_index == item["probe_index"]
                    for c in p.candidates
                    if c.candidate_rank == item["representative_candidate_rank"]
                    and c.integer_epoch_sample == item["integer_epoch_sample"]
                    and abs(
                        c.fractional_epoch_offset_samples - item["fractional_epoch_offset_samples"]
                    )
                    < 1e-12
                    and abs(c.fractional_tracking_cfo_hz - item["fractional_tracking_cfo_hz"])
                    < 1e-7
                ]
                if len(candidates) != 1:
                    raise ValueError("source candidate does not bind uniquely to visit analysis")
                item["acquired_cfo_hz"] = candidates[0].acquired_cfo_hz
                # The historical y is normalized at its exported RF; convert the
                # source tracking CFO likewise, then resolve its known 4.4-us
                # pilot alias.  This is provenance reconciliation, not phase data.
                item["historical_rf_normalization_scale"] = scale
                item["historical_pilot_alias_period_hz"] = alias_period
                item["historical_pilot_alias_index"] = alias_index
                item["historical_alias_residual_hz"] = residual
                if abs(item["historical_alias_residual_hz"]) > 1e-3:
                    raise ValueError(
                        "historical CFO does not agree after RF-normalized pilot alias"
                    )
        timing = published.manifest.timing
        partition = fresh_whole_visit_partition(bound)
        return dict(
            schema="longarc-phase-source-binding/v1",
            seed=SEED,
            historical_evidence_path=str(evidence),
            historical_evidence_sha256=digest(evidence),
            session_id=SESSION,
            tracklet_id=TRACK,
            episode_cache_index=CACHE_INDEX,
            historical_inventory=inventory,
            historical_series=row,
            historical_episode=episode,
            candidate_bank_path=str(cache),
            candidate_bank_sha256=digest(cache),
            cache_catalogue_digest=str(archive[f"catalogue_digest_{CACHE_INDEX}"].item()),
            cache_candidate_norads=[int(x) for x in archive[f"norad_{CACHE_INDEX}"]],
            cache_winner_norad=int(archive[f"winner_norad_{CACHE_INDEX}"].item()),
            sample_rate_hz=source.sample_rate_hz,
            source_capture_digest=source.input_manifest_sha256,
            source_analysis_digest=source.analysis_manifest_sha256,
            source_input_manifest_sha256=published.manifest_sha256,
            iq_ordinal_basis=(
                "all 2137 visit indices are retained in order, so iq_ordinal equals visit_index"
            ),
            source_first_counter=receipt.terminal.first_counter,
            first_sample_estimate_utc_ns=timing.first_sample_estimate_utc_ns,
            first_sample_earliest_utc_ns=timing.first_sample_earliest_utc_ns,
            first_sample_latest_utc_ns=timing.first_sample_latest_utc_ns,
            absolute_utc_mapping=(
                "first_sample_estimate_utc_ns + "
                "(valid_start_counter-first_counter+frame_sample_offset)/sample_rate_hz"
            ),
            historical_candidate_ids_preserved=True,
            historical_candidate_id_reproduction=(
                "unavailable: historical V11 projection provenance differs"
            ),
            current_public_time_binding="exact support-center equality",
            current_public_cfo_binding=(
                "all rows agree after per-probe RF normalization and integer "
                "4.4-us pilot-alias resolution"
            ),
            historical_split_provenance=(
                "inventory partition=randomized; preserved per point only, "
                "never used for phase replay"
            ),
            phase_random_whole_visit_partition=partition,
            observations=bound,
        )
    finally:
        if analysis is not None:
            analysis.close()
        tracking.close()
        iq.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path("/tmp/leo-sky-position-48h/evidence-v2/evidence") / f"{SESSION}.json",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path(
            "reports/artifacts/2026_09_21_shared_identity_orbit/candidate-phase-states.npz"
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bind(root=args.root, evidence=args.evidence, cache=args.cache), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
