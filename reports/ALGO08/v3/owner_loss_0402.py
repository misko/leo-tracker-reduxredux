"""Trace saved cumulative ownership and try the qualified signed pair before deletion."""

import argparse
from collections import Counter
from contextlib import contextmanager
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from prospective_0402_solver import ARMS, PINS, SETTINGS, checked, inspect, invoke, orbit_legends, owner_delta, verify_sources


STAGED = Path("/dev/shm/leo-v3-saved-0402-pair-01")
ARCHIVED = HERE / "measurements/prospective-0402-solver.json.gz"
ARCHIVED_SHA = "efaf99cf3d5462d9f92a705164c2795c9b72b4cce9f6e3f4c19391f2f36f0e54"
REQUEST_SHA = "a2d730f64833eafd096877650e24b5c250b3bcfbef69d6bb5a44b70f0cbf1274"
BASE = "f0b2bf34f"
PROTOCOL = HERE / "owner-loss-0402-protocol.md"
SOURCE_PINS = PINS | {
    "blind_joint_finish.py": "7d8d5a65ceb0e11150e28d0dbbddeabb7741ef1408ded6272500e4f0e012c708",
    "blind_joint_route.py": "f7a66aea7ed875f5de067a0125948cd51c91e329ac0ea4b4ab1b4da6db5d1ca6",
    "blind_joint_signed.py": "3ec955b211a1c4b48fe18c66d9374a78fd393d3b068ffed1c7a9fe42d035629b",
    "blind_joint_repair.py": "f89e80dd65606b065e4c8097d0d3204362993e070dc7dd3f2c2590dc2c32b2a0",
    "lighter_joint_estimator.py": "6692c234ab897ec62057b1472ed25b47392345a84d7fa5730190bbfdd27086b8",
    "certified_salvage.py": "7ccb39db8f2f4a278b2c7b1977866e3d731601de7d759adb5541e88692917f09",
}


def now():
    return process_time(), perf_counter()


def clocks(start):
    cpu, wall = start
    return dict(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-wall)


def pair_gate_rows(pair):
    return {a: dict(curved=record["gates"]["tracks"], predictive=record["linear_gates"])
            for a, record in pair.items()}


def eligible(pair):
    from blind_joint_repair import failed_union, small_rejection

    failed_curved, failed_linear = failed_union(pair)
    if len(failed_curved) != 1 or failed_linear:
        return False
    rows = pair["c0"]["gates"]["tracks"]
    entries = pair["c0"]["linear_gates"]
    size = sum(row["points"] for row in rows)
    return small_rejection(dict(tracks=(len(rows)+len(entries), 1),
                                curved=(size, sum(row["points"] for row in rows if row["component"] in failed_curved))))


def earlier_signed(prepared, candidate, detail):
    """Try each original bounded warm arm once and defer admission to the paired gate."""
    from blind_joint_signed import update
    from lighter_joint_estimator import warm_arm

    def fit_pair(original, means):
        ready = {}
        for arm in ARMS:
            result, reason = warm_arm(original, means, arm)
            detail.setdefault("warm_reasons", {})[arm] = reason
            if result is not None:
                ready[arm] = result
        detail["refit_gates"] = pair_gate_rows(ready)
        if len(ready) != len(ARMS):
            raise ValueError("unaligned warm signed refreshes")
        return ready

    start = now()
    try:
        return update(prepared, candidate, detail, fit_pair=fit_pair)
    finally:
        detail["clocks"] = clocks(start)


