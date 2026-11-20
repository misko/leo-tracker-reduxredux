"""Qualify a complete lower-edge screened original capture with batched fine CFO."""

import argparse
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json
from ..variants.fine_batch import FineBatch
from ..variants.fine_search import FineSearch
from ..variants.original_kernel import PersistentGrid
from ..variants.selective_capture import visit_pairs
from . import capture_whole as base
from . import field_exact_waveform as previous
from . import prepared_capture_waveform as prepared
from . import selector_waveform
from .full_v5_check import _sha

IDENT = "DS29-0519"
REPORT = ROOT / "reports/2026_11_19_receiver_screening/retry-and-transfer/batched-waveform"
PANEL = REPORT.with_name("fine-batch")
PANEL_SHA = "b529eda1890f00ee6ecb7362de1fe2cd613888c8d8057224abb3c747d9aca1e9"
WORK = Path("/var/tmp/leo-batched-waveform-ds29-0519-20261119")
METHOD = "original_capture_batched_fine_full_iq"
MODULE = "tools.pipeline_eval.qualification.batched_waveform"
CPUS = (0, 1, 6, 7, 8, 9, 10, 11)
CAPACITY = {cpu: (1.0 if cpu <= 7 else 0.68) for cpu in CPUS}
TRACE = previous.TRACE
FINE_COUNTERS = previous.FINE_COUNTERS
EXPECTED = dict(scheduled=6771, valid=6727, invalid=44, probes=13454, candidates=62048, empty=22)


@contextmanager
def configured():
    with patch.multiple(base, IDENT=IDENT, REPORT=REPORT, METHOD=METHOD, MODULE=MODULE):
        yield


def partition(chunks, invalid):
    """Balance prospective detector work by CPU class, with no access to RF outcomes."""
    totals, assignment = dict.fromkeys(CPUS, 0), {cpu: [] for cpu in CPUS}
    valid = [
        (sum(v not in invalid for v in range(base_index + first, base_index + stop)), chunk)
        for chunk in chunks
        for _, first, stop, base_index in [chunk]
    ]
    for count, chunk in sorted(valid, key=lambda x: (-x[0], x[1])):
        cpu = min(CPUS, key=lambda c: ((totals[c] + count) / CAPACITY[c], len(assignment[c]), c))
        assignment[cpu].append(chunk)
        totals[cpu] += count
    return [(cpu, totals[cpu], sorted(assignment[cpu])) for cpu in CPUS]


