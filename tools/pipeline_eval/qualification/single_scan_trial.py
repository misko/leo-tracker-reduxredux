"""Compare resident original, one-scan and cancellation receivers on the same stereo visits."""

import ctypes as ct
import json
import os
import zipfile
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy as np

from ..variants.portable_field import Detector
from .full_v5_check import _sha
from .reverse_glrt_reference import REPORT, digest, packed
from .reverse_glrt_report import read
from .reverse_glrt_search import key
from .reverse_quarter_trial import null_samples
from .score_two_carrier import compatible
from .single_scan_roster import OUT, PRIOR
from .timing_first_report import tab
from .two_carrier_position import ORIGINAL
from .two_carrier_roster import WORK as PRIOR_WORK
from .two_carrier_trial import from_archive

METHODS = ("original", "single_scan", "cancellation")


class Peak(ct.Structure):
    _fields_ = [(s, ct.c_double) for s in ("epoch", "hz", "margin")] + [
        ("rank", ct.c_int),
        ("confirmation", ct.c_int),
    ]


class Native:
    def __init__(self, path, asset):
        self.lib = lib = ct.CDLL(str(path))
        lib.two_carrier_create.argtypes = [ct.c_void_p]
        lib.two_carrier_create.restype = ct.c_void_p
        lib.two_carrier_free.argtypes = [ct.c_void_p]
        lib.two_carrier_free.restype = None
        lib.two_carrier_bytes.argtypes = [ct.c_void_p]
        lib.two_carrier_bytes.restype = ct.c_size_t
        lib.two_carrier_detect.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_int,
            ct.c_double,
            ct.c_double,
            ct.POINTER(Peak),
        ]
        self.ctx = lib.two_carrier_create(asset.ctypes.data)
        if not self.ctx:
            raise MemoryError("receiver initialization failed")
        self.bytes = lib.two_carrier_bytes(self.ctx)

    def close(self):
        self.lib.two_carrier_free(self.ctx)

    def run(self, w, lo, hi):
        lanes = []
        for lane in (0, 1):
            result = (Peak * 2)()
            n = self.lib.two_carrier_detect(self.ctx, w.samples.ctypes.data, lane, lo, hi, result)
            if not 0 <= n <= 2:
                raise ValueError("native acquisition failed")
            lanes.append(
                [{field: getattr(p, field) for field, _ in Peak._fields_} for p in result[:n]]
            )
        return lanes


def original(receiver, w):
    lanes = []
    for lane in receiver(w, w.receiver_ids):
        passed = sorted(
            (
                c
                for c in lane.candidates
                if c.fractional_margin is not None and c.fractional_margin >= 0.025
            ),
            key=lambda c: (-c.fractional_margin, c.candidate_rank),
        )
        unique = []
        for c in passed:
            peak = dict(
                hz=c.fractional_tracking_cfo_hz,
                epoch=c.fractional_frame_phase_sample,
                margin=c.fractional_margin,
                rank=c.candidate_rank,
            )
            if not any(compatible(peak, p) for p in unique):
                unique.append(peak)
        lanes.append(unique)
    return lanes


def paired(w, receivers, order):
    mid = w.target["rf_center_hz"] - w.target["lnb_lo_hz"] - w.acquisition["actual_if_center_hz"]
    answer = {}
    for method in order:
        cpu, wall = process_time_ns(), perf_counter_ns()
        obj = receivers[method]
        lanes = (
            original(obj, w) if method == "original" else obj.run(w, mid - 800000.0, mid + 800000.0)
        )
        answer[method] = dict(
            wall_ns=perf_counter_ns() - wall, cpu_ns=process_time_ns() - cpu, lanes=lanes
        )
    return answer


