"""Add exact prefix reuse plus anchored full lanes to a sealed member A/B."""

import argparse
from collections import Counter
from contextlib import contextmanager
import ctypes as ct
from functools import partial
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ANCHOR = Path("/dev/shm/leo-v3-anchored-raw/reports/ALGO08/v3")
STAGE_SHA = "08e9f0d24b0105837d38039fdb326179f9d23b3609f7d301dac5150a388de1a6"
ANCHOR_SHA = "295204e3a5f20bc642a41cbef186e587b985f02062d8789efe7190c3fed3afda"
PACK = Path("/dev/shm/leo-anchored-cfo-raw-pack01")
PACK_SHA = "0d590b0c7e4ffc468fb17804146362b8534d33d115d83055ae7bbc1dafd967a9"
AB = Path("/dev/shm/leo-anchored-cfo-stage-results01")
AB_SHA = "8b7b9aaf1c914d2ec9e6ac9b1c993533da7599a25dcf5a0743650513452c70a8"
PREFIX = Path("/dev/shm/leo-v3-prefix-refine-results-02")
SHORT_SHA = "52cf2d62b6bde206a7d8bd2647c4910c0f271256da675347201c49edbc7234b9"
REFINE_SHA = "6f007dfe0f92706f1fdd41fae89e5821ab98f646de1e337e0e73139072d8cd28"


def checked(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"Unreviewed staged ingredient {path}")
    return data


def load_exact(name, pin):
    path = ANCHOR/(name+".py")
    source = checked(path, pin)
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), vars(module))
    return module


def dimensions(handle):
    method = handle.portable_verifier_workspace_bytes
    method.argtypes, method.restype = (), ct.c_size_t
    return method()


def prefix_call(path, full, library, captures, audit):
    invoke = path.native.lib.short_primary_and_cfo
    invoke.argtypes = (ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double, ct.c_void_p, ct.c_void_p, ct.c_void_p,
                       ct.POINTER(ct.c_double), ct.POINTER(ct.c_int), ct.POINTER(ct.c_uint64))
    invoke.restype = ct.c_int
    context = ct.cast(full.native.ctx, ct.POINTER(ct.c_void_p))[1]
    callback = ct.cast(library.short_cfo_reuse, ct.c_void_p)
    if len({dimensions(native) for native in (path.native.lib, full.native.lib, library)}) != 1:
        raise ValueError("The paired native verifier layouts differ")

    def capture(ctx, iq, lane, low, high, out):
        result, used, cpu = (ct.c_double*8)(), ct.c_int(), ct.c_uint64()
        status = invoke(ctx, iq, lane, low, high, out, context, callback, result, ct.byref(used), ct.byref(cpu))
        if status == 1:
            if lane in captures or used.value not in (-1, 0, 8):
                raise ValueError("Prefix certificate escaped its current stereo lane")
            row = tuple(getattr(out[0], key) for key, _ in path.factor._fields_)
            captures[lane] = (row, tuple(result) if used.value >= 0 else None)
            audit.update(attempted=1, cpu_ns=cpu.value, reused_frames=max(0, used.value),
                         independent_fallbacks=int(used.value == 0), unavailable=int(used.value < 0))
        return status

    return capture


