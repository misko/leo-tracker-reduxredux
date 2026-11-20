"""Bind and replay one complete upper-edge original capture after a fixed coarse decision."""

import argparse
import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json
from ..variants import nested_anchors
from ..variants.original_kernel import PersistentGrid
from ..variants.selective_capture import visit_pairs
from . import batched_waveform as incumbent
from . import capture_whole as base
from . import prepared_capture_waveform as prepared
from . import selector_waveform
from .full_v5_check import _sha, compare_probes

IDENT = "DS26-0162"
SCREENING = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREENING / "coarse-and-navigation/coarse-waveform"
WORK = Path("/var/tmp/leo-coarse-waveform-ds26-0162-20261120")
HOLDOUT = SCREENING / "retry-and-transfer/retry-policy-holdout"
PEER = SCREENING / "retry-and-transfer/peer-retry"
PANEL = incumbent.PANEL
PANEL_SHA = incumbent.PANEL_SHA
METHOD = "original_capture_coarse_complete_iq"
MODULE = "tools.pipeline_eval.qualification.coarse_waveform"
EXPECTED = dict(scheduled=6772, valid=6713, invalid=59, probes=13426, candidates=63534, empty=28)
MINIMUM_CPUS = (6, 7, 8, 9, 10, 11)
CPU_ROSTERS = (
    MINIMUM_CPUS,
    (0, 1, *MINIMUM_CPUS),
    (2, 3, *MINIMUM_CPUS),
    (4, 5, *MINIMUM_CPUS),
    (*MINIMUM_CPUS, 16, 23),
)
DECISION_UTC = "2026-11-20T00:27:00Z"
TRACE = incumbent.TRACE
FINE_COUNTERS = incumbent.FINE_COUNTERS
NESTED_TRACE = "nested-anchor-v1: "
NESTED_SOURCE = "605da890fc46c516415b26deb183bbd1e01664bcf8392a66f58fc4adb4bad28d"
NESTED_LIBRARY = "0db3e36c7f9b27402f1843f6edb8d14fe25d26d6a9c503df4a95ca1f73876779"


@contextmanager
def configured():
    with patch.multiple(base, IDENT=IDENT, REPORT=REPORT, METHOD=METHOD, MODULE=MODULE):
        yield


def prospective(case, archive, locator):
    actual = dict(
        scheduled=len(locator),
        invalid=len(archive["provenance"]["excluded_windows"]),
        probes=len(archive["source"]["probes"]),
        candidates=sum(len(r["candidates"]) for r in archive["source"]["probes"]),
        empty=sum(not r["candidates"] for r in archive["source"]["probes"]),
    )
    actual["valid"] = actual["scheduled"] - actual["invalid"]
    if (
        actual != EXPECTED
        or case["recording"]["window_count"] != EXPECTED["scheduled"]
        or len(archive["delivery_clocks"]) != EXPECTED["scheduled"]
    ):
        raise ValueError("the completed original waveform, clock or physical roster changed")
    return actual


