"""Build and measure a fixed centered 12 ms receiver on signed saved visits."""

import argparse
from collections import Counter
from contextlib import ExitStack, closing
import ctypes
import errno
from hashlib import sha256
from importlib import import_module
import json
from math import remainder
import mmap
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive

from .low_bit_pilot_screen import adc, carrier_wave
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, MixedApertureDetector, NativePath, verified
from .mixed_aperture_trial import center, encoded, exports, ordered, window
from .scout_readout_trial import check_machine, factor_bytes
from .sparse_cold_input import BINDING, BINDING_SHA, MANIFEST_SHA, PAYLOAD, RELEASE, RUNTIME, SOURCE_DIR, copy_bounded


HERE = Path(__file__).resolve().parent
ORIGINAL = Path("/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2")
BUILD_PIN = "99f912ef6c1cd57f13b081408a8cececc9bb3ea2384c517bef70f7eb34bfcfac"
PREFIX_PIN = "06570a53032c770d99cc9678b8660e1bb502b71f30fc47c8b1a4a8e31bc19ba9"
RELEASE_BUILD = Path("/tmp/leo-algo08v2-2x-bench/receiver-fractional-exact-v1/build.json")
RELEASE_PIN = "5566ddd22345982e1b7673c7d65a8ce5799ce8229275365e1e6e237ab3f0e86d"
WEAK_PIN = "0f025d0f5c80f5425a3c6fa90bc77a0e5628eb8cf7bc7ac7dab7fdd6c1d2e9d9"
SHIFT, APERTURE, PERIOD = 40000, 120000, 13333
ARMS = ("prefix", "centered")
INPUT_MODULES = ("leo.storage.fast_scan", "leo.storage.short_window", "leo.scanner.fast_scan_analysis",
                 "tools.pipeline_eval.qualification.blind_compact_run")


def digest(contents):
    return sha256(contents).hexdigest()


def source_with_center(prefix, extension):
    token = b"int cancellation_primary_factors("
    if prefix.count(token) != 1:
        raise ValueError("Cannot locate the pinned signed primary entry")
    return prefix.replace(token, b"static int primary_on_aperture(") + b"\n" + extension


def build(output):
    output = output.resolve()
    archived = json.loads(verified(ORIGINAL / "build-receipt.json", BUILD_PIN))
    release = json.loads(verified(RELEASE_BUILD, RELEASE_PIN))
    prefix = ORIGINAL / "short-primary.so"
    verified(prefix, PREFIX_PIN)
    compiler = subprocess.check_output(["cc", "--version"], text=True).splitlines()[0]
    if compiler != release["compiler"]:
        raise ValueError("The native compiler differs from release provenance")
    old_object = archived["compile"][-1]
    for item in archived["relink"]:
        if not item.endswith(".o") or item == old_object:
            continue
        verified(item, archived["short_object_sha256"][Path(item).name])
    source = verified(archived["compile"][-3], archived["source_wrapper_sha256"])
    extension = HERE.joinpath("centered_primary.c").read_bytes()
    output.mkdir()
    commands = []
    for arm, contents in (("prefix", source), ("centered", source_with_center(source, extension))):
        arm_output = output / arm
        arm_output.mkdir()
        c_path, obj = (arm_output / f"two_carrier_receiver.{suffix}" for suffix in ("c", "o"))
        binary = arm_output / "short-primary.so"
        c_path.write_bytes(contents)
        compile_ = [*archived["compile"][:-4], "-c", str(c_path), "-o", str(obj)]
        link = [str(obj) if item == old_object else item for item in archived["relink"][:-1]]
        for command in (compile_, [*link, str(binary)]):
            commands.append(command)
            subprocess.run(command, cwd=release["cwd"], check=True)
    verified(output / "prefix" / "short-primary.so", PREFIX_PIN)
    if exports(binary) != exports(prefix):
        raise ValueError("The centered primary changes the receiver's exported ABI")
    return {"prefix": (prefix, PREFIX_PIN), "centered": (binary, digest(binary.read_bytes()))}, dict(
        cwd=release["cwd"], compiler=compiler, commands=commands, archive_build_sha256=BUILD_PIN,
        release_build_sha256=RELEASE_PIN, source_sha256=digest(c_path.read_bytes()),
        extension_sha256=digest(extension), objects=archived["short_object_sha256"])


