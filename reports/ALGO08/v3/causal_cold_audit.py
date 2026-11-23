"""Attribute one cold stage without changing original optimizer decisions."""

import argparse
from collections import Counter
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from aperture_trial import ARMS, RELEASE, read, write
from dense_full_short_raw import checked
from dense_geographic_trial import host
from full_short_physical import environment
from optimizer_quadrature_census import site
from short_raw_diagnostic import measure
from target_owner_recovery_trial import STAGED, inventory_for, worker as original_worker


CAUSAL = Path("/dev/shm/leo-v3-causal-mask-dense-01")
ARCHIVES = {
    "full-mixed": (Path("/var/tmp/leo-v3-regional-dense-pair/native"), "11c554cbcca4f756e07e810bbc7b34b548a799fd005645fd4d9e5fcbba8ef72e"),
    "target": (Path("/dev/shm/leo-v3-modest-mask-results.0qfAjbDv/DS30-0008/target"), "22742b7b08a400f06df9263e8f3cfa8946bc20c9ff8fddeb9e9842625c60d7d2"),
    "causal": (CAUSAL / "dense", "8dded884cd12d52f95d135d4da850fbb5f7dc62ee1252d7553a7065170668f61"),
    "hindsight": (Path("/dev/shm/leo-v3-target-owner-recovery-01/dense"), "fb24dae00f05b586722997cb83f599f7bbde363873cde7813bd2de54d3f9c769"),
}
PINS = {
    HERE / "cold_finalist_race.py": "eeb7d1041f34fb7dbb805cb12eb93f66eba87e729e9cf695ff77811b51842fe7",
    HERE / "joint_publication.py": "9df6978f279577f972460a6b752511df9bf4c511e74d072ce4ff23ebd39ac5f7",
    HERE / "target_owner_recovery_trial.py": "9da442b4a2f917f27dbc134f59ca997f30efc65fa569fae76cc538c209dfd6e6",
    CAUSAL / "request.json": "191d2b39af53069ed2db3eec9da2126dfddff3ee99d5b03a0caaf876c1839aeb",
    CAUSAL / "seal.json": "2ada322a4083b6b42961527c980a5d37789cdc7c5edea03711b7a51b0e42eaa6",
}


class ColdDone(BaseException):
    """End the saved observer before generating a new solver terminal."""


def finite(value):
    from math import isfinite

    return float(value) if isfinite(value) else None


def without_timers(obj):
    if isinstance(obj, dict):
        return {k: without_timers(v) for k, v in obj.items() if k != "cpu_ns"}
    if isinstance(obj, list):
        return list(map(without_timers, obj))
    return obj


def duplicate_scope(rows):
    """Price only truly repeated requests in the same unchanged model."""
    seen, duplicates = {}, []
    for row in rows:
        signature = row["model"], row["exact_position"]
        original = seen.setdefault(signature, row)
        if original is row:
            continue
        if original["result_sha256"] != row["result_sha256"]:
            raise ValueError("Identical model coordinate returned different objective bits")
        duplicates.append(row)
    return dict(calls=len(rows), exact_duplicates=len(duplicates), cpu_ns=sum(r["cpu_ns"] for r in rows),
                free_duplicate_ceiling_ns=sum(r["cpu_ns"] for r in duplicates))


