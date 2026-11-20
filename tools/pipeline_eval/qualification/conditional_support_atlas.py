"""Adapt original conditional-support receipts to the standard screening atlas."""

import argparse
import json
from hashlib import sha256
from pathlib import Path

from ..__main__ import read_predictions, save_json, write
from ..scoring import ARMS, validate_result
from . import conditional_support_trial as trial
from . import owner_factor
from .armijo_finish_results import pack
from .native_joint_full_results import roi_margin

BLIND = "conditional_support_recovery"
ORACLE = "conditional_support_oracle"
STOCK = "native_joint_orbits"
REJECTED = "conditional_support_rejected_refit"
CASES = {
    "diagnostic": trial.IDS[:2],
    "confirmation": trial.IDS[2:-1],
    "omitted": trial.IDS[-1:],
}
MATCH = ("input_sha256", "native_sha256", "catalog_sha256", "observation_sha256")
PAIRED = "blind-atlas-positions.jsonl.gz"
FORCED = "oracle-atlas-positions.jsonl.gz"
QUERIES = "omitted-queries.json"


def _read(path):
    return json.loads(path.read_bytes())


def _hash(path):
    return sha256(path.read_bytes()).hexdigest()


def _sealed(path, expected):
    content = path.read_bytes()
    if sha256(content).hexdigest() != expected:
        raise ValueError(f"{path.name} differs from the original evidence seal")
    return content


def _copy(output, path, expected, name=None):
    payload = _sealed(path, expected)
    name = name or path.name
    write(output / name, payload)
    return name, expected


def forced_row(reference, refit, mode):
    if refit["status"] != "forced_only" or set(refit["arms"]) != set(ARMS):
        raise ValueError("the privileged diagnosis requires two original forced-only arms")
    arms = {}
    for arm, options in refit["arms"].items():
        point = options[mode]
        if point["latlon"] is not None or point["forced_latlon"] is None:
            raise ValueError("an oracle arm must retain its original forced-only endpoint")
        arms[arm] = dict(
            latlon=None,
            forced_latlon=point["forced_latlon"],
            rf_rms_hz=point["total_rms_hz"],
            added_support_rms_hz=point["added_rms_hz"],
        )
    result = dict(
        status="withheld",
        reason="forced_diagnostic_only",
        boundary="Privileged exact refit with archived v5 components, owners and alias lifts",
        metrics={"privileged_diagnostic": True},
        arms=arms,
    )
    validate_result(result)
    return dict(
        id=refit["id"],
        method=ORACLE,
        atlas_bound=mode,
        native_sha256=reference["native_sha256"],
        catalog_sha256=reference["catalog_sha256"],
        input_sha256=refit["input_sha256"],
        result=result,
    )


def _bundle(source, output, full, owner):
    lock = _read(source / "prediction-lock.json")
    artifacts = _read(source / "artifact-lock.json")
    if tuple(lock["cases"]) != trial.IDS or artifacts["prediction-lock.json"] != _hash(
        source / "prediction-lock.json"
    ):
        raise ValueError("blind qualification has a different roster or prediction seal")
    provenance = dict(
        _copy(output, source / name, artifacts[name], "source-" + name)
        for name in (
            "prediction-lock.json",
            "blind-plan.json",
            *(f"{case}-oracle-refit.json" for case in CASES["diagnostic"]),
        )
    )
    for name, expected in lock["files"].items():
        _sealed(source / name, expected)
    _sealed(source / "control-positions.jsonl.gz", artifacts["control-positions.jsonl.gz"])
    blind = read_predictions(source / "positions.jsonl.gz")
    control = read_predictions(source / "control-positions.jsonl.gz")
    archive_lock = _read(full / "prediction-lock.json")
    plan = _read(source / "blind-plan.json")
    if archive_lock["files"]["positions.jsonl.gz"] != plan["control_sha256"]:
        raise ValueError("archived control changed after the blind plan")
    _sealed(full / "positions.jsonl.gz", plan["control_sha256"])
    archived = read_predictions(full / "positions.jsonl.gz")
    for ident in trial.IDS:
        if (
            control[ident] != archived[ident]
            or blind[ident]["method"] != BLIND
            or control[ident]["method"] != STOCK
            or any(blind[ident][k] != control[ident][k] for k in (*MATCH, "tile"))
        ):
            raise ValueError(f"{ident} does not match the sealed native control")
    original_owners = _read(owner / "prediction-lock.json")
    source_owner = json.loads(
        _sealed(owner / "input-lock.json", original_owners["input_lock_sha256"])
    )
    _sealed(owner / owner_factor.FILE, original_owners["files"][owner_factor.FILE])
    old_oracle = {row["id"]: row for row in owner_factor._load(owner / owner_factor.FILE)}
    provenance.update(
        [
            _copy(
                output,
                owner / "input-lock.json",
                original_owners["input_lock_sha256"],
                "source-v5-owner-input-lock.json",
            )
        ]
    )
    oracle_rows = []
    for ident in CASES["diagnostic"]:
        refit = _read(output / f"source-{ident}-oracle-refit.json")
        record = old_oracle[ident]
        if (
            refit["id"] != ident
            or refit["input_sha256"] != source_owner["privileged_sha256"]
            or refit["source_position_sha256"] != source_owner["blind_lock_sha256"]
            or any(
                record["bindings"][k] != blind[ident][k]
                for k in ("native_sha256", "catalog_sha256")
            )
            or any(
                refit["arms"][arm]["fixed"]["forced_latlon"]
                != record["estimates"]["v5_full_lean"]["arms"][arm]["forced_latlon"]
                for arm in ARMS
            )
        ):
            raise ValueError(
                f"{ident} privileged refit does not match its prior inputs and position"
            )
        oracle_rows.extend(
            forced_row(blind[ident], refit, mode) for mode in ("fixed", "release_saturation")
        )
    blind_rows = [
        dict(row, atlas_cohort=cohort)
        for cohort, ids in CASES.items()
        for ident in ids
        for row in (blind[ident], control[ident])
    ]
    (omitted,) = CASES["omitted"]
    query_lock = _read(full / "omitted-figure-lock.json")
    query_raw = _sealed(full / QUERIES, query_lock["files"][QUERIES])
    (query,) = [q for q in json.loads(query_raw)["queries"] if q["id"] == omitted]
    selected = blind[omitted]
    refit = selected["recovery"]["refit"]
    if (
        refit["status"] != "withheld"
        or selected["recovery"]["admitted"]
        or any(refit["arms"][a]["latlon"] is not None for a in ARMS)
        or any(selected[k] != value for k, value in query["bindings"].items())
        or roi_margin(query["truth"], selected["tile"]) >= 0
    ):
        raise ValueError("original rejected refit or omitted offer cannot be verified")
    query["bindings"].update({k: selected[k] for k in MATCH})
    blind_rows.append(
        dict(id=omitted, method=REJECTED, atlas_cohort="omitted", result=refit, **query["bindings"])
    )

    save_json(output / QUERIES, dict(queries=[query]))
    blind_files = dict(
        provenance,
        **{
            PAIRED: pack(output, PAIRED, blind_rows),
            QUERIES: _hash(output / QUERIES),
        },
    )
    oracle_files = dict(provenance, **{FORCED: pack(output, FORCED, oracle_rows)})
    return blind_files, oracle_files, tuple(provenance)