def verify_input():
    for name in INPUT_MODULES:
        verified(import_module(name).__file__, RUNTIME[name])
    return {name: RUNTIME[name] for name in INPUT_MODULES}


def cache_copy(origin, target, *, limit, expected_hash, size=None, metadata=False):
    command = ["sudo", "-n", "-u", "leo"]
    if metadata:
        command.extend(["cat", "--", str(origin)])
    else:
        command.extend(["/usr/bin/python3", str(HERE / "centered_primary_cached.py"), str(origin), str(limit)])
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as child:
        with closing(child.stdout), target.open("xb") as out:
            try:
                copy_bounded(child.stdout, out, limit=limit, expected_hash=expected_hash, exact_size=size)
            except ValueError:
                child.stdout.close()
                if child.wait() != 0:
                    message = child.stderr.read().decode().strip()
                    if "Cache-only input unavailable" in message:
                        raise BlockingIOError(errno.EAGAIN, message) from None
                    raise RuntimeError(message) from None
                raise
        if child.wait() != 0:
            raise RuntimeError(child.stderr.read().decode().strip())


def dense_rows():
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage.fast_scan import FastSegmentSource

    case = json.loads(verified(BINDING, BINDING_SHA))["case"]
    entry = case["recording"]["segments"][0]
    origin = (Path("/srv/bulk") / entry["path"]).parent
    if SOURCE_DIR not in origin.parents or entry["sha256"] != MANIFEST_SHA:
        raise ValueError("Unexpected dense source")
    try:
        with TemporaryDirectory(prefix="centered-primary-", dir="/dev/shm") as tmp:
            target = Path(tmp) / origin.name
            target.mkdir(mode=0o700)
            label = "sha256:"+MANIFEST_SHA
            cache_copy(origin / "manifest.json", target / "manifest.json", limit=1 << 20,
                       expected_hash=label, metadata=True)
            source = FastSegmentSource(dict(path=str(target), manifest_digest=label), stop_sequence=48)
            member = source.reader.manifest.chunks[0]
            if member.first_sequence != 0 or member.window_count != 64 or tuple(source.receiver_ids) != (0, 1):
                raise ValueError("Unexpected dense member and receiver geometry")
            for name, size, expected in ((member.index_relative_path, member.index_bytes, member.index_sha256),
                                         (member.payload_relative_path, member.compressed_bytes, member.compressed_sha256)):
                if Path(name).name != name or size > 80 << 20:
                    raise ValueError("Dense source exceeds its one-member budget")
                cache_copy(origin / name, target / name, limit=size, expected_hash=expected, size=size)
            policy = FastScanPolicyV2()
            rows = []
            for item in source.windows():  # Exhaustion validates the entire first decoded member.
                a, t = item.acquisition, item.target
                if valid_window_support(a, item.sample_rate_hz, item.samples.shape, (0, 1), policy):
                    rows.append((dict(case=case["id"], key=f'{case["id"]}:{a["global_visit"]}', edge=t["edge"],
                                      acquisition=a, target=t, sha256=item.iq_sha256), item.samples))
            return rows, dict(binding_sha256=BINDING_SHA, manifest_sha256=MANIFEST_SHA,
                              member=member.model_dump(mode="json"), staged="strict RWF_NOWAIT", stop_sequence=48)
    except BlockingIOError as error:
        return [], dict(binding_sha256=BINDING_SHA, manifest_sha256=MANIFEST_SHA, unavailable=str(error))


def plants():
    ranges = {"whole": (0, 200000), "early": (0, 120000), "late": (80000, 200000),
              "noise": (0, 0), "rolled": (0, 200000)}
    rng = np.random.default_rng(898789)
    for edge, pin in PILOT_SHA.items():
        asset = np.frombuffer(verified(RELEASE / "assets" / f"{edge}.f32", pin), dtype="<f4")
        for i, (label, (start, stop)) in enumerate(ranges.items()):
            iq = np.empty((200000, 2, 2), dtype="<i2")
            tones = [(10993, -639701), (27113, 554913)]
            for lane, (epoch_ticks, hz) in enumerate(tones):
                wave = carrier_wave(asset, epoch_ticks, hz, rolled=label == "rolled")
                wave[:start] = 0
                wave[stop:] = 0
                noise = (rng.normal(size=len(wave)) + 1j * rng.normal(size=len(wave))) / np.sqrt(2)
                signal = adc(1900 * (wave + 0.39 * noise))
                iq[:, lane, 0], iq[:, lane, 1] = signal.real, signal.imag
            tune = 0 if edge == "lower" else 75000
            yield dict(edge=edge, case="independent plants", key=f"{edge}:{label}", visit=i,
                       target=dict(rf_center_hz=tune, lnb_lo_hz=0, channel=1), tones=tones,
                       acquisition=dict(actual_if_center_hz=0, sample_start=200000*i), sha256=digest(iq.tobytes())), iq