def freeze(work):
    from .fresh_replay_results import sealed
    from .scheduled_capture_waveform import metadata

    path = REPORT / "source-lock.json"
    if path.exists() or work.exists():
        raise FileExistsError("preserve the first qualification source and work directories")
    receipt = sealed(PANEL, "qualification-lock.json", PANEL_SHA)
    batch = whole_iq.read(PANEL / "input-lock.json")
    result = whole_iq.read(PANEL / "summary.json")
    pooled = result["pooled"]["detector"]["cpu"]
    if not (
        result["qualified"] is True
        and len(result["cases"]) == 4
        and pooled["saved"]["n"] == 80
        and pooled["saved"]["median"] >= 10
        and pooled["saved_percent"] >= 3
    ):
        raise ValueError("the gated batched detector has no material four-case qualification")
    legacy_seal = sealed(base.exact.REPORT, "qualification-lock.json")
    legacy_path = whole_iq.checked(
        base.exact.REPORT / "source-lock.json", legacy_seal["files"]["source-lock.json"]
    )
    old = whole_iq.read(legacy_path)
    found = old["cases"][IDENT]
    study = batch["cases"][IDENT]
    case, original_request = whole_iq.binding(IDENT)
    capture = base.capture_release.read_capture(case)
    expected = (study["root"], study["edge"], study["input_manifest"], study["archive_sha256"])
    original = found["root"]
    if expected != (
        original["producer"],
        original["edge"],
        original["input_manifest_sha256"],
        original["archived_native_sha256"],
    ) or expected != (
        str(base.capture_release.producer(case, capture).root),
        "lower",
        capture["input_manifest_sha256"],
        case["native"]["sha256"],
    ):
        raise ValueError("the screened original DS29-0519 release does not match its exact panel")
    if found["python_sha256"] != batch["python_sha256"] or any(
        old["libraries"][k] != batch["libs"][k] for k in ("batched32", "cfo", "fused")
    ):
        raise ValueError("original and batched capture environments differ")
    archive = whole_iq.read(
        whole_iq.checked(base.BULK / case["native"]["path"], case["native"]["sha256"])
    )
    count, chunks = metadata(case)
    invalid = {item["visit"] for item in archive["provenance"]["excluded_windows"]}
    factors = archive["source"]["probes"]
    if (
        dict(
            scheduled=len(count),
            valid=len(count) - len(invalid),
            invalid=len(invalid),
            probes=len(factors),
            candidates=sum(len(r["candidates"]) for r in factors),
            empty=sum(not r["candidates"] for r in factors),
        )
        != EXPECTED
        or len(archive["delivery_clocks"]) != EXPECTED["scheduled"]
    ):
        raise ValueError("the declared authentic DS29-0519 physical roster changed")
    before = set(invalid) | set(original["visits"]) | {r["visit"] for r in found["rows"]}
    held = {r["visit"]: r["iq_sha256"] for r in study["rows"]}
    unseen = sorted(
        set(range(len(count))) - before - held.keys(),
        key=lambda v: base.recording.digest([IDENT, "new-batched-preflight-v1", v]),
    )[:3]
    smoke = []
    for visit in sorted([*held, *unseen, min(invalid)]):
        segment, _, _, offset = next(c for c in chunks if c[3] + c[1] <= visit < c[3] + c[2])
        smoke.append((segment, visit - offset, visit))
    receiver_lock = base.exact.REPORT.parent / "on-hit-waveforms/source-lock.json"
    receiver_description = whole_iq.read(receiver_lock)
    receiver = Path(receiver_description["receiver"])
    if whole_iq.receiver_identity(receiver) != receiver_description["receiver_files"]:
        raise ValueError("the already qualified standalone compact receiver differs")
    sources = old["sources"] | original["sources"] | batch["sources"] | study["sources"]
    for f in (
        Path(__file__),
        Path(prepared.__file__),
        Path(base.__file__),
        Path(selector_waveform.__file__),
        REPORT / "PROTOCOL.md",
        receiver_lock,
        PANEL / "qualification-lock.json",
        PANEL / "summary.json",
        PANEL / "input-lock.json",
        PANEL / f"{IDENT}.json.gz",
    ):
        sources[str(f)] = _sha(f)
    for f, digest in sources.items():
        whole_iq.checked(Path(f), digest)
    for entry in batch["libs"].values():
        whole_iq.checked(Path(entry["path"]), entry["sha256"])
    private = {f: h for f, h in sources.items() if not Path(f).stat().st_mode & 0o004}
    native = case["native"]
    capture.update(case={key: case[key] for key in ("id", "run_id", "session_id")})
    lock = dict(
        id=IDENT,
        capture=capture,
        recording=case["recording"],
        libraries=batch["libs"],
        original=dict(
            native=native,
            request=case["request"],
            catalog=case["catalog"],
            tile=case["regions"][0],
            causal_snapshots=original_request["causal_snapshots"],
        ),
        producer=study["root"],
        python=found["python"],
        python_sha256=batch["python_sha256"],
        sources={f: h for f, h in sources.items() if f not in private},
        evidence_sources=private,
        raw_limit_s=720,
        position_limit_s=180,
        receiver=str(receiver),
        receiver_files=receiver_description["receiver_files"],
        memory_max=whole_iq.MEMORY,
        workers=partition(chunks, invalid),
        capacity=CAPACITY,
        smoke=smoke,
        smoke_invalid=[min(invalid)],
        held_sha256={str(v): h for v, h in held.items()},
        unseen=unseen,
        batch_qualification_sha256=PANEL_SHA,
        archival_counts=EXPECTED,
        archival_launch_probes={
            str(v): p for v, p in visit_pairs(factors) if any(v == s[2] for s in smoke)
        },
    )
    if receipt["files"]["input-lock.json"] != _sha(PANEL / "input-lock.json"):
        raise ValueError("the four-case plan changed during complete-track preparation")
    work.mkdir(mode=0o755)
    for out in (path, work / path.name):
        save_json(out, lock)
        out.chmod(0o644)
    print("Authenticated chunks", len(chunks), "scheduled preflight", smoke, flush=True)
    print("CPU / valid visits", [(cpu, n) for cpu, n, _ in lock["workers"]], flush=True)


def batched_for(lock, library):
    from leo.analysis.starlink import acquisition

    source = Path(acquisition.__file__)
    if str(source) not in lock["sources"] or not source.is_relative_to(lock["producer"]):
        raise ValueError("batched FFT must bind the signed DS29 capture producer")
    impl = FineBatch(library, acquisition)
    if not impl.compatible:
        raise ValueError("AVX2 batch failed the installed scalar FFT arithmetic sentinel")
    return impl


