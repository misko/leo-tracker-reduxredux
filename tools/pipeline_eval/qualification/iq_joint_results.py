"""Seal complete raw-to-joint outcomes, their matched controls and wrong-tile probe."""

import argparse
import gzip
from hashlib import sha256
from pathlib import Path

from ..__main__ import encoded, local_output, read_predictions, references, save_json, write
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import iq_joint_trial as trial
from .full_v5_check import _load_case, _sha
from .prefix_figures import csv_file

FILES = {
    trial.METHOD: "positions.jsonl.gz",
    "v5_secant_fit": "ordinary-secant-positions.jsonl.gz",
    trial.joint.METHOD: "capture-era-joint-positions.jsonl.gz",
}
WRONG_FILE = "missing-tile-positions.jsonl.gz"


def write_rows(output, name, rows):
    path = output / name
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
    return _sha(path)


def check_query(row, packet, physical, expected):
    if (
        row["input_sha256"] != sha256(encoded(packet)).hexdigest()
        or row["native_sha256"] != packet["native"]["sha256"]
        or row["native_sha256"] != expected["ordinary_native_sha256"]
        or row["native_sha256"] != _sha(physical)
        or row["catalog_sha256"] != packet["catalogue"]["sha256"]
        or row["catalog_sha256"] != expected["catalogue_sha256"]
        or row["tile"] != packet["offer"]
        or packet["track_config"]["sha256"] != expected["track_config_sha256"]
        or row["source_lock_sha256"] != _sha(trial.SEAL)
    ):
        raise ValueError("the measured worker query differs from its complete sealed IQ product")
    validate_result(row["result"])


def account_cpu(row, host):
    isolated = row.get("worker", {}).get("cpu_s")
    total = None if isolated is None else host + isolated
    row["worker_cpu_s"] = total
    return dict(
        host_supervisor_and_waited_cpu_s=host,
        isolated_fitter_self_cpu_s=isolated,
        total_cpu_s=total,
    )


def publish(output, work, bundle):
    lock = trial.read(trial.SEAL)
    if encoded(lock) != encoded(trial.source_lock(bundle)):
        raise ValueError("the run source or historical controls have changed")
    joint = read_predictions(trial.joint.REPORT / "positions.jsonl.gz")
    compact = read_predictions(trial.raw_stream_trial.CONTROL / "positions.jsonl.gz")
    rows, stages = {method: [] for method in FILES}, {}
    for ident in trial.CASES:
        case = _load_case(ident)
        expected = lock["inputs"][ident]
        path = work / ident
        row = trial.read(path / "position.json")
        stage = trial.read(path / "stages.json")
        control = joint[ident]
        control_query, _ = trial.joint.native.request(case, "native")
        check_query(row, stage["native_query"], path / "native.json", expected)
        if (
            row["mode"] != "matched-tile"
            or not row["raw_replayed_here"]
            or row["capture_era_native_sha256"] != expected["capture_era_native_sha256"]
            or stage["raw"]["native_sha256"] != expected["ordinary_native_sha256"]
            or stage["raw"]["recording_windows"] != expected["window_count"]
            or stage["graph_sha256"] != row.get("observation_sha256")
            or row["worker_wall_s"] > trial.CAP_S
            or control["input_sha256"] != sha256(encoded(control_query)).hexdigest()
            or control["native_sha256"] != expected["capture_era_native_sha256"]
            or control["catalog_sha256"] != row["catalog_sha256"]
            or control["tile"] != row["tile"]
            or compact[ident]["native_sha256"] != row["native_sha256"]
            or compact[ident]["catalog_sha256"] != row["catalog_sha256"]
            or compact[ident]["tile"] != row["tile"]
        ):
            raise ValueError("recording, Graph, matched tile or detector controls differ from plan")
        stage["cpu_accounting"] = account_cpu(row, stage["whole_chain"]["cpu_s"])
        stages[ident] = stage
        rows[trial.METHOD].append(row)
        rows["v5_secant_fit"].append(compact[ident])
        rows[trial.joint.METHOD].append(dict(control, mode="matched-tile"))
    ident = trial.CASES[0]
    wrong = trial.read(work / ident / "missing-tile.json")
    missing, packet = wrong["prediction"], wrong["native_query"]
    first = rows[trial.METHOD][0]
    check_query(missing, packet, work / ident / "native.json", lock["inputs"][ident])
    if (
        missing["id"] != trial.MISSING_ID
        or missing["raw_replayed_here"]
        or packet != dict(stages[ident]["native_query"], offer=lock["wrong_offer"])
        or (
            missing.get("observation_sha256") is not None
            and missing["observation_sha256"] != first.get("observation_sha256")
        )
    ):
        raise ValueError("the omitted-tile replay changed input evidence beyond the offer")
    missing["cpu_accounting"] = account_cpu(missing, missing["fit_envelope"]["cpu_s"])
    files = {name: write_rows(output, name, rows[method]) for method, name in FILES.items()}
    files[WRONG_FILE] = write_rows(output, WRONG_FILE, [missing])
    for name, value in (("stage-receipts.json", stages), ("missing-tile-query.json", packet)):
        save_json(output / name, value)
        files[name] = _sha(output / name)
    save_json(
        output / "prediction-lock.json",
        dict(cases=trial.CASES, files=files, source_lock_sha256=_sha(trial.SEAL)),
    )


