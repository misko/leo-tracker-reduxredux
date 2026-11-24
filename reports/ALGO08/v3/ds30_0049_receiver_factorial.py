"""Measure matched native apertures, cancellation, and selector history on one signed prefix."""

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
import gzip
from hashlib import sha256
import json
from math import remainder
from pathlib import Path
import sys
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import empty_bootstrap as boot
from mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath, StereoSchedule, strongest
from original_prefix_scaling import guard


PROTOCOL = HERE / "ds30-0049-receiver-factorial-protocol.md"
CASE = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases/DS30-0049")
STAGE = Path("/tmp/leo-v3-ds30-0049-complete-idle01")
CUSTODY_PIN = "132a92c06c4e126023621027ae6a59ece97612f13715e9c9dc307a46e2ba8ba0"
PAIR_PIN = "7514497ea681194487e8d85aecf2d739e996abf2b90566d446f81fe38875c36b"
CROSSOVER = Path("/tmp/leo-v3-0049-saved-cross-proof02/final-evidence.json")
CROSSOVER_PIN = "c1fd49b28d0a90370ecf056ac7c0bf90b01af094a9377bfff5c38db39da7b7f3"
FULL = boot.PAYLOAD / "receiver.so"
PRIMARY = Path("/var/tmp/leo-algo08v3-primary-schedule-trial-native/primary.so")
PRIMARY_PIN = "5e9667bbe38c1aeb897189c5ebff0a05cd400fd21f41703a279a384c202f3f50"
SHORT = Path("/tmp/leo-v3-short-rank-transfer-DS30-0016-01/sparse/use.so")
SHORT_PIN = "c5b57b0602e81a6a85c14caf648eb12341f098d09915b4d3f705094ed309574c"
MODES = ("20-two", "20-primary", "8-two", "8-primary")
SELECTORS = ("continuation", "strongest")
ARMS = ("c0", "fitted_c")
SANITY, STOP = 64, 384


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, payload):
    path.write_bytes(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n")


def sources():
    return {path.name: digest(path) for path in (Path(__file__), PROTOCOL, HERE / "mixed_aperture_receiver.py",
             HERE / "empty_bootstrap.py", HERE / "anchor_cycle_route.py", HERE / "anchor_holds.py",
             HERE / "anchor_exposure.py", HERE / "original_prefix_scaling.py")}


def controls():
    from leo.contracts.digests import canonical_digest

    pair = json.loads(boot.checked(CASE / "pair.json", PAIR_PIN))
    if not pair["verified_pair"] or not pair["same_lease"] or pair["generation"] != 2:
        raise ValueError("Original clean paired control changed")
    rows = {}
    for mode, pin in pair["attempt_result_sha256"].items():
        path = CASE / mode / "attempt-000002"
        result = json.loads(boot.checked(path / "result.json", pin[7:]))
        native, = (path / "publication/fast-scan-automatic-work").glob("*/detections.json")
        packet = json.loads(boot.checked(native, result["native_sha256"][7:]))
        if canonical_digest(packet) != result["native_sha256"] or result["outcome"] != "complete":
            raise ValueError("Original detector payload differs from its complete sealed publication")
        rows[mode] = (packet, result)
    left, right = (rows[name][1]["raw_identity"] for name in ("installed", "successor"))
    if left != right:
        raise ValueError("Original raw authorities disagree")
    return rows


def input_scope(original):
    custody = json.loads(boot.checked(STAGE / "result.json", CUSTODY_PIN))
    recording = Path(custody["stage"])
    observed = {row["relative"]: (row["length"], row["sha256"]) for row in custody["verified_files"]}
    segment = recording / (recording.name + "-segment-00000000")
    manifest_file = segment / "manifest.json"
    manifest_pin = observed[str(manifest_file.relative_to(STAGE))][1]
    inventory = CASE / "installed/attempt-000002/publication/fast-scan-inputs" / (original["session_id"] + ".json")
    authority = json.loads(boot.checked(inventory, original["input_manifest_sha256"][7:]))
    if (recording.parent != STAGE or segment.resolve(strict=True) != segment
            or authority["segments"][0]["manifest_digest"] != manifest_pin):
        raise ValueError("Local signed custody no longer binds the original first segment")
    manifest = json.loads(boot.checked(manifest_file, manifest_pin[7:]))
    files = [manifest_file]
    members = manifest["chunks"][:6]
    visited = 0
    for ordinal, member in enumerate(members):
        if member["chunk_index"] != ordinal or member["first_sequence"] != visited or member["window_count"] != 64:
            raise ValueError("Expected the exact original contiguous signed members")
        visited += member["window_count"]
        for kind, name in (("index", "index_relative_path"), ("compressed", "payload_relative_path")):
            path = segment / member[name]
            expected = (member[kind + "_bytes"], member[kind + "_sha256"])
            if (path.resolve(strict=True) != path or not path.is_file() or path.stat().st_size != expected[0]
                    or expected != observed.get(str(path.relative_to(STAGE)))):
                raise ValueError("A member or index is not fully present in authenticated local custody")
            files.append(path)
    if visited != STOP:
        raise ValueError("Unexpected six-member frontier")
    return segment, manifest_pin, members, files


def runtime():
    return boot.receiver_symbols({name: boot.checked(boot.PAYLOAD / name, sha) for name, sha in boot.EXTRA_SOURCES.items()})


def engines(stack, edge, symbols):
    import ctypes as ct
    import numpy as np
    from unified_short_bootstrap import receiver_import

    pilot = np.frombuffer(boot.checked(boot.RELEASE / "assets" / (edge + ".f32"), PILOT_SHA[edge]), dtype="<f4")
    callbacks = {}
    for mode in MODES:
        library = FULL if mode.startswith("20") else SHORT
        constructor_mode = "short_primary" if mode == "8-primary" else "full"
        with receiver_import("tools.pipeline_eval.qualification.blind_compact_run", symbols):
            native = NativePath(library, pilot, constructor_mode)
        stack.callback(native.close)
        if mode == "20-primary":
            helper = ct.CDLL(str(PRIMARY)).primary_factors
            helper.argtypes, helper.restype = native.call.argtypes, native.call.restype
            native.call, native.maximum = helper, 1
        callbacks[mode] = native
    return callbacks


def choose(rows, mode, selector, continuation):
    selected = []
    followers = defaultdict(continuation)
    for row in rows:
        alternatives = row["alternatives"]["20-two" if row["anchor"] else mode]
        probe = dict(row["opportunity"], candidates=alternatives)
        if selector == "strongest":
            factor = strongest(alternatives)
        else:
            _, keep, _ = followers[probe["edge"]].select(probe)
            factor = alternatives[keep] if keep is not None else None
        selected.append(dict(probe, candidates=[] if factor is None else [factor]))
    return selected


def diagonal(rows, expected, stop, continuation):
    signs = {name: [row for row in document["source"]["probes"] if row["visit_index"] < stop]
             for name, document in expected.items()}
    replay = {"installed": choose(rows, "20-two", "continuation", continuation),
              "successor": choose(rows, "8-primary", "strongest", continuation)}
    counts = {name: sum(a != b for a, b in zip(replay[name], signs[name], strict=True)) for name in signs}
    if any(counts.values()):
        raise ValueError(f"Exact prefix detector diagonal failed at stop {stop}: {counts}")
    return dict(stop=stop, antenna_slots=len(rows), positive={name: sum(bool(r["candidates"]) for r in data)
                                                             for name, data in replay.items()}, changes=counts)


def measure(root):
    import numpy as np
    symbols = runtime()

    from aperture_trial import machine
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage.fast_scan import FastSegmentSource
    from visit_frame_raw_0016 import resident

    status = machine()
    if status["cpu"] != [2] or status["nice"] < 15 or "prio 7" not in status["ionice"] or set(status["threads"].values()) != {"1"}:
        raise ValueError("Require the low-priority, one-core Gauss slot")
    if root.parent != Path("/dev/shm") or root.exists():
        raise ValueError("Expected a new private tmpfs result directory")
    start = process_time_ns(), perf_counter_ns()
    documents = {key: val[0] for key, val in controls().items()}
    original = documents["installed"]
    segment, pin, members, paths = input_scope(original["source"])
    cache = resident(paths)
    sys.addaudithook(guard(paths))
    short = boot.checked(SHORT, SHORT_PIN)
    if not short or not boot.checked(FULL, INSTALLED_SHA) or not boot.checked(PRIMARY, PRIMARY_PIN):
        raise ValueError("A pinned native path is empty")
    policy = FastScanPolicyV2()
    reader = FastSegmentSource(dict(path=str(segment), manifest_digest=pin), stop_sequence=STOP)
    schedule = StereoSchedule(full_coverage=True)
    invalid = {row["visit"]: row for row in original["provenance"]["excluded_windows"]}
    rows, hashes, excluded, poisoned = [], [], [], []
    root.mkdir(mode=0o700)
    write(root / "admission.json", dict(machine=status, custody=CUSTODY_PIN, public_pair=PAIR_PIN, crossover=CROSSOVER_PIN,
          native={str(FULL): INSTALLED_SHA, str(PRIMARY): PRIMARY_PIN, str(SHORT): SHORT_PIN},
          source_sha256=sources(), manifest=pin, members=members, resident=cache, known_complete_visits=STOP))
    prepared = process_time_ns(), perf_counter_ns()
    with ExitStack() as stack:
        bank = {}
        for window in reader.windows():
            visit, acquisition, target = window.acquisition["global_visit"], window.acquisition, window.target
            retune = json.loads(acquisition["retune_receipt"])
            if (visit != len(hashes) or original["delivery_clocks"][visit] != retune["host_delivery_clock"]
                    or (visit == 0 and retune["utc_clock_bracket"] != original["clock_anchor"])):
                raise ValueError("Local visit order or capture clocks differ from the released packet")
            hashes.append(window.iq_sha256)
            if not valid_window_support(acquisition, window.sample_rate_hz, window.samples.shape, (0, 1), policy):
                saved = invalid[visit]
                if (saved["sample_start"], saved["sample_end"], saved["iq_sha256"]) != (
                        acquisition["sample_start"], acquisition["sample_end"], window.iq_sha256):
                    raise ValueError("An original physical exclusion has changed")
                excluded.append(visit)
            else:
                if visit in invalid or window.samples.shape != (200_000, 2, 2):
                    raise ValueError("Original admitted stereo geometry changed")
                edge = target["edge"]
                if edge not in bank:
                    bank[edge] = engines(stack, edge, symbols)
                slot, aperture = schedule.visit(edge, target, acquisition)
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - acquisition["actual_if_center_hz"]
                raw = SimpleNamespace(acquisition=acquisition, target=target, sample_rate_hz=window.sample_rate_hz)
                for rx in (0, 1):
                    # Rotate every cell through the first position to reduce cache-order bias.
                    rotation = (visit + rx) % len(MODES)
                    order = MODES[rotation:] + MODES[:rotation]
                    called = {mode: bank[edge][mode].run(window.samples, rx, center) for mode in order}
                    alternatives = {mode: [symbols["factor_candidate"](rank, epoch, status="complete", offset=offset,
                        cfo=hz, exact=exact, control=roll, margin=exact-roll) for rank, epoch, offset, hz, exact, roll in found]
                        for mode, (found, _) in called.items()}
                    if any(not factor["passed_fractional_margin_gate"] for factors in alternatives.values() for factor in factors):
                        raise ValueError("A native factor bypassed the reviewed margin gate")
                    for ms in ("20", "8"):
                        if alternatives[ms + "-primary"] != [f for f in alternatives[ms + "-two"] if f["candidate_rank"] == 0]:
                            raise ValueError(f"The {ms} ms primary helper changed genuine rank-zero factors at visit {visit}, rx {rx}")
                    if slot == 0:
                        changed = window.samples.copy()
                        changed[80_000:] = np.iinfo(np.int16).max
                        for mode in ("8-two", "8-primary"):
                            if bank[edge][mode].run(changed, rx, center)[0] != called[mode][0]:
                                raise ValueError(f"The {mode} callback reads samples outside 8 ms")
                            poisoned.append([visit, rx, mode])
                    rows.append(dict(opportunity=symbols["_probe"](raw, rx, []), anchor=aperture == "full",
                                     alternatives=alternatives, clocks={mode: row[1] for mode, row in called.items()}))
            if visit == SANITY - 1:
                write(root / "sanity.json", diagonal(rows, documents, SANITY, symbols["Continuation"]))
    measured = process_time_ns(), perf_counter_ns()
    if len(hashes) != STOP or excluded != sorted(v for v in invalid if v < STOP) or len(rows) + 2 * len(excluded) != 2 * STOP:
        raise ValueError("The final signed prefix visits or exclusions differ")
    write(root / "final-diagonal.json", diagonal(rows, documents, STOP, symbols["Continuation"]))
    write(root / "native-rows.json", rows)
    write(root / "selection.json", selection(rows, original, excluded, symbols["Continuation"]))
    write(root / "acquisition.json", dict(window_hashes=hashes, excluded=excluded, suffix_checks=poisoned,
          combined_loading_and_native_cpu_wall_ns=[b-a for a, b in zip(prepared, measured, strict=True)],
          setup_cpu_wall_ns=[b-a for a, b in zip(start, prepared, strict=True)], resident_after=resident(paths)))
    write(root / "seal.json", {p.name: digest(p) for p in root.iterdir()})


def selection(rows, original, excluded, continuation):
    from anchor_cycle_route import select_route

    outputs = {}
    for mode in MODES:
        for selector in SELECTORS:
            label = mode + "/" + selector
            began = process_time_ns(), perf_counter_ns()
            probes = choose(rows, mode, selector, continuation)
            clock = [process_time_ns() - began[0], perf_counter_ns() - began[1]]
            outputs[label] = dict(probes=probes, selection_cpu_wall_ns=clock)
    probe = outputs["8-primary/strongest"]["probes"]
    prefix = dict(original, source=dict(original["source"], probes=probe),
                  provenance=dict(original["provenance"], window_count=STOP, processed_windows=len(rows)//2,
                                  invalid_capture=len(excluded)))
    return dict(cells=outputs, original_held_selector_at_prefix=select_route(prefix))


def compare(reference, candidate):
    if reference is None:
        return "both_empty" if candidate is None else "gained"
    if candidate is None:
        return "empty"
    epoch = lambda factor: factor["integer_epoch_sample"] + factor["fractional_epoch_offset_samples"]
    cfo_delta = candidate["fractional_tracking_cfo_hz"] - reference["fractional_tracking_cfo_hz"]
    same_measurement = abs(cfo_delta) <= 250 and abs(remainder(epoch(candidate)-epoch(reference), 13_333)) <= 2
    return ("exact" if candidate == reference else "matched") if same_measurement else "displaced"


def observation(row, session):
    payload = f"{session}:{row['receiver_id']}:{row['valid_start_counter']}".encode()
    return "sha256:" + sha256(payload).hexdigest()


def score(root):
    from leo.contracts.digests import canonical_digest

    seal = read(root / "seal.json")
    if seal != {filename: digest(root / filename) for filename in seal} or read(root / "admission.json")["source_sha256"] != sources():
        raise ValueError("Candidate products or frozen source changed before owner scoring")
    pair = controls()
    session = pair["installed"][0]["source"]["session_id"]
    packets = {key: {observation(p, session): p for p in obj[0]["source"]["probes"]} for key, obj in pair.items()}
    old, live = packets["installed"], packets["successor"]
    rows = read(root / "native-rows.json")
    latest = read(root / "selection.json")
    cross = json.loads(boot.checked(CROSSOVER, CROSSOVER_PIN))
    board = {name: cross["ordered_owner_rows"][name + "-" + name] for name in pair}
    by_arm = {}
    for arm in ARMS:
        for name in pair:
            owners = {row[0]: row[1] for row in board[name][arm]}
            if canonical_digest(owners) != pair[name][1]["evidence"]["owners"][arm]:
                raise ValueError("Crossover owners differ from the original terminal")
        stock = {row[0] for row in board["installed"][arm]}
        successor = {row[0] for row in board["successor"][arm]}
        subset = dict(stock=stock, shared=stock & successor,
                      lost_empty={o for o in stock-successor if not live[o]["candidates"]},
                      lost_displaced={o for o in stock-successor if compare(first(old[o]), first(live[o])) == "displaced"},
                      lost_matched={o for o in stock-successor if compare(first(old[o]), first(live[o])) in {"exact", "matched"}})
        if len(subset["lost_empty"]) != 44:
            raise ValueError("Original full capture empty-owner-loss census changed")
        by_arm[arm] = subset
    score_cells = {}
    for label, data in latest["cells"].items():
        mode, _ = label.split("/")
        totals, groups = Counter(), defaultdict(Counter)
        clocks = [0, 0]
        for row, probe in zip(rows, data["probes"], strict=True):
            identifier = observation(probe, session)
            reference = first(old[identifier])
            state = compare(reference, first(probe))
            totals[state] += 1
            effective = "20-two" if row["anchor"] else mode
            choices = row["alternatives"][effective]
            reachable = reference is not None and any(compare(reference, c) in {"matched", "exact"} for c in choices)
            for i, amount in enumerate(row["clocks"][effective]):
                clocks[i] += amount
            for arm, sections in by_arm.items():
                for group, ids in sections.items():
                    if identifier in ids:
                        each = groups[arm + "/" + group]
                        each[state] += 1
                        each["available_before_selector"] += reachable
                        lane = groups[f"{arm}/{group}/rx{probe['receiver_id']}-ch{probe['channel']}"]
                        lane[state] += 1
                        lane["available_before_selector"] += reachable
        score_cells[label] = dict(all_slots=totals, owners=groups, callback_cpu_wall_ns=clocks,
                                 selection_cpu_wall_ns=data["selection_cpu_wall_ns"])
    summary = dict(seal_sha256=digest(root / "seal.json"), full_owner_counts={arm: {name: len(ids) for name, ids in sets.items()}
          for arm, sets in by_arm.items()}, measurements=score_cells, prefix_held=latest["original_held_selector_at_prefix"])
    (root / "scored.json.gz").write_bytes(gzip.compress(json.dumps(summary, sort_keys=True).encode(), mtime=0))


def first(row):
    candidates = row["candidates"]
    return candidates[0] if candidates else None


if __name__ == "__main__":
    sys.path[:0] = [str(boot.PAYLOAD), str(boot.RELEASE / "src"), str(HERE.parents[2])]
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("measure", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    {"measure": measure, "score": score}[args.action](args.root)