def export(source=trial.OUTPUT, output=None, *, full=trial.full.REPORT, owner=owner_factor.REPORT):
    output = Path(output or source / "standard-atlas")
    if output.resolve() == source.resolve():
        raise ValueError("atlas files must be separate from original evidence")
    output.mkdir(parents=True, exist_ok=True)
    blind_files, oracle_files, provenance = _bundle(source, output, full, owner)
    charts = []
    for cohort, cases in CASES.items():
        missing = cohort == "omitted"
        name = BLIND + "-" + cohort
        seal = cohort + "-figure-lock.json"
        main = "candidate" if missing else "one"
        series = [
            dict(
                key=main,
                label="Paired phase rescue · publication",
                file=PAIRED,
                value=BLIND,
                forced_label="Paired phase rescue · forced",
                where=dict(atlas_cohort=cohort),
            ),
            dict(
                key="stock",
                label="Nominal native joint · publication",
                file=PAIRED,
                value=STOCK,
                where=dict(atlas_cohort=cohort),
                match=list(MATCH),
            ),
        ]
        if missing:
            series[1]["forced_label"] = "Nominal native joint · forced"
            series.append(
                dict(
                    key="one",
                    label="Rejected rescue refit · publication",
                    file=PAIRED,
                    forced_label="Rejected rescue refit · forced",
                    value=REJECTED,
                    where=dict(atlas_cohort=cohort),
                    match=list(MATCH),
                )
            )
        spec = dict(
            id=name,
            method=BLIND,
            scope="transfer" if missing else "roof",
            cases=list(cases),
            seal=seal,
            provenance=list(provenance[:2]),
            series=series,
            title={
                "diagnostic": "Blind phase rescue on the diagnosed recordings",
                "confirmation": "Blind phase rescue on four disjoint recordings",
                "omitted": "Blind phase rescue with the correct region omitted",
            }[cohort],
            caption=(
                "One original omitted offer. The measured rescue refit also withheld under "
                "the unchanged held-track gate."
                if missing
                else "Complete stored native GLRT factors with the matching causal catalogue and "
                "original offer. Archived nominal and final rescue output arms are identical."
            ),
        )
        if missing:
            spec["queries"] = QUERIES
        save_json(output / seal, dict(cases=list(cases), files=blind_files))
        charts.append(spec)
    for suffix, mode, label in (
        ("fixed", "fixed", "Nominal bound · forced"),
        ("release", "release_saturation", "Released phase bound · forced"),
    ):
        cases = list(CASES["diagnostic"])
        seal = "oracle-" + suffix + "-figure-lock.json"
        charts.append(
            dict(
                id=ORACLE + "-" + suffix,
                method=ORACLE,
                scope="roof",
                cases=cases,
                seal=seal,
                provenance=list(provenance[2:]),
                title="Privileged fixed owners · "
                + ("original phase bound" if suffix == "fixed" else "phase bound released"),
                caption=(
                    "Original ±7.5 s phase bound. "
                    if suffix == "fixed"
                    else "Only the saturated family's phase bound is released. "
                )
                + "Uses archived v5 owners and alias lifts. Refit coordinates are forced. "
                "The four original v5 options are publication references.",
                series=[
                    dict(
                        key="one",
                        label="Privileged diagnostic · publication",
                        file=FORCED,
                        value=ORACLE,
                        where=dict(atlas_bound=mode),
                        forced_label=label,
                    )
                ],
            )
        )
        save_json(output / seal, dict(cases=cases, files=oracle_files))
    save_json(output / "figures.json", dict(version=1, charts=charts))
    return tuple(chart["id"] for chart in charts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    print("\n".join(export(output=args.out)))
