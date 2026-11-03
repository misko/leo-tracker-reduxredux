"""Frozen posthoc density-family comparison; no fitting or endpoint selection."""

import csv
import sys
from pathlib import Path
from types import SimpleNamespace

import control
import numpy as np
from leo.analysis.shared_scan_model import density

HERE = Path(__file__).resolve().parent
ARMS = ("fitted-c", "zero-c")


def gate(rows, blocks):
    r = rows["fitted-c"]
    m = r["original_shared"]
    selected = [b for b in blocks if b["arm"] == "fitted-c"]
    delta = m["held"]["current_nll"] - m["held"]["original_nll"]
    requirements = dict(
        both_fitted_strict=all(
            r["audits"][k]["feasible"] and r["audits"][k]["accepted"]
            for k in ("legacy", "new_point")
        ),
        full_held_count_nondecreasing=m["held"]["associated"] >= m["held"]["original"],
        requested_held_count_nondecreasing=m["requested_held"]["associated"]
        >= m["requested_held"]["original"],
        original_shared_held_nll_lower=delta < 0,
        at_least_four_of_seven_blocks=len(selected) == 7
        and sum(b["delta_original_shared_nll"] < 0 for b in selected) >= 4,
    )
    return dict(
        passed=all(requirements.values()),
        requirements=requirements,
        delta_original_shared_held_nll=delta,
        improved_blocks=sum(b["delta_original_shared_nll"] < 0 for b in selected),
        interpretation="Posthoc explored-S03 density-family comparison; no automatic expansion",
    )


def checked(directory, name, field, expected):
    seal = control.read(directory / name)
    flag = "all_two_sealed" if len(expected) == 2 else "all_four_sealed"
    if seal.get(flag) is not True:
        raise ValueError("Complete outcome/prediction seal required before CFO reads")
    rows = seal[field]
    if len(rows) != len(expected) or {r["case"] for r in rows} != set(expected):
        raise ValueError("Exact sealed case inventory required")
    result = {}
    for row in rows:
        path = Path(row["path"])
        if not path.is_absolute():
            path = directory / path
        if control.digest(path) != row["sha256"]:
            raise ValueError("Sealed bytes changed")
        result[row["case"]] = path
    return seal, result


def freeze():
    control.verify()
    paths = [
        HERE / n
        for n in ("score_control.py", "test_score_control.py", "PROTOCOL.md", "root_fit_gate.json")
    ]
    paths += [control.PILOT / n for n in ("FINAL_SEAL.json", "score_pilot.py", "ports.py")]
    paths += [control.PILOT.parent / "original_anchor" / n for n in ("audit.py", "manifest.json")]
    paths += [
        control.REPORTS / "2026_10_16_dsx01_fast_association_losses" / n
        for n in ("context-observations.jsonl", "membership.csv")
    ]
    bindings = dict(control.read(HERE / "source_freeze.json")["files"])
    bindings.update({str(p): control.digest(p) for p in paths})
    control.save(
        HERE / "evaluation_source_freeze.json",
        dict(
            files=bindings,
            direction="New minus legacy, using the same original shared PDF/classifier",
            gate="Both fitted strict; counts nondecrease; shared held NLL lower and >=4/7 blocks",
            chronology="Evaluator frozen after control outcomes, before any control held scores",
            prespecified_metric_gate="Frozen PROTOCOL predates control outcomes",
            no_fits=True,
            no_new_point_refits=True,
            no_held_score=True,
        ),
    )


