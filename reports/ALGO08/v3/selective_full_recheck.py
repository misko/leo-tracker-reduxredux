"""Measure an exact full-aperture recheck on existing signed prefix detections."""

import argparse
from collections import Counter, defaultdict, deque
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns, process_time_ns


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROTOCOL = HERE / "selective-full-recheck-protocol.md"
OLD_BOUND = 80_000_000
HISTORY_LENGTH = 12
CASES = {
    "DS30-0163": (Path("/tmp/leo-v3-0163-resumed-member-pair02"), "integrated",
                  "332607cbb9d30a8ffeb406a23b50c4419d77f6ec7c04c5cdb0668c139ef09931",
                  "8631fad91d1b9555baf22f752d2679d123244066d3e77100ba7bd6be5ac0945c",
                  "c68eb6ecfedfc770e8d4f02327e15b759d757346f10d41d93ed6bb46fae82238", "named"),
    "DS30-0008": (Path("/tmp/leo-v3-original-dense-intake-result01"), "1-first_use",
                  "2856e72fd8103617e8e4af6249ebbd39a0e449bf655ac98509634cb65e66f60d",
                  "77772c3bb11e717700bb44e010111b45a6742b13032756791a6a3baad5b69828",
                  "9e9c5b2503b95c09c1e7fdd42fa5add20a54ba59d32d3ff04d48fe49ff49d8ca", "1-named"),
}


def read(path, pin):
    body = path.read_bytes()
    if sha256(body).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Frozen detector input changed at {path.name}")
    return json.loads(body)


def clocks():
    return process_time_ns(), perf_counter_ns()


def spent(start):
    now = clocks()
    return {unit: b - a for unit, a, b in zip(("cpu_ns", "wall_ns"), start, now, strict=True)}


def digest_file(path):
    return sha256(path.read_bytes()).hexdigest()


def lane(row):
    return row["visit_index"], row["receiver_id"]


def key(row):
    return tuple(row[f] for f in ("edge", "receiver_id", "channel", "actual_rf_hz"))


class Shortlist:
    """Hardware chronology has no path for named answers, owners or geography."""

    def __init__(self, continuation):
        self.continuation = continuation
        self.remembered = defaultdict(lambda: deque(maxlen=HISTORY_LENGTH))

    def consider(self, row, aperture):
        if len(row["candidates"]) > 1:
            raise ValueError("Expected the original one-measurement mixed chronology")
        counter = row["valid_start_counter"]
        history = self.remembered[key(row)]
        preceding = sum(kept and 0 < counter - start <= OLD_BOUND for start, kept in history)
        _, keep, votes = self.continuation.select(row)
        matched = aperture == "short" and votes == [0] and preceding > 0
        history.append((counter, keep is not None))
        return dict(lane=lane(row), aperture=aperture, same_lane_prior_kept=preceding, votes=votes, selected=matched)


def shortlist(rows, entries, continuation):
    history = Shortlist(continuation)
    decisions, selected = [], set()
    for row, event in zip(rows, entries, strict=True):
        visit, _, radio, _, aperture, _ = event
        if lane(row) != (visit, radio):
            raise ValueError("Expected the original one-measurement mixed chronology")
        decision = history.consider(row, aperture)
        decisions.append(decision)
        if decision["selected"]:
            selected.add(lane(row))
    return selected, decisions


def rechecked(base, factors, continuation):
    if factors is None:
        continuation.select(base)
        return base, None
    _, keep, votes = continuation.select(dict(base, candidates=factors))
    chosen = [] if keep is None else [factors[keep]]
    return dict(base, candidates=chosen), dict(lane=lane(base), full_candidates=factors, votes=votes, chosen=chosen)


def replace(rows, replacements, continuation):
    result, witness = [], []
    for base in rows:
        row, evidence = rechecked(base, replacements.get(lane(base)), continuation)
        result.append(row)
        if evidence is not None:
            witness.append(evidence)
    return result, witness


def full_candidates(factors, constructor):
    rows = [constructor(rank, epoch, status="complete", offset=offset, cfo=hz, exact=exact, control=roll,
                        margin=exact-roll) for rank, epoch, offset, hz, exact, roll in factors]
    if any(not row["passed_fractional_margin_gate"] for row in rows):
        raise ValueError("Full ABI returned an invalid candidate")
    return rows


