"""Confirm prospective repair factors against the sealed full-aperture packet."""

import argparse
from collections import Counter, defaultdict, deque
from hashlib import sha256
from math import remainder
from pathlib import Path
import subprocess
from time import perf_counter, process_time
from unittest.mock import patch

from aperture_trial import RELEASE, archive_identity, read, write
from local_future_0057 import changes


HERE = Path(__file__).resolve().parent
CASES = ("DS30-0016", "DS30-0057")
RAW_STEREO_BYTES = 200_000 * 2 * 2 * 2
SUPPORT_SAMPLES = 80_000_000
SUPPORT_ROWS = 12


def history_plan(probes, targets, already_full):
    """Count the known Python history inputs, without assuming native replay parity."""
    history = defaultdict(lambda: deque(maxlen=SUPPORT_ROWS))
    visit_counters, needed = {}, set()
    for probe in probes:
        visit, receiver = probe["visit_index"], probe["receiver_id"]
        counter = probe["valid_start_counter"]
        visit_counters[visit] = counter
        lane = receiver, probe["channel"], probe["actual_rf_hz"]
        if (visit, receiver) in targets:
            needed.add((visit, receiver))
            needed.update((old_visit, receiver) for old_visit, old_counter in history[lane]
                          if 0 < counter - old_counter <= SUPPORT_SAMPLES)
        history[lane].append((visit, counter))
    target_visits = {visit for visit, _ in targets}
    history_visits = {visit for visit, _ in needed}
    last = max(target_visits, default=-1)
    prefix_visits = sum(visit <= last for visit in visit_counters)
    return dict(
        target_lanes=len(targets), target_visits=len(target_visits),
        history_context_lanes=len(needed-targets), history_target_and_context_lanes=len(needed),
        history_target_and_context_visits=len(history_visits),
        history_context_already_full_lanes=sum(visit in already_full for visit, _ in needed-targets),
        history_stereo_visits_with_retained_full_vectors=len(history_visits-already_full),
        prefix_admitted_full_visits=prefix_visits, prefix_last_issued_visit=last,
        target_only_stereo_decoded_bytes=len(target_visits)*RAW_STEREO_BYTES,
        history_stereo_decoded_bytes=len(history_visits)*RAW_STEREO_BYTES,
        prefix_admitted_decoded_bytes=prefix_visits*RAW_STEREO_BYTES,
        potential_initial_pass_buffer_bytes=len(visit_counters)*RAW_STEREO_BYTES,
        admitted_visits=len(visit_counters),
    )


def confirm(stock, short, future):
    from short_primary_epoch_audit import FRAME_SAMPLES, epoch, good_match, paired_probes

    ids = {row["observation_id"] for row in future}
    if len(ids) != len(future):
        raise ValueError("Duplicate prospective observation ID")
    counts, targets, full, keep, matched = Counter(), set(), set(), set(), set()
    for oid, probe, original, candidate, short_slot in paired_probes(stock, short):
        visit, receiver = probe["visit_index"], probe["receiver_id"]
        if not short_slot:
            full.add(visit)
        if oid not in ids:
            continue
        if candidate is None:
            raise ValueError("Prospective observation must be a verified original factor")
        counts["future"] += 1
        if not short_slot:
            counts["already_full"] += 1
            keep.add(oid)
            continue
        targets.add((visit, receiver))
        counts["short_future"] += 1
        if good_match(original, candidate):
            counts["confirmed_short"] += 1
            matched.add(oid)
            keep.add(oid)
        elif original is None:
            counts["missing_stock_selected_factor"] += 1
        elif original["candidate_rank"] != 0:
            counts["stock_selected_residual"] += 1
        else:
            phase = abs(remainder(epoch(candidate)-epoch(original), FRAME_SAMPLES)) > 2.
            cfo = abs(candidate["fractional_tracking_cfo_hz"]-original["fractional_tracking_cfo_hz"]) > 250.
            counts["mismatched_phase_and_cfo" if phase and cfo else
                   "mismatched_phase" if phase else "mismatched_cfo"] += 1
    if counts["future"] != len(future):
        raise ValueError("Prospective roster did not match the original lanes")
    kept = [row for row in future if row["observation_id"] in keep]
    return kept, dict(counts=dict(counts), matched_short_ids=sorted(matched),
                      already_full_ids=sorted(keep-matched),
                      history=history_plan(short["source"]["probes"], targets, full))


