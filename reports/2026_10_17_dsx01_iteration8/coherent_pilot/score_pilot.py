"""Post-seal singleton forecasts; never invent coherent group row likelihoods."""

import argparse
import csv
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import ports
import qualify as source
from leo.analysis.shared_scan_model import density
from numpy.testing import assert_array_equal

HERE = Path(__file__).resolve().parent
CASES = ("independent_fitted-c", "automatic_fitted-c", "independent_zero-c", "automatic_zero-c")


def rms(values):
    return float(np.sqrt(np.mean(np.square(values)))) if len(values) else None


def metrics(mask, current, baseline):
    """Keep the full denominator and compare residuals on the same intersection."""
    mask = np.asarray(mask, bool)
    assigned, old = current["associated"], baseline["associated"]
    retained = mask & assigned & old
    return dict(
        observations=int(mask.sum()),
        associated=int((mask & assigned).sum()),
        nll=float(current["row_nll"][mask].sum()),
        associated_rms_hz=rms(current["residual_hz"][mask & assigned]),
        new=int((mask & assigned & ~old).sum()),
        lost=int((mask & ~assigned & old).sum()),
        retained=int(retained.sum()),
        intersection_baseline_rms_hz=rms(baseline["residual_hz"][retained]),
        intersection_current_rms_hz=rms(current["residual_hz"][retained]),
    )


def broadening_gate(results, blocks):
    """Apply only the predeclared fitted-c development gate, without selecting states."""
    old = results["independent_fitted-c"]
    new = results["automatic_fitted-c"]
    delta = new["new_singleton"]["held"]["nll"] - old["new_singleton"]["held"]["nll"]
    selected = [r for r in blocks if r["arm"] == "fitted-c"]
    improved = sum(r["delta_new_singleton_nll"] < 0 for r in selected)
    requirements = dict(
        both_strict=bool(old["audit"]["accepted"] and new["audit"]["accepted"]),
        aggregate_new_singleton_nll_improves=bool(delta < 0),
        seven_blocks_and_at_least_four_improve=bool(len(selected) == 7 and improved >= 4),
        original_classifier_full_held_non_decrease=bool(
            new["original_shared"]["held"]["associated"]
            >= old["original_shared"]["held"]["associated"]
        ),
        original_classifier_requested_held_non_decrease=bool(
            new["original_shared"]["requested_held"]["associated"]
            >= old["original_shared"]["requested_held"]["associated"]
        ),
    )
    return dict(
        passed=all(requirements.values()),
        requirements=requirements,
        fitted_c_delta_held_new_singleton_nll=delta,
        improved_blocks=improved,
        total_held_blocks=len(selected),
        meaning="Development expansion only; root review required; no production/identity claim",
    )


def sealed_rows(directory, filename, field):
    seal = source.read(directory / filename)
    if seal.get("all_four_sealed") is not True:
        raise ValueError("All four outcomes/predictions must be sealed before measurement reads")
    rows = seal[field]
    if len(rows) != 4 or {r["case"] for r in rows} != set(CASES):
        raise ValueError("Exact four-case inventory required")
    for row in rows:
        path = Path(row["path"])
        path = path if path.is_absolute() else directory / path
        if source.digest(path) != row["sha256"]:
            raise ValueError("Sealed inference file changed: " + str(path))
        row = dict(row, path=path)
        yield row


def freeze():
    paths = [HERE / n for n in ("score_pilot.py", "test_score_pilot.py", "ROOT_GATE.md")]
    paths += [source.DATA / "context-observations.jsonl", source.DATA / "membership.csv"]
    paths += [
        HERE / n for n in ("qualification.json", "source_freeze.json", "actual_inventory.json")
    ]
    source.save(
        HERE / "evaluation_source_freeze.json",
        dict(
            source_sha256={str(p): source.digest(p) for p in paths},
            expected_cases=CASES,
            no_fits=True,
            eta=0.10,
            epsilon=0.12,
            measurement_reads_only_after_all_outcome_and_prediction_seals=True,
        ),
    )