def inputs(case):
    from continued_cfo_trial import rebinding
    from leo.contracts.digests import canonical_digest

    root, branch, binding_pin, packet_pin, witness_pin, _ = CASES[case]
    binding = read(root / "binding.json", binding_pin)
    scope = binding["scopes"]["1"] if "scopes" in binding else binding
    nested = scope["inventory"]
    entry, = nested["segments"]
    member, = nested["prefix_members"]
    source = Path(entry["path"])
    receipt = read(root / f"{branch}-held-anchor-route.json", witness_pin)
    native = read(root / branch / "detections.json", packet_pin)
    recipe = {k: v for k, v in receipt["receiver_recipe"].items() if k != "held_native_8ms"}
    original = rebinding(native, native["source"]["probes"], recipe)
    if (not source.is_absolute() or source.resolve(strict=True) != source or source.parts[1:3] == ("srv", "bulk")
            or subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", source], text=True).strip() != "tmpfs"
            or scope["stop"] != 64 or member["window_count"] != 64 or member["first_sequence"]
            or receipt["choice"]["route"] != "unfiltered" or receipt["refinement_calls"]
            or canonical_digest(original) != receipt["parent_native_sha256"]
            or canonical_digest(recipe) != receipt["parent_detector_sha256"]
            or native["source"]["input_manifest_sha256"] != scope["digest"]
            or canonical_digest(nested) != scope["digest"]):
        raise ValueError("Expected one independently authenticated original first-member acquisition")
    paths = [source / name for name in ("manifest.json", member["index_relative_path"], member["payload_relative_path"])]
    return native, original, recipe, scope, entry, member, paths


def resident(paths):
    rows = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE,FILE", *paths]))["fincore"]
    if len(rows) != 3 or any(r["res"] < r["size"] for r in rows):
        raise ValueError("All enrolled original member pages must remain resident")
    return rows


def full_lookup(original, entry, member, scheduled, full_binary, tab):
    import numpy as np
    from empty_bootstrap import RELEASE, checked
    from leo.contracts.digests import canonical_digest
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.storage.fast_scan import FastSegmentSource
    from mixed_aperture_receiver import NativePath, PILOT_SHA
    from tools.pipeline_eval.qualification.blind_compact_run import factor_candidate

    if not scheduled:
        return {}, dict(no_new_waveform_read=True)
    observed = {lane(row): row for row in original["source"]["probes"]}
    excluded = {row["visit"]: row for row in original["provenance"]["excluded_windows"]}
    edge = next(iter(observed.values()))["edge"]
    asset = np.frombuffer(checked(RELEASE / "assets" / f"{edge}.f32", PILOT_SHA[edge]), dtype="<f4")
    setup = clocks()
    receiver = NativePath(full_binary, asset, "full")
    tab["context_setup"] = spent(setup)
    reading, calls = Counter(), []
    returned, hashes = {}, []

    def timed_next(stream):
        tick = clocks()
        try:
            return next(stream)
        finally:
            reading.update(spent(tick))

    policy = FastScanPolicyV2()
    try:
        source = FastSegmentSource(entry, stop_sequence=64)
        if (source.reader.manifest_sha256 != entry["manifest_digest"] or
                source.reader.manifest.chunks[0].model_dump(mode="json") != member or tuple(source.receiver_ids) != (0, 1)):
            raise ValueError("The full native receiver must use the exact signed local first member")
        with closing(source.windows()) as sequence:
            for visit in range(64):
                window = timed_next(sequence)
                a, target = window.acquisition, window.target
                telemetry = json.loads(a["retune_receipt"])
                valid = valid_window_support(a, window.sample_rate_hz, window.samples.shape, (0, 1), policy)
                if (a["global_visit"] != visit or target["edge"] != edge
                        or telemetry["host_delivery_clock"] != original["delivery_clocks"][visit]
                        or (visit == 0 and telemetry["utc_clock_bracket"] != original["clock_anchor"])
                        or valid != (visit not in excluded)
                        or (not valid and (a["sample_start"], a["sample_end"], window.iq_sha256) != tuple(
                            excluded[visit][k] for k in ("sample_start", "sample_end", "iq_sha256")))):
                    raise ValueError("Original signed window support, clock or exclusion changed")
                hashes.append(window.iq_sha256)
                if not valid:
                    continue
                for radio in (0, 1):
                    row = observed[visit, radio]
                    rf = a["actual_if_center_hz"] + target["lnb_lo_hz"]
                    if (row["channel"], row["actual_rf_hz"], row["valid_start_counter"]) != (
                            target["channel"], rf, a["sample_start"]):
                        raise ValueError("Archived candidate lane identity differs from original signed support")
                    if (visit, radio) in scheduled:
                        midpoint = target["rf_center_hz"] - target["lnb_lo_hz"] - a["actual_if_center_hz"]
                        factors, (cpu, wall) = receiver.run(window.samples, radio, midpoint)
                        returned[visit, radio] = full_candidates(factors, factor_candidate)
                        calls.append(dict(lane=(visit, radio), cpu_ns=cpu, wall_ns=wall))
            try:
                timed_next(sequence)
            except StopIteration:
                pass
            else:
                raise ValueError("Unexpected next member beyond the authorized scope")
    finally:
        receiver.close()
    if (set(returned) != scheduled or canonical_digest([original["source"]["input_manifest_sha256"], hashes])
            != original["source"]["raw_recording_authority_digest"]):
        raise ValueError("The reread must reproduce the scoped original authority and all flagged calls")
    return returned, dict(reader_ns=dict(reading), native_calls=calls, original_window_hashes=hashes)