def evaluate():
    frozen = control.read(HERE / "evaluation_source_freeze.json")
    control.io.verify_bindings(frozen["files"])
    olddir, newdir = HERE / "inference_results", control.RESULTS
    oldseal, oldfits = checked(olddir, "outcomes_seal.json", "outcomes", control.CASES)
    oldpredseal, oldpreds = checked(olddir, "predictions_seal.json", "predictions", control.CASES)
    newseal, newfits = checked(newdir, "outcomes_seal.json", "outcomes", control.io.CASES)
    newpredseal, newpreds = checked(
        newdir, "predictions_seal.json", "predictions", control.io.CASES
    )
    for directory, pseal in ((olddir, oldpredseal), (newdir, newpredseal)):
        if pseal["outcomes_seal_sha256"] != control.digest(directory / "outcomes_seal.json"):
            raise ValueError("Predictions must bind exact outcomes")
    if oldseal["immutable_new_point_predictions_sha256"] != control.digest(
        newdir / "predictions_seal.json"
    ):
        raise ValueError("Immutable previous point predictions differ")
    if oldseal["root_gate_sha256"] != control.digest(HERE / "root_fit_gate.json"):
        raise ValueError("Exact authorized two-control gate required")
    if oldseal["original_shared_score"] != newseal["original_shared_score"]:
        raise ValueError("Original normalized score configuration differs")
    ports = control.public_ports()
    anchor = control.module(
        "point_control_paired_port", control.PILOT.parent / "original_anchor/audit.py"
    )
    data = control.REPORTS / "2026_10_16_dsx01_fast_association_losses"
    # First held measured CFO and requested labels enter after both families seal.
    rows = [
        control.io.json.loads(line)
        for line in (data / "context-observations.jsonl").read_text().splitlines()
    ]
    rows = [r for r in rows if r["source_id"] == "S03"]
    ids = np.array([r["observation_id"] for r in rows])
    measured = np.array([r["measured_cfo_hz"] for r in rows])
    with (data / "membership.csv").open() as stream:
        members = [r for r in csv.DictReader(stream) if r["source_id"] == "S03"]
    roles = ports.qualifier.ports.role_masks(
        ids, control.read(ports.qualifier.ATTEMPT / "derivation.json")["membership"]
    )
    masks = dict(
        roles,
        full=np.ones(len(ids), bool),
        requested_held=roles["held"] & np.isin(ids, [r["observation_id"] for r in members]),
    )
    if [int(masks[k].sum()) for k in ("train", "held", "boundary", "requested_held")] != [
        2073,
        1909,
        6,
        80,
    ]:
        raise ValueError("Exact unchanged denominators required")
    windows = {
        rid: np.isin(ids, [r["observation_id"] for r in members if r["region_id"] == rid])
        for rid in sorted({r["region_id"] for r in members})
    }
    states, outcomes, predictions = {}, {}, {}
    for arm in ARMS:
        for family, fitpaths, predpaths, prefix in (
            ("legacy", oldfits, oldpreds, "old_"),
            ("new_point", newfits, newpreds, "independent_"),
        ):
            key = prefix + arm
            outcomes[family, arm] = control.read(fitpaths[key])
            with np.load(predpaths[key], allow_pickle=False) as archive:
                p = dict(archive)
            predictions[family, arm] = p
            np.testing.assert_array_equal(p["observation_id"], ids)
            np.testing.assert_array_equal(p["times_s"], np.array([r["time_s"] for r in rows]))
            for role, mask in roles.items():
                np.testing.assert_array_equal(p[role + "_mask"], mask)
            old, details = density(
                measured,
                p["prediction_hz"],
                p["visibility_weight"],
                np.full(len(ids), 125.0),
                p["detection_probability"],
                SimpleNamespace(**oldseal["original_shared_score"]),
            )
            new = ports.adapter.singleton_marginal(measured, p)
            for score, terms, nll in (
                ("original_shared", old, details["row_nll"]),
                ("new_singleton", new, new.group_nll[new.group_index]),
            ):
                c = ports.adapter.classify(terms)
                states[family, arm, score] = dict(
                    associated=c["associated"],
                    residual_hz=c["residual_hz"],
                    number=p["number"][c["best_index"]],
                    row_nll=nll,
                )
    result, blocks = {}, []
    for arm in ARMS:
        row = dict(
            audits={
                f: outcomes[f, arm]["independent_endpoint_status"] for f in ("legacy", "new_point")
            },
            costs={f: outcomes[f, arm]["cost"] for f in ("legacy", "new_point")},
        )
        arrays = dict(
            observation_id=ids,
            times_s=predictions["legacy", arm]["times_s"],
            **{r + "_mask": m for r, m in masks.items()},
        )
        for score in ("original_shared", "new_singleton"):
            old, new = states["legacy", arm, score], states["new_point", arm, score]

            def metric(use, old=old, new=new):
                m = anchor.paired(use, old, new)
                m.update(
                    original_associated_rms_hz=anchor.rms(
                        old["residual_hz"][use & old["associated"]]
                    ),
                    current_associated_rms_hz=anchor.rms(
                        new["residual_hz"][use & new["associated"]]
                    ),
                )
                return m

            row[score] = {k: metric(m) for k, m in masks.items()}
            row[score]["windows"] = {
                rid: {role: metric(mask & use) for role, mask in roles.items()}
                for rid, use in windows.items()
            }
            for family in ("legacy", "new_point"):
                arrays.update(
                    {
                        family + "_" + score + "_" + k: v
                        for k, v in states[family, arm, score].items()
                    }
                )
        index = np.floor(predictions["legacy", arm]["times_s"] / 20).astype(int)
        for b in np.unique(index[roles["held"]]):
            use = roles["held"] & (index == b)
            block = dict(arm=arm, start_s=int(20 * b), observations=int(use.sum()))
            for score in ("original_shared", "new_singleton"):
                old, new = states["legacy", arm, score], states["new_point", arm, score]
                block[score] = anchor.paired(use, old, new)
                block["delta_" + score + "_nll"] = float(
                    (new["row_nll"][use] - old["row_nll"][use]).sum()
                )
            blocks.append(block)
        np.savez_compressed(HERE / ("evaluation_" + arm + ".npz"), **arrays)
        result[arm] = row
    control.io.verify_bindings(frozen["files"])
    control.save(
        HERE / "evaluation.json",
        dict(
            rows=result,
            blocks=blocks,
            gate=gate(result, blocks),
            normalized_density_calls=8,
            fits=0,
            new_point_refits=0,
            posthoc_explored_source=True,
            no_held_grouping=True,
            evaluation_source_freeze_sha256=control.digest(HERE / "evaluation_source_freeze.json"),
            source_seals={
                str(d / n): control.digest(d / n)
                for d in (olddir, newdir)
                for n in ("outcomes_seal.json", "predictions_seal.json")
            },
        ),
    )


if __name__ == "__main__":
    if sys.argv[1:] == ["freeze"]:
        freeze()
    elif sys.argv[1:] == ["evaluate"]:
        evaluate()
    else:
        raise ValueError("freeze or evaluate required")
