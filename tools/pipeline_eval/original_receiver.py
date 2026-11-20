"""Run the accelerated original receiver on authenticated saved I/Q."""

import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from functools import partial
from hashlib import sha256
from pathlib import Path
from time import monotonic
from unittest.mock import patch
from uuid import uuid4

from . import iq_service, whole_iq
from .__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from .qualification import capture_release, capture_whole
from .qualification import prepared_capture_waveform as prepared
from .qualification.capture_whole import recording
from .qualification.full_v5_check import BULK, _load_case, _sha
from .scoring import validate_result
from .variants import (
    compact_tile_interior,
    final_region,
    fine_batch,
    fine_search,
    first_gate,
    prepared_hotpath_peaks,
    v5_secant_fit,
)
from .variants.iq_stream import _read_prefix

MODULE = "tools.pipeline_eval.original_receiver"
ARCHIVE = BULK / "leo/fast-scan-recordings"
CALIBRATION = BULK / "leo-dev/whole-band-BCw8KqMY/receiver-phase-release"
CALIBRATION_SHA = "f4f5baef17a0f579469ef9aad6038ac0115b6f753d92eca96080541cc8f279a9"
NATIVE_BOUND_SHA = "40888d6143f385c2146e5e2cb28ea99a96b2f1bb791fab4c22b5afaaa2b3a23b"
ORBIT_PROJECTOR_SHA = "47d8605da701d4426d2a3a6f8a3e9dd272b1499a9f5e0b19e406087ff211a28f"
NUMERIC_SOURCES = {
    "leo/analysis/localization_v4/native_bound.c": NATIVE_BOUND_SHA,
    "tools/pipeline_eval/variants/orbit_projector.c": ORBIT_PROJECTOR_SHA,
}
PYTHON_SHA = "8f9781a98200d9ecda7e00464e4c64b1327abae788ae8e6979d5c859311410c7"
KERNEL_DIR = BULK / "leo-dev/receiver-screening-20261119/capture-exact-v2"
PREPARED = (
    ROOT
    / "reports/2026_11_19_receiver_screening/original-support/original-kernel/original_kernel.so"
)
SHORT_FFT = (
    ROOT
    / "reports/2026_11_19_receiver_screening/coarse-and-navigation/fft-length"
    / "build/planned-256/prepared_measured.so",
    "40965b750fb0e833fd211f4c069bb3eb0f190a40a0cf65963a2e5ebbe6456286",
)
SHORT_FFT_QUALIFICATION = "10eea2f5602dc6ebd948c378808cadc3b3b64a1b446da7ad725a6d287c19a6e4"
KERNELS = {
    "prepared": (PREPARED, "26d1e10bb0cf0f15d58d922c46a2b50e38124d54a7efdccfcb8e2ba46783de02"),
    "batched32": (
        KERNEL_DIR / "capture_batched_fft.so",
        "5c7f96f8219d29a776660c4b0de5deafadaf4983774432e5868e1817423144ec",
    ),
    "cfo": (
        KERNEL_DIR / "conditioned.so",
        "378219a59d7b9b13f7548d9d056917853aad369c720ded4b1d07c32d661bfa1e",
    ),
    "fused": (
        KERNEL_DIR / "fused.so",
        "dc34f7196391931e27105425217bfcac3a47833571cb36fe8260686a9ce1ffb0",
    ),
}
PEAK_SELECTORS = ("installed", "row-wise")
ROW_SELECTOR_SHA = "a4198d5e47fdf337b1ee8605c715d9da24672cffddf3774b1a8265d5ad929527"
ROW_SELECTOR_QUALIFICATION = "c8bfb6ef30c385a85f7129ed18bc9565cfa02021be0c1174dcb1d2ee0fb5c52e"
ROW_SELECTOR_PRODUCERS = {
    capture_release.RELEASE_ROOTS[
        "fast-1f3a91c6a882b6e7eac8827fbb95f215"
    ]: "ef87f40f289e47724ba9fb135b37775d45a2e3fb0b5573e8e9d2b441d20339d6",
    capture_release.RELEASE_ROOTS[
        "fast-33b3892e0162eac7fd2232898aa9d1ce"
    ]: "ef87f40f289e47724ba9fb135b37775d45a2e3fb0b5573e8e9d2b441d20339d6",
    capture_release.RELEASE_ROOTS[
        "fast-a9ce664313cc56759cdffefe4750f833"
    ]: "6a1e88345d2d64f6d6e11f1d586753b74bcc0ef5a6f6816e42880eb8bc6e7a23",
}
FINE_SEARCHES = ("installed", "pruned", "batched")
FINE_QUALIFICATION = "905317d53cb7b41a341bc6c121bc99bddf9caf4da1e666f1e3580111184c4895"
FINE_LIBRARY_SHA = "4d0b38f6c10aedba4f585e006fda5683ac78eafbc45be96a3609acf786b0458a"
FINE_LIBRARY_CACHE = BULK / "leo-dev/fine-search-20261119/qualified/fine_search.so"
FINE_NUMPY_VERSION = "2.5.2"
FINE_POCKETFFT_SHA = "29a1547b480b7ddc1e45cdc772b3f4b614cccced70204181bf5d3ad138a04ebb"
FINE_SOURCES = {
    Path(fine_search.__file__): "c484609d9a40ae8052f645c18917f98ce94bacbba056078c7ba40ab1c4d06ccc",
    fine_search.SOURCE: "4ecef2edc76d36f9c2c7eec221b8a2a35ee43ce442264634426a6da531157565",
    fine_search.SOURCE.with_name(
        "prepared_hotpath.py"
    ): "af424b931bc0ccd9dd867f7665916387de2f1983875401776ef522db99dd9afe",
    fine_search.SOURCE.with_name(
        "refine_bank.py"
    ): "34986485227b71a8e23ad8898904c8a25ff48961995cf2bd71949780c4770cf6",
}
BATCH_QUALIFICATION = "b529eda1890f00ee6ecb7362de1fe2cd613888c8d8057224abb3c747d9aca1e9"
BATCH_LIBRARY_SHA = "98a23962c45e8077b4f9a98904d836d77d99041d08e06aeb9bb0f635778c6f65"
BATCH_LIBRARY_CACHE = BULK / "leo-dev/fine-batch-20261119/frozen/fine_batch.so"
BATCH_SOURCES = {
    Path(fine_batch.__file__): "08ed341c3dbe928b6ecb420ae4b2b050c037120efb52bd7d90a4564560cb4cad",
    fine_batch.SOURCE: "226d35c4d2f7c0babf0a08b80b03b1e79d74077c02a92d341c12aaf6732f316c",
}
FINE_TRACE = "pruned-fine-search-v1: "
FRACTIONAL_STOPS = {"full": None, "first": 1, "second": 2}
GATE_SOURCE_SHA = "d213c400249bb2361cbec1bf4f599cbb010956dd6d042da7bd569c8e8151ed68"
GATE_QUALIFICATION = "235eee88a9cb7e803e3b02b517c1210bda594cfd86acec1e98f1c4b964898651"
GATE_TRACE = "ranked-fractional-stop-v1: "