def inputs(case):
    from local_future_0057 import inputs as transfer
    from short_stereo_trial import CONTROLS, controls, single_packet, source_for

    row, short_pin, saved, geo, regional = transfer("repair")
    if case == "DS30-0057":
        _, stock_pin, stock, _, _ = transfer("stock")
        target = Path("/tmp/leo-protected-DS30-0057-01")
        return dict(recording=Path(row["recording"]), archive=row["archive"], region=Path(row["region_file"]),
                    offer=row["region"], short=saved, short_pin=short_pin, stock=stock, stock_pin=stock_pin,
                    stock_terminal=row["runs"]["stock"]["retained_handoff"]["terminal_sha256"],
                    stock_images=Path(row["archived_stock_publication"]["root"]),
                    original_full_images=row["archived_stock_publication"]["pngs"],
                    forward=target / "forward", unconfirmed=target / "repair", geo=geo, regional=regional)
    if case != "DS30-0016":
        raise ValueError("Only the frozen physical cases are enrolled")
    recording, archive, region, saved, short_pin, offer = source_for("physical")
    references = {name: read(HERE / "measurements" / name) for name in CONTROLS}
    stock_root, stock_pin, stock_terminal, _, _ = controls("physical", references)
    return dict(recording=recording, archive=archive, region=region, offer=offer, short=saved, short_pin=short_pin,
                stock=single_packet(stock_root), stock_pin=stock_pin, stock_terminal=stock_terminal,
                stock_images=stock_root, original_full_images=references["weak-combined-raw.json"]["runs"]["stock"]["images"],
                forward=Path("/var/tmp/leo-causal-weak-south-nov23/physical"),
                unconfirmed=Path("/var/tmp/leo-local-future-repair.DqnORtL8/replay/physical"), geo=geo, regional=regional)


def bind(case):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from short_primary_epoch_audit import SHORT, STOCK
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA

    request = inputs(case)
    stock, short = (read(request[key]) for key in ("stock", "short"))
    for key, document, detector in (("stock", stock, STOCK), ("short", short, SHORT)):
        source = document["source"]
        if (canonical_digest(document) != request[f"{key}_pin"]
                or detector != document["provenance"]["detector_sha256"]
                or source["analysis_manifest_sha256"] != canonical_digest([
                    "cancellation", source["raw_recording_authority_digest"], detector[7:], source["probes"]])):
            raise ValueError(f"Saved {key} detector differs from the frozen packet")
    if (Algo08Region.parse(read(request["region"])).document() != request["offer"]
            or archive_identity(Path(request["archive"]["root"])) != request["archive"]):
        raise ValueError("Causal archive or operator region differs from the original pair")
    for key, expected in (("geo", GEOGRAPHIC_SHA), ("regional", TRACK_SCORES_SHA)):
        if sha256(request[key].read_bytes()).hexdigest() != expected:
            raise ValueError("Unexpected geographic or regional solver library")
    return request, stock, short


def worker(case, output):
    import local_future_repair_trial as trial

    request = inputs(case)
    original = trial.future_observations
    audit = {}

    def confirmed(short, forward):
        _, stock, checked_short = bind(case)
        if checked_short != short:
            raise ValueError("Solver preparation received another short packet")
        future = original(short, forward)
        begin = process_time(), perf_counter()
        kept, evidence = confirm(stock, short, future)
        audit.update(evidence, selection_cpu_s=process_time()-begin[0], selection_elapsed_s=perf_counter()-begin[1])
        return kept

    with patch.object(trial, "future_observations", confirmed):
        trial.worker(request["short"], request["short_pin"], output, request["recording"],
                     Path(request["archive"]["root"]), request["region"], request["geo"], request["regional"])
    write(output / "full-aperture-admission.json", audit)


def launch(case, root):
    from dense_full_short_raw import usage
    from dense_geographic_trial import host
    from full_short_physical import environment

    roster = host()
    root.mkdir(exist_ok=False)
    env = environment(root)
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    start, before = perf_counter(), usage()
    run = subprocess.run([python, "-BPs", __file__, "worker", case, root / "confirmed"],
                         env=env, capture_output=True, text=True, timeout=75)
    after = usage()
    write(root / "confirmed-clock.json", dict(elapsed_s=perf_counter()-start, status=run.returncode,
          machine=roster, stderr_tail=run.stderr[-4000:], **{key: after[key]-before[key] for key in before}))
    if run.returncode:
        raise ValueError(run.stderr[-4000:])


