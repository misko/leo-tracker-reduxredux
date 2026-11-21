"""Paired raw receiver comparison on the waveform benchmark and prospective recording visits."""

import argparse
import json
import os
import zipfile
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from time import perf_counter, process_time

import numpy as np

from ..variants import two_carrier
from ..variants.iq_stream import IQWindow
from ..variants.portable_field import Detector
from .full_v5_check import _load_case, _sha
from .original_kernel_trial import decode
from .reverse_glrt_reference import digest, packed
from .reverse_glrt_report import read
from .reverse_glrt_search import key
from .reverse_quarter_trial import null_samples
from .timing_first_roster import OUT as PREVIOUS
from .timing_first_trial import inventories
from .two_carrier_position import ORIGINAL, RawVerifier, peak, sources
from .two_carrier_roster import OUT, WORK

MODES = ("original", "single", "pair")


class Trial:
    def __init__(self, edge, binaries):
        self.field = Detector(ORIGINAL, edge)
        self.receiver = two_carrier.Receiver(binaries, edge)
        self.raw = RawVerifier(edge)

    def close(self):
        self.field.__exit__(None, None, None)
        self.receiver.__exit__(None, None, None)
        self.raw.close()

    def run(self, w, order):
        mid = (
            w.target["rf_center_hz"] - w.target["lnb_lo_hz"] - w.acquisition["actual_if_center_hz"]
        )
        result = {}
        for mode in order:
            lanes = []
            cpu, wall = process_time(), perf_counter()
            if mode == "original":
                for lane, out in enumerate(self.field(w, (0, 1))):
                    passed = sorted(
                        (
                            c
                            for c in out.candidates
                            if c.fractional_margin is not None and c.fractional_margin >= 0.025
                        ),
                        key=lambda c: (-c.fractional_margin, c.candidate_rank),
                    )
                    peaks = []
                    for c in passed:
                        p = dict(
                            epoch=c.fractional_frame_phase_sample,
                            hz=c.fractional_tracking_cfo_hz,
                            margin=c.fractional_margin,
                            rank=c.candidate_rank,
                        )
                        if not any(two_carrier.same(p, q) for q in peaks):
                            peaks.append(p)
                    cost = [x for x in self.field.attempts if x["lane"] == lane]
                    lanes.append(
                        dict(
                            peaks=peaks,
                            proposals=peaks,
                            cpu_s=sum(
                                (v["coarse_cpu_ns"] + v["verify_cpu_ns"]) * 1e-9 for v in cost
                            ),
                        )
                    )
            else:
                for lane in (0, 1):
                    start = process_time()
                    if mode == "single":
                        first = self.receiver.base(w.samples, lane, mid - 800000.0, mid + 800000.0)
                        proposals = [first] if first else []
                    else:
                        proposals = self.receiver(w.samples, lane, mid - 800000.0, mid + 800000.0)
                    acquisition = process_time() - start
                    factors, checks = self.raw.factors(proposals, w.samples, lane)
                    elapsed = process_time() - start
                    verified = sorted(
                        (
                            dict(**peak(f), rank=f["candidate_rank"], margin=f["fractional_margin"])
                            for f in factors
                        ),
                        key=lambda p: (-p["margin"], p["rank"]),
                    )
                    lanes.append(
                        dict(
                            cpu_s=elapsed,
                            acquisition_cpu_s=acquisition,
                            proposals=proposals,
                            peaks=verified,
                            checks=checks,
                        )
                    )
            result[mode] = dict(
                lanes=lanes, wall_s=perf_counter() - wall, cpu_s=process_time() - cpu
            )
        return result


def from_archive(row, item):
    z, v = item
    raw = z.read(v["file"])
    if (
        "sha256:" + digest(raw) != v["sha256"]
        or v["physical_id"] != row["id"]
        or int(v["hardware_sample_counter"]) != row["counter"]
        or v["evaluated_antenna"] != row["rx"]
        or v["edge"] != row["edge"]
        or v["shape"] != [200000, 2, 2]
        or v["dtype"] != "<i2"
        or v["sample_rate_hz"] != 10_000_000
    ):
        raise ValueError("input archive no longer matches the raw opportunity")
    return IQWindow(
        v["window_sequence"],
        np.frombuffer(raw, dtype="<i2").reshape(200000, 2, 2),
        (0, 1),
        v["sample_rate_hz"],
        v["acquisition"],
        v["target"]["target_id"],
        v["target"],
        v["sha256"],
    )