def input_case(ident, path, digest):
    if ident is not None:
        if digest is not None:
            raise ValueError("--input-sha256 accompanies --input")
        try:
            return _load_case(ident)
        except StopIteration:
            raise ValueError(f"unknown recording case {ident}") from None
    if digest is None or not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", digest):
        raise ValueError("--input requires the authenticated --input-sha256 digest")
    locator = whole_iq.checked(path.resolve(strict=True), digest)
    case = whole_iq.read(locator)
    if "request" in case:
        request = case["request"]
        case["request"] = dict(request, path=str((locator.parent / request["path"]).resolve()))
    return case


def binding(case):
    request = whole_iq.read(
        whole_iq.checked(BULK / case["request"]["path"], case["request"]["sha256"])
    )
    job = request["job"]
    if (
        request["role"] != "baseline"
        or job["identity"]["session_id"] != case["session_id"]
        or job.get("evaluation_reference") is not None
        or job["search_center"] != case["regions"][0]["center"]
    ):
        raise ValueError(
            "expected the truth-free original no-repair request for the offered region"
        )
    if "native" in case and (job.get("native_input") or {}).get("sha256") != (
        "sha256:" + case["native"]["sha256"].removeprefix("sha256:")
    ):
        raise ValueError("benchmark request does not bind its declared original detector input")
    snapshots = {p.name: _sha(p) for p in Path(job["tle_root"]).rglob("*.tle")}
    expected = {
        name: digest.removeprefix("sha256:") for name, digest in request["causal_snapshots"].items()
    }
    if not snapshots or snapshots != expected:
        raise ValueError("causal orbit snapshots differ from the authenticated request")
    config = job["track_config"]
    whole_iq.checked(Path(config["path"]), config["sha256"])
    return request