class Census:
    def __init__(self):
        self.models, self.indices, self.calculations, self.objectives = [], {}, [], []
        self.fits, self.bound_calls, self.ranks, self.scopes = [], [], [], {}
        self.stage, self.active_model = "setup", None

    def model(self, problem):
        key = id(problem)
        if key not in self.indices:
            self.indices[key] = len(self.models)
            # Retain references until the audit ends so recycled Python IDs cannot cause cache hits.
            self.models.append(problem)
        return self.indices[key]

    def rank(self, original):
        def audited(scan):
            self.stage = "rank"
            now = process_time_ns()
            try:
                nodes = original(scan)
                if len(nodes) != len(self.ranks):
                    raise ValueError("Did not expose exactly one original centre objective per unique node")
                self.ranks.sort(key=lambda row: row["score"])
                return nodes
            finally:
                self.scopes["rank_cpu_ns"] = process_time_ns()-now
                self.stage = "finalists"
        return audited

    def residual(self, original, minimum):
        def audited(problem, x):
            current = site(sys._getframe(1))
            model = self.model(problem)
            begin = process_time_ns()
            result = original(problem, x)
            cpu = process_time_ns()-begin
            if current is None:
                if self.stage == "rank":
                    self.ranks.append(dict(model=model, score=finite(result @ result)))
                return result
            _, role, refresh, prior = current
            score = finite(result @ result)
            self.objectives.append(dict(model=model, role=role, refresh=refresh, score=score,
                accepted=(score is not None and score < prior-minimum) if role == "trust" else None,
                point=x.tolist(), exact_position=x.tobytes().hex(), cpu_ns=cpu,
                result_sha256=sha256(result.tobytes()).hexdigest()))
            return result
        return audited

    def calculate(self, original):
        def audited(problem, x):
            model = self.model(problem)
            previous, self.active_model = self.active_model, model
            begin = process_time_ns()
            try:
                result = original(problem, x)
            finally:
                self.active_model = previous
            cpu = process_time_ns()-begin
            value = sha256(result["residual"].tobytes()+result["elevation"].tobytes()).hexdigest()
            self.calculations.append(dict(model=model, stage=self.stage, exact_position=x.tobytes().hex(),
                                          cpu_ns=cpu, result_sha256=value))
            return result
        return audited

    def bound(self, original):
        def audited(bound, response, matrix, *args, **kwargs):
            start = process_time_ns()
            activated = bound.counts["activated"]
            result = original(bound, response, matrix, *args, **kwargs)
            self.bound_calls.append(dict(model=self.active_model, stage=self.stage, native=bound.counts["activated"] > activated,
                                         cpu_ns=process_time_ns()-start, width=matrix.shape[1], rows=len(response),
                                         robust_updates=int(result["precision_iterations"])))
            return result
        return audited

    def fit(self, original):
        def audited(problem, *args, **kwargs):
            begin = process_time_ns()
            result = original(problem, *args, **kwargs)
            cpu = process_time_ns()-begin
            phases = [dict(parameters=r["parameters"].tolist(), score=finite(r["score"])) for r in result["history"]]
            counts = {k: result[k] for k in ("evaluations", "jacobian_refreshes", "secant_updates", "rejected_trials", "stopped")}
            self.fits.append(dict(model=self.model(problem), cpu_ns=cpu, history=phases, **counts))
            return result
        return audited

    def result(self, details):
        if len(self.fits) != 2*len(details["completed"]):
            raise ValueError("Observed fits do not match original two-refresh accounting")
        for branch, left, right in zip(details["completed"], self.fits[::2], self.fits[1::2], strict=True):
            for phase, (fit, key) in enumerate(zip((left, right), ("first_evaluations", "second_evaluations"), strict=True), 1):
                rows = [r for r in self.objectives if r["model"] == fit["model"]]
                if fit["evaluations"] != branch[key] or len(rows) != fit["evaluations"]:
                    raise ValueError("Optimizer requests do not close against the archived final count")
                counted = Counter(r["role"] for r in rows)
                fit.update(branch=branch["branch"], phase=phase, roles=dict(counted),
                           objective=duplicate_scope(rows), calculations=duplicate_scope([
                               r for r in self.calculations if r["model"] == fit["model"]]),
                           limits=dict(members=len(self.models[fit["model"]].members),
                                       active_rows=int(self.models[fit["model"]].keep.sum()),
                                       families=len(self.models[fit["model"]].labels)))
        return dict(fit_details=self.fits, objectives=self.objectives, calculations=self.calculations,
                    bounds=self.bound_calls, ranks=self.ranks, scopes=self.scopes)


