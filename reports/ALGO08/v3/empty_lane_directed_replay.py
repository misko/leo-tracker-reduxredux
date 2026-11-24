"""Check frozen DS30-0049 empty-lane Graph hypotheses against original 20 ms I/Q."""

import argparse
from collections import Counter, defaultdict
import ctypes
import fcntl
from hashlib import sha256
import json
from math import isfinite, remainder
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from . import empty_lane_arrival as arrival  # noqa: E402
from . import prefetch_prefix_0049 as prefix  # noqa: E402
from .directed_donor import NATIVE_WINDOW_PERIOD, PERIOD, arrival_phase  # noqa: E402


CASE = "DS30-0049"
FIELD_SNAPSHOT = Path("/srv/postgres-nvme/leo-ds30-research-worktrees/field-first30-ZvFir1")
GRAPH = Path("/tmp/leo-empty-graph-rescue-development-plan.json.gz")
GRAPH_PIN = "adcde673c80fd9a58a81380b90795b6e844f6f9ad236c945e83d4bdbc07354d3"
ARRIVAL_PIN = "9971473052ea2c2d9b2f8db1a82e45f82fcd19f5c165af30dc6c351f361829f9"
RELEASE = arrival.signed.RELEASE
LIBRARY = Path("/var/tmp/leo-v3-directed-pass2/use.so")
LIBRARY_PIN = "d66ab774f8844fbaec21e28eb2c6ecf42e57152705ea5d4677ca8f032d52397d"
ASSET = RELEASE / "assets/lower.f32"
ASSET_PIN = "1b98937cbd87fd5f27b82e4d535512ca5ee12b33a64a6bae90e07ec041368adb"
LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
MODE = "decode"
ABSTAIN_EXIT = 75


def tag(path):
    return sha256(path.read_bytes()).hexdigest()


def phase_epoch(counter, phase):
    if type(counter) is not int or counter < 0 or not isfinite(phase) or not 0 <= phase < PERIOD:
        raise ValueError("Expected an exact hardware counter and wrapped physical phase")
    return ((phase - (3 * counter % 40_000) / 3) % PERIOD) % NATIVE_WINDOW_PERIOD


def project(candidate, predictions):
    visits, proposed = {}, []
    for oid, lane in candidate.items():
        row = lane["row"]
        visit = row["visit_index"]
        if not 0 <= visit < prefix.WINDOWS:
            continue
        if (row["probe_start_ms"] != 0 or row["probe_index"] != 0
                or row["payload_start_sample"] != 200_000 * visit or lane["radio"] != row["receiver_id"]):
            raise ValueError("Native factors do not refer to the original window start")
        binding = [lane["counter"], row["edge"], row["channel"], row["actual_rf_hz"]]
        prior = visits.setdefault(str(visit), binding)
        if binding != prior or row["edge"] != "lower":
            raise ValueError("Expected a single signed lower-edge stereo identity per visit")
        if oid in predictions:
            if not lane["short"] or lane["factor"] is not None:
                raise ValueError("Only candidate-empty short lanes are eligible")
            (hz,) = predictions[oid]["centers_hz"]
            phases = predictions[oid]["phase"]
            if not isfinite(hz) or set(phases) != set(arrival.PHASES):
                raise ValueError("Incomplete signed proposal")
            epochs = {method: phase_epoch(lane["counter"], phases[method]) for method in arrival.PHASES}
            proposed.append(dict(id=oid, visit=visit, radio=lane["radio"], hz=hz, phases=phases, epochs=epochs))
    return visits, sorted(proposed, key=lambda r: (int(visits[str(r["visit"])][0]), r["radio"]))