def clock():
    return process_time_ns(), perf_counter_ns()


def elapsed(start):
    return [now - then for now, then in zip(clock(), start, strict=True)]


def match(reference, proposal):
    samples = abs(remainder((reference[1]+reference[2])-(proposal[1]+proposal[2]), PERIOD))
    hz = abs(reference[3]-proposal[3])
    return dict(samples=samples, hz=hz, hit=samples <= 2 and hz <= 250)


def score(rows):
    result = {}
    for arm in ARMS:
        counts = Counter()
        for row in rows:
            full, proposals, lane = row["installed"], row[arm], row["lane"]
            counts.update(lanes=1, stock_factors=len(full), proposed=len(proposals),
                          stock_selected=bool(full), stock_rank_zero=any(f[0] == 0 for f in full))
            counts[f"stock_selected_lane_{lane}"] += bool(full)
            hit = bool(full and proposals and match(ordered(full)[0], proposals[0])["hit"])
            counts.update(selected_matches=hit,
                          rank_zero_matches=bool(proposals and any(f[0] == 0 and match(f, proposals[0])["hit"]
                                                                 for f in full)))
            counts[f"selected_matches_lane_{lane}"] += hit
            counts["new_proposals"] += bool(proposals and not any(match(f, proposals[0])["hit"] for f in full))
        result[arm] = dict(counts)
    return result


def compare(rows, paths, *, schedule):
    installed = PAYLOAD / "receiver.so"
    edges = sorted({r["edge"] for r, _ in rows})
    windows = [window(row, samples) for row, samples in rows]
    packets, clocks = None, []
    for order in (ARMS, ARMS[::-1]):
        detectors, callbacks, setups = {}, {}, {}
        emitted, times = {arm: [] for arm in ARMS}, {arm: [0, 0] for arm in ARMS}
        modes = []
        with ExitStack() as scopes:
            for arm in order:
                start = clock()
                detector = MixedApertureDetector(*paths[arm], full_coverage=True)
                detectors[arm] = detector
                if not schedule:
                    detector.schedule.rule = ("short_primary",)
                callbacks[arm] = {edge: scopes.enter_context(detector.detector(
                    "cancellation", edge, binary=installed, pilot=RELEASE / "assets" / f"{edge}.f32"))
                                  for edge in edges}
                setups[arm] = elapsed(start)
            past = None
            for i, ((row, _), ci) in enumerate(zip(rows, windows, strict=True)):
                if past != row["case"]:
                    for detector in detectors.values():
                        detector.schedule.streams.clear()
                    past = row["case"]
                for arm in (order if i % 2 == 0 else order[::-1]):
                    detector = detectors[arm]
                    before = detector.visits["full"]
                    start = clock()
                    probes = callbacks[arm][row["edge"]](ci)
                    spent = elapsed(start)
                    emitted[arm].append(probes)
                    for k, value in enumerate(spent):
                        times[arm][k] += value
                    mode = "full" if detector.visits["full"] > before else "short_primary"
                    if arm == "centered":
                        modes.append(mode)
            clocks.append({arm: dict(setup_cpu_wall_ns=setups[arm], callback_cpu_wall_ns=times[arm],
                                     native=detectors[arm].receipt()) for arm in ARMS})
        if packets is not None and packets != emitted:
            raise ValueError("Repeated mixed-aperture outputs changed")
        packets = emitted
    details, audited = [], 0
    verified(installed, INSTALLED_SHA)
    with ExitStack() as scopes:
        stock, prefix, shifted = {}, {}, {}
        for edge in edges:
            asset = np.frombuffer(verified(RELEASE / "assets" / f"{edge}.f32", PILOT_SHA[edge]), dtype="<f4")
            for store, path, mode in ((stock, installed, "full"), (prefix, paths["prefix"][0], "short_primary"),
                                      (shifted, paths["centered"][0], "short_primary")):
                engine = store[edge] = NativePath(path, asset, mode)
                scopes.callback(engine.close)
        for i, (((row, raw), ci), mode) in enumerate(zip(zip(rows, windows, strict=True), modes, strict=True)):
            edge = row["edge"]
            changed = raw.copy()
            changed[:SHIFT], changed[SHIFT+APERTURE:] = -32768, 32767
            for lane in (0, 1):
                a, b = (packets[arm][i][lane] for arm in ARMS)
                if {k: v for k, v in a.items() if k != "candidates"} != {k: v for k, v in b.items() if k != "candidates"}:
                    raise ValueError("Original probe support differs")
                baseline, _ = stock[edge].run(raw, lane, center(ci))
                control, experiment = encoded(a), encoded(b)
                if mode == "full":
                    if factor_bytes(control) != factor_bytes(ordered(baseline)) or a != b:
                        raise ValueError("Unchanged original full anchors differ")
                else:
                    crop, _ = prefix[edge].run(raw[SHIFT:SHIFT+APERTURE], lane, center(ci))
                    wings, _ = shifted[edge].run(changed, lane, center(ci))
                    if len({factor_bytes(x) for x in (experiment, crop, wings)}) != 1:
                        raise ValueError("Centered outputs read an excluded wing or differ from the explicit slice")
                    audited += 1
                desired = row.get("tones", [None, None])[lane]
                details.append(dict(key=row["key"], iq_sha256=row["sha256"], lane=lane, mode=mode,
                                    installed=baseline, prefix=control, centered=experiment, plant=desired,
                                    metadata={k: v for k, v in a.items() if k != "candidates"}))
    return dict(clocks=clocks, complete=score(details), primaries=score([r for r in details if r["mode"] != "full"]),
                checked_wings_and_slices=audited, details=details)