def bind_fresh(case, native, path):
    original = binding(case)
    job = dict(native_input=None, output_root=None, evaluation_reference=None) | original["job"]
    identity = dict(input_sha256=None, run_id=None) | job["identity"]
    job["identity"] = identity
    original["job"] = job
    native_sha = "sha256:" + _sha(native)
    request = dict(
        original,
        job=dict(
            job,
            native_input=dict(path=str(native), sha256=native_sha),
            output_root=str(path.parent / "position"),
            identity=dict(
                identity, input_sha256=native_sha, run_id="experiment-" + native_sha[7:39]
            ),
        ),
    )
    whole_iq.verify_request(request, original, native_path=str(native), native_sha256=native_sha)
    save_json(path, request)
    return native_sha


def chunks(case):
    output, base = [], 0
    for segment, locator in enumerate(case["recording"]["segments"]):
        path = (BULK / locator["path"]).resolve()
        if path.name != "manifest.json" or not path.is_relative_to(ARCHIVE):
            raise ValueError("each segment manifest must be in the supported saved-IQ archive")
        data = _read_prefix(path, 65537)
        if len(data) > 65536 or sha256(data).hexdigest() != locator["sha256"]:
            raise ValueError("a segment manifest failed SHA-256 verification")
        manifest, first = json.loads(data), 0
        for chunk in manifest["chunks"]:
            if chunk["first_sequence"] != first or chunk["window_count"] < 1:
                raise ValueError("signed chunk ranges must cover consecutive sequence numbers")
            stop = first + chunk["window_count"]
            output.append((segment, first, stop, base))
            first = stop
        if manifest["window_count"] != first:
            raise ValueError("segment chunks do not cover the signed window count")
        base += first
    if not output or base != case["recording"]["window_count"]:
        raise ValueError("recording chunks do not cover the signed window count")
    return output


def receiver_assets(path):
    programs = whole_iq.receiver_identity(path)
    content = {key: digest for key, digest in programs.items() if key != "native/manifest.json"}
    if sha256(encoded(content)).hexdigest() != CALIBRATION_SHA:
        raise ValueError("compact position installation differs from the qualified phase release")
    if whole_iq.native_sources(path) != NUMERIC_SOURCES:
        raise ValueError("compact native source differs from the qualified phase release")
    return programs


def selector_evidence(backend, producer):
    installed = producer / "leo/analysis/starlink/acquisition.py"
    if backend == "installed":
        return dict(
            backend=backend, version="installed-v1", source=str(installed), sha256=_sha(installed)
        )
    if backend != "row-wise" or producer not in ROW_SELECTOR_PRODUCERS:
        raise ValueError(f"peak selector {backend!r} is unqualified for producer {producer}")
    producer_sha = ROW_SELECTOR_PRODUCERS[producer]
    whole_iq.checked(installed, producer_sha)
    source = Path(prepared_hotpath_peaks.__file__)
    whole_iq.checked(source, ROW_SELECTOR_SHA)
    return dict(
        backend=backend,
        version="row-wise-v1",
        source=str(source),
        sha256=ROW_SELECTOR_SHA,
        producer_source=str(installed),
        producer_sha256=producer_sha,
        qualification_sha256=ROW_SELECTOR_QUALIFICATION,
    )


def peak_selector_for(lock):
    evidence = lock.get("peak_selector")
    if evidence is None:
        return nullcontext()
    backend = evidence["backend"]
    if evidence != selector_evidence(backend, Path(lock["producer"])):
        raise ValueError("peak selector differs from the source seal")
    if backend == "installed":
        return nullcontext()
    from leo.analysis.starlink import acquisition

    if Path(acquisition.__file__) != Path(evidence["producer_source"]):
        raise ValueError("the installed acquisition producer must own the peak selector")
    return patch.object(
        acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks
    )


