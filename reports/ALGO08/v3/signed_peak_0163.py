"""Read the two frozen DS30-0163 peak neighborhoods with the original exact verifier."""

import argparse
from contextlib import contextmanager
import ctypes as ct
import gzip
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
ROOT = Path("/tmp/leo-v3-0163-first-idle-resume01")
STAGE = ROOT / "fast8-auto-20261115-233248-20797f02-1-lower-segment-00000000"
PAYLOAD = Path("/opt/leo-algo08/algo08v3/payload")
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
FULL = PAYLOAD / "receiver.so"
SPARSE = Path("/tmp/leo-v3-short-rank-transfer-DS30-0016-01/sparse/use.so")
DIRECTED = Path("/var/tmp/leo-v3-directed-pass2/use.so")
PILOT = RELEASE / "assets/lower.f32"
PINS = {
    FULL: "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5",
    SPARSE: "c5b57b0602e81a6a85c14caf648eb12341f098d09915b4d3f705094ed309574c",
    DIRECTED: "d66ab774f8844fbaec21e28eb2c6ecf42e57152705ea5d4677ca8f032d52397d",
    PILOT: "1b98937cbd87fd5f27b82e4d535512ca5ee12b33a64a6bae90e07ec041368adb",
    ROOT / "resumed-stage.json": "3624c9ac33bce434fd141fc3a1a0d2f47857dd429752301cb29892753b9c00d6",
    HERE / "measurements/first-member-0163-resume-acquisition.json.gz": "5cf1c7e7c785c84913851515242ddcd434b02ee4de33c1a244e3f53732ee7c8f",
    HERE / "measurements/directed-verifier.json.gz": "dc132cbaac6cb3eddb21ec4c7df950b03eb1713461dac2d50ff0a92ac3e9a13b",
}
VISITS = {61: 32520379791826, 53: 32520376250566}
RADIO, CHANNEL, RATE, PERIOD = 0, 6, 10_000_000, 13_333
RF, FREQ_STEP, FREQ_RADIUS, MARGIN_GATE = 11_959_687_500., 250, 2_000, .025
EPOCH_STEPS, FREQ_STEPS = tuple(range(-16, 17)), tuple(range(-8, 9))
ALIAS_HZ = RATE / 44
THREADS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


class Timing(ct.Structure):
    _fields_ = [("epoch", ct.c_double), ("hz", ct.c_double), ("score", ct.c_double), ("confirmation", ct.c_int)]


class Trace(ct.Structure):
    _fields_ = [("timing", Timing), ("sample", ct.c_int)]


class Factor(ct.Structure):
    _fields_ = [("rank", ct.c_int), ("integer", ct.c_int), *[(k, ct.c_double) for k in ("offset", "hz", "exact", "control")]]


class VerifierResult(ct.Structure):
    _fields_ = [*((k, ct.c_uint) for k in ("seed_index", "fine_winner", "conditioned_winner", "conditioned_bins", "flags", "stage_frames")),
                *((k, ct.c_double) for k in ("fine_residual_hz", "acquired_hz", "acquired_residual_hz", "acquire", "verify", "verify_control",
                    "conditioned", "integer_exact", "integer_control", "integer_residual_hz", "offset_samples", "curvature",
                    "fractional_exact", "fractional_control", "fractional_residual_hz")),
                *((k, ct.c_double * n) for k, n in (("exact_grid", 5), ("control_grid", 5),
                                                   ("conditioned_grid", 42), ("conditioned_scores", 42)))]


def checked(path, expected=None):
    data = path.read_bytes()
    expected = PINS[path] if expected is None else expected.removeprefix("sha256:")
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Pinned source changed: {path}")
    return data


def archived(name):
    return json.loads(gzip.decompress(checked(HERE / "measurements" / name)))


