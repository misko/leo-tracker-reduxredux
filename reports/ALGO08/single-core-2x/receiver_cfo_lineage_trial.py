"""Trace the three published DS30-0008 primary CFO changes through archived receivers."""

import argparse
import ctypes as ct
import json
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from struct import Struct
from unittest.mock import patch

import numpy as np

from leo.contracts.digests import canonical_digest
from tools import algo08_scan
from tools.pipeline_eval.variants import iq_stream
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver
from tools.pipeline_eval.variants.verifier_integration import Result

VISITS = ((2661, 1, 6), (3298, 0, 3), (3869, 0, 6))
BOUND = 64 * 1_600_000
BINDING = "a9ced88711b3a8174e47f7a337e2d5a497642c81eb4a7b5c877c2402d607f77a"
DETECTION_PINS = {
    "baseline": "a84e1396dbe60ebd49f6ee28687b22c189270fd2cc6a492455914c286e9bf2bc",
    "candidate": "e6cfc4bd307ac754faa26e2d9c04aa1fc407a7dc8c5b2e17e47f2b94edbcb53c",
}
FACTOR = Struct("<ii4d")
FIELDS = ("candidate_rank", "integer_epoch_sample", "fractional_epoch_offset_samples",
          "fractional_tracking_cfo_hz", "fractional_exact_score", "fractional_control_score")
RESTORATION_BUILDS = ("deployed", "packed-fractional", "floating-pgo", "paired-covariance")


class Scout(ct.Structure):
    _fields_ = [("epoch", ct.c_double), ("hz", ct.c_double), ("score", ct.c_double),
                ("confirmation", ct.c_int)]


class Request(ct.Structure):
    _fields_ = [("epoch", ct.c_int), ("hz", ct.c_double)]


class RefinementCapture(ct.Structure):
    _fields_ = [("iq", ct.c_void_p), ("pilot", ct.c_void_p), ("fir_output", ct.c_void_p),
                ("bank_count", ct.c_int), ("bank_calls", ct.c_int), ("scalar_count", ct.c_int),
                ("seeds", Request * 16), ("scalar", Request * 16),
                ("results", (ct.c_double * 4) * 16)]

    def receipt(self):
        if self.bank_calls != 1 or not self.iq or not self.pilot or not self.fir_output:
            raise ValueError("Missing native refinement boundary")
        return dict(full_rate_sha256=sha256(ct.string_at(self.iq, 200_000 * 8)).hexdigest(),
                    pilot_sha256=sha256(ct.string_at(self.pilot, 2816 * 8)).hexdigest(),
                    fir_sha256=sha256(ct.string_at(self.fir_output, 50_000 * 8)).hexdigest(),
                    requests=[(r.epoch, r.hz) for r in self.seeds[:self.bank_count]],
                    scalar_requests=[(r.epoch, r.hz) for r in self.scalar[:self.scalar_count]],
                    outputs=[list(row) for row in self.results[:self.bank_count]])


class RefinementProbe:
    def __init__(self, binary):
        library = ct.CDLL(str(binary.resolve()), mode=ct.RTLD_GLOBAL)
        pointer = ct.c_void_p
        self.setup = bind(library, "cfo_refine_readout_setup", None, pointer, pointer, pointer,
                          ct.POINTER(RefinementCapture))

    def select(self, receiver, capture=None):
        symbols = (getattr(receiver.lib, name, None) for name in
                   ("delay_decimate", "delay_refine", "delay_refine_bank"))
        self.setup(*(ct.cast(symbol, ct.c_void_p) for symbol in symbols), capture)


def bind(library, name, result, *arguments):
    call = getattr(library, name)
    call.restype, call.argtypes = result, list(arguments)
    return call