def pruned_fine_evidence(producer, *, batched=False):
    if producer not in ROW_SELECTOR_PRODUCERS:
        raise ValueError(f"pruned fine search is unqualified for producer {producer}")
    acquisition = producer / "leo/analysis/starlink/acquisition.py"
    sources = FINE_SOURCES | {acquisition: ROW_SELECTOR_PRODUCERS[producer]}
    if batched:
        sources.update(BATCH_SOURCES)
    for path, digest in sources.items():
        whole_iq.checked(path, digest)
    evidence = dict(
        backend="batched" if batched else "pruned",
        version="batched-v1" if batched else "pruned-v1",
        qualification_sha256=BATCH_QUALIFICATION if batched else FINE_QUALIFICATION,
        numpy_version=FINE_NUMPY_VERSION,
        pocketfft_sha256=FINE_POCKETFFT_SHA,
        sources={str(path): digest for path, digest in sources.items()},
    )
    if batched:
        evidence["frame_lanes"] = fine_batch.LANES
    return evidence


def pruned_library(out, kernel_dir, *, batched=False):
    started = monotonic()
    implementation = fine_batch if batched else fine_search
    cache = BATCH_LIBRARY_CACHE if batched else FINE_LIBRARY_CACHE
    expected = BATCH_LIBRARY_SHA if batched else FINE_LIBRARY_SHA
    if batched and not fine_batch.supports_host():
        raise ValueError("batched fine search requires AVX2 support")
    choices = (
        (kernel_dir / cache.name,) if kernel_dir is not None else (KERNEL_DIR / cache.name, cache)
    )
    library = next((path for path in choices if path.exists()), None)
    command = None
    if library is None:
        directory = out / "fine-build"
        directory.mkdir()
        try:
            library, command = implementation.build(directory)
        except (subprocess.CalledProcessError, RuntimeError) as error:
            raise ValueError("could not compile the qualified fine search") from error
    whole_iq.checked(library, expected)
    return library, dict(
        mode="compiled" if command else "reused",
        source=str(library),
        command=command,
        wall_s=monotonic() - started,
    )


def fine_search_for(lock, libs):
    selected = lock.get("fine_search")
    if selected is None:
        return None
    producer = Path(lock["producer"])
    batched = selected["backend"] == "batched"
    expected = pruned_fine_evidence(producer, batched=batched)
    if any(selected[key] != value for key, value in expected.items()):
        raise ValueError("pruned fine search differs from the source seal")
    from numpy import __version__ as numpy_version
    from numpy.fft import _pocketfft_umath

    from leo.analysis.starlink import acquisition

    if Path(acquisition.__file__) != producer / "leo/analysis/starlink/acquisition.py":
        raise ValueError("the installed acquisition producer must own the pruned fine search")
    if numpy_version != FINE_NUMPY_VERSION:
        raise ValueError(f"unqualified NumPy {numpy_version} for pruned fine search")
    whole_iq.checked(Path(_pocketfft_umath.__file__), FINE_POCKETFFT_SHA)
    if batched:
        if not fine_batch.supports_host():
            raise ValueError("batched fine search requires AVX2 support")
        library = whole_iq.checked(libs["fine"], BATCH_LIBRARY_SHA)
        return fine_batch.FineBatch(library, acquisition)
    library = whole_iq.checked(libs["fine"], FINE_LIBRARY_SHA)
    return fine_search.FineSearch(library, acquisition)


def fractional_stop_evidence(backend, producer):
    if backend not in ("first", "second") or producer not in ROW_SELECTOR_PRODUCERS:
        raise ValueError(f"fractional stop {backend!r} is unqualified for producer {producer}")
    sources = {producer / path: digest for path, digest in first_gate.PRODUCER_FILES.items()}
    sources[producer / "leo/analysis/starlink/acquisition.py"] = ROW_SELECTOR_PRODUCERS[producer]
    sources[Path(first_gate.__file__)] = GATE_SOURCE_SHA
    for path, digest in sources.items():
        whole_iq.checked(path, digest)
    return dict(
        backend=backend,
        version="ranked-fractional-stop-v1",
        passes=FRACTIONAL_STOPS[backend],
        gate=first_gate.GATE,
        sources={str(path): digest for path, digest in sources.items()},
        qualification_sha256=GATE_QUALIFICATION,
    )


class GateAttemptTally:
    def __init__(self):
        self.counts = dict(attempts=0, available=0, evaluated=0, shortened_attempts=0)

    def append(self, record):
        _, _, available, responses = record
        self.counts["attempts"] += 1
        self.counts["available"] += available
        self.counts["evaluated"] += len(responses)
        self.counts["shortened_attempts"] += len(responses) < available