def bind(work):
    from . import capture_whole_results as positions
    from . import field_exact_waveform_results as previous
    from .fresh_replay_results import sealed
    from .scheduled_capture_waveform import metadata
    from .single_pass_trial import read_gzip

    if (REPORT / "binding-lock.json").exists() or work.exists():
        raise FileExistsError("the prospective DS26 binding is already frozen")
    batch = sealed(PANEL, "qualification-lock.json", PANEL_SHA)
    panel = whole_iq.read(PANEL / "input-lock.json")
    hold = sealed(HOLDOUT, "prediction-lock.json")
    peer = sealed(PEER, "qualification-lock.json")
    earlier = sealed(base.exact.REPORT, "qualification-lock.json")
    old_file = base.exact.REPORT / "source-lock.json"
    old = whole_iq.read(old_file)
    seeds = old["cases"][IDENT]
    h = whole_iq.read(HOLDOUT / "source-lock.json")
    evidence = whole_iq.read(HOLDOUT / "receipts/smoke.json")
    experiments = read_gzip(PEER / f"{IDENT}.json.gz")
    case, request = whole_iq.binding(IDENT)
    capture = base.capture_release.read_capture(case)
    root = str(base.capture_release.producer(case, capture).root)
    original = seeds["root"]
    shared = panel["cases"]["DS26-0237"]
    if (
        h["id"] != IDENT
        or h["recording"] != case["recording"]
        or h["original"]["native"] != case["native"]
        or root != h["producer"]
        or root != shared["root"]
        or root != original["producer"]
        or capture["edge"] != "upper"
        or original["edge"] != capture["edge"]
        or original["input_manifest_sha256"] != capture["input_manifest_sha256"]
        or original["archived_native_sha256"] != case["native"]["sha256"]
        or h["python_sha256"] != panel["python_sha256"]
        or seeds["python_sha256"] != panel["python_sha256"]
        or any(panel["libs"][k] != lib for k, lib in h["libraries"].items())
    ):
        raise ValueError("upper original and authenticated batched runtime disagree")
    if not all((batch["files"], hold["files"], peer["files"], earlier["files"])):
        raise ValueError("empty prior qualification")
    if evidence["source_lock_sha256"] != _sha(HOLDOUT / "source-lock.json"):
        raise ValueError("the preceding complete-primary witness is unauthenticated")
    native = case["native"]
    archive = whole_iq.read(whole_iq.checked(base.BULK / native["path"], native["sha256"]))
    locator, chunks = metadata(case)
    counts = prospective(case, archive, locator)
    invalid = {row["visit"] for row in archive["provenance"]["excluded_windows"]}
    known = [
        (r["visit"], r["iq_sha256"])
        for r in evidence["rows"]
        if len(r["conditional"]["attempts"]) == 3
    ]
    positive_retry = {}
    for r in experiments["rows"]:
        attempts = r["methods"]["conditional"]["attempts"]
        if len(attempts) == 3 and attempts[2]["gate"]:
            positive_retry.setdefault(attempts[2]["receiver"], (r["visit"], r["iq_sha256"]))
    if len(known) < 2 or set(positive_retry) != {0, 1}:
        raise ValueError("both physical peer rescue directions require prior genuine IQ witnesses")
    held = dict(known[:2] + list(positive_retry.values()))
    old_visits = set(original["visits"]) | {r["visit"] for r in experiments["rows"]}
    unseen = sorted(
        set(range(len(locator))) - invalid - old_visits - held.keys(),
        key=lambda v: base.recording.digest([IDENT, "coarse-waveform-first-visit-v1", v]),
    )[:3]
    smoke = []
    for visit in sorted([*held, *unseen, min(invalid)]):
        segment, _, _, offset = next(c for c in chunks if c[3] + c[1] <= visit < c[3] + c[2])
        smoke.append((segment, visit - offset, visit))
    sources = original["sources"] | h["sources"] | h["evidence_sources"] | panel["sources"]
    for path in (
        Path(__file__),
        Path(base.__file__),
        Path(prepared.__file__),
        Path(incumbent.__file__),
        Path(selector_waveform.__file__),
        REPORT / "PROTOCOL.md",
        HOLDOUT / "prediction-lock.json",
        HOLDOUT / "source-lock.json",
        HOLDOUT / "receipts/smoke.json",
        PEER / "qualification-lock.json",
        PEER / f"{IDENT}.json.gz",
        PANEL / "qualification-lock.json",
        PANEL / "input-lock.json",
        PANEL / "summary.json",
        base.exact.REPORT / "qualification-lock.json",
        old_file,
    ):
        sources[str(path)] = _sha(path)
    for path, digest in sources.items():
        whole_iq.checked(Path(path), digest)
    if whole_iq.receiver_identity(Path(h["receiver"])) != h["receiver_files"]:
        raise ValueError("standalone compact receiver closure differs from its signed request")
    capture.update(case={key: case[key] for key in ("id", "run_id", "session_id")})
    original_binding = dict(
        native=native,
        request=case["request"],
        catalog=case["catalog"],
        tile=case["regions"][0],
        causal_snapshots=request["causal_snapshots"],
    )
    wide = SCREENING / "latency-and-support/complete-roster"
    wide_receipt = sealed(wide, "all-figure-lock.json")
    wide_rows = [
        row
        for row in positions.rows_from(wide / "all-positions.jsonl.gz")
        if row["id"] == IDENT and row["method"] in (positions.FOUR, positions.FIVE)
    ]
    keys = (
        native["sha256"],
        case["request"]["sha256"],
        case["catalog"]["sha256"],
        case["regions"][0],
    )
    if len(wide_rows) != 2 or any(
        tuple(row[k] for k in positions.MINIMAL) != keys for row in wide_rows
    ):
        raise ValueError("earlier complete fast positions differ in their physical request")
    with patch.object(previous, "trial", SimpleNamespace(REPORT=REPORT, IDENT=IDENT)):
        wide_resources = previous.historical_wide_resources(
            {"original": original_binding}, wide_rows
        )
    historic = {
        str(wide / "all-positions.jsonl.gz"): wide_receipt["files"]["all-positions.jsonl.gz"],
        str(wide / "all-figure-lock.json"): _sha(wide / "all-figure-lock.json"),
        **wide_resources["files"],
    }
    sources.update(historic)
    private = {path: sha for path, sha in sources.items() if not Path(path).stat().st_mode & 0o004}
    lock = dict(
        id=IDENT,
        capture=capture,
        recording=case["recording"],
        original=original_binding,
        producer=root,
        python=h["python"],
        python_sha256=panel["python_sha256"],
        receiver=h["receiver"],
        receiver_files=h["receiver_files"],
        memory_max=whole_iq.MEMORY,
        sources={path: sha for path, sha in sources.items() if path not in private},
        evidence_sources=private,
        libraries=panel["libs"],
        raw_limit_s=720,
        position_limit_s=180,
        chronology=dict(chunks=chunks, invalid=sorted(invalid)),
        archival_counts=counts,
        smoke=smoke,
        smoke_invalid=[min(invalid)],
        held_sha256={str(visit): sha for visit, sha in held.items()},
        unseen=unseen,
        archival_launch_probes={
            str(v): p
            for v, p in visit_pairs(archive["source"]["probes"])
            if any(v == s[2] for s in smoke)
        },
        original_retry_opportunities=1319,
        cpu_rosters=CPU_ROSTERS,
        peer_success_visits=positive_retry,
        deadline_utc=DECISION_UTC,
        batch_qualification_sha256=PANEL_SHA,
        historical=historic,
    )
    work.mkdir(mode=0o755)
    for out in (REPORT / "binding-lock.json", work / "binding-lock.json"):
        save_json(out, lock)
        out.chmod(0o644)
    print(f"{IDENT} · {len(chunks)} authenticated chunks · {counts}", flush=True)
    print("Launch visit witnesses", smoke, "successful retries", positive_retry, flush=True)


