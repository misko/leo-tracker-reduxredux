#!/usr/bin/env python3
"""Render the score-only final Doppler holdout publication supplement.

This tool is intentionally downstream of the immutable score ledger.  It has no
recording, IQ, estimator, propagation, or candidate-ranking imports.  It only
clarifies the already-frozen score and preserves the superseded first report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from leo.contracts.digests import canonical_digest  # noqa: E402

SOURCE_SCORE_PATH = Path("reports/figures/2026_08_26_final_doppler_holdout_attempt2-score.json")
SOURCE_SCORE_SHA256 = "sha256:490f36345fec7d494261d63f3b3cf9581a249bdca46d80c8b9e63baed3471d1f"
SOURCE_SCORE_DIGEST = "sha256:3316fb28e8bb421d8bfdec00d8598e456e4a6a1d94c61026cf8e5fc51e643c31"
SOURCE_SCORE_FREEZE_COMMIT = "34860820481487d8dcc64ff47ccbca536f8207fa"
SOURCE_SCORE_FREEZE_TREE = "df74a1793e6588ec9fa14b2eadd184098edb63cc"
ACTIVE_PROTOCOL_PATH = Path("config/analysis/final-doppler-holdout-satellite-protocol-v3.json")
ACTIVE_PROTOCOL_SHA256 = "sha256:cbc61509401c05a935fd82431640f18a8aa55e33a104b952d89e1f68fed4ed5e"

METHOD_ORDER = (
    "fixed_20ms_linear",
    "fixed_125ms_linear",
    "fixed_500ms_linear",
    "lean_500ms_quadratic",
)
METHOD_LABELS = {
    "fixed_20ms_linear": "Fixed 20 ms linear",
    "fixed_125ms_linear": "Fixed 125 ms linear",
    "fixed_500ms_linear": "Fixed 500 ms linear",
    "lean_500ms_quadratic": "Strict-past 500 ms quadratic",
}

SOURCE_ARTIFACTS = {
    "attempt1_markdown": (
        "reports/2026_08_26_final_doppler_holdout_attempt2_results.md",
        "sha256:6d2bb1c65030d24fe98bc3e9a0a70e67aa883ed63239aa1d0a9a90116dca4eca",
    ),
    "attempt1_command_log": (
        "reports/figures/2026_08_26_final_doppler_holdout_attempt2-report-command-output.log",
        "sha256:de492914265b04760491515c13afc46d22bc582a6b9e7a30173d59962f4b554b",
    ),
    "attempt1_forecast_png": (
        "reports/figures/2026_08_26_final_doppler_holdout_attempt2_report/forecast-method-rms.png",
        "sha256:c49446897b559db8a4cdcaf133c5f6bb2a7a8b6999af73c275a350b1272b6fa7",
    ),
    "attempt1_paired_png": (
        "reports/figures/2026_08_26_final_doppler_holdout_attempt2_report/paired-capture-rms.png",
        "sha256:aebc87b138afb01dfaef600511c25cf5595a5d47d309e8814cd125cefcabaf0c",
    ),
    "attempt1_association_png": (
        "reports/figures/2026_08_26_final_doppler_holdout_attempt2_report/"
        "association-heldout-rms.png",
        "sha256:5b5e017bdb0c323a5063ee76cc21432f969fb992d8c417dfb7ca79a558d8f410",
    ),
    "attempt1_evidence": (
        "reports/figures/2026_08_26_final_doppler_holdout_attempt2_report/"
        "report-attempt-1-evidence.json",
        "sha256:5bf6c75c054c56994129bf1de68870409471fc896dee8003bb5cb44c5d08b467",
    ),
    "response_evidence": (
        "reports/figures/2026_08_26_final_doppler_holdout_attempt2_odd_attachment/"
        "attach-attempt-2-success-evidence.json",
        "sha256:77823ac8ca1e9f7f0c1d3eaf5fbf39fdd752a78e65d2fd996a6cf3f8113a5cc8",
    ),
}

GATE_COLUMNS = (
    ("absolute_rank_one_heldout_odd_rms", "RMS <=100"),
    ("primary_baseline_rank_one_agreement", "Primary=base"),
    ("training_runner_margin_ratio", "Train margin"),
    ("heldout_rank_one_remains_best", "Heldout persists"),
    ("heldout_runner_margin_ratio", "Heldout margin"),
    ("wrong_time_empirical_p", "Wrong-time null"),
    ("permutation_empirical_p", "Permutation null"),
    ("at_least_2_rolling_origins_complete_and_stable", "Rolling stable"),
)


def _sha256_tag(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _load_json_without_duplicates(path: Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        output: dict[str, object] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError(f"duplicate JSON key in {path.name}: {key}")
            output[key] = value
        return output

    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def load_frozen_score(path: Path, *, repository_root: Path) -> dict[str, Any]:
    """Load the one immutable score authority and reject every substitution."""

    expected_path = (repository_root / SOURCE_SCORE_PATH).resolve()
    if path.resolve() != expected_path or _sha256_tag(path) != SOURCE_SCORE_SHA256:
        raise ValueError("publication score path or bytes differ from frozen authority")
    score = _load_json_without_duplicates(path)
    if not isinstance(score, dict) or score.get("schema") != (
        "org.leo.research.final-holdout-score/v1"
    ):
        raise ValueError("publication score schema is invalid")
    if score.get("score_digest") != SOURCE_SCORE_DIGEST or score["score_digest"] != (
        canonical_digest({key: value for key, value in score.items() if key != "score_digest"})
    ):
        raise ValueError("publication score semantic digest disagrees")
    if tuple(item.get("method") for item in score.get("scores", ())) != METHOD_ORDER:
        raise ValueError("publication method inventory/order drifted")
    association = score.get("association")
    if not isinstance(association, list) or len(association) != 10:
        raise ValueError("publication association inventory drifted")
    evaluable = [item for item in association if item.get("evaluable") is True]
    non_evaluable = [item for item in association if item.get("evaluable") is False]
    if (
        len(evaluable) != 8
        or len(non_evaluable) != 2
        or sum(bool(item["gate"]["recovered_track"]) for item in evaluable) != 8
        or sum(bool(item["gate"]["catalog_compatible"]) for item in evaluable) != 0
        or score.get("absolute_secure_norad") is not False
    ):
        raise ValueError("publication association headline drifted")
    denominator = score.get("response_status_denominator", {})
    if denominator.get("target_count") != 5_413 or denominator.get("common_accuracy") != 3_942:
        raise ValueError("publication denominator drifted")
    gate = score.get("quadratic_promotion_gate", {})
    if (
        gate.get("passed") is not False
        or gate.get("capture_wins") != 9
        or gate.get("capture_comparisons") != 10
    ):
        raise ValueError("publication promotion result drifted")
    return score


def verify_frozen_source_artifacts(*, repository_root: Path) -> None:
    """Prove the terse first report and sealed response evidence are unchanged."""

    if _sha256_tag(repository_root / SOURCE_SCORE_PATH) != SOURCE_SCORE_SHA256:
        raise ValueError("frozen score bytes drifted")
    if _sha256_tag(repository_root / ACTIVE_PROTOCOL_PATH) != ACTIVE_PROTOCOL_SHA256:
        raise ValueError("active v3 protocol bytes drifted")
    for label, (relative, expected) in SOURCE_ARTIFACTS.items():
        if _sha256_tag(repository_root / relative) != expected:
            raise ValueError(f"frozen source artifact drifted: {label}")


def _rank_one(score: dict[str, Any]) -> dict[str, Any]:
    rows = [item for item in score["scores"] if item.get("rank") == 1]
    if len(rows) != 1:
        raise ValueError("association score does not have exactly one rank-one candidate")
    return rows[0]


def _short_capture(session_id: str) -> str:
    match = re.search(r"T(\d{6})", session_id)
    return match.group(1) if match else session_id


def _yes_no(value: object) -> str:
    return "yes" if value is True else "no"


def _fmt(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def association_publication_rows(score: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract presentation rows without refitting or reordering candidates."""

    output: list[dict[str, Any]] = []
    for item in score["association"]:
        if item["evaluable"] is not True:
            output.append(
                {
                    "session_id": item["session_id"],
                    "evaluable": False,
                    "failure_reasons": tuple(item.get("failure_reasons", ())),
                }
            )
            continue
        gate = item["gate"]
        primary = _rank_one(item["primary"])
        baseline = _rank_one(item["baseline"])
        output.append(
            {
                "session_id": item["session_id"],
                "evaluable": True,
                "primary_candidate_id": primary["candidate_id"],
                "primary_training_rms_hz": primary["training_rms_hz"],
                "primary_heldout_rms_hz": primary["heldout_odd_rms_hz"],
                "baseline_candidate_id": baseline["candidate_id"],
                "baseline_training_rms_hz": baseline["training_rms_hz"],
                "baseline_heldout_rms_hz": baseline["heldout_odd_rms_hz"],
                "primary_baseline_agreement": gate["conditions"][
                    "primary_baseline_rank_one_agreement"
                ],
                "heldout_rank_one_remains_best": gate["conditions"][
                    "heldout_rank_one_remains_best"
                ],
                "wrong_time_empirical_p": gate["wrong_time_empirical_p"],
                "permutation_empirical_p": gate["permutation_empirical_p"],
                "rolling_stable": gate["conditions"][
                    "at_least_2_rolling_origins_complete_and_stable"
                ],
                "recovered_track": gate["recovered_track"],
                "catalog_compatible": gate["catalog_compatible"],
                "failed_conditions": tuple(gate["failed_conditions"]),
                "conditions": dict(gate["conditions"]),
            }
        )
    return output