def fractional_stop_for(lock):
    selected = lock.get("fractional_stop")
    if selected is None:
        return None
    producer = Path(lock["producer"])
    if selected != fractional_stop_evidence(selected["backend"], producer):
        raise ValueError("fractional stop differs from the source seal")
    from leo.analysis.starlink import fast_scan_scores
    from leo.scanner import fast_scan_detector

    if any(
        str(Path(module.__file__)) not in selected["sources"]
        for module in (fast_scan_detector, fast_scan_scores)
    ):
        raise ValueError("the installed producer must own the fractional stop bindings")
    gate = first_gate.GateStop(fast_scan_detector, selected["passes"])
    gate.attempts = GateAttemptTally()
    return gate


def interior_guard_sources():
    policy = (final_region, compact_tile_interior, v5_secant_fit)
    return {module.__file__: _sha(Path(module.__file__)) for module in policy}


def prepare(
    case,
    out,
    cpus,
    raw_limit,
    position_limit,
    receiver,
    kernel_dir,
    smoke,
    peak_selector="installed",
    interior_guard=False,
    fine_backend="installed",
    fractional_stop="full",
    short_fft=False,
):
    from .qualification import capture_whole_results

    if len(set(cpus)) != len(cpus) or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("choose distinct available CPU numbers")
    if out.is_relative_to(BULK / "leo"):
        raise ValueError("choose an output outside the recording archive")
    ranges = chunks(case)
    capture = capture_release.read_capture(case)
    producer = capture_release.producer(case, capture)
    selector = selector_evidence(peak_selector, producer.root)
    if fine_backend not in FINE_SEARCHES:
        raise ValueError("unknown fine search backend")
    batched = fine_backend == "batched"
    fine = (
        pruned_fine_evidence(producer.root, batched=batched)
        if fine_backend != "installed"
        else None
    )
    stop = (
        None
        if fractional_stop == "full"
        else fractional_stop_evidence(fractional_stop, producer.root)
    )
    binding(case)
    capture["case"] = {key: case[key] for key in ("id", "session_id", "run_id")}
    receiver_files = receiver_assets(receiver)
    python = whole_iq.checked(recording.ARCHIVE_PYTHON, PYTHON_SHA)
    original_libraries = {}
    kernels = KERNELS | {"prepared": SHORT_FFT} if short_fft else KERNELS
    for role, (default, digest) in kernels.items():
        path = default if kernel_dir is None else kernel_dir / default.name
        original_libraries[role] = (whole_iq.checked(path, digest), digest)
    if smoke:
        ranges = ranges[:1]
    if len(cpus) > len(ranges):
        raise ValueError("choose at most one CPU per scheduled chunk, and one for --smoke")
    workers = capture_whole.partition(ranges, frozenset(), tuple(cpus))
    out.mkdir(parents=True, exist_ok=False)
    if fine is not None:
        library, installation = pruned_library(out, kernel_dir, batched=batched)
        original_libraries["fine"] = (library, BATCH_LIBRARY_SHA if batched else FINE_LIBRARY_SHA)
    libraries = {}
    for role, (path, digest) in original_libraries.items():
        staged = out / "kernels" / path.name
        write(staged, path.read_bytes())
        staged.chmod(0o444)
        libraries[role] = dict(path=str(whole_iq.checked(staged, digest)), sha256=digest)
    programs = (
        Path(__file__),
        Path(capture_whole.__file__),
        Path(capture_whole_results.__file__),
        Path(prepared.__file__),
        Path(recording.__file__),
        Path(whole_iq.__file__),
    )
    lock = dict(
        id=case["id"],
        case=case,
        capture=capture,
        recording=case["recording"],
        producer=str(producer.root),
        peak_selector=selector,
        python=str(python),
        python_sha256=PYTHON_SHA,
        libraries=libraries,
        workers=workers,
        cpus=cpus,
        smoke=smoke,
        raw_limit_s=raw_limit,
        position_limit_s=position_limit,
        receiver=str(receiver),
        receiver_files=receiver_files,
        sources={str(path): _sha(path) for path in programs},
    )
    if interior_guard:
        lock["interior_guard"] = interior_guard_sources()
    if short_fft:
        lock["coarse_search"] = dict(
            fft_samples=256,
            planner="stored-measure",
            qualification_sha256=SHORT_FFT_QUALIFICATION,
            library_sha256=libraries["prepared"]["sha256"],
        )
    if fine is not None:
        lock["fine_search"] = fine | dict(library=libraries["fine"], installation=installation)
    if stop is not None:
        lock["fractional_stop"] = stop
    save_json(out / "source-lock.json", lock)
    (out / "source-lock.json").chmod(0o644)
    return lock