@contextmanager
def bind(audit):
    import blind_joint_finish as finish
    import lighter_joint_estimator as signed

    propose, update = finish.propose, signed.update
    drop, select, pair = finish.drop_failing, finish.select_entries, finish.finish_pair
    attempted, accepted = False, None

    def scoped_drop(keep, rows, slices, gates):
        answer = drop(keep, rows, slices, gates)
        audit["curved_gates"].append(dict(input=int(keep.sum()), retained=int(answer[0].sum()), rows=gates["tracks"]))
        return answer

    def scoped_select(p, x, metrics):
        entries = select(p, x, metrics)
        accepted_rows = [row for row in metrics["tracks"] if row["compatible"]]
        phases = p.state(x)["phases"]
        audit["predictive"].append(dict(
            available=sorted({int(row["norad"]) for row in accepted_rows if abs(phases[row["candidate_index"]]) <= 15}),
            entries=entries,
            tracks=[dict(component=t["key"], ids=t["observation_ids"], receiver=t["receiver"], channel=t["channel"],
                         rf_hz=t["rf_hz"], curved=i in p.scan.curved) for i, t in enumerate(p.scan.tracks)],
        ))
        return entries

    def scoped_finish(*args, **kwargs):
        result, passed = pair(*args, **kwargs)
        audit["pre_repair"].append(dict(passed=passed, arms=pair_gate_rows(result["arms"])))
        return result, passed

    def hooked_propose(prepared, region, bound, measured, *, repair=None, **kwargs):
        def try_signed(candidate, region, measured):
            nonlocal attempted, accepted
            if not attempted and eligible(candidate["arms"]):
                detail = audit["pre_repair_signed"] = {}
                attempted = True
                try:
                    trial = earlier_signed(prepared, candidate, detail)
                except (AssertionError, ValueError, np.linalg.LinAlgError) as exc:
                    detail["error"] = f"{type(exc).__name__}: {exc}"
                else:
                    if trial is not candidate:
                        accepted = trial
                        measured.update({k: v for k, v in detail.items() if k.startswith("signed")})
                        return accepted, None
            return repair(candidate, region, measured)

        return propose(prepared, region, bound, measured, repair=try_signed if repair is not None else None, **kwargs)

    def finish_signed(prepared, ordinary, measured):
        result = ordinary if ordinary is accepted else update(prepared, ordinary, measured)
        audit["final"].append(dict(pre_repair=result is accepted, arms=pair_gate_rows(result["arms"])))
        return result

    with (patch.object(finish, "drop_failing", scoped_drop), patch.object(finish, "select_entries", scoped_select),
          patch.object(finish, "finish_pair", scoped_finish), patch.object(finish, "propose", hooked_propose),
          patch.object(signed, "update", finish_signed)):
        yield


def request():
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    job = STAGED/"request.json"
    data = json.loads(checked(job, REQUEST_SHA))
    archive = Path(data["local_archive"]["root"])
    contained = [archive, Path(data["native_file"]), Path(data["offer_file"]), STAGED/"inventory.json",
                 *(Path(path) for path in data["local_libraries"].values())]
    if (not all(path.resolve(strict=True).is_relative_to(STAGED) for path in contained)
            or archive_identity(archive)["snapshots_sha256"] != data["local_archive"]["snapshots_sha256"]):
        raise ValueError("The sealed DS30-0402 input is outside its original staged root")
    return job, data


def worker(output):
    import unified_short_bootstrap as entry

    verify_sources(checked, SOURCE_PINS)
    audit = dict(curved_gates=[], predictive=[], pre_repair=[], final=[])
    publication = entry.publish_active

    def scoped(*args, **kwargs):
        with bind(audit):
            return publication(*args, **kwargs)

    with patch.object(entry, "publish_active", scoped):
        invoke(STAGED/"request.json", "cumulative", output)

    from aperture_trial import write

    write(output/"owner-trace.json", audit)


def launch(output):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    job, _ = request()
    verify_sources(checked, SOURCE_PINS)
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", output.parent], text=True).strip() != "tmpfs":
        raise ValueError("Expected a fresh tmpfs output")
    output.mkdir()
    (output/"tmp").mkdir()
    write(output/"seal.json", dict(base=BASE, machine=machine, request_sha256=sha256(job.read_bytes()).hexdigest(),
          protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest(),
          source_sha256=SOURCE_PINS | {Path(__file__).name: sha256(Path(__file__).read_bytes()).hexdigest()}))
    env = environment(STAGED)
    env["TMPDIR"] = str(output/"tmp")
    path = output/"candidate"
    command = [RELEASE/"venv/bin/python", "-IB", __file__, "worker", path]
    run = measure(command, env, path)
    write(output/"candidate-clock.json", dict(timing=run, command=list(map(str, command))))


