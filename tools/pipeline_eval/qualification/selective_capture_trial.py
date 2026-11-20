"""Seal wide-only decisions, assemble native mixes, and run bounded position fits."""

import argparse
import gzip
import json
import shutil
from hashlib import sha256
from pathlib import Path
from time import process_time_ns

from .. import cavity_runtime
from ..__main__ import encoded, local_output, save_json, write
from ..variants import selective_capture as policy
from . import cavity_payload_transfer as receiver
from .input_factor_bridge import BULK, SCREEN, _load_case, _sha, check, checked_history, read

REPORT = SCREEN / "acquisition-support/selective-capture"
BAND = SCREEN / "detector-origins/whole-band"
DEV = ("DS26-0036", "DS29-0082")
HELD = ("DS26-0237", "DS29-0174")
CASES = (*DEV, *HELD)
LANES = {6: (HELD[0], DEV[0]), 7: (HELD[1], DEV[1])}
METHODS = ("first_128", "first_16", "uniform_128", "uniform_16")
MEMORY = 512 * 1024**2
BOUNDARY = "Stored per-visit wide/capture factor mix through the released compact cavity"


def digest(value):
    return sha256(encoded(value)).hexdigest()


def wide_bytes(case):
    lock = read(BAND / "prediction-lock.json")
    path = BAND / "native" / f"{case}.json.gz"
    check(path, lock["files"][str(path.relative_to(BAND))])
    return gzip.decompress(path.read_bytes())


def freeze(work):
    target = REPORT / "selection-lock.json"
    if target.exists():
        raise ValueError("selection was already frozen")
    work.mkdir(parents=True, exist_ok=True)
    paths = (
        Path(__file__),
        Path(policy.__file__),
        REPORT / "PROTOCOL.md",
        BAND / "prediction-lock.json",
    )
    lock = dict(sources={str(p): _sha(p) for p in paths}, cases={})
    for ident in CASES:
        payload = wide_bytes(ident)
        wide = json.loads(payload)
        start = process_time_ns()
        selected = policy.schedule(wide["source"]["probes"])
        cpu = (process_time_ns() - start) / 1e6
        if selected["admitted"] != wide["provenance"]["processed_windows"]:
            raise ValueError("wide trigger did not see every admitted stereo visit")
        lock["cases"][ident] = dict(
            wide_sha256=sha256(payload).hexdigest(), selection=selected, selector_cpu_ms=cpu
        )
        write(work / f"{ident}-wide.json", payload)
    save_json(target, lock)


def verify_selection(work):
    lock = read(REPORT / "selection-lock.json")
    for path, sha in lock["sources"].items():
        check(Path(path), sha)
    for ident, entry in lock["cases"].items():
        check(work / f"{ident}-wide.json", entry["wide_sha256"])
    return lock


def archive_context(case, work):
    request_path = BULK / case["request"]["path"]
    request_sha256 = check(request_path, case["request"]["sha256"])
    original = read(request_path)
    job = original["job"]
    history = checked_history(job, original["causal_snapshots"], case["cutoff_utc_ns"])
    if (
        history[-1] != dict(utc_ns=case["catalog_timestamp_ns"], sha256=case["catalog"]["sha256"])
        or job["evaluation_reference"] is not None
        or job["identity"]["session_id"] != case["session_id"]
        or job["search_center"] != case["regions"][0]["center"]
    ):
        raise ValueError("frozen current catalogue or public geographic offer changed")
    config = work / "track-config.json"
    content = Path(job["track_config"]["path"]).read_bytes()
    write(config, content)
    check(config, case["track_config"]["sha256"])
    catalogue = work / "tle"
    snapshots = catalogue / "archive/space-track"
    snapshots.mkdir(parents=True, exist_ok=True)
    for src in Path(job["tle_root"]).rglob("*.tle"):
        dest = snapshots / src.name
        shutil.copyfile(src, dest)
        check(dest, original["causal_snapshots"][src.name])
    shared = dict(
        id=case["id"],
        capture_id=case["session_id"],
        catalog_sha256=case["catalog"]["sha256"],
        track_config_sha256=case["track_config"]["sha256"],
        frozen_request_sha256=request_sha256,
        history_sha256=digest(history),
        screen_center=job["screen_center"],
        tile=dict(case["regions"][0], width_km=25),
    )
    return shared, config, catalogue, history


def is_positive(pair):
    return any(c["passed_fractional_margin_gate"] for p in pair for c in p["candidates"])