def configure(work):
    lock = whole_iq.read(work / "source-lock.json")
    for path, digest in lock["sources"].items():
        whole_iq.checked(Path(path), digest)
    whole_iq.checked(Path(lock["python"]), lock["python_sha256"])
    libs = {k: whole_iq.checked(Path(v["path"]), v["sha256"]) for k, v in lock["libraries"].items()}
    return lock, libs


def live_validity(lock):
    """Ordinary replay schedules signed chunks and learns exclusions during acquisition."""
    return dict(lock, workers=[(cpu, None, chunks) for cpu, _, chunks in lock["workers"]])


def shard(work, cpu, source_sha):
    whole_iq.checked(work / "source-lock.json", source_sha)
    lock, libs = configure(work)
    fine = fine_search_for(lock, libs)
    gate = fractional_stop_for(lock)
    try:
        if fine is not None and not fine.compatible:
            raise ValueError("installed FFT runtime failed the pruned fine search arithmetic check")
        with (
            patch.object(capture_whole, "configure", return_value=(live_validity(lock), libs)),
            peak_selector_for(lock),
            fine.route() if fine is not None else nullcontext(),
            gate.route() if gate is not None else nullcontext(),
        ):
            prepared.raw(work, cpu)
    finally:
        if fine is not None:
            evidence = dict(
                cpu=cpu,
                source_lock_sha256=source_sha,
                compatible=fine.compatible,
                pruned_calls=fine.calls,
                installed_fallbacks=fine.fallbacks,
            )
            print(FINE_TRACE + json.dumps(evidence), file=sys.stderr, flush=True)
        if gate is not None:
            evidence = dict(cpu=cpu, source_lock_sha256=source_sha, **gate.attempts.counts)
            print(GATE_TRACE + json.dumps(evidence), file=sys.stderr, flush=True)


def worker(attempt):
    plan = whole_iq.read(attempt / "plan.json")
    work, (cpu,) = attempt.parent, plan["cpus"]
    lock = whole_iq.read(whole_iq.checked(work / "source-lock.json", plan["source_lock_sha256"]))
    save_json(attempt / "start.json", whole_iq.raw.mark("original receiver worker enter"))
    if plan["stage"] == "position":
        if receiver_assets(Path(lock["receiver"])) != lock["receiver_files"]:
            raise ValueError("compact installation changed after the source seal")
        policy = lock.get("interior_guard")
        if policy is None:
            whole_iq.position(attempt)
        else:
            for path, digest in policy.items():
                whole_iq.checked(Path(path), digest)
            whole_iq.position(attempt, publish=partial(final_region.publish, enabled=True))
        return 0
    command = [
        "sudo",
        "-n",
        "-u",
        "leo",
        "--",
        "env",
        f"PYTHONPATH={lock['producer']}:{ROOT}",
        *(f"{k}={v}" for k, v in THREAD_ENV.items()),
        lock["python"],
        "-Bu",
        "-m",
        MODULE,
        "shard",
        str(work),
        str(cpu),
        plan["source_lock_sha256"],
    ]
    with (
        (work / f"cpu-{cpu}.jsonl").open("xb") as data,
        (work / f"cpu-{cpu}.log").open("xb") as log,
    ):
        return subprocess.run(command, stdout=data, stderr=log, check=False).returncode


def service(attempt, cpu, limit, stage, options=None):
    parent = attempt.parent
    plan = dict(
        stage=stage,
        cpus=[cpu],
        limit_s=limit,
        source_lock_sha256=_sha(parent / "source-lock.json"),
        **(options or {}),
    )
    save_json(attempt / "plan.json", plan)
    unit = "leo-iq-bench-" + uuid4().hex[:12]
    command = capture_whole.service(
        unit,
        limit,
        [
            f"--setenv=TMPDIR={attempt}",
            *(f"--setenv={k}={v}" for k, v in THREAD_ENV.items()),
            "taskset",
            "-c",
            str(cpu),
            sys.executable,
            "-B",
            "-m",
            MODULE,
            "worker",
            str(attempt),
        ],
    )
    return iq_service.run(attempt, command, unit, timeout=limit + 20)


