"""Pure-array, fixed-hypothesis comparison on an unfiltered archived integer bank.

The adapter owns raw readers, scan/visit identity, archived completeness, and
coverage/failure receipts. This evaluator selects each method's winner using only
first-window evidence. Later arrays retain the same candidate timing and acquired
CFO seeds. Both exact and control are evaluated at the winner's frozen residual
CFO. Gaussian and kernel32 confirmation margins use identical metrics for every
method's hypothesis and the current baseline hypothesis; scores are statistics.
"""

from __future__ import annotations

import hashlib
import importlib.util
import math
import sys
import time
from numbers import Integral
from pathlib import Path

import numpy as np

FROZEN_SOURCE = Path(__file__).resolve().parents[1] / (
    "2026_10_07_glrt_segment_followup/segment_methods.py"
)
FROZEN_SOURCE_SHA256 = hashlib.sha256(FROZEN_SOURCE.read_bytes()).hexdigest()
_spec = importlib.util.spec_from_file_location("recent16_frozen_segment_methods", FROZEN_SOURCE)
_scorer = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _scorer
_spec.loader.exec_module(_scorer)

PRIMARY_METHODS = (
    "current_coherent_margin",
    "gaussian_coherent",
    "segment8",
    "segment16",
    "segment32",
    "phase_kernel32",
)
_PERSISTED_FIELDS = {
    "exact_score": "persisted_integer_exact_score",
    "control_score": "persisted_integer_control_score",
    "score": "persisted_integer_margin",
    "total_cfo_hz": "persisted_integer_tracking_cfo_hz",
}


def _integer(value, name):
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(value)


def _candidate(item, index):
    identifier = item.get("candidate_id", item.get("id", item.get("rank")))
    if isinstance(identifier, bool) or not isinstance(identifier, (Integral, str)):
        raise ValueError("candidate requires an integer/string candidate_id, id, or rank")
    if isinstance(identifier, Integral):
        identifier = int(identifier)
    rank = _integer(item.get("candidate_rank", item.get("rank", index)), "candidate rank")
    epoch = _integer(item["epoch_sample"], "epoch_sample")
    seed = float(item["seed_cfo_hz"])
    if not math.isfinite(seed):
        raise ValueError("seed CFO must be finite")
    return dict(candidate_id=identifier, candidate_rank=rank, epoch_sample=epoch, seed_cfo_hz=seed)


def _pair(pair):
    if len(pair) != 2:
        raise ValueError("a candidate pair requires exact and control arrays")
    exact, control = (np.asarray(values, dtype=np.complex128) for values in pair)
    if exact.ndim != 2 or exact.shape[1] != 64 or exact.shape != control.shape or len(exact) < 1:
        raise ValueError("matched nonempty [frames,64] exact/control arrays required")
    if not np.all(np.isfinite(exact)) or not np.all(np.isfinite(control)):
        raise ValueError("correlation matrices must be finite")
    return exact, control


def _ranked_entry(candidate, score):
    if not all(math.isfinite(float(value)) for value in score.values()):
        raise ValueError("scorer returned nonfinite candidate statistics")
    return dict(
        candidate,
        score=float(score["score"]),
        exact_score=float(score["exact_score"]),
        control_score=float(score["control_score"]),
        residual_cfo_hz=float(score["cfo_hz"]),
        total_cfo_hz=float(candidate["seed_cfo_hz"] + score["cfo_hz"]),
        control_residual_cfo_hz=float(score["control_cfo_hz"]),
        control_total_cfo_hz=float(candidate["seed_cfo_hz"] + score["control_cfo_hz"]),
    )


def _common(item):
    if not all(math.isfinite(float(item[key])) for key in ("exact_score", "control_score")):
        raise ValueError("fixed scorer returned nonfinite confirmation statistics")
    return dict(
        exact_score=float(item["exact_score"]),
        control_score=float(item["control_score"]),
        margin=float(item["exact_score"] - item["control_score"]),
    )


def _baseline_comparison(bank, current):
    entries = []
    max_errors = {}
    counts = {}
    for metadata, score in zip(bank, current, strict=True):
        errors = {}
        available = any(metadata.get(field) is not None for field in _PERSISTED_FIELDS.values())
        compatible = metadata.get("persisted_integer_compatible", True) is True
        status = (
            "compared"
            if available and compatible
            else "incompatible"
            if available
            else "unavailable"
        )
        if status == "compared":
            for field, persisted_name in _PERSISTED_FIELDS.items():
                if metadata.get(persisted_name) is None:
                    continue
                persisted = float(metadata[persisted_name])
                if not math.isfinite(persisted):
                    raise ValueError("persisted integer statistics must be finite")
                error = abs(score[field] - persisted)
                errors[field] = error
                max_errors[field] = max(max_errors.get(field, 0.0), error)
                counts[field] = counts.get(field, 0) + 1
        entries.append(
            dict(candidate_id=score["candidate_id"], status=status, absolute_errors=errors)
        )
    return dict(
        entries=entries,
        max_absolute_errors=max_errors,
        compared_counts=counts,
        note="Archived integer scores only; fractional scores and incompatible supports excluded",
    )