def hybrid_module(anchored, paths):
    original = anchored.exact
    mixed = original.mixed
    library = ct.CDLL(str(PREFIX/"full/tail.so"))

    class Hybrid(mixed.MixedApertureDetector):
        def __init__(self, short_binary, short_sha256, *, full_coverage, policy):
            super().__init__(short_binary, short_sha256, full_coverage=full_coverage)
            self.phase, self.lanes, self.prefix = {}, {}, Counter()
            self.rule_cpu = self.rule_wall = 0
            self.policy = policy

        @contextmanager
        def detector(self, method, edge, *, binary=None, pilot=None):
            original_path = mixed.NativePath
            observations = {}
            full = None

            def open_path(path, asset, mode):
                nonlocal full
                expected = binary if mode == "full" else self.short_binary
                if Path(path).resolve() != Path(expected).resolve():
                    raise ValueError("Unexpected original native path during composition")
                if mode == "full":
                    counts = self.phase.setdefault(edge, Counter())
                    full = anchored.GuardedPath(paths["full.so"], asset, mode, counts)
                    return full
                if mode != "short_primary" or full is None:
                    raise ValueError("The original mixed path must bind the common full pilot first")
                short = original_path(PREFIX/"prefix-primary.so", asset, mode)
                try:
                    short.call = prefix_call(short, full, library, observations, self.prefix)
                except BaseException:
                    short.close()
                    raise
                return short

            context = super().detector(method, edge, binary=binary, pilot=pilot)
            with patch.object(mixed, "NativePath", open_path):
                receive = context.__enter__()
            try:
                def refined(window):
                    if observations:
                        raise ValueError("Found stale signed refinement state before stereo receive")
                    probes = receive(window)
                    if not observations:
                        return probes
                    target, initial = window.target, window.acquisition
                    tune = target["rf_center_hz"]-target["lnb_lo_hz"]-initial["actual_if_center_hz"]
                    for i, probe in enumerate(probes):
                        lane = probe["receiver_id"]
                        if lane not in observations:
                            continue
                        cpu, wall = process_time_ns(), perf_counter_ns()
                        measured, diagnostic = observations.pop(lane)
                        candidate, = probe["candidates"]
                        if measured != tuple(candidate[k] for k in original.FIELDS):
                            raise ValueError("Prefix diagnostics do not bind the current verified primary")
                        fixed = SimpleNamespace(diagnostics=lambda *_: diagnostic)
                        policy = SimpleNamespace(refiner=fixed, amend=self.policy.amend)
                        probes[i], why, changed = original.refined_probe(probe, window.samples, full, policy, tune)
                        self.lanes.setdefault((edge, lane), Counter()).update({"attempted": 1, "changed": int(changed), why: 1})
                        self.rule_cpu += process_time_ns()-cpu
                        self.rule_wall += perf_counter_ns()-wall
                    if observations:
                        raise ValueError("One native refinement could not reach its measured output lane")
                    return probes

                yield refined
            finally:
                context.__exit__(*sys.exc_info())

        def receipt(self):
            return super().receipt() | {
                "cfo_refinement": dict(cpu_ns=self.rule_cpu, wall_ns=self.rule_wall, lanes=[
                    dict(edge=edge, receiver_id=lane, counts=dict(data)) for (edge, lane), data in sorted(self.lanes.items())]),
                "exact_prefix": dict(self.prefix),
                "anchored_full": [dict(edge=edge, **data) for edge, data in sorted(self.phase.items())]}

    def invoke(argv):
        def recipe(original_receiver, parent):
            return anchored.ORIGINAL_RECIPE(original_receiver, parent) | {"exact_prefix_cfo": dict(
                version=1, entry_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                short_producer_sha256=SHORT_SHA, linked_refiner_sha256=REFINE_SHA,
                full_anchor_sha256=anchored.LIBRARIES["full.so"], anchor_pack_sha256=PACK_SHA,
                prefix_frames=8, original_gather_fallback=True, anchored_apertures=["full"])}

        with (patch.object(original, "RefinedShortDetector", Hybrid), patch.object(original, "recipe", recipe)):
            original.run_cli(paths["original-cfo.so"], argv)

    return invoke


def worker(output):
    sys.path.insert(0, str(HERE))
    anchor = load_exact("anchored_cfo_raw", ANCHOR_SHA)
    stage = load_exact("anchored_cfo_stage", STAGE_SHA)
    checked(PACK/"pack.json", PACK_SHA)
    checked(PREFIX/"prefix-primary.so", SHORT_SHA)
    checked(PREFIX/"full/tail.so", REFINE_SHA)
    paths = anchor.verified_pack(PACK)
    stage.worker("candidate-c", PACK, output, launch=hybrid_module(anchor, paths))