def _method_table(score: dict[str, Any]) -> str:
    rows = []
    for method in score["scores"]:
        rows.append(
            "| {label} | {equal:.3f} | {pooled:.3f} | {complete:,}/{total:,} | "
            "{fraction:.2%} | {common:,} |".format(
                label=METHOD_LABELS[method["method"]],
                equal=method["equal_capture_rms_hz"],
                pooled=method["pooled_rms_hz"],
                complete=method["prediction_complete_count"],
                total=method["denominator_count"],
                fraction=method["completion_fraction"],
                common=method["common_accuracy_count"],
            )
        )
    return "\n".join(rows)


def _capture_method_table(score: dict[str, Any]) -> str:
    methods = {item["method"]: item for item in score["scores"]}
    captures_by_method = {
        method: {item["session_id"]: item for item in value["captures"]}
        for method, value in methods.items()
    }
    denominator = {
        item["session_id"]: item for item in score["response_status_denominator"]["captures"]
    }
    rows = []
    for session_id in denominator:
        values = {
            method: captures_by_method[method][session_id]["rms_hz"] for method in METHOD_ORDER
        }
        ratio = values["lean_500ms_quadratic"] / values["fixed_500ms_linear"]
        item = denominator[session_id]
        rows.append(
            "| `{capture}` | {targets:,} | {eligible:,} | {common:,} | {m20} | {m125} | "
            "{m500} | {quadratic} | {ratio:.3f} |".format(
                capture=_short_capture(session_id),
                targets=item["target_count"],
                eligible=item["accuracy_eligible"],
                common=item["common_accuracy"],
                m20=_fmt(values["fixed_20ms_linear"]),
                m125=_fmt(values["fixed_125ms_linear"]),
                m500=_fmt(values["fixed_500ms_linear"]),
                quadratic=_fmt(values["lean_500ms_quadratic"]),
                ratio=ratio,
            )
        )
    return "\n".join(rows)