class PrimaryReadout:
    def __init__(self, receiver, asset, stack):
        library = receiver.lib
        ptr = ct.c_void_p
        create = bind(library, "timing_first_create", ptr, ct.c_int, ptr, ptr)
        clear = bind(library, "timing_first_free", None, ptr)
        self.scout = bind(library, "timing_first_detect", ct.c_int, ptr, ptr, ct.c_int,
                          ct.c_double, ct.c_double, ct.POINTER(Scout))
        self.timing = create(4, asset.ctypes.data, asset[4 * 13333:].ctypes.data)
        if not self.timing:
            raise ValueError("Could not initialize the scout")
        stack.callback(clear, self.timing)
        create = bind(library, "portable_verifier_create", ptr, ptr, ptr)
        clear = bind(library, "portable_verifier_free", None, ptr)
        self.load = bind(library, "portable_verifier_load", ct.c_int, ptr, ptr, ct.c_uint)
        self.factor = bind(library, "portable_verifier_factor", ct.c_int, ptr, ct.c_uint,
                           ct.POINTER(Result))
        self.reference = None
        if hasattr(library, "portable_verifier_factor_reference"):
            self.reference = bind(library, "portable_verifier_factor_reference", ct.c_int,
                                  ptr, ct.c_uint, ct.POINTER(Result))
        # The full receiver widens both Float32 pilot tables to double before
        # binding the verifier. The verifier retains these pointers.
        self.templates = asset[:4 * 13333].astype("<f8")
        self.verifier = create(self.templates.ctypes.data,
                               self.templates[2 * 13333:].ctypes.data)
        if not self.verifier:
            raise ValueError("Could not initialize the verifier")
        stack.callback(clear, self.verifier)

    def scout_seed(self, samples, lane, center):
        out = Scout()
        if self.scout(self.timing, samples.ctypes.data, lane, center - 800_000, center + 800_000,
                      ct.byref(out)) or not out.confirmation:
            raise ValueError("No confirmed primary scout on a published primary lane")
        return dict(epoch=out.epoch, integer=round(out.epoch) % 13333,
                    hz=out.hz, score=out.score, confirmation=out.confirmation)

    def verify(self, samples, lane, seed, *, reference=False):
        if self.load(self.verifier, samples.ctypes.data, lane):
            raise ValueError("Failed to load the verified lane")
        result = Result(acquired_hz=seed["hz"])
        verifier = self.reference if reference else self.factor
        if verifier(self.verifier, seed["integer"], ct.byref(result)):
            raise ValueError("Primary verification failed")
        factor = (0, seed["integer"], result.offset_samples,
                  seed["hz"] + result.fractional_residual_hz,
                  result.fractional_exact, result.fractional_control)
        return dict(factor=factor, fractional_residual_hz=result.fractional_residual_hz,
                    exact_grid=list(result.exact_grid), flags=result.flags)


def pin(path, expected):
    payload = path.read_bytes()
    if sha256(payload).hexdigest() != expected:
        raise ValueError(f"Saved input changed: {path}")
    return payload


def saved_rows(path, arm, batch):
    raw = json.loads(pin(path, DETECTION_PINS[arm]))
    source = raw["source"]
    if source["raw_recording_authority_digest"] != batch["runs"][arm]["raw_authority"]:
        raise ValueError("Detection bytes and paired raw authority disagree")
    keys = {(visit, lane) for visit, lane, _ in VISITS}
    rows = {(r["visit_index"], r["receiver_id"]): r for r in source["probes"]
            if (r["visit_index"], r["receiver_id"]) in keys}
    if rows.keys() != keys:
        raise ValueError("Missing frozen target lanes")
    for key, row in rows.items():
        if len(row["candidates"]) != 1 or row["candidates"][0]["candidate_rank"] != 0:
            raise ValueError(f"Expected the published primary factor at {key}")
    return rows


def load_samples(binding, bulk, batch, rows):
    case = json.loads(pin(binding, BINDING))["case"]
    targets = {visit for visit, _, _ in VISITS}
    found = {}
    offset = 0
    for item in case["recording"]["segments"]:
        path = bulk / item["path"]
        manifest = json.loads(pin(path, item["sha256"]))
        count = manifest["window_count"]
        wanted = sorted(targets.intersection(range(offset, offset + count)))
        if wanted and path.parents[1] != Path(batch["recording"]):
            raise ValueError("Frozen segment is from a different physical recording")
        for visit in wanted:
            with patch.multiple(iq_stream, MAX_CHUNK_PREFIX=BOUND, MAX_DECODE_BYTES=BOUND):
                window, = iq_stream.load_windows(
                    dict(recording_path=str(path), recording_sha256="sha256:" + item["sha256"]),
                    (visit - offset,),
                )
            _, lane, channel = next(entry for entry in VISITS if entry[0] == visit)
            saved = rows[visit, lane]
            acq, target = window.acquisition, window.target
            rf = acq["actual_if_center_hz"] + target["lnb_lo_hz"]
            if (window.receiver_ids != (0, 1) or window.samples.shape != (200000, 2, 2)
                    or window.sample_rate_hz != 10_000_000 or acq["global_visit"] != visit
                    or saved["valid_start_counter"] != acq["sample_start"]
                    or saved["actual_rf_hz"] != rf or channel != saved["channel"]
                    or channel != target["channel"] or target["edge"] != "lower"):
                raise ValueError("Saved visit does not match its archived stereo acquisition")
            center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
            found[visit] = dict(samples=window.samples, lane=lane, channel=channel, center=center,
                                iq_sha256=window.iq_sha256, segment_sha256=item["sha256"],
                                sequence=window.sequence)
        offset += count
        if targets == found.keys():
            return found
    raise ValueError("Missing requested archived stereo visits")