def select(work, cpus, fft_library=None, nested_library=None, evidence=None, digest=None):
    from .fresh_replay_results import sealed

    name = "binding-lock.json"
    lock = whole_iq.read(whole_iq.checked(work / name, _sha(REPORT / name)))
    if (REPORT / "source-lock.json").exists():
        raise FileExistsError("one full waveform configuration is already selected")
    if tuple(cpus) not in CPU_ROSTERS:
        raise ValueError("choose a prospectively allowed CPU roster after release")
    libraries = lock["libraries"]
    incumbent_prepared = libraries["prepared"]
    if fft_library is not None and nested_library is not None:
        raise ValueError("one full recording may exercise only one changed detector path")
    library = nested_library or fft_library
    if any(option is not None for option in (library, evidence, digest)):
        if not all((library, evidence, digest)):
            raise ValueError("the selected path requires its library and verified held seal")
        receipt = sealed(evidence.parent, evidence.name, digest)
        library_sha = _sha(library)
        paths = [evidence.parent / path for path in receipt["files"] if path.endswith(".json")]
        if library_sha not in receipt["files"].values() and not any(
            library_sha in path.read_text() for path in paths
        ):
            raise ValueError("the selected drop-in library is outside the sealed held scope")
        lock["evidence_sources"][str(evidence)] = digest
        entry = dict(path=str(library), sha256=library_sha)
        if nested_library:
            nested_source = str(Path(nested_anchors.__file__))
            whole_iq.checked(Path(nested_source), NESTED_SOURCE)
            whole_iq.checked(nested_library, NESTED_LIBRARY)
            lock["sources"][nested_source] = NESTED_SOURCE
            libraries["nested"] = entry
            selection = dict(
                name="nested-12-add10",
                eligibility="changed-measurement",
                evidence_sha256=digest,
                library_sha256=library_sha,
                primary=list(nested_anchors.PRIMARY),
                additional=list(nested_anchors.ADDITION),
            )
        else:
            libraries["prepared"] = entry
            selection = dict(
                name="qualified-overlap-save-length",
                eligibility="exact-held",
                evidence_sha256=digest,
                library_sha256=library_sha,
            )
    else:
        selection = dict(
            name="incumbent-batched",
            eligibility="exact-held",
            evidence_sha256=PANEL_SHA,
            library_sha256=incumbent_prepared["sha256"],
        )
    lock["evidence_sources"][str(REPORT / name)] = _sha(REPORT / name)
    chronology = lock.pop("chronology")
    capacity = {cpu: 1.0 if cpu <= 7 else 0.68 for cpu in cpus}
    with patch.multiple(incumbent, CPUS=tuple(cpus), CAPACITY=capacity):
        workers = incumbent.partition(chronology["chunks"], set(chronology["invalid"]))
    lock.update(
        capacity=capacity,
        workers=workers,
        incumbent_prepared=incumbent_prepared,
        selection=selection,
    )
    for out in (REPORT / "source-lock.json", work / "source-lock.json"):
        save_json(out, lock)
        out.chmod(0o644)
    incumbent.previous.check_evidence(work)
    print(selection, [(cpu, n) for cpu, n, _ in workers], flush=True)