def score(output):
    trial.verify_lock(output)
    lock = trial.read(output / "prediction-lock.json")
    if lock["source_lock_sha256"] != _sha(trial.SEAL):
        raise ValueError("candidate changed after sealing")
    refs = {r["id"]: r for r in references("smoke", None)[1]}
    positions = {key: read_predictions(output / name) for key, name in FILES.items()}
    wrong = read_predictions(output / WRONG_FILE)[trial.MISSING_ID]
    scores = []

    def numeric(row, ident, arm, source, method):
        result = row["result"]
        point = result["arms"][arm]
        truth = refs[ident]["truth"]
        return dict(
            id=row["id"],
            recording=ident,
            arm=arm,
            method=method,
            source=source,
            status=result["status"],
            reason=result.get("reason"),
            position_error_km=distance_km(point["latlon"], truth),
            forced_error_km=distance_km(point.get("forced_latlon"), truth),
            conditional_rms_hz=point.get("rf_rms_hz"),
            fitted_c_hz_per_ghz=point.get("c_hz_per_ghz"),
            held_score=point.get("held_score"),
            worker_wall_s=row["worker_wall_s"],
        )

    for ident in trial.CASES:
        for arm in ARMS:
            for method, rows in positions.items():
                source = "capture-era" if method == trial.joint.METHOD else "ordinary"
                scores.append(numeric(rows[ident], ident, arm, source, method))
            for role in ROLES:
                endpoint = refs[ident]["reference"][role][arm]
                item = dict.fromkeys(scores[-1])
                item.update(
                    id=ident,
                    recording=ident,
                    arm=arm,
                    method=f"capture-v5-{role}",
                    source="capture-era",
                    status="ok" if endpoint["latlon"] is not None else "withheld",
                    position_error_km=endpoint["error_km"],
                )
                scores.append(item)
    scores.extend(numeric(wrong, trial.CASES[0], arm, "ordinary", trial.METHOD) for arm in ARMS)
    csv_file(output / "scores.csv", scores)
    bindings = {
        name: wrong[name]
        for name in ("native_sha256", "catalog_sha256", "observation_sha256")
        if name in wrong
    }
    name = "missing-tile-queries.json"
    save_json(
        output / name,
        dict(
            queries=[
                dict(
                    id=trial.MISSING_ID,
                    recording=trial.CASES[0],
                    condition="Correct tile omitted",
                    truth=refs[trial.CASES[0]]["truth"],
                    bindings=bindings,
                )
            ]
        ),
    )
    save_json(
        output / "missing-tile-lock.json",
        dict(
            cases=[trial.MISSING_ID],
            files={
                key: _sha(output / key) for key in (name, WRONG_FILE, "missing-tile-query.json")
            },
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("publish", "score"))
    parser.add_argument("--bundle", type=Path, default=trial.joint.BUNDLE)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    opts = parser.parse_args()
    if opts.action == "publish":
        if opts.work is None:
            parser.error("publication requires the two fresh recorded-IQ work directories")
        publish(opts.out, opts.work, opts.bundle)
    else:
        score(opts.out)


if __name__ == "__main__":
    main()