def make_document(wide, original, role, chosen, wide_sha, capture_sha):
    factors = policy.mix_probes(wide["source"]["probes"], original["source"]["probes"], chosen)
    identity = dict(
        policy=role,
        selected_visits=sorted(chosen),
        wide_native_sha256=wide_sha,
        capture_native_sha256=capture_sha,
    )
    analysis = digest(identity)
    document = dict(
        wide,
        source=dict(wide["source"], probes=factors, analysis_manifest_sha256="sha256:" + analysis),
    )
    document["provenance"] = dict(
        wide["provenance"],
        factor_mix=identity,
        run_id="conditional-replay-" + analysis[:32],
        scope=BOUNDARY,
    )
    document["provenance"].pop("detector_sha256", None)
    pairs_a = dict(policy.visit_pairs(wide["source"]["probes"]))
    pairs_b = dict(policy.visit_pairs(original["source"]["probes"]))
    metrics = dict(
        selected=len(chosen),
        admitted=len(pairs_a),
        fraction=len(chosen) / len(pairs_a),
        changed_complete_visits=sum(pairs_a[v] != pairs_b[v] for v in chosen),
        selected_with_wide_positive=sum(is_positive(pairs_a[v]) for v in chosen),
        selected_with_capture_positive=sum(is_positive(pairs_b[v]) for v in chosen),
        selected_positive_added=sum(
            not is_positive(pairs_a[v]) and is_positive(pairs_b[v]) for v in chosen
        ),
        selected_positive_removed=sum(
            is_positive(pairs_a[v]) and not is_positive(pairs_b[v]) for v in chosen
        ),
    )
    return document, metrics


def prepare(work):
    lock = verify_selection(work)
    bundle = work / "phase-release"
    cavity_runtime.install(bundle, profile="phase-release")
    expected = cavity_runtime.release_files(cavity_runtime.RELEASE, "phase-release")
    if any((bundle / name).read_bytes() != value for name, value in expected.items()):
        raise ValueError("prepared standalone source does not match the measured phase release")
    roles = {}
    for ident in (*HELD, *DEV):
        case = _load_case(ident)
        root = work / ident
        root.mkdir(parents=True, exist_ok=True)
        record = lock["cases"][ident]
        wide = read(work / f"{ident}-wide.json")
        capture_path = BULK / case["native"]["path"]
        capture_payload = capture_path.read_bytes()
        original = json.loads(capture_payload)
        capture_sha = sha256(capture_payload).hexdigest()
        if capture_sha != case["native"]["sha256"]:
            raise ValueError("capture-era archive source differs from original run")
        policy.same_support(wide, original)
        if wide["clock_anchor"]["before"]["realtime_ns"] != case["cutoff_utc_ns"]:
            raise ValueError("parent raw clock does not match frozen cutoff")
        settings, config, archive, history = archive_context(case, root)
        roles[ident] = {}
        for role in METHODS:
            chosen = {r["visit"] for r in record["selection"]["policies"][role]}
            document, metrics = make_document(
                wide, original, role, chosen, record["wide_sha256"], capture_sha
            )
            output = root / f"{role}.native.json"
            write(output, encoded(document))
            row = dict(
                settings,
                method=role,
                native_sha256=_sha(output),
                original_native_sha256=capture_sha,
                wide_native_sha256=record["wide_sha256"],
                cohort="held" if ident in HELD else "development",
                selection=metrics,
            )
            row["input_sha256"] = digest(row)
            roles[ident][role] = dict(
                row=row,
                native=str(output),
                track=str(config),
                archive=str(archive),
                history=history,
            )
    files = sorted(p for p in bundle.rglob("*") if p.is_file())
    plan = dict(
        jobs=roles,
        cpu_lanes=LANES,
        phase_release_files={str(p.relative_to(bundle)): _sha(p) for p in files},
        memory_max=MEMORY,
        swap_max=0,
        timer_seconds=receiver.LIMIT_S,
        selection_sha256=_sha(REPORT / "selection-lock.json"),
    )
    save_json(REPORT / "fit-plan.json", plan)


def run(work, cpu):
    verify_selection(work)
    plan = read(REPORT / "fit-plan.json")
    check(REPORT / "selection-lock.json", plan["selection_sha256"])
    bundle = work / "phase-release"
    for name, sha in plan["phase_release_files"].items():
        check(bundle / name, sha)
    for ident in LANES[cpu]:
        for role in METHODS:
            item = plan["jobs"][ident][role]
            out = work / f"{ident}-{role}-fit.json"
            if out.exists():
                continue
            row = item["row"]
            native = Path(item["native"])
            check(native, row["native_sha256"])
            archive = Path(item["archive"])
            config = Path(item["track"])
            job = (row, native, config, archive, item["history"])
            result = receiver.capped(work / "attempts" / role, work, job, bundle.name, cpu)
            save_json(
                out, dict(result, method=role, fit_cgroup_memory_max=MEMORY, fit_cgroup_swap_max=0)
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "prepare", "run"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--cpu", type=int, choices=LANES)
    args = parser.parse_args()
    if args.stage == "run":
        if args.cpu is None:
            parser.error("--cpu is required when launching a lane")
        run(args.work, args.cpu)
    else:
        (freeze if args.stage == "freeze" else prepare)(args.work)