def run(case, root):
    from empty_bootstrap import load_runtime

    setup = clocks()
    _, spec, _, _, _ = load_runtime()
    from anchor_exposure import enroll
    from continued_cfo_trial import rebinding
    from dense_geographic_trial import host
    from eight_ms_held_fit import select
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import immutable_json
    from original_prefix_scaling import guard
    from tools.pipeline_eval.variants.carrier_continuation import Continuation

    machine = host()
    base, original, recipe, scope, entry, member, paths = inputs(case)
    before = resident(paths)
    sys.addaudithook(guard(paths))
    times = {"receiver_runtime_and_input_admission": spent(setup)}
    rows = original["source"]["probes"]
    start = clocks()
    scheduled, decisions = shortlist(rows, enroll(original), Continuation())
    times["shortlist"] = spent(start)
    start = clocks()
    measured, acquisition = full_lookup(original, entry, member, scheduled, spec["detector"], times)
    times["incremental_reader_and_full_calls"] = spent(start)
    start = clocks()
    mixed, replacement = replace(rows, measured, Continuation())
    times["replacement_temporal_pass"] = spent(start)
    additions = dict(protocol_sha256=digest_file(PROTOCOL), implementation_sha256=digest_file(Path(__file__)),
                     original_detector=canonical_digest(recipe), installed_full_sha256=spec["detector_sha256"],
                     source_policy="candidate-only zero votes with preceding kept stream history")
    recheck_recipe = dict(recipe, selective_full_20ms_recheck=additions)
    start = clocks()
    packet, witness = select(rebinding(original, mixed, recheck_recipe), recheck_recipe)
    times["original_held_eof"] = spent(start)
    root.mkdir(mode=0o750)
    start = clocks()
    immutable_json(root / "detections.json", packet)
    times["immutable_detection_write"] = spent(start)
    if (canonical_digest(packet) != "sha256:" + digest_file(root / "detections.json")
            or packet["source"]["raw_recording_authority_digest"] != base["source"]["raw_recording_authority_digest"]):
        raise ValueError("New immutable detector evidence changed original acquisition authority")
    immutable_json(root / "receipt.json", dict(case=case, machine=machine, binding=scope, original_member=member,
                   legacy_candidate_sha256=canonical_digest(base), output_sha256=canonical_digest(packet),
                   original_parent_sha256=canonical_digest(original), old_detector_recipe=recipe,
                   replacements=replacement, decisions=decisions, held=witness, acquisition=acquisition,
                   times=times, prelaunch_residency=before, postlaunch_residency=resident(paths),
                   position_solvers=0, original_backing_reads=0))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("case", choices=CASES)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    run(args.case, args.output)
