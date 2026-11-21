"""Compile and evaluate the symmetric held-symbol pair check on signed archived samples."""

import argparse
import ctypes as ct
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy as np

from ..variants.portable_field import Detector
from .full_v5_check import _load_case, _sha
from .original_kernel_trial import decode
from .reverse_glrt_reference import REPORT, digest, packed
from .reverse_glrt_report import read, write_csv
from .reverse_glrt_search import key
from .reverse_quarter_trial import null_samples
from .score_two_carrier import matching
from .single_scan_build import SOURCE
from .single_scan_inputs import reference
from .single_scan_roster import OUT, PRIOR, WORK
from .single_scan_trial import Native, Peak, original
from .timing_first_report import tab
from .two_carrier_conditional import injection
from .two_carrier_position import ORIGINAL
from .two_carrier_roster import WORK as PRIOR_WORK

CHECK = SOURCE.with_name("pilot_pair_check.c")
CLI = Path(__file__).with_name("checked_scan_iq.c")


class Checked(Native):
    def __init__(self, path, gate, asset):
        super().__init__(path, asset)
        self.gate = ct.CDLL(str(gate)).pilot_pair_check
        self.gate.argtypes = [ct.c_void_p, ct.c_int, ct.c_void_p, ct.POINTER(Peak), ct.c_int]
        self.pilot = np.ascontiguousarray(asset[-80000:]).copy()
        self.bytes += self.pilot.nbytes

    def run(self, w, lo, hi):
        lanes = []
        for lane in (0, 1):
            out = (Peak * 2)()
            n = self.lib.two_carrier_detect(self.ctx, w.samples.ctypes.data, lane, lo, hi, out)
            kept = self.gate(w.samples.ctypes.data, lane, self.pilot.ctypes.data, out, n)
            if not 0 <= kept <= n <= 2:
                raise ValueError("signed pair check failed")
            lanes.append([{k: getattr(p, k) for k, _ in Peak._fields_} for p in out[:kept]])
        return lanes


def build():
    first = read(OUT / "builds.json")["builds"]
    folder = WORK / "bin"
    target = folder / "pair-check.so"
    flags = ["cc", "-O3", "-std=c11", "-fno-math-errno", "-ffp-contract=off", "-shared", "-fPIC"]
    cmd = [*flags, str(CHECK), "-lm", "-o", str(target)]
    subprocess.run(cmd, check=True)
    artifacts = dict(gate=dict(path=str(target), sha256=_sha(target), command=cmd))
    for arch in ("host", "aarch64", "armv7"):
        command = first["single_scan-" + arch]["command"][:-2]
        command = [str(CLI) if Path(v).name == "two_carrier_iq.c" else v for v in command]
        command.insert(command.index("-lm"), str(CHECK))
        path = folder / ("checked-" + arch)
        command += ["-o", str(path)]
        subprocess.run(command, check=True)
        artifacts[arch] = dict(path=str(path), sha256=_sha(path), command=command)
    body = (
        packed(
            dict(
                artifacts=artifacts,
                base=_sha(OUT / "builds.json"),
                sources={
                    p.name: _sha(p) for p in (CHECK, CHECK.with_suffix(".h"), CLI, Path(__file__))
                },
                protocol=_sha(OUT / "PAIR-CHECK.md"),
                holdout=_sha(OUT / "pair-holdout/roster.json"),
            )
        )
        + b"\n"
    )
    seal = OUT / "checked-build.json"
    if seal.exists() and seal.read_bytes() != body:
        raise ValueError("checked receiver or reserved inputs changed")
    seal.write_bytes(body)


def make(method, edge, stack):
    if method == "original":
        return stack.enter_context(Detector(ORIGINAL, edge))
    asset = np.fromfile(PRIOR_WORK / "embedded" / (edge + ".f32"), dtype="<f4")
    if method == "checked":
        rx = Checked(WORK / "bin/single_scan-x86-64.so", WORK / "bin/pair-check.so", asset)
    else:
        rx = Native(WORK / "bin" / (method + "-x86-64.so"), asset)
    stack.callback(rx.close)
    return rx