def process(job):
    tasks, cpu, output, builds, paths = job
    os.sched_setaffinity(0, {cpu})
    with ExitStack() as stack:
        samples = {}
        for path in paths:
            z = stack.enter_context(zipfile.ZipFile(path))
            for v in json.loads(z.read("index.json"))["visits"]:
                if v["key"] in samples:
                    raise ValueError("duplicate raw visit")
                samples[v["key"]] = z, v
        bank = {}
        for panel, r in tasks:
            name = key(r)
            target = output / (name + ".json")
            w = from_archive(r, samples[name])
            edge = r["edge"]
            if edge not in bank:
                asset = np.fromfile(PRIOR_WORK / "embedded" / (edge + ".f32"), dtype="<f4")
                objects = {"original": stack.enter_context(Detector(ORIGINAL, edge))}
                for m in METHODS[1:]:
                    obj = Native(builds["builds"][m + "-x86-64"]["path"], asset)
                    stack.callback(obj.close)
                    objects[m] = obj
                bank[edge] = objects
                # Remove lazy allocation and initialization from resident timing.
                paired(w, objects, METHODS)
            offset = int(r["id"][-12:], 16) % len(METHODS)
            order = METHODS[offset:] + METHODS[:offset]
            null = null_samples(w.samples, int(r["id"][-12:], 16))
            random = replace(w, samples=null, iq_sha256="sha256:" + digest(null.tobytes()))
            real = paired(w, bank[edge], order)
            control = paired(random, bank[edge], order[::-1])
            old = real["original"]["lanes"][r["rx"]]
            if bool(old) != r["old_pass"] or (
                old and abs(old[0]["hz"] - r["incumbent"]["fractional_tracking_cfo_hz"]) > 1e-5
            ):
                raise ValueError("original detector did not reproduce the archived visit")
            if panel == "satellite":
                previous = read(PRIOR / "measurements" / target.name)
                expected = [a["peaks"] for a in previous["real"]["pair"]["lanes"]]
                for xx, yy in zip(real["cancellation"]["lanes"], expected, strict=True):
                    if len(xx) != len(yy) or any(
                        abs(p["hz"] - q["hz"]) > 0.001 or abs(p["epoch"] - q["epoch"]) > 1.0e-5
                        for p, q in zip(xx, yy, strict=True)
                    ):
                        raise ValueError("standalone baseline differs from the sealed experiment")
            answer = dict(
                key=name,
                panel=panel,
                case=r["case"],
                rx=r["rx"],
                id=r["id"],
                iq=w.iq_sha256,
                null_iq=random.iq_sha256,
                cpu=cpu,
                order=order,
                real=real,
                null=control,
                workspace_bytes={m: bank[edge][m].bytes for m in METHODS[1:]},
            )
            temp = target.with_suffix(".partial")
            temp.write_bytes(packed(answer) + b"\n")
            temp.replace(target)


def run(out, cpus=(0, 2, 4)):
    builds = read(out / "builds.json")
    for recipe in builds["builds"].values():
        if _sha(Path(recipe["path"])) != recipe["sha256"]:
            raise ValueError("C receiver binary changed")
    for edge, value in builds["assets"].items():
        if _sha(PRIOR_WORK / "embedded" / (edge + ".f32")) != value:
            raise ValueError("receiver pilot asset changed")
    fresh = read(out / "inputs.json")
    strict_zip = PRIOR / "revised/revised-satellite-iq.zip"
    if (
        _sha(Path(fresh["path"])) != fresh["sha256"]
        or _sha(strict_zip) != read(PRIOR / "revised/verification.json")["signed_iq_sha256"]
    ):
        raise ValueError("I/Q archive changed")
    strict = {r["key"] for r in tab(PRIOR / "revised/checked-associations.csv")}
    tasks = [(p, r) for p in ("fresh", "backward") for r in read(out / p / "roster.json")]
    tasks.extend(
        ("satellite", r) for r in read(REPORT / "recovery/roster.json") if key(r) in strict
    )
    if len(tasks) != 156 or len({(r["case"], r["visit"]) for _, r in tasks}) != len(tasks):
        raise ValueError("unexpected visit count")
    tasks.sort(key=lambda item: digest(packed(["single-scan-run-v1", item[1]["id"]])))
    output = out / "receivers"
    output.mkdir(exist_ok=True)
    signature = dict(
        builds=_sha(out / "builds.json"),
        source=_sha(Path(__file__)),
        inputs=_sha(out / "inputs.json"),
        original=_sha(ORIGINAL),
        strict=_sha(strict_zip),
        cpus=cpus,
    )
    body = packed(signature) + b"\n"
    lock = output / "lock.json"
    if lock.exists() and lock.read_bytes() != body:
        raise ValueError("frozen receiver evaluation changed")
    lock.write_bytes(body)
    todo = [t for t in tasks if not (output / (key(t[1]) + ".json")).exists()]
    paths = (Path(fresh["path"]), strict_zip)
    with ProcessPoolExecutor(max_workers=len(cpus)) as pool:
        list(
            pool.map(
                process,
                [(todo[i :: len(cpus)], c, output, builds, paths) for i, c in enumerate(cpus)],
            )
        )


if __name__ == "__main__":
    run(OUT)