def scopes(pair):
    documents = pair["documents"]
    booked = json.loads(checked(ROOT / "resumed-stage.json"))
    if documents["resumed-stage.json"]["document"] != booked or not booked["verified_complete"]:
        raise ValueError("The complete authenticated first member differs")
    rows = {}
    for mode in ("named", "integrated"):
        source = documents[f"{mode}/detections.json"]["document"]["source"]
        for visit, counter in VISITS.items():
            (row,) = [row for row in source["probes"] if row["visit_index"] == visit and row["receiver_id"] == RADIO]
            if (row["channel"], row["actual_rf_hz"], row["edge"], row["valid_start_counter"], len(row["candidates"])) != (CHANNEL, RF, "lower", counter, 1):
                raise ValueError("A sealed comparison lane changed")
            rows.setdefault(visit, {})[mode] = row["candidates"][0]
    return booked, rows


def allow_local_waveform(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0])).absolute()
        if (path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01")
                or path.name.endswith(".ci16.zst") and path != STAGE / "iq-000000.ci16.zst"):
            raise PermissionError(f"Only the enrolled resident original waveform is available: {path}")


def read_member(book):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage.short_window import ShortWindowReader

    manifest = STAGE / "manifest.json"
    member = book["member"]
    paths = [manifest, STAGE / member["index_relative_path"], STAGE / member["payload_relative_path"]]
    if any(path.resolve(strict=True) != path or path.stat().st_mode & 0o222 for path in paths):
        raise ValueError("Expected direct read-only staged original files")
    if subprocess.check_output(["findmnt", "-n", "-o", "FSTYPE", "-T", STAGE], text=True).strip() != "tmpfs":
        raise ValueError("Expected a private resident original stage")
    checked(manifest, book["manifest_sha256"])
    reader = ShortWindowReader(STAGE)
    if reader.manifest.chunks[0].model_dump(mode="json") != member or not reader.manifest.chunks[0].window_count == 64:
        raise ValueError("The stock reader must exhaust exactly the original first member")
    targets = {target["target_id"]: target for target in reader.manifest.configuration["targets"]}
    retained = {}
    for seq, window in enumerate(reader.windows(stop_sequence=64)):
        row, samples = window.index, window.samples
        if row.sequence != seq:
            raise ValueError("Original member order changed")
        if seq not in VISITS:
            continue
        capture, target = row.acquisition, targets[row.target_id]
        valid = valid_window_support(capture, RATE, samples.shape, reader.manifest.receiver_ids, FastScanPolicyV2())
        if (not valid or samples.shape != (200_000, 2, 2) or samples.flags.writeable
                or tuple(reader.manifest.receiver_ids) != (0, 1) or reader.manifest.sample_rate_hz != RATE
                or (capture["sample_start"], target["channel"], target["edge"], capture["actual_if_center_hz"] + target["lnb_lo_hz"])
                != (VISITS[seq], CHANNEL, "lower", RF)):
            raise ValueError("Native diagnostic lane differs from its committed stereo support")
        center = target["rf_center_hz"] - target["lnb_lo_hz"] - capture["actual_if_center_hz"]
        retained[seq] = row.iq_sha256, samples, center
    if set(retained) != set(VISITS):
        raise ValueError("Expected exactly the two frozen diagnostic windows")
    return retained


def function(lib, name, result, *arguments):
    call = getattr(lib, name)
    call.argtypes, call.restype = arguments, result
    return call


@contextmanager
def context(lib, prefix, *inputs):
    ptr = ct.c_void_p
    create_types = (ct.c_int, ptr, ptr) if prefix == "timing_first" else (ptr,) * len(inputs)
    create = function(lib, prefix + "_create", ptr, *create_types)
    free = function(lib, prefix + "_free", None, ptr)
    state = create(*inputs)
    if not state:
        raise ValueError("Native diagnostic context creation failed")
    try:
        yield state
    finally:
        free(state)


def fields(value):
    return {key: getattr(value, key) for key, _ in value._fields_}


def factors(lib, symbol, ctx, samples, center):
    call = function(lib, symbol, ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_int,
                    ct.c_double, ct.c_double, ct.POINTER(Factor))
    rows = (Factor * 2)()
    count = call(ctx, samples.ctypes.data, RADIO, center-800_000., center+800_000., rows)
    if not 0 <= count <= (1 if symbol == "cancellation_primary_factors" else 2):
        raise ValueError("Unexpected native factor count")
    return [fields(row) for row in rows[:count]]