def evaluate(directory):
    source.verify()
    for path, sha in source.read(HERE / "evaluation_source_freeze.json")["source_sha256"].items():
        if source.digest(path) != sha:
            raise ValueError("Evaluation source changed: " + path)
    outcomes = {
        r["case"]: source.read(r["path"])
        for r in sealed_rows(directory, "outcomes_seal.json", "outcomes")
    }
    predictions = {
        r["case"]: dict(np.load(r["path"], allow_pickle=False))
        for r in sealed_rows(directory, "predictions_seal.json", "predictions")
    }
    sealed = source.read(directory / "predictions_seal.json")
    if sealed["outcomes_seal_sha256"] != source.digest(directory / "outcomes_seal.json"):
        raise ValueError("Predictions must bind exact four-outcome seal")
    outcome_seal = source.read(directory / "outcomes_seal.json")
    if outcome_seal["qualification_sha256"] != source.digest(HERE / "qualification.json"):
        raise ValueError("Exact qualified model required")
    for key in ("root_gate_sha256", "qualification_sha256", "runner_source_freeze_sha256"):
        if sealed[key] != outcome_seal[key]:
            raise ValueError("Prediction/outcome authority differs: " + key)
    if (
        source.digest(HERE / "inference_source_freeze.json")
        != outcome_seal["runner_source_freeze_sha256"]
    ):
        raise ValueError("Exact runner source freeze required")
    score = SimpleNamespace(**outcome_seal["original_shared_score"])
    adapter = source.module("coherent_evaluation_adapter", source.MODEL / "adapter.py")
    # First measured CFO/requested labels enter here, after both validated seals.
    rows = [
        source.json.loads(line)
        for line in (source.DATA / "context-observations.jsonl").read_text().splitlines()
    ]
    rows = [r for r in rows if r["source_id"] == "S03"]
    measured = np.array([r["measured_cfo_hz"] for r in rows])
    ids = np.array([r["observation_id"] for r in rows])
    with (source.DATA / "membership.csv").open() as stream:
        membership = [r for r in csv.DictReader(stream) if r["source_id"] == "S03"]
    requested_ids = {r["observation_id"] for r in membership}
    requested = np.array([key in requested_ids for key in ids])
    windows = {
        rid: np.isin(ids, [r["observation_id"] for r in membership if r["region_id"] == rid])
        for rid in sorted({r["region_id"] for r in membership})
    }
    roles = ports.role_masks(ids, source.read(source.ATTEMPT / "derivation.json")["membership"])
    if [int(roles[r].sum()) for r in ("train", "held", "boundary")] != [2073, 1909, 6]:
        raise ValueError("Original exact role denominators required")
    if int((requested & roles["held"]).sum()) != 80:
        raise ValueError("Original requested held denominator required")
    classified = {}
    for case in CASES:
        p = predictions[case]
        assert_array_equal(p["observation_id"], ids)
        for role, mask in roles.items():
            assert_array_equal(p[role + "_mask"], mask)
        new = adapter.singleton_marginal(measured, p)
        old, details = density(
            measured,
            p["prediction_hz"],
            p["visibility_weight"],
            np.full(len(measured), 125.0),
            p["detection_probability"],
            score,
        )
        for label, terms, row_nll in (
            ("new_singleton", new, new.group_nll[new.group_index]),
            ("original_shared", old, details["row_nll"]),
        ):
            c = adapter.classify(terms)
            c.update(row_nll=row_nll, best_number=p["number"][c["best_index"]])
            classified[case, label] = c
    results = {}
    for case in CASES:
        arm = case.split("_", 1)[1]
        result = dict(
            audit=outcomes[case]["independent_endpoint_status"],
            diagnostics=outcomes[case]["result"]["diagnostics"],
        )
        arrays = dict(
            times_s=predictions[case]["times_s"],
            observation_id=ids,
            **{r + "_mask": m for r, m in roles.items()},
            requested_mask=requested,
        )
        for label in ("new_singleton", "original_shared"):
            c = classified[case, label]
            baseline = classified["independent_" + arm, label]
            uses = dict(
                roles, full=np.ones(len(ids), bool), requested_held=requested & roles["held"]
            )
            result[label] = {role: metrics(mask, c, baseline) for role, mask in uses.items()}
            result[label]["windows"] = {
                rid: {r: metrics(m & use, c, baseline) for r, m in roles.items()}
                for rid, use in windows.items()
            }
            arrays.update({label + "_" + k: v for k, v in c.items()})
        np.savez_compressed(HERE / f"evaluation_{case}.npz", **arrays)
        results[case] = result
    blocks = []
    for arm in ("fitted-c", "zero-c"):
        oldcase, newcase = "independent_" + arm, "automatic_" + arm
        indexes = np.floor(predictions[oldcase]["times_s"] / 20).astype(int)
        for block in np.unique(indexes[roles["held"]]):
            use = roles["held"] & (indexes == block)
            row = dict(arm=arm, start_s=int(20 * block), observations=int(use.sum()))
            for label in ("new_singleton", "original_shared"):
                old, new = classified[oldcase, label], classified[newcase, label]
                row["delta_" + label + "_nll"] = float(
                    (new["row_nll"][use] - old["row_nll"][use]).sum()
                )
                row[label] = metrics(use, new, old)
            blocks.append(row)
    gate = broadening_gate(results, blocks)
    source.save(
        HERE / "evaluation.json",
        dict(
            results=results,
            blocks=blocks,
            gate=gate,
            fits=0,
            singleton_density_calls=8,
            outcomes_seal_sha256=source.digest(directory / "outcomes_seal.json"),
            predictions_seal_sha256=source.digest(directory / "predictions_seal.json"),
            evaluation_source_freeze_sha256=source.digest(HERE / "evaluation_source_freeze.json"),
            classification_not_verified_identity=True,
            no_held_grouping=True,
            all15_denominator_untested_other_sources=555,
            evaluation_denominators=source.read(source.ATTEMPT / "derivation.json")[
                "evaluation_denominators"
            ],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "evaluate"))
    parser.add_argument("--directory", type=Path, default=HERE / "inference_results")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze()
    else:
        evaluate(args.directory)