def smoke(work):
    from leo.analysis.starlink import acquisition

    lock, libs = base.configure(work)
    policy = base.policy_for(lock)
    grid = PersistentGrid(libs["prepared"])
    batched = batched_for(lock, libs["batch"])
    scalar = FineSearch(libs["fine"], acquisition)
    if not scalar.compatible:
        raise ValueError("the incumbent pruned path failed its runtime sentinel")
    rows = []
    try:
        for segment, index, visit in lock["smoke"]:
            (window,) = base.open_span(lock, segment, index, index + 1).windows()
            if window.acquisition["global_visit"] != visit or window.iq_sha256 != lock[
                "held_sha256"
            ].get(str(visit), window.iq_sha256):
                raise ValueError("launch check addressed different signed IQ")
            observed = SimpleNamespace(**vars(window), receiver_ids=(0, 1))
            reference = base.exact.trial(observed, policy, "installed", libs)
            rows_by_mode = {"installed": reference}
            counters = {}
            with base.exact.refiners(libs), selector_waveform.selector(lock):
                for name, backend in (("scalar", scalar), ("batched", batched)):
                    start = backend.calls
                    with backend.route():
                        rows_by_mode[name] = base.exact.stages.detector(observed, policy, grid)
                    counters[name] = backend.calls - start
            valid = visit not in lock["smoke_invalid"]
            status = "processed" if valid else "invalid_capture"
            if (
                reference["status"] != status
                or encoded(reference["probes"])
                != encoded(lock["archival_launch_probes"].get(str(visit), []))
                or any(r != valid for r in (v > 0 for v in counters.values()))
                or scalar.fallbacks
                or batched.fallbacks
                or any(
                    encoded(row[key]) != encoded(reference[key])
                    for row in rows_by_mode.values()
                    for key in ("status", "public", "probes", "attempts")
                )
            ):
                raise ValueError(
                    f"installed, scalar or batched public path differs at visit {visit}"
                )
            rows.append(
                dict(
                    visit=visit,
                    status=status,
                    iq_sha256=window.iq_sha256,
                    cpu_ns={name: r["cpu_ns"] for name, r in rows_by_mode.items()},
                    wall_ns={name: r["wall_ns"] for name, r in rows_by_mode.items()},
                    fine_calls=counters,
                    **{
                        f"{k}_sha256": base.recording.digest(reference[k])
                        for k in ("public", "probes", "attempts")
                    },
                )
            )
            grid.calls.clear()
    finally:
        grid.clear_cache()
    print(
        encoded(dict(source_lock_sha256=_sha(work / "source-lock.json"), rows=rows)).decode(),
        flush=True,
    )


def raw(work, cpu):
    lock, libs = base.configure(work)
    impl = batched_for(lock, libs["batch"])
    with (
        selector_waveform.selector(lock),
        impl.route(),
        patch.object(prepared, "VisitGridRecords", lambda: previous.VisitRecords(impl)),
    ):
        prepared.raw(work, cpu)


def run(work):
    """Cap each launched worker against the same fixed 720-second deadline."""
    previous.check_evidence(work)
    service = base.service
    deadline = perf_counter() + 720

    def bounded(unit, limit, command):
        remaining = int(deadline - perf_counter())
        if remaining < 1:
            raise TimeoutError("the common raw launch budget expired")
        return service(unit, min(limit, remaining), command)

    with patch.object(base, "service", bounded):
        base.run(work)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "preflight", "smoke", "raw", "run"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    parser.add_argument("cpu", type=int, nargs="?", default=CPUS[0])
    args = parser.parse_args()
    with configured():
        if args.action == "freeze":
            freeze(args.work)
        elif args.action == "preflight":
            previous.check_evidence(args.work)
            command = base.service(
                f"leo-batched-preflight-{uuid4().hex[:8]}",
                90,
                base.command(args.work, args.cpu, "smoke"),
            )
            output = subprocess.run(command, stdout=subprocess.PIPE, check=True, timeout=100)
            result = json.loads(output.stdout)
            save_json(args.work / "smoke.json", result)
            for row in result["rows"]:
                print(row["visit"], row["status"], row["fine_calls"], flush=True)
        elif args.action == "smoke":
            smoke(args.work)
        elif args.action == "raw":
            raw(args.work, args.cpu)
        else:
            run(args.work)


if __name__ == "__main__":
    main()
