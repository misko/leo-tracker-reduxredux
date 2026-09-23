"""Compare four archived continuous GLRT branches using metadata only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from leo.analysis.starlink.kalman_tracking import canonical_digest
from tools import report_glrt_phase_segment_comparison as evidence_reader

ROOT = Path(__file__).resolve().parents[4]
OUTPUT = Path(__file__).with_name("continuous-branch-discrimination.json")
BULK_ROOT = Path("/srv/bulk/leo")
SESSION = "cap-20260825T010019-89c2889553e0"
RUN = "capture-34471d9087a94ec1b043951350de3956"
INTERVAL = (31.8, 32.625)
SAMPLE_RATE_HZ = 2_500_000
FRAME_PERIOD_SAMPLES = SAMPLE_RATE_HZ / 750
ALIAS_PERIOD_HZ = 1 / 4.4e-6
BRANCHES = {
    "rx0_selected": (
        "sha256:b6c2f8f86668304044c5c41903004b13a37d94328762172d83577cce4c41170b",
        "sha256:be34d146cfec9d9fe8b1fd1a73e2dd2c0fa6cc3931eed839f24d8539bcaae69d",
    ),
    "rx0_secondary": (
        "sha256:b6c2f8f86668304044c5c41903004b13a37d94328762172d83577cce4c41170b",
        "sha256:799f42467ed5a262172b2bf9c514722ce76de01d3893eed727e82ade6572868e",
    ),
    "rx1_selected": (
        "sha256:deec3913863c3241497d7c81c48d3891a601e7b9dd823a06088b6c3a7210e885",
        "sha256:5f2716dd54e070caeac4cc1ea76b694bdea81a4694d9b70d25432e84b238e856",
    ),
    "rx1_secondary": (
        "sha256:deec3913863c3241497d7c81c48d3891a601e7b9dd823a06088b6c3a7210e885",
        "sha256:3b1281ab14c21bc0c8a468e760d573bc47cfd3cb7c489d6da5d5827d13641438",
    ),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wrap(value: float, period: float) -> float:
    return (value + period / 2) % period - period / 2


def associated_rows(track) -> list[dict]:
    canonical = {
        observation.observation_id: observation
        for observation in track.evidence.dealiased_bank.observations
    }
    source_ids = {
        source_id
        for observation_id in track.track.observation_ids
        for source_id in canonical[observation_id].source_observation_ids
    }
    rows = []
    for detection in track.evidence.pilot_scan["detections"]:
        sample_start = int(detection["sample_start"])
        time_s = sample_start / SAMPLE_RATE_HZ
        if not INTERVAL[0] <= time_s <= INTERVAL[1]:
            continue
        for candidate in detection["candidates"]:
            candidate_id = canonical_digest(
                {
                    "sample_start": sample_start,
                    "candidate_rank": candidate["rank"],
                    "method": "glrt64",
                }
            )
            if candidate_id not in source_ids:
                continue
            score = next(row for row in candidate["scores"] if row["method"] == "glrt64")
            rows.append(
                {
                    "sample_start": sample_start,
                    "time_s": time_s,
                    "candidate_rank": candidate["rank"],
                    "local_epoch_sample": candidate["local_epoch_sample"],
                    "tracking_cfo_hz": score["tracking_cfo_hz"],
                    "residual_cfo_hz": score["residual_cfo_hz"],
                    "exact_score": score["exact_score"],
                    "control_score": score["control_score"],
                    "margin": score["margin"],
                }
            )
    return sorted(rows, key=lambda row: (row["sample_start"], row["candidate_rank"]))


def unique_by_sample(rows: list[dict]) -> dict[int, dict]:
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["sample_start"], []).append(row)
    return {sample: values[0] for sample, values in grouped.items() if len(values) == 1}


def opportunity_accounting(rows: list[dict]) -> dict:
    counts: dict[int, int] = {}
    for row in rows:
        counts[row["sample_start"]] = counts.get(row["sample_start"], 0) + 1
    return {
        "probe_start_count": len(counts),
        "unique_association_probe_count": sum(count == 1 for count in counts.values()),
        "ambiguous_association_probe_count": sum(count > 1 for count in counts.values()),
        "ambiguous_probe_starts": sorted(sample for sample, count in counts.items() if count > 1),
    }


def compare(left: list[dict], right: list[dict]) -> dict:
    left_by_sample, right_by_sample = unique_by_sample(left), unique_by_sample(right)
    common = sorted(set(left_by_sample) & set(right_by_sample))
    rows = []
    for sample in common:
        lhs, rhs = left_by_sample[sample], right_by_sample[sample]
        cfo = rhs["tracking_cfo_hz"] - lhs["tracking_cfo_hz"]
        epoch = rhs["local_epoch_sample"] - lhs["local_epoch_sample"]
        rows.append(
            {
                "sample_start": sample,
                "time_s": sample / SAMPLE_RATE_HZ,
                "left_candidate_rank": lhs["candidate_rank"],
                "right_candidate_rank": rhs["candidate_rank"],
                "raw_cfo_difference_hz": cfo,
                "alias_wrapped_cfo_difference_hz": wrap(cfo, ALIAS_PERIOD_HZ),
                "raw_epoch_difference_samples": epoch,
                "frame_wrapped_epoch_difference_samples": wrap(epoch, FRAME_PERIOD_SAMPLES),
            }
        )
    if len(rows) < 2:
        return {"matched_timestamp_count": len(rows), "rows": rows}
    return {
        "matched_timestamp_count": len(rows),
        "differential_cfo_alias_period_hz": ALIAS_PERIOD_HZ,
        "median_absolute_frame_wrapped_epoch_difference_samples": float(
            np.median(np.abs([row["frame_wrapped_epoch_difference_samples"] for row in rows]))
        ),
        "existing_two_sample_timing_gate_pass_count": sum(
            abs(row["frame_wrapped_epoch_difference_samples"]) <= 2 for row in rows
        ),
        "rows": rows,
    }


def build() -> dict:
    manifest, evidence = evidence_reader.load_path_evidence(BULK_ROOT, SESSION, RUN)
    tracks = evidence_reader.deduplicate_glrt_tracks(evidence)
    lookup = {(track.scope, track.branch_id): track for track in tracks}
    branch_rows = {name: associated_rows(lookup[key]) for name, key in BRANCHES.items()}
    comparisons = {}
    for left in ("rx0_selected", "rx0_secondary"):
        for right in ("rx1_selected", "rx1_secondary"):
            comparisons[f"{left}__{right}"] = compare(branch_rows[left], branch_rows[right])
    within_receiver = {
        "rx0_selected__rx0_secondary": compare(
            branch_rows["rx0_selected"], branch_rows["rx0_secondary"]
        ),
        "rx1_selected__rx1_secondary": compare(
            branch_rows["rx1_selected"], branch_rows["rx1_secondary"]
        ),
    }
    indexed = {name: unique_by_sample(rows) for name, rows in branch_rows.items()}
    simultaneous = sorted(set.intersection(*(set(rows) for rows in indexed.values())))
    closure_rows = []
    for sample in simultaneous:
        r0a = indexed["rx0_selected"][sample]
        r0b = indexed["rx0_secondary"][sample]
        r1a = indexed["rx1_selected"][sample]
        r1b = indexed["rx1_secondary"][sample]
        closure = (r1a["tracking_cfo_hz"] - r1b["tracking_cfo_hz"]) - (
            r0a["tracking_cfo_hz"] - r0b["tracking_cfo_hz"]
        )
        closure_rows.append(
            {
                "sample_start": sample,
                "time_s": sample / SAMPLE_RATE_HZ,
                "receiver_offset_closure_hz": closure,
                "closure_wrapped_full_alias_hz": wrap(closure, ALIAS_PERIOD_HZ),
                "closure_wrapped_half_alias_hz": wrap(closure, ALIAS_PERIOD_HZ / 2),
                "straight_pairing_epoch_offsets_samples": [
                    wrap(
                        r1a["local_epoch_sample"] - r0a["local_epoch_sample"],
                        FRAME_PERIOD_SAMPLES,
                    ),
                    wrap(
                        r1b["local_epoch_sample"] - r0b["local_epoch_sample"],
                        FRAME_PERIOD_SAMPLES,
                    ),
                ],
                "crossed_pairing_epoch_offsets_samples": [
                    wrap(
                        r1b["local_epoch_sample"] - r0a["local_epoch_sample"],
                        FRAME_PERIOD_SAMPLES,
                    ),
                    wrap(
                        r1a["local_epoch_sample"] - r0b["local_epoch_sample"],
                        FRAME_PERIOD_SAMPLES,
                    ),
                ],
            }
        )
    helper = Path(evidence_reader.__file__)
    return {
        "schema": "continuous-glrt-branch-discrimination/v1",
        "session_id": SESSION,
        "analysis_run_id": RUN,
        "run_manifest_identity": {
            "session_id": manifest["session_id"],
            "run_id": manifest["run_id"],
        },
        "fixed_interval_s": list(INTERVAL),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "frame_period_samples": FRAME_PERIOD_SAMPLES,
        "cfo_alias_period_hz": ALIAS_PERIOD_HZ,
        "branches": {
            name: {
                "scope": scope,
                "branch_id": branch,
                "associated_opportunity_count": len(branch_rows[name]),
                "opportunity_accounting": opportunity_accounting(branch_rows[name]),
                "rows": branch_rows[name],
            }
            for name, (scope, branch) in BRANCHES.items()
        },
        "within_receiver_comparisons": within_receiver,
        "cross_receiver_pairing_comparisons": comparisons,
        "simultaneity": {
            "rx0_two_branch_common_probe_count": len(
                set(indexed["rx0_selected"]) & set(indexed["rx0_secondary"])
            ),
            "rx1_two_branch_common_probe_count": len(
                set(indexed["rx1_selected"]) & set(indexed["rx1_secondary"])
            ),
            "all_four_branch_common_probe_count": len(simultaneous),
            "all_four_branch_common_probe_starts": simultaneous,
        },
        "common_receiver_offset_closure": {
            "definition": "(RX1 selected - RX1 secondary) - (RX0 selected - RX0 secondary)",
            "full_alias_period_hz": ALIAS_PERIOD_HZ,
            "half_alias_period_hz": ALIAS_PERIOD_HZ / 2,
            "existing_timing_gate_reference_samples": 2.0,
            "evaluable": bool(closure_rows),
            "unevaluable_reason": (
                None
                if closure_rows
                else "no probe start contains a unique associated candidate from all four branches"
            ),
            "rows": closure_rows,
        },
        "selection_note": (
            "All four predeclared pairings are retained. No pairing is selected by CFO, "
            "timing, score, or residual proximity."
        ),
        "interpretation": (
            "These are scoped trajectory-associated detection opportunities. Timing and CFO "
            "separation can distinguish archived hypotheses, but cannot alone establish "
            "physical source identity, cross-receiver pairing, or independent emitters. "
            "Wrapped epochs are local template coordinates, not verified common phase gauges. "
            "CFO differences are descriptive only: no alias path, unwrap, or fit is selected."
        ),
        "no_iq_read": True,
        "no_phase_refit": True,
        "source_sha256": {
            str(Path(__file__).relative_to(ROOT)): digest(Path(__file__)),
            str(helper.relative_to(ROOT)): digest(helper),
        },
    }


if __name__ == "__main__":
    if OUTPUT.exists():
        raise ValueError("fresh output path required")
    OUTPUT.write_text(json.dumps(build(), indent=2, allow_nan=False) + "\n")