def collect(work, lock):
    from .qualification import capture_whole_results

    return capture_whole_results.collect(work, live_validity(lock))


def bind_short_fft(document, lock):
    """Include the accelerated detector choices in the native measurement identity."""
    source, provenance = document["source"], document["provenance"]
    detector = recording.digest(
        [
            provenance["detector_sha256"],
            lock["coarse_search"],
            {name: lib["sha256"] for name, lib in lock["libraries"].items()},
            lock["peak_selector"]["backend"],
            lock.get("fine_search", {}).get("backend", "installed"),
            lock.get("fractional_stop", {}).get("backend", "full"),
        ]
    )
    analysis = recording.digest([source["analysis_manifest_sha256"], detector])
    source["analysis_manifest_sha256"] = analysis
    provenance.update(
        detector_sha256=detector,
        run_id="replay-" + analysis[7:39],
        scope="fresh original capture detector with a stored 256-point coarse FFT",
    )


def fit(out, lock, shards):
    """Assemble complete verified shards and invoke the compact receiver once."""
    from .qualification.capture_whole_results import assemble

    document, counts = assemble(lock["case"], lock, shards)
    if "coarse_search" in lock:
        bind_short_fft(document, lock)
    native = out / "native.json"
    recording.save(native, document)
    attempt = out / "position"
    request = attempt / "recording/request.json"
    request.parent.mkdir(parents=True, exist_ok=False)
    native_sha = bind_fresh(lock["case"], native, request)
    save_json(attempt / "raw.json", dict(native_sha256=native_sha, request_sha256=_sha(request)))
    with patch.object(iq_service, "MODULE", MODULE):
        receipt = service(
            attempt,
            lock["cpus"][0],
            lock["position_limit_s"],
            "position",
            dict(receiver=lock["receiver"]),
        )
    result = dict(
        stage="position", position_service=receipt, counts=counts, native_sha256=native_sha
    )
    if not iq_service.succeeded(receipt):
        return dict(result, status=failure_status((receipt,)))
    prediction = whole_iq.read(attempt / "position.json")
    validate_result(prediction)
    return dict(result, status=prediction["status"], result=prediction)


def raw_option_receipt(out, cpu, source_sha, prefix):
    log = out / f"cpu-{cpu}.log"
    if not log.exists():
        return None
    with log.open() as stream:
        rows = [json.loads(line.removeprefix(prefix)) for line in stream if line.startswith(prefix)]
    if not rows:
        return None
    (row,) = rows
    if row["cpu"] != cpu or row["source_lock_sha256"] != source_sha:
        raise ValueError("raw option worker receipt differs from the source seal")
    return row


def fine_worker_receipt(out, cpu, source_sha):
    return raw_option_receipt(out, cpu, source_sha, FINE_TRACE)


def run(out, lock):
    from .qualification import capture_whole_results

    with patch.object(iq_service, "MODULE", MODULE):
        started = monotonic()

        def raw_job(row):
            cpu = row[0]
            return cpu, service(out / f"raw-{cpu}", cpu, lock["raw_limit_s"], "raw")

        with ThreadPoolExecutor(max_workers=len(lock["workers"])) as pool:
            receipts = dict(pool.map(raw_job, lock["workers"]))
        raw_wall = monotonic() - started
        source_sha = _sha(out / "source-lock.json")
        save_json(out / "launch.json", dict(source_lock_sha256=source_sha))
        save_json(
            out / "raw-exits.json",
            dict(exits={str(c): r["exit_code"] for c, r in receipts.items()}, wall_s=raw_wall),
        )
        result = dict(
            id=lock["id"],
            mode="smoke" if lock["smoke"] else "full",
            peak_selector=lock.get("peak_selector", {"backend": "installed"}),
            raw_wall_s=raw_wall,
            raw_services=receipts,
        )
        if "coarse_search" in lock:
            result["coarse_search"] = lock["coarse_search"]
        failed = [receipt for receipt in receipts.values() if not iq_service.succeeded(receipt)]
        fine = lock.get("fine_search")
        if fine is not None:
            workers = {cpu: fine_worker_receipt(out, cpu, source_sha) for cpu in receipts}
            result["fine_search"] = fine | {"workers": workers}
            if not failed and any(row is None or not row["compatible"] for row in workers.values()):
                raise ValueError(
                    "finished raw workers must attest to compatible pruned fine search"
                )
        stop = lock.get("fractional_stop")
        if stop is not None:
            gate = {cpu: raw_option_receipt(out, cpu, source_sha, GATE_TRACE) for cpu in receipts}
            result["fractional_stop"] = stop | {"workers": gate}
            if not failed and any(row is None for row in gate.values()):
                raise ValueError("finished raw workers must attest to the fractional stop policy")
        if failed:
            return dict(result, status=failure_status(failed), stage="raw")
        shards, workers, _ = collect(out, lock)
        rows = capture_whole_results.summary_rows(shards)
        result.update(
            completed_visits=len(rows),
            recorded_visits=lock["recording"]["window_count"],
            valid_visits=sum(row["status"] == "processed" for row in rows),
            invalid_visits=sum(row["status"] == "invalid_capture" for row in rows),
            grid_calls=sum(row["folded_calls"] for row in rows),
            workers=workers,
        )
        if lock["smoke"]:
            return dict(result, status="stage_only", stage="raw")
        return result | fit(out, lock, shards)


