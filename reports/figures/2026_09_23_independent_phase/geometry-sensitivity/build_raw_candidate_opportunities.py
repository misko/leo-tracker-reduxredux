"""Screen archived raw pilot candidates for simultaneous distinct hypotheses."""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

from tools import report_glrt_phase_segment_comparison as reader

ROOT = Path(__file__).resolve().parents[4]
OUTPUT = Path(__file__).with_name("raw-candidate-opportunities.json")
BULK_ROOT = Path("/srv/bulk/leo")
SESSION = "cap-20260825T010019-89c2889553e0"
RUN = "capture-34471d9087a94ec1b043951350de3956"
SCOPES = {
    0: "sha256:b6c2f8f86668304044c5c41903004b13a37d94328762172d83577cce4c41170b",
    1: "sha256:deec3913863c3241497d7c81c48d3891a601e7b9dd823a06088b6c3a7210e885",
}
SAMPLE_RATE_HZ = 2_500_000.0
FRAME_PERIOD_SAMPLES = SAMPLE_RATE_HZ / 750.0
NATIVE_ALIAS_PERIOD_HZ = 1.0 / 4.4e-6
TIMING_GATE_SAMPLES = 2.0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wrap(value: float, period: float) -> float:
    return (value + period / 2.0) % period - period / 2.0


def glrt(candidate: dict) -> dict:
    return next(score for score in candidate["scores"] if score["method"] == "glrt64")