def disjoint(receipt):
    native = receipt["receiver_audit"]["native"]
    embedded = native.get("exact_prefix", {}).get("cpu_ns", 0)
    original = native["native_cpu_ns"]
    extra = native["cfo_refinement"]["cpu_ns"]
    if not 0 <= embedded <= original["short_primary"]:
        raise ValueError("The nested prefix CPU was not inside the short-call clock")
    return dict(full_lane_cpu_ns=original["full"], primary_cpu_ns=original["short_primary"]-embedded,
                refinement_cpu_ns=extra+embedded, all_native_and_refinement_cpu_ns=sum(original.values())+extra)


def verify_partition(original, anchored, hybrid, a, b, c):
    short = ("short_primary", a, original)
    full = ("full", b, anchored)
    for mode, expected, native in (short, full):
        old = {(r["visit"], r["lane"]): r for r in expected["vectors"] if r["mode"] == mode}
        new = {(r["visit"], r["lane"]): r for r in c["vectors"] if r["mode"] == mode}
        if old != new:
            raise ValueError(f"The hybrid changed {mode} from its actual native comparator")
        wanted, actual = ([r for r in packet["source"]["probes"] if (r["visit_index"], r["receiver_id"]) in old]
                          for packet in (native, hybrid))
        if wanted != actual:
            raise ValueError(f"The realized {mode} continuation or emitted factor changed")


def run(root):
    if os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise ValueError("Use the shared low-priority one-core research slot")
    sys.path.insert(0, str(HERE))
    comparator = load_exact("anchored_cfo_stage", STAGE_SHA)
    ab = json.loads(checked(AB/"receipt.json", AB_SHA))
    root.mkdir()
    results = []
    for repeat in (1, 2):
        target = root/f"{repeat}-candidate-c"
        resources = resource.getrusage(resource.RUSAGE_CHILDREN)
        start = perf_counter_ns()
        subprocess.run([sys.executable, "-IB", __file__, "worker", target], timeout=20, check=True)
        wall = perf_counter_ns()-start
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        read = lambda p: json.loads(p.read_bytes())
        a, b, c = (read(p/"scope-receipt.json") for p in (AB/f"{repeat}-exact", AB/f"{repeat}-anchored", target))
        original, anchored, hybrid = (read(p/"detections.json") for p in (AB/f"{repeat}-exact", AB/f"{repeat}-anchored", target))
        for receipt, native, archived in zip((a,b), (original,anchored), ab["arms"], strict=True):
            expected = archived["receipt"]
            keys = ("iq", "vectors", "recipe", "native_sha256", "prefix_inventory")
            if any(receipt[k] != expected[k] for k in keys):
                raise ValueError("Archived original member run changed")
            # Production detector JSON is already the canonical serialized data.
            mode = "exact" if receipt is a else "anchored"
            path = AB/f"{repeat}-{mode}"/"detections.json"
            checked(path, receipt["native_sha256"][7:])
        verify_partition(original, anchored, hybrid, a, b, c)
        applied = c["receiver_audit"]["native"]["exact_prefix"]
        if applied["attempted"] != 45 or applied["reused_frames"] != 360 or applied["independent_fallbacks"]:
            raise ValueError("The hybrid did not reproduce the held prefix census")
        results.append(dict(whole_process_wall_ns=wall, through_seal=c["elapsed_through_seal"],
                            whole_process_cpu_s=(after.ru_stime-resources.ru_stime)+(after.ru_utime-resources.ru_utime),
                            input_blocks=after.ru_inblock-resources.ru_inblock, same_lanes_as_original=True,
                            original_comparison=comparator.compare(original, hybrid, a, c),
                            anchored_comparison=comparator.compare(anchored, hybrid, b, c),
                            disjoint_cpu={mode: disjoint(receipt) for mode, receipt in zip(("A", "B", "C"), (a,b,c), strict=True)},
                            receipt=c))
    comparator.write(root/"result.json", dict(references_sha256=AB_SHA, archived_ab=ab["paired"],
                     runs=results, one_staged_member=True, position_measured=False))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("run", "worker"))
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    (run if args.mode == "run" else worker)(args.output)