def local_custody():
    staged = prefix.read(prefix.STAGE / "result.json", prefix.STAGE_PIN)
    factorial = prefix.read(prefix.FACTORIAL / "seal.json", prefix.FACTORIAL_PIN)
    admitted = prefix.read(prefix.FACTORIAL / "admission.json", factorial["admission.json"])
    acquisition = prefix.read(prefix.FACTORIAL / "acquisition.json", factorial["acquisition.json"])
    original = prefix.read(prefix.OFFICIAL / "pair.json", prefix.PAIR_PIN)
    authority = prefix.read(prefix.OFFICIAL / "authority.json", original["authority_sha256"])
    root = Path(staged["stage"])
    if (root.parent != prefix.STAGE or root.name != Path(authority["recording"]).name
            or admitted["custody"] != prefix.STAGE_PIN or admitted["manifest"] != prefix.MANIFEST_PIN
            or admitted["public_pair"] != prefix.PAIR_PIN or not original["verified_pair"]):
        raise ValueError("Private stage is detached from the original authority")
    source = root / (root.name + "-segment-00000000")
    paths = [source / "manifest.json"]
    manifest = prefix.read(paths[0], prefix.MANIFEST_PIN)
    members = manifest["chunks"][:prefix.COUNT]
    if members != admitted["members"] or len(members) != prefix.COUNT:
        raise ValueError("Private stage does not reproduce the six signed member commitments")
    verified = {row["relative"]: (row["length"], row["sha256"]) for row in staged["verified_files"]}
    for number, row in enumerate(members):
        if [row[k] for k in ("chunk_index", "first_sequence", "window_count")] != [number, number * 64, 64]:
            raise ValueError("Only the complete first six original members are enrolled")
        for extent, key in (("index", "index_relative_path"), ("compressed", "payload_relative_path")):
            path = source / row[key]
            expected = row[f"{extent}_bytes"], row[f"{extent}_sha256"]
            if (path.parent != source or verified.get(str(path.relative_to(prefix.STAGE))) != expected
                    or path.stat().st_size != expected[0]):
                raise ValueError("Private member size or prior signed custody changed")
            paths.append(path)
    if len(acquisition["window_hashes"]) != prefix.WINDOWS or any(
        path.resolve(strict=True) != path or not path.is_file() for path in paths
    ):
        raise ValueError("Private inputs must be regular files at the exact original local stage paths")
    return dict(recording=str(source), files=list(map(str, paths)), authority=authority,
                compressed_bytes=sum(row["compressed_bytes"] for row in members),
                window_hashes=acquisition["window_hashes"])


def candidate_inputs():
    rows = arrival.original_pairs(FIELD_SNAPSHOT, "development")
    result, native, candidate, _ = arrival.candidate_packet(rows[CASE, "successor"])
    return result, native, candidate