def run_part(job):
    todo, cpu, folder, binaries, archives = job
    os.sched_setaffinity(0, {cpu})
    trials = {}
    with ExitStack() as stack:
        bank = {}
        for path in archives:
            z = stack.enter_context(zipfile.ZipFile(path))
            for v in json.loads(z.read("index.json"))["visits"]:
                if v["key"] in bank:
                    raise ValueError("duplicate raw visit")
                bank[v["key"]] = z, v
        try:
            for row, cohort, expected_iq in todo:
                ident = key(row)
                target = folder / (ident + ".json")
                if target.exists():
                    continue
                if ident in bank:
                    w = from_archive(row, bank[ident])
                else:
                    _, _, w = decode(_load_case(row["case"]), row["visit"])
                if (
                    w.iq_sha256 != expected_iq
                    or w.acquisition["sample_start"] != row["counter"]
                    or w.target["channel"] != row["channel"]
                    or w.target["edge"] != row["edge"]
                ):
                    raise ValueError("reference grid and runtime input differ")
                if row["edge"] not in trials:
                    trials[row["edge"]] = Trial(row["edge"], binaries)
                null = null_samples(w.samples, int(row["id"][-12:], 16))
                null_hash = "sha256:" + digest(null.tobytes())
                random = replace(w, samples=null, iq_sha256=null_hash)
                index = int(row["id"][-4:], 16) % 3
                order = MODES[index:] + MODES[:index]
                raw = trials[row["edge"]].run(w, order)
                control = trials[row["edge"]].run(random, order)
                old = raw["original"]["lanes"][row["rx"]]["peaks"]
                incumbent = row["incumbent"]
                if bool(old) != bool(incumbent) or (
                    old and abs(old[0]["hz"] - incumbent["fractional_tracking_cfo_hz"]) > 1e-5
                ):
                    raise ValueError("original GLRT does not reproduce the archived winner")
                for data in (raw, control):
                    for lane in (0, 1):
                        one = data["single"]["lanes"][lane]
                        two = data["pair"]["lanes"][lane]
                        if one["proposals"] != two["proposals"][:1] or one["peaks"] != [
                            v for v in two["peaks"] if v["rank"] == 0
                        ]:
                            raise ValueError("single and two-carrier primary measurements differ")
                temp = target.with_suffix(".partial")
                temp.write_bytes(
                    packed(
                        dict(
                            key=ident,
                            id=row["id"],
                            case=row["case"],
                            visit=row["visit"],
                            rx=row["rx"],
                            cohort=cohort,
                            cpu=cpu,
                            iq=w.iq_sha256,
                            null_iq=null_hash,
                            real=raw,
                            null=control,
                        )
                    )
                    + b"\n"
                )
                temp.replace(target)
        finally:
            for trial in trials.values():
                trial.close()
    print("paired measurements", cpu, len(todo), flush=True)


def run(out, work, cpus):
    binaries = two_carrier.build(work)
    archive = read(PREVIOUS / "iq-bundles.json")
    paths = [Path(a["path"]) for a in archive.values()]
    if any(_sha(Path(a["path"])) != a["sha256"] for a in archive.values()):
        raise ValueError("I/Q bundle changed")
    panels = dict(inventories(PREVIOUS), prospective=out / "prospective")
    rows = []
    for prefix, folder in panels.items():
        if _sha(folder / "roster.json") != read(folder / "manifest.json")["roster_sha256"]:
            raise ValueError("roster changed")
        for r in read(folder / "roster.json"):
            m = read(folder / "measurements" / (key(r) + ".json"))
            if (
                m["row_id"] != r["id"]
                or _sha(folder / "grids" / (key(r) + ".npz")) != m["grid_sha256"]
            ):
                raise ValueError("reference grid changed")
            rows.append((r, prefix, m["signed_iq"]))
    if len(rows) != len({(v[0]["case"], v[0]["visit"]) for v in rows}):
        raise ValueError("physical visit repeated")
    rows.sort(key=lambda job: digest(packed(["two-carrier-run-v1", job[0]["id"]])))
    folder = out / "measurements"
    folder.mkdir(exist_ok=True, parents=True)
    provenance = dict(
        sources=sources(out, binaries),
        measurement_source=_sha(Path(__file__)),
        archives=archive,
        rosters={k: _sha(v / "roster.json") for k, v in panels.items()},
        cpus=cpus,
    )
    seal = folder / "lock.json"
    if seal.exists() and read(seal) != provenance:
        raise ValueError("frozen paired experiment changed")
    seal.write_bytes(packed(provenance) + b"\n")
    with ProcessPoolExecutor(max_workers=len(cpus)) as pool:
        list(
            pool.map(
                run_part,
                [(rows[i :: len(cpus)], c, folder, binaries, paths) for i, c in enumerate(cpus)],
            )
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, default=OUT)
    p.add_argument("--work", type=Path, default=WORK)
    p.add_argument("--cpus", type=int, nargs="+", default=[1, 3, 5])
    a = p.parse_args()
    if len(set(a.cpus)) != len(a.cpus) or not set(a.cpus) <= os.sched_getaffinity(0):
        raise ValueError("invalid worker CPUs")
    run(a.report, a.work, a.cpus)