def compare_launch(work):
    lock, libs = base.configure(work)
    if lock["selection"]["name"] == "incumbent-batched":
        incumbent.smoke(work)
        return
    if lock["selection"]["name"] == "nested-12-add10":
        nested_launch(work, lock, libs)
        return
    policy = base.policy_for(lock)
    new_grid = PersistentGrid(libs["prepared"])
    old_grid = PersistentGrid(
        whole_iq.checked(
            Path(lock["incumbent_prepared"]["path"]), lock["incumbent_prepared"]["sha256"]
        )
    )
    rows = []
    try:
        fine = incumbent.batched_for(lock, libs["batch"])
        for segment, index, visit in lock["smoke"]:
            (window,) = base.open_span(lock, segment, index, index + 1).windows()
            if window.acquisition["global_visit"] != visit or window.iq_sha256 != lock[
                "held_sha256"
            ].get(str(visit), window.iq_sha256):
                raise ValueError("preflight opened the wrong authenticated physical visit")
            witness = SimpleNamespace(**vars(window), receiver_ids=(0, 1))
            stock = base.exact.trial(witness, policy, "installed", libs)
            results = {"installed": stock}
            with base.exact.refiners(libs), selector_waveform.selector(lock), fine.route():
                for name, grid in (("incumbent", old_grid), ("selected", new_grid)):
                    results[name] = base.exact.stages.detector(witness, policy, grid)
                    grid.calls.clear()
            if (
                fine.fallbacks
                or encoded(stock["probes"])
                != encoded(lock["archival_launch_probes"].get(str(visit), []))
                or any(
                    encoded(row[k]) != encoded(stock[k])
                    for row in results.values()
                    for k in ("status", "public", "probes", "attempts")
                )
            ):
                raise ValueError(
                    f"the selected coarse path changes genuine public fields at {visit}"
                )
            rows.append(
                dict(
                    visit=visit,
                    iq_sha256=window.iq_sha256,
                    status=stock["status"],
                    cpu_ns={k: r["cpu_ns"] for k, r in results.items()},
                    wall_ns={k: r["wall_ns"] for k, r in results.items()},
                    **{
                        f"{k}_sha256": base.recording.digest(stock[k])
                        for k in ("public", "probes", "attempts")
                    },
                )
            )
    finally:
        old_grid.clear_cache()
        new_grid.clear_cache()
    print(
        encoded(dict(source_lock_sha256=_sha(work / "source-lock.json"), rows=rows)).decode(),
        flush=True,
    )


