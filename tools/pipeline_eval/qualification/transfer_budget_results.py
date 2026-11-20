"""Score exact matched compact recovery decisions after the public prediction seal."""

import argparse
import gzip
from pathlib import Path

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km
from . import compact_transfer_results as historical
from . import screening_figures
from . import transfer_budget as trial
from .fresh_scenes import _read, _sha
from .native_joint_full_results import roi_margin

CANDIDATE, CONTROL = (trial.METHODS[k] for k in ("gate", "control"))
FIELDS = ("native_sha256", "catalog_sha256", "worker_input_sha256", "history_sha256")
ARCHIVE = "chart-positions.jsonl.gz"
LABELS = {
    "original": "Containing tile",
    "near-outside": "Near omission · site 1–2 km outside",
    "far-outside": "Far omission",
    "authentic": "Measured roof · shifted tile",
}
GEO = trial.compact.prior.custodian.cold


def sealed(path):
    lock = _read(path / "prediction-lock.json")
    files = lock.get("files", lock)
    if any(_sha(path / name) != digest for name, digest in files.items()):
        raise ValueError("prediction seal has changed")
    return files


def matches(a, b):
    return all(a[k] == b[k] for k in ("id", "capture_id", "tile", *FIELDS))


def archive_controls():
    root = historical.trial.REPORT
    sealed(root)
    original = historical._records(root / historical.COMPACT)
    retry = root / "measured-retry"
    sealed(retry)
    measured = _read(retry / "prediction.json")
    if not matches(measured, original[historical.trial.ROOF]):
        raise ValueError("measured archived retry differs from its original request")
    original[historical.trial.ROOF] = measured
    return {
        ident: dict(row, method=CONTROL, cohort="development", archived=True)
        for ident, row in original.items()
    }


def score(output):
    sealed(output)
    raw, requests = _read(output / "predictions.json"), _read(output / "requests.json")
    roster = {(r["id"], r["method"], r["cohort"]): r for r in requests}
    if len(roster) != len(raw) or any(
        not matches(r, roster[r["id"], r["method"], r["cohort"]]) for r in raw
    ):
        raise ValueError("a truth-free treatment request changed after sealing")
    archived = archive_controls()
    candidates = {r["id"]: r for r in raw if r["method"] == CANDIDATE}
    controls = archived | {r["id"]: r for r in raw if r["method"] == CONTROL}
    if set(candidates) != set(controls) or any(
        not matches(c, controls[k]) for k, c in candidates.items()
    ):
        raise ValueError("compact budget pairing changed an offer or a factor")

    truth_lock = _read(output / "fresh-input-lock.json")
    truth = _read(output / "released-truth.json")
    seed = bytes.fromhex(_read(output / "released-seed.json")["seed_hex"])
    draw = _read(output / "fresh-draw.json")
    for name, data in (
        ("private/truth.json", encoded(truth) + b"\n"),
        ("private/seed.bin", seed),
        ("public/cases.json", encoded(draw) + b"\n"),
    ):
        if truth_lock[name] != GEO._sha(data):
            raise ValueError("released custodian data differs from its pre-inference commitment")
    if draw["sha256"] != truth_lock["public/native.json"]:
        raise ValueError("released draw misstates the fresh native hash")
    prior = trial.compact.prior.REPORT
    if _read(prior / "input-lock.json")["private"]["private/truth.json"] != _sha(
        prior / "truth.json"
    ):
        raise ValueError("earlier ground truth changed")
    old_truth = _read(prior / "truth.json")
    _, [roof] = trial.compact.portable.references(
        "ds26-common127", [trial.compact.portable.ROOF_CASE]
    )
    queries, rows, normalized = [], [], []
    for ident, candidate in candidates.items():
        cohort = candidate["cohort"]
        if cohort == "fresh":
            target, role = truth["location"], truth["roles"][ident]
        elif ident == trial.compact.ROOF:
            target, role, cohort = roof["truth"], "authentic", "measured"
        else:
            target, role = old_truth[ident]["latlon"], old_truth[ident]["condition"]
        queries.append(
            dict(
                id=ident,
                recording=candidate["capture_id"],
                truth=target,
                study=cohort,
                condition=LABELS[role],
                bindings={key: candidate[key] for key in FIELDS},
            )
        )
        for record in (candidate, controls[ident]):
            normalized.append(dict(record, study=cohort))
            result = record["result"]
            diagnostic = next((x for x in record["trace"] if x["stage"] == "initial_evidence"), {})
            for arm in ARMS:
                endpoint = result.get("arms", {}).get(arm, {})
                fix = endpoint.get("latlon")
                rows.append(
                    dict(
                        id=ident,
                        study=cohort,
                        role=role,
                        arm=arm,
                        method=record["method"],
                        status=result["status"],
                        reason=result.get("reason"),
                        position_error_km=distance_km(fix, target),
                        false_publication=fix is not None and role.endswith("outside"),
                        true_margin_km=roi_margin(target, candidate["tile"]),
                        estimate_margin_km=roi_margin(fix, candidate["tile"]) if fix else None,
                        initial_compatible_fraction=(
                            diagnostic["accepted_points"] / diagnostic["tracked_points"]
                            if diagnostic.get("tracked_points")
                            else None
                        ),
                        initial_rf_rms_hz=diagnostic.get("accepted_rf_rms_hz"),
                        final_rf_rms_hz=endpoint.get("rf_rms_hz"),
                        wall_s=record["wall_s"],
                    )
                )
    write(
        output / ARCHIVE, gzip.compress(b"".join(encoded(r) + b"\n" for r in normalized), mtime=0)
    )
    save_json(output / "scores.json", rows)
    return queries


def charts(output, queries):
    specs = []
    titles = {
        "fresh": "Compact recovery budget at one new simulated site",
        "development": "Compact recovery budget on two earlier simulated sites",
        "measured": "Compact recovery budget on the shifted authentic roof tile",
    }
    for study, title in titles.items():
        cases = [
            {k: v for k, v in q.items() if k != "study"} for q in queries if q["study"] == study
        ]
        stem = f"compact-recovery-budget-{study}"
        query, lock = f"{stem}-queries.json", f"{stem}-lock.json"
        save_json(output / query, dict(queries=cases))
        files = (query, ARCHIVE, "prediction-lock.json", "policy-lock.json")
        save_json(
            output / lock,
            dict(cases=[q["id"] for q in cases], files={f: _sha(output / f) for f in files}),
        )
        control = "Same-run compact secant" if study == "fresh" else "Earlier compact secant"
        specs.append(
            dict(
                id=stem,
                method=CANDIDATE,
                scope="transfer",
                title=title,
                cases="sealed",
                caption="Paired native factors, supplied tiles and causal orbital history. "
                "Only complete cavity decisions supply positions. "
                "Deadlines remain distinct from withheld fixes.",
                seal=lock,
                queries=query,
                provenance=["prediction-lock.json", "policy-lock.json"],
                series=[
                    dict(
                        key=k,
                        label=label,
                        file=ARCHIVE,
                        value=method,
                        where=dict(study=study),
                        match=list(FIELDS),
                    )
                    for k, label, method in (
                        ("candidate", "Majority + 55 s recovery cap", CANDIDATE),
                        ("stock", control, CONTROL),
                    )
                ],
            )
        )
    save_json(output / "figures.json", dict(version=1, charts=specs))
    screening_figures.generate(output / "figures", evidence=output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=trial.REPORT)
    args = parser.parse_args()
    charts(args.out, score(args.out))