def score(case, root):
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_inputs import future_observations
    from mixture_score import section
    from north_factor_swap import continued
    from short_stereo_trial import single_packet
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    request, stock, short = bind(case)
    if sha256(REFERENCE.read_bytes()).hexdigest() != REFERENCE_SHA256:
        raise ValueError("Unrecognized reference roster")
    ref, = [row["reference"] for row in read(REFERENCE)["cases"] if row["dataset_label"] == case
            and row["authority_eligible"] and row["sealed_metadata_digests_verified"]]
    truth = [ref["latitude_deg"], ref["longitude_deg"]]
    stock_root = request["stock_images"]
    terminal_path, = stock_root.glob("fast-scan-automatic-work/*/terminal.json")
    stock_terminal = read(terminal_path)
    if (canonical_digest(stock_terminal) != request["stock_terminal"]
            or stock_terminal["native_sha256"] != request["stock_pin"]
            or stock_terminal["region"] != request["offer"]):
        raise ValueError("Installed stock figure authority differs")
    stock_evidence = artifacts(stock_root, dict(run_id=terminal_path.parent.name, decision="complete",
                                                terminal_sha256=request["stock_terminal"]))
    if canonical_digest(stock_evidence["images"]) != canonical_digest(request["original_full_images"]):
        raise ValueError("Archived stock image fingerprints changed")
    stock_store = FastStandardAnalysisStore(stock_root)
    stock_grid = stock_store.position_grid(terminal_path.parent.name)
    stock_replay = stock_grid["endpoint_objective_replay"]
    if not stock_grid["complete"] or set(stock_replay.values()) != {0.}:
        raise ValueError("Installed grid is incomplete or fails its endpoint objective replay")
    output = root / "confirmed"
    audit = read(output / "full-aperture-admission.json")
    forward = continued(short)
    prospective = future_observations(short, forward)
    eligible, expected = confirm(stock, short, prospective)
    if any(audit.get(key) != value for key, value in expected.items()):
        raise ValueError("Recomputed full aperture gating differs from the solver admission")
    policy = read(output / "local-future-policy.json")
    if (policy["forward_sha256"] != canonical_digest(forward)
            or policy["future_ids"] != [row["observation_id"] for row in eligible]):
        raise ValueError("Aperture gating altered the causal path or admitted different observations")

    def checked(folder, pin):
        run = read(folder / "joint-research-receipt.json")
        receipt = run["receipt"]
        terminal = read(folder / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")
        publication = artifacts(folder, receipt)
        if (canonical_digest(publication) != canonical_digest(run["evidence"])
                or terminal["native_sha256"] != pin or canonical_digest(terminal) != receipt["terminal_sha256"]
                or terminal["region"] != request["offer"] or receipt["decision"] != "complete"
                or not run["solve"]["grid_complete"] or set(run["solve"]["objective_replay"].values()) != {0.}):
            raise ValueError("Expected complete sealed and replayable position, grid, and figures")
        return dict(score=section(terminal["arms"], truth, stock_terminal["arms"]), publication=publication,
                    solve=run["solve"], terminal_sha256=receipt["terminal_sha256"],
                    full_native_sha256=terminal["native_sha256"],
                    repair=(run["route_details"] or {}).get("local_future_repair")), run["selected_rows"]

    # The weak forward publication stored a rebound detection packet with the exact
    # same retained measurements. The newer forward run stored the original short packet.
    forward_pin = canonical_digest(read(single_packet(request["forward"])))
    if forward_pin != request["short_pin"]:
        saved_forward = read(single_packet(request["forward"]))
        if saved_forward["source"]["probes"] != forward["source"]["probes"]:
            raise ValueError("Archived forward inputs differ from the kept measurements")
    before, owners = checked(request["forward"], forward_pin)
    unconfirmed, more = checked(request["unconfirmed"], request["short_pin"])
    confirmed, resulting = checked(output, request["short_pin"])
    if not confirmed["repair"]:
        raise ValueError("The confirmed repair route did not run")
    added = {row["observation_id"] for row in confirmed["repair"].get("added", ())}
    audit["additions_by_aperture"] = {key: len(added.intersection(audit[key]))
                                      for key in ("already_full_ids", "matched_short_ids")}
    original_added, confirmed_added = {}, {}
    eligible_ids = set(policy["future_ids"])
    for arm in ("c0", "fitted_c"):
        original_added[arm] = changes(owners[arm], more[arm])
        confirmed_added[arm] = changes(owners[arm], resulting[arm])
        before_ids = {row[0] for row in owners[arm]}
        after_ids = {row[0] for row in resulting[arm]}
        if not after_ids - before_ids <= eligible_ids or confirmed_added[arm]["lost"] or confirmed_added[arm]["changed"]:
            raise ValueError("Confirmation introduced an ineligible observation or changed an old owner")
    confirmed["process"] = read(root / "confirmed-clock.json")
    screen = all(scores["delta_error_km"] <= .25 for scores in confirmed["score"]["arms"].values())
    return dict(case=case, effective_confirmed_policy=policy, admission=audit,
                bindings=dict(archive=request["archive"], region=request["offer"],
                              original_receiver=request["short_pin"], full_aperture_packet=request["stock_pin"],
                              evaluation_reference=truth),
                runs=dict(stock=dict(score=section(stock_terminal["arms"], truth, stock_terminal["arms"]),
                                     publication=stock_evidence, terminal_sha256=request["stock_terminal"],
                                     full_native_sha256=request["stock_pin"],
                                     solve=dict(grid_complete=stock_grid["complete"],
                                                grid_points=stock_grid["evaluated_points"],
                                                objective_replay=stock_replay)),
                          forward=before, unconfirmed=unconfirmed, confirmed=confirmed),
                owner_changes=dict(unconfirmed=original_added, confirmed=confirmed_added),
                screen_passed=screen)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("trial", "worker", "score"))
    parser.add_argument("case", choices=CASES)
    parser.add_argument("root", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.mode == "worker":
        worker(args.case, args.root)
    elif args.mode == "trial":
        launch(args.case, args.root)
    elif not args.receipt:
        parser.error("--receipt is required for scoring")
    else:
        write(args.receipt, score(args.case, args.root))