def nested_launch(work, lock, libs):
    from leo.scanner import fast_scan_detector

    policy = base.policy_for(lock)
    old_grid = PersistentGrid(libs["prepared"])
    nested = nested_anchors.NestedGrid(libs["nested"])
    fine = incumbent.batched_for(lock, libs["batch"])
    rows = []
    try:
        for segment, index, visit in lock["smoke"]:
            (window,) = base.open_span(lock, segment, index, index + 1).windows()
            if window.acquisition["global_visit"] != visit or window.iq_sha256 != lock[
                "held_sha256"
            ].get(str(visit), window.iq_sha256):
                raise ValueError("nested preflight opened a different physical visit")
            witness = SimpleNamespace(**vars(window), receiver_ids=(0, 1))
            result = {"installed": base.exact.trial(witness, policy, "installed", libs)}
            attempts, reused = {}, 0
            with base.exact.refiners(libs), selector_waveform.selector(lock), fine.route():
                result["incumbent"] = base.exact.stages.detector(witness, policy, old_grid)
                old_grid.calls.clear()
                for mode in ("recompute", "reuse"):
                    with nested.window(fast_scan_detector, mode) as entered:
                        result[mode] = base.exact.stages.detector(witness, policy, nested)
                    attempts[mode] = entered
                    if mode == "reuse":
                        reused = nested.reuses
                    nested.calls.clear()
            stock = result["installed"]
            keys = ("status", "public", "probes", "attempts")
            if (
                fine.fallbacks
                or encoded(stock["probes"])
                != encoded(lock["archival_launch_probes"].get(str(visit), []))
                or any(encoded(stock[k]) != encoded(result["incumbent"][k]) for k in keys)
                or any(encoded(result["recompute"][k]) != encoded(result["reuse"][k]) for k in keys)
                or attempts["recompute"] != attempts["reuse"]
            ):
                raise ValueError(
                    f"old stock or nested sharing differs from its own control: {visit}"
                )
            matches = [
                compare_probes(a, b, window.sample_rate_hz)
                for a, b in zip(stock["probes"], result["reuse"]["probes"], strict=True)
            ]
            for rx, (peer_visit, _) in lock["peer_success_visits"].items():
                if peer_visit == visit and not matches[int(rx)]["positive_matches"]:
                    raise ValueError(f"genuine original successful peer target lost at {visit}")
            rows.append(
                dict(
                    visit=visit,
                    status=stock["status"],
                    iq_sha256=window.iq_sha256,
                    cpu_ns={k: r["cpu_ns"] for k, r in result.items()},
                    wall_ns={k: r["wall_ns"] for k, r in result.items()},
                    attempts=attempts["reuse"],
                    shared_retry_grids=reused,
                    original_matches=matches,
                    original_public_exact=encoded(stock["public"])
                    == encoded(result["reuse"]["public"]),
                    original_factors_exact=encoded(stock["probes"])
                    == encoded(result["reuse"]["probes"]),
                    **{
                        k + "_sha256": {
                            mode: base.recording.digest(r[k]) for mode, r in result.items()
                        }
                        for k in ("public", "probes", "attempts")
                    },
                )
            )
    finally:
        old_grid.clear_cache()
        nested.clear_cache()
    if not any(row["shared_retry_grids"] for row in rows):
        raise ValueError("genuine nested launch did not exercise its measured retry sharing")
    print(
        encoded(dict(source_lock_sha256=_sha(work / "source-lock.json"), rows=rows)).decode(),
        flush=True,
    )


def raw(work, cpu):
    lock, libs = base.configure(work)
    if lock["selection"]["name"] != "nested-12-add10":
        incumbent.raw(work, cpu)
        return
    from leo.scanner import fast_scan_detector

    nested = nested_anchors.NestedGrid(libs["nested"])
    fine = incumbent.batched_for(lock, libs["batch"])
    original_scan = base.scan_capture_window
    attempts = []

    def scan(*args, **kwargs):
        with nested.window(fast_scan_detector, "reuse") as entered:
            result = original_scan(*args, **kwargs)
        attempts[:] = entered
        return result

    class Records(incumbent.previous.VisitRecords):
        def clear(self):
            row = dict(
                ordinal=self.ordinal,
                attempts=attempts,
                reuses=nested.reuses,
                partial_bytes=nested.peak_partial_bytes,
                merge_cpu_ns=sum(r.get("combine_cpu_ns", 0) for r in self),
            )
            print(NESTED_TRACE + encoded(row).decode(), file=sys.stderr, flush=True)
            super().clear()

    with (
        selector_waveform.selector(lock),
        fine.route(),
        patch.object(base, "scan_capture_window", scan),
        patch.object(prepared, "PersistentGrid", lambda _: nested),
        patch.object(prepared, "VisitGridRecords", lambda: Records(fine)),
    ):
        prepared.raw(work, cpu)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("bind", "select", "preflight", "smoke", "raw", "run"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    parser.add_argument("cpu", type=int, nargs="?", default=6)
    parser.add_argument("--cpus", nargs="+", type=int, default=MINIMUM_CPUS)
    parser.add_argument("--fft-library", type=Path)
    parser.add_argument("--nested-library", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--evidence-sha256")
    args = parser.parse_args()
    with configured():
        if args.action == "bind":
            bind(args.work)
        elif args.action == "select":
            select(
                args.work,
                args.cpus,
                args.fft_library,
                args.nested_library,
                args.evidence,
                args.evidence_sha256,
            )
        elif args.action == "preflight":
            incumbent.previous.check_evidence(args.work)
            cmd = base.service(
                f"leo-coarse-preflight-{uuid4().hex[:8]}",
                100,
                base.command(args.work, args.cpu, "smoke"),
            )
            output = subprocess.run(cmd, stdout=subprocess.PIPE, check=True, timeout=110)
            receipt = json.loads(output.stdout)
            save_json(args.work / "smoke.json", receipt)
            for row in receipt["rows"]:
                print(row["visit"], row["status"], row["cpu_ns"], flush=True)
        elif args.action == "smoke":
            compare_launch(args.work)
        elif args.action == "raw":
            raw(args.work, args.cpu)
        else:
            incumbent.run(args.work)


if __name__ == "__main__":
    main()