def guarded_aperture(binary):
    """Exercise both native edges using different alignments and a real verified plant."""
    row, raw = next(plants())
    asset = np.frombuffer(verified(RELEASE / "assets" / "lower.f32", PILOT_SHA["lower"]), dtype="<f4")
    native = NativePath(binary, asset, "short_primary")
    protect = ctypes.CDLL(None, use_errno=True).mprotect
    protect.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int)
    protect.restype = ctypes.c_int
    page = mmap.PAGESIZE
    stride = raw.strides[0]
    tested = []
    try:
        expected = [factor_bytes(native.run(raw, lane, 0)[0]) for lane in (0, 1)]
        if not all(expected):
            raise ValueError(f"Guarded real verifier requires two positive native plants ({row['key']})")
        for edge, boundary in (("before", SHIFT), ("after", SHIFT + APERTURE)):
            pad = (-boundary * stride) % page
            with mmap.mmap(-1, raw.nbytes + page) as region:
                view = np.ndarray(raw.shape, dtype=raw.dtype, offset=pad, buffer=region)
                view[:] = raw
                ptr = view.ctypes.data + boundary * stride - (page if edge == "before" else 0)
                if protect(ptr, page, 0):
                    raise OSError(ctypes.get_errno(), "Cannot guard the excluded native input boundary")
                try:
                    for lane in (0, 1):
                        if factor_bytes(native.run(view, lane, 0)[0]) != expected[lane]:
                            raise ValueError("Guarded native factor changed")
                        tested.append(dict(edge=edge, lane=lane, protected_page_bytes=page))
                finally:
                    if protect(ptr, page, mmap.PROT_READ | mmap.PROT_WRITE):
                        raise OSError(ctypes.get_errno(), "Cannot restore the test's excluded input page")
                    del view
    finally:
        native.close()
    return tested


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("weak", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("use a fresh output directory")
    machine = check_machine()
    args.output.mkdir()
    paths, build_receipt = build(args.output / "build")
    verified(args.weak, WEAK_PIN)
    weak = compare(list(read_archive(args.weak, 18)), paths, schedule=False)
    dense, dense_authority = dense_rows()
    receipt = dict(machine=machine, build=build_receipt, receiver_sha256={a: paths[a][1] for a in ARMS},
                   installed_sha256=INSTALLED_SHA, pilot_sha256=PILOT_SHA, weak_archive_sha256=WEAK_PIN,
                   dense_authority=dense_authority, weak=weak, planted=compare(list(plants()), paths, schedule=False),
                   dense=compare(dense, paths, schedule=True) if dense else None,
                   runtime_files=verify_input(), guarded=guarded_aperture(paths["centered"][0]))
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False)+"\n")


if __name__ == "__main__":
    main()