def components(rows: list[dict], frequency_gate_hz: float) -> list[list[dict]]:
    parents = list(range(len(rows)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for right in range(len(rows)):
        for left in range(right):
            epoch_close = abs(
                wrap(
                    rows[right]["local_epoch_sample"] - rows[left]["local_epoch_sample"],
                    FRAME_PERIOD_SAMPLES,
                )
            ) <= TIMING_GATE_SAMPLES
            frequency_close = abs(
                wrap(
                    rows[right]["tracking_cfo_hz"] - rows[left]["tracking_cfo_hz"],
                    NATIVE_ALIAS_PERIOD_HZ,
                )
            ) <= frequency_gate_hz
            if epoch_close and frequency_close:
                a, b = find(left), find(right)
                parents[b] = a
    result: dict[int, list[dict]] = {}
    for index, row in enumerate(rows):
        result.setdefault(find(index), []).append(row)
    return [result[key] for key in sorted(result)]


def timing_matchings(left: list[list[dict]], right: list[list[dict]]) -> list[dict]:
    matches = []
    for left_components in itertools.combinations(range(len(left)), 2):
        for right_components in itertools.combinations(range(len(right)), 2):
            for permutation in itertools.permutations(right_components):
                member_matches = []
                for left_index, right_index in zip(left_components, permutation, strict=True):
                    pairs = []
                    for left_row in left[left_index]:
                        for right_row in right[right_index]:
                            offset = wrap(
                                right_row["local_epoch_sample"]
                                - left_row["local_epoch_sample"],
                                FRAME_PERIOD_SAMPLES,
                            )
                            if abs(offset) <= TIMING_GATE_SAMPLES:
                                pairs.append(
                                    {
                                        "rx0_candidate_rank": left_row["candidate_rank"],
                                        "rx1_candidate_rank": right_row["candidate_rank"],
                                        "timing_offset_samples": offset,
                                    }
                                )
                    member_matches.append(pairs)
                matches.append(
                    {
                        "rx0_component_indices": list(left_components),
                        "rx1_component_indices": list(permutation),
                        "both_pairs_timing_compatible": all(member_matches),
                        "compatible_candidate_members_by_pair": member_matches,
                    }
                )
    return matches


def build() -> dict:
    manifest, evidence = reader.load_path_evidence(BULK_ROOT, SESSION, RUN)
    by_scope = {row.scope: row for row in evidence}
    inventory = {}
    for product in manifest["products"]:
        key = (product.get("scope_key"), product.get("kind"))
        inventory[key] = product

    threshold_by_receiver = {}
    frequency_gate_by_receiver = {}
    accounting_digests = {}
    qualified = {}
    counts = {}
    for receiver, scope in SCOPES.items():
        product = inventory[(scope, "standard.trajectory-conditioned-accounting")]
        payload = reader._bulk_uri_path(BULK_ROOT, product["logical_uri"]).read_bytes()
        if "sha256:" + hashlib.sha256(payload).hexdigest() != product["digest"]:
            raise ValueError("accounting product digest mismatch")
        document = json.loads(payload)
        configuration = document["configuration"]
        threshold_by_receiver[receiver] = float(configuration["positive_margin"])
        frequency_gate_by_receiver[receiver] = float(configuration["association_gate_hz"])
        accounting_digests[receiver] = product["digest"]
        rows_by_probe = {}
        raw_multi = 0
        for detection in by_scope[scope].pilot_scan["detections"]:
            rows = []
            for candidate in detection["candidates"]:
                score = glrt(candidate)
                if score["margin"] < threshold_by_receiver[receiver]:
                    continue
                rows.append(
                    {
                        "candidate_rank": int(candidate["rank"]),
                        "local_epoch_sample": float(candidate["local_epoch_sample"]),
                        "tracking_cfo_hz": float(score["tracking_cfo_hz"]),
                        "exact_score": float(score["exact_score"]),
                        "control_score": float(score["control_score"]),
                        "margin": float(score["margin"]),
                    }
                )
            raw_multi += len(rows) >= 2
            rows_by_probe[int(detection["sample_start"])] = components(
                rows, float(configuration["association_gate_hz"])
            )
        qualified[receiver] = rows_by_probe
        counts[receiver] = {
            "passing_candidate_count": sum(
                len(component)
                for probe in rows_by_probe.values()
                for component in probe
            ),
            "probe_count_with_at_least_one_passing_candidate": sum(
                bool(probe) for probe in rows_by_probe.values()
            ),
            "probe_count_with_at_least_two_passing_candidates_before_collapse": raw_multi,
            "probe_count_with_at_least_two_components": sum(
                len(probe) >= 2 for probe in rows_by_probe.values()
            ),
        }

    starts = sorted(
        sample
        for sample in qualified[0].keys() & qualified[1].keys()
        if len(qualified[0][sample]) >= 2 and len(qualified[1][sample]) >= 2
    )
    opportunities = []
    for sample in starts:
        matchings = timing_matchings(qualified[0][sample], qualified[1][sample])
        opportunities.append(
            {
                "sample_start": sample,
                "time_s": sample / SAMPLE_RATE_HZ,
                "receiver_components": {
                    "0": qualified[0][sample],
                    "1": qualified[1][sample],
                },
                "one_to_one_component_matchings": matchings,
                "any_two_pair_timing_compatible_matching": any(
                    row["both_pairs_timing_compatible"] for row in matchings
                ),
            }
        )
    source = Path(__file__)
    helper = Path(reader.__file__)
    return {
        "schema": "raw-pilot-candidate-opportunities/v1",
        "session_id": SESSION,
        "analysis_run_id": RUN,
        "stream_id": "stream-1",
        "screening_policy": {
            "margin_rule": "glrt64 exact_score - control_score >= positive_margin",
            "positive_margin_by_receiver": {
                str(key): value for key, value in threshold_by_receiver.items()
            },
            "threshold_authority": (
                "Persisted standard.trajectory-conditioned-accounting/v2 configuration; "
                "this screens raw candidates and was not an ingestion gate in pilot-scan/v3."
            ),
            "accounting_product_digest_by_receiver": {
                str(key): value for key, value in accounting_digests.items()
            },
        },
        "diagnostic_collapse": {
            "epoch_gate_samples_modulo_frame": TIMING_GATE_SAMPLES,
            "frequency_gate_hz_modulo_native_alias_by_receiver": {
                str(key): value for key, value in frequency_gate_by_receiver.items()
            },
            "native_alias_period_hz": NATIVE_ALIAS_PERIOD_HZ,
            "policy": (
                "Connected components under both existing gates; descriptive grouping, not "
                "an archived candidate deduplication contract."
            ),
        },
        "counts_by_receiver": {str(key): value for key, value in counts.items()},
        "simultaneous_two_component_probe_count": len(opportunities),
        "timing_compatible_two_pair_probe_count": sum(
            row["any_two_pair_timing_compatible_matching"] for row in opportunities
        ),
        "opportunities": opportunities,
        "interpretation": (
            "All passing candidate members are retained. Cross-receiver matchings use timing "
            "only and do not select by CFO, score, or phase; timing compatibility is not source "
            "identity authority. Six isolated probes are discovery material, not a long arc."
        ),
        "no_iq_read": True,
        "no_phase_refit": True,
        "source_product_digests_by_receiver": {
            str(receiver): by_scope[scope].source_digests
            for receiver, scope in SCOPES.items()
        },
        "source_sha256": {
            str(source.relative_to(ROOT)): sha256(source),
            str(helper.relative_to(ROOT)): sha256(helper),
        },
    }


if __name__ == "__main__":
    if OUTPUT.exists():
        raise ValueError("fresh output path required")
    OUTPUT.write_text(json.dumps(build(), indent=2, allow_nan=False) + "\n")