def freeze():
    source = local_custody()
    result, _, candidate = candidate_inputs()
    graph = arrival.signed.document(GRAPH, GRAPH_PIN)["cases"][CASE]
    seal = arrival.signed.document(HERE / "measurements/empty-lane-arrival-seal.json", ARRIVAL_PIN)
    empty, predictions, proof = arrival.prepare(graph, candidate)
    proof.update(empty_short=len(empty), candidate_sha256=result["native_sha256"])
    if (proof != seal["cases"][CASE] or seal["prediction_inputs"]["development"] != GRAPH_PIN
            or result["native_sha256"] != graph["candidate_native_sha256"]
            or result["raw_identity"] != source["authority"]):
        raise ValueError("Frozen Graph projections, candidate input or original raw authority changed")
    visits, proposed = project(candidate, predictions)
    grouped = Counter(row["visit"] // 64 for row in proposed)
    if len(visits) != 362 or dict(sorted(grouped.items())) != dict(enumerate((7, 17, 26, 18, 23, 26))):
        raise ValueError("The predeclared physical visit or query count changed")
    if (tag(LIBRARY), tag(ASSET)) != (LIBRARY_PIN, ASSET_PIN):
        raise ValueError("Unexpected existing full-aperture directed verifier or pilot asset")
    return dict(case=CASE, original_source=source, admitted_visits=visits, total_issued_visits=prefix.WINDOWS,
                prefix_empty_short=sum(candidate[oid]["row"]["visit_index"] < prefix.WINDOWS for oid in empty),
                queries=proposed, queries_by_member=dict(sorted(grouped.items())), arrival_proof=proof,
                graph_sha256=GRAPH_PIN, source_sha256=tag(Path(__file__)), directed_library_sha256=LIBRARY_PIN,
                asset_sha256=ASSET_PIN, mode=MODE, phase_order=list(arrival.PHASES))


def forbid_source(event, params, *, allowed=(), prediction=True):
    if event != "open" or not isinstance(params[0], (str, bytes, os.PathLike)):
        return
    path = Path(os.path.abspath(os.fsdecode(params[0])))
    if str(path) in allowed:
        if prediction and isinstance(params[2], int) and params[2] & (os.O_WRONLY | os.O_RDWR):
            raise ValueError("The private waveform source is read-only")
        return
    if path.is_relative_to(prefix.STAGE) and path.name not in ("result.json", "manifest.json"):
        raise ValueError(f"The private source extent was not enrolled: {path}")
    arrival.saved_only(event, params, prediction=prediction)


def signed_visit(window, binding):
    acq, target = window.acquisition, window.target
    actual_rf = acq["actual_if_center_hz"] + target["lnb_lo_hz"]
    if ([acq["sample_start"], target["edge"], target["channel"], actual_rf] != binding
            or acq["global_visit"] != window.sequence or window.sample_rate_hz != 10_000_000
            or window.samples.shape != (200_000, 2, 2) or not window.samples.flags.c_contiguous
            or window.samples.dtype.str != "<i2"):
        raise ValueError("Decoded I/Q has different original visit, RF or full stereo geometry")
    return target["rf_center_hz"] - actual_rf


def report_pulse(samples, center, row, verifier, seed):
    out = {}
    for method in arrival.PHASES:
        factor, cpu, wall, work = verifier.timed(samples, row["radio"], center,
                                                [seed(row["epochs"][method], row["hz"])], MODE)
        if len(factor) > 1 or work.cancellations or work.refine_ns or work.gates != 1:
            raise ValueError("Directed request performed work outside the one supplied signed seed")
        out[method] = dict(factor=list(factor[0]) if factor else None, cpu_ns=cpu, wall_ns=wall,
                           stages={name: getattr(work, name) for name, _ in work._fields_})
    return out


def take(plan):
    import numpy as np
    from leo.storage.fast_scan import FastSegmentSource
    from .directed_verifier_trial import Directed, seed

    before = getrusage(RUSAGE_SELF)
    started, cpu_start = perf_counter_ns(), process_time_ns()
    if tag(LIBRARY) != plan["directed_library_sha256"] or tag(ASSET) != plan["asset_sha256"]:
        raise ValueError("The native library or independent gate asset differs from the freeze")
    source = FastSegmentSource(dict(path=plan["original_source"]["recording"], manifest_digest=prefix.MANIFEST_PIN),
                               stop_sequence=prefix.WINDOWS)
    if tuple(source.receiver_ids) != (0, 1):
        raise ValueError("Physical antenna IDs differ from the frozen lanes")
    pulse = Directed(SimpleNamespace(lib=ctypes.CDLL(str(LIBRARY))), np.fromfile(ASSET, dtype="<f4"))
    setup_cpu = process_time_ns() - cpu_start
    expected = plan["admitted_visits"]
    groups, results, windows = defaultdict(list), [], []
    for row in plan["queries"]:
        groups[row["visit"]].append(row)
    try:
        for window, digest in zip(source.windows(), plan["original_source"]["window_hashes"], strict=True):
            if window.sequence != len(windows) or window.iq_sha256 != digest:
                raise ValueError("The private prefix no longer follows the original signed window bytes or order")
            windows.append(window.iq_sha256)
            admitted = expected.get(str(window.sequence))
            center = signed_visit(window, admitted) if admitted is not None else None
            for row in groups.pop(window.sequence, []):
                if center is None or abs(row["hz"] - center) > 800_000:
                    raise ValueError("Supplied signed CFO is outside the actual lane receiver band")
                results.append(dict(id=row["id"], paths=report_pulse(window.samples, center, row, pulse, seed)))
    finally:
        pulse.close()
    if len(windows) != prefix.WINDOWS or groups or [r["id"] for r in results] != [r["id"] for r in plan["queries"]]:
        raise ValueError("The complete six-member signed sweep failed")
    after = getrusage(RUSAGE_SELF)
    return dict(rows=results, verified_windows=len(windows), ordered_iq_sha256=arrival.signed.canonical(windows),
                setup_cpu_ns=setup_cpu, authenticated_sweep_cpu_ns=process_time_ns() - cpu_start,
                authenticated_sweep_wall_ns=perf_counter_ns() - started,
                input_blocks=after.ru_inblock - before.ru_inblock, peak_rss_kib=after.ru_maxrss)


def guarded(plan):
    from ds30_paired_evaluation import quiet_window, storage_sample
    from visit_frame_raw_0016 import resident

    if os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise ValueError("Use the isolated low-priority CPU2 launch in the frozen protocol")
    pathset = plan["original_source"]["files"]
    with LOCK.open("r") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return dict(admitted=False, reason="shared-lease-in-use")
        event, deferred = prefix.occupied()
        if not deferred:
            return dict(admitted=False, reason="no-fresh-field-deferral", field_event=event)
        quiet, storage = quiet_window()
        before = resident(pathset)
        event, deferred = prefix.occupied()
        if not deferred or not quiet:
            return dict(admitted=False, reason="no-fresh-quiet-field-deferral", field_event=event,
                        storage_before=storage, before=before)
        sweep = take(plan)
        after = resident(pathset)
        if sweep["input_blocks"]:
            raise ValueError("A pass incurred physical input despite fully resident admission")
        return dict(admitted=True, field_event=event, storage_before=storage,
                    storage_after=storage_sample(), before=before, after=after, **sweep)


def matches(counter, got, reference):
    rank, integer, offset, hz, exact, control = got
    if rank != 0 or not all(map(isfinite, (integer, offset, hz, exact, control))) or exact <= control:
        raise ValueError("Unexpected accepted verifier factor")
    local = dict(integer_epoch_sample=integer, fractional_epoch_offset_samples=offset)
    return (abs(hz - reference[arrival.HERTZ]) <= 250
            and abs(remainder(arrival_phase(counter, local) - arrival_phase(counter, reference), PERIOD)) <= 2)


def comparison(plan):
    result, native, candidate = candidate_inputs()
    control = arrival.original_pairs(FIELD_SNAPSHOT, "development")[CASE, "installed"]
    old = arrival.signed_attempt(arrival.FIELD, control)
    stock = arrival.signed.read_native((arrival.FIELD / control["attempt"]).parent / "publication", old["native_sha256"])
    if old["raw_identity"] != result["raw_identity"] or stock["provenance"]["detector_sha256"] != "sha256:" + arrival.signed.FULL:
        raise ValueError("Installed full receiver belongs to a different original source")
    installed = arrival.signed.opportunities(stock)
    arrival.signed.bind_pair(stock, native, installed, candidate)
    owners = arrival.signed.owners(arrival.named_rows(CASE, old), old["evidence"]["owners"])
    prefix_missing = {oid for oid, lane in candidate.items() if lane["row"]["visit_index"] < prefix.WINDOWS
                      and lane["short"] and lane["factor"] is None and installed[oid]["factor"] is not None}
    proposals = {row["id"]: dict(centers_hz=[row["hz"]], phase=row["phases"]) for row in plan["queries"]}
    summary = dict(installed_sha256=old["native_sha256"], prefix_missing=len(prefix_missing),
                   prefix_owned_missing={arm: len(prefix_missing & rows.keys()) for arm, rows in owners.items()},
                   proposal_only=arrival.score_group(prefix_missing, proposals, installed),
                   owner_proposal_only={arm: arrival.score_group(prefix_missing, proposals, installed, set(rows))
                                        for arm, rows in owners.items()})
    return summary, installed, prefix_missing, owners


def score(plan, sweep):
    if not sweep["admitted"] or sweep["verified_windows"] != plan["total_issued_visits"]:
        raise ValueError("Only a complete sealed waveform sweep may be scored")
    if [r["id"] for r in sweep["rows"]] != [r["id"] for r in plan["queries"]]:
        raise ValueError("Waveform receipt does not match frozen query chronology")
    summary, installed, prefix_missing, owners = comparison(plan)
    measured = {}
    for phase in arrival.PHASES:
        counts, clock, assigned = Counter(), Counter(), Counter()
        for outcome in sweep["rows"]:
            oid = outcome["id"]
            item = outcome["paths"][phase]
            has_reference = oid in prefix_missing
            factor = installed[oid]["factor"]
            counts["queries"] += 1
            counts["installed_positive_queries"] += has_reference
            counts["accepted"] += item["factor"] is not None
            for key in ("cpu_ns", "wall_ns"):
                clock[key] += item[key]
            clock.update(item["stages"])
            if item["factor"] is not None:
                match = has_reference and matches(installed[oid]["counter"], item["factor"], factor)
                counts["signed_matches"] += match
                counts["matched_no_installed_factor"] += not has_reference
                counts["accepted_wrong_signed_factor"] += has_reference and not match
                for arm, owned in owners.items():
                    assigned[arm] += bool(match and oid in owned)
        measured[phase] = dict(counts, clocks=dict(clock), installed_owned_signed_matches=dict(assigned))
    return dict(**summary, measured=measured)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "score", "compare-proposals"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--plan-sha256")
    parser.add_argument("--waveforms", type=Path)
    parser.add_argument("--waveform-sha256")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output is immutable and must be new")
    if args.action == "freeze":
        sys.addaudithook(forbid_source)
        prefix.write(args.output, freeze())
        return 0
    if args.plan is None or args.plan_sha256 is None:
        parser.error("run and score require the frozen plan and its SHA-256")
    if args.action == "score" and (args.waveforms is None or args.waveform_sha256 is None):
        parser.error("score requires the immutable waveform receipt and its SHA-256")
    plan = prefix.read(args.plan, args.plan_sha256)
    if plan["source_sha256"] != tag(Path(__file__)):
        raise ValueError("Replay source changed after the candidate-only freeze")
    if args.action == "run":
        allowed = frozenset(plan["original_source"]["files"])
        sys.addaudithook(lambda event, params: forbid_source(event, params, allowed=allowed))
        if plan["original_source"] != local_custody():
            raise ValueError("Private signed source differs from candidate-only freeze")
        result = guarded(plan)
    elif args.action == "score":
        sys.addaudithook(lambda event, params: forbid_source(event, params, prediction=False))
        waveforms = prefix.read(args.waveforms, args.waveform_sha256)
        if waveforms["plan_sha256"] != args.plan_sha256:
            raise ValueError("Waveform receipt changed frozen input")
        result = score(plan, waveforms)
        result["waveform_sha256"] = args.waveform_sha256
    else:
        sys.addaudithook(lambda event, params: forbid_source(event, params, prediction=False))
        result, _, _, _ = comparison(plan)
    result["plan_sha256"] = args.plan_sha256
    prefix.write(args.output, result)
    return ABSTAIN_EXIT if result.get("admitted") is False else 0


if __name__ == "__main__":
    sys.exit(main())