def _denominator_table(score: dict[str, Any]) -> str:
    rows = []
    for item in score["response_status_denominator"]["captures"]:
        rows.append(
            "| `{session_id}` | {target_count:,} | {accuracy_eligible:,} | {boundary:,} | "
            "{no_support:,} | {missing:,} | {common_accuracy:,} |".format(**item)
        )
    return "\n".join(rows)


def _association_table(rows: list[dict[str, Any]]) -> str:
    output = []
    for item in rows:
        if not item["evaluable"]:
            continue
        failed = "<br>".join(item["failed_conditions"])
        output.append(
            "| `{capture}` | `{primary}` | {ptrain} | {phold} | `{baseline}` | {btrain} | "
            "{bhold} | {agree} | {persist} | {wrong:.3f} | {perm:.3f} | {rolling} | "
            "**FAIL** | {failed} |".format(
                capture=_short_capture(item["session_id"]),
                primary=item["primary_candidate_id"],
                ptrain=_fmt(item["primary_training_rms_hz"]),
                phold=_fmt(item["primary_heldout_rms_hz"]),
                baseline=item["baseline_candidate_id"],
                btrain=_fmt(item["baseline_training_rms_hz"]),
                bhold=_fmt(item["baseline_heldout_rms_hz"]),
                agree=_yes_no(item["primary_baseline_agreement"]),
                persist=_yes_no(item["heldout_rank_one_remains_best"]),
                wrong=item["wrong_time_empirical_p"],
                perm=item["permutation_empirical_p"],
                rolling=_yes_no(item["rolling_stable"]),
                failed=failed,
            )
        )
    return "\n".join(output)


def _non_evaluable_table(rows: list[dict[str, Any]]) -> str:
    return "\n".join(
        "| `{capture}` | retained, not evaluable | {reasons} |".format(
            capture=_short_capture(item["session_id"]),
            reasons=", ".join(item["failure_reasons"]),
        )
        for item in rows
        if not item["evaluable"]
    )