def failure_status(receipts):
    return (
        "timed_out"
        if all(receipt.get("systemd", {}).get("Result") == "timeout" for receipt in receipts)
        else "failed"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--case", help="recording ID in the frozen input inventory")
    source.add_argument("--input", type=Path, help="authenticated recording locator JSON")
    parser.add_argument("--input-sha256")
    parser.add_argument("--out", required=True, type=local_output)
    parser.add_argument("--cpus", required=True, nargs="+", type=int)
    parser.add_argument("--raw-limit", type=int, default=600, metavar="SECONDS")
    parser.add_argument("--position-limit", type=int, default=180, metavar="SECONDS")
    parser.add_argument("--receiver", type=local_output, default=CALIBRATION)
    parser.add_argument("--kernel-dir", type=local_output)
    parser.add_argument(
        "--accelerated",
        action="store_true",
        help="use the stored 256-point coarse FFT, row-wise peak selection and batched fine search",
    )
    parser.add_argument(
        "--peak-selector",
        choices=PEAK_SELECTORS,
        help="override peak selection (installed by default, row-wise with --accelerated)",
    )
    parser.add_argument(
        "--fine-search",
        choices=FINE_SEARCHES,
        help="override fine CFO search (installed by default, batched with --accelerated)",
    )
    parser.add_argument(
        "--interior-guard",
        action="store_true",
        help="withhold both positions when either fit is within 20 m of a tile face",
    )
    parser.add_argument(
        "--fractional-stop",
        choices=FRACTIONAL_STOPS,
        default="full",
        help="research policy to keep ranks through the first or second fractional gate pass",
    )
    parser.add_argument(
        "--smoke", action="store_true", help="measure one complete chunk without fitting a position"
    )
    args = parser.parse_args(argv)
    if not (1 <= args.raw_limit <= 600 and 1 <= args.position_limit <= 600):
        parser.error("each service limit must be 1 through 600 seconds")
    try:
        case = input_case(args.case, args.input, args.input_sha256)
        start = monotonic()
        selector = args.peak_selector or ("row-wise" if args.accelerated else "installed")
        fine = args.fine_search or ("batched" if args.accelerated else "installed")
        acquisition_options = {} if fine == "installed" else {"fine_backend": fine}
        if args.accelerated:
            acquisition_options["short_fft"] = True
        if args.fractional_stop != "full":
            acquisition_options["fractional_stop"] = args.fractional_stop
        plan = prepare(
            case,
            args.out,
            args.cpus,
            args.raw_limit,
            args.position_limit,
            args.receiver,
            args.kernel_dir,
            args.smoke,
            peak_selector=selector,
            interior_guard=args.interior_guard,
            **acquisition_options,
        )
    except (KeyError, TypeError, OSError, ValueError) as error:
        parser.error(str(error))
    setup_wall = monotonic() - start
    result = run(args.out, plan) | {"setup_wall_s": setup_wall}
    save_json(args.out / "summary.json", result)
    print(json.dumps({key: result[key] for key in ("id", "status", "stage")}), flush=True)
    return int(result["status"] in ("failed", "unavailable", "timed_out"))


if __name__ == "__main__":
    if sys.argv[1:2] == ["worker"] and len(sys.argv) == 3:
        raise SystemExit(worker(local_output(sys.argv[2])))
    if sys.argv[1:2] == ["shard"] and len(sys.argv) == 5:
        shard(local_output(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
    else:
        raise SystemExit(main())