def same_factor(left, right):
    return FACTOR.pack(*left) == FACTOR.pack(*right)


def compare(samples, builds, asset, saved, stack, probe=None):
    prepared = []
    for name, path, digest in builds:
        pin(path, digest)
        receiver = Receiver(path, asset)
        stack.callback(receiver.close)
        prepared.append((name, receiver, PrimaryReadout(receiver, asset, stack)))
    evidence = []
    for visit, source in samples.items():
        iq, lane, center = (source[key] for key in ("samples", "lane", "center"))
        if probe is not None:
            probe.select(prepared[0][1])
        original_seed = prepared[0][2].scout_seed(iq, lane, center)
        readouts = []
        for name, receiver, readout in prepared:
            capture = None
            if probe is not None:
                probe.select(receiver)
            all_factors, _, _ = receiver.timed(iq, lane, center)
            exported, = [record for record in all_factors if record[0] == 0]
            if probe is not None and name != "deployed":
                capture = RefinementCapture()
                probe.select(receiver, capture)
            seed = readout.scout_seed(iq, lane, center)
            if capture is not None:
                probe.select(receiver)
            own = readout.verify(iq, lane, seed)
            verifier_reference = False
            if not same_factor(own["factor"], exported) and readout.reference is not None:
                own = readout.verify(iq, lane, seed, reference=True)
                verifier_reference = True
            if not same_factor(own["factor"], exported):
                raise ValueError(f"The independent stages do not reproduce {visit} on {name}")
            stage = dict(build=name, all_factors=all_factors, scout=seed, verification=own,
                         reference_fallback=verifier_reference,
                         same_deployed_seed=readout.verify(iq, lane, original_seed,
                                                          reference=verifier_reference),
                         deployed_verifier_on_seed=prepared[0][2].verify(iq, lane, seed))
            if capture is not None:
                stage["refinement"] = capture.receipt()
            readouts.append(stage)
        for name, arm in (("deployed", "baseline"), ("paired-covariance", "candidate")):
            stage = next(row for row in readouts if row["build"] == name)
            current = stage["verification"]["factor"]
            expected = tuple(saved[arm][visit, lane]["candidates"][0][key] for key in FIELDS)
            if not same_factor(current, expected):
                raise ValueError(f"The archived {name} receiver differs from the saved factor")
        evidence.append(dict({k: v for k, v in source.items() if k != "samples"},
                             visit=visit, builds=readouts))
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("plan", "pair", "baseline", "candidate", "binding", "assets", "bench", "bulk"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("--correction", type=Path)
    parser.add_argument("--refinement-probe", type=Path)
    args = parser.parse_args()
    if args.refinement_probe is not None and args.correction is None:
        parser.error("The native probe requires --correction to select refinement-bank builds")
    batch = json.loads(args.pair.read_bytes())
    saved = {arm: saved_rows(getattr(args, arm), arm, batch) for arm in DETECTION_PINS}
    for key, left in saved["baseline"].items():
        if ({k: v for k, v in left.items() if k != "candidates"} !=
                {k: v for k, v in saved["candidate"][key].items() if k != "candidates"}):
            raise ValueError("Published arms differ in visited RF-lane metadata")
    plan = json.loads(args.plan.read_bytes())
    builds = [(row["name"], getattr(args, row["root"]) / row["path"], row["sha256"])
              for row in plan]
    if batch["candidate_specification"]["detector_sha256"] != builds[-1][2]:
        raise ValueError("Expected the covariance receiver from the matched pair")
    correction = None
    if args.correction is not None:
        correction = json.loads((args.correction / "build.json").read_bytes())
        builds = [entry for entry in builds if entry[0] in RESTORATION_BUILDS]
        builds += [
            ("packed-cancellation", args.correction / "packed.so", correction["packed_sha256"]),
            ("restored-delay-product", args.correction / "restored.so",
             correction["corrected_sha256"]),
        ]
    raw = pin(args.assets / "lower.f32", algo08_scan.PINS["lower.f32"])
    asset = np.frombuffer(raw, dtype="<f4")
    samples = load_samples(args.binding, args.bulk, batch, saved["baseline"])
    probe = None if args.refinement_probe is None else RefinementProbe(args.refinement_probe)
    with ExitStack() as stack:
        evidence = compare(samples, builds, asset, saved, stack, probe)
    print(json.dumps(dict(plan=plan, plan_digest=canonical_digest(plan), correction=correction,
                          detections=DETECTION_PINS, rows=evidence), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