def _association_aggregate_table(
    score: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    evaluable = [item for item in rows if item["evaluable"]]
    source_evaluable = [item for item in score["association"] if item["evaluable"]]
    population_counts = [len(item["primary"]["scores"]) for item in source_evaluable]
    stable_authority_controls = sum(
        item["conditions"]["utc_site_predecessor_controls_complete_and_stable"]
        for item in evaluable
    )
    values = (
        ("Frozen visible-candidate populations", ", ".join(map(str, population_counts))),
        ("Recovered response tracks", f"{sum(item['recovered_track'] for item in evaluable)}/8"),
        (
            "Primary/baseline rank-one agreement",
            f"{sum(item['primary_baseline_agreement'] for item in evaluable)}/8",
        ),
        (
            "Training winner remains best held out",
            f"{sum(item['heldout_rank_one_remains_best'] for item in evaluable)}/8",
        ),
        (
            "Wrong-time empirical-p gate passes",
            f"{sum(item['conditions']['wrong_time_empirical_p'] for item in evaluable)}/8",
        ),
        (
            "Permutation empirical-p gate passes",
            f"{sum(item['conditions']['permutation_empirical_p'] for item in evaluable)}/8",
        ),
        (
            "At least two rolling origins stable",
            f"{sum(item['rolling_stable'] for item in evaluable)}/8",
        ),
        (
            "Required permutation family fully scored",
            f"{sum(item['conditions']['required_permutations_scored'] for item in evaluable)}/8",
        ),
        (
            "UTC/site/predecessor controls complete and stable",
            f"{stable_authority_controls}/8",
        ),
        (
            "Full catalog-compatibility gate passes",
            f"{sum(item['catalog_compatible'] for item in evaluable)}/8",
        ),
    )
    return "\n".join(f"| {label} | {value} |" for label, value in values)


def _shared_rate_table(score: dict[str, Any]) -> str:
    sensitivity = score["shared_physical_radio_rate_sensitivity"]["sensitivity"]
    return "\n".join(
        f"| `{radio}` | {float(rate):+.4f} |"
        for radio, rate in zip(
            sensitivity["physical_radio_ids"],
            sensitivity["rate_departures_hz_s"],
            strict=True,
        )
    )


def build_detailed_markdown(
    score: dict[str, Any],
    *,
    markdown_path: Path,
    forecast_figure: Path,
    paired_figure: Path,
    corrected_association_figure: Path,
    gate_matrix_figure: Path,
    publication_manifest: Path,
) -> str:
    """Build the detailed publication text from already-scored fields only."""

    def link(path: Path) -> str:
        return Path(os.path.relpath(path, markdown_path.parent)).as_posix()

    gate = score["quadratic_promotion_gate"]
    denominator = score["response_status_denominator"]
    association_rows = association_publication_rows(score)
    shared = score["shared_physical_radio_rate_sensitivity"]["sensitivity"]
    availability = next(
        item
        for item in denominator["captures"]
        if item["session_id"] == "cap-20260825T034929-bc0480bdb4a8"
    )
    capture_header = (
        "| Capture (UTC key) | Targets | Eligible odd | Common n | 20 ms RMS | "
        "125 ms RMS | 500 ms RMS | Quadratic RMS | Quad/500 |"
    )
    completion_gate_row = (
        "| Completion difference | <= 1 percentage point | "
        f"{gate['completion_difference_percentage_points']:.3f} pp | pass |"
    )
    availability_gate_row = (
        "| Per-capture response/common availability | >= 50% | `034929`: "
        f"{availability['common_accuracy']}/{availability['target_count']} common | fail |"
    )
    association_header = (
        "| Capture | Primary NORAD | Train RMS | Heldout RMS | Baseline NORAD | "
        "Base train | Base heldout | IDs agree | Heldout persists | Wrong-time p | "
        "Permutation p | Rolling stable | Verdict | Failed required gates |"
    )
    score_link = link(_REPOSITORY_ROOT / SOURCE_SCORE_PATH)
    protocol_link = link(_REPOSITORY_ROOT / ACTIVE_PROTOCOL_PATH)
    response_evidence_link = link(_REPOSITORY_ROOT / SOURCE_ARTIFACTS["response_evidence"][0])
    attempt_evidence_link = link(_REPOSITORY_ROOT / SOURCE_ARTIFACTS["attempt1_evidence"][0])
    attempt_log_link = link(_REPOSITORY_ROOT / SOURCE_ARTIFACTS["attempt1_command_log"][0])
    return f"""# Final POST-FIX Doppler holdout and Starlink association

## Bottom line

This strictly frozen, downstream-withheld odd-Qin experiment produced a useful
forecasting result but **did not link any capture to a Starlink catalog identity**.
The response track was recoverable in all 8 evaluable captures, yet **0/8 passed the
full catalog-compatibility gate** and 2 additional captures remained non-evaluable.
Absolute secure NORAD identification is **0**, both because no candidate passed and
because the observer site is preset-only rather than capture-bound.

For CFO prediction, fixed 125 ms linear had the lowest equal-capture RMS
(`57.754 Hz`). The strict-past 500 ms quadratic improved the fixed 500 ms linear
baseline from `60.289` to `58.170 Hz`, winning 9/10 paired captures, but its formal
promotion gate **failed**: the ratio was `{gate["ratio"]:.6f}` rather than at most
`0.95`, and capture `034929` had only `{availability["common_accuracy"]}` common
accuracy rows out of `{availability["target_count"]}` targets
(`{availability["common_accuracy"] / availability["target_count"]:.2%}`), below the
frozen 50% availability floor. The quadratic remains a promising challenger, not a
promoted replacement.

## Scope and conditioning

The cohort is exactly 10 policy-classified **POST_FIX** captures and 5,413 frozen
selector-v2 targets. PRE_FIX, CAPTURE_ONLY, newer, and unlisted captures were
excluded. This separates these results from the historical continuous-recording /
refill-bug data.

The predictors are strict-past: each target uses only history in
`[target - horizon, target)`, and the target frame's numeric even-Qin CFO is never
consumed. Odd-Qin measurements were attached only after prediction and Starlink
rankings were immutable. However, upstream source, alias, trajectory, and epoch
selection may use all-Qin GLRT64 evidence. Results are therefore **conditional on
frozen upstream all-Qin acquisition and conditioning**, not an end-to-end unopened
acquisition test.

The primary error metric is equal-capture RMS on the identical 3,942-row common
eligible odd-Qin mask. Equal-capture RMS weights each capture equally; pooled RMS
weights every retained row equally. Completion is reported on all 5,413 targets.

## Forecast methods

| Method | Equal-capture RMS (Hz) | Pooled RMS (Hz) | Predictions complete | Completion | Common n |
|---|---:|---:|---:|---:|---:|
{_method_table(score)}

![Strict-past forecast comparison]({link(forecast_figure)})

### Per-capture paired errors

Every RMS below is evaluated on the same per-capture common mask.

{capture_header}
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{_capture_method_table(score)}

![Paired fixed-500 and quadratic capture errors]({link(paired_figure)})

### Frozen quadratic promotion gate

| Condition | Frozen requirement | Observed | Result |
|---|---:|---:|---|
| Equal-capture RMS ratio | quadratic / fixed500 <= 0.95 | {gate["ratio"]:.6f} | fail |
| Capture wins | >= 8 of 10 | {gate["capture_wins"]} of {gate["capture_comparisons"]} | pass |
| Capture comparisons | exactly 10 | {gate["capture_comparisons"]} | pass |
| Worst capture ratio | <= 1.10 | {gate["maximum_capture_ratio"]:.6f} | pass |
{completion_gate_row}
{availability_gate_row}

Formal result: **FAIL / do not promote**. The two recorded failure codes are
`equal_capture_rms_ratio_above_0_95` and
`capture_response_availability_below_50pct`; the gate was not revised after seeing
responses.

## Odd-response denominator

| Capture | Targets | Eligible | Boundary | No support | Missing | Common accuracy |
|---|---:|---:|---:|---:|---:|---:|
{_denominator_table(score)}

Global closure: `{denominator["target_count"]}` targets =
`{denominator["accuracy_eligible"]}` eligible + `{denominator["boundary"]}` boundary
+ `{denominator["no_support"]}` no-support + `{denominator["missing"]}` missing.
All 5,413 measurements were nonmissing; 3,942 rows formed the four-method common
accuracy mask.

## Starlink association

### What was frozen and fit

The candidate set was Starlink-only and came from the exact causal pre-capture TLE
snapshot. The primary lane was the strict-past quadratic predictor and the mandatory
baseline was fixed 500 ms. The primary nuisance fit used **one constant CFO offset
per capture/path with time delay fixed at tau = 0**. It did not fit candidate-specific
rate, acceleration, sample-clock scale, or delay. Candidate populations, 60/40 time
splits, offsets, wrong-time fields, permutations, rolling origins, UTC/site/TLE
sensitivities, and training rank order were all frozen before odd-Qin access.

`recovered_track` means only that enough held-out odd-response bins existed to score
the frozen trajectory. It is **not an identity claim**. `catalog_compatible` requires
every predeclared identity and null-control gate. A low held-out RMS, including a
value below the 100 Hz ceiling, is only one necessary condition.

### Exact outcome: 8/8 recovered, 0/8 catalog-compatible

![Corrected association RMS and gate meaning]({link(corrected_association_figure)})

![Association gate matrix]({link(gate_matrix_figure)})

The matrix shows selected discriminating conditions plus the full gate. The omitted
conditions—minimum held-out bins, minimum held-out fraction, recovered-track
availability, required permutation scoring, minimum wrong-time scoring, and
UTC/site/predecessor stability—passed for all 8 evaluable captures.

| Aggregate association/control check | Result |
|---|---:|
{_association_aggregate_table(score, association_rows)}

{association_header}
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---|---|---|
{_association_table(association_rows)}

The two retained non-evaluable captures were not dropped:

| Capture | Status | Frozen reason |
|---|---|---|
{_non_evaluable_table(association_rows)}

Across the 8 evaluable captures, primary and baseline selected the same rank-one
candidate in only 2/8, the training rank-one remained best on held-out odd data in
2/8, the wrong-time null passed in 0/8, and at least two rolling origins were stable
in 1/8. Those failures dominate the conclusion: **no satellite was linked**.

### Shared physical-radio rate sensitivity

This diagnostic was frozen before odd responses, fit after candidate ranking, and
was forbidden from changing candidate identity. It estimates one regularized shared
rate departure per physical receive chain plus capture-specific CFO offsets:

| Physical chain | Shared rate departure (Hz/s) |
|---|---:|
{_shared_rate_table(score)}

The diagnostic training RMS was `{shared["penalized_training_rms_hz"]:.3f} Hz` with
a `{shared["rate_prior_sigma_hz_s"]:.1f} Hz/s` zero-centered prior. These small
departures—especially the `{shared["rate_departures_hz_s"][1]:+.4f} Hz/s` value for
`rx_lnb_d`—are repeatability clues only. They are not absolute satellite Doppler-rate
measurements and do not identify LNB, receiver-clock, or sample-clock drift.

## Why no satellite match passed

1. Most short captures admit a low-RMS TLE trajectory after a free CFO offset, but
   wrong-time trajectories often fit comparably; 0/8 passed that null.
2. Candidate identity is model-sensitive: quadratic and fixed500 agree in only 2/8.
3. Future odd-Qin data preserve the training winner in only 2/8.
4. Rolling-origin stability is weak (1/8), so the association is not causally
   persistent.
5. The reviewed site is a preset with 50 m uncertainty and no capture-bound
   boresight; LNB and sample-clock drift remain unmeasured nuisance terms.

## Next experiments most likely to improve genuine matching

1. Open a new, source-supported POST_FIX holdout with longer counter-contiguous
   episodes. Longer arcs should make wrong-time Doppler shapes more distinguishable.
2. Predeclare an association comparison using fixed125 (the best forecast here),
   quadratic, and fixed500 agreement; do not choose the lane after responses.
3. Use simultaneous physical radios/bands with a shared rate and free per-path CFO
   offsets, while keeping identity selection independent of the diagnostic fit.
4. Measure or separately calibrate LNB, receiver, and sample-clock drift. Do not make
   the satellite model absorb those effects.
5. Require recurrence of the same candidate across independent captures and retain
   full wrong-time, permutation, rolling-origin, UTC, site, and predecessor-TLE
   controls.
6. Extend the causal archive to an all-satellite catalog only under a newly frozen
   protocol; a larger catalog without stronger null controls would increase false
   matches rather than confidence.

## Limits and claim language

- This is a retrospective, conditional POST_FIX holdout, not end-to-end unopened
  acquisition.
- The 8 recovered tracks are response-available CFO curves, not satellite IDs.
- No candidate is catalog-compatible; no absolute secure NORAD claim is permitted.
- The primary association fixed delay at tau=0 and fit only constant CFO offset.
- The shared-rate sensitivity is diagnostic and cannot alter rank-one identity.
- Corrected fixed500 interval calibration remains an abstention because its point
  estimator failed the frozen RMSE gate and a finite-sample 95% group quantile was
  unavailable.

## Provenance

- Immutable score: [`{SOURCE_SCORE_PATH.name}`]({score_link})
- Active v3 protocol: [`{ACTIVE_PROTOCOL_PATH.name}`]({protocol_link})
- Response-freeze evidence: [`attach-attempt-2-success-evidence.json`]({response_evidence_link})
- Superseded report evidence: [`report-attempt-1-evidence.json`]({attempt_evidence_link})
- Superseded report [command log]({attempt_log_link})
- Score SHA-256: `{SOURCE_SCORE_SHA256}`
- Score semantic digest: `{SOURCE_SCORE_DIGEST}`
- Prediction ledger digest: `{score["prediction_ledger_digest"]}`
- Odd attachment digest: `{score["attachment_digest"]}`
- Active v3 protocol digest: `{score["provenance"]["active_attachment_protocol_digest"]}`
- Source score freeze commit: `{SOURCE_SCORE_FREEZE_COMMIT}`
- Publication manifest: [`{publication_manifest.name}`]({link(publication_manifest)})
- Superseded terse report and ambiguous association figure remain immutable under
  their attempt-1 evidence receipt; this supplement changes presentation only.
"""


def render_corrected_figures(
    score: dict[str, Any],
    *,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Render two plain Matplotlib PNGs with explicit gate semantics."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    rows = association_publication_rows(score)
    labels = [_short_capture(item["session_id"]) for item in rows]
    heights = [item["primary_heldout_rms_hz"] if item["evaluable"] else np.nan for item in rows]
    colors = ["#228833" if item.get("catalog_compatible") is True else "#cc6677" for item in rows]
    figure, axis = plt.subplots(figsize=(13.5, 6.5))
    x = np.arange(len(rows))
    axis.bar(x, heights, color=colors, edgecolor="black", linewidth=0.5)
    for index, item in enumerate(rows):
        if not item["evaluable"]:
            axis.text(index, 4.0, "NE", ha="center", va="bottom", color="#555555")
    axis.axhline(100.0, color="black", linestyle="--", linewidth=1.2)
    axis.set_xticks(x, labels, rotation=30)
    axis.set_ylabel("Frozen primary rank-one held-out odd RMS (Hz)")
    axis.set_title("Starlink association: 0/8 catalog-compatible; no satellite linked")
    axis.text(
        0.5,
        1.01,
        "All eight evaluable response tracks fail at least one required identity/null gate",
        transform=axis.transAxes,
        ha="center",
        va="bottom",
        fontsize=10,
    )
    axis.grid(axis="y", alpha=0.25)
    axis.legend(
        handles=[
            Patch(facecolor="#cc6677", edgecolor="black", label="red = failed full gate"),
            Patch(facecolor="white", edgecolor="white", label="no bar / NE = non-evaluable"),
            Line2D(
                [0],
                [0],
                color="black",
                linestyle="--",
                label="100 Hz = one necessary condition only",
            ),
        ],
        loc="upper left",
    )
    figure.tight_layout()
    rms_path = output_dir / "association-heldout-rms-gated.png"
    figure.savefig(rms_path, dpi=180)
    plt.close(figure)

    evaluable = [item for item in rows if item["evaluable"]]
    matrix = np.asarray(
        [
            [bool(item["conditions"][key]) for key, _ in GATE_COLUMNS]
            + [bool(item["catalog_compatible"])]
            for item in evaluable
        ],
        dtype=int,
    )
    column_labels = [label for _, label in GATE_COLUMNS] + ["Full gate"]
    figure, axis = plt.subplots(figsize=(14.5, 7.2))
    axis.imshow(matrix, aspect="auto", cmap=ListedColormap(["#cc6677", "#228833"]), vmin=0, vmax=1)
    axis.set_xticks(np.arange(len(column_labels)), column_labels, rotation=35, ha="right")
    axis.set_yticks(
        np.arange(len(evaluable)),
        [_short_capture(item["session_id"]) for item in evaluable],
    )
    for row_index in range(matrix.shape[0]):
        for column_index in range(matrix.shape[1]):
            axis.text(
                column_index,
                row_index,
                "PASS" if matrix[row_index, column_index] else "FAIL",
                ha="center",
                va="center",
                color="white",
                fontsize=7.5,
                fontweight="bold",
            )
    axis.set_title("Selected discriminating association conditions + full gate (0/8 full pass)")
    axis.set_xlabel("A low held-out RMS is necessary but not sufficient")
    axis.set_ylabel("Capture UTC key")
    axis.legend(
        handles=[
            Patch(facecolor="#228833", label="condition passed"),
            Patch(facecolor="#cc6677", label="condition failed"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.20),
        ncol=2,
    )
    figure.tight_layout()
    matrix_path = output_dir / "association-gate-matrix.png"
    figure.savefig(matrix_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return rms_path, matrix_path


def _git_binding(repository_root: Path) -> tuple[str, str]:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository_root, text=True
    ).strip()
    tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=repository_root, text=True
    ).strip()
    relative = Path(__file__).resolve().relative_to(repository_root).as_posix()
    if subprocess.run(
        ["git", "diff", "--quiet", commit, "--", relative],
        cwd=repository_root,
        check=False,
    ).returncode:
        raise ValueError("publication renderer differs from the execution commit")
    return commit, tree


def render_publication(
    *,
    score_path: Path,
    output_dir: Path,
    markdown_path: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Render a score-only supplement to exclusive output paths."""

    score = load_frozen_score(score_path, repository_root=repository_root)
    verify_frozen_source_artifacts(repository_root=repository_root)
    if output_dir.exists() or markdown_path.exists():
        raise FileExistsError("publication output directory or markdown already exists")
    commit, tree = _git_binding(repository_root)
    output_dir.mkdir(parents=True, exist_ok=False)
    corrected_rms, gate_matrix = render_corrected_figures(score, output_dir=output_dir)
    forecast = repository_root / SOURCE_ARTIFACTS["attempt1_forecast_png"][0]
    paired = repository_root / SOURCE_ARTIFACTS["attempt1_paired_png"][0]
    manifest_path = output_dir / "publication-manifest.json"
    markdown = build_detailed_markdown(
        score,
        markdown_path=markdown_path,
        forecast_figure=forecast,
        paired_figure=paired,
        corrected_association_figure=corrected_rms,
        gate_matrix_figure=gate_matrix,
        publication_manifest=manifest_path,
    )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    with markdown_path.open("x") as handle:
        handle.write(markdown)

    association_rows = association_publication_rows(score)
    outputs = {}
    for label, path in (
        ("detailed_markdown", markdown_path),
        ("corrected_association_rms_png", corrected_rms),
        ("association_gate_matrix_png", gate_matrix),
    ):
        outputs[label] = {
            "path": path.relative_to(repository_root).as_posix(),
            "byte_size": path.stat().st_size,
            "sha256": _sha256_tag(path),
        }
    manifest: dict[str, Any] = {
        "schema": "org.leo.research.final-holdout-publication-supplement/v1",
        "status": "score_only_presentation_correction",
        "source_score": {
            "path": SOURCE_SCORE_PATH.as_posix(),
            "freeze_commit": SOURCE_SCORE_FREEZE_COMMIT,
            "freeze_tree": SOURCE_SCORE_FREEZE_TREE,
            "sha256": SOURCE_SCORE_SHA256,
            "semantic_digest": SOURCE_SCORE_DIGEST,
        },
        "active_protocol": {
            "path": ACTIVE_PROTOCOL_PATH.as_posix(),
            "sha256": ACTIVE_PROTOCOL_SHA256,
            "semantic_digest": score["provenance"]["active_attachment_protocol_digest"],
        },
        "renderer": {
            "path": Path(__file__).resolve().relative_to(repository_root).as_posix(),
            "execution_commit": commit,
            "execution_tree": tree,
            "sha256": _sha256_tag(Path(__file__).resolve()),
        },
        "preserved_source_artifacts": {
            label: {"path": relative, "sha256": digest}
            for label, (relative, digest) in SOURCE_ARTIFACTS.items()
        },
        "presentation_correction": {
            "first_report_remains_byte_identical": True,
            "first_association_figure_remains_byte_identical": True,
            "explicit_recovered_track_definition_added": True,
            "zero_of_eight_catalog_compatible_stated": True,
            "hundred_hz_line_labeled_one_necessary_condition_only": True,
            "failed_full_gate_and_non_evaluable_visual_semantics_added": True,
            "method_capture_association_and_shared_rate_tables_added": True,
        },
        "execution_boundary": {
            "iq_or_recording_storage_opened": False,
            "prediction_recomputed": False,
            "satellite_propagation_or_ranking_recomputed": False,
            "candidate_or_nuisance_parameters_refit": False,
            "score_values_changed": False,
        },
        "headline": {
            "target_count": score["response_status_denominator"]["target_count"],
            "common_accuracy_count": score["response_status_denominator"]["common_accuracy"],
            "quadratic_promotion_passed": score["quadratic_promotion_gate"]["passed"],
            "association_evaluable_capture_count": sum(
                bool(item["evaluable"]) for item in association_rows
            ),
            "association_recovered_track_count": sum(
                bool(item.get("recovered_track")) for item in association_rows
            ),
            "association_catalog_compatible_count": sum(
                bool(item.get("catalog_compatible")) for item in association_rows
            ),
            "absolute_secure_norad": score["absolute_secure_norad"],
        },
        "outputs": outputs,
        "created_utc": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
    }
    manifest["manifest_digest"] = canonical_digest(manifest)
    with manifest_path.open("x") as handle:
        handle.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def markdown_image_links(markdown: str) -> tuple[str, ...]:
    """Return local image links for static integrity tests."""

    return tuple(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", markdown))


def markdown_artifact_links(markdown: str) -> tuple[str, ...]:
    """Return non-image local artifact links for static integrity tests."""

    return tuple(re.findall(r"(?<!!)\[[^\]\n]+\]\(([^)]+)\)", markdown))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    arguments = parser.parse_args()
    render_publication(
        score_path=arguments.score,
        output_dir=arguments.output_dir,
        markdown_path=arguments.markdown,
        repository_root=_REPOSITORY_ROOT,
    )


if __name__ == "__main__":
    main()