def typed(row):
    margin = row["exact"] - row["control"]
    return dict(candidate_rank=row["rank"], integer_epoch_sample=row["integer"], fractional_epoch_offset_samples=row["offset"],
                fractional_tracking_cfo_hz=row["hz"], fractional_exact_score=row["exact"], fractional_control_score=row["control"],
                fractional_margin=margin, passed_fractional_margin_gate=margin >= MARGIN_GATE)


def grid(center):
    for t in EPOCH_STEPS:
        shift = t / 4
        whole = math.floor(shift + .5)
        offset = center["fractional_epoch_offset_samples"] + shift - whole
        for f in FREQ_STEPS:
            yield t, f, (center["integer_epoch_sample"] + whole) % PERIOD, offset, center["fractional_tracking_cfo_hz"] + f*FREQ_STEP


def support_frames(epoch, offset):
    integer = abs(offset - round(offset)) <= 1e-12
    for frame in range(15):
        start = epoch + (40_000*frame + 1)//3
        if start+88+offset < (0 if integer else 7) or start+2903+offset >= 200_000-(0 if integer else 8):
            return frame
    return 15


def scores(lib, state):
    call = function(lib, "directed_verify_fixed", ct.c_int, ct.c_void_p, ct.c_uint, ct.c_double, ct.c_double,
                    ct.c_int, ct.POINTER(VerifierResult))

    def evaluate(epoch, hz, offset):
        out = VerifierResult()
        if call(state, epoch, hz, offset, 0, ct.byref(out)):
            raise ValueError("The original exact local verifier declined a valid point")
        return out.fractional_exact, out.fractional_control, out.fractional_residual_hz, out.flags

    return evaluate


def surface(evaluate, hypothesis, center):
    residual_center = hypothesis["fractional_tracking_cfo_hz"]
    points = []
    for t, f, epoch, offset, hz in grid(hypothesis):
        if abs(hz-center) > 800_000:
            raise ValueError("The frozen grid extends outside the original signed-band support")
        exact, rolled, residual, flags = evaluate(epoch, hz, offset)
        emitted = hz + residual
        inside = abs(emitted-residual_center) <= FREQ_RADIUS and abs(emitted-center) <= 800_000
        points.append(dict(t=t, f=f, phase=epoch+offset, reference_hz=hz, exact=exact, rolled=rolled,
                           residual_hz=residual, emitted_hz=emitted, flags=flags, inside=inside,
                           frames=support_frames(epoch, offset), margin=exact-rolled))
    inside = [p for p in points if p["inside"]]
    return dict(hypothesis=hypothesis, center=next(p for p in points if not p["t"] and not p["f"]),
                best_exact=max(inside, key=lambda p: p["exact"], default=None),
                best_margin=max(inside, key=lambda p: p["margin"], default=None),
                unrestricted_best_exact=max(points, key=lambda p: p["exact"]),
                inside_count=len(inside), cells=points)