def child(root):
    import cold_finalist_race

    original = cold_finalist_race.refine

    def observed(mode, prepared, region, bound):
        from leo.analysis.localization_v3 import position
        from tools.pipeline_eval.variants import compact_cavity_optimizer, v5_core

        if mode != "race" or type(bound).__name__ != "NativeBound":
            raise ValueError("Expected the original cold race and installed robust bound")
        census = Census()
        start = process_time_ns()
        with ExitStack() as patches:
            patches.enter_context(patch.object(type(bound), "__call__", census.bound(type(bound).__call__)))
            patches.enter_context(patch.object(v5_core, "ranked_initial_nodes", census.rank(v5_core.ranked_initial_nodes)))
            patches.enter_context(patch.object(position.NormalPosition, "residual", census.residual(
                position.NormalPosition.residual, compact_cavity_optimizer.MIN_DECREASE)))
            patches.enter_context(patch.object(position.NormalPosition, "calculate", census.calculate(position.NormalPosition.calculate)))
            patches.enter_context(patch.object(position, "fit", census.fit(position.fit)))
            _, _, _, cold = original(mode, prepared, region, bound)
        cold_cpu = process_time_ns()-start
        write(root / "cold.json", dict(cold=cold, fresh_cold_cpu_ns=cold_cpu, trace=census.result(cold),
                    prepared=prepared["status"], waveform_calls=0))
        raise ColdDone

    request = read(root / "request.json")
    inventory = STAGED / "selected/fast-scan-inputs" / f"{request['session']}.json"
    with patch.object(cold_finalist_race, "refine", observed):
        try:
            original_worker(root / "request.json", inventory, root / "cold-only")
        except ColdDone:
            return
    raise ValueError("Saved benchmark went beyond the original cold stage")


def archived():
    rows, full = {}, None
    for name, (directory, pin) in ARCHIVES.items():
        report = read(checked(directory / "joint-research-receipt.json", pin))
        if name == "full-mixed":
            full = report
        receipt, route = report["receipt"], report["route_details"]
        if (receipt["region"] != full["receipt"]["region"] or receipt["session_id"] != full["receipt"]["session_id"]
                or report["source_sha256"]["cold_finalist_race.py"] != PINS[HERE / "cold_finalist_race.py"]):
            raise ValueError("Signed case, supplied region or original finalist implementation changed")
        cold = route["cold"]
        prefix = sum(r["cpu_ns"] for r in cold["prefix"])/1e9
        finish = sum(r["cpu_ns"] for r in cold["completed"])/1e9
        total = route["cold_clocks"]["cpu_s"]
        owner = {}
        for arm in ARMS:
            a, b = [{r[0]: r[1:] for r in p["selected_rows"][arm]} for p in (full, report)]
            common = a.keys() & b.keys()
            owner[arm] = dict(total=len(b), shared=len(common), norad_changes=sum(a[k][0] != b[k][0] for k in common))
        rows[name] = dict(cold=cold, costs=dict(total_s=total, prefix_s=prefix, completions_s=finish,
                          setup_rank_and_other_s=total-prefix-finish), cold_rows=route["support"]["full_curved"],
                          checked_region=report["early_regional"][0]["result"], owners=owner,
                          selected_roles=report["selected_roles"], route=report["route"], digest=report["saved_digest"],
                          report_sha256=pin, sources=report["source_sha256"])
    return rows


def run(root):
    machine = host()
    for path, pin in PINS.items():
        checked(path, pin)
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use fresh tmpfs for the cold-only audit")
    historical = archived()
    request = read(CAUSAL / "request.json")
    packet, = (CAUSAL / "dense/fast-scan-automatic-work").glob("*/detections.json")
    candidate = read(checked(packet, request["native_pin"]))
    data, _ = inventory_for(candidate, read(CAUSAL / "seal.json")["binding"])
    if any(value != request[k] for k, value in data.items()):
        raise ValueError("Saved causal replay provenance changed")
    checked(Path(request["saved_file"]), "5a81919e3105ba2f38acfd401da91f828a9846f14b54de20d5e26165053e2c7b")
    root.mkdir()
    (root / "tmp").mkdir()
    write(root / "request.json", request)
    env = environment(STAGED)
    env["TMPDIR"] = str(root / "tmp")
    command = [RELEASE / "venv/bin/python", "-IB", __file__, "child", root]
    job = measure(command, env, root / "trace")
    write(root / "process.json", job)
    if job["exit_code"]:
        raise RuntimeError(job["stderr_tail"])
    fresh = read(root / "cold.json")
    matched = without_timers(fresh["cold"]) == without_timers(historical["causal"]["cold"])
    result = dict(machine=machine, historical=historical, replay=fresh, timing=job, exact_original_result=matched,
                  protocol_sha256=sha256((HERE / "causal-cold-audit-protocol.md").read_bytes()).hexdigest(),
                  source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    write(root / "result.json", result)
    if not matched:
        raise ValueError("Cold observer changed the archived calculation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "child"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    {"run": run, "child": child}[args.command](args.root)