def run_part(job):
    rows, cpu = job
    os.sched_setaffinity(0, {cpu})
    with ExitStack() as stack:
        bank = {}
        for panel, r in rows:
            name = key(r)
            _, _, w = decode(_load_case(r["case"]), r["visit"])
            if (
                w.acquisition["sample_start"] != r["counter"]
                or w.target["channel"] != r["channel"]
                or w.target["edge"] != r["edge"]
            ):
                raise ValueError("hardware opportunity changed")
            fresh = panel == "pair-holdout"
            methods = (
                ("original", "single_scan", "cancellation", "checked") if fresh else ("checked",)
            )
            order = int(r["id"][-12:], 16) % len(methods)
            methods = methods[order:] + methods[:order]
            mid = (
                w.target["rf_center_hz"]
                - w.target["lnb_lo_hz"]
                - w.acquisition["actual_if_center_hz"]
            )
            parent = read(
                OUT / ("pair-holdout/measurements" if fresh else "receivers") / (name + ".json")
            )
            if (parent["signed_iq"] if fresh else parent["iq"]) != w.iq_sha256:
                raise ValueError("samples differ from prior audit")
            null = null_samples(w.samples, int(r["id"][-12:], 16))
            data = dict(
                key=name,
                id=r["id"],
                rx=r["rx"],
                case=r["case"],
                panel=panel,
                iq=w.iq_sha256,
                null_iq="sha256:" + digest(null.tobytes()),
                cpu=cpu,
            )
            for kind, window in (("real", w), ("null", replace(w, samples=null))):
                results = {}
                for method in methods if kind == "real" else methods[::-1]:
                    tag = method, r["edge"]
                    if tag not in bank:
                        bank[tag] = make(*tag, stack)
                        if method == "original":
                            original(bank[tag], w)
                        else:
                            bank[tag].run(w, mid - 800000, mid + 800000)
                    obj = bank[tag]
                    cpu0, wall = process_time_ns(), perf_counter_ns()
                    peaks = (
                        original(obj, window)
                        if method == "original"
                        else obj.run(window, mid - 800000, mid + 800000)
                    )
                    results[method] = dict(
                        wall_ns=perf_counter_ns() - wall,
                        cpu_ns=process_time_ns() - cpu0,
                        lanes=peaks,
                    )
                data[kind] = results
                plain = results.get("single_scan", {}) if fresh else parent[kind]["single_scan"]
                for a, b in zip(results["checked"]["lanes"], plain["lanes"], strict=True):
                    if any(p not in b for p in a) or (len(b) <= 1 and a != b):
                        raise ValueError("conditional filter changed a measured carrier")
            if fresh:
                baseline = data["real"]["original"]["lanes"][r["rx"]]
                if bool(baseline) != r["old_pass"] or (
                    baseline
                    and abs(baseline[0]["hz"] - r["incumbent"]["fractional_tracking_cfo_hz"]) > 1e-5
                ):
                    raise ValueError("second holdout does not replay the archived original winner")
                ref = reference(w, r, OUT / "pair-holdout")
                (OUT / "pair-holdout/reference" / (name + ".json")).write_bytes(packed(ref) + b"\n")
            p = OUT / "checked" / (name + ".json")
            tmp = p.with_suffix(".partial")
            tmp.write_bytes(packed(data) + b"\n")
            tmp.replace(p)


def measure():
    roster = [
        (p, r) for p in ("pair-holdout", "fresh", "backward") for r in read(OUT / p / "roster.json")
    ]
    strict = {r["key"] for r in tab(PRIOR / "revised/checked-associations.csv")}
    roster.extend(
        ("satellite", r) for r in read(REPORT / "recovery/roster.json") if key(r) in strict
    )
    if len(roster) != 220 or len({(r["case"], r["visit"]) for _, r in roster}) != 220:
        raise ValueError("unexpected combined physical roster")
    for folder in (OUT / "checked", OUT / "pair-holdout/reference"):
        folder.mkdir(exist_ok=True)
    roster.sort(key=lambda t: digest(packed(["pair-check-run", t[1]["id"]])))
    cpus = (0, 2, 4)
    with ProcessPoolExecutor(max_workers=len(cpus)) as pool:
        list(pool.map(run_part, [(roster[i :: len(cpus)], cpu) for i, cpu in enumerate(cpus)]))


def mixtures():
    previous = tab(OUT / "mixtures.csv")
    frozen = {r["iq"]: r for r in tab(PRIOR / "injections.csv") if r["method"] == "pair"}
    rosters = {r["id"]: r for r in read(REPORT / "roster.json")}
    results = []
    with ExitStack() as stack:
        bank, windows = {}, {}
        for row in previous:
            m = frozen[row["iq"]]
            r = rosters[m["source_id"]]
            if r["edge"] not in bank:
                bank[r["edge"]] = make("checked", r["edge"], stack)
            if r["id"] not in windows:
                _, _, windows[r["id"]] = decode(_load_case(r["case"]), r["visit"])
            w = windows[r["id"]]
            raw, truth = injection(r, w, m)
            peaks = bank[r["edge"]].run(replace(w, samples=raw), -800000, 800000)[r["rx"]]
            hits = len(matching(peaks, truth))
            results.append(
                dict(
                    **row,
                    checked_found=hits,
                    checked_all=hits == len(truth),
                    checked_extras=len(peaks) - hits,
                )
            )
    write_csv(OUT / "checked-mixtures.csv", results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "measure", "mixtures"))
    {"build": build, "measure": measure, "mixtures": mixtures}[parser.parse_args().action]()