def diagnostic(window, caster, assets, sealed):
    digest, samples, center = window
    full, short, directed = caster
    pilot, original, rolled, fir_ptr = assets
    record = dict(window_sha256=digest, center_hz=center, sealed=sealed)
    with context(full, "two_carrier", pilot) as ctx:
        raw_full = factors(full, "cancellation_factors", ctx, samples, center)
    with context(short, "two_carrier", pilot) as ctx:
        raw_short = factors(short, "cancellation_primary_factors", ctx, samples, center)
    if sealed["named"] not in list(map(typed, raw_full)) or list(map(typed, raw_short)) != [sealed["integrated"]]:
        raise ValueError("The signed local lane did not reproduce the sealed selections")
    with context(directed, "two_carrier", pilot) as ctx:
        traced = factors(directed, "cancellation_factors", ctx, samples, center)
        read_trace = function(directed, "directed_timing_trace", ct.c_int, ct.POINTER(Trace))
        trace = (Trace * 2)()
        count = read_trace(trace)
        if raw_full != traced or count not in (1, 2):
            raise ValueError("Relinked full trace does not reproduce the original native alternatives")
        scouts = [fields(item.timing) | {"sample": item.sample} for item in trace[:count]]
    with context(short, "timing_first", 4, pilot, fir_ptr) as ctx:
        call = function(short, "timing_first_detect", ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_int,
                        ct.c_double, ct.c_double, ct.POINTER(Timing))
        scout = Timing()
        if call(ctx, samples.ctypes.data, RADIO, center-800_000., center+800_000., ct.byref(scout)):
            raise ValueError("The registered short scout failed its original input")
    with context(directed, "portable_verifier", original, rolled) as ctx:
        load = function(directed, "portable_verifier_load", ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_uint)
        if load(ctx, samples.ctypes.data, RADIO):
            raise ValueError("Original input failed the diagnostic verifier load")
        score = scores(directed, ctx)
        fixed_checks = []
        for factor in raw_full:
            hz = scouts[factor["rank"]]["hz"]
            exact, control, residual, flags = score(factor["integer"], hz, factor["offset"])
            if (exact, control, hz+residual) != (factor["exact"], factor["control"], factor["hz"]):
                raise ValueError("The original fixed verifier did not reproduce the expected full factor at its scout CFO")
            fixed_checks.append(dict(rank=factor["rank"], exact=exact, rolled=control, reference_hz=hz,
                                     residual_hz=residual, flags=flags))
        neighborhoods = {mode: surface(score, hypothesis, center) for mode, hypothesis in sealed.items()}
    return record | dict(native_full=raw_full, native_short=raw_short, full_scouts=scouts, short_scout=fields(scout),
                         fixed_verifier_checks=fixed_checks, neighborhoods=neighborhoods)


def run(output):
    import numpy as np

    cpu, wall = process_time(), perf_counter()
    io = subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip()
    if os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) != 15 or "prio 7" not in io or any(os.getenv(k) != "1" for k in THREADS):
        raise ValueError("The physical diagnostic requires the standard benchmark lease and service settings")
    sys.addaudithook(allow_local_waveform)
    pair = archived("first-member-0163-resume-acquisition.json.gz")
    build = archived("directed-verifier.json.gz")["build"]
    if build["installed_sha256"] != PINS[FULL] or build["build"]["library_sha256"] != PINS[DIRECTED]:
        raise ValueError("Exact fixed verifier differs from the archived parity comparison")
    book, sealed = scopes(pair)
    windows = read_member(book)
    pinned = []
    for path in (FULL, SPARSE, DIRECTED):
        checked(path)
        pinned.append(ct.CDLL(str(path)))
    asset = np.frombuffer(checked(PILOT), dtype="<f4")
    if asset.shape != (133_413,):
        raise ValueError("Original pilot asset geometry changed")
    templates = asset[:4*PERIOD].astype("<f8").reshape(2, -1)
    assets = asset.ctypes.data, templates[0].ctypes.data, templates[1].ctypes.data, asset[4*PERIOD:].ctypes.data
    results = {visit: diagnostic(windows[visit], pinned, assets, sealed[visit]) for visit in VISITS}
    receipt = dict(case="DS30-0163", radio=RADIO, channel=CHANNEL, rf_hz=RF, counters=VISITS, sample_rate_hz=RATE,
                   issued=64, prior="uniform local cells", grid_timing_step_samples=.25, grid_timing_radius_samples=4,
                   grid_carrier_step_hz=FREQ_STEP, grid_carrier_radius_hz=FREQ_RADIUS, residual_bins=512,
                   residual_alias_hz=ALIAS_HZ, residual_bin_spacing_hz=ALIAS_HZ/512, waveform_backing_bytes=0,
                   source_pins={str(path): pin for path, pin in PINS.items()}, member=book["member"],
                   clock=dict(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-wall), results=results)
    with output.open("xb") as stream:
        stream.write(gzip.compress((json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False)+"\n").encode(), mtime=0))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