def stages(trace, original):
    first, second = trace["curved_gates"]
    (prediction,) = trace["predictive"]
    (pair,) = trace["pre_repair"]
    source = {oid: (track["component"], track["curved"]) for track in prediction["tracks"] for oid in track["ids"]}

    def gate_index(rows):
        return {oid: row for row in rows for oid in row["observation_ids"]}

    curved = [gate_index(stage["rows"]) for stage in (first, second)]
    nomination = gate_index(prediction["entries"])
    result = {}
    for arm in ARMS:
        pair_rows = gate_index(pair["arms"][arm]["curved"] + pair["arms"][arm]["predictive"])
        id_set = set(original["owners"][arm]["dropped"])
        groups = Counter()
        records = []
        for oid, norad, role in original["runs"]["stock"]["selected_rows"][arm]:
            if oid not in id_set:
                continue
            component, is_curved = source.get(oid, (None, None))
            f, s = [lookup.get(oid) for lookup in curved]
            before = pair_rows.get(oid)
            if before is not None and not before["compatible"]:
                where = "paired_track_gate"
            elif role == "predictive" and oid not in nomination:
                where = "predictive_family_unavailable" if norad not in prediction["available"] else "predictive_nomination"
            elif f is not None and not f["compatible"] and s is None:
                where = "first_curved_gate_no_salvage"
            elif s is not None and not s["compatible"]:
                where = "second_curved_gate"
            elif before is not None:
                where = "after_first_pair"
            else:
                where = "outside_initial_curved_roster"
            groups[(component, norad, role, where)] += 1
            records.append(dict(observation_id=oid, norad=norad, role=role, curve=is_curved, component=component,
                                status=where, first=f and f["compatible"], second=s and s["compatible"]))
        if len(records) != len(id_set):
            raise ValueError("Every archived owner loss needs an observation-backed stage")
        result[arm] = dict(groups=[dict(component=cmp, norad=n, role=r, stage=stage, count=count)
                                   for (cmp, n, r, stage), count in groups.items()], rows=records)
    return dict(by_arm=result, curved_counts=[(g["input"], g["retained"]) for g in (first, second)],
                predictive_counts=dict(families=len(prediction["available"]), rows=sum(r["points"] for r in prediction["entries"])))


def evaluate(output, receipt):
    from aperture_trial import read, write
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    _, req = request()
    old = json.loads(gzip.decompress(checked(ARCHIVED, ARCHIVED_SHA)))
    path = output/"candidate"
    clock = read(output/"candidate-clock.json")["timing"]
    if clock["exit_code"]:
        raise ValueError(clock["stderr_tail"])
    trace = read(path/"owner-trace.json")
    worker = read(path/SETTINGS["audit_name"])
    current = inspect(path, "cumulative", worker["receipt"], clock, req, **SETTINGS)
    if current["science"]["receipt"]["decision"] != "complete":
        raise ValueError("Expected the assigned complete saved fix")
    losses = stages(trace, old)
    baseline = old["runs"]["cumulative"]
    original_route = baseline["route_details"]
    if (losses["curved_counts"] != [(original_route["support"]["full_curved"], original_route["support"]["initial_curved"]),
                                    (original_route["support"]["initial_curved"]+original_route["support"]["curved_restored"],
                                     original_route["support"]["rechecked_curved"])]
            or losses["predictive_counts"]["rows"] != original_route["support"]["predictive_points"]):
        raise ValueError("The observer did not reproduce the archived pre-repair stages")
    ref, = (r["reference"] for r in json.loads(checked(REFERENCE, REFERENCE_SHA256))["cases"]
            if r["dataset_label"] == "DS30-0402" and r["authority_eligible"] and r["sealed_metadata_digests_verified"])
    pos = [ref["latitude_deg"], ref["longitude_deg"]]
    score = {arm: dict(horizontal_error_km=distance_km(pos, data["latlon"]), rf_rms_hz=data["rf_rms_hz"])
             for arm, data in current["terminal"]["arms"].items()}
    compare = {mode: {arm: owner_delta(run["selected_rows"][arm], current["selected_rows"][arm]) for arm in ARMS}
               for mode, run in old["runs"].items()}
    media = {name: old["runs"]["cumulative"]["figures"][name] == data for name, data in current["figures"].items()}
    write(receipt, dict(case="DS30-0402", seal=read(output/"seal.json"), prior_sha256=ARCHIVED_SHA, loss=losses,
                       original_scores=old["scores"], candidate_scores=score, deltas=compare, comparison_pngs=media,
                       candidate=current, trace=trace, legends=orbit_legends(path, current),
                       archived_clocks={mode: run["process"] for mode, run in old["runs"].items()}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("launch", "worker", "evaluate"):
        item = commands.add_parser(action)
        item.add_argument("output", type=Path)
        if action == "evaluate":
            item.add_argument("receipt", type=Path)
    args = parser.parse_args()
    values = vars(args)
    globals()[values.pop("action")](**values)