def evaluate_bank(
    bank,
    first_pairs,
    later_pairs,
    *,
    exact_template_energy,
    control_template_energy,
    symbol_step_s=4.4e-6,
    fft_size=512,
):
    """Evaluate all 17 frozen statistics on one shared candidate inventory.

    Metadata: candidate_id/id/rank; epoch_sample; seed_cfo_hz (acquired, not
    tracking CFO). Optional persisted_integer_* score fields enable numerical
    comparison; persisted_integer_compatible=False explicitly excludes comparison.
    Each paired matrix uses original complete64-symbol frame support. Different
    candidates/windows may have different frame counts. Invalid evidence raises;
    adapters must persist an explicit failure rather than drop the source case.
    """
    began_wall, began_cpu = time.perf_counter(), time.process_time()
    if not bank or len(bank) != len(first_pairs) or len(bank) != len(later_pairs):
        raise ValueError("nonempty metadata/first/later banks must have identical lengths")
    if isinstance(fft_size, bool) or fft_size != 512:
        raise ValueError("recent16 comparison requires exactly 512 CFO bins")
    candidates = [_candidate(item, index) for index, item in enumerate(bank)]
    identifiers = [item["candidate_id"] for item in candidates]
    ranks = [item["candidate_rank"] for item in candidates]
    if len(set(identifiers)) != len(identifiers) or len(set(ranks)) != len(ranks):
        raise ValueError("candidate IDs and ranks must be unique")
    first = [_pair(pair) for pair in first_pairs]
    later = [_pair(pair) for pair in later_pairs]
    for energy in (exact_template_energy, control_template_energy):
        values = np.asarray(energy, dtype=float)
        if values.shape != (64,) or not np.all(np.isfinite(values)) or np.any(values <= 0):
            raise ValueError("actual template energies must be positive finite [64] vectors")
    kwargs = dict(
        exact_template_energy=exact_template_energy,
        control_template_energy=control_template_energy,
        symbol_step_s=symbol_step_s,
        fft_size=fft_size,
    )
    ranking = {}
    started = time.process_time()
    for candidate, pair in zip(candidates, first, strict=True):
        scores = _scorer.score_bank(*pair, **kwargs)
        for method, item in scores.items():
            ranking.setdefault(method, []).append(_ranked_entry(candidate, item))
    first_cpu = time.process_time() - started
    current = ranking["current_coherent_margin"]
    baseline_comparison = _baseline_comparison(bank, current)
    for rows in ranking.values():
        rows.sort(key=lambda item: (-item["score"], item["candidate_rank"]))
    baseline = ranking["current_coherent_margin"][0]
    index_by_id = {item["candidate_id"]: index for index, item in enumerate(candidates)}
    cached = {}

    def confirmation(winner):
        key = winner["candidate_id"], winner["residual_cfo_hz"]
        if key not in cached:
            cached[key] = _scorer.score_at_frequency(
                *later[index_by_id[winner["candidate_id"]]],
                cfo_hz=winner["residual_cfo_hz"],
                **kwargs,
            )
        return cached[key]

    started = time.process_time()
    baseline_fixed = confirmation(baseline)
    baseline_by_id = {item["candidate_id"]: item for item in ranking["current_coherent_margin"]}
    methods = {}
    for method, rows in ranking.items():
        winner = rows[0]
        index = index_by_id[winner["candidate_id"]]
        fixed = confirmation(winner)
        own = fixed[method]
        own_confirmation = dict(
            score=float(own["score"]),
            **_common(own),
            residual_cfo_hz=winner["residual_cfo_hz"],
            total_cfo_hz=winner["total_cfo_hz"],
        )
        common = {}
        for label, common_method in (
            ("gaussian", "gaussian_coherent"),
            ("phase_kernel32", "phase_kernel32"),
        ):
            selected_metric, baseline_metric = (
                _common(fixed[common_method]),
                _common(baseline_fixed[common_method]),
            )
            common[label] = dict(
                winner=selected_metric,
                baseline=baseline_metric,
                margin_difference=selected_metric["margin"] - baseline_metric["margin"],
            )
        delta = winner["total_cfo_hz"] - baseline["total_cfo_hz"]
        methods[method] = dict(
            winner=winner,
            ranking=rows,
            winner_agreement_with_current=winner["candidate_id"] == baseline["candidate_id"],
            winner_total_cfo_change_from_current_hz=delta,
            abs_winner_total_cfo_change_from_current_hz=abs(delta),
            same_candidate_max_abs_cfo_change_from_current_hz=max(
                abs(item["total_cfo_hz"] - baseline_by_id[item["candidate_id"]]["total_cfo_hz"])
                for item in rows
            ),
            first_frame_count=len(first[index][0]),
            later_frame_count=len(later[index][0]),
            own_fixed_confirmation=own_confirmation,
            common_confirmation=common,
        )
    confirmation_cpu = time.process_time() - started
    return dict(
        schema="org.leo.research.recent16-segment-bank-evaluation/v1",
        status="complete",
        candidate_count=len(bank),
        primary_methods=list(PRIMARY_METHODS),
        baseline_winner=baseline,
        methods=methods,
        baseline_comparison=baseline_comparison,
        source_frame_counts=[
            dict(candidate_id=item["candidate_id"], first=len(first[i][0]), later=len(later[i][0]))
            for i, item in enumerate(candidates)
        ],
        frozen_scorer_sha256=FROZEN_SOURCE_SHA256,
        cost=dict(
            first_scoring_process_cpu_s=first_cpu,
            fixed_confirmation_process_cpu_s=confirmation_cpu,
            total_process_cpu_s=time.process_time() - began_cpu,
            total_wall_s=time.perf_counter() - began_wall,
            unique_fixed_hypotheses=len(cached),
        ),
        interpretation="Unlabeled archived-candidate evidence; no calibrated RF ROC/recall claim",
    )
