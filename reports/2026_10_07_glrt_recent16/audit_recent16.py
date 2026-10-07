"""Independent oracles on saved recent16 audit banks; no evaluator/scorer imports."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis.starlink.pilot_methods import _glrt_pair, _SymbolCorrelations

EXPECTED_SEGMENT_SHA256 = "06c341391596c60dc885a5fafdcd4c169614dfe96a3492fff77c2f84fd2a7b33"
HERE = Path(__file__).resolve().parent
SEGMENT_SOURCE = HERE.parent / "2026_10_07_glrt_segment_followup/segment_methods.py"
SCORE_TOLERANCE = 1e-12
CFO_TOLERANCE_HZ = 1e-6
SYMBOL_STEP_S = 4.4e-6
_KERNEL = np.exp(-np.abs(np.arange(64)[:, None] - np.arange(64)[None, :]) / 32)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def direct_gaussian(raw, energy, frequency):
    """Unknown complex amplitude per frame: minimize whitened residual energy."""
    observed = (raw / np.sqrt(energy)).T
    steering = (np.sqrt(energy) * np.exp(2j * np.pi * frequency * np.arange(64) * SYMBOL_STEP_S))[
        :, None
    ]
    amplitude = np.linalg.lstsq(steering, observed, rcond=None)[0]
    residual = observed - steering @ amplitude
    total = float(np.sum(np.abs(observed) ** 2))
    return 1 - float(np.sum(np.abs(residual) ** 2)) / total if total > 0 else 0.0


def direct_kernel(raw, energy, frequency):
    """Direct Toeplitz quadratic, independent of FFT/autocorrelation scoring."""
    rotated = raw * np.exp(-2j * np.pi * frequency * np.arange(64) * SYMBOL_STEP_S)
    numerator = sum(float(np.vdot(frame, _KERNEL @ frame).real) for frame in rotated)
    denominator = float(energy.sum() * np.sum(np.abs(raw) ** 2 / energy))
    return numerator / denominator if denominator > 0 else 0.0


def audit_bank(case, arrays):
    """Audit chosen/baseline later hypotheses and every first current64 candidate."""
    evaluation = case["evaluation"]
    bank = case["candidate_bank"]
    ids = [row["candidate_id"] for row in bank]
    if not ids or len(ids) != len(set(ids)) or len(ids) != evaluation["candidate_count"]:
        raise ValueError("candidate inventory identity/count mismatch")
    by_id = {row["candidate_id"]: i for i, row in enumerate(bank)}
    energy = [
        np.asarray(arrays[name], dtype=float)
        for name in ("exact_template_energy", "control_template_energy")
    ]
    if any(
        value.shape != (64,) or not np.all(np.isfinite(value)) or np.any(value <= 0)
        for value in energy
    ):
        raise ValueError("invalid actual template energies")
    matrices = {}
    for wi in (0, 1):
        for index, identifier in enumerate(ids):
            pair = tuple(
                np.asarray(arrays[f"w{wi}_c{index}_{name}"]) for name in ("exact", "control")
            )
            if (
                pair[0].ndim != 2
                or pair[0].shape != pair[1].shape
                or pair[0].shape[1] != 64
                or len(pair[0]) < 1
                or not all(np.all(np.isfinite(value)) for value in pair)
            ):
                raise ValueError("invalid cached matrix support")
            matrices[wi, identifier] = pair
    errors, counts = {}, {}

    def compare(key, observed, expected):
        if not np.isfinite(observed) or not np.isfinite(expected):
            raise ValueError("nonfinite audit statistic")
        errors[key] = max(errors.get(key, 0.0), abs(float(observed) - float(expected)))
        counts[key] = counts.get(key, 0) + 1

    def identity(winner):
        if winner["candidate_id"] not in by_id:
            raise ValueError("chosen candidate not in original bank")
        metadata = bank[by_id[winner["candidate_id"]]]
        for field in ("candidate_rank", "epoch_sample", "seed_cfo_hz"):
            if winner[field] != metadata[field]:
                raise ValueError(f"candidate {field} changed")
        compare(
            "total_cfo_hz",
            winner["total_cfo_hz"],
            metadata["seed_cfo_hz"] + winner["residual_cfo_hz"],
        )

    baseline = evaluation["baseline_winner"]
    if baseline != evaluation["methods"]["current_coherent_margin"]["winner"]:
        raise ValueError("baseline winner identity differs from current method")
    identity(baseline)
    fixed_cache = {}

    def direct_metrics(winner):
        key = winner["candidate_id"], winner["residual_cfo_hz"]
        if key not in fixed_cache:
            pair = matrices[1, key[0]]
            values = {}
            for name, oracle in (("gaussian", direct_gaussian), ("phase_kernel32", direct_kernel)):
                exact = oracle(pair[0], energy[0], key[1])
                control = oracle(pair[1], energy[1], key[1])
                values[name] = dict(
                    exact_score=exact, control_score=control, margin=exact - control
                )
            fixed_cache[key] = values
        return fixed_cache[key]

    reference = direct_metrics(baseline)
    for item in evaluation["methods"].values():
        winner = item["winner"]
        identity(winner)
        identifier = winner["candidate_id"]
        if item["first_frame_count"] != len(matrices[0, identifier][0]):
            raise ValueError("first frame count mismatch")
        if item["later_frame_count"] != len(matrices[1, identifier][0]):
            raise ValueError("later frame count mismatch")
        if len(item["ranking"]) != len(ids) or {
            row["candidate_id"] for row in item["ranking"]
        } != set(ids):
            raise ValueError("method ranking omitted candidate identity")
        if winner != item["ranking"][0]:
            raise ValueError("method winner differs from first-ranked candidate")
        direct = direct_metrics(winner)
        for metric, direct_item in direct.items():
            stored = item["common_confirmation"][metric]
            for field, value in direct_item.items():
                compare(f"later_{metric}_winner_{field}", stored["winner"][field], value)
                compare(
                    f"later_{metric}_baseline_{field}",
                    stored["baseline"][field],
                    reference[metric][field],
                )
            compare(
                f"later_{metric}_margin_difference",
                stored["margin_difference"],
                direct_item["margin"] - reference[metric]["margin"],
            )
    ranking = evaluation["methods"]["current_coherent_margin"]["ranking"]
    baseline_oracle_scores = {}
    for candidate in ranking:
        identity(candidate)
        identifier = candidate["candidate_id"]
        exact, control = matrices[0, identifier]
        times = np.broadcast_to(np.arange(64) * SYMBOL_STEP_S, exact.shape)
        result = _glrt_pair(
            _SymbolCorrelations(exact, np.zeros_like(times), times),
            _SymbolCorrelations(control, np.zeros_like(times), times),
            size=512,
        )
        for field, value in (
            ("exact_score", result[0][0]),
            ("control_score", result[1][0]),
            ("score", result[0][0] - result[1][0]),
            ("residual_cfo_hz", result[0][1]),
            ("control_residual_cfo_hz", result[1][1]),
        ):
            compare("first_current_" + field, candidate[field], value)
        baseline_oracle_scores[identifier] = result[0][0] - result[1][0]
    winner_deficit = (
        max(baseline_oracle_scores.values()) - baseline_oracle_scores[baseline["candidate_id"]]
    )
    compare("first_current_winner_score_deficit", winner_deficit, 0.0)
    hash_matches = evaluation["frozen_scorer_sha256"] == EXPECTED_SEGMENT_SHA256
    passed = hash_matches and all(
        error < (CFO_TOLERANCE_HZ if key.endswith("cfo_hz") else SCORE_TOLERANCE)
        for key, error in errors.items()
    )
    return dict(
        case_id=case["case_id"],
        label=case["label"],
        passed=bool(passed),
        candidates=len(bank),
        methods=len(evaluation["methods"]),
        fixed_hypotheses=len(fixed_cache),
        max_absolute_errors=errors,
        comparison_counts=counts,
        frozen_scorer_hash_matches=hash_matches,
    )


def audit_directory(root, *, require_complete=False, expected_scans=16):
    root = Path(root)
    started = time.perf_counter()
    banks, failures = [], []
    source_matches = digest(SEGMENT_SOURCE) == EXPECTED_SEGMENT_SHA256
    for path in sorted(root.glob("R*/audit-v*-rx*.npz")):
        try:
            case = json.loads(path.with_suffix(".json").read_text())
            with np.load(path, allow_pickle=False) as arrays:
                result = audit_bank(case, arrays)
            result.update(
                matrices_sha256=digest(path), case_json_sha256=digest(path.with_suffix(".json"))
            )
            banks.append(result)
        except (OSError, KeyError, ValueError) as error:
            failures.append(dict(path=str(path), error=f"{type(error).__name__}: {error}"))
    receipts = [json.loads(path.read_text()) for path in sorted(root.glob("R*/receipt.json"))]
    completed = sum(receipt["status"] == "complete" for receipt in receipts)
    scanned_labels = sorted({bank["label"] for bank in banks})
    maxima, totals = {}, {}
    for bank in banks:
        for key, value in bank["max_absolute_errors"].items():
            maxima[key] = max(maxima.get(key, 0.0), value)
        for key, value in bank["comparison_counts"].items():
            totals[key] = totals.get(key, 0) + value
    complete = completed == expected_scans and len(scanned_labels) == expected_scans
    passed = (
        bool(banks) and source_matches and not failures and all(bank["passed"] for bank in banks)
    )
    if require_complete:
        passed = passed and complete
    return dict(
        schema="org.leo.research.recent16-independent-numerical-audit/v1",
        passed=bool(passed),
        provisional=not complete,
        expected_scans=expected_scans,
        completed_scan_receipts=completed,
        audited_scans=scanned_labels,
        audited_banks=len(banks),
        expected_maximum_audit_banks=expected_scans * 6,
        frozen_segment_sha256=EXPECTED_SEGMENT_SHA256,
        frozen_segment_hash_matches=source_matches,
        tolerances=dict(score_absolute=SCORE_TOLERANCE, cfo_absolute_hz=CFO_TOLERANCE_HZ),
        oracle_descriptions=dict(
            gaussian="Direct complex least-squares residual minimization",
            phase_kernel32="Direct dense Toeplitz quadratic at identical fixed exact/control CFO",
            current64="Production _glrt_pair on identical cached first-window frame support",
        ),
        max_absolute_errors=maxima,
        comparison_counts=totals,
        failures=failures,
        banks=banks,
        elapsed_seconds=round(time.perf_counter() - started, 4),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=HERE / "local/full")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    result = audit_directory(args.root, require_complete=args.require_complete)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("passed", "provisional", "audited_banks", "elapsed_seconds")
            }
        )
    )
    if not result["passed"]:
        raise SystemExit("independent numerical audit failed; inspect receipt")
